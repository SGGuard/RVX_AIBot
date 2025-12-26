# 📋 Remaining Handlers - Localization Checklist

## Priority 1: High Visibility (Next to Localize)

### 1. History System
**Status:** ❌ Not Started  
**Location:** Lines with `"start_history"`  
**Handlers:** 2
- Clear history display
- Clear confirmation
- Clear execution

**Sample Keys Needed:**
```
history.title: "📜 История"
history.empty: "История пуста"
history.clear_confirm: "Вы уверены?"
history.cleared: "История очищена"
history.clear_btn: "🗑️ Очистить историю"
history.back: "⬅️ Назад"
```

---

### 2. Settings/Menu System
**Status:** ❌ Not Started  
**Location:** Lines with `"start_menu"`  
**Handlers:** 3-5
- Language selection
- Notification settings
- Theme settings
- Clear cache
- Privacy policy

**Sample Keys Needed:**
```
settings.title: "⚙️ Настройки"
settings.language: "🌐 Язык"
settings.notifications: "🔔 Уведомления"
settings.theme: "🎨 Тема"
settings.clear_cache: "🗑️ Очистить кэш"
settings.back: "⬅️ Назад"
```

---

### 3. Stats/Progress Display
**Status:** ❌ Not Started  
**Location:** Lines with `"start_stats"` or `"show_stats"`  
**Handlers:** 2
- User statistics display
- Learning progress
- Achievement count
- XP breakdown

**Sample Keys Needed:**
```
stats.title: "📊 Статистика"
stats.total_xp: "Всего XP:"
stats.level: "Уровень:"
stats.courses: "Курсов пройдено:"
stats.tests: "Тестов пройдено:"
stats.back: "⬅️ Назад"
```

---

## Priority 2: Medium Visibility

### 4. Resources Menu
**Status:** ❌ Not Started  
**Handlers:** 2-3
- Resource listing
- Category selection

**Estimated Time:** 30 minutes

---

### 5. Quiz/Test System
**Status:** ❌ Not Started  
**Handlers:** 5-10
- Quiz start
- Question display
- Answer submission
- Results display
- Score messages

**Estimated Time:** 1-2 hours

---

### 6. Course Content Display
**Status:** ❌ Not Started  
**Handlers:** 10+
- Lesson content
- Progress indicators
- Completion messages

**Estimated Time:** 1-2 hours

---

## Priority 3: Lower Visibility

### 7. Analysis System
**Status:** ❌ Not Started  
**Handlers:** 5+
- Analysis request handling
- Result formatting
- Error messages for API

**Estimated Time:** 1-2 hours

---

### 8. Admin/Moderator Commands
**Status:** ❌ Not Started  
**Handlers:** 15+
- Ban user
- Unban user
- Send announcement
- View stats

**Estimated Time:** 2-3 hours

---

### 9. Utility Functions
**Status:** ❌ Not Started  
**Handlers:** 50+
- Error messages
- Success messages
- Helper functions
- Logging messages

**Estimated Time:** 4-6 hours

---

## 🎯 Quick Start - Next Handlers

### History Handler Template

**Find:**
```python
if data == "start_history":
    # Display history
```

**Update to:**
```python
if data == "start_history":
    user_id = query.from_user.id
    
    # Get translations
    title = await get_text("history.title", user_id)
    clear_btn = await get_text("history.clear_btn", user_id)
    back_btn = await get_text("history.back", user_id)
    
    # Build keyboard with translated buttons
    keyboard = [
        [InlineKeyboardButton(clear_btn, callback_data="clear_history_confirm")],
        [InlineKeyboardButton(back_btn, callback_data="back_to_start")]
    ]
    
    # Use translated title
    text = f"<b>{title}</b>\n\n..."
```

---

### Settings Handler Template

