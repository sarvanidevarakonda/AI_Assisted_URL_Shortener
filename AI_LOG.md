# AI Assistance Log

**Project:** AI-Assisted URL Shortener Service  
**Candidate:** Sarvani Devarakonda  
**AI Tool:** GitHub Copilot (Agent Mode)  
**Date Started:** 2026-09-13

---

## Purpose

This log documents how GitHub Copilot was used across the project: the prompts
issued, the outputs generated, my review of each output, and how correctness
was validated. It serves as evidence of AI-assisted engineering under full
human ownership.

---

## Workflow Summary

For each component:
1. Wrote a specific prompt in Copilot Agent Mode.
2. Reviewed Copilot's output against engineering standards.
3. Accepted, modified, or rejected the output.
4. Validated via import check and/or tests.
5. Logged the result below.

---

## Component: `.github/copilot-instructions.md`

**Prompt used:** N/A — authored directly.

**Purpose:** Provides project context to Copilot (tech stack, standards, rules).

**My review:** Confirmed rules align with assignment requirements
(cryptographic randomness, test coverage, edge cases).

**Validation:** N/A (configuration only).

---

## Component: `database.py`

**Prompt used:**
> "Create a file called database.py for SQLAlchemy with SQLite.
> It should:
> - Create an engine connected to 'sqlite:///./shortener.db'
> - Set connect_args={'check_same_thread': False}
> - Create a SessionLocal sessionmaker
> - Define a Base class
> - Provide a get_db() dependency function that yields a session"

**Copilot output summary:**
- Generated engine, SessionLocal, Base, and get_db() as requested.
- Used `declarative_base()` from `sqlalchemy.ext.declarative`.

**My review and changes:**
- Verified `check_same_thread=False` is set (required for SQLite + FastAPI).
- Verified `get_db()` uses try/finally to close sessions.
- No functional changes needed at first.
- Later extended with a Redis client (see "Redis Caching Layer" below).

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import database"`): initially FAILED —
  SQLAlchemy not installed.
- Resolution: ran `pip install sqlalchemy`, re-ran import → PASS.
- Updated `requirements.txt` to reflect new dependency.
- Tests: N/A (no logic yet)

---

## Component: `models.py`

**Prompt used:**
> "Create a file called models.py with a SQLAlchemy model called URLMapping.
> Import Base from database.
> Columns:
> - id: Integer, primary key
> - original_url: String, not null
> - short_code: String, unique, indexed
> - created_at: DateTime, default=datetime.utcnow
> - click_count: Integer, default=0
> Add a __repr__ method for debugging."

**Copilot output summary:**
- Generated the URLMapping class with all requested columns and __repr__.
- Used `datetime.utcnow` as the default for `created_at`.
- `short_code` had `unique=True` and `index=True` but not `nullable=False`.
- Left a stray `created_at = Column(...)` line at the top of the file, outside any class.

**My review and changes:**
- Removed the stray top-level `created_at` line (would raise NameError on import).
- Added `from datetime import datetime, timezone` — missing from Copilot's output.
- Replaced deprecated `datetime.utcnow` with `datetime.now(timezone.utc)`.
- Added `nullable=False` to `short_code` (a short code must always exist).

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import models"`): PASS
- Introspection check: `URLMapping.short_code.unique=True`, `index=True`, `nullable=False`
- Tests: N/A (model only; exercised via test_main.py)

---

## Component: `schemas.py`

**Prompt used:**
> "Create a file called schemas.py with Pydantic models for the URL shortener.
> Use Pydantic v2 syntax.
>
> Models needed:
> 1. URLRequest:
>    - original_url: str
>    - A field_validator that ensures the URL starts with 'http://' or 'https://'
>    - If invalid, raise ValueError with a clear message
> 2. URLResponse:
>    - short_code: str
>    - short_url: str
>    - original_url: str
> 3. AnalyticsResponse:
>    - original_url: str
>    - short_code: str
>    - click_count: int
>    - created_at: datetime
>
> Use model_config = ConfigDict(from_attributes=True) where appropriate
> so Pydantic can read from SQLAlchemy objects."

**Copilot output summary:**
- Generated URLRequest, URLResponse, AnalyticsResponse with Pydantic v2 syntax.
- URLRequest includes a field_validator for http:// and https://.
- Response models use ConfigDict(from_attributes=True).

