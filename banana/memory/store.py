"""Persistent memory store (simplified from nanobot's MemoryStore)."""
from __future__ import annotations

import os
import re
from pathlib import Path

MEMORY_SECTION_RE = re.compile(r"^### (.+)$", re.MULTILINE)


class MemoryStore:
    """File-based long-term memory backed by a single MEMORY.md file.

    Stores facts as markdown bullet points under ### sections.
    Supports remember/forget/list operations.

    File format:
        # Memory

        ### Project
        - User prefers pytest over unittest
        - The API uses JWT auth

        ### Preferences
        - Always reply in Chinese
    """

    def __init__(self, storage_dir: Path):
        self._dir = storage_dir / "memory"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "MEMORY.md"
        self._ensure_file()

    def _ensure_file(self):
        if not self._path.exists():
            self._path.write_text("# Memory\n\n", encoding="utf-8")

    # ---- CRUD ----

    def read_all(self) -> str:
        return self._path.read_text(encoding="utf-8")

    def get_sections(self) -> dict[str, list[str]]:
        """Parse MEMORY.md into {section_name: [facts]}."""
        text = self.read_all()
        sections: dict[str, list[str]] = {}
        current = "_header"
        for line in text.splitlines():
            m = re.match(r"^### (.+)$", line)
            if m:
                current = m.group(1).strip()
                sections.setdefault(current, [])
            elif line.strip().startswith("- "):
                fact = line.strip()[2:].strip()
                if fact:
                    sections.setdefault(current, []).append(fact)
        return sections

    def add(self, section: str, fact: str):
        """Add a fact to a section. Creates section if needed."""
        text = self.read_all()
        section_header = f"### {section}"
        lines = text.splitlines()

        # Find or create section
        section_idx = None
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                section_idx = i
                break

        if section_idx is not None:
            # Insert after section header
            insert_at = section_idx + 1
            lines.insert(insert_at, f"- {fact}")
        else:
            # Append new section
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(section_header)
            lines.append(f"- {fact}")

        self._atomic_write("\n".join(lines) + "\n")

    def remove(self, section: str | None, query: str) -> int:
        """Remove facts matching query. If section is None, search all.
        Returns number of facts removed."""
        text = self.read_all()
        lines = text.splitlines()
        removed = 0
        result = []
        current_section = "_header"
        for line in lines:
            m = MEMORY_SECTION_RE.match(line.strip())
            if m:
                current_section = m.group(1).strip()
            stripped = line.strip()
            in_target = section is None or current_section == section
            if in_target and stripped.startswith("- ") and query.lower() in stripped.lower():
                removed += 1
                continue
            result.append(line)
        if removed:
            self._atomic_write("\n".join(result) + "\n")
        return removed

    def search(self, query: str) -> list[str]:
        """Search for facts containing query."""
        results = []
        for line in self.read_all().splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and query.lower() in stripped.lower():
                results.append(stripped[2:])
        return results

    def get_context(self) -> str:
        """Return memory content formatted for system prompt injection."""
        sections = self.get_sections()
        facts = []
        for section, items in sections.items():
            if section == "_header":
                continue
            for item in items:
                facts.append(f"- {item}")
        if not facts:
            return ""
        return "## Long-term Memory\n\n" + "\n".join(facts)

    def _atomic_write(self, content: str):
        tmp = str(self._path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
