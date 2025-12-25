# 🚀 ПЛАН ДЕЙСТВИЙ - Улучшения RVX Bot (Next 3 Sprints)

## ФИ ЛОСЬ ОБНОВЛЕНО: 25 Декабря 2025

---

## 📍 ТЕКУЩЕЕ СОСТОЯНИЕ

```
v0.37.15 Status:
✅ User Profile Feature - MERGED
✅ All Systems Working
✅ Database Persistent
❌ Monolithic bot.py (13K lines)
❌ No database indices
❌ N+1 query problems
❌ Limited test coverage
```

---

## 🎯 SPRINT 1: СРОЧНЫЕ СТРУКТУРНЫЕ УЛУЧШЕНИЯ (2 недели)

### Этап 1.1: Database Layer Optimization (2 дня)
**Задача:** Добавить индексы и оптимизировать queries

**Действия:**
```sql
-- 1. Добавить критические индексы
CREATE INDEX idx_users_xp ON users(xp DESC);
CREATE INDEX idx_users_level ON users(level);
CREATE INDEX idx_users_created_at ON users(created_at DESC);
CREATE INDEX idx_quiz_stats_user_lesson ON user_quiz_stats(user_id, lesson_id);
CREATE INDEX idx_progress_user_lesson ON user_progress(user_id, lesson_id);
CREATE INDEX idx_leaderboard ON users(xp DESC, level DESC);

-- 2. Analyze query plans
EXPLAIN QUERY PLAN SELECT * FROM users ORDER BY xp DESC LIMIT 100;

-- 3. Vacuum database
VACUUM;
ANALYZE;
```

**Результат:** 10-100x speedup на Leaderboard

**Файлы для изменения:**
- `bot.py`: Lines where queries occur
- Создать `database/migrations/001_add_indices.sql`

---

### Этап 1.2: Рефакторинг bot.py - Часть 1 (5 дней)
**Задача:** Начать разделять bot.py на модули

**Этап 1.2a: Создать структуру папок**
```bash
mkdir -p bot/{models,services,handlers,formatters,utils}
touch bot/__init__.py
touch bot/models/__init__.py
touch bot/services/__init__.py
touch bot/handlers/__init__.py
touch bot/formatters/__init__.py
touch bot/utils/__init__.py
```

**Этап 1.2b: Переместить функции (начиная с самых простых)**

1. **Formatters** (No dependencies)
```python
# bot/formatters/text_formatter.py
def format_header(title: str) -> str:
    """Move from bot.py line ~1200"""
    
def format_section(title: str, content: str) -> str:
    """Move formatting functions"""

# bot/formatters/profile_formatter.py
def format_user_profile(profile_data: dict) -> str:
    """Move from bot.py line ~4983"""
```

2. **Utils** (Security, validation)
```python
# bot/utils/security.py
def sanitize_input(text: str) -> str:
    """Move security functions"""

# bot/utils/errors.py
class RVXError(Exception): pass
class LLMError(RVXError): pass
class DatabaseError(RVXError): pass
```

3. **Models** (Data structures)
```python
# bot/models/user.py
from pydantic import BaseModel

class UserProfile(BaseModel):
    user_id: int
    username: str
    xp: int
    level: int
    badges: list

# bot/models/lesson.py
class Lesson(BaseModel):
    topic: str
    difficulty: str
    title: str
```

**Результат:** 3-4 модуля создано, bot.py сокращен на ~1000 строк

---

### Этап 1.3: Оптимизировать N+1 Queries (2-3 дня)
**Задача:** Переписать queries с JOINs

**Найти и переписать:**
1. **Leaderboard query** (bot.py ~5000+)
   ```python
   # ❌ ДО: 1 + N queries
   users = get_all_users()
   for user in users:
       stats = get_user_stats(user.id)
   
   # ✅ ПОСЛЕ: 1 query
   cursor.execute("""
       SELECT u.*, COUNT(DISTINCT uqs.lesson_id) as tests
       FROM users u
       LEFT JOIN user_quiz_stats uqs ON u.user_id = uqs.user_id
       GROUP BY u.user_id
   """)
   ```

2. **Profile query** (bot.py ~4900+)
   ```python
   # Оптимизировать get_user_profile_data()
   # Вместо 4 queries → 1 query с LEFT JOINs
   ```

3. **Лидерборд для периода** (bot.py ~5100+)
   ```python
   # Оптимизировать get_leaderboard_data()
   ```

