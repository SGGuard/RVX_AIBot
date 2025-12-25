"""
RVX Teaching Module v0.37.10 - Интерактивное обучение криптографии, ИИ, Web3 и трейдингу
Поддерживает 4 ИИ: Groq (основной), Mistral, DeepSeek, Gemini
Использует встроенные уроки как 100% надежный fallback
"""

import httpx
import json
import os
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv
import logging
import asyncio

load_dotenv()
logger = logging.getLogger("RVX_TEACHER")

# Темы для обучения
TEACHING_TOPICS = {
    "crypto_basics": {
        "name": "Основы криптографии и блокчейна",
        "description": "Начните здесь, если вы новичок в крипто"
    },
    "trading": {
        "name": "Основы трейдинга и анализа рынка",
        "description": "Техники анализа и торговли криптоактивами"
    },
    "web3": {
        "name": "Web3, децентрализация и смарт-контракты",
        "description": "Децентрализованный интернет и смарт-контракты"
    },
    "ai": {
        "name": "Искусственный интеллект и нейронные сети",
        "description": "ИИ, машинное обучение и применение в крипто"
    },
    "defi": {
        "name": "DeFi - децентрализованные финансы",
        "description": "Протоколы, стейкинг и кредитование"
    },
    "nft": {
        "name": "NFT и цифровые активы",
        "description": "NFT стандарты, маркетплейсы и применение"
    },
    "security": {
        "name": "Безопасность в крипто",
        "description": "Защита кошельков, приватных ключей, от фишинга"
    },
    "tokenomics": {
        "name": "Токеномика и экономика проектов",
        "description": "Как работает экономика криптопроектов"
    },
}

DIFFICULTY_LEVELS = {
    "beginner": {"emoji": "🌱", "name": "Новичок"},
    "intermediate": {"emoji": "📚", "name": "Средний"},
    "advanced": {"emoji": "🚀", "name": "Продвинутый"},
    "expert": {"emoji": "💎", "name": "Эксперт"}
}


def _get_fallback_lesson(topic: str, difficulty_level: str) -> Optional[Dict[str, Any]]:
    """Возвращает встроенный урок как fallback - без пугающих сообщений об API."""
    topic_info = TEACHING_TOPICS.get(topic, {"name": topic, "description": ""})
    if isinstance(topic_info, str):
        topic_info = {"name": topic_info, "description": ""}
    
    level_info = DIFFICULTY_LEVELS.get(difficulty_level, {"emoji": "📚", "name": "средний"})
    
    # ✅ v0.37.10: Если запрашивается expert, используем advanced встроенный (он лучше beginner)
    fallback_difficulty = difficulty_level
    if difficulty_level == "expert":
        logger.info(f"📚 Для expert используем advanced встроенный урок")
        fallback_difficulty = "advanced"
    
    # Пытаемся получить встроенный урок как fallback для хорошего качества контента
    try:
        from embedded_teacher import get_embedded_lesson
        embedded_topic = convert_topic_name_to_embedded(topic)
        logger.info(f"📚 Fallback: загружаем {fallback_difficulty} встроенный урок")
        embedded_lesson = get_embedded_lesson(embedded_topic, fallback_difficulty)
        if embedded_lesson:
            logger.info(f"✅ Встроенный урок готов: {embedded_lesson.lesson_title}")
            return {
                "lesson_title": embedded_lesson.lesson_title,
                "content": embedded_lesson.content,
                "key_points": embedded_lesson.key_points,
                "real_world_example": embedded_lesson.real_world_example,
                "practice_question": embedded_lesson.practice_question,
                "next_topics": embedded_lesson.next_topics,
                "is_fallback": True  # Флаг что это встроенный, не от ИИ
            }
        else:
            logger.warning(f"⚠️ Встроенный урок не найден для {embedded_topic}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при загрузке встроенного урока: {e}")
    
    # Если встроенный не сработал, вернём скучный fallback (редко)
    fallback_content = f"""
    {level_info['emoji']} {topic_info['name']}
    
    Пожалуйста, попробуйте ещё раз позже для полного интерактивного урока.
    """
    
    return {
        "lesson_title": f"{level_info['emoji']} {topic_info['name']}",
        "content": fallback_content.strip(),
        "key_points": [
            "Основная концепция",
            "Практическое применение",
            "Дальнейшее изучение"
        ],
        "real_world_example": "Примеры будут доступны позже",
        "practice_question": "Попробуйте ещё раз",
        "next_topics": [],
        "is_fallback": True
    }


