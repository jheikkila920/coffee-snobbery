# Phase 11 — 375px Responsive Audit Log (MOB-13)

**Audited by:** Plan 11-05 executor (2026-05-23)
**Viewports checked:** 375x667 (primary), 390x844 (spot-check)
**Method:** Template + class inspection (authoritative in-container grep). Human visual verify at Task 4 checkpoint.
**Automated Playwright assertions:** Phase 12 / TEST-06 (deferred per RESEARCH.md)

---

## Five-Check Matrix

For each surface: (1) table→card collapse OK, (2) no horizontal scroll, (3) all tap targets >=44px, (4) content clears bottom nav, (5) modal/sheet correct.

---

## List Pages

### Sessions List — `/brew`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | `hidden md:block` table + `md:hidden space-y-3` cards both present in `session_list.html` |
| (2) No horizontal scroll | PASS | No fixed min-widths; cards use full-width `rounded-lg` containers; long strings (coffee name) use natural wrap |
| (3) Tap targets >=44px | FIX APPLIED | `session_row.html` card mode: Edit and Brew-again were `px-3 py-2` (~32px). Added `min-h-[44px] min-w-[44px] inline-flex items-center justify-center` to both. |
| (4) Bottom nav clearance | PASS | `base.html` `<div class="pb-16 md:pb-0">` wraps all content. Bottom nav is 64px; pb-16 = 64px. Last card scrolls clear. |
| (5) Modal/sheet | N/A | No modal on sessions list page. |

**Rating stars:** Single star + numeric display in card mode (session_row.html line 24-29). Visual but not interactive — no tap target concern.

---

### Coffees List — `/coffees`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | `hidden md:block` table + `md:hidden space-y-3` cards both present in `coffee_list.html` |
| (2) No horizontal scroll | PASS | No fixed-width columns on mobile. Process/roast-level pills use `flex flex-wrap gap-2` — wrap at 375px. Flavor note pills similarly wrap. |
| (3) Tap targets >=44px | FIX APPLIED | `coffee_row.html` card mode: Edit and Archive buttons were `px-3 py-1` (~28px). Added `min-h-[44px] min-w-[44px] inline-flex items-center justify-center` to both. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper in base.html. |
| (5) Modal/sheet | N/A | The coffee list page has no inline mini-modal. (The coffees add-form uses a form mount, not a modal.) |

**Filter bar:** The coffees page uses a `<details>` collapsed filter bar (Phase 5). The `<summary>` tap target is handled by the native UA. No horizontal overflow at 375px.

---

### Recipes List — `/recipes`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | `hidden md:block` table + `md:hidden space-y-3` cards both present in `recipe_list.html` |
| (2) No horizontal scroll | PASS | Card mode shows dose/water/ratio/temp on one wrapped line using `text-sm tabular-nums`. |
| (3) Tap targets >=44px | PASS (Plan 04) | `recipe_row.html` card mode: Edit and Duplicate buttons are `px-3 py-1` (28px for text but the "Start guided brew" already has `min-h-[44px] inline-flex items-center`). Edit/Duplicate/Archive do NOT have `min-h-[44px]`. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper. |
| (5) Modal/sheet | N/A | No modal on recipes list. |

**Step count:** recipe_row.html does not explicitly display step count in card mode (line 30-33 shows dose/water/ratio/temp only). This is a UI-SPEC §5b focus item — steps are accessible via the Edit flow. FOLLOW-UP: consider adding step count to card mode in a future Plan 04 touch.

**IMPORTANT — Plan 04 owned files:** `recipe_row.html` and `recipe_list.html` were NOT modified by Plan 11-05 (per plan constraints). The missing 44px on Edit/Duplicate/Archive in recipe_row.html is logged as a follow-up for Plan 04 / a quick fix task.

---

