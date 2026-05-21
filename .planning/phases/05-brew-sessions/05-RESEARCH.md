# Phase 5: Brew Sessions - Research

**Researched:** 2026-05-19
**Domain:** Per-user brew logging (FastAPI + SQLAlchemy 2.0 + Postgres 16 GENERATED columns + HTMX/Alpine CSP forms + CSV round-trip)
**Confidence:** HIGH for stack/architecture/schema (verified against shipped Phase 0-4 code + official docs); MEDIUM-LOW for the literal Beanconqueror CSV header strings (could not reach the export-service source without auth — best-effort mapping flagged for confirmation).

## Summary

Phase 5 is the first per-user surface and the daily-use core of Snobbery. Everything it needs is already established in the Phase 0-4 codebase: the SEC-06 Pydantic-validation-to-200-fragment pattern (`app/routers/coffees.py` + `app/services/form_validation.py`), the CSP-build Alpine registration convention (`recipe-step-builder.js`, `autocomplete.js`), the autocomplete machinery (`flavorNoteChips` factory + `autocomplete_list.html`), the GIN-index hand-edit migration precedent (`p4_shared_catalog.py`), and the sync-session service shape (`app/services/equipment.py`). Phase 5 adds one new model (`BrewSession`), an optional draft store, a `brew` router, three services (`brew_sessions`, `drafts`, `csv_io`), four new Alpine components, and three new pages — all following patterns already on disk. The UI is fully locked by `05-UI-SPEC.md`; this research covers only the data-binding mechanics and the backend that the planner must build.

The two genuinely novel technical items are (1) the Postgres GENERATED column `extraction_yield_pct` — `mapped_column(Computed("...", persisted=True))` is the verified SQLAlchemy 2.0 syntax, but Alembic autogenerate will NOT emit the `GENERATED ALWAYS AS` clause, so the migration needs the same kind of hand-edit the GIN index already got in Phase 4; and (2) the `ARRAY(BigInteger)` round-trip for `flavor_note_ids_observed`, which mirrors the already-shipped `coffees.advertised_flavor_note_ids` column and its `getlist()`-based form parsing exactly.

**Primary recommendation:** Mirror the Phase 4 catalog conventions verbatim. New model with `Computed(..., persisted=True)` for EY, hand-edited migration for the GENERATED clause and the dedup/list indexes, `ARRAY(BigInteger)` for observed notes copied from the coffee model, a clone of the `flavorNoteChips` Alpine factory (renamed `observedFlavorNotes`, bound to `flavor_note_ids_observed`), stdlib `csv` for import/export, and a dedicated `brew_drafts` table (one row per user) for the BREW-07 server backstop. Add no new dependencies.

## User Constraints (from CONTEXT.md)

