import os
import logging
import json
import httpx
import hashlib
import sqlite3
from typing import Optional, List, Tuple
from datetime import datetime
from contextlib import contextmanager
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest, TelegramError

# --- 1. Настройка окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0"))
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
    """Инициализация БД."""
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
    """Сохраняет пользователя."""
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
    """Увеличивает счетчик запросов."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET total_requests = total_requests + 1,
                last_request_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))

def save_request(user_id: int, news_text: str, response_text: str, from_cache: bool) -> int:
    """Сохраняет запрос. Возвращает request_id."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (user_id, news_text, response_text, from_cache)
            VALUES (?, ?, ?, ?)
        """, (user_id, news_text, response_text, from_cache))
        return cursor.lastrowid

def save_feedback(user_id: int, request_id: int, is_helpful: bool):
    """Сохраняет обратную связь."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (user_id, request_id, is_helpful)
            VALUES (?, ?, ?)
        """, (user_id, request_id, is_helpful))

def get_cache(cache_key: str) -> Optional[str]:
    """Получает из кэша."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT response_text FROM cache WHERE cache_key = ?", (cache_key,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?", (cache_key,))
            return row[0]
        return None

def set_cache(cache_key: str, response_text: str):
    """Сохраняет в кэш."""
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
    """История пользователя."""
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
    """Поиск по истории."""
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
    """Глобальная статистика."""
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

async def send_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает 'печатает...'."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

def check_flood(user_id: int) -> bool:
    """Антифлуд."""
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

def get_cache_key(text: str) -> str:
    """Ключ кэша."""
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки."""
    if not MANDATORY_CHANNEL_ID:
        return True
    
    try:
        member = await context.bot.get_chat_member(MANDATORY_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидация ответа API."""
    if not isinstance(api_response, dict):
        return None
    
    simplified_text = api_response.get("simplified_text")
    
    if not simplified_text or not isinstance(simplified_text, str):
        return None
    
    if len(simplified_text) > 4096:
        return simplified_text[:4090] + "..."
    
    return simplified_text

def apply_formatting_rules(text: str) -> str:
    """HTML форматирование."""
    text = text.replace('**', '<b>').replace('__', '<i>')
    text = text.replace('━━━━━━━━━━━━━━━━━━', '<hr>')
    
    if '🔍 СУТЬ' in text:
        text = text.replace('🔍 СУТЬ', '🔍 <b>СУТЬ</b>')
    if '💡 ВЛИЯНИЕ НА КРИПТУ' in text:
        text = text.replace('💡 ВЛИЯНИЕ НА КРИПТУ', '💡 <b>ВЛИЯНИЕ НА КРИПТУ</b>')
    
    return text

def restricted(func):
    """Декоратор: whitelist."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            logger.warning(f"⛔️ Доступ запрещен для {user_id}")
            await update.message.reply_text("⛔️ Этот бот приватный.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 5. Команды ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    user = update.effective_user
    save_user(user.id, user.username or "", user.first_name)
    
    welcome_text = (
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я <b>RVX AI-аналитик v0.3.0</b> с базой данных!\n\n"
        "🆕 Новое:\n"
        "💾 История анализов\n"
        "🔍 Поиск по истории\n"
        "📊 Расширенная статистика\n"
        "📥 Экспорт истории\n\n"
        "Используй /help для инструкций."
    )
    
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    help_text = (
        "📖 <b>Как пользоваться:</b>\n\n"
        "1. Отправь криптоновость\n"
        "2. Получи объяснение\n"
        "3. Оцени 👍/👎\n\n"
        "💡 <b>Команды:</b>\n"
        "/start - Начать\n"
        "/help - Справка\n"
        "/stats - Статистика\n"
        "/history - Последние 5\n"
        "/search <текст> - Поиск\n"
        "/export - Экспорт в файл\n"
        "/clear_cache - Очистить кэш\n\n"
        f"⚙️ Макс {MAX_INPUT_LENGTH} символов"
    )
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 <a href='{MANDATORY_CHANNEL_LINK}'>Обязательная подписка</a>"
    
    await update.message.reply_text(help_text, parse_mode=constants.ParseMode.HTML, disable_web_page_preview=True)

@restricted
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика."""
    user_id = update.effective_user.id
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_requests FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        user_requests = row[0] if row else 0
    
    stats = get_global_stats()
    
    stats_text = (
        "📊 <b>Статистика v0.3.0:</b>\n\n"
        f"👤 Ваши запросы: <code>{user_requests}</code>\n"
        f"👥 Пользователей: <code>{stats['total_users']}</code>\n"
        f"📝 Всего запросов: <code>{stats['total_requests']}</code>\n"
        f"💾 Кэш: <code>{stats['cache_size']}</code>\n\n"
        f"📈 <b>Обратная связь:</b>\n"
        f"👍 Полезно: <code>{stats['helpful']}</code>\n"
        f"👎 Не помогло: <code>{stats['not_helpful']}</code>\n\n"
        f"🏆 <b>ТОП-5:</b>\n"
    )
    
    for i, (username, first_name, requests) in enumerate(stats['top_users'], 1):
        name = username or first_name or "Анонимный"
        stats_text += f"{i}. {name}: {requests}\n"
    
    await update.message.reply_text(stats_text, parse_mode=constants.ParseMode.HTML)

@restricted
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История."""
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=5)
    
    if not history:
        await update.message.reply_text("📜 История пуста.")
        return
    
    response = "📜 <b>Последние 5:</b>\n\n"
    
    for i, (news, _, created_at, from_cache) in enumerate(history, 1):
        news_preview = news[:50] + "..." if len(news) > 50 else news
        cache_icon = "⚡" if from_cache else "🆕"
        response += f"{i}. {cache_icon} {news_preview}\n   🕐 {created_at}\n\n"
    
    response += "Используй /search для поиска"
    
    await update.message.reply_text(response, parse_mode=constants.ParseMode.HTML)

@restricted
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /search <текст>")
        return
    
    search_text = " ".join(context.args)
    results = search_user_requests(user_id, search_text)
    
    if not results:
        await update.message.reply_text(f"🔍 Не найдено: {search_text}")
        return
    
    response = f"🔍 <b>Найдено {len(results)}:</b>\n\n"
    
    for i, (news, _, created_at) in enumerate(results[:5], 1):
        news_preview = news[:60] + "..." if len(news) > 60 else news
        response += f"{i}. {news_preview}\n   🕐 {created_at}\n\n"
    
    await update.message.reply_text(response, parse_mode=constants.ParseMode.HTML)

@restricted
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт."""
    user_id = update.effective_user.id
    history = get_user_history(user_id, limit=100)
    
    if not history:
        await update.message.reply_text("📜 История пуста.")
        return
    
    export_text = f"История RVX AI\nПользователь: {user_id}\nДата: {datetime.now()}\n\n{'=' * 50}\n\n"
    
    for i, (news, response, created_at, from_cache) in enumerate(history, 1):
        export_text += f"#{i} | {created_at} | {'Кэш' if from_cache else 'Новый'}\n"
        export_text += f"НОВОСТЬ:\n{news}\n\nАНАЛИЗ:\n{response}\n\n{'=' * 50}\n\n"
    
    from io import BytesIO
    file = BytesIO(export_text.encode('utf-8'))
    file.name = f"rvx_history_{user_id}.txt"
    
    await update.message.reply_document(document=file, caption=f"📥 {len(history)} записей")

@restricted
async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка кэша."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cache")
        cache_size = cursor.fetchone()[0]
        cursor.execute("DELETE FROM cache")
    
    await update.message.reply_text(f"🗑️ Кэш очищен! Удалено {cache_size}.")

