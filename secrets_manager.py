"""
🔒 Secrets Manager - Secure handling of sensitive data
v1.0 - Prevent secrets from leaking in logs and errors
"""
import os
import logging
import re
import json
from typing import Optional, Dict, Any, List, Pattern
from dataclasses import dataclass, field
from threading import RLock

logger = logging.getLogger("RVX_SECRETS")

# =============================================================================
# SECRET PATTERNS
# =============================================================================

# Regex patterns for detecting secrets
SECRET_PATTERNS: List[Pattern] = [
    re.compile(r'api[_-]?key[\s"\']*[:=][\s"\']*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'secret[\s"\']*[:=][\s"\']*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'password[\s"\']*[:=][\s"\']*([a-zA-Z0-9!@#$%^&*\-_\.]+)', re.IGNORECASE),
    re.compile(r'token[\s"\']*[:=][\s"\']*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'bearer[\s]+([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'authorization[\s"\']*[:=][\s"\']*bearer\s+([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'access[_-]?token[\s"\']*[:=][\s"\']*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'refresh[_-]?token[\s"\']*[:=][\s"\']*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE),
    re.compile(r'github[\s_-]?token[\s"\']*[:=][\s"\']*([a-zA-Z0-9_]+)', re.IGNORECASE),
    re.compile(r'database[_-]?password[\s"\']*[:=][\s"\']*([a-zA-Z0-9!@#$%^&*\-_\.]+)', re.IGNORECASE),
    re.compile(r'(sk_live_[a-zA-Z0-9_]+)', re.IGNORECASE),  # Stripe API keys
]

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MaskedSecret:
    """Information about a masked secret"""
    original_pattern: str
    masked_value: str
    secret_type: str = "unknown"
    was_logged: bool = False
    timestamp: Optional[str] = None

@dataclass
class SecretRegistry:
    """Registry of known secrets to protect"""
    registered_secrets: Dict[str, str] = field(default_factory=dict)  # name -> hash
    masked_instances: List[MaskedSecret] = field(default_factory=list)

# =============================================================================
# SECRETS MANAGER
# =============================================================================

class SecretsManager:
    """Manages secret detection, masking, and handling"""
    
    _instance = None
    _lock = RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._registry = SecretRegistry()
            self._mask_char = "*"
            self._min_show_chars = 0  # Don't show any chars from secrets
            self._max_show_chars = 0
            self._register_env_secrets()
            self._initialized = True
            logger.info("✅ SecretsManager initialized")
    
    def _register_env_secrets(self):
        """Register secrets from environment variables"""
        secret_env_vars = [
            "TELEGRAM_BOT_TOKEN",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "API_URL_NEWS",
            "DATABASE_PASSWORD",
            "REDIS_PASSWORD",
        ]
        
        for env_var in secret_env_vars:
            value = os.getenv(env_var)
            if value:
                self.register_secret(env_var, value)
    
    def register_secret(self, name: str, value: str) -> None:
        """
        Register a secret to be protected
        
        Args:
            name: Name of the secret (for reference)
            value: The secret value to protect
        """
        import hashlib
        
        secret_hash = hashlib.sha256(value.encode()).hexdigest()
        self._registry.registered_secrets[name] = secret_hash
        logger.debug(f"✅ Registered secret: {name}")
    
    def is_secret(self, value: str) -> bool:
        """Check if a value looks like a secret"""
        if not value or len(value) < 10:
            return False
        
        # Check against patterns
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                return True
        
        # Check against registered secrets
        import hashlib
        value_hash = hashlib.sha256(value.encode()).hexdigest()
        if value_hash in self._registry.registered_secrets.values():
            return True
        
        return False
    
    def mask_value(self, value: str, secret_type: str = "unknown") -> str:
        """
        Mask a secret value
        
        Args:
            value: The value to mask
            secret_type: Type of secret (api_key, password, token, etc)
            
        Returns:
            Masked value like [REDACTED-TYPE]
        """
        if not value:
            return "[EMPTY]"
        
        if len(value) <= 10:
            return "[REDACTED]"
        
        # Different masking based on type
        if secret_type == "api_key":
            return f"[REDACTED_KEY]"
        elif secret_type == "password":
            return f"[REDACTED_PASSWORD]"
        elif secret_type == "token":
            return f"[REDACTED_TOKEN]"
        else:
            return "[REDACTED]"
    
    def sanitize_string(self, text: str, log_context: bool = False) -> str:
        """
        Remove or mask secrets from a string
        
        Args:
            text: Text that might contain secrets
            log_context: If True, log detection (for analysis)
            
        Returns:
            Sanitized text with secrets masked
        """
        if not text:
            return text
        
        sanitized = text
        found_secrets = []
        
        # Check each pattern
        for pattern in SECRET_PATTERNS:
            matches = pattern.finditer(sanitized)
            for match in matches:
                secret_value = match.group(1) if match.groups() else match.group(0)
                found_secrets.append(secret_value)
                
                # Replace with masked version
                masked = self.mask_value(secret_value, "detected")
                sanitized = sanitized.replace(secret_value, masked)
        
        # Check registered secrets
        import hashlib
        words = sanitized.split()
        for word in words:
            word_hash = hashlib.sha256(word.encode()).hexdigest()
            if word_hash in self._registry.registered_secrets.values():
                masked = self.mask_value(word, "registered")
                sanitized = sanitized.replace(word, masked)
                found_secrets.append(word)
        
        if log_context and found_secrets:
            logger.warning(f"🔐 Detected {len(found_secrets)} potential secrets in log message")
        
        return sanitized
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove secrets from a dictionary
        
        Args:
            data: Dictionary that might contain secrets
            
        Returns:
            Dictionary with secrets masked
        """
        sanitized = {}
        
        for key, value in data.items():
            # Check if key name looks like a secret
            if any(pattern in key.lower() for pattern in 
                   ['password', 'token', 'secret', 'key', 'auth']):
                sanitized[key] = self.mask_value(str(value), key.lower())
            elif isinstance(value, str):
                sanitized[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_dict(item) if isinstance(item, dict)
                    else self.sanitize_string(str(item)) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def sanitize_exception(self, exception: Exception) -> str:
        """
        Sanitize exception message
        
        Args:
            exception: Exception to sanitize
            
        Returns:
            Sanitized error message
        """
        error_msg = str(exception)
        return self.sanitize_string(error_msg, log_context=True)

# =============================================================================
# SAFE LOGGING UTILITIES
# =============================================================================

class SafeLogger:
    """Wrapper for safe logging that prevents secret leaks"""
    
    def __init__(self, logger_instance: logging.Logger):
        self.logger = logger_instance
        self.secrets_manager = SecretsManager()
    
    def info(self, msg: str, *args, **kwargs) -> None:
        """Safe info logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.info(safe_msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs) -> None:
        """Safe debug logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.debug(safe_msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs) -> None:
        """Safe warning logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.warning(safe_msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs) -> None:
        """Safe error logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.error(safe_msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs) -> None:
        """Safe critical logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.critical(safe_msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs) -> None:
        """Safe exception logging"""
        safe_msg = self.secrets_manager.sanitize_string(msg)
        self.logger.exception(safe_msg, *args, **kwargs)

# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

secrets_manager = SecretsManager()

def get_safe_logger(logger_instance: logging.Logger) -> SafeLogger:
    """Get a safe logger wrapper"""
    return SafeLogger(logger_instance)

# Export
__all__ = [
    'SecretsManager',
    'SafeLogger',
    'SecretRegistry',
    'MaskedSecret',
    'secrets_manager',
    'get_safe_logger',
]
