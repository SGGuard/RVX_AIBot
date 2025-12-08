# 🏆 Leaderboard System Documentation (v0.17.0)

## Overview

Leaderboard система в RVX Bot позволяет пользователям видеть рейтинг других пользователей по XP (опыт/очки) за различные периоды времени.

## Features

- ✅ Три временных периода: неделя, месяц, всё время
- ✅ Топ-50 пользователей с кэшированием
- ✅ Показ позиции текущего пользователя
- ✅ Медали для топ-3 (🥇🥈🥉)
- ✅ Background job обновления каждый час
- ✅ API endpoint для интеграции

## Architecture

### Database Schema

```sql
CREATE TABLE leaderboard_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,           -- 'week', 'month', 'all'
    rank INTEGER,                    -- Позиция в рейтинге
    user_id INTEGER,                 -- Telegram user ID
    username TEXT,                   -- Telegram username
    xp INTEGER,                      -- Количество XP
    level INTEGER,                   -- Уровень пользователя
    total_requests INTEGER,          -- Всего запросов
    cached_at TIMESTAMP,             -- Время кэширования
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(period, rank)             -- Один ранг на период
);

CREATE INDEX idx_leaderboard_cache_period ON leaderboard_cache(period, cached_at);
```

### Core Functions (bot.py)

#### `get_leaderboard_data(period: str, limit: int) -> Tuple[List, int]`
Получает данные рейтинга из кэша или БД.

```python
# Parameters
period: str = "all"  # "week", "month", or "all"
limit: int = 50      # Максимум 50 пользователей

# Returns
leaderboard: List[Tuple] = [(rank, user_id, username, xp, level, requests), ...]
total_users: int = количество активных пользователей
```

**Logic:**
1. Пробует получить из кэша (`leaderboard_cache`)
2. Если кэша нет - генерирует из БД
3. Кэширует результаты для будущих запросов
4. Учитывает временной период

#### `get_user_rank(user_id: int, period: str) -> Optional[Tuple]`
Получает позицию конкретного пользователя.

```python
# Returns
(rank, xp, level, total_requests) or None
```

#### `show_leaderboard(update, context, period)`
Показывает красиво отформатированную таблицу лидеров.

```python
# Usage
await show_leaderboard(update, context, "all")
```

### Bot Integration

#### Main Menu Button
```python
[InlineKeyboardButton("🏆 Лидерборд", callback_data="start_leaderboard")]
```

#### Callback Handlers (button_callback)
```python
if data == "leaderboard_week":
    await show_leaderboard(update, context, "week")
    
if data == "leaderboard_month":
    await show_leaderboard(update, context, "month")
    
if data == "leaderboard_all":
    await show_leaderboard(update, context, "all")
```

### Background Job

**Function:** `update_leaderboard_cache(context)`
- Запускается автоматически каждый час
- Обновляет кэш для всех трёх периодов
- Логирует статус обновления

```python
# Configured in main()
job_queue.run_repeating(
    update_leaderboard_cache,
    interval=3600,   # 1 hour
    first=30         # First run after 30 seconds
)
```

### API Endpoint

**Endpoint:** `GET /get_leaderboard`

**Parameters:**
```
period: str = "all"          # Query: "week", "month", "all"
limit: int = 10              # Query: 1-50
user_id: Optional[int] = None # Query: Telegram user ID
```

**Response:**
```json
{
  "period": "all",
  "top_users": [
    {
      "rank": 1,
      "user_id": 123456,
      "username": "john_doe",
      "xp": 500,
      "level": 5,
      "total_requests": 42
    }
  ],
  "user_rank": {
    "rank": 15,
    "xp": 250,
    "level": 3,
    "total_requests": 20,
    "is_in_top": false
  },
  "total_users": 42,
  "cached": true,
  "timestamp": "2025-12-02T23:39:00.000000"
}
```

## User Flow

### Using Leaderboard

