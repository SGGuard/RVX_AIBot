import os
import logging
import json
import httpx
import hashlib
import sqlite3
import asyncio
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError, TimedOut, NetworkError
from telegram.constants import ParseMode

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

# Учительский модуль (v0.7.0) - ИИ преподает крипто, AI, Web3, трейдинг
from teacher import teach_lesson, TEACHING_TOPICS, DIFFICULTY_LEVELS

# Новая система адаптивных квестов v2 (v0.13.0)
from daily_quests_v2 import (
    DAILY_QUESTS, get_user_level, get_level_name, get_level_info,
    get_daily_quests_for_level
)
from quest_handler_v2 import (
    start_quest, start_test, show_question, handle_answer, show_results
)

# В памяти считаем попытки регенерации фидбека (ключ — request_id)
feedback_attempts: Dict[int, int] = {}
FEEDBACK_MAX_RETRIES = 4

# Последовательность режимов регенерации (от простого к более наглядному)
REGENERATION_MODES = [
    ("упрости", "Объясни проще, используя короткие предложения и минимум терминов."),
    ("примеры", "Приведи конкретные примеры и короткие сценарии использования."),
    ("пошагово", "Разбей объяснение на пошаговую инструкцию с нумерованными шагами."),
    ("аналогия", "Поясни через аналогию или метафору, чтобы упростить понимание.")
]

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

load_dotenv()

# Основные настройки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS", "http://localhost:8000/explain_news")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0"))
API_RETRY_ATTEMPTS = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
API_RETRY_DELAY = float(os.getenv("API_RETRY_DELAY", "2.0"))

# Контроль доступа
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
ADMIN_USERS = set(map(int, filter(None, os.getenv("ADMIN_USERS", "").split(","))))
UNLIMITED_ADMIN_USERS = set(map(int, filter(None, os.getenv("UNLIMITED_ADMIN_USERS", "").split(","))))  # Админы без лимитов
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "50"))

# Обязательная подписка
MANDATORY_CHANNEL_ID = os.getenv("MANDATORY_CHANNEL_ID", "")
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "")

# Канал для постов об обновлениях (админский канал для публикации новостей)
UPDATE_CHANNEL_ID = os.getenv("UPDATE_CHANNEL_ID", "")  # Канал для постов об обновлениях
BOT_VERSION = "0.15.0"  # Текущая версия бота

# База данных
DB_PATH = os.getenv("DB_PATH", "rvx_bot.db")
DB_BACKUP_INTERVAL = int(os.getenv("DB_BACKUP_INTERVAL", "86400"))  # 24 часа

# Фичи
ENABLE_ANALYTICS = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
ENABLE_AUTO_CACHE_CLEANUP = os.getenv("ENABLE_AUTO_CACHE_CLEANUP", "true").lower() == "true"
CACHE_MAX_AGE_DAYS = int(os.getenv("CACHE_MAX_AGE_DAYS", "7"))

# =============================================================================
# ЛОГИРОВАНИЕ
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
        logger.warning("⚠️ UPDATE_CHANNEL_ID не установлен - посты не будут отправляться")
        return False
    
    try:
        await context.bot.send_message(
            chat_id=UPDATE_CHANNEL_ID,
            text=text,
            parse_mode=parse_mode,
            disable_notification=silent
        )
        logger.info("📢 Пост отправлен в канал обновлений")
        return True
    except TelegramError as e:
        logger.error(f"❌ Ошибка при отправке поста в канал: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при отправке поста: {e}")
        return False


async def notify_version_update(context: ContextTypes.DEFAULT_TYPE, version: str, changelog: str):
    """
    Отправляет уведомление об обновлении версии в канал.
    """
    post = f"""🚀 <b>ОБНОВЛЕНИЕ БОТА - Версия {version}</b>

<b>Что нового:</b>
{changelog}

⏰ Обновление: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

✨ Спасибо за активность! Ваши отзывы помогают улучшить бот!"""
    
    await send_channel_post(context, post)


async def notify_new_quests(context: ContextTypes.DEFAULT_TYPE):
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


async def notify_system_maintenance(context: ContextTypes.DEFAULT_TYPE, duration_minutes: int = 5):
    """
    Отправляет уведомление об обслуживании системы.
    """
    post = f"""🔧 <b>Техническое обслуживание</b>

⏸️ Бот временно недоступен для обслуживания

⏱️ Ожидаемая длительность: ~{duration_minutes} минут

🔄 Система будет восстановлена вскоре

Спасибо за ваше терпение!"""
    
    await send_channel_post(context, post)


async def notify_milestone_reached(context: ContextTypes.DEFAULT_TYPE, milestone: str, count: int):
    """
    Отправляет уведомление о достижении вехи (например, 100 пользователей).
    """
    post = f"""🎉 <b>Веха достигнута: {milestone}!</b>

📈 В сообществе RVX {count} активных пользователей!

🙏 Спасибо за вашу поддержку и активность

✨ Продолжайте учиться и развиваться вместе с нами!"""
    
    await send_channel_post(context, post)


async def notify_new_feature(context: ContextTypes.DEFAULT_TYPE, feature_name: str, description: str):
    """
    Отправляет уведомление о новой функции.
    """
    post = f"""✨ <b>Новая функция: {feature_name}</b>

📝 {description}

🎯 Используйте /help для подробной информации

💪 Продолжайте развиваться с новыми возможностями!"""
    
    await send_channel_post(context, post)


