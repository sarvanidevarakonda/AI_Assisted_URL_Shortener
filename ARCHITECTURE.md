# Architecture Overview

## 1. System Design

The URL shortener follows a classic three-layer design:

    Client (curl / browser)
             |
             | HTTP
             v
    FastAPI Application
      main.py
      - POST /shorten
      - GET  /{short_code}
      - GET  /analytics/{short_code}
      - GET  /health
      - GET  /ready
             |
             | SQLAlchemy ORM           | Redis (Memurai)
             v                          v
    SQLite Database               Cache + click queue
      url_mappings                  url:{short_code} -> original_url
        id, original_url,           clicks:queue (list of short codes)
        short_code,                 TTL = 3600s on URL entries
        created_at, click_count
             ^
             |
      ClickFlushWorker (background thread, every 5s)

### Layer Responsibilities

| Layer | File | Responsibility |
|-------|------|----------------|
| HTTP / routing | main.py | Request parsing, route logic, response shaping |
| Validation | schemas.py | Request/response contracts, input sanitization |
| Domain model | models.py | Persistent entity + ORM mapping |
| Persistence | database.py | Engine, session factory, session lifecycle, Redis client |
| Background worker | main.py (`ClickFlushWorker`) | Drains the Redis click queue into SQLite every 5s |
| Tests | tests/test_main.py | Endpoint behavior, cache paths, fail-open, concurrency |
| Benchmark | benchmark.py | Three-path latency comparison (DB-only, cache+DB, cache+queue) |

## 2. Request Flow

### POST /shorten

1. FastAPI parses the body into URLRequest.
2. field_validator rejects URLs not starting with http:// or https://.
3. get_db() yields a SQLAlchemy session.
4. The handler queries for an existing original_url.
   - If found: return the existing mapping (idempotent).
   - If not found: enter the short-code generation loop.
5. A 6-character code is generated with secrets.choice over [A-Za-z0-9].
6. The mapping is added and committed.
7. On IntegrityError (code collision), the transaction is rolled back
   and retried up to 3 times.
8. Response is shaped by URLResponse with short_url composed from the code.

### GET /{short_code}

1. Build cache key `url:{short_code}`.
2. Redis `GET` for the URL (with a 1s Python-level timeout).
3. If cache HIT:
   - Redis `RPUSH` the short_code onto `clicks:queue`.
   - Return RedirectResponse(url=cached_url, status_code=307).
   - **No SQLite I/O on this path.**
4. If cache MISS:
   - SELECT the mapping by `short_code` from SQLite.
   - If missing -> 404.
   - Redis `SET` the URL with TTL 3600s.
   - Redis `RPUSH` the click onto `clicks:queue`.
   - If the RPUSH fails (Redis down): fall back to a single atomic
     SQLite `UPDATE click_count = click_count + 1`.
   - Return RedirectResponse(url=..., status_code=307).
5. Redis failures are wrapped in a thread-pool future with a 1s
   deadline (see §9 for why this is needed on Windows).

### GET /analytics/{short_code}

1. SELECT the mapping by `short_code`.
2. If missing -> 404.
3. Count pending clicks for this code in the Redis queue (`LRANGE`
   filtered by matching short_code).
4. Return AnalyticsResponse with `click_count = db_count + pending`.

### Background worker — ClickFlushWorker

1. Runs in a daemon thread, started in the FastAPI lifespan handler.
2. Every 5 seconds:
   - LPOP up to 500 entries from `clicks:queue`.
   - Aggregate them by short_code into `{code: increment}`.
   - Apply all increments in one SQLite transaction using
     `UPDATE ... SET click_count = click_count + N`.
   - On failure, re-queue the popped items so no click is lost.
3. Uses a `session_factory` so tests can supply their own isolated DB.

## 3. Route Ordering Note

In main.py, GET /{short_code} is declared before
GET /analytics/{short_code}. Because /{short_code} matches a single
path segment and /analytics/{short_code} matches two, requests to
/analytics/abc do not collide — FastAPI matches the more specific
two-segment route.

This is currently correct but fragile. If a future single-segment
route is added (e.g. GET /stats), it must be declared before
GET /{short_code}, or the catch-all will intercept it.

Mitigation: consider converting the single-segment catch-all to a
prefix like /r/{short_code} in a future iteration. This is noted as a
design trade-off, not a bug. `/health` and `/ready` are two-segment
or explicit paths and do not collide.

## 4. Data Model

    url_mappings
    ---------------------------------------------
    id            INTEGER  PK
    original_url  VARCHAR  NOT NULL
    short_code    VARCHAR  NOT NULL  UNIQUE  INDEXED
    created_at    DATETIME default = now(UTC)
    click_count   INTEGER  default = 0

Design choices:

| Choice | Rationale |
|--------|-----------|
| short_code unique + indexed | Ensures lookup is O(log n) and prevents duplicates |
| short_code NOT NULL | A mapping without a code is invalid |
| created_at timezone-aware | Python 3.12 deprecates naive utcnow() |
| click_count on same row | Simple model; updated in batches by the worker |
| SQLite check_same_thread=False | Required because FastAPI serves across threads |

