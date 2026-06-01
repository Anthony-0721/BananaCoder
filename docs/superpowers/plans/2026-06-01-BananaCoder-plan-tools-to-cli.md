# BananaCoder Implementation Plan (Part 2)

> Continuation from `2026-06-01-BananaCoder-plan-foundation.md`. Prerequisites: Task Groups 1-5 complete.

**Prerequisite foundation:** Config, Provider, Tool ABC/Registry, Session all pass tests.

---

## Task Group 6: Built-in Tools

### Task 10: Bash tool

**Files:**
- Create: `banana/tools/bash.py`
- Modify: `tests/test_tools.py` (add bash tests)

- [ ] **Step 1: Write banana/tools/bash.py**

```python
"""Shell execution tool."""
from __future__ import annotations

import asyncio
import os
import platform
from typing import Any

from banana.tools.base import Tool, tool_parameters

_WINDOWS = platform.system() == "Windows"


@tool_parameters({
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "The shell command to execute"},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default 120, max 600)"},
        "workdir": {"type": "string", "description": "Working directory override"},
    },
    "required": ["command"],
})
class BashTool(Tool):
    name = "bash"
    description = "Execute a shell command. On Windows: Git Bash if available, else PowerShell."
    exclusive = True

    async def execute(self, command: str, timeout: int = 120, workdir: str | None = None) -> str:
        timeout = min(max(timeout, 1), 600)
        cwd = workdir or os.getcwd()

        if _WINDOWS:
            return await self._run_windows(command, timeout, cwd)
        else:
            return await self._run_unix(command, timeout, cwd)

    async def _run_unix(self, command: str, timeout: int, cwd: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"bash:\n[FAILED] Command timed out after {timeout}s"

        out = stdout.decode("utf-8", errors="replace").rstrip()
        err = stderr.decode("utf-8", errors="replace").rstrip()

        parts = [f"[OK] Exit code: {proc.returncode}" if proc.returncode == 0
                 else f"[FAILED] Exit code: {proc.returncode}"]
        if out:
            parts.append(out)
        if err:
            parts.append(f"--- stderr ---\n{err}")
        return "bash:\n" + "\n".join(parts)

    async def _run_windows(self, command: str, timeout: int, cwd: str) -> str:
        # Try Git Bash first, then PowerShell
        git_bash = "C:\\Program Files\\Git\\bin\\bash.exe"
        if os.path.exists(git_bash):
            proc = await asyncio.create_subprocess_exec(
                git_bash, "-c", command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
            )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"bash:\n[FAILED] Command timed out after {timeout}s"

        out = stdout.decode("utf-8", errors="replace").rstrip()
        err = stderr.decode("utf-8", errors="replace").rstrip()

        parts = [f"[OK] Exit code: {proc.returncode}" if proc.returncode == 0
                 else f"[FAILED] Exit code: {proc.returncode}"]
        if out:
            parts.append(out)
        if err:
            parts.append(f"--- stderr ---\n{err}")
        return "bash:\n" + "\n".join(parts)
```

- [ ] **Step 2: Add bash tests to tests/test_tools.py**

```python
import pytest
from banana.tools.bash import BashTool


class TestBashTool:
    @pytest.mark.asyncio
    async def test_simple_echo(self):
        t = BashTool()
        result = await t.execute(command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_missing_command(self):
        t = BashTool()
        result = await t.execute(command="nonexistent_command_xyz")
        assert "FAILED" in result or "127" in result

    @pytest.mark.asyncio
    async def test_timeout(self):
        t = BashTool()
        result = await t.execute(command="sleep 10", timeout=1)
        assert "timed out" in result.lower()
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_tools.py::TestBashTool -v
```

### Task 11: Filesystem tools (read_file, write_file, edit)

**Files:**
- Create: `banana/tools/filesystem.py`
- Modify: `tests/test_tools.py` (add filesystem tests)

- [ ] **Step 1: Write banana/tools/filesystem.py**

```python
"""Filesystem tools: read, write, edit."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import aiofiles

from banana.tools.base import Tool, tool_parameters


def _resolve_path(file_path: str) -> Path:
    return Path(file_path).expanduser().resolve()


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
        path = _resolve_path(file_path)
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
        path = _resolve_path(file_path)
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
        path = _resolve_path(file_path)
        if not path.exists():
            return f"edit:\n[FAILED] File not found: {file_path}"
        if not path.is_file():
            return f"edit:\n[FAILED] Not a file: {file_path}"

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
        return f"edit:\n[OK] Edited {path.name}: replaced {old_lines} lines with {new_lines} lines"
```

- [ ] **Step 2: Add tests**

```python
class TestReadFile:
    @pytest.mark.asyncio
    async def test_read(self, temp_dir):
        f = temp_dir / "test.txt"
        f.write_text("line1\nline2\n")
        t = ReadFileTool()
        result = await t.execute(file_path=str(f))
        assert "line1" in result
        assert "line2" in result

    @pytest.mark.asyncio
    async def test_not_found(self, temp_dir):
        t = ReadFileTool()
        result = await t.execute(file_path=str(temp_dir / "nonexistent.txt"))
        assert "FAILED" in result


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write(self, temp_dir):
        f = temp_dir / "out.txt"
        t = WriteFileTool()
        result = await t.execute(file_path=str(f), content="hello world")
        assert "[OK]" in result
        assert f.read_text() == "hello world"


class TestEdit:
    @pytest.mark.asyncio
    async def test_edit_single_match(self, temp_dir):
        f = temp_dir / "code.py"
        f.write_text("x = 1\n")
        t = EditTool()
        result = await t.execute(file_path=str(f), old_string="x = 1", new_string="x = 2")
        assert "[OK]" in result
        assert f.read_text() == "x = 2\n"

    @pytest.mark.asyncio
    async def test_edit_multiple_matches(self, temp_dir):
        f = temp_dir / "code.py"
        f.write_text("x = 1\nx = 1\n")
        t = EditTool()
        result = await t.execute(file_path=str(f), old_string="x = 1", new_string="x = 2")
        assert "appears 2 times" in result
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_tools.py -v -k "TestReadFile or TestWriteFile or TestEdit"
```

### Task 12: Search tools (glob, grep)

