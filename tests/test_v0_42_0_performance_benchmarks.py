"""
🏃 v0.42.0 Performance Benchmarks - Measure Speed & Memory Usage

Tests for:
- Function execution time (critical paths)
- Memory usage profiling
- Database query performance
- Message processing speed
- Cache efficiency

Target: Identify bottlenecks and optimize critical functions
"""

import unittest
import time
import sys
import tracemalloc
from unittest.mock import patch, MagicMock
from typing import Callable, Any
import asyncio


class PerformanceTimer:
    """Context manager for timing code execution."""
    
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start = None
        self.end = None
        self.duration = None
    
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.duration = self.end - self.start
    
    def __str__(self):
        return f"{self.name}: {self.duration*1000:.2f}ms"


class MemoryTracker:
    """Context manager for tracking memory usage."""
    
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start = None
        self.end = None
        self.delta = None
    
    def __enter__(self):
        tracemalloc.start()
        self.start = tracemalloc.get_traced_memory()[0]
        return self
    
    def __exit__(self, *args):
        self.end = tracemalloc.get_traced_memory()[0]
        self.delta = (self.end - self.start) / 1024  # KB
        tracemalloc.stop()
    
    def __str__(self):
        return f"{self.name}: {self.delta:.2f}KB"


class TestFormatFunctionPerformance(unittest.TestCase):
    """Performance tests for message formatting functions."""
    
    def test_format_header_speed(self):
        """format_header should execute quickly."""
        from bot import format_header
        
        with PerformanceTimer("format_header") as timer:
            for _ in range(1000):
                format_header("Test Header")
        
        # Should complete 1000 iterations in < 100ms
        self.assertLess(timer.duration, 0.1, f"format_header took {timer.duration*1000:.2f}ms")
    
    def test_format_section_speed(self):
        """format_section should handle large content efficiently."""
        from bot import format_section
        
        large_content = "x" * 10000
        
        with PerformanceTimer("format_section") as timer:
            for _ in range(100):
                format_section("Title", large_content)
        
        # Should complete 100 iterations in < 200ms
        self.assertLess(timer.duration, 0.2, f"format_section took {timer.duration*1000:.2f}ms")
    
    def test_format_list_items_speed(self):
        """format_list_items should handle large lists efficiently."""
        from bot import format_list_items
        
        large_list = [f"Item {i}" for i in range(1000)]
        
        with PerformanceTimer("format_list_items") as timer:
            for _ in range(10):
                format_list_items(large_list, numbered=True)
        
        # Should complete 10 iterations in < 500ms
        self.assertLess(timer.duration, 0.5, f"format_list_items took {timer.duration*1000:.2f}ms")


class TestLanguageDetectionPerformance(unittest.TestCase):
    """Performance tests for language detection."""
    
    def test_detect_language_speed_short_text(self):
        """detect_user_language should be fast for short text."""
        from bot import detect_user_language
        
        short_text = "Привет мир"
        
        with PerformanceTimer("detect_language (short)") as timer:
            for _ in range(10000):
                detect_user_language(short_text)
        
        # Should complete 10k iterations in < 500ms
        self.assertLess(timer.duration, 0.5)
    
    def test_detect_language_speed_long_text(self):
        """detect_user_language should handle long text efficiently."""
        from bot import detect_user_language
        
        long_text = "Привет " * 1000  # ~7KB
        
        with PerformanceTimer("detect_language (long)") as timer:
            for _ in range(100):
                detect_user_language(long_text)
        
        # Should complete 100 iterations in < 1 second
        self.assertLess(timer.duration, 1.0)


class TestDatabasePerformance(unittest.TestCase):
    """Performance tests for database operations."""
    
    @patch('bot.get_db')
    def test_check_user_banned_speed(self, mock_get_db):
        """check_user_banned should execute quickly."""
        from bot import check_user_banned
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        with PerformanceTimer("check_user_banned") as timer:
            for _ in range(1000):
                check_user_banned(123456)
        
        # Should complete 1000 iterations in < 500ms
        self.assertLess(timer.duration, 0.5)
    
    @patch('bot.get_db')
    def test_get_user_profile_speed(self, mock_get_db):
        """get_user_profile should execute quickly."""
        from bot import get_user_profile
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            123456, "user", "crypto", "active", "medium", 100, 50
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        with PerformanceTimer("get_user_profile") as timer:
            for _ in range(1000):
                get_user_profile(123456)
        
        # Should complete 1000 iterations in < 500ms
        self.assertLess(timer.duration, 0.5)


class TestCachePerformance(unittest.TestCase):
    """Performance tests for caching mechanisms."""
    
    @patch('bot.get_db')
    def test_cache_hit_speed(self, mock_get_db):
        """Cache hits should be very fast."""
        from bot import get_cache
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("cached_response",)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        with PerformanceTimer("cache_hit") as timer:
            for _ in range(10000):
                get_cache("test_key")
        
        # Should complete 10k hits in < 5 seconds
        self.assertLess(timer.duration, 5.0)


class TestInputValidationPerformance(unittest.TestCase):
    """Performance tests for input validation."""
    
    def test_validate_input_speed(self):
        """validate_user_input should be fast for various inputs."""
        from bot import validate_user_input
        
        test_inputs = [
            "Привет",
            "Hello world" * 100,
            "Test input with emojis 🚀",
            "x" * 5000,
        ]
        
        with PerformanceTimer("validate_input") as timer:
            for _ in range(1000):
                for test_input in test_inputs:
                    validate_user_input(test_input)
        
        # Should complete 4000 validations in < 500ms
        self.assertLess(timer.duration, 0.5)


