# 🚀 Развёртывание RVX Bot v0.6.0

> **Стратегия**: Локальное развёртывание с возможностью масштабирования

## 📊 Архитектура

```
┌─────────────────────────────────────────────────────┐
│           Telegram User Interface                    │
└──────────────┬──────────────────────────────────────┘
               │ /explain_news command
               ▼
┌──────────────────────────────────────────────────────┐
│  Bot (bot.py)                    ⏱️ 2.8 MB           │
│  ├─ Command handlers             │ 2822 lines        │
│  ├─ Callback routing             │ Python 3.12       │
│  ├─ Database persistence         │                   │
│  └─ Telegram API client          │                   │
└──────────────┬───────────────────────────────────────┘
               │ HTTP POST /explain_news
               ▼
┌──────────────────────────────────────────────────────┐
│  API Server (api_server.py)      ⏱️ 1.2 MB           │
│  ├─ FastAPI framework            │ 815 lines         │
│  ├─ Gemini AI integration        │ Python 3.12       │
│  ├─ Response caching             │                   │
│  └─ Error handling & retry       │                   │
└──────────────┬───────────────────────────────────────┘
               │ generate_content()
               ▼
┌──────────────────────────────────────────────────────┐
│  Google Gemini API (Cloud)       🔑 API Key Required │
│  ├─ gemini-2.5-flash model       │ Rate limited      │
│  ├─ Streaming analysis           │ Production-ready  │
│  └─ JSON output format           │                   │
└──────────────────────────────────────────────────────┘
               
┌──────────────────────────────────────────────────────┐
│  SQLite Database (rvx_bot.db)                        │
│  ├─ users, requests, feedback                        │
│  ├─ courses, lessons, user_progress                  │
│  ├─ tools, faq, bookmarks                            │
│  └─ 13 таблиц, 100+ запросов/день                    │
└──────────────────────────────────────────────────────┘
```

---

## 🏠 Локальное развёртывание (рекомендуется)

### Вариант 1️⃣: Ручной запуск (для разработки)