**Files:**
- Create: `banana/tools/search.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write banana/tools/search.py**

```python
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
        matches = sorted(cwd.glob(pattern))
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
```

- [ ] **Step 2: Add tests and run**

```bash
cd e:/BananaCoder && python -m pytest tests/test_tools.py -v -k "TestGlob or TestGrep"
```

### Task 13: Web tools + remaining tools (web_search, web_fetch, ask_user, todo_write, load_skill)

**Files:**
- Create: `banana/tools/web.py`
- Create: `banana/tools/ask.py`
- Create: `banana/tools/todo.py`
- Create: `banana/tools/skill_tool.py`
- Create: `banana/tools/agent_tool.py` (placeholder, wired in Task 17)

- [ ] **Step 1: Write banana/tools/web.py**

```python
"""Web tools: search and fetch."""
from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import httpx
from banana.tools.base import Tool, tool_parameters

FETCH_TIMEOUT = 60.0
MAX_URL_LENGTH = 2000
MAX_MARKDOWN_LENGTH = 100_000


def _html_to_markdown(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@tool_parameters({
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Max results (default: 5)"},
    },
    "required": ["query"],
})
class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web. Requires TAVILY_API_KEY env var."
    read_only = True

    async def execute(self, query: str, max_results: int = 5) -> str:
        import os
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return "web_search:\n[FAILED] TAVILY_API_KEY not set. Configure it in your environment."

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            result = await __import__("asyncio").to_thread(
                client.search, query, max_results=max_results,
            )
            lines = []
            for r in result.get("results", []):
                lines.append(f"- [{r.get('title', 'No title')}]({r.get('url', '')}): {r.get('content', '')[:200]}")
            return f"web_search:\n[OK] ({len(lines)} results)\n\n" + "\n".join(lines)
        except ImportError:
            return "web_search:\n[FAILED] Install 'tavily-python' to use web search."
        except Exception as e:
            return f"web_search:\n[FAILED] {e}"


@tool_parameters({
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to fetch"},
    },
    "required": ["url"],
})
class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch and convert a web page to text."
    read_only = True

    async def execute(self, url: str) -> str:
        if len(url) > MAX_URL_LENGTH:
            return f"web_fetch:\n[FAILED] URL exceeds {MAX_URL_LENGTH} chars"

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return f"web_fetch:\n[FAILED] Invalid URL: {url}"
        if parsed.scheme == "http":
            url = url.replace("http://", "https://", 1)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=FETCH_TIMEOUT, max_redirects=10,
                headers={"User-Agent": "BananaCoder/1.0"},
            ) as client:
                resp = await client.get(url)
        except httpx.TimeoutException:
            return f"web_fetch:\n[FAILED] Timeout after {FETCH_TIMEOUT}s"
        except Exception as e:
            return f"web_fetch:\n[FAILED] {e}"

        content_type = resp.headers.get("content-type", "")
        if any(t in content_type.lower() for t in ("image/", "video/", "audio/", "application/pdf")):
            return f"web_fetch:\n[FAILED] Binary content ({content_type}), cannot extract text."

        text = _html_to_markdown(resp.text) if "text/html" in content_type else resp.text
        if len(text) > MAX_MARKDOWN_LENGTH:
            text = text[:MAX_MARKDOWN_LENGTH] + "\n\n[Content truncated...]"
        return f"web_fetch:\n[OK] ({resp.status_code}, {len(text)} chars)\n\n{text}"
```

- [ ] **Step 2: Write banana/tools/ask.py**

```python
"""Interactive user prompt tool."""
from __future__ import annotations

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
            answer = await __import__("asyncio").to_thread(
                lambda: Prompt.ask(">", default="")
            )
        else:
            answer = await __import__("asyncio").to_thread(
                lambda: Prompt.ask(">", default="")
            )

        return f"user_answer:\n{answer or '(no response)'}"
```

- [ ] **Step 3: Write banana/tools/todo.py**

```python
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
```

- [ ] **Step 4: Write banana/tools/skill_tool.py**

```python
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
```

- [ ] **Step 5: Put placeholder for agent_tool (wired fully in Task 17)**

```python
# banana/tools/agent_tool.py
"""Placeholder — wired when SubagentManager is ready."""

from banana.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Task description for the sub-agent"},
        "subagent_type": {"type": "string", "description": "Type: Explore, Plan, or general-purpose"},
        "description": {"type": "string", "description": "Short description (for display)"},
        "timeout_seconds": {"type": "integer", "description": "Max seconds (default 300)"},
    },
    "required": ["prompt", "subagent_type"],
})
class AgentTool(Tool):
    name = "agent"
    description = "Launch a sub-agent to perform a task autonomously."
    exclusive = True

    def __init__(self, subagent_manager=None):
        super().__init__()
        self._manager = subagent_manager

    def set_manager(self, manager):
        self._manager = manager

    async def execute(self, prompt: str, subagent_type: str = "Explore",
                      description: str = "", timeout_seconds: int = 300) -> str:
        if not self._manager:
            return "agent:\n[FAILED] Subagent system not initialized."
        return await self._manager.run_subagent(
            prompt=prompt, agent_type=subagent_type, timeout=timeout_seconds,
        )
```

- [ ] **Step 6: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_tools.py -v
```

---

## Task Group 7: MCP Integration

### Task 14: MCP client

**Files:**
- Create: `banana/tools/mcp.py`
- Create: `tests/test_mcp.py`

- [ ] **Step 1: Write banana/tools/mcp.py**

