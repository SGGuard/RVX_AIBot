# 🎯 Ollama Integration v1.0

## Обзор

Локальная LLM **Ollama** теперь интегрирована в проект RVX как **ПРИОРИТЕТ 1** провайдер ИИ!

✅ **Работает локально БЕЗ интернета**
✅ **Быстрее всего облачных сервисов** (после прогрева модели)
✅ **Полностью бесплатно** — нет API квот, лимитов или платежей
✅ **Модель qwen2.5** — отличная для кодинга и анализа

---

## 📦 Что было добавлено

### 1. **ollama_client.py** (новый модуль)
Полнофункциональный Python клиент для работы с локальной Ollama:
- Асинхронный API для генерации текста
- Встроенное кеширование результатов
- Автоматические повторы при ошибках
- Специализированные методы:
  - `analyze_code()` — анализ кода
  - `generate_docstring()` — генерация документации
  - `write_tests()` — генерация юнит-тестов

```python
from ollama_client import initialize_ollama, generate_with_ollama

# Инициализация
await initialize_ollama()

# Использование
response = await generate_with_ollama(
    prompt="Объясни Redis",
    system_prompt="Ты эксперт DevOps",
    temperature=0.3,
    max_tokens=1500
)
```

### 2. **api_server.py** (обновлен)
- Импортирует и инициализирует Ollama клиент при старте
- Добавлены переменные окружения для Ollama конфигурации
- Логирует статус Ollama при запуске

**Конфигурация:**
```python
OLLAMA_ENABLED = True
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5"
OLLAMA_TIMEOUT = 60
```

### 3. **ai_dialogue.py** (обновлен v0.25)
Добавлена Ollama как **первый провайдер** в цепочке fallback:

**Приоритет провайдеров:**
1. **Ollama** (локальная, без интернета) ⚡
2. Groq (облачная, быстрая) 
3. Mistral (облачная, fallback 1)
4. Gemini (облачная, fallback 2)
5. Fallback (шаблонный ответ)

```python
# get_ai_response_sync теперь пробует Ollama в первую очередь
response = get_ai_response_sync(
    user_message="Как использовать asyncio?",
    context_history=[],
    user_id=123456
)
# Попробует: Ollama → Groq → Mistral → Gemini
```

### 4. **.env** (обновлен)
Добавлены переменные для Ollama:
```bash
# Ollama Local LLM (приоритет 1 - ЛОКАЛЬНАЯ, без интернета!)
OLLAMA_ENABLED=true
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5"
OLLAMA_TIMEOUT=60
OLLAMA_TEMPERATURE=0.3
OLLAMA_MAX_TOKENS=1500
```

---

## 🚀 Как запустить

### 1. **Убедись что Ollama установлена и запущена**

```bash
# Проверка установки
ollama --version

# Запуск Ollama (если не запущена)
ollama serve

# Или запуск modели в отдельном терминале
ollama run qwen2.5
```

### 2. **Проверка доступности Ollama**

```bash
# Проверить что Ollama слушает на http://localhost:11434
curl http://localhost:11434/api/tags

# Или через Python
python3 << 'EOF'
import asyncio
from ollama_client import initialize_ollama

async def test():
    client = await initialize_ollama()
    print(f"Ollama доступна: {client.is_available}")

asyncio.run(test())
EOF
```

### 3. **Запуск API**

```bash
python3 api_server.py
```

### 4. **Проверка что Ollama используется**

При запуске API смотри логи:
```
✅ Ollama клиент инициализирован (модель: qwen2.5)
   URL: http://localhost:11434
   ⚡ Ollama будет использоваться в ПРИОРИТЕТЕ перед облачными сервисами!
```

---

## 💡 Примеры использования

### Анализ кода

```python
from ollama_client import get_ollama_client

client = get_ollama_client()
if client:
    analysis = await client.analyze_code(
        code="def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)",
        analysis_type="performance"
    )
    print(analysis)
```

### Генерация документации

```python
docstring = await client.generate_docstring(
    code="async def fetch_data(url): ...",
    language="python"
)
```

### Написание тестов

```python
tests = await client.write_tests(
    code="def add(a, b): return a + b",
    language="python"
)
```

---

## 📊 Метрики и мониторинг

Ollama запросы отслеживаются в метриках `ai_dialogue`:

