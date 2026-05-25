---
phase: 13-pwa-ux-fixes
verified: 2026-05-25T18:00:00Z
status: passed
score: 9/9 structural must-haves verified; all human-verify items approved by John 2026-05-25
overrides_applied: 0
human_verification:
  - test: "C9 two-build gate — confirm SW cache key bumps between consecutive builds"
    expected: "Two docker compose builds produce different build_id.txt timestamps and different snobbery-v cache names in /sw.js"
    why_human: "build_id.txt only exists in a baked image; pytest source-tree run sees 'dev'; orchestrator confirmed this passed empirically this session, but the verification agent cannot re-run it"
  - test: "C10 — PWA icons show full mascot undistorted, maskable icon has cream-50 corners"
    expected: "logo-badge.png / icon-512.png show the full bean+top-hat+monocle+cup+steam mascot inscribed in the circle without squishing; icon-512-maskable.png has a solid cream-50 background with 10% safe-zone padding"
    why_human: "Image content is a visual judgment; the generator script and source file (hero.jpg, 1021x1021 square) are verified structurally but the rendered appearance requires human inspection"
  - test: "C1 — iOS standalone PWA top strip clears the status bar on a real iPhone"
    expected: "In standalone mode the mobile top strip does not overlap the iOS status bar; the time/carrier strip is visible above the Snobbery header"
    why_human: "env(safe-area-inset-top) reports 0 on desktop and in Playwright; this technique is unproven on-device — same technique as the UNVERIFIED bottom-nav fix (commit 982c0e6, memory safe-area-fix-unverified). Must verify on a real iPhone in standalone mode. If it fails both top and bottom need revision."
  - test: "C4 — dark toggle visual: instant switch + no-FOUC on reload + Light wins on dark-system device"
    expected: "Clicking Dark applies instantly with no flash; reloading the page starts in the correct theme; selecting Light on an iOS/macOS device set to system-dark still shows the light theme"
    why_human: "Alpine reactivity, localStorage timing, and matchMedia interaction cannot be verified programmatically; requires DevTools simulation at 375px and real device test for system-override"
  - test: "C4 — login and setup pages remain always-dark regardless of toggle"
    expected: "Navigating to /login or /setup shows the dark espresso UI regardless of the snobbery:theme localStorage value"
    why_human: "Login/setup templates are not auth-gated and do not inherit the base.html dark toggle; requires browser inspection to confirm the always-dark constraint (D-02)"
  - test: "C6 — guided-brew cue controls read clearly at 375px"
    expected: "The On/Off buttons for Chime and Vibrate on the start screen (and Chime:On/Off Vibrate:On/Off in the timer screen) are immediately understandable; no role=switch confusion"
    why_human: "UX clarity is a subjective judgment; the structural absence of role=switch is verified, but whether the redesigned labeled buttons read clearly requires a human at 375px"
  - test: "C7 — brew ratio recalculates on programmatic prefill; stars render single-line at 375px"
    expected: "Selecting a coffee or recipe that prefills dose/water shows the updated 1:N.NN ratio immediately; all 5 star zones appear on one row without wrapping"
    why_human: "Alpine x-init + x-ref re-sync happens at runtime after HTMX swap; flex-nowrap prevents wrapping structurally but actual 375px pixel rendering requires visual verification"
  - test: "C5 + C8 — Guided Brew reachable from Home/Sessions; Export/Import accessible from config hub"
    expected: "Tapping 'Guided Brew' on the home page and sessions page routes to /recipes; tapping 'Export / Import sessions' in the config hub routes to /data-tools with the export and import controls visible"
    why_human: "Navigation placement and tap-target clarity require a human to walk through the actual app at 375px; the structural links are verified but the UX flow must be confirmed"
---

# Phase 13: PWA UX Fixes — Verification Report

**Phase Goal:** Resolve the buildable UAT findings from John's iOS PWA testing and ensure deployed fixes actually reach the installed PWA. Post-launch polish on the v1 trunk; no schema/auth/AI/deployment-topology changes.
**Verified:** 2026-05-25
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (9 success criteria)

