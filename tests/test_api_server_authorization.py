import importlib
import os
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


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


@pytest.fixture(autouse=True)
def disable_rate_limiting_for_unrelated_tests(api_server_module, monkeypatch):
    monkeypatch.setattr(api_server_module, "RATE_LIMIT_ENABLED", False)


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


@pytest.mark.parametrize(
    "image_url",
    [
        "http://127.0.0.1/image.jpg",
        "http://10.0.0.1/image.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/image.jpg",
        "http://[fc00::1]/image.jpg",
        "http://[fe80::1]/image.jpg",
        "http://[64:ff9b::7f00:1]/image.jpg",
        "http://2130706433/image.jpg",
        "http://0177.0.0.1/image.jpg",
        "http://0x7f000001/image.jpg",
    ],
)
def test_image_payload_rejects_non_public_ip_literals(api_server_module, image_url):
    with pytest.raises(ValidationError):
        api_server_module.ImagePayload(image_url=image_url)


def test_image_payload_accepts_public_hostname(api_server_module):
    payload = api_server_module.ImagePayload(
        image_url="https://images.example.com/chart.png"
    )

    assert payload.image_url == "https://images.example.com/chart.png"


@pytest.mark.integration
def test_analyze_image_rejects_private_url(api_server_module, monkeypatch):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda api_key: (api_key == "valid-key", None),
    )

    response = TestClient(api_server_module.app).post(
        "/analyze_image",
        headers={"Authorization": "Bearer valid-key"},
        json={"image_url": "http://127.0.0.1/latest/meta-data/"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_address_resolver_rejects_private_dns_answers(
    api_server_module, monkeypatch
):
    class PrivateAddressResolver:
        async def resolve(self, host, port, family):
            return [
                {"host": "93.184.216.34"},
                {"host": "10.0.0.5"},
            ]

        async def close(self):
            return None

    resolver = api_server_module.PublicAddressResolver()
    monkeypatch.setattr(resolver, "_resolver", PrivateAddressResolver())

    try:
        with pytest.raises(OSError, match="non-public"):
            await resolver.resolve("public.example", 443)
    finally:
        await resolver.close()


@pytest.mark.asyncio
async def test_image_download_validates_redirect_target(api_server_module, monkeypatch):
    class RedirectResponse:
        status = 302
        headers = {"Location": "http://127.0.0.1/private"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClientSession:
        def __init__(self, **_kwargs):
            self.requested_urls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get(self, url, *, allow_redirects):
            assert allow_redirects is False
            self.requested_urls.append(str(url))
            return RedirectResponse()

    sessions = []

    def create_session(**kwargs):
        session = FakeClientSession(**kwargs)
        sessions.append(session)
        return session

    monkeypatch.setattr(api_server_module.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(api_server_module.aiohttp, "ClientSession", create_session)

    with pytest.raises(ValueError, match="non-public"):
        await api_server_module.download_image_from_url(
            "https://images.example.com/redirect"
        )

    assert len(sessions[0].requested_urls) == 1


def test_trusted_proxy_allowlist_accepts_only_ips_and_networks(api_server_module):
    assert api_server_module._parse_trusted_proxy_ips(
        "127.0.0.1, 10.20.99.5/16, ::1"
    ) == ["127.0.0.1", "10.20.0.0/16", "::1"]


def test_client_ip_ignores_untrusted_forwarded_header():
    from fastapi import Request
    from security_middleware import get_client_ip

    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"203.0.113.99")],
            "client": ("10.0.0.20", 1234),
            "server": ("api", 8000),
        }
    )

    assert get_client_ip(request) == "10.0.0.20"


@pytest.mark.parametrize("value", ["", "*", "proxy.example.com", "127.0.0.1,*"])
def test_trusted_proxy_allowlist_rejects_unsafe_values(api_server_module, value):
    with pytest.raises(ValueError):
        api_server_module._parse_trusted_proxy_ips(value)


@pytest.mark.integration
def test_rate_limit_middleware_awaits_async_limiter(api_server_module, monkeypatch):
    check_rate_limit = AsyncMock(return_value=False)
    get_retry_after = AsyncMock(return_value=7)
    monkeypatch.setattr(api_server_module.rate_limiter, "is_allowed", check_rate_limit)
    monkeypatch.setattr(api_server_module.rate_limiter, "get_retry_after", get_retry_after)

    response = TestClient(api_server_module.app).get("/metrics")

    assert response.status_code == 429
    check_rate_limit.assert_awaited_once()
    get_retry_after.assert_awaited_once()


@pytest.mark.integration
def test_analyze_image_awaits_async_limiter(api_server_module, monkeypatch):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda api_key: (api_key == "valid-key", None),
    )
    check_rate_limit = AsyncMock(return_value=False)
    monkeypatch.setattr(api_server_module.rate_limiter, "is_allowed", check_rate_limit)

    response = TestClient(api_server_module.app).post(
        "/analyze_image",
        headers={"Authorization": "Bearer valid-key"},
        json={"image_base64": "dGVzdA=="},
    )

    assert response.status_code == 429
    check_rate_limit.assert_awaited_once()


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
    assert api_server_module.app.docs_url == "/docs"
    assert api_server_module.app.redoc_url == "/redoc"
    assert api_server_module.app.openapi_url == "/openapi.json"

    client = TestClient(api_server_module.app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200
