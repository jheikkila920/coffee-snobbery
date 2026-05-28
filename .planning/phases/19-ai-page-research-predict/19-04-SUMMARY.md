---
phase: 19-ai-page-research-predict
plan: "04"
subsystem: ai-improve-brew-preference-prose
tags: [ai, sse, tdd, aix-09, aix-12, aix-13, d-10, d-12, d-15, d-16, scheduler]
dependency_graph:
  requires: [19-01 (BrewImproveSchema/PreferenceProfileProseSchema), 19-02 (D-14/D-15 ai_service hardening), 19-03 (ai_quota helpers, SSE two-phase pattern)]
  provides: [generate_brew_improvement SSE flow, generate_preference_profile_prose, scheduler nightly preference_profile_prose regen]
  affects: [app/services/ai_service.py, app/services/scheduler.py, tests/services/test_brew_improve.py, tests/services/test_preference_prose.py]
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, SSE two-phase prose-stream+structured-validate (mirrored from ai_research.py), signature-keyed dedup, sync-to-async bridge in scheduler]
key_files:
  created: []
  modified:
    - app/services/ai_service.py (generate_brew_improvement + generate_preference_profile_prose + _build_brew_improve_prompt + _build_preference_prose_prompt + ServerSentEvent import + AsyncGenerator import)
    - app/services/scheduler.py (run_nightly_ai_refresh extended with preference_profile_prose nightly regen)
    - tests/services/test_brew_improve.py (schema test kept + 3 new tests: prior sessions, IDOR guard, quota bucket)
    - tests/services/test_preference_prose.py (schema test kept + 3 new tests: analytics consumption, sig skip, latency comment)
decisions:
  - "generate_brew_improvement is SSE (D-16 three-flow scope); generate_preference_profile_prose is non-SSE (D-16 excludes it -- it is signature-driven not slow-streamed)"
  - "generate_preference_profile_prose uses synchronous anthropic.Anthropic (not AsyncAnthropic) -- consistent with the existing regenerate() sync-read/sync-write bracketing pattern"
  - "Scheduler per-user loop runs preference_profile_prose in its own SessionLocal() with/block -- matches the existing regenerate() session isolation pattern"
  - "brew_improvement is on-demand only; scheduler comment explicitly states it is NOT regenerated nightly (RESEARCH Pitfall 6)"
  - "_build_brew_improve_prompt serializes prior sessions (including target) into JSON for D-12 prior-session-aware coaching"
  - "sse_starlette imported at module level in ai_service.py (with try/except fallback) rather than inside the function -- avoids repeated import overhead on each SSE request"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-28"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 19 Plan 04: Improve-Brew SSE Flow + Preference-Profile Prose Summary

Two new AI service flows using TDD: `generate_brew_improvement` (SSE, prior-session-aware, own quota bucket) and `generate_preference_profile_prose` (non-SSE, analytics-powered, nightly scheduler integration).

## What Was Built

### Task 1: generate_brew_improvement (AIX-12 / D-12 / D-16)

