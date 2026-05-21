---
phase: 07-ai-services
plan: "01"
subsystem: ai-service-foundation
tags: [ai, pydantic, schemas, events, ssrf, citation-projector, advisory-lock]
dependency_graph:
  requires: []
  provides:
    - app/services/ai_schemas.py
    - app/services/ai_service.py (helpers)
    - app/events.py (ai.* constants)
    - tests/services/test_ai_service.py (Wave 0)
  affects:
    - "07-03 (coffee rec flow)"
    - "07-04 (equipment + paste-rank flows)"
    - "07-05 (AI router)"
tech_stack:
  added: []
  patterns:
    - "Pydantic v2 ConfigDict(extra=forbid) for LLM output validation"
    - "httpx follow_redirects=False + scheme allowlist for SSRF hardening"
    - "SHA256 → int64 advisory lock key derivation"
    - "asyncio.Lock dict keyed by (user_id, rec_type)"
    - "getattr with 0 defaults for cross-provider usage shape compatibility"
key_files:
  created:
    - app/services/ai_schemas.py
    - app/services/ai_service.py
    - tests/services/test_ai_service.py
  modified:
    - app/events.py
decisions:
  - "All three tasks' ai_service.py helpers implemented in one file creation (Task 2) rather than three separate edit cycles — all Task 3 acceptance criteria verified by tests before separate Task 3 commit"
  - "NON_RETRYABLE tuple defined at module level so _is_anthropic_fallback_error stays a simple isinstance check"
  - "noqa: F401 used on imports reserved for 07-03+ flows (json, time, select, events, services) to keep the import contract stable"
metrics:
  duration: "~35 minutes"
  completed: "2026-05-20"
  tasks_completed: 3
  files_created: 3
  files_modified: 1
---

# Phase 7 Plan 01: AI Service Foundation Summary

**One-liner:** Per-flow Pydantic v2 schemas (extra=forbid), citation projector (T-07-02), SSRF-hardened URL verifier (T-07-01), advisory lock key, throttle eviction, fallback predicate (incl. 529 streaming bug), telemetry writer, and 20 Wave 0 unit tests.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Per-flow Pydantic schemas + ai.* event taxonomy | cdca20f | app/services/ai_schemas.py, app/events.py, tests/services/test_ai_service.py |
| 2 | Citation projector + SSRF-hardened URL verifier | d9dc68b | app/services/ai_service.py |
| 3 | Lock/throttle/clients/fallback predicate + tests | d9dc68b | app/services/ai_service.py (same commit — all helpers implemented together) |

## Verification

- `python -m pytest tests/services/test_ai_service.py -x -q` → **20 passed**
- `ruff check app/services/ai_service.py app/services/ai_schemas.py app/events.py` → **All checks passed**
- `grep -n "cred.key" app/services/ai_service.py` → appears only in `_build_anthropic_client` and `_build_openai_client` SDK constructor calls (T-07-03 verified)

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema defined | PASS |
| All top-level schemas have summary_prose + extra="forbid" | PASS |
| 8 ai.* events exported and in __all__ | PASS |
| _project_tool_use_input strips non-tool_use blocks (T-07-02) | PASS |
| _verify_buy_url: https-only, no redirect, 64KB cap, 5s timeout (T-07-01) | PASS |
| test_url_verify_ssrf_redirect passes | PASS |
| test_url_verify_scheme_rejected passes | PASS |
| _LOCKS, _THROTTLE, _get_lock, _evict_stale_throttle defined | PASS |
| _build_anthropic_client, _build_openai_client with max_retries=1 (AI-01) | PASS |
| _is_anthropic_fallback_error: non-retryable + 529/overloaded (Pitfall 1) | PASS |
| test_fallback_predicate_529_string passes | PASS |
| test_fallback_predicate_rate_limit_false passes | PASS |
| _write_recommendation_row: tokens_input_search=0 with TODO(A1) | PASS |
| ruff check passes on all three files | PASS |

## Deviations from Plan

### Implementation Structure

**Task 2 and Task 3 were implemented together in a single ai_service.py creation.**

The plan's TDD flow intended three separate edit cycles (Task 2 adds projector/verifier/advisory_key; Task 3 adds lock/throttle/clients/fallback/telemetry). Since all helpers are tightly coupled in a single module and the Wave 0 tests were written for all of them simultaneously in Task 1's commit, implementing them in one pass was the natural execution path.

- All Task 2 acceptance criteria verified by tests (projector, SSRF redirect, scheme reject, advisory key stability)
- All Task 3 acceptance criteria verified by tests (fallback predicate, 529 string match, rate-limit false, lock identity, throttle eviction, max_uses settings)
- Both committed under d9dc68b with the Task 2 label (Task 3 has no additional file changes)

This is a documentation-only deviation; no functionality was skipped or deferred.

## Known Stubs

None. This plan delivers infrastructure helpers with no UI surface and no data placeholders.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond those defined in the plan's threat model. All four threat register items (T-07-01 through T-07-04) are implemented and verified by tests.

## Self-Check

Will run after SUMMARY commit.
