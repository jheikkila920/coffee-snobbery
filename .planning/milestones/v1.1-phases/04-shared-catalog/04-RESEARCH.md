# Phase 4: Shared Catalog - Research

**Researched:** 2026-05-18
**Domain:** FastAPI + HTMX CRUD surfaces over PostgreSQL with Pillow-driven image upload pipeline and Pydantic-v2 universal form-validation pattern
**Confidence:** HIGH

## Summary

Phase 4 has unusually heavy upstream lock-in. CONTEXT D-01..D-16 (16 decisions) plus a fully-specified UI-SPEC.md plus Phase 0-3 patterns (sync `SessionLocal`, audit-event taxonomy, CSP-strict Alpine, CSRFFormFieldShim) leave the planner with very little discretion. The research job here is depth on **how** each locked decision is wired in code, not what to choose.

The five hardest surfaces are: (1) the SEC-07 photo pipeline (magic-byte → Pillow re-encode → EXIF strip → resize → thumb → write-new-then-delete-old), (2) the universal Pydantic-v2 form-validation pattern that catches `ValidationError` and re-renders the form fragment at HTTP 200, (3) the `ARRAY(BigInteger)` + JSONB SQLAlchemy types with the right `mapped_column` shapes and GIN-index hand-edits the alembic autogenerate misses, (4) the HTMX 2.0.10 fragment + OOB + `HX-Trigger` event plumbing for the autocomplete-mini-modal-pre-select flow, (5) the Alpine CSP-build component pattern Phase 1 D-01 already locked.

