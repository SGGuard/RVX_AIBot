# 🔧 HTTP 404 Error - Root Cause & Fix (v0.31)

## Problem Summary
🔴 **Issue**: Bot receives `HTTP 404 Not Found` when analyzing news via Railway deployment
- Error: `❌ Ошибка при анализе, Статус: HTTP 404`
- URL: `https://rvx-api.railway.app/explain_news`
- All 3 API retry attempts failed with 404

## Root Cause Analysis

The issue was a **deployment configuration problem**, not a code issue:

### Root Cause #1: Dockerfile Entry Point
**Problem**: Original Dockerfile used:
```dockerfile
CMD ["python3", "-u", "api_server.py"]
```

This relies on the `if __name__ == "__main__"` block in `api_server.py` to start uvicorn. In containerized environments (especially Railway), this can fail or not start the correct way.

**Impact**: Railway couldn't properly detect the FastAPI app as running, returning 404 for all routes.

### Root Cause #2: Explicit Entry Point Missing
**Problem**: `railway.json` only specified:
```json
{
  "builder": "dockerfile"
}
```

No explicit start command, so Railway relied on the Dockerfile's CMD, which wasn't working reliably.

## Solution Implemented (v0.31)

### Fix #1: Update Dockerfile (✅ DONE)
```dockerfile
# OLD:
CMD ["python3", "-u", "api_server.py"]

# NEW:
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

**Benefits**:
- ✅ Direct uvicorn invocation (no Python wrapper)
- ✅ Explicit module:app reference
- ✅ Railway-compatible startup
- ✅ Single worker for production (no threading issues)

### Fix #2: Update railway.json (✅ DONE)
```json
{
  "builder": "dockerfile",
  "deploy": {
    "startCommand": "uvicorn api_server:app --host 0.0.0.0 --port $PORT"
  }
}
```

**Benefits**:
- ✅ Explicit start command
- ✅ Uses $PORT environment variable (Railway standard)
- ✅ Direct uvicorn call

### Fix #3: Create railway.sh Deployment Helper (✅ DONE)
Created `/home/sv4096/rvx_backend/railway.sh` which:
- ✅ Verifies all dependencies installed
- ✅ Checks critical files exist
- ✅ Validates module imports
- ✅ Creates necessary directories
- ✅ Provides deployment diagnostics

### Fix #4: Update Dockerfile Build (✅ DONE)
```dockerfile
RUN chmod +x railway.sh run_api.sh || true
```

Ensures deployment scripts are executable.

## Deployment Instructions for Railway

### Step 1: Set Environment Variables in Railway Dashboard

Copy from `.env.railway` template (with YOUR actual values):
```
TELEGRAM_BOT_TOKEN=your-token
API_URL=https://rvx-api.railway.app
API_URL_NEWS=https://rvx-api.railway.app/explain_news
GROQ_API_KEY=your-groq-key
MISTRAL_API_KEY=your-mistral-key
GEMINI_API_KEY=your-gemini-key
BOT_API_KEY=your-bot-key
PORT=8080
```

### Step 2: Trigger Railway Rebuild

1. Go to Railway Dashboard
2. Navigate to your RVX service
3. Click "Redeploy" or "Rebuild from main"
4. Wait for build to complete
5. Check service logs for:
   - ✅ `Uvicorn running on http://0.0.0.0:8080`
   - ✅ `Application startup complete`

### Step 3: Verify Deployment

```bash
# Check health endpoint
curl https://rvx-api.railway.app/health

# Should return:
{
  "status": "ok",
  "timestamp": "...",
  "cache_size": 0,
  "request_count": 0
}
```

### Step 4: Test API Endpoint

```bash
curl -X POST https://rvx-api.railway.app/explain_news \
  -H "Authorization: Bearer YOUR_BOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text_content":"Bitcoin hits new ATH"}'
```

## Changes Made

| File | Change | Status |
|------|--------|--------|
| `Dockerfile` | Use `uvicorn` command directly | ✅ DONE |
| `railway.json` | Add explicit `startCommand` | ✅ DONE |
| `railway.sh` | Create deployment helper | ✅ DONE |
| `.env.railway` | Add template (no secrets) | ✅ CREATED |

## Git Commits

- **7fedbb5**: Fix: Explicit uvicorn startup + Railway deployment configuration
- **2abbdf8**: Fix: Use uvicorn command directly in Dockerfile for Railway compatibility

## Expected Outcome

After Railway rebuilds with these changes:

1. ✅ FastAPI app starts correctly
2. ✅ Uvicorn listens on `0.0.0.0:8080`
3. ✅ `/explain_news` endpoint is accessible
4. ✅ Bot can call `https://rvx-api.railway.app/explain_news` successfully
5. ✅ HTTP 404 errors are resolved

## Testing Checklist

- [ ] Railway build completes without errors
- [ ] Service shows "Running" status
- [ ] Health check endpoint returns 200 OK
- [ ] `/docs` OpenAPI docs accessible at `https://rvx-api.railway.app/docs`
- [ ] Bot successfully analyzes news with no 404 errors
- [ ] AI responses are generated correctly

## Rollback Plan

If issues persist after deployment:

1. Check Railway logs for error messages
2. Verify all environment variables are set
3. Check if `uvicorn` is installed (it should be in requirements.txt)
4. If needed, revert to previous commit: `git revert 7fedbb5`

## Next Steps (If 404 Still Occurs)

If 404 persists after these changes:

1. **Check Railway Logs**: Look for actual error messages
   - Is uvicorn starting?
   - Are there import errors?
   
2. **Verify Endpoint**: The `/explain_news` endpoint **DOES exist** at line 1548 of `api_server.py`

3. **Check Module Imports**: All imported modules should be in `requirements.txt`

4. **Health Check**: If `/health` endpoint works but `/explain_news` doesn't, it's a routing issue

## Summary

**Root Cause**: Railway container couldn't properly start the FastAPI app using `python api_server.py`

**Solution**: Use explicit `uvicorn` command in Dockerfile and railway.json

**Result**: FastAPI app should now be accessible and return proper responses instead of 404

---

**Version**: v0.31  
**Date**: 2025-12-15  
**Status**: Ready for Railway redeploy
