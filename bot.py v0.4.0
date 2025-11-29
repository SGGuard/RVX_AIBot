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
    """Миграция базы данных к новой схеме."""
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
    """Инициализация базы данных с расширенной схемой."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
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
        
        logger.info("✅ База данных инициализирована (v0.4.0)")
    
    # Выполняем миграцию существующих таблиц
    migrate_database()

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
    """Проверяет дневной лимит запросов. Возвращает (можно_ли, оставшиеся_запросы)."""
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
    """Удаляет старый кэш."""
    with get_db() as conn:
        cursor = conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=CACHE_MAX_AGE_DAYS)
        cursor.execute("""
            DELETE FROM cache 
            WHERE last_used_at < ? AND hit_count < 5
        """, (cutoff_date,))
        deleted = cursor.rowcount
        logger.info(f"🗑️ Удалено {deleted} старых записей из кэша")

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

async def call_api_with_retry(news_text: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Вызывает API с повторными попытками.
    Возвращает (response_text, processing_time_ms, error_message)
    """
    start_time = datetime.now()
    last_error = None
    
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"🔄 API попытка {attempt}/{API_RETRY_ATTEMPTS}")
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(
                    API_URL_NEWS,
                    json={"text_content": news_text}
                )
                response.raise_for_status()
                api_response = response.json()
                
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Невалидный ответ от API")
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(f"✅ API успех за {processing_time:.0f}ms (попытка {attempt})")
                
                return simplified_text, processing_time, None
        
        except httpx.TimeoutException:
            last_error = f"Таймаут ({API_TIMEOUT}s)"
            logger.warning(f"⏱️ Таймаут на попытке {attempt}")
        
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            logger.error(f"❌ HTTP ошибка на попытке {attempt}: {e}")
        
        except Exception as e:
            last_error = str(e)
            logger.error(f"❌ Ошибка на попытке {attempt}: {e}")
        
        # Ждем перед следующей попыткой (кроме последней)
        if attempt < API_RETRY_ATTEMPTS:
            await asyncio.sleep(API_RETRY_DELAY * attempt)
    
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
            f"⛔ Вы заблокированы\n\nПричина: {ban_reason or 'Не указана'}"
        )
        return
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🤖 **RVX AI Analyzer v0.4.0**\n\n"
        "Я помогаю понять сложные криптоновости простым языком.\n\n"
        "📋 **Основные команды:**\n"
        "• Просто отправь текст новости\n"
        "• /help — полная инструкция\n"
        "• /history — твоя история\n"
        "• /stats — статистика\n\n"
        f"💡 Лимит: {MAX_REQUESTS_PER_DAY} запросов/день"
    )
    
    if MANDATORY_CHANNEL_ID:
        welcome_text += f"\n\n📢 Обязательная подписка:\n{MANDATORY_CHANNEL_LINK}"
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь по использованию."""
    help_text = (
        "📖 **Инструкция по использованию**\n\n"
        "**Как работает:**\n"
        "1️⃣ Отправь текст криптоновости\n"
        "2️⃣ Получи понятное объяснение\n"
        "3️⃣ Оцени ответ (👍/👎)\n\n"
        "**Команды:**\n"
        "• /start — приветствие\n"
        "• /help — эта справка\n"
        "• /stats — статистика\n"
        "• /history — последние 10 анализов\n"
        "• /search <текст> — поиск в истории\n"
        "• /export — экспорт истории\n"
        "• /limits — твои лимиты\n\n"
        f"⚡ **Лимиты:**\n"
        f"• {MAX_REQUESTS_PER_DAY} запросов в день\n"
        f"• {FLOOD_COOLDOWN_SECONDS}с между запросами\n"
        f"• Макс. длина: {MAX_INPUT_LENGTH} символов\n\n"
        "❓ **Проблемы?** Напиши администратору"
    )
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 Канал: {MANDATORY_CHANNEL_LINK}"
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@log_command
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику."""
    user_id = update.effective_user.id
    
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
        "📊 **Статистика RVX v0.4.0**\n\n"
        f"👤 **Твоя статистика:**\n"
        f"• Всего запросов: {user_requests}\n"
        f"• Сегодня: {daily_requests}/{MAX_REQUESTS_PER_DAY}\n"
        f"• С нами с: {member_since[:10]}\n\n"
        f"🌐 **Глобальная:**\n"
        f"• 👥 Пользователей: {stats['total_users']}\n"
        f"• 📝 Запросов: {stats['total_requests']}\n"
        f"• 💾 Кэш: {stats['cache_size']} записей\n"
        f"• ⚡ Попадания в кэш: {stats['cache_hits']}\n"
        f"• ⏱️ Среднее время: {stats['avg_processing_time']}ms\n"
        f"• 👍 Полезно: {stats['helpful']}\n"
        f"• 👎 Не помогло: {stats['not_helpful']}\n\n"
        f"🏆 **ТОП пользователей:**\n"
    )
    
    for i, (username, first_name, requests) in enumerate(stats['top_users'], 1):
        name = username or first_name or "Аноним"
        stats_text += f"{i}. {name}: {requests} запросов\n"
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

