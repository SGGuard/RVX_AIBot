# v0.43.0 Language Selection Fix - Complete Solution

## Problem
After subscription check, the "Select Language" button was disappearing with no follow-up message.

### Root Cause
The `i18n.py` module was trying to import `get_db()` from `db_service`, but this function didn't exist in that module.

Error in Railway logs:
```
Error getting user language from DB: cannot import name 'get_db' from 'db_service'
```

This caused `get_user_language()` to fail silently, preventing the language selection flow from executing.

## Solution Implemented

### 1. Fixed Database Import in i18n.py
**File**: `i18n.py` (lines 1-240)

Changed from:
```python
from db_service import get_db
# ... later in function
with get_db() as conn:
    cursor = conn.cursor()
```

Changed to:
```python
import sqlite3
# ... later in function
conn = sqlite3.connect("rvx_bot.db")
cursor = conn.cursor()
```

**Rationale**: The bot.py already uses `sqlite3.connect()` directly. This pattern is consistent throughout the codebase and doesn't depend on unavailable db_service functions.

### 2. Added Language Column to Database Schema
**File**: `bot.py`

#### In `migrate_database()` (line 2007):
Added `'language'` to the `required_columns` set:
```python
required_columns = {
    'user_id', 'username', 'first_name', 'created_at', 'total_requests',
    'last_request_at', 'is_banned', 'ban_reason', 'daily_requests',
    'daily_reset_at', 'knowledge_level', 'xp', 'level', 'badges',
    'requests_today', 'last_request_date', 'language'  # ← NEW
}
```

#### In `migrate_database()` (line 2047):
Added language column to the CREATE TABLE statement:
```sql
CREATE TABLE users (
    -- ... existing columns ...
    last_request_date TEXT,
    language TEXT DEFAULT 'ru'  -- ← NEW
)
```

#### In `migrate_database()` (line 2157):
Added migration check for existing databases:
```python
if not check_column_exists(cursor, 'users', 'language'):
    logger.info("  • Добавление колонки language для i18n поддержки...")
    cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
    migrations_needed = True
```

#### In `init_database()` (line 2590):
Added language column to initial table creation:
```sql
CREATE TABLE IF NOT EXISTS users (
    -- ... existing columns ...
    last_request_date TEXT,
    language TEXT DEFAULT 'ru'  -- ← NEW
)
```

### 3. Cleaned Up Debug Logging
**File**: `bot.py`

Removed excessive print statements from:
- `check_subscription_` callback handler (lines 9495-9560)
- `start_command()` function (lines 6085-6105)

Kept structured logging via `logger` module for production visibility.

## Testing Performed

### Local Testing
1. ✅ Database initialization with new language column
2. ✅ `get_user_language()` returns cached values
3. ✅ `get_user_language()` queries DB and returns 'uk' for set user
4. ✅ `get_user_language()` returns default 'ru' for unset user
5. ✅ `set_user_language()` persists to database
6. ✅ Language cache works correctly
7. ✅ Syntax check passes for bot.py and i18n.py

### Expected Production Flow
1. User clicks `/start`
2. `start_command()` calls `get_user_lang(user_id, default=None)`
3. If `None`, shows language selection: "🇷🇺 Русский" / "🇺🇦 Українська"
4. User clicks language button → `handle_language_selection()` saves choice
5. User subscribes to channel
6. User clicks "Я подписался, проверить"
7. `check_subscription_` handler:
   - Clears subscription cache
   - Checks subscription status
   - If subscribed:
     - Gets user's language via `get_user_lang()` (should be set now)
     - Shows success message
   - If not subscribed:
     - Shows retry prompt

## Commits
1. **da48551**: Fixed i18n.py to use sqlite3.connect directly
2. **e2c0c16**: Added language column to database schema
3. **45c653e**: Cleaned up debug logging for production

## Deployment Status
✅ All changes committed to main branch
✅ Deployed to Railway (v0.43.0)
✅ Ready for production testing

## Files Modified
- `i18n.py` - Fixed imports and simplified database access
- `bot.py` - Added language column migrations and schema updates
