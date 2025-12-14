"""
Bot Refactored Package - Phase 2 SPRINT 4 Refactoring.

This package contains the fully refactored bot application with SOLID principles:
- Single Responsibility: Each module has one reason to change
- Open/Closed: Easy to extend with new handlers/services
- Liskov Substitution: Interfaces for extensibility
- Interface Segregation: Minimal dependencies
- Dependency Inversion: Services depend on abstractions

Structure:
├── handlers/          # Command, message, button handlers (SRP)
├── services/         # Business logic services (SRP)
├── schemas/          # Pydantic data models (DRY - single source of truth)
├── core.py          # Bot initialization and orchestration
└── __init__.py      # Package exports
"""

from .core import BotCore, get_bot_core, main
from .handlers import CommandHandler, MessageHandler, ButtonHandler
from .services import APIClientService, UserService, LessonService, QuestService
from .schemas import (
    UserSchema, UserStatsSchema, UserProgressSchema,
    LessonSchema, QuizQuestionSchema, LessonProgressSchema,
    QuestSchema, QuestProgressSchema,
    MessageSchema, AnalysisResponseSchema
)

__version__ = "0.1.0"
__all__ = [
    # Core
    "BotCore",
    "get_bot_core",
    "main",
    # Handlers
    "CommandHandler",
    "MessageHandler",
    "ButtonHandler",
    # Services
    "APIClientService",
    "UserService",
    "LessonService",
    "QuestService",
    # Schemas
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
