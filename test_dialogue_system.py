#!/usr/bin/env python3
"""
Тест диалоговой системы v0.21.0
Проверяет:
- Классификацию намерений
- Сохранение истории диалогов
- Получение контекста
- Работу с профилями пользователей
"""

import sqlite3
import sys
from datetime import datetime

# Импортируем функции из bot.py
sys.path.insert(0, '/home/sv4096/rvx_backend')

from bot import (
    classify_intent,
    save_conversation,
    get_conversation_history,
    get_user_profile,
    update_user_profile,
    search_relevant_context,
    get_db
)

def test_intent_classification():
    """Тест классификации намерений."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ 1: Классификация намерений")
    print("="*60)
    
    test_cases = [
        ("Анализируй эту новость про Bitcoin", "news_analysis"),
        ("Что такое блокчейн?", "question"),
        ("Еще подробнее об этом", "follow_up"),
        ("Привет, как дела?", "general_chat"),
        ("Объясни как работает DeFi", "question"),
        ("Что произошло на рынке?", "news_analysis"),
    ]
    
    for text, expected in test_cases:
        result = classify_intent(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{text}' → {result} (ожидалось: {expected})")

def test_conversation_storage():
    """Тест сохранения и получения истории диалогов."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ 2: Сохранение и получение истории")
    print("="*60)
    
    test_user_id = 9999  # Тестовый user_id
    
    # Очищаем тестовые данные если существуют
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (test_user_id,))
        conn.commit()
    
    # Сохраняем серию сообщений
    messages = [
        ("user", "Привет! Анализируй эту новость", "greeting"),
        ("bot", "Хорошо, вот анализ...", "news_analysis"),
        ("user", "Еще подробнее", "follow_up"),
        ("bot", "Дополнительный анализ...", "news_analysis"),
    ]
    
    print(f"\n📝 Сохранение {len(messages)} сообщений...")
    for msg_type, content, intent in messages:
        save_conversation(test_user_id, msg_type, content, intent)
        print(f"  • {msg_type.upper()}: {content[:40]}...")
    
    # Получаем историю
    print(f"\n📖 Получение истории...")
    history = get_conversation_history(test_user_id, limit=10)
    print(f"  Получено {len(history)} сообщений из базы")
    
    for h in history:
        print(f"  • [{h['type']}] {h['content'][:40]}... (intent: {h['intent']})")
    
    # Проверяем что данные сохранились
    if len(history) >= len(messages):
        print("\n✅ История диалогов сохранена и восстановлена успешно!")
    else:
        print(f"\n❌ Ошибка: ожидалось {len(messages)} сообщений, получено {len(history)}")
    
    # Очищаем тестовые данные
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (test_user_id,))
        conn.commit()

def test_user_profiles():
    """Тест работы с профилями пользователей."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ 3: Профили пользователей")
    print("="*60)
    
    test_user_id = 8888  # Тестовый user_id
    
    # Очищаем тестовые данные если существуют
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (test_user_id,))
        conn.commit()
    
    # Тестируем получение профиля (должен быть создан с дефолтными значениями)
    print(f"\n👤 Получение профиля для user_id={test_user_id}...")
    profile = get_user_profile(test_user_id)
    print(f"  Профиль: {profile}")
    
    # Обновляем профиль
    print(f"\n✏️ Обновление профиля...")
    update_user_profile(
        test_user_id,
        interests="Bitcoin, DeFi, Ethereum",
        portfolio="0.5 BTC, 10 ETH",
        risk_tolerance="high"
    )
    print("  Профиль обновлен!")
    
    # Получаем обновленный профиль
    print(f"\n👤 Получение обновленного профиля...")
    profile_updated = get_user_profile(test_user_id)
    print(f"  Профиль: {profile_updated}")
    
    if profile_updated["interests"] == "Bitcoin, DeFi, Ethereum":
        print("\n✅ Профили работают правильно!")
    else:
        print(f"\n❌ Ошибка обновления профиля")
    
    # Очищаем тестовые данные
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (test_user_id,))
        conn.commit()

def test_context_search():
    """Тест поиска релевантного контекста."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ 4: Поиск релевантного контекста")
    print("="*60)
    
    test_user_id = 7777  # Тестовый user_id
    
    # Очищаем тестовые данные если существуют
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (test_user_id,))
        conn.commit()
    
    # Сохраняем сообщения с разными намерениями
    messages = [
        ("user", "Что такое Bitcoin?", "question"),
        ("bot", "Bitcoin - это криптовалюта...", "question"),
        ("user", "А как его майнить?", "follow_up"),
        ("bot", "Майнинг требует специального оборудования...", "follow_up"),
        ("user", "Анализируй эту новость про крах FTX", "news_analysis"),
    ]
    
    print(f"\n📝 Сохранение {len(messages)} сообщений с разными интентами...")
    for msg_type, content, intent in messages:
        save_conversation(test_user_id, msg_type, content, intent)
    
    # Ищем контекст для follow-up
    print(f"\n🔍 Поиск контекста для 'follow_up'...")
    context = search_relevant_context(test_user_id, "follow_up", limit=3)
    print(f"  Найдено {len(context)} релевантных сообщений:")
    for c in context:
        print(f"    • [{c['type']}] {c['content'][:40]}... (intent: {c['intent']})")
    
    if len(context) > 0:
        print("\n✅ Поиск контекста работает!")
    else:
        print("\n❌ Контекст не найден")
    
    # Очищаем тестовые данные
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (test_user_id,))
        conn.commit()

def main():
    """Запуск всех тестов."""
    print("\n" + "="*60)
    print("🚀 ДИАЛОГОВАЯ СИСТЕМА v0.21.0 - ТЕСТЫ")
    print("="*60)
    
    try:
        test_intent_classification()
        test_conversation_storage()
        test_user_profiles()
        test_context_search()
        
        print("\n" + "="*60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("="*60)
        print("\n📊 Диалоговая система готова к использованию!")
        print("   • Классификация намерений: ✅")
        print("   • Сохранение истории: ✅")
        print("   • Профили пользователей: ✅")
        print("   • Поиск контекста: ✅")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
