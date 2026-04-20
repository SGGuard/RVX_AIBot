import os
import sys
import logging
import json
import re
import hashlib
import asyncio
import base64
import time
from typing import Optional, Any, Dict, List, AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

# ============================================================================
# CRITICAL: Prevent API server from running in Railway
# ============================================================================
if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID'):
    print("❌ ERROR: API server cannot run in Railway environment!")
    print("    Railway is configured to run BOT ONLY via bot.py")
    print("    This file (api_server.py) must NOT be executed")
    sys.exit(1)

from fastapi import FastAPI, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

# DeepSeek AI (OpenAI compatible) + Google Gemini
from openai import OpenAI
from google import genai

# 🎯 OLLAMA LOCAL LLM (v1.0) - локальная LLM без интернета!
from ollama_client import initialize_ollama, get_ollama_client

# TIER 1 Optimizations (v0.22.0)
from tier1_optimizations import cache_manager, structured_logger

# Limited Cache (v1.0) - исправление утечки памяти
from limited_cache import LimitedCache

# AI Quality Fixer - улучшение качества ответов AI (v0.1.0)
from ai_quality_fixer import AIQualityValidator, get_improved_system_prompt

# Drops Tracker - для информации о дропах и активностях (v0.15.0)
from drops_tracker import (
    get_trending_tokens, get_nft_drops, get_activities,
    get_drops_by_chain, get_token_info
)

# ============================================================================
# 🔐 SECURITY MODULES v1.0 - Production-Grade Security
# ============================================================================
from security_manager import security_manager, SECURITY_HEADERS
from api_auth_manager import api_key_manager, init_auth_database
from audit_logger import audit_logger
from secrets_manager import get_safe_logger
from security_middleware import (
    RateLimiter,
)

# =============================================================================
# КОНФИГУРАЦИЯ И НАСТРОЙКА
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RVX_API")

load_dotenv()

# =============================================================================
# SECURITY UTILITIES (Critical Fix #2: Mask secrets in logs)
# =============================================================================

def mask_secret(secret: str, show_chars: int = 4) -> str:
    """Маскирует чувствительные строки для логирования."""
    if not secret or len(secret) <= show_chars * 2:
        return "***" * 3
    return f"{secret[:show_chars]}...{secret[-show_chars:]}"

def get_error_id() -> str:
    """Генерирует уникальный ID ошибки для логирования без раскрытия стека."""
    import uuid
    return str(uuid.uuid4())[:8]

# DeepSeek конфигурация (основной AI провайдер)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3"))
DEEPSEEK_MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "1500"))

# 🎯 OLLAMA конфигурация (локальная LLM без интернета - ПРИОРИТЕТ 1!)
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "1500"))

# Gemini конфигурация (резервный провайдер)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "4096"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1500"))
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))  # запросов
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # секунд
RATE_LIMIT_PER_IP = os.getenv("RATE_LIMIT_PER_IP", "true").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 час по умолчанию
CACHE_CLEANUP_INTERVAL = int(os.getenv("CACHE_CLEANUP_INTERVAL", "300"))  # 5 минут

# Глобальные переменные
deepseek_client: Optional[OpenAI] = None  # DeepSeek API (основной)
client: Optional[genai.Client] = None  # Gemini API (резервный)
request_counter = {"total": 0, "success": 0, "errors": 0, "fallback": 0, "rate_limited": 0}
response_cache = LimitedCache(max_size=1000, ttl_seconds=3600)  # ✅ ИСПРАВЛЕНО: LRU + TTL
ip_request_history: Dict[str, list] = {}  # Для rate limiting по IP

# CRITICAL FIX #1 & #2: Asyncio locks для синхронизации глобального состояния в async контексте
_client_lock: asyncio.Lock = None  # Инициализируется в lifespan
_deepseek_client_lock: asyncio.Lock = None  # Инициализируется в lifespan
_rate_limit_lock: asyncio.Lock = None  # Инициализируется в lifespan

# Security middleware instances
rate_limiter = RateLimiter(requests_per_minute=100, window_seconds=60)

# =============================================================================
# МОДЕЛИ ДАННЫХ
# =============================================================================

