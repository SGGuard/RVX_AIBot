# 🤖 RVX AI Crypto News Bot

> **Telegram-бот для анализа криптоновостей и интерактивного обучения**  
> Версия: v0.18.0 | ИИ анализирует новости, преподает крипто, Web3, трейдинг, + закладки & рейтинги

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Telegram](https://img.shields.io/badge/Telegram--Bot-7.0+-blue.svg)](https://python-telegram-bot.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Описание

RVX Bot состоит из двух компонентов:

1. **Telegram Bot** (`bot.py`) — принимает новости от пользователей
2. **FastAPI Backend** (`api_server.py`) — анализирует текст через Gemini AI

### Основные возможности

- ✅ Анализ криптоновостей на понятном языке
- ✅ Оценка влияния на рынок (3-5 ключевых пунктов)
- ✅ Защита от prompt injection
- ✅ Автоматический retry при ошибках
- ✅ Кэширование ответов
- ✅ Fallback режим при недоступности AI

---

## 🚀 Быстрый старт

### 1. Требования

- Python 3.10 или выше
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))
- Google Gemini API Key

### 2. Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/rvx-bot.git
cd rvx-bot

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 3. Настройка

Создайте файл `.env` в корне проекта:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Gemini AI
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=models/gemini-2.5-flash
GEMINI_TEMPERATURE=0.3
GEMINI_MAX_TOKENS=1500
GEMINI_TIMEOUT=30

# API Server
PORT=8000
MAX_TEXT_LENGTH=4096
CACHE_ENABLED=true
ALLOWED_ORIGINS=*

# Rate Limiting (новое!)
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60
RATE_LIMIT_PER_IP=true

# Cache TTL (новое!)
CACHE_TTL_SECONDS=3600
CACHE_CLEANUP_INTERVAL=300

# Backend URL (для bot.py)
BACKEND_URL=http://localhost:8000
```

### 4. Запуск

**Вариант А: Запуск обоих компонентов вручную**

Терминал 1 (API Backend):
```bash
python api_server.py
```

Терминал 2 (Telegram Bot):
```bash
python bot.py
```

**Вариант Б: Использование главного скрипта**

```bash
python main.py
```

---

## 📁 Структура проекта

```
rvx-bot/
├── api_server.py       # FastAPI бэкенд с Gemini AI
├── bot.py              # Telegram bot логика
├── main.py             # Главный скрипт запуска
├── .env                # Конфигурация (не в Git!)
├── requirements.txt    # Python зависимости
├── README.md           # Документация
├── .gitignore          # Игнорируемые файлы
└── tests/              # Тесты (опционально)
    ├── test_api.py
    └── test_bot.py
```

---

## 🎮 Использование

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Пришлите криптоновость текстом
4. Получите анализ через 3-5 секунд

### Примеры команд

- `/start` — приветствие и инструкции
- `/help` — помощь по использованию
- `/stats` — статистика API (опционально)
- `/learn` — начать интерактивный курс
- `/teach <topic> [level]` — **НОВОЕ в v0.7.0** - интерактивный учитель по крипто, AI, Web3, трейдингу
  - Темы: `crypto_basics`, `trading`, `web3`, `ai`, `defi`, `nft`, `security`, `tokenomics`
  - Уровни: `beginner` 🌱, `intermediate` 📚, `advanced` 🚀, `expert` 💎
  - Примеры: `/teach crypto_basics`, `/teach trading intermediate`, `/teach defi advanced`

---

## ⚙️ Конфигурация

### Основные параметры

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `MAX_TEXT_LENGTH` | Максимальная длина новости | 4096 символов |
| `GEMINI_TEMPERATURE` | Креативность AI (0-1) | 0.3 |
| `GEMINI_TIMEOUT` | Таймаут запроса к AI | 30 секунд |
| `CACHE_ENABLED` | Включить кэширование | true |
| `CACHE_TTL_SECONDS` | Время жизни кэша | 3600 сек (1 час) |
| `RATE_LIMIT_ENABLED` | Включить rate limiting | true |
| `RATE_LIMIT_REQUESTS` | Запросов в окне | 10 |
| `RATE_LIMIT_WINDOW` | Окно в секундах | 60 |
| `RATE_LIMIT_PER_IP` | Ограничивать по IP | true |

### Продвинутые настройки

Для production окружения рекомендуется:

```env
# Logging
LOG_LEVEL=INFO

