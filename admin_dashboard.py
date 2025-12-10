# admin_dashboard.py
# Admin Dashboard для анализа метрик и аналитики
# Version: 0.25.0

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from event_tracker import get_tracker, get_analytics


class AdminDashboard:
    """Полный admin dashboard для анализа бота"""
    
    def __init__(self):
        self.tracker = get_tracker()
        self.analytics = get_analytics()
    
    def get_dashboard_metrics(self, hours: int = 24) -> Dict:
        """Получить все метрики для dashboard"""
        return {
            "timestamp": datetime.now().isoformat(),
            "period_hours": hours,
            "overview": self._get_overview(hours),
            "engagement": self._get_engagement_metrics(hours),
            "events": self._get_event_breakdown(hours),
            "top_users": self._get_top_users(hours),
            "user_journeys": self._get_journey_analysis(hours),
            "ai_performance": self._get_ai_performance(hours),
            "feature_usage": self._get_feature_usage(hours),
            "retention": self._get_retention_metrics(hours),
        }
    
    def _get_overview(self, hours: int) -> Dict:
        """DAU, MAU и общие метрики"""
        stats = self.tracker.get_stats(hours=hours)
        
        return {
            "dau": stats.get("unique_users", 0),
            "total_events": stats.get("total_events", 0),
            "average_events_per_user": round(
                stats.get("total_events", 0) / max(stats.get("unique_users", 1), 1), 2
            ),
            "events_per_hour": round(
                stats.get("total_events", 0) / max(hours, 1), 2
            ),
        }
    
    def _get_engagement_metrics(self, hours: int) -> Dict:
        """Engagement rate по разным сегментам"""
        stats = self.tracker.get_stats(hours=hours)
        events_by_type = stats.get("events_by_type", {})
        total_events = stats.get("total_events", 1)
        
        return {
            "learning_engagement": round(
                (events_by_type.get("user_education", 0) + 
                 events_by_type.get("user_teach", 0)) / total_events * 100, 2
            ),
            "analysis_engagement": round(
                events_by_type.get("user_analyze", 0) / total_events * 100, 2
            ),
            "quest_engagement": round(
                events_by_type.get("user_quest", 0) / total_events * 100, 2
            ),
            "feedback_rate": round(
                (events_by_type.get("user_feedback", 0) + 
                 events_by_type.get("user_clarify", 0)) / 
                max(events_by_type.get("user_analyze", 1), 1) * 100, 2
            ),
        }
    
    def _get_event_breakdown(self, hours: int) -> Dict:
        """Подробный breakdown всех событий"""
        stats = self.tracker.get_stats(hours=hours)
        events_by_type = stats.get("events_by_type", {})
        total = stats.get("total_events", 1)
        
        breakdown = {}
        for event_type, count in events_by_type.items():
            breakdown[event_type] = {
                "count": count,
                "percentage": round(count / total * 100, 2),
            }
        
        return breakdown
    
    def _get_top_users(self, hours: int, limit: int = 5) -> List[Dict]:
        """Топ активные пользователи"""
        try:
            conn = sqlite3.connect("rvx_bot.db")
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT user_id, COUNT(*) as event_count 
                FROM bot_events 
                WHERE datetime(created_at) > datetime('now', '-' || ? || ' hours')
                GROUP BY user_id 
                ORDER BY event_count DESC 
                LIMIT ?
            """, (hours, limit))
            
            results = []
            for user_id, count in cursor.fetchall():
                results.append({
                    "user_id": user_id,
                    "event_count": count,
                    "rank": len(results) + 1,
                })
            
            conn.close()
            return results
        except Exception as e:
            return [{"error": str(e)}]
    
    def _get_journey_analysis(self, hours: int) -> Dict:
        """Анализ пути пользователя"""
        try:
            journeys = self.tracker.get_user_journeys(hours=hours)
            
            if not journeys:
                return {"total_journeys": 0, "journeys": []}
            
            return {
                "total_journeys": len(journeys),
                "most_common_paths": self._analyze_common_paths(journeys),
                "average_journey_length": round(
                    sum(len(j) for j in journeys) / len(journeys), 2
                ),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _analyze_common_paths(self, journeys: List[List]) -> List[Dict]:
        """Найти самые частые пути пользователя"""
        if not journeys:
            return []
        
        # Преобразуем в строки для подсчета
        path_counts = {}
        for journey in journeys:
            path_str = " → ".join(journey)
            path_counts[path_str] = path_counts.get(path_str, 0) + 1
        
        # Сортируем и берем топ 3
        top_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return [
            {
                "path": path,
                "count": count,
                "percentage": round(count / sum(path_counts.values()) * 100, 2),
            }
            for path, count in top_paths
        ]
    
    def _get_ai_performance(self, hours: int) -> Dict:
        """Статистика по AI ответам"""
        try:
            ai_perf = self.analytics.get_ai_performance(hours=hours)
            return {
                "total_responses": ai_perf.get("total_responses", 0),
                "average_confidence": round(
                    ai_perf.get("average_confidence", 0.8), 2
                ),
                "high_confidence_rate": round(
                    ai_perf.get("high_confidence_rate", 0.85) * 100, 2
                ),
                "low_confidence_warnings": ai_perf.get("low_confidence_count", 0),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_feature_usage(self, hours: int) -> Dict:
        """Использование разных фич"""
        stats = self.tracker.get_stats(hours=hours)
        events_by_type = stats.get("events_by_type", {})
        
        features = {
            "learning": {
                "name": "📚 Learning System",
                "events": events_by_type.get("user_education", 0) + 
                         events_by_type.get("user_teach", 0),
            },
            "news_analysis": {
                "name": "📰 News Analysis",
                "events": events_by_type.get("user_analyze", 0),
            },
            "quests": {
                "name": "🎯 Daily Quests",
                "events": events_by_type.get("user_quest", 0),
            },
            "feedback": {
                "name": "👍 Feedback System",
                "events": events_by_type.get("user_feedback", 0) + 
                         events_by_type.get("user_clarify", 0),
            },
            "profile": {
                "name": "👤 Profile/Stats",
                "events": events_by_type.get("user_profile", 0),
            },
        }
        
        return features
    
    def _get_retention_metrics(self, hours: int) -> Dict:
        """Метрики удержания пользователей"""
        try:
            conn = sqlite3.connect("rvx_bot.db")
            cursor = conn.cursor()
            
            # Уникальные пользователи в разные периоды
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as cnt 
                FROM bot_events 
                WHERE datetime(created_at) > datetime('now', '-1 hours')
            """)
            users_1h = cursor.fetchone()[0] if cursor.fetchone() else 0
            
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as cnt 
                FROM bot_events 
                WHERE datetime(created_at) > datetime('now', '-24 hours')
            """)
            users_24h = cursor.fetchone()[0] if cursor.fetchone() else 0
            
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as cnt 
                FROM bot_events 
                WHERE datetime(created_at) > datetime('now', '-7 days')
            """)
            users_7d = cursor.fetchone()[0] if cursor.fetchone() else 0
            
            conn.close()
            
            return {
                "active_1h": users_1h,
                "active_24h": users_24h,
                "active_7d": users_7d,
                "retention_24h": round(users_24h / max(users_7d, 1) * 100, 2),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def format_dashboard_for_telegram(self, metrics: Dict) -> str:
        """Отформатировать метрики для Telegram"""
        overview = metrics.get("overview", {})
        engagement = metrics.get("engagement", {})
        events = metrics.get("events", {})
        top_users = metrics.get("top_users", [])
        ai_perf = metrics.get("ai_performance", {})
        features = metrics.get("feature_usage", {})
        
        text = (
            "<b>📊 RVX ADMIN DASHBOARD v0.25.0</b>\n"
            "<b>═════════════════════════════════════</b>\n\n"
            
            "<b>📈 OVERVIEW (за {hours}ч):</b>\n"
            f"  • DAU: <b>{overview.get('dau', 0)}</b> пользователей\n"
            f"  • Events: <b>{overview.get('total_events', 0)}</b> всего\n"
            f"  • Per user: <b>{overview.get('average_events_per_user', 0)}</b> events/user\n"
            f"  • Per hour: <b>{overview.get('events_per_hour', 0)}</b> events/hour\n\n"
            
            "<b>💬 ENGAGEMENT:</b>\n"
            f"  • Learning: <b>{engagement.get('learning_engagement', 0)}%</b>\n"
            f"  • Analysis: <b>{engagement.get('analysis_engagement', 0)}%</b>\n"
            f"  • Quests: <b>{engagement.get('quest_engagement', 0)}%</b>\n"
            f"  • Feedback: <b>{engagement.get('feedback_rate', 0)}%</b>\n\n"
            
            "<b>🎯 EVENT BREAKDOWN:</b>\n"
        ).format(hours=metrics.get("period_hours", 24))
        
        # События
        for event_type, data in events.items():
            text += f"  • {event_type}: {data['count']} ({data['percentage']}%)\n"
        
        text += "\n<b>🏆 TOP USERS:</b>\n"
        for user in top_users[:5]:
            text += f"  #{user.get('rank', '?')} User {user.get('user_id', '?')}: {user.get('event_count', 0)} events\n"
        
        text += f"\n<b>🤖 AI PERFORMANCE:</b>\n"
        text += f"  • Responses: <b>{ai_perf.get('total_responses', 0)}</b>\n"
        text += f"  • Avg confidence: <b>{ai_perf.get('average_confidence', 0)}</b>\n"
        text += f"  • High confidence: <b>{ai_perf.get('high_confidence_rate', 0)}%</b>\n"
        text += f"  • Low confidence warnings: <b>{ai_perf.get('low_confidence_warnings', 0)}</b>\n"
        
        text += "\n<b>📱 FEATURE USAGE:</b>\n"
        for feature_key, feature_data in features.items():
            text += f"  • {feature_data['name']}: {feature_data['events']} uses\n"
        
        text += "\n<b>═════════════════════════════════════</b>\n"
        text += f"<i>Generated: {metrics.get('timestamp', 'unknown')}</i>"
        
        return text


def get_admin_dashboard() -> AdminDashboard:
    """Получить singleton instance Admin Dashboard"""
    if not hasattr(get_admin_dashboard, '_instance'):
        get_admin_dashboard._instance = AdminDashboard()
    return get_admin_dashboard._instance
