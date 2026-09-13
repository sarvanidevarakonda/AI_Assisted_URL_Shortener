# Project: AI-Assisted URL Shortener

## Tech Stack
- Backend: Python (FastAPI)
- Database: SQLite (SQLAlchemy)
- Testing: pytest

## Coding Standards
- Follow PEP 8 style guidelines.
- Include docstrings for all public functions and API endpoints.
- Write unit tests for all new logic using pytest.
- Use `secrets` module for generating short codes, not `random`.

## Project Structure
- `main.py`: FastAPI application entry point and routes.
- `models.py`: SQLAlchemy database models.
- `schemas.py`: Pydantic request/response models.
- `database.py`: Database connection and session setup.
- `tests/`: All test files.

## Rules
- Always handle edge cases (invalid URLs, missing parameters).
- Do not use external libraries unless absolutely necessary.