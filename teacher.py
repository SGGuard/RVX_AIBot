"""
RVX Teaching Module - Интерактивное обучение криптографии, ИИ, Web3 и трейдингу
Версия: v1.0.0

Работает через API сервер вместо прямого обращения к Gemini
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
    """Возвращает базовый урок когда API недоступен (fallback режим)."""
    topic_info = TEACHING_TOPICS.get(topic, {"name": topic, "description": ""})
    if isinstance(topic_info, str):
        topic_info = {"name": topic_info, "description": ""}
    
    level_info = DIFFICULTY_LEVELS.get(difficulty_level, {"emoji": "📚", "name": "средний"})
    
    fallback_content = f"""
    {level_info['emoji']} {topic_info['name']}
    
    Это базовое объяснение, так как сервис обучения временно недоступен.
    Пожалуйста, попробуйте снова позже для полного интерактивного урока.
    """
    
    return {
        "lesson_title": f"{level_info['emoji']} {topic_info['name']} (offline mode)",
        "content": fallback_content.strip(),
        "key_points": [
            "Основная концепция",
            "Практическое применение",
            "Дальнейшее изучение"
        ],
        "real_world_example": "Примеры будут доступны при восстановлении сервиса обучения",
        "practice_question": "Попробуйте снова позже для проверки понимания",
        "next_topics": []
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


async def teach_lesson(
    topic: str,
    difficulty_level: str = "beginner",
    user_knowledge_context: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Создает интерактивный урок через специализированный API endpoint /teach_lesson.
    Возвращает словарь с уроком или None если ошибка.
    """
    try:
        topic = topic.lower()
        if topic not in TEACHING_TOPICS:
            topic = get_topic_by_keyword(topic)
        
        topic_info = TEACHING_TOPICS.get(topic, {})
        level_info = DIFFICULTY_LEVELS.get(difficulty_level, {})
        
        logger.info(f"📚 Подготовка урока: {topic_info.get('name', topic)} ({difficulty_level})")
        
        # Получаем API URL для связи между сервисами
        from urllib.parse import urlparse
        
        # Priority 1: Explicit TEACH_API_URL env var (for override)
        teach_api_url = os.getenv("TEACH_API_URL")
        if not teach_api_url:
            # Priority 2: API_BASE_URL env var (for Railway public URL)
            api_base_url = os.getenv("API_BASE_URL")
            if not api_base_url:
                # Priority 3: API_URL env var (Railway service URL)
                api_url = os.getenv("API_URL")
                if api_url:
                    api_base_url = api_url.rstrip('/')
                elif os.getenv("RAILWAY_ENVIRONMENT"):
                    # Priority 4: On Railway, try localhost first (if both in same network)
                    api_base_url = "http://localhost:8080"
                else:
                    # Priority 5: Local development
                    api_base_url = "http://localhost:8000"
            
            teach_api_url = f"{api_base_url}/teach_lesson"
        
        logger.debug(f"🔗 TEACH_API_URL resolved to: {teach_api_url}")
        logger.info(f"🔗 Using TEACH_API_URL: {teach_api_url}")
        logger.info(f"🔗 Environment: RAILWAY_ENVIRONMENT={os.getenv('RAILWAY_ENVIRONMENT')}, API_URL={os.getenv('API_URL')}, API_BASE_URL={os.getenv('API_BASE_URL')}")
        
        
        # Отправляем запрос на новый endpoint
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    teach_api_url,
                    json={
                        "topic": topic,
                        "difficulty_level": difficulty_level
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.error(f"❌ API ошибка {response.status_code}: {response.text[:200]}")
                    logger.warning(f"⚠️ Использую fallback урок, так как API вернул ошибку")
                    return _get_fallback_lesson(topic, difficulty_level)
                
                lesson_data = response.json()
                
                logger.info(f"📤 Получен урок: {len(str(lesson_data))} символов")
                logger.debug(f"Урок: {lesson_data}")
                
                # Проверяем, что все необходимые поля присутствуют
                required_fields = ["lesson_title", "content", "key_points", "real_world_example", "practice_question", "next_topics"]
                if all(field in lesson_data for field in required_fields):
                    logger.info(f"✅ Урок готов: {lesson_data.get('lesson_title', 'Без названия')}")
                    return lesson_data
                else:
                    logger.warning(f"⚠️ Урок имеет неполную структуру: {list(lesson_data.keys())}")
                    # Возвращаем с заполнением недостающих полей
                    for field in required_fields:
                        if field not in lesson_data:
                            if field in ["key_points", "next_topics"]:
                                lesson_data[field] = []
                            else:
                                lesson_data[field] = ""
                    return lesson_data
        
        except httpx.ConnectError as e:
            logger.error(f"❌ Connection error при запросе к {teach_api_url}: {str(e)[:100]}")
            logger.warning(f"⚠️ Используется fallback урок (API недоступен)")
            return _get_fallback_lesson(topic, difficulty_level)
        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout (30s) при запросе к {teach_api_url}")
            logger.warning(f"⚠️ Используется fallback урок (API не ответил)")
            return _get_fallback_lesson(topic, difficulty_level)
        except Exception as e:
            logger.error(f"❌ Ошибка при создании урока: {e}", exc_info=True)
            logger.warning(f"⚠️ Использую fallback урок")
            return _get_fallback_lesson(topic, difficulty_level)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в teach_lesson: {e}", exc_info=True)
        return _get_fallback_lesson(topic, difficulty_level)
        return None