# Rate Limiting
MAX_REQUESTS_PER_MINUTE=30

# Cache
CACHE_MAX_SIZE=100
CACHE_TTL=3600
```

---

## 🛡️ Безопасность

- ✅ Все секретные ключи в `.env` (не коммитятся в Git)
- ✅ Защита от prompt injection
- ✅ Валидация всех входных данных
- ✅ Rate limiting (опционально)
- ✅ CORS настройка

**⚠️ Важно:** Никогда не коммитьте `.env` файл в репозиторий!

---

## 📊 Мониторинг

### Health Check

```bash
curl http://localhost:8000/health
```

Ответ:
```json
{
  "status": "healthy",
  "gemini_available": true,
  "requests_total": 142,
  "requests_success": 138,
  "requests_errors": 4,
  "requests_fallback": 2,
  "cache_size": 15,
  "uptime_seconds": 3672.45
}
```

### API Документация

После запуска API доступна по адресу:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 🐛 Troubleshooting

### Проблема: Bot не отвечает

**Решение:**
1. Проверьте, что API сервер запущен (`http://localhost:8000/health`)
2. Проверьте `TELEGRAM_BOT_TOKEN` в `.env`
3. Убедитесь, что бот не заблокирован в Telegram

### Проблема: Ошибка Gemini API

**Решение:**
1. Проверьте `GEMINI_API_KEY` в `.env`
2. Убедитесь, что у вас есть квота на API
3. Проверьте логи: `tail -f api_server.log`

### Проблема: Таймауты

**Решение:**
1. Увеличьте `GEMINI_TIMEOUT` в `.env`
2. Проверьте интернет соединение
3. Используйте более быструю модель (`gemini-2.0-flash-exp`)

---

## 🧪 Тестирование

```bash
# Установите dev зависимости
pip install pytest pytest-asyncio pytest-cov

# Запустите тесты
pytest tests/ -v

# С покрытием кода
pytest tests/ --cov=. --cov-report=html
```

---

## 📈 Roadmap

- [ ] Поддержка голосовых сообщений
- [ ] Анализ изображений графиков
- [ ] Интеграция с CoinGecko API
- [ ] Мультиязычность (EN, RU, UA)
- [ ] Веб-интерфейс для статистики
- [ ] Docker контейнеризация
- [ ] CI/CD pipeline

---

## 🤝 Contribution

Contributions are welcome! Пожалуйста:

1. Форкните репозиторий
2. Создайте ветку для фичи (`git checkout -b feature/amazing-feature`)
3. Закоммитьте изменения (`git commit -m 'Add amazing feature'`)
4. Запушьте в ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

---

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл [LICENSE](LICENSE) для деталей.

---

## 👨‍💻 Автор

Создано с ❤️ для крипто-комьюнити

<<<<<<< HEAD
- Telegram: [@RVX_AIBot](https://t.me/RVX_AIBot))
- GitHub: [@SGGuard](https://github.com/SGGuard))
=======
- Telegram: [@SV4096](https://t.me/SV4096)
>>>>>>> 0f7d810 (feat: Обновление API до v0.5.0, добавление тестов и кэширования)

---

## 🙏 Благодарности

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Google Gemini](https://ai.google.dev/)

---

<<<<<<< HEAD
**⭐ Если проект полезен — поставьте звезду на GitHub!**
=======
**⭐ Если проект полезен — поставьте звезду на GitHub!**
>>>>>>> 0f7d810 (feat: Обновление API до v0.5.0, добавление тестов и кэширования)
