import json
import re
import shutil
import subprocess
import time
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from config import (
    COMMAND_TIMEOUT_SECONDS,
    MAX_COMMAND_OUTPUT_CHARS,
    MAX_WEB_CONTENT_CHARS,
    MAX_WEB_RESULTS,
    WEB_TIMEOUT_SECONDS,
)


class LocalToolExecutor:
    def __init__(self, workspace_root=None, allow_run_command=False, allow_file_edits=True):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.allow_run_command = allow_run_command
        self.allow_file_edits = allow_file_edits

    def execute(self, tool_call):
        if not isinstance(tool_call, dict):
            raise ValueError("Tool call must be a JSON object.")

        action = tool_call.get("action")
        if action == "read_file":
            return self._read_file(tool_call.get("path"))
        if action == "write_file":
            self._ensure_file_edits_allowed(action)
            return self._write_file(tool_call.get("path"), tool_call.get("content", ""))
        if action == "update_file":
            self._ensure_file_edits_allowed(action)
            return self._update_file(
                tool_call.get("path"),
                tool_call.get("find", ""),
                tool_call.get("replace", ""),
                bool(tool_call.get("replace_all", False)),
            )
        if action == "list_dir":
            return self._list_dir(tool_call.get("path", "."))
        if action == "search_text":
            return self._search_text(
                tool_call.get("path", "."),
                tool_call.get("query", ""),
                bool(tool_call.get("case_sensitive", False)),
            )
        if action == "make_dir":
            self._ensure_file_edits_allowed(action)
            return self._make_dir(tool_call.get("path"))
        if action == "move_path":
            self._ensure_file_edits_allowed(action)
            return self._move_path(tool_call.get("src"), tool_call.get("dest"))
        if action == "copy_path":
            self._ensure_file_edits_allowed(action)
            return self._copy_path(tool_call.get("src"), tool_call.get("dest"))
        if action == "delete_path":
            self._ensure_file_edits_allowed(action)
            return self._delete_path(tool_call.get("path"), bool(tool_call.get("recursive", False)))
        if action == "search_web":
            return self._search_web(tool_call.get("query", ""))
        if action == "fetch_url":
            return self._fetch_url(tool_call.get("url", ""))
        if action == "run_command":
            return self._run_command(tool_call.get("command", ""), tool_call.get("path", "."))

        raise ValueError(f"Unsupported action: {action}")

    def format_result(self, result):
        return json.dumps(result, ensure_ascii=True, indent=2)

    def _resolve_path(self, raw_path):
        if not raw_path:
            raise ValueError("Missing required 'path' value.")

        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path

        return path.resolve(strict=False)

    def _read_file(self, raw_path):
        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "action": "read_file",
            "path": str(path),
            "content": content,
        }

    def _write_file(self, raw_path, content):
        path = self._resolve_path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return {
            "ok": True,
            "action": "write_file",
            "path": str(path),
            "bytes_written": len(content.encode("utf-8")),
        }

    def _list_dir(self, raw_path):
        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        entries = []
        for item in sorted(path.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())):
            entry_type = "dir" if item.is_dir() else "file"
            entries.append({"name": item.name, "type": entry_type})

        return {
            "ok": True,
            "action": "list_dir",
            "path": str(path),
            "entries": entries,
        }

    def _update_file(self, raw_path, find_text, replace_text, replace_all):
        if not find_text:
            raise ValueError("Missing required 'find' value.")

        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        original = path.read_text(encoding="utf-8", errors="replace")
        if find_text not in original:
            raise ValueError("Target text not found in file.")

        if replace_all:
            occurrences = original.count(find_text)
            updated = original.replace(find_text, replace_text)
        else:
            occurrences = 1
            updated = original.replace(find_text, replace_text, 1)

        path.write_text(updated, encoding="utf-8")
        return {
            "ok": True,
            "action": "update_file",
            "path": str(path),
            "replacements": occurrences,
            "bytes_written": len(updated.encode("utf-8")),
        }

    def _search_text(self, raw_path, query, case_sensitive):
        if not query:
            raise ValueError("Missing required 'query' value.")

        base_path = self._resolve_path(raw_path)
        if not base_path.exists():
            raise FileNotFoundError(f"Path not found: {base_path}")

        files_to_scan = []
        if base_path.is_file():
            files_to_scan = [base_path]
        else:
            files_to_scan = [p for p in base_path.rglob("*") if p.is_file()]

        if case_sensitive:
            needle = query
        else:
            needle = query.lower()

        matches = []
        max_matches = 200
        for file_path in files_to_scan:
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for line_number, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    matches.append(
                        {
                            "path": str(file_path),
                            "line": line_number,
                            "text": line[:240],
                        }
                    )
                    if len(matches) >= max_matches:
                        return {
                            "ok": True,
                            "action": "search_text",
                            "path": str(base_path),
                            "query": query,
                            "truncated": True,
                            "matches": matches,
                        }

        return {
            "ok": True,
            "action": "search_text",
            "path": str(base_path),
            "query": query,
            "truncated": False,
            "matches": matches,
        }

    def _make_dir(self, raw_path):
        path = self._resolve_path(raw_path)
        path.mkdir(parents=True, exist_ok=True)
        return {
            "ok": True,
            "action": "make_dir",
            "path": str(path),
        }

    def _move_path(self, raw_src, raw_dest):
        src = self._resolve_path(raw_src)
        dest = self._resolve_path(raw_dest)
        if not src.exists():
            raise FileNotFoundError(f"Source path not found: {src}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        moved = shutil.move(str(src), str(dest))
        return {
            "ok": True,
            "action": "move_path",
            "src": str(src),
            "dest": str(Path(moved)),
        }

    def _copy_path(self, raw_src, raw_dest):
        src = self._resolve_path(raw_src)
        dest = self._resolve_path(raw_dest)
        if not src.exists():
            raise FileNotFoundError(f"Source path not found: {src}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                raise FileExistsError(f"Destination already exists: {dest}")
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

        return {
            "ok": True,
            "action": "copy_path",
            "src": str(src),
            "dest": str(dest),
        }

    def _delete_path(self, raw_path, recursive):
        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        if path == self.workspace_root:
            raise ValueError("Refusing to delete workspace root.")

        if path.is_dir():
            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()
        else:
            path.unlink()

        return {
            "ok": True,
            "action": "delete_path",
            "path": str(path),
            "recursive": recursive,
        }

    def _search_web(self, query):
        query = (query or "").strip()
        if not query:
            raise ValueError("Missing required 'query' value.")

        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        response = requests.get(
            search_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=WEB_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        results = self._parse_duckduckgo_results(response.text)
        return {
            "ok": True,
            "action": "search_web",
            "query": query,
            "results": results[:MAX_WEB_RESULTS],
        }

    def _fetch_url(self, url):
        url = (url or "").strip()
        if not url:
            raise ValueError("Missing required 'url' value.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=WEB_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        raw = response.text
        text = self._html_to_text(raw) if "text/html" in content_type.lower() else raw
        return {
            "ok": True,
            "action": "fetch_url",
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content": text[:MAX_WEB_CONTENT_CHARS],
            "truncated": len(text) > MAX_WEB_CONTENT_CHARS,
        }

    def _run_command(self, command, raw_path):
        if not command:
            raise ValueError("Missing required 'command' value.")
        if not self.allow_run_command:
            return {
                "ok": False,
                "action": "run_command",
                "error": "Command execution is disabled. Enable it with /cmd on.",
            }

        workdir = self._resolve_path(raw_path)
        if workdir.is_file():
            workdir = workdir.parent

        if not workdir.exists():
            raise FileNotFoundError(f"Working directory not found: {workdir}")

        started_at = time.perf_counter()
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        stdout = (completed.stdout or "")[:MAX_COMMAND_OUTPUT_CHARS]
        stderr = (completed.stderr or "")[:MAX_COMMAND_OUTPUT_CHARS]

        return {
            "ok": completed.returncode == 0,
            "action": "run_command",
            "command": command,
            "path": str(workdir),
            "exit_code": completed.returncode,
            "elapsed_ms": elapsed_ms,
            "stdout": stdout,
            "stderr": stderr,
        }

    def _ensure_file_edits_allowed(self, action):
        if self.allow_file_edits:
            return
        raise PermissionError(
            f"Action '{action}' is disabled in current mode. Switch to /mode agent to allow file edits."
        )

    def _parse_duckduckgo_results(self, html_text):
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        results = []
        for match in pattern.finditer(html_text):
            href = unescape(match.group("href"))
            parsed = urlparse(href)
            if parsed.path.startswith("/l/"):
                query = parse_qs(parsed.query)
                redirect = query.get("uddg", [])
                if redirect:
                    href = unquote(redirect[0])

            title_html = match.group("title")
            title = self._strip_tags(unescape(title_html)).strip()
            if not title or not href.startswith(("http://", "https://")):
                continue

            results.append({"title": title, "url": href})
            if len(results) >= MAX_WEB_RESULTS:
                break
        return results

    def _html_to_text(self, html_text):
        cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
        cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
        cleaned = self._strip_tags(cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
        return cleaned.strip()

    def _strip_tags(self, value):
        return re.sub(r"(?s)<[^>]*>", " ", value)
