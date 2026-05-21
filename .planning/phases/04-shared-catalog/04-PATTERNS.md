# Phase 4: Shared Catalog - Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** ~50 (5 new models + 1 modified, 7 routers, 7 services, 6 schemas, 5 pages + ~15 fragments + 1 detail page, 4 JS files, 1 migration, `events.py` extension, `dependencies/auth.py` already has `require_user`)
**Analogs found:** strong analogs in repo for every category — confidence HIGH

---

## Cross-Cutting Notes for Planner

1. **`require_user` already exists** at `app/dependencies/auth.py:33-45` (verified) — Phase 4 does NOT need to add it. Just `Depends(require_user)` in catalog routes that need an authenticated session.
2. **Sync `SessionLocal`** is the Phase 4 DB session (per Phase 3 D-07 + CONTEXT). Async path is reserved for auth. There is **no** existing FastAPI dep that hands out a sync `Session` — Phase 4 must add one (e.g., `app/dependencies/db.py::get_session()` analog to the existing `get_async_session`). Use the contextmanager pattern already documented in `app/db.py:18-22`.
3. **The existing `app/routers/auth.py` uses `AsyncSession`** — its handler shapes are still the right structural reference (Form params, `request: Request`, `templates.TemplateResponse`, `status_code=200` re-render on validation failure), but the DB session type changes from `AsyncSession` to `Session` and `await db.execute(...)` becomes `db.execute(...)`.
4. **Two CSRF tokens, one pattern.** Every Phase 4 form (inline form, mini-modal, photo upload, archive POST) carries the same hidden input copied verbatim from `pages/setup.html:10` and `pages/login.html:9`. HTMX-driven POSTs additionally get the header injected by `app/static/js/htmx-listeners.js:34-39` from the `meta[name=csrf-token]` tag in `base.html:10`.
5. **Audit-event taxonomy.** Phase 4 extends `app/events.py` with `catalog.<entity>.<action>` constants following the Phase 1 D-14 taxonomy already implemented in that file (lines 39-75). Add to `__all__` at the bottom.
6. **Templates package autoescape ON.** `app/templates_setup.py:43` enforces this. No `|safe`. Match-highlighting in autocomplete must wrap with `<strong>` server-side after both halves are template-escaped.
7. **Alpine CSP build.** Templates can only use `x-data="componentName"` (string referring to a registered factory) — never inline object literals. Pattern reference at `app/static/js/alpine-components/__init.js:33-49`.

---

## File Classification

### Models

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/models/coffee.py` | model | CRUD | `app/models/user.py` (CITEXT unique), `app/models/api_credential.py` (CheckConstraint), `app/models/bag.py` (BigInteger Identity + audit cols) | exact (composite) |
| `app/models/roaster.py` | model | CRUD | `app/models/user.py` (CITEXT unique) | exact |
| `app/models/flavor_note.py` | model | CRUD | `app/models/user.py` (CITEXT) + `app/models/api_credential.py` (CheckConstraint on category enum) | exact |
| `app/models/equipment.py` | model | CRUD | `app/models/api_credential.py` (CheckConstraint on type enum), `app/models/bag.py` (BigInteger Identity) | exact |
| `app/models/recipe.py` | model | CRUD | `app/models/ai_recommendation.py` referenced through `0001_initial.py:165` for `JSONB`; `app/models/bag.py` for audit columns | role-match |
| `app/models/bag.py` | model (MODIFY) | CRUD | `app/models/bag.py` itself (already shipped) | self |
| `app/models/__init__.py` | model registry (MODIFY) | n/a | `app/models/__init__.py` itself | self |

### Schemas

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/schemas/coffee.py` | schema | request-response | `app/schemas/auth.py` (BaseModel + Field constraints + ValidationError caught at router) | exact |
| `app/schemas/roaster.py` | schema | request-response | `app/schemas/auth.py` (BaseModel + Field) — adds `HttpUrl` for website | role-match |
| `app/schemas/flavor_note.py` | schema | request-response | `app/schemas/auth.py` (BaseModel + Field with regex/enum constraint) | role-match |
| `app/schemas/equipment.py` | schema | request-response | `app/schemas/auth.py` | role-match |
| `app/schemas/recipe.py` | schema | request-response | `app/schemas/auth.py` + nested step model with `Field(ge=, le=)` | role-match |
| `app/schemas/bag.py` | schema | request-response | `app/schemas/auth.py` | role-match |

### Services

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/coffees.py` | service | CRUD | `app/services/credentials.py` (kwargs API, `select()`/`update()`, audit-event emission, single commit) + `app/services/settings.py` (sync `Session`, structlog kwargs) | exact |
| `app/services/roasters.py` | service | CRUD | same as coffees.py | exact |
| `app/services/flavor_notes.py` | service | CRUD | same as coffees.py | exact |
| `app/services/equipment.py` | service | CRUD | same as coffees.py | exact |
| `app/services/recipes.py` | service | CRUD + duplicate | same as coffees.py — duplicate path is INSERT-from-SELECT pattern | exact |
| `app/services/bags.py` | service | CRUD + file lifecycle | `app/services/credentials.py` (transaction shape) + `app/services/photos.py` for unlink wiring | role-match |
| `app/services/photos.py` | service | file-I/O + transform | (no direct analog — net-new) `app/services/encryption.py` is the structural template for "primitives in a pure module" | role-match |

### Routers

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/routers/coffees.py` | router | request-response (+HTMX fragments) | `app/routers/auth.py` (Form params, templates.TemplateResponse, ValidationError → 200 re-render, RedirectResponse via 303 — but Phase 4 uses 200 fragments per D-01..D-04) | role-match |
| `app/routers/roasters.py` | router | HTMX fragments + datalist | same as coffees.py + `HX-Trigger` header emission for D-15 mini-modal | role-match |
| `app/routers/flavor_notes.py` | router | HTMX fragments + datalist | same as roasters.py | role-match |
| `app/routers/equipment.py` | router | HTMX fragments | same as coffees.py | role-match |
| `app/routers/recipes.py` | router | HTMX fragments + `HX-Redirect` for D-12 duplicate | same as coffees.py + `HX-Redirect` header pattern (net-new, see notes) | role-match |
| `app/routers/bags.py` | router | HTMX fragments + multipart upload | `app/routers/auth.py` for handler shape + FastAPI `File()`/`UploadFile` for the photo POST (net-new) | role-match |
| `app/routers/photos.py` | router | file streaming | `app/routers/admin.py` (require_user-style gate) + FastAPI `FileResponse` (net-new) | role-match |