> Copied from `05-CONTEXT.md` (D-01..D-15 + Claude's Discretion + Deferred). These are LOCKED. Research does not propose alternatives to locked decisions.

### Locked Decisions

**Form surface & controls**
- **D-01:** Dedicated route for the brew form (`/brew/new`, `/brew/{id}/edit`, `/brew/new?from={session_id}`), NOT catalog-style inline-expand. Sessions LIST still uses Phase 4 HTMX-fragment + `hx-push-url` filter conventions.
- **D-02:** Optional refractometer fields (`yield_grams_actual`, `tds_pct`) behind a closed-by-default "Refractometer / advanced" disclosure; `extraction_yield_pct` is a GENERATED column rendered read-only inside it. Draft persistence remembers whether the disclosure was open.
- **D-03:** Rating uses half-step (0.5) left/right tap-zones in the UI, but the column stays `Decimal multiple_of=0.25` (`ge=0, le=5`). Recorded deviation: ~28px half-zones below the 44px rule, accepted at household scale; mitigate with full 56px star height hit-slop.

**Prefill & smart defaults**
- **D-04:** Hybrid prefill — on `/brew/new` prefill from the user's single most-recent session; when the coffee changes, re-prefill from their last session with that coffee.
- **D-05:** Recipe wins on select for the four template fields (`dose_grams_actual`, `water_grams_actual`, `water_temp_c_actual`, `grind_setting_actual`). Last-session prefill fills everything else. All fields remain editable.
- **D-06:** Auto-select the coffee's newest open bag (`finished_at IS NULL`, most-recent `opened_at`). Editable/clearable (clear = freestyle, `bag_id=null`). No open bag → blank + "open new bag" link.
- **D-07:** `water_type` is a native `<select>` of common types (Tap, Filtered, Third Wave Water, Distilled, Spring, RO/Zero) plus free-text "Other". Stored as text on the session.
- **D-08:** "Brew again" prefills from the source session and explicitly blanks `rating`, `flavor_note_ids_observed`, `notes`. Overrides D-04 when `?from=` is present.

**Flavor-note tag input**
- **D-09:** A committed observed note matching nothing is auto-created as a shared `flavor_notes` row with `category='other'` (no modal). Chip shows a "new" badge.
- **D-10:** Autocomplete-first, link-on-exact-match (citext), create-only-on-no-match. Reuse Phase 4's `autocomplete_list.html` + `hx-get`-on-focus / debounce / `hx-sync="this:replace"` (D-13/D-14).
- **D-11:** The selected coffee's `advertised_flavor_note_ids` render as one-tap quick-add chips above the input. `flavor_note_ids_observed` (per-session) is distinct from `advertised_flavor_note_ids` (per-coffee) — never conflate.

**CSV import & export**
- **D-12:** Coffee matched by name (citext), roaster-qualified when a roaster column is present (`coffees.name` is non-unique). Ambiguous multi-match = refused row.
- **D-13:** Bag matching optional; refuse only on named-but-unmatched (resolve by coffee + `roast_date`). No bag named → import freestyle (`bag_id=null`).
- **D-14:** Idempotent dedup on `(user_id, coffee_id, brewed_at)`. Matching rows skipped + counted. All accepted rows in a single transaction.
- **D-15:** Export is name-based and round-trip-safe (IDs → human-readable names; includes read-only computed brew ratio + extraction yield). Re-imports cleanly via D-12/D-13.

### Claude's Discretion
- **`brewed_at` default + editability** — recommend default to now (server-side), editable for back-dating. Store tz-aware UTC; render in `APP_TIMEZONE`.
- **Server draft store model** — recommend one active draft per `user_id` (`brew_drafts` table or JSON column). Autosave-on-blur on `/brew/new` only. Edit form is NOT draft-backed. Cleared on submit + on logout. localStorage primary; server restore ONLY when localStorage empty.
- **`equipment.usage_count` increment mechanism** — recommend service-layer (testable, one place) over trigger; handle three FKs (brewer/grinder/kettle) + equipment-change edits.
- **Sessions-list default sort** — recommend newest `brewed_at` first.
- **Edit-session form population** — shows actual stored values, no ghost-prefill (ghosting is `/brew/new` only).
- **Exact Beanconqueror column→field mapping** — plan-phase research item (see "CSV Import/Export" section below; partial verification, flagged).
- **Filter control styling + rating-range/date-range widgets** — planner picks (native preferred).
- **Whether the live ratio readout also shows extraction yield** when TDS entered — planner picks (UI-SPEC recommends ratio-only inline, EY inside disclosure).

### Deferred Ideas (OUT OF SCOPE)
- Guided Brew Mode + wake lock (BREW-12/13) — Phase 11.
- Per-attempt advanced insights beyond EY — v2.
- Inline recategorization of an auto-created flavor note — catalog page only.
- Bag-required strict import mode — D-13 chose bag-optional.
- CSV import of catalog entities (coffees/bags/roasters) — import is brew-sessions-only.
- Hard UNIQUE on `(user_id, coffee_id, brewed_at)` — deferred in favor of import-time dedup (avoids rejecting legitimate same-second manual logs).
- Quick-log "repeat exact last brew" one-tap — defer unless requested.
- Standalone `/bags` page — Phase 4 carryover; not Phase 5 scope.

## Project Constraints (from CLAUDE.md)

Directives the planner must honor with the same authority as locked decisions:

- **Stack invariants (do not change without asking):** Python 3.12 + FastAPI, PostgreSQL 16, SQLAlchemy 2.0 + Alembic, Jinja2 + HTMX + Tailwind (CDN/standalone CLI) + Alpine.js — **no npm build pipeline**, argon2-cffi, Fernet, APScheduler in-process, two-container Docker Compose.
- **Architectural invariants:** Brew sessions and AI recommendations are **per-user** (scope every query by `request.state.user.id`). Coffees/equipment/recipes/roasters/flavor notes are **shared**. CSRF on all state-changing forms. Security headers on every response. Mobile-first tested at 375px. Reverse-proxy aware (never hardcode hostnames/schemes).
- **Code conventions:** `ruff format` + `ruff check` (warnings as errors); type hints required, `from __future__ import annotations`; Pydantic v2; SQLAlchemy 2.0 style (typed `Mapped[...]`, `select()`/`update()`, no legacy Query API); 2-space Jinja indent; conventional commits.
- **Never do silently:** drop/rename a column without a data-preservation plan; disable CSRF/CSP/security headers; log API keys/passwords/session tokens; bypass the encryption layer; modify `docs/snobbery-gsd-prompt.md`.
- **When to ask first:** schema migrations that drop columns or change types lossy; changes to auth/CSRF/encryption; refactors touching >1 module; deployment-topology changes. (Phase 5 is additive — new tables, new router, no middleware change — so it stays in "proceed" territory, but the planner should keep migrations strictly additive.)
- **GSD workflow enforcement:** all file edits go through a GSD command.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BREW-01 | `brew_sessions` table per user (full column list) | Schema section below: `Mapped[...]` columns, `Computed(persisted=True)` EY, `ARRAY(BigInteger)` observed notes, indexes |
| BREW-02 | Single scrollable add-session form with aggressive prefill + visible indicators | Prefill section (D-04/D-05/D-06 query patterns) + UI-SPEC prefill-pill contract |
| BREW-03 | Tag input for observed flavor notes (autocomplete, comma/enter, chips, mobile) | Clone `flavorNoteChips` → `observedFlavorNotes`; reuse `autocomplete_list.html` |
| BREW-04 | Rating control 0-5 in 0.25 steps, tap-on-stars, ≥44px | `Decimal` column + Pydantic `multiple_of=0.25`; hidden-input + Alpine `ratingStars` factory |
| BREW-05 | Live brew-ratio readout in Alpine; no schema column | `brewRatio` Alpine factory; computed `water/dose` |
| BREW-06 | LocalStorage draft persistence namespaced by `user_id`, cleared on submit | `snobbery:draft:brew:<user_id>` key; `brew-draft.js`; MX-5 clear-on-logout |
| BREW-07 | Server-side draft autosave on blur; restore when localStorage empty; iOS ITP backstop | `brew_drafts` table (one/user); `POST /brew/draft`; reconciliation order |
| BREW-08 | Sticky Save/Cancel on long mobile forms | UI-SPEC sticky-bar contract (CSS only) |
| BREW-09 | Quick re-log on every row (prefill all but rating/notes/observed) | `/brew/new?from={id}` (D-08); prefill source = specific session |
| BREW-10 | Sessions list per user with filters (coffee/brewer/rating/date) + CSV export | Phase 4 filter-bar pattern; stdlib `csv` export of filtered view |
| BREW-11 | CSV import; refuse rows where coffee or bag not in catalog; single transaction | stdlib `csv` import; D-12/D-13/D-14 resolver; per-row outcome summary |
| MOB-05 | `inputmode`/`type` attributes for mobile keyboards | Input-attribute matrix below |
| MOB-06 | 16px input rule (no iOS focus-zoom) + Playwright 375px assertion | **Already shipped** in `tailwind.src.css` `@layer base` (UI-SPEC correction); planner's only obligation is the Playwright assertion (deferred to Phase 12) + no input overriding font-size <16px |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Brew-session persistence + dedup | API/Backend (`services/brew_sessions.py`) | Database (GENERATED EY, indexes, dedup query) | Per-user writes, single-transaction integrity, audit events all belong in the service layer per the Phase 4 convention |
| Extraction-yield computation | Database (Postgres GENERATED column) | — | D-02/BREW-01 lock it as a GENERATED column; the app never writes it. DB is the single source of truth |
| Prefill source resolution (D-04/05/06) | API/Backend | — | Last-session, last-session-with-coffee, recipe-targets, newest-open-bag are all SQL queries scoped by `user.id` |
| Live brew-ratio readout (BREW-05) | Browser/Client (Alpine) | — | Pure presentation; no schema column, no round-trip |
| Rating control (BREW-04) | Browser/Client (Alpine) | API (Decimal validation) | Tap UI is client; the `Decimal` constraint is enforced server-side via Pydantic |
| Flavor-note tag input (BREW-03) | Browser/Client (Alpine chips) | API (autocomplete fragment + auto-create) | Chip management is client; the autocomplete list + D-09 auto-create are server endpoints |
| Draft persistence (BREW-06/07) | Browser/Client (localStorage primary) | API (`brew_drafts` table, ITP backstop) | localStorage is the primary store; server is the eviction backstop, restored only when localStorage empty |
| CSV import/export (BREW-10/11) | API/Backend | Database (single transaction) | Resolution, dedup, transaction boundary, name↔id mapping are all backend |
| `equipment.usage_count` increment | API/Backend (service-layer) | — | D-discretion recommends service-layer over trigger for testability; handles 3 FKs + edits |

## Standard Stack

No new dependencies. Everything is already pinned and installed from Phase 0-4. [VERIFIED: codebase — `app/` imports, `pyproject.toml` pins in CLAUDE.md Technology Stack]

### Core (already installed — used by Phase 5)
| Library | Version (pinned) | Purpose in Phase 5 | Why Standard |
|---------|------------------|--------------------|--------------|
| SQLAlchemy | `>=2.0.49,<2.1` | `BrewSession` model, `Computed()` GENERATED column, `ARRAY(BigInteger)`, `Numeric` rating, `select()`/`update()` | Locked stack; `Computed(persisted=True)` is the 2.0 idiom [CITED: docs.sqlalchemy.org/en/20/core/defaults.html] |
| Alembic | `>=1.18,<2.0` | New migration: `brew_sessions` table, `brew_drafts`, indexes | Locked; autogenerate from `Mapped[...]` (with hand-edits — see Pitfalls) |
| Pydantic | `>=2.13,<3.0` | Brew form schema, CSV row schema; `Field(ge=, le=, multiple_of=)` + `Decimal` | Locked; `ConfigDict(extra="forbid")` mass-assignment defense per `app/schemas/coffee.py` |
| FastAPI | `>=0.136,<0.137` | `brew` router; `await request.form()` + `getlist()` for repeated `flavor_note_ids_observed` keys; `UploadFile` for CSV | Locked; the multi-value form pattern is exactly `app/routers/coffees.py` |
| Python `csv` (stdlib) | 3.12 | CSV import (`csv.DictReader`) + export (`csv.DictWriter`/`writer`) | **Don't-hand-roll the parser, but don't add a dep either** — stdlib handles quoting/escaping/dialect correctly at household scale |
| Python `decimal.Decimal` (stdlib) | 3.12 | Rating persistence (avoids float `multiple_of` rounding) | Standard for money/rating exactness |
| HTMX (CDN) | `2.0.10` | Sessions-list filters (`hx-get`+`hx-push-url`), tag-input autocomplete, draft autosave, post-save `HX-Redirect` | Already in `base.html` |
| Alpine.js CSP build (CDN) | `@alpinejs/csp@3.15.12` | `ratingStars`, `observedFlavorNotes`, `brewRatio`, `brewDraft` + Advanced disclosure | Already in `base.html`; CSP-build registration via `Alpine.data()` |
| structlog | `>=25.5,<26` | `brew.session.*`, `brew.draft.*`, `brew.csv.*` audit events | Established in `app/events.py` |

### Alternatives Considered (and rejected)
| Instead of | Could Use | Tradeoff — why rejected |
|------------|-----------|-------------------------|
| stdlib `csv` | `pandas` / `polars` | Heavy dependency for a household-scale row reader; violates "no new deps unless strongly justified". stdlib `csv.DictReader` is sufficient. |
| Service-layer `usage_count` increment | Postgres trigger | Trigger is harder to test and splits brew-write logic across SQL+Python. Discretion note already recommends service-layer. |
| `brew_drafts` table | JSONB column on `users` | A dedicated table keeps the draft lifecycle (autosave/clear) isolated from the user row and gives a clean `DELETE WHERE user_id=` on logout/submit. Recommend the table. |
| GENERATED column for EY | Computing EY in Python on read | D-02/BREW-01 explicitly lock EY as a GENERATED column; computing in Python would diverge from CSV-imported rows and the read-only contract. |

**Installation:** None. All packages present.

**Version verification:** Versions are pinned and verified in the CLAUDE.md "Technology Stack" table (PyPI consulted 2026-05-16); the codebase imports confirm they are installed and in use. No registry re-check needed for an additive phase using already-installed libraries. [VERIFIED: codebase imports + CLAUDE.md pins]

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────────────────────┐
   Browser (375px)        │            FastAPI app (single worker)        │
   ┌──────────────┐       │                                               │
   │ /brew/new    │ GET   │  brew router (app/routers/brew.py)            │
   │ (page)       ├──────►│   require_user → request.state.user.id        │
   │              │       │   ├─ GET /brew/new[?from=]  → prefill query    │──┐
   │ Alpine:      │       │   │     (D-04/05/06 source resolution)         │  │
   │ ratingStars  │       │   ├─ POST /brew         → Coffee-style 200/    │  │ services/
   │ observedTags │ POST  │   │     fragment validate → service write      │  │ brew_sessions.py
   │ brewRatio    ├──────►│   ├─ POST /brew/{id}    → update               │──┤  (sync Session)
   │ brewDraft    │       │   ├─ POST /brew/draft   → drafts service       │  │  + drafts.py
   │              │ blur  │   ├─ GET  /brew         → list + filters        │  │  + csv_io.py
   │ localStorage ├──────►│   │     (HX-Request → fragment; hx-push-url)    │  │  + equipment usage++
   │ snobbery:    │       │   ├─ GET  /brew/export  → csv_io (DictWriter)   │  │
   │ draft:brew:  │       │   └─ POST /brew/import  → csv_io (DictReader)   │  │
   │ <user_id>    │       │         single txn, per-row resolve+dedup       │  │
   └──────────────┘       │                                               │  │
        │  autocomplete   │  flavor_notes service (D-09 auto-create)      │  │
        │  hx-get focus   │  reuse fragments/autocomplete_list.html       │  │
        └────────────────►│                                               │  │
                          └───────────────────────┬───────────────────────┘  │
                                                  ▼                          ▼
                          ┌─────────────────────────────────────────────────────┐
                          │                 PostgreSQL 16                         │
                          │  brew_sessions  (per-user; FKs → coffees/bags/        │
                          │    recipes/equipment/flavor_notes; extraction_yield_  │
                          │    pct GENERATED ALWAYS AS (...) STORED)              │
                          │  brew_drafts    (one row per user_id; UNIQUE user_id) │
                          │  indexes: (user_id, brewed_at DESC),                  │
                          │           (user_id, coffee_id, brewed_at DESC),       │
                          │           GIN (flavor_note_ids_observed)              │
                          └─────────────────────────────────────────────────────┘
```

### Recommended File Structure (additive — mirrors Phase 4)
```
app/
├── models/
│   ├── brew_session.py      # NEW: BrewSession (Computed EY, ARRAY observed notes)
│   ├── brew_draft.py        # NEW: BrewDraft (one per user; JSON/columns)
│   └── __init__.py          # ADD re-export of BrewSession + BrewDraft (Alembic discovery)
├── schemas/
│   ├── brew_session.py      # NEW: BrewSessionCreate/Update (Decimal rating, ranges)
│   └── brew_csv.py          # NEW: per-row import schema
├── services/
│   ├── brew_sessions.py     # NEW: CRUD + prefill queries + usage_count increment
│   ├── brew_drafts.py       # NEW: get/upsert/clear one draft per user
│   └── csv_io.py            # NEW: import (resolve+dedup+txn) + export (name-based)
├── routers/
│   └── brew.py              # NEW: register in app/main.py via include_router
├── templates/
│   ├── pages/{brew_form,sessions,brew_import}.html     # NEW
│   └── fragments/{session_list,session_row,csv_import_results}.html  # NEW
│       (autocomplete_list.html REUSED unchanged)
├── static/js/alpine-components/
│   ├── rating-stars.js      # NEW: Alpine.data('ratingStars', ...)
│   ├── flavor-tag-input.js  # NEW: Alpine.data('observedFlavorNotes', ...)
│   ├── brew-ratio.js        # NEW: Alpine.data('brewRatio', ...)
│   └── brew-draft.js        # NEW: Alpine.data('brewDraft', ...)
├── events.py                # ADD brew.* constants
└── migrations/versions/
    └── p5_brew_sessions.py  # NEW: table + GENERATED hand-edit + indexes + brew_drafts
```
`base.html`: add four `<script defer nonce>` tags BEFORE the Alpine core script (after the existing three). [VERIFIED: `app/templates/base.html` lines 13-25]

### Pattern 1: SEC-06 form validation → 200 + fragment re-render
**What:** POST handler reads `await request.form()`, parses via a `_parse_form_payload`-style helper, constructs the Pydantic schema, catches `ValidationError`, pivots via `errors_by_field()`, re-renders the form fragment at HTTP 200 with `values` + `errors`.
**When to use:** Every Phase 5 form POST (`/brew`, `/brew/{id}`).
**Example (verbatim shape from `app/routers/coffees.py`):**
```python
# Source: app/routers/coffees.py create_coffee (lines 353-382)
form_data = await request.form()
raw_view, schema_input = _parse_form_payload(form_data)
try:
    form = BrewSessionCreate(**schema_input)
except ValidationError as exc:
    context = _hydrate_form_context(db, values=raw_view,
                                    errors=_normalize_errors(errors_by_field(exc)),
                                    mode="create")
    return templates.TemplateResponse(request=request,
        name="pages/brew_form.html", context=context, status_code=200)
# ... service write, then HX-Redirect to /brew (D-01 dedicated route)
```
Note divergence: Phase 4 returns a row fragment on success (inline-expand); Phase 5 D-01 is a dedicated page, so success → `HX-Redirect` to the sessions list (or cleared `/brew/new`).

### Pattern 2: ARRAY(BigInteger) multi-value form round-trip
**What:** Repeated hidden inputs named `flavor_note_ids_observed`, collected via `form_data.getlist(...)`, cast to `list[int]`, validated by a `field_validator` that all ids are `>= 1`.
**When to use:** The observed-flavor-notes chip widget submit.
**Example (the exact pattern already shipped for `advertised_flavor_note_ids`):**
```python
# Source: app/routers/coffees.py _parse_form_payload (lines 155-168)
values = form_data.getlist("flavor_note_ids_observed")
id_strs = [v for v in values if isinstance(v, str) and v != ""]
schema_input["flavor_note_ids_observed"] = [int(v) for v in id_strs]
```
The Alpine `flavorNoteChips` factory renders two parallel `<template x-for>` blocks (visible chips + hidden inputs) so FastAPI collects the repeated keys natively. Clone it as `observedFlavorNotes`, bind to `flavor_note_ids_observed`. [VERIFIED: `app/static/js/alpine-components/autocomplete.js` lines 167-318]

### Pattern 3: CSP-build Alpine component
**What:** `document.addEventListener('alpine:init', () => Alpine.data('name', () => ({...})))`; config via `data-*` read in `init()` from `this.$root.dataset`; two-way binding via `:value` + `x-on:input` (NO `x-model`); JSON config via `data-initial-* |tojson` parsed in `init()`. Each component is its own `<script defer nonce>` BEFORE the Alpine core.
**When to use:** All four new components.
**Example:** `recipe-step-builder.js` (`data-initial-steps` + `JSON.parse`) and `autocomplete.js` (`data-initial-chips`). The `ratingStars` component seeds via `data-initial-rating` and mirrors a `<input type="hidden" name="rating" :value="value">`. [VERIFIED: `app/static/js/alpine-components/recipe-step-builder.js` lines 28-44]

### Pattern 4: Sync service with audit event + single commit
**What:** `def create_brew_session(db: Session, *, ..., by_user_id: int) -> BrewSession:` → instantiate ORM → `add` → `flush` (populate id) → `commit` → `log.info(BREW_SESSION_CREATED, brew_session_id=..., user_id=by_user_id)` → return.
**When to use:** Every brew-session write. `equipment.usage_count` increments happen in the same transaction before commit.
**Example:** `app/services/equipment.py` `create_equipment` (lines 67-102). [VERIFIED]

### Anti-Patterns to Avoid
- **Conflating `flavor_note_ids_observed` with `advertised_flavor_note_ids`** — different meaning, different binding name, different source. The chip widget for Phase 5 must be a sibling factory bound to a different `name`, not a reuse of the Phase 4 one. (CONTEXT D-11 + UI-SPEC.)
- **Writing `extraction_yield_pct` from the app** — it is GENERATED; the INSERT/UPDATE must NOT include it. Pydantic schema must NOT have it as a writable field. Render read-only only.
- **`x-model` / inline `hx-on:` / `|safe`** — banned by CSP grep tests (SEC-02/SEC-05). Use `:value`+`x-on:input`; CSRF header via the global `htmx-listeners.js` (no per-element `hx-headers`).
- **Hard UNIQUE on `(user_id, coffee_id, brewed_at)`** — CONTEXT defers this; use a non-unique index + import-time dedup so legitimate same-second manual logs aren't rejected.
- **Async handler calling sync `Session`** — keep brew CRUD handlers sync (FastAPI runs them in a threadpool); only the (non-existent here) AI path is async. [STACK.md §3.3]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Extraction-yield math + NULL handling | App-side EY computation on read/write | Postgres GENERATED column `Computed(..., persisted=True)` | DB computes once, stays NULL when inputs NULL, identical for manual + imported rows, read-only by construction |
| CSV parsing/quoting/escaping | Manual `line.split(",")` | stdlib `csv.DictReader` / `csv.writer` | Handles quoted commas, embedded newlines, dialect, BOM — `split` corrupts notes containing commas |
| Form validation + error mapping | Per-field manual checks | Pydantic v2 schema + `errors_by_field()` (`app/services/form_validation.py`) | The SEC-06/D-04 pattern is already the project standard; reuse exactly |
| Multi-value form collection | Comma-joined string field | `form_data.getlist()` + parallel `<template x-for>` hidden inputs | Already proven for `advertised_flavor_note_ids`; FastAPI collects repeated keys natively |
| Autocomplete dropdown + keyboard nav | New widget | Clone `flavorNoteChips` + reuse `autocomplete_list.html` | HX-3/HX-4 footguns already solved (no OOB, `hx-get` on focus, `hx-sync`, 350ms debounce, min-2-char) |
| 16px iOS no-zoom rule | New `custom.css` | Already shipped in `tailwind.src.css @layer base` | UI-SPEC correction: `custom.css` does NOT exist and must NOT be created; the rule is inherited |
| Timezone conversion | Manual offset math | `zoneinfo.ZoneInfo(settings.APP_TIMEZONE)` for render; store tz-aware UTC | Standard; `APP_TIMEZONE` already in `app/config.py` |

**Key insight:** Phase 5 is almost entirely composition of existing patterns. The only net-new backend primitive is the GENERATED column, and even that has a direct precedent in the GIN-index hand-edit already in `p4_shared_catalog.py`.

## brew_sessions Schema (BREW-01) — verified design

`BrewSession` model (`app/models/brew_session.py`), mirroring the established `Mapped[...]` conventions:

```python
# Columns (types/nullability from BREW-01 + CONTEXT):
id:                     BigInteger Identity PK
user_id:                BigInteger FK→users.id  NOT NULL  (per-user scope)
coffee_id:              BigInteger FK→coffees.id NOT NULL (denormalized for fast queries; ondelete RESTRICT)
bag_id:                 BigInteger FK→bags.id    NULL     (freestyle when null; ondelete SET NULL)
recipe_id:              BigInteger FK→recipes.id NULL     (ondelete SET NULL)
brewer_id:              BigInteger FK→equipment.id NULL   (ondelete SET NULL)
grinder_id:             BigInteger FK→equipment.id NULL   (ondelete SET NULL)
kettle_id:              BigInteger FK→equipment.id NULL   (ondelete SET NULL)
water_type:             Text       NULL  (D-07 select-or-Other text)
dose_grams_actual:      Numeric    NOT NULL
water_grams_actual:     Numeric    NOT NULL
yield_grams_actual:     Numeric    NULL  (D-02 advanced)
tds_pct:                Numeric    NULL  (D-02 advanced)
extraction_yield_pct:   Numeric    GENERATED ALWAYS AS (...) STORED  (read-only)
water_temp_c_actual:    Numeric/Integer  (range 0-100; planner picks precision)
grind_setting_actual:   Text       NULL  (free-form magic number)
rating:                 Numeric(3,2) NULL  (Decimal, 0-5, 0.25 steps)
flavor_note_ids_observed: ARRAY(BigInteger) NOT NULL default '{}'
notes:                  Text       NOT NULL default ''
brewed_at:              TIMESTAMP(timezone=True) NOT NULL default now()
created_at / updated_at: TIMESTAMP(timezone=True) default now()
```

**EY formula + NULL behavior (verify with John in plan-phase):** CONTEXT `<specifics>` states `(yield_grams_actual * tds_pct) / dose_grams_actual`. **Caveat — this is dimensionally unusual.** The standard coffee extraction-yield formula is `EY% = (beverage_mass_g × TDS%) / dose_g`, which is exactly what CONTEXT specifies, EXCEPT the conventional definition uses **beverage mass** (what's in the cup) and TDS as a percentage. CONTEXT names the numerator `yield_grams_actual` — confirm `yield_grams_actual` IS the beverage mass (out), not the spent-grounds yield. Postgres NULL semantics: any arithmetic operand NULL → result NULL automatically [CITED: standard SQL NULL propagation], so EY is NULL whenever `yield_grams_actual`, `tds_pct`, or `dose_grams_actual` is NULL — matching the read-only "—" render. The exact `STORED` expression goes in the migration (see Pitfall 1).

**Indexes (hand-edited or declared):**
- `(user_id, brewed_at DESC)` — sessions list default sort + recent lookups.
- `(user_id, coffee_id, brewed_at DESC)` — D-04 per-coffee prefill + D-14 dedup probe.
- GIN on `flavor_note_ids_observed` — future containment queries (HOME-03 reads 4.0+ rated observed notes in Phase 6); same `USING GIN` hand-edit as `p4_shared_catalog.py`. [VERIFIED: precedent in migration]
- Do NOT add a UNIQUE constraint on the dedup key (CONTEXT deferred — import-time dedup only).

## CSV Import / Export (BREW-10, BREW-11, D-12..D-15)

### Beanconqueror column mapping — partial verification, MUST confirm

I verified Beanconqueror's internal `Brew` data-model field names from source [VERIFIED: github.com/graphefruit/Beanconqueror src/classes/brew/brew.ts], but I could **not** retrieve the literal Excel/CSV **column header strings** the export emits — the export-service file path was not reachable without GitHub auth, and the official docs do not enumerate headers. **This is the flagged research item from CONTEXT discretion.** The mapping below is a best-effort built on the verified internal field names + the standard coffee-brew vocabulary; the literal header text needs confirmation against a real export file from John (or a one-line Beanconqueror "Export → Excel" + open in a spreadsheet).

**Verified Beanconqueror internal field names → Snobbery columns (semantics HIGH; literal CSV header LOW):**

| Beanconqueror internal field | Snobbery `brew_sessions` column | Confidence | Notes |
|---|---|---|---|
| `bean` (reference → bean name) | `coffee_id` (resolve by name, D-12) | HIGH semantics | Export flattens the bean ref to a name string; roaster may be a separate column |
| `grind_weight` (number) | `dose_grams_actual` | HIGH | Confirmed = dose-in by difluid converter [VERIFIED] |
| `grind_size` (string) | `grind_setting_actual` | HIGH | Free-form grinder setting [VERIFIED] |
| `brew_temperature` (number) | `water_temp_c_actual` | HIGH | Celsius assumed; confirm unit |
| `brew_beverage_quantity` (number) | `yield_grams_actual` | MEDIUM | "beverage in the cup" = yield-out; map to advanced yield field |
| `brew_quantity` (number) | (possibly water-in) `water_grams_actual` | MEDIUM | `brew_quantity` vs `brew_beverage_quantity` distinction needs confirmation against a real file |
| `tds` (number) | `tds_pct` | HIGH | Direct |
| `rating` (number) | `rating` (scale-convert) | MEDIUM | Beanconqueror rating scale (0-5? 0-10?) must be confirmed and converted to 0-5 0.25-step Decimal |
| `note` (string) | `notes` | HIGH | Direct |
| `cupped_flavor` / cupping flavors | `flavor_note_ids_observed` (resolve/auto-create per D-09/D-10) | LOW | Structure unknown; may be unmapped at v1 |
| brew timestamp (config/created) | `brewed_at` | MEDIUM | Confirm the export's date column + format |
| `method_of_preparation` (→ name) | `brewer_id` (resolve by equipment name) | LOW | Optional; refuse-or-skip policy planner picks |
| `mill` (→ name) | `grinder_id` | LOW | Optional |
| `water` (→ name) | `water_type` | LOW | Beanconqueror `water` is a reference, not free text |
| (no native EY) | `extraction_yield_pct` | n/a | GENERATED — never imported; computed from dose/yield/tds |

**Recommendation:** Make the importer **header-driven, not positional** — read `csv.DictReader.fieldnames`, map known headers case-insensitively, ignore unknown columns. This makes the importer resilient to Beanconqueror version drift AND lets the D-15 Snobbery-native export (which uses Snobbery's own clean headers) round-trip through the same importer. Define the Snobbery export header set explicitly (it is the authoritative round-trip format); accept Beanconqueror headers as a best-effort superset. Plan-phase: confirm the exact Beanconqueror header strings against one real export before locking the header-alias table.

### Import algorithm (D-12/13/14, single transaction — BREW-11)
1. Reject non-CSV / oversized upload before reading the full body (mirror the photo-upload size guard in `app/services/photos.py`).
2. `csv.DictReader` over the decoded text (handle UTF-8 + BOM via `utf-8-sig`).
3. Per row, resolve in order:
   - **Coffee (D-12):** match `coffees.name` citext; if a roaster column present, qualify by `(name, roaster_id)`; ambiguous multi-match → **refused** (`coffee "{name}" ambiguous (matches multiple roasters)`); no match → **refused** (`coffee "{name}" not in catalog`).
   - **Bag (D-13):** if row names a bag (coffee + `roast_date`) and it resolves → link; if named but unmatched → **refused** (`bag (roast {date}) not found`); if not named → `bag_id=null` (freestyle).
   - **Dedup (D-14):** if a session already exists with `(user_id, coffee_id, brewed_at)` → **skipped-duplicate** (`duplicate of an existing session`).
4. Validate each accepted row through a Pydantic CSV-row schema (numeric ranges, rating scale, Decimal rating).
5. INSERT all accepted rows in a **single transaction**; commit once. Build the per-row outcome list (inserted / skipped / refused-with-reason). Render via `fragments/csv_import_results.html` after commit.
6. Auto-create observed flavor notes per D-09 (`category='other'`) inside the same transaction; resolve advertised/observed by citext name.

### Export (D-15, name-based round-trip)
- `GET /brew/export?{filters}` returns the **currently-filtered** view (same query params as the list).
- Resolve ids → human names (coffee, roaster, recipe, equipment, observed flavor notes joined by a delimiter); include computed brew-ratio + `extraction_yield_pct` as read-only columns.
- `csv.writer`/`DictWriter` with an explicit Snobbery header row; `Content-Disposition: attachment; filename="...csv"`; plain `<a href>` download (not an HTMX swap).
- The Snobbery export headers ARE the authoritative round-trip format the importer must accept.

## Draft Persistence (BREW-06/07, MX-5)

### iOS Safari ITP 7-day eviction — verified context
Apple's Intelligent Tracking Prevention caps script-writable storage (localStorage, IndexedDB, etc.) at a **7-day expiry** for sites the user reaches without a "user interaction" signal / for sites classified as having cross-site tracking capability; the cap is well-documented behavior. [CITED: webkit.org/blog "Full Third-Party Cookie Blocking and More" — 7-day cap on script-writable storage]. For an installed PWA / frequently-revisited first-party app the practical risk is lower, but BREW-07 treats the server draft as the backstop for exactly this case. **Confidence:** the 7-day cap is real and documented; whether it triggers for this specific self-hosted first-party PWA is install-and-usage-dependent — the backstop is the correct conservative design either way. [ASSUMED that the cap applies to this app's access pattern — the backstop neutralizes the question regardless.]

### Recommended design
- **localStorage key:** `snobbery:draft:brew:<user_id>` (MX-5 namespacing so a shared phone never leaks one user's draft). Written on every input change (BREW-06). Cleared on successful submit AND on logout.
- **Clear-on-logout mechanism:** the logout route already returns `RedirectResponse(url="/login", 303)` + `build_session_clear_cookie()` [VERIFIED: `app/routers/auth.py` lines 362-392]. localStorage cannot be cleared from the server. Options for the planner: (a) the `/login` page (or a small boot script) clears any `snobbery:draft:brew:*` keys on load when no session is present; or (b) `brew-draft.js` clears the namespaced key when it detects logout. Recommend (a) — clearing at `/login` render is simple and covers the shared-device case. Confirm with planner.
- **Server draft store:** dedicated `brew_drafts` table, `user_id` UNIQUE (one active draft per user), columns `user_id FK`, `payload JSONB` (the serialized form state incl. per-field touched-state + disclosure-open flag per D-02), `updated_at`. Upsert on `POST /brew/draft` (autosave-on-blur, `/brew/new` only). `DELETE WHERE user_id=` on submit + on logout (server-side).
- **Reconciliation order (BREW-07):** on `/brew/new` open — restore from localStorage if present; fall back to the server draft ONLY when localStorage is empty. `?from=` (Brew again) and edit mode bypass draft restore.
- **CSRF for the autosave POST:** the global `htmx-listeners.js` injects `X-CSRF-Token` on every HTMX request from the `csrf-token` meta [VERIFIED: lines 34-39]; if `brew-draft.js` uses `fetch` instead of an HTMX request, it must read the same meta and set the header manually. Recommend issuing the autosave as an HTMX request so CSRF is automatic.

## Rating Control Data Binding (BREW-04, D-03)

- **Persistence:** `rating: Decimal | None` column, `Numeric(3,2)`. Pydantic: `rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))`. **Use `Decimal`, not `float`** — `multiple_of` on floats hits binary-rounding edge cases; `Decimal("0.25")` is exact. [CITED: pydantic docs — `Decimal` fields support `max_digits`/`decimal_places`; numeric constraints `ge`/`le`/`multiple_of` apply]. The UI exposes only 0.5 steps but the column accepts 0.25 so CSV-imported quarter values validate and a finer future UI is not a migration (D-03).
- **Binding:** hidden `<input type="hidden" name="rating" :value="value">` inside `x-data="ratingStars"`; seed via `data-initial-rating` read in `init()`. Empty/blank rating on `/brew/new`. A "Clear" affordance resets to blank (submits empty → `None`).
- **CSP:** `:value` / `x-on:click` / `x-on:keydown` only; no `x-model`, no inline expressions; config via `data-*`. [VERIFIED: pattern in `recipe-step-builder.js`]
- **No-JS floor:** native `<input type="range" min="0" max="5" step="0.25">` or static numeric input, Alpine-enhanced to stars (planner picks).

## MOB-05 input attribute matrix

| Field | `type` | `inputmode` | Notes |
|-------|--------|-------------|-------|
| dose_grams_actual, water_grams_actual, yield_grams_actual, tds_pct | `text` or `number` | `decimal` | grams/percent — decimal keypad |
| water_temp_c_actual | `text` or `number` | `decimal` | 0-100°C |
| grind_setting_actual | `text` | `text` | free-form magic number |
| rating (no-JS floor) | `range` | — | step 0.25 |
| brewed_at | `datetime-local` (or `date`) | — | native picker; back-dating; tz handled server-side |
| notes | (textarea) | `text` | — |
| flavor-note query | `text` | `text` | `autocomplete="off"` |

**MOB-06:** the global `input, select, textarea { font-size: 16px }` rule is **already shipped** in `app/static/css/tailwind.src.css @layer base` (UI-SPEC correction, lines 18-20). Do NOT create `custom.css`. Every brew input inherits 16px; the only obligations are: never set an input font-size below 16px in a brew template, and the Playwright 375px no-zoom assertion (deferred to Phase 12 / TEST-06). [VERIFIED: UI-SPEC discovery note]

## Runtime State Inventory

> Phase 5 is **greenfield additive** (new tables, new router, no rename/refactor/migration of existing runtime state). This section is included for completeness because the phase touches the `equipment.usage_count` denormalized counter, which is the one piece of existing stored state Phase 5 mutates.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `equipment.usage_count` ships at 0 (Phase 4); Phase 5 starts incrementing it on session insert. No existing brew_sessions data to migrate (first phase to create the table). | Service-layer increment in the brew-write transaction; decrement/re-point on equipment-change edits and session deletes. No back-fill needed (counter starts correct from first session). |
| Live service config | None — no external service stores a Phase 5 string. | None — verified: no n8n/Datadog/Tailscale/etc. in this stack. |
| OS-registered state | None — APScheduler jobs are in-process (Phase 8); Phase 5 registers no OS-level tasks. | None. |
| Secrets/env vars | None new. `APP_TIMEZONE` (existing) is read for `brewed_at` render. | None — `APP_TIMEZONE` already in `app/config.py`. |
| Build artifacts | New Alpine `.js` files are served static (baked into the image; require `docker compose build` to take effect per CLAUDE.md). New migration runs on container start via `entrypoint.sh`. | Standard rebuild + redeploy; migration auto-applies. |

## Common Pitfalls

### Pitfall 1: Alembic autogenerate drops the GENERATED clause
**What goes wrong:** `alembic revision --autogenerate` detects the new `BrewSession` model but emits `extraction_yield_pct` as a plain `Numeric` column WITHOUT `GENERATED ALWAYS AS (...) STORED` — the same class of gap that forced the GIN-index hand-edit in `p4_shared_catalog.py`. The Computed clause is silently lost. [VERIFIED: Alembic docs list table/column/nullable/index/FK detection but NOT computed columns; "autogenerate is not intended to be perfect — always review" — CITED: alembic.sqlalchemy.org/en/latest/autogenerate.html]
**Why it happens:** Computed/GENERATED columns are outside Alembic's autogenerate comparison set.
**How to avoid:** After autogenerate, hand-edit the migration to render the column with the explicit clause via `sa.Column("extraction_yield_pct", sa.Numeric, sa.Computed("(yield_grams_actual * tds_pct) / dose_grams_actual", persisted=True))` OR raw `op.execute("ALTER TABLE ... ADD COLUMN extraction_yield_pct numeric GENERATED ALWAYS AS (...) STORED")`. SQLAlchemy 2.0 `Computed("expr", persisted=True)` renders `GENERATED ALWAYS AS (expr) STORED`. [CITED: docs.sqlalchemy.org/en/20/core/defaults.html — `Computed(persisted=True)`]
**Warning signs:** A migration diff where `extraction_yield_pct` looks like a normal writable column; an INSERT succeeding that sets EY directly; EY not auto-updating when yield/tds change.

### Pitfall 2: `multiple_of` on float rating rejects valid quarter values
**What goes wrong:** `Field(multiple_of=0.25)` on a `float` rating can reject `3.5` or `1.75` due to binary float representation (`0.25` is exact in binary but intermediate float math is not always), or accept near-misses.
**How to avoid:** Type the field as `Decimal` and pass `multiple_of=Decimal("0.25")`. Persist as `Numeric(3,2)`. The CSV importer must parse the rating string straight into `Decimal`, not via `float`.
**Warning signs:** Sporadic validation failures on round-trip of exported ratings; ratings drifting (3.50000004) in the DB.

### Pitfall 3: Observed/advertised flavor-note conflation
**What goes wrong:** Reusing the Phase 4 `flavorNoteChips` factory as-is binds the chips to `advertised_flavor_note_ids` (per-coffee) instead of `flavor_note_ids_observed` (per-session); the form silently writes the wrong relationship, or worse, posts a name the coffee router expects.
**How to avoid:** New sibling factory `observedFlavorNotes` in `flavor-tag-input.js`, bound to `name="flavor_note_ids_observed"`, with the D-09 auto-create + "new" badge behavior the Phase 4 widget lacks. Distinct from the D-11 advertised quick-add chips (those READ `advertised_flavor_note_ids` to populate suggestions; they never write it).
**Warning signs:** Observed notes appearing as advertised notes on the coffee; the coffee form's notes changing after logging a brew.

### Pitfall 4: CSV import partial commit on a mid-file error
**What goes wrong:** Inserting rows one-at-a-time with per-row commits means a failure on row 30 leaves rows 1-29 committed — not idempotent, not a clean re-import.
**How to avoid:** Resolve + validate ALL rows first, collect outcomes, then INSERT accepted rows in a single transaction and commit once (BREW-11 explicit). Refused/skipped rows never enter the transaction. Render the summary after commit.
**Warning signs:** Re-importing the same file inserting duplicates; a 500 mid-import leaving a half-imported log.

### Pitfall 5: `bag_id`/`recipe_id`/equipment FK `ondelete` mismatch
**What goes wrong:** Using `RESTRICT` on `bag_id`/`recipe_id`/equipment FKs would block archiving/deleting catalog rows that have ever been brewed; using `CASCADE` would delete brew history when a recipe is removed.
**How to avoid:** `bag_id`/`recipe_id`/`brewer_id`/`grinder_id`/`kettle_id` → `ondelete="SET NULL"` (history survives, becomes freestyle). `coffee_id` → keep `RESTRICT` (a session must always know its coffee; the catalog uses archive-not-delete anyway). `user_id` → `RESTRICT` or `CASCADE` per how admin user-delete (ADMIN-01, Phase 9) should treat a user's logs — flag for planner; recommend `RESTRICT` so deleting a user with logs is a conscious admin action.
**Warning signs:** "cannot archive equipment referenced by a session" errors; brew history vanishing on recipe delete.

### Pitfall 6: `equipment.usage_count` drift on edit
**What goes wrong:** Incrementing on insert but not adjusting when a session edit changes the brewer/grinder/kettle, or not decrementing on session delete, makes the counter drift from reality (breaks the Phase 6 "most-used grinder" widget).
**How to avoid:** Service-layer logic in the same transaction: on create, +1 each non-null equipment FK; on update, diff old vs new FKs and ±1 the changed ones; on delete, -1 each. Handle all three FKs. (CONTEXT discretion recommends service-layer for exactly this testability.)
**Warning signs:** `usage_count` higher than the actual session count for that equipment.

## Code Examples

### Computed (GENERATED) column in the model
```python
# Source: docs.sqlalchemy.org/en/20/core/defaults.html (Computed, persisted=True)
from sqlalchemy import Numeric, Computed
from sqlalchemy.orm import Mapped, mapped_column

