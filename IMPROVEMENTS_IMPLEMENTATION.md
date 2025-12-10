# 🔧 КОНКРЕТНЫЕ УЛУЧШЕНИЯ И FIXES

**Статус**: Ready to implement  
**Приоритет**: HIGH → MEDIUM → LOW  
**Время реализации**: 2-3 дня

---

## 🔴 HIGH PRIORITY

### 1. Fix: AI Hallucination Prevention

**Файл**: `ai_dialogue.py`  
**Время**: 2 часа

**Проблема**: Бот может выдумать информацию про финансирование, команду, продукты

**Решение**:

```python
# Добавить в ai_dialogue.py

SENSITIVE_TOPICS = {
    'финансирование': ['инвестор', 'funding', 'привлек', 'капитал', 'сумма', 'раунд'],
    'команда': ['основатель', 'CEO', 'COO', 'developer', 'member', 'создатель'],
    'продукты': ['продукт', 'услуга', 'сервис', 'feature', 'функция'],
    'владельцы': ['владелец', 'собственник', 'founder'],
}

def detect_sensitive_topic(user_question: str) -> Optional[str]:
    """Определяет если вопрос касается чувствительной информации"""
    question_lower = user_question.lower()
    for topic, keywords in SENSITIVE_TOPICS.items():
        if any(kw in question_lower for kw in keywords):
            return topic
    return None

def get_deflection_response(topic: str) -> str:
    """Честный ответ вместо выдумывания"""
    responses = {
        'финансирование': (
            "📊 Я ИИ ассистент для анализа новостей, но я не располагаю актуальной информацией "
            "о финансировании конкретных проектов.\n\n"
            "🔍 Где найти: CoinGecko, Twitter официальный аккаунт, Crunchbase, или whitepaper"
        ),
        'команда': (
            "👥 Информация о команде обычно устаревает быстро.\n\n"
            "🔍 Где найти: официальный сайт проекта, LinkedIn, GitHub contributors"
        ),
        'продукты': (
            "🛠️ Я диалоговый помощник для анализа крипто-новостей.\n\n"
            "Чтобы узнать о продуктах и сервисах - посети официальный веб-сайт."
        ),
        'владельцы': (
            "👤 Информация о владельцах часто является приватной.\n\n"
            "Проверь документацию и официальные источники проекта."
        ),
    }
    return responses.get(topic, "Мне не известна эта информация. Посмотри официальные источники.")

# В build_simple_dialogue_prompt() добавить:
def build_simple_dialogue_prompt(question: str, context_info: str = "") -> str:
    return f"""
СИСТЕМА: Ты помощник для анализа крипто-новостей. ОЧЕНЬ ВАЖНО:

⚠️ КРИТИЧЕСКИЕ ПРАВИЛА:
1. НЕ ВЫДУМЫВАЙ информацию про финансирование, инвесторов, команду
2. Если не знаешь - скажи "я не знаю"
3. Будь честен о своих ограничениях

📝 ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

✅ ОТВЕЧАЙ ПРАВДОЙ, не выдумкой!
"""
```

**Тестирование**:
```python
def test_no_hallucination():
    q = "Кто инвесторы проекта Solana?"
    topic = detect_sensitive_topic(q)
    assert topic == 'финансирование'
    response = get_deflection_response(topic)
    assert 'не располагаю' in response
    assert 'выдумка' not in response.lower()
```

---

### 2. Fix: Event Tracking для Analytics

**Файл**: `bot.py` + `api_server.py` + новая таблица в БД  
**Время**: 2-3 часа

**Текущее состояние**: Только логирование в файл, нет истории в БД

**Решение**:

```sql
-- Добавить таблицу в БД

CREATE TABLE IF NOT EXISTS bot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'message', 'command', 'button', 'error'
    event_name VARCHAR(100),           -- '/help', 'explain_news', 'feedback_positive'
    event_data TEXT,                   -- JSON с параметрами
    duration_ms INTEGER,               -- Время выполнения
    error_message TEXT,                -- Если была ошибка
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_user ON bot_events(user_id);
CREATE INDEX idx_events_type ON bot_events(event_type);
CREATE INDEX idx_events_created ON bot_events(created_at);
```

