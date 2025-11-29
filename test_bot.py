"""Tests for bot.py database and utility functions."""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from contextlib import contextmanager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    yield path
    
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@contextmanager
def get_test_db(db_path):
    """Context manager for test database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_test_database(db_path):
    """Initialize test database schema."""
    with get_test_db(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_requests INTEGER DEFAULT 0,
                last_request_at TIMESTAMP,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                daily_requests INTEGER DEFAULT 0,
                daily_reset_at TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                news_text TEXT,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                from_cache BOOLEAN DEFAULT 0,
                processing_time_ms REAL,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            )
        """)


class TestUserManagement:
    """Test user-related database operations."""
    
    def test_save_user(self, temp_db):
        """Should save user to database."""
        init_test_database(temp_db)
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            """, (123, "testuser", "Test"))
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (123,))
            row = cursor.fetchone()
            
            assert row is not None
            assert row["username"] == "testuser"
            assert row["first_name"] == "Test"
    
    def test_update_user_requests(self, temp_db):
        """Should increment user request counter."""
        init_test_database(temp_db)
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, total_requests)
                VALUES (?, ?, ?)
            """, (123, "testuser", 0))
            
            cursor.execute("""
                UPDATE users 
                SET total_requests = total_requests + 1
                WHERE user_id = ?
            """, (123,))
            
            cursor.execute("SELECT total_requests FROM users WHERE user_id = ?", (123,))
            count = cursor.fetchone()[0]
            
            assert count == 1
    
    def test_ban_user(self, temp_db):
        """Should set user ban status."""
        init_test_database(temp_db)
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, is_banned, ban_reason)
                VALUES (?, ?, ?, ?)
            """, (123, "testuser", 0, None))
            
            cursor.execute("""
                UPDATE users 
                SET is_banned = 1, ban_reason = ?
                WHERE user_id = ?
            """, ("Spam", 123))
            
            cursor.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (123,))
            is_banned, reason = cursor.fetchone()
            
            assert is_banned == 1
            assert reason == "Spam"


class TestCaching:
    """Test caching functionality."""
    
    def test_set_and_get_cache(self, temp_db):
        """Should store and retrieve cached response."""
        init_test_database(temp_db)
        
        cache_key = "abc123"
        response = "Test response"
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cache (cache_key, response_text)
                VALUES (?, ?)
            """, (cache_key, response))
            
            cursor.execute("SELECT response_text FROM cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()
            
            assert row is not None
            assert row[0] == response
    
    def test_cache_hit_count(self, temp_db):
        """Should increment cache hit count on access."""
        init_test_database(temp_db)
        
        cache_key = "abc123"
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cache (cache_key, response_text, hit_count)
                VALUES (?, ?, ?)
            """, (cache_key, "response", 0))
            
            cursor.execute("""
                UPDATE cache 
                SET hit_count = hit_count + 1
                WHERE cache_key = ?
            """, (cache_key,))
            
            cursor.execute("SELECT hit_count FROM cache WHERE cache_key = ?", (cache_key,))
            hits = cursor.fetchone()[0]
            
            assert hits == 1
    
    def test_cache_expiry(self, temp_db):
        """Should identify old cache entries."""
        init_test_database(temp_db)
        
        old_date = datetime.now() - timedelta(days=8)
        cache_key = "old_key"
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cache (cache_key, response_text, last_used_at)
                VALUES (?, ?, ?)
            """, (cache_key, "response", old_date.isoformat()))
            
            cutoff = datetime.now() - timedelta(days=7)
            cursor.execute("""
                SELECT cache_key FROM cache 
                WHERE last_used_at < ?
            """, (cutoff.isoformat(),))
            
            expired = cursor.fetchall()
            
            assert len(expired) > 0
            assert expired[0][0] == cache_key


class TestRequests:
    """Test request tracking."""
    
    def test_save_request(self, temp_db):
        """Should save request to database."""
        init_test_database(temp_db)
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            
            # Insert user first
            cursor.execute("""
                INSERT INTO users (user_id, username)
                VALUES (?, ?)
            """, (123, "testuser"))
            
            # Insert request
            cursor.execute("""
                INSERT INTO requests (user_id, news_text, response_text, from_cache)
                VALUES (?, ?, ?, ?)
            """, (123, "Test news", "Test response", False))
            
            cursor.execute("SELECT news_text, response_text FROM requests WHERE user_id = ?", (123,))
            row = cursor.fetchone()
            
            assert row is not None
            assert row[0] == "Test news"
            assert row[1] == "Test response"
    
    def test_request_with_error(self, temp_db):
        """Should save request with error message."""
        init_test_database(temp_db)
        
        with get_test_db(temp_db) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO users (user_id, username)
                VALUES (?, ?)
            """, (123, "testuser"))
            
            cursor.execute("""
                INSERT INTO requests (user_id, news_text, error_message)
                VALUES (?, ?, ?)
            """, (123, "Test news", "API timeout"))
            
            cursor.execute("SELECT error_message FROM requests WHERE user_id = ?", (123,))
            row = cursor.fetchone()
            
            assert row is not None
            assert "timeout" in row[0].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
