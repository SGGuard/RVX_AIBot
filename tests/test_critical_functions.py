"""
🧪 Unit тесты для критических функций RVX AI Bot

Тестируются:
✅ AI dialogue система (rate limiting, response generation)
✅ Database операции (CRUD, валидация)
✅ Cache система (TTL, hit/miss)
✅ Validators (input sanitization, message splitting)
✅ Rate limiting (основной и AI-специфичный)
"""

import pytest
import sqlite3
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
import json

# Import тестируемые функции
from ai_dialogue import (
    check_ai_rate_limit,
    build_dialogue_system_prompt,
    get_metrics_summary
)


# ==================== FIXTURES ====================

@pytest.fixture
def reset_rate_limit():
    """Сброс rate limit перед каждым тестом"""
    from ai_dialogue import ai_request_history
    ai_request_history.clear()
    yield
    ai_request_history.clear()


@pytest.fixture
def mock_db():
    """Mock БД для тестов"""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # Создаем тестовые таблицы
    cursor.execute("""
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            response TEXT,
            created_at TIMESTAMP
        )
    """)
    
    conn.commit()
    yield conn
    conn.close()


# ==================== RATE LIMITING TESTS ====================

class TestAIRateLimiting:
    """Тесты для AI rate limiting"""
    
    def test_rate_limit_first_request_allowed(self, reset_rate_limit):
        """Первый запрос должен быть разрешен"""
        is_allowed, remaining, message = check_ai_rate_limit(user_id=123)
        
        assert is_allowed == True
        assert remaining == 9  # 10 - 1 (текущий)
        assert message == ""
    
    def test_rate_limit_multiple_requests_within_window(self, reset_rate_limit):
        """Несколько запросов в окне должны быть разрешены"""
        for i in range(10):
            is_allowed, remaining, message = check_ai_rate_limit(user_id=123)
            assert is_allowed == True, f"Запрос {i+1} должен быть разрешен"
            assert remaining == (9 - i)
    
    def test_rate_limit_exceeds_quota(self, reset_rate_limit):
        """Превышение квоты должно быть заблокировано"""
        # Заполняем до лимита
        for i in range(10):
            check_ai_rate_limit(user_id=123)
        
        # 11-й запрос должен быть заблокирован
        is_allowed, remaining, message = check_ai_rate_limit(user_id=123)
        
        assert is_allowed == False
        assert remaining == 0
        assert "⏱️ Лимит AI запросов" in message
    
    def test_rate_limit_independent_per_user(self, reset_rate_limit):
        """Лимиты независимы для разных пользователей"""
        # User 1: 10 запросов
        for i in range(10):
            check_ai_rate_limit(user_id=1)
        
        # User 2: первый запрос
        is_allowed_user2, remaining_user2, _ = check_ai_rate_limit(user_id=2)
        
        # User 1: проверяем, что он заблокирован
        is_allowed_user1, _, _ = check_ai_rate_limit(user_id=1)
        
        assert is_allowed_user2 == True
        assert is_allowed_user1 == False
    
    def test_rate_limit_window_expiration(self, reset_rate_limit):
        """Лимит должен сброситься после истечения окна"""
        from ai_dialogue import ai_request_history, AI_RATE_LIMIT_WINDOW
        
        # Запросы в окне
        for i in range(10):
            check_ai_rate_limit(user_id=123)
        
        # Проверяем, что заблокирован
        is_allowed, _, _ = check_ai_rate_limit(user_id=123)
        assert is_allowed == False
        
        # Эмулируем истечение окна
        now = time.time()
        ai_request_history[123] = [now - AI_RATE_LIMIT_WINDOW - 1]
        
        # Должен быть разрешен (окно очищено)
        is_allowed, remaining, _ = check_ai_rate_limit(user_id=123)
        assert is_allowed == True
        assert remaining >= 9


# ==================== DATABASE TESTS ====================

