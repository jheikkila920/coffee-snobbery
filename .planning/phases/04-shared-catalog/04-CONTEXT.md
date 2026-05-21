# Phase 4: Shared Catalog - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

The first feature surface. Five shared-catalog entities + bags + photo upload + the universal Pydantic-v2 form-validation pattern that every Phase-4+ router will follow. No per-user data yet — that's Phase 5.

In scope:
- `roasters` table + CRUD: `name` (citext unique), `location`, `website` (validated URL), `notes`. Autocomplete-on-create from inside the coffee form. CAT-01.
- `flavor_notes` table + CRUD: `name` (citext unique lowercased), `category` enum (`fruit`, `floral`, `sweet`, `chocolate`, `nutty`, `spice`, `savory`, `fermented`, `other`). Autocomplete-on-create from inside the coffee form. CAT-02.
- `coffees` table + CRUD: shared (no `user_id`), soft-delete via `archived` bool, `advertised_flavor_note_ids` array referencing `flavor_notes`. Filter UI (roaster / country / process / archived). Desktop table ↔ mobile card-list at 768px. CAT-03, CAT-07.
- `equipment` table + CRUD: `type` enum (`brewer`, `grinder`, `kettle`, `scale`, `water_filter`, `other`), `brand`, `model`, `notes`. Soft-delete via `archived`. List grouped by type. Usage count visible (count of brew sessions referencing it — schema FK in Phase 5; Phase 4 ships the column as 0). Archive forced (not delete) once Phase 5 sessions exist. CAT-05.
- `recipes` table + CRUD: JSONB `steps` array, `dose_grams`, `water_grams`, `water_temp_c`, `grind_setting` (free-form text), soft-delete via `archived`. Step builder UI (Alpine-local). Vertical pour-timeline preview. Duplicate-recipe action. CAT-06.
- `bags` photo-upload + CRUD UI: the `bags` table already exists (shipped in Phase 0 from CAT-04); Phase 4 adds the missing FK `bags.coffee_id → coffees.id`, builds the CRUD UI nested under the coffee detail page ("Open new bag of this coffee" action), and ships the photo pipeline. CAT-08.
- Photo pipeline (SEC-07): client-side Canvas downscale to ~2000px max edge → server-side magic-byte check → Pillow decode + re-encode (polyglot defense, SEC-4) → EXIF strip → resize ≤1600px wide → 400px thumbnail → save under `coffee_snobbery_photos` named volume. Reject >5MB before buffering.
- Photo serving route at `app/routers/photos.py` (NOT a `StaticFiles` mount): auth-gated, opaque UUID filenames, `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`. Unauthenticated requests return 404 (not 403).
- Photo lifecycle: synchronous unlink on photo replace and on bag hard-delete. Nightly orphan-sweep job (one-shot APScheduler entry to be wired alongside Phase 8's backup job; in Phase 4 we ship the standalone sweep function `app/services/photos.py::sweep_orphans()` and a callable management command, even if scheduler registration waits for Phase 8).
- Universal **Pydantic v2 form-validation pattern** (SEC-06): every state-changing route accepts a form schema with explicit numeric ranges (`Field(ge=0, le=100)` for temps, sensible ranges for dose/water/grams). On validation failure, server returns the inline form fragment (HTTP 200) with the user's values preserved and inline field-level error messages. This is the template Phase 5+ form routes consume.

Out of scope (belongs in later phases):
- `brew_sessions` table + per-user logging surface — Phase 5 (BREW-*).
- Tap-on-stars rating control + tag input for observed flavor notes — Phase 5 (BREW-04, BREW-03). Phase 4's flavor-note CRUD ships the underlying vocabulary; the tag-input widget that consumes it lives in Phase 5.
- Home page analytics / preference profile — Phase 6.
- AI service consuming the catalog — Phase 7.
- Nightly orphan-photo sweep **scheduler registration** — Phase 8 (the function ships in Phase 4; APScheduler wiring lands alongside the other nightly jobs in Phase 8).
- Admin user/credentials/settings UI — Phase 9.
- Global search across the catalog — Phase 10.
- Bottom-tab nav / PWA manifest / dark-mode polish — Phase 11. Phase 4 ships templates that work at 375px (card-list collapse) but the persistent bottom nav frame is Phase 11.
- Full per-router unit test suite — Phase 12.

9 requirements mapped: CAT-01, CAT-02, CAT-03, CAT-05, CAT-06, CAT-07, CAT-08, SEC-06, SEC-07.

</domain>

<decisions>
## Implementation Decisions

### CRUD interaction pattern

- **D-01: HTMX fragments throughout.** All five entity surfaces are HTMX-driven. The list page is the canonical surface. POST returns a row fragment that's `hx-swap`'d into the list; OOB swaps update count badges. No classic POST→303 inside the catalog (that pattern stays reserved for auth surfaces — Phase 2 D-05). The CSP-strict Alpine + HTMX 2.0.10 stack from Phase 1 is the substrate; no `hx-on:` inline handlers (Phase 1 D-04), no `|safe` (Phase 1 SEC-05).
- **D-02: Add/Edit form lives as an inline expand on the list page, not as a modal or separate page.** Click "Add coffee" → `hx-get` fetches the form fragment which renders as a top-of-list expandable row. Saving `hx-swap`'s the new row into the list, form collapses. Edit click → `hx-get` replaces that row with an editable form. Rationale: stays in one viewport at 375px (form sits at top, list below); avoids modal scaffolding (focus trap, ESC handling, full-screen-sheet-vs-dialog branching that PROJECT MOB-08 demands). Modal pattern is reserved for Phase 11's polish pass when MOB-08 lands properly.
- **D-03: Filter state uses `hx-push-url` on every filter change.** Selecting roaster / country / process / archived fires `hx-get` against `/coffees?roaster=Onyx&archived=false` (and equivalents per entity) AND updates the browser URL via `hx-push-url`. Browser back/forward replays filters; users bookmark and share filtered views. PITFALL HX-2 (bfcache fragment leak) is already mitigated by Phase 1's `FragmentCacheHeadersMiddleware` (Phase 1 D-11): every `HX-Request: true` fragment carries `Cache-Control: no-store` + `Vary: HX-Request`. The list-fragment endpoints rely on that middleware; no per-route opt-in needed.
- **D-04: Form validation errors re-render the whole inline form fragment with field-level errors.** Server returns HTTP 200 with the form fragment (NOT 422 — 200 lets HTMX swap cleanly). Pydantic ValidationError is caught, the user's submitted values are preserved, inline error messages render next to each invalid field (red helper text under the field). This pattern carries forward to Phase 5 brew-session forms and Phase 9 admin forms. SEC-06 numeric-range constraints (`Field(ge=..., le=...)`) are the validation source of truth; HTML5 `min`/`max`/`step` attributes are advisory only (browser convenience), Pydantic is the authoritative check.

### Photo upload + serving pipeline

- **D-05: Client-side Canvas downscale to ~2000px max edge before POST.** Vanilla JS in `app/static/js/photo-upload.js` (~80 LOC). Reads EXIF orientation client-side to render upright, downscales to max edge 2000px via `<canvas>`, re-encodes as JPEG quality ~0.85, then submits the smaller blob through the form. Phone cameras at 4000×3000+ go from 4–8MB → ~500KB–1MB. Server **still** re-encodes (the SEC-4 polyglot defense doesn't trust client bytes); the client downscale is a UX/bandwidth optimization, not a security measure. Form must work without JS (fallback: server accepts the raw bytes and handles the full resize on its own), but the JS-disabled path is best-effort.
- **D-06: Auth-gated photo serving route with opaque UUID filenames.** `GET /photos/{uuid}.jpg` in `app/routers/photos.py`. Requires authenticated session (Phase 2's `SessionMiddleware` populates `request.state.user`); non-authenticated requests return **404, not 403** (don't leak existence). Filename is `uuid4().hex + ext`. Response headers: `Content-Type: image/jpeg|png|webp` (explicit, never sniffed), `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`. Matches ROADMAP Phase 4 success #4 verbatim. NOT a `StaticFiles` mount.
- **D-07: Photo lifecycle — synchronous unlink on replace and on bag hard-delete; nightly orphan-sweep function ships now (scheduler registration waits for Phase 8).** Replacing a bag photo: old file unlinked in the same request after the new file is fsync'd and the DB row updated (write-new-then-delete-old; never delete-then-write so a crash never destroys the only copy). Bag soft-delete (`archived=true`) keeps the photo (history matters). Bag hard-delete (rare; planner picks if it's even surfaced in v1) unlinks. The orphan-sweep function lives in `app/services/photos.py::sweep_orphans()` and walks the photos volume diff'd against `bags.photo_filename` to delete unreferenced files; Phase 8 wires it into APScheduler.
- **D-08: Photos attach to bags only — coffees have no separate photo column at v1.** CAT-08 spec is explicit ("bag photo upload"). The coffee list / detail views may surface the latest bag's thumbnail as a visual cue (planner picks; small enhancement, optional), but the schema only adds a `photo_filename` column to `bags`, not to `coffees`. Keeps the lifecycle simple — one entity owns the photo, one place to manage it.

### Recipe step builder mechanics

- **D-09: Alpine.js local array, single JSON submit on save.** Step builder is a CSP-build Alpine component (registered via `Alpine.data('recipeStepBuilder', factory)` in `app/static/js/alpine-components/recipe-step-builder.js` per Phase 1 D-01). State = `steps: [{water_grams, time_seconds, label}, ...]`. Add / remove / reorder are pure Alpine — zero server round-trips during editing. Live cumulative-water + time-offset readouts are Alpine-computed. On submit, the array serializes into a hidden input as JSON; the server-side Pydantic schema validates the array and writes the `steps` JSONB column in one transaction. No draft-state table, no per-step round-trips.
- **D-10: A step captures `water_grams` (cumulative target) + `time_seconds` (elapsed time at that target) + `label` (free-text, e.g., "Bloom" / "Main pour" / "Final pour").** Three fields. Live readout shows delta-water + delta-time per step alongside the cumulative numbers. No pour-duration column, no agitation/technique enum at v1 — those are deferred (see `<deferred>`).
- **D-11: Vertical bar pour-timeline preview with proportional segments.** Matches ROADMAP Phase 4 success #3 verbatim. Each step is a colored segment whose height is proportional to its `time_seconds` slice. Cumulative water labeled at each segment break. Reads top-to-bottom like the actual brew. Mobile-friendly (stays narrow at 375px). Implemented in the same Alpine component as the step builder — segment heights are computed reactively from the `steps` array.
- **D-12: Duplicate-recipe is an immediate server-side copy + HTMX redirect to the new recipe's edit form.** "Duplicate" button appears on each row in the recipes list and on the recipe detail view. Click → `hx-post /recipes/{id}/duplicate` → server INSERTs a deep copy (new `id`, `name = "{original_name} (copy)"`, `archived=false`, fresh timestamps), then returns an `HX-Redirect` response that takes the user to the new recipe in edit mode. Predictable; matches spec phrase "duplicate-recipe action". Phase 5 sessions are not duplicated (they're per-user logs, not recipes).

