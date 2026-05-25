# Phase 10: Global Search — Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 7 (5 new + 2 modified)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/search.py` | service | CRUD (read-only, multi-entity) | `app/services/analytics.py` | exact — same sync `select()` pattern, same per-user IDOR guard, same `Session` signature |
| `app/routers/search.py` | router | request-response (GET fragment) | `app/routers/roasters.py` `roaster_autocomplete()` (lines 417-449) | exact — GET-only HTMX fragment, `require_user`, empty-200 short-circuit, `templates.TemplateResponse` |
| `app/templates/fragments/search_results.html` | template (fragment) | request-response | `app/templates/fragments/autocomplete_list.html` | exact — grouped live-results, autoescape-safe highlight, `min-h-[44px]` rows, same color tokens |
| `app/static/js/alpine-components/search-bar.js` | frontend component | event-driven | `app/static/js/alpine-components/mini-modal.js` | exact — `Alpine.data()` CSP factory, ESC handler, `init()`/`destroy()` lifecycle, `window.addEventListener` |
| `app/migrations/versions/p10_search_indexes.py` | migration | batch (DDL) | `app/migrations/versions/p4_shared_catalog.py` lines 174-178 + 279 | exact — `op.execute("CREATE INDEX ... USING GIN ...")` + `op.execute("DROP INDEX IF EXISTS ...")` |
| `app/templates/base.html` (MODIFIED) | template (layout) | request-response | `app/templates/pages/home.html` lines 13-14 (`request.state.user` gate) + `app/templates/base.html` lines 17-25 (script registration) | exact — auth gate + `<script defer nonce="{{ csp_nonce(request) }}">` before `@alpinejs/csp` core |
| `app/main.py` (MODIFIED) | config | request-response | `app/main.py` lines 84-99 + 229-241 (router import + `app.include_router(...)`) | exact — same import alias + `include_router` call pattern |

---

## Pattern Assignments

### `app/services/search.py` (service, read-only CRUD)

**Analog:** `app/services/analytics.py`

**Imports pattern** (analytics.py lines 17-35):
```python
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.recipe import Recipe
from app.models.roaster import Roaster

log = structlog.get_logger(__name__)
```
For `search.py`, swap in `markupsafe` and all six model imports; keep the `from __future__ import annotations` header and the `structlog` logger.

**Per-user IDOR defense pattern** (analytics.py lines 7-9 docstring + lines 54, 94-95 first WHERE):
```python
# Per-user scoping (T-06-01 IDOR defense): the first WHERE clause on every query
# is BrewSession.user_id == user_id. user_id is always a typed function arg,
# never a global or request param.
.where(
    BrewSession.user_id == user_id,   # ALWAYS first
    ...
)
```
The brew-note query in `search.py` must follow this exact convention: `user_id` is a function parameter, the `user_id == :id` clause is **first** in `.where()`.

**Core select() pattern** (analytics.py lines 53-70):
```python
def get_top_coffees(db: Session, user_id: int) -> list[Row]:
    stmt = (
        select(
            Coffee.id,
            Coffee.name,
            func.avg(BrewSession.rating).label("avg_rating"),
            ...
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .order_by(func.avg(BrewSession.rating).desc())
        .limit(5)
    )
    return db.execute(stmt).all()
```
Each per-entity search function follows the same shape: `select(...)`, `.join(...)` (when needed), `.where(...)`, `.order_by(func.similarity(...).desc())`, `.limit(6)` (fetch 6; show 5; 6th triggers "+N more").

**JOIN pattern for context columns** (analytics.py lines 107-121 — roaster dimension):
```python
roaster_stmt = (
    select(
        Roaster.name.label("label"),
        ...
    )
    .join(Coffee, BrewSession.coffee_id == Coffee.id)
    .join(Roaster, Coffee.roaster_id == Roaster.id)
    .where(BrewSession.user_id == user_id, ...)
)
```
The coffees query in `search.py` needs an `.outerjoin(Roaster, Coffee.roaster_id == Roaster.id)` to fetch `roaster_name` for D-05 context display.

**Raw SQL fallback pattern** (analytics.py lines 148-162):
```python
stmt = text("""
    SELECT fn.id, fn.name, count(*) AS session_count
    FROM brew_sessions bs, unnest(...)
    ...
    WHERE bs.user_id = :user_id
    ...
""")
return db.execute(stmt, {"user_id": user_id}).all()
```
Not needed for search queries (all six use ORM `select()`), but shown because this is the established fallback when SQLAlchemy ORM cannot express a construct cleanly. For search, always prefer `Column.ilike(pattern)` with a bound variable.

