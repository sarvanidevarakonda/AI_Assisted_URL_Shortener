# Build a Scalable URL Shortener Service

## Source Requirement

> Build a scalable URL shortener service with APIs, persistence, and analytics.
> 
> Acceptance criteria:
> - Accept a long URL via HTTP and return a short code
> - Redirect the short code to the original URL
> - Persist mappings durably
> - Track click analytics per short code
> - Handle read-heavy load on the redirect path

---

## 1. Interpreted Problem

Deliver an HTTP service that accepts a long URL and returns a short code that redirects to the original. Persist mappings, track click analytics, and remain responsive under read-heavy load. The core concern is the redirect path: reads vastly outnumber writes.

## 2. Ambiguities and Assumptions

**Ambiguities identified:**

- How short is 'short'? (6 chars chosen: 62^6 ≈ 5.6×10^10 space)
- Should the same URL return the same code? (Yes — idempotent)
- Is analytics a total count or time-series? (Total count for v1)
- Authentication? (Not required for v1)
- Custom aliases? (Deferred to v2)

**Assumptions made:**

- SQLite is acceptable for the prototype; production would use PostgreSQL.
- Single-region deployment is acceptable for the prototype.
- Click counts can lag by up to a worker interval (5s) as long as the analytics endpoint reflects pending clicks.

## 3. Sequenced Tasks

| # | Task | Depends on | AI Assistance Point |
|---|------|-----------|---------------------|
| 1 | Define data model | - | Generate SQLAlchemy URLMapping model |
| 2 | Set up DB session lifecycle | 1 | Generate database.py engine + get_db |
| 3 | Define request/response schemas | 1 | Generate Pydantic v2 models |
| 4 | Implement POST /shorten | 2,3 | Generate idempotent create handler |
| 5 | Implement GET /{short_code} | 4 | Generate redirect + click tracking |
| 6 | Implement GET /analytics/{short_code} | 5 | Generate analytics handler |
| 7 | Add Redis cache + click queue | 5 | Generate cache helpers + worker skeleton |
| 8 | Write pytest suite | 4-7 | Generate test cases; engineer adds concurrency + fail-open |
| 9 | Add health/readiness probes | 4-7 | Generate /health and /ready |
| 10 | Benchmark hot vs cold path | 7 | Generate benchmark.py scaffold |

## 4. AI Assistance Points

Each task lists where AI assists. The engineer owns review,
validation, and integration — AI never commits unreviewed code.

| # | Task | What AI helps with |
|---|------|--------------------|
| 1 | Define data model | Generate SQLAlchemy URLMapping model |
| 2 | Set up DB session lifecycle | Generate database.py engine + get_db |
| 3 | Define request/response schemas | Generate Pydantic v2 models |
| 4 | Implement POST /shorten | Generate idempotent create handler |
| 5 | Implement GET /{short_code} | Generate redirect + click tracking |
| 6 | Implement GET /analytics/{short_code} | Generate analytics handler |
| 7 | Add Redis cache + click queue | Generate cache helpers + worker skeleton |
| 8 | Write pytest suite | Generate test cases; engineer adds concurrency + fail-open |
| 9 | Add health/readiness probes | Generate /health and /ready |
| 10 | Benchmark hot vs cold path | Generate benchmark.py scaffold |

## 5. Proposed Artifacts

| Artifact | Purpose |
|----------|---------|
| `database.py` | SQLAlchemy engine, SessionLocal, Base, get_db, redis_client |
| `models.py` | URLMapping table with indexed unique short_code |
| `schemas.py` | Pydantic v2 request/response contracts |
| `main.py` | FastAPI app with endpoints, cache, queue, worker |
| `benchmark.py` | Three-path latency comparison |
| `tests/test_main.py` | 12 tests: idempotency, cache, fail-open, concurrency, rate limit |
| `ARCHITECTURE.md` | System design + scale considerations |
| `ENGINEERING_SUMMARY.md` | Validation evidence + risks + reflection |

## 6. Acceptance Checks

- [ ] POST /shorten returns 200 with short_code, short_url, original_url
- [ ] POST /shorten with same URL twice returns identical short_code
- [ ] POST /shorten with non-http(s) URL returns 422
- [ ] GET /{code} returns 307 with Location header
- [ ] GET /{code} for unknown code returns 404
- [ ] GET /analytics/{code} returns click_count that increases on redirects
- [ ] 20 concurrent redirects produce click_count == 20 after flush
- [ ] Hot path (cache + queue) completes in < 1ms avg over 1000 iterations
- [ ] Rate limit returns 429 after 20 requests/minute
- [ ] Fail-open path completes in < 2s when Redis is down

## 7. Risks and Mitigations

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random codes | Security | Use secrets module; never random() |
| Duplicate URL rows | Functional | Idempotent lookup by original_url |
| Short-code collision | Functional | Retry loop on IntegrityError |
| DB write on hot path | Performance | Queue clicks; flush in batches |
| Redis outage | Availability | Fail-open to atomic DB increment; 1s thread-pool timeout |
| Worker loses clicks on crash | Data integrity | Re-queue popped items on flush failure |
| Copilot generates unwired helpers | AI-related | Read the diff; verify calls; py_compile |

---

_Generated by `workflow.py`. This tool is engineer-led: it produces_
_structure, not decisions. All content is reviewed before use._
