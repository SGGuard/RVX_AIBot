# 🚆 Railway Deployment Guide - Fix Multiple Containers

## Problem: Multiple Containers Starting

From logs, Railway is still spawning multiple containers:
```
19:04:24 - Starting Container (OK)
19:04:29 - Starting Container (NEW - causes api_server error)
19:04:32 - Stopping Container
19:05:41 - Starting Container (ANOTHER NEW!)
```

This suggests Railway is not respecting the dockerfile configuration.

## Solution: Railway Dashboard Configuration

### Step 1: Clear Build Cache
1. Go to **Railway Dashboard** → Your Project
2. Click on **Settings** (bottom left)
3. Look for **"Clear Build Cache"** button
4. Click it

### Step 2: Force Rebuild
1. Go back to **Deployments** tab
2. Find the latest deployment
3. Click **"Redeploy"** button OR
4. Push a new commit to `main` branch to trigger automatic rebuild

### Step 3: Verify Configuration in Dashboard

**Settings** → **Build**:
- Should see: `Dockerfile: railway.dockerfile`
- Should see: Build command (probably empty - OK)

**Settings** → **Deploy**:
- Start command should be: `python bot.py` (from CMD in Dockerfile)

**Services** tab:
- Should show only ONE service running
- NOT showing "web" and "worker" separately

### Step 4: Confirm Procfile is Gone

Railway should have picked up the deletion:
```bash
git log --oneline Procfile  # Should show "delete" in latest commit
```

If Procfile still exists on Railway's side:
1. Open **Railway Dashboard**
2. Go to **Source** tab
3. Verify that Procfile is deleted in the repo

## File Structure (Should Be)

```
/app/
├── Dockerfile                    # Main dockerfile (minimal)
├── railway.dockerfile            # Explicit for Railway (bot only)
├── railway.json                  # Points to railway.dockerfile
├── bot.py                        # ✅ RUNS
├── api_server.py                 # ❌ DOES NOT RUN (guard check)
├── Procfile                      # ❌ DELETED (no longer exists)
└── ...
```

## Expected Behavior After Fix

1. Railway starts ONE container only
2. Logs show:
   ```
   🔧 CLEANUP: Current PID = 1
   🚀 Starting polling...
   🚀 БОТ ПОЛНОСТЬЮ ЗАПУЩЕН И ГОТОВ К РАБОТЕ
   ```
3. NO `api_server` errors
4. NO multiple "Starting Container" messages
5. `/test_digest` command works for user ID 7216426044

## Debugging: Check What Railway is Running

If problems persist, check Railway logs for:
- Search for "Starting Container" count (should be 1, then maybe restart 1 time)
- Search for "ERROR" or "Conflict" (should be none)
- Search for "api_server" (should NOT appear)

## Manual Fix (Last Resort)

If Railway still uses multiple services:

1. **Delete the Railway app** and create new one
2. **Connect to GitHub repo** (with Procfile deleted)
3. **Set build command**: Leave empty
4. **Set start command**: `python bot.py`

## Commits Related

- `2a21e00` - DELETE Procfile completely
- `aabedc2` - Use psutil instead of shell commands
- `e9714e8` - Fix admin access control

---

**Status**: Waiting for Railway rebuild
**Next**: Monitor logs after Railway picks up changes