def build_teacher_prompt(topic: str, level: str, question: Optional[str] = None) -> str:
    """Создает промпт для обучающего ИИ."""
    
    topic_info = TEACHING_TOPICS.get(topic, {"name": topic, "description": ""})
    if isinstance(topic_info, str):
        topic_info = {"name": topic_info, "description": ""}
    
    level_info = DIFFICULTY_LEVELS.get(level, {"emoji": "📚", "name": level})
    
    system_prompt = f"""
Ты — опытный преподаватель криптографии, блокчейна, ИИ, Web3 и трейдинга в RVX Academy.
Твоя цель — научить пользователя БЫСТРО и БЕЗ ПЕРЕГРУЗКИ информацией.

ТЕКУЩИЙ УРОК:
• Тема: {topic_info['name']}
• Уровень: {level_info['emoji']} {level_info['name']}

ПРАВИЛА ПРЕПОДАВАНИЯ:
1. Раздели материал на КОРОТКИЕ, ПОНЯТНЫЕ БЛОКИ
2. Фокусируйся на ОДНОЙ главной идее за раз
3. Используй простые аналогии (не перегружай технически)
4. Добавляй реальные примеры из крипто-мира
5. Задавай проверочный вопрос в конце

СТРУКТУРА БЛОКА:
- Введение: что главное (1-2 предложения)
- Объяснение с аналогией (3-4 предложения)
- Применение в крипто (1-2 предложения)

ФОРМАТ ОТВЕТА (СТРОГО В JSON, 150-200 СЛОВ):
{{
    "lesson_title": "Название блока на русском (2-4 слова)",
    "content": "Короткое объяснение (150-200 слов максимум). Для начинающих - совсем просто, для опытных - больше деталей",
    "key_points": ["пункт 1", "пункт 2", "пункт 3"],
    "real_world_example": "Один конкретный пример из крипто (1-2 предложения)",
    "practice_question": "Проверочный вопрос",
    "next_topics": ["рекомендуемая_тема_1", "рекомендуемая_тема_2"]
}}

НЕ добавляй: *, **, _, ~, `, маркдаун, эмодзи. ТОЛЬКО ВАЛИДНЫЙ JSON!
"""
    
    if question:
        system_prompt += f"\n\nУЗЕЦ ЗАДАЛ ВОПРОС: {question}\nОтвети кратко и просто в контексте урока."
    
    return system_prompt


def create_teaching_config(level: str = "beginner") -> dict:
    """Создает конфигурацию для обучающего запроса."""
    return {
        "system_instruction": build_teacher_prompt("crypto_basics", level),
        "temperature": 0.7,  # Более творческий
        "max_output_tokens": 2000,
        "top_p": 0.95,
        "top_k": 40
    }


def extract_teaching_json(raw_text: str) -> Optional[dict]:
    """Извлекает JSON из ответа учителя."""
    if not raw_text:
        return None
    
    import re
    
    # Сначала ищем <json>...</json> обертку (от API)
    json_wrap = re.search(r'<json>(.*?)</json>', raw_text, re.DOTALL | re.IGNORECASE)
    if json_wrap:
        text_to_parse = json_wrap.group(1)
    else:
        # Удаляем markdown блоки
        text = re.sub(r'```json\s*', '', raw_text, flags=re.IGNORECASE).strip()
        text = re.sub(r'```\s*', '', text).strip()
        
        # Ищем JSON напрямую - от первого { до последнего }
        json_start = text.find('{')
        json_end = text.rfind('}')
        
        if json_start == -1 or json_end == -1 or json_start > json_end:
            logger.warning(f"JSON не найден в ответе (ищем {{}} скобки)")
            return None
        
        text_to_parse = text[json_start:json_end+1]
    
    # Очищаем от маркеров
    text_to_parse = text_to_parse.replace("**", "").replace("__", "").replace("~~", "")
    
    try:
        data = json.loads(text_to_parse)
        if isinstance(data, dict):
            return data
        return None
    except json.JSONDecodeError as e:
        logger.debug(f"JSON parse error (попытка 1): {e}")
        
        # Пытаемся исправить с заменой кавычек
        cleaned = text_to_parse.replace("'", '"')
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError as e2:
            logger.warning(f"JSON parse error (попытка 2): {e2}")
            logger.debug(f"Текст для парса: {text_to_parse[:200]}")
            return None