**My review and changes:**
- Verified Pydantic v2 imports (`field_validator`, `ConfigDict`), no v1 `@validator`.
- Validator correctly rejects strings not starting with http:// or https://.
- No functional changes needed.

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import schemas"`): PASS
- Valid URL (`https://example.com`): PASS — model constructed
- Invalid URL (`notaurl`): PASS — raised ValidationError with custom message

**Note on Copilot limitation:**
- Copilot Agent Mode reported "Pydantic not installed" during its own
  runtime check, but `pip show pydantic` confirmed v2.13.5 was installed
  in the active venv. Copilot's terminal context does not always inherit
  the venv, so its runtime claims are not authoritative. Verified manually.

---

## Component: `main.py`

**Prompt used:**
> "Create main.py with a FastAPI app for a URL shortener.
> Imports: from database (engine, Base, get_db), from models (URLMapping),
> from schemas (URLRequest, URLResponse, AnalyticsResponse).
> Setup: app = FastAPI(); Base.metadata.create_all(bind=engine) on startup.
> Endpoints:
> 1. POST /shorten — accept URLRequest; idempotent by original_url;
>    generate 6-char code via secrets; retry up to 3x on IntegrityError;
>    return URLResponse with short_url = 'http://localhost:8000/{code}'.
> 2. GET /{short_code} — 404 if missing; increment click_count;
>    RedirectResponse 307 to original_url.
> 3. GET /analytics/{short_code} — 404 if missing; return AnalyticsResponse.
> Use Depends(get_db) for DB sessions."

**Copilot output summary:**
- Generated FastAPI app with POST /shorten, GET /{short_code},
  GET /analytics/{short_code}.
- Base.metadata.create_all(bind=engine) at startup.
- Uses secrets module for short code generation.
- Idempotent behavior: existing URL returns same short_code.
- Retry loop on IntegrityError for code collisions.
- Redirects with 307; increments click_count.

**My review and changes:**
- Confirmed `secrets` module used (not `random`).
- Confirmed idempotent lookup by `original_url` before generation.
- Confirmed rollback on `IntegrityError` and 500 after 3 retries.
- No functional changes needed to the initial version.

**Validation:**
- Syntax check: PASS (`python -m py_compile main.py`)
- App import: PASS (`from main import app` → routes registered)
- Smoke tests: PASS
  - POST /shorten → 200, returns short_code
  - POST /shorten duplicate → same short_code (idempotent)
  - GET /{code} → 307 redirect
  - GET /analytics/{code} → click_count incremented
  - GET /{invalid} → 404

**Post-review refactor (lifespan):**
- FastAPI's `@app.on_event("startup")` is deprecated in favor of
  lifespan context managers.
- Prompted Copilot to refactor to `@asynccontextmanager` with
  `Base.metadata.create_all(bind=engine)` before `yield`, passed to
  `FastAPI(lifespan=lifespan)`.
- Verified: tests still pass; the `main.py:17` deprecation warning
  no longer appears in pytest output (warnings dropped from 4 to 2).
- Remaining warnings (Starlette/httpx, anyio.BlockingPortal) are
  upstream library issues, not project code. Documented as known
  limitations rather than fixed, to avoid patching third-party packages.

**Post-review polish (OpenAPI metadata):**
- Swagger UI labeled 307/404 responses as "Undocumented" because
  the route decorators didn't declare them in OpenAPI `responses=`.
- Added `responses={307: ..., 404: ...}` metadata to `GET /{short_code}`,
  and corresponding entries for `/shorten` and `/analytics/{short_code}`.
- Verified: /docs now shows the responses; all tests still pass.

**Post-review fix (fail-open timeout wrapper):**
- Added helper functions `_redis_get_with_timeout` and
  `_redis_set_with_timeout` that wrap Redis calls in a
  `ThreadPoolExecutor` future with `timeout=1.0`.
- Rationale: on Windows, `socket_connect_timeout=1` is not honored when
  the target port is unreachable; TCP SYN retries can exceed 20 seconds.
  A Python-level deadline bounds the fail-open path regardless of OS
  socket behavior.
- **AI-related note:** Copilot added the helper functions but did not
  replace the existing `redis_client.get` / `redis_client.set` calls in
  the redirect handler. It also introduced an indentation error on the
  replacement line. Both were caught during manual verification
  (`py_compile` and looking at the actual call sites).
- Re-verified: with Memurai stopped, redirects complete in ~1–2 seconds
  (previously 26–52 seconds).

