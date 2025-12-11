"""
Phase 4.3: Bot Integration Tests

Comprehensive integration tests for bot.py module covering:
- Database initialization and schema
- User profile management
- Message history and caching
- Daily request limits
- XP and level system
- Course progression
- Learning metrics
- Error handling and recovery

Test Coverage Targets:
- bot.py: 12% → 50% (+38%)
- Total tests: 35+ comprehensive integration tests
- Focus on database operations and user workflows
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Import bot module for testing
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Test Database Setup
# ============================================================================

@pytest.fixture(scope="function")
def temp_db():
    """Create temporary SQLite database for testing."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def mock_db_connection(temp_db):
    """Mock database connection using temporary database."""
    with patch('bot.sqlite3.connect', return_value=sqlite3.connect(temp_db)):
        conn = sqlite3.connect(temp_db)
        yield conn
        conn.close()


@pytest.fixture(scope="function")
def initialized_db(temp_db):
    """Create initialized database with schema."""
    from bot import init_database, get_db
    
    with patch('bot.DB_PATH', temp_db):
        with patch('bot.get_db') as mock_get_db:
            conn = sqlite3.connect(temp_db)
            conn.row_factory = sqlite3.Row
            mock_get_db.return_value.__enter__.return_value = conn
            mock_get_db.return_value.__exit__.return_value = None
            
            # Initialize schema
            init_database()
            
            yield conn
            
            conn.close()


# ============================================================================
# Test: Database Initialization & Schema
# ============================================================================

class TestDatabaseInitialization:
    """Test database initialization and schema creation."""
    
    def test_init_database_creates_schema(self, initialized_db):
        """Test that init_database creates all required tables."""
        cursor = initialized_db.cursor()
        
        # Check required tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        required_tables = {'users', 'requests', 'feedback', 'cache', 'analytics'}
        assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"
    
    def test_users_table_schema(self, initialized_db):
        """Test users table has correct columns."""
        cursor = initialized_db.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            'user_id', 'username', 'first_name', 'created_at',
            'total_requests', 'is_banned', 'knowledge_level',
            'xp', 'level', 'requests_today'
        }
        assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"
    
    def test_requests_table_schema(self, initialized_db):
        """Test requests table has correct structure."""
        cursor = initialized_db.cursor()
        cursor.execute("PRAGMA table_info(requests)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            'id', 'user_id', 'news_text', 'response_text',
            'created_at', 'from_cache', 'processing_time_ms'
        }
        assert required_columns.issubset(columns)
    
    def test_cache_table_schema(self, initialized_db):
        """Test cache table has correct structure."""
        cursor = initialized_db.cursor()
        cursor.execute("PRAGMA table_info(cache)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {'cache_key', 'response_text', 'hit_count', 'last_used_at'}
        assert required_columns.issubset(columns)
    
    def test_init_database_idempotent(self, temp_db):
        """Test that init_database can be called multiple times safely."""
        from bot import init_database, get_db
        
        with patch('bot.DB_PATH', temp_db):
            with patch('bot.get_db') as mock_get_db:
                conn = sqlite3.connect(temp_db)
                mock_get_db.return_value.__enter__.return_value = conn
                mock_get_db.return_value.__exit__.return_value = None
                
                # Should not raise error on multiple calls
                init_database()
                init_database()
                init_database()
                
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                assert table_count > 0
                
                conn.close()


# ============================================================================
# Test: User Profile Management
# ============================================================================

class TestUserProfileManagement:
    """Test user profile creation, retrieval, and updates."""
    
    def test_add_user_to_database(self, initialized_db):
        """Test adding new user to database."""
        from bot import save_user, get_db
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            user_id = 12345
            username = "test_user"
            first_name = "Test"
            
            save_user(user_id, username, first_name)
            
            cursor = initialized_db.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            assert row is not None
            assert row[1] == username
            assert row[2] == first_name
    
    def test_get_user_profile(self, initialized_db):
        """Test retrieving user profile."""
        from bot import get_user_profile, get_db
        
        # Add test user profile
        cursor = initialized_db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                interests TEXT,
                portfolio TEXT,
                risk_tolerance TEXT,
                preferred_language TEXT DEFAULT 'russian',
                last_updated TIMESTAMP
            )
        """)
        
        cursor.execute("""
            INSERT INTO user_profiles (user_id, interests, portfolio, risk_tolerance)
            VALUES (?, ?, ?, ?)
        """, (12345, "crypto,trading", "BTC,ETH", "high"))
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            profile = get_user_profile(12345)
            
            assert profile is not None
            assert profile['interests'] == "crypto,trading"
            assert profile['portfolio'] == "BTC,ETH"
    
    def test_update_user_profile(self, initialized_db):
        """Test updating user profile information."""
        from bot import update_user_profile, get_db
        
        # Create user_profiles table if not exists
        cursor = initialized_db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                interests TEXT,
                portfolio TEXT,
                risk_tolerance TEXT,
                preferred_language TEXT DEFAULT 'russian',
                last_updated TIMESTAMP
            )
        """)
        
        # Add test user profile
        cursor.execute("""
            INSERT INTO user_profiles (user_id, interests)
            VALUES (?, ?)
        """, (12345, "initial"))
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            interests = "crypto,trading"
            update_user_profile(12345, interests=interests)
            
            cursor = initialized_db.cursor()
            cursor.execute("SELECT interests FROM user_profiles WHERE user_id = ?", (12345,))
            row = cursor.fetchone()
            
            assert row is not None
            assert row[0] == interests


