"""Search tools: glob and grep."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from banana.tools.base import Tool, tool_parameters

_EXCLUDED_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__",
                            ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
                            ".idea", ".vscode", ".cache"})
_BINARY_EXT = frozenset({".exe", ".dll", ".so", ".dylib", ".bin", ".png", ".jpg",
                         ".jpeg", ".gif", ".mp3", ".mp4", ".zip", ".tar", ".gz",
                         ".pdf", ".pyc", ".class", ".jar", ".ttf", ".woff"})
_MAX_FILE_SIZE = 1 * 1024 * 1024


@tool_parameters({
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')"},
    },
    "required": ["pattern"],
})
class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern."
    read_only = True

    async def execute(self, pattern: str) -> str:
        cwd = Path.cwd()
        loop = asyncio.get_running_loop()
        matches = await loop.run_in_executor(None, lambda: sorted(cwd.glob(pattern)))
        if not matches:
            return f"glob:\n[FAILED] No files matching: {pattern}"

        result_lines = []
        for p in matches[:100]:
            try:
                result_lines.append(str(p.relative_to(cwd)))
            except ValueError:
                result_lines.append(str(p))

        result = "\n".join(result_lines)
        if len(matches) > 100:
            result += f"\n... and {len(matches) - 100} more files"
        return f"glob:\n[OK] ({len(matches)} matches)\n\n{result}"


@tool_parameters({
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Regular expression pattern to search for"},
        "path": {"type": "string", "description": "File or directory path (default: current directory)"},
    },
    "required": ["pattern"],
})
class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern in files. Skips binary files and common VCS/build dirs."
    read_only = True

    async def execute(self, pattern: str, path: str = ".") -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"grep:\n[FAILED] Invalid regex: {e}"

        search_path = Path(path).expanduser().resolve()
        if not search_path.exists():
            return f"grep:\n[FAILED] Path not found: {path}"

        results = []
        files_searched = 0

        def _search_file(file_path: Path):
            nonlocal files_searched
            try:
                if file_path.stat().st_size > _MAX_FILE_SIZE:
                    return
            except OSError:
                return
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except (PermissionError, IsADirectoryError):
                return
            files_searched += 1
            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    results.append(f"{file_path}:{i}: {line.strip()[:120]}")
                    if len(results) >= 50:
                        return

        if search_path.is_file():
            _search_file(search_path)
        else:
            for p in search_path.rglob("*"):
                if len(results) >= 50:
                    break
                if not p.is_file():
                    continue
                if any(part in _EXCLUDED_DIRS for part in p.parts):
                    continue
                if p.suffix.lower() in _BINARY_EXT:
                    continue
                _search_file(p)

        if not results:
            return f"grep:\n[FAILED] No matches for '{pattern}' (searched {files_searched} files)"

        output = "\n".join(results)
        if len(results) >= 50:
            output += f"\n... (truncated, showing first 50 matches)"
        return f"grep:\n[OK] ({len(results)} matches in {files_searched} files)\n\n{output}"
