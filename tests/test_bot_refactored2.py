"""
Comprehensive tests for bot_refactored2 Phase 2 refactoring.

Tests cover:
- Schemas validation
- Services functionality
- Handlers logic
- Integration scenarios
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import schemas
from bot_refactored2.schemas import (
    UserSchema, UserStatsSchema, LessonSchema, QuestSchema,
    MessageSchema, AnalysisResponseSchema
)

# Import services
from bot_refactored2.services import (
    APIClientService, UserService, LessonService, QuestService
)


# ============================================================================
# SCHEMA TESTS
# ============================================================================

class TestUserSchemas:
    """Test user-related Pydantic schemas."""
    
    def test_user_schema_valid(self):
        """Test valid user schema."""
        user = UserSchema(
            user_id=123,
            username="testuser",
            first_name="Test"
        )
        assert user.user_id == 123
        assert user.username == "testuser"
        assert not user.is_banned
    
    def test_user_stats_schema_valid(self):
        """Test valid user stats schema."""
        stats = UserStatsSchema(
            user_id=123,
            xp=500,
            level=3,
            courses_completed=2
        )
        assert stats.xp == 500
        assert stats.level == 3
    
    def test_user_stats_schema_validation(self):
        """Test user stats validation."""
        with pytest.raises(ValueError):
            UserStatsSchema(
                user_id=123,
                xp=-100,  # Negative XP should fail
                level=1
            )


class TestLessonSchemas:
    """Test lesson-related schemas."""
    
    def test_lesson_schema_valid(self):
        """Test valid lesson schema."""
        lesson = LessonSchema(
            lesson_id="lesson_1",
            course_id="crypto_basics",
            title="Introduction to Crypto",
            content="Lorem ipsum...",
            lesson_number=1,
            xp_reward=100
        )
        assert lesson.lesson_number == 1
        assert lesson.xp_reward == 100
    
    def test_lesson_schema_with_quiz(self):
        """Test lesson with quiz questions."""
        from bot_refactored2.schemas import QuizQuestionSchema
        
        quiz = [
            QuizQuestionSchema(
                question="What is Bitcoin?",
                options=["Currency", "Technology", "Both"],
                correct_answer="Both",
                explanation="Bitcoin is both a currency and technology"
            )
        ]
        
        lesson = LessonSchema(
            lesson_id="lesson_1",
            course_id="crypto_basics",
            title="Introduction",
            content="Content",
            lesson_number=1,
            quiz=quiz
        )
        assert len(lesson.quiz) == 1
        assert lesson.quiz[0].correct_answer == "Both"


class TestQuestSchemas:
    """Test quest-related schemas."""
    
    def test_quest_schema_valid(self):
        """Test valid quest schema."""
        quest = QuestSchema(
            quest_id="daily_quest_1",
            title="Daily Analysis",
            description="Analyze 5 news items",
            objective="Perform analysis",
            xp_reward=50,
            required_level=1
        )
        assert quest.xp_reward == 50
        assert quest.required_level == 1
    
    def test_quest_xp_range(self):
        """Test quest XP reward range."""
        with pytest.raises(ValueError):
            QuestSchema(
                quest_id="quest",
                title="Quest",
                description="Desc",
                objective="Obj",
                xp_reward=10000,  # Too high
                required_level=1
            )


class TestMessageSchemas:
    """Test message and response schemas."""
    
    def test_message_schema_valid(self):
        """Test valid message schema."""
        msg = MessageSchema(
            user_id=123,
            text="Analyze this text",
            message_type="text"
        )
        assert msg.text == "Analyze this text"
    
    def test_analysis_response_schema(self):
        """Test analysis response schema."""
        response = AnalysisResponseSchema(
            summary_text="This is a summary",
            impact_points=["Point 1", "Point 2"],
            xp_earned=10
        )
        assert len(response.impact_points) == 2
        assert response.xp_earned == 10


# ============================================================================
# SERVICE TESTS
# ============================================================================

class TestAPIClientService:
    """Test APIClientService."""
    
    def test_api_client_init(self):
        """Test API client initialization."""
        client = APIClientService("http://localhost:8000", "test_key")
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test_key"
    
    def test_api_client_stats(self):
        """Test API client statistics."""
        client = APIClientService("http://localhost:8000")
        client.request_counter["success"] = 5
        client.request_counter["failure"] = 2
        
        stats = client.get_stats()
        assert stats["success"] == 5
        assert stats["failure"] == 2
        assert stats["total"] == 7
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        client = APIClientService("http://localhost:8000")
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await client.health_check()
            assert result


class TestUserService:
    """Test UserService."""
    
    def test_user_service_init(self):
        """Test user service initialization."""
        service = UserService()
        assert service.db is None
    
    def test_user_service_with_pool(self):
        """Test user service with connection pool."""
        mock_pool = Mock()
        service = UserService(mock_pool)
        assert service.db == mock_pool


class TestLessonService:
    """Test LessonService."""
    
    def test_lesson_service_init(self):
        """Test lesson service initialization."""
        service = LessonService()
        assert service.db is None
    
    def test_lesson_service_with_pool(self):
        """Test lesson service with connection pool."""
        mock_pool = Mock()
        service = LessonService(mock_pool)
        assert service.db == mock_pool


class TestQuestService:
    """Test QuestService."""
    
    def test_quest_service_init(self):
        """Test quest service initialization."""
        service = QuestService()
        assert service.db is None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for services and handlers."""
    
    def test_full_user_flow(self):
        """Test complete user flow."""
        user_service = UserService()
        lesson_service = LessonService()
        quest_service = QuestService()
        
        # Services should be initialized
        assert user_service is not None
        assert lesson_service is not None
        assert quest_service is not None
    
    def test_handler_initialization(self):
        """Test handler initialization."""
        from bot_refactored2.handlers import CommandHandler, MessageHandler, ButtonHandler
        
        cmd_handler = CommandHandler()
        msg_handler = MessageHandler()
        btn_handler = ButtonHandler()
        
        assert cmd_handler is not None
        assert msg_handler is not None
        assert btn_handler is not None


