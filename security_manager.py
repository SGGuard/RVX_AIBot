"""
🔐 Security Manager - Centralized Security Module
v1.0 - Core security utilities and decorators
"""
import os
import logging
import hashlib
import secrets
import time
from typing import Optional, Callable, Any, Dict, List
from functools import wraps
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from threading import RLock
import json

logger = logging.getLogger("RVX_SECURITY")

# =============================================================================
# CONSTANTS
# =============================================================================

# Secure string constants (never log these)
SECRETS_REGEX_PATTERNS = [
    r'api[_-]?key',
    r'secret[_-]?key',
    r'password',
    r'token',
    r'bearer',
    r'authorization',
    r'x-api-key',
    r'x-auth-token',
    r'sk_live_'  # Stripe API keys
]

# Security headers for responses
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
}

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SecurityEvent:
    """Represents a security-relevant event"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: str = "unknown"
    severity: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    user_id: Optional[int] = None
    action: str = ""
    result: str = "unknown"  # success, failure, suspicious
    details: Dict[str, Any] = field(default_factory=dict)
    source_ip: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dict for logging"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "severity": self.severity,
            "user_id": self.user_id,
            "action": self.action,
            "result": self.result,
            "source_ip": self.source_ip,
            "details": self.details
        }

# =============================================================================
# SECURITY UTILITIES
# =============================================================================

class SecretManager:
    """Manages sensitive data with masking and secure handling"""
    
    @staticmethod
    def mask_api_key(api_key: str, show_chars: int = 3) -> str:
        """
        Safely mask API key for logging
        
        Args:
            api_key: The API key to mask
            show_chars: Number of characters to show at start/end
            
        Returns:
            Masked version like "abc...xyz"
        """
        if not api_key or len(api_key) <= show_chars * 2:
            return "[REDACTED]"
        return f"{api_key[:show_chars]}...{api_key[-show_chars:]}"
    
    @staticmethod
    def mask_sensitive_string(value: str, show_chars: int = 2) -> str:
        """Mask any sensitive string"""
        if not value or len(value) < 5:
            return "[REDACTED]"
        return f"{value[:show_chars]}...{value[-show_chars:]}"
    
    @staticmethod
    def sanitize_log_message(message: str) -> str:
        """
        Remove sensitive data from log message
        
        Args:
            message: Message that might contain secrets
            
        Returns:
            Message with secrets masked
        """
        import re
        
        # Check for common secret patterns in "key=value" format
        for pattern in SECRETS_REGEX_PATTERNS:
            # Replace anything that looks like "key=value" where key matches pattern
            message = re.sub(
                f'({pattern})\\s*=\\s*([^,\\s}}\\]]+)',
                f'\\1=[REDACTED]',
                message,
                flags=re.IGNORECASE
            )
        
        # Also detect standalone secrets (Stripe keys, tokens, etc.)
        # Stripe keys like sk_live_xxxxx or sk_test_xxxxx
        message = re.sub(r'sk_(live|test)_[a-zA-Z0-9]+', '[REDACTED]', message)
        
        # RVX API keys
        message = re.sub(r'rvx_key_[a-zA-Z0-9_]+', '[REDACTED]', message)
        
        return message
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate cryptographically secure random token"""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_sensitive_data(data: str, salt: Optional[str] = None) -> str:
        """
        Securely hash sensitive data for comparison
        
        Args:
            data: Data to hash
            salt: Optional salt for additional security
            
        Returns:
            SHA256 hash
        """
        if salt:
            data = salt + data
        return hashlib.sha256(data.encode()).hexdigest()

# =============================================================================
# SECURITY MANAGER
# =============================================================================