async def notify_stats_milestone(context: ContextTypes.DEFAULT_TYPE, stat_name: str, value: str):
    """
    Отправляет уведомление о статистическом рекорде.
    """
    post = f"""📊 <b>Новый рекорд: {stat_name}</b>

🏆 {value}

🔥 Это показывает активность нашего сообщества!

✨ Спасибо вам всем за участие!"""
    
    await send_channel_post(context, post)

# =============================================================================

# БАЗА ДАННЫХ
# =============================================================================

@contextmanager
def get_db():
    """Context manager для работы с БД с улучшенной обработкой ошибок."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging для производительности
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"❌ DB ошибка: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def check_column_exists(cursor, table: str, column: str) -> bool:
    """Проверяет существование колонки в таблице."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def migrate_database():
    """Миграция базы данных к новой схеме v0.5.0."""
    logger.info("🔄 Проверка необходимости миграции...")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Миграция users
        migrations_needed = False
        
        if not check_column_exists(cursor, 'users', 'is_banned'):
            logger.info("  • Добавление колонки is_banned...")
            cursor.execute("ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'ban_reason'):
            logger.info("  • Добавление колонки ban_reason...")
            cursor.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'daily_requests'):
            logger.info("  • Добавление колонки daily_requests...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_requests INTEGER DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'daily_reset_at'):
            logger.info("  • Добавление колонки daily_reset_at...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_reset_at TIMESTAMP")
            migrations_needed = True
        
        # NEW v0.5.0: Миграция новых полей для обучения
        if not check_column_exists(cursor, 'users', 'knowledge_level'):
            logger.info("  • Добавление колонки knowledge_level...")
            cursor.execute("ALTER TABLE users ADD COLUMN knowledge_level TEXT DEFAULT 'unknown'")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'xp'):
            logger.info("  • Добавление колонки xp...")
            cursor.execute("ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0")
            migrations_needed = True
        
        if not check_column_exists(cursor, 'users', 'level'):
            logger.info("  • Добавление колонки level...")
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
        
        if migrations_needed:
            logger.info("✅ Миграция успешно завершена")
        else:
            logger.info("✅ Миграция не требуется, схема актуальна")

def init_database():
    """Инициализация базы данных с расширенной схемой v0.5.0."""
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
        
        logger.info("✅ База данных инициализирована (v0.15.0)")
    
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

# --- Функции работы с пользователями ---

def save_user(user_id: int, username: str, first_name: str):
    """Сохраняет или обновляет информацию о пользователе."""
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
    """Проверяет, забанен ли пользователь."""
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

def increment_user_requests(user_id: int):
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

def get_request_by_id(request_id: int) -> Optional[Dict[str, str]]:
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

def save_feedback(user_id: int, request_id: int, is_helpful: bool, comment: Optional[str] = None):
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

def set_cache(cache_key: str, response_text: str):
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

def cleanup_old_cache():
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
        logger.info(f"🗑️ Удалено {deleted} старых/неиспользуемых записей из кэша")
        
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

def init_daily_tasks(user_id: int):
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

def update_task_progress(user_id: int, task_type: str, increment: int = 1):
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

def log_analytics_event(event_type: str, user_id: Optional[int] = None, data: Optional[dict] = None):
    """Логирует аналитическое событие."""
    if not ENABLE_ANALYTICS:
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analytics (event_type, user_id, data)
            VALUES (?, ?, ?)
        """, (event_type, user_id, json.dumps(data) if data else None))

# =============================================================================
# УТИЛИТЫ
# =============================================================================

# In-memory хранилища для rate limiting
user_last_request: Dict[int, datetime] = {}
user_last_news: Dict[int, str] = {}
user_current_course: Dict[int, str] = {}  # Отслеживает текущий курс пользователя

# Quiz state tracking: user_id -> {lesson, questions, current_q, answers, score}
user_quiz_state: Dict[int, Dict] = {}

def check_flood(user_id: int) -> bool:
    """Проверяет flood control."""
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

def get_cache_key(text: str) -> str:
    """Генерирует ключ кэша для текста."""
    normalized = text.lower().strip()
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

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
        logger.error(f"❌ Ошибка проверки подписки для {user_id}: {e}")
        return True  # В случае ошибки не блокируем пользователя

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ от API и очищает от нежелательного форматирования."""
    if not isinstance(api_response, dict):
        logger.warning(f"⚠️ API вернул не dict: {type(api_response)}")
        return None
    
    simplified_text = api_response.get("simplified_text")
    
    if not simplified_text or not isinstance(simplified_text, str):
        logger.warning("⚠️ simplified_text отсутствует или не строка")
        return None
    
    simplified_text = simplified_text.strip()
    
    # Очищаем от звёздочек и markdown маркеров
    # Но СОХРАНЯЕМ подчеркивания в словах (например, learning_question)
    simplified_text = simplified_text.replace("**", "")  # Убираем жирное
    simplified_text = simplified_text.replace("__", "")  # Убираем двойное подчеркивание
    simplified_text = simplified_text.replace("~~", "")  # Убираем зачеркивание
    
    if len(simplified_text) < 10:
        logger.warning(f"⚠️ Слишком короткий ответ: {len(simplified_text)} символов")
        return None
    
    # Telegram ограничивает 4096 символов
    if len(simplified_text) > 4096:
        logger.warning(f"⚠️ Ответ слишком длинный ({len(simplified_text)} символов), обрезаю")
        return simplified_text[:4090] + "\n\n..."
    
    return simplified_text