**Safe highlight helper** (no analog in services — this is new, based on RESEARCH.md §RQ4):
```python
from markupsafe import Markup, escape

def highlight(text: str, query: str) -> Markup:
    """Escape text and wrap matched substring in <strong class='font-semibold'>."""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return escape(text)
    before = escape(text[:idx])
    matched = escape(text[idx: idx + len(query)])
    after = escape(text[idx + len(query):])
    return Markup(f"{before}<strong class='font-semibold'>{matched}</strong>{after}")
```
This function returns a `Markup` object — Jinja2 will NOT double-escape it. Every text fragment (`before`, `matched`, `after`) is passed through `markupsafe.escape()` before composition. This is the only safe path to D-06 when Python-side snippet extraction is needed (brew notes).

---

### `app/routers/search.py` (router, GET fragment)

**Analog:** `app/routers/roasters.py` — `roaster_autocomplete()` (lines 417-449)

**Imports pattern** (roasters.py lines 64-76):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.templates_setup import templates
```
For `search.py`, add `from app.services import search as search_service` and remove the Pydantic/form imports (GET-only, no state changes).

**Router declaration pattern** (roasters.py line 77):
```python
router = APIRouter(prefix="/search")
```
The search router has a single endpoint at `""` (i.e., `GET /search`). No sub-paths needed.

**Core GET fragment handler pattern** (roasters.py lines 417-449 — exact template):
```python
@router.get("/list", response_class=HTMLResponse)
def roaster_autocomplete(
    request: Request,
    roaster_query: str = "",
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    q = roaster_query
    if len(q) < 2:
        return HTMLResponse("", status_code=200)
    matches = roasters_service.search_by_prefix(db, query=q)
    ...
    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={...},
    )
```
The search endpoint follows this pattern exactly:
- Sync `def` (not async) — FastAPI runs it in a threadpool, consistent with all catalog routers
- `user: User = Depends(require_user)` — returns 401 if unauthenticated
- `db: Session = Depends(get_session)` — sync session
- `if len(q.strip()) < 2: return HTMLResponse("", status_code=200)` — server-authoritative 2-char guard
- `templates.TemplateResponse(request=request, name="fragments/search_results.html", context={...})`

**No CSRF token needed:** GET is read-only. `starlette-csrf` only validates on POST/PUT/PATCH/DELETE. The `htmx-listeners.js` CSRF header attachment is harmless (confirmed in RESEARCH.md §RQ5 Pitfall 6).

**Cache headers:** `FragmentCacheHeadersMiddleware` detects `HX-Request: true` and applies `Cache-Control: no-store` + `Vary: HX-Request` automatically (verified: `fragment_cache.py` lines 103-107). No route-level `Cache-Control` override needed.

---

### `app/templates/fragments/search_results.html` (template, fragment)

**Analog:** `app/templates/fragments/autocomplete_list.html`

**Fragment structure** (autocomplete_list.html lines 36-66 — full file, small):
```jinja2
<ul role="listbox" class="bg-cream-100 border border-espresso-200 rounded-lg max-h-64 overflow-y-auto dark:bg-espresso-900 dark:border-espresso-800">
  {% for item in items %}
    {% set lower = item.name|lower %}
    {% set q_lower = query|lower %}
    <li role="option"
        ...
        class="px-3 py-2 text-base hover:bg-cream-200 dark:hover:bg-espresso-800 cursor-pointer min-h-[44px]">
      {% if q_lower in lower %}
        {% set idx = lower.find(q_lower) %}
        {{ item.name[:idx] }}<strong class="font-semibold">{{ item.name[idx:idx + query|length] }}</strong>{{ item.name[idx + query|length:] }}
      {% else %}
        {{ item.name }}
      {% endif %}
    </li>
  {% endfor %}
