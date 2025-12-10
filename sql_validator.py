"""
SQL Query Validator v1.0
Защита от SQL injection с whitelist валидацией таблиц.
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Whitelist известных таблиц в системе
ALLOWED_TABLES = {
    'users',
    'messages',
    'lessons',
    'conversation_history',
    'conversation_stats',
    'events',
    'user_progress',
    'daily_quests',
    'admin_audit_log',
    'cache_metadata'
}

# Whitelist колонок для каждой таблицы
ALLOWED_COLUMNS = {
    'users': {
        'user_id', 'username', 'level', 'xp', 'is_banned', 'ban_reason',
        'created_at', 'last_active', 'is_admin'
    },
    'conversation_history': {
        'id', 'user_id', 'role', 'content', 'intent', 'timestamp',
        'message_length', 'tokens_estimate'
    },
    'conversation_stats': {
        'user_id', 'total_messages', 'total_tokens', 'last_message_time',
        'context_window_size', 'cleanup_count'
    },
    'events': {
        'id', 'user_id', 'event_type', 'event_data', 'timestamp'
    }
}

class SQLValidator:
    """Валидирует SQL запросы и параметры"""
    
    @staticmethod
    def validate_table_name(table_name: str) -> bool:
        """Проверяет если таблица в whitelist"""
        if not isinstance(table_name, str):
            return False
        
        clean_name = table_name.strip().lower()
        
        if clean_name not in ALLOWED_TABLES:
            logger.error(f"❌ SQL Injection attempt: Unknown table '{table_name}'")
            return False
        
        return True
    
    @staticmethod
    def validate_column_name(table: str, column: str) -> bool:
        """Проверяет если колонка разрешена для таблицы"""
        if not isinstance(column, str):
            return False
        
        clean_column = column.strip().lower()
        
        if table not in ALLOWED_COLUMNS:
            return False
        
        if clean_column not in ALLOWED_COLUMNS[table]:
            logger.error(f"❌ Invalid column '{column}' for table '{table}'")
            return False
        
        return True
    
    @staticmethod
    def validate_query_structure(query: str) -> Optional[str]:
        """
        Проверяет структуру SQL запроса на опасные паттерны.
        Возвращает error message если найдена проблема.
        """
        query_upper = query.upper()
        
        # Проверяем на DROP, DELETE без WHERE, и т.д.
        dangerous_patterns = [
            (r'DROP\s+TABLE', 'DROP TABLE not allowed'),
            (r'TRUNCATE\s+TABLE', 'TRUNCATE not allowed'),
            (r'ALTER\s+TABLE', 'ALTER TABLE not allowed'),
            (r'DELETE\s+FROM\s+\w+\s*(?:;|$)', 'DELETE без WHERE не разрешен'),
            (r'UPDATE\s+\w+\s+SET', 'UPDATE only through parameterized queries'),
            (r'UNION\s+SELECT', 'UNION SELECT not allowed'),
        ]
        
        for pattern, msg in dangerous_patterns:
            if re.search(pattern, query_upper):
                logger.error(f"❌ Dangerous SQL pattern: {msg}")
                return msg
        
        return None
    
    @staticmethod
    def validate_parameter_type(param, expected_type=None) -> bool:
        """Проверяет тип параметра перед вставкой в query"""
        if expected_type is None:
            return True
        
        return isinstance(param, (str, int, float, bool, type(None)))

# Глобальный валидатор
sql_validator = SQLValidator()
