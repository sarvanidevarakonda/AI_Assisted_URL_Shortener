# Engineering Summary

**Candidate:** Sarvani Devarakonda
**Project:** AI-Assisted URL Shortener
**Deliverable:** Interview Assignment — AI-Proficient Software Engineer
**Date:** 2026-09-14

---

## 1. Implementation Approach and Rationale

I built a URL shortener with three HTTP endpoints (`POST /shorten`,
`GET /{short_code}`, `GET /analytics/{short_code}`) plus `/health` and
`/ready` probes, using FastAPI, SQLAlchemy, SQLite, and a Redis-compatible
cache and queue layer. The design deliberately kept each concern in its
own module:

- `database.py` — engine, session lifecycle, and Redis client
- `models.py` — persistent entity
- `schemas.py` — request/response contracts
- `main.py` — routing, caching, queue-based click tracking, and a
  background flush worker
- `benchmark.py` — three-path latency comparison

GitHub Copilot (Agent Mode) generated the first draft of each module. I
then reviewed every line, corrected deprecated APIs, added missing
constraints, redesigned the caching layer to eliminate the DB write
from the hot path, and validated behavior with an 11-test pytest suite
that uses per-test database isolation.

The intent was not to maximize AI output — it was to demonstrate that
AI accelerates *while the engineer retains ownership*. That ownership
is visible in `AI_LOG.md`, which records the prompt used for each
component, what Copilot produced, and what I changed.

## 2. Generated Artifacts

| Artifact | Purpose |
|----------|---------|
| `database.py` | SQLAlchemy engine, `SessionLocal`, `Base`, `get_db()`, `redis_client` |
| `models.py` | `URLMapping` table with indexed, unique `short_code` |
| `schemas.py` | Pydantic v2 models with URL validation |
| `main.py` | FastAPI app with lifespan handler, 5 endpoints, queue-based click tracking, background flush worker, fail-open timeout wrapper |
| `ClickFlushWorker` (in `main.py`) | Background thread; drains the Redis click queue into SQLite every 5s |
| `benchmark.py` | Three-path latency comparison (DB-only, cache+DB, cache+queue) |
| `tests/test_main.py` | 11 endpoint tests with temp DB per test |
| `AI_LOG.md` | Per-file prompt/output/validation record |
| `ARCHITECTURE.md` | System design, cache model, AI integration, trade-offs |
| `SCENARIOS.md` | Greenfield / brownfield / ambiguous walkthroughs |
| `README.md` | Setup, API reference, testing, quick verification |
| `Verification_Image.png` | Screenshot of Swagger UI showing documented responses |

## 3. Validation Approach

Three layers of validation:

**Static**
- `py_compile` on every file
- Editor diagnostics
- `git diff --check` for whitespace

**Runtime**
- Import check for each module
- `Base.metadata.create_all()` confirmed the table was created
- `sqlite_master` inspection confirmed the schema
- Redis client verified via `SET`/`GET` smoke test

**Behavioral**
- 11 pytest cases covering valid/invalid input, idempotency, redirect
  status + location, cache hit path, cache miss path, fail-open on
  Redis outage, analytics increment, 404 paths, and **20 concurrent
  redirects producing exactly 20 clicks** after queue flush
- Manual curl tests during development
- Benchmark: 1,000 iterations per scenario across three handler paths

Final state: **11 passed, 2 warnings** in ~24s. The two remaining
warnings are upstream (Starlette/httpx, anyio) and not project code.

## 3a. Performance and Scale Notes

The assignment calls for a "scalable" service. This section states
clearly what was measured and what was not.

**What is designed for scale:**
- Indexed `short_code` column for O(log n) lookups
- Unique constraint preventing duplicates at the DB layer
- Idempotent `POST /shorten` preventing unbounded duplicate rows
- Stateless FastAPI handlers suitable for horizontal scaling
- `secrets`-based uniform code distribution to avoid hot spots
- Redis cache removing the URL-lookup DB hit for hot codes
- **Queue-based click tracking** removing the click-write DB hit
  from the hot path entirely
- **Batched atomic UPDATEs** — the worker flushes many clicks in one
  transaction, so the DB sees far fewer writes under load
- Thread-pool timeout wrapping every Redis call, so fail-open latency
  is bounded at ~1s regardless of OS socket behavior

**What is measured:**
- Benchmark of three handler paths (1,000 iterations each, `benchmark.py`):
  1. DB-only (pre-cache): `SELECT` + `UPDATE` → **8.07 ms avg**
  2. Cache + DB write: Redis `GET` + `UPDATE` → **7.74 ms avg**
  3. **Cache + queue (hot path): Redis `GET` + `RPUSH` → 0.29 ms avg**
- **Hot-path speedup vs pre-cache: 27.6×.**
- Cache-only design (option 2) gave only ~4% improvement because the
  DB write dominated. Moving clicks to a queue removed the write
  entirely — that is where the real gain comes from.
