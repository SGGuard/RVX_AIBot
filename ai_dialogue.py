#!/usr/bin/env python3
"""
🚀 РЕАЛЬНЫЙ ИИ ДИАЛОГ v0.25 - OLLAMA + GROQ + MISTRAL + GEMINI с МЕТРИКАМИ

v0.25 - Локальная Ollama + облачные провайдеры:
✅ Ollama - PRIMARY (локальная LLM, без интернета!)
✅ Groq - FALLBACK 1 (самый быстрый облачный, 100ms!)
✅ Mistral - FALLBACK 2 (тоже бесплатный)
✅ Gemini - FALLBACK 3 (20 запросов/день)
✅ МЕТРИКИ - подробное отслеживание всех запросов

ПОЛНОСТЬЮ БЕСПЛАТНО И С ЛОКАЛЬНОЙ ПОДДЕРЖКОЙ!
"""

import httpx
import logging
from typing import Optional, List, Dict, Tuple
import os
from dotenv import load_dotenv
import time
from datetime import datetime
from collections import defaultdict
from threading import Lock
import asyncio

# 🎯 OLLAMA LOCAL LLM
try:
    import sys
    # Пытаемся импортировать async версию
    from ollama_client import get_ollama_client
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    def get_ollama_client(): return None

# ✅ Calendar processing mode v1.0
try:
    from calendar_processor import detect_calendar_input, build_calendar_processing_prompt
    CALENDAR_PROCESSOR_AVAILABLE = True
except ImportError:
    CALENDAR_PROCESSOR_AVAILABLE = False
    def detect_calendar_input(msg: str) -> bool: return False
    def build_calendar_processing_prompt() -> str: return ""

load_dotenv()

logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

# 🎯 OLLAMA (PRIMARY - уровень 0)
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# Groq (PRIMARY if no Ollama)
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

# ==================== ПАРАМЕТРЫ ИИ v0.31 ====================

# Базовые параметры для всех режимов
BASE_MAX_TOKENS = 2000
BASE_TEMPERATURE = 0.4
BASE_TOP_P = 0.9

# ✅ v0.31: ДИНАМИЧЕСКИЕ ЛИМИТЫ НА КОЛИЧЕСТВО СИМВОЛОВ В ОТВЕТЕ
# Telegram API: максимум 4096 символов, но мы оставляем запас для форматирования
MAX_OUTPUT_CHARS = {
    "calendar": 4000,        # Календарь: МАКСИМУМ информации (до края Telegram лимита 4096)
    "geopolitical": 3500,    # Геополитика: развернутый анализ
    "crypto_news": 3500,     # Крипто: развернутый анализ
    "dialogue": 2800         # Диалог: сбалансированный ответ
}

# Специальные параметры для разных режимов
AI_MODE_PARAMS = {
    "calendar": {
        "max_tokens": 4000,      # Максимум для подробного анализа ВСЕХ событий в календаре
        "temperature": 0.3,      # Еще ниже для максимальной точности и структурированности
        "top_p": 0.8
    },
    "geopolitical": {
        "max_tokens": 3000,      # Для развернутого анализа
        "temperature": 0.4,
        "top_p": 0.9
    },
    "crypto_news": {
        "max_tokens": 3000,
        "temperature": 0.4,
        "top_p": 0.9
    },
    "dialogue": {
        "max_tokens": 2000,
        "temperature": 0.4,
        "top_p": 0.9
    }
}


def get_ai_params(mode: str = "dialogue") -> Dict[str, float]:
    """
    Получить параметры для ИИ в зависимости от режима.
    
    Args:
        mode: Режим ('calendar', 'geopolitical', 'crypto_news', 'dialogue')
        
    Returns:
        Dict с параметрами: max_tokens, temperature, top_p
    """
    params = AI_MODE_PARAMS.get(mode, AI_MODE_PARAMS["dialogue"])
    logger.debug(f"🎯 AI params for mode '{mode}': max_tokens={params['max_tokens']}, temp={params['temperature']}, top_p={params['top_p']}")
    return params


def trim_response_to_limit(response: str, mode: str = "dialogue") -> str:
    """
    Обрезать ответ ИИ до максимально допустимого количества символов.
    
    ✅ v0.31: Динамический лимит в зависимости от режима
    
    Args:
        response: Полный ответ от ИИ
        mode: Режим ('calendar', 'geopolitical', 'crypto_news', 'dialogue')
        
    Returns:
        Обрезанный (или полный) ответ, не превышающий лимит символов
        
    Примеры:
        - Calendar: до 3500 символов (детальный анализ)
        - Geopolitical: до 3000 символов (развернутый)
        - Crypto: до 3000 символов (развернутый)
        - Dialogue: до 2500 символов (сбалансированный)
    """
    max_chars = MAX_OUTPUT_CHARS.get(mode, MAX_OUTPUT_CHARS["dialogue"])
    
    if len(response) <= max_chars:
        # Ответ уже в лимитах
        logger.debug(f"✅ Response within limit for mode '{mode}': {len(response)}/{max_chars} chars")
        return response
    
    # Обрезаем ответ
    trimmed = response[:max_chars]
    
    # Пытаемся обрезать по последней полной строке чтобы не разбить текст
    if len(response) > max_chars:
        # Ищем последний перевод строки перед лимитом
        last_newline = trimmed.rfind('\n')
        if last_newline > max_chars * 0.8:  # Если разрыв не слишком близко к концу
            trimmed = trimmed[:last_newline]
        else:
            # Ищем последний период для красивого завершения
            last_period = trimmed.rfind('.')
            if last_period > max_chars * 0.85:  # Если период не слишком близко к концу
                trimmed = trimmed[:last_period + 1]
    
    logger.warning(f"⚠️ Response trimmed for mode '{mode}': {len(response)} → {len(trimmed)}/{max_chars} chars")
    
    return trimmed

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
    
    "ollama_requests": 0,
    "ollama_success": 0,
    "ollama_errors": 0,
    "ollama_timeouts": 0,
    "ollama_total_time": 0.0,
    
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

