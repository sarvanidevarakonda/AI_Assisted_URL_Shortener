
# Example Scenarios

This document demonstrates how the AI-assisted workflow handled three
classes of requirement: greenfield, brownfield, and ambiguous.
Each scenario shows task decomposition, AI-assisted execution, and output
validation.

---

## Scenario 1 — Greenfield: Build the URL Shortener Core

### Requirement
"Build a scalable URL shortener service with APIs, persistence, and analytics."

### Task Decomposition

| # | Task | Depends on |
|---|------|------------|
| 1 | Define data model (URLMapping) | — |
| 2 | Set up database session lifecycle (database.py) | 1 |
| 3 | Define request/response schemas | 1 |
| 4 | Implement POST /shorten | 2, 3 |
| 5 | Implement GET /{short_code} redirect | 4 |
| 6 | Implement GET /analytics/{short_code} | 5 |
| 7 | Write pytest suite | 4-6 |
| 8 | Fix deprecation warnings | 4-6 |

### AI-Assisted Execution

- Prompt for Task 1: asked Copilot to generate a SQLAlchemy model
  with the required columns and constraints.
- Prompt for Task 4: asked for POST /shorten with idempotency,
  secrets-based generation, and collision retries.
- Prompt for Task 7: listed 7 explicit test cases with fixtures.

### Output Validation

| Task | Validation |
|------|-----------|
| 1 | python -c "import models"; introspected short_code.unique/index/nullable |
| 2 | python -c "import database"; Base.metadata.create_all() created the table |
| 3 | Valid URL constructed; invalid URL raised ValidationError |
| 4 | Manual curl: 200 + short_code; duplicate URL returned same code |
| 5 | Manual curl -I: 307 + correct location header |
| 6 | Manual curl: click_count incremented after redirect |
| 7 | python -m pytest tests/ -v -> 7 passed |
| 8 | Warning count dropped from 4 -> 2 (remaining are upstream) |

### Engineer Corrections to AI Output

- Removed a stray top-level created_at = Column(...) line Copilot left
  outside the class.
- Added missing from datetime import datetime, timezone import.
- Replaced deprecated datetime.utcnow() with timezone-aware now(UTC).
- Added nullable=False to short_code.

---

## Scenario 2 — Brownfield: Add Post-Startup Deprecation Refactor

### Requirement
"The service works, but pytest emits a deprecation warning from our
own main.py for @app.on_event("startup"). Modernize it without
changing behavior."

### Task Decomposition

| # | Task | Depends on |
|---|------|------------|
| 1 | Identify the source of the warning | — |
| 2 | Refactor startup to lifespan handler | 1 |
| 3 | Re-run full test suite | 2 |
| 4 | Confirm the warning disappeared | 3 |

### AI-Assisted Execution

- Prompt: "Refactor main.py to replace @app.on_event("startup")
  with a FastAPI lifespan context manager. Use @asynccontextmanager
  and pass lifespan=lifespan to FastAPI(). Call
  Base.metadata.create_all(bind=engine) inside the lifespan before
  yield. Do not change any endpoints."

### Output Validation

Before:

    7 passed, 4 warnings in 2.24s
      main.py:17  DeprecationWarning: on_event is deprecated

After:

    7 passed, 2 warnings in 1.70s
      (only .venv\Lib\site-packages\... warnings remain)

- Behavior unchanged: all 7 tests still pass.
- Warning from project code eliminated.
- Remaining warnings traced to site-packages, not project files.

### Engineer Corrections to AI Output

None — Copilot produced a correct lifespan refactor on the first pass.
The engineer verified it by diffing the warning counts and confirming
that no endpoint behavior changed.

---

## Scenario 3 — Ambiguous: "Make It Scale"

### Requirement
"Make the shortener scale better."

This requirement contains no acceptance criteria — it must be normalized
into an engineering problem.

### Requirement Clarification

| Ambiguity | Interpretation chosen | Rationale |
|-----------|----------------------|-----------|
| "Scale" how? | Short-code lookup performance | Most frequent operation |
| "Better" than what? | Current behavior is correct but un-indexed in some paths | Index on short_code is the biggest lever |
| Latency target? | Not specified — propose a measurable target | Choose "lookup < 5ms on dev hardware" |
| Scope | Just the lookup path, not DB migration | Keep the change small and verifiable |

Normalized engineering problem: "Ensure short-code lookups are
backed by a database index so lookups remain O(log n) as the table
grows."

### Task Decomposition

| # | Task | Depends on |
|---|------|------------|
| 1 | Confirm the current schema has an index on short_code | — |
| 2 | Add index=True if missing | 1 |
| 3 | Verify via sqlite_master | 2 |
| 4 | Re-run tests | 3 |

### AI-Assisted Execution

- Prompt: "Does URLMapping.short_code currently have an index?
  If not, add index=True. Do not change anything else."

### Output Validation

- URLMapping.short_code.index returned True.
- sqlite_master showed a unique index on short_code.
- All 7 tests continued to pass.

### Outcome

This ambiguity was already resolved during the greenfield build —
the index was added on the original model. The scenario demonstrates
the process: an ambiguous requirement became a concrete, verifiable
engineering task, with AI assisting only the mechanical part
(checking and confirming the index).

### Engineer Judgment Call

Rather than adding speculative caching or sharding (which the ambiguous
requirement could be read to imply), the engineer scoped the change to
the highest-value, lowest-risk lever: the index. Anything larger would
require explicit acceptance criteria and load testing before it could
be justified. This is a deliberate trade-off documented for the reviewer.

---

## Summary Table

| Scenario | Type | AI Role | Engineer Role |
|----------|------|---------|---------------|
| 1. Core build | Greenfield | Generated code | Reviewed, corrected deprecated APIs, validated end-to-end |
| 2. Lifespan refactor | Brownfield | Proposed refactor | Verified no behavior change, measured warning delta |
| 3. "Make it scale" | Ambiguous | Confirmed index state | Normalized requirement, scoped the change, rejected speculation |