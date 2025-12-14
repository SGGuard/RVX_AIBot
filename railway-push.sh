#!/bin/bash

# 🚀 RVX Backend - Railway Push Script
# Этот скрипт автоматически загружает код на Railway

set -e  # Выход при первой ошибке

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  🚀 RVX Backend - Railway Deploy v0.4.0   ║"
echo "║  SPRINT 3: AI Quality Improvements        ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# 1. Проверка git
echo "📦 Проверка Git репозитория..."
if ! git status > /dev/null 2>&1; then
    echo "❌ Это не Git репозиторий"
    exit 1
fi
echo "✅ Git репозиторий найден"
echo ""

# 2. Проверка ветки
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "⚠️  Вы находитесь на ветке '$CURRENT_BRANCH', а не 'main'"
    read -p "Продолжить? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo "✅ Ветка: $CURRENT_BRANCH"
echo ""

# 3. Проверка изменений
echo "📋 Проверка изменений..."
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Есть несохраненные изменения"
    read -p "Хотите их добавить? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add -A
        echo "✅ Изменения добавлены"
    fi
fi
echo ""

# 4. Проверка commit message
echo "💬 Введите сообщение commit:"
read -p "> " COMMIT_MSG
if [ -z "$COMMIT_MSG" ]; then
    COMMIT_MSG="SPRINT3: AI Quality Improvements and Railway deployment"
fi
echo ""

# 5. Commit и push
echo "🔄 Загружаем на GitHub..."
git commit -m "$COMMIT_MSG" --allow-empty
git push origin $CURRENT_BRANCH

echo ""
echo "✅ Код загружен на GitHub!"
echo ""
echo "🚀 Railway автоматически обнаружит изменения и начнет deploy"
echo ""
echo "📊 Для мониторинга процесса:"
echo "   1. Откройте https://railway.app"
echo "   2. Перейдите в проект RVX_AIBot"
echo "   3. Смотрите вкладку 'Deployments'"
echo ""
echo "⏱️  Примерное время деплоя: 3-5 минут"
echo ""
echo "✅ После завершения деплоя:"
echo "   - API будет доступен по HTTPS"
echo "   - Bot будет отвечать в Telegram"
echo "   - Качество анализа улучшено на SPRINT3"
echo ""
echo "📞 Проверьте статус командой:"
echo "   curl https://<ваш-проект>.railway.app/health"
echo ""
