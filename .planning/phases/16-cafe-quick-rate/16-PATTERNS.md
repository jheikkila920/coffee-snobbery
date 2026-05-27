# Phase 16: Cafe Quick-Rate - Pattern Map

**Mapped:** 2026-05-27
**Files analyzed:** 24 (10 new + 14 modified/extended)
**Analogs found:** 24 / 24 (all files have a strong analog inside the repo)

This map tells each executor: which file in the repo to copy from, the 3–5 load-bearing excerpts that matter, and the project-memory caveats relevant to the file type. Read alongside `16-CONTEXT.md` (decisions D-01..D-16) and `16-RESEARCH.md` (Patterns 1–12 + Pitfalls 1–13).

---

## File Classification

### New files

| New file | Role | Data flow | Closest analog | Match quality |
|----------|------|-----------|----------------|---------------|
| `app/models/cafe_log.py` | model | persistence (per-user) | `app/models/brew_session.py` | exact (per-user table, ARRAY+GIN, FK asymmetry) |
| `app/schemas/cafe_log.py` | schema (Pydantic v2) | request-validation | `app/schemas/brew_session.py` | exact (mass-assignment defense, Decimal rating, list[int] FK ids) |
| `app/services/cafe_logs.py` | service | CRUD (per-user) | `app/services/brew_sessions.py` | exact (kwargs API, by_user_id, IDOR sentinel, single commit) |
| `app/routers/cafe_logs.py` | router | request-response (HTMX form + autocomplete) | `app/routers/brew.py` | exact (`_parse_form_payload`, `_hydrate_form_context`, NON_SCHEMA_FORM_KEYS, IDOR-404) |
| `app/templates/pages/cafe_log_form.html` | page template | server-rendered form (HTMX) | `app/templates/pages/brew_form.html` | exact (scope nesting, sticky save, safe-area-inset, autoescape contract) |
| `app/templates/fragments/cafe_log_card.html` | fragment | mobile-card render | `app/templates/fragments/coffee_row.html` mode="card" + `fragments/session_list.html` mobile branch | role-match (border-l-2 accent is the new bit) |
| `app/templates/fragments/cafe_log_row.html` | fragment | desktop-table row | `app/templates/fragments/coffee_row.html` mode="row" | exact (D-21 dual Edit button + OOB clear) |
| `app/templates/fragments/cafe_log_list.html` | fragment | HTMX swap target (list + empty branches) | `app/templates/fragments/session_list.html` | exact (md+ table / <md cards split; filtered-zero branch) |
| `app/migrations/versions/p16_cafe_logs.py` | migration | DDL (CREATE TABLE + indices) | `app/migrations/versions/p5_brew_sessions.py` (template) + `app/migrations/versions/p15_1_multi_origin.py` (sibling-table reference) | exact (inline schema, GIN via op.execute, DESC B-tree via op.execute) |
| `tests/services/test_cafe_logs.py` | test | service-layer | `tests/services/test_brew_sessions_service.py` + `tests/services/test_analytics.py` (skip-gate + `SessionLocal` pattern) | exact |
| `tests/routers/test_cafe_logs.py` | test | router | `tests/routers/test_brew_router.py` | exact |

### Modified files

| Modified file | Role | What changes | Closest analog (in-file) |
|---------------|------|--------------|--------------------------|
| `app/services/analytics.py` | service | extend `get_preference_profile` (l. 78), `get_flavor_descriptors` (l. 158), `get_cold_start_counts` (l. 309), `compute_input_signature` (l. 353); add comments on `get_top_coffees` (l. 47) + `get_sweet_spots` (l. 191) | the existing brew-only blocks within the same functions |
| `app/services/photos.py` | service | extend `sweep_orphans` UNION to include `cafe_logs.photo_filename` | the existing `Bag.photo_filename` block at l. 382-389 |
| `app/routers/brew.py` | router | `list_sessions` (l. 479) accepts `?tab=cafe` and dispatches | existing `_parse_list_filters` + `_raw_filters` helpers |
| `app/templates/pages/sessions.html` | page template | add 3rd "Quick rate" header button + tab toggle (above `{% include "fragments/session_list.html" %}`) + cafe-tab filter form variant | existing header flex row (l. 13-88) + Phase 4 filter-bar `<details>` |
| `app/templates/fragments/home/_cold_start.html` | fragment | dict-key contract unchanged (Pattern 11 keeps `gate.sessions` semantics); D-15 changes math only | the existing `{{ gate.sessions_needed }} more brew` copy at l. 30-39 stays |
| `app/main.py` | bootstrap | one-line: `app.include_router(cafe_logs_router.router)` | existing router includes |

---

## Pattern Assignments

### 1. `app/models/cafe_log.py` (new — model, persistence)

**Analog:** `app/models/brew_session.py` (verbatim shape; one new table)

**Imports + base** — copy the import block at `app/models/brew_session.py:38-58` (drop `Computed` + `Integer` — cafe has no GENERATED column and no Integer column):

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base
```

**FK directionality** — copy the RESTRICT-vs-SET-NULL contract from `app/models/brew_session.py:73-110`:

```python
# ondelete="RESTRICT" — user history is precious (mirrors BrewSession.user_id)
user_id: Mapped[int] = mapped_column(
    BigInteger,
    ForeignKey("users.id", ondelete="RESTRICT"),
    nullable=False,
)
# ondelete="SET NULL" — cafe log survives a roaster delete (mirrors BrewSession optional FKs)
roaster_id: Mapped[int | None] = mapped_column(
    BigInteger,
    ForeignKey("roasters.id", ondelete="SET NULL"),
    nullable=True,
)
```

**ARRAY + GIN caveat** — copy the docstring + column shape from `app/models/brew_session.py:30-35, :127-131`:

```python
flavor_note_ids: Mapped[list[int]] = mapped_column(
    ARRAY(BigInteger),
    nullable=False,
    server_default=text("'{}'::bigint[]"),
)
```

**Index declaration** — copy the `__table_args__` block from `app/models/brew_session.py:149-161` (DESC B-tree + the explicit comment that GIN lives in the migration, not here):

```python
__table_args__ = (
    Index("ix_cafe_logs_user_logged_at", "user_id", text("logged_at DESC")),
    # NOTE: GIN on flavor_note_ids is NOT declared here.
    # SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`;
    # the migration p16_cafe_logs.py adds it via raw op.execute().
)
```

**Project-memory caveats:**
- Plain `Text NOT NULL` for `cafe_name` — NOT CITEXT. Free per-user text, not a shared catalog identity. (Mirrors `coffee_origins.country`.)
- Always `from __future__ import annotations` — SQLAlchemy 2.0 + `Mapped[...]` convention.
- `rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)` — same precision as `BrewSession.rating` (`app/models/brew_session.py:126`).

---

### 2. `app/schemas/cafe_log.py` (new — schema, request-validation)

**Analog:** `app/schemas/brew_session.py` (the template for `extra="forbid"` mass-assignment defense)

**ConfigDict + Decimal rating** — copy the model_config + rating field from `app/schemas/brew_session.py:74-96`:

```python
from pydantic import BaseModel, ConfigDict, Field

