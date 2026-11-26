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
    original_environment = config.ENVIRONMENT
    os.environ["AUTH_DB_PATH"] = str(auth_database)
    config.validate_config = lambda **_kwargs: True
    config.ENVIRONMENT = "development"
    try:
        return importlib.import_module("api_server")
    finally:
        config.validate_config = original_validate_config
        config.ENVIRONMENT = original_environment
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


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/teach_lesson", {"topic": "unknown-test-topic", "difficulty_level": "beginner"}),
        ("GET", "/get_token_info/bitcoin", None),
        ("GET", "/get_leaderboard", None),
        ("GET", "/metrics", None),
    ],
)
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-key"])
def test_remaining_functional_endpoints_reject_missing_or_invalid_api_key(
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
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/teach_lesson", {"topic": "unknown-test-topic", "difficulty_level": "beginner"}),
        ("GET", "/get_token_info/bitcoin", None),
        ("GET", "/get_leaderboard", None),
        ("GET", "/metrics", None),
    ],
)
def test_remaining_functional_endpoints_accept_valid_api_key(
    api_server_module, monkeypatch, method, path, payload
):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda api_key: (api_key == "valid-key", None),
    )

    if path == "/teach_lesson":
        import embedded_teacher

        monkeypatch.setattr(embedded_teacher, "get_difficulties_for_topic", lambda _topic: [])
        monkeypatch.setattr(embedded_teacher, "get_all_topics", lambda: [])
    elif path == "/get_token_info/bitcoin":
        async def get_test_token_info(_token_id):
            return {
                "name": "Bitcoin",
                "symbol": "BTC",
                "price": 1,
                "market_cap": 1,
                "market_cap_rank": 1,
                "change_24h": 0,
                "change_7d": 0,
                "volume_24h": 1,
                "ath": 1,
                "atl": 1,
            }

        monkeypatch.setattr(api_server_module, "get_token_info", get_test_token_info)

    response = TestClient(api_server_module.app).request(
        method,
        path,
        headers={"Authorization": "Bearer valid-key"},
        json=payload,
    )

    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/auth/create_api_key", {}),
        ("GET", "/security/status", None),
        ("GET", "/dialogue_metrics", None),
    ],
)
@pytest.mark.parametrize("admin_token", [None, "wrong-admin-token"])
def test_admin_endpoints_reject_missing_or_invalid_admin_token(
    api_server_module, monkeypatch, method, path, payload, admin_token
):
    monkeypatch.setenv("ADMIN_TOKEN", "expected-admin-token")
    headers = {"X-Admin-Token": admin_token} if admin_token else {}

    response = TestClient(api_server_module.app).request(
        method,
        path,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/auth/create_api_key", {}),
        ("GET", "/security/status", None),
        ("GET", "/dialogue_metrics", None),
    ],
)
def test_admin_endpoints_accept_valid_admin_token(
    api_server_module, monkeypatch, method, path, payload
):
    monkeypatch.setenv("ADMIN_TOKEN", "expected-admin-token")
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "generate_api_key",
        lambda *_args, **_kwargs: "rvx_key_test",
    )
    monkeypatch.setattr(api_server_module.audit_logger, "get_statistics", lambda: {})
    monkeypatch.setattr(api_server_module.audit_logger, "get_events", lambda **_kwargs: [])

    import ai_dialogue

    monkeypatch.setattr(
        ai_dialogue,
        "get_metrics_summary",
        lambda: {"total_requests": 0, "success_rate": 100},
    )

    original_compare_digest = api_server_module.secrets.compare_digest
    compared_tokens = []

    def compare_digest(left, right):
        compared_tokens.append((left, right))
        return original_compare_digest(left, right)

    monkeypatch.setattr(api_server_module.secrets, "compare_digest", compare_digest)

    response = TestClient(api_server_module.app).request(
        method,
        path,
        headers={"X-Admin-Token": "expected-admin-token"},
        json=payload,
    )

    assert response.status_code == 200
    assert compared_tokens == [
        (b"expected-admin-token", b"expected-admin-token")
    ]


@pytest.mark.integration
def test_public_routes_remain_accessible_without_authentication(api_server_module, monkeypatch):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda _api_key: (False, "Invalid API key"),
    )
    client = TestClient(api_server_module.app)

    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    verify_response = client.post(
        "/auth/verify_api_key",
        json={"api_key": "invalid-key"},
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is False


@pytest.mark.integration
def test_api_documentation_routes_are_development_only(api_server_module):
    assert api_server_module._api_documentation_config("development") == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
    assert api_server_module._api_documentation_config("production") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }

    client = TestClient(api_server_module.app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200
