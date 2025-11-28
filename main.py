import os
import logging
import json
import httpx
from typing import Optional
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup # Добавлены InlineButton и InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes # Добавлен CallbackQueryHandler
from telegram.error import BadRequest

# --- 1. Настройка окружения и конфигурация ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0"))
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))

# --- 2. Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Глобальные переменные для статистики, антифлуда и обратной связи ---
user_last_request = {}
request_stats = {}
user_last_news = {} # Для хранения текста новости перед отправкой (для регенерации)

# --- Утилиты ---

async def send_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус 'печатает...'."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

def check_flood(user_id: int) -> bool:
    """Проверяет, не спамит ли пользователь."""
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

def increment_user_stats(user_id: int):
    """Увеличивает счетчик запросов пользователя."""
    request_stats[user_id] = request_stats.get(user_id, 0) + 1

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ от API и возвращает текст или None."""
    if not isinstance(api_response, dict):
        logger.error(f"API вернул не-dict объект: {type(api_response)}")
        return None
    
    simplified_text = api_response.get("simplified_text")
    
    if not simplified_text or not isinstance(simplified_text, str):
        logger.error(f"API вернул пустое или неверное поле 'simplified_text'")
        return None
    
    if len(simplified_text) > 4096:
        logger.warning(f"API вернул текст длиннее 4096 символов. Обрезаю.")
        return simplified_text[:4090] + "..."
    
    return simplified_text

def apply_formatting_rules(text: str) -> str:
    """Применяет правила форматирования к тексту от AI."""
    # Заменяем Markdown-стиль (**) на HTML-стиль (<b>)
    text = text.replace('**', '<b>').replace('__', '<i>') 
    
    # Замена структурных элементов на HTML-теги для красивого отображения
    # Используем универсальную замену, чтобы поймать пробелы и переносы строк.
    
    # 1. Горизонтальный разделитель
    text = text.replace('━━━━━━━━━━━━━━━━━━', '<hr>')
    
    # 2. Заголовки (игнорируем пробелы и символы, ищем подстроки)
    if '🔍 СУТЬ' in text:
        text = text.replace('🔍 СУТЬ', '🔍 <b>СУТЬ</b>')
    if '💡 ВЛИЯНИЕ НА КРИПТУ' in text:
        text = text.replace('💡 ВЛИЯНИЕ НА КРИПТУ', '💡 <b>ВЛИЯНИЕ НА КРИПТУ</b>')
    # Возможно, есть и другие заголовки, например, 📉 Ожидается
    if '📉 Ожидается' in text:
         text = text.replace('📉 Ожидается', '📉 <b>Ожидается</b>')

    return text

# --- 6. Обработчики команд ---

def restricted(func):
    """Декоратор: пускает только пользователей из whitelist."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        allowed_users = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
        if allowed_users and user_id not in allowed_users:
            logger.warning(f"⛔ Unauthorized access denied for {user_id}")
            await update.message.reply_text("⛔ Извините, этот бот приватный.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} ({user.first_name}) запустил бота")
    
    welcome_text = (
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я <b>RVX AI-аналитик</b>. Кидай мне сложные крипто-новости, "
        "а я переведу их на человеческий язык.\n\n"
        "Используй /help для получения инструкций."
    )
    
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справочную информацию."""
    help_text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1. Отправь мне текст криптоновости\n"
        "2. Жди несколько секунд\n"
        "3. Получи упрощенное объяснение от AI\n\n"
        "⚙️ Ограничения:\n"
        f"• Максимум {MAX_INPUT_LENGTH} символов\n"
        "• Только текстовые сообщения\n"
        f"• Не чаще 1 запроса в {FLOOD_COOLDOWN_SECONDS} сек\n\n"
        "💡 Команды:\n"
        "/start - Начать работу\n"
        "/help - Показать справку\n"
        "/stats - <b>Статистика</b> использования"
    )
    
    await update.message.reply_text(help_text, parse_mode=constants.ParseMode.HTML)

@restricted
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику использования."""
    user_id = update.effective_user.id
    user_requests = request_stats.get(user_id, 0)
    total_requests = sum(request_stats.values())
    total_users = len(request_stats)
    
    stats_text = (
        "📊 <b>Статистика:</b>\n\n"
        f"Ваши запросы: <code>{user_requests}</code>\n"
        f"Всего запросов: <code>{total_requests}</code>\n"
        f"Всего пользователей: <code>{total_users}</code>"
    )
    
    await update.message.reply_text(stats_text, parse_mode=constants.ParseMode.HTML)

