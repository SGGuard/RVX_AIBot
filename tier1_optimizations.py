"""
🚀 TIER 1 QUICK WINS - v0.22.0 Optimizations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This module contains TIER 1 improvements:
1. Type hints for better IDE support
2. Redis cache for persistent caching
3. Connection pooling for database performance
4. Structured logging for analytics

Author: GitHub Copilot
Date: 2025-12-09
"""

import os
import logging
import json
import sqlite3
import time
from queue import Queue
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from functools import wraps

# ============================================================================
# 1️⃣  STRUCTURED LOGGING (python-json-logger)
# ============================================================================

try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False
    print("⚠️ python-json-logger not installed, using default logging")


class StructuredLogger:
    """Structured logging with JSON output for analytics."""
    
    def __init__(self, name: str = __name__):
        """Initialize structured logger."""
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if HAS_JSON_LOGGER and not self.logger.handlers:
            # JSON console handler
            console_handler = logging.StreamHandler()
            formatter = jsonlogger.JsonFormatter()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def log_request(
        self,
        user_id: int,
        endpoint: str,
        method: str,
        response_time_ms: float,
        status: str = "success",
        cache_hit: bool = False,
        ai_provider: Optional[str] = None,
        error: Optional[str] = None,
        **extra: Any
    ) -> None:
        """Log structured request with analytics."""
        log_data = {
            "event": "api_request",
            "user_id": user_id,
            "endpoint": endpoint,
            "method": method,
            "response_time_ms": round(response_time_ms, 2),
            "status": status,
            "cache_hit": cache_hit,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if ai_provider:
            log_data["ai_provider"] = ai_provider
        if error:
            log_data["error"] = error
        
        # Add any extra fields
        log_data.update(extra)
        
        if HAS_JSON_LOGGER:
            self.logger.info(json.dumps(log_data))
        else:
            self.logger.info(f"REQUEST: {log_data}")
    
    def log_error(
        self,
        error_type: str,
        message: str,
        user_id: Optional[int] = None,
        endpoint: Optional[str] = None,
        **extra: Any
    ) -> None:
        """Log structured error."""
        log_data = {
            "event": "error",
            "error_type": error_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if user_id:
            log_data["user_id"] = user_id
        if endpoint:
            log_data["endpoint"] = endpoint
        
        log_data.update(extra)
        
        if HAS_JSON_LOGGER:
            self.logger.error(json.dumps(log_data))
        else:
            self.logger.error(f"ERROR: {log_data}")


# Global structured logger
structured_logger = StructuredLogger()


# ============================================================================
# 2️⃣  REDIS CACHE
# ============================================================================

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    print("⚠️ redis not installed, caching disabled")


class CacheManager:
    """Unified cache manager supporting both Redis and in-memory fallback."""
    
    def __init__(self, use_redis: bool = True, redis_host: str = "localhost", redis_port: int = 6379):
        """Initialize cache manager."""
        self.use_redis = use_redis and HAS_REDIS
        self.in_memory_cache: Dict[str, Tuple[Any, float]] = {}  # (value, expiry_time)
        self.redis_client: Optional[redis.Redis] = None
        
        if self.use_redis:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                print("✅ Redis connected")
            except Exception as e:
                print(f"⚠️ Redis connection failed: {e}, falling back to in-memory cache")
                self.use_redis = False
                self.redis_client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except:
                        return value
            except Exception as e:
                print(f"⚠️ Redis GET error: {e}")
        
        # Fallback to in-memory
        if key in self.in_memory_cache:
            value, expiry_time = self.in_memory_cache[key]
            if time.time() < expiry_time:
                return value
            else:
                del self.in_memory_cache[key]
        
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> bool:
        """Set value in cache with TTL."""
        try:
            # Try Redis first
            if self.redis_client:
                try:
                    json_value = json.dumps(value) if not isinstance(value, str) else value
                    self.redis_client.setex(key, ttl_seconds, json_value)
                    return True
                except Exception as e:
                    print(f"⚠️ Redis SET error: {e}")
            
            # Fallback to in-memory
            expiry_time = time.time() + ttl_seconds
            self.in_memory_cache[key] = (value, expiry_time)
            return True
        except Exception as e:
            print(f"⚠️ Cache SET error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            if key in self.in_memory_cache:
                del self.in_memory_cache[key]
            return True
        except Exception as e:
            print(f"⚠️ Cache DELETE error: {e}")
            return False
    
    def clear_all(self) -> bool:
        """Clear all cache."""
        try:
            if self.redis_client:
                self.redis_client.flushdb()
            self.in_memory_cache.clear()
            return True
        except Exception as e:
            print(f"⚠️ Cache CLEAR error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "in_memory_size": len(self.in_memory_cache),
            "redis_connected": self.redis_client is not None
        }
        
        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats["redis_used_memory"] = info.get("used_memory", 0)
                stats["redis_keys"] = self.redis_client.dbsize()
            except:
                pass
        
        return stats


# Global cache manager
cache_manager = CacheManager(use_redis=True)


# ============================================================================
# 3️⃣  CONNECTION POOLING
# ============================================================================

class DatabaseConnectionPool:
    """Connection pool for SQLite database connections."""
    
    def __init__(self, db_path: str, pool_size: int = 10):
        """Initialize connection pool."""
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool: Queue = Queue(maxsize=pool_size)
        self.stats = {
            "created": 0,
            "total_get": 0,
            "total_return": 0,
            "errors": 0
        }
        
        # Pre-populate pool with connections
        for _ in range(pool_size):
            try:
                conn = sqlite3.connect(db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                self.pool.put(conn)
                self.stats["created"] += 1
            except Exception as e:
                print(f"⚠️ Failed to create connection: {e}")
                self.stats["errors"] += 1
    
    def get_connection(self, timeout: int = 5) -> Optional[sqlite3.Connection]:
        """Get connection from pool."""
        try:
            conn = self.pool.get(timeout=timeout)
            self.stats["total_get"] += 1
            return conn
        except Exception as e:
            print(f"⚠️ Failed to get connection from pool: {e}")
            self.stats["errors"] += 1
            return None
    
    def return_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        """Return connection to pool."""
        if conn:
            try:
                self.pool.put(conn)
                self.stats["total_return"] += 1
            except Exception as e:
                print(f"⚠️ Failed to return connection to pool: {e}")
                self.stats["errors"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            **self.stats,
            "pool_size": self.pool_size,
            "available": self.pool.qsize()
        }


# ============================================================================
# 4️⃣  TYPE HINTS AND UTILITIES
# ============================================================================

# Common type aliases for better type safety
UserId = int
MessageId = int
Timestamp = str
JsonData = Dict[str, Any]
ApiResponse = Dict[str, Any]


def with_timing(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_ms = (time.time() - start_time) * 1000
        return result, elapsed_ms
    return wrapper


def cache_with_ttl(ttl_seconds: int = 3600):
    """Decorator for caching function results in Redis."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached = cache_manager.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "StructuredLogger",
    "structured_logger",
    "CacheManager",
    "cache_manager",
    "DatabaseConnectionPool",
    "UserId",
    "MessageId",
    "Timestamp",
    "JsonData",
    "ApiResponse",
    "with_timing",
    "cache_with_ttl",
]
