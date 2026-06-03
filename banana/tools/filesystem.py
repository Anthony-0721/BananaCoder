"""Filesystem tools: read, write, edit."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import aiofiles

from banana.tools.base import Tool, tool_parameters
from banana.tools.file_state import get_file_state
from banana.tools.path_utils import resolve_workspace_path


def _resolve_path(file_path: str, allowed_dir: Path | None = None) -> Path:
    return resolve_workspace_path(file_path, workspace=Path.cwd(), allowed_dir=allowed_dir)


# Global workspace restriction (set by build_tools from config)
_workspace_root: Path | None = None


def set_workspace_root(path: Path | None):
    global _workspace_root
    _workspace_root = path


@tool_parameters({
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file (absolute or relative)"},
    },
    "required": ["file_path"],
})
class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file's contents with line numbers. Use to inspect files."
    read_only = True

    async def execute(self, file_path: str) -> str:
        allowed = _workspace_root if _workspace_root else None
        try:
            path = _resolve_path(file_path, allowed_dir=allowed)
        except PermissionError as e:
            return f"read:\n[BLOCKED] {e}"
        if not path.exists():
            return f"read:\n[FAILED] File not found: {file_path}"
        if not path.is_file():
            return f"read:\n[FAILED] Not a file: {file_path}"

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
        except UnicodeDecodeError:
            return f"read:\n[FAILED] Binary file or unknown encoding: {file_path}"
        except Exception as e:
            return f"read:\n[FAILED] {e}"

        lines = content.split("\n")
        numbered = [f"{i+1:4d}| {line}" for i, line in enumerate(lines[:2000])]
        if len(lines) > 2000:
            numbered.append(f"... ({len(lines) - 2000} more lines)")
        get_file_state().mark_read(path)
        return f"read:\n[OK] ({len(lines)} lines)\n\n" + "\n".join(numbered)


@tool_parameters({
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to write"},
        "content": {"type": "string", "description": "Content to write to the file"},
    },
    "required": ["file_path", "content"],
})
class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file. Creates parent directories if needed."
    exclusive = True

    async def execute(self, file_path: str, content: str) -> str:
        allowed = _workspace_root if _workspace_root else None
        try:
            path = _resolve_path(file_path, allowed_dir=allowed)
        except PermissionError as e:
            return f"write:\n[BLOCKED] {e}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
            return f"write:\n[OK] Written {path} ({len(content)} chars)"
        except Exception as e:
            return f"write:\n[FAILED] {e}"


@tool_parameters({
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to edit"},
        "old_string": {"type": "string", "description": "The exact text to replace"},
        "new_string": {"type": "string", "description": "The text to replace it with"},
    },
    "required": ["file_path", "old_string", "new_string"],
})
class EditTool(Tool):
    name = "edit"
    description = "Edit a file by replacing an exact text match. The old_string must be unique in the file."
    exclusive = True

    async def execute(self, file_path: str, old_string: str, new_string: str) -> str:
        allowed = _workspace_root if _workspace_root else None
        try:
            path = _resolve_path(file_path, allowed_dir=allowed)
        except PermissionError as e:
            return f"edit:\n[BLOCKED] {e}"
        if not path.exists():
            return f"edit:\n[FAILED] File not found: {file_path}"
        if not path.is_file():
            return f"edit:\n[FAILED] Not a file: {file_path}"

        # Warn if file wasn't read first
        warn = get_file_state().check_edit(path)
        if warn:
            return warn

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
        except UnicodeDecodeError:
            return f"edit:\n[FAILED] Binary file or unknown encoding"

        count = content.count(old_string)
        if count == 0:
            return "edit:\n[FAILED] String not found in file. Check exact whitespace/indentation."
        if count > 1:
            return f"edit:\n[FAILED] String appears {count} times. Provide more context to make it unique."

        new_content = content.replace(old_string, new_string, 1)
        try:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(new_content)
        except Exception as e:
            return f"edit:\n[FAILED] {e}"

        old_lines = len(old_string.split("\n"))
        new_lines = len(new_string.split("\n"))
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=path.name, tofile=path.name,
            n=3,
        )
        diff_text = "".join(diff).strip()
        return f"edit:\n[OK] Edited {path.name}: -{old_lines}+{new_lines}\n{diff_text}"
