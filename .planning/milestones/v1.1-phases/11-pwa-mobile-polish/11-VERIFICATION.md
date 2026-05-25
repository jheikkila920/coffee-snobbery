---
phase: 11-pwa-mobile-polish
verified: 2026-05-23T00:00:00Z
status: human_needed
score: 16/16 must-haves verified (1 blocking gap resolved during execution; remaining items are human/real-device verification)
overrides_applied: 0
gaps: []
resolved_gaps:
  - truth: "Snobbery becomes installable on iOS Safari and Android Chrome (MOB-12, ROADMAP SC #1)"
    resolution: |
      RESOLVED post-verification (commit wiring manifest links into base.html): added
      <link rel="manifest" href="/manifest.json">, <link rel="apple-touch-icon" href="/static/img/apple-touch-icon.png">,
      and apple-mobile-web-app-* meta tags to base.html <head>. Confirmed present in served HTML (curl /login).
      The manifest is now discoverable so browsers can offer install; on-device install confirmation is the
      human-verification item below.
    artifacts:
      - path: "app/templates/base.html"
        issue: "FIXED — manifest + apple-touch-icon links + iOS meta tags now present in <head>"
human_verification:
  - test: "Real-device iOS Safari installability"
    expected: |
      After the manifest link tag is added: Install Snobbery to iOS Home Screen via Share -> Add to Home
      Screen. Confirm the app icon is the circular mascot badge (not a screenshot). Confirm standalone
      mode (no Safari chrome). Confirm the iOS install banner appeared before install and was dismissible.
    why_human: "iOS Safari does not report PWA installability programmatically; requires real device"
  - test: "Android Chrome installability (Lighthouse)"
    expected: |
      After the manifest link tag is added: Chrome DevTools -> Lighthouse -> PWA audit passes installability
      criteria. Confirm Add to Home Screen prompt appears when browsing the app logged in.
    why_human: "Lighthouse PWA audit requires a running server and browser interaction; automated only in Phase 12"
  - test: "BREW-13: Wake lock on real device (deferred by user)"
    expected: |
      On a real iPhone (note iOS version): install as PWA, start a guided brew, confirm screen stays on for
      the full brew duration; 'Screen stays on' indicator shows green (native >= iOS 18.4) or yellow
      (NoSleep fallback on older iOS). Background app for 10s and confirm re-acquisition. Chime plays on
      step advance. Vibration is silently absent (expected on iOS). On Android Chrome: confirm native wake
      lock (green), chime, and vibration all work.
    why_human: "Wake Lock API, AudioContext, and standalone PWA behavior cannot be tested without a real device. Deferred per user decision until VPS deploy."
  - test: "MOB-13: Responsive visual verification (375x667 and 390x844)"
    expected: |
      All list pages (Sessions, Coffees, Recipes, Equipment, Roasters, Flavor Notes) render as cards with
      no horizontal scroll at 375px. Every card-mode control is comfortably tappable. Mini-modal is
      full-screen sheet < 768px and centered dialog >= 768px. Bottom nav present and functional.
    why_human: "Human checkpoint was approved by John per 11-05-SUMMARY.md. Playwright automation is Phase 12/TEST-06."
---

# Phase 11: PWA + Mobile Polish — Verification Report

**Phase Goal:** Snobbery becomes installable on iOS Safari and Android Chrome, behaves correctly at 375x667 and 390x844, ships the bottom-tab nav on mobile + top nav on desktop, collapses all tables to card lists at mobile widths, replaces native pickers with full-screen sheets where appropriate, lands the warm-minimalist palette with system-preference dark mode, and finally ships Guided Brew Mode — full-screen timer, audio + haptic step-transition cues, wake lock with iOS fallback (silent audio loop / NoSleep.js), re-acquisition on visibilitychange, and a visible "Screen will stay on" indicator.

