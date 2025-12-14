"""
Button Handler - обработчик нажатий на кнопки.

SRP: Обрабатывает callback queries, логика в сервисах.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..services import UserService, LessonService, QuestService

logger = logging.getLogger("button_handler")


class ButtonHandler:
    """Handler for inline keyboard buttons (callbacks)."""
    
    def __init__(self, user_service: UserService = None, lesson_service: LessonService = None, 
                 quest_service: QuestService = None):
        """Initialize button handler."""
        self.user_service = user_service or UserService()
        self.lesson_service = lesson_service or LessonService()
        self.quest_service = quest_service or QuestService()
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Main callback handler dispatcher."""
        query = update.callback_query
        await query.answer()  # Acknowledge button press
        
        callback_data = query.data
        
        # Route to appropriate handler
        if callback_data == "back_to_start":
            await self.handle_back_to_start(update, context)
        elif callback_data == "show_help":
            await self.handle_show_help(update, context)
        elif callback_data == "show_stats":
            await self.handle_show_stats(update, context)
        elif callback_data == "start_learn":
            await self.handle_start_learn(update, context)
        elif callback_data == "start_quests":
            await self.handle_start_quests(update, context)
        elif callback_data.startswith("course_"):
            course_id = callback_data.replace("course_", "")
            await self.handle_course_selection(update, context, course_id)
        elif callback_data.startswith("lesson_"):
            parts = callback_data.split("_")
            if len(parts) == 3:
                course_id, lesson_num = parts[1], int(parts[2])
                await self.handle_lesson_view(update, context, course_id, lesson_num)
        elif callback_data.startswith("quest_"):
            quest_id = callback_data.replace("quest_", "")
            await self.handle_quest_start(update, context, quest_id)
        else:
            logger.warning(f"⚠️ Unknown callback: {callback_data}")
            await query.edit_message_text("❓ Неизвестная команда")
    
    async def handle_back_to_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle back to main menu button."""
        query = update.callback_query
        
        main_menu_text = (
            "👋 <b>Главное меню RVX</b>\n\n"
            "Выберите действие:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📚 Курсы", callback_data="start_learn"),
                InlineKeyboardButton("🎮 Квесты", callback_data="start_quests")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="show_stats"),
                InlineKeyboardButton("❓ Помощь", callback_data="show_help")
            ]
        ]
        
        try:
            await query.edit_message_text(
                main_menu_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in back_to_start handler: {e}")
    
    async def handle_show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help information."""
        query = update.callback_query
        
        help_text = (
            "<b>❓ СПРАВКА</b>\n\n"
            "<b>📚 КУРСЫ:</b>\n"
            "Пройдите интерактивные курсы по криптовалютам\n\n"
            "<b>🎮 КВЕСТЫ:</b>\n"
            "Выполняйте ежедневные задания для получения XP\n\n"
            "<b>💬 АНАЛИЗ:</b>\n"
            "Отправьте текст для анализа\n\n"
            "<b>📊 СТАТИСТИКА:</b>\n"
            "Просмотрите ваш прогресс и достижения"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        try:
            await query.edit_message_text(
                help_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in help handler: {e}")
    
    async def handle_show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show user statistics."""
        query = update.callback_query
        user_id = update.effective_user.id
        
        stats = self.user_service.get_user_stats(user_id)
        if not stats:
            await query.edit_message_text("❌ Ошибка при получении статистики")
            return
        
        stats_text = (
            "📊 <b>ВАША СТАТИСТИКА</b>\n\n"
            f"👤 <b>Профиль:</b>\n"
            f"  • Level: {stats.get('level', 1)}\n"
            f"  • XP: {stats.get('xp', 0)}\n"
            f"  • Значки: {stats.get('badges_count', 0)}\n\n"
            f"📚 <b>Обучение:</b>\n"
            f"  • Курсов: {stats.get('courses_completed', 0)}\n"
            f"  • Тестов: {stats.get('tests_passed', 0)}\n"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]]
        
        try:
            await query.edit_message_text(
                stats_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in stats handler: {e}")
    
    async def handle_start_learn(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show available courses."""
        query = update.callback_query
        
        courses = [
            {"id": "crypto_basics", "title": "Основы крипто", "emoji": "🌱"},
            {"id": "trading", "title": "Трейдинг", "emoji": "📈"},
            {"id": "security", "title": "Безопасность", "emoji": "🔒"}
        ]
        
        learn_text = "🎓 <b>ДОСТУПНЫЕ КУРСЫ</b>\n\n"
        keyboard = []
        
        for course in courses:
            learn_text += f"{course['emoji']} <b>{course['title']}</b>\n\n"
            keyboard.append([InlineKeyboardButton(
                f"{course['emoji']} {course['title']}", 
                callback_data=f"course_{course['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        try:
            await query.edit_message_text(
                learn_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in learn handler: {e}")
    
    async def handle_start_quests(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show available quests."""
        query = update.callback_query
        user_id = update.effective_user.id
        
        quests = self.quest_service.get_daily_quests(user_id)
        
        quests_text = "🎮 <b>ЕЖЕДНЕВНЫЕ КВЕСТЫ</b>\n\n"
        keyboard = []
        
        if not quests:
            quests_text += "❌ Квестов не найдено"
        else:
            for quest in quests[:5]:  # Show top 5
                quest_id = quest.get('id', f"quest_{len(keyboard)}")
                quests_text += f"🎯 <b>{quest.get('title', 'Квест')}</b>\n  XP: +{quest.get('xp', 100)}\n\n"
                keyboard.append([InlineKeyboardButton(
                    f"▶️ {quest.get('title', 'Начать')}", 
                    callback_data=f"quest_{quest_id}"
                )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")])
        
        try:
            await query.edit_message_text(
                quests_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in quests handler: {e}")
    
    async def handle_course_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     course_id: str) -> None:
        """Handle course selection."""
        query = update.callback_query
        
        course_text = (
            f"📚 <b>КУРС: {course_id}</b>\n\n"
            f"Описание курса...\n\n"
            f"Выберите урок:"
        )
        
        # Show first 5 lessons
        keyboard = [
            [InlineKeyboardButton(f"Урок {i}", callback_data=f"lesson_{course_id}_{i}")] 
            for i in range(1, 6)
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="start_learn")])
        
        try:
            await query.edit_message_text(
                course_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"❌ Error in course selection: {e}")
    
    async def handle_lesson_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                course_id: str, lesson_num: int) -> None:
        """Show lesson content."""
        query = update.callback_query
        user_id = update.effective_user.id
        
        try:
            lesson_content = self.lesson_service.get_lesson_content(course_id, lesson_num)
            
            if not lesson_content:
                await query.edit_message_text("❌ Урок не найден")
                return
            
            # Limit message size
            max_len = 3500
            if len(lesson_content) > max_len:
                lesson_content = lesson_content[:max_len] + "\n\n[... продолжение]"
            
            lesson_text = (
                f"📖 <b>{course_id} - Урок {lesson_num}</b>\n\n"
                f"{lesson_content}"
            )
            
            # Add XP for viewing
            self.lesson_service.save_quiz_response(user_id, f"view_lesson_{lesson_num}", "viewed", True)
            
            keyboard = []
            if lesson_num > 1:
                keyboard.append([InlineKeyboardButton(
                    "◀️ Предыдущий", 
                    callback_data=f"lesson_{course_id}_{lesson_num - 1}"
                )])
            
            keyboard.append([InlineKeyboardButton(
                "▶️ Следующий", 
                callback_data=f"lesson_{course_id}_{lesson_num + 1}"
            )])
            keyboard.append([InlineKeyboardButton("⬅️ Курс", callback_data=f"course_{course_id}")])
            
            await query.edit_message_text(
                lesson_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"✅ Lesson {lesson_num} shown for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error viewing lesson: {e}")
            await query.edit_message_text("❌ Ошибка при загрузке урока")
    
    async def handle_quest_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                quest_id: str) -> None:
        """Handle quest start."""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if self.quest_service.start_quest(user_id, quest_id):
            quest_text = (
                f"🎯 <b>КВЕСТ НАЧАТ: {quest_id}</b>\n\n"
                f"Описание задания...\n\n"
                f"Начните выполнять квест!"
            )
            
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="start_quests")]]
            
            await query.edit_message_text(
                quest_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"✅ Quest {quest_id} started for user {user_id}")
        else:
            await query.edit_message_text("❌ Ошибка при запуске квеста")