```python
from ai_dialogue import dialogue_metrics, get_metrics_summary

# Смотри статистику Ollama
print(f"Ollama успешно: {dialogue_metrics['ollama_success']}")
print(f"Ollama ошибок: {dialogue_metrics['ollama_errors']}")
print(f"Ollama среднее время: {dialogue_metrics['ollama_total_time'] / max(dialogue_metrics['ollama_requests'], 1):.2f}s")
```

---

## ⚙️ Конфигурация и тюнинг

### Изменение модели

```bash
# В .env или при инициализации
OLLAMA_MODEL="mistral"  # или "neural-chat", "llama2" и т.д.

# Потом перезапусти:
ollama run mistral
```

### Изменение таймаута

```bash
OLLAMA_TIMEOUT=120  # Увеличь если модель медленнее
```

### Отключение Ollama (вернуться к облачным)

```bash
OLLAMA_ENABLED=false
```

### Температура и параметры генерации

```bash
OLLAMA_TEMPERATURE=0.1   # Более детерминированные ответы
OLLAMA_MAX_TOKENS=2000   # Макс размер ответа
```

---

## 🐛 Troubleshooting

### Ollama не отвечает

```bash
# 1. Проверь что Ollama запущена
ps aux | grep ollama

# 2. Проверь что модель загружена
curl http://localhost:11434/api/tags

# 3. Перезагрузи Ollama
ollama serve
```

### Модель не найдена

```bash
# Загрузи модель
ollama login  # если нужна авторизация
ollama pull qwen2.5
ollama pull mistral
```

### Медленные ответы

Это нормально при первом запросе (модель прогревается в памяти). Последующие запросы будут быстрее.

### Слишком большой вывод

Увеличь `MAX_OUTPUT_CHARS` или уменьши `OLLAMA_MAX_TOKENS`.

---

## 📈 Производительность

**Ожидаемые времена ответа:**
- **Первый запрос**: 5-15 сек (прогрев модели)
- **Последующие**: 2-5 сек (зависит от длины текста)
- После нескольких запросов модель кэшируется в памяти
- Полностью бесплатно в отличие от облачных сервисов!

---

## 🔄 Fallback цепочка

Если Ollama по какой-то причине не работает, система **автоматически** переключится на облачные провайдеры:

```
Пользователь: "Ответь на вопрос"
  ↓
  Пробуем Ollama (локальная)  
    ❌ Недоступна?
  ↓
  Пробуем Groq (облачная, быстрая)
    ❌ Error?
  ↓
  Пробуем Mistral (облачная, fallback)
    ❌ Error?
  ↓
  Пробуем Gemini (облачная, последний шанс)
    ❌ Error?
  ↓
  Fallback ответ (шаблон)
```

---

## 🎓 Для разработчиков

### Расширение OllamaClient

```python
class OllamaClient:
    async def my_custom_method(self, text: str):
        return await self.generate(
            prompt=text,
            system_prompt="Custom system prompt"
        )
```

### Добавление новых анализаторов

```python
async def analyze_security(self, code: str) -> str:
    prompt = f"""Analyze this code for security issues:
    
{code}

Provide:
1. Vulnerabilities
2. Risks
3. Fixes"""
    
    return await self.generate(prompt, system_prompt="Security expert")
```

---

## 📚 Дополнительные ресурсы

- [Ollama GitHub](https://github.com/ollama/ollama)
- [Доступные модели](https://ollama.ai/library)
- [Документация Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Qwen2.5 документация](https://github.com/QwenLM/Qwen2.5)

---

## 📝 История изменений

### v1.0 (20 марта 2026)
- ✅ Создан модуль `ollama_client.py`
- ✅ Интегрирована в `api_server.py`
- ✅ Добавлена в цепочку провайдеров `ai_dialogue.py`
- ✅ Добавлены переменные окружения в `.env`
- ✅ Добавлены метрики и мониторинг
- ✅ Протестирована интеграция

---

## 🎯 Следующие шаги

1. ✅ Интеграция завершена
2. 🔄 Регулярно проверяй логи Ollama
3. 📊 Мониторь метрики в `dialogue_metrics`
4. 🚀 Рассмотри использование других моделей (mistral, neural-chat)
5. 💾 Настрой кеширование под свои нужды

---

**Обновлено:** 20 марта 2026 г.
**Версия:** 1.0
**Статус:** ✅ Готово к использованию
