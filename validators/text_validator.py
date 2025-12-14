"""
Text Validation Module (DRY - Single Source of Truth)
=====================================================

All text validation rules are centralized here.
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import re


class ValidationError(Exception):
    """Raised when validation fails"""
    pass


@dataclass
class ValidationResult:
    """Result of validation check"""
    is_valid: bool
    errors: List[str]
    
    def __bool__(self) -> bool:
        return self.is_valid
    
    def error_message(self) -> str:
        """Returns formatted error message"""
        if not self.errors:
            return ""
        return "❌ " + "\n❌ ".join(self.errors)


class TextValidationRule(Enum):
    """Central configuration for text validation (KISS principle)"""
    MIN_LENGTH = 1
    MAX_LENGTH = 4096
    REQUIRE_NON_EMPTY = True


class TextValidator:
    """
    Centralized text validator (DRY principle)
    
    Usage:
        from validators import TextValidator
        
        result = TextValidator.validate(user_input)
        if not result:
            print(result.error_message())
    """
    
    # Single source of truth for validation rules
    MIN_LENGTH = TextValidationRule.MIN_LENGTH.value
    MAX_LENGTH = TextValidationRule.MAX_LENGTH.value
    
    @classmethod
    def validate(cls, text: Optional[str]) -> ValidationResult:
        """
        Validates text and returns detailed result
        
        Args:
            text: Text to validate
            
        Returns:
            ValidationResult with is_valid flag and error list
        """
        errors = []
        
        # Check for None or non-string
        if text is None:
            errors.append("Text is required (cannot be None)")
            return ValidationResult(is_valid=False, errors=errors)
        
        # Convert to string if needed
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                errors.append("Cannot convert input to text")
                return ValidationResult(is_valid=False, errors=errors)
        
        # Check empty after strip
        if not text or not text.strip():
            errors.append(f"Text cannot be empty")
            return ValidationResult(is_valid=False, errors=errors)
        
        # Use stripped version for length checks
        text = text.strip()
        
        # Check minimum length
        if len(text) < cls.MIN_LENGTH:
            errors.append(
                f"Text is too short (minimum {cls.MIN_LENGTH} character)"
            )
        
        # Check maximum length
        if len(text) > cls.MAX_LENGTH:
            errors.append(
                f"Text is too long (maximum {cls.MAX_LENGTH} characters, got {len(text)})"
            )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )
    
    @classmethod
    def validate_or_raise(cls, text: Optional[str]) -> str:
        """
        Validates text or raises exception
        
        Args:
            text: Text to validate
            
        Returns:
            Validated (stripped) text
            
        Raises:
            ValidationError: If validation fails
        """
        result = cls.validate(text)
        if not result.is_valid:
            raise ValidationError("; ".join(result.errors))
        return text.strip() if isinstance(text, str) else str(text).strip()
    
    @classmethod
    def truncate(cls, text: str, max_length: Optional[int] = None) -> str:
        """
        Truncates text to maximum length with ellipsis
        
        Args:
            text: Text to truncate
            max_length: Maximum length (uses class default if None)
            
        Returns:
            Truncated text
        """
        if max_length is None:
            max_length = cls.MAX_LENGTH
        
        if len(text) <= max_length:
            return text
        
        return text[:max_length - 3] + "..."