---

## Component: Redis Caching Layer (Scaling Upgrade)

**Prompt used:**
> "Modify the GET /{short_code} endpoint in main.py to use Redis caching.
> Build cache key f'url:{short_code}'. On hit, increment click_count and
> return redirect. On miss, query DB, write to Redis with TTL 3600s, then
> increment and redirect. Wrap Redis calls in try/except for fail-open
> behavior. Import redis_client from database."

**Copilot output summary:**
- Added Redis caching to `GET /{short_code}` in `main.py`.
- Cache key: `url:{short_code}` with 1-hour TTL.
- Cache hits still increment DB `click_count`.
- Redis failures fall through to the DB path (fail-open).
- Added a cache-hit regression test to `tests/test_main.py`.

**My review and changes:**
- Verified `redis_client` is imported from `database`.
- Confirmed cache hit path still updates analytics.
- Confirmed fail-open behavior via `try/except`.
- No existing error handling was removed.
- Extended `database.py` with `redis_client` using
  `socket_connect_timeout=1` and `socket_timeout=1`.
- Later added the thread-pool timeout wrapper (see `main.py` section).

**Validation:**
- Test suite: `10 passed, 2 warnings` (was 7; three Redis tests added).
- Manual verification: after a redirect, Redis contains `url:{code}`.
- TTL verification: `redis_client.ttl('url:{code}')` returns a positive
  value under 3600 (observed ~3458s shortly after a write).
- Benchmark (`python benchmark.py`): Redis avg 0.12–0.17 ms vs SQLite
  avg 0.36–0.45 ms over 1,000 iterations. **2.2–3.7× speedup** per lookup.
  Results recorded in ARCHITECTURE.md §9.

**Scaling rationale:**
- URL shorteners are read-heavy (~100:1 read:write ratio).
- Redis caching eliminates DB hits for hot codes.
- TTL keeps memory bounded.
- Fail-open ensures Redis downtime doesn't break redirects.

---

## Component: `tests/test_main.py`

**Prompt used:**
> "Create tests/test_main.py with pytest tests for the FastAPI URL shortener.
> Use FastAPI's TestClient. Use a temporary SQLite database for tests so
> the real shortener.db is not touched. Override the get_db dependency
> to use the test database.
>
> Test cases:
> 1. test_shorten_valid_url — 200, contains short_code/short_url/original_url
> 2. test_shorten_idempotent — same URL returns same short_code
> 3. test_shorten_invalid_url — 422
> 4. test_redirect_valid_code — 307 + location header
> 5. test_redirect_invalid_code — 404
> 6. test_analytics_increments — click_count == 1 after one redirect
> 7. test_analytics_invalid_code — 404
>
> Use pytest fixtures for the test client and test database.
> Clean up after each test."

**Copilot output summary:**
- Created 7 test functions matching the requested cases.
- Used function-scoped fixtures with a temporary SQLite database.
- Overrode the get_db dependency for isolation from production DB.
- Later added 3 Redis-related tests (cache hit, cache miss, fail-open).

**My review and changes:**
- No changes needed to the first 7 tests; they matched the requirements.
- For the Redis tests: verified that the FakeRedis stub replaces
  `main.redis_client` for each test via `monkeypatch`, so no test
  hits the real Memurai instance.
- Added `test_redirect_cache_miss_populates_cache` and
  `test_redirect_fails_open_when_redis_is_down` on top of Copilot's
  initial cache-hit test.

**Validation:**
- Initial run via `pytest tests/test_main.py -q` failed: pytest launcher
  did not put repo root on sys.path, so `main` could not be imported.
- Diagnosis: use `python -m pytest` instead, which uses the active
  interpreter's import path. Minimal fix — no test code changes needed.
- Re-ran: `python -m pytest tests/ -v` → **10 passed, 2 warnings**
- Deprecation warnings from FastAPI/Starlette noted but not blocking.
- Whitespace check: `git diff --check` → clean.
- Confirmed real `shortener.db` untouched (tests use temp DB via override).

---

## Component: `benchmark.py`

**Prompt used:** N/A — authored directly (with Copilot assistance on
structure and statistics formatting).

**Purpose:** Compare Redis cache-hit latency against SQLite lookup
latency for the same short code, over 1,000 iterations each.

**Copilot output summary:**
- Provided the initial structure (fetch a sample code, time Redis, time
  SQLite, compute mean/median/p99).
