# 🚀 SPRINT 4 Phase 2 - ROADMAP (bot.py Refactoring)

**Статус**: 🔜 Next Phase  
**ETA**: 1-2 дня  
**Приоритет**: 🔴 ВЫСОКИЙ (bot.py ещё больше чем api_server!)

---

## 📊 Проблема с bot.py

```
bot.py: 11010 строк 😱

Содержит:
├── Хэндлеры команд (/start, /help и т.д.)
├── Хэндлеры сообщений
├── Хэндлеры кнопок
├── Обработка уроков
├── Обработка квестов
├── Работа с БД
├── Логирование
├── Аналитика
├── Уведомления
└── ... ещё 10 тысяч строк

= АБСОЛЮТНЫЙ НАРУШИТЕЛЬ SRP!
```

---

## 🎯 План Рефакторизации

### Структура ПОСЛЕ:

```
bot/
├── __init__.py                     # Package exports
├── core.py                         # Инициализация бота (~200 строк)
│
├── handlers/                       # Обработчики (SRP)
│   ├── __init__.py
│   ├── command_handler.py          # /start, /help, etc (~300 строк)
│   ├── message_handler.py          # Текстовые сообщения (~400 строк)
│   └── button_handler.py           # Callback queries (~300 строк)
│
├── services/                       # Бизнес-логика (SRP)
│   ├── __init__.py
│   ├── user_service.py             # Управление пользователем (~300 строк)
│   ├── lesson_service.py           # Логика уроков (~400 строк)
│   ├── quest_service.py            # Логика квестов (~350 строк)
│   ├── notification_service.py     # Уведомления (~200 строк)
│   └── api_service.py              # Вызовы к api_server (~150 строк)
│
└── schemas.py                      # Pydantic модели (~100 строк)
```

### Результат:

```
bot.py: 11010 строк → 8 файлов по 200-400 строк каждый

Средний размер файла: 300 строк (идеально!)
SRP: Каждый файл - одна ответственность
Тестируемость: Каждый сервис можно тестировать отдельно
Поддерживаемость: 20x лучше
```

---

## 📋 Пошаговый План

### Шаг 1: Создать структуру директорий

```bash
mkdir -p bot/handlers
mkdir -p bot/services
touch bot/__init__.py
touch bot/core.py
touch bot/handlers/__init__.py
touch bot/services/__init__.py
touch bot/schemas.py
```

### Шаг 2: Извлечь Schemas (Pydantic модели)

```python
# bot/schemas.py

from dataclasses import dataclass
from pydantic import BaseModel

class UserProfile(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    xp: int
    level: int

class LessonData(BaseModel):
    topic: str
    difficulty: str
    content: str

# ... остальные модели
```

### Шаг 3: Создать Service Layer

```python
# bot/services/user_service.py

class UserService:
    """Управляет профилем пользователя (SRP)"""
    
    def __init__(self, db_repo):
        self.repo = db_repo
    
    async def get_or_create_user(self, telegram_id: int) -> UserProfile:
        user = await self.repo.get_by_telegram_id(telegram_id)
        if not user:
            user = await self.repo.create(telegram_id=telegram_id)
        return user
    
    async def add_xp(self, user_id: int, xp: int) -> UserProfile:
        user = await self.repo.get_by_id(user_id)
        new_xp = user.xp + xp
        return await self.repo.update(user_id, xp=new_xp)
    
    async def get_level(self, xp: int) -> int:
        # Вычисление уровня по XP
        return xp // 1000 + 1
```

### Шаг 4: Создать Handlers

```python
# bot/handlers/command_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from bot.services import UserService

class CommandHandler:
    """Обработчик команд (SRP)"""
    
    def __init__(self, user_service: UserService):
        self.user_service = user_service
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка /start"""
        user = await self.user_service.get_or_create_user(update.effective_user.id)
        await update.message.reply_text(f"Привет, {user.first_name}! 👋")
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка /help"""
        help_text = "Это помощь..."
        await update.message.reply_text(help_text)
```

### Шаг 5: Инициализировать Бота