extraction_yield_pct: Mapped[Decimal | None] = mapped_column(
    Numeric,
    Computed("(yield_grams_actual * tds_pct) / dose_grams_actual", persisted=True),
)
# Renders: extraction_yield_pct NUMERIC GENERATED ALWAYS AS
#          ((yield_grams_actual * tds_pct) / dose_grams_actual) STORED
# NULL whenever any operand is NULL (SQL NULL propagation).
```

### Decimal rating field (Pydantic v2)
```python
# Source: pydantic docs — Decimal field with numeric constraints
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class BrewSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # mass-assignment defense (matches CoffeeCreate)
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))
    dose_grams_actual: Decimal = Field(..., gt=0, le=200)
    water_grams_actual: Decimal = Field(..., gt=0, le=3000)
    water_temp_c_actual: Decimal | None = Field(None, ge=0, le=100)
    yield_grams_actual: Decimal | None = Field(None, ge=0, le=3000)
    tds_pct: Decimal | None = Field(None, ge=0, le=100)
    flavor_note_ids_observed: list[int] = Field(default_factory=list)
    # NOTE: extraction_yield_pct is GENERATED — NOT a field here.
```

### CSV import skeleton (stdlib, single transaction)
```python
# Source: stdlib csv + the single-commit service pattern (app/services/equipment.py)
import csv, io
def import_brews(db, *, raw_bytes, user_id):
    reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
    outcomes, accepted = [], []
    for i, row in enumerate(reader, start=2):  # row 1 = header
        coffee = resolve_coffee(db, row)            # D-12
        if coffee is None or coffee == AMBIGUOUS:
            outcomes.append(("refused", i, reason)); continue
        bag_id = resolve_bag(db, coffee, row)       # D-13 (None ok; sentinel REFUSED -> refuse)
        if exists_session(db, user_id, coffee.id, brewed_at):  # D-14
            outcomes.append(("skipped", i, "duplicate of an existing session")); continue
        accepted.append(build_row(coffee, bag_id, row))
    for r in accepted:
        db.add(r)
    db.commit()  # single transaction
    return outcomes
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact on Phase 5 |
|--------------|------------------|--------------|-------------------|
| Compute derived metrics in app code | Postgres GENERATED columns (`Computed(persisted=True)`) | Postgres 12+ / SQLAlchemy 1.3.11+ | EY is a GENERATED column; app never computes it |
| `float` for fractional ratings | `Decimal` + `Numeric` | long-standing best practice | Avoids `multiple_of` float edge cases |
| Native `<input type=range>` for star ratings | Tap-on-stars with hidden numeric input | mobile-first era | Native range is unusable at 44px on 375px (MX-6); UI-SPEC locks tap-stars |
| Server-only form state | localStorage primary + server backstop | post-ITP (2020+) | BREW-06/07 dual-store design is the correct response to ITP eviction |

