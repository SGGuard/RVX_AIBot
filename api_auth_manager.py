"""
🔑 API Authentication Manager - Handle API keys and tokens
v1.0 - Secure API key management and verification
"""
import os
import logging
import hashlib
import secrets
import json
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from threading import RLock
import sqlite3

logger = logging.getLogger("RVX_AUTH")

# =============================================================================
# DATABASE SETUP
# =============================================================================

DB_PATH = os.getenv("AUTH_DB_PATH", "auth_keys.db")

def init_auth_database():
    """Initialize authentication database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create API keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT UNIQUE NOT NULL,
                key_name TEXT NOT NULL,
                owner_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                rate_limit_per_minute INTEGER DEFAULT 60,
                total_requests INTEGER DEFAULT 0,
                total_errors INTEGER DEFAULT 0,
                notes TEXT
            )
        """)
        
        # Create API usage log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL,
                endpoint TEXT,
                request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_code INTEGER,
                response_time_ms INTEGER,
                success BOOLEAN,
                FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys(key_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_key ON api_usage_log(key_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_time ON api_usage_log(request_time)")
        
        conn.commit()
        conn.close()
        logger.info("✅ Auth database initialized")
    except Exception as e:
        logger.error(f"❌ Error initializing auth database: {e}")
        raise

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class APIKeyInfo:
    """Information about an API key"""
    key_hash: str
    key_name: str
    owner_name: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    rate_limit: int
    total_requests: int
    total_errors: int
    notes: str

# =============================================================================
# API KEY MANAGER
# =============================================================================

class APIKeyManager:
    """Manages API keys and authentication"""
    
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
            self._db_path = DB_PATH
            init_auth_database()
            self._key_cache = {}  # In-memory cache of active keys
            self._cache_ttl = 300  # 5 minutes
            self._last_cache_refresh = datetime.utcnow() - timedelta(seconds=self._cache_ttl)
            self._refresh_cache()
            self._initialized = True
            logger.info("✅ APIKeyManager initialized")
    
    def _get_conn(self):
        """Get database connection"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _refresh_cache(self):
        """Refresh cache of active API keys"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT key_hash, rate_limit_per_minute FROM api_keys WHERE is_active = 1")
            self._key_cache = {row['key_hash']: row['rate_limit_per_minute'] for row in cursor.fetchall()}
            self._last_cache_refresh = datetime.utcnow()
            conn.close()
            logger.debug(f"✅ Cache refreshed with {len(self._key_cache)} active keys")
        except Exception as e:
            logger.error(f"❌ Error refreshing cache: {e}")
    
    def _should_refresh_cache(self) -> bool:
        """Check if cache should be refreshed"""
        age = (datetime.utcnow() - self._last_cache_refresh).total_seconds()
        return age > self._cache_ttl
    
    def generate_api_key(self, key_name: str, owner_name: str, 
                        rate_limit: int = 60, notes: str = "") -> str:
        """
        Generate a new API key
        
        Args:
            key_name: Human-readable name for the key
            owner_name: Owner/organization name
            rate_limit: Requests per minute allowed
            notes: Additional notes
            
        Returns:
            The generated API key (only shown once!)
        """
        # Generate secure random token
        api_key = f"rvx_key_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO api_keys 
                (key_hash, key_name, owner_name, rate_limit_per_minute, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (key_hash, key_name, owner_name, rate_limit, notes))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Generated new API key: {key_name} for {owner_name}")
            
            # Refresh cache
            self._refresh_cache()
            
            return api_key  # Return unhashed key (only shown once)
        except sqlite3.IntegrityError:
            logger.error(f"❌ API key with hash already exists (collision?)")
            raise ValueError("Duplicate API key detected")
        except Exception as e:
            logger.error(f"❌ Error generating API key: {e}")
            raise
    
    def verify_api_key(self, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Verify if an API key is valid
        
        Args:
            api_key: The API key to verify
            
        Returns:
            (is_valid, error_message)
        """
        if not api_key or not api_key.startswith("rvx_key_"):
            return False, "Invalid API key format"
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Check cache first
        if self._should_refresh_cache():
            self._refresh_cache()
        
        if key_hash not in self._key_cache:
            logger.warning(f"🔐 Invalid API key attempt")
            return False, "API key not found or inactive"
        
        # Update last_used_at in database
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE key_hash = ?",
                (key_hash,)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error updating key usage: {e}")
        
        return True, None
    
    def get_api_key_info(self, api_key: str) -> Optional[APIKeyInfo]:
        """Get information about an API key"""
        if not api_key.startswith("rvx_key_"):
            return None
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key_hash, key_name, owner_name, created_at, last_used_at,
                       is_active, rate_limit_per_minute, total_requests, total_errors, notes
                FROM api_keys WHERE key_hash = ?
            """, (key_hash,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return APIKeyInfo(
                key_hash=row['key_hash'],
                key_name=row['key_name'],
                owner_name=row['owner_name'],
                created_at=datetime.fromisoformat(row['created_at']),
                last_used_at=datetime.fromisoformat(row['last_used_at']) if row['last_used_at'] else None,
                is_active=bool(row['is_active']),
                rate_limit=row['rate_limit_per_minute'],
                total_requests=row['total_requests'],
                total_errors=row['total_errors'],
                notes=row['notes']
            )
        except Exception as e:
            logger.error(f"❌ Error getting key info: {e}")
            return None
    
    def log_api_usage(self, api_key: str, endpoint: str, 
                     status_code: int, response_time_ms: int, success: bool) -> None:
        """Log API usage for rate limiting and auditing"""
        if not api_key.startswith("rvx_key_"):
            return
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO api_usage_log 
                (key_hash, endpoint, status_code, response_time_ms, success)
                VALUES (?, ?, ?, ?, ?)
            """, (key_hash, endpoint, status_code, response_time_ms, success))
            
            # Update counters
            cursor.execute("""
                UPDATE api_keys SET total_requests = total_requests + 1
                WHERE key_hash = ?
            """, (key_hash,))
            
            if not success:
                cursor.execute("""
                    UPDATE api_keys SET total_errors = total_errors + 1
                    WHERE key_hash = ?
                """, (key_hash,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error logging API usage: {e}")
    
    def disable_api_key(self, api_key: str, reason: str = "") -> bool:
        """Disable an API key"""
        if not api_key.startswith("rvx_key_"):
            return False
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE api_keys SET is_active = 0, notes = ? WHERE key_hash = ?",
                (f"Disabled: {reason}", key_hash)
            )
            conn.commit()
            conn.close()
            
            self._refresh_cache()
            logger.info(f"✅ API key disabled: {reason}")
            return True
        except Exception as e:
            logger.error(f"❌ Error disabling API key: {e}")
            return False
    
    def get_rate_limit(self, api_key: str) -> Optional[int]:
        """Get rate limit for API key (requests per minute)"""
        if not api_key.startswith("rvx_key_"):
            return None
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        if self._should_refresh_cache():
            self._refresh_cache()
        
        return self._key_cache.get(key_hash)
    
    def get_usage_stats(self, api_key: str, hours: int = 24) -> Dict:
        """Get usage statistics for an API key"""
        if not api_key.startswith("rvx_key_"):
            return {}
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Get recent usage
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls,
                    AVG(response_time_ms) as avg_response_time,
                    MAX(response_time_ms) as max_response_time
                FROM api_usage_log
                WHERE key_hash = ? AND request_time > ?
            """, (key_hash, cutoff.isoformat()))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "total_calls": row['total_calls'] or 0,
                    "successful_calls": row['successful_calls'] or 0,
                    "failed_calls": row['failed_calls'] or 0,
                    "avg_response_time_ms": round(row['avg_response_time'] or 0, 2),
                    "max_response_time_ms": row['max_response_time'] or 0,
                    "success_rate": round(
                        (row['successful_calls'] or 0) / (row['total_calls'] or 1) * 100, 2
                    )
                }
        except Exception as e:
            logger.error(f"❌ Error getting usage stats: {e}")
        
        return {}

# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

api_key_manager = APIKeyManager()

# Export
__all__ = [
    'APIKeyManager',
    'APIKeyInfo',
    'api_key_manager',
    'init_auth_database',
]