class SecurityManager:
    """Central security management"""
    
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
            self.secret_manager = SecretManager()
            self.security_events: List[SecurityEvent] = []
            self._max_events = 1000
            self._lock = RLock()
            self._initialized = True
            logger.info("✅ SecurityManager initialized")
    
    def log_security_event(self, event: SecurityEvent) -> None:
        """Log a security event"""
        with self._lock:
            self.security_events.append(event)
            
            # Keep only last N events
            if len(self.security_events) > self._max_events:
                self.security_events = self.security_events[-self._max_events:]
            
            # Log to file
            log_level = {
                "LOW": logging.INFO,
                "MEDIUM": logging.WARNING,
                "HIGH": logging.ERROR,
                "CRITICAL": logging.CRITICAL
            }.get(event.severity, logging.INFO)
            
            logger.log(log_level, f"🔐 [{event.severity}] {event.event_type}: {event.action}")
    
    def get_security_events(self, hours: int = 24) -> List[Dict]:
        """Get security events from last N hours"""
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            recent = [e for e in self.security_events if e.timestamp >= cutoff]
            return [e.to_dict() for e in recent]
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics"""
        with self._lock:
            events = self.security_events[-100:]  # Last 100
            
            stats = {
                "total_events": len(self.security_events),
                "recent_events": len(events),
                "critical_count": sum(1 for e in events if e.severity == "CRITICAL"),
                "high_count": sum(1 for e in events if e.severity == "HIGH"),
                "medium_count": sum(1 for e in events if e.severity == "MEDIUM"),
                "failures": sum(1 for e in events if e.result == "failure"),
                "suspicious": sum(1 for e in events if e.result == "suspicious"),
            }
            
            return stats

# =============================================================================
# DECORATORS
# =============================================================================

def require_https(func: Callable) -> Callable:
    """Decorator to ensure endpoint is called over HTTPS"""
    @wraps(func)
    async def wrapper(*args, request=None, **kwargs):
        if request and not request.url.scheme == "https":
            logger.warning("🔐 HTTP access attempt, redirecting to HTTPS")
            raise ValueError("This endpoint requires HTTPS")
        return await func(*args, request=request, **kwargs)
    return wrapper

def rate_limit_sensitive(max_calls: int = 5, time_window: int = 60):
    """Decorator for rate limiting sensitive operations"""
    calls = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, user_id=None, **kwargs):
            if user_id is None:
                logger.warning("⚠️ rate_limit_sensitive called without user_id")
                return await func(*args, user_id=user_id, **kwargs)
            
            now = time.time()
            key = f"{func.__name__}:{user_id}"
            
            if key not in calls:
                calls[key] = []
            
            # Clean old calls
            calls[key] = [t for t in calls[key] if now - t < time_window]
            
            if len(calls[key]) >= max_calls:
                logger.warning(f"🔐 Rate limit exceeded for {func.__name__} by user {user_id}")
                raise PermissionError(f"Too many {func.__name__} requests. Try again in {time_window}s")
            
            calls[key].append(now)
            return await func(*args, user_id=user_id, **kwargs)
        return wrapper
    return decorator

def log_security_action(action: str, severity: str = "MEDIUM"):
    """Decorator to log security-relevant actions"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, user_id=None, request=None, **kwargs):
            start_time = time.time()
            result = "unknown"
            
            try:
                output = await func(*args, user_id=user_id, request=request, **kwargs)
                result = "success"
                return output
            except PermissionError:
                result = "failure"
                raise
            except Exception as e:
                result = "failure"
                raise
            finally:
                duration = time.time() - start_time
                
                event = SecurityEvent(
                    event_type="ACTION",
                    severity=severity,
                    user_id=user_id,
                    action=action,
                    result=result,
                    source_ip=request.client.host if request else None,
                    details={"duration_ms": round(duration * 1000)}
                )
                
                security_manager = SecurityManager()
                security_manager.log_security_event(event)
        
        return wrapper
    return decorator

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_callback_data(callback_data: str, allowed_values: List[str]) -> bool:
    """
    Validate callback data is in whitelist
    
    Args:
        callback_data: Data to validate
        allowed_values: List of allowed values
        
    Returns:
        True if valid, False otherwise
    """
    if not callback_data:
        logger.warning("🔐 Empty callback_data rejected")
        return False
    
    # Extract command (before ':' if present)
    command = callback_data.split(':')[0]
    
    if command not in allowed_values:
        logger.warning(f"🔐 Invalid callback_data: {command} not in whitelist")
        return False
    
    return True

def validate_user_id(user_id: Any) -> bool:
    """Validate user_id is a positive integer"""
    try:
        uid = int(user_id)
        return uid > 0
    except (ValueError, TypeError):
        return False

def validate_request_size(size: int, max_size: int = 1024 * 100) -> bool:
    """Validate request size doesn't exceed limit (default 100KB)"""
    return 0 < size <= max_size

# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

security_manager = SecurityManager()

# Export commonly used functions
__all__ = [
    'SecurityManager',
    'SecretManager',
    'SecurityEvent',
    'security_manager',
    'require_https',
    'rate_limit_sensitive',
    'log_security_action',
    'validate_callback_data',
    'validate_user_id',
    'validate_request_size',
    'SECURITY_HEADERS',
]
