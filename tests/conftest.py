"""
pytest configuration и fixtures для всех тестов
"""

import pytest
import sys
import os

# Добавляем путь к коду
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ==================== GLOBAL FIXTURES ====================

@pytest.fixture(scope="session")
def test_environment():
    """Конфигурация тестового окружения"""
    os.environ['TESTING'] = 'true'
    return {
        'testing': True,
        'db_path': ':memory:',  # In-memory DB для тестов
        'timeout': 5
    }


# ==================== MARKERS ====================

def pytest_configure(config):
    """Регистрируем custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security tests"
    )


# ==================== REPORTING ====================

def pytest_collection_modifyitems(config, items):
    """Модифицируем items для добавления маркеров"""
    for item in items:
        # Интеграционные тесты
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        
        # Security тесты
        if "injection" in item.nodeid or "security" in item.nodeid:
            item.add_marker(pytest.mark.security)


# ==================== HELPERS ====================

@pytest.fixture
def cleanup_env():
    """Очистка переменных окружения после теста"""
    yield
    # Cleanup
    if 'TESTING' in os.environ:
        del os.environ['TESTING']
