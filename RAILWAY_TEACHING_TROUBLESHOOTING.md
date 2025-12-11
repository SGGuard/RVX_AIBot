# 🔧 Railway Deployment Troubleshooting Guide

**Current Issue:** Teaching feature showing fallback lesson instead of API-generated lessons

---

## 🎯 Root Cause

Your **bot and API are in separate Railway containers** that cannot communicate via `localhost:8080`. They need a public URL or service-to-service networking.

---

## ✅ Solution Steps for Railway

### Step 1: Set Environment Variables in Railway Dashboard

**For Bot Service:**
```
API_URL=https://rvx-api.railway.app
API_BASE_URL=https://rvx-api.railway.app
TEACH_API_URL=https://rvx-api.railway.app/teach_lesson
```

**For API Service:**
```
(No changes needed - API runs on port 8080)
```

### Step 2: Verify API Service Public URL

1. Go to Railway Dashboard → **Plugins** → **API Service**
2. Click **Settings**
3. Look for **Public URL** or **Domain**
4. It should look like: `https://rvx-api.railway.app`
5. Test it: `curl https://rvx-api.railway.app/health`

If not enabled:
1. Click **Generate Domain** 
2. Wait 1-2 minutes for Railway to assign a domain
3. Use that domain in environment variables

### Step 3: Update Bot Service Environment

1. Go to Railway Dashboard → **Plugins** → **Bot Service**
2. Click **Variables**
3. Add/Update:
   ```
   API_URL=https://rvx-api.railway.app
   ```
4. Click **Deploy**

### Step 4: Restart Both Services

1. Stop bot container (it will auto-restart)
2. API will restart automatically
3. Test `/teach` command in bot

---

## 🐛 How to Diagnose

After redeployment, check bot logs for these messages:

### ✅ Success (API Found)
```
🔗 Using TEACH_API_URL: https://rvx-api.railway.app/teach_lesson
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=https://rvx-api.railway.app, API_BASE_URL=None
📚 Подготовка урока: Основы криптографии и блокчейна (beginner)
📤 Получен урок: 1500+ символов
✅ Урок готов: 🌱 Основы криптографии и блокчейна
```

### ❌ Fallback (API Not Found)
```
🔗 Using TEACH_API_URL: http://localhost:8080/teach_lesson
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=None, API_BASE_URL=None
📚 Подготовка урока: Основы криптографии и блокчейна (beginner)
❌ Connection error при запросе к http://localhost:8080/teach_lesson: Connection refused
⚠️ Используется fallback урок (API недоступен)
```

---

## 🔄 Priority Order for API URL Resolution

The bot checks environment variables in this order:

1. **`TEACH_API_URL`** ← Explicit override (highest priority)
   - Set this if you have a custom API deployment
   
2. **`API_BASE_URL`** ← Preferred for Railway
   - Example: `https://rvx-api.railway.app`
   
3. **`API_URL`** ← Alternative for Railway
   - Example: `https://rvx-api.railway.app`
   
4. **`http://localhost:8080`** ← If RAILWAY_ENVIRONMENT set
   - Only works if both services in same internal network
   
5. **`http://localhost:8000`** ← Local development default
   - Used when no environment variables set

---

## 🚀 Quick Fix Checklist

- [ ] API Service has **Public URL/Domain enabled** in Railway
- [ ] Bot environment has **API_URL** variable set
- [ ] Both services are **deployed** (not just restarted)
- [ ] Bot logs show correct `TEACH_API_URL` (not localhost)
- [ ] Can manually test API: `curl https://rvx-api.railway.app/health`
- [ ] Teaching endpoint exists: `curl https://rvx-api.railway.app/docs`

---

## 🔍 Testing the Connection

### From Your Local Machine

```bash
# Test API is accessible
curl https://rvx-api.railway.app/health

# Expected response:
{
  "status": "healthy",
  "gemini_available": true,
  ...
}
```

### Check Bot Logs in Railway

1. Go to **Bot Service** → **Deployments**
2. Click latest deployment
3. Click **Logs**
4. Trigger `/teach` command in bot
5. Look for `Using TEACH_API_URL:` line
6. Verify it's using `https://` URL, not `localhost`

---

## 📊 Configuration Examples

### ✅ Correct Setup (Railway)
```bash
# Bot environment variables
API_URL=https://rvx-api.railway.app
TEACH_API_URL=https://rvx-api.railway.app/teach_lesson
RAILWAY_ENVIRONMENT=production
```

### ❌ Wrong Setup (localhost doesn't work in separate containers)
```bash
# This won't work!
API_URL=http://localhost:8080
TEACH_API_URL=http://localhost:8080/teach_lesson
```

### ⚠️ Fallback (automatic but not ideal)
```bash
# Environment variables NOT set
# Bot will try localhost:8080 and fail, then use fallback
```

---

## 🆘 Still Not Working?

### Check These:

1. **API Service Port**
   - Should be `8080` in Railway
   - Check: `echo $PORT` in API logs

2. **API Service Health**
   - Visit: `https://rvx-api.railway.app/health`
   - Should return `200 OK`

3. **Bot Logs Show Correct URL**
   - Look for: `Using TEACH_API_URL: https://...`
   - NOT `http://localhost:8080`

4. **Network Connectivity**
   - Railway services can't use localhost
   - Must use public domain or service-to-service networking

5. **Environment Variable Names** (case-sensitive)
   - `API_URL` ✅
   - `api_url` ❌
   - `API_URL_NEWS` (for different endpoint)

---

## 📞 Debug Commands

### Show URL being used
Check bot logs after triggering `/teach`:
```
grep "Using TEACH_API_URL" bot.log
```

### Show environment
```
grep "Environment:" bot.log
```

### Show which error occurred
```
grep "Connection error\|Timeout\|fallback" bot.log
```

---

## ✅ After You Fix It

Once API is reachable, you should see:
- ✅ Full lessons from API (not fallback)
- ✅ Lessons load in 2-3 seconds
- ✅ No "Connection error" messages
- ✅ Teaching feature works normally

---

**TL;DR:** Set `API_URL=https://rvx-api.railway.app` in bot environment variables and restart. That's it!
