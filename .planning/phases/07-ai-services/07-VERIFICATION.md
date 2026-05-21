---
phase: 07-ai-services
verified: 2026-05-21T00:00:00Z
status: human_needed
score: 17/19 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Hero card end-to-end with a live provider key"
    expected: "With an enabled Anthropic or OpenAI credential and a gate-open user (>=3 sessions, >=5 flavor notes), the home page hero card lazy-loads, shows a single confident pick (name, roaster, why-prose), a buy link (verified / verifying / couldn't verify), add-to-wishlist, and the manual-refresh button. The stale badge appears after logging a new rated session."
    why_human: "No provider credential is currently configured (api_credentials anthropic+openai both is_enabled=false). The hero card's 'generated' branch — including url_verified tri-state rendering and add-to-wishlist happy path — cannot be reached without a live LLM response. Automated tests use mocked SDKs."
  - test: "375px layout — all five AI states and paste-rank/wishlist pages"
    expected: "All five AI hero states (cold-start meter, not-configured, in-flight spinner, try-again, hero card) render without horizontal scroll at 375px. Paste-rank page and wishlist page also pass the 375px check. Human-verify checkpoints in 07-06 and 07-07 were approved for placement and reachable states, but not for the hero card with a real recommendation."
    why_human: "Live hero card with real AI output was not visually verified end-to-end due to missing provider credentials. The 07-06 and 07-07 human-verify checkpoints were approved for the reachable states only."
---

# Phase 7: AI Services Verification Report

**Phase Goal:** Snobbery's differentiator goes live. services/ai_service.py exposes a provider-agnostic API; the live coffee recommendation runs a three-tier web-search fallback (primary → broadened → characteristics-only); structured outputs land via tool_use blocks and pass per-flow Pydantic validation after citation projection; URL verification uses a ranged GET with a realistic User-Agent and a body-contains-name check; an asyncio lock + Postgres advisory lock prevents the scheduler and a manual refresh from racing; the home page shows the new card with a stale-indicator badge when the stored signature drifts; equipment recommendation, alternative-brewer callout, paste-and-rank, and sweet-spots prose all land alongside.

**Verified:** 2026-05-21T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Step 0: Previous Verification