# --- 7. Основной обработчик сообщений ---

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик текстовых сообщений."""
    user = update.effective_user
    user_text = update.message.text
    
    # 🚫 Антифлуд
    if not check_flood(user.id):
        await update.message.reply_text(
            f"⏱️ <i>Подождите {FLOOD_COOLDOWN_SECONDS} секунд между запросами.</i>",
            parse_mode=constants.ParseMode.HTML
        )
        return
    
    # 🚨 Валидация входных данных
    if not user_text or not user_text.strip():
        await update.message.reply_text("❌ Текст не может быть пустым.")
        return
    
    if len(user_text) > MAX_INPUT_LENGTH:
        await update.message.reply_text(
            f"❌ Текст слишком длинный. Максимум {MAX_INPUT_LENGTH} символов."
        )
        return
    
    if not API_URL_NEWS:
        logger.critical("API_URL_NEWS не найден в .env")
        await update.message.reply_text("❌ Критическая ошибка конфигурации.")
        return
    
    logger.info(f"Запрос от пользователя {user.id} ({len(user_text)} символов)")
    
    # UX: Показываем, что бот думает
    await send_typing_action(update, context)
    payload = {"text_content": user_text}
    status_msg = await update.message.reply_text("⏳ Анализирую новость...")
    
    # Запоминаем текст новости для возможной регенерации
    user_last_news[user.id] = user_text

    try:
        # Запрос к API
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(API_URL_NEWS, json=payload)
            response.raise_for_status()
            
            api_response = response.json()
            simplified_text = validate_api_response(api_response)
            
            if not simplified_text:
                raise ValueError("API вернул некорректные данные")
        
        # 4. Готовим HTML ответ
        final_text = apply_formatting_rules(simplified_text)
        final_response = f"🤖 <b>СКАУТ RVX:</b>\n\n{final_text}"
        
        # Кнопки обратной связи (нужен placeholder ID, т.к. нет DB)
        # Используем 0 как placeholder ID. Нам важно только action
        keyboard = [
            [
                InlineKeyboardButton("👍 Полезно", callback_data="feedback_helpful_0"),
                InlineKeyboardButton("👎 Не помогло", callback_data="feedback_not_helpful_0")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Редактируем временное сообщение с HTML и кнопками
        await status_msg.edit_text(final_response, parse_mode=constants.ParseMode.HTML, reply_markup=reply_markup)
        
        # Обновляем статистику
        increment_user_stats(user.id)
        logger.info(f"✅ Успешно обработан запрос пользователя {user.id}")

    except BadRequest as e:
        logger.error(f"Telegram BadRequest: {e}. Отправка как чистый текст.")
        # Отправляем как чистый текст, чтобы бот не завис
        await status_msg.edit_text(
            f"❌ Ошибка форматирования. Вот чистый текст:\n\n{simplified_text}"
        )

    except httpx.TimeoutException:
        logger.error(f"Timeout при подключении к API: {API_URL_NEWS}")
        await status_msg.edit_text("❌ Превышено время ожидания ответа от сервера.")
    
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {str(e)}", exc_info=True)
        await status_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")

# --- 8. Обработчик кнопок (CallbackQueryHandler) ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline кнопок."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Парсинг данных кнопки (в упрощенной версии нам важен только action)
    action = data.split("_")[1] # 'helpful' или 'not'
    
    if action == "helpful":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Спасибо! Рады помочь 🙂")
        
        # Удаляем новость из памяти
        if user_id in user_last_news:
            del user_last_news[user_id]
            
    elif action == "not": # 'feedback_not_helpful_0'
        
        if user_id not in user_last_news:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("😔 Попробуйте отправить новость заново.")
            return
        
        original_text = user_last_news[user_id]
        
        # Регенерация
        await query.edit_message_text("🔄 Пробую объяснить иначе...")
        
        try:
            payload = {"text_content": original_text}
            
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(API_URL_NEWS, json=payload)
                response.raise_for_status()
                
                api_response = response.json()
                simplified_text = validate_api_response(api_response)
                
                if not simplified_text:
                    raise ValueError("Пустой ответ при регенерации")
            
            # Готовим HTML ответ
            final_text = apply_formatting_rules(simplified_text)
            
            new_response = f"🤖 <b>СКАУТ RVX (Попытка 2):</b>\n\n{final_text}"
            
            # Кнопки (снова с placeholder ID)
            keyboard = [
                [
                    InlineKeyboardButton("👍 Полезно", callback_data="feedback_helpful_0"),
                    InlineKeyboardButton("👎 Не помогло", callback_data="feedback_not_helpful_0")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(new_response, parse_mode=constants.ParseMode.HTML, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Ошибка regenerate: {e}")
            await query.edit_message_text("❌ Ошибка при пересоздании.")


# --- 9. Главная функция запуска ---

def main():
    """Запускает бота с проверкой конфигурации."""
    if not TELEGRAM_BOT_TOKEN or not API_URL_NEWS:
        logger.critical("Критическая ошибка конфигурации. Проверьте .env")
        return
    
    # ... (Логирование конфигурации) ...
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback)) # Добавлен обработчик кнопок

    logger.info("🤖 Бот успешно запущен. Ожидание сообщений...")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()
