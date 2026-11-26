from unittest.mock import Mock

import run_tests


def test_run_command_does_not_use_a_shell(monkeypatch):
    subprocess_run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(run_tests.subprocess, "run", subprocess_run)

    assert run_tests.run_command("pytest tests -q")

    subprocess_run.assert_called_once_with(
        ["pytest", "tests", "-q"],
        check=False,
    )
