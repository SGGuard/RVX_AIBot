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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    get_next_lesson_info, build_user_context_prompt, get_user_course_summary
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
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "50"))

# Обязательная подписка
MANDATORY_CHANNEL_ID = os.getenv("MANDATORY_CHANNEL_ID", "")
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "")

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
                badges TEXT DEFAULT '[]'
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
        
        # Индексы для производительности
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_user_id 
            ON requests(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_created_at 
            ON requests(created_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_last_used 
            ON cache(last_used_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_progress_user
            ON user_progress(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_questions_user
            ON user_questions(user_id)
        """)
        
        logger.info("✅ База данных инициализирована (v0.5.0)")
    
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
    # Администраторы имеют безлимитный доступ
    if user_id in ADMIN_USERS:
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
        
        cursor.execute("""
            SELECT username, first_name, total_requests
            FROM users
            WHERE is_banned = 0
            ORDER BY total_requests DESC
            LIMIT 5
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
    """Валидирует ответ от API."""
    if not isinstance(api_response, dict):
        logger.warning(f"⚠️ API вернул не dict: {type(api_response)}")
        return None
    
    simplified_text = api_response.get("simplified_text")
    
    if not simplified_text or not isinstance(simplified_text, str):
        logger.warning("⚠️ simplified_text отсутствует или не строка")
        return None
    
    simplified_text = simplified_text.strip()
    
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
                    json=request_payload
                )
                response.raise_for_status()
                api_response = response.json()
                
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Невалидный ответ от API")
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(f"✅ API успех за {processing_time:.0f}ms (попытка {attempt})")
                
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
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение."""
    user = update.effective_user
    save_user(user.id, user.username or "", user.first_name)
    
    is_banned, ban_reason = check_user_banned(user.id)
    if is_banned:
        await update.message.reply_text(
            f"⛔ <b>Вы заблокированы</b>\n\nПричина: <i>{ban_reason or 'Не указана'}</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        "🤖 <b>RVX AI ANALYZER v0.5.0</b>\n\n"
        "<i>Я помогаю понять сложные криптоновости простым языком.</i>\n\n"
        "<b>⚡ БЫСТРЫЙ СТАРТ:</b>\n"
        "  1️⃣ Просто отправь текст новости\n"
        "  2️⃣ Получи понятное объяснение\n"
        "  3️⃣ Оцени результат 👍 или 👎\n\n"
        "<b>📋 КОМАНДЫ:</b>\n"
        "  • /help — полная инструкция\n"
        "  • /history — твоя история\n"
        "  • /stats — статистика\n"
        "  • /menu — меню действий\n\n"
        f"💡 <b>Твой лимит:</b> {MAX_REQUESTS_PER_DAY} запросов в день"
    )
    
    if MANDATORY_CHANNEL_ID:
        welcome_text += f"\n\n📢 <b>Официальный канал:</b>\n{MANDATORY_CHANNEL_LINK}"
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь по использованию."""
    is_callback = update.callback_query is not None
    query = update.callback_query if is_callback else None
    
    help_text = (
        "📖 <b>ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ</b>\n\n"
        "<b>✨ Как работает:</b>\n"
        "1️⃣ Отправь текст криптоновости\n"
        "2️⃣ Получи понятное объяснение\n"
        "3️⃣ Оцени ответ (👍/👎)\n\n"
        "<b>⚙️ КОМАНДЫ:</b>\n"
        "• /start — приветствие\n"
        "• /help — эта справка\n"
        "• /stats — статистика\n"
        "• /history — последние 10 анализов\n"
        "• /search &lt;текст&gt; — поиск в истории\n"
        "• /export — экспорт истории\n"
        "• /limits — твои лимиты\n"
        "• /menu — быстрые действия\n\n"
        f"⚡ <b>ТВОИ ЛИМИТЫ:</b>\n"
        f"• {MAX_REQUESTS_PER_DAY} запросов в день\n"
        f"• {FLOOD_COOLDOWN_SECONDS}с между запросами\n"
        f"• Макс. длина текста: {MAX_INPUT_LENGTH} символов\n\n"
        "❓ <b>Проблемы?</b> Напиши администратору"
    )
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 <b>Официальный канал:</b>\n{MANDATORY_CHANNEL_LINK}"
    
    try:
        if is_callback and query:
            await query.edit_message_text(help_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
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
            SELECT total_requests, daily_requests, created_at 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        user_requests = row[0] if row else 0
        daily_requests = row[1] if row else 0
        member_since = row[2] if row else "Неизвестно"
    
    stats = get_global_stats()
    
    stats_text = (
        "📊 <b>СТАТИСТИКА RVX v0.5.0</b>\n\n"
        "<b>👤 ТВОЯ СТАТИСТИКА:</b>\n"
        f"  • Всего запросов: <b>{user_requests}</b>\n"
        f"  • Сегодня: <b>{daily_requests}/{MAX_REQUESTS_PER_DAY}</b>\n"
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
    
    for i, (username, first_name, requests) in enumerate(stats['top_users'], 1):
        name = username or first_name or "Аноним"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        stats_text += f"  {medal} {name}: <b>{requests}</b> запросов\n"
    
    try:
        if is_callback and query:
            await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
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
    
    try:
        if is_callback and query:
            await query.edit_message_text(response, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
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
    
    try:
        if is_callback and query:
            await query.edit_message_text(learn_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(learn_text, parse_mode=ParseMode.HTML)
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
    parts = data.split("_")
    
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
        
        # Кнопки фидбека
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        # Добавляем кнопку меню
        keyboard.append([
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
        
        # Кнопки фидбека
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        
        # Рекомендуем связанные уроки и практические советы (v0.5.0)
        educational_context, learn_callback, practical_tips = get_educational_context(simplified_text, user.id)
        
        # Улучшенное форматирование ответа
        full_response = f"<b>📰 RVX АНАЛИЗ</b>\n\n{simplified_text}"
        
        # Добавляем практические советы
        if practical_tips and any(t.strip() for t in practical_tips):
            full_response += "\n\n💡 <b>ПРАКТИЧЕСКИЕ СОВЕТЫ:</b>"
            for i, tip in enumerate(practical_tips[:3], 1):
                if tip.strip():
                    full_response += f"\n  {i}. {tip}"
        
        # Добавляем образовательные рекомендации если есть
        if educational_context and educational_context.strip():
            full_response += f"\n\n📚 <b>ОБРАЗОВАТЕЛЬНО:</b>\n{educational_context}"
            keyboard.append([
                InlineKeyboardButton("📚 Начать урок", callback_data=learn_callback),
                InlineKeyboardButton("💬 Задать вопрос", callback_data=f"ask_related_{request_id}")
            ])
        
        # Добавляем кнопку меню внизу
        keyboard.append([
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
    logger.info("🚀 RVX Telegram Bot v0.5.0 запускается...")
    logger.info("=" * 70)
    logger.info(f"📊 Конфигурация:")
    logger.info(f"  • API URL: {API_URL_NEWS}")
    logger.info(f"  • Max input: {MAX_INPUT_LENGTH} символов")
    logger.info(f"  • Daily limit: {MAX_REQUESTS_PER_DAY} запросов")
    logger.info(f"  • Flood control: {FLOOD_COOLDOWN_SECONDS}с")
    logger.info(f"  • Admin users: {len(ADMIN_USERS)}")
    logger.info(f"  • Mandatory channel: {'Да' if MANDATORY_CHANNEL_ID else 'Нет'}")
    logger.info(f"  • Analytics: {'Включена' if ENABLE_ANALYTICS else 'Выключена'}")
    logger.info("=" * 70)
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
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
    
    # Динамические команды для запуска курсов (start_blockchain_basics, start_defi_contracts, etc.)
    application.add_handler(CommandHandler(["start_blockchain_basics", "start_defi_contracts", "start_scaling_dao"], start_course_command))
    
    # Админские команды
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("ban", ban_user_command))
    application.add_handler(CommandHandler("unban", unban_user_command))
    application.add_handler(CommandHandler("clear_cache", clear_cache_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Обработчики
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Фоновые задачи
    if ENABLE_AUTO_CACHE_CLEANUP:
        job_queue = application.job_queue
        # Очистка кэша каждые 6 часов
        job_queue.run_repeating(
            periodic_cache_cleanup,
            interval=21600,  # 6 часов
            first=10  # Первый запуск через 10 секунд
        )
        logger.info("✅ Автоматическая очистка кэша настроена (каждые 6ч)")
    
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
