"""
Benchmark: compare three paths through the redirect handler.

1. DB-only (pre-cache)        SELECT + UPDATE click_count
2. Redis cache + DB write     Redis GET + UPDATE click_count
3. Redis cache + queue         Redis GET + rpush only (production hot path)

Path 3 is the hot path in the new design: no DB touch at all. Path 1 is
the pre-cache baseline. Path 2 is the intermediate design (cache for URL,
synchronous DB write for the click).

All three use the same short_code. 1,000 iterations per scenario.
"""

import statistics
import time

import redis
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from models import URLMapping

ITERATIONS = 1000
SQLALCHEMY_DATABASE_URL = "sqlite:///./shortener.db"

redis_client = redis.Redis(
    host="localhost", port=6379, db=0, decode_responses=True,
    socket_connect_timeout=1, socket_timeout=1,
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_sample_code() -> str:
    db = SessionLocal()
    try:
        row = db.query(URLMapping).first()
        if row is None:
            raise SystemExit("No rows. Create a short URL first.")
        return row.short_code
    finally:
        db.close()


def time_db_only(code: str, n: int) -> list:
    """SELECT + UPDATE — the pre-cache baseline."""
    db = SessionLocal()
    times = []
    try:
        for _ in range(n):
            t0 = time.perf_counter()
            db.query(URLMapping).filter(URLMapping.short_code == code).first()
            db.execute(
                update(URLMapping)
                .where(URLMapping.short_code == code)
                .values(click_count=URLMapping.click_count + 1)
            )
            db.commit()
            times.append((time.perf_counter() - t0) * 1000)
    finally:
        db.close()
    return times


def time_cache_db_write(code: str, n: int) -> list:
    """Redis GET for the URL + synchronous DB UPDATE for the click."""
    key = f"url:{code}"
    if redis_client.get(key) is None:
        redis_client.set(key, "https://example.com", ex=3600)

    db = SessionLocal()
    times = []
    try:
        for _ in range(n):
            t0 = time.perf_counter()
            redis_client.get(key)
            db.execute(
                update(URLMapping)
                .where(URLMapping.short_code == code)
                .values(click_count=URLMapping.click_count + 1)
            )
            db.commit()
            times.append((time.perf_counter() - t0) * 1000)
    finally:
        db.close()
    return times


def time_cache_queue(code: str, n: int) -> list:
    """Redis GET for the URL + RPUSH to the click queue. No DB touch."""
    key = f"url:{code}"
    if redis_client.get(key) is None:
        redis_client.set(key, "https://example.com", ex=3600)

    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        redis_client.get(key)
        redis_client.rpush("clicks:bench", code)
        times.append((time.perf_counter() - t0) * 1000)
    redis_client.delete("clicks:bench")
    return times


def summarize(label: str, samples: list) -> dict:
    s = sorted(samples)
    return {
        "label": label,
        "avg": statistics.mean(samples),
        "med": statistics.median(samples),
        "p99": s[int(0.99 * len(s)) - 1],
        "min": min(s),
        "max": max(s),
    }


def main() -> None:
    code = get_sample_code()
    print(f"Short code: {code}")
    print(f"Iterations: {ITERATIONS}\n")

    db_only = time_db_only(code, ITERATIONS)
    cache_db = time_cache_db_write(code, ITERATIONS)
    cache_q = time_cache_queue(code, ITERATIONS)

    header = f"{'Scenario':<30} {'Avg':>8} {'Med':>8} {'P99':>8} {'Min':>8} {'Max':>8}"
    print(header)
    print("-" * len(header))
    for s in (
        summarize("DB-only (pre-cache)", db_only),
        summarize("Cache + DB write", cache_db),
        summarize("Cache + queue (hot path)", cache_q),
    ):
        print(f"{s['label']:<30} {s['avg']:>8.3f} {s['med']:>8.3f} "
              f"{s['p99']:>8.3f} {s['min']:>8.3f} {s['max']:>8.3f}")

    print(f"\nHot-path speedup vs pre-cache: "
          f"{statistics.mean(db_only) / statistics.mean(cache_q):.1f}x")
    print("(All values in milliseconds)")


if __name__ == "__main__":
    main()