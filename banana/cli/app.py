"""CLI application entry point."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from banana.config.loader import load_config, resolve_env_vars
from banana.config.schema import Config
from banana.providers.factory import make_provider
from banana.tools.registry import ToolRegistry
from banana.tools.bash import BashTool
from banana.tools.filesystem import ReadFileTool, WriteFileTool, EditTool
from banana.tools.search import GlobTool, GrepTool
from banana.tools.web import WebSearchTool, WebFetchTool
from banana.tools.agent_tool import AgentTool
from banana.tools.ask import AskUserTool
from banana.tools.todo import TodoWriteTool
from banana.tools.skill_tool import LoadSkillTool
from banana.tools.mcp import connect_mcp_servers
from banana.session.manager import SessionManager
from banana.skills.loader import SkillsLoader
from banana.agent.loop import Agent
from banana.cli.display import Display, console


def build_tools(config: Config, skills_loader: SkillsLoader) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    from loguru import logger
    search_tool = WebSearchTool()
    if config.tools.tavily_api_key:
        search_tool.set_api_key(config.tools.tavily_api_key)
        logger.debug(f"Tavily API key configured (length={len(config.tools.tavily_api_key)})")
    else:
        logger.debug("Tavily API key NOT configured")
    registry.register(search_tool)
    registry.register(WebFetchTool())
    registry.register(AgentTool())
    registry.register(AskUserTool())
    registry.register(TodoWriteTool())
    skill_tool = LoadSkillTool()
    skill_tool.set_loader(skills_loader)
    registry.register(skill_tool)
    return registry


async def _run_single(config: Config, args, mcp_stacks):
    """Single-shot execution mode."""
    display = Display()
    skills_loader = SkillsLoader(Path.cwd())
    registry = build_tools(config, skills_loader)
    provider = make_provider(config)

    data_dir = Path.home() / ".bananacoder"
    session_mgr = SessionManager(data_dir, Path.cwd())
    if args.session:
        await session_mgr.switch(args.session)

    # Connect MCP servers
    more_stacks = await connect_mcp_servers(
        {k: v.model_dump() for k, v in config.mcp_servers.items()},
        registry,
    )
    mcp_stacks.update(more_stacks)

    try:
        agent = Agent(provider, registry, session_mgr, skills_loader,
                      max_rounds=config.agent.max_tool_rounds,
                      max_tool_chars=config.agent.max_tool_result_chars)
        result = await agent.chat(
            args.prompt,
            on_token=display.on_token,
            on_tool=display.on_tool,
        )
        console.print(f"\n{result}")
    finally:
        for stack in mcp_stacks.values():
            await stack.aclose()


async def _run_interactive(config: Config, args):
    """Interactive REPL mode."""
    display = Display()
    skills_loader = SkillsLoader(Path.cwd())
    registry = build_tools(config, skills_loader)
    provider = make_provider(config)

    data_dir = Path.home() / ".bananacoder"
    data_dir.mkdir(parents=True, exist_ok=True)
    session_mgr = SessionManager(data_dir, Path.cwd())

    mcp_stacks = await connect_mcp_servers(
        {k: v.model_dump() for k, v in config.mcp_servers.items()},
        registry,
    )

    agent = Agent(provider, registry, session_mgr, skills_loader,
                  max_rounds=config.agent.max_tool_rounds,
                  max_tool_chars=config.agent.max_tool_result_chars)

    default_preset = config.model_presets.get("default")
    model_name = default_preset.model if default_preset else "unknown"
    session = await session_mgr.load()
    display.print_welcome(model_name, session.id)

    bindings = KeyBindings()

    @bindings.add("c-c")
    def _(event):
        console.print("\n[yellow]Interrupted[/yellow]")

    prompt_session = PromptSession(
        history=FileHistory(str(data_dir / ".history")),
        key_bindings=bindings,
        style=Style.from_dict({"prompt": "bold green"}),
    )

    try:
        while True:
            try:
                line = await prompt_session.prompt_async("> ")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            if line.startswith("/"):
                result = await _handle_slash(line, session_mgr, config, skills_loader, registry)
                if result == "EXIT":
                    break
                continue

            console.print()
            try:
                await agent.chat(
                    line,
                    on_token=display.on_token,
                    on_tool=display.on_tool,
                )
                console.print()
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        await session_mgr.save(session)
        for stack in mcp_stacks.values():
            await stack.aclose()

    display.print_goodbye()


async def _handle_slash(cmd: str, session_mgr, config, skills_loader=None, registry=None):
    parts = cmd.split()
    op = parts[0].lower()

    if op in ("/exit", "/quit"):
        return "EXIT"
    elif op == "/help":
        console.print("""