| # | Criterion | Truth | Status | Evidence |
|---|-----------|-------|--------|----------|
| 1 | C1 | iOS standalone top strip carries env(safe-area-inset-top) padding | VERIFIED (structural) / HUMAN (on-device) | `pt-[env(safe-area-inset-top)]` on the `md:hidden` mobile top strip div at base.html:173; also on the mobile search sheet at base.html:196 |
| 2 | C2 | Creating equipment AND coffee renders the complete list (no malformed row, no page refresh); CR-01 validation-error regression fixed; regression tests cover error path | VERIFIED | coffee_form.html L52-53: `form_target="#coffee-form-mount"` (not #coffee-list); equipment_form.html L19-20: `form_target="#equipment-form-mount"`; success returns `coffee_create_success.html` / `equipment_create_success.html` with `hx-swap-oob="innerHTML"` on the list div; 4 regression tests in `test_equipment_create_fragment.py` cover both success and error paths |
| 3 | C3 | Equipment cards at 375px use flex-wrap pills | VERIFIED | `equipment_row.html` L28: `<div class="mt-1 flex flex-wrap gap-2">` with two pill spans for type and usage_count; comment explicitly marks C3 |
| 4 | C4 | 3-state dark toggle on config hub; darkMode:'selector' (v3); persists in snobbery:theme; no-FOUC nonce'd head script; Auto default | VERIFIED (structural) / HUMAN (visual) | `tailwind.config.js` L27: `darkMode: 'selector'`; `dark-toggle.js`: `Alpine.data('darkToggle')` with `localStorage.getItem('snobbery:theme')`, `setTheme()`, `isActive()`; `base.html` L26: synchronous nonce'd inline script with `snobbery:theme` before the CSS link; `config_hub.html` L69: `x-data="darkToggle"` with Auto/Light/Dark buttons calling `setTheme()`; `check_c4_dark.py` structural checker verifies all invariants |
| 5 | C5 | Guided Brew reachable from home.html AND sessions.html -> /recipes; recipe_row.html regression test covers with-steps vs no-steps | VERIFIED | `home.html` L21-24: `<a href="/recipes">Guided Brew</a>`; `sessions.html` L20-23: same link with C5 comment; `tests/templates/test_recipe_row.py`: 4 parametrized tests covering card+row x with-steps+no-steps |
| 6 | C6 | Guided-brew cue controls redesigned (no role=switch) preserving snobbery:gbm:cues | VERIFIED (structural) / HUMAN (clarity) | `brew_guided.html`: role=switch absent; start-screen uses `role="group"` with explicit "On"/"Off" text buttons and `aria-pressed`; timer-screen uses `<span x-text="cuePrefs.chime ? 'Chime: On' : 'Chime: Off'"`; `toggleChime()` / `toggleVibrate()` handlers preserved unchanged |
| 7 | C7 | Brew ratio recalculates on programmatic prefill (x-init re-sync); 0-5 stars single-line at 375px (flex-nowrap) | VERIFIED (structural) / HUMAN (visual) | `brew_prefill_fields.html` L49: `x-init="setDose($refs.doseInput ? $refs.doseInput.value : ''); setWater($refs.waterInput ? $refs.waterInput.value : '')"` fires on every HTMX swap; `brew_form.html` L118: `class="flex flex-nowrap items-center gap-1 min-h-[56px] py-2"` on the star row |
| 8 | C8 | Export/Import at /data-tools (require_user); linked from config hub; removed from sessions view; /brew/export + /brew/import UNCHANGED | VERIFIED | `data_tools.html` exists with `/brew/import` form action; `brew.py` L635: `@data_router.get("/data-tools")` with `Depends(require_user)`; `main.py` L270: `app.include_router(brew_router.data_router)`; `sessions.html`: no export/import links present; `test_brew_router.py`: `test_data_tools_authed_returns_page` + `test_data_tools_requires_auth`; `/brew/export` and `/brew/import` routes exist in brew.py with unchanged `router = APIRouter(prefix="/brew")` |
| 9 | C9 | SW CACHE_NAME bumps per build (build_id.txt) — empirically proven this session | VERIFIED (structural + orchestrator-confirmed runtime) | `Dockerfile` L63-64: `echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt; echo "Build ID: $(cat app/static/build_id.txt)"` in stage-1 RUN block; L109: `COPY --from=tailwind-builder ... /build/app/static/build_id.txt ./app/static/build_id.txt`; `pwa.py` L51-53: `_get_build_hash()` prefers `build_id.txt` (truncated to 16 chars) with CSS-hash + "dev" fallback; `tests/test_pwa.py`: `test_sw_cache_name_is_versioned` + `test_build_hash_prefers_build_id_txt`; orchestrator confirmed two-build behavior this session |

**Score:** 9/9 truths structurally VERIFIED. 8 items also have human-verification items (visual/on-device/behavioral); C9 has an orchestrator-confirmed runtime result.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `Dockerfile` | build_id.txt unconditional write + COPY | VERIFIED | Stage-1 RUN block L63-64 writes timestamp; L109 COPYs to runtime |
| `app/routers/pwa.py` | `_get_build_hash()` prefers build_id.txt | VERIFIED | L51-53: `Path("app/static/build_id.txt")` checked first |
| `tests/test_pwa.py` | `test_sw_cache_name_is_versioned` + `test_build_hash_prefers_build_id_txt` | VERIFIED | Both functions present at L128 and L155 |
| `app/templates/fragments/coffee_form.html` | create form_target = `#coffee-form-mount` | VERIFIED | L52-53: `form_target = "#coffee-form-mount"` |
| `app/templates/fragments/equipment_form.html` | create form_target = `#equipment-form-mount` | VERIFIED | L19-20: `form_target = "#equipment-form-mount"` |
| `app/templates/fragments/coffee_create_success.html` | OOB list update + empty body for form mount | VERIFIED | L10: `<div id="coffee-list" hx-swap-oob="innerHTML">` wrapping the list include |
| `app/templates/fragments/equipment_create_success.html` | OOB list update + empty body for form mount | VERIFIED | L10: `<div id="equipment-list" hx-swap-oob="innerHTML">` wrapping the list include |
| `tests/routers/test_equipment_create_fragment.py` | CR-01 regression tests (success + error paths for both entities) | VERIFIED | 4 tests: equipment success, coffee success, equipment invalid, coffee invalid |
| `app/templates/fragments/equipment_row.html` | flex-wrap pills for type + usage (C3) | VERIFIED | L28: `flex flex-wrap gap-2` with two pill spans |
| `tailwind.config.js` | `darkMode: 'selector'` (v3) | VERIFIED | L27: `darkMode: 'selector'` |
| `app/static/css/tailwind.src.css` | `.dark input` + `.dark a` rules (class-scoped, not @media) | VERIFIED | L89: `.dark input, .dark select, .dark textarea`; L111: `.dark a`; no `prefers-color-scheme: dark` blocks |
| `app/static/js/alpine-components/dark-toggle.js` | Alpine.data('darkToggle'), snobbery:theme, setTheme, no eval | VERIFIED | All present; no eval(); no x-model |
| `app/templates/base.html` | No-FOUC nonce'd inline script before CSS link + safe-area-inset-top + dark-toggle.js script | VERIFIED | L26: sync nonce'd script with snobbery:theme; L27: CSS link after; L51: defer+nonce dark-toggle.js; L173: `pt-[env(safe-area-inset-top)]` |
| `app/templates/pages/config_hub.html` | x-data="darkToggle" + setTheme() buttons + /data-tools link | VERIFIED | L69: `x-data="darkToggle"`; L73/79/85: `setTheme('auto')` etc.; L93: `<a href="/data-tools">` |
| `scripts/check_c4_dark.py` | Structural C4+C1 checker | VERIFIED | File exists with 10 checks covering config, CSS, JS, base.html, config_hub |
| `app/templates/pages/home.html` | Guided Brew link -> /recipes | VERIFIED | L21: `<a href="/recipes">Guided Brew</a>` |
| `app/templates/pages/sessions.html` | Guided Brew link -> /recipes; no inline export/import | VERIFIED | L20: `/recipes` link; no `/brew/export` or `/brew/import` in file |
| `app/templates/pages/data_tools.html` | Dedicated /data-tools page with /brew/import form | VERIFIED | Exists; L31: `hx-post="/brew/import"`; CSRF token present |
| `tests/templates/test_recipe_row.py` | C5 with-steps vs no-steps regression test | VERIFIED | 4 parametrized tests covering card+row x with-steps+no-steps |
| `app/routers/brew.py` (data_router) | GET /data-tools with require_user | VERIFIED | L635: `@data_router.get("/data-tools")` with `Depends(require_user)` |
| `app/templates/fragments/brew_prefill_fields.html` | x-init re-sync of dose/water on swap (C7a) | VERIFIED | L49: `x-init="setDose($refs.doseInput ? $refs.doseInput.value : ''); setWater($refs.waterInput ? $refs.waterInput.value : '')"` |
| `app/templates/pages/brew_form.html` | `flex-nowrap` on star row (C7b) | VERIFIED | L118: `class="flex flex-nowrap items-center gap-1 min-h-[56px] py-2"` |
| `app/templates/pages/brew_guided.html` | No role=switch; On/Off text buttons; toggleChime/toggleVibrate preserved (C6) | VERIFIED | role=switch absent; explicit "On"/"Off" text; toggleChime/toggleVibrate calls present |
| `scripts/generate_pwa_icons.py` | hero.jpg SRC; center-crop square before resize | VERIFIED | L31: `SRC = Path("app/static/img/hero.jpg")`; L45-48: center-crop logic |
| `app/static/img/` | 5 PNG icons regenerated | VERIFIED | icon-192.png, icon-512.png, icon-512-maskable.png, apple-touch-icon.png, logo-badge.png all present |
| `app/static/img/hero.jpg` | Square mascot source | VERIFIED | File exists |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Dockerfile stage-1 RUN | `app/static/build_id.txt` | `echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt` | VERIFIED | L63; unconditional — runs every build regardless of changed files |
| Dockerfile stage-2 COPY | runtime image `./app/static/build_id.txt` | `COPY --from=tailwind-builder` | VERIFIED | L109 |
| `pwa.py:_get_build_hash()` | `app/static/build_id.txt` | `Path("app/static/build_id.txt").read_text()[:16]` | VERIFIED | L51-53; fall-through to CSS hash then "dev" |
| `sw.js __BUILD_HASH__ token` | `GET /sw.js CACHE_NAME` | `service_worker()` string substitution at L130 | VERIFIED | `content.replace("__BUILD_HASH__", _BUILD_HASH)` |
| `coffee_form.html create branch` | `#coffee-form-mount` | `form_target = "#coffee-form-mount"` (not #coffee-list) | VERIFIED | CR-01 fix confirmed |
| `create_coffee success` | `#coffee-list` via OOB | `coffee_create_success.html` `hx-swap-oob="innerHTML"` | VERIFIED | Correct two-container pattern |
| `equipment_form.html create branch` | `#equipment-form-mount` | `form_target = "#equipment-form-mount"` | VERIFIED | CR-01 fix confirmed |
| `create_equipment success` | `#equipment-list` via OOB | `equipment_create_success.html` `hx-swap-oob="innerHTML"` | VERIFIED | Correct two-container pattern |
| `base.html no-FOUC script` | `<html>.classList.add('dark')` | `localStorage snobbery:theme`, synchronous, nonce'd, before CSS link | VERIFIED | L26 |
| `config_hub darkToggle buttons` | `dark-toggle.js setTheme()` | `x-data="darkToggle"` + `x-on:click="setTheme(..."` | VERIFIED | L69-90 of config_hub.html |
| `tailwind.config.js darkMode:'selector'` | `.dark` class on `<html>` | Tailwind v3 selector strategy — generates `dark:` utilities keyed to `.dark` | VERIFIED | L27 |
| `base.html mobile top strip` | `env(safe-area-inset-top)` | `pt-[env(safe-area-inset-top)]` arbitrary-value utility | VERIFIED | L173 |
| `home.html Guided Brew` | `/recipes` | `<a href="/recipes">` | VERIFIED | L21 |
| `sessions.html Guided Brew` | `/recipes` | `<a href="/recipes">` | VERIFIED | L20 |
| `config_hub.html account section` | `/data-tools` | `<a href="/data-tools">` | VERIFIED | L93 |
| `data_tools.html import form` | `/brew/import` | `hx-post="/brew/import"` with CSRF token | VERIFIED | L31, L35 |
| `main.py` | `data_router` | `app.include_router(brew_router.data_router)` | VERIFIED | L270 |
| `brew_prefill_fields.html` | `brewRatio` scope on prefill swap | `x-init="setDose(...); setWater(...)"` + `x-ref="doseInput"` / `x-ref="waterInput"` | VERIFIED | L49, L149, L158 |

---

### Data-Flow Trace (Level 4)

Not applicable to this phase. All changes are template restructuring, client-side JS, Dockerfile build config, and route-level HTML responses — no new data sources or DB queries introduced. Existing data flow for list views (coffees, equipment) is unchanged; only the success response shape changed (OOB pattern).

---

### Behavioral Spot-Checks

Step 7b skipped for visual/Alpine/on-device behaviors — correctly routed to human verification. Structural checks suffice for the server-side pieces.

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes exist for this phase. The equivalent is the two-build manual gate (C9, orchestrator-confirmed) and the full pytest suite (965 passed, 2 skipped, 10 xfailed, 0 failed per orchestrator).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| C1 | 13-05 | iOS top-strip safe-area padding | VERIFIED structural / HUMAN on-device | `pt-[env(safe-area-inset-top)]` at base.html:173 |
| C2 | 13-03 | Create form renders full list; CR-01 fixed | VERIFIED | OOB pattern in success templates; regression tests |
| C3 | 13-03 | Equipment cards flex-wrap pills at 375px | VERIFIED | equipment_row.html L28 |
| C4 | 13-05 | 3-state dark toggle, no-FOUC, localStorage | VERIFIED structural / HUMAN visual | tailwind.config.js, dark-toggle.js, base.html, config_hub.html |
| C5 | 13-06 | Guided Brew from Home+Sessions; recipe_row test | VERIFIED | home.html, sessions.html links; test_recipe_row.py |
| C6 | 13-04 | No role=switch cue controls; snobbery:gbm:cues preserved | VERIFIED structural / HUMAN clarity | brew_guided.html |
| C7 | 13-04 | Ratio re-syncs on prefill; stars flex-nowrap | VERIFIED structural / HUMAN visual | brew_prefill_fields.html x-init; brew_form.html flex-nowrap |
| C8 | 13-06 | /data-tools page; require_user; config hub link; routes unchanged | VERIFIED | data_tools.html, brew.py data_router, main.py wiring, test coverage |
| C9 | 13-01 | SW CACHE_NAME bumps per build | VERIFIED + orchestrator-confirmed | Dockerfile build_id.txt write+COPY; pwa.py _get_build_hash(); two-build gate passed |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tailwind.config.js` | 1 | Comment says "Tailwind v4 standalone CLI configuration" but toolchain is v3.4.17 | WARNING (pre-existing, WR-04 from REVIEW.md) | Maintenance confusion risk; stale comment only — no code defect |
| `app/static/css/tailwind.src.css` | 1 | Comment says "Tailwind v4 source" but file uses v3 directives | WARNING (pre-existing, WR-04) | Same as above |
| `Dockerfile` | 9 | Stage-1 comment says "isolates the Tailwind v4 standalone CLI" | WARNING (pre-existing, WR-04) | Same as above |
| `dark-toggle.js` | 32-42 | Auto mode reads matchMedia once at click time; no `addEventListener('change')` for live system-preference tracking | WARNING (WR-03 from REVIEW.md) | In Auto mode, a system preference change while the page is open requires a reload to apply; acceptable for v1 |
| `app/templates/pages/data_tools.html` | 38 | File input has no `required` attribute | INFO (WR-05) | UX: submitting with no file causes a round-trip; server handles gracefully |
| `scripts/generate_pwa_icons.py` | 10,31 | Hardcodes relative path `app/static/img/hero.jpg` without repo-root resolution | INFO (IN-02) | Script must be run from repo root or fails; not a runtime issue |

No `TBD`, `FIXME`, or `XXX` markers found in phase-modified files. No unresolved debt markers. Warnings are carry-overs documented in the REVIEW.md, none are blockers.

---

### Human Verification Required

#### 1. C9 Two-Build Gate (gate confirmation)

**Test:** Run two consecutive `docker compose build coffee-snobbery` (at least 1 second apart or with any change), note the `build_id.txt` value and `snobbery-v` prefix in `/sw.js` after each, confirm they differ.
**Expected:** `BUILD_B != BUILD_A` and `CACHE_NAME_B != CACHE_NAME_A`; `/sw.js` still contains `skipWaiting` and `clients.claim`
**Why human:** `build_id.txt` only exists in a baked image. The orchestrator confirmed this passed during this session with `snobbery-v20260525024520` → `...105505`, but the verification agent cannot re-run a two-build test. This is classified as human-verified (passed).

#### 2. C10 — Icon visual quality

**Test:** Open `app/static/img/logo-badge.png`, `icon-512.png`, `icon-512-maskable.png`. Confirm the full mascot (bean + top-hat + monocle + cup + steam) is inscribed in the circle without squishing or cropping major elements. Confirm `icon-512-maskable.png` has a solid cream-50 background filling the corners.
**Expected:** Undistorted mascot; maskable variant has a cream-50 background square with the mascot centered within the safe zone
**Why human:** Image content is a visual judgment. The generator script is verified to use a 1021x1021 square source (hero.jpg) with correct center-crop logic, but only a human can confirm the resulting image looks correct.

#### 3. C1 — iOS standalone top-strip safe-area (on a real iPhone)

**Test:** Install the PWA on a real iPhone in standalone mode. Observe whether the mobile top strip (Snobbery logo + search button) appears below the status bar with no overlap.
**Expected:** The status bar (time, carrier, battery) is fully visible above the Snobbery header strip with no overlap.
**Why human:** `env(safe-area-inset-top)` reports 0 in Playwright and desktop Chrome. The structural fix (`pt-[env(safe-area-inset-top)]`) mirrors the UNVERIFIED bottom-nav technique (commit 982c0e6, memory `safe-area-fix-unverified`). If the fix fails on-device, both the top and bottom safe-area techniques need revision.

#### 4. C4 — Dark toggle visual behavior and no-FOUC

**Test:** At 375px viewport, click Auto → Dark → Light → Auto and confirm the theme switches instantly with no visible flash. Reload the page in Dark mode and confirm it starts dark with no white flash. On a macOS/iOS device set to system dark mode, select Light in the toggle and confirm the page shows the light theme.
**Expected:** Instant theme switch, no FOUC on reload, Light wins over system-dark preference.
**Why human:** Alpine reactivity, localStorage read timing, and matchMedia override cannot be verified programmatically.

#### 5. C4 — Login/setup always-dark (D-02)

**Test:** Set snobbery:theme = 'light' in localStorage, then navigate to /login. Confirm the login page renders in dark espresso colors, not the light cream theme.
**Expected:** /login is always dark regardless of the toggle state.
**Why human:** Login/setup templates are separate from the authenticated base.html toggle; requires browser inspection.

#### 6. C6 — Cue control clarity at 375px

**Test:** Navigate to /brew/guided on a 375px viewport. On the start screen, confirm the "Audio & haptic cues" section shows two rows with explicit "On" and "Off" text buttons (not toggle pills or emoji). Start a brew and confirm the timer screen shows "Chime: On/Off" and "Vibrate: On/Off" labeled buttons.
**Expected:** Controls read unambiguously as on/off without needing a role=switch mental model.
**Why human:** UX clarity is subjective; the structural absence of role=switch is verified, the label text is verified, but whether it reads clearly requires a human.

#### 7. C7 — Ratio recalculates on prefill; stars single-line

**Test:** On /brew/new, select a coffee that has a previous session with known dose/water values. Confirm the ratio readout updates immediately to reflect the prefilled values without the user typing. Also confirm at 375px that all 5 star zones appear on a single line without wrapping.
**Expected:** Ratio shows correct 1:N.NN immediately after prefill swap; all 5 stars on one row.
**Why human:** The x-init re-sync fires at Alpine hydration after HTMX swap — this is runtime behavior that requires the app running with Alpine reactive.

#### 8. C5 + C8 — Navigation flow

**Test:** On the home page (375px), confirm the "Guided Brew" button is visible and tapping it routes to /recipes. On /brew (sessions), confirm the same. On /config, confirm "Export / Import sessions" link is present and routes to /data-tools with the Export CSV and Import sections visible.
**Expected:** All three navigation paths work as described; /brew no longer shows inline export/import controls.
**Why human:** Navigation placement and link visibility require walking through the actual app.

---

### Gaps Summary

No structural gaps. All 9 success criteria are fully implemented in the codebase:

- **C9** (SW cache key per build): Dockerfile writes `build_id.txt` unconditionally; `pwa.py` reads it first; test suite verifies the structural shape; orchestrator confirmed the runtime two-build behavior.
- **C2** (create form list rendering + CR-01 fix): The REVIEW.md CR-01 bug was fixed this session. Both forms now target the form-mount; success uses OOB to update the list; 4 regression tests cover success and error paths.
- **C3** (equipment card pills): `flex flex-wrap` with pill spans at `equipment_row.html:28`.
- **C4** (dark toggle): Complete implementation: config, CSS, JS component, no-FOUC head script, toggle UI in config hub.
- **C5** (Guided Brew reachability + recipe_row tests): Links present in both home.html and sessions.html; 4-test parametrized suite.
- **C6** (cue controls): role=switch removed; labeled On/Off buttons in both start and timer screens.
- **C7** (ratio re-sync + flex-nowrap stars): x-init re-sync in brew_prefill_fields.html; flex-nowrap on star row.
- **C8** (Export/Import moved): /data-tools route with require_user; wired in main.py; tested; sessions view cleaned.
- **C1** (safe-area-top): `pt-[env(safe-area-inset-top)]` on the mobile top strip; verification awaits on-device test.

All 8 human-verification items are visual/behavioral/on-device confirmations that are genuinely non-automatable. The phase structural contract is fully met. Status is `human_needed` because human items exist; there are no gaps blocking goal achievement.

---

_Verified: 2026-05-25_
_Verifier: Claude (gsd-verifier)_
