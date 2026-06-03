"""Rich display helpers for streaming output."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

console = Console()


class Display:
    def __init__(self):
        self._tool_count = 0
        self._needs_sep = False
        self._thinking = False
        self._spinner = None

    async def on_llm_start(self):
        self._thinking = True
        self._spinner = console.status("  Thinking...", spinner="dots")
        self._spinner.start()

    async def _stop_thinking(self):
        if self._thinking:
            self._thinking = False
            if self._spinner:
                self._spinner.stop()
                self._spinner = None

    async def on_token(self, token: str):
        await self._stop_thinking()
        console.print(token, end="", highlight=False, markup=False)
        self._needs_sep = True

    async def on_tool(self, name: str, args: dict):
        await self._stop_thinking()
        self._tool_count += 1
        summary = self._tool_summary(name, args)
        sep = "\n" if self._needs_sep else ""
        self._needs_sep = False
        console.print(f"{sep}  [dim cyan]\\[{name}][/] {summary}")

    async def on_tool_result(self, name: str, result: str):
        status = self._format_status(name, result)
        console.print(f"  {status}")

    async def on_turn_complete(self, prompt_tokens: int, completion_tokens: int,
                                elapsed: float, info: str = "", window: int = 0, **kwargs):
        if info and not prompt_tokens:
            console.print(f"  [dim]{info}[/dim]")
        elif prompt_tokens:
            total = prompt_tokens + completion_tokens
            pct = f" ({total * 100 // window}% of {window // 1000}K)" if window else ""
            console.print(f"\n  [dim]Prompt: {prompt_tokens:,} | Completion: {completion_tokens:,} | "
                         f"Total: {total:,}{pct} | {elapsed:.1f}s[/dim]")

    async def on_reasoning(self, text: str):
        pass  # Suppressed — "Thinking..." spinner already shows model is working

    def _format_status(self, name: str, result: str) -> str:
        first = result[:50]
        if first.startswith("Error") or "FAILED" in first or "BLOCKED" in first:
            return "[bold red]FAILED[/]"

        if name == "grep":
            import re
            m = re.search(r"\((\d+) matches in (\d+) files\)", result)
            if m:
                return f"[bold green]OK[/] [dim]({m.group(1)} matches in {m.group(2)} files)[/dim]"
            return "[bold red]FAILED[/]" if "No matches" in result else "[bold green]OK[/]"

        if name == "glob":
            import re
            m = re.search(r"\((\d+) matches\)", result)
            if m:
                return f"[bold green]OK[/] [dim]({m.group(1)} files)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "bash":
            if "Exit code: 0" in result[:100]:
                lines = result.strip().split("\n")
                out_lines = sum(1 for l in lines if l.strip() and not l.startswith("bash:") and not l.startswith("[OK]"))
                return f"[bold green]OK[/] [dim](exit 0, {out_lines} lines)[/dim]"
            m = __import__("re").search(r"Exit code: (\d+)", result)
            ec = m.group(1) if m else "?"
            return f"[bold red]FAILED[/] [dim](exit {ec})[/dim]"

        if name == "read_file":
            import re
            m = re.search(r"\((\d+) lines\)", result)
            if m:
                return f"[bold green]OK[/] [dim]({m.group(1)} lines)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "write_file":
            import re
            m = re.search(r"\((\d+) chars\)", result)
            if m:
                return f"[bold green]OK[/] [dim]({m.group(1)} chars)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "edit":
            import re
            if "[WARN]" in result:
                return "[bold yellow]WARN[/]"
            m = re.search(r"-(\d+)\+(\d+)", result)
            if m:
                return f"[bold green]OK[/] [dim](-{m.group(1)}+{m.group(2)} lines)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "web_search":
            import re
            m = re.search(r"\((\d+) results\)", result)
            if m:
                return f"[bold green]OK[/] [dim]({m.group(1)} results)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "web_fetch":
            import re
            m = re.search(r"\((\d+), (\d+) chars\)", result)
            if m:
                return f"[bold green]OK[/] [dim](HTTP {m.group(1)}, {m.group(2)} chars)[/dim]"
            return "[bold red]FAILED[/]"

        if name == "agent":
            lines = result.strip().split("\n")
            preview = lines[-1][:50] if len(lines) > 1 else ""
            return f"[bold green]OK[/] [dim]{preview}[/dim]"

        if len(result) > 500:
            return f"[bold green]OK[/] [dim]({len(result)} chars)[/dim]"
        return "[bold green]OK[/]"

    def _tool_summary(self, name: str, args: dict) -> str:
        key_map = {
            "bash": "command", "read_file": "file_path", "write_file": "file_path",
            "edit": "file_path", "grep": "pattern", "glob": "pattern",
            "web_search": "query", "web_fetch": "url",
            "agent": "description", "load_skill": "skill_name",
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
        console.print("\n[bold yellow]Goodbye![/]")
