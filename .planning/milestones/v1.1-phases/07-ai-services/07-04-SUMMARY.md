---
phase: 07-ai-services
plan: "04"
subsystem: ai-equipment-paste-rank-flows
tags: [ai, equipment-rec, paste-rank, ssrf, html-parser, tdd]
dependency_graph:
  requires:
    - app/services/ai_service.py (07-01 helpers: _verify_buy_url SSRF pattern, VERIFY_UA, _build_anthropic_client, _build_openai_client, _project_tool_use_input, _write_recommendation_row, SYSTEM_PROMPT_VOICE)
    - app/services/ai_schemas.py (EquipmentRecSchema, PasteRankSchema, RankedCoffeeItem)
    - app/services/analytics.py (get_preference_profile)
    - app/services/credentials.py (get_provider_credential)
    - app/services/settings.py (get_str)
    - app/models/equipment.py (Equipment — type, brand, model, archived)
  provides:
    - app/services/ai_service.py (generate_equipment_rec, rank_pasted_coffees, _fetch_page_text, _split_inputs, _TextExtractor)
  affects:
    - "07-05 (AI router — will call generate_equipment_rec and rank_pasted_coffees)"
tech_stack:
  added:
    - stdlib html.parser (via _TextExtractor subclass — no new dependency)
  patterns:
    - "Profile-only Anthropic call (no web_search server tool) for equipment rec (AI-08/D-05)"
    - "Anthropic→OpenAI provider fallback via _is_anthropic_fallback_error (same pattern as 07-03)"
    - "SSRF-hardened ranged GET for URL extraction — mirrors _verify_buy_url: https-only, follow_redirects=False, 128KB Range, 5s timeout (T-07-09)"
    - "stdlib html.parser subclass (_TextExtractor) extracting p/h1/h2 text, tolerates truncated HTML (assumption A5)"
    - "Dual-input _split_inputs: separates https:// URL lines from freeform text (D-08)"
    - "On-demand telemetry rows (rec_type='equipment'/'paste_rank') never in regenerate() (D-05/D-07)"
    - "PasteRankSchema.model_validate() as return value (not the DB row) — type-safe caller interface"
key_files:
  created: []
  modified:
    - app/services/ai_service.py
    - tests/services/test_ai_service.py
decisions:
  - "generate_equipment_rec reads Equipment via db.execute(select(Equipment).where(archived.is_(False))) — no SQL sub-flow helper needed (single query, always non-signed)"
  - "_TextExtractor uses html.parser subclass (not regex/BeautifulSoup) — stdlib, no dep, handles truncated HTML gracefully per assumption A5"
  - "_split_inputs detects URL lines by http:// or https:// prefix — http:// lines are classified as URLs but _fetch_page_text rejects them on scheme check (SSRF safety maintained)"
  - "rank_pasted_coffees returns PasteRankSchema (validated) not the DB row — keeps the caller interface type-safe and consistent with schema enforcement"
  - "input_signature='' on both on-demand flows — no signature gate applies (D-05/D-07); empty string is intentional, not a stub"
  - "settings_service.get_str patched in all new tests to avoid SettingNotFoundError in test environment"
  - "noqa S110 applied to html.parser except block — intentional bare except-pass per assumption A5 (truncated HTML tolerance)"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-21"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 7 Plan 04: Equipment Rec + Paste-Rank On-Demand Flows Summary

**One-liner:** Equipment weakest-link recommendation (profile-only, no web search) and paste-and-rank flow (dual text/URL input with SSRF-hardened 128KB ranged GET + html.parser extraction), both on-demand with telemetry rows, never participating in signature-based regeneration.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| RED | Failing tests for equipment-rec + paste-rank | ec2c898 | tests/services/test_ai_service.py |
| 1 (GREEN) | Equipment recommendation flow + paste-rank implementation | 572590e | app/services/ai_service.py, tests/services/test_ai_service.py |

## Verification

- `python -m pytest tests/services/test_ai_service.py -q` → **45 passed** (35 from 07-01+07-03 + 10 new)
- `python -m pytest tests/services/test_ai_service.py -k "equipment_rec"` → **4 passed**
- `python -m pytest tests/services/test_ai_service.py -k "paste_rank"` → **7 passed** (including schema test from 07-01)
- `ruff check app/services/ai_service.py tests/services/test_ai_service.py` → **All checks passed**
- `generate_equipment_rec` absent from `regenerate()` body — verified by `test_paste_rank_never_cached`
- `rank_pasted_coffees` absent from `regenerate()` body — verified by `test_paste_rank_never_cached`
- `_fetch_page_text` uses `follow_redirects=False` + `startswith("https://")` scheme guard — verified by tests + grep

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| `generate_equipment_rec` defined and returns status + row | PASS |
| `test_equipment_rec_no_web_search_tool` passes (no web_search tool in anthropic call) | PASS |
| `test_equipment_rec_no_changes` passes (weakest_link=None is valid) | PASS |
| `generate_equipment_rec` absent from `regenerate()` body | PASS |
| `_fetch_page_text` uses `follow_redirects=False` + https scheme guard (T-07-09) | PASS |
| `test_paste_rank_fetch_https_only` passes (http:// rejected, no network call) | PASS |
| `test_paste_rank_fetch_no_cross_host_redirect` passes (302 not followed) | PASS |
| `test_paste_rank_top3` passes (PasteRankSchema enforces <=3 ranked items) | PASS |
| `rank_pasted_coffees` absent from `regenerate()` | PASS |
| Full `python -m pytest tests/services/test_ai_service.py -q` exits 0 | PASS |

## Deviations from Plan

### Implementation Adjustments

**Test patches for `settings_service.get_str`**

- **Found during:** GREEN phase test run
- **Issue:** The new flows call `settings_service.get_str("ai_tool_version_anthropic")` which raises `SettingNotFoundError` in the test environment (no real DB/settings store).
- **Fix:** Added `patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305")` to all four new equipment_rec and paste_rank tests that trigger the implementation path. This is identical to the pattern used implicitly in 07-03 tests.
- **No production behavior changed.**

**Tasks 1 and 2 committed together as one feat commit**

Both flows are in the same file and both test groups were green simultaneously. The RED commit captured all tests; the GREEN commit captured both implementations. This matches the 07-01 precedent.

### Ruff Fixes

- `F811`: Removed duplicate `from pydantic import ValidationError as PydanticValidationError` inside `generate_equipment_rec` (first import at function entry is used throughout)
- `S110`: Added `noqa S110` to the html.parser bare `except Exception: pass` block — intentional per assumption A5
- `F841`: Changed `rec_row = _write_recommendation_row(...)` to `_write_recommendation_row(...)` in `rank_pasted_coffees` since the row is not returned (the function returns `PasteRankSchema.model_validate(raw)`)
- `F401`: Removed unused `EquipmentRecSchema` import and `call` import in test file

## Known Stubs

None. Both flows return real validated schemas or well-defined status strings. `input_signature=""` on on-demand rows is intentional (no signature gate per D-05/D-07), not a data stub.

## Threat Flags

No new network endpoints or auth paths introduced. T-07-09 (SSRF via paste-rank URL) is fully mitigated:
- `_fetch_page_text`: https-only scheme allowlist, `follow_redirects=False`, 128KB Range cap, 5s timeout
- `test_paste_rank_fetch_https_only` and `test_paste_rank_fetch_no_cross_host_redirect` both pass

## Self-Check: PASSED

All modified files found on disk. Commits verified in git log:
- ec2c898: test(07-04): add failing tests for equipment-rec and paste-rank flows
- 572590e: feat(07-04): equipment-rec + paste-rank on-demand flows
