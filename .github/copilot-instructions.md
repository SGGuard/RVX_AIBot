**Repo Overview**
- **Service Boundaries**: This project has two main runtime components: the FastAPI backend (`api_server.py`) which performs AI analysis using Google Gemini (`google.genai` client), and the Telegram bot (`bot.py` / `main.py`) which handles user interaction and persists data in SQLite (`rvx_bot.db`). The backend exposes `/explain_news` and `/health` and serves OpenAPI docs at `/docs`.

**How to run (developer)**
- **Local dev (manual)**: run the API and the bot in separate terminals: `python api_server.py` and `python bot.py` (or `python main.py` for older entrypoint).
- **Key env**: use `.env` with `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `API_URL_NEWS`, `GEMINI_MODEL`, `GEMINI_TIMEOUT`, `PORT`, `CACHE_ENABLED`.

**Key integrations & external deps**
- **Gemini AI**: `google.genai.Client` is created during FastAPI lifespan in `api_server.py`. The code expects `GEMINI_API_KEY` in environment.
- **Telegram**: Uses `python-telegram-bot` library (`Application`, handlers) in `bot.py` and `main.py`.
- **HTTP client**: `httpx.AsyncClient` for bot -> backend calls.
- **Persistence**: SQLite (`rvx_bot.db`) with schema and migration logic in `bot.py` (`init_database`, `migrate_database`). The API keeps a simple in-memory cache plus an LRU eviction.

**Important patterns and conventions (copy-paste friendly)**
- **Strict AI output format**: The system prompt (see `build_gemini_config()` in `api_server.py`) instructs Gemini to reply ONLY with JSON wrapped in `<json>...</json>` and has a required structure: `{"summary_text": "...", "impact_points": ["...","..."]}`. Agent code extracts JSON via `extract_json_from_response()` and performs `validate_analysis()` — preserve these behaviors when updating prompts or parsers.
- **Prompt injection defense**: Sanitize user input with `sanitize_input()` in `api_server.py`. When changing input handling, keep the existing dangerous-pattern filters.
- **Caching strategy differences**: API: in-memory `response_cache` keyed by SHA-256 (`hash_text()`), evicted when >100 entries. Bot: persistent DB cache table with `hit_count` and `last_used_at`. If you change caching, update both components accordingly.
- **Retry & fallback**: API calls to Gemini use `tenacity` retry + exponential backoff (`call_gemini_with_retry`). On repeated failure the code uses `fallback_analysis()` and increments `request_counter['fallback']`. Keep retry semantics and fallback messaging if tuning timeouts or backoff.
- **Error contract**: All API responses returned to the bot include `simplified_text` (string). Handlers expect this key; altering the API response shape requires updates in `bot.py`'s `validate_api_response()` and `main.py`'s validator.

**Developer workflows & commands**
- Install deps: `pip install -r requirements.txt` (repo expects Python 3.10+).
- Run unit tests (if added): `pytest tests/ -v` per README.
- Health check: `curl http://localhost:8000/health` (fast way to confirm Gemini availability and cache stats).

**Where to make common changes**
- Update Gemini prompt/constraints: `build_gemini_config()` in `api_server.py` and ensure `extract_json_from_response()` remains compatible.
- Add DB column / change schema: update `init_database()` and `migrate_database()` in `bot.py` (migrations are applied at bot startup).
- Logging & monitoring: `logging` configured at module top; follow existing structured logging style (emoji + messages) for consistency.

**Small guidelines for AI agents editing this repo**
- Preserve the strict JSON response contract between API and bot. If you add fields, keep backward-compatible names and update `validate_api_response()` and `validate_analysis()`.
- When modifying prompts, include example responses in the prompt (the project relies on robust parsing heuristics). Keep `<json>` wrapping instructions.
- Avoid switching the caching key algorithm silently — both API and bot depend on hashes (`hash_text()` and `get_cache_key()`). If changing, update both places and migrate DB cache if needed.
- Respect env-driven config: prefer adding toggles via `.env` variables rather than hardcoding constants.
- Tests: add small focused tests under `tests/` that validate JSON parsing (`extract_json_from_response`), validation (`validate_analysis`), and end-to-end bot->API call with a mocked genai client.

**Quick examples**
- Curl analyze: `curl -X POST http://localhost:8000/explain_news -H 'Content-Type: application/json' -d '{"text_content":"Bitcoin ETF одобрен..."}'`
- Health: `curl http://localhost:8000/health`

If anything here is unclear or you want more detail (deploy, CI, or adding test harnesses), tell me which area to expand. 