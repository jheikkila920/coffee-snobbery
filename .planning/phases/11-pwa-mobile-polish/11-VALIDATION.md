---
phase: 11
slug: pwa-mobile-polish
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-23
validated: 2026-05-23
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (+ pytest-asyncio, respx) |
| **Config file** | `pyproject.toml` / `conftest.py` (pytest NOT baked into prod image — `pip install --user pytest pytest-asyncio respx` into the running container per CLAUDE.md) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_pwa.py tests/test_migrations.py tests/test_nav.py tests/routers/test_gbm.py -q -rs` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Estimated runtime** | ~8 seconds (Phase 11 subset: 34 tests) |

> No source bind-mount; Jinja caches templates in-process. To exercise a changed test, copy it in **file by file** (`docker compose cp tests/test_pwa.py coffee-snobbery:/app/tests/test_pwa.py`) — copying the directory nests (`tests/tests`). HTML/template changes require a rebuild; test-only changes need only the cp.

---

## Sampling Rate

- **After every task commit:** Run the quick run command for the touched file
- **After every plan wave:** Run the quick run command (all four Phase 11 files)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~8 seconds (phase subset)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-T1/2 | 01 | 1 | MOB-09 | T-11-01 | Public route serves only locked non-PII strings | unit (HTTP) | `pytest tests/test_pwa.py::test_manifest_200` | ✅ | ✅ green |
| 11-01-T2/3 | 01 | 1 | MOB-10 | T-11-02 | SW headers correct; non-GET bypass keeps CSRF intact | unit (HTTP) | `pytest tests/test_pwa.py::test_sw_headers` | ✅ | ✅ green |
| 11-01-T1 | 01 | 1 | MOB-09 | T-11-05 | start_url passes through, no query-param sink | unit (HTTP) | `pytest tests/test_pwa.py::test_start_url_returns_200` | ✅ | ✅ green |
| 11-01 | 01 | 1 | UX-02 | T-11-01 | Locked branding strings asserted exactly | unit (HTTP) | `pytest tests/test_pwa.py::test_manifest_200` | ✅ | ✅ green |
| 11-01/03 | 01,03 | 1,2 | MOB-12 | — | `<link rel="manifest">` discoverable in served HTML (regression of the verifier-found blocker) | unit (HTTP) | `pytest tests/test_pwa.py::test_manifest_link_in_head` | ✅ | ✅ green |
| 11-03 | 03 | 2 | MOB-11 | — | apple-touch-icon + iOS web-app meta tags discoverable in served HTML | unit (HTTP) | `pytest tests/test_pwa.py::test_apple_touch_icon_and_web_app_meta_in_head` | ✅ | ✅ green |
| 11-02-T1/2 | 02 | 1 | BREW-12 (D-10) | T-11-06 | `brew_time_seconds` nullable col; Field ge=0/le=86400 rejects negative/>24h | migration + schema | `pytest tests/test_migrations.py` | ✅ | ✅ green |
| 11-03-T3 | 03 | 2 | MOB-01 | — | Persistent nav (`navBar`) present on authenticated pages | router (HTML) | `pytest tests/test_nav.py::test_authenticated_home_has_nav_bar_component` | ✅ | ✅ green |
| 11-03-T3 | 03 | 2 | MOB-02 | T-11-09 | Admin nav link absent for non-admin, present for admin | router (HTML) | `pytest tests/test_nav.py::test_non_admin_home_has_no_admin_link`, `::test_admin_home_has_admin_link` | ✅ | ✅ green |
| 11-03-T3 | 03 | 2 | UX-04 / D-03 | T-11-08 | `/config` 200/401; mobile sign-out CSRF POST to /logout | router (HTML) | `pytest tests/test_nav.py::test_config_hub_returns_200_for_authenticated_user`, `::test_config_hub_returns_401_for_anonymous`, `::test_config_hub_has_mobile_signout_form` | ✅ | ✅ green |
| 11-04-T2/4 | 04 | 3 | BREW-12 | T-11-12 | `/brew/guided` require_user (401 anon), 404 missing recipe, no-steps state | router (HTML) | `pytest tests/routers/test_gbm.py` | ✅ | ✅ green |
| 11-04-T3/4 | 04 | 3 | BREW-12 | T-11-13 | `brew_time_seconds` round-trips on create; 86401 rejected | router | `pytest tests/routers/test_gbm.py` | ✅ | ✅ green |
| 11-04-T5 | 04 | 3 | BREW-13 | T-11-14 | Wake lock native→NoSleep fallback→re-acquire; chime; haptics | manual (real device) | — | N/A | 🔒 manual |
| 11-05-T1/3 | 05 | 4 | MOB-03 | — | Tables collapse to cards, no horizontal scroll at 375px | manual + Phase 12 | — | N/A | 🔒 manual |
| 11-05-T1 | 05 | 4 | MOB-04 | — | All card-mode controls ≥44×44px | manual + Phase 12 | — | N/A | 🔒 manual |
| 11-05-T2 | 05 | 4 | MOB-07 | — | Native select short lists; searchable dropdown for coffees | manual | — | N/A | 🔒 manual |
| 11-05-T2 | 05 | 4 | MOB-08 | — | Mini-modal full-screen sheet <768px / dialog ≥768px | manual + Phase 12 | — | N/A | 🔒 manual |
| 11-05-T3 | 05 | 4 | MOB-13 | — | Responsive at 375×667 + 390×844 (human checkpoint approved) | manual + Phase 12 | — | N/A | 🔒 manual |
| 11-03 | 03 | 2 | UX-01 | — | Warm palette + system-preference dark mode | manual (visual) | — | N/A | 🔒 manual |
| 11-01/03 | 01,03 | 1,2 | MOB-12 | — | On-device installability (iOS A2HS / Android Lighthouse PWA) | manual (real device) | — | N/A | 🔒 manual |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · 🔒 manual-only*

---

## Wave 0 Requirements

- [x] `tests/test_pwa.py` — MOB-09 / MOB-10 / start_url Wave 0 scaffold (landed RED before routes, now green)
- [x] `{% block head_extra %}` empty block added to `base.html` (GBM NoSleep.js mount point)
- [x] pytest installed into running container (not baked into prod image)

*Existing `conftest.py` fixtures (`client`, `seeded_regular_user`, `seeded_admin_user`) covered all new tests — no new fixtures required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| iOS Wake Lock + silent-audio/NoSleep.js fallback holds screen on | BREW-13 | Wake Lock + AudioContext cannot be verified in headless browser; iOS-specific | Install PWA on a real iPhone (iOS 16.4–18.3 for fallback, 18.4+ for native), start Guided Brew, confirm screen stays on and the indicator reflects actual lock state (green native / yellow fallback) |
| Haptic step-transition cues vibrate on Android; silently skip on iOS | BREW-12 / BREW-13 | Vibration API unsupported on iOS Safari; no headless verification | On Android Chrome confirm vibration at each step; on iOS confirm no error and no indicator |
| Audio chime fires at step transitions after user-gesture unlock | BREW-12 / BREW-13 | AudioContext autoplay gate; iOS re-suspension | On real device confirm chime at each transition; backgrounding/foregrounding does not silence it |
| Installable on iOS Safari (one-time A2HS banner) and Android Chrome (Lighthouse PWA audit) | MOB-12 | iOS never prompts programmatically; Lighthouse needs a running browser; on-device install confirmation required | Add to Home Screen on both platforms; confirm standalone launch + circular mascot icon; Chrome DevTools → Lighthouse → PWA "installable" passes. *(HTML manifest-link discovery is now automated — see test_pwa.py::test_manifest_link_in_head.)* |
| Responsive visual at 375×667 + 390×844 (cards, no h-scroll, ≥44px, sheet/dialog) | MOB-03 / MOB-04 / MOB-08 / MOB-13 | Visual layout verification; Playwright automation is Phase 12 / TEST-06 | DevTools responsive mode; cross-check each surface against 11-POLISH-AUDIT.md. Human checkpoint approved by John (11-05-SUMMARY). |
| Native OS picker vs searchable dropdown at 375px | MOB-07 | Native picker rendering is OS-driven; not assertable in-process | Open equipment-type/roast-level (native) and the coffees searchable dropdown at 375px |
| Warm minimalist palette + system-preference dark mode | UX-01 | Visual / OS-preference driven | Toggle OS dark mode; confirm cream/espresso palette and `darkMode: 'media'` switch |

---

## Validation Sign-Off

- [x] All automatable tasks have an `<automated>` verify; manual-only items documented with instructions
- [x] Sampling continuity: no 3 consecutive automatable tasks without automated verify
- [x] Wave 0 covered all MISSING references; the post-audit gap (manifest-link discovery) is now automated
- [x] No watch-mode flags
- [x] Feedback latency < 10s (phase subset ~8s)
- [x] `nyquist_compliant: true` set in frontmatter (no automatable gaps remain)

**Approval:** validated 2026-05-23 — all automatable requirements have automated verification; remaining items are real-device / visual gates owned by manual UAT + Phase 12 (TEST-06) Playwright.

---

## Validation Audit 2026-05-23

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

**Gap GAP-1 (MOB-12 / MOB-11) — RESOLVED.** No automated test asserted the PWA discovery link tags (`<link rel="manifest">`, `apple-touch-icon`, iOS web-app meta) were present in served HTML. This was the exact blocker the phase verifier caught (both Plan 01 and Plan 03 omitted the tags from `base.html`, breaking installability / ROADMAP SC#1) and fixed post-verification with no regression coverage. Added `test_manifest_link_in_head` and `test_apple_touch_icon_and_web_app_meta_in_head` to `tests/test_pwa.py` (anonymous `GET /login`, asserting the unconditional `<head>` tags). Commit `0323d4d`. Phase subset now 34 tests, all green, 0 skips.

**Observation (non-blocking):** `tests/test_nav.py` guards its 5 tests with `_require_nav_wired()` which calls `pytest.skip` on a `config_hub` import error. Harmless today (router is wired; all 5 run green), but it is a latent skip-as-green path — if `config_hub` ever fails at import, those tests silently skip instead of failing. Consider hardening to a hard failure in a future pass.
