import os
import logging
import json
import httpx
import hashlib
from typing import Optional
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError

# --- 1. Настройка окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "15.0"))
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MANDATORY_CHANNEL_ID = os.getenv("MANDATORY_CHANNEL_ID", "")
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "")

# --- 2. Логирование ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3. Глобальные хранилища ---
user_last_request = {}  # Антифлуд
request_stats = {}  # Статистика
response_cache = {}  # Кэш ответов {hash: response}
feedback_stats = {"helpful": 0, "not_helpful": 0}  # Статистика обратной связи

# --- 4. Утилиты ---

def check_flood(user_id: int) -> bool:
    """Антифлуд проверка."""
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

def get_cache_key(text: str) -> str:
    """Генерирует уникальный ключ для кэша."""
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет подписку на обязательный канал."""
    if not MANDATORY_CHANNEL_ID:
        return True  # Если канал не настроен - пропускаем всех
    
    try:
        member = await context.bot.get_chat_member(MANDATORY_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True  # В случае ошибки пропускаем

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ API."""
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
    """Приветствие."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запустил бота")
    
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я RVX AI-аналитик криптоновостей.\n\n"
        "📌 Отправь мне новость - получишь простое объяснение\n"
        "⚡ Быстрые ответы благодаря кэшированию\n"
        "💬 Оцени полезность через кнопки под ответом\n\n"
        "Используй /help для инструкций."
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    help_text = (
        "📖 Как пользоваться:\n\n"
        "1. Отправь текст криптоновости\n"
        "2. Получи простое объяснение\n"
        "3. Оцени полезность кнопками 👍/👎\n\n"
        "⚙️ Ограничения:\n"
        f"• Макс {MAX_INPUT_LENGTH} символов\n"
        f"• Не чаще 1 запроса в {FLOOD_COOLDOWN_SECONDS} сек\n\n"
        "💡 Команды:\n"
        "/start - Начать\n"
        "/help - Справка\n"
        "/stats - Статистика\n"
        "/clear_cache - Очистить кэш (только для вас)"
    )
    
    if MANDATORY_CHANNEL_ID:
        help_text += f"\n\n📢 Обязательная подписка:\n{MANDATORY_CHANNEL_LINK}"
    
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика."""
    user_id = update.effective_user.id
    user_requests = request_stats.get(user_id, 0)
    total_requests = sum(request_stats.values())
    total_users = len(request_stats)
    cache_size = len(response_cache)
    
    stats_text = (
        "📊 Статистика:\n\n"
        f"Ваши запросы: {user_requests}\n"
        f"Всего запросов: {total_requests}\n"
        f"Пользователей: {total_users}\n"
        f"Кэшировано ответов: {cache_size}\n\n"
        f"📈 Обратная связь:\n"
        f"👍 Полезно: {feedback_stats['helpful']}\n"
        f"👎 Не помогло: {feedback_stats['not_helpful']}"
    )
    
    await update.message.reply_text(stats_text)

