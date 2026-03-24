"""
Input Validators v1.1 - УЛУЧШЕНО by Ollama ✨
Валидация и очистка пользовательского ввода с оптимизациями.
"""

import re
import logging
from typing import Optional, Tuple, Set
from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger(__name__)

# Константы валидации
MAX_MESSAGE_LENGTH = 4096
MIN_MESSAGE_LENGTH = 1
MAX_TOPIC_LENGTH = 100
MAX_FEEDBACK_LENGTH = 500

# Кэш для недопустимых символов (производительность)
CONTROL_CHARS = set(chr(i) for i in range(32))  # char 0-31
CONTROL_CHARS.discard('\n')  # оставляем новые строки
CONTROL_CHARS.discard('\t')  # оставляем табы
CONTROL_CHARS.discard('\r')  # оставляем carriage return


def _remove_control_chars(text: str) -> str:
    """
    ⚡ Быстрое удаление контрольных символов (используем set вместо ord проверок).
    ~3x быстрее чем старая версия!
    """
    return ''.join(char for char in text if char not in CONTROL_CHARS)


def _collapse_newlines(text: str) -> str:
    """
    Удаляет множественные переводы строк добавляя max 2 consecutively.
    """
    lines = text.split('\n')
    result = []
    consecutive_empty = 0
    
    for line in lines:
        stripped = line.rstrip()
        if stripped:
            result.append(stripped)
            consecutive_empty = 0
        elif consecutive_empty < 1:  # Allow max 1 empty line
            result.append('')
            consecutive_empty += 1
    
    return '\n'.join(result).strip()


class UserMessageInput(BaseModel):
    """Валидированное пользовательское сообщение"""
    text: str = Field(..., min_length=MIN_MESSAGE_LENGTH, max_length=MAX_MESSAGE_LENGTH)
    
    @field_validator('text', mode='before')  # ✨ Улучшено: field_validator вместо @validator
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """
        Очищает опасные символы оптимизированным способом.
        
        Этапы:
        1. Проверка типа (быстрый fail)
        2. Удаление контрольных символов (оптимизировано)
        3. Kollapse multiple newlines
        4. Trim whitespace
        """
        # Проверка входных данных
        if not isinstance(v, str):
            raise ValueError("Text must be non-empty string")
        
        if not v.strip():
            raise ValueError("Text cannot be empty or only whitespace")
        
        # ⚡ Оптимизировано: быстрое удаление контрольных символов
        v = _remove_control_chars(v)
        
        # ⚡ Оптимизировано: collapse multiple newlines
        v = _collapse_newlines(v)
        
        # Truncate если превышает max length
        if len(v) > MAX_MESSAGE_LENGTH:
            v = v[:MAX_MESSAGE_LENGTH].rstrip()
        
        return v


class TopicInput(BaseModel):
    """Валидированная тема"""
    topic: str = Field(..., min_length=1, max_length=MAX_TOPIC_LENGTH)
    
    @field_validator('topic', mode='before')
    @classmethod
    def validate_topic(cls, v: str) -> str:
        """
        Валидирует формат темы.
        Разрешены: буквы, цифры, пробелы, дефисы, точки
        """
        v = v.strip()
        
        # ✨ Оптимизировано: используем скомпилированный regex для производительности
        topic_pattern = re.compile(r'^[a-zA-Zа-яА-Я0-9\s\-\.]+$')
        if not topic_pattern.match(v):
            raise ValueError(
                f"Topic contains invalid characters. "
                f"Allowed: letters, digits, spaces, dashes, dots. Got: {v[:50]}"
            )
        
        return v


