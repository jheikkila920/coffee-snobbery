---
phase: 13-pwa-ux-fixes
plan: "05"
subsystem: frontend/pwa
tags: [dark-mode, tailwind-v3, alpine-csp, pwa, safe-area, fouc]
dependency_graph:
  requires: []
  provides: [C4-dark-mode-toggle, C1-top-safe-area]
  affects: [base.html, config_hub.html, tailwind.config.js]
tech_stack:
  added: []
  patterns:
    - Tailwind v3 darkMode:'selector' strategy (.dark class on <html>)
    - localStorage snobbery:theme key for theme persistence
    - Synchronous nonce'd IIFE in <head> for no-FOUC dark mode
    - Alpine CSP component via Alpine.data('darkToggle') registration
    - env(safe-area-inset-top) arbitrary-value utility for iOS standalone
key_files:
  created:
    - app/static/js/alpine-components/dark-toggle.js
    - scripts/check_c4_dark.py
  modified:
    - tailwind.config.js
    - app/static/css/tailwind.src.css
    - app/templates/base.html
    - app/templates/pages/config_hub.html
decisions:
  - "darkMode:'selector' chosen over 'class' — both work in v3.4.17; 'selector' is the canonical v3.4.1+ value (RESEARCH Open Question 3 resolved)"
  - "No-FOUC script uses localStorage.getItem('snobbery:theme') with matchMedia fallback for Auto — minimal synchronous logic, eval-free"
  - "C1 safe-area delivered via pt-[env(safe-area-inset-top)] arbitrary-value utility on elements, not a separate CSS rule — satisfies MX-1 (all CSS in tailwind.src.css, no custom.css)"
  - "Dark toggle placed after Sign out form in config_hub.html md:hidden block — mobile-only, mirrors desktop account dropdown placement"
  - "Scripts structural checker strips Jinja comments before position-based assertions to avoid false failures from comments that mention forbidden patterns"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-25"
  tasks: 3
  files: 6
---

# Phase 13 Plan 05: C4 Dark-Mode Toggle + C1 iOS Safe-Area Top Summary

Implemented a 3-state Auto/Light/Dark theme toggle (C4, D-01/D-02) and iOS standalone top safe-area padding (C1) with a strict Tailwind v3 + CSP-nonce architecture. No FOUC, no @custom-variant (v4-only), no custom.css.

## What Was Built

**C4 — Manual dark-mode toggle:**
- `tailwind.config.js`: Changed `darkMode: 'media'` to `darkMode: 'selector'` — Tailwind v3.4.1+ canonical value. All `dark:` utilities now key off a `.dark` class on `<html>`, not system preference alone.
- `tailwind.src.css`: Rewrote both `@media (prefers-color-scheme: dark)` blocks (form controls at lines 88-97, anchor colors at lines 111-116) to `.dark` class-scoped selectors (`.dark input`, `.dark a`). An explicit Light choice on a dark-system device now wins.
- `dark-toggle.js`: New Alpine CSP component registered via `Alpine.data('darkToggle')`. 3-state `setTheme(auto|light|dark)`: Auto removes localStorage key and checks matchMedia, Light/Dark write to `snobbery:theme` and manipulate `document.documentElement.classList.toggle('dark')`. No eval, no x-model.
- `base.html`: Added synchronous nonce'd IIFE before the Tailwind `<link>` tag — reads `snobbery:theme` from localStorage, falls back to matchMedia for Auto, sets `.dark` on `<html>` before first paint (no FOUC). Added `defer+nonce` script tag for `dark-toggle.js` before `@alpinejs/csp` core.
- `config_hub.html`: Added `x-data="darkToggle"` block with Auto/Light/Dark buttons after the Sign out form in the `md:hidden` account section. Each button: `x-on:click="setTheme(...)"`, `:class` driven by `isActive(...)`, `min-h-[44px]`.

**C1 — iOS top safe-area:**
- `base.html` mobile top strip: Changed `h-14` to `min-h-14`, added `pt-[env(safe-area-inset-top)]` arbitrary-value utility directly on the element.
- `base.html` full-screen mobile search sheet: Added `pt-[env(safe-area-inset-top)]` on the `fixed inset-0 z-50` container so the search header clears the status bar in standalone mode.
- No separate `.top-safe-area` CSS rule added; Tailwind v3 compiles arbitrary values directly into the output CSS.

**Structural checker:**
- `scripts/check_c4_dark.py`: Standalone Python script (no app imports, no third-party deps, no eval, no x-model). Default mode checks tailwind.config.js + tailwind.src.css + dark-toggle.js. `--templates` mode also checks base.html and config_hub.html. Strips Jinja `{# #}` comments before position-based assertions to avoid false failures.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `python scripts/check_c4_dark.py` — 10/10 checks passed (default mode)
- `python scripts/check_c4_dark.py --templates` — 8/8 additional template checks passed
- `python -m pytest tests/ci/` — 349 passed (no regressions from new no-FOUC script or dark-toggle.js addition; all CSP nonce + no-unsafe-jinja guards green)
- No `.top-safe-area` rule in tailwind.src.css (C1 uses arbitrary-value utility only)
- No `custom.css` created (MX-1 satisfied)

## Known Stubs

None. C1 safe-area-inset-top is implemented but flagged as **UNVERIFIED on-device** — the technique is correct per CSS spec but `env(safe-area-inset-top)` evaluates to 0 in all desktop/Playwright environments. On-device verification is required for C1 (and C1's bottom-nav analog from commit 982c0e6). This is documented as intentional in the plan (RESEARCH Pattern 6, Pitfall 6) and is the subject of the Task 4 manual checkpoint.

## Threat Surface Scan

No new network endpoints or auth paths introduced. Two threat mitigations from the plan's threat register applied:

- **T-13-11 mitigated**: No-FOUC script carries `nonce="{{ csp_nonce(request) }}"`, is eval-free (IIFE, no new Function), reads only localStorage + matchMedia. CI CSP grep guard confirms no violation.
- **T-13-12 mitigated**: `dark-toggle.js` uses Alpine CSP build, string x-data, named methods only, no eval, no x-model; served from 'self' with nonce.

## Checkpoint Deferred

**Task 4** (`type="checkpoint:human-verify"`) is deferred to the orchestrator's consolidated batch verification pass per the sequential executor protocol. The checkpoint covers:
- C4: dark toggle switches theme instantly with no FOUC; Auto/Light/Dark persist; Light override wins on dark-system
- D-02: login + setup stay always-dark regardless of toggle
- C1: iOS standalone top strip clear of status bar (on-device required)

## Self-Check

Commits exist:
- `3749c7e` — feat(13-05): C4 dark-mode selector strategy + class-scoped CSS + darkToggle component
- `12fd1d9` — feat(13-05): C4 no-FOUC head script + dark toggle UI; C1 top safe-area padding

Files created/modified:
- `tailwind.config.js` — darkMode: 'selector' confirmed
- `app/static/css/tailwind.src.css` — .dark rules confirmed, no @media dark blocks remain
- `app/static/js/alpine-components/dark-toggle.js` — created
- `scripts/check_c4_dark.py` — created, passes in both modes
- `app/templates/base.html` — no-FOUC script, dark-toggle.js tag, safe-area-inset-top
- `app/templates/pages/config_hub.html` — darkToggle UI block

## Self-Check: PASSED
