# 📊 Daily Digest Scheduler v0.28.0

## Описание

Ежедневный крипто-дайджест отправляется в Telegram канал в определенное время (по умолчанию 9:00 UTC).

**Что включает дайджест:**
- 🔗 **Обзор рынка** - BTC, ETH, топ-25 крипто по маркетку
- 😱 **Fear & Greed Index** - текущее настроение рынка
- 📈 **Gainers & Losers** - топ растущие и падающие монеты за 24ч
- 📰 **Последние новости** - из RSS лент Cointelegraph и других источников
- ⏰ **Календарь событий** - ключевые события на день (FOMC, ECB, макро данные)

## Конфигурация

### Переменные окружения (.env)

```env
# ===== DAILY DIGEST SCHEDULER =====
DIGEST_ENABLED=true                    # Включить/отключить дайджест
DIGEST_CHANNEL_ID=@RVX_AI             # Telegram канал (@username или ID)
DIGEST_HOUR=9                          # Час отправки (0-23, UTC)
DIGEST_MINUTE=0                        # Минута отправки (0-59)
DIGEST_TIMEZONE=UTC                    # Часовой пояс
```

### Примеры конфигурации

**9:00 UTC каждый день (дефолт):**
```env
DIGEST_HOUR=9
DIGEST_MINUTE=0
DIGEST_TIMEZONE=UTC
```

**14:00 Москва (UTC+3):**
```env
DIGEST_HOUR=11
DIGEST_MINUTE=0
DIGEST_TIMEZONE=Europe/Moscow
```

**7:00 Нью-Йорк (UTC-5):**
```env
DIGEST_HOUR=12
DIGEST_MINUTE=0
DIGEST_TIMEZONE=America/New_York
```

## Использование

### Запуск бота с дайджестом

```bash
python bot.py
```

При запуске вы увидите:
```
🚀 Initializing daily digest scheduler...
✅ Daily digest scheduler started
```

### Тестирование дайджеста

**Собрать и показать данные:**
```bash
python test_daily_digest.py
```

**Показать формат отправляемого сообщения:**
```bash
python test_daily_digest.py send
```

### Прямое использование в коде

```python
from daily_digest_scheduler import initialize_digest_scheduler, get_digest_scheduler

# Инициализировать
scheduler = await initialize_digest_scheduler()

# Отправить сразу (не ждать расписания)
await scheduler.send_daily_digest()

# Остановить
await stop_digest_scheduler()
```

## Интеграция с CoinGecko API

Дайджест автоматически использует **Pro API** если задан `COINGECKO_API_KEY`:

```env
COINGECKO_API_KEY=your_coingecko_pro_api_key_here
```

**Преимущества Pro API:**
- 🚀 Higher rate limits (50 req/min vs 10-15 free)
- 😱 Fear & Greed Index (требует Pro key)
- ⚡ Более стабильный API

## Дебаг и мониторинг

### Логирование

Дайджест логирует все действия:
```
✅ Daily digest scheduled for 09:00 UTC
📢 Channel: @RVX_AI
🔄 Starting daily digest collection at 2024-12-17T09:00:01
📊 Message sent to @RVX_AI (part 1/1)
✅ Daily digest sent successfully
```

### Проблемы и решения

**Проблема:** Дайджест не отправляется
- ✅ Проверить `DIGEST_ENABLED=true`
- ✅ Проверить `DIGEST_CHANNEL_ID` (боту нужны права на отправку)
- ✅ Проверить наличие апи ключей (COINGECKO_API_KEY, TELEGRAM_BOT_TOKEN)

**Проблема:** Неправильное время отправки
- ✅ Проверить `DIGEST_HOUR` и `DIGEST_MINUTE`
- ✅ Проверить `DIGEST_TIMEZONE` (используется pytz)

**Проблема:** Ошибки при отправке
- ✅ Проверить права доступа бота к каналу
- ✅ Проверить лимиты API (Rate limit)
- ✅ Проверить интернет соединение

## Развертывание на Railway

### 1. Добавить переменные в Settings → Variables

```
DIGEST_ENABLED=true
DIGEST_CHANNEL_ID=@YOUR_CHANNEL_ID
DIGEST_HOUR=9
DIGEST_MINUTE=0
DIGEST_TIMEZONE=UTC
COINGECKO_API_KEY=YOUR_API_KEY
```

### 2. Убедиться что bot.py в worker dyno

**Procfile:**
```
web: python api_server.py
worker: python bot.py
```

### 3. Проверить логи

```bash
railway logs worker
```

## Расширение функционала

### Добавить свой источник новостей

В `crypto_digest.py` измените `NewsCollector.FEEDS`:

```python
FEEDS = {
    "CoinTelegraph": "https://cointelegraph.com/feed",
    "MyCustomSource": "https://example.com/feed",
}
```

### Добавить дополнительные события

В `crypto_digest.py` расширьте `FinanceNewsCollector.get_important_events()`:

```python
events = [
    {
        "time": "14:30 UTC",
        "title": "My Custom Event",
        "importance": "High",
        "impact": "USD"
    }
]
```

### Изменить формат дайджеста

В `digest_formatter.py` модифицируйте `DigestFormatter` методы:

```python
def format_market_overview(self, data: Dict) -> str:
    # Ваш кастомный формат
    pass
```

## API справка

### DailyDigestScheduler

```python
class DailyDigestScheduler:
    async def initialize()          # Инициализировать планировщик
    async def send_daily_digest()   # Отправить дайджест прямо сейчас
    async def send_message_safe()   # Безопасно отправить сообщение
    async def stop()                # Остановить планировщик
```

### Функции модуля

```python
async def initialize_digest_scheduler()    # Инициализировать
async def stop_digest_scheduler()          # Остановить
def get_digest_scheduler()                 # Получить текущий экземпляр
```

## Версия

**v0.28.0** - Initial release
- ✅ Daily scheduling (APScheduler)
- ✅ CoinGecko API integration
- ✅ HTML formatted messages
- ✅ Multi-part message support
- ✅ Retry mechanism

## Лицензия

MIT
