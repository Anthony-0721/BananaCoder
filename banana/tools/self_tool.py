"""Self-inspection tool — lets the agent query its own runtime state."""

from __future__ import annotations

from banana.tools.base import Tool, tool_parameters
from banana.tools.runtime_state import RuntimeState


@tool_parameters({
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "Specific field to inspect, or omit for all: model, provider, max_iterations, current_iteration, security_mode, working_dir, tools_available, session_messages",
        },
    },
})
class SelfTool(Tool):
    name = "self"
    description = "Inspect the agent's own runtime state: model, iteration, security mode, etc."

    def __init__(self, state: RuntimeState | None = None):
        super().__init__()
        self._state = state or RuntimeState()

    @property
    def read_only(self) -> bool:
        return True

    @property
    def concurrency_safe(self) -> bool:
        return True

    def set_state(self, state: RuntimeState):
        self._state = state

    async def execute(self, key: str = "") -> str:
        data = self._state.snapshot()
        if key:
            val = data.get(key)
            if val is None:
                return f"self:\n[FAILED] Unknown key '{key}'. Valid keys: {', '.join(sorted(data))}"
            return f"self:\n[OK] {key}: {val}"
        lines = [f"self:\n[OK] Runtime state"]
        for k, v in sorted(data.items()):
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
