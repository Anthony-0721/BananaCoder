"""Security sandbox for bash command execution."""
from __future__ import annotations

import asyncio
import fnmatch
from dataclasses import dataclass, field
from enum import Enum

from rich.console import Console
from rich.prompt import Confirm

console = Console()


class SecurityMode(str, Enum):
    NORMAL = "normal"   # safe=auto, write=confirm, unknown=blocked
    FAST = "fast"       # safe+write=auto, unknown=confirm, blocked=blocked
    YOLO = "yolo"       # all=auto, blocked=blocked


# Patterns that auto-approve in normal mode (read-only, informational)
AUTO_APPROVE = [
    # File browsing (read-only)
    "ls *", "dir *", "cat *", "head *", "tail *", "less *", "more *",
    "find *", "tree *", "pwd", "which *", "where *", "type *",
    "file *", "stat *", "wc *", "du *", "df *",
    # Search
    "grep *", "rg *", "ag *", "awk *",
    # Env / info
    "echo *", "env", "printenv", "set", "date", "whoami", "id",
    "uname *", "hostname",
    # Process info
    "ps *", "top *", "htop *",
    # Network read-only
    "ping *", "traceroute *", "nslookup *", "dig *",
    "curl *", "wget *",
    # Git read-only
    "git status", "git log *", "git diff *", "git show *",
    "git branch *", "git remote *", "git stash list",
    "git blame *", "git grep *", "git config *",
    # Docker read-only
    "docker ps *", "docker images *", "docker inspect *",
    "docker logs *", "docker stats *",
    "docker compose ps *", "docker compose logs *", "docker compose config *",
    # Misc safe
    "clear", "cls", "cd *", "pushd *", "popd",
    # Python / Node info
    "python --version", "python -V", "python -c *",
    "node --version", "node -v", "node -e *",
    "npm --version", "npm -v", "pip --version", "pip -V",
    "pip list *", "pip show *", "npm list *", "npm view *",
]


# Patterns that need confirmation in normal mode, but auto-approve in fast/yolo
WRITE_PATTERNS = [
    # File write
    "touch *", "mkdir *", "cp *", "mv *",
    # Code tools (build/run)
    "python *", "python3 *", "pip install *", "pip3 install *",
    "node *", "npm install *", "npm run *", "npm start *", "npm test *",
    "npx *", "yarn *", "pnpm *", "bun *",
    "cargo *", "go *", "rustc *", "javac *", "java *",
    "make *", "cmake *", "ninja *", "meson *",
    "gcc *", "g++ *", "clang *", "clang++ *",
    # Test runners
    "pytest *", "python -m pytest *", "jest *", "vitest *",
    "cargo test *", "go test *",
    # Git write
    "git add *", "git reset *", "git restore *", "git checkout *",
    "git switch *", "git merge *", "git rebase *", "git commit *",
    "git tag *", "git stash *", "git fetch *", "git pull *",
    # Package management
    "apt *", "apt-get *", "brew *", "choco *", "winget *",
    "conda *", "mamba *",
    # Dev servers
    "python -m http.server *", "python -m flask *",
    "uvicorn *", "gunicorn *",
    # Editors
    "code *", "vim *", "nano *", "notepad *",
    # Permissions (limited)
    "chmod [0-7][0-7][0-7] *", "chown *",
]


# Always blocked regardless of mode
BLOCKED = [
    # Destructive recursive/root
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .",
    "rm -rf --no-preserve-root /*",
    "del /f /s *\\*", "rd /s /q C:\\*",
    "Remove-Item -Path C:\\* -Recurse -Force",
    # Format/partition
    "format *", "mkfs.*", "dd if=*", "fdisk *", "parted *", "diskpart *",
    # System
    "shutdown *", "reboot", "halt", "poweroff",
    "shutdown.exe *", "shutdown /s*", "shutdown /r*",
    # Fork bomb / dangerous loops
    ":() { :|:& };:", "while true; do",
    # Wide-open permissions
    "chmod 777 /*", "chmod -R 777 /*", "chmod 777 /usr/*",
    "chown -R * /*", "chown root * /usr/*",
    # Force push
    "git push --force *", "git push -f *",
    "git reset --hard *", "git clean -fdx *",
    # Eval / pipe to shell
    "eval *",
    "curl * | sh", "curl * | bash", "wget * | sh", "wget * | bash",
    "curl * | python", "wget * | python",
    # Miners
    "xmrig *", "t-rex *", "phoenixminer *",
    # Registry
    "reg add *", "reg delete *", "reg import *",
    # Global installs
    "npm install -g *", "pip install --global *",
    # Blind rm
    "rm -rf *", "del /f /s *",
    # Edit write_file calls (these use our tool, not bash)
]


@dataclass
class SecurityContext:
    mode: SecurityMode = SecurityMode.NORMAL
    auto_approve: list[str] = field(default_factory=lambda: list(AUTO_APPROVE))
    write_patterns: list[str] = field(default_factory=lambda: list(WRITE_PATTERNS))
    blocked: list[str] = field(default_factory=lambda: list(BLOCKED))

    def _matches(self, command: str, patterns: list[str]) -> bool:
        cmd = command.strip()
        for p in patterns:
            if fnmatch.fnmatch(cmd, p) or p in cmd:
                return True
        return False

    def _is_safe(self, command: str) -> bool:
        return self._matches(command, self.auto_approve)

    def _is_write(self, command: str) -> bool:
        return self._matches(command, self.write_patterns)

    def _is_blocked(self, command: str) -> bool:
        return self._matches(command, self.blocked)

    async def check_and_confirm(self, command: str) -> tuple[bool, str]:
        # Blocked patterns always blocked in all modes
        if self._is_blocked(command):
            return False, f"Blocked by security policy: {command[:60]}"

        if self.mode == SecurityMode.NORMAL:
            # Safe commands = auto-approve
            if self._is_safe(command):
                return True, "OK"
            # Write commands = confirm
            if self._is_write(command):
                allowed = await asyncio.to_thread(
                    lambda: Confirm.ask(
                        f"[yellow]Allow: {command[:100]}[/yellow]",
                        default=False,
                    )
                )
                if not allowed:
                    return False, "User cancelled."
                return True, "OK"
            # Unknown = blocked
            return False, (
                f"Not in safe/write patterns. Use /fast or /yolo mode, "
                f"or add to auto_approve/write_patterns in ~/.bananacoder/config.json"
            )

        elif self.mode == SecurityMode.FAST:
            # Safe + known write = auto-approve, unknown = confirm
            if self._is_safe(command) or self._is_write(command):
                return True, "OK"
            # Unknown command = confirm
            allowed = await asyncio.to_thread(
                lambda: Confirm.ask(
                    f"[yellow]Unknown command, allow? {command[:100]}[/yellow]",
                    default=False,
                )
            )
            if not allowed:
                return False, "User cancelled."
            return True, "OK"

        elif self.mode == SecurityMode.YOLO:
            # Everything not blocked auto-approves
            return True, "OK"

        return False, "Unknown mode."


# Global security context
_security = SecurityContext()


def get_security() -> SecurityContext:
    return _security


def set_mode(mode: SecurityMode):
    _security.mode = mode
    mode_desc = {
        SecurityMode.NORMAL: "[bold blue]NORMAL[/] — safe=auto, write=confirm, unknown=block",
        SecurityMode.FAST: "[bold yellow]FAST[/] — safe+write=auto, unknown=confirm, blocked=deny",
        SecurityMode.YOLO: "[bold red]YOLO[/] — all=auto, blocked=deny",
    }
    console.print(f"Security mode: {mode_desc.get(mode, str(mode))}")
