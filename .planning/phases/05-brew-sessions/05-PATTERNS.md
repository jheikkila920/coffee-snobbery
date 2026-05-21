# Phase 5: Brew Sessions - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 24 new/modified
**Analogs found:** 22 with strong matches / 24 (2 partial)

All analog files cited below were verified to exist on disk; line references were confirmed against the actual file contents (not just quoted from RESEARCH.md). Where RESEARCH.md cited a line range, it was re-read and the exact lines are reproduced here.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/models/brew_session.py` | model | CRUD | `app/models/coffee.py` (+ `recipe.py`, `bag.py`) | role-match (novel: `Computed` EY) |
| `app/models/brew_draft.py` | model | CRUD (upsert) | `app/models/app_setting.py` / `coffee.py` | role-match |
| `app/schemas/brew_session.py` | schema | request-response | `app/schemas/recipe.py` (+ `coffee.py`) | exact |
| `app/schemas/brew_csv.py` | schema | transform/batch | `app/schemas/recipe.py` (`StepSchema`) | role-match |
| `app/routers/brew.py` | router | request-response + CRUD | `app/routers/coffees.py` | exact (with D-01 divergence) |
| `app/services/brew_sessions.py` | service | CRUD | `app/services/equipment.py` | exact |
| `app/services/brew_drafts.py` | service | CRUD (upsert/clear) | `app/services/equipment.py` + `app/services/settings.py` | role-match |
| `app/services/csv_io.py` | service | batch/transform | `app/services/flavor_notes.py` (citext resolve) + stdlib `csv` | partial (no CSV analog) |
| `app/static/js/alpine-components/rating-stars.js` | component (Alpine) | event-driven | `app/static/js/alpine-components/recipe-step-builder.js` | role-match |
| `app/static/js/alpine-components/flavor-tag-input.js` | component (Alpine) | event-driven | `app/static/js/alpine-components/autocomplete.js` (`flavorNoteChips`) | exact (clone + rename) |
| `app/static/js/alpine-components/brew-ratio.js` | component (Alpine) | transform | `app/static/js/alpine-components/recipe-step-builder.js` (computed getters) | role-match |
| `app/static/js/alpine-components/brew-draft.js` | component (Alpine) | event-driven | `app/static/js/alpine-components/recipe-step-builder.js` (init/data-*) | partial (localStorage + fetch novel) |
| `app/templates/pages/brew_form.html` | template (page) | request-response | `app/templates/fragments/coffee_form.html` | role-match (page, not fragment) |
| `app/templates/pages/sessions.html` | template (page) | CRUD list | `app/templates/pages/coffees.html` | exact |
| `app/templates/pages/brew_import.html` | template (page) | batch | `app/templates/pages/coffees.html` (page shell) | partial |
| `app/templates/fragments/session_list.html` | template (fragment) | CRUD list | `app/templates/fragments/coffee_list.html` | exact |
| `app/templates/fragments/session_row.html` | template (fragment) | CRUD | `app/templates/fragments/coffee_row.html` | exact |
| `app/templates/fragments/csv_import_results.html` | template (fragment) | batch | `app/templates/fragments/coffee_list.html` (loop shell) | partial |
| `app/templates/fragments/autocomplete_list.html` | template (fragment) | REUSE | (no change — reuse as-is) | n/a |
| `app/migrations/versions/p5_*.py` | migration | DDL | `app/migrations/versions/p4_shared_catalog.py` | exact (GIN + hand-edit precedent) |
| `app/events.py` (extend) | config (constants) | n/a | existing `CATALOG_*` block in `app/events.py` | exact |
| `app/main.py` (extend) | config (wiring) | n/a | `app/main.py` `include_router` block | exact |
| `app/models/__init__.py` (extend) | config (re-export) | n/a | `app/models/__init__.py` | exact |
| `app/templates/base.html` (extend) | template (layout) | n/a | `app/templates/base.html` script-tag block | exact |

---

## Pattern Assignments

### `app/models/brew_session.py` (model, CRUD)

**Analog:** `app/models/coffee.py` (ARRAY column + conventions); `app/models/recipe.py` (numeric/grind columns); `app/models/bag.py` (FK `ondelete` choices).

**Imports + `Mapped[...]` column convention** (`app/models/coffee.py:33-84`):
```python
from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Identity, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base