**Deprecated/outdated:**
- `psycopg2` → use `psycopg` 3 (`postgresql+psycopg://`) — already the project default.
- Legacy SQLAlchemy `Query` API → `select()`/`update()` — project convention.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact Beanconqueror CSV **column header strings** (literal labels) | CSV Import/Export | Importer header-alias map is wrong → real Beanconqueror files refused or mis-mapped. Mitigation: header-driven (not positional) importer + confirm against one real export before locking aliases. |
| A2 | Beanconqueror `brew_quantity` vs `brew_beverage_quantity` map to water-in vs yield-out respectively | CSV mapping table | Dose/water/yield columns swapped on import. Confirm against a real export. |
| A3 | Beanconqueror rating uses a 0-5 scale (vs 0-10) | CSV mapping table | Imported ratings off by 2x. Confirm + add a scale-conversion step. |
| A4 | EY numerator `yield_grams_actual` = beverage mass (in the cup), matching the standard EY formula | Schema section | EY values wrong/inverted. Confirm the semantic of `yield_grams_actual` with John (beverage out, not spent grounds). |
| A5 | iOS Safari 7-day ITP eviction applies to this self-hosted first-party PWA's access pattern | Draft Persistence | Lower-than-assumed eviction risk — but the server backstop neutralizes this regardless, so low impact. |
| A6 | `water_temp_c_actual` precision (Integer vs Numeric) | Schema | Cosmetic; planner picks. Decimal allows 92.5°C; Integer is fine for whole-degree logging. |