```python
# bot/core.py

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bot.handlers import CommandHandler, MessageHandler as MsgHandler
from bot.services import UserService

async def setup_bot() -> Application:
    """Инициализирует бота и регистрирует хэндлеры"""
    
    # Создаем Application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Инициализируем сервисы
    user_service = UserService(db_repo)
    command_handler = CommandHandler(user_service)
    
    # Регистрируем хэндлеры
    app.add_handler(CommandHandler("start", command_handler.handle_start))
    app.add_handler(CommandHandler("help", command_handler.handle_help))
    
    return app
```

### Шаг 6: Создать Entry Point

```python
# main.py (новый или bot/__init__.py)

from bot.core import setup_bot

async def main():
    app = await setup_bot()
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## 📦 Детальное описание каждого модуля

### 1. **core.py** (~200 строк)
```
Ответственность:
- Инициализация Application
- Регистрация всех хэндлеров
- Setup/teardown логика

Не должен содержать:
- Бизнес-логику
- Обработку сообщений (кроме регистрации)
- Работу с БД
```

### 2. **handlers/command_handler.py** (~300 строк)
```
Команды:
- /start     -> handle_start()
- /help      -> handle_help()
- /profile   -> handle_profile()
- /settings  -> handle_settings()

Ответственность:
- Обработка команд Telegram
- Делегирование сервисам
- Отправка ответов пользователю

Не должен содержать:
- Бизнес-логику (она в services)
- Работу с БД напрямую (через services)
```

### 3. **handlers/message_handler.py** (~400 строк)
```
Обработчик текстовых сообщений

Ответственность:
- Обработка сообщений от пользователя
- Детекция намерения (intent detection)
- Делегирование нужному сервису

Не должен содержать:
- Логику анализа текста (в services)
- Логику сохранения (в services)
```

### 4. **handlers/button_handler.py** (~300 строк)
```
Обработчик inline кнопок (callback_query)

Ответственность:
- Обработка нажатий на кнопки
- Обновление состояния
- Отправка результатов

Не должен содержать:
- Логику создания кнопок (в services/UI service)
- Работу с БД напрямую (через services)
```

### 5. **services/user_service.py** (~300 строк)
```
Управление профилем пользователя (SRP)

Методы:
- get_or_create_user(telegram_id)
- add_xp(user_id, xp)
- add_badge(user_id, badge)
- get_level(xp)
- update_profile(user_id, **fields)

Зависимости:
- DatabaseRepository
- (Использует validators для безопасности)

Не должен:
- Отправлять сообщения в Telegram
- Работать с API напрямую (через api_service)
```

### 6. **services/lesson_service.py** (~400 строк)
```
Логика уроков

Методы:
- start_lesson(user_id, topic)
- get_lesson_content(lesson_id)
- submit_answer(user_id, lesson_id, answer)
- complete_lesson(user_id, lesson_id)

Зависимости:
- LessonRepository
- UserService (для добавления XP)
- API Service (для вызова анализа)
```

### 7. **services/quest_service.py** (~350 строк)
```
Логика квестов

Методы:
- get_available_quests(user_id)
- start_quest(user_id, quest_id)
- progress_quest(user_id, quest_id)
- complete_quest(user_id, quest_id)

Зависимости:
- QuestRepository
- UserService
```

### 8. **services/api_service.py** (~150 строк)
```
Вызовы к api_server

Методы:
- analyze_news(text) -> AIResponse
- teach_lesson(topic, difficulty) -> LessonResponse
- health_check() -> HealthStatus

Зависимости:
- httpx.AsyncClient
- Конфиг (API_URL, AUTH_KEY)

Преимущество:
- Если поменяется API, меняем только этот файл!
```

### 9. **services/notification_service.py** (~200 строк)
```
Отправка уведомлений

Методы:
- notify_quest_complete(user_id)
- notify_level_up(user_id, new_level)
- notify_milestone(user_id, milestone)

Зависимости:
- Telegram Application
```

---

## 🧪 Тестирование Phase 2

### Unit Тесты:

```python
# tests/test_bot_services.py

