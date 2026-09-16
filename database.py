import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


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

redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True,
    socket_connect_timeout=1,   # fail fast on connect
    socket_timeout=1,           # fail fast on read/write
)


def get_db():
    """Yield a database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()