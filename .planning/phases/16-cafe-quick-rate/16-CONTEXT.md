# Phase 16: Cafe Quick-Rate - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a per-user "cafe-log" entity that captures a coffee tasted outside the home in ~20 seconds, with optional enrichment, isolated from brew-parameter analytics but feeding taste-preference derivation and the AI input signature. Six locked requirements:

- **CAFE-01:** ~20-second log path requiring only a name + a rating
- **CAFE-02:** Optional brand/roaster, origin, brew method, notes, flavor notes, photo
- **CAFE-03:** Per-user, listed/viewable, visually distinct from brew sessions
- **CAFE-04:** Cafe ratings, flavor notes, origin/roaster feed preference derivation and the AI input signature (subsequent AI runs reflect cafe taste data)
- **CAFE-05:** Cafe logs excluded from grind, ratio, temperature, and recipe sweet-spot analytics
- **CAFE-06:** User can edit and delete their own cafe logs

Explicitly NOT in this phase:
- IA / nav redesign (Phase 17 owns) — the new "Quick rate" button lives on the existing `/brew` page header, surviving Phase 17's nav reshuffle untouched
- Mobile visual rework / safe-area / polish-to-major-company-bar (Phase 21 owns)
- AI page consolidation, AI research/predict, or charts (Phase 19 owns)
- A separate "Top cafe tastings" home card or any home-page restructure (Phase 17 / Phase 19)
- Cafe logs in global trigram search index (Phase 10 surface; expansion deferred)
- CSV import/export for cafe logs — brew CSV stays brew-only (consistent with Phase 15.1 boundary)
- Inline "add new coffee from brew form" carryover (STATE.md note; re-evaluated and out-of-scope: cafe quick-rate doesn't enrich the shared coffee catalog, it bypasses it)

</domain>

<decisions>
## Implementation Decisions

### Data model — `cafe_logs` table shape

- **D-01:** Net-new `cafe_logs` table. Purely additive migration; zero impact on `brew_sessions`, the AI scheduler, or existing analytics queries. Unified-table options (boolean `is_cafe_log` or `session_type` ENUM on `brew_sessions`) were rejected because `brew_sessions.coffee_id` is `NOT NULL ondelete=RESTRICT` per `app/models/brew_session.py:79`, and making it nullable breaks a documented schema invariant. ARCHITECTURE.md confirms the same blocking constraint. Lock the separate-table approach; the planner finalizes column types.

- **D-02:** Brand → `roaster_id INT NULL ondelete=SET NULL` FK to `roasters.id`, with create-on-the-fly autocomplete mirroring the existing flavor-notes pattern (Phase 4) and the Phase 15.1 D-03 varietal pattern. CITEXT UNIQUE on `roasters.name` already collapses casing dupes. Lets `get_preference_profile`'s roaster GROUP BY UNION cafe roasters with brew roasters without typo pollution.

- **D-03:** Origin → `origin_country TEXT NULL` (no FK, no new lookup table). Autocomplete sources from the existing distinct `coffee_origins.country` values (Phase 15.1 D-01 introduced this table) plus a small seeded country list. Origin preference query UNIONs `cafe_logs.origin_country` with `coffee_origins.country`. No region column at v1 (matches Phase 15.1 D-05 reasoning — region is optional, user can put it in notes if they care).

- **D-04:** Flavor notes → `flavor_note_ids BIGINT[]` NOT NULL DEFAULT '{}' with a GIN index, mirroring `brew_sessions.flavor_note_ids_observed` and `coffees.advertised_flavor_note_ids`. Reuses the existing autocomplete + create-on-the-fly chip UX from `coffee_form.html`. SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN` — hand-edit the migration with `op.execute()` per the established pattern in `app/migrations/versions/p4_shared_catalog.py`.

- **D-05:** Brew method → `brew_method TEXT NULL` free-text. No enum, no FK. High-variance, low-current-analytics-value field; mobile-fastest. Phase 19 AI prompt can read it as free-form signal. Defer enum / lookup until a query needs it.

### Claude's discretion — column shapes locked to brew-session parity

- `cafe_name TEXT NOT NULL` — the only required field besides rating. Free-text; cafe coffees do **not** FK to the shared `coffees` catalog (cafe entries are not household-catalog entries).
- `rating Numeric(3,2) NULL` — same type/precision as `brew_sessions.rating`; 0–5 in 0.25 steps; nullable for "still thinking" entries.
- `notes Text NOT NULL DEFAULT ''` — same shape as brew sessions.
- `photo_filename TEXT NULL` — single photo per log; reuses the existing `app/services/photos.py` EXIF-strip + magic-byte + thumbnail pipeline and the `coffee_snobbery_photos` volume. No second volume.
- `user_id BIGINT NOT NULL ondelete=RESTRICT` — same posture as `brew_sessions.user_id`. Hard-delete protection.
- `logged_at TIMESTAMPTZ NOT NULL DEFAULT now()` — auto-now on insert. **Editable** via the form for backfilling tastings (the user may log a cafe coffee a day late). Date + time granularity, matching brew sessions.
- Per-user visibility: every list/detail/edit/delete query filters by `current_user.id`. No household-shared view; cafe logs are personal, not catalog.
- Indices: `(user_id, logged_at DESC)` for the list query; GIN on `flavor_note_ids` for AI signature + flavor descriptor joins.

### List view & visual distinction (CAFE-03)

- **D-06:** Cafe logs live on the existing `/brew` Sessions page as a tab toggle. Page header becomes "Sessions" / "Cafe tastings"; same URL family `/brew?tab=cafe` (query param drives which list renders). No new nav slot; survives Phase 17's nav reshuffle (Admin off → AI on, still 4 slots) untouched. Active tab filters are tab-scoped.

- **D-07:** Cafe cards differ from brew session cards via **border-l-2 amber accent** (vs the espresso-600 brew accent) + a small coffee-cup icon in the corner (vs the kettle icon on brew). Subtle, mobile-readable, no badge clutter, theme-friendly in dark mode. The card body itself stays similar (coffee name, rating, flavor chips) — the discriminator is the accent + icon, not the layout.

- **D-08:** Empty state for the Cafe tastings tab is a **blank list** — no friendly copy, no sample entry, no watermark. Matches the minimalist aesthetic and follows the user's explicit preference. (Note: this is a deliberate divergence from Snobbery's other empty-state surfaces which typically carry a one-line hint; locked here at the user's request.)

### Claude's discretion — list view operational details

- Per-row Edit / Delete affordances use the **Phase 15.1 D-21 dual-button pattern**: `md:hidden` Edit (`hx-target="closest [data-row]"` / `outerHTML`) for mobile, `hidden md:inline-flex` Edit (`hx-target="#cafe-form-mount"` / `innerHTML` + `?layout=desktop`) for desktop. Server handler reads the `layout` query param via a per-router `_hydrate_form_context()` helper (mirroring the post-`a3a2f76` pattern across the five entity forms).
- Delete via POST with hidden `_method=DELETE` + confirmation step (HTMX 2.x convention; matches Phase 15.1 §3.2 guidance to avoid DELETE form-body).
- Filters on the Cafe tab limited to **rating range + date range**. No brand/origin filters at v1 — defer until usage demands them.
- Default sort: `logged_at DESC` (newest first), matching the Sessions tab.
- Pagination: mirror the Sessions tab pattern (cursor / page-based — planner reads the current `/brew` list code and matches; do not introduce a new pattern in this phase).
- Card-tap behavior on mobile: same as Sessions tab (expand inline or navigate to a read-only detail surface — planner mirrors current Sessions behavior).

### Entry point — the 20-second path (CAFE-01)

- **D-09:** Primary entry point is a third **"Quick rate"** button on the `/brew` page header, placed in the same flex row as the existing "Guided Brew" + "Log session" buttons. Two taps from launch (any page → Log tab → Quick rate). Survives Phase 17's nav reshuffle. Mirrors the existing button shape (Tailwind utility classes + HTMX progressive enhancement, CSP-safe).

- **D-10:** Form UX is a **dedicated `/cafe-logs/new` page** (and `/cafe-logs/{id}/edit` for CAFE-06 edit), full-page render extending `base.html`. Mirrors the brew form architecture (`/brew/new` is a dedicated page per Phase 5 D-01). Not a bottom-sheet modal (no modal pattern exists in the app today; designing one is Phase 21's call). Not an inline form-block (would break the autocomplete + photo-upload patterns already wired into the page-level form architecture).

- **D-11:** Form is **single-scroll, required fields on top**. First viewport: coffee name input (autofocused) + rating control + Save button (sticky-bottom or visible without scroll). Below the fold (in scroll order): brand/roaster autocomplete, origin country autocomplete, brew method free-text, flavor notes chip input, notes textarea, photo upload. Matches the brew form's single-scroll philosophy (Phase 5 D-04). No two-stage save, no expandable "More" accordion.

### Claude's discretion — entry-point operational details

- Routes: `GET /cafe-logs/new`, `POST /cafe-logs`, `GET /cafe-logs/{id}/edit`, `POST /cafe-logs/{id}` (update), `POST /cafe-logs/{id}` with hidden `_method=DELETE` (or `DELETE /cafe-logs/{id}` if a clean HTMX 2.x query-param pattern is preferred per the HTMX 2.x migration §3.2). Planner's call; both work.
- CSRF + autoescape are universal invariants; the form uses the same `<meta name="csrf-token">` + double-submit-cookie pattern as every other state-changing form.
- Photo upload: reuse `app/services/photos.py` (validated_image + EXIF strip + thumbnail). Same `coffee_snobbery_photos` volume.
- **No `brew_drafts`-style autosave-on-blur** at v1. The cafe form is short enough that ITP-loss risk doesn't warrant the server-side draft table. Localstorage form-restore is acceptable if cheap; not required.
- Autofocus on the coffee-name input on `/cafe-logs/new` load (the mobile keyboard pops immediately on tab-in).
- Post-save destination: `/brew?tab=cafe` (the Cafe tab of the Sessions page). On Cancel: same destination.
- The brew-form-mount / cafe-form-mount divs follow the Phase 15.1 D-13 pattern uniformly so the desktop edit path lands cleanly.

### AI integration mechanics (CAFE-04 policy locked, plumbing decided here)

- **D-12:** Extend `compute_input_signature` (analytics.py:353) by **appending cafe rows as a second list** in the SHA256 payload. Cafe row shape: `(cafe_log_id, float(rating), sorted flavor_note_ids, roaster_id, origin_country)`. Single payload, single SHA256, single signature column. `cafe_log_id` namespace differs from `coffee_id` so the row-identity collision risk is zero. Adding or editing a cafe log triggers the same nightly regen as adding/editing a brew session — no separate scheduler logic.

- **D-13:** `get_preference_profile` (analytics.py:78) dims that cafe logs feed:
  - **Origin:** YES. UNION `cafe_logs.origin_country` (per-user, rated, non-null) with `coffee_origins.country` (per-user via brew_sessions JOIN). Group on country, average rating, count sessions/logs, min ≥2 across the union.
  - **Roaster:** YES. UNION cafe roaster (via `roaster_id` JOIN) with brew roaster (via `Coffee.roaster_id` JOIN). Same min ≥2 across the union.
  - **Process:** NO. Cafe form doesn't capture process — user doesn't reliably know "washed/natural/honey" at a cafe. Stays brew-only.
  - **Roast level:** NO. Same reasoning. Stays brew-only.
  - **Flavor descriptors (get_flavor_descriptors, HOME-03):** YES. UNION `cafe_logs.flavor_note_ids` (rating ≥4.0, per-user) with `brew_sessions.flavor_note_ids_observed` (rating ≥4.0, per-user). Top-10 by total appearance count across the union.

- **D-14:** `get_top_coffees` (HOME-01, analytics.py:47) stays **brew-only**. Cafe coffees have no row in the `coffees` table by design; the query JOINs `Coffee` and there's no stable cafe-coffee identity to GROUP BY (free-text `cafe_name` would create duplicates like "Onyx Geometry" vs "Onyx, Geometry"). The card-tap target also dies (no `/coffees/{id}` detail page for cafe entries). CAFE-04 is satisfied by D-13's origin / roaster / flavor descriptor contributions; top-coffees is a separate surface. A future "Top cafe tastings" widget belongs in Phase 17 (IA restructure) or Phase 19 (AI page), not here.

- **D-15:** Cold-start gate counts cafe + brew together. New formula: `(brew_session_count + cafe_log_count) >= 3 AND distinct flavor_notes across both >= 5`. Consistent with CAFE-04's "subsequent AI runs reflect cafe taste data" — if cafe data is preference signal, it should also gate AI availability. Helps users who taste-out more than they brew at home reach AI faster. The cold-start meter UI (where it lives is Phase 17/19's call) updates its progress arithmetic accordingly.

### Sweet-spots exclusion (CAFE-05)

- **D-16:** `get_sweet_spots` (analytics.py:191) — grind, ratio, temperature, recipe sweet-spot queries — stays **brew-only, no UNIONs**. Cafe logs have no `recipe_id`, `dose`, `yield`, `water_temp_c`, or `brewer_id` fields by design (the user doesn't capture brew parameters at a cafe). The existing query bodies on the brew-only base don't need modification; just ensure the planner doesn't accidentally UNION cafe data here during the D-13 refactor. Add a one-line code comment on the sweet-spots functions: "Cafe logs are intentionally excluded — they have no brew-parameter fields (CAFE-05)."

### Claude's discretion — open implementation tactics for the planner

- Migration ordering: one new revision creating the `cafe_logs` table + GIN index. The Phase 15.1 origins/varietals migration must already be merged (dependency: Phase 15 + Phase 15.1).
- Whether to add an explicit `cafe_log` audit-log entry to the existing structlog audit channels — planner's call. Per CLAUDE.md the household-scale audit posture is "auth + admin events." A net-new cafe log isn't auth/admin — likely no audit-log row needed.
- The exact UNION SQL shape for D-13 (CTE vs derived table vs raw UNION ALL) — planner's call. SQLAlchemy 2.0 + psycopg 3 + Postgres 16 all support either; the established pattern in `analytics.py` is plain `select()` + `func.avg/count` per dim, so a CTE that yields a unified `(user_id, rating, group_dim, source_kind)` row may be cleaner than four parallel UNIONs.
- Whether the cold-start arithmetic in D-15 is computed in a single SQL query (count brews + count cafe + count DISTINCT flavor notes from both arrays) or two queries summed in Python — planner's call. Single SQL is preferred for atomicity but either works.
- Tab routing pattern for the `/brew?tab=cafe` toggle: pure server-side ?tab=cafe vs Alpine.js client-side tab swap. Planner's call; lean toward server-side ?tab= for CSP cleanliness and back/forward navigation correctness (Phase 4 filter-bar pattern uses `hx-get` + `hx-push-url` for exactly this).
- Whether to introduce a `cafe_logs` Pydantic schema in `app/schemas/cafe_log.py` (yes — established one-schema-per-model convention).
- Whether tests live in a new `tests/services/test_cafe_logs.py` + `tests/routers/test_cafe_logs.py` pair (yes — convention).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 16: Cafe Quick-Rate" — goal + 6 success criteria + dependency on Phase 15 + 15.1
- `.planning/REQUIREMENTS.md` § "Cafe Quick-Rate (CAFE)" lines covering CAFE-01..CAFE-06 — precise requirement wording
- `.planning/PROJECT.md` § "Active" — v1.2 milestone scope and the cafe quick-rate line item; § "Key Decisions" — signature-based AI regen as the cost control invariant
- `.planning/STATE.md` § "Decisions" — the override locks: "cafe ratings/flavor/origin DO feed preference derivation and AI signature; excluded only from brew-parameter sweet-spots" + "v1.2 open: cafe data model final approach (separate `cafe_logs` table recommended by research) — resolve at plan-phase 16" (resolved in D-01)
- `.planning/research/SUMMARY.md` § "Open Decisions" Decision 1 — the three-way data-model debate (Option C = separate table = chosen) + the analytics isolation contract
- `.planning/research/FEATURES.md` § cafe quick-rate — minimum-viable field set + competitor comparison context
- `.planning/research/ARCHITECTURE.md` § cafe_logs — the verified `brew_sessions.coffee_id NOT NULL RESTRICT` blocker on unified-table approaches
- `.planning/phases/15-v1-1-debt-cleanup/15-CONTEXT.md` — prior phase patterns to carry forward
- `.planning/phases/15.1-catalog-session-polish/15.1-CONTEXT.md` — the D-21 dual-Edit-button pattern (mobile inline + desktop mount), the create-on-the-fly autocomplete pattern for varietals (mirror for cafe roaster), the `coffee_origins` table (origin_country autocomplete source)

### CAFE-01..06 — code surfaces this phase introduces or extends

**New files (planner creates):**
- `app/models/cafe_log.py` — the new SQLAlchemy 2.0 model with `Mapped[...]` columns; mirrors the conventions in `app/models/brew_session.py`
- `app/schemas/cafe_log.py` — Pydantic v2 schema for create/update/form (one schema reused per coffees convention)
- `app/services/cafe_logs.py` — service layer: CRUD + draft-restore logic if added later
- `app/routers/cafe_logs.py` — `/cafe-logs` routes (new, list-on-Sessions-tab routing through the existing `/brew` router or a small new module — planner's call)
- `app/templates/pages/cafe_log_form.html` — full-page form (mirrors `pages/brew_form.html`)
- `app/templates/fragments/cafe_log_card.html` — list card (mirrors brew session card)
- `app/templates/fragments/cafe_log_row.html` — desktop table row + dual Edit button (mirrors Phase 15.1 D-21 row templates)
- `app/migrations/versions/<rev>_cafe_logs.py` — new migration with hand-edited GIN index for `flavor_note_ids`

**Existing files that MUST be modified:**
- `app/services/analytics.py:47` (`get_top_coffees`) — add the one-line "cafe excluded by design (CAFE-04 not applicable here)" comment; query body unchanged (D-14)
- `app/services/analytics.py:78` (`get_preference_profile`) — UNION cafe data into origin + roaster dims; leave process + roast_level brew-only (D-13)
- `app/services/analytics.py:158` (`get_flavor_descriptors`) — UNION cafe rated-4+ flavor_note_ids with brew (D-13)
- `app/services/analytics.py:191` (`get_sweet_spots`) — add a one-line comment confirming intentional exclusion (D-16); body unchanged
- `app/services/analytics.py:353` (`compute_input_signature`) — append cafe rows as a second payload list, SHA256 the combined payload (D-12)
- `app/services/analytics.py` — cold-start threshold computation (search the module for the `>= 3` and `>= 5` constants — if computed elsewhere, update wherever the gate lives) (D-15)
- `app/templates/pages/sessions.html` — header gets a third "Quick rate" button (D-09); add tab toggle "Sessions" / "Cafe tastings" (D-06)
- `app/routers/brew.py` — `/brew` GET list handler accepts a `tab` query param and dispatches to brew-list vs cafe-list (or delegates the cafe branch to the new cafe_logs router)
- `app/services/photos.py` — no changes needed; cafe form reuses the existing pipeline

**Pattern files to read before implementing:**
- `app/models/brew_session.py` — column shapes, the `flavor_note_ids_observed` BIGINT[] + GIN pattern (mirror for `cafe_logs.flavor_note_ids`), the FK directionality conventions (RESTRICT for user_id, SET NULL for optional FKs)
- `app/models/coffee.py` — the `advertised_flavor_note_ids` GIN-indexed array pattern + the SQLA-autogen GIN-emission caveat (must hand-edit migration via `op.execute()`)
- `app/services/flavor_notes.py` + `app/templates/fragments/coffee_form.html` (autocomplete fragment) — the established "create on the fly from autocomplete" UX pattern; mirror for the cafe roaster autocomplete (D-02)
- `app/services/coffees.py` — the per-router `_hydrate_form_context()` helper introduced in commit `a3a2f76` and finalized in Phase 15.1 D-21; cafe_logs router needs the same helper for the dual-Edit-button pattern
- `app/templates/fragments/coffee_form.html` — the chip-input + autocomplete pattern for `flavor_note_ids` (mirror for cafe form's flavor notes chip section)
- `app/templates/pages/brew_form.html` — the page-level form architecture that the cafe form mirrors (single-scroll, required fields top, optional below, Save sticky)
- `app/services/photos.py` — the EXIF strip + magic-byte + thumbnail pipeline that cafe photo upload reuses
- `app/services/encryption.py` — untouched by this phase; planner must not accidentally touch
- `app/services/scheduler.py` — untouched by this phase (the nightly AI signature-driven regen naturally picks up cafe contributions via D-12); planner must not accidentally touch

### Architectural patterns to follow
- `app/services/analytics.py` module docstring — the existing pitfalls (NULL rating exclusion, INNER JOIN guards, deterministic sort for signature) that the UNION'd cafe queries must respect
- HTMX 2.x conventions from CLAUDE.md § 3.2 (kebab-case `hx-on:event`, no `hx-ws` / `hx-sse` attributes, DELETE as POST with `_method=DELETE` recommended)
- Tailwind v3 + standalone CLI invariant (CLAUDE.md memory: `tailwind-v3-not-v4`) — `darkMode:'selector'`, `.dark` selectors, never `@custom-variant`
- CSP nonce invariant — define any new `htmx-indicator`-style styles in `tailwind.src.css` rather than relying on htmx's auto-injection (CLAUDE.md memory: `strict-csp-blocks-htmx-indicator`)

No external specs introduced during discussion — the decisions above are the contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`brew_sessions.flavor_note_ids_observed` BIGINT[] + GIN index pattern** (`app/models/brew_session.py:127-132` and the GIN-via-`op.execute()` migration note) — the cafe_logs.flavor_note_ids column directly mirrors this. Same Pydantic conversion, same chip-input UI binding, same `unnest()` pattern in analytics queries.
- **`coffees.advertised_flavor_note_ids` BIGINT[] + GIN index** (`app/models/coffee.py:73-77`) — second instance of the same pattern; confirms it as the established convention for many-flavor-notes-per-row.
- **`flavor_notes` shared catalog + create-on-the-fly autocomplete** (`app/services/flavor_notes.py` + `app/templates/fragments/coffee_form.html` autocomplete fragment + Phase 4 documented pattern) — D-04's cafe flavor notes chip input lifts this without modification.
- **`roasters` table with CITEXT UNIQUE name + Phase 4 autocomplete + create-on-the-fly** — D-02's cafe roaster_id FK + autocomplete reuses this. No new lookup table needed.
- **`coffee_origins.country` distinct values** (Phase 15.1 D-01 table) — D-03's origin_country autocomplete sources from these distinct values. No new countries table.
- **`compute_input_signature` SHA256-payload design** (`app/services/analytics.py:353-399`) — the existing pattern is "deterministic order + JSON serialize + SHA256." D-12 appends a second list to the same payload; no architectural change.
- **`app/services/photos.py` upload pipeline** — validated_image + EXIF strip + magic-byte + thumbnail + `coffee_snobbery_photos` volume. Cafe photo upload is a one-line call into this.
- **Phase 15.1 D-21 dual Edit button pattern** — `md:hidden` mobile inline + `hidden md:inline-flex` desktop mount, with server-side `?layout=desktop` query param driving the form's Save/Cancel target. Cafe_log_row.html lifts this verbatim.
- **`a3a2f76`-style per-router `_hydrate_form_context()` helper** — the established pattern for routing edit forms to mobile-inline vs desktop-mount. Cafe_logs router replicates this helper.

### Established Patterns

- **CITEXT for case-insensitive shared catalog names** — `coffees.name`, `roasters.name`, `flavor_notes.name`, `varietals.name`. If cafe_name ever becomes shared (it isn't at v1), it would follow this convention.
- **FK directionality:** RESTRICT for `user_id` (no hard delete from under user content), SET NULL for optional shared-catalog FKs (`roaster_id`), CASCADE for owned child rows. Cafe_logs.user_id = RESTRICT, cafe_logs.roaster_id = SET NULL.
- **Numeric(3,2) for ratings, 0-5 in 0.25 steps** — `brew_sessions.rating` convention; `cafe_logs.rating` mirrors exactly.
- **Single uvicorn worker invariant** — unchanged by this phase. APScheduler in-process locks remain single-process.
- **Server-side `?tab=` query param for tab toggles** — the Phase 4 filter-bar pattern uses `hx-get` + `hx-push-url` + `hx-target` for HTMX-driven URL-stateful UI; the Sessions/Cafe tab toggle follows the same pattern (D-06).
- **Mobile-first @ 375px hard rule** — the form layout + Sessions tab + cafe card must be tested at 375px before being declared done. Bottom nav <768px, top nav ≥768px.
- **`flavor_note_ids` arrays default to `'{}'` NOT NULL** — established in both `brew_sessions` and `coffees`. Mirror in `cafe_logs`.

### Integration Points

- **Analytics signature** (`compute_input_signature` at line 353) — the single integration point that wires D-12 into the existing nightly cadence. Removing the cafe-row append after this phase would silently break preference derivation; adding it must include the deterministic ordering rule (cafe_log_id ASC after brew rows).
- **Preference profile** (`get_preference_profile` at line 78) — three of the four dim queries (origin via CoffeeOrigin JOIN, roaster via Roaster JOIN, and the implicit "flavor descriptors" via `get_flavor_descriptors`) gain UNION'd cafe contributions. The other two (process, roast_level) stay brew-only. Planner audits the GROUP BY and HAVING clauses to ensure they survive the UNION shape.
- **Sweet-spots exclusion** (`get_sweet_spots` at line 191) — explicit one-line code comment as a guard; no body change. Prevents future contributors from "helpfully" UNIONing cafe data into a query that has no cafe-applicable fields.
- **Cold-start gate** (search `analytics.py` for `>= 3` and `>= 5` thresholds, or wherever the cold-start computation lives) — D-15 changes the count arithmetic only. UI text stays "your tasted-it-all data" or similar; planner picks copy.
- **Sessions page (`app/templates/pages/sessions.html`)** — gains a tab toggle + a third header button. Existing brew filter form is tab-scoped (mobile and desktop both); the cafe tab's filter form is a small new fragment with rating + date inputs only.
- **`/brew` GET list handler** (`app/routers/brew.py:71`) — accepts `tab=cafe` query param. Either dispatches to the new cafe_logs service inline, or HTMX-loads the cafe list fragment from the cafe_logs router. Planner's call; either is consistent with existing patterns.
- **`coffee-form-mount` div equivalent** — Sessions page gains a `cafe-form-mount` div above the tab content (Phase 15.1 D-13 pattern) for desktop edit landing.
- **No scheduler / encryption / search changes** — APScheduler nightly job picks up signature changes automatically (D-12); encryption is API-key-only and untouched; search index is brew/coffee-scoped at v1 and intentionally not extended.

</code_context>

<specifics>
## Specific Ideas

- **"Quick rate" button placement next to "Log session"** (D-09) — concrete: same flex row, same Tailwind utility classes, same HTMX progressive-enhancement shape. Visual parity with the two existing buttons; no FAB pattern, no modal pattern, no home-page CTA card.
- **Border-l-2 amber accent + cafe-cup icon** for visual distinction (D-07) — specific: `border-l-2` Tailwind class with an amber-500-ish accent for cafe vs the existing espresso-600 brew accent, and a small coffee-cup SVG icon where brew session cards show a kettle icon. Subtle, not loud.
- **Blank empty state** (D-08) — deliberate divergence from Snobbery's other empty-state surfaces (which typically carry a hint line). The user explicitly prefers blank. Capture this so a future contributor doesn't "helpfully" add hint copy.
- **No autosave-draft at v1** (D-11 Claude's discretion) — the form is short enough that ITP-loss isn't a meaningful risk; localstorage form-restore is acceptable but not required, and a `brew_drafts`-style server-side table is explicitly out-of-scope at v1.
- **Cafe cold-start counts toward the gate** (D-15) — specific arithmetic: `(brew_count + cafe_count) >= 3 AND distinct flavor_notes across both >= 5`. The UI meter (where it lives today) reflects the combined count.
- **`cafe_log_id` is in a separate namespace from `coffee_id`** so the D-12 signature append cannot collide — both are BIGINTs but the row-shape distinguishes them (a brew row has 5 fields including `coffee_id`; a cafe row has 5 fields including `cafe_log_id`). Sequential `ORDER BY` within each list segment + concatenation = deterministic.
- **Comment guards on sweet-spots queries** (D-16) — concrete one-liner: "Cafe logs are intentionally excluded — they have no brew-parameter fields (CAFE-05)." Same style as the Pitfall-N comments in the existing `analytics.py` module.

</specifics>

<deferred>
## Deferred Ideas

- **"Top cafe tastings" home card / widget** — considered for D-14 (synthetic-merge into `get_top_coffees`) and rejected. If wanted, design cleanly in Phase 17 (IA restructure of home) or Phase 19 (AI page). Requires a stable identity for cafe coffee names (normalization or FK) before it can rank meaningfully.
- **Cafe logs in global trigram search index** (Phase 10 surface) — not in Phase 16. Index expansion is its own scope; cafe entries become searchable when Phase 19 / 21 owns search rework or when usage demands it.
- **CSV import / export for cafe logs** — brew CSV is brew-session-only (Phase 5 + Phase 15.1 D-20). Cafe CSV would need its own format. Not in v1.2; revisit if users ask.
- **Brew method enum / lookup table** — D-05 keeps it free-text. Defer until an analytics query needs a constrained set (none does at Phase 16; possibly Phase 19 AI prompt-tuning).
- **Optional process + roast_level fields on cafe logs** — would let D-13 add those dims, but adds friction to the 20-sec path (user often doesn't know these at a cafe). Defer; revisit only if a user explicitly wants to capture estimated process/roast on cafe logs.
- **Bottom-sheet / modal form pattern** — considered for D-10 and rejected. The app has no modal pattern today; designing one is Phase 21 mobile-rework scope.
- **FAB (Floating Action Button)** — considered for D-09 and rejected. Phase 21 may design the cross-app FAB direction holistically; Phase 16 doesn't introduce the pattern unilaterally.
- **Home-page CTA card for "Quick rate"** — considered for D-09 and rejected. Phase 17 simplifies home; this card would conflict.
- **Server-side autosave-on-blur draft (brew_drafts-style) for cafe form** — considered for D-11 Claude's discretion and rejected. Short form, low ITP-loss risk. Revisit if users report drafts disappearing.
- **Cafe coffee → optional FK to `coffees` catalog when the cafe coffee IS in the household catalog** — considered for D-01 and rejected. Mixing identity types complicates queries. Cafe logs stay coffee-FK-free; if a user wants their household catalog enriched, they create a normal `coffees` row.
- **Separate cafe_logs photos volume** — considered for D-04 column shapes and rejected. Reuse the existing `coffee_snobbery_photos` volume.
- **Per-user provenance on cafe roaster autocomplete** (who added what roaster) — considered and rejected. Shared catalog last-write-wins per Phase 15.1 D-09. Cafe logs piggyback the same policy.
- **Audit-log entries on cafe log create/edit/delete** — Claude's discretion (likely no audit entry). Household-scale audit posture is auth + admin events; cafe log churn is user-content noise.
- **Two-stage save ("save quick, then add details")** — considered for D-11 and rejected. Adds friction for users who want details up front. Single-scroll handles both speeds.
- **Inline "add new coffee from brew form" carryover** (STATE.md Pending Todos line) — re-evaluated. Cafe quick-rate is a different path; it does NOT enrich the shared coffee catalog. The original todo (about brew form prefill) remains owned by a future brew-form polish phase, not Phase 16.

None of the above are dropped — they are captured for the phases or future iterations that own that surface.

</deferred>

---

*Phase: 16-cafe-quick-rate*
*Context gathered: 2026-05-27*
