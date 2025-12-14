"""
Command Handler - обработчик команд бота.

SRP: Обрабатывает только команды, логика в сервисах.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..services import UserService, LessonService, QuestService
from ..schemas import UserSchema, UserStatsSchema

logger = logging.getLogger("command_handler")


class CommandHandler:
    """Handler for bot commands."""
    
    def __init__(self, user_service: UserService = None, lesson_service: LessonService = None):
        """Initialize command handler."""
        self.user_service = user_service or UserService()
        self.lesson_service = lesson_service or LessonService()
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user = update.effective_user
        user_id = user.id
        
        # Create/update user
        self.user_service.create_or_update_user(user_id, user.username or "", user.first_name or "")
        
        # Get user stats
        stats = self.user_service.get_user_stats(user_id)
        
        # Build welcome message
        welcome_text = (
            f"👋 <b>Добро пожаловать в RVX AI Bot!</b>\n\n"
            f"🎯 <b>Ваш статус:</b>\n"
            f"  • Level: {stats.get('level', 1) if stats else 1}\n"
            f"  • XP: {stats.get('xp', 0) if stats else 0}\n\n"
            f"📚 <b>Что вы можете делать:</b>\n"
            f"  • Анализировать новости\n"
            f"  • Проходить курсы\n"
            f"  • Решать квесты\n"
            f"  • Зарабатывать XP и значки\n\n"
            f"👇 <b>Выберите действие:</b>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📚 Курсы", callback_data="start_learn"),
                InlineKeyboardButton("🎮 Квесты", callback_data="start_quests")
            ],
            [
                InlineKeyboardButton("💬 Вопрос", callback_data="ask_question"),
                InlineKeyboardButton("📊 Статистика", callback_data="show_stats")
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="show_help")
            ]
        ]
        
        try:
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"✅ User {user_id} started bot")
        except Exception as e:
            logger.error(f"❌ Error in /start handler: {e}")
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_text = (
            "<b>❓ СПРАВКА</b>\n\n"
            "<b>📚 КУРСЫ:</b>\n"
            "  /learn - Просмотр доступных курсов\n"
            "  /lesson - Просмотр урока\n\n"
            "<b>🎮 КВЕСТЫ:</b>\n"
            "  /quests - Просмотр ежедневных квестов\n"
            "  /stats - Статистика пользователя\n\n"
            "<b>💬 АНАЛИЗ:</b>\n"
            "  Просто отправьте текст для анализа\n\n"
            "<b>🔧 ИНСТРУМЕНТЫ:</b>\n"
            "  /menu - Главное меню\n"
            "  /help - Эта справка"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    help_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    help_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            logger.info(f"✅ Help command executed for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"❌ Error in /help handler: {e}")
    
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command."""
        user_id = update.effective_user.id
        
        stats = self.user_service.get_user_stats(user_id)
        if not stats:
            error_text = "❌ Ошибка: не удалось получить статистику"
            try:
                if update.callback_query:
                    await update.callback_query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"❌ Error sending stats error: {e}")
            return
        
        stats_text = (
            "📊 <b>ВАША СТАТИСТИКА</b>\n\n"
            f"👤 <b>Профиль:</b>\n"
            f"  • Level: {stats.get('level', 1)}\n"
            f"  • XP: {stats.get('xp', 0)}\n"
            f"  • Значки: {stats.get('badges_count', 0)}\n\n"
            f"📚 <b>Обучение:</b>\n"
            f"  • Пройдено курсов: {stats.get('courses_completed', 0)}\n"
            f"  • Тестов пройдено: {stats.get('tests_passed', 0)}\n\n"
            f"📈 <b>Активность:</b>\n"
            f"  • Запросов сегодня: {stats.get('daily_requests_used', 0)}\n"
            f"  • Последний запрос: {stats.get('last_request_at', 'Нет')}"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    stats_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    stats_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            logger.info(f"✅ Stats shown for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error in /stats handler: {e}")
    
    async def handle_learn(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /learn command."""
        user_id = update.effective_user.id
        
        try:
            # Get available courses
            courses = [
                {"id": "crypto_basics", "title": "Основы крипто", "description": "Введение в криптовалюты"},
                {"id": "trading", "title": "Трейдинг", "description": "Основы торговли"},
                {"id": "security", "title": "Безопасность", "description": "Защита ваших активов"}
            ]
            
            learn_text = "🎓 <b>ДОСТУПНЫЕ КУРСЫ</b>\n\n"
            for course in courses:
                learn_text += f"📚 <b>{course['title']}</b>\n  {course['description']}\n\n"
            
            keyboard = [
                [InlineKeyboardButton(f"📚 {course['title']}", callback_data=f"course_{course['id']}")] 
                for course in courses
            ]
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    learn_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    learn_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            logger.info(f"✅ Learn menu shown for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error in /learn handler: {e}")
