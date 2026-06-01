from chcode.utils.shell.semantics import (
    Interpretation,
    _get_base_command,
    interpret_command_result,
)


class TestGetBaseCommand:
    def test_simple(self):
        assert _get_base_command("grep foo") == "grep"

    def test_with_path(self):
        assert _get_base_command("/usr/bin/grep foo") == "grep"

    def test_with_backslash_path(self):
        assert _get_base_command("C:\\Git\\bin\\bash -c 'echo'") == "bash"

    def test_pipe(self):
        assert _get_base_command("cat file | grep foo") == "grep"

    def test_empty_semantics(self):
        assert _get_base_command("") == ""

    def test_semicolon(self):
        result = _get_base_command("echo a ; echo b")
        assert result == "echo"


class TestInterpretCommandResult:
    def test_exit_zero(self):
        r = interpret_command_result("anything", 0)
        assert r.is_error is False
        assert r.message is None

    def test_grep_exit_1(self):
        r = interpret_command_result("grep pattern file", 1)
        assert r.is_error is False
        assert "No matches" in r.message

    def test_grep_exit_2(self):
        r = interpret_command_result("grep pattern file", 2)
        assert r.is_error is True

    def test_diff_exit_1(self):
        r = interpret_command_result("diff a.txt b.txt", 1)
        assert r.is_error is False
        assert "differ" in r.message

    def test_robocopy_exit_1(self):
        r = interpret_command_result("robocopy src dst", 1)
        assert r.is_error is False
        assert "copied" in r.message

    def test_unknown_command_exit_1(self):
        r = interpret_command_result("myapp", 1)
        assert r.is_error is True

    def test_empty_command(self):
        r = interpret_command_result("", 1)
        assert r.is_error is True
        assert "Exit code 1" in r.message

    def test_ping_exit_1(self):
        r = interpret_command_result("ping host", 1)
        assert r.is_error is False
        assert "unreachable" in r.message.lower() or "no response" in r.message.lower()

    def test_which_exit_1(self):
        r = interpret_command_result("which python3", 1)
        assert r.is_error is False

    def test_mkdir_exit_1(self):
        r = interpret_command_result("mkdir /root/forbidden", 1)
        assert r.is_error is False

    def test_exit_code_higher(self):
        r = interpret_command_result("grep foo bar", 42)
        assert r.is_error is True
