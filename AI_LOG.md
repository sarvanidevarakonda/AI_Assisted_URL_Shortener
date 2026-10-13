# AI Assistance Log

**Project:** AI-Assisted URL Shortener Service  
**Candidate:** Sarvani Devarakonda  
**AI Tool:** GitHub Copilot (Agent Mode)  
**Date Started:** 2026-09-13  
**Last Updated:** 2026-10-13

---

## Purpose

This log documents how GitHub Copilot was used across the project: the
prompts issued, the outputs generated, my review of each output, and how
correctness was validated. It serves as evidence of AI-assisted
engineering under full human ownership.

Companion document: `AI_EVIDENCE.md` — four concrete cases where an AI
suggestion was rejected, corrected, or redesigned, each tied to a
repeatable command.

---

## Workflow Summary

For each component:
1. Wrote a specific prompt in Copilot Agent Mode.
2. Reviewed Copilot's output against engineering standards.
3. Accepted, modified, or rejected the output.
4. Validated via import check and/or tests.
5. Logged the result below.

The log is organized chronologically. The initial build is the first
half; the second half documents improvements driven by a reviewer's
feedback.

---

# Part 1 — Initial Build

## Component: `.github/copilot-instructions.md`

**Prompt used:** N/A — authored directly.

**Purpose:** Provides project context to Copilot (tech stack, standards,
rules).

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
- Runtime import: initially FAILED — SQLAlchemy not installed.
- Resolution: ran `pip install sqlalchemy`, re-ran import → PASS.
- Updated `requirements.txt` to reflect new dependency.

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
- Left a stray `created_at = Column(...)` line at the top of the file,
  outside any class.

**My review and changes:**
- Removed the stray top-level `created_at` line (would raise NameError
  on import).
- Added `from datetime import datetime, timezone` — missing from
  Copilot's output.
- Replaced deprecated `datetime.utcnow` with `datetime.now(timezone.utc)`.
- Added `nullable=False` to `short_code` (a short code must always exist).

**Validation:**
- Syntax check: PASS
- Runtime import: PASS
- Introspection check: `URLMapping.short_code.unique=True`,
  `index=True`, `nullable=False`.

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
- Generated URLRequest, URLResponse, AnalyticsResponse with Pydantic v2
  syntax.
- URLRequest includes a field_validator for http:// and https://.
- Response models use ConfigDict(from_attributes=True).

**My review and changes:**
- Verified Pydantic v2 imports (`field_validator`, `ConfigDict`), no v1
  `@validator`.
- Validator correctly rejects strings not starting with http:// or
  https://.
- No functional changes needed at this stage. Structural validation
  added later (see Part 2, "URL Validation Strengthened").

**Validation:**
- Syntax check: PASS
- Runtime import: PASS
- Valid URL: PASS — model constructed
- Invalid URL: PASS — raised ValidationError with custom message

**Note on Copilot limitation:**
- Copilot Agent Mode reported "Pydantic not installed" during its own
  runtime check, but `pip show pydantic` confirmed v2.13.5 was installed
  in the active venv. Copilot's terminal context does not always inherit
  the venv, so its runtime claims are not authoritative.

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
- Syntax check: PASS
- App import: PASS
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
  `Base.metadata.create_all(bind=engine)` before `yield`.
- Verified: tests still pass; the deprecation warning no longer appears.

**Post-review polish (OpenAPI metadata):**
- Swagger UI labeled 307/404 responses as "Undocumented" because the
  route decorators didn't declare them in OpenAPI `responses=`.
- Added `responses={307: ..., 404: ...}` metadata to `GET /{short_code}`,
  and corresponding entries for `/shorten` and `/analytics/{short_code}`.

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
  replacement line. Both were caught during manual verification.
- Re-verified: with Memurai stopped, redirects complete in ~1–2 seconds
  (previously 26–52 seconds).

---

## Component: Redis Caching Layer

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

**My review and changes:**
- Verified `redis_client` is imported from `database`.
- Extended `database.py` with `redis_client` using
  `socket_connect_timeout=1` and `socket_timeout=1`.
- Later added the thread-pool timeout wrapper (see `main.py` section).
- **Later redesigned the click-tracking path** — see Part 2, "Queue-Based
  Click Tracking" for the corrected design and benchmark results.

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

**My review and changes:**
- No changes needed to the first 7 tests.
- Added 3 Redis tests (cache hit, cache miss, fail-open) with a
  FakeRedis stub that replaces `main.redis_client` via `monkeypatch`.
- Added 6 URL-validation tests, 1 concurrency test, 1 rate-limit test
  (see Part 2).

**Validation:**
- Initial run via `pytest tests/test_main.py -q` failed: pytest launcher
  did not put repo root on sys.path, so `main` could not be imported.
- Diagnosis: use `python -m pytest` instead. Minimal fix.
- Final: **18 passed, 0 warnings** (after Part 2 additions).

---