async def call_api_with_retry(news_text: str, user_id: Optional[int] = None) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Вызывает API с повторными попытками с экспоненциальной задержкой.
    Включает контекст знаний пользователя в запрос если доступен.
    Возвращает (response_text, processing_time_ms, error_message)
    """
    start_time = datetime.now()
    last_error = None
    
    # Подготавливаем контент для отправки
    request_payload = {"text_content": news_text}
    
    # Добавляем контекст пользователя если доступен
    user_context = None
    if user_id:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                # Получаем уровень знаний пользователя
                cursor.execute("SELECT knowledge_level FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                user_level = row[0] if row else "beginner"
                
                # Получаем краткий прогресс
                progress = get_user_course_summary(cursor, user_id)
                
                user_context = {
                    "knowledge_level": user_level,
                    "course_progress": progress
                }
                
                request_payload["user_context"] = user_context
                logger.info(f"📚 Добавлен контекст пользователя {user_id}: уровень={user_level}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить контекст пользователя: {e}")
    
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"🔄 API попытка {attempt}/{API_RETRY_ATTEMPTS}")
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(
                    API_URL_NEWS,
                    json=request_payload,
                    headers={"X-User-ID": str(user_id)}  # NEW v0.14.0: передаем user_id для проверки лимита
                )
                response.raise_for_status()
                api_response = response.json()
                
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Невалидный ответ от API")
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(f"✅ API успех за {processing_time:.0f}ms (попытка {attempt})")
                
                # NEW v0.14.0: Инкрементируем счетчик запросов
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        increment_daily_requests(cursor, user_id)
                        conn.commit()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при обновлении счетчика запросов: {e}")
                
                return simplified_text, processing_time, None
        
        except httpx.TimeoutException as e:
            last_error = f"Таймаут ({API_TIMEOUT}s)"
            logger.warning(f"⏱️ Таймаут на попытке {attempt}: {e}")
        
        except httpx.ConnectError as e:
            last_error = "Ошибка подключения"
            logger.warning(f"🔗 Ошибка подключения на попытке {attempt}: {e}")
        
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            
            if e.response.status_code == 429:  # Too many requests
                logger.warning(f"⛔ Rate limit на попытке {attempt}: {e}")
                last_error = "Rate limit от API"
            else:
                logger.error(f"❌ HTTP ошибка на попытке {attempt}: {e}")
        
        except Exception as e:
            last_error = str(e)[:100]  # Ограничиваем длину
            logger.error(f"❌ Ошибка на попытке {attempt}: {e}")
        
        # Ждем перед следующей попыткой (кроме последней)
        if attempt < API_RETRY_ATTEMPTS:
            wait_time = API_RETRY_DELAY * (2 ** (attempt - 1))  # Экспоненциальная задержка
            logger.debug(f"⏳ Ожидание {wait_time:.1f}сек перед следующей попыткой...")
            await asyncio.sleep(wait_time)
    
    # Все попытки исчерпаны
    processing_time = (datetime.now() - start_time).total_seconds() * 1000
    logger.error(f"❌ Все {API_RETRY_ATTEMPTS} попытки провалены. Последняя ошибка: {last_error}")
    
    return None, processing_time, last_error

# =============================================================================
# ДЕКОРАТОРЫ
# =============================================================================

def admin_only(func):
    """Декоратор для команд, доступных только администраторам."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USERS:
            await update.message.reply_text("⛔ Только для администраторов")
            return
        return await func(update, context)
    return wrapper

def log_command(func):
    """Декоратор для логирования использования команд."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        command = update.message.text.split()[0] if update.message else "unknown"
        logger.info(f"📝 Команда {command} от {user.id} (@{user.username})")
        
        if ENABLE_ANALYTICS:
            log_analytics_event("command_used", user.id, {"command": command})
        
        return await func(update, context)
    return wrapper

# =============================================================================
# КОМАНДЫ
# =============================================================================

@log_command
async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает адаптивные ежедневные задания по уровню пользователя."""
    user = update.effective_user
    user_id = user.id
    
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
        logger.error(f"❌ Ошибка tasks_command: {e}")
        error_text = "❌ Ошибка. Попробуй позже."
        if is_callback and query:
            await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)