## Open Questions (RESOLVED)

1. **Exact Beanconqueror export header strings (A1-A3).** — RESOLVED: addressed by Plan 03 header-driven alias table + execution-time confirmation.
   - What we know: the internal `Brew` field names (verified from source); `grind_weight`=dose, `grind_size`=grind setting (verified by the difluid converter).
   - What's unclear: the literal column headers the Excel/CSV export emits, the rating scale, and the water-in vs yield-out column semantics.
   - Recommendation: build a **header-driven** importer with a case-insensitive alias map; have John run one "Export → Excel" from Beanconqueror and paste the header row before the planner locks the alias table. The Snobbery-native export format (D-15) is the authoritative round-trip format regardless.

2. **EY formula semantics (A4).** — RESOLVED: gated by Plan 01 Task 0 decision checkpoint.
   - What we know: CONTEXT specifies `(yield_grams_actual * tds_pct) / dose_grams_actual`.
   - What's unclear: whether `yield_grams_actual` is beverage mass (the standard EY input) and whether `tds_pct` is stored as a percent (e.g. 1.35) or a fraction (0.0135) — this changes the formula's scale by 100x.
   - Recommendation: confirm with John; the GENERATED expression must match the stored unit of `tds_pct` (likely `× tds_pct / 100` if tds is stored as a whole percent like 1.35).