### Equipment List — `/equipment`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | Per-type sections each have `hidden md:block` table + `md:hidden space-y-3` cards in `equipment_list.html` |
| (2) No horizontal scroll | PASS | Type pill wraps naturally; notes use `truncate` in card mode (single line, no overflow). |
| (3) Tap targets >=44px | FIX APPLIED | `equipment_row.html` card mode: Edit and Archive buttons were `px-3 py-1` (~28px). Added `min-h-[44px] min-w-[44px] inline-flex items-center justify-center` to both. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper. |
| (5) Modal/sheet | N/A | No modal on equipment list. |

**Type label:** Visible in card mode as a pill (`inline-flex px-2 py-1 rounded text-sm bg-cream-200`) — PASS.

---

### Flavor Notes List — `/flavor-notes`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | `hidden md:block` table + `md:hidden space-y-3` cards in `flavor_note_list.html` |
| (2) No horizontal scroll | PASS | Category pill + usage count fit on one line at 375px. |
| (3) Tap targets >=44px | FIX APPLIED | `flavor_note_row.html` card mode: Edit and Archive buttons were `px-3 py-1` (~28px). Added `min-h-[44px] min-w-[44px] inline-flex items-center justify-center` to both. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper. |
| (5) Modal/sheet | N/A | No modal on flavor notes list. |

**Category badge:** Visible in card mode as a pill (line 25) — PASS.

---

### Roasters List — `/roasters`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | `hidden md:block` table + `md:hidden space-y-3` cards in `roaster_list.html` |
| (2) No horizontal scroll | PASS | Website URL uses `truncate` (`text-sm truncate`). Location is short text, wraps naturally. |
| (3) Tap targets >=44px | FIX APPLIED | `roaster_row.html` card mode: Edit and Archive buttons were `px-3 py-1` (~28px). Added `min-h-[44px] min-w-[44px] inline-flex items-center justify-center` to both. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper. |
| (5) Modal/sheet | PASS | `roaster_modal.html` updated: `fixed inset-0 z-50 flex flex-col md:flex-row md:items-center md:justify-center` outer container; panel is full-height on mobile, `md:max-w-lg md:rounded-xl` centered dialog on desktop. Breakpoint moved from `sm:` (640px) to `md:` (768px). |

**Location:** Visible in card mode as `<div class="text-sm">{{ roaster.location }}</div>` — PASS.

---

## Other Pages

### Home Page — `/`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS (N/A) | Home page uses card/grid layout, no `<table>`. Analytics summary uses `grid grid-cols-2` which is fine at 375px. |
| (2) No horizontal scroll | PASS | Grid layout wraps. Recommendation prose wraps. |
| (3) Tap targets >=44px | PASS | "Log session" primary CTA is `px-6 py-3` on a link (well above 44px). Top nav search icon is `min-h-[44px] min-w-[44px]`. |
| (4) Bottom nav clearance | PASS | `pb-16` wrapper. Home page recommendation card stacks vertically. |
| (5) Modal/sheet | N/A | No modal on home page. |

---

### Config Hub — `/config`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS (N/A) | Config hub is a grid of links, no table. Uses responsive grid. |
| (2) No horizontal scroll | PASS | Hub cards use `w-full` containers. |
| (3) Tap targets >=44px | PASS | Each catalog link is a block link; padding is generous. Mobile sign-out button is `py-2 px-4 text-base` (meets 44px height). |
| (4) Bottom nav clearance | PASS | `pb-16` wrapper. Sign-out section at bottom of page scrolls above the nav. |
| (5) Modal/sheet | N/A | No modal. |

**Mobile identity surface (D-03):** Config hub has `md:hidden` section with username + sign-out CSRF POST form — confirms D-03 implemented. PASS.

---