**Тестирование:**
```bash
# Перед: EXPLAIN QUERY PLAN (проверить FULL SCAN)
# После: EXPLAIN QUERY PLAN (проверить use of index)
```

**Результат:** 10-100x ускорение для popular queries

---

## 🔄 SPRINT 2: НАДЕЖНОСТЬ И ТЕСТИРОВАНИЕ (2 недели)

### Этап 2.1: Transaction Management (2 дня)
**Задача:** Добавить ACID гарантии для multi-step операций

**Найти все multi-step операции:**
1. Quiz completion → add XP → add badge → increment level
2. User profile update → multiple fields
3. Lesson completion → save progress → add XP → check achievements

**Паттерн для всех:**
```python
# bot/utils/database_utils.py
@contextmanager
def transaction(conn):
    """Transaction context manager with rollback"""
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")  # Lock immediately
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Transaction failed: {e}")
        raise

# Использование везде:
with transaction(conn) as cursor:
    add_xp(cursor, user_id, 10)
    increment_level(cursor, user_id)
    add_badge(cursor, user_id, "level_5")
    # All or nothing!
```

**Результат:** Zero data inconsistency

---

### Этап 2.2: Unit Tests (3 дня)
**Задача:** Написать основные unit тесты

**Структура:**
```python
# tests/test_database.py
def test_database_connection()
def test_get_user_profile_data()
def test_profile_formatting()
def test_n_plus_one_fix()

# tests/test_llm.py
def test_groq_provider()
def test_fallback_to_mistral()
def test_fallback_chain()

# tests/test_profile.py
def test_profile_data_collection()
def test_profile_formatting()
def test_badge_system()

# tests/test_security.py
def test_sql_injection_blocked()
def test_rate_limiting()
def test_sanitize_input()
```

**Минимум тестов:** 30-40
**Target coverage:** >80%

**Запуск:**
```bash
pytest tests/ -v --cov=bot
```

**Результат:** Confidence в коде, easy regression detection

---

### Этап 2.3: Exception Handling Standardization (1 день)
**Задача:** Единый способ обработки ошибок

**Создать:**
```python
# bot/utils/errors.py
class RVXError(Exception):
    """Base exception"""
    pass

class LLMError(RVXError):
    """AI provider failed"""
    pass

class DatabaseError(RVXError):
    """Database operation failed"""
    pass

class ValidationError(RVXError):
    """Input validation failed"""
    pass

class RateLimitError(RVXError):
    """User rate limited"""
    pass
```

**Использовать везде:**
```python
try:
    teach_lesson(user_id)
except LLMError as e:
    logger.error(f"LLM: {e}")
    await send_error(update, "Ошибка AI, попробуйте позже")
except DatabaseError as e:
    logger.critical(f"DB: {e}")
    await send_error(update, "Ошибка БД, попробуйте позже")
except ValidationError as e:
    logger.warning(f"Validation: {e}")
    await send_error(update, f"Неверный ввод: {e}")
```

**Результат:** Consistent error handling throughout

---

## 🎨 SPRINT 3: РЕФАКТОРИНГ И ОПТИМИЗАЦИЯ (2 недели)

### Этап 3.1: Полный рефакторинг bot.py (5 дней)
**Задача:** Разделить оставшиеся 10K строк на сервисы и handler'ы

**Модули для создания:**
```python
# bot/services/llm_service.py
class LLMOrchestrator:
    def teach_lesson(topic, difficulty)
    def explain_news(text)

# bot/services/teaching_service.py
class TeachingService:
    def get_lesson_content()
    def show_quiz_question()
    def handle_quiz_answer()

# bot/services/profile_service.py
class ProfileService:
    def get_user_profile()
    def format_profile()
    def get_achievements()

# bot/handlers/callback_handler.py
class CallbackRouter:
    async def handle_start_profile(callback)
    async def handle_teach_menu(callback)
    async def handle_quiz_answer(callback)
```

**Результат:** bot.py сокращен до 2000-3000 строк, все модули <1000 строк

---

### Этап 3.2: Caching Optimization (2 дня)
**Задача:** Улучшить caching стратегию

**Вариант 1: Улучшить SQLite cache**
```python
# bot/services/cache_service.py
class CacheService:
    def get(key):
        # Check if not expired
        # Return value
    
    def set(key, value, ttl):
        # Store with expiration
    
    def invalidate(pattern):
        # Invalidate by pattern
```