**Pattern:**
```python
if data == "start_menu":  # Settings
    user_id = query.from_user.id
    
    # Fetch all needed translations
    title = await get_text("settings.title", user_id)
    language_btn = await get_text("settings.language", user_id)
    notifications_btn = await get_text("settings.notifications", user_id)
    back_btn = await get_text("settings.back", user_id)
    
    # Build buttons with translations
    keyboard = [
        [InlineKeyboardButton(language_btn, callback_data="lang_select")],
        [InlineKeyboardButton(notifications_btn, callback_data="notif_select")],
        [InlineKeyboardButton(back_btn, callback_data="back_to_start")]
    ]
    
    text = f"⚙️ <b>{title}</b>\n\n..."
```

---

## 📊 Localization Completion Tracker

| Component | Status | ETA | Handler Count |
|-----------|--------|-----|----------------|
| ✅ Profile | Done | - | 2 |
| ✅ Leaderboard | Done | - | 3 |
| ✅ Teaching | Done | - | 5 |
| ✅ Quests | Done | - | 1 |
| ✅ Bookmarks | Done | - | 1 |
| ✅ Menu | Done | - | 1 |
| ✅ Ask Question | Done | - | 1 |
| ✅ Calculator | Done | - | 1 |
| ✅ Courses | Done | - | 1 |
| ✅ Activities | Done | - | 1 |
| ❌ History | Next | 15min | 2 |
| ❌ Settings | Next | 45min | 4 |
| ❌ Stats | Next | 30min | 2 |
| ❌ Resources | Coming | 30min | 2 |
| ❌ Quiz | Coming | 2hr | 10 |
| ❌ Analysis | Coming | 1hr | 5 |
| ❌ Admin | Coming | 2hr | 15 |
| ❌ Utility | Coming | 5hr | 50 |
| **TOTAL** | **18/135** | **15-20h** | **117** |

---

## 🚀 How to Speed Up Remaining Work

1. **Template Approach:** Copy the pattern from ask_command, apply to similar handlers
2. **Batch Updates:** Group similar components together (e.g., all quiz handlers)
3. **Reusable Keys:** Share keys across components where text is identical
4. **Automated Search:** Find all hardcoded Russian text with grep, add keys in batch

---

## 💾 Key Storage Organization

**Suggested Grouping:**
```
profile.*          - 22 keys (✅ Done)
leaderboard.*      - 17 keys (✅ Done)
menu.*             - 13 keys (✅ Done)
bookmarks.*        - 17 keys (✅ Done)
teach.*            - 10 keys (✅ Done)
airdrops.*         - 30 keys (✅ Done)
badge.*            - 22 keys (✅ Done)
quests.*           - 1 key (✅ Done)
question.*         - 14 keys (✅ Done)
calculator.*       - 4 keys (✅ Done)
resources.*        - 6 keys (⏳ Next)
learn.*            - 6 keys (✅ Done)
activities.*       - 14 keys (✅ Done)
history.*          - 6 keys (⏳ Next)
settings.*         - 8 keys (⏳ Next)
stats.*            - 6 keys (⏳ Next)
quiz.*             - 15 keys (📋 Coming)
analysis.*         - 10 keys (📋 Coming)
error.*            - 20 keys (📋 Coming)
success.*          - 15 keys (📋 Coming)
```

---

## ⏱️ Estimated Timeline

| Phase | Handlers | Time | Coverage |
|-------|----------|------|----------|
| Session 1 | 14 | 2h | 10.4% |
| **Session 2** | **4** | **1h** | **13.3%** |
| Session 3 | 6 (History, Settings, Stats, Resources, etc.) | 2h | 18.5% |
| Session 4 | 15 (Quiz, Analysis, Admin) | 4h | 29.6% |
| Session 5+ | 80+ (Utilities, Edge Cases) | 10h+ | 100% |

---

## 📝 Quick Reference

**To Localize Next Handler:**

1. Identify all hardcoded Russian strings
2. Create keys: `component.key_name`
3. Add to both ru.json and uk.json
4. Replace strings with `await get_text("component.key", user_id)`
5. Test with Ukrainian user

**Time per handler:** 10-20 minutes (once pattern known)

---

Generated: 2025-12-26  
Next Session Target: History + Settings + Stats = 6 more handlers

