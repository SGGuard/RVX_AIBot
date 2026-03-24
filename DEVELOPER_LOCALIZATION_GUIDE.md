# 🛠️ РУКОВОДСТВО РАЗРАБОТЧИКА - ИСПОЛЬЗОВАНИЕ ЛОКАЛИЗАЦИИ

**Для разработчиков: как использовать систему многоязычной поддержки в RVX Bot**

---

## 📌 БЫСТРЫЙ СТАРТ

### Шаг 1: Импортируй модуль локализации

```python
from i18n import get_text, set_user_language, get_user_language
```

### Шаг 2: Получите текст на языке пользователя

```python
# В асинхронном обработчике
async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Получить текст - автоматически на языке пользователя
    greeting = await get_text("start.welcome", user_id)
    await update.message.reply_text(greeting)
```

### Шаг 3: Вот и всё!

Система автоматически выберет правильный язык.

---

## 🎯 ОСНОВНЫЕ ФУНКЦИИ

### 1️⃣ Получить перевод - `await get_text(key, user_id)`

```python
# Способ 1: Получить текст на языке пользователя
text = await get_text("menu.ask_button", user_id=123)

# Способ 2: Если не знаешь user_id, укажи язык явно
text = await get_text("menu.ask_button", language="ru")

# Способ 3: С параметрами подстановки
text = await get_text("limits.daily_questions", user_id, 
                     used=5, limit=10)
# Результат: "Вопросов: 5/10" (если в ключе есть {used}/{limit})
```

### 2️⃣ Установить язык - `await set_user_language(user_id, language)`

```python
# Установить языкдля пользователя
await set_user_language(user_id=123, language="uk")

# Теперь все get_text() для этого пользователя вернут украинский
```

### 3️⃣ Получить язык - `get_user_language(user_id)`

```python
# Узнать какой язык выбрал пользователь
lang = get_user_language(user_id=123)
print(lang)  # Выведет: "ru" или "uk"
```

---

## 📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ

### Пример 1: Простое сообщение

**Старый способ (без локализации):**
```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Добро пожаловать!")
```

**Новый способ (с локализацией):**
```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    greeting = await get_text("start.welcome", user_id)
    await update.message.reply_text(greeting)
```

### Пример 2: Кнопки меню

**Старый способ:**
```python
keyboard = [
    [InlineKeyboardButton("💬 Задать вопрос", callback_data="ask_ai")],
    [InlineKeyboardButton("🎓 Обучение", callback_data="teach")],
]
```

**Новый способ:**
```python
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    ask_btn = await get_text("menu.ask_button", user_id)
    teach_btn = await get_text("menu.teach_button", user_id)
    
    keyboard = [
        [InlineKeyboardButton(ask_btn, callback_data="ask_ai")],
        [InlineKeyboardButton(teach_btn, callback_data="teach")],
    ]
```

### Пример 3: Обработка ошибок

**Старый способ:**
```python
try:
    result = some_operation()
except Exception as e:
    await update.message.reply_text(f"❌ Ошибка: {str(e)}")
```

**Новый способ:**
```python
try:
    result = some_operation()
except Exception as e:
    user_id = update.effective_user.id
    error_msg = await get_text("error.generic_error", user_id)
    await update.message.reply_text(f"{error_msg} {str(e)}")
```

### Пример 4: Выбор языка

```python
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if query.data == "lang_ru":
        await set_user_language(user_id, "ru")
        msg = await get_text("language.selected_ru", user_id)
    elif query.data == "lang_uk":
        await set_user_language(user_id, "uk")
        msg = await get_text("language.selected_uk", user_id)
    
    await query.edit_message_text(msg)
```

### Пример 5: С форматированием текста

**Если ключ содержит параметры, передай их:**

```python
# В ru.json: "quiz.score": "Ваш результат: {correct}/{total}"
text = await get_text("quiz.score", user_id, correct=8, total=10)
# Результат: "Ваш результат: 8/10"
```

---

## 🔍 СПИСОК ЧАСТО ИСПОЛЬЗУЕМЫХ КЛЮЧЕЙ

### Главное меню
```
menu.ask_button              - Кнопка "Задать вопрос"
menu.teach_button            - Кнопка "Обучение"
menu.profile_button          - Кнопка "Профиль"
menu.courses_button          - Кнопка "Курсы"
menu.settings_button         - Кнопка "Настройки"
menu.help_button             - Кнопка "Помощь"
```

### Кнопки навигации
```
button.back                  - "⬅️ Назад"
button.menu                  - "🏠 Меню"
button.next                  - "➡️ Далее"
button.previous              - "⬅️ Предыдущее"
button.yes                   - "✅ Да"
button.no                    - "❌ Нет"
```

### Ошибки
```
error.generic_error          - Общая ошибка
error.network_error          - Ошибка сети
error.timeout_error          - Timeout
error.invalid_input          - Неверный ввод
error.not_authorized         - Не авторизован
```

### Сообщения об успехе
```
success.operation_complete   - Операция выполнена
success.saved                - Сохранено
success.deleted              - Удалено
```

### Языкои локализация
```
language.choose              - "Выберите язык"
language.selected_ru         - "Язык установлен: Русский"
language.selected_uk         - "Язык установлен: Украинский"
settings.language_select     - "🌐 Выберите язык:"
```