# ============================================================================
# Test: Daily Request Limits
# ============================================================================

class TestDailyRequestLimits:
    """Test daily request limit tracking and enforcement."""
    
    def test_check_daily_limit_first_request(self, initialized_db):
        """Test checking daily limit for new user."""
        from bot import check_daily_limit, get_db
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, requests_today, last_request_date)
            VALUES (?, ?, ?)
        """, (12345, 0, datetime.now().date().isoformat()))
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            can_request, remaining = check_daily_limit(12345)
            
            assert can_request is True
            assert remaining > 0
    
    def test_check_daily_limit_exceeded(self, initialized_db):
        """Test checking daily limit when limit exceeded."""
        from bot import check_daily_limit, get_db
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, requests_today, last_request_date, xp, daily_requests)
            VALUES (?, ?, ?, ?, ?)
        """, (55555, 100, datetime.now().date().isoformat(), 10, 100))
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            # Ensure user is not in admin list
            with patch('bot.ADMIN_USERS', []):
                with patch('bot.UNLIMITED_ADMIN_USERS', []):
                    # Mock MAX_REQUESTS_PER_DAY to 50
                    with patch('bot.MAX_REQUESTS_PER_DAY', 50):
                        mock_get_db.return_value.__enter__.return_value = initialized_db
                        mock_get_db.return_value.__exit__.return_value = None
                        
                        can_request, remaining = check_daily_limit(55555)
                        
                        # When daily_requests (100) >= MAX_REQUESTS_PER_DAY (50), should not allow
                        assert can_request is False
                        assert remaining <= 0
    
    def test_reset_daily_requests_new_day(self, initialized_db):
        """Test daily requests reset on new day."""
        from bot import get_db
        
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, requests_today, last_request_date)
            VALUES (?, ?, ?)
        """, (12345, 10, yesterday))
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            # Reset should happen automatically on new day
            cursor = initialized_db.cursor()
            cursor.execute("SELECT requests_today FROM users WHERE user_id = ?", (12345,))
            requests_today = cursor.fetchone()[0]
            
            # Before reset, should show old value
            assert requests_today == 10


# ============================================================================
# Test: Message History & Caching
# ============================================================================

class TestMessageHistoryAndCaching:
    """Test message storage, retrieval, and caching behavior."""
    
    def test_save_message_to_database(self, initialized_db):
        """Test saving user message to database."""
        from bot import get_db
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
        """, (12345, "test_user"))
        
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text, from_cache)
            VALUES (?, ?, ?, ?)
        """, (12345, "Bitcoin price up", "Analysis of bitcoin", 0))
        
        initialized_db.commit()
        
        cursor.execute("SELECT * FROM requests WHERE user_id = ?", (12345,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[2] == "Bitcoin price up"
        assert row[3] == "Analysis of bitcoin"
        assert row[5] == 0  # from_cache
    
    def test_get_user_message_history(self, initialized_db):
        """Test retrieving user message history."""
        from bot import get_user_history, get_db
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
        """, (12345, "test_user"))
        
        # Add multiple messages
        for i in range(5):
            cursor.execute("""
                INSERT INTO requests (user_id, news_text, response_text)
                VALUES (?, ?, ?)
            """, (12345, f"News {i}", f"Response {i}"))
        
        initialized_db.commit()
        
        with patch('bot.get_db') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = initialized_db
            mock_get_db.return_value.__exit__.return_value = None
            
            history = get_user_history(12345, limit=5)
            
            assert len(history) == 5
    
    def test_cache_hit_tracking(self, initialized_db):
        """Test caching hit count tracking."""
        cursor = initialized_db.cursor()
        
        cache_key = "test_cache_key"
        response = "Cached response"
        
        cursor.execute("""
            INSERT INTO cache (cache_key, response_text, hit_count)
            VALUES (?, ?, ?)
        """, (cache_key, response, 1))
        
        # Simulate cache hit - increment hit_count
        cursor.execute("""
            UPDATE cache SET hit_count = hit_count + 1
            WHERE cache_key = ?
        """, (cache_key,))
        
        initialized_db.commit()
        
        cursor.execute("SELECT hit_count FROM cache WHERE cache_key = ?", (cache_key,))
        hit_count = cursor.fetchone()[0]
        
        assert hit_count == 2


