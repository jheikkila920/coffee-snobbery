# Phase 16: Cafe Quick-Rate - Research

**Researched:** 2026-05-27
**Domain:** Per-user secondary entity (cafe_logs) + analytics UNION integration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Data model — cafe_logs table:**
- **D-01:** Net-new `cafe_logs` table (separate, additive). Unified-table options rejected because `brew_sessions.coffee_id NOT NULL ondelete=RESTRICT` is a documented schema invariant. Planner finalizes column types.
- **D-02:** `roaster_id INT NULL ondelete=SET NULL` FK to `roasters.id` + create-on-the-fly autocomplete (mirrors Phase 4 flavor-notes / Phase 15.1 D-03 varietals pattern).
- **D-03:** `origin_country TEXT NULL` (no FK, no new lookup). Autocomplete sources from distinct `coffee_origins.country` values + small seeded list. No region column at v1.
- **D-04:** `flavor_note_ids BIGINT[]` NOT NULL DEFAULT '{}' + GIN index. Hand-edit migration with `op.execute()` (autogenerate cannot emit USING GIN).
- **D-05:** `brew_method TEXT NULL` free-text. No enum, no FK.

**Claude's discretion — column shapes (locked to brew-session parity):**
- `cafe_name TEXT NOT NULL` — only required field besides rating. Free-text; does NOT FK to `coffees`.
- `rating Numeric(3,2) NULL` — 0–5 in 0.25 steps; nullable for "still thinking" entries.
- `notes Text NOT NULL DEFAULT ''` — same shape as brew sessions.
- `photo_filename TEXT NULL` — single photo per log; reuses `app/services/photos.py` pipeline + `coffee_snobbery_photos` volume.
- `user_id BIGINT NOT NULL ondelete=RESTRICT`.
- `logged_at TIMESTAMPTZ NOT NULL DEFAULT now()` — editable via form (backfilling).
- Indices: `(user_id, logged_at DESC)` for list; GIN on `flavor_note_ids`.

**List view & visual distinction (CAFE-03):**
- **D-06:** Cafe logs live on existing `/brew` Sessions page as a tab toggle. URL family `/brew?tab=cafe`. Active tab filters are tab-scoped.
- **D-07:** `border-l-2` amber accent (vs espresso-600 brew accent) + small coffee-cup icon (vs kettle icon).
- **D-08:** Blank empty state — no friendly copy, no sample, no watermark.

**Edit / delete (CAFE-06):**
- Phase 15.1 D-21 dual Edit button pattern (`md:hidden` mobile inline + `hidden md:inline-flex` desktop mount with `?layout=desktop`).
- Delete via POST + hidden `_method=DELETE` + confirmation step.
- Filters on Cafe tab: rating range + date range only. No brand/origin filters at v1.
- Default sort: `logged_at DESC`. Pagination + card-tap behavior: mirror Sessions tab.

**Entry point — 20-second path (CAFE-01):**
- **D-09:** Third "Quick rate" button on `/brew` page header, same flex row as "Guided Brew" + "Log session".
- **D-10:** Dedicated `/cafe-logs/new` page (and `/cafe-logs/{id}/edit`). Full-page render extending `base.html`. NOT a bottom-sheet modal. NOT an inline form-block.
- **D-11:** Single-scroll form, required fields on top: coffee name (autofocused) + rating + Save above the fold. Below: roaster, origin, brew method, flavor notes, notes, photo. NO server-side draft autosave at v1. Localstorage form-restore acceptable but not required.

**AI integration (CAFE-04):**
- **D-12:** Extend `compute_input_signature` (analytics.py:353) by appending cafe rows as a second list. Cafe row shape: `(cafe_log_id, float(rating), sorted flavor_note_ids, roaster_id, origin_country)`. Single payload, single SHA256.
- **D-13:** `get_preference_profile` cafe contributions:
  - Origin: YES (UNION `cafe_logs.origin_country` with `coffee_origins.country`).
  - Roaster: YES (UNION cafe roaster_id JOIN with brew roaster JOIN).
  - Process: NO. Roast level: NO.
  - Flavor descriptors (`get_flavor_descriptors`): YES (UNION rating ≥4.0 flavor_note_ids).
- **D-14:** `get_top_coffees` stays brew-only. Cafe coffees have no `coffees` row by design.
- **D-15:** Cold-start gate counts cafe + brew together: `(brew_count + cafe_count) >= 3 AND distinct flavor_notes across both >= 5`.

**Sweet-spots exclusion (CAFE-05):**
- **D-16:** `get_sweet_spots` stays brew-only, no UNIONs. Add one-line comment: "Cafe logs are intentionally excluded — they have no brew-parameter fields (CAFE-05)."

### Claude's Discretion

- Whether to add an explicit `cafe_log` audit-log entry — household-scale audit posture is "auth + admin events"; cafe log churn is user-content noise (recommend NO audit entry).
- Exact UNION SQL shape for D-13 (CTE vs derived table vs raw UNION ALL) — SQLAlchemy 2.0 + psycopg 3 + Postgres 16 all support either.
- Whether cold-start D-15 arithmetic is single SQL or two queries summed in Python.
- Tab routing: pure server-side `?tab=cafe` vs Alpine.js client tab swap — lean server-side for CSP + back/forward.
- Pydantic schema in `app/schemas/cafe_log.py` (yes — one-schema-per-model convention).
- Tests in `tests/services/test_cafe_logs.py` + `tests/routers/test_cafe_logs.py` (yes — convention).

### Deferred Ideas (OUT OF SCOPE)

- "Top cafe tastings" home card / widget (Phase 17 or Phase 19).
- Cafe logs in global trigram search index (Phase 10 surface; deferred).
- CSV import/export for cafe logs.
- Brew method enum / lookup table.
- Optional process + roast_level fields on cafe logs.
- Bottom-sheet / modal form pattern (Phase 21 owns).
- FAB (Floating Action Button).
- Home-page CTA card for "Quick rate" (Phase 17 owns).
- Server-side `brew_drafts`-style autosave for cafe form.
- FK from cafe_log to `coffees` catalog when the cafe coffee IS in the household catalog.
- Separate cafe_logs photos volume.
- Per-user provenance on cafe roaster autocomplete.
- Audit-log entries on cafe log create/edit/delete.
- Two-stage save ("save quick, then add details").
- Inline "add new coffee from brew form" carryover — owned by future brew-form polish.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CAFE-01 | User can log a cafe coffee with just name + rating in ~20 seconds | Form architecture mirroring `/brew/new` (Patterns 2 + 3), autofocus + required-fields-on-top single-scroll (D-11), `?tab=cafe` redirect after save |
| CAFE-02 | Optionally add brand/roaster, origin, brew method, notes, flavor notes, photo | Column shapes (Pattern 1) + create-on-the-fly autocompletes (D-02, D-03, Pattern 5), photo pipeline reuse (Pattern 6), free-text brew_method (D-05) |
| CAFE-03 | Per-user, listed/viewable, visually distinct from brew sessions | Tab toggle on `/brew` (Pattern 7), border-l-2 amber + coffee-cup icon (Pattern 8), per-user IDOR-safe service helpers, blank empty state (D-08) |
| CAFE-04 | Cafe ratings/flavor/origin/roaster feed preference derivation + AI signature | `compute_input_signature` extension (Pattern 9), UNION'd dim queries (Pattern 10), cold-start gate cafe+brew (Pattern 11) |
| CAFE-05 | Excluded from grind/ratio/temp/recipe sweet-spots | `get_sweet_spots` stays brew-only + guard comment (D-16 — code body unchanged, one-line comment only) |
| CAFE-06 | User can edit + delete own cafe logs | Phase 15.1 D-21 dual Edit button (Pattern 12) + `_method=DELETE` POST + confirmation + 404 on cross-user (IDOR) |
</phase_requirements>

## Summary

Phase 16 is a **purely additive, well-bounded vertical slice**: one new table, one new model, one new schema, one new service, one new router, three new templates, one new migration. The analytics integration (D-12 / D-13 / D-15) is the only non-trivial cross-cutting work; it appends a second list to a SHA256 signature payload and UNIONs three dim queries. Sweet-spots stays untouched by code, gains only a one-line guard comment (D-16).

CONTEXT.md is exceptionally complete — 16 D-decisions are locked, all alternatives explicitly rejected. Research surfaces HOW to implement, not WHETHER. The data model debate is closed (separate `cafe_logs` table).

**Primary recommendation:** Follow the brew_sessions / brew form / Phase 15.1 D-21 dual-Edit pattern verbatim. The cafe vertical slice mirrors brew at every layer (model, schema, service, router, templates, tests). Diverge only where CONTEXT.md explicitly says so (no draft autosave, no `coffee_id` FK, no brew parameters, no CSV import).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `cafe_logs` schema + GIN index | Database (Postgres 16) | — | New table; standard SQLAlchemy 2.0 Mapped + Alembic migration with `op.execute()` for GIN |
| Cafe log CRUD service | API / Backend (`app/services/cafe_logs.py`) | — | Per-user scoping (`by_user_id` kwarg pattern) + photo pipeline call-through |
| Cafe log routes | API / Backend (`app/routers/cafe_logs.py`) | — | Mirror `routers/brew.py` — `_parse_form_payload`, `_hydrate_form_context`, mass-assignment defense (`extra="forbid"`), CSRF |
| Form page + chip widgets | Frontend Server (Jinja templates + HTMX) | Browser (Alpine.js for chip/autocomplete) | Server-rendered template extends `base.html`; Alpine handles client-side chip state |
| Tab routing on `/brew?tab=cafe` | Frontend Server (Jinja + HTMX) | API / Backend (router branch in `brew.py`) | Server-side `?tab=` for CSP + back/forward correctness; `hx-get` + `hx-push-url` updates URL on tab click |
| Analytics UNION queries | Database (Postgres) | API / Backend (analytics.py) | Postgres UNION ALL inside `select()`; aggregation in SQL, not Python |
| AI signature SHA256 | API / Backend (analytics.py) | — | Pure Python (hashlib + json.dumps); no DB or external service |
| Cold-start gate UI meter | Frontend Server (existing `_cold_start.html`) + API / Backend (`get_cold_start_counts`) | — | Extend gate arithmetic; templates render the dict the function returns (no template-side changes needed if the dict keys stay the same) |
| Photo upload | API / Backend (`app/services/photos.py`) | — | Reuse — zero changes to the module itself; only `sweep_orphans` needs to learn the second table (see Pattern 6 + Pitfall 8) |

## Standard Stack

The phase introduces no new libraries — every dependency is already in the pinned stack. See CLAUDE.md § "Technology Stack" for the full pin list.

### Reused (no new pins)

| Library | Pinned Version | Used For |
|---------|----------------|----------|
| SQLAlchemy | `>=2.0.49,<2.1` | Mapped[...] columns, `select()` + UNION ALL query construction |
| Alembic | `>=1.18,<2.0` | New migration `pXX_cafe_logs.py` with hand-edited GIN |
| psycopg | `>=3.3,<3.4` | Postgres driver; supports `ARRAY` + GIN |
| Pydantic | `>=2.13,<3.0` | `CafeLogCreate` / `CafeLogUpdate` schemas with `extra="forbid"` |
| Jinja2 | `>=3.1.6,<4` | New form / card / row templates |
| Pillow | `>=12.2,<13` | Photo pipeline (reused via `app/services/photos.py`) |
| HTMX | 2.0.x CDN | Tab toggle (`hx-get` + `hx-push-url`), form POST + HX-Redirect, dual Edit button |
| Alpine.js | 3.x CDN | Chip input, autocomplete dropdown state — reuse existing `flavorNoteChips` / `autocomplete` scopes |
| Tailwind | v3 standalone CLI (NOT v4) | `border-l-2 border-amber-500` accent; `.dark` selectors |
| structlog | `>=25.5,<26` | OPTIONAL audit channels — CONTEXT recommends no audit events for cafe logs (household-scale posture) |

**Version verification:** All libraries already pinned and present in the running container. No `pip index` / `npm view` checks required — the pinned versions in `pyproject.toml` are the truth. [VERIFIED: pyproject.toml]