**Требования:**
- Python 3.10+
- Git
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Google Gemini API Key (https://ai.google.dev)

**Шаги:**

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/SGGuard/RVX_AIBot.git
cd RVX_AIBot

# 2. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Создайте .env файл
cat > .env << 'EOF'
# Telegram
TELEGRAM_BOT_TOKEN=your_token_here

# Gemini AI
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=models/gemini-2.5-flash
GEMINI_TEMPERATURE=0.3
GEMINI_MAX_TOKENS=1500
GEMINI_TIMEOUT=30

# API Server
PORT=8000
API_URL_NEWS=http://localhost:8000/explain_news

# Database
DB_PATH=rvx_bot.db

# Features
RATE_LIMIT_ENABLED=true
ENABLE_ANALYTICS=true
ENABLE_AUTO_CACHE_CLEANUP=true
EOF

# 5. Запустите оба компонента (в разных терминалах)

# Терминал 1 - API Server
python api_server.py

# Терминал 2 - Bot
python bot.py

# ✅ Bot готов! Отправляйте боту сообщения в Telegram
```

**Проверка здоровья:**
```bash
curl http://localhost:8000/health
# Ожидается: {"status":"healthy","gemini_available":true}
```

---

### Вариант 2️⃣: Docker Compose (рекомендуется для production)

**Требования:**
- Docker Desktop (https://www.docker.com/products/docker-desktop)

**Шаги:**

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/SGGuard/RVX_AIBot.git
cd RVX_AIBot

# 2. Создайте .env файл
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_api_key_here
EOF

# 3. Запустите docker-compose
docker-compose up -d

# 4. Проверьте логи
docker-compose logs -f api
docker-compose logs -f bot

# 5. Остановка
docker-compose down
```

**Преимущества Docker:**
- ✅ Изолированная окружение
- ✅ Легко масштабировать
- ✅ Простой деплой на серверы
- ✅ Совместимость между системами

---

### Вариант 3️⃣: Systemd Service (Linux Production)

Создайте `/etc/systemd/system/rvx-bot.service`:

```ini
[Unit]
Description=RVX AI Crypto Bot
After=network.target

[Service]
Type=simple
User=rvx-bot
WorkingDirectory=/home/rvx-bot/RVX_AIBot
Environment="PATH=/home/rvx-bot/RVX_AIBot/venv/bin"
ExecStart=/home/rvx-bot/RVX_AIBot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Активируйте сервис
sudo systemctl enable rvx-bot
sudo systemctl start rvx-bot

# Проверьте статус
sudo systemctl status rvx-bot

# Логи
sudo journalctl -u rvx-bot -f
```

---

## 📈 Мониторинг

### Health Check Endpoint

```bash
# API здоров?
curl http://localhost:8000/health

# Ответ:
{
  "status": "healthy",
  "gemini_available": true,
  "requests_total": 42,
  "requests_success": 40,
  "requests_errors": 2,
  "requests_fallback": 0,
  "cache_size": 15,
  "cache_hits": 8
}
```

### Логи

```bash
# API логи
tail -f api_server.log

# Bot логи
tail -f bot.log

# Комбинированные логи
tail -f *.log | grep "ERROR\|❌\|⚠️"
```

---

## 🔐 Безопасность

### Environment Variables Checklist

- [ ] `TELEGRAM_BOT_TOKEN` - никогда не коммитить в Git
- [ ] `GEMINI_API_KEY` - хранить в `.env`
- [ ] `.env` добавлен в `.gitignore`
- [ ] Используется HTTPS для всех API запросов
- [ ] Rate limiting включен (`RATE_LIMIT_ENABLED=true`)

### Защита от атак

```python
# Automatически применяется:
✅ SQL Injection Protection (parameterized queries)
✅ Prompt Injection Defense (input sanitization)
✅ Rate Limiting (10 запросов/60с per IP)
✅ Flood Control (3 сек между запросами)
✅ Input Validation (max 4096 chars)
✅ Output Escaping (HTML entities in responses)
```

---

## 🚨 Troubleshooting

### Проблема: "API недоступен"

```bash
# Проверьте запуск API
curl http://localhost:8000/health

# Если не работает, проверьте логи
tail -20 api_server.log

# Проверьте порт 8000
netstat -tuln | grep 8000
# или
lsof -i :8000
```

### Проблема: "Бот не отвечает"

```bash
# Проверьте токен
grep TELEGRAM_BOT_TOKEN .env

# Проверьте подключение к API
curl -X POST http://localhost:8000/explain_news \
  -H 'Content-Type: application/json' \
  -d '{"text_content":"test"}'

# Проверьте логи бота
tail -50 bot.log | grep ERROR
```

### Проблема: "Gemini API Key invalid"

```bash
# Получите новый ключ: https://ai.google.dev/
# Обновите .env
GEMINI_API_KEY=your_new_key_here

# Перезагрузите услуги
docker-compose restart
# или
pkill -f "python api_server|python bot"
sleep 2
python api_server.py &
python bot.py &
```

---

## 📊 Производительность

### Benchmarks (локально)

```
API Response Time:
  ├─ Cache hit:       50-100ms ⚡
  ├─ First request:   4-6 sec (Gemini call)
  └─ Timeout:         30 sec

Bot Response Time:
  ├─ Message received: instant
  ├─ API call:        5-7 sec
  └─ Total:           5-8 sec per message

Database:
  ├─ Queries/day:     100-200
  ├─ Size:            2-5 MB
  └─ Performance:     <10ms per query
```

### Resource Usage

```
Memory:
  ├─ API:  ~80-120 MB
  ├─ Bot:  ~60-100 MB
  └─ Total: ~150-200 MB

CPU:
  ├─ Idle:    <1%
  ├─ Active:  5-15%
  └─ Peak:    20-30% during analysis

Disk:
  ├─ Code:    ~20 MB
  ├─ Venv:    ~500 MB
  ├─ DB:      ~5 MB
  └─ Logs:    ~1 MB/day
```

---

## 🔄 Обновления

### Обновление версии

```bash
# 1. Закройте текущий процесс
docker-compose down
# или
pkill -f "python bot|api_server"

# 2. Получите обновления
git pull origin main

# 3. Переустановите зависимости (если необходимо)
pip install -r requirements.txt --upgrade

# 4. Запустите снова
docker-compose up -d
# или
python api_server.py &
python bot.py &
```

### Миграции БД

```bash
# Миграции применяются автоматически при запуске bot.py
# Проверьте логи для подтверждения:
grep "Миграция\|migration" bot.log
```

---

## 📞 Поддержка

- **Issues**: https://github.com/SGGuard/RVX_AIBot/issues
- **Discussions**: https://github.com/SGGuard/RVX_AIBot/discussions
- **Email**: support@example.com (при наличии)

---

## 📝 Лицензия

MIT License - см. LICENSE файл

---

**Последнее обновление:** 30 ноября 2025 г.  
**Версия:** v0.6.0  
**Статус:** ✅ Production Ready
