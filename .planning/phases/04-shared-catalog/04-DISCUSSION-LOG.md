# Phase 4: Shared Catalog - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `04-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 4-Shared Catalog
**Areas discussed:** CRUD interaction pattern, Photo upload + serving pipeline, Recipe step builder mechanics, Autocomplete-on-create UX

---

## CRUD interaction pattern

### Q1: Default interaction pattern for the catalog?

| Option | Description | Selected |
|--------|-------------|----------|
| HTMX fragments throughout (Recommended) | List page canonical; add/edit via HTMX-loaded form; POST returns a row fragment + OOB swaps for counts. Filters drive list via hx-get with URL push. | ✓ |
| Classic POST→303 page redirects | Each entity has /coffees, /coffees/new, /coffees/{id}/edit pages mirroring auth pattern. Every save = full page reload. | |
| Hybrid — lists HTMX, single-row CRUD classic | Filter/search HTMX; create/edit/archive as full-page forms with 303 back. | |

**User's choice:** HTMX fragments throughout
**Notes:** Locks the catalog feel as a modern HTMX-fragment surface, distinct from the classic auth pages.

### Q2: Where does the add/edit form live in the HTMX flow?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline expand on the list page (Recommended) | Form expands at top of list; saving hx-swaps the row in, form collapses. Stays in one viewport at 375px. | ✓ |
| Full-screen sheet on mobile, dialog on desktop (modal) | Matches MOB-08 from PROJECT spec; heavier Alpine scaffolding (focus trap, ESC, breakpoint branching). | |
| Dedicated /new and /edit pages | Even with HTMX lists, send to separate route for forms. Simplest template; full navigation per save. | |

**User's choice:** Inline expand on the list page
**Notes:** Defers the modal scaffolding to Phase 11's polish pass where MOB-08 lands.

### Q3: How should filter state interact with the URL?

| Option | Description | Selected |
|--------|-------------|----------|
| hx-push-url on filter changes (Recommended) | Filter change HTMX-fetches list + updates URL to /coffees?roaster=...&archived=...; browser back replays; bookmarkable. Phase 1 FragmentCacheHeadersMiddleware mitigates HX-2 bfcache leak. | ✓ |
| Pure HTMX (no URL update) | No bookmarkable filtered views; refresh loses filter. | |
| Form-submit-to-URL (classic) | Filter changes submit GET form; full reload. Universal browser behavior, no JS. | |

**User's choice:** hx-push-url on filter changes
**Notes:** Bookmarkable filtered views are valuable for the household-share use case.

### Q4: Form validation errors — how should they render after a bad save?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-render whole inline form fragment with field-level errors (Recommended) | Server returns 200 with form fragment, user's values preserved, inline error messages by each field. | ✓ |
| Inline-error swap targeting only invalid field(s) | OOB swaps to per-field error spans; less data on retry, more fiddly templating. | |
| Native HTML5 validation first, Pydantic backstop | min/max/step on inputs; Pydantic catches what slips through. Duplicates constraints in template + schema. | |

**User's choice:** Re-render whole inline form fragment with field-level errors
**Notes:** Sets the pattern for Phase 5 brew-session forms and Phase 9 admin forms.

---

## Photo upload + serving pipeline

### Q1: Client-side downscale before upload — worth the complexity?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — Canvas downscale to ~2000px max before POST (Recommended) | 4–8MB → ~500KB–1MB; saves cell-data + server CPU; server still re-encodes for SEC-4 defense. ~80 LOC vanilla JS. | ✓ |
| No — server-only resize | Simpler client code; raw 4–8MB on every upload; server blocked ~1–2s under Pillow. | |

**User's choice:** Yes — Canvas downscale to ~2000px max before POST
**Notes:** JS-disabled fallback path acceptable; server-side re-encode is the security boundary.

### Q2: Photo serving route and access control?

| Option | Description | Selected |
|--------|-------------|----------|
| Auth-gated route, opaque UUID filenames, private cache (Recommended) | GET /photos/{uuid}.jpg under routers/photos.py; auth required, 404 (not 403) for non-authed; immutable private cache; nosniff. | ✓ |
| Auth-gated route, sequential filenames, private cache | Same gating, predictable filenames make debug easier; slightly leakier enumeration risk. | |
| Public StaticFiles mount, opaque UUIDs | No auth check; URL secrecy only; faster but violates spec ("served via app route"). | |

