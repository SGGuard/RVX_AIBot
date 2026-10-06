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


def test_build_api_headers_uses_shared_key_and_user_id(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")

    assert build_api_headers(42) == {
        "Authorization": "Bearer test-key",
        "X-User-ID": "42",
    }


def test_build_api_headers_fails_without_key(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", " ")

    with pytest.raises(ValueError, match="BOT_API_KEY"):
        build_api_headers()
