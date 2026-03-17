import re
import time

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Box, Frame, Label, RadioList

from config import CLI_NAME, MODEL_NAMES, SHOW_TOOL_ACTIVITY

console = Console()
CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)

MODEL_DIALOG_STYLE = Style.from_dict(
    {
        "dialog": "bg:#11131A",
        "dialog frame.label": "bg:#11131A #7AD7F0 bold",
        "dialog.body": "bg:#0D0F15 #E6E6E6",
        "dialog shadow": "bg:#05060A",
        "radio": "bg:#0D0F15 #E6E6E6",
        "radio-selected": "bg:#0D0F15 #7AD7F0 bold",
        "button": "bg:#1A1F2B #DCDCDC",
        "button.focused": "bg:#7AD7F0 #0B0D12 bold",
    }
)


def print_banner():
    top = Text.from_markup("[#FF6B6B]o[/] [#F7C948]o[/] [#2ECC71]o[/]  [dim]terminal session[/dim]")
    title = Text(CLI_NAME, style="bold #7AD7F0")
    subtitle = Text("coding assistant with local file tools", style="dim")

    cmds = Text.from_markup(
        "[bold #7AD7F0]/help[/]  [bold #7AD7F0]/model[/]  [bold #7AD7F0]/clear[/]  "
        "[bold #7AD7F0]/files[/]  [bold #7AD7F0]/tools[/]  [bold #7AD7F0]/web[/]  [bold #7AD7F0]/cmd[/]  [bold #7AD7F0]/run[/]  "
        "[bold #7AD7F0]/pwd[/]  [bold #7AD7F0]/exit[/]"
    )
    body = Group(top, Text(""), title, subtitle, Text(""), cmds)
    console.print(Panel(body, border_style="#155A6C", expand=False, padding=(1, 2)))


def print_status(current_model, workspace_root, command_execution_enabled=False, mode="agent", file_edits_enabled=True):
    model_name = MODEL_NAMES.get(current_model, current_model)
    status = Table.grid(padding=(0, 1))
    status.add_row(f"[bold #7AD7F0]workspace[/bold #7AD7F0] {_ellipsize(workspace_root, 96)}")
    status.add_row(f"[bold #FF8BD7]model[/bold #FF8BD7] {_ellipsize(model_name, 96)}")
    status.add_row(f"[bold #E6C229]mode[/bold #E6C229] {mode}")
    edit_mode = "enabled" if file_edits_enabled else "disabled"
    edit_color = "#3CCB7F" if file_edits_enabled else "#E27D60"
    status.add_row(f"[bold {edit_color}]file edits[/bold {edit_color}] {edit_mode}")
    cmd_mode = "enabled" if command_execution_enabled else "disabled"
    cmd_color = "#3CCB7F" if command_execution_enabled else "#E27D60"
    status.add_row(f"[bold {cmd_color}]command mode[/bold {cmd_color}] {cmd_mode} (/cmd on or /cmd off)")
    console.print(Panel(status, title=CLI_NAME, border_style="#2B5D80", expand=False))
    console.print(
        "[dim]Tip: use Tab for slash-command completion and Up arrow for prompt history.[/dim]"
    )


def print_help():
    help_table = Table(show_header=False, box=None, padding=(0, 2))
    help_table.add_row(r"\help or /help", "Show commands and capabilities")
    help_table.add_row(r"\model or /model", "Choose a different OpenRouter model")
    help_table.add_row(r"\clear or /clear", "Clear conversation history")
    help_table.add_row(r"\files [path] or /files [path]", "List files from the workspace or a provided path")
    help_table.add_row(r"/tools", "Show supported agent tool actions")
    help_table.add_row(r"/web <query>", "Search the internet for references (UI/design/research)")
    help_table.add_row(r"/mode plan|safe|agent", "Set execution mode (plan: no edits/commands, safe: edits only, agent: full)")
    help_table.add_row(r"/permissions", "Show current permission snapshot")
    help_table.add_row(r"\pwd or /pwd", "Show the active workspace folder")
    help_table.add_row(r"/cmd on|off", "Enable or disable model-triggered command execution")
    help_table.add_row(r"/run <shell command>", "Run a shell command in workspace (requires /cmd on)")
    help_table.add_row(r"\exit or /exit", "Quit the CLI")
    help_table.add_row("Agent flow", "Inspect -> edit -> verify with visible tool activity")
    console.print(Panel(help_table, title=f"{CLI_NAME} Help", border_style="#4FA6C0", expand=False))


def print_assistant_response(content, reasoning=None):
    if _is_verbose_intro(content):
        console.print("[dim]ready[/dim]")
        return

    if _has_code_block(content):
        _animate_code_response(content)
        return

    renderable = Markdown(content) if _looks_like_markdown(content) else Text(content)
    console.print(Panel(renderable, title="Assistant", border_style="#3C8A5E"))


