"""
🧪 Test: Встроенный анализатор новостей
"""
import asyncio
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем анализатор
from embedded_news_analyzer import analyze_news, sanitize_input, hash_text

async def test_embedded_analyzer():
    """Тестируем встроенный анализатор"""
    
    # Примеры новостей для тестирования
    test_news = [
        "Bitcoin reached a new all-time high of $100,000 today, driven by institutional investment and positive market sentiment. The cryptocurrency market cap exceeded $5 trillion for the first time.",
        "Ethereum's Shanghai upgrade has been successfully deployed, enabling staking and reducing energy consumption by 95%. Validators are now earning rewards for securing the network.",
        "Tesla announced a new AI chip for autonomous driving, claiming 10x performance improvement over previous generation. The chip is based on a novel neural architecture optimized for real-time processing.",
    ]
    
    print("=" * 80)
    print("🧪 ТЕСТ: Встроенный анализатор новостей v1.0")
    print("=" * 80)
    
    for i, news in enumerate(test_news, 1):
        print(f"\n📰 Тест #{i}")
        print(f"Текст: {news[:80]}...")
        print(f"Длина: {len(news)} символов")
        
        try:
            # Проверяем валидацию
            clean_text = sanitize_input(news)
            text_hash = hash_text(news)
            print(f"✅ Валидация: OK")
            print(f"🔐 Hash: {text_hash[:16]}...")
            
            # Запускаем анализ
            print(f"⏳ Анализ в прогрессе...")
            result = await analyze_news(news, user_id=7216426044)
            
            # Выводим результаты
            print(f"\n📊 Результаты:")
            print(f"  Provider: {result.get('provider', 'unknown')}")
            print(f"  Processing: {result.get('processing_time_ms', 0)}ms")
            print(f"  Cached: {result.get('cached', False)}")
            print(f"\n📝 Анализ (первые 200 символов):")
            summary = result.get('simplified_text', '')[:200]
            print(f"  {summary}...")
            
            print(f"\n💡 Ключевые моменты:")
            impact_points = result.get('impact_points', [])
            for j, point in enumerate(impact_points[:3], 1):
                print(f"  {j}. {point}")
            
            print("\n✅ Тест пройден!")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ Все тесты завершены!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_embedded_analyzer())
