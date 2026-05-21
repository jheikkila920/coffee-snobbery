---
phase: 06-analytics-home-page
verified: 2026-05-20T00:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
---

# Phase 6: Analytics (Home Page) Verification Report

**Phase Goal:** The home page renders for a user with >=3 sessions: recent brews eager-loaded, every analytics card lazy-loaded via HTMX with staggered triggers (`load delay:Nms` per section, the AI section deferred to Phase 7), every query pure SQL with explicit indexes, and the stale-data signature plumbing (`compute_input_signature`) in place so Phase 7's AI card can later decide whether a recommendation is stale. Cold-start path: a user with <3 sessions OR <5 distinct observed flavor notes sees a friendly empty state with a progress meter. HOME-06 (AI prose) is OUT OF SCOPE — Phase 7.
**Verified:** 2026-05-20
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A user with >=3 sessions sees all 7 SQL-derived cards (top coffees, preference profile, flavor descriptors, roast freshness, sweet spots, recent brews, unrated coffees) | ✓ VERIFIED | `analytics.py` has all 9 functions (8 derivations + cold-start); each rendered by a fragment template + lazy slot in `home.html`. Probe: all 9 functions present. 30 unit/router tests pass. |
| 2 | Recent brews are eager-loaded (no HTMX request on first paint) | ✓ VERIFIED | `home.html:24` uses `{% include "fragments/home/recent_brews.html" %}` (server-side include); `home_shell` calls `get_recent_brews` eagerly (`home.py:56`). |
| 3 | Every analytics card lazy-loads via HTMX with staggered `load delay:Nms` triggers | ✓ VERIFIED | `home.html` has 6 `hx-trigger="load delay:Nms"` (unrated 150ms + 5 aggregate cards 100/200/300/400/500ms). Template probe: "6 staggered triggers". |
| 4 | The AI section is deferred to Phase 7, not shipped as a live trigger | ✓ VERIFIED | `home.html:115` is a Jinja comment only (`{# Phase 7: AI recommendation card slot ... Do not implement here. #}`). Probe confirms no live `hx-get="/home/cards/ai-recommendation"` or `hx-trigger="revealed"` outside the comment. |
| 5 | Every query is pure SQL with explicit indexes (no Python aggregation loops) | ✓ VERIFIED | `analytics.py` uses `select()` + GROUP BY/HAVING; HOME-03/cold-start use parameterized `text()` lateral unnest (bound `:user_id`, single round-trip, no Python loop — A2 limitation, documented). No `db.query()` legacy API. Uses Phase 5 indexes (no new migration). |
| 6 | `compute_input_signature` plumbing is in place, deterministic, user-scoped | ✓ VERIFIED | `analytics.py:359` — sha256 over canonical JSON of RATED sessions only, ordered by `BrewSession.id`, excludes free-text/timestamps, `_EMPTY_SIGNATURE` sentinel = sha256(b"[]"). Signature determinism/order-independence/free-text-exclusion/zero-rated-sentinel tests pass. |
| 7 | Cold-start path: <3 sessions OR <5 distinct notes shows a friendly empty state with a progress meter | ✓ VERIFIED | `home.html:43` branches on `gate.gate_open`; false branch includes `_cold_start.html` with `role="progressbar"`, server-computed pct, and 3-branch dynamic copy. `get_cold_start_counts` gate_open = sessions>=3 AND distinct_notes>=5. `test_cold_start_branch_renders_meter` passes. |
| 8 | HOME-04 reads `bags.roast_date`, never `coffees.roast_date` | ✓ VERIFIED | `get_roast_freshness_buckets` INNER JOINs `Bag`, reads `Bag.roast_date` only. Grep: zero `Coffee.roast_date` references in `analytics.py`. |
| 9 | HOME-03 reads the OBSERVED array, never advertised flavor notes | ✓ VERIFIED | `get_flavor_descriptors` unnests `bs.flavor_note_ids_observed`. Grep: only docstring mention of `advertised_flavor_note_ids` (as a "never use" note), no code reference. |
| 10 | HOME-08 excludes archived coffees | ✓ VERIFIED | `get_unrated_coffees` WHERE includes `Coffee.archived == False` (`analytics.py:305`). `test_unrated_coffees` asserts the seeded archived coffee is excluded. |
| 11 | Every analytics derivation runs <50ms against a 1000-session seed (ROADMAP SC2) | ✓ VERIFIED | `test_analytics_query_latency` passes. Measured medians (1000-session seed, 700 rated): top_coffees 2.3ms, preference_profile 12.2ms, flavor_descriptors 2.1ms, roast_freshness 3.3ms, sweet_spots 3.2ms, recent_brews 1.1ms, unrated_coffees 1.0ms, cold_start 2.1ms, signature 8.6ms — all well under 50ms. |
| 12 | The home shell + every fragment endpoint is auth-gated (require_user → 401 unauthenticated) | ✓ VERIFIED | All 8 handlers declare `Depends(require_user)`; `user.id` is the only `user_id` source (IDOR defense). `test_home_unauthenticated_returns_401`, `test_unrated_coffees_fragment_requires_auth`, `test_*_requires_auth` pass. |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/analytics.py` | 9 pure-SQL functions + signature | ✓ VERIFIED | 409 lines; all 9 functions present, per-user scoped, D-06/D-07 floors, rating-NULL handling. Import probe + ruff pass. |
| `app/routers/home.py` | Shell + 7 fragment endpoints, auth-gated | ✓ VERIFIED | 8 handlers, all `Depends(require_user)` + `Depends(get_session)`, `user.id`-scoped. Route probe: all 8 routes registered. |
| `app/templates/pages/home.html` | Eager shell + gate branch + 5 staggered slots + Phase 7 comment | ✓ VERIFIED | Extends base.html; gate branch; 6 staggered triggers; Phase 7 comment-only AI slot; CSP-clean. |
| `app/templates/fragments/home/_cold_start.html` | Progress meter empty state | ✓ VERIFIED | `role="progressbar"`, server-computed pct, 3-branch dynamic copy. |
| `app/templates/fragments/home/recent_brews.html` | Card list with edit links | ✓ VERIFIED | Card list at all viewports; Edit → `/brew/{id}/edit` (live route confirmed); Brew-again link; empty state present. |
| `app/templates/fragments/home/unrated_coffees.html` | Catalog suggestions | ✓ VERIFIED | Log-session links with aria-label; empty state present. |
| 5 aggregate card templates + `_card_sparse.html` | SQL-derived bodies + sparse/all-unrated hints | ✓ VERIFIED | All 6 files exist, render real data, include `_card_sparse.html` on empty; sweet_spots has no AI placeholder. |
| `tests/services/test_analytics.py` | 13 seeded-DB unit tests | ✓ VERIFIED | 13 tests pass (incl. signature determinism, archived exclusion, all-unrated). |
| `tests/services/test_analytics_perf.py` | 1000-session <50ms check | ✓ VERIFIED | 1 test, seeds exactly 1000 sessions, asserts <50ms per query; passes. |
| `tests/routers/test_home.py` | 17 router smoke tests | ✓ VERIFIED | 17 tests pass (auth gate, cache headers, gate branches, sparse/all-unrated, no-AI-placeholder guard). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `app/main.py` | `app/routers/home.py` | `include_router` + placeholder removal | ✓ WIRED | Import at `main.py:93`, include at `main.py:231`; zero `pages/index` references remain. |
| `home.html` | `/home/cards/*` endpoints | `hx-get` + `hx-trigger="load delay:"` | ✓ WIRED | 6 lazy slots reference registered endpoints; all resolve (route probe). |
| `home.py` | `analytics.py` | per-card `analytics.get_*(db, user.id)` | ✓ WIRED | All 7 card handlers + shell call analytics scoped to `user.id`. |
| `analytics.py` | `brew_sessions` table | `select().where(BrewSession.user_id == user_id)` | ✓ WIRED | First WHERE clause on every query (IDOR defense). |
| `compute_input_signature` | `hashlib.sha256` over canonical JSON | `json.dumps(sort_keys=True)` of rated-session fields | ✓ WIRED | `analytics.py:407-408`. |
| `home.html` Edit link | `/brew/{id}/edit` | anchor href | ✓ WIRED | brew router prefix `/brew` + `@router.get("/{session_id}/edit")` = live route (HOME-07). |
| aggregate card templates | `_card_sparse.html` | `{% include %}` with hint_type | ✓ WIRED | All 5 rating/sparse cards include the partial on empty branch. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `home.html` recent brews | `recent_brews` | `analytics.get_recent_brews(db, user.id)` (real `select` join) | Yes (measured 1.1ms over 1000-seed) | ✓ FLOWING |
| `home.html` gate branch | `gate` | `analytics.get_cold_start_counts` (live counts) | Yes | ✓ FLOWING |
| aggregate cards | `rows`/`profile` | per-card `analytics.get_*` (real GROUP BY) | Yes (perf test confirms rows aggregated) | ✓ FLOWING |
| `compute_input_signature` | rated rows | `select` over rated sessions | Yes (8.6ms over 700 rated rows) | ✓ FLOWING |

No hollow props or hardcoded empty data found. All template data flows from live DB queries.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 8 home routes register, placeholder gone | `create_app` route-set probe | "routes ok — all 8 home routes registered, placeholder gone" | ✓ PASS |
| Analytics public surface complete | import + signature inspection probe | "analytics ok — 9 functions, compute_input_signature(db,user_id)" | ✓ PASS |
| Empty signature sentinel correct | `_EMPTY_SIGNATURE == sha256(b"[]")` | matches | ✓ PASS |
| Template CSP/stagger/AI-slot | regex probe over home templates | "6 staggered triggers, AI slot comment-only, no live AI trigger, CSP-clean" | ✓ PASS |
| Analytics unit + router tests | `pytest test_analytics.py test_home.py -q` | 30 passed | ✓ PASS |
| 1000-session latency (ROADMAP SC2) | `pytest test_analytics_perf.py -q` | 1 passed; all 9 functions <50ms (max 12.2ms) | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared for this phase; verification uses the plan-declared automated probes + pytest (run above). N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HOME-01 | 06-01, 06-03 | Top 5 coffees by avg rating, min 2 sessions | ✓ SATISFIED | `get_top_coffees` + `top_coffees.html`; `test_top_coffees` passes. |
| HOME-02 | 06-01, 06-03 | Preference profile by origin/process/roaster/roast level | ✓ SATISFIED | `get_preference_profile` (4 GROUP BYs) + `preference_profile.html`. |
| HOME-03 | 06-01, 06-03 | Top-10 flavor descriptors in 4.0+ sessions | ✓ SATISFIED | `get_flavor_descriptors` (observed array) + `flavor_descriptors.html`. |
| HOME-04 | 06-01, 06-03 | Roast freshness buckets from `bags.roast_date` | ✓ SATISFIED | `get_roast_freshness_buckets` (bags.roast_date) + `roast_freshness.html`. |
| HOME-05 | 06-01, 06-03 | Top 3 sweet spots (origin×process×brewer×recipe), min 3 | ✓ SATISFIED | `get_sweet_spots` (single GROUP BY, no loops) + `sweet_spots.html`. |
| HOME-06 | (Phase 7) | AI prose below sweet spots | ⏭ DEFERRED | Intentionally Phase 7; REQUIREMENTS.md maps HOME-06 → Phase 7. Phase 6 ships only the `compute_input_signature` helper + comment slot. Correctly NOT a Phase 6 gap. |
| HOME-07 | 06-01, 06-02 | Recent 10 brews with edit links | ✓ SATISFIED | `get_recent_brews` + `recent_brews.html`; Edit → live `/brew/{id}/edit`. |
| HOME-08 | 06-01, 06-02, 06-03 | Unrated coffees (archived excluded) | ✓ SATISFIED | `get_unrated_coffees` (archived==False) + `unrated_coffees.html`. |
| HOME-09 | 06-02, 06-03 | Each section lazy-loads via HTMX, staggered | ✓ SATISFIED | 6 staggered `load delay:Nms` slots in `home.html`. |

All 8 phase-declared requirement IDs (HOME-01..05, 07, 08, 09) are satisfied. HOME-06 is correctly deferred to Phase 7. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TODO/FIXME/XXX/TBD/PLACEHOLDER debt markers in any phase-6 file | ℹ️ Info | Clean — completion is auditable. |
| `analytics.py` | 141 | docstring mentions `advertised_flavor_note_ids` | ℹ️ Info | Documentation of the "never use" rule, not a code reference. No impact. |
| `home.py` | 3, 222 | docstring/comment mention "placeholder" | ℹ️ Info | Documents removed Phase 0 placeholder + no-AI-placeholder guard. No impact. |

### Advisory Items (from 06-REVIEW.md — non-blocking)

The code review found 0 blockers and 4 warnings. None defeat a must-have:

- **WR-01:** Cold-start gate counts flavor-note IDs that may not reference real flavor notes. Edge case; gate still functions. Advisory.
- **WR-02:** Roast-freshness buckets absorb sessions brewed before the roast date into the `0-3 days` bucket (negative day-count). Edge case; HOME-04 still derives from `bags.roast_date`. Advisory.
- **WR-03:** `cast(brewed_at, Date)` is session-timezone dependent. Edge case at day boundaries. Advisory.
- **WR-04:** `<div>` elements are direct children of `<ul>` in three card fragments (invalid HTML). Renders correctly in browsers; cosmetic/validity. Advisory.

These are recommended cleanups but do not block the phase goal.

### Human Verification Required

None. All truths were verifiable programmatically (route probes, import probes, template probes, seeded-DB tests, and measured latency). The phase goal is observable in the codebase and confirmed by the running container.

Optional (not blocking): visual confirmation at 375px viewport that the staggered lazy-load and progress meter render as intended — this is a UI-polish check, not a goal blocker, and the mobile-first markup (single column, no `md:` except preference profile) is present in source.

### Gaps Summary

No gaps. All 12 observable truths are verified, all 10 required artifacts pass all four levels (exist, substantive, wired, data-flowing), all 7 key links are wired, all 8 phase requirement IDs are satisfied, HOME-06 is correctly deferred to Phase 7, no new migration was added (Phase 5 indexes confirmed sufficient by the measured <50ms latencies), and no blocker anti-patterns exist. The phase goal is achieved.

---

_Verified: 2026-05-20_
_Verifier: Claude (gsd-verifier)_
