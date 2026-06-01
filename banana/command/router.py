"""Command router with tiered dispatch (inspired by nanobot's command system)."""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

console = Console()

# Handler: receives (args: str, ctx: dict) -> str | None (None = not handled)
Handler = Callable[[str, dict[str, Any]], Awaitable[str | None]]


@dataclass(frozen=True)
class CommandSpec:
    """Metadata for a slash command (inspired by nanobot's BuiltinCommandSpec)."""
    command: str          # e.g. "/new"
    title: str            # e.g. "New chat"
    description: str      # e.g. "Clear the session and start fresh."
    icon: str = ""        # Emoji icon
    arg_hint: str = ""    # e.g. "[preset]" or "[name]"
    priority: bool = False  # True = dispatch before session lock


class CommandRouter:
    """Tiered command dispatcher.

    Dispatch order:
      1. Priority commands (exact match, dispatched immediately)
      2. Exact commands (exact match)
      3. Prefix commands (longest-prefix-first match)
      4. Interceptors (fallback chain)
    """

    def __init__(self):
        self._priority: dict[str, Handler] = {}
        self._exact: dict[str, Handler] = {}
        self._prefix: list[tuple[str, Handler]] = []  # sorted by prefix length desc
        self._interceptors: list[Handler] = []
        self._specs: list[CommandSpec] = []

    # ---- Registration ----

    def priority(self, command: str, handler: Handler, **spec_kw):
        """Register a priority command (dispatched before session lock)."""
        self._priority[command] = handler
        spec_kw.pop("priority", None)  # Don't double-pass priority
        self._register_spec(command, handler, priority=True, **spec_kw)

    def exact(self, command: str, handler: Handler, **spec_kw):
        """Register an exact-match command."""
        self._exact[command] = handler
        self._register_spec(command, handler, **spec_kw)

    def prefix(self, command: str, handler: Handler, **spec_kw):
        """Register a prefix-match command. E.g. prefix('/model ', handler)."""
        self._prefix.append((command, handler))
        self._prefix.sort(key=lambda x: len(x[0]), reverse=True)
        # Only create spec if one doesn't exist (exact registration takes priority)
        cmd = command.strip()
        if not any(s.command == cmd for s in self._specs):
            self._register_spec(cmd, handler, **spec_kw)

    def intercept(self, handler: Handler):
        """Register an interceptor (fallback handler)."""
        self._interceptors.append(handler)

    def _register_spec(self, command: str, handler: Handler, priority: bool = False, **kw):
        # Deduplicate by command
        cmd = command.rstrip()
        existing = [s for s in self._specs if s.command == cmd]
        for s in existing:
            self._specs.remove(s)
        if not kw.get("hide_from_help"):
            self._specs.append(CommandSpec(
                command=cmd,
                title=kw.get("title", cmd.lstrip("/")),
                description=kw.get("description", ""),
                icon=kw.get("icon", ""),
                arg_hint=kw.get("arg_hint", ""),
                priority=priority,
            ))

    # ---- Dispatch ----

    def is_priority(self, text: str) -> bool:
        return text.split()[0] in self._priority if text else False

    def is_command(self, text: str) -> bool:
        if not text or not text.startswith("/"):
            return False
        head = text.split()[0]
        return head in self._priority or head in self._exact or any(
            text.startswith(prefix) for prefix, _ in self._prefix
        )

    async def dispatch_priority(self, text: str, ctx: dict) -> str | None:
        """Dispatch priority commands inline (no session lock)."""
        head = text.split()[0]
        handler = self._priority.get(head)
        if handler:
            args = text[len(head):].strip()
            return await handler(args, ctx)
        return None

    async def dispatch(self, text: str, ctx: dict) -> str | None:
        """Full dispatch: exact -> prefix -> interceptor."""
        # 1. Exact match
        head = text.split()[0]
        handler = self._exact.get(head)
        if handler:
            args = text[len(head):].strip()
            return await handler(args, ctx)

        # 2. Prefix match (longest first)
        for prefix, handler in self._prefix:
            if text.startswith(prefix):
                args = text[len(prefix):].strip()
                return await handler(args, ctx)

        # 3. Interceptors
        for handler in self._interceptors:
            result = await handler(text, ctx)
            if result is not None:
                return result

        return None

    # ---- Help ----

    def build_help_text(self) -> str:
        """Generate help text from registered command specs, grouped by category."""
        groups = [
            ("Session", [
                "/clear", "/session", "/history", "/export",
            ]),
            ("State & config", [
                "/status", "/model", "/mode", "/config", "/tool", "/skill",
            ]),
            ("Memory", [
                "/memory", "/remember", "/forget",
            ]),
            ("Other", [
                "/stop", "/help", "/exit",
            ]),
        ]
        # Build lookup from command name to spec
        spec_map: dict[str, CommandSpec] = {}
        for s in self._specs:
            cmd = s.command.rstrip()
            spec_map[cmd] = s

        lines: list[str] = []
        for group_name, cmds in groups:
            visible = [(c, spec_map[c]) for c in cmds if c in spec_map]
            if not visible:
                continue
            lines.append(f"[bold]{group_name}:[/bold]")
            for cmd, spec in visible:
                arg = " " + spec.arg_hint if spec.arg_hint else ""
                lines.append(f"  {cmd}{arg} — {spec.description}")
            lines.append("")
        return "\n".join(lines).rstrip()