**Вариант 2: Redis (для production)**
```python
import redis
cache = redis.Redis(host='localhost')
cache.set(f"profile:{user_id}", json.dumps(profile), ex=3600)
```

**Результат:** Faster response times, reduced DB load

---

### Этап 3.3: Monitoring & Metrics (2 дня)
**Задача:** Добавить метрики для анализа

**Implement:**
```python
# bot/utils/metrics.py
class Metrics:
    llm_provider_usage = {}
    response_times = {}
    error_rates = {}
    
    def record_llm_call(provider, elapsed_time):
        llm_provider_usage[provider] += 1
        response_times[provider].append(elapsed_time)
    
    def get_stats():
        return {
            'groq_usage': llm_provider_usage.get('groq', 0),
            'avg_response_time': mean(response_times['groq']),
            'fallback_rate': fallback_count / total_count
        }
```

**Dashboard:**
```
Groq: 85% usage, 320ms avg
Mistral: 12% usage, 450ms avg
DeepSeek: 2% usage, 600ms avg
Gemini: 1% usage, 800ms avg

Error rate: 0.5%
Fallback rate: 2%
```

---

## 📊 TIMELINE И MILESTONES

```
Week 1-2 (Sprint 1):
  ✓ Add database indices (Day 1)
  ✓ Start bot.py refactoring (Days 2-5)
  ✓ Optimize N+1 queries (Days 4-5)
  
Week 3-4 (Sprint 2):
  ✓ Add transaction management (Days 1-2)
  ✓ Write unit tests (Days 1-4)
  ✓ Standardize error handling (Day 4)
  
Week 5-6 (Sprint 3):
  ✓ Complete bot.py refactoring (Days 1-5)
  ✓ Implement Redis/advanced caching (Days 2-3)
  ✓ Add monitoring & metrics (Days 4-5)
```

**Total: 6 weeks to complete all improvements**

---

## 🎯 ВЕРСИОНИРОВАНИЕ

```
v0.37.15 → v0.38.0 (Sprint 1 - DB Optimization)
  - Add database indices
  - Optimize N+1 queries
  - Start bot.py refactoring
  
v0.38.0 → v0.39.0 (Sprint 2 - Reliability)
  - Add transaction management
  - Unit tests (30+ tests)
  - Exception handling standardization
  
v0.39.0 → v0.40.0 (Sprint 3 - Refactoring Complete)
  - Complete bot.py refactoring
  - Redis caching
  - Monitoring & metrics
```

---

## 🎁 EXPECTED BENEFITS

### Performance
- **Leaderboard:** 5-10s → <500ms (10-20x faster)
- **Profile:** 3-5s → <200ms (15-25x faster)
- **Database queries:** 3000+ → <10 (300x fewer queries)

### Code Quality
- **bot.py:** 13K lines → ~3K lines + 20 modules
- **Test coverage:** ~50% → ~90%
- **Maintainability:** Hard → Easy

### Reliability
- **Data consistency:** ~80% → 100%
- **Error handling:** Inconsistent → Standardized
- **Monitoring:** None → Comprehensive

---

## 🚦 GO/NO-GO CRITERIA

### ✅ Go ahead if:
- [ ] v0.37.15 is stable and deployed
- [ ] All databases are backed up
- [ ] Team is ready for refactoring
- [ ] Tests are written in parallel

### ❌ Hold if:
- [ ] v0.37.15 has critical bugs
- [ ] Production is unstable
- [ ] Team capacity is low (<50%)

---

## 👥 TEAM REQUIREMENTS

**Skill levels needed:**
- 1x Senior Python Developer (refactoring, architecture)
- 1x Mid-level Python Developer (testing, optimization)
- 1x DevOps Engineer (deployment, monitoring setup)

**Time commitment:**
- Sprint 1: 60-80 hours
- Sprint 2: 50-60 hours
- Sprint 3: 60-80 hours
- **Total: ~200-220 hours (~5 weeks for 1 senior dev)**

---

## 📞 NEXT STEPS

1. **Approve this plan** (Today)
2. **Create milestone in GitHub** (Today)
3. **Assign tasks** (Tomorrow)
4. **Start Sprint 1** (Next Monday)
5. **Weekly sync meetings** (Every Friday)

---

**Created:** 25 Dec 2025
**Status:** Ready for approval
**Confidence Level:** High (95%) based on code audit
