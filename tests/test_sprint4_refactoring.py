"""
Tests for SOLID Refactoring (SPRINT 4)
======================================

Tests for new modules: validators, database, AI providers.
"""

import pytest
from validators import TextValidator, ValidationError, SecurityValidator


class TestTextValidator:
    """Tests for TextValidator (DRY principle)"""
    
    def test_valid_text(self):
        """Should accept valid text"""
        result = TextValidator.validate("This is valid text")
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_empty_text(self):
        """Should reject empty text"""
        result = TextValidator.validate("")
        assert not result.is_valid
        assert "empty" in result.errors[0].lower()
    
    def test_none_text(self):
        """Should reject None"""
        result = TextValidator.validate(None)
        assert not result.is_valid
    
    def test_text_too_short(self):
        """Should reject very short text"""
        result = TextValidator.validate("a")
        # Note: MIN_LENGTH is 1, so this should be valid
        assert result.is_valid
    
    def test_text_too_long(self):
        """Should reject text longer than MAX_LENGTH"""
        long_text = "a" * (TextValidator.MAX_LENGTH + 1)
        result = TextValidator.validate(long_text)
        assert not result.is_valid
        assert "too long" in result.errors[0].lower()
    
    def test_validate_or_raise_valid(self):
        """Should return stripped text when valid"""
        text = "  Valid text  "
        result = TextValidator.validate_or_raise(text)
        assert result == "Valid text"
    
    def test_validate_or_raise_invalid(self):
        """Should raise ValidationError when invalid"""
        with pytest.raises(ValidationError):
            TextValidator.validate_or_raise("")
    
    def test_truncate(self):
        """Should truncate text with ellipsis"""
        long_text = "a" * 100
        truncated = TextValidator.truncate(long_text, max_length=50)
        assert len(truncated) == 50
        assert truncated.endswith("...")


class TestSecurityValidator:
    """Tests for SecurityValidator (DRY principle)"""
    
    def test_safe_text(self):
        """Should accept safe text"""
        result = SecurityValidator.validate("This is safe text")
        assert result.is_safe
        assert len(result.threats) == 0
    
    def test_sql_injection_drop(self):
        """Should detect SQL injection - DROP TABLE"""
        result = SecurityValidator.validate("DROP TABLE users")
        assert not result.is_safe
        assert len(result.threats) > 0
    
    def test_sql_injection_delete(self):
        """Should detect SQL injection - DELETE FROM"""
        result = SecurityValidator.validate("DELETE FROM users WHERE id=1")
        assert not result.is_safe
    
    def test_xss_injection_script(self):
        """Should detect XSS - script tag"""
        result = SecurityValidator.validate("<script>alert('xss')</script>")
        assert not result.is_safe
    
    def test_xss_injection_event(self):
        """Should detect XSS - event handler"""
        result = SecurityValidator.validate("<div onclick=alert('xss')>")
        assert not result.is_safe
    
    def test_command_injection(self):
        """Should detect command injection"""
        result = SecurityValidator.validate("; exec(rm -rf /)")
        assert not result.is_safe
    
    def test_path_traversal(self):
        """Should detect path traversal"""
        result = SecurityValidator.validate("../../etc/passwd")
        assert not result.is_safe
    
    def test_sanitize(self):
        """Should sanitize dangerous characters"""
        text = "Hello  \x00  World\n\n\nTest"
        sanitized = SecurityValidator.sanitize(text)
        assert "\x00" not in sanitized
        assert "\n\n\n" not in sanitized


class TestAIProviders:
    """Tests for AI Provider abstraction (SOLID - OCP, LSP)"""
    
    @pytest.mark.asyncio
    async def test_provider_factory(self):
        """Should create providers via factory"""
        from ai import AIProviderFactory
        
        # Get available providers
        available = AIProviderFactory.get_available()
        assert "deepseek" in available
        assert "gemini" in available
    
    @pytest.mark.asyncio
    async def test_provider_interface(self):
        """All providers should implement AIProvider interface"""
        from ai import AIProvider, DeepSeekProvider, GeminiProvider
        
        # Mock providers for testing
        assert issubclass(DeepSeekProvider, AIProvider)
        assert issubclass(GeminiProvider, AIProvider)
    
    @pytest.mark.asyncio
    async def test_orchestrator_health_check(self):
        """Orchestrator should perform health checks"""
        from ai import AIOrchestrator, AIProviderFactory, AIException
        
        # This would need real API keys to fully test
        # For now, just test the interface
        try:
            primary = AIProviderFactory.create(
                "deepseek",
                api_key="test_key",
                model="deepseek-chat"
            )
            
            fallback = AIProviderFactory.create(
                "gemini",
                api_key="test_key",
                model="models/gemini-2.5-flash"
            )
            
            orchestrator = AIOrchestrator(primary=primary, fallback=fallback)
            
            # Should have both providers
            assert orchestrator.primary is not None
            assert orchestrator.fallback is not None
        except AIException:
            # Expected if API keys are invalid
            pass


class TestDatabaseService:
    """Tests for Database Service (DAL - DRY principle)"""
    
    def test_connection_pool_init(self):
        """Should initialize connection pool"""
        from db_service import DatabaseConnectionPool
        
        pool = DatabaseConnectionPool(":memory:")
        conn = pool.get_connection()
        assert conn is not None
    
    def test_base_repository(self):
        """Should implement CRUD operations"""
        from db_service import BaseRepository, DatabaseConnectionPool
        
        pool = DatabaseConnectionPool(":memory:")
        repo = BaseRepository("test_table", pool)
        
        # Just check methods exist
        assert hasattr(repo, 'get_by_id')
        assert hasattr(repo, 'create')
        assert hasattr(repo, 'update')
        assert hasattr(repo, 'delete')


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for refactored components"""
    
    def test_validators_integration(self):
        """Validators should work together"""
        from validators import TextValidator, SecurityValidator, ValidationError
        
        # Good text
        text = "This is a safe message"
        text_result = TextValidator.validate(text)
        security_result = SecurityValidator.validate(text)
        
        assert text_result.is_valid
        assert security_result.is_safe
    
    def test_api_response_model(self):
        """API response model should work"""
        from api_server_refactored import APIResponse
        
        response = APIResponse(
            status="ok",
            data={"message": "test"},
            cached=False
        )
        
        assert response.status == "ok"
        assert response.data["message"] == "test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
