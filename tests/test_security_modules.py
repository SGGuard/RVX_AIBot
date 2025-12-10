"""
🧪 Security Modules Test Suite
Tests for: security_manager, api_auth_manager, audit_logger, secrets_manager
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from security_manager import (
    SecurityManager, SecretManager, SecurityEvent, security_manager,
    validate_callback_data, validate_user_id, validate_request_size
)
from api_auth_manager import APIKeyManager, api_key_manager, init_auth_database
from audit_logger import AuditLogger, AuditEvent, audit_logger
from secrets_manager import SecretsManager, SafeLogger, secrets_manager
import logging

# =============================================================================
# SECURITY MANAGER TESTS
# =============================================================================

class TestSecurityManager:
    """Test security_manager module"""
    
    def test_singleton_instance(self):
        """Test that SecurityManager is a singleton"""
        manager1 = SecurityManager()
        manager2 = SecurityManager()
        assert manager1 is manager2
    
    def test_log_security_event(self):
        """Test logging security events"""
        manager = SecurityManager()
        
        event = SecurityEvent(
            event_type="test",
            severity="HIGH",
            user_id=123,
            action="test action",
            result="success"
        )
        
        manager.log_security_event(event)
        
        events = manager.security_events
        assert len(events) > 0
        assert events[-1].event_type == "test"
    
    def test_get_security_events_filtered(self):
        """Test retrieving security events with time filter"""
        manager = SecurityManager()
        
        # Add events
        for i in range(3):
            event = SecurityEvent(
                event_type="test",
                severity="MEDIUM",
                action=f"action {i}",
                result="success"
            )
            manager.log_security_event(event)
        
        # Get recent events
        recent = manager.get_security_events(hours=24)
        assert len(recent) >= 3
    
    def test_get_security_stats(self):
        """Test security statistics"""
        manager = SecurityManager()
        
        # Add events with different severities
        for severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            event = SecurityEvent(
                event_type="test",
                severity=severity,
                action="test",
                result="success"
            )
            manager.log_security_event(event)
        
        stats = manager.get_security_stats()
        assert "critical_count" in stats
        assert "high_count" in stats
        assert stats["critical_count"] >= 1

# =============================================================================
# SECRET MANAGER TESTS
# =============================================================================

class TestSecretManager:
    """Test SecretManager utilities"""
    
    def test_mask_api_key(self):
        """Test API key masking"""
        api_key = "test_key_1234567890abcdefghijklmnop"  # Not a real Stripe key
        masked = SecretManager.mask_api_key(api_key)
        
        assert "[REDACTED]" in masked or "..." in masked
        assert api_key not in masked
    
    def test_mask_sensitive_string(self):
        """Test general string masking"""
        secret = "my_super_secret_password"
        masked = SecretManager.mask_sensitive_string(secret)
        
        assert masked != secret
        # Should have ellipsis or REDACTED
        assert "..." in masked or "[REDACTED]" in masked
    
    def test_sanitize_log_message(self):
        """Test log message sanitization"""
        message = "API Key set to sk_live_1234567890 for user 123"
        sanitized = SecretManager.sanitize_log_message(message)
        
        assert "sk_live_1234567890" not in sanitized
        assert "[REDACTED" in sanitized
    
    def test_generate_secure_token(self):
        """Test secure token generation"""
        token1 = SecretManager.generate_secure_token()
        token2 = SecretManager.generate_secure_token()
        
        assert token1 != token2
        assert len(token1) > 20
        assert len(token2) > 20
    
    def test_hash_sensitive_data(self):
        """Test secure hashing"""
        data = "sensitive_password"
        hash1 = SecretManager.hash_sensitive_data(data)
        hash2 = SecretManager.hash_sensitive_data(data)
        
        # Same data should produce same hash
        assert hash1 == hash2
        # Hash should be long hex string
        assert len(hash1) == 64

# =============================================================================
# SECRETS MANAGER TESTS
# =============================================================================

class TestSecretsManager:
    """Test SecretsManager for secret detection"""
    
    def test_singleton_instance(self):
        """Test that SecretsManager is a singleton"""
        manager1 = SecretsManager()
        manager2 = SecretsManager()
        assert manager1 is manager2
    
    def test_register_secret(self):
        """Test registering a secret"""
        manager = SecretsManager()
        manager.register_secret("test_key", "super_secret_value_12345")
        
        # Should be in registry
        assert len(manager._registry.registered_secrets) > 0
    
    def test_is_secret_detection(self):
        """Test detecting secrets in strings"""
        manager = SecretsManager()
        
        # Should detect these patterns
        assert manager.is_secret("api_key = sk_live_1234567890abcdefgh")
        assert manager.is_secret("password: super_secret_password_123")
        assert manager.is_secret("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    
    def test_sanitize_string(self):
        """Test string sanitization"""
        manager = SecretsManager()
        text = "Connect with api_key=sk_live_1234567890abcdefgh to server"
        sanitized = manager.sanitize_string(text)
        
        assert "sk_live_" not in sanitized
        assert "[REDACTED" in sanitized
    
    def test_sanitize_dict(self):
        """Test dictionary sanitization"""
        manager = SecretsManager()
        data = {
            "username": "user123",
            "password": "super_secret_123",
            "api_key": "sk_live_abc123def456",
            "normal_field": "normal_value"
        }
        
        sanitized = manager.sanitize_dict(data)
        
        assert sanitized["username"] == "user123"
        assert sanitized["normal_field"] == "normal_value"
        assert sanitized["password"] != "super_secret_123"
        assert sanitized["api_key"] != "sk_live_abc123def456"
    
    def test_safe_logger(self):
        """Test SafeLogger wrapper"""
        logger_instance = logging.getLogger("test_logger")
        safe_logger = SafeLogger(logger_instance)
        
        # Should not raise
        safe_logger.info("API key: sk_live_secret123")
        safe_logger.error("Password error with token_xyz")

# =============================================================================
# API AUTH MANAGER TESTS
# =============================================================================

class TestAPIKeyManager:
    """Test APIKeyManager"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset manager before each test"""
        # Initialize clean database
        import os
        if os.path.exists("auth_keys.db"):
            os.remove("auth_keys.db")
        init_auth_database()
    
    def test_generate_api_key(self):
        """Test API key generation"""
        manager = APIKeyManager()
        
        api_key = manager.generate_api_key(
            key_name="Test Key",
            owner_name="Test Owner"
        )
        
        assert api_key.startswith("rvx_key_")
        assert len(api_key) > 20
    
    def test_verify_api_key(self):
        """Test API key verification"""
        manager = APIKeyManager()
        
        # Generate key
        api_key = manager.generate_api_key(
            key_name="Test Key",
            owner_name="Test Owner"
        )
        
        # Verify it
        is_valid, error = manager.verify_api_key(api_key)
        assert is_valid is True
        assert error is None
        
        # Verify wrong key
        is_valid, error = manager.verify_api_key("rvx_key_invalid_key")
        assert is_valid is False
        assert error is not None
    
    def test_get_api_key_info(self):
        """Test getting API key information"""
        manager = APIKeyManager()
        
        api_key = manager.generate_api_key(
            key_name="Test Key",
            owner_name="Test Owner",
            rate_limit=100
        )
        
        info = manager.get_api_key_info(api_key)
        assert info is not None
        assert info.key_name == "Test Key"
        assert info.owner_name == "Test Owner"
        assert info.rate_limit == 100
    
    def test_log_api_usage(self):
        """Test logging API usage"""
        manager = APIKeyManager()
        
        api_key = manager.generate_api_key(
            key_name="Test Key",
            owner_name="Test Owner"
        )
        
        # Log some usage
        manager.log_api_usage(
            api_key=api_key,
            endpoint="/test",
            status_code=200,
            response_time_ms=100,
            success=True
        )
        
        # Get stats
        stats = manager.get_usage_stats(api_key, hours=24)
        assert stats["total_calls"] == 1
        assert stats["successful_calls"] == 1
    
    def test_disable_api_key(self):
        """Test disabling API key"""
        manager = APIKeyManager()
        
        api_key = manager.generate_api_key(
            key_name="Test Key",
            owner_name="Test Owner"
        )
        
        # Disable it
        result = manager.disable_api_key(api_key, reason="Testing")
        assert result is True
        
        # Verify it's disabled
        is_valid, error = manager.verify_api_key(api_key)
        assert is_valid is False

