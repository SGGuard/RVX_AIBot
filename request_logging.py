"""
Request Logging & Tracing v0.27.0
Comprehensive request logging with request IDs and detailed metrics.

Features:
- Unique request ID generation and propagation
- Structured logging with request context
- Request timing and performance metrics
- Request/response logging
- Debug mode for detailed logging
"""

import logging
import time
import uuid
import json
from typing import Dict, Optional, Any
from datetime import datetime
from threading import local
import contextlib

logger = logging.getLogger(__name__)

# Thread-local storage for request context
_request_context = local()


# =============================================================================
# REQUEST ID MANAGEMENT
# =============================================================================

def generate_request_id(prefix: str = "req") -> str:
    """
    Generate unique request ID.
    
    Args:
        prefix: Prefix for request ID
        
    Returns:
        str: Unique request ID (e.g., "req_a1b2c3d4e5f6...")
    """
    unique_id = str(uuid.uuid4())[:8]
    timestamp = str(int(time.time() * 1000))[-6:]
    return f"{prefix}_{timestamp}_{unique_id}"


def get_request_id() -> Optional[str]:
    """
    Get current request ID from thread-local context.
    
    Returns:
        str: Request ID or None if not set
    """
    return getattr(_request_context, 'request_id', None)


def set_request_id(request_id: str) -> None:
    """
    Set request ID in thread-local context.
    
    Args:
        request_id: Request ID to set
    """
    _request_context.request_id = request_id


@contextlib.contextmanager
def request_context(request_id: Optional[str] = None, **context_data):
    """
    Context manager for setting request context.
    
    Args:
        request_id: Request ID (generates if None)
        **context_data: Additional context data
        
    Example:
        with request_context() as req_id:
            logger.info(f"Processing request {req_id}")
    """
    if request_id is None:
        request_id = generate_request_id()
    
    old_id = get_request_id()
    set_request_id(request_id)
    
    try:
        yield request_id
    finally:
        if old_id:
            set_request_id(old_id)
        else:
            _request_context.request_id = None


# =============================================================================
# STRUCTURED LOGGING
# =============================================================================