def validate_teaching_response(data: dict) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность ответа учителя."""
    if not isinstance(data, dict):
        return False, "Ответ не является словарем"
    
    required_fields = ["lesson_title", "content", "key_points", "practice_question"]
    for field in required_fields:
        if field not in data:
            return False, f"Отсутствует поле: {field}"
    
    if not isinstance(data["key_points"], list) or len(data["key_points"]) < 2:
        return False, "key_points должен быть списком из 2+ элементов"
    
    if len(data.get("content", "")) < 50:
        return False, "content слишком короткий"
    
    return True, None


def format_lesson(lesson_data: dict, level: str) -> str:
    """Форматирует урок для отправки пользователю."""
    title = lesson_data.get("lesson_title", "Урок")
    content = lesson_data.get("content", "")
    key_points = lesson_data.get("key_points", [])
    example = lesson_data.get("real_world_example", "")
    question = lesson_data.get("practice_question", "")
    next_topics = lesson_data.get("next_topics", [])
    
    level_emoji = {
        "beginner": "🌱",
        "intermediate": "📚",
        "advanced": "🚀",
        "expert": "💎"
    }.get(level, "📖")
    
    separator = "━━━━━━━━━━━━━━━━━━"
    
    result = f"{separator}\n{level_emoji} <b>{title}</b>\n\n"
    result += f"{content}\n\n"
    
    result += f"{separator}\n📌 <b>КЛЮЧЕВЫЕ МОМЕНТЫ:</b>\n"
    for i, point in enumerate(key_points, 1):
        result += f"{i}. {point}\n"
    
    if example:
        result += f"\n{separator}\n💼 <b>ПРИМЕР ИЗ ЖИЗНИ:</b>\n{example}\n"
    
    if question:
        result += f"\n{separator}\n❓ <b>ПРОВЕРКА ПОНИМАНИЯ:</b>\n{question}\n"
    
    if next_topics:
        result += f"\n{separator}\n📚 <b>РЕКОМЕНДУЕМЫЕ ТЕМЫ:</b>\n"
        for topic in next_topics[:3]:
            result += f"• {topic}\n"
    
    result += separator
    return result.strip()


def get_topic_by_keyword(keyword: str) -> Optional[str]:
    """Находит тему по ключевому слову."""
    keyword_lower = keyword.lower()
    
    keywords_map = {
        "крипто": "crypto_basics",
        "блокчейн": "crypto_basics",
        "биткоин": "crypto_basics",
        "ethereum": "crypto_basics",
        "трейдинг": "trading",
        "торговля": "trading",
        "анализ": "trading",
        "web3": "web3",
        "децентрализ": "web3",
        "смарт-контракт": "web3",
        "ai": "ai",
        "нейрон": "ai",
        "машин": "ai",
        "defi": "defi",
        "финанс": "defi",
        "nft": "nft",
        "токен": "tokenomics",
        "экономика": "tokenomics",
        "безопасность": "security",
        "приватный": "security",
    }
    
    for key, topic in keywords_map.items():
        if key in keyword_lower:
            return topic
    
    return "crypto_basics"  # Default


def convert_topic_name_to_embedded(topic: str) -> str:
    """
    Конвертирует имена тем из TEACHING_TOPICS в имена доступные в embedded_teacher.
    
    Маппинг:
    - crypto_basics -> bitcoin (как основная тема криптографии)
    - trading -> (пока нет в embedded_teacher, fallback к bitcoin)
    - web3 -> web3
    - ai -> ai
    - defi -> defi
    - nft -> nft
    - security -> (пока нет, fallback к bitcoin)
    - tokenomics -> (пока нет, fallback к bitcoin)
    """
    topic_lower = topic.lower().strip()
    
    mapping = {
        "crypto_basics": "bitcoin",  # bitcoin уроки - главная часть крипто обучения
        "bitcoin": "bitcoin",
        "ethereum": "ethereum",
        "blockchain": "blockchain",
        "web3": "web3",
        "ai": "ai",
        "defi": "defi",
        "nft": "nft",
        "mining": "mining",
        # Fallback для тем, которых еще нет в embedded_teacher
        "trading": "bitcoin",  # Trading уроков нет, используем базу Bitcoin
        "security": "bitcoin",  # Security уроков нет, используем базу Bitcoin
        "tokenomics": "bitcoin",  # Tokenomics уроков нет, используем базу Bitcoin
    }
    
    return mapping.get(topic_lower, "bitcoin")


async def teach_lesson(
    topic: str,
    difficulty_level: str = "beginner",
    user_knowledge_context: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Создает интерактивный урок.
    
    Сначала пытается использовать встроенного преподавателя (встроенные уроки),
    затем - API endpoint если встроенный урок не найден.
    Возвращает словарь с уроком или None если ошибка.
    """
    try:
        topic = topic.lower()
        
        # ✅ СНАЧАЛА: Попытаемся использовать встроенного преподавателя (fast path)
        # Конвертируем имя темы в формат embedded_teacher
        embedded_topic = convert_topic_name_to_embedded(topic)
        logger.info(f"📚 Попытка загрузить встроенный урок: {topic} → {embedded_topic} ({difficulty_level})")
        try:
            from embedded_teacher import get_embedded_lesson, get_difficulties_for_topic
            
            # ✅ v0.37.6: Проверяем ПЕРЕД загрузкой что уровень существует
            available_difficulties = get_difficulties_for_topic(embedded_topic)
            if difficulty_level in available_difficulties:
                embedded_lesson = get_embedded_lesson(embedded_topic, difficulty_level)
                if embedded_lesson:
                    logger.info(f"✅ Встроенный урок найден: {embedded_lesson.lesson_title}")
                    return {
                        "lesson_title": embedded_lesson.lesson_title,
                        "content": embedded_lesson.content,
                        "key_points": embedded_lesson.key_points,
                        "real_world_example": embedded_lesson.real_world_example,
                        "practice_question": embedded_lesson.practice_question,
                        "next_topics": embedded_lesson.next_topics,
                        "processing_time_ms": 1.0
                    }
            else:
                logger.info(f"⚠️ Встроенный урок не имеет уровня '{difficulty_level}' (доступны: {available_difficulties}), используем API")
        except Exception as e:
            logger.warning(f"⚠️ embedded_teacher ошибка: {e}, используем API fallback")
        
        # ✅ v0.37.10: НОВАЯ АРХИТЕКТУРА - 4 ИИ напрямую, БЕЗ API
        # Попытаемся 4 ИИ в порядке приоритета: Groq → Mistral → DeepSeek → Gemini
        logger.info(f"🤖 Пытаемся 4 ИИ для создания урока...")
        
        # Groq (самый быстрый)
        logger.info(f"🚀 Попытка 1: Groq...")
        groq_result = await teach_lesson_via_groq(topic, difficulty_level)
        if groq_result and groq_result.get("lesson_title"):
            logger.info(f"✅ Groq создал урок!")
            return groq_result
        
        # Mistral (fallback 1)
        logger.info(f"🟣 Попытка 2: Mistral...")
        mistral_result = await teach_lesson_via_mistral(topic, difficulty_level)
        if mistral_result and mistral_result.get("lesson_title"):
            logger.info(f"✅ Mistral создал урок!")
            return mistral_result
        
        # DeepSeek (fallback 2)
        logger.info(f"🔵 Попытка 3: DeepSeek...")
        deepseek_result = await teach_lesson_via_deepseek(topic, difficulty_level)
        if deepseek_result and deepseek_result.get("lesson_title"):
            logger.info(f"✅ DeepSeek создал урок!")
            return deepseek_result
        
        # Gemini (fallback 3)
        logger.info(f"💎 Попытка 4: Gemini...")
        gemini_result = await teach_lesson_via_gemini_direct(topic, difficulty_level)
        if gemini_result and gemini_result.get("lesson_title"):
            logger.info(f"✅ Gemini создал урок!")
            return gemini_result
        
        # Если все 4 ИИ не сработали, используем встроенный урок как fallback
        logger.warning(f"⚠️ Все 4 ИИ не сработали, используем встроенный урок")
        return _get_fallback_lesson(topic, difficulty_level)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в teach_lesson: {e}", exc_info=True)
        return _get_fallback_lesson(topic, difficulty_level)
        return _get_fallback_lesson(topic, difficulty_level)