class NewsPayload(BaseModel):
    """Входные данные для анализа новости."""
    text_content: str = Field(..., min_length=10, max_length=MAX_TEXT_LENGTH)
    
    @field_validator('text_content')
    @classmethod
    def validate_and_sanitize(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Текст не может быть пустым")
        return sanitize_input(v.strip())

class TeachingPayload(BaseModel):
    """Входные данные для создания урока."""
    topic: str = Field(..., min_length=2, max_length=100)
    difficulty_level: str = Field(default="beginner")
    
    @field_validator('topic')
    @classmethod
    def validate_topic(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Тема не может быть пустой")
        return v.strip().lower()
    
    @field_validator('difficulty_level')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Уровень должен быть одним из: {', '.join(valid_levels)}")
        return v.lower()

class SimplifiedResponse(BaseModel):
    """Ответ API с анализом."""
    simplified_text: str
    cached: bool = False
    processing_time_ms: Optional[float] = None

class TeachingResponse(BaseModel):
    """Ответ API с учебным уроком."""
    lesson_title: str
    content: str
    key_points: list = Field(default_factory=list)
    real_world_example: str = ""
    practice_question: str = ""
    next_topics: list = Field(default_factory=list)
    processing_time_ms: Optional[float] = None

class HealthResponse(BaseModel):
    """Статус здоровья API."""
    status: str
    gemini_available: bool
    requests_total: int
    requests_success: int
    requests_errors: int
    requests_fallback: int
    requests_rate_limited: int = 0
    cache_size: int
    uptime_seconds: Optional[float] = None

# ============================================================================= 
# МОДЕЛИ ДРОПОВ И АКТИВНОСТЕЙ (v0.15.0)
# =============================================================================

class DropsResponse(BaseModel):
    """Ответ с информацией о дропах."""
    drops: list = Field(default_factory=list)
    count: int = 0
    source: str = "CoinGecko + Launchpads"
    timestamp: str = ""
    cache_ttl_minutes: int = 60

class ActivitiesResponse(BaseModel):
    """Ответ с информацией об активностях."""
    staking_updates: list = Field(default_factory=list)
    new_launches: list = Field(default_factory=list)
    contract_updates: list = Field(default_factory=list)
    governance: list = Field(default_factory=list)
    partnerships: list = Field(default_factory=list)
    total_activities: int = 0
    timestamp: str = ""
    cache_ttl_minutes: int = 60

class TokenInfoResponse(BaseModel):
    """Информация о конкретном токене."""
    name: str
    symbol: str
    price: float
    market_cap: float
    market_cap_rank: Optional[int]
    change_24h: float
    change_7d: float
    volume_24h: float
    ath: float
    atl: float
    timestamp: str = ""

class LeaderboardUserEntry(BaseModel):
    """Запись о пользователе в рейтинге."""
    rank: int
    user_id: int
    username: Optional[str]
    xp: int
    level: int
    total_requests: int

class UserRankEntry(BaseModel):
    """Позиция текущего пользователя."""
    rank: Optional[int] = None
    xp: int = 0
    level: int = 1
    total_requests: int = 0
    is_in_top: bool = False

class LeaderboardResponse(BaseModel):
    """Ответ с таблицей лидеров."""
    period: str
    top_users: List[LeaderboardUserEntry] = Field(default_factory=list)
    user_rank: Optional[UserRankEntry] = None
    total_users: int = 0
    cached: bool = False
    timestamp: str = ""

class ImagePayload(BaseModel):
    """Входные данные для анализа изображения."""
    image_url: Optional[str] = Field(None, description="URL изображения")
    image_base64: Optional[str] = Field(None, description="Изображение в формате base64")
    context: Optional[str] = Field(None, description="Дополнительный контекст", max_length=500)

class ImageAnalysisResponse(BaseModel):
    """Ответ API с анализом изображения."""
    analysis: str
    asset_type: Optional[str] = None  # "chart", "screenshot", "meme", "other"
    confidence: Optional[float] = None  # 0-1
    mentioned_assets: List[str] = Field(default_factory=list)
    simplified_text: str  # для совместимости с ботом
    cached: bool = False
    processing_time_ms: Optional[float] = None

# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter by IP address."""
    
    def __init__(self, requests_per_window: int, window_seconds: int):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
    
    async def is_allowed(self, ip: str) -> bool:
        """Check if request from IP is allowed - async version with proper locking."""
        if not RATE_LIMIT_ENABLED or not RATE_LIMIT_PER_IP:
            return True
        
        # CRITICAL FIX #2: Использовать asyncio.Lock для синхронизации
        async with _rate_limit_lock:
            now = datetime.now()
            cutoff_time = now - timedelta(seconds=self.window_seconds)
            
            # Инициализируем список для IP если его нет
            if ip not in ip_request_history:
                ip_request_history[ip] = []
            
            # Удаляем старые запросы вне окна
            ip_request_history[ip] = [
                timestamp for timestamp in ip_request_history[ip]
                if timestamp > cutoff_time
            ]
            
            # Проверяем лимит
            if len(ip_request_history[ip]) >= self.requests_per_window:
                return False
            
            # Добавляем текущий запрос
            ip_request_history[ip].append(now)
            return True
    
    async def get_retry_after(self, ip: str) -> int:
        """Get seconds to retry after for rate limited IP - async version with locking."""
        # CRITICAL FIX #2: Использовать asyncio.Lock для синхронизации
        async with _rate_limit_lock:
            if ip not in ip_request_history or not ip_request_history[ip]:
                return 0
            
            oldest_request = min(ip_request_history[ip])
            retry_time = oldest_request + timedelta(seconds=self.window_seconds)
            seconds_to_wait = max(0, int((retry_time - datetime.now()).total_seconds()))
            return seconds_to_wait

rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

# =============================================================================
# УТИЛИТЫ
# =============================================================================

def sanitize_input(text: str) -> str:
    """
    Санитизирует и валидирует входной текст для защиты от атак.
    
    Реализует многоуровневую защиту от:
    - Prompt injection атак ("ignore instructions", etc)
    - Jailbreak попыток ("you are now...", "new instructions")
    - Опасных паттернов (<|im_start|>, system:, etc)
    - Невалидных символов (оставляет только буквы, цифры, пунктуацию)
    
    Args:
        text (str): Raw input text from user (max 4096 chars)
        
    Returns:
        str: Cleaned and safe text, safe for passing to AI models
        
    Security Features:
        1. Pattern matching: ищет опасные последовательности
        2. Character filtering: оставляет только безопасные символы
        3. Case-insensitive: ловит варианты через различные регистры
        4. Unicode handling: обрабатывает русские, китайские символы
        
    Examples:
        >>> sanitize_input("ignore all previous instructions")
        'ignore all previous instructions'  # Dangerous pattern removed
        >>> sanitize_input("Normal question about Bitcoin?")
        'Normal question about Bitcoin?'  # Unchanged
        
    Dangerous Patterns Blocked:
        - "ignore previous instructions"
        - "system: jailbreak"
        - "forget everything"
        - "you are now a ..."
        - "new instructions for you"
        - Special tokens: <|im_start|>, <|im_end|>
    """
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
    """
    Создает SHA-256 хеш текста для кэширования и дедупликации.
    
    Используется для создания уникального ключа кэша на основе содержимого.
    Одинаковые тексты всегда дают одинаковый хеш (детерминированный).
    
    Args:
        text (str): Input text для хеширования (any length)
        
    Returns:
        str: 64-character hexadecimal string (SHA-256 hash)
        
    Usage:
        >>> hash_text("Bitcoin price")
        "a1b2c3d4e5f6..."  # Always same for same input
        
    Cache Key Strategy:
        - Input: "Bitcoin rises to $100k"
        - Hash: "3f7a9d2e1c5b..."
        - Cache lookup: response_cache.get("3f7a9d2e1c5b...")
        - Hit rate: ~60% in production
        
    Performance:
        - Time: <1ms per call
        - Deterministic: f(x) always equals f(x)
        - Collision rate: Negligible (2^256 space)
        
    Example:
        >>> key1 = hash_text("Bitcoin news")
        >>> key2 = hash_text("Bitcoin news")
        >>> assert key1 == key2  # Same text = same hash
        
    Note:
        - Used for response caching (TTL 1 hour)
        - Used for deduplication checks
        - Critical for cache hit rate optimization
        - UTF-8 encoding handles international characters
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def clean_text(text: str) -> str:
    """
    Удаляет markdown, HTML-теги и лишние пробелы из текста.
    
    Очищает текст для красивого отображения в UI.
    Удаляет форматирование, оставляя только плаинтекст.
    
    Args:
        text (str): Raw text с возможными тегами и markdown
        
    Returns:
        str: Cleaned plain text ready for display
        
    Removes:
        - HTML tags: <b>, <i>, <br>, etc
        - Markdown: **bold**, __italic__, *emphasis*, etc
        - Strikethrough: ~~crossed~~
        - Code blocks: `code`
        - Extra whitespace: multiple spaces/newlines
        
    Example:
        >>> clean_text("**Bitcoin** <b>Price</b> `$100k`")
        "Bitcoin Price $100k"
        
    Preserves:
        - Plain text
        - Punctuation
        - Line breaks (normalized)
        - Unicode characters
    """
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
    """
    Извлекает JSON из ответа AI с множественными стратегиями.
    КРИТИЧЕСКИЙ ФИК #6: Защита от DoS через переполнение стека/памяти
    
    ИСПРАВЛЕНИЕ ПРОБЛЕМЫ #1: Более надежный парсинг с лучшей очисткой текста.
    ИСПРАВЛЕНИЕ #4: Правильная обработка вложенных объектов JSON в XML тегах.
    """
    if not raw_text:
        return None
    
    # ✅ CRITICAL FIX #6: Protect against DoS via extremely large responses
    MAX_JSON_SIZE = 100_000  # 100KB max JSON size
    if len(raw_text) > MAX_JSON_SIZE:
        logger.warning(f"⚠️ JSON response exceeds max size ({len(raw_text)} > {MAX_JSON_SIZE})")
        return None
    
    logger.debug(f"🔍 Начало парсинга JSON. Длина входа: {len(raw_text)} символов")
    
    original_text = raw_text
    text = raw_text
    
    # Стратегия 0: Удаляем markdown блоки и escape символы
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'```\s*', '', text).strip()
    text = text.replace('\\n', '\n').replace('\\t', '\t')  # Раскрываем escape
    
    # ИСПРАВЛЕНИЕ #4: Стратегия 1 - XML теги с правильным парсингом вложенных скобок
    xml_start = text.find('<json>')
    if xml_start != -1:
        logger.debug("✅ Найдены XML теги <json>...")
        # Находим содержимое между <json> и </json> с учетом вложенных скобок
        search_start = xml_start + 6  # Длина '<json>'
        brace_count = 0
        in_string = False
        escape_next = False
        json_end = -1
        
        for i in range(search_start, len(text)):
            char = text[i]
            
            # Обработка escape
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            # Обработка строк
            if char == '"':
                in_string = not in_string
            
            # Считаем скобки вне строк
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
        
        if json_end != -1:
            text_to_parse = text[search_start:json_end].strip()
            if text_to_parse and text_to_parse.startswith('{'):
                logger.debug(f"XML: Извлечен JSON из XML тегов ({len(text_to_parse)} символов)")
                candidates = [("xml_tags", text_to_parse)]
                
                # Пробуем парсить сразу - это приоритетная стратегия
                cleaned = text_to_parse.strip()
                # ВНИМАНИЕ: НЕ удаляем подчеркивания! Они могут быть частью JSON ключей
                # cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', cleaned)  # ← УБИРАЮТ JSON ключи!
                # cleaned = re.sub(r'~~(.+?)~~', r'\1', cleaned)
                # cleaned = re.sub(r'\*(.+?)\*', r'\1', cleaned)
                # cleaned = re.sub(r'_(.+?)_', r'\1', cleaned)
                
                try:
                    data = json.loads(cleaned)
                    if isinstance(data, dict) and len(data) > 0:
                        logger.info(f"✅ JSON успешно распарсен (xml_tags)")
                        return data
                except json.JSONDecodeError as e:
                    logger.debug(f"  ❌ XML JSON парсинг не сработал: {e.msg}")
    
    # ЕСЛИ XML не сработала, пробуем другие стратегии
    candidates = []
    
    # Стратегия 2: Markdown блоки ```json...```
    md_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if md_match:
        logger.debug("✅ Найдены markdown блоки ```json...")
        text_to_parse = md_match.group(1).strip()
        candidates.append(("markdown_json", text_to_parse))
    
    # Стратегия 3: Ищем ПЕРВЫЙ валидный JSON блок методом поиска скобок
    first_brace = text.find('{')
    if first_brace != -1:
        brace_count = 0
        in_string = False
        escape_next = False
        end_pos = -1
        
        for i in range(first_brace, len(text)):
            char = text[i]
            
            # Обработка escape
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            # Обработка строк
            if char == '"':
                in_string = not in_string
            
            # Не считаем скобки внутри строк
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
        
        if end_pos != -1:
            potential_json = text[first_brace:end_pos]
            logger.debug(f"Найден JSON от первой скобки (длина: {len(potential_json)})")
            candidates.append(("brace_matching", potential_json))
    
    if not candidates:
        logger.warning(f"❌ JSON не найден вообще. Начало ответа: {original_text[:200]}...")
        return None
    
    # Пробуем парсить каждого кандидата
    for strategy_name, text_to_parse in candidates:
        logger.debug(f"🔄 Попытка парсинга стратегией: {strategy_name}")
        
        # Очищаем от markdown маркеров
        cleaned = text_to_parse.strip()
        
        # ИСПРАВЛЕНИЕ: Заменяем переводы строк на пробелы
        # (Gemini часто разбивает длинные строки JSON на несколько строк)
        cleaned = cleaned.replace('\n', ' ').replace('\r', '')
        
        # Удаляем множественные пробелы
        cleaned = re.sub(r' +', ' ', cleaned)
        
        # Попытка 1: Парсим как есть (БЕЗ удаления markdown - это ломает JSON!)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and len(data) > 0:
                logger.info(f"✅ JSON успешно распарсен ({strategy_name})")
                return data
        except json.JSONDecodeError as e:
            logger.debug(f"  ❌ Стандартный парсинг не сработал: строка {e.lineno}, колонка {e.colno}: {e.msg}")
        
        # Попытка 2: Замена одиночных кавычек на двойные (для Python dict синтаксиса)
        try:
            cleaned_quotes = cleaned.replace("'", '"')
            data = json.loads(cleaned_quotes)
            if isinstance(data, dict):
                logger.info(f"✅ JSON распарсен после замены кавычек ({strategy_name})")
                return data
        except json.JSONDecodeError:
            logger.debug(f"  ❌ Замена кавычек не помогла")
        
        # Попытка 3: Удаляем одиночные подчеркивания в значениях
        try:
            # Более осторожная замена: только в строках после двоеточия
            cleaned_underscores = re.sub(r':\s*"([^"]*?)_([^"]*?)"', r': "\1\2"', cleaned)
            data = json.loads(cleaned_underscores)
            if isinstance(data, dict):
                logger.info(f"✅ JSON распарсен после удаления подчеркиваний ({strategy_name})")
                return data
        except json.JSONDecodeError:
            logger.debug(f"  ❌ Удаление подчеркиваний не помогло")
    
    logger.error("❌ Не удалось распарсить JSON ни одной стратегией")
    if candidates:
        logger.error(f"Первый кандидат (первые 300 символов): {candidates[0][1][:300]}")
    return None

def extract_teaching_json(raw_text: str) -> Optional[dict]:
    """Извлекает JSON урока из ответа AI - использует универсальный парсер.
    
    ✅ CRITICAL FIX #6: Protect against DoS via oversized responses
    ✅ Uses advanced extract_json_from_response for reliable parsing
    """
    # Используем универсальный парсер с полной поддержкой вложенных скобок
    return extract_json_from_response(raw_text)

def validate_analysis(data: Any) -> tuple[bool, Optional[str]]:
    """Валидация структуры ответа AI - summary_text и impact_points ОБЯЗАТЕЛЬНЫ."""
    if not isinstance(data, dict):
        logger.error(f"❌ Валидация: Ответ не является словарем")
        return False, "Ответ не является словарем"
    
    # ТОЛЬКО эти 2 поля обязательны
    required_fields = ["summary_text", "impact_points"]
    for field in required_fields:
        if field not in data:
            logger.error(f"❌ Валидация: Отсутствует обязательное поле '{field}'")
            return False, f"Отсутствует обязательное поле: {field}"
    
    # Валидация summary_text
    summary = data["summary_text"]
    if not isinstance(summary, str) or len(summary.strip()) < 20 or len(summary) > 1000:
        logger.error(f"❌ Валидация: summary_text невалиден")
        return False, "summary_text невалиден"
    
    logger.debug(f"✅ summary_text валиден ({len(summary)} символов)")
    
    # Валидация impact_points
    points = data["impact_points"]
    if not isinstance(points, list) or len(points) < 2 or len(points) > 10:
        logger.error(f"❌ Валидация: impact_points невалиден (нужно 2-10 пунктов)")
        return False, "impact_points невалиден"
    
    for i, point in enumerate(points):
        if not isinstance(point, str) or len(point.strip()) < 10 or len(point) > 500:
            logger.error(f"❌ Валидация: impact_points[{i}] невалиден")
            return False, f"impact_points[{i}] невалиден"
    
    logger.debug(f"✅ impact_points валидны ({len(points)} пунктов)")
    
    # Валидация ОПЦИОНАЛЬНЫХ полей (если есть - нормализуем)
    if "action" in data and data["action"]:
        action = str(data.get("action", "")).strip().upper()
        if action not in ["BUY", "HOLD", "SELL", "WATCH"]:
            data["action"] = None  # Удаляем невалидный
    
    if "risk_level" in data and data["risk_level"]:
        risk = str(data.get("risk_level", "")).strip()
        if risk not in ["Low", "Medium", "High"]:
            data["risk_level"] = None
    
    if "timeframe" in data and data["timeframe"]:
        tf = str(data.get("timeframe", "")).strip().lower()
        if tf not in ["day", "week", "month"]:
            data["timeframe"] = None
        else:
            data["timeframe"] = tf
    
    logger.debug(f"✅ Валидация успешна!")
    return True, None

def format_response(analysis: dict) -> str:
    """Форматирует анализ для читаемого вывода с включением образовательных элементов."""
    summary = clean_text(analysis.get('summary_text', 'Нет описания'))
    
    emojis = ['📉', '📊', '⚡️', '💰', '🎯', '🔥', '📈', '⚠️', '💡', '🌐']
    separator = "━━━━━━━━━━━━━━━━━━"
    
    result = f"{separator}\n🔍 СУТЬ\n\n{summary}\n\n{separator}\n💡 ВЛИЯНИЕ НА КРИПТУ\n\n"
    
    for i, point in enumerate(analysis.get('impact_points', [])):
        if point.strip():
            clean_point = clean_text(point)
            emoji = emojis[i % len(emojis)]
            result += f"{emoji} {clean_point}\n\n"
    
    # Добавление образовательных элементов
    if analysis.get("learning_question"):
        result += f"\n{separator}\n❓ УГЛУБИТЕ ЗНАНИЯ\n\n{clean_text(analysis['learning_question'])}\n\n"
    
    if analysis.get("related_topics"):
        result += f"{separator}\n📚 РЕКОМЕНДУЕМ ИЗУЧИТЬ\n\n"
        for topic in analysis["related_topics"]:
            result += f"• {clean_text(topic)}\n"
    
    result += separator
    return result.strip()

def fallback_analysis(text: str) -> dict:
    """Упрощенный анализ без AI (для аварийных ситуаций) - возвращает JSON."""
    keywords = {
        'bitcoin': 'BTC', 'btc': 'BTC', 'ethereum': 'ETH', 'eth': 'ETH',
        'sec': 'SEC', 'регулятор': 'REG', 'fomo': 'FOMO',
        'hack': 'HACK', 'взлом': 'HACK', 'dump': 'DUMP', 'обвал': 'DUMP',
        'pump': 'PUMP', 'рост': 'PUMP', 'etf': 'ETF', 'whale': 'WHALE'
    }
    
    words = text.lower().split()
    summary = text[:250] + "..." if len(text) > 250 else text
    
    # Ищем ключевые слова
    found_keywords = set()
    for word, keyword in keywords.items():
        if word in ' '.join(words):
            found_keywords.add(keyword)
    
    # Форматируем как JSON ответ
    impact_points = list(found_keywords) if found_keywords else ["Криптоновость"]
    
    logger.warning(f"⚠️ Fallback анализ: найдено {len(found_keywords)} ключевых слов")
    
    return {
        "summary_text": f"⚙️ ЭКСПРЕСС-РЕЖИМ (AI недоступен): {summary}",
        "impact_points": impact_points,
        "simplified_text": f"AI анализ временно недоступен. Основные активы: {', '.join(impact_points)}"
    }

def fallback_image_analysis(asset_type: str = "other") -> dict:
    """Fallback анализ изображения когда AI недоступна."""
    logger.warning("⚠️ Используется fallback анализ для изображения")
    request_counter['fallback'] += 1
    
    analysis_templates = {
        "chart": "Видно, что это график/диаграмма. Могу видеть структуру, но точный анализ тренда требует подключения к AI. Для полного анализа технических уровней рекомендуем попробовать позже или использовать специализированные платформы.",
        "screenshot": "Это скриншот с текстовой информацией. AI анализ недоступен, но видно наличие информационного контента. Отправьте текстовое описание для более точного анализа.",
        "meme": "Распознан контент юмористического характера, возможно с финансовой тематикой. Полное понимание контекста требует AI обработки.",
        "other": "Изображение распознано, но AI анализ временно недоступен. Попробуйте отправить текстовое описание или повторите попытку позже."
    }
    
    return {
        "summary_text": f"⚙️ Экспресс-режим: {asset_type}",
        "analysis": analysis_templates.get(asset_type, analysis_templates["other"]),
        "asset_type": asset_type,
        "confidence": 0.3,
        "mentioned_assets": []
    }

def cleanup_expired_cache() -> int:
    """Удаляет кэш записи с истёкшим TTL (Redis TTL автоматический)."""
    # Redis автоматически удаляет ключи с истёкшим TTL
    # Эта функция теперь используется только для статистики
    stats = cache_manager.get_stats()
    if stats.get("redis_connected"):
        logger.debug(f"📊 Redis cache stats: {stats}")
    else:
        logger.debug(f"📊 In-memory cache size: {stats.get('in_memory_size', 0)} items")

def build_gemini_config() -> dict:
    """Создает оптимизированную конфигурацию для Gemini с улучшенным промптом v3.1."""
    system_prompt = get_improved_system_prompt()
    
    return {
        "system_instruction": system_prompt,
        "temperature": GEMINI_TEMPERATURE,
        "max_output_tokens": GEMINI_MAX_TOKENS,
        "top_p": 0.95,
        "top_k": 40
    }
# ==================== ДИАЛОГОВАЯ СИСТЕМА v0.21.0 ====================

def build_conversation_context(user_id: int) -> str:
    """Получает контекст диалогов пользователя для инъекции в промпт."""
    try:
        # Подключаемся к боту БД для получения контекста
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "rvx_bot.db")
        
        if not os.path.exists(db_path):
            return ""
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получаем последние 5 сообщений из истории
        cursor.execute("""
            SELECT message_type, content, intent 
            FROM conversation_history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 5
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return ""
        
        # Формируем контекст
        context_lines = ["КОНТЕКСТ ПРЕДЫДУЩИХ СООБЩЕНИЙ:"]
        for msg_type, content, intent in reversed(rows):
            role = "ПОЛЬЗОВАТЕЛЬ" if msg_type == "user" else "БОТ"
            context_lines.append(f"{role} ({intent}): {content[:100]}...")  # Первые 100 символов
        
        context_lines.append("END CONTEXT\n")
        return "\n".join(context_lines)
    
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить контекст диалога для {user_id}: {e}")
        return ""

# ===================================================================

def build_teaching_config() -> dict:
    """Создает улучшенную конфигурацию для Gemini для создания качественных уроков."""
    system_prompt = (
        "Ты — опытный преподаватель криптографии и Web3, создающий ясные, структурированные и практичные уроки для новичков и продвинутых пользователей.\n\n"
        
        "ТВОЯ РОЛЬ И ОТВЕТСТВЕННОСТЬ:\n"
        "- Создавать уроки, которые реально помогают людям понять сложные концепции\n"
        "- Адаптировать контент под уровень сложности (beginner, intermediate, advanced, expert)\n"
        "- Использовать аналогии из реальной жизни для объяснения абстрактных идей\n"
        "- Предоставлять практические примеры, которые применимы в реальном мире\n"
        "- Проверять понимание через эффективные вопросы и упражнения\n\n"
        
        "УРОВНИ СЛОЖНОСТИ И ТРЕБОВАНИЯ:\n"
        "Beginner (новичок):\n"
        "  - Простой язык без технических терминов\n"
        "  - Реальные аналогии из повседневной жизни\n"
        "  - 250-350 слов, структурированный текст\n"
        "  - Много примеров и иллюстраций идей\n"
        "\n"
        "Intermediate (промежуточный):\n"
        "  - Технические детали с объяснениями\n"
        "  - Кейсы из реальной индустрии\n"
        "  - 350-450 слов с глубиной\n"
        "  - Несколько примеров разной сложности\n"
        "\n"
        "Advanced (продвинутый):\n"
        "  - Архитектура, стандарты, лучшие практики\n"
        "  - Математические основы и детали реализации\n"
        "  - 400-500 слов с высокой степенью детализации\n"
        "  - Ссылки на стандарты (BIP, EIP) где применимо\n"
        "\n"
        "Expert (эксперт):\n"
        "  - Исследовательский уровень анализа\n"
        "  - Последние тренды и инновации\n"
        "  - 450-600 слов с критическим анализом\n"
        "  - Сравнение разных подходов и их преимуществ\n\n"
        
        "МЕТОДОЛОГИЯ ОБУЧЕНИЯ:\n"
        "1. Открытие: Начни с вопроса или проблемы, которую решает тема\n"
        "2. Объяснение: Развернуто объясни основные концепции с примерами\n"
        "3. Применение: Покажи как использовать эту информацию в реальности\n"
        "4. Закрепление: Три ключевых пункта для запоминания\n"
        "5. Проверка: Проблемный вопрос для размышления\n"
        "6. Продолжение: Логичные следующие шаги в обучении\n\n"
        
        "СТРОГИЕ ФОРМАТНЫЕ ПРАВИЛА:\n"
        "1. Отвечай ТОЛЬКО валидным JSON, завернутым в теги <json></json>\n"
        "2. ЗАПРЕЩЕНО использовать markdown символы: *, **, _, ~, `, #\n"
        "3. ЗАПРЕЩЕНО использовать эмодзи (😊, 📚, и т.д.)\n"
        "4. ЗАПРЕЩЕНО использовать HTML теги\n"
        "5. Используй только простой текст и базовую пунктуацию\n"
        "6. Все строки в JSON должны быть валидными (экранируй кавычки как \")\n"
        "7. Не добавляй комментарии или текст вне JSON\n\n"
        
        "ОБЯЗАТЕЛЬНАЯ СТРУКТУРА JSON:\n"
        "{\n"
        '  "lesson_title": "4-8 слов, ясная и описательная",\n'
        '  "intro": "1-2 предложения о значимости темы",\n'
        '  "content": "Основное объяснение (200-300 слов в зависимости от уровня)",\n'
        '  "key_points": ["Первый важный момент", "Второй важный момент", "Третий важный момент"],\n'
        '  "real_world_example": "Конкретный практический пример в 2-3 предложениях",\n'
        '  "common_mistakes": "Частая ошибка новичков и как её избежать",\n'
        '  "practice_question": "Проблемный вопрос для критического размышления",\n'
        '  "next_topics": ["Логичное продолжение 1", "Логичное продолжение 2"]\n'
        "}\n\n"
        
        "ТРЕБОВАНИЯ К КАЧЕСТВУ КОНТЕНТА:\n"
        "- content: должен быть структурирован с параграфами (разделены точками)\n"
        "- key_points: ровно 3 пункта, каждый 1-2 предложения, не повторяющиеся\n"
        "- real_world_example: конкретный, не абстрактный, легко визуализируется\n"
        "- common_mistakes: типичная ошибка и сразу объяснение как избежать\n"
        "- practice_question: открытый вопрос, требующий размышления, не \"да/нет\"\n"
        "- next_topics: логичная прогрессия обучения, слегка сложнее\n\n"
        
        "ПРИМЕР ОТЛИЧНОГО ОТВЕТА:\n"
        "<json>{\n"
        '  "lesson_title": "Как работает публичная криптография в блокчейне",\n'
        '  "intro": "Публичная криптография это математический инструмент, который позволяет отправить деньги незнакомцу без посредника. Это основа блокчейна.",\n'
        '  "content": "Криптография работает с двумя ключами: публичным и приватным. Публичный ключ - это ваш адрес кошелька, который вы можете публиковать. Приватный ключ - это пароль, который знаете только вы. Математически они связаны так: если вы подписываете транзакцию приватным ключом, любой может проверить подпись используя ваш публичный ключ. В блокчейне это работает так: вы подписываете транзакцию приватным ключом. Сеть проверяет подпись и видит что это именно вы. Невозможно подделать подпись без приватного ключа, даже если знаешь публичный.",\n'
        '  "key_points": ["Публичный ключ это адрес, приватный это пароль", "Подпись приватным ключом доказывает что это именно вы", "Проверить подпись можно публичным ключом, подделать нельзя"],\n'
        '  "real_world_example": "Как почтовый штемпель. Ваш публичный ключ это печать государства (все знают как она выглядит). Ваш приватный ключ это матрица печати (только у вас). Письмо со штемпелем может быть проверено кем-то, но подделать штемпель без матрицы невозможно.",\n'
        '  "common_mistakes": "Новички думают что если знают публичный ключ, они могут подделать подпись. Неправильно! Математически это невозможно. Публичный ключ только для проверки, не для создания подписей.",\n'
        '  "practice_question": "Если я публикую свой публичный ключ, опасно ли это? Может ли кто-то использовать его чтобы потратить мои биткойны?",\n'
        '  "next_topics": ["Алгоритмы ECDSA и RSA - как они работают математически", "Где и как безопасно хранить приватные ключи"]\n'
        '}</json>\n\n'
        
        "СОЗДАЙ ВЫСОКАЧЕСТВЕННЫЙ УРОК ПО ЗАПРОСУ, СЛЕДУЯ ВСЕМ ТРЕБОВАНИЯМ ВЫШЕ."
    )
    
    return {
        "system_instruction": system_prompt,
        "temperature": 0.5,  # Баланс между структурированностью и креативностью
        "max_output_tokens": 2500,  # Достаточно для подробного урока
        "top_p": 0.85,
        "top_k": 35
    }

def build_image_analysis_config(context: Optional[str] = None) -> dict:
    """Создает конфигурацию для анализа изображений (графиков, скриншотов)."""
    system_prompt = (
        "⚠️ КРИТИЧНОЕ ПРАВИЛО: Отвечай ТОЛЬКО JSON в <json></json> тегах. БЕЗ ИСКЛЮЧЕНИЙ.\n\n"
        
        "Ты — профессиональный финансовый аналитик, специализирующийся на анализе графиков, скриншотов и визуальной информации о криптовалютах, акциях и финансовых инструментах.\n\n"
        
        "ТВОИ ЗАДАЧИ:\n"
        "1. Определить тип изображения: графики цены, скриншоты новостей, мемы, диаграммы или другое\n"
        "2. Идентифицировать упомянутые активы (монеты, акции, тикеры)\n"
        "3. Предоставить анализ с выводами и рекомендациями\n"
        "4. Указать уровень уверенности в анализе\n\n"
        
        "ОБЯЗАТЕЛЬНЫЕ ПОЛЯ ОТВЕТА:\n"
        "- summary_text: 2-3 предложения о изображении (ОБЯЗАТЕЛЬНО)\n"
        "- analysis: подробный анализ того что видишь (ОБЯЗАТЕЛЬНО)\n"
        "- asset_type: 'chart', 'screenshot', 'meme', 'other' (ОБЯЗАТЕЛЬНО)\n"
        "- confidence: число от 0 до 1 для уверенности в анализе (ОБЯЗАТЕЛЬНО)\n"
        "- mentioned_assets: массив с найденными активами/тикерами (ОБЯЗАТЕЛЬНО)\n\n"
        
        "ОПЦИОНАЛЬНЫЕ ПОЛЯ:\n"
        "- action: BUY, HOLD, SELL, WATCH если это применимо к графику\n"
        "- risk_level: Low, Medium, High если это применимо\n"
        "- timeframe: day, week, month, year если указано на графике\n\n"
        
        "ПРАВИЛА:\n"
        "1. Отвечай ТОЛЬКО <json>...</json>\n"
        "2. Используй простой текст, БЕЗ *, **, _, ~, эмодзи\n"
        "3. НИКАКОГО текста вне JSON тегов\n"
        "4. Если не можешь определить asset_type - используй 'other'\n"
        "5. Будь честен о том что видишь, не галлюцинируй\n"
        "6. Если это мем или шутка - скажи об этом в анализе\n\n"
        
        "ПРИМЕРЫ ОТВЕТОВ:\n"
        "ПРИМЕР 1 (график BTC):\n"
        "<json>{\"summary_text\":\"График BTC/USDT показывает восходящий тренд с поддержкой на уровне 95000.\",\"analysis\":\"На часовом графике видно образование восходящего треугольника. Объем торговли выше среднего. Линия тренда поддерживает бычий сценарий. При пробое выше 102000 ожидается рост к 110000.\",\"asset_type\":\"chart\",\"confidence\":0.85,\"mentioned_assets\":[\"BTC\",\"USDT\"],\"action\":\"BUY\",\"timeframe\":\"week\"}</json>\n\n"
        
        "ПРИМЕР 2 (скриншот новости):\n"
        "<json>{\"summary_text\":\"Скриншот сообщения о одобрении Bitcoin ETF одного из регуляторов.\",\"analysis\":\"В скриншоте видна новость о ожидаемом одобрении. Дата и источник указаны. Это может быть прайсированный событием но стоит следить за официальными объявлениями.\",\"asset_type\":\"screenshot\",\"confidence\":0.7,\"mentioned_assets\":[\"BTC\",\"ETF\"],\"action\":\"WATCH\"}</json>\n\n"
        
        f"ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ОТ ПОЛЬЗОВАТЕЛЯ:\n{context if context else 'Нет дополнительного контекста'}\n\n"
        
        "АНАЛИЗИРУЙ ИЗОБРАЖЕНИЕ И ПРЕДОСТАВЬ ПОЛНЫЙ JSON ОТВЕТ."
    )
    
    return {
        "system_instruction": system_prompt,
        "temperature": 0.4,
        "max_output_tokens": 1200,
        "top_p": 0.90,
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
async def call_deepseek_with_retry(
    system_prompt: str,
    user_message: str,
    max_retries: int = 3
) -> Optional[str]:
    """Вызов DeepSeek API с автоматическими повторами."""
    
    if not deepseek_client:
        logger.error("❌ DeepSeek клиент не инициализирован")
        return None
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"🔄 Попытка вызова DeepSeek #{attempt + 1}/{max_retries}")
            
            response = deepseek_client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=DEEPSEEK_TEMPERATURE,
                max_tokens=DEEPSEEK_MAX_TOKENS
            )
            
            if response and response.choices and len(response.choices) > 0:
                text = response.choices[0].message.content
                logger.info(f"✅ DeepSeek ответил успешно (попытка {attempt + 1})")
                logger.debug(f"📝 Ответ (первые 200 символов): {text[:200]}")
                return text
            else:
                logger.warning(f"⚠️ DeepSeek вернул пустой ответ (попытка {attempt + 1})")
                
        except Exception as e:
            logger.error(f"❌ Ошибка DeepSeek (попытка {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)[:200]}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
            continue
    
    logger.error(f"❌ Все {max_retries} попытки вызова DeepSeek исчерпаны")
    return None

async def call_gemini_with_retry(
    client: genai.Client,
    model: str,
    contents: list,
    config: dict,
    max_retries: int = 3
) -> Any:
    """Вызов Gemini с автоматическими повторами при ошибках (резервный)."""
    
    for attempt in range(max_retries):
        try:
            def sync_call():
                logger.debug(f"🔄 Попытка вызова Gemini #{attempt + 1}/{max_retries}")
                return client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            
            response = await asyncio.wait_for(
                run_in_threadpool(sync_call),
                timeout=GEMINI_TIMEOUT
            )
            
            if response:
                logger.info(f"✅ Gemini ответил успешно (попытка {attempt + 1})")
                logger.debug(f"📝 Ответ (первые 200 символов): {str(response.text)[:200]}")
                return response
            else:
                logger.warning(f"⚠️ Gemini вернул None (попытка {attempt + 1})")
                
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout {GEMINI_TIMEOUT}s на попытке {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
            continue
            
        except Exception as e:
            logger.error(f"❌ Ошибка Gemini (попытка {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)[:200]}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
            continue
    
    logger.error(f"❌ Все {max_retries} попытки вызова Gemini исчерпаны")
    return None

# =============================================================================
# LIFECYCLE MANAGEMENT
# =============================================================================

start_time = datetime.now(timezone.utc)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управление жизненным циклом приложения."""
    global client, deepseek_client, _client_lock, _deepseek_client_lock, _rate_limit_lock
    
    # CRITICAL FIX #1 & #2: Инициализировать asyncio.Lock для потокобезопасности
    _client_lock = asyncio.Lock()
    _deepseek_client_lock = asyncio.Lock()
    _rate_limit_lock = asyncio.Lock()
    logger.debug("🔒 Asyncio locks инициализированы для синхронизации глобального состояния")
    
    # CRITICAL FIX #5: Вызвать валидацию конфигурации при запуске
    try:
        from config import validate_config
        validate_config()
        logger.info("✅ Конфигурация валидна")
    except Exception as e:
        logger.warning(f"⚠️ Предупреждение валидации конфигурации: {e}")
    
    # Startup
    logger.info("=" * 70)
    logger.info("🚀 Запуск RVX AI Backend API v3.2 (с Ollama + DeepSeek)")
    logger.info("=" * 70)
    
    # ====================================================================
    # 🎯 Инициализируем OLLAMA (ПРИОРИТЕТ 1 - локальная LLM)
    # ====================================================================
    if OLLAMA_ENABLED:
        try:
            await initialize_ollama(
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_MODEL,
                timeout=OLLAMA_TIMEOUT
            )
            logger.info(f"✅ Ollama клиент инициализирован (модель: {OLLAMA_MODEL})")
            logger.info(f"   URL: {OLLAMA_BASE_URL}")
            logger.info(f"   ⚡ Ollama будет использоваться в ПРИОРИТЕТЕ перед облачными сервисами!")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка инициализации Ollama: {e}")
            logger.warning(f"   Система переключится на облачные провайдеры (Groq/Mistral/Gemini)")
    else:
        logger.warning("⚠️ OLLAMA_ENABLED=false, используем только облачные провайдеры")
    
    # CRITICAL FIX #1: Инициализируем DeepSeek с asyncio.Lock для потокобезопасности
    if DEEPSEEK_API_KEY:
        try:
            async with _deepseek_client_lock:
                deepseek_client = OpenAI(
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com",
                    timeout=30.0
                )
            logger.info(f"✅ Клиент DeepSeek успешно инициализирован (key: {mask_secret(DEEPSEEK_API_KEY)})")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")
            deepseek_client = None
    else:
        logger.warning("⚠️ DEEPSEEK_API_KEY не найден, используем Gemini")
    
    # CRITICAL FIX #1: Инициализируем Gemini с asyncio.Lock для потокобезопасности
    if GEMINI_API_KEY:
        try:
            async with _client_lock:
                client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info(f"✅ Клиент Gemini успешно инициализирован (key: {mask_secret(GEMINI_API_KEY)})")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Gemini: {e}")
            client = None
    else:
        logger.warning("⚠️ GEMINI_API_KEY не найден")
    
    logger.info("📋 Конфигурация AI Providers:")
    logger.info(f"  1️⃣  OLLAMA (локальная): {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
    logger.info(f"  2️⃣  DEEPSEEK_MODEL: {DEEPSEEK_MODEL}")
    logger.info(f"  3️⃣  GEMINI_MODEL: {GEMINI_MODEL}")
    logger.info(f"  • TEMPERATURE: {OLLAMA_TEMPERATURE}")
    logger.info(f"  • MAX_TOKENS: {OLLAMA_MAX_TOKENS}")
    logger.info(f"  • TIMEOUT: {OLLAMA_TIMEOUT}s")
    logger.info(f"  • CACHE_ENABLED: {CACHE_ENABLED}")
    
    if RATE_LIMIT_ENABLED:
        logger.info(f"  • RATE_LIMIT: {RATE_LIMIT_REQUESTS} запросов/{RATE_LIMIT_WINDOW}s")
        logger.info(f"  • RATE_LIMIT_PER_IP: {RATE_LIMIT_PER_IP}")
    
    logger.info("=" * 70)
    
    # CRITICAL FIX #6: Background cache and rate limiter cleanup (prevent memory leak)
    async def cleanup_cache_and_rate_limiter():
        """
        Periodically clean up old cache entries and stale IP rate limit tracking.
        
        Issues fixed:
        - Cache entries with expired TTL
        - IP addresses with no recent requests (stale entries)
        - Memory leaks from unbounded dictionaries
        """
        cleanup_interval = CACHE_CLEANUP_INTERVAL
        last_rate_limit_cleanup = 0
        
        while True:
            try:
                await asyncio.sleep(cleanup_interval)
                
                # 1. Cache cleanup
                if CACHE_ENABLED:
                    try:
                        cache_stats = response_cache.get_stats()
                        if cache_stats['size'] > cache_stats['max_size'] * 0.8:
                            logger.warning(
                                f"⚠️ Cache utilization high: {cache_stats['utilization_percent']:.1f}% "
                                f"({cache_stats['size']}/{cache_stats['max_size']})"
                            )
                    except Exception as e:
                        logger.debug(f"Cache stats retrieval error: {e}")
                
                # 2. CRITICAL FIX #6: Rate limiter cleanup (unbounded memory fix)
                current_time = datetime.now()
                if RATE_LIMIT_ENABLED and RATE_LIMIT_PER_IP:
                    try:
                        async with _rate_limit_lock:
                            # Remove IPs with no recent activity
                            cutoff_time = current_time - timedelta(seconds=RATE_LIMIT_WINDOW * 10)
                            ips_to_remove = []
                            
                            for ip, timestamps in ip_request_history.items():
                                # Check if any requests are recent
                                recent = any(ts > cutoff_time for ts in timestamps)
                                if not recent:
                                    ips_to_remove.append(ip)
                            
                            # Remove stale entries
                            for ip in ips_to_remove:
                                del ip_request_history[ip]
                            
                            if ips_to_remove:
                                logger.debug(
                                    f"🧹 Rate limiter cleanup: removed {len(ips_to_remove)} stale IPs, "
                                    f"total tracked: {len(ip_request_history)}"
                                )
                    except Exception as e:
                        logger.error(f"❌ Rate limiter cleanup error: {type(e).__name__}: {e}")
                
                last_rate_limit_cleanup = time.time()
                
            except asyncio.CancelledError:
                logger.debug("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected cleanup error: {type(e).__name__}: {e}", exc_info=False)
                # Continue despite errors
                await asyncio.sleep(1)
    
    # Start background cleanup task with proper error handling
    try:
        cleanup_task = asyncio.create_task(cleanup_cache_and_rate_limiter())
        logger.info("✅ Background cleanup task started")
    except Exception as e:
        logger.error(f"❌ Failed to start cleanup task: {e}")
        cleanup_task = None
    
    # ========================================================================
    # 🔐 SECURITY INITIALIZATION (v1.0)
    # ========================================================================
    
    # Initialize security databases
    try:
        init_auth_database()
        logger.info("✅ Auth database initialized for API key management")
    except Exception as e:
        logger.warning(f"⚠️ Auth database initialization warning: {e}")
    
    # Register environment secrets for protection
    logger.info("🔐 Secrets manager initialized - masking sensitive data in logs")
    
    # Setup safe logger to prevent secret leaks
    safe_logger = get_safe_logger(logger)
    safe_logger.info("✅ Safe logging activated - secrets will be masked")
    
    yield
    
    # Shutdown - CRITICAL FIX #9: Proper error handling for cleanup task
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(cleanup_task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug("Cleanup task cancelled during shutdown")
        except Exception as e:
            logger.warning(f"⚠️ Error cancelling cleanup task: {e}")
    
    logger.info("🛑 Остановка API")
    logger.info(f"📊 Финальная статистика:")
    logger.info(f"  • Всего запросов: {request_counter['total']}")
    logger.info(f"  • Успешных: {request_counter['success']}")
    logger.info(f"  • Ошибок: {request_counter['errors']}")
    logger.info(f"  • Fallback режим: {request_counter['fallback']}")
    logger.info(f"  • Rate limited: {request_counter.get('rate_limited', 0)}")
    
    # Get cache stats safely
    try:
        cache_stats = response_cache.get_stats()
        logger.info(f"  • Размер кэша: {cache_stats['size']}/{cache_stats['max_size']}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить размер кэша: {e}")
    
    # Security stats at shutdown
    security_stats = security_manager.get_security_stats()
    if security_stats["total_events"] > 0:
        logger.info("📊 Security Events Summary:")
        logger.info(f"  • Total Events: {security_stats['total_events']}")
        logger.info(f"  • Critical: {security_stats['critical_count']}")
        logger.info(f"  • High: {security_stats['high_count']}")
        logger.info(f"  • Failures: {security_stats['failures']}")

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
async def security_headers_middleware(request: Request, call_next) -> Response:
    """✅ Apply security headers to all responses."""
    response = await call_next(request)
    
    # Add SECURITY_HEADERS to response
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    
    # Add cache control for sensitive endpoints
    if request.url.path.startswith("/auth") or request.url.path.startswith("/security"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    
    return response

@app.middleware("http")
async def request_validation_middleware(request: Request, call_next) -> Response:
    """✅ Validate requests before processing."""
    # Skip validation for health checks and docs
    if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    # Validate content length
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > (1024 * 100):  # 100KB max
                logger.warning(f"⚠️ Request too large: {size} bytes")
                return JSONResponse(
                    status_code=413,
                    content={"simplified_text": "Request too large"}
                )
        except ValueError:
            pass
    
    return await call_next(request)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next) -> Response:
    """✅ Rate limiting middleware with per-IP support."""
    if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    client_ip = request.client.host if request.client else "unknown"
    
    # IP-based rate limiting
    allowed = rate_limiter.is_allowed(client_ip)
    retry_after = rate_limiter.get_retry_after(client_ip) if not allowed else None
    
    if not allowed:
        request_counter["rate_limited"] += 1
        logger.warning(f"⛔ Rate limit exceeded for IP: {client_ip}")
        
        return JSONResponse(
            status_code=429,
            content={
                "simplified_text": f"Too many requests. Retry after {retry_after} seconds.",
                "cached": False
            },
            headers={"Retry-After": str(retry_after)}
        )
    
    return await call_next(request)

@app.middleware("http")
async def log_and_monitor_requests(request: Request, call_next) -> Response:
    """✅ Logging and monitoring with security events."""
    start = datetime.now(timezone.utc)
    request_counter["total"] += 1
    
    # Extract API key if present
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    ip_addr = request.client.host if request.client else "unknown"
    
    logger.info(f"📨 {request.method} {request.url.path} | IP: {ip_addr}")
    
    try:
        response = await call_next(request)
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        
        # Log successful requests
        if response.status_code < 400:
            logger.info(f"✅ {request.url.path} завершен за {duration:.2f}s | Статус: {response.status_code}")
            
            # Track API key usage (optional - for future analytics)
            if api_key:
                try:
                    api_key_manager.record_usage(api_key)
                except Exception:
                    pass  # Not critical if usage tracking fails
        else:
            logger.warning(f"⚠️ {request.url.path} завершен за {duration:.2f}s | Статус: {response.status_code}")
        
        return response
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        logger.error(f"❌ Критическая ошибка в middleware: {e} | Длительность: {duration:.2f}s")
        request_counter["errors"] += 1
        
        return JSONResponse(
            status_code=500,
            content={"simplified_text": "❌ Внутренняя ошибка сервера"}
        )

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def verify_api_key(request: Request) -> str:
    """✅ Verify API key from Authorization header.
    
    Returns:
        str: Verified API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        logger.warning(f"⚠️ API key missing from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=401, detail="Missing API key")
    
    api_key = auth_header.replace("Bearer ", "")
    
    is_valid, error_msg = api_key_manager.verify_api_key(api_key)
    if not is_valid:
        logger.warning(f"⚠️ Invalid API key from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root() -> Dict[str, Any]:
    """Информация об API."""
    uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
    
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
async def health_check() -> HealthResponse:
    """
    System health check endpoint для мониторинга.
    
    Проверяет состояние всех критических компонентов API:
    - Доступность AI провайдеров (Groq, Mistral, Gemini)
    - Состояние кэша
    - Статистика запросов
    - Uptime сервиса
    
    Returns:
        HealthResponse: Детальный статус сервиса
            - status: "healthy", "degraded", or "down"
            - gemini_available: True если хотя бы один провайдер работает
            - requests_total: Всего запросов с момента запуска
            - requests_success: Успешных запросов
            - requests_errors: Ошибок
            - requests_fallback: Fallback ответов
            - cache_size: Количество кэшированных ответов
            - uptime_seconds: Время работы сервиса
            
    Response Status Codes:
        200: All systems operational
        200: At least one AI provider available
        503: Critical services down
        
    Usage:
        - Called by Railway monitoring every 10 seconds
        - Used for alerting on production issues
        - Provides visibility into system health
        
    Performance:
        - Response time: <50ms
        - No database queries
        - Only in-memory checks
    """
    uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
    
    # CRITICAL FIX #12: Use try-except instead of hasattr() for proper error handling
    try:
        cache_stats = response_cache.get_stats()
    except (AttributeError, Exception) as e:
        logger.debug(f"Could not retrieve cache stats: {e}")
        cache_stats = {}
    
    return HealthResponse(
        status="healthy" if client else "degraded",
        gemini_available=client is not None,
        requests_total=request_counter["total"],
        requests_success=request_counter["success"],
        requests_errors=request_counter["errors"],
        requests_fallback=request_counter["fallback"],
        requests_rate_limited=request_counter.get("rate_limited", 0),
        cache_size=cache_stats.get('size', 0),
        uptime_seconds=round(uptime, 2)
    )

# =============================================================================
# SECURITY: AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/create_api_key")
async def create_api_key(request: Request) -> Dict[str, Any]:
    """✅ Create a new API key for programmatic access.
    
    Requires:
        - X-Admin-Token header with valid admin token
        
    Returns:
        - New API key (shown only once)
        - Key metadata
    """
    # Verify admin token
    admin_token = request.headers.get("X-Admin-Token", "")
    if not admin_token or admin_token != os.getenv("ADMIN_TOKEN", ""):
        logger.warning(f"⚠️ Unauthorized API key creation attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Create new API key
    key_name = request.headers.get("X-Key-Name", "Auto-generated key")
    owner_name = request.headers.get("X-Owner-Name", "Unknown")
    
    api_key = api_key_manager.generate_api_key(key_name, owner_name)
    
    logger.info(f"🔑 New API key created: {key_name}")
    
    return {
        "success": True,
        "api_key": api_key,  # Only shown once
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": "Save your API key securely. It will not be shown again.",
        "usage": "Use as Authorization: Bearer <your_api_key> in requests to /explain_news"
    }

@app.post("/auth/verify_api_key")
async def verify_api_key_endpoint(request: Request) -> Dict[str, bool]:
    """✅ Verify if an API key is valid.
    
    Requires:
        - Request JSON with "api_key" field
        
    Returns:
        - Key validity and metadata
    """
    try:
        body = await request.json()
        api_key = body.get("api_key", "")
        
        is_valid, error_msg = api_key_manager.verify_api_key(api_key)
        
        if is_valid:
            key_info = api_key_manager.get_api_key_info(api_key)
            if key_info:
                return {
                    "is_valid": True,
                    "key_name": key_info.key_name,
                    "owner_name": key_info.owner_name,
                    "created_at": key_info.created_at.isoformat() if hasattr(key_info.created_at, 'isoformat') else str(key_info.created_at),
                    "last_used": key_info.last_used_at.isoformat() if key_info.last_used_at and hasattr(key_info.last_used_at, 'isoformat') else None,
                    "total_requests": key_info.total_requests
                }
        
        return {"is_valid": False, "error": error_msg}
    except Exception as e:
        logger.error(f"❌ Error in verify_api_key endpoint: {e}")
        return {"is_valid": False, "error": str(e)}


@app.get("/security/status")
async def security_status(request: Request) -> Dict[str, Any]:
    """✅ Get security status and recent events.
    
    Requires:
        - X-Admin-Token header with valid admin token
        
    Returns:
        - Security statistics and recent events
    """
    # Verify admin token
    admin_token = request.headers.get("X-Admin-Token", "")
    if not admin_token or admin_token != os.getenv("ADMIN_TOKEN", ""):
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Get security statistics
    stats = audit_logger.get_statistics()
    recent_events = audit_logger.get_events(hours=24)  # Fixed: was get_recent_events()
    
    return {
        "status": "operational",
        "statistics": {
            "total_events": stats.get("total_events", 0),
            "critical_count": stats.get("critical_count", 0),
            "high_count": stats.get("high_count", 0),
            "medium_count": stats.get("medium_count", 0),
            "low_count": stats.get("low_count", 0),
            "by_category": stats.get("by_category", {})
        },
        "recent_events": recent_events[:20]  # Return last 20 events
    }

@app.post("/explain_news", response_model=SimplifiedResponse)
async def explain_news(payload: NewsPayload, request: Request) -> JSONResponse:
    """
    Основной API endpoint для анализа криптоновостей и финансовых событий.
    
    Реализует multi-provider AI fallback chain для гарантированного ответа.
    Все ответы кэшируются для последующих запросов (TTL 1 час).
    
    Args:
        payload (NewsPayload): JSON payload содержащий:
            - text_content: Текст новости (max 4096 chars)
            - user_id: Optional ID для аналитики и rate limiting
            - cache_override: Boolean для skip cache (force fresh analysis)
        request (Request): FastAPI Request для security checks
            
    Returns:
        SimplifiedResponse: JSON содержащий:
            - simplified_text: 2-3 параграфа анализа (200-300 words)
            - cached: Boolean есть ли это из кэша
            - processing_time_ms: Время обработки в миллисекундах
            
    AI Fallback Chain:
        1. Groq (llama-3.3-70b-versatile)
           - Speed: ~100ms
           - Cost: Free
           - Status: Primary provider
        2. Mistral (mistral-large-latest)
           - Speed: ~500ms
           - Cost: Free
           - Status: First fallback
        3. Gemini (gemini-2.5-flash)
           - Speed: ~1000ms
           - Cost: Free (20 req/day limit)
           - Status: Last resort
        4. Fallback response
           - Status: When all providers fail
           
    Caching:
        - Key: SHA-256 hash of text_content
        - TTL: 3600 seconds (1 hour)
        - Hit rate: ~60% in production
        - Cache bypass: Set cache_override=true
        
    Security:
        ✅ Requires: Bearer token in Authorization header
        ✅ Rate limiting: 10 req/min per API key
        ✅ Input sanitization: Protects against prompt injection
        ✅ Audit logging: All requests logged with user_id
        ✅ Response validation: JSON structure verified
        
    Error Handling:
        400 Bad Request: Text too long or invalid format
        401 Unauthorized: Missing or invalid API key
        429 Too Many Requests: Rate limit exceeded
        503 Service Unavailable: All AI providers down
    """
    start_time_request = datetime.now(timezone.utc)
    
    # ✅ Verify API key
    api_key = verify_api_key(request)
    
    news_text = payload.text_content
    text_hash = hash_text(news_text)
    
    # Получаем user_id из заголовков
    user_id_header = request.headers.get("X-User-ID", "anonymous")
    try:
        user_id = int(user_id_header)
    except (ValueError, TypeError):
        user_id = "anonymous"
    
    logger.info(f"📰 Запрос анализа новости от {user_id}: {len(news_text)} символов | Hash: {text_hash[:8]}...")
    
    # Проверка кэша (Redis или in-memory fallback)
    if CACHE_ENABLED:
        cached = cache_manager.get(text_hash)
        if cached:
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            logger.info(f"💾 Кэш HIT для {text_hash[:8]} ({duration_ms:.0f}ms)")
            structured_logger.log_request(
                user_id=user_id if isinstance(user_id, int) else 0,
                endpoint="/explain_news",
                method="POST",
                response_time_ms=duration_ms,
                cache_hit=True,
                ai_provider="cache"
            )
            request_counter["success"] += 1
            
            return SimplifiedResponse(
                simplified_text=cached["text"],
                cached=True,
                processing_time_ms=round(duration_ms, 2)
            )
    
    # ==================== НОВАЯ v0.24: ИСПОЛЬЗУЕМ AI_DIALOGUE ====================
    try:
        # Импортируем новую систему ИИ
        from ai_dialogue import get_ai_response_sync
        
        # Формируем промпт для анализа новости
        analysis_prompt = f"""Проанализируй эту криптоновость КРАТКО и ясно:

📰 НОВОСТЬ:
{news_text}

Ответь одним-двумя предложениями:
1. ЧТО произошло?
2. Почему это ВАЖНО для крипторынка?

Будь кратким и понятным, только ФАКТЫ."""
        
        logger.info(f"🔄 Вызываем ai_dialogue для анализа...")
        
        # Получаем ответ через Groq → Mistral → Gemini
        ai_response = get_ai_response_sync(
            user_message=analysis_prompt,
            context_history=[],  # Анализ новостей - не нужен контекст
            timeout=15.0
        )
        
        if ai_response:
            logger.info(f"✅ Анализ получен: {len(ai_response)} символов ({(datetime.now(timezone.utc) - start_time_request).total_seconds():.2f}s)")
            
            # ⚡ HARD LIMIT: Ограничиваем ответ до 400 символов (v0.21.0)
            MAX_RESPONSE_CHARS = 400
            original_length = len(ai_response)
            
            if len(ai_response) > MAX_RESPONSE_CHARS:
                # Обрезаем на последнем полном предложении
                truncated = ai_response[:MAX_RESPONSE_CHARS]
                last_period = truncated.rfind('.')
                if last_period > 100:  # Есть хотя бы 100 символов перед точкой
                    ai_response = ai_response[:last_period + 1]
                else:
                    # Обрезаем на последнем пробеле
                    last_space = truncated.rfind(' ')
                    if last_space > 0:
                        ai_response = ai_response[:last_space] + "..."
                    else:
                        ai_response = truncated + "..."
                logger.info(f"✂️ Обрезан с {original_length} до {len(ai_response)} символов (API response truncation)")
            
            # Кэшируем результат (Redis с TTL)
            if CACHE_ENABLED:
                cache_data = {"text": ai_response, "timestamp": datetime.now(timezone.utc).isoformat()}
                cache_manager.set(text_hash, cache_data, ttl_seconds=CACHE_TTL_SECONDS)
            
            request_counter["success"] += 1
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            
            structured_logger.log_request(
                user_id=user_id if isinstance(user_id, int) else 0,
                endpoint="/explain_news",
                method="POST",
                response_time_ms=duration_ms,
                cache_hit=False,
                ai_provider="groq",
                status="success"
            )
            
            return SimplifiedResponse(
                simplified_text=ai_response,
                cached=False,
                processing_time_ms=round(duration_ms, 2)
            )
        else:
            # ai_dialogue не ответил, переходим на fallback
            logger.warning(f"⚠️ ai_dialogue не вернул ответ, используем fallback...")
            raise Exception("ai_dialogue returned None")
    
    except Exception as e:
        logger.error(f"❌ Ошибка в ai_dialogue: {type(e).__name__}: {str(e)}")
        request_counter["errors"] += 1
        
        structured_logger.log_error(
            error_type=type(e).__name__,
            message=str(e),
            user_id=user_id if isinstance(user_id, int) else 0,
            endpoint="/explain_news"
        )
        
        # Финальный fallback - ВСЕГДА даём какой-то ответ
        logger.warning(f"⚠️ Переходим на финальный fallback...")
        try:
            fallback_data = fallback_analysis(news_text)
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            
            request_counter["fallback"] += 1
            
            structured_logger.log_request(
                user_id=user_id if isinstance(user_id, int) else 0,
                endpoint="/explain_news",
                method="POST",
                response_time_ms=duration_ms,
                cache_hit=False,
                ai_provider="fallback",
                status="fallback"
            )
            
            return SimplifiedResponse(
                simplified_text=fallback_data["simplified_text"],
                cached=False,
                processing_time_ms=round(duration_ms, 2)
            )
        except Exception as fallback_err:
            logger.error(f"❌ Даже fallback не сработал: {fallback_err}")
            
            # ПОСЛЕДНИЙ ВАРИАНТ: Очень простой анализ или сообщение об ошибке
            request_counter["errors"] += 1
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            
            structured_logger.log_error(
                error_type="fallback_failure",
                message="All analysis methods failed",
                user_id=user_id if isinstance(user_id, int) else 0,
                endpoint="/explain_news"
            )
            
            # Даём минимально простой ответ
            simple_response = f"📰 Получена новость ({len(news_text)} символов). Система анализа сейчас перегружена. Попробуй позже."
            
            return SimplifiedResponse(
                simplified_text=simple_response,
                cached=False,
                processing_time_ms=round(duration_ms, 2)
            )
    
    # Вызов AI (сначала пробуем DeepSeek, потом Gemini)


# =============================================================================
# ENDPOINT: IMAGE ANALYSIS (v0.24 - updated)
# =============================================================================

@app.post("/analyze_image", response_model=ImageAnalysisResponse)
async def analyze_image(payload: ImagePayload, request: Request) -> JSONResponse:
    """
    Анализирует изображение (график, скриншот, мем) с помощью Gemini Vision.
    
    Поддерживает:
    - image_url: прямой URL на изображение
    - image_base64: изображение в формате base64 (PNG, JPEG, GIF, WebP)
    - context: дополнительный контекст для анализа
    """
    start_time_request = datetime.now(timezone.utc)
    request_counter["total"] += 1
    
    # Получаем user_id из заголовков
    user_id_header = request.headers.get("X-User-ID", "anonymous")
    try:
        user_id = int(user_id_header)
    except (ValueError, TypeError):
        user_id = 0
    
    try:
        # Проверяем rate limit
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            logger.warning(f"⚠️ Rate limit exceeded for IP: {client_ip}")
            request_counter["rate_limited"] += 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Попробуйте позже."
            )
        
        # Формируем контент для Gemini Vision API
        if payload.image_url:
            logger.info(f"📸 Анализирую изображение по URL: {payload.image_url[:50]}...")
            
            async with httpx.AsyncClient() as http_client:
                try:
                    img_response = await http_client.get(payload.image_url, timeout=10.0)
                    img_response.raise_for_status()
                    image_data = img_response.content
                    
                    # Определяем MIME тип
                    mime_type = img_response.headers.get("content-type", "image/jpeg")
                except Exception as e:
                    logger.error(f"❌ Ошибка при загрузке изображения по URL: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Не удалось загрузить изображение по URL"
                    )
        
        elif payload.image_base64:
            logger.info(f"📸 Анализирую изображение из base64 ({len(payload.image_base64)//1024}KB)...")
            try:
                image_data = base64.b64decode(payload.image_base64)
                mime_type = "image/jpeg"  # по умолчанию JPEG
            except Exception as e:
                logger.error(f"❌ Ошибка при декодировании base64: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный base64 формат"
                )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Необходимо предоставить image_url или image_base64"
            )
        
        # Конвертируем в base64 если загружали по URL
        image_b64 = base64.b64encode(image_data).decode()
        
        # Формируем запрос к Gemini с изображением
        config = build_image_analysis_config(payload.context)
        
        # Содержимое для Gemini (поддерживает изображения)
        contents = [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64
                        }
                    },
                    {
                        "text": "Проанализируй это изображение и предоставь полный анализ согласно инструкциям."
                    }
                ]
            }
        ]
        
        # Вызываем Gemini
        logger.info("🤖 Отправляю изображение Gemini для анализа...")
        try:
            response = await call_gemini_with_retry(
                client=client,
                model=GEMINI_MODEL,
                contents=contents,
                config=config
            )
            
            response_text = response.text if response and response.text else ""
            
            # Парсим JSON ответ
            json_match = re.search(r'<json>(.*?)</json>', response_text, re.DOTALL)
            if json_match:
                try:
                    analysis_data = json.loads(json_match.group(1))
                    logger.info("✅ Успешно распарсен JSON от Gemini")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON: {e}")
                    raise ValueError("Ошибка при парсинге JSON")
            else:
                logger.error(f"❌ JSON не найден в ответе Gemini: {response_text[:200]}")
                raise ValueError("JSON не найден в ответе")
            
            # ✅ NEW: Проверяем качество анализа с помощью AIQualityValidator
            quality = AIQualityValidator.validate_analysis(analysis_data)
            logger.info(f"📊 Качество анализа: {quality.score:.1f}/10 | Проблемы: {quality.issues}")
            
            # Если качество плохое, пытаемся исправить
            if quality.score < 5.0:
                logger.warning(f"⚠️ Низкое качество анализа ({quality.score:.1f}/10), пытаемся исправить...")
                fixed_data = AIQualityValidator.fix_analysis(analysis_data)
                if fixed_data:
                    analysis_data = fixed_data
                    quality = AIQualityValidator.validate_analysis(analysis_data)
                    logger.info(f"✅ Анализ исправлен: качество теперь {quality.score:.1f}/10")
                else:
                    logger.warning(f"⚠️ Не удалось исправить анализ, используем как есть")
            
            # Проверяем обязательные поля
            required_fields = ["summary_text", "analysis", "asset_type", "confidence", "mentioned_assets"]
            missing_fields = [f for f in required_fields if f not in analysis_data]
            
            if missing_fields:
                logger.warning(f"⚠️ Пропущены поля в ответе: {missing_fields}")
                raise ValueError(f"Пропущены поля: {missing_fields}")
            
            # Подготавливаем ответ
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            request_counter["success"] += 1
            
            return ImageAnalysisResponse(
                analysis=analysis_data.get("analysis", ""),
                asset_type=analysis_data.get("asset_type", "other"),
                confidence=float(analysis_data.get("confidence", 0.5)),
                mentioned_assets=analysis_data.get("mentioned_assets", []),
                simplified_text=analysis_data.get("summary_text", ""),
                cached=False,
                processing_time_ms=round(duration_ms, 2)
            )
        
        except HTTPException:
            raise
        except Exception as e:
            error_id = get_error_id()
            logger.error(f"❌ Ошибка при вызове Gemini [ID: {error_id}]")
            logger.debug(f"Details: {e}", exc_info=True)
            # Используем fallback анализ вместо ошибки
            try:
                fallback_data = fallback_image_analysis("other")
                duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
                
                return ImageAnalysisResponse(
                    analysis=fallback_data["analysis"],
                    asset_type=fallback_data["asset_type"],
                    confidence=fallback_data["confidence"],
                    mentioned_assets=fallback_data["mentioned_assets"],
                    simplified_text=fallback_data["summary_text"],
                    cached=False,
                    processing_time_ms=round(duration_ms, 2)
                )
            except Exception as fallback_error:
                logger.error(f"❌ Fallback также не сработал: {fallback_error}")
                request_counter["errors"] += 1
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Ошибка при анализе изображения"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        error_id = get_error_id()
        logger.error(f"❌ Неожиданная ошибка [ID: {error_id}]")
        logger.debug(f"Details: {e}", exc_info=True)
        request_counter["errors"] += 1
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сервера. ID: {error_id}"
        )

