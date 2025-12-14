"""
Unified Validation System (DRY Principle)
==========================================

Centralized validation for the entire project to avoid code duplication.
"""

from .text_validator import TextValidator, ValidationResult, ValidationError
from .security_validator import SecurityValidator

__all__ = [
    "TextValidator",
    "ValidationResult",
    "ValidationError",
    "SecurityValidator",
]