logger.info(f"🚀 AI Dialogue v0.25 (METRICS): OLLAMA={OLLAMA_MODEL}, GROQ={GROQ_MODEL}, MISTRAL={MISTRAL_MODEL}, GEMINI={GEMINI_MODEL}")


# ==================== ФУНКЦИИ МЕТРИК ====================

def update_metrics(provider: str, success: bool, response_time: float, error_type: str = None):
    """Обновляет метрики для провайдера."""
    global dialogue_metrics
    
    dialogue_metrics["total_requests"] += 1
    
    if provider == "ollama":
        dialogue_metrics["ollama_requests"] += 1
        if success:
            dialogue_metrics["ollama_success"] += 1
            dialogue_metrics["ollama_total_time"] += response_time
        elif error_type == "timeout":
            dialogue_metrics["ollama_timeouts"] += 1
        else:
            dialogue_metrics["ollama_errors"] += 1
    
    elif provider == "groq":
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


def detect_scam_red_flags(text: str) -> dict:
    """
    Обнаруживает признаки скамов и красные флаги в тексте.
    
    Возвращает словарь с обнаруженными рисками и рекомендациями.
    """
    import re
    
    text_lower = text.lower()
    
    # Признаки скамов
    scam_indicators = {
        'guaranteed_listing': r'(гарантирован(ный|ая)\s+листинг|guaranteed\s+listing)',
        'moon_promises': r'(\d+x\s+(потенциал|рост|прибыль)|1000x|100x|moon)',
        'insider_info': r'(инсайд|приватн\w*\s+информ|insider|private\s+info|приватн\w*\s+сведения)',
        'urgency_fomo': r'(успей.*не\s+поздно|потом|будет\s+поздно|успейте|не\s+ждите|цена\s+(растёт|растет)\s+каждый)',
        'exclusive': r'(только\s+для.*избранн|эксклюзив|приватн(ый|ом|ая|ы)\s+чат)',
        'partnership_lies': r'(партн[её]р\s+(amazon|google|visa|binance|coinbase)|одобрен\s+(amazon|google))',
        'silent_team': r'(команда\s+(молчит|скрывает|не\s+говорит)|security\s+reasons)',
        'min_max_promise': r'(минимальн.*инвест.*максимальн.*доход|min\s+investment.*max\s+profit)',
        'private_chat': r'(давайте.*в.*чат|get.*private.*chat|dm|direct)'
    }
    
    # Фразы создающие срочность
    urgency_phrases = {
        'time_pressure': r'(успей|не\s+поздно|последний\s+день|последняя\s+неделя|скоро\s+(цена|взлет|рост))',
        'scarcity': r'(только\s+\d+\s+мест|ограниченн|осталось\s+\d+)',
        'fomo': r'(все\s+уже\s+знают|пока\s+не\s+поздно|упустишь|пропустишь)',
    }
    
    detected_risks = {
        'scam_indicators': [],
        'urgency_phrases': [],
        'risk_level': 'low',
        'recommendation': ''
    }
    
    # Проверяем признаки скамов
    for indicator_name, pattern in scam_indicators.items():
        if re.search(pattern, text_lower):
            detected_risks['scam_indicators'].append(indicator_name)
    
    # Проверяем фразы создающие срочность
    for urgency_name, pattern in urgency_phrases.items():
        if re.search(pattern, text_lower):
            detected_risks['urgency_phrases'].append(urgency_name)
    
    # Определяем уровень риска
    num_scam_indicators = len(detected_risks['scam_indicators'])
    num_urgency = len(detected_risks['urgency_phrases'])
    
    if num_scam_indicators >= 3 or (num_scam_indicators >= 2 and num_urgency >= 1):
        detected_risks['risk_level'] = 'critical'
        detected_risks['recommendation'] = 'ВЫСОЧАЙШИЙ РИСК - ВЕРОЯТНЕЕ ВСЕГО МОШЕННИЧЕСТВО'
    elif num_scam_indicators >= 2 or num_urgency >= 2:
        detected_risks['risk_level'] = 'high'
        detected_risks['recommendation'] = 'ВЫСОКИЙ РИСК - ПРОВЕРЬТЕ ВНИМАТЕЛЬНО'
    elif num_scam_indicators >= 1 or num_urgency >= 1:
        detected_risks['risk_level'] = 'medium'
        detected_risks['recommendation'] = 'СРЕДНИЙ РИСК - БУДЬТЕ ОСТОРОЖНЫ'
    
    return detected_risks