class Coffee(Base):
    __tablename__ = "coffees"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ...
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
```

**ARRAY(BigInteger) column** — copy verbatim for `flavor_note_ids_observed` (`app/models/coffee.py:73-77`):
```python
advertised_flavor_note_ids: Mapped[list[int]] = mapped_column(
    ARRAY(BigInteger),
    nullable=False,
    server_default=text("'{}'::bigint[]"),
)
```

**FK `ondelete` choices** — mirror the asymmetry: `coffee_id` denormalized NOT NULL with `ondelete="RESTRICT"` (matches `bags.coffee_id`, `app/models/bag.py:49-53`); nullable equipment/recipe/bag FKs use `ondelete="SET NULL"` (matches `coffees.roaster_id`, `app/models/coffee.py:62-66`):
```python
roaster_id: Mapped[int | None] = mapped_column(
    BigInteger,
    ForeignKey("roasters.id", ondelete="SET NULL"),
    nullable=True,
)
```

**NOVEL — GENERATED column.** No on-disk analog for `Computed`. Per RESEARCH §"brew_sessions Schema", the model declares it but the migration owns the literal DDL (see migration section). The model side:
```python
from sqlalchemy import Computed, Numeric
extraction_yield_pct: Mapped[Decimal | None] = mapped_column(
    Numeric(5, 2),
    Computed("(yield_grams_actual * tds_pct) / dose_grams_actual", persisted=True),
    nullable=True,
)
```
The planner must confirm the EY formula with John (RESEARCH flags it as dimensionally unusual) and verify `Computed(..., persisted=True)` against Context7 SQLAlchemy 2.0 docs. NULL propagates automatically when any operand is NULL.

**`__table_args__` Index pattern + GIN deferral note** (`app/models/coffee.py:86-104`): declare B-tree indexes here; do NOT declare the GIN index (autogenerate can't emit `USING GIN` — the migration adds it via raw SQL, exactly as `coffees` does).

---

### `app/models/brew_draft.py` (model, upsert)

**Analog:** `app/models/coffee.py` for the column/timestamp shape. One row per `user_id` (recommend a UNIQUE constraint on `user_id`). Store draft body as JSONB (mirror `recipes.steps`, `app/models/recipe.py:53-57`):
```python
steps: Mapped[list[dict]] = mapped_column(
    JSONB,
    nullable=False,
    server_default=text("'[]'::jsonb"),
)
```
Use the same `created_at`/`updated_at` `func.now()` pattern. FK `user_id → users.id` with `ondelete="CASCADE"` (a draft is meaningless without its user; this is the one place CASCADE is correct).

---

### `app/schemas/brew_session.py` (schema, request-response)

**Analog:** `app/schemas/recipe.py` (numeric ranges) + `app/schemas/coffee.py` (ARRAY field + `field_validator`).

**`extra="forbid"` + numeric `Field` ranges** (`app/schemas/recipe.py:47-57`):
```python
from pydantic import BaseModel, ConfigDict, Field

class RecipeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=200)
    dose_grams: int = Field(..., ge=1, le=200)
    water_grams: int = Field(..., ge=1, le=3000)
    water_temp_c: int = Field(..., ge=0, le=100)
    grind_setting: str = Field("", max_length=200)
```

**Rating — `Decimal` + `multiple_of`** (NOVEL exact value; pattern mirrors above). Per D-03 / BREW-04 the data layer stays `0.25`:
```python
from decimal import Decimal
rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))
```

**ARRAY id field + positive-int validator** — copy verbatim from `app/schemas/coffee.py:49-57`, rename to `flavor_note_ids_observed`:
```python
advertised_flavor_note_ids: list[int] = Field(default_factory=list)

@field_validator("advertised_flavor_note_ids")
@classmethod
def _all_ids_positive(cls, v: list[int]) -> list[int]:
    if not all(i >= 1 for i in v):
        msg = "advertised_flavor_note_ids must be positive integers (>= 1)"
        raise ValueError(msg)
    return v
