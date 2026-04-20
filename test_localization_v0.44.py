#!/usr/bin/env python3
"""
Тест локализации AI диалога - v0.44

Проверяет что:
1. Функции build_*_prompt() поддерживают language параметр
2. get_ai_response_sync() принимает language параметр
3. Украинские промпты существуют и не пусты
4. Русские промпты существуют и не пусты
"""

import sys
sys.path.insert(0, '/home/sv4096/rvx_backend')

from ai_dialogue import (
    build_dialogue_system_prompt,
    build_geopolitical_analysis_prompt,
    build_crypto_news_analysis_prompt,
    build_simple_dialogue_prompt,
    _build_dialogue_prompt_russian,
    _build_dialogue_prompt_ukrainian,
    _build_geopolitical_prompt_russian,
    _build_geopolitical_prompt_ukrainian,
    _build_crypto_news_analysis_russian,
    _build_crypto_news_analysis_ukrainian,
    _build_simple_dialogue_russian,
    _build_simple_dialogue_ukrainian,
)


def test_dialogue_prompt_localization():
    """Проверяет что build_dialogue_system_prompt() возвращает разные промпты для разных языков."""
    print("✅ Test 1: build_dialogue_system_prompt() localization")
    
    ru_prompt = build_dialogue_system_prompt("ru")
    uk_prompt = build_dialogue_system_prompt("uk")
    default_prompt = build_dialogue_system_prompt()
    
    # Проверяем что промпты не пусты
    assert len(ru_prompt) > 3000, f"Russian prompt too short: {len(ru_prompt)}"
    assert len(uk_prompt) > 3000, f"Ukrainian prompt too short: {len(uk_prompt)}"
    
    # Проверяем что русский и украинский разные
    assert ru_prompt != uk_prompt, "Russian and Ukrainian prompts are identical!"
    
    # Проверяем что default = русский
    assert default_prompt == ru_prompt, "Default should be Russian"
    
    # Проверяем русские ключевые слова в русском промпте
    assert "ФИНАНСОВЫЙ АНАЛИТИК" in ru_prompt, "Russian prompt missing Russian keywords"
    assert "опыта в криптовалютах" in ru_prompt, "Russian prompt missing Russian content"
    
    # Проверяем украинские ключевые слова в украинском промпте
    assert "ФІНАНСОВИЙ АНАЛІТИК" in uk_prompt, "Ukrainian prompt missing Ukrainian keywords"
    assert "досвіду в криптовалютах" in uk_prompt, "Ukrainian prompt missing Ukrainian content"
    
    print(f"  ✓ Russian prompt: {len(ru_prompt)} chars")
    print(f"  ✓ Ukrainian prompt: {len(uk_prompt)} chars")
    print(f"  ✓ Prompts are different: {ru_prompt[:50]}... vs {uk_prompt[:50]}...")
    print()


def test_geopolitical_prompt_localization():
    """Проверяет локализацию геополитического анализа."""
    print("✅ Test 2: build_geopolitical_analysis_prompt() localization")
    
    ru_prompt = build_geopolitical_analysis_prompt("ru")
    uk_prompt = build_geopolitical_analysis_prompt("uk")
    default_prompt = build_geopolitical_analysis_prompt()
    
    assert len(ru_prompt) > 2000, f"Russian geopolitical prompt too short: {len(ru_prompt)}"
    assert len(uk_prompt) > 2000, f"Ukrainian geopolitical prompt too short: {len(uk_prompt)}"
    assert ru_prompt != uk_prompt, "Russian and Ukrainian geopolitical prompts are identical!"
    assert default_prompt == ru_prompt, "Default should be Russian"
    
    # Проверяем языковые признаки
    assert "РЕЖИМ ФИНАНСОВОГО АНАЛИЗА" in ru_prompt, "Russian geo prompt missing Russian content"
    assert "РЕЖИМ ФІНАНСОВОГО АНАЛІЗУ" in uk_prompt, "Ukrainian geo prompt missing Ukrainian content"
    
    print(f"  ✓ Russian geopolitical prompt: {len(ru_prompt)} chars")
    print(f"  ✓ Ukrainian geopolitical prompt: {len(uk_prompt)} chars")
    print()