class CafeLogCreate(BaseModel):
    """Cafe-log form. Validation errors → 200 + form re-render (SEC-06)."""

    model_config = ConfigDict(extra="forbid")

    # Decimal (NOT float) so 0.25 quarter-steps validate exactly (Pitfall 2 from brew_session schema)
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))
```

**Create/Update split** — copy the class split from `app/schemas/brew_session.py:128-134`:

```python
class CafeLogUpdate(CafeLogCreate):
    """Same shape today — split lets a future Update path diverge."""
```

**Field policy (Pattern 3 of RESEARCH.md):**
- `cafe_name: str = Field(..., min_length=1, max_length=200)` — only required field besides rating.
- `roaster_id: int | None = Field(None, ge=1)` — same shape as `bag_id` / `recipe_id` / `brewer_id` etc in `brew_session.py:81-85`.
- `flavor_note_ids: list[int] = Field(default_factory=list)` — mirrors `flavor_note_ids_observed` at `brew_session.py:97`.
- `origin_country: str | None = Field(None, max_length=100)` — plain string, no FK.
- `brew_method: str | None = Field(None, max_length=100)` — D-05 free-text.
- `notes: str = Field("", max_length=5000)` — mirrors `brew_session.py:98`.
- `logged_at: datetime | None = None` — nullable so the server can default to `datetime.now(UTC)` (mirrors `brewed_at` at `brew_session.py:103-104`).

**Fields that MUST be absent (mass-assignment defense, T-05-16):**
- `user_id` — server-set from `request.state.user.id`.
- `photo_filename` — the router reads `UploadFile` separately and passes the result of `photos.process_and_save()` to the service.

**Project-memory caveats:**
- Decimal-not-float for `rating` (rationale documented at `app/schemas/brew_session.py:13`).
- `extra="forbid"` folds posted-but-undeclared fields into the `_form` sentinel (matches the router's `_normalize_errors` at `app/routers/brew.py:138-153`).

---

### 3. `app/services/cafe_logs.py` (new — service, CRUD)

**Analog:** `app/services/brew_sessions.py` (the canonical per-user CRUD shape)

**CRUD signature convention** — copy the kwargs-after-leading-`*` shape from `app/services/brew_sessions.py:188-209`:

```python
def create_cafe_log(
    db: Session,
    *,
    by_user_id: int,
    cafe_name: str,
    rating: Decimal | None,
    roaster_id: int | None,
    origin_country: str | None,
    brew_method: str | None,
    flavor_note_ids: list[int],
    notes: str,
    photo_filename: str | None,
    logged_at: datetime | None,
) -> CafeLog: ...
```

**IDOR sentinel** — copy the `None` return for cross-user reads from `app/services/brew_sessions.py:273-277`:

```python
def update_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int, **fields: Any) -> CafeLog | None:
    log_row = db.execute(
        select(CafeLog).where(CafeLog.id == cafe_log_id, CafeLog.user_id == by_user_id)
    ).scalar_one_or_none()
    if log_row is None:
        return None  # router maps to HTTPException(status_code=404)
    ...
