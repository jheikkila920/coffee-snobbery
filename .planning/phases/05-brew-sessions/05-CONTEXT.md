# Phase 5: Brew Sessions - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The daily-use surface: the per-user brew log. This phase delivers the `brew_sessions` table and the full logging experience around it. It is the first per-user (not household-shared) feature; every prior feature surface (Phase 4 catalog) is shared.

In scope (13 requirements: BREW-01..11, MOB-05, MOB-06):
- `brew_sessions` table (BREW-01): per-user, with `coffee_id` (denormalized), `bag_id` (FK→bags, nullable), `recipe_id` (FK, nullable), `brewer_id`/`grinder_id`/`kettle_id` (FK→equipment), `water_type`, `dose_grams_actual`, `water_grams_actual`, `yield_grams_actual` (nullable), `tds_pct` (nullable), `extraction_yield_pct` (GENERATED), `water_temp_c_actual`, `grind_setting_actual`, `rating` (Decimal), `flavor_note_ids_observed` (bigint array), `notes`, `brewed_at`.
- Add/edit session form (BREW-02): single scrollable form on a **dedicated route** with aggressive prefill + visible prefill indicators (ghost text / pills).
- Flavor-note tag input for observed notes (BREW-03): autocomplete from shared vocabulary, comma/enter commit, tap-to-remove chips, create-on-no-match.
- Tap-on-stars rating control (BREW-04): 56px stars, thumb-operable, persisted as `Decimal`.
- Live `1:N.NN` brew-ratio readout in Alpine (BREW-05): no schema column.
- LocalStorage draft persistence (BREW-06): namespaced `snobbery:draft:brew:<user_id>`, cleared on submit.
- Server-side draft autosave-on-blur (BREW-07): `POST /brew/draft`, iOS ITP backstop.
- Sticky Save/Cancel on long mobile forms (BREW-08).
- "Brew again" quick re-log (BREW-09): prefills everything but rating/flavor notes/notes.
- Sessions list per user with filters + CSV export (BREW-10): coffee / brewer / rating range / date range.
- CSV import (BREW-11): Beanconqueror-style, refuse rows where coffee (or a named bag) is not in catalog, per-row error list, single transaction.
- `inputmode`/`type` attributes for mobile keyboards (MOB-05).
- Global 16px input rule to prevent iOS focus-zoom (MOB-06): lands in `app/static/css/custom.css`.