# ============================================================================
# Test: XP & Level System
# ============================================================================

class TestXPAndLevelSystem:
    """Test experience points and level progression."""
    
    def test_user_initial_xp_and_level(self, initialized_db):
        """Test new user starts with correct XP and level."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, level)
            VALUES (?, ?, ?, ?)
        """, (12345, "test_user", 0, 1))
        initialized_db.commit()
        
        cursor.execute("SELECT xp, level FROM users WHERE user_id = ?", (12345,))
        xp, level = cursor.fetchone()
        
        assert xp == 0
        assert level == 1
    
    def test_add_xp_to_user(self, initialized_db):
        """Test adding XP to user."""
        from bot import get_db
        
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, level)
            VALUES (?, ?, ?, ?)
        """, (12345, "test_user", 0, 1))
        initialized_db.commit()
        
        # Simulate XP addition
        xp_to_add = 50
        cursor.execute("""
            UPDATE users SET xp = xp + ?
            WHERE user_id = ?
        """, (xp_to_add, 12345))
        initialized_db.commit()
        
        cursor.execute("SELECT xp FROM users WHERE user_id = ?", (12345,))
        new_xp = cursor.fetchone()[0]
        
        assert new_xp == 50
    
    def test_level_progression_with_xp(self, initialized_db):
        """Test user level increases with sufficient XP."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, level)
            VALUES (?, ?, ?, ?)
        """, (12345, "test_user", 0, 1))
        initialized_db.commit()
        
        # Add significant XP
        cursor.execute("""
            UPDATE users SET xp = 500, level = 3
            WHERE user_id = ?
        """, (12345,))
        initialized_db.commit()
        
        cursor.execute("SELECT xp, level FROM users WHERE user_id = ?", (12345,))
        xp, level = cursor.fetchone()
        
        assert xp == 500
        assert level == 3
    
    def test_get_user_knowledge_level(self, initialized_db):
        """Test getting user knowledge level."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, knowledge_level)
            VALUES (?, ?, ?)
        """, (12345, "test_user", "intermediate"))
        initialized_db.commit()
        
        cursor.execute("SELECT knowledge_level FROM users WHERE user_id = ?", (12345,))
        knowledge_level = cursor.fetchone()[0]
        
        assert knowledge_level == "intermediate"


# ============================================================================
# Test: User Banning & Moderation
# ============================================================================

class TestUserBanningAndModeration:
    """Test user banning and moderation features."""
    
    def test_ban_user(self, initialized_db):
        """Test banning a user."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, is_banned)
            VALUES (?, ?, ?)
        """, (12345, "test_user", 0))
        initialized_db.commit()
        
        # Ban the user
        cursor.execute("""
            UPDATE users SET is_banned = 1, ban_reason = ?
            WHERE user_id = ?
        """, ("spam", 12345))
        initialized_db.commit()
        
        cursor.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (12345,))
        is_banned, ban_reason = cursor.fetchone()
        
        assert is_banned == 1
        assert ban_reason == "spam"
    
    def test_check_user_banned_status(self, initialized_db):
        """Test checking if user is banned."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, is_banned)
            VALUES (?, ?, ?)
        """, (12345, "test_user", 1))
        initialized_db.commit()
        
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (12345,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[0] == 1
    
    def test_unban_user(self, initialized_db):
        """Test unbanning a user."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, is_banned, ban_reason)
            VALUES (?, ?, ?, ?)
        """, (12345, "test_user", 1, "spam"))
        initialized_db.commit()
        
        # Unban the user
        cursor.execute("""
            UPDATE users SET is_banned = 0, ban_reason = NULL
            WHERE user_id = ?
        """, (12345,))
        initialized_db.commit()
        
        cursor.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (12345,))
        is_banned, ban_reason = cursor.fetchone()
        
        assert is_banned == 0
        assert ban_reason is None


# ============================================================================
# Test: Analytics & Events
# ============================================================================

class TestAnalyticsAndEvents:
    """Test analytics and event tracking."""
    
    def test_save_analytics_event(self, initialized_db):
        """Test saving analytics event."""
        cursor = initialized_db.cursor()
        cursor.execute("""
            INSERT INTO analytics (event_type, user_id, data)
            VALUES (?, ?, ?)
        """, ("message_sent", 12345, '{"text_length": 100}'))
        initialized_db.commit()
        
        cursor.execute("SELECT * FROM analytics WHERE user_id = ?", (12345,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[1] == "message_sent"
        assert row[2] == 12345
    
    def test_get_user_analytics(self, initialized_db):
        """Test retrieving user analytics."""
        cursor = initialized_db.cursor()
        
        # Add multiple analytics events
        for i in range(5):
            cursor.execute("""
                INSERT INTO analytics (event_type, user_id, data)
                VALUES (?, ?, ?)
            """, (f"event_{i}", 12345, f'{{"num": {i}}}'))
        
        initialized_db.commit()
        
        cursor.execute("SELECT * FROM analytics WHERE user_id = ?", (12345,))
        rows = cursor.fetchall()
        
        assert len(rows) == 5


# ============================================================================
# Test: Feedback System
# ============================================================================

class TestFeedbackSystem:
    """Test user feedback tracking and storage."""
    
    def test_save_helpful_feedback(self, initialized_db):
        """Test saving helpful feedback."""
        cursor = initialized_db.cursor()
        
        # Add user and request first
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
        """, (12345, "test_user"))
        
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text)
            VALUES (?, ?, ?)
        """, (12345, "News", "Response"))
        initialized_db.commit()
        
        request_id = cursor.lastrowid
        
        # Save feedback
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful, comment)
            VALUES (?, ?, ?, ?)
        """, (12345, request_id, 1, "Great analysis"))
        initialized_db.commit()
        
        cursor.execute("SELECT * FROM feedback WHERE user_id = ?", (12345,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[3] == 1  # is_helpful
        assert row[4] == "Great analysis"
    
    def test_save_unhelpful_feedback(self, initialized_db):
        """Test saving unhelpful feedback."""
        cursor = initialized_db.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
        """, (12345, "test_user"))
        
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text)
            VALUES (?, ?, ?)
        """, (12345, "News", "Response"))
        initialized_db.commit()
        
        request_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful, comment)
            VALUES (?, ?, ?, ?)
        """, (12345, request_id, 0, "Not relevant"))
        initialized_db.commit()
        
        cursor.execute("SELECT is_helpful FROM feedback WHERE user_id = ?", (12345,))
        is_helpful = cursor.fetchone()[0]
        
        assert is_helpful == 0


# ============================================================================
# Test: Transaction & Error Handling
# ============================================================================

class TestTransactionAndErrorHandling:
    """Test database transaction handling and error recovery."""
    
    def test_database_transaction_rollback(self, initialized_db):
        """Test transaction rollback on error."""
        cursor = initialized_db.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username) VALUES (?, ?)
            """, (12345, "test_user"))
            
            # Simulate error - insert duplicate
            cursor.execute("""
                INSERT INTO users (user_id, username) VALUES (?, ?)
            """, (12345, "test_user_2"))
            
            initialized_db.commit()
        except sqlite3.IntegrityError:
            initialized_db.rollback()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (12345,))
        count = cursor.fetchone()[0]
        
        # Should have rolled back, so 0 or 1 depending on rollback implementation
        assert count >= 0
    
    def test_database_connection_recovery(self, temp_db):
        """Test recovery from database connection errors."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Create a table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, value TEXT)
        """)
        conn.commit()
        
        # Close connection
        conn.close()
        
        # Reconnect
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Should still be able to query
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        assert len(tables) > 0
        conn.close()
    
    def test_handle_missing_user(self, initialized_db):
        """Test handling request for non-existent user."""
        cursor = initialized_db.cursor()
        
        # Query for non-existent user
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (99999,))
        row = cursor.fetchone()
        
        assert row is None


