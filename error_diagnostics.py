"""
Error Diagnostics v0.27.0
Comprehensive error tracking, diagnostics, and recovery suggestions.

Features:
- Error categorization (network, API, validation, timeout)
- Detailed error context with timestamps and stack traces
- Error recovery suggestions
- Error metrics and statistics
- Error history for debugging
"""

import logging
import traceback
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock

logger = logging.getLogger(__name__)

# =============================================================================
# ERROR TYPES & CATEGORIES
# =============================================================================

class ErrorCategory(Enum):
    """Categorizes different error types."""
    NETWORK = "network"              # Connection, timeout, unreachable
    API = "api"                      # API returned error, invalid response
    VALIDATION = "validation"        # Input validation failed
    AUTHENTICATION = "authentication" # Auth token expired, invalid
    RATE_LIMIT = "rate_limit"       # Rate limited by API
    TIMEOUT = "timeout"             # Request timeout
    DATABASE = "database"           # DB connection/query error
    UNKNOWN = "unknown"             # Cannot categorize


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = 1         # Non-critical, handled gracefully
    MEDIUM = 2      # Important, needs attention
    HIGH = 3        # Critical, service degraded
    CRITICAL = 4    # System failure imminent


# =============================================================================
# ERROR TRACKING DATA STRUCTURES
# =============================================================================

@dataclass
class ErrorContext:
    """Detailed error context for debugging."""
    timestamp: float = field(default_factory=time.time)
    error_type: str = ""
    error_message: str = ""
    stack_trace: str = ""
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    request_id: Optional[str] = None
    user_id: Optional[int] = None
    endpoint: Optional[str] = None
    error_count: int = 1  # How many times this error has occurred
    recovery_attempted: bool = False
    recovery_successful: bool = False
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        data = asdict(self)
        data['category'] = self.category.value
        data['severity'] = self.severity.value
        return data
    
    def __str__(self) -> str:
        return f"[{self.category.value.upper()}] {self.error_message}"


@dataclass
class ErrorMetrics:
    """Statistics for error tracking."""
    total_errors: int = 0
    errors_by_category: Dict[str, int] = field(default_factory=lambda: {
        cat.value: 0 for cat in ErrorCategory
    })
    recovered_count: int = 0
    unrecovered_count: int = 0
    last_error_time: Optional[float] = None
    error_window_1h: int = 0  # Errors in last hour
    error_window_24h: int = 0  # Errors in last 24 hours


# =============================================================================
# ERROR DIAGNOSTICS ENGINE
# =============================================================================

