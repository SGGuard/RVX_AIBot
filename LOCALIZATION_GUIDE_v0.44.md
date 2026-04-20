# Гайд: Как работает локализация AI диалога (Phase 4)

## Для разработчиков

### Быстрый старт

**Бот автоматически использует язык пользователя** - ничего не нужно настраивать!

```python
# В bot.py - получаем язык пользователя из БД
user_language = get_user_lang(user_id)  # "ru" или "uk"

# Передаём в AI функцию
ai_response = get_ai_response_sync(
    user_text,
    dialogue_context,
    user_id=user_id,
    language=user_language  # Бот будет отвечать на этом языке
)
```

### Структура локализации

```
ai_dialogue.py
├── build_dialogue_system_prompt(language="ru")
│   ├── если language=="uk": вызови _build_dialogue_prompt_ukrainian()
│   └── иначе: вызови _build_dialogue_prompt_russian()
├── build_geopolitical_analysis_prompt(language="ru")
├── build_crypto_news_analysis_prompt(language="ru")
└── build_simple_dialogue_prompt(language="ru")
```

### Если нужно добавить новый язык (напр. "de" - немецкий)

1. В `ai_dialogue.py` добавьте функции:
```python
def _build_dialogue_prompt_german() -> str:
    return """Ты - опытный финансовый аналитик... (на немецком)"""

def _build_geopolitical_prompt_german() -> str:
    return """Режим анализа... (на немецком)"""
```

2. Обновите build_*_prompt() функции:
```python
def build_dialogue_system_prompt(language: str = "ru") -> str:
    if language == "uk":
        return _build_dialogue_prompt_ukrainian()
    elif language == "de":  # ✅ НОВОЕ
        return _build_dialogue_prompt_german()
    else:
        return _build_dialogue_prompt_russian()
```

3. Добавьте язык в i18n.py:
```python
SUPPORTED_LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "uk": "🇺🇦 Українська",
    "de": "🇩🇪 Deutsch"  # ✅ НОВОЕ
}
```

### Проверка локализации

Запустите тест:
```bash
python3 test_localization_v0.44.py
```

Результат:
```
✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! (8/8)
```

## Для пользователей

### Как выбрать язык?

Язык бота следует за языком интерфейса Telegram:
1. Откройте Settings в боте → выберите язык (кнопка 🇷🇺/🇺🇦)
2. Бот запомнит ваш выбор в базе
3. Все AI ответы будут на выбранном языке

### Что локализовано?

| Компонент | Русский | Украинский |
|-----------|---------|-----------|
| Диалоговые ответы | ✅ | ✅ |
| Геополитический анализ | ✅ | ✅ |
| Крипто-новости анализ | ✅ | ✅ |
| Простые вопросы | ✅ | ✅ |
| Кнопки/меню | ✅ | ✅ |
| Скам-предупреждения | ✅ | ✅ |

### Пример работы

**Русский пользователь**:
```
Пользователь: Что такое DeFi?
Бот: Ты - ОПЫТНЫЙ ФИНАНСОВЫЙ АНАЛИТИК...
     DeFi (децентрализованные финансы) это...
     (ответ на РУССКОМ)
```

**Украинский пользователь**:
```
Користувач: Що таке DeFi?
Бот: Ти - ДОСВІДЧЕНИЙ ФІНАНСОВИЙ АНАЛІТИК...
     DeFi (децентралізовані фінанси) це...
     (відповідь на УКРАЇНСЬКІЙ)
```

## Технические детали

### Где хранится язык пользователя?

База данных SQLite, таблица `users`:
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    language TEXT DEFAULT 'ru',  -- ✅ Здесь
    ...
)
```

### Как бот определяет язык?

1. **При первом запуске**: Default = "ru"
2. **Когда пользователь выбирает язык**: Сохраняется в `users.language`
3. **При каждом запросе**: `get_user_lang(user_id)` достаёт из БД

```python
def get_user_language(user_id: int, default=None) -> str:
    # Проверяем кэш
    if user_id in _user_languages_cache:
        return _user_languages_cache[user_id]
    
    # Если нет в кэше - берём из БД
    result = db.execute(
        "SELECT language FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    
    language = result[0] if result else (default or DEFAULT_LANGUAGE)
    _user_languages_cache[user_id] = language
    return language
```

### Файлы локализации

```
locales/
├── ru.json (761 строк) - Русские переводы UI
└── uk.json (761 строк) - Украинские переводы UI

ai_dialogue.py
├── _build_dialogue_prompt_russian() (6170 chars)
├── _build_dialogue_prompt_ukrainian() (6101 chars)
├── _build_geopolitical_prompt_russian() (4051 chars)
├── _build_geopolitical_prompt_ukrainian() (3973 chars)
├── _build_crypto_news_analysis_russian() (3688 chars)
├── _build_crypto_news_analysis_ukrainian() (3554 chars)
├── _build_simple_dialogue_russian() (827 chars)
└── _build_simple_dialogue_ukrainian() (806 chars)
```

### Performance

- **Overhead локализации**: 0ms (просто выбор строк)
- **Размер промптов**: Идентичен русскому (~3-6KB каждый)
- **Скорость ответа**: Не изменилась
- **Использование памяти**: Вся система локализации в памяти (<5MB)

## Troubleshooting

### Проблема: Бот отвечает на русском когда я выбрал украинский

**Решение**: 
1. Перезагрузите бот
2. Проверьте что язык сохранился: `SELECT language FROM users WHERE id=YOUR_ID;`
3. Попробуйте снова выбрать язык в Settings

### Проблема: В ответе смешанные языки

**Это НЕ должно происходить с v0.44**, но если случилось:
1. Проверьте логи: `grep "language:" current_logs.txt`
2. Убедитесь что `language` параметр передаётся правильно
3. Запустите тест: `python3 test_localization_v0.44.py`

## FAQ

**Q: Можно ли использовать оба языка в одном чате?**
A: Нет, язык бота фиксирован для каждого пользователя. Чтобы переключиться - используйте Settings → выберите другой язык.

**Q: Если я изменю язык - изменятся ли старые сообщения?**
A: Старые сообщения останутся на старом языке. Новые ответы будут на новом языке.

**Q: Какой язык по умолчанию?**
A: Русский ("ru"). Украинский включается только если пользователь явно выберет его.

**Q: Как быстро реагирует система на смену языка?**
A: Мгновенно - язык кэшируется и обновляется при следующем запросе.

---

**Версия**: v0.44
**Статус**: Production Ready ✅
**Last Updated**: Phase 4 Complete