```

**Delete pattern** — copy `delete_brew_session` shape from `app/services/brew_sessions.py:317-341` (drop the equipment-counter logic; cafe has no equipment FKs):

```python
def delete_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int) -> bool:
    row = db.execute(
        select(CafeLog).where(CafeLog.id == cafe_log_id, CafeLog.user_id == by_user_id)
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    log.info(CAFE_LOG_DELETED, cafe_log_id=cafe_log_id, user_id=by_user_id)
    return True
```

**List filter pattern** — copy the structure of `list_brew_sessions` at `app/services/brew_sessions.py:356-389` (cafe filters are only `rating_min` / `rating_max` / `date_from` / `date_to` per CONTEXT D-06):

```python
def list_cafe_logs(
    db: Session,
    *,
    by_user_id: int,
    rating_min: Decimal | None = None,
    rating_max: Decimal | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CafeLog]:
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
```

**Project-memory caveats:**
- `structlog.get_logger(__name__)` + `log.info(EVENT_NAME, ...)` at commit success (mirrors `brew_sessions.py:49, :254`). New event names: `CAFE_LOG_CREATED`, `CAFE_LOG_UPDATED`, `CAFE_LOG_DELETED` in `app/events.py` — mirror the `BREW_SESSION_CREATED` / `_UPDATED` / `_DELETED` constants used at `brew_sessions.py:39-43`.
- NO equipment-counter logic (cafe has no equipment FKs); NO `_sync_coffee_flavor_notes` write-back (cafe has no `coffee_id` parent). The cafe service is structurally simpler than the brew service.
- Single commit per write (no nested transactions); `db.flush()` only when an id is needed for an audit event before commit.

---

### 4. `app/routers/cafe_logs.py` (new — router, HTMX form + autocomplete)

**Analog:** `app/routers/brew.py` (full pattern reference)

**Module-level constants** — copy the four constants from `app/routers/brew.py:74-127`:

```python
router = APIRouter(prefix="/cafe-logs")

_LIST_URL = "/brew?tab=cafe"  # post-save destination per CONTEXT D-11

_FORM_FIELDS = {
    "cafe_name", "rating", "roaster_id", "origin_country",
    "brew_method", "flavor_note_ids", "notes", "logged_at",
}

_EMPTY_TO_NONE_FIELDS = {
    "rating", "roaster_id", "origin_country", "brew_method", "logged_at",
}

_INT_FIELDS = {"roaster_id"}

# Form keys autocomplete/chip widgets emit that are NOT schema fields.
_NON_SCHEMA_FORM_KEYS = {
    "X-CSRF-Token",
    "roaster_query",
    "flavor_note_query",
    "origin_country_query",
    "layout",         # Pitfall 2: ?layout=desktop driver field MUST be stripped before Pydantic
    "_method",        # POST + _method=DELETE pattern (HTMX 2.x convention, CLAUDE.md § 3.2)
}
```

**`_parse_form_payload`** — copy verbatim from `app/routers/brew.py:156-200` (renaming the chip-list key from `flavor_note_ids_observed` to `flavor_note_ids`):

```python
# Source: app/routers/brew.py:156-200
def _parse_form_payload(form_data: Any) -> tuple[dict[str, object], dict[str, object]]:
    """Convert raw FormData → (raw_view, schema_input).

    raw_view echoes the user's submission for re-render; schema_input is the
    dict handed to the Pydantic schema. Mass-assignment defense: user_id and
    photo_filename are NEVER read from the form (T-05-16).
    """
    raw_view: dict[str, object] = {}
    schema_input: dict[str, object] = {}
    seen_keys: set[str] = set()
    for key, _ in form_data.multi_items():
        if key in seen_keys: continue
        seen_keys.add(key)
        if key in _NON_SCHEMA_FORM_KEYS: continue
        if key == "flavor_note_ids":
            values = form_data.getlist(key)
            id_strs = [v for v in values if isinstance(v, str) and v != ""]
            raw_view[key] = id_strs
            try:
                schema_input[key] = [int(v) for v in id_strs]
            except (TypeError, ValueError):
                schema_input[key] = [0]  # trips the schema's ge=1 validator
            continue
        value = form_data.get(key)
        raw_view[key] = value
        if isinstance(value, str) and value == "" and key in _EMPTY_TO_NONE_FIELDS:
            schema_input[key] = None
        elif key in _INT_FIELDS and isinstance(value, str) and value:
            try: schema_input[key] = int(value)
            except ValueError: schema_input[key] = value
        else:
            schema_input[key] = value
    return raw_view, schema_input
```

**`_hydrate_form_context` (Phase 15.1 D-21 dual-Edit)** — copy the shape from `app/routers/brew.py:276-356` and the D-21 layout-driven dispatch logic from RESEARCH.md Pattern 12:

```python
# Source: app/routers/brew.py:276-356 (structure) + RESEARCH.md Pattern 12 (D-21 dispatch)
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

    layout="desktop" + edit mode → target #cafe-form-mount innerHTML.
    edit mode without layout → target closest [data-row] outerHTML (mobile inline).
    create mode → target #cafe-form-mount innerHTML.
    """
    is_edit = mode == "edit"
    if layout == "desktop" and is_edit:
        form_target, form_swap = "#cafe-form-mount", "innerHTML"
    elif is_edit:
        form_target, form_swap = "closest [data-row]", "outerHTML"
    else:
        form_target, form_swap = "#cafe-form-mount", "innerHTML"

    return {
        "values": values,
        "errors": errors,
        "mode": mode,
        "cafe_log_id": cafe_log_id,
        "form_action": f"/cafe-logs/{cafe_log_id}" if is_edit else "/cafe-logs",
        "form_target": form_target,
        "form_swap": form_swap,
        "layout": layout,
        # Server-resolved chip seeds + roaster name (rendered pre-Alpine hydration)
        "selected_flavor_notes": _resolve_flavor_notes(db, values.get("flavor_note_ids", [])),
        "roaster_name": _resolve_roaster_name(db, values.get("roaster_id")),
    }
```

**IDOR-404 pattern** — copy from `app/routers/brew.py:864-878, :935-937` (existence non-leak):

```python
@router.get("/{cafe_log_id}/edit", response_class=HTMLResponse)
def edit_cafe_log_form(cafe_log_id: int, request: Request, ...):
    log_row = cafe_logs_service.get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=user.id)
    if log_row is None:
        raise HTTPException(status_code=404)  # 404 not 403 — IDOR existence non-leak
```

**Form-error re-render at HTTP 200** — copy from `app/routers/brew.py:981-1005`:

```python
def _render_form_error(request, db, *, user, raw_view, exc, mode, cafe_log_id=None, layout=None):
    context = _hydrate_form_context(
        db, user=user, values=raw_view,
        errors=_normalize_errors(errors_by_field(exc)),
        mode=mode, cafe_log_id=cafe_log_id, layout=layout,
    )
    return templates.TemplateResponse(
        request=request, name="pages/cafe_log_form.html",
        context=context, status_code=200,  # NOT 422 — HTMX swaps only 2xx
    )
```

**Success redirect** — copy from `app/routers/brew.py:856`:

```python
return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})
```

**Origin-country autocomplete endpoint (NEW pattern, per CONTEXT D-03)** — see RESEARCH.md Pattern 5. Source: distinct `coffee_origins.country` UNION small seeded list. NO `+ Create new` (free text, plain suggestions only).

**Project-memory caveats:**
- Pitfall 2 from RESEARCH.md: `"layout"` MUST be in `_NON_SCHEMA_FORM_KEYS` or Pydantic's `extra="forbid"` rejects the form (project-memory: `tojson-attr-quoting-and-live-browser-repro` and the post-`a3a2f76` D-21 pattern across five entity forms).
- HTMX 2.x: kebab-case `hx-on:event`, no `hx-ws` / `hx-sse` attributes; DELETE as POST + `_method=DELETE` (CLAUDE.md § 3.2).
- Every read/write filters by `request.state.user.id` (via `Depends(require_user)`). Service returns `None` on cross-user; router maps to 404.
- Photo upload: read `UploadFile` from the form, call `photos.process_and_save(raw_bytes)`, pass the resulting filename to the service. Mirror the bag form pattern (`app/routers/bags.py:367-418` per RESEARCH.md citation).

---

### 5. `app/templates/pages/cafe_log_form.html` (new — page template)

**Analog:** `app/templates/pages/brew_form.html` (page-level architecture)

**Page shell + scope nesting** — copy from `app/templates/pages/brew_form.html:1-59`:

```html
{% extends "base.html" %}
{% set is_edit = mode == "edit" %}
{% block page_title %}{% if is_edit %}Edit cafe tasting{% else %}Quick rate a coffee{% endif %}{% endblock %}
{% block content %}
  <main class="mx-auto max-w-2xl px-6 py-12">
    <h1 class="text-2xl font-semibold mb-6">{% if is_edit %}Edit cafe tasting{% else %}Quick rate a coffee{% endif %}</h1>
    ...
  </main>
{% endblock %}
```

Cafe form has NO `brewDraft` scope at v1 (CONTEXT D-11 explicitly rejects autosave). Mount `observedFlavorNotes` (or a rename — see RESEARCH.md "Open Question 1") + `ratingStars` only.

**Sticky-bottom Save bar** — copy verbatim from `app/templates/pages/brew_form.html:285-327`:

```html
{# D-20 pattern: bottom-16 on mobile (above the persistent bottom nav);
   md:bottom-0 on desktop. safe-area-inset-bottom padding clears the iOS home indicator. #}
<div class="sticky bottom-16 md:bottom-0 inset-x-0 z-20 border-t border-espresso-200 bg-cream-50/95 backdrop-blur px-4 py-3 flex flex-col gap-2 dark:bg-espresso-950/95 dark:border-espresso-800"
     style="padding-bottom: calc(0.75rem + env(safe-area-inset-bottom))">
  <div class="flex items-center gap-3">
    <a href="/brew?tab=cafe"
       class="flex-1 inline-flex items-center justify-center rounded border border-espresso-300 px-4 py-2 text-base text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200">Cancel</a>
    <button type="submit"
            class="flex-1 inline-flex items-center justify-center rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800">
      {% if is_edit %}Save changes{% else %}Save{% endif %}
    </button>
  </div>
</div>
```

**Autocomplete chip widget (`|tojson` attr-quoting Pitfall 5 / project-memory)** — copy from `app/templates/fragments/coffee_form.html:179-184`:

```html
{# data-initial-chips MUST use SINGLE quotes — |tojson emits double-quoted strings inside the JSON;
   double-quoting the attr breaks HTML parsing (project memory: tojson-attr-quoting-and-live-browser-repro). #}
<div id="cafe-flavor-chips"
     class="field flavor-note-chips-field flex flex-col gap-1"
     x-data="observedFlavorNotes"
     data-initial-chips='{{ selected_flavor_notes|tojson }}'>
  ...
</div>
```

**Roaster autocomplete field** — copy from `app/templates/fragments/coffee_form.html:83-112`:

```html
<div class="field flex flex-col gap-1"
     x-data="autocomplete"
     data-entity-key="roaster"
     data-hidden-input-name="roaster_id"
     data-initial-id="{{ values.get('roaster_id') or '' }}"
     data-initial-name="{{ roaster_name or '' }}">
  <input type="text" name="roaster_query" :value="query"
         hx-get="/roasters/list"
         hx-trigger="input changed delay:350ms[target.value.length >= 2], focus once from:closest .field"
         hx-target="#roaster-dropdown" hx-swap="innerHTML"
         ...>
  <input type="hidden" name="roaster_id" :value="selectedId">
  <div id="roaster-dropdown" x-show="open" class="absolute top-full left-0 right-0 z-10 mt-1"></div>
</div>
```

**Project-memory caveats:**
- Tailwind v3 (NOT v4): `darkMode:'selector'`, `.dark` selectors, never `@custom-variant` (project memory: `tailwind-v3-not-v4`).
- CSP nonce-strict: any new class must compile via `tailwind.src.css`; no inline `<style>` blocks, no `style=` attrs except the numeric width/height + the `padding-bottom: calc(... + env(safe-area-inset-bottom))` precedent established here (mirrors `_cold_start.html` precedent of inline `style="width: {{ pct }}%"`).
- `|tojson` MUST be inside single-quoted attrs (Pitfall 5). Double-quoting breaks HTML parsing.
- The `.htmx-indicator` class is NOT auto-styled — define it explicitly in `tailwind.src.css` if used (project memory: `strict-csp-blocks-htmx-indicator`). Phase 9 already shipped a rule; verify before adding.
- Autofocus the coffee-name input: `autofocus` attribute + a belt-and-suspenders Alpine `$el.focus()` on `init()` (UI-SPEC §"Form field — required + autofocus").
- CSRF hidden input: `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">` (mirrors every state-changing form).

---

### 6. `app/templates/fragments/cafe_log_card.html` (new — mobile-card fragment)

**Analog:** `app/templates/fragments/coffee_row.html` mode="card" branch (l. 23-99) — for D-21 dual Edit button, `pr-24` gutter, `data-row` + `id="cafe-log-{{ log.id }}"`, top-right button cluster pattern.

**Border-l-2 amber + cup icon** — UI-SPEC §"Visual Distinction Spec — D-07 expanded". The only deviation from `coffee_row.html` mode="card" is the outer class set:

```html
<div id="cafe-log-{{ log.id }}"
     data-row
     class="relative rounded-lg border border-espresso-200 border-l-2 border-l-amber-500 bg-cream-100 p-4 pr-24 dark:bg-espresso-900 dark:border-espresso-800 dark:border-l-amber-400">
  {# Heroicons "Coffee" outline path — aria-label for SR discoverability (UI-SPEC §Accessibility) #}
  <svg xmlns="http://www.w3.org/2000/svg"
       class="absolute top-3 left-3 w-4 h-4 text-amber-600 dark:text-amber-400"
       fill="none" viewBox="0 0 24 24" stroke="currentColor"
       aria-label="Cafe tasting">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M3 8h13v6a4 4 0 01-4 4H7a4 4 0 01-4-4V8zm13 1h2a2 2 0 010 4h-2"/>
  </svg>
  ...
</div>
```

**Dual Edit button (D-21)** — copy verbatim from `app/templates/fragments/coffee_row.html:30-46`, swapping route paths:

```html
<div class="absolute top-3 right-3 flex gap-1">
  {# mobile: post-a3a2f76 inline pattern, hidden at md+ #}
  <button type="button"
          hx-get="/cafe-logs/{{ log.id }}/edit"
          hx-target="closest [data-row]"
          hx-swap="outerHTML"
          class="md:hidden inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
    Edit
  </button>
  {# desktop: Phase 15.1 D-21 pattern, hidden at <md #}
  <button type="button"
          hx-get="/cafe-logs/{{ log.id }}/edit?layout=desktop"
          hx-target="#cafe-form-mount"
          hx-swap="innerHTML"
          class="hidden md:inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
    Edit
  </button>
  {# Delete via POST + _method=DELETE + hx-confirm (HTMX 2.x convention, CLAUDE.md § 3.2) #}
  <form hx-post="/cafe-logs/{{ log.id }}"
        hx-target="closest [data-row]"
        hx-swap="outerHTML"
        hx-confirm="Delete this cafe tasting? This cannot be undone."
        class="inline">
    <input type="hidden" name="_method" value="DELETE">
    <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
    <button type="submit"
            class="inline-flex items-center justify-center rounded border border-espresso-300 px-2 py-1 text-sm text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px] min-w-[44px]">
      Delete
    </button>
  </form>
</div>
```

**Flavor pill render (up to 3 + "+N more")** — copy from `app/templates/fragments/coffee_row.html:83-98` verbatim, renaming `coffee.advertised_flavor_note_ids` → `log.flavor_note_ids`.

**Project-memory caveats:**
- Tailwind v3 `.dark` selectors (NOT `@custom-variant`).
- Touch-target floor: `min-h-[44px] min-w-[44px]` on every tappable control on mobile (Apple HIG / WCAG 2.5.5).
- `aria-label="Cafe tasting"` on the cup SVG (UI-SPEC §Accessibility); the star glyph stays `aria-hidden="true"`.

---

### 7. `app/templates/fragments/cafe_log_row.html` (new — desktop-table row)

**Analog:** `app/templates/fragments/coffee_row.html` mode="row" branch (l. 100-184) — including the OOB clear pattern at the very end of the file (l. 175-183).

**`<tr>` shape + accent** — UI-SPEC §"Visual Distinction Spec — D-07 expanded" leaves the accent technique to the planner (`border-l-2 border-l-amber-500` on the `<tr>` OR a thin `w-1 bg-amber-500` leading column). Pick the `<tr>`-class approach for parity with the mobile card:

```html
<tr id="cafe-log-{{ log.id }}" data-row
    {% if include_desktop_oob %}hx-swap-oob="outerHTML"{% endif %}
    class="border-b border-espresso-100 border-l-2 border-l-amber-500 dark:border-l-amber-400">
  <td class="py-2">{{ log.logged_at_local|...|date_filter }}</td>
  <td class="py-2"><a href="..." class="hover:underline">{{ log.cafe_name }}</a></td>
  <td class="py-2">{{ log.rating or "—" }}</td>
  <td class="py-2">{{ roaster_name or "—" }}</td>
  <td class="py-2">{{ log.origin_country or "—" }}</td>
  <td class="py-2 text-right">
    {# Dual Edit button — copy verbatim from coffee_row.html:147-161 #}
  </td>
</tr>
```

**OOB clear pattern (D-21)** — copy from `app/templates/fragments/coffee_row.html:175-183`:

```html
{% if include_oob_form_clear %}
  {# 04-RESEARCH Pattern 2: clear the form mount on successful create. #}
  <div id="cafe-form-mount" hx-swap-oob="innerHTML"></div>
{% endif %}
{% if include_desktop_oob %}
  {# D-21: desktop edit success — row already has hx-swap-oob="outerHTML" above;
     clear the form mount as the second OOB element. #}
  <div id="cafe-form-mount" hx-swap-oob="innerHTML"></div>
{% endif %}
```

---

### 8. `app/templates/fragments/cafe_log_list.html` (new — HTMX swap target)

**Analog:** `app/templates/fragments/session_list.html` (complete shape: md+ table, <md cards, empty branches)

**Outer wrapper id="session-list"** — copy from `app/templates/fragments/session_list.html:15`. This lets the existing filter-bar `hx-target="#session-list"` cover both tabs without code change in `sessions.html` beyond conditional rendering:

```html
<div id="session-list">
  {% if rows %}
    <div class="hidden md:block">
      <table class="w-full text-base">
        <thead>
          <tr class="text-sm font-semibold border-b border-espresso-200 dark:border-espresso-800">
            <th class="text-left py-2">Date</th>
            <th class="text-left py-2">Coffee name</th>
            <th class="text-left py-2">Rating</th>
            <th class="text-left py-2">Roaster</th>
            <th class="text-left py-2">Origin</th>
            <th class="text-right py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for row in rows %}
            {% with mode = "row" %}
              {% include "fragments/cafe_log_row.html" %}
            {% endwith %}
          {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="md:hidden space-y-3">
      {% for row in rows %}
        {% with mode = "card" %}
          {% include "fragments/cafe_log_card.html" %}
        {% endwith %}
      {% endfor %}
    </div>
  {% elif active_filter_count %}
    {# Filtered-zero — mirror session_list.html:46-62 structure but with cafe copy. #}
    <div class="flex flex-col items-center justify-center text-center py-16 gap-3">
      <h2 class="text-lg font-semibold">No cafe tastings match these filters.</h2>
      <p class="text-base text-espresso-700 dark:text-cream-200">Try widening the rating or date range.</p>
      <a href="/brew?tab=cafe"
         class="rounded border border-espresso-300 px-4 py-2 text-base text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900">
        Clear filters
      </a>
    </div>
  {% else %}
    {# D-08 LOCKED: truly empty Cafe tastings tab renders BLANK.
       Do NOT add a heading, body, or CTA — explicit divergence from session_list.html:64-71. #}
  {% endif %}
</div>
```

**Project-memory caveats:**
- D-08 LOCKED — blank empty state. A future contributor must NOT add a "log your first tasting" CTA without re-opening the decision.

---

### 9. `app/migrations/versions/p16_cafe_logs.py` (new — DDL)

**Analog:** `app/migrations/versions/p5_brew_sessions.py` (the canonical template; GIN + DESC B-tree via op.execute) + `app/migrations/versions/p15_1_multi_origin.py` (sibling-table reference for shape + Alembic-safe convention)

**Alembic-safe convention** — copy the docstring + import block from `app/migrations/versions/p5_brew_sessions.py:34-50`:

```python
"""
Alembic-safe convention (mirrors p4_shared_catalog.py): this migration body
does NOT import from app.models. Schema is described inline with sa.Column /
sa.ForeignKey. A future model rename does not invalidate this migration.
"""

from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p16_cafe_logs"
# IMPORTANT: Phase 15.1 introduced four migrations. Current head is
# p15_1_varietal_m2m. VERIFY with `docker compose exec coffee-snobbery alembic heads`
# BEFORE finalizing this value (Pitfall 4 from RESEARCH.md).
down_revision: str | Sequence[str] | None = "p15_1_varietal_m2m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**Table create + ARRAY column** — copy the shape from `app/migrations/versions/p5_brew_sessions.py:68-151` (drop the brew-specific columns; keep the cafe set per RESEARCH.md Pattern 2):

```python
op.create_table(
    "cafe_logs",
    sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
    sa.Column("user_id", sa.BigInteger,
              sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("roaster_id", sa.BigInteger,
              sa.ForeignKey("roasters.id", ondelete="SET NULL"), nullable=True),
    sa.Column("cafe_name", sa.Text, nullable=False),
    sa.Column("origin_country", sa.Text, nullable=True),
    sa.Column("brew_method", sa.Text, nullable=True),
    sa.Column("rating", sa.Numeric(3, 2), nullable=True),
    sa.Column("flavor_note_ids", postgresql.ARRAY(sa.BigInteger),
              nullable=False, server_default=sa.text("'{}'::bigint[]")),
    sa.Column("notes", sa.Text, nullable=False, server_default=""),
    sa.Column("photo_filename", sa.Text, nullable=True),
    sa.Column("logged_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
)
```

**GIN + DESC B-tree via op.execute** — copy the raw-SQL idioms from `app/migrations/versions/p5_brew_sessions.py:160-171`:

```python
# B-tree (DESC) — raw SQL to carry the sort direction reliably.
op.execute(
    "CREATE INDEX ix_cafe_logs_user_logged_at ON cafe_logs (user_id, logged_at DESC)"
)
# GIN — hand-edited (Pitfall 1: autogenerate cannot emit USING GIN).
op.execute(
    "CREATE INDEX ix_cafe_logs_flavor_note_ids "
    "ON cafe_logs USING GIN (flavor_note_ids)"
)
```

**Downgrade ordering** — copy from `app/migrations/versions/p5_brew_sessions.py:207-219` (DROP INDEX IF EXISTS before DROP TABLE):

```python
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_flavor_note_ids")
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_user_logged_at")
    op.drop_table("cafe_logs")
```

**Project-memory caveats:**
- Pitfall 1 (RESEARCH.md): Alembic autogenerate CANNOT emit `USING GIN` — hand-edit. Verify with `\d cafe_logs` post-migration.
- Pitfall 4 (RESEARCH.md): `down_revision` MUST point to current head (`p15_1_varietal_m2m` per repo state). Run `alembic heads` before pinning.
- Alembic-safe convention: no `from app.models import ...` in the migration body. Schema declared inline with `sa.Column` / `sa.ForeignKey`.

---

### 10. `tests/services/test_cafe_logs.py` (new — service-layer tests)

**Analog:** `tests/services/test_brew_sessions_service.py` (full structural shape) + `tests/services/test_analytics.py` (skip-gate pattern, `_seed_analytics_scenario` helper for analytics)

**Skip gates** — copy verbatim from `tests/services/test_analytics.py:24-49` (the `_require_postgres` + `_require_analytics_tables` helpers). Add a new gate:

```python
def _require_cafe_logs_table() -> None:
    """Skip if the cafe_logs table is not present (Pitfall 6 — tests-pass-by-skip-mask-green).

    Without this gate the suite silently skips every cafe assertion when the
    p16_cafe_logs migration has not run. Project memory:
    tests-pass-by-skip-mask-green. Run pytest with `-rs` during gsd-validate-phase
    to surface every skip.
    """
    try:
        from sqlalchemy import text
        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.cafe_logs')")).scalar()
    except Exception as exc:
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("cafe_logs table not present — migration p16_cafe_logs not applied")
```

**Test obligations** — RESEARCH.md Pattern 9 lists the signature-determinism cases. Mirror the existing analytics tests' signature-mutation pattern. Specific cafe-related tests to add to **`tests/services/test_analytics.py`** rather than fork:
- empty-user → `_EMPTY_SIGNATURE` (unchanged).
- brew-only user signature change due to new payload shape `[brew_list, cafe_list]` (Pitfall 9 — accept one-time AI regen).
- adding a rated cafe log → signature changes.
- editing a cafe log's rating → signature changes.
- deleting a cafe log → signature changes.
- adding an UNRATED cafe log → signature unchanged (rating IS NOT NULL filter).
- per-user scoping (no cross-user cross-contamination).
- D-13 preference profile origin + roaster UNION rows surface.
- D-13 `get_flavor_descriptors` UNION counts notes from both arrays.
- D-15 cold-start gate combines brew + cafe counts.
- `test_sweep_orphans_keeps_cafe_photos` (Pitfall 8 — extends `tests/services/test_photos.py` or sits in test_cafe_logs.py).

**Project-memory caveats:**
- Pitfall 6 (RESEARCH.md, project memory `tests-pass-by-skip-mask-green`): skip-gates can silently mask failures. Run `pytest -rs` in validate-phase.
- Pitfall 9 (RESEARCH.md): signature shape change forces a one-time AI regen for every user — the test must accept this and document it.

---

### 11. `tests/routers/test_cafe_logs.py` (new — router tests)

**Analog:** `tests/routers/test_brew_router.py` (mirror its `TestClient` + login + form-post pattern)

Required coverage:
- GET `/cafe-logs/new` renders the form (autofocus + CSRF input present).
- POST `/cafe-logs` with valid payload → 204 + `HX-Redirect: /brew?tab=cafe`.
- POST `/cafe-logs` with missing `cafe_name` → 200 + form re-render with `errors.cafe_name`.
- GET `/cafe-logs/{id}/edit` cross-user → 404 (existence non-leak).
- POST `/cafe-logs/{id}` cross-user → 404.
- POST `/cafe-logs/{id}` with `_method=DELETE` + `hx-confirm` confirmation → 204 + row OOB swap.
- `?layout=desktop` returns the form fragment (innerHTML target = `#cafe-form-mount`, no `extends "base.html"`).
- Origin-country autocomplete endpoint returns merged distinct values + seeded list.
- Tab routing: `/brew?tab=cafe` HX-Request → `fragments/cafe_log_list.html`; non-HX → `pages/sessions.html` with `active_tab="cafe"`.

---

## Shared Patterns (cross-cutting)

### Authentication / per-user scoping
**Source:** `app/dependencies/auth.py` + `app/routers/brew.py:480-484, :874-878`
**Apply to:** Every cafe_logs router endpoint
```python
@router.get(...)
def handler(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    # cross-user reads → service returns None → router raises HTTPException(status_code=404)
    row = cafe_logs_service.get_cafe_log(db, cafe_log_id=id, by_user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404)  # existence non-leak (404 not 403)
```

### CSRF on state-changing forms
**Source:** every form template; e.g. `app/templates/fragments/coffee_row.html:65` (the form-level hidden input is in the form templates, not the row, but the pattern is identical).
**Apply to:** `cafe_log_form.html` + the Delete `<form>` inside `cafe_log_card.html` / `cafe_log_row.html`
```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

### Error handling — Pydantic ValidationError → HTTP 200 + form re-render
**Source:** `app/routers/brew.py:981-1005` (`_render_form_error`) + `app/routers/brew.py:138-153` (`_normalize_errors`)
**Apply to:** `create_cafe_log` + `update_cafe_log` POST handlers
```python
try:
    form = CafeLogCreate(**schema_input)
except ValidationError as exc:
    return _render_form_error(
        request, db, user=user, raw_view=raw_view, exc=exc,
        mode="create",   # or "edit"
        cafe_log_id=cafe_log_id_if_edit,
        layout=qp.get("layout"),
    )
# success path:
return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})
```

### Structured logging — audit events on commit
**Source:** `app/services/brew_sessions.py:49, :254, :313, :340` + `app/events.py` constants
**Apply to:** `cafe_logs.py` service create / update / delete
```python
import structlog
log = structlog.get_logger(__name__)
# at the end of create/update/delete after db.commit():
log.info(CAFE_LOG_CREATED, cafe_log_id=row.id, user_id=by_user_id)
```
Note: CONTEXT.md "Claude's discretion" recommends NO audit-log entry (cafe log churn is user-content noise, not auth/admin). The planner picks; if no audit, drop the structlog calls entirely.

### Photo upload — single call into the existing pipeline
**Source:** `app/services/photos.py:170-256` (`process_and_save`) + `app/routers/bags.py:367-418` (the upload pattern)
**Apply to:** `cafe_logs.py` router POST handlers (create + update)
- Read `UploadFile` from `await request.form()`.
- Pass raw bytes to `photos.process_and_save()`.
- Store the returned filename in `cafe_logs.photo_filename`.
- The Pillow pipeline (magic-byte check, EXIF strip, thumbnail, re-encode) is reused VERBATIM — never call `PIL.Image` directly from the cafe_logs router or service.

### Photo orphan sweep — EXTEND, do not branch
**Source:** `app/services/photos.py:382-389`
**Apply to:** `app/services/photos.py:sweep_orphans` ONLY
```python
# CURRENT (l. 383-386):
from app.models.bag import Bag
rows = db.execute(select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))).all()
referenced_main: set[str] = {fn for (fn,) in rows if fn is not None}

# MODIFIED (Pattern 6 + Pitfall 8):
from app.models.bag import Bag
from app.models.cafe_log import CafeLog  # NEW lazy-import
bag_rows = db.execute(select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))).all()
cafe_rows = db.execute(select(CafeLog.photo_filename).where(CafeLog.photo_filename.isnot(None))).all()
referenced_main: set[str] = {fn for (fn,) in bag_rows if fn is not None}
referenced_main |= {fn for (fn,) in cafe_rows if fn is not None}
```
**Pitfall 8 from RESEARCH.md is the load-bearing memory:** if the planner forgets to extend `sweep_orphans`, the nightly sweep silently deletes every cafe photo. Mandatory test: `test_sweep_orphans_keeps_cafe_photos`.

---

## Modified-file pattern assignments

### `app/services/analytics.py` (modify 5 functions)

**Analog (in-file):** existing brew-only blocks within the same functions.

**`compute_input_signature` (l. 353)** — see RESEARCH.md Pattern 9. Append a second SELECT + payload sublist. Payload shape MUST become `[brew_list, cafe_list]` (a list of two lists, NOT a flat concatenation — Pitfall 3 row-identity-collision defense + Pitfall 9 one-time AI regen accepted). Anchor on the existing `_serialize_row` lambda at l. 388-395.

**`get_preference_profile` (l. 78)** — see RESEARCH.md Pattern 10. Per-dimension UNION subquery (`.union_all(...).subquery()`), then aggregate over the subquery. Origin + roaster dims UNION cafe; process + roast_level stay brew-only (cafe form doesn't capture them — CONTEXT D-13). Anchor on the existing roaster_stmt + origin_stmt at l. 107-143.

**`get_flavor_descriptors` (l. 158)** — see RESEARCH.md Pattern 10 second snippet. Extend the raw SQL `unnest()` block with a `UNION ALL` of two `unnest` blocks (brew + cafe), both filtered to `rating >= 4.0`. Anchor on the existing `text("...")` body at l. 169-182. Bound `:user_id` parameter stays.

**`get_cold_start_counts` (l. 309)** — see RESEARCH.md Pattern 11. Add `cafe_count` scalar count; combine `total = brew_count + cafe_count` for the `gate_open` math; merge raw SQL `UNION ALL` of two `unnest` blocks for distinct-notes-across-both. Dict keys `sessions` / `distinct_notes` / `gate_open` / `sessions_needed` / `notes_needed` MUST stay the same shape (the cold-start template at `_cold_start.html` reads them by those names — non-breaking).

**`get_top_coffees` (l. 47)** — one-line comment per CONTEXT D-14:
```python
# CAFE-04 not applicable: cafe coffees have no row in coffees table by design (D-14).
```

**`get_sweet_spots` (l. 191)** — one-line comment per CONTEXT D-16:
```python
# Cafe logs are intentionally excluded — they have no brew-parameter fields (CAFE-05 / D-16).
```

**Project-memory caveats:**
- Deterministic ordering for signature: cafe rows ordered by `CafeLog.id` ASC within the cafe sublist (analytics module's existing pitfall — order matters for SHA256 stability).
- NULL-rating filter: `CafeLog.rating.is_not(None)` (mirrors `BrewSession.rating.is_not(None)` everywhere in analytics.py).
- Bound `:user_id` parameter on every raw SQL (T-06-03 SQLi defense).

---

### `app/services/photos.py` (modify `sweep_orphans` only)

See "Shared Patterns — Photo orphan sweep" above. Single block at l. 382-389 is the only change; the rest of `photos.py` stays untouched.

---

### `app/routers/brew.py` (modify `list_sessions` at l. 479)

**Analog (in-file):** existing `_parse_list_filters` + `_raw_filters` helpers (l. 409-429).

Branch the existing `list_sessions` handler on `?tab=cafe` per RESEARCH.md Pattern 7. When `tab == "cafe"`, parse the cafe-only filter set (rating + date only — CONTEXT D-06), call `cafe_logs_service.list_cafe_logs(...)`, render `fragments/cafe_log_list.html` (HTMX) or `pages/sessions.html` with `active_tab="cafe"` (full page).

```python
qp = request.query_params
tab = qp.get("tab", "brew")
if tab == "cafe":
    cafe_filters = _parse_cafe_list_filters(qp)  # rating_min/max + date_from/to
    cafe_rows = cafe_logs_service.list_cafe_logs(db, by_user_id=user.id, **cafe_filters)
    context = {
        "active_tab": "cafe",
        "rows": cafe_rows,
        "filters": _raw_cafe_filters(qp),
        "active_filter_count": sum(1 for v in _raw_cafe_filters(qp).values() if v),
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request, name="fragments/cafe_log_list.html",
            context={**context, "is_fragment": True},
        )
    return templates.TemplateResponse(
        request=request, name="pages/sessions.html",
        context=context,
    )
# existing brew tab logic unchanged
```

**Project-memory caveats:**
- Tab routing is **server-side** `?tab=` + `hx-get` + `hx-push-url` (NOT Alpine.js client-side swap). CSP-clean, back/forward-correct. Pattern 7 in RESEARCH.md is the load-bearing source.
- Tab-scoped filters: cafe tab MUST NOT echo brew filter query params back onto the cafe filter form (Open Question 4 in UI-SPEC.md). Document this in the handler.

---

### `app/templates/pages/sessions.html` (modify — header + tab toggle + cafe filter variant)

**Analog (in-file):** existing flex-wrap header at l. 13-88.

**Three changes:**

1. **Third "Quick rate" button** — insert after the "Log session" anchor at l. 24-27. Use identical Tailwind utility set (UI-SPEC §"Component Inventory"):
```html
<a href="/cafe-logs/new"
   class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
  Quick rate
</a>
```

2. **Tab toggle `<nav>`** — insert above `{% include "fragments/session_list.html" %}` at l. 90. Two anchors with `hx-get` + `hx-push-url` + `hx-target="#session-list"`; active tab gets a colored `border-b-2` (UI-SPEC §"Color" reserves espresso-700 for the Sessions tab + amber-500 for the Cafe tastings tab).
```html
<nav class="flex border-b border-espresso-200 dark:border-espresso-800 mb-4">
  <a href="/brew?tab=brew" hx-get="/brew?tab=brew" hx-push-url="true"
     hx-target="#session-list" hx-swap="outerHTML"
     {% if active_tab != 'cafe' %}aria-current="page"{% endif %}
     class="px-4 py-2 text-base {% if active_tab != 'cafe' %}border-b-2 border-espresso-700 font-semibold{% else %}text-espresso-600 dark:text-cream-300{% endif %}">
    Sessions
  </a>
  <a href="/brew?tab=cafe" hx-get="/brew?tab=cafe" hx-push-url="true"
     hx-target="#session-list" hx-swap="outerHTML"
     {% if active_tab == 'cafe' %}aria-current="page"{% endif %}
     class="px-4 py-2 text-base {% if active_tab == 'cafe' %}border-b-2 border-amber-500 font-semibold{% else %}text-espresso-600 dark:text-cream-300{% endif %}">
    Cafe tastings
  </a>
</nav>
```

3. **Desktop edit mount + tab-scoped include** — add `<div id="cafe-form-mount" class="hidden md:block"></div>` above the tab content, and branch the include on `active_tab`:
```html
<div id="cafe-form-mount" class="hidden md:block"></div>
{% if active_tab == 'cafe' %}
  {% include "fragments/cafe_log_list.html" %}
{% else %}
  {% include "fragments/session_list.html" %}
{% endif %}
```

The filter `<details>` block at l. 30-86 should be branched per tab: cafe tab renders only rating + date inputs (UI-SPEC §"Component Inventory" — "When `active_tab == 'cafe'`, the filter form contains ONLY: `rating_min` + `rating_max` + `date_from` + `date_to`").

**Project-memory caveats:**
- Tailwind v3 + `.dark` selectors.
- Brew-tab `#brew-form-mount` does NOT exist (brew uses dedicated `/brew/new` page — no mid-page edit pattern). The `#cafe-form-mount` is cafe-only (UI-SPEC Open Question 3).

---

### `app/templates/fragments/home/_cold_start.html` (modify — math input only)

**Analog (in-file):** the existing copy at l. 30-39.

`get_cold_start_counts` (RESEARCH.md Pattern 11) preserves the dict-key contract — `gate.sessions` becomes the combined `(brew_count + cafe_count)`, `gate.distinct_notes` becomes the distinct count across both arrays. The template SHOULD render correctly with NO markup changes. UI-SPEC §"Cold-start meter (D-15)" recommends keeping "brews" wording for v1.2 (slight imprecision; revisit if usage shows confusion). Phase 16 ships zero edits to this file UNLESS the planner picks the alternative copy wording.

---

### `app/main.py` (modify — register router)

**Analog (in-file):** the existing `app.include_router(...)` line for `brew_router`.

```python
from app.routers import cafe_logs as cafe_logs_router
app.include_router(cafe_logs_router.router)
```

---

## Anti-Patterns (DO NOT propagate from analogs)

Reproduced from RESEARCH.md "Anti-Patterns to Avoid" + spotted while pattern-mapping:

- Do **NOT** add `coffee_id` FK to `cafe_logs` (CONTEXT D-01).
- Do **NOT** introduce `is_cafe_log` or `session_type` on `brew_sessions` (D-01).
- Do **NOT** add a `cafe_drafts` table (D-11 — no autosave at v1).
- Do **NOT** constrain `brew_method` with ENUM/CHECK (D-05).
- Do **NOT** add a `countries` lookup table (D-03 — plain TEXT with autocomplete suggestions).
- Do **NOT** UNION cafe data into `get_sweet_spots` or `get_top_coffees` (D-14 + D-16).
- Do **NOT** use Alpine.js client-side tab swap (CSP + back/forward correctness — Pattern 7).
- Do **NOT** rely on htmx's auto-injected `.htmx-indicator` style under strict CSP (project memory; define the rule in `tailwind.src.css`).
- Do **NOT** forget to extend `photos.sweep_orphans` to reference `cafe_logs.photo_filename` (Pitfall 8 — silent data loss).
- Do **NOT** flatten the brew + cafe rows into one signature list (Pitfall 3 — row-identity collision).

---

## Metadata

**Analog search scope:**
- `app/models/` — brew_session.py (primary), coffee.py, coffee_origin.py
- `app/schemas/` — brew_session.py
- `app/services/` — brew_sessions.py, analytics.py, photos.py
- `app/routers/` — brew.py (primary), bags.py (photo upload), coffees.py (_hydrate_form_context historical reference)
- `app/templates/pages/` — brew_form.html, sessions.html
- `app/templates/fragments/` — coffee_row.html (D-21 reference), session_list.html, coffee_form.html (autocomplete + chip), autocomplete_list.html, home/_cold_start.html
- `app/migrations/versions/` — p5_brew_sessions.py (primary template), p15_1_multi_origin.py (sibling-table reference), p4_shared_catalog.py (GIN precedent — referenced)
- `tests/services/` — test_analytics.py (skip-gate), test_brew_sessions_service.py (CRUD test shape)
- `tests/routers/` — test_brew_router.py

**Files scanned:** 26 (read; multiple targeted reads on brew_form.html and brew.py for non-overlapping sections).

**Coverage:**
- Files with exact analog: 8 (model, schema, service, router, page template, desktop row, list fragment, migration)
- Files with role-match analog: 3 (cafe card lifts mobile-card patterns from two analogs; tests; modified analytics functions)
- Files with no analog: 0 — every Phase 16 file has a direct precedent in the repo

**Pattern extraction date:** 2026-05-27

---

## PATTERN MAPPING COMPLETE

**Phase:** 16 - Cafe Quick-Rate
**Files classified:** 24 (10 new + 14 modified/extended)
**Analogs found:** 24 / 24

### Coverage
- Files with exact analog: 21
- Files with role-match analog: 3
- Files with no analog: 0

### Key Patterns Identified
- **Mirror the brew vertical slice verbatim:** every new file (model, schema, service, router, three templates, migration, two test files) maps 1:1 to its `brew_sessions` counterpart with surgical divergences locked by D-01..D-16.
- **Compose existing primitives, never re-roll:** photo pipeline (`photos.process_and_save`), roaster autocomplete (`/roasters/list`), flavor-note chip widget (`flavorNoteChips` / `observedFlavorNotes` Alpine scope), Phase 15.1 D-21 dual Edit button, Phase 4 filter-bar tab pattern. The only net-new endpoint is `/cafe-logs/origin-country-autocomplete` (free-text suggestions, no `+ Create new`).
- **Two load-bearing project-memory caveats per file type:** Tailwind v3 + `.dark` (templates), ARRAY+GIN hand-edit via `op.execute` (migration), `|tojson` single-quoted attrs (chip widgets), `_NON_SCHEMA_FORM_KEYS` must include `"layout"` (routers), strict-CSP htmx-indicator (form spinners), tests-pass-by-skip-mask-green requires `_require_cafe_logs_table()`.
- **Analytics integration is the only non-trivial cross-cutting work:** SHA256 payload shape becomes `[brew_list, cafe_list]` (Pitfall 9 — one-time AI regen accepted); origin + roaster + flavor_descriptors UNION cafe (D-13); sweet-spots + top-coffees stay brew-only with one-line guard comments (D-14, D-16); cold-start gate combines brew + cafe counts (D-15).
- **Photo orphan sweep is the highest-risk silent-data-loss landmine** (Pitfall 8): `photos.sweep_orphans` MUST be extended to UNION `cafe_logs.photo_filename` or every cafe photo disappears overnight. Mandatory test: `test_sweep_orphans_keeps_cafe_photos`.

### File Created
`C:\Claude\Coffee-Snobbery\.planning\phases\16-cafe-quick-rate\16-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog file + line ranges + concrete excerpts in every plan slice (16-01 through 16-05 per the wave structure in RESEARCH.md § "Decision-to-Plan-Slice Mapping").
