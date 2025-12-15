# Deployment Migration: Vercel → Railway

**Status:** ✅ COMPLETE

## Summary

Проект успешно мигрирован с Vercel на Railway. Все Vercel конфигурации удалены, и теперь проект полностью оптимизирован для Railway.

## What Was Removed

### Vercel Files (Deleted)
- `vercel.json` - Vercel configuration
- `.vercel/` - Vercel build cache
- `.vercelignore` - Vercel ignore rules

### Vercel References (Cleaned)
- Git commits with Vercel setup removed from main branch
- Documentation updated to remove Vercel deployment instructions

## What Was Kept

### Railway-Compatible Setup ✅

```
├── Dockerfile                  # Multi-stage Docker build (Railway)
├── Procfile                    # Service definitions (web + worker)
├── docker-compose.yml          # Local development environment
├── requirements.txt            # Python dependencies
└── .env.example               # Environment template
```

### Configuration Files
- `Procfile`: Defines two services:
  - `web: python api_server.py` (FastAPI)
  - `worker: python bot.py` (Telegram Bot)

- `Dockerfile`: Production-ready multi-stage build
  - Stage 1: Builder (installs dependencies)
  - Stage 2: Runtime (minimal image with installed packages)
  - Health check configured
  - Railway-compatible CMD

### Git Safety
- `.gitignore` includes Vercel entries as safety measure
- If Vercel files accidentally created, they won't be committed

## Current Deployment Flow

```
GitHub (main branch)
    ↓
Railway (auto-deploy on push)
    ↓
Docker build (using Dockerfile)
    ↓
Services start (Procfile)
    ├─ web service (API: port 8000)
    └─ worker service (Bot: polling)
```

## Verification Results

✅ No Vercel config files in root  
✅ No Vercel references in code  
✅ Railway compatibility verified  
✅ All deployment files present  
✅ Git history cleaned  

## How to Deploy

```bash
# Simply push to main branch
git push origin main

# Railway will:
# 1. Detect changes
# 2. Run git pull
# 3. Build Docker image from Dockerfile
# 4. Execute Procfile services
# 5. Start health checks
```

## Environment Variables Required on Railway

```
TELEGRAM_BOT_TOKEN          # Telegram Bot API token
GEMINI_API_KEY              # Google Gemini API key
GEMINI_MODEL                # Model name (default: models/gemini-2.5-flash)
GROQ_API_KEY                # Groq API key (backup)
MISTRAL_API_KEY             # Mistral API key (backup)
PORT                        # Port for API (default: 8000)
```

## Rollback Plan

If needed to return to Vercel:
1. Create feature branch: `git checkout -b feature/vercel-restore`
2. Cherry-pick Vercel commits from git history
3. Test locally with docker-compose
4. Push to Vercel via their CLI

But it's not recommended - Railway is more stable for this project!

## Benefits of Migration

- ✅ Better support for background workers (Procfile)
- ✅ Simpler configuration (no build vs. runtime separation issues)
- ✅ Native WebSocket support
- ✅ Easier environment variable management
- ✅ Better cost-effectiveness
- ✅ No cold start issues

---

**Migration completed:** 15 December 2025  
**Verified by:** Cleanup verification script  
**Platform:** Railway only 🚀