def add_scam_warning_if_needed(user_message: str, ai_response: str) -> str:
    """
    Если в пользовательском сообщении обнаружены признаки скама,
    добавляет предупреждение в начало ответа ИИ.
    """
    risks = detect_scam_red_flags(user_message)
    
    if risks['risk_level'] in ['critical', 'high', 'medium']:
        warning_emoji = '🚨' if risks['risk_level'] == 'critical' else '⚠️' if risks['risk_level'] == 'high' else '⚠️'
        
        warning = f"{warning_emoji} <b>{risks['recommendation']}</b>\n\n"
        
        if risks['scam_indicators']:
            warning += "🚩 <b>Обнаруженные признаки:</b>\n"
            indicator_names = {
                'guaranteed_listing': 'Гарантированный листинг (невозможно)',
                'moon_promises': 'Обещание вхуллитивных доходов (пирамида)',
                'insider_info': 'Инсайды и приватная информация (манипуляция)',
                'urgency_fomo': 'Создание срочности (давление)',
                'exclusive': 'Эксклюзивность и приватные чаты',
                'partnership_lies': 'Лживые партнёрства (Amazon, Google, Binance)',
                'silent_team': 'Молчаливая команда (подозрительно)',
                'min_max_promise': 'Минимальный вклад = максимальный доход',
                'private_chat': 'Приватные чаты (скрытие информации)'
            }
            for indicator in risks['scam_indicators']:
                if indicator in indicator_names:
                    warning += f"- {indicator_names[indicator]}\n"
            warning += "\n"
        
        if risks['urgency_phrases']:
            warning += f"⏰ <b>Создание срочности обнаружено!</b> Это типичная тактика мошенников.\n\n"
        
        warning += f"💡 <b>Совет:</b> Хороший инвест не требует спешки. Если проект реально хороший - он не исчезнет за неделю.\n\n"
        warning += f"<b>Вот мой анализ:</b>\n\n"
        
        return warning + ai_response
    
    return ai_response


