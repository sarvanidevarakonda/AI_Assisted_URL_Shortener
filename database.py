import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import REDIS_DB, REDIS_HOST, REDIS_PORT


SQLALCHEMY_DATABASE_URL = "sqlite:///./shortener.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
# Redis client for the read-through cache on GET /{short_code}.
# The socket timeouts are a first line of defense; main.py additionally
# wraps Redis calls in a thread-pool future with timeout=1.0 because
# Windows does not always honor socket timeouts when the port is
# unreachable (TCP SYN retries can exceed the configured timeout).

from config import REDIS_HOST, REDIS_PORT, REDIS_DB

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


def get_db():
    """Yield a database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()