### Autocomplete-on-create UX

- **D-13: From inside a parent form, an unmatched typed value surfaces an explicit "+ Create new" option in the autocomplete dropdown.** HTMX-driven autocomplete on the roaster and flavor-note inputs inside the coffee form. `hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"` (cancels in-flight on new keystroke, per PITFALL HX-4 pattern). Server returns matching rows; if none match the exact typed string, the response prepends a "+ Create new roaster: 'Onyx'" (or "+ Create new flavor note: 'nectarine'") option. Discoverable; no silent inserts; no typos becoming permanent rows.
- **D-14: PITFALL HX-3 dodge — no `hx-swap-oob` on the flavor-notes datalist. Use `hx-get` on field focus to refresh.** Each autocomplete-aware input has `hx-trigger="focus once from:closest .field"` (or equivalent) that fires `hx-get /flavor-notes/datalist` (and `/roasters/list`) returning the current full list of options. Creating a new flavor note or roaster does NOT OOB-swap into other open datalists; the next focus on each datalist re-fetches. Eliminates the HX-3 duplicate-ID race entirely. Matches PITFALL HX-3's preferred mitigation verbatim.
- **D-15: Clicking "+ Create new …" opens a mini-modal with the entity's full editable fields.** User choice over Claude recommendation (name-only); user wants completeness at creation time, not a follow-up nag. Modal scope per entity:
  - **Roaster:** `name` (required) + `location` (optional text) + `website` (optional, validated URL via Pydantic `HttpUrl`) + `notes` (optional textarea).
  - **Flavor note:** `name` (required) + `category` dropdown (required, the 9-value enum from CAT-02).
  Modal submit POSTs to `/roasters` or `/flavor-notes`, server inserts and returns the new row + an `HX-Trigger` response header carrying e.g. `roaster-created` so the parent coffee form's roaster field can pre-select the new value. Modal closes on success; ESC closes without saving; backdrop click closes without saving. Implemented as an Alpine component registered globally so both autocomplete fields can hand off to it.
