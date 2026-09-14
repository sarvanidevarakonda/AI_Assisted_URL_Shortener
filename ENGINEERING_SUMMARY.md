# Engineering Summary

Candidate: Sarvani Devarakonda
Project: AI-Assisted URL Shortener
Deliverable: Interview Assignment — AI-Proficient Software Engineer
Date: 2026-09-14

---

## 1. Implementation Approach and Rationale

I built a URL shortener with three HTTP endpoints (POST /shorten,
GET /{short_code}, GET /analytics/{short_code}) using FastAPI,
SQLAlchemy, and SQLite. The design deliberately kept each concern in
its own module:

- database.py — engine and session lifecycle
- models.py — persistent entity
- schemas.py — request/response contracts
- main.py — routing and orchestration

GitHub Copilot (Agent Mode) generated the first draft of each file. I
then reviewed every line, corrected deprecated APIs, added missing
constraints, and validated behavior with a 7-test pytest suite that
uses per-test database isolation.

The intent was not to maximize AI output — it was to demonstrate that
AI accelerates while the engineer retains ownership. That ownership
is visible in AI_LOG.md, which records the prompt used for each
component, what Copilot produced, and what I changed.

## 2. Generated Artifacts

| Artifact | Purpose |
|----------|---------|
| database.py | SQLAlchemy engine, SessionLocal, Base, get_db() |
| models.py | URLMapping table with indexed, unique short_code |
| schemas.py | Pydantic v2 models with URL validation |
| main.py | FastAPI app with lifespan handler and 3 endpoints |
| tests/test_main.py | 7 endpoint tests with temp DB per test |
| AI_LOG.md | Per-file prompt/output/validation record |
| ARCHITECTURE.md | System design, AI integration, trade-offs |
| SCENARIOS.md | Greenfield / brownfield / ambiguous walkthroughs |
| README.md | Setup, API reference, testing instructions |

## 3. Validation Approach

Three layers of validation:

Static:
- py_compile on every file
- Editor diagnostics
- git diff --check for whitespace

Runtime:
- Import check for each module
- Base.metadata.create_all() confirmed the table was created
- sqlite_master inspection confirmed the schema

Behavioral:
- 7 pytest cases covering valid/invalid input, idempotency, redirect
  status + location, analytics increment, and 404 paths
- Manual curl tests during development

Final state: 7 passed, 2 warnings in ~1.7s. The two remaining
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

**What is not measured:**
- No load test, benchmark, or throughput measurement was performed.
- No latency targets were verified against the running service.

**Why:**
Time was allocated to correctness, validation, and documentation
based on the assignment's emphasis on engineering execution under
AI assistance, rather than performance engineering.

**What would be measured if this were productionized:**
- P99 latency for both POST /shorten and GET /{short_code}
- Sustained RPS per instance
- Error rate under load
- Collision retry rate

See `ARCHITECTURE.md` §9 for details.

**Honest limitation:** A reviewer looking for empirical scalability
evidence will not find it here. The scale-relevant design is
documented and defensible; the measurements are not claimed.

### 3b. Validation Evidence

Every claim in this summary is backed by a specific observation from
running the code. Evidence is listed here so a reviewer can verify
each claim independently.

| Claim | How It Was Verified | Observed Result |
|-------|---------------------|-----------------|
| Test suite passes | `python -m pytest tests/ -v` | `7 passed, 2 warnings in ~1.5s` |
| Database table created | `Base.metadata.create_all()` at startup; `sqlite_master` query | `[('url_mappings',)]` |
| Index on `short_code` | Introspection: `URLMapping.short_code.index` | `True` |
| Unique constraint | Introspection: `URLMapping.short_code.unique` | `True` |
| Not nullable | Introspection: `URLMapping.short_code.nullable` | `False` |
| URL validation rejects bad input | `POST /shorten` with `{"original_url": "notaurl"}` | `422` with `"must start with http:// or https://"` |
| Idempotent creation | `POST /shorten` twice with same URL | Same `short_code` both times |
| Redirect works | Server log during manual test | `"GET /u7o6u1 HTTP/1.1" 307` |
| Analytics increments | `GET /analytics/{code}` after one redirect | `click_count: 1` |
| 404 for unknown code | `GET /zzzzzz` | `404` with `{"detail": "Short URL not found"}` |
| Redirect counter increments per request | Two requests → analytics check | `click_count: 2` |
| OpenAPI metadata documents 307/404 | `/docs` after `responses=` addition | Swagger UI shows both status codes |