- Concurrent-click correctness: 20 parallel redirects → final count
  is exactly 20 after queue flush (verified in
  `test_concurrent_clicks_are_counted_correctly`).
- Fail-open behavior with Redis down completes in **~1–2 seconds**,
  bounded by a `ThreadPoolExecutor` future timeout of 1s.

**Honest caveat:** `click_count` in the database lags by up to the
5-second worker interval. The analytics endpoint compensates by adding
the pending queue depth, so the user-visible count is always accurate.

**What is not measured:**
- HTTP-layer load testing (concurrent clients, sustained RPS).
- Multi-region latency.
- Behavior under cache eviction / cold-start at high churn.
- Worker scaling under high queue depth.

**Why this scope:**
The handler path is the dominant cost on the redirect. Measuring it
directly yields actionable evidence for the caching and queue design
without requiring the infrastructure for HTTP load testing. Load
testing is listed as a productionization step in `ARCHITECTURE.md` §10.

## 3b. Validation Evidence

Every claim in this summary is backed by a specific observation from
running the code. Evidence is listed here so a reviewer can verify
each claim independently.

| Claim | How It Was Verified | Observed Result |
|-------|---------------------|-----------------|
| Test suite passes | `python -m pytest tests/ -v` | `11 passed, 2 warnings in ~24s` |
| Database table created | `Base.metadata.create_all()` at startup; `sqlite_master` query | `[('url_mappings',)]` |
| Index on `short_code` | Introspection: `URLMapping.short_code.index` | `True` |
| Unique constraint | Introspection: `URLMapping.short_code.unique` | `True` |
| Not nullable | Introspection: `URLMapping.short_code.nullable` | `False` |
| URL validation rejects bad input | `POST /shorten` with `{"original_url": "notaurl"}` | `422` with `"must start with http:// or https://"` |
| Idempotent creation | `POST /shorten` twice with same URL | Same `short_code` both times |
| Redirect works | Server log during manual test | `"GET /u7o6u1 HTTP/1.1" 307` |
| Analytics increments | `GET /analytics/{code}` after one redirect | `click_count` incremented |
| 404 for unknown code | `GET /zzzzzz` | `404` with `{"detail": "Short URL not found"}` |
| OpenAPI metadata documents 307/404 | `/docs` after `responses=` addition | Swagger UI shows both status codes |
| Redis URL cache populates on miss | `redis_client.get('url:{code}')` after a redirect | Original URL stored |
| Cache hit doesn't call Redis SET | `test_redirect_cache_hit_uses_cached_url_and_increments_clicks` | PASSED — `set_calls == []` |
| TTL applied to URL cache | `redis_client.ttl('url:{code}')` | Positive value < 3600 |
| Cache-hit click is queued, not written | `test_redirect_cache_hit_uses_cached_url_and_increments_clicks` | PASSED — analytics reads queue depth |
| **20 concurrent clicks → exact count** | `test_concurrent_clicks_are_counted_correctly` | PASSED — count == 20 after flush |
| Fail-open works (mocked) | `test_redirect_fails_open_when_redis_is_down` | PASSED |
| Fail-open works (real outage) | Stopped Memurai, hit redirect URL | Redirect succeeded in ~1–2 s |
| **Hot-path speedup** | `python benchmark.py` | 0.29 ms vs 8.07 ms = **27.6×** |

**Note on the redirect via Swagger:** Swagger's "Execute" button
triggers a CORS block when the endpoint returns a 307 to an external
domain. The 307 is verified via the browser address bar and `curl -i`
instead. This is documented in `README.md`.

## 4. Risks and Mitigation

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random codes | Security | `secrets` module (not `random`) |
| Duplicate URL creation | Functional | Idempotent lookup by `original_url` |
| Short-code collision | Functional | Retry loop (3×) on `IntegrityError` |
| Missing short-code index | Performance | `index=True` on `short_code` |
| SQLite thread-safety | Runtime | `check_same_thread=False` |
| Deprecated `datetime.utcnow` | Maintainability | Replaced with `datetime.now(timezone.utc)` |
| Deprecated `@app.on_event` | Maintainability | Refactored to `@asynccontextmanager` lifespan |
| Test DB contamination | Test isolation | Dependency override with temp SQLite |
| pytest import failure | Build | Use `python -m pytest` (adds repo root to path) |
| Redis unavailable | Availability | Fail-open: fall through to atomic DB increment |
| Stale URL cache | Consistency | 1-hour TTL; short codes are immutable |
| Redis socket hang on Windows | Availability | Thread-pool future timeout wraps every Redis call at 1s |
| Worker flush failure | Data integrity | Popped items re-queued so no click is lost |
| Worker targets wrong DB in tests | Test correctness | `ClickFlushWorker(session_factory=...)` injection |
| Copilot runtime misdiagnosis | AI-related | Cross-check every "not installed" claim in the active venv |
| Copilot scaffolding not wired in | AI-related | Verify generated helpers are actually called; read the diff |

