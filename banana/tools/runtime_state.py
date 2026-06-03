"""Runtime state holder for agent self-inspection."""

from __future__ import annotations


class RuntimeState:
    """Live agent state exposed to the SelfTool."""

    def __init__(self):
        self.model: str = "unknown"
        self.provider: str = "unknown"
        self.max_rounds: int = 50
        self.iteration: int = 0
        self.security_mode: str = "normal"
        self.working_dir: str = ""
        self.tool_count: int = 0
        self.session_messages: int = 0

    def snapshot(self) -> dict[str, object]:
        return {
            "model": self.model,
            "provider": self.provider,
            "max_iterations": self.max_rounds,
            "current_iteration": self.iteration,
            "security_mode": self.security_mode,
            "working_dir": self.working_dir,
            "tools_available": self.tool_count,
            "session_messages": self.session_messages,
        }
