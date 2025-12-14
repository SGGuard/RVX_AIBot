"""
Database Service (DAL - Data Access Layer)
==========================================

Centralized database access to avoid SQL duplication everywhere.
"""

import sqlite3
import logging
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("DB_SERVICE")


class DatabaseConnectionPool:
    """Simple connection pool for SQLite"""
    
    def __init__(self, db_path: str = "rvx_bot.db"):
        self.db_path = db_path
        self._connections: Dict[int, sqlite3.Connection] = {}
    
    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection"""
        import threading
        thread_id = threading.get_ident()
        
        if thread_id not in self._connections:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._connections[thread_id] = conn
        
        return self._connections[thread_id]
    
    def close_all(self):
        """Close all connections"""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()


class BaseRepository:
    """
    Base repository for all data models (SRP)
    
    Implements common CRUD operations to avoid duplication.
    """
    
    def __init__(self, table_name: str, pool: DatabaseConnectionPool):
        self.table_name = table_name
        self.pool = pool
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database cursor"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error in {self.table_name}: {e}")
            raise
    
    def execute(self, query: str, params: Tuple = ()) -> sqlite3.Cursor:
        """Execute query and return cursor"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor
    
    def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get record by ID"""
        with self._get_cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?",
                (id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all records"""
        with self._get_cursor() as cursor:
            query = f"SELECT * FROM {self.table_name}"
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def count(self) -> int:
        """Count records in table"""
        with self._get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            return cursor.fetchone()[0]
    
    def create(self, **kwargs) -> Dict[str, Any]:
        """Create new record"""
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
                tuple(kwargs.values())
            )
            record_id = cursor.lastrowid
        
        return self.get_by_id(record_id)
    
    def update(self, id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Update record"""
        if not kwargs:
            return self.get_by_id(id)
        
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [id]
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?",
                values
            )
        
        return self.get_by_id(id)
    
    def delete(self, id: int) -> bool:
        """Delete record"""
        with self._get_cursor() as cursor:
            cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))
            return cursor.rowcount > 0
    
    def find(self, **where_clause) -> List[Dict[str, Any]]:
        """Find records by criteria"""
        where_parts = [f"{k} = ?" for k in where_clause.keys()]
        where_sql = " AND ".join(where_parts)
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self.table_name} WHERE {where_sql}",
                tuple(where_clause.values())
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]


# Global pool instance
_pool: Optional[DatabaseConnectionPool] = None


def init_pool(db_path: str = "rvx_bot.db"):
    """Initialize global connection pool"""
    global _pool
    _pool = DatabaseConnectionPool(db_path)


def get_pool() -> DatabaseConnectionPool:
    """Get global connection pool"""
    global _pool
    if _pool is None:
        init_pool()
    return _pool


def close_pool():
    """Close global connection pool"""
    global _pool
    if _pool:
        _pool.close_all()
        _pool = None
