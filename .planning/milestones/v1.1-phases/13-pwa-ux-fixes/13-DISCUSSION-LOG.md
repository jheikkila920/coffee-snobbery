# Phase 13: PWA UX Fixes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-24
**Phase:** 13-pwa-ux-fixes
**Areas discussed:** Dark-mode toggle (C4), Guided Brew reach (C5), New-card render (C2), Export/Import page (C8), Logo + PWA icon (C10, added)

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Dark-mode toggle (C4) | 2-state vs 3-state; login interaction | ✓ |
| Guided Brew reach (C5) | How to reach GBM from Home/Log without a pre-selected recipe | ✓ |
| New-card render (C2) | Card placement + form behavior after create | ✓ |
| Export/Import page (C8) | Route/name + config-hub link location | ✓ |

**User's choice:** All four. C1/C3/C6/C7/C9 left to Claude's discretion with stated defaults.

---

## Dark mode (C4) — state model

| Option | Description | Selected |
|--------|-------------|----------|
| 3-state: Auto/Light/Dark | Auto = follow system (today) and default; Light/Dark explicit overrides | ✓ |
| 2-state: Light/Dark | Simpler but drops follow-system; forces a fixed default | |

**User's choice:** 3-state, Auto default.
**Notes:** Preserves the current adaptive behavior for existing users; toggle is an override.

## Dark mode (C4) — login interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Login stays always-dark | /login + /setup ignore the toggle (preserve D-14 brand moment) | ✓ |
| Login respects the toggle | Light-mode users get a light login; abandons D-14 | |

**User's choice:** Login stays always-dark. Toggle affects authenticated pages only.

## New-card render (C2) — placement

| Option | Description | Selected |
|--------|-------------|----------|
| Re-render the list region | Full list fragment into the list container; correct sort + empty-state | ✓ |
| Prepend single card to top | Snappier but can break sort and needs explicit empty-state handling | |

**User's choice:** Re-render the list region.
**Notes:** Fixes the `mode="row"` `<tr>`-in-a-div bug at the same time.

## New-card render (C2) — form behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Clear and stay open | Reset in place (extends include_oob_form_clear) for rapid entry | |
| Collapse/close the form | Tidier resting state, one extra tap for the next item | ✓ |

**User's choice:** Collapse/close the form.

## Guided Brew reach (C5)

| Option | Description | Selected |
|--------|-------------|----------|
| Link to recipe list | Action on Home/Log → /recipes; reuses the fixed per-recipe control | ✓ |
| Recipe-picker sheet | Full-screen sheet of steps-bearing recipes; new UI to build | |
| Launch with last recipe | Jump into GBM with most-recent recipe; least predictable | |

**User's choice:** Link to recipe list.
**Notes:** Simplest, no new picker UI; pairs with the mandated recipe_row.html regression test.

## Export/Import page (C8)

| Option | Description | Selected |
|--------|-------------|----------|
| /brew/data card in catalog grid | "Import & Export" card alongside catalog entities | |
| Link in account section | Near "Signed in as"/Sign out at the bottom of config_hub | ✓ |
| Separate config section | A distinct "Data" section below the catalog grid | |

**User's choice:** Link in the account section. Routes unchanged; only entry-point moves.

## Logo + PWA icon (C10, added during discussion)

| Option | Description | Selected |
|--------|-------------|----------|
| Tight crop on the bean | Zoom on hatted bean+monocle; drops cup/steam; reads at 32px | |
| Full mascot in circle | Largest inscribed circle of the full square; keeps whole scene | ✓ |

**User's request (free text):** "the circle logo on the top nav bar and used for the PWA app
is very skewed. I loaded a new hero.jpg file, can you edit it to be circular without skewing
and adjust it to be used for the PWA app icon and top nav bar."
**Root cause (investigated):** `scripts/generate_pwa_icons.py` points at `snobbery-login.jpg`
(2816×1536 landscape) and resizes to a square with no aspect preservation → skew baked into
the PNGs. New `hero.jpg` is 1021² square. Nav `<img>` CSS is already correct.
**User's choice:** Full mascot inscribed in the circle (keep cup/steam/chain).

---

## Claude's Discretion

- **C1** safe-area-inset-top on mobile top strip + sticky top chrome (mirror the bottom fix;
  technique unverified on-device).
- **C3** equipment cards → flex-wrap pills like coffee cards at 375px.
- **C6** redesign guided-brew cue controls (replace `role="switch"`), keep localStorage prefs.
- **C7** ratio auto-recalc on programmatic prefill (Alpine effect/watcher) + single-line
  rating stars at 375px.
- **C9** SW cache name/version bumps per deploy (root-cause the build-hash mechanism).

## Deferred Ideas

- `hero-alt.jpg` (1149²) — unused alternate; not the chosen source.
- `brew_time_seconds` in analytics — future enhancement.
- Per-user settings/preferences page — none in v1; dark-mode pref lives in localStorage.
- On-device verification of the safe-area technique (C1 + existing `982c0e6`).