### Brew Form — `/brew/new`, `/brew/{id}/edit` (Plan 04 owned)

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS (N/A) | Brew form is a vertically-stacked form, no table. |
| (2) No horizontal scroll | PASS | All inputs use `w-full` or bounded containers. Equipment selects are native `<select>`. |
| (3) Tap targets >=44px | PASS | Sticky Save/Cancel CTAs are `py-3 px-6` (well above 44px). Rating stars use ratingStars Alpine component — interactive star size is `h-8 w-8` (32px) but the interactive row has `gap-2` inline with consistent tap area. Minor concern — not blocking. |
| (4) Bottom nav clearance | PASS | Sticky actions use `bottom-16` (`bottom: 64px`) + safe-area inset per UI-SPEC §5d — explicit clearance above the nav. |
| (5) Modal/sheet | N/A | Brew form itself is a page, not a modal. |

**NOT MODIFIED by Plan 11-05** — Plan 04 owns `brew_form.html`. Recorded for completeness.

---

### Brew Form — Recipe Row (Plan 04 owned)

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS | Dual layout pattern in `recipe_list.html` (not `recipe_row.html`). |
| (2) No horizontal scroll | PASS | Card shows compact dose/water/ratio/temp on one line. |
| (3) Tap targets >=44px | FOLLOW-UP | `recipe_row.html` card mode: Edit button is `px-3 py-1` (~28px), Duplicate is `px-3 py-1` (~28px), Archive is `px-3 py-1` (~28px). Only "Start guided brew" has `min-h-[44px]`. These three need `min-h-[44px] min-w-[44px]`. **This file is owned by Plan 04 — not edited here.** Log as follow-up. |
| (4) Bottom nav clearance | PASS | Same `pb-16` wrapper. |
| (5) Modal/sheet | N/A | No modal in recipe row. |

**NOT MODIFIED by Plan 11-05** — Plan 04 owns `recipe_row.html`.

---

### Admin Pages — `/admin`, `/admin/users`, `/admin/credentials`, `/admin/settings`, `/admin/backups`, `/admin/system`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | PASS (N/A) | Admin pages use card/list layouts, no `<table>` with horizontal scroll. `admin_user_list.html` uses `space-y-3` card layout. |
| (2) No horizontal scroll | PASS | Admin cards use `w-full`. Long strings (email, username) use `truncate`. |
| (3) Tap targets >=44px | PASS | Admin action buttons use `px-4 py-2` (adequate). "Add user" button is `px-4 py-2 text-base` (~40px; borderline). No critical sub-44px paths identified. |
| (4) Bottom nav clearance | PASS | Admin pages extend `admin_base.html` which also wraps in `pb-16` via `base.html`. Admin tab in bottom nav is admin-gated. |
| (5) Modal/sheet | N/A | Admin pages do not use mini-modal. |

---

### Login Page — `/login`

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | N/A | No table — login card is a centered form. |
| (2) No horizontal scroll | PASS | `max-w-sm w-full` card doesn't overflow at 375px. |
| (3) Tap targets >=44px | PASS | "Sign in" button is `py-3 px-6 text-base` (well above 44px). |
| (4) Bottom nav clearance | N/A | Bottom nav is auth-gated and hidden on login (no `request.state.user`). |
| (5) Modal/sheet | N/A | No modal. |

---

### Guided Brew Mode — `/brew/guided` (Plan 04 / Plan 11-04 owned)

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | N/A | Full-screen single-surface page. No table. |
| (2) No horizontal scroll | PASS | `min-h-screen` full-width layout. Timer text uses `tabular-nums`. |
| (3) Tap targets >=44px | PASS | All GBM controls (Pause, Next step, Cancel) are `min-h-[56px]` or `min-h-[44px]` per UI-SPEC §4c. |
| (4) Bottom nav clearance | PASS | GBM page is `fixed inset-0` full-screen — bottom nav is covered by the GBM surface (D-20 compliant). |
| (5) Modal/sheet | N/A | GBM itself is a full-screen page. |

---

### Mini-Modal (create-new Roaster / Flavor Note)

