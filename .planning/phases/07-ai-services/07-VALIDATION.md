---
phase: 7
slug: ai-services
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-20
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + respx (HTTP mock for AI SDK + URL-verify) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/ -q -x` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Estimated runtime** | ~30 seconds |

Note: pytest + respx are not baked into the production image (CLAUDE.md). Install once into the
running container before the first test run:
`docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx`.
Code has no bind-mount: copy changed files in (`docker compose cp tests/ coffee-snobbery:/app/tests/`,
`docker compose cp app/ coffee-snobbery:/app/app/`) or rebuild before exercising in-container.

---

## Sampling Rate

- **After every task commit:** `docker compose exec coffee-snobbery python -m pytest tests/services/test_ai_service.py tests/services/test_wishlist.py tests/routers/test_ai_router.py -q -x`
- **After every plan wave:** `docker compose exec coffee-snobbery python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01 T1 | 07-01 | 1 | AI-18 | — | Every response schema exposes summary_prose + extra="forbid" | unit | `pytest tests/services/test_ai_service.py -k schema` | ❌ Wave 0 | ⬜ pending |
| 07-01 T2 | 07-01 | 1 | AI-04 | T-07-02 | Projector keeps only named tool_use block | unit | `pytest tests/services/test_ai_service.py::test_citation_projector` | ❌ Wave 0 | ⬜ pending |
| 07-01 T2 | 07-01 | 1 | AI-05 | T-07-01 | URL verifier blocks cross-host redirect | unit (respx) | `pytest tests/services/test_ai_service.py::test_url_verify_ssrf_redirect` | ❌ Wave 0 | ⬜ pending |
| 07-01 T2 | 07-01 | 1 | AI-05 | T-07-01 | URL verifier rejects non-https scheme | unit | `pytest tests/services/test_ai_service.py::test_url_verify_scheme_rejected` | ❌ Wave 0 | ⬜ pending |
| 07-01 T2 | 07-01 | 1 | AI-13 | T-07-07 | Advisory key stable signed int64 | unit | `pytest tests/services/test_ai_service.py -k advisory_key` | ❌ Wave 0 | ⬜ pending |
| 07-01 T3 | 07-01 | 1 | AI-01 | T-07-03 | Fallback predicate: non-retryable + 529/overloaded string only | unit | `pytest tests/services/test_ai_service.py -k fallback_predicate` | ❌ Wave 0 | ⬜ pending |
| 07-01 T3 | 07-01 | 1 | AI-17 | — | max_uses read from app_settings (5/3) | unit | `pytest tests/services/test_ai_service.py::test_max_uses_from_settings` | ❌ Wave 0 | ⬜ pending |
| 07-01 T3 | 07-01 | 1 | AI-14 | T-07-04 | Throttle dict eviction bounded | unit | `pytest tests/services/test_ai_service.py::test_throttle_eviction` | ❌ Wave 0 | ⬜ pending |
| 07-02 T1/T2 | 07-02 | 1 | AI-13 | T-07-05 | Wishlist cross-user get/remove → None/False | unit (DB) | `pytest tests/services/test_wishlist.py -k cross_user` | ❌ Wave 0 | ⬜ pending |
| 07-03 T1 | 07-03 | 2 | AI-06 | — | Recipe suggestion picks existing recipe only | unit (DB) | `pytest tests/services/test_ai_service.py -k suggest_recipe` | ❌ Wave 0 | ⬜ pending |
| 07-03 T1 | 07-03 | 2 | AI-07 | — | Alt-brewer fires only at >=0.5 delta | unit (DB) | `pytest tests/services/test_ai_service.py -k alt_brewer` | ❌ Wave 0 | ⬜ pending |
| 07-03 T2 | 07-03 | 2 | AI-03 | T-07-02 | Three-tier search fallback + tier reported | unit (mock SDK) | `pytest tests/services/test_ai_service.py::test_three_tier_fallback` | ❌ Wave 0 | ⬜ pending |
| 07-03 T2 | 07-03 | 2 | AI-01 | T-07-03 | Anthropic non-retryable → OpenAI caller | unit (mock SDK) | `pytest tests/services/test_ai_service.py::test_provider_fallback_anthropic_to_openai` | ❌ Wave 0 | ⬜ pending |
| 07-03 T2 | 07-03 | 2 | AI-04 | T-07-02 | ValidationError at all tiers → try_again | unit (mock SDK) | `pytest tests/services/test_ai_service.py::test_pydantic_validation_error_try_again` | ❌ Wave 0 | ⬜ pending |
| 07-03 T2 | 07-03 | 2 | AI-10/HOME-06 | — | Sweet-spots prose row written with coffee bundle | unit (mock SDK) | `pytest tests/services/test_ai_service.py -k sweet_spots_prose` | ❌ Wave 0 | ⬜ pending |
| 07-03 T3 | 07-03 | 2 | AI-12 | T-07-08 | Unchanged signature → "skipped" (force bypasses) | unit | `pytest tests/services/test_ai_service.py -k "sig_skip or force_regenerates"` | ❌ Wave 0 | ⬜ pending |
| 07-03 T3 | 07-03 | 2 | AI-13 | T-07-07 | Advisory lock unavailable → "locked" | unit (DB) | `pytest tests/services/test_ai_service.py::test_advisory_lock_concurrent` | ❌ Wave 0 | ⬜ pending |
| 07-03 T3 | 07-03 | 2 | AI-16 | — | No provider → "not_configured" | unit | `pytest tests/services/test_ai_service.py::test_not_configured` | ❌ Wave 0 | ⬜ pending |
| 07-03 T3 | 07-03 | 2 | AI-11 | — | Cold-start gate closed → "skipped" | unit (DB) | `pytest tests/services/test_ai_service.py::test_cold_start_skips` | ❌ Wave 0 | ⬜ pending |
| 07-03 T3 | 07-03 | 2 | AI-15 | — | is_stale True when signature changed | unit (DB) | `pytest tests/services/test_ai_service.py::test_is_stale_true_when_sig_changed` | ❌ Wave 0 | ⬜ pending |
| 07-04 T1 | 07-04 | 3 | AI-08 | — | Equipment rec uses NO web_search tool; "no changes" valid | unit (mock SDK) | `pytest tests/services/test_ai_service.py -k equipment_rec` | ❌ Wave 0 | ⬜ pending |
| 07-04 T2 | 07-04 | 3 | AI-09 | T-07-09 | Paste-rank URL fetch: https-only + no cross-host redirect | unit (respx) | `pytest tests/services/test_ai_service.py -k "paste_rank_fetch"` | ❌ Wave 0 | ⬜ pending |
| 07-04 T2 | 07-04 | 3 | AI-09 | — | Paste-rank top-3 cap; never cached | unit (mock SDK) | `pytest tests/services/test_ai_service.py -k "paste_rank_top3 or paste_rank_never_cached"` | ❌ Wave 0 | ⬜ pending |
| 07-05 T1 | 07-05 | 4 | AI-14 | T-07-07 | Second refresh in 5 min → 429 + HX-Retarget | unit (router) | `pytest tests/routers/test_ai_router.py::test_throttle_429` | ❌ Wave 0 | ⬜ pending |
| 07-05 T1 | 07-05 | 4 | AI-13 | T-07-07 | Refresh while in-flight → 429 | unit (router) | `pytest tests/routers/test_ai_router.py::test_in_flight_429` | ❌ Wave 0 | ⬜ pending |
| 07-05 T1 | 07-05 | 4 | AI-05 | T-07-01 | Background task verifies buy_url, updates url_verified | unit (router) | `pytest tests/routers/test_ai_router.py -k refresh` | ❌ Wave 0 | ⬜ pending |
| 07-05 T2 | 07-05 | 4 | AI-13 | T-07-05 | Wishlist purchase/remove cross-user → 404 | unit (router) | `pytest tests/routers/test_ai_router.py -k "wishlist.*cross_user"` | ❌ Wave 0 | ⬜ pending |
| 07-05 T2 | 07-05 | 4 | AI-09/AI-08 | T-07-11 | Paste-rank + equipment + wishlist POST CSRF-enforced | unit (router) | `pytest tests/routers/test_ai_router.py -k "csrf or paste_rank_route or equipment_route"` | ❌ Wave 0 | ⬜ pending |
| 07-05 T3 | 07-05 | 4 | AI-16 | T-07-12 | ai_router registered; /ai/* resolve | smoke | `pytest tests/routers/test_ai_router.py -k registered` | ❌ Wave 0 | ⬜ pending |
| 07-06 T1 | 07-06 | 5 | AI-04/AI-05/HOME-06 | T-07-13 | Fragments CSP-clean (no \|safe); buy-link tri-state; HOME-06 prose | unit (CI grep) | `pytest tests/ci -k "safe or jinja"` | partial | ⬜ pending |
| 07-06 T2 | 07-06 | 5 | AI-11/AI-15/AI-16/HOME-06 | T-07-12 | Hero-card endpoint state branches; sweet-spots prose context | unit (router) | `pytest tests/routers/test_home.py -k "ai_card or sweet_spots_prose"` | partial | ⬜ pending |
| 07-07 T1 | 07-07 | 6 | AI-09/AI-08 | T-07-13 | Paste-rank page + results; equipment fragment | unit (router) | `pytest tests/routers/test_ai_router.py -k "paste_rank_page or paste_rank_submit or equipment_button"` | ❌ Wave 0 | ⬜ pending |
| 07-07 T2 | 07-07 | 6 | HOME-06 | T-07-05 | Wishlist page user-scoped; home links + equipment button | unit (router) | `pytest tests/routers/test_ai_router.py tests/routers/test_home.py -k "wishlist_page or home_links or equipment"` | partial | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 test scaffolds (created by the FIRST task that needs them, before implementation):

- [ ] **`tests/services/test_ai_service.py`** (created in 07-01 T2) — covers AI-04 (projector), AI-05 (URL verify SSRF),
      AI-01 (fallback predicate), AI-17 (max_uses), AI-13 (advisory key/lock), AI-18 (schemas), AI-03 (tiers),
      AI-06/AI-07 (recipe/alt-brewer), AI-12 (sig skip), AI-16 (not_configured), AI-11 (cold-start), AI-15 (stale),
      AI-08 (equipment), AI-09 (paste-rank). This file is the import surface 07-03 and 07-04 extend.
- [ ] **`tests/services/test_wishlist.py`** (created in 07-02 T2) — covers wishlist CRUD + cross-user IDOR (AI-13 lock-adjacent scoping).
- [ ] **`tests/routers/test_ai_router.py`** (created in 07-05 T1) — covers AI-14 (throttle 429), AI-13 (in-flight 429),
      AI-05 (background verify), AI-09/AI-08 (route CSRF + IDOR), AI-16 (registration).
- [ ] **`tests/routers/test_home.py`** (extended in 07-06 T2) — covers AI-11/AI-15/AI-16/HOME-06 home-card state branches.

**Required for Wave 0:** `respx` mock library for httpx outbound calls (AI SDK + URL verify). Install into the
running container: `pip install --user respx` (formal `respx` AI suite is Phase 12 / TEST-02; Wave-0 stubs accrue here).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live coffee-rec end-to-end with a real provider key | AI-01, AI-03 | Real API call costs tokens; not run in CI | Enable a provider in admin, click Refresh, confirm card + verified URL within ~30s |
| 375px home hero card layout + 5 states | HOME-06, AI-11/16 | Visual | 07-06 Task 3 checkpoint: cold-start / not-configured / in-flight / try-again / hero card; no horizontal scroll |
| Paste-rank, wishlist, equipment button at 375px | AI-08, AI-09 | Visual | 07-07 Task 3 checkpoint: top-3 results, wishlist purchase/remove, on-click equipment rec |

*Load-bearing behaviors with automated coverage (RESEARCH §Validation Architecture): provider fallback predicate
(non-retryable only, 529 string-match), citation projection (keep tool_use only), three-tier search fallback + tier
reporting, URL verification (verified / unverified / SSRF cross-host + scheme reject), advisory-lock + in-memory-lock
concurrency, 5-min manual-refresh throttle (429 + HX-Retarget), cold-start gate, signature-based regen skip, graceful
"AI not configured" / "Try again" states. All mapped above.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (checkpoints excepted, by design)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_ai_service.py / test_wishlist.py / test_ai_router.py created before implementation)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner)
