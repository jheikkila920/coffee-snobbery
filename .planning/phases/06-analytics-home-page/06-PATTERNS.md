# Phase 6: Analytics (Home Page) - Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 9 (5 new, 4 modified/extended)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/services/analytics.py` | service | CRUD (read-only aggregation) | `app/services/brew_sessions.py` | role-match |
| `app/routers/home.py` | router | request-response (shell + fragments) | `app/routers/brew.py` lines 473-516 | exact |
| `app/templates/pages/home.html` | template | request-response | `app/templates/pages/sessions.html` | role-match |
| `app/templates/fragments/home/` (per-card) | template | request-response | `app/templates/fragments/session_list.html` + `session_row.html` | role-match |
| `app/templates/fragments/home/_card_sparse.html` | template | request-response | `app/templates/fragments/empty.html` | role-match |
| `app/main.py` (remove placeholder `/`) | config | n/a | `app/main.py` lines 249-262 | exact (removal target) |
| `tests/services/test_analytics.py` | test | CRUD | `tests/services/test_brew_sessions_service.py` | exact |
| `tests/routers/test_home.py` | test | request-response | `tests/routers/test_brew_router.py` | exact |
| `tests/services/conftest.py` (or extend `tests/conftest.py`) | test config | n/a | `tests/phase_04/conftest.py` | role-match |

---

## Pattern Assignments

### `app/services/analytics.py` (service, read-only CRUD aggregation)

**Analog:** `app/services/brew_sessions.py`

**Imports pattern** (`app/services/brew_sessions.py` lines 29-49):
```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.equipment import Equipment
from app.models.recipe import Recipe

log = structlog.get_logger(__name__)
```

For `analytics.py` extend these with the additional models and stdlib imports needed:
```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import case, cast, func, literal, select, union_all
from sqlalchemy import Date as SaDate
from sqlalchemy.orm import Row, Session, aliased

from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe

log = structlog.get_logger(__name__)
```

**Core read-query pattern — per-user scoping + SQLAlchemy 2.0 style** (`app/services/brew_sessions.py` lines 154-215, trimmed to the select shape):
```python
def create_brew_session(db: Session, *, by_user_id: int, ...) -> BrewSession:
    # The key scoping discipline: every read/write has user_id in WHERE.
    # Analytics mirrors the same pattern with select() instead of insert().
    stmt = (
        select(BrewSession)
        .where(BrewSession.user_id == by_user_id)
        .order_by(BrewSession.brewed_at.desc())
        .limit(10)
    )
    return db.execute(stmt).scalars().all()
```

**`db.scalar()` scalar-result pattern** (used in conftest `_usage_count` helper at `tests/services/test_brew_sessions_service.py` lines 123-131):
```python
def _usage_count(db, equipment_id: int) -> int:
    from sqlalchemy import select
    from app.models.equipment import Equipment
    return db.execute(
        select(Equipment.usage_count).where(Equipment.id == equipment_id)
    ).scalar_one()
```

For analytics use `db.scalar(...)` (returns `None` on empty) rather than `scalar_one()` (raises on empty):
```python
count = db.scalar(select(func.count(BrewSession.id)).where(...)) or 0
```

**Module-level sentinel constant pattern** (no existing analog — use this shape):
```python
_EMPTY_SIGNATURE: str = hashlib.sha256(b"[]").hexdigest()
```

**Structlog emit pattern** (`app/services/brew_sessions.py` — not needed for read-only analytics; omit `log.info(...)` audit events since analytics reads carry no side-effects).

---

### `app/routers/home.py` (router, request-response — shell + lazy fragment endpoints)

**Analog:** `app/routers/brew.py` — specifically the `list_sessions` (lines 473-516) and `prefill_fragment` (lines 679-725) handlers, which show the HX-Request fragment branch and the `require_user` + `get_session` Depends pattern.

**Imports pattern** (`app/routers/brew.py` lines 37-65):
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

For `home.py` add the analytics service import and drop the brew-specific ones:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import analytics
from app.templates_setup import templates

