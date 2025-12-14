"""
Bot Pydantic Schemas for type safety and validation.

This module defines all data models used throughout the bot application.
Following DRY principle: single source of truth for data structures.
"""

from .user_schema import UserSchema, UserStatsSchema, UserProgressSchema
from .lesson_schema import LessonSchema, QuizQuestionSchema, LessonProgressSchema
from .quest_schema import QuestSchema, QuestProgressSchema
from .message_schema import MessageSchema, AnalysisResponseSchema

__all__ = [
    "UserSchema",
    "UserStatsSchema",
    "UserProgressSchema",
    "LessonSchema",
    "QuizQuestionSchema",
    "LessonProgressSchema",
    "QuestSchema",
    "QuestProgressSchema",
    "MessageSchema",
    "AnalysisResponseSchema",
]