## Architecture Patterns

### System Architecture Diagram

```
[Browser: any page]
      |
      | tap "Quick rate" button in /brew header
      v
[GET /cafe-logs/new]
      |
      | render pages/cafe_log_form.html (mode=create)
      | autofocus cafe_name input
      v
[User fills form: name + rating + (optional) roaster/origin/brew_method/flavor_notes/notes/photo]
      |
      | optional: hx-get autocomplete fragments for roaster + origin_country
      | optional: hx-get flavor-notes autocomplete (reuse coffee_form chip pattern)
      v
[POST /cafe-logs]  (multipart/form-data; CSRF via X-CSRF-Token hidden input)
      |
      |--(ValidationError) -> 200 + re-render pages/cafe_log_form.html with errors
      |
      | service: cafe_logs.create_cafe_log(by_user_id=user.id, ...)
      |   - if photo: photos.process_and_save(raw_bytes) -> filename
      |   - insert row
      |   - commit
      v
[HX-Redirect: /brew?tab=cafe]
      |
      v
[GET /brew?tab=cafe]  (existing /brew handler branches on tab query param)
      |
      | service: cafe_logs.list_cafe_logs(by_user_id=user.id, filters)
      v
[render pages/sessions.html with cafe tab content]
      |
      | each cafe log row -> fragments/cafe_log_card.html (mobile, <md)
      |                    -> fragments/cafe_log_row.html (desktop table tbody, md+)
      v
[User taps "Edit" - mobile inline]                    [User taps "Edit" - desktop]
      |                                                       |
      | hx-get /cafe-logs/{id}/edit                           | hx-get /cafe-logs/{id}/edit?layout=desktop
      | hx-target=closest [data-row]                          | hx-target=#cafe-form-mount
      | hx-swap=outerHTML                                     | hx-swap=innerHTML
      v                                                       v
[inline form replaces card]                          [form renders into desktop mount]


[Nightly APScheduler job]
      |
      | for each user: compute_input_signature(db, user_id)
      |   - existing: SELECT rated brew rows -> serialize -> payload list 1
      |   - NEW (D-12): SELECT rated cafe rows -> serialize -> payload list 2
      |   - SHA256(json.dumps([list1, list2]))
      v
[Compare signature against ai_recommendations.input_signature; regen if differs]
      |
      | regen prompt now includes cafe taste signal via:
      |   - get_preference_profile() origin + roaster UNION (D-13)
      |   - get_flavor_descriptors() UNION (D-13)
      v
[New AI recommendation reflects cafe data]
```

### Recommended Project Structure

No new directories — every new file lands in the existing app subdirectory it conceptually belongs to.

```
app/
├── models/
│   └── cafe_log.py             # NEW — Mapped[] columns, mirrors brew_session.py
├── schemas/
│   └── cafe_log.py             # NEW — CafeLogCreate, CafeLogUpdate (extra="forbid")
├── services/
│   ├── cafe_logs.py            # NEW — CRUD, per-user scoping, photo orchestration
│   ├── analytics.py            # MODIFY — D-12 signature, D-13 UNIONs, D-15 cold-start, D-16 comment
│   └── photos.py               # MODIFY (sweep_orphans only) — extend reference set to include cafe_logs.photo_filename
├── routers/
│   ├── cafe_logs.py            # NEW — /cafe-logs CRUD; _hydrate_form_context helper
│   └── brew.py                 # MODIFY — list_sessions accepts ?tab=cafe + branches
├── templates/
│   ├── pages/
│   │   ├── cafe_log_form.html  # NEW — full-page form (mirrors brew_form.html)
│   │   └── sessions.html       # MODIFY — third "Quick rate" button + tab toggle
│   └── fragments/
│       ├── cafe_log_card.html  # NEW — mobile card (border-l-2 amber + cup icon)
│       ├── cafe_log_row.html   # NEW — desktop row + dual Edit button (D-21)
│       └── cafe_log_list.html  # NEW — list fragment for HTMX swap on tab toggle / filter
└── migrations/
    └── versions/
        └── pXX_cafe_logs.py    # NEW — table create + GIN index via op.execute()
                                #       down_revision = head AFTER Phase 15.1 merge
                                #       (currently p15_1_varietal_m2m — verify)

app/main.py                     # MODIFY — register routers.cafe_logs.router (one line)

tests/
├── services/
│   ├── test_cafe_logs.py       # NEW
│   └── test_analytics.py       # MODIFY — extend _seed_analytics_scenario with cafe fixtures;
│                               #          add UNION coverage + signature mutation tests
└── routers/
    └── test_cafe_logs.py       # NEW
```

### Pattern 1: New SQLAlchemy 2.0 model — cafe_log.py

**What:** Mapped[...] columns + FK directionality matching brew_session.py. RESTRICT on user_id (history is precious), SET NULL on roaster_id (cafe log survives roaster deletion). [CITED: app/models/brew_session.py:74-110 — FK asymmetry conventions]

**When to use:** Always for new tables in this stack.

```python
# Source: app/models/brew_session.py:66-161 (pattern), app/models/coffee.py:79-83 (ARRAY)
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class CafeLog(Base):
    """A coffee a user tasted outside the home. Per-user (NOT household-shared)."""

    __tablename__ = "cafe_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    roaster_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("roasters.id", ondelete="SET NULL"),
        nullable=True,
    )

    cafe_name: Mapped[str] = mapped_column(Text, nullable=False)
    origin_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    brew_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    flavor_note_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'::bigint[]"),
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)

    logged_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_cafe_logs_user_logged_at", "user_id", text("logged_at DESC")),
        # NOTE: GIN on flavor_note_ids is NOT declared here.
        # SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`;
        # the migration pXX_cafe_logs.py adds it via raw op.execute().
    )
```

**Note on `cafe_name`:** Plain `Text NOT NULL` — NOT `CITEXT`. Cafe coffee names are per-user free text, not a shared catalog identity; they don't dedupe across rows. [VERIFIED: matches `coffee_origins.country` plain-text pattern in `app/models/coffee_origin.py:38`.]

### Pattern 2: Alembic migration — pXX_cafe_logs.py

**What:** Inline schema description (no model imports), hand-edited GIN + DESC B-tree.

**When to use:** Always — Alembic-safe convention prevents future model renames from breaking past migrations. [CITED: app/migrations/versions/p5_brew_sessions.py:34-37, "this migration body does NOT import from app.models"]

```python
# Source: app/migrations/versions/p5_brew_sessions.py:63-220 (pattern)
from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "pXX_cafe_logs"
# IMPORTANT: down_revision MUST be the head AFTER Phase 15.1 has merged.
# Current head is `p15_1_varietal_m2m` (Phase 15.1 has shipped — verify
# with `docker compose exec coffee-snobbery alembic heads` before writing
# this value). See Pitfall 4.
down_revision: str | Sequence[str] | None = "p15_1_varietal_m2m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cafe_logs",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "roaster_id",
            sa.BigInteger,
            sa.ForeignKey("roasters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cafe_name", sa.Text, nullable=False),
        sa.Column("origin_country", sa.Text, nullable=True),
        sa.Column("brew_method", sa.Text, nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "flavor_note_ids",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("photo_filename", sa.Text, nullable=True),
        sa.Column(
            "logged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # B-tree index — raw SQL to carry the DESC sort direction reliably
    # (mirrors p5_brew_sessions.py:160-162).
    op.execute(
        "CREATE INDEX ix_cafe_logs_user_logged_at ON cafe_logs (user_id, logged_at DESC)"
    )

    # GIN index — hand-edited because autogenerate cannot emit USING GIN
    # (mirrors p4_shared_catalog.py + p5_brew_sessions.py:167-171).
    op.execute(
        "CREATE INDEX ix_cafe_logs_flavor_note_ids "
        "ON cafe_logs USING GIN (flavor_note_ids)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_flavor_note_ids")
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_user_logged_at")
    op.drop_table("cafe_logs")
```

### Pattern 3: Pydantic v2 schema with `extra="forbid"`

**What:** Mass-assignment defense. `user_id` and `photo_filename` (server-set from upload pipeline) are NEVER declared as fields. [CITED: app/schemas/brew_session.py:74-100]

```python
# Source: app/schemas/brew_session.py:74-100 (pattern)
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CafeLogCreate(BaseModel):
    """Cafe-log form. Validation errors → 200 + form re-render (SEC-06)."""

    model_config = ConfigDict(extra="forbid")

    # cafe_name + rating are the only required-ish fields (rating still nullable).
    cafe_name: str = Field(..., min_length=1, max_length=200)
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))

    # Optional enrichment.
    roaster_id: int | None = Field(None, ge=1)
    origin_country: str | None = Field(None, max_length=100)
    brew_method: str | None = Field(None, max_length=100)
    flavor_note_ids: list[int] = Field(default_factory=list)
    notes: str = Field("", max_length=5000)
    logged_at: datetime | None = None  # nullable in schema; service defaults to now()


class CafeLogUpdate(CafeLogCreate):
    """Same shape today — split class lets a future Update path diverge."""
    pass
```

**Notes:**
- `photo_filename` is intentionally absent. The router reads `UploadFile` separately and passes the result of `photos.process_and_save()` to the service. The form field is `photo: UploadFile`, not a string.
- Match the existing `roaster_query` / `flavor_note_query` autocomplete-input field-strip pattern (see `app/routers/brew.py:_NON_SCHEMA_FORM_KEYS`) — those keys must be stripped before Pydantic so `extra="forbid"` doesn't trip.
- For multipart endpoints, the router pre-strips the `X-CSRF-Token` hidden field and any `*_query` autocomplete inputs.

### Pattern 4: Router structure — mirror routers/brew.py

**What:** Page-level GET + POST routes, `_hydrate_form_context` helper, `_parse_form_payload` helper, 404 (never 403) on cross-user IDOR. [CITED: app/routers/brew.py:276-356, "_hydrate_form_context"]

```python
# Source: app/routers/brew.py:656-727 (new_brew_form), :814-856 (create_brew),
#         :864-921 (edit_brew_form), :924-973 (update_brew)

router = APIRouter(prefix="/cafe-logs")

_LIST_URL = "/brew?tab=cafe"  # post-save destination per D-11

# Form keys the cafe-log template renders error paragraphs for.
_FORM_FIELDS = {
    "cafe_name", "rating", "roaster_id", "origin_country",
    "brew_method", "flavor_note_ids", "notes", "logged_at",
}

# Empty-string -> None for optional fields.
_EMPTY_TO_NONE_FIELDS = {
    "rating", "roaster_id", "origin_country", "brew_method",
    "logged_at",
}

# Integer FK fields.
_INT_FIELDS = {"roaster_id"}

# Form keys that the autocomplete widgets emit but the schema doesn't accept.
_NON_SCHEMA_FORM_KEYS = {
    "X-CSRF-Token",
    "roaster_query",
    "flavor_note_query",
    "origin_country_query",
    "layout",          # ?layout=desktop is a query param, but a hidden input is also fine
    "_method",         # for POST + _method=DELETE pattern
}


@router.get("/new", response_class=HTMLResponse)
def new_cafe_log_form(...):
    """Create-mode form, autofocus cafe_name (D-11)."""
    ...

@router.post("", response_class=HTMLResponse)
async def create_cafe_log(...):
    """Create. ValidationError -> 200 + re-render. Success -> HX-Redirect /brew?tab=cafe."""
    ...

@router.get("/{cafe_log_id}/edit", response_class=HTMLResponse)
def edit_cafe_log_form(cafe_log_id: int, ...):
    """Edit-mode. 404 on cross-user (IDOR existence non-leak).

    Reads optional `?layout=desktop` query param via _hydrate_form_context
    (D-21 dual Edit pattern — see Pattern 12).
    """
    ...

@router.post("/{cafe_log_id}", response_class=HTMLResponse)
async def update_cafe_log(cafe_log_id: int, ...):
    """Update if owned. 404 on cross-user. HX-Redirect /brew?tab=cafe."""
    # Branch on form._method == "DELETE" if using POST + _method=DELETE pattern.
    ...
