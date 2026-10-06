import importlib
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.fixture(scope="module")
def api_server_module(tmp_path_factory):
    import config

    temp_directory = tmp_path_factory.mktemp("api-auth")
    test_paths = {
        "AUTH_DB_PATH": temp_directory / "auth_keys.sqlite3",
        "AUDIT_LOG_PATH": temp_directory / "audit_logs.db",
        "AUDIT_LOG_FILE": temp_directory / "audit.log",
    }
    previous_paths = {name: os.environ.get(name) for name in test_paths}
    original_validate_config = config.validate_config
    for name, path in test_paths.items():
        os.environ[name] = str(path)
    config.validate_config = lambda **_kwargs: True
    try:
        return importlib.import_module("api_server")
    finally:
        config.validate_config = original_validate_config
        for name, previous_path in previous_paths.items():
            if previous_path is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_path


def make_request(authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/explain_news",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


@pytest.mark.parametrize("authorization", [None, "Basic test-key"])
def test_verify_api_key_rejects_missing_or_non_bearer_header(
    api_server_module, monkeypatch, authorization
):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda _api_key: pytest.fail("key manager must not run without a Bearer token"),
    )

    with pytest.raises(HTTPException) as error:
        api_server_module.verify_api_key(make_request(authorization))

    assert error.value.status_code == 401
    assert error.value.detail == "Missing API key"


def test_verify_api_key_rejects_invalid_bearer_token(api_server_module, monkeypatch):
    verified_keys = []

    def reject_key(api_key):
        verified_keys.append(api_key)
        return False, "Invalid API key"

    monkeypatch.setattr(api_server_module.api_key_manager, "verify_api_key", reject_key)

    with pytest.raises(HTTPException) as error:
        api_server_module.verify_api_key(make_request("Bearer bad-key"))

    assert verified_keys == ["bad-key"]
    assert error.value.status_code == 401
    assert error.value.detail == "Invalid API key"


def test_verify_api_key_returns_valid_bearer_token(api_server_module, monkeypatch):
    verified_keys = []

    def accept_key(api_key):
        verified_keys.append(api_key)
        return True, None

    monkeypatch.setattr(api_server_module.api_key_manager, "verify_api_key", accept_key)

    result = api_server_module.verify_api_key(make_request("Bearer valid-key"))

    assert result == "valid-key"
    assert verified_keys == ["valid-key"]
