import os
import logging
import json
import re 
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool 

from google import genai
from google.genai.errors import APIError

# --- 1. Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RVX_API")

# --- 2. Загрузка конфигурации ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "4096"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1500"))

# --- 3. Глобальные переменные ---
client: Optional[genai.Client] = None
request_counter = {"total": 0, "success": 0, "errors": 0}

# --- 4. Lifecycle management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    global client
    
    # Startup
    logger.info("=" * 60)
    logger.info("🚀 Запуск RVX AI Backend API")
    logger.info("=" * 60)
    
    if not GEMINI_API_KEY:
        logger.critical("❌ GEMINI_API_KEY не найден в .env!")
    else:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info("✅ Клиент Gemini инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Gemini: {e}")
            client = None
    
    logger.info("Конфигурация:")
    logger.info(f"  • MAX_TEXT_LENGTH: {MAX_TEXT_LENGTH}")
    logger.info(f"  • GEMINI_MODEL: {GEMINI_MODEL}")
    logger.info(f"  • TEMPERATURE: {GEMINI_TEMPERATURE}")
    logger.info(f"  • MAX_TOKENS: {GEMINI_MAX_TOKENS}")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("🛑 Остановка API")
    logger.info(f"Статистика: {request_counter['total']} запросов, "
                f"{request_counter['success']} успешных, {request_counter['errors']} ошибок")

app = FastAPI(
    title="RVX AI Backend",
    version="2.2.0",
    description="API для анализа криптоновостей",
    lifespan=lifespan
)

# --- 5. Утилиты ---

def clean_text(text: str) -> str:
    """Очищает текст от markdown и лишних пробелов."""
    if not text:
        return ""
    
    # Убираем markdown
    text = text.replace('**', '').replace('*', '')
    text = text.replace('__', '').replace('_', '')
    text = text.replace('~~', '')
    
    # Убираем лишние пробелы
    text = ' '.join(text.split())
    
    return text.strip()

