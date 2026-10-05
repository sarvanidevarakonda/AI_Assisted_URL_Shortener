import concurrent.futures
import json
import logging
import secrets
import string
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import Base, engine, get_db, redis_client
from models import URLMapping
from schemas import AnalyticsResponse, URLRequest, URLResponse


# ---------- Structured logging ----------

class JsonFormatter(logging.Formatter):
    """Minimal structured logger - one JSON object per line."""

    def format(self, record):
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_logging() -> logging.Logger:
    logger = logging.getLogger("url_shortener")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


logger = _configure_logging()


# ---------- Redis helpers with hard timeout ----------

_redis_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _redis_call_with_timeout(func, *args, timeout: float = 1.0, **kwargs):
    """Run a Redis call in a worker thread with a Python-level deadline."""
    try:
        future = _redis_pool.submit(func, *args, **kwargs)
        return future.result(timeout=timeout)
    except Exception:
        return None


def _redis_get(key: str, timeout: float = 1.0):
    return _redis_call_with_timeout(redis_client.get, key, timeout=timeout)


def _redis_set(key: str, value: str, ttl: int, timeout: float = 1.0) -> None:
    _redis_call_with_timeout(redis_client.set, key, value, ex=ttl, timeout=timeout)


def _redis_rpush(key: str, value: str, timeout: float = 1.0):
    return _redis_call_with_timeout(redis_client.rpush, key, value, timeout=timeout)


# Queue of pending click events. Drained by the background worker.
CLICK_QUEUE_KEY = "clicks:queue"


# ---------- Background worker ----------

class ClickFlushWorker:
    """Drains pending click events from Redis into SQLite in batches.

    Runs in a daemon thread. Every `interval` seconds, pops up to
    `batch_size` entries from the queue, aggregates by short_code, and
    applies the increments in a single transaction.

    Accepts an optional `session_factory` so tests can supply their own
    database session (the app's default is `database.SessionLocal`).
    """

    def __init__(self, interval: float = 5.0, batch_size: int = 500,
                 session_factory=None):
        self.interval = interval
        self.batch_size = batch_size
        self._stop = False
        self._thread = None
        if session_factory is None:
            from database import SessionLocal
            session_factory = SessionLocal
        self._session_factory = session_factory

    def start(self) -> None:
        def run():
            while not self._stop:
                try:
                    self._flush_once()
                except Exception as exc:
                    logger.info(f"worker flush error: {exc}")
                time.sleep(self.interval)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _flush_once(self) -> None:
        """Pop up to batch_size entries and apply them in one transaction."""
        popped = []
        for _ in range(self.batch_size):
            item = _redis_call_with_timeout(
                redis_client.lpop, CLICK_QUEUE_KEY, timeout=1.0
            )
            if item is None:
                break
            popped.append(item)

        if not popped:
            return

        counts: dict[str, int] = {}
        for code in popped:
            counts[code] = counts.get(code, 0) + 1

        db = self._session_factory()
        try:
            for code, inc in counts.items():
                db.execute(
                    update(URLMapping)
                    .where(URLMapping.short_code == code)
                    .values(click_count=URLMapping.click_count + inc)
                )
            db.commit()
            logger.info(
                f"worker flushed clicks={len(popped)} codes={len(counts)}"
            )
        except Exception:
            db.rollback()
            for code in popped:
                try:
                    redis_client.rpush(CLICK_QUEUE_KEY, code)
                except Exception:
                    pass
            raise
        finally:
            db.close()