### Cache and Queue Model

| Key | Type | Purpose | TTL |
|-----|------|---------|-----|
| `url:{short_code}` | String | Cached original URL | 3600 s |
| `clicks:queue` | List | Pending click events (short codes) | none (drained every 5s) |

| Property | Value |
|----------|-------|
| Cache backend | Redis-compatible (Memurai for local dev, Redis for prod) |
| Failure mode | Fail-open — falls through to atomic DB increment on Redis outage |
| Consistency | Eventual for click_count (max 5s lag); analytics endpoint adds pending depth |
| Latency bound | 1s Python-level timeout via ThreadPoolExecutor |

## 5. Error Handling Strategy

| Failure | Response |
|---------|----------|
| Invalid URL | 422 from Pydantic (automatic) |
| Missing short code | 404 from explicit HTTPException |
| Code collision after 3 retries | 500 with a clear message |
| Any SQLAlchemyError | Rollback + 500 "Database error" |
| Redis unavailable on redirect | Fail-open: fall through to atomic DB increment |
| Redis unavailable on analytics | Pending count treated as 0; DB count still returned |
| Worker flush failure | Popped items re-queued so no click is lost |

All write paths roll back on failure, so partial state never persists.

## 6. How AI Tools Were Integrated

Copilot (Agent Mode) was used across the lifecycle, but always under
engineer review. Concrete touchpoints:

| Phase | AI Role | Engineer Role |
|-------|---------|---------------|
| Scaffolding | Generated database.py, models.py, schemas.py | Reviewed, corrected deprecated APIs, added constraints |
| Route logic | Generated main.py handlers | Reviewed retry loop, confirmed secrets usage, refactored startup to lifespan |
| Testing | Generated 7 pytest cases with fixtures | Diagnosed sys.path issue, chose python -m pytest; added 4 more tests |
| Debugging | Suggested fixes when tests failed | Verified fixes in the active venv, not Copilot's shell |
| Caching | Added Redis layer + cache-hit test | Reviewed fail-open behavior, verified cache writes |
| Queue design | Not generated — engineer-directed | Designed queue-based click tracking; measured 27.6x hot-path gain |
| Documentation | Assisted with phrasing | Authored the final narrative and validation story |

Key pattern: Copilot's runtime claims ("package not installed") were
cross-checked in the engineer's own terminal. Twice, Copilot reported a
missing dependency that was actually installed in the active venv.

**Specific case where an AI suggestion was rejected:** When adding the
fail-open timeout wrapper, Copilot generated the helper functions but
did not wire them into the redirect handler, and left the direct
`redis_client.get` calls in place. It also introduced an indentation
error on the replacement line. Both issues were caught by reading the
diff and running `python -m py_compile` — the fix is recorded in the
main.py section of AI_LOG.md with the specific evidence.

## 7. Design Trade-offs

| Decision | Alternative | Why this choice |
|----------|-------------|-----------------|
| SQLite | PostgreSQL | Zero-config dev; sufficient for prototype scope |
| secrets for codes | uuid4() truncated | Direct character-set control; easier to keep 6 chars |
| 6-char codes | 8-char codes | 62^6 ~= 5.6 x 10^10 space — adequate for demo scale |
| Inline click_count (batched) | Separate events table | Simpler model; queue already provides async batching |
| Dependency override in tests | Mock the DB | Real SQLite exercises actual SQL and constraints |
| Redis cache with fail-open | Fail-closed on Redis error | Redirects must keep working even if cache is down |
| 1-hour TTL on URL cache | Invalidate on write | Short codes are immutable so staleness is bounded |
| Queue-based clicks | Synchronous DB write on every hit | 27.6x hot-path speedup; analytics endpoint reads pending depth |

## 8. Route Reference

| Method | Path | Purpose |
|--------|------|---------|
| POST | /shorten | Create a short URL (idempotent) |
| GET | /{short_code} | Redirect to original URL (307), queue a click |
| GET | /analytics/{short_code} | Return click count (DB + pending) and metadata |
| GET | /health | Liveness probe — process is up |
| GET | /ready | Readiness probe — DB and Redis reachable |
| GET | /docs | Swagger UI (auto-generated) |
| GET | /openapi.json | OpenAPI schema (auto-generated) |

## 9. Scale Considerations

The assignment asks for a "scalable" URL shortener. This section
documents the scaling-relevant design choices and explicitly states
what was and was not measured.

### Design Choices That Support Scale

| Choice | Scale Benefit |
|--------|--------------|
| Index on `short_code` | O(log n) lookup vs. O(n) full scan |
| Unique constraint on `short_code` | Prevents duplicates at the DB layer, not app layer |
| Idempotent `POST /shorten` | Avoids unbounded duplicate rows for the same URL |
| Retry loop on `IntegrityError` | Handles code collisions without failing the request |
| `secrets` module for code generation | Uniform distribution across the keyspace, no hot spots |
| 6-char code over `[A-Za-z0-9]` | 62^6 ~= 5.6 x 10^10 possible codes |
| Dependency-injected session | Enables pooling / swap to a real pool in production |
| Stateless FastAPI handlers | Horizontally scalable behind a load balancer |
| Redis cache on redirect path | Removes the URL-lookup DB hit for hot codes |
| Queue-based click tracking | Removes the click-write DB hit from the hot path entirely |
| Batched atomic UPDATEs | Worker flushes many clicks in one transaction |