# --- 6. Обработчик сообщений ---

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик."""
    user = update.effective_user
    user_text = update.message.text
    
    save_user(user.id, user.username or "", user.first_name)
    
    # Проверка подписки
    if not await check_subscription(user.id, context):
        keyboard = [[InlineKeyboardButton("📢 Подписаться", url=MANDATORY_CHANNEL_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⛔ Подпишитесь на канал!", reply_markup=reply_markup)
        return
    
    # Антифлуд
    if not check_flood(user.id):
        await update.message.reply_text(f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS}с.")
        return
    
    # Валидация
    if not user_text or len(user_text) > MAX_INPUT_LENGTH:
        await update.message.reply_text("❌ Текст некорректный.")
        return
    
    if not API_URL_NEWS:
        await update.message.reply_text("❌ Ошибка конфигурации.")
        return
    
    # Кэш (БД)
    cache_key = get_cache_key(user_text)
    cached_response = get_cache(cache_key)
    
    if cached_response:
        logger.info(f"✨ Кэш HIT для {user.id}")
        
        user_last_news[user.id] = user_text
        request_id = save_request(user.id, user_text, cached_response, from_cache=True)
        increment_user_requests(user.id)
        
        final_text = apply_formatting_rules(cached_response)
        final_response = f"🤖 <b>СКАУТ RVX:</b>\n\n⚡ Из кэша\n\n{final_text}"
        
        keyboard = [
            [
                InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
                InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(final_response, parse_mode=constants.ParseMode.HTML, reply_markup=reply_markup)
        return
    
    # Новый запрос
    await send_typing_action(update, context)
    status_msg = await update.message.reply_text("⏳ Анализирую...")
    
    user_last_news[user.id] = user_text

    try:
        payload = {"text_content": user_text}
        
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(API_URL_NEWS, json=payload)
            response.raise_for_status()
            
            api_response = response.json()
            simplified_text = validate_api_response(api_response)
            
            if not simplified_text:
                raise ValueError("Некорректный ответ")
        
        # Сохранение
        set_cache(cache_key, simplified_text)
        request_id = save_request(user.id, user_text, simplified_text, from_cache=False)
        increment_user_requests(user.id)
        
        # HTML форматирование
        final_text = apply_formatting_rules(simplified_text)
        final_response = f"🤖 <b>СКАУТ RVX:</b>\n\n{final_text}"
        
        keyboard = [
            [
                InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{request_id}"),
                InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{request_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(final_response, parse_mode=constants.ParseMode.HTML, reply_markup=reply_markup)
        logger.info(f"✅ Успех для {user.id}")

    except BadRequest as e:
        logger.error(f"BadRequest: {e}")
        await status_msg.edit_text(f"❌ Ошибка форматирования.\n\n{simplified_text}")

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await status_msg.edit_text("❌ Ошибка.")

# --- 7. Обработчик кнопок ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    parts = data.split("_")
    action = "_".join(parts[:2])
    request_id = int(parts[2]) if len(parts) > 2 else None
    
    if action == "feedback_helpful":
        if request_id:
            save_feedback(user.id, request_id, is_helpful=True)
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Спасибо! 🙂")
        
        if user.id in user_last_news:
            del user_last_news[user.id]
    
    elif action == "feedback_not":
        if request_id:
            save_feedback(user.id, request_id, is_helpful=False)
        
        if user.id not in user_last_news:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("😔 Отправьте заново.")
            return
        
        original_text = user_last_news[user.id]
        await query.edit_message_text("🔄 Создаю новый вариант...")
        
        try:
            payload = {"text_content": original_text}
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(API_URL_NEWS, json=payload)
                response.raise_for_status()
                
                api_response = response.json()
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Пустой ответ")
            
            new_request_id = save_request(user.id, original_text, simplified_text, from_cache=False)
            
            final_text = apply_formatting_rules(simplified_text)
            new_response = f"🤖 <b>СКАУТ RVX (новый вариант):</b>\n\n{final_text}"
            
            keyboard = [
                [
                    InlineKeyboardButton("👍 Полезно", callback_data=f"feedback_helpful_{new_request_id}"),
                    InlineKeyboardButton("👎 Не помогло", callback_data=f"feedback_not_helpful_{new_request_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(new_response, parse_mode=constants.ParseMode.HTML, reply_markup=reply_markup)
        
        except Exception as e:
            logger.error(f"Ошибка regenerate: {e}")
            await query.edit_message_text("❌ Ошибка.")

# --- 8. Запуск ---

def main():
    """Запуск."""
    if not TELEGRAM_BOT_TOKEN or not API_URL_NEWS:
        logger.critical("Отсутствуют токены")
        return
    
    init_database()
    
    logger.info("=" * 50)
    logger.info("🚀 RVX AI v0.3.0 (SQLite + HTML)")
    logger.info("=" * 50)
    
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

    logger.info("🤖 Бот v0.3.0 запущен!")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Остановка...")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)

if __name__ == '__main__':
    main()
