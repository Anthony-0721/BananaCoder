"""Sub-agent launcher tool."""
from __future__ import annotations

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Task description for the sub-agent"},
        "subagent_type": {"type": "string", "description": "Type: Explore, Plan, or general-purpose"},
        "description": {"type": "string", "description": "Short description (for display)"},
        "timeout_seconds": {"type": "integer", "description": "Max seconds (default 300)"},
    },
    "required": ["prompt", "subagent_type"],
})
class AgentTool(Tool):
    name = "agent"
    description = (
        "Launch a sub-agent to handle a task independently. "
        "Use this for:\n"
        "- Researching codebase structure or searching across many files\n"
        "- Implementing a multi-step change in isolation (fresh context)\n"
        "- Designing implementation plans with structured analysis\n"
        "- Any task that would benefit from a separate context window\n\n"
        "You can launch multiple agents in a single response — "
        "they will execute in parallel.\n"
        "Available types: Explore (read-only search), Plan (architecture design), "
        "general-purpose (full tool access)"
    )

    @property
    def concurrency_safe(self) -> bool:
        return True

    def __init__(self, subagent_manager=None):
        super().__init__()
        self._manager = subagent_manager

    def set_manager(self, manager):
        self._manager = manager

    async def execute(self, prompt: str, subagent_type: str = "Explore",
                      description: str = "", timeout_seconds: int = 300) -> str:
        if not self._manager:
            return "agent:\n[FAILED] Subagent system not initialized."
        result = await self._manager.run_subagent(
            prompt=prompt, agent_type=subagent_type, timeout=timeout_seconds,
        )
        if len(result) > 5000:
            result = result[:4500] + f"\n... (sub-agent output truncated, {len(result)} chars total)"
        return f"agent:\n[Sub-agent completed]\n{result}"
