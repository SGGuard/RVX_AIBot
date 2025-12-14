"""
Message Handler - обработчик текстовых сообщений.

SRP: Обрабатывает только сообщения, логика в сервисах.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..services import UserService, APIClientService

logger = logging.getLogger("message_handler")


class MessageHandler:
    """Handler for user text messages."""
    
    def __init__(self, user_service: UserService = None, api_client: APIClientService = None):
        """Initialize message handler."""
        self.user_service = user_service or UserService()
        self.api_client = api_client
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle incoming text messages for analysis.
        
        Validates input, checks limits, calls API, returns response.
        """
        if not update.message or not update.message.text:
            logger.warning("❌ Empty message received")
            return
        
        user = update.effective_user
        user_id = user.id
        text = update.message.text.strip()
        
        # Validate input
        if len(text) == 0:
            await update.message.reply_text("❌ Пустое сообщение")
            return
        
        if len(text) > 4096:
            await update.message.reply_text("❌ Сообщение слишком длинное (максимум 4096 символов)")
            return
        
        # Save user
        self.user_service.create_or_update_user(user_id, user.username or "", user.first_name or "")
        
        # Check daily limit
        can_request, remaining = self.user_service.check_daily_limit(user_id)
        if not can_request:
            await update.message.reply_text(
                "⛔ <b>Лимит исчерпан</b>\n\n"
                f"Осталось: {remaining} запросов\n"
                "Попробуйте завтра.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check for banned user
        is_banned, ban_reason = self.user_service.is_banned(user_id)
        if is_banned:
            await update.message.reply_text(
                f"⛔ <b>Вы заблокированы</b>\n\n"
                f"Причина: {ban_reason or 'Не указана'}",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            "🔄 <b>Анализирую...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            # Call API
            if not self.api_client:
                await processing_msg.edit_text(
                    "❌ <b>API клиент не инициализирован</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            result = await self.api_client.explain_news(text)
            
            # Format response
            response = (
                f"<b>📊 АНАЛИЗ:</b>\n\n"
                f"{result.get('summary_text', 'Ошибка при анализе')}\n\n"
            )
            
            if result.get('impact_points'):
                response += "<b>📍 Ключевые моменты:</b>\n"
                for point in result.get('impact_points', []):
                    response += f"  • {point}\n"
            
            # Update processing message
            await processing_msg.edit_text(
                response,
                parse_mode=ParseMode.HTML
            )
            
            # Increment request counter
            self.user_service.increment_request_counter(user_id)
            
            # Add XP
            self.user_service.add_xp(user_id, 10)
            
            logger.info(f"✅ Message analyzed for user {user_id} (+10 XP)")
            
        except ConnectionError as e:
            await processing_msg.edit_text(
                f"❌ <b>Ошибка подключения</b>\n\n{str(e)}",
                parse_mode=ParseMode.HTML
            )
            logger.error(f"❌ Connection error: {e}")
        except Exception as e:
            await processing_msg.edit_text(
                f"❌ <b>Ошибка при анализе</b>\n\n{str(e)}",
                parse_mode=ParseMode.HTML
            )
            logger.error(f"❌ Error analyzing message: {e}")
