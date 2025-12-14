# 🔧 SOLID/DRY/KISS Рефакторизация - Конкретные Примеры Кода

**Дата**: 14 декабря 2025  
**Версия**: SPRINT 4 Plan  
**Цель**: Превратить проект в Production-Quality архитектуру

---

## 🎯 Пример 1: Абстракция для AI Провайдеров (OCP + LSP)

### ❌ ДО (Нарушает OCP и LSP):

```python
# api_server.py - ПЛОХО

import asyncio
from google import genai
from openai import OpenAI

# Разные интерфейсы для разных провайдеров!
client_gemini = genai.Client(api_key=GEMINI_API_KEY)
client_deepseek = OpenAI(api_key=DEEPSEEK_API_KEY)

async def call_gemini_with_retry(text: str):
    # Специфичный для Gemini код
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(text)
    return response.text

def call_deepseek(text: str):
    # Специфичный для DeepSeek код
    response = client_deepseek.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": text}]
    )
    return response.choices[0].message.content

async def analyze_news(text: str) -> Dict:
    # Нарушение OCP - нельзя добавить нового провайдера без изменения этой функции!
    try:
        result = await call_deepseek(text)
    except Exception:
        try:
            result = await call_gemini_with_retry(text)
        except Exception:
            result = "Error"
    return {"result": result}
```

**Проблемы**:
- ❌ Нельзя добавить нового AI провайдера без изменения функции
- ❌ Разные интерфейсы - нарушение LSP
- ❌ Невозможно тестировать без реального API
- ❌ Код жестко связан с конкретными реализациями

### ✅ ПОСЛЕ (SOLID-compliant):