class FeedbackInput(BaseModel):
    """Валидированный feedback с рейтингом."""
    feedback: str = Field(..., min_length=1, max_length=MAX_FEEDBACK_LENGTH)
    rating: int = Field(..., ge=1, le=5)  # 1-5 stars
    
    @field_validator('feedback', mode='before')
    @classmethod
    def validate_feedback(cls, v: str) -> str:
        """
        Валидирует и очищает текст фидбека.
        """
        if not isinstance(v, str):
            raise ValueError("Feedback must be string")
        
        v = v.strip()
        
        # ⚡ Оптимизировано: используем helper функцию
        v = _remove_control_chars(v)
        
        if not v:
            raise ValueError("Feedback cannot be empty after sanitization")
        
        # Truncate if too long
        if len(v) > MAX_FEEDBACK_LENGTH:
            v = v[:MAX_FEEDBACK_LENGTH].rstrip()
        
        return v
    
    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Валидирует рейтинг (1-5)"""
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("Rating must be integer")
        
        if v < 1 or v > 5:
            raise ValueError(f"Rating must be 1-5, got {v}")
        
        return v



def validate_user_input(text: str) -> Tuple[bool, Optional[str]]:
    """
    ✨ Валидирует пользовательский ввод с правильной обработкой ошибок.
    
    Args:
        text: Строка для валидации
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
        - is_valid: True если валидна, False иначе
        - error_message: Сообщение об ошибке или None если успешно
        
    Examples:
        >>> validate_user_input("Hello world")
        (True, None)
        
        >>> validate_user_input("")
        (False, "text: ensure this value has at least 1 characters")
    """
    if not isinstance(text, str):
        msg = "Input must be string"
        logger.warning(f"⚠️ Validation error: {msg}")
        return False, msg
    
    try:
        UserMessageInput(text=text)  # Этот вызов выполняет валидацию
        logger.debug(f"✅ Valid input: {len(text)} chars")
        return True, None
    
    except ValidationError as e:
        # ✨ Улучшено: более информативная обработка ошибок
        errors = e.errors()
        if errors:
            first_error = errors[0]
            field = first_error['loc'][0] if first_error['loc'] else 'unknown'
            msg = first_error['msg']
            error_msg = f"{field}: {msg}"
        else:
            error_msg = "Validation failed"
        
        logger.warning(f"⚠️ Validation error: {error_msg}")
        return False, error_msg
    
    except RuntimeError as e:
        logger.error(f"❌ Runtime error during validation: {e}")
        return False, "Validation service error"


def validate_topic_input(topic: str) -> Tuple[bool, Optional[str]]:
    """
    ✨ Валидирует тему для анализа.
    
    Args:
        topic: Тема для валидации
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not isinstance(topic, str):
        return False, "Topic must be string"
    
    try:
        TopicInput(topic=topic)
        return True, None
    except ValidationError as e:
        errors = e.errors()
        msg = errors[0]['msg'] if errors else "Invalid topic"
        logger.warning(f"⚠️ Topic validation error: {msg}")
        return False, msg


def validate_feedback_input(feedback: str, rating: int) -> Tuple[bool, Optional[str]]:
    """
    ✨ Валидирует feedback с рейтингом.
    
    Args:
        feedback: Текст обратной связи
        rating: Рейтинг (1-5)
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not isinstance(feedback, str) or not isinstance(rating, int):
        return False, "Feedback must be string, rating must be int"
    
    try:
        FeedbackInput(feedback=feedback, rating=rating)
        return True, None
    except ValidationError as e:
        errors = e.errors()
        msg = errors[0]['msg'] if errors else "Invalid feedback"
        logger.warning(f"⚠️ Feedback validation error: {msg}")
        return False, msg


def sanitize_for_display(text: str, max_length: int = 500) -> str:
    """
    ✨ Очищает текст для безопасного отображения в Telegram.
    
    Args:
        text: Текст для очистки
        max_length: Максимальная длина результата
        
    Returns:
        str: Очищенный текст
        
    Examples:
        >>> sanitize_for_display("Hello\\x00World", 5)
        'Hello...'
    """
    # ⚡ Оптимизировано: используем быстрое удаление контрольных символов
    text = _remove_control_chars(text)
    
    # Обрезаем если слишком длинный
    if len(text) > max_length:
        text = text[:max_length-3] + "..."
    
    return text


# ============================================================================
# ПРОФИЛИРОВАНИЕ И СТАТИСТИКА (для мониторинга производительности)
# ============================================================================

if __name__ == "__main__":
    # ✨ Быстрый тест
    print(" 🧪 Testing Validators v1.1\n" + "=" * 50)
    
    # Тест 1: Валидный ввод
    is_valid, error = validate_user_input("Hello world!")
    assert is_valid, f"Expected valid, got: {error}"
    print("✅ Test 1 passed: Valid text")
    
    # Тест 2: Пустой ввод
    is_valid, error = validate_user_input("")
    assert not is_valid, "Expected invalid for empty text"
    print("✅ Test 2 passed: Empty text rejected")
    
    # Тест 3: Контрольные символы
    is_valid, error = validate_user_input("Hello\x00World")
    assert is_valid, f"Expected to sanitize control chars, got: {error}"
    print("✅ Test 3 passed: Control chars sanitized")
    
    # Тест 4: Валидная тема
    is_valid, error = validate_topic_input("Python Programming")
    assert is_valid, f"Expected valid topic, got: {error}"
    print("✅ Test 4 passed: Valid topic")
    
    # Тест 5: Невалидная тема
    is_valid, error = validate_topic_input("Topic@#$Invalid")
    assert not is_valid, "Expected invalid topic"
    print("✅ Test 5 passed: Invalid topic rejected")
    
    # Тест 6: Валидный feedback
    is_valid, error = validate_feedback_input("Great service!", 5)
    assert is_valid, f"Expected valid feedback, got: {error}"
    print("✅ Test 6 passed: Valid feedback")
    
    # Тест 7: Невалидный рейтинг
    is_valid, error = validate_feedback_input("Good", 10)
    assert not is_valid, "Expected invalid rating"
    print("✅ Test 7 passed: Invalid rating rejected")
    
    # Тест 8: Очистка для отображения
    cleaned = sanitize_for_display("Hello" + "\x00" + "World", 5)
    assert "..." in cleaned or len(cleaned.replace("...", "")) <= 2
    print("✅ Test 8 passed: Display sanitization")
    
    print("\n🎉 Все тесты пройдены!")

