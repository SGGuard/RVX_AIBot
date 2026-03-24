# ✅ Ollama Integration Checklist

## Быстрый старт (5 минут)

### 1️⃣ Убедится что Ollama работает
```bash
# Проверка установки
ollama --version  # должно быть >= 0.18.0

# Проверка что модель загружена
ollama list | grep qwen2.5

# Если нет модели - загрузи её
ollama pull qwen2.5
```

### 2️⃣ Проверить что Ollama слушает на localhost:11434
```bash
# Один из способов:
curl -s http://localhost:11434/api/tags | head -20

# Если вывод с JSON - всё хорошо ✅
# Если ошибка - запусти Ollama:
ollama serve
```

### 3️⃣ Запустить API с Ollama
```bash
cd /home/sv4096/rvx_backend

# В первом терминале - запусти API
python3 api_server.py

# Ожидай строк в логах:
# ✅ Ollama клиент инициализирован
# ✅ Ollama доступна! Модель 'qwen2.5' загружена
```

### 4️⃣ Тест интеграции (в другом терминале)
```bash
cd /home/sv4096/rvx_backend

python3 << 'EOF'
import asyncio
from ollama_client import initialize_ollama, generate_with_ollama

async def test():
    client = await initialize_ollama()
    if client.is_available:
        print("✅ Ollama работает!")
        resp = await generate_with_ollama("Привет! Кто ты?")
        print(f"💬 {resp[:100]}...")

asyncio.run(test())
EOF
```

---

## ✨ Особенности (что работает)

| Функция | Статус | Примечание |
|---------|--------|-----------|
| Ollama как PRIMARY провайдер | ✅ | Приоритет 1 перед облачными |
| Fallback на Groq/Mistral/Gemini | ✅ | Если Ollama недоступна |
| Кеширование результатов | ✅ | 24 часа по умолчанию |
| Метрики и мониторинг | ✅ | В `dialogue_metrics` |
| Анализ кода | ✅ | `client.analyze_code(code)` |
| Генерация документации | ✅ | `client.generate_docstring(code)` |
| Написание тестов | ✅ | `client.write_tests(code)` |
| Работает БЕЗ интернета | ✅ | 🎯 Главное преимущество! |

---

## 🔧 Конфигурация (в .env)

```ini
# Локальная Ollama (ПРИОРИТЕТ 1)
OLLAMA_ENABLED=true
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5"
OLLAMA_TIMEOUT=60
OLLAMA_TEMPERATURE=0.3
OLLAMA_MAX_TOKENS=1500

# Облачные провайдеры (fallback)
GROQ_API_KEY="..."
GROQ_MODEL="llama-3.3-70b-versatile"

MISTRAL_API_KEY="..."
MISTRAL_MODEL="mistral-large"

GEMINI_API_KEY="..."
GEMINI_MODEL="models/gemini-2.5-flash"
```

---

## 🧪 Примеры использования

### Пример 1: Анализ кода с Ollama
```python
from ollama_client import get_ollama_client

async def find_bugs():
    client = get_ollama_client()
    code = """
    def partition(arr, low, high):
        pivot = arr[high]
        i = low - 1
        for j in range(low, high):
            if arr[j] < pivot:
                arr[i], arr[j] = arr[j], arr[i]
                i = i + 1
            return arr  # ❌ Bug: return in loop
        arr[i+1], arr[high] = arr[high], arr[i+1]
        return i + 1
    """
    
    analysis = await client.analyze_code(code, "security")
    print(analysis)
```

### Пример 2: Диалог через API
```bash
# Запрос к API
curl -X POST http://localhost:8000/explain_news \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "text_content": "Bitcoin достиг $100000 благодаря спросу на ETF"
  }'

# Ответ будет от Ollama! (без интернета)
```

### Пример 3: Прямой вызов Ollama
```python
import asyncio
from ollama_client import generate_with_ollama

async def ask_expert():
    response = await generate_with_ollama(
        prompt="Чем async отличается от sync?",
        system_prompt="Ты эксперт по Python async",
        temperature=0.2,
        max_tokens=1000
    )
    print(response)

asyncio.run(ask_expert())
```

---

## 📊 Мониторинг Ollama

### Проверить статистику
```python
from ai_dialogue import dialogue_metrics

print(f"Ollama запросов: {dialogue_metrics['ollama_requests']}")
print(f"Ollama успешно: {dialogue_metrics['ollama_success']}")
print(f"Ollama ошибок: {dialogue_metrics['ollama_errors']}")
```

### Проверить кеш Ollama
```python
from ollama_client import get_ollama_client

client = get_ollama_client()
stats = client.get_cache_stats()
print(f"Кеш размер: {stats['cache_size']}")
print(f"Модель: {stats['model']}")
print(f"Доступна: {stats['is_available']}")
```

---

## 🚨 Если что-то не работает

### 1. Ollama не запущена
```bash
# Проверь процесс
ps aux | grep ollama

# Если нет - запусти
ollama serve
```

### 2. Модель не загружена
```bash
# Загрузи модель
ollama pull qwen2.5
ollama list
```

### 3. Timeout при генерации
```bash
# Увеличь timeout в .env
OLLAMA_TIMEOUT=120
```

### 4. Смотри логи API
```bash
# При запуске API смотри строки с "Ollama"
python3 api_server.py 2>&1 | grep -i ollama
```

---

## 💡 Pro Tips

1. **Первый запрос медленнее** — модель прогревается в памяти (5-10 сек)
2. **Последующие быстрее** — модель кэшируется в памяти (2-5 сек)
3. **БЕЗ интернета** — Ollama работает полностью локально 🎯
4. **Бесплатно зовсім** — нет никаких API квот или платежей
5. **Легко переключать** — можно менять модель в .env

---

## 🎓 Что дальше?

1. ✅ Ollama интегрирована
2. 🔄 Запусти API и Бота
3. 📝 Заметь как быстро работает локальная LLM
4. 🚀 Рассмотри использование других моделей:
   - `mistral` - ещё быстрее (7B параметров)
   - `neural-chat` - специализирована для диалогов
   - `llama2` - более мощная (70B параметров, медленнее)

---

**Versio**: 1.0  
**Дата**: 20 марта 2026 г.  
**Статус**: ✅ Готово к использованию