def extract_json_from_response(raw_text: str) -> Optional[dict]:
    """Извлекает JSON из ответа AI."""
    if not raw_text:
        return None
    
    # Очищаем от markdown блоков
    raw_text = re.sub(r'```json\s*', '', raw_text)
    raw_text = re.sub(r'```\s*', '', raw_text)
    
    # Стратегия 1: XML теги
    xml_match = re.search(r'<json>(.*?)</json>', raw_text, re.DOTALL | re.IGNORECASE)
    if xml_match:
        try:
            return json.loads(xml_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Стратегия 2: Поиск {...}
    brace_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    
    logger.error(f"Не удалось извлечь JSON: {raw_text[:200]}...")
    return None

def validate_analysis(data: dict) -> bool:
    """Проверяет структуру ответа AI."""
    if not isinstance(data, dict):
        return False
    
    if "summary_text" not in data or not isinstance(data["summary_text"], str):
        return False
    
    if "impact_points" not in data or not isinstance(data["impact_points"], list):
        return False
    
    if not data["impact_points"] or not all(isinstance(p, str) for p in data["impact_points"]):
        return False
    
    return True

def format_response(analysis: dict) -> str:
    """Форматирует анализ для Telegram."""
    summary = clean_text(analysis.get('summary_text', 'Нет описания'))
    
    emojis = ['📉', '📊', '⚡️', '💰', '🎯', '🔥', '📈', '⚠️']
    separator = "━━━━━━━━━━━━━━━━━━"
    
    result = f"{separator}\n🔍 СУТЬ\n\n{summary}\n\n{separator}\n💡 ВЛИЯНИЕ НА КРИПТУ\n\n"
    
    for i, point in enumerate(analysis.get('impact_points', [])):
        if point.strip():
            clean_point = clean_text(point)
            emoji = emojis[i % len(emojis)]
            result += f"{emoji} {clean_point}\n\n"
    
    result += separator
    return result.strip()

# --- 6. Модели данных ---

class NewsPayload(BaseModel):
    """Входные данные."""
    text_content: str = Field(..., min_length=10, max_length=MAX_TEXT_LENGTH)
    
    @validator('text_content')
    def validate_text(cls, v):
        if not v.strip():
            raise ValueError("Текст не может быть пустым")
        return v.strip()

class SimplifiedResponse(BaseModel):
    """Ответ API."""
    simplified_text: str

class HealthResponse(BaseModel):
    """Health check."""
    status: str
    gemini_available: bool
    requests_total: int
    requests_success: int
    requests_errors: int

# --- 7. Middleware ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирует запросы."""
    logger.info(f"📨 {request.method} {request.url.path}")
    request_counter["total"] += 1
    
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        request_counter["errors"] += 1
        return JSONResponse(
            status_code=500,
            content={"simplified_text": "❌ Ошибка сервера"}
        )

# --- 8. Эндпоинты ---

@app.get("/")
async def root():
    """Информация об API."""
    return {
        "service": "RVX AI Backend",
        "version": "2.2.0",
        "status": "running",
        "endpoints": {
            "analyze": "/explain_news",
            "health": "/health"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check."""
    return HealthResponse(
        status="healthy" if client else "degraded",
        gemini_available=client is not None,
        requests_total=request_counter["total"],
        requests_success=request_counter["success"],
        requests_errors=request_counter["errors"]
    )

@app.post("/explain_news", response_model=SimplifiedResponse)
async def explain_news(payload: NewsPayload):
    """Анализирует криптоновость."""
    if not client:
        logger.error("Gemini недоступен")
        request_counter["errors"] += 1
        raise HTTPException(503, "Сервис AI недоступен")
    
    news_text = payload.text_content
    logger.info(f"📥 Анализ ({len(news_text)} символов)")
    
    # Промпт для AI
    system_prompt = (
        "Ты — криптоаналитик RVX. Объясняй новости просто.\n\n"
        "ПРАВИЛА:\n"
        "- Отвечай JSON в тегах <json></json>\n"
        "- БЕЗ markdown (**, *, _)\n"
        "- БЕЗ эмодзи\n\n"
        "Формат:\n"
        '{"summary_text": "2-3 предложения о сути", '
        '"impact_points": ["пункт 1", "пункт 2", "пункт 3"]}\n\n'
        "Пример:\n"
        '{"summary_text": "Bitcoin достиг максимума. Рост связан с институциональным спросом.", '
        '"impact_points": ["Усиление доверия", "Возможный рост альткоинов"]}'
    )
    
    user_prompt = f"Проанализируй:\n\n{news_text}"
    
    try:
        # Вызов Gemini
        def sync_call():
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[user_prompt],
                config={
                    "system_instruction": system_prompt,
                    "temperature": GEMINI_TEMPERATURE,
                    "max_output_tokens": GEMINI_MAX_TOKENS
                }
            )
        
        logger.info("🤖 Запрос к Gemini...")
        response = await run_in_threadpool(sync_call)
        raw_text = response.text
        
        if not raw_text:
            logger.warning("⚠️ Пустой ответ")
            request_counter["errors"] += 1
            return SimplifiedResponse(
                simplified_text="⚠️ AI не смог ответить. Попробуйте другую новость."
            )
        
        logger.info(f"📤 Ответ получен ({len(raw_text)} символов)")
        
        # Парсинг
        data = extract_json_from_response(raw_text)
        
        if not data or not validate_analysis(data):
            logger.error("❌ Невалидный JSON")
            request_counter["errors"] += 1
            return SimplifiedResponse(
                simplified_text="❌ AI вернул некорректный ответ."
            )
        
        # Форматирование
        formatted = format_response(data)
        
        logger.info("✅ Успех")
        request_counter["success"] += 1
        
        return SimplifiedResponse(simplified_text=formatted)
    
    except APIError as e:
        logger.error(f"❌ Gemini API: {e}")
        request_counter["errors"] += 1
        return SimplifiedResponse(
            simplified_text="❌ Сервис AI недоступен. Попробуйте через минуту."
        )
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        request_counter["errors"] += 1
        return SimplifiedResponse(
            simplified_text="❌ Внутренняя ошибка."
        )

# --- 9. Обработчики ошибок ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP ошибки."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"simplified_text": f"❌ {exc.detail}"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Общие ошибки."""
    logger.error(f"Необработанная ошибка: {exc}", exc_info=True)
    request_counter["errors"] += 1
    return JSONResponse(
        status_code=500,
        content={"simplified_text": "❌ Ошибка сервера"}
    )

# --- 10. Запуск ---
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🚀 Запуск на порту {port}")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )