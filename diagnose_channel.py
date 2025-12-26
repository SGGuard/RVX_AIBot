#!/usr/bin/env python3
"""
Диагностика канала для проверки конфигурации подписки
"""
import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANDATORY_CHANNEL_ID = -1001228919683  # RVX_AI channel
CHANNEL_USERNAME = "RVX_AI"

async def diagnose():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    print("=" * 60)
    print("🔍 ДИАГНОСТИКА КАНАЛА RVX_AI")
    print("=" * 60)
    
    try:
        # Проверяем информацию о боте
        print("\n1️⃣  Информация о боте:")
        me = await bot.get_me()
        print(f"   Bot ID: {me.id}")
        print(f"   Bot username: @{me.username}")
        print(f"   Bot name: {me.first_name}")
        
        # Проверяем информацию о канале
        print(f"\n2️⃣  Информация о канале:")
        try:
            chat = await bot.get_chat(MANDATORY_CHANNEL_ID)
            print(f"   ✅ Канал найден: {chat.title}")
            print(f"   Type: {chat.type}")
            print(f"   Channel username: @{chat.username}")
            
            # Проверяем статус бота в канале
            print(f"\n3️⃣  Статус бота в канале:")
            try:
                member = await bot.get_chat_member(MANDATORY_CHANNEL_ID, me.id)
                print(f"   ✅ Статус бота: {member.status}")
                print(f"   Can manage messages: {member.can_manage_messages}")
                print(f"   Can delete messages: {member.can_delete_messages}")
                print(f"   Can restrict members: {member.can_restrict_members}")
                
                if member.status not in ["administrator", "creator"]:
                    print(f"\n   ⚠️  ВНИМАНИЕ: Бот не является администратором!")
                    print(f"   Требуется: administrator или creator")
                    print(f"   Текущий статус: {member.status}")
                else:
                    print(f"\n   ✅ Бот имеет необходимые права")
                    
            except TelegramError as e:
                print(f"   ❌ Ошибка получения статуса бота: {e}")
        
        except TelegramError as e:
            print(f"   ❌ Ошибка получения информации о канале: {e}")
            print(f"   Channel ID: {MANDATORY_CHANNEL_ID}")
        
        # Проверяем возможность получить информацию о членстве пользователя
        print(f"\n4️⃣  Проверка членства (тестирование на примере бота):")
        try:
            test_member = await bot.get_chat_member(MANDATORY_CHANNEL_ID, me.id)
            print(f"   ✅ Можно получить информацию о членстве")
            print(f"   Статус: {test_member.status}")
        except TelegramError as e:
            print(f"   ❌ Ошибка при получении информации о членстве: {e}")
            print(f"   Это означает, что проверка подписки может не работать!")
        
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ ДИАГНОСТИКИ:")
        print("=" * 60)
        print(f"Канал: @{CHANNEL_USERNAME}")
        print(f"Channel ID: {MANDATORY_CHANNEL_ID}")
        print(f"Бот: @{me.username}")
        print("\nДля работы проверки подписки требуется:")
        print("1. Бот должен быть администратором в канале")
        print("2. Бот должен иметь права на управление сообщениями")
        print("3. Канал должен быть доступен для проверки членства")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