@log_command
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает историю запросов."""
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=10)
    
    if not history:
        await update.message.reply_text("📜 История пуста. Отправь первую новость!")
        return
    
    response = "📜 **Последние 10 анализов:**\n\n"
    
    for i, (news, _, created_at, from_cache, proc_time) in enumerate(history, 1):
        news_preview = news[:60] + "..." if len(news) > 60 else news
        icon = "⚡" if from_cache else "🆕"
        time_str = f"{proc_time:.0f}ms" if proc_time else "—"
        
        response += (
            f"{i}. {icon} {news_preview}\n"
            f"   🕐 {created_at[:16]} | ⏱️ {time_str}\n\n"
        )
    
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

@log_command
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск по истории запросов."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите текст для поиска\n\n"
            "Пример: /search биткоин"
        )
        return
    
    search_text = " ".join(context.args)
    results = search_user_requests(user_id, search_text)
    
    if not results:
        await update.message.reply_text(
            f"🔍 Ничего не найдено по запросу: **{search_text}**",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    response = f"🔍 **Найдено {len(results)} результатов:**\n\n"
    
    for i, (news, _, created_at) in enumerate(results[:5], 1):
        news_preview = news[:70] + "..."
        response += f"{i}. {news_preview}\n   🕐 {created_at[:16]}\n\n"
    
    if len(results) > 5:
        response += f"_...и еще {len(results) - 5} результатов_"
    
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

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
    
    limits_text = (
        f"{status_emoji} **Ваши лимиты**\n\n"
        f"📊 **Дневной лимит:**\n"
        f"• Использовано: {daily_used}/{MAX_REQUESTS_PER_DAY}\n"
        f"• Осталось: {remaining}\n"
        f"• Сброс через: {reset_str}\n\n"
        f"⏱️ **Flood control:**\n"
        f"• Минимум {FLOOD_COOLDOWN_SECONDS}с между запросами\n\n"
        f"📏 **Лимиты текста:**\n"
        f"• Максимум {MAX_INPUT_LENGTH} символов\n\n"
    )
    
    if not can_request:
        limits_text += "⚠️ **Дневной лимит исчерпан!**\nПопробуйте завтра."
    
    await update.message.reply_text(limits_text, parse_mode=ParseMode.MARKDOWN)

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
    
    # Парсинг callback_data: action_requestid
    parts = data.split("_")
    
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
        
        await query.edit_message_text(
            "🔄 Анализирую иначе... (попытка 2)"
        )
        
        try:
            # Вызываем API заново для регенерации
            simplified_text, proc_time, error = await call_api_with_retry(original_text)
            
            if not simplified_text:
                raise ValueError(f"Ошибка API: {error}")
            
            # Сохраняем новый запрос
            new_request_id = save_request(
                user.id, 
                original_text, 
                simplified_text, 
                from_cache=False,
                processing_time_ms=proc_time
            )
            
            # Отправляем новый ответ с кнопками
            new_response = f"🤖 **RVX Скаут (попытка 2):**\n\n{simplified_text}"
            
            keyboard = [
                [
                    InlineKeyboardButton(
                        "👍 Полезно", 
                        callback_data=f"feedback_helpful_{new_request_id}"
                    ),
                    InlineKeyboardButton(
                        "👎 Не помогло", 
                        callback_data=f"feedback_not_helpful_{new_request_id}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                new_response,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Регенерация успешна для {user.id}")
        
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
        
        await update.message.reply_text(
            f"⚡ **Из кэша:**\n\n{cached_response}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
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
        simplified_text, proc_time, error = await call_api_with_retry(user_text)
        
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
        
        # Отправляем результат
        await status_msg.edit_text(
            f"🤖 **RVX Скаут:**\n\n{simplified_text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
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
            "❌ **Превышено время ожидания**\n\n"
            "AI сервис не ответил вовремя.\n"
            "Попробуйте через минуту.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP ошибка для {user.id}: {e}")
        await status_msg.edit_text(
            f"❌ **Ошибка API (HTTP {e.response.status_code})**\n\n"
            "AI сервис временно недоступен.\n"
            "Попробуйте позже.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка для {user.id}: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ **Произошла ошибка**\n\n"
            "Попробуйте отправить новость заново.\n"
            "Если проблема повторяется, свяжитесь с администратором.",
            parse_mode=ParseMode.MARKDOWN
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
    """Глобальный обработчик ошибок."""
    logger.error(f"❌ Необработанная ошибка: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка.\n\n"
                "Команда уже уведомлена."
            )
        except TelegramError:
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
    logger.info("🚀 RVX Telegram Bot v0.4.0 запускается...")
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
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("limits", limits_command))
    
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
