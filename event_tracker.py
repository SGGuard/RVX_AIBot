# event_tracker.py
# Система событийной аналитики для RVX Bot
# Version: 0.25.0

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, asdict

# ============================================================================
# EVENT TYPES
# ============================================================================
class EventType(Enum):
    """Типы событий для трекинга"""
    # Пользовательские действия
    USER_START = "user_start"
    USER_HELP = "user_help"
    USER_ANALYZE = "user_analyze"
    USER_FEEDBACK = "user_feedback"
    USER_CLARIFY = "user_clarify"
    USER_QUEST_START = "user_quest_start"
    USER_QUEST_COMPLETE = "user_quest_complete"
    USER_DROP_RECEIVED = "user_drop_received"
    USER_PROFILE_VIEW = "user_profile_view"
    
    # AI события
    AI_REQUEST = "ai_request"
    AI_SUCCESS = "ai_success"
    AI_TIMEOUT = "ai_timeout"
    AI_ERROR = "ai_error"
    AI_FALLBACK = "ai_fallback"
    AI_HALLUCINATION = "ai_hallucination"
    
    # Система
    SYSTEM_ERROR = "system_error"
    SYSTEM_HEALTH = "system_health"
    SYSTEM_CACHE_HIT = "system_cache_hit"
    SYSTEM_CACHE_MISS = "system_cache_miss"
    
    # Админ
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_COMMAND = "admin_command"

# ============================================================================
# EVENT MODEL
# ============================================================================
@dataclass
class Event:
    """Модель события"""
    event_type: EventType
    user_id: Optional[int] = None
    timestamp: str = None
    data: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.data is None:
            self.data = {}
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

