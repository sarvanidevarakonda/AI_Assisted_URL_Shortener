import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import Base, get_db


@pytest.fixture
def test_database(tmp_path):
    """Create an isolated SQLite database for one test."""
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
        yield
    finally:
        main.app.dependency_overrides.clear()
        main.engine = original_engine
        engine.dispose()


@pytest.fixture
def client(test_database):
    """Provide a TestClient backed by the isolated test database."""
    with TestClient(main.app) as test_client:
        yield test_client


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


def test_redirect_valid_code(client):
    url = "https://example.com"
    shorten_response = client.post("/shorten", json={"original_url": url})
    short_code = shorten_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == url


def test_redirect_cache_hit_uses_cached_url_and_increments_clicks(client, monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.set_calls = []

        def get(self, key):
            assert key.startswith("url:")
            return "https://cached.example.com"

        def set(self, *args, **kwargs):
            self.set_calls.append((args, kwargs))

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "redis_client", fake_redis)

    shorten_response = client.post(
        "/shorten", json={"original_url": "https://example.com"}
    )
    short_code = shorten_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)
    analytics_response = client.get(f"/analytics/{short_code}")

    assert response.status_code == 307
    assert response.headers["location"] == "https://cached.example.com"
    assert analytics_response.json()["click_count"] == 1
    assert fake_redis.set_calls == []


def test_redirect_invalid_code(client):
    response = client.get("/nonexistent")

    assert response.status_code == 404


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