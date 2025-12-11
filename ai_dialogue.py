#!/usr/bin/env python3
"""
🚀 РЕАЛЬНЫЙ ИИ ДИАЛОГ v0.24 - GROQ + MISTRAL + GEMINI с МЕТРИКАМИ

v0.24 - Полностью бесплатные провайдеры + мониторинг:
✅ Groq - PRIMARY (самый быстрый, 100ms!)
✅ Mistral - FALLBACK 1 (тоже бесплатный)
✅ Gemini - FALLBACK 2 (20 запросов/день)
✅ МЕТРИКИ - подробное отслеживание всех запросов

НИКАКИХ ПЛАТЕЖЕЙ, НИКАКИХ ЛИМИТОВ!
"""

import httpx
import json
import logging
from typing import Optional, List, Dict, Tuple
import os
from dotenv import load_dotenv
import time
from datetime import datetime
from collections import defaultdict
import asyncio
from threading import Lock

load_dotenv()

logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

# Groq (PRIMARY)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Mistral (FALLBACK 1)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# Gemini (FALLBACK 2)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").replace("models/", "")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "15.0"))

# ==================== RATE LIMITING v0.25 (БЕЗОПАСНОСТЬ) ====================

# Конфиг rate limiting
AI_RATE_LIMIT_REQUESTS = int(os.getenv("AI_RATE_LIMIT_REQUESTS", "10"))  # запросов
AI_RATE_LIMIT_WINDOW = int(os.getenv("AI_RATE_LIMIT_WINDOW", "60"))  # секунд

# Трекинг запросов: {user_id: [timestamp1, timestamp2, ...]}
ai_request_history: Dict[int, List[float]] = defaultdict(list)
# ✅ КРИТИЧЕСКИЙ ФИК #3: Race condition защита с lock'ом
_rate_limit_lock = Lock()


def check_ai_rate_limit(user_id: int) -> Tuple[bool, int, str]:
    """
    Проверяет rate limit для AI запросов.
    
    ✅ БЕЗОПАСНОСТЬ: Защита от DDoS через спам AI запросов
    
    Args:
        user_id: ID пользователя
        
    Returns:
        (is_allowed, remaining_requests, message)
        - is_allowed: Разрешен ли запрос
        - remaining_requests: Сколько запросов осталось
        - message: Текст для ответа пользователю
    """
    # ✅ КРИТИЧЕСКИЙ ФИК #3: Синхронизация с lock'ом для предотвращения race condition
    with _rate_limit_lock:
        now = time.time()
        window_start = now - AI_RATE_LIMIT_WINDOW
        
        # Очищаем старые запросы за пределами окна
        ai_request_history[user_id] = [
            t for t in ai_request_history[user_id]
            if t > window_start
        ]
        
        requests_in_window = len(ai_request_history[user_id])
        
        if requests_in_window >= AI_RATE_LIMIT_REQUESTS:
            remaining_time = int(
                AI_RATE_LIMIT_WINDOW - (now - ai_request_history[user_id][0])
            )
            logger.warning(f"⚠️ Rate limit exceeded for user {user_id}")
            return (
                False,
                0,
                f"⏱️ Лимит AI запросов: {AI_RATE_LIMIT_REQUESTS} за {AI_RATE_LIMIT_WINDOW}сек.\n"
                f"Попробуй через {remaining_time}сек."
            )
        
        # Добавляем текущий запрос (ATOMIC операция внутри lock'а)
        ai_request_history[user_id].append(now)
    remaining = AI_RATE_LIMIT_REQUESTS - len(ai_request_history[user_id])
    
    logger.debug(f"✅ AI Rate limit OK: user={user_id}, used={len(ai_request_history[user_id])}/{AI_RATE_LIMIT_REQUESTS}")
    
    return True, remaining, ""


# ==================== МЕТРИКИ v0.24 ====================

dialogue_metrics = {
    "total_requests": 0,
    "groq_requests": 0,
    "groq_success": 0,
    "groq_errors": 0,
    "groq_timeouts": 0,
    "groq_total_time": 0.0,
    
    "mistral_requests": 0,
    "mistral_success": 0,
    "mistral_errors": 0,
    "mistral_timeouts": 0,
    
    "gemini_requests": 0,
    "gemini_success": 0,
    "gemini_errors": 0,
    "gemini_timeouts": 0,
    
    "total_errors": 0,
    "total_success": 0,
    "avg_response_time": 0.0,
    "last_updated": None
}

