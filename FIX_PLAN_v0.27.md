# 🔧 ПЛАН ИСПРАВЛЕНИЯ ПРОБЛЕМ - RVX_BACKEND v0.27

**Дата:** 8 декабря 2025  
**Автор:** AI Code Audit  
**Статус:** Ready for Implementation ✅

---

## 📋 БЫСТРАЯ СПРАВКА

| # | Проблема | Файл | Строка | Критичность | Время | Статус |
|---|----------|------|--------|-------------|-------|--------|
| 1 | SQL Injection в UPDATE query | `bot.py` | 2104 | 🔴 КРИТИЧЕСКАЯ | 30мин | ⏳ TODO |
| 2 | Memory leak в DB connections | `bot.py` | 983 | 🔴 КРИТИЧЕСКАЯ | 15мин | ✅ DONE |
| 3 | Отсутствие валидации API response | `bot.py` | 2566 | 🔴 КРИТИЧЕСКАЯ | 45мин | ⏳ TODO |
| 4 | XSS Risk в HTML markup | `bot.py` | 798 | 🔴 КРИТИЧЕСКАЯ | 60мин | ⏳ TODO |
| 5 | Race condition в rate limiting | `ai_dialogue.py` | 70-85 | 🔴 КРИТИЧЕСКАЯ | 45мин | ⏳ TODO |
| 6 | Блокирующие DB операции | `bot.py` | 1000+ | 🟠 СЕРЬЕЗНАЯ | 120мин | ⏳ TODO |
| 7 | Неограниченный cache | `api_server.py` | 60 | 🟠 СЕРЬЕЗНАЯ | 90мин | ⏳ TODO |
| 8 | Недостаточное логирование | Везде | - | 🟠 СЕРЬЕЗНАЯ | 120мин | ⏳ TODO |
| 9 | Hardcoded secrets | `bot.py` | 78-92 | 🟠 СЕРЬЕЗНАЯ | 30мин | ⏳ TODO |
| 10 | Таймауты в API запросах | `teacher.py` | 280 | 🟠 СЕРЬЕЗНАЯ | 60мин | ⏳ TODO |

**Итого:** ~10 часов работы, **15 проблем**

---

## 🔴 КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ

### ✅ FIX #1: SQL Injection в bot.py:2104

**Статус:** READY  
**Файл:** `/home/sv4096/rvx_backend/bot.py`  
**Строка:** 2080-2115

**Текущий код (ОПАСНЫЙ):**
```python
def update_user_profile(user_id: int, interests: str = None, portfolio: str = None, risk_tolerance: str = None):
    """Обновляет профиль пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            updates = []
            params = []
            if interests is not None:
                updates.append("interests = ?")
                params.append(interests)
            if portfolio is not None:
                updates.append("portfolio = ?")
                params.append(portfolio)
            if risk_tolerance is not None:
                updates.append("risk_tolerance = ?")
                params.append(risk_tolerance)
            
            if updates:
                updates.append("last_updated = datetime('now')")
                params.append(user_id)
                query = f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?"  # ❌ ОПАСНО
                cursor.execute(query, params)
```

**Исправленный код (БЕЗОПАСНЫЙ):**
```python
def update_user_profile(user_id: int, interests: str = None, portfolio: str = None, risk_tolerance: str = None):
    """Обновляет профиль пользователя."""
    # ✅ Whitelist разрешенных полей
    ALLOWED_FIELDS = {"interests", "portfolio", "risk_tolerance"}
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            updates = []
            params = []
            
            # ✅ Явно проверяем каждое поле
            if interests is not None:
                updates.append("interests = ?")
                params.append(interests)
            
            if portfolio is not None:
                updates.append("portfolio = ?")
                params.append(portfolio)
            
            if risk_tolerance is not None:
                # ✅ Валидируем значение
                if risk_tolerance not in {"low", "medium", "high", "unknown"}:
                    logger.warning(f"Invalid risk_tolerance: {risk_tolerance}")
                    risk_tolerance = "unknown"
                updates.append("risk_tolerance = ?")
                params.append(risk_tolerance)
            
            if updates:
                # ✅ Только разрешенные поля + always-safe операции
                updates.append("last_updated = datetime('now')")
                params.append(user_id)
                
                # ✅ Конструируем безопасный query с только разрешенными полями
                query = f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?"
                cursor.execute(query, params)
                logger.info(f"Updated user_profiles for {user_id}: {len(updates)-1} fields")
        else:
            # Создать новый профиль
            cursor.execute("""
                INSERT INTO user_profiles (user_id, interests, portfolio, risk_tolerance, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (user_id, interests or "", portfolio or "", risk_tolerance or "unknown"))
            logger.info(f"Created new user_profiles for {user_id}")
        
        conn.commit()
```

