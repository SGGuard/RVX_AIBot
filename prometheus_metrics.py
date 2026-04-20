"""
Prometheus metrics collection and monitoring for RVX Backend.

Provides:
- Request counters (total, success, errors, rate-limited, fallback)
- Response time histograms
- Cache hit ratio
- AI provider availability tracking
- Rate limiter statistics
- Error tracking by type

Integration:
    from prometheus_metrics import (
        REQUEST_COUNTER, RESPONSE_TIME, CACHE_HIT_RATIO,
        record_request, record_error, record_cache_hit
    )
    
Usage:
    # Record metrics
    record_request(provider="gemini", success=True, time_ms=150)
    record_error(provider="deepseek", error_type="timeout")
    record_cache_hit(cache_type="response")
"""

from prometheus_client import Counter, Histogram, Gauge, Enum
import time
from typing import Optional, Dict, Any


# ============================================================================
# PROMETHEUS METRICS DEFINITIONS
# ============================================================================

# Request counters
REQUEST_COUNTER = Counter(
    'rvx_requests_total',
    'Total API requests',
    ['endpoint', 'method', 'status']
)

REQUEST_SUCCESS = Counter(
    'rvx_requests_success_total',
    'Successful API requests',
    ['endpoint', 'provider']
)

REQUEST_ERRORS = Counter(
    'rvx_requests_errors_total',
    'Failed API requests',
    ['endpoint', 'error_type']
)

REQUEST_RATE_LIMITED = Counter(
    'rvx_requests_rate_limited_total',
    'Rate-limited requests',
    ['endpoint']
)

REQUEST_FALLBACK = Counter(
    'rvx_requests_fallback_total',
    'Requests using fallback analysis',
    ['endpoint', 'fallback_reason']
)

# Response time metrics
RESPONSE_TIME = Histogram(
    'rvx_response_time_ms',
    'API response time in milliseconds',
    ['endpoint'],
    buckets=[50, 100, 200, 500, 1000, 2000, 5000, 10000]  # milliseconds
)

# Cache metrics
CACHE_HIT_RATIO = Counter(
    'rvx_cache_hits_total',
    'Cache hits by type',
    ['cache_type']  # response, subscription, etc
)

CACHE_MISS_RATIO = Counter(
    'rvx_cache_misses_total',
    'Cache misses by type',
    ['cache_type']
)

CACHE_SIZE = Gauge(
    'rvx_cache_size_bytes',
    'Current cache size in bytes',
    ['cache_type']
)

# AI provider metrics
PROVIDER_AVAILABILITY = Gauge(
    'rvx_provider_available',
    'AI provider availability (1=available, 0=down)',
    ['provider']  # gemini, deepseek, ollama
)

PROVIDER_LATENCY = Histogram(
    'rvx_provider_latency_ms',
    'Provider response latency in ms',
    ['provider'],
    buckets=[50, 100, 200, 500, 1000, 2000, 5000]
)

# Rate limiter metrics
RATE_LIMITER_STATS = Gauge(
    'rvx_rate_limiter_tracked_ips',
    'Number of IPs currently tracked by rate limiter'
)

RATE_LIMITER_BLOCKED = Gauge(
    'rvx_rate_limiter_blocked_ips',
    'Number of IPs currently blocked by rate limiter'
)

# Database metrics
DB_CONNECTION_POOL_SIZE = Gauge(
    'rvx_db_pool_available_connections',
    'Available database connections in pool'
)

DB_QUERY_TIME = Histogram(
    'rvx_db_query_time_ms',
    'Database query time in milliseconds',
    ['query_type'],  # select, insert, update, delete
    buckets=[10, 50, 100, 200, 500, 1000]
)

# Error tracking
ERROR_COUNTER = Counter(
    'rvx_errors_total',
    'Total errors by type',
    ['error_type', 'severity']  # severity: info, warning, error, critical
)

# System health
UPTIME_SECONDS = Gauge(
    'rvx_uptime_seconds',
    'Application uptime in seconds'
)


# ============================================================================
# METRIC RECORDING FUNCTIONS
# ============================================================================

def record_request(
    endpoint: str,
    method: str = "POST",
    status: int = 200,
    response_time_ms: float = 0.0,
    provider: Optional[str] = None
) -> None:
    """
    Record API request metrics.
    
    Args:
        endpoint: API endpoint path (e.g., '/explain_news')
        method: HTTP method (default: POST)
        status: HTTP status code
        response_time_ms: Response time in milliseconds
        provider: AI provider used (gemini, deepseek, ollama)
    """
    REQUEST_COUNTER.labels(endpoint=endpoint, method=method, status=status).inc()
    RESPONSE_TIME.labels(endpoint=endpoint).observe(response_time_ms)
    
    if 200 <= status < 300:
        if provider:
            REQUEST_SUCCESS.labels(endpoint=endpoint, provider=provider).inc()


