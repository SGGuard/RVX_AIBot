import os
import logging
import json
import re
import hashlib
import asyncio
from typing import Optional, Any, Dict
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from google import genai
from google.genai.errors import APIError

# =============================================================================
# КОНФИГУРАЦИЯ И НАСТРОЙКА
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RVX_API")

load_dotenv()

# Конфигурация
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "4096"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1500"))
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Глобальные переменные
client: Optional[genai.Client] = None
request_counter = {"total": 0, "success": 0, "errors": 0, "fallback": 0}
response_cache: Dict[str, Dict] = {}  # Простой in-memory кэш

# =============================================================================
# МОДЕЛИ ДАННЫХ
# =============================================================================

class NewsPayload(BaseModel):
    """Входные данные для анализа новости."""
    text_content: str = Field(..., min_length=10, max_length=MAX_TEXT_LENGTH)
    
    @validator('text_content')
    def validate_and_sanitize(cls, v):
        if not v.strip():
            raise ValueError("Текст не может быть пустым")
        return sanitize_input(v.strip())

class SimplifiedResponse(BaseModel):
    """Ответ API с анализом."""
    simplified_text: str
    cached: bool = False
    processing_time_ms: Optional[float] = None

class HealthResponse(BaseModel):
    """Статус здоровья API."""
    status: str
    gemini_available: bool
    requests_total: int
    requests_success: int
    requests_errors: int
    requests_fallback: int
    cache_size: int
    uptime_seconds: Optional[float] = None

# =============================================================================
# УТИЛИТЫ
# =============================================================================

def sanitize_input(text: str) -> str:
    """Защита от prompt injection и очистка входных данных."""
    dangerous_patterns = [
        r'ignore\s+(previous|all|above)\s+instructions?',
        r'system\s*:',
        r'<\|im_start\|>',
        r'<\|im_end\|>',
        r'you\s+are\s+now',
        r'forget\s+everything',
        r'new\s+instructions?',
    ]
    
    cleaned = text
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Удаляем подозрительные последовательности символов
    cleaned = re.sub(r'[^\w\s\d\.,!?;:()\-—\'\"№@#$%&*+=/\\<>«»€£¥₽₿]', '', cleaned)
    
    return cleaned[:MAX_TEXT_LENGTH]