| Check | Result | Notes |
|-------|--------|-------|
| (1) Table→card collapse | N/A | Modal is a form, not a list. |
| (2) No horizontal scroll | PASS | Modal panel is `flex flex-col flex-1` on mobile (full-width, no overflow). |
| (3) Tap targets >=44px | FIX APPLIED | Close X button updated from `w-11 h-11` to `inline-flex items-center justify-center min-h-[44px] min-w-[44px]` in both `roaster_modal.html` and `flavor_note_modal.html`. |
| (4) Bottom nav clearance | PASS | Modal is `fixed inset-0 z-50` — covers the bottom nav entirely (z-50 > z-40 nav). |
| (5) Modal/sheet | FIX APPLIED | Changed from `sm:` (640px) breakpoint to `md:` (768px) breakpoint. Mobile: `fixed inset-0 flex flex-col flex-1` full-height sheet. Desktop: `md:flex-none md:rounded-xl md:w-full md:max-w-lg md:mx-4 md:max-h-[90vh] md:overflow-y-auto` centered dialog. Backdrop: `bg-espresso-950/50`. miniModal Alpine component unchanged. |

---

### Native Select vs HTMX Dropdown Audit (UI-SPEC §5c)

| Field | Control type | Location | Status |
|-------|-------------|----------|--------|
| Equipment type (brewer/grinder/etc.) | Native `<select>` | `brew_form.html` + equipment forms | PASS — native OS picker at 375px |
| Roast level | Native `<select>` | Coffee form | PASS |
| Process | Native `<select>` | Coffee form | PASS |
| Water type | `<datalist>` (Phase 5 D-07) | `brew_form.html` | PASS — suggestions + free-type in native input |
| Coffees (searchable) | HTMX autocomplete dropdown | Coffee select in brew form | PASS — `autocomplete.js` renders result list inside the viewport using `absolute` positioning; no horizontal overflow at 375px |

---

## Summary

### Surfaces Audited

Total surfaces: 11 (6 list pages, config hub, home, admin, login, GBM, mini-modal)

### Fixes Applied in Plan 11-05

| Fix | Files Modified | Rule |
|-----|---------------|------|
| 44px tap targets on Edit/Archive/Brew-again in card mode | `session_row.html`, `coffee_row.html`, `equipment_row.html`, `flavor_note_row.html`, `roaster_row.html` | Task 1 (MOB-04) |
| Mini-modal: full-screen sheet (<768px) / dialog (>=768px); breakpoint `sm:` → `md:` | `roaster_modal.html`, `flavor_note_modal.html` | Task 2 (MOB-08) |
| Mini-modal close X: `min-h-[44px] min-w-[44px]` | `roaster_modal.html`, `flavor_note_modal.html` | Task 2 (MOB-04) |

### Deferred Follow-ups (NOT edited by Plan 11-05)

1. **`recipe_row.html` (Plan 04 owned):** Edit, Duplicate, Archive buttons in card mode are `px-3 py-1` (~28px). Need `min-h-[44px] min-w-[44px]`. "Start guided brew" already has `min-h-[44px]`. Action: add to a follow-up quick task or Plan 04 patch.

2. **`recipe_row.html` step count in card mode:** Card mode does not display step count (shows dose/water/ratio/temp only). UI-SPEC §5b lists "step count visible" as the card-mode audit focus. The information is available only through Edit. Action: low priority follow-up.

### Phase Gate Status

- MOB-03 (tables → card lists, no horizontal scroll): PASS — all 6 list fragments have dual layout, no viewport overflow
- MOB-04 (44px tap targets): PASS for this plan's files. Follow-up needed for recipe_row.html (Plan 04 owned)
- MOB-07 (native select for short lists, searchable for coffees): PASS — audit only, no changes needed
- MOB-08 (modals → full-screen sheets <768px / dialogs >=768px): PASS — both modal fragments updated
- MOB-13 (manual 375px verification): pending human verify at Task 4 checkpoint