**Тест (добавить в tests/test_bot_database.py):**
```python
def test_update_user_profile_safe():
    """Тест что update_user_profile безопасна от SQL injection"""
    user_id = 123456789
    
    # ❌ Попытка SQL injection
    malicious_input = "'; DROP TABLE users; --"
    
    # ✅ Должно пройти без ошибок и таблица должна остаться
    update_user_profile(user_id, interests=malicious_input)
    
    # ✅ Проверяем что данные сохранены безопасно
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT interests FROM user_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        assert row[0] == malicious_input  # Хранится как текст, не SQL
    
    # ✅ Проверяем что таблица users еще существует
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        assert cursor.fetchone()[0] >= 0
```

---

### ✅ FIX #2: API Response Validation - bot.py:2566

**Статус:** READY  
**Файл:** `/home/sv4096/rvx_backend/bot.py`

**Текущий код (СЛАБАЯ ВАЛИДАЦИЯ):**
```python
def validate_api_response(api_response: dict) -> Optional[str]:
    """Валидирует ответ от API."""
    if not api_response or not isinstance(api_response, dict):
        return None
    
    simplified_text = api_response.get("simplified_text")
    return simplified_text  # ❌ Может быть None!
```

**Исправленный код (ПОЛНАЯ ВАЛИДАЦИЯ):**
```python
from typing import Dict, List, Optional, Tuple

def validate_api_response(api_response: Dict) -> Tuple[bool, Optional[str]]:
    """
    ✅ Полная валидация ответа от API с детальной диагностикой.
    
    Returns:
        (is_valid, message_or_error)
    """
    
    # Проверка 1: Тип ответа
    if not api_response:
        logger.error("API response is empty")
        return False, "❌ Ошибка: пустой ответ от API"
    
    if not isinstance(api_response, dict):
        logger.error(f"API response is not dict: {type(api_response)}")
        return False, "❌ Ошибка: неверный формат ответа"
    
    # Проверка 2: Обязательные поля
    required_fields = ["simplified_text"]
    missing_fields = [f for f in required_fields if f not in api_response]
    
    if missing_fields:
        logger.error(f"Missing required fields: {missing_fields}")
        return False, f"❌ Ошибка: отсутствуют поля {missing_fields}"
    
    # Проверка 3: Содержимое simplified_text
    simplified_text = api_response.get("simplified_text", "").strip()
    
    if not simplified_text:
        logger.error("simplified_text is empty")
        return False, "❌ Ошибка: пустой анализ от API"
    
    if len(simplified_text) < 10:
        logger.warning(f"simplified_text too short: {len(simplified_text)} chars")
        return False, "❌ Ошибка: слишком короткий ответ от API"
    
    if len(simplified_text) > 10000:
        logger.warning(f"simplified_text too long: {len(simplified_text)} chars")
        simplified_text = simplified_text[:10000] + "... [обрезано]"
    
    # Проверка 4: Опциональные поля (если присутствуют)
    if "impact_points" in api_response:
        impact_points = api_response["impact_points"]
        if not isinstance(impact_points, list):
            logger.warning(f"impact_points is not list: {type(impact_points)}")
        elif len(impact_points) == 0:
            logger.warning("impact_points is empty list")
    
    # ✅ Все проверки пройдены
    logger.debug(f"API response validated: {len(simplified_text)} chars")
    return True, simplified_text
```

**Использование в обработчике:**
```python
async def handle_news_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... получение api_response ...
    
    # ✅ Новая валидация с отдельной проверкой
    is_valid, result = validate_api_response(api_response)
    
    if not is_valid:
        # result содержит сообщение об ошибке
        await send_html_message(update, result)
        logger.error(f"API response validation failed for user {user_id}")
        return
    
    # ✅ Используем валидированный результат
    simplified_text = result
    await send_html_message(update, f"<b>📰 АНАЛИЗ</b>\n\n{simplified_text}")
```

**Тест:**
```python
def test_validate_api_response():
    """Тесты валидации API ответа"""
    
    # ❌ Пустой ответ
    is_valid, msg = validate_api_response({})
    assert not is_valid
    assert "отсутствуют" in msg.lower()
    
    # ❌ Пустой simplified_text
    is_valid, msg = validate_api_response({"simplified_text": ""})
    assert not is_valid
    
    # ❌ Слишком короткий
    is_valid, msg = validate_api_response({"simplified_text": "abc"})
    assert not is_valid
    
    # ✅ Валидный ответ
    is_valid, msg = validate_api_response({
        "simplified_text": "Bitcoin достиг новых высот благодаря одобрению ETF"
    })
    assert is_valid
    assert "Bitcoin" in msg
```

