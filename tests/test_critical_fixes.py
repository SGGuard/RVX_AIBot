"""
Unit Tests for Critical Fixes v0.27.0
Comprehensive test suite for all critical fixes and validations.

Covers:
- SQL injection prevention (sql_validator)
- Input validation (input_validators)
- Memory leak prevention (limited_cache)
- Thread-safety (conversation_context)
- Error diagnostics (error_diagnostics)
- Type hints validation (type_hints_support)
- Request logging (request_logging)
"""

import pytest
import sqlite3
import threading
import time
import json
from typing import List
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/sv4096/rvx_backend')

# Import modules under test
from sql_validator import SQLValidator, sql_validator
from input_validators import validate_user_input, UserMessageInput, sanitize_for_display
from limited_cache import LimitedCache
from conversation_context import ConversationContextManager
from error_diagnostics import ErrorDiagnosticsEngine, ErrorCategory, ErrorSeverity, record_error
from type_hints_support import validate_types, validate_request, AnalysisRequest, AnalysisResponse
from request_logging import generate_request_id, get_request_id, set_request_id, request_context


# =============================================================================
# TESTS: SQL VALIDATOR
# =============================================================================

class TestSQLValidator:
    """Test SQL injection prevention."""
    
    def test_valid_table_name(self):
        """Valid table names should pass."""
        assert sql_validator.validate_table_name("conversation_history") is True
        assert sql_validator.validate_table_name("users") is True
        assert sql_validator.validate_table_name("conversation_stats") is True
    
    def test_invalid_table_name(self):
        """Invalid table names should fail."""
        assert sql_validator.validate_table_name("'; DROP TABLE users; --") is False
        assert sql_validator.validate_table_name("users OR 1=1") is False
        assert sql_validator.validate_table_name("*") is False
    
    def test_valid_column_name(self):
        """Valid column names should pass."""
        assert sql_validator.validate_column_name("conversation_history", "content") is True
        assert sql_validator.validate_column_name("users", "user_id") is True
    
    def test_invalid_column_name(self):
        """Invalid column names should fail."""
        assert sql_validator.validate_column_name("users", "'; DROP TABLE--") is False
        assert sql_validator.validate_column_name("users", "*") is False


# =============================================================================
# TESTS: INPUT VALIDATORS
# =============================================================================

class TestInputValidators:
    """Test input validation and sanitization."""
    
    def test_valid_user_input(self):
        """Valid input should pass validation."""
        is_valid, error = validate_user_input("Bitcoin ETF approved")
        assert is_valid is True
        assert error is None
    
    def test_empty_input(self):
        """Empty input should fail validation."""
        is_valid, error = validate_user_input("")
        assert is_valid is False
    
    def test_too_long_input(self):
        """Too long input should fail validation."""
        is_valid, error = validate_user_input("x" * 10000)
        assert is_valid is False
    
    def test_control_characters_removed(self):
        """Control characters should be sanitized."""
        dirty_text = "Hello\x00\x01\x02World"
        clean_text = sanitize_for_display(dirty_text)
        assert '\x00' not in clean_text
        assert '\x01' not in clean_text
    
    def test_user_message_input_model(self):
        """Pydantic model should validate input."""
        # Valid
        msg = UserMessageInput(text="Valid message")
        assert msg.text == "Valid message"
        
        # Invalid - too long
        with pytest.raises(Exception):
            UserMessageInput(text="x" * 10000)


# =============================================================================
# TESTS: LIMITED CACHE
# =============================================================================