- **`generate_brew_improvement(db, user_id, session_id)`**: Two-phase SSE generator mirroring the ai_research.py pattern (established in plan 19-03).
  - Session loaded via `brew_sessions.get_brew_session(db, session_id=session_id, by_user_id=user_id)` — user-scoped IDOR guard (T-19-12). Returns `event:error` on None.
  - ALL prior sessions for `coffee_id` loaded via `brew_sessions.list_brew_sessions(by_user_id=user_id, coffee_id=coffee_id)` (D-12).
  - Prompt serializes each session's `{grind, ratio, temp_c, brewer_id, recipe_id, rating}` as JSON; instructs the LLM to propose parameters NOT already tried.
  - Quota checked against `brew_improvement` bucket (separate from research — T-19-14 / D-08).
  - Advisory lock via `_get_lock` + `_try_advisory_lock` (T-19-10 reconnect guard).
  - Phase 1: `async with async_client.messages.stream(...)` + `text_stream` deltas as `event:message`.
  - Phase 2: `get_final_message()` → `_project_tool_use_input` → `BrewImproveSchema.model_validate` (T-19-13).
  - On `ValidationError` → `event:error` + telemetry error row.
  - Telemetry row written with `rec_type='brew_improvement'`, `duration_ms` (AIX-13 / D-15).
  - `event:complete` emits JSON-serialized `BrewImproveSchema`.
  - OpenAI non-streaming fallback (RESEARCH Open Q#1).
  - `# p95 target: <= 20s` comment (D-15).

- **`_build_brew_improve_prompt(session, prior_sessions)`**: Serializes target session + all prior sessions to JSON. Instructs the model to check `unchanged_parameters` against prior-session dials.

**Test results:** 4 passed (test_brew_improve.py), 0 skipped.

### Task 2: generate_preference_profile_prose + scheduler (AIX-09 / D-10 / D-15)

- **`generate_preference_profile_prose(db, user_id)`**: Non-SSE synchronous structured call.
  - Pre-reads: `compute_input_signature` for dedup; `get_latest_recommendation` to check existing row.
  - Signature skip: returns `("skipped", existing_row)` when `existing_row.input_signature == current_sig`.
  - Prompt inputs (D-10): `get_preference_profile` (origin/process/roaster/roast_level dims) + `get_flavor_descriptors` (top-10 flavor notes from 4.0+ sessions), both JSON-serialized.
  - Single structured call: `anthropic.Anthropic.messages.create` with `structure_output` tool.
  - `_project_tool_use_input` + `PreferenceProfileProseSchema.model_validate` (T-19-13).
  - Telemetry row: `rec_type='preference_profile_prose'`, `input_signature=current_sig`, `duration_ms` (AIX-13 / D-15).
  - OpenAI non-streaming fallback.
  - `# p95 target: <= 30s` comment (D-15).
  - Returns `("generated", row)` | `("skipped", row)` | `("try_again", None)` | `("not_configured", None)`.

- **`_build_preference_prose_prompt(profile, flavor_descriptors)`**: Serializes `get_preference_profile` dimensions dict + `get_flavor_descriptors` rows to JSON; instructs the LLM to cross-cut flavor × process × origin × varietal × rating.

- **`run_nightly_ai_refresh` (scheduler.py)**: Per-user loop extended with a second `SessionLocal` block that calls `asyncio.run(ai_service.generate_preference_profile_prose(db, user_id=uid))`. Errors are logged but do not abort the run. `brew_improvement` is explicitly NOT in the nightly loop (comment documents this). Research cache/predictions are NOT regenerated nightly.

**Test results:** 4 passed (test_preference_prose.py), 0 skipped.

**Combined: 8 passed, 0 skipped (test_brew_improve.py + test_preference_prose.py).**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Duplicate ValidationError import**
- **Found during:** ruff check after implementing generate_preference_profile_prose
- **Issue:** Added `from pydantic import ValidationError as PydanticValidationError` at module level while a `from pydantic import ValidationError` already existed. Caused F811 (redefinition) + regressions in local-import functions throughout the file.
- **Fix:** Removed the duplicate alias import; existing functions continue to locally import `PydanticValidationError` where needed.
- **Files modified:** `app/services/ai_service.py`
- **Commit:** fbf3262

**2. [Rule 1 - Bug] Unused `import anthropic as _anthropic` inside function**
- **Found during:** ruff check (F401)
- **Issue:** Added an `import anthropic as _anthropic` inside `generate_preference_profile_prose` that was immediately shadowed by the module-level `anthropic` import already in scope.
- **Fix:** Removed the inner import; use the module-level `anthropic` binding directly.
- **Files modified:** `app/services/ai_service.py`
- **Commit:** a3e2daa (fixed inline before commit)

**3. [Rule 1 - Bug] MagicMock not JSON-serializable in preference prose test**
- **Found during:** Task 2 test GREEN run
- **Issue:** `_build_preference_prose_prompt` calls `float(row.avg_rating)` — with `MagicMock` rows this returned a MagicMock, which `json.dumps` cannot serialize.
- **Fix:** Changed test mock data to use `collections.namedtuple` with real float/int values instead of `MagicMock` objects.
- **Files modified:** `tests/services/test_preference_prose.py`
- **Commit:** 98da670

## Known Stubs

- `generate_brew_improvement` emits `event:complete` with JSON-serialized `BrewImproveSchema.model_dump()`. The route in plan 19-05 renders this into an HTML fragment; the service layer emits the validated object data (not HTML) as the `event:complete` payload. The plan 19-05 route will render the fragment from the JSON.
- `generate_preference_profile_prose` writes the prose to `ai_recommendations`; the template card that displays it is wired in plan 19-06.

## Threat Flags

No new network endpoints introduced. The two new functions are service-layer only — routes added in plans 19-05/19-06 will be the trust boundary. Threat mitigations applied as designed:
- T-19-12: `get_brew_session(..., by_user_id=user_id)` — session load is always user-scoped
- T-19-13: `_project_tool_use_input` + `extra=forbid` on both schemas
- T-19-14: quota bucket `brew_improvement` separate from `coffee_research`
- T-19-15: preference_profile_prose regenerates only on signature change; brew_improvement on-demand; research cache TTL-driven

## Self-Check: PASSED

Files exist:
- `app/services/ai_service.py` — FOUND (generate_brew_improvement + generate_preference_profile_prose)
- `app/services/scheduler.py` — FOUND (preference_profile_prose in nightly loop)
- `tests/services/test_brew_improve.py` — FOUND (4 tests)
- `tests/services/test_preference_prose.py` — FOUND (4 tests)

Source assertions:
- `grep -n "p95 target: <= 20s" app/services/ai_service.py` → line 1925 FOUND
- `grep -n "p95 target: <= 30s" app/services/ai_service.py` → line 2212 FOUND
- `grep -n "preference_profile_prose" app/services/scheduler.py` → lines 316, 322, 334 FOUND
- `grep -n "brew_improvement" app/services/scheduler.py` → line 317 (comment only, no call) FOUND

Commits exist:
- 97249a5: test(19-04): add failing tests for generate_brew_improvement SSE flow (RED)
- fbf3262: feat(19-04): implement generate_brew_improvement SSE flow (GREEN)
- 98da670: test(19-04): add tests for generate_preference_profile_prose flow (RED/GREEN)
- a3e2daa: feat(19-04): implement generate_preference_profile_prose + scheduler nightly regen