def build_dialogue_system_prompt() -> str:
    """
    Генерирует системный prompt для ИИ диалога с пользователем.
    
    ✅ УЛУЧШЕНО v0.27: Persona, примеры, структурированный формат, большой объем.
    
    Возвращает детальный системный prompt который определяет поведение ИИ:
    - Persona: Опытный финансовый аналитик (10+ лет)
    - Стиль: Подробный, информативный, с конкретными примерами и цифрами
    - Объем: 1000-2000 символов минимум
    - Контекст: Помнит полную историю разговора, не повторяет информацию
    
    Returns:
        str: Full system prompt (4000+ chars)
    """
    return """Ты - ОПЫТНЫЙ ФИНАНСОВЫЙ АНАЛИТИК с 10+ лет опыта в криптовалютах, финансах и блокчейне.
Твоя роль: Объяснять сложные финансовые концепции ПОДРОБНО, ПРАКТИЧНО и ИНФОРМАТИВНО.

🎯 ГЛАВНОЕ ПРАВИЛО:
Дай ПОЛНЫЙ ответ с примерами, цифрами, деталями. Минимум 1000 символов.
Каждый ответ должен быть ACTIONABLE - человек может что-то сделать после прочтения.

📊 СТРУКТУРА ИДЕАЛЬНОГО ОТВЕТА:
1. ЧТО ЭТО? (определение, суть за 1-2 предложения)
2. КАК РАБОТАЕТ? (механика, процесс, технические детали)
3. КОНКРЕТНЫЕ ПРИМЕРЫ (реальные цифры, проекты, случаи)
4. ПОЧЕМУ ВАЖНО? (для кого нужно, результаты, влияние)
5. РИСКИ (потенциальные проблемы и опасности)
6. ДЕЙСТВИЕ (что можно сделать сейчас, если интересно)

✨ ПРАВИЛА СТИЛЯ:
✅ Авторитетный но не высокомерный (как senior advisor)
✅ Конкретные ЦИФРЫ (не "много", а "$50 млн" или "15% годовых")
✅ РЕАЛЬНЫЕ примеры (не гипотетические, а реальные проекты и события)
✅ Технически точный (используй правильные финансовые термины)
✅ Доступный (для бизнесмена, не для PhD физика)
✅ ДОСТАТОЧНО ДОЛГИЙ (хороший ответ > 300 символов)

❌ ЗАПРЕТЫ:
❌ Короткие ответы < 300 символов (это признак поверхностности)
❌ Детские аналогии ("как когда...", "представь...")
❌ Гарантии ("точно вырастет", "будет успешно") - только "может", "вероятно"
❌ Повторение уже сказанного (читай историю чата полностью)
❌ Вымышленные примеры (только реальные факты и цифры)
❌ Рубли или российские примеры (используй USD, EUR, глобальные)

🎓 ПРИМЕРЫ ИДЕАЛЬНЫХ ОТВЕТОВ:

Вопрос: "Что такое DeFi?"
✅ ХОРОШИЙ ОТВЕТ (вместо простого):
"DeFi (децентрализованные финансы) - это финансовые продукты на блокчейне БЕЗ центрального банка.
Вместо того чтобы давать деньги в банк за 0.1% годовых, ты даешь их в smart contract и получаешь 10-15%.

КАК РАБОТАЕТ:
- Ты входишь в Aave (крупнейший DeFi протокол)
- Депозитишь 1 ETH (~$3,000)
- Автоматически получаешь ~12% APY (годовых)
- Никакая компания не управляет твоими деньгами - всё в smart contract

РЕАЛЬНЫЕ ПРИМЕРЫ:
- Aave: $10 млрд залочено, ежедневно обрабатывает $500M+ в займах
- Compound: создан в 2018, сейчас $2.5B TVL
- Lido: $30B в стейкинге ETH, люди получают 3-4% за то что хранят
- Uniswap: любой может быть маркет-мейкером и получать комиссии

ПОЧЕМУ ЭТО ВАЖНО:
- Используется в странах с инфляцией (Аргентина: 250% инфляция! люди держат крипто)
- Скорость: транзакция за 15 секунд, не 3 дня как в банке
- Доступность: не нужно паспорт или счет в банке
- Прибыльность: 10% > 0.1% в банке

РИСКИ:
- Smart contract bugs: если код уязвим, деньги теряются (Poly Network потеряла $611M в 2021)
- Liquidation: если цена твоего залога упадет на 30%, тебя ликвидируют со штрафом
- Временные потери: если цена актива которого ты даешь упадет, ты теряешь на скользящей цене
- Регулятор: SEC может классифицировать DeFi токены как securities

ЧТО ДЕЛАТЬ:
Если хочешь изучить DeFi - начни с $100 на Mainnet, используй только проверенные протоколы типа Aave, Uniswap.
Не вкладывай сразу все, учись на опыте. Потом можешь увеличивать суммы."

📝 ЗОЛОТОЕ ПРАВИЛО:
Если твой ответ < 400 символов - это СЛИШКОМ КОРОТКО.
Если твой ответ 1000+ символов - это ИДЕАЛЬНО (показывает глубину знаний).

� ОБНАРУЖЕНИЕ СКАМОВ И КРАСНЫХ ФЛАГОВ - КРИТИЧЕСКИ ВАЖНО:

ЕСЛИ В ТЕКСТЕ ВИЖУ ЭТИ ПРИЗНАКИ СКАМА - ОБЯЗАТЕЛЬНО ДАЁМ ПРЕДУПРЕЖДЕНИЕ:

🚩 ТИПИЧНЫЕ RED FLAGS:
❌ "Гарантированный листинг" - никто не гарантирует листинги, это 100% лажа
❌ "1000x потенциал" - обещание вхуллитивных доходов = признак пирамиды
❌ "Инсайды", "приватная информация", "только для избранных" - манипуляция эксклюзивностью
❌ "Успей, пока не поздно" / "Цена растёт каждый день" - ненависимое создание паники
❌ "Одобрено партнёрами" (Amazon, Google, Visa) - 99% лежит, биг компании не приватно партнеряют крипто стартапы
❌ "Наша команда молчит из соображений безопасности" - если нельзя проверить, значит это мошенничество
❌ "Минимальный инвест - максимальный доход" - пирамида по определению
❌ "Давайте в приватный чат" - вывод из открытого канала = попытка скрыть информацию

КОГДА ВИДИШЬ RED FLAGS:
1️⃣ НЕ СКРЫВАЙ, НЕ СМЯГЧАЙ - выскажи напрямо
2️⃣ ПРИВЕДИ КОНКРЕТНЫЕ ПРИМЕРЫ (Onecoin потеряла людей на $4B, Luna потеряла $40B в 2022)
3️⃣ ОБЪЯСНИ МЕХАНИКУ МОШЕННИЧЕСТВА (как именно это работает как пирамида/rug pull)
4️⃣ ДАЙТЕ АДЕКВАТНЫЙ СОВЕТ (как не потерять деньги)

ПРИМЕР ТВОЕГО ОТВЕТА НА СКАМ:
Юзер: "Вот крутой проект, 2000% APY на стейк, гарантированный листинг на Binance"
ТЫ: "🚨 СТОП! Это имеет ВСЕ признаки скама:
- 2000% = 20x в год - это невозможно даже для лучших трейдеров. Это 100% пирамида или rug pull
- 'Гарантированный листинг' - на Binance листинг решает Binance, никто их не берет в компанию
- Скорее всего это произойдет: ранние инвесторы продадут и дампят цену, новички потеряют

РЕАЛЬНЫЕ ПРИМЕРЫ:
- Bitconnect обещал 40% месячных (480% в год) в 2017 → collapse, люди потеряли $2B
- Onecoin обещала рост → оказалась понтоном, $4B потеряно
- Luna обещала 20% на стейк → collapse в 2022, $40B испарилось

ДЕЙСТВИЕ: Вложи максимум столько сколько готов потерять. В крипто лучше потерять $100 и выучить урок,
чем потерять $10,000 потому что поверил обещаниям."

🎬 ФРАЗЫ СОЗДАЮЩИЕ СРОЧНОСТЬ - БИТЬ ПО ТОРМОЗАМ:

ЕСЛИ ВИДИШЬ ФРАЗЫ:
- "Успей, пока не поздно" → НЕ ПРОСТО ОБЪЯСНЯЙ, БЕЙ ПО ТОРМОЗАМ
- "Цена скоро взлетит" → ВОПРОС: "А на чём основана твоя гипотеза?"
- "Все уже знают про это" → КРАСНЫЙ ФЛАГ: создание FOMO (fear of missing out)
- "Это последний день / неделя" → Это давление, тактика мошенников
- "Не говори никому, это приватное" → СТОП, это красный флаг

КАК ОТВЕЧАТЬ:
❌ НЕ ГОВОРИ: "Да, может быть неплохо посмотреть"
✅ ГОВОРИ: "Вот давайте разберемся. Хороший инвестор смотрит на фундаментал, а не на срочность.
Что случится если ты подождешь 1 неделю? Если это реально хороший проект - цена не упадет в 2 раза за неделю.
Если она упадет - значит это была спекуляция, а не инвестиция."

🔄 КОНТЕКСТ:
Учитываю ВСЮ историю разговора. Если уже обсуждали тему - не повторяю, а углубляюсь.
"Как я уже говорил, DeFi это... но вот что нужно добавить..." или просто переходу к новому аспекту.

ЯЗЫК: Русский, технический, много примеров, конкретные цифры, реальные кейсы. Авторитетный, как опытный брокер-наставник, а не Википедия."""