**Полный список всех 760 ключей см. в `locales/ru.json` и `locales/uk.json`**

---

## ✅ ЧЕК-ЛИСТ ДЛЯ НОВЫХ СТРОК КОДА

Перед коммитом убедись что:

- [ ] Вместо хардкода "Добро пожаловать!" использован `await get_text("start.welcome", user_id)`
- [ ] Все кнопки берут текст из `get_text()`
- [ ] Все сообщения об ошибках используют `error.*` ключи
- [ ] Обработчики асинхронные (используют `async`/`await`)
- [ ] JSON ключи существуют в обоих файлах (`ru.json` и `uk.json`)

---

## 🧪 ТЕСТИРОВАНИЕ

### Тест 1: Проверить что ключ существует

```python
from i18n import get_text

async def test_translation():
    # Попробуй получить текст
    text = await get_text("menu.ask_button", language="ru")
    assert text != "[MISSING: menu.ask_button]", "Ключ не найден!"
    print(f"✅ Ключ найден: {text}")

# Запусти
import asyncio
asyncio.run(test_translation())
```

### Тест 2: Проверить оба языка

```python
async def test_both_languages():
    ru_text = await get_text("menu.ask_button", language="ru")
    uk_text = await get_text("menu.ask_button", language="uk")
    
    print(f"🇷🇺 Русский: {ru_text}")
    print(f"🇺🇦 Украинский: {uk_text}")
    
    assert ru_text != uk_text, "Переводы одинаковые!"
    print("✅ Переводы разные!")

asyncio.run(test_both_languages())
```

### Тест 3: Проверить язык пользователя

```python
async def test_user_language():
    user_id = 123
    
    # Установи украинский
    await set_user_language(user_id, "uk")
    lang = get_user_language(user_id)
    assert lang == "uk", f"Язык не установлен! Получено: {lang}"
    
    # Получи текст
    text = await get_text("menu.ask_button", user_id)
    print(f"Текст для пользователя на {lang}: {text}")
    print("✅ Тест пройден!")

asyncio.run(test_user_language())
```

---

## 🐛 РЕШЕНИЕ ПРОБЛЕМ

### Проблема: "Чтобы получить скорлу [MISSING: menu.ask_button]"

**Решение:** Ключ не существует!
1. Проверь орфографию ключа (`menu.ask_button` ✓ vs `menu.Ask_button` ✗)
2. Проверь наличие ключа в `locales/ru.json` и `locales/uk.json`
3. Если ключа нет - добавь в оба файла:
   ```json
   {
     "menu.ask_button": "💬 Задать вопрос"
   }
   ```

### Проблема: "TypeError: object NoneType can't be used in 'await' expression"

**Решение:** Ты забыл `await`
```python
# ❌ Неправильно
text = get_text("menu.ask_button", user_id)

# ✅ Правильно
text = await get_text("menu.ask_button", user_id)
```

### Проблема: "get_text() is not waiting for user ID"

**Решение:** Функция требует либо `user_id`, либо `language`:
```python
# ✅ С user_id
text = await get_text("menu.ask_button", user_id=123)

# ✅ С language
text = await get_text("menu.ask_button", language="ru")

# ❌ Без оного из них - ошибка
text = await get_text("menu.ask_button")
```

---

## 📚 ДОКУМЕНТАЦИЯ

**Дополнительно смотри:**
- `i18n.py` - исходный код модуля
- `locales/ru.json` - все русские переводы
- `locales/uk.json` - все украинские переводы
- `LOCALIZATION_FINAL_COMPLETE.md` - общее описание
- `bot.py` - примеры использования в коде

---

## 💡 СОВЕТЫ И ТРЮКИ

### Совет 1: Повторное использование текста

```python
# Если нужен один текст в разных местах - сохрани в переменную
greeting = await get_text("start.welcome", user_id)
await update.message.reply_text(greeting)
# ... потом еще раз
await update.message.edit_text(greeting)
```

### Совет 2: Условные сообщения

```python
# Если сообщение зависит от условия, получи оба варианта
success_msg = await get_text("success.operation_complete", user_id)
error_msg = await get_text("error.generic_error", user_id)

if operation_succeeded:
    await update.message.reply_text(success_msg)
else:
    await update.message.reply_text(error_msg)
```

### Совет 3: Логирование на языке пользователя

```python
# Хорош для уведомлений и логов
notification = await get_text("admin.user_joined", language="ru")
log(f"Уведомление админу: {notification}")
```

---

## 🚀 ПРОИЗВОДИТЕЛЬНОСТЬ

**Система кэширует переводы, поэтому безопасно вызывать `get_text()` часто:**

```python
# Это быстро - переводы кэшируются
for i in range(1000):
    text = await get_text("menu.ask_button", user_id)
    # ~1 мс, потому что читает из памяти
```

---

## ✨ ЗАКЛЮЧЕНИЕ

Система локализации автоматическая и простая в использовании:

1. ✅ Импортируй `get_text` и используй везде
2. ✅ Передай `user_id` или `language`
3. ✅ Остальное происходит само
4. ✅ Переводы кэшируются для скорости

**Больше не пиши хардкод строк - используй локализацию!** 🌍
