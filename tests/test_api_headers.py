import hashlib
import hmac

import pytest

import config
from config import build_api_headers


def test_build_api_headers_signs_user_id(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")
    monkeypatch.setattr(config, "USER_ID_SIGNING_SECRET", "s" * 32)
    expected_signature = hmac.new(
        b"s" * 32, b"42", hashlib.sha256
    ).hexdigest()

    assert build_api_headers(42) == {
        "Authorization": "Bearer test-key",
        "X-User-ID": "42",
        "X-User-ID-Signature": expected_signature,
    }


def test_build_api_headers_omits_unsigned_user_id(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")
    monkeypatch.setattr(config, "USER_ID_SIGNING_SECRET", "")

    assert build_api_headers(42) == {"Authorization": "Bearer test-key"}


def test_build_api_headers_omits_user_id_when_not_provided(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", "test-key")

    assert build_api_headers() == {"Authorization": "Bearer test-key"}


def test_build_api_headers_fails_when_key_is_missing(monkeypatch):
    monkeypatch.setattr(config, "BOT_API_KEY", " ")

    with pytest.raises(ValueError, match="BOT_API_KEY"):
        build_api_headers()