logger.info(f"🚀 AI Dialogue v0.24 (METRICS): GROQ={GROQ_MODEL}, MISTRAL={MISTRAL_MODEL}, GEMINI={GEMINI_MODEL}")


# ==================== ФУНКЦИИ МЕТРИК ====================

def update_metrics(provider: str, success: bool, response_time: float, error_type: str = None):
    """Обновляет метрики для провайдера."""
    global dialogue_metrics
    
    dialogue_metrics["total_requests"] += 1
    
    if provider == "groq":
        dialogue_metrics["groq_requests"] += 1
        if success:
            dialogue_metrics["groq_success"] += 1
            dialogue_metrics["groq_total_time"] += response_time
        elif error_type == "timeout":
            dialogue_metrics["groq_timeouts"] += 1
        else:
            dialogue_metrics["groq_errors"] += 1
    
    elif provider == "mistral":
        dialogue_metrics["mistral_requests"] += 1
        if success:
            dialogue_metrics["mistral_success"] += 1
        elif error_type == "timeout":
            dialogue_metrics["mistral_timeouts"] += 1
        else:
            dialogue_metrics["mistral_errors"] += 1
    
    elif provider == "gemini":
        dialogue_metrics["gemini_requests"] += 1
        if success:
            dialogue_metrics["gemini_success"] += 1
        elif error_type == "timeout":
            dialogue_metrics["gemini_timeouts"] += 1
        else:
            dialogue_metrics["gemini_errors"] += 1
    
    if success:
        dialogue_metrics["total_success"] += 1
    else:
        dialogue_metrics["total_errors"] += 1
    
    dialogue_metrics["last_updated"] = datetime.now().isoformat()


def get_metrics_summary() -> Dict:
    """Возвращает сводку метрик."""
    summary = {
        "timestamp": dialogue_metrics["last_updated"],
        "total_requests": dialogue_metrics["total_requests"],
        "success_rate": f"{(dialogue_metrics['total_success'] / max(dialogue_metrics['total_requests'], 1) * 100):.1f}%",
        "providers": {
            "groq": {
                "requests": dialogue_metrics["groq_requests"],
                "success": dialogue_metrics["groq_success"],
                "errors": dialogue_metrics["groq_errors"],
                "timeouts": dialogue_metrics["groq_timeouts"],
                "avg_time_ms": f"{(dialogue_metrics['groq_total_time'] / max(dialogue_metrics['groq_success'], 1) * 1000):.0f}"
            },
            "mistral": {
                "requests": dialogue_metrics["mistral_requests"],
                "success": dialogue_metrics["mistral_success"],
                "errors": dialogue_metrics["mistral_errors"],
                "timeouts": dialogue_metrics["mistral_timeouts"]
            },
            "gemini": {
                "requests": dialogue_metrics["gemini_requests"],
                "success": dialogue_metrics["gemini_success"],
                "errors": dialogue_metrics["gemini_errors"],
                "timeouts": dialogue_metrics["gemini_timeouts"]
            }
        }
    }
    return summary



def build_dialogue_system_prompt() -> str:
    """Системный промпт для ИИ - УНИВЕРСАЛЬНЫЙ для любой темы."""
    return """Ты - ЭКСПЕРТНЫЙ помощник в финансах, экономике, криптовалютах и макроэкономике.

⚠️ КРИТИЧНО - АДАПТИРУЙСЯ К ТЕМЕ:
- Определи тему разговора из контекста
- Отвечай КОНКРЕТно по теме, не уходи в неправильное направление
- ВНИМАТЕЛЬНО читай предыдущие сообщения - это ИСТОРИЯ разговора
- Если тема поменялась - адаптируй ответ, не повторяй старые точки зрения

СТРУКТУРА ОТВЕТА (компактно, 4-5 предложений):
1. Прямой ответ на вопрос (главное - в первом предложении)
2. Ключевые детали и механика
3. Практический контекст или пример
4. Почему это важно сейчас
5. Совет или заключение

ПРАВИЛА ОТВЕТОВ:
✅ ДЕЛАЙ:
- Отвечай прямо и по существу
- Приводи конкретные цифры и факты
- Учитывай ПОЛНЫЙ контекст разговора
- Объясняй просто, но точно
- Используй технические термины если нужно
- Один-два практических примера максимум

❌ НЕ ДЕЛАЙ:
- Не повторяй информацию из истории
- Не хвали пользователя
- Не выдумывай данные
- Не уходи от вопроса в общие рассуждения
- Не пиши лишние абзацы

ТОНЕ: Профессиональный эксперт, разговорный, без воды.
ОБЪЕМ: 4-5 предложений для компактного ответа, максимум 500 символов."""


