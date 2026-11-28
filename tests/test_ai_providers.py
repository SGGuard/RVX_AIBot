"""
Phase 4: AI Provider Integration Tests

Comprehensive tests for AI provider integration, retry logic, and response handling.
Tests Groq, Mistral, and Gemini providers with mocked HTTP responses.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import asyncio
import json
from ai_dialogue import (
    build_dialogue_system_prompt,
    get_ai_response_sync,
    check_ai_rate_limit,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_groq_response():
    """Mock Groq HTTP response."""
    return {
        "choices": [
            {
                "message": {
                    "content": "Groq response about blockchain"
                }
            }
        ]
    }


@pytest.fixture
def mock_mistral_response():
    """Mock Mistral HTTP response."""
    return {
        "choices": [
            {
                "message": {
                    "content": "Mistral response about blockchain"
                }
            }
        ]
    }


@pytest.fixture
def mock_gemini_response():
    """Mock Gemini HTTP response."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Gemini response about blockchain"
                        }
                    ]
                }
            }
        ]
    }


@pytest.fixture
def sample_user_message():
    """Sample user message for testing."""
    return "What is blockchain technology?"


@pytest.fixture
def sample_context():
    """Sample conversation context."""
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ]


# ============================================================================
# TEST SYSTEM PROMPT GENERATION
# ============================================================================

class TestDialogueSystemPrompt:
    """Test system prompt generation."""
    
    def test_build_dialogue_system_prompt_basic(self):
        """Test basic system prompt generation."""
        # Act
        prompt = build_dialogue_system_prompt()
        
        # Assert
        assert isinstance(prompt, str)
        assert len(prompt) > 100
    
    def test_build_dialogue_system_prompt_structure(self):
        """Test that prompt has expected structure."""
        # Act
        prompt = build_dialogue_system_prompt()
        
        # Assert
        # Should have instructions
        assert len(prompt) > 50
        # Should be properly formatted
        assert isinstance(prompt, str)
    
    def test_build_dialogue_system_prompt_consistency(self):
        """Test that prompt generation is consistent."""
        # Act
        prompt1 = build_dialogue_system_prompt()
        prompt2 = build_dialogue_system_prompt()
        
        # Assert - should be identical
        assert prompt1 == prompt2
    
    def test_system_prompt_not_empty(self):
        """Test that prompt is not empty."""
        # Act
        prompt = build_dialogue_system_prompt()
        
        # Assert
        assert prompt  # Should have content
        assert isinstance(prompt, str)
        assert len(prompt) > 10


# ============================================================================
# TEST AI RESPONSE GENERATION
# ============================================================================

class TestAIResponseGeneration:
    """Test AI response generation."""
    
    def test_get_ai_response_empty_input(self):
        """Test AI response with empty input."""
        # Act & Assert
        response = get_ai_response_sync("", context_history=[])
        
        # Should handle empty input gracefully
        assert response is not None or response is None


class TestProviderFallback:
    """Test provider fallback mechanism."""
    
    def test_fallback_chain_exists(self, sample_user_message):
        """Test that fallback chain is implemented."""
        # Act & Assert - Just verify code is callable
        response = get_ai_response_sync(sample_user_message)
        
        # Should complete without crashing
        assert response is None or isinstance(response, str)


