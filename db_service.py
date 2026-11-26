"""
Database Service (DAL - Data Access Layer)
==========================================

Centralized database access to avoid SQL duplication everywhere.
"""

import sqlite3
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("DB_SERVICE")

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(identifier: str) -> str:
    """Validate and quote an identifier before using it in a SQL statement."""
    if not isinstance(identifier, str) or not _SQL_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return f'"{identifier}"'


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
        self.table_name = _quote_identifier(table_name)
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
                f"SELECT * FROM {self.table_name} WHERE id = ?",  # nosec B608
                (id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all records"""
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
        ):
            raise ValueError("limit must be a non-negative integer")

        with self._get_cursor() as cursor:
            query = f"SELECT * FROM {self.table_name}"  # nosec B608
            params = ()
            if limit is not None:
                query += " LIMIT ?"
                params = (limit,)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def count(self) -> int:
        """Count records in table"""
        with self._get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")  # nosec B608
            return cursor.fetchone()[0]
    
    def create(self, **kwargs) -> Dict[str, Any]:
        """Create new record"""
        if not kwargs:
            raise ValueError("At least one column is required")
        columns = ", ".join(_quote_identifier(column) for column in kwargs)
        placeholders = ", ".join(["?"] * len(kwargs))
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",  # nosec B608
                tuple(kwargs.values())
            )
            record_id = cursor.lastrowid
        
        return self.get_by_id(record_id)
    
    def update(self, id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Update record"""
        if not kwargs:
            return self.get_by_id(id)
        
        set_clause = ", ".join(
            f"{_quote_identifier(key)} = ?" for key in kwargs
        )
        values = list(kwargs.values()) + [id]
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?",  # nosec B608
                values
            )
        
        return self.get_by_id(id)
    
    def delete(self, id: int) -> bool:
        """Delete record"""
        with self._get_cursor() as cursor:
            cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))  # nosec B608
            return cursor.rowcount > 0
    
    def find(self, **where_clause) -> List[Dict[str, Any]]:
        """Find records by criteria"""
        if not where_clause:
            raise ValueError("At least one search criterion is required")
        where_parts = [
            f"{_quote_identifier(key)} = ?" for key in where_clause
        ]
        where_sql = " AND ".join(where_parts)
        
        with self._get_cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self.table_name} WHERE {where_sql}",  # nosec B608
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
