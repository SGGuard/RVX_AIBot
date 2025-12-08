# 🤖 GitHub Actions CI/CD Workflows

Automated testing and quality checks for RVX Backend.

## Workflows

### 1. **python-tests.yml** - Full Test Suite
**Trigger:** Push to main/develop, Pull Requests

**What it does:**
- ✅ Runs pytest across Python 3.10, 3.11, 3.12
- ✅ Code quality checks (black, flake8, mypy)
- ✅ Import verification (groq, mistralai, fastapi, telegram)
- ✅ Critical files verification
- ✅ Security scan (bandit, safety)

**Status Badge:**
```
![Tests](https://github.com/SGGuard/RVX_AIBot/actions/workflows/python-tests.yml/badge.svg)
```

### 2. **quick-check.yml** - Quick Health Check
**Trigger:** Every push and PR (faster feedback)

**What it does:**
- ✅ Syntax validation
- ✅ Import checks (fast way to catch import errors)
- ✅ File structure verification
- ✅ Code metrics (lines of code per file)
- ✅ Dependency availability check

---

## 📊 Current Status

| Workflow | Status | Purpose |
|----------|--------|---------|
| quick-check | 🟢 Active | Fast feedback on every commit |
| python-tests | 🟢 Active | Deep testing & quality checks |

---

## ✅ Requirements for Passing

### python-tests.yml
- Python syntax valid
- All imports work
- pytest passes (or skipped if no tests)
- Required dependencies in requirements.txt:
  - `fastapi`
  - `python-telegram-bot`
  - `httpx`
  - `groq` ⭐ **CRITICAL** (added in v0.25)
  - `mistralai` ⭐ **CRITICAL** (added in v0.25)
  - `google-genai`

### quick-check.yml
- No syntax errors
- All critical imports available
- All required files exist
- Code metrics reported

---

## 🚀 Using Locally

Before pushing, run locally:

```bash
# Quick syntax check
python -m py_compile bot.py api_server.py ai_dialogue.py

# Import check
python -c "import groq; import mistralai; import fastapi; import telegram; print('✅ OK')"

# Run tests (if available)
pytest tests/ -v

# Check formatting
black --check *.py

# Run linter
flake8 *.py --max-line-length=120
```

---

## 📝 What Changed (v0.25)

**Added workflows for:**
- ✅ Automated testing on every push/PR
- ✅ Python version compatibility check (3.10, 3.11, 3.12)
- ✅ Critical dependency verification (groq, mistralai)
- ✅ Fast health checks (quick-check.yml)

**This prevents:**
- ❌ Missing dependencies on deployment
- ❌ Syntax errors reaching production
- ❌ Import failures
- ❌ Regressions

---

## 🔗 View Results

1. Go to **Actions** tab on GitHub
2. Select workflow
3. Click latest run
4. See detailed logs

---

## 🆘 Troubleshooting

**Workflow failing?**

1. Check **Logs** tab in GitHub Actions
2. Look for which step failed
3. Run that command locally to debug
4. Push fix and re-run

**Common issues:**

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: groq` | Add `groq==0.9.0` to requirements.txt |
| `ModuleNotFoundError: mistralai` | Add `mistralai==0.4.2` to requirements.txt |
| Python syntax error | Run `python -m py_compile <file.py>` locally |
| Import error | Run `python -c "import module_name"` to debug |

---

## 📚 References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [pytest Documentation](https://docs.pytest.org/)
- [flake8 Documentation](https://flake8.pycqa.org/)
- [mypy Documentation](https://mypy.readthedocs.io/)

---

**Last Updated:** 8 декабря 2025 (v0.25)