```python
"""MCP client: connect to MCP servers and register their tools/resources/prompts."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import urllib.parse
from contextlib import AsyncExitStack, suppress
from typing import Any

import httpx
from loguru import logger

from banana.tools.base import Tool
from banana.tools.registry import ToolRegistry

_TRANSIENT_EXC_NAMES: frozenset[str] = frozenset((
    "ClosedResourceError", "BrokenResourceError", "EndOfStream",
    "BrokenPipeError", "ConnectionResetError", "ConnectionRefusedError",
    "ConnectionAbortedError", "ConnectionError",
))
_WINDOWS_SHELL_LAUNCHERS: frozenset[str] = frozenset(("npx", "npm", "pnpm", "yarn", "bunx"))
_SANITIZE_RE = re.compile(r"_+")


def _sanitize_name(name: str) -> str:
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))


def _is_transient(exc: BaseException) -> bool:
    return type(exc).__name__ in _TRANSIENT_EXC_NAMES


def _windows_command_basename(command: str) -> str:
    return command.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()


def _normalize_windows_stdio_command(command: str, args: list[str] | None,
                                     env: dict[str, str] | None) -> tuple[str, list[str], dict[str, str] | None]:
    normalized_args = list(args or [])
    if os.name != "nt":
        return command, normalized_args, env
    basename = _windows_command_basename(command)
    if basename in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return command, normalized_args, env
    if basename.endswith((".exe", ".com")):
        return command, normalized_args, env
    resolved = shutil.which(command, path=(env or {}).get("PATH")) or command
    resolved_basename = _windows_command_basename(resolved)
    should_wrap = basename in _WINDOWS_SHELL_LAUNCHERS or basename.endswith((".cmd", ".bat")) or resolved_basename.endswith((".cmd", ".bat"))
    if not should_wrap:
        return command, normalized_args, env
    comspec = (env or {}).get("COMSPEC") or os.environ.get("COMSPEC") or "cmd.exe"
    return comspec, ["/d", "/c", command, *normalized_args], env


async def _probe_http_url(url: str, timeout: float = 3.0) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if not port:
        port = 443 if parsed.scheme == "https" else 80
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def _normalize_schema_for_openai(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    raw_type = normalized.get("type")
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item != "null"]
        if "null" in raw_type and len(non_null) == 1:
            normalized["type"] = non_null[0]
            normalized["nullable"] = True
    if "properties" in normalized and isinstance(normalized["properties"], dict):
        normalized["properties"] = {
            name: _normalize_schema_for_openai(prop) if isinstance(prop, dict) else prop
            for name, prop in normalized["properties"].items()
        }
    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = _normalize_schema_for_openai(normalized["items"])
    if normalized.get("type") != "object":
        return normalized
    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])
    return normalized


class MCPToolWrapper(Tool):
    _plugin_discoverable = False

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_{tool_def.name}")
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(self._original_name, arguments=kwargs),
                    timeout=self._tool_timeout,
                )
            except asyncio.TimeoutError:
                return f"(MCP tool '{self._name}' timed out after {self._tool_timeout}s)"
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling() > 0:
                    raise
                return f"(MCP tool '{self._name}' was cancelled)"
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP tool '{self._name}' failed: {type(exc).__name__})"
            else:
                parts = []
                for block in result.content:
                    if isinstance(block, types.TextContent):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                return "\n".join(parts) or "(no output)"
        return "(MCP tool call failed)"


class MCPResourceWrapper(Tool):
    _plugin_discoverable = False
    read_only: bool = True

    def __init__(self, session, server_name: str, resource_def, resource_timeout: int = 30):
        self._session = session
        self._uri = resource_def.uri
        self._name = _sanitize_name(f"mcp_{server_name}_resource_{resource_def.name}")
        desc = resource_def.description or resource_def.name
        self._description = f"[MCP Resource] {desc}\nURI: {self._uri}"
        self._parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        self._resource_timeout = resource_timeout

    @property
    def name(self) -> str: return self._name

    @property
    def description(self) -> str: return self._description

    @property
    def parameters(self) -> dict[str, Any]: return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.read_resource(self._uri),
                    timeout=self._resource_timeout,
                )
            except asyncio.TimeoutError:
                return f"(MCP resource timed out)"
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP resource failed: {type(exc).__name__})"
            else:
                parts = []
                for block in result.contents:
                    if isinstance(block, types.TextResourceContents):
                        parts.append(block.text)
                    else:
                        parts.append(f"[Binary: {len(getattr(block, 'blob', b''))} bytes]")
                return "\n".join(parts) or "(no output)"
        return "(MCP resource failed)"


async def connect_mcp_servers(mcp_servers: dict, registry: ToolRegistry) -> dict[str, AsyncExitStack]:
    """Connect to configured MCP servers and register their tools/resources/prompts."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    async def connect_single_server(name: str, cfg) -> tuple[str, AsyncExitStack | None]:
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        try:
            transport_type = cfg.get("type", "")
            if not transport_type:
                if cfg.get("command"):
                    transport_type = "stdio"
                elif cfg.get("url"):
                    transport_type = "sse" if cfg["url"].rstrip("/").endswith("/sse") else "streamableHttp"
                else:
                    logger.warning(f"MCP server '{name}': no command or url, skipping")
                    await server_stack.aclose()
                    return name, None

            if transport_type == "stdio":
                command, args, env = _normalize_windows_stdio_command(
                    cfg["command"], cfg.get("args"), cfg.get("env"),
                )
                params = StdioServerParameters(command=command, args=args, env=env)
                read, write = await server_stack.enter_async_context(stdio_client(params))
            elif transport_type == "sse":
                if not await _probe_http_url(cfg["url"]):
                    logger.warning(f"MCP server '{name}': unreachable, skipping")
                    await server_stack.aclose()
                    return name, None
                read, write = await server_stack.enter_async_context(sse_client(cfg["url"]))
            elif transport_type == "streamableHttp":
                if not await _probe_http_url(cfg["url"]):
                    logger.warning(f"MCP server '{name}': unreachable, skipping")
                    await server_stack.aclose()
                    return name, None
                http_client = await server_stack.enter_async_context(
                    httpx.AsyncClient(headers=cfg.get("headers"), follow_redirects=True, timeout=None))
                read, write, _ = await server_stack.enter_async_context(
                    streamable_http_client(cfg["url"], http_client=http_client))
            else:
                logger.warning(f"MCP server '{name}': unknown transport '{transport_type}'")
                await server_stack.aclose()
                return name, None

            session = await server_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            enabled_tools = set(cfg.get("enabled_tools", ["*"]))
            allow_all = "*" in enabled_tools
            tool_timeout = cfg.get("tool_timeout", 30)

            tools_result = await session.list_tools()
            for tool_def in tools_result.tools:
                wrapped_name = _sanitize_name(f"mcp_{name}_{tool_def.name}")
                if not allow_all and tool_def.name not in enabled_tools and wrapped_name not in enabled_tools:
                    continue
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=tool_timeout)
                registry.register(wrapper)
                logger.debug(f"MCP: registered tool '{wrapper.name}' from '{name}'")

            with suppress(Exception):
                resources = await session.list_resources()
                for res in resources.resources:
                    registry.register(MCPResourceWrapper(session, name, res, resource_timeout=tool_timeout))

            with suppress(Exception):
                prompts = await session.list_prompts()
                for prompt in prompts.prompts:
                    from banana.tools.mcp import MCPPromptWrapper
                    registry.register(MCPPromptWrapper(session, name, prompt, prompt_timeout=tool_timeout))

            return name, server_stack
        except Exception as e:
            logger.warning(f"MCP server '{name}': connection failed: {e}")
            with suppress(Exception):
                await server_stack.aclose()
            return name, None

    server_stacks: dict[str, AsyncExitStack] = {}
    for name, cfg in mcp_servers.items():
        result = await connect_single_server(name, cfg)
        if result is not None and result[1] is not None:
            server_stacks[result[0]] = result[1]
    return server_stacks


class MCPPromptWrapper(Tool):
    _plugin_discoverable = False
    read_only = True

    def __init__(self, session, server_name: str, prompt_def, prompt_timeout: int = 30):
        self._session = session
        self._prompt_name = prompt_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_prompt_{prompt_def.name}")
        desc = prompt_def.description or prompt_def.name
        self._description = f"[MCP Prompt] {desc}"
        self._prompt_timeout = prompt_timeout
        properties = {}
        required = []
        for arg in prompt_def.arguments or []:
            properties[arg.name] = {"type": "string", "description": getattr(arg, "description", "") or ""}
            if arg.required:
                required.append(arg.name)
        self._parameters = {"type": "object", "properties": properties, "required": required}

    @property
    def name(self) -> str: return self._name

    @property
    def description(self) -> str: return self._description

    @property
    def parameters(self) -> dict[str, Any]: return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types
        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.get_prompt(self._prompt_name, arguments=kwargs),
                    timeout=self._prompt_timeout,
                )
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP prompt failed: {type(exc).__name__})"
            else:
                parts = []
                for msg in result.messages:
                    content = msg.content
                    if isinstance(content, types.TextContent):
                        parts.append(content.text)
                    else:
                        parts.append(str(content))
                return "\n".join(parts) or "(no output)"
        return "(MCP prompt failed)"
```

