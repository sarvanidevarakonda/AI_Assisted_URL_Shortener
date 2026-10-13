import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import main
from database import Base, get_db
from models import URLMapping


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear slowapi's in-memory state between tests.

    Without this, rate-limit counters accumulate across the test session
    and unrelated tests start failing with 429.
    """
    try:
        from main import limiter
        limiter.reset()
    except (ImportError, AttributeError):
        pass
    yield
    try:
        from main import limiter
        limiter.reset()
    except (ImportError, AttributeError):
        pass


class FakeRedis:
    """In-memory stub for redis_client.

    Supports get/set/rpush/lpop/llen/lrange so the queue-based click
    path works under test. Pass `preload={key: value}` to simulate
    warm cache hits.
    """

    def __init__(self, preload=None):
        self.store = dict(preload or {})
        self.set_calls = []
        self.queues: dict[str, list] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.set_calls.append((key, value, ex))

    def rpush(self, key, *values):
        self.queues.setdefault(key, []).extend(values)
        return len(self.queues[key])

    def lpop(self, key):
        q = self.queues.get(key, [])
        if not q:
            return None
        return q.pop(0)

    def llen(self, key):
        return len(self.queues.get(key, []))

    def lrange(self, key, start, end):
        q = self.queues.get(key, [])
        if end == -1:
            return q[start:]
        return q[start:end + 1]

    def ping(self):
        return True


@pytest.fixture
def test_database(tmp_path):
    """Create an isolated SQLite database for one test.

    Yields the session factory so tests that drive a background worker
    can point it at the same isolated database.
    """
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    original_engine = main.engine
    main.engine = engine
    main.app.dependency_overrides[get_db] = override_get_db
    try:
        yield session_local
    finally:
        main.app.dependency_overrides.clear()
        main.engine = original_engine
        engine.dispose()


@pytest.fixture
def fake_redis(monkeypatch):
    """Replace main.redis_client with an in-memory stub for every test."""
    stub = FakeRedis()
    monkeypatch.setattr(main, "redis_client", stub)
    return stub


@pytest.fixture
def client(test_database, fake_redis):
    """Provide a TestClient backed by the isolated test database and fake cache."""
    with TestClient(main.app) as test_client:
        yield test_client


# ---------- POST /shorten ----------

def test_shorten_valid_url(client):
    response = client.post("/shorten", json={"original_url": "https://example.com"})

    assert response.status_code == 200
    payload = response.json()
    assert "short_code" in payload
    assert "short_url" in payload
    assert payload["original_url"] == "https://example.com"


def test_shorten_idempotent(client):
    url = "https://example.com"

    first_response = client.post("/shorten", json={"original_url": url})
    second_response = client.post("/shorten", json={"original_url": url})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["short_code"] == second_response.json()["short_code"]


def test_shorten_invalid_url(client):
    response = client.post("/shorten", json={"original_url": "notaurl"})

    assert response.status_code == 422


def test_shorten_rejects_url_without_host(client):
    """'https://' alone has no host — must be rejected."""
    response = client.post("/shorten", json={"original_url": "https://"})
    assert response.status_code == 422


def test_shorten_rejects_url_with_whitespace(client):
    """'https://exa mple.com' has a space — must be rejected."""
    response = client.post("/shorten", json={"original_url": "https://exa mple.com"})
    assert response.status_code == 422


def test_shorten_rejects_url_without_dot_in_host(client):
    """'https://notadomain' has no dot and isn't localhost — must be rejected."""
    response = client.post("/shorten", json={"original_url": "https://notadomain"})
    assert response.status_code == 422


def test_shorten_accepts_localhost(client):
    """localhost is explicitly allowed for development."""
    response = client.post(
        "/shorten", json={"original_url": "http://localhost:8000/path"}
    )
    assert response.status_code == 200
    assert "short_code" in response.json()


def test_shorten_accepts_url_with_port_and_path(client):
    """A full URL with port, path, query, and fragment should be accepted."""
    url = "https://example.com:8443/a/b?x=1&y=2#frag"
    response = client.post("/shorten", json={"original_url": url})
    assert response.status_code == 200
    assert response.json()["original_url"] == url