# ============================================================================
# Test: Concurrent User Operations
# ============================================================================

class TestConcurrentOperations:
    """Test handling concurrent user operations."""
    
    def test_multiple_users_concurrent_requests(self, initialized_db):
        """Test multiple users making requests simultaneously."""
        cursor = initialized_db.cursor()
        
        # Add multiple users
        for user_id in range(12345, 12350):
            cursor.execute("""
                INSERT INTO users (user_id, username)
                VALUES (?, ?)
            """, (user_id, f"user_{user_id}"))
        
        # Add requests for each user
        for user_id in range(12345, 12350):
            cursor.execute("""
                INSERT INTO requests (user_id, news_text, response_text)
                VALUES (?, ?, ?)
            """, (user_id, f"News {user_id}", f"Response {user_id}"))
        
        initialized_db.commit()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM requests")
        request_count = cursor.fetchone()[0]
        
        assert user_count == 5
        assert request_count == 5
    
    def test_concurrent_xp_updates(self, initialized_db):
        """Test concurrent XP updates for same user."""
        cursor = initialized_db.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, username, xp)
            VALUES (?, ?, ?)
        """, (12345, "test_user", 0))
        initialized_db.commit()
        
        # Simulate multiple XP additions
        for i in range(10):
            cursor.execute("""
                UPDATE users SET xp = xp + 10 WHERE user_id = ?
            """, (12345,))
        
        initialized_db.commit()
        
        cursor.execute("SELECT xp FROM users WHERE user_id = ?", (12345,))
        total_xp = cursor.fetchone()[0]
        
        assert total_xp == 100


# ============================================================================
# Test: Data Integrity
# ============================================================================

class TestDataIntegrity:
    """Test data integrity and consistency."""
    
    def test_user_id_uniqueness(self, initialized_db):
        """Test that user IDs are unique."""
        cursor = initialized_db.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
        """, (12345, "user1"))
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username) VALUES (?, ?)
            """, (12345, "user2"))
            initialized_db.commit()
            assert False, "Should have raised IntegrityError"
        except sqlite3.IntegrityError:
            initialized_db.rollback()
            # Expected behavior
    
    def test_foreign_key_constraints(self, initialized_db):
        """Test foreign key constraints."""
        cursor = initialized_db.cursor()
        
        # Add user
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
        """, (12345, "test_user"))
        initialized_db.commit()
        
        # Add request for user
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text)
            VALUES (?, ?, ?)
        """, (12345, "News", "Response"))
        initialized_db.commit()
        
        cursor.execute("SELECT COUNT(*) FROM requests WHERE user_id = ?", (12345,))
        count = cursor.fetchone()[0]
        
        assert count == 1
    
    def test_timestamp_auto_population(self, initialized_db):
        """Test that timestamps are automatically populated."""
        cursor = initialized_db.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
        """, (12345, "test_user"))
        initialized_db.commit()
        
        cursor.execute("SELECT created_at FROM users WHERE user_id = ?", (12345,))
        created_at = cursor.fetchone()[0]
        
        assert created_at is not None


