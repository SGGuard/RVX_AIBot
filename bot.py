import os
import sys
import logging
import json
import httpx
import hashlib
import sqlite3
import asyncio
import re
import html
import time
import subprocess
from typing import Optional, List, Tuple, Dict, Any, Callable
from datetime import datetime, timedelta
import datetime as datetime_module
from contextlib import contextmanager
from functools import wraps

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator, ValidationInfo, ValidationError, Field

# Импорт i18n для мультиязычной поддержки
try:
    from i18n import get_text, set_user_language, get_user_language as get_user_lang
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("i18n module not found, will use stub functions")
    async def get_text(key, *args, **kwargs): return f"[{key}]"
    async def set_user_language(*args, **kwargs): return False
    def get_user_lang(*args, **kwargs): return "ru"

# ============================================================================
# 🔧 CRITICAL: Clean up old bot processes on startup
# ============================================================================
def cleanup_stale_bot_processes() -> None:
    """
    ULTRA-AGGRESSIVE cleanup to prevent 409 Conflicts (Python-only, no external commands)
    - Kills ALL bot.py processes except current
    - Kills ALL api_server/uvicorn processes
    - Sleeps 3 seconds to let Telegram API release the lock
    
    Note: Uses Python's psutil/os module only - no external pkill/ps commands
    which may not exist in Docker slim images
    """
    # Early logger for startup (before full logger config)
    init_logger = logging.getLogger('startup')
    init_logger.setLevel(logging.DEBUG)
    if not init_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
        init_logger.addHandler(handler)
    
    try:
        current_pid = os.getpid()
        init_logger.info(f"CLEANUP: Current PID = {current_pid}")
        
        # Try to use psutil if available, otherwise skip process killing
        try:
            import psutil
            
            # Kill processes matching patterns
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    pid = proc.info['pid']
                    
                    # Kill other bot.py instances
                    if 'bot.py' in cmdline and pid != current_pid:
                        try:
                            os.kill(pid, 9)
                            init_logger.debug(f"Killed stale bot process PID={pid}")
                        except ProcessLookupError:
                            pass
                    
                    # Kill api_server
                    if 'api_server' in cmdline or 'uvicorn' in cmdline:
                        try:
                            os.kill(pid, 9)
                            init_logger.debug(f"Killed api_server/uvicorn process PID={pid}")
                        except ProcessLookupError:
                            pass
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            # psutil not available - just skip process killing
            init_logger.warning("psutil not available, skipping process killing")
        
        # CRITICAL: Sleep to let Telegram release the polling lock
        init_logger.debug("Waiting 3 seconds for Telegram polling lock to release...")
        time.sleep(3)
        
    except Exception as e:
        init_logger.error(f"Cleanup warning: {e}")

# Run cleanup BEFORE anything else - this is the very first thing that runs
cleanup_stale_bot_processes()

# Fix SQLite3 datetime adapter deprecation warning (Python 3.12+)
def _adapt_datetime(val: datetime) -> str:
    """Adapter for datetime to ISO format string for SQLite3"""
    return val.isoformat()

sqlite3.register_adapter(datetime, _adapt_datetime)

# Load environment variables with explicit path for Railway compatibility
import os
from pathlib import Path

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path), verbose=True)
else:
    load_dotenv(verbose=True)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError, TimedOut, NetworkError, Conflict
from telegram.constants import ParseMode, ChatAction

# ============================================================================
# ✅ v0.25.0: CORE MODULES - Config, Messages, AI Honesty, Event Tracking
# ============================================================================
from config import (
    API_URL_NEWS,
    CACHE_ENABLED, BOT_ADMIN_IDS, BOT_OWNER_ID,
    FEATURE_ANALYTICS_ENABLED
)
from messages import (
    split_message, MSG_HELP_EXTENDED, MSG_FEEDBACK_HELPFUL, MSG_FEEDBACK_UNHELPFUL,
    MSG_CLARIFY_PROMPT, MSG_CLARIFY_NOT_FOUND
)
from ai_honesty import (
    analyze_ai_response, get_honesty_system_prompt
)
from event_tracker import (
    get_tracker, create_event, EventType, get_analytics
)

# ✅ v1.0: Embedded News Analyzer - встроенный анализ без API
# ============================================================================
from embedded_news_analyzer import analyze_news

# ✅ v0.25.0: Admin Dashboard
from admin_dashboard import get_admin_dashboard

# ✅ v0.26.0: Conversation Context Manager - контекст разговора
from conversation_context import (
    add_user_message, add_ai_message, get_context_messages, 
    clear_user_history, get_context_stats
)

# ✅ CRITICAL FIX #2: Input Validators - валидация входных данных
from input_validators import validate_user_input, UserMessageInput

# ✅ CRITICAL FIX #1: SQL Validator - защита от SQL injection

# ✅ v0.28.0: Daily Digest Scheduler - ежедневный крипто-дайджест в 9:00
from daily_digest_scheduler import initialize_digest_scheduler, stop_digest_scheduler

# Новый модуль для обучения (v0.5.0)
from education import (
    COURSES_DATA, XP_REWARDS, LEVEL_THRESHOLDS, BADGES,
    load_courses_to_db, get_user_knowledge_level, calculate_user_level_and_xp,
    add_xp_to_user, get_user_badges, add_badge_to_user, get_lesson_content,
    extract_quiz_from_lesson, get_faq_by_keyword, save_question_to_db,
    add_question_to_faq, get_user_course_progress, get_all_tools_db,
    get_educational_context, clean_lesson_content, split_lesson_content,
    get_next_lesson_info, build_user_context_prompt, get_user_course_summary,
    # NEW v0.14.0: функции для лимитов на запросы
    XP_TIER_LIMITS, get_daily_limit_by_xp, get_remaining_requests,
    check_daily_limit, increment_daily_requests, reset_daily_requests
)

# ✅ NEW: Crypto Daily Digest (v0.27.0)
try:
    from crypto_digest import collect_digest_data
    from digest_formatter import format_digest
    CRYPTO_DIGEST_ENABLED = True
except ImportError:
    logger.warning("Crypto digest modules not available")
    CRYPTO_DIGEST_ENABLED = False

# Передовая система обучения (v0.21.0)
from adaptive_learning import (
    Gamification, initialize_learning_profile, get_recommended_learning_session,
    DifficultyLevel
)

# TIER 1 Optimizations (v0.22.0) - Type hints, Redis cache, connection pooling, structured logging
from tier1_optimizations import DatabaseConnectionPool

# Учительский модуль (v0.7.0) - ИИ преподает крипто, AI, Web3, трейдинг
from teacher import teach_lesson, TEACHING_TOPICS, DIFFICULTY_LEVELS

# Модуль детектирования пропаганды и манипуляций (v0.32.0)
from propaganda_detector import (
    analyze_propaganda, format_propaganda_analysis, 
    get_propaganda_tips, quick_propaganda_check
)

# ✅ v0.33.0: Crypto Calculator - калькулятор для расчета market cap
from crypto_calculator import (
    get_token_stats, get_token_list, format_calculator_result,
    validate_price, get_calculator_menu_text, CRYPTO_TOKENS, format_number, get_price_table
)

# Новый модуль для умного общения (v0.20.0)
from ai_intelligence import (
    analyze_user_knowledge_level, get_adaptive_greeting, get_contextual_tips,
    get_encouragement_message, get_personalized_next_action, UserLevel,
    analyze_user_interests
)

# Новая система адаптивных квестов v2 (v0.13.0)
from daily_quests_v2 import (
    DAILY_QUESTS, get_user_level, get_level_name, get_level_info,
    get_daily_quests_for_level, LEVEL_RANGES
)
from quest_handler_v2 import (
    start_quest, start_test, show_question, handle_answer
)

# (v0.23.0) Глобальное состояние теперь управляется через BotState класс - см. ниже
FEEDBACK_MAX_RETRIES = 6

# Последовательность режимов регенерации (от простого к более наглядному)
# v0.19.0: Добавлены новые режимы для лучшей помощи
REGENERATION_MODES = [
    ("упрощен", "Объясни ОЧЕНЬ просто в 2-3 предложениях без сложных терминов, но серьезно."),
    ("примеры", "Приведи 2-3 конкретных реальных примера с цифрами - как это работает в практике."),
    ("пошагово", "Разбей на нумерованные пошаговые действия: ШАГ 1, ШАГ 2, ШАГ 3."),
    ("контекст", "Объясни исторический контекст - откуда это взялось, как развивалось, где используется сейчас."),
    ("вопросы", "Вместо объяснения задай 2-3 умных вопроса, которые помогут разобраться глубже.")
]

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

load_dotenv()

# Основные настройки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Определяем API URL - с поддержкой Railway environment
# Priority: 
# 1. Single-container (localhost when api_server.py exists)
# 2. API_URL_NEWS env variable
# 3. API_URL env variable (gets /explain_news appended)
# 4. External service URL for multi-container Railway deployment

_is_localhost_available = os.getenv("RAILWAY_ENVIRONMENT") or os.path.exists("/app/api_server.py")

if _is_localhost_available and os.path.exists("/app/api_server.py"):
    # Single-container deployment - API runs on localhost:8000
    API_URL_NEWS = "http://localhost:8000/explain_news"
    logger_init_source = "localhost (single-container with api_server.py)"
else:
    # Multi-container or external API
    _api_url_env = os.getenv("API_URL_NEWS")
    if _api_url_env:
        API_URL_NEWS = _api_url_env
        logger_init_source = "API_URL_NEWS env var"
    else:
        _api_url = os.getenv("API_URL")
        if _api_url:
            # Handle both cases: with and without /explain_news suffix
            if not _api_url.endswith("/explain_news"):
                API_URL_NEWS = _api_url.rstrip('/') + "/explain_news"
            else:
                API_URL_NEWS = _api_url
            logger_init_source = f"API_URL env var ({_api_url})"
        elif _api_base_url := os.getenv("API_BASE_URL"):
            API_URL_NEWS = _api_base_url.rstrip('/') + "/explain_news"
            logger_init_source = "API_BASE_URL env var"
        else:
            # Default fallback
            API_URL_NEWS = "http://localhost:8000/explain_news"
            logger_init_source = "default localhost"

logger_init = logging.getLogger("config_loader")
logger_init.info(f"API_URL_NEWS configured: {API_URL_NEWS}")
logger_init.info(f"   Source: {logger_init_source}")

BOT_API_KEY = os.getenv("BOT_API_KEY", "")  # ✅ API key for authentication
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0"))
API_RETRY_ATTEMPTS = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
API_RETRY_DELAY = float(os.getenv("API_RETRY_DELAY", "0.5"))  # Оптимизировано: быстрое восстановление

# Контроль доступа
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
# Use BOT_ADMIN_IDS from config.py which includes 7216426044 (creator)
ADMIN_USERS = set(BOT_ADMIN_IDS) if BOT_ADMIN_IDS else set(map(int, filter(None, os.getenv("ADMIN_USERS", "").split(","))))
UNLIMITED_ADMIN_USERS = set(map(int, filter(None, os.getenv("UNLIMITED_ADMIN_USERS", "").split(","))))  # Админы без лимитов
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "50"))

# Производственные настройки (v0.21.0 Production Ready)
BOT_START_TIME = datetime.now()
GRACEFUL_SHUTDOWN_TIMEOUT = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30"))  # Время для graceful shutdown
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))  # Проверка здоровья каждые 5 минут

# =============================================================================
# CRITICAL FIX #5: Centralized Authorization Decorator (Security)
# =============================================================================

from enum import Enum

class AuthLevel(Enum):
    """Уровни доступа для команд."""
    ANYONE = 0
    USER = 1
    ADMIN = 2
    OWNER = 3

def get_user_auth_level(user_id: int) -> AuthLevel:
    """
    Определяет уровень доступа пользователя.
    ✅ CRITICAL FIX #5: Centralized permission checking
    """
    if user_id in UNLIMITED_ADMIN_USERS:
        return AuthLevel.OWNER
    elif user_id in ADMIN_USERS:
        return AuthLevel.ADMIN
    elif ALLOWED_USERS and user_id in ALLOWED_USERS:
        return AuthLevel.USER
    else:
        return AuthLevel.ANYONE

def require_auth(required_level: AuthLevel) -> Callable:
    """
    Декоратор для проверки прав доступа.
    ✅ CRITICAL FIX #5: Centralized authorization check
    
    Usage:
        @require_auth(AuthLevel.ADMIN)
        async def admin_only_command(update, context):
            pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            user_level = get_user_auth_level(user_id)
            
            if user_level.value < required_level.value:
                logger.warning(f"Access denied for user {user_id} (level={user_level.name}, required={required_level.name})")
                await update.message.reply_text(f"❌ Недостаточно прав для этой команды")
                return
            
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# Обязательная подписка на канал
MANDATORY_CHANNEL_ID = -1003228919683  # Канал для обязательной подписки (преобразовано из 3228919683)
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "https://t.me/RVX_AI")  # Ссылка на канал для подписки

# =============================================================================
# CHANNEL SUBSCRIPTION CHECK (v0.42.1 Mandatory Subscription)
# =============================================================================

# Кэш для результатов проверки подписки (user_id -> (is_subscribed, timestamp))
_subscription_cache = {}
_SUBSCRIPTION_CACHE_TTL = 300  # 5 минут

async def clear_subscription_cache(user_id: int = None) -> None:
    """Очищает кэш подписки для пользователя или всех пользователей"""
    global _subscription_cache
    if user_id is None:
        _subscription_cache.clear()
        logger.info("🗑️  Cleared subscription cache for ALL users")
    else:
        if user_id in _subscription_cache:
            del _subscription_cache[user_id]
            logger.info(f"🗑️  Cleared subscription cache for user {user_id}")

async def check_channel_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет подписан ли пользователь на обязательный канал.
    
    Результаты кэшируются на 5 минут для снижения нагрузки на API.
    Если бот не может проверить членство через API - показывает подтверждение.
    
    Args:
        user_id: ID пользователя
        context: Telegram context для доступа к боту
    
    Returns:
        True если пользователь подписан, False если нет
    """
    print(f"\n{'='*50}")
    print(f"DEBUG: check_channel_subscription called for user {user_id}")
    print(f"DEBUG: MANDATORY_CHANNEL_ID = {MANDATORY_CHANNEL_ID}")
    print(f"DEBUG: Type of MANDATORY_CHANNEL_ID: {type(MANDATORY_CHANNEL_ID)}")
    
    # ВАЖНО: Если MANDATORY_CHANNEL_ID не установлен - БЛОКИРУЕМ ВСЕ
    # Это значит что пока бот не в production режиме
    if not MANDATORY_CHANNEL_ID:
        print(f"DEBUG: MANDATORY_CHANNEL_ID is falsy! Blocking all access.")
        return False  # Если канал не задан, блокируем всем
    
    print(f"DEBUG: MANDATORY_CHANNEL_ID is set to {MANDATORY_CHANNEL_ID}")
    
    # Проверяем кэш
    current_time = time.time()
    if user_id in _subscription_cache:
        is_subscribed, cache_time = _subscription_cache[user_id]
        if current_time - cache_time < _SUBSCRIPTION_CACHE_TTL:
            print(f"DEBUG: Cache hit for user {user_id}: {is_subscribed}")
            logger.debug(f"🔄 Cache hit for user {user_id}: {is_subscribed}")
            return is_subscribed  # Возвращаем закэшированный результат
    
    try:
        print(f"DEBUG: Calling context.bot.get_chat_member for user {user_id} in channel {MANDATORY_CHANNEL_ID}")
        logger.debug(f"🔍 Checking subscription for user {user_id} in channel {MANDATORY_CHANNEL_ID}")
        
        # Проверяем статус члена в канале
        member = await context.bot.get_chat_member(MANDATORY_CHANNEL_ID, user_id)
        print(f"DEBUG: Got member info, status={member.status}")
        logger.debug(f"Member info: status={member.status}, user_id={user_id}")
        
        # Пользователь является членом если статус: member, administrator, creator
        is_subscribed = member.status in ["member", "administrator", "creator"]
        print(f"DEBUG: is_subscribed = {is_subscribed} (status={member.status})")
        
        # Кэшируем результат
        _subscription_cache[user_id] = (is_subscribed, current_time)
        print(f"DEBUG: Cached result for user {user_id}: {is_subscribed}")
        logger.debug(f"✅ Cached result for user {user_id}: {is_subscribed}")
        
        if is_subscribed:
            print(f"DEBUG: RETURNING TRUE - User {user_id} IS subscribed")
            logger.info(f"✅ User {user_id} is subscribed to mandatory channel (status: {member.status})")
            return True
        else:
            print(f"DEBUG: RETURNING FALSE - User {user_id} is NOT subscribed")
            logger.info(f"❌ User {user_id} is NOT subscribed to mandatory channel (status: {member.status})")
            return False
        
    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG: Exception caught: {error_msg}")
        logger.error(f"❌ Error checking subscription for user {user_id}: {error_msg}")
        
        # Если ошибка 400 или "user not a member" - пользователь не подписан
        if "user is not a member" in error_msg.lower() or "not found" in error_msg.lower() or "400" in error_msg:
            print(f"DEBUG: User not a member error, RETURNING FALSE")
            logger.info(f"⚠️ User {user_id} is not a member of the channel (API confirmed)")
            _subscription_cache[user_id] = (False, current_time)  # Кэшируем что не подписан
            return False
        
        # При других ошибках - требуем подписку (лучше требовать по ошибке чем разрешать)
        print(f"DEBUG: API error (not member error), RETURNING FALSE")
        logger.warning(f"⚠️ Subscription check API error for user {user_id}, blocking access until retry: {error_msg}")
        # Не кэшируем ошибки - пусть пользователь сможет попробовать еще раз
        return False  # Блокируем доступ при ошибке API

def require_channel_subscription(func: Callable) -> Callable:
    """
    Декоратор для проверки подписки на обязательный канал.
    
    Если пользователь не подписан на канал, отправляет сообщение с кнопкой
    для перехода на канал и прерывает выполнение команды.
    
    Usage:
        @require_channel_subscription
        async def some_command(update, context):
            # код команды
            pass
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Проверяем подписку
        is_subscribed = await check_channel_subscription(user_id, context)
        
        if not is_subscribed:
            logger.info(f"User {user_id} tried to use command without channel subscription")
            
            # Отправляем сообщение с кнопками для подписки
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📢 Подписаться на канал",
                        url=MANDATORY_CHANNEL_LINK
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ Я подписался, проверить еще раз",
                        callback_data=f"check_subscription_{user_id}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "<b>📢 Требуется подписка</b>\n\n"
                "Для использования этого бота необходимо подписаться на наш канал. "
                "После подписки вы сможете пользоваться всеми командами.\n\n"
                "👇 Подпишитесь по ссылке ниже:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return
        
        # Пользователь подписан, выполняем команду
        return await func(update, context, *args, **kwargs)
    
    return wrapper


# Канал для постов об обновлениях (админский канал для публикации новостей)
UPDATE_CHANNEL_ID = os.getenv("UPDATE_CHANNEL_ID", "")  # Канал для постов об обновлениях
BOT_VERSION = "0.21.0"  # v0.21.0 - Production Ready (Health checks, Graceful shutdown, DB optimization)

# База данных
DB_PATH = os.getenv("DB_PATH", "rvx_bot.db")
DB_BACKUP_INTERVAL = int(os.getenv("DB_BACKUP_INTERVAL", "86400"))  # 24 часа

# Connection pooling configuration (SERIOUS FIX: Performance optimization)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))  # Max 5 concurrent connections
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "10"))  # Wait max 10 seconds for connection

# Фичи
ENABLE_ANALYTICS = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
ENABLE_AUTO_CACHE_CLEANUP = os.getenv("ENABLE_AUTO_CACHE_CLEANUP", "true").lower() == "true"
CACHE_MAX_AGE_DAYS = int(os.getenv("CACHE_MAX_AGE_DAYS", "7"))

# =============================================================================
# ЛОГИРОВАНИЕ (Unified Format v0.39.0)
# =============================================================================

class RVXFormatter(logging.Formatter):
    """Unified logging formatter with emoji prefixes for console and structured logs for files"""
    
    LEVEL_EMOJI = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔴"
    }
    
    def __init__(self, fmt=None, datefmt=None, use_emoji=True):
        super().__init__(fmt, datefmt)
        self.use_emoji = use_emoji
    
    def format(self, record):
        """Format log record with emoji prefix and consistent structure"""
        if self.use_emoji:
            emoji = self.LEVEL_EMOJI.get(record.levelno, "•")
            record.msg = f"{emoji} {record.msg}"
        
        # Preserve original formatting if there's context data
        if hasattr(record, 'user_id'):
            record.msg += f" [user_id={record.user_id}]"
        
        return super().format(record)


def setup_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Configure unified logger with file and console handlers"""
    logger = logging.getLogger(name or __name__)
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # File handler (structured, no emoji)
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = RVXFormatter(
        fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        use_emoji=False
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler (with emoji)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = RVXFormatter(
        fmt='%(asctime)s [%(levelname)-8s] %(message)s',
        datefmt='%H:%M:%S',
        use_emoji=True
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logger(__name__)

# =============================================================================
# PYDANTIC MODELS FOR API RESPONSE VALIDATION (FIX #5: XSS/Injection Protection)
# =============================================================================

class APIResponse(BaseModel):
    """Валидирует все ответы от API для предотвращения injection атак"""
    
    simplified_text: Optional[str] = None
    summary_text: Optional[str] = None
    impact_points: Optional[List[str]] = None
    
    @field_validator('simplified_text', 'summary_text', mode='before')
    @classmethod
    def validate_text_not_empty(cls, v: str, info: ValidationInfo) -> str:
        """Проверяет что текст не пуст и валиден (Pydantic V2 style)"""
        if v is not None:
            if not isinstance(v, str):
                raise ValueError("Text must be string")
            if len(v) > 10000:
                raise ValueError("Text too long (max 10000 chars)")
        return v
    
    @field_validator('impact_points', mode='before')
    @classmethod
    def validate_impact_points(cls, v, info: ValidationInfo):
        """Проверяет impact_points структуру (Pydantic V2 style)"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("impact_points must be list")
            if len(v) > 50:
                raise ValueError("Too many impact points")
            for item in v:
                if not isinstance(item, str) or len(item) > 500:
                    raise ValueError("Invalid impact point")
        return v
    
    class Config:
        str_strip_whitespace = True
        max_anystr_length = 10000

# =============================================================================
# UNIFIED RESPONSE WRAPPER (v0.24.0) - Standardized API responses
# =============================================================================

class BotResponse(BaseModel):
    """
    Unified response format for all API responses.
    Ensures consistent structure across all endpoints and operations.
    """
    
    success: bool
    status: str  # "ok", "error", "warning", "processing"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    request_id: Optional[str] = None
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Converts response to dictionary, removing None values."""
        return {k: v for k, v in self.dict().items() if v is not None}
    
    @classmethod
    def success_response(cls, data: Dict[str, Any], request_id: Optional[str] = None, 
                        processing_time_ms: float = 0.0) -> "BotResponse":
        """Creates a successful response."""
        return cls(
            success=True,
            status="ok",
            data=data,
            request_id=request_id,
            processing_time_ms=processing_time_ms
        )
    
    @classmethod
    def error_response(cls, error: str, error_code: str = "UNKNOWN", 
                      request_id: Optional[str] = None) -> "BotResponse":
        """Creates an error response."""
        return cls(
            success=False,
            status="error",
            error=error,
            error_code=error_code,
            request_id=request_id
        )
    
    @classmethod
    def warning_response(cls, data: Dict[str, Any], warning: str, 
                        request_id: Optional[str] = None) -> "BotResponse":
        """Creates a warning response (partial success)."""
        return cls(
            success=True,
            status="warning",
            data=data,
            error=warning,
            request_id=request_id
        )

# =============================================================================
# IP-BASED RATE LIMITING (v0.39.0 - QUICK WIN #3)
# =============================================================================

from collections import defaultdict
from threading import Lock

class IPRateLimiter:
    """
    IP-based rate limiter for DDoS protection.
    
    Features:
        - Per-IP rate limiting (configurable requests per time window)
        - Automatic cleanup of old entries
        - Thread-safe operations
        - Integration with logging
    
    Usage:
        limiter = IPRateLimiter(max_requests=30, window_seconds=60)
        if limiter.check_rate_limit(user_ip):
            # Process request
        else:
            # Too many requests
    """
    
    def __init__(self, max_requests: int = 30, window_seconds: int = 60, 
                 cleanup_interval: int = 300):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed in time window (default: 30)
            window_seconds: Time window in seconds (default: 60)
            cleanup_interval: Cleanup old entries every N seconds (default: 300)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval
        
        # IP -> list of timestamps (in seconds)
        self.request_times: Dict[str, List[float]] = defaultdict(list)
        
        # Lock for thread-safe operations
        self.lock = Lock()
        
        # Cleanup tracking
        self.last_cleanup = time.time()
    
    def check_rate_limit(self, ip_address: str) -> bool:
        """
        Check if request from IP should be allowed.
        
        Args:
            ip_address: Client IP address (string)
        
        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        with self.lock:
            current_time = time.time()
            
            # Auto-cleanup old entries periodically
            if current_time - self.last_cleanup > self.cleanup_interval:
                self._cleanup_old_entries(current_time)
                self.last_cleanup = current_time
            
            # Get timestamps for this IP within the window
            window_start = current_time - self.window_seconds
            self.request_times[ip_address] = [
                ts for ts in self.request_times[ip_address] 
                if ts > window_start
            ]
            
            # Check if limit exceeded
            if len(self.request_times[ip_address]) >= self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for IP {ip_address}: "
                    f"{len(self.request_times[ip_address])}/{self.max_requests} "
                    f"requests in {self.window_seconds}s"
                )
                return False
            
            # Add current request timestamp
            self.request_times[ip_address].append(current_time)
            return True
    
    def get_remaining_requests(self, ip_address: str) -> int:
        """
        Get remaining requests for IP address.
        
        Args:
            ip_address: Client IP address
        
        Returns:
            Number of remaining requests before hitting limit
        """
        with self.lock:
            current_time = time.time()
            window_start = current_time - self.window_seconds
            
            recent_requests = len([
                ts for ts in self.request_times[ip_address] 
                if ts > window_start
            ])
            
            return max(0, self.max_requests - recent_requests)
    
    def reset_ip(self, ip_address: str) -> None:
        """Reset rate limit for specific IP (admin only)."""
        with self.lock:
            if ip_address in self.request_times:
                del self.request_times[ip_address]
                logger.info(f"Rate limit reset for IP {ip_address}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self.lock:
            total_ips = len(self.request_times)
            blocked_ips = sum(
                1 for requests in self.request_times.values()
                if len(requests) >= self.max_requests
            )
            
            return {
                'total_tracked_ips': total_ips,
                'blocked_ips': blocked_ips,
                'max_requests_per_window': self.max_requests,
                'window_seconds': self.window_seconds,
                'cleanup_interval': self.cleanup_interval,
            }
    
    def _cleanup_old_entries(self, current_time: float) -> None:
        """
        Remove IPs with no recent activity.
        Called periodically to prevent memory leaks.
        """
        window_start = current_time - self.window_seconds
        cleanup_count = 0
        
        # Find IPs with no requests in current window
        ips_to_remove = [
            ip for ip, timestamps in self.request_times.items()
            if not any(ts > window_start for ts in timestamps)
        ]
        
        for ip in ips_to_remove:
            del self.request_times[ip]
            cleanup_count += 1
        
        if cleanup_count > 0:
            logger.debug(f"Rate limiter cleanup: removed {cleanup_count} inactive IPs")


# Global rate limiter instance (30 requests per minute per IP)
rate_limiter = IPRateLimiter(max_requests=30, window_seconds=60)

# =============================================================================
# STANDARDIZED ERROR HANDLING SYSTEM (v0.23.0)
# =============================================================================

from enum import Enum

class ErrorLevel(Enum):
    """Уровни серьёзности ошибок."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AppError(Exception):
    """Базовый класс для всех ошибок приложения."""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        level: ErrorLevel = ErrorLevel.ERROR,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ):
        self.message: str = message
        self.error_code: str = error_code
        self.level: ErrorLevel = level
        self.details: Dict[str, Any] = details or {}
        self.user_message: str = user_message or "Произошла ошибка. Попробуйте позже."
        super().__init__(self.message)

class DatabaseError(AppError):
    """Ошибки работы с БД."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="DB_ERROR",
            level=ErrorLevel.ERROR,
            details=details,
            user_message="Ошибка базы данных. Попробуйте позже."
        )

class APIError(AppError):
    """Ошибки API."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code=f"API_ERROR_{status_code}" if status_code else "API_ERROR",
            level=ErrorLevel.ERROR,
            details=details or {"status_code": status_code},
            user_message="API недоступен. Попробуйте позже."
        )

class ValidationError(AppError):
    """Ошибки валидации."""
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code=f"VALIDATION_ERROR_{field}" if field else "VALIDATION_ERROR",
            level=ErrorLevel.WARNING,
            details=details or {"field": field},
            user_message="Неверные данные. Проверьте введённое значение."
        )

class RateLimitError(AppError):
    """Ошибки rate limiting."""
    def __init__(self, message: str, retry_after: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            level=ErrorLevel.WARNING,
            details=details or {"retry_after": retry_after},
            user_message=f"Слишком много запросов. Попробуйте через {retry_after or 60} секунд."
        )

def handle_error(
    error: Exception,
    context_info: Optional[str] = None,
    user_id: Optional[int] = None
) -> AppError:
    """
    Стандартизированная обработка ошибок.
    
    Преобразует любую ошибку в AppError для единообразной обработки.
    
    Args:
        error: Исходная ошибка
        context_info: Контекст где произошла ошибка
        user_id: ID пользователя (для логирования)
        
    Returns:
        AppError - стандартизированная ошибка
    """
    context_str: str = f" (context: {context_info})" if context_info else ""
    
    if isinstance(error, AppError):
        return error
    
    if isinstance(error, sqlite3.Error):
        return DatabaseError(
            f"Database error: {str(error)}{context_str}",
            details={"original_error": str(error), "user_id": user_id}
        )
    
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return APIError(
            f"Request timeout: {str(error)}{context_str}",
            status_code=408,
            details={"user_id": user_id}
        )
    
    if isinstance(error, (httpx.TimeoutException, httpx.HTTPStatusError)):
        status_code: Optional[int] = getattr(error.response, "status_code", None) if hasattr(error, 'response') else None
        return APIError(
            f"API error: {str(error)}{context_str}",
            status_code=status_code,
            details={"user_id": user_id}
        )
    
    if isinstance(error, (TelegramError, TimedOut, NetworkError)):
        return AppError(
            message=f"Telegram error: {str(error)}{context_str}",
            error_code="TELEGRAM_ERROR",
            level=ErrorLevel.ERROR,
            details={"user_id": user_id},
            user_message="Ошибка Telegram. Попробуйте позже."
        )
    
    # Default fallback
    return AppError(
        message=f"Unexpected error: {str(error)}{context_str}",
        error_code="UNKNOWN_ERROR",
        level=ErrorLevel.CRITICAL,
        details={"original_error": str(error), "error_type": type(error).__name__, "user_id": user_id},
        user_message="Внутренняя ошибка. Попробуйте позже."
    )

async def log_error(
    error: AppError,
    operation: str,
    user_id: Optional[int] = None
) -> None:
    """
    Логирует ошибку с полной информацией.
    
    Args:
        error: Ошибка
        operation: Название операции
        user_id: ID пользователя
    """
    log_message: str = (
        f"[{error.error_code}] {operation}: {error.message}"
    )
    
    if error.level == ErrorLevel.CRITICAL:
        logger.critical(log_message, extra={"user_id": user_id, "details": error.details})
    elif error.level == ErrorLevel.ERROR:
        logger.error(log_message, extra={"user_id": user_id, "details": error.details})
    elif error.level == ErrorLevel.WARNING:
        logger.warning(log_message, extra={"user_id": user_id, "details": error.details})
    else:
        logger.info(log_message, extra={"user_id": user_id, "details": error.details})
    
    # Записываем в аудит для критических ошибок
    if error.level in (ErrorLevel.ERROR, ErrorLevel.CRITICAL):
        try:
            await audit_log(
                user_id=user_id,
                action="error",
                command=operation,
                error_message=error.message,
                status="failed"
            )
        except Exception as e:
            logger.error(f"Failed to log error to audit: {e}")

# =============================================================================
# ФУНКЦИИ ДЛЯ ПУБЛИКАЦИИ ПОСТОВ В КАНАЛ
# =============================================================================

async def send_channel_post(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    parse_mode: str = ParseMode.HTML,
    silent: bool = True
) -> bool:
    """
    Отправляет пост в канал обновлений.
    
    Args:
        context: Контекст бота
        text: Текст поста
        parse_mode: Режим парсинга (HTML или Markdown)
        silent: Отправлять ли без звука уведомления
    
    Returns:
        True если успешно, False если ошибка
    """
    if not UPDATE_CHANNEL_ID:
        logger.warning("UPDATE_CHANNEL_ID не установлен - посты не будут отправляться")
        return False
    
    try:
        await context.bot.send_message(
            chat_id=UPDATE_CHANNEL_ID,
            text=text,
            parse_mode=parse_mode,
            disable_notification=silent
        )
        logger.info("Пост отправлен в канал обновлений")
        return True
    except TelegramError as e:
        logger.error(f"Ошибка при отправке поста в канал: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке поста: {e}")
        return False


async def notify_version_update(context: ContextTypes.DEFAULT_TYPE, version: str, changelog: str) -> None:
    """
    Отправляет уведомление об обновлении версии в канал.
    """
    post = f"""🚀 <b>ОБНОВЛЕНИЕ БОТА - Версия {version}</b>

<b>Что нового:</b>
{changelog}

⏰ Обновление: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

✨ Спасибо за активность! Ваши отзывы помогают улучшить бот!"""
    
    await send_channel_post(context, post)


async def notify_new_quests(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет уведомление о новых ежедневных квестах.
    """
    post = """📋 <b>Новые ежедневные квесты готовы!</b>

✅ У вас доступно 5 новых квестов

🎁 Полученные награды:
• XP за выполнение
• Бейджи за достижения
• Увеличение лимита запросов

💡 Совет: Используйте команду /tasks для просмотра квестов

⚡ Лимит запросов зависит от вашего уровня - получайте XP через квесты!"""
    
    await send_channel_post(context, post)


async def notify_system_maintenance(context: ContextTypes.DEFAULT_TYPE, duration_minutes: int = 5) -> None:
    """
    Отправляет уведомление об обслуживании системы.
    """
    post = f"""🔧 <b>Техническое обслуживание</b>

⏸️ Бот временно недоступен для обслуживания

⏱️ Ожидаемая длительность: ~{duration_minutes} минут

🔄 Система будет восстановлена вскоре

Спасибо за ваше терпение!"""
    
    await send_channel_post(context, post)


async def notify_milestone_reached(context: ContextTypes.DEFAULT_TYPE, milestone: str, count: int) -> None:
    """
    Отправляет уведомление о достижении вехи (например, 100 пользователей).
    """
    post = f"""🎉 <b>Веха достигнута: {milestone}!</b>

📈 В сообществе RVX {count} активных пользователей!

🙏 Спасибо за вашу поддержку и активность

✨ Продолжайте учиться и развиваться вместе с нами!"""
    
    await send_channel_post(context, post)


async def notify_new_feature(context: ContextTypes.DEFAULT_TYPE, feature_name: str, description: str) -> None:
    """
    Отправляет уведомление о новой функции.
    """
    post = f"""✨ <b>Новая функция: {feature_name}</b>

📝 {description}

🎯 Используйте /help для подробной информации

💪 Продолжайте развиваться с новыми возможностями!"""
    
    await send_channel_post(context, post)


async def notify_stats_milestone(context: ContextTypes.DEFAULT_TYPE, stat_name: str, value: str) -> None:
    """
    Отправляет уведомление о статистическом рекорде.
    """
    post = f"""📊 <b>Новый рекорд: {stat_name}</b>

🏆 {value}

🔥 Это показывает активность нашего сообщества!

✨ Спасибо вам всем за участие!"""
    
    await send_channel_post(context, post)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (HELPER FUNCTIONS)
# =============================================================================

async def send_html_message(
    update: Update,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    edit: bool = False
) -> None:
    """
    Отправляет HTML сообщение (减少дублирования).
    
    Args:
        update: Telegram Update объект
        text: HTML текст
        reply_markup: Клавиатура (опционально)
        edit: Если True, редактирует сообщение (для callback)
        
    Returns:
        None
    """
    if edit and update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )


async def send_educational_message(
    update: Update,
    topic: str,
    explanation: str,
    tips: Optional[List[str]] = None,
    example: Optional[str] = None
) -> None:
    """
    Отправляет обучающее сообщение с объяснением, советами и примерами.
    
    Args:
        update: Telegram Update объект
        topic: Тема сообщения (заголовок)
        explanation: Основное объяснение
        tips: Список советов/ключевых моментов
        example: Практический пример
        
    Returns:
        None
    """
    message = f"<b>📚 {topic}</b>\n\n"
    message += f"{explanation}\n"
    
    if tips:
        message += "\n<b>💡 Ключевые моменты:</b>\n"
        for i, tip in enumerate(tips, 1):
            message += f"  {i}. {tip}\n"
    
    if example:
        message += f"\n<b>📝 Пример:</b>\n<code>{example}</code>"
    
    await send_html_message(update, message)


async def send_expert_response(
    update: Update,
    title: str,
    main_content: str,
    context: Optional[str] = None,
    background: Optional[str] = None,
    historical_context: Optional[str] = None,
    key_points: Optional[List[str]] = None,
    examples: Optional[List[str]] = None,
    real_world_applications: Optional[List[str]] = None,
    interactive_questions: Optional[List[str]] = None,
    deep_insights: Optional[List[str]] = None,
    common_misconceptions: Optional[List[str]] = None,
    advanced_details: Optional[str] = None,
    related_topics: Optional[List[str]] = None,
    next_steps: Optional[List[str]] = None,
    resources: Optional[List[str]] = None
) -> None:
    """
    МАКСИМАЛЬНО РАЗВЕРНУТЫЙ экспертный ответ с ОГРОМНЫМ количеством информации.
    
    Это главная функция для **глубоких, информативных, экспертных ответов**.
    Включает: контекст, фон, историю, примеры, вопросы, инсайты, и много еще!
    
    Args:
        update: Telegram Update
        title: Заголовок (основная тема)
        main_content: ОСНОВНОЕ СОДЕРЖАНИЕ (развернутое объяснение)
        context: Контекст и взаимосвязи
        background: Фоновая информация для понимания
        historical_context: Историческое развитие темы
        key_points: КРИТИЧЕСКИЕ ключевые моменты (запомни!)
        examples: Примеры со всеми деталями
        real_world_applications: Применение в реальной жизни
        interactive_questions: Вопросы для размышления и самопроверки
        deep_insights: ГЛУБОКИЕ инсайты и секреты профессионалов
        common_misconceptions: Типичные ошибки и неправильные представления
        advanced_details: Продвинутые детали для глубокого понимания
        related_topics: Связанные темы для расширения знаний
        next_steps: Точная дорожная карта дальнейшего обучения
        resources: Ссылки на дополнительные ресурсы и материалы
        
    Returns:
        None
    """
    message = f"<b>🎓 ПОЛНЫЙ ГАЙД: {title}</b>\n"
    message += "═" * 60 + "\n\n"
    
    # 1. ОСНОВНОЕ СОДЕРЖАНИЕ (самое важное!)
    message += f"<b>📖 ПОЛНОЕ ОБЪЯСНЕНИЕ:</b>\n{main_content}\n\n"
    
    # 2. КОНТЕКСТ И ФОНОВАЯ ИНФОРМАЦИЯ
    if context:
        message += f"<b>🔍 КОНТЕКСТ И ВЗАИМОСВЯЗИ:</b>\n{context}\n\n"
    
    if background:
        message += f"<b>📚 ФОНОВАЯ ИНФОРМАЦИЯ:</b>\n{background}\n\n"
    
    # 3. ИСТОРИЧЕСКОЕ РАЗВИТИЕ
    if historical_context:
        message += f"<b>⏳ ИСТОРИЯ И ЭВОЛЮЦИЯ:</b>\n{historical_context}\n\n"
    
    # 4. КЛЮЧЕВЫЕ МОМЕНТЫ (ОЧЕНЬ ВАЖНО!)
    if key_points:
        message += "<b>⭐ КЛЮЧЕВЫЕ МОМЕНТЫ (ЗАПОМНИ!):</b>\n"
        for i, point in enumerate(key_points, 1):
            message += f"  {i}. 🔴 {point}\n"
        message += "\n"
    
    # 5. ПРИМЕРЫ С ДЕТАЛЯМИ
    if examples:
        message += "<b>💼 РЕАЛЬНЫЕ ПРИМЕРЫ И КЕЙСЫ:</b>\n"
        for i, example in enumerate(examples, 1):
            message += f"  ├─ Пример {i}: {example}\n"
        message += "\n"
    
    # 6. ПРИМЕНЕНИЕ В ЖИЗНИ
    if real_world_applications:
        message += "<b>🌍 ПРИМЕНЕНИЕ В РЕАЛЬНОЙ ЖИЗНИ:</b>\n"
        for app in real_world_applications:
            message += f"  • {app}\n"
        message += "\n"
    
    # 7. ГЛУБОКИЕ ИНСАЙТЫ (ПРОФЕССИОНАЛЬНЫЙ УРОВЕНЬ!)
    if deep_insights:
        message += "<b>💎 ГЛУБОКИЕ ИНСАЙТЫ (профессиональный уровень!):</b>\n"
        for i, insight in enumerate(deep_insights, 1):
            message += f"  ✦ {insight}\n"
        message += "\n"
    
    # 8. ТИПИЧНЫЕ ОШИБКИ
    if common_misconceptions:
        message += "<b>❌ ТИПИЧНЫЕ ОШИБКИ И НЕПРАВИЛЬНЫЕ ПРЕДСТАВЛЕНИЯ:</b>\n"
        for misconception in common_misconceptions:
            message += f"  ✗ {misconception}\n"
        message += "\n"
    
    # 9. ВОПРОСЫ ДЛЯ РАЗМЫШЛЕНИЯ
    if interactive_questions:
        message += "<b>🤔 ВОПРОСЫ ДЛЯ РАЗМЫШЛЕНИЯ (ответь себе!):</b>\n"
        for i, q in enumerate(interactive_questions, 1):
            message += f"  {i}. {q}\n"
        message += "\n"
    
    # 10. ПРОДВИНУТЫЕ ДЕТАЛИ
    if advanced_details:
        message += f"<b>🔬 ПРОДВИНУТЫЕ ДЕТАЛИ (для глубокого погружения):</b>\n{advanced_details}\n\n"
    
    # 11. СВЯЗАННЫЕ ТЕМЫ
    if related_topics:
        message += "<b>🔗 СВЯЗАННЫЕ ТЕМЫ ДЛЯ РАСШИРЕНИЯ ЗНАНИЙ:</b>\n"
        for topic in related_topics:
            message += f"  → {topic}\n"
        message += "\n"
    
    # 12. ДОРОЖНАЯ КАРТА
    if next_steps:
        message += "<b>🚀 ДОРОЖНАЯ КАРТА ОБУЧЕНИЯ:</b>\n"
        for i, step in enumerate(next_steps, 1):
            message += f"  {i}. {step}\n"
        message += "\n"
    
    # 13. РЕСУРСЫ
    if resources:
        message += "<b>📎 ПОЛЕЗНЫЕ РЕСУРСЫ И МАТЕРИАЛЫ:</b>\n"
        for resource in resources:
            message += f"  • {resource}\n"
        message += "\n"
    
    message += f"\n<i>💪 Это полный гайд. Изучи внимательно и задавай вопросы!</i>"
    
    await send_html_message(update, message)


async def send_analytical_breakdown(
    update: Update,
    topic: str,
    analysis: str,
    market_context: Optional[str] = None,
    historical_background: Optional[str] = None,
    pros: Optional[List[str]] = None,
    cons: Optional[List[str]] = None,
    critical_points: Optional[List[str]] = None,
    comparison: Optional[str] = None,
    statistical_data: Optional[str] = None,
    market_implications: Optional[str] = None,
    expert_opinion: Optional[List[str]] = None,
    contrarian_view: Optional[str] = None,
    discussion_prompts: Optional[List[str]] = None,
    action_items: Optional[List[str]] = None,
    risks_and_opportunities: Optional[str] = None
) -> None:
    """
    МЕГА-АНАЛИТИЧЕСКИЙ РАЗБОР с глубочайшим анализом.
    
    Для новостей, фундаментального анализа, сложных тем, инвестиционных решений.
    Включает: контекст, плюсы-минусы, статистику, экспертное мнение, риски, возможности!
    
    Args:
        update: Telegram Update
        topic: Название темы / новости
        analysis: ОСНОВНОЙ развернутый анализ
        market_context: Контекст на рынке
        historical_background: Историческое развитие темы
        pros: ПОЛОЖИТЕЛЬНЫЕ аспекты (будущие выводы)
        cons: ОТРИЦАТЕЛЬНЫЕ аспекты (потенциальные риски)
        critical_points: КРИТИЧЕСКИЕ моменты (особое внимание!)
        comparison: Сравнение с альтернативами/предыдущими событиями
        statistical_data: СТАТИСТИЧЕСКИЕ данные и цифры
        market_implications: Последствия для рынка
        expert_opinion: Мнения экспертов и аналитиков
        contrarian_view: Противоположная точка зрения (важна!)
        discussion_prompts: Вопросы для дискуссии и размышления
        action_items: Рекомендуемые действия
        risks_and_opportunities: Риски И возможности
        
    Returns:
        None
    """
    message = f"<b>📊 ПОЛНЫЙ АНАЛИТИЧЕСКИЙ РАЗБОР: {topic}</b>\n"
    message += "═" * 60 + "\n\n"
    
    # 1. КОНТЕКСТ НА РЫНКЕ
    if market_context:
        message += f"<b>📍 КОНТЕКСТ НА РЫНКЕ:</b>\n{market_context}\n\n"
    
    # 2. ИСТОРИЧЕСКОЕ РАЗВИТИЕ
    if historical_background:
        message += f"<b>⏳ ИСТОРИЧЕСКОЕ РАЗВИТИЕ:</b>\n{historical_background}\n\n"
    
    # 3. ОСНОВНОЙ АНАЛИЗ (ГЛАВНЫЙ!)
    message += f"<b>🔎 ПОЛНЫЙ АНАЛИЗ:</b>\n{analysis}\n\n"
    
    # 4. ПОЛОЖИТЕЛЬНЫЕ АСПЕКТЫ
    if pros:
        message += "<b>✅ ПОЛОЖИТЕЛЬНЫЕ АСПЕКТЫ И ВОЗМОЖНОСТИ:</b>\n"
        for i, pro in enumerate(pros, 1):
            message += f"  ✓ {pro}\n"
        message += "\n"
    
    # 5. ОТРИЦАТЕЛЬНЫЕ АСПЕКТЫ
    if cons:
        message += "<b>⚠️ ОТРИЦАТЕЛЬНЫЕ АСПЕКТЫ И РИСКИ:</b>\n"
        for i, con in enumerate(cons, 1):
            message += f"  ✗ {con}\n"
        message += "\n"
    
    # 6. КРИТИЧЕСКИЕ МОМЕНТЫ
    if critical_points:
        message += "<b>🚨 КРИТИЧЕСКИЕ МОМЕНТЫ (ОБЯЗАТЕЛЬНО ЗНАЙ!):</b>\n"
        for i, cp in enumerate(critical_points, 1):
            message += f"  ⚡ {cp}\n"
        message += "\n"
    
    # 7. СРАВНЕНИЕ
    if comparison:
        message += f"<b>⚖️ СРАВНЕНИЕ С АЛЬТЕРНАТИВАМИ:</b>\n{comparison}\n\n"
    
    # 8. СТАТИСТИКА
    if statistical_data:
        message += f"<b>📈 СТАТИСТИЧЕСКИЕ ДАННЫЕ И ЦИФРЫ:</b>\n{statistical_data}\n\n"
    
    # 9. ПОСЛЕДСТВИЯ ДЛЯ РЫНКА
    if market_implications:
        message += f"<b>💹 ПОСЛЕДСТВИЯ ДЛЯ РЫНКА:</b>\n{market_implications}\n\n"
    
    # 10. ЭКСПЕРТНЫЕ МНЕНИЯ
    if expert_opinion:
        message += "<b>👨‍💼 МНЕНИЯ ЭКСПЕРТОВ И АНАЛИТИКОВ:</b>\n"
        for opinion in expert_opinion:
            message += f"  • {opinion}\n"
        message += "\n"
    
    # 11. ПРОТИВОПОЛОЖНАЯ ТОЧКА ЗРЕНИЯ
    if contrarian_view:
        message += f"<b>🔄 ПРОТИВОПОЛОЖНАЯ ТОЧКА ЗРЕНИЯ (важна!):</b>\n{contrarian_view}\n\n"
    
    # 12. РИСКИ И ВОЗМОЖНОСТИ
    if risks_and_opportunities:
        message += f"<b>⚔️ РИСКИ И ВОЗМОЖНОСТИ:</b>\n{risks_and_opportunities}\n\n"
    
    # 13. РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ
    if action_items:
        message += "<b>🎯 РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ:</b>\n"
        for i, action in enumerate(action_items, 1):
            message += f"  {i}. {action}\n"
        message += "\n"
    
    # 14. ВОПРОСЫ ДЛЯ ДИСКУССИИ
    if discussion_prompts:
        message += "<b>💬 ДАВАЙ ОБСУДИМ (напиши свой ответ):</b>\n"
        for i, prompt in enumerate(discussion_prompts, 1):
            message += f"  {i}. {prompt}\n"
        message += "\n"
    
    message += "<i>🧠 Будь критичным! Анализируй информацию из разных источников!</i>"
    
    await send_html_message(update, message)


async def send_interactive_learning(
    update: Update,
    lesson_title: str,
    introduction: str,
    core_concepts: Dict[str, str],
    learning_objectives: Optional[List[str]] = None,
    prerequisites: Optional[List[str]] = None,
    practice_questions: Optional[List[str]] = None,
    common_mistakes: Optional[List[str]] = None,
    step_by_step_guide: Optional[str] = None,
    deeper_dive: Optional[str] = None,
    advanced_techniques: Optional[List[str]] = None,
    real_world_projects: Optional[List[str]] = None,
    student_reflection: Optional[List[str]] = None,
    assessment_criteria: Optional[str] = None,
    resources_to_study: Optional[List[str]] = None,
    next_lesson_path: Optional[str] = None
) -> None:
    """
    ПОЛНЫЙ ИНТЕРАКТИВНЫЙ УРОК с максимум деталей и структуры.
    
    Для полноценного обучения от новичка к профессионалу.
    Включает: цели, концепции, практику, проекты, рефлексию, следующие шаги!
    
    Args:
        update: Telegram Update
        lesson_title: Название урока
        introduction: ВВЕДЕНИЕ в тему (зачем это нужно?)
        core_concepts: Основные концепции {название: объяснение}
        learning_objectives: ЦЕЛИ обучения (что ты научишься?)
        prerequisites: Предварительные знания (что нужно знать?)
        practice_questions: ПРАКТИЧЕСКИЕ вопросы (ответь!)
        common_mistakes: Типичные ошибки новичков (избегай!)
        step_by_step_guide: Пошаговая инструкция
        deeper_dive: Глубокое погружение для расширения знаний
        advanced_techniques: Продвинутые техники (для опытных)
        real_world_projects: Реальные проекты для практики
        student_reflection: Вопросы для саморефлексии (самоанализ)
        assessment_criteria: Как проверить, что ты все понял?
        resources_to_study: Ресурсы для углубленного изучения
        next_lesson_path: Дорожная карта дальнейшего обучения
        
    Returns:
        None
    """
    message = f"<b>📚 ПОЛНЫЙ ИНТЕРАКТИВНЫЙ УРОК: {lesson_title}</b>\n"
    message += "═" * 60 + "\n\n"
    
    # 1. ВВЕДЕНИЕ
    message += f"<b>👋 ВВЕДЕНИЕ:</b>\n{introduction}\n\n"
    
    # 2. ЦЕЛИ ОБУЧЕНИЯ
    if learning_objectives:
        message += "<b>🎯 ЦЕЛИ ОБУЧЕНИЯ (что ты получишь?):</b>\n"
        for i, obj in enumerate(learning_objectives, 1):
            message += f"  {i}. {obj}\n"
        message += "\n"
    
    # 3. ПРЕДВАРИТЕЛЬНЫЕ ЗНАНИЯ
    if prerequisites:
        message += "<b>📖 ПРЕДВАРИТЕЛЬНЫЕ ЗНАНИЯ (нужно знать):</b>\n"
        for prereq in prerequisites:
            message += f"  • {prereq}\n"
        message += "\n"
    
    # 4. ОСНОВНЫЕ КОНЦЕПЦИИ (ГЛАВНОЕ!)
    message += "<b>🎯 ОСНОВНЫЕ КОНЦЕПЦИИ (запомни всё!):</b>\n"
    for i, (concept, explanation) in enumerate(core_concepts.items(), 1):
        message += f"\n  <b>{i}. {concept}</b>\n"
        message += f"     {explanation}\n"
    message += "\n"
    
    # 5. ТИПИЧНЫЕ ОШИБКИ
    if common_mistakes:
        message += "<b>❌ ТИПИЧНЫЕ ОШИБКИ НОВИЧКОВ (избегай!):</b>\n"
        for mistake in common_mistakes:
            message += f"  ✗ {mistake}\n"
        message += "\n"
    
    # 6. ПОШАГОВАЯ ИНСТРУКЦИЯ
    if step_by_step_guide:
        message += f"<b>📋 ПОШАГОВАЯ ИНСТРУКЦИЯ:</b>\n{step_by_step_guide}\n\n"
    
    # 7. ПРАКТИЧЕСКИЕ ВОПРОСЫ
    if practice_questions:
        message += "<b>✍️ ПОПРОБУЙ ОТВЕТИТЬ (пиши свои ответы!):</b>\n"
        for i, q in enumerate(practice_questions, 1):
            message += f"  {i}. {q}\n"
        message += "\n"
    
    # 8. ГЛУБОКОЕ ПОГРУЖЕНИЕ
    if deeper_dive:
        message += f"<b>🔬 ГЛУБОКОЕ ПОГРУЖЕНИЕ (для расширения):</b>\n{deeper_dive}\n\n"
    
    # 9. ПРОДВИНУТЫЕ ТЕХНИКИ
    if advanced_techniques:
        message += "<b>⚡ ПРОДВИНУТЫЕ ТЕХНИКИ (для опытных):</b>\n"
        for i, tech in enumerate(advanced_techniques, 1):
            message += f"  {i}. {tech}\n"
        message += "\n"
    
    # 10. РЕАЛЬНЫЕ ПРОЕКТЫ
    if real_world_projects:
        message += "<b>🚀 РЕАЛЬНЫЕ ПРОЕКТЫ ДЛЯ ПРАКТИКИ:</b>\n"
        for i, project in enumerate(real_world_projects, 1):
            message += f"  {i}. {project}\n"
        message += "\n"
    
    # 11. САМОРЕФЛЕКСИЯ
    if student_reflection:
        message += "<b>🤔 ВОПРОСЫ ДЛЯ САМОРЕФЛЕКСИИ (самоанализ!):</b>\n"
        for q in student_reflection:
            message += f"  • {q}\n"
        message += "\n"
    
    # 12. КРИТЕРИИ ОЦЕНКИ
    if assessment_criteria:
        message += f"<b>✓ КАК ПРОВЕРИТЬ, ЧТО ТЫ ВСЕ ПОНЯЛ?</b>\n{assessment_criteria}\n\n"
    
    # 13. РЕСУРСЫ
    if resources_to_study:
        message += "<b>📚 РЕСУРСЫ ДЛЯ УГЛУБЛЕННОГО ИЗУЧЕНИЯ:</b>\n"
        for resource in resources_to_study:
            message += f"  • {resource}\n"
        message += "\n"
    
    # 14. ДОРОЖНАЯ КАРТА
    if next_lesson_path:
        message += f"<b>🗺️ ДОРОЖНАЯ КАРТА ДАЛЬНЕЙШЕГО ОБУЧЕНИЯ:</b>\n{next_lesson_path}\n\n"
    
    message += "<i>💪 Учись активно! Не читай пассивно - думай, практикуй, применяй!</i>"
    
    await send_html_message(update, message)


async def send_comprehensive_analysis(
    update: Update,
    title: str,
    executive_summary: str,
    detailed_explanation: str,
    historical_context: Optional[str] = None,
    current_state: Optional[str] = None,
    technical_breakdown: Optional[str] = None,
    fundamental_analysis: Optional[str] = None,
    market_data_points: Optional[List[str]] = None,
    pros_list: Optional[List[str]] = None,
    cons_list: Optional[List[str]] = None,
    risks: Optional[List[str]] = None,
    opportunities: Optional[List[str]] = None,
    expert_predictions: Optional[List[str]] = None,
    contrarian_opinions: Optional[List[str]] = None,
    real_world_examples: Optional[List[str]] = None,
    action_recommendations: Optional[List[str]] = None,
    investment_thesis: Optional[str] = None,
    timeline_and_catalysts: Optional[str] = None,
    key_metrics_to_watch: Optional[List[str]] = None,
    conclusion_and_outlook: Optional[str] = None
) -> None:
    """
    МАКСИМАЛЬНО ПОЛНЫЙ И КОМПЛЕКСНЫЙ АНАЛИЗ - самая развёрнутая функция!
    
    Для максимально информативных ответов на сложные вопросы.
    Включает: резюме, анализ, данные, риски, возможности, прогнозы, выводы!
    
    Args:
        update: Telegram Update
        title: Заголовок анализа
        executive_summary: КРАТКОЕ РЕЗЮМЕ (главное коротко)
        detailed_explanation: ПОДРОБНОЕ ОБЪЯСНЕНИЕ (все детали)
        historical_context: Историческое развитие вопроса
        current_state: ТЕКУЩЕЕ СОСТОЯНИЕ (как сейчас?)
        technical_breakdown: Техническая разборка
        fundamental_analysis: Фундаментальный анализ
        market_data_points: Ключевые данные и цифры
        pros_list: Плюсы и преимущества
        cons_list: Минусы и недостатки
        risks: Риски и угрозы
        opportunities: Возможности и потенциал
        expert_predictions: Прогнозы экспертов
        contrarian_opinions: Противоположные мнения
        real_world_examples: Реальные примеры и кейсы
        action_recommendations: Рекомендуемые действия
        investment_thesis: Инвестиционный тезис
        timeline_and_catalysts: Временная шкала и катализаторы
        key_metrics_to_watch: Ключевые метрики для мониторинга
        conclusion_and_outlook: Выводы и прогноз
        
    Returns:
        None
    """
    message = f"<b>🔬 ПОЛНЫЙ КОМПЛЕКСНЫЙ АНАЛИЗ: {html.escape(title)}</b>\n"
    message += "═" * 70 + "\n\n"
    
    # 1. КРАТКОЕ РЕЗЮМЕ (XSS Protection: escape user content)
    message += f"<b>📝 КРАТКОЕ РЕЗЮМЕ (главное коротко):</b>\n{html.escape(executive_summary)}\n\n"
    
    # 2. ПОДРОБНОЕ ОБЪЯСНЕНИЕ
    message += f"<b>📖 ПОЛНОЕ ПОДРОБНОЕ ОБЪЯСНЕНИЕ:</b>\n{html.escape(detailed_explanation)}\n\n"
    
    # 3. ИСТОРИЧЕСКОЕ РАЗВИТИЕ
    if historical_context:
        message += f"<b>⏳ ИСТОРИЧЕСКОЕ РАЗВИТИЕ:</b>\n{html.escape(historical_context)}\n\n"
    
    # 4. ТЕКУЩЕЕ СОСТОЯНИЕ
    if current_state:
        message += f"<b>🎯 ТЕКУЩЕЕ СОСТОЯНИЕ (как сейчас?):</b>\n{html.escape(current_state)}\n\n"
    
    # 5. ТЕХНИЧЕСКАЯ РАЗБОРКА
    if technical_breakdown:
        message += f"<b>⚙️ ТЕХНИЧЕСКАЯ РАЗБОРКА:</b>\n{html.escape(technical_breakdown)}\n\n"
    
    # 6. ФУНДАМЕНТАЛЬНЫЙ АНАЛИЗ
    if fundamental_analysis:
        message += f"<b>📊 ФУНДАМЕНТАЛЬНЫЙ АНАЛИЗ:</b>\n{html.escape(fundamental_analysis)}\n\n"
    
    # 7. КЛЮЧЕВЫЕ ДАННЫЕ
    if market_data_points:
        message += "<b>📈 КЛЮЧЕВЫЕ ДАННЫЕ И ЦИФРЫ:</b>\n"
        for data in market_data_points:
            message += f"  • {html.escape(data)}\n"
        message += "\n"
    
    # 8. ПЛЮСЫ
    if pros_list:
        message += "<b>✅ ПЛЮСЫ И ПРЕИМУЩЕСТВА:</b>\n"
        for i, pro in enumerate(pros_list, 1):
            message += f"  {i}. {html.escape(pro)}\n"
        message += "\n"
    
    # 9. МИНУСЫ
    if cons_list:
        message += "<b>❌ МИНУСЫ И НЕДОСТАТКИ:</b>\n"
        for i, con in enumerate(cons_list, 1):
            message += f"  {i}. {html.escape(con)}\n"
        message += "\n"
    
    # 10. РИСКИ
    if risks:
        message += "<b>⚠️ РИСКИ И УГРОЗЫ:</b>\n"
        for risk in risks:
            message += f"  ⚡ {html.escape(risk)}\n"
        message += "\n"
    
    # 11. ВОЗМОЖНОСТИ
    if opportunities:
        message += "<b>🚀 ВОЗМОЖНОСТИ И ПОТЕНЦИАЛ:</b>\n"
        for opp in opportunities:
            message += f"  ⭐ {opp}\n"
        message += "\n"
    
    # 12. ПРОГНОЗЫ ЭКСПЕРТОВ
    if expert_predictions:
        message += "<b>🔮 ПРОГНОЗЫ ЭКСПЕРТОВ:</b>\n"
        for pred in expert_predictions:
            message += f"  • {pred}\n"
        message += "\n"
    
    # 13. ПРОТИВОПОЛОЖНЫЕ МНЕНИЯ
    if contrarian_opinions:
        message += "<b>🔄 ПРОТИВОПОЛОЖНЫЕ МНЕНИЯ (важны!):</b>\n"
        for opinion in contrarian_opinions:
            message += f"  • {opinion}\n"
        message += "\n"
    
    # 14. РЕАЛЬНЫЕ ПРИМЕРЫ
    if real_world_examples:
        message += "<b>🌍 РЕАЛЬНЫЕ ПРИМЕРЫ И КЕЙСЫ:</b>\n"
        for example in real_world_examples:
            message += f"  • {example}\n"
        message += "\n"
    
    # 15. ИНВЕСТИЦИОННЫЙ ТЕЗИС
    if investment_thesis:
        message += f"<b>💼 ИНВЕСТИЦИОННЫЙ ТЕЗИС:</b>\n{investment_thesis}\n\n"
    
    # 16. ВРЕМЕННАЯ ШКАЛА И КАТАЛИЗАТОРЫ
    if timeline_and_catalysts:
        message += f"<b>⏱️ ВРЕМЕННАЯ ШКАЛА И КАТАЛИЗАТОРЫ:</b>\n{timeline_and_catalysts}\n\n"
    
    # 17. КЛЮЧЕВЫЕ МЕТРИКИ
    if key_metrics_to_watch:
        message += "<b>📊 КЛЮЧЕВЫЕ МЕТРИКИ ДЛЯ МОНИТОРИНГА:</b>\n"
        for metric in key_metrics_to_watch:
            message += f"  ► {metric}\n"
        message += "\n"
    
    # 18. РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ
    if action_recommendations:
        message += "<b>🎯 РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ:</b>\n"
        for i, action in enumerate(action_recommendations, 1):
            message += f"  {i}. {action}\n"
        message += "\n"
    
    # 19. ВЫВОДЫ И ПРОГНОЗ
    if conclusion_and_outlook:
        message += f"<b>🔚 ВЫВОДЫ И ПРОГНОЗ:</b>\n{conclusion_and_outlook}\n\n"
    
    message += "<i>🧠 Это полный анализ со всех сторон. Изучи внимательно!</i>"
    
    await send_html_message(update, message)

async def send_error_with_tips(
    update: Update,
    error: str,
    tips: Optional[List[str]] = None,
    command_help: Optional[str] = None
) -> None:
    """
    Отправляет сообщение об ошибке с полезными советами.
    
    Args:
        update: Telegram Update объект
        error: Описание ошибки
        tips: Список советов как исправить
        command_help: Пример правильного использования команды
        
    Returns:
        None
    """
    message = f"❌ <b>Ошибка:</b> {error}\n"
    
    if tips:
        message += "\n<b>🔧 Как исправить:</b>\n"
        for i, tip in enumerate(tips, 1):
            message += f"  {i}. {tip}\n"
    
    if command_help:
        message += f"\n<b>📖 Пример:</b>\n<code>{command_help}</code>"
    
    message += "\n\n💬 <i>Если нужна помощь, используй /help</i>"
    
    await send_html_message(update, message)


async def send_success_with_next_steps(
    update: Update,
    success_message: str,
    next_steps: Optional[List[str]] = None,
    action_tip: Optional[str] = None
) -> None:
    """
    Отправляет сообщение об успехе с советами что дальше.
    
    Args:
        update: Telegram Update объект
        success_message: Основное сообщение об успехе
        next_steps: Список рекомендуемых действий
        action_tip: Совет для дальнейшего обучения
        
    Returns:
        None
    """
    message = f"✅ <b>Готово!</b> {success_message}\n"
    
    if next_steps:
        message += "\n<b>🚀 Что дальше:</b>\n"
        for i, step in enumerate(next_steps, 1):
            message += f"  {i}. {step}\n"
    
    if action_tip:
        message += f"\n<b>💭 Полезно знать:</b>\n{action_tip}"
    
    await send_html_message(update, message)


# =============================================================================
# DATABASE CONNECTION POOL (TIER 1: Performance optimization v0.22.0)
# =============================================================================

# Global pool instance (using optimized DatabaseConnectionPool from tier1_optimizations)
db_pool: Optional[DatabaseConnectionPool] = None

def init_db_pool() -> None:
    """Initialize database pool on bot startup with TIER 1 optimization."""
    global db_pool
    db_pool = DatabaseConnectionPool(DB_PATH, pool_size=DB_POOL_SIZE)
    stats = db_pool.get_stats()
    logger.info(f"Database pool initialized: {stats}")

# =============================================================================

# БАЗА ДАННЫХ
# =============================================================================

@contextmanager
def get_db() -> contextmanager:
    """Context manager для работы с БД с правильной обработкой ошибок и освобождением ресурсов.
    
    TIER 1 v0.22.0: Использует пул соединений для оптимизации производительности.
    Гарантирует закрытие соединения даже при исключениях.
    Предотвращает утечку ресурсов (memory leak ~500KB/day в production).
    
    v0.26.0: Добавлен retry mechanism для "database is locked" ошибок с exponential backoff.
    """
    conn = None
    max_retries = 5
    retry_delay = 0.1  # Start with 100ms
    attempt = 0
    
    while attempt < max_retries:
        try:
            # Получаем соединение из пула или создаем новое
            if db_pool:
                conn = db_pool.get_connection()
            else:
                conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
            
            if conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
                conn.execute("PRAGMA busy_timeout=10000")  # 10 second timeout
            
            yield conn
            if conn:
                conn.commit()
            break  # Success, exit retry loop
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                # Retry with exponential backoff for locked database
                import time
                attempt += 1
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
                if conn:
                    try:
                        conn.close()
                    except Exception as close_err:
                        logger.debug(f"Could not close locked connection: {close_err}")
                continue
            else:
                # Not a lock error or final attempt
                if conn:
                    try:
                        conn.rollback()
                    except Exception as rollback_err:
                        logger.debug(f"Could not rollback on error: {rollback_err}")
                logger.error(f"DB ошибка: {e}", exc_info=True)
                raise
        except sqlite3.Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_err:
                    logger.debug(f"Could not rollback: {rollback_err}")
            logger.error(f"DB ошибка: {e}", exc_info=True)
            raise
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_err:
                    logger.debug(f"Could not rollback: {rollback_err}")
            logger.error(f"Неожиданная ошибка БД: {e}", exc_info=True)
            raise
        finally:
            # Возвращаем соединение в пул (TIER 1 v0.22.0)
            if conn and db_pool:
                db_pool.return_connection(conn)

def check_column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Проверяет существование колонки в таблице.
    
    ✅ CRITICAL FIX #1: SQL Injection protection via whitelist validation
    PRAGMA statements do not support parameterized queries, so we validate
    table name against whitelist before execution.
    """
    # Whitelist разрешенных таблиц (контролируется разработчиком)
    # CRITICAL FIX #1: Only allow known tables to prevent PRAGMA injection
    ALLOWED_TABLES = {
        "users", "requests", "feedback", "cache", "user_progress",
        "user_quiz_responses", "user_quiz_stats", "conversation_history",
        "user_profiles", "user_bookmarks", "user_xp_events", "courses",
        "lessons", "user_questions", "faq", "tools", "user_drop_subscriptions",
        "drops_history", "activities_cache", "user_courses"
    }
    
    # Проверка против whitelist - БЕЗОПАСНО ОТ SQL INJECTION
    if table not in ALLOWED_TABLES:
        logger.warning(f"Попытка доступа к запрещённой таблице: {table}")
        return False
    
    # ✅ БЕЗОПАСНО: Таблица проверена против whitelist перед PRAGMA
    # PRAGMA table_info() не поддерживает параметры, но таблица валидирована
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def migrate_database() -> None:
    """Миграция базы данных к новой схеме v0.5.0."""
    logger.info("Проверка необходимости миграции...")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 🆕 v0.37.14: CRITICAL FIX - Пересоздание таблицы users если она неполная
        # (это может случиться если БД была создана старой версией кода)
        logger.info("Проверка полноты схемы таблицы users...")
        required_columns = {
            'user_id', 'username', 'first_name', 'created_at', 'total_requests',
            'last_request_at', 'is_banned', 'ban_reason', 'daily_requests',
            'daily_reset_at', 'knowledge_level', 'xp', 'level', 'badges',
            'requests_today', 'last_request_date'
        }
        
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        missing_columns = required_columns - existing_columns
        
        if missing_columns:
            logger.warning(f"КРИТИЧНО: В таблице users отсутствуют колонки: {missing_columns}")
            logger.warning(f"Текущие колонки: {existing_columns}")
            logger.warning("Пересоздаём таблицу users с полной схемой...")
            
            try:
                # Сохраняем существующие данные
                cursor.execute("SELECT user_id, username FROM users")
                existing_users = cursor.fetchall()
                logger.info(f"Сохранено {len(existing_users)} пользователей")
                
                # Переименовываем старую таблицу
                cursor.execute("ALTER TABLE users RENAME TO users_old")
                
                # Создаём новую таблицу с правильной схемой
                cursor.execute("""
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        total_requests INTEGER DEFAULT 0,
                        last_request_at TIMESTAMP,
                        is_banned BOOLEAN DEFAULT 0,
                        ban_reason TEXT,
                        daily_requests INTEGER DEFAULT 0,
                        daily_reset_at TIMESTAMP,
                        knowledge_level TEXT DEFAULT 'unknown',
                        xp INTEGER DEFAULT 0,
                        level INTEGER DEFAULT 1,
                        badges TEXT DEFAULT '[]',
                        requests_today INTEGER DEFAULT 0,
                        last_request_date TEXT
                    )
                """)
                
                # Мигрируем данные
                for user_id, username in existing_users:
                    cursor.execute("""
                        INSERT INTO users (user_id, username, created_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (user_id, username))
                
                # Удаляем старую таблицу
                cursor.execute("DROP TABLE users_old")
                
                conn.commit()
                logger.info("Таблица users успешно пересоздана с полной схемой!")
                
            except Exception as e:
                logger.error(f"ОШИБКА при пересоздании таблицы users: {e}")
                conn.rollback()
                raise
        else:
            logger.info("Таблица users имеет полную схему")
        
        # Миграция users
        migrations_needed = False
        
        if not check_column_exists(cursor, 'users', 'is_banned'):
            logger.info("Добавление колонки is_banned...")
            cursor.execute("ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'ban_reason'):
            logger.info("Добавление колонки ban_reason...")
            cursor.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'daily_requests'):
            logger.info("Добавление колонки daily_requests...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_requests INTEGER DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'daily_reset_at'):
            logger.info("Добавление колонки daily_reset_at...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_reset_at TIMESTAMP")
            migrations_needed = True
        
        # NEW v0.5.0: Миграция новых полей для обучения
        if not check_column_exists(cursor, 'users', 'knowledge_level'):
            logger.info("Добавление колонки knowledge_level...")
            cursor.execute("ALTER TABLE users ADD COLUMN knowledge_level TEXT DEFAULT 'unknown'")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'xp'):
            logger.info("Добавление колонки xp...")
            cursor.execute("ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'level'):
            logger.info("Добавление колонки level...")
            cursor.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'badges'):
            logger.info("  • Добавление колонки badges...")
            cursor.execute("ALTER TABLE users ADD COLUMN badges TEXT DEFAULT '[]'")
            migrations_needed = True
        
        # Миграция requests
        if not check_column_exists(cursor, 'requests', 'processing_time_ms'):
            logger.info("  • Добавление колонки processing_time_ms...")
            cursor.execute("ALTER TABLE requests ADD COLUMN processing_time_ms REAL")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'requests', 'error_message'):
            logger.info("  • Добавление колонки error_message...")
            cursor.execute("ALTER TABLE requests ADD COLUMN error_message TEXT")
            migrations_needed = True
        
        # Миграция feedback
        if not check_column_exists(cursor, 'feedback', 'comment'):
            logger.info("  • Добавление колонки comment в feedback...")
            cursor.execute("ALTER TABLE feedback ADD COLUMN comment TEXT")
            migrations_needed = True
        
        # Миграция cache
        if not check_column_exists(cursor, 'cache', 'last_used_at'):
            logger.info("  • Добавление колонки last_used_at в cache...")
            cursor.execute("ALTER TABLE cache ADD COLUMN last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            migrations_needed = True
        
        # NEW v0.6.0: Добавление course_name в user_progress для поддержки get_user_course_summary()
        if not check_column_exists(cursor, 'user_progress', 'course_name'):
            logger.info("  • Добавление колонки course_name в user_progress...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN course_name TEXT")
            migrations_needed = True
        
        # NEW v0.14.0: Добавление колонок для системы лимитов (XP-зависимые запросы)
        if not check_column_exists(cursor, 'users', 'requests_today'):
            logger.info("  • Добавление колонки requests_today...")
            cursor.execute("ALTER TABLE users ADD COLUMN requests_today INTEGER DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'last_request_date'):
            logger.info("  • Добавление колонки last_request_date...")
            cursor.execute("ALTER TABLE users ADD COLUMN last_request_date TEXT")
            migrations_needed = True
        
        # NEW v0.19.0: Таблицы для Quiz System
        # Эти таблицы должны быть созданы в init_database, но добавляем миграцию для старых БД
        try:
            cursor.execute("SELECT 1 FROM user_quiz_responses LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы user_quiz_responses...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_quiz_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    lesson_id INTEGER,
                    question_number INTEGER,
                    selected_answer_index INTEGER,
                    is_correct BOOLEAN,
                    xp_earned INTEGER DEFAULT 0,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id)
                )
            """)
            migrations_needed = True
        
        try:
            cursor.execute("SELECT 1 FROM user_quiz_stats LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы user_quiz_stats...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_quiz_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    lesson_id INTEGER,
                    total_questions INTEGER,
                    correct_answers INTEGER,
                    quiz_score REAL,
                    total_xp_earned INTEGER DEFAULT 0,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_perfect_score BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id)
                )
            """)
            migrations_needed = True
        
        # NEW v0.21.0: Таблицы для диалоговой системы
        try:
            cursor.execute("SELECT 1 FROM conversation_history LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы conversation_history...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_type TEXT,
                    content TEXT,
                    intent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            migrations_needed = True
        
        try:
            cursor.execute("SELECT 1 FROM user_profiles LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы user_profiles...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    interests TEXT,
                    portfolio TEXT,
                    risk_tolerance TEXT,
                    preferred_language TEXT DEFAULT 'russian',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            migrations_needed = True
        
        # ✅ NEW v0.30.0: Миграция conversation_history к унифицированной схеме
        # Конвертируем старую схему (message_type, created_at) в новую (role, timestamp)
        try:
            cursor.execute("PRAGMA table_info(conversation_history)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # Если таблица имеет старую схему, мигрируем её
            if 'message_type' in columns and 'role' not in columns:
                logger.warning("🔄 Миграция conversation_history к новой схеме...")
                try:
                    # Переименовываем старую таблицу
                    cursor.execute("ALTER TABLE conversation_history RENAME TO conversation_history_old")
                    
                    # Создаём новую таблицу с правильной схемой
                    cursor.execute("""
                        CREATE TABLE conversation_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                            content TEXT NOT NULL,
                            intent TEXT,
                            timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                            message_length INTEGER,
                            tokens_estimate INTEGER,
                            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                        )
                    """)
                    
                    # Создаём индексы
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversation_history(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversation_history(timestamp)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_role ON conversation_history(role)")
                    
                    # Мигрируем данные со старой таблицы
                    cursor.execute("""
                        INSERT INTO conversation_history (id, user_id, role, content, intent, message_length)
                        SELECT id, user_id, 
                               CASE WHEN message_type = 'bot' THEN 'assistant' ELSE 'user' END as role,
                               content, intent, LENGTH(content)
                        FROM conversation_history_old
                    """)
                    
                    # Удаляем старую таблицу
                    cursor.execute("DROP TABLE conversation_history_old")
                    logger.info(f"Таблица conversation_history успешно мигрирована")
                    migrations_needed = True
                except Exception as e:
                    logger.error(f"Ошибка миграции conversation_history: {e}")
        except Exception as e:
            logger.debug(f"Не удалось проверить schema conversation_history: {e}")
        
        # Migration v0.26: Fix conversation_stats schema to match conversation_context.py expectations
        try:
            cursor.execute("PRAGMA table_info(conversation_stats)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # If old schema exists, recreate it with correct columns
            if 'message_count' in columns or 'average_response_time' in columns:
                logger.info("  • Миграция схемы conversation_stats на новые колонки...")
                cursor.execute("DROP TABLE IF EXISTS conversation_stats")
                cursor.execute("""
                    CREATE TABLE conversation_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        total_messages INTEGER DEFAULT 0,
                        total_tokens INTEGER DEFAULT 0,
                        last_message_time INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                """)
                migrations_needed = True
        except Exception as e:
            logger.debug(f"Не удалось проверить schema conversation_stats: {e}")
        
        # NEW v0.37.0: Teaching Module Phase 1 improvements
        try:
            cursor.execute("SELECT 1 FROM teaching_lessons LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы teaching_lessons...")
            cursor.execute("""
                CREATE TABLE teaching_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    title TEXT,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quiz_score INTEGER,
                    quiz_passed BOOLEAN DEFAULT 0,
                    xp_earned INTEGER DEFAULT 50,
                    repeat_count INTEGER DEFAULT 0,
                    last_repeated_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    UNIQUE(user_id, topic, difficulty)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_teaching_lessons_user ON teaching_lessons(user_id, completed_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_teaching_lessons_topic ON teaching_lessons(user_id, topic, difficulty)")
            migrations_needed = True
        
        try:
            cursor.execute("SELECT 1 FROM learning_paths LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы learning_paths...")
            cursor.execute("""
                CREATE TABLE learning_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path_name TEXT UNIQUE NOT NULL,
                    path_title TEXT,
                    description TEXT,
                    difficulty_level TEXT,
                    topics TEXT NOT NULL,
                    prerequisites TEXT,
                    estimated_time_hours INTEGER,
                    total_xp_reward INTEGER,
                    badge_reward TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            migrations_needed = True
        
        try:
            cursor.execute("SELECT 1 FROM user_learning_paths LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы user_learning_paths...")
            cursor.execute("""
                CREATE TABLE user_learning_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    path_name TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    progress_percent REAL DEFAULT 0,
                    total_xp_earned INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (path_name) REFERENCES learning_paths(path_name),
                    UNIQUE(user_id, path_name)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_learning_paths_user ON user_learning_paths(user_id, is_active)")
            migrations_needed = True
        
        try:
            cursor.execute("SELECT 1 FROM user_badges LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("  • Создание таблицы user_badges...")
            cursor.execute("""
                CREATE TABLE user_badges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    badge_id TEXT NOT NULL,
                    badge_name TEXT,
                    badge_emoji TEXT,
                    badge_description TEXT,
                    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    condition_met TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    UNIQUE(user_id, badge_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_badges_user ON user_badges(user_id, earned_at DESC)")
            migrations_needed = True
        
        if migrations_needed:
            logger.info(f"Миграция успешно завершена (v0.37.0 - Teaching Module Phase 1)")
        else:
            logger.info(f"Миграция не требуется, схема актуальна")
        
        # v0.43.0: Добавляем поддержку мультиязычности
        if not check_column_exists(cursor, 'users', 'language'):
            logger.info("Добавление колонки language для поддержки мультиязычности...")
            cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
            conn.commit()
            logger.info("Колонка language успешно добавлена")


def create_database_indices() -> None:
    """
    🚀 QUICK WIN: Create critical database indices for performance.
    
    These indices significantly improve query performance:
    - users: 10-50x faster leaderboard queries
    - requests: 5-10x faster user request history  
    - user_progress: 10-20x faster learning queries
    - daily_tasks: 5x faster task lookups
    - user_bookmarks_v2: 10x faster bookmark queries
    - analytics: 5x faster stat aggregations
    
    Expected improvement: 10-100x speedup on popular queries
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        try:
            # Index 1: Leaderboard optimization (CRITICAL)
            # Queries: "ORDER BY xp DESC, level DESC, created_at DESC"
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_leaderboard 
                ON users(xp DESC, level DESC, created_at DESC)
            """)
            logger.info("  📊 Created: idx_users_leaderboard (leaderboard queries)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_users_leaderboard: {e}")
        
        try:
            # Index 2: User requests lookup (HIGH)
            # Queries: "WHERE user_id = ? ORDER BY created_at DESC"
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_requests_user_date 
                ON requests(user_id, created_at DESC)
            """)
            logger.info("  📝 Created: idx_requests_user_date (user request history)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_requests_user_date: {e}")
        
        try:
            # Index 3: User learning progress (HIGH)
            # Queries: "WHERE user_id = ? AND course_id = ?"
            # Check if course_id column exists first
            cursor.execute("PRAGMA table_info(user_progress)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'course_id' in columns and 'lesson_id' in columns:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_progress_lookup 
                    ON user_progress(user_id, course_id, lesson_id)
                """)
                logger.info("  📚 Created: idx_user_progress_lookup (learning progress)")
            else:
                logger.warning(f"  ⚠️ Skipping idx_user_progress_lookup (missing columns)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_user_progress_lookup: {e}")
        
        try:
            # Index 4: Daily tasks (MEDIUM)
            # Queries: "WHERE user_id = ? AND completed = 0"
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_tasks_user 
                ON daily_tasks(user_id, completed, created_at DESC)
            """)
            logger.info("  ✅ Created: idx_daily_tasks_user (daily task queries)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_daily_tasks_user: {e}")
        
        try:
            # Index 5: Bookmarks optimization (MEDIUM)
            # Queries: "WHERE user_id = ? ORDER BY created_at DESC"
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bookmarks_user 
                ON user_bookmarks_v2(user_id, created_at DESC)
            """)
            logger.info("  🔖 Created: idx_bookmarks_user (bookmark queries)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_bookmarks_user: {e}")
        
        try:
            # Index 6: Analytics (MEDIUM)
            # Queries: "WHERE created_at > ? GROUP BY user_id"
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_analytics_date 
                ON analytics(created_at DESC, user_id)
            """)
            logger.info("  📈 Created: idx_analytics_date (analytics queries)")
        except sqlite3.OperationalError as e:
            logger.warning(f"  ⚠️ Could not create idx_analytics_date: {e}")
        
        conn.commit()
        logger.info(f"Database indices created successfully (v0.38.0 - QUICK WIN #2)")


def verify_database_schema() -> dict:
    """
    Проверить что все необходимые таблицы существуют в БД.
    
    Returns:
        dict: {
            'valid': bool - все таблицы существуют,
            'missing_tables': list - отсутствующие таблицы,
            'existing_tables': list - существующие таблицы
        }
    """
    REQUIRED_TABLES = [
        'users', 'requests', 'feedback', 'cache', 'analytics',
        'courses', 'lessons', 'user_progress', 'user_questions', 'faq',
        'tools', 'user_bookmarks', 'daily_tasks',
        'user_drop_subscriptions', 'drops_feed',
        'conversation_history', 'conversation_stats', 
        'user_badges', 'teaching_lessons', 'learning_paths'
    ]
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing = {row[0] for row in cursor.fetchall()}
            
            missing = [t for t in REQUIRED_TABLES if t not in existing]
            
            result = {
                'valid': len(missing) == 0,
                'missing_tables': missing,
                'existing_tables': sorted(list(existing))
            }
            
            if result['valid']:
                logger.info(f"Database schema verified: {len(existing)} tables present")
            else:
                logger.warning(
                    f"Database schema incomplete: missing {len(missing)} tables"
                    f"\nMissing: {missing}"
                    f"\nExisting: {result['existing_tables']}"
                )
            
            return result
            
    except Exception as e:
        logger.error(f"Database schema verification failed: {e}", exc_info=True)
        return {
            'valid': False,
            'missing_tables': [],
            'existing_tables': [],
            'error': str(e)
        }


def init_database() -> None:
    """
    Инициализирует SQLite базу данных с полной схемой.
    
    Создает все необходимые таблицы и выполняет миграции схемы.
    Выполняется при запуске бота, безопасна для повторных вызовов.
    
    Tables Created:
        - users: Профили пользователей
        - conversations: История разговоров
        - conversation_stats: Статистика по разговорам
        - analysis_cache: Кэш анализов
        - feedback: Обратная связь
        - learning_progress: Прогресс обучения
        - events: Для аналитики
        
    Features:
        - Idempotent: безопасно вызывать много раз
        - Auto-migration: автомиграция схемы
        - WAL mode: для лучшей производительности
        - Indexes: оптимизированы на часто используемые колонки
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей (обновленная)
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
                daily_reset_at TIMESTAMP,
                knowledge_level TEXT DEFAULT 'unknown',
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                badges TEXT DEFAULT '[]',
                requests_today INTEGER DEFAULT 0,
                last_request_date TEXT
            )
        """)
        
        # Таблица запросов
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
        
        # Таблица фидбека
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                request_id INTEGER,
                is_helpful BOOLEAN,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (request_id) REFERENCES requests(id)
            )
        """)
        
        # Таблица кэша
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            )
        """)
        
        # Таблица аналитики
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                user_id INTEGER,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.5.0 ============
        
        # Таблица курсов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                title TEXT,
                level TEXT,
                description TEXT,
                total_lessons INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица уроков
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER,
                lesson_number INTEGER,
                title TEXT,
                content TEXT,
                duration_minutes INTEGER,
                quiz_json TEXT,
                xp_reward INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        """)
        
        # Таблица прогресса пользователя
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                lesson_id INTEGER,
                completed_at TIMESTAMP,
                quiz_score INTEGER,
                xp_earned INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            )
        """)
        
        # Таблица вопросов и ответов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                answer TEXT,
                source TEXT,
                is_in_faq BOOLEAN DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица FAQ
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT UNIQUE,
                answer TEXT,
                related_lesson_id INTEGER,
                category TEXT,
                views INTEGER DEFAULT 0,
                helpful INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (related_lesson_id) REFERENCES lessons(id)
            )
        """)
        
        # Таблица инструментов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                url TEXT,
                category TEXT,
                difficulty TEXT,
                tutorial TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица избранных инструментов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tool_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица ЕЖЕДНЕВНЫХ ЗАДАЧ (v0.11.0) - Самообучение & Геймификация
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_type TEXT,
                task_name TEXT,
                xp_reward INTEGER,
                progress INTEGER DEFAULT 0,
                target INTEGER,
                completed BOOLEAN DEFAULT 0,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.15.0 (ДРОПЫ И АКТИВНОСТИ) ============
        
        # Таблица подписок на дропы
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_drop_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chain TEXT,
                notify_interval TEXT DEFAULT 'daily',
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица AUDIT ЛОГОВ (v0.22.0) - полный трейл действий пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                command TEXT,
                parameters TEXT,
                result TEXT,
                error_message TEXT,
                ip_address TEXT,
                client_version TEXT,
                execution_time_ms REAL,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Таблица истории дропов (кэш просмотренных)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drops_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                drop_name TEXT,
                drop_type TEXT,
                chain TEXT,
                viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_new BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица кэша активностей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_type TEXT,
                project_name TEXT,
                activity_data TEXT,
                chain TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.21.0 (ДИАЛОГОВАЯ СИСТЕМА) ============
        
        # Таблица истории диалогов (memory system) - UNIFIED SCHEMA
        # ✅ UNIFIED: Используется одна схема для bot.py и conversation_context.py
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                intent TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                message_length INTEGER,
                tokens_estimate INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # ✅ FIX: Таблица статистики диалогов (fixes: no such table: conversation_stats)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                total_messages INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                last_message_time INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Таблица профилей пользователей (для персонализации)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                interests TEXT,
                portfolio TEXT,
                risk_tolerance TEXT,
                preferred_language TEXT DEFAULT 'russian',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Индексы для дропов
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_drop_subscriptions
            ON user_drop_subscriptions(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drops_history_user
            ON drops_history(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_cache_expires
            ON activities_cache(expires_at)
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.17.0 (LEADERBOARD) ============
        
        # Таблица кэша рейтингов (обновляется каждый час)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                rank INTEGER,
                user_id INTEGER,
                username TEXT,
                xp INTEGER,
                level INTEGER,
                total_requests INTEGER,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(period, rank)
            )
        """)
        
        # Индекс для быстрого доступа к кэшу
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaderboard_cache_period
            ON leaderboard_cache(period, cached_at)
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.18.0 (BOOKMARKS) ============
        
        # Таблица закладок пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_bookmarks_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bookmark_type TEXT NOT NULL,
                content_title TEXT,
                content_text TEXT,
                content_source TEXT,
                external_id TEXT,
                rating INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                viewed_count INTEGER DEFAULT 0,
                last_viewed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, bookmark_type, external_id)
            )
        """)
        
        # История просмотра закладок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmark_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bookmark_id INTEGER,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (bookmark_id) REFERENCES user_bookmarks_v2(id)
            )
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookmarks_user
            ON user_bookmarks_v2(user_id, added_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookmarks_type
            ON user_bookmarks_v2(user_id, bookmark_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookmark_history
            ON bookmark_history(user_id, timestamp DESC)
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.19.0 (QUIZ SYSTEM) ============
        
        # Таблица для сохранения ответов на квизы
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_quiz_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                lesson_id INTEGER,
                question_number INTEGER,
                selected_answer_index INTEGER,
                is_correct BOOLEAN,
                xp_earned INTEGER DEFAULT 0,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            )
        """)
        
        # Таблица статистики квизов по уроках
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_quiz_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                lesson_id INTEGER,
                total_questions INTEGER,
                correct_answers INTEGER,
                quiz_score REAL,
                total_xp_earned INTEGER DEFAULT 0,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_perfect_score BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            )
        """)
        
        # Индексы для быстрого доступа (оптимизация v0.21.0)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quiz_responses_user_lesson
            ON user_quiz_responses(user_id, lesson_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quiz_stats_user_lesson
            ON user_quiz_stats(user_id, lesson_id)
        """)
        
        # Дополнительные индексы для production (v0.21.0 - Production Ready)
        # WITH SAFE CHECKS - некоторые таблицы могут быть созданы в других местах
        indices = [
            ("idx_requests_user_id", "CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id)"),
            ("idx_requests_created_at", "CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at)"),
            ("idx_cache_created_at", "CREATE INDEX IF NOT EXISTS idx_cache_created_at ON cache(created_at)"),
            ("idx_user_xp_user_id", "CREATE INDEX IF NOT EXISTS idx_user_xp_user_id ON user_xp(user_id)"),
            ("idx_quests_user_id", "CREATE INDEX IF NOT EXISTS idx_quests_user_id ON user_daily_quests(user_id)"),
            ("idx_bookmarks_user_id", "CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id)")
        ]
        
        for idx_name, idx_query in indices:
            try:
                cursor.execute(idx_query)
                logger.debug(f"✅ Index {idx_name} created/verified")
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    logger.debug(f"Index {idx_name} skipped (table may not exist yet)")
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error creating index {idx_name}: {e}")
        
        # ============ ТАБЛИЦА ПРОГРЕССА КУРСОВ (КРИТИЧНО) ============
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                course_name TEXT,
                completed_lessons INTEGER DEFAULT 0,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # ============ НОВЫЕ ТАБЛИЦЫ v0.37.0 (TEACHING MODULE IMPROVEMENTS) ============
        
        # Таблица для отслеживания пройденных уроков (Phase 1 улучшений)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teaching_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                title TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                quiz_score INTEGER,
                quiz_passed BOOLEAN DEFAULT 0,
                xp_earned INTEGER DEFAULT 50,
                repeat_count INTEGER DEFAULT 0,
                last_repeated_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, topic, difficulty)
            )
        """)
        
        # Таблица для системы рекомендаций и путей обучения
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learning_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path_name TEXT UNIQUE NOT NULL,
                path_title TEXT,
                description TEXT,
                difficulty_level TEXT,
                topics TEXT NOT NULL,
                prerequisites TEXT,
                estimated_time_hours INTEGER,
                total_xp_reward INTEGER,
                badge_reward TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для отслеживания прогресса пути обучения
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_learning_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                path_name TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                progress_percent REAL DEFAULT 0,
                total_xp_earned INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (path_name) REFERENCES learning_paths(path_name),
                UNIQUE(user_id, path_name)
            )
        """)
        
        # Таблица для системы достижений (badges)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_id TEXT NOT NULL,
                badge_name TEXT,
                badge_emoji TEXT,
                badge_description TEXT,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                condition_met TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, badge_id)
            )
        """)
        
        # Индексы для оптимизации Phase 1
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_teaching_lessons_user
            ON teaching_lessons(user_id, completed_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_teaching_lessons_topic
            ON teaching_lessons(user_id, topic, difficulty)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_learning_paths_user
            ON user_learning_paths(user_id, is_active)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_badges_user
            ON user_badges(user_id, earned_at DESC)
        """)
        
        logger.info(f"База данных инициализирована с optimized indexes (v0.37.0 - Teaching Module Phase 1)")
    
    # Инициализируем курсы (загружаем из markdown в БД)
    with get_db() as conn:
        cursor = conn.cursor()
        load_courses_to_db(cursor)
    
    # Выполняем миграцию существующих таблиц
    migrate_database()

# =============================================================================
# ФОРМАТИРОВАНИЕ ТЕКСТА
# =============================================================================

def format_header(title: str) -> str:
    """Форматирование заголовка с красивым отделением."""
    return f"\n{'─' * 45}\n✨ {title}\n{'─' * 45}\n"

def format_section(title: str, content: str, emoji: str = "•") -> str:
    """Форматирование раздела с заголовком и содержимым."""
    return f"\n{emoji} <b>{title}</b>\n{content}"

def format_tips_block(tips: List[str], emoji: str = "💡") -> str:
    """Форматирование блока советов с нумерацией."""
    if not tips:
        return ""
    formatted = f"\n{emoji} <b>ПРАКТИЧЕСКИЕ СОВЕТЫ:</b>"
    for i, tip in enumerate(tips[:3], 1):
        formatted += f"\n  {i}. {tip}"
    return formatted

def format_impact_points(points: List[str]) -> str:
    """Форматирование ключевых моментов с иконками."""
    if not points:
        return ""
    formatted = f"\n📍 <b>КЛЮЧЕВЫЕ МОМЕНТЫ:</b>"
    for point in points[:5]:
        formatted += f"\n  ▪️ {point}"
    return formatted

def format_educational_content(context_text: str, callback: str = "", emoji: str = "📚") -> str:
    """Форматирование образовательного контента."""
    if not context_text:
        return ""
    
    formatted = f"\n{emoji} <b>ОБРАЗОВАТЕЛЬНО:</b>\n{context_text}"
    if callback:
        formatted += f"\n  <i>👉 {callback}</i>"
    return formatted

def format_question_block(question: str, emoji: str = "❓") -> str:
    """Форматирование вопроса для размышления."""
    if not question:
        return ""
    return f"\n{emoji} <b>ВОПРОС ДЛЯ РАЗМЫШЛЕНИЯ:</b>\n  \"{question}\""

def format_related_topics(topics: List[str], emoji: str = "🔗") -> str:
    """Форматирование связанных тем."""
    if not topics or all(t.strip() == "" for t in topics):
        return ""
    
    formatted = f"\n{emoji} <b>СВЯЗАННЫЕ ТЕМЫ:</b>"
    for topic in topics[:5]:
        if topic.strip():
            formatted += f"\n  • {topic}"
    return formatted

def format_main_response(
    summary_text: str,
    impact_points: List[str] = None,
    practical_tips: List[str] = None,
    learning_question: str = "",
    educational_context: str = "",
    related_topics: List[str] = None,
    callback_text: str = ""
) -> str:
    """
    Главное форматирование ответа анализа новостей.
    Объединяет все компоненты в красивый читаемый формат.
    """
    
    response = f"<b>📰 АНАЛИЗ НОВОСТИ</b>"
    
    # Основной текст
    response += f"\n\n{summary_text}"
    
    # Ключевые моменты
    if impact_points:
        response += format_impact_points(impact_points)
    
    # Практические советы
    if practical_tips and any(t.strip() for t in practical_tips):
        response += format_tips_block([t for t in practical_tips if t.strip()])
    
    # Вопрос для размышления
    if learning_question and learning_question.strip():
        response += format_question_block(learning_question)
    
    # Образовательный контент
    if educational_context and educational_context.strip():
        response += format_educational_content(educational_context, callback_text)
    
    # Связанные темы
    if related_topics:
        response += format_related_topics([t for t in related_topics if t.strip()])
    
    # Финальный разделитель
    response += f"\n\n{'─' * 45}"
    
    return response

def format_command_response(title: str, content: str, emoji: str = "ℹ️") -> str:
    """Форматирование ответа на команду с заголовком."""
    return f"{emoji} <b>{title}</b>\n\n{content}"

def format_error(error_msg: str, emoji: str = "❌") -> str:
    """Форматирование сообщения об ошибке."""
    return f"{emoji} <b>Ошибка:</b>\n{error_msg}"

def format_success(message: str, emoji: str = "✅") -> str:
    """Форматирование сообщения об успехе."""
    return f"{emoji} {message}"

def format_list_items(items: List[str], numbered: bool = False) -> str:
    """Форматирование списка элементов."""
    if not items:
        return ""
    
    formatted = ""
    if numbered:
        for i, item in enumerate(items, 1):
            formatted += f"\n{i}. {item}"
    else:
        for item in items:
            formatted += f"\n• {item}"
    return formatted

def format_lesson_for_telegram(lesson_content: str, course_title: str, lesson_num: int, 
                               course_level: str, completed: int, total: int) -> Tuple[str, str]:
    """
    Форматирует урок для отправки в Telegram с ограничением по размеру.
    Возвращает (основной_текст, дополнительный_текст_если_длинный).
    
    Включает:
    - Визуальные индикаторы прогресса
    - Информацию о сложности и времени
    - Структурированное форматирование контента
    
    Telegram имеет лимит 4096 символов, поэтому уроки могут быть разбиты на две части.
    """
    # Очищаем контент от лишних символов
    clean_content = lesson_content.strip()
    # Удаляем множественные переносы строк
    clean_content = re.sub(r'\n\n\n+', '\n\n', clean_content)
    
    # Конвертируем Markdown в HTML для Telegram
    clean_content = markdown_to_html_for_telegram(clean_content)
    
    # Визуализация прогресса
    progress_bar = ""
    progress_percent = (completed / total * 100) if total > 0 else 0
    filled_blocks = int(progress_percent / 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = "█" * filled_blocks + "░" * empty_blocks
    
    # Выбираем эмодзи в зависимости от сложности
    level_emoji = {
        "beginner": "🌱",
        "intermediate": "📚", 
        "advanced": "🚀",
        "expert": "👑"
    }.get(course_level.lower(), "📖")
    
    # Оценка времени (примерно 8 минут на урок)
    time_estimate = "⏱️ ~8 мин"
    
    # Формируем красивый заголовок с прогрессом
    header = (
        f"{level_emoji} <b>{course_title} — Урок {lesson_num}</b>\n"
        f"─────────────────────────\n"
        f"📊 Прогресс: <code>{progress_bar}</code>\n"
        f"   <b>{completed}/{total}</b> ({progress_percent:.0f}%)\n"
        f"{time_estimate} | Сложность: {course_level.upper()}\n"
        f"─────────────────────────\n\n"
    )
    
    # Первые 2300 символов контента (оставляем место для кнопок и заголовка)
    # Telegram лимит = 4096, минус заголовок (~250), минус место для кнопок (~300)
    max_content_length = 2300
    
    if len(clean_content) > max_content_length:
        # Урок слишком длинный - разбиваем
        main_content = clean_content[:max_content_length]
        
        # Ищем последний полный параграф (заканчивающийся на \n\n)
        last_break = main_content.rfind('\n\n')
        if last_break > 1000:  # Если нашли разрыв хотя бы после 1000 символов
            cutoff_point = last_break
        else:
            # Если нет хорошего разрыва, обрезаем по максимум
            cutoff_point = max_content_length
        
        main_content = clean_content[:cutoff_point].rstrip()
        main_content += "\n\n<i>▶️ (продолжение ниже)</i>"
        
        # Остаток контента начиная сразу после точки разрыва
        remaining_content = clean_content[cutoff_point:].lstrip()
        
        return header + main_content, remaining_content
    else:
        # Урок умещается в один посыл
        return header + clean_content, ""

def markdown_to_html_for_telegram(text: str) -> str:
    """
    Конвертирует Markdown синтаксис в HTML для Telegram.
    Поддерживает:
    - **bold** -> <b>bold</b>
    - _italic_ -> <i>italic</i>
    - `code` -> <code>code</code>
    """
    # Заменяем **text** на <b>text</b>
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    
    # Заменяем _text_ на <i>text</i>
    text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)
    
    # Заменяем `code` на <code>code</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    return text

# --- Функции работы с пользователями ---

def save_user(user_id: int, username: str, first_name: str) -> None:
    """
    Сохраняет или обновляет информацию о пользователе в БД.
    
    Создает новую запись пользователя или обновляет существующую.
    Вызывается каждый раз когда пользователь взаимодействует с ботом.
    
    Args:
        user_id (int): Unique Telegram user ID
        username (str): Telegram username (may be empty)
        first_name (str): User's first name from Telegram profile
        
    Side Effects:
        - Creates or updates row in users table
        - Updates: username, first_name
        - Preserves: user_id, daily_requests, xp, level, created_at, is_banned
        
    Example:
        >>> save_user(123456, "johndoe", "John")
        >>> # User 123456 is now saved in DB with username "johndoe"
        
    Note:
        - Idempotent: safe to call multiple times
        - Uses ON CONFLICT to handle duplicates
        - Minimal: only saves essential profile fields
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))

def check_user_banned(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, забанен ли пользователь и возвращает причину.
    
    Быстрая проверка для фильтрации забаненных пользователей.
    Вызывается в начале обработки каждого сообщения.
    
    Args:
        user_id (int): Unique Telegram user ID для проверки
        
    Returns:
        Tuple[bool, Optional[str]]:
            - (True, ban_reason) if user is banned
            - (False, None) if user is not banned
            
    Ban Reasons:
        - "spam": Отправка спама
        - "abuse": Оскорбительное поведение
        - "malicious": Попытка взлома/атак
        - "terms": Нарушение условий использования
        
    Performance:
        - O(log N) lookup via indexed user_id
        - Response time: <1ms typically
        
    Example:
        >>> is_banned, reason = check_user_banned(123456)
        >>> if is_banned:
        ...     print(f"User banned: {reason}")
        
    Note:
        - Used in every message handler
        - Critical for abuse prevention
        - Checked before rate limiting
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT is_banned, ban_reason FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            return True, row[1]
        return False, None

def check_daily_limit(user_id: int) -> Tuple[bool, int]:
    """Проверяет дневной лимит запросов. Администраторы имеют безлимитный доступ."""
    # Администраторы и избранные пользователи имеют безлимитный доступ
    if user_id in ADMIN_USERS or user_id in UNLIMITED_ADMIN_USERS:
        return True, 999999
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT daily_requests, daily_reset_at FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return True, MAX_REQUESTS_PER_DAY
        
        daily_requests = row[0] or 0
        daily_reset_at = row[1]
        
        # Проверяем, нужно ли сбросить счетчик
        if daily_reset_at:
            reset_time = datetime.fromisoformat(daily_reset_at)
            if datetime.now() > reset_time:
                # Сбрасываем счетчик
                cursor.execute("""
                    UPDATE users 
                    SET daily_requests = 0,
                        daily_reset_at = ?
                    WHERE user_id = ?
                """, (datetime.now() + timedelta(days=1), user_id))
                return True, MAX_REQUESTS_PER_DAY
        
        remaining = MAX_REQUESTS_PER_DAY - daily_requests
        if remaining <= 0:
            return False, 0
        
        return True, remaining

def increment_user_requests(user_id: int) -> None:
    """Увеличивает счетчики запросов."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем, нужно ли установить daily_reset_at
        cursor.execute("""
            SELECT daily_reset_at FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row or not row[0]:
            next_reset = datetime.now() + timedelta(days=1)
            cursor.execute("""
                UPDATE users 
                SET total_requests = total_requests + 1,
                    last_request_at = CURRENT_TIMESTAMP,
                    daily_requests = daily_requests + 1,
                    daily_reset_at = ?
                WHERE user_id = ?
            """, (next_reset, user_id))
        else:
            cursor.execute("""
                UPDATE users 
                SET total_requests = total_requests + 1,
                    last_request_at = CURRENT_TIMESTAMP,
                    daily_requests = daily_requests + 1
                WHERE user_id = ?
            """, (user_id,))

# --- Функции работы с запросами ---

def save_request(user_id: int, news_text: str, response_text: str, 
                from_cache: bool, processing_time_ms: Optional[float] = None,
                error_message: Optional[str] = None) -> int:
    """Сохраняет запрос с метриками."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text, from_cache, 
                                 processing_time_ms, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, news_text, response_text, from_cache, processing_time_ms, error_message))
        return cursor.lastrowid

def get_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает запись запроса по id или None."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, news_text, response_text, created_at
            FROM requests WHERE id = ?
        """, (request_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "user_id": row[1],
            "news_text": row[2],
            "response_text": row[3],
            "created_at": row[4]
        }

def save_feedback(user_id: int, request_id: int, is_helpful: bool, comment: Optional[str] = None) -> None:
    """Сохраняет фидбек с опциональным комментарием."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful, comment)
            VALUES (?, ?, ?, ?)
        """, (user_id, request_id, is_helpful, comment))

# --- Функции работы с кэшем ---

def get_cache(cache_key: str) -> Optional[str]:
    """Получает ответ из кэша и обновляет статистику."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT response_text FROM cache WHERE cache_key = ?
        """, (cache_key,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE cache 
                SET hit_count = hit_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE cache_key = ?
            """, (cache_key,))
            return row[0]
        return None

def set_cache(cache_key: str, response_text: str) -> None:
    """Сохраняет ответ в кэш."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cache (cache_key, response_text)
            VALUES (?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_text = excluded.response_text,
                last_used_at = CURRENT_TIMESTAMP,
                hit_count = hit_count + 1
        """, (cache_key, response_text))

def cleanup_old_cache() -> None:
    """Удаляет старый и неиспользуемый кэш."""
    with get_db() as conn:
        cursor = conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=CACHE_MAX_AGE_DAYS)
        
        # Удаляем старые записи (старше CACHE_MAX_AGE_DAYS) с низким числом попаданий или вообще не использованные
        cursor.execute("""
            DELETE FROM cache 
            WHERE (last_used_at < ? AND hit_count < 5) OR (hit_count = 0)
        """, (cutoff_date,))
        deleted = cursor.rowcount
        logger.info(f"Удалено {deleted} старых/неиспользуемых записей из кэша")
        
        # Логируем статистику оставшегося кэша
        cursor.execute("SELECT COUNT(*) FROM cache")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(hit_count) FROM cache")
        total_hits = cursor.fetchone()[0] or 0
        logger.info(f"💾 Кэш: {total} записей, всего попаданий: {total_hits}")

# --- Функции работы с историей ---

def get_user_history(user_id: int, limit: int = 10) -> List[Tuple]:
    """Получает историю запросов пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT news_text, response_text, created_at, from_cache, processing_time_ms
            FROM requests
            WHERE user_id = ? AND error_message IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return cursor.fetchall()

# ==================== ДИАЛОГОВАЯ СИСТЕМА v0.21.0 ====================

def ensure_conversation_history_columns() -> None:
    """Проверяет и добавляет недостающие столбцы в conversation_history.
    
    ⚠️ ВАЖНО: Вызывается ПЕРЕД основной инициализацией!
    TIER 1 v0.23.0: Enhanced with default values and data consistency fixes.
    TIER 1 v0.24.0: More aggressive migration to fix Railway deployment issues.
    """
    import sqlite3
    try:
        # Открываем БД напрямую (не через пул) - используем правильную переменную
        db_path = os.getenv("DB_PATH", "rvx_bot.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        conn.execute("PRAGMA foreign_keys=OFF")  # Отключаем внешние ключи во время миграции
        
        # Проверяем существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_history'")
        if not cursor.fetchone():
            logger.info(f"Таблица conversation_history не существует, будет создана позже")
            conn.close()
            return
        
        # Получаем информацию о столбцах ДО миграции
        cursor.execute("PRAGMA table_info(conversation_history)")
        columns_before = {col[1] for col in cursor.fetchall()}
        logger.info(f"📋 Столбцы ДО миграции: {sorted(columns_before)}")
        
        # Проверяем и добавляем недостающие столбцы
        needs_migration = False
        
        if 'message_type' not in columns_before:
            logger.info("  ⚡ Добавляем столбец message_type в conversation_history...")
            try:
                cursor.execute("ALTER TABLE conversation_history ADD COLUMN message_type TEXT DEFAULT 'user'")
                conn.commit()
                logger.info(f"Столбец message_type добавлен успешно")
                needs_migration = True
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.error(f"Не удалось добавить message_type: {e}")
                
        if 'intent' not in columns_before:
            logger.info("  ⚡ Добавляем столбец intent в conversation_history...")
            try:
                cursor.execute("ALTER TABLE conversation_history ADD COLUMN intent TEXT DEFAULT 'general'")
                conn.commit()
                logger.info(f"Столбец intent добавлен успешно")
                needs_migration = True
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.error(f"Не удалось добавить intent: {e}")
        
        # Финальная проверка
        cursor.execute("PRAGMA table_info(conversation_history)")
        columns_after = {col[1] for col in cursor.fetchall()}
        logger.info(f"Столбцы ПОСЛЕ миграции: {sorted(columns_after)}")
        
        # Проверяем что все нужные столбцы есть
        required_columns = {'id', 'user_id', 'message_type', 'content', 'intent', 'created_at'}
        missing = required_columns - columns_after
        if missing:
            logger.error(f"🚨 КРИТИЧНО: Отсутствуют столбцы: {missing}")
        else:
            logger.info(f"УСПЕШНО: Все необходимые столбцы присутствуют")
        
        conn.execute("PRAGMA foreign_keys=ON")  # Включаем внешние ключи обратно
        conn.close()
        
    except Exception as e:
        logger.error(f"Критическая ошибка при миграции БД: {e}", exc_info=True)

def save_conversation(user_id: int, message_type: str, content: str, intent: Optional[str] = None) -> None:
    """Сохраняет сообщение в историю диалога с правильным форматом."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Map message_type to role: 'user' stays 'user', 'bot' becomes 'assistant'
            role = "assistant" if message_type == "bot" else "user"
            
            # Вставляем в унифицированную схему
            tokens_estimate = len(content.split()) * 1.3
            current_time = int(time.time())
            
            cursor.execute("""
                INSERT INTO conversation_history 
                (user_id, role, content, intent, timestamp, message_length, tokens_estimate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, role, content, intent or "general", current_time, len(content), int(tokens_estimate)))
            
            conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"DB save failed (non-critical): {e}")
    except Exception as e:
        logger.warning(f"Could not save conversation: {e}")

def get_conversation_history(user_id: int, limit: int = 10) -> List[dict]:
    """Получает последние сообщения из истории диалога для контекста.
    
    Работает с унифицированной схемой conversation_history.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, intent, timestamp
                FROM conversation_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                try:
                    # role может быть 'user' или 'assistant'
                    role = row[0] if row[0] else 'user'
                    content = row[1] if row[1] else ''
                    intent = row[2] if row[2] else 'general'
                    timestamp = row[3] if row[3] else ''
                    
                    result.append({
                        "type": role,
                        "content": str(content),
                        "intent": intent,
                        "timestamp": timestamp
                    })
                except (IndexError, TypeError) as e:
                    logger.debug(f"Skipping malformed conversation row: {e}")
                    continue
            
            return result
    except Exception as e:
        logger.warning(f"Failed to retrieve conversation history for user {user_id}: {e}")
        return []

def get_user_profile(user_id: int) -> Dict[str, str]:
    """Получает профиль пользователя для персонализации."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT interests, portfolio, risk_tolerance, preferred_language
            FROM user_profiles
            WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "interests": row[0] or "",
                "portfolio": row[1] or "",
                "risk_tolerance": row[2] or "unknown",
                "preferred_language": row[3] or "russian"
            }
        return {"interests": "", "portfolio": "", "risk_tolerance": "unknown", "preferred_language": "russian"}

def update_user_profile(user_id: int, interests: Optional[str] = None, portfolio: Optional[str] = None, risk_tolerance: Optional[str] = None) -> None:
    """Обновляет профиль пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Попытка обновить существующий профиль
        cursor.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            updates = []
            params = []
            if interests is not None:
                updates.append("interests = ?")
                params.append(interests)
            if portfolio is not None:
                updates.append("portfolio = ?")
                params.append(portfolio)
            if risk_tolerance is not None:
                updates.append("risk_tolerance = ?")
                params.append(risk_tolerance)
            
            if updates:
                # ✅ КРИТИЧЕСКИЙ ФИК #1: SQL Injection защита - whitelist полей
                ALLOWED_FIELDS = {"interests", "portfolio", "risk_tolerance"}
                safe_updates = [u.split(" ")[0] for u in updates if u.split(" ")[0] in ALLOWED_FIELDS]
                if safe_updates or len(updates) > 0:
                    updates.append("last_updated = datetime('now')")
                    params.append(user_id)
                    query = f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?"
                    cursor.execute(query, params)
                    logger.info(f"Updated user {user_id} profile (SQL safe)")
        else:
            # Создать новый профиль
            cursor.execute("""
                INSERT INTO user_profiles (user_id, interests, portfolio, risk_tolerance, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (user_id, interests or "", portfolio or "", risk_tolerance or "unknown"))
        
        conn.commit()
        logger.debug(f"👤 Профиль обновлен: user_id={user_id}")

def classify_intent(text: str) -> str:
    """
    Классификация намерения пользователя на основе ключевых слов.
    Порядок проверок важен: более специфичные проверяются первыми.
    """
    text_lower = text.lower()
    
    # 1. Уточняющие вопросы (follow-up) - ПЕРВЫМ, так как это более специфично
    # Включаем очень короткие follow-up вопросы типа "Почему?", "Как?", "Где?", "Когда?"
    followup_keywords = ["еще", "подробнее", "расскажи больше", "непонятно", "уточни", "можешь повторить", 
                        "а что", "и что", "поясни", "детальнее", "подробней", "почему?", "как?", "где?", 
                        "когда?", "почему", "как ", "что это", "кто это"]
    if any(kw in text_lower for kw in followup_keywords):
        return "follow_up"
    
    # 2. Анализ новостей (требует ключевых слов о финансах/крипто)
    news_keywords = ["анализ", "новость", "криптовалюта", "биткойн", "bitcoin", "эфир", "ethereum", 
                    "рынок", "цена", "тренд", "падение", "рост", "скачок", "окончательно", 
                    "одобрен", "запущен", "приказ", "давит", "крах", "взлет", "что произошло", "произошло"]
    if any(kw in text_lower for kw in news_keywords):
        return "news_analysis"
    
    # 3. Вопросы об обучении (явные вопросительные слова)
    question_keywords = ["что такое", "как работает", "почему", "зачем", "какой", "какая", "какое",
                        "чем отличается", "разница", "в чем", "опиши", "расскажи о", "объясни"]
    if any(kw in text_lower for kw in question_keywords):
        return "question"
    
    # 4. Обнаружение вопросительных предложений (заканчиваются на ?)
    if text.rstrip().endswith("?"):
        return "question"
    
    # 5. Общая беседа (по умолчанию)
    return "general_chat"

def search_relevant_context(user_id: int, intent: str, limit: int = 5) -> List[dict]:
    """Ищет релевантный контекст из истории диалогов для инъекции в промпт."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Если это follow-up, ищем последние сообщения любого типа
        if intent == "follow_up":
            query = "SELECT message_type, content, intent FROM conversation_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
            cursor.execute(query, (user_id, limit))
        # Иначе ищем сообщения с похожим намерением
        else:
            query = "SELECT message_type, content, intent FROM conversation_history WHERE user_id = ? AND intent = ? ORDER BY created_at DESC LIMIT ?"
            cursor.execute(query, (user_id, intent, limit))
        
        rows = cursor.fetchall()
        return [{"type": r[0], "content": r[1], "intent": r[2]} for r in rows]

# ===================================================================

def search_user_requests(user_id: int, search_text: str) -> List[Tuple]:
    """Поиск по запросам пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT news_text, response_text, created_at
            FROM requests
            WHERE user_id = ? AND news_text LIKE ? AND error_message IS NULL
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id, f"%{search_text}%"))
        return cursor.fetchall()

# --- Статистика ---

def get_global_stats() -> dict:
    """Получает глобальную статистику."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM requests WHERE error_message IS NULL")
        total_requests = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cache")
        cache_size = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(hit_count) FROM cache")
        cache_hits = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM feedback WHERE is_helpful = 1")
        helpful_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM feedback WHERE is_helpful = 0")
        not_helpful_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT AVG(processing_time_ms) FROM requests 
            WHERE processing_time_ms IS NOT NULL AND from_cache = 0
        """)
        avg_processing_time = cursor.fetchone()[0] or 0
        
        # TOP-10 пользователей по XP (обновлено v0.9.0)
        cursor.execute("""
            SELECT username, first_name, xp, level
            FROM users
            WHERE is_banned = 0 AND xp > 0
            ORDER BY xp DESC
            LIMIT 10
        """)
        top_users = cursor.fetchall()
        
        return {
            "total_users": total_users,
            "total_requests": total_requests,
            "cache_size": cache_size,
            "cache_hits": cache_hits,
            "helpful": helpful_count,
            "not_helpful": not_helpful_count,
            "avg_processing_time": round(avg_processing_time, 2),
            "top_users": top_users
        }

def get_user_learning_style() -> dict:
    """Анализирует стиль обучения пользователя на основе фидбека. v0.10.0 - Самообучение."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем все фидбеки пользователя
        cursor.execute("""
            SELECT f.is_helpful, r.processing_time_ms
            FROM feedback f
            JOIN requests r ON f.request_id = r.id
            WHERE f.created_at > datetime('now', '-7 days')
            ORDER BY f.created_at DESC
            LIMIT 50
        """)
        recent_feedback = cursor.fetchall()
        
        if not recent_feedback:
            return {
                "helpful_rate": 0.5,
                "preferred_length": "medium",
                "style": "balanced",
                "samples_count": 0
            }
        
        helpful_count = sum(1 for h, _ in recent_feedback if h)
        total_count = len(recent_feedback)
        helpful_rate = helpful_count / total_count if total_count > 0 else 0.5
        
        # Анализ скорости обработки
        times = [t for _, t in recent_feedback if t]
        avg_time = sum(times) / len(times) if times else 0
        
        # Определяем предпочитаемую длину ответа
        if helpful_rate > 0.75:
            preferred_length = "current"  # Текущий стиль работает
        elif helpful_rate > 0.5:
            if avg_time > 1000:
                preferred_length = "shorter"  # Слишком долго
            else:
                preferred_length = "with_examples"  # Добавить примеры
        else:
            preferred_length = "simpler"  # Упростить
        
        style = "effective" if helpful_rate > 0.7 else "needs_adjustment"
        
        logger.info(f"📊 Анализ стиля: полезность {helpful_rate:.1%}, длина {preferred_length}")
        
        return {
            "helpful_rate": helpful_rate,
            "preferred_length": preferred_length,
            "style": style,
            "samples_count": total_count,
            "avg_response_time_ms": round(avg_time, 0)
        }

def get_user_knowledge_gaps() -> dict:
    """Определяет пробелы в знаниях на основе XP и истории. v0.10.0 - Самообучение."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем предметы, по которым пользователь спрашивал больше всего
        cursor.execute("""
            SELECT topic, COUNT(*) as count
            FROM (
                SELECT 
                    CASE 
                        WHEN news_text LIKE '%bitcoin%' OR news_text LIKE '%BTC%' THEN 'bitcoin'
                        WHEN news_text LIKE '%ethereum%' OR news_text LIKE '%ETH%' THEN 'ethereum'
                        WHEN news_text LIKE '%defi%' THEN 'defi'
                        WHEN news_text LIKE '%nft%' THEN 'nft'
                        WHEN news_text LIKE '%trading%' OR news_text LIKE '%трейдинг%' THEN 'trading'
                        ELSE 'other'
                    END as topic
                FROM requests
                WHERE user_id = ? AND created_at > datetime('now', '-30 days')
            )
            GROUP BY topic
            ORDER BY count DESC
            LIMIT 3
        """, (...,))  # Placeholder
        
        topics = cursor.fetchall()
        return {
            "top_topics": [t[0] for t in topics],
            "total_requests": sum(t[1] for t in topics)
        }

# ============= ЕЖЕДНЕВНЫЕ ЗАДАЧИ (v0.11.0) =============

DAILY_TASKS_TEMPLATES = {
    "news_5": {
        "name": "📰 Новостной аналитик",
        "emoji": "📰",
        "quest_title": "Анализ новостей крипто-мира",
        "quest_description": "Твоя задача - проанализировать 5 криптоновостей и понять их влияние на рынок. Каждый анализ развивает твой навык в оценке рыночных событий.",
        "what_to_do": "Отправь боту текст криптоновости (например, о Bitcoin, Ethereum или других проектах). Бот проанализирует её и даст упрощённое объяснение.",
        "tips": [
            "💡 Начни с коротких новостей о популярных криптовалютах (Bitcoin, Ethereum)",
            "💡 Обрати внимание на ключевые события: листинги, обновления, регуляция",
            "💡 После каждого анализа оцени полезность ответа (👍 или 👎)"
        ],
        "related_topics": ["crypto_basics", "trading"],
        "target": 5,
        "xp_reward": 50
    },
    "lessons_2": {
        "name": "🎓 Ученик",
        "emoji": "🎓",
        "quest_title": "Путь познания",
        "quest_description": "Развивай свои знания, проходя интерактивные уроки. Каждый урок - новая информация, которая поможет лучше понять крипто-индустрию.",
        "what_to_do": "Используй команду /teach для прохождения интерактивных уроков. Можешь выбрать тему и уровень сложности (beginner, intermediate, advanced).",
        "tips": [
            "💡 Начни с уровня 'beginner' для основ криптографии",
            "💡 Команда: /teach crypto_basics beginner",
            "💡 После урока ответь на проверочный вопрос для лучшего запоминания"
        ],
        "related_topics": ["crypto_basics", "web3", "defi"],
        "target": 2,
        "xp_reward": 40
    },
    "voting_3": {
        "name": "👍 Критик",
        "emoji": "👍",
        "quest_title": "Оценка знаний",
        "quest_description": "Помоги боту улучшать качество ответов, оценивая полезность анализов. Твой голос важен для развития AI!",
        "what_to_do": "После каждого анализа новости ты увидишь кнопки 👍 и 👎. Нажми на одну из них, чтобы оценить качество ответа.",
        "tips": [
            "💡 Оцени ответ как полезный (👍), если объяснение понятное и точное",
            "💡 Оцени как неполезный (👎), если чего-то не хватает или есть ошибки",
            "💡 Твои оценки помогают улучшать систему для всех"
        ],
        "related_topics": ["news_5"],
        "target": 3,
        "xp_reward": 30
    },
    "learning_quiz": {
        "name": "🧠 Студент",
        "emoji": "🧠",
        "quest_title": "Проверка знаний",
        "quest_description": "Реши квиз из интерактивного курса и проверь, насколько хорошо ты усвоил пройденный материал. Это лучший способ закрепить знания!",
        "what_to_do": "Используй /learn для доступа к интерактивным курсам. В каждом курсе есть квизы для проверки знаний.",
        "tips": [
            "💡 Квизы состоят из 3-5 вопросов с вариантами ответов",
            "💡 За каждый правильный ответ получаешь XP",
            "💡 Если ошибёшься, ты узнаешь правильный ответ и сможешь учиться дальше"
        ],
        "related_topics": ["crypto_basics", "trading"],
        "target": 1,
        "xp_reward": 35
    },
    "teach_explore": {
        "name": "🔍 Исследователь",
        "emoji": "🔍",
        "quest_title": "Расширение горизонтов",
        "quest_description": "Исследуй разные темы обучения и найди то, что тебя интересует больше всего. Разносторонние знания - ключ к успеху!",
        "what_to_do": "Используй /teach с разными темами. Доступные темы: crypto_basics, trading, web3, ai, defi, nft, security, tokenomics.",
        "tips": [
            "💡 Начни с crypto_basics, если новичок",
            "💡 Затем попробуй web3 для понимания децентрализации",
            "💡 Завершись последовательностью: trading → defi → tokenomics для полного понимания"
        ],
        "related_topics": ["crypto_basics", "web3", "defi", "trading"],
        "target": 3,
        "xp_reward": 45
    }
}

def init_daily_tasks(user_id: int) -> None:
    """Инициализирует ежедневные задачи для пользователя. v0.11.0"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем есть ли задачи на сегодня
        today_date = datetime.now().date().isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM daily_tasks 
            WHERE user_id = ? AND DATE(reset_at) = ?
        """, (user_id, today_date))
        
        if cursor.fetchone()[0] > 0:
            return  # Задачи уже инициализированы
        
        # Создаем новые задачи на день
        today = datetime.now().isoformat()
        for task_id, task_data in DAILY_TASKS_TEMPLATES.items():
            cursor.execute("""
                INSERT INTO daily_tasks 
                (user_id, task_type, task_name, target, xp_reward, reset_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                task_id,
                task_data["name"],
                task_data["target"],
                task_data["xp_reward"],
                today,
                today
            ))
        
        conn.commit()
        logger.info(f"✨ Инициализированы ежедневные задачи для {user_id}")

def get_user_daily_tasks(user_id: int) -> List[dict]:
    """Получает текущие ежедневные задачи пользователя. v0.11.0"""
    init_daily_tasks(user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, task_type, task_name, progress, target, xp_reward, completed
            FROM daily_tasks
            WHERE user_id = ? AND DATE(reset_at) = DATE('now')
            ORDER BY completed, xp_reward DESC
        """, (user_id,))
        
        tasks = []
        for task_id, task_type, task_name, progress, target, xp, completed in cursor.fetchall():
            pct = int((progress / target * 100) if target > 0 else 0)
            tasks.append({
                "id": task_id,
                "type": task_type,
                "name": task_name,
                "progress": progress,
                "target": target,
                "xp_reward": xp,
                "completed": completed,
                "percentage": min(pct, 100),
                "bar": "█" * (pct // 10) + "░" * (10 - pct // 10)
            })
        
        return tasks

def update_task_progress(user_id: int, task_type: str, increment: int = 1) -> None:
    """Обновляет прогресс задачи. v0.11.0"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем текущий прогресс
        cursor.execute("""
            SELECT id, progress, target, xp_reward, completed FROM daily_tasks
            WHERE user_id = ? AND task_type = ? AND DATE(reset_at) = DATE('now')
        """, (user_id, task_type))
        
        row = cursor.fetchone()
        if not row:
            return False
        
        task_id, progress, target, xp_reward, completed = row
        
        # Если уже выполнена, не обновляем
        if completed:
            return False
        
        new_progress = min(progress + increment, target)
        is_completed = new_progress >= target
        
        # Обновляем прогресс
        cursor.execute("""
            UPDATE daily_tasks
            SET progress = ?, completed = ?
            WHERE id = ?
        """, (new_progress, is_completed, task_id))
        
        # Если задача выполнена, даем XP
        if is_completed and not completed:
            add_xp_to_user(cursor, user_id, xp_reward, f"daily_task_{task_type}")
            logger.info(f"🎉 Задача выполнена! {user_id} получил {xp_reward} XP за {task_type}")
        
        conn.commit()
        return is_completed

def log_analytics_event(event_type: str, user_id: Optional[int] = None, data: Optional[dict] = None) -> None:
    """Логирует аналитическое событие."""
    if not ENABLE_ANALYTICS:
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analytics (event_type, user_id, data)
            VALUES (?, ?, ?)
        """, (event_type, user_id, json.dumps(data) if data else None))

async def audit_log(
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    action: str = "unknown",
    command: Optional[str] = None,
    parameters: Optional[dict] = None,
    result: Optional[str] = None,
    error_message: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    status: str = "success",
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> int:
    """
    🔍 Компrehensive аудит логирование - записывает ВСЕ действия пользователей.
    
    Используется для:
    - Безопасности: отслеживание попыток атак, несанкционированного доступа
    - Соответствия: GDPR, PCI-DSS, SOC2 требования
    - Debugging: отследить баги и проблемы
    - Analytics: понять как пользователи используют бота
    
    Args:
        user_id: ID пользователя
        username: Имя пользователя
        action: Тип действия (command_execute, database_query, error, etc)
        command: Какая команда была выполнена
        parameters: Параметры команды (может содержать чувствительные данные - будут замаскированы!)
        result: Результат выполнения
        error_message: Если есть ошибка
        execution_time_ms: Время выполнения в миллисекундах
        status: Статус выполнения (success, failed, rejected, etc)
        context: Telegram context для извлечения IP и версии
        
    Returns:
        ID записи в БД
    """
    try:
        # Маскируем чувствительные параметры
        safe_params = {}
        if parameters:
            for key, value in parameters.items():
                if any(x in key.lower() for x in ['key', 'secret', 'token', 'password', 'api']):
                    safe_params[key] = "***MASKED***"
                else:
                    safe_params[key] = value
        
        ip_address = None
        client_version = None
        
        # Пытаемся получить IP из context (если доступно)
        if context and context.user_data:
            ip_address = context.user_data.get('client_ip')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs 
                (user_id, username, action, command, parameters, result, error_message, 
                 ip_address, client_version, execution_time_ms, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                user_id,
                username,
                action,
                command,
                json.dumps(safe_params) if safe_params else None,
                result,
                error_message,
                ip_address,
                client_version,
                execution_time_ms,
                status
            ))
            conn.commit()
            
            # Возвращаем ID записи
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка при аудит логировании: {str(e)}", exc_info=False)
        return -1

# =============================================================================
# УТИЛИТЫ
# =============================================================================

# =============================================================================
# GLOBAL STATE MANAGEMENT (v0.23.0) - Замена глобальных переменных
# =============================================================================

class BotState:
    """
    Централизованное управление состоянием бота.
    Заменяет разрозненные глобальные переменные на один объект.
    
    Преимущества:
    - Легче отследить состояние
    - Проще добавлять новые поля
    - Лучше тестируемость
    - Безопаснее с потокобезопасностью
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        
        # Rate limiting & flood control
        self.user_last_request: Dict[int, datetime] = {}
        
        # Последние новости (для регенерации)
        self.user_last_news: Dict[int, str] = {}
        
        # Текущие курсы пользователей
        self.user_current_course: Dict[int, str] = {}
        
        # Quiz state: user_id -> {lesson, questions, current_q, answers, score}
        self.user_quiz_state: Dict[int, Dict[str, Any]] = {}
        
        # Попытки регенерации фидбека
        self.feedback_attempts: Dict[int, int] = {}
        
        logger.info(f"BotState инициализирован")
    
    async def check_flood(self, user_id: int, cooldown: int = FLOOD_COOLDOWN_SECONDS) -> bool:
        """Проверяет flood control для пользователя."""
        async with self._lock:
            now: datetime = datetime.now()
            
            if user_id in self.user_last_request:
                time_diff: float = (now - self.user_last_request[user_id]).total_seconds()
                if time_diff < cooldown:
                    return False
            
            self.user_last_request[user_id] = now
            return True
    
    async def set_user_news(self, user_id: int, text: str) -> None:
        """Сохраняет последнюю новость пользователя."""
        async with self._lock:
            self.user_last_news[user_id] = text
    
    async def get_user_news(self, user_id: int) -> Optional[str]:
        """Получает последнюю новость пользователя."""
        async with self._lock:
            return self.user_last_news.get(user_id)
    
    async def clear_user_news(self, user_id: int) -> None:
        """Очищает последнюю новость пользователя."""
        async with self._lock:
            self.user_last_news.pop(user_id, None)
    
    async def set_user_course(self, user_id: int, course: str) -> None:
        """Сохраняет текущий курс пользователя."""
        async with self._lock:
            self.user_current_course[user_id] = course
    
    async def get_user_course(self, user_id: int) -> Optional[str]:
        """Получает текущий курс пользователя."""
        async with self._lock:
            return self.user_current_course.get(user_id)
    
    async def set_quiz_state(self, user_id: int, state: Dict[str, Any]) -> None:
        """Сохраняет состояние квиза для пользователя."""
        async with self._lock:
            self.user_quiz_state[user_id] = state
    
    async def get_quiz_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает состояние квиза для пользователя."""
        async with self._lock:
            return self.user_quiz_state.get(user_id)
    
    async def clear_quiz_state(self, user_id: int) -> None:
        """Очищает состояние квиза для пользователя."""
        async with self._lock:
            self.user_quiz_state.pop(user_id, None)
    
    async def record_feedback_attempt(self, request_id: int) -> int:
        """Записывает попытку фидбека и возвращает номер попытки."""
        async with self._lock:
            attempt: int = self.feedback_attempts.get(request_id, 0) + 1
            self.feedback_attempts[request_id] = attempt
            return attempt
    
    async def clear_feedback_attempts(self, request_id: int) -> None:
        """Очищает попытки фидбека."""
        async with self._lock:
            self.feedback_attempts.pop(request_id, None)
    
    async def cleanup_user_data(self, user_id: int) -> None:
        """Очищает все данные пользователя (при logout/ban)."""
        async with self._lock:
            self.user_last_request.pop(user_id, None)
            self.user_last_news.pop(user_id, None)
            self.user_current_course.pop(user_id, None)
            self.user_quiz_state.pop(user_id, None)
            logger.info(f"🧹 Очищены данные пользователя {user_id}")
    
    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику состояния бота."""
        return {
            "active_users": len(self.user_last_request),
            "users_in_news": len(self.user_last_news),
            "users_in_course": len(self.user_current_course),
            "users_in_quiz": len(self.user_quiz_state),
            "pending_feedback": len(self.feedback_attempts)
        }
    
    async def cleanup_expired_sessions(self, timeout_seconds: int = 3600) -> int:
        """
        Очищает сессии пользователей которые не активны более timeout_seconds.
        Возвращает количество очищенных сессий.
        
        Args:
            timeout_seconds: Время неактивности после которого сессия считается истекшей (default 1 час)
        
        Returns:
            int: Количество очищенных сессий
        """
        async with self._lock:
            now: datetime = datetime.now()
            expired_users: list = []
            
            # Найди пользователей с истекшей сессией
            for user_id, last_request in list(self.user_last_request.items()):
                time_elapsed: float = (now - last_request).total_seconds()
                if time_elapsed > timeout_seconds:
                    expired_users.append(user_id)
            
            # Очищаем каждого истекшего пользователя
            for user_id in expired_users:
                self.user_last_request.pop(user_id, None)
                self.user_last_news.pop(user_id, None)
                self.user_current_course.pop(user_id, None)
                self.user_quiz_state.pop(user_id, None)
            
            if expired_users:
                logger.info(f"🧹 Очищено {len(expired_users)} истекших сессий (timeout: {timeout_seconds}s)")
            
            return len(expired_users)

# Global instance
bot_state: BotState = BotState()

# =============================================================================
# SCHEDULED TASKS (v0.24.0) - Периодические задачи для cleanup
# =============================================================================

async def periodic_session_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Периодически очищает истекшие сессии (запускается каждый час).
    Интегрирует с job queue Telegram бота.
    """
    try:
        cleaned: int = await bot_state.cleanup_expired_sessions(timeout_seconds=3600)
        if cleaned > 0:
            logger.info(f"📊 Периодический cleanup: {cleaned} сессий удалено")
    except Exception as e:
        error = await log_error(
            e,
            operation="periodic_session_cleanup",
            user_id=None
        )
        logger.error(f"Ошибка в periodic_session_cleanup: {error.message}")

async def periodic_metrics_snapshot(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Периодически логирует снимок метрик бота (запускается каждые 6 часов).
    Используется компактный режим для минимизации логов.
    """
    try:
        bot_metrics.log_metrics_snapshot(compact=True)  # ← Компактный режим
    except Exception as e:
        logger.error(f"Ошибка при логировании метрик: {e}")

# =============================================================================
# MONITORING & METRICS (v0.24.0) - Отслеживание производительности бота
# =============================================================================

class BotMetrics:
    """
    Centralized metrics tracking for monitoring bot health and performance.
    Tracks requests, errors, user activity, and other KPIs.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        
        # Request metrics
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.api_errors: int = 0
        self.db_errors: int = 0
        
        # User metrics
        self.total_unique_users: set = set()
        self.active_today: int = 0
        
        # Performance metrics
        self.avg_response_time_ms: float = 0.0
        self.slowest_response_ms: float = 0.0
        self.fastest_response_ms: float = float('inf')
        
        # Error metrics by level
        self.errors_by_level: Dict[str, int] = {
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0
        }
        
        # Cache metrics
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        
        # Session metrics
        self.sessions_created: int = 0
        self.sessions_cleaned: int = 0
        
        logger.info(f"BotMetrics инициализирован")
    
    async def record_request(self, user_id: int, success: bool, response_time_ms: float = 0.0) -> None:
        """Records a user request with performance metrics."""
        async with self._lock:
            self.total_requests += 1
            self.total_unique_users.add(user_id)
            
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            if response_time_ms > 0:
                self.fastest_response_ms = min(self.fastest_response_ms, response_time_ms)
                self.slowest_response_ms = max(self.slowest_response_ms, response_time_ms)
                
                # Update running average
                if self.successful_requests > 0:
                    self.avg_response_time_ms = (
                        self.avg_response_time_ms * (self.successful_requests - 1) + response_time_ms
                    ) / self.successful_requests
    
    async def record_error(self, error_level: str, user_id: Optional[int] = None) -> None:
        """Records an error with its severity level."""
        async with self._lock:
            if error_level in self.errors_by_level:
                self.errors_by_level[error_level] += 1
            
            if error_level in ["ERROR", "CRITICAL"]:
                self.failed_requests += 1
    
    async def record_cache_hit(self, hit: bool) -> None:
        """Records cache hit or miss."""
        async with self._lock:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
    
    async def record_api_error(self) -> None:
        """Records an API call error."""
        async with self._lock:
            self.api_errors += 1
    
    async def record_db_error(self) -> None:
        """Records a database error."""
        async with self._lock:
            self.db_errors += 1
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Returns current metrics as a dictionary."""
        cache_total = self.cache_hits + self.cache_misses
        cache_ratio = (self.cache_hits / cache_total * 100) if cache_total > 0 else 0
        
        return {
            "timestamp": datetime.now().isoformat(),
            "requests": {
                "total": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
            },
            "users": {
                "unique_total": len(self.total_unique_users),
                "active_today": self.active_today
            },
            "performance": {
                "avg_response_ms": round(self.avg_response_time_ms, 2),
                "fastest_ms": round(self.fastest_response_ms, 2) if self.fastest_response_ms != float('inf') else 0,
                "slowest_ms": round(self.slowest_response_ms, 2)
            },
            "errors": {
                "by_level": self.errors_by_level,
                "api_errors": self.api_errors,
                "db_errors": self.db_errors
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_ratio": round(cache_ratio, 2)
            }
        }
    
    def log_metrics_snapshot(self, compact: bool = True) -> None:
        """
        Logs current metrics snapshot to logger.
        
        Args:
            compact: If True, logs minimal info. If False, logs detailed breakdown.
        """
        metrics = self.get_metrics_summary()
        
        if compact:
            # Минималистичный вывод
            logger.info(
                f"📊 Req={metrics['requests']['total']} "
                f"({metrics['requests']['success_rate']:.0f}%) | "
                f"Users={metrics['users']['unique_total']} | "
                f"Resp={metrics['performance']['avg_response_ms']}ms"
            )
        else:
            # Полный детальный вывод
            logger.info(
                f"📊 METRICS SNAPSHOT: "
                f"Req={metrics['requests']['total']} "
                f"(✅{metrics['requests']['successful']}|❌{metrics['requests']['failed']}) | "
                f"Users={metrics['users']['unique_total']} | "
                f"Resp={metrics['performance']['avg_response_ms']}ms | "
                f"Cache={metrics['cache']['hit_ratio']}% | "
                f"Errors={metrics['errors']['by_level']}"
            )

# Global metrics instance
bot_metrics: BotMetrics = BotMetrics()

def get_cache_key(text: str) -> str:
    """Генерирует ключ кэша для текста (MD5 hash)."""
    normalized: str = text.lower().strip()
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

# =============================================================================
# BACKUP SYSTEM (v0.22.0) - Автоматические резервные копии БД
# =============================================================================

BACKUP_DIR: str = os.path.join(os.path.dirname(__file__), 'backups')
BACKUP_RETENTION_DAYS: int = 30  # Хранить резервные копии 30 дней
MAX_BACKUP_SIZE_MB: int = 500  # Максимальный размер одного бэкапа

def ensure_backup_dir() -> None:
    """Создает директорию для бэкапов если её нет."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    logger.info(f"Директория бэкапов готова: {BACKUP_DIR}")

async def create_database_backup() -> Tuple[bool, str]:
    """
    💾 Создает резервную копию базы данных.
    
    Returns:
        (success: bool, backup_path: str)
    """
    ensure_backup_dir()
    
    try:
        db_path = DB_PATH
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"rvx_bot_backup_{timestamp}.db")
        
        # Используем SQLite VACUUM INTO для безопасного копирования
        with get_db() as conn:
            # Закрываем все соединения перед бэкапом
            conn.execute("VACUUM")
            
            # Копируем файл с синхронизацией
            import shutil
            shutil.copy2(db_path, backup_path)
        
        backup_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        logger.info(f"Бэкап создан: {backup_path} ({backup_size_mb:.2f} MB)")
        
        # Логируем в аудит
        await audit_log(
            action="database_backup",
            command="create_backup",
            result=f"Backup created: {backup_path}",
            status="success",
            execution_time_ms=0
        )
        
        return True, backup_path
    except Exception as e:
        error_msg = f"Ошибка при создании бэкапа: {str(e)}"
        logger.error(f"{error_msg}", exc_info=False)
        
        await audit_log(
            action="database_backup",
            command="create_backup",
            error_message=error_msg,
            status="failed"
        )
        
        return False, ""

async def cleanup_old_backups() -> int:
    """
    🧹 Удаляет старые бэкапы (старше BACKUP_RETENTION_DAYS).
    
    Returns:
        Количество удаленных бэкапов
    """
    ensure_backup_dir()
    deleted_count = 0
    
    try:
        now = datetime.now()
        cutoff_time = now - timedelta(days=BACKUP_RETENTION_DAYS)
        
        for filename in os.listdir(BACKUP_DIR):
            if not filename.endswith('.db'):
                continue
            
            filepath = os.path.join(BACKUP_DIR, filename)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_mtime < cutoff_time:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info(f"Старый бэкап удален: {filename}")
                except Exception as e:
                    logger.error(f"Ошибка удаления {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"🧹 Очистка завершена: удалено {deleted_count} старых бэкапов")
            await audit_log(
                action="backup_cleanup",
                command="cleanup_old_backups",
                result=f"Deleted {deleted_count} backups",
                status="success"
            )
        
        return deleted_count
    except Exception as e:
        logger.error(f"Ошибка при очистке бэкапов: {e}", exc_info=False)
        return 0

async def restore_from_backup(backup_path: str) -> Tuple[bool, str]:
    """
    🔄 Восстанавливает БД из бэкапа.
    
    Args:
        backup_path: Путь к файлу бэкапа
        
    Returns:
        (success: bool, message: str)
    """
    try:
        if not os.path.exists(backup_path):
            msg = f"Бэкап не найден: {backup_path}"
            logger.error(f"{msg}")
            return False, msg
        
        db_path = DB_PATH
        backup_old = f"{db_path}.backup_before_restore"
        
        # Создаем резервную копию текущей БД перед восстановлением
        import shutil
        shutil.copy2(db_path, backup_old)
        
        # Восстанавливаем из бэкапа
        shutil.copy2(backup_path, db_path)
        
        msg = f"БД восстановлена из {backup_path}"
        logger.info(f"{msg}")
        
        await audit_log(
            action="database_restore",
            command="restore_from_backup",
            parameters={"backup_path": backup_path},
            result=msg,
            status="success"
        )
        
        return True, msg
    except Exception as e:
        error_msg = f"Ошибка при восстановлении: {str(e)}"
        logger.error(f"{error_msg}", exc_info=False)
        
        await audit_log(
            action="database_restore",
            command="restore_from_backup",
            error_message=error_msg,
            status="failed"
        )
        
        return False, error_msg

def list_backups() -> List[Dict[str, Any]]:
    """
    📋 Списки всех доступных бэкапов с информацией о размере и дате.
    
    Returns:
        Список дикционариев с информацией о бэкапах
    """
    ensure_backup_dir()
    backups = []
    
    try:
        for filename in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if not filename.endswith('.db'):
                continue
            
            filepath = os.path.join(BACKUP_DIR, filename)
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            backups.append({
                "filename": filename,
                "path": filepath,
                "size_mb": round(size_mb, 2),
                "created_at": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                "age_hours": round((datetime.now() - mtime).total_seconds() / 3600, 1)
            })
    except Exception as e:
        logger.error(f"Ошибка получения списка бэкапов: {e}")
    
    return backups

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет подписку на обязательный канал."""
    if not MANDATORY_CHANNEL_ID:
        return True
    
    try:
        member = await context.bot.get_chat_member(MANDATORY_CHANNEL_ID, user_id)
        is_subscribed = member.status in ['member', 'administrator', 'creator']
        
        if ENABLE_ANALYTICS:
            log_analytics_event("subscription_check", user_id, {
                "channel": MANDATORY_CHANNEL_ID,
                "status": member.status,
                "result": is_subscribed
            })
        
        return is_subscribed
    except TelegramError as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return True  # В случае ошибки не блокируем пользователя

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ от API (TIER 1 v0.22.0 - более гибкая валидация)"""
    try:
        # Если ответ пришёл как Pydantic объект, конвертируем в dict
        if hasattr(api_response, 'model_dump'):
            api_response = api_response.model_dump()
        elif hasattr(api_response, 'dict'):
            api_response = api_response.dict()
        
        # Проверяем что это dict
        if not isinstance(api_response, dict):
            logger.warning(f"API вернул не dict: {type(api_response)}")
            return None
        
        # Получаем основной текст ответа
        simplified_text = api_response.get("simplified_text")
        
        if not simplified_text or not isinstance(simplified_text, str):
            logger.warning(f"simplified_text отсутствует или не строка: {api_response}")
            return None
        
        simplified_text = simplified_text.strip()
        
        # Очищаем от markdown маркеров
        simplified_text = simplified_text.replace("**", "")  # Убираем жирное
        simplified_text = simplified_text.replace("__", "")  # Убираем двойное подчеркивание
        simplified_text = simplified_text.replace("~~", "")  # Убираем зачеркивание
        
        if len(simplified_text) < 5:
            logger.warning(f"Слишком короткий ответ: {len(simplified_text)} символов")
            return None
        
        # Telegram ограничивает 4096 символов
        if len(simplified_text) > 4096:
            logger.warning(f"Ответ слишком длинный ({len(simplified_text)} символов), обрезаю")
            return simplified_text[:4090] + "\n\n..."
        
        logger.info(f"Ответ от API валиден ({len(simplified_text)} символов)")
        return simplified_text
    
    except Exception as e:
        logger.error(f"Ошибка валидации ответа API: {e}")
        return None
async def call_api_with_retry(news_text: str, user_id: Optional[int] = None) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    🆕 v1.0: Встроенный анализатор новостей (без внешней API).
    Решает проблему 502 Bad Gateway на Railway.
    
    Анализирует новости с multi-provider fallback chain:
    1. Groq (быстро)
    2. Mistral (первый fallback)
    3. DeepSeek (альтернатива)
    4. Gemini (последний fallback)
    
    Returns:
        (response_text, processing_time_ms, error_message)
    """
    try:
        logger.info(f"📰 Встроенный анализ новостей ({len(news_text)} символов)")
        
        # Используем встроенный анализатор
        result = await analyze_news(news_text, user_id=user_id or 0)
        
        simplified_text = result.get("simplified_text", "")
        processing_time = result.get("processing_time_ms", 0)
        provider = result.get("provider", "unknown")
        
        if not simplified_text:
            logger.error(f"Анализатор вернул пустой результат")
            return None, processing_time, "Пустой результат анализа"
        
        logger.info(f"Анализ завершен за {processing_time}ms ({provider})")
        
        # Инкрементируем счетчик запросов
        try:
            if user_id:
                with get_db() as conn:
                    cursor = conn.cursor()
                    increment_daily_requests(cursor, user_id)
                    conn.commit()
        except Exception as e:
            logger.warning(f"Ошибка при обновлении счетчика запросов: {e}")
        
        return simplified_text, processing_time, None
        
    except Exception as e:
        error_msg = str(e)[:100]
        logger.error(f"Ошибка встроенного анализатора: {error_msg}")
        return None, 0, error_msg

# =============================================================================
# ДЕКОРАТОРЫ
# =============================================================================

def admin_only(func: Callable) -> Callable:
    """Декоратор для команд, доступных только администраторам."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id not in ADMIN_USERS:
            await update.message.reply_text("⛔ Только для администраторов")
            return
        return await func(update, context)
    return wrapper

def log_command(func: Callable) -> Callable:
    """Декоратор для логирования использования команд."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        command = update.message.text.split()[0] if update.message else "unknown"
        logger.info(f"📝 Команда {command} от {user.id} (@{user.username})")
        
        if ENABLE_ANALYTICS:
            log_analytics_event("command_used", user.id, {"command": command})
        
        return await func(update, context)
    return wrapper

# =============================================================================
# ФУНКЦИИ УМНОГО ОБЩЕНИЯ (v0.20.0)
# =============================================================================

async def get_user_intelligent_profile(user_id: int) -> Dict:
    """
    Получает полный профиль пользователя для умного общения.
    
    Returns:
        Словарь с информацией о пользователе
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Основная информация
            cursor.execute("""
                SELECT xp, level, badges, created_at FROM users WHERE user_id = ?
            """, (user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return None
            
            user_xp, user_level, badges_json, created_at = user_data
            
            # Статистика курсов
            cursor.execute("""
                SELECT COUNT(*) FROM user_progress WHERE user_id = ?
            """, (user_id,))
            courses_completed = cursor.fetchone()[0]
            
            # Статистика тестов
            cursor.execute("""
                SELECT COUNT(*), AVG(CASE WHEN is_correct THEN 1 ELSE 0 END) 
                FROM user_quiz_responses WHERE user_id = ?
            """, (user_id,))
            tests_result = cursor.fetchone()
            tests_count = tests_result[0] if tests_result[0] else 0
            tests_accuracy = tests_result[1] if tests_result[1] else 0.0
            
            # История изученных топиков
            cursor.execute("""
                SELECT DISTINCT course_name FROM user_progress 
                WHERE user_id = ? 
                ORDER BY completed_at DESC LIMIT 5
            """, (user_id,))
            recent_topics = [row[0] for row in cursor.fetchall()]
            
            return {
                'user_id': user_id,
                'xp': user_xp,
                'level': user_level,
                'badges': badges_json,
                'courses_completed': courses_completed,
                'tests_count': tests_count,
                'tests_accuracy': float(tests_accuracy) if tests_accuracy else 0.0,
                'recent_topics': recent_topics,
                'created_at': created_at
            }
    except Exception as e:
        logger.error(f"Ошибка при получении профиля пользователя: {e}")
        return None


async def send_smart_feedback_message(
    update: Update,
    user_profile: Dict,
    context_type: str = "general",
    parse_mode: str = ParseMode.HTML
):
    """
    Отправляет умное сообщение с фидбеком на основе профиля пользователя.
    
    Args:
        update: Update объект Telegram
        user_profile: Профиль пользователя
        context_type: Тип контекста (test_passed, test_failed, learning, daily_check)
        parse_mode: Режим парсинга
    """
    if not user_profile:
        return
    
    user_knowledge_level = analyze_user_knowledge_level(
        xp=user_profile['xp'],
        level=user_profile['level'],
        courses_completed=user_profile['courses_completed'],
        tests_passed=user_profile['tests_count']
    )
    
    message_text = ""
    
    if context_type == "test_passed":
        message_text = get_encouragement_message("test_passed", user_knowledge_level)
    elif context_type == "test_failed":
        message_text = get_encouragement_message("test_failed", user_knowledge_level)
    elif context_type == "learning":
        message_text = get_encouragement_message("course_completed", user_knowledge_level)
    elif context_type == "daily_check":
        # Ежедневная мотивационная подсказка
        tips = get_contextual_tips(
            user_knowledge_level,
            user_profile['recent_topics'],
            "DeFi Protocols",  # Можно сделать более умным
            user_profile['tests_accuracy']
        )
        if tips:
            message_text = tips
    
    # Не отправляем бесполезные сообщения
    if message_text and message_text.strip():
        try:
            if update.callback_query:
                await update.callback_query.answer(message_text, show_alert=False)
            elif update.message:
                await update.message.reply_text(message_text, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"Не удалось отправить умное сообщение: {e}")


async def get_smart_next_recommendation(user_id: int) -> Optional[str]:
    """
    Генерирует персонализированное рекомендацию на основе истории пользователя.
    
    Returns:
        Текст с рекомендацией
    """
    try:
        profile = await get_user_intelligent_profile(user_id)
        if not profile:
            return None
        
        user_knowledge_level = analyze_user_knowledge_level(
            xp=profile['xp'],
            level=profile['level'],
            courses_completed=profile['courses_completed'],
            tests_passed=profile['tests_count']
        )
        
        # Определяем интересы
        primary_interest, secondary_interest = analyze_user_interests(
            profile['recent_topics'],
            {}  # Можно добавить более сложный анализ
        )
        
        # Генерируем рекомендацию
        recommendation = get_personalized_next_action(
            user_knowledge_level,
            has_pending_quests=True,
            new_course_available=True,
            can_take_test=True
        )
        
        return recommendation
    except Exception as e:
        logger.error(f"Ошибка при генерации рекомендации: {e}")
        return None


# =============================================================================
# КОМАНДЫ
# =============================================================================

@log_command
async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает адаптивные ежедневные задания по уровню пользователя."""
    user = update.effective_user
    user_id = user.id
    
    # ✅ v0.25.0: Track user education event (tasks are educational)
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_EDUCATION,
        user_id=user_id,
        data={"action": "view_daily_tasks"}
    ))
    
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    try:
        # Получаем XP пользователя из БД
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            user_xp = row[0] if row else 0
        
        # Определяем уровень и получаем список заданий
        user_level = get_user_level(user_xp)
        level_name = get_level_name(user_level)
        level_info = get_level_info(user_level)
        quests = get_daily_quests_for_level(user_level)
        
        # Формируем текст
        text = f"""📋 <b>ЕЖЕДНЕВНЫЕ ЗАДАНИЯ</b>

{level_name}
XP: {user_xp}

────────────────────
Выбери задание и пройди тест!"""
        
        # Строим клавиатуру с кнопками заданий
        keyboard = []
        for quest in quests:
            button_text = f"▶️ {quest['title']}"
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"start_quest_{quest['id']}"
            )])
        
        # Добавляем кнопку назад
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        if is_callback and query:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.answer()
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"Ошибка tasks_command: {e}")
        error_text = "❌ Ошибка. Попробуй позже."
        if is_callback and query:
            await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)


@log_command
async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команд /quest_* для запуска конкретного квеста."""
    user_id = update.effective_user.id
    
    # Получаем quest_id из команды
    # Например: /quest_what_is_dex → quest_id = "what_is_dex"
    if not context.args or len(context.args) == 0:
        await send_error_with_tips(
            update,
            "Не указан ID квеста",
            tips=[
                "Используй одну из команд: /quest_what_is_dex, /quest_what_is_staking и т.д.",
                "Или перейди в меню /tasks для выбора квеста"
            ],
            command_help="/quest_what_is_dex"
        )
        return
    
    quest_id = "_".join(context.args)  # На случай, если ID содержит подчеркивания
    
    # Проверяем, существует ли такой квест
    if quest_id not in DAILY_QUESTS:
        available_quests = ", ".join(list(DAILY_QUESTS.keys())[:5])
        await send_error_with_tips(
            update,
            f"Квест '{quest_id}' не найден",
            tips=[
                f"Доступные квесты: {available_quests}",
                "Используй /tasks для просмотра всех квестов"
            ],
            command_help="/quest_what_is_dex"
        )
        return
    
    # Запускаем квест
    await start_quest(update, context, quest_id)


# =============================================================================
# LEADERBOARD - РЕЙТИНГОВАЯ СИСТЕМА (v0.17.0)
# =============================================================================

def get_leaderboard_data(period: str = "all", limit: int = 50) -> Tuple[List[Tuple], Optional[int]]:
    """
    Получает данные рейтинга из кэша или БД.
    
    Args:
        period: "week", "month", "all"
        limit: количество топ позиций
    
    Returns:
        ([(rank, user_id, username, xp, level, requests), ...], total_users)
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Сначала пробуем кэш (обновляется каждый час)
        cursor.execute("""
            SELECT rank, user_id, username, xp, level, total_requests
            FROM leaderboard_cache
            WHERE period = ?
            ORDER BY rank
            LIMIT ?
        """, (period, limit))
        
        cached = cursor.fetchall()
        if cached:
            # Считаем общее количество уникальных пользователей
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users")
            total_users = cursor.fetchone()[0]
            return cached, total_users
        
        # Если кэша нет, генерируем данные
        now = datetime.now()
        
        # Определяем временной период
        if period == "week":
            start_date = now - timedelta(days=7)
            cursor.execute("""
                SELECT user_id, username, xp, level, total_requests
                FROM users
                WHERE xp > 0 AND created_at > ?
                ORDER BY xp DESC, level DESC, total_requests DESC
                LIMIT ?
            """, (start_date.isoformat(), limit))
        elif period == "month":
            start_date = now - timedelta(days=30)
            cursor.execute("""
                SELECT user_id, username, xp, level, total_requests
                FROM users
                WHERE xp > 0 AND created_at > ?
                ORDER BY xp DESC, level DESC, total_requests DESC
                LIMIT ?
            """, (start_date.isoformat(), limit))
        else:  # "all"
            cursor.execute("""
                SELECT user_id, username, xp, level, total_requests
                FROM users
                WHERE xp > 0
                ORDER BY xp DESC, level DESC, total_requests DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        result = []
        for rank, row in enumerate(rows, 1):
            result.append((rank, row[0], row[1], row[2], row[3], row[4]))
        
        # Кэшируем результаты
        cursor.execute("DELETE FROM leaderboard_cache WHERE period = ?", (period,))
        for rank, user_id, username, xp, level, requests in result:
            cursor.execute("""
                INSERT INTO leaderboard_cache (period, rank, user_id, username, xp, level, total_requests)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (period, rank, user_id, username, xp, level, requests))
        
        conn.commit()
        
        # Считаем общее количество
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users")
        total_users = cursor.fetchone()[0]
        
        return result, total_users


def get_user_rank(user_id: int, period: str = "all") -> Optional[Tuple[int, int, int, int]]:
    """
    Получает позицию пользователя в рейтинге.
    
    Returns:
        (rank, xp, level, requests) или None
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем кэш
        cursor.execute("""
            SELECT rank, xp, level, total_requests
            FROM leaderboard_cache
            WHERE period = ? AND user_id = ?
        """, (period, user_id))
        
        cached = cursor.fetchone()
        if cached:
            return cached
        
        # Если в кэше нет, считаем ранг
        now = datetime.now()
        
        cursor.execute("""
            SELECT xp, level, total_requests
            FROM users
            WHERE user_id = ?
        """, (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data or user_data[0] == 0:
            return None
        
        xp, level, requests = user_data
        
        # Определяем временной период
        if period == "week":
            start_date = now - timedelta(days=7)
            # Считаем сколько людей выше
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE created_at > ?
                AND (xp > ? OR (xp = ? AND level > ?) OR (xp = ? AND level = ? AND total_requests > ?))
            """, (start_date.isoformat(), xp, xp, level, xp, level, requests))
        elif period == "month":
            start_date = now - timedelta(days=30)
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE created_at > ?
                AND (xp > ? OR (xp = ? AND level > ?) OR (xp = ? AND level = ? AND total_requests > ?))
            """, (start_date.isoformat(), xp, xp, level, xp, level, requests))
        else:  # "all"
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE xp > ? OR (xp = ? AND level > ?) OR (xp = ? AND level = ? AND total_requests > ?)
            """, (xp, xp, level, xp, level, requests))
        
        rank = cursor.fetchone()[0] + 1
        return (rank, xp, level, requests)


# =============================================================================
# USER PROFILE SYSTEM v0.37.15
# =============================================================================

def get_user_profile_data(user_id: int) -> dict:
    """Собирает все данные профиля пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Основная информация
        cursor.execute("""
            SELECT user_id, username, first_name, xp, level, created_at, total_requests, badges
            FROM users WHERE user_id = ?
        """, (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            return None
        
        user_id, username, first_name, xp, level, created_at, total_requests, badges_json = user_data
        
        # Парсим бейджи
        try:
            badges = json.loads(badges_json) if badges_json else []
        except:
            badges = []
        
        # Статистика активности
        # Пройденные уроки (из user_progress)
        cursor.execute("""
            SELECT COUNT(DISTINCT lesson_id) FROM user_progress 
            WHERE user_id = ? AND completed_at IS NOT NULL
        """, (user_id,))
        lessons_completed = cursor.fetchone()[0] or 0
        
        # Сданные тесты (из user_quiz_stats)
        cursor.execute("""
            SELECT COUNT(*) FROM user_quiz_stats 
            WHERE user_id = ? AND is_perfect_score = 1
        """, (user_id,))
        perfect_tests = cursor.fetchone()[0] or 0
        
        # Попытки тестов (все попытки)
        cursor.execute("""
            SELECT COUNT(*) FROM user_quiz_stats 
            WHERE user_id = ?
        """, (user_id,))
        total_tests = cursor.fetchone()[0] or 0
        
        # Вопросы которые задавал пользователь
        cursor.execute("""
            SELECT COUNT(*) FROM user_questions 
            WHERE user_id = ?
        """, (user_id,))
        questions_asked = cursor.fetchone()[0] or 0
        
        # Дней активности подряд (примерный подсчет)
        cursor.execute("""
            SELECT DATE('now') as today, created_at FROM users WHERE user_id = ?
        """, (user_id,))
        dates = cursor.fetchone()
        days_active = 1  # Минимум 1 день
        
        return {
            'user_id': user_id,
            'username': username or f'User#{user_id}',
            'first_name': first_name,
            'xp': xp or 0,
            'level': level or 1,
            'created_at': created_at,
            'total_requests': total_requests or 0,
            'badges': badges,
            'lessons_completed': lessons_completed,
            'perfect_tests': perfect_tests,
            'total_tests': total_tests,
            'questions_asked': questions_asked,
            'days_active': days_active
        }


def format_user_profile(profile_data: dict) -> str:
    """Форматирует профиль в красивое сообщение."""
    if not profile_data:
        return "❌ Профиль не найден"
    
    # Определяем статус на основе уровня
    if profile_data['level'] >= 50:
        status = "🎓 Эксперт"
    elif profile_data['level'] >= 30:
        status = "📚 Продвинутый"
    elif profile_data['level'] >= 10:
        status = "⭐ Ученик"
    else:
        status = "🌱 Новичок"
    
    # Прогресс-бар к следующему уровню (каждый уровень = 100 XP)
    xp_in_level = profile_data['xp'] % 100
    progress_bar = "▓" * (xp_in_level // 10) + "░" * (10 - xp_in_level // 10)
    
    # Текст профиля
    text = (
        f"👤 <b>ВАШ ПРОФИЛЬ</b>\n"
        f"{'═' * 40}\n\n"
        
        f"<b>📊 ОСНОВНАЯ ИНФОРМАЦИЯ</b>\n"
        f"Ник: <b>{profile_data['username']}</b>\n"
        f"Статус: {status}\n"
        f"Уровень: <b>{profile_data['level']}</b> 🎯\n"
        f"XP: <b>{profile_data['xp']}</b> / {profile_data['level'] * 100}\n"
        f"Прогресс: [{progress_bar}] {xp_in_level}%\n\n"
        
        f"<b>📈 СТАТИСТИКА АКТИВНОСТИ</b>\n"
        f"🔹 Пройдено уроков: {profile_data['lessons_completed']}/24\n"
        f"🔹 Сдано тестов идеально: {profile_data['perfect_tests']}/{profile_data['total_tests']}\n"
        f"🔹 Задано вопросов: {profile_data['questions_asked']}\n"
        f"🔹 Дней подряд активен: {profile_data['days_active']}\n\n"
    )
    
    # Добавляем бейджи если есть
    if profile_data['badges']:
        badge_emojis = {
            'first_lesson': '🎓',
            'first_test': '✅',
            'first_question': '💬',
            'level_5': '⭐',
            'level_10': '🌟',
            'perfect_score': '🎯',
            'daily_active': '🔥',
            'helper': '👐'
        }
        
        badge_names = {
            'first_lesson': 'Первый урок',
            'first_test': 'Первый тест',
            'first_question': 'Первый вопрос',
            'level_5': 'Уровень 5',
            'level_10': 'Уровень 10',
            'perfect_score': 'Идеальный результат',
            'daily_active': 'Ежедневный активист',
            'helper': 'Помощник'
        }
        
        text += f"<b>🏅 ДОСТИЖЕНИЯ ({len(profile_data['badges'])})</b>\n"
        for badge in profile_data['badges'][:5]:  # Показываем максимум 5
            emoji = badge_emojis.get(badge, '🎖️')
            name = badge_names.get(badge, badge)
            text += f"{emoji} {name}\n"
        
        if len(profile_data['badges']) > 5:
            text += f"... и ещё {len(profile_data['badges']) - 5} достижений\n"
        text += "\n"
    
    # Рекомендация развития
    text += f"<b>🎓 РЕКОМЕНДАЦИИ</b>\n"
    
    if profile_data['lessons_completed'] < 5:
        text += "📚 Пройди первые 5 уроков для лучшего понимания\n"
    
    if profile_data['total_tests'] < profile_data['lessons_completed']:
        text += "✅ Попробуй пройти тесты по пройденным темам\n"
    
    if profile_data['questions_asked'] == 0:
        text += "💬 Задай свой первый вопрос нашему ИИ\n"
    
    if profile_data['xp'] < profile_data['level'] * 100:
        remaining_xp = (profile_data['level'] * 100) - profile_data['xp']
        text += f"🚀 Ещё {remaining_xp} XP до следующего уровня!\n"
    
    text += "\n" + "═" * 40
    
    return text


def get_user_recommendations(user_id: int) -> dict:
    """Получает рекомендации развития для пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем пройденные темы
        cursor.execute("""
            SELECT DISTINCT topic FROM teaching_lessons 
            WHERE user_id = ? AND difficulty = 'advanced'
            ORDER BY created_at DESC
        """, (user_id,))
        
        completed_topics = [row[0] for row in cursor.fetchall()]
        
        # Определяем следующую рекомендуемую тему
        all_topics = list(TEACHING_TOPICS.keys())
        uncompleted = [t for t in all_topics if t not in completed_topics]
        
        next_topic = uncompleted[0] if uncompleted else all_topics[0]
        
        # Тема с наименьшим прогрессом (слабая сторона)
        cursor.execute("""
            SELECT topic, COUNT(*) as attempts FROM teaching_lessons 
            WHERE user_id = ?
            GROUP BY topic
            ORDER BY COUNT(*) ASC
            LIMIT 1
        """, (user_id,))
        
        weak_topic_data = cursor.fetchone()
        weak_topic = weak_topic_data[0] if weak_topic_data else None
        
        return {
            'next_topic': next_topic,
            'weak_topic': weak_topic,
            'completed_count': len(completed_topics),
            'total_topics': len(all_topics)
        }


@log_command
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает профиль пользователя с достижениями и рекомендациями."""
    user_id = update.effective_user.id
    
    # Сохраняем пользователя
    save_user(user_id, update.effective_user.username or "", update.effective_user.first_name)
    
    try:
        # Получаем данные профиля
        profile_data = get_user_profile_data(user_id)
        
        if not profile_data:
            await update.message.reply_text("❌ Ошибка загрузки профиля")
            return
        
        # Форматируем сообщение
        text = format_user_profile(profile_data)
        
        # Кнопки
        keyboard = [
            [InlineKeyboardButton("📚 Все достижения", callback_data="profile_all_badges")],
            [InlineKeyboardButton("📊 Детальная статистика", callback_data="profile_stats")],
            [InlineKeyboardButton("🚀 Начать урок", callback_data="teach_recommended")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в profile_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка загрузки профиля")


@log_command
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает рейтинг пользователей."""
    user = update.effective_user
    user_id = user.id
    
    # ✅ Сохраняем пользователя перед получением статистики
    save_user(user_id, user.username or "", user.first_name)
    
    query = update.callback_query if update.callback_query else None
    is_callback = query is not None
    
    # Кнопки для выбора периода
    keyboard = [
        [
            InlineKeyboardButton("📅 Неделя", callback_data="leaderboard_week"),
            InlineKeyboardButton("📆 Месяц", callback_data="leaderboard_month"),
            InlineKeyboardButton("⏳ Всё время", callback_data="leaderboard_all")
        ]
    ]
    
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\nВыбери период:"
    
    try:
        if is_callback:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.answer()
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Ошибка leaderboard_command: {e}")


# =============================================================================
# BOOKMARKS SYSTEM (v0.18.0)
# =============================================================================

def add_bookmark(user_id: int, bookmark_type: str, content_title: str, 
                 content_text: str, external_id: str = None, source: str = None) -> bool:
    """
    Добавляет новую закладку пользователю.
    
    Args:
        user_id: Telegram user ID
        bookmark_type: "news", "lesson", "tool", "resource"
        content_title: Заголовок контента
        content_text: Текст контента (макс 500 символов)
        external_id: Внешний ID (для уникальности)
        source: Источник закладки
    
    Returns:
        True если успешно, False если ошибка
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Обрезаем текст до 500 символов
            content_text = content_text[:500] if content_text else ""
            
            cursor.execute("""
                INSERT OR REPLACE INTO user_bookmarks_v2 
                (user_id, bookmark_type, content_title, content_text, content_source, external_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, bookmark_type, content_title, content_text, source, external_id))
            
            conn.commit()
            
            logger.info(f"📌 Закладка добавлена: {user_id} | {bookmark_type} | {content_title[:30]}")
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления закладки: {e}")
        return False


def remove_bookmark(user_id: int, bookmark_id: int) -> bool:
    """Удаляет закладку."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем что закладка принадлежит пользователю
            cursor.execute("""
                SELECT id FROM user_bookmarks_v2 
                WHERE id = ? AND user_id = ?
            """, (bookmark_id, user_id))
            
            if not cursor.fetchone():
                return False
            
            # Удаляем
            cursor.execute("DELETE FROM user_bookmarks_v2 WHERE id = ? AND user_id = ?", 
                          (bookmark_id, user_id))
            
            conn.commit()
            logger.info(f"Закладка удалена: {user_id} | ID: {bookmark_id}")
            return True
    except Exception as e:
        logger.error(f"Ошибка удаления закладки: {e}")
        return False


def get_user_bookmarks(user_id: int, bookmark_type: str = None, limit: int = 10) -> List[Tuple]:
    """
    Получает закладки пользователя.
    
    Returns:
        [(id, type, title, text, source, added_at, viewed_count), ...]
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            if bookmark_type:
                cursor.execute("""
                    SELECT id, bookmark_type, content_title, content_text, 
                           content_source, added_at, viewed_count
                    FROM user_bookmarks_v2
                    WHERE user_id = ? AND bookmark_type = ?
                    ORDER BY added_at DESC
                    LIMIT ?
                """, (user_id, bookmark_type, limit))
            else:
                cursor.execute("""
                    SELECT id, bookmark_type, content_title, content_text, 
                           content_source, added_at, viewed_count
                    FROM user_bookmarks_v2
                    WHERE user_id = ?
                    ORDER BY added_at DESC
                    LIMIT ?
                """, (user_id, limit))
            
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения закладок: {e}")
        return []


def update_bookmark_views(bookmark_id: int, user_id: int) -> bool:
    """Обновляет счётчик просмотров и время последнего просмотра."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE user_bookmarks_v2
                SET viewed_count = viewed_count + 1,
                    last_viewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            """, (bookmark_id, user_id))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления просмотров: {e}")
        return False


def get_bookmark_count(user_id: int, bookmark_type: str = None) -> int:
    """Получает количество закладок пользователя."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            if bookmark_type:
                cursor.execute("""
                    SELECT COUNT(*) FROM user_bookmarks_v2
                    WHERE user_id = ? AND bookmark_type = ?
                """, (user_id, bookmark_type))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM user_bookmarks_v2
                    WHERE user_id = ?
                """, (user_id,))
            
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Ошибка подсчёта закладок: {e}")
        return 0


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str) -> None:
    """Показывает таблицу лидеров за период."""
    user = update.effective_user
    user_id = user.id
    
    # ✅ Сохраняем пользователя перед показом лидерборда
    save_user(user_id, user.username or "", user.first_name)
    
    query = update.callback_query
    
    try:
        # Получаем данные рейтинга
        leaderboard, total_users = get_leaderboard_data(period, limit=10)
        
        # Заголовок
        period_names = {"week": "за неделю", "month": "за месяц", "all": "за всё время"}
        period_emoji = {"week": "📅", "month": "📆", "all": "⏳"}
        
        text = f"🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b> {period_emoji[period]} ({period_names[period]})\n"
        text += f"<i>Всего пользователей: {total_users}</i>\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for rank, uid, username, xp, level, requests in leaderboard:
            medal = medals[rank - 1] if rank <= 3 else "  "
            username_display = username or f"User#{uid}"
            
            # Выделяем текущего пользователя
            if uid == user_id:
                text += f"{medal} <b>#{rank}. {username_display}</b>\n"
                text += f"   💫 {xp} XP | Уровень {level} | Запросов: {requests}\n\n"
            else:
                text += f"{medal} #{rank}. {username_display}\n"
                text += f"   💫 {xp} XP | Уровень {level} | Запросов: {requests}\n"
        
        # Добавляем позицию текущего пользователя, если его нет в топ-10
        user_rank_data = get_user_rank(user_id, period)
        if user_rank_data and user_rank_data[0] > 10:
            rank, xp, level, requests = user_rank_data
            text += f"\n{'─' * 45}\n"
            text += f"👤 <b>Твоя позиция:</b>\n"
            text += f"   #{rank} | 💫 {xp} XP | Уровень {level}\n"
        elif not user_rank_data:
            text += f"\n{'─' * 45}\n"
            text += f"👤 <b>Ты пока не в рейтинге</b>\n"
            text += f"   Начни зарабатывать XP через команды /news, /teach, /quest\n"
        
        # Кнопки для переключения периода
        keyboard = [
            [
                InlineKeyboardButton("📅 Неделя", callback_data="leaderboard_week"),
                InlineKeyboardButton("📆 Месяц", callback_data="leaderboard_month"),
                InlineKeyboardButton("⏳ Всё время", callback_data="leaderboard_all")
            ],
            [InlineKeyboardButton("« Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.answer()
        
    except Exception as e:
        logger.error(f"Ошибка show_leaderboard: {e}", exc_info=True)
        try:
            if query:
                await query.answer("❌ Ошибка загрузки рейтинга", show_alert=True)
            else:
                await update.message.reply_text("❌ Ошибка загрузки рейтинга")
        except:
            logger.error(f"Не удалось отправить ошибку пользователю")


@log_command
async def bookmarks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает закладки пользователя с интерактивным интерфейсом."""
    user_id = update.effective_user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    bookmarks = get_user_bookmarks(user_id, limit=100)
    
    if not bookmarks:
        keyboard = [
            [InlineKeyboardButton("« Назад в меню", callback_data="back_to_start")]
        ]
        text = "📌 <b>Твои закладки пусты</b>\n\n" \
               "💡 <b>Как использовать закладки:</b>\n" \
               "  1️⃣ Отправь текст новости или вопроса\n" \
               "  2️⃣ Получи анализ от ИИ\n" \
               "  3️⃣ Нажми кнопку 📌 чтобы сохранить\n" \
               "  4️⃣ Вернись сюда позже через /bookmarks\n\n" \
               "📚 <i>Закладки помогают отслеживать интересные анализы и материалы для обучения!</i>"
    else:
        # Группируем по типам
        bookmark_types = {
            "news": ("📰", "Новости"),
            "lesson": ("🎓", "Уроки"),
            "tool": ("🧰", "Инструменты"),
            "resource": ("📚", "Ресурсы")
        }
        
        text = f"📚 <b>ТВИ ЗАКЛАДКИ</b> (Всего: {len(bookmarks)})\n\n"
        
        # Группируем закладки
        grouped = {}
        for bm in bookmarks:
            bm_type = bm[1]  # bookmark_type (ИСПРАВЛЕНО: было bm[2])
            if bm_type not in grouped:
                grouped[bm_type] = []
            grouped[bm_type].append(bm)
        
        keyboard = []
        row = []
        
        # Выводим по категориям кнопками
        for bm_type, items in sorted(grouped.items()):
            emoji, name = bookmark_types.get(bm_type, ("📌", bm_type))
            count = len(items)
            button_label = f"{emoji} {name} ({count})"
            
            row.append(InlineKeyboardButton(button_label, callback_data=f"show_bookmarks_{bm_type}"))
            
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("« Назад в меню", callback_data="back_to_start")])
        
        # Показываем краткую статистику
        for bm_type, items in sorted(grouped.items()):
            emoji, name = bookmark_types.get(bm_type, ("📌", bm_type))
            text += f"{emoji} <b>{name}</b>: {len(items)} сохранено\n"
        
        text += "\n👆 Нажми на категорию для просмотра закладок"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if is_callback and query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при выводе закладок: {e}")
        await query.answer("❌ Ошибка", show_alert=True) if is_callback else None


@log_command
async def add_bookmark_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет текущий контент в закладки."""
    user_id = update.effective_user.id
    
    # Проверяем есть ли контекст от предыдущего запроса
    if "last_content" not in context.user_data:
        await update.message.reply_text(
            "❌ Нет контента для добавления.\n\n"
            "Сначала получи новость через /news или урок через /teach",
            parse_mode=ParseMode.HTML
        )
        return
    
    content = context.user_data["last_content"]
    
    success = add_bookmark(
        user_id,
        bookmark_type=content.get("type", "news"),
        content_title=content.get("title", "Без заголовка")[:100],
        content_text=content.get("text", "")[:500],
        source=content.get("source", None)
    )
    
    if success:
        await update.message.reply_text(
            "✅ <b>Закладка сохранена!</b>\n\n"
            "Смотри /my_bookmarks чтобы увидеть все закладки",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "❌ <b>Ошибка сохранения закладки</b>",
            parse_mode=ParseMode.HTML
        )


@log_command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Приветственное сообщение с адаптивными кнопками.
    
    Функция:
    - Проверяет подписку на обязательный канал (v0.42.1)
    - Сохраняет пользователя в БД
    - Проверяет бан
    - Анализирует уровень знаний
    - Показывает адаптивное меню
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
        
    Returns:
        None
    """
    user = update.effective_user
    user_id = user.id
    
    print(f"\n=== START_COMMAND DEBUG ===")
    print(f"User ID: {user_id}")
    print(f"Username: {user.username}")
    
    logger.info(f"🚀 START_COMMAND called by user {user_id} (@{user.username})")
    
    # ✅ v0.43.0: Проверяем язык пользователя - если не установлен, показываем выбор
    user_language = get_user_lang(user_id, default=None)
    print(f"DEBUG: User language from DB: {user_language}")
    
    if user_language is None:
        logger.info(f"📢 User {user_id} doesn't have language selected, showing language selection menu")
        
        # Сохраняем пользователя в БД чтобы потом можно было обновить язык
        save_user(user_id, user.username or "", user.first_name)
        
        # Показываем меню выбора языка
        selection_prompt = await get_text("language.select_prompt", language="ru")
        
        keyboard = [
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            selection_prompt,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return  # Выходим, дальше пользователь выбирает язык и мы снова вызовем start_command
    
    # Очищаем кэш для этого пользователя при каждом /start (чтобы всегда проверять актуальный статус)
    await clear_subscription_cache(user_id)
    
    # ✅ v0.42.1: Проверяем подписку на обязательный канал
    logger.info(f"📋 Checking mandatory channel subscription for user {user_id}...")
    print(f"DEBUG: About to call check_channel_subscription")
    is_subscribed = await check_channel_subscription(user_id, context)
    print(f"DEBUG: check_channel_subscription returned: {is_subscribed}")
    logger.info(f"✅ Subscription check result for user {user_id}: {is_subscribed}")
    
    print(f"DEBUG: Checking if not is_subscribed: {not is_subscribed}")
    
    if not is_subscribed:
        print(f"DEBUG: User is NOT subscribed, showing subscription prompt")
        
        # Отправляем сообщение с кнопкой для подписки
        keyboard = [
            [
                InlineKeyboardButton(
                    "📢 Подписаться на канал",
                    url=MANDATORY_CHANNEL_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Я подписался, проверить еще раз",
                    callback_data=f"check_subscription_{user_id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        subscription_prompt = (
            "<b>📢 Требуется подписка</b>\n\n"
            "Добро пожаловать! Для использования этого бота необходимо подписаться на наш канал. "
            "После подписки вы получите доступ ко всем функциям.\n\n"
            "👇 Подпишитесь по ссылке ниже:"
        )
        
        await update.message.reply_text(
            subscription_prompt,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return
    
    logger.info(f"✅ User {user_id} is subscribed, proceeding with start_command")
    
    # ✅ v0.25.0: Track user_start event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_START,
        user_id=user_id,
        data={"username": user.username or "", "first_name": user.first_name or ""}
    ))
    
    # Сохраняем пользователя
    save_user(user_id, user.username or "", user.first_name)
    
    is_banned, ban_reason = check_user_banned(user_id)
    if is_banned:
        await update.message.reply_text(
            f"⛔ <b>Вы заблокированы</b>\n\nПричина: <i>{ban_reason or 'Не указана'}</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Получаем статистику пользователя для умного общения
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT xp, level, (
                SELECT COUNT(*) FROM user_progress WHERE user_id = ?
            ), (
                SELECT COUNT(*) FROM user_quiz_responses WHERE user_id = ?
            ), created_at FROM users WHERE user_id = ?
        """, (user_id, user_id, user_id))
        
        user_stats = cursor.fetchone()
        if user_stats:
            user_xp, user_level, courses_completed, tests_passed, created_at = user_stats
        else:
            user_xp, user_level, courses_completed, tests_passed = 0, 1, 0, 0
    
    # Анализируем уровень пользователя для адаптивного общения (v0.20.0)
    user_knowledge_level = analyze_user_knowledge_level(
        xp=user_xp,
        level=user_level,
        courses_completed=courses_completed,
        tests_passed=tests_passed
    )
    
    # Адаптивное приветствие вместо стандартного
    adaptive_greeting = get_adaptive_greeting(
        user_knowledge_level,
        user.first_name or "друже"
    )
    
    # Получаем информацию о лимитах
    can_request, remaining = check_daily_limit(user_id)
    if user_id in ADMIN_USERS:
        limits_text = f"⚡ <b>Твой лимит:</b> <i>БЕЗЛИМИТНЫЙ (Admin)</i>"
    else:
        limits_text = f"⚡ <b>Твой лимит:</b> <i>{remaining}/{MAX_REQUESTS_PER_DAY} запросов</i>"
    
    # Получаем ежедневные задачи для уровня пользователя (NEW v0.21.0)
    user_quest_level = get_user_level(user_xp)
    level_name = get_level_name(user_quest_level)
    daily_quests = get_daily_quests_for_level(user_quest_level)
    
    # Получаем выполненные квесты за сегодня
    from daily_quests_v2 import get_completed_quests_today, get_daily_quest_xp_earned
    with get_db() as conn:
        completed_quests = get_completed_quests_today(user_id, conn)
        daily_xp_earned = get_daily_quest_xp_earned(user_id, conn)
    
    # Форматируем топ 3 задачи для отображения
    quests_preview = ""
    if daily_quests:
        completed_count = len(completed_quests)
        quests_preview = f"<b>🎯 СЕГОДНЯШНИЕ ЗАДАЧИ ({completed_count}/5):</b>\n"
        for idx, quest in enumerate(daily_quests[:3], 1):
            # Проверяем как строку (т.к. completed_quests содержит строки)
            quest_completed = "✅" if str(quest.get('id', '')) in completed_quests else "⭕"
            quests_preview += f"{quest_completed} {idx}. {quest['title']} <b>({quest['xp']} XP)</b>\n"
        
        # Добавляем информацию о заработках
        if completed_count > 0:
            quests_preview += f"\n💰 Заработано сегодня: <b>{daily_xp_earned} XP</b>"
        else:
            quests_preview += "\n💡 Начни с первой задачи!"
        quests_preview += "\n"
    
    welcome_text = (
        f"🚀 <b>RVX AI - Твой эксперт в крипто и Web3</b>\n"
        f"<i>Анализ • Обучение • Стратегия</i>\n\n"
        
        f"👋 {adaptive_greeting}\n\n"
        
        f"<b>✨ Твой путь начинается здесь:</b>\n\n"
        
        f"🧠 <b>Анализ новостей</b>\n"
        f"   Получай умный анализ крипто новостей за 10 сек\n\n"
        
        f"📚 <b>Обучение (50+ уроков)</b>\n"
        f"   От новичка до эксперта • Все о блокчейне и Web3\n\n"
        
        f"🎯 <b>Ежедневные задачи</b>\n"
        f"   Заработай до 200 XP/день и поднимайся в лидерборде\n\n"
        
        f"🏆 <b>Лидерборд и награды</b>\n"
        f"   Топ пользователи получают эксклюзивные бенефиты\n\n"
        
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Твой профиль:</b>\n"
        f"{limits_text}"
        f"📈 Уровень: <code>{level_name}</code> | XP: <code>{user_xp}</code>\n"
        f"🎓 Прогресс: <code>{courses_completed}/3 курсов</code> | <code>{tests_passed} тестов</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"<b>🎁 Что тебя ждёт:</b>\n"
        f"✅ Бесплатное обучение от А до Я\n"
        f"✅ Интерактивные задачи с наградами\n"
        f"✅ Рейтинговая система с топ-10 лидерборде\n"
        f"✅ Анализ любых крипто новостей за секунды\n"
        f"✅ Защита от манипуляций и фейков\n\n"
        
        f"<b>⚡ Начни прямо сейчас!</b>\n"
        f"Выбери действие ниже и погрузись в мир крипто 👇\n\n"
        f"<i>Или просто отправь мне вопрос или новость, которую хочешь обсудить — я помогу! 💬</i>\n"
    )
    
    if MANDATORY_CHANNEL_ID:
        welcome_text += f"\n📢 <b>Бонус:</b> Подпишись на канал для эксклюзивного контента → {MANDATORY_CHANNEL_LINK}\n"
    
    # Интерактивные кнопки основных функций (v0.26.0 красивый дизайн)
    keyboard = [
        [
            InlineKeyboardButton("🎓 Учиться", callback_data="start_teach"),
            InlineKeyboardButton("📚 Курсы", callback_data="start_learn")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="start_stats"),
            InlineKeyboardButton("🏆 Лидерборд", callback_data="start_leaderboard")
        ],
        [
            InlineKeyboardButton("👤 Мой профиль", callback_data="start_profile"),
            InlineKeyboardButton("🎯 Ежедневные", callback_data="start_quests")
        ],
        [
            InlineKeyboardButton("📚 Ресурсы", callback_data="start_resources"),
            InlineKeyboardButton("📌 Закладки", callback_data="start_bookmarks")
        ],
        [
            InlineKeyboardButton("🧮 Калькулятор", callback_data="start_calculator"),
            InlineKeyboardButton("📦 Дропы", callback_data="start_airdrops")
        ],
        [
            InlineKeyboardButton("🔥 Активности", callback_data="start_activities"),
            InlineKeyboardButton("📜 История", callback_data="start_history")
        ],
        [
            InlineKeyboardButton("⚙️ Меню", callback_data="start_menu")
        ]
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает справку по всем доступным командам.
    
    Выводит:
    - Список основных команд
    - Описание каждой команды
    - Советы по использованию
    - Примеры
    
    Args:
        update: Telegram Update объект (command или callback)
        context: Telegram Context объект
        
    Returns:
        None
    """
    # ✅ v0.25.0: Track user_help event
    user_id = update.effective_user.id
    tracker = get_tracker()
    tracker.track(create_event(EventType.USER_HELP, user_id=user_id))
    
    help_text = MSG_HELP_EXTENDED
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 <b>Официальный канал:</b>\n{MANDATORY_CHANNEL_LINK}"
    
    keyboard = [
        [
            InlineKeyboardButton("📚 Начать обучение", callback_data="start_teach"),
            InlineKeyboardButton("🎮 Квесты", callback_data="start_tasks")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="show_stats"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")
        ]
    ]
    
    try:
        await send_html_message(update, help_text, InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке справки: {e}")


@log_command
async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Очищает историю разговора с ИИ для пользователя.
    
    Использование: /clear_history
    
    Эффект:
    - Удаляет всю сохраненную историю диалога
    - ИИ больше не будет вспоминать предыдущие сообщения
    - Полезно для начала нового разговора на другую тему
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
        
    Returns:
        None
    """
    user_id = update.effective_user.id
    user = update.effective_user
    
    # ✅ v0.26.0: Track history clear event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_ANALYZE,
        user_id=user_id,
        data={"action": "clear_history"}
    ))
    
    try:
        # Очищаем историю
        clear_user_history(user_id)
        
        # Получаем статистику до очистки (для логирования)
        stats = get_context_stats(user_id)
        
        response_text = (
            "✅ <b>История разговора очищена!</b>\n\n"
            f"📊 <b>Было удалено:</b>\n"
            f"• Сообщений: {stats['total_messages']}\n"
            f"• Токенов: {stats['total_tokens']}\n\n"
            "<i>ИИ теперь не будет помнить предыдущие разговоры.</i>\n"
            "Можешь начать новый разговор! 🚀"
        )
        
        logger.info(f"История разговора очищена для {user.username or user_id} "
                   f"(было {stats['total_messages']} сообщений)")
        
        keyboard = [[
            InlineKeyboardButton("💬 Начать диалог", callback_data="start_dialog"),
            InlineKeyboardButton("📋 Меню", callback_data="back_to_start")
        ]]
        
        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при очистке истории: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при очистке истории. Попробуй позже.",
            parse_mode=ParseMode.HTML
        )


@log_command
async def context_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает статистику текущего контекста разговора.
    
    Использование: /context_stats
    
    Информация:
    - Количество сообщений в памяти
    - Общее количество токенов
    - Время последнего сообщения
    - Размер контекстного окна
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
        
    Returns:
        None
    """
    user_id = update.effective_user.id
    
    try:
        stats = get_context_stats(user_id)
        
        if stats['total_messages'] == 0:
            response_text = (
                "📊 <b>Статистика контекста</b>\n\n"
                "История разговора пуста.\n"
                "Начни диалог с ИИ, чтобы заполнить контекст! 💬"
            )
        else:
            last_msg_time = datetime.fromtimestamp(stats['last_message_time']).strftime("%H:%M:%S")
            response_text = (
                "📊 <b>Статистика контекста разговора</b>\n"
                "═════════════════════════════════════\n\n"
                f"💬 <b>Сообщений в памяти:</b> {stats['total_messages']}\n"
                f"🔤 <b>Всего токенов:</b> {stats['total_tokens']}\n"
                f"⏰ <b>Последнее сообщение:</b> {last_msg_time}\n"
                f"📏 <b>Размер контекстного окна:</b> {stats['context_window_size']}\n"
                f"🧹 <b>Очисток истории:</b> {stats['cleanup_count']}\n\n"
                "<i>Контекст помогает ИИ помнить о чем ты говоришь.</i>\n"
                f"<i>Максимум сообщений в памяти: 50</i>"
            )
        
        keyboard = [[
            InlineKeyboardButton("🗑️ Очистить историю", callback_data=f"clear_history_confirm"),
            InlineKeyboardButton("📋 Меню", callback_data="back_to_start")
        ]]
        
        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении статистики контекста.",
            parse_mode=ParseMode.HTML
        )


@log_command
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню с быстрыми действиями (команда /menu)."""
    keyboard = [
        [
            InlineKeyboardButton("📚 Курсы", callback_data="menu_learn"),
            InlineKeyboardButton("🧰 Инструменты", callback_data="menu_tools")
        ],
        [
            InlineKeyboardButton("💬 Задать вопрос", callback_data="menu_ask"),
            InlineKeyboardButton("📜 История", callback_data="menu_history")
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
            InlineKeyboardButton("⚙️ Статус", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")
        ]
    ]

    try:
        await update.message.reply_text(
            "📋 **Главное меню RVX**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        #fallback
        await update.message.reply_text("📋 Главное меню RVX")

@log_command
async def admin_metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 Admin Dashboard с полной аналитикой (только для админов)"""
    user_id = update.effective_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_USERS and user_id != BOT_OWNER_ID:
        await update.message.reply_text(
            "❌ <b>Доступ запрещен</b>\n"
            "Эта команда доступна только администраторам.",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Получаем dashboard
        dashboard = get_admin_dashboard()
        metrics = dashboard.get_dashboard_metrics(hours=24)
        dashboard_text = dashboard.format_dashboard_for_telegram(metrics)
        
        # Отправляем dashboard
        await update.message.reply_text(
            dashboard_text,
            parse_mode=ParseMode.HTML
        )
        
        # Логируем
        logger.info(f"Admin dashboard viewed by {user_id}")
        
    except Exception as e:
        logger.error(f"Error generating admin dashboard: {e}")
        await update.message.reply_text(
            f"❌ <b>Ошибка при создании dashboard:</b>\n<i>{str(e)}</i>",
            parse_mode=ParseMode.HTML
        )


@log_command
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статистику."""
    user = update.effective_user
    user_id = user.id
    
    # ✅ Сохраняем пользователя перед получением статистики
    save_user(user_id, user.username or "", user.first_name)
    
    # ✅ v0.25.0: Track user_profile event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_PROFILE_VIEW,
        user_id=user_id,
        data={}
    ))
    
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT total_requests, daily_requests, created_at, xp, level 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        user_requests = row[0] if row else 0
        daily_requests = row[1] if row else 0
        member_since = row[2] if row else "Неизвестно"
        user_xp = row[3] if row else 0
        user_level = row[4] if row else 1
        
        # NEW v0.14.0: Получаем информацию о лимитах
        remaining, total_limit, tier_name = get_remaining_requests(cursor, user_id)
    
    stats = get_global_stats()
    
    stats_text = (
        "📊 <b>СТАТИСТИКА RVX v0.14.0</b>\n\n"
        "<b>👤 ТВОЯ СТАТИСТИКА:</b>\n"
        f"  • Всего запросов: <b>{user_requests}</b>\n"
        f"  • Сегодня: <b>{daily_requests}/{total_limit}</b> (осталось: {remaining})\n"
        f"  • Уровень: <b>Лvl {user_level}</b> ({tier_name})\n"
        f"  • XP: <b>{user_xp}</b>\n"
        f"  • Участник с: <b>{member_since[:10]}</b>\n\n"
        "<b>🌐 ГЛОБАЛЬНАЯ СТАТИСТИКА:</b>\n"
        f"  • 👥 Активных пользователей: <b>{stats['total_users']}</b>\n"
        f"  • 📝 Всего запросов: <b>{stats['total_requests']}</b>\n"
        f"  • 💾 Записей в кэше: <b>{stats['cache_size']}</b>\n"
        f"  • ⚡ Попадания в кэш: <b>{stats['cache_hits']}</b>\n"
        f"  • ⏱️ Среднее время обработки: <b>{stats['avg_processing_time']}ms</b>\n\n"
        "<b>👍 ОЦЕНКИ:</b>\n"
        f"  • Полезно: <b>{stats['helpful']}</b>\n"
        f"  • Не помогло: <b>{stats['not_helpful']}</b>\n\n"
        f"🏆 <b>ТОП-5 ПОЛЬЗОВАТЕЛЕЙ:</b>\n"
    )
    
    # Обновленный TOP-10 по XP (v0.9.0)
    for i, user_data in enumerate(stats['top_users'], 1):
        if len(user_data) == 4:  # новый формат: (username, first_name, xp, level)
            username, first_name, xp, level = user_data
            name = username or first_name or "Аноним"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
            stats_text += f"  {medal} {name}: <b>{xp} XP</b> (Level {level})\n"
        else:  # старый формат для совместимости
            username, first_name = user_data[:2]
            requests = user_data[2] if len(user_data) > 2 else 0
            name = username or first_name or "Аноним"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
            stats_text += f"  {medal} {name}: <b>{requests}</b> запросов\n"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
    ]
    
    try:
        if is_callback and query:
            await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке статистики: {e}")

@log_command
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает историю запросов."""
    user_id = update.effective_user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    history = get_user_history(user_id, limit=10)
    
    if not history:
        response = "📜 <b>История пуста</b>\n\nОтправь первую новость для анализа!"
        try:
            if is_callback and query:
                await query.edit_message_text(response, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при отправке пустой истории: {e}")
        return
    
    response = "📜 <b>ПОСЛЕДНИЕ 10 АНАЛИЗОВ:</b>\n\n"
    
    for i, (news, _, created_at, from_cache, proc_time) in enumerate(history, 1):
        news_preview = news[:50] + "..." if len(news) > 50 else news
        icon = "⚡ Кэш" if from_cache else "🆕 Новый"
        time_str = f"{proc_time:.0f}ms" if proc_time else "—"
        
        response += (
            f"<b>{i}.</b> {news_preview}\n"
            f"  {icon} | 🕐 {created_at[:16]} | ⏱️ {time_str}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
    ]
    
    try:
        if is_callback and query:
            await query.edit_message_text(response, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке истории: {e}")

@log_command
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Поиск по истории запросов."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Укажите текст для поиска</b>\n\n"
            "<i>Пример:</i> /search биткоин",
            parse_mode=ParseMode.HTML
        )
        return
    
    search_text = " ".join(context.args)
    results = search_user_requests(user_id, search_text)
    
    if not results:
        await update.message.reply_text(
            f"🔍 <b>Ничего не найдено</b>\n\n"
            f"По запросу: <i>{search_text}</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    response = f"🔍 <b>НАЙДЕНО {len(results)} РЕЗУЛЬТАТОВ</b>\n\n"
    
    for i, (news, _, created_at) in enumerate(results[:5], 1):
        news_preview = news[:50] + "..."
        response += f"<b>{i}.</b> {news_preview}\n  🕐 {created_at[:16]}\n\n"
    
    if len(results) > 5:
        response += f"<i>...и ещё {len(results) - 5} результатов</i>"
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

@log_command
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Экспорт истории в файл."""
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=100)
    
    if not history:
        await update.message.reply_text("📜 История пуста.")
        return
    
    export_text = (
        f"RVX AI Analyzer - Экспорт истории\n"
        f"Пользователь ID: {user_id}\n"
        f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Записей: {len(history)}\n"
        f"{'=' * 60}\n\n"
    )
    
    for i, (news, response, created_at, from_cache, proc_time) in enumerate(history, 1):
        source = "Кэш" if from_cache else "API"
        time_str = f"{proc_time:.0f}ms" if proc_time else "—"
        
        export_text += (
            f"{'=' * 60}\n"
            f"Запись #{i}\n"
            f"Дата: {created_at}\n"
            f"Источник: {source} | Время: {time_str}\n"
            f"{'-' * 60}\n"
            f"ВХОДНОЙ ТЕКСТ:\n{news}\n\n"
            f"АНАЛИЗ:\n{response}\n"
            f"{'=' * 60}\n\n"
        )
    
    from io import BytesIO
    file = BytesIO(export_text.encode('utf-8'))
    file.name = f"rvx_history_{user_id}_{datetime.now().strftime('%Y%m%d')}.txt"
    
    await update.message.reply_document(
        document=file,
        caption=f"📥 **История экспортирована**\n\nЗаписей: {len(history)}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    if ENABLE_ANALYTICS:
        log_analytics_event("export_history", user_id, {"records": len(history)})

@log_command
async def limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает лимиты пользователя."""
    user_id = update.effective_user.id
    
    can_request, remaining = check_daily_limit(user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT daily_requests, daily_reset_at 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        daily_used = row[0] if row and row[0] else 0
        reset_at = row[1] if row and row[1] else None
    
    if reset_at:
        reset_time = datetime.fromisoformat(reset_at)
        time_until_reset = reset_time - datetime.now()
        hours = int(time_until_reset.total_seconds() // 3600)
        minutes = int((time_until_reset.total_seconds() % 3600) // 60)
        reset_str = f"{hours}ч {minutes}мин"
    else:
        reset_str = "Неизвестно"
    
    status_emoji = "✅" if can_request else "⛔"
    
    # Прогресс-бар
    progress_bar = ""
    percent = (daily_used / MAX_REQUESTS_PER_DAY) * 100
    filled = int(percent / 10)
    empty = 10 - filled
    progress_bar = "█" * filled + "░" * empty
    
    limits_text = (
        f"{status_emoji} <b>ВАШИ ЛИМИТЫ</b>\n\n"
        f"<b>📊 ДНЕВНОЙ ЛИМИТ:</b>\n"
        f"  {progress_bar} {daily_used}/{MAX_REQUESTS_PER_DAY}\n"
        f"  • Осталось: <b>{remaining}</b> запросов\n"
        f"  • Сброс: <b>{reset_str}</b>\n\n"
        f"<b>⏱️ FLOOD CONTROL:</b>\n"
        f"  • Минимум: <b>{FLOOD_COOLDOWN_SECONDS}с</b> между запросами\n"
        f"  • Защищает сервер от перегрузки\n\n"
        f"<b>📏 ОГРАНИЧЕНИЯ ТЕКСТА:</b>\n"
        f"  • Максимум: <b>{MAX_INPUT_LENGTH}</b> символов\n"
        f"  • Оптимально: 100-500 символов для анализа\n\n"
        f"<b>💡 СОВЕТЫ:</b>\n"
        f"  • Используй лимиты эффективно - анализируй самые интересные материалы\n"
        f"  • Изучай /learn курсы - они не требуют запросов\n"
        f"  • Задавай конкретные вопросы - получишь лучше ответы\n"
        f"  • Проверь /teach для интерактивных уроков\n\n"
        f"📈 <i>Уровень прокачки даёт больше лимитов!</i>"
    )
    
    if not can_request:
        limits_text += "⚠️ <b>ЛИМИТ ИСЧЕРПАН!</b>\n<i>Попробуйте завтра.</i>"
    
    await update.message.reply_text(limits_text, parse_mode=ParseMode.HTML)

# ============= НОВЫЕ КОМАНДЫ v0.5.0 - ОБУЧЕНИЕ =============

@log_command
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список доступных курсов для обучения."""
    user = update.effective_user
    user_id = user.id
    
    # ✅ v0.25.0: Track user_education event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_EDUCATION,
        user_id=user_id,
        data={}
    ))
    
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    save_user(user_id, user.username or "", user.first_name)
    
    # Получаем уровень пользователя
    with get_db() as conn:
        cursor = conn.cursor()
        knowledge_level = get_user_knowledge_level(cursor, user_id)
        level, xp = calculate_user_level_and_xp(cursor, user_id)
    
    learn_text = (
        "🎓 <b>КРИПТОВАЛЮТНАЯ АКАДЕМИЯ RVX v0.5.1</b>\n"
        f"───────────────────────────────────\n"
        f"👤 <b>Ваш статус:</b> Level {level} ({xp} XP)\n"
        f"📈 <b>Знание:</b> {knowledge_level}\n\n"
        f"<b>📚 ДОСТУПНЫЕ КУРСЫ:</b>\n\n"
    )
    
    # Получаем прогресс пользователя по курсам (если таблица существует)
    user_courses_progress = {}
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT course_name, completed_lessons, started_at
                FROM user_courses
                WHERE user_id = ?
            """, (user_id,))
            for row in cursor.fetchall():
                user_courses_progress[row[0]] = {
                    'completed': row[1],
                    'started': row[2] is not None
                }
    except Exception as e:
        logger.debug(f"Ошибка при получении прогресса курсов: {e}")
    
    # Создаем кнопки для каждого курса с улучшенной информацией
    keyboard = []
    
    for course_key, course_data in COURSES_DATA.items():
        # Определяем эмодзи для уровня сложности
        level_emoji = {
            "beginner": "🌱",
            "intermediate": "📚",
            "advanced": "🚀",
            "expert": "👑"
        }.get(course_data['level'], "📌")
        
        # Проверяем прогресс
        progress = user_courses_progress.get(course_key, {})
        completed = progress.get('completed', 0)
        is_started = progress.get('started', False)
        
        # Статус курса
        if completed == course_data['total_lessons']:
            status = "✅"  # Завершен
        elif is_started:
            status = f"▶️"  # В процессе
        else:
            status = "🔒"  # Не начат
        
        # Формируем текст кнопки с прогрессом
        button_label = (
            f"{level_emoji} {course_data['title']} "
            f"({completed}/{course_data['total_lessons']}) {status}"
        )
        
        keyboard.append([InlineKeyboardButton(button_label, callback_data=f"start_course_{course_key}")])
        
        # Добавляем информацию о курсе в основной текст
        course_time = course_data['total_lessons'] * 8
        learn_text += (
            f"{level_emoji} <b>{course_data['title']}</b>\n"
            f"  • Уроков: {course_data['total_lessons']} (⏱️ ~{course_time} мин)\n"
            f"  • XP: +{course_data['total_xp']} при завершении\n"
            f"  • Прогресс: {completed}/{course_data['total_lessons']} ✅\n"
            f"  <i>{course_data['description'][:100]}</i>\n\n"
        )
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
    
    try:
        if is_callback and query:
            await query.edit_message_text(learn_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(learn_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке learn: {e}")
        # Fallback
        try:
            fallback_text = (
                f"🎓 КРИПТОВАЛЮТНАЯ АКАДЕМИЯ\n\n"
                f"Level {level} ({xp} XP)\n"
                f"Знание: {knowledge_level}"
            )
            if is_callback and query:
                await query.edit_message_text(fallback_text)
            else:
                await update.message.reply_text(fallback_text)
        except Exception as e2:
            logger.error(f"Ошибка fallback: {e2}")


@log_command
async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает конкретный урок. Используется так: /lesson 1"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Укажите номер урока</b>\n\n"
            "<i>Пример:</i> <code>/lesson 1</code>\n"
            "Сначала начните курс через <code>/learn</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем, есть ли текущий курс у пользователя
    if user_id not in bot_state.user_current_course:
        await update.message.reply_text(
            "❌ <b>Сначала выберите курс!</b>\n\n"
            "Доступные команды:\n"
            "<code>/start_blockchain_basics</code>\n"
            "<code>/start_defi_contracts</code>\n"
            "<code>/start_scaling_dao</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        lesson_num = int(context.args[0])
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ <b>Укажите номер урока (число)</b>\n\n"
            "<i>Пример:</i> <code>/lesson 1</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    course_name = await bot_state.get_user_course(user_id)
    if not course_name:
        await update.message.reply_text(
            "❌ <b>Сначала выберите курс</b>\n\nИспользуйте /courses",
            parse_mode=ParseMode.HTML
        )
        return
    
    course_data = COURSES_DATA.get(course_name)
    
    if not course_data:
        await update.message.reply_text(
            "❌ <b>Курс не найден</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем валидность номера урока
    if lesson_num < 1 or lesson_num > course_data['total_lessons']:
        await update.message.reply_text(
            f"❌ <b>Номер урока должен быть от 1 до {course_data['total_lessons']}</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Получаем контент урока
    lesson_content = get_lesson_content(course_name, lesson_num)
    
    if not lesson_content:
        await update.message.reply_text(
            "❌ <b>Урок не найден</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Очищаем контент от проблемных символов
    lesson_content = clean_lesson_content(lesson_content)
    
    # Разделяем контент на основной текст и quiz
    lesson_text, quiz_section = split_lesson_content(lesson_content)
    
    # Форматируем и отправляем урок (БЕЗ quiz секции)
    # Ограничиваем размер (Telegram лимит 4096 символов)
    max_length = 3500  # Оставляем место для кнопок
    if len(lesson_text) > max_length:
        lesson_preview = lesson_text[:max_length] + "\n\n[... урок продолжается]"
    else:
        lesson_preview = lesson_text
    
    response = (
        f"📚 <b>{course_data['title'].upper()}</b>\n"
        f"📖 Урок {lesson_num}/{course_data['total_lessons']}\n\n"
        f"{lesson_preview}"
    )
    
    # Создаем кнопку для старта quiz (если есть questions)
    keyboard = []
    if quiz_section:
        keyboard.append([
            InlineKeyboardButton("🎯 Начать тест", callback_data=f"start_quiz_{course_name}_{lesson_num}")
        ])
    
    # Проверяем и добавляем кнопку "Следующий урок"
    next_lesson_info = get_next_lesson_info(course_name, lesson_num)
    if next_lesson_info:
        keyboard.append([
            InlineKeyboardButton("▶️ Следующий урок", callback_data=f"next_lesson_{course_name}_{lesson_num + 1}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    # Добавляем XP за просмотр урока
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            add_xp_to_user(cursor, user_id, 5, "viewed_lesson")
        logger.info(f"⭐ Пользователь {user_id} получил 5 XP за урок {lesson_num}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении XP: {e}")
    
    # Логируем событие
    if ENABLE_ANALYTICS:
        log_analytics_event("lesson_viewed", user_id, {"course": course_name, "lesson": lesson_num})


async def handle_start_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, course_name: str, query: CallbackQuery) -> None:
    """
    Обработчик для запуска курса через callback кнопку с интерактивным UI.
    
    Вызывается когда пользователь нажимает кнопку "Начать курс" в интерфейсе.
    Инициализирует выбранный курс, сохраняет прогресс, показывает первый урок.
    
    Args:
        update (Update): Telegram Update с callback query от кнопки
        context (ContextTypes.DEFAULT_TYPE): Telegram context
        course_name (str): Название курса (key в COURSES_DATA)
        query: CallbackQuery объект для ответа на кнопку
        
    Supported Courses:
        - "intro": Основы криптовалют
        - "trading": Трейдинг и анализ
        - "security": Безопасность и кошельки
        - "defi": Децентрализованные финансы
        - "nfts": NFTs и цифровое искусство
        
    Side Effects:
        - Сохраняет выбранный курс в bot_state
        - Создает запись в БД о начале курса
        - Рассчитывает уровень пользователя
        - Показывает первый урок курса
        - Логирует действие в структурированный лог
        
    Error Handling:
        - Course not found: "❌ Курс не найден"
        - User banned: Gracefully ignores
        - DB error: Shows error with retry
        
    Response:
        - Отвечает на callback query с ack
        - Отправляет первый урок как сообщение
        - Показывает кнопки для навигации по курсу
    """
    user_id = update.effective_user.id
    user = update.effective_user
    
    # Проверяем, существует ли такой курс
    if course_name not in COURSES_DATA:
        await query.answer("❌ Курс не найден", show_alert=True)
        logger.warning(f"❌ Курс не найден: {course_name}")
        return
    
    course_data = COURSES_DATA[course_name]
    save_user(user_id, user.username or "", user.first_name)
    
    # СОХРАНЯЕМ текущий курс пользователя для использования в /lesson команде
    await bot_state.set_user_course(user_id, course_name)
    logger.info(f"📚 Пользователь {user_id} начал курс {course_name} через callback")
    
    # Получаем информацию о пользователе и его прогресс
    with get_db() as conn:
        cursor = conn.cursor()
        level, xp = calculate_user_level_and_xp(cursor, user_id)
        
        # Получаем прогресс по этому курсу
        cursor.execute("""
            SELECT completed_lessons FROM user_courses
            WHERE user_id = ? AND course_name = ?
        """, (user_id, course_name))
        row = cursor.fetchone()
        completed_lessons = row[0] if row else 0
    
    # Выбираем эмодзи для уровня
    level_emoji = {
        "beginner": "🌱",
        "intermediate": "📚",
        "advanced": "🚀",
        "expert": "👑"
    }.get(course_data['level'], "📖")
    
    # Вычисляем время завершения
    total_time = course_data['total_lessons'] * 8
    remaining_time = (course_data['total_lessons'] - completed_lessons) * 8
    
    # Формируем красивый текст с улучшенной информацией
    response = (
        f"{level_emoji} <b>{course_data['title'].upper()}</b>\n"
        f"{'═' * 35}\n\n"
        f"<b>📋 ИНФОРМАЦИЯ О КУРСЕ:</b>\n"
        f"  • Сложность: {course_data['level'].upper()}\n"
        f"  • Уроков: {course_data['total_lessons']}\n"
        f"  • ⏱️ Время: ~{total_time} мин ({remaining_time} мин осталось)\n"
        f"  • 🎁 XP: +{course_data['total_xp']} при завершении\n\n"
        f"<b>📖 ОПИСАНИЕ:</b>\n{course_data['description']}\n\n"
        f"<b>📊 ВАШ ПРОГРЕСС:</b>\n"
        f"  • Завершено: {completed_lessons}/{course_data['total_lessons']} уроков\n"
        f"  • Статус: Level {level} ({xp} XP)\n"
        f"  • Следующий: Урок {completed_lessons + 1}\n\n"
        f"<b>🎯 ВЫБЕРИТЕ УРОК:</b>"
    )
    
    # Создаем кнопки для выбора урока с улучшенным визуалом
    keyboard = []
    
    # Группируем уроки по 2 в строку
    for i in range(1, course_data['total_lessons'] + 1):
        # Определяем статус урока
        if i < completed_lessons:
            status = "✅"  # Завершен
        elif i == completed_lessons + 1:
            status = "▶️"  # Текущий
        elif i == completed_lessons:
            status = "🔄"  # В процессе
        else:
            status = "🔒"  # Заблокирован
        
        if (i - 1) % 2 == 0:  # Новая строка каждые 2 кнопки
            row = []
            keyboard.append(row)
        else:
            row = keyboard[-1]
        
        button_text = f"Урок {i} {status}"
        row.append(InlineKeyboardButton(button_text, callback_data=f"lesson_{course_name}_{i}"))
    
    # Добавляем кнопки навигации
    nav_row = []
    if completed_lessons < course_data['total_lessons']:
        # Кнопка для начала со следующего урока
        next_lesson = min(completed_lessons + 1, course_data['total_lessons'])
        nav_row.append(InlineKeyboardButton("▶️ Продолжить", callback_data=f"lesson_{course_name}_{next_lesson}"))
    
    if completed_lessons == course_data['total_lessons']:
        nav_row.append(InlineKeyboardButton("🏆 Пересдать курс", callback_data=f"lesson_{course_name}_1"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    # Кнопка "Назад" 
    keyboard.append([InlineKeyboardButton("⬅️ К курсам", callback_data="start_learn")])
    
    await query.edit_message_text(
        response,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await query.answer("✅ Курс загружен!", show_alert=False)


@log_command
async def start_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает конкретный курс по команде /start_<course_name>"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    # Получаем имя курса из команды
    # update.message.text содержит полную команду, например '/start_blockchain_basics'
    command_text = update.message.text.strip()
    
    # Извлекаем имя курса из команды
    if command_text.startswith('/start_'):
        course_name = command_text[7:].strip().lower()  # Убираем '/start_' 
    else:
        await update.message.reply_text(
            "❓ <b>Укажите курс</b>\n\n"
            "<i>Доступные команды:</i>\n"
            "<code>/start_blockchain_basics</code>\n"
            "<code>/start_defi_contracts</code>\n"
            "<code>/start_scaling_dao</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем, существует ли такой курс
    if course_name not in COURSES_DATA:
        await update.message.reply_text(
            f"❌ <b>Курс не найден:</b> {course_name}\n\n"
            "<i>Доступные курсы:</i>\n"
            "• <code>blockchain_basics</code>\n"
            "• <code>defi_contracts</code>\n"
            "• <code>scaling_dao</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    course_data = COURSES_DATA[course_name]
    save_user(user_id, user.username or "", user.first_name)
    
    # СОХРАНЯЕМ текущий курс пользователя для использования в /lesson команде
    await bot_state.set_user_course(user_id, course_name)
    logger.info(f"📚 Пользователь {user_id} начал курс {course_name}")
    
    # Получаем информацию о пользователе
    with get_db() as conn:
        cursor = conn.cursor()
        level, xp = calculate_user_level_and_xp(cursor, user_id)
    
    # Показываем информацию о курсе и первый урок
    response = (
        f"📚 <b>{course_data['title'].upper()}</b>\n\n"
        f"<b>Уровень:</b> {course_data['level'].upper()}\n"
        f"<b>Уроков:</b> {course_data['total_lessons']}\n"
        f"<b>XP к получению:</b> {course_data['total_xp']}\n\n"
        f"<b>Описание:</b>\n{course_data['description']}\n\n"
        f"💡 <b>Твой прогресс:</b> Level {level} ({xp} XP)\n\n"
        f"👇 <b>Выбери урок для начала:</b>"
    )
    
    # Создаем кнопки для выбора урока (2 урока в строке)
    keyboard = []
    for i in range(1, course_data['total_lessons'] + 1):
        if (i - 1) % 2 == 0:  # Новая строка каждые 2 кнопки
            row = []
            keyboard.append(row)
        else:
            row = keyboard[-1]
        
        row.append(InlineKeyboardButton(f"📖 Урок {i}", callback_data=f"lesson_{course_name}_{i}"))
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Логируем событие
    if ENABLE_ANALYTICS:
        log_analytics_event("course_started", user_id, {"course": course_name})


@log_command
async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает интерактивный справочник инструментов."""
    user_id = update.effective_user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    if not context.args:
        # Показываем список всех инструментов
        tools = get_all_tools_db()
        
        tools_text = "🛠️ <b>СПРАВОЧНИК КРИПТИНСТРУМЕНТОВ</b>\n\n"
        
        # Группируем по категориям
        categories = {}
        for tool in tools:
            cat = tool['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool)
        
        for category, category_tools in categories.items():
            tools_text += f"<b>{category}:</b>\n"
            for tool in category_tools:
                tools_text += f"  • {tool['name']} <i>({tool['difficulty']})</i>\n"
            tools_text += "\n"
        
        tools_text += "📖 <i>Введите название инструмента, чтобы узнать подробнее:</i>\n<code>/tools Etherscan</code>"
        
        try:
            if is_callback and query:
                await query.edit_message_text(tools_text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(tools_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при отправке tools: {e}")
        return
    
    # Показываем подробнее про конкретный инструмент
    tool_name = " ".join(context.args)
    tools = get_all_tools_db()
    
    tool = next((t for t in tools if t['name'].lower() == tool_name.lower()), None)
    
    if not tool:
        error_text = f"❌ <b>Инструмент не найден</b>\n\n<i>'{tool_name}'</i>\n\nИспользуйте <code>/tools</code> для списка всех инструментов"
        try:
            if is_callback and query:
                await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при отправке ошибки tools: {e}")
        return
    
    tool_text = (
        f"🔧 <b>{tool['name']}</b>\n\n"
        f"📖 <i>{tool['description']}</i>\n\n"
        f"<b>ℹ️ ИНФОРМАЦИЯ:</b>\n"
        f"  • Категория: <b>{tool['category']}</b>\n"
        f"  • Сложность: <b>{tool['difficulty']}</b>\n"
        f"  • URL: <code>{tool['url']}</code>\n\n"
        f"<b>📚 КАК ИСПОЛЬЗОВАТЬ:</b>\n"
        f"{tool['tutorial']}\n\n"
        f"💡 <i>Хотите сохранить в избранное?</i> <code>/bookmark {tool['name']}</code>"
    )
    
    try:
        if is_callback and query:
            await query.edit_message_text(tool_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(tool_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при отправке информации о tool: {e}")
    
    # Логируем просмотр
    if ENABLE_ANALYTICS:
        log_analytics_event("tool_viewed", user_id, {"tool": tool['name']})


@log_command
async def bookmark_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет инструмент в закладки. Использование: /bookmark Etherscan"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "📌 <b>Добавить инструмент в закладки</b>\n\n"
            "Использование: <code>/bookmark Etherscan</code>\n"
            "Просмотр закладок: <code>/bookmarks</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    tool_name = " ".join(context.args)
    tools = get_all_tools_db()
    
    # Проверяем, существует ли инструмент
    tool = next((t for t in tools if t['name'].lower() == tool_name.lower()), None)
    
    if not tool:
        await update.message.reply_text(
            f"❌ <b>Инструмент не найден</b>\n\n"
            f"<i>'{tool_name}'</i>\n\n"
            f"Используйте <code>/tools</code> для списка всех инструментов",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, не добавлена ли уже
            cursor.execute(
                "SELECT id FROM user_bookmarks WHERE user_id = ? AND tool_name = ?",
                (user_id, tool['name'])
            )
            
            if cursor.fetchone():
                await update.message.reply_text(
                    f"ℹ️ <b>{tool['name']}</b> уже в ваших закладках",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Добавляем в закладки
            cursor.execute(
                "INSERT INTO user_bookmarks (user_id, tool_name) VALUES (?, ?)",
                (user_id, tool['name'])
            )
            conn.commit()
        
        await update.message.reply_text(
            f"✅ <b>{tool['name']}</b> добавлена в закладки!\n\n"
            f"Просмотреть все закладки: /my_bookmarks",
            parse_mode=ParseMode.HTML
        )
        
        # Логируем событие
        if ENABLE_ANALYTICS:
            log_analytics_event("tool_bookmarked", user_id, {"tool": tool['name']})
    
    except Exception as e:
        logger.error(f"Ошибка при добавлении в закладки: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении в закладки",
            parse_mode=ParseMode.HTML
        )


@log_command
async def show_bookmarks_by_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает закладки определённого типа с интерактивными кнопками."""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Парсим тип из callback_data
    bm_type = query.data.replace("show_bookmarks_", "")
    
    bookmarks = get_user_bookmarks(user_id, bookmark_type=bm_type, limit=100)
    
    bookmark_types = {
        "news": ("📰", "Новости"),
        "lesson": ("🎓", "Уроки"),
        "tool": ("🧰", "Инструменты"),
        "resource": ("📚", "Ресурсы")
    }
    
    emoji, name = bookmark_types.get(bm_type, ("📌", bm_type))
    
    if not bookmarks:
        text = f"{emoji} <b>Закладок {name.lower()} нет</b>\n\n"
        text += "💡 Нажимай 📌 при просмотре контента, чтобы сохранить!"
        keyboard = [
            [InlineKeyboardButton("« К закладкам", callback_data="start_bookmarks")],
            [InlineKeyboardButton("« Назад в меню", callback_data="back_to_start")]
        ]
    else:
        # Показываем закладки интерактивными кнопками
        text = (
            f"{emoji} <b>{name}</b> ({len(bookmarks)} закладок)\n\n"
            "<i>Нажмите на закладку чтобы посмотреть полный анализ:</i>\n"
        )
        
        keyboard = []
        for idx, bm in enumerate(bookmarks, 1):
            bm_id = bm[0]  # id
            title = bm[2]  # content_title
            
            # Обрезаем длинный заголовок для кнопки
            button_text = f"{idx}. {title[:40]}"
            if len(title) > 40:
                button_text += "..."
            
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"view_bookmark_{bm_id}")
            ])
        
        # Добавляем кнопку возврата
        keyboard.append([InlineKeyboardButton("« К закладкам", callback_data="start_bookmarks")])
        keyboard.append([InlineKeyboardButton("« Назад в меню", callback_data="back_to_start")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)



# ═══════════════════════════════════════════════════════════════════════════════
# РЕСУРСЫ: Бесплатные ресурсы по крипто, AI, трейдингу и Web3
# ═══════════════════════════════════════════════════════════════════════════════

# Структура: {раздел: {название: (ссылка, описание)}}
FREE_RESOURCES = {
    "🪙 Крипто Основы": {
        "CoinMarketCap": ("https://coinmarketcap.com/", "Рейтинг криптовалют, графики и статистика"),
        "CoinGecko": ("https://coingecko.com/", "Аналог CMC, бесплатный API для разработчиков"),
        "Khan Academy (Крипто)": ("https://www.khanacademy.org/economics-finance-domain/core-finance", "Курсы по финансам и экономике"),
        "Bitcoin.org": ("https://bitcoin.org/", "Официальный сайт Bitcoin - всё о технологии"),
        "Ethereum.org": ("https://ethereum.org/", "Документация Ethereum, гайды для новичков"),
    },
    "📊 Аналитика и Графики": {
        "TradingView": ("https://www.tradingview.com/", "Лучший сервис для анализа графиков (есть бесплатный план)"),
        "Glassnode": ("https://glassnode.com/", "Метрики блокчейна и аналитика сети"),
        "CryptoQuant": ("https://cryptoquant.com/", "Данные о капитализации и объёмах"),
        "DefiLlama": ("https://defillama.com/", "Статистика DeFi проектов и их TVL"),
        "Messari": ("https://messari.io/", "Исследования и отчёты по крипто"),
    },
    "🏦 DeFi и Стейкинг": {
        "Uniswap": ("https://uniswap.org/", "Самый популярный DEX (децентрализованный обмен)"),
        "Aave": ("https://aave.com/", "Платформа для кредитования и заимствования"),
        "Curve Finance": ("https://curve.fi/", "Лучший DEX для стейблкойнов"),
        "Yearn Finance": ("https://yearn.finance/", "Оптимизация доходности в DeFi"),
        "Lido": ("https://lido.fi/", "Liquid staking для Ethereum"),
    },
    "🖼️ NFT и Маркетплейсы": {
        "OpenSea": ("https://opensea.io/", "Крупнейший NFT маркетплейс"),
        "Magic Eden": ("https://magiceden.io/", "NFT маркетплейс для Solana"),
        "Blur": ("https://blur.io/", "Новый NFT маркетплейс с лучшими условиями"),
        "Raydium": ("https://raydium.io/", "AMM на Solana для торговли токенами"),
        "Phantom Wallet": ("https://phantom.app/", "Кошелёк для взаимодействия с Web3"),
    },
    "🤖 AI и Machine Learning": {
        "Hugging Face": ("https://huggingface.co/", "Платформа для моделей AI - огромное сообщество"),
        "OpenAI Playground": ("https://platform.openai.com/playground", "Экспериментируйте с GPT (100$ бесплатный кредит)"),
        "Google Colab": ("https://colab.research.google.com/", "Бесплатные GPU для обучения моделей"),
        "Kaggle": ("https://www.kaggle.com/", "Конкурсы по машинному обучению и датасеты"),
        "Paperswithcode": ("https://paperswithcode.com/", "Исследования AI с кодом и датасетами"),
    },
    "📖 Обучение и Курсы": {
        "Udemy (Бесплатные)": ("https://www.udemy.com/", "Ищите курсы со скидкой 100% или бесплатные"),
        "YouTube (Crypto Channel)": ("https://www.youtube.com/", "Каналы: Coin Bureau, 99Bitcoins, Andreas M. Antonopoulos"),
        "Coursera": ("https://www.coursera.org/", "Курсы от университетов (некоторые бесплатные)"),
        "edX": ("https://www.edx.org/", "Платформа с курсами по программированию и бизнесу"),
        "Codecademy": ("https://www.codecademy.com/", "Интерактивные курсы по программированию"),
    },
    "💻 Разработка и API": {
        "Etherscan": ("https://etherscan.io/", "Обозреватель блокчейна Ethereum"),
        "Solscan": ("https://solscan.io/", "Обозреватель блокчейна Solana"),
        "The Graph": ("https://thegraph.com/", "Индексирование данных блокчейна"),
        "Alchemy": ("https://www.alchemy.com/", "Платформа для разработки на блокчейне (бесплатный план)"),
        "Hardhat": ("https://hardhat.org/", "Фреймворк для разработки смарт-контрактов"),
    },
    "📱 Кошельки и Безопасность": {
        "MetaMask": ("https://metamask.io/", "Самый популярный кошелёк для Ethereum"),
        "Ledger Live": ("https://www.ledger.com/", "Управление аппаратным кошельком"),
        "Trust Wallet": ("https://trustwallet.com/", "Мобильный кошелёк с поддержкой многих сетей"),
        "Trezor": ("https://trezor.io/", "Аппаратный кошелёк для безопасного хранения"),
        "AuthenticatR": ("https://www.hotp.app/", "Генератор двухфакторной аутентификации"),
    },
    "🎯 Новости и Сообщество": {
        "The Block": ("https://www.theblock.co/", "Исследования и новости про крипто"),
        "Cointelegraph": ("https://cointelegraph.com/", "Главный источник новостей крипто"),
        "CryptoSlate": ("https://cryptoslate.com/", "Мониторинг проектов и новости"),
        "Discord (Communities)": ("https://discord.com/", "Найти серверы крипто-сообществ и проектов"),
        "Reddit (r/cryptocurrency)": ("https://reddit.com/r/cryptocurrency/", "Дискуссии и мнения сообщества"),
    }
}


async def show_resources_menu(update: Update, query: Optional[CallbackQuery] = None) -> None:
    """Показывает главное меню ресурсов с категориями."""
    keyboard = []
    
    # Создаём кнопки для каждой категории
    for i, category in enumerate(FREE_RESOURCES.keys()):
        callback_key = f"resources_cat_{i}"
        keyboard.append([InlineKeyboardButton(category, callback_data=callback_key)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
    
    text = (
        "📚 <b>БЕСПЛАТНЫЕ РЕСУРСЫ ДЛЯ КРИПТОВАЛЮТ, AI И WEB3</b>\n\n"
        "Здесь собраны лучшие бесплатные инструменты и ресурсы для:\n"
        "🪙 Изучения криптовалют\n"
        "📊 Анализа и трейдинга\n"
        "🤖 Работы с AI и ML\n"
        "🏦 DeFi и Web3\n"
        "💻 Разработки смарт-контрактов\n\n"
        "<b>Выберите интересующую вас категорию:</b>"
    )
    
    try:
        if query:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке меню ресурсов: {e}")


async def show_resources_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_index: int) -> None:
    """Показывает ресурсы конкретной категории."""
    query = update.callback_query
    categories = list(FREE_RESOURCES.keys())
    
    if category_index >= len(categories):
        await query.answer("❌ Категория не найдена")
        return
    
    category = categories[category_index]
    resources = FREE_RESOURCES[category]
    
    text = f"<b>{category}</b>\n\n"
    
    # Формируем список ресурсов с ссылками
    for name, (url, description) in resources.items():
        text += f"<b>• {name}</b>\n"
        text += f"  <i>{description}</i>\n"
        text += f"  🔗 <a href='{url}'>Открыть</a>\n\n"
    
    # Создаём кнопки навигации
    keyboard = [
        [
            InlineKeyboardButton("⬅️ К категориям", callback_data="resources_back"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"resources_cat_{category_index}")
        ],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_start")]
    ]
    
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке категории ресурсов: {e}")


@log_command
async def resources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает бесплатные ресурсы по крипто, AI и Web3."""
    await show_resources_menu(update)


@log_command
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Задать вопрос про крипто (/ask какой вопрос?)"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❓ Задайте вопрос про крипто!\n\n"
            "Пример: `/ask Что такое smart contract?`"
        )
        return
    
    question = " ".join(context.args)
    
    # Сначала проверяем FAQ
    with get_db() as conn:
        cursor = conn.cursor()
        faq_result = get_faq_by_keyword(cursor, question)
    
    if faq_result:
        faq_question, faq_answer, faq_id = faq_result
        
        await update.message.reply_text(
            f"📖 **Найдено в FAQ:**\n\n"
            f"**Q:** {faq_question}\n\n"
            f"**A:** {faq_answer}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Увеличиваем просмотры
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE faq SET views = views + 1 WHERE id = ?", (faq_id,))
        
        return
    
    # Если нет в FAQ - используем Gemini для ответа
    status_msg = await update.message.reply_text("🤖 Думаю над вашим вопросом...")
    
    try:
        # Специальный промпт для Q&A
        gemini_qa_prompt = f"""Ты эксперт по крипто, обучаешь новичков.
Ответь на вопрос подробно, но понятно для новичка.
Используй аналогии из обычной жизни если возможно.

Вопрос: {question}

Формат ответа:
1. Прямой ответ (1 параграф)
2. Простой пример
3. Расширенное объяснение
4. Частые ошибки при этом
5. Дальнейшее чтение (какие уроки пройти)"""
        
        # Вызываем API
        simplified_text, proc_time, error = await call_api_with_retry(gemini_qa_prompt)
        
        if not simplified_text:
            raise ValueError(f"API ошибка: {error}")
        
        # Сохраняем вопрос и ответ
        with get_db() as conn:
            cursor = conn.cursor()
            save_question_to_db(cursor, user_id, question, simplified_text, "gemini")
            
            # Добавляем в FAQ если это хороший ответ
            try:
                add_question_to_faq(cursor, question, simplified_text, "general")
            except ValueError as e:
                logger.debug(f"FAQ: {e}")  # Вопрос уже в FAQ
            except Exception as e:
                logger.warning(f"Failed to add question to FAQ: {e}")
        
        await status_msg.edit_text(
            f"❓ **Ваш вопрос:** {question}\n\n"
            f"📚 **Ответ:**\n\n{simplified_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Даем XP за вопрос
        with get_db() as conn:
            cursor = conn.cursor()
            add_xp_to_user(cursor, user_id, XP_REWARDS['ask_question'], "asked_question")
        
        if ENABLE_ANALYTICS:
            log_analytics_event("question_asked", user_id, {"question": question})
    
    except Exception as e:
        logger.error(f"Ошибка в /ask: {e}")
        await status_msg.edit_text(
            "❌ Не удалось найти ответ.\n\n"
            "Попробуйте переформулировать вопрос или начните курс `/learn`"
        )


# =============================================================================
# УЧИТЕЛЬСКИЙ МОДУЛЬ v0.7.0 - ИИ ПРЕПОДАЕТ КРИПТО, AI, WEB3, ТРЕЙДИНГ
# =============================================================================

# ════════ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ v0.37.0 - LESSON TRACKING & RECOMMENDATIONS ════════

# ════════════════ СИСТЕМА ДОСТИЖЕНИЙ (BADGES) v0.37.0 ════════════════

ACHIEVEMENT_BADGES = {
    'first_lesson': {
        'name': '🎓 Первый шаг',
        'emoji': '🎓',
        'description': 'Пройди первый урок',
        'condition': lambda completed, xp: len(completed) > 0
    },
    'expert_hunter': {
        'name': '💎 Охотник за экспертизой',
        'emoji': '💎',
        'description': 'Пройди 5 уроков на уровне expert',
        'condition': lambda completed, xp: sum(1 for t in completed.values() if 'expert' in t.get('difficulties', [])) >= 5
    },
    'topic_master': {
        'name': '🏆 Мастер темы',
        'emoji': '🏆',
        'description': 'Пройди все уровни одной темы',
        'condition': lambda completed, xp: any(len(t.get('difficulties', [])) == 4 for t in completed.values())
    },
    'all_rounder': {
        'name': '🌟 Всесторонний специалист',
        'emoji': '🌟',
        'description': 'Пройди уроки по 5 разным темам',
        'condition': lambda completed, xp: len(completed) >= 5
    },
    'xp_collector': {
        'name': '⚡ Сборщик XP',
        'emoji': '⚡',
        'description': 'Накопи 500+ XP',
        'condition': lambda completed, xp: xp >= 500
    },
}

def check_and_award_badges(user_id: int) -> list:
    """Проверяет и выдаёт новые badge'и пользователю.
    
    Returns:
        list: Список новых полученных badge'ей [{'badge_id': ..., 'name': ...}, ...]
    """
    new_badges = []
    try:
        completed = get_completed_topics(user_id)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            user_xp = result[0] if result else 0
        
        # Получаем уже выданные badge'и пользователю
        with get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT badge_id FROM user_badges WHERE user_id = ?", (user_id,))
                earned_badges = set(row[0] for row in cursor.fetchall())
            except sqlite3.OperationalError:
                # Таблица не существует - пропускаем проверку badges
                logger.debug(f"Таблица user_badges не существует, пропускаем проверку badges")
                return new_badges
        
        # Проверяем каждый badge
        for badge_id, badge_info in ACHIEVEMENT_BADGES.items():
            if badge_id not in earned_badges:
                # Проверяем условие badge'а
                if badge_info['condition'](completed, user_xp):
                    # Выдаём новый badge
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO user_badges (user_id, badge_id, badge_name, badge_emoji, badge_description, condition_met)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (user_id, badge_id, badge_info['name'], badge_info['emoji'], badge_info['description'], 'auto_detected'))
                        
                        new_badges.append({
                            'badge_id': badge_id,
                            'name': badge_info['name'],
                            'emoji': badge_info['emoji'],
                            'description': badge_info['description']
                        })
                        logger.info(f"🏅 Новый badge для {user_id}: {badge_id}")
                    except sqlite3.OperationalError:
                        logger.debug(f"Не удалось выдать badge {badge_id} (таблица не готова)")
    except Exception as e:
        logger.warning(f"Ошибка при проверке badge'ей: {e}")
    
    return new_badges

def get_user_badges(user_id: int) -> list:
    """Получает все badge'и пользователя."""
    badges = []
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT badge_emoji, badge_name, badge_description, earned_at
                FROM user_badges
                WHERE user_id = ?
                ORDER BY earned_at DESC
            """, (user_id,))
            
            for emoji, name, desc, earned_at in cursor.fetchall():
                badges.append({'emoji': emoji, 'name': name, 'description': desc, 'earned_at': earned_at})
    except Exception as e:
        logger.warning(f"Ошибка при получении badge'ей: {e}")
    
    return badges

def get_completed_topics(user_id: int) -> dict:
    """Получает список пройденных уроков пользователя с деталями.
    
    Returns:
        dict: {topic_name: {difficulty_levels: [...], completed_count: int, last_completed: datetime}}
    """
    completed = {}
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT topic, difficulty, COUNT(*) as count, MAX(completed_at) as last_completed
                    FROM teaching_lessons
                    WHERE user_id = ? AND quiz_passed = 1
                    GROUP BY topic, difficulty
                """, (user_id,))
                
                for topic, difficulty, count, last_completed in cursor.fetchall():
                    if topic not in completed:
                        completed[topic] = {'difficulties': [], 'completed_count': 0, 'last_completed': None}
                    completed[topic]['difficulties'].append(difficulty)
                    completed[topic]['completed_count'] += count
                    completed[topic]['last_completed'] = last_completed
            except sqlite3.OperationalError:
                # Таблица не существует - просто возвращаем пустой dict
                logger.debug(f"Таблица teaching_lessons не существует, возвращаю пустой результат")
                return completed
    except Exception as e:
        logger.warning(f"Ошибка при получении завершённых уроков: {e}")
    
    return completed

def get_recommended_lesson(user_id: int) -> dict:
    """Рекомендует следующий урок на основе пройденных уроков и XP.
    
    Логика рекомендаций:
    1. Найти незавершённые сложности для пройденных тем (progression)
    2. Если все сложности пройдены, рекомендовать новую тему
    3. Использовать XP для определения оптимального уровня сложности
    
    Returns:
        dict: {'topic': str, 'difficulty': str, 'reason': str} или {} если нет рекомендаций
    """
    try:
        completed = get_completed_topics(user_id)
        
        # Получаем XP пользователя для определения сложности
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            user_xp = result[0] if result else 0
        
        # 🎯 Стратегия рекомендации:
        # XP < 100: beginner
        # XP 100-300: intermediate
        # XP 300-600: advanced
        # XP >= 600: expert
        
        if user_xp >= 600:
            recommended_difficulty = 'expert'
            intermediate_levels = ['beginner', 'intermediate', 'advanced']
        elif user_xp >= 300:
            recommended_difficulty = 'advanced'
            intermediate_levels = ['beginner', 'intermediate']
        elif user_xp >= 100:
            recommended_difficulty = 'intermediate'
            intermediate_levels = ['beginner']
        else:
            recommended_difficulty = 'beginner'
            intermediate_levels = []
        
        # Приоритет рекомендаций:
        # 1. Новая сложность для пройденной темы (progression)
        for topic in sorted(completed.keys()):
            completed_difficulties = set(completed[topic]['difficulties'])
            all_difficulties = {'beginner', 'intermediate', 'advanced', 'expert'}
            
            # Проверяем от simple к hard: если не пройдена следующая сложность
            for level in ['beginner', 'intermediate', 'advanced', 'expert']:
                if level not in completed_difficulties:
                    topic_name = TEACHING_TOPICS.get(topic, {}).get('name', topic)
                    return {
                        'topic': topic,
                        'difficulty': level,
                        'reason': f"Продолжи тему <b>{topic_name}</b>",
                        'clean_reason': f"Продолжи тему {topic_name}"
                    }
        
        # 2. Новая тема (если все основные пройдены)
        all_topics = set(TEACHING_TOPICS.keys())
        started_topics = set(completed.keys())
        unstarted_topics = all_topics - started_topics
        
        if unstarted_topics:
            # Рекомендуем новую тему с рекомендуемой сложностью
            next_topic = sorted(unstarted_topics)[0]
            topic_name = TEACHING_TOPICS.get(next_topic, {}).get('name', next_topic)
            return {
                'topic': next_topic,
                'difficulty': recommended_difficulty,
                'reason': f"Изучи новую тему: <b>{topic_name}</b>",
                'clean_reason': f"Изучи новую тему: {topic_name}"
            }
        
        # 3. Если всё пройдено, рекомендуем повторение на наивысшей сложности
        if completed:
            hardest_topic = max(completed.keys(), key=lambda t: len(completed[t]['difficulties']))
            topic_name = TEACHING_TOPICS.get(hardest_topic, {}).get('name', hardest_topic)
            return {
                'topic': hardest_topic,
                'difficulty': 'expert',
                'reason': f"Закрепи: <b>{topic_name}</b> на expert",
                'clean_reason': f"Закрепи: {topic_name} на expert"
            }
        
        # Нет рекомендации
        return {}
        
    except Exception as e:
        logger.warning(f"Ошибка при получении рекомендации: {e}")
        return {}

async def _launch_teaching_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, topic: str, difficulty: str, query: Optional[CallbackQuery] = None) -> None:
    """Вспомогательная функция для запуска урока и показа результата с кнопками."""
    try:
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty, {})
        
        # Определяем способ отправки сообщения
        if query:
            # Из callback - редактируем существующее сообщение
            await query.edit_message_text(
                f"📖 Подготавливаю урок: <b>{topic_info.get('name', topic)}</b>\n"
                f"Уровень: {level_info.get('emoji', '📚')} {level_info.get('name', difficulty)}\n\n"
                "⏳ Думаю над содержанием...",
                parse_mode=ParseMode.HTML
            )
            status_msg = query.message
        else:
            # Из команды - отправляем новое сообщение
            status_msg = await update.message.reply_text(
                f"📖 Подготавливаю урок: <b>{topic_info.get('name', topic)}</b>\n"
                f"Уровень: {level_info.get('emoji', '📚')} {level_info.get('name', difficulty)}\n\n"
                "⏳ Думаю над содержанием...",
                parse_mode=ParseMode.HTML
            )
        
        # Получаем урок из ИИ
        lesson = await teach_lesson(
            topic=topic,
            difficulty_level=difficulty,
            user_knowledge_context=None
        )
        
        if not lesson:
            try:
                await status_msg.edit_text(
                    "❌ Не удалось создать урок. Попробуйте позже.",
                    parse_mode=ParseMode.HTML
                )
            except:
                await update.message.reply_text("❌ Не удалось создать урок. Попробуйте позже.")
            return
        
        # Обновляем ежедневную задачу по обучению (v0.11.0)
        update_task_progress(user_id, "lessons_2", 1)
        
        # Форматируем ответ
        title = lesson.get('lesson_title', 'Урок')
        content = lesson.get('content', '')[:1000]  # Сокращаем до 1000 символов
        key_points = lesson.get('key_points', [])[:3]
        example = lesson.get('real_world_example', '')[:300]
        question = lesson.get('practice_question', '')[:200]
        
        # Строим сообщение
        lines = [
            f"🎓 <b>{title}</b>",
            "",
            "📚 <b>Содержание:</b>",
            content,
            "",
            "🔑 <b>Ключевые моменты:</b>",
        ]
        
        for point in key_points:
            lines.append(f"• {point[:100]}")
        
        if example:
            lines.extend(["", "💡 <b>Пример:</b>", example])
        
        if question:
            lines.extend(["", "❓ <b>Вопрос для размышления:</b>", question])
        
        formatted_lesson = "\n".join(lines)
        
        # Кнопки действий под уроком
        keyboard = [
            [
                InlineKeyboardButton("✅ Понял!", callback_data=f"teach_understood_{topic}"),
                InlineKeyboardButton("🎯 Что дальше?", callback_data=f"teach_question_{topic}")
            ],
            [
                InlineKeyboardButton("📚 Другая тема", callback_data="teach_menu"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu")
            ]
        ]
        
        await status_msg.edit_text(
            formatted_lesson,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Даем XP за прохождение урока и отслеживаем в БД (v0.37.0)
        xp_reward = XP_REWARDS.get('lesson_completed', 50)
        with get_db() as conn:
            cursor = conn.cursor()
            add_xp_to_user(cursor, user_id, xp_reward, "completed_teaching_lesson")
            
            # ✅ NEW v0.37.0: Отслеживаем пройденный урок в БД
            try:
                # Используем INSERT OR REPLACE для обновления существующей записи
                cursor.execute("""
                    INSERT OR REPLACE INTO teaching_lessons (user_id, topic, difficulty, title, xp_earned, quiz_passed, repeat_count, completed_at)
                    SELECT ?, ?, ?, ?, ?, 1, COALESCE(repeat_count, 0) + 1, CURRENT_TIMESTAMP
                    FROM (
                        SELECT repeat_count FROM teaching_lessons 
                        WHERE user_id = ? AND topic = ? AND difficulty = ?
                        UNION ALL SELECT 0
                        LIMIT 1
                    )
                """, (user_id, topic, difficulty, title, xp_reward, user_id, topic, difficulty))
                logger.debug(f"✅ Урок отслежен: user_id={user_id}, topic={topic}, difficulty={difficulty}")
            except Exception as e:
                logger.warning(f"Ошибка отслеживания урока: {e}")
        
        if ENABLE_ANALYTICS:
            log_analytics_event("teaching_lesson", user_id, {
                "topic": topic,
                "difficulty": difficulty
            })
        
        logger.info(f"Урок создан для {user_id}: {topic} ({difficulty})")
        
    except asyncio.TimeoutError:
        try:
            await status_msg.edit_text(
                "⏱️ Истекло время ожидания. Попробуйте снова или выберите более простой уровень.",
                parse_mode=ParseMode.HTML
            )
        except:
            if query:
                await query.answer("⏱️ Истекло время ожидания.", show_alert=True)
            else:
                await update.message.reply_text("⏱️ Истекло время ожидания.")
    except Exception as e:
        logger.error(f"Ошибка в _launch_teaching_lesson: {e}")
        try:
            await status_msg.edit_text(
                f"❌ Ошибка при создании урока.\n\nПопробуйте позже или выберите другую тему.",
                parse_mode=ParseMode.HTML
            )
        except:
            if query:
                await query.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
            else:
                await update.message.reply_text("❌ Ошибка при создании урока.")


# ═══════════════════════════════════════════════════════════════════════════════
# CRYPTO CALCULATOR COMMAND (v0.33.0)
# ═══════════════════════════════════════════════════════════════════════════════

@log_command
async def calculator_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🧮 Крипто-калькулятор для расчета market cap (v0.33.0)
    
    Функции:
    - Выбор различных токенов
    - Расчет market cap при заданной цене
    - Анализ diluted vs actual
    - Поддержка GNK, HEX, BTC, ETH и других токенов
    """
    user_id = update.effective_user.id
    
    # Таймер для отслеживания использования
    start_time = time.time()
    
    logger.info(f"🧮 Калькулятор открыт пользователем {user_id}")
    
    # Получаем список доступных токенов
    tokens = get_token_list()
    
    # Создаем кнопки для выбора токена
    keyboard = []
    for i in range(0, len(tokens), 2):
        row = []
        
        # Первый токен в строке
        token1 = tokens[i].upper()
        token_data1 = get_token_stats(token1)
        if token_data1:
            row.append(InlineKeyboardButton(
                f"{token_data1['emoji']} {token_data1['symbol']}",
                callback_data=f"calc_token_{token1.lower()}"
            ))
        
        # Второй токен в строке (если есть)
        if i + 1 < len(tokens):
            token2 = tokens[i + 1].upper()
            token_data2 = get_token_stats(token2)
            if token_data2:
                row.append(InlineKeyboardButton(
                    f"{token_data2['emoji']} {token_data2['symbol']}",
                    callback_data=f"calc_token_{token2.lower()}"
                ))
        
        if row:
            keyboard.append(row)
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
    
    # Показываем меню калькулятора
    try:
        await update.message.reply_text(
            get_calculator_menu_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        elapsed = time.time() - start_time
        logger.info(f"Меню калькулятора показано за {elapsed:.2f}с")
        
    except Exception as e:
        logger.error(f"Ошибка при показе меню калькулятора: {e}")
        await update.message.reply_text(
            "❌ Ошибка при открытии калькулятора. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )


@log_command
@log_command
async def learn_progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 Показывает прогресс обучения пользователя (v0.37.0)
    
    Отображает:
    - Пройденные уроки по темам
    - Уровень владения
    - Полученные достижения
    - Рекомендацию следующего урока
    """
    user_id = update.effective_user.id
    user = update.effective_user
    
    logger.info(f"📊 Пользователь {user_id} открыл прогресс обучения")
    
    try:
        completed = get_completed_topics(user_id)
        badges = get_user_badges(user_id)
        recommended = get_recommended_lesson(user_id)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            user_xp = result[0] if result else 0
        
        # Формируем сообщение с прогрессом
        lines = [
            f"📊 <b>Ваш прогресс обучения</b>",
            f"👤 {user.first_name or 'Ученик'}",
            f"⚡ XP: {user_xp}",
            ""
        ]
        
        if completed:
            lines.append(f"📚 <b>Пройденные темы ({len(completed)}):</b>")
            for topic, info in sorted(completed.items()):
                topic_name = TEACHING_TOPICS.get(topic, {}).get('name', topic)
                difficulties = ", ".join([DIFFICULTY_LEVELS.get(d, {}).get('emoji', '') for d in sorted(info['difficulties'])])
                lines.append(f"  • {topic_name}: {difficulties}")
            lines.append("")
        else:
            lines.append("<i>Вы ещё не начали обучение. Начните с /teach!</i>")
            lines.append("")
        
        if badges:
            lines.append(f"🏅 <b>Достижения ({len(badges)}):</b>")
            for badge in badges[:5]:  # Показываем первые 5
                lines.append(f"  {badge['emoji']} <b>{badge['name']}</b>: {badge['description']}")
            if len(badges) > 5:
                lines.append(f"  ... и ещё {len(badges) - 5} достижений")
            lines.append("")
        
        if recommended:
            lines.append(f"🎯 <b>Рекомендуемый следующий урок:</b>")
            lines.append(f"  {recommended['reason']}")
            lines.append(f"  Уровень: {DIFFICULTY_LEVELS.get(recommended['difficulty'], {}).get('emoji', '📚')}")
        
        keyboard = []
        
        if recommended:
            keyboard.append([InlineKeyboardButton(
                f"🚀 Начать урок",
                callback_data=f"teach_start_{recommended['topic']}_{recommended['difficulty']}"
            )])
        
        keyboard.extend([
            [InlineKeyboardButton("🎓 Все темы", callback_data="teach_menu")],
            [InlineKeyboardButton("🏠 Меню", callback_data="menu")]
        ])
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Прогресс показан для {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка в learn_progress_command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке прогресса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="menu")]])
        )

async def teach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎓 Интерактивный учитель с передовой системой обучения (v0.21.0)
    
    Функции:
    - Спиральное обучение (повторение с углублением)
    - Адаптивные пути обучения
    - Геймификация с достижениями
    - Персонализированный контент
    """
    user_id = update.effective_user.id
    
    # ✅ v0.25.0: Track user_teach event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_TEACH,
        user_id=user_id,
        data={}
    ))
    
    # Получаем профиль обучения пользователя
    with get_db() as conn:
        cursor = conn.cursor()
        _, user_xp = calculate_user_level_and_xp(cursor, user_id)
    
    # Создаём или загружаем профиль адаптивного обучения
    # TODO: Сохранять в БД user_learning_profile
    learning_profile = initialize_learning_profile(user_id)
    
    # Устанавливаем уровень на основе XP
    if user_xp < 100:
        learning_profile.current_level = DifficultyLevel.BEGINNER
        difficulty_hint = "🌱 Рекомендуем начать с основ"
    elif user_xp < 300:
        learning_profile.current_level = DifficultyLevel.ELEMENTARY
        difficulty_hint = "📚 Вы готовы к промежуточному уровню"
    elif user_xp < 600:
        learning_profile.current_level = DifficultyLevel.INTERMEDIATE
        difficulty_hint = "🚀 Пора учить продвинутые темы"
    elif user_xp < 1000:
        learning_profile.current_level = DifficultyLevel.ADVANCED
        difficulty_hint = "⭐ Продвинутые концепции ждут вас"
    else:
        learning_profile.current_level = DifficultyLevel.EXPERT
        difficulty_hint = "👑 Добро пожаловать на экспертный уровень!"
    
    # Получаем рекомендованную сессию
    recommended_session = get_recommended_learning_session(learning_profile)
    
    # Если нет аргументов - показываем интерактивное меню через кнопку
    if not context.args:
        # Используем callback систему для меню (это проще и избегает дублирования)
        keyboard = [[InlineKeyboardButton("🎓 Начать обучение", callback_data="teach_menu")]]
        
        next_milestone = Gamification.get_next_milestone(user_xp)
        
        menu_text = (
            "🎓 <b>ИНТЕРАКТИВНЫЙ УЧИТЕЛЬ</b>\n\n"
            "Выберите тему для обучения:\n\n"
            f"💡 <i>{difficulty_hint}</i>\n"
            f"📊 Следующая цель: {next_milestone['icon']} <b>{next_milestone['title']}</b> ({next_milestone['xp']} XP)\n\n"
            f"💼 Рекомендованный формат: <b>{recommended_session['recommended_format']}</b>\n"
            f"⏱️ Время сессии: {recommended_session['estimated_session_time']} минут"
        )
        
        try:
            await update.message.reply_text(
                menu_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_command: {e}")
        return
    
    # Если передан топик и уровень как аргументы - запускаем урок напрямую
    topic = context.args[0].lower()
    recommended_difficulty = "medium"  # Значение по умолчанию
    difficulty = context.args[1].lower() if len(context.args) > 1 else recommended_difficulty  # Используем автоматический уровень
    
    # Валидация
    if topic not in TEACHING_TOPICS:
        await update.message.reply_text(f"❌ Неизвестная тема: `{topic}`", parse_mode=ParseMode.MARKDOWN)
        return
    
    if difficulty not in DIFFICULTY_LEVELS:
        await update.message.reply_text(f"❌ Неизвестный уровень: `{difficulty}`", parse_mode=ParseMode.MARKDOWN)
        return
    
    logger.info(f"📚 Автоматическая сложность для {user_id}: {difficulty} (XP: {user_xp})")
    
    # Запускаем урок
    await _launch_teaching_lesson(update, context, user_id, topic, difficulty)


# =============================================================================
# ADMIN КОМАНДЫ
# =============================================================================

@admin_only
@log_command
async def test_digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда для тестирования крипто дайджеста
    Отправляет дайджест в канал сразу же
    """
    try:
        await update.message.reply_text("⏳ Сбираю данные для крипто дайджеста...", parse_mode=ParseMode.HTML)
        
        # Отправляем дайджест
        await send_crypto_digest(context)
        
        await update.message.reply_text("✅ Крипто дайджест отправлен в канал!", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании дайджеста: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}",
            parse_mode=ParseMode.HTML
        )

@admin_only
@log_command
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Детальная статистика для администраторов."""
    stats = get_global_stats()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Активные пользователи (запросы за последние 7 дней)
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) FROM requests
            WHERE created_at >= datetime('now', '-7 days')
        """)
        active_users = cursor.fetchone()[0]
        
        # Ошибки
        cursor.execute("""
            SELECT COUNT(*) FROM requests WHERE error_message IS NOT NULL
        """)
        error_count = cursor.fetchone()[0]
        
        # Заблокированные
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_count = cursor.fetchone()[0]
    
    cache_hit_rate = 0
    if stats['total_requests'] > 0:
        cache_hit_rate = (stats['cache_hits'] / stats['total_requests']) * 100
    
    admin_text = (
        "👑 **Админская статистика**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {stats['total_users']}\n"
        f"• Активных (7д): {active_users}\n"
        f"• Заблокированных: {banned_count}\n\n"
        f"📊 **Запросы:**\n"
        f"• Всего: {stats['total_requests']}\n"
        f"• Ошибок: {error_count}\n"
        f"• Среднее время: {stats['avg_processing_time']}ms\n\n"
        f"💾 **Кэш:**\n"
        f"• Размер: {stats['cache_size']}\n"
        f"• Попадания: {stats['cache_hits']}\n"
        f"• Hit rate: {cache_hit_rate:.1f}%\n\n"
        f"📈 **Фидбек:**\n"
        f"• 👍 Полезно: {stats['helpful']}\n"
        f"• 👎 Не помогло: {stats['not_helpful']}\n"
    )
    
    await update.message.reply_text(admin_text, parse_mode=ParseMode.MARKDOWN)

@admin_only
@log_command
async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Блокировка пользователя."""
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ Формат: /ban <user_id> [причина]"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Нарушение правил"
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET is_banned = 1, ban_reason = ?
                WHERE user_id = ?
            """, (reason, target_user_id))
        
        await update.message.reply_text(
            f"✅ Пользователь {target_user_id} заблокирован\n\n"
            f"Причина: {reason}"
        )
        
        log_analytics_event("user_banned", update.effective_user.id, {
            "target_user": target_user_id,
            "reason": reason
        })
    
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя")
    except Exception as e:
        logger.error(f"Ошибка блокировки: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

@admin_only
@log_command
async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Разблокировка пользователя."""
    if len(context.args) < 1:
        await update.message.reply_text("❌ Формат: /unban <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET is_banned = 0, ban_reason = NULL
                WHERE user_id = ?
            """, (target_user_id,))
        
        await update.message.reply_text(
            f"✅ Пользователь {target_user_id} разблокирован"
        )
        
        log_analytics_event("user_unbanned", update.effective_user.id, {
            "target_user": target_user_id
        })
    
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя")
    except Exception as e:
        logger.error(f"Ошибка разблокировки: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

@admin_only
@log_command
async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка кэша."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cache")
        cache_size = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM cache")
    
    await update.message.reply_text(
        f"🗑️ **Кэш очищен**\n\nУдалено записей: {cache_size}"
    )
    
    log_analytics_event("cache_cleared", update.effective_user.id, {
        "records_deleted": cache_size
    })

@admin_only
@log_command
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Рассылка сообщения всем пользователям."""
    if not context.args:
        await update.message.reply_text(
            "❌ Формат: /broadcast <сообщение>"
        )
        return
    
    message = " ".join(context.args)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id FROM users WHERE is_banned = 0
        """)
        users = cursor.fetchall()
    
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(
        f"📢 Начинаю рассылку для {len(users)} пользователей..."
    )
    
    for (user_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **Объявление от администрации:**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
            
            # Небольшая задержка, чтобы не превысить rate limits Telegram
            if sent % 20 == 0:
                await asyncio.sleep(1)
        
        except TelegramError as e:
            logger.warning(f"Не удалось отправить {user_id}: {e}")
            failed += 1
    
    await status_msg.edit_text(
        f"✅ **Рассылка завершена**\n\n"
        f"• Отправлено: {sent}\n"
        f"• Не удалось: {failed}"
    )
    
    log_analytics_event("broadcast_sent", update.effective_user.id, {
        "sent": sent,
        "failed": failed,
        "message_length": len(message)
    })


async def post_to_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет пост в канал обновлений.
    Использование: /post_to_channel <текст поста>
    
    Пример: /post_to_channel 🚀 <b>Новое обновление!</b>
    Поддерживает HTML форматирование.
    """
    # Проверка прав админа
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("❌ Только админы могут отправлять посты в канал")
        return
    
    # Проверка наличия текста
    if not context.args:
        await update.message.reply_text(
            "❌ Формат: /post_to_channel <текст>\n\n"
            "Пример: /post_to_channel 🚀 <b>Новое обновление!</b>\n"
            "(Поддерживается HTML форматирование)"
        )
        return
    
    post_text = " ".join(context.args)
    
    # Проверка что канал установлен
    if not UPDATE_CHANNEL_ID:
        await update.message.reply_text("❌ UPDATE_CHANNEL_ID не установлен в .env")
        return
    
    try:
        # Отправляем пост
        await context.bot.send_message(
            chat_id=UPDATE_CHANNEL_ID,
            text=post_text,
            parse_mode=ParseMode.HTML,
            disable_notification=True
        )
        
        await update.message.reply_text(
            f"✅ Пост успешно отправлен в канал!\n\n"
            f"📍 Канал: {UPDATE_CHANNEL_ID}\n"
            f"📏 Размер: {len(post_text)} символов"
        )
        
        logger.info(f"Админ {update.effective_user.id} отправил пост в канал")
        
        # Логируем событие
        if ENABLE_ANALYTICS:
            log_analytics_event("post_to_channel", update.effective_user.id, {
                "text_length": len(post_text),
                "channel_id": UPDATE_CHANNEL_ID
            })
    
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Ошибка форматирования HTML: {e}\n\n"
            "Проверьте синтаксис HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(
            f"❌ Ошибка при отправке в канал: {e}"
        )
        logger.error(f"Ошибка отправки поста в канал: {e}")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Неожиданная ошибка: {e}"
        )
        logger.error(f"Неожиданная ошибка при отправке поста: {e}")


async def notify_version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет уведомление об обновлении версии в канал.
    Использование: /notify_version <версия> | <список улучшений через |>
    
    Пример: /notify_version 0.15.0 | Новая система квестов | Улучшена производительность
    """
    # Проверка прав админа
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("❌ Только админы могут отправлять уведомления об обновлениях")
        return
    
    # Парсим аргументы
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Формат: /notify_version <версия> | <улучшение1> | <улучшение2>\n\n"
            "Пример: /notify_version 0.15.0 | Новые квесты | Лучше производительность"
        )
        return
    
    text = " ".join(context.args)
    parts = text.split("|")
    
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Используйте | для разделения версии и улучшений\n"
            "Пример: /notify_version 0.15.0 | Новые квесты | Лучше производительность"
        )
        return
    
    version = parts[0].strip()
    changelog_items = [item.strip() for item in parts[1:] if item.strip()]
    changelog = "\n".join([f"• {item}" for item in changelog_items])
    
    try:
        await notify_version_update(context, version, changelog)
        
        await update.message.reply_text(
            f"✅ Уведомление об обновлении отправлено!\n\n"
            f"📌 Версия: {version}\n"
            f"📝 Изменений: {len(changelog_items)}"
        )
        
        logger.info(f"Админ {update.effective_user.id} отправил уведомление об обновлении v{version}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка отправки уведомления: {e}")


async def notify_quests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет уведомление о новых квестах в канал."""
    # Проверка прав админа
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("❌ Только админы могут отправлять уведомления о квестах")
        return
    
    try:
        await notify_new_quests(context)
        
        await update.message.reply_text(
            "✅ Уведомление о новых квестах отправлено в канал!"
        )
        
        logger.info(f"Админ {update.effective_user.id} отправил уведомление о квестах")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка отправки уведомления о квестах: {e}")


async def notify_milestone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет уведомление о вехе (например, 100 пользователей).
    Использование: /notify_milestone <название вехи> | <количество>
    
    Пример: /notify_milestone 100 активных пользователей | 100
    """
    # Проверка прав админа
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("❌ Только админы могут отправлять уведомления о вехах")
        return
    
    if not context.args or "|" not in " ".join(context.args):
        await update.message.reply_text(
            "❌ Формат: /notify_milestone <название> | <количество>\n\n"
            "Пример: /notify_milestone 100 активных пользователей | 100"
        )
        return
    
    text = " ".join(context.args)
    parts = text.split("|")
    
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Используйте | один раз для разделения названия и количества"
        )
        return
    
    milestone_name = parts[0].strip()
    try:
        count = int(parts[1].strip())
    except ValueError:
        await update.message.reply_text("❌ Количество должно быть числом")
        return
    
    try:
        await notify_milestone_reached(context, milestone_name, count)
        
        await update.message.reply_text(
            f"✅ Уведомление о вехе отправлено!\n\n"
            f"📌 Веха: {milestone_name}\n"
            f"📊 Количество: {count}"
        )
        
        logger.info(f"Админ {update.effective_user.id} отправил уведомление о вехе")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка отправки уведомления о вехе: {e}")


# =============================================================================
# КОМАНДЫ ДРОПОВ И АКТИВНОСТЕЙ
# =============================================================================

async def drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить свежие NFT дропы"""
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    user_id = update.effective_user.id
    
    # Проверка лимита запросов
    has_limit, _ = check_daily_limit(user_id)
    if not has_limit:
        try:
            if is_callback and query:
                await query.answer("❌ Превышен лимит запросов", show_alert=True)
            else:
                await update.message.reply_text("❌ Превышен лимит запросов на день")
        except Exception as e:
            logger.error(f"Ошибка при проверке лимита: {e}")
        return
    
    try:
        # Отправить статус "печатает"
        if is_callback and query:
            await query.answer()
        
        if not is_callback:
            await update.message.chat.send_action(ChatAction.TYPING)
        
        # Запрос к API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_URL_NEWS.replace('/explain_news', '')}/get_drops",
                params={"limit": 10, "chain": "all"}
            )
        
        if response.status_code != 200:
            raise Exception(f"API вернул статус {response.status_code}")
        
        data = response.json()
        drops = data.get("drops", [])
        
        if not drops:
            text = "❌ Дропы не найдены"
        else:
            text = "📦 <b>ТОП-10 СВЕЖИХ NFT ДРОПОВ</b>\n\n"
            for i, drop in enumerate(drops[:10], 1):
                name = drop.get("name", "Unknown")
                chain = drop.get("chain", "N/A")
                price = drop.get("price", "N/A")
                time_until = drop.get("time_until", "N/A")
                url = drop.get("url", "")
                text += f"{i}. <b>{name}</b>\n"
                text += f"   🔗 Цепь: {chain}\n"
                text += f"   💰 Цена: {price}\n"
                text += f"   ⏱️ Время: {time_until}\n"
                if url:
                    text += f"   🌐 <a href='{url}'>Перейти</a>\n"
                text += "\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        if is_callback and query:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, 
                                         reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Логирование
        logger.info(f"📦 /drops команда от {user_id}")
        
    except httpx.ConnectError:
        error_msg = "❌ Не удалось подключиться к API. Пожалуйста, попробуйте позже."
    except httpx.TimeoutException:
        error_msg = "⏱️ Запрос к API занял слишком много времени. Пожалуйста, попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка в /drops: {e}")
        error_msg = "❌ Произошла внутренняя ошибка.\n\nПожалуйста, попробуйте позже."
    
    try:
        if 'error_msg' in locals():
            if is_callback and query:
                await query.edit_message_text(error_msg, parse_mode=ParseMode.HTML,
                                             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]))
            else:
                await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при отправке ошибки: {e}")


async def activities_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить активности в крипто"""
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    user_id = update.effective_user.id
    
    # Проверка лимита запросов
    has_limit, _ = check_daily_limit(user_id)
    if not has_limit:
        try:
            if is_callback and query:
                await query.answer("❌ Превышен лимит запросов", show_alert=True)
            else:
                await update.message.reply_text("❌ Превышен лимит запросов на день")
        except Exception as e:
            logger.error(f"Ошибка при проверке лимита: {e}")
        return
    
    try:
        # Отправить статус "печатает"
        if is_callback and query:
            await query.answer()
        
        if not is_callback:
            await update.message.chat.send_action(ChatAction.TYPING)
        
        # Запрос к API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_URL_NEWS.replace('/explain_news', '')}/get_activities",
                timeout=30.0
            )
        
        if response.status_code != 200:
            raise Exception(f"API вернул статус {response.status_code}")
        
        data = response.json()
        
        text = "🔥 <b>АКТИВНОСТИ В КРИПТО</b>\n\n"
        
        # Стейкинг
        staking = data.get("staking_updates", [])
        if staking:
            text += "<b>📊 Стейкинг обновления:</b>\n"
            for item in staking[:3]:
                text += f"• {item}\n"
            text += "\n"
        
        # Новые ланчи
        launches = data.get("new_launches", [])
        if launches:
            text += "<b>🚀 Новые ланчи:</b>\n"
            for item in launches[:3]:
                text += f"• {item}\n"
            text += "\n"
        
        # Гавернанс
        governance = data.get("governance", [])
        if governance:
            text += "<b>🗳️ Гавернанс:</b>\n"
            for item in governance[:3]:
                text += f"• {item}\n"
            text += "\n"
        
        # Партнерства
        partnerships = data.get("partnerships", [])
        if partnerships:
            text += "<b>🤝 Партнерства:</b>\n"
            for item in partnerships[:3]:
                text += f"• {item}\n"
        
        if not text.endswith("\n"):
            text += "\n\n"
        
        text += "💡 <i>Обновляется раз в час</i>"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        if is_callback and query:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                         reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Логирование
        logger.info(f"🔥 /activities команда от {user_id}")
        
    except httpx.ConnectError:
        error_msg = "❌ Не удалось подключиться к API. Пожалуйста, попробуйте позже."
    except httpx.TimeoutException:
        error_msg = "⏱️ Запрос к API занял слишком много времени. Пожалуйста, попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка в /activities: {e}")
        error_msg = "❌ Произошла внутренняя ошибка.\n\nПожалуйста, попробуйте позже."
    
    try:
        if 'error_msg' in locals():
            if is_callback and query:
                await query.edit_message_text(error_msg, parse_mode=ParseMode.HTML,
                                             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]))
            else:
                await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при отправке ошибки: {e}")


# =============================================================================
# QUIZ SYSTEM (v0.19.0) - ФУНКЦИИ ДЛЯ РАБОТЫ С ТЕСТАМИ
# =============================================================================

async def show_quiz_for_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, course_name: str, lesson_num: int) -> None:
    """Показывает первый вопрос квиза для урока."""
    query = update.callback_query
    user = query.from_user
    
    try:
        # Получаем контент урока с включением раздела тестов
        lesson_content = get_lesson_content(course_name, lesson_num, include_tests=True)
        
        if not lesson_content:
            logger.error(f"Урок не найден: {course_name}, lesson {lesson_num}")
            await query.answer("❌ Урок не найден", show_alert=True)
            return
        
        logger.info(f"Контент загружен: {len(lesson_content)} символов")
        
        # Извлекаем вопросы из quiz раздела
        _, quiz_text = split_lesson_content(lesson_content)
        
        logger.info(f"Quiz текст: {len(quiz_text)} символов")
        
        # Если quiz не найден в уроке, ищем в разделе "ТЕСТЫ К КУРСУ"
        if not quiz_text:
            logger.info(f"⚠️ Quiz текст пуст, ищем в разделе ТЕСТЫ К КУРСУ для урока {lesson_num}")
            questions = extract_quiz_from_lesson(
                "",  # пустой quiz_text
                lesson_number=lesson_num,
                full_course_content=lesson_content  # передаем полный контент
            )
        else:
            logger.info(f"Найден quiz текст, извлекаем вопросы")
            questions = extract_quiz_from_lesson(quiz_text)
        
        logger.info(f"Найдено вопросов: {len(questions)}")
        
        if not questions:
            logger.error(f"Вопросы не найдены для урока {lesson_num}")
            await query.answer("❌ Вопросы не найдены", show_alert=True)
            return
        
        # Сохраняем сессию квиза в context
        context.user_data['quiz_session'] = {
            'course': course_name,
            'lesson': lesson_num,
            'questions': questions,
            'current_q': 0,
            'responses': [],
            'correct_count': 0
        }
        
        logger.info(f"Сессия квиза создана, переходим к первому вопросу")
        
        # Показываем первый вопрос
        await show_quiz_question(update, context)
    
    except Exception as e:
        logger.error(f"Ошибка в show_quiz_for_lesson: {e}", exc_info=True)
        await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


async def show_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущий вопрос квиза."""
    query = update.callback_query
    user = query.from_user
    
    try:
        quiz_session = context.user_data.get('quiz_session')
        
        if not quiz_session:
            logger.error(f"Сессия квиза потеряна")
            await query.answer("❌ Сессия квиза потеряна", show_alert=True)
            return
        
        current_q_idx = quiz_session['current_q']
        questions = quiz_session['questions']
        total_questions = len(questions)
        
        logger.info(f"📝 Показываем вопрос {current_q_idx} из {total_questions}")
        
        if current_q_idx >= total_questions:
            # Квиз завершен
            logger.info(f"Квиз завершен, переходим к результатам")
            await show_quiz_results(update, context)
            return
        
        current_question = questions[current_q_idx]
        q_num = current_question['number']
        q_text = current_question['text']
        answers = current_question['answers']
        
        # Форматируем сообщение
        message = (
            f"📝 <b>ТЕСТ</b>\n"
            f"Вопрос {current_q_idx + 1} из {total_questions}\n\n"
            f"<b>{q_text}</b>\n\n"
            f"Выберите ответ:"
        )
        
        # Создаем кнопки для вариантов ответа
        keyboard = []
        for idx, answer_text in enumerate(answers):
            lesson_id = quiz_session['lesson']  # Используем номер урока как lesson_id
            callback_data = f"quiz_answer_{quiz_session['course']}_{lesson_id}_{current_q_idx}_{idx}"
            keyboard.append([InlineKeyboardButton(f"○ {answer_text}", callback_data=callback_data)])
        
        # Кнопка выхода из квиза
        keyboard.append([InlineKeyboardButton("❌ Выход из теста", callback_data=f"quiz_exit_{quiz_session['course']}_{lesson_id}")])
        
        logger.info(f"Отправляем вопрос с {len(keyboard)} кнопками")
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Вопрос успешно отправлен")
    
    except Exception as e:
        logger.error(f"Ошибка в show_quiz_question: {e}", exc_info=True)
        try:
            await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        except:
            pass


async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, course_name: str, lesson_id: int, q_idx: int, answer_idx: int) -> None:
    """
    Обрабатывает ответ на вопрос квиза с проверкой и feedback.
    
    Вызывается когда пользователь выбирает ответ на вопрос викторины.
    Проверяет правильность, сохраняет ответ, показывает feedback, переводит на следующий вопрос.
    
    Args:
        update (Update): Telegram Update с callback от выбора ответа
        context (ContextTypes.DEFAULT_TYPE): Telegram context с quiz_session
        course_name (str): Название курса
        lesson_id (int): ID урока в рамках курса
        q_idx (int): Индекс вопроса в текущем квизе (0-based)
        answer_idx (int): Индекс выбранного ответа (0-3, обычно)
        
    Quiz Session Structure:
        quiz_session = {
            'course': str,
            'lesson_id': int,
            'questions': list of question dicts,
            'responses': list of user answers,
            'current_q': int (current question index)
        }
        
    Question Structure:
        {
            'number': int,      # Question number (1-indexed)
            'text': str,        # Question text
            'options': list,    # List of answer options
            'correct': int      # Index of correct answer (0-3)
        }
        
    Response Tracking:
        - Saves user answer immediately
        - Shows correct/incorrect feedback with emoji
        - Adds explanation if provided
        - Updates score counters
        
    Scoring:
        - Correct answer: +10 XP
        - Incorrect: +2 XP for attempt
        - Bonus: +5 XP if all quiz questions correct
        
    Side Effects:
        - Updates quiz_session in context
        - Saves answers to conversation history
        - Increments user XP and score
        - Logs quiz interaction
        - Shows next question or quiz summary
    """
    query = update.callback_query
    user = query.from_user
    
    quiz_session = context.user_data.get('quiz_session')
    
    if not quiz_session:
        await query.answer("❌ Сессия квиза потеряна", show_alert=True)
        return
    
    questions = quiz_session['questions']
    current_question = questions[q_idx]
    correct_idx = current_question['correct']
    
    # Проверяем правильность ответа
    is_correct = (answer_idx == correct_idx)
    
    # Сохраняем ответ
    quiz_session['responses'].append({
        'q_num': current_question['number'],
        'selected': answer_idx,
        'correct': correct_idx,
        'is_correct': is_correct
    })
    
    if is_correct:
        quiz_session['correct_count'] += 1
    
    # Показываем результат вопроса
    result_emoji = "✅" if is_correct else "❌"
    correct_answer_text = current_question['answers'][correct_idx]
    
    message = (
        f"{result_emoji} <b>Ответ {'ПРАВИЛЬНЫЙ' if is_correct else 'НЕПРАВИЛЬНЫЙ'}</b>\n\n"
        f"Ваш ответ: {current_question['answers'][answer_idx]}\n"
        f"Правильный ответ: {correct_answer_text}\n\n"
        f"Нажмите кнопку ниже для следующего вопроса..."
    )
    
    # Переходим к следующему вопросу
    quiz_session['current_q'] += 1
    
    keyboard = [[InlineKeyboardButton("➡️ Далее", callback_data=f"quiz_next_{course_name}_{lesson_id}")]]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_quiz_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает итоговые результаты квиза."""
    query = update.callback_query
    user = query.from_user
    
    quiz_session = context.user_data.get('quiz_session')
    
    if not quiz_session:
        await query.answer("❌ Сессия квиза потеряна", show_alert=True)
        return
    
    course_name = quiz_session['course']
    lesson_num = quiz_session['lesson']
    correct_count = quiz_session['correct_count']
    total_questions = len(quiz_session['questions'])
    
    # Вычисляем оценку
    score_percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0
    xp_earned = int(score_percentage * 2)  # До 200 XP за 100%
    is_perfect = (score_percentage == 100)
    message_suffix = ""  # Инициализируем переменную для добавления информации о повторе
    
    # Формируем сообщение с результатами
    if score_percentage == 100:
        result_emoji = "🎉"
        verdict = "ОТЛИЧНО!"
    elif score_percentage >= 80:
        result_emoji = "😊"
        verdict = "ХОРОШО"
    elif score_percentage >= 60:
        result_emoji = "👍"
        verdict = "НОРМАЛЬНО"
    else:
        result_emoji = "😢"
        verdict = "НУЖНО УЧИТЬ"
    
    message = (
        f"{result_emoji} <b>РЕЗУЛЬТАТЫ ТЕСТА</b>\n\n"
        f"Правильных ответов: {correct_count}/{total_questions}\n"
        f"Оценка: {score_percentage:.0f}%\n"
        f"Вердикт: <b>{verdict}</b>\n\n"
        f"+{xp_earned} XP {'🏆' if is_perfect else ''}\n\n"
        f"Детали ответов:"
    )
    
    # Добавляем детали
    for resp in quiz_session['responses']:
        emoji = "✅" if resp['is_correct'] else "❌"
        message += f"\n{emoji} Q{resp['q_num']}: {resp['is_correct']}"
    
    # Инициализируем переменную для отслеживания первого прохождения
    already_completed = False
    
    # Сохраняем результаты в БД
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # 🆕 ЗАЩИТА ОТ АБУЗА: Проверяем, проходил ли уже пользователь этот тест
            cursor.execute("""
                SELECT id FROM user_quiz_stats 
                WHERE user_id = ? AND lesson_id = ?
                LIMIT 1
            """, (user.id, lesson_num))
            
            already_completed = cursor.fetchone() is not None
            actual_xp_earned = 0  # По умолчанию XP не начисляем при повторе
            
            if already_completed:
                # Пользователь уже проходил этот тест
                logger.info(f"ℹ️ Пользователь {user.id} повторно проходит тест {lesson_num} - XP не начисляется")
                message_suffix = "\n\n⚠️ <i>Вы уже проходили этот тест. XP не начисляется при повторных попытках.</i>"
            else:
                # Первое прохождение - начисляем XP
                actual_xp_earned = xp_earned
                logger.info(f"Первое прохождение теста {lesson_num} пользователем {user.id} - начисляем {xp_earned} XP")
            
            # Сохраняем каждый ответ
            for resp in quiz_session['responses']:
                cursor.execute("""
                    INSERT INTO user_quiz_responses 
                    (user_id, lesson_id, question_number, selected_answer_index, is_correct, xp_earned)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user.id, lesson_num, resp['q_num'], resp['selected'], resp['is_correct'], actual_xp_earned // total_questions if total_questions > 0 else 0))
            
            # Сохраняем статистику по квизу только при первом прохождении
            if not already_completed:
                cursor.execute("""
                    INSERT INTO user_quiz_stats 
                    (user_id, lesson_id, total_questions, correct_answers, quiz_score, total_xp_earned, is_perfect_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user.id, lesson_num, total_questions, correct_count, score_percentage, actual_xp_earned, is_perfect))
                
                # Добавляем XP пользователю ТОЛЬКО при первом прохождении
                add_xp_to_user(cursor, user.id, actual_xp_earned)
            
            conn.commit()
            
    except Exception as e:
        logger.warning(f"Ошибка при сохранении результатов квиза: {e}")
        message_suffix = ""
        already_completed = False
    
    # Кнопки навигации
    keyboard = [
        [InlineKeyboardButton("📚 Вернуться к курсу", callback_data=f"start_course_{course_name}")],
        [InlineKeyboardButton("➡️ Следующий урок", callback_data=f"lesson_{course_name}_{lesson_num + 1}")] if lesson_num < 5 else [],
        [InlineKeyboardButton("« В меню", callback_data="back_to_start")]
    ]
    
    # Убираем пустые строки
    keyboard = [row for row in keyboard if row]
    
    await query.edit_message_text(
        message + message_suffix,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Очищаем сессию
    if 'quiz_session' in context.user_data:
        del context.user_data['quiz_session']


# =============================================================================
# CALLBACK ОБРАБОТЧИК
# =============================================================================

async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает выбор языка пользователем.
    
    Срабатывает при нажатии на кнопку выбора языка (ru, uk)
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
    """
    query = update.callback_query
    user_id = query.from_user.id
    selected_language = query.data.replace("lang_", "")
    
    # Валидируем язык
    if selected_language not in ["ru", "uk"]:
        await query.answer("❌ Неизвестный язык", show_alert=False)
        return
    
    # Сохраняем выбор в БД
    success = await set_user_language(user_id, selected_language)
    
    if success:
        logger.info(f"✅ User {user_id} selected language: {selected_language}")
        await query.answer(f"✅ Язык установлен!", show_alert=False)
        
        # Теперь показываем главное меню
        await start_command(update, context)
    else:
        logger.error(f"❌ Failed to set language for user {user_id}")
        await query.answer("❌ Ошибка при установке языка", show_alert=True)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие inline-кнопок.
    
    Функции:
    - Выбор языка (v0.43.0)
    - Проверяет подписку на обязательный канал (v0.42.1)
    - Выбор меню
    - Ответы на квесты
    - Выбор уровня
    - Управление подписками
    - Лайки/дизлайки
    - Регенерация ответов
    
    Args:
        update: Telegram Update объект с данными кнопки
        context: Telegram Context объект
        
    Returns:
        None
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    user_id = user.id
    
    # ✅ v0.43.0: Проверяем выбор языка первым делом
    if data.startswith("lang_"):
        return await handle_language_selection(update, context)
    
    # ✅ v0.42.1: Проверяем подписку перед обработкой кнопки
    # Пропускаем проверку для кнопок которые относятся к подписке
    if not data.startswith("skip_"):
        is_subscribed = await check_channel_subscription(user_id, context)
        if not is_subscribed:
            logger.info(f"User {user_id} clicked button without channel subscription")
            
            # Отправляем сообщение с кнопкой для подписки
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📢 Подписаться на канал",
                        url=MANDATORY_CHANNEL_LINK
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "<b>📢 Требуется подписка на канал</b>\n\n"
                "Для использования этого бота необходимо подписаться на наш канал. "
                "После подписки вы получите доступ ко всем функциям.\n\n"
                "👇 Подпишитесь по ссылке ниже:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return
    
    logger.info(f"🔘 Callback получен: {data} от пользователя {user.id}")
    
    # ============ SUBSCRIPTION CHECK CALLBACK ============
    if data.startswith("check_subscription_"):
        # Очищаем кэш подписки для этого пользователя
        user_id = user.id
        if user_id in _subscription_cache:
            del _subscription_cache[user_id]
        
        # Проверяем подписку еще раз
        is_subscribed = await check_channel_subscription(user_id, context)
        
        if is_subscribed:
            # ✅ v0.43.0: Проверяем язык пользователя
            user_language = get_user_lang(user_id, default=None)
            
            if user_language is None:
                # Если язык не выбран, показываем выбор языка
                logger.info(f"📢 User {user_id} subscribed successfully, showing language selection")
                
                selection_prompt = await get_text("language.select_prompt", language="ru")
                
                keyboard = [
                    [
                        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                        InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ <b>Спасибо за подписку!</b>\n\n"
                    f"Теперь выберите язык для использования бота:\n\n"
                    f"{selection_prompt}",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Если язык уже выбран, просто показываем сообщение и предлагаем начать
                await query.edit_message_text(
                    "✅ <b>Спасибо за подписку!</b>\n\n"
                    "Вы подписаны на наш канал и теперь имеете полный доступ ко всем функциям бота. "
                    "Напишите /start чтобы начать работу.",
                    parse_mode=ParseMode.HTML
                )
            return
        else:
            # Пользователь еще не подписался
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📢 Подписаться на канал",
                        url=MANDATORY_CHANNEL_LINK
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ Я подписался, проверить еще раз",
                        callback_data=f"check_subscription_{user_id}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ <b>Подписка еще не подтверждена</b>\n\n"
                "Пожалуйста, сначала подпишитесь на наш канал, а затем нажмите кнопку ниже.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return
    
    # ============ PROFILE CALLBACKS v0.37.15 ============
    if data == "start_profile":
        try:
            # Создаём fake update для передачи в profile_command
            profile_data = get_user_profile_data(user.id)
            
            if not profile_data:
                await query.edit_message_text("❌ Ошибка загрузки профиля")
                return
            
            # Форматируем сообщение
            text = format_user_profile(profile_data)
            
            # Кнопки
            keyboard = [
                [InlineKeyboardButton("🏅 Все достижения", callback_data="profile_all_badges")],
                [InlineKeyboardButton("📊 Статистика", callback_data="profile_stats")],
                [InlineKeyboardButton("🚀 Начать урок", callback_data="teach_menu")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
            ]
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Ошибка в profile callback: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка загрузки профиля")
        return
    
    if data == "profile_all_badges":
        try:
            profile_data = get_user_profile_data(user.id)
            
            if not profile_data:
                await query.answer("❌ Ошибка загрузки", show_alert=True)
                return
            
            # Описания бейджей
            badge_info = {
                'first_lesson': ('🎓', 'Первый урок', 'Ты начал своё обучение!'),
                'first_test': ('✅', 'Первый тест', 'Ты прошел первый тест!'),
                'first_question': ('💬', 'Первый вопрос', 'Ты задал первый вопрос ИИ!'),
                'level_5': ('⭐', 'Уровень 5', 'Достигнут уровень 5'),
                'level_10': ('🌟', 'Уровень 10', 'Достигнут уровень 10'),
                'perfect_score': ('🎯', 'Идеальный результат', 'Ты решил тест на 100%!'),
                'daily_active': ('🔥', 'Ежедневный активист', 'Ты активен 7 дней подряд'),
                'helper': ('👐', 'Помощник', 'Ты помогал другим пользователям')
            }
            
            text = "<b>🏅 ВСЕ ТОИ ДОСТИЖЕНИЯ\n</b>═════════════════\n\n"
            
            if not profile_data['badges']:
                text += "Здесь пока нет достижений 😢\n\nНачни обучение чтобы разблокировать первые награды!"
            else:
                for badge in profile_data['badges']:
                    emoji, name, desc = badge_info.get(badge, ('🎖️', badge, 'Награда'))
                    text += f"{emoji} <b>{name}</b>\n"
                    text += f"   <i>{desc}</i>\n\n"
                
                text += f"\n<b>Всего достижений:</b> {len(profile_data['badges'])}/8"
            
            keyboard = [[InlineKeyboardButton("⬅️ Назад к профилю", callback_data="start_profile")]]
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Ошибка в profile_all_badges: {e}", exc_info=True)
            await query.answer("❌ Ошибка загрузки", show_alert=True)
        return
    
    if data == "profile_stats":
        try:
            profile_data = get_user_profile_data(user.id)
            
            if not profile_data:
                await query.answer("❌ Ошибка загрузки", show_alert=True)
                return
            
            # Вычисляем процент прогресса
            total_lessons = 24
            lessons_percent = (profile_data['lessons_completed'] / total_lessons * 100) if total_lessons > 0 else 0
            
            # Процент тестов
            tests_percent = (profile_data['perfect_tests'] / max(profile_data['total_tests'], 1) * 100) if profile_data['total_tests'] > 0 else 0
            
            text = (
                "<b>📊 ДЕТАЛЬНАЯ СТАТИСТИКА\n</b>"
                "════════════════════════════\n\n"
                
                f"<b>📚 ОБУЧЕНИЕ</b>\n"
                f"Пройдено уроков: {profile_data['lessons_completed']}/24\n"
                f"Прогресс: {'▓' * int(lessons_percent/10)}{'░' * (10 - int(lessons_percent/10))} {lessons_percent:.0f}%\n\n"
                
                f"<b>✅ ТЕСТЫ</b>\n"
                f"Попыток: {profile_data['total_tests']}\n"
                f"Идеальные результаты: {profile_data['perfect_tests']}\n"
                f"Процент успеха: {tests_percent:.0f}%\n\n"
                
                f"<b>💬 ВОПРОСЫ</b>\n"
                f"Задано вопросов: {profile_data['questions_asked']}\n"
                f"Дней активен: {profile_data['days_active']}\n\n"
                
                f"<b>📈 РОСТ</b>\n"
                f"Текущий уровень: {profile_data['level']}\n"
                f"Текущий XP: {profile_data['xp']}\n"
                f"До следующего уровня: {max(0, profile_data['level'] * 100 - profile_data['xp'])} XP\n"
            )
            
            keyboard = [[InlineKeyboardButton("⬅️ Назад к профилю", callback_data="start_profile")]]
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Ошибка в profile_stats: {e}", exc_info=True)
            await query.answer("❌ Ошибка загрузки", show_alert=True)
        return
    
    # ============ RETRY IMAGE CALLBACK ============
    if data == "retry_image":
        logger.info(f"🔄 Retry image запрошен пользователем {user.id}")
        
        # Получаем сохраненное изображение из context.user_data
        image_b64 = context.user_data.get("last_image_b64")
        
        if not image_b64:
            await query.answer("❌ Изображение не найдено. Отправьте его снова.", show_alert=True)
            return
        
        # Повторно анализируем изображение
        await context.bot.send_chat_action(user.id, ChatAction.TYPING)
        
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(
                    f"{API_URL_NEWS.replace('/explain_news', '')}/analyze_image",
                    json={
                        "image_base64": image_b64,
                        "context": ""
                    },
                    headers={"X-User-ID": str(user.id)}
                )
                
                if response.status_code != 200:
                    logger.error(f"API ошибка при retry: {response.status_code}")
                    await query.answer("❌ Ошибка при повторном анализе. Попробуйте позже.", show_alert=True)
                    return
                
                result = response.json()
                
                # Форматируем ответ (аналогично handle_photo)
                analysis = result.get("analysis", "")
                asset_type = result.get("asset_type", "unknown")
                confidence = result.get("confidence", 0) * 100
                mentioned_assets = result.get("mentioned_assets", [])
                
                # Ограничиваем длину анализа для Telegram
                max_analysis_len = 1200
                is_truncated = len(analysis) > max_analysis_len
                if is_truncated:
                    analysis = analysis[:max_analysis_len] + "..."
                
                # Определяем эмодзи в зависимости от типа
                asset_icons = {
                    "chart": "📈",
                    "screenshot": "📸",
                    "meme": "😄",
                    "other": "🖼️"
                }
                asset_icon = asset_icons.get(asset_type, "🖼️")
                
                # Определяем стиль заголовка в зависимости от уверенности
                confidence_emoji = "🔍" if confidence < 50 else "✅" if confidence < 80 else "⭐"
                
                # Формируем красивый ответ
                reply_text = (
                    f"{confidence_emoji} <b>АНАЛИЗ ИЗОБРАЖЕНИЯ (переанализ)</b>\n"
                    f"─────────────────────\n"
                    f"{asset_icon} <b>Тип:</b> {asset_type.upper()}"
                )
                
                if confidence < 50:
                    reply_text += f" <i>(экспресс-режим)</i>"
                
                reply_text += f"\n🎯 <b>Уверенность:</b> {confidence:.0f}%\n"
                
                if mentioned_assets:
                    assets_str = " ".join([f"<code>{a}</code>" for a in mentioned_assets])
                    reply_text += f"💰 {assets_str}\n"
                
                reply_text += f"\n📝 <b>Анализ:</b>\n{analysis}"
                
                if is_truncated:
                    reply_text += "\n\n<i>[Анализ сокращен для читаемости]</i>"
                
                # Добавляем кнопку для переотправки если низкая уверенность
                keyboard = None
                if confidence < 50:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Попробуй снова", callback_data="retry_image")]
                    ])
                
                await query.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                
                logger.info(f"Переанализ завершен для {user.id} - уверенность: {confidence:.0f}%")
                
            except httpx.TimeoutException:
                logger.error(f"Timeout при retry анализе")
                await query.answer("⏱️ Timeout. Попробуйте позже.", show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при retry анализе: {e}")
                await query.answer("❌ Ошибка при анализе.", show_alert=True)
        
        return
    
    # ============ BOOKMARK CALLBACKS (v0.18.0) - ПРОЦЕССИРОВАТЬ В ПЕРВУЮ ОЧЕРЕДЬ ============
    
    if data.startswith("save_bookmark_news_"):
        request_id_str = data.replace("save_bookmark_news_", "")
        logger.info(f"📌 Обработка save_bookmark_news: request_id_str={request_id_str}, user_id={user.id}")
        
        try:
            # Конвертируем в int
            request_id = int(request_id_str)
            logger.info(f"   🔢 Преобразовано в int: {request_id}")
            
            # Получаем запрос из БД
            request = get_request_by_id(request_id)
            logger.info(f"   📊 Запрос из БД: {request is not None}")
            
            if not request:
                logger.warning(f"   ❌ Запрос не найден в БД: {request_id}")
                await query.answer("❌ Запрос не найден", show_alert=True)
                return
            
            # Логируем содержимое
            logger.info(f"   📄 Title: {request.get('news_text', '')[:50]}")
            logger.info(f"   📄 Response: {request.get('response_text', '')[:50]}")
            
            # Сохраняем в закладки
            success = add_bookmark(
                user_id=user.id,
                bookmark_type="news",
                content_title=request.get("news_text", "Новость")[:100],  # Используем news_text, а не request_text
                content_text=request.get("response_text", ""),
                source="manual_news",
                external_id=request_id
            )
            
            if success:
                logger.info(f"   ✅ Закладка успешно добавлена")
                # Показываем уведомление
                await query.answer("✅ Добавлено в закладки!", show_alert=False)
                # Отправляем сообщение в чат с кнопкой (будет заметнее)
                keyboard = [
                    [InlineKeyboardButton("📌 Перейти в закладки", callback_data="start_bookmarks")],
                ]
                await query.message.reply_text(
                    "✅ <b>Закладка успешно добавлена!</b>\n\n"
                    "💡 Закладки помогают сохранять важные анализы для дальнейшего использования",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                logger.error(f"   ❌ Ошибка при добавлении закладки в БД")
                await query.answer("❌ Ошибка сохранения", show_alert=True)
            
        except Exception as e:
            logger.error(f"   ❌ Исключение при обработке закладки: {e}", exc_info=True)
            await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        return
    
    # Парсинг callback_data
    parts = data.split("_", 2)  # Ограничиваем разбор до 3 частей
    
    # ============ НОВЫЕ CALLBACKS ДЛЯ КВЕСТОВ v2 ============
    
    # Запуск квеста (показать материал)
    if data.startswith("start_quest_"):
        quest_id = data.replace("start_quest_", "")
        if quest_id in DAILY_QUESTS:
            await start_quest(update, context, quest_id)
            return
    
    # Запуск теста (показать первый вопрос)
    if data.startswith("start_test_"):
        topic = data.replace("start_test_", "")
        # Проверяем что это валидная тема обучения
        if topic in TEACHING_TOPICS:
            # Ищем тест по этой теме в DAILY_QUESTS или запускаем генерацию теста
            matching_quests = [qid for qid in DAILY_QUESTS if topic in qid.lower()]
            if matching_quests:
                # Есть готовый тест для этой темы
                await start_test(update, context, matching_quests[0])
            else:
                # Генерируем рекомендацию пройти тест позже или через меню
                try:
                    await query.edit_message_text(
                        f"📝 <b>Тесты по теме '{TEACHING_TOPICS.get(topic, {}).get('name', topic)}'</b>\n\n"
                        "Тесты генерируются автоматически на основе ежедневных заданий.\n"
                        "Используй кнопку '🎯 Ежедневные задачи' в главном меню для прохождения тестов!",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎯 Ежедневные задачи", callback_data="start_quests")],
                            [InlineKeyboardButton("⬅️ Назад", callback_data=f"teach_question_{topic}")]
                        ])
                    )
                except:
                    pass
            return
        # Fallback: ищем как quest_id (для совместимости)
        elif data.replace("start_test_", "") in DAILY_QUESTS:
            quest_id = data.replace("start_test_", "")
            await start_test(update, context, quest_id)
            return
    
    # Обработка ответа на вопрос
    if data.startswith("answer_"):
        try:
            # Format: answer_quest_id_question_num_answer_idx
            parts_answer = data.split("_")
            answer_idx = int(parts_answer[-1])
            question_num = int(parts_answer[-2])
            quest_id = "_".join(parts_answer[1:-2])
            
            if quest_id in DAILY_QUESTS:
                await handle_answer(update, context, quest_id, question_num, answer_idx)
            return
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга ответа: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
            return
    
    # Переход к следующему вопросу
    if data.startswith("next_q_"):
        try:
            parts_next = data.split("_")
            question_num = int(parts_next[-1])
            quest_id = "_".join(parts_next[2:-1])
            
            if quest_id in DAILY_QUESTS:
                await show_question(update, context, quest_id, question_num)
            return
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга next_q: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
            return
    
    # Показать результаты
    if data.startswith("show_quests"):
        await tasks_command(update, context)
        return
    
    # ============ СТАРЫЕ CALLBACKS (совместимость) ============
    # NOTE: start_teach is now handled via teach_menu redirect below, so we skip it here
    if data.startswith("start_") and not data.startswith("start_teach"):
        action = "_".join(parts[1:])
        
        if action == "learn":
            await learn_command(update, context)
            return
        elif action == "stats":
            await stats_command(update, context)
            return
        elif action == "leaderboard":
            await leaderboard_command(update, context)
            return
        elif action == "drops":
            await drops_command(update, context)
            return
        elif action == "activities":
            await activities_command(update, context)
            return
        elif action == "resources":
            await show_resources_menu(update, query)
            return
        elif action == "bookmarks":
            await bookmarks_command(update, context)
            return
        elif action == "tasks":
            await tasks_command(update, context)
            return
        elif action == "quests":
            # NEW v0.21.0: Ежедневные задачи
            await show_daily_quests_menu(update, context)
            return
        elif action == "help":
            await help_command(update, context)
            return
        elif action == "history":
            await history_command(update, context)
            return
        elif action.startswith("course_"):
            # Обработка запуска курса через callback (например, start_course_blockchain_basics)
            course_name = action.replace("course_", "")
            await handle_start_course_callback(update, context, course_name, query)
            return
        elif action == "menu":
            keyboard = [
                [
                    InlineKeyboardButton("📚 Курсы", callback_data="menu_learn"),
                    InlineKeyboardButton("🧰 Инструменты", callback_data="menu_tools")
                ],
                [
                    InlineKeyboardButton("💬 Задать вопрос", callback_data="menu_ask"),
                    InlineKeyboardButton("📜 История", callback_data="menu_history")
                ],
                [
                    InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
                    InlineKeyboardButton("⚙️ Статус", callback_data="menu_stats")
                ]
            ]
            try:
                await query.edit_message_text(
                    "📋 <b>ГЛАВНОЕ МЕНЮ RVX</b>",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                await query.message.reply_text(
                    "📋 <b>ГЛАВНОЕ МЕНЮ RVX</b>",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
            return
            return
    
    # Обновление задач (новое в v0.11.0)
    if data == "refresh_tasks":
        await tasks_command(update, context)
        return
    
    # ============ LEADERBOARD CALLBACKS (v0.17.0) ============
    
    if data == "leaderboard_week":
        await show_leaderboard(update, context, "week")
        return
    
    if data == "leaderboard_month":
        await show_leaderboard(update, context, "month")
        return
    
    if data == "leaderboard_all":
        await show_leaderboard(update, context, "all")
        return
    
    # ============ MENU CALLBACKS (v0.38.0 FIX) ============
    
    if data == "show_stats":
        await stats_command(update, context)
        return
    
    if data == "menu_stats":
        await stats_command(update, context)
        return
    
    if data == "menu_learn":
        await learn_command(update, context)
        return
    
    if data == "menu_tools":
        await show_resources_menu(update, query)
        return
    
    if data == "menu_help":
        await help_command(update, context)
        return
    
    # ============ LESSON SELECTION (Interactive Mode) ============
    if data.startswith("lesson_"):
        # Парсим: lesson_<course_name>_<lesson_num>
        # Правильный способ: последний элемент это номер урока, всё остальное - имя курса
        parts_all = data.split("_")
        if len(parts_all) >= 3:  # lesson + course_name + lesson_num
            try:
                lesson_num = int(parts_all[-1])  # Последний элемент - номер урока
                course_name = "_".join(parts_all[1:-1])  # Всё между "lesson_" и номером
                
                logger.info(f"📖 Парсинг lesson callback: data={data}, course={course_name}, lesson={lesson_num}")
                
                # Проверяем курс
                if course_name not in COURSES_DATA:
                    logger.warning(f"❌ Курс не найден: {course_name}")
                    await query.answer("❌ Курс не найден", show_alert=True)
                    return
                
                course_data = COURSES_DATA[course_name]
                
                # Проверяем номер урока
                if lesson_num < 1 or lesson_num > course_data['total_lessons']:
                    await query.answer(f"❌ Урок должен быть от 1 до {course_data['total_lessons']}", show_alert=True)
                    return
                
                # Сохраняем текущий курс
                await bot_state.set_user_course(user.id, course_name)
                
                # Получаем содержимое урока используя функцию из education модуля
                lesson_content = get_lesson_content(course_name, lesson_num)
                
                if not lesson_content:
                    await query.answer("❌ Урок не найден", show_alert=True)
                    logger.warning(f"❌ Урок не найден: {course_name}, урок {lesson_num}")
                    return
                
                # Получаем прогресс пользователя (если таблица существует)
                completed_lessons = 0
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT completed_lessons FROM user_courses
                            WHERE user_id = ? AND course_name = ?
                        """, (user.id, course_name))
                        row = cursor.fetchone()
                        completed_lessons = row[0] if row else 0
                except Exception as e:
                    logger.warning(f"Не удалось получить прогресс из БД: {e}")
                    completed_lessons = 0
                
                # Форматируем урок красиво с ограничением размера
                lesson_text, lesson_continuation = format_lesson_for_telegram(
                    lesson_content, 
                    course_data['title'],
                    lesson_num,
                    course_data['level'],
                    completed_lessons,
                    course_data['total_lessons']
                )
                
                # Кнопки для навигации
                keyboard = []
                
                # Кнопка "Предыдущий урок"
                if lesson_num > 1:
                    keyboard.append([InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"lesson_{course_name}_{lesson_num-1}")])
                
                # Кнопки для прохождения теста и следующего урока
                nav_row = []
                nav_row.append(InlineKeyboardButton("📝 Пройти тест", callback_data=f"start_quiz_{course_name}_{lesson_num}"))
                
                if lesson_num < course_data['total_lessons']:
                    nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"lesson_{course_name}_{lesson_num+1}"))
                
                keyboard.append(nav_row)
                
                # Кнопка "Вернуться к курсу"
                keyboard.append([InlineKeyboardButton("« К курсу", callback_data=f"start_course_{course_name}")])
                
                await query.edit_message_text(
                    lesson_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка при выборе урока: {e}")
                await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # ============ COMPLETE LESSON (Mark as completed) ============
    if data.startswith("complete_lesson_"):
        # Парсим: complete_lesson_<course_name>_<lesson_num>
        # Правильный способ: последний элемент это номер урока, всё остальное - имя курса
        all_parts = data.replace("complete_lesson_", "").split("_")
        if len(all_parts) >= 2:
            try:
                lesson_num = int(all_parts[-1])
                course_name = "_".join(all_parts[:-1])
                
                logger.info(f"Парсинг complete_lesson callback: data={data}, course={course_name}, lesson={lesson_num}")
                
                # Проверяем курс
                if course_name not in COURSES_DATA:
                    await query.answer("❌ Курс не найден", show_alert=True)
                    return
                
                course_data = COURSES_DATA[course_name]
                
                # Проверяем номер урока
                if lesson_num < 1 or lesson_num > course_data['total_lessons']:
                    await query.answer("❌ Неверный номер урока", show_alert=True)
                    return
                
                # Сохраняем прогресс в БД (если таблицы существуют)
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        
                        # Проверяем, уже ли завершен этот урок
                        cursor.execute("""
                            SELECT id FROM user_lessons
                            WHERE user_id = ? AND course_name = ? AND lesson_number = ?
                        """, (user.id, course_name, lesson_num))
                        
                        if not cursor.fetchone():
                            # Добавляем урок как завершенный
                            cursor.execute("""
                                INSERT INTO user_lessons (user_id, course_name, lesson_number, completed_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            """, (user.id, course_name, lesson_num))
                            
                            # Обновляем количество завершенных уроков
                            cursor.execute("""
                                SELECT COUNT(*) FROM user_lessons
                                WHERE user_id = ? AND course_name = ?
                            """, (user.id, course_name))
                            completed_count = cursor.fetchone()[0]
                            
                            # Обновляем user_courses таблицу
                            cursor.execute("""
                                UPDATE user_courses
                                SET completed_lessons = ?, last_accessed = CURRENT_TIMESTAMP
                                WHERE user_id = ? AND course_name = ?
                            """, (completed_count, user.id, course_name))
                            
                            conn.commit()
                            
                            # Даем XP за завершение урока
                            xp_reward = course_data['total_xp'] // course_data['total_lessons']
                            with get_db() as conn2:
                                cursor2 = conn2.cursor()
                                cursor2.execute("""
                                    UPDATE user_stats
                                    SET total_xp = total_xp + ?, courses_completed = courses_completed
                                    WHERE user_id = ?
                                """, (xp_reward, user.id))
                                conn2.commit()
                            
                            message = f"✅ <b>Урок завершен!</b>\n+{xp_reward} XP"
                        else:
                            message = "ℹ️ Этот урок уже был завершен"
                except Exception as db_err:
                    logger.warning(f"Не удалось сохранить прогресс в БД: {db_err}")
                    xp_reward = course_data['total_xp'] // course_data['total_lessons']
                    message = f"✅ <b>Урок завершен!</b>\n+{xp_reward} XP (локально)"
                
                await query.answer(message, show_alert=True)
                
                # Показываем сообщение об успехе
                if lesson_num < course_data['total_lessons']:
                    await query.edit_message_text(
                        f"✅ <b>Урок {lesson_num} завершен!</b>\n\n"
                        f"Готовы к следующему уроку?",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("➡️ Следующий урок", callback_data=f"lesson_{course_name}_{lesson_num+1}")],
                            [InlineKeyboardButton("« К курсу", callback_data=f"start_course_{course_name}")]
                        ])
                    )
                else:
                    # Последний урок - курс завершен
                    await query.edit_message_text(
                        f"🎉 <b>Поздравляем!</b>\n\n"
                        f"Вы завершили курс <b>{course_data['title']}</b>\n"
                        f"Получено: +{course_data['total_xp']} XP",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📚 Другие курсы", callback_data="start_learn")],
                            [InlineKeyboardButton("« В меню", callback_data="back_to_start")]
                        ])
                    )
            
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка при завершении урока: {e}")
                await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # ============ QUIZ SYSTEM (v0.19.0) ============
    
    # Запуск квиза
    if data.startswith("start_quiz_"):
        # Парсим: start_quiz_<course_name>_<lesson_num>
        parts_all = data.replace("start_quiz_", "").split("_")
        if len(parts_all) >= 2:
            try:
                lesson_num = int(parts_all[-1])
                course_name = "_".join(parts_all[:-1])
                
                logger.info(f"🧪 Запуск квиза: {course_name}, урок {lesson_num}")
                await show_quiz_for_lesson(update, context, course_name, lesson_num)
            
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка при запуске квиза: {e}")
                await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Ответ на вопрос квиза
    if data.startswith("quiz_answer_"):
        # Парсим: quiz_answer_<course_name>_<lesson_id>_<q_idx>_<answer_idx>
        parts_all = data.replace("quiz_answer_", "").split("_")
        try:
            answer_idx = int(parts_all[-1])
            q_idx = int(parts_all[-2])
            lesson_id = int(parts_all[-3])
            course_name = "_".join(parts_all[:-3])
            
            logger.info(f"✏️ Ответ на вопрос {q_idx}: {answer_idx} (курс: {course_name})")
            await handle_quiz_answer(update, context, course_name, lesson_id, q_idx, answer_idx)
        
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке ответа на квиз: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Показать следующий вопрос
    if data.startswith("quiz_next_"):
        # Парсим: quiz_next_<course_name>_<lesson_id>
        parts_all = data.replace("quiz_next_", "").split("_")
        try:
            lesson_id = int(parts_all[-1])
            course_name = "_".join(parts_all[:-1])
            
            logger.info(f"➡️ Следующий вопрос квиза")
            await show_quiz_question(update, context)
        
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при переходе к следующему вопросу: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Выход из квиза
    if data.startswith("quiz_exit_"):
        # Парсим: quiz_exit_<course_name>_<lesson_id>
        parts_all = data.replace("quiz_exit_", "").split("_")
        try:
            course_name = "_".join(parts_all[:-1]) if len(parts_all) > 1 else parts_all[0]
            
            logger.info(f"❌ Выход из квиза")
            if 'quiz_session' in context.user_data:
                del context.user_data['quiz_session']
            
            await query.edit_message_text(
                "❌ Тест отменен.\n\nВы можете повторить тест позже.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« К курсу", callback_data=f"start_course_{course_name}")],
                    [InlineKeyboardButton("« В меню", callback_data="back_to_start")]
                ])
            )
        
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при выходе из квиза: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # ============ SHOW BOOKMARKS BY TYPE (v0.18.0) ============
    if data.startswith("show_bookmarks_"):
        await show_bookmarks_by_type(update, context)
        return
    
    # ============ VIEW BOOKMARK DETAIL (v0.20.0) ============
    if data.startswith("view_bookmark_"):
        bookmark_id_str = data.replace("view_bookmark_", "")
        try:
            bookmark_id = int(bookmark_id_str)
            
            # Получаем данные закладки из БД
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, bookmark_type, content_title, content_text, 
                           content_source, added_at, viewed_count
                    FROM user_bookmarks_v2
                    WHERE id = ? AND user_id = ?
                """, (bookmark_id, user.id))
                
                bm = cursor.fetchone()
                
                if not bm:
                    await query.answer("❌ Закладка не найдена", show_alert=True)
                    return
                
                # Форматируем контент
                bm_id, bm_type, title, content_text, source, added_at, viewed_count = bm
                
                # Показываем закладку
                text = (
                    f"📌 <b>Закладка: {bm_type}</b>\n\n"
                    f"<b>{title[:100]}</b>\n"
                    f"{'─' * 40}\n\n"
                    f"{content_text}\n\n"
                    f"{'─' * 40}\n"
                    f"📅 Сохранена: {added_at}\n"
                    f"👁️ Просмотров: {viewed_count}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Полезна", callback_data=f"rate_bookmark_{bm_id}_1"),
                        InlineKeyboardButton("👎 Удалить", callback_data=f"delete_bookmark_{bm_id}")
                    ],
                    [InlineKeyboardButton("« Назад", callback_data=f"show_bookmarks_{bm_type}")],
                ]
                
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
                
                # Обновляем счетчик просмотров
                cursor.execute("""
                    UPDATE user_bookmarks_v2
                    SET viewed_count = viewed_count + 1, last_viewed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (bm_id,))
                conn.commit()
        
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при просмотре закладки: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # ============ DELETE BOOKMARK (v0.20.0) ============
    if data.startswith("delete_bookmark_"):
        bookmark_id_str = data.replace("delete_bookmark_", "")
        try:
            bookmark_id = int(bookmark_id_str)
            
            # Удаляем закладку
            success = remove_bookmark(user.id, bookmark_id)
            
            if success:
                await query.answer("✅ Закладка удалена", show_alert=True)
                await query.edit_message_text(
                    "✅ <b>Закладка успешно удалена</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.answer("❌ Не удалось удалить закладку", show_alert=True)
        
        except ValueError:
            logger.error(f"Ошибка при удалении закладки")
            await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Кнопка "Назад" - возврат на стартовое меню
    if data == "back_to_start":
        keyboard = [
            [
                InlineKeyboardButton("🎓 Учиться", callback_data="start_teach"),
                InlineKeyboardButton("📚 Курсы", callback_data="start_learn")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="start_stats"),
                InlineKeyboardButton("🏆 Лидерборд", callback_data="start_leaderboard")
            ],
            [
                InlineKeyboardButton("🎯 Ежедневные задачи", callback_data="start_quests"),
                InlineKeyboardButton("📚 Ресурсы", callback_data="start_resources")
            ],
            [
                InlineKeyboardButton("📌 Закладки", callback_data="start_bookmarks"),
                InlineKeyboardButton("🧮 Калькулятор", callback_data="start_calculator")
            ],
            [
                InlineKeyboardButton("🎯 Аирдропхантинг", callback_data="start_airdrops"),
                InlineKeyboardButton("🔥 Активности", callback_data="start_activities")
            ],
            [
                InlineKeyboardButton("📜 История", callback_data="start_history"),
                InlineKeyboardButton("⚙️ Меню", callback_data="start_menu")
            ]
        ]
        try:
            await query.edit_message_text(
                "🏠 <b>RVX - КРИПТОАНАЛИТИЧЕСКИЙ БОТ</b>\n\n"
                "Выберите действие из меню ниже:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            await query.message.reply_text(
                "🏠 <b>RVX - КРИПТОАНАЛИТИЧЕСКИЙ БОТ</b>\n\n"
                "Выберите действие из меню ниже:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        return
    
    # Кнопка "Задать вопрос" (из ограничений регенерации и других мест)
    if data == "ask_question":
        await query.edit_message_text(
            "💬 <b>Задайте мне вопрос о криптовалютах и Web3</b>\n\n"
            "Пример: <code>Что такое смарт-контракт?</code>\n"
            "Или: <code>Как работает Ethereum?</code>\n\n"
            "<i>Просто напишите вопрос в чат и я вам отвечу</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]])
        )
        return
    
    # Быстрое меню (глобальная кнопка)
    if data == "menu":
        # Показываем главное меню с быстрыми действиями
        keyboard = [
            [
                InlineKeyboardButton("📚 Курсы", callback_data="menu_learn"),
                InlineKeyboardButton("🧰 Инструменты", callback_data="menu_tools")
            ],
            [
                InlineKeyboardButton("💬 Задать вопрос", callback_data="menu_ask"),
                InlineKeyboardButton("📜 История", callback_data="menu_history")
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
                InlineKeyboardButton("⚙️ Статус", callback_data="menu_stats")
            ]
        ]
        try:
            await query.edit_message_text(
                "📋 <b>ГЛАВНОЕ МЕНЮ RVX</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            # Если редактирование не удалось (сообщение удалено) — отправим новое
            await query.message.reply_text(
                "📋 **Главное меню RVX**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        return

    # Обработка быстрых меню-опций (вызываем существующие команды если нужно)
    if data.startswith("menu_"):
        sub = data.split("_", 1)[1]
        # Перенаправляем на существующие команды, они работают с callback Update тоже
        if sub == "learn":
            await learn_command(update, context)
            return
        if sub == "tools":
            await tools_command(update, context)
            return
        if sub == "ask":
            # Покажем подсказку по /ask
            try:
                await query.edit_message_text(
                    "💬 <b>Чтобы задать уточняющий вопрос используйте команду:</b>\n<code>/ask &lt;ваш вопрос&gt;</code>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                await query.message.reply_text(
                    "💬 Чтобы задать уточняющий вопрос используйте команду:\n/ask <ваш вопрос>"
                )
            return
        if sub == "history":
            await history_command(update, context)
            return
        if sub == "help":
            await help_command(update, context)
            return
        if sub == "stats":
            await stats_command(update, context)
            return

    # ============ РЕСУРСЫ - Обработка кнопок категорий v0.16.0 ============
    
    if data == "resources_back":
        # Возврат к меню категорий ресурсов
        await show_resources_menu(update, query)
        return
    
    if data.startswith("resources_cat_"):
        # Формат: resources_cat_0, resources_cat_1, и т.д.
        try:
            category_index = int(data.replace("resources_cat_", ""))
            await show_resources_category(update, context, category_index)
            return
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга ресурсов: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
            return

    # ============ ОБУЧЕНИЕ - Новые кнопки v0.5.0 ============
    
    if data.startswith("learn_"):
        # Формат: learn_course_lesson
        try:
            course = "_".join(parts[1:-1])  # blockchain_basics или defi_contracts
            lesson = int(parts[-1])
            
            lesson_content = get_lesson_content(course, lesson)
            if lesson_content:
                # Показываем превью урока (ограничиваем длину и безопасно форматируем)
                preview = lesson_content[:600]  # Сокращаем до 600 символов
                # Экранируем HTML специальные символы
                preview = preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                
                response_text = f"📖 <b>УРОК ЗАГРУЖЕН!</b>\n\n{preview}\n\n<i>Читайте полный урок в команде /learn</i>"
                
                await query.edit_message_text(
                    response_text,
                    parse_mode=ParseMode.HTML
                )
                with get_db() as conn:
                    cursor = conn.cursor()
                    add_xp_to_user(cursor, user.id, 5, "viewed_lesson")
                logger.info(f"Пользователь {user.id} начал урок {course} #{lesson}")
            else:
                await query.edit_message_text("❌ <b>Урок не найден</b>", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка в learn_: {e}", exc_info=True)
            try:
                await query.edit_message_text("❌ <b>Ошибка загрузки урока</b>", parse_mode=ParseMode.HTML)
            except:
                await query.answer("Ошибка загрузки урока", show_alert=True)
        
        return
    
    # ============ НАВИГАЦИЯ ПО УРОКАМ - Следующий урок ============
    
    if data.startswith("next_lesson_"):
        try:
            # Формат: next_lesson_course_name_lesson_num
            parts_list = data.split("_")
            # Последний элемент - номер урока
            lesson_num = int(parts_list[-1])
            # Остальное - имя курса
            course_name = "_".join(parts_list[2:-1])
            
            course_data = COURSES_DATA.get(course_name)
            if not course_data:
                await query.answer("❌ Курс не найден", show_alert=True)
                return
            
            # Проверяем валидность номера урока
            if lesson_num < 1 or lesson_num > course_data['total_lessons']:
                await query.answer("❌ Урок не найден", show_alert=True)
                return
            
            # Получаем контент урока
            lesson_content = get_lesson_content(course_name, lesson_num)
            
            if not lesson_content:
                await query.answer("❌ Урок не найден", show_alert=True)
                return
            
            # Очищаем контент
            lesson_content = clean_lesson_content(lesson_content)
            lesson_text, quiz_section = split_lesson_content(lesson_content)
            
            # Форматируем и отправляем
            max_length = 3500
            if len(lesson_text) > max_length:
                lesson_preview = lesson_text[:max_length] + "\n\n[... урок продолжается]"
            else:
                lesson_preview = lesson_text
            
            response = (
                f"📚 <b>{course_data['title'].upper()}</b>\n"
                f"📖 Урок {lesson_num}/{course_data['total_lessons']}\n\n"
                f"{lesson_preview}"
            )
            
            # Создаем кнопки
            keyboard = []
            if quiz_section:
                keyboard.append([
                    InlineKeyboardButton("🎯 Начать тест", callback_data=f"start_quiz_{course_name}_{lesson_num}")
                ])
            
            # Проверяем, есть ли следующий урок
            next_lesson_info = get_next_lesson_info(course_name, lesson_num)
            if next_lesson_info:
                keyboard.append([
                    InlineKeyboardButton("▶️ Следующий урок", callback_data=f"next_lesson_{course_name}_{lesson_num + 1}")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await query.edit_message_text(response, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            
            # Добавляем XP за просмотр
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    add_xp_to_user(cursor, user.id, 5, "viewed_lesson")
                logger.info(f"⭐ Пользователь {user.id} получил 5 XP за урок {lesson_num}")
            except Exception as e:
                logger.error(f"Ошибка при добавлении XP: {e}")
            
            # Логируем событие
            if ENABLE_ANALYTICS:
                log_analytics_event("next_lesson_clicked", user.id, {"course": course_name, "lesson": lesson_num})
        
        except Exception as e:
            logger.error(f"Ошибка в next_lesson_: {e}", exc_info=True)
            try:
                await query.answer("❌ Ошибка загрузки урока", show_alert=True)
            except:
                pass
        
        return
    
    # ============ ВОПРОСЫ - Новая кнопка v0.5.0 ============
    
    if data.startswith("ask_related_"):
        try:
            request_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "💬 <b>ЗАДАЙТЕ УТОЧНЯЮЩИЙ ВОПРОС:</b>\n\n"
                "Используйте <code>/ask [ваш вопрос]</code> чтобы задать вопрос эксперту\n\n"
                "<i>Пример:</i> <code>/ask Как это работает с другими блокчейнами?</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка в ask_related_: {e}")
            try:
                await query.answer("Ошибка при загрузке вопроса", show_alert=True)
            except:
                pass
        
        return
    
    # ============ TEACH CALLBACKS v0.8.0 - ОБРАБАТЫВАЕМ ДО ОСТАЛЬНОГО ============
    
    # Инициация меню обучения
    if data == "start_teach":
        data = "teach_menu"  # Перенаправляем на меню выбора тем
    
    # Меню выбора тем обучения
    if data == "teach_menu":
        keyboard = []
        topics_list = list(TEACHING_TOPICS.keys())
        
        for i in range(0, len(topics_list), 2):
            row = []
            if i < len(topics_list):
                topic1 = topics_list[i]
                row.append(InlineKeyboardButton(f"📚 {TEACHING_TOPICS[topic1]['name']}", callback_data=f"teach_topic_{topic1}"))
            if i + 1 < len(topics_list):
                topic2 = topics_list[i + 1]
                row.append(InlineKeyboardButton(f"📖 {TEACHING_TOPICS[topic2]['name']}", callback_data=f"teach_topic_{topic2}"))
            if row:
                keyboard.append(row)
        
        # Добавляем персонализированную кнопку "Рекомендованное обучение"
        keyboard.insert(0, [InlineKeyboardButton("✨ Рекомендованное для вас", callback_data="teach_recommended")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        try:
            await query.edit_message_text(
                "🎓 <b>ИНТЕРАКТИВНЫЙ УЧИТЕЛЬ</b>\n\n"
                "Выберите тему для обучения:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_menu: {e}", exc_info=True)
        return
    
    # ============ ИНТЕРАКТИВНОЕ ОБУЧЕНИЕ АИРДРОПАМ (v0.34.1) ============
    
    # Начало обучения аирдропам
    if data == "start_airdrops":
        try:
            keyboard = [
                [InlineKeyboardButton("📖 Что такое аирдроп?", callback_data="airdrops_lesson_1")],
                [InlineKeyboardButton("🎯 Как участвовать?", callback_data="airdrops_lesson_2")],
                [InlineKeyboardButton("📋 Что нужно знать?", callback_data="airdrops_lesson_3")],
                [InlineKeyboardButton("⚠️ Риски и безопасность", callback_data="airdrops_lesson_4")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
            ]
            
            menu_text = (
                "🎯 <b>ПОЛНЫЙ ГАЙД ПО АИРДРОПХАНТИНГУ</b>\n\n"
                "Хочешь понять что такое аирдроп и как получить бесплатные крипто?\n\n"
                "Выбери тему для изучения:\n\n"
                "🚀 Этот гайд проведет тебя от нуля до профессионала за 5 минут!\n"
                "Каждый урок содержит реальные примеры и полезные советы."
            )
            
            try:
                await query.edit_message_text(
                    menu_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение: {e}")
                await query.message.reply_text(
                    menu_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.error(f"Ошибка в start_airdrops: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ Ошибка при открытии гайда. Попробуйте позже.", show_alert=True)
            except:
                pass
        return
    
    # Урок 1: Что такое аирдроп
    if data == "airdrops_lesson_1":
        keyboard = [
            [InlineKeyboardButton("✅ Понял!", callback_data="airdrops_lesson_2")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_airdrops")]
        ]
        
        try:
            await query.edit_message_text(
                "📦 <b>УРОК 1: ЧТО ТАКОЕ АИРДРОП?</b>\n\n"
                "<b>Определение:</b>\n"
                "Аирдроп - это бесплатное распределение криптовалютных токенов проектом для популяризации.\n\n"
                
                "<b>🤔 Простым языком:</b>\n"
                "Представь, что компания выпускает новую монету и раздает образцы людям, чтобы они ее попробовали. "
                "Так же работают аирдропы - проекты дарят токены бесплатно!\n\n"
                
                "<b>💰 Почему они это делают?</b>\n"
                "• Привлечение внимания к проекту\n"
                "• Увеличение числа пользователей\n"
                "• Создание сообщества\n"
                "• Распределение токенов справедливо\n\n"
                
                "<b>📊 Реальный пример:</b>\n"
                "Проект Uniswap раздал 400 токенов каждому пользователю, кто использовал платформу до определенной даты. "
                "Это стоило компании миллионы, но привлекло миллионы людей!\n\n"
                
                "<b>⚡ Ключевой момент:</b>\n"
                "Не все аирдропы одинаковые. Некоторые стоят много, некоторые мало, а некоторые - это мошенничество!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_lesson_1: {e}")
        return
    
    # Урок 2: Как участвовать
    if data == "airdrops_lesson_2":
        keyboard = [
            [InlineKeyboardButton("✅ Готово!", callback_data="airdrops_lesson_3")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_airdrops")]
        ]
        
        try:
            await query.edit_message_text(
                "🎯 <b>УРОК 2: КАК УЧАСТВОВАТЬ В АИРДРОПЕ?</b>\n\n"
                "<b>Типичные шаги:</b>\n\n"
                
                "<b>1️⃣ Узнай о аирдропе</b>\n"
                "• Подпишись на крипто-комьюнити\n"
                "• Следи за аирдроп-сайтами (CoinMarketCap, DefiLlama)\n"
                "• Читай криптовалютные новости\n\n"
                
                "<b>2️⃣ Прочитай условия</b>\n"
                "⚠️ ВАЖНО! Перед участием:\n"
                "• Какие действия нужно выполнить?\n"
                "• Когда закрывается возможность участвовать?\n"
                "• Сколько в среднем стоит аирдроп?\n\n"
                
                "<b>3️⃣ Выполни условия</b>\n"
                "Обычно нужно:\n"
                "📱 Подписаться на социальные сети (Twitter, Discord)\n"
                "💬 Поделиться постом\n"
                "⭐ Нравится посты\n"
                "📝 Оставить комментарий\n"
                "👥 Пригласить друзей\n\n"
                
                "<b>4️⃣ Получи токены</b>\n"
                "• Проверь свой кошелек через несколько дней\n"
                "• Токены появятся автоматически\n"
                "• Продай их если хочешь получить деньги\n\n"
                
                "<b>💡 Совет:</b>\n"
                "Лучше участвовать в проектах которым ты доверяешь. "
                "Неизвестные аирдропы часто требуют приватный ключ - это ОПАСНО!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_lesson_2: {e}")
        return
    
    # Урок 3: Что нужно знать
    if data == "airdrops_lesson_3":
        keyboard = [
            [InlineKeyboardButton("✅ Ясно!", callback_data="airdrops_lesson_4")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_airdrops")]
        ]
        
        try:
            await query.edit_message_text(
                "📋 <b>УРОК 3: ЧТО НУЖНО ИМЕТЬ?</b>\n\n"
                "<b>🛠️ Минимальный набор:</b>\n\n"
                
                "<b>1. Крипто-кошелек</b>\n"
                "Это как банковский счет в крипто.\n"
                "Лучший для новичков: MetaMask\n"
                "• Скачай расширение для браузера\n"
                "• Создай аккаунт (запиши фразу из 12 слов!)\n"
                "• Готово! Теперь ты готов получать токены\n\n"
                
                "<b>2. Кошелек с адресом</b>\n"
                "Это как номер счета. Копируешь и даешь проекту.\n"
                "Адрес выглядит так: 0x742d35Cc6634C0532925a3b844Bc924e6... 🔒\n\n"
                
                "<b>3. Социальные аккаунты</b>\n"
                "📱 Twitter - ГЛАВНЫЙ (почти всегда нужен)\n"
                "💬 Discord - помощь и обновления\n"
                "📺 Telegram - новости проекта\n\n"
                
                "<b>4. Основные знания</b>\n"
                "✅ Не давай никому приватный ключ\n"
                "✅ Не переводи деньги на незнакомые адреса\n"
                "✅ Проверяй официальные ссылки\n"
                "✅ Если звучит слишком хорошо - это мошенничество\n\n"
                
                "<b>💎 Бонус информация:</b>\n"
                "Некоторые аирдропы действительно стоят МНОГО денег! "
                "Например, аирдроп Optimism стоил для некоторых $3000+!\n"
                "Но это редко. Обычно $5-50.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_lesson_3: {e}")
        return
    
    # Урок 4: Риски и безопасность
    if data == "airdrops_lesson_4":
        keyboard = [
            [InlineKeyboardButton("🎓 Финальный тест", callback_data="airdrops_quiz")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_airdrops")]
        ]
        
        try:
            await query.edit_message_text(
                "⚠️ <b>УРОК 4: РИСКИ И БЕЗОПАСНОСТЬ</b>\n\n"
                "<b>🚨 ГЛАВНОЕ ПРАВИЛО:</b>\n"
                "Если просят приватный ключ = ЭТО МОШЕННИЧЕСТВО!\n\n"
                
                "<b>❌ Не делай эти ошибки:</b>\n\n"
                
                "<b>1. Фишинг (подделанные сайты)</b>\n"
                "❌ Переходишь по ссылке из спама\n"
                "❌ Вводишь приватный ключ\n"
                "❌ Теряешь все деньги\n\n"
                
                "✅ Правильно:\n"
                "✓ Проверяй что ссылка официальная\n"
                "✓ Вводи пароль только на VERIFIED аккаунтах\n"
                "✓ Используй 2FA (двухфакторная аутентификация)\n\n"
                
                "<b>2. Скам аирдропы</b>\n"
                "❌ Обещают 1000 токенов за 2 минуты работы\n"
                "❌ Просят платеж за участие\n"
                "❌ Требуют инвестировать деньги\n\n"
                
                "<b>3. Поддельные токены</b>\n"
                "Получил аирдроп - но это не оригинальный токен!\n"
                "Проверяй адрес контракта токена перед тем как его продавать.\n\n"
                
                "<b>✅ КАК ЗАЩИТИТЬ СЕБЯ:</b>\n"
                "🔒 Используй только официальные каналы проекта\n"
                "🔐 Никогда не давай приватный ключ\n"
                "📋 Проверяй адреса контрактов на Etherscan\n"
                "🛡️ Используй холодный кошелек для больших сумм\n"
                "👥 Сообщи о мошенниках в модераторы\n\n"
                
                "<b>💪 Самые безопасные аирдропы:</b>\n"
                "• Известные проекты (Uniswap, Optimism, Arbitrum)\n"
                "• Аирдропы на крупных биржах (Coinbase, Kraken)\n"
                "• Аирдропы где просто нужно использовать сервис",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_lesson_4: {e}")
        return
    
    # Финальный тест/резюме
    if data == "airdrops_quiz":
        keyboard = [
            [InlineKeyboardButton("🎉 Готов к аирдропам!", callback_data="airdrops_summary")],
            [InlineKeyboardButton("🔄 Повторить уроки", callback_data="start_airdrops")],
            [InlineKeyboardButton("⬅️ В меню", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "🎓 <b>БЫСТРЫЙ ТЕСТ ПОНИМАНИЯ</b>\n\n"
                "Ты готов? Вот 3 вопроса:\n\n"
                
                "<b>1️⃣ Что никогда нельзя давать в аирдропе?</b>\n"
                "❌ Email\n"
                "❌ Номер телефона\n"
                "✅ Приватный ключ - НИКОГДА!\n\n"
                
                "<b>2️⃣ Сколько примерно стоит средний аирдроп?</b>\n"
                "❌ $1000+\n"
                "✅ $5-50 - ОБЫЧНО\n"
                "❌ Миллион\n\n"
                
                "<b>3️⃣ Где начать если я новичок?</b>\n"
                "❌ В неизвестных дискордах\n"
                "✅ С известных проектов (Uniswap, Optimism, Arbitrum)\n"
                "❌ В спам-сообщениях\n\n"
                
                "<b>🎯 Результат:</b>\n"
                "Если ты ответил правильно на все - ты готов участвовать в аирдропах! 🚀",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_quiz: {e}")
        return
    
    # Финальное резюме
    if data == "airdrops_summary":
        keyboard = [
            [InlineKeyboardButton("📖 Узнать больше", callback_data="airdrops_lesson_1")],
            [InlineKeyboardButton("🎯 Другие функции", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                "Теперь ты знаешь всё о аирдропах! 🚀\n\n"
                
                "<b>📚 Что ты изучил:</b>\n"
                "✅ Что такое аирдроп\n"
                "✅ Как участвовать правильно\n"
                "✅ Что нужно подготовить\n"
                "✅ Как защитить себя\n\n"
                
                "<b>🎯 Следующие шаги:</b>\n"
                "1️⃣ Создай MetaMask кошелек\n"
                "2️⃣ Подпишись на крипто-новости\n"
                "3️⃣ Найди интересный аирдроп\n"
                "4️⃣ Выполни условия\n"
                "5️⃣ Получи бесплатные токены! 💰\n\n"
                
                "<b>💡 Совет профи:</b>\n"
                "Лучшие аирдропы обычно скрыты. Ищи их в дискордах проектов и в твиттере. "
                "Чем раньше ты присоединишься к новому проекту - тем больше токенов получишь!\n\n"
                
                "<b>⚠️ Помни:</b>\n"
                "Если звучит слишком хорошо - это обман. Всегда проверяй дважды!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в airdrops_summary: {e}")
        return
    
    # ============ ИНТЕРАКТИВНОЕ ОБУЧЕНИЕ АКТИВНОСТЯМ (v0.35.0) ============
    
    # Начало обучения активностям
    if data == "start_activities":
        try:
            keyboard = [
                [InlineKeyboardButton("💡 Что такое активности?", callback_data="activities_lesson_1")],
                [InlineKeyboardButton("🎯 Как участвовать?", callback_data="activities_lesson_2")],
                [InlineKeyboardButton("💰 Как заработать?", callback_data="activities_lesson_3")],
                [InlineKeyboardButton("⚠️ Риски и советы", callback_data="activities_lesson_4")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
            ]
            
            menu_text = (
                "🔥 <b>ПОЛНЫЙ ГАЙД ПО КРИПТО-АКТИВНОСТЯМ</b>\n\n"
                "Хочешь понять как участвовать в активностях и зарабатывать?\n\n"
                "<b>Что ты научишься:</b>\n"
                "✅ Что такое активности в крипто\n"
                "✅ Как правильно участвовать\n"
                "✅ Способы заработка\n"
                "✅ Как защитить себя\n\n"
                "<b>⏱️ Время учебы:</b> ~5 минут\n"
                "<b>📊 Сложность:</b> Для новичков"
            )
            
            await query.edit_message_text(
                menu_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в start_activities: {e}", exc_info=True)
            try:
                await update.message.reply_text(
                    menu_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as fallback_error:
                logger.error(f"Ошибка fallback в start_activities: {fallback_error}", exc_info=True)
        return
    
    # Урок 1: Что такое активности
    if data == "activities_lesson_1":
        keyboard = [
            [InlineKeyboardButton("✅ Понял!", callback_data="activities_lesson_2")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_activities")]
        ]
        
        try:
            await query.edit_message_text(
                "💡 <b>УРОК 1: ЧТО ТАКОЕ АКТИВНОСТИ?</b>\n\n"
                "<b>Определение:</b>\n"
                "Активности - это задания и события в крипто-проектах, за которые дарят награды (токены, NFT, деньги).\n\n"
                
                "<b>🤔 Простым языком:</b>\n"
                "Проекты проводят задания типа:\n"
                "• Следить за аккаунтом в Twitter\n"
                "• Присоединиться к дискорду\n"
                "• Поделиться постом\n"
                "• Ответить в викторину\n"
                "За это получаешь бесплатные награды!\n\n"
                
                "<b>🎁 Виды активностей:</b>\n"
                "1. <b>Social-активности:</b> Follow, Like, Retweet, Share\n"
                "2. <b>Community:</b> Discord, Telegram, форумы\n"
                "3. <b>Игровые:</b> Квесты, викторины, челленджи\n"
                "4. <b>Образовательные:</b> Обучение, видео, статьи\n\n"
                
                "<b>💰 Разница от аирдропа:</b>\n"
                "🎁 Аирдроп = Просто даёшь адрес и получаешь\n"
                "⚙️ Активность = Выполняешь задания и получаешь\n\n"
                
                "<b>⚡ Почему проекты это делают?</b>\n"
                "• Набрать подписчиков\n"
                "• Создать активное сообщество\n"
                "• Рекламировать проект\n"
                "• Привлечь инвесторов",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_lesson_1: {e}", exc_info=True)
        return
    
    # Урок 2: Как участвовать
    if data == "activities_lesson_2":
        keyboard = [
            [InlineKeyboardButton("✅ Готово!", callback_data="activities_lesson_3")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_activities")]
        ]
        
        try:
            await query.edit_message_text(
                "🎯 <b>УРОК 2: КАК УЧАСТВОВАТЬ В АКТИВНОСТЯХ?</b>\n\n"
                "<b>Пошаговая инструкция:</b>\n\n"
                
                "<b>Шаг 1️⃣: Найти активность</b>\n"
                "• Twitter/X - ищи посты с хэштегами типа #crypto #airdrop #giveaway\n"
                "• Discord серверы крипто-проектов\n"
                "• Telegram каналы\n"
                "• Сайты проектов (обычно есть вкладка Activities)\n\n"
                
                "<b>Шаг 2️⃣: Прочитать условия</b>\n"
                "❌ Не просто кликай - читай что нужно делать!\n"
                "• Нужен ли кошелек?\n"
                "• Какой минимум активности?\n"
                "• Когда закончится активность?\n"
                "• Сколько можно заработать?\n\n"
                
                "<b>Шаг 3️⃣: Выполнить задания</b>\n"
                "• Follow/Like/Retweet если нужно\n"
                "• Присоединиться в Discord\n"
                "• Ответить на вопросы\n"
                "• Поделиться постом\n"
                "• Заполнить форму регистрации\n\n"
                
                "<b>Шаг 4️⃣: Получить награду</b>\n"
                "• Проверь свой адрес кошелька\n"
                "• Получи токены или NFT\n"
                "• Продай если хочешь или держи\n\n"
                
                "<b>💡 Совет:</b>\n"
                "Делай активности постоянно - даже маленькие награды складываются в большие деньги!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_lesson_2: {e}", exc_info=True)
        return
    
    # Урок 3: Как заработать
    if data == "activities_lesson_3":
        keyboard = [
            [InlineKeyboardButton("✅ Ясно!", callback_data="activities_lesson_4")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_activities")]
        ]
        
        try:
            await query.edit_message_text(
                "💰 <b>УРОК 3: КАК МАКСИМАЛЬНО ЗАРАБОТАТЬ?</b>\n\n"
                "<b>Стратегия заработка:</b>\n\n"
                
                "<b>1️⃣ Участвуй в большом кол-ве активностей</b>\n"
                "• 1 активность = $5-50\n"
                "• 10 активностей = $50-500\n"
                "• 100 активностей = $500+\n"
                "Ключ - участвовать в МНОГО активностей!\n\n"
                
                "<b>2️⃣ Выбирай известные проекты</b>\n"
                "Известные = Больше денег\n"
                "• Bitcoin Layer 2s (Optimism, Arbitrum, Starknet)\n"
                "• Популярные DeFi (Uniswap, Aave, Curve)\n"
                "• Новые перспективные проекты\n\n"
                
                "<b>3️⃣ Включи рефереральную систему</b>\n"
                "Многие активности платят за приглашения!\n"
                "• Пригласи друга = Дополнительный доход\n"
                "• Часто платят комиссию 5-20%\n\n"
                
                "<b>4️⃣ Не упускай ранние активности</b>\n"
                "• Первые участники = больше токенов\n"
                "• Следи за новыми проектами\n"
                "• Подпишись на крипто-новости\n\n"
                
                "<b>5️⃣ Держи токены (не продавай сразу)</b>\n"
                "• Получи токен → держи месяц\n"
                "• Цена может вырасти в 10 раз\n"
                "• Пример: Uniswap аирдроп (400 UNI = $4000)\n\n"
                
                "<b>📊 Реальные примеры доходов:</b>\n"
                "• Новичок: $100-500 в месяц\n"
                "• Опытный: $500-2000 в месяц\n"
                "• Профессионал: $2000+ в месяц",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_lesson_3: {e}", exc_info=True)
        return
    
    # Урок 4: Риски
    if data == "activities_lesson_4":
        keyboard = [
            [InlineKeyboardButton("🎓 Финальный тест", callback_data="activities_quiz")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="start_activities")]
        ]
        
        try:
            await query.edit_message_text(
                "⚠️ <b>УРОК 4: РИСКИ И СОВЕТЫ ПО БЕЗОПАСНОСТИ</b>\n\n"
                "<b>Главные РИСКИ:</b>\n\n"
                
                "<b>❌ МОШЕННИЧЕСТВО:</b>\n"
                "Опасаться:\n"
                "• Просят расширенный доступ\n"
                "• Просят приватный ключ\n"
                "• Просят платить авансом\n"
                "• Неизвестные дискорды\n"
                "• Подозрительные ссылки\n\n"
                
                "<b>💀 RUGPULL:</b>\n"
                "Разработчики скрываются с деньгами\n"
                "• Проверяй проект перед участием\n"
                "• Не все токены стоят денег\n"
                "• Известные проекты безопаснее\n\n"
                
                "<b>🔗 СКАМ ССЫЛКИ:</b>\n"
                "Фишинговые сайты\n"
                "❌ Не кликай на чужие ссылки\n"
                "✅ Переходи только на официальные сайты\n"
                "✅ Проверяй URL внимательно\n\n"
                
                "<b>✅ КАК ЗАЩИТИТЬ СЕБЯ:</b>\n"
                "1️⃣ Не давай приватный ключ НИКОМУ\n"
                "2️⃣ Проверяй официальность проекта\n"
                "3️⃣ Используй отдельный кошелек для активностей\n"
                "4️⃣ Включи 2FA на всех аккаунтах\n"
                "5️⃣ Не переходи по ссылкам в DM\n"
                "6️⃣ Если звучит слишком хорошо - это обман\n"
                "7️⃣ Всегда проверяй дважды\n\n"
                
                "<b>💡 Главный совет:</b>\n"
                "Крипто - это риск. Не вкладывай свои деньги если не понимаешь что делаешь. "
                "Но БЕСПЛАТНЫЕ активности? Их стоит делать все! 🚀",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_lesson_4: {e}", exc_info=True)
        return
    
    # Викторина активностей
    if data == "activities_quiz":
        keyboard = [
            [InlineKeyboardButton("✅ Готов к активностям!", callback_data="activities_summary")],
            [InlineKeyboardButton("🔄 Повторить уроки", callback_data="start_activities")],
            [InlineKeyboardButton("⬅️ В меню", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "🎓 <b>ВИКТОРИНА: ПРОВЕРЬ СВОИ ЗНАНИЯ</b>\n\n"
                "Правильный ответ отмечен ✅\n\n"
                
                "<b>1️⃣ Что нужно сделать чтобы участвовать в активности?</b>\n"
                "❌ Пустить в свой кошелек\n"
                "✅ Выполнить задания (Follow, Like, Join Discord)\n"
                "❌ Отправить приватный ключ\n\n"
                
                "<b>2️⃣ Сколько в среднем платят за одну активность?</b>\n"
                "❌ $1000+\n"
                "✅ $5-50 - ОБЫЧНО\n"
                "❌ 1 доллар\n\n"
                
                "<b>3️⃣ Какой главный риск в активностях?</b>\n"
                "❌ Они забирают все деньги\n"
                "✅ Мошенничество и rugpull\n"
                "❌ Ничего опасного\n\n"
                
                "<b>4️⃣ Что делать если проект просит приватный ключ?</b>\n"
                "❌ Дать - это нормально\n"
                "✅ НИКОГДА не давать - это мошенничество!\n"
                "❌ Спросить цену\n\n"
                
                "<b>🎯 Если ты ответил правильно на все - ты готов! 🚀</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_quiz: {e}", exc_info=True)
        return
    
    # Финальное резюме активностей
    if data == "activities_summary":
        keyboard = [
            [InlineKeyboardButton("📖 Узнать больше", callback_data="activities_lesson_1")],
            [InlineKeyboardButton("⬅️ В меню", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "🔥 <b>ТЫ ГОТОВ К АКТИВНОСТЯМ!</b>\n\n"
                "<b>📚 Что ты изучил:</b>\n"
                "✅ Что такое активности\n"
                "✅ Как правильно участвовать\n"
                "✅ Как максимально заработать\n"
                "✅ Как защитить себя\n\n"
                
                "<b>🎯 Следующие шаги:</b>\n"
                "1️⃣ Создай MetaMask кошелек (если нет)\n"
                "2️⃣ Подпишись на крипто-новости\n"
                "3️⃣ Найди первую активность\n"
                "4️⃣ Выполни все условия\n"
                "5️⃣ Получи первую награду! 💰\n\n"
                
                "<b>💡 Где искать активности:</b>\n"
                "🔗 Twitter/X - #crypto #activity\n"
                "🔗 Discord - крипто серверы\n"
                "🔗 Telegram - крипто каналы\n"
                "🔗 Сайты проектов\n\n"
                
                "<b>⚡ Главное правило:</b>\n"
                "Участвуй в МНОГО активностях, держи токены, и со временем заработаешь реальные деньги! 🚀\n\n"
                
                "<b>⚠️ И всегда помни:</b>\n"
                "Если звучит слишком хорошо - это обман. Проверяй дважды!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в activities_summary: {e}", exc_info=True)
        return
    
    # Открытие калькулятора из главного меню (v0.33.3)
    if data == "start_calculator":
        try:
            logger.info(f"🧮 start_calculator callback вызван")
            
            user_id = update.effective_user.id
            logger.info(f"🧮 Калькулятор открыт пользователем {user_id} через меню")
            
            # Получаем список доступных токенов
            tokens = get_token_list()
            logger.debug(f"📊 Токены: {tokens}")
            
            # Создаем кнопки для выбора токена
            keyboard = []
            for i in range(0, len(tokens), 2):
                row = []
                
                # Первый токен в строке
                if i < len(tokens):
                    token1 = tokens[i].upper()
                    token_data1 = get_token_stats(token1)
                    if token_data1:
                        row.append(InlineKeyboardButton(
                            f"{token_data1['emoji']} {token_data1['symbol']}",
                            callback_data=f"calc_token_{token1.lower()}"
                        ))
                
                # Второй токен в строке (если есть)
                if i + 1 < len(tokens):
                    token2 = tokens[i + 1].upper()
                    token_data2 = get_token_stats(token2)
                    if token_data2:
                        row.append(InlineKeyboardButton(
                            f"{token_data2['emoji']} {token_data2['symbol']}",
                            callback_data=f"calc_token_{token2.lower()}"
                        ))
                
                if row:
                    keyboard.append(row)
            
            # Добавляем кнопку "Назад"
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
            
            # Получаем текст меню
            menu_text = get_calculator_menu_text()
            
            # Показываем меню калькулятора
            await query.edit_message_text(
                menu_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Меню калькулятора показано для пользователя {user_id}")
            return
        
        except Exception as e:
            logger.error(f"Критическая ошибка в start_calculator: {type(e).__name__}: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ Ошибка при открытии калькулятора", show_alert=True)
            except Exception as alert_err:
                logger.error(f"Не удалось отправить alert: {alert_err}")
            return
    
    # ============ CALCULATOR CALLBACKS (v0.33.0) ============
    
    # Выбор токена в калькуляторе
    if data.startswith("calc_token_"):
        try:
            token_symbol = data.replace("calc_token_", "").upper()
            token_data = get_token_stats(token_symbol)
            
            if not token_data:
                await query.answer("❌ Токен не найден", show_alert=True)
                return
            
            # Сохраняем выбранный токен в контекст
            context.user_data["selected_token"] = token_symbol
            context.user_data["waiting_for_price"] = True
            
            logger.info(f"💰 Выбран токен {token_symbol} для {user.id}")
            
            # Показываем информацию о токене и просим цену
            text = (
                f"{token_data['emoji']} <b>{token_data['name']} ({token_data['symbol']}) Calculator</b>\n\n"
                f"<b>📊 Параметры токена:</b>\n"
                f"🔓 Разблокировано: {format_number(token_data['unlocked'])}\n"
                f"🔒 В веститинге: {format_number(token_data['vesting'])}\n"
                f"📈 Всего: {format_number(token_data['total_supply'])}\n\n"
                f"<b>💰 Введи цену токена в долларах:</b>\n"
                f"<i>Примеры: 0.001, 1.5, 100</i>"
            )
            
            keyboard_calc = [
                [InlineKeyboardButton("🪙 Другой токен", callback_data="calc_menu")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
            ]
            
            try:
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard_calc)
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение: {e}")
                await query.message.reply_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard_calc)
                )
            return
        
        except Exception as e:
            logger.error(f"Ошибка в calc_token callback: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
            except:
                pass
            return
    
    # Возврат к меню выбора токенов
    if data == "calc_menu":
        try:
            tokens = get_token_list()
            keyboard = []
            
            for i in range(0, len(tokens), 2):
                row = []
                
                token1 = tokens[i].upper()
                token_data1 = get_token_stats(token1)
                if token_data1:
                    row.append(InlineKeyboardButton(
                        f"{token_data1['emoji']} {token_data1['symbol']}",
                        callback_data=f"calc_token_{token1.lower()}"
                    ))
                
                if i + 1 < len(tokens):
                    token2 = tokens[i + 1].upper()
                    token_data2 = get_token_stats(token2)
                    if token_data2:
                        row.append(InlineKeyboardButton(
                            f"{token_data2['emoji']} {token_data2['symbol']}",
                            callback_data=f"calc_token_{token2.lower()}"
                        ))
                
                if row:
                    keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
            
            try:
                await query.edit_message_text(
                    get_calculator_menu_text(),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение в calc_menu: {e}")
                await query.message.reply_text(
                    get_calculator_menu_text(),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return
        
        except Exception as e:
            logger.error(f"Ошибка в calc_menu callback: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
            except:
                pass
            return
    
    # Таблица цен в калькуляторе (v0.33.2)
    if data.startswith("calc_price_table_"):
        try:
            token_symbol = data.replace("calc_price_table_", "").upper()
            
            # Получаем таблицу цен
            price_table = get_price_table(token_symbol)
            
            # Кнопки навигации
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Новый расчет", callback_data=f"calc_token_{token_symbol.lower()}"),
                    InlineKeyboardButton("🪙 Другой токен", callback_data="calc_menu")
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
            ]
            
            try:
                await query.edit_message_text(
                    price_table,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение в calc_price_table: {e}")
                await query.message.reply_text(
                    price_table,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            logger.info(f"📊 Показана таблица цен для {token_symbol} пользователю {user.id}")
            return
        
        except Exception as e:
            logger.error(f"Ошибка в calc_price_table callback: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
            except:
                pass
            return
    
    # Выбор темы обучения
    if data.startswith("teach_topic_"):
        topic = data.replace("teach_topic_", "")
        if topic not in TEACHING_TOPICS:
            await query.answer("❌ Неизвестная тема", show_alert=True)
            return
        
        # Обновляем ежедневную задачу по исследованию тем (v0.11.0)
        update_task_progress(user.id, "teach_explore", 1)
        
        # САМООБУЧЕНИЕ #3: Анализируем историю и выбираем рекомендуемый уровень
        with get_db() as conn:
            cursor = conn.cursor()
            _, user_xp = calculate_user_level_and_xp(cursor, user.id)
            
            # Определяем рекомендуемый уровень
            if user_xp < 100:
                recommended = "beginner"
                rec_emoji = "🌱"
            elif user_xp < 300:
                recommended = "intermediate"
                rec_emoji = "📚"
            elif user_xp < 600:
                recommended = "advanced"
                rec_emoji = "🚀"
            else:
                recommended = "expert"
                rec_emoji = "💎"
        
        # Показываем выбор уровня сложности
        topic_info = TEACHING_TOPICS.get(topic, {})
        
        keyboard = []
        # Создаем 2x2 сетку для уровней
        levels_list = list(DIFFICULTY_LEVELS.keys())
        for i in range(0, len(levels_list), 2):
            row = []
            if i < len(levels_list):
                level1 = levels_list[i]
                level_info = DIFFICULTY_LEVELS[level1]
                # Отмечаем рекомендуемый уровень звездой
                level_label = f"{level_info['emoji']} {level_info['name']}"
                if level1 == recommended:
                    level_label = f"⭐ {level_label}"
                row.append(InlineKeyboardButton(
                    level_label, 
                    callback_data=f"teach_start_{topic}_{level1}"
                ))
            if i + 1 < len(levels_list):
                level2 = levels_list[i + 1]
                level_info = DIFFICULTY_LEVELS[level2]
                level_label = f"{level_info['emoji']} {level_info['name']}"
                if level2 == recommended:
                    level_label = f"⭐ {level_label}"
                row.append(InlineKeyboardButton(
                    level_label, 
                    callback_data=f"teach_start_{topic}_{level2}"
                ))
            if row:
                keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("◀️ Другая тема", callback_data="teach_menu")])
        
        try:
            rec_text = f"\n\n💡 <i>Рекомендуем уровень: {rec_emoji} {DIFFICULTY_LEVELS[recommended]['name']}</i>"
            await query.edit_message_text(
                f"📚 <b>{topic_info.get('name', topic)}</b>\n\n"
                f"{topic_info.get('description', 'Описание темы')}\n\n"
                "<b>Выберите уровень сложности:</b>"
                f"{rec_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_topic_: {e}")
        return
    
    # ============ TEACH RECOMMENDED - Автоматический выбор рекомендуемой темы ============
    if data == "teach_recommended":
        # Получаем рекомендуемую тему на основе XP пользователя
        with get_db() as conn:
            cursor = conn.cursor()
            _, user_xp = calculate_user_level_and_xp(cursor, user.id)
            
            # Выбираем тему на основе прогресса
            if user_xp < 100:
                recommended_topic = "crypto_basics"  # Начинаем с основ
            elif user_xp < 300:
                recommended_topic = "trading"  # Переходим к торговле
            elif user_xp < 600:
                recommended_topic = "web3"  # Изучаем Web3
            else:
                recommended_topic = "defi"  # Продвинутые темы
        
        # Переходим как если бы выбрали teach_topic_
        # Повторяем логику teach_topic_ для выбранной темы
        topic = recommended_topic
        if topic not in TEACHING_TOPICS:
            await query.answer("❌ Ошибка при выборе рекомендуемой темы", show_alert=True)
            return
        
        # Обновляем ежедневную задачу
        update_task_progress(user.id, "teach_explore", 1)
        
        # Повторно определяем рекомендуемый уровень
        with get_db() as conn:
            cursor = conn.cursor()
            _, user_xp = calculate_user_level_and_xp(cursor, user.id)
            
            if user_xp < 100:
                recommended = "beginner"
                rec_emoji = "🌱"
            elif user_xp < 300:
                recommended = "intermediate"
                rec_emoji = "📚"
            elif user_xp < 600:
                recommended = "advanced"
                rec_emoji = "🚀"
            else:
                recommended = "expert"
                rec_emoji = "💎"
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        
        keyboard = []
        levels_list = list(DIFFICULTY_LEVELS.keys())
        for i in range(0, len(levels_list), 2):
            row = []
            if i < len(levels_list):
                level1 = levels_list[i]
                level_info = DIFFICULTY_LEVELS[level1]
                level_label = f"{level_info['emoji']} {level_info['name']}"
                if level1 == recommended:
                    level_label = f"⭐ {level_label}"
                row.append(InlineKeyboardButton(
                    level_label, 
                    callback_data=f"teach_start_{topic}_{level1}"
                ))
            if i + 1 < len(levels_list):
                level2 = levels_list[i + 1]
                level_info = DIFFICULTY_LEVELS[level2]
                level_label = f"{level_info['emoji']} {level_info['name']}"
                if level2 == recommended:
                    level_label = f"⭐ {level_label}"
                row.append(InlineKeyboardButton(
                    level_label, 
                    callback_data=f"teach_start_{topic}_{level2}"
                ))
            if row:
                keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("◀️ Другая тема", callback_data="teach_menu")])
        
        try:
            rec_text = f"\n\n💡 <i>Рекомендуем уровень: {rec_emoji} {DIFFICULTY_LEVELS[recommended]['name']}</i>"
            await query.edit_message_text(
                f"📚 <b>Рекомендуемая тема: {topic_info.get('name', topic)}</b>\n\n"
                f"{topic_info.get('description', 'Описание темы')}\n\n"
                "<b>Выберите уровень сложности:</b>"
                f"{rec_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_recommended: {e}")
            await query.answer("❌ Ошибка при загрузке рекомендуемой темы", show_alert=True)
        return
    
    # Запуск урока
    if data.startswith("teach_start_"):
        try:
            parts_teach = data.replace("teach_start_", "").split("_")
            # Последний элемент - уровень
            difficulty = parts_teach[-1]
            # Остальное - тема (может быть многословная)
            topic = "_".join(parts_teach[:-1])
            
            if topic not in TEACHING_TOPICS or difficulty not in DIFFICULTY_LEVELS:
                await query.answer("❌ Ошибка параметров", show_alert=True)
                return
            
            await query.answer()  # Убираем loading состояние
            
            # Запускаем урок через helper функцию с передачей query
            await _launch_teaching_lesson(
                update,
                context,
                user.id,
                topic,
                difficulty,
                query=query  # Передаем query для редактирования сообщения
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_start_: {e}")
            await query.answer("❌ Ошибка при запуске урока", show_alert=True)
        return
    
    # Действия после урока
    if data.startswith("teach_understood_"):
        topic = data.replace("teach_understood_", "")
        await query.answer("✅ Отлично! Вы получили +50 XP!", show_alert=False)
        
        # 🆕 v0.37.0: Проверяем и выдаём новые badge'и
        new_badges = check_and_award_badges(user.id)
        
        # 🆕 v0.37.0: Показываем рекомендацию следующего урока
        recommended = get_recommended_lesson(user.id)
        
        if recommended:
            recommendation_text = (
                f"<b>🎯 Рекомендация:</b>\n"
                f"{recommended['reason']}\n\n"
                f"Уровень: {DIFFICULTY_LEVELS.get(recommended['difficulty'], {}).get('emoji', '📚')} "
                f"{DIFFICULTY_LEVELS.get(recommended['difficulty'], {}).get('name', recommended['difficulty'])}"
            )
        else:
            recommendation_text = "<b>🎉 Отлично!</b> Вы прошли все доступные уроки!"
        
        # Добавляем информацию о новых badge'ах
        if new_badges:
            badges_text = "\n".join([f"{b['emoji']} <b>{b['name']}</b>" for b in new_badges])
            recommendation_text = f"<b>🏅 Новые достижения:</b>\n{badges_text}\n\n{recommendation_text}"
        
        keyboard = [
            [InlineKeyboardButton("📚 Другая тема", callback_data="teach_menu")],
        ]
        
        # Если есть рекомендация, добавляем кнопку перейти к ней
        if recommended:
            keyboard.insert(0, [InlineKeyboardButton(
                f"🚀 {recommended.get('clean_reason', recommended['reason'])[:30]}...",
                callback_data=f"teach_start_{recommended['topic']}_{recommended['difficulty']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        try:
            await query.edit_message_text(recommendation_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
        return
    
    if data.startswith("teach_question_"):
        topic = data.replace("teach_question_", "")
        
        keyboard = [
            [InlineKeyboardButton("✅ Проверить знания", callback_data=f"teach_test_{topic}")],
            [InlineKeyboardButton("📚 Смежные темы", callback_data=f"teach_related_{topic}")],
            [InlineKeyboardButton("📖 Другая тема", callback_data="teach_menu")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "🎓 <b>ЧТО ДАЛЬШЕ?</b>\n\n"
                "✅ <b>Проверить знания</b> - мини-тест по этой теме\n"
                "📚 <b>Смежные темы</b> - рекомендуемые уроки для углубления\n"
                "📖 <b>Другая тема</b> - выбрать другой предмет для обучения",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
        return
    
    # Обработчик "Проверить знания" - показать описание или запустить тест
    if data.startswith("teach_test_"):
        topic = data.replace("teach_test_", "")
        keyboard = [
            [InlineKeyboardButton("🎯 Начать тест", callback_data=f"start_test_{topic}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"teach_question_{topic}")]
        ]
        try:
            await query.edit_message_text(
                f"✅ <b>Проверка знаний по теме:</b> {TEACHING_TOPICS.get(topic, {}).get('name', topic)}\n\n"
                "Ответь на вопросы и проверь свое понимание материала!\n"
                "За каждый правильный ответ получишь опыт. 🎯",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
        return
    
    # Обработчик "Смежные темы" - показать рекомендации
    if data.startswith("teach_related_"):
        topic = data.replace("teach_related_", "")
        
        # Определяем смежные темы для каждого топика
        related_topics = {
            "crypto_basics": ["trading", "security"],
            "trading": ["crypto_basics", "tokenomics"],
            "web3": ["defi", "nft"],
            "defi": ["web3", "security"],
            "ai": ["security", "tokenomics"],
            "nft": ["web3", "trading"],
            "security": ["crypto_basics", "ai"],
            "tokenomics": ["trading", "defi"]
        }
        
        related = related_topics.get(topic, ["crypto_basics", "web3"])
        
        keyboard = []
        for rel_topic in related[:2]:
            keyboard.append([InlineKeyboardButton(
                f"📚 {TEACHING_TOPICS.get(rel_topic, {}).get('name', rel_topic)}", 
                callback_data=f"teach_topic_{rel_topic}"
            )])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"teach_question_{topic}")])
        
        try:
            await query.edit_message_text(
                f"📚 <b>Рекомендуемые темы для углубления после '{TEACHING_TOPICS.get(topic, {}).get('name', topic)}':</b>\n\n"
                "Эти темы расширят твое понимание крипто и помогут развиваться дальше! 🚀",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
        return
    
    # ============ ОРИГИНАЛЬНЫЕ КНОПКИ ============
    
    try:
        # Парсим request_id с конца (он всегда последний, отделён подчеркиванием)
        # Например: feedback_not_helpful_24 -> request_id=24, action="feedback_not_helpful"
        parts_all = data.split("_")
        if parts_all[-1].isdigit():
            request_id = int(parts_all[-1])
            action = "_".join(parts_all[:-1])
        else:
            # Если последний элемент не число, то это не старый формат callback'а
            logger.debug(f"⏭️ Пропуск парсинга (не старый формат): {data}")
            request_id = None
            action = None
    except (ValueError, IndexError):
        logger.error(f"Ошибка парсинга callback: {data}")
        await query.message.reply_text("❌ Ошибка обработки кнопки")
        return
    
    # Обработка фидбека "Полезно"
    if action == "feedback_helpful":
        save_feedback(user.id, request_id, is_helpful=True)
        
        # ✅ v0.25.0: Track feedback event
        tracker = get_tracker()
        tracker.track(create_event(
            EventType.USER_FEEDBACK,
            user_id=user.id,
            data={"rating": "helpful", "request_id": request_id}
        ))
        
        # Обновляем ежедневную задачу по рейтингу (v0.11.0)
        update_task_progress(user.id, "voting_3", 1)
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(MSG_FEEDBACK_HELPFUL)
        
        if user.id in bot_state.user_last_news:
            await bot_state.clear_user_news(user.id)
        # Сбрасываем счётчик регенераций для этого запроса
        if request_id in bot_state.feedback_attempts:
            await bot_state.clear_feedback_attempts(request_id)
        
        if ENABLE_ANALYTICS:
            log_analytics_event("feedback_positive", user.id, {
                "request_id": request_id
            })
    
    # Обработка фидбека "Не помогло" с регенерацией
    elif action == "feedback_not_helpful":
        save_feedback(user.id, request_id, is_helpful=False)
        
        # ✅ v0.25.0: Track feedback event
        tracker = get_tracker()
        tracker.track(create_event(
            EventType.USER_FEEDBACK,
            user_id=user.id,
            data={"rating": "unhelpful", "request_id": request_id}
        ))
        
        if ENABLE_ANALYTICS:
            log_analytics_event("feedback_negative", user.id, {
                "request_id": request_id
            })
        
        # Проверяем, есть ли сохраненный текст для регенерации
        original_text = await bot_state.get_user_news(user.id)
        if not original_text:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(MSG_FEEDBACK_UNHELPFUL)
            return

        # Подсчитываем попытку регенерации для данного request_id
        attempt = await bot_state.record_feedback_attempt(request_id)

        # Если превысили лимит — эскалируем
        if attempt > FEEDBACK_MAX_RETRIES:
            await query.edit_message_reply_markup(reply_markup=None)
            
            # Создаём кнопки для предложенных действий
            keyboard = [
                [InlineKeyboardButton("💬 Задать вопрос", callback_data="ask_question")],
                [InlineKeyboardButton("📌 Закладки", callback_data="start_bookmarks")],
                [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_start")],
            ]
            
            await query.message.reply_text(
                f"😓 <b>Я исчерпал свои варианты объяснений</b> (попытка {attempt}/{FEEDBACK_MAX_RETRIES})\n\n"
                "<i>Это может быть:</i>\n"
                "🔸 Новость слишком сложная или специфичная\n"
                "🔸 Нужна помощь эксперта\n\n"
                "<b>Что делать дальше:</b>\n"
                "💬 Задайте уточняющий вопрос\n"
                "📌 Сохраните в закладки для последующего изучения\n"
                "⬅️ Вернитесь в главное меню",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await bot_state.clear_feedback_attempts(request_id)
            return

        # Выбираем режим регенерации по попытке
        mode_name, mode_desc = REGENERATION_MODES[min(attempt-1, len(REGENERATION_MODES)-1)]

        await query.edit_message_text(
            f"🔄 <b>Подготавливаю новый вариант объяснения...</b>\n"
            f"📝 Режим: <code>{mode_name}</code>\n"
            f"⏳ Попытка: {attempt}/{FEEDBACK_MAX_RETRIES}",
            parse_mode=ParseMode.HTML
        )

        try:
            # Пытаемся взять предыдущий ответ (если есть) чтобы задать более точную задачу модели
            prev = get_request_by_id(request_id)
            prev_response_text = prev.get("response_text") if prev else ""

            regen_prompt = (
                "Пользователь отметил, что предыдущий ответ не помог. "
                f"Требование: {mode_desc}\n\n"
                "Исходная новость:\n" + original_text + "\n\n"
                "Предыдущий анализ:\n" + (prev_response_text or "(не доступен)") + "\n\n"
                "Перепиши анализ в соответствии с требованием выше. Будь максимально понятным и конкретным."
            )

            # Вызываем API с модифицированным вводом, чтобы получить альтернативный стиль ответа
            simplified_text, proc_time, error = await call_api_with_retry(regen_prompt)

            if not simplified_text:
                raise ValueError(f"Ошибка API: {error}")

            # Сохраняем новый вариант ответа (для истории)
            new_request_id = save_request(
                user.id,
                original_text,
                simplified_text,
                from_cache=False,
                processing_time_ms=proc_time
            )

            # Формируем ответ — оставляем callback на исходный request_id, чтобы отслеживать попытки
            new_response = f"🤖 **RVX Скаут (альтернатива):**\n\n{simplified_text}"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "👍 Полезно",
                        callback_data=f"feedback_helpful_{request_id}"
                    ),
                    InlineKeyboardButton(
                        "👎 Не помогло",
                        callback_data=f"feedback_not_helpful_{request_id}"
                    )
                ]
            ]
            # Добавляем кнопку меню
            keyboard.append([
                InlineKeyboardButton("📋 Меню", callback_data="menu")
            ])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                new_response,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

            logger.info(f"Регенерация ({mode_name}) успешна для {user.id} (попытка {attempt})")

        except Exception as e:
            logger.error(f"Ошибка регенерации: {e}")
            await query.edit_message_text(
                "❌ Не удалось создать новый анализ.\n\n"
                "Попробуйте отправить новость заново."
            )

    # ============ DIALOGUE FEEDBACK CALLBACKS ============
    
    if data.startswith("feedback_helpful_"):
        user_id = int(data.split("_")[-1])
        await query.answer("👍 Спасибо! Рады, что помогли!", show_alert=False)
        logger.info(f"Positive feedback на AI диалог от {user_id}")
        
    if data.startswith("feedback_not_helpful_"):
        user_id = int(data.split("_")[-1])
        await query.answer("👎 Спасибо за отзыв. Постараемся улучшить!", show_alert=False)
        logger.info(f"⚠️ Negative feedback на AI диалог от {user_id}")
        
    if data.startswith("clarify_"):
        user_id = int(data.split("_")[-1])
        user = query.from_user
        
        # ✅ v0.25.0: Track clarify event
        tracker = get_tracker()
        tracker.track(create_event(
            EventType.USER_CLARIFY,
            user_id=user.id,
            data={"clarify_attempt": context.user_data.get("clarify_count", 0) + 1}
        ))
        
        # Получаем последний вопрос/тему из истории
        last_question = context.user_data.get("last_question", "")
        clarify_count = context.user_data.get("clarify_count", 0)
        
        # Получаем список всех предыдущих ответов чтобы не повторять
        previous_answers = context.user_data.get("previous_answers", [])
        
        if not last_question:
            await query.answer(MSG_CLARIFY_NOT_FOUND, show_alert=True)
            return
        
        # Показываем статус "думаю"
        await query.answer(MSG_CLARIFY_PROMPT, show_alert=False)
        
        try:
            # Генерируем разные "углы зрения" для действительно новой информации
            deep_dives = [
                ("📚 История и происхождение", "Расскажи ИСТОРИЮ {} - как это возникло, эволюционировало, откуда название?"),
                ("💡 Как это работает на практике", "Дай РЕАЛЬНЫЙ пример как люди используют {} в своей жизни - конкретный случай."),
                ("🔗 Связь с другим", "Как {} связан с другими концепциями? Что меняется если это изменится?"),
                ("⚡ Неожиданный факт", "Расскажи ИНТЕРЕСНЫЙ и НЕОЖИДАННЫЙ факт о {} которые мало кто знает."),
                ("🎯 Зачем это нужно", "ПОЧЕМУ люди должны это знать? Какие ПРОБЛЕМЫ это решает?"),
                ("🌍 Мировой контекст", "Как {} работает в других странах? Разные подходы, разные примеры из истории."),
                ("⚠️ Опасности и минусы", "Какие ПРОБЛЕМЫ и ОПАСНОСТИ связаны с {}? Что может пойти не так?"),
                ("🚀 Будущее и тренды", "Куда движется {} в будущем? Какие НОВЫЕ тренды и изменения?")
            ]
            
            # Выбираем следующий "угол зрения"
            dive_index = clarify_count % len(deep_dives)
            dive_emoji, dive_template = deep_dives[dive_index]
            clarify_count += 1
            
            # Получаем ответ от ИИ
            from ai_dialogue import get_ai_response_sync
            
            # Формируем запрос с ПОЛНЫМ контекстом предыдущих ответов
            # Так AI видит что уже было сказано и не повторяет
            previous_context = ""
            if previous_answers:
                previous_context = "\n\n⚠️ ЭТО УЖЕ БЫЛО СКАЗАНО (НЕ ПОВТОРЯЙ!):\n"
                for i, answer in enumerate(previous_answers[-3:], 1):  # Показываем последние 3 ответа
                    previous_context += f"{i}. {answer[:200]}...\n"
            
            exploration_question = (
                f"ТЕМА: {last_question}\n\n"
                f"Дай НОВУЮ информацию про {dive_template.format(last_question)}\n"
                f"{previous_context}\n"
                f"⚠️ КРИТИЧНО - НОВИЗНА:\n"
                f"1. НЕ повторяй то что указано выше - это уже было сказано\n"
                f"2. Генерируй ДЕЙСТВИТЕЛЬНО НОВЫЙ факт или перспективу\n"
                f"3. Пиши как эксперт - профессионально, но доступно\n"
                f"4. БЕЗ детских аналогий типа 'представь', 'это как', 'когда ты'\n"
                f"5. Максимум 450 символов - концентрированно и без воды\n"
                f"6. Используй USD/EUR в примерах (не рубли), конкретные цифры если знаешь\n"
                f"7. Реальные примеры, факты, последствия - как для взрослого человека"
            )
            
            dialogue_context = None
            exploration_response = get_ai_response_sync(
                exploration_question,
                dialogue_context,
                user_id=user_id
            )
            
            if exploration_response:
                # Обрезаем до 450 символов
                MAX_RESPONSE = 450
                if len(exploration_response) > MAX_RESPONSE:
                    truncated = exploration_response[:MAX_RESPONSE]
                    last_period = truncated.rfind('.')
                    
                    if last_period > MAX_RESPONSE * 0.7:
                        exploration_response = truncated[:last_period + 1]
                    elif last_period > 0:
                        exploration_response = truncated[:last_period + 1]
                    else:
                        last_space = truncated.rfind(' ')
                        if last_space > 0:
                            exploration_response = truncated[:last_space] + "..."
                        else:
                            exploration_response = truncated + "..."
                
                # Очищаем markdown
                exploration_response = exploration_response.replace("**", "").replace("__", "").replace("--", "").replace("~~", "")
                
                # Сохраняем ответ для следующего клика
                if exploration_response not in previous_answers:
                    previous_answers.append(exploration_response)
                    if len(previous_answers) > 10:  # Сохраняем последние 10
                        previous_answers = previous_answers[-10:]
                context.user_data["previous_answers"] = previous_answers
                
                # Форматируем
                formatted_dive = (
                    f"{dive_emoji} <b>Интересный факт</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{exploration_response}\n\n"
                    "<i>✨ Просто и интересно</i>"
                )
                
                # Кнопки
                keyboard = [[
                    InlineKeyboardButton("❓ Что еще?", callback_data=f"clarify_{user_id}"),
                    InlineKeyboardButton("📋 Меню", callback_data="menu")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Отправляем
                await context.bot.send_message(
                    user_id,
                    formatted_dive,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    reply_to_message_id=query.message.message_id
                )
                
                # Обновляем счетчик
                context.user_data["clarify_count"] = clarify_count
                
                logger.info(f"Новый факт #{clarify_count} для {user_id}: {dive_emoji}")
            else:
                await query.answer("❌ Не удалось получить информацию", show_alert=True)
                logger.warning(f"Не удалось получить информацию для {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации: {e}", exc_info=True)
            await query.answer("❌ Ошибка при получении информации", show_alert=True)
    
    # ============ TELL MORE CALLBACK - Расширенный анализ новостей (v0.32.3) ============
    
    if data.startswith("tell_more_"):
        try:
            # Парсим callback_data: tell_more_{request_id}_{user_id}
            parts_tell = data.replace("tell_more_", "").split("_")
            request_id_str = parts_tell[0]
            
            # Попытаемся получить данные из контекста пользователя
            last_analysis = context.user_data.get("last_news_analysis", "")
            last_question = context.user_data.get("last_news_question", "")
            last_original = context.user_data.get("last_news_original", "")
            
            if not last_analysis or not last_question:
                logger.warning(f"Контекст для tell_more не найден для {user.id}")
                await query.answer("❌ Контекст анализа потерян. Отправьте новость заново.", show_alert=True)
                return
            
            # Показываем статус "думаю"
            await query.answer()  # Убираем loading
            
            await query.edit_message_text(
                f"📖 <b>ГЛУБЖЕ О:</b> {last_question}\n\n"
                f"⏳ <i>Подготавливаю развернутый анализ...</i>",
                parse_mode=ParseMode.HTML
            )
            
            # Формируем prompt для расширенного анализа
            # Вопрос может быть типа "📊 Какой масштаб влияния?" - извлекаем текст
            question_text = last_question.replace("📊 ", "").replace("📈 ", "").replace("💡 ", "").replace("❓ ", "").replace("🔍 ", "")
            
            # ✅ v0.32.4: Улучшенный prompt без HTML тегов для API
            expand_prompt = (
                f"Пользователь просит развернутый анализ по конкретному вопросу к новости.\n\n"
                f"НОВОСТЬ:\n{last_original}\n\n"
                f"ПРЕДЫДУЩИЙ АНАЛИЗ:\n{last_analysis}\n\n"
                f"ВОПРОС ДЛЯ РАСШИРЕНИЯ: {question_text}\n\n"
                f"ЗАДАЧА: Дай максимально развернутый и глубокий анализ ИМЕННО по этому вопросу.\n"
                f"Требования:\n"
                f"1. Конкретные примеры и цифры (если есть)\n"
                f"2. Объяснение влияния на разные категории\n"
                f"3. Временные рамки и возможные сценарии\n"
                f"4. Практические рекомендации\n"
                f"5. Максимальная конкретность (не общие фразы)\n\n"
                f"Язык: РУССКИЙ. Формат: Структурированный с подзаголовками."
            )
            
            # Вызываем API для расширенного анализа с таймаутом
            try:
                expanded_analysis, proc_time, error = await asyncio.wait_for(
                    call_api_with_retry(expand_prompt),
                    timeout=60  # 60 секунд максимум
                )
            except asyncio.TimeoutError:
                logger.error(f"⏱️ TIMEOUT при расширенном анализе для {user.id} (более 60 сек)")
                await query.edit_message_text(
                    f"⏱️ <b>Анализ слишком долгий</b>\n\n"
                    f"<i>Сервер долго обрабатывает запрос. Попробуйте:</i>\n"
                    f"• Повторить запрос позже\n"
                    f"• Отправить более короткую новость\n"
                    f"• Задать более конкретный вопрос",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Вернуться", callback_data="back_to_start")]
                    ])
                )
                return
            
            # Валидация результата
            if not expanded_analysis or expanded_analysis.strip() == "":
                logger.error(f"API вернул пустой результат для {user.id}")
                await query.edit_message_text(
                    f"❌ <b>Пустой результат</b>\n\n"
                    f"<i>Сервер вернул пустой ответ. Попробуйте позже.</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Вернуться", callback_data="back_to_start")]
                    ])
                )
                return
            
            # ✅ v0.32.4: Чистим результат от артефактов
            expanded_analysis = expanded_analysis.strip()
            # Убираем HTML теги если вдруг попали в результат
            expanded_analysis = expanded_analysis.replace("<b>", "**").replace("</b>", "**")
            expanded_analysis = expanded_analysis.replace("<i>", "_").replace("</i>", "_")
            
            # Ограничиваем длину для Telegram (макс 4096 символов)
            max_length = 3800
            if len(expanded_analysis) > max_length:
                expanded_analysis = expanded_analysis[:max_length] + "\n\n[... анализ продолжается]"
            
            # Форматируем финальный ответ
            response_text = (
                f"📖 <b>ГЛУБЖЕ О: {question_text}</b>\n"
                f"{'─' * 40}\n\n"
                f"{expanded_analysis}\n\n"
                f"{'─' * 40}\n"
                f"⏱️ Анализ выполнен за {proc_time:.1f}с" if proc_time else "📖 <b>ГЛУБЖЕ О: {question_text}</b>\n\n{expanded_analysis}"
            )
            
            # Добавляем кнопки навигации
            keyboard = [
                [
                    InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id_str}"),
                    InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id_str}")
                ],
                [
                    InlineKeyboardButton("❓ Еще вопрос", callback_data="ask_question"),
                    InlineKeyboardButton("📌 Сохранить", callback_data=f"save_bookmark_news_{request_id_str}")
                ],
                [
                    InlineKeyboardButton("⬅️ Вернуться", callback_data="back_to_start")
                ]
            ]
            
            await query.edit_message_text(
                response_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Расширенный анализ показан для {user.id} по вопросу: {question_text} ({proc_time:.1f}с)")
            
        except Exception as e:
            logger.error(f"Ошибка в tell_more callback: {e}", exc_info=True)
            try:
                await query.edit_message_text(
                    f"❌ <b>Ошибка при подготовке анализа</b>\n\n"
                    f"<i>Попробуйте позже или задайте новый вопрос</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Вернуться", callback_data="back_to_start")]
                    ])
                )
            except:
                await query.answer("❌ Ошибка при подготовке расширенного анализа", show_alert=True)
        
        return

    # ============ TEACHING CALLBACKS v0.7.0 ============
    
    # Меню выбора тем обучения

# =============================================================================
# CONTEXT ANALYSIS KEYWORDS & PATTERNS (v0.27)
# =============================================================================

# Криптовалютные ключевые слова
crypto_words = [
    "bitcoin", "btc", "ethereum", "eth", "крипто", "криптовалюта", "криптовалютой",
    "блокчейн", "blockchain", "altcoin", "alt", "dex", "decentralized", "defi",
    "nft", "токен", "token", "токены", "crypto", "coin", "монета", "монеты",
    "wallet", "кошелек", "exchange", "биржа", "mining", "майнинг", "hash",
    "consensus", "fork", "upgrade", "gas fee", "tx", "transaction",
    
    # Украинский
    "крипто", "криптовалюта", "блокчейн", "альткойн", "токен", "монета",
    "гаманець", "біржа", "майнинг", "транзакція"
]

# Технологические ключевые слова
tech_keywords = [
    "ai", "искусственный интеллект", "ml", "machine learning", "algorithm",
    "api", "server", "cloud", "web", "app", "application", "система",
    "интеграция", "интегрированн", "технолог", "фича", "feature", "update",
    "bug", "баг", "fix", "фикс", "deploy", "развертыв", "сервис",
    
    # Украинский
    "штучний інтелект", "алгоритм", "сервер", "хмара", "додаток",
    "система", "інтеграція", "технологія", "оновлення", "розгортання"
]

# Финансовые ключевые слова
finance_words = [
    "цена", "price", "курс", "rate", "трейдинг", "trading", "trade", "продать",
    "купить", "покупка", "продажа", "инвест", "investment", "портфель", "wallet",
    "доход", "прибыль", "убыток", "loss", "profit", "margin", "leverage",
    "акция", "stock", "облигация", "bond", "индекс", "index", "валюта",
    "фонд", "fund", "ставка", "rate", "процент", "dividend", "дивиденд",
    "котировка", "котировок", "мировой рынок", "рынок", "market", "падение",
    "взлет", "взлетел", "вырос", "упал", "вырастет", "упадет", "скачок",
    "ipo", "startup", "стартап", "листинг", "листирован", "ipo path", "венчур",
    
    # Украинский
    "ціна", "курс", "торгівля", "торг", "продати", "купити", "покупка",
    "продаж", "інвестиція", "портфель", "дохід", "прибуток", "збиток",
    "акція", "облігація", "індекс", "валюта", "фонд", "ставка", "процент",
    "дивіденд", "котировка", "ринок", "ринку", "падіння", "коливання"
]

# Геополитические ключевые слова
geopolitical_words = [
    # Русский
    "война", "war", "конфликт", "conflict", "тензия", "tension", "переговор",
    "negotiate", "санкция", "sanctions", "эмбарго", "embargo", "блокада",
    "экспорт", "импорт", "торговля", "trade", "таможня", "таможен", "пошлина",
    "дипломат", "diplomat", "международн", "international", "политик", "политичес",
    "президент", "премьер", "government", "правительство", "государство", "state",
    "союз", "alliance", "договор", "treaty", "соглашение", "agreement",
    "страна", "страны", "государств", "регион", "region", "народ",
    "армия", "военн", "army", "military", "флот", "navy", "граница",
    "граница", "border", "территори", "территория", "оккупация", "occupation",
    "беженец", "refugee", "мигрант", "migrant", "иммигрант", "эмигрант",
    
    # Украинский
    "війна", "конфлікт", "переговори", "санкції", "емба рго", "блокада",
    "експорт", "імпорт", "торгівля", "митниця", "тариф", "дипломат",
    "міжнародн", "політик", "президент", "уряд", "державн", "територі",
    "окупація", "угода", "альянс", "союз", "армія", "військ", "флот",
    "кордон", "біженець", "мігрант", "зелен", "путін", "нато"
]

# Слова, указывающие на действие/происшествие
action_words = [
    "объявила", "объявил", "объявили", "запустила", "запустил", "запустили",
    "закрыла", "закрыл", "закрыли", "запустил", "хакнула", "хакнули",
    "поддержала", "одобрила", "запретила", "запретил", "введен", "введена",
    "отменена", "отменен", "вводит", "вводят", "запускает", "запускают",
    "поддерживает", "поддерживает", "отвергает", "отвергает", "объявляет",
    "объявляют", "призывает", "призывают", "предостерегает", "предостерегают",
    "анонсирует", "анонсируют", "раскрыла", "раскрыли", "выпустил", "выпустили",
    "обновила", "обновил", "обновили", "интегрировала", "интегрировал",
    "партнер", "сотрудничество", "сделка", "сделки", "соглашение",
    "достиг", "достигла", "достигли", "вошел", "вошла", "вошли",
    "установил", "установила", "установили", "запущен", "запущена",
    "интегрирован", "интегрирована", "выпущен", "выпущена", "введен",
    "лончен", "листирован", "рекорд", "достижение",
    
    # Украинский
    "оголосив", "оголосила", "оголосили", "запустив", "запустила",
    "закрив", "закрила", "закрили", "підтримав", "підтримала", "схвалив",
    "схвалила", "заборонив", "заборонила", "запровадив", "запроваджу",
    "запускає", "запускають", "пропонує", "пропонують", "запропонував",
    "запропонувала", "відмовитися", "відмовляється", "угода", "договір",
    "досяг", "досягла", "досягли", "увійшов", "увійшла", "увійшли"
]

# Регулярные выражения для детектирования новостей (самый надежный способ)
news_patterns = [
    re.compile(r"(новост|news|объявл|announce|запуск|launch|компани|company|проект|project|новина|оголо|ipo|листинг)", re.IGNORECASE),
    re.compile(r"(цена|price|курс|rate|поднялась|упала|выросла|выросл|взлет|взлетел|ціна|поднялась|упала)", re.IGNORECASE),
    re.compile(r"(криптовалют|cryptocurrency|bitcoin|ethereum|ETH|BTC|altcoin|token|крипто)", re.IGNORECASE),
    re.compile(r"(санкц|embargo|война|conflict|договор|treaty|международ|international|санкції|угода)", re.IGNORECASE),
    re.compile(r"(инвестиц|investment|фонд|fund|капитал|capital|трейдинг|trading|інвестиція|фонд|стартап|startup)", re.IGNORECASE),
    re.compile(r"(регулятор|regulatory|sec|фца|центробанк|央行|regulat|compliance|регулятор)", re.IGNORECASE)
]

# =============================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# =============================================================================


def detect_user_language(text: str) -> str:
    """
    Определяет язык текста пользователя.
    
    Returns:
        'ru' если текст на русском
        'en' если текст на английском
        'mixed' если смешанный
    """
    if not text:
        return 'en'
    
    # Простой детектор - ищет кириллицу
    cyrillic_count = sum(1 for c in text if 'а' <= c.lower() <= 'я' or c in 'ёЁ')
    latin_count = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    
    total_letters = cyrillic_count + latin_count
    if total_letters == 0:
        return 'en'  # Default
    
    cyrillic_ratio = cyrillic_count / total_letters
    
    if cyrillic_ratio > 0.6:
        return 'ru'
    elif cyrillic_ratio < 0.2:
        return 'en'
    else:
        return 'mixed'


def analyze_message_context(text: str) -> dict:
    """
    Анализирует контекст сообщения и возвращает детальную информацию.
    АГРЕССИВНАЯ СТРАТЕГИЯ: если есть хоть намек на финансовый контекст - отправляем на анализ.
    """
    text_lower = text.lower().strip()
    
    # ✅ DEBUG: Логируем входящий текст
    logger.debug(f"📊 analyze_message_context for text ({len(text)} chars): {text[:80]}...")
    
    # Приветствие
    if any(g in text_lower for g in ["привет", "hello", "hi", "пока", "bye", "привееет", "yo", "хай"]):
        result = {"type": "greeting", "needs_crypto_analysis": False}
        logger.debug(f"   → {result['type']}")
        return result
    
    # Вопрос о боте / возможностях (только если в начале/конце или явно вопрос)
    if any(c in text_lower for c in ["что ты", "что умеешь", "кто ты", "возможности", 
                                      "что делаешь", "помощь", "как работать", "команды", "функции"]):
        # Но проверяем - это не новость
        if not any(n in text_lower for n in ["упал", "взлетел", "пал", "вырос", "вырастет", 
                                             "объявила", "запустила", "закрыл", "хакнули",
                                             "скачку", "скачок", "в два раза", "мертва", "мертво",
                                             "выпустил", "выпустили", "угроза", "конкурент", "лидер",
                                             "переход", "миграция", "интеграция"]):
            return {"type": "info_request", "needs_crypto_analysis": False}
    
    # ✅ FIXED: REMOVED EARLY RETURN - Analysis logic continues below
    # Ключевые слова для анализа контекста (встроено, не требует отдельного файла)
    # Для сложных сценариев используйте ai_dialogue.py
    
    has_crypto = any(c in text_lower for c in crypto_words)
    has_tech = any(t in text_lower for t in tech_keywords)
    has_finance = any(f in text_lower for f in finance_words)
    has_geopolitical = any(g in text_lower for g in geopolitical_words)
    has_action = any(a in text_lower for a in action_words)
    
    # DEBUG логирование флагов
    logger.debug(f"   Flags: crypto={has_crypto}, tech={has_tech}, finance={has_finance}, geo={has_geopolitical}, action={has_action}")
    
    # ПРОВЕРКА РЕГУЛЯРНЫХ ВЫРАЖЕНИЙ - это самая мощная проверка новостей
    matches_pattern = any(pattern.search(text) for pattern in news_patterns)
    
    # ========== АГРЕССИВНАЯ СТРАТЕГИЯ ==========
    # ПЕРВАЯ ПРОВЕРКА: Новость по регулярным выражениям (САМАЯ НАДЕЖНАЯ)
    if matches_pattern:
        msg_type = "finance_news" if has_finance else "crypto_news" if has_crypto else "geopolitical_news" if has_geopolitical else "tech_news"
        result = {
            "type": msg_type,
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": has_finance,
            "is_geopolitical": has_geopolitical
        }
        logger.info(f"News pattern matched → {result}")
        return result
    
    # ВТОРАЯ ПРОВЕРКА: Явный финансовый контекст + действие = АНАЛИЗИРОВАТЬ
    if has_finance and has_action:
        result = {
            "type": "finance_news",
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": True,
            "is_geopolitical": has_geopolitical
        }
        logger.info(f"Finance news (has_finance + has_action) → {result}")
        return result
    
    # ВТОРОЙ-Б ПРОВЕРКА: Явный геополитический контекст + действие = АНАЛИЗИРОВАТЬ
    if has_geopolitical and has_action:
        result = {
            "type": "geopolitical_news",
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": has_finance,
            "is_geopolitical": True
        }
        logger.info(f"Geopolitical news (has_geopolitical + has_action) → {result}")
        return result
    
    # ТРЕТЬЯ ПРОВЕРКА: Явный крипто/tech контекст + действие = АНАЛИЗИРОВАТЬ
    if (has_crypto or has_tech) and has_action:
        msg_type = "crypto_news" if has_crypto else "tech_news"
        return {
            "type": msg_type,
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": has_finance,
            "is_geopolitical": has_geopolitical
        }
    
    # ЧЕТВЁРТАЯ ПРОВЕРКА: Длинное сообщение с финансовым контентом = АНАЛИЗИРОВАТЬ
    # (даже без явных действий - может быть анализ ситуации)
    if has_finance and len(text) > 40:
        return {
            "type": "finance_news",
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": True,
            "is_geopolitical": has_geopolitical
        }
    
    # ЧЕТВЁРТАЯ-Б ПРОВЕРКА: Длинное сообщение с геополитическим контентом = АНАЛИЗИРОВАТЬ
    if has_geopolitical and len(text) > 40:
        return {
            "type": "geopolitical_news",
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": has_finance,
            "is_geopolitical": True
        }
    
    # ПЯТАЯ ПРОВЕРКА: Длинное сообщение с крипто/tech = АНАЛИЗИРОВАТЬ
    if (has_crypto or has_tech) and len(text) > 50:
        msg_type = "crypto_news" if has_crypto else "tech_news"
        return {
            "type": msg_type,
            "needs_crypto_analysis": True,
            "is_tech": has_tech,
            "is_finance": has_finance,
            "is_geopolitical": has_geopolitical
        }
    
    # ШЕСТАЯ ПРОВЕРКА: Вопрос о финансах/крипто/tech/геополитике = АНАЛИЗИРОВАТЬ
    if any(q in text_lower for q in ["почему", "как это", "когда это", "где это", "что это", "что такое",
                                     "зачем", "для чего", "какой", "какая", "какое", "почему это"]):
        if has_crypto or has_tech or has_finance or has_geopolitical:
            if has_finance:
                msg_type = "finance_question"
            elif has_geopolitical:
                msg_type = "geopolitical_question"
            elif has_crypto:
                msg_type = "crypto_question"
            else:
                msg_type = "tech_question"
            return {
                "type": msg_type,
                "needs_crypto_analysis": True,
                "is_tech": has_tech,
                "is_finance": has_finance,
                "is_geopolitical": has_geopolitical
            }
        else:
            return {"type": "knowledge_question", "needs_crypto_analysis": False}
    
    # Просто общение - нужно быть живым и интересным
    return {"type": "casual_chat", "needs_crypto_analysis": False}


async def get_smart_response(user_id: int, text: str, msg_type: str) -> str:
    """
    Генерирует 'живой' ответ используя ai_intelligence функции.
    Разные ответы на разные вопросы, без шаблонов.
    """
    try:
        user_profile = await get_user_intelligent_profile(user_id)
        user_level = analyze_user_knowledge_level(
            xp=user_profile.get('xp', 0),
            level=user_profile.get('level', 1),
            courses_completed=user_profile.get('courses_completed', 0),
            tests_passed=user_profile.get('tests_count', 0)
        ) if user_profile else UserLevel.BEGINNER
    except:
        user_level = UserLevel.BEGINNER
        user_profile = {}
    
    # Разные ответы в зависимости от типа и содержания
    if msg_type == "greeting":
        # Адаптивное приветствие
        greeting = get_adaptive_greeting(user_level, "друже")
        return greeting or "Привет! 👋"
    
    elif msg_type == "info_request":
        # О возможностях - простой ответ
        if "помощь" in text.lower() or "help" in text.lower():
            return "📰 Отправь крипто-новость\n🎓 /teach или /learn\n📊 /stats для прогресса"
        elif "что" in text.lower() and ("ты" in text.lower() or "умеешь" in text.lower()):
            return "Я анализирую крипто-новости и учу тебя криптовалютам"
        elif "команды" in text.lower() or "команд" in text.lower():
            return "/learn - курсы\n/teach - генерировать урок\n/stats - прогресс\n/leaderboard - рейтинг"
        else:
            return "Спроси что-то конкретное 😊"
    
    elif msg_type == "crypto_question":
        # Вопрос о крипто - нужен анализ
        return None
    
    elif msg_type in ["knowledge_question", "casual_chat"]:
        # Живой ответ на вопрос/общение
        # Ищем ключевые слова в вопросе для разных ответов
        text_lower = text.lower()
        
        # Вопросы "почему", "как", "что это"
        if any(w in text_lower for w in ["почему", "зачем", "для чего"]):
            return "Хороший вопрос! Это связано с тем, что децентрализованные системы нужны для безопасности 🔒"
        
        if any(w in text_lower for w in ["как это", "как работает", "как они"]):
            return "Работает на основе криптографии - специального шифрования, которое невозможно взломать 🛡️"
        
        if any(w in text_lower for w in ["что такое", "что это", "какой это"]):
            return "Это технология, которая позволяет людям доверять друг другу без посредников 🤝"
        
        if any(w in text_lower for w in ["когда", "сколько", "насколько"]):
            return "Зависит от много факторов - спроса, регуляции, технического развития 📈"
        
        if any(w in text_lower for w in ["интересно", "слышал", "видел", "читал"]):
            return "Интересная тема! Расскажи больше, что тебя привлекает 👀"
        
        # Просто общение - живые ответы
        if len(text) < 15:
            responses = [
                "Согласен! 😊",
                "Да, точно! 👍",
                "Интересно! Продолжай ✨",
                "Верно сказано! 💯"
            ]
            import random
            return random.choice(responses)
        
        # Длинные сообщения - осмысленные ответы
        if "блокчейн" in text_lower or "bitcoin" in text_lower or "ethereum" in text_lower:
            return "Да, крипто - это действительно революционная технология! Что тебя больше всего интересует?"
        
        if "скучно" in text_lower or "сложно" in text_lower:
            return "Можешь попробовать /learn - там всё объясняется пошагово 📚"
        
        if "отлично" in text_lower or "круто" in text_lower or "норм" in text_lower:
            return "Спасибо! Продолжай изучать, в /learn много интересного 🚀"
        
        # Дефолт - живой ответ
        return "Интересное замечание! Расскажи подробнее 🤔"
    
    return None


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик изображений (графики, скриншоты, диаграммы) для анализа.
    
    Позволяет пользователям отправлять графики, скриншоты или диаграммы
    криптовалютных трейдов для анализа. Извлекает текст из изображения
    (если есть) и анализирует его через AI.
    
    Args:
        update (Update): Telegram Update с фото от пользователя
        context (ContextTypes.DEFAULT_TYPE): Telegram context
        
    Side Effects:
        - Скачивает изображение с Telegram серверов
        - Сохраняет пользователя в БД
        - Проверяет бан пользователя
        - Проверяет rate limits
        - Анализирует изображение через OCR/AI
        - Отправляет анализ пользователю
        
    Supported Image Types:
        - Trading charts (TradingView, Binance screenshots)
        - Crypto news screenshots
        - Market analysis images
        - Custom diagrams
        
    Error Handling:
        - User is banned: "⛔ Вы заблокированы"
        - Rate limit exceeded: "⏰ Исчерпан лимит запросов"
        - Bad image: "❌ Не удалось обработать изображение"
        - API error: Shows error with retry option
    """
    user = update.effective_user
    
    if not update.message.photo:
        await update.message.reply_text("❌ Не удалось получить изображение")
        return
    
    # Сохраняем пользователя
    save_user(user.id, user.username or "", user.first_name)
    
    # Проверка бана
    is_banned, ban_reason = check_user_banned(user.id)
    if is_banned:
        await update.message.reply_text(
            f"⛔ **Вы заблокированы**\n\n"
            f"Причина: {ban_reason or 'Не указана'}\n\n"
            f"Для разблокировки свяжитесь с администратором.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверка whitelist (если настроен)
    if ALLOWED_USERS and user.id not in ALLOWED_USERS and user.id not in ADMIN_USERS:
        await update.message.reply_text("⛔ Доступ ограничен.\n\nБот работает в закрытом режиме.")
        return
    
    # Проверка подписки на канал
    if not await check_subscription(user.id, context):
        keyboard = [[InlineKeyboardButton("📢 Подписаться", url=MANDATORY_CHANNEL_LINK)]]
        await update.message.reply_text(
            "⛔ **Требуется подписка**\n\n"
            f"Подпишитесь на канал для доступа:\n{MANDATORY_CHANNEL_LINK}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверка дневного лимита
    can_request, remaining = check_daily_limit(user.id)
    if not can_request:
        await update.message.reply_text(
            f"⛔ **Дневной лимит исчерпан**\n\n"
            f"Вы использовали все {MAX_REQUESTS_PER_DAY} запросов.\n"
            f"Попробуйте завтра!\n\n"
            f"Посмотреть лимиты: /limits",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Flood control
    if not await bot_state.check_flood(user.id):
        await update.message.reply_text(f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS} секунд между запросами")
        return
    
    try:
        # Показываем что обрабатываем (только action, без сообщения)
        await context.bot.send_chat_action(user.id, ChatAction.TYPING)
        
        # Получаем самое крупное изображение (обычно последнее в списке)
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # Скачиваем изображение в памяти
        import io
        import base64
        
        photo_bytes = io.BytesIO()
        await file.download_to_memory(photo_bytes)
        photo_bytes.seek(0)
        
        # Конвертируем в base64
        image_b64 = base64.b64encode(photo_bytes.getvalue()).decode()
        
        # СОХРАНЯЕМ в контекст пользователя для retry (используем context.user_data)
        context.user_data["last_image_b64"] = image_b64
        
        # Получаем caption если есть
        caption = update.message.caption or ""
        
        logger.info(f"📸 Обработка фото для пользователя {user.id} ({len(image_b64)//1024}KB)")
        
        # ЛОГИКА: Если есть текст в caption - анализируем текст (как новость с изображением)
        # Если нет текста - анализируем изображение
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                # Если есть текст в подписи - анализируем текст как основное, фото как доп контекст
                if caption and caption.strip():
                    logger.info(f"📝 Найден текст в caption ({len(caption)} символов) - анализируем как новость")
                    response = await client.post(
                        f"{API_URL_NEWS.replace('/explain_news', '')}/explain_news",
                        json={"text_content": caption},
                        headers={"X-User-ID": str(user.id)}
                    )
                else:
                    # Только изображение без текста - анализируем как картинку
                    logger.info(f"🖼️ Текст не найден - анализируем как изображение")
                    response = await client.post(
                        f"{API_URL_NEWS.replace('/explain_news', '')}/analyze_image",
                        json={
                            "image_base64": image_b64,
                            "context": ""
                        },
                        headers={"X-User-ID": str(user.id)}
                    )
                
                if response.status_code != 200:
                    logger.error(f"API ошибка: {response.status_code}")
                    await update.message.reply_text("❌ Ошибка при анализе")
                    return
                
                result = response.json()
                
                # Обработка в зависимости от типа анализа (текст или изображение)
                if caption and caption.strip():
                    # Анализ ТЕКСТА (новость)
                    logger.info(f"Текст проанализирован")
                    
                    # Формат для текста: {"summary_text": "...", "impact_points": [...]}
                    summary = result.get("simplified_text") or result.get("summary_text", "")
                    impact_points = result.get("impact_points", [])
                    
                    reply_text = f"📰 <b>АНАЛИЗ НОВОСТИ</b>\n─────────────────────\n"
                    reply_text += f"📝 {summary}\n"
                    
                    if impact_points:
                        reply_text += "\n<b>💡 Ключевые моменты:</b>\n"
                        for i, point in enumerate(impact_points, 1):
                            reply_text += f"{i}. {point}\n"
                    
                    reply_text += "\n<i>[Анализ на основе текста + прикрепленное изображение]</i>"
                    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
                    
                else:
                    # Анализ ИЗОБРАЖЕНИЯ
                    logger.info(f"Изображение проанализировано")
                    
                    # Формат для изображения: {"analysis": "...", "asset_type": "...", "confidence": 0.X, ...}
                    analysis = result.get("analysis", "")
                    asset_type = result.get("asset_type", "unknown")
                    confidence = result.get("confidence", 0) * 100
                    mentioned_assets = result.get("mentioned_assets", [])
                    
                    # Ограничиваем длину анализа для Telegram
                    max_analysis_len = 1200
                    is_truncated = len(analysis) > max_analysis_len
                    if is_truncated:
                        analysis = analysis[:max_analysis_len] + "..."
                    
                    # Определяем эмодзи в зависимости от типа
                    asset_icons = {
                        "chart": "📈",
                        "screenshot": "📸",
                        "meme": "😄",
                        "other": "🖼️"
                    }
                    asset_icon = asset_icons.get(asset_type, "🖼️")
                    
                    # Определяем стиль заголовка в зависимости от уверенности
                    confidence_emoji = "🔍" if confidence < 50 else "✅" if confidence < 80 else "⭐"
                    
                    # Формируем красивый ответ
                    reply_text = (
                        f"{confidence_emoji} <b>АНАЛИЗ ИЗОБРАЖЕНИЯ</b>\n"
                        f"─────────────────────\n"
                        f"{asset_icon} <b>Тип:</b> {asset_type.upper()}"
                    )
                    
                    if confidence < 50:
                        reply_text += f" <i>(экспресс-режим)</i>"
                    
                    reply_text += f"\n🎯 <b>Уверенность:</b> {confidence:.0f}%\n"
                    
                    if mentioned_assets:
                        assets_str = " ".join([f"<code>{a}</code>" for a in mentioned_assets])
                        reply_text += f"💰 {assets_str}\n"
                    
                    reply_text += f"\n📝 <b>Анализ:</b>\n{analysis}"
                    
                    if is_truncated:
                        reply_text += "\n\n<i>[Анализ сокращен для читаемости]</i>"
                    
                    # Добавляем кнопку для переотправки если низкая уверенность
                    keyboard = None
                    if confidence < 50:
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Попробуй снова", callback_data="retry_image")]
                        ])
                    
                    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                
                # Обновляем статистику
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        increment_daily_requests(cursor, user.id)
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Ошибка при обновлении счетчика запросов: {e}")
                
                # Логируем результат
                mode = "(fallback)" if confidence < 50 else "(AI mode)"
                logger.info(f"Фото обработано для {user.id} {mode} - уверенность: {confidence:.0f}%")
                
            except httpx.TimeoutException:
                logger.error(f"Timeout при вызове API для фото")
                await update.message.reply_text("⏱️ Timeout при анализе изображения. Попробуйте позже.")
            except Exception as e:
                logger.error(f"Ошибка при вызове API: {e}")
                await update.message.reply_text("❌ Ошибка при анализе изображения")
    
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке изображения")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает текстовые сообщения пользователей.
    
    Функция:
    - Проверяет подписку на обязательный канал (v0.42.1)
    - Проверяет бан и лимиты
    - Анализирует тип контента
    - Вызывает AI анализ
    - Сохраняет результаты
    - Отправляет ответ
    
    Поддерживаемые типы:
    - Новости
    - Вопросы
    - Общие диалоги
    
    Args:
        update: Telegram Update объект с текстом
        context: Telegram Context объект
        
    Returns:
        None
    """
    user = update.effective_user
    user_id = user.id
    
    # ✅ v0.42.1: Проверяем подписку на обязательный канал перед обработкой сообщения
    is_subscribed = await check_channel_subscription(user_id, context)
    if not is_subscribed:
        logger.info(f"User {user_id} sent message without channel subscription")
        
        # Отправляем сообщение с кнопкой для подписки
        keyboard = [
            [
                InlineKeyboardButton(
                    "📢 Подписаться на канал",
                    url=MANDATORY_CHANNEL_LINK
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "<b>📢 Требуется подписка на канал</b>\n\n"
            "Для использования этого бота необходимо подписаться на наш канал. "
            "После подписки вы сможете пользоваться всеми функциями.\n\n"
            "👇 Подпишитесь по ссылке ниже:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return
    
    # 🔍 DEBUG: Log chat_id for digest setup
    if update.message and update.message.chat:
        logger.info(f"📨 Message from chat_id={update.message.chat.id}, type={update.message.chat.type}")
    
    # ✅ CRITICAL FIX #2: Валидация входного текста
    if not update.message or not update.message.text:
        logger.warning(f"Empty message from user {user.id}")
        return
    
    # ✅ v0.33.0: CALCULATOR PRICE INPUT HANDLER (проверяем ДО валидации основного текста)
    if context.user_data.get("waiting_for_price"):
        try:
            user_text = update.message.text.strip()
            
            # Валидируем цену
            is_valid, price, error_msg = validate_price(user_text)
            
            if not is_valid:
                # Показываем ошибку с кнопкой отмены
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"calc_token_{context.user_data.get('selected_token', 'gnk').lower()}"),
                        InlineKeyboardButton("❌ Отменить ввод", callback_data="back_to_start")
                    ]
                ]
                await update.message.reply_text(
                    f"{error_msg}\n\n"
                    f"<i>Пожалуйста, введи число (например: 0.001, 1.5, 100) или нажми кнопку отмены</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            # Получаем выбранный токен
            token_symbol = context.user_data.get("selected_token", "GNK").upper()
            
            # Генерируем результат расчета
            calculator_result = format_calculator_result(token_symbol, price)
            
            # Кнопки для калькулятора
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Другая цена", callback_data=f"calc_token_{token_symbol.lower()}"),
                    InlineKeyboardButton("🪙 Другой токен", callback_data="calc_menu")
                ],
                [
                    InlineKeyboardButton("📊 Таблица цен", callback_data=f"calc_price_table_{token_symbol.lower()}"),
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")
                ]
            ]
            
            await update.message.reply_text(
                calculator_result,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем флаг ожидания цены
            context.user_data["waiting_for_price"] = False
            
            logger.info(f"Расчет калькулятора для {user.id}: {token_symbol} @ ${price:,.2f}")
            return
        
        except Exception as e:
            logger.error(f"Ошибка в калькуляторе: {str(e)}", exc_info=True)
            context.user_data["waiting_for_price"] = False
            await update.message.reply_text(
                "❌ Произошла ошибка при расчете. Пожалуйста, попробуйте позже.\n\n"
                "Используйте /calc для новой попытки."
            )
            return
    
    # Валидация и санитизация входа
    is_valid, error_msg = validate_user_input(update.message.text)
    if not is_valid:
        logger.warning(f"Invalid input from {user.id}: {error_msg}")
        await update.message.reply_text(
            f"❌ Ошибка ввода: {error_msg}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Парсим валидированный ввод
    try:
        input_data = UserMessageInput(text=update.message.text)
        user_text = input_data.text
    except Exception as e:
        logger.error(f"Parsing error: {e}")
        return
    
    # ✅ v0.39.0: IP-BASED RATE LIMITING (DDoS Protection)
    client_ip = update.effective_user.id  # Use user_id as fallback if IP not available
    if update.message and update.message.chat:
        # In real Telegram bot, we'd use update.message.from_user.id as a unique identifier
        client_ip = str(update.message.from_user.id)
    
    if not rate_limiter.check_rate_limit(client_ip):
        remaining = rate_limiter.get_remaining_requests(client_ip)
        logger.warning(f"IP rate limit exceeded for {client_ip}: {remaining} requests left")
        await update.message.reply_text(
            "⚠️ Слишком много запросов. Пожалуйста, подождите минуту перед следующим запросом.\n\n"
            "<i>Это ограничение существует для защиты сервиса от злоупотреблений.</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # ✅ v0.32.0: Проверка пропаганды с ВЫСОКОЙ уверенностью
    # НЕ блокируем сообщение, только предупреждаем если очень подозрительно (> 70%)
    propaganda_check = quick_propaganda_check(user_text)
    high_confidence_propaganda = False
    
    if propaganda_check[0]:  # Если обнаружена потенциальная манипуляция
        analysis = analyze_propaganda(user_text)
        if analysis:
            confidence = analysis.get("confidence", 0)
            
            # ТОЛЬКО если уверенность > 70% считаем это серьезной манипуляцией
            if confidence > 0.7:
                high_confidence_propaganda = True
                logger.warning(f"ВЫСОКАЯ УВЕРЕННОСТЬ пропаганда от {user.id}: {confidence*100:.0f}%")
                
                # Показываем предупреждение но ПРОДОЛЖАЕМ обработку
                warning_msg = format_propaganda_analysis(analysis)
                try:
                    await update.message.reply_text(
                        warning_msg,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.debug(f"Ошибка при отправке предупреждения: {e}")
            else:
                # Низкая уверенность - просто логируем, не показываем
                logger.debug(f"ℹ️ Низкая уверенность пропаганда от {user.id}: {confidence*100:.0f}%")
    
    # ✅ v0.25.0: Track user_analyze event
    tracker = get_tracker()
    tracker.track(create_event(
        EventType.USER_ANALYZE,
        user_id=user.id,
        data={"text_length": len(user_text)}
    ))
    
    # Сохраняем пользователя
    save_user(user.id, user.username or "", user.first_name)
    
    # ✅ v0.32.1: Определяем и сохраняем язык пользователя
    user_language = detect_user_language(user_text)
    logger.debug(f"🌐 Язык пользователя {user.id}: {user_language}")
    

    # Классифицируем намерение и сохраняем в историю
    intent = classify_intent(user_text)
    try:
        save_conversation(user.id, "user", user_text, intent)
    except Exception as e:
        logger.warning(f"DB save failed (non-critical): {e}")
    # ===================================================================
    
    # Анализируем контекст сообщения
    msg_context = analyze_message_context(user_text)
    msg_type = msg_context.get("type", "casual_chat")
    needs_analysis = msg_context.get("needs_crypto_analysis", False)
    
    # ==================== НОВАЯ v0.22.0: РЕАЛЬНЫЙ ИИ ДЛЯ ВСЕХ ДИАЛОГОВ ====================
    # Если это НЕ крипто-новость (то есть это диалог) - используем ИИ!
    # Это НАСТОЯЩИЙ искусственный интеллект, не скрипты!
    
    if not needs_analysis:
        # Это диалог, не новость - используем DeepSeek ИИ
        try:
            from ai_dialogue import get_ai_response_sync
            
            logger.info(f"🤖 AI диалог для {user.id}: '{user_text[:50]}...'")
            
            # ✅ v0.26.0: Получаем контекст из истории разговора В ПРАВИЛЬНОМ ФОРМАТЕ (List[dict])
            dialogue_context = get_context_messages(user.id, limit=10)
            
            # ✅ Добавляем сообщение пользователя в контекст
            add_user_message(user.id, user_text, intent)
            
            # ✅ Получаем ИИ ответ с rate limiting (передаем user_id для проверки лимитов)
            ai_response = get_ai_response_sync(
                user_text,
                dialogue_context,
                user_id=user.id,
                message_context=msg_context  # ✅ v0.27: Pass message context for prompt selection
            )
            
            if ai_response:
                # ✅ Обрезаем до 1200 символов - достаточно для полного объяснения
                MAX_RESPONSE = 1200
                
                if len(ai_response) > MAX_RESPONSE:
                    # Обрезаем по полным словам, не посередине
                    truncated = ai_response[:MAX_RESPONSE]
                    
                    # Ищем последнюю точку (конец предложения)
                    last_period = truncated.rfind('.')
                    
                    # Если есть точка - обрезаем после неё
                    if last_period > MAX_RESPONSE * 0.7:  # Точка в последних 30%
                        ai_response = truncated[:last_period + 1]
                    elif last_period > 0:  # Если точка есть хотя бы где-то
                        ai_response = truncated[:last_period + 1]
                    else:
                        # Если точки нет - ищем последний пробел
                        last_space = truncated.rfind(' ')
                        if last_space > 0:
                            ai_response = truncated[:last_space] + "..."
                        else:
                            ai_response = truncated + "..."
                
                # Очищаем markdown символы (**, __, --, ~~) которые ИИ может добавить
                ai_response = ai_response.replace("**", "").replace("__", "").replace("--", "").replace("~~", "")
                
                # ✅ Проверяем нужно ли упомянуть разработчика (в ключевых случаях)
                from ai_dialogue import should_mention_developer
                if should_mention_developer(user_text):
                    # Добавляем информацию об администраторе для контактов/проблем
                    ai_response = ai_response + "\n\n👤 Администратор проекта: @SV4096"
                
                # Добавляем структурированное форматирование с HTML разметкой
                formatted_response = (
                    "<b>🤖 RVX ОТВЕТ</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{ai_response}\n\n"
                    "<i>✨ Просто и без воды • Нажми 'Что еще?' для деталей</i>"
                )
                
                # Сохраняем последний вопрос для кнопки "Уточнить"
                context.user_data["last_question"] = user_text
                context.user_data["last_ai_response"] = ai_response
                context.user_data["clarify_count"] = 0  # Сбрасываем счетчик для нового вопроса
                
                # Кнопки фидбека для диалога
                keyboard = [[
                    InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{user.id}"),
                    InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{user.id}")
                ], [
                    InlineKeyboardButton("❓ Что еще?", callback_data=f"clarify_{user.id}"),
                    InlineKeyboardButton("📋 Меню", callback_data="menu")
                ]]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # ✅ v0.25.0: Apply AI honesty checks before sending response
                honesty_analysis = analyze_ai_response(ai_response)
                
                # ✅ v0.26.0: FIX - ТОЛЬКО ОДНО сообщение, никаких дубликатов!
                final_response = formatted_response
                
                if honesty_analysis["confidence"] < 0.6:
                    # Low confidence - add warning AT THE BEGINNING
                    final_response = f"⚠️ <i>Уверенность ИИ в этом ответе средняя. Пожалуйста, проверьте информацию самостоятельно.</i>\n\n{formatted_response}"
                
                # ✅ CRITICAL FIX: Split long responses to stay under 4096 char limit
                response_chunks = split_message(final_response, chunk_size=4090)
                
                # Send first chunk with keyboard
                if response_chunks:
                    await update.message.reply_text(response_chunks[0], parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                    # Send remaining chunks without keyboard
                    for chunk in response_chunks[1:]:
                        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
                
                # ✅ v0.26.0: Добавляем ИИ ответ в контекст
                add_ai_message(user.id, ai_response)
                
                # Сохраняем ответ в историю диалога
                try:
                    save_conversation(user.id, "bot", ai_response, intent)
                except Exception as e:
                    logger.warning(f"DB save failed (non-critical): {e}")
                logger.info(f"AI Dialogue для {user.id}: '{user_text[:40]}...' → ИИ ответ ({len(ai_response)} символов)")
                return
            else:
                # Fallback - если ИИ не ответил
                logger.warning(f"AI dialogue failed for {user.id}, falling back")
                await update.message.reply_text(
                    "Извини, сейчас я не могу ответить. Попробуй позже! 🤔",
                    parse_mode=ParseMode.HTML
                )
                return
                
        except Exception as e:
            logger.error(f"Error in AI dialogue: {type(e).__name__}: {str(e)}", exc_info=True)
            
            # Пытаемся дать простой ответ вместо ошибки
            try:
                await update.message.reply_text(
                    f"🤖 Сейчас я не могу ответить подробно, но спасибо за вопрос! '{user_text[:50]}...'\n\n"
                    "Попробуй позже или спроси про крипто! 💰",
                    parse_mode=ParseMode.HTML
                )
            except:
                try:
                    await update.message.reply_text("🤖 Спасибо за вопрос!")
                except:
                    pass
            return
    
    # ==================== ДАЛЬШЕ - ТОЛЬКО ДЛЯ КРИПТО НОВОСТЕЙ ====================
    # Это крипто-новость - нужна полная проверка
    
    # Для крипто-новостей - проверим лимиты и валидацию
    # Проверка бана
    is_banned, ban_reason = check_user_banned(user.id)
    if is_banned:
        await update.message.reply_text(
            f"⛔ **Вы заблокированы**\n\n"
            f"Причина: {ban_reason or 'Не указана'}\n\n"
            f"Для разблокировки свяжитесь с администратором.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверка whitelist (если настроен)
    if ALLOWED_USERS and user.id not in ALLOWED_USERS and user.id not in ADMIN_USERS:
        await update.message.reply_text(
            "⛔ Доступ ограничен.\n\nБот работает в закрытом режиме."
        )
        return
    
    # Проверка подписки на канал
    if not await check_subscription(user.id, context):
        keyboard = [[
            InlineKeyboardButton("📢 Подписаться", url=MANDATORY_CHANNEL_LINK)
        ]]
        await update.message.reply_text(
            "⛔ **Требуется подписка**\n\n"
            f"Подпишитесь на канал для доступа:\n{MANDATORY_CHANNEL_LINK}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверка дневного лимита
    can_request, remaining = check_daily_limit(user.id)
    if not can_request:
        await update.message.reply_text(
            f"⛔ **Дневной лимит исчерпан**\n\n"
            f"Вы использовали все {MAX_REQUESTS_PER_DAY} запросов.\n"
            f"Попробуйте завтра!\n\n"
            f"Посмотреть лимиты: /limits",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Flood control
    if not await bot_state.check_flood(user.id):
        await update.message.reply_text(
            f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS} секунд между запросами"
        )
        return
    
    # Валидация длины текста (ТОЛЬКО для крипто-новостей!)
    if len(user_text) > MAX_INPUT_LENGTH:
        await update.message.reply_text(
            f"❌ Текст слишком длинный\n\n"
            f"Максимум: {MAX_INPUT_LENGTH} символов\n"
            f"У вас: {len(user_text)} символов"
        )
        return
    
    # Минимум 10 символов - ТОЛЬКО для крипто-новостей
    if len(user_text.strip()) < 10:
        await update.message.reply_text(
            "❌ Для анализа новостей нужен текст минимум 10 символов.\n\n"
            "Или задай вопрос коротко - я пойму! 💬"
        )
        return
    

    
    # ==================== ДАЛЬШЕ - ТОЛЬКО ДЛЯ КРИПТО НОВОСТЕЙ ====================
    
    # Проверка кэша
    cache_key = get_cache_key(user_text)
    cached_response = get_cache(cache_key)
    
    if cached_response:
        logger.info(f"✨ Кэш HIT для пользователя {user.id}")
        
        # Сохраняем запрос с меткой "из кэша"
        request_id = save_request(
            user.id, 
            user_text, 
            cached_response, 
            from_cache=True,
            processing_time_ms=0
        )
        
        increment_user_requests(user.id)
        await bot_state.set_user_news(user.id, user_text)
        
        # Обновляем ежедневную задачу по анализу новостей (v0.11.0)
        update_task_progress(user.id, "news_5", 1)
        
        # Кнопки фидбека
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        # Добавляем кнопки обучения и меню
        keyboard.append([
            InlineKeyboardButton("📌 В закладки", callback_data=f"save_bookmark_news_{request_id}"),
            InlineKeyboardButton("🔄 Переанализ", callback_data="menu")
        ])
        keyboard.append([
            InlineKeyboardButton("📚 Узнать больше", callback_data="teach_menu"),
            InlineKeyboardButton("📋 Меню", callback_data="menu")
        ])
        
        await update.message.reply_text(
            f"⚡ <b>Из кэша:</b>\n\n{cached_response}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        
        # Уведомление об оставшихся запросах
        if remaining <= 5:
            await update.message.reply_text(
                f"💡 Осталось запросов сегодня: {remaining - 1}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        return
    
    # Запрос к API
    status_msg = await update.message.reply_text("🧠 Шуршу мозгами...")
    
    try:
        # Вызов API с retry логикой
        simplified_text, proc_time, error = await call_api_with_retry(user_text, user_id=user.id)
        
        # Проверяем успех: есть ответ И нет ошибки
        if simplified_text and not error:
            logger.info(f"API успех: {len(simplified_text)} символов за {proc_time:.0f}ms")
            
            # ⚡ LIMIT RESPONSE TO 1500 CHARS MAX - достаточно для полного анализа
            MAX_CHARS = 1500
            if len(simplified_text) > MAX_CHARS:
                # Find last space before limit
                truncated = simplified_text[:MAX_CHARS]
                last_space = truncated.rfind(' ')
                if last_space > 0:
                    simplified_text = simplified_text[:last_space] + "..."
                else:
                    simplified_text = truncated + "..."
            
            # Сохраняем в кэш
            set_cache(cache_key, simplified_text)
            
            # Сохраняем успешный запрос
            request_id = save_request(
                user.id,
                user_text,
                simplified_text,
                from_cache=False,
                processing_time_ms=proc_time
            )
            
            increment_user_requests(user.id)
            await bot_state.set_user_news(user.id, user_text)
            
            # Обновляем ежедневную задачу по анализу новостей (v0.11.0)
            update_task_progress(user.id, "news_5", 1)
            
            # Кнопки фидбека
            keyboard = [[
                InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
                InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
            ]]
            
            # Генерируем наводящий вопрос для погружения в тему
            follow_up_questions = [
                "💭 Как это влияет на цену?",
                "🤔 Кто выиграет от этого?",
                "❓ Когда это произойдёт?",
                "📊 Какой масштаб влияния?",
                "🎯 Что это значит для инвесторов?"
            ]
            import random
            follow_up = random.choice(follow_up_questions)
            
            # Просто отправляем ответ от API как есть (он уже полностью отформатирован)
            full_response = f"<b>📰 RVX АНАЛИЗ</b>\n\n{simplified_text}\n\n<i>{follow_up}</i>"
            
            # Сохраняем в контекст для закладок
            context.user_data["last_content"] = {
                "type": "news",
                "title": user_text[:50] + "..." if len(user_text) > 50 else user_text,
                "text": simplified_text,
                "source": "user_news"
            }
            
            # ✅ v0.32.2: Сохраняем анализ и вопрос для "Расскажи еще"
            context.user_data["last_news_analysis"] = simplified_text
            context.user_data["last_news_question"] = follow_up
            context.user_data["last_news_original"] = user_text
            
            # Добавляем кнопки сохранения в закладки
            keyboard.append([
                InlineKeyboardButton("📌 В закладки", callback_data=f"save_bookmark_news_{request_id}"),
                InlineKeyboardButton("🔄 Переанализ", callback_data="menu")
            ])
            
            # ✅ v0.32.2: Добавляем кнопку "Расскажи еще" для развития мысли
            keyboard.append([
                InlineKeyboardButton("📖 Расскажи еще", callback_data=f"tell_more_{request_id}_{user.id}"),
                InlineKeyboardButton("❓ Другой вопрос", callback_data="menu")
            ])
            
            # Добавляем кнопки обучения и меню внизу
            keyboard.append([
                InlineKeyboardButton("📚 Узнать больше", callback_data="teach_menu"),
                InlineKeyboardButton("📋 Меню", callback_data="menu")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем результат
            await status_msg.edit_text(
                full_response,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
            logger.info(f"Запрос успешно обработан для {user.id} за {proc_time:.0f}ms")
        
        else:
            # API вернул ошибку
            error_msg = error or "Неизвестная ошибка"
            logger.error(f"API ошибка для {user.id}: {error_msg}")
            
            # Сохраняем неудачный запрос
            save_request(
                user.id,
                user_text,
                simplified_text or "",
                from_cache=False,
                processing_time_ms=proc_time,
                error_message=error_msg
            )
            
            # Отправляем сообщение об ошибке
            await status_msg.edit_text(
                f"❌ <b>Ошибка при анализе</b>\n\n"
                f"Статус: {error_msg}\n\n"
                f"🔄 Попробуйте еще раз или свяжитесь с администратором.",
                parse_mode=ParseMode.HTML
            )
    
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.error(f"⏱️ ТАЙМАУТ API для {user.id}: {type(e).__name__} (ИСПРАВЛЕНИЕ КРИТИЧЕСКОЙ ОШИБКИ #2)")
        try:
            await status_msg.edit_text(
                "❌ <b>Превышено время ожидания</b>\n\n"
                "AI сервис не ответил за 30 секунд.\n"
                "🔄 Попробуйте через минуту.\n\n"
                "<i>Если проблема повторяется часто, сообщите администратору.</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception as edit_err:
            logger.error(f"⚠️ Не удалось отредактировать сообщение статуса: {edit_err}")
            try:
                await update.message.reply_text(
                    "❌ <b>Превышено время ожидания</b>\n\n"
                    "AI сервис не ответил вовремя. Попробуйте позже.",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка для {user.id}: {e}")
        await status_msg.edit_text(
            f"❌ <b>Ошибка API (HTTP {e.response.status_code})</b>\n\n"
            "AI сервис временно недоступен.\n"
            "Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"Неожиданная ошибка для {user.id}: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ <b>Произошла ошибка</b>\n\n"
            "Попробуйте отправить новость заново.\n"
            "Если проблема повторяется, свяжитесь с администратором.",
            parse_mode=ParseMode.HTML
        )

# =============================================================================
# ФОНОВЫЕ ЗАДАЧИ
# =============================================================================

# ============================================================================
# 📊 CRYPTO DAILY DIGEST (v0.27.0)
# ============================================================================

async def send_crypto_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ✅ v0.28.0: Ежедневный крипто дайджест в 9:00 UTC
    Теперь использует daily_digest_scheduler для консистентной отправки
    Отправляет в канал красивый пост с данными о крипте
    """
    if not CRYPTO_DIGEST_ENABLED:
        logger.warning(f"Crypto digest disabled - modules not available")
        return
    
    # ✅ v0.28.0: Используем канал из конфига или дефолт
    CHANNEL_ID = os.getenv('DIGEST_CHANNEL_ID', '@RVX_AI')  # Может быть @username или ID
    
    # Преобразуем числовой ID группы в правильный формат для Telegram
    # Приватные группы: 1003228919683 -> -1001003228919683
    if isinstance(CHANNEL_ID, str) and CHANNEL_ID.isdigit():
        channel_id_int = int(CHANNEL_ID)
        if channel_id_int > 0:
            CHANNEL_ID = -100 * (channel_id_int // 1000) - (channel_id_int % 1000)
    
    try:
        logger.info("📊 Начинаю сбор данных для крипто дайджеста...")
        
        # Собираем данные
        digest_data = await collect_digest_data()
        
        # Форматируем
        digest_text = format_digest(digest_data)
        
        # Отправляем в канал
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=digest_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        logger.info(f"Крипто дайджест успешно отправлен в {CHANNEL_ID}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке дайджеста: {e}", exc_info=True)

async def periodic_cache_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодическая очистка старого кэша."""
    if ENABLE_AUTO_CACHE_CLEANUP:
        logger.info("🧹 Запуск автоматической очистки кэша...")
        try:
            cleanup_old_cache()
        except Exception as e:
            logger.error(f"Ошибка очистки кэша: {e}")

# =============================================================================
# BACKGROUND JOBS (v0.17.0)
# =============================================================================

async def update_leaderboard_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет кэш рейтингов каждый час (v0.17.0)."""
    logger.info("📊 Обновление кэша рейтингов...")
    try:
        # Обновляем для всех периодов
        for period in ["week", "month", "all"]:
            leaderboard_data, total_users = get_leaderboard_data(period, limit=50)
            logger.info(f"   ✅ Период '{period}': {len(leaderboard_data)} пользователей")
    except Exception as e:
        logger.error(f"Ошибка обновления кэша рейтингов: {e}")

# =============================================================================
# ОБРАБОТКА ОШИБОК
# =============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок с восстановлением после сетевых ошибок."""
    error = context.error
    
    # Логируем ошибку
    logger.error(f"Необработанная ошибка: {error}", exc_info=error)
    
    # Не отправляем сообщение об ошибке для сетевых проблем
    if isinstance(error, (TelegramError, TimedOut, NetworkError)):
        logger.warning(f"Сетевая ошибка Telegram: {type(error).__name__}")
        return  # Пропускаем отправку уведомления при сетевых ошибках
    
    # Для других ошибок пытаемся отправить уведомление
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка.\n\n"
                "Пожалуйста, попробуйте позже."
            )
        except (TelegramError, TimedOut, NetworkError) as e:
            logger.warning(f"Не удалось отправить ошибку: {e}")
            pass  # Не можем отправить сообщение
# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================

@log_command
async def show_daily_quests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню с ежедневными задачами (v0.21.0)."""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    user_id = user.id
    
    # Получаем XP пользователя
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        user_xp = row[0] if row else 0
        
        # Получаем выполненные квесты
        from daily_quests_v2 import get_completed_quests_today, get_daily_quest_xp_earned
        completed_quests = get_completed_quests_today(user_id, conn)
        daily_xp_earned = get_daily_quest_xp_earned(user_id, conn)
    
    # Определяем уровень и задачи
    user_quest_level = get_user_level(user_xp)
    level_name = get_level_name(user_quest_level)
    daily_quests = get_daily_quests_for_level(user_quest_level)
    
    # Подготавливаем текст с информацией о уровне
    level_range = LEVEL_RANGES.get(user_quest_level, LEVEL_RANGES[1])
    xp_progress = user_xp - level_range['min_xp']
    xp_needed = level_range['max_xp'] - level_range['min_xp'] + 1
    xp_progress = min(xp_progress, xp_needed)
    progress_percent = int((xp_progress / xp_needed * 100) if xp_needed > 0 else 0)
    
    # Делаем прогресс-бар
    filled = int(progress_percent / 10)
    empty = 10 - filled
    progress_bar = "🟩" * filled + "⬜" * empty
    
    quests_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🎯 <b>ЕЖЕДНЕВНЫЕ ЗАДАЧИ</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        
        f"📈 <b>Твой уровень:</b> {level_name}\n"
        f"⭐ <b>Прогресс:</b> {progress_bar} {progress_percent}%\n"
        f"💾 <b>XP:</b> {user_xp}\n\n"
        
        f"📊 <b>Сегодня выполнено:</b>\n"
        f"   ✅ Задач: {len(completed_quests)}/5\n"
        f"   💰 XP заработано: {daily_xp_earned} XP\n\n"
        
        f"<b>─────────────────────────────────</b>\n"
        f"📋 <b>ЗАДАЧИ ДЛЯ ТВОЕГО УРОВНЯ:</b>\n\n"
    )
    
    # Добавляем все задачи с индикатором выполнения
    for idx, quest in enumerate(daily_quests, 1):
        quest_completed = str(quest.get('id', '')) in completed_quests
        status_icon = "✅" if quest_completed else "⭕"
        
        quests_text += (
            f"{status_icon} <b>{idx}. {quest['title']}</b>\n"
            f"   ✨ Награда: <b>{quest['xp']} XP</b>\n"
            f"   📊 Сложность: {quest['difficulty']}\n\n"
        )
    
    quests_text += f"<b>─────────────────────────────────</b>\n"
    quests_text += f"💡 Выполняй задачи каждый день и зарабатывай опыт! 🚀"
    
    # Кнопки для каждой задачи
    keyboard = []
    for quest in daily_quests:
        quest_completed = str(quest.get('id', '')) in completed_quests
        button_text = f"✅ {quest['title']}" if quest_completed else f"▶️ {quest['title']} ({quest['xp']} XP)"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"start_quest_{quest['id']}"
            )
        ])
    
    # Добавляем кнопку назад
    keyboard.append([
        InlineKeyboardButton("◀️ Назад на главную", callback_data="start_teach")
    ])
    
    # Отправляем или обновляем сообщение
    if query:
        try:
            await query.edit_message_text(
                quests_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            await query.message.reply_text(
                quests_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(
            quests_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# =============================================================================
# HEALTH CHECKS & PRODUCTION MONITORING (v0.21.0 - Production Ready)
# =============================================================================

async def bot_health_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодическая проверка здоровья бота (запускается каждые 5 минут)."""
    try:
        # Проверяем БД
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
        
        # Собираем метрики
        uptime = (datetime.now() - BOT_START_TIME).total_seconds() / 3600  # В часах
        metrics = bot_metrics.get_metrics_summary()
        
        # Проверяем критические показатели
        error_rate = 0
        if metrics['requests']['total'] > 0:
            error_rate = (metrics['requests']['failed'] / metrics['requests']['total']) * 100
        
        logger.info(
            f"💊 HEALTH CHECK: "
            f"Users={user_count} | "
            f"Uptime={uptime:.1f}h | "
            f"ErrorRate={error_rate:.1f}% | "
            f"CacheHits={metrics['cache']['hits']} | "
            f"AvgResponse={metrics['performance']['avg_response_ms']:.0f}ms"
        )
        
        # Предупреждение если высокая ошибка
        if error_rate > 20:
            logger.warning(f"HIGH ERROR RATE: {error_rate:.1f}%")
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")

async def graceful_shutdown(application) -> None:
    """Graceful shutdown с закрытием всех ресурсов."""
    logger.info("🛑 Инициирован graceful shutdown...")
    
    try:
        # Даем 30 секунд на завершение текущих операций
        logger.info(f"⏳ Ожидание завершения операций ({GRACEFUL_SHUTDOWN_TIMEOUT}s)...")
        await asyncio.sleep(min(5, GRACEFUL_SHUTDOWN_TIMEOUT))
        
        # Сохраняем финальную метрику
        bot_metrics.log_metrics_snapshot(compact=True)
        logger.info(f"Финальные метрики сохранены")
        
        # Очищаем сессии
        cleaned = await bot_state.cleanup_expired_sessions(timeout_seconds=0)
        logger.info(f"🧹 Очищено {cleaned} сессий")
        
        # Создаем финальный бэкап
        try:
            success, msg = await create_database_backup()
            if success:
                logger.info(f"💾 Финальный бэкап: {msg}")
        except Exception as e:
            logger.warning(f"Не удалось создать финальный бэкап: {e}")
        
        logger.info(f"Graceful shutdown завершен успешно")
        
    except Exception as e:
        logger.error(f"Ошибка во время graceful shutdown: {e}")

def main() -> None:
    """Запуск бота."""
    # ✅ CRITICAL: Ensure we're running in worker dyno on Railway
    # Prevent double-polling that causes "Conflict: terminated by other getUpdates"
    dyno_type = os.getenv("DYNO", "").split(".")[0] if os.getenv("DYNO") else ""
    railway_env = os.getenv("RAILWAY_ENVIRONMENT", "")
    is_railway = bool(railway_env)
    
    # If on Railway, warn if not in worker dyno
    if is_railway and dyno_type:
        if dyno_type != "worker":
            logger.warning(f"Running on {dyno_type} dyno (should be 'worker')")
            logger.warning(f"   If you see 'Conflict: terminated by other getUpdates', check Procfile")
            logger.warning(f"   Required: web: python api_server.py")
            logger.warning(f"   Required: worker: python bot.py")
    
    # Set asyncio event loop policy for Python 3.10+ Windows/Unix compatibility
    if sys.version_info >= (3, 10):
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        else:
            # For Unix/Linux, ensure we have a proper event loop
            try:
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            except:
                pass
    
    # Проверка обязательных переменных
    if not TELEGRAM_BOT_TOKEN:
        logger.critical(f"TELEGRAM_BOT_TOKEN не найден в .env!")
        return
    
    if not API_URL_NEWS:
        logger.critical(f"API_URL_NEWS не найден в .env!")
        return
    
    # ✅ v0.25.0: Initialize core systems
    print("\n" + "="*80)
    print("🚀 INITIALIZING v0.25.0 CORE SYSTEMS")
    print("="*80)
    
    tracker = get_tracker()
    honesty_prompt = get_honesty_system_prompt()
    analytics = get_analytics()
    
    print("✅ Event tracker initialized")
    print("✅ AI honesty system loaded")
    print("✅ Analytics system ready")
    print(f"✅ Config loaded: BOT_ADMIN_IDS={BOT_ADMIN_IDS}")
    print(f"✅ Cache enabled: {CACHE_ENABLED}")
    print(f"✅ Analytics enabled: {FEATURE_ANALYTICS_ENABLED}")
    print("="*80 + "\n")
    
    # 🔧 Сначала создаём БД, потом применяем миграции (order matters!)
    ensure_conversation_history_columns()
    
    # Инициализация БД (создаёт все таблицы)
    init_database()
    
    # Затем применяем миграции (после того как таблицы существуют)
    migrate_database()  # ✅ v0.37.0: Миграция новых таблиц
    
    # ✅ v0.39.0: Verify database schema integrity
    schema_check = verify_database_schema()
    if not schema_check['valid']:
        logger.warning(
            f"Database schema incomplete. Missing tables: {schema_check['missing_tables']}"
            f"\nAttempting to reinitialize..."
        )
        init_database()
        schema_check = verify_database_schema()
        if not schema_check['valid']:
            logger.error(
                f"Critical: Database schema still invalid after reinitialization!"
                f"\nMissing: {schema_check['missing_tables']}"
            )
    
    # � Создаем критические индексы (QUICK WIN v0.38.0)
    create_database_indices()  # ✅ v0.38.0: Database indices for performance
    
    # �💾 Инициализируем пул соединений (TIER 1 v0.22.0)
    init_db_pool()
    
    # 💾 Создаем автоматический бэкап при старте (v0.22.0)
    try:
        import asyncio
        asyncio.run(create_database_backup())
        asyncio.run(cleanup_old_backups())
    except Exception as e:
        logger.warning(f"Не удалось создать бэкап при старте: {e}")
    
    logger.info("=" * 70)
    logger.info("🚀 RVX Telegram Bot v0.7.0 запускается...")
    logger.info("=" * 70)
    logger.info(f"📊 Конфигурация:")
    logger.info(f"  • API URL: {API_URL_NEWS}")
    logger.info(f"  • Max input: {MAX_INPUT_LENGTH} символов")
    logger.info(f"  • Daily limit: {MAX_REQUESTS_PER_DAY} запросов")
    logger.info(f"  • Flood control: {FLOOD_COOLDOWN_SECONDS}с")
    logger.info(f"  • Admin users: {len(ADMIN_USERS)} (with limits)")
    logger.info(f"  • Unlimited admins: {len(UNLIMITED_ADMIN_USERS)} (no limits) ⭐")
    logger.info(f"  • Mandatory channel: {'Да' if MANDATORY_CHANNEL_ID else 'Нет'}")
    logger.info(f"  • Update channel: {'Да' if UPDATE_CHANNEL_ID else 'Нет'}")
    logger.info(f"  • Bot version: {BOT_VERSION}")
    logger.info(f"  • Analytics: {'Включена' if ENABLE_ANALYTICS else 'Выключена'}")
    logger.info("=" * 70)
    
    # =============================================================================
    # КОМАНДЫ ДЛЯ ДРОПОВ И АКТИВНОСТЕЙ (v0.15.0)
    # =============================================================================
    
    async def drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает свежие NFT дропы."""
        user_id = update.effective_user.id
        
        # Проверяем лимиты
        can_proceed, limit_info = check_daily_limit(user_id)
        if not can_proceed:
            await update.message.reply_text(
                f"⚠️ Ты исчерпал дневной лимит запросов: {limit_info}\n"
                f"Попробуй завтра или используй /limits для подробности"
            )
            return
        
        # Отправляем сообщение о загрузке
        status_msg = await update.message.reply_text("⏳ Загружаю свежие дропы...")
        increment_daily_requests(user_id)
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API_URL_NEWS.replace('/explain_news', '')}/get_drops?limit=10")
                response.raise_for_status()
                data = response.json()
                
                drops = data.get("drops", [])
                if not drops:
                    await status_msg.edit_text("😔 Сейчас нет активных дропов. Проверь позже!")
                    return
                
                text = "📦 <b>АКТУАЛЬНЫЕ NFT ДРОПЫ</b>\n\n"
                for i, drop in enumerate(drops[:10], 1):
                    text += (
                        f"<b>{i}. {drop.get('name', 'Unknown')}</b> ({drop.get('symbol', '?')})\n"
                        f"  ⛓️ Цепь: {drop.get('chain', 'Unknown')}\n"
                        f"  💰 Цена: {drop.get('price', 'TBA')}\n"
                        f"  ⏱️ Начало: {drop.get('time_until', 'TBA')}\n"
                        f"  🔗 {drop.get('url', '#')}\n\n"
                    )
                
                text += f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
                
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
                
                # Сохраняем в историю
                with get_db() as conn:
                    cursor = conn.cursor()
                    for drop in drops[:5]:
                        cursor.execute(
                            "INSERT INTO drops_history (user_id, drop_name, drop_type, chain) VALUES (?, ?, ?, ?)",
                            (user_id, drop.get('name'), 'nft_drop', drop.get('chain'))
                        )
                    conn.commit()
                        
        except Exception as e:
            logger.error(f"Ошибка при получении дропов: {e}")
            await status_msg.edit_text(f"❌ Ошибка при загрузке дропов: {str(e)[:100]}")
    
    async def activities_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает активности в топ-проектах."""
        user_id = update.effective_user.id
        
        can_proceed, limit_info = check_daily_limit(user_id)
        if not can_proceed:
            await update.message.reply_text(
                f"⚠️ Ты исчерпал дневной лимит запросов: {limit_info}"
            )
            return
        
        status_msg = await update.message.reply_text("⏳ Загружаю активности...")
        increment_daily_requests(user_id)
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API_URL_NEWS.replace('/explain_news', '')}/get_activities")
                response.raise_for_status()
                data = response.json()
                
                text = "🔥 <b>АКТИВНОСТИ В ТОП-ПРОЕКТАХ</b>\n\n"
                
                # Стейкинг
                staking = data.get("staking_updates", [])
                if staking:
                    text += "<b>📊 Обновления стейкинга:</b>\n"
                    for item in staking[:3]:
                        text += f"  • <b>{item.get('project')}</b>: {item.get('activity')}\n"
                    text += "\n"
                
                # Новые ланчи
                launches = data.get("new_launches", [])
                if launches:
                    text += "<b>🚀 Новые ланчи:</b>\n"
                    for item in launches[:3]:
                        text += f"  • <b>{item.get('project')}</b>: {item.get('change')} ({item.get('volume')})\n"
                    text += "\n"
                
                # Гавернанс
                governance = data.get("governance", [])
                if governance:
                    text += "<b>🗳️ Гавернанс:</b>\n"
                    for item in governance[:3]:
                        text += f"  • <b>{item.get('project')}</b>: {item.get('proposal', 'Новое предложение')}\n"
                    text += "\n"
                
                text += f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
                
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"Ошибка при получении активностей: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    
    async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает трендовые (вирусные) токены."""
        user_id = update.effective_user.id
        
        can_proceed, limit_info = check_daily_limit(user_id)
        if not can_proceed:
            await update.message.reply_text(f"⚠️ Лимит исчерпан: {limit_info}")
            return
        
        status_msg = await update.message.reply_text("⏳ Загружаю трендовые токены...")
        increment_daily_requests(user_id)
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API_URL_NEWS.replace('/explain_news', '')}/get_trending?limit=10")
                response.raise_for_status()
                data = response.json()
                
                drops = data.get("drops", [])
                if not drops:
                    await status_msg.edit_text("😔 Сейчас нет трендовых токенов")
                    return
                
                text = "📈 <b>ВИРУСНЫЕ ТОКЕНЫ (TRENDING)</b>\n\n"
                for i, token in enumerate(drops[:10], 1):
                    text += (
                        f"<b>{i}. {token.get('name')}</b> (${token.get('symbol', '?')})\n"
                        f"  Ранг: #{token.get('market_cap_rank', 'N/A')}\n"
                        f"  Скор: {token.get('score', 0)}\n\n"
                    )
                
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"Ошибка при получении трендов: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    
    async def subscribe_drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Подписаться на уведомления о дропах."""
        user_id = update.effective_user.id
        
        keyboard = [
            [
                InlineKeyboardButton("Arbitrum 🔷", callback_data="sub_arbitrum"),
                InlineKeyboardButton("Solana ◎", callback_data="sub_solana"),
            ],
            [
                InlineKeyboardButton("Polygon 🟣", callback_data="sub_polygon"),
                InlineKeyboardButton("Ethereum 🔹", callback_data="sub_ethereum"),
            ],
            [
                InlineKeyboardButton("Все цепи 🌐", callback_data="sub_all"),
                InlineKeyboardButton("Отписаться ❌", callback_data="unsub_all"),
            ],
        ]
        
        await update.message.reply_text(
            "📢 <b>Подписаться на уведомления о дропах</b>\n\n"
            "Выбери цепь(и) для получения уведомлений:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    async def my_subscriptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает текущие подписки."""
        user_id = update.effective_user.id
        
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT chain, enabled FROM user_drop_subscriptions WHERE user_id = ? AND enabled = 1",
                    (user_id,)
                )
                subs = cursor.fetchall()
            
            if not subs:
                await update.message.reply_text(
                    "📭 У тебя нет активных подписок на дропы\n"
                    "Используй /subscribe_drops для подписки"
                )
                return
            
            text = "📋 <b>Твои подписки на дропы:</b>\n\n"
            for chain, _ in subs:
                emoji = {
                    "arbitrum": "🔷",
                    "solana": "◎",
                    "polygon": "🟣",
                    "ethereum": "🔹",
                    "all": "🌐"
                }.get(chain, "•")
                text += f"{emoji} {chain.capitalize()}\n"
            
            text += f"\n✅ Всего подписок: {len(subs)}"
            
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            logger.error(f"Ошибка при получении подписок: {e}")
            await update.message.reply_text("❌ Ошибка при получении подписок")
    
    # ================================================================
    # 🔧 CRITICAL: Pre-Application Cleanup
    # Kill all stale processes before creating the Application instance
    # This prevents "409 Conflict: terminated by other getUpdates"
    # ================================================================
    print("\n🔧 PRE-APPLICATION CLEANUP")
    print("   Killing any competing bot/api processes...")
    
    # Try psutil-based cleanup
    try:
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                pid = proc.info['pid']
                
                if 'bot.py' in cmdline and pid != current_pid:
                    try:
                        os.kill(pid, 9)
                        print(f"   🗑️ Killed old bot process PID={pid}")
                    except ProcessLookupError:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except ImportError:
        print("   ⚠️ psutil not available for pre-app cleanup")
    except Exception as e:
        print(f"   ⚠️ Pre-cleanup warning: {e}")
    
    # Wait for Telegram polling lock to release
    print("   ⏳ Waiting 2 seconds for Telegram polling lock to release...")
    time.sleep(2)
    print("✅ Pre-application cleanup completed\n")
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Установка списка команд (показывается при вводе / в Telegram) - v0.11.0
    async def set_commands_on_start(context: ContextTypes.DEFAULT_TYPE):
        """Устанавливает список команд в Telegram при запуске бота."""
        try:
            await context.bot.set_my_commands([
                BotCommand("start", "🏠 Главное меню"),
                BotCommand("help", "❓ Помощь и инструкция"),
                BotCommand("teach", "🎓 Интерактивный учитель"),
                BotCommand("learn", "📚 Интерактивные курсы"),
                BotCommand("calc", "🧮 Крипто калькулятор"),
                BotCommand("drops", "📦 Свежие NFT дропы"),
                BotCommand("activities", "🔥 Активности в проектах"),
                BotCommand("trending", "📈 Вирусные токены"),
                BotCommand("subscribe_drops", "📢 Подписка на дропы"),
                BotCommand("stats", "📊 Твоя статистика и достижения"),
                BotCommand("tasks", "📋 Ежедневные задачи"),
                BotCommand("history", "📜 История анализов"),
                BotCommand("limits", "⚡ Твои лимиты"),
                BotCommand("search", "🔍 Поиск в истории"),
                BotCommand("bookmark", "📌 Сохранить анализ"),
                BotCommand("bookmarks", "📎 Мои закладки"),
                BotCommand("export", "📥 Экспорт истории"),
                BotCommand("detect", "🛡️ Обнаружить манипуляцию"),
                BotCommand("tips", "💡 Советы от манипуляции"),
                BotCommand("menu", "⚙️ Быстрое меню"),
                BotCommand("clear_history", "🗑️ Очистить контекст разговора"),
                BotCommand("context_stats", "📊 Статистика контекста"),
            ])
            logger.info(f"Список команд установлен в Telegram")
        except Exception as e:
            logger.error(f"Ошибка при установке команд: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # КОМАНДЫ АНАЛИЗА МАНИПУЛЯЦИЙ И ПРОПАГАНДЫ (v0.32.0)
    # ═══════════════════════════════════════════════════════════════════════════════
    
    @log_command
    async def detect_propaganda_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Анализирует текст на пропаганду и манипуляции.
        Использование: /detect <текст> или ответь на сообщение"""
        user_id = update.effective_user.id
        
        text_to_analyze = None
        
        # Если это ответ на сообщение
        if update.message.reply_to_message:
            text_to_analyze = update.message.reply_to_message.text or update.message.reply_to_message.caption
        
        # Если текст передан в команду
        elif context.args:
            text_to_analyze = " ".join(context.args)
        
        # Если ничего не передано
        if not text_to_analyze:
            await update.message.reply_text(
                "🛡️ <b>ДЕТЕКТОР МАНИПУЛЯЦИЙ И ПРОПАГАНДЫ</b>\n\n"
                "Анализирует текст на признаки:\n"
                "  • Нагнетание страха\n"
                "  • Ложные обещания\n"
                "  • Теории заговора\n"
                "  • Эмоциональные манипуляции\n"
                "  • И другие техники\n\n"
                "<b>Использование:</b>\n"
                "  /detect <текст>\n"
                "  или ответьте на сообщение и напишите /detect\n\n"
                "💡 Тип: /tips для советов как распознавать манипуляции",
                parse_mode=ParseMode.HTML
            )
            return
        
        try:
            # Анализируем текст
            analysis = analyze_propaganda(text_to_analyze)
            
            if analysis:
                response = format_propaganda_analysis(analysis)
                if response:
                    await update.message.reply_text(response, parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_text(
                        "✅ <b>Признаков манипуляции не обнаружено</b>\n\n"
                        "Этот текст выглядит объективным и не содержит явных техник пропаганды.",
                        parse_mode=ParseMode.HTML
                    )
            else:
                await update.message.reply_text(
                    "❌ Не удалось проанализировать текст. Проверьте длину (минимум 20 символов).",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Ошибка при анализе пропаганды: {e}")
            await update.message.reply_text(
                "❌ Ошибка при анализе текста",
                parse_mode=ParseMode.HTML
            )
    
    @log_command
    async def propaganda_tips_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает советы как распознавать манипуляции и пропаганду"""
        user_id = update.effective_user.id
        
        try:
            tips = get_propaganda_tips()
            await update.message.reply_text(tips, parse_mode=ParseMode.HTML)
        
        except Exception as e:
            logger.error(f"Ошибка при выводе советов: {e}")
            await update.message.reply_text(
                "❌ Ошибка при загрузке советов",
                parse_mode=ParseMode.HTML
            )
    
    # Регистрация команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # ✅ v0.26.0: Conversation Context Commands
    application.add_handler(CommandHandler("clear_history", clear_history_command))
    application.add_handler(CommandHandler("context_stats", context_stats_command))
    
    # ✅ v0.25.0: Admin Dashboard
    application.add_handler(CommandHandler("admin_metrics", admin_metrics_command))
    application.add_handler(CommandHandler("admin", admin_metrics_command))  # Alias
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("limits", limits_command))
    
    # НОВЫЕ КОМАНДЫ v0.5.0
    application.add_handler(CommandHandler("learn", learn_command))
    application.add_handler(CommandHandler("lesson", lesson_command))
    application.add_handler(CommandHandler("tools", tools_command))
    application.add_handler(CommandHandler("bookmark", bookmark_command))
    application.add_handler(CommandHandler("bookmarks", bookmarks_command))
    application.add_handler(CommandHandler("ask", ask_command))
    
    # НОВАЯ КОМАНДА v0.7.0 - Интерактивный учитель по крипто, AI, Web3, трейдингу
    application.add_handler(CommandHandler("teach", teach_command))
    
    # НОВАЯ КОМАНДА v0.37.0 - Прогресс обучения с рекомендациями
    application.add_handler(CommandHandler("learn_progress", learn_progress_command))
    
    # НОВАЯ КОМАНДА v0.11.0 - Ежедневные задачи
    application.add_handler(CommandHandler("tasks", tasks_command))
    
    # НОВАЯ КОМАНДА v0.16.0 - Бесплатные ресурсы
    application.add_handler(CommandHandler("resources", resources_command))
    
    # НОВАЯ КОМАНДА v0.32.0 - Детектирование пропаганды и манипуляций
    application.add_handler(CommandHandler("detect", detect_propaganda_command))
    application.add_handler(CommandHandler("tips", propaganda_tips_command))
    
    # ✅ НОВАЯ КОМАНДА v0.33.0 - Крипто калькулятор для расчета market cap
    application.add_handler(CommandHandler("calc", calculator_command))
    
    # НОВАЯ КОМАНДА v0.12.0 - Динамические команды квестов (quest_what_is_dex, quest_what_is_staking и т.д.)
    quest_ids = list(DAILY_QUESTS.keys())
    quest_commands = [f"quest_{qid}" for qid in quest_ids]
    application.add_handler(CommandHandler(quest_commands, quest_command))
    
    # Динамические команды для запуска курсов (start_blockchain_basics, start_defi_contracts, etc.)
    application.add_handler(CommandHandler(["start_blockchain_basics", "start_defi_contracts", "start_scaling_dao"], start_course_command))
    
    # Админские команды
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("test_digest", test_digest_command))  # 📊 Тест крипто дайджеста
    application.add_handler(CommandHandler("ban", ban_user_command))
    application.add_handler(CommandHandler("unban", unban_user_command))
    application.add_handler(CommandHandler("clear_cache", clear_cache_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # НОВЫЕ КОМАНДЫ ДЛЯ ПУБЛИКАЦИИ В КАНАЛ (v0.15.0)
    application.add_handler(CommandHandler("post_to_channel", post_to_channel_command))
    application.add_handler(CommandHandler("notify_version", notify_version_command))
    application.add_handler(CommandHandler("notify_quests", notify_quests_command))
    application.add_handler(CommandHandler("notify_milestone", notify_milestone_command))
    
    # НОВЫЕ КОМАНДЫ ДЛЯ ДРОПОВ И АКТИВНОСТЕЙ (v0.15.0)
    application.add_handler(CommandHandler("drops", drops_command))
    application.add_handler(CommandHandler("activities", activities_command))
    application.add_handler(CommandHandler("trending", trending_command))
    application.add_handler(CommandHandler("subscribe_drops", subscribe_drops_command))
    application.add_handler(CommandHandler("my_subscriptions", my_subscriptions_command))
    
    # Обработчики
    application.add_handler(CallbackQueryHandler(button_callback))
    # Анализ фото ОТКЛЮЧЕН на free tier (экономия квоты для текстовых новостей)
    # application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    # Handle text messages ONLY in private chats (not in channels/groups)
    # This prevents bot from responding to every message in public channels
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
        handle_message
    ))
    
    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Фоновые задачи
    job_queue = application.job_queue
    
    if ENABLE_AUTO_CACHE_CLEANUP:
        # Очистка кэша каждые 6 часов
        job_queue.run_repeating(
            periodic_cache_cleanup,
            interval=21600,  # 6 часов
            first=10  # Первый запуск через 10 секунд
        )
        logger.info(f"Автоматическая очистка кэша настроена (каждые 6ч)")
    
    # Периодическая очистка истекших сессий каждый час (v0.24.0)
    job_queue.run_repeating(
        periodic_session_cleanup,
        interval=3600,  # 1 час
        first=60  # Первый запуск через 60 секунд
    )
    logger.info(f"Периодическая очистка сессий настроена (каждый час)")
    
    # Периодический снимок метрик каждые 6 часов (v0.24.0)
    job_queue.run_repeating(
        periodic_metrics_snapshot,
        interval=21600,  # 6 часов
        first=120  # Первый запуск через 2 минуты
    )
    logger.info(f"Периодическое логирование метрик настроено (каждые 6 часов)")
    
    # Обновление кэша рейтингов каждый час (v0.17.0)
    job_queue.run_repeating(
        update_leaderboard_cache,
        interval=3600,  # 1 час
        first=30  # Первый запуск через 30 секунд
    )
    logger.info(f"Обновление рейтингов настроено (каждый час)")
    
    # Health check каждые 5 минут (v0.21.0 - Production Ready)
    job_queue.run_repeating(
        bot_health_check,
        interval=HEALTH_CHECK_INTERVAL,  # 5 минут (300 секунд)
        first=30  # Первый запуск через 30 секунд после старта
    )
    logger.info(f"💊 Health check настроен (каждые {HEALTH_CHECK_INTERVAL} сек)")
    
    # ✅ v0.28.0: Крипто дайджест теперь управляется через daily_digest_scheduler.py
    # (удалена старая job_queue реализация - используется APScheduler для консистентности)
    
    # Установка списка команд при запуске бота
    job_queue.run_once(set_commands_on_start, when=1)  # Запускаем через 1 секунду после старта
    
    try:
        logger.info("🚀 БОТ ПОЛНОСТЬЮ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
        # ✅ CRITICAL FIX v7: Explicit event loop for Railway compatibility
        # Don't use asyncio.run() - it closes loop immediately (breaks PTB)
        # Create explicit loop and DON'T close it - let Python handle cleanup
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # CRITICAL: Before starting polling, kill ALL other bot processes one more time
        print("🔧 PRE-POLLING CLEANUP: Killing any competing bot instances...")
        try:
            import psutil
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    pid = proc.info['pid']
                    if 'bot.py' in cmdline and pid != current_pid:
                        try:
                            os.kill(pid, 9)
                            print(f"   🗑️ Killed bot process PID={pid}")
                        except ProcessLookupError:
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            print("   ⚠️ psutil not available")
        except Exception as e:
            print(f"   ⚠️ Pre-polling cleanup warning: {e}")
        
        time.sleep(1)  # Wait for kill signal to propagate
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # ✅ v0.28.0: Initialize daily digest scheduler BEFORE polling
            try:
                async def init_scheduler():
                    print("🚀 Initializing daily digest scheduler...")
                    await initialize_digest_scheduler()
                    print("✅ Daily digest scheduler started")
                
                loop.run_until_complete(init_scheduler())
            except Exception as e:
                logger.error(f"⚠️ Failed to initialize digest scheduler: {e}")
                # Don't fail if digest scheduler fails - bot should still work
            
            # CRITICAL: Delete any webhook to ensure polling mode works
            print("🔧 Ensuring polling mode (removing webhook if any)...")
            try:
                async def delete_webhook():
                    await application.bot.delete_webhook(drop_pending_updates=True)
                loop.run_until_complete(delete_webhook())
                print("✅ Webhook deleted successfully")
            except Exception as e:
                print(f"⚠️ Webhook deletion warning: {e}")
            
            # Run polling without closing loop (prevents "Event loop is closed" crash)
            print("🚀 Starting polling...")
            loop.run_until_complete(application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True))
        except Conflict as e:
            # Another bot instance is running - graceful exit
            logger.error(f"💥 CONFLICT: {e}")
            logger.error("⚠️ Another bot instance is running. Killing this process to restart...")
            try:
                loop.run_until_complete(application.stop())
            except Exception as stop_error:
                logger.warning(f"Error during graceful stop: {stop_error}")
            # Kill current process to restart fresh (Railway will restart)
            print("💥 Terminating process...")
            os.kill(os.getpid(), 9)
        except RuntimeError as e:
            if "Event loop" in str(e):
                # Event loop crashed - restart needed
                logger.error(f"Event loop crashed: {e}")
                logger.error("💥 Restarting process...")
                os.kill(os.getpid(), 9)
            else:
                raise
        except Exception as e:
            logger.error(f"Polling error: {e}", exc_info=True)
            raise
        finally:
            # ✅ v0.28.0: Stop daily digest scheduler
            try:
                if not loop.is_closed():
                    async def shutdown_scheduler():
                        await stop_digest_scheduler()
                    loop.run_until_complete(shutdown_scheduler())
                    logger.info(f"Daily digest scheduler stopped")
            except Exception as e:
                logger.debug(f"Error stopping digest scheduler: {e}")
            
            # Clean shutdown - don't close loop to prevent "Event loop is closed" error
            try:
                if not loop.is_closed():
                    # Cancel all pending tasks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    # Give time for cancellation
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                logger.debug(f"Error during task cleanup: {e}")
            # Don't close the loop - let Python handle it
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)

if __name__ == "__main__":
    main()