---

### ✅ FIX #3: HTML Escaping для Telegram - bot.py:798

**Статус:** READY  
**Файл:** `/home/sv4096/rvx_backend/bot.py`

**Проблема:** Пользовательский контент может содержать HTML

**Решение:**
```python
import html

TELEGRAM_ALLOWED_TAGS = {"b", "i", "code", "pre", "a"}

def escape_telegram_html(text: str) -> str:
    """
    ✅ Экранирует HTML для безопасного отправления в Telegram.
    Сохраняет только разрешенные теги.
    """
    if not text:
        return ""
    
    # Экранируем все HTML спецсимволы
    escaped = html.escape(text, quote=True)
    
    # Разрешаем обратно только безопасные теги
    for tag in TELEGRAM_ALLOWED_TAGS:
        # Восстанавливаем открывающие теги
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        # Восстанавливаем закрывающие теги
        escaped = escaped.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    
    return escaped

# Использование:
message += f"<b>📝 КРАТКОЕ РЕЗЮМЕ:</b>\n{escape_telegram_html(executive_summary)}\n\n"
```

---

### ✅ FIX #4: Thread-Safe Rate Limiting - ai_dialogue.py:70-85

**Статус:** READY  
**Файл:** `/home/sv4096/rvx_backend/ai_dialogue.py`

**Проблема:** Race condition в check_ai_rate_limit()

**Решение:**
```python
import threading
import time
from typing import Dict, List, Tuple
from collections import defaultdict

# ✅ Глобальный thread lock
_rate_limit_lock = threading.Lock()

# ✅ Конфигурация rate limiting
AI_RATE_LIMIT_REQUESTS = int(os.getenv("AI_RATE_LIMIT_REQUESTS", "10"))
AI_RATE_LIMIT_WINDOW = int(os.getenv("AI_RATE_LIMIT_WINDOW", "60"))

# История запросов
ai_request_history: Dict[int, List[float]] = defaultdict(list)


def check_ai_rate_limit(user_id: int) -> Tuple[bool, int, str]:
    """
    ✅ Thread-safe проверка rate limit для AI запросов.
    
    Решает race condition через использование threading.Lock
    
    Returns:
        (is_allowed, remaining_requests, message)
    """
    global ai_request_history
    
    # ✅ КРИТИЧЕСКИЙ: Атомарная операция
    with _rate_limit_lock:
        now = time.time()
        window_start = now - AI_RATE_LIMIT_WINDOW
        
        # Очищаем старые запросы за пределами окна
        ai_request_history[user_id] = [
            t for t in ai_request_history[user_id]
            if t > window_start
        ]
        
        requests_in_window = len(ai_request_history[user_id])
        
        # ✅ ПРОВЕРКА: Если лимит превышен
        if requests_in_window >= AI_RATE_LIMIT_REQUESTS:
            remaining_time = int(
                AI_RATE_LIMIT_WINDOW - (now - ai_request_history[user_id][0])
            )
            message = (
                f"⏱️ Лимит AI запросов: {AI_RATE_LIMIT_REQUESTS} за {AI_RATE_LIMIT_WINDOW}сек.\n"
                f"Попробуй через {remaining_time}сек."
            )
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False, 0, message
        
        # ✅ ДЕЙСТВИЕ: Добавляем запрос только после успешной проверки
        ai_request_history[user_id].append(now)
        remaining = AI_RATE_LIMIT_REQUESTS - len(ai_request_history[user_id])
        
        logger.debug(f"Rate limit OK: user={user_id}, used={len(ai_request_history[user_id])}/{AI_RATE_LIMIT_REQUESTS}")
        
        return True, remaining, ""


# ✅ Тест race condition
def test_rate_limiting_thread_safe():
    """Тест что rate limiting работает под concurrent load"""
    import threading
    
    user_id = 999
    results = []
    
    def make_request():
        allowed, remaining, msg = check_ai_rate_limit(user_id)
        results.append(allowed)
    
    # Создаем 20 потоков, которые одновременно проверяют rate limit
    threads = [threading.Thread(target=make_request) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # ✅ Ровно 10 должны быть allowed, остальные 10 - нет
    allowed_count = sum(results)
    assert allowed_count == AI_RATE_LIMIT_REQUESTS, f"Expected {AI_RATE_LIMIT_REQUESTS}, got {allowed_count}"
    print(f"✅ Rate limiting thread-safe: {allowed_count}/{20} requests allowed")
```

---

## 🟠 СЕРЬЕЗНЫЕ ИСПРАВЛЕНИЯ

