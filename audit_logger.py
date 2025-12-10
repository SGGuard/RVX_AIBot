"""
📝 Audit Logger - Security and compliance logging
v1.0 - Structured audit logging for security events
"""
import os
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from threading import RLock
import sqlite3

logger = logging.getLogger("RVX_AUDIT")

# =============================================================================
# DATABASE SETUP
# =============================================================================

AUDIT_DB_PATH = os.getenv("AUDIT_LOG_PATH", "audit_logs.db")
AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", "audit.log")

def init_audit_database():
    """Initialize audit logging database"""
    try:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                result TEXT,
                source_ip TEXT,
                details TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for quick searches
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON audit_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON audit_logs(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_severity ON audit_logs(severity)")
        
        conn.commit()
        conn.close()
        logger.info("✅ Audit database initialized")
    except Exception as e:
        logger.error(f"❌ Error initializing audit database: {e}")
        raise

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AuditEvent:
    """Audit event"""
    timestamp: datetime
    event_type: str  # auth, api, action, error, warning
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    user_id: Optional[int]
    action: str
    result: str  # success, failure, warning
    source_ip: Optional[str]
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        """Convert to dict"""
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
# AUDIT LOGGER
# =============================================================================

class AuditLogger:
    """Centralized audit logging"""
    
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
            self._db_path = AUDIT_DB_PATH
            self._log_file = AUDIT_LOG_FILE
            init_audit_database()
            self._setup_file_logger()
            self._initialized = True
            logger.info("✅ AuditLogger initialized")
    
    def _setup_file_logger(self):
        """Setup file-based audit logging"""
        try:
            audit_logger = logging.getLogger("AUDIT")
            handler = logging.FileHandler(self._log_file)
            formatter = logging.Formatter(
                '%(asctime)s - [%(levelname)s] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            audit_logger.addHandler(handler)
            audit_logger.setLevel(logging.INFO)
        except Exception as e:
            logger.error(f"❌ Error setting up audit file logger: {e}")
    
    def _get_conn(self):
        """Get database connection"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def log_event(self, event: AuditEvent) -> None:
        """
        Log an audit event
        
        Args:
            event: The audit event to log
        """
        try:
            # Log to database
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO audit_logs
                (timestamp, event_type, severity, user_id, action, result, source_ip, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp.isoformat(),
                event.event_type,
                event.severity,
                event.user_id,
                event.action,
                event.result,
                event.source_ip,
                json.dumps(event.details)
            ))
            
            conn.commit()
            conn.close()
            
            # Log to file
            audit_logger = logging.getLogger("AUDIT")
            log_level = {
                "LOW": logging.INFO,
                "MEDIUM": logging.WARNING,
                "HIGH": logging.ERROR,
                "CRITICAL": logging.CRITICAL
            }.get(event.severity, logging.INFO)
            
            audit_logger.log(
                log_level,
                f"[{event.event_type.upper()}] {event.action} - Result: {event.result} - "
                f"User: {event.user_id} - Details: {json.dumps(event.details)}"
            )
        except Exception as e:
            logger.error(f"❌ Error logging audit event: {e}")
    
    def log_auth_event(self, user_id: Optional[int], action: str, 
                       result: str, source_ip: Optional[str] = None,
                       details: Optional[Dict] = None) -> None:
        """Log authentication event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="auth",
            severity="HIGH" if result == "failure" else "LOW",
            user_id=user_id,
            action=action,
            result=result,
            source_ip=source_ip,
            details=details or {}
        )
        self.log_event(event)
    
    def log_api_event(self, user_id: Optional[int], endpoint: str,
                     result: str, status_code: int, 
                     source_ip: Optional[str] = None,
                     details: Optional[Dict] = None) -> None:
        """Log API access event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="api",
            severity="MEDIUM" if status_code >= 400 else "LOW",
            user_id=user_id,
            action=f"API Call to {endpoint}",
            result=result,
            source_ip=source_ip,
            details={
                "endpoint": endpoint,
                "status_code": status_code,
                **(details or {})
            }
        )
        self.log_event(event)
    
    def log_action(self, user_id: Optional[int], action: str,
                  result: str, severity: str = "LOW",
                  source_ip: Optional[str] = None,
                  details: Optional[Dict] = None) -> None:
        """Log user action"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="action",
            severity=severity,
            user_id=user_id,
            action=action,
            result=result,
            source_ip=source_ip,
            details=details or {}
        )
        self.log_event(event)
    
    def log_error(self, error_msg: str, severity: str = "MEDIUM",
                 user_id: Optional[int] = None,
                 source_ip: Optional[str] = None,
                 details: Optional[Dict] = None) -> None:
        """Log error event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="error",
            severity=severity,
            user_id=user_id,
            action=error_msg,
            result="error",
            source_ip=source_ip,
            details=details or {}
        )
        self.log_event(event)
    
    def log_warning(self, warning_msg: str,
                   user_id: Optional[int] = None,
                   source_ip: Optional[str] = None,
                   details: Optional[Dict] = None) -> None:
        """Log warning event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="warning",
            severity="MEDIUM",
            user_id=user_id,
            action=warning_msg,
            result="warning",
            source_ip=source_ip,
            details=details or {}
        )
        self.log_event(event)
    
    def get_events(self, hours: int = 24, event_type: Optional[str] = None,
                  severity: Optional[str] = None,
                  user_id: Optional[int] = None) -> list:
        """
        Get audit events with filters
        
        Args:
            hours: Get events from last N hours
            event_type: Filter by event type (auth, api, action, etc)
            severity: Filter by severity level
            user_id: Filter by user ID
            
        Returns:
            List of audit events
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            query = "SELECT * FROM audit_logs WHERE timestamp > ?"
            params = [(datetime.utcnow() - timedelta(hours=hours)).isoformat()]
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY timestamp DESC LIMIT 1000"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            events = []
            for row in rows:
                events.append({
                    "timestamp": row['timestamp'],
                    "event_type": row['event_type'],
                    "severity": row['severity'],
                    "user_id": row['user_id'],
                    "action": row['action'],
                    "result": row['result'],
                    "source_ip": row['source_ip'],
                    "details": json.loads(row['details']) if row['details'] else {}
                })
            
            return events
        except Exception as e:
            logger.error(f"❌ Error getting audit events: {e}")
            return []
    
    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get audit statistics"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_events,
                    SUM(CASE WHEN severity = 'CRITICAL' THEN 1 ELSE 0 END) as critical_count,
                    SUM(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) as high_count,
                    SUM(CASE WHEN severity = 'MEDIUM' THEN 1 ELSE 0 END) as medium_count,
                    SUM(CASE WHEN result = 'failure' THEN 1 ELSE 0 END) as failure_count,
                    COUNT(DISTINCT user_id) as unique_users
                FROM audit_logs
                WHERE timestamp > ?
            """, (cutoff,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "total_events": row['total_events'] or 0,
                    "critical_count": row['critical_count'] or 0,
                    "high_count": row['high_count'] or 0,
                    "medium_count": row['medium_count'] or 0,
                    "failure_count": row['failure_count'] or 0,
                    "unique_users": row['unique_users'] or 0,
                }
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
        
        return {}

# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

audit_logger = AuditLogger()

# Export
__all__ = [
    'AuditLogger',
    'AuditEvent',
    'audit_logger',
    'init_audit_database',
]
