# 🌍 СИСТЕМА ЛОКАЛИЗАЦИИ RVX BOT - БЫСТРЫЙ СПРАВОЧНИК

**TL;DR версия: Как добавить перевод в 30 секунд**

---

## ⚡ САМЫЙ БЫСТРЫЙ СТАРТ

### Ты написал:
```python
await update.message.reply_text("Добро пожаловать!")
```

### Измени на:
```python
user_id = update.effective_user.id
text = await get_text("start.welcome", user_id)
await update.message.reply_text(text)
```

### Готово! ✅

Не забудь импортировать:
```python
from i18n import get_text
```

---

## 3️⃣ ШАГА К ЛОКАЛИЗАЦИИ

### Шаг 1: Импортируй
```python
from i18n import get_text, set_user_language, get_user_language
```

### Шаг 2: Замени строки
```python
# ❌ Было
await update.message.reply_text("❌ Ошибка!")

# ✅ Теперь
text = await get_text("error.generic", user.id)
await update.message.reply_text(text)
```

### Шаг 3: Добавь ключ в JSON (если новый)
```json
{
  "error.generic": "❌ Ошибка!"
}
```

---

## 🎯 ОСНОВНЫЕ ФУНКЦИИ

| Функция | Пример | Результат |
|---------|--------|-----------|
| `get_text(key, user_id)` | `await get_text("menu.ask", 123)` | Текст на языке пользователя |
| `set_user_language(uid, lang)` | `await set_user_language(123, "uk")` | Устанавливает язык |
| `get_user_language(uid)` | `get_user_language(123)` | Возвращает "ru" или "uk" |

---

## 📝 ШАБЛОН КОДА

### Простое сообщение
```python
async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Получи перевод
    msg = await get_text("menu.ask_button", user_id)
    
    # Отправь
    await update.message.reply_text(msg)
```

### С кнопками
```python
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Переводы для кнопок
    btn1 = await get_text("menu.ask_button", user_id)
    btn2 = await get_text("menu.teach_button", user_id)
    
    keyboard = [[
        InlineKeyboardButton(btn1, callback_data="ask"),
        InlineKeyboardButton(btn2, callback_data="teach")
    ]]
    
    await update.message.reply_text("Выбери:", reply_markup=InlineKeyboardMarkup(keyboard))
```

### С ошибкой
```python
async def do_something(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = some_operation()
    except Exception as e:
        user_id = update.effective_user.id
        error_msg = await get_text("error.generic", user_id)
        await update.message.reply_text(f"{error_msg}\n\n{str(e)}")
```

---

## 📊 ГДЕ НАХОДЯТСЯ ПЕРЕВОДЫ

```
locales/
├── ru.json      ← Русские переводы (760 ключей)
└── uk.json      ← Украинские переводы (760 ключей)

i18n.py         ← Главный модуль локализации

bot.py          ← Использует локализацию везде
```

---

## 🔍 ПОИСК СУЩЕСТВУЮЩЕГО КЛЮЧА

### Хочешь узнать как сказать "Назад"?

**Вариант 1: Поиск в JSON**
```bash
grep -i "назад\|back\|назові\|назад" locales/ru.json | head -5
```

**Вариант 2: Посмотри файл**
```json
{
  "button.back": "⬅️ Назад",
  "menu.back_button": "⬅️ Вернуться в меню"
}
```

---

## ➕ ДОБАВИТЬ НОВЫЙ КЛЮЧ

### Если ключа нет в JSON:

**1. Добавь в `locales/ru.json`:**
```json
{
  "my.custom.key": "Мой текст на русском",
  ...
}
```

**2. Добавь в `locales/uk.json`:**
```json
{
  "my.custom.key": "Мій текст на українському",
  ...
}
```

**3. Используй в коде:**
```python
text = await get_text("my.custom.key", user_id)
```

**Готово!** Система автоматически найдет ключ. ✅

---

## 🧪 БЫСТРЫЙ ТЕСТ

### Проверить что все работает:

```bash
python3 << 'EOF'
import json
import asyncio
from i18n import get_text

# Проверка 1: JSON валиден
print("Проверка 1: JSON файлы...")
json.load(open('locales/ru.json'))
json.load(open('locales/uk.json'))
print("✅ JSON файлы валидны")

# Проверка 2: Модуль работает
print("Проверка 2: Модуль i18n...")
async def test():
    ru = await get_text("menu.ask_button", language="ru")
    uk = await get_text("menu.ask_button", language="uk")
    print(f"🇷🇺 Русский: {ru}")
    print(f"🇺🇦 Украинский: {uk}")
    print("✅ Модуль работает")

asyncio.run(test())
EOF
```

