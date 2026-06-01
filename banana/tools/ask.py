"""Interactive user prompt tool."""
from __future__ import annotations

import asyncio

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The question to ask the user"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "Predefined options (optional)"},
    },
    "required": ["question"],
})
class AskUserTool(Tool):
    name = "ask_user"
    description = "Ask the user a question. Use when you need clarification before proceeding."
    exclusive = True

    async def execute(self, question: str, options: list[str] | None = None) -> str:
        from rich.console import Console
        from rich.prompt import Prompt

        console = Console()
        console.print(f"\n[bold yellow]? {question}[/bold yellow]")

        if options:
            for i, opt in enumerate(options, 1):
                console.print(f"  {i}. {opt}")
            console.print("  Or type your answer:")

        answer = await asyncio.to_thread(lambda: Prompt.ask(">", default=""))
        return f"user_answer:\n{answer or '(no response)'}"
