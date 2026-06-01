"""Shell execution tool."""
from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path
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
        from banana.security import get_security
        from banana.tools.filesystem import _workspace_root
        from banana.tools.path_utils import is_under, WORKSPACE_BOUNDARY_NOTE

        # Security check
        security = get_security()
        allowed, reason = await security.check_and_confirm(command)
        if not allowed:
            return f"bash:\n[BLOCKED] {reason}"

        timeout = min(max(timeout, 1), 600)
        cwd = workdir or os.getcwd()

        # Workspace boundary for working_dir
        if _workspace_root:
            requested = Path(cwd).expanduser().resolve()
            workspace = _workspace_root.resolve()
            if not is_under(requested, workspace) and requested != workspace:
                return f"bash:\n[BLOCKED] working_dir '{cwd}' is outside workspace '{workspace}'." + WORKSPACE_BOUNDARY_NOTE

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
