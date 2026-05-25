---
phase: 13-pwa-ux-fixes
plan: "02"
subsystem: pwa-icons
tags: [pwa, icons, branding, c10, d-07]
dependency_graph:
  requires: []
  provides: [regenerated-pwa-icons, hardened-icon-generator]
  affects: [app/static/img/logo-badge.png, app/manifest.json]
tech_stack:
  added: []
  patterns: [center-crop-before-resize, pillow-image-processing]
key_files:
  created: []
  modified:
    - scripts/generate_pwa_icons.py
    - app/static/img/icon-192.png
    - app/static/img/icon-512.png
    - app/static/img/icon-512-maskable.png
    - app/static/img/apple-touch-icon.png
    - app/static/img/logo-badge.png
decisions:
  - "SRC changed to hero.jpg (1021x1021 square) — avoids landscape-squish bug that caused C10 distortion"
  - "circular_crop hardened to center-crop-to-square BEFORE resize — defensive for any future source swap"
  - "snobbery-login-hero.jpg generation block removed — D-07 brand lock; login hero is a separate managed asset"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-25"
  tasks_completed: 2
  tasks_total: 3
  files_modified: 6
---

# Phase 13 Plan 02: PWA Icon Regeneration (C10) Summary

**One-liner:** Regenerated all 5 PWA icons from the correct square mascot source (hero.jpg, 1021x1021) after hardening `circular_crop()` to center-crop before resize, eliminating the landscape-squish bug.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Harden circular_crop + repoint SRC to hero.jpg | 9e8eb48 | scripts/generate_pwa_icons.py |
| 2 | Regenerate + commit 5 icon PNGs; delete hero-alt.jpg | ec4e2ae | 5 PNGs in app/static/img/ |

## Task 3: Deferred to Orchestrator Batch Verification

Task 3 is `type="checkpoint:human-verify"` — deferred to the orchestrator's consolidated visual verify pass at the end of Phase 13. Visual judgment required: confirm full mascot (bean + top-hat + monocle + cup + steam) is inscribed in the circle, undistorted, with maskable padding intact.

## What Changed

**`scripts/generate_pwa_icons.py`:**
- `SRC` changed from `snobbery-login.jpg` (2816x1536 landscape, the bug) to `hero.jpg` (1021x1021 square)
- `circular_crop()` hardened: step 1 is now center-crop to min-dimension square before any resize; then resize, then mask
- `snobbery-login-hero.jpg` generation block removed (D-07 brand lock)
- Module docstring updated to reflect 5 outputs, new source, and D-07 note

**Regenerated icons (all from hero.jpg, full mascot, no distortion):**
- `app/static/img/icon-192.png` — 192x192
- `app/static/img/icon-512.png` — 512x512
- `app/static/img/icon-512-maskable.png` — 512x512, cream-50 background with 10% safe-zone padding
- `app/static/img/apple-touch-icon.png` — 180x180
- `app/static/img/logo-badge.png` — 64x64 (renders at 32px retina)

**`app/static/img/hero-alt.jpg`:** Deleted (was never tracked in git; D-07 cleanup — hero.jpg is the canonical source).

**`app/static/img/snobbery-login-hero.jpg`:** Untouched (D-07 brand lock confirmed via `git diff`).

## Deviations from Plan

None — plan executed exactly as written.

hero-alt.jpg was listed as a file to delete but was never committed to git (it was untracked). The deletion is complete on disk; no `git rm` was needed.

## Verification Results

```
app/static/img/icon-192.png (192, 192) ✓
app/static/img/icon-512.png (512, 512) ✓
app/static/img/icon-512-maskable.png (512, 512) ✓
app/static/img/apple-touch-icon.png (180, 180) ✓
app/static/img/logo-badge.png (64, 64) ✓
hero-alt.jpg deleted ✓
snobbery-login-hero.jpg unmodified ✓
```

Script AST parse + SRC/crop assertions: OK.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes. Icon assets are non-sensitive; manifest icon filenames verified to match `app/routers/pwa.py` manifest() output.

## Self-Check: PASSED

- `scripts/generate_pwa_icons.py` — exists and modified (9e8eb48)
- `app/static/img/icon-192.png` — exists, 192x192
- `app/static/img/icon-512.png` — exists, 512x512
- `app/static/img/icon-512-maskable.png` — exists, 512x512
- `app/static/img/apple-touch-icon.png` — exists, 180x180
- `app/static/img/logo-badge.png` — exists, 64x64
- Commits 9e8eb48, ec4e2ae — verified in git log
