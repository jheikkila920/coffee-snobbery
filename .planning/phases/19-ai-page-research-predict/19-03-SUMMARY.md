---
phase: 19-ai-page-research-predict
plan: "03"
subsystem: ai-research-service
tags: [ai, sse, quota, cache, tdd, aix-04, aix-05, aix-07, aix-13, d-06, d-07, d-08, d-09, d-16]
dependency_graph:
  requires: [19-01 (AICoffeeResearchCache/AIRatingPrediction models + CoffeeResearchSchema), 19-02 (D-14/D-15 ai_service hardening)]
  provides: [ai_quota.py rolling-24h math, ai_research.py cache+prediction+SSE generator, analytics.count_research_calls_in_last_24h delegation]
  affects: [app/services/ai_quota.py, app/services/ai_research.py, app/services/analytics.py, tests/services/test_ai_quota.py, tests/services/test_ai_research.py]
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, rolling-24h DB COUNT quota, lazy TTL cache eviction, two-phase SSE (Anthropic streaming + structured finalize), signature-versioned prediction upsert, advisory lock reconnect guard]
key_files:
  created:
    - app/services/ai_quota.py
    - app/services/ai_research.py
    - tests/services/test_ai_quota.py
  modified:
    - app/services/analytics.py (count_research_calls_in_last_24h delegation added)
    - tests/services/test_ai_research.py (7 skipped placeholders filled with real tests)
decisions:
  - "AsyncGenerator imported from collections.abc (not typing) per UP035 ruff rule"
  - "generate_coffee_research returns AsyncGenerator[ServerSentEvent, None] — caller wraps in EventSourceResponse"
  - "cache hit path does NOT write an ai_recommendations row (quota not decremented, AIX-04/D-04)"
  - "_write_research_telemetry uses cache_key as input_signature (not brew-session sig) — telemetry row is cost-only, not signature-gated"
  - "OpenAI fallback path uses non-streaming structured call per RESEARCH Open Q#1"
  - "SSE lock guard: in-memory _get_lock checked first (fast path); then _try_advisory_lock (Postgres cross-process)"
  - "p95 target comment placed at module level (line 19) AND above generate_coffee_research (line 350)"
metrics:
  duration: "~60 minutes"
  completed: "2026-05-28"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 19 Plan 03: AI Research Service Layer Summary

Rolling-24h quota math, shared world-view cache with lazy TTL eviction, signature-versioned per-user rating predictions, and the two-phase Anthropic SSE generator with structured-output reconciliation — using TDD RED/GREEN throughout.

## What Was Built

### Task 1: ai_quota.py — rolling-24h quota math (AIX-05/D-08/D-09)

- **`count_calls_last_24h(db, user_id, rec_type)`**: `SELECT COUNT(id)` on `ai_recommendations` where `error_status IS NULL` and `generated_at >= now-24h`. Returns 0 on None (empty table). Cache hits never write rows, so they never decrement quota.
- **`get_quota_reset_time(db, user_id, rec_type)`**: `SELECT MIN(generated_at)` in the same 24h window. Returns `oldest_at + 24h` or None when window empty (D-09).
- **`get_quota_cap(rec_type)`**: Reads `ai.research_daily_quota` or `ai.improve_brew_daily_quota` from `app_settings` via `settings_service.get_int`. Falls back to 20 when absent (D-08 defensive fallback). Separate keys = separate buckets.
- **`remaining(db, user_id, rec_type)`**: `max(cap - count, 0)` — never negative.
- **`analytics.count_research_calls_in_last_24h`**: One-line delegation to `ai_quota.count_calls_last_24h` (per CONTEXT.md naming requirement; avoids duplicating the query).

**Final test result:** 7 passed (test_ai_quota.py), 0 skipped.

### Task 2: ai_research.py — cache, prediction, SSE generator (AIX-01/02/03/04/07/13)