- Suggested using `time.perf_counter()` for high-resolution timing.

**My review and changes:**
- Tuned iterations to 1,000 to get stable statistics without long runs.
- Added a guard that creates the Redis key if it's missing so the
  benchmark measures a genuine cache hit, not a cold miss.
- Verified the SQLite query mirrors the exact filter used by the
  redirect endpoint.

**Validation:**
- Ran twice: `2.2×` and `3.7×` speedup. Documented as a range
  (2.2–3.7×) in ARCHITECTURE.md §9 to reflect run-to-run variance.

---

## Version Control Setup

**Action:** Initialized Git repository and maintained a clean commit history.

**Files tracked:**
- `.gitignore`
- `.github/copilot-instructions.md`
- `AI_LOG.md`, `README.md`, `ARCHITECTURE.md`, `SCENARIOS.md`, `ENGINEERING_SUMMARY.md`
- `database.py`, `models.py`, `schemas.py`, `main.py`, `benchmark.py`
- `requirements.txt`
- `tests/__init__.py`, `tests/test_main.py`
- `Verification_Image.png`

**Files excluded (via .gitignore):**
- `.venv/` (virtual environment)
- `__pycache__/` (Python bytecode cache)
- `*.db` (local SQLite database)
- `.pytest_cache/`

**Validation:** `git status` shows clean tree; `git log --oneline` shows
a linear commit history.

---

## Summary of AI Outputs Accepted / Modified / Rejected

| Component | Accepted as-is | Modified | Rejected | Notes |
|-----------|---------------|----------|----------|-------|
| database.py | ✅ | | | extended later with redis_client |
| models.py | | ✅ | | fixed deprecated API + added nullable constraint |
| schemas.py | ✅ | | | |
| main.py | | ✅ | | lifespan refactor + OpenAPI metadata + Redis caching + thread-pool timeout wrapper |
| tests/test_main.py | | ✅ | | added 3 Redis tests |
| benchmark.py | ✅ | | | |
| Redis caching layer | | ✅ | | Copilot added helpers but not wired in; fixed manually |

---

## Key Risks Identified and Mitigated

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random code generation | Security | Uses `secrets` module (not `random`) |
| Duplicate URL creation | Functional | Idempotent lookup by `original_url` |
| SQLite thread-safety | Runtime | `check_same_thread=False` in database.py |
| Missing dependency | Build | Pinned in requirements.txt |
| Deprecated `datetime.utcnow` | Maintainability | Replaced with `datetime.now(timezone.utc)` |
| Invalid URL input | Functional | Pydantic field_validator rejects non-http(s) URLs |
| Short code collision | Functional | Retry loop on IntegrityError (max 3 attempts) |
| Missing 404 handling | Functional | HTTPException 404 for missing short codes |
| Test DB contamination | Test isolation | Dependency override with temp SQLite per test |
| pytest path issues | Build | Use `python -m pytest` (adds repo root to sys.path) |
| Deprecated `@app.on_event("startup")` | Maintainability | Refactored to `@asynccontextmanager` lifespan |
| Redis unavailable | Availability | Fail-open: fall through to DB path |
| Stale cache entries | Consistency | 1-hour TTL; acceptable for URL shorteners |
| Redis socket hang on Windows | Availability | Thread-pool timeout wraps every Redis call at 1s |
| Copilot runtime misdiagnosis | AI-related | Cross-check every "not installed" claim in active venv |
| Copilot scaffolding not wired in | AI-related | Verify generated helpers are actually called |

---

## Assumptions and Limitations

- SQLite used for simplicity; production would use PostgreSQL.
- No authentication / rate limiting implemented yet.
- Short codes are 6 characters (space of ~56 billion); acceptable for prototype.
- Analytics limited to total `click_count`; no time-series or per-IP data.
- FastAPI/Starlette emit deprecation warnings about httpx and anyio
  aliases. These are upstream and not caused by project code.
- The `on_event` deprecation was caused by project code and was
  refactored to a lifespan handler.
- Redis caching implemented locally with Memurai (Redis-compatible).
  Production would use Redis or Memurai Enterprise.
- HTTP-layer load testing (concurrent clients, sustained RPS) not
  performed. Backend lookup latency is benchmarked; see ARCHITECTURE.md §9.

---

## Final Notes

All AI-generated outputs were reviewed line-by-line before acceptance.
Full ownership of the final codebase rests with the candidate.