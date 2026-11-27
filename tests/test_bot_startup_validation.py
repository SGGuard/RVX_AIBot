import pytest

import bot


def test_main_exits_with_error_when_config_validation_fails(monkeypatch):
    def fail_validation():
        raise ValueError("Invalid test configuration")

    monkeypatch.setattr("config.validate_config", fail_validation)

    with pytest.raises(SystemExit) as exc_info:
        bot.main()

    assert exc_info.value.code == 1
