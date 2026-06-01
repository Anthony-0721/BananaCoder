"""Task tracking tool."""
from __future__ import annotations

from typing import Any

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Task description"},
                    "status": {"type": "string", "description": "pending, in_progress, completed, cancelled"},
                    "priority": {"type": "string", "description": "high, medium, low"},
                },
                "required": ["content", "status"],
            },
            "description": "The updated todo list",
        },
    },
    "required": ["todos"],
})
class TodoWriteTool(Tool):
    name = "todo_write"
    description = "Create and manage a structured task list. Use for complex multi-step tasks."
    exclusive = True

    _STATUS_MARKERS = {"completed": "[x]", "in_progress": "[>]", "cancelled": "[-]", "pending": "[ ]"}

    async def execute(self, todos: list[dict[str, Any]]) -> str:
        active = sum(1 for t in todos if t.get("status") != "completed")
        lines = [f"{active} active todo(s):"]
        for t in todos:
            status = t.get("status", "pending")
            content = t.get("content", "")
            priority = t.get("priority", "medium")
            marker = self._STATUS_MARKERS.get(status, "[ ]")
            lines.append(f"  {marker} {content} (priority: {priority})")

        if not todos:
            return "Todo list cleared."
        return "\n".join(lines)
