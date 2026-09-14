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
             |
             | SQLAlchemy ORM
             v
    SQLite Database
      url_mappings
        id, original_url, short_code,
        created_at, click_count

### Layer Responsibilities

| Layer | File | Responsibility |
|-------|------|----------------|
| HTTP / routing | main.py | Request parsing, route logic, response shaping |
| Validation | schemas.py | Request/response contracts, input sanitization |
| Domain model | models.py | Persistent entity + ORM mapping |
| Persistence | database.py | Engine, session factory, session lifecycle |
| Tests | tests/test_main.py | Endpoint behavior + isolation |

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

1. Look up the mapping by short_code.
2. If missing -> 404.
3. Increment click_count, commit.
4. Return RedirectResponse(url=..., status_code=307).

### GET /analytics/{short_code}

1. Look up the mapping by short_code.
2. If missing -> 404.
3. Return AnalyticsResponse.model_validate(mapping) — reads directly
   from the SQLAlchemy object via from_attributes=True.

## 3. Route Ordering Note

In main.py, GET /{short_code} is declared before
GET /analytics/{short_code}. Because /{short_code} matches a single
path segment and /analytics/{short_code} matches two, requests to
/analytics/abc do not collide — FastAPI matches the more specific
two-segment route.

This is currently correct but fragile. If a future single-segment
route is added (e.g. GET /health or GET /stats), it must be declared
before GET /{short_code}, or the catch-all will intercept it.

Mitigation: consider converting the single-segment catch-all to a
prefix like /r/{short_code} in a future iteration. This is noted as a
design trade-off, not a bug.

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
| click_count on same row | Avoids a separate events table for a prototype |
| SQLite check_same_thread=False | Required because FastAPI serves across threads |

## 5. Error Handling Strategy

| Failure | Response |
|---------|----------|
| Invalid URL | 422 from Pydantic (automatic) |
| Missing short code | 404 from explicit HTTPException |
| Code collision after 3 retries | 500 with a clear message |
| Any SQLAlchemyError | Rollback + 500 "Database error" |

All write paths roll back on failure, so partial state never persists.

## 6. How AI Tools Were Integrated

Copilot (Agent Mode) was used across the lifecycle, but always under
engineer review. Concrete touchpoints:

| Phase | AI Role | Engineer Role |
|-------|---------|---------------|
| Scaffolding | Generated database.py, models.py, schemas.py | Reviewed, corrected deprecated APIs, added constraints |
| Route logic | Generated main.py handlers | Reviewed retry loop, confirmed secrets usage, refactored startup to lifespan |
| Testing | Generated 7 pytest cases with fixtures | Diagnosed sys.path issue, chose python -m pytest over code changes |
| Debugging | Suggested fixes when tests failed | Verified fixes in the active venv, not Copilot's shell |
| Documentation | Assisted with phrasing | Authored the final narrative and validation story |

Key pattern: Copilot's runtime claims ("package not installed") were
cross-checked in the engineer's own terminal. Twice, Copilot reported a
missing dependency that was actually installed in the active venv. This
is documented in AI_LOG.md as a known Copilot limitation.

## 7. Design Trade-offs

| Decision | Alternative | Why this choice |
|----------|-------------|-----------------|
| SQLite | PostgreSQL | Zero-config dev; sufficient for prototype scope |
| secrets for codes | uuid4() truncated | Direct character-set control; easier to keep 6 chars |
| 6-char codes | 8-char codes | 62^6 ~= 5.6x10^10 space — adequate for demo scale |
| Inline click_count | Separate events table | Simpler model; meets "analytics" requirement |
| Dependency override in tests | Mock the DB | Real SQLite exercises actual SQL and constraints |

## 8. Productionization Gaps

If this were to move to production:

1. Database: swap SQLite for PostgreSQL; add Alembic migrations.
2. Base URL: move short_url construction to a config value.
3. Rate limiting: add per-IP throttling on POST /shorten.
4. Auth: API keys for create/analytics endpoints.
5. Analytics: event table with timestamp, user agent, referrer.
6. Observability: structured logging, metrics, tracing.
7. Route naming: prefix short-code routes (/r/{code}) to avoid
   the ordering fragility noted in section 3.