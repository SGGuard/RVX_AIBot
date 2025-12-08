#!/usr/bin/env python3
"""
Скрипт для тестирования бота через Telegram API.
Отправляет тестовые сообщения для проверки работы анализа новостей.
"""

import requests
import json
import time
from datetime import datetime

# Конфигурация (нужно получить из переменных окружения или .env)
BOT_TOKEN = "REDACTED"
TELEGRAM_API = "https://api.telegram.org/bot"

# ID тестового пользователя (нужно использовать реальный chat_id)
TEST_USER_CHAT_ID = "YOUR_CHAT_ID_HERE"  # Замените на реальный chat_id

def send_message_to_telegram(chat_id: str, text: str):
    """Отправляет сообщение в Telegram."""
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Сообщение отправлено (длина: {len(text)} символов)")
            return True
        else:
            print(f"❌ Ошибка отправки: статус {response.status_code}")
            print(f"   Ответ: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    print("\n" + "=" * 70)
    print("🤖 БОТА ТЕСТИРОВАНИЕ - Проверка анализа новостей")
    print("=" * 70)
    
    if TEST_USER_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("\n⚠️  ВНИМАНИЕ:")
        print("   Нужно установить TEST_USER_CHAT_ID в скрипте!")
        print("   Как узнать свой chat_id:")
        print("   1. Напишите боту /start")
        print("   2. Сообщите мне ваш chat_id (будет выведен в логах)")
        print("   3. Обновите скрипт и запустите снова")
        return
    
    print(f"\n📱 Будут отправлены тестовые сообщения на chat_id: {TEST_USER_CHAT_ID}")
    print(f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    test_messages = [
        ("🔔 Привет, бот!", "Тест приветствия"),
        ("Bitcoin стоит $45,000", "Тест криптоновости #1"),
        ("Ethereum обновилась до Shanghai", "Тест криптоновости #2"),
        ("SEC одобрила спотовый Bitcoin ETF, это огромный шаг для легализации крипто в США", "Тест подробной новости"),
    ]
    
    for i, (message, description) in enumerate(test_messages, 1):
        print(f"\n📨 ТЕСТ #{i}: {description}")
        print(f"   💬 Сообщение: {message}")
        
        if send_message_to_telegram(TEST_USER_CHAT_ID, message):
            print(f"   ⏳ Ожидание ответа бота...")
            time.sleep(2)
        else:
            print(f"   ⚠️  Пропуск теста")
        
        if i < len(test_messages):
            time.sleep(1)
    
    print(f"\n" + "=" * 70)
    print("✅ Тестирование завершено")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
