"""
🔧 Embedded News Analyzer v1.0
Встроенный анализатор новостей для бота без необходимости внешней API.
Решает проблему 502 Bad Gateway на Railway.

Основные функции:
- Анализ криптоновостей и финансовых событий
- Multi-provider AI fallback (Groq → Mistral → Gemini)
- Кэширование результатов
- Обработка ошибок с fallback ответами
"""

import os
import logging
import json
import re
import hashlib
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

# Load environment variables with explicit path for Railway compatibility
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path), verbose=True)
else:
    load_dotenv(verbose=True)

# AI Providers
from openai import OpenAI
from google import genai

logger = logging.getLogger("EmbeddedAnalyzer")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Groq Configuration (Primary)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "5"))

# Mistral Configuration (First Fallback)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
MISTRAL_TIMEOUT = int(os.getenv("MISTRAL_TIMEOUT", "10"))

# Gemini Configuration (Last Fallback)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))

# DeepSeek Configuration (Alternative)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "10"))

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SYSTEM_PROMPT = """Ты опытный финансовый аналитик, специализирующийся на криптовалютах и блокчейн-технологиях. Твоя задача анализировать новости и финансовую информацию на РУССКОМ языке.

Когда анализируешь контент, ДОЛЖЕН ответить ТОЛЬКО валидным JSON объектом (без дополнительного текста) завернутым в теги <json></json>. JSON ДОЛЖЕН иметь точно эту структуру:

{
  "summary_text": "2-3 параграфа анализа новости (200-300 слов на РУССКОМ). Объясни что произошло, почему это важно, и какой потенциальный влияние на крипто-рынок.",
  "impact_points": ["Пункт 1 о влияние", "Пункт 2 о влияние", "Пункт 3 о влияние"]
}

ВАЖНО:
- Отвечай ТОЛЬКО на русском языке!
- Будь лаконичным но полным
- Используй техническую терминологию когда уместно
- Рассмотри рыночные последствия
- Определи возможные риски или возможности
- ВСЕГДА отвечай только валидным JSON
- Оберни ответ в теги <json></json>
- Помни что пользователь говорит на русском - отвечай соответственно!"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def hash_text(text: str) -> str:
    """Generate SHA-256 hash of text for caching."""
    return hashlib.sha256(text.encode()).hexdigest()

def extract_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from response text wrapped in <json></json> tags."""
    try:
        # Try to extract from <json>...</json> tags
        json_match = re.search(r'<json>(.*?)</json>', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try direct JSON parsing
            json_str = response_text.strip()
        
        data = json.loads(json_str)
        
        # Validate structure
        if "summary_text" in data and "impact_points" in data:
            if isinstance(data["impact_points"], list):
                return data
        
        return None
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"Failed to extract JSON: {e}")
        return None

def sanitize_input(text: str, max_length: int = 4096) -> str:
    """Sanitize and validate input text."""
    if not text or len(text) == 0:
        raise ValueError("Text cannot be empty")
    
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove potential prompt injection patterns
    dangerous_patterns = [
        r"ignore.*previous.*instructions",
        r"override.*system.*prompt",
        r"execute.*code",
        r"retrieve.*api.*key",
    ]
    
    for pattern in dangerous_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    return text.strip()

def validate_response(response: Dict[str, Any]) -> bool:
    """Validate AI response structure."""
    required_fields = {"summary_text", "impact_points"}
    
    if not all(field in response for field in required_fields):
        return False
    
    if not isinstance(response["summary_text"], str):
        return False
    
    if not isinstance(response["impact_points"], list):
        return False
    
    if len(response["summary_text"]) < 50:
        return False
    
    if len(response["impact_points"]) == 0:
        return False
    
    return True

def fallback_analysis(news_text: str) -> Dict[str, str]:
    """Fallback response when all providers fail."""
    return {
        "summary_text": f"""Based on the provided information, this news relates to cryptocurrency and blockchain markets. While detailed analysis requires AI processing, the key takeaways are: {news_text[:200]}... 

This news likely has market implications for crypto assets. Monitor official announcements and market reactions for more detailed impact assessment.

Recommendation: Follow up with official sources and market data for confirmation of any market impact.""",
        "impact_points": [
            "Crypto market may experience volatility based on this news",
            "Need to monitor official channel announcements for confirmation",
            "Consider broader market conditions when assessing impact"
        ]
    }