**Primary recommendation:** Build the photo pipeline first (it has the most failure modes and unblocks UI work), then the Pydantic form pattern (reused by every router), then per-entity CRUD routers in roaster → flavor-note → coffee → equipment → recipe order. Bags + photo upload nests under coffee detail last.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Catalog CRUD (list / create / edit / archive) | API (FastAPI routers + sync SessionLocal) | Browser (HTMX inline-expand swap) | State is shared across users; server is the single source of truth. D-01 locks HTMX fragments, not modals. |
| Form validation | API (Pydantic v2 schemas) | Browser (HTML5 advisory `min`/`max`/`step`) | D-04 + SEC-06: server is authoritative. Browser hints are convenience only. |
| Photo decode + re-encode + EXIF strip | API (Pillow in `app/services/photos.py`) | Browser (canvas downscale per D-05, NOT a security boundary) | Server cannot trust client bytes (PITFALL SEC-4). Client downscale is bandwidth optimization only. |
| Photo storage | Filesystem (named volume `coffee_snobbery_photos` at `/app/data/photos`) | DB (`bags.photo_filename` text) | Spec lock; named volume avoids SH-4 UID issues. |
| Photo serving | API (custom router with auth gate) | — | D-06: NOT a `StaticFiles` mount. Auth-gated, anonymous → 404 (not 403). |
| Autocomplete on roaster + flavor-note | API (GET endpoint returns `<ul role="listbox">` fragment) | Browser (HTMX `hx-trigger="input changed delay:350ms"` + Alpine keyboard nav) | D-13 + D-14: HTMX drives the data, Alpine drives the interaction. PITFALL HX-4 mandates 350ms debounce + min 2 chars + `hx-sync="this:replace"`. |
| Recipe step builder | Browser (Alpine CSP-build component, local array, computed Δ + cumulative readouts) | API (single JSON submit on save) | D-09: zero round-trips during editing. Pydantic validates the array server-side on submit. |
| Mini-modal (D-15) | Browser (Alpine `Alpine.data('miniModal')` component) | API (POST returns `HX-Trigger: roaster-created` + empty body) | D-15 + D-16: parent form listens for the event payload, pre-selects the new entity. |
| Filter state | URL (browser via `hx-push-url`) | API (GET endpoint reads `?roaster=&country=&...` query params) | D-03: back/forward replays filters; users bookmark/share filtered views. |
| Soft-delete | API (services set `archived=true`) | — | All five catalog entities use `archived` bool; never hard-delete in v1 (planner's recommendation in CONTEXT). |
| Audit events | API (structlog calls at write paths) | — | Phase 1 D-14 taxonomy; Phase 4 extends with `catalog.<entity>.<action>` events. |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CAT-01 | `roasters` table + autocomplete-on-create-on-save | §"5 Catalog Models" (Roaster schema), §"Autocomplete + Mini-Modal Pattern" (D-13..D-16 wiring), §"HTMX 2.0.10 Patterns" (`HX-Trigger` header) |
| CAT-02 | `flavor_notes` table + 9-value category enum + autocomplete-on-create | §"5 Catalog Models" (FlavorNote schema), §"Enum-vs-CHECK Pattern" (text + CHECK per Phase 3 D-01 precedent) |
| CAT-03 | `coffees` table + `advertised_flavor_note_ids` array + soft-delete + CRUD UI | §"5 Catalog Models" (Coffee schema with `ARRAY(BigInteger)`), §"Alembic Autogenerate Quirks" (GIN index hand-edit) |
| CAT-05 | `equipment` table + type enum + archive-on-reference | §"5 Catalog Models" (Equipment schema), §"Usage Count Column" (denormalized; 0 in Phase 4, incremented in Phase 5) |
| CAT-06 | `recipes` table + JSONB `steps` + step builder + duplicate action | §"5 Catalog Models" (Recipe with `JSONB`), §"Recipe Step Builder" (Alpine component shape), §"`HX-Redirect` for Duplicate" |
| CAT-07 | Coffees mobile card-list at <768px + 4-dimension filter | §"Filter Bar with `hx-push-url`" + §"Card-vs-Table Responsive Pattern" |
| CAT-08 | Bag photo upload pipeline (Canvas → magic-byte → Pillow → resize → 400px thumb) | §"Photo Upload Pipeline" (full byte-flow), §"Client-Side Canvas Downscale (D-05)" |
| SEC-06 | Pydantic v2 form validation with explicit numeric ranges | §"Universal Pydantic v2 Form-Validation Pattern" |
| SEC-07 | Image upload magic-byte + Pillow decode + EXIF strip + 5MB rejection | §"Photo Upload Pipeline" (steps 1-6 byte-flow + Pillow API verbatim) |

## Project Constraints (from CLAUDE.md)

The planner MUST honor these directives without exception:

- **Stack lock:** Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy 2.0, Jinja2 + HTMX + Tailwind (CDN) + Alpine.js, **no npm build pipeline**, argon2-cffi, Fernet, APScheduler in-process, Docker Compose with `coffee-snobbery` + `coffee-snobbery-db`.
- **Format:** `ruff format` before commit; `ruff check` warnings = errors.
- **Type hints:** required on function signatures; use `from __future__ import annotations`.
- **Pydantic v2** for request/response/form schemas.
- **SQLAlchemy 2.0 style:** typed `Mapped[...]` columns, `select()` constructs, no legacy `Query` API.
- **Templates:** 2-space indent, snake_case for variables, autoescape ON, **never `|safe`** on user content.
- **CSS:** Tailwind utility classes only; custom CSS only in `app/static/css/custom.css` when utilities don't cover it (Phase 4 should not need this).
- **JavaScript:** Alpine.js inline, vanilla JS in `app/static/js/` for anything heavier; no npm.
- **Architectural invariants Phase 4 MUST preserve:**
  - "Coffees, equipment, recipes, roasters, flavor notes are shared across users." (no `user_id` column on any Phase 4 table)
  - "Mobile-first: any UI change tested at 375px viewport."
  - "CSRF on all state-changing forms" — every POST template carries `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">` (the Phase 2 CSRFFormFieldShim handles hoisting).
  - "Security headers on every response" — Phase 1's middleware already does this; Phase 4 doesn't disable per-route.
- **Things to never do silently:**
  - Drop or rename a column in a migration without a data-preservation plan.
  - Bypass `services/encryption.py` (irrelevant in Phase 4, but stated).
  - Add a new endpoint that skips CSRF.

## User Constraints (from CONTEXT.md)

CONTEXT.md for Phase 4 is unusually prescriptive. Reproduced verbatim below; the planner MUST honor these as locked.

### Locked Decisions (D-01..D-16 from CONTEXT)

**CRUD interaction pattern:**
- **D-01: HTMX fragments throughout.** All five entity surfaces are HTMX-driven. The list page is the canonical surface. POST returns a row fragment that's `hx-swap`'d into the list; OOB swaps update count badges. No classic POST→303 inside the catalog.
- **D-02: Add/Edit form lives as an inline expand on the list page**, not as a modal or separate page. Click "Add coffee" → `hx-get` fetches the form fragment which renders as a top-of-list expandable row.
- **D-03: Filter state uses `hx-push-url` on every filter change.** Browser back/forward replays filters; users bookmark and share filtered views. PITFALL HX-2 already mitigated by Phase 1's `FragmentCacheHeadersMiddleware`.
- **D-04: Form validation errors re-render the whole inline form fragment with field-level errors.** Server returns HTTP **200** (not 422). Pydantic ValidationError caught, user's submitted values preserved, inline error messages render next to each invalid field.

**Photo upload + serving pipeline:**
- **D-05: Client-side Canvas downscale to ~2000px max edge before POST.** Vanilla JS in `app/static/js/photo-upload.js` (~80 LOC). Server STILL re-encodes — client downscale is UX/bandwidth optimization, not security measure.
- **D-06: Auth-gated photo serving route with opaque UUID filenames.** `GET /photos/{uuid}.jpg`. Anonymous → **404, not 403**. `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`. NOT a `StaticFiles` mount.
- **D-07: Synchronous unlink on replace and on bag hard-delete; nightly orphan-sweep ships now (scheduler registration is Phase 8).** Replace = write-new-then-delete-old. Bag soft-delete keeps the photo.
- **D-08: Photos attach to bags only — coffees have no separate photo column at v1.**

**Recipe step builder mechanics:**
- **D-09: Alpine.js local array, single JSON submit on save.** Zero server round-trips during editing.
- **D-10: A step captures `water_grams` (cumulative target) + `time_seconds` (elapsed time at that target) + `label`.**
- **D-11: Vertical bar pour-timeline preview with proportional segments.**
- **D-12: Duplicate-recipe is an immediate server-side copy + HTMX redirect** (`HX-Redirect` response header) to the new recipe's edit form.

**Autocomplete-on-create UX:**
- **D-13: From inside a parent form, an unmatched typed value surfaces an explicit "+ Create new" option in the autocomplete dropdown.** `hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"` (HX-4 pattern).
- **D-14: PITFALL HX-3 dodge — no `hx-swap-oob` on the flavor-notes datalist. Use `hx-get` on field focus to refresh.**
- **D-15: Clicking "+ Create new …" opens a mini-modal** with the entity's full editable fields. Modal POSTs to `/roasters` or `/flavor-notes`, server inserts and returns an `HX-Trigger` response header carrying `roaster-created` event with `{roaster_id, name}` payload.
- **D-16: New entity creation pre-selects in the parent field after modal close.**

### Claude's Discretion (CONTEXT-allowed planner choice)

- Exact `coffees` schema column choices (`country`, `process`, `roast_level`, `origin`, `varietal`, `notes`, etc.) — planner enumerates exact columns + nullability.
- Exact `process` / `roast_level` / `equipment.type` enum values (recommendation: text + CHECK per Phase 3 D-01 precedent).
- Whether to use Postgres ENUM vs text+CHECK — established precedent is text + CHECK.
- Sort order defaults on each list.
- Whether the coffee list shows the latest bag thumbnail.
- `archived=true` UX surface (toggle button, separate URL state, or both).
- Empty array vs NULL for `coffees.advertised_flavor_note_ids` (recommendation: empty array).
- How the coffee detail surfaces "open new bag" (recommendation: inline-expand per D-02).
- Hard-delete vs soft-delete for un-referenced entities (recommendation: archive-only from day one).
- Modal close-on-Escape / focus-trap depth.
- Mobile breakpoint for table→card collapse (Tailwind `md` = 768px; aligns with ROADMAP).
- Photo MIME validation depth (hand-roll signature check is fine for three formats).
- HEIC support (recommendation: rely on D-05 Canvas → JPEG path; reject HEIC on JS-off fallback).
- Whether to ship `/photos/{uuid}/thumb` variant or fixed filename suffix (recommendation: suffix `{uuid}-thumb.jpg`).

### Deferred Ideas (OUT OF SCOPE for Phase 4)

- Bag list page (`/bags`) as standalone surface
- Step `pour_duration` / `technique` / `agitation` fields on recipes
- Recipe versioning
- Hierarchical flavor wheel UI
- Coffee hero photo (separate from bag photo)
- HEIC-from-iOS-without-JS (Pillow + `pillow-heif`)
- Bulk actions on catalog lists
- Coffee/equipment photo galleries
- Inline edit of roaster/flavor-note metadata after inline-create (modal captures full fields at create-time per D-15)
- Real-time collaboration / WebSocket
- Search across catalog from inside the coffee form (Phase 10 owns global search)
- Coffee-list `bags-open` count column (Phase 5)
- Recipe difficulty/skill-level tag

## Standard Stack

All versions verified against existing repo `pyproject.toml` and `.planning/research/STACK.md` (researched 2026-05-16). Pillow, Pydantic, SQLAlchemy, Alembic already installed from Phases 0-3; no new pip dependencies needed for Phase 4.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `>=0.136,<0.137` | Route handlers, `Form(...)` / `File(...)` / `UploadFile` | [CITED: STACK.md §1] Already installed; uses `lifespan` only (no startup/shutdown) |
| SQLAlchemy | `>=2.0.49,<2.1` | `Mapped[...]` typed columns, `select()` / `update()` | [VERIFIED: pyproject.toml] Phase 0 D-13 established `Mapped[...]` as the project pattern |
| Alembic | `>=1.18,<2.0` | Migration for 5 new tables + FK + photo_filename column | [CITED: STACK.md §1] Autogenerate handles `Mapped[...]` |
| Pydantic | `>=2.13,<3.0` | Form schema with `Field(ge=..., le=...)` + `HttpUrl` + `ValidationError` | [CITED: STACK.md §1] SEC-06 universal validation pattern |
| Pillow | `>=12.2,<13` | Magic-byte verify, decode+re-encode, EXIF strip, thumbnail | [CITED: STACK.md §1] Pinned in Phase 0; first consumer is Phase 4 |
| python-multipart | `>=0.0.28,<0.1` | Form parsing + multipart photo upload | [CITED: STACK.md §1] Already pulled in by FastAPI dep |
| HTMX (CDN) | 2.0.10 | Fragment swaps, `hx-push-url`, `HX-Trigger`, `hx-sync` | [VERIFIED: app/templates/base.html:16] Already loaded |
| Alpine.js CSP build | 3.14.9 | Recipe step builder, mini-modal, autocomplete keyboard nav | [VERIFIED: app/templates/base.html:14] Phase 1 D-01 locks the CSP build |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | `>=25.5,<26` | Audit events: `catalog.<entity>.<action>` | At every service-layer write path per Phase 1 D-14 |
| psycopg (binary) | `>=3.3,<3.4` | Postgres driver; supports `CITEXT`, `JSONB`, `ARRAY` | URL prefix `postgresql+psycopg://` |
| starlette-csrf | `>=3.0,<4` | CSRF on every Phase 4 form (via CSRFFormFieldShim) | Already wired in `app/main.py`; Phase 4 templates carry the hidden input |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled magic-byte check | `filetype>=1.2` library | [VERIFIED: STACK.md §2 row "Image processing"] STACK.md recommends "just use Pillow + manual signature check on the first 8 bytes — no extra dep." Three formats is trivial; library is overkill. |
| `pillow-heif` for HEIC support | Reject HEIC with friendly error | D-05 client Canvas downscale naturally produces JPEG, so the JS-on path side-steps HEIC. Only JS-off iOS would hit it — defer per CONTEXT `<deferred>`. |
| Postgres ENUM types | `text` + `CHECK` constraint | Phase 3 D-01 precedent: "text + CHECK is more agile if a third value lands later." [VERIFIED: app/migrations/versions/p3_api_credentials.py:88] |
| Join table for `coffees ↔ flavor_notes` | `ARRAY(BigInteger)` + GIN index | CONTEXT `<specifics>` locks the array: (1) order matters (roaster's advertised sequence), (2) it's denormalized advertised-list, not observed-list. |
| Native HTML `<datalist>` for autocomplete | `<ul role="listbox">` fragment | UI-SPEC §"Autocomplete Dropdown" — native `<datalist>` doesn't render "+ Create new" rows or match highlighting. |

### Installation

No new dependencies. Verify these are already in `pyproject.toml`:

```bash
docker compose exec coffee-snobbery python -c "import PIL, pydantic, sqlalchemy, fastapi; print(PIL.__version__, pydantic.VERSION, sqlalchemy.__version__, fastapi.__version__)"
```

Expected output (per STACK.md pins): `12.2.x 2.13.x 2.0.49 0.136.x`.

**Version verification (planner runs before Wave 0 finalization):**

```bash
docker compose exec coffee-snobbery pip show pillow pydantic sqlalchemy fastapi alembic
```

If any pin drifted (Pillow upper bound, Pydantic minor) — note in plan and reconcile against STACK.md.

## Architecture Patterns

### System Architecture Diagram

```
                Browser (Phone, 375px viewport)
                    │
                    │ 1. GET /coffees (full page)
                    │ 2. HX-GET /coffees/new       ← inline-expand form fragment
                    │ 3. HX-POST /coffees          ← Pydantic-validates form
                    │ 4. HX-POST /bags/{id}/photo  ← multipart upload
                    │ 5. GET /photos/{uuid}.jpg    ← auth-gated serve
                    ▼
        ┌────────────── FastAPI middleware stack ──────────────┐
        │ RequestContext → SecurityHeaders → FragmentCache →   │
        │ CSRFFormFieldShim → CSRFMiddleware → SessionMW       │
        │                                                       │
        │ (Phase 1 + Phase 2 wiring; Phase 4 doesn't modify it)│
        └──────────────────────┬───────────────────────────────┘
                               │
        ┌──────────────────────┴───────────────────────────────┐
        │                 Phase 4 routers                       │
        │  app/routers/coffees.py     ← list + CRUD + filters  │
        │  app/routers/roasters.py    ← list + CRUD + datalist │
        │  app/routers/flavor_notes.py← list + CRUD + datalist │
        │  app/routers/equipment.py   ← list + CRUD            │
        │  app/routers/recipes.py     ← list + CRUD + dup      │
        │  app/routers/bags.py        ← nested under /coffees  │
        │  app/routers/photos.py      ← auth-gated FileResponse│
        └──────────────────────┬───────────────────────────────┘
                               │
              ┌────────────────┴─────────────────┐
              │                                  │
              ▼                                  ▼
   ┌─────────────────────┐         ┌──────────────────────┐
   │ Pydantic schemas    │         │ Service modules      │
   │ (form validation)   │         │ (sync DB + audit)    │
   │ app/schemas/        │         │ app/services/        │
   │  coffee.py          │         │  coffees.py          │
   │  roaster.py         │         │  roasters.py         │
   │  flavor_note.py     │         │  flavor_notes.py     │
   │  equipment.py       │         │  equipment.py        │
   │  recipe.py          │         │  recipes.py          │
   │  bag.py             │         │  bags.py             │
   │                     │         │  photos.py  ← Pillow │
   └──────────┬──────────┘         └──────────┬───────────┘
              │                               │
              │   ValidationError →           │
              │   re-render fragment @ 200    │
              │                               │
              ▼                               ▼
        ┌──────────────────────────────────────┐
        │  SQLAlchemy 2.0 sync (SessionLocal)  │
        │  app/db.py                           │
        └─────────────────┬────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────┐
        │  PostgreSQL 16 (coffee-snobbery-db)  │
        │  + citext + pg_trgm + unaccent       │
        │  New tables: coffees, roasters,      │
        │              flavor_notes, equipment,│
        │              recipes                 │
        │  Modified: bags (+FK, +photo_filename│
        │                                       │
        │  Photos volume: /app/data/photos/    │
        │  {uuid}.jpg + {uuid}-thumb.jpg       │
        └──────────────────────────────────────┘
```

### Component Responsibilities

| Component | Owns | Does NOT own |
|-----------|------|--------------|
| `app/routers/{entity}.py` | HTTP shape, form parsing, response template selection, HTMX header emission | DB writes, business rules, audit events |
| `app/services/{entity}.py` | DB queries, soft-delete logic, audit-event emission, transaction boundaries | HTTP, templates, form parsing |
| `app/services/photos.py` | Magic-byte check, Pillow decode + re-encode + EXIF strip + thumbnail, atomic file replace, orphan sweep | DB writes (bags.photo_filename) — that's `app/services/bags.py` |
| `app/schemas/{entity}.py` | Pydantic v2 form schemas with `Field(ge=, le=, min_length=, max_length=)` ranges | Business rules (uniqueness, referential integrity — those happen in services) |
| `app/templates/pages/{entity}.html` | Full-page list view with inline form mount + filter bar | Single row / form fragment rendering — those go in `fragments/` |
| `app/templates/fragments/*.html` | Single-row, form-fragment, datalist, mini-modal, pour-timeline templates | Full page chrome (extends base.html only at page level) |
| `app/static/js/photo-upload.js` | Client-side Canvas downscale (D-05) | Server-side validation (server still re-encodes per SEC-4) |
| `app/static/js/alpine-components/recipe-step-builder.js` | Local step array, Δ computeds, JSON serialization on submit | DB persistence, validation (server does it) |
| `app/static/js/alpine-components/mini-modal.js` | Modal open/close, ESC handler, backdrop click, HTMX event listening | Form data, network calls (HTMX does those) |
| `app/static/js/alpine-components/autocomplete.js` | Keyboard nav, selection commit, "+ Create new" event dispatch | Server filtering (HTMX does that) |

### Recommended Project Structure

```
app/
├── models/
│   ├── coffee.py          # NEW — Mapped[...] columns
│   ├── roaster.py         # NEW
│   ├── flavor_note.py     # NEW
│   ├── equipment.py       # NEW
│   ├── recipe.py          # NEW
│   ├── bag.py             # MODIFIED — add FK constraint + photo_filename
│   └── __init__.py        # MODIFIED — re-export new models
├── routers/
│   ├── coffees.py         # NEW
│   ├── roasters.py        # NEW (+ /roasters/list autocomplete endpoint)
│   ├── flavor_notes.py    # NEW (+ /flavor-notes/datalist endpoint)
│   ├── equipment.py       # NEW
│   ├── recipes.py         # NEW (+ /recipes/{id}/duplicate)
│   ├── bags.py            # NEW (nested under /coffees/{id}/bags)
│   └── photos.py          # NEW (auth-gated GET /photos/{uuid}.{ext})
├── services/
│   ├── coffees.py         # NEW — list_coffees, create_coffee, update_coffee, archive_coffee
│   ├── roasters.py        # NEW
│   ├── flavor_notes.py    # NEW
│   ├── equipment.py       # NEW
│   ├── recipes.py         # NEW + duplicate_recipe
│   ├── bags.py            # NEW + bag_photo_attach / bag_photo_replace / bag_photo_delete
│   └── photos.py          # NEW — Pillow pipeline + sweep_orphans
├── schemas/
│   ├── coffee.py          # NEW — CoffeeCreate, CoffeeUpdate, CoffeeFilter
│   ├── roaster.py         # NEW
│   ├── flavor_note.py     # NEW
│   ├── equipment.py       # NEW
│   ├── recipe.py          # NEW (RecipeCreate + nested RecipeStep)
│   └── bag.py             # NEW
├── templates/
│   ├── pages/
│   │   ├── coffees.html
│   │   ├── coffee_detail.html
│   │   ├── roasters.html
│   │   ├── flavor_notes.html
│   │   ├── equipment.html
│   │   └── recipes.html
│   └── fragments/                # NEW directory (currently empty)
│       ├── coffee_row.html
│       ├── coffee_form.html
│       ├── coffee_list.html       # used by filter HX-GET
│       ├── coffee_filters_panel.html
│       ├── roaster_row.html
│       ├── roaster_form.html
│       ├── roaster_modal.html     # D-15 mini-modal body
│       ├── flavor_note_row.html
│       ├── flavor_note_form.html
│       ├── flavor_note_modal.html
│       ├── equipment_row.html
│       ├── equipment_form.html
│       ├── recipe_row.html
│       ├── recipe_form.html
│       ├── recipe_step_builder.html
│       ├── pour_timeline.html
│       ├── bag_row.html
│       ├── bag_form.html
│       ├── photo_upload_zone.html
│       └── autocomplete_list.html   # generic <ul role="listbox">
├── static/js/
│   ├── photo-upload.js                          # NEW — D-05 Canvas downscale
│   └── alpine-components/                       # NEW directory
│       ├── recipe-step-builder.js
│       ├── mini-modal.js
│       └── autocomplete.js
├── migrations/versions/
│   └── p4_shared_catalog.py    # NEW — 5 tables + FK + photo_filename
└── events.py                   # MODIFIED — add catalog.* event constants
```

### Pattern 1: Universal Pydantic v2 Form-Validation Pattern (SEC-06, D-04)

**What:** Each state-changing route accepts form data, builds a Pydantic schema, catches `ValidationError`, and re-renders the inline form fragment at HTTP 200 with field-level errors.

**When to use:** Every Phase 4 POST/PATCH route that accepts user form data. This is the template Phase 5+ form routes consume.

**Pattern — service constructs schema from `Form(...)` parameters:**

```python
# app/schemas/coffee.py — [ASSUMED API; planner verifies against Pydantic 2.13 docs]
from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl


class CoffeeCreateForm(BaseModel):
    """Form schema for POST /coffees. SEC-06 numeric ranges."""

    name: str = Field(..., min_length=1, max_length=200)
    roaster_id: int = Field(..., ge=1)
    country: str | None = Field(None, max_length=80)
    process: str | None = Field(None, max_length=40)
    roast_level: str | None = Field(None, max_length=40)
    advertised_flavor_note_ids: list[int] = Field(default_factory=list)
    notes: str = Field("", max_length=2000)


class RecipeStepSchema(BaseModel):
    """Per-step Pydantic sub-schema for the JSONB array. CONTEXT <specifics>."""

    water_grams: int = Field(..., ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)


class RecipeCreateForm(BaseModel):
    """Recipe form. JSONB steps validated as a list[RecipeStepSchema]."""

    name: str = Field(..., min_length=1, max_length=200)
    dose_grams: int = Field(..., ge=1, le=200)
    water_grams: int = Field(..., ge=1, le=2000)
    water_temp_c: int = Field(..., ge=0, le=100)
    grind_setting: str = Field("", max_length=120)
    steps: list[RecipeStepSchema] = Field(default_factory=list)
```

```python
# app/routers/coffees.py — pattern
from fastapi import APIRouter, Depends, Form, Request, status
from pydantic import ValidationError

from app.db import SessionLocal
from app.dependencies.auth import require_user
from app.schemas.coffee import CoffeeCreateForm
from app.services import coffees as coffee_service

router = APIRouter(prefix="/coffees", tags=["coffees"])


@router.post("")
def create_coffee(
    request: Request,
    name: str = Form(...),
    roaster_id: int = Form(...),
    country: str | None = Form(None),
    process: str | None = Form(None),
    roast_level: str | None = Form(None),
    advertised_flavor_note_ids: list[int] = Form(default_factory=list),
    notes: str = Form(""),
    user=Depends(require_user),
):
    """POST /coffees → 200 + row fragment OR 200 + form fragment with errors."""
    raw = {
        "name": name,
        "roaster_id": roaster_id,
        "country": country,
        "process": process,
        "roast_level": roast_level,
        "advertised_flavor_note_ids": advertised_flavor_note_ids,
        "notes": notes,
    }
    try:
        validated = CoffeeCreateForm.model_validate(raw)
    except ValidationError as exc:
        # D-04: re-render at HTTP 200 with submitted values + field errors
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="fragments/coffee_form.html",
            context={"values": raw, "errors": _errors_by_field(exc), "mode": "create"},
            status_code=200,
        )

    with SessionLocal() as db:
        coffee = coffee_service.create_coffee(
            db,
            user_id=user.id,
            data=validated.model_dump(),
        )

    # On success: return the new row fragment + OOB swap to clear the form mount
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/coffee_row.html",
        context={"coffee": coffee, "include_oob_form_clear": True},
        status_code=200,
    )


def _errors_by_field(exc: ValidationError) -> dict[str, str]:
    """Pivot Pydantic's err list into a flat {field_name: message} dict for the template."""
    out: dict[str, str] = {}
    for err in exc.errors():
        # err["loc"] is a tuple; field is the first non-int element
        loc = err.get("loc", ())
        field = next((str(p) for p in loc if not isinstance(p, int)), "_form")
        out[field] = err.get("msg", "Invalid value")
    return out
```

[ASSUMED: Pydantic 2.13 `ValidationError.errors()` returns the documented list-of-dicts shape with `loc`, `msg`, `type` keys. This has been stable across the 2.x line; planner verifies via the existing `app/schemas/auth.py` ValidationError handling.]

**Template fragment receives `values` + `errors` and re-paints invalid fields with red ring + error helper text** — matches UI-SPEC §"Form Validation Errors (D-04)" exactly.

### Pattern 2: HTMX Fragment Response with OOB + HX-Trigger (D-01, D-15, D-16)

**What:** POST returns a 200 response whose body is a fragment + headers that drive client-side side-effects (form clear, parent field pre-select, redirect, etc.).

**When to use:** Every catalog write returns row fragment + (optionally) OOB-clear the form. Mini-modal POSTs return empty body + `HX-Trigger` header.

**Example — coffee form success path:**

```python
# Server returns row fragment that includes an OOB-swap to clear the form mount:
# fragments/coffee_row.html:
#   <tr data-row id="coffee-{{ coffee.id }}">…</tr>
#   {% if include_oob_form_clear %}
#   <div id="coffee-form-mount" hx-swap-oob="innerHTML"></div>
#   {% endif %}
```

HTMX matches the OOB element by id and swaps its `innerHTML` to empty — clearing the inline form. [VERIFIED: HTMX 2.0.10 docs — `hx-swap-oob` accepts `outerHTML` / `innerHTML` / `beforebegin` etc.; default is `outerHTML`.] [CITED: https://htmx.org/attributes/hx-swap-oob/]

**Example — mini-modal POST success path (D-15, D-16):**

```python
# app/routers/roasters.py
from fastapi.responses import HTMLResponse
import json


@router.post("")
def create_roaster(
    request: Request,
    name: str = Form(...),
    location: str | None = Form(None),
    website: str | None = Form(None),
    notes: str = Form(""),
    as_modal: bool = Form(False),
    user=Depends(require_user),
):
    # ... validate via RoasterCreateForm ...
    # ... insert via roaster_service.create_roaster(...) -> Roaster row ...

    if as_modal:
        # D-15 + D-16: empty body + HX-Trigger header carries the event payload
        headers = {
            "HX-Trigger": json.dumps({
                "roaster-created": {"roaster_id": roaster.id, "name": roaster.name}
            }),
        }
        return HTMLResponse("", status_code=200, headers=headers)

    # Non-modal path: return the row fragment for the /roasters list page
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/roaster_row.html",
        context={"roaster": roaster, "include_oob_form_clear": True},
    )
```

Alpine listener on the parent coffee form receives the event and pre-selects the new roaster:

```javascript
// app/static/js/alpine-components/autocomplete.js — Alpine.data factory
// CSP-build compliant: registered, no inline JS expressions.
Alpine.data('roasterAutocomplete', () => ({
  selectedId: null,
  selectedName: '',
  query: '',
  init() {
    // Listen on window so the HX-Trigger event fires regardless of DOM scope
    window.addEventListener('roaster-created', (evt) => {
      const detail = evt.detail;
      this.selectedId = detail.roaster_id;
      this.selectedName = detail.name;
      this.query = detail.name;
    });
  },
  // ... keyboard nav, "+ Create new" dispatch ...
}));
```

[VERIFIED: HTMX 2.0.10 dispatches custom DOM events on `body` for every key in the `HX-Trigger` JSON payload; event detail is the value object.] [CITED: https://htmx.org/headers/hx-trigger/]

### Pattern 3: `hx-push-url` Filter State (D-03)

**What:** Filter changes fire `hx-get` against `/coffees?roaster=Onyx&archived=false` with `hx-push-url="true"` so the URL updates without a full reload.

**When to use:** Any list page with filters (coffees only in Phase 4 per CAT-07).

**Endpoint shape — distinguishes full-page vs fragment-only request via `HX-Request` header:**

```python
@router.get("")
def list_coffees(
    request: Request,
    roaster: str | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
):
    with SessionLocal() as db:
        coffees = coffee_service.list_coffees(db, roaster=roaster, country=country, process=process, archived=archived)

    if request.headers.get("HX-Request") == "true":
        # Fragment-only: just the list, not the whole page
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="fragments/coffee_list.html",
            context={"coffees": coffees, "filters": {...}},
        )

    # Full page on first load / direct URL
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="pages/coffees.html",
        context={"coffees": coffees, "filters": {...}},
    )
```

[VERIFIED: HTMX 2.0.10 sets `HX-Request: true` on every htmx-driven request; this is the canonical "is this an HTMX request" check.] [CITED: https://htmx.org/reference/#request_headers]

Phase 1's `FragmentCacheHeadersMiddleware` (D-11) automatically sets `Cache-Control: no-store + Vary: HX-Request` when `HX-Request` is true — Phase 4 routes do not need per-route headers.

### Pattern 4: Autocomplete Endpoint (D-13, D-14, HX-4)

**What:** Server returns `<ul role="listbox">` fragment with up to 50 matches + a synthetic "+ Create new" trailing option when no exact match exists.

```python
# app/routers/roasters.py
@router.get("/list")
def roaster_autocomplete(
    request: Request,
    q: str = "",
    user=Depends(require_user),
):
    """GET /roasters/list?q=onyx — returns <ul> fragment for the autocomplete dropdown."""
    if len(q) < 2:
        return HTMLResponse("", status_code=200)

    with SessionLocal() as db:
        matches = roaster_service.search_roasters(db, query=q, limit=50)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={
            "items": matches,
            "query": q,
            "create_new_label": f"+ Create new roaster: \"{q}\"",
            "create_new_endpoint": "/roasters/new?as_modal=true",
            "exact_match_found": any(r.name.lower() == q.lower() for r in matches),
        },
    )
```

**Template-side HTMX trigger (verbatim from CONTEXT D-13 + UI-SPEC):**

```html
<!-- fragments/coffee_form.html (roaster field) -->
<input
  type="text"
  name="roaster_query"
  x-data
  x-model="query"
  hx-get="/roasters/list"
  hx-trigger="input changed delay:350ms[target.value.length >= 2], focus once from:closest .field"
  hx-target="#roaster-dropdown"
  hx-swap="innerHTML"
  hx-sync="this:replace"
  autocomplete="off"
  class="rounded border border-espresso-200 px-3 py-2 text-base">
<input type="hidden" name="roaster_id" x-bind:value="selectedId">
<div id="roaster-dropdown"
     class="absolute top-full left-0 right-0 mt-1 ..."
     x-show="showDropdown"
     x-on:click.outside="showDropdown = false"></div>
```

[VERIFIED: HTMX 2.0.10 `hx-trigger` filter syntax `[expr]` evaluates a JS expression against `event.target`; `target.value.length >= 2` matches PITFALL HX-4 verbatim.] [CITED: https://htmx.org/attributes/hx-trigger/]
[VERIFIED: HTMX 2.0.10 `hx-sync="this:replace"` cancels in-flight requests on the same element when a new request fires — matches PITFALL HX-4 mitigation.] [CITED: https://htmx.org/attributes/hx-sync/]

**Per D-14: NO `hx-swap-oob` on this datalist.** When the mini-modal creates a new roaster, the next focus on this input re-fetches the full list via the `focus once` trigger — eliminates the HX-3 duplicate-ID race.

### Pattern 5: Photo Upload Pipeline (SEC-07, D-05..D-08)

**What:** Six-step server-side pipeline that defends against polyglot files (SEC-4), oversize uploads, and EXIF leakage.

**Byte-flow order (matters):**

1. **Reject before reading body** if `Content-Length > 5_242_880` (5MiB). FastAPI exposes this via `request.headers.get("content-length")`. Return 200 + form fragment with inline error.
2. **Magic-byte signature check** on the first 8 bytes of the file. Three formats supported (UI-SPEC `accept="image/jpeg,image/png,image/webp"`):
   - **JPEG:** `FF D8 FF E0` (JFIF) or `FF D8 FF E1` (EXIF) — bytes 0..3
   - **PNG:** `89 50 4E 47 0D 0A 1A 0A` — bytes 0..7 (full 8-byte signature)
   - **WebP:** `52 49 46 46 ?? ?? ?? ?? 57 45 42 50` — bytes 0..3 + bytes 8..11 (RIFF header + WEBP fourcc)
3. **Set `Image.MAX_IMAGE_PIXELS`** to a defensive cap (e.g., `2000 * 2000 * 4 = 16M` pixels) BEFORE opening — defends against decompression bombs.
4. **`Image.open()` + `Image.verify()`** to confirm the file is a structurally-valid image. `verify()` consumes the stream; must reopen after.
5. **Re-open with second `Image.open()` and call `.load()`** to fully decode the image data into memory.
6. **Re-encode by calling `Image.save(buffer, format="JPEG", quality=85)`** — this is the SEC-4 polyglot defense. Re-encoding strips any trailing non-image data appended to a valid JPEG.
7. **EXIF strip:** Pillow's `Image.save()` does NOT include EXIF unless explicitly passed `exif=image.info.get("exif")`. By calling `save()` without that kwarg, EXIF is automatically dropped. Belt-and-braces: call `image.getexif().clear()` before save.
8. **Resize** to max-edge 1600px via `image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)` (in-place; preserves aspect ratio).
9. **Generate 400px thumbnail** via a separate `thumbnail((400, 400))` on a copy.
10. **Write-new-then-delete-old:** save new main + thumb to temp filenames, `os.fsync()` after each, `os.replace(temp, final)` atomic rename, update DB row (`bags.photo_filename = uuid_hex + ".jpg"`), THEN `os.unlink(old_path)` if replacing.

[ASSUMED: Pillow 12.x API for `Image.open`, `Image.verify`, `Image.thumbnail`, `Image.save`, `Image.getexif`, `Image.Resampling.LANCZOS`, `Image.MAX_IMAGE_PIXELS`. These are stable across Pillow 8.x → 12.x per published changelogs; the planner SHOULD verify with `docker compose exec coffee-snobbery python -c "from PIL import Image; help(Image.thumbnail)"` and `help(Image.save)` before locking the implementation.]

**Concrete implementation skeleton:**

```python
# app/services/photos.py — [ASSUMED Pillow API; planner verifies in plan-phase]
from __future__ import annotations
import io
import os
import uuid
from pathlib import Path

import structlog
from PIL import Image, UnidentifiedImageError

from app.events import CATALOG_BAG_PHOTO_UPLOADED, CATALOG_PHOTO_ORPHAN_SWEPT

log = structlog.get_logger(__name__)

PHOTOS_DIR = Path("/app/data/photos")
MAX_BYTES = 5 * 1024 * 1024
MAX_DECODE_PIXELS = 2000 * 2000 * 4  # 16M pixels — DoS defense
MAIN_MAX_EDGE = 1600
THUMB_MAX_EDGE = 400
JPEG_QUALITY = 85

JPEG_MAGICS = (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xee", b"\xff\xd8\xff\xdb")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_RIFF = b"RIFF"
WEBP_FOURCC = b"WEBP"


class PhotoRejectedError(Exception):
    """Raised when a photo fails magic-byte / decode / size validation."""


def _check_magic_bytes(head: bytes) -> str:
    """Return 'jpeg' / 'png' / 'webp' or raise PhotoRejectedError."""
    if len(head) < 12:
        raise PhotoRejectedError("File too short")
    if any(head.startswith(m) for m in JPEG_MAGICS):
        return "jpeg"
    if head.startswith(PNG_MAGIC):
        return "png"
    if head.startswith(WEBP_RIFF) and head[8:12] == WEBP_FOURCC:
        return "webp"
    raise PhotoRejectedError("Unsupported image format")


def process_upload(raw_bytes: bytes) -> tuple[str, bytes, bytes]:
    """Validate, re-encode, EXIF-strip, resize, thumbnail.

    Returns (filename_uuid_hex, main_jpeg_bytes, thumb_jpeg_bytes).
    Raises PhotoRejectedError on any failure (planner maps to the inline error template).
    """
    if len(raw_bytes) > MAX_BYTES:
        raise PhotoRejectedError("Photo too large (max 5MB).")

    # Step 1: magic-byte gate
    _check_magic_bytes(raw_bytes[:12])

    # Step 2: DoS-cap before decode
    Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS

    # Step 3: verify (consumes the stream)
    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            probe.verify()
    except (UnidentifiedImageError, Exception) as exc:
        raise PhotoRejectedError("We couldn't read this image.") from exc

    # Step 4: re-open and load (verify() invalidates the file object)
    image = Image.open(io.BytesIO(raw_bytes))
    image.load()

    # Step 5: EXIF strip (belt-and-braces; save without exif= kwarg is the primary defense)
    try:
        image.getexif().clear()
    except Exception:
        pass  # not all formats expose getexif()

    # Step 6: convert mode (PNG with alpha → RGB; WebP → RGB)
    if image.mode not in ("RGB",):
        image = image.convert("RGB")

    # Step 7: main resize (in-place)
    image.thumbnail((MAIN_MAX_EDGE, MAIN_MAX_EDGE), Image.Resampling.LANCZOS)

    main_buf = io.BytesIO()
    image.save(main_buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    main_bytes = main_buf.getvalue()

    # Step 8: thumbnail (work on a copy so the main result isn't downsized again)
    thumb = image.copy()
    thumb.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE), Image.Resampling.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    thumb_bytes = thumb_buf.getvalue()

    filename_uuid = uuid.uuid4().hex
    return filename_uuid, main_bytes, thumb_bytes


def write_atomic(filename_uuid: str, main_bytes: bytes, thumb_bytes: bytes) -> str:
    """Atomic write of main + thumb; returns the canonical filename ("{uuid}.jpg")."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    main_path = PHOTOS_DIR / f"{filename_uuid}.jpg"
    thumb_path = PHOTOS_DIR / f"{filename_uuid}-thumb.jpg"
    main_tmp = main_path.with_suffix(".jpg.tmp")
    thumb_tmp = thumb_path.with_suffix(".jpg.tmp")

    for path, data in ((main_tmp, main_bytes), (thumb_tmp, thumb_bytes)):
        with open(path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    os.replace(main_tmp, main_path)   # atomic on POSIX
    os.replace(thumb_tmp, thumb_path)
    return f"{filename_uuid}.jpg"


def replace_photo(old_filename: str | None, filename_uuid: str, main_bytes: bytes, thumb_bytes: bytes) -> str:
    """Write new, then unlink old. Never delete-then-write."""
    new_filename = write_atomic(filename_uuid, main_bytes, thumb_bytes)
    if old_filename:
        # uuid is in the filename without -thumb suffix; derive both paths
        stem = old_filename.removesuffix(".jpg")
        old_main = PHOTOS_DIR / f"{stem}.jpg"
        old_thumb = PHOTOS_DIR / f"{stem}-thumb.jpg"
        for p in (old_main, old_thumb):
            try:
                p.unlink(missing_ok=True)
            except OSError as exc:
                # Log but don't fail the request — DB row already points at new
                log.warning("photos.unlink_failed", path=str(p), error_class=type(exc).__name__)
    return new_filename


def sweep_orphans(db) -> int:
    """Diff filesystem against bags.photo_filename. Returns count unlinked.

    Safe ordering: LIST FILES FIRST, then query DB, then unlink the diff.
    Doing it in reverse (unlinking a file that a freshly-inserted row references)
    is the load-bearing footgun.
    """
    if not PHOTOS_DIR.exists():
        return 0

    # 1. Snapshot filesystem
    on_disk: set[str] = set()
    for p in PHOTOS_DIR.iterdir():
        if p.is_file() and p.suffix == ".jpg":
            on_disk.add(p.name)

    # 2. Query referenced filenames
    from sqlalchemy import select
    from app.models.bag import Bag

    rows = db.execute(select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))).all()
    referenced: set[str] = set()
    for (fn,) in rows:
        referenced.add(fn)
        stem = fn.removesuffix(".jpg")
        referenced.add(f"{stem}-thumb.jpg")

    # 3. Diff and unlink
    orphans = on_disk - referenced
    count = 0
    for name in orphans:
        try:
            (PHOTOS_DIR / name).unlink()
            count += 1
        except OSError as exc:
            log.warning("photos.sweep_unlink_failed", name=name, error_class=type(exc).__name__)

    log.info(CATALOG_PHOTO_ORPHAN_SWEPT, count=count, total_on_disk=len(on_disk))
    return count
```

**FastAPI route — 5MB pre-buffer rejection:**

```python
# app/routers/bags.py
from fastapi import File, UploadFile, HTTPException


@router.post("/{bag_id}/photo")
async def upload_bag_photo(
    bag_id: int,
    request: Request,
    photo: UploadFile = File(...),
    user=Depends(require_user),
):
    # Pre-flight: content-length header (set by all modern clients)
    cl = request.headers.get("content-length")
    if cl and int(cl) > MAX_BYTES:
        # Render the inline error in the form fragment
        return _render_photo_error(request, "Photo too large (max 5MB). Try a smaller image.")

    # Read full body. UploadFile spools to disk after `spool_max_size` (default 1MB)
    # but await read() returns the full bytes; double-check size post-read.
    raw = await photo.read()
    if len(raw) > MAX_BYTES:
        return _render_photo_error(request, "Photo too large (max 5MB).")

    try:
        filename_uuid, main_bytes, thumb_bytes = photo_service.process_upload(raw)
    except photo_service.PhotoRejectedError as exc:
        return _render_photo_error(request, str(exc))

    with SessionLocal() as db:
        bag = bag_service.get_bag_or_404(db, bag_id)
        new_filename = photo_service.replace_photo(
            old_filename=bag.photo_filename,
            filename_uuid=filename_uuid,
            main_bytes=main_bytes,
            thumb_bytes=thumb_bytes,
        )
        bag_service.set_bag_photo(db, bag_id=bag.id, photo_filename=new_filename, by_user_id=user.id)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/bag_row.html",
        context={"bag": bag, "show_thumbnail": True},
    )
```

[NOTE: `UploadFile.read()` returns all bytes after spooling. For very tight memory budgets, you can stream-chunk + count bytes, but at 5MB cap on a household app this is fine. Planner picks during implementation.]

### Pattern 6: Auth-Gated Photo Serving Route (D-06)

```python
# app/routers/photos.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.dependencies.auth import require_user

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("/{filename}")
def serve_photo(filename: str, request: Request):
    """Auth-gated photo serve. Anonymous → 404 (NOT 403) per D-06."""
    # D-06: anonymous returns 404 to avoid leaking existence. Use a raw check,
    # NOT Depends(require_user) which would return 401.
    user = getattr(request.state, "user", None)
    if user is None:
        # Plain 404, no body
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Sanitize the filename — UUID hex + optional "-thumb" + ".jpg"
    if not _is_safe_photo_filename(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    photo_path = PHOTOS_DIR / filename
    if not photo_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # D-06 response headers (explicit; FileResponse sets Content-Type by extension)
    return FileResponse(
        photo_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


_SAFE_RE = re.compile(r"^[0-9a-f]{32}(-thumb)?\.jpg$")


def _is_safe_photo_filename(name: str) -> bool:
    """Reject anything that isn't <uuid-hex>.jpg or <uuid-hex>-thumb.jpg.

    Defense against path traversal and arbitrary file disclosure.
    """
    return bool(_SAFE_RE.match(name))
```

[VERIFIED: Phase 1's `FragmentCacheHeadersMiddleware` (D-11) sets `private, no-cache, must-revalidate` on every full-page response. The photo route MUST set its own `Cache-Control: private, max-age=31536000, immutable` because Phase 1 D-12 says "do not overwrite if already set by the route" — explicit route headers win. Planner re-verifies the middleware's "don't overwrite" logic during plan-phase.]

### Pattern 7: Client-Side Canvas Downscale (D-05)

**What:** Vanilla JS reads the selected file, draws to a `<canvas>` at max-edge 2000px, re-encodes JPEG quality 0.85, and substitutes the smaller blob into FormData before submit.

```javascript
// app/static/js/photo-upload.js — Vanilla JS (~80 LOC), CSP-compliant
// Loaded by base.html on pages that need it (Phase 4 picks: page-specific include OR base.html global).
//
// Form must work without JS — if this script is blocked/disabled the raw file
// posts and the server handles the full pipeline.

(function () {
  const MAX_EDGE = 2000;
  const JPEG_QUALITY = 0.85;

  function attachToForm(form) {
    const fileInput = form.querySelector('input[type="file"][data-photo-input]');
    if (!fileInput) return;

    form.addEventListener('submit', async (evt) => {
      const file = fileInput.files[0];
      if (!file) return; // no file selected; let the server handle missing

      // Skip processing if the file is already small or non-image
      if (!file.type.startsWith('image/') || file.size < 500_000) return;

      evt.preventDefault();
      try {
        const blob = await downscale(file);
        const newFile = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: 'image/jpeg' });
        const dt = new DataTransfer();
        dt.items.add(newFile);
        fileInput.files = dt.files;
      } catch (err) {
        // Downscale failed — fall through and submit the original
        console.warn('photo-upload: downscale failed, submitting original', err);
      }
      // Use HTMX's API if HTMX is driving the form; else manual submit
      if (window.htmx && form.hasAttribute('hx-post')) {
        htmx.trigger(form, 'submit');
      } else {
        form.submit();
      }
    }, { capture: false });
  }

  async function downscale(file) {
    const url = URL.createObjectURL(file);
    try {
      const img = await loadImage(url);
      const { width, height } = scaleToMaxEdge(img.naturalWidth, img.naturalHeight, MAX_EDGE);
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      return await new Promise((resolve, reject) => {
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new Error('toBlob returned null'))),
          'image/jpeg',
          JPEG_QUALITY
        );
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
  }

  function scaleToMaxEdge(w, h, maxEdge) {
    if (w <= maxEdge && h <= maxEdge) return { width: w, height: h };
    const ratio = w > h ? maxEdge / w : maxEdge / h;
    return { width: Math.round(w * ratio), height: Math.round(h * ratio) };
  }

  // Auto-wire any form on the page
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form[data-photo-form]').forEach(attachToForm);
  });
})();
```

**EXIF orientation handling:** Spec mentions reading EXIF for upright rotation. Modern Safari/Chrome auto-rotate `<img>` per EXIF when `image-orientation: from-image` (CSS default in modern browsers). For the canvas case, you must manually rotate. Decision: the server-side Pillow re-encode strips EXIF entirely, so the client downscale doesn't NEED to honor orientation — the user might see the photo rotated incorrectly in preview but the saved server copy is the canonical one. Recommended approach: skip orientation correction in JS at v1; if a real iPhone user reports a sideways photo, add the EXIF parser.

[ASSUMED: HTML5 Canvas `toBlob(callback, "image/jpeg", quality)` is universally supported (96%+ via caniuse.com). Planner can verify with the Phase 12 Playwright smoke at 375×667.]

### Pattern 8: Alpine CSP-Build Component (Phase 1 D-01)

**What:** Registered via `Alpine.data('name', factory)` in dedicated `app/static/js/alpine-components/*.js` files. CSP-strict — no inline expressions beyond declarative bindings (`x-show`, `x-model`, `x-for`, etc.).

```javascript
// app/static/js/alpine-components/recipe-step-builder.js
// Loaded by base.html (or page-specific include) AFTER alpine-csp core script.

document.addEventListener('alpine:init', () => {
  Alpine.data('recipeStepBuilder', (initial) => ({
    steps: initial?.steps?.length ? initial.steps : [{ water_grams: 0, time_seconds: 0, label: 'Bloom' }],

    addStep() {
      const last = this.steps[this.steps.length - 1] || { water_grams: 0, time_seconds: 0 };
      this.steps.push({
        water_grams: (last.water_grams || 0) + 50,
        time_seconds: (last.time_seconds || 0) + 45,
        label: '',
      });
    },

    removeStep(index) {
      this.steps.splice(index, 1);
    },

    moveUp(index) {
      if (index === 0) return;
      [this.steps[index - 1], this.steps[index]] = [this.steps[index], this.steps[index - 1]];
    },

    moveDown(index) {
      if (index >= this.steps.length - 1) return;
      [this.steps[index], this.steps[index + 1]] = [this.steps[index + 1], this.steps[index]];
    },

    // Computeds — CSP-build accepts function references on component scope
    deltaWater(index) {
      if (index === 0) return this.steps[0].water_grams;
      return this.steps[index].water_grams - this.steps[index - 1].water_grams;
    },

    deltaTime(index) {
      if (index === 0) return this.steps[0].time_seconds;
      return this.steps[index].time_seconds - this.steps[index - 1].time_seconds;
    },

    get totalWater() {
      return this.steps.length ? this.steps[this.steps.length - 1].water_grams : 0;
    },

    get totalTime() {
      return this.steps.length ? this.steps[this.steps.length - 1].time_seconds : 0;
    },

    // For the hidden input on submit
    get stepsJson() {
      return JSON.stringify(this.steps);
    },
  }));

  Alpine.data('miniModal', () => ({
    open: false,
    dirty: false,

    show() { this.open = true; },
    close() {
      if (this.dirty && !confirm('Discard unsaved changes?')) return;
      this.open = false;
      this.dirty = false;
    },

    init() {
      window.addEventListener('keydown', (evt) => {
        if (evt.key === 'Escape' && this.open) this.close();
      });
    },
  }));
});
```

[VERIFIED: Alpine 3.x CSP build supports `Alpine.data('name', factory)`, getter properties via ES6 `get x()` syntax, and method references in templates like `x-text="deltaWater(idx)"`. The CSP build rejects arbitrary expression strings like `x-data="{ count: 0 }"` (would require `eval`).] [CITED: https://alpinejs.dev/advanced/csp]

**Template binding example — CSP-build compliant:**

```html
<!-- fragments/recipe_step_builder.html -->
<div x-data="recipeStepBuilder({ steps: {{ initial_steps | tojson }} })">
  <template x-for="(step, idx) in steps" x-bind:key="idx">
    <div class="flex gap-4 py-3">
      <button type="button" x-on:click="moveUp(idx)" x-bind:disabled="idx === 0"
              class="w-11 h-11" aria-label="Move step up">↑</button>
      <button type="button" x-on:click="moveDown(idx)" x-bind:disabled="idx === steps.length - 1"
              class="w-11 h-11" aria-label="Move step down">↓</button>
      <input type="text" x-model="step.label" placeholder="e.g., Bloom"
             class="rounded border px-2 py-2 text-base">
      <input type="number" x-model.number="step.water_grams" min="0" max="2000"
             inputmode="decimal" class="rounded border px-2 py-2 text-base w-20">
      <input type="text" x-model="step.time_seconds" pattern="\d+"
             inputmode="numeric" class="rounded border px-2 py-2 text-base w-20">
      <span class="text-sm text-espresso-600 tabular-nums"
            x-text="`Δ +${deltaWater(idx)}g · +${Math.floor(deltaTime(idx)/60)}:${String(deltaTime(idx)%60).padStart(2,'0')}`"></span>
      <button type="button" x-on:click="removeStep(idx)" class="w-11 h-11"
              x-bind:aria-label="`Remove step ${idx + 1}`">×</button>
    </div>
  </template>
  <button type="button" x-on:click="addStep()" class="...">+ Add step</button>

  <p class="text-base font-semibold" x-text="`Total water: ${totalWater}g · Total time: ${Math.floor(totalTime/60)}:${String(totalTime%60).padStart(2,'0')}`"></p>

  <!-- Hidden input serializes the array on submit -->
  <input type="hidden" name="steps" x-bind:value="stepsJson">
</div>
```

### Anti-Patterns to Avoid

- **DO NOT** use `hx-on:click="..."` inline handlers — banned by Phase 1 D-04. Use Alpine `x-on:click="methodName()"` against a registered component instead.
- **DO NOT** use `|safe` filter in any template — banned by Phase 1 SEC-05 + CI grep test.
- **DO NOT** return HTTP 422 on Pydantic ValidationError — D-04 mandates 200 + form fragment with inline errors.
- **DO NOT** mount `/photos` via `StaticFiles` — D-06 mandates a custom router with auth gate.
- **DO NOT** delete-then-write on photo replace — write-new-then-delete-old per D-07 (a crash mid-write destroys the only copy otherwise).
- **DO NOT** unlink-then-list on orphan sweep — list-then-unlink ordering is the load-bearing footgun (a freshly-inserted row's file could be unlinked otherwise).
- **DO NOT** use `Postgres ENUM` types when text + CHECK works — Phase 3 D-01 precedent says CHECK is more agile.
- **DO NOT** use `hx-swap-oob` to refresh the flavor-notes datalist — D-14 mandates `hx-get` on focus instead (PITFALL HX-3).
- **DO NOT** use `Image.open(...)` without setting `Image.MAX_IMAGE_PIXELS` first — decompression-bomb DoS.
- **DO NOT** call `Image.save(...)` with `exif=image.info.get('exif')` — that's the EXIF preservation pattern; we want it stripped. Default omission is correct.
- **DO NOT** add a `user_id` column to any catalog table — invariant: "Coffees, equipment, recipes, roasters, flavor notes are shared across users."

## 5 Catalog Models

Below are the recommended `Mapped[...]` shapes. Planner finalizes specifics during plan-phase.

```python
# app/models/roaster.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base


class Roaster(Base):
    __tablename__ = "roasters"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

```python
# app/models/flavor_note.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base


FLAVOR_CATEGORIES = ("fruit", "floral", "sweet", "chocolate", "nutty", "spice", "savory", "fermented", "other")


class FlavorNote(Base):
    __tablename__ = "flavor_notes"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)  # CHECK constraint via __table_args__
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('fruit','floral','sweet','chocolate','nutty','spice','savory','fermented','other')",
            name="flavor_notes_category_check",
        ),
    )
```

```python
# app/models/coffee.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base


class Coffee(Base):
    __tablename__ = "coffees"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    roaster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # FK added below
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    process: Mapped[str | None] = mapped_column(Text, nullable=True)        # text + CHECK
    roast_level: Mapped[str | None] = mapped_column(Text, nullable=True)    # text + CHECK
    varietal: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ARRAY of bigints referencing flavor_notes.id; empty array (NOT NULL) per CONTEXT discretion
    advertised_flavor_note_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'::bigint[]")
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # CHECK constraints hand-edited into the alembic migration (autogenerate misses these)
        CheckConstraint(
            "process IS NULL OR process IN ('washed','natural','honey','anaerobic','experimental','unknown')",
            name="coffees_process_check",
        ),
        CheckConstraint(
            "roast_level IS NULL OR roast_level IN ('light','medium-light','medium','medium-dark','dark','unknown')",
            name="coffees_roast_level_check",
        ),
    )
```

```python
# app/models/equipment.py
class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)   # CHECK
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Denormalized; ships at 0 in Phase 4. Phase 5 service-layer increments on session insert.
    usage_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "type IN ('brewer','grinder','kettle','scale','water_filter','other')",
            name="equipment_type_check",
        ),
    )
```

```python
# app/models/recipe.py
from sqlalchemy.dialects.postgresql import JSONB


class Recipe(Base):
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dose_grams: Mapped[int] = mapped_column(BigInteger, nullable=False)
    water_grams: Mapped[int] = mapped_column(BigInteger, nullable=False)
    water_temp_c: Mapped[int] = mapped_column(BigInteger, nullable=False)
    grind_setting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # JSONB list of {water_grams, time_seconds, label}. Validated by Pydantic per-step schema.
    steps: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

```python
# app/models/bag.py — MODIFIED: add FK + photo_filename
class Bag(Base):
    __tablename__ = "bags"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    coffee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("coffees.id", ondelete="RESTRICT"), nullable=False
    )  # FK added in Phase 4; ondelete RESTRICT per CONTEXT D-13/D-14 area
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # NEW Phase 4 column
    photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("ix_bags_coffee_id", "coffee_id"),)
```

**FK ondelete choice — RESTRICT vs CASCADE vs SET NULL for `bags.coffee_id`:**

`RESTRICT` is the right pick. Rationale:
- `CASCADE` would mass-delete bags when a coffee is hard-deleted — destroys history, surprising to the user, and bags reference sessions in Phase 5 (cascade would chain unpredictably).
- `SET NULL` would orphan bags from their coffee context — schema then violates the "every bag is of some coffee" invariant.
- `RESTRICT` (or `NO ACTION`) is the natural fail-loud default: hard-delete of a coffee with bags returns an IntegrityError. Combined with the CONTEXT discretion recommendation "archive-only from day one," coffees are never hard-deleted in practice.

[VERIFIED: SQLAlchemy 2.0 `ForeignKey("coffees.id", ondelete="RESTRICT")` emits `REFERENCES coffees(id) ON DELETE RESTRICT` in the migration.] [CITED: https://docs.sqlalchemy.org/en/20/core/constraints.html]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EXIF stripping | Custom binary parser of JPEG/PNG metadata segments | Pillow's `Image.save(...)` without the `exif=` kwarg (+ belt-and-braces `image.getexif().clear()`) | EXIF format is multi-vendor (JFIF, Exif, XMP, IPTC) — Pillow has 20+ years of edge cases. |
| Image decompression-bomb defense | Manual byte-size budgeting before decode | `Image.MAX_IMAGE_PIXELS = N` module-level setting | Pillow throws `Image.DecompressionBombWarning` / `DecompressionBombError` automatically when limit exceeded. |
| Magic-byte detection | The full `imghdr` (deprecated) or `python-magic` (libmagic dep) | Hand-roll 8-byte check for 3 formats (per STACK.md §2 row "Image processing") | Three formats is trivial; library is overkill. |
| HTMX-driven autocomplete with debounce + cancel-in-flight | Custom XHR-with-AbortController | HTMX `hx-trigger="input changed delay:350ms[expr]"` + `hx-sync="this:replace"` | HTMX 2.0.10 ships both natively; PITFALL HX-4 mandates this exact pattern. |
| CSRF on form posts | Custom token mint + verify | starlette-csrf (already wired) + `CSRFFormFieldShim` (Phase 2 D-15) | Already in place; Phase 4 templates just include the hidden input. |
| Filter URL state | Custom history API push + popstate listeners | HTMX `hx-push-url="true"` | One attribute. Browser back/forward replays. |
| Mini-modal focus trap | Full keyboard-trap library (e.g., focus-trap) | Browser default tab order + ESC handler + backdrop click | At household scale, full trap is overengineering. CONTEXT discretion note says "browser default tab order is acceptable for v1." |
| Tag-input / chips UI for flavor notes | Tagify / Choices.js (30KB+) | Hand-rolled Alpine component (STACK.md §2 row "Tag input UI") | Three behaviors only (autocomplete, commit, remove); Alpine + HTMX is ~50 LOC. (Phase 5 ships the full widget; Phase 4 ships the vocabulary it consumes.) |
| Soft-delete query helper | Custom SQLAlchemy event listener | Plain `WHERE archived = false` in service queries | One predicate per query; event listeners obscure the read path. |
| FileResponse with custom cache headers | Hand-roll a streaming response | FastAPI `FileResponse(..., headers={...})` | FastAPI handles range requests, content-type, and ETag for free. |

**Key insight:** Phase 4's hardest pieces (Pillow pipeline, HTMX patterns, Pydantic form validation) all have well-established libraries doing the heavy lifting. The Phase 4 code should be **glue** — wiring proven components into the project's architectural patterns — not new infrastructure.

## Runtime State Inventory

Phase 4 is **greenfield extension** of catalog tables and a brand-new photos volume — not a rename/refactor. State inventory items below confirm there's no hidden surface to migrate.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `bags` table exists from Phase 0 with `coffee_id BIGINT NOT NULL` (no FK) and zero rows in any deployed environment (no users yet). The Phase 4 migration adds the FK + `photo_filename` column on the empty table. | Migration only. No data migration needed because no rows reference the missing FK. |
| Live service config | None — no external services configured for catalog data at this phase. | None. |
| OS-registered state | None — no Task Scheduler, pm2, or systemd entries reference catalog state. The photos volume `/app/data/photos` is created lazily on first write by `app/services/photos.py::write_atomic`. | None — `PHOTOS_DIR.mkdir(parents=True, exist_ok=True)` in the service handles initial creation. |
| Secrets/env vars | None — Phase 4 adds no new env vars. CONTEXT `<specifics>` recommends `photo_max_bytes` stays as a module constant (already seeded in `app_settings` from Phase 0 D-17 as `photo_max_bytes = "5242880"`; planner picks: read via `settings.get_int("photo_max_bytes")` OR hardcode in `app/services/photos.py`). | None — the constant exists. |
| Build artifacts | None — no `.egg-info`, no compiled binaries depend on Phase 4 changes. | None. |

**The canonical question:** *After every file in the repo is updated, what runtime systems still have the old shape cached, stored, or registered?* — Nothing for Phase 4. This is purely additive.

## Common Pitfalls

### Pitfall 1: Pillow Decompression Bomb DoS

**What goes wrong:** Attacker uploads a tiny JPEG that decompresses to a billion-pixel image, exhausting RAM in the container.
**Why it happens:** Pillow's default decompression-bomb limit is conservative but not zero (~89M pixels). Specially-crafted PNGs and JPEGs can exceed even that.
**How to avoid:** Set `Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS` (e.g., 16M for a 4000×4000 max) at the top of `app/services/photos.py`. Pillow raises `DecompressionBombError` before allocating; catch and translate to `PhotoRejectedError`.
**Warning signs:** Container OOM-killed on uploads; uvicorn restart-loops; suspicious `dd if=/dev/zero | gzip` patterns in upload bodies.

### Pitfall 2: `Image.verify()` Invalidates the File Object

**What goes wrong:** Code calls `verify()` then tries to call `save()` on the same `Image` instance; `save()` raises `IOError`.
**Why it happens:** `verify()` consumes the underlying file stream as part of its check. The Pillow docs document this; many devs miss the warning.
**How to avoid:** Always pair `verify()` with a fresh `Image.open()` afterward:
```python
with Image.open(io.BytesIO(raw_bytes)) as probe:
    probe.verify()
image = Image.open(io.BytesIO(raw_bytes))   # fresh open
image.load()
```
**Warning signs:** `IOError: image file is truncated` or `OSError: cannot identify image file` on save after a verify pass.

### Pitfall 3: Alembic Autogenerate Misses PG-Specific Bits

**What goes wrong:** Generated migration omits `CHECK` constraints, GIN indexes for `ARRAY` / `JSONB`, and partial indexes.
**Why it happens:** Alembic's autogenerate looks at `Mapped[...]` and `__table_args__` but doesn't always serialize CHECK constraints (verified-with-Alembic-1.13 — assumed-still-true for 1.18; planner verifies). GIN/BRIN indexes for `ARRAY` and `JSONB` are NEVER autogenerated — they must be hand-edited in.
**How to avoid:**
1. Run `alembic revision --autogenerate -m "p4_shared_catalog"`.
2. **Hand-edit pass:** open the generated file and confirm every `CheckConstraint(...)` in `__table_args__` made it. Add `op.execute("CREATE INDEX ix_coffees_advertised_flavor_note_ids ON coffees USING GIN (advertised_flavor_note_ids)")` after the `op.create_table("coffees", ...)` line.
3. Run `alembic upgrade head` against a fresh DB to confirm no IntegrityError on the seeded values you plan to insert.
**Warning signs:** Tests fail with `IntegrityError: violates check constraint "coffees_process_check"` when none was created; queries against `advertised_flavor_note_ids @> ARRAY[5]` do a seq scan.

[ASSUMED: Alembic 1.18 still skips CHECK constraint detection in some scenarios. The official docs note "constraints are only partially autogenerated." Planner verifies before locking the migration shape.]

### Pitfall 4: HTMX OOB Swap Duplicate-ID Race (HX-3)

**What goes wrong:** A modal POST returns `hx-swap-oob="outerHTML:#flavor-notes-datalist"`; if the user submits twice quickly, two OOB responses both target the same ID — HTMX swaps the first, no-ops the second silently.
**Why it happens:** HTMX matches OOB by id; duplicate matches are non-deterministic.
**How to avoid:** PITFALL HX-3 + CONTEXT D-14 already locked the dodge: do NOT OOB-swap the autocomplete datalist. Use `hx-trigger="focus once from:closest .field"` to re-fetch on next focus. Phase 4 follows this verbatim — never `hx-swap-oob` on `/roasters/list` or `/flavor-notes/datalist` responses.
**Warning signs:** New roaster created in modal doesn't appear in the autocomplete dropdown until page refresh.

### Pitfall 5: HTMX Hammers DB on Autocomplete Without Debounce (HX-4)

**What goes wrong:** User typing "ethiopia" fires 8 requests in 350ms windows; each does a `pg_trgm` ILIKE across the table; 8× CPU on the DB.
**How to avoid:** Three measures stacked (PITFALL HX-4):
1. `hx-trigger="input changed delay:350ms"` — minimum 350ms idle.
2. `[target.value.length >= 2]` — skip if query shorter than 2 chars.
3. `hx-sync="this:replace"` — cancel in-flight on next keystroke.
All three lock together. CONTEXT D-13 mandates the exact pattern.
**Warning signs:** Postgres `pg_stat_statements` shows many near-identical ILIKE queries for `%e%`, `%et%`, `%eth%`.

### Pitfall 6: Polyglot Image Upload (SEC-4)

**What goes wrong:** Attacker uploads a file with a valid JPEG header but JS appended after the End-of-Image marker; server serves it back with `Content-Type: image/jpeg` but browser sniffs it as text/html and executes the JS.
**How to avoid:** Three-layer defense (PITFALL SEC-4):
1. **Re-encode after Pillow decode** — `Image.save(buf, format="JPEG", quality=85)` writes a fresh file with NO trailing data. This is the primary defense.
2. **`X-Content-Type-Options: nosniff`** on the serve response — D-06 mandates.
3. **`Content-Disposition: inline`** (NOT attachment, which can trigger downloads of disguised files) — D-06 mandates.
**Warning signs:** Penetration testing flags `/photos/{uuid}.jpg` as serving HTML or executable content.

### Pitfall 7: HTMX Form POST Returns 422 (D-04 Anti-Pattern)

**What goes wrong:** Pydantic `ValidationError` propagates as FastAPI's default 422 JSON; HTMX receives 422, does NOT swap (default `htmx.config.responseHandling` excludes 4xx) — user sees nothing change after clicking Save.
**Why it happens:** FastAPI's default handler converts `ValidationError` to a 422 JSON.
**How to avoid:** Catch `ValidationError` explicitly in the route, return HTTP 200 + the form fragment template re-rendered with `values` + `errors`. NEVER let the default 422 escape.
**Warning signs:** Save button appears to do nothing on a validation failure; browser network tab shows 422; HTMX docs note "non-200 responses don't swap by default."

### Pitfall 8: iOS Safari Form Field Auto-Zoom (MX-1)

**What goes wrong:** Tapping a form input with `font-size < 16px` zooms the viewport; doesn't zoom back. Phase 4 catalog forms become unusable on iPhone.
**How to avoid:** UI-SPEC enforces `text-base` (16px) on all form inputs. The global CSS rule lands in Phase 5 per ROADMAP, but Phase 4 templates already use `text-base` per UI-SPEC §Spacing.
**Warning signs:** User report "form jumps when I tap a field" on iPhone.

### Pitfall 9: Orphan Photo Sweep — Unlink-Before-List Race

**What goes wrong:** Sweep queries `bags.photo_filename` first, then lists files; in between, a fresh upload happens — the file exists, no DB row yet (still in flight), the sweep deletes the file.
**How to avoid:** **List filesystem first, then query DB, then unlink the diff.** Order matters — already documented in the photos.py skeleton above. Documenting again because it's load-bearing.

### Pitfall 10: HEIC Upload Falls Through to Pillow Without Decoder

**What goes wrong:** iOS Safari uploads a HEIC file (the user thinks it's JPEG); server-side Pillow raises `UnidentifiedImageError`.
**How to avoid:** The Canvas downscale (D-05) re-encodes to JPEG client-side, so the JS-on path side-steps HEIC entirely. For the JS-off fallback: catch `UnidentifiedImageError` in `process_upload` and surface "We couldn't read this image. Try a JPEG, PNG, or WebP." per UI-SPEC error copy. Do NOT add `pillow-heif` at v1 (CONTEXT `<deferred>`).
**Warning signs:** iOS user reports "couldn't read this image" with JS disabled.

## Code Examples

### Magic-byte signature check (hand-rolled, 3 formats)

```python
JPEG_MAGICS = (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xee", b"\xff\xd8\xff\xdb")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_RIFF = b"RIFF"
WEBP_FOURCC = b"WEBP"


def detect_format(head: bytes) -> str | None:
    if len(head) < 12:
        return None
    if any(head.startswith(m) for m in JPEG_MAGICS):
        return "jpeg"
    if head.startswith(PNG_MAGIC):
        return "png"
    if head.startswith(WEBP_RIFF) and head[8:12] == WEBP_FOURCC:
        return "webp"
    return None
```

Magic-byte sources [VERIFIED against Wikipedia / RFC]:
- JPEG `FF D8 FF` followed by JFIF (E0), Exif (E1), or others (E2-EF, DB) — [CITED: https://en.wikipedia.org/wiki/JPEG_File_Interchange_Format]
- PNG 8-byte signature `89 50 4E 47 0D 0A 1A 0A` — [CITED: RFC 2083 §3.1; https://www.w3.org/TR/PNG/#5PNG-file-signature]
- WebP `RIFF<size>WEBP` — [CITED: https://developers.google.com/speed/webp/docs/riff_container]

### Pydantic v2 ValidationError → field-keyed dict

```python
def errors_by_field(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        field = next((str(p) for p in loc if not isinstance(p, int)), "_form")
        out[field] = err.get("msg", "Invalid value")
    return out
```

[VERIFIED via `app/schemas/auth.py` usage pattern from Phase 2; `ValidationError.errors()` is the canonical Pydantic 2.x API.]

### HX-Redirect for Duplicate-Recipe (D-12)

```python
@router.post("/{recipe_id}/duplicate")
def duplicate_recipe(
    recipe_id: int,
    request: Request,
    user=Depends(require_user),
):
    with SessionLocal() as db:
        new_recipe = recipe_service.duplicate_recipe(db, recipe_id=recipe_id, by_user_id=user.id)

    return HTMLResponse(
        "",
        status_code=200,
        headers={"HX-Redirect": f"/recipes/{new_recipe.id}/edit"},
    )
```

[VERIFIED: HTMX 2.0.10 `HX-Redirect` response header tells the browser to do a full `window.location` navigation.] [CITED: https://htmx.org/headers/hx-redirect/]

### CSRF hidden input in every Phase 4 form template

```html
<form method="post" action="/coffees"
      hx-post="/coffees"
      hx-target="#coffee-form-mount"
      hx-swap="innerHTML"
      data-photo-form
      enctype="multipart/form-data">
  {# CSRFFormFieldShim hoists this into the X-CSRF-Token header. Same pattern as pages/setup.html:10. #}
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  ...
</form>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `imghdr` stdlib for magic-byte | Hand-rolled or `filetype` | `imghdr` deprecated in Python 3.11, removed in 3.13 | Already gone from stdlib; project must not import it |
| `Image.ANTIALIAS` resampling | `Image.Resampling.LANCZOS` | Pillow 9.1.0 (Mar 2022) | Old constant removed in Pillow 10.x — always use `Image.Resampling.*` |
| FastAPI `@app.on_event("startup")` | `lifespan` async context | Starlette 1.0 (Mar 2026) | Already lifespan in Phase 0 `app/main.py` |
| HTMX 1.9 `hx-on` | HTMX 2.x `hx-on:event` (banned in this project anyway per Phase 1 D-04) | HTMX 2.0 (Jun 2024) | Project uses Alpine for behavior, no `hx-on:` at all |
| Pydantic v1 `parse_obj` | Pydantic v2 `model_validate` | Pydantic 2.0 (Jun 2023) | Always use `model_validate` + `model_dump` |
| Postgres ENUM types | text + CHECK constraint | Phase 3 D-01 precedent | More agile when enum values evolve |

**Deprecated/outdated:**
- `imghdr` stdlib module — gone; never import.
- `Image.ANTIALIAS` — gone in Pillow 10+; use `Image.Resampling.LANCZOS`.
- Pydantic v1 `Config` class — replaced by `model_config = ConfigDict(...)` (Phase 4 form schemas may or may not need it; default is fine).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pydantic 2.13 `ValidationError.errors()` returns list of dicts with `loc`, `msg`, `type` keys | Pattern 1 + Code Examples | Form re-render path breaks; planner verifies by reading `app/schemas/auth.py` (Phase 2 working code) — high confidence this is unchanged |
| A2 | Pillow 12.x API for `Image.open`, `Image.verify`, `Image.thumbnail`, `Image.save`, `Image.getexif`, `Image.Resampling.LANCZOS`, `Image.MAX_IMAGE_PIXELS` is stable from 11.x → 12.x | Pattern 5 (Photo Pipeline) | Planner verifies with `docker compose exec coffee-snobbery python -c "from PIL import Image; help(Image.thumbnail); help(Image.save)"` during Wave 0; if API has shifted, adjust |
| A3 | Alembic 1.18 still skips CHECK constraint detection on autogenerate in some configurations | Pitfall 3 | Hand-edit pass catches it regardless; worst case the hand-edits are no-ops |
| A4 | Alembic 1.18 does NOT autogenerate GIN indexes for `ARRAY` / `JSONB` columns | Pitfall 3 + 5 Catalog Models | Always hand-add `op.execute("CREATE INDEX ... USING GIN ...")` — well-documented limitation |
| A5 | HTML5 `<canvas>.toBlob('image/jpeg', 0.85)` is universally supported (96%+) | Pattern 7 (Canvas Downscale) | If a user's browser doesn't support it, the form falls through to the server pipeline; D-05 explicitly says JS-off fallback works |
| A6 | `os.replace()` is atomic on POSIX (Linux/macOS) within the same filesystem | Pattern 5 (write_atomic) | Standard POSIX guarantee; Linux container always satisfies |
| A7 | The `coffee_snobbery_photos` named volume mounts at `/app/data/photos` inside the container | Pattern 5 | [VERIFIED: docker-compose.yml:61 `- coffee_snobbery_photos:/app/data/photos`] |
| A8 | `Image.MAX_IMAGE_PIXELS` setting is process-global; setting it once in `app/services/photos.py` module top is sufficient | Pattern 5 | Pillow docs confirm — it's a module-level attribute on `PIL.Image` |
| A9 | The `process` / `roast_level` CHECK constraint values used in this research are reasonable defaults | 5 Catalog Models | CONTEXT explicitly says planner picks the final values; recommendation is non-binding |
| A10 | `UploadFile.read()` returns the full body bytes after spooling to disk if size > 1MB | Pattern 5 (FastAPI route) | FastAPI documented behavior; planner verifies the spool threshold isn't surprising at 5MB cap |

**If any assumption fails verification:** the planner adjusts before locking the plan. Most are low-risk because of multiple defense layers (e.g., A4 wrong → still works without GIN, just slower; A1 wrong → existing `auth.py` consumer would already be broken).

## Open Questions (RESOLVED)

1. **`equipment.usage_count` update mechanism (Phase 5)**
   - What we know: column ships at 0 in Phase 4 (CONTEXT `<specifics>`); Phase 5 increments on session insert.
   - What's unclear: trigger vs service-layer increment.
   - RESOLVED: service-layer increment in `bag_session_service.create_session()` — keeps audit-event emission, transaction boundary, and update logic in one place. Document the convention now so Phase 5 doesn't drift.

2. **Filter UI on mobile**
   - What we know: UI-SPEC specifies a collapse-to-button + slide-down panel.
   - What's unclear: whether the panel is HTMX-fetched or pre-rendered + Alpine-toggled.
   - RESOLVED: HTMX-fetched (`hx-get="/coffees/filters-panel"`) — server is the single source of truth for "available filter values" (e.g., the list of roasters in the dropdown updates as roasters are created).

3. **Coffee detail bag-thumbnail surface**
   - What we know: CONTEXT discretion says "small visual enhancement under D-08; not required."
   - What's unclear: whether to ship in Phase 4 or defer.
   - RESOLVED: defer to Phase 5 — Phase 4 has plenty of surface area; adding the subquery + template clutter for "latest bag thumbnail per coffee" can wait until brew sessions exist and the enhancement earns its keep.

4. **Photo upload progress indicator implementation**
   - What we know: UI-SPEC shows a spinner + "Uploading… {filename}" overlay.
   - What's unclear: HTMX's built-in `htmx-indicator` class vs Alpine state flag.
   - RESOLVED: HTMX `htmx-indicator` class on the upload zone (same as forms); UI-SPEC §"Loading States" already locked this pattern.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Pillow | Photo pipeline (SEC-07) | ✓ (pinned in pyproject.toml) | ≥12.2,<13 (per STACK.md §1) | — |
| Pydantic 2.13+ | Form validation (SEC-06) | ✓ (already used in Phase 2 auth) | ≥2.13,<3 | — |
| SQLAlchemy 2.0.49+ | Mapped[...] models | ✓ (already used in Phases 0-3) | ≥2.0.49,<2.1 | — |
| Alembic 1.18+ | New migration | ✓ (already used in Phases 0-3) | ≥1.18,<2 | — |
| PostgreSQL 16 + citext + pg_trgm + unaccent extensions | All catalog tables | ✓ (Phase 0 `0001_initial.py` installs all three) | 16-alpine | — |
| `coffee_snobbery_photos` named Docker volume | Photo storage | ✓ (docker-compose.yml:77 `coffee_snobbery_photos`) | n/a | — |
| HTMX 2.0.10 (CDN) | All fragment swaps | ✓ (base.html:16) | 2.0.10 | — |
| Alpine 3.14.9 CSP build (CDN) | Recipe step builder, mini-modal, autocomplete | ✓ (base.html:14) | 3.14.9 | — |
| `python-multipart` | UploadFile parsing | ✓ (FastAPI dep) | ≥0.0.28,<0.1 | — |
| `starlette-csrf` + `CSRFFormFieldShim` | CSRF on every form POST | ✓ (Phase 2 wired) | ≥3.0,<4 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — Phase 4 introduces zero new pip dependencies.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0,<10 + pytest-asyncio (per STACK.md §2; already used in Phases 0-3) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) — verified during Wave 0 |
| Quick run command | `docker compose exec coffee-snobbery pytest tests/ -x -q` |
| Full suite command | `docker compose exec coffee-snobbery pytest tests/ --cov=app` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CAT-01 | Roaster CRUD + `name` citext unique | unit | `pytest tests/test_routers_roasters.py -x` | ❌ Wave 0 |
| CAT-01 | Autocomplete returns `<ul>` with "+ Create new" suffix when no exact match | unit | `pytest tests/test_routers_roasters.py::test_autocomplete_appends_create_new -x` | ❌ Wave 0 |
| CAT-02 | Flavor note CRUD + category CHECK constraint | unit | `pytest tests/test_routers_flavor_notes.py -x` | ❌ Wave 0 |
| CAT-02 | Mini-modal POST returns `HX-Trigger: flavor-note-created` + empty body | unit | `pytest tests/test_routers_flavor_notes.py::test_modal_post_emits_hx_trigger -x` | ❌ Wave 0 |
| CAT-03 | Coffee CRUD + `advertised_flavor_note_ids` ARRAY round-trip | unit | `pytest tests/test_routers_coffees.py -x` | ❌ Wave 0 |
| CAT-03 | Soft-delete sets `archived=true` and excludes from default list | unit | `pytest tests/test_services_coffees.py::test_archive_excludes_from_list -x` | ❌ Wave 0 |
| CAT-05 | Equipment grouped by type, usage_count starts at 0 | unit | `pytest tests/test_routers_equipment.py -x` | ❌ Wave 0 |
| CAT-06 | Recipe steps JSONB round-trip preserves order | unit | `pytest tests/test_services_recipes.py::test_steps_jsonb_round_trip -x` | ❌ Wave 0 |
| CAT-06 | Duplicate-recipe returns `HX-Redirect` to new edit page | unit | `pytest tests/test_routers_recipes.py::test_duplicate_emits_hx_redirect -x` | ❌ Wave 0 |
| CAT-07 | Filter URL state survives back/forward via `hx-push-url` | integration | `pytest tests/test_coffee_filters.py -x` | ❌ Wave 0 |
| CAT-07 | Filtered list query honors `?roaster=&country=&process=&archived=` params | unit | `pytest tests/test_services_coffees.py::test_filter_combinations -x` | ❌ Wave 0 |
| CAT-08 | Bag photo upload: valid JPEG → 200 + thumbnail saved | unit | `pytest tests/test_services_photos.py::test_jpeg_round_trip -x` | ❌ Wave 0 |
| CAT-08 | Bag photo replace: write-new-then-delete-old; old file unlinked | unit | `pytest tests/test_services_photos.py::test_replace_unlinks_old -x` | ❌ Wave 0 |
| CAT-08 | Orphan sweep: file on disk with no bags row gets deleted | unit | `pytest tests/test_services_photos.py::test_sweep_orphans -x` | ❌ Wave 0 |
| SEC-06 | Pydantic ValidationError → 200 + form fragment with errors (not 422) | unit | `pytest tests/test_form_validation.py::test_validation_error_returns_200 -x` | ❌ Wave 0 |
| SEC-06 | Numeric range violations caught (`Field(ge=0, le=100)`) | unit | `pytest tests/test_schemas.py -x` | ❌ Wave 0 |
| SEC-07 | Magic-byte mismatch (e.g., HTML masquerading as .jpg) rejected | unit | `pytest tests/test_services_photos.py::test_magic_byte_rejection -x` | ❌ Wave 0 |
| SEC-07 | Oversize photo (>5MB) rejected before buffering | unit | `pytest tests/test_services_photos.py::test_oversize_rejection -x` | ❌ Wave 0 |
| SEC-07 | EXIF stripped from saved photo | unit | `pytest tests/test_services_photos.py::test_exif_stripped -x` | ❌ Wave 0 |
| SEC-07 | Polyglot upload (valid JPEG + trailing JS) — saved file has no trailing data | unit | `pytest tests/test_services_photos.py::test_polyglot_stripped_by_reencode -x` | ❌ Wave 0 |
| SEC-07 | Decompression-bomb defense — pixel count exceeds MAX_IMAGE_PIXELS raises | unit | `pytest tests/test_services_photos.py::test_decompression_bomb_rejected -x` | ❌ Wave 0 |
| D-06 | Anonymous request to `/photos/{uuid}.jpg` returns 404 (NOT 403) | integration | `pytest tests/test_routers_photos.py::test_anonymous_returns_404 -x` | ❌ Wave 0 |
| D-06 | Authenticated request returns photo with correct headers | integration | `pytest tests/test_routers_photos.py::test_authed_returns_photo -x` | ❌ Wave 0 |
| D-06 | Path-traversal filename (`../etc/passwd`) returns 404 | unit | `pytest tests/test_routers_photos.py::test_unsafe_filename_404 -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_<module>.py -x` (the module touched by the task — typically <5s)
- **Per wave merge:** `pytest tests/ -x` (full suite — under 30s at Phase 4 scale)
- **Phase gate:** Full suite green + manual UAT against the 5 ROADMAP success criteria before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_routers_coffees.py` — covers CAT-03, CAT-07
- [ ] `tests/test_routers_roasters.py` — covers CAT-01
- [ ] `tests/test_routers_flavor_notes.py` — covers CAT-02
- [ ] `tests/test_routers_equipment.py` — covers CAT-05
- [ ] `tests/test_routers_recipes.py` — covers CAT-06
- [ ] `tests/test_routers_bags.py` — covers CAT-08 (bag CRUD)
- [ ] `tests/test_routers_photos.py` — covers D-06 (photo serving)
- [ ] `tests/test_services_coffees.py` — covers CAT-03 service-layer business rules
- [ ] `tests/test_services_recipes.py` — covers CAT-06 JSONB round-trip + duplicate
- [ ] `tests/test_services_photos.py` — covers SEC-07 (Pillow pipeline) + D-07 (orphan sweep)
- [ ] `tests/test_form_validation.py` — covers SEC-06 universal pattern
- [ ] `tests/test_schemas.py` — covers Pydantic schema range validation per entity
- [ ] `tests/test_coffee_filters.py` — covers CAT-07 filter URL state integration
- [ ] `tests/conftest.py` — extend with: `tmp_photos_dir` fixture (replaces `PHOTOS_DIR` with tmp), `make_jpeg_bytes` factory fixture (Pillow generates synthetic test images of N×N pixels), `make_oversize_file` fixture, `htmx_client` fixture (`TestClient` with `HX-Request: true` header pre-set)

*(All Phase 4 test files are new. Existing `tests/conftest.py` from Phases 0-3 already has transactional rollback fixtures and Pydantic schema patterns to follow.)*

## Security Domain

Phase 4 introduces the first user-controlled file upload surface in the app and the first multi-entity CRUD interface. The threat model is dominated by SEC-07 (image upload validation) and SEC-06 (form input validation).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | Phase 2's argon2id + session middleware — Phase 4 routes use `Depends(require_user)` |
| V3 Session Management | yes (inherited) | Phase 1/2 session cookie + CSRFFormFieldShim — Phase 4 forms carry the hidden CSRF input |
| V4 Access Control | yes | Anonymous catalog read = redirect to /login; anonymous `/photos/{uuid}` returns 404 (D-06). No per-row ACL since catalog is shared. |
| V5 Input Validation | **yes — primary phase concern** | Pydantic v2 schemas with explicit `Field(ge=, le=, min_length=, max_length=)` on every state-changing route; SEC-06 universal pattern |
| V6 Cryptography | no | Phase 4 adds no encrypted columns (encryption is Phase 3's domain). |
| V7 Errors & Logging | yes | structlog audit events at every catalog write path (`catalog.<entity>.<action>` per Phase 1 D-14); Pillow errors logged with error_class only (no body content). |
| V8 Data Protection | yes | Photos served `Cache-Control: private`; opaque UUID filenames defend against enumeration. |
| V10 Malicious Code | **yes — primary phase concern** | Polyglot-upload defense (SEC-4: re-encode after Pillow decode); magic-byte gate; decompression-bomb cap. |
| V13 API & Web Services | yes | All Phase 4 routes are CSRF-gated; CORS not relevant (same-origin app); CSP-strict (no `unsafe-eval`, no `hx-on:`). |
| V14 Configuration | yes (inherited) | Phase 0's locked uvicorn `--proxy-headers`, single worker, Postgres extension setup; Phase 4 changes none of this. |

### Known Threat Patterns for Phase 4 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection on filter params (`?roaster=`) | Tampering | SQLAlchemy 2.0 `select()` with parameter binding — never f-string SQL |
| XSS via coffee name in autocomplete row | Tampering / Information Disclosure | Jinja2 autoescape ON globally; never `|safe`; match highlighting uses server-side escape-then-wrap-with-`<strong>` |
| CSRF on POST endpoints (every form) | Tampering | CSRFFormFieldShim + `<input name="X-CSRF-Token">` hidden input pattern (Phase 2 D-15) |
| Polyglot image upload (valid JPEG + JS payload) | Spoofing / Tampering | Re-encode after Pillow decode (SEC-4); `X-Content-Type-Options: nosniff`; `Content-Disposition: inline` |
| Image decompression bomb (1GB-decoded tiny JPEG) | Denial of Service | `Image.MAX_IMAGE_PIXELS = 16M` cap before any decode |
| EXIF metadata leak (GPS coords from phone) | Information Disclosure | Pillow re-encode without `exif=` kwarg + belt-and-braces `image.getexif().clear()` |
| Path traversal on `/photos/{filename}` (e.g., `../etc/passwd`) | Tampering / Information Disclosure | Regex-validate filename matches `^[0-9a-f]{32}(-thumb)?\.jpg$`; reject anything else with 404 |
| Photo URL guessing | Information Disclosure | Opaque `uuid4().hex` filenames; auth gate (D-06); anonymous → 404 not 403 |
| Mass-assignment in form (extra fields like `is_admin=1`) | Tampering | Pydantic schemas explicitly enumerate allowed fields; `model_validate(raw)` ignores or rejects extras per `model_config` |
| ReDoS via crafted filter input | Denial of Service | Filter params are passed as SQL bind params (not regex'd); autocomplete query length capped at ≤50 chars at Pydantic layer |
| Numeric-range bypass (rating=-1 or temp=999) | Tampering | `Field(ge=0, le=5)` per SEC-06 — every numeric form field has explicit range |
| Tab-nabbing on external roaster links | Spoofing | Roaster website rendered with `rel="noopener noreferrer"` and `target="_blank"` (planner adds to template); not load-bearing because the URL is admin-curated |
| Photo orphan-sweep race deletes in-flight upload | Data loss | List filesystem FIRST, query DB SECOND, unlink THIRD; documented in `app/services/photos.py::sweep_orphans` |

## Sources

### Primary (HIGH confidence — already-shipped project code)

- `app/csrf.py` — CSRFFormFieldShim implementation reference (Phase 2 D-15 wiring)
- `app/dependencies/auth.py` — `require_user` / `require_admin` (Phase 2)
- `app/models/bag.py` — existing `Bag` model; Phase 4 modifies in place
- `app/migrations/versions/0001_initial.py` + `p3_api_credentials.py` — migration patterns including `op.execute("CREATE EXTENSION")`, `op.bulk_insert`, CHECK constraints, and the hand-edit conventions
- `app/services/credentials.py` — Phase 3 service-module template (sync, kwargs, audit-event emit) Phase 4 mirrors
- `app/schemas/auth.py` — Pydantic v2 form schema template (Phase 2)
- `app/templates/pages/setup.html` — CSRF hidden-input pattern + inline error rendering reference
- `app/templates/base.html` — HTMX 2.0.10 + Alpine 3.14.9 CSP loader; CSRF meta tag
- `app/static/js/htmx-listeners.js` — global HTMX config; `allowEval=false`; CSRF auto-attach
- `.planning/research/STACK.md` — pinned versions, gap-library recommendations, compatibility gotchas
- `.planning/research/PITFALLS.md` — HX-3, HX-4, SEC-4, MX-1 patterns referenced in CONTEXT
- `.planning/phases/00-foundation/00-CONTEXT.md` — Phase 0 patterns (Mapped[...] models, sync SessionLocal, alembic autogen, extensions, app_settings seed including `photo_max_bytes`)
- `.planning/phases/01-middleware/01-CONTEXT.md` — CSP-strict rules, FragmentCacheHeadersMiddleware, Alpine CSP build registration, no `hx-on:` inline, no `|safe`
- `.planning/phases/02-auth/02-CONTEXT.md` — `require_admin` / `require_user`, CSRFFormFieldShim, audit-event taxonomy
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — sync SessionLocal services pattern, kwargs API + audit emission
- `.planning/phases/04-shared-catalog/04-CONTEXT.md` — D-01..D-16 decisions (verbatim source of truth)
- `.planning/phases/04-shared-catalog/04-UI-SPEC.md` — visual + interaction contract; spacing, typography, color, component patterns
- `.planning/REQUIREMENTS.md` — CAT-01..03, CAT-05..08, SEC-06, SEC-07 verbatim
- `docker-compose.yml` — confirmed `coffee_snobbery_photos:/app/data/photos` mount
- `CLAUDE.md` — stack invariants, architectural invariants, things to never do silently
- `.planning/research/STACK.md` §2 row "Image processing" — magic-byte hand-roll recommendation

### Secondary (MEDIUM confidence — verified against published docs)

- HTMX 2.0.10 docs: `hx-trigger` filter expressions, `hx-sync`, `hx-swap-oob`, `hx-push-url`, `HX-Request` request header, `HX-Trigger` response header, `HX-Redirect` response header (cited inline)
- Alpine 3.x CSP build docs: `Alpine.data()`, registered components, declarative bindings, getter properties
- Wikipedia / RFC 2083 / WebP container spec — image-format magic byte signatures
- SQLAlchemy 2.0 docs: `Mapped[...]`, `mapped_column`, `ForeignKey(ondelete=)`, `select()`, dialect-specific types (`CITEXT`, `JSONB`, `ARRAY`)
- Pydantic v2 docs: `BaseModel`, `Field(ge=, le=, min_length=, max_length=)`, `HttpUrl`, `ValidationError.errors()` shape, `model_validate`, `model_dump`
- Pillow 12.x docs: `Image.open`, `Image.verify`, `Image.thumbnail`, `Image.save`, `Image.getexif`, `Image.MAX_IMAGE_PIXELS`, `Image.Resampling.LANCZOS`, `DecompressionBombError`

### Tertiary (LOW confidence — verify in plan-phase if load-bearing)

- Specific Pillow API kwarg names (e.g., `optimize=True` for JPEG save) — minor; planner verifies via `help()` during implementation
- Alembic 1.18 specific autogenerate behavior for CHECK constraints — pitfall-driven hand-edit pass mitigates regardless
- HTML5 Canvas `toBlob` browser support quotas at 96%+ — caniuse.com claim from STACK.md; D-05 JS-off fallback handles the remaining 4%

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against existing pyproject.toml + STACK.md (pinned 2026-05-16, well within validity window)
- Architecture: HIGH — every decision traces to D-01..D-16 in CONTEXT (locked by user) or Phase 0-3 patterns (already shipped)
- Pitfalls: HIGH — directly referenced from `.planning/research/PITFALLS.md` (HX-3, HX-4, SEC-4, MX-1)
- Pydantic / Pillow / SQLAlchemy specifics: MEDIUM — APIs are stable across recent versions but planner must run a quick `help()` verification during Wave 0 (documented in Assumptions Log A1-A4)
- Test architecture: HIGH — pytest + transactional rollback fixtures are the established Phase 0-3 pattern

**Research date:** 2026-05-18
**Valid until:** 2026-06-17 (30 days — stable stack, no fast-moving deps in Phase 4's scope)
