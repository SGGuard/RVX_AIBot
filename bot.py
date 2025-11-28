import os
import logging
import json
import httpx
import hashlib
import sqlite3
from typing import Optional, List, Tuple
from datetime import datetime
from contextlib import contextmanager

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError

# --- 1. Настройка окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0")) # Увеличил таймаут
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MANDATORY_CHANNEL_ID = os.getenv("MANDATORY_CHANNEL_ID", "")
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "")

DB_PATH = "rvx_bot.db"

# --- 2. Логирование ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3. База данных ---

@contextmanager
def get_db():
    """Context manager для работы с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB ошибка: {e}")
        raise
    finally:
        conn.close()

def init_database():
    """Инициализация базы данных."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_requests INTEGER DEFAULT 0,
                last_request_at TIMESTAMP
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
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                request_id INTEGER,
                is_helpful BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (request_id) REFERENCES requests(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            )
        """)
        
        logger.info("✅ База данных инициализирована")

def save_user(user_id: int, username: str, first_name: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))

def increment_user_requests(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET total_requests = total_requests + 1,
                last_request_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))

def save_request(user_id: int, news_text: str, response_text: str, from_cache: bool) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text, from_cache)
            VALUES (?, ?, ?, ?)
        """, (user_id, news_text, response_text, from_cache))
        return cursor.lastrowid

def save_feedback(user_id: int, request_id: int, is_helpful: bool):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful)
            VALUES (?, ?, ?)
        """, (user_id, request_id, is_helpful))

def get_cache(cache_key: str) -> Optional[str]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT response_text FROM cache WHERE cache_key = ?
        """, (cache_key,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?
            """, (cache_key,))
            return row[0]
        return None

def set_cache(cache_key: str, response_text: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cache (cache_key, response_text)
            VALUES (?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_text = excluded.response_text,
                hit_count = hit_count + 1
        """, (cache_key, response_text))

def get_user_history(user_id: int, limit: int = 5) -> List[Tuple]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT news_text, response_text, created_at, from_cache
            FROM requests
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return cursor.fetchall()

def search_user_requests(user_id: int, search_text: str) -> List[Tuple]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT news_text, response_text, created_at
            FROM requests
            WHERE user_id = ? AND news_text LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id, f"%{search_text}%"))
        return cursor.fetchall()

