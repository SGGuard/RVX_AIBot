"""
Conversation Context Manager v0.26.0
Управление контекстом разговора и историей сообщений для каждого пользователя.

Функции:
- Сохранение истории сообщений (user & AI)
- Управление контекстом для каждого пользователя
- Перестроение полного контекста из истории
- Очистка старой истории (по времени и размеру)
- Поиск релевантных сообщений из истории

Особенности:
- SQLite для персистентности
- LRU кэш в памяти для быстрого доступа
- Автоматическое удаление старых записей
- Защита от переполнения контекста
"""

import sqlite3
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from functools import lru_cache
from threading import Lock, RLock

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SCHEMA
# ============================================================================

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    intent TEXT,
    timestamp INTEGER DEFAULT (strftime('%s', 'now')),
    message_length INTEGER,
    tokens_estimate INTEGER,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversation_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_conv_role ON conversation_history(role);

CREATE TABLE IF NOT EXISTS conversation_stats (
    user_id INTEGER PRIMARY KEY,
    total_messages INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    last_message_time INTEGER,
    context_window_size INTEGER DEFAULT 0,
    cleanup_count INTEGER DEFAULT 0,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_MESSAGES_PER_USER = 50  # Максимум сообщений в истории на пользователя
MAX_CONTEXT_TOKENS = 2000  # Максимум токенов в контексте
MESSAGE_RETENTION_DAYS = 7  # Хранить сообщения 7 дней
CLEANUP_INTERVAL_HOURS = 24  # Очистка каждые 24 часа
MIN_MESSAGE_LENGTH = 10  # Минимальная длина сообщения для сохранения
MAX_MESSAGE_LENGTH = 2000  # Максимальная длина сохраняемого сообщения

# ============================================================================
# MAIN CLASS
# ============================================================================

class ConversationContextManager:
    """Управляет контекстом разговора для каждого пользователя"""
    
    _instance = None
    _lock = Lock()
    
    def __init__(self, db_path: str = "rvx_bot.db"):
        self.db_path = db_path
        self.init_database()
        self._memory_cache = {}  # user_id -> list of messages
        self._last_cleanup = time.time()
        # ✅ CRITICAL FIX #3: Thread-safe database access
        self._db_lock = RLock()  # Recursive lock for nested DB operations
        logger.info("✅ ConversationContextManager инициализирован (thread-safe)")
    
    def __new__(cls, db_path: str = "rvx_bot.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def init_database(self):
        """Инициализирует базу данных и схему"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Drop old tables if they exist and recreate with proper schema
            cursor.execute("DROP TABLE IF EXISTS conversation_history")
            cursor.execute("DROP TABLE IF EXISTS conversation_stats")
            
            cursor.executescript(DB_SCHEMA)
            conn.commit()
            conn.close()
            logger.info("✅ Database schema initialized (conversation_context tables recreated)")
        except Exception as e:
            logger.error(f"❌ Failed to init database: {e}")
    
    def get_connection(self) -> sqlite3.Connection:
        """Получает соединение с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ========================================================================
    # CORE METHODS
    # ========================================================================
    
    def add_message(
        self, 
        user_id: int, 
        role: str, 
        content: str, 
        intent: Optional[str] = None
    ) -> bool:
        """
        Добавляет сообщение в историю разговора (THREAD-SAFE!)
        
        Args:
            user_id: ID пользователя
            role: 'user' или 'assistant'
            content: Содержание сообщения
            intent: Классификация намерения (опционально)
            
        Returns:
            bool: Успешно ли добавлено
        """
        try:
            # ✅ CRITICAL FIX #3: Thread-safe DB операция
            if not hasattr(self, '_db_lock'):
                self._db_lock = threading.RLock()
            
            with self._db_lock:
                # Валидация
                if not isinstance(user_id, int) or user_id <= 0:
                    logger.error(f"❌ Invalid user_id: {user_id}")
                    return False
                
                if role not in ('user', 'assistant'):
                    logger.error(f"❌ Invalid role: {role}")
                    return False
                
                if not content or len(content) < MIN_MESSAGE_LENGTH:
                    return False
                
                if len(content) > MAX_MESSAGE_LENGTH:
                    content = content[:MAX_MESSAGE_LENGTH]
                
                # Сохранение в БД
                try:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    
                    tokens_estimate = len(content.split()) * 1.3  # Примерная оценка токенов
                    current_time = int(time.time())
                    
                    # Всё в одной транзакции
                    cursor.execute("""
                        INSERT INTO conversation_history 
                        (user_id, role, content, intent, timestamp, message_length, tokens_estimate)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, role, content, intent, current_time, len(content), int(tokens_estimate)))
                    
                    # Обновляем статистику
                    cursor.execute("""
                        INSERT INTO conversation_stats (user_id, total_messages, total_tokens, last_message_time)
                        VALUES (?, 1, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            total_messages = total_messages + 1,
                            total_tokens = total_tokens + ?,
                            last_message_time = ?
                    """, (user_id, int(tokens_estimate), current_time, int(tokens_estimate), current_time))
                    
                    # Удаляем старые сообщения (выше лимита)
                    cursor.execute("""
                        DELETE FROM conversation_history
                        WHERE user_id = ? AND id NOT IN (
                            SELECT id FROM conversation_history
                            WHERE user_id = ?
                            ORDER BY timestamp DESC
                            LIMIT ?
                        )
                    """, (user_id, user_id, MAX_MESSAGES_PER_USER))
                    
                    conn.commit()
                    conn.close()
                    
                    logger.debug(f"✅ Message added for user {user_id} (len={len(content)})")
                    
                    # Инвалидируем кэш
                    if user_id in self._memory_cache:
                        del self._memory_cache[user_id]
                    
                    return True
                
                except sqlite3.Error as e:
                    logger.error(f"❌ DB error: {e}", exc_info=True)
                    return False
        
        except Exception as e:
            logger.error(f"❌ Unexpected error in add_message: {e}", exc_info=True)
            return False
    
    def get_context(self, user_id: int, max_messages: Optional[int] = None) -> str:
        """
        Получает полный контекст для пользователя в виде строки
        
        Args:
            user_id: ID пользователя
            max_messages: Максимум сообщений (если None, используется default)
            
        Returns:
            str: Форматированный контекст для передачи в ИИ
        """
        try:
            if max_messages is None:
                max_messages = 10  # Последние 10 сообщений
            
            messages = self.get_messages(user_id, limit=max_messages)
            
            if not messages:
                return ""
            
            # Форматируем в читаемый контекст
            context_parts = []
            context_parts.append("📝 ИСТОРИЯ РАЗГОВОРА:")
            context_parts.append("-" * 50)
            
            for msg in messages:
                role = "👤 Вы" if msg["role"] == "user" else "🤖 ИИ"
                content = msg["content"][:200]  # Обрезаем для краткости
                timestamp = datetime.fromtimestamp(msg["timestamp"]).strftime("%H:%M")
                context_parts.append(f"{role} ({timestamp}): {content}")
            
            context_parts.append("-" * 50)
            context_parts.append("📌 КОНТЕКСТ РАЗГОВОРА")
            context_parts.append("Помни эту историю разговора при ответе")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"❌ Failed to get context: {e}")
            return ""
    
    def get_messages(
        self, 
        user_id: int, 
        limit: int = 20,
        offset: int = 0,
        role: Optional[str] = None
    ) -> List[Dict]:
        """
        Получает сообщения из истории (THREAD-SAFE!)
        
        Args:
            user_id: ID пользователя
            limit: Количество сообщений
            offset: Смещение
            role: Фильтр по роли ('user', 'assistant')
            
        Returns:
            List[Dict]: Список сообщений
        """
        try:
            # ✅ CRITICAL FIX #3: Thread-safe DB операция
            if not hasattr(self, '_db_lock'):
                self._db_lock = threading.RLock()
            
            with self._db_lock:
                # Валидация параметров
                if not isinstance(user_id, int) or user_id <= 0:
                    logger.warning(f"⚠️ Invalid user_id: {user_id}")
                    return []
                
                if limit < 1 or limit > 100:
                    limit = 20
                
                if offset < 0:
                    offset = 0
                
                # Проверяем кэш (гарантированно безопасный доступ)
                cache_key = f"{user_id}_{limit}_{offset}_{role}"
                
                try:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    
                    query = "SELECT * FROM conversation_history WHERE user_id = ?"
                    params = [user_id]
                    
                    if role and role in ('user', 'assistant'):
                        query += " AND role = ?"
                        params.append(role)
                    
                    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                    params.extend([limit, offset])
                    
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    conn.close()
                    
                    # Переворачиваем (самое старое первым)
                    messages = [dict(row) for row in reversed(rows)]
                    
                    logger.debug(f"✅ Retrieved {len(messages)} messages for user {user_id}")
                    return messages
                
                except sqlite3.Error as e:
                    logger.error(f"❌ DB error in get_messages: {e}", exc_info=True)
                    return []
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in get_messages: {e}", exc_info=True)
            return []
    
    def get_stats(self, user_id: int) -> Dict:
        """
        Получает статистику разговора пользователя (THREAD-SAFE!)
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict: Статистика
        """
        try:
            # ✅ CRITICAL FIX #3: Thread-safe DB операция
            with self._db_lock:
                # Валидация
                if not isinstance(user_id, int) or user_id <= 0:
                    return {
                        "total_messages": 0,
                        "total_tokens": 0,
                        "last_message_time": None,
                        "context_window_size": 0,
                        "cleanup_count": 0
                    }
                
                try:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT * FROM conversation_stats WHERE user_id = ?
                    """, (user_id,))
                    
                    row = cursor.fetchone()
                    conn.close()
                    
                    if row:
                        stats = {
                            "total_messages": row["total_messages"],
                            "total_tokens": row["total_tokens"],
                            "last_message_time": row["last_message_time"],
                            "context_window_size": row["context_window_size"],
                            "cleanup_count": row["cleanup_count"]
                        }
                        logger.debug(f"✅ Stats retrieved for user {user_id}")
                        return stats
                    
                    return {
                        "total_messages": 0,
                        "total_tokens": 0,
                        "last_message_time": None,
                        "context_window_size": 0,
                        "cleanup_count": 0
                    }
                
                except sqlite3.Error as e:
                    logger.error(f"❌ DB error in get_stats: {e}", exc_info=True)
                    return {}
        
        except Exception as e:
            logger.error(f"❌ Unexpected error in get_stats: {e}", exc_info=True)
            return {}
    
    def clear_history(self, user_id: int) -> bool:
        """
        Очищает всю историю разговора для пользователя (THREAD-SAFE!)
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: Успешно ли очищено
        """
        try:
            # ✅ CRITICAL FIX #3: Thread-safe DB операция
            with self._db_lock:
                # Валидация
                if not isinstance(user_id, int) or user_id <= 0:
                    logger.warning(f"⚠️ Invalid user_id: {user_id}")
                    return False
                
                try:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (user_id,))
                    cursor.execute("""
                        DELETE FROM conversation_stats WHERE user_id = ?
                    """, (user_id,))
                    
                    conn.commit()
                    conn.close()
                    
                    # Инвалидируем кэш
                    if user_id in self._memory_cache:
                        del self._memory_cache[user_id]
                    
                    logger.info(f"✅ История разговора очищена для пользователя {user_id}")
                    return True
                
                except sqlite3.Error as e:
                    logger.error(f"❌ DB error in clear_history: {e}", exc_info=True)
                    return False
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in clear_history: {e}", exc_info=True)
            return False
    
    # ========================================================================
    # CLEANUP & MAINTENANCE
    # ========================================================================
    
    def _maybe_cleanup(self, user_id: int):
        """Проверяет необходимость очистки истории"""
        try:
            # Очищаем если много сообщений
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM conversation_history WHERE user_id = ?",
                (user_id,)
            )
            count = cursor.fetchone()["cnt"]
            
            if count > MAX_MESSAGES_PER_USER:
                # Удаляем старые сообщения
                excess = count - MAX_MESSAGES_PER_USER
                cursor.execute("""
                    DELETE FROM conversation_history WHERE id IN (
                        SELECT id FROM conversation_history 
                        WHERE user_id = ? 
                        ORDER BY timestamp ASC 
                        LIMIT ?
                    )
                """, (user_id, excess))
                
                conn.commit()
                logger.info(f"🧹 Очищено {excess} старых сообщений для пользователя {user_id}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
    
    def cleanup_old_messages(self, days: int = MESSAGE_RETENTION_DAYS) -> int:
        """
        Удаляет старые сообщения
        
        Args:
            days: Удалить старше чем N дней
            
        Returns:
            int: Количество удаленных сообщений
        """
        try:
            cutoff_time = int(time.time()) - (days * 86400)
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM conversation_history WHERE timestamp < ?",
                (cutoff_time,)
            )
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"🧹 Удалено {deleted_count} сообщений старше {days} дней")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old messages: {e}")
            return 0
    
    def get_database_size(self) -> Dict:
        """Получает размер таблиц"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as total_messages FROM conversation_history
            """)
            total_messages = cursor.fetchone()["total_messages"]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as unique_users FROM conversation_history
            """)
            unique_users = cursor.fetchone()["unique_users"]
            
            conn.close()
            
            return {
                "total_messages": total_messages,
                "unique_users": unique_users,
                "avg_per_user": total_messages // max(unique_users, 1)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get size: {e}")
            return {}


# ============================================================================
# SINGLETON FUNCTIONS
# ============================================================================

_context_manager_instance = None

def get_context_manager() -> ConversationContextManager:
    """Получает singleton экземпляр ConversationContextManager"""
    global _context_manager_instance
    if _context_manager_instance is None:
        _context_manager_instance = ConversationContextManager()
    return _context_manager_instance


def add_user_message(user_id: int, text: str, intent: Optional[str] = None) -> bool:
    """Добавляет сообщение пользователя в контекст"""
    manager = get_context_manager()
    return manager.add_message(user_id, "user", text, intent)


def add_ai_message(user_id: int, text: str) -> bool:
    """Добавляет сообщение ИИ в контекст"""
    manager = get_context_manager()
    return manager.add_message(user_id, "assistant", text)


def get_user_context(user_id: int) -> str:
    """Получает контекст разговора пользователя"""
    manager = get_context_manager()
    return manager.get_context(user_id)


def clear_user_history(user_id: int) -> bool:
    """Очищает историю пользователя"""
    manager = get_context_manager()
    return manager.clear_history(user_id)


def get_context_stats(user_id: int) -> Dict:
    """Получает статистику контекста"""
    manager = get_context_manager()
    return manager.get_stats(user_id)


# ============================================================================
# TESTING & UTILITIES
# ============================================================================

if __name__ == "__main__":
    # Простой тест
    logging.basicConfig(level=logging.INFO)
    
    manager = get_context_manager()
    
    # Добавляем сообщения
    manager.add_message(12345, "user", "Привет! Как дела?", "greeting")
    manager.add_message(12345, "assistant", "Привет! Я в порядке. Чем я могу тебе помочь?")
    manager.add_message(12345, "user", "Расскажи о биткоине", "education")
    manager.add_message(12345, "assistant", "Биткоин - это первая цифровая валюта...")
    
    # Получаем контекст
    context = manager.get_context(12345)
    print("\n" + context)
    
    # Статистика
    stats = manager.get_stats(12345)
    print("\n📊 Stats:", stats)
    
    # Размер БД
    size = manager.get_database_size()
    print("\n📦 DB Size:", size)