```python
# ai/interfaces.py - Абстракция (OCP + LSP + DIP)

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

class AIProvider(ABC):
    """Интерфейс для всех AI провайдеров"""
    
    @abstractmethod
    async def analyze(self, text: str) -> AIResponse:
        """Анализирует текст и возвращает структурированный результат"""
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Проверяет доступность провайдера"""
        pass

@dataclass
class AIResponse:
    """Единый формат ответа для всех провайдеров"""
    summary_text: str
    impact_points: list[str]
    confidence: float
    provider: str
    raw_response: Dict[str, Any]

@dataclass
class HealthStatus:
    is_healthy: bool
    latency_ms: float
    error: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────
# ai/providers/gemini.py

from typing import Optional

class GeminiProvider(AIProvider):
    """Реализация провайдера Gemini"""
    
    def __init__(self, api_key: str, model: str = "models/gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization"""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client
    
    async def analyze(self, text: str) -> AIResponse:
        import time
        start = time.time()
        
        try:
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(text)
            
            # Парсинг ответа
            parsed = self._parse_response(response.text)
            
            return AIResponse(
                summary_text=parsed["summary_text"],
                impact_points=parsed["impact_points"],
                confidence=parsed.get("confidence", 0.8),
                provider="gemini",
                raw_response={"text": response.text}
            )
        except Exception as e:
            raise AIProviderException(f"Gemini error: {str(e)}")
    
    async def health_check(self) -> HealthStatus:
        import time
        start = time.time()
        
        try:
            model = genai.GenerativeModel(self.model)
            model.generate_content("test")
            latency = (time.time() - start) * 1000
            
            return HealthStatus(is_healthy=True, latency_ms=latency)
        except Exception as e:
            return HealthStatus(
                is_healthy=False,
                latency_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        # Специфичный для Gemini парсинг
        import re
        import json
        
        match = re.search(r'<json>(.*?)</json>', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return {"summary_text": text, "impact_points": []}

# ─────────────────────────────────────────────────────────────────────
# ai/providers/deepseek.py

class DeepSeekProvider(AIProvider):
    """Реализация провайдера DeepSeek"""
    
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    async def analyze(self, text: str) -> AIResponse:
        import time
        start = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": text}],
                temperature=0.3,
                max_tokens=1500
            )
            
            parsed = self._parse_response(response.choices[0].message.content)
            
            return AIResponse(
                summary_text=parsed["summary_text"],
                impact_points=parsed["impact_points"],
                confidence=parsed.get("confidence", 0.8),
                provider="deepseek",
                raw_response={"text": response.choices[0].message.content}
            )
        except Exception as e:
            raise AIProviderException(f"DeepSeek error: {str(e)}")
    
    async def health_check(self) -> HealthStatus:
        import time
        start = time.time()
        
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10
            )
            latency = (time.time() - start) * 1000
            
            return HealthStatus(is_healthy=True, latency_ms=latency)
        except Exception as e:
            return HealthStatus(
                is_healthy=False,
                latency_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        # Специфичный для DeepSeek парсинг
        import re
        import json
        
        match = re.search(r'<json>(.*?)</json>', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return {"summary_text": text, "impact_points": []}

# ─────────────────────────────────────────────────────────────────────
# ai/provider_factory.py - Factory Pattern (DIP)

class AIProviderFactory:
    """Фабрика для создания провайдеров (Inversion of Control)"""
    
    _providers = {
        "gemini": GeminiProvider,
        "deepseek": DeepSeekProvider,
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type):
        """Регистрирует новый провайдер без изменения кода!"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create(cls, provider_name: str, **kwargs) -> AIProvider:
        """Создает провайдер по имени"""
        if provider_name not in cls._providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        return cls._providers[provider_name](**kwargs)

# ─────────────────────────────────────────────────────────────────────
# ai/orchestrator.py - Оркестратор с fallback (DIP)

class AIOrchestrator:
    """Управляет провайдерами, handles fallback и retry логика"""
    
    def __init__(self, primary: AIProvider, fallback: Optional[AIProvider] = None):
        self.primary = primary
        self.fallback = fallback
    
    async def analyze(self, text: str) -> AIResponse:
        """Анализирует текст с fallback логикой"""
        
        try:
            # Пытаемся основной провайдер
            return await self.primary.analyze(text)
        except AIProviderException as e:
            logger.warning(f"Primary provider failed: {e}")
            
            if self.fallback:
                try:
                    return await self.fallback.analyze(text)
                except Exception as e:
                    logger.error(f"Fallback provider also failed: {e}")
                    raise
            else:
                raise
    
    async def health_check(self) -> Dict[str, HealthStatus]:
        """Проверяет здоровье всех провайдеров"""
        
        status = {}
        
        try:
            status["primary"] = await self.primary.health_check()
        except Exception as e:
            status["primary"] = HealthStatus(
                is_healthy=False,
                latency_ms=0,
                error=str(e)
            )
        
        if self.fallback:
            try:
                status["fallback"] = await self.fallback.health_check()
            except Exception as e:
                status["fallback"] = HealthStatus(
                    is_healthy=False,
                    latency_ms=0,
                    error=str(e)
                )
        
        return status

# ─────────────────────────────────────────────────────────────────────
# api_server.py - ПОСЛЕ (Чистый и простой!)

from ai.provider_factory import AIProviderFactory
from ai.orchestrator import AIOrchestrator

# Инициализация в lifespan (DIP - Dependency Injection)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup: создаем провайдеры один раз
    primary = AIProviderFactory.create(
        "deepseek",
        api_key=DEEPSEEK_API_KEY,
        model=DEEPSEEK_MODEL
    )
    
    fallback = AIProviderFactory.create(
        "gemini",
        api_key=GEMINI_API_KEY,
        model=GEMINI_MODEL
    )
    
    ai_orchestrator = AIOrchestrator(primary=primary, fallback=fallback)
    app.state.ai = ai_orchestrator
    
    yield
    
    # Cleanup (если нужен)
    pass

app = FastAPI(lifespan=lifespan)

@app.post("/explain_news")
async def analyze_news(request: NewsRequest) -> Dict:
    """Анализирует новость - код стал супер-простой!"""
    
    # Получаем AI от app.state (injected в lifespan)
    ai = request.app.state.ai
    
    # Вызываем единый интерфейс
    result = await ai.analyze(request.text_content)
    
    # Используем единый формат ответа
    return {
        "simplified_text": result.summary_text,
        "impact_points": result.impact_points,
        "confidence": result.confidence,
        "provider": result.provider
    }

@app.get("/health")
async def health_check():
    """Проверяет здоровье всех провайдеров"""
    
    ai = request.app.state.ai
    status = await ai.health_check()
    
    return {
        "status": "ok" if all(s.is_healthy for s in status.values()) else "degraded",
        "providers": status
    }
```