# =============================================================================
# AUDIT LOGGER TESTS
# =============================================================================

class TestAuditLogger:
    """Test AuditLogger"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset audit logger before each test"""
        import os
        if os.path.exists("audit_logs.db"):
            os.remove("audit_logs.db")
        from audit_logger import init_audit_database
        init_audit_database()
    
    def test_singleton_instance(self):
        """Test AuditLogger singleton"""
        logger1 = AuditLogger()
        logger2 = AuditLogger()
        assert logger1 is logger2
    
    def test_log_auth_event(self):
        """Test logging auth events"""
        logger = AuditLogger()
        
        logger.log_auth_event(
            user_id=123,
            action="Login attempt",
            result="success",
            source_ip="192.168.1.1"
        )
        
        events = logger.get_events(event_type="auth")
        assert len(events) > 0
        assert events[0]["action"] == "Login attempt"
    
    def test_log_api_event(self):
        """Test logging API events"""
        logger = AuditLogger()
        
        logger.log_api_event(
            user_id=None,
            endpoint="/explain_news",
            result="success",
            status_code=200,
            source_ip="192.168.1.1"
        )
        
        events = logger.get_events(event_type="api")
        assert len(events) > 0
    
    def test_get_events_with_filters(self):
        """Test filtering events"""
        logger = AuditLogger()
        
        # Log events with different severities
        logger.log_error("Critical error", severity="CRITICAL", user_id=123)
        logger.log_warning("Warning message", user_id=456)
        
        # Filter by severity
        critical_events = logger.get_events(severity="CRITICAL")
        assert len(critical_events) >= 1
        
        # Filter by user
        user_events = logger.get_events(user_id=123)
        assert len(user_events) >= 1
    
    def test_get_statistics(self):
        """Test audit statistics"""
        logger = AuditLogger()
        
        # Log various events
        logger.log_error("Error 1", severity="CRITICAL")
        logger.log_error("Error 2", severity="HIGH")
        logger.log_warning("Warning")
        
        stats = logger.get_statistics(hours=24)
        assert stats["total_events"] >= 3
        assert stats["critical_count"] >= 1
        assert stats["high_count"] >= 1

# =============================================================================
# VALIDATION FUNCTIONS TESTS
# =============================================================================

class TestValidationFunctions:
    """Test validation helper functions"""
    
    def test_validate_callback_data(self):
        """Test callback data validation"""
        allowed = ["btn_help", "btn_start", "btn_settings"]
        
        # Should pass
        assert validate_callback_data("btn_help", allowed) is True
        assert validate_callback_data("btn_help:param1", allowed) is True
        
        # Should fail
        assert validate_callback_data("btn_invalid", allowed) is False
        assert validate_callback_data("", allowed) is False
    
    def test_validate_user_id(self):
        """Test user ID validation"""
        assert validate_user_id(123456789) is True
        assert validate_user_id("123456789") is True
        assert validate_user_id(-1) is False
        assert validate_user_id(0) is False
        assert validate_user_id("invalid") is False
    
    def test_validate_request_size(self):
        """Test request size validation"""
        assert validate_request_size(1000) is True
        assert validate_request_size(100000) is True
        assert validate_request_size(1024 * 100) is True  # 100KB
        assert validate_request_size(1024 * 101) is False  # > 100KB
        assert validate_request_size(0) is False

# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
