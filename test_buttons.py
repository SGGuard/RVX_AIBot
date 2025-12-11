#!/usr/bin/env python3
"""
Тест проверки всех callback_data кнопок из приветственного сообщения
"""

import asyncio
import sys
from unittest.mock import Mock, AsyncMock, patch

# Добавляем путь к bot модулю
sys.path.insert(0, '/home/sv4096/rvx_backend')

from telegram import Update, User, Chat, CallbackQuery, Message
from telegram.ext import ContextTypes

# Тестируемые callback_data с приветственной страницы
TEST_CALLBACKS = [
    "start_teach",
    "start_learn",
    "start_stats",
    "start_leaderboard",
    "start_quests",
    "start_resources",
    "start_bookmarks",
    "start_drops",
    "start_activities",
    "start_history",
    "start_menu",
    "back_to_start"
]

async def test_callback(callback_data):
    """Тест одного callback_data"""
    print(f"\n📍 Тестирование: {callback_data}")
    
    try:
        # Создаем mock объекты
        user = Mock(spec=User)
        user.id = 12345
        user.username = "test_user"
        user.first_name = "Test"
        
        chat = Mock(spec=Chat)
        chat.id = 12345
        
        message = Mock(spec=Message)
        message.chat = chat
        
        query = Mock(spec=CallbackQuery)
        query.from_user = user
        query.data = callback_data
        query.message = message
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        
        update = Mock(spec=Update)
        update.effective_user = user
        update.callback_query = query
        update.message = None
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        context.bot = AsyncMock()
        context.args = None
        
        # Импортируем button_callback функцию
        from bot import button_callback
        
        # Вызываем функцию
        await button_callback(update, context)
        
        print(f"✅ {callback_data} - OK")
        return True
        
    except Exception as e:
        print(f"❌ {callback_data} - ERROR: {str(e)[:100]}")
        return False

async def main():
    """Запуск тестов всех кнопок"""
    print("=" * 50)
    print("🧪 ТЕСТ ВСЕХ КНОПОК ИЗ ПРИВЕТСТВИЯ")
    print("=" * 50)
    
    results = []
    
    # Тестируем каждый callback
    for callback_data in TEST_CALLBACKS:
        try:
            result = await test_callback(callback_data)
            results.append((callback_data, result))
        except Exception as e:
            print(f"❌ {callback_data} - FATAL: {str(e)[:100]}")
            results.append((callback_data, False))
    
    # Итоги
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ")
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for callback_data, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {callback_data}")
    
    print("\n" + "=" * 50)
    print(f"Пройдено: {passed}/{total}")
    
    if passed == total:
        print("🎉 ВСЕ КНОПКИ РАБОТАЮТ!")
    else:
        print(f"⚠️ {total - passed} кнопок имеют проблемы")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
