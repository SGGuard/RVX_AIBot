"""
Daily Digest Scheduler v1.0
Отправляет ежедневный крипто-дайджест в Telegram канал в 9:00 утра

Функционал:
- 📊 Обзор рынка (BTC, ETH, топ альты)
- 😱 Fear & Greed Index
- 📈 Топ gainers & losers
- 📰 Последние новости
- ⏰ Календарь ключевых событий
"""

import logging
import asyncio
import os
from datetime import datetime, time as datetime_time
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv

from crypto_digest import collect_digest_data
from digest_formatter import format_digest

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DIGEST_CHANNEL_ID = os.getenv('DIGEST_CHANNEL_ID', '@RVX_AI')  # ID или @username канала
DIGEST_HOUR = int(os.getenv('DIGEST_HOUR', 9))  # Час отправки (9:00)
DIGEST_MINUTE = int(os.getenv('DIGEST_MINUTE', 0))  # Минуты отправки
DIGEST_TIMEZONE = os.getenv('DIGEST_TIMEZONE', 'UTC')  # Timezone

# Флаги функций
DIGEST_ENABLED = os.getenv('DIGEST_ENABLED', 'true').lower() == 'true'


class DailyDigestScheduler:
    """Планировщик для ежедневного дайджеста"""
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.bot: Optional[Bot] = None
        self.is_running = False
        
    async def initialize(self):
        """Инициализировать планировщик и бота"""
        try:
            self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
            self.scheduler = AsyncIOScheduler()
            
            # Добавляем задачу отправки дайджеста
            if DIGEST_ENABLED:
                self.scheduler.add_job(
                    self.send_daily_digest,
                    CronTrigger(
                        hour=DIGEST_HOUR,
                        minute=DIGEST_MINUTE,
                        timezone=DIGEST_TIMEZONE
                    ),
                    id='daily_digest',
                    name='Daily Crypto Digest',
                    misfire_grace_time=300,  # 5 минут допуска
                    max_instances=1  # Только один экземпляр в раз
                )
                logger.info(f"✅ Daily digest scheduled for {DIGEST_HOUR:02d}:{DIGEST_MINUTE:02d} UTC")
                logger.info(f"📢 Channel: {DIGEST_CHANNEL_ID}")
            else:
                logger.info("⏸️ Daily digest is disabled (DIGEST_ENABLED=false)")
            
            self.scheduler.start()
            self.is_running = True
            logger.info("🚀 Digest scheduler started")
            
        except Exception as e:
            logger.error(f"❌ Error initializing digest scheduler: {e}")
            raise
    
    async def send_daily_digest(self):
        """Собрать и отправить ежедневный дайджест"""
        try:
            logger.info(f"🔄 Starting daily digest collection at {datetime.now().isoformat()}")
            
            # Собираем данные
            digest_data = await collect_digest_data()
            
            if not digest_data.get("market_data"):
                logger.warning("⚠️ No market data collected, skipping digest send")
                return
            
            # Форматируем
            formatted_digest = format_digest(digest_data)
            
            if not formatted_digest:
                logger.warning("⚠️ Formatted digest is empty, skipping send")
                return
            
            # Отправляем в канал
            await self.send_message_safe(
                chat_id=DIGEST_CHANNEL_ID,
                text=formatted_digest,
                parse_mode='HTML'
            )
            
            logger.info("✅ Daily digest sent successfully")
            
        except Exception as e:
            logger.error(f"❌ Error sending daily digest: {e}", exc_info=True)
    
    async def send_message_safe(self, chat_id: str, text: str, parse_mode: str = 'HTML', 
                                max_retries: int = 3):
        """
        Безопасно отправить сообщение с повторными попытками
        
        Args:
            chat_id: ID или @username канала
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
            max_retries: Максимум попыток отправки
        """
        if not self.bot:
            logger.error("❌ Bot is not initialized")
            return
        
        # Преобразуем числовой ID группы в правильный формат для Telegram
        # Приватные группы: 1003228919683 -> -1001003228919683
        final_chat_id = chat_id
        if isinstance(chat_id, str) and chat_id.isdigit():
            channel_id_int = int(chat_id)
            if channel_id_int > 0:
                final_chat_id = -100 * (channel_id_int // 1000) - (channel_id_int % 1000)
        
        # Разбиваем на чанки если сообщение больше 4096 символов
        chunks = self._split_message(text, max_length=4096)
        
        for attempt in range(max_retries):
            try:
                for i, chunk in enumerate(chunks):
                    message = await self.bot.send_message(
                        chat_id=final_chat_id,
                        text=chunk,
                        parse_mode=parse_mode
                    )
                    
                    if i == 0:
                        logger.info(f"✅ Message sent to {chat_id} (part {i+1}/{len(chunks)})")
                    else:
                        logger.info(f"✅ Message part {i+1}/{len(chunks)} sent")
                
                break  # Успешно отправили
                
            except TelegramError as e:
                logger.error(f"⚠️ Attempt {attempt+1}/{max_retries} failed: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Экспоненциальная задержка
                    logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to send message after {max_retries} attempts")
                    raise
    
    @staticmethod
    def _split_message(text: str, max_length: int = 4096) -> list:
        """
        Разбить сообщение на части если оно слишком длинное
        """
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        for line in text.split('\n'):
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part)
                current_part = line
            else:
                current_part += ('\n' if current_part else '') + line
        
        if current_part:
            parts.append(current_part)
        
        return parts
    
    async def stop(self):
        """Остановить планировщик"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("✅ Digest scheduler stopped")
        
        if self.bot:
            await self.bot.close()


# ============================================================================
# ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ ДОСТУПА ИЗ BOT.PY
# ============================================================================

_digest_scheduler: Optional[DailyDigestScheduler] = None


async def initialize_digest_scheduler() -> DailyDigestScheduler:
    """Инициализировать глобальный планировщик дайджеста"""
    global _digest_scheduler
    
    if _digest_scheduler is None:
        _digest_scheduler = DailyDigestScheduler()
        await _digest_scheduler.initialize()
    
    return _digest_scheduler


async def stop_digest_scheduler():
    """Остановить глобальный планировщик дайджеста"""
    global _digest_scheduler
    
    if _digest_scheduler:
        await _digest_scheduler.stop()
        _digest_scheduler = None


def get_digest_scheduler() -> Optional[DailyDigestScheduler]:
    """Получить текущий планировщик дайджеста"""
    return _digest_scheduler


# ============================================================================
# ТЕСТИРОВАНИЕ
# ============================================================================

async def test_digest():
    """Тестировать сбор и форматирование дайджеста"""
    print("\n📊 Testing digest collection...\n")
    
    try:
        digest_data = await collect_digest_data()
        
        if digest_data.get("market_data"):
            print(f"✅ Market data: {len(digest_data['market_data'])} coins")
        else:
            print("⚠️ No market data")
        
        print(f"Fear & Greed: {digest_data.get('fear_greed', {}).get('value_classification', 'N/A')}")
        print(f"News items: {len(digest_data.get('news', []))}")
        print(f"Events: {len(digest_data.get('events', []))}")
        
        formatted = format_digest(digest_data)
        print(f"\n📝 Formatted digest length: {len(formatted)} chars")
        print(f"\n📄 Preview (first 500 chars):\n")
        print(formatted[:500] + "...")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Тест
    asyncio.run(test_digest())
