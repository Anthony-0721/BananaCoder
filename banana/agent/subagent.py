"""Sub-agent manager."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from banana.prompts.subagent import AGENT_DEFINITIONS

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider
    from banana.tools.registry import ToolRegistry


class SubagentManager:
    """Manages subagent execution (synchronous only)."""

    def __init__(self, provider: "LLMProvider", tools: "ToolRegistry"):
        self.provider = provider
        self.tools = tools

    def _filter_tools(self, definition) -> "ToolRegistry":
        if definition.tools is None:
            return self.tools
        from banana.tools.registry import ToolRegistry
        filtered = ToolRegistry()
        for tool_name in definition.tools:
            tool = self.tools.get(tool_name)
            if tool:
                filtered.register(tool)
        return filtered

    async def run_subagent(self, prompt: str, agent_type: str = "Explore",
                           timeout: int = 300) -> str:
        """Run a subagent synchronously and return the result text."""
        definition = AGENT_DEFINITIONS.get(agent_type)
        if not definition:
            return f"Unknown agent type '{agent_type}'. Available: {', '.join(AGENT_DEFINITIONS)}"

        sub_tools = self._filter_tools(definition)

        from banana.agent.runner import AgentRunner
        runner = AgentRunner(
            provider=self.provider,
            tools=sub_tools,
            subagent_manager=None,
            system_prompt_override=definition.system_prompt,
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            result = await asyncio.wait_for(
                runner.run(messages),
                timeout=timeout,
            )
            return result.text
        except asyncio.TimeoutError:
            return f"Sub-agent timed out after {timeout}s"
