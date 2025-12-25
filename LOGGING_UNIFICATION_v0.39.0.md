# Logging Unification (v0.39.0)

## Overview
Unified logging format across entire bot.py (13,880 lines) with consistent emoji prefixes and structured output.

## Changes Made

### 1. **New RVXFormatter Class**
```python
class RVXFormatter(logging.Formatter):
    """Unified logging formatter with emoji prefixes"""
    
    LEVEL_EMOJI = {
        logging.DEBUG: "🔍",      # Debug/Info messages
        logging.INFO: "ℹ️",       # Info messages
        logging.WARNING: "⚠️",    # Warnings
        logging.ERROR: "❌",      # Errors
        logging.CRITICAL: "🔴"    # Critical issues
    }
```

**Features:**
- Automatic emoji prefix based on log level
- Separate formatting for console (with emoji) and files (without emoji)
- Preserves context data (user_id, details)
- Graceful formatting with proper alignment

### 2. **New setup_logger() Function**
```python
def setup_logger(name=None, level=logging.INFO):
    """Configure unified logger with file and console handlers"""
```

**Configuration:**
- **Console Handler**: 
  - Level: INFO and above (visible)
  - Format: `HH:MM:SS [LEVEL] emoji message`
  - Shows: debug emoji, full context
  
- **File Handler**:
  - Level: DEBUG and above (comprehensive)
  - Format: `YYYY-MM-DD HH:MM:SS [LEVEL] module: message`
  - Clean: no emoji, structured for parsing

### 3. **Logger Initialization**
Replaced:
```python
# OLD (inconsistent, basic)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
```

With:
```python
# NEW (unified, emoji-based)
logger = setup_logger(__name__)
```

### 4. **Emoji Removal from Code**
**Before:**
```python
logger.warning("⚠️ UPDATE_CHANNEL_ID не установлен")
logger.error(f"❌ DB ошибка: {e}")
logger.info("✅ Database pool initialized")
```

**After:**
```python
logger.warning("UPDATE_CHANNEL_ID не установлен")
logger.error(f"DB ошибка: {e}")
logger.info("Database pool initialized")
```

The emoji is now added **automatically by RVXFormatter** based on log level!

### 5. **Early Logger for Startup**
Created early logger for `cleanup_stale_bot_processes()` which runs before main logger initialization:

```python
init_logger = logging.getLogger('startup')
init_logger.setLevel(logging.DEBUG)
if not init_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', 
        datefmt='%H:%M:%S'
    ))
    init_logger.addHandler(handler)
```

## Output Examples

### Console Output (with emoji)
```
00:45:00 [INFO    ] ℹ️ User action performed [user_id=12345]
00:45:00 [WARNING ] ⚠️ UPDATE_CHANNEL_ID not configured
00:45:00 [ERROR   ] ❌ Database error: timeout
00:45:00 [CRITICAL] 🔴 Fatal system error
```

### File Output (structured, no emoji)
```
2025-12-26 00:45:00 [INFO    ] bot: User action performed [user_id=12345]
2025-12-26 00:45:00 [WARNING ] bot: UPDATE_CHANNEL_ID not configured
2025-12-26 00:45:00 [ERROR   ] bot: Database error: timeout
2025-12-26 00:45:00 [CRITICAL] bot: Fatal system error
```

## Benefits

### Code Quality
✅ **Consistency** - All logs follow same format
✅ **Maintainability** - Emoji added automatically, not in code
✅ **Readability** - Clear visual hierarchy with emoji
✅ **Parsability** - File logs suitable for log analysis tools

### Developer Experience
✅ **Less Typing** - No emoji in logger calls
✅ **Clear Semantics** - Level determines emoji
✅ **Easy Updates** - Change emoji in one place (RVXFormatter)
✅ **Context Preservation** - User ID and details logged automatically

### Operational
✅ **Monitoring Ready** - Structured file logs for tools like ELK, Splunk
✅ **Debugging** - Separate debug level for detailed diagnostics
✅ **Auditing** - Complete audit trail in bot.log

## Migration Stats

| Metric | Count |
|--------|-------|
| Logger calls updated | 100+ |
| Emoji removed from code | 50+ |
| Log levels standardized | 13,880 lines |
| New RVXFormatter | 45 lines |
| New setup_logger | 35 lines |

## Testing

✅ **Test Results:**
- All log levels work correctly (DEBUG → CRITICAL)
- Emoji prefixes display correctly in console
- File output is structured and emoji-free
- Context data (user_id) is preserved
- No duplicate logs
- No file handler conflicts

## Files Modified

- `bot.py` - 
  - Lines 360-420: New RVXFormatter class and setup_logger function
  - Lines 30-80: Updated cleanup_stale_bot_processes early logger
  - Lines 100+: Removed emoji from all logger calls
  - Lines 272+: Updated config_loader logger

## Next Steps (v0.39.0+)

1. ✅ Logging unification (THIS COMMIT)
2. ⏳ Schema validation & database init (30 min)
3. ⏳ IP-based rate limiting (2-3 hours)
4. ⏳ Add full type hints (20-30 hours)
5. ⏳ Expand unit tests (target 40%+ coverage)

## Rollback Instructions

If needed, restore old logging:
```python
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
```

---

**Commit:** Logging Unification (v0.39.0)  
**Date:** 2025-12-26  
**Impact:** HIGH - Improves code quality and maintainability
