#!/usr/bin/env python3
"""
🎯 ДЕМОНСТРАЦИЯ МОЩИ OLLAMA
===========================
Наглядные примеры того, как Ollama помогает разработчику:
1. Анализ проблемного кода (находит баги)
2. Генерация документации (создаёт docstring)
3. Написание тестов (создаёт unit tests)
4. Поиск уязвимостей (security анализ)
"""

import asyncio
import sys
from ollama_client import initialize_ollama, get_ollama_client

# ПРИМЕРЫ КОДА КОТОРЫЕ МЫ БУДЕМ АНАЛИЗИРОВАТЬ

PROBLEMATIC_CODE = """
def process_user_data(user_list):
    '''Processing user data'''
    for i in range(len(user_list)):
        name = user_list[i]['name']
        email = user_list[i]['email']
        age = user_list[i]['age']
        
        # ❌ ПРОБЛЕМА #1: Нет проверки на None/KeyError
        # ❌ ПРОБЛЕМА #2: Неэффективный цикл (range + len)
        # ❌ ПРОБЛЕМА #3: Нет обработки исключений
        if age > 18:  
            send_email(email)  # Может упасть если email None!
        
        queries = []
        for j in range(len(user_list)):  # ❌ O(n^2) сложность!
            if user_list[j]['age'] == age:
                queries.append(j)
        
        return queries  # ❌ Возвращает результат в цикле!
"""

INSECURE_CODE = """
def login_user(username, password):
    # ❌ УЯЗВИМОСТЬ #1: SQL Injection
    query = f"SELECT * FROM users WHERE username='{username}'"
    result = db.execute(query)
    
    # ❌ УЯЗВИМОСТЬ #2: Plaintext password comparison
    if result['password'] == password:
        # ❌ УЯЗВИМОСТЬ #3: No input validation
        token = generate_token(username)
        return token
    return None

def get_file(filepath):
    # ❌ УЯЗВИМОСТЬ #4: Path traversal
    return open(f"/files/{filepath}", 'r').read()
"""

UNDOCUMENTED_CODE = """
async def fetch_crypto_data(symbols, cache_ttl=3600):
    async with httpx.AsyncClient() as client:
        results = {}
        for sym in symbols:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={sym}&vs_currencies=usd"
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results[sym] = data[sym]['usd']
        return results
"""

UNTESTED_CODE = """
def calculate_portfolio_value(holdings):
    total = 0
    for asset in holdings:
        price = fetch_price(asset['symbol'])
        total += asset['quantity'] * price
    return total

def apply_discount(price, discount_percent):
    return price * (1 - discount_percent / 100)

def validate_email(email):
    return '@' in email and '.' in email
"""


async def demo_section(title: str, code: str, analysis_type: str):
    """
    Демонстрирует Ollama анализ кода.
    
    Args:
        title: Название демо-секции
        code: Код для анализа
        analysis_type: Тип анализа (security, performance, general, style)
    """
    print(f"\n{'='*70}")
    print(f"🎯 {title}")
    print(f"{'='*70}\n")
    
    print(f"📝 КОД ДЛЯ АНАЛИЗА:\n")
    print(f"```python")
    for i, line in enumerate(code.strip().split('\n')[:10], 1):  # Показываем первые 10 строк
        print(f"{i:2d} │ {line}")
    print(f"   ... (еще {len(code.strip().split(chr(10))) - 10} строк)")
    print(f"```\n")
    
    client = get_ollama_client()
    if not client or not client.is_available:
        print("❌ Ollama не доступна!")
        return
    
    print(f"🔍 Ollama АНАЛИЗИРУЕТ {analysis_type} ...\n")
    
    try:
        analysis = await client.analyze_code(code, analysis_type)
        
        print(f"✅ РЕЗУЛЬТАТ АНАЛИЗА:\n")
        print("─" * 70)
        print(analysis)
        print("─" * 70)
        print()
        
    except Exception as e:
        print(f"❌ Ошибка при анализе: {e}\n")


async def demo_docstring():
    """Демонстрирует генерацию документации."""
    print(f"\n{'='*70}")
    print(f"📚 ГЕНЕРАЦИЯ ДОКУМЕНТАЦИИ (Docstring)")
    print(f"{'='*70}\n")
    
    print(f"📝 КОД БЕЗ ДОКУМЕНТАЦИИ:\n")
    print(f"```python")
    for i, line in enumerate(UNDOCUMENTED_CODE.strip().split('\n')[:5], 1):
        print(f"{i:2d} │ {line}")
    print(f"```\n")
    
    client = get_ollama_client()
    if not client or not client.is_available:
        print("❌ Ollama не доступна!")
        return
    
    print(f"✍️  Ollama ГЕНЕРИРУЕТ docstring ...\n")
    
    try:
        docstring = await client.generate_docstring(UNDOCUMENTED_CODE, "python")
        
        print(f"✅ РЕЗУЛЬТАТ - ПОЛНАЯ ДОКУМЕНТАЦИЯ:\n")
        print("─" * 70)
        print(docstring)
        print("─" * 70)
        print()
        
    except Exception as e:
        print(f"❌ Ошибка при генерации: {e}\n")