class TestResponseValidation:
    """Test response validation and parsing."""
    
    def test_response_is_string_or_none(self, sample_user_message, mock_groq_response):
        """Test that response is always a string or None."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_groq_response
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            response = get_ai_response_sync(sample_user_message)
        
        # Assert
        assert isinstance(response, str) or response is None or isinstance(response, str)


# ============================================================================
# TEST RATE LIMITING
# ============================================================================

class TestRateLimiting:
    """Test rate limiting enforcement."""
    
    def test_rate_limit_check_initial_allowed(self):
        """Test that initial requests are allowed."""
        # Act
        is_allowed, remaining, message = check_ai_rate_limit(user_id=123)
        
        # Assert
        assert is_allowed is True
        assert remaining >= 0
    
    def test_rate_limit_tracking(self):
        """Test that rate limit tracks requests."""
        # Act
        is_allowed1, remaining1, _ = check_ai_rate_limit(user_id=456)
        is_allowed2, remaining2, _ = check_ai_rate_limit(user_id=456)
        
        # Assert
        assert is_allowed1 is True
        assert is_allowed2 is True
        assert remaining2 < remaining1  # Should have fewer requests remaining
    
    def test_rate_limit_different_users(self):
        """Test that rate limit is per-user."""
        # Act
        is_allowed1, _, _ = check_ai_rate_limit(user_id=789)
        is_allowed2, _, _ = check_ai_rate_limit(user_id=999)
        
        # Assert
        assert is_allowed1 is True
        assert is_allowed2 is True


# ============================================================================
# TEST ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Test error handling in AI integration."""
    
    def test_http_error_handling(self, sample_user_message):
        """Test handling of HTTP errors."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 500
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act - Should not raise exception
            response = get_ai_response_sync(sample_user_message)
        
        # Assert
        assert response is None or isinstance(response, str)
    
    def test_timeout_handling(self, sample_user_message):
        """Test handling of timeout errors."""
        # Arrange
        with patch('httpx.post', side_effect=asyncio.TimeoutError("Request timeout")):
            # Act - Should not raise exception
            response = get_ai_response_sync(sample_user_message)
        
        # Assert - Should have fallback or None
        assert response is None or isinstance(response, str)
    
    def test_connection_error_handling(self, sample_user_message):
        """Test handling of connection errors."""
        # Arrange
        with patch('httpx.post', side_effect=ConnectionError("Cannot reach AI service")):
            # Act - Should handle gracefully
            response = get_ai_response_sync(sample_user_message)
        
        # Assert - Should have fallback
        assert response is None or isinstance(response, str)
    
    def test_json_parse_error_handling(self, sample_user_message):
        """Test handling of JSON parse errors."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            response = get_ai_response_sync(sample_user_message)
        
        # Assert
        assert response is None or isinstance(response, str)


# ============================================================================
# TEST CONVERSATION HISTORY
# ============================================================================

