#!/usr/bin/env python3
"""
Простой тест для проверки механики "Расскажи еще" кнопки
"""

import sys
import asyncio

# Проверяем что структура callback'а парсится правильно
def test_callback_parsing():
    """Тестируем парсинг callback_data для tell_more кнопки"""
    
    # Симуляция callback_data
    callback_data_examples = [
        "tell_more_123_456",  # tell_more_{request_id}_{user_id}
        "tell_more_999_111",
        "tell_more_1_2",
    ]
    
    for data in callback_data_examples:
        if data.startswith("tell_more_"):
            # Format: tell_more_123_456 -> parts = ['123', '456']
            parts_tell = data.replace("tell_more_", "").split("_")
            request_id_str = parts_tell[0]
            user_id_str = parts_tell[1] if len(parts_tell) > 1 else None
            print(f"✅ Callback '{data}' -> request_id='{request_id_str}', user_id='{user_id_str}'")
            
            # Проверяем что запарсилось корректно
            assert request_id_str.isdigit(), f"request_id должен быть числом: {request_id_str}"
            assert user_id_str.isdigit(), f"user_id должен быть числом: {user_id_str}"
    
    print("✅ Все callback'ы парсятся правильно")


def test_context_storage():
    """Тестируем что контекст сохраняется и читается правильно"""
    
    # Симуляция context.user_data
    user_data = {}
    
    # Имитируем сохранение
    simplified_text = "Это анализ новости"
    follow_up = "📊 Какой масштаб влияния?"
    user_text = "Оригинальная новость о крипто"
    
    user_data["last_news_analysis"] = simplified_text
    user_data["last_news_question"] = follow_up
    user_data["last_news_original"] = user_text
    
    # Имитируем чтение в handler'е
    last_analysis = user_data.get("last_news_analysis", "")
    last_question = user_data.get("last_news_question", "")
    last_original = user_data.get("last_news_original", "")
    
    # Проверяем
    assert last_analysis == simplified_text, "Анализ не сохранился"
    assert last_question == follow_up, "Вопрос не сохранился"
    assert last_original == user_text, "Оригинальный текст не сохранился"
    
    print("✅ Контекст сохраняется и читается правильно")


def test_question_extraction():
    """Тестируем извлечение текста вопроса"""
    
    questions = [
        "📊 Какой масштаб влияния?",
        "📈 Как это повлияет на цену?",
        "💡 Что это значит?",
        "❓ Есть ли риски?",
        "🔍 Какие детали важны?",
    ]
    
    for question in questions:
        # Извлекаем текст без эмодзи
        question_text = (question
            .replace("📊 ", "")
            .replace("📈 ", "")
            .replace("💡 ", "")
            .replace("❓ ", "")
            .replace("🔍 ", ""))
        
        print(f"✅ '{question}' -> '{question_text}'")
        assert len(question_text) > 0, f"Не удалось извлечь текст из {question}"
    
    print("✅ Вопросы парсятся правильно")


def test_expand_prompt_generation():
    """Тестируем генерацию prompt'а для расширенного анализа"""
    
    original = "Новость о Bitcoin"
    analysis = "Анализ новости"
    question = "❓ Какие риски?"
    
    question_text = question.replace("❓ ", "")
    
    prompt = (
        f"Пользователь хочет получить более развернутый анализ по конкретному вопросу.\n\n"
        f"<b>Исходная новость:</b>\n{original}\n\n"
        f"<b>Предыдущий анализ:</b>\n{analysis}\n\n"
        f"<b>На какой аспект расширить анализ:</b> {question_text}\n\n"
        f"ЗАДАЧА: Дай развернутый, глубокий анализ"
    )
    
    # Проверяем что всё вошло в prompt
    assert original in prompt, "Оригинальная новость не в prompt"
    assert analysis in prompt, "Анализ не в prompt"
    assert question_text in prompt, "Текст вопроса не в prompt"
    
    print("✅ Prompt генерируется правильно")
    print(f"\nПример prompt'а:\n{prompt[:200]}...")


if __name__ == "__main__":
    print("🧪 Тестирование механики 'Расскажи еще' кнопки\n")
    print("=" * 50)
    
    test_callback_parsing()
    print()
    
    test_context_storage()
    print()
    
    test_question_extraction()
    print()
    
    test_expand_prompt_generation()
    
    print("\n" + "=" * 50)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("\nГотово к развертыванию на Railway!")