class TestUserService:
    @pytest.mark.asyncio
    async def test_get_or_create_user(self, mock_db):
        service = UserService(mock_db)
        user = await service.get_or_create_user(12345)
        assert user.telegram_id == 12345

class TestLessonService:
    @pytest.mark.asyncio
    async def test_start_lesson(self, mock_api):
        service = LessonService(mock_api)
        lesson = await service.start_lesson(user_id=1, topic="crypto")
        assert lesson.topic == "crypto"
```

### Интеграционные тесты:

```python
# tests/test_bot_handlers.py

class TestCommandHandler:
    @pytest.mark.asyncio
    async def test_handle_start(self, mock_update, mock_context):
        handler = CommandHandler(user_service)
        await handler.handle_start(mock_update, mock_context)
        # Проверяем что было отправлено сообщение
```

---

## 📊 Ожидаемые результаты Phase 2

```
Метрика                  До      После       Улучшение
─────────────────────────────────────────────────────
bot.py (строк)          11010   ~300 (×8)   88% ↓
Дублирование кода       Много   Минимум     ~80% ↓
SRP оценка               2/10    8/10        +300% ↑
Тестируемость           Сложно  Легко       +100% ↑
Time to change           Долго   Быстро      50x быстрее
New tests                -       50+         +50 тестов
SOLID оценка             6.0     8.5         +41% ↑
─────────────────────────────────────────────────────
```

---

## 🔄 Миграция: Как переходить

### Вариант 1: Параллельная разработка (Рекомендуется)

```python
# Создаем новый bot параллельно со старым
# bot_new/          - Новая рефакторизованная версия
# bot.py (старая)   - Работает как раньше

# Тестируем bot_new/
# Когда готово, переименовываем:
# mv bot.py bot_old_backup.py
# mv bot_new bot.py
```

### Вариант 2: Постепенное внедрение

```python
# Добавляем новые модули в существующий bot.py
from bot.services import UserService
from bot.handlers import CommandHandler

# Постепенно переписываем функции
# Старая функция: 50 строк
# Новая: 5 строк (просто вызов сервиса)
```

---

## 📚 Documentation для Phase 2

- [ ] SPRINT4_PHASE2_PLAN.md - Этот документ
- [ ] bot/README.md - Архитектура и структура
- [ ] bot/services/README.md - Описание каждого сервиса
- [ ] bot/handlers/README.md - Описание хэндлеров
- [ ] MIGRATION_GUIDE.md - Как переходить с версии на версию

---

## ⏰ Timeline

| День | Задачи | ETA |
|------|--------|-----|
| День 1 | Создать структуру, services layer | 4 часа |
| День 1 | Создать handlers | 3 часа |
| День 1 | Unit тесты | 2 часа |
| День 2 | Интеграционные тесты | 2 часа |
| День 2 | Миграция и проверка | 2 часа |
| День 2 | Документация | 1 час |

**Итого**: ~14 часов = 1-2 дня активной разработки

---

## 🎯 Следующие шаги

### СЕЙЧАС (Phase 1 ✅):
- ✅ Анализ проблем
- ✅ Дизайн решений
- ✅ Реализация API абстракций
- ✅ Создание DAL и validators

### СЛЕДУЮЩЕЕ (Phase 2 📋):
- [ ] Разделить bot.py на 8 модулей
- [ ] Создать service layer
- [ ] Миграция хэндлеров
- [ ] Unit тесты для сервисов
- [ ] Интеграционные тесты

### ПОТОМ (Phase 3 🔜):
- [ ] Полный refactor всех модулей
- [ ] Добавить новые возможности
- [ ] Optimization
- [ ] Performance tuning

---

## 🎓 Выводы

После Phase 2:

✅ bot.py будет модульным и понятным  
✅ Каждый сервис будет легко тестируемым  
✅ Легко добавлять новые фичи  
✅ Легко менять существующие  
✅ Production-quality код  

**TOTAL SOLID оценка**: 6.0 → 8.5/10 (+41% улучшение)

---

**Готовы к Phase 2?** 🚀

Начинаем, как только скажете!