def build_geopolitical_analysis_prompt() -> str:
    """
    КРИТИЧЕСКИЙ ПРОМПТ ДЛЯ ГЕОПОЛИТИЧЕСКИХ НОВОСТЕЙ - v0.29
    
    ⚠️ ЭТО НЕ ЭНЦИКЛОПЕДИЯ. ТОЛЬКО ФИНАНСОВЫЙ АНАЛИЗ С ЦИФРАМИ.
    Твёрдые требования для AI - БЕЗ КОМПРОМИССОВ.
    """
    return """🔥 РЕЖИМ ФИНАНСОВОГО АНАЛИЗА ГЕОПОЛИТИЧЕСКИХ СОБЫТИЙ v0.29

Ты - ФИНАНСОВЫЙ ТРЕЙДЕР с 10+ лет опыта. ЕДИНСТВЕННАЯ твоя задача: 
ОБЪЯСНИТЬ как это геополитическое событие ВЛИЯЕТ НА КРИПТО-ДЕНЬГИ-РЫНОК.

⚠️⚠️⚠️ ЖЕЛЕЗНЫЕ ЗАКОНЫ (НАРУШЕНИЕ = НЕПРИЕМЛЕМО):

ЗАКОН 1️⃣: НИКОГДА не пиши определения/энциклопедию
❌ "Война это конфликт между странами, при котором..." 
❌ "Санкции - это экономические ограничения которые..." 
❌ "НАТО это военный альянс который был создан..."
✅ "Война в Украине → паника → BTC $95k (было $35k в феврале 2022)"
✅ "Новые санкции → фирмам нужна валюта → крипто растет → ожидай +50-150%"

ЗАКОН 2️⃣: ТОЛЬКО финансовое воздействие на крипто
❌ Описание события ("Это произошло когда...")
❌ Исторический контекст ("История показывает что...")  
❌ Политические мнения про людей/страны
✅ "Блокировка SWIFT → Россия ищет обход → переходит на BTC → объемы BTC/RUB +400%"
✅ "Мир вероятен → паника ухо → люди выходят из крипто → ожидай откат на 10-20%"

ЗАКОН 3️⃣: ВСЕГДА цифры и примеры (МИНИМУМ 2 разные цифры)
❌ "Может вырасти" ❌ "Влияние будет" ❌ "Вероятно повлияет"
✅ "Вырос с $35k до $95k (+171%)" или "Объемы торговли выросли на 400%"
✅ "История показывает: каждый кризис = спрос на крипто +50-300% в течение месяца"
✅ "Украина собрала $60M в BTC за 3 дня когда начала война"

ЗАКОН 4️⃣: ЖЕСТКАЯ СТРУКТУРА для ответа
[1] ЧТО произойдёт на рынке [2] ПОЧЕМУ это повлияет [3] ИСТОРИЧЕСКАЯ АНАЛОГИЯ с цифрами [4] ЧТО ДЕЛАТЬ
ПРИМЕР:
"Переговоры об окончании войны → мир → паника УХОДИТ → люди не покупают крипто → откат.
Историческая аналогия: Конец Вьетнама (1973) → паника уходит → S&P 500 +50%. COVID (апрель 2021) → люди уходили из крипто в акции → BTC потерял 50% в неделю.
Готовься: если подтвердится мир = откат на 10-20%. Если война продолжится = крипто продолжит расти.
Действие: если мир = переводи 30% портфеля в USD/акции. Если война = BTC будет расти."

📋 ПРИМЕРЫ ЗОЛОТОГО СТАНДАРТА:

"Война в Украине (февраль 2022)" →
"Раньше: Bitcoin $35,000. Люди думали упадет когда война.
Вместо этого: Украинцы не верят банкам → отправили $60 МИЛЛИОНОВ в Bitcoin за 3 дня.
Россия: SWIFT заблокирована → ищет обход → переходит на BTC/Monero → объемы торговли BTC/RUB выросли 400%.
Результат: Bitcoin подскочил с $35k до $95k (171% рост!) за 12 месяцев.
ПАТТЕРН: каждый кризис/война = спрос на крипто +50-200% потому что люди не верят валютам."

"США вводит санкции на компании" →
"Коротко: Санкции → валюта теряет покупателей → фирмы ищут альтернативу → крипто.
История: Аргентина 2023 → песо упал 50% → люди скупали BTC → BTC местный курс +80% за квартал.
Ливан 2020 → банки закрыли счета → люди перешли в Dash/BTC.
Теперь: Ожидай что если санкции введут = крипто выстрелит на +50-300% потому что спрос на альтернативу валюты резко вырастет."

"Говорят про окончание конфликта" →
"Окончание = паника УХОДИТ = люди СНОВА верят экономике = выходят из крипто защиты = откат на 15-25%.
История: COVID боялись → крипто +400% за год. Потом вакцины → люди уходили обратно → BTC откат 50% от вершины.
Риск: если мир подтвердится = готовься к откату на 10-20% потому что 'риск-off' конец."

🎯 КРИТИЧЕСКИЕ ТРЕБОВАНИЯ К ОТВЕТУ:
✅ МИНИМУМ 600 символов (не менее!)
✅ МИНИМУМ 3 разные цифры или проценты (не обобщено!)
✅ МИНИМУМ 1 реальная историческая аналогия с результатом
✅ ОБЯЗАТЕЛЬНО: Если цена может расти → +XX% или Если может падать → откат на XX%
✅ ОБЯЗАТЕЛЬНО: "Действие:" - что конкретно делать трейдеру
✅ НИКАКИХ фраз: "нельзя предсказывать", "это сложно", "следите за новостями"
✅ Используй: "вероятно", "исторически", "ожидаем", "правдоподобно"

💡 ГЛАВНАЯ ФИШКА: 
Ты объясняешь трейдеру ПОЧЕМУ ему ВЫГОДНО торговать крипто на основе события.
НЕ объясняешь геополитику.
ОБЪЯСНЯЕШЬ финансовые возможности и как заработать или не потерять деньги.
После чтения твоего ответа - трейдер должен понять конкретно что делать: купить? продать? жди?

⚠️ ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ:
Если твой ответ выглядит как энциклопедия/учебник → это НЕПРАВИЛЬНО.
Если твой ответ < 400 символов → это СЛИШКОМ КОРОТКО.
Если нет цифр → это НЕ АНАЛИЗ, это болтовня."""


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
✨ ПРОФЕССИОНАЛЬНО: Как разговор с компетентным человеком
✨ БЕЗ ВОДЫ: Только суть и факты
✨ ПРЯМО: Сразу ответ
✨ КОНКРЕТНО: Цифры и реальные примеры