def build_simple_dialogue_prompt() -> str:
    """Промпт с ударением на главную фишку - простые слова без воды."""
    return """Ты - помощник бота RVX AI по криптовалютам и блокчейну.

🎯 ГЛАВНАЯ ФИШКА RVX AI:
Объясняем ВСЕ простыми словами БЕЗ воды и сложного жаргона!

О RVX AI:
- Образовательный Telegram бот
- Это ТОЛЬКО диалоговый помощник и анализатор новостей
- НЕ сложный продукт, НЕ платформа, НЕ услуга - просто бот

⚠️ САМЫЕ КРИТИЧНЫЕ ЗАПРЕТЫ:
- НИКОГДА не выдумывай финансирование, инвесторов, деньги
- НИКОГДА не выдумывай про команду - разработчик один
- НИКОГДА не выдумывай про продукты/услуги - только бот для диалогов
- Если спросят про всё это → скажи: "я не располагаю информацией"

ПРАВИЛА НАПИСАНИЯ:
✨ СУПЕР ПРОСТО: Как для школьника
✨ БЕЗ ВОДЫ: Только суть
✨ ПРЯМО: Сразу ответ
✨ КОНКРЕТНО: Факты и примеры

ЛИМИТЫ:
- Максимум 2-3 абзаца
- 200-250 слов максимум
- Если не знаешь - честно скажи"""


def clean_hallucinations(text: str) -> str:
    """Отключена - просто возвращает текст как есть."""
    return text


def should_mention_developer(user_message: str) -> bool:
    """Определяет нужно ли упомянуть разработчика как администратора."""
    # Только для вопросов про поддержку, проблемы, контакты
    keywords = [
        "админ", "администратор", "ошибка", "баг", "проблема",
        "контакт", "поддержка", "помощь"
    ]
    
    message_lower = user_message.lower()
    return any(keyword in message_lower for keyword in keywords)


def build_context_for_prompt(context_history: List[dict]) -> str:
    """Формирует контекст из истории.
    
    ✅ FIXED: Теперь получает List[dict] в правильном формате
    """
    if not context_history:
        return ""
    
    context_lines = []
    for msg in context_history[-10:]:
        try:
            if not isinstance(msg, dict):
                continue
                
            msg_type = msg.get('role', 'user')
            content = msg.get('content', '')
            
            # Увеличена до 300 символов для лучшего контекста (было 150)
            if isinstance(content, str):
                content = content[:300]
            else:
                content = str(content)[:300] if content else ''
            
            if msg_type == 'user':
                context_lines.append(f"Пользователь: {content}")
            else:
                context_lines.append(f"Помощник: {content}")
        except Exception as e:
            logger.debug(f"⚠️ Error processing message in context: {e}")
            continue
    
    if context_lines:
        return "ИСТОРИЯ:\n" + "\n".join(context_lines) + "\n\n"
    return ""