## Component: `benchmark.py`

**Prompt used:** N/A — authored directly (with Copilot assistance on
structure and statistics formatting).

**Purpose (initial):** Compare Redis cache-hit latency against SQLite
lookup latency for the same short code.

**My review and changes:**
- Tuned iterations to 1,000 for stable statistics.
- Later redesigned as a three-path comparison (DB-only, cache+DB,
  cache+queue). See Part 2.

---

## Version Control Setup

**Action:** Initialized Git repository and maintained a clean commit
history.

**Validation:** `git status` shows clean tree; `git log --oneline`
shows a linear commit history.

---

# Part 2 — Feedback-Driven Improvements

A reviewer provided feedback on five areas after the initial
submission. This section documents the work done in response.

## 1. Requirement-to-Engineering Workflow Tool

**Prompt used:** Engineer-directed design; Copilot assisted with the
dataclass structure and argparse setup.

**What was built:**
- `workflow.py` — a CLI that reads a requirement (file or stdin) and
  emits a structured engineering plan as markdown with 7 sections:
  interpreted problem, ambiguities/assumptions, sequenced tasks, AI
  assistance points, proposed artifacts, acceptance checks, risks.
- `examples/url_shortener.txt`, `examples/brownfield_add_expiry.txt`,
  `examples/ambiguous_scale.txt` — three sample requirements.
- Hybrid design: a catalog for known requirement types plus a generic
  fallback template for arbitrary inputs.

**Validation:**
- `python workflow.py --list` → lists catalog entries.
- `python workflow.py examples/url_shortener.txt` → matches catalog,
  produces the correct 7-section report.
- Generic fallback verified via stdin.

**Note:** The assignment explicitly says it is *not* asking for an
autonomous agent. The tool produces structure, not decisions. Every
section is reviewed by the engineer before use.

---

## 2. Queue-Based Click Tracking (Redis Performance Corrected)

**The problem:** An earlier review found that the cache-hit path still
performed a synchronous DB write to increment `click_count`. That
meant the cache did not actually avoid a DB round-trip.

**Benchmark evidence (before the fix):**
- DB-only path: ~8 ms avg
- Cache + synchronous DB write: ~7.7 ms avg
- Only ~4% improvement — the cache wasn't doing its job.

**What was changed:**
- Cache-hit path now does Redis `GET` for the URL and Redis `RPUSH`
  to enqueue a click. **No DB touch on the hot path.**
- A `ClickFlushWorker` background thread drains the click queue every
  5 seconds and applies batched atomic increments via
  `UPDATE ... SET click_count = click_count + N`.
- Analytics endpoint adds the pending queue depth to the persisted
  count so results are always current.
- Worker accepts an optional `session_factory` so tests can point it
  at the isolated test DB.

**Benchmark evidence (after the fix, two runs):**
- DB-only: 8.1 – 25.8 ms avg
- Cache + DB write: 7.7 – 24.7 ms avg
- Cache + queue (hot path): **0.3 – 0.6 ms avg**
- **Hot-path speedup: 27.6× – 40.8×**

**New tests added for this design:**
- `test_redirect_cache_miss_populates_cache`
- `test_redirect_fails_open_when_redis_is_down`
- `test_concurrent_clicks_are_counted_correctly`
  (20 parallel redirects → exactly 20 clicks after flush)

---

## 3. Validation Strengthened

**More tests (18 total, was 10):**
- 6 new URL-structural-validation tests
- 1 concurrency test
- 1 rate-limit test

**Structural URL validation (`schemas.py`):**
- Switched from a scheme-prefix check to `urllib.parse.urlparse`.
- Rejects empty hosts, whitespace, and hosts without a dot (except
  `localhost`).
- Trims leading/trailing whitespace.

**CI (GitHub Actions):**
- `.github/workflows/tests.yml` runs the full suite on Ubuntu with a
  Redis 7 service container on every push to `main`.
- The CI run for the current head commit is green.

**pytest.ini:**
- Added to silence upstream deprecation warnings from
  Starlette/httpx/anyio. The suite reports **18 passed, 0 warnings**.

---

## 4. Production-Readiness Layer

**Configuration (`config.py`):**
- `BASE_URL`, `RATE_LIMIT_SHORTEN`, `REDIS_HOST`, `REDIS_PORT`,
  `REDIS_DB`, `CACHE_TTL_SECONDS` — all env-driven with defaults.
- `main.py` and `database.py` import from `config.py` instead of
  hardcoding values.

**Rate limiting (`slowapi`):**
- Applied to `POST /shorten` at 20 requests/minute per IP.
- Verified with `test_rate_limit_returns_429_after_quota`.

**Structured logging:**
- Added a `JsonFormatter` that emits one JSON object per line to stdout.
- Every endpoint logs a structured event (`redirect cache_hit`,
  `shorten created`, `worker flushed clicks=N`).

