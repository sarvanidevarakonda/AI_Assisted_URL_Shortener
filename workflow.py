"""
Requirement-to-Engineering Workflow Tool

Takes a software requirement (from a file or stdin) and produces a
structured engineering plan as markdown. The plan is engineer-led:
this tool does not generate code or run AI; it demonstrates how a
requirement is decomposed into tasks, AI-assistance points, artifacts,
acceptance checks, and risks.

Usage:
    python workflow.py example/url_shortener.txt
    python workflow.py example/url_shortener.txt --out plan.md
    echo "Add user login" | python workflow.py -
    python workflow.py --list

Design:
    Hybrid: built-in catalog of known requirement types, plus a
    generic fallback template for unknown example. This keeps
    output deterministic for the documented use cases while still
    being usable for any requirement.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------- Data model ----------

@dataclass
class Plan:
    title: str
    interpreted_problem: str
    ambiguities: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    tasks: list[tuple[str, str, str]] = field(default_factory=list)
    # tasks: (task_name, depends_on, ai_assistance_point)
    artifacts: list[tuple[str, str]] = field(default_factory=list)
    # artifacts: (name, purpose)
    acceptance_checks: list[str] = field(default_factory=list)
    risks: list[tuple[str, str, str]] = field(default_factory=list)
    # risks: (risk, category, mitigation)


# ---------- Catalog: known requirement patterns ----------

def _plan_url_shortener() -> Plan:
    return Plan(
        title="Build a Scalable URL Shortener Service",
        interpreted_problem=(
            "Deliver an HTTP service that accepts a long URL and returns a "
            "short code that redirects to the original. Persist mappings, "
            "track click analytics, and remain responsive under read-heavy "
            "load. The core concern is the redirect path: reads vastly "
            "outnumber writes."
        ),
        ambiguities=[
            "How short is 'short'? (6 chars chosen: 62^6 ≈ 5.6×10^10 space)",
            "Should the same URL return the same code? (Yes — idempotent)",
            "Is analytics a total count or time-series? (Total count for v1)",
            "Authentication? (Not required for v1)",
            "Custom aliases? (Deferred to v2)",
        ],
        assumptions=[
            "SQLite is acceptable for the prototype; production would use PostgreSQL.",
            "Single-region deployment is acceptable for the prototype.",
            "Click counts can lag by up to a worker interval (5s) as long as "
            "the analytics endpoint reflects pending clicks.",
        ],
        tasks=[
            ("Define data model", "-", "Generate SQLAlchemy URLMapping model"),
            ("Set up DB session lifecycle", "1", "Generate database.py engine + get_db"),
            ("Define request/response schemas", "1", "Generate Pydantic v2 models"),
            ("Implement POST /shorten", "2,3", "Generate idempotent create handler"),
            ("Implement GET /{short_code}", "4", "Generate redirect + click tracking"),
            ("Implement GET /analytics/{short_code}", "5", "Generate analytics handler"),
            ("Add Redis cache + click queue", "5", "Generate cache helpers + worker skeleton"),
            ("Write pytest suite", "4-7", "Generate test cases; engineer adds concurrency + fail-open"),
            ("Add health/readiness probes", "4-7", "Generate /health and /ready"),
            ("Benchmark hot vs cold path", "7", "Generate benchmark.py scaffold"),
        ],
        artifacts=[
            ("database.py", "SQLAlchemy engine, SessionLocal, Base, get_db, redis_client"),
            ("models.py", "URLMapping table with indexed unique short_code"),
            ("schemas.py", "Pydantic v2 request/response contracts"),
            ("main.py", "FastAPI app with endpoints, cache, queue, worker"),
            ("benchmark.py", "Three-path latency comparison"),
            ("tests/test_main.py", "12 tests: idempotency, cache, fail-open, concurrency, rate limit"),
            ("ARCHITECTURE.md", "System design + scale considerations"),
            ("ENGINEERING_SUMMARY.md", "Validation evidence + risks + reflection"),
        ],
        acceptance_checks=[
            "POST /shorten returns 200 with short_code, short_url, original_url",
            "POST /shorten with same URL twice returns identical short_code",
            "POST /shorten with non-http(s) URL returns 422",
            "GET /{code} returns 307 with Location header",
            "GET /{code} for unknown code returns 404",
            "GET /analytics/{code} returns click_count that increases on redirects",
            "20 concurrent redirects produce click_count == 20 after flush",
            "Hot path (cache + queue) completes in < 1ms avg over 1000 iterations",
            "Rate limit returns 429 after 20 requests/minute",
            "Fail-open path completes in < 2s when Redis is down",
        ],
        risks=[
            ("Weak random codes", "Security", "Use secrets module; never random()"),
            ("Duplicate URL rows", "Functional", "Idempotent lookup by original_url"),
            ("Short-code collision", "Functional", "Retry loop on IntegrityError"),
            ("DB write on hot path", "Performance", "Queue clicks; flush in batches"),
            ("Redis outage", "Availability", "Fail-open to atomic DB increment; 1s thread-pool timeout"),
            ("Worker loses clicks on crash", "Data integrity", "Re-queue popped items on flush failure"),
            ("Copilot generates unwired helpers", "AI-related", "Read the diff; verify calls; py_compile"),
        ],
    )


def _plan_brownfield_expiry() -> Plan:
    return Plan(
        title="Brownfield: Add Link Expiry to Existing URL Shortener",
        interpreted_problem=(
            "Extend the existing URL shortener with optional link expiration. "
            "Callers may supply an expires_at timestamp on POST /shorten; "
            "expired links must return 410 Gone on redirect, not 404. "
            "Existing endpoints must keep working unchanged."
        ),
        ambiguities=[
            "Should already-created links get a default expiry? (No — null means never expires)",
            "Is expiry checked on redirect only, or also on analytics? (Redirect only for v1)",
            "Should an expired link be deleted from the DB? (No — keep for audit; just refuse redirect)",
        ],
        assumptions=[
            "Schema change is acceptable; production would use Alembic but prototype uses create_all.",
            "No backfill is needed since existing rows default to null expiry.",
        ],
        tasks=[
            ("Add expires_at column to model", "-", "Generate SQLAlchemy nullable DateTime column"),
            ("Add expires_at to request schema", "1", "Generate optional Pydantic field"),
            ("Check expiry in GET /{short_code}", "2", "Generate 410 branch before redirect"),
            ("Add pytest coverage for expiry", "3", "Generate tests for future/past/missing expiry"),
            ("Update AI_LOG.md and ARCHITECTURE.md", "4", "Assist with phrasing"),
        ],
        artifacts=[
            ("models.py (modified)", "Add nullable expires_at column"),
            ("schemas.py (modified)", "Add optional expires_at to URLRequest"),
            ("main.py (modified)", "410 Gone branch on redirect for expired links"),
            ("tests/test_main.py (modified)", "3 new expiry tests"),
        ],
        acceptance_checks=[
            "POST /shorten without expires_at still works (no regression)",
            "POST /shorten with future expires_at returns 200",
            "GET /{code} before expiry returns 307",
            "GET /{code} after expiry returns 410 with a clear message",
            "Analytics still returns metadata for expired links",
        ],
        risks=[
            ("Regressing existing endpoints", "Functional", "Run the full existing test suite after change"),
            ("Timezone confusion on expiry comparison", "Correctness", "Store UTC; compare against datetime.now(timezone.utc)"),
        ],
    )


def _plan_ambiguous_scale() -> Plan:
    return Plan(
        title="Ambiguous: 'Make It Scale'",
        interpreted_problem=(
            "The requirement 'make it scale' has no acceptance criteria. "
            "Normalized interpretation: reduce redirect-path latency and DB "
            "load so the service handles a read-heavy workload without "
            "degrading. The highest-leverage lever is removing DB I/O from "
            "the hot path."
        ),
        ambiguities=[
            "Scale in what dimension? (Chose: read throughput on the redirect path)",
            "Target RPS? (Not specified — propose 5,000+ per instance as a design goal)",
            "Latency target? (Not specified — propose P99 < 5ms)",
            "Which bottleneck first? (Chose: DB write on cache hit, confirmed by benchmark)",
        ],
        assumptions=[
            "Analytics eventual consistency (up to 5s lag) is acceptable.",
            "Redis is available and can hold the working set of URLs.",
        ],
        tasks=[
            ("Baseline the current path", "-", "Generate benchmark scaffold"),
            ("Identify the real bottleneck", "1", "Interpret results: DB write dominated"),
            ("Design the cache + queue change", "2", "Engineer-led; AI assists with worker scaffold"),
            ("Implement queue-based click tracking", "3", "Generate worker skeleton; engineer wires it"),
            ("Measure the improvement", "4", "Re-run benchmark; record numbers"),
            ("Add a concurrency test", "4", "Generate thread-pool test; engineer verifies count"),
        ],
        artifacts=[
            ("main.py (modified)", "Cache + queue + background worker"),
            ("benchmark.py", "Three-path comparison script"),
            ("tests/test_main.py (modified)", "Concurrent-click test"),
            ("ARCHITECTURE.md §9", "Measured cache + queue performance"),
        ],
        acceptance_checks=[
            "Hot-path avg latency < 1ms over 1000 iterations",
            "20 concurrent redirects produce exactly 20 clicks after flush",
            "Analytics reflects pending queue depth between worker ticks",
            "All pre-existing tests still pass",
        ],
        risks=[
            ("Eventual consistency surprises users", "Product", "Analytics adds queue depth to DB count"),
            ("Worker fails silently", "Operational", "Re-queue popped items; log flush errors"),
            ("Over-engineering beyond the ask", "Scope", "Normalize the ambiguous requirement to one measurable goal first"),
        ],
    )


CATALOG: dict[str, Callable[[], Plan]] = {
    "url shortener": _plan_url_shortener,
    "url_shortener": _plan_url_shortener,
    "shorten url": _plan_url_shortener,
    "link expiry": _plan_brownfield_expiry,
    "expiration": _plan_brownfield_expiry,
    "make it scale": _plan_ambiguous_scale,
    "make it scalable": _plan_ambiguous_scale,
}


# ---------- Generic fallback ----------

def _plan_generic(requirement: str) -> Plan:
    first_line = requirement.strip().splitlines()[0][:80] if requirement.strip() else "Untitled requirement"
    return Plan(
        title=f"Generic Plan: {first_line}",
        interpreted_problem=(
            "This requirement did not match a catalog entry. The tool has "
            "produced a generic engineering template. Fill in each section "
            "after clarifying the requirement with the stakeholder.\n\n"
            f"Raw requirement:\n\n> {requirement.strip()}"
        ),
        ambiguities=[
            "What is the primary success metric?",
            "What is explicitly out of scope?",
            "Which existing systems does this touch?",
            "Who are the users and what is the expected load?",
        ],
        assumptions=[
            "The requirement can be satisfied without breaking existing APIs.",
            "The team can ship a small vertical slice first, then expand.",
        ],
        tasks=[
            ("Clarify the requirement", "-", "Assist with drafting clarifying questions"),
            ("Write a one-sentence success criterion", "1", "Assist with phrasing"),
            ("Sketch the smallest testable slice", "2", "Generate a scaffold"),
            ("Implement the slice", "3", "Generate first draft; engineer reviews"),
            ("Write tests for the slice", "4", "Generate test cases"),
            ("Document decisions and trade-offs", "4-5", "Assist with structure"),
        ],
        artifacts=[
            ("PROBLEM_STATEMENT.md", "One page: what, why, scope, non-goals"),
            ("<module>.py", "First implementation slice"),
            ("tests/test_<module>.py", "Tests for the slice"),
        ],
        acceptance_checks=[
            "The one-sentence success criterion is objectively verifiable",
            "The smallest slice passes its tests",
            "No existing tests regress",
        ],
        risks=[
            ("Building the wrong thing", "Scope", "Write the one-sentence success criterion before any code"),
            ("Scope creep", "Scope", "Explicitly list non-goals in PROBLEM_STATEMENT.md"),
        ],
    )


# ---------- Catalog matching ----------

def select_plan(requirement: str) -> Plan:
    """Return a Plan for the given requirement, using the catalog if it matches."""
    text = requirement.lower()
    # Longest-keyword-first so 'make it scalable' doesn't match 'make it scale'
    for key in sorted(CATALOG, key=len, reverse=True):
        if key in text:
            return CATALOG[key]()
    return _plan_generic(requirement)


# ---------- Markdown rendering ----------

def render_markdown(plan: Plan, raw_requirement: str) -> str:
    lines: list[str] = []
    lines.append(f"# {plan.title}")
    lines.append("")
    lines.append("## Source Requirement")
    lines.append("")
    lines.append("> " + raw_requirement.strip().replace("\n", "\n> "))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Interpreted Problem")
    lines.append("")
    lines.append(plan.interpreted_problem)
    lines.append("")
    lines.append("## 2. Ambiguities and Assumptions")
    lines.append("")
    lines.append("**Ambiguities identified:**")
    lines.append("")
    for a in plan.ambiguities:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("**Assumptions made:**")
    lines.append("")
    for a in plan.assumptions:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("## 3. Sequenced Tasks")
    lines.append("")
    lines.append("| # | Task | Depends on | AI Assistance Point |")
    lines.append("|---|------|-----------|---------------------|")
    for i, (task, deps, ai) in enumerate(plan.tasks, start=1):
        lines.append(f"| {i} | {task} | {deps} | {ai} |")
    lines.append("")
    lines.append("## 4. AI Assistance Points")
    lines.append("")
    lines.append("Each task lists where AI assists. The engineer owns review,")
    lines.append("validation, and integration — AI never commits unreviewed code.")
    lines.append("")
    lines.append("| # | Task | What AI helps with |")
    lines.append("|---|------|--------------------|")
    for i, (task, _, ai) in enumerate(plan.tasks, start=1):
        lines.append(f"| {i} | {task} | {ai} |")
    lines.append("")
    lines.append("## 5. Proposed Artifacts")
    lines.append("")
    lines.append("| Artifact | Purpose |")
    lines.append("|----------|---------|")
    for name, purpose in plan.artifacts:
        lines.append(f"| `{name}` | {purpose} |")
    lines.append("")
    lines.append("## 6. Acceptance Checks")
    lines.append("")
    for c in plan.acceptance_checks:
        lines.append(f"- [ ] {c}")
    lines.append("")
    lines.append("## 7. Risks and Mitigations")
    lines.append("")
    lines.append("| Risk | Category | Mitigation |")
    lines.append("|------|----------|------------|")
    for risk, cat, mit in plan.risks:
        lines.append(f"| {risk} | {cat} | {mit} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Generated by `workflow.py`. This tool is engineer-led: it produces_")
    lines.append("_structure, not decisions. All content is reviewed before use._")
    lines.append("")
    return "\n".join(lines)


# ---------- CLI ----------

def _load_requirement(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    if not path.exists():
        raise SystemExit(f"Requirement file not found: {source}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn a software requirement into a structured engineering plan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python workflow.py example/url_shortener.txt\n"
            "  python workflow.py example/url_shortener.txt --out plan.md\n"
            "  echo 'Add user login' | python workflow.py -\n"
            "  python workflow.py --list\n"
        ),
    )
    parser.add_argument("requirement", nargs="?", help="Path to a requirement file, or '-' for stdin.")
    parser.add_argument("--out", help="Write the markdown report to this file instead of stdout.")
    parser.add_argument("--list", action="store_true", help="List the catalog of known requirement types.")
    args = parser.parse_args()

    if args.list:
        print("Catalog entries (matched by substring against the requirement):")
        for key in sorted(CATALOG):
            print(f"  - {key}")
        print()
        print("Any requirement that does not match falls through to the generic template.")
        return

    if not args.requirement:
        parser.print_help()
        sys.exit(1)

    raw = _load_requirement(args.requirement)
    plan = select_plan(raw)
    markdown = render_markdown(plan, raw)

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()