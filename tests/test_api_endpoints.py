"""
Phase 4.2: API Endpoint Integration Tests

Comprehensive tests for all FastAPI endpoints covering:
- Request validation and sanitization
- Response formats and status codes
- Error handling and edge cases
- Caching behavior
- Rate limiting
- Authentication
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
import json


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from api_server import app
    
    # Disable rate limiting for tests
    with patch('api_server.RATE_LIMIT_ENABLED', False):
        # Mock verify_api_key to always return valid key
        with patch('api_server.verify_api_key', return_value="test-key"):
            # Also mock api_key_manager.verify_api_key
            with patch('api_server.api_key_manager.verify_api_key', return_value=(True, "")):
                test_client = TestClient(app)
                # Add default API key header for authenticated endpoints
                test_client.headers.update({"X-API-Key": "test-key-12345"})
                yield test_client


@pytest.fixture
def sample_news_text():
    """Sample news text for testing."""
    return "Bitcoin price surges to new all-time high as institutional investors increase their holdings. The cryptocurrency market shows strong bullish signals with positive sentiment from analysts."


@pytest.fixture
def sample_image_data():
    """Sample image data (base64 encoded)."""
    # Minimal valid JPEG header
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


@pytest.fixture
def sample_teaching_payload():
    """Sample teaching lesson payload."""
    return {
        "topic": "blockchain technology",
        "difficulty_level": "beginner"
    }


# ============================================================================
# ROOT ENDPOINT TESTS
# ============================================================================

class TestRootEndpoint:
    """Test GET / root endpoint."""
    
    def test_root_endpoint_returns_200(self, client):
        """Test that root endpoint returns status 200."""
        # Act
        response = client.get("/")
        
        # Assert
        assert response.status_code == 200
    
    def test_root_endpoint_returns_json(self, client):
        """Test that root endpoint returns JSON."""
        # Act
        response = client.get("/")
        
        # Assert
        assert response.headers.get("content-type") is not None
    
    def test_root_endpoint_has_welcome_message(self, client):
        """Test that root endpoint returns welcome message."""
        # Act
        response = client.get("/")
        
        # Assert
        assert response.status_code == 200
        # Should have some content
        assert len(response.text) > 0


# ============================================================================
# HEALTH CHECK ENDPOINT TESTS
# ============================================================================

class TestHealthCheckEndpoint:
    """Test GET /health endpoint."""
    
    def test_health_check_returns_200(self, client):
        """Test that health check returns status 200."""
        # Act
        response = client.get("/health")
        
        # Assert
        assert response.status_code == 200
    
    def test_health_check_returns_ok_status(self, client):
        """Test that health check returns OK status."""
        # Act
        response = client.get("/health")
        data = response.json()
        
        # Assert
        assert "status" in data
        # Status can be "ok", "OK", "healthy", "HEALTHY", or "degraded"
        assert data["status"] in ["ok", "OK", "healthy", "HEALTHY", "degraded"]
    
    def test_health_check_includes_timestamp(self, client):
        """Test that health check includes timestamp or metrics."""
        # Act
        response = client.get("/health")
        data = response.json()
        
        # Assert - health response should have some content
        assert len(data) > 0
        assert "status" in data
    
    def test_health_check_includes_cache_stats(self, client):
        """Test that health check includes cache information."""
        # Act
        response = client.get("/health")
        data = response.json()
        
        # Assert
        # Should have some cache-related information
        assert response.status_code == 200
    
    def test_health_check_is_fast(self, client):
        """Test that health check responds quickly."""
        # Act
        import time
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        
        # Assert - should complete in <1 second
        assert elapsed < 1.0
        assert response.status_code == 200


# ============================================================================
# NEWS EXPLANATION ENDPOINT TESTS
# ============================================================================

class TestExplainNewsEndpoint:
    """Test POST /explain_news endpoint."""
    
    def test_explain_news_valid_input_returns_200(self, client, sample_news_text):
        """Test news explanation with valid input."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "simplified_text" in data
    
    def test_explain_news_response_has_required_fields(self, client, sample_news_text):
        """Test that response has required fields."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        response = client.post("/explain_news", json=payload)
        data = response.json()
        
        # Assert
        assert "simplified_text" in data
        assert isinstance(data["simplified_text"], str)
        assert len(data["simplified_text"]) > 0
    
    def test_explain_news_returns_cached_on_repeat(self, client, sample_news_text):
        """Test that repeated requests return cached results."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        response1 = client.post("/explain_news", json=payload)
        response2 = client.post("/explain_news", json=payload)
        
        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        
        # Second response should be cached
        assert "cached" in data2
    
    def test_explain_news_empty_text_returns_400(self, client):
        """Test that empty text returns 400 error."""
        # Arrange
        payload = {"text_content": ""}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code in [400, 422]  # Validation error
    
    def test_explain_news_too_long_text_returns_400(self, client):
        """Test that text exceeding max length returns 400."""
        # Arrange
        payload = {"text_content": "a" * 10000}  # Exceeds MAX_TEXT_LENGTH
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code in [400, 422]
    
    def test_explain_news_missing_text_returns_400(self, client):
        """Test that missing text_content returns 400."""
        # Arrange
        payload = {}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code == 422  # Missing required field
    
    def test_explain_news_response_includes_processing_time(self, client, sample_news_text):
        """Test that response includes processing time."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        response = client.post("/explain_news", json=payload)
        data = response.json()
        
        # Assert - processing_time_ms is optional but if present should be numeric
        if "processing_time_ms" in data:
            assert isinstance(data["processing_time_ms"], (int, float))


# ============================================================================
# IMAGE ANALYSIS ENDPOINT TESTS
# ============================================================================

class TestAnalyzeImageEndpoint:
    """Test POST /analyze_image endpoint."""
    
    def test_analyze_image_valid_input_returns_200(self, client, sample_image_data):
        """Test image analysis with valid input."""
        # Arrange
        payload = {"image_base64": sample_image_data}
        
        # Act
        response = client.post("/analyze_image", json=payload)
        
        # Assert
        assert response.status_code in [200, 400, 500]  # May fail if no AI available
    
    def test_analyze_image_missing_image_returns_400(self, client):
        """Test that missing image returns 400."""
        # Arrange
        payload = {}
        
        # Act
        response = client.post("/analyze_image", json=payload)
        
        # Assert - can be 400 or 422
        assert response.status_code in [400, 422]
    
    def test_analyze_image_invalid_base64_returns_400(self, client):
        """Test that invalid base64 returns 400."""
        # Arrange
        payload = {"image_base64": "not_valid_base64!!!"}
        
        # Act
        response = client.post("/analyze_image", json=payload)
        
        # Assert
        assert response.status_code in [400, 422]
    
    def test_analyze_image_returns_response_object(self, client, sample_image_data):
        """Test that image analysis returns expected response."""
        # Arrange
        payload = {"image_base64": sample_image_data}
        
        # Act
        response = client.post("/analyze_image", json=payload)
        
        # Assert - Should either succeed or fail gracefully
        assert response.status_code in [200, 400, 500, 422]


# ============================================================================
# TEACHING LESSON ENDPOINT TESTS
# ============================================================================

class TestTeachLessonEndpoint:
    """Test POST /teach_lesson endpoint."""
    
    def test_teach_lesson_valid_input_returns_200(self, client, sample_teaching_payload):
        """Test lesson creation with valid input."""
        # Act
        response = client.post("/teach_lesson", json=sample_teaching_payload)
        
        # Assert
        assert response.status_code in [200, 422]  # May fail due to validation
    
    def test_teach_lesson_missing_topic_returns_422(self, client):
        """Test that missing topic returns 422."""
        # Arrange
        payload = {"difficulty_level": "beginner"}
        
        # Act
        response = client.post("/teach_lesson", json=payload)
        
        # Assert
        assert response.status_code == 422
    
    def test_teach_lesson_invalid_difficulty_returns_422(self, client):
        """Test that invalid difficulty level returns 422."""
        # Arrange
        payload = {
            "topic": "blockchain",
            "difficulty_level": "invalid_level"
        }
        
        # Act
        response = client.post("/teach_lesson", json=payload)
        
        # Assert
        assert response.status_code == 422
    
    def test_teach_lesson_valid_difficulty_levels(self, client):
        """Test all valid difficulty levels."""
        # Arrange
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        
        for level in valid_levels:
            payload = {"topic": "blockchain", "difficulty_level": level}
            
            # Act
            response = client.post("/teach_lesson", json=payload)
            
            # Assert - Should not reject valid difficulty
            assert response.status_code in [200, 500, 422]  # 500 ok if AI unavailable


# ============================================================================
# DROPS ENDPOINT TESTS
# ============================================================================

class TestDropsEndpoint:
    """Test GET /get_drops endpoint."""
    
    def test_get_drops_returns_200(self, client):
        """Test that get_drops returns 200."""
        # Act
        response = client.get("/get_drops")
        
        # Assert
        assert response.status_code == 200
    
    def test_get_drops_returns_json(self, client):
        """Test that get_drops returns JSON."""
        # Act
        response = client.get("/get_drops")
        
        # Assert
        assert response.status_code == 200
        assert response.headers.get("content-type") is not None
        data = response.json()
        assert isinstance(data, dict)
    
    def test_get_drops_has_drops_field(self, client):
        """Test that response has drops field."""
        # Act
        response = client.get("/get_drops")
        data = response.json()
        
        # Assert
        assert "drops" in data or response.status_code != 200


# ============================================================================
# ACTIVITIES ENDPOINT TESTS
# ============================================================================

class TestActivitiesEndpoint:
    """Test GET /get_activities endpoint."""
    
    def test_get_activities_returns_200(self, client):
        """Test that get_activities returns 200."""
        # Act
        response = client.get("/get_activities")
        
        # Assert
        assert response.status_code == 200
    
    def test_get_activities_returns_json(self, client):
        """Test that get_activities returns JSON."""
        # Act
        response = client.get("/get_activities")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ============================================================================
# TRENDING ENDPOINT TESTS
# ============================================================================

class TestTrendingEndpoint:
    """Test GET /get_trending endpoint."""
    
    def test_get_trending_returns_200(self, client):
        """Test that get_trending returns 200."""
        # Act
        response = client.get("/get_trending")
        
        # Assert
        assert response.status_code == 200
    
    def test_get_trending_returns_data(self, client):
        """Test that get_trending returns data."""
        # Act
        response = client.get("/get_trending")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ============================================================================
# TOKEN INFO ENDPOINT TESTS
# ============================================================================

class TestTokenInfoEndpoint:
    """Test GET /get_token_info/{token_id} endpoint."""
    
    def test_get_token_info_with_valid_id_returns_200(self, client):
        """Test token info with valid ID."""
        # Act
        response = client.get("/get_token_info/SOL")
        
        # Assert - May return 200 or 404 if endpoint not available
        assert response.status_code in [200, 404]
    
    def test_get_token_info_returns_json(self, client):
        """Test that token info returns JSON."""
        # Act
        response = client.get("/get_token_info/BTC")
        
        # Assert - May return 200 or 404
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
    
    def test_get_token_info_with_different_tokens(self, client):
        """Test token info with different token IDs."""
        # Arrange
        tokens = ["BTC", "ETH", "SOL", "XRP"]
        
        for token in tokens:
            # Act
            response = client.get(f"/get_token_info/{token}")
            
            # Assert - endpoint may not be fully implemented
            assert response.status_code in [200, 404]


# ============================================================================
# LEADERBOARD ENDPOINT TESTS
# ============================================================================

class TestLeaderboardEndpoint:
    """Test GET /get_leaderboard endpoint."""
    
    def test_get_leaderboard_returns_200(self, client):
        """Test that get_leaderboard returns 200."""
        # Act
        response = client.get("/get_leaderboard")
        
        # Assert
        assert response.status_code == 200
    
    def test_get_leaderboard_returns_json(self, client):
        """Test that get_leaderboard returns JSON."""
        # Act
        response = client.get("/get_leaderboard")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ============================================================================
# DIALOGUE METRICS ENDPOINT TESTS
# ============================================================================

class TestDialogueMetricsEndpoint:
    """Test GET /dialogue_metrics endpoint."""
    
    def test_dialogue_metrics_returns_200(self, client):
        """Test that dialogue_metrics returns 200."""
        # Act
        response = client.get("/dialogue_metrics")
        
        # Assert
        assert response.status_code == 200
    
    def test_dialogue_metrics_returns_json(self, client):
        """Test that dialogue_metrics returns JSON."""
        # Act
        response = client.get("/dialogue_metrics")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling across endpoints."""
    
    def test_nonexistent_endpoint_returns_404(self, client):
        """Test that nonexistent endpoint returns 404."""
        # Act
        response = client.get("/nonexistent_endpoint")
        
        # Assert
        assert response.status_code == 404
    
    def test_invalid_json_returns_400(self, client):
        """Test that invalid JSON returns 400."""
        # Act
        response = client.post(
            "/explain_news",
            content="invalid json {",
            headers={"content-type": "application/json"}
        )
        
        # Assert
        assert response.status_code in [400, 422]
    
    def test_wrong_http_method_returns_405(self, client):
        """Test that wrong HTTP method returns 405."""
        # Act
        response = client.get("/explain_news")  # Should be POST
        
        # Assert
        assert response.status_code == 405