```

**`Create`/`Update` class split** — keep the two-class convention (`app/schemas/coffee.py:60-67`): `BrewSessionUpdate(BrewSessionCreate)`.

**Anti-pattern (RESEARCH §Anti-Patterns):** `extraction_yield_pct` MUST NOT be a writable schema field — it is GENERATED, render-only.

---

### `app/schemas/brew_csv.py` (schema, transform/batch)

**Analog:** `app/schemas/recipe.py::StepSchema` (`app/schemas/recipe.py:37-44`) — a focused per-row Pydantic model with `extra="forbid"` and per-field ranges. The CSV row schema validates numeric ranges + rating scale before INSERT (RESEARCH import-algorithm step 4). Same `Decimal` rating constraint as `brew_session.py`.

---

### `app/routers/brew.py` (router, request-response + CRUD)

**Analog:** `app/routers/coffees.py` — the canonical SEC-06 / D-04 router. Differences are D-01 (dedicated page routes, not inline fragments) and per-user scoping.

**Router setup + `require_user` gate + per-user scope** (`app/routers/coffees.py:46-64`, `app/dependencies/auth.py:33-45`):
```python
from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/brew")
```
Every handler takes `user: User = Depends(require_user)` and scopes queries by `user.id` (architectural invariant: brew sessions are per-user). `require_user` returns the full `User` row from `request.state.user`.

**SEC-06 form validation → 200 + fragment re-render** (`app/routers/coffees.py:353-382`):
```python
@router.post("", response_class=HTMLResponse)
async def create_coffee(request, user=Depends(require_user), db=Depends(get_session)):
    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = CoffeeCreate(**schema_input)
    except ValidationError as exc:
        context = _hydrate_form_context(
            db, values=raw_view,
            errors=_normalize_errors(errors_by_field(exc)),
            mode="create",
        )
        return templates.TemplateResponse(
            request=request, name="fragments/coffee_form.html",
            context=context, status_code=200,
        )
    # ... service write
```
**D-01 divergence:** Phase 4 returns a `coffee_row.html` fragment on success (inline-expand). Phase 5's brew form is a dedicated page, so success → `HX-Redirect` to `/brew` (sessions list) or a cleared `/brew/new`. Validation-failure path is identical (re-render the page at 200 with `values` + `errors`).

**ARRAY multi-value form collection via `getlist`** (`app/routers/coffees.py:155-168`) — copy `_parse_form_payload` shape, change the key to `flavor_note_ids_observed`:
```python
if key == "advertised_flavor_note_ids":
    values = form_data.getlist(key)
    id_strs = [v for v in values if isinstance(v, str) and v != ""]
    raw_view[key] = id_strs
    try:
        schema_input[key] = [int(v) for v in id_strs]
    except (TypeError, ValueError):
        schema_input[key] = [0]  # sentinel → field_validator ge=1 trips
```

**`_normalize_errors` + `_FORM_FIELDS` sentinel fold** (`app/routers/coffees.py:70-125`) — copy for the brew form's larger field set so a `T-04-MASS` `extra="forbid"` rejection folds into `_form`.

**`_hydrate_form_context`** (`app/routers/coffees.py:186-238`) — the brew analog resolves: selected coffee/bag/recipe/equipment names + `selected_flavor_notes` (for seeded observed chips) + the D-11 advertised-note chips for the selected coffee + the prefill source values (D-04/D-05/D-06/D-08).

**List page vs HTMX fragment branch** (`app/routers/coffees.py:246-312`) — the sessions list reuses this exactly: `if request.headers.get("HX-Request") == "true"` → return `fragments/session_list.html`; else return `pages/sessions.html`. Filters are query params (`coffee_id`, `brewer_id`, rating range, date range). `FragmentCacheHeadersMiddleware` handles `no-store + Vary: HX-Request` for free.

**Route-order gotcha** (`app/routers/coffees.py:420-456`): declare literal paths (e.g. `/brew/new`, `/brew/import`, `/brew/export`, `/brew/draft`) BEFORE `/brew/{session_id}` so Starlette's int matcher doesn't capture them.

**CSV upload guard:** RESEARCH cites `app/services/photos.py` for an upload size guard, but photos validates via a Canvas downscale (`/static/js/photo-upload.js`) + router checks, not a reusable byte-size service function. **No clean analog** — the planner reads `UploadFile`, enforces a size ceiling, and decodes with `utf-8-sig` (stdlib). Treat as net-new.

---

### `app/services/brew_sessions.py` (service, CRUD)

**Analog:** `app/services/equipment.py` — the canonical sync-service shape (kwargs API, single commit, audit event).

**Create: instantiate → add → flush → commit → audit** (`app/services/equipment.py:67-102`):
```python
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from app.events import CATALOG_EQUIPMENT_CREATED