async def teach_lesson_via_gemini_direct(
    topic: str,
    difficulty_level: str = "beginner"
) -> Optional[Dict[str, Any]]:
    """
    ✅ v0.37.9: Вызывает Gemini НАПРЯМУЮ, обходя API сервер.
    
    Это решает проблему падения API при большой нагрузке.
    Используется как fallback когда API недоступен.
    
    Преимущества:
    - Не зависит от отдельного API процесса
    - Быстрее (нет HTTP overhead)
    - Более надежно (2 процесса вместо 3)
    """
    try:
        from google import genai
        
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        if not gemini_api_key:
            logger.error("❌ GEMINI_API_KEY не установлен")
            return _get_fallback_lesson(topic, difficulty_level)
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty_level, {})
        
        prompt = f"""Создай интерактивный урок по криптографии с высокой ценностью.

ТЕМА: {topic_info.get('name', topic)}
УРОВЕНЬ: {level_info.get('name', difficulty_level)}
ОПИСАНИЕ: {topic_info.get('description', '')}

ТРЕБОВАНИЯ:
1. Ответь ТОЛЬКО JSON (без markdown, без ```json кода)
2. Структура:
{{
  "lesson_title": "Название урока (максимум 50 символов)",
  "content": "Подробное объяснение (200-400 слов, с примерами для уровня {difficulty_level})",
  "key_points": ["Пункт 1", "Пункт 2", "Пункт 3", "Пункт 4"],
  "real_world_example": "Практический пример как это используется (50-100 слов)",
  "practice_question": "Вопрос для проверки понимания",
  "next_topics": ["Рекомендуемая тема 1", "Рекомендуемая тема 2"]
}}

ПРИМЕЧАНИЯ:
- Уровень {difficulty_level}: {'для начинающих, базовые концепции' if difficulty_level == 'beginner' else 'более глубокий анализ' if difficulty_level in ['intermediate', 'advanced'] else 'для экспертов, углубленный анализ'}
- Используй точные технические термины
- Добавь практические примеры
- Сделай контент интересным и полезным"""

        logger.info(f"🤖 Вызываю Gemini напрямую для {topic} ({difficulty_level})")
        
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=gemini_model,
            contents=prompt
        )
        
        if not response.text:
            logger.warning("❌ Gemini вернул пустой ответ")
            return _get_fallback_lesson(topic, difficulty_level)
        
        # Парсим JSON из ответа
        try:
            lesson_data = json.loads(response.text)
            
            # Валидируем структуру
            required_fields = ["lesson_title", "content", "key_points", "real_world_example", "practice_question", "next_topics"]
            if all(field in lesson_data for field in required_fields):
                logger.info(f"✅ Gemini создал урок: {lesson_data.get('lesson_title')}")
                lesson_data["is_gemini_direct"] = True
                return lesson_data
            else:
                logger.warning(f"⚠️ Неполная структура от Gemini: {list(lesson_data.keys())}")
                return _get_fallback_lesson(topic, difficulty_level)
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Не смог распарсить JSON от Gemini: {e}")
            logger.debug(f"Ответ Gemini: {response.text[:200]}")
            return _get_fallback_lesson(topic, difficulty_level)
            
    except Exception as e:
        logger.error(f"❌ Ошибка при вызове Gemini напрямую: {e}", exc_info=True)
        return _get_fallback_lesson(topic, difficulty_level)


