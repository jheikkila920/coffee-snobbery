---
phase: 07-ai-services
plan: "03"
subsystem: ai-coffee-rec-flow
tags: [ai, coffee-rec, sweet-spots, regenerate, locking, tdd]
dependency_graph:
  requires:
    - app/services/ai_service.py (07-01 helpers)
    - app/services/ai_schemas.py (07-01 schemas)
    - app/services/analytics.py (compute_input_signature, get_cold_start_counts, get_sweet_spots)
    - app/services/credentials.py (get_provider_credential)
  provides:
    - app/services/ai_service.py (regenerate, coffee-rec 3-tier flow, sweet-spots prose, recipe/alt-brewer SQL, get_latest_recommendation, is_stale, in_flight)
  affects:
    - "07-04 (equipment + paste-rank flows, same file)"
    - "07-05 (AI router — calls regenerate, in_flight, get_latest_recommendation, is_stale)"
    - "Phase 8 (SCHED-02 scheduler calls regenerate directly)"
tech_stack:
  added: []
  patterns:
    - "Three-tier web-search fallback (primary → broadened → characteristics_only)"
    - "Anthropic→OpenAI provider fallback via _is_anthropic_fallback_error predicate"
    - "_project_tool_use_input projector + CoffeeRecSchema(extra=forbid) validation chain (T-07-02)"
    - "Prompt-based JSON for OpenAI (NOT json_schema — Pitfall 2 avoided)"
    - "Pre-read/post-write DB bracketing around awaited LLM call (Pitfall 5)"
    - "In-memory asyncio.Lock + Postgres advisory lock double guard (AI-13)"
    - "Signature skip (SHA256 comparison, COST-4)"
    - "Sweet-spots written as separate sweet_spots row in same regeneration flow (AI-10)"
    - "SQL-only recipe suggestion (existing recipes only, never fabricated, AI-06)"
    - "SQL-only alt-brewer callout (>=0.5 rating delta threshold, AI-07)"
key_files:
  created: []
  modified:
    - app/services/ai_service.py
    - tests/services/test_ai_service.py
decisions:
  - "sweet_spots written as SEPARATE row (recommendation_type='sweet_spots') in same regen transaction for clean telemetry — consistent with plan frontmatter"
  - "url_verified=None on coffee row write — verification deferred to 07-05 background task per plan objective"
  - "Pre-read/post-write DB bracketing chosen over run_in_executor for Pitfall 5 — simpler and sufficient since analytics reads are fast and writes are post-await"
  - "_generate_sweet_spots_prose accepts cred= arg (not self-looking-up) to keep regenerate() in control of credential lifecycle"
  - "test_force_regenerates patches credentials_service.get_provider_credential to avoid mock-DB TypeError in regenerate's sweet-spots cred lookup"
metrics:
  duration: "~90 minutes"
  completed: "2026-05-21"
  tasks_completed: 3
  files_created: 0
  files_modified: 2
---

# Phase 7 Plan 03: Coffee-Rec Composite Flow Summary

**One-liner:** Three-tier web-search coffee-rec flow (primary→broadened→characteristics_only) with Anthropic→OpenAI fallback, citation projection, Pydantic validation, sweet-spots prose, SQL-only recipe/alt-brewer sub-flows, and the frozen `regenerate()` SCHED-02 entry point with cold-start gate, in-memory + advisory locking, and signature skip.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Recipe-suggestion + alt-brewer SQL sub-flows (no LLM) | fafec2f | app/services/ai_service.py, tests/services/test_ai_service.py |
| 2 | Coffee-rec composite flow — 3-tier search + provider fallback + sweet-spots prose | 04e6f3e | app/services/ai_service.py, tests/services/test_ai_service.py |
| 3 | regenerate() entry point + signature skip + locking + read helpers | c095c13 | app/services/ai_service.py, tests/services/test_ai_service.py |

## Verification