**Улучшения**:
- ✅ OCP: Можно добавить нового провайдера без изменения `api_server.py`!
- ✅ LSP: Все провайдеры взаимозаменяемы
- ✅ DIP: `api_server` зависит от интерфейса, не от конкретных реализаций
- ✅ KISS: Код понятный и простой
- ✅ DRY: Общая логика в одном месте
- ✅ Тестируемость: Легко мокировать провайдеры

---

## 🎯 Пример 2: Консолидация Валидации (DRY)

### ❌ ДО (Дублирование везде):

```python
# bot.py
def validate_message(text: str) -> bool:
    if not text:
        return False
    if len(text) > 4096:
        return False
    if len(text) < 10:
        return False
    return True

# api_server.py
def validate_input(text: str) -> bool:
    if not text:
        return False
    if len(text) > 4096:  # ТО ЖЕ САМОЕ!
        return False
    return True

# education.py
def validate_lesson_content(content: str) -> bool:
    if len(content) > 4096:  # ТО ЖЕ САМОЕ!
        return False
    return True
```

**Проблемы**: 
- ❌ Дублирование правил валидации в 3+ местах
- ❌ Если измениться лимит, нужно менять везде
- ❌ Невозможно переиспользовать логику

### ✅ ПОСЛЕ (Единая система валидации):

```python
# validators/__init__.py

from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

class ValidationError(Exception):
    """Единое исключение для всех ошибок валидации"""
    pass

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]

class TextValidationRule(Enum):
    """Правила валидации (единый источник истины)"""
    MIN_LENGTH = 10
    MAX_LENGTH = 4096
    REQUIRED = True

# validators/text_validator.py

class TextValidator:
    """Валидирует текстовые входы"""
    
    MIN_LENGTH = TextValidationRule.MIN_LENGTH.value
    MAX_LENGTH = TextValidationRule.MAX_LENGTH.value
    
    @classmethod
    def validate(cls, text: str) -> ValidationResult:
        """Валидирует текст и возвращает детальный результат"""
        
        errors = []
        
        # Пустой текст
        if not text or not text.strip():
            errors.append(f"Text is required")
        
        # Минимальная длина
        elif len(text) < cls.MIN_LENGTH:
            errors.append(f"Text is too short (min {cls.MIN_LENGTH} characters)")
        
        # Максимальная длина
        elif len(text) > cls.MAX_LENGTH:
            errors.append(f"Text is too long (max {cls.MAX_LENGTH} characters)")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )
    
    @classmethod
    def validate_or_raise(cls, text: str) -> str:
        """Валидирует или выбрасывает исключение"""
        result = cls.validate(text)
        if not result.is_valid:
            raise ValidationError("; ".join(result.errors))
        return text

# validators/security_validator.py

class SecurityValidator:
    """Проверяет безопасность входа"""
    
    # Все опасные паттерны в одном месте (DRY)
    DANGEROUS_PATTERNS = [
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
        r"INSERT\s+INTO",
        r"UPDATE\s+.*SET",
        r"<script>",
        r"javascript:",
    ]
    
    @classmethod
    def validate(cls, text: str) -> ValidationResult:
        """Проверяет текст на опасные паттерны"""
        
        errors = []
        
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(f"Potentially dangerous pattern detected: {pattern}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )

# Использование в разных модулях:

# bot.py
from validators import TextValidator, SecurityValidator

async def handle_message(update: Update):
    text = update.message.text
    
    # Валидация текста
    result = TextValidator.validate(text)
    if not result.is_valid:
        await update.message.reply_text("; ".join(result.errors))
        return
    
    # Проверка безопасности
    result = SecurityValidator.validate(text)
    if not result.is_valid:
        logger.warning(f"Security issue detected: {result.errors}")
        return
    
    # ... дальше код

# api_server.py
from validators import TextValidator, SecurityValidator

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    # Валидация - один и тот же код!
    result = TextValidator.validate(request.text)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail="; ".join(result.errors))
    
    # Проверка безопасности - один и тот же код!
    result = SecurityValidator.validate(request.text)
    if not result.is_valid:
        raise HTTPException(status_code=403, detail="Security violation")
    
    # ... дальше код

# education.py
from validators import TextValidator

def extract_quiz(lesson: str) -> List[Question]:
    # Валидация - один и тот же код!
    result = TextValidator.validate(lesson)
    if not result.is_valid:
        raise ValueError("; ".join(result.errors))
    
    # ... дальше код
```