- [ ] **Step 2: Write mcp tests**

```python
# tests/test_mcp.py
import pytest
from banana.tools.mcp import _sanitize_name, _normalize_schema_for_openai


class TestSanitizeName:
    def test_simple(self):
        assert _sanitize_name("hello_world") == "hello_world"

    def test_dots(self):
        assert _sanitize_name("my.tool.name") == "my_tool_name"

    def test_special_chars(self):
        assert _sanitize_name("tool@#$name") == "tool___name"


class TestSchemaNormalize:
    def test_nullable_type(self):
        result = _normalize_schema_for_openai({"type": ["string", "null"]})
        assert result["type"] == "string"
        assert result["nullable"] is True

    def test_nested_properties(self):
        result = _normalize_schema_for_openai({
            "type": "object",
            "properties": {"x": {"type": ["integer", "null"]}},
        })
        assert result["properties"]["x"]["type"] == "integer"
        assert result["properties"]["x"]["nullable"] is True
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_mcp.py -v
```

---

## Task Group 8: Skills

### Task 15: Skills loader

**Files:**
- Create: `banana/skills/loader.py`
- Create: `tests/test_skills_loader.py`

- [ ] **Step 1: Write banana/skills/loader.py**

```python
"""Skills loader for agent capabilities."""
from __future__ import annotations

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
        content = self.load_skill(name)
        # re-read with frontmatter
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
            import json
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
```

- [ ] **Step 2: Write tests**

```python
# tests/test_skills_loader.py
import pytest
from banana.skills.loader import SkillsLoader


@pytest.fixture
def skill_dirs(temp_home):
    ws = temp_home / "workspace"
    ws.mkdir()
    skill_dir = ws / ".banana" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Does X when user needs it
always: true
---
# My Skill
Do the thing.
""")
    return ws


class TestSkillsLoader:
    def test_list_skills(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        skills = loader.list_skills(filter_unavailable=False)
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"

    def test_load_skill(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        content = loader.load_skill("my-skill")
        assert "# My Skill" in content
        assert "---" not in content

    def test_get_always_skills(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        always = loader.get_always_skills()
        assert "my-skill" in always

    def test_build_summary(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        summary = loader.build_skills_summary()
        assert "my-skill" in summary
        assert "Does X" in summary

    def test_load_nonexistent(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        assert loader.load_skill("nope") is None
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_skills_loader.py -v
```

---

## Task Group 9: Agent Layer

### Task 16: Context manager

