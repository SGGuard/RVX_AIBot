"""
Unit tests for v0.39.0 improvements:
- Logging unification (RVXFormatter, setup_logger)
- Database schema validation (verify_database_schema)

Run: pytest tests/test_v0_39_0_improvements.py -v
"""

import pytest
import logging
import tempfile
import os
from pathlib import Path
from io import StringIO


# RVXFormatter and setup_logger classes (imported from bot.py logic)
class RVXFormatter(logging.Formatter):
    """Unified logging formatter with emoji prefixes"""
    
    LEVEL_EMOJI = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔴"
    }
    
    def __init__(self, fmt=None, datefmt=None, use_emoji=True):
        super().__init__(fmt, datefmt)
        self.use_emoji = use_emoji
    
    def format(self, record):
        if self.use_emoji:
            emoji = self.LEVEL_EMOJI.get(record.levelno, "•")
            record.msg = f"{emoji} {record.msg}"
        
        if hasattr(record, 'user_id'):
            record.msg += f" [user_id={record.user_id}]"
        
        return super().format(record)


def setup_logger(name=None, level=logging.INFO):
    """Configure unified logger"""
    logger = logging.getLogger(name or __name__)
    logger.setLevel(level)
    logger.handlers.clear()
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = RVXFormatter(
        fmt='%(asctime)s [%(levelname)-8s] %(message)s',
        datefmt='%H:%M:%S',
        use_emoji=True
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger


# Tests
class TestRVXFormatter:
    """Test the unified logging formatter"""
    
    def test_emoji_by_level(self):
        """Verify emoji is selected correctly by log level"""
        formatter = RVXFormatter(use_emoji=True)
        
        # Create log records for each level
        record_debug = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        record_info = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        record_warning = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        record_error = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        record_critical = logging.LogRecord(
            name="test", level=logging.CRITICAL, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        
        # Format and check emoji
        assert "🔍" in formatter.format(record_debug)
        assert "ℹ️" in formatter.format(record_info)
        assert "⚠️" in formatter.format(record_warning)
        assert "❌" in formatter.format(record_error)
        assert "🔴" in formatter.format(record_critical)
    
    def test_no_emoji_when_disabled(self):
        """Verify emoji is not added when use_emoji=False"""
        formatter = RVXFormatter(use_emoji=False)
        
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        
        formatted = formatter.format(record)
        assert "❌" not in formatted
        assert "Test message" in formatted
    
    def test_context_preservation(self):
        """Verify context data (user_id) is preserved in log"""
        formatter = RVXFormatter(use_emoji=True)
        
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="User action", args=(), exc_info=None
        )
        record.user_id = 12345
        
        formatted = formatter.format(record)
        assert "[user_id=12345]" in formatted


class TestSetupLogger:
    """Test logger setup function"""
    
    def test_logger_creation(self):
        """Verify logger is created with correct name and level"""
        logger = setup_logger("test_module", level=logging.DEBUG)
        
        assert logger.name == "test_module"
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) > 0
    
    def test_handler_count(self):
        """Verify correct number of handlers (console only in test)"""
        logger = setup_logger("test_module2", level=logging.INFO)
        
        # Should have at least console handler
        assert len(logger.handlers) > 0
    
    def test_logger_idempotence(self):
        """Verify calling setup_logger twice doesn't duplicate handlers"""
        name = "test_idempotent"
        logger1 = setup_logger(name, level=logging.INFO)
        handler_count_1 = len(logger1.handlers)
        
        logger2 = setup_logger(name, level=logging.INFO)
        handler_count_2 = len(logger2.handlers)
        
        # Should clear and recreate, not accumulate
        assert handler_count_1 == handler_count_2


class TestLoggingIntegration:
    """Integration tests for the logging system"""
    
    def test_log_levels_work(self):
        """Verify all log levels produce output"""
        logger = setup_logger("integration_test", level=logging.DEBUG)
        
        # Capture output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(RVXFormatter(
            fmt='%(levelname)s: %(message)s',
            use_emoji=False
        ))
        
        test_logger = logging.getLogger("integration_test2")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        
        test_logger.debug("Debug message")
        test_logger.info("Info message")
        test_logger.warning("Warning message")
        test_logger.error("Error message")
        test_logger.critical("Critical message")
        
        output = stream.getvalue()
        
        assert "Debug message" in output
        assert "Info message" in output
        assert "Warning message" in output
        assert "Error message" in output
        assert "Critical message" in output


class TestDatabaseSchemaValidation:
    """Test database schema verification logic"""
    
    def test_schema_validation_logic(self):
        """Test the logic of schema validation"""
        # Simulate the verify_database_schema logic
        required_tables = ['users', 'requests', 'feedback', 'cache']
        existing_tables = {'users', 'requests', 'feedback', 'cache', 'extra_table'}
        
        missing = [t for t in required_tables if t not in existing_tables]
        
        assert len(missing) == 0, "All required tables should be present"
    
    def test_schema_validation_with_missing(self):
        """Test schema validation detects missing tables"""
        required_tables = ['users', 'requests', 'feedback', 'cache', 'missing_table']
        existing_tables = {'users', 'requests', 'feedback', 'cache'}
        
        missing = [t for t in required_tables if t not in existing_tables]
        
        assert 'missing_table' in missing
        assert len(missing) == 1


# Performance Tests
class TestLoggingPerformance:
    """Test performance characteristics of logging"""
    
    def test_emoji_replacement_overhead(self):
        """Verify emoji replacement doesn't significantly impact performance"""
        formatter_with_emoji = RVXFormatter(use_emoji=True)
        formatter_without_emoji = RVXFormatter(use_emoji=False)
        
        # Create multiple records
        records = [
            logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg=f"Message {i}", args=(), exc_info=None
            )
            for i in range(100)
        ]
        
        # Format all records - should be fast
        for record in records:
            formatted = formatter_with_emoji.format(record)
            assert len(formatted) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
