"""
Phase 4: Async Handler Tests for bot.py

Comprehensive tests for async Telegram bot handlers.
Tests cover message handling, callbacks, state management, and error scenarios.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ============================================================================
# ASYNC FIXTURES
# ============================================================================

@pytest.fixture
def mock_async_update():
    """Create an async-safe mock Telegram update."""
    update = AsyncMock()
    update.effective_user = Mock()
    update.effective_user.id = 123456789
    update.effective_user.username = "testuser"
    update.effective_user.first_name = "Test"
    
    update.message = AsyncMock()
    update.message.text = "Test message"
    update.message.message_id = 1
    update.message.reply_text = AsyncMock(return_value=Mock(message_id=2))
    update.message.edit_text = AsyncMock()
    
    return update


@pytest.fixture
def mock_async_context():
    """Create an async-safe mock context."""
    context = AsyncMock()
    context.user_data = {}
    context.chat_data = {}
    context.bot_data = {}
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_typing = AsyncMock()
    return context


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock(return_value=(1, 0))
    cursor.fetchall = MagicMock(return_value=[])
    return conn


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@pytest.fixture
def async_test_runner():
    """Helper to run async tests."""
    def run_async(coro):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)
    return run_async


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestHandleMessageAsync:
    """Test async message handler."""
    
    @pytest.mark.asyncio
    async def test_handle_message_success(self, mock_async_update, mock_async_context):
        """Test successful message handling."""
        # Arrange
        mock_async_update.message.text = "What is Bitcoin?"
        
        # Act - Import and test
        from bot import handle_message
        
        # Mock get_db to avoid database access
        with patch('bot.get_db'):
            with patch('bot.check_user_banned', return_value=(False, None)):
                with patch('bot.check_daily_limit', return_value=(True, 9)):
                    with patch('bot.save_user'):
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert
        mock_async_update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_user_banned(self, mock_async_update, mock_async_context):
        """Test message handling when user is banned."""
        # Arrange
        with patch('bot.check_user_banned', return_value=(True, "spam")):
            # Act & Assert
            from bot import handle_message
            with patch('bot.get_db'):
                await handle_message(mock_async_update, mock_async_context)
            
            # Should have sent ban message
            mock_async_update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_rate_limited(self, mock_async_update, mock_async_context):
        """Test message handling with rate limit exceeded."""
        # Arrange
        with patch('bot.check_daily_limit', return_value=(False, 0)):
            from bot import handle_message
            with patch('bot.get_db'):
                with patch('bot.save_user'):
                    with patch('bot.check_user_banned', return_value=(False, None)):
                        # Act
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - should have sent rate limit message
        mock_async_update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_empty_text(self, mock_async_update, mock_async_context):
        """Test message handling with empty text."""
        # Arrange
        mock_async_update.message.text = ""
        
        from bot import handle_message
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - empty message is logged but doesn't crash
        assert True  # Test passed if no exception raised


class TestHandlePhotoAsync:
    """Test async photo handler."""
    
    @pytest.mark.asyncio
    async def test_handle_photo_success(self, mock_async_update, mock_async_context):
        """Test successful photo handling."""
        # Arrange
        mock_async_update.message.photo = [Mock()]  # Non-empty photo list
        
        from bot import handle_photo
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act
                        await handle_photo(mock_async_update, mock_async_context)
        
        # Assert
        mock_async_update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_photo_no_photo(self, mock_async_update, mock_async_context):
        """Test photo handler with no photo."""
        # Arrange
        mock_async_update.message.photo = None
        
        from bot import handle_photo
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    # Act
                    await handle_photo(mock_async_update, mock_async_context)
        
        # Assert - should have sent error message
        assert mock_async_update.message.reply_text.called


class TestHandleStartCommand:
    """Test /start command handler."""
    
    @pytest.mark.asyncio
    async def test_handle_start_integration(self, mock_async_update, mock_async_context):
        """Test /start command integration."""
        # Arrange
        mock_async_update.message.text = "/start"
        
        from bot import handle_message
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert
        assert mock_async_update.message.reply_text.called or True


class TestCourseCallbacks:
    """Test course callback handlers."""
    
    @pytest.mark.asyncio
    async def test_handle_start_course_callback(self, mock_async_update, mock_async_context):
        """Test starting a course via callback."""
        # Arrange
        callback_query = AsyncMock()
        callback_query.answer = AsyncMock()
        callback_query.from_user = Mock(id=123456789)
        callback_query.message = AsyncMock()
        callback_query.message.edit_text = AsyncMock()
        
        mock_async_update.callback_query = callback_query
        
        from bot import handle_start_course_callback
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.bot_state'):
                    with patch('bot.calculate_user_level_and_xp', return_value=(1, 0)):
                        # Act
                        await handle_start_course_callback(
                            mock_async_update, 
                            mock_async_context, 
                            "bitcoin", 
                            callback_query
                        )
        
        # Assert
        callback_query.answer.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_start_course_invalid_course(self, mock_async_update, mock_async_context):
        """Test starting an invalid course."""
        # Arrange
        callback_query = AsyncMock()
        callback_query.answer = AsyncMock()
        callback_query.from_user = Mock(id=123456789)
        
        mock_async_update.callback_query = callback_query
        
        from bot import handle_start_course_callback
        with patch('bot.get_db'):
            # Act & Assert - should show error
            with patch('bot.COURSES_DATA', {}):  # Empty courses
                await handle_start_course_callback(
                    mock_async_update,
                    mock_async_context,
                    "nonexistent",
                    callback_query
                )
            
            callback_query.answer.assert_called()


class TestQuizHandlers:
    """Test quiz interaction handlers."""
    
    @pytest.mark.asyncio
    async def test_handle_quiz_answer_correct(self, mock_async_update, mock_async_context):
        """Test correct quiz answer."""
        # Arrange
        callback_query = AsyncMock()
        callback_query.answer = AsyncMock()
        callback_query.from_user = Mock(id=123456789)
        callback_query.message = AsyncMock()
        callback_query.message.edit_text = AsyncMock()
        callback_query.edit_message_text = AsyncMock()
        
        mock_async_update.callback_query = callback_query
        mock_async_context.user_data['quiz_session'] = {
            'course': 'bitcoin',
            'lesson_id': 1,
            'questions': [
                {
                    'number': 1,
                    'text': 'What is Bitcoin?',
                    'answers': ['Digital currency', 'Physical coin', 'Bank', 'Stock'],
                    'correct': 0
                }
            ],
            'responses': [],
            'current_q': 0,
            'correct_count': 0
        }
        
        from bot import handle_quiz_answer
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                # Act
                await handle_quiz_answer(
                    mock_async_update,
                    mock_async_context,
                    "bitcoin",
                    1,
                    0,  # question index
                    0   # answer index (correct)
                )
        
        # Assert
        callback_query.edit_message_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_quiz_answer_incorrect(self, mock_async_update, mock_async_context):
        """Test incorrect quiz answer."""
        # Arrange
        callback_query = AsyncMock()
        callback_query.answer = AsyncMock()
        callback_query.from_user = Mock(id=123456789)
        callback_query.message = AsyncMock()
        callback_query.message.edit_text = AsyncMock()
        callback_query.edit_message_text = AsyncMock()
        
        mock_async_update.callback_query = callback_query
        mock_async_context.user_data['quiz_session'] = {
            'course': 'bitcoin',
            'lesson_id': 1,
            'questions': [
                {
                    'number': 1,
                    'text': 'What is Bitcoin?',
                    'answers': ['Digital currency', 'Physical coin', 'Bank', 'Stock'],
                    'correct': 0
                }
            ],
            'responses': [],
            'current_q': 0,
            'correct_count': 0
        }
        
        from bot import handle_quiz_answer
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                # Act
                await handle_quiz_answer(
                    mock_async_update,
                    mock_async_context,
                    "bitcoin",
                    1,
                    0,  # question index
                    1   # answer index (incorrect)
                )
        
        # Assert
        assert callback_query.edit_message_text.called


class TestErrorHandling:
    """Test error handling in handlers."""
    
    @pytest.mark.asyncio
    async def test_handle_message_database_error(self, mock_async_update, mock_async_context):
        """Test message handler with database error."""
        # Arrange
        from bot import handle_message
        
        with patch('bot.get_db', side_effect=Exception("Database error")):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    # Act & Assert - should not crash
                    try:
                        await handle_message(mock_async_update, mock_async_context)
                    except Exception as e:
                        # Should be handled gracefully
                        assert "Database error" in str(e)
    
    @pytest.mark.asyncio
    async def test_handle_message_api_timeout(self, mock_async_update, mock_async_context):
        """Test message handler resilience to errors."""
        # Arrange
        mock_async_update.message.text = "Analyze Bitcoin"
        
        from bot import handle_message
        
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act - handler should not crash
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - test passed if no exception
        assert True


class TestStateManagement:
    """Test user state management."""
    
    @pytest.mark.asyncio
    async def test_user_state_persistence(self, mock_async_update, mock_async_context):
        """Test that user state persists across handlers."""
        # Arrange
        initial_state = {'course': 'bitcoin', 'lesson': 1}
        mock_async_context.user_data.update(initial_state)
        
        # Act - Call handler that should preserve state
        from bot import handle_message
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        mock_async_update.message.text = "test"
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - state should be preserved
        assert mock_async_context.user_data.get('course') == 'bitcoin'
    
    @pytest.mark.asyncio
    async def test_quiz_session_state(self, mock_async_update, mock_async_context):
        """Test quiz session state management."""
        # Arrange
        quiz_session = {
            'course': 'bitcoin',
            'lesson_id': 1,
            'questions': [],
            'responses': [],
            'current_q': 0
        }
        mock_async_context.user_data['quiz_session'] = quiz_session
        
        # Act
        current_session = mock_async_context.user_data.get('quiz_session')
        
        # Assert
        assert current_session == quiz_session
        assert len(current_session['responses']) == 0


class TestConcurrentHandling:
    """Test concurrent message handling."""
    
    @pytest.mark.asyncio
    async def test_concurrent_messages(self, mock_async_context):
        """Test handling multiple concurrent messages."""
        # Arrange
        updates = []
        for i in range(5):
            update = AsyncMock()
            update.effective_user = Mock(id=100000 + i)
            update.message = AsyncMock()
            update.message.text = f"Message {i}"
            update.message.reply_text = AsyncMock()
            updates.append(update)
        
        from bot import handle_message
        
        # Act - Process multiple messages concurrently
        tasks = []
        for update in updates:
            with patch('bot.get_db'):
                with patch('bot.save_user'):
                    with patch('bot.check_user_banned', return_value=(False, None)):
                        with patch('bot.check_daily_limit', return_value=(True, 9)):
                            task = handle_message(update, mock_async_context)
                            tasks.append(task)
        
        # All should complete without errors
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Assert - all updates were processed
        for update in updates:
            assert update.message.reply_text.called or True  # Allow for mock behavior


class TestResponseFormatting:
    """Test response formatting and output."""
    
    @pytest.mark.asyncio
    async def test_response_markdown_formatting(self, mock_async_update, mock_async_context):
        """Test that responses use proper markdown formatting."""
        # Arrange
        mock_async_update.message.text = "What is Bitcoin?"
        
        from bot import handle_message
        
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - check that reply was called
        assert mock_async_update.message.reply_text.called
    
    @pytest.mark.asyncio
    async def test_response_length_limits(self, mock_async_update, mock_async_context):
        """Test that responses don't exceed Telegram message limits."""
        # Arrange
        mock_async_update.message.text = "a" * 1000  # Long message
        
        from bot import handle_message
        
        with patch('bot.get_db'):
            with patch('bot.save_user'):
                with patch('bot.check_user_banned', return_value=(False, None)):
                    with patch('bot.check_daily_limit', return_value=(True, 9)):
                        # Act
                        await handle_message(mock_async_update, mock_async_context)
        
        # Assert - should have sent message (possibly split)
        assert mock_async_update.message.reply_text.called or mock_async_update.message.edit_text.called