**User's choice:** Auth-gated route, opaque UUID filenames, private cache
**Notes:** Matches ROADMAP Phase 4 success #4 verbatim.

### Q3: Photo lifecycle — replace / delete / orphans?

| Option | Description | Selected |
|--------|-------------|----------|
| Delete old file synchronously on replace + on bag delete; orphan-sweep nightly (Recommended) | Write-new-then-delete-old ordering; sweep runs alongside Phase 8 backups; self-healing against leaks. | ✓ |
| Delete on replace only, no sweep | Synchronous unlink on replace and hard-delete; no nightly cleanup; orphans linger forever. | |
| Never delete | Photos accumulate; admin manual cleanup. Simplest code, worst hygiene. | |

**User's choice:** Delete old file synchronously on replace; on bag delete; orphan-sweep nightly
**Notes:** Phase 4 ships sweep_orphans() function; Phase 8 wires it into APScheduler.

### Q4: Where does the photo attach — bags only, coffees only, or both?

| Option | Description | Selected |
|--------|-------------|----------|
| Bags only (Recommended; matches CAT-08) | Spec is "bag photo upload"; each physical bag can have its own photo. Coffee list can surface latest bag thumb if useful. | ✓ |
| Both — coffee hero + bag photos | Adds coffees.photo_filename column. Visually richer but more lifecycle to manage. | |
| Coffees only — bag photos collapse into coffee.photo_filename | Conflicts with CAT-08; not recommended. | |

**User's choice:** Bags only
**Notes:** Coffee list may show latest bag thumb (planner discretion).

---

## Recipe step builder mechanics

### Q1: Step builder mechanics — Alpine.js array vs HTMX server round-trips?

| Option | Description | Selected |
|--------|-------------|----------|
| Alpine.js local array, single JSON submit on save (Recommended) | Add/remove/reorder pure Alpine; zero server round-trips during editing; live cumulative-water + time-offset readouts; submit serializes to JSON in hidden input. | ✓ |
| HTMX-driven per-step actions | Each add/remove/reorder is hx-post; server stores draft state; chatty (12 round-trips for 6-step recipe); needs draft schema. | |
| Hybrid — Alpine for unsaved drafts, HTMX once recipe exists | Bridges both worlds; doubles the JS code. | |

**User's choice:** Alpine.js local array, single JSON submit on save
**Notes:** No draft-state table; server validates the full JSON array on save.

### Q2: What does a single step capture?

| Option | Description | Selected |
|--------|-------------|----------|
| water_grams + time_seconds + label (Recommended) | Cumulative water + elapsed time + free-text label. Live readout shows delta-water + delta-time. | ✓ |
| Add 'pour duration' explicit field | water_grams + start_time + pour_duration + label; more expressive but doubles cognitive load. | |
| Add 'agitation' / 'technique' enum per step | Niche pour-over nuance; deferred to v2. | |

**User's choice:** water_grams + time_seconds + label
**Notes:** pour_duration and technique enums noted in deferred ideas.

### Q3: Pour timeline preview — how should it render?

| Option | Description | Selected |
|--------|-------------|----------|
| Vertical bar with proportional segments (Recommended; matches ROADMAP) | Colored segments height-proportional to time; cumulative water labeled at breaks; top-to-bottom reads like the brew. | ✓ |
| Horizontal Gantt-style bar | More familiar timeline affordance; cramped at 375px. | |
| Plain table — (time, cum water, delta water, label) rows | Readable; screen-reader friendly; less visual. | |

**User's choice:** Vertical bar with proportional segments
**Notes:** Same Alpine component as the step builder; segment heights computed reactively.

### Q4: Duplicate-recipe action — where and how?

| Option | Description | Selected |
|--------|-------------|----------|
| Button on row + on detail; immediate copy + redirect to edit (Recommended) | hx-post → server INSERTs deep copy with " (copy)" suffix → HX-Redirect to new recipe edit. Predictable. | ✓ |
| Duplicate creates draft, opens in modal | More involved schema (is_draft column or temp table). | |
| Fork-from-existing dropdown on new-recipe form | No INSERT until save; less discoverable from list. | |

**User's choice:** Button on the recipe row + on recipe detail; immediate copy + redirect to edit
**Notes:** Uses HX-Redirect response header for the navigation.

---

## Autocomplete-on-create UX