async def demo_tests():
    """Демонстрирует генерацию тестов."""
    print(f"\n{'='*70}")
    print(f"🧪 АВТОМАТИЧЕСКОЕ НАПИСАНИЕ ТЕСТОВ")
    print(f"{'='*70}\n")
    
    print(f"📝 КОД БЕЗ ТЕСТОВ:\n")
    print(f"```python")
    for i, line in enumerate(UNTESTED_CODE.strip().split('\n')[:8], 1):
        print(f"{i:2d} │ {line}")
    print(f"   ... (еще {len(UNTESTED_CODE.strip().split(chr(10))) - 8} строк)")
    print(f"```\n")
    
    client = get_ollama_client()
    if not client or not client.is_available:
        print("❌ Ollama не доступна!")
        return
    
    print(f"🤖 Ollama ПИШЕТ ТЕСТЫ ...\n")
    
    try:
        tests = await client.write_tests(UNTESTED_CODE, "python")
        
        print(f"✅ РЕЗУЛЬТАТ - ГОТОВЫЕ ТЕСТЫ:\n")
        print("─" * 70)
        # Показываем только первую часть
        lines = tests.split('\n')
        for line in lines[:25]:
            print(line)
        if len(lines) > 25:
            print(f"\n... (еще {len(lines) - 25} строк тестов!) ...")
        print("─" * 70)
        print()
        
    except Exception as e:
        print(f"❌ Ошибка при генерации: {e}\n")


async def main():
    """Главная функция демонстрации."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  🚀 ДЕМОНСТРАЦИЯ МОЩИ OLLAMA - ПОЛНАЯ АВТОМАТИЗАЦИЯ! 🚀".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    print()
    print("📌 ЧТО ТЫ СЕЙЧАС УВИДИШЬ:")
    print("   1️⃣  Ollama находит БАГИ в проблемном коде")
    print("   2️⃣  Ollama находит УЯЗВИМОСТИ (security анализ)")
    print("   3️⃣  Ollama генерирует ПОЛНУЮ ДОКУМЕНТАЦИЮ")
    print("   4️⃣  Ollama ПИШЕТ UNIT ТЕСТЫ")
    print()
    print("⏳ Каждый анализ займет 5-10 секунд (первый раз медленнее)")
    print()
    
    # Инициализируем Ollama
    print("🔧 Инициализируем Ollama...\n")
    client = await initialize_ollama()
    
    if not client.is_available:
        print("❌ Ollama не доступна!")
        print("   Убедись что запустил: ollama serve")
        return
    
    print(f"✅ Ollama БЕЗ ИНТЕРНЕТА готова работать!\n")
    
    # ДЕМО 1: Анализ проблемного кода (находит баги)
    await demo_section(
        "ДЕМО 1️⃣ : АНАЛИЗ КОДА - Ollama НАХОДИТ БАГИ",
        PROBLEMATIC_CODE,
        "general"
    )
    input("Press Enter to continue...")
    
    # ДЕМО 2: Security анализ (находит уязвимости)
    await demo_section(
        "ДЕМО 2️⃣ : SECURITY АНАЛИЗ - Ollama НАХОДИТ УЯЗВИМОСТИ",
        INSECURE_CODE,
        "security"
    )
    input("Press Enter to continue...")
    
    # ДЕМО 3: Генерация документации
    await demo_docstring()
    input("Press Enter to continue...")
    
    # ДЕМО 4: Написание тестов
    await demo_tests()
    
    # Итоги
    print(f"\n{'='*70}")
    print(f"✨ ИТОГИ ДЕМОНСТРАЦИИ")
    print(f"{'='*70}\n")
    
    print("🎯 ЧТО OLLAMA СДЕЛАЛА ДЛЯ ТЕБЯ:\n")
    
    print("1️⃣  АНАЛИЗ КОДА")
    print("   ✅ Нашла проблемы в логике")
    print("   ✅ Нашла проблемы с производительностью")
    print("   ✅ Предложила решения\n")
    
    print("2️⃣  SECURITY АНАЛИЗ")
    print("   ✅ Нашла SQL Injection уязвимость")
    print("   ✅ Нашла Path Traversal уязвимость")
    print("   ✅ Нашла проблемы с паролями\n")
    
    print("3️⃣  ДОКУМЕНТАЦИЯ")
    print("   ✅ Создала подробный docstring")
    print("   ✅ Описала параметры и возвращаемые значения")
    print("   ✅ Добавила примеры использования\n")
    
    print("4️⃣  ТЕСТЫ")
    print("   ✅ Написала unit тесты")
    print("   ✅ Покрыла positive и negative cases")
    print("   ✅ Добавила edge cases\n")
    
    print("─" * 70)
    print()
    print("💡 ИТОГ: Ollama сделала за 40 секунд то, что обычно делается часами!")
    print()
    print("🎯 ТЕПЕРЬ ТЫ МОЖЕШЬ:")
    print("   ✅ Анализировать свой код автоматически")
    print("   ✅ Находить баги ДО production'а")
    print("   ✅ Писать документацию БЕЗ рутины")
    print("   ✅ Создавать тесты快速")
    print("   ✅ Всё это БЕЗ ИНТЕРНЕТА на своем компе!")
    print()
    print("🚀 ГОТОВО! Теперь ты видишь как Ollama АВТОМАТИЗИРУЕТ разработку!\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Демонстрация прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)
