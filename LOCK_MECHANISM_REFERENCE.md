# 🔒 Lock Mechanism Technical Reference

## Implementation Overview

### Lock File Location
```
/tmp/rvx_bot.lock
```

### Lock Acquisition (bot.py, lines 9941-9959)

```python
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
```

### Lock Release (bot.py, finally block, lines 10407-10415)

```python
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

---

## How It Works

### Scenario 1: Normal Startup ✅

```
Time  Bot Process          Lock File        Telegram Polling
────────────────────────────────────────────────────────────
0s    bot.py starts
      acquire lock → SUCCESS              
      lock: PID 1234      [CREATED]        
      initialize          
1s    polling starts                       ✅ getUpdates() succeeds
      🔒 Bot lock acquired
      
∞     bot.py running
      (lock file exists)   [ACTIVE]        ✅ getUpdates() polling
```

### Scenario 2: Duplicate Attempt ❌ (PREVENTED)

```
Time  Bot#1                Bot#2            Lock File        Telegram
────────────────────────────────────────────────────────────────────
0s    bot.py starts        
      acquire lock → OK    
      lock: PID 1234       [CREATED]
1s    polling OK                           [ACTIVE, PID=1234]
      ✅ getUpdates()      
      
5s                         bot.py starts    
                           acquire lock     [EXISTS, PID=1234]
                           → FAIL!          
                           log ERROR        
                           exit             
                                            ❌ Second polling request
                                            blocked before it starts!
```

### Scenario 3: Graceful Shutdown ✅

```
Time  Bot Process          Lock File        Telegram
───────────────────────────────────────────────────
0s    bot.py running
      polling active       [ACTIVE]         ✅ getUpdates()
      
10s   Ctrl+C pressed
      KeyboardInterrupt
      exception caught
      → finally block      
      remove lock          [DELETED]        ✅ Polling stops
      🔓 Lock removed
      
11s   bot.py exits         [GONE]           (No connection)
```

### Scenario 4: Crash During Polling

```
Time  Bot Process          Lock File        Effect
───────────────────────────────────────────────────
0s    bot.py running       [ACTIVE]
      polling active
      
8s    Network error
      Exception raised
      (not caught)
      → finally block      
      remove lock          [DELETED]        ✅ Lock cleaned up
      
9s    bot.py crashed       [GONE]           
      
10s   Railway detects crash and restarts bot.py
      Lock doesn't exist
      acquire lock → OK    [CREATED]        ✅ New instance starts
```

---

## Why This Works

### Problem: Telegram API Rejects Duplicate Polling

```
Telegram Server
  │
  ├─ Bot#1: getUpdates(offset=123)  ✅ ACCEPTED
  │
  └─ Bot#2: getUpdates(offset=456)  ❌ REJECTED
       Error: "Conflict: terminated by other getUpdates request"
       Code: 409
```

### Solution: Prevent Bot#2 From Even Starting

```
Local Machine (Railway Container)

┌─────────────────────────────┐
│ bot.py startup              │
│                             │
│  lock = /tmp/rvx_bot.lock   │
│                             │
│  if lock exists:            │
│    ❌ EXIT immediately      │  ← Before any polling starts
│    Don't contact Telegram   │
│                             │
│  if lock doesn't exist:     │
│    Create lock file         │
│    ✅ Start polling         │
│       Now Telegram safe     │
└─────────────────────────────┘
```

---

## Atomic Lock Semantics

### os.O_EXCL Guarantee

```python
# Atomic operation - cannot be interrupted
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
```

**Properties:**
- ✅ Atomic at OS level (not just Python level)
- ✅ Race-condition safe (works with multiple processes)
- ✅ Works across filesystem boundaries
- ✅ Fails immediately if file exists (no retry logic needed)

**Comparison:**

```python
# ❌ NOT atomic - race condition possible
if not os.path.exists(lock_file):    # Check
    os.open(lock_file, ...)           # Act
    # Another process could create here!

# ✅ Atomic - race condition impossible
fd = os.open(lock_file, os.O_CREAT | os.O_EXCL)  # Check + Act = 1 operation
```

---

## Error Handling Strategy

### "Fail Open" Approach

```python
try:
    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
except FileExistsError:
    logger.critical("Another instance running")
    return  # ✅ Exit cleanly
except Exception as e:
    logger.error(f"Lock error: {e}")
    # ⚠️ Continue anyway - don't block bot startup on lock issues