---

## ⚠️ ЧАСТЫЕ ОШИБКИ

### ❌ Забыл `await`
```python
# Неправильно
text = get_text("menu.ask", user_id)  # ❌ Ошибка!

# Правильно
text = await get_text("menu.ask", user_id)  # ✅
```

### ❌ Неправильный ключ
```python
# Если ключа нет, вернет: "[MISSING: my.key]"
text = await get_text("my.wrong.key", user_id)
print(text)  # Выведет: [MISSING: my.wrong.key]
```

**Решение:** Проверь орфографию ключа в JSON

### ❌ Нет user_id
```python
# Неправильно
text = await get_text("menu.ask")  # ❌ Ошибка!

# Правильно (вариант 1: с user_id)
text = await get_text("menu.ask", user_id=123)

# Правильно (вариант 2: с language)
text = await get_text("menu.ask", language="ru")
```

---

## 💡 ПОЛЕЗНЫЕ СОВЕТЫ

### Совет 1: Переиспользуй переменные
```python
# Если текст используется несколько раз, сохрани
greeting = await get_text("start.welcome", user_id)
await update.message.reply_text(greeting)
# и потом еще раз
await context.bot.send_message(chat_id=123, text=greeting)
```

### Совет 2: Получай все переводы для сложных сообщений
```python
title = await get_text("settings.menu_title", user_id)
lang_select = await get_text("settings.language_select", user_id)
message = f"<b>{title}</b>\n\n{lang_select}"
await update.message.reply_text(message, parse_mode="HTML")
```

### Совет 3: Проверь язык пользователя
```python
from i18n import get_user_language

lang = get_user_language(user_id=123)
if lang == "uk":
    print("Пользователь на украинском")
elif lang == "ru":
    print("Пользователь на русском")
```

---

## 🎯 СПИСОК ПОПУЛЯРНЫХ КЛЮЧЕЙ

```
menu.ask_button              → 💬 Задать вопрос
menu.teach_button            → 🎓 Обучение
menu.back_button             → ⬅️ Вернуться
button.yes                   → ✅ Да
button.no                    → ❌ Нет
error.generic                → ❌ Ошибка
success.saved                → ✅ Сохранено
settings.language_select     → 🌐 Язык
```

**Полный список всех 760 ключей см. в `locales/ru.json`**

---

## 🚀 БЫСТРЫЙ ДЕПЛОЙ

```bash
# 1. Запусти тесты
python3 -m pytest tests/ -v

# 2. Проверь синтаксис
python3 -m py_compile bot.py i18n.py

# 3. Запусти бота
python3 bot.py
```

---

## 📞 ЕСЛИ ЧТО-ТО НЕ РАБОТАЕТ

### Проблема: "Бот не отвечает"
```bash
# 1. Проверь что файлы есть
ls -la locales/
# 2. Проверь JSON
python3 -c "import json; json.load(open('locales/ru.json')); print('✅')"
# 3. Проверь импорт
python3 -c "from i18n import get_text; print('✅')"
```

### Проблема: "Текст не переводится"
```bash
# Проверь что ключ существует
grep "my.key" locales/ru.json
grep "my.key" locales/uk.json
# Если не найден - добавь в оба файла!
```

### Проблема: "Синтаксис ошибка"
```bash
python3 -m py_compile bot.py
python3 -m py_compile i18n.py
```

---

## 📚 ПОЛНАЯ ДОКУМЕНТАЦИЯ

Для большей информации смотри:

- **LOCALIZATION_FINAL_COMPLETE.md** - Полное описание
- **DEVELOPER_LOCALIZATION_GUIDE.md** - Подробное руководство
- **i18n.py** - Исходный код
- **CHECKLIST_COMPLETION.md** - Чек-лист завершения

---

## ✨ ЗАКЛЮЧЕНИЕ

**Используй локализацию везде где есть строки!**

```python
# ❌ Не пиши так (никогда!)
await update.message.reply_text("Привет!")

# ✅ Пиши так (всегда!)
text = await get_text("start.welcome", user_id)
await update.message.reply_text(text)
```

**Как быстро?**
- Первый раз: 10-15 минут разобраться
- В следующие разы: 30 секунд добавить строку
- Результат: Боト поддерживает любой язык! 🌍

---

**Happy coding!** 🚀