</ul>
```

**Key patterns to replicate:**
1. `min-h-[44px]` on every result row (MOB-04 tap-target rule — seen in autocomplete_list.html line 44)
2. `hover:bg-cream-200 dark:hover:bg-espresso-800` hover state (line 44)
3. The three-part autoescape-safe highlight — `{{ item.name[:idx] }}<strong class="font-semibold">{{ item.name[idx:idx+query|length] }}</strong>{{ item.name[idx+query|length:] }}` — the surrounding text fragments autoescaped by Jinja; only the literal `<strong>` tag is raw template. **No `|safe` on any user variable.** (lines 47-47)
4. `role="listbox"` on the container; `role="option"` on each `<li>`

**Search results additions over autocomplete analog:**
- Group headers (sticky, `role="group"` with `aria-label`): `class="px-4 py-1 text-sm font-semibold text-espresso-700 dark:text-cream-300 bg-cream-200 dark:bg-espresso-800 sticky top-0"` (from UI-SPEC §Component Inventory)
- Result rows are `<a href="...">` (full-page nav, D-11) not `<li x-on:click="...">` (no Alpine needed in the fragment)
- Archived badge: `class="ml-2 inline-block rounded-full bg-espresso-200 px-2 py-0.5 text-xs text-espresso-800 dark:bg-espresso-700 dark:text-cream-100"` (UI-SPEC; also check `coffee_row.html` for exact wording)
- `aria-live="polite"` + `aria-atomic="false"` on the `#search-results` container (UI-SPEC §aria-live)
- "+N more" hint: `class="block px-4 py-2 text-sm text-espresso-600 dark:text-cream-300 cursor-default select-none"` (non-clickable)
- Empty state: single `<p>` or `<div>` with text `"Nothing matches. The grounds are clean."` (D-10)
- Groups with zero matches are omitted entirely from the fragment

**Brew note highlight uses Python-side `Markup` object** (RESEARCH.md §RQ4): the service passes a `Markup` object as `result.highlighted_name`; the template renders it as `{{ result.highlighted_name }}` — Jinja2 trusts `Markup` and does not double-escape. This is safe because every fragment inside the `Markup` was built with `markupsafe.escape()`.

---

### `app/static/js/alpine-components/search-bar.js` (Alpine CSP component)

**Analog:** `app/static/js/alpine-components/mini-modal.js`

**File structure** (mini-modal.js lines 1-97 — full file):
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('miniModal', () => ({
    open: true,
    dirty: false,

    init() {
      this._onKeydown = (e) => {
        if (e.key === 'Escape' && this.open) {
          this.close();
        }
      };
      window.addEventListener('keydown', this._onKeydown);
    },

    destroy() {
      window.removeEventListener('keydown', this._onKeydown);
    },

    close() { ... },
    ...
  }));
});
```

**Patterns to replicate exactly:**
1. `document.addEventListener('alpine:init', () => { Alpine.data('searchBar', () => ({ ... })); });` — registered inside `alpine:init`, not at module top-level (lines 31-76)
2. ESC handler via `window.addEventListener('keydown', this._onKeydown)` in `init()`, cleaned up in `destroy()` — prevents memory leaks when the Alpine component is destroyed (lines 40-50)
3. Backdrop dismiss via a method called by `@click.self` in the template (line 68-75 `onBackdropClick`)
4. No `eval`, no `new Function`, no inline object literals as `x-data` values in the template — all handlers are string method references (`x-on:click="openSheet()"`) or Alpine directive bindings

**`search-bar.js` state and methods:**
```javascript
Alpine.data('searchBar', () => ({
  sheetOpen: false,

  init() {
    this._onKeydown = (e) => {
      if (e.key === 'Escape' && this.sheetOpen) {
        this.closeSheet();
      }
    };
    window.addEventListener('keydown', this._onKeydown);
  },

  destroy() {
    window.removeEventListener('keydown', this._onKeydown);
  },

  openSheet() {
    this.sheetOpen = true;
    // auto-focus the input after Alpine renders — use $nextTick equivalent
  },

  closeSheet() {
    this.sheetOpen = false;
    // clear input value + clear #search-results innerHTML
  },
}));
```

**Rating-stars analog for `data-*` init pattern** (`rating-stars.js` lines 31-38):
```javascript
init() {
  const raw = this.$root.dataset.initialRating;
  ...
}
```
If `search-bar.js` needs to read any configuration from the DOM element, use `this.$root.dataset.*` — not inline `x-data="searchBar({ config: ... })"` (the CSP build rejects object-literal arguments in `x-data`).

---

### `app/migrations/versions/p10_search_indexes.py` (migration, DDL)

**Analog:** `app/migrations/versions/p4_shared_catalog.py` lines 175-178 (upgrade) and 279 (downgrade)

**GIN index DDL via `op.execute()`** (p4_shared_catalog.py lines 174-178):
```python
# GIN index — hand-edited per Pitfall 3 (autogenerate cannot emit USING GIN).
op.execute(
    "CREATE INDEX ix_coffees_advertised_flavor_note_ids "
    "ON coffees USING GIN (advertised_flavor_note_ids)"
)
```

**Downgrade pattern** (p4_shared_catalog.py line 279):
```python
op.execute("DROP INDEX IF EXISTS ix_coffees_advertised_flavor_note_ids")
```

**Migration header pattern** (p4_shared_catalog.py lines 59-63):
```python
revision: str = "p10_search_indexes"
down_revision: str | Sequence[str] | None = "p9_<most_recent_revision>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```
Check `alembic history` to get the exact `down_revision` value before writing the file.

**Convention note** (p4_shared_catalog.py lines 32-34):
```
# Alembic-safe convention: this migration body does NOT import from app.models.
# Schema is described inline. A future model rename does not invalidate this migration.
```
`p10_search_indexes.py` only uses `op.execute()` strings — no model imports needed.

**No `CONCURRENTLY`:** Omit `CONCURRENTLY` from all six `CREATE INDEX` statements. `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block and Alembic wraps migrations in a transaction by default. At Phase 10 first-deploy these tables have no traffic; a non-concurrent build is safe and fast (RESEARCH.md §RQ1, Pitfall 7).

**No `CREATE EXTENSION`:** Both `pg_trgm` and `unaccent` are already installed in `0001_initial.py` lines 61-62. Do not re-create them. (Verified: RESEARCH.md §Standard Stack + 0001_initial.py source.)

**Six index DDL statements to emit:**
```python
def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_coffees_name "
        "ON coffees USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_roasters_name "
        "ON roasters USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_flavor_notes_name "
        "ON flavor_notes USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_recipes_name "
        "ON recipes USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_equipment_brand_model "
        "ON equipment USING GIN ((brand || ' ' || model) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_brew_sessions_notes "
        "ON brew_sessions USING GIN (notes gin_trgm_ops)"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_search_brew_sessions_notes")
    op.execute("DROP INDEX IF EXISTS ix_search_equipment_brand_model")
    op.execute("DROP INDEX IF EXISTS ix_search_recipes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_flavor_notes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_roasters_name")
    op.execute("DROP INDEX IF EXISTS ix_search_coffees_name")
```

---

### `app/templates/base.html` (MODIFIED)

**Analog 1 — auth gate:** `app/templates/pages/home.html` lines 13-14
```jinja2
{% if request.state.user and request.state.user.is_admin %}
  {# admin-gated content #}
{% endif %}
```
For the search header the gate is simpler — no `is_admin` check:
```jinja2
{% if request.state.user %}
  <header ...>
    {# persistent search header content #}
  </header>
{% endif %}
```
This gate must wrap the entire `<header>` element so the header is absent on `/login` and `/setup` (both extend `base.html` — verified in RESEARCH.md §RQ6).

**Analog 2 — Alpine component script registration:** `app/templates/base.html` lines 17-25
```jinja2
<script defer src="/static/js/alpine-components/recipe-step-builder.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/mini-modal.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/autocomplete.js" nonce="{{ csp_nonce(request) }}"></script>
```
Add the new `search-bar.js` script tag immediately after the last existing Alpine component registration and before the `@alpinejs/csp` core script (line 31). Exact pattern:
```jinja2
<script defer src="/static/js/alpine-components/search-bar.js" nonce="{{ csp_nonce(request) }}"></script>
```

**Injection point in `base.html`:** The persistent header inserts between `<body class="...">` (line 39) and `{% block content %}{% endblock %}` (line 40). Current base.html has no content between those two lines — the insert is additive, not a replacement.

**`x-data` usage on the header:** The persistent header element itself carries `x-data="searchBar"` (string reference — CSP build requires the string form, not an inline object). The outer `<header>` element is the Alpine component root.

---

### `app/main.py` (MODIFIED)

**Analog:** `app/main.py` lines 84-99 (import block) and 229-241 (router include block)

**Import pattern** (main.py lines 84-99):
```python
from app.routers import admin as admin_router
from app.routers import ai as ai_router
from app.routers import auth as auth_router
...
from app.routers import photos as photos_router
```
Add immediately after `photos_router`:
```python
from app.routers import search as search_router
```

**`include_router` pattern** (main.py lines 229-241):
```python
app.include_router(csp_report_router.router)
app.include_router(auth_router.router)
...
app.include_router(ai_router.router)
app.include_router(photos_router.router)
```
Add after `photos_router`:
```python
app.include_router(search_router.router)
```
No prefix argument needed — the router's own `APIRouter(prefix="/search")` handles it (consistent with all other flat routers).

---

## Shared Patterns

### Authentication (`require_user` dependency)
**Source:** `app/dependencies/auth.py` lines 33-45
**Apply to:** `app/routers/search.py`
```python
def require_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
```
All authenticated endpoints use `user: User = Depends(require_user)`. The search endpoint is no exception.

### Sync DB session dependency
**Source:** `app/routers/coffees.py` line 254, `app/routers/roasters.py` line 421
**Apply to:** `app/routers/search.py`
```python
db: Session = Depends(get_session)  # noqa: B008
```
All catalog router handlers use sync `Session`, consistent with search's six sync `select()` queries.

### `templates.TemplateResponse` call signature
**Source:** `app/routers/roasters.py` lines 439-448 (current API — `request=request` as kwarg)
```python
return templates.TemplateResponse(
    request=request,
    name="fragments/autocomplete_list.html",
    context={
        "items": matches,
        "query": q,
        ...
    },
)
```
Use `request=request` as a keyword argument (FastAPI 0.136+ / Starlette 1.0 API). Do not use the older positional `(name, {"request": request, ...})` form.

### Fragment cache headers (automatic via middleware)
**Source:** `app/middleware/fragment_cache.py` lines 103-107
**Apply to:** `app/routers/search.py` (automatically — no code change needed)
```python
if hx_request:
    headers.append((b"cache-control", HX_REQUEST_CACHE))  # "no-store"
    headers.append((b"vary", HX_VARY))                    # "HX-Request"
```
`FragmentCacheHeadersMiddleware` is already in the middleware stack. `GET /search` requests from HTMX will carry `HX-Request: true` and get `Cache-Control: no-store` + `Vary: HX-Request` for free. The route handler does NOT need to set any headers manually.

### Autoescape-ON Jinja environment
**Source:** `app/templates_setup.py` lines 40-47
**Apply to:** All new templates in `app/templates/fragments/`
```python
templates.env.autoescape = select_autoescape(["html", "jinja", "jinja2"])
```
Autoescape is on globally. No template fragment needs to do anything — the environment handles it. The consequence is that `{{ variable }}` always escapes; to render trusted `Markup` objects (from the `highlight()` helper), Jinja2 trusts `Markup` instances and does not re-escape them.

### CSP nonce on script tags
**Source:** `app/templates/base.html` lines 17-37
**Apply to:** Any new `<script>` tag added to `base.html`
```jinja2
<script defer src="/static/js/alpine-components/search-bar.js" nonce="{{ csp_nonce(request) }}"></script>
```
Every `<script>` tag must carry `nonce="{{ csp_nonce(request) }}"`. A script tag without a nonce is blocked by the `SecurityHeadersMiddleware` CSP policy.

---

## Critical Correctness Traps (for executor)

These are not patterns to copy — they are pitfalls the executor must avoid.

| Trap | Wrong | Correct |
|------|-------|---------|
| Recipe searchable columns | `Recipe.description` (does not exist) | `Recipe.name` only — `description` column was never added (RESEARCH.md Pitfall 1, D-13) |
| Equipment searchable field | `Equipment.name` (does not exist) | `func.concat(Equipment.brand, " ", Equipment.model).ilike(pattern)` (RESEARCH.md Pitfall 2, D-14 schema note) |
| HTML-safe highlight | `{{ variable \| safe }}` | Three-part template split or `markupsafe.Markup` composition — never `\|safe` on user data (D-06, SEC-05) |
| ILIKE bind parameter | `text(f"... ILIKE '%{query}%'")` | `Column.ilike(pattern)` where `pattern = f"%{query}%"` is a Python variable (RESEARCH.md §Security, SQL injection note) |
| Alpine component in template | `x-data="{ sheetOpen: false }"` (object literal) | `x-data="searchBar"` (string reference to registered `Alpine.data()` factory) — CSP build rejects object literals |
| `CREATE INDEX CONCURRENTLY` in migration | Inside a transaction block (Alembic default) | Omit `CONCURRENTLY` for the initial migration (RESEARCH.md Pitfall 7) |

---

## No Analog Found

None. All seven files have strong analogs in the codebase. No file in this phase requires reaching outside the existing pattern library.

---

## Metadata

**Analog search scope:** `app/services/`, `app/routers/`, `app/templates/fragments/`, `app/static/js/alpine-components/`, `app/migrations/versions/`, `app/templates/`, `app/middleware/`, `app/dependencies/`, `app/main.py`
**Files read for pattern extraction:** `analytics.py`, `roasters.py` (autocomplete endpoint), `autocomplete_list.html`, `fragment_cache.py`, `coffees.py` (list handler), `base.html`, `home.html`, `main.py`, `mini-modal.js`, `rating-stars.js`, `p4_shared_catalog.py`, `templates_setup.py`, `auth.py`
**Pattern extraction date:** 2026-05-22

---

## PATTERN MAPPING COMPLETE
