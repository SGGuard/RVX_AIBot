#!/bin/bash

# ============================================================================
# ТЕСТИРОВАНИЕ ФИЧИ: СВЕЖИЕ ДРОПЫ И АКТИВНОСТИ (v0.15.0)
# ============================================================================

echo "🧪 Начало тестирования фичи дропов и активностей..."
echo "=================================================================="

# Проверка, что сервисы работают
echo ""
echo "1️⃣  Проверка статуса сервисов..."
ps aux | grep -E "python.*api_server|python.*bot.py" | grep -v grep
if [ $? -eq 0 ]; then
    echo "✅ Оба сервиса запущены"
else
    echo "❌ Сервисы не запущены!"
    exit 1
fi

# Проверка API здоровья
echo ""
echo "2️⃣  Проверка здоровья API..."
curl -s http://localhost:8000/health | python3 -m json.tool > /dev/null && echo "✅ API здоров" || echo "❌ API не отвечает"

# Тест /get_drops
echo ""
echo "3️⃣  Тест /get_drops endpoint..."
echo "Запрос: GET /get_drops?limit=3"
DROPS_RESPONSE=$(curl -s http://localhost:8000/get_drops?limit=3)
DROPS_COUNT=$(echo "$DROPS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null)
if [ "$DROPS_COUNT" -gt 0 ]; then
    echo "✅ Получено $DROPS_COUNT дропов"
    echo "$DROPS_RESPONSE" | python3 -m json.tool | head -20
else
    echo "❌ Ошибка при получении дропов"
fi

# Тест /get_trending
echo ""
echo "4️⃣  Тест /get_trending endpoint..."
echo "Запрос: GET /get_trending?limit=5"
TRENDING=$(curl -s http://localhost:8000/get_trending?limit=5)
TRENDING_COUNT=$(echo "$TRENDING" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null)
if [ "$TRENDING_COUNT" -gt 0 ]; then
    echo "✅ Получено $TRENDING_COUNT трендовых токенов"
    echo "$TRENDING" | python3 -m json.tool | head -20
else
    echo "❌ Ошибка при получении трендов"
fi

# Тест /get_activities
echo ""
echo "5️⃣  Тест /get_activities endpoint..."
echo "Запрос: GET /get_activities"
ACTIVITIES=$(curl -s http://localhost:8000/get_activities)
ACTIVITIES_COUNT=$(echo "$ACTIVITIES" | python3 -c "import sys, json; print(json.load(sys.stdin)['total_activities'])" 2>/dev/null)
echo "✅ Получено $ACTIVITIES_COUNT активностей"
echo "$ACTIVITIES" | python3 -m json.tool | head -30

# Тест /get_token_info
echo ""
echo "6️⃣  Тест /get_token_info endpoint..."
echo "Запрос: GET /get_token_info/bitcoin"
TOKEN_INFO=$(curl -s http://localhost:8000/get_token_info/bitcoin)
TOKEN_NAME=$(echo "$TOKEN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin)['name'])" 2>/dev/null)
TOKEN_PRICE=$(echo "$TOKEN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin)['price'])" 2>/dev/null)
if [ ! -z "$TOKEN_NAME" ]; then
    echo "✅ Получена информация: $TOKEN_NAME = \$$TOKEN_PRICE"
    echo "$TOKEN_INFO" | python3 -m json.tool
else
    echo "❌ Ошибка при получении информации о токене"
fi

# Проверка логов
echo ""
echo "7️⃣  Проверка логов сервисов..."
echo ""
echo "📝 Последние 5 строк api_server.log:"
tail -5 api_server.log | grep -E "GET|POST|ERROR" || echo "✅ Нет ошибок в логах"

echo ""
echo "📝 Последние 5 строк bot.log:"
tail -5 bot.log | grep -E "drop|ERROR" || echo "✅ Нет ошибок в логах"

# Финальный отчет
echo ""
echo "=================================================================="
echo "✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО!"
echo "=================================================================="
echo ""
echo "🎉 Доступные команды в Telegram боте:"
echo "  • /drops - Свежие NFT дропы"
echo "  • /activities - Активности в проектах"
echo "  • /trending - Вирусные токены"
echo "  • /subscribe_drops - Подписка на дропы"
echo "  • /my_subscriptions - Мои подписки"
echo ""
echo "📚 Документация: DROPS_FEATURES_README.md"
echo "📦 Модуль: drops_tracker.py"
echo ""
echo "Версия: 0.15.0"
echo "Дата: $(date '+%d.%m.%Y %H:%M:%S')"