**Verified:** 2026-05-23
**Status:** GAPS FOUND (1 gap)
**Re-verification:** No — initial verification
**Automated tests run in-container:** 32/32 passed (tests/test_pwa.py, tests/test_migrations.py, tests/test_nav.py, tests/routers/test_gbm.py)
**Code review criticals resolved:** CR-01 (brew_time_seconds edit path) and CR-02 (SW caches auth shell) both fixed in commit 5ffa4d3 — verified in code.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /manifest.json returns 200 with application/manifest+json and all UX-02 strings | VERIFIED | test_manifest_200 green; pwa.py serves exact locked strings |
| 2 | GET /sw.js returns 200 with Service-Worker-Allowed: / and Cache-Control: no-cache | VERIFIED | test_sw_headers green; Response headers confirmed in pwa.py |
| 3 | SW correctly bypasses non-GET (CSRF safety) and cross-origin requests | VERIFIED | sw.js line 53: `if (req.method !== 'GET') return`; line 61: origin check |
| 4 | SW cache name embeds build hash; '/' not in APP_SHELL (CR-02 fix) | VERIFIED | sw.js APP_SHELL confirmed; '/' explicitly excluded with comment |
| 5 | app is installable via manifest + SW — manifest discoverable from HTML | FAILED | base.html has NO `<link rel="manifest">` tag; browser cannot discover manifest |
| 6 | Apple touch icon linked from HTML head (MOB-11 "iOS install meta tags") | FAILED | base.html has no `<link rel="apple-touch-icon">` tag; asset exists at /static/img/apple-touch-icon.png |
| 7 | Persistent nav: bottom tab nav <768px with safe-area inset, top nav >=768px | VERIFIED | base.html confirmed; navBar Alpine component confirmed; test_authenticated_home_has_nav_bar_component passes |
| 8 | Admin tab/link hidden for non-admins (MOB-02) | VERIFIED | base.html lines 77-79 + 261-270 gated by `{% if request.state.user.is_admin %}`; test_non_admin_home_has_no_admin_link passes |
| 9 | Sign-out works on mobile (config hub) and desktop (dropdown), both CSRF-protected POST | VERIFIED | base.html account dropdown + config_hub.html both have CSRF POST form to /logout; test_config_hub_has_mobile_signout_form passes |
| 10 | brew_time_seconds column, schema validation (0..86400), write path on create AND edit | VERIFIED | Migration chained off p10_search_indexes; model + schema confirmed; brew.py lines 810 (create) + 926 (update); _WRITABLE_FIELDS includes brew_time_seconds; edit form seeds value (line 855); CR-01 fix confirmed |
| 11 | GBM launches full-screen with timer, steps, audio/vibration cues, pause/resume, cancel, done flow | VERIFIED | brew_guided.html confirmed; guidedBrewMode component present with all behaviors; test_gbm routes 200/404/401/no-steps green |
| 12 | Wake lock code path: native navigator.wakeLock -> NoSleep.js fallback -> visibilitychange re-acquire -> visible indicator | VERIFIED (code) | guided-brew-mode.js lines 238-285 implement full path; wakeLockState tracks held/fallback/none; real-device pending |
| 13 | All list fragments: dual table/card layout, no horizontal scroll at 375px, 44px tap targets | VERIFIED | Six *_list.html all have md:hidden card splits; min-h-[44px] confirmed on all row files; POLISH-AUDIT.md documents per-surface fixes |
| 14 | Mini-modal is full-screen sheet <768px / centered dialog >=768px (MOB-08) | VERIFIED | roaster_modal.html + flavor_note_modal.html: `fixed inset-0 z-50` + `md:max-w-lg`; no custom.css |
| 15 | Warm minimalist palette as Tailwind theme, system-preference dark mode (UX-01) | VERIFIED | tailwind.config.js: `darkMode: 'media'`; cream/espresso palette tokens present; base.html body class dark: variants confirmed |
| 16 | iOS install banner present and dismissible via localStorage (MOB-11 banner component) | VERIFIED | iosBanner Alpine component confirmed; base.html x-data="iosBanner" confirmed; localStorage key snobbery:ios-banner-dismissed |