log = structlog.get_logger(__name__)

def create_equipment(db, *, type_, brand, model, notes, by_user_id) -> Equipment:
    equipment = Equipment(type=type_, brand=brand, model=model, notes=notes)
    db.add(equipment)
    db.flush()   # populate id for the audit event
    db.commit()
    log.info(CATALOG_EQUIPMENT_CREATED, equipment_id=equipment.id, user_id=by_user_id)
    return equipment
```

**Update via Core `update()` + `updated_at=func.now()`** (`app/services/equipment.py:151-189`) — copy for `update_brew_session`.

**Per-user scoped queries** — every `select(BrewSession).where(BrewSession.user_id == by_user_id)`. Prefill queries (D-04 last-session, D-04 last-session-with-coffee, D-06 newest-open-bag) follow this.

**D-06 open-bag lookup analog** (`app/services/bags.py:115-126`) — `list_bags_for_coffee` already orders `opened_at DESC NULLS LAST`; the D-06 query adds `.where(Bag.finished_at.is_(None))` and takes the first row:
```python
stmt = (select(Bag)
    .where(Bag.coffee_id == coffee_id)
    .order_by(Bag.opened_at.desc().nulls_last(), Bag.created_at.desc()))
```

**`equipment.usage_count` increment (CONTEXT discretion → service-layer):** in the same transaction before commit, `update(Equipment).where(Equipment.id.in_([brewer_id, grinder_id, kettle_id])).values(usage_count=Equipment.usage_count + 1)`. Decrement on equipment-change edit + on session delete. The `equipment.py` docstring (`app/services/equipment.py:43-46`) explicitly notes this is Phase 5's job and the create/update/archive paths do NOT touch it.

---

### `app/services/brew_drafts.py` (service, upsert/clear)

**Analog:** `app/services/equipment.py` (write shape) + `app/services/settings.py` (single-key upsert idea). One draft per user: get-or-upsert keyed by `user_id`, plus a `clear_draft(db, *, user_id)` that does `delete(BrewDraft).where(BrewDraft.user_id == user_id)` + commit. Called on successful submit and on logout (MX-5). Emit `brew.draft.*` audit events. `/brew/new` only.

---

### `app/services/csv_io.py` (service, batch/transform)

**Analog (partial):** `app/services/flavor_notes.py` for the citext resolve/auto-create primitives; stdlib `csv` for parsing (no project CSV analog exists).

**Citext name resolution (D-12 coffee match, D-10 flavor-note match)** — `app/services/flavor_notes.py:187-204` shows CITEXT-native case-insensitive matching with no `func.lower()` wrapper:
```python
stmt = (select(FlavorNote)
    .where(FlavorNote.archived.is_(False))
    .where(FlavorNote.name.ilike(f"{query}%"))  # CITEXT → case-insensitive natively
    .order_by(FlavorNote.name).limit(limit))
