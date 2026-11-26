import os
import subprocess
import sys
from pathlib import Path

import pytest

import config


@pytest.mark.parametrize(
    "admin_token",
    [
        None,
        "",
        "replace_with_a_long_random_admin_token",
        "admin_token_change_this_to_secure_random_token_in_production",
    ],
)
def test_non_development_config_rejects_missing_or_example_admin_token(
    monkeypatch, caplog, admin_token
):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "DEBUG_MODE", False)
    if admin_token is None:
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_TOKEN", admin_token)

    with pytest.raises(ValueError):
        config.validate_config(require_bot=False)
    assert "ADMIN_TOKEN" in caplog.text


def test_non_development_config_accepts_custom_admin_token(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "DEBUG_MODE", False)
    monkeypatch.setenv("ADMIN_TOKEN", "a-custom-production-admin-token")

    assert config.validate_config(require_bot=False) is True


def test_env_example_does_not_override_secure_environment_default():
    env_example = Path(__file__).resolve().parents[1] / ".env.example"

    assert not any(
        line.strip() == "ENVIRONMENT=development"
        for line in env_example.read_text(encoding="utf-8").splitlines()
    )


def test_unset_environment_defaults_to_production_and_disables_docs(tmp_path):
    environment = os.environ.copy()
    environment.pop("ENVIRONMENT", None)
    environment.pop("RAILWAY_ENVIRONMENT", None)
    environment.pop("RAILWAY_PROJECT_ID", None)
    environment.update(
        {
            "ADMIN_TOKEN": "test-production-admin-token",
            "AUTH_DB_PATH": str(tmp_path / "auth_keys.sqlite3"),
            "BOT_API_KEY": "test-api-key",
            "DEBUG_MODE": "false",
            "GEMINI_API_KEY": "test-gemini-key",
            "TELEGRAM_BOT_TOKEN": "test-bot-token",
        }
    )
    script = """
import config
from fastapi.testclient import TestClient
import api_server

assert config.ENVIRONMENT == "production"
assert api_server.app.docs_url is None
assert api_server.app.redoc_url is None
assert api_server.app.openapi_url is None

client = TestClient(api_server.app)
for path in ("/docs", "/redoc", "/openapi.json"):
    assert client.get(path).status_code == 404, path
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