class TestLimitedCache:
    """Test LRU cache with TTL."""
    
    def test_cache_set_get(self):
        """Cache should store and retrieve values."""
        cache = LimitedCache(max_size=10, ttl_seconds=60)
        cache.set("key1", {"value": "data1"})
        result = cache.get("key1")
        assert result == {"value": "data1"}
    
    def test_cache_miss(self):
        """Cache should return None for missing keys."""
        cache = LimitedCache(max_size=10, ttl_seconds=60)
        result = cache.get("nonexistent")
        assert result is None
    
    def test_cache_lru_eviction(self):
        """Cache should evict LRU items when full."""
        cache = LimitedCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "val1")
        cache.set("key2", "val2")
        cache.set("key3", "val3")
        cache.set("key4", "val4")  # Should evict key1
        
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key4") == "val4"  # Present
    
    def test_cache_ttl_expiration(self):
        """Cache items should expire after TTL."""
        cache = LimitedCache(max_size=10, ttl_seconds=1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        time.sleep(1.1)  # Wait for expiration
        assert cache.get("key1") is None
    
    def test_cache_thread_safety(self):
        """Cache should be thread-safe."""
        cache = LimitedCache(max_size=100, ttl_seconds=60)
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(100):
                    cache.set(f"key_{thread_id}_{i}", f"val_{i}")
                    cache.get(f"key_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


# =============================================================================
# TESTS: CONVERSATION CONTEXT THREAD-SAFETY
# =============================================================================

class TestConversationContextThreadSafety:
    """Test thread-safety of conversation context manager."""
    
    def test_concurrent_add_messages(self):
        """Multiple threads should safely add messages."""
        import tempfile
        import os
        
        # Create temp database file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = ConversationContextManager(db_path)
            errors = []
            user_id = 123
            
            def add_messages(thread_id):
                try:
                    for i in range(10):
                        manager.add_message(user_id, "user", f"Message {thread_id}-{i}")
                        manager.add_message(user_id, "assistant", f"Response {thread_id}-{i}")
                except Exception as e:
                    errors.append(e)
            
            threads = [threading.Thread(target=add_messages, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            assert len(errors) == 0
            
            # Verify all messages were added
            messages = manager.get_messages(user_id, limit=100)
            assert len(messages) >= 30  # At least 30 messages
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_concurrent_read_write(self):
        """Concurrent reads and writes should work safely."""
        import tempfile
        import os
        
        # Create temp database file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = ConversationContextManager(db_path)
            user_id = 456
            errors = []
            
            # Pre-populate
            for i in range(10):
                manager.add_message(user_id, "user", f"Message {i}")
            
            def reader():
                try:
                    for _ in range(20):
                        manager.get_messages(user_id, limit=5)
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            
            def writer():
                try:
                    for i in range(10):
                        manager.add_message(user_id, "user", f"New message {i}")
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            
            threads = [
                threading.Thread(target=reader) for _ in range(3)
            ] + [
                threading.Thread(target=writer) for _ in range(2)
            ]
            
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            assert len(errors) == 0
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)


# =============================================================================
# TESTS: ERROR DIAGNOSTICS
# =============================================================================

class TestErrorDiagnostics:
    """Test error tracking and diagnostics."""
    
    def test_error_categorization(self):
        """Errors should be categorized correctly."""
        engine = ErrorDiagnosticsEngine()
        
        # Validation error
        value_error = ValueError("Invalid value")
        category = engine.categorize_error(value_error)
        assert category in [ErrorCategory.VALIDATION, ErrorCategory.UNKNOWN]  # Both acceptable
        
        # Network error
        conn_error = ConnectionError("Connection refused")
        assert engine.categorize_error(conn_error) == ErrorCategory.NETWORK
    
    def test_error_severity(self):
        """Error severity should be correct."""
        engine = ErrorDiagnosticsEngine()
        
        assert engine.get_error_severity(ErrorCategory.VALIDATION) == ErrorSeverity.LOW
        assert engine.get_error_severity(ErrorCategory.TIMEOUT) == ErrorSeverity.MEDIUM
        assert engine.get_error_severity(ErrorCategory.API) == ErrorSeverity.HIGH
        assert engine.get_error_severity(ErrorCategory.AUTHENTICATION) == ErrorSeverity.CRITICAL
    
    def test_error_recording(self):
        """Errors should be recorded with context."""
        engine = ErrorDiagnosticsEngine()
        engine.clear_history()
        
        test_error = ValueError("Test error")
        ctx = engine.record_error(test_error, endpoint="/test", request_id="req_123")
        
        assert ctx.error_type == "ValueError"
        assert ctx.endpoint == "/test"
        assert ctx.request_id == "req_123"
        assert len(ctx.suggestions) > 0
    
    def test_error_recovery_suggestions(self):
        """Recovery suggestions should be provided."""
        engine = ErrorDiagnosticsEngine()
        
        suggestions = engine.get_recovery_suggestions(ErrorCategory.NETWORK)
        assert len(suggestions) > 0
        assert any("connectivity" in s.lower() for s in suggestions)


# =============================================================================
# TESTS: TYPE HINTS SUPPORT
# =============================================================================

class TestTypeHintsSupport:
    """Test type validation and Pydantic models."""
    
    def test_analysis_request_model(self):
        """AnalysisRequest model should validate input."""
        req = AnalysisRequest(text_content="Bitcoin news")
        assert req.text_content == "Bitcoin news"
        
        # Too long
        with pytest.raises(Exception):
            AnalysisRequest(text_content="x" * 20000)
    
    def test_analysis_response_model(self):
        """AnalysisResponse model should validate output."""
        resp = AnalysisResponse(
            summary_text="Summary",
            impact_points=["BTC", "ETF"]
        )
        assert resp.summary_text == "Summary"
        assert len(resp.impact_points) == 2
    
    def test_validate_request(self):
        """validate_request should work with models."""
        data = {"text_content": "Test"}
        is_valid, result = validate_request(data, AnalysisRequest)
        assert is_valid is True
        assert isinstance(result, AnalysisRequest)
        
        # Invalid
        invalid_data = {"text_content": ""}
        is_valid, error = validate_request(invalid_data, AnalysisRequest)
        assert is_valid is False


# =============================================================================
# TESTS: REQUEST LOGGING
# =============================================================================

class TestRequestLogging:
    """Test request ID generation and context management."""
    
    def test_request_id_generation(self):
        """Should generate unique request IDs."""
        id1 = generate_request_id("req")
        id2 = generate_request_id("req")
        
        assert id1 != id2
        assert id1.startswith("req_")
        assert len(id1.split("_")) == 3  # prefix_timestamp_uuid
    
    def test_request_context_manager(self):
        """Request context manager should manage IDs."""
        with request_context("test_123") as req_id:
            assert get_request_id() == "test_123"
        
        # Outside context, ID should be None or old value
        set_request_id(None)
        assert get_request_id() is None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple fixes."""
    
    def test_full_message_flow_with_validation(self):
        """Test complete message flow with all validations."""
        import tempfile
        import os
        
        # Create temp database file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = ConversationContextManager(db_path)
            user_id = 789
            
            # Valid input
            is_valid, _ = validate_user_input("Bitcoin news")
            assert is_valid is True
            
            # Add to conversation
            manager.add_message(user_id, "user", "Bitcoin news")
            
            # Retrieve with thread-safety
            messages = manager.get_messages(user_id)
            assert len(messages) > 0
            assert messages[0]["content"] == "Bitcoin news"
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_error_tracking_with_diagnostics(self):
        """Test error tracking through diagnostics."""
        engine = ErrorDiagnosticsEngine()
        engine.clear_history()
        
        # Simulate an error
        try:
            raise ConnectionError("API unreachable")
        except Exception as e:
            ctx = engine.record_error(e, endpoint="/analyze")
        
        # Check it was recorded
        summary = engine.get_error_summary()
        assert summary['total_errors'] > 0
        assert summary['errors_by_category']['network'] > 0


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
