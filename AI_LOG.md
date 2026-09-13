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

**Status:** IN PROGRESS — not yet started

---

## Component: `schemas.py`

**Status:** NOT STARTED

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

---

## Key Risks Identified and Mitigated

| Risk | Category | Mitigation |
|------|----------|------------|
| Weak random code generation | Security | (planned) force `secrets` module in main.py |
| Duplicate URL creation | Functional | (planned) idempotent check in POST /shorten |
| SQLite thread-safety | Runtime | `check_same_thread=False` set in database.py |
| Missing dependency | Build | Added SQLAlchemy to requirements.txt |

---

## Assumptions and Limitations

- SQLite used for simplicity; production would use PostgreSQL.
- No authentication / rate limiting implemented yet.
- [Add more as you go]

---

## Final Notes

All AI-generated outputs were reviewed line-by-line before acceptance.
Full ownership of the final codebase rests with the candidate.