# ---------- App lifecycle ----------

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create database tables and start the click-flush worker."""
    Base.metadata.create_all(bind=engine)
    worker = ClickFlushWorker()
    worker.start()
    logger.info("app startup complete")
    try:
        yield
    finally:
        worker.stop()
        logger.info("app shutdown complete")


app = FastAPI(lifespan=lifespan)


# ---------- Rate limiting ----------

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------- Response helpers ----------

def _build_url_response(mapping: URLMapping) -> URLResponse:
    return URLResponse(
        short_code=mapping.short_code,
        short_url=f"http://localhost:8000/{mapping.short_code}",
        original_url=mapping.original_url,
    )


# ---------- Endpoints ----------

@app.post(
    "/shorten",
    response_model=URLResponse,
    responses={
        422: {"description": "Invalid URL format"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Database error or unable to generate a unique code"},
    },
)
@limiter.limit("20/minute")
def shorten_url(
    request: Request,
    url_request: URLRequest,
    db: Session = Depends(get_db),
) -> URLResponse:
    """Create a short URL or return the existing mapping for the original URL."""
    try:
        existing_mapping = (
            db.query(URLMapping)
            .filter(URLMapping.original_url == url_request.original_url)
            .first()
        )
        if existing_mapping is not None:
            logger.info(f"shorten existing code={existing_mapping.short_code}")
            return _build_url_response(existing_mapping)

        alphabet = string.ascii_letters + string.digits
        for _ in range(3):
            mapping = URLMapping(
                original_url=url_request.original_url,
                short_code="".join(secrets.choice(alphabet) for _ in range(6)),
            )
            db.add(mapping)
            try:
                db.commit()
                db.refresh(mapping)
                logger.info(f"shorten created code={mapping.short_code}")
                return _build_url_response(mapping)
            except IntegrityError:
                db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to generate a unique short code",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.info(f"shorten db_error: {exc}")
        raise HTTPException(status_code=500, detail="Database error") from exc


@app.get(
    "/{short_code}",
    responses={
        307: {"description": "Redirect to the original URL"},
        404: {"description": "Short URL not found"},
    },
)
def redirect_to_original(short_code: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect to the original URL and record a click event.

    Cache hit path (the common case): Redis GET + rpush into the click
    queue. No SQLite touch on the hot path. The background worker
    drains the queue in batches and applies atomic increments.

    Cache miss path: DB lookup + cache write + rpush. Rare for hot codes.

    Fail-open: if Redis is unreachable, fall through to an atomic DB
    UPDATE so the redirect still works and the click is still counted.
    """
    try:
        cache_key = f"url:{short_code}"

        cached_url = _redis_get(cache_key, timeout=1.0)

        if cached_url is not None:
            _redis_rpush(CLICK_QUEUE_KEY, short_code, timeout=1.0)
            logger.info(f"redirect cache_hit code={short_code}")
            return RedirectResponse(url=cached_url, status_code=307)

        mapping = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .first()
        )
        if mapping is None:
            logger.info(f"redirect not_found code={short_code}")
            raise HTTPException(status_code=404, detail="Short URL not found")

        _redis_set(cache_key, mapping.original_url, ttl=3600, timeout=1.0)
        logger.info(f"redirect cache_miss code={short_code}")

        rpush_ok = _redis_call_with_timeout(
            redis_client.rpush, CLICK_QUEUE_KEY, short_code, timeout=1.0
        )
        if rpush_ok is None:
            db.execute(
                update(URLMapping)
                .where(URLMapping.short_code == short_code)
                .values(click_count=URLMapping.click_count + 1)
            )
            db.commit()
            logger.info(f"redirect redis_down_db_fallback code={short_code}")

        return RedirectResponse(url=mapping.original_url, status_code=307)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.info(f"redirect db_error: {exc}")
        raise HTTPException(status_code=500, detail="Database error") from exc


@app.get(
    "/analytics/{short_code}",
    response_model=AnalyticsResponse,
    responses={
        404: {"description": "Short URL not found"},
    },
)
def get_analytics(short_code: str, db: Session = Depends(get_db)) -> AnalyticsResponse:
    """Return analytics for a shortened URL.

    Reads click_count from the DB and adds the pending (not yet flushed)
    count for this code from Redis, so results are correct even between
    worker ticks.
    """
    try:
        mapping = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .first()
        )
        if mapping is None:
            raise HTTPException(status_code=404, detail="Short URL not found")

        pending = _pending_clicks_for(short_code)
        response = AnalyticsResponse.model_validate(mapping)
        response.click_count = mapping.click_count + pending
        logger.info(
            f"analytics code={short_code} db={mapping.click_count} pending={pending}"
        )
        return response
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from exc


def _pending_clicks_for(short_code: str) -> int:
    """Count pending clicks for a code currently sitting in the Redis queue."""
    items = _redis_call_with_timeout(
        redis_client.lrange, CLICK_QUEUE_KEY, 0, -1, timeout=1.0
    )
    if not items:
        return 0
    return sum(1 for item in items if item == short_code)


# ---------- Health / readiness ----------

@app.get("/health")
def health():
    """Liveness probe: process is up and can serve requests."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: DB and Redis are both reachable."""
    from database import SessionLocal
    db_ok = False
    redis_ok = False

    try:
        db = SessionLocal()
        db.execute(update(URLMapping).where(URLMapping.id == -1))
        db.close()
        db_ok = True
    except Exception:
        db_ok = False

    try:
        redis_ok = bool(_redis_call_with_timeout(redis_client.ping, timeout=1.0))
    except Exception:
        redis_ok = False

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {"status": status, "db": db_ok, "redis": redis_ok}