**Files:**
- Create: `banana/agent/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write banana/agent/context.py**

```python
"""3-layer context compression."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider


def _approx_tokens(text: str) -> int:
    return len(text) // 3


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += _approx_tokens(content)
        tool_calls = m.get("tool_calls")
        if tool_calls:
            total += _approx_tokens(str(tool_calls))
    return total


class ContextManager:
    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        self._snip_at = int(max_tokens * 0.50)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    async def compress(self, messages: list[dict], provider: "LLMProvider | None" = None) -> bool:
        current = estimate_tokens(messages)
        compressed = False

        if current > self._snip_at:
            if self._snip_tool_outputs(messages):
                compressed = True
                current = estimate_tokens(messages)

        if current > self._summarize_at and len(messages) > 10:
            if await self._summarize(messages, provider, keep_recent=8):
                compressed = True
                current = estimate_tokens(messages)

        if current > self._collapse_at and len(messages) > 4:
            await self._hard_collapse(messages, provider)
            compressed = True

        return compressed

    @staticmethod
    def _snip_tool_outputs(messages: list[dict]) -> bool:
        changed = False
        for m in messages:
            if m.get("role") != "tool":
                continue
            content = m.get("content", "")
            if not isinstance(content, str) or len(content) <= 1500:
                continue
            lines = content.splitlines()
            if len(lines) <= 6:
                continue
            m["content"] = (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines snipped) ...\n"
                + "\n".join(lines[-3:])
            )
            changed = True
        return changed

    async def _summarize(self, messages: list[dict], provider, keep_recent: int = 8) -> bool:
        if len(messages) <= keep_recent:
            return False
        old = messages[:-keep_recent]
        summary = await self._get_summary(old, provider)
        messages.clear()
        messages.append({"role": "user", "content": f"[Context compressed]\n{summary}"})
        messages.append({"role": "assistant", "content": "Got it, I have the prior context."})
        messages.extend(messages[-keep_recent:] if len(old) > keep_recent else old[-keep_recent:])
        return True

    async def _hard_collapse(self, messages: list[dict], provider):
        tail = messages[-4:] if len(messages) > 4 else messages[-2:]
        summary = await self._get_summary(messages[:-len(tail)], provider)
        messages.clear()
        messages.append({"role": "user", "content": f"[Hard reset]\n{summary}"})
        messages.append({"role": "assistant", "content": "Context restored. Continuing."})
        messages.extend(tail)

    async def _get_summary(self, messages: list[dict], provider) -> str:
        flat = "\n".join(
            f"[{m.get('role', '?')}] {str(m.get('content', ''))[:300]}"
            for m in messages
        )
        if provider:
            try:
                resp = await provider.chat(
                    messages=[
                        {"role": "system", "content": (
                            "Compress this conversation into a brief summary. "
                            "Preserve: file paths edited, key decisions, errors encountered."
                        )},
                        {"role": "user", "content": flat[:12000]},
                    ],
                )
                return resp.content or "(summary unavailable)"
            except Exception:
                pass
        return self._extract_key_info(messages)

    @staticmethod
    def _extract_key_info(messages: list[dict]) -> str:
        import re
        files_seen = set()
        for m in messages:
            text = m.get("content", "")
            if isinstance(text, str):
                for match in re.finditer(r'[\w./\-]+\.\w{1,5}', text):
                    files_seen.add(match.group())
        parts = []
        if files_seen:
            parts.append(f"Files: {', '.join(sorted(files_seen)[:20])}")
        return "\n".join(parts) or "(no extractable context)"
```

- [ ] **Step 2: Write tests**

```python
# tests/test_context.py
from banana.agent.context import ContextManager, estimate_tokens


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens([]) == 0

    def test_simple(self):
        msgs = [{"role": "user", "content": "hello world" * 100}]
        assert estimate_tokens(msgs) > 0


class TestContextManager:
    def test_snip_tool_outputs(self):
        msgs = [
            {"role": "tool", "content": "short"},
            {"role": "tool", "content": "line1\nline2\nline3\n" + ("x" * 2000)},
        ]
        changed = ContextManager._snip_tool_outputs(msgs)
        assert changed is True
        assert "snipped" in msgs[1]["content"]

    def test_no_snip_short(self):
        msgs = [{"role": "tool", "content": "short"}]
        changed = ContextManager._snip_tool_outputs(msgs)
        assert changed is False
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_context.py -v
```

### Task 17: Agent runner + subagent

**Files:**
- Create: `banana/agent/runner.py`
- Create: `banana/agent/subagent.py`
- Create: `tests/test_agent_runner.py`

- [ ] **Step 1: Write banana/agent/subagent.py**

```python
"""Sub-agent manager."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider
    from banana.tools.registry import ToolRegistry


@dataclass
class AgentDefinition:
    description: str
    tools: list[str] | None = None
    read_only: bool = False
    system_prompt: str = ""

    @property
    def allowed_tools(self) -> set[str] | None:
        return set(self.tools) if self.tools is not None else None


AGENT_DEFINITIONS = {
    "Explore": AgentDefinition(
        description="Read-only codebase exploration",
        tools=["read_file", "glob", "grep", "web_search", "web_fetch", "load_skill"],
        read_only=True,
        system_prompt="You are a code exploration assistant. Explore the codebase and report findings.",
    ),
    "Plan": AgentDefinition(
        description="Design implementation plans",
        tools=["read_file", "glob", "grep"],
        read_only=True,
        system_prompt="You are a software architecture assistant. Design plans and analyze trade-offs.",
    ),
    "general-purpose": AgentDefinition(
        description="Full-capability sub-agent",
        tools=None,
        read_only=False,
        system_prompt="You are a general-purpose coding assistant. Complete the given task autonomously.",
    ),
}


