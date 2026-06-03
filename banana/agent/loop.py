"""Main Agent orchestrator."""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from banana.agent.runner import AgentRunner
from banana.agent.subagent import SubagentManager
from banana.providers.base import LLMProvider
from banana.session.manager import SessionManager
from banana.skills.loader import SkillsLoader
from banana.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry,
        session_mgr: SessionManager, skills_loader: SkillsLoader,
        memory_store=None, hook_manager=None,
        max_rounds: int = 50, max_tool_chars: int = 80000,
        context_window_tokens: int = 128_000,
    ):
        self.provider = provider
        self.tools = tools
        self.session_mgr = session_mgr
        self.skills_loader = skills_loader
        self.memory_store = memory_store
        self.hook_manager = hook_manager
        self.max_rounds = max_rounds
        self.max_tool_chars = max_tool_chars
        self.context_window_tokens = context_window_tokens
        # Persistent subagent manager (survives across chat calls)
        self._subagent_mgr = SubagentManager(provider, tools)
        agent_tool = tools.get("agent")
        if agent_tool:
            agent_tool.set_manager(self._subagent_mgr)

    async def chat(
        self, user_input: str,
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_tool: Callable[[str, dict], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> str:
        session = await self.session_mgr.load()
        session.messages.append({"role": "user", "content": user_input})

        system_prompt = self._build_system_prompt()

        runner = AgentRunner(
            provider=self.provider, tools=self.tools,
            subagent_manager=self._subagent_mgr,
            system_prompt_override=system_prompt,
            hook_manager=self.hook_manager,
            max_rounds=self.max_rounds,
            max_tool_result_chars=self.max_tool_chars,
            context_window_tokens=self.context_window_tokens,
        )

        result = await runner.run(
            session.messages,
            on_token=on_token,
            on_tool=on_tool,
            on_tool_result=on_tool_result,
        )

        # Accumulate tokens
        session.prompt_tokens += result.prompt_tokens
        session.completion_tokens += result.completion_tokens

        await self.session_mgr.save(session)
        return result.text

    def _build_system_prompt(self) -> str:
        skills_summary = self.skills_loader.build_skills_summary()
        always_skills = self.skills_loader.get_always_skills()
        always_content = self.skills_loader.load_skills_for_context(always_skills) if always_skills else ""
        memory_context = self.memory_store.get_context() if self.memory_store else ""

        from banana.prompts.system import build_system_prompt
        return build_system_prompt(
            cwd=str(Path.cwd()),
            skills_summary=skills_summary,
            always_content=always_content,
            memory_context=memory_context,
        )