```python
# В bot.py добавить трекинг

async def track_event(
    user_id: int,
    event_type: str,
    event_name: str,
    duration_ms: int = 0,
    error: Optional[str] = None,
    data: Optional[dict] = None
):
    """Логирует событие в БД для аналитики"""
    try:
        conn = sqlite3.connect('rvx_bot.db')
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO bot_events 
               (user_id, event_type, event_name, duration_ms, error_message, event_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                event_type,
                event_name,
                duration_ms,
                error,
                json.dumps(data or {}),
                datetime.now()
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to track event: {e}")

# Использование в handlers:

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_time = time.time()
    
    try:
        # ... основная логика ...
        duration = int((time.time() - start_time) * 1000)
        await track_event(user_id, 'message', 'explain_news', duration)
    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        await track_event(
            user_id, 'message', 'explain_news',
            duration, str(e)
        )
        raise
```

**Dashboard** (в api_server.py):

```python
@app.get("/admin/metrics")
async def get_metrics():
    """Метрики за последние 24 часа"""
    conn = sqlite3.connect('rvx_bot.db')
    cursor = conn.cursor()
    
    # Active users
    active = cursor.execute(
        "SELECT COUNT(DISTINCT user_id) FROM bot_events "
        "WHERE created_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    # Events breakdown
    breakdown = cursor.execute("""
        SELECT event_type, COUNT(*) FROM bot_events
        WHERE created_at > datetime('now', '-1 day')
        GROUP BY event_type
    """).fetchall()
    
    # Errors
    errors = cursor.execute(
        "SELECT COUNT(*) FROM bot_events WHERE error_message IS NOT NULL "
        "AND created_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    # Avg response time
    avg_time = cursor.execute(
        "SELECT AVG(duration_ms) FROM bot_events "
        "WHERE created_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    return {
        'active_users_24h': active,
        'total_events_24h': sum(c for _, c in breakdown),
        'events_by_type': {t: c for t, c in breakdown},
        'errors_24h': errors,
        'avg_response_time_ms': round(avg_time or 0, 2),
    }
```

---

### 3. Fix: Add Unit Tests for Critical Functions

**Файл**: `tests/test_ai_honesty.py` (новый)  
**Время**: 2 часа

```python
# tests/test_ai_honesty.py

import pytest
from ai_dialogue import (
    detect_sensitive_topic,
    get_deflection_response,
    SENSITIVE_TOPICS
)

class TestAIHonesty:
    """Тесты что бот не выдумывает информацию"""
    
    def test_detect_financing_question(self):
        questions = [
            "Кто инвесторы Solana?",
            "Сколько денег привлекли?",
            "Какой размер funding раунда?",
        ]
        for q in questions:
            topic = detect_sensitive_topic(q)
            assert topic == 'финансирование', f"Failed for: {q}"
    
    def test_detect_team_question(self):
        questions = [
            "Кто основатель этого проекта?",
            "Какой CEO?",
            "Расскажи о разработчиках",
        ]
        for q in questions:
            topic = detect_sensitive_topic(q)
            assert topic == 'команда', f"Failed for: {q}"
    
    def test_deflection_contains_honesty(self):
        """Проверяем что deflection содержит честный ответ"""
        for topic in SENSITIVE_TOPICS.keys():
            response = get_deflection_response(topic)
            # Не должно быть выдумки
            assert 'выдумка' not in response.lower()
            # Должна быть рекомендация где искать
            assert any(word in response for word in ['веб', 'сайт', 'официа', 'Twitter', 'GitHub'])
    
    def test_no_fabricated_numbers(self):
        """Проверяем что в ответе нет выдуманных чисел"""
        response = get_deflection_response('финансирование')
        # Примеры выдумки - конкретные суммы в долларах
        assert not any(f'${i}M' for i in range(1, 100) if f'${i}M' in response)
    
    def test_unknown_topic_handled(self):
        """Неизвестная тема должна вернуть стандартный ответ"""
        response = get_deflection_response('unknown_topic')
        assert response  # Должен быть непустой ответ
        assert 'я не' in response.lower() or 'не' in response.lower()
```

---

## 🟡 MEDIUM PRIORITY

### 4. Optimization: Cache Warming

**Файл**: `ai_dialogue.py`  
**Время**: 1 час

**Проблема**: Первый запрос после restart медленнее (загрузка модели)

**Решение**:

```python
# При инициализации бота запустить cache warming

async def warm_up_cache():
    """Прогревает кэш перед тем как запустить бота"""
    test_questions = [
        "Что такое Bitcoin?",
        "Как работает blockchain?",
        "Что такое DeFi?",
    ]
    
    for question in test_questions:
        try:
            _ = await get_dialogue_response(question, user_id=0)  # user_id=0 это система
            logger.info(f"✅ Warmed up: {question}")
        except Exception as e:
            logger.warning(f"⚠️ Cache warm failed: {e}")

# При запуске:
if __name__ == '__main__':
    asyncio.run(warm_up_cache())
    application.run_polling()
```