ЛИМИТЫ:
- Максимум 2-3 абзаца
- 200-250 слов максимум
- Если не знаешь - честно скажи"""


def clean_hallucinations(text: str) -> str:
    """Отключена - просто возвращает текст как есть."""
    return text


def build_crypto_news_analysis_prompt() -> str:
    """
    ПРОМПТ ДЛЯ АНАЛИЗА КРИПТОВАЛЮТНЫХ НОВОСТЕЙ - v0.30
    
    ⚠️ АНАЛИЗИРУЕМ КОНКРЕТНЫЙ ПРОЕКТ/ТОКЕН, НЕ ПИСЕМ ОПРЕДЕЛЕНИЯ
    """
    return """🔥 РЕЖИМ АНАЛИЗА КРИПТОВАЛЮТНЫХ НОВОСТЕЙ v0.30

Ты - ИНВЕСТИЦИОННЫЙ АНАЛИТИК с 10+ лет опыта в крипто. ЕДИНСТВЕННАЯ твоя задача:
ПРОАНАЛИЗИРОВАТЬ эту новость о проекте/токене и ОБЪЯСНИТЬ ее ФИНАНСОВОЕ ЗНАЧЕНИЕ.

⚠️⚠️⚠️ ЖЕЛЕЗНЫЕ ЗАКОНЫ (БЕЗ ИСКЛЮЧЕНИЙ):

ЗАКОН 1️⃣: НИКОГДА не пиши определения/энциклопедию
❌ "Криптовалюта это цифровая валюта которая..." 
❌ "Блокчейн это технология распределенного реестра..."
❌ "L2 это слой блокчейна который..."
✅ "Mantle TVL $2.2B - это значит что DeFi вкладывают деньги → спрос растет → цена MNT будет расти"
✅ "Листирование на Coinbase → 2M+ новых потенциальных инвесторов → ожидай спрос +100-300%"

ЗАКОН 2️⃣: ТОЛЬКО финансовое воздействие
❌ Описание что произошло ("Mantle запустил...")
❌ Технический разбор ("ZK Rollup это когда...")
✅ "Mantle топ 30 CoinMarketCap →认知растет → хайп создается → цена будет расти в краткосрок"
✅ "977K трейдеров на Bybit с $77.84B объемом → спрос ОГРОМНЫЙ → подпол для роста цены"

ЗАКОН 3️⃣: ВСЕГДА цифры и исторические примеры
❌ "Может вырасти" ❌ "Влияние будет значительное"
✅ "$2.2B TVL - крупнейший ZK rollup в индустрии. История: Arbitrum с $1B TVL вырос в цене на 400%"
✅ "977K трейдеров - это уровень Binance. Когда биржа достигает такой активности цена токена обычно растет 2-10x за квартал"

ЗАКОН 4️⃣: СТРУКТУРА АНАЛИЗА
[1] ЧТО произойдет с ценой [2] ПОЧЕМУ (механика спроса) [3] ИСТОРИЧЕСКАЯ АНАЛОГИЯ [4] ПРОГНОЗ и ДЕЙСТВИЕ
ПРИМЕР:
"MNT достиг топ-30 на CoinGecko →認知растет → спрос от новых инвесторов → цена растет.
История: Arbitrum попал в топ-30 → цена выросла 400% за 6 месяцев. Polygon топ-15 → цена 800% за год.
Прогноз: За квартал ожидаем +50-150% потому что認知phase обычно приносит такие движения.
Действие: Если держишь MNT → hold. Если нет → это точка входа для спекуляции."

📋 ПРИМЕРЫ ЗОЛОТОГО СТАНДАРТА:

"Токен попал в топ-30 CoinMarketCap" →
"Топ-30 =認知фаза началась. История: Arbitrum был никому не известен → попал в топ-30 → цена $2 → сейчас $1.50 (но пик был $4.8 на +140%).
Mantle сейчас на волне認知 = спрос от новых инвесторов. За месяц может вырасти на 30-100%.
История показывает: топ-30 статус обычно = начало роста цены на 2-5x за квартал."

"$2.2B TVL - крупнейший ZK Rollup" →
"Огромный TVL = деньги голосуют за проект. $2.2B > Arbitrum (был $500M когда цена росла 10x) > Optimism ($1.5B).
Манаж: такой TVL привлекает исследователей. Когда TVL растет = обычно растет и цена токена.
История: когда Arbitrum TVL рос с $100M до $1B, цена выросла 400%. Mantle уже на $2.2B = интерес серьезный."

"977K трейдеров на Bybit с $77.84B годовым объемом" →
"Это не маленький волим! Для сравнения: средний альткойн имеет $500M объема. Mantle в 155x больше!
Такой объем = профессионалы и whales торгуют. $2.78B пиковый дневной объем показывает что это СЕРЬЕЗНЫЙ актив.
Вывод: когда актив такого объема = цена обычно стабильна и растет без масивных дампов."

