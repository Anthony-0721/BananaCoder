"""Main system prompt builder."""
from __future__ import annotations

from pathlib import Path

SYSTEM_PROMPT = (
    "You are BananaCoder, a personal AI coding assistant. "
    "You help with software engineering tasks.\n\n"
    "When answering questions about file locations or project structure, "
    "use the available tools (glob, grep, read_file) to verify the current "
    "state rather than relying on conversation memory. "
    "The codebase may have changed during the session.\n\n"
)

FALLBACK_SYSTEM_PROMPT = "You are a helpful coding assistant."

# Section templates injected into the system prompt
WORKING_DIR_SECTION = "## Working Directory\nCurrent: {cwd}\n\n"
SKILLS_SECTION = "## Available Skills\n\n{summary}\n\n"
ALWAYS_SKILLS_SECTION = "## Always-Loaded Skills\n\n{content}\n\n"
PROJECT_STRUCTURE_SECTION = "## Project Structure\n\n```\n{tree}\n```\n\n"
CLAUDE_MD_FILENAME = "CLAUDE.md"

# Cache for CLAUDE.md content
_claude_md_cache: tuple[str, float] | None = None
_CLAUDE_CACHE_TTL = 60.0  # seconds


def _read_claude_md(root: Path) -> str:
    """Read CLAUDE.md from project root, with caching."""
    global _claude_md_cache
    import time
    now = time.time()
    if _claude_md_cache and (now - _claude_md_cache[1]) < _CLAUDE_CACHE_TTL:
        return _claude_md_cache[0]

    path = root / CLAUDE_MD_FILENAME
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
    else:
        content = ""
    _claude_md_cache = (content, now)
    return content

# Cache for project tree to avoid re-scanning on every turn
_tree_cache: dict[str, tuple[str, float]] = {}
_TREE_CACHE_TTL = 60.0  # seconds


def _build_project_tree(root: Path, max_depth: int = 3) -> str:
    """Generate an ASCII tree of the project structure up to *max_depth*."""
    import time
    root_str = str(root.resolve())
    now = time.time()

    cached = _tree_cache.get(root_str)
    if cached and (now - cached[1]) < _TREE_CACHE_TTL:
        return cached[0]

    lines: list[str] = [root.name + "/"]

    def _walk(dir_path: Path, prefix: str = "", depth: int = 0):
        if depth >= max_depth:
            return
        entries = sorted(
            [e for e in dir_path.iterdir() if e.name not in _EXCLUDE_DIRS],
            key=lambda e: (not e.is_dir(), e.name.lower()),
        )
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _walk(root)
    result = "\n".join(lines)
    _tree_cache[root_str] = (result, now)
    return result


_EXCLUDE_DIRS = frozenset({
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".venv", "venv", ".git",
})


def build_system_prompt(
    cwd: str,
    skills_summary: str = "",
    always_content: str = "",
    memory_context: str = "",
) -> str:
    """Assemble the full system prompt from parts."""
    prompt = SYSTEM_PROMPT
    prompt += WORKING_DIR_SECTION.format(cwd=cwd)

    # Project structure tree (lightweight, cached)
    tree = _build_project_tree(Path.cwd(), max_depth=3)
    if tree:
        prompt += PROJECT_STRUCTURE_SECTION.format(tree=tree)

    # Behavioral guidelines from CLAUDE.md
    claude_md = _read_claude_md(Path.cwd())
    if claude_md:
        prompt += f"## Behavioral Guidelines\n\n{claude_md}\n\n"

    if memory_context:
        prompt += memory_context + "\n\n"

    if skills_summary:
        prompt += SKILLS_SECTION.format(summary=skills_summary)

    if always_content:
        prompt += ALWAYS_SKILLS_SECTION.format(content=always_content)

    return prompt
