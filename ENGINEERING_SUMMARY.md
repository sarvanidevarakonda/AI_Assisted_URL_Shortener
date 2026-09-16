# Engineering Summary

**Candidate:** Sarvani Devarakonda
**Project:** AI-Assisted URL Shortener
**Deliverable:** Interview Assignment — AI-Proficient Software Engineer
**Date:** 2026-09-14

---

## 1. Implementation Approach and Rationale

I built a URL shortener with three HTTP endpoints (`POST /shorten`,
`GET /{short_code}`, `GET /analytics/{short_code}`) using FastAPI,
SQLAlchemy, SQLite, and a Redis-compatible cache layer. The design
deliberately kept each concern in its own module:

- `database.py` — engine, session lifecycle, and Redis client
- `models.py` — persistent entity
- `schemas.py` — request/response contracts
- `main.py` — routing, caching, and orchestration
- `benchmark.py` — Redis vs SQLite lookup latency comparison

GitHub Copilot (Agent Mode) generated the first draft of each module. I
then reviewed every line, corrected deprecated APIs, added missing
constraints, added the caching layer, and validated behavior with a
10-test pytest suite that uses per-test database isolation.

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
| `main.py` | FastAPI app with lifespan handler, 3 endpoints, Redis-cached redirect, fail-open timeout wrapper |
| `benchmark.py` | Redis vs SQLite lookup latency benchmark |
| `tests/test_main.py` | 10 endpoint tests with temp DB per test |
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
- 10 pytest cases covering valid/invalid input, idempotency, redirect
  status + location, cache hit path, cache miss path, fail-open on
  Redis outage, analytics increment, and 404 paths
- Manual curl tests during development
- Benchmark: 1,000 iterations per backend

Final state: **10 passed, 2 warnings** in ~1.5s. The two remaining
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
- Redis cache layer removing DB hits for hot codes
- Thread-pool-bounded Redis timeout so fail-open latency is fixed at
  ~1 second regardless of OS socket behavior

**What is measured:**
- Redis cache hits average **0.12–0.17 ms** vs SQLite lookups at
  **0.36–0.45 ms** — a **2.2–3.7× speedup** per lookup (1,000
  iterations each, local loopback, across two runs).
- P99 latency improves from **0.90–1.26 ms** (SQLite) to
  **0.28–0.56 ms** (Redis) — up to **4.5× improvement at the tail**,
  which matters most under load.
- Fail-open behavior with Redis down completes in **~1–2 seconds**,
  bounded by a `ThreadPoolExecutor` future timeout of 1s (verified
  manually by stopping the Memurai service).
- Benchmark script: `benchmark.py`. Full results in `ARCHITECTURE.md` §9.

**What is not measured:**
- HTTP-layer load testing (concurrent clients, sustained RPS).
- Multi-region latency.
- Behavior under cache eviction / cold-start conditions at high churn.

**Why this scope:**
The backend lookup is the dominant cost on the redirect path. Measuring
it directly yields actionable evidence for the caching decision without
requiring the infrastructure needed for HTTP load testing. Load
testing is listed as a productionization step in `ARCHITECTURE.md` §10.

## 3b. Validation Evidence

Every claim in this summary is backed by a specific observation from
running the code. Evidence is listed here so a reviewer can verify
each claim independently.

| Claim | How It Was Verified | Observed Result |
|-------|---------------------|-----------------|
| Test suite passes | `python -m pytest tests/ -v` | `10 passed, 2 warnings in ~1.5s` |
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
| Redis cache populates on redirect | `redis_client.get('url:{code}')` after a redirect | Original URL stored |
| Redis cache reduces latency | `python benchmark.py`, 1,000 iterations per backend | Redis ~0.12–0.17 ms avg vs SQLite ~0.36–0.45 ms avg (2.2–3.7× speedup) |
| TTL applied | `redis_client.ttl('url:{code}')` | Positive value (< 3600) |
| Cache-hit test passes | `test_redirect_cache_hit_uses_cached_url_and_increments_clicks` | PASSED |
| Cache-miss test passes | `test_redirect_cache_miss_populates_cache` | PASSED |
| Fail-open works (mocked) | `test_redirect_fails_open_when_redis_is_down` | PASSED |
| Fail-open works (real outage) | Stopped Memurai service, hit redirect URL | Redirect succeeded within ~1–2 seconds |

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
| Redis unavailable | Availability | Fail-open: fall through to DB path |
| Stale cache entries | Consistency | 1-hour TTL; acceptable for URL shorteners |
| Redis socket hang on Windows | Availability | Thread-pool timeout wraps every Redis call at 1s |
| Copilot runtime misdiagnosis | AI-related | Cross-check every "not installed" claim in the active venv |

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
- HTTP-layer load testing (concurrent clients, sustained RPS) not
  performed. Backend lookup latency is benchmarked; see §3a.
- Two upstream deprecation warnings remain (Starlette/httpx, anyio).

## 7. What Success Looks Like (Self-Assessment)

Against the assignment's own success criteria:

| Criterion | Evidence |
|-----------|----------|
| Effective use of AI tools | `AI_LOG.md` — prompt, output, and review per file |
| Strength of software design | Layered modules, indexed model, Pydantic validation, cache layer |
| Quality and correctness | 10/10 tests pass; manual curl verified; benchmark recorded |
| Demonstrated ownership | Every AI output reviewed; deprecated APIs corrected; caching designed and tested; unwired helpers caught |
| Validation rigor | Static + runtime + behavioral + benchmark documented |
| Clarity and defensibility | Four docs + log; every choice has a rationale |
| Controlled autonomy | Engineer-led decomposition; AI execution per task |

## 8. Final Reflection

Copilot was genuinely useful — it produced working scaffolds for each
module in minutes, which let me spend more time on review and
validation than on typing. But every meaningful decision (index
placement, timezone-aware timestamps, lifespan refactor, test
isolation, route ordering, cache TTL, fail-open timeout strategy) was
made by the engineer, not the AI.

The caching work is a good illustration: Copilot generated the first
draft of the redirect handler with Redis, but the design decisions —
key pattern, TTL length, fail-open strategy, and the thread-pool
timeout wrapper to bound fail-open latency on Windows — were all
engineer choices, validated with a benchmark, a new regression test,
and a real-world outage test.

The log is the artifact I'd point to first: it records the exact
prompts, the exact outputs, and the exact corrections — a paper trail
that makes the ownership claim verifiable rather than asserted.

**AI assists the engineer within tasks; the engineer owns execution
and quality.** This project is my attempt to demonstrate that in a
small, reviewable package.