# ============================================================================
# EVENT TRACKER
# ============================================================================
class EventTracker:
    """Система трекинга и аналитики событий"""
    
    def __init__(self, db_path: str = "./rvx_bot.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализировать таблицу событий"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                timestamp TEXT NOT NULL,
                data TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_user_id 
            ON bot_events(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type 
            ON bot_events(event_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp 
            ON bot_events(timestamp)
        """)
        
        conn.commit()
        conn.close()
    
    def track(self, event: Event) -> bool:
        """Записать событие в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bot_events 
                (event_type, user_id, timestamp, data, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                event.event_type.value,
                event.user_id,
                event.timestamp,
                json.dumps(event.data, ensure_ascii=False, default=str),
                json.dumps(event.metadata, ensure_ascii=False, default=str),
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Ошибка при трекинге события: {e}")
            return False
    
    def get_events(
        self,
        event_type: Optional[EventType] = None,
        user_id: Optional[int] = None,
        hours: int = 24,
        limit: int = 1000
    ) -> List[Dict]:
        """Получить события с фильтрацией"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM bot_events WHERE 1=1"
        params = []
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        # Временной фильтр
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        query += " AND timestamp > ?"
        params.append(cutoff_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        events = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return events
    
    def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Получить статистику по событиям"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        # Общая статистика
        cursor.execute("""
            SELECT 
                COUNT(*) as total_events,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT event_type) as event_types
            FROM bot_events
            WHERE timestamp > ?
        """, (cutoff_time,))
        
        stats = dict(zip(
            [desc[0] for desc in cursor.description],
            cursor.fetchone()
        ))
        
        # Событие по типам
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM bot_events
            WHERE timestamp > ?
            GROUP BY event_type
            ORDER BY count DESC
        """, (cutoff_time,))
        
        stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Топ пользователи
        cursor.execute("""
            SELECT user_id, COUNT(*) as count
            FROM bot_events
            WHERE timestamp > ? AND user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY count DESC
            LIMIT 10
        """, (cutoff_time,))
        
        stats["top_users"] = [
            {"user_id": row[0], "events": row[1]}
            for row in cursor.fetchall()
        ]
        
        # AI статистика
        cursor.execute("""
            SELECT 
                event_type,
                COUNT(*) as count,
                AVG(CAST(json_extract(data, '$.duration') AS FLOAT)) as avg_duration
            FROM bot_events
            WHERE timestamp > ? AND event_type LIKE 'ai_%'
            GROUP BY event_type
        """, (cutoff_time,))
        
        stats["ai_stats"] = [
            {
                "type": row[0],
                "count": row[1],
                "avg_duration": row[2]
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return stats
    
    def get_user_journey(self, user_id: int) -> List[Dict]:
        """Получить путь пользователя (все его события)"""
        return self.get_events(user_id=user_id, hours=720)  # 30 дней
    
    def cleanup_old_events(self, days: int = 30) -> int:
        """Удалить старые события (оптимизация БД)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            DELETE FROM bot_events
            WHERE timestamp < ?
        """, (cutoff_time,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted

# ============================================================================
# ANALYTICS CALCULATOR
# ============================================================================
class Analytics:
    """Расчеты аналитики на основе событий"""
    
    def __init__(self, tracker: EventTracker):
        self.tracker = tracker
    
    def get_user_engagement(self, user_id: int) -> Dict[str, Any]:
        """Вычислить вовлеченность пользователя"""
        events = self.tracker.get_user_journey(user_id)
        
        if not events:
            return {"engagement_score": 0, "status": "inactive"}
        
        # Расчет метрик
        total_events = len(events)
        unique_days = len(set(e["timestamp"].split("T")[0] for e in events))
        
        event_types = {}
        for event in events:
            event_type = event["event_type"]
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Оценка вовлеченности (0-100)
        engagement_score = min(100, total_events * 5 + unique_days * 10)
        
        return {
            "engagement_score": engagement_score,
            "total_events": total_events,
            "days_active": unique_days,
            "event_breakdown": event_types,
            "status": "active" if unique_days >= 7 else "inactive",
        }
    
    def get_ai_performance(self, hours: int = 24) -> Dict[str, Any]:
        """Вычислить производительность AI"""
        stats = self.tracker.get_stats(hours)
        
        ai_stats = stats.get("ai_stats", [])
        
        total_ai_requests = sum(s["count"] for s in ai_stats)
        
        # Подсчет успешных/ошибок
        ai_events = self.tracker.get_events(hours=hours, limit=10000)
        ai_events = [e for e in ai_events if e["event_type"].startswith("ai_")]
        
        successes = len([e for e in ai_events if e["event_type"] == "ai_success"])
        errors = len([e for e in ai_events if e["event_type"] == "ai_error"])
        timeouts = len([e for e in ai_events if e["event_type"] == "ai_timeout"])
        
        success_rate = (successes / total_ai_requests * 100) if total_ai_requests > 0 else 0
        
        return {
            "total_requests": total_ai_requests,
            "successes": successes,
            "errors": errors,
            "timeouts": timeouts,
            "success_rate": round(success_rate, 2),
            "avg_duration": sum(
                s["avg_duration"] or 0 for s in ai_stats
            ) / len(ai_stats) if ai_stats else 0,
        }
    
    def get_feature_usage(self, hours: int = 24) -> Dict[str, int]:
        """Получить использование функций"""
        events = self.tracker.get_events(hours=hours, limit=10000)
        
        usage = {}
        for event in events:
            event_type = event["event_type"]
            usage[event_type] = usage.get(event_type, 0) + 1
        
        return sorted(usage.items(), key=lambda x: x[1], reverse=True)
    
    def get_daily_active_users(self, days: int = 7) -> Dict[str, int]:
        """Получить DAU (Daily Active Users)"""
        dau = {}
        
        for i in range(days):
            target_date = (datetime.now() - timedelta(days=i)).date().isoformat()
            events = self.tracker.get_events(hours=24 * (i + 1), limit=100000)
            events = [e for e in events if e["timestamp"].startswith(target_date)]
            
            unique_users = len(set(e["user_id"] for e in events if e["user_id"]))
            dau[target_date] = unique_users
        
        return dau

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def create_event(
    event_type: EventType,
    user_id: Optional[int] = None,
    data: Optional[Dict] = None,
    metadata: Optional[Dict] = None
) -> Event:
    """Удобный способ создать событие"""
    return Event(
        event_type=event_type,
        user_id=user_id,
        data=data or {},
        metadata=metadata or {}
    )

# ============================================================================
# SINGLETON TRACKER INSTANCE
# ============================================================================
_tracker_instance = None

def get_tracker(db_path: str = "./rvx_bot.db") -> EventTracker:
    """Получить глобальный экземпляр трекера (singleton)"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = EventTracker(db_path)
    return _tracker_instance

def get_analytics(db_path: str = "./rvx_bot.db") -> Analytics:
    """Получить экземпляр аналитики"""
    return Analytics(get_tracker(db_path))
