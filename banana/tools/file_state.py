"""Track file read state to prevent editing files without reading them first."""

from __future__ import annotations

from pathlib import Path


class FileState:
    """Tracks which files have been read by the agent.

    The edit tool checks this before allowing modifications.
    If a file hasn't been read, the agent is warned to read it first.
    """

    def __init__(self):
        self._read: dict[str, str] = {}

    def mark_read(self, path):
        """Record a file as read."""
        self._read[str(Path(path).resolve())] = "read"

    def was_read(self, path) -> bool:
        """Check if a file was read in this session."""
        return str(Path(path).resolve()) in self._read

    def check_edit(self, path) -> str | None:
        """Return a warning message if the file hasn't been read, else None."""
        if not self.was_read(path):
            return (
                f"edit:\n[WARN] File '{path.name}' was not read before editing. "
                f"Use read_file to review the file first to avoid unintended changes."
            )
        return None

    def clear(self):
        self._read.clear()


# Global singleton
_file_state = FileState()


def get_file_state() -> FileState:
    return _file_state
