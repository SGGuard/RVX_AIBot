"""
🛡️ Security Middleware - FastAPI middleware for security enforcement
v1.0 - Rate limiting, authentication, logging
"""
import time
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from threading import RLock
from functools import lru_cache

from fastapi import Request, HTTPException, status

logger = logging.getLogger("RVX_MIDDLEWARE")

# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """Per-IP and per-key rate limiting"""
    
    def __init__(self, requests_per_minute: int = 60, window_seconds: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
        self._lock = RLock()
    
    def is_allowed(self, identifier: str) -> Tuple[bool, Optional[str]]:
        """
        Check if request is allowed under rate limit
        
        Args:
            identifier: IP address or API key hash
            
        Returns:
            (is_allowed, error_message)
        """
        with self._lock:
            now = time.time()
            
            # Initialize if first request
            if identifier not in self.requests:
                self.requests[identifier] = []
            
            # Remove old requests outside window
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if now - req_time < self.window_seconds
            ]
            
            # Check limit
            if len(self.requests[identifier]) >= self.requests_per_minute:
                return False, f"Rate limited: {self.requests_per_minute} requests per minute"
            
            # Record this request
            self.requests[identifier].append(now)
            return True, None
    
    def get_stats(self, identifier: str) -> Dict:
        """Get rate limit stats for identifier"""
        with self._lock:
            if identifier not in self.requests:
                return {"requests": 0, "limit": self.requests_per_minute}
            
            now = time.time()
            recent = [t for t in self.requests[identifier] if now - t < self.window_seconds]
            
            return {
                "requests": len(recent),
                "limit": self.requests_per_minute,
                "remaining": self.requests_per_minute - len(recent)
            }

# =============================================================================
# REQUEST VALIDATOR
# =============================================================================

class RequestValidator:
    """Validates incoming requests"""
    
    # Maximum request body size (100KB)
    MAX_BODY_SIZE = 1024 * 100
    
    # Allowed content types
    ALLOWED_CONTENT_TYPES = [
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ]
    
    @staticmethod
    def validate_content_length(request: Request) -> Tuple[bool, Optional[str]]:
        """Validate request body size"""
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                size = int(content_length)
                if size > RequestValidator.MAX_BODY_SIZE:
                    return False, f"Request too large: {size} > {RequestValidator.MAX_BODY_SIZE}"
            except ValueError:
                return False, "Invalid Content-Length header"
        
        return True, None
    
    @staticmethod
    def validate_content_type(request: Request) -> Tuple[bool, Optional[str]]:
        """Validate content type"""
        if request.method in ["GET", "HEAD", "DELETE"]:
            return True, None  # No body expected
        
        content_type = request.headers.get("content-type", "").lower()
        
        if not content_type:
            return False, "Missing Content-Type header"
        
        # Check if content type is allowed (ignore charset parameter)
        base_type = content_type.split(";")[0].strip()
        
        if base_type not in RequestValidator.ALLOWED_CONTENT_TYPES:
            return False, f"Invalid Content-Type: {base_type}"
        
        return True, None

# =============================================================================
# SECURITY HEADERS
# =============================================================================

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# =============================================================================
# MIDDLEWARE FUNCTIONS
# =============================================================================

# Create global rate limiter
rate_limiter = RateLimiter(requests_per_minute=60)

async def security_headers_middleware(request: Request, call_next):
    """Add security headers to responses"""
    response = await call_next(request)
    
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

async def request_validation_middleware(request: Request, call_next):
    """Validate incoming requests"""
    
    # Validate content length
    is_valid, error = RequestValidator.validate_content_length(request)
    if not is_valid:
        logger.warning(f"🔐 Invalid request size: {error}")
        raise HTTPException(status_code=413, detail=error)
    
    # Validate content type
    is_valid, error = RequestValidator.validate_content_type(request)
    if not is_valid:
        logger.warning(f"🔐 Invalid content type: {error}")
        raise HTTPException(status_code=415, detail=error)
    
    response = await call_next(request)
    return response

async def rate_limit_middleware(request: Request, call_next):
    """Rate limit requests by IP"""
    
    # Get client IP (handle X-Forwarded-For for proxies)
    client_ip = request.headers.get("X-Forwarded-For", request.client.host)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    
    # Check rate limit
    is_allowed, error = rate_limiter.is_allowed(client_ip)
    
    if not is_allowed:
        logger.warning(f"🔐 Rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=429,
            detail=error,
            headers={"Retry-After": "60"}
        )
    
    response = await call_next(request)
    
    # Add rate limit headers
    stats = rate_limiter.get_stats(client_ip)
    response.headers["X-RateLimit-Limit"] = str(stats["limit"])
    response.headers["X-RateLimit-Remaining"] = str(stats["remaining"])
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
    
    return response

async def request_logging_middleware(request: Request, call_next):
    """Log all requests"""
    start_time = time.time()
    
    # Get client IP
    client_ip = request.headers.get("X-Forwarded-For", request.client.host)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    
    # Log request
    logger.debug(
        f"📨 {request.method} {request.url.path} from {client_ip}"
    )
    
    try:
        response = await call_next(request)
        
        # Log response
        duration = time.time() - start_time
        logger.debug(
            f"✅ {request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)"
        )
        
        # Add timing header
        response.headers["X-Response-Time"] = str(duration)
        
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"❌ {request.method} {request.url.path} -> ERROR ({duration:.3f}s): {e}"
        )
        raise

# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'RateLimiter',
    'RequestValidator',
    'rate_limiter',
    'security_headers_middleware',
    'request_validation_middleware',
    'rate_limit_middleware',
    'request_logging_middleware',
    'SECURITY_HEADERS',
]