**Health / readiness:**
- `/health` — liveness probe.
- `/ready` — readiness probe that checks both DB and Redis.

---

## 5. AI Ownership Independently Reviewable

**New file: `AI_EVIDENCE.md`**
- Four concrete examples of AI suggestions that were rejected,
  corrected, or redesigned by the engineer.
- Each entry shows: the AI output, what was wrong, the fix, the
  evidence (test or benchmark), and a repeatable command to verify.

**Cases documented:**
1. Copilot generated fail-open timeout helpers but didn't wire them in.
2. Copilot used deprecated `datetime.utcnow()`.
3. `socket_connect_timeout` alone insufficient on Windows — replaced
   with thread-pool timeout wrapper.
4. Cache-only design didn't eliminate the DB write — redesigned as
   queue-based click tracking.

---

# Summary of AI Outputs Accepted / Modified / Rejected

| Component | Accepted as-is | Modified | Rejected | Notes |
|-----------|:-------------:|:--------:|:--------:|-------|
| database.py | ✅ | | | Extended later with redis_client |
| models.py | | ✅ | | Fixed deprecated API + added nullable constraint |
| schemas.py | | ✅ | | Structural URL validation added in Part 2 |
| main.py | | ✅ | | Lifespan refactor + OpenAPI metadata + cache + queue + worker + logging + rate limit |
| tests/test_main.py | | ✅ | | Grew from 7 to 18 tests |
| benchmark.py | | ✅ | | Redesigned as three-path comparison |
| Redis caching layer | | ✅ | | Copilot added helpers but not wired in; fixed manually |
| workflow.py | ✅ | | | Engineer-directed design; Copilot assisted with structure |
| config.py | ✅ | | | Authored directly |
| AI_EVIDENCE.md | ✅ | | | Authored directly |

---

# Key Risks Identified and Mitigated

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random code generation | Security | Uses `secrets` module (not `random`) |
| Duplicate URL creation | Functional | Idempotent lookup by `original_url` |
| SQLite thread-safety | Runtime | `check_same_thread=False` |
| Missing dependency | Build | Pinned in `requirements.txt` |
| Deprecated `datetime.utcnow` | Maintainability | Replaced with `datetime.now(timezone.utc)` |
| Invalid URL input | Functional | Pydantic field_validator; structural parsing added in Part 2 |
| Short code collision | Functional | Retry loop on IntegrityError (max 3 attempts) |
| Missing 404 handling | Functional | HTTPException 404 for missing short codes |
| Test DB contamination | Test isolation | Dependency override with temp SQLite per test |
| pytest path issues | Build | Use `python -m pytest` |
| Deprecated `@app.on_event` | Maintainability | Refactored to lifespan handler |
| Redis unavailable | Availability | Fail-open: fall through to DB path |
| Stale cache entries | Consistency | 1-hour TTL |
| Redis socket hang on Windows | Availability | Thread-pool timeout wraps every Redis call at 1s |
| Worker flush failure | Data integrity | Popped items re-queued so no click is lost |
| Worker targets wrong DB in tests | Test correctness | `session_factory` injection |
| Config drift between environments | Ops | All settings in `config.py` from env vars |
| Abuse / spam creation | Security | slowapi rate limit on `POST /shorten` (20/min) |
| Copilot runtime misdiagnosis | AI-related | Cross-check every "not installed" claim in the active venv |
| Copilot scaffolding not wired in | AI-related | Verify generated helpers are actually called; read the diff |

---

# Assumptions and Limitations

- SQLite used for simplicity; production would use PostgreSQL.
- Short URL base is configurable via `BASE_URL` (default
  `http://localhost:8000`).
- Rate limiting is per-IP via slowapi using in-memory storage.
  Production would use a shared backend (Redis) for multi-instance
  deployments.
- No authentication or API keys yet.
- Analytics is a single integer `click_count` — no time-series.
- No custom aliases, expiry, or link deactivation.
- The single-segment route `/{short_code}` would need reordering or a
  prefix if more single-segment routes are added later.
- Redis caching implemented locally with Memurai (Redis-compatible).
  Production would use Redis or Memurai Enterprise.
- The fail-open wrapper uses a small thread pool (`max_workers=4`); at
  very high concurrency with Redis down, requests could queue. For
  production, an async Redis client would be preferred.
- `click_count` in the database lags by up to the 5-second worker
  interval; the analytics endpoint corrects for this by adding the
  pending queue depth.
- HTTP-layer load testing (concurrent clients, sustained RPS) not
  performed. Backend lookup latency is benchmarked; see
  `ARCHITECTURE.md` §9.

---

# Final Notes

All AI-generated outputs were reviewed line-by-line before acceptance.
Full ownership of the final codebase rests with the candidate.

`AI_EVIDENCE.md` documents four concrete cases where an AI suggestion
was rejected, corrected, or redesigned by the engineer, with a
repeatable command to verify each one. That makes the ownership claim
reviewable rather than asserted.