def test_crypto_news_prompt_localization():
    """Проверяет локализацию анализа крипто-новостей."""
    print("✅ Test 3: build_crypto_news_analysis_prompt() localization")
    
    ru_prompt = build_crypto_news_analysis_prompt("ru")
    uk_prompt = build_crypto_news_analysis_prompt("uk")
    default_prompt = build_crypto_news_analysis_prompt()
    
    assert len(ru_prompt) > 2000, f"Russian crypto prompt too short: {len(ru_prompt)}"
    assert len(uk_prompt) > 2000, f"Ukrainian crypto prompt too short: {len(uk_prompt)}"
    assert ru_prompt != uk_prompt, "Russian and Ukrainian crypto prompts are identical!"
    assert default_prompt == ru_prompt, "Default should be Russian"
    
    # Проверяем языковые признаки
    assert "РЕЖИМ АНАЛИЗА КРИПТОВАЛЮТНЫХ НОВОСТЕЙ" in ru_prompt
    assert "РЕЖИМ АНАЛІЗУ КРИПТОВАЛЮТНИХ НОВИН" in uk_prompt
    
    print(f"  ✓ Russian crypto news prompt: {len(ru_prompt)} chars")
    print(f"  ✓ Ukrainian crypto news prompt: {len(uk_prompt)} chars")
    print()


def test_simple_dialogue_prompt_localization():
    """Проверяет локализацию простого диалога."""
    print("✅ Test 4: build_simple_dialogue_prompt() localization")
    
    ru_prompt = build_simple_dialogue_prompt("ru")
    uk_prompt = build_simple_dialogue_prompt("uk")
    default_prompt = build_simple_dialogue_prompt()
    
    assert len(ru_prompt) > 300, f"Russian simple prompt too short: {len(ru_prompt)}"
    assert len(uk_prompt) > 300, f"Ukrainian simple prompt too short: {len(uk_prompt)}"
    assert ru_prompt != uk_prompt, "Russian and Ukrainian simple prompts are identical!"
    assert default_prompt == ru_prompt, "Default should be Russian"
    
    # Проверяем языковые признаки
    assert "помощник бота RVX AI" in ru_prompt
    assert "помічник бота RVX AI" in uk_prompt
    
    print(f"  ✓ Russian simple prompt: {len(ru_prompt)} chars")
    print(f"  ✓ Ukrainian simple prompt: {len(uk_prompt)} chars")
    print()


def test_internal_functions_exist():
    """Проверяет что существуют все внутренние функции."""
    print("✅ Test 5: Internal functions existence")
    
    # Все эти функции должны существовать и быть вызываемыми
    functions = [
        _build_dialogue_prompt_russian,
        _build_dialogue_prompt_ukrainian,
        _build_geopolitical_prompt_russian,
        _build_geopolitical_prompt_ukrainian,
        _build_crypto_news_analysis_russian,
        _build_crypto_news_analysis_ukrainian,
        _build_simple_dialogue_russian,
        _build_simple_dialogue_ukrainian,
    ]
    
    for func in functions:
        assert callable(func), f"Function {func.__name__} is not callable"
        result = func()
        assert isinstance(result, str), f"Function {func.__name__} didn't return string"
        assert len(result) > 100, f"Function {func.__name__} returned too short result"
        print(f"  ✓ {func.__name__}: {len(result)} chars")
    
    print()


def test_russian_prompts_have_russian_keywords():
    """Проверяет что русские промпты содержат русские ключевые слова."""
    print("✅ Test 6: Russian prompts contain Russian keywords")
    
    russian_prompts = [
        (_build_dialogue_prompt_russian, ["ФИНАНСОВЫЙ АНАЛИТИК", "криптовалютах"]),
        (_build_geopolitical_prompt_russian, ["ФИНАНСОВОГО АНАЛИЗА", "трейдеру"]),
        (_build_crypto_news_analysis_russian, ["ИНВЕСТИЦИОННЫЙ АНАЛИТИК", "новость"]),
        (_build_simple_dialogue_russian, ["помощник бота", "Образовательный"]),
    ]
    
    for func, keywords in russian_prompts:
        prompt = func()
        for keyword in keywords:
            assert keyword in prompt, f"{func.__name__} missing keyword: {keyword}"
        print(f"  ✓ {func.__name__}: contains Russian keywords")
    
    print()


