# AI-Assisted URL Shortener

A production-style URL shortener service built as a demonstration of
AI-assisted software engineering. The project shows how GitHub Copilot
was used as a development accelerator while the engineer retained full
ownership of design, validation, and code quality.

## Features

- Create short URLs from long URLs via `POST /shorten`
- Idempotent: submitting the same URL twice returns the same short code
- 6-character codes generated with Python's `secrets` module (cryptographically secure)
- Collision handling with up to 3 retries on `IntegrityError`
- `GET /{short_code}` redirects (307) to the original URL and increments click count
- `GET /analytics/{short_code}` returns click count and metadata
- Input validation via Pydantic (rejects non-http/https URLs)
- Full pytest suite with per-test database isolation

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Validation | Pydantic v2 |
| Database | SQLite (dev); production would use PostgreSQL |
| Testing | pytest + FastAPI TestClient |
| AI tooling | GitHub Copilot (Agent Mode) |

## Project Structure

AI_Assisted_URL_Shortener/
├── .github/
│   └── copilot-instructions.md   # Project context for Copilot
├── .gitignore
├── AI_LOG.md                     # Per-file AI assistance log
├── README.md                     # This file
├── ARCHITECTURE.md               # System design and AI integration
├── SCENARIOS.md                  # Greenfield / brownfield / ambiguous examples
├── ENGINEERING_SUMMARY.md        # Final summary and reflections
├── database.py                   # SQLAlchemy engine, session, Base
├── models.py                     # URLMapping model
├── schemas.py                    # Pydantic request/response models
├── main.py                       # FastAPI app and endpoints
├── requirements.txt
├── tests/
│   ├── __init__.py
│   └── test_main.py              # 7 endpoint tests
└── shortener.db                  # SQLite DB (gitignored, created on first run)

## Setup

### 1. Clone and enter the project

    git clone <your-repo-url>
    cd AI_Assisted_URL_Shortener

### 2. Create and activate a virtual environment

Windows (PowerShell):

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

macOS / Linux:

    python -m venv .venv
    source .venv/bin/activate

### 3. Install dependencies

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

If requirements.txt is out of date, install directly:

    python -m pip install "fastapi[standard]" sqlalchemy pydantic pytest httpx

## Running the Service

Start the development server:

    fastapi dev main.py

or:

    uvicorn main:app --reload

The service listens on http://localhost:8000. Interactive API docs are
available at http://localhost:8000/docs.

The SQLite file shortener.db and the url_mappings table are created
automatically on first startup via the FastAPI lifespan handler.

## API Reference

### POST /shorten

Create a short URL. If the original URL already exists, the existing
short code is returned (idempotent).

Request:

    { "original_url": "https://example.com/very/long/path" }

Response (200):

    {
      "short_code": "aB3xY9",
      "short_url": "http://localhost:8000/aB3xY9",
      "original_url": "https://example.com/very/long/path"
    }

Errors:
- 422 — original_url missing or does not start with http:// / https://
- 500 — database error or unable to generate a unique code after 3 retries

### GET /{short_code}

Redirect to the original URL (HTTP 307) and increment the click count.

Errors:
- 404 — short code not found
- 500 — database error

### GET /analytics/{short_code}

Return click metadata for a short code.

Response (200):

    {
      "original_url": "https://example.com/very/long/path",
      "short_code": "aB3xY9",
      "click_count": 3,
      "created_at": "2026-09-14T10:23:11.482913+00:00"
    }

Errors:
- 404 — short code not found
- 500 — database error

## Testing

Run the full test suite:

    python -m pytest tests/ -v

Expected result:

    tests/test_main.py::test_shorten_valid_url PASSED
    tests/test_main.py::test_shorten_idempotent PASSED
    tests/test_main.py::test_shorten_invalid_url PASSED
    tests/test_main.py::test_redirect_valid_code PASSED
    tests/test_main.py::test_redirect_invalid_code PASSED
    tests/test_main.py::test_analytics_increments PASSED
    tests/test_main.py::test_analytics_invalid_code PASSED

    7 passed, 2 warnings

Note: Use python -m pytest (not bare pytest) so the project root
is added to sys.path and main.py is importable from the test module.

### Test Isolation

Each test uses a fresh temporary SQLite database via a dependency
override on get_db. The production shortener.db is never touched.

### Warnings

The two remaining warnings originate from Starlette / httpx / anyio
internals and are upstream, not project code. See ENGINEERING_SUMMARY.md
for details.

## Known Limitations

- SQLite used for simplicity; concurrent writes in production would
  require PostgreSQL or another server-grade DB.
- Short URL base is hardcoded to http://localhost:8000.
- No authentication, rate limiting, or abuse protection.
- Analytics limited to a total click count (no time-series, referrer, or
  geography data).
- No custom aliases or link expiration yet.

## License

Created as an interview assignment submission.