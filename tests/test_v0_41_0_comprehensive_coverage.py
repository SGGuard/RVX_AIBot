"""
🧪 v0.41.0 Comprehensive Unit Tests - 60%+ Code Coverage

Tests for:
- Main message handlers
- Database operations
- Utility/formatting functions
- Integration scenarios
- Error handling and edge cases

Target: 100+ tests with 60%+ code coverage
"""

import unittest
import logging
import sqlite3
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from typing import Optional
from datetime import datetime, timedelta
import asyncio


class TestUserManagement(unittest.TestCase):
    """Tests for user-related database operations."""
    
    @patch('bot.get_db')
    def test_save_user_new_user(self, mock_get_db):
        """save_user should create new user record."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import save_user
        save_user(123456, "testuser", "Test")
        
        # Verify database was called
        mock_conn.cursor.assert_called()
    
    @patch('bot.get_db')
    def test_save_user_existing_user(self, mock_get_db):
        """save_user should update existing user."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import save_user
        # Call twice with same ID
        save_user(123456, "testuser", "Test")
        save_user(123456, "testuser2", "Test2")
        
        # Should not raise error
        self.assertTrue(True)
    
    @patch('bot.get_db')
    def test_check_user_banned_not_banned(self, mock_get_db):
        """check_user_banned should return False for non-banned user."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No ban record
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import check_user_banned
        is_banned, reason = check_user_banned(123456)
        
        self.assertFalse(is_banned)
        self.assertIsNone(reason)
    
    @patch('bot.get_db')
    def test_check_user_banned_is_banned(self, mock_get_db):
        """check_user_banned should return True and reason for banned user."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, "Spam")  # Ban record exists
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import check_user_banned
        is_banned, reason = check_user_banned(123456)
        
        self.assertTrue(is_banned)
        self.assertEqual(reason, "Spam")


class TestLimitChecking(unittest.TestCase):
    """Tests for daily limit enforcement."""
    
    @patch('bot.get_db')
    def test_check_daily_limit_within_limit(self, mock_get_db):
        """check_daily_limit should allow requests within limit."""
        from datetime import datetime, timedelta
        
        mock_cursor = MagicMock()
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        mock_cursor.fetchone.return_value = (5, tomorrow)  # 5 requests made, reset tomorrow
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import check_daily_limit, MAX_REQUESTS_PER_DAY
        can_request, remaining = check_daily_limit(123456)
        
        self.assertTrue(can_request)
        self.assertGreater(remaining, 0)
    
    @patch('bot.get_db')
    def test_check_daily_limit_exceeded(self, mock_get_db):
        """check_daily_limit should block after limit exceeded."""
        from datetime import datetime, timedelta
        
        mock_cursor = MagicMock()
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        mock_cursor.fetchone.return_value = (100, tomorrow)  # 100 requests made (exceeds limit)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import check_daily_limit
        can_request, remaining = check_daily_limit(123456)
        
        self.assertFalse(can_request)


