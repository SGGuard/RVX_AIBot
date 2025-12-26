#!/usr/bin/env python3
"""
Поиск правильного ID канала @RVX_AI
"""
import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def find_channel():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    print("=" * 60)
    print("🔍 ПОИСК КАНАЛА @RVX_AI")
    print("=" * 60)
    
    # Список возможных ID для канала @RVX_AI
    possible_ids = [
        -1001228919683,  # Текущий ID
        -1001228919683,  # Преобразованный из 1228919683
        -1003228919683,  # Преобразованный из 3228919683
        "RVX_AI",        # Username
        "@RVX_AI",       # Username с @
    ]
    
    for channel_id in possible_ids:
        try:
            print(f"\n🔎 Проверяем ID: {channel_id}")
            chat = await bot.get_chat(channel_id)
            print(f"   ✅ НАЙДЕН КАНАЛ!")
            print(f"   Title: {chat.title}")
            print(f"   Type: {chat.type}")
            print(f"   ID: {chat.id}")
            print(f"   Username: @{chat.username if chat.username else 'N/A'}")
            print(f"\n   >>> Используйте ID: {chat.id}")
            
        except TelegramError as e:
            print(f"   ❌ Не найден: {str(e)[:60]}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(find_channel())
