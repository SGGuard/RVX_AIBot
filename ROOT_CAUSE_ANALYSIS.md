# 🔴 ROOT CAUSE ANALYSIS: Why Teaching Feature Shows Fallback

**Status:** IDENTIFIED & ACTIONABLE  
**Severity:** CRITICAL  
**Date:** December 11, 2025

---

## 🎯 The Problem

Your bot shows fallback lesson instead of real lessons:
```
🌱 Основы криптографии и блокчейна (offline mode)
Это базовое объяснение, так как сервис обучения временно недоступен.
```

---

## 🔍 Root Cause

**Primary Issue:** `API_URL` environment variable is **NOT SET** in Railway bot service

**Evidence from logs:**
```
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=None, API_BASE_URL=None
❌ Connection error при запросе к http://localhost:8080/teach_lesson
```

**Why it fails:**
1. Bot and API are in **separate Railway containers**
2. When `API_URL` is not set, code falls back to `localhost:8080`
3. `localhost:8080` only works within THE SAME container
4. Different containers cannot communicate via localhost ❌
5. Connection times out → fallback lesson is shown

---

## 🏗️ Architecture Problem

```
Railway Infrastructure:
┌─────────────────────────────────────┐
│                                     │
│  ┌──────────────────┐               │
│  │   Bot Container  │               │
│  │   (localhost)    │               │
│  └──────────────────┘               │
│                                     │
│  ┌──────────────────┐               │
│  │   API Container  │               │
│  │   (localhost)    │               │
│  └──────────────────┘               │
│                                     │
└─────────────────────────────────────┘

Problem: Bot can't reach API via localhost:8080
Solution: Use public API URL instead
```

---

## ✅ Solution (PERMANENT FIX)

### What's Already Done (v0.35.x)

Code is fixed to read `API_URL` environment variable:

**teacher.py (line 315-345):**
```python
teach_api_url = os.getenv("TEACH_API_URL")  # Priority 1
if not teach_api_url:
    api_base_url = os.getenv("API_BASE_URL")  # Priority 2
    if not api_base_url:
        api_url = os.getenv("API_URL")  # Priority 3 ← YOUR JOB
        if api_url:
            api_base_url = api_url.rstrip('/')
```

**bot.py (line 145-160):**
```python
_api_url = os.getenv("API_URL")  # ← Priority 2
if _api_url:
    API_URL_NEWS = _api_url.rstrip('/') + "/explain_news"
```

### What YOU Need to Do

**STEP 1: Get Your API Public URL**

1. Open Railway Dashboard
2. Click **RVX API** service (not Bot!)
3. Click **Settings** tab
4. Look for **Networking** section
5. Find **Public URL** or **Custom Domain**
6. Should look like: `https://rvx-api.railway.app`
7. If not present, click **Generate Domain**

**STEP 2: Set Environment Variable in Bot Service**

1. Go to Railway Dashboard
2. Click **RVX Bot** service
3. Click **Variables** tab
4. Click **+ New Variable** button
5. Fill in:
   - **Name:** `API_URL`
   - **Value:** `https://rvx-api.railway.app` (your actual URL from Step 1)
6. Click **Save** or press Enter
7. **WAIT 2-3 MINUTES** for container to restart

**STEP 3: Verify**

1. Open bot in Telegram
2. Send `/start`
3. Click "🎓 Учиться"
4. Click any lesson
5. Should see REAL lesson content (not "offline mode")

---

## 🔬 Why Previous Attempts Failed

### Attempt 1: Code Changes
✅ Code was fixed (v0.35.0 - v0.35.3)
✅ Pushed to GitHub
✅ But Railway container wasn't updated OR environment variable still missing

### Attempt 2: Troubleshooting Docs
✅ Documented the problem thoroughly
✅ But didn't explicitly state: "You must set `API_URL` in Railway"
❌ User didn't know exactly which variable to set

### Attempt 3: Multiple Fixes
✅ Fixed hardcoded URLs in bot.py
✅ Fixed variable names in teacher.py
✅ Added better logging
❌ But forgot to verify: Is `API_URL` actually set in Railway?

---

## 📋 Checklist to Fix NOW

- [ ] Go to Railway Dashboard
- [ ] Find RVX API service
- [ ] Find its Public URL (copy it)
- [ ] Go to RVX Bot service
- [ ] Go to Variables tab
- [ ] Add new variable: `API_URL = <your-api-url>`
- [ ] Wait 2-3 minutes
- [ ] Test in Telegram
- [ ] See real lessons (not fallback)

---

## 🚨 What Will Happen After Fix

**Bot logs will show:**
```
🔗 Using TEACH_API_URL: https://rvx-api.railway.app/teach_lesson
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=https://rvx-api.railway.app
✅ Получен урок: 1500+ символов
✅ Урок готов: 🌱 Основы криптографии и блокчейна
```

**Instead of:**
```
🔗 Using TEACH_API_URL: http://localhost:8080/teach_lesson
🔗 Environment: RAILWAY_ENVIRONMENT=production, API_URL=None
❌ Connection error при запросе к http://localhost:8080/teach_lesson
⚠️ Используется fallback урок
```

---

## 🔐 Why This Approach is Correct

1. **Scalable**: Works with any number of containers
2. **Secure**: Uses public HTTPS URL
3. **Simple**: Single environment variable
4. **Standard**: Industry-standard practice
5. **Documented**: Clear priority system

---

## 📚 Version History

| Version | Issue | Fix |
|---------|-------|-----|
| v0.34.0 | API connectivity | Added fallback teaching |
| v0.35.0 | datetime deprecation | Fixed warnings |
| v0.35.1 | Variable name typo | Fixed TEACH_API_URL |
| v0.35.2 | Poor debugging | Added better logging |
| v0.35.3 | Hardcoded localhost | Added env var routing |
| **NOW** | **User action needed** | **Set API_URL in Railway** |

---

## 💡 Key Insight

**The code is correct.** ✅  
**The infrastructure supports it.** ✅  
**The only missing piece: One environment variable.** ⏳

Setting `API_URL` in Railway will immediately fix the teaching feature. No code changes needed.

---

## 🎯 Next Step

**DO THIS NOW:**

1. Open your Railway Dashboard
2. Navigate to Bot Service → Variables
3. Set: `API_URL=https://rvx-api.railway.app`
4. Wait 3 minutes
5. Test `/teach` in Telegram

That's it. Teaching will work. 🎓

---

**TL;DR:** 
- Code is fixed ✅
- Environment variable is not set ❌
- Set `API_URL` in Railway bot service Variables
- Done 🎉