class SubagentManager:
    def __init__(self, provider: "LLMProvider", tools: "ToolRegistry", sub_agent=None):
        self.provider = provider
        self.tools = tools
        self._create_runner = sub_agent

    def _filter_tools(self, definition: AgentDefinition) -> "ToolRegistry":
        if definition.tools is None:
            return self.tools
        from banana.tools.registry import ToolRegistry
        filtered = ToolRegistry()
        for tool_name in definition.tools:
            tool = self.tools.get(tool_name)
            if tool:
                filtered.register(tool)
        return filtered

    async def run_subagent(self, prompt: str, agent_type: str = "Explore",
                           timeout: int = 300) -> str:
        definition = AGENT_DEFINITIONS.get(agent_type)
        if not definition:
            return f"Unknown agent type '{agent_type}'. Available: {', '.join(AGENT_DEFINITIONS)}"

        sub_tools = self._filter_tools(definition)

        from banana.agent.runner import AgentRunner
        runner = AgentRunner(
            provider=self.provider,
            tools=sub_tools,
            subagent_manager=None,
            system_prompt_override=definition.system_prompt,
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            result = await asyncio.wait_for(
                runner.run(messages),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            return f"Sub-agent timed out after {timeout}s"
```

- [ ] **Step 2: Write banana/agent/runner.py**

```python
"""AgentRunner: executes LLM <-> Tools loop."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from banana.providers.base import LLMProvider, LLMResponse
from banana.agent.context import ContextManager
from banana.tools.registry import ToolRegistry


class AgentRunner:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry,
        subagent_manager=None,
        system_prompt_override: str | None = None,
        max_rounds: int = 50,
        max_tool_result_chars: int = 80000,
        context_window_tokens: int = 128_000,
    ):
        self.provider = provider
        self.tools = tools
        self.subagent_manager = subagent_manager
        self.system_prompt_override = system_prompt_override
        self.max_rounds = max_rounds
        self.max_tool_result_chars = max_tool_result_chars
        self.context = ContextManager(max_tokens=context_window_tokens)

    async def run(
        self, messages: list[dict[str, Any]],
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_tool: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> str:
        system_msg = self.system_prompt_override or "You are a helpful coding assistant."

        for _ in range(self.max_rounds):
            await self.context.compress(messages, self.provider)
            full = [{"role": "system", "content": system_msg}] + messages

            response = await self.provider.chat_stream_with_retry(
                messages=full,
                tools=self.tools.get_definitions() if len(self.tools) > 0 else None,
                on_content_delta=on_token,
            )

            if response.finish_reason == "error":
                messages.append({"role": "assistant", "content": response.content or "Model error"})
                return response.content or "Model error"

            if not response.content and not response.tool_calls:
                messages.append({"role": "user", "content": "(continue)"})
                continue

            messages.append(self._build_assistant_message(response))

            if not response.tool_calls:
                return response.content or ""

            tool_results = await self._execute_tools(response.tool_calls, on_tool)
            for tc, result in zip(response.tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": self._truncate_result(result),
                })

        return "(reached maximum tool-call rounds)"

    async def _execute_tools(self, tool_calls, on_tool=None) -> list[str]:
        parallel_calls = []
        serial_calls = []
        for tc in tool_calls:
            tool = self.tools.get(tc.name)
            if tool and tool.concurrency_safe:
                parallel_calls.append(tc)
            else:
                serial_calls.append(tc)

        results: list[tuple[int, str]] = []

        if parallel_calls:
            if on_tool:
                for tc in parallel_calls:
                    await on_tool(tc.name, tc.arguments)
            parallel_results = await asyncio.gather(
                *(self.tools.execute(tc.name, tc.arguments) for tc in parallel_calls),
                return_exceptions=True,
            )
            for tc, r in zip(parallel_calls, parallel_results):
                results.append((tool_calls.index(tc), str(r) if not isinstance(r, Exception) else f"Error: {r}"))

        for tc in serial_calls:
            idx = tool_calls.index(tc)
            if on_tool:
                await on_tool(tc.name, tc.arguments)
            r = await self.tools.execute(tc.name, tc.arguments)
            results.append((idx, str(r)))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    def _build_assistant_message(self, response: LLMResponse) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": response.content or None}
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ]
        return msg

    def _truncate_result(self, result: str) -> str:
        if len(result) <= self.max_tool_result_chars:
            return result
        return result[:self.max_tool_result_chars] + f"\n\n... (truncated, {len(result)} chars total)"
```

- [ ] **Step 3: Write tests**

```python
# tests/test_agent_runner.py
import pytest
from banana.providers.base import LLMResponse
from banana.agent.runner import AgentRunner
from banana.tools.registry import ToolRegistry
from banana.tools.base import Tool


class FakeProvider:
    """Minimal fake that responds once then stops."""
    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self._idx = 0

    async def chat_stream_with_retry(self, messages, tools, on_content_delta=None, **kwargs):
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            if on_content_delta and resp.content:
                await on_content_delta(resp.content)
            return resp
        return LLMResponse(content="done")


class EchoTool(Tool):
    name = "echo"
    description = "Echo back"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    concurrency_safe = True

    async def execute(self, text: str) -> str:
        return f"echo: {text}"


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        p = FakeProvider([LLMResponse(content="Hello!")])
        r = ToolRegistry()
        runner = AgentRunner(p, r)
        messages = [{"role": "user", "content": "hi"}]
        result = await runner.run(messages)
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_loop(self):
        p = FakeProvider([
            LLMResponse(content=None, tool_calls=[], finish_reason="tool_calls"),  # will be skipped
        ])
        # Actually need a proper tool call test:
        from banana.providers.base import ToolCallRequest
        p2 = FakeProvider([
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="echo", arguments={"text": "hi"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Got your echo!"),
        ])
        r = ToolRegistry()
        r.register(EchoTool())
        runner = AgentRunner(p2, r)
        messages = [{"role": "user", "content": "echo hi"}]
        result = await runner.run(messages)
        assert result == "Got your echo!"
        assert any(m["role"] == "tool" and "echo: hi" in str(m["content"]) for m in messages)

    @pytest.mark.asyncio
    async def test_max_rounds(self):
        from banana.providers.base import ToolCallRequest
        p = FakeProvider([
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id=f"c{i}", name="echo", arguments={"text": str(i)})],
                finish_reason="tool_calls",
            ) for i in range(100)
        ])
        r = ToolRegistry()
        r.register(EchoTool())
        runner = AgentRunner(p, r, max_rounds=3)
        messages = [{"role": "user", "content": "loop"}]
        result = await runner.run(messages)
        assert "maximum" in result
```

- [ ] **Step 4: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_agent_runner.py -v
```

### Task 18: Agent main loop

**Files:**
- Create: `banana/agent/loop.py`

- [ ] **Step 1: Complete banana/agent/loop.py**

```python
"""Main Agent orchestrator."""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from banana.agent.runner import AgentRunner
from banana.agent.subagent import SubagentManager
from banana.providers.base import LLMProvider
from banana.session.manager import SessionManager
from banana.skills.loader import SkillsLoader
from banana.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry,
        session_mgr: SessionManager, skills_loader: SkillsLoader,
        max_rounds: int = 50, max_tool_chars: int = 80000,
        context_window_tokens: int = 128_000,
    ):
        self.provider = provider
        self.tools = tools
        self.session_mgr = session_mgr
        self.skills_loader = skills_loader
        self.max_rounds = max_rounds
        self.max_tool_chars = max_tool_chars
        self.context_window_tokens = context_window_tokens

    async def chat(
        self, user_input: str,
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_tool: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> str:
        session = await self.session_mgr.load()
        session.messages.append({"role": "user", "content": user_input})

        # Build system prompt with skills
        system_prompt = self._build_system_prompt()

        subagent_mgr = SubagentManager(self.provider, self.tools)

        # Wire up agent_tool
        agent_tool = self.tools.get("agent")
        if agent_tool:
            agent_tool.set_manager(subagent_mgr)

        runner = AgentRunner(
            provider=self.provider, tools=self.tools,
            subagent_manager=subagent_mgr,
            system_prompt_override=system_prompt,
            max_rounds=self.max_rounds,
            max_tool_result_chars=self.max_tool_chars,
            context_window_tokens=self.context_window_tokens,
        )

        result = await runner.run(
            session.messages,
            on_token=on_token,
            on_tool=on_tool,
        )

        await self.session_mgr.save(session)
        return result

    def _build_system_prompt(self) -> str:
        skills_summary = self.skills_loader.build_skills_summary()
        always_skills = self.skills_loader.get_always_skills()
        always_content = self.skills_loader.load_skills_for_context(always_skills) if always_skills else ""

        prompt = "You are BananaCoder, a personal AI coding assistant. You help with software engineering tasks.\n\n"
        prompt += "## Working Directory\n"
        prompt += f"Current: {Path.cwd()}\n\n"

        if skills_summary:
            prompt += "## Available Skills\n\n"
            prompt += skills_summary + "\n\n"

        if always_content:
            prompt += "## Always-Loaded Skills\n\n"
            prompt += always_content + "\n\n"

        return prompt
```

---

## Task Group 10: CLI Layer

### Task 19: Display + CLI app

**Files:**
- Create: `banana/cli/display.py`
- Create: `banana/cli/app.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write banana/cli/display.py**

```python
"""Rich display helpers for streaming output."""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text
from rich.live import Live
from rich.panel import Panel

console = Console()


class Display:
    def __init__(self):
        self._tool_count = 0
        self._current_text = ""

    async def on_token(self, token: str):
        console.print(token, end="", highlight=False)

    async def on_tool(self, name: str, args: dict):
        self._tool_count += 1
        summary = self._tool_summary(name, args)
        console.print(Text(f"\n  [{name}] {summary}", style="dim cyan"))

    async def on_tool_result(self, name: str, truncated: bool = False):
        if truncated:
            console.print(Text(f"  [{name}] ✓ (truncated)", style="dim green"))

    def _tool_summary(self, name: str, args: dict) -> str:
        key_map = {
            "bash": "command", "read_file": "file_path", "write_file": "file_path",
            "edit": "file_path", "grep": "pattern", "glob": "pattern",
            "web_search": "query", "web_fetch": "url",
            "agent": "subagent_type", "load_skill": "skill_name",
        }
        key = key_map.get(name, "")
        if key and key in args:
            return str(args[key])[:80]
        if args:
            first_val = list(args.values())[0] if args else ""
            return str(first_val)[:80]
        return ""

    def print_welcome(self, model: str, session_id: str):
        console.print(Panel(
            f"[bold]BananaCoder[/] v0.1.0\n"
            f"Session: {session_id}  Model: {model}\n"
            f"Type /help for commands, exit to quit",
            title="Welcome",
            border_style="green",
        ))

    def print_goodbye(self):
        console.print(Text("\nGoodbye! 🍌", style="bold yellow"))
```

- [ ] **Step 2: Write banana/cli/app.py**

```python
"""CLI application entry point."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from banana.config.loader import load_config, resolve_env_vars
from banana.config.schema import Config
from banana.providers.factory import make_provider
from banana.tools.registry import ToolRegistry
from banana.tools.bash import BashTool
from banana.tools.filesystem import ReadFileTool, WriteFileTool, EditTool
from banana.tools.search import GlobTool, GrepTool
from banana.tools.web import WebSearchTool, WebFetchTool
from banana.tools.agent_tool import AgentTool
from banana.tools.ask import AskUserTool
from banana.tools.todo import TodoWriteTool
from banana.tools.skill_tool import LoadSkillTool
from banana.tools.mcp import connect_mcp_servers
from banana.session.manager import SessionManager
from banana.skills.loader import SkillsLoader
from banana.agent.loop import Agent
from banana.cli.display import Display, console


def build_tools(config: Config, skills_loader: SkillsLoader) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    registry.register(AgentTool())  # wired later
    registry.register(AskUserTool())
    registry.register(TodoWriteTool())
    skill_tool = LoadSkillTool()
    skill_tool.set_loader(skills_loader)
    registry.register(skill_tool)
    return registry


async def _run_single(config: Config, args):
    """Single-shot execution mode."""
    display = Display()
    skills_loader = SkillsLoader(Path.cwd())

    registry = build_tools(config, skills_loader)
    provider = make_provider(config)

    session_mgr = SessionManager(
        Path(config._data_dir or Path.home() / ".bananacoder"),
        Path.cwd(),
    )
    if args.session:
        await session_mgr.switch(args.session)

    # Connect MCP servers
    mcp_stacks = await connect_mcp_servers(
        {k: v.model_dump() for k, v in config.mcp_servers.items()},
        registry,
    )

    try:
        agent = Agent(provider, registry, session_mgr, skills_loader,
                      max_rounds=config.agent.max_tool_rounds,
                      max_tool_chars=config.agent.max_tool_result_chars)
        result = await agent.chat(
            args.prompt,
            on_token=display.on_token,
            on_tool=display.on_tool,
        )
        console.print(f"\n{result}")
    finally:
        for stack in mcp_stacks.values():
            await stack.aclose()


async def _run_interactive(config: Config, args):
    """Interactive REPL mode."""
    display = Display()
    skills_loader = SkillsLoader(Path.cwd())

    registry = build_tools(config, skills_loader)
    provider = make_provider(config)

    data_dir = Path.home() / ".bananacoder"
    session_mgr = SessionManager(data_dir, Path.cwd())

    mcp_stacks = await connect_mcp_servers(
        {k: v.model_dump() for k, v in config.mcp_servers.items()},
        registry,
    )

    agent = Agent(provider, registry, session_mgr, skills_loader,
                  max_rounds=config.agent.max_tool_rounds,
                  max_tool_chars=config.agent.max_tool_result_chars)

    default_preset = config.model_presets.get("default")
    model_name = default_preset.model if default_preset else "unknown"
    session = await session_mgr.load()
    display.print_welcome(model_name, session.id)

    bindings = KeyBindings()

    @bindings.add("c-c")
    def _(event):
        console.print("\n[yellow]Interrupted[/yellow]")

    prompt_session = PromptSession(
        history=FileHistory(str(data_dir / ".history")),
        key_bindings=bindings,
        style=Style.from_dict({"prompt": "bold green"}),
    )

    try:
        while True:
            try:
                line = await prompt_session.prompt_async("> ")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            if line.startswith("/"):
                await _handle_slash(line, session_mgr, agent, config)
                continue

            console.print()  # blank line before response
            try:
                await agent.chat(
                    line,
                    on_token=display.on_token,
                    on_tool=display.on_tool,
                )
                console.print()  # blank line after response
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        await session_mgr.save(session)
        for stack in mcp_stacks.values():
            await stack.aclose()

    display.print_goodbye()


async def _handle_slash(cmd: str, session_mgr, agent, config):
    parts = cmd.split()
    op = parts[0].lower()

    if op == "/help":
        console.print("""
[bold]Commands:[/bold]
  /session list|new|switch|delete  — Session management
  /model [name]                     — View or switch model
  /config                           — Show config
  /yolo on|off                      — Auto-approve mode
  /clear                            — Clear current session
  /status                           — Show current status
  /exit, /quit                      — Exit
""")
    elif op == "/session":
        sub = parts[1] if len(parts) > 1 else "list"
        if sub == "list":
            sessions = await session_mgr.list_sessions()
            for s in sessions:
                marker = "→ " if s["id"] == session_mgr._active_id else "  "
                console.print(f"{marker}{s['id']} ({s.get('message_count', 0)} msgs)")
        elif sub == "new" and len(parts) > 2:
            s = await session_mgr.new(parts[2])
            console.print(f"Created and switched to session: {s.id}")
        elif sub == "switch" and len(parts) > 2:
            s = await session_mgr.switch(parts[2])
            console.print(f"Switched to session: {s.id}")
        elif sub == "delete" and len(parts) > 2:
            await session_mgr.delete(parts[2])
            console.print(f"Deleted session: {parts[2]}")
    elif op == "/status":
        session = await session_mgr.load()
        default = config.model_presets.get("default")
        console.print(f"Session: {session.id}  Messages: {len(session.messages)}  Model: {default.model if default else 'N/A'}")
    elif op == "/clear":
        session = await session_mgr.load()
        session.messages.clear()
        await session_mgr.save(session)
        console.print("Session cleared.")
    else:
        console.print(f"Unknown command: {op}. Type /help for commands.")


def main():
    parser = argparse.ArgumentParser(description="BananaCoder - AI coding assistant")
    parser.add_argument("prompt", nargs="?", help="Single-shot prompt (omit for interactive mode)")
    parser.add_argument("--session", "-s", help="Session name")
    parser.add_argument("--model", "-m", help="Model override")
    args = parser.parse_args()

    config = resolve_env_vars(load_config())
    config._data_dir = str(Path.home() / ".bananacoder")

    if args.prompt:
        asyncio.run(_run_single(config, args))
    else:
        asyncio.run(_run_interactive(config, args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write basic CLI test**

```python
# tests/test_cli.py
import pytest
from banana.cli.app import build_tools
from banana.config.schema import Config, ProviderConfig, ModelPresetConfig
from banana.skills.loader import SkillsLoader
from pathlib import Path


class TestBuildTools:
    def test_all_tools_registered(self, temp_home):
        config = Config(
            providers={"test": ProviderConfig(api_key="sk-xxx")},
            model_presets={"default": ModelPresetConfig(model="t", provider="test")},
        )
        loader = SkillsLoader(temp_home)
        registry = build_tools(config, loader)
        tool_names = registry.tool_names
        assert "bash" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names
        assert "web_fetch" in tool_names
        assert "agent" in tool_names
        assert "ask_user" in tool_names
        assert "todo_write" in tool_names
        assert "load_skill" in tool_names
```

- [ ] **Step 4: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_cli.py -v
```

---

## Task Group 11: Integration Verification

### Task 20: Full integration test + smoke test

**Files:**
- Modify: `tests/test_cli.py` (add integration)

- [ ] **Step 1: Add integration test**

```python
class TestFullIntegration:
    """End-to-end test with fake provider."""
    @pytest.mark.asyncio
    async def test_full_flow(self, temp_home, monkeypatch):
        monkeypatch.chdir(temp_home)

        from banana.config.schema import Config, ProviderConfig, ModelPresetConfig
        from banana.providers.factory import make_provider
        from banana.tools.bash import BashTool
        from banana.tools.registry import ToolRegistry
        from banana.session.manager import SessionManager
        from banana.skills.loader import SkillsLoader
        from banana.agent.loop import Agent

        config = Config(
            providers={"test": ProviderConfig(api_key="sk-test")},
            model_presets={"default": ModelPresetConfig(model="test", provider="test")},
        )

        # Override factory to return a fake
        class FakeProvider:
            async def chat_stream_with_retry(self, messages, tools, on_content_delta=None, **kw):
                if on_content_delta:
                    await on_content_delta("Hello from test!")
                from banana.providers.base import LLMResponse
                return LLMResponse(content="Hello from test!")

        provider = FakeProvider()
        registry = ToolRegistry()
        registry.register(BashTool())
        loader = SkillsLoader(temp_home)
        session_mgr = SessionManager(temp_home / ".bananacoder", temp_home)

        agent = Agent(provider, registry, session_mgr, loader)
        result = await agent.chat("say hi")
        assert "Hello from test!" in result
```

- [ ] **Step 2: Run all tests**

```bash
cd e:/BananaCoder && python -m pytest tests/ -v --tb=short 2>&1
```

- [ ] **Step 3: Verify CLI entry point loads**

```bash
cd e:/BananaCoder && python -c "from banana.cli.app import main; print('Entry point OK')"
```

Expected: "Entry point OK"

---

## Completion Checklist

- [ ] Task 1-3: Scaffolding + Config (passing tests)
- [ ] Task 4-7: Provider layer (passing tests)
- [ ] Task 8: Tool base + registry (passing tests)
- [ ] Task 9: Session manager (passing tests)
- [ ] Task 10-13: Built-in tools (passing tests)
- [ ] Task 14: MCP client (passing tests)
- [ ] Task 15: Skills loader (passing tests)
- [ ] Task 16-18: Agent layer (passing tests)
- [ ] Task 19: CLI + display (passing tests)
- [ ] Task 20: Integration smoke test (passing)

**Final verification command:**
```bash
cd e:/BananaCoder && python -m pytest tests/ -v --tb=short
```
Expected: 50+ tests passing