## 5. AI-Related Risks Observed

Three concrete failure modes emerged during the build:

**1. Copilot reported a missing dependency that was installed.**
Twice, Copilot Agent Mode claimed SQLAlchemy or Pydantic was not
installed. `pip show` proved both were present in the active venv.
Copilot's terminal context does not always inherit the venv, so its
runtime claims are not authoritative. **Mitigation:** always re-run
the check in the engineer's own terminal before acting on it.

**2. Copilot emitted deprecated APIs.**
Copilot used `datetime.utcnow()` and `@app.on_event("startup")`, both
deprecated in the current Python / FastAPI. **Mitigation:** treat AI
output as a draft; review against current idioms; refactor.

**3. Copilot generated scaffolding that wasn't wired in.**
When adding the fail-open timeout wrapper, Copilot created the helper
functions (`_redis_get_with_timeout`, `_redis_set_with_timeout`) but
left the direct `redis_client.get` / `redis_client.set` calls in the
redirect handler. The helpers existed but were never invoked. It also
introduced an indentation error on the replacement line.
**Mitigation:** verify that generated helpers are actually called;
review the diff, not just the new code; catch issues with `py_compile`
and manual testing.

None of these were fatal, but all three illustrate why ownership
cannot be delegated to the AI.

## 6. Assumptions and Limitations

- SQLite is used for simplicity; production would use PostgreSQL.
- Short URLs are hardcoded to `http://localhost:8000`.
- No authentication, rate limiting, or abuse protection.
- Analytics is a single integer `click_count` — no time-series.
- No custom aliases, expiry, or link deactivation.
- The single-segment route `/{short_code}` would need reordering or a
  prefix if more single-segment routes are added later.
- Redis caching is implemented locally with Memurai (Redis-compatible).
  Production would use Redis or Memurai Enterprise.
- The fail-open wrapper uses a small thread pool (`max_workers=4`); at
  very high concurrency with Redis down, requests could queue. For
  production, an async Redis client would be preferred.
- `click_count` in the database lags by up to the 5-second worker
  interval; the analytics endpoint corrects for this by adding the
  pending queue depth.
- HTTP-layer load testing (concurrent clients, sustained RPS) not
  performed. Backend lookup latency is benchmarked; see §3a.
- Two upstream deprecation warnings remain (Starlette/httpx, anyio).

## 7. What Success Looks Like (Self-Assessment)

Against the assignment's own success criteria:

| Criterion | Evidence |
|-----------|----------|
| Effective use of AI tools | `AI_LOG.md` — prompt, output, and review per file; specific rejection logged |
| Strength of software design | Layered modules, indexed model, Pydantic validation, cache + queue design |
| Quality and correctness | 11/11 tests pass; 20-way concurrent click test; manual curl verified; benchmark recorded |
| Demonstrated ownership | Every AI output reviewed; deprecated APIs corrected; queue design engineer-directed; unwired helpers caught |
| Validation rigor | Static + runtime + behavioral + benchmark + concurrency documented |
| Clarity and defensibility | Four docs + log; every choice has a rationale |
| Controlled autonomy | Engineer-led decomposition; AI execution per task |

## 8. Final Reflection

Copilot was genuinely useful — it produced working scaffolds for each
module in minutes, which let me spend more time on review and
validation than on typing. But every meaningful decision (index
placement, timezone-aware timestamps, lifespan refactor, test
isolation, route ordering, cache TTL, fail-open timeout strategy, and
the queue-based click design) was made by the engineer, not the AI.

The caching work is the clearest illustration. Copilot generated the
first draft of the redirect handler with Redis, but the design
decisions were mine:

1. **Queue over synchronous write.** After reviewing the cache-hit
   path, I noticed the cache wasn't actually saving a DB round-trip.
   Benchmarking confirmed it: caching the URL alone gave ~4%
   improvement. Moving clicks to a Redis queue removed the DB write
   from the hot path entirely and produced a 27.6× speedup.
2. **Thread-pool timeout for fail-open.** `socket_connect_timeout=1`
   on Windows does not honor the timeout when the port is unreachable
   — a real outage test showed 52-second redirects. Wrapping Redis
   calls in a `ThreadPoolExecutor` with a Python-level deadline
   bounded fail-open latency to ~1 second.
3. **Worker session injection.** The background worker needed a
   `session_factory` parameter so tests could point it at the isolated
   test DB — otherwise it silently wrote to the production database
   and the concurrency test returned 0.

The log is the artifact I'd point to first: it records the exact
prompts, the exact outputs, and the exact corrections — a paper trail
that makes the ownership claim verifiable rather than asserted.

**AI assists the engineer within tasks; the engineer owns execution
and quality.** This project is my attempt to demonstrate that in a
small, reviewable package.