- **D-16: New entity creation pre-selects in the parent field after modal close.** When the modal's POST succeeds, the response carries the new row's id; an Alpine listener on the parent form picks up the `HX-Trigger` event payload (`{ roaster_id, name }`) and sets the parent form's `roaster_id` hidden input + displays the name in the visible field. No second user action required.

### Claude's Discretion

- **Exact `coffees` schema column choices** — `country`, `process`, `roast_level`, `origin`, `varietal`, `notes`, etc. The base spec (`docs/snobbery-gsd-prompt.md`) and existing analytics signatures (Phase 6 will derive preference profiles from these) lock the field set. Planner enumerates exact columns + nullability via SQLAlchemy `Mapped[...]` per the Phase-0-established pattern.
- **Exact `process` enum values** — washed / natural / honey / anaerobic / experimental / unknown is the typical set; planner picks final values + decides Postgres ENUM vs text+CHECK (Phase 3 D-01 set a precedent for text+CHECK as the more agile choice). Same call for `roast_level` (light / medium-light / medium / medium-dark / dark / unknown) and `equipment.type` (brewer / grinder / kettle / scale / water_filter / other — CAT-05 already names these).
- **Whether to use Postgres ENUM types or text+CHECK constraints for the enums** — Phase 3 D-01 ("text + CHECK is more agile") is the established precedent; planner follows unless a strong reason to deviate exists.
- **Sort order defaults on each list** — coffees: alphabetical by name? most recently added first? planner picks based on what serves a returning user best. Same for recipes, equipment, roasters.
- **Whether the coffee list shows the latest bag thumbnail** — small visual enhancement under D-08; not required, planner picks whether the extra subquery + template clutter earns its keep.
- **`archived=true` UX surface** — toggle button to "show archived" on each list, separate `?archived=true` URL state, or both. Planner picks; the filter spec lists archived as one of the four filter dimensions, so it's a first-class filter, not a hidden mode.
- **Exact NULL-handling on `coffees.advertised_flavor_note_ids`** — empty array vs NULL. Planner picks; empty array is usually cleaner for downstream queries.
- **How the coffee detail page surfaces "open new bag of this coffee"** — button on the coffee detail page that opens an inline bag form (per D-02 inline-expand pattern), or a dedicated `/coffees/{id}/bags/new` route. Planner picks; the inline-expand pattern is the locked default.
- **Hard-delete vs soft-delete for entities that have NO downstream references** — CAT-05 mandates archive (not delete) when an equipment row is referenced by a brew session. At Phase 4 there are no brew sessions yet, so technically any equipment row can be hard-deleted. Planner picks the cleaner default — recommendation: archive-only from day one so the rule doesn't change once Phase 5 lands.
- **Modal close-on-Escape / focus-trap depth** — D-15 mentions ESC and backdrop-click; planner decides whether to implement a full focus-trap (heavier Alpine component) or rely on browser tab order. At household scale, browser default is probably fine.
- **Mobile breakpoint for table→card-list collapse** — 768px per ROADMAP. Planner verifies the Tailwind `md:` breakpoint matches (Tailwind default `md` = 768px, so this aligns).
- **Photo MIME validation depth** — magic-byte signature check on first 8 bytes (JPEG: `FF D8 FF E0/E1`, PNG: `89 50 4E 47`, WebP: `52 49 46 46 … 57 45 42 50`), then Pillow decode. Whether to use `puremagic`/`filetype` library or hand-roll the signature check — planner picks; hand-roll is fine for three formats.
- **HEIC support** — iOS Safari sometimes uploads HEIC even when the user thinks it's JPEG. Pillow needs `pillow-heif` to decode. Planner decides whether to add the dep (small) or reject HEIC with a friendly error and let the client downscale convert it to JPEG (the Canvas re-encode at D-05 will naturally produce JPEG, so the JS path side-steps HEIC; only the JS-disabled fallback would hit this).
- **Whether to ship a `/photos/{uuid}/thumb` thumbnail-serving variant or serve from a fixed filename suffix** — e.g., `photo-{uuid}.jpg` and `photo-{uuid}-thumb.jpg`. Planner picks; suffix is simpler.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` §"Requirements / Data Model — Shared Household Catalog" (verbatim scope for roasters, flavor notes, coffees, equipment, recipes), §"Coffee Catalog UX" (bag photo upload pipeline + filters), §"Key Decisions" row "Add `bags` table to v1 Foundation (separate from coffees catalog)" (the FK gets added in Phase 4), §"Architectural invariants" ("Coffees, equipment, recipes, roasters, flavor notes are shared across users"; "CSRF on all state-changing forms"; "Security headers on every response"; "Mobile-first").
- `.planning/REQUIREMENTS.md` §"Shared Catalog" (CAT-01, CAT-02, CAT-03, CAT-05, CAT-06, CAT-07, CAT-08 — verbatim) and §"Security Hardening" (SEC-06 Pydantic v2 form validation pattern, SEC-07 image upload validation). CAT-04 stays owned by Phase 0; Phase 4 adds the FK constraint that Phase 0 deferred.
- `.planning/ROADMAP.md` §"Phase 4: Shared Catalog" — goal sentence + 5 success criteria + Notes (carries SEC-4 polyglot-upload defense; CAT-04 bag CRUD UI lands as derived task in this phase; HX-3 datalist OOB footgun → Phase 4 D-14 resolves this verbatim).
- `.planning/STATE.md` — current decision accumulator. No Phase-4-specific plan-phase research flag carried forward; the three live flags belong to Phases 1, 7, 10, 11.

### Prior phase context (decisions Phase 4 inherits)
- `.planning/phases/00-foundation/00-CONTEXT.md` — `bags` table already exists with `coffee_id BIGINT NOT NULL` and NO FK constraint (deferred to Phase 4 per the Phase 0 model docstring at `app/models/bag.py:5-9`); Postgres extensions `citext`, `pg_trgm`, `unaccent` installed in `0001_initial.py`; the SQLAlchemy `Mapped[...]` model pattern is the project convention; sync DB session via `app/db.py::SessionLocal`.
- `.planning/phases/01-middleware/01-CONTEXT.md` D-01..D-06 (CSP-strict — no `unsafe-eval`, no `'unsafe-inline'` for scripts, no `hx-on:` inline handlers; Alpine CSP build registered via `Alpine.data('name', factory)` in `app/static/js/alpine-components/*.js`), D-11 (`FragmentCacheHeadersMiddleware` already emits `Cache-Control: no-store + Vary: HX-Request` on `HX-Request: true` responses — Phase 4's list-fragment routes rely on this without per-route configuration), D-12 ("template-level conventions enforced in Phase 4+ code review" — the no-`|safe`-in-pages and no-`hx-on:`-in-pages grep tests already cover Phase 4 templates), D-17 (slowapi default in-memory storage; Phase 4 routes are NOT rate-limited).
- `.planning/phases/02-auth/02-CONTEXT.md` D-09 (`request.state.user` is the full `User` row, not a stub dict — Phase 4 routes reference `user.id`, `user.username`, `user.is_admin` directly), D-12 (form POSTs use `CSRFFormFieldShim` to hoist the hidden `X-CSRF-Token` field into the header before `CSRFMiddleware` — Phase 4 catalog forms include the same hidden input as `pages/setup.html` and `pages/login.html`), D-14 (`require_admin` lives in `app/dependencies/auth.py` — Phase 4 introduces `require_user` if it's not already present, in the same module).
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` D-07 (sync DB session via `app/db.py::SessionLocal` is the catalog pattern); the services-split convention (primitives vs domain logic) — Phase 4 may split `app/services/catalog.py` into per-entity modules at planner discretion (`app/services/coffees.py`, `app/services/roasters.py`, etc.) or keep one file; the Phase 2 services pattern (kwargs API, audit-event emission) is the structural template.

### Research output
- `.planning/research/PITFALLS.md` §2 — HX-3 (`hx-swap-oob` flavor-notes datalist duplicate-ID footgun — Phase 4 D-14 resolves with hx-get on focus; preferred fix per the pitfall doc), HX-4 (350ms debounce + `hx-sync="this:replace"` + min 2-char threshold for HTMX-driven autocomplete — Phase 4 D-13 applies the same pattern); §5 — SEC-4 (polyglot upload defense: re-encode after Pillow decode strips trailing data; serve with `nosniff` + `Content-Disposition: inline` — Phase 4 D-06 + D-07 implement this verbatim); §6 — MX-1 (16px minimum font-size on form inputs to prevent iOS auto-zoom — global CSS rule in `app/static/css/custom.css` lands in Phase 5 per ROADMAP; Phase 4 templates can use `text-base` (16px) on form inputs as the explicit class).
- `.planning/research/STACK.md` §1 — Pillow `>=12.2,<13` (magic-byte + Pillow re-encode + EXIF strip), Pydantic `>=2.13,<3.0` (form schemas with `Field(ge=..., le=...)` numeric ranges), SQLAlchemy `>=2.0.49,<2.1` (typed `Mapped[...]` columns, `select()` constructs), Alembic `>=1.18,<2.0` (autogenerate detects new `Mapped[...]` models), `python-multipart >=0.0.28,<0.1` (form parsing + multipart photo upload — already installed via FastAPI). §3.3 — sync engine for Phase 4 CRUD via `psycopg://` URL.

### Operational + spec
- `CLAUDE.md` §"Stack invariants" (Jinja2 autoescape on, Tailwind utility classes, Alpine inline + vanilla JS in `app/static/js/`, Pydantic v2 for request/response/form schemas, SQLAlchemy 2.0 style with `Mapped[...]`), §"Architectural invariants" ("Coffees, equipment, recipes, roasters, flavor notes are shared across users", "Mobile-first: any UI change tested at 375px viewport", "CSRF on all state-changing forms", "Security headers on every response"), §"Things to never do silently" (no `|safe` on user content; never disable CSRF/CSP).
- `docs/snobbery-gsd-prompt.md` — original product brief; the catalog requirements and field intent originate here. CLAUDE.md and `.planning/` docs are authoritative where they diverge.

### External library docs (planner verifies via Context7 in plan-phase)
- `pillow` (PyPI `>=12.2,<13`) — `Image.open()` / `Image.verify()` / `Image.convert()` / `Image.save(format=...)` API; EXIF strip via `image.info` clearing + `image.save` re-encode; `Image.thumbnail()` for in-place resize; HEIC support gating via `pillow-heif` (optional).
- `pydantic` (PyPI `>=2.13,<3.0`) — `BaseModel` + `Field(ge=..., le=..., min_length=..., max_length=...)`, `HttpUrl` type for roaster website validation, `ValidationError` handling in the form-fragment re-render path.
- `sqlalchemy` (PyPI `>=2.0.49,<2.1`) — `Mapped[...]` typed columns, `mapped_column(CITEXT(), unique=True)`, `mapped_column(JSONB)` for `recipes.steps`, `mapped_column(ARRAY(BigInteger))` for `coffees.advertised_flavor_note_ids`, `select()` + `update()` constructs.
- `alembic` (PyPI `>=1.18,<2.0`) — autogenerated migration detects the new `Mapped[...]` models; planner reviews the autogenerate output before committing.
- `htmx` 2.0.10 (CDN, already loaded in `base.html`) — `hx-get`, `hx-post`, `hx-swap=innerHTML|outerHTML|beforebegin|afterend`, `hx-target`, `hx-push-url=true`, `hx-trigger="input changed delay:350ms[target.value.length >= 2]"`, `hx-sync="this:replace"`, `HX-Redirect` response header for D-12.
- `alpinejs` CSP build 3.14.9 (CDN, already loaded in `base.html`) — `Alpine.data('name', factory)` registration pattern (Phase 1 D-01), `x-data`, `x-bind`, `x-show`, `x-for`, `x-on:click="..."` (CSP build only accepts declarative expressions referring to registered components — no inline arbitrary JS).

### Existing code (read before changing)
- `app/models/bag.py` — already shipped from Phase 0 with `coffee_id BIGINT NOT NULL` and NO FK constraint. Phase 4 ADDs the FK constraint (`ForeignKey("coffees.id", ondelete="RESTRICT")` — once a session references a bag, the coffee can't be hard-deleted; planner confirms `ondelete` choice). Phase 4 also adds `photo_filename: Mapped[str | None]` to support CAT-08.
- `app/models/base.py` — `Base` declarative base for the new `Coffee`, `Roaster`, `FlavorNote`, `Equipment`, `Recipe` models.
- `app/models/__init__.py` — re-export new models so Alembic autogenerate sees them.
- `app/db.py` — `SessionLocal` (sync) is what Phase 4 routes consume; `AsyncSessionLocal` reserved for auth path only.
- `app/dependencies/auth.py` — Phase 2 introduced `require_admin`; Phase 4 either reuses or introduces `require_user` (raises 302 → `/login` for anonymous; planner picks 302-vs-401 based on whether the client is HTMX or full-page).
- `app/csrf.py` — `CSRF_COOKIE_NAME`, `CSRF_HEADER_NAME`, `CSRFFormFieldShim`. Phase 4 forms include the hidden `<input name="X-CSRF-Token">` like `pages/setup.html` does; the shim handles the rest.
- `app/main.py` — middleware stack already wired (Phase 1 D-17 + Phase 2 D-15 lock the order). Phase 4 adds new routers via `include_router`. No middleware changes.
- `app/templates/base.html` — base layout with CSP nonce, CSRF meta, HTMX + Alpine CDN, dual theme-color. Phase 4 templates extend it. Phase 4 introduces `app/templates/fragments/` (currently empty) — entity-row, form-fragment, datalist templates land here.
- `app/templates/pages/setup.html`, `app/templates/pages/login.html` — reference templates for the CSRF hidden-input pattern and inline-form-error rendering.
- `app/static/css/custom.css` — destination for any utility-class-insufficient CSS (project convention). Phase 4 likely doesn't add custom CSS; the 16px form-input rule (MX-1) lands in Phase 5 per ROADMAP.
- `app/static/js/htmx-listeners.js` — global HTMX configuration (Phase 1 D-04; loads after htmx core, sets `htmx.config.allowEval=false`). Phase 4 adds `app/static/js/photo-upload.js` for D-05 client downscale and Alpine components in `app/static/js/alpine-components/*.js` (e.g., `recipe-step-builder.js`, `mini-modal.js`).
- `app/events.py` — event-name constants. Phase 4 extends with `CATALOG_COFFEE_CREATED`, `CATALOG_COFFEE_UPDATED`, `CATALOG_COFFEE_ARCHIVED`, parallel for the other four entities + `CATALOG_BAG_CREATED`, `CATALOG_BAG_PHOTO_UPLOADED`, `CATALOG_BAG_PHOTO_DELETED`, `CATALOG_PHOTO_ORPHAN_SWEPT`. Planner picks exact names following Phase 1 D-14 taxonomy (`<area>.<action>`).
- `app/services/__init__.py` — package marker. Phase 4 adds catalog services (planner picks: one `catalog.py` or per-entity modules `coffees.py`, `roasters.py`, `flavor_notes.py`, `equipment.py`, `recipes.py`, `bags.py`, `photos.py`). Recommendation: per-entity for clarity; Phase 9 admin routes will reuse them.
- `app/migrations/versions/` — new migration creates the five catalog tables, adds the FK + `photo_filename` column to `bags`, creates the photos volume directory if needed. Single migration file per Phase 0 D-02 ("one migration per logical change").

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all already on disk from Phases 0–3)
- **`app/templates/base.html`** — already loads HTMX 2.0.10, Alpine 3.14.9 CSP build, the CSP nonce + CSRF meta. Phase 4 templates extend it.
- **`app/csrf.py::CSRFFormFieldShim`** — Phase 2 wired this into `app/main.py`. Every Phase 4 form template includes `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">` exactly like `pages/setup.html:10`.
- **`app/middleware/FragmentCacheHeadersMiddleware`** — Phase 1 D-11. Phase 4's HTMX list-fragment routes get `Cache-Control: no-store + Vary: HX-Request` for free.
- **`app/dependencies/auth.py::require_admin`** — Phase 2 D-14 shipped this. Phase 4 routes for catalog CRUD use either `require_user` (existing or new) or no dep (every authenticated user can edit the shared catalog).
- **`app/db.py::SessionLocal`** — sync sessionmaker with the Phase 0 pool knobs. Phase 4 catalog services use this.
- **`app/services/settings.py`** — Phase 3's typed reader. Phase 4 doesn't read settings directly, but the pattern (sync, cached, audit-event-emitting) is the template if Phase 4 adds catalog-level toggles.
- **Postgres extensions** — `citext`, `pg_trgm`, `unaccent` are installed (Phase 0 `0001_initial.py`). `Roaster.name`, `FlavorNote.name`, `Coffee.name` all use `CITEXT()` for case-insensitive uniqueness.

### Established Patterns (set by Phases 0–3; Phase 4 follows)
- **"Cross-cutting → middleware; feature surface → router; stateful logic → service"** (Phase 0). Phase 4 lands `app/routers/coffees.py`, `app/routers/roasters.py`, etc. plus per-entity service modules.
- **"All env reads go through `app/config.py`"** (Phase 0). Phase 4 doesn't add env vars unless planner identifies one (e.g., `PHOTO_MAX_BYTES` — probably stays a constant in `app/services/photos.py`).
- **"Migrations are autogenerated from `Mapped[...]` models"** (Phase 0). Phase 4 adds five new models + the FK + `photo_filename` column; alembic autogenerate produces the migration.
- **"Audit events are structured-logger calls"** (Phase 1 D-14). Phase 4 emits `catalog.<entity>.<action>` events at the service-layer write paths.
- **"Sync DB for the catalog surface"** (Phase 3 D-07). Phase 4 commits.
- **"CSP-strict: no `unsafe-eval`, no `hx-on:` inline handlers, no `|safe`"** (Phase 1 D-01..D-06). Phase 4 templates are subject to the grep tests; Alpine components are registered via `Alpine.data(...)` only.
- **"Form POSTs use 303 See Other to redirect"** (Phase 2 D-05) — but only for auth surfaces. Phase 4 D-01 deviates: HTMX fragments return 200 with HX-swap'd row fragments; HTMX-redirect (HX-Redirect header) is used only for cross-page navigations like D-12 duplicate-recipe.

### Integration Points
- **`app/main.py`** — register the five new routers (`coffees`, `roasters`, `flavor_notes`, `equipment`, `recipes`, `photos`, `bags`) via `app.include_router(...)`. No middleware changes.
- **`app/migrations/versions/`** — new file (e.g., `p4_shared_catalog.py`) creates the five catalog tables + adds the FK constraint on `bags.coffee_id` + adds `bags.photo_filename` column. Single migration per Phase 0 D-02.
- **`app/models/`** — NEW files: `coffee.py`, `roaster.py`, `flavor_note.py`, `equipment.py`, `recipe.py`. Update `bag.py` to add the FK + `photo_filename`. Register all in `__init__.py`.
- **`app/routers/`** — NEW files: `coffees.py`, `roasters.py`, `flavor_notes.py`, `equipment.py`, `recipes.py`, `bags.py`, `photos.py`. Each follows the HTMX-fragment pattern from D-01..D-04.
- **`app/services/`** — NEW files: per planner discretion, either one `catalog.py` or `coffees.py`/`roasters.py`/`flavor_notes.py`/`equipment.py`/`recipes.py`/`bags.py`/`photos.py`. Recommendation: per-entity.
- **`app/schemas/`** — NEW files: per-entity Pydantic form schemas (`coffee.py`, `roaster.py`, etc.) implementing the SEC-06 numeric-range pattern. Existing `app/schemas/auth.py` is the reference template.
- **`app/templates/pages/`** — NEW templates: `coffees.html`, `roasters.html`, `flavor_notes.html`, `equipment.html`, `recipes.html`. Each is a list page with inline-expand form.
- **`app/templates/fragments/`** — populated for the first time: `coffee_row.html`, `coffee_form.html`, `roaster_row.html`, `roaster_modal.html`, `flavor_note_modal.html`, `recipe_step_builder.html`, datalists, pour-timeline preview. Each fragment is autoescape-on; no `|safe`.
- **`app/static/js/photo-upload.js`** — NEW. Vanilla JS Canvas downscale per D-05.
- **`app/static/js/alpine-components/`** — NEW directory + components (`recipe-step-builder.js`, `mini-modal.js`, possibly a tag-input precursor for the flavor-note dropdown). All CSP-build compliant (registered via `Alpine.data`, no inline expressions).
- **`app/events.py`** — extends with catalog event constants per Phase 1 D-14 taxonomy.
- **Photo storage** — `coffee_snobbery_photos` named volume (Phase 0). Layout: `/app/data/photos/{uuid}.jpg` and `/app/data/photos/{uuid}-thumb.jpg`. Planner confirms the volume mount path matches `docker-compose.yml`.

</code_context>

<specifics>
## Specific Ideas

- **`Recipe.steps` JSONB schema lock:** array of objects `{water_grams: int (ge=0, le=2000), time_seconds: int (ge=0, le=3600), label: str (max_length=80)}`. Validated by a per-step Pydantic sub-schema in `app/schemas/recipe.py`. Planner confirms exact ranges.
- **`Coffee.advertised_flavor_note_ids` is an array of bigints, NOT a join table.** Two reasons: (1) order matters (the roaster lists them in a specific sequence on the bag); (2) it's a denormalized advertised-by-roaster list, not the user's observed list (that's per-session, lives in `brew_sessions.flavor_note_ids_observed` Phase 5). Postgres array + GIN index for the eventual search.
- **`Roaster.website` validated with Pydantic `HttpUrl`** — used later by Phase 7 AI URL verification (the AI-suggested buy URL is independent, but having a known roaster website is useful for the AI's web search context).
- **Coffee detail page is the "open new bag" launching pad.** Bag CRUD is nested: `GET /coffees/{id}` shows the coffee + its bags + "Open new bag" button (inline-expand bag form per D-02). Bag list at `/bags` is NOT required at v1; planner picks whether to ship one or just surface bags from the coffee detail. Recommendation: coffee-nested only.
- **`equipment.usage_count` denormalized column ships at 0 in Phase 4** and is updated by triggers / service-layer increments in Phase 5 when sessions reference equipment. Planner confirms whether to use a Postgres trigger or service-layer write.
- **Mini-modal HTMX flow (D-15):** parent form's "+ Create new roaster" link is `hx-get /roasters/new?as_modal=true hx-target=#modal-mount hx-swap=innerHTML`. The modal Alpine component opens on element-mount. Modal POSTs to `/roasters` with `as_modal=true`; on 200, server returns `HX-Trigger: roaster-created` with `{id, name}` payload + an empty fragment that clears the modal. Parent form's roaster-field Alpine listener listens for `roaster-created` and updates the hidden `roaster_id` input + the visible label.
- **Photo MIME validation order:** (1) reject if `Content-Length` > 5MB before reading body; (2) read first 8 bytes, check magic byte signature against JPEG/PNG/WebP; (3) full body to Pillow `Image.open()` + `Image.verify()` (separate decode pass); (4) re-encode to JPEG quality 0.85 (this naturally strips trailing polyglot bytes per PITFALL SEC-4); (5) EXIF strip via `Image.getexif().clear()` + save; (6) generate 400px thumbnail. Order matters — magic-byte first because Pillow will happily decode 1GB of structured nonsense.
- **`HX-Redirect` is used for cross-context navigations only** — D-12 (duplicate-recipe → new recipe edit form), Phase 9 admin pages, etc. Day-to-day catalog edits use `hx-swap` row replacement, not redirects.
- **Datalist endpoint pattern:** `GET /flavor-notes/datalist?q=<query>` returns a `<datalist id="flavor-notes-list">` fragment with up to 50 matches sorted by usage count or alphabetically. Same shape for `/roasters/list`. Per D-14, no OOB swaps.
- **The `setup_completed` row stays raw-SQL** — Phase 2's lock path is unchanged. Phase 4 doesn't touch auth.

</specifics>

<deferred>
## Deferred Ideas

- **Bag list page (`/bags`) as a standalone surface** — at v1, bags live under the coffee detail page only. Standalone `/bags` page might be useful for "what bags are open right now?" — revisit in Phase 5 when brew-session UX lights up the use case.
- **Step `pour_duration` field on recipes** — "pour 50g over 10 seconds" rather than just "be at 50g by 0:30". More expressive but most published recipes only give cumulative time. Deferred unless we see real recipes that need it.
- **Step `technique` / `agitation` enum (swirl / stir / WDT / none)** — niche pour-over nuance. Some recipes care; most don't. Defer to v2.
- **Recipe versioning** — currently "edit in place"; the "Duplicate to iterate" convention (D-12) is the substitute. PROJECT v2-deferred list calls this out explicitly.
- **Hierarchical flavor wheel UI** — flat tags with category enum is v1. v2 might surface a coffee-flavor-wheel picker. PROJECT v2-deferred list.
- **Coffee hero photo (separate from bag photo)** — D-08 rejected for v1. If we want a visual hero image (e.g., the roaster's hero shot) on the coffee catalog, revisit in v2.
- **HEIC-from-iOS-without-JS** — the Canvas downscale at D-05 naturally converts to JPEG for the JS-on path; the JS-off fallback would hit Pillow + need `pillow-heif`. If JS-off iOS uploads become a real complaint, add `pillow-heif`. Otherwise the JS-off fallback can reject HEIC with "Please use JPEG/PNG/WebP, or enable JavaScript for automatic conversion."
- **Bulk actions on catalog lists** — "archive 5 coffees at once". Not in spec; user volume doesn't need it. Defer.
- **Coffee/equipment photo galleries** — multiple photos per entity. Not in spec; bag-per-photo is the model.
- **Inline edit of roaster/flavor-note metadata after inline-create** — D-15 mini-modal captures full fields at create time. Editing them later happens on the `/roasters` or `/flavor-notes` list page; the coffee form doesn't surface a roaster-edit affordance. If that becomes friction, add an inline edit shortcut.
- **Real-time collaboration / WebSocket presence** — PROJECT.md out-of-scope.
- **Search across catalog from inside the coffee form** — Phase 10 ships global search; Phase 4 ships per-field autocomplete only.
- **Coffee-list `bags-open` count column** — useful info ("you have 3 open bags of this coffee"); deferred to Phase 5 when sessions/bags actually have lifecycle data to count.
- **Recipe difficulty/skill-level tag** — niche; deferred.

</deferred>

---

*Phase: 4-Shared Catalog*
*Context gathered: 2026-05-18*