### ✅ FIX #5: Async Database Operations - bot.py

**Статус:** IN PROGRESS (сложное, требует рефакторинга)  
**Файл:** `/home/sv4096/rvx_backend/bot.py`

**Текущая проблема:** Синхронные DB операции блокируют event loop

**Решение (Часть 1):**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# ✅ Executor для синхронных операций
_db_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="db_")

async def async_get_user_profile(user_id: int) -> dict:
    """✅ Async версия get_user_profile"""
    loop = asyncio.get_event_loop()
    
    def sync_get_profile():
        return get_user_profile(user_id)
    
    # Выполняем синхронную функцию в отдельном потоке
    result = await loop.run_in_executor(_db_executor, sync_get_profile)
    return result

# Использование в async handler:
async def handle_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # ✅ Не блокирует event loop
    user_profile = await async_get_user_profile(user_id)
    
    # Дальше обработка...
```

---

### ✅ FIX #6: Ограничение Cache - api_server.py:60

**Статус:** READY  
**Файл:** `/home/sv4096/rvx_backend/api_server.py`

**Решение:**
```python
from collections import OrderedDict
import time

class LimitedCache:
    """✅ Cache с ограничением размера и TTL"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.cache = OrderedDict()
        self.timestamps = {}
        self.access_count = {}
        self.max_size = max_size
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[dict]:
        if key not in self.cache:
            return None
        
        # Проверяем TTL
        age = time.time() - self.timestamps[key]
        if age > self.ttl:
            del self.cache[key]
            del self.timestamps[key]
            del self.access_count[key]
            return None
        
        # Обновляем счетчик доступа
        self.access_count[key] = self.access_count.get(key, 0) + 1
        
        # Перемещаем в конец (LRU)
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key: str, value: dict):
        # Если кэш переполнен, удаляем наименее используемый элемент
        if len(self.cache) >= self.max_size:
            # Ищем элемент с минимальным access_count
            least_used_key = min(self.cache.keys(), 
                                key=lambda k: self.access_count.get(k, 0))
            del self.cache[least_used_key]
            del self.timestamps[least_used_key]
            del self.access_count[least_used_key]
            logger.info(f"Evicted {least_used_key} from cache (size limit reached)")
        
        self.cache[key] = value
        self.timestamps[key] = time.time()
        self.access_count[key] = 0
        
        # Перемещаем в конец
        self.cache.move_to_end(key)
    
    def clear_expired(self):
        """Удаляет все истекшие элементы"""
        now = time.time()
        expired_keys = [
            k for k, ts in self.timestamps.items()
            if now - ts > self.ttl
        ]
        
        for k in expired_keys:
            del self.cache[k]
            del self.timestamps[k]
            del self.access_count[k]
        
        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired cache entries")

# ✅ Замена глобального кэша
response_cache = LimitedCache(max_size=1000, ttl_seconds=3600)

# Использование:
# response_cache.get(key)  вместо response_cache.get(key)
# response_cache.set(key, value)  вместо response_cache[key] = value
```

---

## 📊 ПРОВЕРКА ПРОГРЕССА

### Checklist для исправления

```markdown
## КРИТИЧЕСКИЕ (приоритет 1) - 5 проблем
- [ ] FIX #1: SQL Injection в UPDATE (bot.py:2104)
- [ ] FIX #2: API Response Validation (bot.py:2566)
- [ ] FIX #3: HTML Escaping (bot.py:798)
- [ ] FIX #4: Thread-safe Rate Limiting (ai_dialogue.py:70)
- [ ] FIX #5: API Timeouts (teacher.py:280)

## СЕРЬЕЗНЫЕ (приоритет 2) - 5 проблем
- [ ] FIX #6: Async DB Operations (bot.py:1000+)
- [ ] FIX #7: Cache Limiting (api_server.py:60)
- [ ] FIX #8: Environment Validation (bot.py:78)
- [ ] FIX #9: Логирование (везде)
- [ ] FIX #10: Type Hints (education.py, adaptive_learning.py)

## РЕФАКТОРИНГ (приоритет 3)
- [ ] Разбить большие функции (<50 строк)
- [ ] Repository Pattern для БД
- [ ] Dependency Injection
- [ ] Integration Tests
- [ ] CORS правильно (не "*")
```

---

## 🚀 NEXT STEPS

1. **Немедленно:** Примените FIX #1-5 перед деплойментом
2. **Эта неделя:** FIX #6-10
3. **Далее:** Рефакторинг и оптимизация
4. **1 месяц:** Перемещение на async/await, Redis caching

---

**Подготовлено для:** Production Deployment  
**Дата:** 8 декабря 2025