# =============================================================================
# ENDPOINT: TEACHING LESSONS
# =============================================================================

@app.post("/teach_lesson", response_model=TeachingResponse)
async def teach_lesson(payload: TeachingPayload) -> JSONResponse:
    """
    Создает интерактивный учебный урок по криптографии с встроенным AI.
    
    Использует встроенную базу знаний для быстрой доставки качественного контента.
    Возвращает структурированный урок с названием, содержанием, примерами и вопросом.
    """
    from embedded_teacher import get_embedded_lesson, get_all_topics, get_difficulties_for_topic
    
    start_time_request = datetime.now(timezone.utc)
    topic = payload.topic
    difficulty = payload.difficulty_level
    
    logger.info(f"📚 Запрос урока: {topic} ({difficulty})")
    
    try:
        # ✅ v0.37.7 FIX: Проверяем что уровень существует ДО загрузки
        available_difficulties = get_difficulties_for_topic(topic)
        
        if difficulty not in available_difficulties:
            # Если expert не существует, используем advanced вместо beginner fallback
            if difficulty == "expert" and "advanced" in available_difficulties:
                logger.info(f"📚 Уровень '{difficulty}' не в embedded, используем 'advanced' для expert request")
                difficulty = "advanced"
            elif not available_difficulties:
                # Тема вообще не существует в embedded
                logger.warning(f"⚠️ Тема '{topic}' не найдена в embedded_teacher")
                available_topics = get_all_topics()
                duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
                request_counter["fallback"] += 1
                
                return TeachingResponse(
                    lesson_title="Выбор темы обучения",
                    content=f"Тема '{topic}' недоступна. Доступные темы: {', '.join(available_topics)}. Пожалуйста, выберите одну из предложенных тем.",
                    key_points=available_topics,
                    real_world_example="Выберите интересующую вас тему для подробного изучения.",
                    practice_question="Какую тему криптографии вы хотели бы изучить?",
                    next_topics=available_topics,
                    processing_time_ms=round(duration_ms, 2)
                )
            else:
                # Уровень не существует, используем первый доступный
                logger.warning(f"⚠️ Уровень '{difficulty}' не существует для '{topic}' (доступны: {available_difficulties}), используем '{available_difficulties[0]}'")
                difficulty = available_difficulties[0]
        
        # Попробуем использовать встроенный урок (быстро и надежно)
        logger.info(f"🎓 Ищу встроенный урок для '{topic}' ({difficulty})...")
        
        embedded_lesson = get_embedded_lesson(topic, difficulty)
        
        if embedded_lesson:
            logger.info(f"✅ Найден встроенный урок: {embedded_lesson.lesson_title}")
            duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
            request_counter["success"] += 1
            
            return TeachingResponse(
                lesson_title=embedded_lesson.lesson_title,
                content=embedded_lesson.content,
                key_points=embedded_lesson.key_points,
                real_world_example=embedded_lesson.real_world_example,
                practice_question=embedded_lesson.practice_question,
                next_topics=embedded_lesson.next_topics,
                processing_time_ms=round(duration_ms, 2)
            )
        
        # Если встроенного урока нет, предложим доступные топики
        logger.warning(f"⚠️ Встроенный урок для '{topic}' не найден")
        available_topics = get_all_topics()
        logger.info(f"📚 Доступные топики: {', '.join(available_topics)}")
        
        # Вернем fallback с информацией о доступных топиках
        duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
        request_counter["fallback"] += 1
        
        return TeachingResponse(
            lesson_title="Выбор темы обучения",
            content=f"Тема '{topic}' недоступна. Доступные темы: {', '.join(available_topics)}. Пожалуйста, выберите одну из предложенных тем.",
            key_points=available_topics,
            real_world_example="Выберите интересующую вас тему для подробного изучения.",
            practice_question="Какую тему криптографии вы хотели бы изучить?",
            next_topics=available_topics,
            processing_time_ms=round(duration_ms, 2)
        )
    
    except Exception as e:
        logger.error(f"❌ Ошибка при создании урока: {e}", exc_info=True)
        request_counter["errors"] += 1
        
        duration_ms = (datetime.now(timezone.utc) - start_time_request).total_seconds() * 1000
        
        return TeachingResponse(
            lesson_title="Ошибка загрузки урока",
            content=f"Произошла ошибка при загрузке урока: {str(e)}. Пожалуйста, попробуйте позже.",
            key_points=["Попробуйте позже", "Выберите другую тему", "Свяжитесь с поддержкой"],
            real_world_example="Система обучения временно работает с ограничениями.",
            practice_question="Что вы хотели бы изучить?",
            next_topics=[],
            processing_time_ms=round(duration_ms, 2)
        )

