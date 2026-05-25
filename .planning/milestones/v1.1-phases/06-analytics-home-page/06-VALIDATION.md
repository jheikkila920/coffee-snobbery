---
phase: 6
slug: analytics-home-page
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-20
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (+ pytest-asyncio, respx) — NOT baked into prod image; install per CLAUDE.md |
| **Config file** | tests/conftest.py (forces `<db>_test`, transactional rollback) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest -q tests/services/test_analytics.py` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q tests/services/test_analytics.py tests/services/test_analytics_perf.py tests/routers/test_home.py` |
| **Estimated runtime** | ~30s quick (service unit tests) · ~90s full (adds the 1000-session perf seed + router smoke tests) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (`tests/services/test_analytics.py`)
- **After every plan wave:** Run full suite command (service + perf + router)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds (quick command); ~90 seconds (full suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|
| 06-01-01 | 01 | 1 | HOME-01..05, HOME-07, HOME-08 | T-6-01 | per-user `analyticstest-` seed isolation; archived coffee seeded for HOME-08 branch | unit (scaffold) | `docker compose exec coffee-snobbery python -m pytest tests/services/test_analytics.py --collect-only -q` | ❌ W0 |
| 06-01-02 | 01 | 1 | HOME-01..05, HOME-07, HOME-08 | T-6-01 / T-6-02 / T-6-03 | first WHERE = `BrewSession.user_id == user_id`; `Coffee.archived == False` in HOME-08; signature over own rated sessions only (COST-4); SQLAlchemy Core (no `text()` interpolation) | unit | `docker compose exec coffee-snobbery python -c "from app.services import analytics; assert all(hasattr(analytics,f) for f in ['get_top_coffees','get_preference_profile','get_flavor_descriptors','get_roast_freshness_buckets','get_sweet_spots','get_recent_brews','get_unrated_coffees','get_cold_start_counts','compute_input_signature']); print('ok')" && docker compose exec coffee-snobbery ruff check app/services/analytics.py` | ❌ W0 |
| 06-01-03 | 01 | 1 | HOME-01..05, HOME-07, HOME-08 | T-6-01 / T-6-02 | per-user scoping proven by seeded asserts; archived coffee excluded; signature deterministic + free-text-excluded | unit | `docker compose exec coffee-snobbery python -m pytest tests/services/test_analytics.py -q` | ❌ W0 |
| 06-01-04 | 01 | 1 | HOME-01..05, HOME-07, HOME-08 (perf) | T-6-03 | parameterized EXPLAIN / direct service calls — no user input interpolated; 1000-session single-user seed, <50ms per derivation | integration (perf) | `docker compose exec coffee-snobbery python -m pytest tests/services/test_analytics_perf.py -q` | ❌ W0 |
| 06-02-01 | 02 | 2 | HOME-07, HOME-08, HOME-09 | T-6-04 / T-6-05 | every handler `Depends(require_user)` → 401; `user.id` from `request.state.user`, never query param | integration (route probe) | `docker compose exec coffee-snobbery python -c "from app.main import create_app; app=create_app(); p={r.path for r in app.routes}; assert '/' in p and '/home/cards/recent-brews' in p and '/home/cards/unrated-coffees' in p; print('routes ok')" && docker compose exec coffee-snobbery ruff check app/routers/home.py` | ❌ W0 |
| 06-02-02 | 02 | 2 | HOME-07, HOME-08, HOME-09 | T-6-06 / T-6-12 | no `\|safe`/`hx-on:`/`hx-vals='js:'` (autoescape, CSP-clean); Phase 7 AI slot is a Jinja comment, not a live `hx-trigger="revealed"` (no 404-on-reveal) | integration (template probe) | `docker compose exec coffee-snobbery python -c "import re,glob; files=glob.glob('app/templates/pages/home.html')+glob.glob('app/templates/fragments/home/*.html'); bad=[f for f in files if re.search(r'\|\s*safe|hx-on:|hx-vals=.js:', open(f,encoding='utf-8').read())]; assert not bad,bad; h=open('app/templates/pages/home.html',encoding='utf-8').read(); assert h.count('hx-trigger=\"load delay:')>=5; assert 'Phase 7: AI recommendation card slot' in h; print('templates ok')"` | ❌ W0 |
| 06-02-03 | 02 | 2 | HOME-07, HOME-08, HOME-09 | T-6-04 / T-6-12 | shell + fragments 401 unauthenticated; fragment cache headers (`no-store` + `Vary: HX-Request`); AI slot placeholder present, no live trigger | integration (router smoke) | `docker compose exec coffee-snobbery python -m pytest tests/routers/test_home.py -q` | ❌ W0 |
| 06-03-01 | 03 | 3 | HOME-01..05, HOME-09 | T-6-08 / T-6-09 | five aggregate endpoints `Depends(require_user)` → 401; `user.id`-scoped; all-unrated detection passed to rating-dependent templates | integration (route probe) | `docker compose exec coffee-snobbery python -c "from app.main import create_app; app=create_app(); p={r.path for r in app.routes}; need={'/home/cards/top-coffees','/home/cards/preference-profile','/home/cards/flavor-descriptors','/home/cards/roast-freshness','/home/cards/sweet-spots'}; assert need<=p, need-p; print('endpoints ok')" && docker compose exec coffee-snobbery ruff check app/routers/home.py` | ❌ W0 |
| 06-03-02 | 03 | 3 | HOME-01..05, HOME-09 | T-6-10 / T-6-11 | card templates CSP-clean (no `\|safe`/`hx-on:`/`hx-vals='js:'`, autoescape); no AI "coming soon" placeholder in sweet-spots (HOME-06 scope guard) | integration (template probe) | `docker compose exec coffee-snobbery python -c "import re,glob; files=glob.glob('app/templates/fragments/home/*.html'); bad=[f for f in files if re.search(r'\|\s*safe|hx-on:|hx-vals=.js:', open(f,encoding='utf-8').read())]; assert not bad,bad; import os; need={'top_coffees.html','preference_profile.html','flavor_descriptors.html','roast_freshness.html','sweet_spots.html','_card_sparse.html'}; have={os.path.basename(f) for f in files}; assert need<=have, need-have; print('cards ok')"` | ❌ W0 |
| 06-03-03 | 03 | 3 | HOME-01..05, HOME-09 | T-6-08 / T-6-10 / T-6-11 | aggregate fragments 401 unauthenticated; cache headers; D-05 all-unrated nudge; no-AI-placeholder scope guard | integration (fragment smoke) | `docker compose exec coffee-snobbery python -m pytest tests/routers/test_home.py -q` | ❌ W0 |

*File Exists: ✅ exists · ❌ W0 (created in Wave 0 / during the plan's first task)*

---

## Wave 0 Requirements

- [ ] `tests/services/test_analytics.py` — stubs + seed helpers (incl. an archived unbrewed coffee) for HOME-01..05, HOME-07/08 + signature determinism (Plan 06-01 Task 1)
- [ ] `tests/services/test_analytics_perf.py` — 1000-session seed + per-query <50ms latency check (Plan 06-01 Task 4)
- [ ] `tests/routers/test_home.py` — router/fragment smoke tests incl. auth-gate 401, cache headers, cold-start branch, Phase 7 AI-slot placeholder (Plans 06-02 / 06-03)
- [ ] `tests/conftest.py` — seeded-session fixtures + `_postgres_reachable` probe (existing infra, reused)
- [ ] pytest install into running container — prod image excludes it (per CLAUDE.md)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Home TTI < 2s at 375px on throttled 3G | HOME-09 | Browser perf profile; formal Playwright/TTI suite is Phase 12 | Throttle to 3G in DevTools, load `/`, measure TTI. (Note: the per-query <50ms budget — ROADMAP criterion 2 — IS automated in `test_analytics_perf.py::test_analytics_query_latency`; only the browser-side TTI remains manual until Phase 12.) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < ~90s (full suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved

---

## Validation Audit 2026-05-20

State-A audit of committed test coverage against the HOME requirements. Coverage was already strong; two gaps were found and filled.

| Metric | Count |
|--------|-------|
| Requirements/properties audited | 9 (HOME-01..05, 07, 08, 09 + signature) |
| Gaps found | 2 |
| Resolved (tests added/repaired) | 2 |
| Escalated | 0 |

**Gaps filled:**
- **HOME-09 (staggered lazy-load)** — was MISSING a committed regression test. Added `tests/routers/test_home.py::test_home_shell_staggered_lazy_load`: seeds a gate-open user, GETs `/`, asserts ≥5 `hx-trigger="load delay:Nms"` slots with the staggered set {100,200,300,400,500} present and ascending. Catches any future collapse/drop/reorder of the slots.
- **Signature D-09 (rated-only)** — replaced the weak/misleading `test_signature_order_independent` (it overclaimed order-independence but only asserted within-user determinism, already covered by `test_signature_determinism`) with `tests/services/test_analytics.py::test_signature_excludes_unrated_sessions`: proves an unrated session leaves the signature unchanged and rating it changes the signature (D-09). Note: signature "order-independence" is intentional `ORDER BY id` within-user determinism, covered by `test_signature_determinism` — not a separately-testable cross-user property.

Full suite after fixes: **455 passed, 2 skipped, 10 xfailed** (in-container). Phase remains `nyquist_compliant: true`.