async def teach_lesson_via_groq(
    topic: str,
    difficulty_level: str = "beginner"
) -> Optional[Dict[str, Any]]:
    """✅ v0.37.10: Вызывает Groq напрямую (самый быстрый ИИ)"""
    try:
        from groq import Groq
        
        groq_api_key = os.getenv("GROQ_API_KEY")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        if not groq_api_key:
            logger.debug("❌ GROQ_API_KEY не установлен")
            return None
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty_level, {})
        
        prompt = f"""Создай интерактивный урок по криптографии.

ТЕМА: {topic_info.get('name', topic)}
УРОВЕНЬ: {level_info.get('name', difficulty_level)}

ОТВЕТЬ ТОЛЬКО JSON (без markdown):
{{
  "lesson_title": "Название (до 50 символов)",
  "content": "Подробно (200-400 слов)",
  "key_points": ["Пункт 1", "Пункт 2", "Пункт 3", "Пункт 4"],
  "real_world_example": "Практический пример (50-100 слов)",
  "practice_question": "Вопрос для проверки",
  "next_topics": ["Тема 1", "Тема 2"]
}}"""

        logger.info(f"🚀 Вызываю Groq для {topic} ({difficulty_level})")
        
        client = Groq(api_key=groq_api_key)
        response = client.chat.completions.create(
            model=groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
            timeout=15.0
        )
        
        if not response.choices or not response.choices[0].message.content:
            logger.warning("❌ Groq вернул пустой ответ")
            return None
        
        text = response.choices[0].message.content
        try:
            lesson_data = json.loads(text)
            required_fields = ["lesson_title", "content", "key_points", "real_world_example", "practice_question", "next_topics"]
            if all(field in lesson_data for field in required_fields):
                logger.info(f"✅ Groq создал урок: {lesson_data.get('lesson_title')}")
                lesson_data["ai_provider"] = "groq"
                return lesson_data
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Groq вернул невалидный JSON")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ Groq ошибка: {type(e).__name__}")
        return None