### Measured Cache Performance

The redirect path uses a **queue-based click design** so that hot-path
requests never touch the database:

- **Hot path (cache hit):** Redis `GET` for the URL, then Redis `RPUSH`
  to enqueue a click event. **No SQLite I/O.**
- **Cache miss:** SQLite `SELECT` for the URL, Redis `SET` to warm the
  cache, Redis `RPUSH` to enqueue the click.
- **Background worker:** every 5 seconds, pops up to 500 queued clicks,
  aggregates by short code, and applies atomic
  `UPDATE ... SET click_count = click_count + N` in one transaction.
- **Analytics endpoint:** returns the persisted `click_count` plus the
  pending queue depth for that code, so results are correct even between
  worker ticks.

Three paths were benchmarked (1,000 iterations each):

| Scenario | Avg (ms) | Median (ms) | P99 (ms) |
|----------|----------|-------------|----------|
| DB-only (pre-cache) | 8.07 | 7.58 | 13.25 |
| Cache + DB write (intermediate) | 7.74 | 7.38 | 10.96 |
| **Cache + queue (hot path)** | **0.29** | **0.27** | **0.56** |

**Hot-path speedup vs pre-cache: 27.6×.**

**Why this matters:** An earlier iteration cached the URL but still
performed a synchronous DB write to increment `click_count`. That
design only reduced latency from 8.07 ms to 7.74 ms — a ~4%
improvement, because the DB write dominated. Moving click tracking
to a Redis queue and draining it via a background worker removes the
DB write from the hot path entirely. The hot path now serves in
**0.29 ms on average, 27.6× faster than the pre-cache baseline.**

**Trade-off:** `click_count` in the database lags behind real clicks
by up to one worker interval (5 seconds). The analytics endpoint
compensates by summing the persisted count with the pending queue
depth, so the user-visible count is always current.

**Environment:** Windows, Python 3.12, SQLite 3, Memurai
(Redis-compatible, Redis 7 API), local loopback. Benchmark:
`benchmark.py`.

### What Was Not Measured

The prototype was **not** load tested at the HTTP layer (no concurrent
client simulation, no sustained RPS measurement). The benchmark above
measures single-threaded handler-path latency, which is the dominant
cost on the redirect path. HTTP-layer load testing is deferred to
productionization (see section 10).

### What Would Be Measured in Production

| Metric | Target (proposed) | How to Measure |
|--------|-------------------|----------------|
| P99 latency, POST /shorten | < 50 ms | APM (Datadog, New Relic) |
| P99 latency, GET /{code} | < 5 ms | APM |
| Sustained RPS per instance | 5,000+ | k6 / locust |
| Error rate | < 0.1% | APM + log aggregation |
| Collision retry rate | < 0.001% | Custom metric on IntegrityError |
| Cache hit rate | > 90% | Redis INFO stats |
| Queue depth | < 1,000 | Redis LLEN on `clicks:queue` |

### Known Bottlenecks at Higher Scale

1. **SQLite single-writer lock** — becomes a bottleneck above ~100 writes/sec.
   *Mitigation:* swap to PostgreSQL (see section 10).
2. **Worker flush cadence** — clicks are batched every 5 seconds, so
   the persisted count lags slightly behind real traffic. For higher
   throughput, scale horizontally by sharding the queue key
   (`clicks:queue:{shard}`) and running multiple workers, each owning
   a shard. Increments are already atomic, so no lost updates.
3. **Cache cold-start** — first lookup for a new code always hits the DB.
   *Mitigation:* warm the cache proactively on `POST /shorten`; consider
   a shared cache across instances (Redis is already in place).
4. **Single-region deployment** — no CDN or edge caching.
   *Mitigation:* read replicas + CDN for popular codes.

### Explicit Trade-Off Statement

The scale-relevant design choices are documented and **measured for the
backend path** (27.6× hot-path speedup over the pre-cache baseline).
HTTP-layer load testing is deferred to productionization. The design
correctness and validation story is complete; the remaining gap is
empirical throughput testing under concurrent HTTP load.

## 10. Productionization Gaps

If this were to move to production:

1. Database: swap SQLite for PostgreSQL; add Alembic migrations.
2. Base URL: move short_url construction to a config value.
3. Rate limiting: add per-IP throttling on POST /shorten.
4. Auth: API keys for create/analytics endpoints.
5. Analytics: event table with timestamp, user agent, referrer.
6. Observability: structured logging, metrics, tracing.
7. Route naming: prefix short-code routes (/r/{code}) to avoid
   the ordering fragility noted in section 3.
8. Caching: promote Redis from local Memurai to a managed Redis cluster;
   add cache-warming on POST /shorten and hit-rate monitoring.
9. Load testing: k6 or locust scripts to verify throughput targets.
10. Worker scaling: shard the click queue and run multiple workers.