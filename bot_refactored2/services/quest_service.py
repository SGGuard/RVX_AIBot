"""
Quest Service - управление квестами.

DRY Principle: Единственное место для операций с квестами.
SRP: Только логика квестов.
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("quest_service")


class QuestService:
    """Service for quest management."""
    
    def __init__(self, db_connection_pool=None):
        """Initialize quest service."""
        self.db = db_connection_pool
    
    def get_daily_quests(self, user_id: int) -> List[Dict[str, Any]]:
        """Get daily quests for user based on level."""
        try:
            from bot import get_db
            from education import get_user_knowledge_level
            from daily_quests_v2 import get_user_level, get_daily_quests_for_level
            
            # Get user XP to determine level
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                user_xp = row[0] if row else 0
            
            quest_level = get_user_level(user_xp)
            quests = get_daily_quests_for_level(quest_level)
            
            logger.info(f"✅ Retrieved {len(quests)} daily quests for user {user_id} (level {quest_level})")
            return quests
        except Exception as e:
            logger.error(f"❌ Error getting daily quests for {user_id}: {e}")
            return []
    
    def start_quest(self, user_id: int, quest_id: str) -> bool:
        """Start a quest for user."""
        try:
            from bot import get_db
            from quest_handler_v2 import start_quest
            from datetime import datetime
            
            with get_db() as conn:
                cursor = conn.cursor()
                # Record quest start
                cursor.execute("""
                    INSERT OR REPLACE INTO user_quests 
                    (user_id, quest_id, started_at, status)
                    VALUES (?, ?, ?, ?)
                """, (user_id, quest_id, datetime.now(), 'in_progress'))
                conn.commit()
            
            logger.info(f"✅ User {user_id} started quest {quest_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error starting quest for user {user_id}: {e}")
            return False
    
    def complete_quest(self, user_id: int, quest_id: str, xp_reward: int = 100) -> bool:
        """Mark quest as completed."""
        try:
            from bot import get_db
            from datetime import datetime
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_quests 
                    SET status = ?, completed_at = ?
                    WHERE user_id = ? AND quest_id = ?
                """, ('completed', datetime.now(), user_id, quest_id))
                
                # Award XP
                cursor.execute("""
                    UPDATE users 
                    SET xp = xp + ?
                    WHERE user_id = ?
                """, (xp_reward, user_id))
                
                conn.commit()
            
            logger.info(f"✅ User {user_id} completed quest {quest_id} (+{xp_reward} XP)")
            return True
        except Exception as e:
            logger.error(f"❌ Error completing quest for user {user_id}: {e}")
            return False
    
    def get_completed_quests_today(self, user_id: int) -> List[str]:
        """Get list of quests completed today by user."""
        try:
            from bot import get_db
            from datetime import datetime, timedelta
            
            today = datetime.now().date()
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT quest_id FROM user_quests 
                    WHERE user_id = ? 
                    AND status = 'completed'
                    AND DATE(completed_at) = ?
                """, (user_id, today))
                
                rows = cursor.fetchall()
                completed = [row[0] for row in rows]
                
                logger.info(f"✅ User {user_id} completed {len(completed)} quests today")
                return completed
        except Exception as e:
            logger.error(f"❌ Error getting completed quests for {user_id}: {e}")
            return []
    
    def get_daily_xp_earned(self, user_id: int) -> int:
        """Get total XP earned from quests today."""
        try:
            from bot import get_db
            from datetime import datetime
            
            today = datetime.now().date()
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COALESCE(SUM(100), 0) FROM user_quests 
                    WHERE user_id = ? 
                    AND status = 'completed'
                    AND DATE(completed_at) = ?
                """, (user_id, today))
                
                row = cursor.fetchone()
                xp_earned = row[0] if row else 0
                
                logger.info(f"✅ User {user_id} earned {xp_earned} XP from quests today")
                return xp_earned
        except Exception as e:
            logger.error(f"❌ Error getting daily XP earned for {user_id}: {e}")
            return 0
