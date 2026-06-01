"""Sub-agent manager."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider
    from banana.tools.registry import ToolRegistry


@dataclass
class AgentDefinition:
    description: str
    tools: list[str] | None = None
    read_only: bool = False
    system_prompt: str = ""


AGENT_DEFINITIONS = {
    "Explore": AgentDefinition(
        description="Read-only codebase exploration",
        tools=["read_file", "glob", "grep", "web_search", "web_fetch", "load_skill"],
        read_only=True,
        system_prompt="You are a code exploration assistant. Explore the codebase and report findings.",
    ),
    "Plan": AgentDefinition(
        description="Design implementation plans",
        tools=["read_file", "glob", "grep"],
        read_only=True,
        system_prompt="You are a software architecture assistant. Design plans and analyze trade-offs.",
    ),
    "general-purpose": AgentDefinition(
        description="Full-capability sub-agent",
        tools=None,
        read_only=False,
        system_prompt="You are a general-purpose coding assistant. Complete the given task autonomously.",
    ),
}


class SubagentManager:
    def __init__(self, provider: "LLMProvider", tools: "ToolRegistry"):
        self.provider = provider
        self.tools = tools

    def _filter_tools(self, definition: AgentDefinition) -> "ToolRegistry":
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
