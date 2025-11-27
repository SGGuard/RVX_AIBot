import os
import logging
import json
import httpx 
from typing import Optional
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. Настройка окружения и конфигурация ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL_NEWS = os.getenv("API_URL_NEWS")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "15.0"))
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))

# --- 2. Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3. Антифлуд механизм ---
user_last_request = {}

def check_flood(user_id: int) -> bool:
    """Проверяет, не спамит ли пользователь."""
    now = datetime.now()
    if user_id in user_last_request:
        time_diff = (now - user_last_request[user_id]).total_seconds()
        if time_diff < FLOOD_COOLDOWN_SECONDS:
            return False
    user_last_request[user_id] = now
    return True

# --- 4. Статистика запросов ---
request_stats = {}

def increment_user_stats(user_id: int):
    """Увеличивает счетчик запросов пользователя."""
    request_stats[user_id] = request_stats.get(user_id, 0) + 1

# --- 5. Валидация ответа от API ---

def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ от API и возвращает текст или None."""
    if not isinstance(api_response, dict):
        logger.error(f"API вернул не-dict объект: {type(api_response)}")
        return None
    
    simplified_text = api_response.get("simplified_text")
    
    if not simplified_text:
        logger.error("API вернул пустое поле 'simplified_text'")
        return None
    
    if not isinstance(simplified_text, str):
        logger.error(f"Поле 'simplified_text' неверного типа: {type(simplified_text)}")
        return None
    
    # Лимит Telegram - 4096 символов
    if len(simplified_text) > 4096:
        logger.warning(f"API вернул текст длиннее 4096 символов. Обрезаю.")
        return simplified_text[:4090] + "..."
    
    return simplified_text

# --- 6. Обработчики команд ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} ({user.first_name}) запустил бота")
    
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я RVX AI-аналитик. Кидай мне сложные крипто-новости, "
        "а я переведу их на человеческий язык.\n\n"
        "Используй /help для получения инструкций."
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справочную информацию."""
    help_text = (
        "📖 Как пользоваться ботом:\n\n"
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
        "/stats - Статистика использования"
    )
    
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику использования."""
    user_id = update.effective_user.id
    user_requests = request_stats.get(user_id, 0)
    total_requests = sum(request_stats.values())
    total_users = len(request_stats)
    
    stats_text = (
        "📊 Статистика:\n\n"
        f"Ваши запросы: {user_requests}\n"
        f"Всего запросов: {total_requests}\n"
        f"Всего пользователей: {total_users}"
    )
    
    await update.message.reply_text(stats_text)

# --- 7. Основной обработчик сообщений ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик текстовых сообщений."""
    user = update.effective_user
    user_text = update.message.text
    
    # 🔐 Проверка whitelist
    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
        logger.warning(f"Доступ запрещен для пользователя {user.id}")
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return
    
    # 🚫 Антифлуд
    if not check_flood(user.id):
        await update.message.reply_text(
            f"⏱️ Подождите {FLOOD_COOLDOWN_SECONDS} секунд между запросами."
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
    
    # 💀 Проверка API URL
    if not API_URL_NEWS:
        logger.critical("API_URL_NEWS не найден в .env")
        await update.message.reply_text(
            "❌ Критическая ошибка конфигурации. Обратитесь к администратору."
        )
        return
    
    logger.info(f"Запрос от пользователя {user.id} ({len(user_text)} символов)")
    
    payload = {"text_content": user_text}
    status_msg = await update.message.reply_text("⏳ Анализирую новость...")

    try:
        # Запрос к API
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(API_URL_NEWS, json=payload)
            response.raise_for_status()
            
            api_response = response.json()
            simplified_text = validate_api_response(api_response)
            
            if not simplified_text:
                raise ValueError("API вернул некорректные данные")
        
        # ✅ Отправляем ответ БЕЗ форматирования
        final_response = f"🤖 СКАУТ RVX:\n\n{simplified_text}"
        
        await status_msg.edit_text(final_response)
        
        # Обновляем статистику
        increment_user_stats(user.id)
        logger.info(f"✅ Успешно обработан запрос пользователя {user.id}")

    except httpx.TimeoutException:
        logger.error(f"Timeout при подключении к API: {API_URL_NEWS}")
        await status_msg.edit_text(
            "❌ Превышено время ожидания ответа от сервера. Попробуйте позже."
        )
    
    except httpx.RequestError as e:
        logger.error(f"Ошибка подключения к API: {str(e)}")
        await status_msg.edit_text(
            "❌ Ошибка подключения. Сервер аналитики временно недоступен."
        )
    
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка от API: {e.response.status_code}")
        await status_msg.edit_text(
            f"❌ Сервер аналитики вернул ошибку ({e.response.status_code})."
        )
    
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON от API")
        await status_msg.edit_text(
            "❌ Сервер вернул некорректный ответ. Попробуйте позже."
        )
    
    except ValueError as e:
        logger.error(f"Ошибка валидации данных: {str(e)}")
        await status_msg.edit_text(
            "❌ API вернул некорректные данные. Обратитесь к администратору."
        )
    
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {str(e)}", exc_info=True)
        await status_msg.edit_text(
            "❌ Произошла неизвестная ошибка. Попробуйте позже."
        )

# --- 8. Главная функция запуска ---

def main():
    """Запускает бота с проверкой конфигурации."""
    # Проверка переменных окружения
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN не найден в .env")
        return
    
    if not API_URL_NEWS:
        logger.critical("API_URL_NEWS не найден в .env")
        return
    
    # Логируем конфигурацию
    logger.info("=" * 50)
    logger.info("🚀 Запуск бота RVX AI-аналитик")
    logger.info("=" * 50)
    logger.info("Конфигурация:")
    logger.info(f"  • MAX_INPUT_LENGTH: {MAX_INPUT_LENGTH} символов")
    logger.info(f"  • API_TIMEOUT: {API_TIMEOUT} секунд")
    logger.info(f"  • FLOOD_COOLDOWN: {FLOOD_COOLDOWN_SECONDS} секунд")
    whitelist_status = f"Включен ({len(ALLOWED_USERS)} польз.)" if ALLOWED_USERS else "Выключен"
    logger.info(f"  • WHITELIST: {whitelist_status}")
    logger.info(f"  • API_URL: {API_URL_NEWS}")
    logger.info("=" * 50)
    
    # Создаем Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Бот успешно запущен. Ожидание сообщений...")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки. Завершение работы...")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()