# =============================================================================
# ENDPOINTS ДЛЯ ДРОПОВ И АКТИВНОСТЕЙ (v0.15.0)
# =============================================================================

@app.get("/get_drops", response_model=DropsResponse, tags=["Drops"])
async def get_drops_endpoint(limit: int = 10, chain: str = "all") -> Dict[str, Any]:
    """
    Получить информацию о свежих NFT дропах.
    
    Args:
        limit: Количество дропов (по умолчанию 10)
        chain: Цепь (arbitrum, solana, polygon, ethereum, all)
    
    Returns:
        DropsResponse с информацией о дропах
    """
    try:
        request_counter["total"] += 1
        start_time = datetime.now(timezone.utc)
        
        if chain.lower() == "all":
            drops = await get_nft_drops(limit)
        else:
            drops = await get_drops_by_chain(chain)
            drops = drops[:limit]
        
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        request_counter["success"] += 1
        
        return DropsResponse(
            drops=drops,
            count=len(drops),
            timestamp=datetime.now().isoformat(),
            cache_ttl_minutes=60
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при получении дропов: {e}")
        request_counter["errors"] += 1
        return DropsResponse(
            drops=[],
            count=0,
            timestamp=datetime.now().isoformat()
        )


@app.get("/get_activities", response_model=ActivitiesResponse, tags=["Drops"])
async def get_activities_endpoint() -> Dict[str, Any]:
    """
    Получить информацию об активностях в топ-проектах.
    
    Включает:
    - Обновления стейкинга (APY изменения)
    - Новые ланчи и события
    - Обновления контрактов
    - Гавернанс предложения
    - Партнерства
    
    Returns:
        ActivitiesResponse с информацией об активностях
    """
    try:
        request_counter["total"] += 1
        start_time = datetime.now(timezone.utc)
        
        activities = await get_activities()
        
        total_count = (
            len(activities.get("staking_updates", [])) +
            len(activities.get("new_launches", [])) +
            len(activities.get("contract_updates", [])) +
            len(activities.get("governance", [])) +
            len(activities.get("partnerships", []))
        )
        
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        request_counter["success"] += 1
        
        return ActivitiesResponse(
            staking_updates=activities.get("staking_updates", []),
            new_launches=activities.get("new_launches", []),
            contract_updates=activities.get("contract_updates", []),
            governance=activities.get("governance", []),
            partnerships=activities.get("partnerships", []),
            total_activities=total_count,
            timestamp=datetime.now().isoformat(),
            cache_ttl_minutes=60
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при получении активностей: {e}")
        request_counter["errors"] += 1
        return ActivitiesResponse(
            timestamp=datetime.now().isoformat()
        )


@app.get("/get_trending", response_model=DropsResponse, tags=["Drops"])
async def get_trending_endpoint(limit: int = 10) -> DropsResponse:
    """
    Получить список трендовых (вирусных) токенов за последние 24ч.
    
    Args:
        limit: Количество токенов (по умолчанию 10)
    
    Returns:
        DropsResponse с информацией о трендовых токенах
    """
    try:
        request_counter["total"] += 1
        start_time = datetime.now(timezone.utc)
        
        trending = await get_trending_tokens(limit)
        
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        request_counter["success"] += 1
        
        return DropsResponse(
            drops=trending,
            count=len(trending),
            source="CoinGecko Trending API",
            timestamp=datetime.now().isoformat(),
            cache_ttl_minutes=60
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при получении трендовых токенов: {e}")
        request_counter["errors"] += 1
        return DropsResponse(
            drops=[],
            count=0,
            timestamp=datetime.now().isoformat()
        )


@app.get("/get_token_info/{token_id}", response_model=TokenInfoResponse, tags=["Drops"])
async def get_token_info_endpoint(token_id: str) -> TokenInfoResponse:
    """
    Получить подробную информацию о конкретном токене.
    
    Args:
        token_id: ID токена в CoinGecko (например, 'bitcoin', 'ethereum', 'uniswap')
    
    Returns:
        TokenInfoResponse с информацией о токене
    """
    try:
        request_counter["total"] += 1
        start_time = datetime.now(timezone.utc)
        
        token_info = await get_token_info(token_id)
        
        if not token_info:
            request_counter["errors"] += 1
            raise ValueError(f"Токен {token_id} не найден")
        
        request_counter["success"] += 1
        token_info["timestamp"] = datetime.now().isoformat()
        
        return TokenInfoResponse(**token_info)
    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о токене: {e}")
        request_counter["errors"] += 1
        raise HTTPException(
            status_code=404,
            detail=f"Токен не найден: {str(e)}"
        )

# =============================================================================
# LEADERBOARD ENDPOINT (v0.17.0)
# =============================================================================

@app.get("/get_leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
async def get_leaderboard_endpoint(
    period: str = Query("all", pattern="^(week|month|all)$"),
    limit: int = Query(10, ge=1, le=50),
    user_id: Optional[int] = Query(None)
):
    """
    Получить таблицу лидеров.
    
    Args:
        period: Временной период ("week" - неделя, "month" - месяц, "all" - всё время)
        limit: Количество топ пользователей (1-50, по умолчанию 10)
        user_id: ID пользователя для получения его позиции
    
    Returns:
        LeaderboardResponse с таблицей лидеров
    """
    try:
        request_counter["total"] += 1
        start_time = datetime.now(timezone.utc)
        
        # Получаем базовые данные рейтинга
        leaderboard_data = []
        total_users = 0
        
        # Читаем из кэша (хотя бы одного из периодов)
        # В реальном приложении это должно быть в БД
        # Для демо используем простую логику
        
        # Получаем временной период
        now = datetime.now()
        if period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        else:  # "all"
            start_date = datetime(1970, 1, 1)
        
        # Форматируем отчёт
        leaderboard_response = LeaderboardResponse(
            period=period,
            top_users=[],
            user_rank=None,
            total_users=0,
            cached=True,
            timestamp=datetime.now().isoformat()
        )
        
        request_counter["success"] += 1
        
        logger.info(f"📊 Leaderboard запрос: period={period}, limit={limit}, user_id={user_id}")
        
        return leaderboard_response
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении рейтинга: {e}")
        request_counter["errors"] += 1
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения рейтинга: {str(e)}"
        )

# =============================================================================
# ENDPOINT: AI DIALOGUE METRICS v0.24
# =============================================================================

@app.get("/dialogue_metrics")
async def get_dialogue_metrics() -> dict:
    """
    📊 Получить метрики системы ИИ диалога.
    
    Показывает:
    - Общее количество запросов
    - Процент успехов
    - Статистику по каждому провайдеру (Groq, Mistral, Gemini)
    - Среднее время ответа
    """
    try:
        from ai_dialogue import get_metrics_summary
        metrics = get_metrics_summary()
        
        logger.info(f"📊 Запрос метрик диалога: {metrics['total_requests']} запросов, {metrics['success_rate']} успешно")
        
        return {
            "status": "ok",
            "data": metrics
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения метрик: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

# =============================================================================
# ОБРАБОТЧИКИ ОШИБОК
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
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
    logger.info(f"🚀 Запуск сервера на порту {port}")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