@log_command
async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команд /quest_* для запуска конкретного квеста."""
    user_id = update.effective_user.id
    
    # Получаем quest_id из команды
    # Например: /quest_what_is_dex → quest_id = "what_is_dex"
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажи ID квеста", parse_mode=ParseMode.HTML)
        return
    
    quest_id = "_".join(context.args)  # На случай, если ID содержит подчеркивания
    
    # Проверяем, существует ли такой квест
    if quest_id not in DAILY_QUESTS:
        await update.message.reply_text(f"❌ Квест '{quest_id}' не найден", parse_mode=ParseMode.HTML)
        return
    
    # Запускаем квест
    await start_quest(update, context, quest_id)


@log_command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение с интерактивными кнопками."""
    user = update.effective_user
    save_user(user.id, user.username or "", user.first_name)
    
    is_banned, ban_reason = check_user_banned(user.id)
    if is_banned:
        await update.message.reply_text(
            f"⛔ <b>Вы заблокированы</b>\n\nПричина: <i>{ban_reason or 'Не указана'}</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Получаем информацию о лимитах
    can_request, remaining = check_daily_limit(user.id)
    if user.id in ADMIN_USERS:
        limits_text = f"⚡ <b>Твой лимит:</b> <i>БЕЗЛИМИТНЫЙ (Admin)</i>"
    else:
        limits_text = f"⚡ <b>Твой лимит:</b> <i>{remaining}/{MAX_REQUESTS_PER_DAY} запросов</i>"
    
    welcome_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"👋 Привет, {user.first_name}!\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        
        f"🤖 <b>RVX AI v0.11.0</b>\n"
        f"Твой AI-помощник в крипто, Web3, AI и новых технологиях\n\n"
        
        f"<b>Что я делаю:</b>\n"
        f"📰 Анализирую новости простым языком\n"
        f"🎓 Учу: Криптовалюты • Web3 • AI • Трейдинг • DeFi • NFT\n"
        f"🏆 Даю награды за обучение и активность\n\n"
        
        f"<b>Мои возможности:</b>\n"
        f"• 3 полных интерактивных курса\n"
        f"• XP система & 6 бейджей за достижения\n"
        f"• Лидерборд TOP-10 по знаниям\n"
        f"• 5 ежедневных задач с бонусами\n\n"
        
        f"{limits_text}\n\n"
        
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>С чего хочешь начать?</b>\n"
        f"<b>⬇️</b>\n"
    )
    
    if MANDATORY_CHANNEL_ID:
        welcome_text += f"\n📢 Подпишись: {MANDATORY_CHANNEL_LINK}"
    
    # Интерактивные кнопки основных функций (v0.11.0 с задачами)
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
            InlineKeyboardButton("📋 Задачи", callback_data="start_tasks"),
            InlineKeyboardButton("❓ Помощь", callback_data="start_help")
        ],
        [
            InlineKeyboardButton("📦 Дропы", callback_data="start_drops"),
            InlineKeyboardButton("🔥 Активности", callback_data="start_activities")
        ],
        [
            InlineKeyboardButton("📜 История", callback_data="start_history"),
            InlineKeyboardButton("⚙️ Меню", callback_data="start_menu")
        ]
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь по использованию."""
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    help_text = (
        "📖 <b>ИНСТРУКЦИЯ RVX BOT v0.7.0</b>\n\n"
        "<b>✨ ДВА ОСНОВНЫХ РЕЖИМА:</b>\n"
        "<b>1. Анализ новостей:</b>\n"
        "   • Отправь текст криптоновости\n"
        "   • Получи объяснение и ключевые пункты\n"
        "   • Оцени ответ (👍/👎)\n\n"
        "<b>2. 🎓 Интерактивное обучение (НОВОЕ!):</b>\n"
        "   • /teach &lt;тема&gt; [уровень]\n"
        "   • 8 тем: crypto_basics, trading, web3, ai, defi, nft, security, tokenomics\n"
        "   • 4 уровня: beginner 🌱, intermediate 📚, advanced 🚀, expert 💎\n\n"
        "<b>📚 КОМАНДЫ:</b>\n"
        "• /teach — интерактивный учитель по крипто, AI, Web3, трейдингу\n"
        "• /learn — интерактивные курсы\n"
        "• /lesson — продолжить урок\n"
        "• /stats — твоя статистика (XP, бейджи, прогресс)\n"
        "• /history — последние 10 анализов\n"
        "• /search &lt;текст&gt; — поиск в истории\n"
        "• /export — экспорт истории\n"
        "• /limits — твои лимиты\n"
        "• /menu — быстрые действия\n\n"
        f"⚡ <b>ТВОИ ЛИМИТЫ:</b>\n"
        f"• {MAX_REQUESTS_PER_DAY} запросов в день\n"
        f"• {FLOOD_COOLDOWN_SECONDS}с между запросами\n"
        f"• Макс. длина текста: {MAX_INPUT_LENGTH} символов\n\n"
        "🎓 <b>ПРИМЕРЫ /teach:</b>\n"
        "• /teach crypto_basics — основы (новичок)\n"
        "• /teach trading beginner — трейдинг для новичков\n"
        "• /teach web3 advanced — Web3 продвинутый\n"
        "• /teach defi expert — DeFi эксперт\n\n"
        "❓ <b>Проблемы?</b> Напиши администратору"
    )
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 <b>Официальный канал:</b>\n{MANDATORY_CHANNEL_LINK}"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
    ]
    
    try:
        if is_callback and query:
            await query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке справки: {e}")


@log_command
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику."""
    user_id = update.effective_user.id
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
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"  • Минимум: <b>{FLOOD_COOLDOWN_SECONDS}с</b> между запросами\n\n"
        f"<b>📏 ОГРАНИЧЕНИЯ ТЕКСТА:</b>\n"
        f"  • Максимум: <b>{MAX_INPUT_LENGTH}</b> символов\n\n"
    )
    
    if not can_request:
        limits_text += "⚠️ <b>ЛИМИТ ИСЧЕРПАН!</b>\n<i>Попробуйте завтра.</i>"
    
    await update.message.reply_text(limits_text, parse_mode=ParseMode.HTML)