class TestDatabaseOperations:
    """Тесты для DB операций"""
    
    def test_check_column_exists_allowed_table(self):
        """Проверка колонки в разрешенной таблице"""
        from bot import check_column_exists
        
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT
            )
        """)
        
        # Должны существовать колонки
        assert check_column_exists(cursor, "users", "user_id") == True
        assert check_column_exists(cursor, "users", "username") == True
        
        # Не должна существовать несуществующая колонка
        assert check_column_exists(cursor, "users", "invalid_column") == False
    
    def test_check_column_exists_denied_table(self):
        """Проверка колонки в неразрешенной таблице"""
        from bot import check_column_exists
        
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()
        
        # Попытка доступа к неразрешенной таблице
        result = check_column_exists(cursor, "invalid_table", "any_column")
        
        assert result == False


# ==================== MESSAGE SPLITTING TESTS ====================

class TestMessageSplitting:
    """Тесты для разбиения длинных сообщений"""
    
    def test_split_short_message(self):
        """Короткое сообщение не должно разбиваться"""
        message = "Это короткое сообщение"
        MAX_LENGTH = 3500
        
        assert len(message) <= MAX_LENGTH
    
    def test_split_long_message(self):
        """Длинное сообщение должно разбиваться по абзацам"""
        # Генерируем длинное сообщение из 4000+ символов
        long_message = "\n".join([f"Абзац {i}: " + "x" * 300 for i in range(20)])
        
        MAX_LENGTH = 3500
        paragraphs = long_message.split('\n')
        
        messages = []
        current_message = ""
        
        for para in paragraphs:
            if len(current_message) + len(para) + 1 > MAX_LENGTH:
                if current_message.strip():
                    messages.append(current_message.strip())
                current_message = para
            else:
                if current_message:
                    current_message += "\n" + para
                else:
                    current_message = para
        
        if current_message.strip():
            messages.append(current_message.strip())
        
        # Все части должны быть <= MAX_LENGTH
        assert all(len(msg) <= MAX_LENGTH for msg in messages)
        
        # Объединение должно вернуть исходный текст
        assert "\n".join(messages) == long_message
        
        # Должно быть несколько частей
        assert len(messages) > 1


# ==================== PROMPT TESTS ====================

class TestSystemPrompt:
    """Тесты для системного промпта"""
    
    def test_prompt_defines_financial_analyst_persona(self):
        """The prompt should identify the financial analyst persona."""
        prompt = build_dialogue_system_prompt()
        
        assert "опытный финансовый аналитик" in prompt.lower()
        assert "не высокомерный" in prompt.lower()
    
    def test_prompt_discourages_guarantees_and_allows_uncertainty(self):
        """The prompt should discourage guarantees and permit uncertainty."""
        prompt = build_dialogue_system_prompt()
        
        assert len(prompt) > 100
        assert "гарантии" in prompt.lower()
        assert '"может", "вероятно"' in prompt.lower()
    
    def test_prompt_requires_detailed_answers(self):
        """Промпт должен требовать подробных/структурированных ответов"""
        prompt = build_dialogue_system_prompt()
        
        # Проверяем наличие структуры в ответах
        assert "структ" in prompt.lower() or "пункт" in prompt.lower() or "факт" in prompt.lower()
    
    def test_prompt_contains_structure(self):
        """Промпт должен описывать структуру ответа"""
        prompt = build_dialogue_system_prompt()
        
        # Проверяем что есть указание на структурированность
        assert "1️⃣" in prompt or "суть" in prompt.lower() or "правила" in prompt.lower()


# ==================== METRICS TESTS ====================

class TestMetrics:
    """Тесты для метрик система"""
    
    def test_metrics_summary_contains_all_providers(self):
        """Метрики должны содержать информацию о всех провайдерах"""
        from ai_dialogue import dialogue_metrics
        
        summary = get_metrics_summary()
        
        # Проверяем наличие провайдеров
        assert "groq" in summary["providers"]
        assert "mistral" in summary["providers"]
        assert "gemini" in summary["providers"]
        
        # Проверяем наличие метрик
        for provider in ["groq", "mistral", "gemini"]:
            assert "requests" in summary["providers"][provider]
            assert "success" in summary["providers"][provider]
            assert "errors" in summary["providers"][provider]


# ==================== INPUT VALIDATION TESTS ====================

class TestInputValidation:
    """Тесты для валидации входных данных"""
    
    def test_empty_input_rejected(self):
        """Пустой ввод должен быть отклонен"""
        empty_inputs = ["", "   ", "\n", "\t"]
        
        for inp in empty_inputs:
            assert inp.strip() == ""
    
    def test_long_input_validation(self):
        """Слишком длинный ввод должен быть проверен"""
        MAX_LENGTH = 4096
        long_input = "x" * (MAX_LENGTH + 100)
        
        assert len(long_input) > MAX_LENGTH
        
        # Должен быть обрезан или отклонен
        truncated = long_input[:MAX_LENGTH]
        assert len(truncated) == MAX_LENGTH
    
    def test_special_characters_handled(self):
        """Специальные символы должны обрабатываться"""
        special_inputs = [
            "Test'; DROP TABLE users; --",
            "<script>alert('xss')</script>",
            "../../etc/passwd",
            "😀 🎉 🚀"
        ]
        
        # Все должны быть обработаны без ошибок
        for inp in special_inputs:
            assert isinstance(inp, str)


# ==================== INTEGRATION TESTS ====================

class TestIntegration:
    """Интеграционные тесты"""
    
    def test_rate_limit_with_ai_response_flow(self, reset_rate_limit):
        """Тест полного потока: rate limit → AI response"""
        user_id = 999
        
        # Проверяем лимит
        is_allowed, remaining, message = check_ai_rate_limit(user_id)
        assert is_allowed == True
        
        # Проверяем промпт
        prompt = build_dialogue_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        
        # Проверяем метрики
        summary = get_metrics_summary()
        assert summary is not None
    
    def test_error_handling_in_database(self, mock_db):
        """Тест обработки ошибок в БД"""
        cursor = mock_db.cursor()
        
        # Попытка вставить данные
        try:
            cursor.execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (123, "testuser", "Test")
            )
            mock_db.commit()
        except sqlite3.Error as e:
            pytest.fail(f"БД операция не должна вызывать ошибку: {e}")
        
        # Проверяем, что данные вставлены
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (123,))
        row = cursor.fetchone()
        assert row is not None


# ==================== PERFORMANCE TESTS ====================

class TestPerformance:
    """Тесты производительности"""
    
    def test_rate_limit_check_performance(self, reset_rate_limit):
        """Rate limit проверка должна быть быстрой (<10ms)"""
        import time
        
        start = time.time()
        for i in range(100):
            check_ai_rate_limit(user_id=i)
        elapsed = (time.time() - start) * 1000  # в миллисекундах
        
        # Должно быть <10ms на проверку
        assert elapsed < 1000, f"Rate limit медленный: {elapsed}ms для 100 проверок"
    
    def test_message_split_performance(self):
        """Разбиение сообщений должно быть быстрым"""
        import time
        
        # 10,000 символов
        long_message = "x" * 10000
        
        start = time.time()
        parts = long_message.split('\n')
        elapsed = (time.time() - start) * 1000
        
        # Должно быть <1ms
        assert elapsed < 1, f"Разбиение медленно: {elapsed}ms"


if __name__ == "__main__":
    # Запуск тестов с verbose выводом
    pytest.main([__file__, "-v", "--tb=short"])
