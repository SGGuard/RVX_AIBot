#!/bin/bash
# 🚀 RVX Bot v0.7.0 - Скрипт запуска

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              RVX Crypto AI Bot v0.7.0                        ║"
echo "║          Запуск сервисов...                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# Проверяем Python
echo "🔍 Проверяем Python..."
python3 --version
echo

# Проверяем зависимости
echo "📦 Проверяем зависимости..."
python3 -m pip list | grep -E "fastapi|telegram|httpx|google-generativeai" | head -5
echo

# Создаем .env если не существует
if [ ! -f .env ]; then
    echo "⚠️  Файл .env не найден!"
    echo "📝 Пожалуйста, создайте .env с следующими переменными:"
    echo
    echo "TELEGRAM_BOT_TOKEN=your_token_here"
    echo "GEMINI_API_KEY=your_key_here"
    echo "GEMINI_MODEL=models/gemini-2.5-flash"
    echo "PORT=8000"
    echo
    exit 1
fi

# Проверяем синтаксис
echo "✓ Проверяем синтаксис Python файлов..."
python3 -m py_compile bot.py api_server.py teacher.py education.py
if [ $? -eq 0 ]; then
    echo "✅ Все файлы синтаксически верны!"
else
    echo "❌ Ошибка синтаксиса! Исправьте файлы."
    exit 1
fi
echo

# Убиваем старые процессы если есть
echo "🧹 Очищаем старые процессы..."
pkill -f "python.*api_server" 2>/dev/null || true
pkill -f "python.*bot.py" 2>/dev/null || true
sleep 1
echo

# Запускаем API Server
echo "🚀 Запускаем API Server на порту 8000..."
nohup python3 api_server.py > /tmp/rvx_api.log 2>&1 &
API_PID=$!
echo "   PID: $API_PID"
sleep 3

# Проверяем API
echo "🔍 Проверяем API..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ API здоров!"
else
    echo "❌ API не ответил на health check"
    echo "   Логи: tail -20 /tmp/rvx_api.log"
    exit 1
fi
echo

# Запускаем Telegram Bot
echo "🚀 Запускаем Telegram Bot..."
nohup python3 bot.py > /tmp/rvx_bot.log 2>&1 &
BOT_PID=$!
echo "   PID: $BOT_PID"
sleep 2
echo

# Финальный статус
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    СТАТУС СИСТЕМЫ                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo "🟢 API Server (PID $API_PID)"
echo "   http://localhost:8000/health"
echo "   http://localhost:8000/docs"
echo
echo "🟢 Telegram Bot (PID $BOT_PID)"  
echo "   Бот готов принимать команды"
echo
echo "📊 Логи:"
echo "   API:  tail -f /tmp/rvx_api.log"
echo "   Bot:  tail -f /tmp/rvx_bot.log"
echo
echo "🎓 Новая команда:"
echo "   /teach crypto_basics       - Основы крипто"
echo "   /teach trading beginner    - Трейдинг для новичков"
echo "   /teach web3 advanced       - Web3 продвинутый"
echo "   /teach defi expert         - DeFi для экспертов"
echo
echo "📚 Документация:"
echo "   README.md - Главная документация"
echo "   TEACHING_GUIDE.md - Гайд по /teach"
echo "   CHANGELOG.md - История версий"
echo
echo "════════════════════════════════════════════════════════════════"
echo "✨ RVX Bot v0.7.0 ЗАПУЩЕН И ГОТОВ К РАБОТЕ! ✨"
echo "════════════════════════════════════════════════════════════════"
echo
echo "Для остановки используйте:"
echo "  kill $API_PID  # Остановить API"
echo "  kill $BOT_PID  # Остановить Bot"
echo
