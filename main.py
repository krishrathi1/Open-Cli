import sys
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory

from client import OpenRouterClient
from config import DEFAULT_MODEL
from ui import (
    console,
    print_assistant_response,
    print_banner,
    print_error,
    print_help,
    print_info,
    print_status,
    print_task_summary,
    print_tool_event,
    print_turn_header,
    print_user_message,
    select_model_dialog,
)


def main():
    client = OpenRouterClient()
    current_model = DEFAULT_MODEL
    command_completer = WordCompleter(
        [
            r"\help",
            r"\model",
            r"\clear",
            r"\files",
            r"\pwd",
            r"\exit",
            r"/help",
            r"/model",
            r"/clear",
            r"/files",
            r"/tools",
            r"/web",
            r"/mode",
            r"/permissions",
            r"/pwd",
            r"/cmd",
            r"/run",
            r"/exit",
            "help",
            "model",
            "clear",
            "files",
            "tools",
            "web",
            "mode",
            "permissions",
            "pwd",
            "cmd",
            "run",
            "exit",
        ],
        ignore_case=True,
    )
    session = PromptSession(
        history=InMemoryHistory(),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        complete_while_typing=True,
        bottom_toolbar=lambda: HTML(
            "<style fg='#7a7a7a'>Enter to send | Tab to complete commands | /mode plan|safe|agent</style>"
        ),
    )
    turn_id = 1

    print_banner()
    print_status(
        current_model,
        client.workspace_root,
        client.command_execution_enabled,
        client.execution_mode,
        client.file_edits_enabled,
    )

    while True:
        try:
            user_input = session.prompt(
                HTML("\n<style fg='#7ad7f0'>rathi</style><style fg='#7a7a7a'> ></style> ")
            ).strip()
            if not user_input:
                continue

            normalized_input = user_input.lower()
            if normalized_input.startswith("/"):
                normalized_input = "\\" + normalized_input[1:]
            elif not normalized_input.startswith("\\"):
                first_token = normalized_input.split(maxsplit=1)[0]
                command_aliases = {
                    "help",
                    "model",
                    "clear",
                    "files",
                    "tools",
                    "web",
                    "mode",
                    "permissions",
                    "pwd",
                    "cmd",
                    "run",
                    "exit",
                }
                if first_token in command_aliases:
                    normalized_input = "\\" + normalized_input

            command_token = normalized_input.split(maxsplit=1)[0]

            if command_token == r"\exit":
                console.print("[yellow]Exiting OpenRouter CLI. Goodbye![/yellow]")
                sys.exit(0)

            if command_token == r"\help":
                print_help()
                continue

            if command_token == r"\clear":
                client.clear_history()
                print_info("Conversation history cleared.")
                continue

            if command_token == r"\pwd":
                print_info(client.workspace_root)
                continue

            if command_token == r"\tools":
                print_info("Supported tools: " + ", ".join(client.supported_actions))
                continue

            if command_token == r"\mode":
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print_info(f"Current mode: {client.execution_mode}. Use /mode plan|safe|agent.")
                    continue
                try:
                    client.set_execution_mode(parts[1].strip().lower())
                    print_status(
                        current_model,
                        client.workspace_root,
                        client.command_execution_enabled,
                        client.execution_mode,
                        client.file_edits_enabled,
                    )
                except Exception as exc:
                    print_error(exc)
                continue

            if command_token == r"\permissions":
                snapshot = client.get_permissions_snapshot()
                print_info(
                    "Permissions:\n"
                    f"- mode: {snapshot['mode']}\n"
                    f"- file_edits_enabled: {snapshot['file_edits_enabled']}\n"
                    f"- command_execution_enabled: {snapshot['command_execution_enabled']}\n"
                    f"- workspace_root: {snapshot['workspace_root']}"
                )
                continue

            if command_token == r"\web":
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print_error("Usage: /web <search query>")
                    continue

                try:
                    result = client.search_web(parts[1])
                    results = result.get("results", [])
                    if not results:
                        print_info("No web results found.")
                    else:
                        formatted = "\n".join(f"- {item['title']}\n  {item['url']}" for item in results)
                        print_info(f"Top web results for '{parts[1]}':\n{formatted}")
                except Exception as exc:
                    print_error(exc)
                continue

            if command_token == r"\cmd":
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    mode = "enabled" if client.command_execution_enabled else "disabled"
                    print_info(f"Command execution is currently {mode}. Use /cmd on or /cmd off.")
                    continue

                setting = parts[1].strip().lower()
                if setting not in {"on", "off"}:
                    print_error("Invalid command mode. Use /cmd on or /cmd off.")
                    continue

                client.set_command_execution_enabled(setting == "on")
                print_status(
                    current_model,
                    client.workspace_root,
                    client.command_execution_enabled,
                    client.execution_mode,
                    client.file_edits_enabled,
                )
                continue

            if command_token == r"\run":
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print_error("Usage: /run <shell command>")
                    continue

                if not client.command_execution_enabled:
                    print_error("Command execution is disabled. Enable it first with /cmd on.")
                    continue

                run_result = client.run_command(parts[1], ".")
                print_tool_event(
                    {
                        "request": {"action": "run_command", "command": parts[1], "path": "."},
                        "result": run_result,
                    }
                )
                continue

            if command_token == r"\files":
                path = "."
                if len(user_input.split(maxsplit=1)) == 2:
                    path = user_input.split(maxsplit=1)[1].strip()

                try:
                    result = client.list_directory(path)
                    print_tool_event({"request": {"action": "list_dir", "path": path}, "result": result})
                except Exception as exc:
                    print_error(exc)
                continue

            if command_token == r"\model":
                new_model = select_model_dialog(current_model)
                if new_model:
                    current_model = new_model
                    print_status(
                        current_model,
                        client.workspace_root,
                        client.command_execution_enabled,
                        client.execution_mode,
                        client.file_edits_enabled,
                    )
                else:
                    print_info("Model selection cancelled.")
                continue

            print_turn_header(turn_id, current_model)
            print_user_message(user_input)
            started_at = time.perf_counter()
            with console.status("[bold #7AD7F0]Agent running: analyzing + planning edits...[/bold #7AD7F0]", spinner="dots"):
                content, reasoning, tool_events = client.send_message(user_input, current_model)
            elapsed_seconds = time.perf_counter() - started_at

            if client.last_model_fallback_from == current_model and client.last_model_used != current_model:
                current_model = client.last_model_used
                print_info(f"Auto-switched model to {current_model} due to OpenRouter policy restrictions.")
                print_status(
                    current_model,
                    client.workspace_root,
                    client.command_execution_enabled,
                    client.execution_mode,
                    client.file_edits_enabled,
                )

            for event in tool_events:
                print_tool_event(event)

            print_task_summary(tool_events, elapsed_seconds)

            if isinstance(content, str) and content.startswith("Error:"):
                print_error(content)
            else:
                print_assistant_response(content, reasoning)
            turn_id += 1

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting OpenRouter CLI. Goodbye![/yellow]")
            sys.exit(0)
        except Exception as exc:
            print_error(f"Unexpected error: {exc}")


if __name__ == "__main__":
    main()
