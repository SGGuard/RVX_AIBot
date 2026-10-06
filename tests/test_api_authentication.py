import importlib
import os
import socket

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


@pytest.mark.asyncio
async def test_analyze_image_requires_bearer_before_processing(api_server_module, monkeypatch):
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda _api_key: pytest.fail("key manager must not run without a Bearer token"),
    )
    monkeypatch.setattr(
        api_server_module.rate_limiter,
        "is_allowed",
        lambda _client_ip: pytest.fail("request processing must stop at authentication"),
    )

    with pytest.raises(HTTPException) as error:
        await api_server_module.analyze_image(
            api_server_module.ImagePayload(image_base64="YQ=="),
            make_request(),
        )

    assert error.value.status_code == 401
    assert error.value.detail == "Missing API key"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::1"],
)
@pytest.mark.asyncio
async def test_image_download_rejects_non_public_dns_addresses(
    api_server_module, monkeypatch, address
):
    resolved_hosts = []

    class StaticResolver:
        async def resolve(self, host, port=0, family=socket.AF_INET):
            resolved_hosts.append(host)
            address_family = socket.AF_INET6 if ":" in address else socket.AF_INET
            return [
                {
                    "hostname": host,
                    "host": address,
                    "port": port,
                    "family": address_family,
                    "proto": 0,
                    "flags": 0,
                }
            ]

        async def close(self):
            return None

    monkeypatch.setattr(
        api_server_module.aiohttp.resolver,
        "DefaultResolver",
        lambda: StaticResolver(),
    )
    monkeypatch.setattr(
        api_server_module.api_key_manager,
        "verify_api_key",
        lambda _api_key: (True, None),
    )
    monkeypatch.setattr(api_server_module.rate_limiter, "is_allowed", lambda _ip: True)

    with pytest.raises(HTTPException) as error:
        await api_server_module.analyze_image(
            api_server_module.ImagePayload(image_url="https://image.example/picture.png"),
            make_request("Bearer valid-key"),
        )

    assert error.value.status_code == 400
    assert resolved_hosts == ["image.example"]


@pytest.mark.asyncio
async def test_public_address_resolver_allows_global_ip(api_server_module):
    class StaticResolver:
        async def resolve(self, host, port=0, family=socket.AF_INET):
            return [
                {
                    "hostname": host,
                    "host": "93.184.216.34",
                    "port": port,
                    "family": socket.AF_INET,
                    "proto": 0,
                    "flags": 0,
                }
            ]

        async def close(self):
            return None

    resolver = api_server_module.PublicAddressResolver(StaticResolver())

    addresses = await resolver.resolve("image.example", 443)

    assert addresses[0]["host"] == "93.184.216.34"
    await resolver.close()


@pytest.mark.asyncio
async def test_image_downloader_does_not_follow_redirects(api_server_module, monkeypatch):
    requests = []

    class RedirectResponse:
        status = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    class FakeClientSession:
        def __init__(self, connector, **_kwargs):
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            await self.connector.close()

        def get(self, url, allow_redirects):
            requests.append((url, allow_redirects))
            return RedirectResponse()

    monkeypatch.setattr(api_server_module.aiohttp, "ClientSession", FakeClientSession)

    with pytest.raises(HTTPException) as error:
        await api_server_module.fetch_image_from_url("https://image.example/redirect")

    assert error.value.status_code == 400
    assert requests == [("https://image.example/redirect", False)]


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://image.example/picture.png", "https://user:pass@image.example/picture.png"],
)
def test_image_download_rejects_unsupported_or_credentialed_urls(api_server_module, url):
    with pytest.raises(HTTPException) as error:
        api_server_module.validate_image_download_url(url)

    assert error.value.status_code == 400
