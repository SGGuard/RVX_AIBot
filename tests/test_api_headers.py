import pytest

import config
from config import build_api_headers


def test_build_api_headers_includes_bearer_token_and_user_id(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")

    assert build_api_headers(42) == {
        "Authorization": "Bearer test-key",
        "X-User-ID": "42",
    }


def test_build_api_headers_omits_user_id_when_not_provided(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")

    assert build_api_headers() == {"Authorization": "Bearer test-key"}


def test_build_api_headers_fails_when_key_is_missing(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", " ")

    with pytest.raises(ValueError, match="BOT_API_KEY"):
        build_api_headers()