def test_shorten_trims_leading_trailing_whitespace(client):
    """Whitespace on the edges is trimmed, not rejected."""
    response = client.post(
        "/shorten", json={"original_url": "  https://example.com  "}
    )
    assert response.status_code == 200
    assert response.json()["original_url"] == "https://example.com"


# ---------- GET /{short_code} ----------

def test_redirect_valid_code(client):
    url = "https://example.com"
    shorten_response = client.post("/shorten", json={"original_url": url})
    short_code = shorten_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == url


def test_redirect_cache_hit_uses_cached_url_and_increments_clicks(
    test_database, monkeypatch
):
    """Cache hit returns the cached URL without querying Redis.set again."""
    preloaded = FakeRedis(preload={"url:cached-code": "https://cached.example.com"})
    monkeypatch.setattr(main, "redis_client", preloaded)

    with TestClient(main.app) as client:
        response = client.post(
            "/shorten", json={"original_url": "https://example.com"}
        )
        short_code = response.json()["short_code"]

        # Force the cache key to match the preloaded one
        preloaded.store[f"url:{short_code}"] = "https://cached.example.com"

        redirect_response = client.get(
            f"/{short_code}", follow_redirects=False
        )
        analytics_response = client.get(f"/analytics/{short_code}")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "https://cached.example.com"
    # Cache hit path: click is queued, not yet in DB; analytics adds queue depth.
    assert analytics_response.json()["click_count"] == 1
    # Cache hit should NOT have triggered a new set() call
    assert preloaded.set_calls == []


def test_redirect_cache_miss_populates_cache(client, fake_redis):
    """First lookup populates the cache; second lookup uses it."""
    url = "https://example.com"
    shorten_response = client.post("/shorten", json={"original_url": url})
    short_code = shorten_response.json()["short_code"]

    assert fake_redis.get(f"url:{short_code}") is None  # cold cache

    first = client.get(f"/{short_code}", follow_redirects=False)
    assert first.status_code == 307
    assert fake_redis.get(f"url:{short_code}") == url  # cache populated
    assert len(fake_redis.set_calls) == 1

    second = client.get(f"/{short_code}", follow_redirects=False)
    assert second.status_code == 307
    assert len(fake_redis.set_calls) == 1  # no second set on hit


