# 🤖 Bot Security Integration Guide

> Руководство по интеграции аутентификации бота с защищенным API  
> Версия: 1.0 | Дата: 2025-12-09

---

## 📋 Содержание

1. [Обзор](#обзор)
2. [Настройка бота](#настройка-бота)
3. [Bearer Token использование](#bearer-token-использование)
4. [Обработка ошибок](#обработка-ошибок)
5. [Тестирование](#тестирование)

---

## 🔍 Обзор

Начиная с версии 1.0 безопасности, API требует Bearer token аутентификацию для всех запросов к `/explain_news`.

### Поток

```
Bot.py
  ↓
  Читает BOT_API_KEY из .env
  ↓
  Добавляет Authorization: Bearer {BOT_API_KEY}
  ↓
  Отправляет POST /explain_news
  ↓
API Server
  ↓
  Проверяет Bearer token
  ↓
  ✅ Если валиден → обрабатывает запрос
  ❌ Если невалиден → возвращает 401
```

---

## 🔧 Настройка бота

### Шаг 1: Обновить `.env`

```env
# ... другие переменные ...

# SECURITY: API Key для аутентификации
BOT_API_KEY=rvx_key_your_generated_key_here
API_URL_NEWS=http://localhost:8000/explain_news
```

### Шаг 2: Получить API ключ

**Если вы администратор:**

```bash
# 1. Запустить API сервер
python3 api_server.py

# 2. В другом терминале создать ключ
curl -X POST http://localhost:8000/auth/create_api_key \
  -H "X-Admin-Token: admin_token_change_this_to_secure_random_token_in_production" \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. Сохранить значение api_key в BOT_API_KEY в .env
```

**Если ключ уже создан:**

Просто добавьте существующий ключ в `.env`:

```env
BOT_API_KEY=rvx_key_HtpbdjaSDXWU_Q22m7L3SK_your_actual_key_here
```

### Шаг 3: Перезапустить бот

```bash
python3 bot.py
```

Проверьте в логах что ключ загружен:

```
✅ BOT_API_KEY loaded from environment
```

---

## 📤 Bearer Token использование

### Что изменилось в `bot.py`

**До (v0.4.0):**
```python
async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
    response = await client.post(API_URL_NEWS, json=request_payload)
```

**После (v1.0):**
```python
async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
    headers = {
        "X-User-ID": str(user_id),
    }
    if BOT_API_KEY:
        headers["Authorization"] = f"Bearer {BOT_API_KEY}"
    response = await client.post(
        API_URL_NEWS, 
        json=request_payload, 
        headers=headers
    )
```

### Как это работает

1. **Загрузка ключа** (строка 138-143):
   ```python
   BOT_API_KEY = os.getenv("BOT_API_KEY", "")
   ```

2. **Добавление в запрос** (строка 3711-3720):
   ```python
   if BOT_API_KEY:
       headers["Authorization"] = f"Bearer {BOT_API_KEY}"
   ```

3. **Логирование использования** (автоматическое):
   ```
   ✅ API request: POST /explain_news with Bearer token
   ```

---

## ⚠️ Обработка ошибок

### Error: 401 Unauthorized

**Причины:**
- BOT_API_KEY не установлен в `.env`
- BOT_API_KEY имеет неправильное значение
- API ключ был отключен администратором

**Решение:**
```python
# В bot.py уже добавлена обработка (строка 3755-3765):

if e.response.status_code == 401:
    logger.error(f"🔐 Ошибка аутентификации...")
    last_error = "Ошибка аутентификации API"
    break  # ← ВАЖНО: не повторяем попытку!
elif e.response.status_code == 500:
    # Сервер ошибка - повторяем попытку
    continue
```

**Проверка ключа:**
```bash
# Проверить что ключ валиден
curl -X POST http://localhost:8000/auth/verify_api_key \
  -H "Content-Type: application/json" \
  -d '{"api_key": "rvx_key_your_key"}'

# Если valid=false - ключ невалиден, получите новый
```

### Error: 429 Too Many Requests

**Причина:** Превышена лимит запросов с IP адреса

**Решение:**
- Дождитесь окончания временного окна (обычно 1 минута)
- В production увеличьте `RATE_LIMIT_PER_MINUTE` в `.env` API

### Error: Connection Refused

**Причина:** API сервер не запущен

**Решение:**
```bash
# Убедитесь что API сервер запущен
python3 api_server.py

# Проверьте что он слушает на нужном порту
curl http://localhost:8000/health
```

---

## ✅ Тестирование

### Тест 1: Проверить что ключ загружен

```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("BOT_API_KEY", "")

if api_key:
    print(f"✅ API Key loaded: {api_key[:30]}...")
else:
    print("❌ API Key NOT found in .env")
```

### Тест 2: Проверить что ключ валиден

```bash
# Убедитесь что API сервер запущен
python3 api_server.py &

# В другом терминале:
sleep 2

curl -X POST http://localhost:8000/auth/verify_api_key \
  -H "Content-Type: application/json" \
  -d '{"api_key": "rvx_key_your_key"}'

# Ожидаемый результат:
# {
#   "is_valid": true,
#   "key_name": "...",
#   "created_at": "...",
#   "total_requests": N
# }
```

### Тест 3: Отправить запрос с токеном

```bash
API_KEY="rvx_key_your_key"

curl -X POST http://localhost:8000/explain_news \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user" \
  -d '{"text_content": "Bitcoin price is rising"}'

# Ожидаемый результат: 200 OK с анализом
```

### Тест 4: Отправить запрос без токена (должна быть ошибка)

```bash
curl -X POST http://localhost:8000/explain_news \
  -H "Content-Type: application/json" \
  -d '{"text_content": "Bitcoin price is rising"}'

# Ожидаемый результат: 401 Unauthorized
# {"detail": "Missing API key"}
```

### Тест 5: Запустить bot.py с симуляцией

```python
# Создайте test_bot_auth.py
import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_bot_auth():
    BOT_API_KEY = os.getenv("BOT_API_KEY", "")
    API_URL = os.getenv("API_URL_NEWS", "http://localhost:8000/explain_news")
    
    print(f"Using API Key: {BOT_API_KEY[:30]}...")
    print(f"Using API URL: {API_URL}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        headers = {}
        if BOT_API_KEY:
            headers["Authorization"] = f"Bearer {BOT_API_KEY}"
        
        try:
            response = await client.post(
                API_URL,
                json={"text_content": "Ethereum upgrade announced"},
                headers=headers
            )
            print(f"✅ Response: {response.status_code}")
            print(f"   Body: {response.json()}")
        except Exception as e:
            print(f"❌ Error: {e}")

# Запустить
asyncio.run(test_bot_auth())
```

---

## 📊 Логирование

При успешной аутентификации вы увидите в логах:

```
2025-12-09 21:18:19 - RVX_API - INFO - 📨 POST /explain_news | IP: 192.168.1.100
2025-12-09 21:18:19 - RVX_API - INFO - 📰 Запрос анализа новости от user_123
2025-12-09 21:18:20 - RVX_API - INFO - ✅ /explain_news завершен за 0.55s | Статус: 200
```

При ошибке аутентификации:

```
2025-12-09 21:18:19 - RVX_API - INFO - 📨 POST /explain_news | IP: 192.168.1.100
2025-12-09 21:18:19 - RVX_API - WARNING - ⚠️ API key missing from 192.168.1.100
2025-12-09 21:18:19 - RVX_API - WARNING - ⚠️ /explain_news завершен за 0.00s | Статус: 401
```

---

## 🔍 Как проверить аудит

```bash
# Посмотреть все попытки API запросов
sqlite3 audit_events.db \
  "SELECT timestamp, category, severity, action FROM audit_events WHERE category='API' LIMIT 20;"

# Посмотреть ошибки аутентификации
sqlite3 audit_events.db \
  "SELECT timestamp, severity, details FROM audit_events WHERE action LIKE '%invalid%' LIMIT 10;"

# Посмотреть использование API ключа
sqlite3 auth_keys.db \
  "SELECT key_name, total_requests, created_at FROM api_keys;"
```

---

## 🎯 Checklist для production

- [ ] BOT_API_KEY добавлен в `.env` бота
- [ ] API ключ проверен через `/auth/verify_api_key`
- [ ] Запущен тест bot_auth с симуляцией
- [ ] Проверены логи в `rvx.log`
- [ ] Бот перезапущен после обновления `.env`
- [ ] Отправлена тестовая новость через бота
- [ ] Проверены audit logs в БД
- [ ] Все 9 интеграционных тестов прошли ✅

---

## 📞 Поддержка

Если возникли проблемы:

1. Проверьте что `.env` содержит правильный `BOT_API_KEY`
2. Убедитесь что API сервер запущен (`curl http://localhost:8000/health`)
3. Проверьте что ключ валиден (`/auth/verify_api_key`)
4. Посмотрите логи: `tail -f rvx.log`
5. Откройте issue в репозитории

---

**Версия:** 1.0  
**Статус:** ✅ Production Ready  
**Последнее обновление:** 2025-12-09
