"""Load skill tool."""
from __future__ import annotations

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "skill_name": {"type": "string", "description": "Name of the skill to load"},
    },
    "required": ["skill_name"],
})
class LoadSkillTool(Tool):
    name = "load_skill"
    description = "Load a skill's detailed instructions. Use when a user's request matches a skill's description."
    read_only = True

    def __init__(self, skills_loader=None):
        super().__init__()
        self._loader = skills_loader

    def set_loader(self, loader):
        self._loader = loader

    async def execute(self, skill_name: str) -> str:
        if not self._loader:
            return "load_skill:\n[FAILED] Skills system not initialized."

        skill = self._loader.load_skill(skill_name)
        if not skill:
            available = [s["name"] for s in self._loader.list_skills(filter_unavailable=False)]
            return f"load_skill:\n[FAILED] Skill '{skill_name}' not found. Available: {', '.join(available)}"

        return f"# Skill: {skill_name}\n\n{skill}"