1. User clicks "🏆 Лидерборд" button in main menu
2. Bot shows period selection: Неделя, Месяц, Всё время
3. User selects a period
4. Bot displays top-10 with user's rank highlighted
5. If user is outside top-10, their position is shown separately

### Display Format

```
🏆 ТАБЛИЦА ЛИДЕРОВ 📅 (за неделю)
Всего пользователей: 42

🥇 #1. john_doe
   💫 500 XP | Уровень 5 | Запросов: 42

🥈 #2. jane_smith
   💫 450 XP | Уровень 4 | Запросов: 38

🥉 #3. bob_jones
   💫 400 XP | Уровень 4 | Запросов: 35

─────────────────────────────────────
👤 Твоя позиция:
   #15 | 💫 200 XP | Уровень 2
```

## Caching Strategy

### Cache Hierarchy

1. **Memory Cache** (Function parameter)
   - Kэш в памяти на время запроса
   - Нет TTL (используется напрямую)

2. **Database Cache** (leaderboard_cache table)
   - TTL: 1 час (обновляется background job)
   - Три записи на период: week, month, all
   - Максимум 50 записей на период

### Cache Invalidation

Cache обновляется в следующих случаях:

1. **Hourly** - Автоматический background job
2. **Manual** - После изменения XP пользователя (если реализовано)
3. **On Demand** - При первом запросе если кэш пуст

## Performance Considerations

### Query Optimization

**Индексы:**
```sql
CREATE INDEX idx_leaderboard_cache_period ON leaderboard_cache(period, cached_at);
```

**Query Plan:**
```
SELECT rank, user_id, username, xp, level, total_requests
FROM leaderboard_cache
WHERE period = 'all'
ORDER BY rank LIMIT 10
```

**Expected:** < 5ms с индексом

### Scalability

**Current:**
- Supports up to 1000 active users
- Background job: ~100ms per update

**Future Improvements:**
- Redis for distributed caching
- Materialized views for complex ranking
- Async batch updates

## Development Notes

### Adding New Sorting Criteria

To add sorting by different fields:

1. Update `get_leaderboard_data()` ORDER BY clause
2. Update `get_user_rank()` rank calculation logic
3. Update leaderboard_cache schema if needed

Example: Sort by level first:
```python
ORDER BY level DESC, xp DESC, total_requests DESC
```

### Testing

**Manual Test:**
```python
cd /home/sv4096/rvx_backend && python3 << 'EOF'
from bot import get_leaderboard_data, get_user_rank

# Get top 10
data, total = get_leaderboard_data("all", limit=10)
print(f"Top 10 of {total} users")

# Get user rank
rank_data = get_user_rank(123456789, "all")
print(f"User rank: {rank_data}")
EOF
```

**API Test:**
```bash
curl http://localhost:8000/get_leaderboard?period=all&limit=10
```

## Troubleshooting

### Leaderboard shows empty
- Check if `leaderboard_cache` table exists
- Run `update_leaderboard_cache()` manually
- Check if users have XP > 0

### Background job not running
- Check `bot.log` for job status
- Verify APScheduler is active
- Restart bot: `python3 bot.py`

### Stale data
- Cache updates hourly
- To force update: restart bot
- Or call `update_leaderboard_cache()` manually

## Future Enhancements

- [ ] Weekly rewards for top-3 (badges, bonus XP)
- [ ] Personal leaderboard (friends/course-mates)
- [ ] Historical leaderboard (weekly snapshots)
- [ ] Leaderboard announcements (new #1)
- [ ] Anti-gaming measures (suspicious activity detection)

## Version History

- **v0.17.0** (Dec 2, 2025) - Initial Leaderboard System
  - Three time periods
  - Hourly cache updates
  - API endpoint
  - User rank display

## References

- Bot version: v0.17.0
- Database: SQLite with WAL mode
- Cache: In-memory + database hybrid
- Update frequency: 1 hour