- **`normalize_cache_key(coffee_name, roaster_name)`**: `lower().strip() + '|' + lower(roaster or '').strip()`. Empty string after pipe when no roaster. Identical derivation in read and write paths (D-06).
- **`get_cached_research(db, cache_key)`**: Lazy eviction — DELETE expired row for this key first, then SELECT the live row. Returns None on cache miss or after eviction (Pattern 4).
- **`_write_cache_row`**: PostgreSQL upsert (`ON CONFLICT (cache_key) DO UPDATE`) with 30-day `expires_at`. Returns the canonical row.
- **`_write_research_telemetry`**: Calls `ai_service._write_recommendation_row` verbatim with `rec_type='coffee_research'`, `duration_ms`, and `generated_by='user_request'` (AIX-13 / AI-02 telemetry).
- **`get_or_refresh_prediction`**: Reads existing `AIRatingPrediction` for `(user_id, research_cache_key)`. Regenerates without web search when: row absent, `expires_at` past (7-day TTL), or `input_signature` mismatch. Upserts via `ON CONFLICT ... DO UPDATE` (D-07/AIX-02). Falls back to OpenAI (non-streaming) if Anthropic not configured.
- **`generate_coffee_research`** (async generator, `# p95 target: <= 30s`): Full gate sequence:
  1. Cold-start gate (`analytics_service.get_cold_start_counts`) — AIX-03
  2. Quota check (`ai_quota.remaining`) — AIX-05/D-08
  3. Cache hit → emit `event:complete` instantly, no LLM, no quota decrement — AIX-04
  4. In-memory lock (`_get_lock`) + advisory lock (`_try_advisory_lock`) — T-19-10
  5. Re-check cache under lock
  6. Phase 1: Anthropic `client.messages.stream(...)` + `text_stream` deltas as `event:message`
  7. Phase 2: `await stream.get_final_message()` → `_project_tool_use_input` → `CoffeeResearchSchema.model_validate` (T-19-08)
  8. On `ValidationError` → `event:error` with short user-facing message (T-19-09)
  9. Write cache row, telemetry row, tie prediction
  10. Render result fragment → `event:complete`
  - OpenAI fallback: non-streaming structured call (RESEARCH Open Q#1)
  - `_verify_buy_url` explicitly NOT called inside generator — scheduled as `BackgroundTask` by route (T-19-11)

**Final test result:** 10 passed (test_ai_research.py), 0 skipped.

**Combined: 17 passed, 0 skipped (test_ai_research.py + test_ai_quota.py).**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock setup for Anthropic `messages.stream` in tests**
- **Found during:** Task 2 TDD GREEN — `test_sse_event_contract` failing with `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`
- **Issue:** `AsyncMock` for `mock_anth_instance` caused `messages.stream()` to return a coroutine instead of an async context manager. `async with client.messages.stream(...)` requires the return value to be a context manager, not a coroutine.
- **Fix:** Changed `mock_anth_instance = AsyncMock()` to `mock_anth_instance = MagicMock()` so `messages.stream()` returns the mock stream object directly (not wrapped in a coroutine).
- **Files modified:** `tests/services/test_ai_research.py`
- **Commit:** 8638c28 (fixed inline before GREEN commit)

**2. [Rule 2 - Missing critical functionality] Added `AsyncGenerator` type annotation from `collections.abc`**
- **Found during:** Ruff check (UP035 rule)
- **Issue:** `from typing import AsyncGenerator` is deprecated in Python 3.9+; `collections.abc.AsyncGenerator` is the canonical import.
- **Fix:** Changed import to `from collections.abc import AsyncGenerator`.
- **Files modified:** `app/services/ai_research.py`
- **Commit:** 8638c28

### Style fixes (ruff)

- Import ordering fixed (I001) in all three affected files
- Unused variables (`mock_quota`, `llm_call_count`, `inside`, `outside`) removed from tests (F841)
- `datetime.UTC` alias used instead of `timezone.utc` (UP017)
- Long docstring line shortened (E501)

## Known Stubs

- `_render_research_result()` returns a minimal HTML string stub — the real Jinja2 template (`fragments/ai/research_result.html`) is created in plan 19-04. The service-layer SSE contract is complete; the stub is sufficient for tests. The `event:complete` data field will contain real rendered HTML once the template is wired.

## Threat Flags

No new network endpoints introduced. The research generator is the service layer only — the route that calls it (added in 19-04) will be the trust boundary. All T-19-07 through T-19-11 mitigations are implemented as designed:
- T-19-07: quota keyed to user_id only (DB-backed COUNT)
- T-19-08: `_project_tool_use_input` + `extra=forbid` on `CoffeeResearchSchema`
- T-19-09: `event:error` emits short user-facing string; real exception structlogged
- T-19-10: `_get_lock` + `_try_advisory_lock` held across generator lifetime
- T-19-11: `_verify_buy_url` explicitly excluded from generator (BackgroundTask for route)

## Self-Check: PASSED

Files exist:
- `app/services/ai_quota.py` — FOUND
- `app/services/ai_research.py` — FOUND
- `tests/services/test_ai_quota.py` — FOUND
- `tests/services/test_ai_research.py` — FOUND (7 skipped placeholders replaced with real tests)

Source assertions:
- `grep -n "p95 target: <= 30s" app/services/ai_research.py` → lines 19 and 350 FOUND
- `grep -n "coffee_research" app/services/ai_quota.py` → `_QUOTA_SETTINGS_KEYS` dict FOUND
- `grep -n "count_research_calls_in_last_24h" app/services/analytics.py` → FOUND

Commits exist:
- eefd1aa: test(19-03): add failing tests for rolling-24h quota math (RED)
- 8e5f676: feat(19-03): implement rolling-24h quota math -- ai_quota.py + analytics delegation
- 8c5c2ed: test(19-03): add failing tests for ai_research service layer (RED)
- 8638c28: feat(19-03): implement ai_research.py -- cache, prediction, two-phase SSE generator
