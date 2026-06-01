"""Memory tool for persistent cross-session memory."""
from __future__ import annotations

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "Action: 'add' to remember a fact, 'search' to find facts, 'list' to show all sections",
            "enum": ["add", "search", "list"],
        },
        "section": {
            "type": "string",
            "description": "Section name for 'add' action (e.g. 'Preferences', 'Project')",
        },
        "fact": {
            "type": "string",
            "description": "The fact to remember, one sentence. Use for 'add' and 'search' actions.",
        },
    },
    "required": ["action"],
})
class MemoryTool(Tool):
    name = "memory"
    description = (
        "Manage persistent memory across sessions. "
        "Use 'add' to remember facts about the user or project. "
        "Use 'search' to find existing facts. Use 'list' to see all sections."
    )
    read_only = False

    def __init__(self, memory_store=None):
        super().__init__()
        self._store = memory_store

    def set_store(self, store):
        self._store = store

    async def execute(self, action: str, section: str = "", fact: str = "") -> str:
        if not self._store:
            return "memory:\n[FAILED] Memory system not initialized."

        if action == "add":
            if not section or not fact:
                return "memory:\n[FAILED] Both 'section' and 'fact' are required for 'add' action."
            self._store.add(section, fact)
            return f"memory:\n[OK] Remembered: [{section}] {fact}"

        elif action == "search":
            if not fact:
                return "memory:\n[FAILED] 'fact' parameter is required for 'search' action."
            results = self._store.search(fact)
            if not results:
                return f"memory:\n[OK] No facts matching '{fact}'."
            return f"memory:\n[OK] Found {len(results)}:\n" + "\n".join(f"- {r}" for r in results)

        elif action == "list":
            sections = self._store.get_sections()
            if not sections:
                return "memory:\n[OK] Memory is empty."
            lines = []
            for sec, facts in sections.items():
                if sec == "_header":
                    continue
                lines.append(f"\n### {sec}")
                for f in facts:
                    lines.append(f"  - {f}")
            return "memory:\n[OK]" + "\n".join(lines)

        return "memory:\n[FAILED] Unknown action. Use: add, search, or list."
