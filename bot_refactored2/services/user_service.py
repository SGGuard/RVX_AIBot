"""
User Service - управление данными пользователя.

DRY Principle: Единственное место для операций с пользователями.
SRP: Только операции связанные с пользователем.
"""

import logging
import sqlite3
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger("user_service")


class UserService:
    """Service for user data management."""
    
    def __init__(self, db_connection_pool=None):
        """
        Initialize user service.
        
        Args:
            db_connection_pool: Optional database connection pool
        """
        self.db = db_connection_pool
    
    def create_or_update_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        """
        Create or update user in database.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User first name
            
        Returns:
            True if successful
        """
        try:
            from bot import get_db
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO users (user_id, username, first_name, created_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, username, first_name, datetime.now()))
                
                cursor.execute("""
                    UPDATE users 
                    SET username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name)
                    WHERE user_id = ?
                """, (username or None, first_name or None, user_id))
                
                conn.commit()
                logger.info(f"✅ User {user_id} created/updated")
                return True
        except Exception as e:
            logger.error(f"❌ Error creating/updating user {user_id}: {e}")
            return False
    
    def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user statistics."""
        try:
            from bot import get_db
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT xp, level, (
                        SELECT COUNT(*) FROM user_progress WHERE user_id = ?
                    ), (
                        SELECT COUNT(*) FROM user_quiz_responses WHERE user_id = ?
                    ), (
                        SELECT COUNT(DISTINCT badge_id) FROM user_badges WHERE user_id = ?
                    ), created_at
                    FROM users WHERE user_id = ?
                """, (user_id, user_id, user_id, user_id))
                
                row = cursor.fetchone()
                if row:
                    xp, level, courses, tests, badges, created_at = row
                    return {
                        "user_id": user_id,
                        "xp": xp or 0,
                        "level": level or 1,
                        "courses_completed": courses or 0,
                        "tests_passed": tests or 0,
                        "badges_count": badges or 0,
                        "created_at": created_at
                    }
        except Exception as e:
            logger.error(f"❌ Error getting user stats {user_id}: {e}")
        
        return None
    
    def is_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user is banned and get reason."""
        try:
            from bot import get_db
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT is_banned, ban_reason FROM users WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if row:
                    is_banned, reason = row
                    return bool(is_banned), reason
        except Exception as e:
            logger.error(f"❌ Error checking ban status for {user_id}: {e}")
        
        return False, None
    
    def add_xp(self, user_id: int, xp_amount: int) -> bool:
        """Add XP to user."""
        try:
            from bot import get_db
            from education import calculate_user_level_and_xp, add_xp_to_user
            
            add_xp_to_user(user_id, xp_amount)
            logger.info(f"✅ Added {xp_amount} XP to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error adding XP to user {user_id}: {e}")
            return False
    
    def check_daily_limit(self, user_id: int, max_requests: int = 50) -> Tuple[bool, int]:
        """
        Check if user has remaining daily requests.
        
        Returns:
            Tuple of (can_request, remaining_requests)
        """
        try:
            from bot import get_db
            from education import check_daily_limit, get_remaining_requests
            
            can_request = check_daily_limit(user_id)
            remaining = get_remaining_requests(user_id)
            
            return can_request, remaining
        except Exception as e:
            logger.error(f"❌ Error checking daily limit for {user_id}: {e}")
            return True, max_requests  # Fail open
    
    def increment_request_counter(self, user_id: int) -> bool:
        """Increment daily request counter."""
        try:
            from bot import get_db
            from education import increment_daily_requests
            
            increment_daily_requests(user_id)
            logger.info(f"✅ Incremented request counter for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error incrementing request counter for {user_id}: {e}")
            return False