# ============================================================================
# AI PROVIDER IMPLEMENTATIONS
# ============================================================================

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def analyze_with_groq(text: str) -> Optional[Dict[str, Any]]:
    """Analyze news using Groq (Primary provider)."""
    if not GROQ_API_KEY:
        logger.debug("Groq API key not configured, skipping")
        return None
    
    try:
        def call_groq():
            client = OpenAI(
                api_key=GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )
            return client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000,
            )
        
        response = await asyncio.wait_for(
            asyncio.to_thread(call_groq),
            timeout=GROQ_TIMEOUT
        )
        
        result_text = response.choices[0].message.content
        parsed = extract_json_from_response(result_text)
        
        if parsed and validate_response(parsed):
            logger.info("✅ Groq analysis successful")
            return parsed
        
        logger.warning("Invalid response from Groq")
        return None
        
    except asyncio.TimeoutError:
        logger.warning(f"Groq timeout after {GROQ_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"Groq error: {e}")
        return None

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def analyze_with_mistral(text: str) -> Optional[Dict[str, Any]]:
    """Analyze news using Mistral (First fallback)."""
    if not MISTRAL_API_KEY:
        logger.debug("Mistral API key not configured, skipping")
        return None
    
    try:
        def call_mistral():
            client = OpenAI(
                api_key=MISTRAL_API_KEY,
                base_url="https://api.mistral.ai/v1"
            )
            return client.chat.completions.create(
                model=MISTRAL_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000,
            )
        
        response = await asyncio.wait_for(
            asyncio.to_thread(call_mistral),
            timeout=MISTRAL_TIMEOUT
        )
        
        result_text = response.choices[0].message.content
        parsed = extract_json_from_response(result_text)
        
        if parsed and validate_response(parsed):
            logger.info("✅ Mistral analysis successful")
            return parsed
        
        logger.warning("Invalid response from Mistral")
        return None
        
    except asyncio.TimeoutError:
        logger.warning(f"Mistral timeout after {MISTRAL_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"Mistral error: {e}")
        return None

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def analyze_with_gemini(text: str) -> Optional[Dict[str, Any]]:
    """Analyze news using Gemini (Last fallback)."""
    if not GEMINI_API_KEY:
        logger.debug("Gemini API key not configured, skipping")
        return None
    
    try:
        def call_gemini():
            # Use new google.genai Client API
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Prepare full prompt
            full_prompt = f"{SYSTEM_PROMPT}\n\n{text}"
            
            # Call the API
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 1000,
                }
            )
            return response
        
        # Use sync API with timeout
        response = await asyncio.wait_for(
            asyncio.to_thread(call_gemini),
            timeout=GEMINI_TIMEOUT
        )
        
        result_text = response.text
        parsed = extract_json_from_response(result_text)
        
        if parsed and validate_response(parsed):
            logger.info("✅ Gemini analysis successful")
            return parsed
        
        logger.warning("Invalid response from Gemini")
        return None
        
    except asyncio.TimeoutError:
        logger.warning(f"Gemini timeout after {GEMINI_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"Gemini error: {e}")
        return None

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def analyze_with_deepseek(text: str) -> Optional[Dict[str, Any]]:
    """Analyze news using DeepSeek (Alternative provider)."""
    if not DEEPSEEK_API_KEY:
        logger.debug("DeepSeek API key not configured, skipping")
        return None
    
    try:
        def call_deepseek():
            client = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com/beta"
            )
            return client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000,
            )
        
        response = await asyncio.wait_for(
            asyncio.to_thread(call_deepseek),
            timeout=DEEPSEEK_TIMEOUT
        )
        
        result_text = response.choices[0].message.content
        parsed = extract_json_from_response(result_text)
        
        if parsed and validate_response(parsed):
            logger.info("✅ DeepSeek analysis successful")
            return parsed
        
        logger.warning("Invalid response from DeepSeek")
        return None
        
    except asyncio.TimeoutError:
        logger.warning(f"DeepSeek timeout after {DEEPSEEK_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"DeepSeek error: {e}")
        return None

# ============================================================================
# MAIN ANALYSIS FUNCTION
# ============================================================================

async def analyze_news(
    news_text: str,
    user_id: int = 0,
    cache: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Analyze news with multi-provider fallback chain.
    
    Args:
        news_text: News text to analyze
        user_id: Optional user ID for analytics
        cache: Optional cache dict
        
    Returns:
        Dict with:
        - simplified_text: Analysis
        - impact_points: List of impacts
        - provider: Which AI provider was used
        - cached: Whether result was cached
        - processing_time_ms: Processing time
    """
    start_time = datetime.now(timezone.utc)
    
    # Sanitize input
    try:
        clean_text = sanitize_input(news_text)
    except ValueError as e:
        logger.error(f"Input validation error: {e}")
        return {
            "simplified_text": "Error: Invalid input text",
            "impact_points": ["Unable to analyze: invalid input"],
            "provider": "error",
            "cached": False,
            "processing_time_ms": 0
        }
    
    # Check cache
    text_hash = hash_text(clean_text)
    if cache:
        cached_result = cache.get(text_hash)
        if cached_result:
            logger.info(f"💾 Cache HIT: {text_hash[:8]}")
            cached_result["cached"] = True
            return cached_result
    
    logger.info(f"🔄 Analyzing with fallback chain: {len(clean_text)} chars | User: {user_id}")
    
    # Try providers in order
    providers = [
        ("Groq", analyze_with_groq),
        ("Mistral", analyze_with_mistral),
        ("DeepSeek", analyze_with_deepseek),
        ("Gemini", analyze_with_gemini),
    ]
    
    # Log API key status for debugging
    logger.info(f"📊 API Key Status: Groq={bool(GROQ_API_KEY)} Mistral={bool(MISTRAL_API_KEY)} DeepSeek={bool(DEEPSEEK_API_KEY)} Gemini={bool(GEMINI_API_KEY)}")
    
    for provider_name, provider_func in providers:
        try:
            logger.info(f"↔️ Trying {provider_name}...")
            result = await provider_func(clean_text)
            
            if result:
                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                response = {
                    "simplified_text": result.get("summary_text", ""),
                    "impact_points": result.get("impact_points", []),
                    "provider": provider_name.lower(),
                    "cached": False,
                    "processing_time_ms": round(processing_time)
                }
                
                # Cache result
                if cache:
                    cache[text_hash] = {
                        k: v for k, v in response.items() if k != "cached"
                    }
                
                logger.info(f"✅ {provider_name} success in {processing_time:.0f}ms")
                return response
                
        except Exception as e:
            logger.warning(f"❌ {provider_name} failed: {e}")
            continue
    
    # Fallback response when all providers fail
    logger.error("❌ All providers failed, using fallback response")
    processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    fallback = fallback_analysis(clean_text)
    
    return {
        "simplified_text": fallback["summary_text"],
        "impact_points": fallback["impact_points"],
        "provider": "fallback",
        "cached": False,
        "processing_time_ms": round(processing_time)
    }

# ============================================================================
# EXPORT
# ============================================================================

__all__ = ["analyze_news", "hash_text", "sanitize_input"]