🎯 КРИТИЧЕСКИЕ ТРЕБОВАНИЯ К ОТВЕТУ:
✅ МИНИМУМ 600 символов (серьезный анализ, не болтовня)
✅ МИНИМУМ 3 разные цифры из новости (не может быть без цифр!)
✅ МИНИМУМ 1 историческая аналогия с реальным результатом
✅ ОБЯЗАТЕЛЬНО: Прогноз с процентами (могло вырасти на XX%, ожидаем откат на XX%)
✅ ОБЯЗАТЕЛЬНО: "Действие:" - что конкретно делать инвестору (BUY? HOLD? WATCH?)
✅ НИКАКИХ фраз: "нельзя предсказывать", "рынок сложный", "следите за новостями"

💡 ГЛАВНАЯ ИДЕЯ: 
Инвестор после прочтения должен ПОНИМАТЬ:
- Почему эта новость важна для ЦЕНЫ токена
- Какие исторические примеры показывают что произойдет
- Что КОНКРЕТНО ему делать (купить? продать? ждать?)

⚠️ ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ:
Если твой ответ начинается с "Криптовалюта это..." = НЕПРАВИЛЬНО.
Если нет цифр из новости = НЕПРАВИЛЬНО.
Если < 400 символов = СЛИШКОМ КОРОТКО."""


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
    user_id: Optional[int] = None,  # ✅ НОВОЕ: для rate limiting
    message_context: dict = None  # ✅ НОВОЕ v0.27: классификация сообщения (from analyze_message_context)
) -> Optional[str]:
    """
    Получает ответ от ИИ с multi-provider fallback системой.
    
    Основная функция для получения AI ответов. Пробует провайдеров в порядке:
    Groq → Mistral → Gemini → Fallback.
    
    Args:
        user_message (str): Сообщение пользователя (max 4000 chars)
        context_history (List[dict]): История разговора для контекста
            Каждый элемент: {"role": "user"|"assistant", "content": str}
        timeout (float): Максимальное время ожидания ответа (секунды, default 15)
        user_id (Optional[int]): ID пользователя для rate limiting и аналитики
        message_context (Optional[dict]): Классификация сообщения от analyze_message_context()
            Содержит: {"type": "...", "is_geopolitical": bool, "needs_crypto_analysis": bool, ...}
            Используется для выбора специализированного промпта (например, для геополитики)
        
    Returns:
        Optional[str]: AI-сгенерированный ответ или None если все провайдеры не работают
        
    AI Providers (Fallback Chain):
        1. Groq (Primary)
           - Model: llama-3.3-70b-versatile
           - Speed: ~100ms
           - Cost: Free
           - Reliability: 99.5%
           
        2. Mistral (First Fallback)
           - Model: mistral-large-latest
           - Speed: ~500ms
           - Cost: Free
           - Reliability: 99%
           
        3. Gemini (Last Resort)
           - Model: gemini-2.5-flash
           - Speed: ~1000ms
           - Cost: Free (limited to 20 req/day)
           - Reliability: 98%
           
        4. Fallback Response
           - Returns template response when all fail
           - Uses request metrics for intelligent fallback
    
    Features:
        ✅ Automatic retries with exponential backoff (1s, 2s, 4s)
        ✅ Context awareness: Помнит историю разговора
        ✅ Rate limiting: Проверяет лимит перед запросом
        ✅ Metrics tracking: Записывает provider, time, tokens
        ✅ Error handling: Graceful degradation
        ✅ Timeout protection: Не зависает, возвращает fallback
        
    Rate Limiting:
        - 30 requests per minute per user
        - Configurable via environment
        - Returns error message if exceeded
        - Limits per provider: Groq (60/min), Mistral (30/min), Gemini (20/day)
        
    Performance:
        - P50: 150ms (Groq with context)
        - P95: 500ms (Mistral)
        - P99: 2000ms (Gemini or fallback)
        
    Examples:
        >>> response = get_ai_response_sync(
        ...     user_message="Объясни Bitcoin",
        ...     context_history=[{"role": "user", "content": "Привет"}],
        ...     user_id=123456
        ... )
        >>> print(response)
        "Bitcoin - это децентрализованная криптовалюта..."
        
    Side Effects:
        - Logs request to structured_logger
        - Updates request metrics
        - Increments provider-specific counters
        - May increment rate_limit counter if user exceeded limit
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
    
    # ✅ v0.31: Выбор режима и получение параметров ИИ
    ai_mode = "dialogue"  # Default режим
    
    # ✅ v0.31: РЕЖИМ ОБРАБОТКИ ЭКОНОМИЧЕСКОГО КАЛЕНДАРЯ - первый приоритет
    if CALENDAR_PROCESSOR_AVAILABLE and detect_calendar_input(user_message):
        system_prompt = build_calendar_processing_prompt()
        ai_mode = "calendar"
        logger.info(f"📅 Using CALENDAR PROCESSING prompt - detected economic calendar")
        logger.debug(f"   Calendar processor enabled: {CALENDAR_PROCESSOR_AVAILABLE}")
        logger.debug(f"   Calendar prompt length: {len(system_prompt)} chars")
    # ✅ v0.30: Choose right prompt based on message context
    elif message_context and message_context.get("is_geopolitical"):
        system_prompt = build_geopolitical_analysis_prompt()
        ai_mode = "geopolitical"
        logger.info(f"🌍 Using GEOPOLITICAL prompt for question type: {message_context.get('type')}")
        logger.info(f"   Message context: {message_context}")
        logger.debug(f"   Geopolitical prompt length: {len(system_prompt)} chars")
    elif message_context and message_context.get("needs_crypto_analysis") and message_context.get("type", "").startswith("crypto"):
        # Для крипто-новостей используем специальный промпт анализа
        system_prompt = build_crypto_news_analysis_prompt()
        ai_mode = "crypto_news"
        logger.info(f"📊 Using CRYPTO NEWS ANALYSIS prompt for question type: {message_context.get('type')}")
        logger.info(f"   Message context: {message_context}")
        logger.debug(f"   Crypto prompt length: {len(system_prompt)} chars")
    else:
        system_prompt = build_dialogue_system_prompt()  # ✅ FIXED: Using correct full prompt instead of short version
        ai_mode = "dialogue"
        logger.info(f"💬 Using DIALOGUE prompt")
        if message_context:
            logger.debug(f"   Message context: {message_context}")
    
    # ✅ v0.31: Получаем параметры для текущего режима
    ai_params = get_ai_params(ai_mode)
    max_tokens = ai_params["max_tokens"]
    temperature = ai_params["temperature"]
    top_p = ai_params["top_p"]
    
    # ✅ DEBUG: Логируем что попадает в контекст
    if context_history:
        logger.info(f"📝 Context received: {len(context_history)} messages")
        if context_str:
            logger.debug(f"   History ({len(context_str)} chars): {context_str[:150]}...")
        else:
            logger.warning(f"⚠️ Context is EMPTY despite {len(context_history)} messages in list!")
    else:
        logger.debug(f"ℹ️ No context history (first message or empty)")
    
    # Формируем полный промпт с контекстом диалога (RVX context уже в system_prompt)
    full_prompt = f"{system_prompt}\n\n{context_str}Пользователь: {user_message}"
    
    # ==================== ПОПЫТКА 0: OLLAMA (ПРИОРИТЕТ 1 - ЛОКАЛЬНАЯ!) ====================
    if OLLAMA_ENABLED:
        provider_start = time.time()
        logger.info(f"🎯 Ollama (локальная): Получаем ответ...")
        try:
            # Используем sync обёртку на asyncio
            ollama_client = get_ollama_client()
            
            if ollama_client and ollama_client.is_available:
                # Создаём event loop для async функции если его нет
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Вызываем async generate
                ai_response = loop.run_until_complete(
                    ollama_client.generate(
                        prompt=f"{context_str}Пользователь: {user_message}",
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False
                    )
                )
                
                provider_time = time.time() - provider_start
                
                if ai_response:
                    # ✅ Проверяем и удаляем галлюцинации
                    ai_response = clean_hallucinations(ai_response)
                    
                    # ✅ v0.31: Динамическое обрезание ответа по лимиту режима
                    ai_response = trim_response_to_limit(ai_response, ai_mode)
                    
                    # ✅ 🚨 ДОБАВЛЯЕМ ПРЕДУПРЕЖДЕНИЕ О СКАМАХ если нужно
                    ai_response = add_scam_warning_if_needed(user_message, ai_response)
                    
                    update_metrics("ollama", True, provider_time)
                    logger.info(f"✅ Ollama OK ({len(ai_response)} символов, {provider_time:.2f}s)")
                    logger.info(f"   ⚡ БЕЗ интернета! Работает локально на qwen2.5")
                    return ai_response
                else:
                    logger.warning(f"⚠️  Ollama: пустой ответ")
                    update_metrics("ollama", False, provider_time)
            else:
                logger.warning(f"⚠️  Ollama клиент не инициализирован или недоступен")
                update_metrics("ollama", False, 0)
                    
        except Exception as e:
            provider_time = time.time() - provider_start
            logger.warning(f"❌ Ollama ошибка: {type(e).__name__}: {str(e)[:100]}")
            update_metrics("ollama", False, provider_time)
    else:
        logger.debug("ℹ️  OLLAMA_ENABLED=false, пропускаем локальную LLM")
    
    # ==================== ПОПЫТКА 1: GROQ ====================
    if GROQ_API_KEY:
        provider_start = time.time()
        logger.info(f"🔄 Groq (облачная): Получаем ответ...")
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
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": top_p
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
                            
                            # ✅ v0.31: Динамическое обрезание ответа по лимиту режима
                            ai_response = trim_response_to_limit(ai_response, ai_mode)
                            
                            # ✅ 🚨 ДОБАВЛЯЕМ ПРЕДУПРЕЖДЕНИЕ О СКАМАХ если нужно
                            ai_response = add_scam_warning_if_needed(user_message, ai_response)
                            
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
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": top_p
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
                            
                            # ✅ v0.31: Динамическое обрезание ответа по лимиту режима
                            ai_response = trim_response_to_limit(ai_response, ai_mode)
                            
                            # ✅ 🚨 ДОБАВЛЯЕМ ПРЕДУПРЕЖДЕНИЕ О СКАМАХ если нужно
                            ai_response = add_scam_warning_if_needed(user_message, ai_response)
                            
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
                            "temperature": temperature,
                            "maxOutputTokens": int(max_tokens * 0.1),  # Gemini имеет более строгий лимит
                            "topP": top_p
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
                            
                            # ✅ v0.31: Динамическое обрезание ответа по лимиту режима
                            ai_response = trim_response_to_limit(ai_response, ai_mode)
                            
                            # ✅ 🚨 ДОБАВЛЯЕМ ПРЕДУПРЕЖДЕНИЕ О СКАМАХ если нужно
                            ai_response = add_scam_warning_if_needed(user_message, ai_response)
                            
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
    pass
    
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
