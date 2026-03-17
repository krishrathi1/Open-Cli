import os
from pathlib import Path


def _load_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
REQUEST_TIMEOUT_SECONDS = 60
MAX_TOOL_ROUNDS = 12
COMMAND_TIMEOUT_SECONDS = 30
MAX_COMMAND_OUTPUT_CHARS = 4000
WEB_TIMEOUT_SECONDS = 12
MAX_WEB_RESULTS = 5
MAX_WEB_CONTENT_CHARS = 5000

MODELS = {
    "stepfun": "stepfun/step-3.5-flash:free",
    "nvidia": "nvidia/nemotron-3-super-120b-a12b:free"
}

# Optional: friendly names for selection menu
MODEL_NAMES = {
    "stepfun/step-3.5-flash:free": "StepFun 3.5 Flash (Free)",
    "nvidia/nemotron-3-super-120b-a12b:free": "Nvidia Nemotron 3 Super 120B (Free)"
}

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
CLI_NAME = "rathi cli"
SHOW_TOOL_ACTIVITY = False
DEFAULT_EXECUTION_MODE = "agent"

SYSTEM_PROMPT_TEMPLATE = """You are rathi cli, an agentic coding assistant running in a terminal on Windows.

Workspace root: {workspace_root}

You can request local file tools when needed. To call a tool, reply with exactly one JSON object wrapped in <tool_call> and </tool_call>, with no extra text before or after it.

Supported tool calls:
<tool_call>{{"action":"read_file","path":"relative-or-absolute-path"}}</tool_call>
<tool_call>{{"action":"write_file","path":"relative-or-absolute-path","content":"full file contents to write"}}</tool_call>
<tool_call>{{"action":"update_file","path":"relative-or-absolute-path","find":"exact old text","replace":"new text","replace_all":false}}</tool_call>
<tool_call>{{"action":"list_dir","path":"relative-or-absolute-path"}}</tool_call>
<tool_call>{{"action":"search_text","path":"relative-or-absolute-path","query":"text to search","case_sensitive":false}}</tool_call>
<tool_call>{{"action":"make_dir","path":"relative-or-absolute-path"}}</tool_call>
<tool_call>{{"action":"move_path","src":"relative-or-absolute-path","dest":"relative-or-absolute-path"}}</tool_call>
<tool_call>{{"action":"copy_path","src":"relative-or-absolute-path","dest":"relative-or-absolute-path"}}</tool_call>
<tool_call>{{"action":"delete_path","path":"relative-or-absolute-path","recursive":false}}</tool_call>
<tool_call>{{"action":"search_web","query":"modern portfolio ui inspiration"}}</tool_call>
<tool_call>{{"action":"fetch_url","url":"https://example.com/design-reference"}}</tool_call>
<tool_call>{{"action":"run_command","command":"python -m pytest -q","path":"relative-or-absolute-path"}}</tool_call>

Rules:
- Use tools whenever the user asks to save, create, update, inspect, read, debug, or solve code from files.
- For direct action requests (e.g., "create folder", "write this file"), execute the action tool call, not only inspection.
- Follow this workflow for coding tasks: inspect first (list/search/read), then edit (update_file/write_file), then verify (run_command when available).
- Prefer update_file for targeted edits; use write_file when creating files or replacing entire file contents.
- When building apps/websites, create directories/files as needed and run verification commands.
- For design tasks, use search_web/fetch_url to gather inspiration before implementing.
- For write_file, send the full final contents of the file, not a diff.
- Tool results come back as user messages that start with TOOL RESULT.
- Use run_command only when needed to verify or inspect behavior.
- You may return multiple tool_call blocks in a single response if several sequential actions are required.
- Do not claim a file was saved, updated, or read unless you actually used a tool and received a successful TOOL RESULT.
- If a tool returns a permissions/mode error, adapt by using non-mutating tools or ask the user to switch mode.
- When you are done, answer normally in plain Markdown with no tool_call block.
- Keep answers practical and concise.
"""
