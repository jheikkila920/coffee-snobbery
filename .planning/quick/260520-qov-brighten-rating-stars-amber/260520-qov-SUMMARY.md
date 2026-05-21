---
quick_id: 260520-qov
slug: brighten-rating-stars-amber
status: complete
date: 2026-05-21
commit: 5c96ec8
---

# Quick Task 260520-qov: Brighten brew-rating stars to amber

**What:** Changed the brew-rating star glyph color from dark `text-espresso-700` to `text-amber-400` across all rating displays, matching the existing rating-star color already used in `app/templates/pages/brew_form.html`.

**Why:** User feedback — the recent-brews star read as dark/dull and should be a brighter yellow. The same dark star was used app-wide, so all instances were updated for consistency (leaving them inconsistent would look like a bug).

**Files changed (10 occurrences, 6 templates):**
- `app/templates/fragments/home/recent_brews.html` (1)
- `app/templates/fragments/home/top_coffees.html` (1)
- `app/templates/fragments/home/preference_profile.html` (4)
- `app/templates/fragments/home/roast_freshness.html` (1)
- `app/templates/fragments/home/sweet_spots.html` (1)
- `app/templates/fragments/session_row.html` (2 — Phase 5 sessions list, included for app-wide consistency)

**Scope safety:** Only star spans matching `class="text-espresso-700" aria-hidden="true">★` were changed; other `text-espresso-700` uses (link colors, badges) untouched. Color-only — no behavior, auth, or CSP change. `text-amber-400` was already in the compiled Tailwind CSS (no Tailwind safelist change needed).

**Verification:** Source = 0 dark star spans / 10 amber. Image rebuilt + restarted; container healthy; container templates confirmed 10 amber / 0 dark.

**Execution note:** Run inline (not via worktree-isolated planner+executor) — a 10-occurrence exact-string CSS-class swap; inline kept GSD guarantees (atomic commit `5c96ec8`, STATE tracking) without the worktree/Docker overhead.

**Commit:** `5c96ec8` — `style: brighten brew-rating stars to amber-400`
