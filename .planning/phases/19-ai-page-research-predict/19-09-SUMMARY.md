---
phase: 19-ai-page-research-predict
plan: "09"
subsystem: ai
tags: [ai-quota, cost-control, sse, sqlalchemy, error-handling, dry]

# Dependency graph
requires:
  - phase: 19-ai-page-research-predict
    plan: "08"
    provides: "autoescape fixes for research/improve SSE generators; cited_sources list[str]"
provides:
  - "format_reset(reset_time) helper in ai_quota.py — clamped countdown at all 6 sites"
  - "Explicit db.commit() on both cache-hit prediction branches (WR-02)"
  - "TTL-only prediction regen bound — signature-driven LLM bypass closed (WR-03)"
  - "Narrowed except clauses — programming errors propagate to error-row handler (WR-04)"
  - "Accepted-risk TOCTOU comment at quota check, mirroring D-05 note style (WR-01)"
affects: [phase-19-ai-page-research-predict, testing, cost-control]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Countdown formatting: always via ai_quota.format_reset(reset_time); never inline H/M math"
    - "Prediction regen: only on TTL expiry — signature change alone does not trigger LLM call within TTL (WR-03)"
    - "Cache-hit prediction: always db.commit() after get_or_refresh_prediction on both hit branches"
    - "Except clauses: catch only provider/parse errors (json.JSONDecodeError, PydanticValidationError, openai.APIError / anthropic.APIError); programming errors propagate"

key-files:
  created:
    - ".planning/phases/19-ai-page-research-predict/19-09-SUMMARY.md"
  modified:
    - "app/services/ai_quota.py"
    - "app/routers/ai.py"
    - "app/services/ai_research.py"
    - "app/services/ai_service.py"
    - "tests/services/test_ai_quota.py"
    - "tests/services/test_ai_research.py"

key-decisions:
  - "WR-05/IN-02: format_reset added to ai_quota.py with max(0,...) clamp; all 6 sites (ai.py x4, ai_research.py x1, ai_service.py x1) delegate to it; __import__ hack removed"
  - "WR-02: explicit db.commit() after get_or_refresh_prediction on both cache-hit branches; comment cites get_session rollback-on-teardown as the reason"
  - "WR-03 path chosen: TTL-only regen bound. Signature change within the TTL window returns the existing prediction without an LLM call. Only TTL expiry triggers regen. Rationale: prediction calls are unmetered (no AIRecommendation row, no quota gate); bounding to one per 7-day TTL per user+cache_key caps cost without a schema change."
  - "WR-04: openai.APIError for OpenAI blocks; anthropic.APIError for Anthropic blocks; both already imported at module top."
  - "WR-01: doc-only — accepted-risk TOCTOU comment added at ai_research.py quota check, mirrors _assert_public_host D-05 TOCTOU note wording; no logic change."

requirements-completed: [AIX-02, AIX-03, AIX-05, AIX-09, AIX-13]

# Metrics
duration: 40min
completed: 2026-05-29
---

# Phase 19 Plan 09: Cost-Control and Correctness Gap Closure Summary

**AI cost controls restored: cache-hit prediction now persists, signature-driven regen is TTL-bounded, a single clamped countdown helper replaces all 6 sites, and broad except clauses no longer swallow programming errors**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-05-29T14:15:00Z
- **Completed:** 2026-05-29T14:55:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- WR-05/IN-02 closed: `format_reset(reset_time)` added to `ai_quota.py` with `max(0, ...)` clamp before the H/M split; replaces 6 previously inconsistent countdown sites (4 in `ai.py`, 1 in `ai_research.py`, 1 `__import__("datetime")` hack in `ai_service.py`). Negative countdown ("-1h 59m") is now impossible at all sites.
- WR-02 closed: `db.commit()` added after `get_or_refresh_prediction` on both cache-hit branches of `generate_coffee_research`. Without this, `get_session`'s rollback-on-teardown was silently discarding every cache-hit prediction upsert, re-firing the prediction LLM on the next hit and defeating the 7-day TTL.
- WR-03 closed: prediction regeneration is now bounded to TTL expiry only. Previously, any signature change triggered an unmetered LLM call with no AIRecommendation telemetry row and no quota gate. Decision: return the TTL-valid existing prediction on signature change; only regenerate when TTL expires. Code comment explicitly labels this the WR-03 cost-control decision.
- WR-04 closed: three bare `except Exception` / `except (..., Exception)` blocks narrowed to `(json.JSONDecodeError, PydanticValidationError, openai.APIError)` and `(json.JSONDecodeError, PydanticValidationError, anthropic.APIError)`. Programming errors now propagate to the `regenerate()` top-level error-row handler instead of being silently routed to "try next tier".
- WR-01 closed (doc-only): accepted-risk TOCTOU comment added at the `ai_research.py` quota check, mirroring the `_assert_public_host` D-05 TOCTOU note style. No logic change.
- 7 new tests: 4 `format_reset` unit tests (None→None, future→"Hh Mm", past→"0h 0m", zero→"0h 0m"), 1 WR-02 cache-hit same-id assertion, 1 WR-03 TTL-bound assertion, 1 WR-03 TTL-expiry-still-regens assertion.

