#!/usr/bin/env python3
"""
Демонстрация работы системы обнаружения скамов и красных флагов.
"""

from ai_dialogue import detect_scam_red_flags, add_scam_warning_if_needed


def demo_scam_detection():
    """Демонстрирует работу обнаружения скамов"""
    
    test_cases = [
        {
            "name": "Критический скам (OneCoin паттерн)",
            "message": "OneCoin даст 1000x потенциал! Гарантированный листинг на Binance. Успей, пока не поздно!",
        },
        {
            "name": "Высокий риск (BitConnect)",
            "message": "Получай 40% в месяц, это гарантировано! Партнер Amazon одобрил проект!",
        },
        {
            "name": "FOMO давление (типичный pump-and-dump)",
            "message": "Все уже знают про этот токен! Успей до роста цены!",
        },
        {
            "name": "Низкий риск (нормальный вопрос)",
            "message": "Расскажи про Bitcoin и как он работает",
        },
        {
            "name": "Инсайды и приватные чаты",
            "message": "Получи приватную информацию в нашем закрытом чате",
        },
    ]
    
    print("=" * 80)
    print("🚨 ДЕМОНСТРАЦИЯ СИСТЕМЫ ОБНАРУЖЕНИЯ СКАМОВ И КРАСНЫХ ФЛАГОВ")
    print("=" * 80)
    print()
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'─' * 80}")
        print(f"Тест #{i}: {test['name']}")
        print(f"{'─' * 80}")
        print(f"📝 Сообщение: {test['message']}")
        print()
        
        risks = detect_scam_red_flags(test['message'])
        
        print(f"🔍 Обнаруженные риски:")
        print(f"   Уровень риска: {risks['risk_level'].upper()}")
        print(f"   Рекомендация: {risks['recommendation']}")
        
        if risks['scam_indicators']:
            print(f"   🚩 Обнаруженные признаки скама:")
            for indicator in risks['scam_indicators']:
                print(f"      - {indicator}")
        
        if risks['urgency_phrases']:
            print(f"   ⏰ Фразы создающие срочность:")
            for phrase in risks['urgency_phrases']:
                print(f"      - {phrase}")
        
        # Демонстрируем как выглядит предупреждение в боте
        dummy_response = "Это интересный проект с хорошим потенциалом роста"
        warning_response = add_scam_warning_if_needed(test['message'], dummy_response)
        
        if warning_response != dummy_response:
            print(f"\n   💬 Ответ бота с предупреждением:")
            print(f"   {warning_response[:200]}...")
        else:
            print(f"\n   💬 Ответ бота (без предупреждения):")
            print(f"   {warning_response}")


def demo_real_world_examples():
    """Демонстрирует реальные примеры"""
    print("\n" + "=" * 80)
    print("📊 РЕАЛЬНЫЕ ПРИМЕРЫ ИЗВЕСТНЫХ СКАМОВ")
    print("=" * 80)
    
    real_examples = [
        {
            "name": "OneCoin (2016-2019) - $4B потеряно",
            "text": "Революционная крипто-валюта OneCoin с гарантированным ростом! 100x потенциал в год! Инсайды о листинге на Binance в приватном чате!",
        },
        {
            "name": "BitConnect (2016-2018) - $2B потеряно",
            "text": "Получай 40% в месяц (480% в год), это гарантировано! Успей, пока не поздно! Партнер Amazon одобрил!",
        },
        {
            "name": "Luna (2021-2022) - $40B потеряно",
            "text": "Luna даст 20% в месяц на стейк! Гарантированный рост! Инсайдеры уже знают о скором листинге!",
        },
    ]
    
    for example in real_examples:
        print(f"\n{example['name']}")
        print(f"─" * 60)
        risks = detect_scam_red_flags(example['text'])
        print(f"Уровень риска: {risks['risk_level'].upper()}")
        print(f"Признаки: {', '.join(risks['scam_indicators'])}")


if __name__ == "__main__":
    demo_scam_detection()
    demo_real_world_examples()
    
    print("\n" + "=" * 80)
    print("✅ Демонстрация завершена!")
    print("=" * 80)