No prior VERIFICATION.md found. Initial verification mode.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Provider-agnostic API in ai_service.py (Anthropic default, OpenAI fallback on non-retryable failures, max_retries=1) | VERIFIED | `_build_anthropic_client` and `_build_openai_client` both pass `max_retries=1`. `_is_anthropic_fallback_error` distinguishes retryable from non-retryable; fallback fires only on `NON_RETRYABLE`, 529, or "overloaded_error" string. |
| 2 | Three-tier web-search fallback (primary → broadened → characteristics-only); search_tier recorded on the row | VERIFIED | `_generate_coffee_rec` at lines 788-934: `tiers = [("primary", primary_max), ("broadened", broadened_max), ("characteristics_only", 0)]`; validated schema receives `model_copy(update={"search_tier": tier_name})`. |
| 3 | Citation projection strips non-tool_use blocks; Pydantic validation gates all outputs; ValidationError → "try_again" | VERIFIED | `_project_tool_use_input` at line 127 keeps only the named `tool_use` block. Every schema has `ConfigDict(extra="forbid")`. All tier-failure paths `continue` to next tier; all tiers exhausted writes error row and returns "try_again". |
| 4 | URL verification uses ranged GET with realistic User-Agent and body-contains-name check; no cross-host redirects; 5s timeout | VERIFIED | `_verify_buy_url`: https-only scheme guard before any network call; `follow_redirects=False`; `Range: bytes=0-65535`; `timeout=httpx.Timeout(5.0)`; `VERIFY_UA` constant. Body check: `roaster_name.lower() in body or coffee_name.lower() in body`. |
| 5 | asyncio lock + Postgres advisory lock prevent concurrent runs from racing | VERIFIED | `regenerate()` at line 1162-1169: `lock.locked()` in-memory check then `async with lock:` then `_try_advisory_lock(db, user_id, "coffee")`. CR-03 (uncaught BaseException) dismissed per review: `pg_try_advisory_xact_lock` is transaction-scoped, auto-released; the advisory lock path does not use BaseException. |
| 6 | Home page shows AI hero card above aggregate cards; stale badge when signature drifts | VERIFIED | `home.html` lines 51-63: `<section aria-labelledby="ai-rec-heading">` with `hx-get="/home/cards/ai-recommendation"` positioned before the aggregate card sections. `ai_rec_hero.html` lines 25-29: stale badge renders when `stale` is True. `is_stale()` compares `compute_input_signature` to stored row's `input_signature`. |
| 7 | Equipment recommendation: profile-only (no web search), on-demand, "no changes recommended" path supported | VERIFIED | `generate_equipment_rec` at line 1227: builds tools list with only `structure_output` tool (no web_search server tool). Never called from `regenerate()`. `equipment_rec.html` renders `weakest_link=None` as "No changes recommended." |
| 8 | Alternative-brewer callout fires only at >=0.5 rating delta | VERIFIED | `alt_brewer_callout` at lines 398-492: explicitly checks `delta >= 0.5` before returning an `AltBrewerSchema`; returns `None` below threshold. |
| 9 | Paste-and-rank: on-demand, never cached, text+URL input, SSRF-hardened URL fetch, top-3 with one-sentence reasoning | VERIFIED | `rank_pasted_coffees` at line 1530; `_fetch_page_text` mirrors `_verify_buy_url` SSRF controls (https-only, `follow_redirects=False`, 5s timeout, `Range: bytes=0-131071`). `PasteRankSchema.ranked` has `max_length=3`. `rank_pasted_coffees` not referenced in `regenerate()`. |
| 10 | Sweet-spots prose generated alongside coffee rec, stored as separate "sweet_spots" row, regenerated together | VERIFIED | `_generate_sweet_spots_prose` at line 579 writes `rec_type="sweet_spots"`. Called from `regenerate()` at line 1197 after the coffee row is written. Same `signature` passed to both rows. |
| 11 | Wishlist CRUD: add/list/mark-purchased/remove, user-scoped, IDOR sentinels, source="ai_recommendation" default | VERIFIED | `wishlist.py`: all reads filter `WishlistEntry.user_id == by_user_id`. `get_wishlist_entry` returns None for cross-user. `mark_purchased` and `remove_entry` return None/False sentinel. `add_to_wishlist` defaults `source="ai_recommendation"`. |
| 12 | All AI POST routes CSRF-enforced, gated by require_user; user_id only from request.state.user.id | VERIFIED | `ai.py` docstring and all handlers: `Depends(require_user)`, user_id from `user.id`. No csrf-exempt decorators found. CR-01 (XSS via source_url) fixed: https-only guard at line 369. CR-05 (empty coffee_name) fixed: 422 guard at line 365. |
| 13 | Manual refresh 429 throttle (5 min per user) + in-flight 429; HX-Retarget on both | VERIFIED | Router lines 180-213: throttle check returns 429 + `HX-Retarget: #ai-rec-hero` + `HX-Reswap: outerHTML`. In-flight check at line 203 returns same 429 structure. |
| 14 | Background task verifies buy_url after generation; url_verified updates on the row | VERIFIED | `_verify_and_persist_url` at line 111: loads latest coffee row, calls `_verify_buy_url`, sets `row.url_verified`, commits. Scheduled via `background_tasks.add_task` at line 222 only on "generated" status. |
| 15 | Cold-start gate: below-gate users see progress meter, not AI card | VERIFIED | `card_ai_recommendation` at line 264: first branch checks `gate["gate_open"]`; returns `ai_rec_cold_start.html` which includes `_cold_start.html`. `regenerate()` also returns "skipped" when gate not open. |
| 16 | Not-configured graceful state when no provider enabled | VERIFIED | `card_ai_recommendation` at line 272-279: both credential lookups None → returns `ai_rec_not_configured.html` with admin configure link. |
| 17 | In-flight polling: ai_rec_in_flight.html has hx-trigger="every 2s"; hero card omits hx-trigger so polling stops | VERIFIED | `ai_rec_in_flight.html` line 7: `hx-trigger="every 2s"`. `ai_rec_hero.html` root div `id="ai-rec-hero"` has no hx-trigger attribute. |
| 18 | Dedicated paste-rank page and wishlist page exist; home links to both; equipment button on home | VERIFIED | `paste_rank.html` exists with `name="input_text"` textarea + CSRF. `wishlist.html` exists with mark-purchased + remove forms + CSRF. `home.html` lines 71-93: `/ai/paste-rank` link, `/ai/wishlist` link, `hx-post="/ai/equipment"` button with `#equipment-rec-result` target. |
| 19 | Hero card end-to-end with real LLM output and all buy-link states exercised | UNCERTAIN | No provider credential is configured. The hero "generated" branch in `ai_rec_hero.html` is correct in code (url_verified tri-state at lines 37-52 is properly wired), but the actual rendered output with a real LLM response has not been confirmed end-to-end. |

