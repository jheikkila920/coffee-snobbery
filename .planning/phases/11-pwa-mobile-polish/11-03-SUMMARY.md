---
phase: 11-pwa-mobile-polish
plan: "03"
subsystem: navigation
tags: [nav, pwa, sign-out, login, config-hub, alpine-csp, service-worker]
dependency_graph:
  requires: [pwa-icons, service-worker]
  provides: [persistent-nav, sign-out, config-hub, head-extra-block, sw-registration, ios-banner, dark-login]
  affects: [app/templates/base.html, app/main.py]
tech_stack:
  added: []
  patterns:
    - Alpine CSP Alpine.data() factories registered in alpine:init (navBar, accountDropdown, iosBanner)
    - Persistent nav frame in base.html (top nav >=768px, fixed bottom tab nav <768px)
    - Nonce-tagged inline SW registration script (StaticFiles bypasses the nonce pipeline)
    - Inline style="display:none" + x-show for pre-hydration hidden elements (no [x-cloak] rule)
    - SW same-origin-only fetch guard (cross-origin CDN left to the browser)
key_files:
  created:
    - app/routers/config_hub.py
    - app/templates/pages/config_hub.html
    - app/static/js/alpine-components/nav-bar.js
    - app/static/js/alpine-components/account-dropdown.js
    - app/static/js/alpine-components/ios-banner.js
    - tests/test_nav.py
  modified:
    - app/templates/base.html
    - app/templates/pages/login.html
    - app/static/css/tailwind.src.css
    - app/main.py
    - app/static/js/sw.js
    - tests/test_phase02_smoke.py
decisions:
  - "All base.html nav chrome lives in this plan so later plans never collide on it (top nav, bottom tab nav, head_extra block, SW registration, iOS banner)"
  - "Two separate x-data=searchBar instances (desktop inline + mobile sheet) replace the Phase 10 single-header instance; mobile sheet absorbed into the mobile top strip"
  - "Mobile sign-out lives only in the /config hub bottom section (D-03); desktop sign-out in the top-nav account dropdown (D-05) — both CSRF POST to /logout"
  - "Login page wraps content in an always-dark espresso-950 div rather than touching the base body class (D-14)"
  - "CHECKPOINT FIX: SW must skip cross-origin requests — intercepting the Alpine/htmx CDN as opaque responses broke Alpine hydration once the SW controlled the page"
  - "CHECKPOINT FIX: x-show sheet + iOS banner need inline display:none (no [x-cloak] rule exists) so a slow/failed Alpine can never leave the full-screen search sheet stuck open"
metrics:
  duration_minutes: 75
  completed_date: "2026-05-23"
  tasks_completed: 4
  files_changed: 12
requirements_met: [MOB-01, MOB-02, MOB-11, UX-01, UX-03, UX-04]
---

# Phase 11 Plan 03: Persistent Nav Frame + Brand Chrome Summary

Built the persistent navigation frame the app has owed since Phase 6 retired the placeholder index: bottom tab nav (Home/Log/Config/Admin) <768px, top horizontal nav (logo + wordmark + absorbed search + account dropdown) >=768px, the first sign-out affordance since Phase 6 (desktop dropdown + mobile config-hub), service-worker registration, the empty `{% block head_extra %}` the GBM plan needs, the iOS install banner, a dark mascot-hero login redesign, and the `/config` catalog hub. Three new Alpine CSP components registered.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Three Alpine CSP components (navBar, accountDropdown, iosBanner) | 76bb796 | nav-bar.js, account-dropdown.js, ios-banner.js |
| 2 | base.html nav frame + head_extra + SW registration + iOS banner | c613614 | app/templates/base.html, app/static/css/tailwind.src.css |
| 3 | Config hub route + page + dark login + main.py wiring + tests | 3c6774b | app/routers/config_hub.py, config_hub.html, login.html, app/main.py, tests/test_nav.py |
| 4 | Human-verify checkpoint (passed after fixes below) | ea07e16, dfd51e6, 1a76ff2 | base.html, login.html, sw.js |

## Verification

Automated (in-container, no skips):
- `tests/test_nav.py` + `tests/test_phase02_smoke.py`: 7 passed
- base.html grep gates: head_extra, serviceWorker.register('/sw.js'), x-data="navBar", x-data="iosBanner", action="/logout", no |safe
- `/config` returns 200 authenticated; admin nav link present for admin / absent for non-admin

Human-verify checkpoint (375px + desktop, clean service-worker cache): login dark mascot hero, persistent nav, Admin hidden for non-admin, sign-out works on mobile (config hub) and desktop (dropdown), search sheet opens/closes, no CSP console violations, SW registered at scope "/". **Approved by John.**

## Checkpoint Feedback Fixes

The human-verify checkpoint surfaced four issues, all fixed before approval:

1. **Logo too small / mobile chrome bare** (ea07e16) — desktop nav logo h-8→h-12 (wordmark text-lg→text-xl); mobile top strip gained the logo badge + wordmark on the left (was a bare right-aligned search icon).
2. **Sign-in mascot hero too small** (dfd51e6) — login hero max-w 280/360 → w-full 340/500 (source image <=720px, no upscaling).
3. **Search sheet stuck open on /config with a dead X** (1a76ff2) — root cause: the service worker intercepted cross-origin GETs (Alpine + htmx CDN) and re-served them as opaque responses, breaking Alpine hydration once the SW controlled the page. Added `if (url.origin !== self.location.origin) return;` so the SW only handles same-origin.
4. **No pre-hydration hidden fallback** (1a76ff2) — added inline `style="display:none"` to the mobile search sheet and iOS banner (this app has no [x-cloak] rule) so a slow/failed Alpine can never leave the full-screen sheet blocking the page.

A large share of the checkpoint loop was lost to stale service-worker cache masking server rebuilds; resolved by a full DevTools "Clear site data". Recorded as a memory for future UI verification.

## Deviations from Plan

- Plan-described fixes above (logo sizing, hero sizing, SW cross-origin guard, display:none fallbacks) were not in the original task list; they are checkpoint-driven corrections to Tasks 2-3.
- `app/static/js/sw.js` (a Plan 01 file) was modified here to fix the cross-origin hydration bug — a justified cross-plan touch driven by the checkpoint.

## Known Stubs

None.

## Threat Flags

None new. T-11-08 (sign-out CSRF), T-11-09 (admin nav hidden for non-admin), T-11-10 (nonce-tagged scripts, no |safe, no inline hx-on:) all mitigated and verified.

## Self-Check: PASSED

Files confirmed present: app/routers/config_hub.py, app/templates/pages/config_hub.html, app/static/js/alpine-components/{nav-bar,account-dropdown,ios-banner}.js, tests/test_nav.py; modified base.html, login.html, tailwind.src.css, main.py, sw.js, test_phase02_smoke.py.

Commits confirmed: 76bb796, c613614, 3c6774b, ea07e16, dfd51e6, 1a76ff2.
