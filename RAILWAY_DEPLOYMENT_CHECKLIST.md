# ✅ Railway Deployment Checklist

## 🔐 PRE-DEPLOYMENT SECURITY CHECKS

### Security Status
- [x] Git история очищена от ключей
- [x] `.env` защищен `.gitignore`
- [x] `.env.example` содержит только плейсхолдеры
- [x] Все ключи переновлены на сервисах
- [x] Dockerfile не содержит ключей
- [x] Procfile готов

### Pre-Push Verification
```bash
# Проверьте перед git push:
git log --all -p | grep -i "gsk_\|AIzaSy\|sk-test\|sk-live" | head -5
# Не должно быть результатов!
```

---

## 📋 DEPLOYMENT CHECKLIST

### Pre-Deployment (Local)
- [ ] Проверен что нет ключей в коде
- [ ] `.env.example` заполнен правильно
- [ ] `requirements.txt` актуален
- [ ] `Procfile` существует
- [ ] `Dockerfile` работает локально
- [ ] `railway.json` конфигурация правильная

### GitHub Repository
- [ ] Все файлы закоммичены
- [ ] История чиста (нет ключей)
- [ ] Push выполнен успешно
- [ ] GitHub действительно содержит:
  - ✅ `Procfile`
  - ✅ `railway.json`
  - ✅ `Dockerfile`
  - ✅ `.env.example`
  - ✅ `requirements.txt`
  - ✅ `RAILWAY_DEPLOYMENT_GUIDE.md`

### Railway Project Setup
- [ ] Создан Railway проект
- [ ] GitHub репозиторий подключен
- [ ] Первый deploy запущен
- [ ] Build завершился успешно
- [ ] Логи показывают успех

### Environment Variables in Railway
- [ ] TELEGRAM_BOT_TOKEN добавлен
- [ ] GROQ_API_KEY добавлен
- [ ] MISTRAL_API_KEY добавлен
- [ ] DEEPSEEK_API_KEY добавлен
- [ ] GEMINI_API_KEY добавлен
- [ ] PORT установлен в 8000
- [ ] ALLOWED_ORIGINS = *
- [ ] Остальные переменные добавлены

### Telegram Webhook Configuration
- [ ] Railway Domain URL скопирован
- [ ] Webhook установлен для Telegram
- [ ] `getWebhookInfo` показывает правильный URL
- [ ] Нет pending updates

### Service Health Checks
- [ ] `/health` endpoint возвращает 200 OK
- [ ] API сервер запущен (Uvicorn logs OK)
- [ ] Telegram бот запущен и получает сообщения
- [ ] Логи не содержат ERROR
- [ ] Оба процесса работают (web + worker)

### Bot Functionality Tests
- [ ] Бот отвечает на `/start`
- [ ] Бот получает сообщения
- [ ] Анализ новостей работает
- [ ] Ответы приходят вовремя (<10 сек)
- [ ] Ошибки обрабатываются корректно
- [ ] БД функционирует правильно

### Monitoring Setup
- [ ] Railway Metrics доступны
- [ ] Логи можно просматривать
- [ ] Нет критических ошибок
- [ ] CPU/Memory использование OK
- [ ] Network metrics OK

---

## 🚀 DEPLOYMENT STEPS

### 1. Prepare Files (DONE ✅)
```bash
# Файлы уже готовы
ls -la Procfile railway.json Dockerfile .env.example
```

### 2. Commit Changes
```bash
git add Procfile railway.json Dockerfile RAILWAY_DEPLOYMENT_GUIDE.md RAILWAY_DEPLOYMENT_CHECKLIST.md
git commit -m "chore: Add Railway deployment configuration and documentation"
git push origin main
```

### 3. Create Railway Project
- Go to https://railway.app/new
- Select "Deploy from GitHub"
- Choose SGGuard/RVX_AIBot
- Click "Deploy Now"

### 4. Wait for Build
- Takes 2-5 minutes
- Check Deployments tab
- Should say "UP" when ready

### 5. Add Environment Variables
- Variables tab
- Add all variables from `.env.example`
- Click Save (triggers redeploy)

### 6. Configure Telegram Webhook
```bash
# Get Railway URL
RAILWAY_URL="https://xxxxx.up.railway.app"

# Set webhook
curl -X POST https://api.telegram.org/botTELEGRAM_TOKEN/setWebhook \
  -d "url=${RAILWAY_URL}/webhook"

# Verify
curl https://api.telegram.org/botTELEGRAM_TOKEN/getWebhookInfo
```

### 7. Verify Deployment
```bash
# Health check
curl https://{RAILWAY_URL}/health

# Should return:
# {"status": "ok", ...}
```

### 8. Test Bot
- Open Telegram
- Send /start to bot
- Should get welcome message

---

## 📊 STATUS INDICATORS

### ✅ GOOD SIGNS
- Railway shows "UP" status
- `/health` returns 200 OK
- Logs show both processes running
- Bot responds to messages
- No ERROR in logs

### ⚠️ WARNING SIGNS
- Railway shows "CRASHED"
- Logs contain ERROR or CRITICAL
- Bot doesn't respond
- API returns 500 errors
- High memory usage (>500MB)

### ❌ BLOCKING ISSUES
- `/health` returns 500
- Both processes stopped
- Telegram not receiving updates
- Database locked
- Build failed

---

## 🔄 ROLLBACK PROCEDURE

If something goes wrong:

1. **Immediate (Stop bleeding):**
   ```bash
   # Redeploy from known good commit
   git log --oneline | head -5
   git reset --hard <good_commit>
   git push --force origin main
   # Railway will redeploy automatically
   ```

2. **Check what went wrong:**
   - Railway Logs → look for errors
   - Local test with Docker
   - Check environment variables

3. **Fix and redeploy:**
   ```bash
   # Fix issue
   git commit -am "fix: issue description"
   git push origin main
   # Railway redeploys automatically
   ```

---

## 📞 SUPPORT & RESOURCES

### Documentation
- [Railway Docs](https://docs.railway.app/)
- [Python-Telegram-Bot](https://python-telegram-bot.org/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Procfile Reference](https://devcenter.heroku.com/articles/procfile)

### Debugging Commands
```bash
# Check Railway logs
railway logs

# Check if port is open
curl -I https://{RAILWAY_URL}

# Test bot locally with Railway env
python bot.py  # with RAILWAY=1

# Validate Python syntax
python -m py_compile *.py
```

### Common Issues & Fixes
See `RAILWAY_DEPLOYMENT_GUIDE.md` for detailed troubleshooting.

---

## ✨ SUCCESS METRICS

Once deployed successfully:

| Metric | Target | How to Check |
|--------|--------|-------------|
| API Health | 200 OK | `curl /health` |
| Bot Response | <10s | Send test message |
| Errors | 0 in logs | Railway Logs tab |
| Memory Usage | <300MB | Railway Metrics |
| Build Time | <5min | Deployments tab |
| Uptime | 99%+ | Railway Metrics |

---

## 📋 SIGN OFF

When everything is working:

```
Date: __________
Tester: __________
Status: PASSED / FAILED

Notes:
_____________________________________________________________________________
_____________________________________________________________________________
```

---

**Created:** 2025-12-10  
**For:** Railway.app Staging Deployment  
**Status:** Ready to Deploy ✅