**Score:** 18/19 truths verified (1 uncertain — live provider not configured)

---

### REQUIREMENTS.md Traceability Status

The REQUIREMENTS.md checkboxes show AI-04, AI-11, AI-15, AI-17, AI-18 as unchecked "Pending", but the implementations are present in the codebase. This is a tracking discrepancy, not a code gap. Evidence per requirement:

| Requirement | REQUIREMENTS.md Status | Actual Code Status | Evidence |
|---|---|---|---|
| AI-01 | [x] Complete | VERIFIED | max_retries=1 in both client builders; fallback predicate implemented |
| AI-03 | [x] Complete | VERIFIED | Three-tier loop in _generate_coffee_rec; search_tier set per tier |
| AI-04 | [ ] Pending | VERIFIED | _project_tool_use_input strips non-tool_use blocks; ValidationError → try_again in all flows |
| AI-05 | [x] Complete | VERIFIED | _verify_buy_url: https-only, no-redirect, 5s, 64KB, body-contains; background task updates url_verified |
| AI-06 | [x] Complete | VERIFIED | suggest_recipe: pure SQL, existing recipes only, no_match=True path |
| AI-07 | [x] Complete | VERIFIED | alt_brewer_callout: >=0.5 delta threshold enforced |
| AI-08 | [x] Complete | VERIFIED | generate_equipment_rec: no web_search tool; "no changes recommended" path |
| AI-09 | [x] Complete | VERIFIED | rank_pasted_coffees: PasteRankSchema.ranked max_length=3; never in regenerate() |
| AI-10 | [x] Complete | VERIFIED | _generate_sweet_spots_prose writes separate "sweet_spots" row in same regenerate() call |
| AI-11 | [ ] Pending | VERIFIED | gate check in regenerate() + card_ai_recommendation branch; ai_rec_cold_start.html reuses progress meter |
| AI-12 | [x] Complete | VERIFIED | compute_input_signature from user's own sessions; signature skip in regenerate() |
| AI-13 | [x] Complete | VERIFIED | _get_lock (in-memory) + _try_advisory_lock (Postgres); both checked in regenerate() |
| AI-14 | [x] Complete | VERIFIED | 5-min per-user throttle in router; in-flight check; in-flight fragment polls every 2s |
| AI-15 | [ ] Pending | VERIFIED | is_stale() compares current signature to stored row; stale badge in ai_rec_hero.html |
| AI-16 | [x] Complete | VERIFIED | not-configured branch in card_ai_recommendation; ai_rec_not_configured.html fragment |
| AI-17 | [ ] Pending | VERIFIED | max_uses from settings.get_int("ai_primary_max_searches") and "ai_broadened_max_searches") in _generate_coffee_rec |
| AI-18 | [ ] Pending | VERIFIED | All four top-level schemas (CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema) have summary_prose: str field and ConfigDict(extra="forbid") |
| HOME-06 | [x] Complete | VERIFIED | card_sweet_spots passes sweet_spots_prose; sweet_spots.html renders it as escaped text with {% if sweet_spots_prose %} block |

