---
slug: bottom-nav-floats-ios-pwa
status: resolved
trigger: |
  PWA app on iOS raises the bottom nav bar from the bottom of the screen on all pages but home and admin pages.
created: 2026-05-24
updated: 2026-05-24
---

# Debug: Bottom nav floats up (gap below) on iOS PWA — all pages except home/admin

## Symptoms

- **Expected:** Bottom nav flush to the screen's bottom edge, with safe-area padding *inside* the nav so icons sit above the home indicator.
- **Actual:** A gap of roughly the home-indicator height appears BELOW the nav (between the nav and the true bottom edge).
- **When:** Immediately on page load. NOT scroll-related. (Rules out the iOS Safari address-bar-collapse-on-scroll theory.)
- **Scope by page:** Wrong on coffees / equipment / recipes / sessions(log). Correct (flush) on home and admin.
- **Environment:** Installed iOS standalone PWA. Browser-tab behavior not yet tested.
- **Errors:** None (no console inspection yet).

## Constraints / important

- This bug ONLY manifests where `env(safe-area-inset-bottom)` is nonzero — real iOS standalone PWA on a home-indicator device. Desktop Chromium and Playwright report `0`, so it CANNOT be reproduced locally. Reason from templates/CSS + iOS standalone behavior. Do NOT attempt Playwright reproduction.
- Do not weaken CSP / CSRF / security-header invariants.
- Project: templates are baked into the image (no bind-mount); a fix must be deployed via rebuild. CSS lives in `app/static/css/tailwind.src.css` (compiled to a baked stylesheet).

## Evidence (codebase, pre-gathered)

- Bottom nav is a SINGLE shared element: `app/templates/base.html:237` — `class="fixed bottom-0 left-0 right-0 z-40 h-16 pb-[env(safe-area-inset-bottom)] ... md:hidden"`, `x-data="navBar"`.
- Main content wrapper: `app/templates/base.html` ~284-287 — `<div class="pb-16 md:pb-0">`.
- `safe-area-inset` appears ONLY at: `base.html:237` (nav), `app/static/css/tailwind.src.css:22` (`.nav-safe-area { padding-bottom: env(safe-area-inset-bottom); }` — reportedly defined but unused on the nav), `app/templates/pages/brew_form.html:302` (sticky action bar).
- NO `transform`/`filter`/`backdrop`/`will-change`/`contain` in `app/static/css` that would create a containing block lifting the fixed nav.
- Template inheritance: home → base.html (direct); admin → admin_base.html → base.html; buggy catalog pages → base.html (direct). So the "extends path" alone does not explain home-vs-catalog difference.

## Eliminated

- hypothesis: iOS Safari address-bar collapse during scroll shifts the fixed nav.
  reason: User reports the gap is present IMMEDIATELY on load, before any scrolling. Static layout issue, not a scroll/viewport-transition effect.

- hypothesis: A containing block (transform/filter/contain/will-change/backdrop-filter) on a catalog-only ancestor lifts the fixed nav.
  reason: Exhaustive grep + read of all catalog page templates, fragments, Alpine components, and compiled CSS src found NO such property on any catalog-only ancestor. Template structure is identical between home/admin (working) and catalog (broken) at the content-block level. The `backdrop-blur` in brew_form.html is not on a nav ancestor, and the `transform` in brew_guided.html similarly cannot affect a fixed sibling. No Alpine component applies transforms that would survive a stacking-context check.

## Root Cause

On iOS standalone PWA, the layout viewport bottom boundary resolves to the **safe-area bottom** (above the home indicator), not the physical screen bottom — even with `viewport-fit=cover` set. As a result, `position:fixed; bottom:0` anchors the nav at the safe-area boundary, leaving a gap of `env(safe-area-inset-bottom)` (~34px on modern iPhones) between the nav's bottom edge and the physical screen bottom.

This gap is universally present on ALL pages, but is **visually masked** on home and admin pages because their last content sections use `bg-cream-100` (#F4EFE6), which matches the nav's background colour. On catalog pages (coffees, equipment, recipes, sessions), the content uses plain tables/cards on the `bg-cream-50` (#FAF7F2) body background, making the cream-50 gap conspicuous against the cream-100 nav.

There is NO page-specific CSS or structural difference causing the nav to behave differently — the gap is identical on all pages; the difference is purely visual masking.

## Fix Applied

**Files modified:**

1. `app/static/css/tailwind.src.css` — Added `.nav-safe-area-extend::after` rule that extends the nav's background colour into the safe-area gap below the nav via an absolutely-positioned pseudo-element. The pseudo-element has `height: env(safe-area-inset-bottom)` and `background-color: inherit`, so it fills the gap on iOS (34px) and is zero-height everywhere else. `background-color: inherit` handles dark mode automatically.

2. `app/templates/base.html` — Added `nav-safe-area-extend` class to the bottom nav `<nav>` element (line 240).

No Python code was touched; ruff is not required.

## On-Device Verification Required

Since this bug only manifests on real iOS hardware (env(safe-area-inset-bottom) > 0), **John must verify** the fix after deploying:

1. `git pull && docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`
2. On the installed iOS PWA, do **Clear site data** (Safari → Settings → Clear History and Website Data or the app's site settings) to bypass the service worker's stale cache.
3. Navigate to `/coffees`, `/equipment`, `/recipes`, `/brew`.
4. **Confirm:** bottom nav is flush to the screen bottom edge on all four pages, with no gap between the nav and the home indicator area.
5. Also confirm home and admin still look the same (flush).
6. Confirm dark mode: nav background matches the fill colour below it in dark mode too.

## Resolution

- **Root cause:** iOS standalone PWA layout viewport excludes bottom safe area; `bottom:0` anchors to safe-area boundary, not physical screen edge. Gap masked on home/admin by matching content backgrounds; exposed on catalog pages with plain body background.
- **Fix:** CSS `::after` pseudo-element on the nav extends the nav background colour into the ~34px gap below. Zero-height on non-iOS or pre-notch devices.
- **Files:** `app/static/css/tailwind.src.css`, `app/templates/base.html`
- **Rebuild required:** yes (templates and CSS are baked into the Docker image)