def hash_text(text: str) -> str:
    """Создает SHA-256 хеш для кэширования."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def clean_text(text: str) -> str:
    """Удаляет markdown, HTML-теги и лишние пробелы."""
    if not text:
        return ""
    
    # Удаляем HTML
    text = re.sub(r'<[^>]*>', '', text)
    
    # Удаляем markdown
    text = re.sub(r'(\*\*|__|\*|_|~~|`)', '', text)
    
    # Нормализуем пробелы
    text = ' '.join(text.split())
    
    return text.strip()

def extract_json_from_response(raw_text: str) -> Optional[dict]:
    """Извлекает JSON из ответа AI с множественными стратегиями."""
    if not raw_text:
        return None
    
    # Стратегия 1: Удаляем markdown блоки
    text = re.sub(r'```json\s*', '', raw_text, flags=re.IGNORECASE).strip()
    text = re.sub(r'```\s*', '', text).strip()
    
    # Стратегия 2: XML теги <json>...</json>
    xml_match = re.search(r'<json>(.*?)</json>', text, re.DOTALL | re.IGNORECASE)
    if xml_match:
        text_to_parse = xml_match.group(1).strip()
    else:
        # Стратегия 3: Ищем первый валидный JSON блок
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            text_to_parse = brace_match.group(0)
        else:
            logger.warning(f"JSON не найден. Начало ответа: {raw_text[:100]}...")
            return None
    
    # Парсинг с обработкой ошибок
    try:
        data = json.loads(text_to_parse)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error на строке {e.lineno}, колонке {e.colno}")
        logger.debug(f"Проблемный текст: {text_to_parse[:200]}")
        return None

def validate_analysis(data: Any) -> tuple[bool, Optional[str]]:
    """Валидация структуры и качества ответа AI."""
    if not isinstance(data, dict):
        return False, "Ответ не является словарем"
    
    # Проверка обязательных полей
    required_fields = ["summary_text", "impact_points"]
    for field in required_fields:
        if field not in data:
            return False, f"Отсутствует обязательное поле: {field}"
    
    # Валидация summary_text
    summary = data["summary_text"]
    if not isinstance(summary, str):
        return False, "summary_text должен быть строкой"
    if len(summary.strip()) < 20:
        return False, f"summary_text слишком короткий ({len(summary)} символов)"
    if len(summary) > 1000:
        return False, "summary_text слишком длинный"
    
    # Валидация impact_points
    points = data["impact_points"]
    if not isinstance(points, list):
        return False, "impact_points должен быть списком"
    if len(points) < 2:
        return False, f"Минимум 2 impact_points требуется (получено {len(points)})"
    if len(points) > 10:
        return False, "Слишком много impact_points (максимум 10)"
    
    # Проверка каждого пункта
    for i, point in enumerate(points):
        if not isinstance(point, str):
            return False, f"impact_points[{i}] должен быть строкой"
        if len(point.strip()) < 10:
            return False, f"impact_points[{i}] слишком короткий"
        if len(point) > 500:
            return False, f"impact_points[{i}] слишком длинный"
    
    return True, None

def format_response(analysis: dict) -> str:
    """Форматирует анализ для читаемого вывода."""
    summary = clean_text(analysis.get('summary_text', 'Нет описания'))
    
    emojis = ['📉', '📊', '⚡️', '💰', '🎯', '🔥', '📈', '⚠️', '💡', '🌐']
    separator = "━━━━━━━━━━━━━━━━━━"
    
    result = f"{separator}\n🔍 СУТЬ\n\n{summary}\n\n{separator}\n💡 ВЛИЯНИЕ НА КРИПТУ\n\n"
    
    for i, point in enumerate(analysis.get('impact_points', [])):
        if point.strip():
            clean_point = clean_text(point)
            emoji = emojis[i % len(emojis)]
            result += f"{emoji} {clean_point}\n\n"
    
    result += separator
    return result.strip()

def fallback_analysis(text: str) -> str:
    """Упрощенный анализ без AI (для аварийных ситуаций)."""
    keywords = {
        'bitcoin': '₿', 'btc': '₿', 'ethereum': 'Ξ', 'eth': 'Ξ',
        'sec': '⚖️', 'регулятор': '⚖️', 'fomo': '🚀',
        'hack': '🚨', 'взлом': '🚨', 'dump': '📉', 'обвал': '📉',
        'pump': '📈', 'рост': '📈', 'etf': '💼', 'whale': '🐋'
    }
    
    words = text.lower().split()
    summary = text[:250] + "..." if len(text) > 250 else text
    
    impact = "⚠️ AI временно недоступен. Базовые наблюдения:\n\n"
    
    found_keywords = []
    for word, emoji in keywords.items():
        if word in ' '.join(words):
            found_keywords.append(f"{emoji} Упоминается: {word.upper()}")
    
    if found_keywords:
        impact += '\n'.join(found_keywords)
    else:
        impact += "📰 Стандартная криптоновость"
    
    separator = "━━━━━━━━━━━━━━━━━━"
    return f"🤖 УПРОЩЕННЫЙ РЕЖИМ\n\n{separator}\n{summary}\n\n{separator}\n{impact}"

def build_gemini_config() -> dict:
    """Создает оптимизированную конфигурацию для Gemini."""
    system_prompt = (
        "Ты — **незаменимый криптоаналитик RVX**, созданный для мгновенного анализа криптоновостей. "
        "Твоя задача — объяснить сложные события максимально просто, избегая жаргона.\n\n"
        
        "**СТИЛЬ ОБЩЕНИЯ:**\n"
        "- Тон: дружелюбный, но уверенный, как у опытного наставника\n"
        "- Фокус: влияние на рынок (ликвидность, цены, доверие, регуляции)\n"
        "- Целевая аудитория: трейдеры с СДВГ (краткость = ключ)\n\n"
        
        "**СТРОГИЕ ПРАВИЛА ОТВЕТА:**\n"
        "1. Отвечай ТОЛЬКО в формате JSON, заключенном в теги <json></json>\n"
        "2. ЗАПРЕЩЕНО использовать Markdown (**, *, _, ~, `) внутри JSON-полей\n"
        "3. ЗАПРЕЩЕНО использовать эмодзи внутри JSON-полей\n"
        "4. ЗАПРЕЩЕНО использовать HTML-теги\n"
        "5. Используй только простой текст в полях JSON\n\n"
        
        "**СТРУКТУРА ОТВЕТА (строго соблюдай):**\n"
        '{"summary_text": "2-3 предложения о сути новости. Переводи жаргон на человеческий язык.", '
        '"impact_points": ["Влияние 1: конкретное последствие", "Влияние 2: кто выиграет/проиграет", '
        '"Влияние 3: что делать трейдеру"]}\n\n'
        
        "**ПРИМЕР ИДЕАЛЬНОГО ОТВЕТА:**\n"
        '<json>{"summary_text": "SEC одобрила первый биткоин-ETF от BlackRock. '
        'Теперь обычные инвесторы смогут покупать BTC через брокерские счета, как акции Apple.", '
        '"impact_points": ["Приток капитала: ожидается 50-100 млрд долларов за год, рост цены BTC на 30-50%", '
        '"Легитимность крипты: институционалы перестанут бояться регуляторов", '
        '"Конкуренция обострится: Fidelity и Vanguard подадут заявки в течение месяца"]}</json>\n\n'
        
        "Теперь проанализируй новость ниже, строго следуя формату."
    )
    
    return {
        "system_instruction": system_prompt,
        "temperature": GEMINI_TEMPERATURE,
        "max_output_tokens": GEMINI_MAX_TOKENS,
        "top_p": 0.95,
        "top_k": 40
    }

# =============================================================================
# РАБОТА С GEMINI API
# =============================================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def call_gemini_with_retry(
    client: genai.Client,
    model: str,
    contents: list,
    config: dict
) -> Any:
    """Вызов Gemini с автоматическими повторами при ошибках."""
    def sync_call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
    
    return await asyncio.wait_for(
        run_in_threadpool(sync_call),
        timeout=GEMINI_TIMEOUT
    )

# =============================================================================
# LIFECYCLE MANAGEMENT
# =============================================================================

start_time = datetime.utcnow()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    global client
    
    # Startup
    logger.info("=" * 70)
    logger.info("🚀 Запуск RVX AI Backend API v3.0")
    logger.info("=" * 70)
    
    if not GEMINI_API_KEY:
        logger.critical("❌ GEMINI_API_KEY не найден в .env файле!")
    else:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info("✅ Клиент Gemini успешно инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Gemini: {e}")
            client = None
    
    logger.info("📋 Конфигурация:")
    logger.info(f"  • MAX_TEXT_LENGTH: {MAX_TEXT_LENGTH}")
    logger.info(f"  • GEMINI_MODEL: {GEMINI_MODEL}")
    logger.info(f"  • TEMPERATURE: {GEMINI_TEMPERATURE}")
    logger.info(f"  • MAX_TOKENS: {GEMINI_MAX_TOKENS}")
    logger.info(f"  • TIMEOUT: {GEMINI_TIMEOUT}s")
    logger.info(f"  • CACHE_ENABLED: {CACHE_ENABLED}")
    logger.info("=" * 70)
    
    yield
    
    # Shutdown
    logger.info("🛑 Остановка API")
    logger.info(f"📊 Финальная статистика:")
    logger.info(f"  • Всего запросов: {request_counter['total']}")
    logger.info(f"  • Успешных: {request_counter['success']}")
    logger.info(f"  • Ошибок: {request_counter['errors']}")
    logger.info(f"  • Fallback режим: {request_counter['fallback']}")
    logger.info(f"  • Размер кэша: {len(response_cache)}")

# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="RVX AI Backend",
    version="3.0.0",
    description="Production-ready API для анализа криптоновостей с AI",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# =============================================================================
# MIDDLEWARE
# =============================================================================

@app.middleware("http")
async def log_and_monitor_requests(request: Request, call_next):
    """Логирование и мониторинг всех запросов."""
    start = datetime.utcnow()
    request_counter["total"] += 1
    
    logger.info(f"📨 {request.method} {request.url.path} | IP: {request.client.host}")
    
    try:
        response = await call_next(request)
        duration = (datetime.utcnow() - start).total_seconds()
        
        logger.info(f"✅ {request.url.path} завершен за {duration:.2f}s | Статус: {response.status_code}")
        return response
        
    except Exception as e:
        duration = (datetime.utcnow() - start).total_seconds()
        logger.error(f"❌ Критическая ошибка в middleware: {e} | Длительность: {duration:.2f}s")
        request_counter["errors"] += 1
        
        return JSONResponse(
            status_code=500,
            content={"simplified_text": "❌ Внутренняя ошибка сервера"}
        )

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Информация об API."""
    uptime = (datetime.utcnow() - start_time).total_seconds()
    
    return {
        "service": "RVX AI Backend",
        "version": "3.0.0",
        "status": "operational",
        "uptime_seconds": round(uptime, 2),
        "endpoints": {
            "analyze": "POST /explain_news",
            "health": "GET /health",
            "docs": "GET /docs"
        },
        "features": [
            "Retry logic с экспоненциальной задержкой",
            "In-memory кэширование",
            "Fallback режим при недоступности AI",
            "Prompt injection защита",
            "Structured logging"
        ]
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Детальная проверка состояния сервиса."""
    uptime = (datetime.utcnow() - start_time).total_seconds()
    
    return HealthResponse(
        status="healthy" if client else "degraded",
        gemini_available=client is not None,
        requests_total=request_counter["total"],
        requests_success=request_counter["success"],
        requests_errors=request_counter["errors"],
        requests_fallback=request_counter["fallback"],
        cache_size=len(response_cache),
        uptime_seconds=round(uptime, 2)
    )

@app.post("/explain_news", response_model=SimplifiedResponse)
async def explain_news(payload: NewsPayload):
    """
    Анализирует криптоновость с помощью AI.
    
    Возвращает структурированный анализ с кратким изложением и ключевыми влияниями на рынок.
    """
    start_time_request = datetime.utcnow()
    news_text = payload.text_content
    text_hash = hash_text(news_text)
    
    logger.info(f"📥 Новый запрос: {len(news_text)} символов | Hash: {text_hash[:8]}...")
    
    # Проверка кэша
    if CACHE_ENABLED and text_hash in response_cache:
        cached = response_cache[text_hash]
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        logger.info(f"💾 Кэш HIT для {text_hash[:8]}")
        request_counter["success"] += 1
        
        return SimplifiedResponse(
            simplified_text=cached["text"],
            cached=True,
            processing_time_ms=round(duration_ms, 2)
        )
    
    # Если Gemini недоступен, используем fallback
    if not client:
        logger.warning("⚠️ Gemini недоступен, использую fallback режим")
        request_counter["fallback"] += 1
        
        fallback_text = fallback_analysis(news_text)
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        return SimplifiedResponse(
            simplified_text=fallback_text,
            cached=False,
            processing_time_ms=round(duration_ms, 2)
        )
    
    # Вызов AI
    try:
        gemini_config = build_gemini_config()
        user_prompt = f"Проанализируй следующую криптоновость:\n\n{news_text}"
        
        logger.info("🤖 Отправка запроса к Gemini API...")
        
        response = await call_gemini_with_retry(
            client=client,
            model=GEMINI_MODEL,
            contents=[user_prompt],
            config=gemini_config
        )
        
        raw_text = response.text
        
        if not raw_text or len(raw_text.strip()) < 10:
            logger.warning("⚠️ Получен пустой/короткий ответ от AI")
            raise ValueError("AI вернул пустой ответ")
        
        logger.info(f"📤 Получен ответ от AI: {len(raw_text)} символов")
        
        # Парсинг и валидация
        data = extract_json_from_response(raw_text)
        
        if not data:
            logger.error("❌ Не удалось извлечь JSON из ответа AI")
            raise ValueError("Некорректный формат ответа AI")
        
        is_valid, error_msg = validate_analysis(data)
        
        if not is_valid:
            logger.error(f"❌ Валидация провалена: {error_msg}")
            logger.debug(f"Данные: {json.dumps(data, ensure_ascii=False, indent=2)}")
            raise ValueError(f"Невалидный анализ: {error_msg}")
        
        # Форматирование
        formatted_text = format_response(data)
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        # Сохранение в кэш
        if CACHE_ENABLED:
            response_cache[text_hash] = {
                "text": formatted_text,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Ограничение размера кэша (простая LRU стратегия)
            if len(response_cache) > 100:
                oldest_key = min(response_cache.keys(), 
                               key=lambda k: response_cache[k]["timestamp"])
                del response_cache[oldest_key]
        
        logger.info(f"✅ Анализ завершен за {duration_ms:.0f}ms")
        request_counter["success"] += 1
        
        return SimplifiedResponse(
            simplified_text=formatted_text,
            cached=False,
            processing_time_ms=round(duration_ms, 2)
        )
    
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Timeout ({GEMINI_TIMEOUT}s) при запросе к Gemini")
        request_counter["errors"] += 1
        request_counter["fallback"] += 1
        
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        return SimplifiedResponse(
            simplified_text=fallback_analysis(news_text),
            cached=False,
            processing_time_ms=round(duration_ms, 2)
        )
    
    except RetryError as e:
        logger.error(f"❌ Все попытки retry исчерпаны: {e}")
        request_counter["errors"] += 1
        request_counter["fallback"] += 1
        
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        return SimplifiedResponse(
            simplified_text=fallback_analysis(news_text),
            cached=False,
            processing_time_ms=round(duration_ms, 2)
        )
    
    except APIError as e:
        logger.error(f"❌ Gemini API Error (код {e.status_code}): {e.message}")
        request_counter["errors"] += 1
        
        if e.status_code == 429:  # Rate limit
            detail = "🚦 Превышен лимит запросов к AI. Попробуйте через минуту."
        elif e.status_code >= 500:
            detail = "🔧 Сервис AI временно недоступен."
        else:
            detail = "⚠️ Ошибка при обращении к AI."
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )
    
    except ValueError as e:
        logger.error(f"❌ Ошибка валидации: {e}")
        request_counter["errors"] += 1
        request_counter["fallback"] += 1
        
        duration_ms = (datetime.utcnow() - start_time_request).total_seconds() * 1000
        
        return SimplifiedResponse(
            simplified_text=fallback_analysis(news_text),
            cached=False,
            processing_time_ms=round(duration_ms, 2)
        )
    
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        request_counter["errors"] += 1
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )

# =============================================================================
# ОБРАБОТЧИКИ ОШИБОК
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработка HTTP ошибок с единообразным форматом."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "simplified_text": f"❌ {exc.detail}",
            "cached": False,
            "processing_time_ms": None
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Обработка всех необработанных исключений."""
    logger.error(f"🔥 Необработанное исключение: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "simplified_text": "❌ Критическая ошибка сервера. Команда уже уведомлена.",
            "cached": False,
            "processing_time_ms": None
        }
    )

# =============================================================================
# ЗАПУСК (для development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🚀 Запуск development сервера на порту {port}")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
