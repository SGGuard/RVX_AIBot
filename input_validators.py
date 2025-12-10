"""
Input Validators v1.0
Полная валидация пользовательского ввода.
"""

import re
import logging
from typing import Optional, Tuple
from pydantic import BaseModel, Field, validator, ValidationError

logger = logging.getLogger(__name__)

# Константы валидации
MAX_MESSAGE_LENGTH = 4096
MIN_MESSAGE_LENGTH = 1
MAX_TOPIC_LENGTH = 100
MAX_FEEDBACK_LENGTH = 500

class UserMessageInput(BaseModel):
    """Валидированное пользовательское сообщение"""
    text: str = Field(..., min_length=MIN_MESSAGE_LENGTH, max_length=MAX_MESSAGE_LENGTH)
    
    @validator('text')
    def sanitize_text(cls, v: str) -> str:
        """Очищает опасные символы"""
        if not v or not isinstance(v, str):
            raise ValueError("Text must be non-empty string")
        
        # 1. Удаляем контрольные символы (но оставляем \n и \t)
        v = ''.join(
            char for char in v
            if ord(char) >= 32 or char in '\n\t\r'
        )
        
        # 2. Удаляем множественные переводы строк
        v = '\n'.join(
            line.rstrip() for line in v.split('\n')
            if line.strip()
        )
        
        # 3. Убираем leading/trailing пробелы
        v = v.strip()
        
        # 4. Проверяем на excessive Unicode
        if len(v) > MAX_MESSAGE_LENGTH:
            v = v[:MAX_MESSAGE_LENGTH]
        
        return v

class TopicInput(BaseModel):
    """Валидированная тема"""
    topic: str = Field(..., min_length=1, max_length=MAX_TOPIC_LENGTH)
    
    @validator('topic')
    def validate_topic(cls, v: str) -> str:
        """Валидирует формат темы"""
        v = v.strip()
        
        # Только буквы, цифры, пробелы, дефисы
        if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-\.]+$', v):
            raise ValueError("Topic contains invalid characters")
        
        return v

class FeedbackInput(BaseModel):
    """Валидированный feedback"""
    feedback: str = Field(..., min_length=1, max_length=MAX_FEEDBACK_LENGTH)
    rating: int = Field(..., ge=1, le=5)  # 1-5 stars
    
    @validator('feedback')
    def validate_feedback(cls, v: str) -> str:
        """Валидирует feedback текст"""
        v = v.strip()
        
        # Удаляем контрольные символы
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\t')
        
        return v

def validate_user_input(text: str) -> Tuple[bool, Optional[str]]:
    """
    Валидирует пользовательский ввод.
    
    Returns:
        (is_valid, error_message)
    """
    if not isinstance(text, str):
        return False, "Input must be string"
    
    try:
        input_data = UserMessageInput(text=text)
        return True, None
    
    except ValidationError as e:
        # Извлекаем первую ошибку
        first_error = e.errors()[0]
        error_msg = f"{first_error['loc'][0]}: {first_error['msg']}"
        logger.warning(f"⚠️ Validation error: {error_msg}")
        return False, error_msg
    
    except Exception as e:
        logger.error(f"❌ Unexpected validation error: {e}")
        return False, "Invalid input"

def sanitize_for_display(text: str, max_length: int = 500) -> str:
    """Очищает текст для отображения в Telegram"""
    # Удаляем контрольные символы
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    # Обрезаем если слишком длинный
    if len(text) > max_length:
        text = text[:max_length-3] + "..."
    
    return text
