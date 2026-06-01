from chcode.utils.shell.result import ShellResult


def test_defaults():
    r = ShellResult()
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.exit_code == 0
    assert r.interrupted is False
    assert r.timed_out is False
    assert r.output_file_path is None
    assert r.output_file_size is None


def test_custom_values():
    r = ShellResult(
        stdout="hello",
        stderr="err",
        exit_code=1,
        interrupted=True,
        timed_out=True,
        output_file_path="/tmp/out.txt",
        output_file_size=1024,
    )
    assert r.stdout == "hello"
    assert r.exit_code == 1
    assert r.output_file_size == 1024