3. **`user_id` ondelete policy for brew_sessions (Pitfall 5).** — RESOLVED: gated by Plan 01 Task 0 decision checkpoint, recommended RESTRICT.
   - Recommendation: `RESTRICT` so admin user-delete (Phase 9) consciously handles a user's logs; flag for the planner to confirm against ADMIN-01 intent.

4. **Clear-on-logout localStorage mechanism.** — RESOLVED: addressed by Plan 05 brew-draft.js + auth-router logout clear.
   - Recommendation: clear `snobbery:draft:brew:*` keys on `/login` render when no session is present (covers shared-device); confirm vs a `brew-draft.js`-driven approach.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 16 | GENERATED column, ARRAY, indexes | ✓ | 16 (locked) | — |
| SQLAlchemy 2.0 / Alembic / Pydantic v2 / FastAPI | All backend | ✓ | pinned (installed) | — |
| Python stdlib `csv`, `decimal`, `zoneinfo` | CSV, rating, tz | ✓ | 3.12 | — |
| HTMX 2.0.10 + Alpine CSP 3.15.12 (CDN) | Forms, filters, components | ✓ | in `base.html` | — |
| pytest (+ pytest-asyncio, respx) | Validation tests | ✗ (not in prod image) | — | Install into running container per CLAUDE.md (`pip install --user pytest ...`) or build a dev image |
| Playwright | MOB-06 375px no-zoom assertion (TEST-06) | unknown | — | TEST-06 is deferred to Phase 12; not a Phase 5 blocker |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** pytest (install into container per CLAUDE.md). Playwright assertion for MOB-06 is deferred to Phase 12 — Phase 5 only needs to ensure no brew input overrides font-size below 16px.