**Улучшения**:
- ✅ DRY: Один источник истины для правил валидации
- ✅ KISS: Простой и понятный интерфейс
- ✅ Легко менять правила (меняем в одном месте!)
- ✅ Тестируемость: Простые unit-тесты

---

## 🎯 Пример 3: Разделение bot.py (SRP)

### ❌ ДО (11010 строк в одном файле):

```python
# bot.py - СУПЕР БОЛЬШОЙ ФАЙЛ

class BotHandler:
    async def handle_message(self, update, context): ...          # 200 строк
    async def handle_start(self, update, context): ...            # 100 строк
    async def handle_help(self, update, context): ...             # 150 строк
    async def handle_lesson(self, update, context): ...           # 300 строк
    async def handle_quest(self, update, context): ...            # 250 строк
    async def handle_payment(self, update, context): ...          # 200 строк
    async def handle_profile(self, update, context): ...          # 150 строк
    async def handle_buttons(self, update, context): ...          # 400 строк
    async def handle_callback_query(self, update, context): ...   # 350 строк
    # ... еще 8000 строк
```

**Проблемы**:
- ❌ Один файл = одна огромная ответственность
- ❌ Невозможно понять и модифицировать
- ❌ Невозможно тестировать отдельно

### ✅ ПОСЛЕ (Разделено на сервисы):