def get_global_stats() -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM requests")
        total_requests = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cache")
        cache_size = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM feedback WHERE is_helpful = 1")
        helpful_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM feedback WHERE is_helpful = 0")
        not_helpful_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT username, first_name, total_requests
            FROM users
            ORDER BY total_requests DESC
            LIMIT 5
        """)
        top_users = cursor.fetchall()
        
        return {
            "total_users": total_users,
            "total_requests": total_requests,
            "cache_size": cache_size,
            "helpful": helpful_count,
            "not_helpful": not_helpful_count,
            "top_users": top_users
        }

# --- 4. Утилиты ---

user_last_request = {}
user_last_news = {}

def check_flood(user_id: int) -> bool:
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

def get_cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not MANDATORY_CHANNEL_ID:
        return True
    try:
        member = await context.bot.get_chat_member(MANDATORY_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True

def validate_api_response(api_response: dict) -> Optional[str]:
    if not isinstance(api_response, dict):
        return None
    simplified_text = api_response.get("simplified_text")
    if not simplified_text or not isinstance(simplified_text, str):
        return None
    if len(simplified_text) > 4096:
        return simplified_text[:4090] + "..."
    return simplified_text

# --- 5. Команды ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.first_name)
    logger.info(f"Пользователь {user.id} запустил бота")
    
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я RVX AI-аналитик v0.3.0 с базой данных!\n\n"
        "🆕 Новое в этой версии:\n"
        "💾 История анализов (/history)\n"
        "🔍 Поиск (/search)\n"
        "📊 Статистика (/stats)\n"
        "📥 Экспорт данных (/export)\n"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 Инструкция:\n"
        "Отправь текст новости — получи перевод на понятный язык.\n\n"
        "Команды:\n"
        "/start, /help, /stats, /history, /search <текст>, /export"
    )
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 Канал:\n{MANDATORY_CHANNEL_LINK}"
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_requests FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        user_requests = row[0] if row else 0
    
    stats = get_global_stats()
    
    stats_text = (
        "📊 Статистика v0.3.0:\n\n"
        f"👤 Ваши запросы: {user_requests}\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"📝 Всего запросов: {stats['total_requests']}\n"
        f"💾 В кэше: {stats['cache_size']}\n"
        f"👍 Полезно: {stats['helpful']} | 👎 Не помогло: {stats['not_helpful']}\n\n"
        f"🏆 ТОП юзеров:\n"
    )
    for i, (username, first_name, requests) in enumerate(stats['top_users'], 1):
        name = username or first_name or "Анонимный"
        stats_text += f"{i}. {name}: {requests}\n"
    
    await update.message.reply_text(stats_text)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=5)
    
    if not history:
        await update.message.reply_text("📜 История пуста.")
        return
    
    response = "📜 Последние 5 анализов:\n\n"
    for i, (news, _, created_at, from_cache) in enumerate(history, 1):
        news_preview = news[:50] + "..." if len(news) > 50 else news
        icon = "⚡" if from_cache else "🆕"
        response += f"{i}. {icon} {news_preview}\n   🕐 {created_at}\n\n"
    
    await update.message.reply_text(response)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Пример: /search биткоин")
        return
    search_text = " ".join(context.args)
    results = search_user_requests(user_id, search_text)
    
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.")
        return
    
    response = f"🔍 Найдено {len(results)}:\n\n"
    for i, (news, _, created_at) in enumerate(results[:5], 1):
        news_preview = news[:60] + "..."
        response += f"{i}. {news_preview}\n   🕐 {created_at}\n\n"
    await update.message.reply_text(response)

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=100)
    
    if not history:
        await update.message.reply_text("📜 История пуста.")
        return
    
    export_text = f"RVX Export | User: {user_id} | Date: {datetime.now()}\n\n"
    for i, (news, response, created_at, _) in enumerate(history, 1):
        export_text += f"=== Запись #{i} ({created_at}) ===\nВход: {news}\nВыход: {response}\n\n"
    
    from io import BytesIO
    file = BytesIO(export_text.encode('utf-8'))
    file.name = f"rvx_history_{user_id}.txt"
    
    await update.message.reply_document(document=file, caption="📥 Ваш архив")

async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache")
    await update.message.reply_text("🗑️ Кэш очищен!")

# --- 6. Обработчик кнопок (ИСПРАВЛЕННЫЙ) ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline кнопок с защитой от ошибок парсинга."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    # Логика парсинга: ID всегда в конце
    parts = data.split("_")
    try:
        # Берем последний элемент как ID
        request_id = int(parts[-1])
        # Всё, что до последнего элемента - это действие
        action = "_".join(parts[:-1])
    except (ValueError, IndexError):
        logger.error(f"Ошибка парсинга кнопки: {data}")
        return

    if action == "feedback_helpful":
        save_feedback(user.id, request_id, is_helpful=True)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Спасибо! Рады помочь 🙂")
        if user.id in user_last_news:
            del user_last_news[user.id]
    
    elif action == "feedback_not_helpful":
        save_feedback(user.id, request_id, is_helpful=False)
        
        if user.id not in user_last_news:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("😔 Попробуйте отправить новость заново.")
            return
        
        original_text = user_last_news[user.id]
        await query.edit_message_text("🔄 Пробую объяснить иначе...")
        
        try:
            # Для регенерации отправляем тот же текст
            payload = {"text_content": original_text}
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(API_URL_NEWS, json=payload)
                response.raise_for_status()
                api_response = response.json()
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Пустой ответ при регенерации")
            
            new_request_id = save_request(user.id, original_text, simplified_text, from_cache=False)
            
            new_response = f"🤖 СКАУТ RVX (Попытка 2):\n\n{simplified_text}"
            keyboard = [
                [
                    InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{new_request_id}"),
                    InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{new_request_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(new_response, reply_markup=reply_markup)
        
        except Exception as e:
            logger.error(f"Ошибка regenerate: {e}")
            await query.edit_message_text("❌ Ошибка при пересоздании.")

# --- 7. Основной обработчик ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text
    save_user(user.id, user.username or "", user.first_name)
    
    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Доступ запрещен.")
        return
    
    if not await check_subscription(user.id, context):
        keyboard = [[InlineKeyboardButton("📢 Подписаться", url=MANDATORY_CHANNEL_LINK)]]
        await update.message.reply_text("⛔ Подпишись на канал!", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    if not check_flood(user.id):
        await update.message.reply_text(f"⏱️ Жди {FLOOD_COOLDOWN_SECONDS} сек.")
        return
    
    # Кэш
    cache_key = get_cache_key(user_text)
    cached_response = get_cache(cache_key)
    
    if cached_response:
        logger.info(f"✨ Кэш HIT для {user.id}")
        user_last_news[user.id] = user_text
        request_id = save_request(user.id, user_text, cached_response, from_cache=True)
        increment_user_requests(user.id)
        
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        await update.message.reply_text(f"⚡ Кэш:\n\n{cached_response}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Запрос
    status_msg = await update.message.reply_text("⏳ Читаю...")
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(API_URL_NEWS, json={"text_content": user_text})
            response.raise_for_status()
            simplified_text = validate_api_response(response.json())
            
            if not simplified_text:
                raise ValueError("Ошибка API")
        
        set_cache(cache_key, simplified_text)
        request_id = save_request(user.id, user_text, simplified_text, from_cache=False)
        increment_user_requests(user.id)
        user_last_news[user.id] = user_text
        
        keyboard = [[
            InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
            InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
        ]]
        await status_msg.edit_text(f"🤖 СКАУТ RVX:\n\n{simplified_text}", reply_markup=InlineKeyboardMarkup(keyboard))
        logger.info(f"✅ Успех для {user.id}")

    except Exception as e:
        logger.error(f"Fail: {e}")
        await status_msg.edit_text("❌ Ошибка связи с мозгом.")

# --- 8. Запуск ---

def main():
    if not TELEGRAM_BOT_TOKEN or not API_URL_NEWS:
        logger.critical("Нет токенов!")
        return
    
    init_database()
    logger.info("🚀 Перезапуск v0.3.1 (Fix Buttons)")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("clear_cache", clear_cache_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
