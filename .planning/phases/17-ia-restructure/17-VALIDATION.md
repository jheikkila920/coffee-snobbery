---
phase: 17
slug: ia-restructure
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-27
updated: 2026-05-28
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + respx |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_nav.py tests/test_dist07_banner.py tests/routers/test_home.py tests/routers/test_ai_router.py tests/services/test_analytics.py -q -rs` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs --ignore=tests/e2e` |
| **Estimated runtime** | ~30 seconds quick / ~120 seconds full |

> Note: pytest is NOT in the production image. Wave 0 must `pip install --user pytest pytest-asyncio respx` into the running container (handled by plan 17-01 Task 5). Project memory `snobbery-test-gate-runtime` — full suite baseline ~939+ pass; Phase 17 adds ~24 new tests.

---

## Sampling Rate

- **After every task commit:** Run the quick run command above (~30s).
- **After every plan wave (and at every plan's final task):** Run the cumulative IA test sweep (plan-specific filters; see Per-Task Verification Map).
- **Before `/gsd-verify-work`:** Full suite command above must be green AND the IA-05 manual on-device PWA check must be recorded in 17-VERIFICATION.md (see Manual-Only Verifications).
- **Max feedback latency:** ~30 seconds for quick filter; ~120 seconds for full.

---

## Per-Task Verification Map

> Filters in the `Automated Command` column MUST collect ≥1 test (per project memory `validation-md-vacuous-k-filters`).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | IA-01, IA-02 | — | Wave 0 test scaffold for nav reshape (5 new tests in tests/test_nav.py) | unit | `pytest tests/test_nav.py -q -rs` | ❌ → ✅ after task | ⬜ pending |
| 17-01-02 | 01 | 1 | IA-02 / D-01 / D-02 / D-03 | T-17-01 (XSS via greeting) — mitigated by autoescape | base.html bottom nav renders AI tab, no Admin tab in bottom nav, top nav order mirrored | unit | `pytest tests/test_nav.py::test_home_has_ai_bottom_nav_tab tests/test_nav.py::test_admin_home_has_no_admin_bottom_nav_tab tests/test_nav.py::test_top_nav_still_has_admin_link_for_admin -x` | ✅ | ⬜ pending |
| 17-01-03 | 01 | 1 | D-05 | — | activeTab returns 'ai' for /ai*; /admin branch removed | unit | `pytest tests/test_nav.py -k "nav_bar_component or ai_bottom_nav_tab" -q -rs` (smoke: verify activeTab still wires) | ✅ | ⬜ pending |
| 17-01-04 | 01 | 1 | IA-01 / D-17 | T-17-02 (admin-only IA leakage to non-admin) — mitigated by `{% if request.state.user.is_admin %}` server-side gate | Config admin entry rendered for admins, hidden for non-admins | unit | `pytest tests/test_nav.py::test_admin_config_page_has_admin_entry tests/test_nav.py::test_non_admin_config_page_has_no_admin_entry -x` | ✅ | ⬜ pending |
| 17-01-05 | 01 | 1 | (all of 17-01) | — | Commit + ruff gates | ci | `docker compose exec coffee-snobbery python -m pytest tests/test_nav.py -q -rs && ruff check .` | ✅ | ⬜ pending |
| 17-02-01 | 02 | 1 | IA-03 / IA-04 / IA-06 + D-06..D-11 | — | Wave 0 test scaffold for home composition (10 new tests across two test modules) | unit | `pytest tests/services/test_analytics.py tests/routers/test_home.py -k "get_top_coffees_no_floor or derive_greeting or home_renders or home_does_not or home_action_row or home_has_see_ai or home_top_coffees_no_floor" -q -rs` | ❌ → ✅ after task | ⬜ pending |
| 17-02-02 | 02 | 1 | IA-06 / D-09 | — | get_top_coffees gains keyword-only min_sessions param; backward-compat default | unit | `pytest tests/services/test_analytics.py -k "get_top_coffees" -q -rs` | ✅ | ⬜ pending |
| 17-02-03 | 02 | 1 | D-10 | T-17-01 (greeting XSS) — mitigated by autoescape | derive_greeting returns morning/afternoon/evening per APP_TIMEZONE; fallback "Home" if username missing | unit | `pytest tests/routers/test_home.py -k "derive_greeting or personalized_greeting" -q -rs` | ✅ | ⬜ pending |
| 17-02-04 | 02 | 1 | IA-03 / IA-04 / D-06 / D-07 / D-08 / D-11 | — | home.html renders new composition; no AI surfaces, no cold-start meter, no Admin button in action row | unit | `pytest tests/routers/test_home.py -k "home_renders or home_does_not_mount_ai or home_action_row or home_has_see_ai or home_top_coffees" -q -rs` | ✅ | ⬜ pending |
| 17-02-05 | 02 | 1 | (all of 17-02) | — | Commit + ruff gates | ci | `docker compose exec coffee-snobbery python -m pytest tests/services/test_analytics.py tests/routers/test_home.py -q -rs && ruff check .` | ✅ | ⬜ pending |
| 17-03-01 | 03 | 2 | DIST-07 / D-19 | T-17-03 (banner shown to non-admin / shared device leak via sessionStorage) — non-admin path mitigated by server-side `{% if is_admin %}`; shared-device leak accepted v1 per Pitfall E | Wave 0 test scaffold for banner (5 new tests in tests/test_dist07_banner.py) | unit | `pytest tests/test_dist07_banner.py -q -rs` | ❌ → ✅ after task | ⬜ pending |
| 17-03-02 | 03 | 2 | D-19 | — | banner-dismiss.js registers Alpine.data inside alpine:init; sessionStorage key correct | unit (smoke via file content) | `pytest tests/test_dist07_banner.py::test_banner_dismiss_component_registered_in_base_html -x` | ✅ | ⬜ pending |
| 17-03-03 | 03 | 2 | DIST-07 / D-19 | T-17-02 | banner fragment self-gates on admin+no-key; admin link target /admin/credentials | unit | `pytest tests/test_dist07_banner.py::test_home_shows_dist07_banner_for_admin_with_no_key tests/test_dist07_banner.py::test_home_hides_dist07_banner_when_admin_has_key tests/test_dist07_banner.py::test_home_hides_dist07_banner_for_non_admin tests/test_dist07_banner.py::test_dist07_banner_uses_admin_credentials_route -x` | ✅ | ⬜ pending |
| 17-03-04 | 03 | 2 | D-19 / banner script registration | T-17-04 (CSP-nonce missing on script tag) — mitigated by Jinja template inheritance | base.html includes banner-dismiss.js script with nonce | unit | `pytest tests/test_dist07_banner.py::test_banner_dismiss_component_registered_in_base_html -x` | ✅ | ⬜ pending |
| 17-03-05 | 03 | 2 | DIST-07 home wiring | — | home_shell passes ai_key_present into context; home.html replaces placeholder with live include | integration | `pytest tests/routers/test_home.py tests/test_dist07_banner.py -q -rs` | ✅ | ⬜ pending |
| 17-03-06 | 03 | 2 | (all of 17-03) | — | Commit + ruff gates | ci | `docker compose exec coffee-snobbery python -m pytest tests/test_dist07_banner.py tests/test_nav.py tests/routers/test_home.py -q -rs && ruff check .` | ✅ | ⬜ pending |
| 17-04-01 | 04 | 3 | IA-02 / IA-03 / AIX-08 / D-13..D-16 / D-20 | — | Wave 0 test scaffold for /ai page (7 new tests in tests/routers/test_ai_router.py) | unit | `pytest tests/routers/test_ai_router.py -k "get_ai_page or ai_page_below_gate or ai_page_shows or ai_page_above_gate" -q -rs` | ❌ → ✅ after task | ⬜ pending |
| 17-04-02 | 04 | 3 | D-14 / Pitfall F | — | cold-start fragment moved to fragments/ai/; D-14 explainer copy; min-h-[14rem] for layout parity | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_below_gate_shows_cold_start_not_no_key -x` + grep min-h-[14rem] | ✅ | ⬜ pending |
| 17-04-03 | 04 | 3 | AIX-08 / D-15 | T-17-02 (non-admin sees admin callout) — mitigated by Jinja {% if is_admin %} branch | admin no-key callout: AI keys needed headline, key icon, Go to Admin button, amber palette | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_shows_admin_callout_above_gate_no_key -x` | ✅ | ⬜ pending |
| 17-04-04 | 04 | 3 | AIX-08 / D-16 | T-17-02 | non-admin no-key callout: AI is not set up, social action copy, no admin link, no notify button | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_shows_non_admin_callout_above_gate_no_key -x` | ✅ | ⬜ pending |
| 17-04-05 | 04 | 3 | D-13 / IA-03 | — | research-coming-soon stub renders disabled button + Phase 19 copy | unit | grep `Coming in Phase 19` + `disabled` in `app/templates/fragments/research_coming_soon.html`; integration test `pytest tests/routers/test_ai_router.py::test_ai_page_above_gate_with_key_shows_hero -x` | ✅ | ⬜ pending |
| 17-04-06 | 04 | 3 | IA-02 / IA-03 / D-13 / D-20 | T-17-04 | pages/ai.html composition: banner include at top; three-branch state machine; AI hero + Preference + Flavor + Sweet Spots mounts + AI tools + research stub on key-present branch | integration | `pytest tests/routers/test_ai_router.py::test_ai_page_above_gate_with_key_shows_hero tests/routers/test_ai_router.py::test_ai_page_shows_dist07_banner_for_admin_with_no_key -x` | ✅ | ⬜ pending |
| 17-04-07 | 04 | 3 | IA-02 | — | GET /ai handler 200 for authed; 401 for anonymous | unit | `pytest tests/routers/test_ai_router.py::test_get_ai_page_returns_200 tests/routers/test_ai_router.py::test_get_ai_page_returns_401_for_anonymous -x` | ✅ | ⬜ pending |
| 17-04-08 | 04 | 3 | (all of 17-04) | — | Commit + ruff gates | ci | `docker compose exec coffee-snobbery python -m pytest tests/routers/test_ai_router.py tests/test_nav.py tests/test_dist07_banner.py tests/routers/test_home.py tests/services/test_analytics.py -q -rs && ruff check .` | ✅ | ⬜ pending |
| 17-05-01 | 05 | 4 | (phase build prep) | — | Container rebuild + SW cache name bumped | manual + automated | `docker compose exec coffee-snobbery grep -o "snobbery-v[a-z0-9]*" /app/app/static/js/sw.js` | n/a (manual) | ⬜ pending |
| 17-05-02 | 05 | 4 | (cumulative phase gate) | — | Full non-e2e suite green | full-suite | `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs --ignore=tests/e2e` | ✅ | ⬜ pending |
| 17-05-03 | 05 | 4 | (style phase gate) | — | ruff format + check both pass | ci | `ruff format --check . && ruff check .` | ✅ | ⬜ pending |
| 17-05-04 | 05 | 4 | IA-05 | — | On-device PWA cache freshness verified by John (manual) | manual checkpoint | (manual on John's iPhone PWA — see Manual-Only Verifications below) | n/a (manual) | ⬜ pending |
| 17-05-05 | 05 | 4 | (phase close) | — | 17-VERIFICATION.md captures all evidence | docs | `test -f .planning/phases/17-ia-restructure/17-VERIFICATION.md && grep -q "IA-05" .planning/phases/17-ia-restructure/17-VERIFICATION.md` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] tests/test_nav.py extended with 5 new tests for IA-01 + IA-02 + D-18 (plan 17-01 Task 1).
- [ ] tests/services/test_analytics.py extended with 3 new tests for the no-floor min_sessions param (plan 17-02 Task 1).
- [ ] tests/routers/test_home.py extended with 7 home composition tests + derive_greeting unit tests (plan 17-02 Task 1).
- [ ] tests/test_dist07_banner.py NEW module with 5 banner tests (plan 17-03 Task 1).
- [ ] tests/routers/test_ai_router.py extended with 7 /ai page shell + AIX-08 callout tests (plan 17-04 Task 1).
- [ ] Container test deps: `pip install --user pytest pytest-asyncio respx` (handled in plan 17-01 Task 5; idempotent thereafter).
- [ ] No new conftest fixtures required — every test reuses `seeded_admin_user` / `seeded_regular_user` from tests/conftest.py and the analytics seed helpers from tests/services/test_analytics.py. Plan 17-03's "with key" / "no key" seed strategy is set by the executor at TDD-red time and reused by plan 17-04 for consistency.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Installed PWA cache freshness on John's iPhone | IA-05 | Service-worker cache invalidation can only be confirmed on a real installed PWA — automated tests do not exercise the iOS Safari SW lifecycle | 1. Pre-deploy, on John's iPhone, open the installed Snobbery PWA. Confirm the pre-Phase-17 bottom nav (Home / Log / Config / Admin) renders. Take a screenshot. 2. Deploy: `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery` (plan 17-05 Task 1 already did this for local; production VPS needs SSH). 3. Open the installed PWA WITHOUT "Clear site data" and WITHOUT re-installing. 4. Tap any nav tab. 5. Confirm bottom nav updates to Home / Log / AI / Config within 1-2 navigation cycles. 6. Take a post-deploy screenshot. 7. Record in 17-VERIFICATION.md: pre/post SW cache name (from `docker compose exec coffee-snobbery grep CACHE_NAME /app/app/static/js/sw.js`), iOS Safari version, both screenshots referenced, PASS/FAIL verdict. |
| 375px mobile layout sweep (bottom nav + home + DIST-07 banner + /ai page) | IA-01, IA-02, IA-03, IA-04, DIST-07, AIX-08, D-06, D-13..D-16, D-19 | Visual / layout assertions; pytest confirms presence but not visual fit, wrap, or touch-target ergonomics | Chrome DevTools (or Safari Web Inspector) at 375×667. (a) **Bottom nav**: four tabs (Home / Log / AI / Config), each `flex-1`, single row, no horizontal scroll, AI label + icon fit within the tab. Repeat at 390×844 and 414×896. (b) **Home (IA-04 / D-06)**: action row (Guided Brew / Log session / Quick rate) wraps cleanly with no horizontal scroll; greeting H1 readable; Top Coffees rows render eagerly. (c) **DIST-07 banner (D-19)**: as admin with no AI key, GET / — banner spans full container width, headline + "Go to Admin" + × button all reachable, no overflow. (d) **/ai page composition (IA-02 / IA-03 / AIX-08 / D-13..D-16)**: GET /ai in each state — below-gate cold-start card + meter + Log session CTA; above-gate-no-key admin (AI keys needed callout + Go to Admin); above-gate-no-key non-admin ("AI is not set up" copy, no admin link); above-gate-with-key (AI hero + Preference + Flavor + Sweet Spots + AI tools + research stub). Each state renders without horizontal scroll; min-h-[14rem] parity holds between cold-start and admin/non-admin callouts. Same browser session as the IA-05 PWA check is acceptable (plan 17-05 Task 4). |
| Personalized greeting reads naturally and falls back to "Home" | D-10 | Time-of-day branch coverage is in CI; the final wording is presentation | Hit GET / at 08:00 / 14:00 / 21:00 local; confirm `Good morning, john` / `Good afternoon, john` / `Good evening, john`. Default fallback rare in prod but verify via a one-off `request.state.user = None` scenario in a local debug session. |
| /admin/credentials link target opens the credentials page | DIST-07 / AIX-08 (A3 assumption) | The link target is verified via grep during planning, but a one-click confirmation prevents a 404 in prod | From the live app, click "Go to Admin" on either the DIST-07 banner OR the AIX-08 admin callout. Expect the credentials sub-page to load. |

---

## Threat Refs (referenced in Per-Task Verification Map)

- **T-17-01:** XSS via personalized greeting / banner — mitigated by Jinja autoescape globally (tests/templates/test_autoescape.py — pre-existing).
- **T-17-02:** Admin-only UI surface leaks to non-admin (banner, AIX-08 admin callout, Config admin entry) — mitigated by SERVER-SIDE `request.state.user.is_admin` template gates with defense-in-depth (page-level branch + fragment-level Jinja `{% if %}`).
- **T-17-03:** sessionStorage banner-dismiss state leaks across users on a shared device — accepted v1 per RESEARCH Pitfall E (household-scale; both users likely admin; dismiss is per-day-at-most-once).
- **T-17-04:** CSP-nonce missing on new script tag → CSP violation → script blocked → silent breakage — mitigated by reusing the established `{{ csp_nonce(request) }}` template macro in base.html.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a documented Manual-Only step
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (plan 17-05 Task 4 is the single manual checkpoint, bracketed by automated Tasks 1-3 and Task 5)
- [x] Wave 0 covers all MISSING test modules (test_dist07_banner.py NEW; test_nav.py / test_home.py / test_analytics.py / test_ai_router.py EXTENDED)
- [x] No watch-mode flags
- [x] Feedback latency < 30s for quick filter
- [x] Every `-k` filter in this table names specific test functions that the Wave-0 tasks will create (project memory `validation-md-vacuous-k-filters` — verify each filter collects ≥1 test post-execution)
- [x] IA-05 manual steps recorded in 17-VERIFICATION.md (plan 17-05 Task 5)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (Wave 0 tasks scheduled in plans 17-01..17-04 first tasks; 17-05 closes the phase)
