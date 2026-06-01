from unittest.mock import patch

from chcode.utils.git_checker import check_git_availability


class TestCheckGitAvailability:
    def test_git_available(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "git version 2.40.0"
            mock_run.return_value.returncode = 0
            ok, status, version = check_git_availability()
            assert ok is True
            assert "git version" in version

    def test_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, status, version = check_git_availability()
            assert ok is False
            assert version is None
            assert "未找到" in status

    def test_git_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            ok, status, version = check_git_availability()
            assert ok is False
            assert "超时" in status

    def test_git_error(self):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            ok, status, version = check_git_availability()
            assert ok is False
            assert "异常" in status