def record_error(
    endpoint: str,
    error_type: str,
    severity: str = "error"
) -> None:
    """
    Record error metrics.
    
    Args:
        endpoint: API endpoint where error occurred
        error_type: Type of error (timeout, validation, database, etc.)
        severity: Error severity (info, warning, error, critical)
    """
    REQUEST_ERRORS.labels(endpoint=endpoint, error_type=error_type).inc()
    ERROR_COUNTER.labels(error_type=error_type, severity=severity).inc()


def record_rate_limit(endpoint: str) -> None:
    """Record rate-limited request."""
    REQUEST_RATE_LIMITED.labels(endpoint=endpoint).inc()


def record_fallback(endpoint: str, reason: str = "all_providers_failed") -> None:
    """
    Record fallback analysis usage.
    
    Args:
        endpoint: API endpoint
        reason: Reason for fallback (all_providers_failed, timeout, etc.)
    """
    REQUEST_FALLBACK.labels(endpoint=endpoint, fallback_reason=reason).inc()


def record_cache_hit(cache_type: str = "response") -> None:
    """
    Record cache hit.
    
    Args:
        cache_type: Type of cache (response, subscription, etc.)
    """
    CACHE_HIT_RATIO.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str = "response") -> None:
    """
    Record cache miss.
    
    Args:
        cache_type: Type of cache
    """
    CACHE_MISS_RATIO.labels(cache_type=cache_type).inc()


def set_cache_size(cache_type: str, size_bytes: int) -> None:
    """
    Update cache size metric.
    
    Args:
        cache_type: Type of cache
        size_bytes: Current cache size in bytes
    """
    CACHE_SIZE.labels(cache_type=cache_type).set(size_bytes)


def set_provider_availability(provider: str, available: bool) -> None:
    """
    Update provider availability status.
    
    Args:
        provider: Provider name (gemini, deepseek, ollama)
        available: True if provider is available
    """
    PROVIDER_AVAILABILITY.labels(provider=provider).set(1 if available else 0)


def record_provider_latency(provider: str, latency_ms: float) -> None:
    """
    Record AI provider response latency.
    
    Args:
        provider: Provider name
        latency_ms: Latency in milliseconds
    """
    PROVIDER_LATENCY.labels(provider=provider).observe(latency_ms)


def set_rate_limiter_stats(tracked_ips: int, blocked_ips: int) -> None:
    """
    Update rate limiter statistics.
    
    Args:
        tracked_ips: Number of IPs currently tracked
        blocked_ips: Number of IPs currently blocked
    """
    RATE_LIMITER_STATS.set(tracked_ips)
    RATE_LIMITER_BLOCKED.set(blocked_ips)


def set_db_pool_availability(available_connections: int) -> None:
    """
    Update database connection pool availability.
    
    Args:
        available_connections: Number of available connections
    """
    DB_CONNECTION_POOL_SIZE.set(available_connections)


def record_db_query(query_type: str, query_time_ms: float) -> None:
    """
    Record database query time.
    
    Args:
        query_type: Type of query (select, insert, update, delete)
        query_time_ms: Query execution time in milliseconds
    """
    DB_QUERY_TIME.labels(query_type=query_type).observe(query_time_ms)


def set_uptime(uptime_seconds: float) -> None:
    """
    Update application uptime.
    
    Args:
        uptime_seconds: Uptime in seconds
    """
    UPTIME_SECONDS.set(uptime_seconds)


# ============================================================================
# METRIC CONTEXT MANAGERS (for easy tracking)
# ============================================================================

class MetricsTracker:
    """
    Context manager for tracking metrics.
    
    Usage:
        with MetricsTracker(endpoint="/explain_news", provider="gemini") as tracker:
            # do work
            tracker.record_success()  # Automatically records response time
    """
    
    def __init__(self, endpoint: str, provider: Optional[str] = None):
        """Initialize tracker with endpoint and provider."""
        self.endpoint = endpoint
        self.provider = provider
        self.start_time = time.time()
        self.success = False
    
    def __enter__(self):
        """Enter context."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and record metrics."""
        elapsed_ms = (time.time() - self.start_time) * 1000
        
        if exc_type is None:
            # No exception - success
            status = 200
            self.record_success()
        else:
            # Exception occurred
            status = 500
            error_type = exc_type.__name__
            record_error(self.endpoint, error_type)
        
        record_request(
            endpoint=self.endpoint,
            method="POST",
            status=status,
            response_time_ms=elapsed_ms,
            provider=self.provider
        )
        
        return False  # Don't suppress exceptions
    
    def record_success(self) -> None:
        """Mark request as successful."""
        self.success = True
    
    def record_cache_hit(self) -> None:
        """Record cache hit for this request."""
        record_cache_hit("response")
    
    def record_fallback(self, reason: str = "all_providers_failed") -> None:
        """Record fallback usage."""
        record_fallback(self.endpoint, reason)
