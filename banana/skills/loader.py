"""Skills loader for agent capabilities."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import yaml

_STRIP_FRONTMATTER = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)


class SkillsLoader:
    def __init__(self, workspace: Path, user_skills_dir: Path | None = None,
                 disabled_skills: set[str] | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / ".banana" / "skills"
        self.user_skills = user_skills_dir or Path.home() / ".bananacoder" / "skills"
        self.disabled_skills = disabled_skills or set()

    def _skill_entries_from_dir(self, base: Path, source: str,
                                skip_names: set[str] | None = None) -> list[dict[str, str]]:
        if not base.exists():
            return []
        entries = []
        for skill_dir in base.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            name = skill_dir.name
            if skip_names is not None and name in skip_names:
                continue
            entries.append({"name": name, "path": str(skill_file), "source": source})
        return entries

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        skills = self._skill_entries_from_dir(self.workspace_skills, "workspace")
        workspace_names = {entry["name"] for entry in skills}
        if self.user_skills.exists():
            skills.extend(
                self._skill_entries_from_dir(self.user_skills, "user", skip_names=workspace_names),
            )
        if self.disabled_skills:
            skills = [s for s in skills if s["name"] not in self.disabled_skills]
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills

    def load_skill(self, name: str) -> str | None:
        roots = [self.workspace_skills]
        if self.user_skills:
            roots.append(self.user_skills)
        for root in roots:
            path = root / name / "SKILL.md"
            if path.exists():
                return self._strip_frontmatter(path.read_text(encoding="utf-8"))
        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                parts.append(f"### Skill: {name}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    def build_skills_summary(self, exclude: set[str] | None = None) -> str:
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""
        lines = []
        for entry in all_skills:
            name = entry["name"]
            if exclude and name in exclude:
                continue
            meta = self._get_skill_meta(name)
            available = self._check_requirements(meta)
            desc = self._get_skill_description(name)
            if available:
                lines.append(f"- **{name}** — {desc}  `{entry['path']}`")
            else:
                missing = self._get_missing_requirements(meta)
                lines.append(f"- **{name}** — {desc} (unavailable: {missing})  `{entry['path']}`")
        return "\n".join(lines)

    def get_always_skills(self) -> list[str]:
        return [
            entry["name"]
            for entry in self.list_skills(filter_unavailable=True)
            if (meta := self.get_skill_metadata(entry["name"]))
            and meta.get("always")
        ]

    def get_skill_metadata(self, name: str) -> dict | None:
        roots = [self.workspace_skills]
        if self.user_skills:
            roots.append(self.user_skills)
        for root in roots:
            path = root / name / "SKILL.md"
            if path.exists():
                raw = path.read_text(encoding="utf-8")
                if not raw.startswith("---"):
                    return None
                match = _STRIP_FRONTMATTER.match(raw)
                if not match:
                    return None
                try:
                    parsed = yaml.safe_load(match.group(1))
                except yaml.YAMLError:
                    return None
                if isinstance(parsed, dict):
                    return parsed
        return None

    def _get_skill_meta(self, name: str) -> dict:
        raw = self.get_skill_metadata(name) or {}
        metadata = raw.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return metadata.get("nanobot", metadata.get("banana", {}))

    def _check_requirements(self, skill_meta: dict) -> bool:
        requires = skill_meta.get("requires", {})
        required_bins = requires.get("bins", [])
        required_env_vars = requires.get("env", [])
        return all(shutil.which(cmd) for cmd in required_bins) and all(
            os.environ.get(var) for var in required_env_vars
        )

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        requires = skill_meta.get("requires", {})
        missing = []
        for cmd in requires.get("bins", []):
            if not shutil.which(cmd):
                missing.append(f"CLI: {cmd}")
        for var in requires.get("env", []):
            if not os.environ.get(var):
                missing.append(f"ENV: {var}")
        return ", ".join(missing) if missing else ""

    def _get_skill_description(self, name: str) -> str:
        meta = self.get_skill_metadata(name)
        return (meta or {}).get("description", name)

    def _strip_frontmatter(self, content: str) -> str:
        if not content.startswith("---"):
            return content
        match = _STRIP_FRONTMATTER.match(content)
        if match:
            return content[match.end():].strip()
        return content