```
bot/
├── __init__.py
├── core.py                 # Инициализация Application, регистрация хэндлеров
├── handlers/
│   ├── __init__.py
│   ├── message_handler.py  # Обработка текстовых сообщений
│   ├── button_handler.py   # Обработка кнопок
│   └── command_handler.py  # Обработка /start, /help и т.д.
├── services/
│   ├── __init__.py
│   ├── user_service.py     # Работа с профилем пользователя
│   ├── lesson_service.py   # Обработка уроков
│   ├── quest_service.py    # Обработка квестов
│   ├── payment_service.py  # Обработка платежей
│   └── db_service.py       # Работа с БД
└── schemas.py              # Pydantic модели

# ─────────────────────────────────────────────────────────────────────
# bot/core.py - Инициализация (только это!)

from telegram.ext import Application, CommandHandler, MessageHandler, filters

async def setup_bot():
    """Инициализирует бота и регистрирует хэндлеры"""
    
    # Создаем Application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем хэндлеры
    from bot.handlers import command_handler, message_handler, button_handler
    
    app.add_handler(CommandHandler("start", command_handler.handle_start))
    app.add_handler(CommandHandler("help", command_handler.handle_help))
    app.add_handler(MessageHandler(filters.TEXT, message_handler.handle))
    app.add_handler(ButtonHandler(..., button_handler.handle))
    
    return app

# ─────────────────────────────────────────────────────────────────────
# bot/handlers/command_handler.py - Только обработка команд!

from telegram import Update
from telegram.ext import ContextTypes
from bot.services import user_service

class CommandHandler:
    """Обработчик команд /start, /help и т.д."""
    
    @staticmethod
    async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start (SRP)"""
        
        # Работаем только с user_service
        user = await user_service.get_or_create(update.effective_user.id)
        
        message = f"Привет, {user.first_name}! 👋"
        await update.message.reply_text(message)
    
    @staticmethod
    async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help (SRP)"""
        
        message = "Это помощь..."
        await update.message.reply_text(message)

# ─────────────────────────────────────────────────────────────────────
# bot/handlers/message_handler.py - Только обработка сообщений!

from telegram import Update
from telegram.ext import ContextTypes
from bot.services import lesson_service, quest_service
from validators import TextValidator

class MessageHandler:
    """Обработчик текстовых сообщений (SRP)"""
    
    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текста (SRP)"""
        
        text = update.message.text
        
        # Валидация
        result = TextValidator.validate(text)
        if not result.is_valid:
            await update.message.reply_text("; ".join(result.errors))
            return
        
        # Определяем, что пользователь хочет
        intent = await self._detect_intent(text)
        
        # Делегируем нужному сервису
        if intent == "lesson":
            response = await lesson_service.process(text)
        elif intent == "quest":
            response = await quest_service.process(text)
        else:
            response = "Не понял. Используй /help"
        
        await update.message.reply_text(response)
    
    @staticmethod
    async def _detect_intent(text: str) -> str:
        """Определяет намерение пользователя"""
        # Простая логика детекции
        if "урок" in text.lower():
            return "lesson"
        elif "квест" in text.lower():
            return "quest"
        return "unknown"

# ─────────────────────────────────────────────────────────────────────
# bot/services/user_service.py - Работа с пользователем (SRP)

from bot.schemas import UserProfile
from db.repository import UserRepository

class UserService:
    """Управляет профилем пользователя (SRP)"""
    
    def __init__(self, repo: UserRepository):
        self.repo = repo
    
    async def get_or_create(self, user_id: int) -> UserProfile:
        """Получает или создает пользователя"""
        user = await self.repo.get(user_id)
        if not user:
            user = await self.repo.create(user_id)
        return user
    
    async def update_profile(self, user_id: int, **kwargs) -> UserProfile:
        """Обновляет профиль"""
        return await self.repo.update(user_id, **kwargs)

# ─────────────────────────────────────────────────────────────────────
# bot/services/lesson_service.py - Обработка уроков (SRP)

from bot.schemas import Lesson
from db.repository import LessonRepository

class LessonService:
    """Управляет уроками (SRP)"""
    
    def __init__(self, repo: LessonRepository):
        self.repo = repo
    
    async def process(self, user_input: str) -> str:
        """Обрабатывает запрос пользователя на урок"""
        
        # Получаем урок
        lesson = await self.repo.get_by_topic(user_input)
        
        # Возвращаем урок
        return lesson.content

# ─────────────────────────────────────────────────────────────────────
# main.py - Entry point (KISS - очень просто!)

from bot.core import setup_bot

async def main():
    """Главная функция"""
    
    # Инициализируем бота
    app = await setup_bot()
    
    # Запускаем
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

**Улучшения**:
- ✅ SRP: Каждый файл имеет одну ответственность
- ✅ DRY: Общая логика в сервисах
- ✅ KISS: Код легко понять
- ✅ Тестируемость: Каждый сервис можно тестировать отдельно
- ✅ Масштабируемость: Легко добавлять новые хэндлеры и сервисы

---

## 🎯 Пример 4: Database Access Layer (DAL) - DRY

### ❌ ДО (SQL дублируется везде):

```python
# bot.py
def get_user(user_id):
    conn = sqlite3.connect("rvx_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# education.py
def get_user(user_id):  # ТО ЖЕ САМОЕ!
    conn = sqlite3.connect("rvx_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# teacher.py
def get_user(user_id):  # ТО ЖЕ САМОЕ!
    conn = sqlite3.connect("rvx_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
```

### ✅ ПОСЛЕ (Единый DAL):

```python
# db/connection_pool.py - Управление подключениями (KISS)

from tier1_optimizations import DatabaseConnectionPool

class DBConnectionManager:
    """Управляет подключениями к БД"""
    
    _pool: Optional[DatabaseConnectionPool] = None
    
    @classmethod
    def init(cls, db_path: str = "rvx_bot.db"):
        """Инициализирует пул подключений"""
        cls._pool = DatabaseConnectionPool(db_path)
    
    @classmethod
    def get_connection(cls):
        """Получает подключение из пула"""
        if cls._pool is None:
            cls.init()
        return cls._pool.get_connection()

# ─────────────────────────────────────────────────────────────────────
# db/base_repository.py - Базовый репозиторий (SRP)

from typing import TypeVar, Generic, List, Optional
from abc import ABC, abstractmethod

T = TypeVar('T')

class BaseRepository(ABC, Generic[T]):
    """Базовый репозиторий для всех сущностей (Template Method паттерн)"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
    
    @abstractmethod
    def from_row(self, row: tuple) -> T:
        """Конвертирует строку БД в объект"""
        pass
    
    async def get(self, id: int) -> Optional[T]:
        """Получает запись по ID"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self.from_row(row) if row else None
        finally:
            conn.close()
    
    async def get_all(self) -> List[T]:
        """Получает все записи"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"SELECT * FROM {self.table_name}")
            rows = cursor.fetchall()
            return [self.from_row(row) for row in rows]
        finally:
            conn.close()
    
    async def create(self, **kwargs) -> T:
        """Создает новую запись"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            columns = ", ".join(kwargs.keys())
            placeholders = ", ".join(["?"] * len(kwargs))
            
            cursor.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
                tuple(kwargs.values())
            )
            conn.commit()
            
            # Получаем созданную запись
            return await self.get(cursor.lastrowid)
        finally:
            conn.close()
    
    async def update(self, id: int, **kwargs) -> T:
        """Обновляет запись"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values()) + [id]
            
            cursor.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()
            
            return await self.get(id)
        finally:
            conn.close()
    
    async def delete(self, id: int) -> bool:
        """Удаляет запись"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

# ─────────────────────────────────────────────────────────────────────
# db/repositories/user_repository.py - Специфичный репозиторий

from db.base_repository import BaseRepository
from bot.schemas import UserProfile

class UserRepository(BaseRepository[UserProfile]):
    """Репозиторий для пользователей"""
    
    def __init__(self):
        super().__init__("users")
    
    def from_row(self, row: tuple) -> UserProfile:
        """Конвертирует строку БД в UserProfile"""
        return UserProfile(
            id=row[0],
            telegram_id=row[1],
            first_name=row[2],
            username=row[3],
            xp=row[4],
            level=row[5],
            # ... остальные поля
        )
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[UserProfile]:
        """Получает пользователя по Telegram ID"""
        
        conn = DBConnectionManager.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                f"SELECT * FROM {self.table_name} WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = cursor.fetchone()
            return self.from_row(row) if row else None
        finally:
            conn.close()

# ─────────────────────────────────────────────────────────────────────
# Использование в разных модулях:

# bot/services/user_service.py
from db.repositories import UserRepository

class UserService:
    def __init__(self):
        self.repo = UserRepository()
    
    async def get_user(self, user_id: int):
        """Просто используем репозиторий"""
        return await self.repo.get(user_id)

# education.py
from db.repositories import UserRepository

async def get_user_progress(user_id: int):
    """Просто используем репозиторий"""
    repo = UserRepository()
    user = await repo.get(user_id)
    return user

# teacher.py
from db.repositories import UserRepository

async def update_xp(user_id: int, xp: int):
    """Просто используем репозиторий"""
    repo = UserRepository()
    user = await repo.update(user_id, xp=xp)
    return user
```

**Улучшения**:
- ✅ DRY: SQL код в одном месте
- ✅ SRP: Каждый репозиторий отвечает за свою таблицу
- ✅ KISS: Простой и понятный интерфейс
- ✅ OCP: Легко добавлять новые методы
- ✅ Тестируемость: Легко мокировать репозитории

---

## 📋 Чек-лист для Рефакторизации

- [ ] Шаг 1: Создать абстракции для AI провайдеров
- [ ] Шаг 2: Разделить `bot.py` на 8 файлов
- [ ] Шаг 3: Разделить `api_server.py` на 6 файлов
- [ ] Шаг 4: Консолидировать валидацию
- [ ] Шаг 5: Создать DAL (Data Access Layer)
- [ ] Шаг 6: Создать единую систему логирования
- [ ] Шаг 7: Внедрить IoC контейнер
- [ ] Шаг 8: Написать unit тесты
- [ ] Шаг 9: Обновить документацию
- [ ] Шаг 10: Провести code review

---

**Дата создания**: 14 декабря 2025  
**Статус**: ✅ Готово для реализации
