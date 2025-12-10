# Bookmarks System Documentation (v0.18.0)

## Overview

The Bookmarks system (`v0.18.0`) allows users to save and manage content they find valuable across the bot's features. Users can bookmark news analyses, lessons, tools, and resources for quick access later.

---

## Features

### 📌 Core Capabilities

1. **Save Content**: Users can bookmark any analysis, lesson, tool, or resource with one click
2. **View Bookmarks**: Browse all saved bookmarks organized by type
3. **Remove Bookmarks**: Delete unwanted bookmarks
4. **Track Views**: System tracks when users last viewed each bookmark
5. **Multiple Types**: Support for different content types:
   - 📰 News (from news analysis)
   - 🎓 Lessons (from teaching)
   - 🧰 Tools (from resources)
   - 📚 Resources (from free resources)

---

## Database Schema

### Table: `user_bookmarks_v2`
Stores all user bookmarks with full content

```sql
CREATE TABLE user_bookmarks_v2 (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    bookmark_type TEXT NOT NULL,  -- news/lesson/tool/resource
    content_title TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_source TEXT,          -- where it came from (manual_news, etc)
    external_id TEXT,             -- reference to original request/lesson ID
    rating INTEGER DEFAULT 0,     -- user's rating (0-5 stars)
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    viewed_count INTEGER DEFAULT 0,
    last_viewed_at DATETIME,
    UNIQUE(user_id, bookmark_type, external_id)
)
```

**Indices:**
- `idx_bookmarks_user_id` on `user_id` for quick user lookups
- `idx_bookmarks_type` on `bookmark_type` for filtering by type
- `idx_bookmarks_added` on `added_at` DESC for chronological ordering

### Table: `bookmark_history`
Tracks all bookmark actions for audit trail

```sql
CREATE TABLE bookmark_history (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    bookmark_id INTEGER,
    action TEXT,  -- 'added', 'removed', 'viewed', 'rated'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

---

## Backend Functions

All functions are defined in `bot.py` (lines 1660-1783).

### `add_bookmark(user_id, bookmark_type, content_title, content_text, external_id, source)`

Saves or updates a bookmark.

**Parameters:**
- `user_id`: Telegram user ID
- `bookmark_type`: One of 'news', 'lesson', 'tool', 'resource'
- `content_title`: Short title/heading
- `content_text`: Full content text
- `external_id`: Reference to original item
- `source`: Where the bookmark came from

**Returns:** `(success: bool, message: str)`

**Example:**
```python
success, msg = add_bookmark(
    user_id=123456,
    bookmark_type="news",
    content_title="Bitcoin ETF approved...",
    content_text="Analysis of the Bitcoin ETF approval...",
    external_id="req_789",
    source="manual_news"
)
```

---

### `remove_bookmark(user_id, bookmark_id)`

Deletes a bookmark, with ownership verification.

**Parameters:**
- `user_id`: Telegram user ID (for verification)
- `bookmark_id`: Database ID of bookmark to remove

**Returns:** `(success: bool, message: str)`

**Example:**
```python
success, msg = remove_bookmark(user_id=123456, bookmark_id=42)
```

---

### `get_user_bookmarks(user_id, bookmark_type=None, limit=100)`

Retrieves all bookmarks for a user, optionally filtered by type.

**Parameters:**
- `user_id`: Telegram user ID
- `bookmark_type`: (Optional) Filter by type ('news', 'lesson', 'tool', 'resource')
- `limit`: Max number of results

**Returns:** List of bookmark dictionaries

**Example:**
```python
news_bookmarks = get_user_bookmarks(user_id=123456, bookmark_type="news", limit=50)
# Returns:
# [
#   {
#     'id': 1,
#     'bookmark_type': 'news',
#     'content_title': 'Bitcoin ETF...',
#     'content_text': 'Full analysis...',
#     'viewed_count': 3,
#     'last_viewed_at': '2025-12-02 23:00:00',
#     'added_at': '2025-12-01 10:00:00'
#   },
#   ...
# ]
```

---

### `update_bookmark_views(bookmark_id, user_id)`

Increments view count and updates last viewed timestamp.

**Parameters:**
- `bookmark_id`: Database ID of bookmark
- `user_id`: Telegram user ID (for verification)

**Returns:** `(success: bool, new_view_count: int)`

**Example:**
```python
success, count = update_bookmark_views(bookmark_id=42, user_id=123456)
```

---

### `get_bookmark_count(user_id, bookmark_type=None)`

Counts total bookmarks or by type.

**Parameters:**
- `user_id`: Telegram user ID
- `bookmark_type`: (Optional) Count for specific type

**Returns:** `count: int`

**Example:**
```python
total = get_bookmark_count(user_id=123456)        # Total: 15
news_count = get_bookmark_count(user_id=123456, bookmark_type="news")  # News: 8
```

---

## User Interface

### Main Menu Button
- **Label**: 📌 Закладки
- **Callback**: `start_bookmarks`
- **Location**: Main menu keyboard (line 2240+)

### Commands

#### `/my_bookmarks` or `📌 Закладки` button
Shows all bookmarks grouped by type with emoji indicators.

**Output format:**
```
📌 <b>МОИ ЗАКЛАДКИ</b>

