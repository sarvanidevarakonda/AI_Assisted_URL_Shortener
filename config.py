"""
Application configuration.

Values are read from environment variables with sensible defaults
for local development. In production, set these via the deployment
platform (Docker env, Kubernetes ConfigMap, Heroku config, etc.).
"""

import os


# Base URL used to compose short_url in API responses.
# Override with: export BASE_URL=https://sho.rt
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")


# Rate limit for POST /shorten (slowapi format).
RATE_LIMIT_SHORTEN: str = os.getenv("RATE_LIMIT_SHORTEN", "20/minute")


# Redis connection.
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))


# Cache TTL for URL entries (seconds).
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))