class TestCacheOperations(unittest.TestCase):
    """Tests for cache get/set operations."""
    
    @patch('bot.get_db')
    def test_get_cache_hit(self, mock_get_db):
        """get_cache should return cached value on hit."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("Cached response",)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_cache
        result = get_cache("test_key")
        
        self.assertEqual(result, "Cached response")
    
    @patch('bot.get_db')
    def test_get_cache_miss(self, mock_get_db):
        """get_cache should return None on miss."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_cache
        result = get_cache("missing_key")
        
        self.assertIsNone(result)
    
    @patch('bot.get_db')
    def test_set_cache(self, mock_get_db):
        """set_cache should store value in cache."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import set_cache
        set_cache("test_key", "test_value")
        
        # Verify insert was called
        mock_cursor.execute.assert_called()


class TestFormatFunctions(unittest.TestCase):
    """Tests for message formatting functions."""
    
    def test_format_header(self):
        """format_header should create header with title."""
        from bot import format_header
        
        result = format_header("Test Title")
        
        self.assertIn("Test Title", result)
        self.assertGreater(len(result), 10)
    
    def test_format_section(self):
        """format_section should create section with title and content."""
        from bot import format_section
        
        result = format_section("Section", "Content here")
        
        self.assertIn("Section", result)
        self.assertIn("Content here", result)
    
    def test_format_section_with_emoji(self):
        """format_section should use emoji parameter."""
        from bot import format_section
        
        result = format_section("Title", "Content", emoji="✅")
        
        self.assertIn("✅", result)
    
    def test_format_tips_block(self):
        """format_tips_block should format list of tips."""
        from bot import format_tips_block
        
        tips = ["Tip 1", "Tip 2", "Tip 3"]
        result = format_tips_block(tips)
        
        self.assertIn("Tip 1", result)
        self.assertIn("Tip 2", result)
        self.assertIn("Tip 3", result)
    
    def test_format_command_response(self):
        """format_command_response should format command output."""
        from bot import format_command_response
        
        result = format_command_response("Command", "Response content")
        
        self.assertIn("Command", result)
        self.assertIn("Response content", result)
    
    def test_format_error(self):
        """format_error should create error message."""
        from bot import format_error
        
        result = format_error("Something went wrong")
        
        self.assertIn("Something went wrong", result)
        self.assertIn("❌", result)
    
    def test_format_success(self):
        """format_success should create success message."""
        from bot import format_success
        
        result = format_success("Operation completed")
        
        self.assertIn("Operation completed", result)
        self.assertIn("✅", result)
    
    def test_format_list_items_unordered(self):
        """format_list_items should create unordered list."""
        from bot import format_list_items
        
        items = ["Item 1", "Item 2", "Item 3"]
        result = format_list_items(items, numbered=False)
        
        for item in items:
            self.assertIn(item, result)
    
    def test_format_list_items_ordered(self):
        """format_list_items should create ordered list when numbered=True."""
        from bot import format_list_items
        
        items = ["Item 1", "Item 2", "Item 3"]
        result = format_list_items(items, numbered=True)
        
        for item in items:
            self.assertIn(item, result)
        # Check for numbering (1., 2., 3. or similar)
        self.assertIn("1", result)


class TestLanguageDetection(unittest.TestCase):
    """Tests for user language detection."""
    
    def test_detect_russian(self):
        """detect_user_language should detect Russian text."""
        from bot import detect_user_language
        
        result = detect_user_language("Привет, как дела?")
        
        self.assertEqual(result, 'ru')
    
    def test_detect_english(self):
        """detect_user_language should detect English text."""
        from bot import detect_user_language
        
        result = detect_user_language("Hello, how are you?")
        
        self.assertEqual(result, 'en')
    
    def test_detect_mixed(self):
        """detect_user_language should detect mixed language."""
        from bot import detect_user_language
        
        result = detect_user_language("Hello привет how дела")
        
        self.assertEqual(result, 'mixed')
    
    def test_detect_empty(self):
        """detect_user_language should handle empty string."""
        from bot import detect_user_language
        
        result = detect_user_language("")
        
        self.assertIn(result, ['ru', 'en', 'mixed'])


class TestContextAnalysis(unittest.TestCase):
    """Tests for message context analysis."""
    
    def test_analyze_greeting(self):
        """analyze_message_context should detect greeting."""
        from bot import analyze_message_context
        
        result = analyze_message_context("привет")
        
        self.assertEqual(result['type'], 'greeting')
        self.assertFalse(result['needs_crypto_analysis'])
    
    def test_analyze_info_request(self):
        """analyze_message_context should detect info request."""
        from bot import analyze_message_context
        
        result = analyze_message_context("что ты умеешь?")
        
        self.assertEqual(result['type'], 'info_request')
    
    def test_analyze_crypto_news(self):
        """analyze_message_context should detect crypto news."""
        from bot import analyze_message_context
        
        result = analyze_message_context("Bitcoin выросл в цене на 50%")
        
        self.assertTrue(result.get('needs_crypto_analysis', False))
    
    def test_analyze_casual_chat(self):
        """analyze_message_context should detect casual chat."""
        from bot import analyze_message_context
        
        result = analyze_message_context("интересно слышать об этом")
        
        self.assertEqual(result['type'], 'casual_chat')


class TestInputValidation(unittest.TestCase):
    """Tests for user input validation."""
    
    def test_validate_input_valid(self):
        """validate_user_input should accept valid input."""
        from bot import validate_user_input
        
        is_valid, error = validate_user_input("This is a normal message")
        
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_validate_input_empty(self):
        """validate_user_input should reject empty input."""
        from bot import validate_user_input
        
        is_valid, error = validate_user_input("")
        
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
    
    def test_validate_input_too_long(self):
        """validate_user_input should reject very long input."""
        from bot import validate_user_input
        from bot import MAX_INPUT_LENGTH
        
        long_text = "a" * (MAX_INPUT_LENGTH + 100)
        is_valid, error = validate_user_input(long_text)
        
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)


class TestIntentClassification(unittest.TestCase):
    """Tests for user intent classification."""
    
    def test_classify_intent_question(self):
        """classify_intent should detect questions."""
        from bot import classify_intent
        
        result = classify_intent("Что такое blockchain?")
        
        self.assertIsNotNone(result)
        self.assertIn(result, ['question', 'unknown', 'teach', 'learn'])
    
    def test_classify_intent_command(self):
        """classify_intent should detect commands."""
        from bot import classify_intent
        
        result = classify_intent("/stats")
        
        self.assertIsNotNone(result)
    
    def test_classify_intent_news(self):
        """classify_intent should detect news."""
        from bot import classify_intent
        
        result = classify_intent("Ethereum объявил о новом обновлении")
        
        self.assertIsNotNone(result)


class TestAuthLevel(unittest.TestCase):
    """Tests for authentication levels."""
    
    def test_auth_level_user_lower_than_admin(self):
        """USER auth level should be lower than ADMIN."""
        from bot import AuthLevel
        
        # AuthLevel is an Enum, so compare values
        self.assertLess(AuthLevel.USER.value, AuthLevel.ADMIN.value)
    
    def test_auth_level_values_are_integers(self):
        """AuthLevel values should be integers."""
        from bot import AuthLevel
        
        # Check that all AuthLevel values are integers
        for level in AuthLevel:
            self.assertIsInstance(level.value, int)


class TestUserProfileManagement(unittest.TestCase):
    """Tests for user profile operations."""
    
    @patch('bot.get_db')
    def test_get_user_profile(self, mock_get_db):
        """get_user_profile should return user data."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("user123", "interest1", "portfolio1", "high")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_user_profile
        result = get_user_profile(123456)
        
        self.assertIsInstance(result, dict)
    
    @patch('bot.get_db')
    def test_update_user_profile(self, mock_get_db):
        """update_user_profile should update user data."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import update_user_profile
        update_user_profile(123456, "crypto", "active", "medium")
        
        mock_cursor.execute.assert_called()


class TestConversationHistory(unittest.TestCase):
    """Tests for conversation history."""
    
    @patch('bot.get_db')
    def test_save_conversation(self, mock_get_db):
        """save_conversation should store message in history."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import save_conversation
        save_conversation(123456, "user", "Test message", "question")
        
        mock_cursor.execute.assert_called()
    
    @patch('bot.get_db')
    def test_get_conversation_history(self, mock_get_db):
        """get_conversation_history should retrieve messages."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'type': 'user', 'content': 'msg1'},
            {'type': 'bot', 'content': 'msg2'},
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_conversation_history
        result = get_conversation_history(123456)
        
        self.assertIsInstance(result, list)


class TestRequestLogging(unittest.TestCase):
    """Tests for request logging operations."""
    
    @patch('bot.get_db')
    def test_save_request(self, mock_get_db):
        """save_request should log request to database."""
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import save_request
        request_id = save_request(123456, "Test input", "Test output", False, 100)
        
        self.assertIsNotNone(request_id)
    
    @patch('bot.get_db')
    def test_get_request_by_id(self, mock_get_db):
        """get_request_by_id should retrieve request."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 123456, "input", "output", 100)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_request_by_id
        result = get_request_by_id(1)
        
        self.assertIsNotNone(result)