def print_tool_event(event):
    if not SHOW_TOOL_ACTIVITY:
        return

    request = event.get("request") or {}
    result = event.get("result") or {}
    action = result.get("action") or request.get("action") or "tool"
    status = "ok" if result.get("ok") else "failed"
    path = result.get("path") or request.get("path") or "-"

    summary_lines = [f"[bold]Action:[/bold] {action}", f"[bold]Path:[/bold] {path}", f"[bold]Status:[/bold] {status}"]

    if action == "write_file" and result.get("ok"):
        _animate_write_operation(path, result.get("bytes_written", 0))
        summary_lines.append(f"[bold]Bytes written:[/bold] {result.get('bytes_written', 0)}")
    elif action == "update_file" and result.get("ok"):
        _animate_write_operation(path, result.get("bytes_written", 0))
        summary_lines.append(f"[bold]Replacements:[/bold] {result.get('replacements', 0)}")
        summary_lines.append(f"[bold]Bytes written:[/bold] {result.get('bytes_written', 0)}")
    elif action == "list_dir" and result.get("ok"):
        entries = result.get("entries", [])
        preview = ", ".join(entry["name"] for entry in entries[:8]) or "(empty)"
        summary_lines.append(f"[bold]Entries:[/bold] {len(entries)}")
        summary_lines.append(f"[bold]Preview:[/bold] {preview}")
    elif action == "read_file" and result.get("ok"):
        content = result.get("content", "")
        summary_lines.append(f"[bold]Chars read:[/bold] {len(content)}")
    elif action == "search_text" and result.get("ok"):
        matches = result.get("matches", [])
        summary_lines.append(f"[bold]Matches:[/bold] {len(matches)}")
        if matches:
            first = matches[0]
            summary_lines.append(
                f"[bold]First hit:[/bold] {first.get('path')}:{first.get('line')} {first.get('text', '')[:80]}"
            )
    elif action == "search_web" and result.get("ok"):
        results = result.get("results", [])
        summary_lines.append(f"[bold]Results:[/bold] {len(results)}")
        if results:
            first = results[0]
            summary_lines.append(f"[bold]Top:[/bold] {first.get('title', '')[:80]}")
            summary_lines.append(f"[bold]URL:[/bold] {first.get('url', '')[:80]}")
    elif action == "fetch_url" and result.get("ok"):
        summary_lines.append(f"[bold]URL:[/bold] {result.get('url', '-')}")
        summary_lines.append(f"[bold]Status code:[/bold] {result.get('status_code', '-')}")
        summary_lines.append(f"[bold]Type:[/bold] {result.get('content_type', '-')}")
    elif action == "make_dir" and result.get("ok"):
        summary_lines.append("[bold]Created:[/bold] directory")
    elif action == "move_path" and result.get("ok"):
        summary_lines.append(f"[bold]From:[/bold] {result.get('src', '-')}")
        summary_lines.append(f"[bold]To:[/bold] {result.get('dest', '-')}")
    elif action == "copy_path" and result.get("ok"):
        summary_lines.append(f"[bold]From:[/bold] {result.get('src', '-')}")
        summary_lines.append(f"[bold]To:[/bold] {result.get('dest', '-')}")
    elif action == "delete_path" and result.get("ok"):
        summary_lines.append(f"[bold]Recursive:[/bold] {result.get('recursive', False)}")
    elif action == "run_command":
        summary_lines.append(f"[bold]Command:[/bold] {result.get('command', request.get('command', '-'))}")
        if "exit_code" in result:
            summary_lines.append(f"[bold]Exit code:[/bold] {result.get('exit_code')}")
        if "elapsed_ms" in result:
            summary_lines.append(f"[bold]Duration:[/bold] {result.get('elapsed_ms')} ms")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        if stdout:
            summary_lines.append(f"[bold]stdout:[/bold] {stdout[:140]}")
        if stderr:
            summary_lines.append(f"[bold]stderr:[/bold] {stderr[:140]}")
    elif result.get("error"):
        summary_lines.append(f"[bold]Error:[/bold] {result['error']}")

    console.print(Panel("\n".join(summary_lines), title="Tool Activity", border_style="#8F4FC0", expand=False))


def print_error(message):
    console.print(Panel(str(message), title="Error", border_style="#C05656", expand=False))


def print_info(message):
    console.print(Panel(str(message), border_style="#2B5D80", expand=False))


def print_turn_header(turn_id, current_model):
    model_name = MODEL_NAMES.get(current_model, current_model)
    label = f"[bold #7AD7F0]Task {turn_id}[/bold #7AD7F0] [dim]{_ellipsize(model_name, 44)}[/dim]"
    console.print(Rule(label, style="#2B5D80"))


def print_user_message(message):
    console.print(Panel(Text(message), title="You", border_style="#4F7AC0"))


