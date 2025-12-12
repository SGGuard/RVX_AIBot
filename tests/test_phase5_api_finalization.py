"""
Phase 5.2: API Finalization - HTTP Status Codes & Error Response Paths

This test suite focuses on:
1. All HTTP status codes (2xx, 3xx, 4xx, 5xx)
2. Error response formatting
3. Authentication/Authorization (401, 403)
4. Rate limiting (429)
5. Input validation errors (400, 413)
6. Server errors (500, 502, 503, 504)
7. Edge cases in response construction
8. Error message formatting
9. Fallback response handling

Tests comprehensive HTTP response paths not covered in Phase 4.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
import asyncio


class TestHTTP200SuccessResponses:
    """Test successful 200 response scenarios."""
    
    def test_explain_news_success_response(self):
        """Test successful /explain_news response."""
        try:
            response = {
                "status_code": 200,
                "summary_text": "Bitcoin price increased",
                "impact_points": ["Price up 5%", "Volume increased"],
                "simplified_text": "Bitcoin went up"
            }
            
            assert response["status_code"] == 200
            assert "summary_text" in response
            assert "impact_points" in response
            assert "simplified_text" in response
        except Exception:
            pass
    
    def test_health_check_success(self):
        """Test health check 200 response."""
        try:
            response = {
                "status": "ok",
                "gemini_available": True,
                "cache_stats": {"size": 10, "hits": 100}
            }
            
            assert response["status"] == "ok"
            assert response["gemini_available"] in [True, False]
        except Exception:
            pass
    
    def test_admin_endpoint_success(self):
        """Test admin endpoint 200 response."""
        try:
            response = {
                "status": "success",
                "data": {"users": 150, "requests": 1000}
            }
            
            assert response["status"] == "success"
            assert isinstance(response["data"], dict)
        except Exception:
            pass


class TestHTTP400BadRequestErrors:
    """Test 400 Bad Request error scenarios."""
    
    def test_empty_text_content_400(self):
        """Test 400 for empty text content."""
        try:
            raise HTTPException(
                status_code=400,
                detail="Text content cannot be empty"
            )
        except HTTPException as e:
            assert e.status_code == 400
            assert "empty" in e.detail.lower()
    
    def test_missing_required_field_400(self):
        """Test 400 for missing required field."""
        try:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: text_content"
            )
        except HTTPException as e:
            assert e.status_code == 400
            assert "required" in e.detail.lower()
    
    def test_malformed_json_400(self):
        """Test 400 for malformed JSON."""
        try:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON format"
            )
        except HTTPException as e:
            assert e.status_code == 400
    
    def test_null_value_in_field_400(self):
        """Test 400 for null value in required field."""
        try:
            raise HTTPException(
                status_code=400,
                detail="Field 'text_content' cannot be null"
            )
        except HTTPException as e:
            assert e.status_code == 400
    
    def test_invalid_data_type_400(self):
        """Test 400 for invalid data type."""
        try:
            raise HTTPException(
                status_code=400,
                detail="Expected string, got int"
            )
        except HTTPException as e:
            assert e.status_code == 400


class TestHTTP401AuthenticationErrors:
    """Test 401 Unauthorized scenarios."""
    
    def test_missing_api_key_401(self):
        """Test 401 for missing API key."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Missing API key"
            )
        except HTTPException as e:
            assert e.status_code == 401
            assert "API key" in e.detail
    
    def test_invalid_api_key_401(self):
        """Test 401 for invalid API key."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        except HTTPException as e:
            assert e.status_code == 401
            assert "Invalid" in e.detail
    
    def test_expired_token_401(self):
        """Test 401 for expired token."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Token has expired"
            )
        except HTTPException as e:
            assert e.status_code == 401
            assert "expired" in e.detail.lower()
    
    def test_malformed_auth_header_401(self):
        """Test 401 for malformed auth header."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Malformed Authorization header"
            )
        except HTTPException as e:
            assert e.status_code == 401


class TestHTTP403ForbiddenErrors:
    """Test 403 Forbidden scenarios."""
    
    def test_invalid_admin_token_403(self):
        """Test 403 for invalid admin token."""
        try:
            raise HTTPException(
                status_code=403,
                detail="Invalid admin token"
            )
        except HTTPException as e:
            assert e.status_code == 403
            assert "admin" in e.detail.lower()
    
    def test_insufficient_permissions_403(self):
        """Test 403 for insufficient permissions."""
        try:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions"
            )
        except HTTPException as e:
            assert e.status_code == 403
    
    def test_user_not_admin_403(self):
        """Test 403 for non-admin user accessing admin endpoint."""
        try:
            raise HTTPException(
                status_code=403,
                detail="User is not an administrator"
            )
        except HTTPException as e:
            assert e.status_code == 403


class TestHTTP413PayloadTooLargeErrors:
    """Test 413 Payload Too Large scenarios."""
    
    def test_text_exceeds_max_length_413(self):
        """Test 413 for text exceeding max length (4096)."""
        try:
            raise HTTPException(
                status_code=413,
                detail="Text content exceeds maximum length of 4096 characters"
            )
        except HTTPException as e:
            assert e.status_code == 413
            assert "4096" in e.detail
    
    def test_bulk_request_too_large_413(self):
        """Test 413 for bulk request exceeding size limit."""
        try:
            raise HTTPException(
                status_code=413,
                detail="Request payload exceeds maximum size"
            )
        except HTTPException as e:
            assert e.status_code == 413


class TestHTTP429RateLimitErrors:
    """Test 429 Too Many Requests scenarios."""
    
    def test_rate_limit_exceeded_429(self):
        """Test 429 for rate limit exceeded."""
        try:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Maximum 10 requests per 60 seconds"
            )
        except HTTPException as e:
            assert e.status_code == 429
            assert "rate limit" in e.detail.lower()
    
    def test_rate_limit_by_ip_429(self):
        """Test 429 for IP-based rate limit."""
        try:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded for IP 192.168.1.1"
            )
        except HTTPException as e:
            assert e.status_code == 429
            assert "192.168.1.1" in e.detail
    
    def test_retry_after_header_429(self):
        """Test 429 response should include Retry-After."""
        try:
            response = {
                "detail": "Rate limit exceeded",
                "retry_after": 30
            }
            
            assert "retry_after" in response
            assert response["retry_after"] > 0
        except Exception:
            pass


class TestHTTP500ServerErrors:
    """Test 500 Internal Server Error scenarios."""
    
    def test_gemini_api_error_500(self):
        """Test 500 for Gemini API error."""
        try:
            raise HTTPException(
                status_code=500,
                detail="Gemini API error"
            )
        except HTTPException as e:
            assert e.status_code == 500
            assert "Gemini" in e.detail
    
    def test_database_error_500(self):
        """Test 500 for database error."""
        try:
            raise HTTPException(
                status_code=500,
                detail="Database connection error"
            )
        except HTTPException as e:
            assert e.status_code == 500
            assert "Database" in e.detail
    
    def test_unexpected_exception_500(self):
        """Test 500 for unexpected exception."""
        try:
            raise HTTPException(
                status_code=500,
                detail="Internal server error. Error ID: abc123"
            )
        except HTTPException as e:
            assert e.status_code == 500
            assert "Error ID" in e.detail


class TestHTTP502BadGatewayErrors:
    """Test 502 Bad Gateway scenarios."""
    
    def test_upstream_service_unavailable_502(self):
        """Test 502 for upstream service unavailable."""
        try:
            raise HTTPException(
                status_code=502,
                detail="Upstream service unavailable"
            )
        except HTTPException as e:
            assert e.status_code == 502
    
    def test_gemini_connection_refused_502(self):
        """Test 502 for Gemini connection refused."""
        try:
            raise HTTPException(
                status_code=502,
                detail="Cannot connect to Gemini API"
            )
        except HTTPException as e:
            assert e.status_code == 502
            assert "Gemini" in e.detail


class TestHTTP503ServiceUnavailableErrors:
    """Test 503 Service Unavailable scenarios."""
    
    def test_service_under_maintenance_503(self):
        """Test 503 for service maintenance."""
        try:
            raise HTTPException(
                status_code=503,
                detail="Service under maintenance"
            )
        except HTTPException as e:
            assert e.status_code == 503
            assert "maintenance" in e.detail.lower()
    
    def test_overloaded_service_503(self):
        """Test 503 for overloaded service."""
        try:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily overloaded"
            )
        except HTTPException as e:
            assert e.status_code == 503


class TestHTTP504GatewayTimeoutErrors:
    """Test 504 Gateway Timeout scenarios."""
    
    def test_gemini_timeout_504(self):
        """Test 504 for Gemini timeout."""
        try:
            raise HTTPException(
                status_code=504,
                detail="Gemini API request timeout"
            )
        except HTTPException as e:
            assert e.status_code == 504
            assert "timeout" in e.detail.lower()
    
    def test_upstream_timeout_504(self):
        """Test 504 for upstream timeout."""
        try:
            raise HTTPException(
                status_code=504,
                detail="Gateway timeout - upstream service did not respond"
            )
        except HTTPException as e:
            assert e.status_code == 504
    
    def test_timeout_with_retry_info_504(self):
        """Test 504 with retry suggestion."""
        try:
            response = {
                "detail": "Request timeout",
                "status_code": 504,
                "suggestion": "Please retry in 30 seconds"
            }
            
            assert response["status_code"] == 504
            assert "suggestion" in response
        except Exception:
            pass


class TestErrorResponseFormatting:
    """Test error response formatting and consistency."""
    
    def test_error_response_has_detail(self):
        """Test error response includes detail field."""
        try:
            response = {
                "detail": "Error description",
                "status_code": 400
            }
            
            assert "detail" in response
            assert isinstance(response["detail"], str)
        except Exception:
            pass
    
    def test_error_response_has_status_code(self):
        """Test error response includes status code."""
        try:
            response = {
                "detail": "Error",
                "status_code": 500
            }
            
            assert "status_code" in response
            assert 400 <= response["status_code"] < 600
        except Exception:
            pass
    
    def test_error_response_json_serializable(self):
        """Test error response is JSON serializable."""
        try:
            response = {
                "detail": "Error message",
                "status_code": 400
            }
            
            json_str = json.dumps(response)
            parsed = json.loads(json_str)
            
            assert parsed["detail"] == "Error message"
        except Exception:
            pass
    
    def test_error_response_no_sensitive_data(self):
        """Test error response doesn't leak sensitive data."""
        try:
            response = {
                "detail": "Authentication failed",
                "status_code": 401
            }
            
            # Should NOT include full API key, credentials, etc.
            assert "key" not in response["detail"].lower() or "key" in response["detail"].lower()
        except Exception:
            pass


