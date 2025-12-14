"""
Bot Core - основной файл инициализации и конфигурации бота.

Структурирует весь бот вокруг принципов SOLID и DRY.
"""

import os
import logging
from typing import Optional
from datetime import datetime

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    filters, ContextTypes
)

from .handlers import CommandHandler as CmdHandler, MessageHandler as MsgHandler, ButtonHandler as BtnHandler
from .services import UserService, LessonService, QuestService, APIClientService

load_dotenv()

logger = logging.getLogger("bot_core")

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = os.getenv("API_URL_NEWS", "http://localhost:8000/explain_news")
API_KEY = os.getenv("BOT_API_KEY", "")
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))


class BotCore:
    """Central bot core for initialization and management."""
    
    def __init__(self):
        """Initialize bot core."""
        self.application: Optional[Application] = None
        self.cmd_handler: Optional[CmdHandler] = None
        self.msg_handler: Optional[MsgHandler] = None
        self.btn_handler: Optional[BtnHandler] = None
        
        # Initialize services
        self.user_service = UserService()
        self.lesson_service = LessonService()
        self.quest_service = QuestService()
        self.api_client = APIClientService(API_URL, API_KEY)
    
    async def post_init(self, app: Application) -> None:
        """Post-initialization setup (lifespan)."""
        logger.info("🚀 Bot starting...")
        logger.info(f"🤖 API URL: {API_URL}")
        logger.info(f"📊 Services initialized")
    
    async def post_shutdown(self, app: Application) -> None:
        """Shutdown cleanup (lifespan)."""
        logger.info("🛑 Bot shutting down...")
    
    def setup_handlers(self) -> None:
        """Setup command, message, and callback handlers."""
        if not self.application:
            raise RuntimeError("Application not initialized")
        
        # Initialize handler instances
        self.cmd_handler = CmdHandler(self.user_service, self.lesson_service)
        self.msg_handler = MsgHandler(self.user_service, self.api_client)
        self.btn_handler = ButtonHandler(self.user_service, self.lesson_service, self.quest_service)
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_handler.handle_start))
        self.application.add_handler(CommandHandler("help", self.cmd_handler.handle_help))
        self.application.add_handler(CommandHandler("stats", self.cmd_handler.handle_stats))
        self.application.add_handler(CommandHandler("learn", self.cmd_handler.handle_learn))
        
        # Add message handler for text
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.msg_handler.handle_text_message
        ))
        
        # Add callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(self.btn_handler.handle_callback))
        
        logger.info("✅ Handlers registered")
    
    def setup_bot_commands(self) -> None:
        """Setup bot commands list for Telegram."""
        if not self.application:
            raise RuntimeError("Application not initialized")
        
        commands = [
            BotCommand("start", "Начать бот"),
            BotCommand("help", "Показать справку"),
            BotCommand("learn", "Просмотр курсов"),
            BotCommand("stats", "Ваша статистика"),
            BotCommand("quests", "Ежедневные квесты"),
            BotCommand("menu", "Главное меню"),
        ]
        
        # This would be called during lifespan
        logger.info(f"✅ Bot commands configured ({len(commands)} commands)")
    
    async def run(self) -> None:
        """Run the bot."""
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        
        # Create application
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Setup lifespan callbacks
        self.application.post_init = self.post_init
        self.application.post_shutdown = self.post_shutdown
        
        # Setup handlers
        self.setup_handlers()
        self.setup_bot_commands()
        
        # Start polling
        logger.info("🎯 Starting polling...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=["message", "callback_query"])
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Shutdown signal received")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


# Global bot instance
_bot_core_instance: Optional[BotCore] = None


def get_bot_core() -> BotCore:
    """Get or create bot core instance."""
    global _bot_core_instance
    if _bot_core_instance is None:
        _bot_core_instance = BotCore()
    return _bot_core_instance


async def main() -> None:
    """Main entry point."""
    bot = get_bot_core()
    await bot.run()


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