def print_task_summary(tool_events, elapsed_seconds):
    total = len(tool_events)
    writes = 0
    structure_ops = 0
    research_ops = 0
    commands = 0
    for event in tool_events:
        action = (event.get("result") or {}).get("action", "")
        if action in {"write_file", "update_file"}:
            writes += 1
        if action in {"make_dir", "move_path", "copy_path", "delete_path"}:
            structure_ops += 1
        if action in {"search_web", "fetch_url"}:
            research_ops += 1
        if action == "run_command":
            commands += 1

    summary = (
        f"[bold #7AD7F0]Task Summary[/bold #7AD7F0] "
        f"| tools: {total} | edits: {writes} | structure: {structure_ops} | research: {research_ops} | commands: {commands} | elapsed: {elapsed_seconds:.2f}s"
    )
    console.print(summary)


def print_shell_footer(workspace_root, current_model):
    model_name = MODEL_NAMES.get(current_model, current_model)
    footer = (
        f"[#6CE2F7]{_ellipsize(workspace_root, 52)}[/]  "
        f"[#FF8BD7]{_ellipsize(model_name, 34)}[/]  "
        "[dim]/help for commands[/dim]"
    )
    console.print(footer)


def select_model_dialog(current_model):
    values = []
    for model_id, name in MODEL_NAMES.items():
        marker = "[current]" if model_id == current_model else "         "
        label = f"{marker} {name}"
        values.append((model_id, label))

    radio_list = RadioList(values=values)
    radio_list.current_value = current_model

    kb = KeyBindings()

    def _selected_model():
        selected_value = radio_list.values[radio_list._selected_index][0]
        return selected_value

    @kb.add("c-j")
    def _accept_ctrl_j(event):
        event.app.exit(result=_selected_model())

    @kb.add("enter")
    def _accept_enter(event):
        event.app.exit(result=_selected_model())

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=None)

    root = Box(
        body=Frame(
            body=HSplit(
                [
                    Label(text="Choose the model for this session."),
                    Label(text="Enter/Ctrl+J = use model, Esc = cancel"),
                    radio_list,
                ]
            ),
            title="Model Selector",
        ),
        padding=1,
    )

    app = Application(
        layout=Layout(root, focused_element=radio_list),
        key_bindings=kb,
        style=MODEL_DIALOG_STYLE,
        full_screen=True,
        mouse_support=True,
    )
    return app.run()


def _looks_like_markdown(content):
    markers = ("```", "# ", "## ", "- ", "* ", "1. ")
    return any(marker in content for marker in markers)


def _has_code_block(content):
    return bool(CODE_BLOCK_RE.search(content))


def _is_verbose_intro(content):
    text = (content or "").lower()
    signals = [
        "i can help with:",
        "workspace root",
        "how can i assist you today",
        "agentic coding assistant",
    ]
    return all(signal in text for signal in signals[:2]) and any(signal in text for signal in signals[2:])


def _animate_write_operation(path, bytes_written):
    total = max(int(bytes_written or 1), 1)
    step = max(total // 12, 1)

    progress = Progress(
        SpinnerColumn(style="#7AD7F0"),
        TextColumn("[bold]writing[/bold] {task.description}"),
        BarColumn(bar_width=26),
        TaskProgressColumn(),
        transient=True,
    )
    with progress:
        task_id = progress.add_task(str(path), total=total)
        written = 0
        while written < total:
            increment = min(step, total - written)
            written += increment
            progress.update(task_id, advance=increment)
            time.sleep(0.02)


def _ellipsize(value, max_len):
    text = str(value)
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


def _animate_code_response(content):
    with console.status("[bold #7AD7F0]Rendering code...[/bold #7AD7F0]", spinner="dots"):
        time.sleep(0.25)

    parts = []
    last_idx = 0
    for match in CODE_BLOCK_RE.finditer(content):
        start, end = match.span()
        plain_text = content[last_idx:start].strip()
        if plain_text:
            parts.append(("text", plain_text))
        language = match.group(1).strip() or "text"
        code = match.group(2)
        parts.append(("code", (language, code)))
        last_idx = end

    tail = content[last_idx:].strip()
    if tail:
        parts.append(("text", tail))

    for part_type, payload in parts:
        if part_type == "text":
            console.print(Panel(Markdown(payload), title="Assistant", border_style="#3C8A5E"))
            continue

        language, code = payload
        _animate_code_block(language, code)


def _animate_code_block(language, code):
    lines = code.splitlines()
    max_animated_lines = 80
    should_animate = len(lines) <= max_animated_lines

    if not should_animate:
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"Code ({language})", border_style="#3C8A5E"))
        return

    rendered_lines = []
    syntax = Syntax("", language, theme="monokai", line_numbers=True)
    panel = Panel(syntax, title=f"Code ({language})", border_style="#3C8A5E")

    with Live(panel, refresh_per_second=25, console=console) as live:
        for line in lines:
            rendered_lines.append(line)
            syntax = Syntax("\n".join(rendered_lines), language, theme="monokai", line_numbers=True)
            panel = Panel(syntax, title=f"Code ({language})", border_style="#3C8A5E")
            live.update(panel)
            time.sleep(0.02)