### Templates

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/templates/pages/coffees.html` | template-page | request-response | `app/templates/pages/setup.html` (extends base, CSRF hidden input, inline error block, Tailwind utilities) | role-match |
| `app/templates/pages/roasters.html` | template-page | same | `app/templates/pages/setup.html` | role-match |
| `app/templates/pages/flavor_notes.html` | template-page | same | `app/templates/pages/setup.html` | role-match |
| `app/templates/pages/equipment.html` | template-page | same | `app/templates/pages/setup.html` | role-match |
| `app/templates/pages/recipes.html` | template-page | same | `app/templates/pages/setup.html` | role-match |
| `app/templates/pages/coffee_detail.html` | template-page | same | `app/templates/pages/setup.html` | role-match |
| `app/templates/fragments/*.html` | template-fragment | same | `app/templates/pages/setup.html` (the form block at lines 8-25 is the row/form-fragment seed) — first fragments in repo, no closer analog | role-match |

### Static JS

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/static/js/photo-upload.js` | static-js (vanilla) | transform | `app/static/js/htmx-listeners.js` (vanilla, defer-loaded, CSP nonce, body-level event listeners) | role-match |
| `app/static/js/alpine-components/recipe-step-builder.js` | alpine-component | event-driven | `app/static/js/alpine-components/__init.js` (pattern reference only — no live components yet) | role-match |
| `app/static/js/alpine-components/mini-modal.js` | alpine-component | event-driven | same as above + reacts to `htmx:afterSwap` and `HX-Trigger` events | role-match |
| `app/static/js/alpine-components/autocomplete.js` | alpine-component | event-driven | same as above | role-match |

### Migrations

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/migrations/versions/p4_shared_catalog.py` | migration | DDL | `app/migrations/versions/0001_initial.py` (single mega-migration: extensions already installed; CITEXT/CheckConstraint columns; `op.bulk_insert` not needed here; `op.create_index` patterns), `app/migrations/versions/p3_api_credentials.py` (CheckConstraint shape, lightweight `sa.table()` if seeding, no model imports) | exact |

### Other

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/events.py` (MODIFY) | config | n/a | `app/events.py` itself | self |
| `app/main.py` (MODIFY — `include_router`) | config | n/a | `app/main.py:211-214` itself | self |
| `app/dependencies/db.py` (MODIFY — add sync `get_session`) | dependency | n/a | `app/dependencies/db.py` itself (async version is the template) | self |

---

## Pattern Assignments — Models

### `app/models/coffee.py` (model, CRUD)

**Analog:** `app/models/user.py` (CITEXT unique pattern) + `app/models/api_credential.py` (CheckConstraint on process/roast_level enums) + `app/models/bag.py` (BigInteger Identity + audit columns).

**Imports + class header (copy from `app/models/user.py:21-33`):**
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Identity, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Coffee(Base):
    """A shared catalog coffee (no user_id — household-shared per CLAUDE.md)."""

    __tablename__ = "coffees"
```

**Identity + CITEXT + audit columns (copy shape from `app/models/user.py:38-52`):**
```python
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False)  # NOT unique — same name OK across roasters
    roaster_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("roasters.id", ondelete="SET NULL"), nullable=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # ... country / process / roast_level / origin / varietal / notes ...
    advertised_flavor_note_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'::bigint[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
```

**CheckConstraint pattern for `process` / `roast_level` (copy from `app/models/api_credential.py:81-86`):**
```python
    __table_args__ = (
        CheckConstraint(
            "process IN ('washed', 'natural', 'honey', 'anaerobic', 'experimental', 'unknown')",
            name="coffees_process_check",
        ),
        CheckConstraint(
            "roast_level IN ('light', 'medium-light', 'medium', 'medium-dark', 'dark', 'unknown')",
            name="coffees_roast_level_check",
        ),
        Index("ix_coffees_roaster_id", "roaster_id"),
        Index("ix_coffees_archived", "archived"),
        # GIN index on the advertised_flavor_note_ids array — added by raw SQL
        # in the migration (autogenerate cannot emit USING GIN).
    )
```

**Translation notes:**
- Same `Mapped[...]` + `mapped_column` + `__table_args__` + `from __future__ import annotations` + docstring-as-decision-record style as every Phase 0–3 model.
- `name` is `CITEXT()` but NOT unique (different roasters can sell same-named coffees). `Roaster.name` and `FlavorNote.name` ARE unique CITEXT — copy `user.py:39` exactly for those.
- `advertised_flavor_note_ids` uses `ARRAY(BigInteger)` — Postgres dialect import. Default `'{}'::bigint[]` (empty array, not NULL — per CONTEXT discretion recommendation).
- text+CHECK over Postgres ENUM per Phase 3 D-01 precedent (verified at `api_credential.py:81-86`).
- GIN index on the array column must be hand-edited into the migration (autogenerate misses `USING GIN`).

---

### `app/models/roaster.py` (model, CRUD)

**Analog:** `app/models/user.py:33-63` (CITEXT unique).

**Excerpt (copy shape from `user.py:38-52`):**
```python
class Roaster(Base):
    """Shared catalog roaster (CAT-01)."""

    __tablename__ = "roasters"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)  # validated as HttpUrl at form layer
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

**Translation notes:** `website` stored as `Text` — `HttpUrl` validation happens only at the Pydantic schema layer (storing as `Text` keeps the DB happy with arbitrary length and avoids SQLAlchemy URL types).

---

### `app/models/flavor_note.py` (model, CRUD)

**Analog:** `app/models/user.py` (CITEXT unique) + `app/models/api_credential.py:81-86` (CheckConstraint on the 9-value category).

**Excerpt:**
```python
class FlavorNote(Base):
    """Shared catalog flavor note (CAT-02)."""

    __tablename__ = "flavor_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('fruit', 'floral', 'sweet', 'chocolate', 'nutty', "
            "'spice', 'savory', 'fermented', 'other')",
            name="flavor_notes_category_check",
        ),
    )
```

---

### `app/models/equipment.py` (model, CRUD)

**Analog:** `app/models/api_credential.py:81-86` (type enum CHECK).

**Excerpt:**
```python
class Equipment(Base):
    """Shared catalog equipment (CAT-05)."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # audit cols ...

    __table_args__ = (
        CheckConstraint(
            "type IN ('brewer', 'grinder', 'kettle', 'scale', 'water_filter', 'other')",
            name="equipment_type_check",
        ),
        Index("ix_equipment_type", "type"),
    )
```

**Translation notes:** `usage_count` denormalized; ships at 0 in Phase 4, incremented by Phase 5 service.

---

### `app/models/recipe.py` (model, CRUD)

**Analog:** `app/migrations/versions/0001_initial.py:165` (`postgresql.JSONB` usage on `ai_recommendations.response_json`) + `app/models/bag.py` audit cols.

**Excerpt:**
```python
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

class Recipe(Base):
    """Shared catalog recipe (CAT-06)."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dose_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    water_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    water_temp_c: Mapped[int] = mapped_column(Integer, nullable=False)
    grind_setting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    steps: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # audit cols ...
```

**Translation notes:** `steps: Mapped[list[dict]]` typed as a list of `{water_grams, time_seconds, label}` dicts; Pydantic enforces per-step shape on submit. `JSONB` (not `JSON`) for indexability later.

---

### `app/models/bag.py` (MODIFY)

**Current state (read from `app/models/bag.py:24-46`):**
```python
class Bag(Base):
    __tablename__ = "bags"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    coffee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # FK deferred to Phase 4
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (Index("ix_bags_coffee_id", "coffee_id"),)
```

**Change summary:**
1. Add `ForeignKey("coffees.id", ondelete="RESTRICT")` to `coffee_id` (planner picks RESTRICT vs SET NULL vs CASCADE — RESTRICT recommended per CONTEXT canonical_refs to prevent destroying bag history if a coffee row is accidentally hard-deleted).
2. Add `photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)` column for CAT-08.
3. Migration (`p4_shared_catalog.py`) carries the actual ALTER TABLE; this file just updates the model declaration.

**Diff excerpt:**
```python
from sqlalchemy import BigInteger, Date, ForeignKey, Identity, Index, Integer, Text
# ...
    coffee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coffees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # ... existing columns ...
    photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
```

---

### `app/models/__init__.py` (MODIFY)

**Current state (read from `app/models/__init__.py:15-33`):**
```python
from app.models.ai_recommendation import AIRecommendation
from app.models.api_credential import ApiCredential
from app.models.app_setting import AppSetting
from app.models.bag import Bag
from app.models.base import Base
from app.models.session import Session
from app.models.user import User
from app.models.wishlist_entry import WishlistEntry

__all__ = [
    "AIRecommendation",
    "ApiCredential",
    "AppSetting",
    "Bag",
    "Base",
    "Session",
    "User",
    "WishlistEntry",
]
```

**Change summary:** Add five new imports + extend `__all__`. Required so Alembic autogenerate sees the new models (file-level comment at `__init__.py:1-11` explains why).

**New additions:**
```python
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster
```

---

## Pattern Assignments — Schemas

### `app/schemas/coffee.py` (schema, request-response)

**Analog:** `app/schemas/auth.py:33-50` — BaseModel + Field constraints; constructed inside the route handler from individual `Form(...)` parameters so `ValidationError` can be caught locally.

**Imports + class shape (copy from `app/schemas/auth.py:28-50`):**
```python
"""Pydantic v2 form schemas for /coffees — SEC-06 universal validation pattern."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoffeeCreate(BaseModel):
    """Coffee form. Validation errors → 200 + form-fragment re-render (D-04)."""

    name: str = Field(..., min_length=1, max_length=200)
    roaster_id: int | None = Field(None, ge=1)
    country: str | None = Field(None, max_length=80)
    process: str = Field(..., pattern=r"^(washed|natural|honey|anaerobic|experimental|unknown)$")
    roast_level: str = Field(..., pattern=r"^(light|medium-light|medium|medium-dark|dark|unknown)$")
    # ... other fields ...
    advertised_flavor_note_ids: list[int] = Field(default_factory=list)
    archived: bool = False


class CoffeeUpdate(CoffeeCreate):
    """Same shape as Create at v1 — keeping the class split lets a future
    Update diverge without churning Create call sites."""


__all__ = ["CoffeeCreate", "CoffeeUpdate"]
```

**Translation notes:**
- Same `Field(...)` constraint syntax already proven in `auth.py:36-49`.
- `ValidationError` is caught at the router layer (analog `routers/auth.py:170-178`); router re-renders the form-fragment template at HTTP 200 (D-04). This is the SEC-06 universal pattern.
- The `process` / `roast_level` regex enforces the same allowed set as the DB CHECK — defense in depth.
- HTML5 `min`/`max`/`pattern` attributes are advisory; Pydantic is authoritative.

---

### `app/schemas/roaster.py` (schema, request-response)

**Analog:** `app/schemas/auth.py`. Adds `HttpUrl` for the website field.

**Excerpt:**
```python
from pydantic import BaseModel, Field, HttpUrl

class RoasterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    location: str | None = Field(None, max_length=200)
    website: HttpUrl | None = None  # Pydantic v2 URL validator
    notes: str = Field("", max_length=4000)
```

**Translation notes:** `HttpUrl | None` is the Pydantic v2 idiom; ensure the field is `None`-defaulted (it's optional per UI-SPEC roaster modal section). Router stores `str(form.website)` in the `Text` DB column.

---

### `app/schemas/flavor_note.py` (schema, request-response)

**Analog:** `app/schemas/auth.py` — pattern-based string validation matches the regex precedent at `auth.py:38`.

**Excerpt:**
```python
class FlavorNoteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(
        ...,
        pattern=r"^(fruit|floral|sweet|chocolate|nutty|spice|savory|fermented|other)$",
    )
```

---

### `app/schemas/equipment.py` (schema, request-response)

**Analog:** `app/schemas/auth.py`.

**Excerpt:**
```python
class EquipmentCreate(BaseModel):
    type: str = Field(..., pattern=r"^(brewer|grinder|kettle|scale|water_filter|other)$")
    brand: str = Field(..., min_length=1, max_length=200)
    model: str = Field(..., min_length=1, max_length=200)
    notes: str = Field("", max_length=4000)
```

---

### `app/schemas/recipe.py` (schema, request-response)

**Analog:** `app/schemas/auth.py` + nested `StepSchema` with numeric range Field constraints (SEC-06 verbatim).

**Excerpt:**
```python
class StepSchema(BaseModel):
    water_grams: int = Field(..., ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)


class RecipeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dose_grams: int = Field(..., ge=1, le=200)
    water_grams: int = Field(..., ge=1, le=3000)
    water_temp_c: int = Field(..., ge=0, le=100)  # SEC-06 explicit numeric range
    grind_setting: str = Field("", max_length=200)
    steps: list[StepSchema] = Field(default_factory=list)
```

**Translation notes:**
- The `steps` field is parsed from a hidden `<input name="steps" value="[...]">` (JSON-stringified Alpine array per D-09) — router does `json.loads(steps_str)` before passing to the schema, OR uses `model_validate_json()` directly.
- Validation error inside any step → re-render form fragment with the offending step highlighted (`ring-1 ring-red-300` per UI-SPEC).

---

### `app/schemas/bag.py` (schema, request-response)

**Analog:** `app/schemas/auth.py`.

**Excerpt:**
```python
class BagCreate(BaseModel):
    coffee_id: int = Field(..., ge=1)
    roast_date: date | None = None
    weight_grams: int | None = Field(None, ge=1, le=10000)
    opened_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str = Field("", max_length=4000)
```

---

## Pattern Assignments — Services

### `app/services/coffees.py` (service, CRUD)

**Analog:** `app/services/credentials.py:166-263` (`set_provider_credential` — kwargs API, sync `Session`, `select()` + `update()`, single commit, audit-event emit).

**Imports + module shape (copy from `app/services/credentials.py:50-70`):**
```python
"""Coffees CRUD + audit-event emission. Phase 4 catalog service.

Sync Session per Phase 3 D-07; kwargs API per Phase 1 D-14 / Phase 3 D-08.
"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import CATALOG_COFFEE_ARCHIVED, CATALOG_COFFEE_CREATED, CATALOG_COFFEE_UPDATED
from app.models.coffee import Coffee

log = structlog.get_logger(__name__)
```

**CRUD + audit emit shape (copy pattern from `credentials.py:166-263`):**
```python
def create_coffee(
    db: Session,
    *,
    name: str,
    roaster_id: int | None,
    process: str,
    roast_level: str,
    advertised_flavor_note_ids: list[int],
    # ... other fields ...
    by_user_id: int,
) -> Coffee:
    """INSERT a Coffee row, commit, emit catalog.coffee.created."""
    coffee = Coffee(
        name=name,
        roaster_id=roaster_id,
        process=process,
        roast_level=roast_level,
        advertised_flavor_note_ids=advertised_flavor_note_ids,
    )
    db.add(coffee)
    db.flush()  # populate coffee.id for audit-event emit
    db.commit()
    log.info(
        CATALOG_COFFEE_CREATED,
        coffee_id=coffee.id,
        roaster_id=roaster_id,
        user_id=by_user_id,
    )
    return coffee


def list_coffees(
    db: Session,
    *,
    roaster_id: int | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
) -> list[Coffee]:
    """Filtered list. Each filter dim → optional WHERE clause."""
    stmt = select(Coffee)
    if not archived:
        stmt = stmt.where(Coffee.archived.is_(False))
    if roaster_id is not None:
        stmt = stmt.where(Coffee.roaster_id == roaster_id)
    # ...
    return list(db.execute(stmt.order_by(Coffee.name)).scalars())
```

**Translation notes:**
- Same kwargs-with-leading-`*` signature shape as `credentials.set_provider_credential` (lines 167-173). This is the Phase 1 D-14 + Phase 3 D-08 convention.
- `by_user_id` is the audit-trail user id; `user_id` is the structlog kwarg name (Phase 1 D-14 taxonomy alignment — see comment at `credentials.py:196-197`).
- Soft-delete: `archive_coffee` runs `UPDATE coffees SET archived=true WHERE id=...` (not `DELETE`). Pattern from `credentials.set_provider_enabled:266-298`.
- The `update()` + `values()` pattern with explicit `updated_at=func.now()` is verbatim from `credentials.py:219-230` (Core update bypasses ORM `onupdate` hooks; explicit timestamp needed).

---

### `app/services/roasters.py` (service, CRUD)

**Analog:** same as `coffees.py`. Add a `find_or_search(query: str)` helper for the D-13 autocomplete endpoint.

**Autocomplete helper excerpt:**
```python
def search_by_prefix(db: Session, query: str, limit: int = 50) -> list[Roaster]:
    """Case-insensitive prefix match for D-13 autocomplete."""
    stmt = (
        select(Roaster)
        .where(Roaster.archived.is_(False))
        .where(Roaster.name.ilike(f"{query}%"))  # CITEXT makes this case-insensitive
        .order_by(Roaster.name)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())
```

**Translation notes:** `CITEXT()` on `Roaster.name` (matches `User.username` pattern at `user.py:39`) means `ilike` and `==` are case-insensitive natively. Avoid `func.lower()` wrapper.

---

### `app/services/flavor_notes.py` (service, CRUD)

**Analog:** same as `roasters.py`. Same `search_by_prefix` helper.

---

### `app/services/equipment.py` (service, CRUD)

**Analog:** same as `coffees.py`. Soft-delete only (CONTEXT recommendation: archive-only from day one even before Phase 5 sessions exist).

---

### `app/services/recipes.py` (service, CRUD + duplicate)

**Analog:** same as `coffees.py`. Adds a `duplicate_recipe(db, source_id, by_user_id) -> Recipe` function.

**Duplicate excerpt:**
```python
def duplicate_recipe(db: Session, *, source_id: int, by_user_id: int) -> Recipe:
    """D-12: INSERT a deep copy with name='{original} (copy)' + fresh timestamps."""
    src = db.execute(select(Recipe).where(Recipe.id == source_id)).scalar_one()
    copy = Recipe(
        name=f"{src.name} (copy)",
        dose_grams=src.dose_grams,
        water_grams=src.water_grams,
        water_temp_c=src.water_temp_c,
        grind_setting=src.grind_setting,
        steps=list(src.steps),  # deep copy the JSONB list
        archived=False,
    )
    db.add(copy)
    db.flush()
    db.commit()
    log.info(CATALOG_RECIPE_CREATED, recipe_id=copy.id, source_id=source_id, user_id=by_user_id)
    return copy
```

---

### `app/services/bags.py` (service, CRUD + photo lifecycle)

**Analog:** `app/services/credentials.py` for the transaction shape, calls into `app.services.photos` for the magic-byte/Pillow pipeline.

**Translation notes:**
- `attach_photo(db, bag_id, file_bytes, by_user_id)` — calls `photos.process_and_save(file_bytes)` → returns `uuid_filename`, then `UPDATE bags SET photo_filename=:n WHERE id=:b`.
- `replace_photo` — write new, fsync, update DB, then `photos.unlink_safe(old_filename)`. Order: never delete-then-write (per D-07).
- Emit `catalog.bag.photo_uploaded` / `catalog.bag.photo_deleted` per D-14 taxonomy.

---

### `app/services/photos.py` (service, file-I/O + transform)

**Analog:** `app/services/encryption.py` is the structural template for "pure primitives module that other services compose." Pillow API is net-new in the repo (no analog).

**Module skeleton:**
```python
"""Photo pipeline: magic-byte verify → Pillow decode + re-encode → EXIF strip → resize → thumb.

SEC-07 + SEC-4 (polyglot defense). Synchronous; no DB writes (bags.py owns those).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image

from app.config import settings

log = structlog.get_logger(__name__)

PHOTOS_DIR = Path("/app/data/photos")
MAX_BYTES = 5 * 1024 * 1024  # 5 MiB; mirrors app_settings.photo_max_bytes seed
ALLOWED_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # plus check "WEBP" at offset 8
}

class PhotoRejected(Exception):
    """Raised on size, format, or decode failure. Router translates to 200 + form-fragment."""


def process_and_save(blob: bytes) -> str:
    """Magic-byte → Pillow decode + verify → EXIF strip → resize ≤1600px wide → 400px thumb.

    Returns the new UUID filename (without extension). Raises PhotoRejected on any failure.
    """
    if len(blob) > MAX_BYTES:
        raise PhotoRejected("Photo too large (max 5MB).")
    if not _verify_magic_bytes(blob):
        raise PhotoRejected("We couldn't read this image. Try a JPEG, PNG, or WebP.")
    try:
        img = Image.open(BytesIO(blob))
        img.verify()  # separate decode pass per SEC-7
        img = Image.open(BytesIO(blob))  # re-open after verify; verify() consumes
    except Exception as exc:
        log.warning("photo.decode_failed", error_class=type(exc).__name__)
        raise PhotoRejected("We couldn't read this image. Try a JPEG, PNG, or WebP.") from exc
    # EXIF strip — re-encode without info
    img.thumbnail((1600, 1600))
    name = uuid.uuid4().hex
    img.convert("RGB").save(PHOTOS_DIR / f"{name}.jpg", "JPEG", quality=85)
    img.thumbnail((400, 400))
    img.convert("RGB").save(PHOTOS_DIR / f"{name}-thumb.jpg", "JPEG", quality=85)
    return name


def unlink_safe(name: str | None) -> None:
    """Remove main + thumb. Idempotent — missing files are fine (logged at debug)."""
    if not name:
        return
    for path in (PHOTOS_DIR / f"{name}.jpg", PHOTOS_DIR / f"{name}-thumb.jpg"):
        path.unlink(missing_ok=True)


def sweep_orphans(db_filenames: set[str]) -> int:
    """D-07 orphan sweep: filesystem entries not present in bags.photo_filename."""
    removed = 0
    for entry in PHOTOS_DIR.glob("*.jpg"):
        base = entry.stem.removesuffix("-thumb")
        if base not in db_filenames:
            entry.unlink(missing_ok=True)
            removed += 1
    log.info("catalog.photo.orphan_swept", removed_count=removed)
    return removed
```

**Translation notes:**
- `PhotoRejected` is the named exception the router catches and translates into 200 + form-fragment re-render (D-04). Compare to `auth.py:170-178` catching `ValidationError`.
- Magic-byte check **before** Pillow decode (CONTEXT specifics step 1-2; SEC-4 polyglot defense). Order matters: Pillow happily decodes 1GB of structured nonsense.
- Re-encode pass strips trailing polyglot bytes (`img.convert("RGB").save(..., "JPEG")` always produces a clean JPEG container).
- `sweep_orphans` is the standalone function from CONTEXT D-07; APScheduler registration waits for Phase 8. Phase 4 ships the function + a callable management command path.

---

## Pattern Assignments — Routers

### `app/routers/coffees.py` (router, HTMX request-response)

**Analog:** `app/routers/auth.py:114-211` for handler shape (Form params, `request: Request`, `templates.TemplateResponse`, `status_code=200` re-render on validation failure). Departs from `auth.py` only in: (a) sync `Session` instead of `AsyncSession`, (b) returns HTMX fragments instead of 303 redirects (D-01 vs D-05).

**Module header + imports (adapt from `routers/auth.py:54-86`):**
```python
"""Coffees CRUD router — HTMX fragments + Pydantic-v2 form validation (SEC-06).

D-01..D-04: list page + inline-expand form fragments; ValidationError → 200 + form-fragment re-render.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session  # NEW sync dep — see planner action below
from app.models.user import User
from app.schemas.coffee import CoffeeCreate
from app.services import coffees as coffees_service
from app.templates_setup import templates

log = structlog.get_logger()
router = APIRouter(prefix="/coffees")
```

**List page + filter handler (analog: `auth.py:114-131`):**
```python
@router.get("", response_class=HTMLResponse)
def list_coffees(
    request: Request,
    roaster_id: int | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI Form 1 idiom
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    coffees = coffees_service.list_coffees(
        db, roaster_id=roaster_id, country=country, process=process, archived=archived,
    )
    # Full page on first hit; list-only fragment for HX-Request (hx-push-url replay)
    template = (
        "fragments/coffee_list.html"
        if request.headers.get("HX-Request") == "true"
        else "pages/coffees.html"
    )
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"coffees": coffees, "filters": {...}},
    )
```

**Form POST handler with ValidationError → 200 (verbatim pattern from `auth.py:170-178`):**
```python
@router.post("", response_class=HTMLResponse)
def create_coffee(
    request: Request,
    name: str = Form(...),
    roaster_id: int | None = Form(None),
    process: str = Form(...),
    # ... other Form() params ...
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    try:
        form = CoffeeCreate(name=name, roaster_id=roaster_id, process=process, ...)
    except ValidationError as exc:
        # D-04: 200 + form fragment re-render with errors + submitted values preserved
        return templates.TemplateResponse(
            request=request,
            name="fragments/coffee_form.html",
            context={
                "values": {"name": name, "roaster_id": roaster_id, ...},
                "errors": _errors_by_field(exc),
            },
            status_code=200,
        )
    coffee = coffees_service.create_coffee(db, **form.model_dump(), by_user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_row.html",
        context={"coffee": coffee},
    )
```

**Translation notes:**
- The `try / except ValidationError → TemplateResponse(..., status_code=200)` shape is verbatim from `auth.py:170-178` — copy it. The only difference is the template name (form fragment vs page) and the context carries `errors` keyed by field for inline rendering (UI-SPEC §"Form Validation Errors").
- `_errors_by_field(exc)` helper: `{e["loc"][-1]: e["msg"] for e in exc.errors()}` — gives the template `{ "name": "must be at least 1 char", ... }`.
- Note: existing auth router uses `AsyncSession`; **Phase 4 uses sync `Session` per Phase 3 D-07**. This requires a new dep `app/dependencies/db.py::get_session()` that mirrors `get_async_session` but yields a `SessionLocal()` context-manager — see the existing async version at `dependencies/db.py:32-45`.
- `Depends(require_user)` from `dependencies/auth.py:33-45` (already exists; verified) — `require_user` raises HTTP 401 if no session.

---

### `app/routers/roasters.py` (router, HTMX + datalist + HX-Trigger for D-15)

**Analog:** `app/routers/coffees.py` (above) for CRUD shape. Adds an autocomplete endpoint + an `HX-Trigger` response header for the D-15 mini-modal flow.

**HX-Trigger emit pattern for D-15 (NEW — no analog in repo):**
```python
import json

@router.post("", response_class=HTMLResponse)
def create_roaster(
    request: Request,
    name: str = Form(...),
    as_modal: bool = Form(False),
    # ...
) -> Response:
    # ... validate + create as in coffees.py ...
    roaster = roasters_service.create_roaster(db, **form.model_dump(), by_user_id=user.id)
    response = templates.TemplateResponse(
        request=request,
        name="fragments/empty.html" if as_modal else "fragments/roaster_row.html",
        context={"roaster": roaster},
    )
    if as_modal:
        # D-15: parent form's Alpine listener consumes this event to pre-select
        response.headers["HX-Trigger"] = json.dumps({
            "roaster-created": {"roaster_id": roaster.id, "name": roaster.name},
        })
    return response
```

**Autocomplete endpoint (`/roasters/list`):**
```python
@router.get("/list", response_class=HTMLResponse)
def roasters_list(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    matches = roasters_service.search_by_prefix(db, q) if len(q) >= 2 else []
    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={"matches": matches, "query": q, "entity": "roaster"},
    )
```

**Translation notes:**
- `HX-Trigger` is a JSON-string-valued response header that HTMX dispatches as a CustomEvent on the client. The Alpine listener pre-selects the new roaster in the parent coffee form (D-16). This is **net-new** in the repo — no analog; it's a documented HTMX 2.x feature listed in CONTEXT canonical_refs.
- The autocomplete endpoint is `require_user`-gated (same household-shared invariant as the CRUD).
- For the D-13 HX-4 mitigation: the **client-side** template attribute sets `hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"` — that's a template concern, not router code.

---

### `app/routers/flavor_notes.py` (router)

**Analog:** same as `roasters.py`. Endpoint is `/flavor-notes/datalist` (path uses hyphen, FastAPI router prefix `/flavor-notes`).

---

### `app/routers/equipment.py` (router)

**Analog:** `app/routers/coffees.py` minus the autocomplete endpoint (equipment is not autocompleted from coffee form).

---

### `app/routers/recipes.py` (router, HTMX + HX-Redirect for D-12)

**Analog:** `app/routers/coffees.py` + adds the duplicate endpoint with `HX-Redirect` response header.

**Duplicate endpoint with HX-Redirect (NEW):**
```python
from fastapi import Response

@router.post("/{recipe_id}/duplicate")
def duplicate(
    recipe_id: int,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    copy = recipes_service.duplicate_recipe(db, source_id=recipe_id, by_user_id=user.id)
    # D-12: HTMX redirect to the new recipe's edit form
    return Response(status_code=200, headers={"HX-Redirect": f"/recipes/{copy.id}/edit"})
```

**Translation notes:** `HX-Redirect` is a response header that HTMX consumes to perform a full-page client-side navigation. The empty response body + 200 status are correct (HTMX ignores the body when `HX-Redirect` is set). Reserved for cross-page navigations per CONTEXT specifics.

---

### `app/routers/bags.py` (router, multipart upload nested under coffees)

**Analog:** `app/routers/coffees.py` for CRUD shape + FastAPI `File()` + `UploadFile` for the photo POST (net-new in repo).

**Photo POST excerpt:**
```python
from fastapi import File, UploadFile
from app.services import bags as bags_service
from app.services.photos import PhotoRejected

@router.post("/{bag_id}/photo", response_class=HTMLResponse)
async def upload_photo(
    bag_id: int,
    request: Request,
    photo: UploadFile = File(...),
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    blob = await photo.read()  # 5MB cap enforced inside process_and_save
    try:
        bag = bags_service.attach_or_replace_photo(db, bag_id=bag_id, blob=blob, by_user_id=user.id)
    except PhotoRejected as exc:
        # D-04 / SEC-07: 200 + form-fragment re-render with the rejection message
        return templates.TemplateResponse(
            request=request,
            name="fragments/photo_upload_zone.html",
            context={"bag_id": bag_id, "error": str(exc)},
            status_code=200,
        )
    return templates.TemplateResponse(
        request=request,
        name="fragments/photo_upload_zone.html",
        context={"bag": bag},
    )
```

**Translation notes:**
- `async def` here because `UploadFile.read()` is async (Starlette wraps the temp-file read).
- Service call is sync — that's fine inside an async handler if the sync work is fast and IO-bound; alternatively run it via `await asyncio.to_thread(bags_service.attach_or_replace_photo, ...)`. Phase 4 planner picks; recommendation: stay simple, direct call.
- Synchronous `unlink` on replace is per D-07; lives inside `bags_service.attach_or_replace_photo` (write-new-then-delete-old order).

---

### `app/routers/photos.py` (router, file streaming with auth gate)

**Analog:** `app/routers/admin.py` for the require_user-style gate + FastAPI `FileResponse` (net-new — auth.py uses `RedirectResponse`/`HTMLResponse`, no `FileResponse` in repo yet).

**Excerpt:**
```python
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.dependencies.auth import require_user
from app.models.user import User
from app.services.photos import PHOTOS_DIR

router = APIRouter(prefix="/photos")


@router.get("/{name}")
def serve_photo(
    name: str,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008 — D-06: authenticated session required
) -> FileResponse:
    """D-06: auth-gated photo serve. Anonymous (no session) → 401 from require_user;
    but per CONTEXT D-06 we want anonymous → 404 (don't leak existence).

    Translation: catch the 401 at this layer by reading request.state.user directly
    instead of using require_user — or wrap require_user and translate.
    """
    # Per D-06: anonymous returns 404, not 403/401.
    if getattr(request.state, "user", None) is None:
        raise HTTPException(status_code=404)
    # Validate filename shape (uuid4 hex + optional -thumb + .jpg/.png/.webp).
    safe = _validate_photo_name(name)  # planner helper
    if safe is None:
        raise HTTPException(status_code=404)
    path = PHOTOS_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type=_explicit_media_type(safe),  # NEVER sniffed
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
```

**Translation notes:**
- D-06 wants **404 for anonymous, not 401/403** — so do NOT use `Depends(require_user)` directly (it 401s). Instead read `request.state.user` and translate `None` → 404.
- `media_type` is **explicit**, never sniffed. Header dict matches CONTEXT D-06 verbatim.
- Filename validation: regex-match `^[0-9a-f]{32}(-thumb)?\.(jpg|png|webp)$` to defeat path traversal. Reject anything else with 404.
- **NOT a `StaticFiles` mount** — main.py docstring at line 55-57 explicitly forbids it.

---

## Pattern Assignments — Templates

### Pages (`app/templates/pages/*.html`)

**Analog for ALL five list pages + coffee_detail:** `app/templates/pages/setup.html` (lines 1-27 — minimal but encodes every Phase 4 convention).

**Excerpt (verbatim from `pages/setup.html:1-27`):**
```jinja
{% extends "base.html" %}
{% block page_title %}Setup{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">First-time setup</h1>
    <p class="mt-2 text-sm">This creates the household admin account.</p>
    {% if error %}<p class="mt-4 text-red-700">{{ error }}</p>{% endif %}
    <form method="post" action="/setup" class="mt-6 flex flex-col gap-4">
      {# D-15: CSRFFormFieldShim hoists this field into the X-CSRF-Token header. #}
      <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
      <label class="flex flex-col">Username
        <input name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_\-]+"
               class="rounded border px-2 py-1">
      </label>
      ...
      <button type="submit" class="mt-2 self-start rounded bg-espresso-900 px-4 py-2 text-cream-50">
        Create admin
      </button>
    </form>
  </main>
{% endblock %}
```

**Translation notes (apply to every Phase 4 page):**
- Same `{% extends "base.html" %}` + `{% block page_title %}` + `{% block content %}` skeleton.
- Same `<main class="mx-auto max-w-prose px-6 py-12">` outer container (UI-SPEC pages use `max-w-prose` for narrow forms and wider containers for list tables — planner adjusts per UI-SPEC).
- The `<h1 class="text-2xl font-semibold">` heading style is verbatim from UI-SPEC typography lock.
- **CSRF hidden input is verbatim** from `setup.html:10` — every state-changing form copies this exact line. Phase 2 D-15 CSRFFormFieldShim handles the rest.
- Error block `{% if error %}<p class="mt-4 text-red-700">...</p>{% endif %}` extends in Phase 4 to per-field errors keyed under `errors.<field>` (UI-SPEC §"Form Validation Errors") but the form-level banner stays this shape.
- **UI-SPEC overrides one button color**: `bg-espresso-900` (setup.html:22) stays as-is for auth surfaces, but Phase 4 catalog primary CTAs use `bg-espresso-700` per UI-SPEC Q1 lock.
- Phase 4 introduces htmx attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`, `hx-push-url`, `hx-trigger`, `hx-sync`, `hx-confirm`, `hx-swap-oob`) — these are NEW in Phase 4 templates (no existing analog). Reference: `base.html:14-18` already loads HTMX 2.0.10 + listener config; the listener at `app/static/js/htmx-listeners.js:34-39` automatically injects the CSRF header for HTMX requests.

### Fragments (`app/templates/fragments/*.html`)

**Analog:** the `<form>...</form>` block of `pages/setup.html:8-25` is the seed for `coffee_form.html` and the other form fragments. **No previous fragments exist in the repo** — Phase 4 establishes the convention.

**Convention rules from Phase 1 D-12 + CLAUDE.md:**
- No `{% extends %}` — fragments render bare HTML.
- Root element is the swap target (e.g., `<div id="coffee-row-{{ coffee.id }}">`).
- No `|safe` on user content (autoescape ON; enforced by Phase 1 grep test per CONTEXT canonical_refs).
- No inline `hx-on:*` event handlers (CSP-strict; enforced by Phase 1 grep test).
- 2-space indent, snake_case template variables.

**Match-highlighting in `autocomplete_list.html` (server-side; keeps autoescape integrity):**
```jinja
{# Match highlight: split on the query, wrap with <strong>. Both halves are
   autoescaped because we use Jinja's normal expression output. #}
{% for row in matches %}
  <li role="option" class="block w-full text-left px-3 py-2 text-base hover:bg-cream-100 cursor-pointer min-h-[44px]">
    {% set lower = row.name|lower %}
    {% set q_lower = query|lower %}
    {% if q_lower in lower %}
      {% set idx = lower.index(q_lower) %}
      {{ row.name[:idx] }}<strong class="font-semibold">{{ row.name[idx:idx + query|length] }}</strong>{{ row.name[idx + query|length:] }}
    {% else %}
      {{ row.name }}
    {% endif %}
  </li>
{% endfor %}
```

**Translation notes:** The three halves are each separately autoescaped — `<strong>` is the only raw HTML and it's a fixed template literal, not user input. This is the safe match-highlight pattern UI-SPEC calls out (no `|safe` needed).

---

## Pattern Assignments — Static JS

### `app/static/js/photo-upload.js` (vanilla)

**Analog:** `app/static/js/htmx-listeners.js` (lines 1-46 — vanilla, defer-loaded, body-level event listeners, no module system, no npm).

**Conventions to copy:**
- Top-of-file comment block explaining the file's role + how it's loaded (htmx-listeners.js:1-16).
- `document.body.addEventListener(...)` pattern (htmx-listeners.js:34) for hooking the form-submit / file-input-change events.
- No build step — file is served as-is from `/static/js/`.
- Loaded via `<script defer src="/static/js/photo-upload.js" nonce="{{ csp_nonce(request) }}"></script>` in pages that need it (bag form fragment). The nonce is from `app/templates_setup.py::csp_nonce`.

**Skeleton:**
```javascript
// app/static/js/photo-upload.js
//
// D-05: client-side Canvas downscale before POST. Reads EXIF orientation,
// resizes to max edge 2000px, re-encodes JPEG quality 0.85, then submits
// the smaller blob through the form.
//
// Loaded after htmx-listeners.js (defer) on bag form pages only.
// Server STILL re-encodes (SEC-4) — this is a UX/bandwidth optimization,
// not a security boundary.

document.body.addEventListener('change', async (evt) => {
  if (!evt.target.matches('input[type="file"][data-photo-upload]')) return;
  // ... read file, draw to canvas, resize, replace file in DataTransfer ...
});
```

---

### `app/static/js/alpine-components/recipe-step-builder.js` (alpine-component)

**Analog:** `app/static/js/alpine-components/__init.js:33-49` (pattern reference; no live components yet — Phase 4 establishes the first ones).

**Convention to copy verbatim:**
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('recipeStepBuilder', () => ({
    steps: [],
    init() {
      // Read initial steps from a JSON-attribute on the root element
      this.steps = JSON.parse(this.$root.dataset.initialSteps || '[]');
    },
    get totalWater() { return this.steps.reduce((s, x) => s + x.water_grams, 0); },
    get totalSeconds() { return this.steps.length ? this.steps[this.steps.length - 1].time_seconds : 0; },
    addStep() {
      const prev = this.steps[this.steps.length - 1] || { water_grams: 0, time_seconds: 0 };
      this.steps.push({
        water_grams: prev.water_grams + 50,
        time_seconds: prev.time_seconds + 45,
        label: '',
      });
    },
    removeStep(i) { this.steps.splice(i, 1); },
    moveUp(i) { if (i > 0) [this.steps[i-1], this.steps[i]] = [this.steps[i], this.steps[i-1]]; },
    moveDown(i) { if (i < this.steps.length - 1) [this.steps[i+1], this.steps[i]] = [this.steps[i], this.steps[i+1]]; },
    serialize() { return JSON.stringify(this.steps); },
  }));
});
```

**Translation notes (CSP-strict per Phase 1 D-01 + __init.js comment lines 13-49):**
- Templates use `x-data="recipeStepBuilder"` (string reference to registered factory) — **never** inline object literals like `x-data="{ steps: [] }"`.
- Two-way binding under CSP build: use `:value="text" @input="setText($el.value)"` — `x-model` is unavailable under the CSP build (per `__init.js:42-49`).
- `base.html` already loads Alpine 3.14.9 CSP build at line 14. Phase 4 adds `<script defer src="/static/js/alpine-components/recipe-step-builder.js" nonce="..."></script>` to pages that need it (or to `base.html` if the components are loaded globally).
- The script tag must load **before** the `@alpinejs/csp` CDN script — per `__init.js:27` comment, the registrations must be present at Alpine boot time.

---

### `app/static/js/alpine-components/mini-modal.js` (alpine-component)

**Analog:** `__init.js:33-49` + new `htmx:afterSwap` listener (HTMX event dispatch is the established pattern from `htmx-listeners.js:34`).

**Skeleton:**
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('miniModal', () => ({
    open: false,
    dirty: false,
    show() { this.open = true; this.dirty = false; },
    close() {
      if (this.dirty && !confirm('Discard unsaved changes?')) return;
      this.open = false;
    },
    onEscape(e) { if (e.key === 'Escape') this.close(); },
  }));
});

// HX-Trigger consumer for D-16 pre-select flow:
document.body.addEventListener('roaster-created', (evt) => {
  // evt.detail = { roaster_id, name } from the HX-Trigger response header
  const target = document.querySelector('[data-roaster-target]');
  if (target) {
    target.querySelector('input[name="roaster_id"]').value = evt.detail.roaster_id;
    target.querySelector('[data-roaster-label]').textContent = evt.detail.name;
  }
});
```

---

### `app/static/js/alpine-components/autocomplete.js` (alpine-component)

**Analog:** same as above. Owns keyboard navigation (arrow up/down, Enter, Escape) per UI-SPEC.

---

## Pattern Assignment — Migration

### `app/migrations/versions/p4_shared_catalog.py` (migration, DDL)

**Analog:** `app/migrations/versions/0001_initial.py` (the full mega-migration; lines 39-379) for the overall structure + `app/migrations/versions/p3_api_credentials.py:48-141` for the CheckConstraint shape + `down_revision` chain.

**Revision header (copy from `p3_api_credentials.py:48-52`):**
```python
revision: str = "p4_shared_catalog"
down_revision: str | Sequence[str] | None = "p3_api_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**Table creation (copy patterns from `0001_initial.py:64-94` for CITEXT + partial unique index; `0001_initial.py:99-121` for the `bags` shape; `p3_api_credentials.py:87-91` for the CheckConstraint):**
```python
def upgrade() -> None:
    # ---- roasters ----
    op.create_table(
        "roasters",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roasters_archived", "roasters", ["archived"])

    # ---- flavor_notes (with CheckConstraint on category) ----
    op.create_table(
        "flavor_notes",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('fruit', 'floral', 'sweet', 'chocolate', 'nutty', "
            "'spice', 'savory', 'fermented', 'other')",
            name="flavor_notes_category_check",
        ),
    )

    # ---- coffees (with ARRAY column + GIN index via raw SQL) ----
    op.create_table(
        "coffees",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "roaster_id",
            sa.BigInteger,
            sa.ForeignKey("roasters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # ... country / process / roast_level / origin / varietal / notes ...
        sa.Column(
            "advertised_flavor_note_ids",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "process IN ('washed', 'natural', 'honey', 'anaerobic', 'experimental', 'unknown')",
            name="coffees_process_check",
        ),
        sa.CheckConstraint(
            "roast_level IN ('light', 'medium-light', 'medium', 'medium-dark', 'dark', 'unknown')",
            name="coffees_roast_level_check",
        ),
    )
    op.create_index("ix_coffees_roaster_id", "coffees", ["roaster_id"])
    op.create_index("ix_coffees_archived", "coffees", ["archived"])
    # GIN index on the array column — raw SQL because autogenerate cannot emit USING GIN.
    op.execute(
        "CREATE INDEX ix_coffees_advertised_flavor_note_ids "
        "ON coffees USING GIN (advertised_flavor_note_ids)"
    )

    # ---- equipment (with CheckConstraint on type) ----
    # ... same shape ...

    # ---- recipes (with JSONB steps column) ----
    op.create_table(
        "recipes",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        # ... numeric brew params ...
        sa.Column("steps", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        # ... audit cols ...
    )

    # ---- bags: ADD photo_filename column + FK constraint ----
    op.add_column("bags", sa.Column("photo_filename", sa.Text, nullable=True))
    op.create_foreign_key(
        "fk_bags_coffee_id",
        "bags",
        "coffees",
        ["coffee_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Reverse order: drop FK + column from bags, then drop new tables in reverse creation order.
    op.drop_constraint("fk_bags_coffee_id", "bags", type_="foreignkey")
    op.drop_column("bags", "photo_filename")
    op.drop_table("recipes")
    op.drop_table("equipment")
    op.execute("DROP INDEX IF EXISTS ix_coffees_advertised_flavor_note_ids")
    op.drop_index("ix_coffees_archived", table_name="coffees")
    op.drop_index("ix_coffees_roaster_id", table_name="coffees")
    op.drop_table("coffees")
    op.drop_table("flavor_notes")
    op.drop_index("ix_roasters_archived", table_name="roasters")
    op.drop_table("roasters")
```

**Translation notes:**
- Extensions (citext, pg_trgm, unaccent) already installed in `0001_initial.py:59-61` — Phase 4 migration does NOT re-create them.
- **Single migration per Phase 0 D-02** ("one migration per logical change") — five tables + bag FK + bag column in one file.
- GIN index on the array column requires raw `op.execute("CREATE INDEX ... USING GIN ...")` — autogenerate misses this (called out in research §"Alembic Autogenerate Quirks").
- Alembic-safe convention: migration body MUST NOT import from `app.models` (verbatim from `p3_api_credentials.py:29-32`). Use lightweight `sa.table()` if seeding (not needed in Phase 4 — no seed rows).
- `down_revision = "p3_api_credentials"` (verified — that's the current head per file order in `migrations/versions/`).
- Bag FK `ondelete="RESTRICT"` per CONTEXT canonical_refs recommendation.

---

## Pattern Assignment — Events

### `app/events.py` (MODIFY)

**Analog:** `app/events.py` itself (lines 39-75) — Phase 1 D-14 taxonomy already established three sections (`auth.*`, `admin.*`, `encryption.*`, operational). Phase 4 adds a `catalog.*` section.

**Diff excerpt to add:**
```python
# --- catalog.* (Phase 4) --------------------------------------------------
# Emitted by app.services.{coffees,roasters,flavor_notes,equipment,recipes,bags,photos}
# at every write path per Phase 1 D-14. Field shape: entity-specific id + user_id.
CATALOG_COFFEE_CREATED = "catalog.coffee.created"
CATALOG_COFFEE_UPDATED = "catalog.coffee.updated"
CATALOG_COFFEE_ARCHIVED = "catalog.coffee.archived"
CATALOG_ROASTER_CREATED = "catalog.roaster.created"
CATALOG_ROASTER_UPDATED = "catalog.roaster.updated"
CATALOG_ROASTER_ARCHIVED = "catalog.roaster.archived"
CATALOG_FLAVOR_NOTE_CREATED = "catalog.flavor_note.created"
CATALOG_FLAVOR_NOTE_UPDATED = "catalog.flavor_note.updated"
CATALOG_FLAVOR_NOTE_ARCHIVED = "catalog.flavor_note.archived"
CATALOG_EQUIPMENT_CREATED = "catalog.equipment.created"
CATALOG_EQUIPMENT_UPDATED = "catalog.equipment.updated"
CATALOG_EQUIPMENT_ARCHIVED = "catalog.equipment.archived"
CATALOG_RECIPE_CREATED = "catalog.recipe.created"
CATALOG_RECIPE_UPDATED = "catalog.recipe.updated"
CATALOG_RECIPE_ARCHIVED = "catalog.recipe.archived"
CATALOG_RECIPE_DUPLICATED = "catalog.recipe.duplicated"
CATALOG_BAG_CREATED = "catalog.bag.created"
CATALOG_BAG_UPDATED = "catalog.bag.updated"
CATALOG_BAG_ARCHIVED = "catalog.bag.archived"
CATALOG_BAG_PHOTO_UPLOADED = "catalog.bag.photo_uploaded"
CATALOG_BAG_PHOTO_DELETED = "catalog.bag.photo_deleted"
CATALOG_PHOTO_ORPHAN_SWEPT = "catalog.photo.orphan_swept"
```

**Add to `__all__` (alphabetical, matches existing convention at `events.py:78-94`).**

---

## Pattern Assignment — `app/main.py` (MODIFY)

**Analog:** `app/main.py:211-214` itself — router registration block.

**Current state:**
```python
app.include_router(csp_report_router.router)
app.include_router(auth_router.router)
app.include_router(debug_router.router)
app.include_router(admin_router.router)
```

**Change summary:** Add seven new router imports + seven `include_router` calls.

**New additions (matching existing import + call style from `main.py:84-87` + `main.py:211-214`):**
```python
from app.routers import bags as bags_router
from app.routers import coffees as coffees_router
from app.routers import equipment as equipment_router
from app.routers import flavor_notes as flavor_notes_router
from app.routers import photos as photos_router
from app.routers import recipes as recipes_router
from app.routers import roasters as roasters_router

# ... later ...
app.include_router(coffees_router.router)
app.include_router(roasters_router.router)
app.include_router(flavor_notes_router.router)
app.include_router(equipment_router.router)
app.include_router(recipes_router.router)
app.include_router(bags_router.router)
app.include_router(photos_router.router)
```

**Translation notes:** No middleware changes (per CONTEXT canonical_refs). Middleware order is locked by Phase 1 D-17 + Phase 2 D-15.

---

## Pattern Assignment — `app/dependencies/db.py` (MODIFY — add sync `get_session`)

**Analog:** `app/dependencies/db.py:32-45` (existing `get_async_session` is the template).

**Change summary:** Add a sync sibling `get_session` that yields a `SessionLocal()` context-manager-bound `Session`. Phase 4 catalog routes consume this; auth routes continue to use the async version.

**New addition:**
```python
from collections.abc import Iterator
from sqlalchemy.orm import Session
from app.db import SessionLocal


def get_session() -> Iterator[Session]:
    """Yield a fresh sync :class:`Session` for the lifetime of the request.

    Phase 4+ catalog routes consume this dep; Phase 2 auth routes use
    :func:`get_async_session` instead. Sync per Phase 3 D-07 — the catalog
    routes are CPU-bound on Jinja rendering + Pydantic validation; an
    AsyncSession would add ceremony without ROI at household scale.
    """
    with SessionLocal() as session:
        yield session
```

**Translation notes:**
- `Iterator[Session]` (sync) vs `AsyncIterator[AsyncSession]` (async) at the existing line 32.
- No lazy import needed — `SessionLocal` is created at module load in `app/db.py` and has no circular dependency on `app.main` (the async factory does — see line 41-42 lazy import in the existing dep).
- `yield` inside an `Iterator`-typed function makes this a FastAPI-compatible generator dependency (analogous to the existing async-generator dependency).

---

## Shared Patterns

### Authentication

**Source:** `app/dependencies/auth.py:33-45` (existing; do not modify).
**Apply to:** every Phase 4 router endpoint except `/photos/{name}` (which must use direct `request.state.user` access to translate anonymous to 404 per D-06).

**Excerpt:**
```python
def require_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
```

**Usage in every Phase 4 router endpoint:**
```python
user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1 idiom
```

---

### CSRF (form-side)

**Source:** `app/templates/pages/setup.html:10` (verbatim line).
**Apply to:** every Phase 4 form fragment + every state-changing form on a page template.

**Excerpt (copy verbatim, do not modify):**
```jinja
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

The `CSRFFormFieldShim` (wired in `app/main.py:205`) hoists this hidden input into the `X-CSRF-Token` request header before `CSRFMiddleware` checks it.

---

### CSRF (HTMX-side)

**Source:** `app/static/js/htmx-listeners.js:34-39` (already wired; do not modify).
**Apply to:** automatic — every HTMX request reads `meta[name=csrf-token]` from `base.html:10` and sets the header.

**Excerpt:**
```javascript
document.body.addEventListener('htmx:configRequest', (evt) => {
  const tokenMeta = document.querySelector('meta[name="csrf-token"]');
  if (tokenMeta) {
    evt.detail.headers['X-CSRF-Token'] = tokenMeta.content;
  }
});
```

**Translation note:** The hidden form input is the **fallback** for HTMX requests where the listener might miss (e.g., the autocomplete dropdown's `hx-get` carries a GET which doesn't trigger CSRF anyway). For state-changing POSTs both belt and braces apply.

---

### Form Validation Error (SEC-06 / D-04 — universal pattern, NEW in Phase 4)

**Source:** the SHAPE comes from `app/routers/auth.py:170-178` (catch `ValidationError`, return `TemplateResponse(..., status_code=200)` with `{"error": "..."}`). **Phase 4 extends this to field-level errors** + form-fragment template (not full page) + preserved submitted values.

**Excerpt (the auth.py reference for the SHAPE):**
```python
try:
    form = SetupForm(username=username, email=email, password=password)
except ValidationError:
    return templates.TemplateResponse(
        request=request,
        name="pages/setup.html",
        context={"error": "Please check the form values."},
        status_code=200,
    )
```

**Phase 4 extension (NEW pattern — apply to every catalog router POST):**
```python
try:
    form = CoffeeCreate(name=name, ...)
except ValidationError as exc:
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_form.html",  # form FRAGMENT, not full page
        context={
            "values": {"name": name, "roaster_id": roaster_id, ...},  # preserve submitted
            "errors": {e["loc"][-1]: e["msg"] for e in exc.errors()},  # field-level errors
        },
        status_code=200,
    )
```

**Translation notes:**
- `status_code=200` (not 422) — HTMX swaps only on 2xx, and the same shape works for HTMX and JS-disabled fallback.
- `values` carries the user's submitted values for re-population (vs auth's `username=` repopulation in `auth.py:296`).
- `errors[field_name]` rendered inline in the template per UI-SPEC §"Form Validation Errors" (red `border-red-300`, helper text `text-sm text-red-700`).
- Apply identically across coffees, roasters, flavor_notes, equipment, recipes, bags routers — the SEC-06 universal pattern.

---

### Audit Event Emission

**Source:** `app/services/credentials.py:257-263` (verbatim — emit at every write path with kwargs only, never positional).

**Excerpt:**
```python
log.info(
    ADMIN_API_CREDENTIAL_SET,
    provider=provider,
    last_four=last_four,
    model_name=model_name,
    user_id=by_user_id,
)
```

**Translation notes:**
- Event name comes from `app/events.py` constant (NEVER inline strings — see `events.py:6-7` rationale).
- Kwarg name is **`user_id`** (NOT `by_user_id`) per Phase 1 D-14 taxonomy alignment — see `credentials.py:196-197`.
- Apply to every Phase 4 catalog write service: `coffees.create_coffee`, `roasters.archive_roaster`, etc. each end with one `log.info(CATALOG_*, entity_id=..., user_id=...)` line.

---

### Soft-Delete (archive flag)

**Source:** `app/services/credentials.py:266-298` (`set_provider_enabled` — the toggle pattern with `update().values()`).

**Excerpt:**
```python
def archive_coffee(db: Session, *, coffee_id: int, by_user_id: int) -> None:
    db.execute(
        update(Coffee)
        .where(Coffee.id == coffee_id)
        .values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(CATALOG_COFFEE_ARCHIVED, coffee_id=coffee_id, user_id=by_user_id)
```

**Translation notes:**
- **Explicit `updated_at=func.now()`** is critical — `credentials.py:67-69` comment explains why: Core update() bypasses ORM onupdate hooks.
- Apply to all five entities + bags.

---

## No Analog Found

The following Phase 4 elements have no exact analog in the repo and must be authored from primary sources (CONTEXT + UI-SPEC + library docs):

| File / pattern | Reason | Source for guidance |
|---|---|---|
| HTMX fragment templates (`app/templates/fragments/*.html`) | First fragments in the repo — `app/templates/fragments/` is currently empty | Phase 4 D-01..D-04 + UI-SPEC + `pages/setup.html` form block as a skeleton |
| HTMX 2.0.10 attribute patterns (`hx-target`, `hx-swap`, `hx-push-url`, `hx-trigger`, `hx-sync`, `hx-swap-oob`) | Repo loads HTMX at `base.html:16` but no template uses any HTMX attributes yet | HTMX 2.0.10 docs (CONTEXT canonical_refs lists the relevant ones); UI-SPEC §"Inline-Expand Form Pattern" + §"Autocomplete Dropdown" |
| Alpine CSP-build live components | `__init.js` is reference-only; no live components in repo | `__init.js` comment block (lines 7-49) is the convention; UI-SPEC §"Recipe Step Builder" + §"Mini-Modal Pattern" |
| Pillow API + magic-byte verify | First Pillow consumer; first multipart upload in the repo | RESEARCH.md §"Photo Upload Pipeline" + CONTEXT §"Photo MIME validation order" + Pillow 12.2 docs |
| `HX-Trigger` response header (D-15 / D-16 plumbing) | Net-new HTTP pattern | HTMX 2.0.10 docs; CONTEXT specifics |
| `HX-Redirect` response header (D-12 duplicate-recipe) | Net-new HTTP pattern | HTMX 2.0.10 docs |
| FastAPI `File()` / `UploadFile` + multipart | First multipart consumer in repo | FastAPI 0.136 docs |
| `FileResponse` with explicit cache + nosniff headers (D-06 photo serve) | Net-new — `auth.py` uses `RedirectResponse`/`HTMLResponse`; `admin.py` uses `HTMLResponse`. No `FileResponse` consumer | FastAPI 0.136 docs + CONTEXT D-06 verbatim |
| Postgres `ARRAY(BigInteger)` + GIN index (`coffees.advertised_flavor_note_ids`) | First array column in repo | RESEARCH.md §"5 Catalog Models" + Postgres 16 GIN docs |
| Postgres `JSONB` column on an ORM model (`recipes.steps`) | Repo uses `JSONB` once in raw migration (`0001_initial.py:165` for `ai_recommendations.response_json`) but no ORM model with it yet (ai_recommendation.py is in models/ but not read for this audit — verify pattern there is identical) | RESEARCH.md + SQLAlchemy 2.0 + `0001_initial.py:165` |

---

## Metadata

**Analog search scope:** `app/**` (full repo).
**Files scanned:** 50 (every .py + 4 templates + 2 static files + 3 migrations).
**Pattern extraction date:** 2026-05-18.
**Key verified files referenced:** `app/models/user.py`, `app/models/api_credential.py`, `app/models/bag.py`, `app/models/__init__.py`, `app/routers/auth.py`, `app/routers/admin.py`, `app/schemas/auth.py`, `app/services/credentials.py`, `app/services/settings.py`, `app/services/auth.py`, `app/services/setup.py`, `app/dependencies/auth.py`, `app/dependencies/db.py`, `app/events.py`, `app/main.py`, `app/db.py`, `app/csrf.py`, `app/templates/pages/setup.html`, `app/templates/pages/login.html`, `app/templates/base.html`, `app/static/js/htmx-listeners.js`, `app/static/js/alpine-components/__init.js`, `app/migrations/versions/0001_initial.py`, `app/migrations/versions/p1_sessions_table.py`, `app/migrations/versions/p3_api_credentials.py`, `app/templates_setup.py`.