router = APIRouter()
```

**Shell route pattern — eager queries + full-page render** (`app/routers/brew.py` lines 473-516):
```python
@router.get("", response_class=HTMLResponse)
def list_sessions(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    # Analog for home shell: call analytics.get_cold_start_counts() and
    # analytics.get_recent_brews() eagerly here, then render the full page.
    # The HX-Request branch in list_sessions shows the fragment-only render
    # pattern; the home shell DOES NOT have a fragment branch on GET /
    # (the initial render is always the full page).
    sessions = brew_sessions_service.list_brew_sessions(db, by_user_id=user.id, ...)
    return templates.TemplateResponse(
        request=request,
        name="pages/sessions.html",
        context={...},
    )
```

**Fragment endpoint pattern — per-card lazy endpoints** (`app/routers/brew.py` lines 679-725, the `prefill_fragment` handler is the closest structural match for a read-only fragment):
```python
@router.get("/prefill", response_class=HTMLResponse)
def prefill_fragment(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    # Analytics fragment shape is simpler: call one analytics function,
    # pass the rows directly to the template. No form state involved.
    # FragmentCacheHeadersMiddleware applies no-store + Vary: HX-Request
    # automatically — no per-route header configuration needed.
    ...
    return templates.TemplateResponse(
        request=request, name="fragments/brew_prefill_fields.html", context=context
    )
```

Home card fragment shape (copy this pattern for each `/home/cards/*` endpoint):
```python
@router.get("/home/cards/top-coffees", response_class=HTMLResponse)
def card_top_coffees(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    rows = analytics.get_top_coffees(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/top_coffees.html",
        context={"rows": rows},
    )
```

**Placeholder removal target** (`app/main.py` lines 249-262):
```python
    @app.get("/")
    def home(request: Request) -> object:
        """Render the placeholder home page (Phase 0).

        Phase 4 replaces this with the real home page route — keeping the
        Phase 0 template path here means existing healthcheck flows and
        manual smoke tests stay green during the Phase 1 → Phase 4
        transition.
        """
        return request.app.state.templates.TemplateResponse(
            request=request, name="pages/index.html", context={}
        )
```

This block is REMOVED. Replace with `app.include_router(home_router.router)` in the router registration block (lines ~225-230), mirroring how other routers are registered.

---

### `app/templates/pages/home.html` (page shell template)

**Analog:** `app/templates/pages/sessions.html`

**Page shell pattern** (`app/templates/pages/sessions.html` lines 1-98):
```html
{% extends "base.html" %}
{% block page_title %}Sessions{% endblock %}
{% block content %}
  <main class="mx-auto max-w-6xl px-6 py-12">
    <header class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <h1 class="text-2xl font-semibold">Sessions</h1>
      ...
    </header>
    {% include "fragments/session_list.html" %}
  </main>
{% endblock %}
```

For `home.html`: extend `base.html`, render the recent-brews section and unrated-coffees section eagerly (included from their fragment files), then render a cold-start gate block that either shows the aggregate-card skeletons (with `hx-trigger="load delay:Nms"`) or the progress meter empty state.

**HTMX lazy-load card shell pattern** (from RESEARCH.md Pattern 1):
```html
<div hx-get="/home/cards/top-coffees"
     hx-trigger="load delay:100ms"
     hx-swap="innerHTML">
  <!-- loading skeleton — animate-pulse, no Alpine, no JS -->
  <div class="animate-pulse space-y-2">
    <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
    <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
  </div>
</div>
```

**CSP constraint (all templates):** No `|safe`, no `hx-on:`, no `hx-vals='js:'`. All values autoescaped. Alpine components loaded via `Alpine.data(...)` in `/static/js/alpine-components/`. Enforced by CI grep test (`tests/ci/test_no_unsafe_jinja.py`).

**Card border/padding pattern** (`app/templates/fragments/session_row.html` lines 18-21 — the card `div` shape used for mobile session cards):
```html
<div id="session-{{ row.id }}"
     data-row
     class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
```

Use this same `rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800` shape for analytics card containers. Wrap each card body in the stagger div above.

---

### `app/templates/fragments/home/*.html` (per-card fragments)

**Analog:** `app/templates/fragments/session_list.html` (empty-state pattern + data rendering) and `app/templates/fragments/session_row.html` (card layout + autoescaping).

**Empty-state pattern** (`app/templates/fragments/session_list.html` lines 58-84):
```html
{% elif active_filter_count %}
  <div class="flex flex-col items-center justify-center text-center py-16 gap-3">
    <h2 class="text-lg font-semibold">No sessions match these filters.</h2>
    <p class="text-base text-espresso-700 dark:text-cream-200">
      Try widening the date range or clearing a filter.
    </p>
  </div>
{% else %}
  <div class="flex flex-col items-center justify-center text-center py-16 gap-3">
    <h2 class="text-lg font-semibold">No brews logged yet.</h2>
    <p class="text-base text-espresso-700 dark:text-cream-200">The snobbery awaits.</p>
  </div>
{% endif %}
```

For analytics cards there are two D-04/D-05 empty-state variants. Use a shared partial `_card_sparse.html` and include it from each card. The partial receives `hint_type` context: `"sparse"` for the generic "keep logging" hint and `"unrated"` for the "rate your brews" nudge.

**Table/list data rendering** (`app/templates/fragments/session_list.html` lines 29-57):
```html
{% if rows %}
  <div class="hidden md:block">
    <table class="w-full text-base">
      <thead>
        <tr class="text-sm font-semibold border-b border-espresso-200 dark:border-espresso-800">
          <th class="text-left py-2">Coffee</th>
          ...
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
          ...
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="md:hidden space-y-3">
    {% for row in rows %}
      ...
    {% endfor %}
  </div>
{% endif %}
```

Analytics cards are read-only summary cards — no desktop table needed. Use `<ul class="space-y-2">` with `<li>` rows for ranked lists (top coffees, sweet spots, flavor descriptors). The session_row card shape (`rounded-lg border ...`) is the right reference for the mobile layout of each card.

**Autoescaping rule** (`app/templates/fragments/session_row.html` line 13):
```
{# All values render autoescaped (no |safe). #}
```

No `|safe` filter anywhere in Phase 6 templates. All user-generated content and query results render through Jinja2's autoescape.

---

### `app/templates/fragments/home/_card_sparse.html` (shared sparse-card partial)

**Analog:** `app/templates/fragments/empty.html`

Read the existing empty.html for its exact structure:
```html
{# Renders the shared empty state (used across all Phase 6 analytics cards).
   Context: hint_type ("sparse" | "unrated"), card_name (for screen reader label). #}
{% if hint_type == "unrated" %}
  <p class="text-sm text-espresso-600 dark:text-cream-300">Rate some brews to see this.</p>
{% else %}
  <p class="text-sm text-espresso-600 dark:text-cream-300">Keep logging to see this.</p>
{% endif %}
```

This partial is included by each aggregate card fragment when `rows` is empty. The caller sets `hint_type` and the card heading is rendered by the outer card shell, not this partial.

---

### `app/main.py` (MODIFIED — remove placeholder `/` route, add `include_router(home)`)

**Analog:** Existing `app/main.py` router registration block (lines 225-231).

**Router registration pattern** (`app/main.py` lines 225-231):
```python
    from app.routers import csp_report as csp_report_router
    ...
    from app.routers import brew as brew_router
    ...
    app.include_router(brew_router.router)
```

Add to the router import block:
```python
    from app.routers import home as home_router
```

Add to the include_router block:
```python
    app.include_router(home_router.router)
```

Remove lines 249-262 (the `@app.get("/") def home(...)` placeholder handler).

---

### `tests/services/test_analytics.py` (test, service-layer unit tests)

**Analog:** `tests/services/test_brew_sessions_service.py`

**Skip-gate pattern** (`tests/services/test_brew_sessions_service.py` lines 33-55):
```python
def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 service test needs the DB")


def _require_p5_migration_applied() -> None:
    try:
        from sqlalchemy import text
        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.brew_sessions')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p5_brew_sessions migration not applied")
```

Rename the migration check to `_require_analytics_tables()` and probe for `brew_sessions` (same table — analytics reads it). Phase 6 adds no migration, so the same probe applies.

**Seeding-helper pattern** (`tests/services/test_brew_sessions_service.py` lines 63-89):
```python
def _seed_user(db, *, username: str):
    from app.models.user import User
    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user

def _seed_coffee(db, *, name: str = "Test Coffee"):
    from app.models.coffee import Coffee
    coffee = Coffee(name=name)
    db.add(coffee)
    db.flush()
    return coffee
```

Analytics tests need richer seeds: multiple brew sessions with ratings, bags with `roast_date`, flavor notes, equipment, recipes. Follow the same lazy-import + `db.flush()` pattern. Group all seeds into a `_seed_analytics_scenario(db, *, username)` helper that creates:
- 1 user
- 2-5 coffees (different origins/processes)
- 1-2 bags with `roast_date` set
- 1 brewer equipment row
- 1 recipe row
- N brew sessions with `rating` set (≥2 per coffee for HOME-01 floors)
- flavor notes with ids in `flavor_note_ids_observed`

**`SessionLocal` test session pattern** (`tests/services/test_brew_sessions_service.py` lines 144-180):
```python
def test_create_writes_user_scoped_row(clean_brew: None) -> None:
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="brewtest-create")
        coffee = _seed_coffee(db)
        db.commit()
        uid, cid = user.id, coffee.id

    with SessionLocal() as db:
        row = svc.create_brew_session(db, by_user_id=uid, coffee_id=cid, ...)
```

Analytics tests follow the same shape: seed in one `with SessionLocal()` block, call analytics in a second block, assert in the same block or a third:
```python
def test_top_coffees(clean_analytics: None) -> None:
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid = _seed_analytics_scenario(db, username="analyticstest-top")

    with SessionLocal() as db:
        rows = analytics.get_top_coffees(db, uid)
    assert len(rows) <= 5
    assert all(r.session_count >= 2 for r in rows)
    # rows are sorted avg_rating DESC
    ratings = [float(r.avg_rating) for r in rows]
    assert ratings == sorted(ratings, reverse=True)
```

**Clean fixture pattern** (`tests/services/test_brew_sessions_service.py` lines 91-120):
```python
@pytest.fixture
def clean_brew() -> Iterator[None]:
    from sqlalchemy import text
    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM users WHERE username LIKE 'brewtest-%'"))

    _reset()
    yield
    _reset()
```

Use the same pattern as `clean_analytics`:
```python
@pytest.fixture
def clean_analytics() -> Iterator[None]:
    from sqlalchemy import text
    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM bags WHERE ..."))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM users WHERE username LIKE 'analyticstest-%'"))

    _reset()
    yield
    _reset()
```

---

### `tests/routers/test_home.py` (test, router smoke tests)

**Analog:** `tests/routers/test_brew_router.py`

**Skip-gate + authed client pattern** (`tests/routers/test_brew_router.py` lines 39-79):
```python
_CSRF_TOKEN = "test-csrf-token-phase05-brew"  # noqa: S105

def _require_postgres() -> None:
    ...
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 router test needs the DB")

def _require_p5_migration_applied() -> None:
    ...
```

**Authed test client construction** (`tests/phase_04/conftest.py` lines 59-81):
```python
@pytest.fixture
def authed_client(app: Any, seeded_admin_user: dict[str, Any]) -> Iterator[Any]:
    from fastapi.testclient import TestClient
    csrf_token = "test-csrf-token-phase04-fixture"
    with TestClient(app) as client:
        client.cookies.set("session_id", seeded_admin_user["signed_cookie"])
        client.cookies.set("csrftoken", csrf_token)
        client.headers["X-CSRF-Token"] = csrf_token
        yield client
```

Home router tests use `seeded_regular_user` (analytics is a non-admin surface). The authed client shape is identical — copy from `tests/phase_04/conftest.py` or use the parent conftest `seeded_regular_user` directly. For fragment endpoint tests, pass `headers={"HX-Request": "true"}`.

Router smoke test shape:
```python
def test_home_shell_authenticated(authed_client: Any) -> None:
    """GET / returns 200 and the home page shell for an authed user."""
    _require_postgres()
    _require_analytics_tables()
    resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "Snobbery" in resp.text

def test_card_top_coffees_fragment(authed_client: Any) -> None:
    """GET /home/cards/top-coffees returns 200 with Vary: HX-Request header."""
    _require_postgres()
    _require_analytics_tables()
    resp = authed_client.get("/home/cards/top-coffees", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")

def test_home_unauthenticated_redirects(client: Any) -> None:
    """GET / without auth returns 401 (require_user gate)."""
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 401
```

---

## Shared Patterns

### Authentication / Auth Gate
**Source:** `app/dependencies/auth.py` lines 33-45
**Apply to:** `app/routers/home.py` — all routes (shell + every fragment endpoint)
```python
def require_user(request: Request) -> User:
    """Return the authenticated User; raise 401 if no session."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
```

Usage in every home router handler:
```python
user: User = Depends(require_user),  # noqa: B008
```

`request.state.user.id` is the ONLY source of `user_id` for analytics queries. Never accept `user_id` from query parameters.

### DB Session Dependency
**Source:** `app/dependencies/db.py` lines 61-70
**Apply to:** `app/routers/home.py` — all routes; `app/services/analytics.py` — all functions accept `db: Session` as first positional arg
```python
def get_session() -> Iterator[Session]:
    """Yield a fresh sync Session for the request lifetime."""
    with SessionLocal() as session:
        yield session
```

Usage in handlers:
```python
db: Session = Depends(get_session),  # noqa: B008
```

### Fragment Cache Headers (automatic — no per-route config)
**Source:** `app/main.py` middleware stack — `FragmentCacheHeadersMiddleware` (Phase 1)
**Apply to:** All `/home/cards/*` fragment endpoints

`FragmentCacheHeadersMiddleware` applies `Cache-Control: no-store` and `Vary: HX-Request` automatically to any response to a request with `HX-Request: true`. No per-route header setting is needed. Verified in `tests/middleware/test_fragment_cache.py`.

### Per-User Scoping (IDOR defense)
**Source:** `app/services/brew_sessions.py` — every function has `by_user_id: int` param; every `select()` has `.where(BrewSession.user_id == by_user_id)`
**Apply to:** Every function in `app/services/analytics.py`

The `user_id` is always passed as an explicit function argument (never a global), and every SQL `WHERE` clause includes `BrewSession.user_id == user_id` as the FIRST filter. No analytics query is ever unscoped.

### SQLAlchemy 2.0 Query Style
**Source:** `app/services/brew_sessions.py` lines 154-215 (all CRUD functions)
**Apply to:** `app/services/analytics.py` — all query functions

```python
# CORRECT — SQLAlchemy 2.0 Core style
stmt = select(BrewSession).where(BrewSession.user_id == user_id)
rows = db.execute(stmt).scalars().all()

# FORBIDDEN — legacy Query API (never used in this codebase)
rows = db.query(BrewSession).filter(BrewSession.user_id == user_id).all()
```

### Template Response Shape
**Source:** `app/routers/brew.py` lines 496-516
**Apply to:** All handlers in `app/routers/home.py`
```python
return templates.TemplateResponse(
    request=request,
    name="pages/sessions.html",
    context={...},
)
```

Always pass `request=request` as a keyword argument (Jinja2 + CSRF meta needs it). Never use positional args for `TemplateResponse`.

### `type: ignore` + `noqa` comment discipline
**Source:** `app/routers/brew.py` lines 476-478
**Apply to:** All `Depends(...)` calls in `app/routers/home.py`
```python
user: User = Depends(require_user),  # noqa: B008
db: Session = Depends(get_session),  # noqa: B008
```

The `# noqa: B008` suppresses the ruff `B008` "do not perform function call in default arguments" warning for FastAPI `Depends()` usage.

---

## No Analog Found

All Phase 6 files have close analogs. The following query patterns have no existing codebase analog but are well-specified in RESEARCH.md:

| Pattern | Reason | Reference |
|---|---|---|
| `func.unnest().column_valued()` lateral join (HOME-03, cold-start note count) | No existing array-unnest queries in the codebase | RESEARCH.md Pattern 3 + SQLAlchemy 2.0 docs |
| `case()` date-arithmetic buckets (HOME-04) | No existing date-bucket queries | RESEARCH.md Pattern 4 |
| `hashlib.sha256` + `json.dumps(sort_keys=True)` signature computation | No existing content-hash functions | RESEARCH.md Pattern 6 (stdlib) |
| `union_all(...).subquery()` ORDER BY + LIMIT (HOME-05 if UNION path chosen) | No existing UNION queries | RESEARCH.md Pattern 5 + SQLAlchemy docs |

For these patterns, the planner should use the RESEARCH.md code examples directly (all are stdlib or SQLAlchemy 2.0 core — no new dependencies).

---

## Metadata

**Analog search scope:** `app/routers/`, `app/services/`, `app/templates/`, `app/dependencies/`, `tests/services/`, `tests/routers/`, `tests/phase_04/`
**Files scanned:** 13 source files fully read
**Pattern extraction date:** 2026-05-20