[bold]Commands:[/bold]
  /session list|new|switch|delete  — Session management
  /model [name]                     — View or switch model
  /tool                             — List available tools (including MCP)
  /skill                            — List available skills
  /config                           — Show config
  /yolo on|off                      — Auto-approve mode
  /clear                            — Clear current session
  /status                           — Show current status
  /exit, /quit                      — Exit
""")
    elif op == "/tool":
        if registry is None:
            console.print("[yellow]Tool registry not available.[/yellow]")
        else:
            names = sorted(registry.tool_names)
            builtins = [n for n in names if not n.startswith("mcp_")]
            mcp_tools = [n for n in names if n.startswith("mcp_")]
            console.print(f"\n[bold]Tools ({len(names)} total)[/bold]\n")
            if builtins:
                console.print("[bold]Built-in:[/bold]")
                for n in builtins:
                    tool = registry.get(n)
                    desc = tool.description[:60] if tool else ""
                    console.print(f"  {n} — {desc}")
            if mcp_tools:
                console.print(f"\n[bold]MCP ({len(mcp_tools)}):[/bold]")
                for n in mcp_tools:
                    tool = registry.get(n)
                    desc = tool.description[:60] if tool else ""
                    console.print(f"  {n} — {desc}")
            console.print()
    elif op == "/skill":
        if skills_loader is None:
            console.print("[yellow]Skills loader not available.[/yellow]")
        else:
            skills = skills_loader.list_skills(filter_unavailable=False)
            if not skills:
                console.print("\n[yellow]No skills found.[/yellow]")
                console.print("Place skills in .banana/skills/<name>/SKILL.md or ~/.bananacoder/skills/<name>/SKILL.md\n")
            else:
                console.print(f"\n[bold]Skills ({len(skills)}):[/bold]\n")
                for s in skills:
                    available = skills_loader._check_requirements(skills_loader._get_skill_meta(s["name"]))
                    status = "" if available else " [dim](unavailable)[/dim]"
                    console.print(f"  {s['name']} — {s['source']}{status}")
                console.print()
    elif op == "/session":
        sub = parts[1] if len(parts) > 1 else "list"
        if sub == "list":
            sessions = await session_mgr.list_sessions()
            for s in sessions:
                marker = "-> " if s.get("id") == session_mgr._active_id else "  "
                console.print(f"{marker}{s.get('id', '?')} ({s.get('message_count', 0)} msgs)")
        elif sub == "new" and len(parts) > 2:
            s = await session_mgr.new(parts[2])
            console.print(f"Created and switched to session: {s.id}")
        elif sub == "switch" and len(parts) > 2:
            s = await session_mgr.switch(parts[2])
            console.print(f"Switched to session: {s.id}")
        elif sub == "delete" and len(parts) > 2:
            await session_mgr.delete(parts[2])
            console.print(f"Deleted session: {parts[2]}")
    elif op == "/status":
        session = await session_mgr.load()
        default = config.model_presets.get("default")
        console.print(f"Session: {session.id}  Messages: {len(session.messages)}  Model: {default.model if default else 'N/A'}")
    elif op == "/config":
        console.print(f"Config file: ~/.bananacoder/config.json")
        console.print(f"Providers: {', '.join(config.providers.keys()) or 'none'}")
        default = config.model_presets.get("default")
        if default:
            console.print(f"Default model: {default.model} (provider: {default.provider})")
        console.print(f"Fallback models: {', '.join(config.fallback_models) or 'none'}")
        console.print(f"MCP servers: {', '.join(config.mcp_servers.keys()) or 'none'}")
    elif op == "/model":
        if len(parts) > 1:
            console.print(f"[yellow]Model switching not yet implemented. Edit ~/.bananacoder/config.json to change model.[/yellow]")
        else:
            default = config.model_presets.get("default")
            console.print(f"Current model: {default.model if default else 'N/A'}")
            console.print(f"Available presets: {', '.join(config.model_presets.keys()) or 'default only'}")
    elif op == "/yolo":
        console.print("[yellow]YOLO mode not yet implemented.[/yellow]")
    elif op == "/clear":
        session = await session_mgr.load()
        session.messages.clear()
        await session_mgr.save(session)
        console.print("Session cleared.")
    else:
        console.print(f"Unknown command: {op}. Type /help for commands.")


def main():
    parser = argparse.ArgumentParser(description="BananaCoder - AI coding assistant")
    parser.add_argument("prompt", nargs="?", help="Single-shot prompt (omit for interactive mode)")
    parser.add_argument("--session", "-s", help="Session name")
    parser.add_argument("--model", "-m", help="Model override")
    args = parser.parse_args()

    config = resolve_env_vars(load_config())

    if args.prompt:
        mcp_stacks = {}
        asyncio.run(_run_single(config, args, mcp_stacks))
    else:
        asyncio.run(_run_interactive(config, args))


if __name__ == "__main__":
    main()