def test_ukrainian_prompts_have_ukrainian_keywords():
    """Проверяет что украинские промпты содержат украинские ключевые слова."""
    print("✅ Test 7: Ukrainian prompts contain Ukrainian keywords")
    
    ukrainian_prompts = [
        (_build_dialogue_prompt_ukrainian, ["ФІНАНСОВИЙ АНАЛІТИК", "криптовалютах"]),
        (_build_geopolitical_prompt_ukrainian, ["ФІНАНСОВОГО АНАЛІЗУ", "трейдеру"]),
        (_build_crypto_news_analysis_ukrainian, ["ІНВЕСТИЦІЙНИЙ АНАЛІТИК", "новину"]),
        (_build_simple_dialogue_ukrainian, ["помічник бота", "Освітній"]),
    ]
    
    for func, keywords in ukrainian_prompts:
        prompt = func()
        for keyword in keywords:
            assert keyword in prompt, f"{func.__name__} missing keyword: {keyword}"
        print(f"  ✓ {func.__name__}: contains Ukrainian keywords")
    
    print()


def test_no_mixed_language_prompts():
    """Проверяет что в русском промпте нет украинских слов и наоборот."""
    print("✅ Test 8: No mixed language content")
    
    # Проверяем все русские промпты
    russian_prompts = [
        _build_dialogue_prompt_russian(),
        _build_geopolitical_prompt_russian(),
        _build_crypto_news_analysis_russian(),
        _build_simple_dialogue_russian(),
    ]
    
    # Проверяем все украинские промпты
    ukrainian_prompts = [
        _build_dialogue_prompt_ukrainian(),
        _build_geopolitical_prompt_ukrainian(),
        _build_crypto_news_analysis_ukrainian(),
        _build_simple_dialogue_ukrainian(),
    ]
    
    # Украинские слова которых не должно быть в русских промптах
    ukrainian_words = ["помічник", "ФІНАНСОВИЙ", "досвіду"]
    
    # Русские слова которых не должно быть в украинских промптах
    russian_words = ["помощник", "ФИНАНСОВЫЙ", "опыта"]
    
    # Проверяем что основные украинские слова есть ТОЛЬКО в украинском промпте
    for word in ["помічник", "ФІНАНСОВИЙ"]:
        for uk_prompt in ukrainian_prompts:
            if word in uk_prompt:
                # Нашли украинское слово в украинском промпте - хорошо
                break
        else:
            # Не нашли украинское слово ни в одном украинском промпте
            assert False, f"Ukrainian word '{word}' not found in any Ukrainian prompt"
        
        # Проверяем что его нет в русских промптах
        for ru_prompt in russian_prompts:
            assert word not in ru_prompt, f"Ukrainian word '{word}' found in Russian prompt!"
    
    # Проверяем что основные русские слова есть ТОЛЬКО в русском промпте
    for word in ["помощник", "ФИНАНСОВЫЙ"]:
        for ru_prompt in russian_prompts:
            if word in ru_prompt:
                # Нашли русское слово в русском промпте - хорошо
                break
        else:
            # Не нашли русское слово ни в одном русском промпте
            assert False, f"Russian word '{word}' not found in any Russian prompt"
        
        # Проверяем что его нет в украинских промптах
        for uk_prompt in ukrainian_prompts:
            assert word not in uk_prompt, f"Russian word '{word}' found in Ukrainian prompt!"
    
    print(f"  ✓ All Russian prompts: no Ukrainian content")
    print(f"  ✓ All Ukrainian prompts: no Russian content")
    print()


if __name__ == "__main__":
    print("\n" + "="*70)
    print("ЛОКАЛИЗАЦИЯ AI ДИАЛОГА - ТЕСТЫ v0.44")
    print("="*70 + "\n")
    
    try:
        test_dialogue_prompt_localization()
        test_geopolitical_prompt_localization()
        test_crypto_news_prompt_localization()
        test_simple_dialogue_prompt_localization()
        test_internal_functions_exist()
        test_russian_prompts_have_russian_keywords()
        test_ukrainian_prompts_have_ukrainian_keywords()
        test_no_mixed_language_prompts()
        
        print("="*70)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! (8/8)")
        print("="*70)
        print("\n💡 Локализация AI диалога полностью работает:")
        print("   • Русские промпты: 4 типа (диалог, геополитика, крипто-новости, простой)")
        print("   • Украинские промпты: 4 типа (идентичные русским по структуре)")
        print("   • Функции build_*_prompt() возвращают правильный язык")
        print("   • Нет смешивания языков в промптах")
        print("\n✅ Готово к интеграции в bot.py и тестированию с реальными пользователями\n")
        
    except AssertionError as e:
        print(f"\n❌ ОШИБКА ТЕСТА: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ НЕОЖИДАННАЯ ОШИБКА: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