async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка кэша (глобально для админа)."""
    user_id = update.effective_user.id
    
    # Простая версия - каждый может очистить весь кэш
    # В продакшене лучше ограничить админами
    cache_size = len(response_cache)
    response_cache.clear()
    
    await update.message.reply_text(
        f"🗑️ Кэш очищен!\n"
        f"Удалено {cache_size} записей."
    )
    logger.info(f"Пользователь {user_id} очистил кэш ({cache_size} записей)")

# --- 6. Хранилище исходных текстов для regenerate ---
user_last_news = {}  # {user_id: original_text}

# --- 7. Обработчик кнопок ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на inline кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "feedback_helpful":
        feedback_stats["helpful"] += 1
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Спасибо! Рады, что помогли 🙂")
        logger.info(f"Пользователь {user.id} оценил как полезный")
        
        # Удаляем сохраненную новость
        if user.id in user_last_news:
            del user_last_news[user.id]
    
    elif data == "feedback_not_helpful":
        feedback_stats["not_helpful"] += 1
        
        # Проверяем, есть ли сохраненная новость
        if user.id not in user_last_news:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "😔 Жаль, что не помогло.\n"
                "Отправьте новость заново для нового анализа."
            )
            return
        
        # Генерируем НОВЫЙ анализ (игнорируем кэш)
        original_text = user_last_news[user.id]
        
        await query.edit_message_text("🔄 Создаю новый вариант объяснения...")
        logger.info(f"Пользователь {user.id} запросил альтернативный анализ")
        
        try:
            # Запрос к API (БЕЗ кэша)
            payload = {"text_content": original_text}
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(API_URL_NEWS, json=payload)
                response.raise_for_status()
                
                api_response = response.json()
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Некорректный ответ")
            
            # Формируем новый ответ
            new_response = f"🤖 СКАУТ RVX (новый вариант):\n\n{simplified_text}"
            
            # Снова добавляем кнопки
            keyboard = [
                [
                    InlineKeyboardButton("👍 Полезно", callback_data="feedback_helpful"),
                    InlineKeyboardButton("👎 Не помогло", callback_data="feedback_not_helpful")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(new_response, reply_markup=reply_markup)
            logger.info(f"✅ Новый вариант создан для пользователя {user.id}")
        
        except Exception as e:
            logger.error(f"Ошибка при создании нового варианта: {e}")
            await query.edit_message_text(
                "❌ Ошибка при создании нового варианта.\n"
                "Попробуйте отправить новость заново."
            )
            await query.edit_message_reply_markup(reply_markup=None)

# --- 7. Основной обработчик ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений."""
    user = update.effective_user
    user_text = update.message.text
    
    # Проверка whitelist
    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    
    # Проверка подписки на канал
    if not await check_subscription(user.id, context):
        keyboard = [[InlineKeyboardButton("📢 Подписаться", url=MANDATORY_CHANNEL_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⛔ Для использования бота необходимо подписаться на наш канал!\n\n"
            "После подписки отправьте новость снова.",
            reply_markup=reply_markup
        )
        logger.info(f"Пользователь {user.id} не подписан на канал")
        return
    
    # Антифлуд
    if not check_flood(user.id):
        await update.message.reply_text(
            f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS} сек между запросами."
        )
        return
    
    # Валидация
    if not user_text or not user_text.strip():
        await update.message.reply_text("❌ Текст пустой.")
        return
    
    if len(user_text) > MAX_INPUT_LENGTH:
        await update.message.reply_text(
            f"❌ Макс {MAX_INPUT_LENGTH} символов."
        )
        return
    
    if not API_URL_NEWS:
        await update.message.reply_text("❌ Ошибка конфигурации.")
        return
    
    # Проверка кэша
    cache_key = get_cache_key(user_text)
    
    if cache_key in response_cache:
        logger.info(f"✨ Кэш HIT для пользователя {user.id}")
        cached_response = response_cache[cache_key]
        
        # ВАЖНО: Сохраняем исходный текст даже для кэшированных ответов
        user_last_news[user.id] = user_text
        
        # Создаем кнопки обратной связи
        keyboard = [
            [
                InlineKeyboardButton("👍 Полезно", callback_data="feedback_helpful"),
                InlineKeyboardButton("👎 Не помогло", callback_data="feedback_not_helpful")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚡ Из кэша\n\n{cached_response}",
            reply_markup=reply_markup
        )
        
        request_stats[user.id] = request_stats.get(user.id, 0) + 1
        return
    
    logger.info(f"📥 Запрос от {user.id} ({len(user_text)} символов)")
    
    payload = {"text_content": user_text}
    status_msg = await update.message.reply_text("⏳ Анализирую...")

    try:
        # Запрос к API
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(API_URL_NEWS, json=payload)
            response.raise_for_status()
            
            api_response = response.json()
            simplified_text = validate_api_response(api_response)
            
            if not simplified_text:
                raise ValueError("Некорректный ответ API")
        
        # Сохраняем в кэш
        response_cache[cache_key] = simplified_text
        logger.info(f"💾 Ответ сохранен в кэш (всего: {len(response_cache)})")
        
        # 💾 ВАЖНО: Сохраняем исходный текст для возможности regenerate
        user_last_news[user.id] = user_text
        
        # Формируем ответ с кнопками
        final_response = f"🤖 СКАУТ RVX:\n\n{simplified_text}"
        
        keyboard = [
            [
                InlineKeyboardButton("👍 Полезно", callback_data="feedback_helpful"),
                InlineKeyboardButton("👎 Не помогло", callback_data="feedback_not_helpful")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(final_response, reply_markup=reply_markup)
        
        request_stats[user.id] = request_stats.get(user.id, 0) + 1
        logger.info(f"✅ Успешно обработан запрос {user.id}")

    except httpx.TimeoutException:
        await status_msg.edit_text("❌ Timeout. Попробуйте позже.")
    
    except httpx.RequestError as e:
        logger.error(f"API ошибка: {e}")
        await status_msg.edit_text("❌ Сервер недоступен.")
    
    except httpx.HTTPStatusError as e:
        await status_msg.edit_text(f"❌ Ошибка {e.response.status_code}.")
    
    except json.JSONDecodeError:
        await status_msg.edit_text("❌ Некорректный JSON.")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await status_msg.edit_text("❌ Неизвестная ошибка.")

# --- 8. Запуск ---

def main():
    """Запуск бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN не найден")
        return
    
    if not API_URL_NEWS:
        logger.critical("API_URL_NEWS не найден")
        return
    
    logger.info("=" * 50)
    logger.info("🚀 Запуск RVX AI-аналитик v0.2.0")
    logger.info("=" * 50)
    logger.info("Конфигурация:")
    logger.info(f"  • MAX_INPUT: {MAX_INPUT_LENGTH}")
    logger.info(f"  • TIMEOUT: {API_TIMEOUT}s")
    logger.info(f"  • FLOOD: {FLOOD_COOLDOWN_SECONDS}s")
    logger.info(f"  • WHITELIST: {'Да' if ALLOWED_USERS else 'Нет'}")
    logger.info(f"  • CHANNEL: {MANDATORY_CHANNEL_ID if MANDATORY_CHANNEL_ID else 'Нет'}")
    logger.info("=" * 50)
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear_cache", clear_cache_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Бот v0.2.0 запущен!")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
        logger.info(f"Финальная статистика кэша: {len(response_cache)} записей")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)

if __name__ == '__main__':
    main()