Note: The REQUIREMENTS.md checkbox status for AI-04, AI-11, AI-15, AI-17, AI-18 appears not to have been updated after implementation. The code evidence is unambiguous — all five are implemented.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `app/services/ai_schemas.py` | Per-flow Pydantic schemas with summary_prose + extra="forbid" | VERIFIED | CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema all present with summary_prose and ConfigDict(extra="forbid") |
| `app/services/ai_service.py` | Projector, URL verifier, lock/throttle, telemetry, client builders, fallback predicate, all flow functions, read helpers | VERIFIED | All named functions exist and are substantive |
| `app/services/wishlist.py` | add/list/get/mark-purchased/remove, all user-scoped | VERIFIED | All five functions exist; WishlistEntry.user_id == by_user_id filter present in get and list |
| `app/routers/ai.py` | All AI POST/GET routes, wishlist routes, background URL verify | VERIFIED | router = APIRouter(prefix="/ai"); all required routes present |
| `app/main.py` | ai_router registration | VERIFIED | `from app.routers import ai as ai_router` + `app.include_router(ai_router.router)` at line 233 |
| `app/templates/fragments/home/ai_rec_hero.html` | Composite hero card | VERIFIED | All fields rendered; buy-link tri-state (url_verified True/None/False); stale badge; wishlist form; refresh form |
| `app/templates/fragments/home/ai_rec_in_flight.html` | Polling fragment with hx-trigger="every 2s" | VERIFIED | hx-trigger="every 2s" on root div; animate-pulse spinner |
| `app/templates/fragments/home/ai_rec_cold_start.html` | Cold-start fragment reusing progress meter | VERIFIED | {% include "fragments/home/_cold_start.html" %} |
| `app/templates/fragments/home/ai_rec_not_configured.html` | Not-configured state with admin link | VERIFIED | Admin configure link present |
| `app/templates/fragments/home/ai_rec_try_again.html` | Try-again state with retry form | VERIFIED | Form posting to /ai/refresh with CSRF field |
| `app/templates/fragments/home/sweet_spots.html` | HOME-06 prose append | VERIFIED | {% if sweet_spots_prose %} block rendering prose as escaped text |
| `app/templates/fragments/home/equipment_rec.html` | Equipment result fragment | VERIFIED | Handles generated/not_configured/other; "no changes recommended" path |
| `app/templates/pages/paste_rank.html` | Paste-and-rank page with textarea | VERIFIED | name="input_text" textarea; hx-post="/ai/paste-rank"; CSRF field |
| `app/templates/pages/wishlist.html` | Wishlist minimal view | VERIFIED | Mark-purchased + Remove forms with CSRF; purchased badge |
| `app/templates/pages/home.html` | AI hero slot above aggregate cards; links to paste-rank/wishlist; equipment button | VERIFIED | hx-get="/home/cards/ai-recommendation" above aggregate cards; /ai/paste-rank + /ai/wishlist links; hx-post="/ai/equipment" with #equipment-rec-result target |

