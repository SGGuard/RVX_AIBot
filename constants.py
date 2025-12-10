"""
RVX Bot - Global Constants and Configuration

This module centralizes all magic numbers, limits, timeouts, and configuration
values used throughout the bot and API server.
"""

import os
from enum import Enum
from datetime import datetime

# =============================================================================
# API & NETWORK CONFIGURATION
# =============================================================================

API_URL_NEWS = os.getenv("API_URL_NEWS", "http://localhost:8000/explain_news")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30.0"))
API_RETRY_ATTEMPTS = int(os.getenv("API_RETRY_ATTEMPTS", "3"))
API_RETRY_DELAY = float(os.getenv("API_RETRY_DELAY", "0.5"))

# =============================================================================
# INPUT LIMITS & VALIDATION
# =============================================================================

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "4096"))
MAX_MESSAGE_LENGTH = 4096  # Telegram message limit
MAX_CAPTION_LENGTH = 1024
MAX_BUTTON_TEXT_LENGTH = 64  # Telegram callback data limit
MAX_TEXT_LENGTH_FOR_DISPLAY = 4096
MAX_ANALYSIS_INPUT = 10000  # Max characters for API analysis
MAX_ANALYSIS_ITEM = 500  # Max characters for analysis items
MAX_BOOKMARK_TITLE = 100
MAX_BOOKMARK_TEXT = 500
MAX_LESSON_CONTENT = 1000  # Characters to show from lesson
MAX_CACHE_KEY_DISPLAY = 100  # Error message limit

# =============================================================================
# RATE LIMITING & QUOTAS
# =============================================================================

MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "50"))
FLOOD_COOLDOWN_SECONDS = int(os.getenv("FLOOD_COOLDOWN_SECONDS", "3"))
MIN_BREAK_LENGTH = 1000  # Minimum characters before breaking text
CACHE_STATISTICS_MAX_LENGTH = 100  # Max history for statistics

# =============================================================================
# TIMEOUT & PERFORMANCE
# =============================================================================

GRACEFUL_SHUTDOWN_TIMEOUT = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30"))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))  # 5 minutes
CACHE_RESPONSE_TIME_THRESHOLD_MS = 1000  # Response time threshold for metrics

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

DB_PATH = os.getenv("DB_PATH", "rvx_bot.db")
DB_BACKUP_INTERVAL = int(os.getenv("DB_BACKUP_INTERVAL", "86400"))  # 24 hours
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "10"))
CACHE_MAX_AGE_DAYS = int(os.getenv("CACHE_MAX_AGE_DAYS", "7"))
MAX_BACKUP_SIZE_MB = 500

# =============================================================================
# CACHING CONFIGURATION
# =============================================================================

ENABLE_ANALYTICS = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
ENABLE_AUTO_CACHE_CLEANUP = os.getenv("ENABLE_AUTO_CACHE_CLEANUP", "true").lower() == "true"

# =============================================================================
# PERCENTAGE & STATISTICS
# =============================================================================

PERCENTAGE_MULTIPLIER = 100  # For percentage calculations
DEFAULT_PERCENTAGE = 0

# =============================================================================
# AUTHENTICATION & AUTHORIZATION
# =============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
ADMIN_USERS = set(map(int, filter(None, os.getenv("ADMIN_USERS", "").split(","))))
UNLIMITED_ADMIN_USERS = set(map(int, filter(None, os.getenv("UNLIMITED_ADMIN_USERS", "").split(","))))
MANDATORY_CHANNEL_ID = os.getenv("MANDATORY_CHANNEL_ID", "")
MANDATORY_CHANNEL_LINK = os.getenv("MANDATORY_CHANNEL_LINK", "")
UPDATE_CHANNEL_ID = os.getenv("UPDATE_CHANNEL_ID", "")

# =============================================================================
# VERSION & METADATA
# =============================================================================

BOT_VERSION = "0.21.0"  # v0.21.0 - Production Ready
BOT_START_TIME = datetime.now()

# =============================================================================
# AUTHORIZATION LEVELS
# =============================================================================

class AuthLevel(Enum):
    """User authorization levels for command access control."""
    ANYONE = 0
    USER = 1
    ADMIN = 2
    OWNER = 3