```
For D-12 use exact citext equality (`Coffee.name == name`); roaster-qualify when a roaster column is present; an ambiguous multi-match → refused row.

**D-09 auto-create flavor note** — reuse `app/services/flavor_notes.py:56-86` `create_flavor_note(db, name=..., category="other", by_user_id=...)`; it already handles the UNIQUE-citext `IntegrityError` → `DuplicateNameError` rollback (treat a concurrent duplicate as "link existing").

**Single-transaction insert (BREW-11):** resolve + dedup + validate per row, INSERT all accepted rows, `db.commit()` once, then build the per-row outcome list. Dedup key `(user_id, coffee_id, brewed_at)` (D-14); no UNIQUE constraint (CONTEXT defers it) — probe with a `select` before insert.

**Export (D-15):** stdlib `csv.DictWriter` with an explicit Snobbery header row; resolve ids → names; include read-only computed brew-ratio + `extraction_yield_pct`; `Content-Disposition: attachment`; plain `<a href>` (not HTMX).

---

### `app/static/js/alpine-components/flavor-tag-input.js` (component, event-driven)

**Analog:** `app/static/js/alpine-components/autocomplete.js` `flavorNoteChips` factory — clone and rename to `observedFlavorNotes`, bind to `flavor_note_ids_observed`.

**CSP-build registration + `data-*` config + parallel x-for hidden inputs** (`app/static/js/alpine-components/autocomplete.js:167-258`):
```js
document.addEventListener('alpine:init', () => {
  Alpine.data('flavorNoteChips', () => ({
    selectedChips: [],
    init() {
      let initialChips = [];
      try { initialChips = JSON.parse(this.$root.dataset.initialChips || '[]'); }
      catch (_err) { initialChips = []; }
      this.selectedChips = Array.isArray(initialChips) ? initialChips.slice() : [];
      // clears static [data-seed-chip] / [data-seed-hidden-container] siblings
      // ...
      this._onCreated = (evt) => { /* HX-Trigger flavor-note-created → push chip */ };
      document.body.addEventListener('flavor-note-created', this._onCreated);
    },
    commitItem(el) {            // reads data-item-id / data-item-name off clicked <li>
      const id = parseInt(el.dataset.itemId, 10);
      if (!Number.isFinite(id)) return;
      this.addChip(id, el.dataset.itemName || '');
    },
    removeChip(id) { this.selectedChips = this.selectedChips.filter(c => c.id !== id); },
    onInput(el) { this.query = el.value; this.open = this.query.length >= 2; },
    onKeydown(e) { /* Up/Down/Enter/Esc + Backspace-removes-last-chip */ },
  }));
});
```
**Anti-pattern (D-11, RESEARCH):** the new factory must be a sibling bound to `flavor_note_ids_observed`, NOT a reuse of the same `name` — `flavor_note_ids_observed` (per-session) and `advertised_flavor_note_ids` (per-coffee) must never be conflated. Add D-09 auto-create handling (the "new" badge) and D-11 advertised quick-add chips.

---

### `app/static/js/alpine-components/rating-stars.js` (component, event-driven)

**Analog:** `app/static/js/alpine-components/recipe-step-builder.js` — for the `init()`/`data-*` seed pattern and CSP-build rules.

**Seed from `data-*` in `init()`** (`app/static/js/alpine-components/recipe-step-builder.js:24-44`):
```js
document.addEventListener('alpine:init', () => {
  Alpine.data('recipeStepBuilder', () => ({
    steps: [],
    init() {
      const initial = this.$root.dataset.initialSteps;   // ← seed via data-*
      try { const parsed = JSON.parse(initial || '[]');
        this.steps = Array.isArray(parsed) ? parsed : []; }
      catch (_err) { this.steps = []; }
    },
  }));
});
```
`ratingStars` seeds `value` via `data-initial-rating`, mirrors a hidden input `<input type="hidden" name="rating" :value="value">` (UI-SPEC). CSP rules (`recipe-step-builder.js:11-22`): no `x-model` (use `:value` + `x-on:click`/`x-on:keydown`), no inline expressions, only method calls + simple member access; precompute anything needing `Math` in JS (see `barStyle` at `recipe-step-builder.js:164`).

---

### `app/static/js/alpine-components/brew-ratio.js` (component, transform)

**Analog:** `app/static/js/alpine-components/recipe-step-builder.js` computed getters (`recipe-step-builder.js:118-139`):
```js
get totalWater() { if (!this.steps.length) return 0; return this.steps[this.steps.length-1].water_grams || 0; }
```
`brewRatio` exposes a `get ratio()` returning `water / dose` formatted to 2 decimals; dose 0/empty → `"—"` (never NaN/Infinity, UI-SPEC lock). Dose/water inputs report in via `x-on:input`.

---

### `app/static/js/alpine-components/brew-draft.js` (component, event-driven)

**Analog (partial):** `recipe-step-builder.js` for the factory/`init`/`data-*` shape. The localStorage read/write, blur→`POST /brew/draft`, and per-field touched-state are net-new. CSRF on the autosave POST: read the token from `<meta name="csrf-token">` (`app/templates/base.html:10`) — the global `htmx-listeners.js` injects the header for HTMX requests; a raw `fetch` must add `X-CSRF-Token` itself. Reconciliation order (BREW-07): localStorage primary, server restore only when localStorage empty.

---

### `app/templates/pages/brew_form.html` (template, page)

**Analog:** `app/templates/fragments/coffee_form.html` — for label/input/CSRF/error patterns; but this is a full page that `extends base.html` (not an inline fragment).

**CSRF hidden field** (`app/templates/fragments/coffee_form.html:60-61`) — mandatory on every brew form:
```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

