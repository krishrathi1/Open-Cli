import json
import re
from pathlib import Path

import requests

from config import (
    CLI_NAME,
    DEFAULT_EXECUTION_MODE,
    DEFAULT_MODEL,
    MAX_TOOL_ROUNDS,
    OPENROUTER_API_KEY,
    REQUEST_TIMEOUT_SECONDS,
    SYSTEM_PROMPT_TEMPLATE,
)
from local_tools import LocalToolExecutor


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL | re.IGNORECASE)
LEGACY_FUNCTION_RE = re.compile(r"<function=([a-zA-Z0-9_]+)>", re.IGNORECASE)
LEGACY_PARAM_RE = re.compile(
    r"<parameter=([a-zA-Z0-9_]+)>\s*(.*?)\s*</parameter>",
    re.DOTALL | re.IGNORECASE,
)


class OpenRouterClient:
    def __init__(self, workspace_root=None):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.execution_mode = "agent"
        self.command_execution_enabled = True
        self.file_edits_enabled = True
        self.executor = LocalToolExecutor(
            self.workspace_root,
            allow_run_command=self.command_execution_enabled,
            allow_file_edits=self.file_edits_enabled,
        )
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(workspace_root=self.workspace_root)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Krish/openrouter-cli",
            "X-Title": CLI_NAME,
        }
        self.messages = []
        self.last_model_used = None
        self.last_model_fallback_from = None
        self.set_execution_mode(DEFAULT_EXECUTION_MODE)

    @property
    def supported_actions(self):
        return [
            "list_dir",
            "read_file",
            "search_text",
            "search_web",
            "fetch_url",
            "write_file",
            "update_file",
            "make_dir",
            "move_path",
            "copy_path",
            "delete_path",
            "run_command",
        ]

    def send_message(self, content, model_name):
        if not self.api_key:
            return "Error: OPENROUTER_API_KEY is missing. Add it to the .env file.", None, []

        self.last_model_used = model_name
        self.last_model_fallback_from = None
        self.messages.append({"role": "user", "content": content})
        tool_events = []

        try:
            return self._run_tool_loop(model_name, tool_events)
        except requests.exceptions.Timeout:
            return "Error: Request to OpenRouter timed out.", None, tool_events
        except requests.exceptions.ConnectionError as exc:
            message = str(exc)
            if "getaddrinfo failed" in message or "Failed to resolve" in message:
                return "Error: DNS lookup failed for openrouter.ai. Check your internet connection or DNS settings.", None, tool_events
            return f"Error: Network connection failed: {message}", None, tool_events
        except requests.exceptions.HTTPError as exc:
            response_text = self._extract_http_error_text(exc)
            if self._is_policy_blocked_error(response_text):
                fallback_model = self._pick_fallback_model(model_name)
                if fallback_model:
                    self.last_model_fallback_from = model_name
                    self.last_model_used = fallback_model
                    try:
                        content, reasoning, tool_events = self._run_tool_loop(fallback_model, tool_events)
                        note = (
                            f"Model `{model_name}` is blocked by OpenRouter privacy policy. "
                            f"Automatically switched to `{fallback_model}`.\n\n"
                        )
                        return f"{note}{content}", reasoning, tool_events
                    except Exception:
                        pass

                friendly_error = self._friendly_openrouter_error(response_text)
                if friendly_error:
                    return friendly_error, None, tool_events
            return f"Error: OpenRouter returned HTTP {exc.response.status_code if exc.response else 'error'} {response_text}".strip(), None, tool_events
        except Exception as exc:
            return f"Error: {exc}", None, tool_events

    def clear_history(self):
        self.messages = []

    def list_directory(self, path="."):
        return self.executor.execute({"action": "list_dir", "path": path})

    def set_command_execution_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled:
            self.set_execution_mode("agent")
        else:
            if self.execution_mode == "agent":
                self.set_execution_mode("safe")
            else:
                self.command_execution_enabled = False
                self.executor.allow_run_command = False

    def run_command(self, command, path="."):
        return self.executor.execute({"action": "run_command", "command": command, "path": path})

    def search_web(self, query):
        return self.executor.execute({"action": "search_web", "query": query})

    def fetch_url(self, url):
        return self.executor.execute({"action": "fetch_url", "url": url})

    def set_execution_mode(self, mode):
        mode = (mode or "").strip().lower()
        if mode not in {"plan", "safe", "agent"}:
            raise ValueError("Mode must be one of: plan, safe, agent")

        self.execution_mode = mode
        if mode == "plan":
            self.file_edits_enabled = False
            self.command_execution_enabled = False
        elif mode == "safe":
            self.file_edits_enabled = True
            self.command_execution_enabled = False
        else:
            self.file_edits_enabled = True
            self.command_execution_enabled = True

        self.executor.allow_file_edits = self.file_edits_enabled
        self.executor.allow_run_command = self.command_execution_enabled

    def get_permissions_snapshot(self):
        return {
            "mode": self.execution_mode,
            "file_edits_enabled": self.file_edits_enabled,
            "command_execution_enabled": self.command_execution_enabled,
            "workspace_root": str(self.workspace_root),
        }

    def _request_completion(self, model_name):
        payload = {
            "model": model_name,
            "messages": [{"role": "system", "content": self.system_prompt}, *self.messages],
            "reasoning": {"enabled": True},
        }

        response = requests.post(
            url=self.base_url,
            headers=self.headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        response_json = response.json()
        if "choices" not in response_json or not response_json["choices"]:
            raise ValueError(f"No choices returned by OpenRouter: {response_json}")

        return response_json["choices"][0]["message"]

    def _run_tool_loop(self, model_name, tool_events):
        self.last_model_used = model_name
        for _ in range(MAX_TOOL_ROUNDS + 1):
            message_data = self._request_completion(model_name)
            assistant_content = message_data.get("content", "")
            reasoning_details = message_data.get("reasoning_details") or message_data.get("reasoning")

            self.messages.append({"role": "assistant", "content": assistant_content})

            tool_calls, parse_error = self._extract_tool_calls(assistant_content)
            if parse_error:
                tool_result = {
                    "ok": False,
                    "action": "tool_call_error",
                    "error": parse_error,
                }
                tool_events.append({"request": None, "result": tool_result})
                self.messages.append({"role": "user", "content": self._tool_result_message(tool_result)})
                continue

            if not tool_calls:
                return assistant_content, reasoning_details, tool_events

            for tool_call in tool_calls:
                tool_result = self._execute_tool_call(tool_call)
                tool_events.append({"request": tool_call, "result": tool_result})
                self.messages.append({"role": "user", "content": self._tool_result_message(tool_result)})

        return "Error: Tool loop limit reached before the model returned a final answer.", None, tool_events

    def _extract_tool_calls(self, content):
        if not content:
            return [], None

        json_matches = list(TOOL_CALL_RE.finditer(content))
        if json_matches:
            tool_calls = []
            for match in json_matches:
                raw_json = match.group(1)
                try:
                    parsed = json.loads(raw_json)
                except json.JSONDecodeError as exc:
                    return [], f"Invalid tool JSON: {exc.msg}"

                if not isinstance(parsed, dict):
                    return [], "Tool call payload must be a JSON object."

                tool_calls.append(parsed)
            return tool_calls, None

        # Fallback parser for model variants that emit:
        # <tool_call><function=...><parameter=...>...</parameter></tool_call>
        block_matches = list(TOOL_CALL_BLOCK_RE.finditer(content))
        if not block_matches:
            return [], None

        tool_calls = []
        for block_match in block_matches:
            block = block_match.group(1)
            function_match = LEGACY_FUNCTION_RE.search(block)
            if not function_match:
                return [], "Invalid tool call block: missing function name."

            action = function_match.group(1).strip()
            tool_call = {"action": action}

            for param_match in LEGACY_PARAM_RE.finditer(block):
                key = param_match.group(1).strip()
                value = param_match.group(2).strip()
                tool_call[key] = self._coerce_tool_value(value)

            tool_calls.append(tool_call)

        return tool_calls, None

    def _coerce_tool_value(self, value):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

        if re.fullmatch(r"-?\d+", value):
            try:
                return int(value)
            except Exception:
                return value

        if (value.startswith("{") and value.endswith("}")) or (value.startswith("[") and value.endswith("]")):
            try:
                return json.loads(value)
            except Exception:
                return value

        return value

    def _execute_tool_call(self, tool_call):
        try:
            return self.executor.execute(tool_call)
        except Exception as exc:
            return {
                "ok": False,
                "action": tool_call.get("action", "unknown"),
                "path": str(tool_call.get("path", "")),
                "error": str(exc),
            }

    def _tool_result_message(self, tool_result):
        return f"TOOL RESULT\n{self.executor.format_result(tool_result)}"

    def _extract_http_error_text(self, exc):
        if exc.response is not None:
            return (exc.response.text or "").strip()
        return str(exc).strip()

    def _is_policy_blocked_error(self, response_text):
        return "No endpoints available matching your guardrail restrictions and data policy" in (
            (response_text or "").strip()
        )

    def _pick_fallback_model(self, blocked_model):
        candidates = [DEFAULT_MODEL, "nvidia/nemotron-3-super-120b-a12b:free", "stepfun/step-3.5-flash:free"]
        for candidate in candidates:
            if candidate and candidate != blocked_model:
                return candidate
        return None

    def _friendly_openrouter_error(self, response_text):
        raw_text = (response_text or "").strip()
        if "No endpoints available matching your guardrail restrictions and data policy" in raw_text:
            return (
                "Error: This model is blocked by your OpenRouter privacy/guardrail settings. "
                "Open https://openrouter.ai/settings/privacy and relax data policy for this model, "
                "or switch model using /model."
            )

        try:
            parsed = json.loads(raw_text)
            message = ((parsed.get("error") or {}).get("message") or "").strip()
        except Exception:
            return None

        if "No endpoints available matching your guardrail restrictions and data policy" in message:
            return (
                "Error: This model is blocked by your OpenRouter privacy/guardrail settings. "
                "Open https://openrouter.ai/settings/privacy and relax data policy for this model, "
                "or switch model using /model."
            )

        return None