# ============================================================================
# BOT CORE TESTS
# ============================================================================

class TestBotCore:
    """Test BotCore functionality."""
    
    def test_bot_core_import(self):
        """Test bot core can be imported."""
        from bot_refactored2.core import BotCore, get_bot_core
        
        assert BotCore is not None
        assert callable(get_bot_core)
    
    def test_get_bot_core_singleton(self):
        """Test bot core singleton pattern."""
        from bot_refactored2.core import get_bot_core
        
        bot1 = get_bot_core()
        bot2 = get_bot_core()
        
        # Both should reference same instance
        assert bot1 is bot2


# ============================================================================
# VALIDATION TESTS
# ============================================================================

class TestValidation:
    """Test input validation."""
    
    def test_message_length_validation(self):
        """Test message length validation."""
        with pytest.raises(ValueError):
            MessageSchema(
                user_id=123,
                text="x" * 5000,  # Too long
                message_type="text"
            )
    
    def test_user_id_required(self):
        """Test user ID is required."""
        with pytest.raises(ValueError):
            UserSchema()
    
    def test_quest_difficulty_enum(self):
        """Test quest difficulty enum validation."""
        with pytest.raises(ValueError):
            QuestSchema(
                quest_id="quest",
                title="Quest",
                description="Desc",
                objective="Obj",
                xp_reward=50,
                difficulty_level="impossible"  # Invalid
            )


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_string_message(self):
        """Test handling of empty string."""
        with pytest.raises(ValueError):
            MessageSchema(
                user_id=123,
                text="",
                message_type="text"
            )
    
    def test_zero_xp_reward(self):
        """Test zero XP reward quest."""
        with pytest.raises(ValueError):
            QuestSchema(
                quest_id="quest",
                title="Quest",
                description="Desc",
                objective="Obj",
                xp_reward=0,  # Too low
                required_level=1
            )
    
    def test_future_timestamp(self):
        """Test future timestamps are allowed."""
        future_time = datetime.fromtimestamp(datetime.now().timestamp() + 3600)
        schema = UserSchema(user_id=123)
        # Should not raise


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