**Field label + error pattern** (`app/templates/fragments/coffee_form.html:63-73`):
```html
<label class="flex flex-col gap-1">
  <span class="text-sm font-semibold">Name</span>
  <input name="name" required maxlength="200" value="{{ values.get('name', '') }}"
         class="rounded border px-2 py-2 text-base{% if errors.get('name') %} border-red-300{% else %} border-espresso-200{% endif %}">
  {% if errors.get('name') %}
    <p class="text-sm text-red-700 mt-1">{{ errors['name'] }}</p>
  {% endif %}
</label>
```

**Native `<select>` pattern (D-07 water_type, equipment, recipe pickers)** (`app/templates/fragments/coffee_form.html:137-149`):
```html
<select name="process" class="rounded border px-2 py-2 text-base ...">
  <option value=""{% if not values.get('process') %} selected{% endif %}>—</option>
  {% for p in processes %}
    <option value="{{ p }}"{% if values.get('process') == p %} selected{% endif %}>{{ p }}</option>
  {% endfor %}
</select>
```

**Chip-builder seed markup (observed flavor notes)** (`app/templates/fragments/coffee_form.html:206-282`) — clone the `x-data="flavorNoteChips"` wrapper + parallel `<template x-for>` (visible chips + hidden inputs) + `[data-seed-chip]`/`[data-seed-hidden-container]` static seeds, change `x-data` to `observedFlavorNotes` and the hidden-input `name` to `flavor_note_ids_observed`.

**Autocomplete input wiring (D-10 reuse)** (`app/templates/fragments/coffee_form.html:261-278`):
```html
<input type="text" name="flavor_note_query" :value="query"
       x-on:input="onInput($el)" x-on:focus="onFocus()" x-on:blur="onBlur()"
       x-on:keydown="onKeydown($event)" autocomplete="off"
       hx-get="/flavor-notes/datalist"
       hx-trigger="input changed delay:350ms[target.value.length >= 2], focus once from:closest .field"
       hx-sync="this:replace" hx-target="#flavor-note-dropdown" hx-swap="innerHTML">
```

**CSP locks (UI-SPEC + RESEARCH):** no `|safe`, no inline `hx-on:`, no `hx-vals='js:'`, no `x-model`. The CSV refused-reason strings, prefill values, and chip names all render autoescaped.

---

### `app/templates/pages/sessions.html` + `fragments/session_list.html` + `fragments/session_row.html`

**Analogs:** `app/templates/pages/coffees.html`, `app/templates/fragments/coffee_list.html`, `app/templates/fragments/coffee_row.html`.

**Filter-bar + `hx-push-url` + desktop-table/mobile-card collapse** — `coffees.py:246-312` (router branch) drives `coffee_list.html`; the session list mirrors it exactly. The row fragment uses a `mode` flag (desktop row vs mobile card) like `coffee_row.html`. "Brew again" links to `/brew/new?from={session_id}` (D-08); "Edit" → `/brew/{id}/edit`.

**Autocomplete dropdown fragment — REUSE unchanged** (`app/templates/fragments/autocomplete_list.html:36-66`): `<ul role="listbox">`, `min-h-[44px]` rows, server-side `<strong>` match highlight, `commitItem($el)` reading `data-item-id`/`data-item-name`, "+ Create new" row only when `not exact_match`. D-10 (link-on-exact, create-on-no-match) is already encoded here.

---

### `app/migrations/versions/p5_brew_sessions.py` (migration, DDL)