async def teach_lesson_via_mistral(
    topic: str,
    difficulty_level: str = "beginner"
) -> Optional[Dict[str, Any]]:
    """✅ v0.37.10: Вызывает Mistral напрямую (fallback 1)"""
    try:
        from mistralai import Mistral
        
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        mistral_model = os.getenv("MISTRAL_MODEL", "mistral-large")
        
        if not mistral_api_key:
            logger.debug("❌ MISTRAL_API_KEY не установлен")
            return None
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty_level, {})
        
        prompt = f"""Создай интерактивный урок по криптографии.

ТЕМА: {topic_info.get('name', topic)}
УРОВЕНЬ: {level_info.get('name', difficulty_level)}

ОТВЕТЬ ТОЛЬКО JSON (без markdown):
{{
  "lesson_title": "Название (до 50 символов)",
  "content": "Подробно (200-400 слов)",
  "key_points": ["Пункт 1", "Пункт 2", "Пункт 3", "Пункт 4"],
  "real_world_example": "Практический пример (50-100 слов)",
  "practice_question": "Вопрос для проверки",
  "next_topics": ["Тема 1", "Тема 2"]
}}"""

        logger.info(f"🟣 Вызываю Mistral для {topic} ({difficulty_level})")
        
        client = Mistral(api_key=mistral_api_key)
        response = await asyncio.to_thread(
            client.chat.complete,
            model=mistral_model,
            messages=[{"role": "user", "content": prompt}],
        )
        
        if not response.choices or not response.choices[0].message.content:
            logger.warning("❌ Mistral вернул пустой ответ")
            return None
        
        text = response.choices[0].message.content
        try:
            lesson_data = json.loads(text)
            required_fields = ["lesson_title", "content", "key_points", "real_world_example", "practice_question", "next_topics"]
            if all(field in lesson_data for field in required_fields):
                logger.info(f"✅ Mistral создал урок: {lesson_data.get('lesson_title')}")
                lesson_data["ai_provider"] = "mistral"
                return lesson_data
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Mistral вернул невалидный JSON")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ Mistral ошибка: {type(e).__name__}")
        return None


async def teach_lesson_via_deepseek(
    topic: str,
    difficulty_level: str = "beginner"
) -> Optional[Dict[str, Any]]:
    """✅ v0.37.10: Вызывает DeepSeek напрямую (fallback 2)"""
    try:
        import openai
        
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        if not deepseek_api_key:
            logger.debug("❌ DEEPSEEK_API_KEY не установлен")
            return None
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty_level, {})
        
        prompt = f"""Создай интерактивный урок по криптографии.

ТЕМА: {topic_info.get('name', topic)}
УРОВЕНЬ: {level_info.get('name', difficulty_level)}

ОТВЕТЬ ТОЛЬКО JSON (без markdown):
{{
  "lesson_title": "Название (до 50 символов)",
  "content": "Подробно (200-400 слов)",
  "key_points": ["Пункт 1", "Пункт 2", "Пункт 3", "Пункт 4"],
  "real_world_example": "Практический пример (50-100 слов)",
  "practice_question": "Вопрос для проверки",
  "next_topics": ["Тема 1", "Тема 2"]
}}"""

        logger.info(f"🔵 Вызываю DeepSeek для {topic} ({difficulty_level})")
        
        client = openai.AsyncOpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        response = await client.chat.completions.create(
            model=deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
            timeout=15
        )
        
        if not response.choices or not response.choices[0].message.content:
            logger.warning("❌ DeepSeek вернул пустой ответ")
            return None
        
        text = response.choices[0].message.content
        try:
            lesson_data = json.loads(text)
            required_fields = ["lesson_title", "content", "key_points", "real_world_example", "practice_question", "next_topics"]
            if all(field in lesson_data for field in required_fields):
                logger.info(f"✅ DeepSeek создал урок: {lesson_data.get('lesson_title')}")
                lesson_data["ai_provider"] = "deepseek"
                return lesson_data
        except json.JSONDecodeError:
            logger.warning(f"⚠️ DeepSeek вернул невалидный JSON")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ DeepSeek ошибка: {type(e).__name__}")
        return None



