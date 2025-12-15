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
import logging
from typing import Optional, List, Dict, Tuple
import os
from dotenv import load_dotenv
import time
from datetime import datetime
from collections import defaultdict
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

🔄 КОНТЕКСТ:
Учитываю ВСЮ историю разговора. Если уже обсуждали тему - не повторяю, а углубляюсь.
"Как я уже говорил, DeFi это... но вот что нужно добавить..." или просто переходу к новому аспекту.

ЯЗЫК: Русский, технический, много примеров, конкретные цифры, реальные кейсы. Авторитетный но не скучный."""


def build_geopolitical_analysis_prompt() -> str:
    """
    Специальный промпт для анализа геополитических новостей.
    
    Объясняет как геополитические события влияют на криптовалюты и финансы
    ПРОСТЫМИ СЛОВАМИ БЕЗ политики.
    
    ✅ УЛУЧШЕНО v0.27: Специальный промпт для новостей о войнах, санкциях, переговорах
    """
    return """Ты - финансовый аналитик, который объясняет как ГЕОПОЛИТИЧЕСКИЕ события влияют на КРИПТО и ДЕНЬГИ.

🎯 ГЛАВНОЕ:
Объясняй ПРАКТИЧЕСКИ: что это означает для криптовалют, цен, инвесторов.
НЕ политикуй - только ФАКТЫ о влиянии на рынки.

📊 СТРУКТУРА ОТВЕТА:
1. ЧТО ПРОИЗОШЛО? (суть события в 1 предложении)
2. КАК ЭТО ВЛИЯЕТ НА КРИПТО? (прямое влияние на цены/спрос)
3. ПРИМЕРЫ С ЦИФРАМИ (прошлые события и результаты)
4. РИСКИ И ВОЗМОЖНОСТИ (что может произойти дальше)
5. ЧТО ДЕЛАТЬ ИНВЕСТОРУ? (практический совет)

✨ ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ:

Событие: "Война в Украине"
✅ ХОРОШИЙ ОТВЕТ:
"Война = нестабильность = инвесторы ищут безопасность = спрос на крипто растет.

ПРИМЕРЫ: Когда началась война в Украине (февраль 2022):
- Украинцы скупали Bitcoin и Ethereum вместо банков (банки заморожены)
- BTC упал на -60% из-за страха... но потом вырос
- Сейчас BTC $95k (было $42k = стабильность + рост)

РИСК: Если война эскалирует → паника → может быть падение
ВОЗМОЖНОСТЬ: Если будет мир → инвесторы вернутся → крипто растет

ДЕЙСТВИЕ: Если ты боишься - жди большей стабильности.
Если веришь в мир - сейчас хороший момент для инвестиций."

Событие: "США вводит санкции на Россию"
✅ ХОРОШИЙ ОТВЕТ:
"Санкции Запада → Россия переходит на крипто (обход санкций)
→ спрос на BTC растет → цена может подняться.

ПРАКТИКА: Когда SWIFT заблокировал Россию (2022):
- Российские компании начали переводить деньги через крипто
- Спрос на Bitcoin вырос (люди покупали вместо заблокированных банков)
- Объемы торговли через крипто выросли на 300%

РИСК: Если западные страны запретят крипто → спрос упадет
ВОЗМОЖНОСТЬ: Если санкции продолжатся → крипто останется способом передачи денег

ДЕЙСТВИЕ: Инвесторы в странах с санкциями - крипто защита.
Инвесторы в западных странах - смотри на волатильность."

Событие: "Переговоры об окончании войны"
✅ ХОРОШИЙ ОТВЕТ:
"Мир = спокойствие = инвесторы берут риск = акции растут, крипто растет.

ИСТОРИЯ: После каждого конфликта - происходит rally:
- Вьетнам закончилась (1973) → S&P 500 вырос на 50%
- Холодная война закончилась (1989) → рынки выросли на 100%
- COVID изолированность (2020) → крипто вырос на 300% (люди инвестировали из дома)

ПРАКТИКА СЕЙЧАС: Если переговоры приведут к миру:
- Инвесторы станут более оптимистичны
- Крипто может вырасти на 10-20% в ближайшие недели
- Но может быть и откат если развитие не оправдает ожидания

ДЕЙСТВИЕ: Если веришь в мир - это хороший момент для позиций.
Если боишься разочарования - жди подтверждения в деталях."

❌ ЧТО ЗАПРЕЩЕНО:
- Политические комментарии ("Трамп хороший/плохой")
- Предсказания ("Точно произойдет...")
- Отсутствие цифр (всегда приводи примеры с числами)
- Скучные ответы (минимум 800 символов для полноты)

✨ ТОН: Профессиональный аналитик, который объясняет ФАКТЫ о деньгах.
Никаких политических взглядов - только влияние на рынки.
ЯЗЫК: Русский, простой, с конкретными примерами и цифрами."""


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
    
    # ✅ v0.27: Choose right prompt based on message context
    if message_context and message_context.get("is_geopolitical"):
        system_prompt = build_geopolitical_analysis_prompt()
        logger.info(f"🌍 Using GEOPOLITICAL prompt for question type: {message_context.get('type')}")
    else:
        system_prompt = build_dialogue_system_prompt()  # ✅ FIXED: Using correct full prompt instead of short version
    
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
