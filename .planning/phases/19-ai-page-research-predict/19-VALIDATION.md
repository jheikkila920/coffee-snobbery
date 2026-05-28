---
phase: 19
slug: ai-page-research-predict
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
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

> Populated by the planner/executor once PLAN.md task IDs exist. The
> requirement → test mapping below is the authoritative source for which
> behaviors each task must satisfy (from `19-RESEARCH.md`).

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| AIX-01 | CoffeeResearchSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_ai_research.py::test_coffee_research_schema_validates -x` | ❌ W0 |
| AIX-01 | Cache miss triggers LLM call; cache hit skips LLM | unit (mock) | `pytest tests/services/test_ai_research.py -k "cache_miss or cache_hit" -x` | ❌ W0 |
| AIX-02 | RatingPredictionSchema renders range (never single point) | unit | `pytest tests/services/test_ai_research.py::test_rating_prediction_schema -x` | ❌ W0 |
| AIX-03 | Research endpoint blocks when gate_open=False | integration | `pytest tests/routers/test_ai_research.py::test_research_blocked_below_gate -x` | ❌ W0 |
| AIX-04 | Cache key normalizes case + whitespace; hits same row | unit | `pytest tests/services/test_ai_research.py::test_cache_key_normalization -x` | ❌ W0 |
| AIX-04 | Expired cache row evicted on read, triggers new LLM call | unit | `pytest tests/services/test_ai_research.py::test_expired_cache_eviction -x` | ❌ W0 |
| AIX-05 | Quota counter returns correct remaining count | unit | `pytest tests/services/test_ai_quota.py::test_quota_count -x` | ❌ W0 |
| AIX-05 | POST /ai/research returns 429 when quota exhausted | integration | `pytest tests/routers/test_ai_research.py::test_research_429_quota_exhausted -x` | ❌ W0 |
| AIX-05 | Reset time computed from oldest call in window | unit | `pytest tests/services/test_ai_quota.py::test_reset_time_computation -x` | ❌ W0 |
| AIX-06 | POST /ai/wishlist/add accepts research-sourced fields | integration (existing) | `pytest tests/routers/test_ai_router.py -k wishlist_add -x` | ✅ existing |
| AIX-07 | SSE generator yields `event: message` then `event: complete` in order | unit (mock) | `pytest tests/services/test_ai_research.py::test_sse_event_contract -x` | ❌ W0 |
| AIX-07 | Advisory lock blocks duplicate in-flight SSE request | unit | `pytest tests/services/test_ai_research.py::test_advisory_lock_blocks_duplicate -x` | ❌ W0 |
| AIX-09 | PreferenceProfileProseSchema: summary_prose + extra=forbid | unit | `pytest tests/services/test_preference_prose.py::test_preference_prose_schema -x` | ❌ W0 |
| AIX-10 | `.htmx-indicator` styles present in tailwind.src.css (CSP-clean) | behavioral | `pytest tests/test_pwa.py -k htmx_indicator -x` (add assertion) | ❌ W0 |
| AIX-11 | RecipeSuggestionSchema raises ValidationError on `no_match` field | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_no_match_rejected -x` | ❌ W0 (modify existing) |
| AIX-11 | RecipeSuggestionSchema requires ratio, temp_c, grind_hint | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_required_fields -x` | ❌ W0 (modify existing) |
| AIX-12 | BrewImproveSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_brew_improve.py::test_brew_improve_schema -x` | ❌ W0 |
| AIX-12 | POST /ai/improve-brew/{session_id} returns 404 on cross-user session | integration | `pytest tests/routers/test_ai_improve.py::test_improve_brew_cross_user_404 -x` | ❌ W0 |
| AIX-13 | duration_ms written for all new rec_types | unit (mock) | `pytest tests/services/test_ai_research.py::test_duration_ms_written -x` | ❌ W0 |
| AIX-13 | p50/p95 latency query executes against existing data | integration | `pytest tests/services/test_analytics_perf.py::test_latency_percentile_query -x` | ❌ W0 |
| VIZ-01 | GET /ai/charts/rating-over-time returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_rating_chart_json -x` | ❌ W0 |
| VIZ-01 | GET /ai/charts/flavor-distribution returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_flavor_chart_json -x` | ❌ W0 |
| D-06 | ai_coffee_research_cache table created by migration | migration | `pytest tests/test_migrations.py -x` | ❌ W0 |
| D-07 | ai_rating_predictions table + UNIQUE(user_id, research_cache_key) | migration | `pytest tests/test_migrations.py -x` | ❌ W0 |
| D-14 | _verify_buy_url returns False on 404/410 | unit | `pytest tests/services/test_archived_retry.py::test_verify_url_rejects_404 -x` | ❌ W0 |
| D-14 | Coffee rec flow retries with broader search on verify failure | unit (mock) | `pytest tests/services/test_archived_retry.py::test_archived_retry_logic -x` | ❌ W0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/services/test_ai_research.py` — schema validation, cache logic, SSE event contract, advisory lock
- [ ] `tests/services/test_ai_quota.py` — rolling-24h COUNT, reset-time computation, admin cap reader
- [ ] `tests/services/test_brew_improve.py` — BrewImproveSchema, prior-sessions loading
- [ ] `tests/services/test_preference_prose.py` — PreferenceProfileProseSchema
- [ ] `tests/services/test_archived_retry.py` — `_verify_buy_url` 404/410 behavior + broader-search retry
- [ ] `tests/routers/test_ai_research.py` — POST research endpoint, 429 quota, gate check
- [ ] `tests/routers/test_ai_improve.py` — POST improve-brew, IDOR 404
- [ ] `tests/routers/test_ai_charts.py` — GET chart JSON endpoints
- [ ] Modify `tests/services/test_ai_service.py` — remove `no_match=True` usage; add `ratio`/`temp_c`/`grind_hint` assertions (run `grep -rn "no_match" tests/` first)
- [ ] `app/migrations/versions/p19_ai_research_predict.py` — two new tables + app_settings quota rows
- [ ] `app/models/ai_coffee_research_cache.py` + `app/models/ai_rating_prediction.py` — new models
- [ ] Framework install: add `sse-starlette>=3.4,<4` to `requirements.txt`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE streams incrementally end-to-end through NPM (not bursted at close) | AIX-07 | Requires the live NPM proxy host with `proxy_buffering off` applied; in-process TestClient cannot reproduce the proxy buffering layer | Apply `proxy_buffering off;` to the Snobbery NPM proxy host Advanced config; trigger a research call from a real browser; confirm prose appears token/sentence-incrementally, not all at once on completion |
| All new cards render without horizontal scroll at 375px | VIZ-01, AIX-01, AIX-05, AIX-12 | Visual; Trends card with two Chart.js canvases is the highest horizontal-scroll risk | Load `/ai` at 375px viewport; confirm Research card, quota counter, Coach-a-brew picker, and both charts fit card width (`maintainAspectRatio:false` + fixed pixel height) |
| Charts re-theme on dark-mode toggle | VIZ-01 | Alpine component watching `<html>.dark`; requires browser DOM | Toggle dark mode on `/ai`; confirm both charts switch palette (light: espresso lines on cream; dark: cream lines on espresso) without reload |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