## Validation Architecture

> Nyquist validation is enabled (`workflow.nyquist_validation: true`). Tests are added per-task per CLAUDE.md; the formal suite is Phase 12. pytest is NOT in the production image — install into the running container or use a dev image (Wave 0).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=9.0,<10` + pytest-asyncio + respx (HTTP mocking, not needed for Phase 5) |
| Config file | none baked into the prod image — pytest installed at test time per CLAUDE.md |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest -q tests/test_brew_*.py` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BREW-01 | `extraction_yield_pct` is GENERATED: insert dose/yield/tds → DB read-back returns computed EY; NULL when any input NULL; INSERT cannot set it | integration (DB read-back) | `pytest tests/test_brew_schema.py::test_extraction_yield_generated -x` | ❌ Wave 0 |
| BREW-01 | `flavor_note_ids_observed` ARRAY round-trips (write list[int] → read list[int]) | integration | `pytest tests/test_brew_schema.py::test_observed_notes_array -x` | ❌ Wave 0 |
| BREW-04 | Rating Decimal validates 0/2.5/5; rejects 5.5, 3.3 (not 0.25 step); accepts 1.75 | unit | `pytest tests/test_brew_schema.py::test_rating_decimal_steps -x` | ❌ Wave 0 |
| BREW-02/05 | Form POST with valid data inserts; invalid → 200 + fragment with errors (SEC-06) | integration (TestClient) | `pytest tests/test_brew_router.py::test_form_validation_200 -x` | ❌ Wave 0 |
| BREW-04/03 | EY/ratio readout are NOT submitted/written (EY GENERATED, ratio no column) | unit | `pytest tests/test_brew_router.py::test_ey_not_writable -x` | ❌ Wave 0 |
| BREW-09 | `/brew/new?from={id}` prefills all-but rating/notes/observed | integration | `pytest tests/test_brew_prefill.py::test_brew_again_blanks_per_attempt -x` | ❌ Wave 0 |
| BREW-04/05/06 | Prefill source resolution (D-04 last session, recipe-wins D-05, open-bag D-06) | integration | `pytest tests/test_brew_prefill.py -x` | ❌ Wave 0 |
| BREW-07 | Draft reconciliation: server restore only when localStorage empty (server-side: draft upsert/get/clear) | integration | `pytest tests/test_brew_drafts.py -x` | ❌ Wave 0 |
| BREW-11 | CSV import: refused row (coffee not in catalog), skipped-duplicate (D-14 dedup), inserted; single transaction (no partial commit on mid-file error) | integration | `pytest tests/test_brew_csv.py::test_import_outcomes -x` | ❌ Wave 0 |
| BREW-10/D-15 | CSV export resolves ids→names, includes ratio + EY, re-imports cleanly (round-trip) | integration | `pytest tests/test_brew_csv.py::test_export_roundtrip -x` | ❌ Wave 0 |
| BREW-10 | Sessions list scoped to current user only (per-user isolation) | integration | `pytest tests/test_brew_router.py::test_list_user_scoped -x` | ❌ Wave 0 |
| equipment usage_count | +1 on create, diff on edit, -1 on delete, 3 FKs | unit | `pytest tests/test_brew_sessions_service.py::test_usage_count -x` | ❌ Wave 0 |
| MOB-06 | No brew input sets font-size <16px (no-zoom) | manual/Playwright | grep templates for `text-xs`/font-size overrides on inputs; Playwright 375px assertion **deferred to Phase 12 (TEST-06)** | ❌ Phase 12 |
| CSP | brew templates have no `\|safe`, no `hx-on:`, no `x-model` | static grep (existing CI grep tests cover `pages/`) | existing grep test extends to new templates automatically | ✅ existing |

