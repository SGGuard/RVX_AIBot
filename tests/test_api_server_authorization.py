import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api_server_module(tmp_path_factory):
    import config

    auth_database = tmp_path_factory.mktemp("api-server-auth") / "auth_keys.sqlite3"
    previous_auth_db_path = os.environ.get("AUTH_DB_PATH")
    original_validate_config = config.validate_config
    os.environ["AUTH_DB_PATH"] = str(auth_database)
    config.validate_config = lambda **_kwargs: True
    try:
        return importlib.import_module("api_server")
    finally:
        config.validate_config = original_validate_config
        if previous_auth_db_path is None:
            os.environ.pop("AUTH_DB_PATH", None)
        else:
            os.environ["AUTH_DB_PATH"] = previous_auth_db_path


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/analyze_image", {"image_base64": "dGVzdA=="}),
        ("GET", "/get_drops", None),
        ("GET", "/get_activities", None),
        ("GET", "/get_trending", None),
    ],
)
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-key"])
def test_bot_api_endpoints_reject_missing_or_invalid_api_key(
    api_server_module, monkeypatch, method, path, payload, authorization
):
    headers = {"Authorization": authorization} if authorization else {}
    if authorization:
        monkeypatch.setattr(
            api_server_module.api_key_manager,
            "verify_api_key",
            lambda _api_key: (False, "Invalid API key"),
        )

    response = TestClient(api_server_module.app).request(
        method,
        path,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 401


@pytest.mark.integration
def test_bot_api_endpoint_accepts_valid_api_key(api_server_module, monkeypatch):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda api_key: (api_key == "valid-key", None),
    )

    async def get_empty_drops(_limit):
        return []

    monkeypatch.setattr(api_server_module, "get_nft_drops", get_empty_drops)

    response = TestClient(api_server_module.app).get(
        "/get_drops",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 200
    assert response.json()["drops"] == []