**Score: 14/16 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/routers/pwa.py` | /manifest.json + /sw.js routes with custom headers | VERIFIED | Present; Service-Worker-Allowed and Cache-Control correct |
| `app/static/js/sw.js` | SWR-shell / network-first / non-GET bypass | VERIFIED | Present; __BUILD_HASH__ token; cross-origin guard; '/' excluded from APP_SHELL |
| `app/migrations/versions/p11_brew_time_seconds.py` | Additive nullable migration off p10_search_indexes | VERIFIED | Present; down_revision = "p10_search_indexes"; upgrade/downgrade correct |
| `app/models/brew_session.py` | brew_time_seconds: Mapped[int | None] | VERIFIED | Line 133 confirmed |
| `app/schemas/brew_session.py` | brew_time_seconds Field(ge=0, le=86400) | VERIFIED | Line 99 confirmed |
| `app/services/brew_sessions.py` | brew_time_seconds in _WRITABLE_FIELDS + create_brew_session param | VERIFIED | Lines 85, 176, 204 confirmed |
| `app/routers/brew_guided.py` | GET /brew/guided, require_user, 404 on missing | VERIFIED | Present; routes correctly |
| `app/templates/pages/brew_guided.html` | Full-screen GBM with three screens, NoSleep.js via head_extra | VERIFIED | Present; data-steps + guidedBrewMode + fixed inset-0 z-50 |
| `app/static/js/alpine-components/guided-brew-mode.js` | guidedBrewMode component, no eval | VERIFIED | Present; eval-free confirmed by grep |
| `app/static/js/vendor/NoSleep.min.js` | Self-hosted, eval-free | VERIFIED | Present; no real eval() calls |
| `app/routers/config_hub.py` | GET /config, require_user | VERIFIED | Present; test_config_hub_returns_200 passes |
| `app/templates/pages/config_hub.html` | Five catalog links + mobile sign-out CSRF form | VERIFIED | Present; /logout form with CSRF field |
| `app/static/js/alpine-components/nav-bar.js` | Alpine.data('navBar') | VERIFIED | Present |
| `app/static/js/alpine-components/account-dropdown.js` | Alpine.data('accountDropdown') | VERIFIED | Present |
| `app/static/js/alpine-components/ios-banner.js` | Alpine.data('iosBanner'), localStorage | VERIFIED | Present |
| `app/templates/base.html` | Nav frame, head_extra, SW registration, iOS banner; NO manifest link | PARTIAL | All specified items present; `<link rel="manifest">` and `<link rel="apple-touch-icon">` missing |
| `app/static/img/icon-192.png` | 192x192 circular PNG | VERIFIED | Confirmed by Pillow check |
| `app/static/img/icon-512-maskable.png` | 512x512 maskable, opaque corners | VERIFIED | Corner pixel alpha=255 confirmed |
| `app/static/img/apple-touch-icon.png` | 180x180 circular PNG | VERIFIED | Confirmed by Pillow check |
| `.planning/phases/11-pwa-mobile-polish/11-POLISH-AUDIT.md` | Per-surface 375px audit with PASS/fix notes | VERIFIED | Present; covers 11 surfaces |
| `tests/test_pwa.py` | Manifest, SW headers, start_url 200 | VERIFIED | 3/3 pass |
| `tests/test_nav.py` | /config 200/401, admin link present/absent, navBar present | VERIFIED | 6/6 pass |
| `tests/routers/test_gbm.py` | GBM 200/404/401/no-steps, brew_time round-trip | VERIFIED | 7/7 pass |
| `tests/test_migrations.py` | brew_time_seconds column + schema validation | VERIFIED | 16/16 pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| app/main.py | app.routers.pwa | include_router(pwa_router.router) | WIRED | Line 233 confirmed |
| app/main.py | app.routers.brew_guided | include_router before brew_router | WIRED | Line 244 confirmed; static /brew/guided before dynamic /brew/{id} |
| app/main.py | app.routers.config_hub | include_router(config_hub_router.router) | WIRED | Line 247 confirmed |
| app/templates/base.html | /sw.js | navigator.serviceWorker.register('/sw.js') | WIRED | Line 50 confirmed |
| app/templates/base.html | /logout | CSRF POST forms (dropdown + absent for manifest link) | WIRED | Line 143 confirmed; config_hub.html line 59 confirmed |
| app/templates/base.html | /manifest.json | <link rel="manifest"> | NOT WIRED | Tag absent from base.html; manifest route exists but is undiscoverable by browsers |
| app/routers/brew.py | brew_sessions.update_brew_session | brew_time_seconds param | WIRED | Line 926; _WRITABLE_FIELDS contains brew_time_seconds |
| app/templates/pages/brew_guided.html | guided-brew-mode.js | head_extra block + data-steps attribute | WIRED | Lines 18-25 + line 32 confirmed |
| app/templates/fragments/recipe_row.html | /brew/guided | "Start guided brew" link | WIRED | Lines 49 + 100 confirmed |
| app/templates/pages/brew_form.html | /brew/guided | "Brew with timer" button | WIRED | Line 308 confirmed |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| brew_guided.html | recipe.steps | brew_guided.py -> recipes_service.get_recipe(db, recipe_id) | Yes — DB query | FLOWING |
| brew_form.html | values['brew_time_seconds'] | brew.py new_brew_form reads ?brew_time= + edit_brew_form seeds from session | Yes — DB read on edit | FLOWING |
| config_hub.html | user.username | config_hub.py Depends(require_user) | Yes — session user | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| /manifest.json returns 200 with masked UX-02 strings | In-container pytest test_manifest_200 | PASS | PASS |
| /sw.js returns 200 with Service-Worker-Allowed: / | In-container pytest test_sw_headers | PASS | PASS |
| /config returns 200 for authenticated user | In-container pytest test_config_hub_returns_200 | PASS | PASS |
| GBM route 200/404/401 + brew_time round-trip | In-container pytest tests/routers/test_gbm.py | 7 PASS | PASS |
| Icon dimensions and maskable corner opacity | Pillow check in-container | ICONS_OK | PASS |
| SW non-GET bypass and cross-origin guard in sw.js | grep in-container | SW_OK | PASS |
| brew_time_seconds write path (create + edit) | grep in-container | BREW_TIME_WIRED | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BREW-12 | Plans 02, 04 | GBM full-screen timer, steps, audio/vibration, cancel, done-prefill, brew_time_seconds | SATISFIED | GBM fully implemented; 7/7 tests green; brew_time create+edit wired |
| BREW-13 | Plan 04 | Wake lock, re-acquire on visibilitychange, NoSleep fallback, visible indicator | PARTIAL (code-complete, real-device pending) | Code verified; real-device test deferred by user to VPS deploy |
| MOB-01 | Plan 03 | Bottom tab nav <768px + top nav >=768px with safe-area inset | SATISFIED | base.html confirmed; navBar tests green |
| MOB-02 | Plan 03 | Admin tab hidden for non-admins | SATISFIED | Jinja gating confirmed; test_non_admin_home_has_no_admin_link passes |
| MOB-03 | Plan 05 | Tables collapse to card lists; no horizontal scroll | SATISFIED | All six list fragments confirmed; POLISH-AUDIT documents per-surface |
| MOB-04 | Plans 04, 05 | All tap targets >=44x44px | SATISFIED | min-h-[44px] on all card-mode controls; recipe_row fixed in 497a4ef |
| MOB-07 | Plan 05 | Native select for short lists; HTMX dropdown for coffees | SATISFIED | Audit confirmed; no changes needed |
| MOB-08 | Plan 05 | Modals full-screen sheets <768px / dialogs >=768px | SATISFIED | roaster_modal + flavor_note_modal confirmed |
| MOB-09 | Plan 01 | manifest.json with all required fields | SATISFIED | Route confirmed; test_manifest_200 green |
| MOB-10 | Plan 01 | /sw.js with Service-Worker-Allowed: / | SATISFIED | Route confirmed; test_sw_headers green |
| MOB-11 | Plan 03 | Apple touch icon + iOS install meta tags; banner | PARTIAL | iosBanner component confirmed; but <link rel="apple-touch-icon"> absent from base.html head |
| MOB-12 | Plan 01 | Installable on iOS Safari and Android Chrome | BLOCKED | manifest route exists but <link rel="manifest"> absent from base.html; browser cannot discover manifest |
| MOB-13 | Plan 05 | Responsive smoke at 375x667 and 390x844 (manual in Phase 11) | SATISFIED (manual evidence) | POLISH-AUDIT.md covers 11 surfaces; human checkpoint approved by John per 11-05-SUMMARY |
| UX-01 | Plan 03 | Warm minimalist palette + system-preference dark mode | SATISFIED | tailwind.config.js darkMode: 'media'; cream/espresso palette tokens in base.html |
| UX-02 | Plan 01 | PWA branding strings locked | SATISFIED | test_manifest_200 asserts all three locked strings |
| UX-03 | Plan 03 | Title format "Snobbery — {Page Name}" | SATISFIED | base.html line 11 confirmed |
| UX-04 | Plans 03, 04, 05 | Snobbery-tone empty states | SATISFIED | "The snobbery awaits." in session_list + recent_brews; "Recipe has no steps." in brew_guided + recipe_row |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| app/routers/pwa.py | 13, 46 | "XXXXXXXX" in docstring | Info | Format example in comment, not a debt marker — NOT a blocker |
| tests/routers/test_gbm.py | 106-109 | f-strings with no interpolation (ruff F541); unscoped DELETE FROM | Warning | IN-02 from code review; pre-existing isolation gap, not Phase 11 regression |
| app/static/js/alpine-components/guided-brew-mode.js | 155-180 | Zero-duration step edge case | Warning | WR-02 from code review; timer desynchronizes on equal-offset recipe steps |
| app/routers/pwa.py | 94-97 | JSONResponse uses headers= override instead of media_type= for Content-Type | Warning | WR-06 from code review; test passes via 'in' check; future Starlette version could break silently |

No TBD / FIXME / XXX debt markers found in any Phase 11 modified files.

---

### Human Verification Required

#### 1. Real-Device iOS Installability

**After fixing the manifest link tag gap:**
**Test:** Install Snobbery to iOS Home Screen via the iosBanner instructions (Share -> Add to Home Screen).
**Expected:** App icon is the circular mascot badge; standalone mode opens (no Safari chrome); banner appeared once and was dismissible.
**Why human:** iOS Safari does not expose PWA installability programmatically; requires a real iPhone.

#### 2. Android Chrome Installability (Lighthouse)

**After fixing the manifest link tag gap:**
**Test:** Chrome DevTools -> Lighthouse -> PWA audit while logged in.
**Expected:** "Installable" check passes; Add to Home Screen prompt appears.
**Why human:** Lighthouse audit requires a running server + browser; automated Playwright coverage is Phase 12/TEST-06.

#### 3. BREW-13: Wake Lock (Deferred — Real Device)

**Test:** Per 11-04-PLAN.md Task 5 procedure: real iPhone, install as PWA, start guided brew, confirm screen stays on, indicator shows (green native >= iOS 18.4 / yellow fallback), chime on step advance, re-acquire after backgrounding. Repeat on Android Chrome (expect native lock + vibration).
**Expected:** Screen stays on for full brew duration; wakeLockState indicator visible; AudioContext chime audible on step advance.
**Why human:** Wake Lock API, AudioContext, and PWA standalone behavior require a real device. Deferred by user decision to next VPS deploy.

#### 4. MOB-13: Responsive Visual Verification

**Note:** Human checkpoint was approved by John (per 11-05-SUMMARY.md). This item is informational for the record.
**Test:** Chrome DevTools responsive mode at 375x667 and 390x844 — all list pages as cards, no horizontal scroll, >=44px controls, sheet/dialog modal modes, native pickers.
**Expected:** All surfaces match the PASS entries in 11-POLISH-AUDIT.md.
**Why human:** Visual layout verification; Playwright automation is Phase 12/TEST-06.

---

### Gaps Summary

**One gap blocking the phase goal, one partial (MOB-11).**

**Root cause:** Plans 01 and 03 both missed adding `<link rel="manifest">` and `<link rel="apple-touch-icon">` to base.html's `<head>`. These are two-line fixes. The manifest endpoint exists, the service worker registers, the icons are committed — but without the HTML discovery link tag, browsers cannot connect the manifest to the app for installability purposes.

**Specifically:**
1. `<link rel="manifest" href="/manifest.json">` is absent — directly blocks MOB-12 (installability) and ROADMAP SC #1. This is a BLOCKER.
2. `<link rel="apple-touch-icon" href="/static/img/apple-touch-icon.png">` is absent — partially blocks MOB-11 ("Apple touch icon + iOS install meta tags"). The iosBanner is present. This is a WARNING.

**All other phase deliverables are fully implemented.** The two code review critical blockers (CR-01 brew_time edit path, CR-02 SW auth-shell caching) are both confirmed fixed in commit 5ffa4d3. The 32 automated tests pass. The GBM wake-lock code path is complete; only real-device validation is pending (explicitly deferred by user).

---

_Verified: 2026-05-23_
_Verifier: Claude (gsd-verifier)_
