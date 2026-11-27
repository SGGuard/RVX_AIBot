import hashlib
import hmac
import pathlib

import pytest

import config
from config import build_api_headers, resolve_api_url, validate_api_url


def test_resolve_api_url_accepts_base_url():
    assert resolve_api_url("https://api.example.com") == "https://api.example.com/explain_news"


def test_resolve_api_url_keeps_final_endpoint():
    assert resolve_api_url("https://api.example.com/explain_news") == "https://api.example.com/explain_news"


def test_resolve_api_url_handles_localhost():
    assert resolve_api_url("http://localhost:8000") == "http://localhost:8000/explain_news"


def test_resolve_api_url_converts_health_endpoint_to_analysis_endpoint():
    assert resolve_api_url("https://api.example.com/health") == "https://api.example.com/explain_news"


@pytest.mark.parametrize("url", ["http://api.example.com/explain_news", "ftp://api.example.com"])
def test_remote_or_unsupported_api_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_api_url(url)


def test_explicit_private_service_host_can_use_http():
    validate_api_url("http://api:8000/explain_news", insecure_hosts={"api"})


def test_http_allowlist_matches_exact_host():
    with pytest.raises(ValueError):
        validate_api_url("http://api.internal.example/explain_news", insecure_hosts={"api"})


def test_build_api_headers_signs_user_id(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")
    monkeypatch.setattr(config, "USER_ID_SIGNING_SECRET", "s" * 32)

    assert build_api_headers(42) == {
        "Authorization": "Bearer test-key",
        "X-User-ID": "42",
        "X-User-ID-Signature": hmac.new(
            b"s" * 32, b"42", hashlib.sha256
        ).hexdigest(),
    }


def test_build_api_headers_fails_without_key(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", " ")

    with pytest.raises(ValueError, match="BOT_API_KEY"):
        build_api_headers()


def test_api_config_does_not_require_telegram_secrets(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "BOT_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")

    assert config.validate_config(require_bot=False)

    with pytest.raises(ValueError, match="Конфигурация невалидна"):
        config.validate_config()


def test_database_path_rejects_prefix_sibling(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    home_dir = tmp_path / "home"
    temp_dir = tmp_path / "tmp"
    sibling_path = tmp_path / "app-elsewhere" / "data.db"
    app_dir.mkdir()
    home_dir.mkdir()
    temp_dir.mkdir()
    monkeypatch.chdir(app_dir)
    monkeypatch.setattr(
        pathlib.Path,
        "home",
        classmethod(lambda _cls: home_dir),
    )
    monkeypatch.setattr(config.tempfile, "gettempdir", lambda: str(temp_dir))

    with pytest.raises(ValueError, match="outside safe directories"):
        config._validate_and_resolve_db_path(str(sibling_path))
