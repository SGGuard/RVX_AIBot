#!/usr/bin/env python3
"""
✅ СИСТЕМА ПРОВЕРОК v0.22.1
Проверяем что бот правильно обрабатывает сообщения
"""

import sys
sys.path.insert(0, '/home/sv4096/rvx_backend')

import logging
from ai_dialogue import get_ai_response_sync

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

def test_ai_responses():
    """Тестируем различные типы сообщений"""
    
    test_cases = [
        {
            "name": "Простой вопрос",
            "message": "Что такое Ethereum?",
            "context": []
        },
        {
            "name": "Follow-up вопрос",
            "message": "Почему?",
            "context": [{"type": "bot", "content": "Ethereum это платформа для смартконтрактов"}]
        },
        {
            "name": "Диалог с историей",
            "message": "А как его использовать?",
            "context": [
                {"type": "user", "content": "Привет! Расскажи про Bitcoin"},
                {"type": "bot", "content": "Bitcoin это первая криптовалюта"},
                {"type": "user", "content": "Интересно!"},
                {"type": "bot", "content": "Да! И она безопасна"},
            ]
        },
    ]
    
    print("\n" + "="*70)
    print("🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ AI ДИАЛОГА v0.22.1")
    print("="*70)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Запрос: '{test['message']}'")
        
        response = get_ai_response_sync(test['message'], test['context'])
        
        if response:
            print(f"   ✅ Ответ: {response[:80]}...")
        else:
            print(f"   ❌ ОШИБКА: Ответ не получен")
            return False
    
    print("\n" + "="*70)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("="*70)
    return True

if __name__ == "__main__":
    success = test_ai_responses()
    sys.exit(0 if success else 1)
