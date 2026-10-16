# AI Ownership Evidence

This document ties specific AI-related claims in `AI_LOG.md` and
`ENGINEERING_SUMMARY.md` to visible diffs, test results, and
repeatable commands. Each entry is independently reviewable.

---

## Example 1: Copilot generated unwired helpers (rejected + fixed)

**AI suggestion:** Copilot created the timeout helper functions
`_redis_get_with_timeout` and `_redis_set_with_timeout` in `main.py`,
but left the redirect handler calling `redis_client.get` directly.
The helpers existed but were never invoked.

**Problem found:** During a real Redis outage test, redirects took
**52 seconds** — proof the timeout wrapper wasn't active.

**Fix:** Changed `cached_url = redis_client.get(cache_key)` to
`cached_url = _redis_get_with_timeout(cache_key, timeout=1.0)`.

**Evidence:** The test stubs Redis to raise on `get`, then asserts the
redirect still returns 307. This is the exact scenario that took 52
seconds before the timeout wrapper was wired in.

    python -m pytest tests/test_main.py::test_redirect_fails_open_when_redis_is_down -v

Expected: `PASSED`.

---

## Example 2: Deprecated datetime API corrected

**AI suggestion:** Copilot used `datetime.utcnow()` in the model,
which is deprecated in Python 3.12.

**Problem found:** Python 3.12 emits a `DeprecationWarning` for
`datetime.utcnow()`.

**Fix:** Replaced with `datetime.now(timezone.utc)`.

**Evidence:**

    python -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc))"

Expected: a timezone-aware ISO timestamp.

---

## Example 3: `socket_connect_timeout` insufficient on Windows

**AI suggestion:** Copilot added `socket_connect_timeout=1` to the
Redis client.

**Problem found:** Windows does not honor this for TCP SYN retries
when the target port is unreachable. During a real Memurai outage,
redirects took 52 seconds.

**Fix:** Wrapped every Redis call in a `ThreadPoolExecutor` future
with a Python-level deadline of 1 second, so fail-open latency is
bounded regardless of OS socket behavior.

**Evidence (manual):**

    # Stop Memurai (Admin PowerShell):
    Stop-Service Memurai

    # Time the redirect:
    Measure-Command { curl.exe -s -o NUL http://localhost:8000/u7o6u1 }

    # Restart Memurai:
    Start-Service Memurai

Expected: ~1-2 seconds, not 52.

---

## Example 4: Cache didn't actually save a DB round-trip (design changed)

**AI suggestion:** Copilot's initial Redis cache still performed a
synchronous DB `UPDATE` for `click_count` on every cache hit.

**Problem found:** Benchmarking showed only ~4% improvement over the
pre-cache path — because the DB write dominated. The cache wasn't
doing its job.

**Fix:** Cache-hit path now does Redis `GET` + Redis `RPUSH` only,
with no DB touch. A background worker drains the click queue every
5 seconds and applies batched atomic increments.

**Evidence (benchmark):**

    python benchmark.py

Expected output:

    Scenario                          Avg (ms)   Median (ms)   P99 (ms)
    -------------------------------------------------------------------
    DB-only (pre-cache)               8.1-25.8   7.6-11.2      13-247
    Cache + DB write (intermediate)   7.7-24.7   7.4-10.9      11-245
    Cache + queue (hot path)          0.3-0.6    0.3-0.6       0.6-1.0

    Hot-path speedup vs pre-cache: 27.6x - 40.8x across two runs.

**Evidence (test):**

    python -m pytest tests/test_main.py::test_concurrent_clicks_are_counted_correctly -v

Expected: `PASSED` (20 parallel redirects produce exactly 20 clicks after flush).

---

## Example 5: Concurrent duplicate-creation race (caught by new test)

**Context:** The client asked for a test that fires simultaneous
duplicate `POST /shorten` calls to prove the endpoint is idempotent
under concurrency.

**What the test found:** The test **failed on first run**. Ten
concurrent POSTs for the same URL produced **three different
short_codes and three duplicate rows** in the database. Two requests
had raced past the idempotent pre-check and each inserted a new row
before the others saw the committed data.

**Root cause:** The `original_url` column had no unique constraint.
The idempotency check was app-level only (`SELECT` then `INSERT`), and
that pattern is inherently racy without a DB constraint backing it.

**Fix:**
1. Added `unique=True, index=True` to `URLMapping.original_url` in
   `models.py`.
2. Extended the `IntegrityError` handler in `shorten_url` to re-query
   and return the existing mapping when the collision was on
   `original_url` (vs a short_code collision, which retries).

**Evidence:**

    python -m pytest tests/test_main.py::test_simultaneous_duplicate_creation_returns_same_code -v

Expected: `PASSED`. The test also asserts exactly one row exists in
the DB for the raced URL.

**Why this matters:** The reviewer's feedback explicitly asked for this
test. Writing it surfaced a real correctness bug that would have
silently created duplicate rows under concurrent load. The test
remains in the suite to guard against regression.

---

## Example 6: `/metrics` bypassed the test DB (caught by CI)

**Context:** After adding the `/metrics` endpoint, all tests passed
locally. CI failed with:

    sqlite3.OperationalError: no such table: url_mappings

**Root cause:** The `/metrics` handler imported `SessionLocal` from
`database` and used it directly instead of the FastAPI dependency
`get_db`. Because the test suite overrides `get_db` to point at an
isolated temp DB, the direct `SessionLocal()` call bypassed the
override and hit the (nonexistent) production DB on the CI runner.

The `/ready` endpoint had the same problem in principle, but its
`SELECT 1` check doesn't reference a table, so it happened to pass.

**Fix:** Changed both handlers to accept `db: Session = Depends(get_db)`:

    @app.get("/ready")
    def ready(db: Session = Depends(get_db)): ...

    @app.get("/metrics")
    def metrics(db: Session = Depends(get_db)): ...

**Evidence:**

    python -m pytest tests/test_main.py::test_metrics_reflect_test_database -v

Expected: `PASSED`. The test creates one short URL, then asserts
`shortener_urls_total 1` appears in the metrics body. This can only
be true if `/metrics` reads from the test DB (via the dependency
override), not the production DB.

**Why this matters:** This bug was invisible locally because a
`./shortener.db` file existed on the developer machine. CI runs on a
clean runner with no such file, so the direct `SessionLocal()` call
failed. This is a concrete example of why the reviewer's request for
a **reproducible environment / CI** matters — environment-specific
bugs only surface when you run in a clean environment.

---

## How to Verify This Entire Document

    git clone https://github.com/sarvanidevarakonda/AI_Assisted_URL_Shortener.git
    cd AI_Assisted_URL_Shortener
    python -m venv .venv
    # Windows:
    .\.venv\Scripts\Activate.ps1
    # macOS/Linux:
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python -m pytest tests/ -v          # expect 23 passed, 0 warnings
    python benchmark.py                 # expect ~0.3 ms hot path

Every claim above is reproducible with the commands shown.