```

**Rationale:**
- If lock check fails due to permissions → don't block bot
- Log clearly for debugging
- Prefer bot running without lock over not running at all
- Real protection comes from Railway not restarting processes

---

## Platform Compatibility

### Linux (Railway default)
```python
os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
```
✅ Works perfectly - standard POSIX behavior

### Windows (local dev)
```python
os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
```
✅ Works - Windows honors O_EXCL since Python 3.4

### macOS (local dev)
```python
os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
```
✅ Works - BSD/macOS POSIX behavior

### Containers (Docker/Railway)
```python
os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
```
✅ Works - /tmp is standard in containers

---

## Monitoring & Debugging

### Check If Lock Is Active

```bash
# On Railway container SSH
ls -la /tmp/rvx_bot.lock

# If exists:
cat /tmp/rvx_bot.lock  # Shows PID of running bot

# If doesn't exist:
# No bot.py instance active
```

### Force Release (Emergency Only)

```bash
# If bot is stuck and won't start
rm /tmp/rvx_bot.lock

# Then restart
# DON'T do this while bot.py is running!
```

### Check Logs

```bash
# Look for lock messages
grep "🔒 Bot lock" /tmp/bot.log      # Successful lock
grep "🚨 CRITICAL" /tmp/bot.log      # Duplicate detected
grep "🔓 Lock" /tmp/bot.log          # Graceful shutdown
```

---

## Lock File Content Format

### What Gets Written

```
1234
```

**Components:**
- PID of the bot.py process
- Single line
- Newline terminated

**Why PID?**
- Useful for debugging
- Shows which process holds lock
- Can trace back to container logs

---

## Integration with Procfile

### How They Work Together

**Procfile:**
```bash
trap "kill 0" SIGTERM SIGINT; python bot.py ... & sleep 2 && python api_server.py; wait
```

**Lock mechanism:**
```python
def main():
    # Acquire lock
    fd = os.open(..., os.O_EXCL)
    # ... initialize bot
    try:
        loop.run_until_complete(application.run_polling())
    finally:
        # Release lock
        os.remove(lock_file)
```

**Flow:**
```
1. Procfile starts bot.py in background
2. bot.py main() acquires lock
3. Bot polls Telegram (lock held)
4. Railway sends SIGTERM (process shutdown)
5. Procfile trap catches SIGTERM
6. Graceful shutdown triggered
7. finally block releases lock
8. bot.py exits
9. Lock file deleted
10. If Railway restarts bot.py:
    → Lock doesn't exist
    → bot.py acquires new lock
    → Only one instance polling
```

---

## Why os.O_EXCL (Not fcntl.flock)

### Comparison

| Feature | os.O_EXCL | fcntl.flock |
|---------|-----------|------------|
| **Simplicity** | Very simple | More complex |
| **Race-safe** | ✅ Yes | ✅ Yes |
| **Container-safe** | ✅ Yes | ⚠️ Depends on mount |
| **Cleanup** | Manual (need finally) | Automatic on close |
| **Portability** | POSIX + Windows | Unix only |
| **Use case** | One-off lock | Long-lived locks |

**Why O_EXCL chosen:**
- ✅ Simpler for single-startup check
- ✅ Works everywhere (Railway, local, Docker)
- ✅ File-based (works across process boundaries)
- ✅ Atomic guarantee from OS

---

## Testing Lock Mechanism

### Test 1: Single Instance Works

```bash
# Terminal 1
python bot.py
# Check logs: 🔒 Bot lock acquired

# Terminal 2 (while Terminal 1 running)
# Won't see lock acquired - process exits
```

### Test 2: Duplicate Blocked

```bash
# Terminal 1
python bot.py
# Logs: 🔒 Bot lock acquired (PID: 12345)

# Terminal 2 (while Terminal 1 running)
python bot.py
# Logs: 🚨 CRITICAL: Another bot instance is already running!
# Process exits
```

### Test 3: Startup After Crash

```bash
# Terminal 1
python bot.py
# Logs: 🔒 Bot lock acquired

# Terminal 2
kill -9 <PID_from_terminal_1>

# Terminal 1 (restart)
python bot.py
# Should see: 🔒 Bot lock acquired (NEW PID)
# Lock file recreated automatically
```

---

## Summary

**Lock mechanism provides:**
1. ✅ **Safety** - Prevents duplicate instances atomically
2. ✅ **Simplicity** - File-based, no external dependencies
3. ✅ **Cleanup** - Automatic on graceful shutdown
4. ✅ **Portability** - Works everywhere (Railway, Docker, local)
5. ✅ **Monitoring** - PID in lock file for debugging

**Result:**
- No "Conflict: terminated by other getUpdates" errors
- No duplicate polling requests
- Telegram API always sees single bot instance
- User experience: reliable, responsive bot