class ErrorDiagnosticsEngine:
    """
    Centralized error tracking and diagnostics system.
    ✅ CRITICAL FIX #5: Enhanced error diagnostics for AI fallback chain
    """
    
    # Singleton pattern with thread-safety
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
            self._error_history: List[ErrorContext] = []
            self._max_history_size = 1000
            self._error_lock = RLock()
            self._metrics = ErrorMetrics()
            self._error_recovery_map = {}  # For tracking recovery strategies
            self._initialized = True
            logger.info("✅ ErrorDiagnosticsEngine initialized (thread-safe)")
    
    def categorize_error(self, error: Exception, endpoint: Optional[str] = None) -> ErrorCategory:
        """
        Categorize an error based on its type and message.
        
        Args:
            error: The exception that occurred
            endpoint: Optional endpoint name for context
            
        Returns:
            ErrorCategory: Categorized error type
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Network errors
        if any(x in error_str for x in ['timeout', 'connectionerror', 'connection refused']):
            return ErrorCategory.TIMEOUT if 'timeout' in error_str else ErrorCategory.NETWORK
        
        if any(x in error_str for x in ['connectionerror', 'refused', 'unreachable', 'econnrefused']):
            return ErrorCategory.NETWORK
        
        # API errors
        if 'api' in error_type or 'http' in error_type:
            if '401' in error_str or 'unauthorized' in error_str:
                return ErrorCategory.AUTHENTICATION
            if '429' in error_str or 'rate' in error_str or 'too many' in error_str:
                return ErrorCategory.RATE_LIMIT
            return ErrorCategory.API
        
        # Database errors
        if 'database' in error_type or 'sqlite' in error_type or 'sql' in error_type:
            return ErrorCategory.DATABASE
        
        # Validation errors
        if 'validation' in error_type or 'value' in error_type or 'type' in error_type:
            return ErrorCategory.VALIDATION
        
        return ErrorCategory.UNKNOWN
    
    def get_error_severity(self, category: ErrorCategory) -> ErrorSeverity:
        """
        Determine severity based on error category.
        
        Args:
            category: ErrorCategory enum value
            
        Returns:
            ErrorSeverity: Severity level
        """
        severity_map = {
            ErrorCategory.VALIDATION: ErrorSeverity.LOW,
            ErrorCategory.RATE_LIMIT: ErrorSeverity.MEDIUM,
            ErrorCategory.TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorCategory.API: ErrorSeverity.HIGH,
            ErrorCategory.NETWORK: ErrorSeverity.HIGH,
            ErrorCategory.AUTHENTICATION: ErrorSeverity.CRITICAL,
            ErrorCategory.DATABASE: ErrorSeverity.CRITICAL,
            ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM,
        }
        return severity_map.get(category, ErrorSeverity.MEDIUM)
    
    def get_recovery_suggestions(self, category: ErrorCategory) -> List[str]:
        """
        Get recovery suggestions for an error category.
        
        Args:
            category: ErrorCategory enum value
            
        Returns:
            List[str]: Suggested recovery actions
        """
        suggestions_map = {
            ErrorCategory.NETWORK: [
                "Check network connectivity",
                "Verify API endpoint is reachable",
                "Retry with exponential backoff",
                "Check firewall/proxy settings"
            ],
            ErrorCategory.API: [
                "Check API response format",
                "Verify request parameters",
                "Review API documentation",
                "Check API status page"
            ],
            ErrorCategory.TIMEOUT: [
                "Increase timeout duration",
                "Optimize request payload",
                "Check API server performance",
                "Implement request queuing"
            ],
            ErrorCategory.AUTHENTICATION: [
                "Refresh authentication token",
                "Verify API credentials",
                "Check token expiration",
                "Re-authenticate user"
            ],
            ErrorCategory.RATE_LIMIT: [
                "Implement rate limiting on client",
                "Use exponential backoff",
                "Queue requests for later",
                "Check API rate limit status"
            ],
            ErrorCategory.DATABASE: [
                "Check database connection",
                "Verify database is running",
                "Check disk space",
                "Review database logs"
            ],
            ErrorCategory.VALIDATION: [
                "Validate input format",
                "Check data types",
                "Review validation rules",
                "Check error message for details"
            ],
        }
        return suggestions_map.get(category, ["Consult logs", "Contact support"])
    
    def record_error(
        self,
        error: Exception,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[int] = None,
        recovery_attempted: bool = False,
        recovery_successful: bool = False
    ) -> ErrorContext:
        """
        Record an error with full context.
        
        Args:
            error: The exception that occurred
            endpoint: Optional endpoint name
            request_id: Optional request ID for tracing
            user_id: Optional user ID for context
            recovery_attempted: Whether recovery was attempted
            recovery_successful: Whether recovery succeeded
            
        Returns:
            ErrorContext: The recorded error context
        """
        with self._error_lock:
            # Categorize and determine severity
            category = self.categorize_error(error, endpoint)
            severity = self.get_error_severity(category)
            suggestions = self.get_recovery_suggestions(category)
            
            # Create error context
            error_context = ErrorContext(
                error_type=type(error).__name__,
                error_message=str(error)[:500],  # Truncate long messages
                stack_trace=traceback.format_exc()[:1000],  # Recent stack trace
                category=category,
                severity=severity,
                request_id=request_id,
                user_id=user_id,
                endpoint=endpoint,
                recovery_attempted=recovery_attempted,
                recovery_successful=recovery_successful,
                suggestions=suggestions
            )
            
            # Add to history (with size limit)
            self._error_history.append(error_context)
            if len(self._error_history) > self._max_history_size:
                self._error_history = self._error_history[-self._max_history_size:]
            
            # Update metrics
            self._update_metrics(error_context)
            
            # Log error with context
            log_level = logging.ERROR if severity.value >= ErrorSeverity.HIGH.value else logging.WARNING
            logger.log(
                log_level,
                f"❌ [{category.value.upper()}:{severity.name}] {str(error)[:100]} "
                f"(endpoint={endpoint}, request_id={request_id})"
            )
            
            return error_context
    
    def _update_metrics(self, error_context: ErrorContext) -> None:
        """Update error metrics based on new error."""
        self._metrics.total_errors += 1
        self._metrics.errors_by_category[error_context.category.value] += 1
        self._metrics.last_error_time = error_context.timestamp
        
        if error_context.recovery_successful:
            self._metrics.recovered_count += 1
        else:
            self._metrics.unrecovered_count += 1
        
        # Update time windows
        now = time.time()
        one_hour_ago = now - 3600
        one_day_ago = now - 86400
        
        self._metrics.error_window_1h = sum(
            1 for e in self._error_history 
            if e.timestamp > one_hour_ago
        )
        self._metrics.error_window_24h = sum(
            1 for e in self._error_history 
            if e.timestamp > one_day_ago
        )
    
    def get_error_summary(self, limit: int = 10) -> Dict:
        """
        Get summary of recent errors.
        
        Args:
            limit: Number of recent errors to include
            
        Returns:
            Dict: Error summary with metrics and recent errors
        """
        with self._error_lock:
            recent_errors = [e.to_dict() for e in self._error_history[-limit:]]
            
            return {
                "total_errors": self._metrics.total_errors,
                "errors_by_category": self._metrics.errors_by_category,
                "recovered_count": self._metrics.recovered_count,
                "unrecovered_count": self._metrics.unrecovered_count,
                "error_rate_1h": self._metrics.error_window_1h,
                "error_rate_24h": self._metrics.error_window_24h,
                "recent_errors": recent_errors
            }
    
    def should_use_fallback(self, error_category: ErrorCategory) -> bool:
        """
        Determine if fallback should be used for this error.
        
        Args:
            error_category: The category of error
            
        Returns:
            bool: True if fallback should be used
        """
        # Use fallback for API errors, timeouts, network issues
        return error_category in [
            ErrorCategory.API,
            ErrorCategory.TIMEOUT,
            ErrorCategory.NETWORK,
            ErrorCategory.RATE_LIMIT
        ]
    
    def clear_history(self) -> None:
        """Clear error history (useful for testing)."""
        with self._error_lock:
            self._error_history.clear()
            self._metrics = ErrorMetrics()
            logger.info("✅ Error history cleared")


# =============================================================================
# GLOBAL INSTANCE & CONVENIENCE FUNCTIONS
# =============================================================================

_diagnostics = ErrorDiagnosticsEngine()


def record_error(
    error: Exception,
    endpoint: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[int] = None,
    recovery_attempted: bool = False,
    recovery_successful: bool = False
) -> ErrorContext:
    """Convenience function to record an error."""
    return _diagnostics.record_error(
        error,
        endpoint=endpoint,
        request_id=request_id,
        user_id=user_id,
        recovery_attempted=recovery_attempted,
        recovery_successful=recovery_successful
    )


def get_error_summary(limit: int = 10) -> Dict:
    """Convenience function to get error summary."""
    return _diagnostics.get_error_summary(limit)


def should_use_fallback(error_category: ErrorCategory) -> bool:
    """Convenience function to check if fallback should be used."""
    return _diagnostics.should_use_fallback(error_category)


def get_diagnostics_engine() -> ErrorDiagnosticsEngine:
    """Get global diagnostics engine instance."""
    return _diagnostics
