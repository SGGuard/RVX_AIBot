# config.py
# Централизованная конфигурация для RVX Bot
# Version: 0.25.0

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# TELEGRAM CONFIGURATION
# ============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# ============================================================================
# API SERVER CONFIGURATION
# ============================================================================
API_URL_NEWS = os.getenv("API_URL_NEWS", "http://localhost:8000")
API_EXPLAIN_NEWS_ENDPOINT = f"{API_URL_NEWS}/explain_news"
API_HEALTH_ENDPOINT = f"{API_URL_NEWS}/health"
API_TIMEOUT_SECONDS = int(float(os.getenv("API_TIMEOUT", "10")))

# ============================================================================
# AI MODEL CONFIGURATION
# ============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))

# AI Provider Fallback Chain
AI_PROVIDERS = {
    "groq": {
        "enabled": True,
        "timeout": 5,
        "model": "mixtral-8x7b-32768",
        "api_key": os.getenv("GROQ_API_KEY", ""),
    },
    "mistral": {
        "enabled": True,
        "timeout": 10,
        "model": "mistral-large-latest",
        "api_key": os.getenv("MISTRAL_API_KEY", ""),
    },
    "gemini": {
        "enabled": True,
        "timeout": 30,
        "model": GEMINI_MODEL,
        "api_key": GEMINI_API_KEY,
    },
}

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
DATABASE_PATH = os.getenv("DATABASE_PATH", "./rvx_bot.db")
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_TIMEOUT = int(os.getenv("DATABASE_TIMEOUT", "30"))

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "86400"))  # 24 hours
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "100"))

# Redis configuration (optional)
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# ============================================================================
# RATE LIMITING
# ============================================================================
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", "60"))  # seconds
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

# ============================================================================
# BOT BEHAVIOR
# ============================================================================
BOT_MAX_MESSAGE_LENGTH = int(os.getenv("BOT_MAX_MESSAGE_LENGTH", "4096"))
BOT_CHUNK_SIZE = int(os.getenv("BOT_CHUNK_SIZE", "3000"))
BOT_TYPING_SPEED = int(os.getenv("BOT_TYPING_SPEED", "50"))  # chars per second

# 👑 CREATOR: ID 7216426044 - Owner of RVX_AIBot
BOT_ADMIN_IDS = [7216426044] + [int(x) for x in os.getenv("BOT_ADMIN_IDS", "0").split(",") if x.isdigit()]
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "7216426044"))  # Creator ID

# ============================================================================
# FEATURES
# ============================================================================
FEATURE_QUESTS_ENABLED = os.getenv("FEATURE_QUESTS_ENABLED", "true").lower() == "true"
FEATURE_EDUCATION_ENABLED = os.getenv("FEATURE_EDUCATION_ENABLED", "true").lower() == "true"
FEATURE_ANALYTICS_ENABLED = os.getenv("FEATURE_ANALYTICS_ENABLED", "true").lower() == "true"
FEATURE_FEEDBACK_ENABLED = os.getenv("FEATURE_FEEDBACK_ENABLED", "true").lower() == "true"

# ============================================================================
# QUEST CONFIGURATION
# ============================================================================
QUEST_DAILY_REWARD_POINTS = int(os.getenv("QUEST_DAILY_REWARD", "50"))
QUEST_WEEKLY_REWARD_POINTS = int(os.getenv("QUEST_WEEKLY_REWARD", "200"))
QUEST_MAX_ACTIVE_QUESTS = int(os.getenv("QUEST_MAX_ACTIVE", "5"))
QUEST_MIN_COMPLETE_TIME = int(os.getenv("QUEST_MIN_TIME", "300"))  # 5 minutes

# ============================================================================
# DROPS CONFIGURATION
# ============================================================================
DROPS_MIN_AMOUNT = int(os.getenv("DROPS_MIN_AMOUNT", "1"))
DROPS_MAX_AMOUNT = int(os.getenv("DROPS_MAX_AMOUNT", "1000"))
DROPS_DEFAULT_RARITY = os.getenv("DROPS_DEFAULT_RARITY", "common")

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # json or text
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() == "true"
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "./logs/bot.log")

# ============================================================================
# DEVELOPMENT / PRODUCTION
# ============================================================================
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
PORT = int(os.getenv("PORT", "8000"))

# ============================================================================
# VALIDATION
# ============================================================================
def validate_config():
    """Проверить критические значения конфигурации"""
    errors = []
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("❌ TELEGRAM_BOT_TOKEN не установлен")
    
    if not GEMINI_API_KEY:
        errors.append("❌ GEMINI_API_KEY не установлен")
    
    if not API_URL_NEWS or API_URL_NEWS == "http://localhost:8000":
        if ENVIRONMENT == "production":
            errors.append("⚠️ API_URL_NEWS использует localhost (может быть проблема в продакшене)")
    
    if errors:
        print("\n⚠️ КОНФИГУРАЦИЯ ИМЕЕТ ПРОБЛЕМЫ:\n")
        for error in errors:
            print(f"  {error}")
        if ENVIRONMENT == "production":
            raise ValueError("Критические параметры конфигурации отсутствуют!")
    
    return len(errors) == 0

# ============================================================================
# EXPORT
# ============================================================================
if __name__ == "__main__":
    print("✅ Конфигурация загружена успешно")
    print(f"📍 Окружение: {ENVIRONMENT}")
    print(f"🤖 Telegram Bot: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"🔑 Gemini API: {GEMINI_API_KEY[:10]}...")
    print(f"📊 Database: {DATABASE_PATH}")
    print(f"💾 Cache: {'✅ Включен' if CACHE_ENABLED else '❌ Отключен'}")
    print(f"🔴 Redis: {'✅ Включен' if REDIS_ENABLED else '❌ Отключен'}")
