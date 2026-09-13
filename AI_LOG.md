# AI Assistance Log

**Project:** AI-Assisted URL Shortener Service  
**Candidate:** Sarvani Devarakonda  
**AI Tool:** GitHub Copilot (Agent Mode)  
**Date Started:** 2026-09-13

---

## Purpose

This log documents how GitHub Copilot was used across the project: the prompts
issued, the outputs generated, my review of each output, and how correctness
was validated. It serves as evidence of AI-assisted engineering under full
human ownership.

---

## Workflow Summary

For each component:
1. Wrote a specific prompt in Copilot Agent Mode.
2. Reviewed Copilot's output against engineering standards.
3. Accepted, modified, or rejected the output.
4. Validated via import check and/or tests.
5. Logged the result below.

---

## Component: `.github/copilot-instructions.md`

**Prompt used:** N/A — authored directly.

**Purpose:** Provides project context to Copilot (tech stack, standards, rules).

**My review:** Confirmed rules align with assignment requirements
(cryptographic randomness, test coverage, edge cases).

**Validation:** N/A (configuration only).

---

## Component: `database.py`

**Prompt used:**
> "Create a file called database.py for SQLAlchemy with SQLite.
> It should:
> - Create an engine connected to 'sqlite:///./shortener.db'
> - Set connect_args={'check_same_thread': False}
> - Create a SessionLocal sessionmaker
> - Define a Base class
> - Provide a get_db() dependency function that yields a session"

**Copilot output summary:**
- Generated engine, SessionLocal, Base, and get_db() as requested.
- Used `declarative_base()` from `sqlalchemy.ext.declarative`.

**My review and changes:**
- Verified `check_same_thread=False` is set (required for SQLite + FastAPI).
- Verified `get_db()` uses try/finally to close sessions.
- No functional changes needed.

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import database"`): initially FAILED —
  SQLAlchemy not installed.
- Resolution: ran `pip install sqlalchemy`, re-ran import → PASS.
- Updated `requirements.txt` to reflect new dependency.
- Tests: N/A (no logic yet)

---

## Component: `models.py`

**Prompt used:**
> "Create a file called models.py with a SQLAlchemy model called URLMapping.
> Import Base from database.
> Columns:
> - id: Integer, primary key
> - original_url: String, not null
> - short_code: String, unique, indexed
> - created_at: DateTime, default=datetime.utcnow
> - click_count: Integer, default=0
> Add a __repr__ method for debugging."

**Copilot output summary:**
- Generated the URLMapping class with all requested columns and __repr__.
- Used `datetime.utcnow` as the default for `created_at`.
- `short_code` had `unique=True` and `index=True` but not `nullable=False`.
- Left a stray `created_at = Column(...)` line at the top of the file, outside any class.

**My review and changes:**
- Removed the stray top-level `created_at` line (would raise NameError on import).
- Added `from datetime import datetime, timezone` — missing from Copilot's output.
- Replaced deprecated `datetime.utcnow` with `datetime.now(timezone.utc)`.
- Added `nullable=False` to `short_code` (a short code must always exist).

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import models"`): PASS
- Introspection check: `URLMapping.short_code.unique=True`, `index=True`, `nullable=False`
- Tests: N/A (model only; will be exercised in test_main.py)
---

## Component: `schemas.py`

**Prompt used:**
> "Create a file called schemas.py with Pydantic models for the URL shortener.
> Use Pydantic v2 syntax.
>
> Models needed:
> 1. URLRequest:
>    - original_url: str
>    - A field_validator that ensures the URL starts with 'http://' or 'https://'
>    - If invalid, raise ValueError with a clear message
> 2. URLResponse:
>    - short_code: str
>    - short_url: str
>    - original_url: str
> 3. AnalyticsResponse:
>    - original_url: str
>    - short_code: str
>    - click_count: int
>    - created_at: datetime
>
> Use model_config = ConfigDict(from_attributes=True) where appropriate
> so Pydantic can read from SQLAlchemy objects."

**Copilot output summary:**
- Generated URLRequest, URLResponse, AnalyticsResponse with Pydantic v2 syntax.
- URLRequest includes a field_validator for http:// and https://.
- Response models use ConfigDict(from_attributes=True).

**My review and changes:**
- Verified Pydantic v2 imports (`field_validator`, `ConfigDict`), no v1 `@validator`.
- Validator correctly rejects strings not starting with http:// or https://.
- No functional changes needed.

**Validation:**
- Syntax check: PASS
- Runtime import (`python -c "import schemas"`): PASS
- Valid URL (`https://example.com`): PASS — model constructed
- Invalid URL (`notaurl`): PASS — raised ValidationError with custom message

**Note on Copilot limitation:**
- Copilot Agent Mode reported "Pydantic not installed" during its own
  runtime check, but `pip show pydantic` confirmed v2.13.5 was installed
  in the active venv. Copilot's terminal context does not always inherit
  the venv, so its runtime claims are not authoritative. Verified manually.

---

## Component: `main.py`

**Status:** NOT STARTED

---

## Component: `tests/test_main.py`

**Status:** NOT STARTED

---

## Version Control Setup

**Action:** Initialized Git repository and made first commit.

**Files tracked:**
- `.gitignore`
- `.github/copilot-instructions.md`
- `AI_LOG.md`
- `database.py`
- `requirements.txt`

**Files excluded (via .gitignore):**
- `.venv/` (virtual environment)
- `__pycache__/` (Python bytecode cache)
- `*.db` (local SQLite database)

**Commit:** `Initial commit: database.py, AI log, project setup`

**Validation:** `git log --oneline` shows commit; `git status` shows clean tree.

---

## Summary of AI Outputs Accepted / Modified / Rejected

| Component | Accepted as-is | Modified | Rejected | Notes |
|-----------|---------------|----------|----------|-------|
| database.py | ✅ | | | |
| models.py | | ✅ | | fixed deprecated API + added nullable constraint |
| schemas.py | ✅ | | | |

---

## Key Risks Identified and Mitigated

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random code generation | Security | (planned) force `secrets` module in main.py |
| Duplicate URL creation | Functional | (planned) idempotent check in POST /shorten |
| SQLite thread-safety | Runtime | `check_same_thread=False` set in database.py |
| Missing dependency | Build | Added SQLAlchemy to requirements.txt |
| Deprecated `datetime.utcnow` | Maintainability | Replaced with `datetime.now(timezone.utc)` |
| Invalid URL input | Functional | Pydantic field_validator rejects non-http(s) URLs |

---

## Assumptions and Limitations

- SQLite used for simplicity; production would use PostgreSQL.
- No authentication / rate limiting implemented yet.
- [Add more as you go]

---

## Final Notes

All AI-generated outputs were reviewed line-by-line before acceptance.
Full ownership of the final codebase rests with the candidate.