# ============= НОВЫЕ КОМАНДЫ v0.5.0 - ОБУЧЕНИЕ =============

@log_command
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список доступных курсов для обучения."""
    user = update.effective_user
    user_id = user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    save_user(user_id, user.username or "", user.first_name)
    
    # Получаем уровень пользователя
    with get_db() as conn:
        cursor = conn.cursor()
        knowledge_level = get_user_knowledge_level(cursor, user_id)
        level, xp = calculate_user_level_and_xp(cursor, user_id)
    
    learn_text = (
        "📚 <b>КРИПТОВАЛЮТНАЯ АКАДЕМИЯ RVX v0.5.0</b>\n\n"
        f"👤 <b>Ваш уровень:</b> Level {level} ({xp} XP)\n"
        f"<b>Знания:</b> {knowledge_level}\n\n"
        "<b>🎓 ДОСТУПНЫЕ КУРСЫ:</b>\n\n"
    )
    
    # Показываем все курсы
    for course_key, course_data in COURSES_DATA.items():
        learn_text += (
            f"<b>{course_data['title']}</b> <i>({course_data['level'].upper()})</i>\n"
            f"  • {course_data['description']}\n"
            f"  • Уроков: {course_data['total_lessons']} | XP: {course_data['total_xp']}\n"
            f"  • Начать: <code>/start_{course_key}</code>\n\n"
        )
    
    learn_text += (
        "💡 <b>Совет:</b> Начните с Blockchain Basics если новичок!\n"
        "Используйте <code>/lesson 1</code> чтобы начать первый урок."
    )
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
    ]
    
    try:
        if is_callback and query:
            await query.edit_message_text(learn_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(learn_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при отправке learn: {e}")
        # Fallback
        try:
            fallback_text = f"📚 Криптовалютная академия\n\nУровень: Level {level} ({xp} XP)"
            if is_callback and query:
                await query.edit_message_text(fallback_text)
            else:
                await update.message.reply_text(fallback_text)
        except Exception as e2:
            logger.error(f"Ошибка fallback: {e2}")


@log_command
async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if user_id not in user_current_course:
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
    
    course_name = user_current_course[user_id]
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


@log_command
async def start_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_current_course[user_id] = course_name
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
        f"📖 <i>Используй команду <code>/lesson 1</code> чтобы начать первый урок</i>"
    )
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)
    
    # Логируем событие
    if ENABLE_ANALYTICS:
        log_analytics_event("course_started", user_id, {"course": course_name})


@log_command
async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def bookmark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Просмотреть все закладки: <code>/bookmarks</code>",
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
async def bookmarks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает сохраненные в закладках инструменты."""
    user_id = update.effective_user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем закладки пользователя
            cursor.execute(
                "SELECT tool_name FROM user_bookmarks WHERE user_id = ? ORDER BY added_at DESC",
                (user_id,)
            )
            
            bookmarks = cursor.fetchall()
        
        if not bookmarks:
            response = (
                "📌 <b>Ваши закладки пусты</b>\n\n"
                "Добавить инструмент: <code>/bookmark Etherscan</code>\n"
                "Посмотреть инструменты: <code>/tools</code>"
            )
        else:
            response = "📌 <b>ВАШИ ЗАКЛАДКИ</b>\n\n"
            
            # Получаем информацию о каждом инструменте
            all_tools = get_all_tools_db()
            tools_by_name = {t['name']: t for t in all_tools}
            
            for (tool_name,) in bookmarks:
                tool = tools_by_name.get(tool_name)
                if tool:
                    response += (
                        f"🔧 <b>{tool['name']}</b>\n"
                        f"   <i>{tool['description'][:60]}...</i>\n"
                        f"   Сложность: {tool['difficulty']}\n\n"
                    )
            
            response += f"\n🔗 Просмотреть подробнее: <code>/tools ИмяИнструмента</code>"
        
        try:
            if is_callback and query:
                await query.edit_message_text(response, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при отправке закладок: {e}")
            await update.message.reply_text("❌ Ошибка при получении закладок", parse_mode=ParseMode.HTML)
        
        # Логируем событие
        if ENABLE_ANALYTICS:
            log_analytics_event("bookmarks_viewed", user_id, {"count": len(bookmarks)})
    
    except Exception as e:
        logger.error(f"Ошибка при получении закладок: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении закладок",
            parse_mode=ParseMode.HTML
        )


@log_command
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            except:
                pass  # Вопрос уже в FAQ
        
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
        logger.error(f"❌ Ошибка в /ask: {e}")
        await status_msg.edit_text(
            "❌ Не удалось найти ответ.\n\n"
            "Попробуйте переформулировать вопрос или начните курс `/learn`"
        )


# =============================================================================
# УЧИТЕЛЬСКИЙ МОДУЛЬ v0.7.0 - ИИ ПРЕПОДАЕТ КРИПТО, AI, WEB3, ТРЕЙДИНГ
# =============================================================================

async def _launch_teaching_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, topic: str, difficulty: str, query=None):
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
                InlineKeyboardButton("❓ Еще вопрос", callback_data=f"teach_question_{topic}")
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
        
        # Даем XP за прохождение урока
        with get_db() as conn:
            cursor = conn.cursor()
            add_xp_to_user(cursor, user_id, XP_REWARDS.get('lesson_completed', 50), "completed_teaching_lesson")
        
        if ENABLE_ANALYTICS:
            log_analytics_event("teaching_lesson", user_id, {
                "topic": topic,
                "difficulty": difficulty
            })
        
        logger.info(f"✅ Урок создан для {user_id}: {topic} ({difficulty})")
        
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
        logger.error(f"❌ Ошибка в _launch_teaching_lesson: {e}")
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


