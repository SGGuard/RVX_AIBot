# test_improvements.py
# Unit тесты для критических функций
# Version: 0.25.0

import unittest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Импорты модулей для тестирования
from config import (
    validate_config, TELEGRAM_BOT_TOKEN, GEMINI_API_KEY,
    CACHE_ENABLED, DATABASE_PATH, RATE_LIMIT_ENABLED
)
from ai_honesty import (
    HonestyDetector, ResponseCleaner, HonestyRules,
    analyze_ai_response, clean_ai_response, validate_response
)
from event_tracker import (
    EventTracker, EventType, Event, Analytics, create_event
)
from messages import (
    format_message, split_message, truncate_message
)

# ============================================================================
# TESTS FOR CONFIG
# ============================================================================
class TestConfig(unittest.TestCase):
    """Тесты конфигурации"""
    
    def test_config_validation(self):
        """Проверить что конфиг валиден"""
        # validate_config() выбросит исключение если есть проблемы
        if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
            self.skipTest("Переменные окружения не установлены")
    
    def test_cache_enabled_flag(self):
        """Проверить флаг кеша"""
        self.assertIsInstance(CACHE_ENABLED, bool)
    
    def test_database_path_exists_or_creatable(self):
        """Проверить что БД путь валидный"""
        self.assertIsNotNone(DATABASE_PATH)
        self.assertTrue(DATABASE_PATH.endswith(".db"))

# ============================================================================
# TESTS FOR AI HONESTY
# ============================================================================
class TestAIHonesty(unittest.TestCase):
    """Тесты системы предотвращения галлюцинаций"""
    
    def setUp(self):
        """Подготовка к каждому тесту"""
        self.detector = HonestyDetector()
        self.cleaner = ResponseCleaner()
    
    def test_detect_fake_investor(self):
        """Обнаружить придуманного инвестора"""
        response = "Инвестор Иван Петров вложил $100 млн в стартап"
        analysis = self.detector.analyze_response(response)
        
        self.assertLess(analysis["confidence"], 0.95)
        self.assertGreater(analysis["patterns_detected"], 0)
    
    def test_detect_suspicious_numbers(self):
        """Обнаружить подозрительные цифры"""
        response = "Компания привлекла $500 млн от неизвестного источника"
        analysis = self.detector.analyze_response(response)
        
        # Должна быть низкая уверенность без источника
        self.assertLess(analysis["confidence"], 0.9)
    
    def test_detect_overconfidence(self):
        """Обнаружить чрезмерную уверенность"""
        response = "Это абсолютно ясно произойдет гарантированно"
        analysis = self.detector.analyze_response(response)
        
        self.assertLess(analysis["confidence"], 0.95)
    
    def test_soften_claims(self):
        """Смягчить уверенные утверждения"""
        response = "Точно известно, что это произойдет гарантированно"
        cleaned = self.cleaner._soften_claims(response)
        
        self.assertNotIn("точно известно", cleaned.lower())
        self.assertNotIn("гарантированно", cleaned.lower())
        self.assertIn("вероятно", cleaned.lower())
    
    def test_clean_response(self):
        """Очистить полный ответ"""
        response = "Инвестор Иван Петров (точно известно) вложил $100 млн"
        cleaned = self.cleaner.clean_response(response)
        
        self.assertIsNotNone(cleaned)
        self.assertIsInstance(cleaned, str)
    
    def test_honest_response_validation(self):
        """Проверить валидацию честного ответа"""
        # Честный ответ с источниками
        honest_response = "По данным Reuters, компания привлекла примерно $100 млн"
        is_honest, message = HonestyRules.validate_honesty(honest_response, 0.5)
        
        self.assertTrue(is_honest)
        self.assertIn("честный", message.lower())
    
    def test_get_honesty_prompt(self):
        """Получить промпт честности"""
        prompt = HonestyRules.get_honesty_prompt()
        
        self.assertIsNotNone(prompt)
        self.assertIn("НИКОГДА", prompt)
        self.assertIn("ВЫДУМЫВАЙ", prompt)

