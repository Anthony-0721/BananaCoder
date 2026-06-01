import os

from chcode.utils.shell.output import (
    MAX_OUTPUT_BYTES,
    MAX_OUTPUT_LINES,
    TruncatedOutput,
    truncate_output,
    _persist_to_file,
)


class TestTruncateOutput:
    def test_small_output_not_truncated(self):
        result = truncate_output("hello")
        assert result.content == "hello"
        assert result.truncated is False
        assert result.persisted_path is None
        assert result.total_bytes == 5

    def test_too_many_lines_truncated(self):
        lines = [f"line {i}" for i in range(MAX_OUTPUT_LINES + 500)]
        text = "\n".join(lines)
        result = truncate_output(text)
        assert result.truncated is True
        assert result.persisted_path is not None
        assert os.path.exists(result.persisted_path)

    def test_too_many_bytes_truncated(self):
        text = "x" * (MAX_OUTPUT_BYTES + 1000)
        result = truncate_output(text)
        assert result.truncated is True
        assert result.total_bytes > MAX_OUTPUT_BYTES

    def test_empty_string(self):
        result = truncate_output("")
        assert result.content == ""
        assert result.truncated is False


class TestPersistToFile:
    def test_creates_file(self):
        path = _persist_to_file("test content")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            assert f.read() == "test content"
        os.unlink(path)

    def test_truncates_large_content(self):
        """Line 58: content exceeds MAX_PERSISTED_BYTES, gets truncated."""
        from chcode.utils.shell.output import MAX_PERSISTED_BYTES

        # Create content larger than MAX_PERSISTED_BYTES
        content = "x" * (MAX_PERSISTED_BYTES + 1000)
        path = _persist_to_file(content)
        assert os.path.exists(path)
        with open(path, "rb") as f:
            written = f.read()
        # Written bytes should be exactly MAX_PERSISTED_BYTES
        assert len(written) == MAX_PERSISTED_BYTES
        os.unlink(path)