@log_command
async def teach_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎓 Интерактивный учитель - показывает красивое меню с кнопками. v0.10.0 - Динамическая сложность."""
    user_id = update.effective_user.id
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    # САМООБУЧЕНИЕ #2: Определяем рекомендуемую сложность автоматически
    with get_db() as conn:
        cursor = conn.cursor()
        _, user_xp = calculate_user_level_and_xp(cursor, user_id)
    
    # Автоматическая рекомендация сложности по XP
    if user_xp < 100:
        recommended_difficulty = "beginner"
        difficulty_hint = "🌱 Рекомендуем начать с основ"
    elif user_xp < 300:
        recommended_difficulty = "intermediate"
        difficulty_hint = "📚 Вы готовы к промежуточному уровню"
    elif user_xp < 600:
        recommended_difficulty = "advanced"
        difficulty_hint = "🚀 Пора учить продвинутые темы"
    else:
        recommended_difficulty = "expert"
        difficulty_hint = "💎 Добро пожаловать на экспертный уровень!"
    
    # Если нет аргументов - показываем интерактивное меню
    if not context.args:
        # Создаем кнопки для выбора темы (2x4 сетка)
        keyboard = []
        topics_list = list(TEACHING_TOPICS.keys())
        
        # Разбиваем на пары для красивого отображения
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
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        menu_text = (
            "🎓 <b>ИНТЕРАКТИВНЫЙ УЧИТЕЛЬ</b>\n\n"
            "Выберите тему для обучения:\n\n"
            f"💡 <i>{difficulty_hint}</i>"
        )
        
        try:
            if is_callback and query:
                await query.edit_message_text(
                    menu_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
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
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def post_to_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        logger.info(f"📢 Админ {update.effective_user.id} отправил пост в канал")
        
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
        logger.error(f"❌ Ошибка отправки поста в канал: {e}")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Неожиданная ошибка: {e}"
        )
        logger.error(f"❌ Неожиданная ошибка при отправке поста: {e}")


async def notify_version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        logger.info(f"📢 Админ {update.effective_user.id} отправил уведомление об обновлении v{version}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"❌ Ошибка отправки уведомления: {e}")


async def notify_quests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        logger.info(f"📢 Админ {update.effective_user.id} отправил уведомление о квестах")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"❌ Ошибка отправки уведомления о квестах: {e}")


async def notify_milestone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        logger.info(f"📢 Админ {update.effective_user.id} отправил уведомление о вехе")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"❌ Ошибка отправки уведомления о вехе: {e}")


# =============================================================================
# CALLBACK ОБРАБОТЧИК
# =============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline кнопок."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
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
        quest_id = data.replace("start_test_", "")
        if quest_id in DAILY_QUESTS:
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
            logger.error(f"❌ Ошибка парсинга ответа: {e}")
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
            logger.error(f"❌ Ошибка парсинга next_q: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
            return
    
    # Показать результаты
    if data.startswith("show_quests"):
        await tasks_command(update, context)
        return
    
    # ============ СТАРЫЕ CALLBACKS (совместимость) ============
    if data.startswith("start_"):
        action = "_".join(parts[1:])
        
        if action == "teach":
            await teach_command(update, context)
            return
        elif action == "learn":
            await learn_command(update, context)
            return
        elif action == "stats":
            await stats_command(update, context)
            return
        elif action == "leaderboard":
            await stats_command(update, context)
            return
        elif action == "drops":
            await drops_command(update, context)
            return
        elif action == "activities":
            await activities_command(update, context)
            return
            return
        elif action == "tasks":
            await tasks_command(update, context)
            return
        elif action == "help":
            await help_command(update, context)
            return
        elif action == "history":
            await history_command(update, context)
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
                InlineKeyboardButton("📋 Задачи", callback_data="start_tasks"),
                InlineKeyboardButton("❓ Помощь", callback_data="start_help")
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
                logger.info(f"✅ Пользователь {user.id} начал урок {course} #{lesson}")
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
        
        keyboard.append([InlineKeyboardButton("⬅️ Другие темы", callback_data="teach_menu")])
        
        try:
            await query.edit_message_text(
                "🎓 <b>ИНТЕРАКТИВНЫЙ УЧИТЕЛЬ</b>\n\n"
                "Выберите тему для обучения:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка в teach_menu: {e}")
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
        
        # Показываем красивое сообщение
        keyboard = [
            [InlineKeyboardButton("📚 Другая тема", callback_data="teach_menu")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
        return
    
    if data.startswith("teach_question_"):
        topic = data.replace("teach_question_", "")
        
        keyboard = [
            [InlineKeyboardButton("💬 Используй /ask для уточнений", url="https://t.me/dummy")],
            [InlineKeyboardButton("📚 Другая тема", callback_data="teach_menu")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
        ]
        
        try:
            await query.edit_message_text(
                "💬 <b>УТОЧНЯЮЩИЕ ВОПРОСЫ</b>\n\n"
                "Используйте команду <code>/ask [ваш вопрос]</code> чтобы задать уточняющий вопрос!\n\n"
                "<i>Пример:</i> <code>/ask Как это работает с другими блокчейнами?</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
        return
    
    # ============ ОРИГИНАЛЬНЫЕ КНОПКИ ============
    
    try:
        request_id = int(parts[-1])
        action = "_".join(parts[:-1])
    except (ValueError, IndexError):
        logger.error(f"❌ Ошибка парсинга callback: {data}")
        await query.message.reply_text("❌ Ошибка обработки кнопки")
        return
    
    # Обработка фидбека "Полезно"
    if action == "feedback_helpful":
        save_feedback(user.id, request_id, is_helpful=True)
        
        # Обновляем ежедневную задачу по рейтингу (v0.11.0)
        update_task_progress(user.id, "voting_3", 1)
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "✅ Спасибо за отзыв! Рад, что помог 🙂"
        )
        
        if user.id in user_last_news:
            del user_last_news[user.id]
        # Сбрасываем счётчик регенераций для этого запроса
        if request_id in feedback_attempts:
            try:
                del feedback_attempts[request_id]
            except KeyError:
                pass
        
        if ENABLE_ANALYTICS:
            log_analytics_event("feedback_positive", user.id, {
                "request_id": request_id
            })
    
    # Обработка фидбека "Не помогло" с регенерацией
    elif action == "feedback_not_helpful":
        save_feedback(user.id, request_id, is_helpful=False)
        
        if ENABLE_ANALYTICS:
            log_analytics_event("feedback_negative", user.id, {
                "request_id": request_id
            })
        
        # Проверяем, есть ли сохраненный текст для регенерации
        if user.id not in user_last_news:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "😔 Попробуйте отправить новость заново для нового анализа."
            )
            return

        original_text = user_last_news[user.id]

        # Подсчитываем попытку регенерации для данного request_id
        attempt = feedback_attempts.get(request_id, 0) + 1
        feedback_attempts[request_id] = attempt

        # Если превысили лимит — эскалируем
        if attempt > FEEDBACK_MAX_RETRIES:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "😓 Похоже, я не смог объяснить иначе. \n"
                "Могу предложить: \n"
                "• Задать уточняющий вопрос командой `/ask` \n"
                "• Обратиться к эксперту — напишите администратору",
                parse_mode=ParseMode.MARKDOWN
            )
            try:
                del feedback_attempts[request_id]
            except KeyError:
                pass
            return

        # Выбираем режим регенерации по попытке
        mode_name, mode_desc = REGENERATION_MODES[min(attempt-1, len(REGENERATION_MODES)-1)]

        await query.edit_message_text(
            f"🔄 Готовлю альтернативное объяснение ({mode_name}) — попытка {attempt}/{FEEDBACK_MAX_RETRIES}"
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

            logger.info(f"✅ Регенерация ({mode_name}) успешна для {user.id} (попытка {attempt})")

        except Exception as e:
            logger.error(f"❌ Ошибка регенерации: {e}")
            await query.edit_message_text(
                "❌ Не удалось создать новый анализ.\n\n"
                "Попробуйте отправить новость заново."
            )

    # ============ TEACHING CALLBACKS v0.7.0 ============
    
    # Меню выбора тем обучения

# =============================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# =============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик текстовых сообщений."""
    user = update.effective_user
    user_text = update.message.text
    
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
    if not check_flood(user.id):
        await update.message.reply_text(
            f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS} секунд между запросами"
        )
        return
    
    # Валидация длины текста
    if len(user_text) > MAX_INPUT_LENGTH:
        await update.message.reply_text(
            f"❌ Текст слишком длинный\n\n"
            f"Максимум: {MAX_INPUT_LENGTH} символов\n"
            f"У вас: {len(user_text)} символов"
        )
        return
    
    if len(user_text.strip()) < 10:
        await update.message.reply_text(
            "❌ Текст слишком короткий\n\n"
            "Отправьте хотя бы 10 символов."
        )
        return
    
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
        user_last_news[user.id] = user_text
        
        # Обновляем ежедневную задачу по анализу новостей (v0.11.0)
        update_task_progress(user.id, "news_5", 1)
        
        # Кнопки фидбека
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        # Добавляем кнопки обучения и меню
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
    status_msg = await update.message.reply_text("⏳ Анализирую новость...")
    
    try:
        # Вызов API с retry логикой
        simplified_text, proc_time, error = await call_api_with_retry(user_text, user_id=user.id)
        
        if not simplified_text:
            # Сохраняем неудачный запрос
            save_request(
                user.id,
                user_text,
                "",
                from_cache=False,
                processing_time_ms=proc_time,
                error_message=error
            )
            
            raise ValueError(f"API ошибка: {error}")
        
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
        user_last_news[user.id] = user_text
        
        # Обновляем ежедневную задачу по анализу новостей (v0.11.0)
        update_task_progress(user.id, "news_5", 1)
        
        # Кнопки фидбека
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        
        # Просто отправляем ответ от API как есть (он уже полностью отформатирован)
        full_response = f"<b>📰 RVX АНАЛИЗ</b>\n\n{simplified_text}"
        
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
        
        logger.info(f"✅ Запрос успешно обработан для {user.id} за {proc_time:.0f}ms")
        
        # Уведомление об оставшихся запросах
        if remaining <= 5:
            await update.message.reply_text(
                f"💡 Осталось запросов сегодня: {remaining - 1}"
            )
    
    except httpx.TimeoutException:
        logger.error(f"⏱️ Таймаут для {user.id}")
        await status_msg.edit_text(
            "❌ <b>Превышено время ожидания</b>\n\n"
            "AI сервис не ответил вовремя.\n"
            "Попробуйте через минуту.",
            parse_mode=ParseMode.HTML
        )
    
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP ошибка для {user.id}: {e}")
        await status_msg.edit_text(
            f"❌ <b>Ошибка API (HTTP {e.response.status_code})</b>\n\n"
            "AI сервис временно недоступен.\n"
            "Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка для {user.id}: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ <b>Произошла ошибка</b>\n\n"
            "Попробуйте отправить новость заново.\n"
            "Если проблема повторяется, свяжитесь с администратором.",
            parse_mode=ParseMode.HTML
        )