def test_redirect_fails_open_when_redis_is_down(client, monkeypatch):
    """If Redis raises on get(), the DB path still serves the redirect."""

    class BrokenRedis:
        def get(self, key):
            raise ConnectionError("Redis is down")

        def set(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

        def rpush(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

        def lpop(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

        def llen(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

        def lrange(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

        def ping(self, *args, **kwargs):
            raise ConnectionError("Redis is down")

    monkeypatch.setattr(main, "redis_client", BrokenRedis())

    url = "https://example.com"
    shorten_response = client.post("/shorten", json={"original_url": url})
    short_code = shorten_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == url


def test_redirect_invalid_code(client):
    response = client.get("/nonexistent")

    assert response.status_code == 404


# ---------- GET /analytics/{short_code} ----------

def test_analytics_increments(client):
    shorten_response = client.post(
        "/shorten", json={"original_url": "https://example.com"}
    )
    short_code = shorten_response.json()["short_code"]

    redirect_response = client.get(f"/{short_code}", follow_redirects=False)
    analytics_response = client.get(f"/analytics/{short_code}")

    assert redirect_response.status_code == 307
    assert analytics_response.status_code == 200
    assert analytics_response.json()["click_count"] == 1


def test_analytics_invalid_code(client):
    response = client.get("/analytics/nonexistent")

    assert response.status_code == 404


# ---------- Concurrency ----------

def test_concurrent_clicks_are_counted_correctly(client, test_database):
    """Fire 20 redirects in parallel; final count after flush is exactly 20.

    Exercises the queue-based click path under concurrency, then triggers
    an explicit flush against the same isolated DB and asserts the count.
    """
    import concurrent.futures
    from main import ClickFlushWorker

    url = "https://example.com/concurrent"
    shorten_response = client.post("/shorten", json={"original_url": url})
    short_code = shorten_response.json()["short_code"]

    def hit():
        return client.get(f"/{short_code}", follow_redirects=False).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: hit(), range(20)))

    assert all(code == 307 for code in results), f"Not all 307: {results}"

    # Force a flush so the DB reflects queued clicks immediately.
    # Point the worker at the same isolated DB the test is using.
    worker = ClickFlushWorker(session_factory=test_database)
    worker._flush_once()

    analytics = client.get(f"/analytics/{short_code}").json()
    assert analytics["click_count"] == 20, f"Expected 20, got {analytics['click_count']}"


def test_simultaneous_duplicate_creation_returns_same_code(client, test_database):
    """Fire 10 concurrent POST /shorten for the SAME URL.

    The unique constraint on original_url (added in response to this
    test) ensures only one row is created even under concurrent
    requests that all miss the idempotent pre-check. All successful
    responses must return the same short_code, and only one row must
    exist in the DB.
    """
    import concurrent.futures

    url = "https://example.com/duplicate-race"
    codes = []

    def create():
        r = client.post("/shorten", json={"original_url": url})
        if r.status_code == 200:
            codes.append(r.json()["short_code"])
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(lambda _: create(), range(10)))

    # All requests succeeded
    assert all(s == 200 for s in statuses), f"Not all 200: {statuses}"

    # All returned codes are identical (only one row was ever created).
    assert len(set(codes)) == 1, f"Expected one code, got {set(codes)}"

    # Verify exactly one row exists for this URL.
    db = test_database()
    try:
        count = (
            db.query(func.count(URLMapping.id))
            .filter(URLMapping.original_url == url)
            .scalar()
        )
        assert count == 1, f"Expected 1 row, found {count}"
    finally:
        db.close()


def test_short_code_collision_retries_and_succeeds(client, monkeypatch):
    """Force a first-attempt collision; the retry loop must succeed.

    We monkeypatch secrets.choice so the first 6 calls produce an
    already-used code, then fall through to the normal random source.
    The endpoint should survive the IntegrityError and complete with a
    different short_code.
    """
    import secrets as _secrets

    # Seed an existing mapping so we know which code is already taken.
    first = client.post(
        "/shorten", json={"original_url": "https://example.com/seed"}
    ).json()
    taken_code = first["short_code"]

    # Count how many times the endpoint tries to generate a code.
    original_choice = _secrets.choice
    call_log = {"count": 0}

    def patched_choice(alphabet):
        call_log["count"] += 1
        # For the first 6 calls (one full code), return chars from
        # taken_code so the generated code matches exactly.
        # After that, fall back to the real random source.
        if call_log["count"] <= 6:
            idx = call_log["count"] - 1
            return taken_code[idx]
        return original_choice(alphabet)

    monkeypatch.setattr(_secrets, "choice", patched_choice)

    # This request must NOT return 500. The retry loop should recover.
    response = client.post(
        "/shorten", json={"original_url": "https://example.com/collision-test"}
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    new_code = response.json()["short_code"]
    assert new_code != taken_code, "Retry should have produced a different code"


# ---------- Rate limiting ----------

def test_rate_limit_returns_429_after_quota(client):
    """20 requests allowed per minute; the 21st returns 429."""
    url_base = "https://example.com/rate-limit-test-"
    statuses = []
    for i in range(25):
        r = client.post("/shorten", json={"original_url": f"{url_base}{i}"})
        statuses.append(r.status_code)
    assert 429 in statuses, f"Expected a 429, got {statuses}"
    assert statuses.count(200) <= 20

def test_health_ready_metrics_are_reachable(client):
    """The probe endpoints must not be intercepted by the /{short_code} catch-all."""
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/metrics").status_code == 200
    body = client.get("/metrics").text
    assert "shortener_urls_total" in body
    assert "shortener_redis_up" in body
def test_ready_reports_db_and_redis(client):
    """/ready must report db=true and redis=true when both are reachable."""
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["db"] is True, f"Expected db=True, got {body}"
    assert body["redis"] is True, f"Expected redis=True, got {body}"