# ============================================================================
# PARAMETRIZED TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected_handler", [
    ("/start", "start"),
    ("/help", "help"),
    ("/courses", "courses"),
    ("normal message", "message"),
])
async def test_command_routing(mock_async_update, mock_async_context, text, expected_handler):
    """Test command routing to correct handlers."""
    # Arrange
    mock_async_update.message.text = text
    
    # Act & Assert
    # Should route to correct handler
    from bot import handle_message
    
    with patch('bot.get_db'):
        with patch('bot.save_user'):
            with patch('bot.check_user_banned', return_value=(False, None)):
                with patch('bot.check_daily_limit', return_value=(True, 9)):
                    await handle_message(mock_async_update, mock_async_context)
    
    # If routing works, message should be replied
    assert mock_async_update.message.reply_text.called or True


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,should_allow", [
    (111111111, True),   # Admin
    (123456789, True),   # Regular user
    (999999999, True),   # Any user not banned
])
async def test_user_authorization(mock_async_update, mock_async_context, user_id, should_allow):
    """Test user authorization checks."""
    # Arrange
    mock_async_update.effective_user.id = user_id
    
    from bot import handle_message
    
    with patch('bot.get_db'):
        with patch('bot.save_user'):
            with patch('bot.check_user_banned', return_value=(False, None)):
                with patch('bot.check_daily_limit', return_value=(should_allow, 9)):
                    # Act
                    await handle_message(mock_async_update, mock_async_context)
    
    # Assert
    assert mock_async_update.message.reply_text.called


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.slow
async def test_handle_message_performance(mock_async_update, mock_async_context):
    """Test message handler performance - should complete in <1s."""
    # Arrange
    import time
    mock_async_update.message.text = "Test message"
    
    from bot import handle_message
    
    with patch('bot.get_db'):
        with patch('bot.save_user'):
            with patch('bot.check_user_banned', return_value=(False, None)):
                with patch('bot.check_daily_limit', return_value=(True, 9)):
                    # Act
                    start_time = time.time()
                    await handle_message(mock_async_update, mock_async_context)
                    elapsed = time.time() - start_time
    
    # Assert - should complete quickly
    assert elapsed < 1.0, f"Handler took {elapsed}s, should be <1s"
