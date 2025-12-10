# 🚀 Railway Configuration Fix Guide

## 🔴 **CRITICAL: Do this NOW on Railway**

### Step 1: Set Environment Variables

Go to Railway Dashboard → Your Project → Settings → Variables

Add/Update these variables:

```
API_URL_NEWS = http://localhost:8000/explain_news
API_URL_BASE = http://localhost:8000
RAILWAY_ENVIRONMENT = production
```

**OR if you have separate services on Railway:**

```
API_URL_NEWS = https://your-railway-api-url.railway.app/explain_news
API_URL_BASE = https://your-railway-api-url.railway.app
```

### Step 2: Redeploy

1. Go to Railway Dashboard → Your Project
2. Click your web service
3. Click "Redeploy" button (↻ icon)
4. Wait 2-3 minutes for deployment

### Step 3: Verify Fix

Check logs for:
```
✅ API_URL_NEWS configured: [your-url]
✅ Столбцы ПОСЛЕ миграции: {'id', 'user_id', 'message_type', 'content', 'intent', 'created_at'}
```

---

## 🐛 What Was Fixed

### Issue 1: teach_lesson Always Failed
**Error:** `All connection attempts failed` on http://localhost:8000/teach_lesson

**Root Cause:** Railway doesn't have localhost:8000, but code had hardcoded default

**Fix:** Smart API URL detection:
- Checks `API_URL_NEWS` env var first
- Falls back to `API_URL_BASE` on Railway
- Only uses localhost:8000 for local development
- Logs the configured URL at startup

### Issue 2: Context Not Saved
**Error:** `sqlite3.OperationalError: table conversation_history has no column named message_type`

**Root Cause:** Old database schema didn't have new columns

**Fix:** Aggressive database migration:
- Disables foreign keys during migration
- Forces ALTER TABLE commands to execute
- Validates columns BEFORE and AFTER
- Logs all changes for debugging
- Adds default values to prevent NULL errors

---

## ✅ Expected Behavior After Fix

- ✅ Buttons work correctly
- ✅ teach_lesson endpoint connects successfully
- ✅ Context is saved and retrieved
- ✅ AI dialogue remembers conversation
- ✅ No "localhost:8000" errors
- ✅ No "column named message_type" errors

---

## 📋 Checklist

- [ ] Deploy commit c06fbea on Railway
- [ ] Set API_URL_NEWS environment variable
- [ ] Wait 3 minutes for restart
- [ ] Test /start command
- [ ] Test AI dialogue
- [ ] Test teach command
- [ ] Verify logs show API URL configured
- [ ] Verify logs show database migration completed

---

## 🔍 If Still Having Issues

Check Railway logs for these patterns:

1. **Good signs:**
   ```
   🔗 API_URL_NEWS configured: http://...
   ✅ Столбцы ПОСЛЕ миграции: {'id', 'user_id', ...}
   ✅ Финальные столбцы conversation_history: {...}
   ```

2. **Bad signs (means fix didn't work):**
   ```
   ❌ Connection error при запросе к http://localhost:8000
   table conversation_history has no column named message_type
   RAILWAY_ENVIRONMENT not set
   ```

---

## 📞 Debug Commands

If you need to check the database locally:

```bash
# Check if message_type column exists
sqlite3 rvx_bot.db "PRAGMA table_info(conversation_history);"

# Check if data exists
sqlite3 rvx_bot.db "SELECT COUNT(*) FROM conversation_history;"

# See structure
sqlite3 rvx_bot.db ".schema conversation_history"
```

---

**Last Updated:** 2025-12-10
**Commit:** c06fbea
**Status:** READY FOR DEPLOYMENT
