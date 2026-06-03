"""CLI application entry point."""
from __future__ import annotations

import argparse
import asyncio
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

    if config.security.restrict_to_workspace:
        from banana.tools import filesystem as fs_tools
        fs_tools.set_workspace_root(Path.cwd())

    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    search_tool = WebSearchTool()
    if config.tools.tavily_api_key:
        search_tool.set_api_key(config.tools.tavily_api_key)
    registry.register(search_tool)
    registry.register(WebFetchTool())
    registry.register(AgentTool())
    registry.register(AskUserTool())
    registry.register(TodoWriteTool())
    skill_tool = LoadSkillTool()
    skill_tool.set_loader(skills_loader)
    registry.register(skill_tool)
    from banana.tools.memory_tool import MemoryTool
    memory_tool = MemoryTool()
    registry.register(memory_tool)
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

    # Load security config
    from banana.security import SecurityContext, SecurityMode, get_security
    sec = get_security()
    if config.security.mode in ("fast", "yolo", "normal"):
        sec.mode = SecurityMode(config.security.mode)
    if config.security.auto_approve:
        sec.auto_approve = config.security.auto_approve
    if config.security.write_patterns:
        sec.write_patterns = config.security.write_patterns
    if config.security.blocked:
        sec.blocked = config.security.blocked

    data_dir = Path.home() / ".bananacoder"
    data_dir.mkdir(parents=True, exist_ok=True)
    session_mgr = SessionManager(data_dir, Path.cwd())

    mcp_stacks = await connect_mcp_servers(
        {k: v.model_dump() for k, v in config.mcp_servers.items()},
        registry,
    )

    # Initialize memory store
    from banana.memory.store import MemoryStore
    memory_store = MemoryStore(data_dir)

    # Wire memory tool
    mem_tool = registry.get("memory")
    if mem_tool:
        mem_tool.set_store(memory_store)

    agent = Agent(provider, registry, session_mgr, skills_loader,
                  memory_store=memory_store,
                  max_rounds=config.agent.max_tool_rounds,
                  max_tool_chars=config.agent.max_tool_result_chars,
                  on_background_complete=display.on_background_complete)

    # Set up command router (inspired by nanobot's CommandRouter)
    from banana.command.router import CommandRouter
    from banana.command.builtin import register_builtin_commands
    command_router = CommandRouter()
    register_builtin_commands(command_router, {
        "session_mgr": session_mgr,
        "config": config,
        "skills_loader": skills_loader,
        "registry": registry,
        "agent_loop": None,
    })

    default_preset = config.model_presets.get("default")
    model_name = default_preset.model if default_preset else "unknown"
    session = await session_mgr.load()

    # Clean startup summary
    mcp_count = len([n for n in registry.tool_names if n.startswith("mcp_")])
    builtin_count = len(registry) - mcp_count
    skill_count = len(skills_loader.list_skills(filter_unavailable=False))
    mcp_server_count = len(config.mcp_servers)
    tavily_status = "ok" if config.tools.tavily_api_key else "not set"
    ws_status = "restricted" if config.security.restrict_to_workspace else "open"
    summary = (f"Tools: {builtin_count} built-in + {mcp_count} MCP | "
               f"Skills: {skill_count} | MCP: {mcp_server_count} | "
               f"Tavily: {tavily_status} | Workspace: {ws_status}")

    display.print_welcome(model_name, session.id, summary)

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

            # Check if it's a command
            if line.startswith("/") and command_router.is_command(line):
                result = await command_router.dispatch(line, {})
                if result == "EXIT":
                    break
                continue

            console.print()
            try:
                await agent.chat(
                    line,
                    on_token=display.on_token,
                    on_tool=display.on_tool,
                    on_tool_result=display.on_tool_result,
                )
                console.print()
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        for stack in mcp_stacks.values():
            await stack.aclose()

    display.print_goodbye()


def main():
    # Suppress DEBUG logs from MCP SDK and internal modules
    from loguru import logger
    logger.remove()
    logger.add(lambda _: None, level="WARNING")  # Only show WARNING and above by default

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