### Q1: From inside the coffee form, user types unmatched value. What happens?

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit '+ Create new roaster: X' option in the dropdown (Recommended) | HTMX autocomplete (350ms debounce, ≥2 chars); unmatched typed value prepends create option; explicit click triggers POST. | ✓ |
| Silent create on coffee save | No audit trail; typos become permanent rows. | |
| Block save — force user to go create the entity first | Cleanest data hygiene, worst UX; conflicts with spec intent. | |

**User's choice:** Explicit '+ Create new roaster: X' option in the dropdown
**Notes:** No silent inserts; discoverable.

### Q2: PITFALL HX-3 dodge for flavor-notes datalist?

| Option | Description | Selected |
|--------|-------------|----------|
| No OOB swap — hx-get on field focus to refresh the datalist (Recommended) | hx-trigger="focus once"; creating a new note doesn't OOB into other datalists; next focus refreshes. Matches HX-3 preferred mitigation. | ✓ |
| Explicit-selector hx-swap-oob='outerHTML:#flavor-notes-datalist' | HTMX 2 supports it; more fragile under rapid create. | |
| Page-level Alpine.js store; HX-Trigger broadcasts | Client-side cache; more state to manage. | |

**User's choice:** No OOB swap — use hx-get on field focus to refresh the datalist
**Notes:** Eliminates the duplicate-ID race entirely.

### Q3: Inline-create depth — name only, or full fields?

| Option | Description | Selected |
|--------|-------------|----------|
| Name only inline; full edit on entity's page later (Recommended) | Inline create sends name (+ category for flavor notes); user fills metadata later on /roasters. Fast. | |
| Mini-modal: full fields when creating inline | Mini-form with name + location + website + notes for roasters. More complete, more friction at coffee-add time. | ✓ |
| Name only + nag toast after coffee save | Soft pressure to fill in metadata via toast on next page load. | |

**User's choice:** Mini-modal: full fields when creating inline
**Notes:** Deviates from Claude's recommendation; user wants completeness at creation time.

### Q4: Mini-modal scope — same depth for both entities, or different?

| Option | Description | Selected |
|--------|-------------|----------|
| Roaster: full set (name+location+website+notes); flavor note: name+category only (Recommended) | Roasters carry meaningful metadata (location, website for future AI URL verification); flavor notes are vocabulary entries. | ✓ |
| Both full set of their columns | Symmetric depth scaled to each entity. | |
| Both name-only with 'add more details' caret to expand | Default fast entry; caret reveals optional fields. Speed with escape hatch. | |

**User's choice:** Roaster gets full mini-modal; flavor note gets name + category only
**Notes:** Asymmetric depth matches the asymmetric value of the metadata.

---

## Claude's Discretion

User deferred to planner on:
- Exact `coffees` schema column choices (country, process, roast_level, origin, varietal, etc.)
- Exact enum values for process / roast_level / equipment.type
- Postgres ENUM vs text+CHECK constraint choice (Phase 3 D-01 precedent: text+CHECK)
- Default sort order per list
- Whether coffee list shows latest bag thumbnail
- `archived=true` UX surface details (toggle vs URL state vs both)
- Empty array vs NULL for `coffees.advertised_flavor_note_ids`
- Inline-expand vs dedicated route for the "open new bag" flow
- Hard-delete-vs-soft-delete default at Phase 4 (recommended: archive-only)
- Modal close-on-Escape / focus-trap depth
- Photo MIME validation library choice (puremagic / filetype / hand-roll)
- HEIC support via `pillow-heif`
- Thumbnail filename suffix vs separate URL pattern

## Deferred Ideas

Captured for future phases:
- Standalone `/bags` list page — Phase 5 may surface the use case
- Recipe step `pour_duration` field — v2 if recipes need it
- Recipe step `technique` / `agitation` enum — v2
- Recipe versioning — currently edit-in-place; deferred per PROJECT v2 list
- Hierarchical flavor wheel UI — v2 per PROJECT v2 list
- Coffee hero photo separate from bag photo — v2 if needed
- HEIC-from-iOS-without-JS via `pillow-heif` — add only if friction surfaces
- Bulk actions on catalog lists — not in spec
- Multiple photos per entity (galleries) — bag-per-photo model is the v1 spec
- Inline edit of roaster metadata after inline-create — defer if it becomes friction
- Search across catalog from inside forms — Phase 10 owns global search
- Coffee-list bags-open count column — Phase 5 when sessions/bags have lifecycle data
- Recipe difficulty / skill-level tag — niche
