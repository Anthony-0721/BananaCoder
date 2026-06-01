"""Built-in slash command handlers (inspired by nanobot's builtin.py)."""
from __future__ import annotations

from typing import Any

from banana.command.router import CommandRouter


def register_builtin_commands(router: CommandRouter, dependencies: dict[str, Any]):
    """Register all built-in commands. Dependencies dict provides:
    - session_mgr: SessionManager
    - config: Config
    - skills_loader: SkillsLoader | None
    - registry: ToolRegistry | None
    - agent_loop: Any | None (for /stop)
    """

    session_mgr = dependencies.get("session_mgr")
    config = dependencies.get("config")
    skills_loader = dependencies.get("skills_loader")
    registry = dependencies.get("registry")

    # ---- /help ----
    async def cmd_help(args: str, ctx: dict) -> str | None:
        from rich.console import Console
        Console().print(router.build_help_text())
        return None

    router.exact("/help", cmd_help,
                 title="Help", description="Show all available commands", icon="?")

    # ---- /exit, /quit ----
    async def cmd_exit(args: str, ctx: dict) -> str | None:
        return "EXIT"

    router.exact("/exit", cmd_exit,
                 title="Exit", description="Exit BananaCoder")
    router.exact("/quit", cmd_exit, hide_from_help=True)

    # ---- /clear ----
    async def cmd_clear(args: str, ctx: dict) -> str | None:
        if not session_mgr:
            return None
        session = await session_mgr.load()
        session.messages.clear()
        await session_mgr.save(session)
        from rich.console import Console
        Console().print("[green]Session cleared. Starting fresh.[/green]")
        return None

    router.exact("/clear", cmd_clear,
                 title="Clear session", description="Clear current session, start fresh (same session ID)")
    router.exact("/new", cmd_clear, hide_from_help=True)

    # ---- /session ----
    async def cmd_session(args: str, ctx: dict) -> str | None:
        if not session_mgr:
            return None
        from rich.console import Console
        c = Console()
        parts = args.split()
        sub = parts[0] if parts else "list"

        if sub == "list":
            sessions = await session_mgr.list_sessions()
            for s in sessions:
                marker = "-> " if s.get("id") == session_mgr._active_id else "  "
                c.print(f"{marker}{s.get('id', '?')} ({s.get('message_count', 0)} msgs)")
        elif sub == "new" and len(parts) > 1:
            s = await session_mgr.new(parts[1])
            c.print(f"[green]Created session: {s.id}[/green]")
        elif sub == "switch" and len(parts) > 1:
            s = await session_mgr.switch(parts[1])
            c.print(f"[green]Switched to: {s.id}[/green]")
        elif sub == "delete" and len(parts) > 1:
            await session_mgr.delete(parts[1])
            c.print(f"[green]Deleted: {parts[1]}[/green]")
        else:
            cmd_session_help()
        return None

    def cmd_session_help():
        from rich.console import Console
        Console().print("/session list|new <name>|switch <name>|delete <name>")

    router.exact("/session", cmd_session,
                 title="Session", description="Manage sessions", icon="S", arg_hint="list|new|switch|delete")
    router.prefix("/session ", cmd_session)

    # ---- /status ----
    async def cmd_status(args: str, ctx: dict) -> str | None:
        if not session_mgr:
            return None
        from pathlib import Path
        from rich.console import Console
        from rich.table import Table
        from banana.security import get_security
        c = Console()
        session = await session_mgr.load()
        sec = get_security()
        default = config.model_presets.get("default") if config else None

        # Count tools
        tool_count = len(registry) if registry else 0
        mcp_count = len([n for n in registry.tool_names if n.startswith("mcp_")]) if registry else 0
        builtin_count = tool_count - mcp_count

        # Count skills
        skill_count = len(skills_loader.list_skills(filter_unavailable=False)) if skills_loader else 0

        table = Table(title="Status", show_header=False, title_style="bold")
        table.add_column("Key", style="dim")
        table.add_column("Value")
        pt = session.prompt_tokens
        ct = session.completion_tokens

        table.add_row("Session", f"{session.id} ({len(session.messages)} messages)")
        table.add_row("Working dir", str(Path.cwd()))
        table.add_row("Model", f"{default.model if default else 'N/A'} ({default.provider if default else 'N/A'})")
        table.add_row("Tokens", f"in: {pt:,}  out: {ct:,}  total: {pt+ct:,}")
        table.add_row("Security mode", sec.mode.value)
        table.add_row("Tools", f"{tool_count} total ({builtin_count} built-in, {mcp_count} MCP)")
        table.add_row("Skills", str(skill_count))
        mcp_server_count = len(config.mcp_servers) if config else 0
        table.add_row("MCP servers", f"{mcp_server_count} configured")
        c.print(table)
        return None

    router.exact("/status", cmd_status,
                 title="Status", description="Show current session, model, and security status", icon="i")

    # ---- /config ----
    async def cmd_config(args: str, ctx: dict) -> str | None:
        if not config:
            return None
        from rich.console import Console
        c = Console()
        c.print(f"Config file: ~/.bananacoder/config.json")
        c.print(f"Providers: {', '.join(config.providers.keys()) or 'none'}")
        default = config.model_presets.get("default")
        if default:
            c.print(f"Default model: {default.model} (provider: {default.provider})")
        c.print(f"Fallback: {', '.join(config.fallback_models) or 'none'}")
        c.print(f"MCP servers: {', '.join(config.mcp_servers.keys()) or 'none'}")
        c.print(f"Tavily key: {'configured' if config.tools.tavily_api_key else 'not set'}")
        return None

    router.exact("/config", cmd_config,
                 title="Config", description="Show current configuration", icon="*")

    # ---- /model ----
    async def cmd_model(args: str, ctx: dict) -> str | None:
        if not config:
            return None
        from rich.console import Console
        c = Console()
        if args:
            c.print(f"[yellow]Model switching at runtime not yet supported.[/yellow]")
            c.print(f"Edit ~/.bananacoder/config.json and restart to change model.")
        else:
            default = config.model_presets.get("default")
            c.print(f"Current: {default.model if default else 'N/A'}")
            c.print(f"Presets: {', '.join(config.model_presets.keys())}")
        return None

    router.exact("/model", cmd_model,
                 title="Model", description="View or switch model", icon="M", arg_hint="[name]")
    router.prefix("/model ", cmd_model)

    # ---- /mode (security mode) ----
    async def cmd_mode(args: str, ctx: dict) -> str | None:
        from banana.security import SecurityMode, set_mode
        if args in ("normal", "fast", "yolo"):
            set_mode(SecurityMode(args))
        else:
            from rich.console import Console
            c = Console()
            c.print("Usage: /mode normal|fast|yolo")
            sec = get_security()
            c.print(f"Current: {sec.mode.value}")
        return None

    router.exact("/mode", cmd_mode,
                 title="Security mode", description="Set security mode: normal|fast|yolo", icon="!", arg_hint="normal|fast|yolo")
    router.prefix("/mode ", cmd_mode)

    # Keep old-style aliases
    async def cmd_normal(args, ctx): return await cmd_mode("normal", ctx)
    async def cmd_fast(args, ctx): return await cmd_mode("fast", ctx)
    async def cmd_yolo(args, ctx): return await cmd_mode("yolo", ctx)

    router.exact("/normal", cmd_normal, hide_from_help=True)
    router.exact("/fast", cmd_fast, hide_from_help=True)
    router.exact("/yolo", cmd_yolo, hide_from_help=True)

    # ---- /tool ----
    async def cmd_tool(args: str, ctx: dict) -> str | None:
        if not registry:
            return None
        from rich.console import Console
        c = Console()
        names = sorted(registry.tool_names)
        builtins = [n for n in names if not n.startswith("mcp_")]
        mcp_tools = [n for n in names if n.startswith("mcp_")]
        c.print(f"\n[bold]Tools ({len(names)} total)[/bold]\n")
        if builtins:
            c.print("[bold]Built-in:[/bold]")
            for n in builtins:
                tool = registry.get(n)
                desc = tool.description[:60] if tool else ""
                c.print(f"  {n} — {desc}")
        if mcp_tools:
            c.print(f"\n[bold]MCP ({len(mcp_tools)}):[/bold]")
            for n in mcp_tools:
                tool = registry.get(n)
                desc = tool.description[:60] if tool else ""
                c.print(f"  {n} — {desc}")
        c.print()
        return None

    router.exact("/tool", cmd_tool,
                 title="Tools", description="List available tools (built-in + MCP)", icon="T")

    # ---- /skill ----
    async def cmd_skill(args: str, ctx: dict) -> str | None:
        if not skills_loader:
            return None
        from rich.console import Console
        c = Console()
        skills = skills_loader.list_skills(filter_unavailable=False)
        if not skills:
            c.print("\n[yellow]No skills found.[/yellow]")
            c.print("Place skills in .banana/skills/<name>/SKILL.md or ~/.bananacoder/skills/<name>/SKILL.md\n")
        else:
            c.print(f"\n[bold]Skills ({len(skills)}):[/bold]\n")
            for s in skills:
                available = skills_loader._check_requirements(skills_loader._get_skill_meta(s["name"]))
                status = "" if available else " [dim](unavailable)[/dim]"
                c.print(f"  {s['name']} — {s['source']}{status}")
            c.print()
        return None

    router.exact("/skill", cmd_skill,
                 title="Skills", description="List available skills", icon="S")

    # ---- /stop (priority command) ----
    async def cmd_stop(args: str, ctx: dict) -> str | None:
        from rich.console import Console
        Console().print("[yellow]Stop requested. Use Ctrl+C to interrupt current generation.[/yellow]")
        return None

    router.priority("/stop", cmd_stop, title="Stop", description="Interrupt current generation")

    # ---- /memory ----
    async def cmd_memory(args: str, ctx: dict) -> str | None:
        from rich.console import Console
        from banana.memory.store import MemoryStore
        from pathlib import Path
        c = Console()
        store = MemoryStore(Path.home() / ".bananacoder")
        sections = store.get_sections()
        if not sections or all(v == [] for k, v in sections.items() if k != "_header"):
            c.print("\n[yellow]Memory is empty.[/yellow]")
            c.print("Use [bold]/remember <fact>[/] to add, or let the AI use the [bold]memory[/] tool.\n")
        else:
            c.print("\n[bold]Memory:[/bold]\n")
            for sec, facts in sections.items():
                if sec == "_header":
                    continue
                c.print(f"[bold]{sec}:[/]")
                for f in facts:
                    c.print(f"  - {f}")
            c.print()
        return None

    router.exact("/memory", cmd_memory,
                 title="Memory", description="Show persistent memory")

    # ---- /remember ----
    async def cmd_remember(args: str, ctx: dict) -> str | None:
        from rich.console import Console
        from banana.memory.store import MemoryStore
        from pathlib import Path
        c = Console()
        if not args.strip():
            c.print("[yellow]Usage: /remember <fact>[/yellow]")
            return None
        store = MemoryStore(Path.home() / ".bananacoder")
        store.add("General", args.strip())
        c.print(f"[green]Remembered: {args.strip()}[/green]")
        return None

    router.exact("/remember", cmd_remember,
                 title="Remember", description="Add a fact to memory", arg_hint="<fact>")
    router.prefix("/remember ", cmd_remember)

    # ---- /forget ----
    async def cmd_forget(args: str, ctx: dict) -> str | None:
        from rich.console import Console
        from banana.memory.store import MemoryStore
        from pathlib import Path
        c = Console()
        if not args.strip():
            c.print("[yellow]Usage: /forget <query>[/yellow]")
            return None
        store = MemoryStore(Path.home() / ".bananacoder")
        removed = store.remove(None, args.strip())
        c.print(f"[green]Removed {removed} fact(s) matching '{args.strip()}'[/green]")
        return None

    router.exact("/forget", cmd_forget,
                 title="Forget", description="Remove facts from memory", arg_hint="<query>")
    router.prefix("/forget ", cmd_forget)

    # ---- /export ----
    async def cmd_export(args: str, ctx: dict) -> str | None:
        if not session_mgr:
            return None
        from pathlib import Path
        from datetime import datetime
        from rich.console import Console
        import aiofiles
        c = Console()
        session = await session_mgr.load()
        if not session.messages:
            c.print("[yellow]No messages to export.[/yellow]")
            return None

        # Determine file path
        filename = args.strip() if args else f"banana-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        path = Path(filename)
        if not path.is_absolute():
            path = Path.cwd() / path

        model_name = config.model_presets.get("default").model if config and config.model_presets else "N/A"
        lines = [
            f"# BananaCoder Session Export",
            f"",
            f"**Session**: {session.id} | **Model**: {model_name}",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Messages**: {len(session.messages)}",
            f"**Tokens**: in={session.prompt_tokens:,} out={session.completion_tokens:,} total={session.prompt_tokens+session.completion_tokens:,}",
            f"",
            f"---",
            f"",
        ]

        for m in session.messages:
            role = m.get("role", "?")
            content = str(m.get("content", ""))
            tool_calls = m.get("tool_calls", [])

            if role == "system":
                lines.append(f"### System\n\n```\n{content[:500]}\n```\n")
            elif role == "user":
                lines.append(f"### You\n\n{content}\n")
            elif role == "assistant":
                if tool_calls:
                    names = ", ".join(tc.get("function", {}).get("name", "?") for tc in tool_calls)
                    lines.append(f"### Assistant\n\n*Used tools: {names}*\n")
                    if content:
                        lines.append(f"{content}\n")
                else:
                    lines.append(f"### Assistant\n\n{content}\n")
            elif role == "tool":
                call_id = m.get("tool_call_id", "?")
                lines.append(f"*Tool result ({call_id[:8]}):*\n\n```\n{content[:500]}\n```\n")

        markdown = "\n".join(lines)
        try:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(markdown)
            c.print(f"[green]Exported {len(session.messages)} messages to {path}[/green]")
        except Exception as e:
            c.print(f"[red]Export failed: {e}[/red]")
        return None

    router.exact("/export", cmd_export,
                 title="Export", description="Export session to Markdown file", arg_hint="[filename]")
    router.prefix("/export ", cmd_export)

    # ---- /history ----
    async def cmd_history(args: str, ctx: dict) -> str | None:
        if not session_mgr:
            return None
        from rich.console import Console
        c = Console()
        n = 10
        if args:
            try:
                n = min(max(int(args.split()[0]), 1), 50)
            except ValueError:
                pass
        session = await session_mgr.load()
        msgs = session.messages[-n:] if len(session.messages) > n else session.messages
        c.print(f"\n[bold]Last {len(msgs)} messages:[/bold]\n")
        for i, m in enumerate(msgs):
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:120]
            # Escape Rich markup characters in content
            content = content.replace("[", "\\[").replace("]", "\\]")
            tool_calls = m.get("tool_calls", [])
            if role == "user":
                c.print(f"  [{i+1}] [bold blue]You:[/] {content}")
            elif role == "assistant":
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    c.print(f"  [{i+1}] [bold green]Assistant:[/] [dim]used {', '.join(names)}[/dim]")
                else:
                    c.print(f"  [{i+1}] [bold green]Assistant:[/] {content[:200]}")
            elif role == "tool":
                c.print(f"  [{i+1}] [bold yellow]Tool ({m.get('tool_call_id', '?')[:8]}):[/] [dim]{content[:100]}[/dim]")
            elif role == "system":
                c.print(f"  [{i+1}] [dim]System[/dim]")
        c.print()
        return None

    router.exact("/history", cmd_history,
                 title="History", description="Show recent conversation messages", arg_hint="[n]")
    router.prefix("/history ", cmd_history)
