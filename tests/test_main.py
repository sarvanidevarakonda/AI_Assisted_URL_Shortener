import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import Base, get_db


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