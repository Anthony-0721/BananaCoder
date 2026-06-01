"""Rich display helpers for streaming output."""
from __future__ import annotations

from rich.console import Console
from rich.text import Text
from rich.panel import Panel

console = Console()


class Display:
    def __init__(self):
        self._tool_count = 0

    async def on_token(self, token: str):
        console.print(token, end="", highlight=False)

    async def on_tool(self, name: str, args: dict):
        self._tool_count += 1
        summary = self._tool_summary(name, args)
        console.print(Text(f"\n  [{name}] {summary}", style="dim cyan"))

    def _tool_summary(self, name: str, args: dict) -> str:
        key_map = {
            "bash": "command", "read_file": "file_path", "write_file": "file_path",
            "edit": "file_path", "grep": "pattern", "glob": "pattern",
            "web_search": "query", "web_fetch": "url",
            "agent": "subagent_type", "load_skill": "skill_name",
        }
        key = key_map.get(name, "")
        if key and key in args:
            return str(args[key])[:80]
        if args:
            first_val = list(args.values())[0] if args else ""
            return str(first_val)[:80]
        return ""

    def print_welcome(self, model: str, session_id: str, summary: str = ""):
        content = (
            f"[bold]BananaCoder[/] v0.1.0\n"
            f"Session: {session_id}  Model: {model}\n"
            f"Type /help for commands, exit to quit"
        )
        if summary:
            content += f"\n[dim]{summary}[/dim]"
        console.print(Panel(content, title="Welcome", border_style="yellow"))

    def print_goodbye(self):
        console.print(Text("\nGoodbye!", style="bold yellow"))