```

**Per-user scoping invariant:** Every read/write filters by `request.state.user.id` (via `Depends(require_user)`). A cross-user `cafe_log_id` returns 404, not 403 (existence non-leak — matches `app/routers/brew.py:864-878`).

### Pattern 5: Create-on-the-fly autocomplete (roaster + origin_country + flavor_note)

**What:** Reuse the existing `x-data="autocomplete"` Alpine scope + `/roasters/list` + `/flavor-notes/datalist` endpoints. Origin_country is new — needs a new endpoint `/cafe-logs/origin-country-autocomplete`. [CITED: app/templates/fragments/coffee_form.html:83-112 (roaster), :263-339 (flavor_notes), :179-231 (varietal); app/templates/fragments/autocomplete_list.html:36-66]

**Roaster autocomplete:** Reuse verbatim. `/roasters/list?q=<query>` returns the dropdown fragment (`fragments/autocomplete_list.html` with `entity="roaster"` + `create_new_endpoint="/roasters/new-modal"`).

**Flavor-note chip input:** Reuse the `flavorNoteChips` Alpine scope verbatim. Note name must be `flavor_note_ids` (singular FK list) so the router collects via `getlist("flavor_note_ids")`. The chip widget already supports `flavor-note-created` HX-Trigger for create-on-the-fly.

**Origin country (new) — NO modal create-on-the-fly, just suggestions:**

```python
# Source: new endpoint, lives in app/routers/cafe_logs.py
# Pattern source: app/routers/coffees.py varietal-autocomplete handler

# Distinct values from coffee_origins.country + small seeded set
_SEEDED_COUNTRIES = (
    "Ethiopia", "Kenya", "Colombia", "Brazil", "Guatemala", "Costa Rica",
    "Honduras", "Panama", "Peru", "Mexico", "Indonesia", "Yemen",
    "Rwanda", "Burundi", "Tanzania", "El Salvador", "Nicaragua",
    "Ecuador", "Bolivia",
)


@router.get("/origin-country-autocomplete", response_class=HTMLResponse)
def origin_country_autocomplete(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
) -> Response:
    """Country suggestions for the cafe form. Source: distinct
    coffee_origins.country UNION seeded list, prefix-filtered.

    NOT a create-on-the-fly entity — just a free-text autocomplete with
    suggestions (the user can type any country the suggestions don't cover).
    """
    query = (request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return templates.TemplateResponse(
            request=request,
            name="fragments/autocomplete_list.html",
            context={"items": [], "query": query, "entity": "country",
                     "exact_match": True, "create_new_endpoint": ""},
        )

    # Distinct existing values from the catalog.
    db_countries = db.execute(
        select(CoffeeOrigin.country)
        .where(CoffeeOrigin.country.ilike(f"{query}%"))
        .distinct()
        .order_by(CoffeeOrigin.country)
        .limit(50)
    ).scalars().all()

    # Merge with seeded list, dedupe, prefix-match.
    candidates = set(db_countries) | {c for c in _SEEDED_COUNTRIES if c.lower().startswith(query.lower())}
    items = [{"id": c, "name": c} for c in sorted(candidates)][:20]

    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={
            "items": items,
            "query": query,
            "entity": "country",
            "exact_match": any(i["name"].lower() == query.lower() for i in items),
            "create_new_endpoint": "",  # no "+ Create new" — free text
        },
    )
```

**Anti-pattern to avoid:** Do NOT add a new `countries` lookup table. CONTEXT D-03 explicitly rejects it. Origin is plain TEXT with suggestions, not an FK.

### Pattern 6: Photo upload — reuse `app/services/photos.py` unchanged

**What:** Cafe form gets a `photo: UploadFile` field exactly like `app/routers/bags.py:367-418`. The service stores the resulting filename in `cafe_logs.photo_filename`. [CITED: app/services/photos.py:170-256 (process_and_save), app/routers/bags.py:367-418 (upload pattern)]

**One change needed in `photos.py`:** `sweep_orphans` currently queries only `bags.photo_filename` (line 385-386). To prevent the nightly orphan sweep from deleting cafe log photos, extend it:

```python
# Source: app/services/photos.py:382-389 — current implementation
# MODIFY: union the two reference sources

from app.models.bag import Bag
from app.models.cafe_log import CafeLog  # NEW

bag_rows = db.execute(select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))).all()
cafe_rows = db.execute(select(CafeLog.photo_filename).where(CafeLog.photo_filename.isnot(None))).all()

referenced_main: set[str] = {fn for (fn,) in bag_rows if fn is not None}
referenced_main |= {fn for (fn,) in cafe_rows if fn is not None}
```

**Note:** This is the ONE place where `photos.py` cannot be left untouched. If the planner overlooks this, the nightly sweep will silently delete every cafe photo. See Pitfall 8.

### Pattern 7: Tab routing on /brew?tab=cafe

**What:** Server-side `?tab=` query param + `hx-get` + `hx-push-url` for back/forward correctness. [CITED: app/templates/pages/sessions.html:38-44 — existing Phase 4 filter-bar pattern]

**Recommendation:** Branch the existing `list_sessions` handler in `app/routers/brew.py:479-522` on `?tab=cafe`:

```python
# Source: app/routers/brew.py:479-522 (pattern)

@router.get("", response_class=HTMLResponse)
def list_sessions(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
) -> Response:
    """Per-user sessions list (BREW-10) + cafe tab (CAFE-03)."""
    qp = request.query_params
    tab = qp.get("tab", "brew")  # default to brew tab

    if tab == "cafe":
        # Delegate to a helper / the cafe_logs service. Keep brew filters
        # ignored on the cafe tab (D-06: filters are tab-scoped).
        cafe_filters = _parse_cafe_list_filters(qp)  # rating range + date range only
        cafe_rows = cafe_logs_service.list_cafe_logs(db, by_user_id=user.id, **cafe_filters)
        context = {
            "active_tab": "cafe",
            "cafe_rows": cafe_rows,
            "filters": _raw_cafe_filters(qp),
            "active_filter_count": sum(1 for v in _raw_cafe_filters(qp).values() if v),
        }
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request=request,
                name="fragments/cafe_log_list.html",
                context=context,
            )
        return templates.TemplateResponse(
            request=request, name="pages/sessions.html", context=context,
        )

    # Existing brew tab logic unchanged
    ...
