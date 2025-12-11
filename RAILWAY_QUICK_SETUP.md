# 🚀 Railway Deployment - Quick Setup Guide

**Current Problem:** Teaching feature showing fallback because `API_URL` environment variable is not set.

---

## ⚡ QUICK FIX (2 minutes)

### Step 1️⃣: Get Your API Public URL

1. Go to **Railway Dashboard**
2. Click **RVX API** service (not the bot!)
3. Click **Settings** tab
4. Scroll to **Networking**
5. Look for **Public URL** or **Custom Domain**
6. If you see a URL like `https://rvx-api.railway.app` - COPY IT ✅
7. If you see **"Generate Domain"** button - CLICK IT and wait 2 minutes

### Step 2️⃣: Set Environment Variable in Bot Service

1. Go to **Railway Dashboard**
2. Click **RVX Bot** service
3. Click **Variables** tab
4. Click **+ New Variable**
5. Set:
   - **Name:** `API_URL`
   - **Value:** `https://rvx-api.railway.app` (replace with YOUR actual URL)
6. Click **Save** or press Enter
7. Wait 30 seconds - bot will auto-restart

### Step 3️⃣: Test It

1. Open your bot in Telegram
2. Send `/start`
3. Click "🎓 Учиться" (Learn)
4. Click "📚 Рекомендуемый урок" or any course
5. Click any lesson like "Основы криптографии"

**Should see:** Full lesson with content (not "offline mode")

---

## 🔍 Verify It's Working

Check bot logs and look for:

```
🔗 Using TEACH_API_URL: https://rvx-api.railway.app/teach_lesson
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=https://rvx-api.railway.app
✅ Получен урок: 1500+ символов
✅ Урок готов: 🌱 Основы криптографии и блокчейна
```

If you still see:
```
🔗 Using TEACH_API_URL: http://localhost:8080/teach_lesson
❌ Connection error
```

Then `API_URL` is still not set. Go back to Step 2 and verify the variable is saved.

---

## 📊 Environment Variables Summary

After proper setup, your **Bot Service** should have:

| Variable | Value | Purpose |
|----------|-------|---------|
| `TELEGRAM_BOT_TOKEN` | `bot123...` | Bot token from BotFather |
| `API_URL` | `https://rvx-api.railway.app` | **← NEW!** Points to API service |
| Other vars | ... | (existing vars) |

---

## ❓ Troubleshooting

**Q: I set `API_URL` but it's still showing "offline mode"**

A: Railway might need 1-2 minutes to fully restart. Wait and try again.

**Q: Where do I find my API's public URL?**

A: 
1. Go to RVX API service
2. Click "Settings"
3. Look for "Public URL" or "Custom Domain" section
4. Should show something like `https://rvx-api.railway.app`
5. If not, click "Generate Domain"

**Q: The API URL shows `localhost` in my bot logs**

A: Environment variable didn't save properly. Check:
1. You're in **Bot Service** (not API service)
2. Click **Variables** tab (not Settings)
3. See `API_URL` listed there
4. If not, add it again and save

**Q: I restarted but still getting fallback**

A: The new code (v0.35.3) was deployed but bot container needs to pull it. Options:
1. Click "Redeploy" on the bot service
2. Or kill and restart the bot manually
3. Or wait 5 minutes for Railway auto-check

---

## 📝 What Changed (v0.35.x)

**Code Fixes:**
- ✅ Fixed hardcoded `127.0.0.1:8080` in bot.py
- ✅ Added environment variable routing in bot.py
- ✅ Improved logging to show which URL is used
- ✅ Fixed variable name in teacher.py
- ✅ Removed `datetime.utcnow()` deprecation warnings

**What You Need to Do:**
- Set `API_URL` environment variable in Railway bot service
- That's it! Everything else is already coded.

---

## 🎯 Priority System (How Bot Finds API)

Bot checks in this order:

1. **`API_URL_NEWS`** ← Explicit for news endpoint (if set)
2. **`API_URL`** ← Main variable (what you need to set!)
3. **`API_BASE_URL`** ← Alternative name for same thing
4. **`http://localhost:8080`** ← Fallback on Railway (usually doesn't work)
5. **`http://localhost:8000`** ← Local dev fallback

---

## 🆘 Still Stuck?

If after setting `API_URL` you STILL see `API_URL=None` in logs:

1. **Check variable is saved:**
   - Go to Bot Service → Variables
   - Type `API_URL` in search box
   - Should show your value

2. **Force redeploy:**
   - Go to Bot Service → Deployments
   - Click the 3-dot menu on latest deployment
   - Click "Redeploy"
   - Wait 2-3 minutes

3. **Check API service is running:**
   - Go to API Service
   - Should say "Running" with a green indicator
   - If "Crashed", click "Redeploy"

---

**Status:** Code is ready ✅ | Just need `API_URL` variable set 🎯

Commit: `b9de7f5` (v0.35.3 - bot URL routing fix)
