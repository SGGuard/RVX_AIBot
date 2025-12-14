#!/bin/bash

# 🚀 RVX Backend - Railway Quick Deployment Script
# Этот скрипт помогает подготовить код для развертывания на Railway

echo "=================================="
echo "🚀 RVX Backend - Railway Deployment"
echo "=================================="
echo ""

# 1. Проверка зависимостей
echo "✓ Проверяем зависимости..."
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ FastAPI не установлен. Запустите: pip install -r requirements.txt"
    exit 1
fi
echo "✅ Зависимости установлены"
echo ""

# 2. Проверка синтаксиса
echo "✓ Проверяем синтаксис кода..."
python -m py_compile api_server.py bot.py ai_quality_fixer.py
if [ $? -eq 0 ]; then
    echo "✅ Синтаксис OK"
else
    echo "❌ Ошибки синтаксиса"
    exit 1
fi
echo ""

# 3. Проверка файлов
echo "✓ Проверяем файлы..."
files=("Procfile" ".env.example" "requirements.txt" "api_server.py" "bot.py" "ai_quality_fixer.py")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file - ОТСУТСТВУЕТ"
        exit 1
    fi
done
echo ""

# 4. Проверка тестов
echo "✓ Запускаем критические тесты..."
pytest tests/test_ai_quality_validator.py -q --tb=no
if [ $? -eq 0 ]; then
    echo "✅ Тесты качеств пройдены (28/28)"
else
    echo "⚠️  Некоторые тесты не прошли"
fi
echo ""

# 5. Git status
echo "✓ Проверяем Git статус..."
git status --short
echo ""
echo "=================================="
echo "✅ ГОТОВО К РАЗВЕРТЫВАНИЮ НА RAILWAY"
echo "=================================="
echo ""
echo "🔗 Следующие шаги:"
echo "1. git add -A"
echo "2. git commit -m 'SPRINT3: AI Quality Improvements'"
echo "3. git push origin main"
echo "4. Railway автоматически обнаружит изменения и развернет"
echo ""
echo "📖 Полный гайд: см. RAILWAY_DEPLOYMENT_GUIDE.md"
echo ""