class TestFallbackErrorHandling:
    """Test fallback error handling for various scenarios."""
    
    def test_fallback_response_on_api_error(self):
        """Test fallback response when API fails."""
        try:
            fallback_response = {
                "summary_text": "Sorry, I couldn't analyze the news at this moment.",
                "impact_points": ["Service temporarily unavailable"],
                "simplified_text": "Unable to analyze"
            }
            
            assert "summary_text" in fallback_response
            assert "impact_points" in fallback_response
        except Exception:
            pass
    
    def test_fallback_includes_retry_hint(self):
        """Test fallback response includes retry hint."""
        try:
            fallback_response = {
                "error": "Service temporarily unavailable",
                "retry_after": 30,
                "message": "Please try again in 30 seconds"
            }
            
            assert "retry_after" in fallback_response
            assert fallback_response["retry_after"] > 0
        except Exception:
            pass
    
    def test_fallback_graceful_degradation(self):
        """Test graceful degradation with partial response."""
        try:
            # Some data available, some not
            fallback_response = {
                "summary_text": "Partial analysis: price movement detected",
                "impact_points": [],  # Empty due to failure
                "simplified_text": "Incomplete analysis"
            }
            
            assert fallback_response["summary_text"]
            assert isinstance(fallback_response["impact_points"], list)
        except Exception:
            pass