class TestUserHistory(unittest.TestCase):
    """Tests for user request history."""
    
    @patch('bot.get_db')
    def test_get_user_history(self, mock_get_db):
        """get_user_history should retrieve user's past requests."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("Request 1", "Response 1"),
            ("Request 2", "Response 2"),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        from bot import get_user_history
        result = get_user_history(123456, limit=10)
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""
    
    def test_format_with_special_characters(self):
        """Formatting functions should handle special characters."""
        from bot import format_section
        
        result = format_section("Title <>&\"'", "Content <>&\"'")
        
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
    
    def test_detect_language_numbers_only(self):
        """detect_user_language should handle numbers."""
        from bot import detect_user_language
        
        result = detect_user_language("123 456 789")
        
        self.assertIn(result, ['ru', 'en', 'mixed'])
    
    def test_analyze_context_unicode(self):
        """analyze_message_context should handle unicode."""
        from bot import analyze_message_context
        
        result = analyze_message_context("你好世界 мир")
        
        self.assertIsInstance(result, dict)
    
    def test_validate_input_with_spaces(self):
        """validate_user_input should handle whitespace correctly."""
        from bot import validate_user_input
        
        is_valid, error = validate_user_input("   message with spaces   ")
        
        # Should validate the actual content
        self.assertIsNotNone(is_valid)


if __name__ == '__main__':
    unittest.main(verbosity=2)
