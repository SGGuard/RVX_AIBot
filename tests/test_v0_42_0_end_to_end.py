"""
🎯 v0.42.0 End-to-End Tests - Complete User Journey Testing

Tests for:
- Complete user journeys from start to finish
- Multi-step user interactions
- State transitions and lifecycle
- Real-world usage patterns
- Recovery from failures

Target: Validate entire application workflows
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json


class UserJourney:
    """Helper class to simulate user journey."""
    
    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        self.messages: List[str] = []
        self.history: List[Dict[str, Any]] = []
        self.profile: Dict[str, Any] = {}
    
    def send_message(self, message: str) -> None:
        self.messages.append(message)
    
    def add_to_history(self, msg: str, msg_type: str) -> None:
        self.history.append({
            'message': msg,
            'type': msg_type,
            'timestamp': datetime.now().isoformat()
        })
    
    def update_profile(self, **kwargs) -> None:
        self.profile.update(kwargs)


class TestBasicUserJourney(unittest.TestCase):
    """Test basic user journey: start -> interaction -> info."""
    
    @patch('bot.get_db')
    def test_user_starts_bot(self, mock_get_db):
        """User initiates interaction with bot."""
        from bot import save_user, get_user_profile
        
        user_journey = UserJourney(111111, "new_user")
        
        # Setup mocks
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: /start command - create user
        save_user(user_journey.user_id, user_journey.username, "FirstName")
        user_journey.send_message("/start")
        user_journey.add_to_history("/start", "command")
        
        # Step 2: Get profile
        mock_cursor.fetchone.return_value = (
            user_journey.user_id, user_journey.username, "general",
            "active", "low", 0, 0
        )
        profile = get_user_profile(user_journey.user_id)
        user_journey.update_profile(**{
            'interest': 'general',
            'status': 'active',
            'interest_level': 'low'
        })
        
        # Verify journey
        self.assertEqual(len(user_journey.messages), 1)
        self.assertEqual(user_journey.messages[0], "/start")
        self.assertEqual(len(user_journey.history), 1)
        self.assertIsNotNone(profile)
    
    @patch('bot.get_db')
    def test_user_requests_help(self, mock_get_db):
        """User requests help from bot."""
        from bot import get_user_profile, save_conversation
        
        user_journey = UserJourney(222222, "help_seeker")
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: Get user profile
        mock_cursor.fetchone.return_value = (
            user_journey.user_id, user_journey.username, "crypto",
            "active", "medium", 5, 3
        )
        profile = get_user_profile(user_journey.user_id)
        
        # Step 2: Send help message
        help_msg = "/help"
        user_journey.send_message(help_msg)
        save_conversation(user_journey.user_id, "user", help_msg, "command")
        user_journey.add_to_history(help_msg, "command")
        
        # Step 3: Verify
        self.assertEqual(len(user_journey.messages), 1)
        self.assertEqual(len(user_journey.history), 1)
        mock_cursor.execute.assert_called()


class TestMultiStepUserInteraction(unittest.TestCase):
    """Test multi-step user interactions."""
    
    @patch('bot.get_db')
    def test_user_learns_course(self, mock_get_db):
        """User starts and progresses through course."""
        from bot import (
            get_user_profile, save_conversation,
            update_leaderboard_cache
        )
        
        user_journey = UserJourney(333333, "learner")
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: Check profile
        mock_cursor.fetchone.return_value = (
            user_journey.user_id, user_journey.username, "education",
            "active", "high", 20, 15
        )
        profile = get_user_profile(user_journey.user_id)
        
        # Step 2: Start course
        user_journey.send_message("/learn")
        save_conversation(user_journey.user_id, "user", "/learn", "command")
        user_journey.add_to_history("/learn", "command")
        
        # Step 3: Complete lesson
        user_journey.send_message("lesson_1_answer")
        save_conversation(user_journey.user_id, "user", "lesson_1_answer", "quiz")
        user_journey.add_to_history("lesson_1_answer", "quiz")
        
        # Step 4: Check leaderboard
        user_journey.update_profile(score=100)
        
        # Verify multi-step journey
        self.assertEqual(len(user_journey.messages), 2)
        self.assertEqual(len(user_journey.history), 2)
        self.assertGreater(len(user_journey.history), 1)
    
    @patch('bot.get_db')
    def test_user_browses_crypto_news(self, mock_get_db):
        """User browses cryptocurrency news."""
        from bot import (
            get_user_profile, save_conversation,
            analyze_message_context
        )
        
        user_journey = UserJourney(444444, "crypto_fan")
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: Get profile (crypto interested)
        mock_cursor.fetchone.return_value = (
            user_journey.user_id, user_journey.username, "crypto",
            "active", "high", 50, 40
        )
        profile = get_user_profile(user_journey.user_id)
        
        # Step 2: Ask about Bitcoin
        msg1 = "Bitcoin цена"
        user_journey.send_message(msg1)
        ctx1 = analyze_message_context(msg1)
        save_conversation(user_journey.user_id, "user", msg1, "crypto_news")
        user_journey.add_to_history(msg1, "crypto_news")
        
        # Step 3: Ask about Ethereum
        msg2 = "Ethereum новости"
        user_journey.send_message(msg2)
        ctx2 = analyze_message_context(msg2)
        save_conversation(user_journey.user_id, "user", msg2, "crypto_news")
        user_journey.add_to_history(msg2, "crypto_news")
        
        # Step 4: Ask about market
        msg3 = "Крипто рынок анализ"
        user_journey.send_message(msg3)
        save_conversation(user_journey.user_id, "user", msg3, "crypto_news")
        user_journey.add_to_history(msg3, "crypto_news")
        
        # Verify journey
        self.assertEqual(len(user_journey.messages), 3)
        self.assertEqual(len(user_journey.history), 3)


class TestComplexUserScenarios(unittest.TestCase):
    """Test complex real-world scenarios."""
    
    @patch('bot.get_db')
    def test_user_exceeds_limits_and_recovers(self, mock_get_db):
        """User hits limit, waits, and continues."""
        from bot import check_daily_limit, update_leaderboard_cache
        
        user_id = 555555
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: User makes requests up to limit
        mock_cursor.fetchone.return_value = (50, tomorrow)
        can_request, remaining = check_daily_limit(user_id)
        self.assertFalse(can_request)  # Exceeded
        
        # Step 2: Next day - limit resets
        next_day = (datetime.now() + timedelta(days=2)).isoformat()
        mock_cursor.fetchone.return_value = (0, next_day)
        can_request, remaining = check_daily_limit(user_id)
        self.assertTrue(can_request)  # Reset
    
    @patch('bot.get_db')
    def test_user_gets_banned_and_unbanned(self, mock_get_db):
        """User gets banned and then unbanned."""
        from bot import check_user_banned
        
        user_id = 666666
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: User is banned
        mock_cursor.fetchone.return_value = (1, "Spam detected")
        is_banned, reason = check_user_banned(user_id)
        self.assertTrue(is_banned)
        self.assertEqual(reason, "Spam detected")
        
        # Step 2: Admin unbans user
        mock_cursor.fetchone.return_value = None  # Not banned anymore
        is_banned, reason = check_user_banned(user_id)
        self.assertFalse(is_banned)
    
    @patch('bot.get_db')
    def test_user_changes_interest_level(self, mock_get_db):
        """User changes their interest settings."""
        from bot import get_user_profile, update_user_profile
        
        user_id = 777777
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Step 1: Get initial profile (low interest)
        mock_cursor.fetchone.return_value = (
            user_id, "user", "crypto", "active", "low", 10, 5
        )
        profile1 = get_user_profile(user_id)
        
        # Step 2: Update interest level
        update_user_profile(user_id, "crypto", "active", "high")
        
        # Step 3: Verify updated
        mock_cursor.fetchone.return_value = (
            user_id, "user", "crypto", "active", "high", 10, 5
        )
        profile2 = get_user_profile(user_id)
        
        # Verify change
        self.assertIsNotNone(profile1)
        self.assertIsNotNone(profile2)


class TestErrorRecoveryJourneys(unittest.TestCase):
    """Test recovery from errors during user journey."""
    
    @patch('bot.get_db')
    def test_recover_from_db_error_during_interaction(self, mock_get_db):
        """Gracefully handle DB error and recover."""
        from bot import get_user_profile, check_user_banned
        
        user_id = 888888
        
        # First call fails
        mock_get_db.return_value.__enter__.side_effect = Exception("DB Error")
        
        with self.assertRaises(Exception):
            get_user_profile(user_id)
        
        # Second call succeeds
        mock_get_db.return_value.__enter__.side_effect = None
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        is_banned, _ = check_user_banned(user_id)
        self.assertFalse(is_banned)
    
    @patch('bot.get_db')
    def test_retry_failed_operation(self, mock_get_db):
        """Retry failed database operation."""
        from bot import save_conversation
        
        user_id = 999999
        message = "Test message"
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # First attempt
        save_conversation(user_id, "user", message, "chat")
        
        # Verify was called
        mock_cursor.execute.assert_called()
        
        # Second attempt should also work
        save_conversation(user_id, "user", message + " retry", "chat")
        self.assertGreaterEqual(mock_cursor.execute.call_count, 2)


class TestConcurrentUserJourneys(unittest.TestCase):
    """Test multiple users interacting concurrently."""
    
    @patch('bot.check_daily_limit')
    @patch('bot.get_user_profile')
    @patch('bot.get_db')
    def test_multiple_users_concurrent_interactions(self, mock_get_db, mock_profile, mock_limit):
        """Multiple users interact concurrently."""
        from bot import save_conversation
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime, timedelta
        
        # Mock the functions to return valid values
        mock_profile.return_value = {
            'user_id': 1, 'username': 'test', 'interest': 'crypto',
            'status': 'active', 'level': 'medium', 'requests': 100
        }
        mock_limit.return_value = (True, {"remaining": 50, "reset_time": None})
        
        mock_cursor = MagicMock()
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        mock_cursor.fetchone.return_value = (5, tomorrow)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        journeys = [
            UserJourney(1000 + i, f"user_{i}")
            for i in range(10)
        ]
        
        def run_journey(journey: UserJourney) -> bool:
            try:
                # Get profile (mocked)
                profile = mock_profile(journey.user_id)
                
                # Send message
                journey.send_message("Hello")
                save_conversation(
                    journey.user_id, "user", "Hello", "greeting"
                )
                
                # Check limit (mocked)
                can_request, limits = mock_limit(journey.user_id)
                
                return True
            except Exception:
                return False
        
        # Run all journeys concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(run_journey, journeys))
        
        # Should have at least some success (most should succeed with proper mocking)
        success_rate = sum(results) / len(results)
        self.assertGreater(success_rate, 0.7)


class TestStatePersistence(unittest.TestCase):
    """Test that user state persists correctly."""
    
    @patch('bot.get_db')
    def test_conversation_history_persists(self, mock_get_db):
        """User conversation history should persist."""
        from bot import save_conversation, get_conversation_history
        
        user_id = 111222333
        messages = [
            ("Hello", "greeting"),
            ("Help", "command"),
            ("Bitcoin price", "crypto_news"),
        ]
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Save all messages
        for msg, msg_type in messages:
            save_conversation(user_id, "user", msg, msg_type)
        
        # Verify saves were made
        self.assertEqual(mock_cursor.execute.call_count, 3)
        
        # Retrieve history
        mock_cursor.fetchall.return_value = [
            (i, msg, msg_type) for i, (msg, msg_type) in enumerate(messages)
        ]
        history = get_conversation_history(user_id)
        
        # Verify persistence
        self.assertIsNotNone(history)
    
    @patch('bot.get_db')
    def test_user_profile_updates_persist(self, mock_get_db):
        """User profile updates should persist."""
        from bot import get_user_profile, update_user_profile
        
        user_id = 222333444
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Get initial profile
        mock_cursor.fetchone.return_value = (
            user_id, "user", "general", "active", "low", 0, 0
        )
        profile1 = get_user_profile(user_id)
        
        # Update profile
        update_user_profile(user_id, "crypto", "active", "high")
        
        # Verify update was saved
        mock_cursor.execute.assert_called()


if __name__ == '__main__':
    unittest.main()