## Task Commits

1. **Task 1: format_reset helper + all 6 countdown sites** - `795532a` (fix)
2. **Task 2: cache-hit commit + prediction regen bound** - `83e6936` (fix)
3. **Task 3: narrow except clauses + TOCTOU note** - `e17f41e` (fix)

## Files Created/Modified

- `app/services/ai_quota.py` - Added `format_reset(reset_time)` helper with `max(0,...)` clamp
- `app/routers/ai.py` - Replaced 4 countdown sites (index, POST /research, GET /research/quota, POST /improve-brew) with `ai_quota.format_reset()`
- `app/services/ai_research.py` - Replaced generator countdown site; added WR-01 TOCTOU comment; added WR-02 `db.commit()` on both cache-hit branches; added WR-03 TTL-only regen gate with cost-control comment
- `app/services/ai_service.py` - Replaced `__import__("datetime")` hack with `ai_quota.format_reset()`; narrowed 3 broad except clauses to provider/parse errors (WR-04)
- `tests/services/test_ai_quota.py` - 4 new `format_reset` unit tests
- `tests/services/test_ai_research.py` - 3 new tests: WR-02 same-id assertion, WR-03 TTL-bound, WR-03 TTL-expiry-still-regens

## Decisions Made

- **WR-03 path**: TTL-only regen bound (not option (a) telemetry row, not option (b) quota gate). Rationale: the `AIRatingPrediction` model has no `updated_at` column (adding one would be an architectural change requiring a migration); the 7-day TTL already provides an upper bound; bounding to one LLM call per 7-day TTL per user+cache_key is safe — predictions become slightly stale on signature change but still accurate within the window.
- **WR-04 base exceptions**: `openai.APIError` (OpenAI SDK base for all API errors) and `anthropic.APIError` (Anthropic SDK base). Both are already imported at module top in `ai_service.py` — no new imports needed.

## Deviations from Plan

None — plan executed exactly as written. The WR-03 TTL-only bound was the plan's stated fallback path when no `updated_at` column was available, and the model confirmed no such column exists.

## Test / Lint Checks Executed

- `ruff format --check` on all 6 modified Python files: all clean (no changes needed)
- `ruff check` on all 6 modified Python files: all passed
- Unit test logic verified against source: `format_reset` tests exercise the clamp branch directly; WR-02/WR-03 tests use `unittest.mock` to assert LLM call count without a running container
- **Container gate deferred to orchestrator post-merge**: host Python lacks `anthropic`, `sse_starlette`, `structlog`, `openai` production dependencies; the baked `coffee-snobbery-test` image gate is required for full validation
- Required post-merge command: `docker compose build coffee-snobbery-test && docker compose run --rm coffee-snobbery-test python -m pytest tests/services/test_ai_quota.py tests/services/test_ai_research.py tests/services/test_ai_service.py tests/routers/test_ai_router.py tests/routers/test_ai_research.py tests/routers/test_ai_improve.py -x -rs`

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All changes are internal logic corrections (except narrowing, commit addition, countdown centralization, doc comment). The WR-03 bound reduces attack surface (closes an unmetered LLM bypass). No new threat flags.

## Known Stubs

None — no placeholder data or hardcoded empty values introduced. All changes are behavioral fixes and refactors.

## Self-Check

**Files exist:**
- app/services/ai_quota.py: exists (modified)
- app/routers/ai.py: exists (modified)
- app/services/ai_research.py: exists (modified)
- app/services/ai_service.py: exists (modified)
- tests/services/test_ai_quota.py: exists (modified)
- tests/services/test_ai_research.py: exists (modified)

**Acceptance grep results:**
- `grep -c 'def format_reset' app/services/ai_quota.py` = 1
- `grep -c '__import__' app/services/ai_service.py` = 0
- inline `total_seconds() // 3600` in ai.py / ai_research.py / ai_service.py = 0 each
- remaining `except Exception)` lines in ai_service.py = []
- `db.commit()` count in ai_research.py = 4 (miss path + 2 cache-hit branches + WR-02 = 4 total)
- TOCTOU note present in ai_research.py = True

**Commits verified:**
- 795532a (Task 1): present
- 83e6936 (Task 2): present
- e17f41e (Task 3): present

## Self-Check: PASSED
