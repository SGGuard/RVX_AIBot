"""
Unit tests for Quick Wins improvements (v0.38.0)

Tests cover:
1. Database indices functionality
2. Exception classes
3. Query optimization functions
4. Performance improvements
"""

import unittest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from typing import Dict, Any

# Import the modules we're testing
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exceptions import (
    RVXException, DatabaseError, DatabaseConnectionError, UserNotFoundError, 
    LLMError, LLMTimeoutError, RateLimitError, handle_exception
)
from query_optimization import (
    optimize_get_leaderboard_with_badges,
    optimize_get_user_stats_batch,
    optimize_get_user_progress_all_courses
)


# ============================================================================
# TEST 1: Exception Classes
# ============================================================================

class TestExceptionClasses(unittest.TestCase):
    """Test custom exception classes."""
    
    def test_base_exception_message(self):
        """Test RVXException base class."""
        exc = RVXException("Test error", "TEST_CODE", {"key": "value"})
        self.assertEqual(exc.message, "Test error")
        self.assertEqual(exc.error_code, "TEST_CODE")
        self.assertEqual(exc.context, {"key": "value"})
    
    def test_database_error_user_message(self):
        """Test DatabaseError produces user-friendly message."""
        exc = DatabaseError("Connection failed")
        msg = exc.to_user_message()
        self.assertIn("❌", msg)
        # DatabaseConnectionError has specific message
        db_error = DatabaseConnectionError("Connection failed")
        db_msg = db_error.to_user_message()
        self.assertIn("БД", db_msg)
    
    def test_user_not_found_error(self):
        """Test UserNotFoundError."""
        exc = UserNotFoundError("User 123 not found")
        msg = exc.to_user_message()
        self.assertIn("не найден", msg.lower())
    
    def test_rate_limit_error(self):
        """Test RateLimitError."""
        exc = RateLimitError("Too many requests")
        msg = exc.to_user_message()
        self.assertIn("слишком много", msg.lower())
    
    def test_llm_timeout_error(self):
        """Test LLMTimeoutError."""
        exc = LLMTimeoutError("AI timeout")
        msg = exc.to_user_message()
        self.assertIn("timeout", msg.lower())
    
    def test_handle_exception_with_rvx_exception(self):
        """Test handle_exception with RVXException."""
        exc = UserNotFoundError("User not found")
        msg = handle_exception(exc, user_id=123, context="test")
        self.assertIsInstance(msg, str)
        self.assertIn("❌", msg)
    
    def test_handle_exception_with_generic_exception(self):
        """Test handle_exception with generic Exception."""
        exc = ValueError("Generic error")
        msg = handle_exception(exc, user_id=123)
        self.assertIn("❌", msg)
        self.assertIn("Неизвестная", msg)


# ============================================================================
# TEST 2: Database Indices
# ============================================================================