- `python -m pytest tests/services/test_ai_service.py -q` → **35 passed** (20 from 07-01 + 15 from 07-03)
- `ruff check app/services/ai_service.py tests/services/test_ai_service.py` → **All checks passed**
- `grep web_search_preview app/services/ai_service.py` → present in `_openai_coffee_call` tools list (line 554)
- `grep json_schema` in `_openai_coffee_call` body → **absent** (Pitfall 2 verified)
- `grep "cred.key"` → appears only in `_build_anthropic_client` and `_build_openai_client` (T-07-03 verified)
- `grep "|safe"` → appears only in a comment, never in code (T-07-03 verified)

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| `suggest_recipe` returns existing recipe_id only (never fabricated) | PASS |
| `test_alt_brewer_fires_at_half_point_delta` passes (delta exactly 0.5 → callout) | PASS |
| `test_alt_brewer_below_threshold_none` passes (delta 0.4 → None) | PASS |
| `_generate_coffee_rec` advances primary→broadened→characteristics_only | PASS |
| `test_three_tier_fallback` asserts search_tier on final tier | PASS |
| `test_provider_fallback_anthropic_to_openai` passes (AuthenticationError triggers fallback) | PASS |
| `_openai_coffee_call` uses `web_search_preview` NOT `json_schema` (Pitfall 2) | PASS |
| `_generate_sweet_spots_prose` writes row with `recommendation_type="sweet_spots"` | PASS |
| All prose uses `SYSTEM_PROMPT_VOICE`; no `|safe` introduced | PASS |
| `async def regenerate(user_id, generated_by, *, db, force=False)` matches SCHED-02 contract | PASS |
| `test_sig_skip` passes (unchanged signature, force=False → "skipped") | PASS |
| `test_advisory_lock_concurrent` passes (advisory lock False → "locked") | PASS |
| `test_not_configured` passes (no provider → "not_configured") | PASS |
| `is_stale` and `get_latest_recommendation` are user-scoped (filter `user_id ==`) | PASS |
| `regenerate` does not hold sync Session open across awaited LLM call (docstring states approach) | PASS |
| Full `python -m pytest tests/services/test_ai_service.py -q` exits 0 | PASS |

## Deviations from Plan

### Auto-fixed Issues

None beyond minor test design adjustments.

### Test Design Deviation

**`test_force_regenerates` patches `credentials_service.get_provider_credential`**

- **Found during:** Task 3 GREEN phase
- **Issue:** Inside `regenerate`, after `_generate_coffee_rec` returns "generated", the code calls `credentials_service.get_provider_credential(db, "anthropic")` to obtain the `cred` arg for `_generate_sweet_spots_prose`. With a MagicMock `db`, this call chains into `encryption.decrypt(MagicMock)` → TypeError.
- **Fix:** Added `patch.object(ai_service.credentials_service, "get_provider_credential", return_value=mock_cred)` to the `test_force_regenerates` context. Since `_generate_sweet_spots_prose` is also mocked, the cred value is never actually used, making this a pure test isolation fix.
- **No production behavior changed.**

### Ruff Fixes

Pre-existing `E501` violations in the `test_ai_service.py` docstring (`test_citation_projector`) were shortened when I modified the file. All `I001` (import sorting) violations introduced by new test functions were auto-fixed.

## Known Stubs

None. All flows return real data structures or well-defined status strings. The `url_verified=None` on coffee rows is intentional (deferred to 07-05 per plan objective, not a stub).

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond those in the plan's threat model. All four threat register items (T-07-02, T-07-03, T-07-07, T-07-08) are implemented and verified by tests.

## Self-Check: PASSED

All modified files found on disk. All commits verified in git log:
- fafec2f: feat(07-03): recipe-suggestion + alt-brewer SQL sub-flows
- 04e6f3e: feat(07-03): coffee-rec 3-tier flow + provider fallback + sweet-spots prose
- c095c13: feat(07-03): regenerate() entry point + read helpers + locking