# =============================================================================
# ФОНОВЫЕ ЗАДАЧИ
# =============================================================================

async def periodic_cache_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая очистка старого кэша."""
    if ENABLE_AUTO_CACHE_CLEANUP:
        logger.info("🧹 Запуск автоматической очистки кэша...")
        try:
            cleanup_old_cache()
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")

# =============================================================================
# ОБРАБОТКА ОШИБОК
# =============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок с восстановлением после сетевых ошибок."""
    error = context.error
    
    # Логируем ошибку
    logger.error(f"❌ Необработанная ошибка: {error}", exc_info=error)
    
    # Не отправляем сообщение об ошибке для сетевых проблем
    if isinstance(error, (TelegramError, TimedOut, NetworkError)):
        logger.warning(f"⚠️ Сетевая ошибка Telegram: {type(error).__name__}")
        return  # Пропускаем отправку уведомления при сетевых ошибках
    
    # Для других ошибок пытаемся отправить уведомление
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка.\n\n"
                "Пожалуйста, попробуйте позже."
            )
        except (TelegramError, TimedOut, NetworkError) as e:
            logger.warning(f"⚠️ Не удалось отправить ошибку: {e}")
            pass  # Не можем отправить сообщение

# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Запуск бота."""
    # Проверка обязательных переменных
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN не найден в .env!")
        return
    
    if not API_URL_NEWS:
        logger.critical("❌ API_URL_NEWS не найден в .env!")
        return
    
    # Инициализация БД
    init_database()
    
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
    
    async def drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            logger.error(f"❌ Ошибка при получении дропов: {e}")
            await status_msg.edit_text(f"❌ Ошибка при загрузке дропов: {str(e)[:100]}")
    
    async def activities_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            logger.error(f"❌ Ошибка при получении активностей: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    
    async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            logger.error(f"❌ Ошибка при получении трендов: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    
    async def subscribe_drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    async def my_subscriptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            logger.error(f"❌ Ошибка при получении подписок: {e}")
            await update.message.reply_text("❌ Ошибка при получении подписок")
    
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
                BotCommand("menu", "⚙️ Быстрое меню"),
            ])
            logger.info("✅ Список команд установлен в Telegram")
        except Exception as e:
            logger.error(f"❌ Ошибка при установке команд: {e}")
    
    # Регистрация команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("stats", stats_command))
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
    
    # НОВАЯ КОМАНДА v0.11.0 - Ежедневные задачи
    application.add_handler(CommandHandler("tasks", tasks_command))
    
    # НОВАЯ КОМАНДА v0.12.0 - Динамические команды квестов (quest_what_is_dex, quest_what_is_staking и т.д.)
    quest_ids = list(DAILY_QUESTS.keys())
    quest_commands = [f"quest_{qid}" for qid in quest_ids]
    application.add_handler(CommandHandler(quest_commands, quest_command))
    
    # Динамические команды для запуска курсов (start_blockchain_basics, start_defi_contracts, etc.)
    application.add_handler(CommandHandler(["start_blockchain_basics", "start_defi_contracts", "start_scaling_dao"], start_course_command))
    
    # Админские команды
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
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
        logger.info("✅ Автоматическая очистка кэша настроена (каждые 6ч)")
    
    # Установка списка команд при запуске бота
    job_queue.run_once(set_commands_on_start, when=1)  # Запускаем через 1 секунду после старта
    
    # Запуск
    logger.info("🟢 Бот запущен и готов к работе!")
    logger.info("=" * 70)
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Пропускаем старые обновления при перезапуске
        )
    except KeyboardInterrupt:
        logger.info("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        logger.info("👋 Бот остановлен")

if __name__ == '__main__':
    main()