**Note on the redirect via Swagger:** Swagger's "Execute" button
triggers a CORS block when the endpoint returns a 307 to an external
domain. The 307 is verified via the browser address bar and `curl -I`
instead. This is documented in `README.md`.

## 4. Risks and Mitigation

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random codes | Security | secrets module (not random) |
| Duplicate URL creation | Functional | Idempotent lookup by original_url |
| Short-code collision | Functional | Retry loop (3x) on IntegrityError |
| Missing short-code index | Performance | index=True on short_code |
| SQLite thread-safety | Runtime | check_same_thread=False |
| Deprecated datetime.utcnow | Maintainability | Replaced with datetime.now(timezone.utc) |
| Deprecated @app.on_event | Maintainability | Refactored to @asynccontextmanager lifespan |
| Test DB contamination | Test isolation | Dependency override with temp SQLite |
| pytest import failure | Build | Use python -m pytest (adds repo root to path) |
| Copilot runtime misdiagnosis | AI-related | Cross-check every "not installed" claim in the active venv |

## 5. AI-Related Risks Observed

Two concrete failure modes emerged during the build:

1. Copilot reported a missing dependency that was installed.
   Twice, Copilot Agent Mode claimed SQLAlchemy or Pydantic was not
   installed. pip show proved both were present in the active venv.
   Copilot's terminal context does not always inherit the venv, so its
   runtime claims are not authoritative. Mitigation: always re-run
   the check in the engineer's own terminal before acting on it.

2. Copilot emitted deprecated APIs.
   Copilot used datetime.utcnow() and @app.on_event("startup"), both
   deprecated in the current Python / FastAPI. Mitigation: treat AI
   output as a draft; review against current idioms; refactor.

Neither issue was fatal, but both illustrate why ownership cannot be
delegated to the AI.

## 6. Assumptions and Limitations

- SQLite is used for simplicity; production would use PostgreSQL.
- Short URLs are hardcoded to http://localhost:8000.
- No authentication, rate limiting, or abuse protection.
- Analytics is a single integer click_count — no time-series.
- No custom aliases, expiry, or link deactivation.
- The single-segment route /{short_code} would need reordering or a
  prefix if more single-segment routes are added later.
- Two upstream deprecation warnings remain (Starlette/httpx, anyio).

## 7. What Success Looks Like (Self-Assessment)

Against the assignment's own success criteria:

| Criterion | Evidence |
|-----------|----------|
| Effective use of AI tools | AI_LOG.md — prompt, output, and review per file |
| Strength of software design | Layered modules, indexed model, Pydantic validation |
| Quality and correctness | 7/7 tests pass; manual curl verified |
| Demonstrated ownership | Every AI output reviewed; deprecated APIs corrected |
| Validation rigor | Static + runtime + behavioral validation documented |
| Clarity and defensibility | Four docs + log; every choice has a rationale |
| Controlled autonomy | Engineer-led decomposition; AI execution per task |

## 8. Final Reflection

Copilot was genuinely useful — it produced working scaffolds for each
module in minutes, which let me spend more time on review and
validation than on typing. But every meaningful decision (index
placement, timezone-aware timestamps, lifespan refactor, test
isolation, route ordering) was made by the engineer, not the AI.

The log is the artifact I'd point to first: it records the exact
prompts, the exact outputs, and the exact corrections — a paper trail
that makes the ownership claim verifiable rather than asserted.

AI assists the engineer within tasks; the engineer owns execution
and quality. This project is my attempt to demonstrate that in a
small, reviewable package.