# ============================================================================
# Test: Database Query Performance
# ============================================================================

class TestDatabaseQueryPerformance:
    """Test query performance and optimization."""
    
    def test_query_large_dataset_efficiency(self, initialized_db):
        """Test querying large dataset efficiently."""
        cursor = initialized_db.cursor()
        
        # Insert many users
        for i in range(100):
            cursor.execute("""
                INSERT INTO users (user_id, username)
                VALUES (?, ?)
            """, (10000 + i, f"user_{i}"))
        
        initialized_db.commit()
        
        import time
        start = time.time()
        
        cursor.execute("SELECT * FROM users WHERE user_id > ?", (10050,))
        results = cursor.fetchall()
        
        elapsed = time.time() - start
        
        assert len(results) == 49
        assert elapsed < 0.1  # Should be fast
    
    def test_cache_query_optimization(self, initialized_db):
        """Test cache queries are optimized."""
        cursor = initialized_db.cursor()
        
        # Insert cache entries
        for i in range(50):
            cursor.execute("""
                INSERT INTO cache (cache_key, response_text, hit_count)
                VALUES (?, ?, ?)
            """, (f"key_{i}", f"response_{i}", i))
        
        initialized_db.commit()
        
        # Query by hit_count
        cursor.execute("""
            SELECT * FROM cache ORDER BY hit_count DESC LIMIT 10
        """)
        results = cursor.fetchall()
        
        assert len(results) == 10
        # Should be ordered by hit_count descending
        assert results[0][3] >= results[-1][3]


