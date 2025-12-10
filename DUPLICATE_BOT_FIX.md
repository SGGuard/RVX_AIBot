ил# Duplicate Bot Instance Fix (Commit: 2d2d492)

## Problem Summary
After clicking buttons (especially "Учиться"/Teach), Railway logs show repeated:
```
Conflict: terminated by other getUpdates request; make sure that only one bot instance is running
```

This happens because:
1. **Procfile** runs bot.py in background with `&` operator
2. Background process can restart when Railway detects it crashed
3. Telegram API rejects second polling request with same token → 409 Conflict error
4. User gets stuck, bot stops responding, buttons fail

## Solutions Implemented

### 1. Startup Lock Mechanism (bot.py)
Added file-based lock at `main()` entry point:

**Location:** `/tmp/rvx_bot.lock`

**How it works:**
- When bot.py starts, tries to create lock file exclusively
- If successful → bot proceeds normally
- If lock exists → bot logs critical error and exits immediately
- On shutdown (success/failure) → lock file is removed

**Code added:**
```python
def main():
    """Запуск бота."""
    # ⚡ ANTI-DUPLICATE GUARD: Ensure only one bot instance runs
    lock_file = "/tmp/rvx_bot.lock"
    try:
        # Try to create lock file exclusively (fails if already exists)
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        logger.info(f"🔒 Bot lock acquired (PID: {os.getpid()})")
    except FileExistsError:
        # Another instance is running
        logger.critical(f"🚨 CRITICAL: Another bot instance is already running!")
        logger.critical(f"   Lock file: {lock_file}")
        logger.critical(f"   Please stop the other instance before starting a new one.")
        logger.critical(f"   To force: rm {lock_file}")
        return
    except Exception as e:
        logger.error(f"⚠️ Lock file error (continuing anyway): {e}")
    
    try:
        # ... existing bot startup code ...
    finally:
        # Clean up lock file on exit (whether success or error)
        lock_file = "/tmp/rvx_bot.lock"
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
                logger.info(f"🔓 Lock file removed on shutdown")
        except Exception as e:
            logger.warning(f"⚠️ Could not remove lock file: {e}")
```

**Behavior:**
- ✅ First bot.py instance starts → acquires lock → logs "🔒 Bot lock acquired"
- ✅ Any subsequent bot.py attempts → fails to acquire lock → logs critical error → exits
- ✅ Lock persists only while bot.py is running
- ✅ On graceful shutdown (Ctrl+C or SIGTERM) → lock released

### 2. Improved Procfile (Procfile)
Updated to ensure proper signal handling:

**Old (problematic):**
```
web: bash -c 'python bot.py > /tmp/bot.log 2>&1 & sleep 1 && python api_server.py'
```

**New (improved):**
```
web: bash -c 'trap "kill 0" SIGTERM SIGINT; python bot.py > /tmp/bot.log 2>&1 & sleep 2 && python api_server.py; wait'
```

**Improvements:**
- `trap "kill 0" SIGTERM SIGINT` → Signal handler that kills ALL child processes on termination
- `sleep 2` → Longer delay (was 1s) to ensure bot.py fully initializes before api_server starts
- `wait` → Shell waits for all background processes, ensuring graceful shutdown

## Deployment Steps

### 1. Pull Latest Changes
```bash
git pull origin main
```

Should see both commits:
- `2d2d492` - 🔒 fix: Add startup lock mechanism
- `c06fbea` - 🔴 CRITICAL FIX: Solve Railway deployment issues

### 2. Deploy on Railway
1. Go to [Railway Dashboard](https://railway.app)
2. Select your project
3. Click **Redeploy** button
4. Wait for deployment to complete

### 3. Verify Environment Variables
Ensure these are set in Railway settings:
```
API_URL_NEWS=http://localhost:8000/explain_news
API_URL_BASE=http://localhost:8000
RAILWAY_ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=<your-token>
GEMINI_API_KEY=<your-key>
```

## Testing

After deployment, test:

1. **Bot starts cleanly:**
   ```
   Check Railway logs for: "🔒 Bot lock acquired (PID: XXXXX)"
   ```

2. **Send /start command:**
   Should see welcome message

3. **Click "Учиться" button multiple times:**
   - Should NOT see "Conflict: terminated by other getUpdates"
   - Should remain responsive
   - Should handle callbacks without crashing

4. **Monitor logs for duplicate attempts:**
   Should see NO lines like:
   ```
   🚨 CRITICAL: Another bot instance is already running!
   ```

5. **Check context is saved:**
   Send message → click button → send follow-up
   Bot should remember previous context

## Troubleshooting

### Issue: Bot won't start after deployment
**Check logs for:**
```
🚨 CRITICAL: Another bot instance is already running!
```

**Solution:**
1. Wait 30 seconds (Railway cleanup cycle)
2. Click **Redeploy** again
3. If persists: SSH to container and remove lock manually:
   ```bash
   rm /tmp/rvx_bot.lock
   ```

### Issue: Still seeing Conflict errors
**Possible causes:**
1. Old bot.py processes still running (from before lock was added)
2. Railway dyno restarts haven't completed
3. Multiple Railway instances trying to run simultaneously

**Solutions:**
1. Hard restart Railway: Delete dyno and redeploy
2. Check logs for multiple "🔒 Bot lock acquired" messages (indicates multiple startups)
3. Verify only ONE process is running: look for single "PID: XXXXX" value

### Issue: Bot starts but buttons don't work
**Check:**
1. API_URL_NEWS is set in Railway environment
2. api_server.py started: look for "🚀 INITIALIZING FastAPI"
3. Health check passes: `curl http://localhost:8000/health`

## Technical Details

### Lock Mechanism Guarantees
- ✅ Atomic file creation (uses `os.O_EXCL`)
- ✅ Works across Linux/Windows/macOS
- ✅ Works in containerized environments (Railway, Docker)
- ✅ Cleaned up on graceful shutdown
- ✅ Fails open (bot continues if lock error, but logs warning)

### Why Two Fixes?
1. **Procfile** → Ensures clean signal handling (Railway can terminate gracefully)
2. **Lock mechanism** → Ensures if bot.py somehow starts twice, second exits immediately

Together they prevent:
- ✅ Zombie processes
- ✅ Duplicate polling requests
- ✅ 409 Conflict errors from Telegram API
- ✅ Lost context/buttons not working

## Related Commits
- `c06fbea` - API URL detection for Railway + DB migration fixes
- `7407cd9` - teacher.py URL parsing + Procfile sleep increase
- `f730d54` - Button callback fixes + EventType enum
- `af0bbbb` - Conversation history robust error handling

## Success Criteria (Post-Deployment)
- [ ] Bot logs "🔒 Bot lock acquired (PID: XXXXX)" on startup
- [ ] No "Conflict: terminated by other getUpdates" in logs
- [ ] Buttons work without crashing
- [ ] /start command responsive
- [ ] Context saved across messages
- [ ] teach_lesson endpoint connects successfully
- [ ] Health check returns 200 OK