class RequestLogger:
    """
    Structured logger for HTTP requests and API calls.
    ✅ CRITICAL FIX #7: Detailed request logging with request IDs
    """
    
    def __init__(self, name: str = "request_logger"):
        self.logger = logging.getLogger(name)
        self.debug_mode = False
    
    def _format_message(self, msg: str, **context) -> str:
        """Format log message with context."""
        request_id = get_request_id()
        prefix = f"[{request_id}]" if request_id else "[no-id]"
        return f"{prefix} {msg}"
    
    def set_debug_mode(self, enabled: bool) -> None:
        """Enable/disable debug logging."""
        self.debug_mode = enabled
        level = logging.DEBUG if enabled else logging.INFO
        self.logger.setLevel(level)
    
    def log_request(
        self,
        method: str,
        endpoint: str,
        path: Optional[str] = None,
        query_params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        body: Optional[Any] = None
    ) -> str:
        """
        Log incoming request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Endpoint name/path
            path: Full request path
            query_params: Query parameters
            headers: Request headers
            body: Request body
            
        Returns:
            str: Request ID
        """
        request_id = get_request_id()
        
        msg_parts = [
            f"🔵 REQUEST: {method} {endpoint}",
            f"path={path}" if path else None,
        ]
        msg = " | ".join(filter(None, msg_parts))
        
        self.logger.info(self._format_message(msg))
        
        if self.debug_mode:
            if query_params:
                self.logger.debug(f"  query_params: {query_params}")
            if headers:
                safe_headers = {k: v if k.lower() not in ['authorization', 'token', 'key'] else '***' for k, v in headers.items()}
                self.logger.debug(f"  headers: {safe_headers}")
            if body:
                body_str = json.dumps(body, default=str)[:500] if isinstance(body, dict) else str(body)[:500]
                self.logger.debug(f"  body: {body_str}")
        
        return request_id
    
    def log_response(
        self,
        status_code: int,
        elapsed_ms: float,
        response_size: int = 0,
        response_data: Optional[Any] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log outgoing response.
        
        Args:
            status_code: HTTP status code
            elapsed_ms: Response time in milliseconds
            response_size: Response size in bytes
            response_data: Response body
            error: Error message if failed
        """
        if error:
            msg = f"🔴 RESPONSE: {status_code} | {elapsed_ms:.0f}ms | ERROR: {error}"
            self.logger.error(self._format_message(msg))
        elif status_code >= 400:
            msg = f"🟠 RESPONSE: {status_code} | {elapsed_ms:.0f}ms | size={response_size}B"
            self.logger.warning(self._format_message(msg))
        else:
            msg = f"🟢 RESPONSE: {status_code} | {elapsed_ms:.0f}ms | size={response_size}B"
            self.logger.info(self._format_message(msg))
        
        if self.debug_mode and response_data:
            data_str = json.dumps(response_data, default=str)[:500]
            self.logger.debug(self._format_message(f"  response: {data_str}"))
    
    def log_api_call(
        self,
        provider: str,
        operation: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> None:
        """
        Log API call to external service.
        
        Args:
            provider: API provider name (e.g., 'gemini', 'deepseek')
            operation: Operation name (e.g., 'analyze', 'generate')
            duration_ms: Operation duration in milliseconds
            success: Whether operation succeeded
            error: Error message if failed
            details: Additional details
        """
        icon = "✅" if success else "❌"
        msg = f"{icon} API CALL: {provider}/{operation} ({duration_ms:.0f}ms)"
        
        if success:
            self.logger.info(self._format_message(msg))
        else:
            self.logger.error(self._format_message(f"{msg} - ERROR: {error}"))
        
        if self.debug_mode and details:
            details_str = json.dumps(details, default=str)[:300]
            self.logger.debug(self._format_message(f"  details: {details_str}"))
    
    def log_db_operation(
        self,
        operation: str,
        table: str,
        duration_ms: float,
        rows_affected: int = 0,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """
        Log database operation.
        
        Args:
            operation: Operation type (SELECT, INSERT, UPDATE, DELETE)
            table: Table name
            duration_ms: Operation duration
            rows_affected: Number of rows affected
            success: Whether operation succeeded
            error: Error message if failed
        """
        icon = "✅" if success else "❌"
        msg = f"{icon} DB: {operation} on {table} ({duration_ms:.1f}ms)"
        
        if rows_affected:
            msg += f" | rows={rows_affected}"
        
        if success:
            self.logger.debug(self._format_message(msg))
        else:
            self.logger.error(self._format_message(f"{msg} - ERROR: {error}"))
    
    def log_cache_hit(self, cache_type: str, key: str, ttl_remaining_s: Optional[float] = None) -> None:
        """
        Log cache hit.
        
        Args:
            cache_type: Cache type (e.g., 'response', 'message', 'db')
            key: Cache key
            ttl_remaining_s: TTL remaining in seconds
        """
        msg = f"💾 CACHE HIT: {cache_type}"
        if ttl_remaining_s is not None:
            msg += f" | ttl={ttl_remaining_s:.0f}s"
        self.logger.debug(self._format_message(msg))
    
    def log_cache_miss(self, cache_type: str, key: str) -> None:
        """
        Log cache miss.
        
        Args:
            cache_type: Cache type
            key: Cache key
        """
        msg = f"📌 CACHE MISS: {cache_type}"
        self.logger.debug(self._format_message(msg))
    
    def log_retry(self, operation: str, attempt: int, max_attempts: int, delay_s: float) -> None:
        """
        Log retry attempt.
        
        Args:
            operation: Operation being retried
            attempt: Current attempt number
            max_attempts: Maximum attempts
            delay_s: Delay before next attempt
        """
        msg = f"🔄 RETRY: {operation} [{attempt}/{max_attempts}] | waiting {delay_s:.1f}s"
        self.logger.warning(self._format_message(msg))
    
    def log_fallback(self, reason: str, original_error: Optional[str] = None) -> None:
        """
        Log fallback to alternative operation.
        
        Args:
            reason: Why fallback is being used
            original_error: Original error that triggered fallback
        """
        msg = f"⚙️ FALLBACK: {reason}"
        if original_error:
            msg += f" | error: {original_error[:100]}"
        self.logger.warning(self._format_message(msg))
    
    def log_performance_warning(self, operation: str, duration_ms: float, threshold_ms: float) -> None:
        """
        Log operation exceeding performance threshold.
        
        Args:
            operation: Operation name
            duration_ms: Actual duration
            threshold_ms: Expected threshold
        """
        msg = f"⚡ PERF WARNING: {operation} took {duration_ms:.0f}ms (threshold: {threshold_ms:.0f}ms)"
        self.logger.warning(self._format_message(msg))


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_request_logger = RequestLogger()


def get_request_logger() -> RequestLogger:
    """Get global request logger instance."""
    return _request_logger


# Convenience functions
def log_request(method: str, endpoint: str, **kwargs) -> str:
    """Log request."""
    return _request_logger.log_request(method, endpoint, **kwargs)


def log_response(status_code: int, elapsed_ms: float, **kwargs) -> None:
    """Log response."""
    _request_logger.log_response(status_code, elapsed_ms, **kwargs)


def log_api_call(provider: str, operation: str, duration_ms: float, success: bool, **kwargs) -> None:
    """Log API call."""
    _request_logger.log_api_call(provider, operation, duration_ms, success, **kwargs)