### Sampling Rate
- **Per task commit:** `docker compose exec coffee-snobbery python -m pytest -q tests/test_brew_*.py` (the new brew test files).
- **Per wave merge:** full suite `python -m pytest -q`.
- **Phase gate:** full suite green + CSP grep tests pass before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/conftest.py` — transactional-rollback DB fixture + a logged-in TestClient fixture (if not already present from Phase 4 tests).
- [ ] `tests/test_brew_schema.py` — GENERATED EY read-back, ARRAY round-trip, Decimal rating steps (BREW-01, BREW-04).
- [ ] `tests/test_brew_router.py` — SEC-06 200-fragment validation, EY-not-writable, user-scoping (BREW-02, BREW-10).
- [ ] `tests/test_brew_prefill.py` — D-04/05/06/08 prefill resolution (BREW-02, BREW-09).
- [ ] `tests/test_brew_drafts.py` — draft upsert/get/clear, reconciliation order (BREW-07).
- [ ] `tests/test_brew_csv.py` — import outcomes + single-txn + round-trip export (BREW-10, BREW-11).
- [ ] `tests/test_brew_sessions_service.py` — `usage_count` increment/decrement across 3 FKs + edits.
- [ ] Framework install: `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` (or a dev image / compose profile — deferred ops work noted in `04-01-SUMMARY.md`).

## Security Domain

> `security_enforcement` is not set to `false` in config → enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `require_user` on every brew route; sessions scoped to `request.state.user.id` (existing) |
| V3 Session Management | yes | Existing custom session middleware; draft cleared on logout (MX-5) |
| V4 Access Control | yes | **Per-user isolation** — every brew query filtered by `user.id`; a user must never read/edit/export another user's sessions or draft. Verify ownership on `/brew/{id}/edit`, `/brew/{id}` POST, `/brew/export`, and draft endpoints (object-level access control / IDOR defense) |
| V5 Input Validation | yes | Pydantic v2 schemas with `extra="forbid"` (mass-assignment defense, T-04-MASS); numeric ranges; CSV row validation; rating Decimal constraints |
| V6 Cryptography | no | No new secrets; no encryption in this phase |
| V12 Files/Resources | yes | CSV upload: reject oversized before buffering (mirror photo guard); validate content-type; decode defensively (`utf-8-sig`); never `eval`/exec row data |
| V14 Config | yes | CSRF on every form (brew form, draft POST, import form); security headers ride existing middleware (no change) |

### Known Threat Patterns for FastAPI + HTMX + Postgres

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — editing/exporting another user's session by id | Elevation / Info disclosure | Filter every read/write by `user_id`; 404 (not 403) on cross-user `/brew/{id}` access to avoid leaking existence |
| SQL injection via CSV field / filter param | Tampering | SQLAlchemy `select()`/parameterized queries (never string-format SQL); citext name match via bound params |
| Mass assignment (`is_admin`, `user_id` override in form) | Tampering / Elevation | `ConfigDict(extra="forbid")`; server sets `user_id` from `request.state.user.id`, never from the form |
| CSV formula injection (cells starting `=`,`+`,`-`,`@`) in export opened in Excel | Tampering (downstream) | Prefix risky leading chars with `'` on export, OR document that export is for re-import not spreadsheet macros; planner picks — low risk at household scale but note it |
| Stored XSS via notes/flavor-note name rendered unescaped | Tampering | Jinja autoescape ON; no `\|safe` (SEC-05 grep test); refused-reason strings + chip names autoescaped (UI-SPEC lock) |
| CSRF on draft autosave / import | Spoofing | `X-CSRF-Token` via global `htmx-listeners.js` (HTMX) or manual meta read (fetch); hidden field on forms |
| Draft store leaking across users on a shared device | Info disclosure | localStorage key namespaced by `user_id` (MX-5); clear on logout; server draft keyed by `user_id` |

## Sources

### Primary (HIGH confidence)
- Codebase (source of truth): `app/models/{coffee,bag,recipe,equipment,flavor_note,user}.py`, `app/routers/coffees.py`, `app/services/{equipment,form_validation}.py`, `app/schemas/{coffee,recipe}.py`, `app/static/js/alpine-components/{autocomplete,recipe-step-builder}.js`, `app/static/js/htmx-listeners.js`, `app/migrations/versions/p4_shared_catalog.py`, `app/events.py`, `app/dependencies/auth.py`, `app/config.py`, `app/templates/base.html`, `app/routers/auth.py` — verified directly.
- `.planning/phases/05-brew-sessions/05-CONTEXT.md` + `05-UI-SPEC.md` (locked decisions + UI contract).
- docs.sqlalchemy.org/en/20/core/defaults.html — `Computed(persisted=True)` GENERATED ALWAYS AS STORED syntax.
- alembic.sqlalchemy.org/en/latest/autogenerate.html — autogenerate detection list (computed columns absent → hand-edit required).
- pydantic.dev/docs/validation/latest/concepts/fields/ + api/types — Decimal fields + numeric constraints.
- github.com/graphefruit/Beanconqueror `src/classes/brew/brew.ts` — verified internal Brew field names.

### Secondary (MEDIUM confidence)
- github.com/Toby-Broom/difluid2Beanconqueror README — confirms `grind_weight`=dose, `grind_size`=grind setting in Beanconqueror's import format.
- webkit.org ITP blog — 7-day script-writable-storage cap (general behavior).

### Tertiary (LOW confidence — flagged for validation)
- Beanconqueror Excel/CSV literal **column header strings** — NOT verified (export-service source unreachable without GitHub auth; docs don't enumerate). Best-effort mapping in Assumptions A1-A3; confirm against a real export.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use; versions pinned/verified.
- Architecture/patterns: HIGH — Phase 5 composes verified Phase 0-4 patterns; new code mirrors shipped files.
- Schema (GENERATED column, ARRAY, indexes): HIGH — `Computed(persisted=True)` confirmed; GIN/GENERATED hand-edit has a direct in-repo precedent; EY formula UNIT/semantics flagged (A4, Q2).
- CSV mapping: MEDIUM (internal field names verified) / LOW (literal export headers unverified — A1-A3, Q1).
- Pitfalls: HIGH — each is verified against docs or in-repo precedent.

**Research date:** 2026-05-19
**Valid until:** ~2026-06-18 (30 days — stable stack; the only volatile item is the Beanconqueror export format, which should be confirmed from a real file regardless of date).
