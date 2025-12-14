"""
Lesson Service - управление курсами и уроками.

DRY Principle: Единственное место для операций с уроками.
SRP: Только логика уроков и курсов.
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("lesson_service")


class LessonService:
    """Service for lesson and course management."""
    
    def __init__(self, db_connection_pool=None):
        """Initialize lesson service."""
        self.db = db_connection_pool
    
    def get_user_course_progress(self, user_id: int) -> Dict[str, Any]:
        """Get user progress in all courses."""
        try:
            from bot import get_db
            from education import get_user_course_progress
            
            progress = get_user_course_progress(user_id)
            logger.info(f"✅ Retrieved course progress for user {user_id}")
            return progress
        except Exception as e:
            logger.error(f"❌ Error getting course progress for {user_id}: {e}")
            return {}
    
    def get_lesson_content(self, course_id: str, lesson_number: int) -> Optional[str]:
        """Get lesson content."""
        try:
            from bot import get_db
            from education import get_lesson_content
            
            content = get_lesson_content(course_id, lesson_number)
            logger.info(f"✅ Retrieved lesson {lesson_number} from course {course_id}")
            return content
        except Exception as e:
            logger.error(f"❌ Error getting lesson content: {e}")
            return None
    
    def get_next_lesson_info(self, user_id: int, course_id: str) -> Optional[Dict[str, Any]]:
        """Get next recommended lesson for user."""
        try:
            from bot import get_db
            from education import get_next_lesson_info
            
            info = get_next_lesson_info(user_id, course_id)
            logger.info(f"✅ Retrieved next lesson info for user {user_id}")
            return info
        except Exception as e:
            logger.error(f"❌ Error getting next lesson info: {e}")
            return None
    
    def extract_quiz(self, lesson_content: str) -> Optional[List[Dict[str, Any]]]:
        """Extract quiz from lesson content."""
        try:
            from bot import get_db
            from education import extract_quiz_from_lesson
            
            quiz = extract_quiz_from_lesson(lesson_content)
            logger.info(f"✅ Extracted quiz from lesson")
            return quiz
        except Exception as e:
            logger.error(f"❌ Error extracting quiz: {e}")
            return None
    
    def save_quiz_response(self, user_id: int, question: str, answer: str, is_correct: bool) -> bool:
        """Save user quiz response."""
        try:
            from bot import get_db
            from datetime import datetime
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_quiz_responses 
                    (user_id, question, answer, is_correct, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, question, answer, is_correct, datetime.now()))
                conn.commit()
                
                logger.info(f"✅ Saved quiz response for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving quiz response: {e}")
            return False
    
    def get_course_summary(self, user_id: int, course_id: str) -> Optional[str]:
        """Get course summary for user."""
        try:
            from bot import get_db
            from education import get_user_course_summary
            
            summary = get_user_course_summary(user_id, course_id)
            logger.info(f"✅ Retrieved course summary for user {user_id}")
            return summary
        except Exception as e:
            logger.error(f"❌ Error getting course summary: {e}")
            return None
