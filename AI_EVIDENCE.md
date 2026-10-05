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

**Evidence:**

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

**Evidence:**

    python benchmark.py

Expected output:

    Scenario                          Avg (ms)   Median (ms)   P99 (ms)
    -------------------------------------------------------------------
    DB-only (pre-cache)               8.07       7.58          13.25
    Cache + DB write (intermediate)   7.74       7.38          10.96
    Cache + queue (hot path)          0.29       0.27          0.56

    Hot-path speedup vs pre-cache: 27.6x

**Evidence (test):**

    python -m pytest tests/test_main.py::test_concurrent_clicks_are_counted_correctly -v

Expected: `PASSED` (20 parallel redirects produce exactly 20 clicks after flush).

---

## How to Verify This Entire Document

    git clone https://github.com/sarvanidevarakonda/AI_Assisted_URL_Shortener.git
    python -m pip install -r requirements.txt
    python -m pytest tests/ -v          # expect 18 passed
    python benchmark.py                 # expect ~0.3 ms hot path

Every claim above is reproducible with the commands shown.