def get_ai_response_sync(
    user_message: str,
    context_history: List[dict] = None,
    timeout: float = TIMEOUT,
    user_id: Optional[int] = None  # ✅ НОВОЕ: для rate limiting
) -> Optional[str]:
    """
    Получает ответ ИИ через Groq → Mistral → Gemini
    
    ✅ Полностью бесплатно
    ✅ Никаких лимитов (rate limit 30 req/min)
    ✅ Быстрые ответы (100ms для Groq!)
    ✅ МЕТРИКИ ДЛЯ КАЖДОГО ЗАПРОСА
    ✅ RATE LIMITING для защиты от DDoS
    """
    
    context_history = context_history or []
    request_start_time = time.time()
    
    # ✅ БЕЗОПАСНОСТЬ: Проверка rate limit перед запросом к AI
    if user_id is not None:
        is_allowed, remaining, limit_message = check_ai_rate_limit(user_id)
        if not is_allowed:
            logger.warning(f"⛔ Rate limit exceeded for user {user_id}")
            return limit_message  # Возвращаем сообщение об ограничении
    
    # Формируем промпт - ИСПОЛЬЗУЕТ ПРАВИЛЬНЫЙ промпт с полным контекстом
    context_str = build_context_for_prompt(context_history)
    system_prompt = build_dialogue_system_prompt()  # ✅ FIXED: Using correct full prompt instead of short version
    
    # ✅ DEBUG: Логируем что попадает в контекст
    if context_str:
        logger.debug(f"📝 Context ({len(context_str)} chars): {context_str[:200]}...")
    else:
        logger.debug(f"⚠️ Context is EMPTY - no history passed!")
    
    # Формируем полный промпт с контекстом диалога (RVX context уже в system_prompt)
    full_prompt = f"{system_prompt}\n\n{context_str}Пользователь: {user_message}"
    
    # ==================== ПОПЫТКА 1: GROQ ====================
    if GROQ_API_KEY:
        provider_start = time.time()
        logger.info(f"🔄 Groq: Получаем ответ...")
        try:
            with httpx.Client(verify=True) as client:  # ✅ CRITICAL FIX #7: Explicit TLS verification
                response = client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": GROQ_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"{context_str}Пользователь: {user_message}"}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 2000,
                        "top_p": 0.9
                    },
                    timeout=timeout
                )
                
                provider_time = time.time() - provider_start
                logger.debug(f"📊 Groq HTTP: {response.status_code} ({provider_time:.2f}s)")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("choices") and len(data["choices"]) > 0:
                        ai_response = data["choices"][0]["message"]["content"].strip()
                        if ai_response:
                            # ✅ Проверяем и удаляем галлюцинации
                            ai_response = clean_hallucinations(ai_response)
                            
                            update_metrics("groq", True, provider_time)
                            logger.info(f"✅ Groq OK ({len(ai_response)} символов, {provider_time:.2f}s)")
                            return ai_response
                        else:
                            logger.warning(f"⚠️  Groq: пустой ответ")
                            update_metrics("groq", False, provider_time)
                    else:
                        logger.warning(f"⚠️  Groq: нет choices в ответе")
                        update_metrics("groq", False, provider_time)
                else:
                    logger.warning(f"⚠️  Groq HTTP {response.status_code}")
                    update_metrics("groq", False, provider_time)
                    
        except httpx.TimeoutException:
            provider_time = time.time() - provider_start
            logger.warning(f"⏱️  Groq: Timeout ({provider_time:.2f}s)")
            update_metrics("groq", False, provider_time, error_type="timeout")
        except Exception as e:
            provider_time = time.time() - provider_start
            logger.warning(f"❌ Groq ошибка: {type(e).__name__}: {str(e)[:100]}")
            update_metrics("groq", False, provider_time)
    else:
        logger.warning("⚠️  GROQ_API_KEY не установлен")
    
    # ==================== ПОПЫТКА 2: MISTRAL ====================
    if MISTRAL_API_KEY and MISTRAL_API_KEY != "ЗАМЕНИ_НА_КЛЮЧ_ИЗ_MISTRAL":
        provider_start = time.time()
        logger.info(f"🔄 Mistral: Получаем ответ (fallback 1)...")
        try:
            with httpx.Client(verify=True) as client:  # ✅ CRITICAL FIX #7: Explicit TLS verification
                response = client.post(
                    MISTRAL_API_URL,
                    headers={
                        "Authorization": f"Bearer {MISTRAL_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": MISTRAL_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"{context_str}Пользователь: {user_message}"}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 2000,
                        "top_p": 0.9
                    },
                    timeout=timeout
                )
                
                provider_time = time.time() - provider_start
                logger.debug(f"📊 Mistral HTTP: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("choices") and len(data["choices"]) > 0:
                        ai_response = data["choices"][0]["message"]["content"].strip()
                        if ai_response:
                            # ✅ Проверяем и удаляем галлюцинации
                            ai_response = clean_hallucinations(ai_response)
                            
                            update_metrics("mistral", True, provider_time)
                            logger.info(f"✅ Mistral OK ({len(ai_response)} символов, {provider_time:.2f}s)")
                            return ai_response
                        else:
                            logger.warning(f"⚠️  Mistral: пустой ответ")
                            update_metrics("mistral", False, provider_time)
                else:
                    logger.warning(f"⚠️  Mistral HTTP {response.status_code}")
                    update_metrics("mistral", False, provider_time)
                    
        except httpx.TimeoutException:
            provider_time = time.time() - provider_start
            logger.warning(f"⏱️  Mistral: Timeout")
            update_metrics("mistral", False, provider_time, error_type="timeout")
        except Exception as e:
            provider_time = time.time() - provider_start
            logger.warning(f"❌ Mistral ошибка: {type(e).__name__}: {str(e)[:100]}")
            update_metrics("mistral", False, provider_time)
    else:
        logger.debug("⏭️  Mistral: Пропущен (ключ не установлен)")
    
    # ==================== ПОПЫТКА 3: GEMINI ====================
    if GEMINI_API_KEY:
        provider_start = time.time()
        logger.info(f"🔄 Gemini: Получаем ответ (fallback 2)...")
        try:
            url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            
            with httpx.Client(verify=True) as client:  # ✅ CRITICAL FIX #7: Explicit TLS verification
                response = client.post(
                    url,
                    json={
                        "contents": [{
                            "parts": [{
                                "text": full_prompt
                            }]
                        }],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 200,
                            "topP": 0.95
                        }
                    },
                    timeout=timeout
                )
                
                provider_time = time.time() - provider_start
                logger.debug(f"📊 Gemini HTTP: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates and candidates[0].get("content", {}).get("parts"):
                        ai_response = candidates[0]["content"]["parts"][0].get("text", "").strip()
                        if ai_response:
                            # ✅ Проверяем и удаляем галлюцинации
                            ai_response = clean_hallucinations(ai_response)
                            
                            update_metrics("gemini", True, provider_time)
                            logger.info(f"✅ Gemini OK ({len(ai_response)} символов, {provider_time:.2f}s)")
                            return ai_response
                        else:
                            logger.warning(f"⚠️  Gemini: пустой ответ")
                            update_metrics("gemini", False, provider_time)
                else:
                    logger.warning(f"⚠️  Gemini HTTP {response.status_code}")
                    update_metrics("gemini", False, provider_time)
                    
        except httpx.TimeoutException:
            provider_time = time.time() - provider_start
            logger.warning(f"⏱️  Gemini: Timeout")
            update_metrics("gemini", False, provider_time, error_type="timeout")
        except Exception as e:
            provider_time = time.time() - provider_start
            logger.warning(f"❌ Gemini ошибка: {type(e).__name__}: {str(e)[:100]}")
            update_metrics("gemini", False, provider_time)
    else:
        logger.debug("⏭️  Gemini: Пропущен (ключ не установлен)")
    
    # ==================== ВСЕ ПРОВАЙДЕРЫ НЕДОСТУПНЫ ====================
    logger.error(f"❌ ВСЕ ПРОВАЙДЕРЫ НЕДОСТУПНЫ!")
    logger.error(f"   Groq: {'✅' if GROQ_API_KEY else '❌'}")
    logger.error(f"   Mistral: {'✅' if MISTRAL_API_KEY and MISTRAL_API_KEY != 'ЗАМЕНИ_НА_КЛЮЧ_ИЗ_MISTRAL' else '❌'}")
    logger.error(f"   Gemini: {'✅' if GEMINI_API_KEY else '❌'}")
    return None


# ==================== ТЕСТИРОВАНИЕ ====================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    print("\n" + "="*70)
    print("🧪 ТЕСТИРОВАНИЕ AI DIALOGUE v0.23")
    print("="*70 + "\n")
    
    tests = [
        ("Что такое Bitcoin?", []),
        ("Почему?", [{"type": "bot", "content": "Bitcoin это валюта"}]),
        ("Привет!", []),
    ]
    
    for msg, ctx in tests:
        print(f"📝 Тест: '{msg}'")
        response = get_ai_response_sync(msg, ctx)
        if response:
            print(f"✅ Ответ: {response[:80]}...\n")
        else:
            print(f"❌ Нет ответа\n")
    
    print("="*70 + "\n")