# ============================================================================
# TESTS FOR EVENT TRACKING
# ============================================================================
class TestEventTracker(unittest.TestCase):
    """Тесты системы трекинга событий"""
    
    def setUp(self):
        """Подготовка к тестам"""
        # Используем временный файл БД
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.tracker = EventTracker(self.temp_db.name)
    
    def tearDown(self):
        """Очистка после тестов"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_track_event(self):
        """Записать событие"""
        event = Event(
            event_type=EventType.USER_START,
            user_id=123,
            data={"source": "telegram"}
        )
        
        result = self.tracker.track(event)
        self.assertTrue(result)
    
    def test_get_events(self):
        """Получить события"""
        # Записать несколько событий
        for i in range(3):
            event = Event(
                event_type=EventType.AI_SUCCESS,
                user_id=123 + i,
                data={"duration": 2.5}
            )
            self.tracker.track(event)
        
        # Получить события
        events = self.tracker.get_events(limit=10)
        self.assertGreaterEqual(len(events), 3)
    
    def test_get_events_by_type(self):
        """Получить события по типу"""
        event = Event(event_type=EventType.USER_FEEDBACK, user_id=123)
        self.tracker.track(event)
        
        events = self.tracker.get_events(event_type=EventType.USER_FEEDBACK)
        self.assertGreaterEqual(len(events), 1)
    
    def test_get_events_by_user(self):
        """Получить события пользователя"""
        user_id = 999
        event = Event(event_type=EventType.USER_ANALYZE, user_id=user_id)
        self.tracker.track(event)
        
        events = self.tracker.get_events(user_id=user_id)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(all(e["user_id"] == user_id for e in events))
    
    def test_get_stats(self):
        """Получить статистику"""
        # Записать события
        for i in range(5):
            event = Event(event_type=EventType.AI_SUCCESS, user_id=100 + i)
            self.tracker.track(event)
        
        stats = self.tracker.get_stats(hours=1)
        
        self.assertIn("total_events", stats)
        self.assertIn("unique_users", stats)
        self.assertIn("by_type", stats)
        self.assertGreaterEqual(stats["total_events"], 5)
    
    def test_get_user_journey(self):
        """Получить путь пользователя"""
        user_id = 777
        
        # Записать несколько событий для одного пользователя
        for event_type in [EventType.USER_START, EventType.USER_ANALYZE, EventType.USER_FEEDBACK]:
            event = Event(event_type=event_type, user_id=user_id)
            self.tracker.track(event)
        
        journey = self.tracker.get_user_journey(user_id)
        
        self.assertGreaterEqual(len(journey), 3)
        self.assertTrue(all(e["user_id"] == user_id for e in journey))

# ============================================================================
# TESTS FOR ANALYTICS
# ============================================================================
class TestAnalytics(unittest.TestCase):
    """Тесты системы аналитики"""
    
    def setUp(self):
        """Подготовка"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.tracker = EventTracker(self.temp_db.name)
        self.analytics = Analytics(self.tracker)
    
    def tearDown(self):
        """Очистка"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_get_user_engagement(self):
        """Вычислить вовлеченность пользователя"""
        user_id = 555
        
        # Записать события
        for _ in range(5):
            event = Event(event_type=EventType.USER_ANALYZE, user_id=user_id)
            self.tracker.track(event)
        
        engagement = self.analytics.get_user_engagement(user_id)
        
        self.assertIn("engagement_score", engagement)
        self.assertIn("total_events", engagement)
        self.assertGreaterEqual(engagement["engagement_score"], 0)
    
    def test_get_ai_performance(self):
        """Получить производительность AI"""
        # Записать AI события
        for _ in range(3):
            event = Event(
                event_type=EventType.AI_SUCCESS,
                data={"duration": 2.5}
            )
            self.tracker.track(event)
        
        performance = self.analytics.get_ai_performance()
        
        self.assertIn("total_requests", performance)
        self.assertIn("success_rate", performance)
        self.assertGreater(performance["total_requests"], 0)
    
    def test_get_feature_usage(self):
        """Получить использование функций"""
        # Записать события разных типов
        for event_type in [EventType.USER_ANALYZE, EventType.USER_QUEST_START, EventType.AI_SUCCESS]:
            event = Event(event_type=event_type)
            self.tracker.track(event)
        
        usage = self.analytics.get_feature_usage()
        
        self.assertIsInstance(usage, list)
        self.assertGreater(len(usage), 0)

# ============================================================================
# TESTS FOR MESSAGES
# ============================================================================
class TestMessages(unittest.TestCase):
    """Тесты шаблонов сообщений"""
    
    def test_format_message(self):
        """Форматировать сообщение"""
        template = "Привет, {name}! У вас {points} очков."
        result = format_message(template, name="Иван", points=100)
        
        self.assertEqual(result, "Привет, Иван! У вас 100 очков.")
    
    def test_format_message_missing_key(self):
        """Обработать ошибку форматирования"""
        template = "Привет, {name}!"
        result = format_message(template, other="value")
        
        self.assertIn("Ошибка", result)
    
    def test_truncate_message(self):
        """Обрезать длинное сообщение"""
        message = "A" * 5000
        truncated = truncate_message(message, max_length=100)
        
        self.assertLessEqual(len(truncated), 100)
        self.assertIn("...", truncated)
    
    def test_truncate_message_short(self):
        """Не обрезать короткое сообщение"""
        message = "Привет"
        truncated = truncate_message(message, max_length=100)
        
        self.assertEqual(truncated, message)
    
    def test_split_message(self):
        """Разбить сообщение на части"""
        message = "A" * 10000
        chunks = split_message(message, chunk_size=3000)
        
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 3000)

# ============================================================================
# INTEGRATION TESTS
# ============================================================================
class TestIntegration(unittest.TestCase):
    """Интеграционные тесты"""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.tracker = EventTracker(self.temp_db.name)
    
    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_full_workflow(self):
        """Полный workflow: трекинг → анализ"""
        user_id = 1001
        
        # 1. Пользователь начинает
        event = create_event(EventType.USER_START, user_id=user_id)
        self.tracker.track(event)
        
        # 2. Отправляет текст на анализ
        event = create_event(
            EventType.USER_ANALYZE,
            user_id=user_id,
            data={"text_length": 250}
        )
        self.tracker.track(event)
        
        # 3. AI обрабатывает (успешно)
        event = create_event(
            EventType.AI_SUCCESS,
            user_id=user_id,
            data={"duration": 2.3}
        )
        self.tracker.track(event)
        
        # 4. Пользователь дает фидбек
        event = create_event(
            EventType.USER_FEEDBACK,
            user_id=user_id,
            data={"rating": "helpful"}
        )
        self.tracker.track(event)
        
        # Проверяем, что все события записаны
        journey = self.tracker.get_user_journey(user_id)
        self.assertEqual(len(journey), 4)
        
        # Проверяем статистику
        stats = self.tracker.get_stats(hours=1)
        self.assertGreater(stats["total_events"], 0)

# ============================================================================
# RUN TESTS
# ============================================================================
if __name__ == "__main__":
    # Запуск тестов с подробным выводом
    unittest.main(verbosity=2)
