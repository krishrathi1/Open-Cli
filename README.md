# rathi cli

`rathi cli` is an agentic terminal coding assistant powered by OpenRouter models.

It can:
- chat in an interactive CLI,
- inspect and edit local files,
- create and manage folders/files,
- run shell commands,
- search the web for references,
- execute multi-step tool workflows.

## Features

- Interactive terminal UI with command completion and history.
- Multiple execution modes:
  - `plan`: no file edits, no shell commands
  - `safe`: file edits enabled, shell commands disabled
  - `agent`: file edits + shell commands enabled
- Tooling for:
  - file read/write/update
  - directory listing/search
  - directory/file create/move/copy/delete
  - web search and URL fetch
  - shell command execution
- Automatic fallback from blocked models when OpenRouter privacy policy blocks endpoints.

## Requirements

- Python 3.10+
- Internet access for OpenRouter and web tools
- OpenRouter API key

Install Python dependencies:

```bash
pip install requests rich prompt_toolkit
```

## Setup

Create `.env` in project root:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
```

## Run

```bash
python main.py
```

## Commands

You can use commands in any of these forms:
- `/help`
- `\help`
- `help`

Main commands:
- `help` - show help
- `model` - open model selector
- `clear` - clear conversation history
- `files [path]` - list files/directories
- `tools` - list supported tool actions
- `web <query>` - web search for references
- `mode plan|safe|agent` - switch execution mode
- `permissions` - show current permission snapshot
- `pwd` - print workspace root
- `cmd on|off` - enable/disable shell command execution
- `run <shell command>` - run shell command in workspace
- `exit` - quit CLI

Model selector keys:
- `Enter` or `Ctrl+J`: select model
- `Esc`: cancel

## Execution Modes

- `plan`
  - file edits: disabled
  - shell commands: disabled
- `safe`
  - file edits: enabled
  - shell commands: disabled
- `agent`
  - file edits: enabled
  - shell commands: enabled

## Supported Agent Tool Actions

- `list_dir`
- `read_file`
- `search_text`
- `write_file`
- `update_file`
- `make_dir`
- `move_path`
- `copy_path`
- `delete_path`
- `search_web`
- `fetch_url`
- `run_command`

## Project Structure

- `main.py` - CLI loop and command handling
- `client.py` - OpenRouter client + tool-call loop + model fallback
- `local_tools.py` - local/web/shell tool implementations
- `ui.py` - terminal rendering and interaction UI
- `config.py` - model list, prompt template, runtime config
- `test_run.py` / `test_run_file.py` - simple smoke scripts

## Troubleshooting

### Model blocked by OpenRouter policy

If you see an error like:
`No endpoints available matching your guardrail restrictions and data policy`

Then either:
- adjust your privacy settings: https://openrouter.ai/settings/privacy
- or switch to another model using `model`

### Commands not executing

Check mode and permissions:
- run `permissions`
- if needed: `mode agent` or `cmd on`

### No web results

- verify internet access
- try a simpler query with `web <query>`

## Notes

- Tool activity panels are hidden by default (`SHOW_TOOL_ACTIVITY = False` in `config.py`).
- Workspace root is the folder where you run `main.py`.
"# Open-Cli" 
