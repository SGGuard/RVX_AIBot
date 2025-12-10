# 🚀 DEPLOYMENT CHECKLIST - Duplicate Bot Instance Fix

**Commit**: f91724a (with Procfile + Lock mechanism + DB migration fixes from c06fbea)

**Status**: ✅ All fixes pushed to GitHub and ready for Railway deployment

---

## Pre-Deployment Checklist ✓

- [x] Lock mechanism added to bot.py (main function + finally block)
- [x] Procfile updated with signal handling (trap + wait)
- [x] All commits pushed: 2d2d492, c06fbea, f91724a
- [x] Documentation created (DUPLICATE_BOT_FIX.md)
- [x] No syntax errors in bot.py
- [x] Git history clean

---

## Railway Deployment Steps

### Step 1: Redeploy
1. Go to [https://railway.app/dashboard](https://railway.app/dashboard)
2. Select RVX project
3. Click **Redeploy** button
4. Wait 2-3 minutes for deployment

### Step 2: Verify Environment Variables
Ensure these are SET in Railway:
```
API_URL_NEWS=http://localhost:8000/explain_news
API_URL_BASE=http://localhost:8000
RAILWAY_ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=<your-bot-token>
GEMINI_API_KEY=<your-gemini-key>
```

**How to check/set:**
1. Railway Dashboard → Project → Variables
2. Add/update each variable if missing
3. Redeploy after changes

### Step 3: Monitor Initial Startup
Watch logs during first 30 seconds:

**Expected (Good):**
```
🔒 Bot lock acquired (PID: 1234)
✅ Event tracker initialized
✅ AI honesty system loaded
✅ Analytics system ready
...
🚀 БОТ ПОЛНОСТЬЮ ЗАПУЩЕН И ГОТОВ К РАБОТЕ
```

**NOT Expected (Bad):**
```
🚨 CRITICAL: Another bot instance is already running!
Conflict: terminated by other getUpdates request
```

---

## Post-Deployment Verification (5 minutes)

### Test 1: Bot Responsiveness
1. Send `/start` to bot
2. Should receive welcome message within 5 seconds
3. ✅ = Bot is responsive

### Test 2: Button Functionality
1. Send `/teach` or click "Учиться" button
2. Click "Выбрать урок" button
3. Should NOT see Conflict errors
4. Should receive response within 10 seconds
5. ✅ = Buttons work

### Test 3: Context Preservation
1. Ask: "Что такое блокчейн?"
2. Wait for response
3. Follow up: "Расскажи подробнее"
4. Bot should reference previous context
5. ✅ = Context saved

### Test 4: Health Check
```bash
curl http://<railway-url>/health
```
Should return JSON with status and cache info
✅ = API server responsive

### Test 5: No Duplicate Instances
Check logs for lines like:
```
🚨 CRITICAL: Another bot instance is already running!
```
Should see **ZERO** of these
✅ = No duplicates

---

## Troubleshooting

### Problem: "Conflict: terminated by other getUpdates"
**Still occurring?**
1. Hard restart: Delete dyno → Redeploy
2. Check logs for multiple "🔒 Bot lock acquired" messages
3. Verify TELEGRAM_BOT_TOKEN is correct (not split across instances)

### Problem: Bot won't start
**Error: "Another bot instance already running"**
1. Wait 60 seconds (Railway cleanup)
2. Redeploy again
3. Check if previous dyno is still terminating (Railway logs)

### Problem: Buttons still don't work
**Steps:**
1. Verify API_URL_NEWS is set in Railway
2. Check api_server.py started: look for "🚀 INITIALIZING FastAPI"
3. Curl health endpoint: `curl http://localhost:8000/health`
4. Check if button callback handler exists in bot.py (should be around line 8600+)

---

## Rollback Plan (if needed)

If deployment causes issues:

### Quick Rollback
1. Railway Dashboard → Deployments
2. Find previous working deployment
3. Click "Redeploy" on that version

### Manual Rollback (if needed)
```bash
cd /home/sv4096/rvx_backend
git revert c06fbea
git push origin main
# Then redeploy on Railway
```

---

## Key Changes Summary

| Component | Change | Benefit |
|-----------|--------|---------|
| **bot.py** | Added lock mechanism at startup | Prevents second instance from starting |
| **bot.py** | Added finally block cleanup | Lock file removed on shutdown |
| **Procfile** | Added trap handler | Ensures graceful termination of child processes |
| **Procfile** | Increased sleep to 2s | Allows bot.py more time to initialize |
| **api_server.py** | Smart API_URL detection | Works on Railway without hardcoding |
| **bot.py** | Aggressive DB migration | Ensures schema matches code |

---

## Support Files

- **DUPLICATE_BOT_FIX.md** - Technical details and explanation
- **RAILWAY_FIX_GUIDE.md** - Railway deployment guide (from previous fix)
- **AUDIT_FINDINGS.md** - Complete audit of all 10 issues found

---

## Success Metrics (Post-Deployment)

✅ **Bot starts without error**
- Sees: "🔒 Bot lock acquired"
- Doesn't see: "Another bot instance"

✅ **No Conflict errors**
- Logs show NO "Conflict: terminated by other getUpdates"

✅ **Buttons work**
- Click doesn't crash bot
- Callback handlers execute properly

✅ **Context preserved**
- Bot remembers previous messages
- Database saves work

✅ **API calls succeed**
- teach_lesson endpoint connects
- Responses received within timeout

---

## Final Notes

This fix addresses the **root cause** of duplicate bot instances via:
1. **File-based lock** - Prevents second bot.py from starting
2. **Signal handling** - Ensures clean shutdown
3. **Railway-specific config** - Smart API URL detection

The combination prevents the "Conflict" errors that were making buttons fail and context disappear.

**Next deployment time**: Now ready! Click Redeploy on Railway.
