#!/usr/bin/env python3
"""
Простой тест встроенного преподавателя
"""
import asyncio
from embedded_teacher import get_embedded_lesson, get_all_topics, get_difficulties_for_topic

def test_embedded_teacher():
    print("=" * 80)
    print("🧪 ТЕСТ ВСТРОЕННОГО ПРЕПОДАВАТЕЛЯ")
    print("=" * 80)
    
    # Тест 1: Получить все топики
    print("\n📚 Доступные топики:")
    topics = get_all_topics()
    for topic in topics:
        print(f"  • {topic}")
    
    # Тест 2: Получить все уровни сложности для каждого топика
    print("\n📊 Уровни сложности по топикам:")
    for topic in topics:
        difficulties = get_difficulties_for_topic(topic)
        print(f"  {topic}: {', '.join(difficulties)}")
    
    # Тест 3: Загрузить несколько уроков
    print("\n🎓 Загрузка примеров уроков:")
    test_cases = [
        ("bitcoin", "beginner"),
        ("ethereum", "intermediate"),
        ("blockchain", "advanced"),
        ("defi", "beginner"),
    ]
    
    for topic, difficulty in test_cases:
        lesson = get_embedded_lesson(topic, difficulty)
        if lesson:
            print(f"\n  ✅ {topic.upper()} ({difficulty}):")
            print(f"     Название: {lesson.lesson_title}")
            print(f"     Контент: {len(lesson.content)} символов")
            print(f"     Ключевые пункты: {len(lesson.key_points)}")
            print(f"     Примеры: {len(lesson.real_world_example)} символов")
            print(f"     Вопрос: {lesson.practice_question[:50]}...")
            print(f"     Следующие темы: {', '.join(lesson.next_topics)}")
        else:
            print(f"\n  ❌ {topic.upper()} ({difficulty}): Не найден")
    
    # Тест 4: Попробовать неправильный топик
    print("\n\n🚫 Тест обработки несуществующего топика:")
    fake_topic = "fake_topic_12345"
    fake_lesson = get_embedded_lesson(fake_topic, "beginner")
    print(f"  Результат: {'ОШИБКА' if fake_lesson is None else 'НАЙДЕН (должна быть ошибка!)'}")
    
    print("\n" + "=" * 80)
    print("✅ ВСЕ ТЕСТЫ УСПЕШНЫ")
    print("=" * 80)

if __name__ == "__main__":
    test_embedded_teacher()