**Analog:** `app/migrations/versions/p4_shared_catalog.py` — the GENERATED + GIN hand-edit precedent.

**Revision header + inline schema (no `app.models` import)** (`app/migrations/versions/p4_shared_catalog.py:51-63`):
```python
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p5_brew_sessions"
down_revision = "p4_shared_catalog"
```
Describe the table inline with `sa.Column`/`sa.ForeignKey`/`sa.CheckConstraint` (do NOT import models — `p4_shared_catalog.py:32-35` documents this rule).

**ARRAY column** (`app/migrations/versions/p4_shared_catalog.py:141-146`):
```python
sa.Column("advertised_flavor_note_ids", postgresql.ARRAY(sa.BigInteger),
          nullable=False, server_default=sa.text("'{}'::bigint[]")),
```

**Hand-edited GIN index via raw `op.execute`** (`app/migrations/versions/p4_shared_catalog.py:174-178`; downgrade `IF EXISTS` at `:279`):
```python
op.execute("CREATE INDEX ix_coffees_advertised_flavor_note_ids "
           "ON coffees USING GIN (advertised_flavor_note_ids)")
```

**NOVEL — GENERATED column DDL.** Autogenerate cannot emit `GENERATED ALWAYS AS`. The migration hand-writes it the same way the GIN index is hand-written — either `op.execute("ALTER TABLE brew_sessions ADD COLUMN extraction_yield_pct numeric(5,2) GENERATED ALWAYS AS ((yield_grams_actual * tds_pct) / dose_grams_actual) STORED")`, or include the generated clause directly in `create_table` via a raw column. Planner confirms the exact expression with John.

**Indexes to declare:** `(user_id, brewed_at DESC)`, `(user_id, coffee_id, brewed_at DESC)`, GIN on `flavor_note_ids_observed`. NO UNIQUE on the dedup key (CONTEXT defers it). FK-order: `brew_drafts` and `brew_sessions` both depend on tables already created in earlier migrations, so order within this migration is flexible; create `brew_sessions` after confirming all referenced tables exist.

---

### `app/events.py` (extend — constants)

**Analog:** the existing `CATALOG_*` block (`app/events.py:77-115`). Add `brew.*` constants following the `<category>.<action>` taxonomy, add them to `__all__` (`app/events.py:118-156`), keeping it alphabetized:
```python
BREW_SESSION_CREATED = "brew.session.created"
BREW_SESSION_UPDATED = "brew.session.updated"
BREW_SESSION_DELETED = "brew.session.deleted"
BREW_DRAFT_SAVED = "brew.draft.saved"
BREW_DRAFT_CLEARED = "brew.draft.cleared"
BREW_CSV_IMPORTED = "brew.csv.imported"
BREW_CSV_EXPORTED = "brew.csv.exported"
```

---

### `app/main.py` (extend — wiring)

**Analog:** the `include_router` block (`app/main.py:84-94` imports, `:218-228` registration). Add `from app.routers import brew as brew_router` and `app.include_router(brew_router.router)`. **No middleware changes** (CONTEXT integration note).

---

### `app/models/__init__.py` (extend — re-export)

**Analog:** `app/models/__init__.py:15-43`. Add `from app.models.brew_session import BrewSession` and `from app.models.brew_draft import BrewDraft`, plus both names to `__all__`. The module docstring (`:1-11`) is explicit: a model not re-exported here is invisible to Alembic autogenerate.

---

### `app/templates/base.html` (extend — layout)

**Analog:** the Alpine component `<script defer nonce>` block (`app/templates/base.html:13-25`). Add four tags BEFORE the `@alpinejs/csp` core script (`:25`), matching the existing three:
```html
<script defer src="/static/js/alpine-components/rating-stars.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/flavor-tag-input.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/brew-ratio.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/brew-draft.js" nonce="{{ csp_nonce(request) }}"></script>
```

---

## Shared Patterns

### Authentication / per-user scope
**Source:** `app/dependencies/auth.py:33-45` (`require_user`)
**Apply to:** every `app/routers/brew.py` handler.
```python
def require_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
```
`request.state.user` is the full `User` row (Phase 2). All brew queries scope by `user.id` (architectural invariant).