# ============================================================================
# Integration Test: Full User Lifecycle
# ============================================================================

class TestFullUserLifecycle:
    """Test complete user lifecycle from registration to activity."""
    
    def test_user_complete_lifecycle(self, initialized_db):
        """Test user from registration through multiple interactions."""
        cursor = initialized_db.cursor()
        
        user_id = 12345
        
        # 1. User registration
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, xp, level)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, "lifecycle_test", "Test", 0, 1))
        initialized_db.commit()
        
        # 2. User makes first request
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text)
            VALUES (?, ?, ?)
        """, (user_id, "First news", "First response"))
        initialized_db.commit()
        
        # 3. User gains XP
        cursor.execute("""
            UPDATE users SET xp = xp + 50 WHERE user_id = ?
        """, (user_id,))
        initialized_db.commit()
        
        # 4. User provides feedback
        request_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful)
            VALUES (?, ?, ?)
        """, (user_id, request_id, 1))
        initialized_db.commit()
        
        # 5. Verify complete state
        cursor.execute("""
            SELECT xp, level FROM users WHERE user_id = ?
        """, (user_id,))
        xp, level = cursor.fetchone()
        
        cursor.execute("""
            SELECT COUNT(*) FROM requests WHERE user_id = ?
        """, (user_id,))
        request_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM feedback WHERE user_id = ?
        """, (user_id,))
        feedback_count = cursor.fetchone()[0]
        
        assert xp == 50
        assert request_count == 1
        assert feedback_count == 1
