"""
i18n (Internationalization) модуль для мультиязычной поддержки RVX AI Bot

Поддерживает:
- Русский (ru) 🇷🇺
- Украинский (uk) 🇺🇦

Использование:
    from i18n import get_text, set_user_language
    
    text = await get_text("start.greeting", user_id, name="John")
    await set_user_language(user_id, "uk")
"""

import json
import os
import sqlite3
from typing import Dict, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Директория с переводами
LOCALES_DIR = Path(__file__).parent / "locales"

# Поддерживаемые языки
SUPPORTED_LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "uk": "🇺🇦 Українська"
}

# Язык по умолчанию
DEFAULT_LANGUAGE = "ru"

# Кэш переводов в памяти
_translations_cache: Dict[str, Dict[str, str]] = {}

# Кэш языков пользователей (user_id -> language)
_user_languages_cache: Dict[int, str] = {}


def _load_translation(language: str) -> Dict[str, str]:
    """Загружает перевод для языка из JSON файла"""
    if language in _translations_cache:
        return _translations_cache[language]
    
    filepath = LOCALES_DIR / f"{language}.json"
    
    if not filepath.exists():
        logger.warning(f"Translation file not found: {filepath}")
        # Вернём русский как fallback
        if language != DEFAULT_LANGUAGE:
            return _load_translation(DEFAULT_LANGUAGE)
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            translations = json.load(f)
            _translations_cache[language] = translations
            logger.debug(f"Loaded {len(translations)} translations for language: {language}")
            return translations
    except Exception as e:
        logger.error(f"Error loading translation {language}: {e}")
        return {}


async def get_text(
    key: str, 
    user_id: Optional[int] = None, 
    language: Optional[str] = None,
    **kwargs
) -> str:
    """
    Получает переведённый текст по ключу.
    
    Args:
        key: Ключ в формате "section.key" (e.g. "start.greeting")
        user_id: ID пользователя (если не указан язык, получит его из БД)
        language: Язык (если не указан, использует язык пользователя или дефолт)
        **kwargs: Параметры для форматирования строки
    
    Returns:
        Переведённый и отформатированный текст
        
    Example:
        >>> text = await get_text("start.greeting", user_id=123, name="John")
        >>> text = await get_text("start.greeting", language="uk", name="John")
    """
    
    # Определяем язык
    if language is None:
        if user_id is not None:
            language = get_user_language(user_id)
        else:
            language = DEFAULT_LANGUAGE
    
    # Валидируем язык
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language: {language}, using default: {DEFAULT_LANGUAGE}")
        language = DEFAULT_LANGUAGE
    
    # Загружаем переводы
    translations = _load_translation(language)
    
    # Получаем текст
    text = translations.get(key, f"[MISSING: {key}]")
    
    # Форматируем с параметрами
    try:
        if kwargs:
            text = text.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing format parameter {e} for key {key}")
    
    return text


def get_user_language(user_id: int, default: Optional[str] = None) -> str:
    """
    Получает язык пользователя из кэша или БД.
    
    Args:
        user_id: ID пользователя
        default: Язык по умолчанию если не найден
    
    Returns:
        Код языка (e.g. "ru", "uk")
    """
    # Проверяем кэш
    if user_id in _user_languages_cache:
        return _user_languages_cache[user_id]
    
    # Получаем из БД
    try:
        conn = sqlite3.connect("rvx_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            lang = result[0]
            _user_languages_cache[user_id] = lang
            return lang
    except Exception as e:
        logger.warning(f"Error getting user language from DB: {e}")
    
    # Возвращаем дефолт
    return default or DEFAULT_LANGUAGE


async def set_user_language(user_id: int, language: str) -> bool:
    """
    Устанавливает язык для пользователя.
    
    Args:
        user_id: ID пользователя
        language: Код языка
    
    Returns:
        True если успешно, False если ошибка
    """
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(f"Invalid language: {language}")
        return False
    
    try:
        conn = sqlite3.connect("rvx_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET language = ? WHERE user_id = ?",
            (language, user_id)
        )
        conn.commit()
        conn.close()
        
        # Обновляем кэш
        _user_languages_cache[user_id] = language
        logger.info(f"Set language {language} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting user language: {e}")
        return False


async def get_language_selection_text() -> str:
    """Получает текст для выбора языка"""
    return await get_text("language.select_prompt", language=DEFAULT_LANGUAGE)


async def get_language_buttons() -> Dict[str, str]:
    """
    Получает кнопки выбора языков с эмодзи.
    
    Returns:
        Dict: {language_code: button_text}
    """
    buttons = {}
    for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
        buttons[lang_code] = lang_name
    return buttons


def clear_user_language_cache(user_id: Optional[int] = None) -> None:
    """
    Очищает кэш языков пользователя.
    
    Args:
        user_id: ID пользователя (если None, очищает весь кэш)
    """
    global _user_languages_cache
    
    if user_id is None:
        _user_languages_cache.clear()
        logger.info("Cleared user language cache for all users")
    else:
        if user_id in _user_languages_cache:
            del _user_languages_cache[user_id]
            logger.debug(f"Cleared language cache for user {user_id}")


def reload_translations(language: Optional[str] = None) -> None:
    """
    Перезагружает переводы из файлов.
    
    Args:
        language: Язык для перезагрузки (если None, перезагружает все)
    """
    global _translations_cache
    
    if language is None:
        _translations_cache.clear()
        logger.info("Reloaded all translations")
    else:
        if language in _translations_cache:
            del _translations_cache[language]
            logger.info(f"Reloaded translations for language: {language}")