### Form validation → 200 + fragment re-render (SEC-06 / D-04)
**Source:** `app/services/form_validation.py:45-69` (`errors_by_field`) + `app/routers/coffees.py:353-382` (catch path)
**Apply to:** every brew form POST (`/brew`, `/brew/{id}`).
```python
def errors_by_field(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        field = next((str(p) for p in reversed(loc) if not isinstance(p, int)), "_form")
        out[field] = err.get("msg", "Invalid value")
    return out
```
Returns HTTP 200 (not 422) so HTMX swaps cleanly. `DuplicateNameError` (`form_validation.py:31-42`) is the same-path sentinel for the D-09 citext-collision case.

### Audit events (structlog constants)
**Source:** `app/events.py` + `app/services/equipment.py:94-101`
**Apply to:** every brew service write path. Import the constant; never hard-code the string. `user_id` kwarg (not `by_user_id`) in the `log.info` call per the D-14 taxonomy alignment.

### CSRF on state-changing forms
**Source:** `app/templates/fragments/coffee_form.html:60-61` (form field) + `app/templates/base.html:10` (meta) + `app/main.py:74,211-212` (`CSRFFormFieldShim`)
**Apply to:** the brew form, the import form, AND the `/brew/draft` autosave POST. Hidden `X-CSRF-Token` field on forms; meta-token + global `htmx-listeners.js` for HTMX/fetch.

### CSP-strict Alpine + template rules
**Source:** `app/static/js/alpine-components/__init.js:1-63` + `recipe-step-builder.js:11-22` + `app/templates/base.html:1,13-25`
**Apply to:** all four new components + all brew templates. `Alpine.data(name, factory)`, string `x-data` refs, config via `data-*` read in `init()`, `:value`+`x-on:input` (no `x-model`), no inline `hx-on:`/`hx-vals='js:'`/`|safe`. Each component a separate `<script defer nonce>` BEFORE the Alpine core. Subject to the existing CSP/grep tests — violations fail the build.

### Sync session + single commit
**Source:** `app/db.py::SessionLocal` (via `get_session` dep) + `app/services/equipment.py`
**Apply to:** all brew services. Keep brew CRUD handlers sync (FastAPI threadpools them); never call sync `Session` from an `async def` handler that isn't form-reading.

---

## No Analog Found

Files where the closest match is partial; the planner should lean on RESEARCH.md + stdlib rather than a copy-paste analog:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/services/csv_io.py` | service | batch/transform | No CSV import/export exists in the codebase. Reuse `flavor_notes.py` citext-resolve + `flavor_notes.create_flavor_note` (D-09) and `equipment.py` write shape; the `csv.DictReader`/`DictWriter` parsing, single-transaction batch insert, and per-row outcome summary are net-new (stdlib `csv`, RESEARCH import algorithm). |
| `app/static/js/alpine-components/brew-draft.js` | component | event-driven | localStorage primary store + blur→`POST /brew/draft` autosave + per-field touched-state have no on-disk precedent. Factory/`init`/`data-*` shape mirrors `recipe-step-builder.js`; the persistence logic is new (BREW-06/07, MX-5). |
| `app/templates/pages/brew_import.html` + `fragments/csv_import_results.html` | template | batch | No import/result-summary UI exists. Page shell + loop come from `pages/coffees.html` / `coffee_list.html`; the per-row outcome (inserted/skipped/refused-with-reason) layout is net-new (UI-SPEC §CSV Import Result UX). |

Net-new backend primitives (no analog, by design — RESEARCH §Don't Hand-Roll): the `Computed(persisted=True)` GENERATED column and its `GENERATED ALWAYS AS ... STORED` migration DDL. The GIN/raw-`op.execute` hand-edit in `p4_shared_catalog.py:174-178` is the closest procedural precedent.

---

## Metadata

**Analog search scope:** `app/models/`, `app/schemas/`, `app/routers/`, `app/services/`, `app/static/js/alpine-components/`, `app/templates/pages/`, `app/templates/fragments/`, `app/migrations/versions/`, `app/events.py`, `app/main.py`, `app/dependencies/auth.py`
**Files scanned:** 17 analog files read in full or by targeted section; all 24 target files classified
**Pattern extraction date:** 2026-05-19
