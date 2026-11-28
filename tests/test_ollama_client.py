"""Tests for OllamaClient response caching."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ollama_client import OllamaClient


@pytest.fixture
def client():
    instance = OllamaClient(enable_cache=True)
    instance.is_available = True
    return instance


def mock_response(text):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"response": text}
    return response


@pytest.mark.asyncio
async def test_identical_request_uses_cache(client):
    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(return_value=mock_response("First response"))
        mock_http.return_value.__aenter__.return_value.post = post

        first = await client.generate("Hello")
        second = await client.generate("Hello")

    assert first == "First response"
    assert second == "First response"
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_different_system_prompt_does_not_use_same_cache_entry(client):
    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(
            side_effect=[
                mock_response("Response A"),
                mock_response("Response B"),
            ]
        )
        mock_http.return_value.__aenter__.return_value.post = post

        first = await client.generate("Hello", system_prompt="Be concise")
        second = await client.generate("Hello", system_prompt="Be detailed")

    assert first == "Response A"
    assert second == "Response B"
    assert post.await_count == 2


@pytest.mark.asyncio
async def test_different_temperature_does_not_use_same_cache_entry(client):
    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(
            side_effect=[
                mock_response("Response A"),
                mock_response("Response B"),
            ]
        )
        mock_http.return_value.__aenter__.return_value.post = post

        first = await client.generate("Hello", temperature=0.2)
        second = await client.generate("Hello", temperature=0.8)

    assert first == "Response A"
    assert second == "Response B"
    assert post.await_count == 2


@pytest.mark.asyncio
async def test_different_max_tokens_does_not_use_same_cache_entry(client):
    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(
            side_effect=[
                mock_response("Response A"),
                mock_response("Response B"),
            ]
        )
        mock_http.return_value.__aenter__.return_value.post = post

        first = await client.generate("Hello", max_tokens=500)
        second = await client.generate("Hello", max_tokens=2000)

    assert first == "Response A"
    assert second == "Response B"
    assert post.await_count == 2


@pytest.mark.asyncio
async def test_empty_response_is_cached(client):
    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(return_value=mock_response(""))
        mock_http.return_value.__aenter__.return_value.post = post

        first = await client.generate("Hello")
        second = await client.generate("Hello")

    assert first == ""
    assert second == ""
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_stream_http_error_reads_response_without_awaiting_text(client):
    response = Mock()
    response.status_code = 500
    response.text = "Internal Server Error"
    response.aread = AsyncMock()

    class ResponseContext:
        async def __aenter__(self):
            return response

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.stream = Mock(
            return_value=ResponseContext()
        )

        with pytest.raises(RuntimeError, match="Internal Server Error"):
            await client.generate("Hello", stream=True)

    assert response.aread.await_count == 3


@pytest.mark.asyncio
async def test_httpx_timeout_is_propagated(client):
    import httpx

    with patch("ollama_client.httpx.AsyncClient") as mock_http:
        post = AsyncMock(side_effect=httpx.ReadTimeout("Request timed out"))
        mock_http.return_value.__aenter__.return_value.post = post

        with pytest.raises(httpx.ReadTimeout):
            await client.generate("Hello")

    assert post.await_count == 3