Out of scope (belongs in later phases):
- Guided Brew Mode + wake-lock (BREW-12, BREW-13) — Phase 11.
- Home page analytics / preference derivations that consume sessions (HOME-*) — Phase 6.
- AI consumption of sessions / signature regeneration — Phase 7.
- Global search across session notes (SEARCH-*) — Phase 10.
- Bottom-tab nav / PWA shell / dark-mode polish — Phase 11. Phase 5 templates must work at 375px (card-list collapse) but the persistent nav frame is Phase 11.
- Full per-router unit test suite — Phase 12 (add tests as you go per CLAUDE.md, but the formal suite is Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Form surface & controls
- **D-01: Dedicated route for the brew form, not catalog-style inline-expand.** `/brew/new`, `/brew/{id}/edit`, and "Brew again" deep-links to `/brew/new?from={session_id}`. This intentionally diverges from Phase 4 D-02 (inline-expand-on-list) because the brew form is long, carries sticky save + draft autosave, and is the future Guided Brew Mode (Phase 11) handoff target; a real route keeps deep-linking, prefill, and draft restore clean. The sessions **list** still follows the HTMX-fragment conventions from Phase 4 (filters via `hx-get` + `hx-push-url`, row fragments).
- **D-02: Optional refractometer fields behind a closed-by-default "Advanced" disclosure.** `yield_grams_actual` and `tds_pct` (both nullable) live inside an expander (labeled e.g. "Refractometer / advanced"); `extraction_yield_pct` is a GENERATED column rendered read-only inside the same disclosure. Keeps the <30s path clean for the common case. Draft persistence remembers whether the disclosure was open.
- **D-03: Rating uses half-step (0.5) left/right tap-zones, but the column stays `Decimal multiple_of=0.25`.** The tap UI exposes 0.5 increments only (left half of a star = +0.5, right half = +1.0; ~28px zones on a 56px star). The DB/Pydantic constraint remains `ge=0, le=5, multiple_of=0.25` (BREW-04 unchanged at the data layer) so CSV imports carrying quarter values still validate and a future finer UI isn't a migration. **Recorded deviation:** the ~28px half-zones are narrower than the strict 44px tap-target rule (MOB-04); accepted at household scale on a 56px-tall control. Planner should make the zones as forgiving as possible (full star height, generous hit-slop).

### Prefill & smart defaults (the <30s core-value engine)
- **D-04: Hybrid prefill source.** On `/brew/new` open, prefill from the user's single most-recent session (coffee + all carryable fields). When the user changes the coffee, re-prefill from their last session **with that coffee**. Best of both: instant for "same beans tomorrow", accurate when switching beans. "Brew again" (D-08) is a special case that prefills from a specific source session.
- **D-05: Recipe wins on select for the four template fields.** Selecting or changing a recipe overwrites `dose_grams_actual`, `water_grams_actual`, `water_temp_c_actual`, and `grind_setting_actual` with the recipe's targets (a recipe IS the template). Last-session prefill fills everything else (coffee, bag, equipment, water_type, flavor context). With no recipe selected, last-session values stand. Every field remains editable after prefill.
- **D-06: Auto-select the coffee's newest open bag.** When a coffee is chosen, default `bag_id` to that coffee's most-recently-`opened_at` bag where `finished_at IS NULL`. Editable and clearable (clearing = "freestyle", `bag_id=null`). If the coffee has no open bag, leave blank and surface a quick "open new bag" link (to the Phase 4 bag form under coffee detail). This keeps roast-freshness analytics (HOME-04, which reads `bags.roast_date`) populated by default.
- **D-07: `water_type` is a native `<select>` of common types plus free-text "Other".** Suggested values: Tap, Filtered, Third Wave Water, Distilled, Spring, RO/Zero. Stored as text on the session. Fast thumb selection with consistent values; "Other" is the escape hatch. Planner picks the final seed list and the Other-input mechanics.
- **D-08: "Brew again" prefills from the source session and explicitly blanks the per-attempt fields.** From any sessions-list row, "Brew again" → `/brew/new?from={id}` prefilled with that session's coffee, bag (if still active), recipe, brewer, grinder, kettle, water_type, dose, water, temp, grind — and explicitly blank `rating`, `flavor_note_ids_observed`, and `notes`. This overrides the D-04 hybrid default when a `from` param is present.

### Flavor-note tag input
- **D-09: A committed observed note that matches nothing is auto-created as a shared `flavor_notes` row with `category='other'`.** No interruption at log time; the new note enters the shared vocabulary and can be recategorized later on the `/flavor-notes` catalog page. The chip shows a subtle "new" badge so the user knows it was just created. This honors BREW-03 ("comma/enter commits a new tag") while preserving the kettle-side speed path. Contrast with Phase 4 D-15's full mini-modal (name + category) for catalog-context creation — too heavy here.
- **D-10: Autocomplete-first, link-on-exact-match, create-only-on-no-match.** As the user types, the input surfaces existing notes (reuse Phase 4's `autocomplete_list.html` fragment + the `hx-get`-on-focus / debounce / `hx-sync="this:replace"` pattern from Phase 4 D-13/D-14). Comma/enter links an existing note when the text matches one case-insensitively (citext); a new row is created only when nothing matches exactly. Minimizes near-duplicate vocabulary churn without an explicit "+ Create" tap.
- **D-11: The selected coffee's advertised notes render as one-tap quick-add chips.** When a coffee is selected, surface its `coffees.advertised_flavor_note_ids` as tappable suggestion chips above the input (e.g. "Advertised: blueberry · chocolate · floral"); tapping adds to the observed list. Leverages catalog data, speeds logging, and helps users clear the AI cold-start gate (≥5 distinct observed notes, AI-11). `flavor_note_ids_observed` (per-session, observed) is distinct from `advertised_flavor_note_ids` (per-coffee, roaster-advertised) — never conflate them.

### CSV import & export
- **D-12: Coffee matched by name (citext), roaster-qualified when a roaster column is present.** Since `coffees.name` is intentionally non-unique (different roasters share names — see `app/models/coffee.py` docstring), an import row with a roaster column must match on name+roaster; without one, match on name alone and treat an ambiguous multi-match as an unresolved (refused) row. Refuse any row whose coffee can't be resolved, with a per-row reason in the result summary (BREW-11).
- **D-13: Bag matching is optional; refuse only on named-but-unmatched.** If a row identifies a bag that resolves (by coffee + `roast_date`), link it; if it names/dates a bag that does not resolve, refuse that row; if it names no bag, import with `bag_id=null` (freestyle). This matches BREW-11's "refuse rows where coffee or bag not in catalog" intent without forcing a bag onto legacy Beanconqueror history that lacks precise bag data.
- **D-14: Idempotent dedup on re-import.** Dedup key = `(user_id, coffee_id, brewed_at)`. Rows matching an existing session are skipped (not inserted) and counted in the result summary, so re-importing the same file is a safe no-op. All accepted rows insert in a single transaction (BREW-11).
- **D-15: Export is name-based and round-trip-safe.** CSV export of the filtered sessions view resolves IDs to human-readable names (coffee, roaster, recipe, equipment, observed flavor notes) and includes read-only computed columns (brew ratio, extraction yield). The same file re-imports cleanly via the D-12/D-13 name matching — one format serves both human reading (Excel) and backup/migration round-trip.

### Claude's Discretion
- **`brewed_at` default + editability** — recommend default to now (server-side) and editable for back-dating imported/late-logged brews. Planner confirms timezone handling (store tz-aware UTC; render in `APP_TIMEZONE`).
- **Server draft store model** — recommend one active draft per `user_id` (a `brew_drafts` table or a JSON column keyed by user); autosave-on-blur applies to `/brew/new` only. Editing an existing session (`/brew/{id}/edit`) is a normal form save, NOT draft-backed. Draft cleared on successful submit and on logout (MX-5). Planner picks the exact storage shape (dedicated table vs reuse of an existing store) and the localStorage↔server reconciliation order (server restore only when localStorage is empty, per BREW-07).
- **`equipment.usage_count` increment mechanism** — Phase 4 shipped this column at 0 and explicitly deferred the increment to Phase 5. Planner picks service-layer write (increment on session insert/delete, decrement on equipment change) vs a Postgres trigger. Recommendation: service-layer for testability and to keep logic in one place; must handle the three equipment FKs (brewer/grinder/kettle) and edits that change equipment.
- **Sessions-list default sort** — recommend newest `brewed_at` first.
- **Edit-session form population** — the dedicated `/brew/{id}/edit` form shows the session's actual stored values (not ghost-text prefill); prefill ghosting is a `/brew/new` affordance only.
- **Exact Beanconqueror column-to-field mapping** — plan-phase research item. Researcher should pull a real Beanconqueror CSV export schema and map its columns to `brew_sessions` fields; the policy decisions (D-12..D-15) constrain the mapping but the literal column names need verification.
- **Filter control styling + rating-range / date-range widgets** — planner picks (native inputs preferred for mobile; reuse Phase 4 filter-bar `hx-push-url` pattern).
- **Whether the live ratio readout also shows extraction yield** when TDS is entered — small enhancement; planner picks.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 5: Brew Sessions" — goal sentence, 5 success criteria, and Notes (carries MX-1 16px rule, MX-5 LocalStorage namespacing + clear-on-logout, MX-6 tap-on-stars-not-native-range, HX-3 flavor-note `hx-get`-on-focus). Confirms Guided Brew Mode (BREW-12/13) is deferred to Phase 11.
- `.planning/REQUIREMENTS.md` §"Brew Sessions (BREW)" — BREW-01..11 verbatim (esp. BREW-01 column list, BREW-06/07 draft semantics, BREW-09 quick-relog field set, BREW-11 import scope) and §"Mobile-First + PWA (MOB)" MOB-05 (`inputmode`/`type`) + MOB-06 (16px rule + Playwright assertion).
- `.planning/PROJECT.md` §"Brew Session UX" + §"Brew Session Catalog UX", §"Key Decisions" rows: "Single-scrollable brew session form with aggressive prefill (not stepped)", "Server-side draft autosave-on-blur as iOS ITP backstop", "Add `yield_grams_actual`, `tds_pct`, `extraction_yield_pct` to brew_sessions in v1", "CSV import alongside export, scope-limited". §"Architectural invariants" ("Brew sessions and AI recommendations are per-user"; CSRF on all state-changing forms; security headers; mobile-first 375px).
- `.planning/STATE.md` — decision accumulator. No Phase-5-specific research flag carried forward (live flags belong to Phases 7, 10, 11).

### Prior phase context (decisions Phase 5 inherits)
- `.planning/phases/04-shared-catalog/04-CONTEXT.md` — **the most important inheritance.** D-01..D-04 (HTMX-fragment CRUD, 200-with-fragment validation pattern that Phase 5 forms reuse), D-13/D-14 (autocomplete debounce + `hx-get`-on-focus, no OOB — the flavor-note tag input reuses this), D-15 (catalog mini-modal create — contrast with Phase 5 D-09's lighter create path), the SEC-06 Pydantic-v2 numeric-range form pattern. Also documents `coffees`, `bags`, `recipes`, `equipment`, `flavor_notes` schemas the session form references.
- `.planning/phases/00-foundation/00-CONTEXT.md` — `Mapped[...]` model convention, `app/db.py::SessionLocal` sync session, single migration per logical change, Postgres extensions (`citext` enables case-insensitive flavor-note matching).
- `.planning/phases/01-middleware/01-CONTEXT.md` — CSP-strict Alpine (CSP build, `Alpine.data('name', factory)`, no `hx-on:` inline, no `|safe`); `FragmentCacheHeadersMiddleware` (`Cache-Control: no-store + Vary: HX-Request` on HTMX fragments — sessions-list filter fragments rely on it); slowapi default (Phase 5 routes not rate-limited).
- `.planning/phases/02-auth/02-CONTEXT.md` — `request.state.user` is the full `User` row (sessions are scoped by `user.id`); `CSRFFormFieldShim` (every Phase 5 form includes the hidden `X-CSRF-Token` input like `pages/setup.html`); `require_user` in `app/dependencies/auth.py`.
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — sync-session catalog pattern; service-split convention (per-entity service modules) — Phase 5 adds `app/services/brew_sessions.py` (+ possibly `drafts.py`, `csv_io.py`).

### Research output
- `.planning/research/PITFALLS.md` — §6 MX-1 (16px min font on inputs → iOS no-zoom; global rule in `custom.css`), MX-5 (LocalStorage draft namespacing + clear-on-logout), MX-6 (tap-on-stars not native range); §2 HX-3 (flavor-note datalist OOB footgun → `hx-get` on focus), HX-4 (debounce 350ms + `hx-sync` + min-char threshold).
- `.planning/research/STACK.md` — §1 Pydantic `>=2.13,<3.0` (`Field(ge=, le=, multiple_of=)` for rating + numeric ranges), SQLAlchemy `>=2.0.49,<2.1` (`Mapped[...]`, `Computed()` for the GENERATED `extraction_yield_pct`, `ARRAY(BigInteger)` for `flavor_note_ids_observed`), Alembic `>=1.18,<2.0`; §3.3 sync engine for the CRUD surface.

### Operational + spec
- `CLAUDE.md` §"Stack invariants", §"Architectural invariants" ("Brew sessions ... are per-user"; "Mobile-first ... 375px"; "CSRF on all state-changing forms"; "Security headers on every response"), §"Things to never do silently" (no `|safe`; never disable CSRF/CSP), §"Code conventions" (ruff, type hints, Pydantic v2, SQLAlchemy 2.0 style).
- `docs/snobbery-gsd-prompt.md` — original brief; brew-session field intent + the 30-second core-value framing originate here. `.planning/` docs are authoritative where they diverge.

### External library docs (planner verifies via Context7 in plan-phase)
- `sqlalchemy` (`>=2.0.49,<2.1`) — `Mapped[...]`, `mapped_column(Computed("..."))` for `extraction_yield_pct`, `ARRAY(BigInteger)`, `select()`/`update()`, `Numeric`/`Decimal` for `rating`.
- `pydantic` (`>=2.13,<3.0`) — `Field(ge=0, le=5, multiple_of=0.25)` for rating, numeric ranges for dose/water/temp/yield/tds, the form-fragment ValidationError re-render path (Phase 4 D-04).
- `alembic` (`>=1.18,<2.0`) — autogenerate detects the new `BrewSession` model; the GENERATED column likely needs a hand-edit (autogenerate doesn't emit `GENERATED ALWAYS AS`).
- `htmx` 2.0.10 (CDN, in `base.html`) — `hx-get`/`hx-post`, `hx-push-url`, `hx-trigger` debounce, `hx-sync="this:replace"` for the filter bar + tag-input autocomplete; `HX-Redirect` for post-save navigation.
- `alpinejs` CSP build (CDN, in `base.html`) — `Alpine.data(...)` components for the rating control, tag input, live ratio readout, and the Advanced disclosure (all CSP-build compliant; no inline expressions).

### Existing code (read before changing)
- `app/models/coffee.py` — name is non-unique citext; identity is (name, roaster_id); `advertised_flavor_note_ids` is `BIGINT[]`. Drives D-11 and D-12.
- `app/models/bag.py` — `coffee_id` FK `ondelete="RESTRICT"`; `opened_at`/`finished_at`/`roast_date` columns drive D-06 open-bag selection and D-13 bag matching.
- `app/models/recipe.py` — `dose_grams`/`water_grams`/`water_temp_c`/`grind_setting` + JSONB `steps`; drives D-05 recipe-wins prefill.
- `app/models/equipment.py` — `type` enum + the `usage_count` column shipped at 0 (Phase 5 increments it per discretion note).
- `app/models/flavor_note.py` — `name` citext unique + `category` 9-value enum; drives D-09/D-10.
- `app/models/__init__.py` — re-export the new `BrewSession` (and any draft model) so Alembic autogenerate sees them.
- `app/db.py::SessionLocal` — sync sessionmaker the brew routes consume.
- `app/dependencies/auth.py::require_user` — gate every brew route; sessions are scoped to `request.state.user.id`.
- `app/csrf.py` — hidden `X-CSRF-Token` field pattern for every brew form.
- `app/main.py` — register the new `brew` router via `include_router`; no middleware changes.
- `app/templates/base.html` — extend for brew pages; CSP nonce + CSRF meta + HTMX/Alpine already loaded.
- `app/templates/fragments/autocomplete_list.html` — reuse for the flavor-note tag-input autocomplete (D-10).
- `app/static/css/custom.css` — currently empty; the MOB-06 16px `input, select, textarea` rule lands here.
- `app/static/js/alpine-components/` — add `rating-stars.js`, `flavor-tag-input.js`, `brew-ratio.js`, `brew-draft.js` (CSP-build, registered via `Alpine.data`).
- `app/events.py` — extend with `brew.session.*` (created/updated/deleted), `brew.draft.*`, `brew.csv.imported`/`exported` constants per the `<area>.<action>` taxonomy.
- `app/migrations/versions/` — single new migration: `brew_sessions` table (+ the GENERATED column hand-edit), optional draft store, any indexes (e.g. on `(user_id, brewed_at)` for the list + the `(user_id, coffee_id, brewed_at)` dedup uniqueness).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all on disk from Phases 0–4)
- **`app/templates/fragments/autocomplete_list.html`** + Phase 4 D-13/D-14 autocomplete wiring — the flavor-note tag input's autocomplete is a direct reuse.
- **`app/static/js/alpine-components/` + `__init.js`** — established CSP-build Alpine registration; new brew components slot in alongside `autocomplete.js`, `mini-modal.js`, `recipe-step-builder.js`.
- **Phase 4 SEC-06 form pattern** (`app/services/form_validation.py::errors_by_field` + 200-with-fragment re-render, D-04) — the brew form's validation path reuses it exactly.
- **`app/csrf.py::CSRFFormFieldShim`** + the hidden-input convention from `pages/setup.html`.
- **`FragmentCacheHeadersMiddleware`** — sessions-list filter fragments get `no-store + Vary: HX-Request` for free.
- **`app/db.py::SessionLocal`** + the Phase 0 pool knobs — brew services use sync sessions.
- **Postgres `citext`** — case-insensitive flavor-note + coffee-name matching (D-10, D-12).

### Established Patterns (Phase 5 follows)
- "Cross-cutting → middleware; feature surface → router; stateful logic → service" — Phase 5 adds `app/routers/brew.py` + `app/services/brew_sessions.py` (+ drafts/csv helpers).
- "Migrations autogenerated from `Mapped[...]` models, one per logical change" — but the GENERATED `extraction_yield_pct` and any partial/unique indexes need a hand-edit (autogenerate can't emit them).
- "Audit events are structured-logger calls" (Phase 1 D-14) — emit `brew.session.*` at service write paths.
- "CSP-strict: no `unsafe-eval`, no `hx-on:`, no `|safe`" — brew templates are subject to the existing grep tests.
- **Deviation from Phase 4 D-02:** the brew form is a dedicated page (D-01), not inline-expand. The sessions LIST still uses HTMX fragments + `hx-push-url` filters like the catalog lists.

### Integration Points
- `app/main.py` — `include_router(brew.router)`.
- `app/models/__init__.py` — register `BrewSession` (+ draft model).
- `app/migrations/versions/` — new migration (table + GENERATED column + indexes + dedup constraint).
- `app/static/css/custom.css` — DO NOT create. MOB-06 16px rule already ships in tailwind.src.css @layer base (RESEARCH.md + UI-SPEC correction).
- Equipment `usage_count` — Phase 5 wires the increment that Phase 4 left at 0.
- Coffee detail page — the D-06 "open new bag" link points at the existing Phase 4 bag form.

</code_context>

<specifics>
## Specific Ideas

- **`brew_sessions` indexes:** at minimum `(user_id, brewed_at DESC)` for the list and the per-coffee prefill lookup `(user_id, coffee_id, brewed_at DESC)`; the D-14 dedup key `(user_id, coffee_id, brewed_at)` is a natural UNIQUE constraint candidate (planner confirms whether to enforce uniqueness in-DB or only at import time — note manual same-second double-logs are unlikely but a hard UNIQUE could reject a legitimate retry; recommend import-time dedup + a non-unique index).
- **`extraction_yield_pct` is a Postgres GENERATED column**, computed from `(yield_grams_actual * tds_pct) / dose_grams_actual` (planner confirms the exact formula and NULL behavior — it must be NULL when yield or tds is NULL). Read-only everywhere; never written by the app.
- **Two distinct flavor-note relationships must never be conflated:** `coffees.advertised_flavor_note_ids` (per-coffee, roaster-advertised, shown as quick-add chips D-11) vs `brew_sessions.flavor_note_ids_observed` (per-session, what the user tasted). Both are `BIGINT[]` referencing `flavor_notes.id`.
- **Prefill indicators (BREW-02):** prefilled values render with a visible ghost/pill treatment so the user trusts them and doesn't re-type defensively. Distinguish "prefilled, untouched" from "user-edited" state in the Alpine component.
- **Draft reconciliation order (BREW-07):** localStorage is primary; the server draft is the ITP backstop. On form open, restore from localStorage if present; fall back to the server draft only when localStorage is empty.
- **CSV result UX:** import returns a per-row outcome summary (inserted / skipped-duplicate / refused-with-reason), not a bare success/fail.

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are captured in the decisions above plus the canonical refs (REQUIREMENTS.md BREW-01..11, MOB-05, MOB-06).

</specifics>

<deferred>
## Deferred Ideas

- **Guided Brew Mode + wake lock (BREW-12, BREW-13)** — Phase 11. The dedicated-route decision (D-01) is partly to make this handoff clean later.
- **Per-attempt "advanced" insights beyond EY** (e.g. strength/extraction target zones, brew control chart) — out of scope; v2.
- **Inline recategorization of an auto-created flavor note** (D-09 creates as 'other'; editing category happens on the catalog page) — add an inline shortcut only if it becomes friction.
- **Bag-required strict import mode** (D-13 chose bag-optional) — revisit only if freshness-analytics integrity demands it.
- **CSV import of catalog entities (coffees/bags/roasters)** — out of scope; import is brew-sessions-only and refuses unknown coffees/bags by design (BREW-11).
- **Hard UNIQUE constraint on (user_id, coffee_id, brewed_at)** — deferred in favor of import-time dedup to avoid rejecting legitimate same-timestamp manual logs; reconsider if duplicate logs become a real problem.
- **Quick-log "repeat exact last brew" one-tap** (logs a copy of the last session with just a new rating) — possible speed enhancement beyond "Brew again"; defer unless requested.
- **Bag list standalone page (`/bags`)** — carried from Phase 4 deferred list; Phase 5's open-bag selection (D-06) may light up the "what's open right now" use case. Revisit if needed; not in Phase 5 scope.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (STATE.md "Pending Todos: None yet").

</deferred>

---

*Phase: 5-Brew Sessions*
*Context gathered: 2026-05-19*