---

### 5. Security: Input Validation Improvement

**Файл**: `constants.py` + `bot.py`  
**Время**: 1 час

```python
# В constants.py добавить максимальную валидацию

DANGEROUS_PATTERNS = [
    r'<script',           # XSS
    r'javascript:',       # XSS
    r'on\w+\s*=',        # Event handlers
    r'eval\(',           # Code injection
    r'__import__',       # Python injection
    r'subprocess',       # Shell injection
    r'os\.system',       # Shell injection
]

def validate_user_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> tuple[bool, str]:
    """
    Валидирует пользовательский ввод
    
    Returns:
        (is_valid, sanitized_text)
    """
    if len(text) > max_length:
        return False, f"Текст слишком длинный (макс {max_length})"
    
    text_lower = text.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text_lower):
            return False, "Обнаружен подозрительный паттерн"
    
    return True, text.strip()
```

---

### 6. Feature: Admin Alerts for Errors

**Файл**: `bot.py`  
**Время**: 1.5 часов

```python
# Отправлять алерты админу при критических ошибках

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

async def send_admin_alert(error_type: str, error_details: str):
    """Отправляет алерт админу при серьезной ошибке"""
    if not ADMIN_USER_ID or ADMIN_USER_ID == 0:
        return
    
    message = (
        f"🚨 **ALERT**: {error_type}\n\n"
        f"```\n{error_details[:500]}\n```\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    try:
        await application.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to send admin alert: {e}")

# Использование:
try:
    # ... risky operation ...
    pass
except Exception as e:
    await send_admin_alert("API Error", str(e))
    raise
```

---

## 🟢 LOW PRIORITY

### 7. Enhancement: Better Error Messages

**Файл**: `bot.py`  
**Время**: 1 час

Текущее:
```
❌ Ошибка обработки. Попробуй позже.
```

Улучшенное:
```
❌ Ошибка обработки запроса (код: ERR_001)

Возможные причины:
• API сервис недоступен
• Слишком много запросов
• Текст содержит недопустимые символы

💡 Решение:
1. Подожди 30 сек и попробуй снова
2. Используй /help для справки
3. Напиши /report если проблема повторяется
```

### 8. Enhancement: Performance Metrics in /stats

**Файл**: `bot.py`  
**Время**: 1 час

Добавить:
```
📊 Твоя статистика:
└─ 📈 Запросы: 42 анализа
└─ ⏱️ Среднее время: 3.2с
└─ 🎯 Успех: 100%
└─ 💾 Сохранено: 12 закладок
```

---

## 📊 SUMMARY TABLE

| # | Фича | Файл | Время | Приоритет | Статус |
|---|------|------|-------|-----------|--------|
| 1 | AI Honesty | ai_dialogue.py | 2h | 🔴 HIGH | TODO |
| 2 | Event Tracking | bot.py + api | 3h | 🔴 HIGH | TODO |
| 3 | Unit Tests | tests/ | 2h | 🔴 HIGH | TODO |
| 4 | Cache Warming | ai_dialogue.py | 1h | 🟡 MED | TODO |
| 5 | Input Validation | constants.py | 1h | 🟡 MED | TODO |
| 6 | Admin Alerts | bot.py | 1.5h | 🟡 MED | TODO |
| 7 | Better Errors | bot.py | 1h | 🟢 LOW | TODO |
| 8 | Performance Metrics | bot.py | 1h | 🟢 LOW | TODO |

**Итого**: ~12.5 часов работы

**ROI**: Огромный - стабильность, видимость, надежность

---

## 🚀 IMPLEMENTATION ORDER

**День 1** (8 часов):
- [ ] AI Honesty (2h)
- [ ] Event Tracking (3h)
- [ ] Input Validation (1h)
- [ ] Admin Alerts (1h)
- [ ] Cache Warming (1h)

**День 2** (4.5 часа):
- [ ] Unit Tests (2h)
- [ ] Better Error Messages (1h)
- [ ] Performance Metrics (1h)
- [ ] Testing & QA (0.5h)

**День 3**:
- [ ] Code Review & Deployment
- [ ] User Testing

---

**Версия**: v1.0  
**Дата**: 9 декабря 2025  
**Статус**: Ready to implement