---

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app/services/ai_service.py` | `app/services/ai_schemas.py` | `from app.services.ai_schemas import CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema` | WIRED | Import at lines 55-62 |
| `app/services/ai_service.py` | `app/events.py` | `from app.events import AI_GENERATION_START, ...` | WIRED | All 8 ai.* events imported at lines 37-46 |
| `app/routers/ai.py` | `app/services/ai_service.py::regenerate` | `regenerate(user.id, "manual_refresh", db=db, force=True)` | WIRED | Line 218 |
| `app/main.py` | `app/routers/ai.py` | `from app.routers import ai as ai_router` + `app.include_router(ai_router.router)` | WIRED | Lines 85 and 233 |
| `app/templates/pages/home.html` | `/home/cards/ai-recommendation` | `hx-get="/home/cards/ai-recommendation"` | WIRED | Line 55 |
| `app/routers/home.py::card_ai_recommendation` | `ai_service.get_latest_recommendation / is_stale / in_flight` | Direct calls in handler body | WIRED | Lines 282, 290, 307 |
| `app/routers/home.py::card_sweet_spots` | `ai_service.get_latest_recommendation` rec_type="sweet_spots" | `ss_row = ai_service.get_latest_recommendation(db, user_id=user.id, rec_type="sweet_spots")` | WIRED | Lines 227-231 |
| `app/services/ai_service.py::regenerate` | `analytics.compute_input_signature` | signature compare for skip decision | WIRED | Lines 1172 |
| `app/services/ai_service.py` | `credentials.get_provider_credential` | anthropic-then-openai provider lookup | WIRED | Lines 773-774, 1202-1204 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `ai_rec_hero.html` | `rec` (AIRecommendation), `prose` (response_json dict), `stale` (bool) | `card_ai_recommendation` in home.py calls `get_latest_recommendation`, `is_stale` | DB query + signature computation — code wiring is correct. No real row exists in current state (no provider configured). | WIRED — data path correct; live data needs human verify |
| `sweet_spots.html` | `sweet_spots_prose` | `card_sweet_spots` in home.py calls `get_latest_recommendation(rec_type="sweet_spots")` and extracts `response_json.get("summary_prose")` | Correct DB query; no real row exists currently. | WIRED — data path correct |
| `paste_rank_results.html` | `results` (PasteRankSchema) | `post_paste_rank` in ai.py calls `rank_pasted_coffees`, passes result to template | Template receives schema on success; never cached. | WIRED |
| `equipment_rec.html` | `rec` (EquipmentRecSchema or None), `status` | `post_ai_equipment` validates `_row.response_json` via `EquipmentRecSchema.model_validate` | Correct on generated path; WR-05 warning: schema re-validation failure is silently logged but status mismatch is not corrected. | WIRED (with WR-05 caveat) |
| `wishlist.html` | `entries` (list[WishlistEntry]) | `get_wishlist_page` calls `list_wishlist(db, by_user_id=user.id)` | DB query filtered by user_id desc. | WIRED |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| ai_schemas import and summary_prose present | `docker compose exec coffee-snobbery python -c "from app.services.ai_schemas import CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema; assert all('summary_prose' in s.model_fields for s in [CoffeeRecSchema, SweetSpotsProseSchema, EquipmentRecSchema, PasteRankSchema]); print('ok')"` | Not run (Docker not available in verifier context) | SKIP (test suite already covers this: 542 passed) |
| Test suite passes | Reported: 542 passed, 2 skipped, 10 xfailed, 0 failures | Pass reported by operator | PASS (operator-verified) |

Step 7b: SKIPPED for live API calls (no provider configured; test suite substitutes with mocked SDK clients).

---

### Probe Execution

Step 7c: No probe scripts found under `scripts/*/tests/probe-*.sh`. SKIPPED.

---

### Requirements Coverage

All 19 requirements assigned to Phase 7 (AI-01, AI-03–AI-18, HOME-06) are implemented in the codebase. The REQUIREMENTS.md checkbox status is a tracking artifact that does not reflect actual implementation state for AI-04, AI-11, AI-15, AI-17, AI-18. All five are verified present and wired.

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| AI-01 | 07-01, 07-03 | Provider abstraction, max_retries=1, fallback predicate | SATISFIED | Client builders pass max_retries=1; _is_anthropic_fallback_error distinguishes non-retryable/529 from rate-limit |
| AI-03 | 07-01, 07-03 | Three-tier web-search fallback with tier recorded | SATISFIED | Tier loop in _generate_coffee_rec; search_tier set via model_copy |
| AI-04 | 07-01, 07-06 | Citation projection + try_again UI | SATISFIED | _project_tool_use_input + ValidationError → try_again path; ai_rec_try_again.html fragment |
| AI-05 | 07-01, 07-05, 07-06 | URL verification ranged GET, SSRF-hardened, tri-state UI | SATISFIED | _verify_buy_url + _verify_and_persist_url background task + buy-link tri-state in ai_rec_hero.html |
| AI-06 | 07-03, 07-06 | Recipe suggestion from existing recipes only | SATISFIED | suggest_recipe: SQL only, no fabrication, no_match path |
| AI-07 | 07-03, 07-06 | Alt-brewer >=0.5 delta threshold | SATISFIED | alt_brewer_callout: delta >= 0.5 check |
| AI-08 | 07-04, 07-07 | Equipment rec profile-only no web search, "no changes" path | SATISFIED | generate_equipment_rec: no web_search tool; equipment_rec.html "no changes" path |
| AI-09 | 07-04, 07-07 | Paste-and-rank top-3, one-sentence reasoning, never cached | SATISFIED | PasteRankSchema max_length=3; rank_pasted_coffees not in regenerate() |
| AI-10 | 07-03, 07-06 | Sweet-spots prose generated + cached with coffee row | SATISFIED | _generate_sweet_spots_prose writes separate "sweet_spots" row in same regenerate() |
| AI-11 | 07-03, 07-06 | Cold-start gate (>=3 sessions, >=5 flavor notes) | SATISFIED | gate check in regenerate() + card_ai_recommendation; ai_rec_cold_start.html |
| AI-12 | 07-03 | Signature based on user's own sessions | SATISFIED | compute_input_signature scoped to user; unchanged sig skips regeneration |
| AI-13 | 07-01, 07-03, 07-05 | In-memory + advisory lock prevent concurrent runs | SATISFIED | _get_lock + _try_advisory_lock in regenerate(); in-flight 429 in router |
| AI-14 | 07-05, 07-06 | Manual refresh throttle 5 min; spinner; swap on completion | SATISFIED | 300s throttle in router; in-flight fragment polls every 2s |
| AI-15 | 07-03, 07-06 | Stale badge when signature drifts | SATISFIED | is_stale() + stale badge in ai_rec_hero.html |
| AI-16 | 07-05, 07-06 | Graceful not-configured state | SATISFIED | card_ai_recommendation not-configured branch; ai_rec_not_configured.html |
| AI-17 | 07-01, 07-03 | max_uses from app_settings (configurable) | SATISFIED | primary_max and broadened_max from settings_service.get_int() |
| AI-18 | 07-01 | All schemas have summary_prose + per-flow Pydantic validation | SATISFIED | All four top-level schemas: summary_prose field present, ConfigDict(extra="forbid") |
| HOME-06 | 07-03, 07-06 | AI prose below Sweet Spots when available | SATISFIED | card_sweet_spots passes sweet_spots_prose; sweet_spots.html renders as escaped text |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `app/routers/ai.py` | 289 | `except Exception:` (bare, no log) on EquipmentRecSchema re-validation | Warning (WR-05 from review) | Schema mismatch is silently logged but status is not corrected to "try_again"; template renders error path while service returned "generated". Low probability since service validates before writing. |
| `app/services/ai_service.py` | ~613-631 | `_generate_sweet_spots_prose` declared `async def` but makes synchronous `client.messages.create()` call | Warning (WR-02 from review) | Blocks event loop during LLM call. Household-scale single worker; accepted per WR-02 comment "intentional at household scale." |
| `app/services/ai_service.py` | ~963, ~1208 | `AI_GENERATION_SUCCESS` logged twice per coffee rec (once in _generate_coffee_rec, once in regenerate) | Info (WR-06 from review) | Double-counting in log queries. No functional impact. |
| `app/routers/ai.py` | 99-103 | `_PLEASE_WAIT_HTML` fallback constant is stale now that the real template exists | Info (IN-02 from review) | Not a defect; could be cleaned up. |
| `tests/services/test_ai_service.py` | 334-344 | `_make_db_with_sessions` helper is dead code | Info (IN-01 from review) | No functional impact. |
| `tests/routers/test_ai_router.py` | 188-205 | `test_throttle_429` mock may pass for wrong reason (WR-01) | Warning | Test may not exercise the actual throttle path. Does not affect shipped code; masks a potential test coverage gap. |

No TBD/FIXME/XXX markers found in phase-modified files that lack issue references.

No `|safe` filter found in any of the six AI template files created in this phase (confirmed by grep: the `safe` occurrences in sweet_spots.html, ai_rec_try_again.html, etc. are within Jinja comment text, not actual filter applications).

---

### Human Verification Required

#### 1. Hero Card with Live Provider Credential

**Test:** Configure an enabled Anthropic or OpenAI API key in admin. With a gate-open user (>=3 brew sessions, >=5 distinct flavor notes observed), load the home page at 375px. Allow the hero card to lazy-load.

**Expected:**
- The card displays a single confident pick: coffee name, roaster, origin/process/roast, summary_prose.
- The buy link shows one of three states: "Buy" (verified, clickable), "verifying link…" (italic span), or plain URL + "(couldn't verify)".
- "Save to wishlist" button is present and submitting it creates a wishlist entry visible at /ai/wishlist.
- "Refresh recommendation" button triggers the spinner + eventual card swap.
- After logging a new rated session, reload: stale badge ("New brews logged — recommendation may be outdated") appears.
- No horizontal scroll at 375px.

**Why human:** No provider credential is configured. The "generated" branch of the hero card — including real AI output, url_verified tri-state, and the full add-to-wishlist flow — cannot be reached without a live LLM response. Test suite uses mocked SDKs.

#### 2. 375px Layout — All Reachable States

**Test:** Rebuild the Docker image and verify all five AI hero states at 375px. Paste-rank page and wishlist page also at 375px.

**Expected:**
- Cold-start state: progress meter renders cleanly (already confirmed in Phase 6).
- Not-configured state: "AI recommendations are not configured yet." renders without layout issues.
- In-flight spinner: animate-pulse + "Searching the web for fresh coffees…" renders cleanly; polls every 2s.
- Try-again state: message + Try again button.
- Paste-rank page: textarea fills width, Rank button accessible, results region appears after submission.
- Wishlist page: entries list with Mark purchased + Remove buttons; purchased entries dimmed with badge.

**Why human:** 07-06 and 07-07 human-verify checkpoints were approved for placement and reachable states, but not for the hero card with a real LLM recommendation. The cold-start, not-configured, and in-flight states were approved; hero card and try-again states were not explicitly confirmed at 375px with real data.

---

### Gaps Summary

No BLOCKER gaps found. All 19 phase requirements are implemented in the codebase. The phase goal is substantially achieved: the provider-agnostic service layer, three-tier web-search fallback, citation projection, Pydantic validation, URL verification, concurrency locking, stale badge, and all four AI flows (coffee rec, sweet-spots prose, equipment rec, paste-and-rank) are present, substantive, and wired.

Two WARNING-level items from the code review remain open:

- **WR-05:** `post_ai_equipment` bare `except Exception` silently handles EquipmentRecSchema re-validation failure without correcting `status` to "try_again". Low probability in practice since the service validates before writing.
- **WR-02:** `_generate_sweet_spots_prose` blocks the event loop with a synchronous SDK call inside `async def`. Accepted at household scale; documented in a code comment.

These are warnings, not blockers. The phase status is `human_needed` because live end-to-end AI flow verification (with a real provider key) was explicitly deferred as a known limitation.

---

_Verified: 2026-05-21T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