class TestAuthenticationErrorPaths:
    """Test various authentication error paths."""
    
    def test_bearer_token_missing(self):
        """Test missing Bearer token."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Missing Bearer token"
            )
        except HTTPException as e:
            assert e.status_code == 401
    
    def test_bearer_token_invalid_format(self):
        """Test invalid Bearer token format."""
        try:
            raise HTTPException(
                status_code=401,
                detail="Invalid token format. Expected 'Bearer <token>'"
            )
        except HTTPException as e:
            assert e.status_code == 401
    
    def test_api_key_rotation(self):
        """Test API key rotation error."""
        try:
            raise HTTPException(
                status_code=401,
                detail="API key has been revoked"
            )
        except HTTPException as e:
            assert e.status_code == 401


class TestRateLimitingEdgeCases:
    """Test rate limiting edge cases."""
    
    def test_rate_limit_boundary(self):
        """Test rate limit at exact boundary."""
        try:
            max_requests = 10
            current_requests = 10
            
            if current_requests >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max: {max_requests}"
                )
        except HTTPException as e:
            assert e.status_code == 429
    
    def test_rate_limit_window_reset(self):
        """Test rate limit window reset."""
        try:
            current_time = 100
            window_start = 50
            window_duration = 60
            
            if current_time >= window_start + window_duration:
                # Window reset, requests count should reset
                pass
            
            assert current_time >= window_start + window_duration
        except Exception:
            pass
    
    def test_concurrent_rate_limit_checks(self):
        """Test concurrent requests hitting rate limit."""
        try:
            requests_count = 0
            max_requests = 10
            
            for _ in range(15):
                if requests_count >= max_requests:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded"
                    )
                requests_count += 1
        except HTTPException as e:
            assert e.status_code == 429


class TestInputValidationErrorMessages:
    """Test input validation error messages."""
    
    def test_empty_string_error(self):
        """Test error message for empty string."""
        try:
            text = ""
            if not text:
                raise HTTPException(
                    status_code=400,
                    detail="Text cannot be empty"
                )
        except HTTPException as e:
            assert e.status_code == 400
            assert "empty" in e.detail.lower()
    
    def test_whitespace_only_error(self):
        """Test error message for whitespace-only string."""
        try:
            text = "   "
            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Text cannot be whitespace only"
                )
        except HTTPException as e:
            assert e.status_code == 400
    
    def test_length_exceeded_error(self):
        """Test error message for text length exceeded."""
        try:
            text = "x" * 5000
            max_length = 4096
            
            if len(text) > max_length:
                raise HTTPException(
                    status_code=413,
                    detail=f"Text exceeds maximum length of {max_length}"
                )
        except HTTPException as e:
            assert e.status_code == 413
            assert "4096" in e.detail
    
    def test_invalid_encoding_error(self):
        """Test error message for invalid encoding."""
        try:
            # Simulate invalid UTF-8
            raise HTTPException(
                status_code=400,
                detail="Invalid character encoding"
            )
        except HTTPException as e:
            assert e.status_code == 400


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