```

**Template-side (sessions.html header):**

```html
{# Tab toggle — pair with the filter bar. Both Tabs are anchors with hx-get
   + hx-push-url so back/forward correctly replay state. The active tab gets
   a visual indicator. NO Alpine — keep CSP clean. #}
<nav class="flex border-b border-espresso-200 dark:border-espresso-800 mb-4">
  <a href="/brew?tab=brew"
     hx-get="/brew?tab=brew"
     hx-push-url="true"
     hx-target="#session-list"
     hx-swap="outerHTML"
     class="px-4 py-2 text-base {% if active_tab != 'cafe' %}border-b-2 border-espresso-700 font-semibold{% else %}text-espresso-600 dark:text-cream-300{% endif %}">
    Sessions
  </a>
  <a href="/brew?tab=cafe"
     hx-get="/brew?tab=cafe"
     hx-push-url="true"
     hx-target="#session-list"
     hx-swap="outerHTML"
     class="px-4 py-2 text-base {% if active_tab == 'cafe' %}border-b-2 border-amber-500 font-semibold{% else %}text-espresso-600 dark:text-cream-300{% endif %}">
    Cafe tastings
  </a>
</nav>
```

**Anti-pattern:** Do NOT use Alpine.js client-side tab swap. CSP-nonce + back-button correctness both favor server-side `?tab=`.

### Pattern 8: Visual distinction — border-l-2 amber + cafe-cup icon

**What:** `border-l-2 border-amber-500` accent (vs the espresso-600 brew accent) + inline SVG cup icon. [CITED: existing brew session row uses `border-b border-espresso-200` per `app/templates/fragments/session_row.html`]

**Tailwind v3 / dark-mode invariant:** Use `.dark:border-amber-400` for the dark-mode variant. NEVER `@custom-variant` (project memory: tailwind-v3-not-v4). [VERIFIED: CLAUDE.md memory `tailwind-v3-not-v4`]

```html
{# fragments/cafe_log_card.html — mobile card (md:hidden) #}
<div id="cafe-log-{{ log.id }}"
     data-row
     class="relative rounded-lg border border-espresso-200 border-l-2 border-l-amber-500 bg-cream-100 p-4 pr-24 dark:bg-espresso-900 dark:border-espresso-800 dark:border-l-amber-400">
  {# Cup icon — inline SVG, top-left, distinguishes from brew sessions #}
  <svg xmlns="http://www.w3.org/2000/svg" class="absolute top-3 left-3 w-4 h-4 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label="Cafe tasting">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8h13v6a4 4 0 01-4 4H7a4 4 0 01-4-4V8zm13 1h2a2 2 0 010 4h-2"/>
  </svg>
  <!-- ... rest of card content ... -->
</div>
```

**Icon source:** A clean coffee-cup outline from Heroicons (https://heroicons.com — used inline elsewhere in the app, e.g. `app/static/img/`). No new dependency.

### Pattern 9: D-12 signature extension — append cafe rows as a second payload list

**What:** Single SHA256 over `[brew_list, cafe_list]`. Determinism comes from ordering by ID within each list. [CITED: app/services/analytics.py:353-399]

```python
# Source: app/services/analytics.py:353-399 (pattern)
# MODIFY: append a second SELECT + payload list

def compute_input_signature(db: Session, user_id: int) -> str:
    """SHA256 hex over RATED brew + cafe rows (D-08/D-09, CAFE-04 / D-12).

    Two ordered lists in the payload:
      1. brew rows: (coffee_id, float(rating), sorted flavor_note_ids_observed,
                     recipe_id, brewer_id)
      2. cafe rows: (cafe_log_id, float(rating), sorted flavor_note_ids,
                     roaster_id, origin_country)

    Each list is ordered by its own primary key (ASC) for determinism.
    A brew payload list of [] is valid (user has only cafe logs); same for cafe.
    Returns _EMPTY_SIGNATURE only when BOTH lists are empty.
    """
    # Existing brew SELECT (unchanged) ...
    brew_stmt = (
        select(
            BrewSession.id,
            BrewSession.coffee_id,
            BrewSession.rating,
            BrewSession.flavor_note_ids_observed,
            BrewSession.recipe_id,
            BrewSession.brewer_id,
        )
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .order_by(BrewSession.id)
    )
    brew_rows = db.execute(brew_stmt).all()

    # NEW: cafe SELECT
    cafe_stmt = (
        select(
            CafeLog.id,
            CafeLog.rating,
            CafeLog.flavor_note_ids,
            CafeLog.roaster_id,
            CafeLog.origin_country,
        )
        .where(
            CafeLog.user_id == user_id,
            CafeLog.rating.is_not(None),
        )
        .order_by(CafeLog.id)  # deterministic
    )
    cafe_rows = db.execute(cafe_stmt).all()

    if not brew_rows and not cafe_rows:
        return _EMPTY_SIGNATURE

    def _serialize_brew(row) -> list:
        return [
            row.coffee_id,
            float(row.rating),
            sorted(row.flavor_note_ids_observed or []),
            row.recipe_id,
            row.brewer_id,
        ]

    def _serialize_cafe(row) -> list:
        return [
            row.id,                       # cafe_log_id namespace differs from coffee_id
            float(row.rating),
            sorted(row.flavor_note_ids or []),
            row.roaster_id,
            row.origin_country,           # plain str | None — json.dumps handles None -> null
        ]

    payload = [
        [_serialize_brew(r) for r in brew_rows],
        [_serialize_cafe(r) for r in cafe_rows],
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Critical:** The payload is `[brew_list, cafe_list]` — a list of two lists, NOT a flat concatenation. This guarantees:
1. A brew row with `coffee_id=N` and a cafe row with `id=N` cannot collide on signature input (they're in different sublists).
2. Adding the first cafe log changes the signature even when no brew rows have changed (the cafe sublist transitions from `[]` to `[[...]]`).
3. JSON serializes `None` as `null` deterministically; `sort_keys=True` is harmless here (lists aren't sorted, but it's idempotent).

**Test obligation:** test_signature_cafe.py MUST cover:
- Empty user → `_EMPTY_SIGNATURE` (unchanged).
- Brew-only user → signature unchanged from pre-D-12 hash. **This is a backwards-incompatibility check:** the test must compare to a pre-computed string from before the change to confirm the brew-only payload shape is still `[[...brews]]`, NOT `[...brews]`. The new shape `[brew_list, cafe_list]` will produce a DIFFERENT signature than the old shape `flat_brew_list` for the same brew rows. The planner should accept this one-time signature churn (and plan a deployment with a forced refresh) OR layer the new cafe list ONLY when non-empty. **Recommended:** force one-time churn — it's cleaner and the cost is one extra AI-regen run per user post-deploy. See Pitfall 9.
- Adding a rated cafe log → signature changes.
- Editing a cafe log's rating → signature changes.
- Deleting a cafe log → signature changes.
- Adding an UNRATED cafe log → signature unchanged (rating IS NOT NULL filter).
- Two users' cafe logs don't cross-contaminate (per-user scoping).

### Pattern 10: D-13 UNION ALL shape — preference profile + flavor descriptors

**What:** Postgres UNION ALL inside `select()`. Two equally valid shapes; recommendation below. [CITED: SQLAlchemy 2.0 SELECT docs https://docs.sqlalchemy.org/en/20/tutorial/data_select.html]

**Recommended shape: per-dimension UNION subquery.** Keep each dim as its own `select(...).union_all(select(...)).subquery()`, then aggregate over the subquery. Reasons:
- Aligns with the existing `analytics.py` style (one `select()` block per dim).
- Each dim has its own `having(count >= 2)` cutoff; the UNION must happen BEFORE the GROUP BY (a brew row with rating=4.0 and a cafe row with rating=4.0 for the same country together satisfy the "min 2" floor; querying them separately and then trying to merge in Python is harder to get right).
- Avoids a giant CTE that interleaves four dims.

```python
# Source: app/services/analytics.py:78-150 (pattern) + Postgres UNION ALL idiom
# MODIFY get_preference_profile — UNION cafe rows in for origin + roaster dims

def get_preference_profile(db: Session, user_id: int) -> dict[str, list[Row]]:
    """Return dict with keys origin/process/roaster/roast_level.

    origin + roaster dims UNION cafe data (CAFE-04 / D-13).
    process + roast_level stay brew-only (cafe form does not capture them).
    """
    # ---- Origin dim — UNION brew origins + cafe origins ----
    # Brew side: (CoffeeOrigin.country, BrewSession.rating) — one row per
    # (origin, session); a blend with N origins contributes N rows
    # (existing behavior — see analytics.py:128-143).
    brew_origin = (
        select(
            CoffeeOrigin.country.label("country"),
            BrewSession.rating.label("rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(CoffeeOrigin, CoffeeOrigin.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
    )
    # Cafe side: (CafeLog.origin_country, CafeLog.rating) — one row per
    # cafe log; nullable origins are filtered out (matches the brew-side
    # IS NOT NULL semantics via JOIN).
    cafe_origin = (
        select(
            CafeLog.origin_country.label("country"),
            CafeLog.rating.label("rating"),
        )
        .where(
            CafeLog.user_id == user_id,
            CafeLog.rating.is_not(None),
            CafeLog.origin_country.is_not(None),
        )
    )
    origin_union = brew_origin.union_all(cafe_origin).subquery()
    origin_stmt = (
        select(
            origin_union.c.country.label("label"),
            func.avg(origin_union.c.rating).label("avg_rating"),
            func.count().label("session_count"),
        )
        .group_by(origin_union.c.country)
        .having(func.count() >= 2)
        .order_by(func.avg(origin_union.c.rating).desc(), func.count().desc())
    )

    # ---- Roaster dim — UNION brew roasters + cafe roasters ----
    brew_roaster = (
        select(
            Roaster.name.label("name"),
            BrewSession.rating.label("rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(Roaster, Coffee.roaster_id == Roaster.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
    )
    cafe_roaster = (
        select(
            Roaster.name.label("name"),
            CafeLog.rating.label("rating"),
        )
        .join(Roaster, CafeLog.roaster_id == Roaster.id)
        .where(
            CafeLog.user_id == user_id,
            CafeLog.rating.is_not(None),
        )
    )
    roaster_union = brew_roaster.union_all(cafe_roaster).subquery()
    roaster_stmt = (
        select(
            roaster_union.c.name.label("label"),
            func.avg(roaster_union.c.rating).label("avg_rating"),
            func.count().label("session_count"),
        )
        .group_by(roaster_union.c.name)
        .having(func.count() >= 2)
        .order_by(func.avg(roaster_union.c.rating).desc(), func.count().desc())
    )

    # ---- process + roast_level — UNCHANGED, brew-only ----
    # ... existing _dim_query bodies preserved ...

    return {
        "origin": db.execute(origin_stmt).all(),
        "roaster": db.execute(roaster_stmt).all(),
        "process": _dim_query(Coffee.process, Coffee.process),
        "roast_level": _dim_query(Coffee.roast_level, Coffee.roast_level),
    }
```

**Flavor descriptors (`get_flavor_descriptors`)** — currently raw SQL `unnest()` (line 169-183). Extend the raw SQL with a UNION ALL of two unnest blocks:

```python
# Source: app/services/analytics.py:158-183 (pattern)
# MODIFY: UNION ALL the two flavor-note arrays

def get_flavor_descriptors(db: Session, user_id: int) -> list[Row]:
    """Top-10 flavor descriptors from rated 4.0+ brew + cafe rows (CAFE-04 / D-13).

    Unnests both brew_sessions.flavor_note_ids_observed AND
    cafe_logs.flavor_note_ids — each rating ≥4.0, per-user.

    Uses raw SQL for the unnest + UNION ALL because func.unnest().column_valued()
    produces a TableValuedColumn that SQLAlchemy's ORM join layer cannot resolve
    (RESEARCH A2). The bound :user_id parameter prevents SQL injection (T-06-03).
    """
    stmt = text(
        """
        SELECT fn.id, fn.name, count(*) AS session_count
        FROM (
            SELECT note_id
            FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
            WHERE bs.user_id = :user_id
              AND bs.rating IS NOT NULL
              AND bs.rating >= 4.0
            UNION ALL
            SELECT note_id
            FROM cafe_logs cl, unnest(cl.flavor_note_ids) AS note_id
            WHERE cl.user_id = :user_id
              AND cl.rating IS NOT NULL
              AND cl.rating >= 4.0
        ) AS notes
        JOIN flavor_notes fn ON fn.id = notes.note_id
        GROUP BY fn.id, fn.name
        HAVING count(*) >= 2
        ORDER BY session_count DESC
        LIMIT 10
        """
    )
    return db.execute(stmt, {"user_id": user_id}).all()
```

**Note on UNION ALL semantics:** A flavor note appearing in both a 4.0+ brew row AND a 4.0+ cafe row will count TWICE (once per source). This is the desired behavior — it weights notes that recur across taste contexts. The current brew-only behavior already counts a note twice if two brew sessions both observe it; the cafe UNION extends that to "twice if one brew session and one cafe log both observe it."

### Pattern 11: D-15 cold-start gate — extend get_cold_start_counts

**What:** Add cafe counts to `get_cold_start_counts` (analytics.py:309-345). Single SQL or two-queries-summed-in-Python — recommendation below. [CITED: app/services/analytics.py:309-345]

**Recommended: two queries summed in Python.** Reasoning:
- The existing function already does two queries (one scalar count + one raw SQL unnest). Adding two more cafe queries keeps the structure parallel and easy to read.
- The cafe counts must merge with the brew counts for the gate threshold but each side has its own scope (brew_sessions has no cafe rows; cafe_logs has no brew rows), so they cannot be UNION'd cheaper than running two scalar counts.
- The `distinct_notes` count must be DISTINCT ACROSS both arrays — that needs a single SQL UNION ALL of the unnest. Use one merged raw SQL block for that one piece.

```python
# Source: app/services/analytics.py:309-345 (pattern)
# MODIFY: include cafe contributions per D-15

def get_cold_start_counts(db: Session, user_id: int) -> dict[str, Any]:
    """Return live counts for the cold-start gate (D-02 + CAFE-04 / D-15).

    gate_open = (brew_count + cafe_count) >= 3 AND distinct_notes_across_both >= 5
    """
    brew_count: int = (
        db.scalar(select(func.count(BrewSession.id)).where(BrewSession.user_id == user_id))
        or 0
    )
    cafe_count: int = (
        db.scalar(select(func.count(CafeLog.id)).where(CafeLog.user_id == user_id))
        or 0
    )
    total = brew_count + cafe_count

    # Distinct notes across BOTH arrays. Single raw SQL with UNION ALL of two
    # unnest blocks; JOIN flavor_notes so dangling IDs don't count.
    note_count_row = db.execute(
        text(
            """
            SELECT count(DISTINCT all_notes.note_id) AS cnt
            FROM (
                SELECT note_id
                FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
                WHERE bs.user_id = :user_id
                UNION ALL
                SELECT note_id
                FROM cafe_logs cl, unnest(cl.flavor_note_ids) AS note_id
                WHERE cl.user_id = :user_id
            ) AS all_notes
            JOIN flavor_notes fn ON fn.id = all_notes.note_id
            """
        ),
        {"user_id": user_id},
    ).first()
    note_count: int = (note_count_row.cnt if note_count_row else 0) or 0

    return {
        "sessions": total,                                  # combined count
        "distinct_notes": note_count,
        "gate_open": total >= 3 and note_count >= 5,
        "sessions_needed": max(0, 3 - total),
        "notes_needed": max(0, 5 - note_count),
        # NEW optional fields for the UI / debugging — non-breaking additions.
        "brew_count": brew_count,
        "cafe_count": cafe_count,
    }
```

**UI impact (locate this surface):** The cold-start meter is rendered by `app/templates/fragments/home/_cold_start.html` (used in home shell + by `ai_rec_cold_start.html`). It reads keys `gate.sessions`, `gate.distinct_notes`, `gate.sessions_needed`, `gate.notes_needed` — the dict shape is preserved. The UI text says "Log {N} more brew{s}" which is now slightly inaccurate (cafe logs also count); the planner should either:
- (a) Leave the copy as-is and accept the imprecision (the user sees "1 more brew" but a cafe log also clears it — a happy surprise).
- (b) Change the copy to "Log {N} more session{s}" to be technically accurate but vaguer.
- (c) Add new keys (`brew_count`, `cafe_count`) and split the message into a richer two-line breakdown.

**Recommendation:** (a) at v1 — minimal template churn, user experience is "log anything, it counts." Phase 17 (IA restructure) is the natural place for fancier copy.

### Pattern 12: Dual Edit button + `_hydrate_form_context` helper (Phase 15.1 D-21)

**What:** Mobile inline (`md:hidden` + `hx-target=closest [data-row]` + `outerHTML`) + desktop mount (`hidden md:inline-flex` + `?layout=desktop` + `hx-target=#cafe-form-mount` + `innerHTML`). [CITED: app/templates/fragments/coffee_row.html:29-46 (mobile) + :147-160 (desktop) + :179-183 (OOB clear), Phase 15.1 D-21]

**Template — `fragments/cafe_log_row.html`** (excerpt):

```html
{# Desktop table row + mobile card via mode flag.
   Mirrors fragments/coffee_row.html structure verbatim (D-21).
#}
{% if mode == "card" %}
  <div id="cafe-log-{{ log.id }}"
       data-row
       class="relative rounded-lg border border-espresso-200 border-l-2 border-l-amber-500 bg-cream-100 p-4 pr-24 dark:bg-espresso-900 dark:border-espresso-800 dark:border-l-amber-400">
    <div class="absolute top-3 right-3 flex gap-1">
      {# mobile: existing a3a2f76 pattern, hidden at md+ #}
      <button type="button"
              hx-get="/cafe-logs/{{ log.id }}/edit"
              hx-target="closest [data-row]"
              hx-swap="outerHTML"
              class="md:hidden inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
        Edit
      </button>
      {# desktop: D-21 pattern, hidden at <md #}
      <button type="button"
              hx-get="/cafe-logs/{{ log.id }}/edit?layout=desktop"
              hx-target="#cafe-form-mount"
              hx-swap="innerHTML"
              class="hidden md:inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
        Edit
      </button>
      {# Delete via POST + _method=DELETE + hx-confirm #}
      <form hx-post="/cafe-logs/{{ log.id }}"
            hx-target="closest [data-row]"
            hx-swap="outerHTML"
            hx-confirm="Delete this cafe tasting? This can't be undone."
            class="inline">
        <input type="hidden" name="_method" value="DELETE">
        <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
        <button type="submit"
                class="inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
          Delete
        </button>
      </form>
    </div>
    {# ... rest of card content: cafe_name, roaster_name, origin_country,
         rating stars, flavor chips, brew_method, notes preview, photo thumb ... #}
  </div>
{% else %}
  {# desktop table row — mirrors fragments/session_row.html shape #}
  <tr id="cafe-log-{{ log.id }}" data-row
      class="border-b border-espresso-100 border-l-2 border-l-amber-500">
    ...
  </tr>
{% endif %}
```

**Sessions page mount:** Add a `<div id="cafe-form-mount"></div>` ABOVE the cafe-list area (same pattern as `#coffee-form-mount` from Phase 15.1).

**Router `_hydrate_form_context` helper:**

```python
# Source: app/routers/brew.py:276-356 (pattern), Phase 15.1 D-21
def _hydrate_form_context(
    db: Session,
    *,
    user: User,
    values: dict[str, object],
    errors: dict[str, str],
    mode: str,                                # "create" | "edit"
    cafe_log_id: int | None = None,
    layout: str | None = None,                # "desktop" | None
) -> dict[str, object]:
    """Build the cafe-log form page context.

    `layout="desktop"` swaps the form target / swap so the edit response
    lands in #cafe-form-mount with innerHTML (vs the mobile inline outerHTML
    of [data-row]). Phase 15.1 D-21 pattern.
    """
    is_edit = mode == "edit"
    if layout == "desktop" and is_edit:
        form_target = "#cafe-form-mount"
        form_swap = "innerHTML"
    elif is_edit:
        form_target = "closest [data-row]"
        form_swap = "outerHTML"
    else:
        form_target = "#cafe-form-mount"  # create mode lands in the mount
        form_swap = "innerHTML"

    return {
        "values": values,
        "errors": errors,
        "mode": mode,
        "cafe_log_id": cafe_log_id,
        "form_action": f"/cafe-logs/{cafe_log_id}" if is_edit else "/cafe-logs",
        "form_target": form_target,
        "form_swap": form_swap,
        "layout": layout,
        # Resolved selectables and seeded chips for autocomplete renders ...
        "selected_flavor_notes": _selected_flavor_notes(db, values.get("flavor_note_ids", [])),
        "roaster_name": _resolved_roaster_name(db, values.get("roaster_id")),
    }
```

### Anti-Patterns to Avoid

- **Add a `coffee_id` FK to `cafe_logs`.** CONTEXT D-01 explicitly rejects mixing identity types. The cafe coffee is intentionally NOT a `coffees` row.
- **Add an `is_cafe_log` boolean to `brew_sessions`.** Rejected by D-01 (the unified-table approach). The `brew_sessions.coffee_id NOT NULL ondelete=RESTRICT` invariant blocks it.
- **Add a `cafe_drafts` table.** D-11 rejects autosave for v1.
- **Cite `brew_method` as ENUM/CHECK constraint.** D-05 keeps it free-text.
- **Add a `countries` lookup table.** D-03 explicitly rejects it; origin_country is plain TEXT with suggestions.
- **UNION cafe data into `get_sweet_spots` / `get_top_coffees`.** D-14 + D-16 keep these brew-only.
- **Use Alpine.js client-side tab swap.** Server-side `?tab=` is CSP-cleaner and back/forward-correct.
- **Use the `htmx-indicator` auto-injected style for the upload spinner.** Strict CSP blocks it (project memory: strict-csp-blocks-htmx-indicator). Define indicator styles in `tailwind.src.css`.
- **Forget to update `photos.sweep_orphans` to reference the second table.** Silent photo loss otherwise (Pitfall 8).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EXIF strip + magic-byte validation + thumbnail | A new photo pipeline for cafe photos | `app/services/photos.py` `process_and_save()` | Five layers of defense (size pre-check, magic bytes, Pillow verify, re-encode, EXIF strip); copying any of these is wasted effort and introduces drift |
| Roaster autocomplete + create-on-the-fly | A new "cafe roaster" entity or autocomplete | Reuse `/roasters/list` endpoint + `x-data="autocomplete"` Alpine scope + the modal-mount pattern | Roasters are already a shared catalog; cafe logs and brew sessions both reference them via FK |
| Flavor-note chip input | A new "cafe flavor notes" chip widget | Reuse `flavorNoteChips` Alpine scope + `/flavor-notes/datalist` endpoint + `flavor-note-created` HX-Trigger | Identical UX; copying creates drift |
| Tab toggle that updates URL | A pure-Alpine tab swap | Server-side `?tab=cafe` + `hx-get` + `hx-push-url` (Phase 4 filter-bar pattern) | CSP-clean, back/forward-correct, no JS required for tab swap |
| Dual mobile/desktop Edit button | A separate mobile-only edit route | Phase 15.1 D-21 pattern: same route, `?layout=desktop` query param drives target/swap | Already locked across five entity forms (coffees, brew, equipment, recipes, bags) |
| Country / process / roast-level lookup | A `countries` table or enum | Plain TEXT + autocomplete sourced from existing `coffee_origins.country` distinct values + small seeded list | D-03 explicit; mirrors `coffee_origins.country` precedent |
| Photo orphan sweep | A separate cafe photo sweep | Extend `photos.sweep_orphans` to union `bags.photo_filename` + `cafe_logs.photo_filename` | Single FS scan + single DB query is cheaper than two parallel sweeps |
| CSRF / autoescape / security headers | Per-route opt-in | Already global middleware — every state-changing form gets CSRF; every Jinja template autoescapes | Established invariant; no per-route work |

**Key insight:** The cafe vertical slice is mostly **composition of existing primitives**. New SQL = one table, one migration, one UNION extension. New code = one model, one schema, one service, one router, three templates. The leverage point is **mirroring the brew pattern**.

## Runtime State Inventory

**Skipped.** Phase 16 is a greenfield additive phase — no rename, refactor, migration of existing data, or string replacement. Nothing in the existing repo is being renamed or moved.

Confirmed by re-reading CONTEXT.md:
- `cafe_logs` is a net-new table (D-01) — no existing data to migrate.
- `roasters`, `coffee_origins.country`, `flavor_notes` are referenced but unchanged.
- `compute_input_signature` extension is additive (new payload list, not field-replacement).
- No existing column is being dropped or renamed.

## Common Pitfalls

### Pitfall 1: Autogenerate cannot emit `USING GIN`
**What goes wrong:** Running `alembic revision --autogenerate -m "cafe_logs"` produces a migration that creates the `flavor_note_ids` column but NOT the GIN index — autogenerate emits a plain B-tree (or nothing). The cafe form's flavor-note containment queries then full-scan instead of using GIN.
**Why it happens:** SQLAlchemy 2.0 + Alembic autogenerate does not know how to emit `CREATE INDEX ... USING GIN` for ARRAY columns. [CITED: `app/models/brew_session.py:158-161`, `app/models/coffee.py:125-127`]
**How to avoid:** Hand-edit the autogenerated migration to add `op.execute("CREATE INDEX ix_cafe_logs_flavor_note_ids ON cafe_logs USING GIN (flavor_note_ids)")`. Verify the index exists post-migration: `\d cafe_logs` in psql should show the gin index.
**Warning signs:** Phase 12 test gate's `EXPLAIN ANALYZE` of `get_flavor_descriptors` on a seeded user fails to mention `Bitmap Index Scan on ix_cafe_logs_flavor_note_ids`.

### Pitfall 2: `?layout=desktop` query param must be stripped before Pydantic
**What goes wrong:** The desktop edit path sends `?layout=desktop` as a query param but the form submits as a regular field. If Pydantic's `extra="forbid"` sees `layout` in the submission, it raises a validation error.
**Why it happens:** `coffee_form.html:59-61` adds a hidden `<input name="layout" value="desktop">` to preserve the layout on the form re-render path. The router must include `"layout"` in `_NON_SCHEMA_FORM_KEYS`.
**How to avoid:** Add `"layout"` to `_NON_SCHEMA_FORM_KEYS` in the cafe-logs router (already included in Pattern 4 above). The router's `_parse_form_payload` filters before handing to the schema.
**Warning signs:** Test `test_update_cafe_log_desktop_layout` fails with `_form: layout: extra fields not permitted`.

### Pitfall 3: `cafe_log_id` namespace collision with `coffee_id` in signature payload
**What goes wrong:** If you flatten the brew + cafe rows into one list, a brew row with `coffee_id=42` and a cafe row with `cafe_log_id=42` produce identical 5-tuples (assuming rating + flavor + recipe/roaster + brewer/origin all coincide — unlikely, but possible). The signature becomes non-bijective.
**Why it happens:** Numeric IDs from two different identity sequences cannot collide UNLESS placed in the same flat list. The fix is to keep them as separate lists.
**How to avoid:** Payload shape is `[brew_list, cafe_list]` — a list of two lists, NOT a flat concatenation (Pattern 9 above). The sublist position is the namespace.
**Warning signs:** A `test_signature_brew_id_cafe_id_namespace_collision` test (recommended): seed a user with one brew (coffee_id=N) and one cafe log (id=N); confirm signature differs from the same data without the cafe log.

### Pitfall 4: down_revision must be the head AFTER Phase 15.1
**What goes wrong:** If the planner copies an earlier migration as a template, they may pin `down_revision = "p11_brew_time_seconds"` (the pre-Phase-15.1 head). The Alembic chain forks; `alembic upgrade head` errors.
**Why it happens:** Phase 15.1 introduced 4 migrations (`p15_1_drop_roast_date`, `p15_1_multi_origin`, `p15_1_roast_level_enum`, `p15_1_varietal_m2m`). The current head is `p15_1_varietal_m2m`. [VERIFIED: `app/migrations/versions/` filesystem inventory]
**How to avoid:** Before writing the cafe_logs migration, run `docker compose exec coffee-snobbery alembic heads` to confirm the current head. Pin `down_revision` to that value.
**Warning signs:** `alembic upgrade head` says "Multiple head revisions are present" or "Can't locate revision identified by".

### Pitfall 5: `|tojson` attribute quoting (project memory)
**What goes wrong:** `data-initial-chips="{{ selected_flavor_notes|tojson }}"` breaks HTML parsing because `|tojson` emits double-quoted strings inside JSON arrays.
**Why it happens:** `|tojson` doesn't escape `"` for HTML attribute context; double-quoting the attr nests double-quotes. [VERIFIED: project memory `tojson-attr-quoting-and-live-browser-repro`]
**How to avoid:** Use single quotes for attrs that contain `|tojson`: `data-initial-chips='{{ selected_flavor_notes|tojson }}'`. Confirmed in `coffee_form.html:182, :266`.
**Warning signs:** Browser dev tools shows mangled `data-initial-chips` attr; Alpine `selectedChips` array is empty pre-hydration despite seeded chips.

### Pitfall 6: Test fixtures that skip on missing seed data mask failures
**What goes wrong:** A test that calls `_require_postgres()` + `_require_analytics_tables()` but doesn't include a `_require_cafe_logs_table()` skip-gate will silently pass when the migration hasn't run.
**Why it happens:** The Phase 6 test pattern uses skip-gates rather than hard fixtures. Adding a new table requires a parallel gate. [VERIFIED: project memory `tests-pass-by-skip-mask-green`]
**How to avoid:** Add `_require_cafe_logs_table()` mirroring `_require_analytics_tables()` in `tests/services/test_cafe_logs.py`. Run pytest with `-rs` during `gsd-validate-phase` to see what skipped.
**Warning signs:** `pytest -q` reports "passed" with no test failures, but the cafe migration was never applied — the suite silently skipped every cafe assertion.

### Pitfall 7: Strict CSP blocks htmx-indicator auto-injected style
**What goes wrong:** Photo upload spinner stays visible after the request completes; OR doesn't show at all on slow uploads.
**Why it happens:** Snobbery's nonce-CSP blocks htmx's `htmx-indicator` auto-injected `<style>` (project memory `strict-csp-blocks-htmx-indicator`). The class `.htmx-indicator` has no rule in the bundled CSS, so the `display:inline` toggle on request never works.
**How to avoid:** Define `.htmx-indicator { display: none; } .htmx-request .htmx-indicator { display: inline; } .htmx-request.htmx-indicator { display: inline; }` in `tailwind.src.css` (or reuse if Phase 9 already defined it — verify before assuming). [VERIFIED: project memory; mirror the Phase 9 backup-job fix]
**Warning signs:** Manual UAT shows the upload spinner never appears; or appears and never goes away.

### Pitfall 8: Photo orphan sweep deletes cafe photos
**What goes wrong:** Nightly orphan sweep runs, sees photo files referenced ONLY by `cafe_logs.photo_filename` (not `bags.photo_filename`), classifies them as orphans, deletes them. Every cafe photo disappears overnight.
**Why it happens:** `app/services/photos.py:382-389` currently queries ONLY `bags.photo_filename`. Adding `cafe_logs` without extending this query is silent data loss. [CITED: `app/services/photos.py:382-389`]
**How to avoid:** Extend `sweep_orphans` to union the two reference sources (Pattern 6 above). Test: seed a cafe log with a photo, run `sweep_orphans`, confirm the photo file still exists.
**Warning signs:** A `test_sweep_orphans_keeps_cafe_photos` test fails after the first nightly run; user reports cafe photos missing the morning after.

### Pitfall 9: Signature payload shape change forces one-time AI regen for every user
**What goes wrong:** Changing the signature shape from a flat brew list to `[brew_list, cafe_list]` produces a DIFFERENT SHA256 for every existing user (even users with zero cafe logs). The nightly job sees every user as stale and regenerates every AI recommendation.
**Why it happens:** SHA256 of `[[...]]` ≠ SHA256 of `[...]` even when the inner contents match.
**How to avoid:** TWO options:
  - **(a) Accept the one-time churn** — every user gets one extra AI regen after deploy. At household scale this is 2-3 API calls total. Recommended.
  - **(b) Conditional payload** — `payload = [brew_list, cafe_list] if cafe_list else brew_list`. Backwards-compatible but two-shape signatures are harder to reason about (and a test must cover both shapes).
**Recommendation:** Option (a). Document in the Phase 16 SUMMARY that "first nightly run post-deploy regenerates every AI rec; expected behavior."
**Warning signs:** Operator sees an unusual spike in Anthropic/OpenAI API calls the night after Phase 16 deploys.

### Pitfall 10: Origin country = "Costa Rica" vs "costa rica" vs "Costa rica"
**What goes wrong:** D-13 origin UNION groups by `cafe_logs.origin_country`. A user typing "ethiopia" and "Ethiopia" creates two preference-profile rows for the same country.
**Why it happens:** `cafe_logs.origin_country` is plain TEXT, not CITEXT. The autocomplete suggests existing values but doesn't enforce them.
**How to avoid:** Either:
  - **(a) Title-case server-side** — `origin_country.strip().title()` before insert/update. Simple, lossy (won't handle "Côte d'Ivoire" cleanly).
  - **(b) Use CITEXT on the column** — case-insensitive equality at the DB layer. Cleaner, no server-side massaging needed. CONTEXT D-03 says plain TEXT; this is a minor deviation worth flagging.
  - **(c) Leave as-is and accept duplicates** — the autocomplete suggestions reduce the duplicate rate to ~0 in practice.
**Recommendation:** (c) for v1 — same approach as `coffee_origins.country` (which is plain TEXT). If duplicates become a problem in practice, add a one-line server-side `.title()` in a future polish phase.
**Warning signs:** Preference profile shows "Ethiopia" and "ethiopia" as two rows.

### Pitfall 11: `cafe_logs` not registered in app/main.py
**What goes wrong:** Routes return 404 because the router isn't included.
**Why it happens:** New routers require `app.include_router(cafe_logs.router)` in `app/main.py`. Easy to forget.
**How to avoid:** Include `from app.routers import cafe_logs` + `app.include_router(cafe_logs.router)` in `app/main.py`. Verify with `pytest tests/routers/test_cafe_logs.py::test_new_form_renders` (a 404 here is the smoking gun).
**Warning signs:** Every cafe_logs route returns 404 + "Not Found"; the routes don't appear in `/openapi.json`.

### Pitfall 12: Executor loosens schema for bad fixtures (project memory)
**What goes wrong:** Executor encounters a test fixture that's missing a `flavor_note_ids` value, "helpfully" makes the column nullable in the migration, schema drifts from the plan.
**Why it happens:** Executors fix the wrong thing — the fixture, not the schema. [VERIFIED: project memory `executor-loosens-schema-for-bad-fixtures`]
**How to avoid:** Per-wave: diff `app/models/cafe_log.py` and `app/migrations/versions/pXX_cafe_logs.py` against the plan's `files_modified`. If a column nullable status drifted from the plan, the executor went off-script. Fix the fixture instead.
**Warning signs:** Post-execution diff shows the column type/nullable signature drifted vs the plan.

### Pitfall 13: VALIDATION.md `-k` filters that match nothing
**What goes wrong:** A row in `cafe_logs/16-VALIDATION.md` says "Covered by `pytest -k 'cafe and signature'`" but the filter collects 0 tests.
**Why it happens:** No test exists yet that matches the filter, OR the test name doesn't contain those words. [VERIFIED: project memory `validation-md-vacuous-k-filters`]
**How to avoid:** During `gsd-validate-phase`, run every filter standalone; confirm `>= 1` test was collected per row. If 0, the requirement is uncovered.
**Warning signs:** `pytest --collect-only -k '<filter>'` shows "no tests ran".

## Code Examples

### Compute input signature with cafe extension

See Pattern 9 above. Source: `app/services/analytics.py:353-399` (existing implementation to extend).

### UNION ALL preference profile dim

See Pattern 10 above. Source: `app/services/analytics.py:78-150` (existing dim queries to extend); SQLAlchemy 2.0 union_all docs: https://docs.sqlalchemy.org/en/20/tutorial/data_select.html.

### Sweet-spots guard comment (D-16)

```python
# Source: app/services/analytics.py:191-230 (existing function — BODY UNCHANGED)
# ADD: one-line comment

def get_sweet_spots(db: Session, user_id: int) -> list[Row]:
    """Top 3 (origin x process x brewer x recipe) combos, min 3 rated sessions.

    Uses a single GROUP BY over all five dimension columns. Sessions with NULL
    brewer_id or recipe_id are excluded by INNER JOIN — this is the documented
    v1 behavior (Pitfall 7). No Python loops; pure SQL aggregation.

    Origin now joins coffee_origins (D-01); a blend session contributes one
    row per origin so the per-origin sweet-spot stays truthful.

    NOTE (CAFE-05 / D-16): Cafe logs are intentionally excluded — they have
    no brew-parameter fields (no recipe_id, brewer_id, dose, yield, temp, or
    grind setting). Do not UNION cafe data into this query.
    """
    # ... existing body unchanged ...
```

### Cafe log service module — list / create stub

```python
# Source: app/services/brew_sessions.py (pattern) + app/services/photos.py call-through
"""Cafe-log service — CRUD + photo orchestration. Per-user scoped.

Mirrors app/services/brew_sessions.py structurally. All writes are
single-transaction (Phase 1 D-14 audit pattern: NO audit event for cafe
logs at v1 — household-scale audit posture is auth + admin events).
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.cafe_log import CafeLog
from app.services import photos as photos_service

log = structlog.get_logger(__name__)


def create_cafe_log(
    db: Session,
    *,
    by_user_id: int,
    cafe_name: str,
    rating: Decimal | None,
    roaster_id: int | None = None,
    origin_country: str | None = None,
    brew_method: str | None = None,
    flavor_note_ids: list[int] | None = None,
    notes: str = "",
    photo_blob: bytes | None = None,
    logged_at: datetime | None = None,
) -> CafeLog:
    """Insert a cafe log. Photo blob (if any) goes through photos.process_and_save."""
    photo_filename = None
    if photo_blob is not None and len(photo_blob) > 0:
        # Raises PhotoRejected on bad input — router catches + re-renders.
        photo_filename = photos_service.process_and_save(photo_blob)

    log_row = CafeLog(
        user_id=by_user_id,
        cafe_name=cafe_name,
        rating=rating,
        roaster_id=roaster_id,
        origin_country=origin_country,
        brew_method=brew_method,
        flavor_note_ids=flavor_note_ids or [],
        notes=notes,
        photo_filename=photo_filename,
        logged_at=logged_at,
    )
    db.add(log_row)
    db.commit()
    db.refresh(log_row)
    return log_row


def get_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int) -> CafeLog | None:
    """Per-user lookup (T-IDOR). Returns None on cross-user (router 404s)."""
    return db.execute(
        select(CafeLog).where(
            CafeLog.id == cafe_log_id,
            CafeLog.user_id == by_user_id,
        )
    ).scalar_one_or_none()


def list_cafe_logs(
    db: Session,
    *,
    by_user_id: int,
    rating_min: Decimal | None = None,
    rating_max: Decimal | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CafeLog]:
    """Per-user list, logged_at DESC. Optional rating + date filters."""
    stmt = select(CafeLog).where(CafeLog.user_id == by_user_id)
    if rating_min is not None:
        stmt = stmt.where(CafeLog.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(CafeLog.rating <= rating_max)
    if date_from is not None:
        stmt = stmt.where(CafeLog.logged_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(CafeLog.logged_at <= date_to)
    stmt = stmt.order_by(CafeLog.logged_at.desc())
    return list(db.execute(stmt).scalars().all())


def update_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int, **fields) -> CafeLog | None:
    """Update if owned. Returns None on cross-user. Photo replacement handled separately."""
    existing = get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=by_user_id)
    if existing is None:
        return None
    for key, value in fields.items():
        if hasattr(existing, key):
            setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return existing


def delete_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int) -> bool:
    """Hard-delete if owned. Returns True on success, False on cross-user.

    Photo file unlink happens nightly via photos.sweep_orphans — the
    row deletion alone is the canonical "delete" action (matches bag
    delete semantics).
    """
    existing = get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=by_user_id)
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    return True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cafe logs as a CSV import column on brew sessions | Separate `cafe_logs` table (D-01) | This phase | Clean separation; sweet-spots stays brew-only without flag-filtering |
| Cafe logs feed nothing | Cafe ratings/flavor/origin/roaster feed preference + AI signature (D-12/D-13/D-15) | This phase | AI recommendations reflect cafe taste data; cold-start opens faster for taste-out users |
| `bags.photo_filename` is the only photo reference | `bags.photo_filename` ∪ `cafe_logs.photo_filename` | This phase | `sweep_orphans` must union the two |
| Sessions page header has 2 buttons | Sessions page header has 3 buttons (Guided Brew, Log session, Quick rate) | This phase | One extra flex item; mobile layout still fits |

**Deprecated / outdated:** None — the phase is purely additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Current Alembic head is `p15_1_varietal_m2m` (Phase 15.1 has merged into main) | Pattern 2 (down_revision) | Migration chain forks; `alembic upgrade head` errors at deploy. **Mitigation:** Pitfall 4 — verify with `alembic heads` before writing the value. |
| A2 | The cold-start meter UI in `_cold_start.html` consumes the dict keys `sessions`, `distinct_notes`, `sessions_needed`, `notes_needed` and nothing else | Pattern 11 (cold-start) | Adding `brew_count` / `cafe_count` keys is non-breaking, but the meter copy ("Log {N} more brews") is now slightly inaccurate. **Mitigation:** Recommendation (a) — accept the imprecision; Phase 17 owns copy polish. |
| A3 | The CSRF middleware extracts the token from the `X-CSRF-Token` header populated by the existing `CSRFFormFieldShim` (which hoists hidden `<input name="X-CSRF-Token">` into the header) | Pattern 4 + 12 (router CSRF) | If CSRF is broken on the new routes, every POST 403s. **Mitigation:** Use the established hidden input + middleware pattern from `coffee_form.html:57`; do NOT skip CSRF. |
| A4 | The Phase 12 test suite gate runs against a BAKED tree (no source bind-mount); cafe_logs migration must be in the image at build time, not just on disk | Pitfall 6 + test infrastructure | If only the source has the migration but the image is stale, the test gate silently skips every cafe assertion. **Mitigation:** Project memory `snobbery-test-gate-runtime`; rebuild before running gate. |
| A5 | The signature shape change forces one-time AI regen per user; the AI provider cost is acceptable at household scale (~6 users × $0.01-0.10 per call) | Pitfall 9 | If household scale grows or if cost is more sensitive than assumed, option (b) conditional payload may be preferred. **Mitigation:** Document in SUMMARY; flag for operator awareness. |

**Risk if any assumption wrong:** All five are LOW-risk and easily verified pre-execution. None require user confirmation.

## Open Questions

1. **Cold-start meter copy under combined counts (Pattern 11 (a)/(b)/(c)).**
   - What we know: D-15 changes the count arithmetic; the existing `_cold_start.html` copy reads "Log {N} more brews".
   - What's unclear: Whether the planner wants to defer copy polish to Phase 17 (recommended) or update the copy now to say "session" / "log" instead of "brew".
   - Recommendation: Defer (option a) — keep template churn out of Phase 16. Phase 17 (IA restructure) owns home-copy polish.

2. **Origin country case dedup (Pitfall 10 (a)/(b)/(c)).**
   - What we know: `cafe_logs.origin_country` is plain TEXT per D-03.
   - What's unclear: Whether the autocomplete + seeded list is sufficient to prevent practical case duplicates ("Ethiopia" vs "ethiopia"), or whether a server-side `.title()` should land in this phase.
   - Recommendation: (c) — leave as-is, match `coffee_origins.country` precedent. Revisit in a future polish phase if real duplicates emerge.

3. **Should the signature payload conditionally include the cafe list (Pitfall 9 (a)/(b))?**
   - What we know: Option (a) forces a one-time regen per user; option (b) keeps the existing brew-only signature stable when cafe_logs are absent.
   - What's unclear: Whether the planner wants stable-on-existing-data semantics or accepts the one-time churn.
   - Recommendation: (a) — cleaner code, one-time cost is trivial at household scale.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 16 | All — cafe_logs schema + UNION + GIN | ✓ (production + dev container) | 16 (alpine) | — |
| Pillow 12.x | Photo pipeline reuse | ✓ (already pinned) | 12.2 | — |
| psycopg 3.x | ARRAY + GIN | ✓ | 3.3 | — |
| pytest + pytest-asyncio | Tests | ✓ (NOT in production image — install in container: `pip install --user pytest pytest-asyncio respx`) | latest | — |
| Playwright | Mobile UAT at 375px | ✓ (Phase 12 baked at `/ms-playwright`) | 1.59 | Manual UAT on physical phone |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

Phase 16 introduces zero new external dependencies. Every primitive is already in the stack and verified by Phase 0-15.1.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0 + pytest-asyncio + respx (HTTP mock, unused this phase) |
| Config file | `pyproject.toml` (no separate pytest.ini) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/services/test_cafe_logs.py tests/routers/test_cafe_logs.py -q -x` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest tests/ -q` (see project memory `snobbery-test-gate-runtime` — drop snobbery_test DB before full run) |
| Phase gate | Run gate against BAKED image — rebuild `docker compose build coffee-snobbery` then `pytest tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CAFE-01 | GET /cafe-logs/new renders form with autofocus on cafe_name | router unit | `pytest tests/routers/test_cafe_logs.py::test_new_form_renders -x` | ❌ Wave 0 |
| CAFE-01 | POST /cafe-logs with only cafe_name + rating succeeds in <one round-trip | router unit | `pytest tests/routers/test_cafe_logs.py::test_create_minimal_payload -x` | ❌ Wave 0 |
| CAFE-02 | POST /cafe-logs accepts roaster_id + origin + brew_method + flavor_note_ids + notes + photo | router unit | `pytest tests/routers/test_cafe_logs.py::test_create_full_enrichment -x` | ❌ Wave 0 |
| CAFE-02 | Photo upload rejects oversize / bad magic / decompression bomb via photos.PhotoRejected | router unit | `pytest tests/routers/test_cafe_logs.py::test_photo_rejection_paths -x` | ❌ Wave 0 |
| CAFE-03 | GET /brew?tab=cafe returns cafe-list fragment; visual class includes border-l-amber-500 | router unit | `pytest tests/routers/test_cafe_logs.py::test_tab_cafe_renders_list -x` | ❌ Wave 0 |
| CAFE-03 | Empty state for cafe tab is blank (no copy, no hint) — D-08 | router unit | `pytest tests/routers/test_cafe_logs.py::test_empty_state_is_blank -x` | ❌ Wave 0 |
| CAFE-03 | Per-user IDOR: user A cannot read user B's cafe logs | router IDOR | `pytest tests/routers/test_cafe_logs.py::test_cross_user_returns_404 -x` | ❌ Wave 0 |
| CAFE-04 | compute_input_signature changes when a rated cafe log is added | service unit | `pytest tests/services/test_analytics.py::test_signature_includes_cafe_logs -x` | ❌ Wave 0 |
| CAFE-04 | compute_input_signature unchanged when an UNRATED cafe log is added | service unit | `pytest tests/services/test_analytics.py::test_signature_excludes_unrated_cafe -x` | ❌ Wave 0 |
| CAFE-04 | get_preference_profile origin dim UNIONs brew + cafe rows | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_origin_unions_cafe -x` | ❌ Wave 0 |
| CAFE-04 | get_preference_profile roaster dim UNIONs brew + cafe rows | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_roaster_unions_cafe -x` | ❌ Wave 0 |
| CAFE-04 | get_preference_profile process + roast_level dims stay brew-only | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_process_brew_only -x` | ❌ Wave 0 |
| CAFE-04 | get_flavor_descriptors UNIONs rated-4+ brew + cafe arrays | service unit | `pytest tests/services/test_analytics.py::test_flavor_descriptors_unions_cafe -x` | ❌ Wave 0 |
| CAFE-04 | get_cold_start_counts: brew-only threshold | service unit | `pytest tests/services/test_analytics.py::test_cold_start_brew_only -x` | ❌ Wave 0 |
| CAFE-04 | get_cold_start_counts: cafe-only threshold | service unit | `pytest tests/services/test_analytics.py::test_cold_start_cafe_only -x` | ❌ Wave 0 |
| CAFE-04 | get_cold_start_counts: mixed threshold (1 brew + 2 cafe = 3 → gate-open if notes ≥5) | service unit | `pytest tests/services/test_analytics.py::test_cold_start_mixed -x` | ❌ Wave 0 |
| CAFE-05 | get_sweet_spots ignores cafe rows (no UNION) | service unit | `pytest tests/services/test_analytics.py::test_sweet_spots_excludes_cafe -x` | ❌ Wave 0 |
| CAFE-05 | get_top_coffees ignores cafe rows | service unit | `pytest tests/services/test_analytics.py::test_top_coffees_excludes_cafe -x` | ❌ Wave 0 |
| CAFE-06 | POST /cafe-logs/{id} with _method=DELETE removes own log | router unit | `pytest tests/routers/test_cafe_logs.py::test_delete_own_succeeds -x` | ❌ Wave 0 |
| CAFE-06 | DELETE of another user's cafe log returns 404 (IDOR) | router IDOR | `pytest tests/routers/test_cafe_logs.py::test_delete_cross_user_404 -x` | ❌ Wave 0 |
| CAFE-06 | GET /cafe-logs/{id}/edit renders form with stored values | router unit | `pytest tests/routers/test_cafe_logs.py::test_edit_form_renders -x` | ❌ Wave 0 |
| CAFE-06 | GET /cafe-logs/{id}/edit?layout=desktop renders desktop variant | router unit | `pytest tests/routers/test_cafe_logs.py::test_edit_form_desktop_layout -x` | ❌ Wave 0 |
| CAFE-06 | POST /cafe-logs/{id} updates own log | router unit | `pytest tests/routers/test_cafe_logs.py::test_update_own_succeeds -x` | ❌ Wave 0 |
| All | photos.sweep_orphans keeps cafe photos (does NOT delete files referenced by cafe_logs.photo_filename) | service unit | `pytest tests/services/test_photos.py::test_sweep_keeps_cafe_photos -x` | ❌ Wave 0 |
| All | Cafe_logs migration applies cleanly on top of p15_1_varietal_m2m | migration smoke | `pytest tests/migrations/test_cafe_logs_migration.py -x` | ❌ Wave 0 |
| All | UAT @ 375px: Quick rate button visible in /brew header; tab toggle works; cafe form fits viewport | manual UAT | Documented in 16-VERIFICATION.md | n/a (human) |

### Sampling Rate

- **Per task commit:** `pytest tests/services/test_cafe_logs.py tests/routers/test_cafe_logs.py -q -x` (~ <5s)
- **Per wave merge:** `pytest tests/services/test_cafe_logs.py tests/routers/test_cafe_logs.py tests/services/test_analytics.py tests/services/test_photos.py::test_sweep_keeps_cafe_photos -q` (~10-20s)
- **Phase gate:** Full suite `pytest tests/ -q -rs` green against BAKED image; `-rs` flag treats skips as visible (project memory `tests-pass-by-skip-mask-green`)

### Wave 0 Gaps

- [ ] `tests/services/test_cafe_logs.py` — covers CAFE-01..06 service-layer (CRUD + photo orchestration)
- [ ] `tests/routers/test_cafe_logs.py` — covers CAFE-01..03, CAFE-06 router-level (CSRF, IDOR, multipart, layout query param)
- [ ] `tests/services/test_analytics.py` — extend `_seed_analytics_scenario` to include cafe fixtures + add cafe-specific test functions (signature, preference profile, flavor descriptors, cold-start, sweet-spots/top-coffees exclusion)
- [ ] `tests/services/test_photos.py::test_sweep_keeps_cafe_photos` — verify sweep_orphans extension
- [ ] `tests/migrations/test_cafe_logs_migration.py` — smoke test the upgrade + downgrade chain
- [ ] `_require_cafe_logs_table()` skip-gate helper in `tests/conftest.py` (or local to the new test files) — mirror `_require_analytics_tables()`

*All gaps net-new — no existing test infrastructure covers cafe_logs because the table doesn't exist yet.*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (inherited) | `Depends(require_user)` on every cafe_logs route — argon2 password / Fernet API key invariants unchanged |
| V3 Session Management | Yes (inherited) | Signed session cookies via itsdangerous + server-side `sessions` table; no change |
| V4 Access Control | Yes | Per-user scoping on every read/write — `cafe_logs.user_id` filter; cross-user returns 404 (non-leak) |
| V5 Input Validation | Yes | Pydantic v2 `extra="forbid"` on `CafeLogCreate` / `CafeLogUpdate`; ValidationError → 200 + form re-render |
| V6 Cryptography | No new surface | Photo bytes are validated but never encrypted; API key encryption (Fernet) untouched |
| V8 Data Protection | Yes | Photo EXIF strip via `photos.process_and_save()`; no PII in cafe log content |
| V12 File Upload | Yes | Magic-byte check + Pillow verify + re-encode + decompression-bomb cap + path-traversal-safe UUID4 filename. All inherited from `app/services/photos.py:170-256` |
| V13 API Security | Yes | CSRF on every state-changing form via global `starlette-csrf` middleware; security headers on every response |

### Known Threat Patterns for FastAPI + Jinja + HTMX

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via free-text origin_country | Tampering | SQLAlchemy 2.0 parameterized queries; `select()` constructs everywhere; raw SQL in analytics uses bound `:user_id` (existing pattern verified) |
| IDOR on cafe_log_id | Information Disclosure | Service layer takes `by_user_id` kwarg; `get_cafe_log` filters by user_id; cross-user returns None → router 404 (non-leak vs 403) |
| Mass-assignment (posting `user_id` in form body) | Tampering | `extra="forbid"` rejects unknown fields; `user_id` and `photo_filename` deliberately absent from schema |
| CSRF on POST/PUT/DELETE | Tampering | Global middleware enforces double-submit-cookie + X-CSRF-Token header; hidden input + `request.cookies.get('csrftoken')` pattern in template |
| XSS via user notes / cafe_name | Information Disclosure | Jinja2 autoescape ON globally; cafe form renders all user strings via `{{ value }}` (escaped) — no `|safe`, no `|tojson` in raw HTML context |
| Decompression bomb / polyglot photo | DoS / Tampering | `Image.MAX_IMAGE_PIXELS` cap + magic-byte gate + Pillow re-encode strips trailing bytes (inherited from `photos.py`) |
| Photo path traversal | Tampering | UUID4-hex `.jpg` filename via `_is_safe_photo_filename` regex (inherited) |
| Cross-user data leak via shared autocomplete | Information Disclosure | Roaster + flavor_note autocompletes return shared-catalog rows (intentional, household-scale); origin_country autocomplete returns distinct values across all coffees (intentional — countries aren't user-private) |
| Brute-force on /cafe-logs/new (DoS) | DoS | Existing `slowapi` rate limit on /login covers session creation; cafe form post-auth is rate-limited by FastAPI's default concurrency at household scale (no extra control needed) |

**Specific compliance checks for this phase:**
- [ ] Every cafe_logs route has `Depends(require_user)`
- [ ] Every cafe_logs service function takes `by_user_id` kwarg and filters on it
- [ ] `CafeLogCreate` / `CafeLogUpdate` declare `model_config = ConfigDict(extra="forbid")`
- [ ] `user_id` and `photo_filename` are NOT declared as schema fields
- [ ] All form templates include `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">`
- [ ] Photo upload routes through `photos.process_and_save()` — no direct PIL.Image calls
- [ ] No raw SQL with unparameterized user input; bound `:user_id` everywhere
- [ ] Cross-user fetch returns None → 404, not 403

## Decision-to-Plan-Slice Mapping

The plan-checker scans plan frontmatter `must_haves:` for D-NN citations (project memory: decision-coverage-gate-scans-must-haves). Use this map to ensure every D-NN appears in at least one plan's must_haves.

| Decision | Plan slice recommended | Reasoning |
|----------|----------------------|-----------|
| D-01 (separate table) | `16-01-migration.md` (cafe_logs schema + migration) | Locks in the architectural choice; this plan creates the table |
| D-02 (roaster_id FK + autocomplete) | `16-01-migration.md` (FK definition) + `16-03-form.md` (autocomplete UX) | FK in migration + autocomplete in template |
| D-03 (origin_country TEXT + autocomplete) | `16-01-migration.md` (column shape) + `16-02-router.md` (autocomplete endpoint) | Column shape in migration; new endpoint in router |
| D-04 (flavor_note_ids BIGINT[] + GIN) | `16-01-migration.md` (hand-edited GIN op.execute) | Migration owns the GIN |
| D-05 (brew_method TEXT free-text) | `16-01-migration.md` (column shape) | One-line schema decision |
| D-06 (tab toggle on /brew?tab=cafe) | `16-04-list-and-tab.md` (extending brew router + sessions.html) | Tab routing branch + template change |
| D-07 (border-l-2 amber + cup icon) | `16-04-list-and-tab.md` (cafe_log_card.html + cafe_log_row.html templates) | Visual treatment in the new templates |
| D-08 (blank empty state) | `16-04-list-and-tab.md` (cafe_log_list.html empty branch) | One template branch |
| D-09 (Quick rate button on /brew header) | `16-04-list-and-tab.md` (sessions.html header) | Same template that gets the tab toggle |
| D-10 (dedicated /cafe-logs/new + /edit pages) | `16-02-router.md` + `16-03-form.md` | Routes + page template |
| D-11 (single-scroll form, autofocus, no autosave) | `16-03-form.md` (cafe_log_form.html structure) | Form template is the single source |
| D-12 (compute_input_signature extension) | `16-05-analytics.md` (signature) | Specific function in analytics.py |
| D-13 (preference profile UNIONs + flavor_descriptors UNION) | `16-05-analytics.md` (preference dims) | Same plan as signature for coherence |
| D-14 (top_coffees stays brew-only) | `16-05-analytics.md` (one-line comment in get_top_coffees) | Documentation-only change in same plan |
| D-15 (cold-start gate cafe+brew) | `16-05-analytics.md` (get_cold_start_counts extension) | Single function update |
| D-16 (sweet_spots exclusion comment) | `16-05-analytics.md` (one-line comment in get_sweet_spots) | Documentation-only change in same plan |

**Suggested wave structure (planner sets actual order):**

- **Wave 0** (test infrastructure): test files + fixtures + `_require_cafe_logs_table()` gate
- **Wave 1** (data layer): plan 16-01 (model + migration + GIN) — `must_haves: [D-01, D-02, D-03, D-04, D-05]`
- **Wave 2** (service + router scaffold): plan 16-02 (router + service + autocomplete endpoints) — `must_haves: [D-03, D-10]`
- **Wave 3** (form UX): plan 16-03 (cafe_log_form.html + Alpine chip + photo + dual Edit) — `must_haves: [D-02, D-10, D-11]`
- **Wave 4** (list + tab + visual): plan 16-04 (sessions.html mods + cafe_log_card/row/list templates) — `must_haves: [D-06, D-07, D-08, D-09]`
- **Wave 5** (analytics + AI): plan 16-05 (analytics.py extensions + sweep_orphans extension) — `must_haves: [D-12, D-13, D-14, D-15, D-16]`

Waves 3 and 4 can parallelize if the executor pattern allows; Waves 1 → 2 → 3,4 → 5 is the strict dep order.

## Open Implementation Tactics for the Planner

These are CONTEXT.md's "Claude's discretion — open implementation tactics" items, with research-supported recommendations:

1. **Audit-log entry for cafe log create/edit/delete?** **No** at v1. Household-scale audit posture is "auth + admin events" (CLAUDE.md). Cafe log churn is user-content noise.
2. **UNION SQL shape for D-13:** Per-dimension UNION subquery (Pattern 10). Avoids interleaving four dims in one giant CTE; aligns with existing `analytics.py` style.
3. **Cold-start arithmetic single-SQL vs two-queries-summed:** Two-queries-summed (Pattern 11). Existing function already runs two queries; parallel structure stays readable.
4. **Tab routing pattern:** Server-side `?tab=cafe` + `hx-get` + `hx-push-url` (Pattern 7). CSP-clean, back/forward-correct.
5. **Pydantic schema in `app/schemas/cafe_log.py`:** Yes (Pattern 3) — one-schema-per-model convention.
6. **Tests in `tests/services/test_cafe_logs.py` + `tests/routers/test_cafe_logs.py`:** Yes — convention. Extend `tests/services/test_analytics.py` rather than fork (existing seed helper + skip gates).

## Sources

### Primary (HIGH confidence)
- `app/models/brew_session.py` — FK directionality, ARRAY+GIN pattern, hand-edit migration caveat [VERIFIED: read]
- `app/models/coffee.py` — ARRAY+GIN pattern (second instance) [VERIFIED: read]
- `app/models/coffee_origin.py` — plain Text country column pattern (NOT CITEXT) [VERIFIED: read]
- `app/services/analytics.py` — all five functions to modify (lines 47, 78, 158, 191, 309, 353) [VERIFIED: read]
- `app/services/photos.py` — process_and_save + sweep_orphans (the orphan-sweep blind spot) [VERIFIED: read]
- `app/services/flavor_notes.py` — autocomplete pattern source [VERIFIED: read]
- `app/routers/brew.py` — `_hydrate_form_context`, `_parse_form_payload`, mass-assignment defense, route order [VERIFIED: read]
- `app/routers/bags.py` — photo upload defense-in-depth pattern [VERIFIED: read]
- `app/routers/home.py` — cold-start gate UI consumer [VERIFIED: read]
- `app/schemas/brew_session.py` — Pydantic v2 + `extra="forbid"` + Decimal multiple_of pattern [VERIFIED: read]
- `app/templates/pages/sessions.html` — header structure for Quick rate button + filter pattern [VERIFIED: read]
- `app/templates/pages/brew_form.html` — sticky-bottom Save area + scope nesting + safe-area-inset padding [VERIFIED: read]
- `app/templates/fragments/coffee_form.html` — autocomplete + chip-builder Alpine pattern [VERIFIED: read]
- `app/templates/fragments/coffee_row.html` — Phase 15.1 D-21 dual Edit button + OOB clear [VERIFIED: read]
- `app/templates/fragments/session_list.html` — desktop table + mobile card + empty-state branches [VERIFIED: read]
- `app/templates/fragments/autocomplete_list.html` — dropdown structure + create-new affordance [VERIFIED: read]
- `app/templates/fragments/home/_cold_start.html` — gate UI dict-key contract [VERIFIED: read]
- `app/migrations/versions/p5_brew_sessions.py` — migration template with GIN + DESC B-tree via op.execute [VERIFIED: read]
- `app/migrations/versions/p15_1_multi_origin.py` — `coffee_origins` table introduction (origin autocomplete source) [VERIFIED: read]
- `tests/services/test_analytics.py` — `_seed_analytics_scenario` + skip-gate pattern + signature determinism tests [VERIFIED: read]
- `.planning/phases/16-cafe-quick-rate/16-CONTEXT.md` — the 16 D-decisions and deferred items [VERIFIED: read]
- `CLAUDE.md` — stack invariants, version pins, communication style [VERIFIED: read]
- `.planning/STATE.md` — STATE override on cafe analytics scope [VERIFIED: read]

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.0 SELECT docs (UNION ALL idiom) — https://docs.sqlalchemy.org/en/20/tutorial/data_select.html [CITED]
- HTMX 2.x migration guide (kebab-case hx-on, DELETE → POST+_method) — CLAUDE.md § 3.2 [CITED]
- Heroicons (cup icon source) — https://heroicons.com [ASSUMED present in app/static — verify, otherwise use inline SVG path inline]

### Tertiary (LOW confidence)
- *None* — every load-bearing claim has a verified or cited source.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library pinned, all patterns precedented in the repo
- Architecture: HIGH — purely additive; CONTEXT.md locks every choice
- Pitfalls: HIGH — 13 pitfalls catalogued, each tied to a specific source / project memory
- Analytics integration: HIGH — UNION + signature shape verified against the existing analytics.py module shape

**Research date:** 2026-05-27
**Valid until:** 2026-06-27 (estimate — 30 days; stable codebase, no rapidly-shifting library APIs touched)

---

## RESEARCH COMPLETE

**Phase:** 16 — Cafe Quick-Rate
**Confidence:** HIGH

Phase 16 is a purely-additive vertical slice: one new `cafe_logs` table, model, schema, service, router, three templates, one migration, plus surgical extensions to `analytics.py` (signature, three dim UNIONs, cold-start). CONTEXT.md is exceptionally complete — all 16 D-decisions are locked, no alternatives to research. The phase's leverage is **mirroring the brew vertical slice verbatim** (Phase 5 + Phase 15.1 D-21 patterns) and **composing existing primitives** (photo pipeline, autocomplete, chip widgets, CSRF middleware). The one non-trivial cross-cutting work is the analytics integration, which appends a second list to a SHA256 payload and UNIONs three dim queries via Postgres `UNION ALL` subqueries (Pattern 10). Sweet-spots and top-coffees stay brew-only with one-line guard comments. 13 pitfalls catalogued, with explicit warning signs and remediations; the highest-risk landmines are (a) signature shape change forcing one-time AI regen, (b) photo orphan sweep blind to the second table, and (c) Alembic autogenerate dropping the GIN clause. All decisions map cleanly to a recommended 5-wave plan structure. Planner can proceed directly to writing plans — no further research required, no user confirmation needed on assumptions.