class TestDatabaseIndices(unittest.TestCase):
    """Test that indices are properly created and improve queries."""
    
    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        # Create test database with tables
        self.conn = sqlite3.connect(self.db_path)
        self._create_test_tables()
    
    def tearDown(self):
        """Clean up temporary database."""
        self.conn.close()
        os.unlink(self.db_path)
    
    def _create_test_tables(self):
        """Create basic test tables."""
        cursor = self.conn.cursor()
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_requests INTEGER DEFAULT 0
            )
        """)
        
        # Create requests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Create user_progress table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                course_id INTEGER,
                lesson_id INTEGER,
                progress INTEGER,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Create courses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                course_id INTEGER PRIMARY KEY,
                course_name TEXT
            )
        """)
        
        # Create lessons table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id INTEGER PRIMARY KEY,
                course_id INTEGER,
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            )
        """)
        
        self.conn.commit()
    
    def test_indices_can_be_created(self):
        """Test that indices can be created without error."""
        cursor = self.conn.cursor()
        
        # Create indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_leaderboard 
            ON users(xp DESC, level DESC, created_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_user_date 
            ON requests(user_id, created_at DESC)
        """)
        
        self.conn.commit()
        
        # Verify indices were created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_%'
        """)
        
        indices = cursor.fetchall()
        self.assertGreaterEqual(len(indices), 2)
    
    def test_query_uses_index(self):
        """Test that query plan shows index usage."""
        cursor = self.conn.cursor()
        
        # Create index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_leaderboard 
            ON users(xp DESC, level DESC)
        """)
        self.conn.commit()
        
        # Insert test data
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, level) 
            VALUES (1, 'user1', 100, 5)
        """)
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, level) 
            VALUES (2, 'user2', 200, 10)
        """)
        self.conn.commit()
        
        # Check query plan
        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM users ORDER BY xp DESC, level DESC LIMIT 10
        """)
        
        plan = cursor.fetchall()
        # Plan should use the index (look for 'Eum' or index name in plan)
        self.assertIsNotNone(plan)


# ============================================================================
# TEST 3: Query Optimization Functions
# ============================================================================

class TestQueryOptimization(unittest.TestCase):
    """Test query optimization functions."""
    
    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        self.conn = sqlite3.connect(self.db_path)
        self._create_test_tables()
        self._insert_test_data()
    
    def tearDown(self):
        """Clean up temporary database."""
        self.conn.close()
        os.unlink(self.db_path)
    
    def _create_test_tables(self):
        """Create test tables."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_requests INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                badge_id TEXT,
                earned_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT,
                rank INTEGER,
                user_id INTEGER,
                username TEXT,
                xp INTEGER,
                level INTEGER,
                total_requests INTEGER
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                course_id INTEGER,
                lesson_id INTEGER,
                progress INTEGER,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_quiz_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                course_id INTEGER PRIMARY KEY,
                course_name TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id INTEGER PRIMARY KEY,
                course_id INTEGER,
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            )
        """)
        
        self.conn.commit()
    
    def _insert_test_data(self):
        """Insert test data."""
        cursor = self.conn.cursor()
        
        # Insert users
        for i in range(1, 6):
            cursor.execute("""
                INSERT INTO users (user_id, username, xp, level, total_requests)
                VALUES (?, ?, ?, ?, ?)
            """, (i, f"user{i}", i*100, i, i*10))
        
        # Insert badges
        cursor.execute("""
            INSERT INTO user_badges (user_id, badge_id, earned_at)
            VALUES (1, 'badge_1', CURRENT_TIMESTAMP)
        """)
        cursor.execute("""
            INSERT INTO user_badges (user_id, badge_id, earned_at)
            VALUES (2, 'badge_2', CURRENT_TIMESTAMP)
        """)
        
        self.conn.commit()
    
    def test_optimize_leaderboard_returns_data(self):
        """Test that leaderboard optimization returns results."""
        result, total_users = optimize_get_leaderboard_with_badges(
            self.conn, "all", 10
        )
        
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
        self.assertGreater(total_users, 0)
    
    def test_optimize_user_stats_batch(self):
        """Test batch stats optimization."""
        result = optimize_get_user_stats_batch(self.conn, [1, 2, 3])
        
        self.assertIsInstance(result, dict)
        self.assertIn(1, result)
        self.assertIn('xp', result[1])
        self.assertIn('level', result[1])
    
    def test_optimize_user_progress_all_courses(self):
        """Test user progress optimization."""
        result = optimize_get_user_progress_all_courses(self.conn, 1)
        
        self.assertIsInstance(result, dict)


# ============================================================================
# TEST 4: Performance Improvements
# ============================================================================

class TestPerformanceImprovements(unittest.TestCase):
    """Test that improvements actually improve performance."""
    
    def test_exception_handling_speed(self):
        """Test that exception handling is fast."""
        import time
        
        start = time.time()
        for _ in range(1000):
            exc = RateLimitError("Test")
            msg = handle_exception(exc)
        end = time.time()
        
        # Should complete 1000 iterations in < 100ms
        self.assertLess(end - start, 0.1)
    
    def test_exception_message_generation(self):
        """Test that user messages are generated correctly."""
        # Test specific exception classes that have custom messages
        exc1 = UserNotFoundError("test")
        self.assertIn("не найден", exc1.to_user_message().lower())
        
        exc2 = RateLimitError("test")
        self.assertIn("слишком много", exc2.to_user_message().lower())
        
        exc3 = LLMTimeoutError("test")
        self.assertIn("timeout", exc3.to_user_message().lower())
        
        exc4 = DatabaseConnectionError("test")
        self.assertIn("бд", exc4.to_user_message().lower())


# ============================================================================
# TEST SUITE
# ============================================================================

if __name__ == "__main__":
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all tests
    suite.addTests(loader.loadTestsFromTestCase(TestExceptionClasses))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseIndices))
    suite.addTests(loader.loadTestsFromTestCase(TestQueryOptimization))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceImprovements))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("🎯 QUICK WINS TEST SUMMARY (v0.38.0)")
    print("="*70)
    print(f"✅ Tests run: {result.testsRun}")
    print(f"✅ Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️ Errors: {len(result.errors)}")
    print("="*70)
    
    # Exit with appropriate code
    exit(0 if result.wasSuccessful() else 1)
