import os
from unittest.mock import patch

import pytest

from chcode.utils.shell.provider import BashProvider, PowerShellProvider


class TestBashProvider:
    def test_build_command(self):
        p = BashProvider()
        cmd = p.build_command("echo hello", "/tmp/cwd")
        assert "echo hello" in cmd
        assert "/tmp/cwd" in cmd

    def test_get_spawn_args(self):
        p = BashProvider()
        args = p.get_spawn_args("echo hello")
        assert args == ["-c", "echo hello"]

    def test_display_name(self):
        assert BashProvider().display_name == "bash"

    def test_create_cwd_file(self):
        p = BashProvider()
        path = p.create_cwd_file()
        assert "chcode-cwd-" in path

    def test_read_cwd_file(self, tmp_path):
        p = BashProvider()
        f = tmp_path / "cwd"
        f.write_text("/some/path", encoding="utf-8")
        assert p.read_cwd_file(str(f)) == "/some/path"

    def test_read_cwd_file_nonexistent(self):
        p = BashProvider()
        assert p.read_cwd_file("/nonexistent/file") is None

    def test_cleanup_cwd_file(self, tmp_path):
        p = BashProvider()
        f = tmp_path / "cwd"
        f.write_text("test")
        p.cleanup_cwd_file(str(f))
        assert not f.exists()

    @patch("os.name", "nt")
    @patch("shutil.which", return_value=None)
    def test_not_available_on_windows_without_git(self, mock_which):
        p = BashProvider()
        assert p.is_available is False


class TestPowerShellProvider:
    def test_shell_path(self):
        assert PowerShellProvider().shell_path == "powershell"

    def test_display_name_windows(self):
        assert PowerShellProvider().display_name == "powershell"

    def test_build_command_windows(self):
        p = PowerShellProvider()
        cmd = p.build_command("Get-Date", "/tmp/cwd")
        assert "Get-Date" in cmd
        assert "/tmp/cwd" in cmd

    def test_get_spawn_args_windows(self):
        p = PowerShellProvider()
        args = p.get_spawn_args("Get-Date")
        assert "-NoProfile" in args
        assert "-Command" in args

    def test_env_overrides(self):
        assert PowerShellProvider().get_env_overrides() == {"PSMODULEPATH": ""}