class TestMemoryEfficiency(unittest.TestCase):
    """Memory efficiency tests."""
    
    def test_format_functions_memory_efficiency(self):
        """format_section should not leak memory."""
        from bot import format_section
        
        # Track memory for multiple calls
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()[0]
        
        for _ in range(1000):
            format_section("Title", "Content" * 100)
        
        end_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        
        # Memory usage should be reasonable
        memory_increase_kb = (end_memory - start_memory) / 1024
        # Should not increase by more than 10MB for 1000 calls
        self.assertLess(memory_increase_kb, 10240)
    
    @patch('bot.get_db')
    def test_cache_memory_usage(self, mock_get_db):
        """Cache operations should be memory efficient."""
        from bot import set_cache
        
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()[0]
        
        # Simulate setting many cache entries
        for i in range(100):
            set_cache(f"key_{i}", f"value_{'x'*1000}")
        
        end_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        
        # Should use reasonable memory
        memory_usage_mb = (end_memory - start_memory) / 1024 / 1024
        self.assertLess(memory_usage_mb, 5)


class TestStringProcessingPerformance(unittest.TestCase):
    """Performance tests for string operations."""
    
    def test_context_analysis_speed(self):
        """analyze_message_context should process quickly."""
        from bot import analyze_message_context
        
        test_messages = [
            "Привет бот",
            "Как дела?",
            "Что ты умеешь?",
            "Покажи курсы крипто",
            "Bitcoin цена",
            "Help me please",
        ]
        
        with PerformanceTimer("context_analysis") as timer:
            for _ in range(1000):
                for msg in test_messages:
                    analyze_message_context(msg)
        
        # Should complete 6000 analyses in < 1 second
        self.assertLess(timer.duration, 1.0)
    
    def test_intent_classification_speed(self):
        """classify_intent should classify quickly."""
        from bot import classify_intent
        
        test_messages = [
            "Привет?",
            "Помощь",
            "Крипто новости",
            "What is Bitcoin",
        ]
        
        with PerformanceTimer("intent_classification") as timer:
            for _ in range(1000):
                for msg in test_messages:
                    classify_intent(msg)
        
        # Should complete 4000 classifications in < 500ms
        self.assertLess(timer.duration, 0.5)


class TestConcurrentOperations(unittest.TestCase):
    """Performance tests for concurrent operations."""
    
    @patch('bot.get_db')
    def test_multiple_db_queries_performance(self, mock_get_db):
        """Multiple DB queries should handle concurrency."""
        from bot import check_user_banned
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
        
        # Simulate multiple concurrent queries
        user_ids = list(range(1000, 2000))
        
        with PerformanceTimer("concurrent_queries") as timer:
            for user_id in user_ids:
                check_user_banned(user_id)
        
        # Should complete 1000 queries in < 500ms
        self.assertLess(timer.duration, 0.5)


class TestBoundaryConditions(unittest.TestCase):
    """Performance at boundary conditions."""
    
    def test_very_long_input_processing(self):
        """Should handle very long inputs without performance degradation."""
        from bot import validate_user_input, detect_user_language
        
        very_long_input = "x" * 100000  # 100KB
        
        with PerformanceTimer("very_long_input") as timer:
            for _ in range(10):
                validate_user_input(very_long_input)
                detect_user_language(very_long_input)
        
        # Should process 20 operations in < 2 seconds
        self.assertLess(timer.duration, 2.0)
    
    def test_empty_input_processing(self):
        """Should handle empty inputs very quickly."""
        from bot import validate_user_input, detect_user_language
        
        with PerformanceTimer("empty_input") as timer:
            for _ in range(10000):
                validate_user_input("")
                detect_user_language("")
        
        # Should process 20k operations in < 5 seconds
        self.assertLess(timer.duration, 5.0)


class TestPerformanceBaselines(unittest.TestCase):
    """Establish performance baselines for future optimization."""
    
    def test_baseline_format_header(self):
        """Baseline: format_header execution time."""
        from bot import format_header
        
        times = []
        for _ in range(100):
            with PerformanceTimer() as timer:
                format_header("Test")
            times.append(timer.duration)
        
        avg_time = sum(times) / len(times)
        # Log baseline for future reference
        print(f"\nBASELINE - format_header: {avg_time*1000:.3f}ms average")
        
        # Should be less than 1ms on average
        self.assertLess(avg_time, 0.001)
    
    def test_baseline_detect_language(self):
        """Baseline: language detection execution time."""
        from bot import detect_user_language
        
        times = []
        for _ in range(100):
            with PerformanceTimer() as timer:
                detect_user_language("Привет мир")
            times.append(timer.duration)
        
        avg_time = sum(times) / len(times)
        print(f"BASELINE - detect_language: {avg_time*1000:.3f}ms average")
        
        # Should be less than 5ms on average
        self.assertLess(avg_time, 0.005)
    
    def test_baseline_context_analysis(self):
        """Baseline: message context analysis execution time."""
        from bot import analyze_message_context
        
        times = []
        for _ in range(100):
            with PerformanceTimer() as timer:
                analyze_message_context("Привет бот")
            times.append(timer.duration)
        
        avg_time = sum(times) / len(times)
        print(f"BASELINE - analyze_context: {avg_time*1000:.3f}ms average")
        
        # Should be less than 10ms on average
        self.assertLess(avg_time, 0.01)


if __name__ == '__main__':
    unittest.main()