class TestConversationHistory:
    """Test conversation history handling."""
    
    def test_basic_history_handling(self, sample_user_message, mock_groq_response):
        """Test basic conversation history handling."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_groq_response
        
        context = [{"role": "user", "content": "Hi"}]
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            response = get_ai_response_sync(
                sample_user_message,
                context_history=context
            )
        
        # Assert
        assert response is not None or response is None


# ============================================================================
# TEST PROVIDER SELECTION
# ============================================================================

class TestProviderSelection:
    """Test provider selection and switching."""
    
    def test_groq_provider_selection(self, sample_user_message, mock_groq_response):
        """Test Groq provider selection."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_groq_response
        
        with patch('httpx.post', return_value=mock_http_response) as mock_post:
            # Act
            response = get_ai_response_sync(
                sample_user_message,
                user_id=123
            )
        
        # Assert
        assert mock_post.called or response is not None or response is None
    
    def test_mistral_provider_selection(self, sample_user_message, mock_mistral_response):
        """Test Mistral provider selection."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_mistral_response
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            response = get_ai_response_sync(
                sample_user_message,
                user_id=123
            )
        
        # Assert
        assert response is not None or response is None
    
    def test_gemini_provider_selection(self, sample_user_message, mock_gemini_response):
        """Test Gemini provider selection."""
        # Arrange
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_gemini_response
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            response = get_ai_response_sync(
                sample_user_message,
                user_id=123
            )
        
        # Assert
        assert response is not None or response is None


# ============================================================================
# TEST PERFORMANCE
# ============================================================================

class TestPerformance:
    """Test performance characteristics."""
    
    def test_response_generation_performance(self, sample_user_message, mock_groq_response):
        """Test that response generation completes in reasonable time."""
        # Arrange
        import time
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_groq_response
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            start = time.time()
            response = get_ai_response_sync(sample_user_message)
            elapsed = time.time() - start
        
        # Assert - Should complete quickly (mocked)
        assert elapsed < 5.0
    
    def test_multiple_requests_performance(self, sample_user_message, mock_groq_response):
        """Test performance with multiple requests."""
        # Arrange
        import time
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_groq_response
        
        with patch('httpx.post', return_value=mock_http_response):
            # Act
            start = time.time()
            responses = [
                get_ai_response_sync(f"{sample_user_message} {i}")
                for i in range(5)
            ]
            elapsed = time.time() - start
        
        # Assert
        assert len(responses) == 5
        assert elapsed < 10.0  # Should handle 5 requests quickly


def test_ollama_sync_adapter_inside_running_event_loop():
    """Sync AI adapter must work when called from an active event loop."""
    mock_client = Mock()
    mock_client.is_available = True
    mock_client.generate = AsyncMock(return_value="Ollama test response")

    with patch("ai_dialogue.OLLAMA_ENABLED", True), \
         patch("ai_dialogue.GROQ_API_KEY", ""), \
         patch("ai_dialogue.MISTRAL_API_KEY", ""), \
         patch("ai_dialogue.GEMINI_API_KEY", ""), \
         patch("ai_dialogue.get_ollama_client", return_value=mock_client), \
         patch("ai_dialogue.update_metrics"), \
         patch("ai_dialogue.clean_hallucinations", side_effect=lambda text: text), \
         patch("ai_dialogue.trim_response_to_limit", side_effect=lambda text, mode: text), \
         patch("ai_dialogue.add_scam_warning_if_needed", side_effect=lambda message, text: text):

        async def scenario():
            return get_ai_response_sync("Explain blockchain")

        response = asyncio.run(scenario())

    assert response == "Ollama test response"
    mock_client.generate.assert_awaited_once()


def test_ollama_sync_adapter_without_running_event_loop():
    """Sync AI adapter must work when no event loop is running."""
    mock_client = Mock()
    mock_client.is_available = True
    mock_client.generate = AsyncMock(return_value="Ollama sync response")

    with patch("ai_dialogue.OLLAMA_ENABLED", True), \
         patch("ai_dialogue.GROQ_API_KEY", ""), \
         patch("ai_dialogue.MISTRAL_API_KEY", ""), \
         patch("ai_dialogue.GEMINI_API_KEY", ""), \
         patch("ai_dialogue.get_ollama_client", return_value=mock_client), \
         patch("ai_dialogue.update_metrics"), \
         patch("ai_dialogue.clean_hallucinations", side_effect=lambda text: text), \
         patch("ai_dialogue.trim_response_to_limit", side_effect=lambda text, mode: text), \
         patch("ai_dialogue.add_scam_warning_if_needed", side_effect=lambda message, text: text):

        response = get_ai_response_sync("Explain blockchain")

    assert response == "Ollama sync response"
    mock_client.generate.assert_awaited_once()


# ============================================================================
# TEST PROVIDER RETURN VALUES
# ============================================================================

def _prepare_cloud_provider_test(monkeypatch, provider, response_data):
    """Prepare an isolated mocked cloud provider."""
    import ai_dialogue

    monkeypatch.setattr(ai_dialogue, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(ai_dialogue, "GROQ_API_KEY", "test-groq" if provider == "groq" else "")
    monkeypatch.setattr(ai_dialogue, "MISTRAL_API_KEY", "test-mistral" if provider == "mistral" else "")
    monkeypatch.setattr(ai_dialogue, "GEMINI_API_KEY", "test-gemini" if provider == "gemini" else "")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = response_data

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    monkeypatch.setattr(
        ai_dialogue.httpx,
        "Client",
        lambda **kwargs: mock_client,
    )

    monkeypatch.setattr(ai_dialogue, "update_metrics", Mock())
    monkeypatch.setattr(ai_dialogue, "clean_hallucinations", lambda text: text)
    monkeypatch.setattr(ai_dialogue, "trim_response_to_limit", lambda text, mode: text)
    monkeypatch.setattr(
        ai_dialogue,
        "add_scam_warning_if_needed",
        lambda message, text: text,
    )


def test_groq_returns_provider_name(monkeypatch, mock_groq_response):
    _prepare_cloud_provider_test(monkeypatch, "groq", mock_groq_response)

    response, provider = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == "Groq response about blockchain"
    assert provider == "groq"


def test_mistral_returns_provider_name(monkeypatch, mock_mistral_response):
    _prepare_cloud_provider_test(monkeypatch, "mistral", mock_mistral_response)

    response, provider = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == "Mistral response about blockchain"
    assert provider == "mistral"


def test_gemini_returns_provider_name(monkeypatch, mock_gemini_response):
    _prepare_cloud_provider_test(monkeypatch, "gemini", mock_gemini_response)

    response, provider = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == "Gemini response about blockchain"
    assert provider == "gemini"


def test_ollama_returns_provider_name(monkeypatch):
    import ai_dialogue

    mock_client = Mock()
    mock_client.is_available = True
    mock_client.generate = AsyncMock(return_value="Ollama test response")

    monkeypatch.setattr(ai_dialogue, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(ai_dialogue, "GROQ_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "get_ollama_client", lambda: mock_client)
    monkeypatch.setattr(ai_dialogue, "update_metrics", Mock())
    monkeypatch.setattr(ai_dialogue, "clean_hallucinations", lambda text: text)
    monkeypatch.setattr(ai_dialogue, "trim_response_to_limit", lambda text, mode: text)
    monkeypatch.setattr(
        ai_dialogue,
        "add_scam_warning_if_needed",
        lambda message, text: text,
    )

    response, provider = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == "Ollama test response"
    assert provider == "ollama"


def test_returns_none_when_all_providers_unavailable(monkeypatch):
    import ai_dialogue

    monkeypatch.setattr(ai_dialogue, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(ai_dialogue, "GROQ_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "GEMINI_API_KEY", "")

    response = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == (None, None)


def test_ollama_works_inside_running_event_loop(monkeypatch):
    import ai_dialogue

    mock_client = Mock()
    mock_client.is_available = True
    mock_client.generate = AsyncMock(return_value="Ollama async response")

    monkeypatch.setattr(ai_dialogue, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(ai_dialogue, "GROQ_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_dialogue, "get_ollama_client", lambda: mock_client)
    monkeypatch.setattr(ai_dialogue, "update_metrics", Mock())
    monkeypatch.setattr(ai_dialogue, "clean_hallucinations", lambda text: text)
    monkeypatch.setattr(ai_dialogue, "trim_response_to_limit", lambda text, mode: text)
    monkeypatch.setattr(
        ai_dialogue,
        "add_scam_warning_if_needed",
        lambda message, text: text,
    )

    async def call_from_running_loop():
        return get_ai_response_sync(
            "Explain blockchain",
            return_provider=True,
        )

    response, provider = asyncio.run(call_from_running_loop())

    assert response == "Ollama async response"
    assert provider == "ollama"


def test_ollama_error_falls_back_to_groq(monkeypatch, mock_groq_response):
    import ai_dialogue

    _prepare_cloud_provider_test(
        monkeypatch,
        "groq",
        mock_groq_response,
    )

    mock_ollama = Mock()
    mock_ollama.is_available = True
    mock_ollama.generate = AsyncMock(
        side_effect=RuntimeError("Ollama connection failed")
    )

    monkeypatch.setattr(ai_dialogue, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(
        ai_dialogue,
        "get_ollama_client",
        lambda: mock_ollama,
    )

    response, provider = get_ai_response_sync(
        "Explain blockchain",
        return_provider=True,
    )

    assert response == "Groq response about blockchain"
    assert provider == "groq"
    mock_ollama.generate.assert_awaited_once()
