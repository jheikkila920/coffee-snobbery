# Phase 17 Verification

**Phase:** 17 — IA Restructure
**Status:** PASS
**Date recorded:** 2026-05-28
**Author:** John (human-authored ledger; verifier agent must write any auto verification to `17-VERIFICATION-AUTO.md` per project memory `verifier-overwrites-human-verification-ledger`)

## IA-05 — PWA picks up nav changes without manual cache clear

**Test environment:** John's installed iPhone PWA (Add to Home Screen)
**Verdict:** **PASS**
**Date:** 2026-05-28

**Build-hash transition (proves the SW cache-bust mechanism fired):**

| Stage | SW cache name (served at `/sw.js`) | Tailwind CSS hash |
|-------|------------------------------------|-------------------|
| Pre-rebuild  | `snobbery-v20260527203723` | `tailwind.885f0251.css` |
| Post-rebuild | `snobbery-v20260528131840` | `tailwind.885f0251.css` |

Build hash is content-deterministic per project memory `c9-sw-cache-content-deterministic`; the Tailwind CSS hash did not bump because the Phase 17 changes added no new utility classes (the `amber-50/300/700/900` palette used by the DIST-07 banner and AIX-08 admin callout was already in the Tailwind v3 default palette). The SW cache name bumped via the timestamp portion of `__BUILD_HASH__` so the activate-on-fetch lifecycle still fires for installed PWAs.

**Confirmation:** John confirmed on-device the installed iPhone PWA picked up the new Home / Log / AI / Config bottom nav (Admin tab removed) without "Clear site data" and without re-install.

## 375px mobile layout sweep

**Verdict:** **PASS** (collective — verified alongside the on-device IA-05 check)

| Sub-step | Requirement | Verdict |
|----------|-------------|---------|
| (a) Bottom nav | IA-01 / IA-02 / D-01 / D-02 — four tabs Home / Log / AI / Config, single row, no Admin | PASS |
| (b) Home composition | IA-04 / D-06 / D-10 — greeting H1, three-button action row, Top Coffees eager, no horizontal scroll | PASS |
| (c) DIST-07 banner | D-19 — admin + no key sees banner at top, headline + Go to Admin + ×, container-width | PASS |
| (d) `/ai` page | IA-02 / IA-03 / AIX-08 / D-13..D-16 / D-20 — three-branch composition, layout parity holds | PASS |

## Cumulative test suite

**Command:** `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs --ignore=tests/e2e`
**Result:** **1216 passed, 3 skipped, 10 xfailed, 0 failed** in 156.43s

Phase 17 added 29 new tests (5 from plan 17-01 nav + 7 from plan 17-02 home rewrite + 5 from plan 17-03 DIST-07 banner + 7 from plan 17-04 `/ai` page shell + 5 parametrize variants). All three skips are pre-existing infrastructure gates (`db_session` async fixture, Playwright not installed for one viewport assertion, FK CASCADE invariant note); none are new from this phase. The 10 xfails are pre-existing project-memory-documented flakes.

## Style gates

| Gate | Result |
|------|--------|
| `ruff format --check .` | PASS (224 files already formatted) |
| `ruff check .` | PASS (All checks passed) |

## Phase 17 close

All four prior plans (17-01, 17-02, 17-03, 17-04) merged. Requirements coverage:

| Requirement | Plan(s) | Verification |
|-------------|---------|--------------|
| IA-01 (Admin off bottom nav, on Config card) | 17-01 | `test_nav.py` admin-card + bottom-nav assertions |
| IA-02 (AI tab + wired `/ai` shell) | 17-01 + 17-04 | nav + `test_ai_router::test_get_ai_page_returns_*` |
| IA-03 (AI surfaces consolidated on `/ai`) | 17-02 + 17-04 | home rewrite tests + `/ai` mount tests |
| IA-04 (Home simplified) | 17-02 | `test_home` composition tests + 375px sweep |
| IA-05 (PWA picks up changes without manual cache clear) | 17-05 | THIS DOC, on-device PASS above |
| IA-06 (Top Coffees no floor) | 17-02 | `test_analytics::test_get_top_coffees_no_floor_*` |
| DIST-07 (Post-setup AI-key nudge banner) | 17-03 | `test_dist07_banner.py` (5 assertions) |
| AIX-08 (Distinct no-key state on `/ai`) | 17-04 | `test_ai_router::test_ai_page_shows_*_callout_*` |

Phase 17 is **closed-ready**. Hand off to `/gsd-verify-work` for the verifier agent to confirm via goal-backward analysis. The verifier MUST write its output to `17-VERIFICATION-AUTO.md` (not this file).
