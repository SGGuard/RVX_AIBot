#!/usr/bin/env python3
"""
Тестирование модуля teach_lesson
"""

import asyncio
from teacher import teach_lesson, TEACHING_TOPICS, DIFFICULTY_LEVELS

async def test_teach():
    """Тестируем teach_lesson"""
    
    print("=" * 70)
    print("🎓 ТЕСТИРОВАНИЕ МОДУЛЯ TEACHING (v0.7.0)")
    print("=" * 70)
    print()
    
    print(f"📚 Доступные темы: {len(TEACHING_TOPICS)}")
    for topic_key, topic_info in TEACHING_TOPICS.items():
        print(f"  • {topic_key}: {topic_info.get('name', topic_key)}")
    
    print()
    print(f"📊 Доступные уровни: {len(DIFFICULTY_LEVELS)}")
    for level_key, level_info in DIFFICULTY_LEVELS.items():
        print(f"  • {level_key}: {level_info.get('emoji', '')} {level_info.get('name', level_key)}")
    
    print()
    print("-" * 70)
    print("🧪 ТЕСТИРОВАНИЕ: teach_lesson (crypto_basics, beginner)")
    print("-" * 70)
    
    try:
        result = await teach_lesson(
            topic="crypto_basics",
            difficulty_level="beginner"
        )
        
        if result:
            print("✅ Успешно получен урок!")
            print()
            print(f"📌 Название: {result.get('lesson_title', 'N/A')}")
            print(f"📝 Содержание (первые 100 символов): {result.get('content', 'N/A')[:100]}...")
            print(f"🔑 Ключевые моменты: {len(result.get('key_points', []))} точек")
            for i, point in enumerate(result.get('key_points', [])[:3], 1):
                print(f"   {i}. {point}")
            print(f"💡 Пример: {result.get('real_world_example', 'N/A')[:80]}...")
            print(f"❓ Вопрос: {result.get('practice_question', 'N/A')[:80]}...")
            print(f"📖 Рекомендуемые темы: {', '.join(result.get('next_topics', []))}")
        else:
            print("❌ Ошибка: teach_lesson вернул None")
    
    except Exception as e:
        print(f"❌ Исключение: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_teach())
