"""
Benchmark: Redis cache hit vs SQLite lookup for URL shortener redirects.

Measures per-lookup latency for the same short_code over N iterations.
The SQLite query mirrors what GET /{short_code} does on a cache miss.
The Redis lookup mirrors a cache hit.
"""

import statistics
import time

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import URLMapping

# Config
ITERATIONS = 1000
SQLALCHEMY_DATABASE_URL = "sqlite:///./shortener.db"

# Connect to Redis (Memurai)
redis_client = redis.Redis(
    host="localhost", port=6379, db=0, decode_responses=True
)

# Connect to SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_sample_code() -> str:
    """Pick any existing short_code from the DB, or fall back to a known one."""
    db = SessionLocal()
    try:
        row = db.query(URLMapping).first()
        if row is None:
            raise SystemExit(
                "No rows in url_mappings. Create a short URL first via /shorten."
            )
        return row.short_code
    finally:
        db.close()


def time_sqlite(code: str, iterations: int) -> list:
    """Measure SQLite lookup latency per call (ms)."""
    db = SessionLocal()
    times = []
    try:
        for _ in range(iterations):
            start = time.perf_counter()
            db.query(URLMapping).filter(
                URLMapping.short_code == code
            ).first()
            times.append((time.perf_counter() - start) * 1000)
    finally:
        db.close()
    return times


def time_redis(code: str, iterations: int) -> list:
    """Measure Redis lookup latency per call (ms)."""
    key = f"url:{code}"
    # Ensure the key exists for a fair comparison
    if redis_client.get(key) is None:
        redis_client.set(key, "https://example.com", ex=3600)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        redis_client.get(key)
        times.append((time.perf_counter() - start) * 1000)
    return times


def summarize(label: str, samples: list) -> dict:
    """Return avg, median, p99 for a list of millisecond samples."""
    samples_sorted = sorted(samples)
    return {
        "label": label,
        "avg_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "p99_ms": samples_sorted[int(0.99 * len(samples_sorted)) - 1],
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


def main() -> None:
    code = get_sample_code()
    print(f"Using short_code: {code}")
    print(f"Iterations per backend: {ITERATIONS}\n")

    sqlite_samples = time_sqlite(code, ITERATIONS)
    redis_samples = time_redis(code, ITERATIONS)

    sqlite_stats = summarize("SQLite", sqlite_samples)
    redis_stats = summarize("Redis  ", redis_samples)

    header = f"{'Backend':<10} {'Avg (ms)':>10} {'Median':>10} {'P99':>10} {'Min':>8} {'Max':>8}"
    print(header)
    print("-" * len(header))
    for s in (sqlite_stats, redis_stats):
        print(
            f"{s['label']:<10} "
            f"{s['avg_ms']:>10.3f} "
            f"{s['median_ms']:>10.3f} "
            f"{s['p99_ms']:>10.3f} "
            f"{s['min_ms']:>8.3f} "
            f"{s['max_ms']:>8.3f}"
        )

    speedup = sqlite_stats["avg_ms"] / redis_stats["avg_ms"]
    print(f"\nAverage speedup: {speedup:.1f}x (SQLite avg / Redis avg)")


if __name__ == "__main__":
    main()