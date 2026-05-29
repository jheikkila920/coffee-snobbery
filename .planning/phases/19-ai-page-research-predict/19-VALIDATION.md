---
phase: 19
slug: ai-page-research-predict
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-28
validated: 2026-05-29
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source map: `19-RESEARCH.md` § "Validation Architecture". Per-task IDs are
> populated by the planner/executor once PLAN.md waves exist.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (+ respx for AI HTTP mocking) |
| **Config file** | `pyproject.toml` / `pytest.ini` (existing) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/services/test_ai_research.py tests/services/test_ai_quota.py -x -q` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~60-120 seconds (full suite) |

> Note: pytest is NOT baked into the production image — install it into the
> running container first (`pip install --user pytest pytest-asyncio respx`) or
> use the `coffee-snobbery-test` compose profile. Copy changed test files in
> with `docker compose cp tests/ coffee-snobbery:/app/tests/` (file-level cp —
> dir-level cp nests, per project memory) or rebuild before exercising.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/services/test_ai_research.py tests/services/test_ai_quota.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green + SSE smoke test through NPM
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

> Every row below was re-verified on 2026-05-29 against the executed test tree
> by name (not just `-k` filter) and run green in the baked `coffee-snobbery-test`
> image. Status = ✅ green for all rows. Each `::test_name` / `-k` reference was
> confirmed to collect ≥1 test (no vacuous filters) per project memory.

| Req ID | Behavior | Test Type | Automated Command | Status |
|--------|----------|-----------|-------------------|--------|
| AIX-01 | CoffeeResearchSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_ai_research.py::test_coffee_research_schema_validates -x` | ✅ |
| AIX-01 | Cache miss triggers LLM call; cache hit skips LLM | unit (mock) | `pytest tests/services/test_ai_research.py -k "cache_miss or cache_hit" -x` | ✅ (2 tests) |
| AIX-02 | RatingPredictionSchema renders range (never single point) | unit | `pytest tests/services/test_ai_research.py::test_rating_prediction_schema -x` | ✅ |
| AIX-03 | Research endpoint blocks when gate_open=False | integration | `pytest tests/routers/test_ai_research.py::test_research_blocked_below_gate -x` | ✅ |
| AIX-04 | Cache key normalizes case + whitespace; hits same row | unit | `pytest tests/services/test_ai_research.py::test_cache_key_normalization -x` | ✅ |
| AIX-04 | Expired cache row evicted on read, triggers new LLM call | unit | `pytest tests/services/test_ai_research.py::test_expired_cache_eviction -x` | ✅ |
| AIX-05 | Quota counter returns correct remaining count | unit | `pytest tests/services/test_ai_quota.py::test_quota_count -x` | ✅ |
| AIX-05 | POST /ai/research returns 429 when quota exhausted | integration | `pytest tests/routers/test_ai_research.py::test_research_429_quota_exhausted -x` | ✅ |
| AIX-05 | Reset time computed from oldest call in window | unit | `pytest tests/services/test_ai_quota.py::test_reset_time_computation -x` | ✅ |
| AIX-06 | POST /ai/wishlist/add accepts research-sourced fields | integration (existing) | `pytest tests/routers/test_ai_router.py -k wishlist_add -x` | ✅ (4 tests) |
| AIX-07 | SSE generator yields `event: message` then `event: complete` in order | unit (mock) | `pytest tests/services/test_ai_research.py::test_sse_event_contract -x` | ✅ |
| AIX-07 | Advisory lock blocks duplicate in-flight SSE request | unit | `pytest tests/services/test_ai_research.py::test_advisory_lock_blocks_duplicate -x` | ✅ |
| AIX-09 | PreferenceProfileProseSchema: summary_prose + extra=forbid | unit | `pytest tests/services/test_preference_prose.py::test_preference_prose_schema -x` | ✅ |
| AIX-10 | `.htmx-indicator` styles present in tailwind.src.css (CSP-clean) | behavioral | `pytest tests/templates/test_ai_page_phase19.py::test_tailwind_has_htmx_indicator -x` | ✅ (corrected¹) |
| AIX-11 | RecipeSuggestionSchema raises ValidationError on `no_match` field | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_no_match_rejected -x` | ✅ |
| AIX-11 | RecipeSuggestionSchema requires ratio, temp_c, grind_hint | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_required_fields -x` | ✅ |
| AIX-12 | BrewImproveSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_brew_improve.py::test_brew_improve_schema -x` | ✅ |
| AIX-12 | POST /ai/improve-brew/{session_id} returns 404 on cross-user session | integration | `pytest tests/routers/test_ai_improve.py::test_improve_brew_cross_user_404 -x` | ✅ |
| AIX-13 | duration_ms written for all new rec_types | unit (mock) | `pytest tests/services/test_ai_research.py::test_duration_ms_written -x` | ✅ |
| AIX-13 | p50/p95 latency query executes against existing data | integration | `pytest tests/services/test_analytics_perf.py::test_latency_percentile_query -x` | ✅ |
| VIZ-01 | GET /ai/charts/rating-over-time returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_rating_chart_json -x` | ✅ |
| VIZ-01 | GET /ai/charts/flavor-distribution returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_flavor_chart_json -x` | ✅ |
| D-06 | ai_coffee_research_cache table created by migration | migration | `pytest tests/test_migrations.py::test_ai_coffee_research_cache_table_exists -x` | ✅ |
| D-07 | ai_rating_predictions table + UNIQUE(user_id, research_cache_key) | migration | `pytest tests/test_migrations.py::test_ai_rating_predictions_table_and_constraints -x` | ✅ |
| D-14 | _verify_buy_url returns False on 404/410 | unit | `pytest tests/services/test_archived_retry.py::test_verify_url_rejects_404 -x` | ✅ |
| D-14 | Coffee rec flow retries with broader search on verify failure | unit (mock) | `pytest tests/services/test_archived_retry.py::test_archived_retry_logic -x` | ✅ |

¹ **AIX-10 command corrected during this audit.** The planner draft referenced
`tests/test_pwa.py -k htmx_indicator`, which collects **0 tests** (vacuous filter —
no such test in that file). The behavior is actually covered by
`tests/templates/test_ai_page_phase19.py::test_tailwind_has_htmx_indicator`
(asserts both `.htmx-indicator` and `.htmx-request .htmx-indicator` in
`tailwind.src.css`). Command above points at the real test.

### Gap-Closure Coverage (plans 19-08 / 19-09 — not in planner draft)

> Added after the phase was reopened for the orphaned-SSE-stub XSS gap and the
> cost-control gap. These tests exist and run green; the original draft predates them.

| Req ID | Behavior | Test Type | Automated Command | Status |
|--------|----------|-----------|-------------------|--------|
| AIX-07 / CR-01 | research `event:complete` renders via Jinja autoescape (not f-string) | security/unit | `pytest tests/services/test_ai_research.py::test_render_research_result_uses_jinja_template -x` | ✅ |
| AIX-01 / CR-01 | adversarial `coffee_name` is HTML-escaped (stored-XSS closed) | security/unit | `pytest tests/services/test_ai_research.py -k "escapes_adversarial or escapes_onerror" -x` | ✅ (2 tests) |
| AIX-12 / CR-02 | improve-brew `event:complete` renders HTML template, not raw JSON | security/unit | `pytest tests/services/test_brew_improve.py -k "renders_html_template or not_raw_json or escapes_adversarial" -x` | ✅ (3 tests) |
| AIX-02 / WR-02 | cache-hit prediction is committed and reused (no re-fire) | unit (mock) | `pytest tests/services/test_ai_research.py::test_cache_hit_prediction_committed_and_reused -x` | ✅ |
| AIX-02 / WR-03 | signature change within TTL does NOT trigger LLM regen; TTL expiry does | unit (mock) | `pytest tests/services/test_ai_research.py -k "does_not_trigger_regen_within_ttl or regen_fires_on_ttl_expiry" -x` | ✅ (2 tests) |
| AIX-05 / WR-05 | `format_reset` clamps countdown to ≥0 (no negative "Resets in") | unit | `pytest tests/services/test_ai_quota.py -k format_reset -x` | ✅ (4 tests) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Audited run (2026-05-29):** all 14 Phase 19 test files in the baked
`coffee-snobbery-test` image → **185 passed, 0 skipped, 0 failed** (`-rs`
confirmed no pass-by-skip masking).

---

## Wave 0 Requirements

- [x] `tests/services/test_ai_research.py` — schema validation, cache logic, SSE event contract, advisory lock (+ CR-01 XSS / WR-02 / WR-03 gap-closure)
- [x] `tests/services/test_ai_quota.py` — rolling-24h COUNT, reset-time computation, admin cap reader (+ WR-05 `format_reset`)
- [x] `tests/services/test_brew_improve.py` — BrewImproveSchema, prior-sessions loading (+ CR-02 HTML-render gap-closure)
- [x] `tests/services/test_preference_prose.py` — PreferenceProfileProseSchema
- [x] `tests/services/test_archived_retry.py` — `_verify_buy_url` 404/410 behavior + broader-search retry
- [x] `tests/routers/test_ai_research.py` — POST research endpoint, 429 quota, gate check
- [x] `tests/routers/test_ai_improve.py` — POST improve-brew, IDOR 404
- [x] `tests/routers/test_ai_charts.py` — GET chart JSON endpoints
- [x] Modify `tests/services/test_ai_service.py` — removed `no_match=True` usage; added `ratio`/`temp_c`/`grind_hint` assertions (`test_recipe_schema_*`, `test_suggest_recipe_no_catalog_match`)
- [x] `app/migrations/versions/p19_ai_research_predict.py` — two new tables + app_settings quota rows
- [x] `app/models/ai_coffee_research_cache.py` + `app/models/ai_rating_prediction.py` — new models
- [x] Framework install: added `sse-starlette>=3.4,<4` to `requirements.txt`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE streams incrementally end-to-end through NPM (not bursted at close) | AIX-07 | Requires the live NPM proxy host with `proxy_buffering off` applied; in-process TestClient cannot reproduce the proxy buffering layer | Apply `proxy_buffering off;` to the Snobbery NPM proxy host Advanced config; trigger a research call from a real browser; confirm prose appears token/sentence-incrementally, not all at once on completion |
| All new cards render without horizontal scroll at 375px | VIZ-01, AIX-01, AIX-05, AIX-12 | Visual; Trends card with two Chart.js canvases is the highest horizontal-scroll risk | Load `/ai` at 375px viewport; confirm Research card, quota counter, Coach-a-brew picker, and both charts fit card width (`maintainAspectRatio:false` + fixed pixel height) |
| Charts re-theme on dark-mode toggle | VIZ-01 | Alpine component watching `<html>.dark`; requires browser DOM | Toggle dark mode on `/ai`; confirm both charts switch palette (light: espresso lines on cream; dark: cream lines on espresso) without reload |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none MISSING at audit)
- [x] No watch-mode flags
- [x] Feedback latency < 120s (targeted Phase 19 set runs in ~20s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-29

---

## Validation Audit 2026-05-29

| Metric | Count |
|--------|-------|
| Gaps found (MISSING / PARTIAL) | 0 |
| Map-accuracy defects fixed | 1 (AIX-10 vacuous `-k` filter → correct test path) |
| Untracked coverage now recorded | 6 rows (CR-01, CR-02, WR-02, WR-03, WR-05 — plans 19-08/19-09) |
| Tests generated by auditor | 0 (no coverage gaps to fill) |
| Phase 19 test files run | 14 → **185 passed, 0 skipped, 0 failed** (`-rs`, baked image rebuilt) |

**Method:** Cross-referenced every requirement→test mapping against the
executed test tree by function name (not just `-k` filter) to catch vacuous
filters, then ran all 14 Phase 19 test files in a freshly rebuilt
`coffee-snobbery-test` image (the prior image predated the 19-08 regression-fix
commit `5a4b22e` by ~2 min). `-rs` confirmed zero skips masking green.

**Manual-only items unchanged:** SSE incremental streaming through NPM
(operator `proxy_buffering off` smoke still PENDING per 19-VERIFICATION.md),
375px no-horizontal-scroll, and dark-mode chart re-theme remain manual — the
first two pending, dark-mode positively spot-checked in 19-06 but not formally
DevTools-confirmed at 375px.