📰 <b>Новости (5)</b>
1. Bitcoin ETF approved...
   👁️ Просмотров: 3 | 📅 Сохранено: 2 дня назад

🎓 <b>Уроки (3)</b>
2. Introduction to Smart Contracts...
   👁️ Просмотров: 1 | 📅 Сохранено: 1 неделю назад

[Меню] [Удалить]
```

### Buttons in Content Responses

#### News Analysis (v0.18.0 NEW)
After user sends news, the response now includes:
- 👍 Helpful / 👎 Not helpful (existing)
- **📌 Save to bookmarks** (NEW) - saves the analysis
- 🔄 Reanalyze
- 📚 Learn more / 📋 Menu

**Callback Data Format:** `save_bookmark_news_{request_id}`

---

## Implementation Flow

### Saving a Bookmark from News

1. User sends news text (e.g., "Bitcoin ETF approved")
2. Bot analyzes and displays result with buttons
3. User clicks "📌 Save to bookmarks"
4. `button_callback()` catches `save_bookmark_news_{request_id}`
5. Calls `add_bookmark()` with:
   - Type: "news"
   - Title: Original news text (first 100 chars)
   - Text: Analysis result
   - External ID: request_id
6. Database stores with timestamp
7. User sees: ✅ Saved to bookmarks!

### Viewing Bookmarks

1. User clicks "📌 Закладки" button in main menu
2. `bookmarks_command()` executes
3. Calls `get_user_bookmarks(user_id)`
4. Groups by type and displays formatted list
5. Shows view count and save date for each

### Managing Bookmarks

Future enhancements (planned):
- Delete individual bookmarks via callback
- Rate bookmarks (1-5 stars)
- Search and filter
- Share bookmarks with other users
- Export as document

---

## Technical Notes

### Database Safety
- Uses parameterized queries (no SQL injection)
- UNIQUE constraint prevents duplicate bookmarks
- Cascade delete on user deletion (when implemented)
- Foreign key references for data integrity (when implemented)

### Error Handling
- Validates user ownership before delete
- Checks content exists before saving
- Graceful handling of missing bookmarks
- Detailed error logging

### Performance
- O(1) lookups by user_id (indexed)
- O(n) type filtering (small n expected)
- View count updates are atomic
- Cache-aware to avoid frequent DB hits

---

## Future Enhancements

- [ ] Rating system (show top-rated bookmarks)
- [ ] Search within bookmarks
- [ ] Bookmark collections/folders
- [ ] Share bookmarks with others
- [ ] Export as PDF/document
- [ ] Bookmark recommendations
- [ ] Sync across devices

---

## Troubleshooting

### Bookmark not appearing after save

**Check:**
1. Database connection working: `curl http://localhost:8000/health`
2. User permission: verify `user_id` is correct
3. Content not empty: check that `content_text` has data
4. Database schema: verify `user_bookmarks_v2` table exists

**Debug SQL:**
```sql
SELECT * FROM user_bookmarks_v2 WHERE user_id = 123456;
SELECT COUNT(*) FROM user_bookmarks_v2;
```

### Duplicate bookmarks appearing

**Root cause:** Likely due to `external_id` collision

**Check:**
```sql
SELECT user_id, bookmark_type, external_id, COUNT(*) 
FROM user_bookmarks_v2 
GROUP BY user_id, bookmark_type, external_id 
HAVING COUNT(*) > 1;
```

### Bookmarks disappearing

**Check:**
1. Cleanup job not deleting them (not implemented yet)
2. User clearing cache
3. Database file corruption
4. Permission issues

---

## Statistics (v0.18.0 Deployment)

- **Total Bookmarks Table Rows**: 0 (fresh deployment)
- **Schema Version**: 1 (2 tables, 3 indices)
- **Supported Types**: 4 (news, lesson, tool, resource)
- **Max Bookmarks per Type**: Unlimited (no enforced quota)

---

## Version History

- **v0.18.0** (2025-12-02)
  - ✅ Initial Bookmarks system
  - ✅ Database schema with 2 tables
  - ✅ Backend functions (5 total)
  - ✅ UI integration with news responses
  - ✅ Main menu button
  - 🔄 Future: Callback handlers for management
  - 🔄 Future: Integration with lessons/resources

---

## References

- **Database File**: `/home/sv4096/rvx_backend/rvx_bot.db`
- **Main Code File**: `/home/sv4096/rvx_backend/bot.py`
- **API Server**: `/home/sv4096/rvx_backend/api_server.py`
- **Leaderboard Docs**: `LEADERBOARD_DOCS.md`

---

## Contact & Support

For issues or feature requests related to Bookmarks:
- Check logs in `bot.log`
- Verify database integrity
- Review error messages in Telegram response
