"""Centralized workspace path resolution (inspired by nanobot's path_utils.py)."""
from __future__ import annotations

from pathlib import Path


WORKSPACE_BOUNDARY_NOTE = (
    "\n\n[This is a hard policy boundary. The path is outside the workspace. "
    "Do not retry with different tools, shell tricks, working_dir overrides, "
    "symlinks, or piping — the answer will not change.]"
)


def is_under(path: Path, parent: Path) -> bool:
    """Check if path is under parent directory."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_workspace_path(
    path: str,
    workspace: Path | None = None,
    allowed_dir: Path | None = None,
) -> Path:
    """Resolve a file path, optionally enforcing workspace containment.

    Args:
        path: The raw path string (from LLM tool call).
        workspace: Base directory for relative paths. If None, uses CWD.
        allowed_dir: If set, resolved path must be under this directory.

    Returns:
        Resolved absolute Path.

    Raises:
        PermissionError: If allowed_dir is set and path is outside it.
    """
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p
    resolved = p.resolve()

    if allowed_dir:
        allowed = allowed_dir.resolve()
        if not is_under(resolved, allowed):
            raise PermissionError(
                f"Path '{path}' resolves to '{resolved}' which is outside "
                f"the workspace '{allowed}'." + WORKSPACE_BOUNDARY_NOTE
            )

    return resolved