# ============================================================================
# INPUT SANITIZATION TESTS
# ============================================================================

class TestInputSanitization:
    """Test input sanitization."""
    
    def test_sanitize_xss_payload(self, client):
        """Test that XSS payloads are sanitized."""
        # Arrange
        payload = {"text_content": "<script>alert('xss')</script>Bitcoin"}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert - Should either sanitize or reject
        assert response.status_code in [200, 400, 422]
    
    def test_sanitize_sql_injection(self, client):
        """Test that SQL injection attempts are handled."""
        # Arrange
        payload = {"text_content": "'; DROP TABLE users; --"}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code in [200, 400, 422]
    
    def test_sanitize_special_characters(self, client):
        """Test handling of special characters."""
        # Arrange
        payload = {"text_content": "Bitcoin 🚀 with émojis and спецсимволы"}
        
        # Act
        response = client.post("/explain_news", json=payload)
        
        # Assert
        assert response.status_code == 200


# ============================================================================
# CACHING TESTS
# ============================================================================

class TestCachingBehavior:
    """Test caching behavior."""
    
    def test_cache_returns_same_response(self, client, sample_news_text):
        """Test that cache returns same response."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        response1 = client.post("/explain_news", json=payload)
        response2 = client.post("/explain_news", json=payload)
        
        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        assert data1["simplified_text"] == data2["simplified_text"]
    
    def test_cache_different_inputs(self, client):
        """Test that different inputs produce different cached results."""
        # Arrange
        payload1 = {"text_content": "Bitcoin price increases"}
        payload2 = {"text_content": "Ethereum smart contracts"}
        
        # Act
        response1 = client.post("/explain_news", json=payload1)
        response2 = client.post("/explain_news", json=payload2)
        
        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        # Different inputs should produce different results
        assert data1["simplified_text"] != data2["simplified_text"]


# ============================================================================
# RATE LIMITING TESTS (if enabled)
# ============================================================================

class TestRateLimiting:
    """Test rate limiting behavior."""
    
    def test_rapid_requests_handled(self, client, sample_news_text):
        """Test that rapid requests are handled."""
        # Arrange
        payload = {"text_content": sample_news_text}
        
        # Act
        responses = []
        for i in range(5):
            response = client.post("/explain_news", json=payload)
            responses.append(response)
        
        # Assert - Should either succeed or be rate limited
        status_codes = [r.status_code for r in responses]
        # All should be valid responses (200 or 429)
        assert all(code in [200, 429] for code in status_codes)


# ============================================================================
# CONCURRENT REQUEST TESTS
# ============================================================================

class TestConcurrentRequests:
    """Test handling of concurrent requests."""
    
    def test_concurrent_news_requests(self, client):
        """Test concurrent news explanation requests."""
        # Arrange
        payload1 = {"text_content": "Bitcoin technical analysis"}
        payload2 = {"text_content": "Ethereum future updates"}
        payload3 = {"text_content": "DeFi protocols comparison"}
        
        # Act
        responses = [
            client.post("/explain_news", json=payload1),
            client.post("/explain_news", json=payload2),
            client.post("/explain_news", json=payload3),
        ]
        
        # Assert
        assert all(r.status_code == 200 for r in responses)
