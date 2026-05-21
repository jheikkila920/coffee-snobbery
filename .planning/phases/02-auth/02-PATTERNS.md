# Phase 2: Auth - Pattern Map

**Mapped:** 2026-05-17
**Files analyzed:** 28 (12 new app files / 6 modified app files / 8 new test files / 4 extended test files / 1 metadata extend)
**Analogs found:** 26 / 28 (2 files have no analog — `tests/dependencies/__init__.py` is a trivial marker; the `CSRFFormFieldShim` body-replay path has no in-repo analog and inherits Starlette's `Request._receive` idiom)

> All file paths are project-relative. Line numbers refer to the analog file's state at mapping time. Concrete patterns are extracted as block-quoted code; the planner is expected to lift these verbatim (with the noted edits) into each plan's action section.

---

## File Classification

### Application code (new)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `app/services/auth.py` | service (crypto wrapper) | transform (sync, pure) | `app/signing.py` | exact (module-level singleton + pure functions; no DB) |
| `app/services/setup.py` | service (DB transaction) | CRUD (async, transactional) | `app/services/sessions.py` `regenerate_session` | exact (async SQLAlchemy 2.0, single-commit atomic write) |
| `app/dependencies/__init__.py` | package marker | n/a | `app/services/__init__.py` (1-line marker) | exact |
| `app/dependencies/auth.py` | dependency (FastAPI guard) | request-response (sync) | — (no existing FastAPI `Depends` in codebase) | NEW pattern — copy from RESEARCH §"FastAPI — Depends(require_admin) pattern" |
| `app/dependencies/db.py` | dependency (async session factory injector) | request-response (async generator) | inline `async with self.session_factory()` in `app/middleware/session.py:161` | role-match (extract pattern from middleware into FastAPI dependency shape) |
| `app/routers/admin.py` | router (HTML page, gated) | request-response | `app/routers/csp_report.py` (router scaffold) + `app/routers/debug.py` (single route) | role-match (router shape; this one renders a template instead of returning JSON) |
| `app/templates/pages/setup.html` | template (form) | request-response (server-rendered) | `app/templates/pages/index.html` + `app/templates/base.html` | partial (extends base.html; first form in the codebase, no exact form analog) |
| `app/templates/pages/login.html` | template (form) | request-response (server-rendered) | `app/templates/pages/index.html` + `app/templates/base.html` | partial (same shape as setup.html) |
| `app/templates/pages/admin.html` | template (one-line stub) | request-response (server-rendered) | `app/templates/pages/index.html` | exact |

### Application code (replace / modify in place)

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `app/routers/auth.py` | router (REPLACE stub bodies + add `/logout`) | request-response (form POSTs) | `app/routers/auth.py` (current Phase 1 stub — keep decorator/import shape; replace bodies) + `app/routers/csp_report.py` (for the Response-returning shape) | self-analog for shape; service-layer composition pattern from `app/services/sessions.py` |
| `app/routers/debug.py` | router (add `Depends(require_admin)` to existing route) | request-response | `app/routers/debug.py` (current file — single-line edit) | exact (self) |
| `app/middleware/session.py` | middleware (in-place D-09/D-10 upgrade) | request-response (async DB lookup) | `app/middleware/session.py` (current Phase 1 file — TODO marker at line 179) | exact (self) |
| `app/csrf.py` | config + APPEND `CSRFFormFieldShim` ASGI class | request-response (ASGI body-replay) | `app/middleware/fragment_cache.py` (pure-ASGI middleware shape) + Starlette's `Request._receive` body buffering idiom (no in-repo example) | role-match for the shim shell; **no body-replay analog in the codebase** |
| `app/main.py` | factory wiring (add shim middleware + include admin router) | request-response | `app/main.py:174-183` (middleware add-order block; router include block) | exact (self) |
| `app/templates/pages/index.html` | template (augment with conditional footer) | request-response | `app/templates/pages/index.html` (current — extend the existing `{% block content %}`) | exact (self) |

### Tests (new)

| New Test File | Role | Closest Analog | Match Quality |
|---------------|------|----------------|---------------|
| `tests/services/test_auth.py` | unit | `tests/services/test_sessions.py` | exact (same `try/except ImportError` skip pattern) |
| `tests/services/test_setup.py` | unit + integration (race fixture) | `tests/services/test_sessions.py` | role-match (adds `asyncio.gather` race; no prior example) |
| `tests/routers/test_auth.py` | integration (REPLACES `test_auth_stub.py`) | `tests/routers/test_auth_stub.py` (delete after creating) + `tests/middleware/test_csrf.py` (`_csrf_pair` helper) | exact (CSRF-paired POST shape) |
| `tests/routers/test_admin.py` | integration (three-state gate) | `tests/routers/test_debug_proxy.py` | role-match (router test scaffold) |
| `tests/dependencies/__init__.py` | package marker | `tests/services/__init__.py` (empty file) | exact |
| `tests/dependencies/test_auth.py` | unit (raise-403 path) | `tests/middleware/test_session.py` (lazy-import + skip pattern) | role-match (no FastAPI-`Depends`-as-callable example in tests) |
| `tests/middleware/test_csrf_form_shim.py` | integration (5 cases) | `tests/middleware/test_csrf.py` | exact (CSRF middleware test scaffold; same `_csrf_pair`-style helper) |
| `tests/test_phase02_smoke.py` | integration (cold-container E2E) | `tests/routers/test_csp_report.py` (TestClient happy-path scaffold) + `tests/test_healthz.py` (lifespan-aware) | partial (no prior multi-route smoke; compose from both) |

### Tests (extend)

| Extended Test File | Existing Analog Tests | Match Quality |
|--------------------|------------------------|---------------|
| `tests/middleware/test_session.py` | `tests/middleware/test_session.py:24-97` (existing 3 tests) | exact (self — same lazy-import pattern, add D-09/D-10 cases) |
| `tests/routers/test_debug_proxy.py` | `tests/routers/test_debug_proxy.py:22-66` | exact (self — add three-state admin-gate cases) |
| `tests/test_logging.py` | `tests/test_logging.py:156-203` (`test_redactor_scrubs_sensitive_keys` — capture-handler pattern) | exact (self — extend with D-15 reason-field assertions for real handlers) |
| `tests/conftest.py` | `tests/conftest.py:56-162` (fixture shape; `_reset_rate_limiter` autouse pattern) | exact (self — add `async_client`, `fresh_db`, `seeded_admin_user`, `seeded_regular_user`) |

---

## Pattern Assignments

### `app/services/auth.py` (service, transform — sync, pure)

**Analog:** `app/signing.py` (module-level singleton + pure functions; no DB)

**Imports pattern** (analog `app/signing.py:17-23`):
```python
from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings
```

**Module-level singleton pattern** (analog `app/signing.py:25-29`):
```python
# Module-level signer: built once at import time, bound to the configured
# APP_SECRET_KEY. The salt namespaces this serializer against any future
# signed-value usage ...
session_signer = URLSafeSerializer(secret_key=settings.APP_SECRET_KEY, salt="session")
```

**For Phase 2 `app/services/auth.py`:** the planner replaces with `_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)` and `_DUMMY_HASH = _ph.hash("…")` (RESEARCH §argon2-cffi 25.1 lines 160-189 is the canonical body).

**Pure-function with `try/except` pattern** (analog `app/signing.py:41-59`):
```python
def load_session_id(signed_cookie_value: str) -> uuid.UUID | None:
    """Verify *signed_cookie_value* and return the embedded UUID.

    Returns ``None`` on either:
    * :class:`itsdangerous.BadSignature` — the cookie was tampered with ...
    """
    try:
        raw = session_signer.loads(signed_cookie_value)
        return uuid.UUID(raw)
    except (BadSignature, ValueError):
        return None
```

**Translate this shape to argon2:** `verify_password(stored_hash, candidate)` catches `(VerifyMismatchError, InvalidHashError)` → returns `False`; `dummy_verify(candidate)` catches `VerifyMismatchError` and `pass`es.

**`__all__` export pattern** (analog `app/signing.py:62`):
```python
__all__ = ["session_signer", "sign_session_id", "load_session_id"]
```

For Phase 2: `__all__ = ["hash_password", "verify_password", "dummy_verify"]` (omit `_ph` and `_DUMMY_HASH` — leading underscore is the convention).

---

### `app/services/setup.py` (service, CRUD — async transactional)

**Analog:** `app/services/sessions.py` — `regenerate_session` (lines 72-109)

**Imports pattern** (analog `app/services/sessions.py:32-40`):
```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
```

**For Phase 2:** drop `delete`/`Session`/`uuid`/timedelta, add `from app.models.app_setting import AppSetting`, `from app.models.user import User`, `from app.services.auth import hash_password`.

**Atomic-transaction pattern** (analog `app/services/sessions.py:72-109`):
```python
async def regenerate_session(
    db: AsyncSession,
    current_session_id: uuid.UUID | None,
    user_id: int,
) -> uuid.UUID:
    """Atomic delete-then-insert for session-ID regeneration (D-10).
    ...
    The delete + insert run in the same transaction and commit ONCE so a
    concurrent reader cannot observe the gap. ...
    """
    if current_session_id is not None:
        await db.execute(delete(Session).where(Session.session_id == current_session_id))

    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_LIFETIME_DAYS)
    new_id = uuid.uuid4()
    db.add(
        Session(
            session_id=new_id,
            user_id=user_id,
            last_seen=now,
            expires_at=expires,
            created_at=now,
        )
    )
    # Single commit so the swap is atomic across the delete + insert.
    await db.commit()
    return new_id
```

**Phase 2 maps this to** `create_first_admin(db, *, username, email, password) -> User | None`:
- Replace the initial `delete()` with `select(AppSetting).where(...).with_for_update()` → `scalar_one()` → race-loss check.
- Replace `db.add(Session(...))` with `db.add(User(...))` + `await db.flush()` (to get `new_user.id`).
- Add `await db.execute(update(AppSetting).where(...).values(value="true"))` before the final commit.
- The body of RESEARCH §"Canonical pattern for AUTH-02" (lines 304-369) is the verbatim composition target.

**Module-trailing TODO + `__all__` pattern** (analog `app/services/sessions.py:185-200`):
```python
# Phase 8 TODO: schedule a periodic
#     DELETE FROM sessions WHERE expires_at < now()
# job via APScheduler. ...

__all__ = [
    "SESSION_LIFETIME_DAYS",
    ...
    "regenerate_session",
]
```

For Phase 2: no TODO needed; `__all__ = ["create_first_admin"]`.

---

### `app/dependencies/__init__.py` (package marker)

**Analog:** `app/services/__init__.py` (1-liner)

**Full file content** (analog `app/services/__init__.py:1`):
```python
"""Stateful logic; owned by Phase 3+."""
```

**For Phase 2:**
```python
"""FastAPI dependency callables (Depends targets); owned by Phase 2+."""
```

---

### `app/dependencies/auth.py` (dependency, request-response)

**Analog:** None in codebase (no existing `Depends()` callables). RESEARCH §"FastAPI — `Depends(require_admin)` pattern" (lines 407-459) is the canonical source.

**Imports pattern** (compose from `app/routers/debug.py:9-14` style):
```python
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.models.user import User
```

**Core pattern** (verbatim from RESEARCH §FastAPI Depends, lines 422-438):
```python
def require_user(request: Request) -> User:
    """Dependency: 401 if request.state.user is None, else returns User."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(request: Request) -> User:
    """Dependency: 403 unless request.state.user is an active admin."""
    user = require_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user
```

**Decisional note for planner (per CONTEXT D-14 + RESEARCH §FastAPI Depends, Form-1 vs Form-2):**
- `app/routers/admin.py` uses **Form 1** (`user: User = Depends(require_admin)`).
- `app/routers/debug.py::debug_proxy` uses **Form 2** (`dependencies=[Depends(require_admin)]` on `@router.get(...)`) — minimum-diff change.

CONTEXT D-13/D-14 are aligned with CONTEXT's "Claude's Discretion / `require_admin` dependency shape" entry; RESEARCH §FastAPI Depends `require_user` raises 401 (CONTEXT mentions only 403 — planner picks behavior: the `/admin` D-13 wording "403 otherwise" covers both anon and non-admin; if `require_admin` calls `require_user` then anon raises 401 first. **Planner choice: either fold `require_user` into `require_admin` returning 403 for both, OR keep 401 for anon and 403 for non-admin. AUTH-09 test_admin_gate_three_states permits either ("anon→401 OR 403 / non-admin→403 / admin→200" per VALIDATION row).**)

`__all__` block: `__all__ = ["require_user", "require_admin"]` (export both even though Phase 2 only uses `require_admin` — Phase 4+ gets `require_user` for free).

---

### `app/dependencies/db.py` (dependency, async session factory injection)

**Analog:** the inline factory consumer in `app/middleware/session.py:161-163`:
```python
async with self.session_factory() as db:
    session_row = await get_session_by_id(db, session_id)
```

And the factory itself in `app/main.py:95-96`:
```python
_async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)
```

**Decisional note for planner:** CONTEXT §"Integration Points" calls out the option of moving `async_session_factory` from `app/main.py` to `app/db.py`. Recommended: leave it in `app/main.py` for Phase 2 (matches Phase 1 lock; SUMMARY note in `app/main.py:88-95` already anticipates a "future Phase 0 follow-up" relocation). `app/dependencies/db.py` imports the factory from `app.main`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a fresh AsyncSession per request.

    Imports the factory lazily to avoid a circular import (app.main imports
    routers, routers import this module).
    """
    from app.main import async_session_factory
    async with async_session_factory() as session:
        yield session
```

**Pattern source for "async generator dependency":** RESEARCH §SQLAlchemy 2.0 lines 371-373: "Plan-phase locks the factory injection pattern (likely a FastAPI dependency `Depends(get_async_session)` that yields from `async_session_factory()`)."

**Usage in routes** (the planner copies this shape into `app/routers/auth.py` POST handlers):
```python
from app.dependencies.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession

@router.post("/login")
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, db: AsyncSession = Depends(get_async_session)) -> ...:
    ...
```

---

### `app/routers/admin.py` (router, request-response, gated)

**Analog:** `app/routers/csp_report.py` (router scaffold) + `app/routers/debug.py` (single-route file)

**Imports pattern** (analog `app/routers/csp_report.py:47-55`):
```python
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request, Response

from app.events import CSP_VIOLATION
from app.rate_limit import limiter

log = structlog.get_logger(__name__)

router = APIRouter()
```

**For Phase 2 `app/routers/admin.py`** (drop structlog/events/rate_limit; add `Depends` + `require_admin` + `templates`):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import require_admin
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()
```

**Single-route shape** (analog `app/routers/debug.py:19-40`):
```python
@router.get("/debug/proxy", response_model=DebugProxyResponse)
async def debug_proxy(request: Request) -> DebugProxyResponse:
    """Echo what uvicorn ProxyHeadersMiddleware concluded about the request.
    ...
    """
    ...
    return DebugProxyResponse(...)
```

**Template-rendering shape** (analog `app/main.py:202-213` — the home route):
```python
@app.get("/")
def home(request: Request) -> object:
    """Render the placeholder home page (Phase 0)."""
    return request.app.state.templates.TemplateResponse(
        request=request, name="pages/index.html", context={}
    )
```

**Composed result for `app/routers/admin.py` (D-13):**
```python
@router.get("/admin")
def admin_stub(
    request: Request,
    user: User = Depends(require_admin),
) -> object:
    """D-13: Admin stub — 200 with literal body, gated by is_admin."""
    return templates.TemplateResponse(
        request=request, name="pages/admin.html", context={"user": user}
    )
```

**Router include in `app/main.py`** (analog `app/main.py:181-183`):
```python
app.include_router(csp_report_router.router)
app.include_router(auth_router.router)
app.include_router(debug_router.router)
```

Add: `app.include_router(admin_router.router)`.

---

### `app/routers/auth.py` (router REPLACEMENT — keep decorator/imports, replace bodies)

**Self-analog:** current `app/routers/auth.py` (lines 1-53). The planner KEEPS:
- The module docstring's "real bodies land in Phase 2" comment is replaced.
- The `from __future__ import annotations` line.
- The `structlog` + `APIRouter` + `Request` imports.
- `from app.events import ...` — extend to import `AUTH_LOGIN_SUCCEEDED, AUTH_LOGIN_FAILED, AUTH_LOGOUT, ADMIN_USER_CREATED`.
- `from app.rate_limit import LOGIN_LIMIT, SETUP_LIMIT, limiter`.
- `log = structlog.get_logger()` + `router = APIRouter()`.
- The `@router.post("/login", status_code=200)` + `@limiter.limit(LOGIN_LIMIT)` decorator stack (status code changes — 303 redirects use `RedirectResponse(status_code=303)` so the decorator's `status_code` can be dropped).

**Decorator pattern to PRESERVE** (analog `app/routers/auth.py:26-28`):
```python
@router.post("/login", status_code=200)
@limiter.limit(LOGIN_LIMIT)
async def login_stub(request: Request) -> dict:
```

**For Phase 2:** drop `status_code=200` (the response itself sets 303 or 200); keep `request: Request` (slowapi requires it for key derivation, per analog docstring + analog `app/routers/csp_report.py:120-123`). Add `db: AsyncSession = Depends(get_async_session)` and form fields.

**Form/Pydantic-body parsing pattern:** no existing form route in codebase. RESEARCH §"FastAPI — `RedirectResponse(status_code=303)`" (lines 375-405) shows the response shape; for the form body the planner uses either FastAPI's `Form(...)` parameters or a Pydantic `BaseModel` parsed via `Form` (the latter is cleaner — `app/schemas/debug.py` is the analog for Pydantic-model shape, then planner adds `app/schemas/auth.py` with `SetupForm`, `LoginForm` BaseModel classes; CONTEXT "Claude's Discretion / Password policy floor" locks the field constraints: username 3-32 `[A-Za-z0-9_-]`, password ≥12 chars, email `EmailStr` for setup-required).

**Response-with-cookie pattern** (verbatim from RESEARCH §FastAPI lines 397-401):
```python
response = RedirectResponse(url="/", status_code=303)
response.headers["Set-Cookie"] = build_session_cookie(signed_session_id)
return response
```

**Structured logging pattern** (analog `app/routers/auth.py:35-39`):
```python
log.info(
    AUTH_LOGIN_ATTEMPT,
    ip=request.client.host if request.client else "unknown",
    request_id=getattr(request.state, "request_id", "unknown"),
)
```

**For Phase 2 (per CONTEXT D-15 logging policy carried from Phase 1):**
- `AUTH_LOGIN_SUCCEEDED`: include `ip`, `request_id`, `user_id`.
- `AUTH_LOGIN_FAILED reason=bad_password`: include `ip`, `request_id`, `user_id` (the matched user). DO NOT include `attempted_username`.
- `AUTH_LOGIN_FAILED reason=user_not_found`: include `ip`, `request_id` only. NO `user_id`, NO `attempted_username`.
- `AUTH_LOGOUT`: include `ip`, `request_id`, `user_id`.
- `ADMIN_USER_CREATED`: include `ip`, `request_id`, `user_id` (the newly created admin), `created_by_user_id=None` (first admin).

**Template rendering for `/login` failure path** (re-render with D-07 generic error):
```python
from app.templates_setup import templates

return templates.TemplateResponse(
    request=request,
    name="pages/login.html",
    context={"error": "Invalid username or password.", "username": form.username},
    status_code=200,  # D-07: 200, not 401
)
```

---

### `app/routers/debug.py` (single-line modification)

**Self-analog:** current `app/routers/debug.py` (lines 19-20).

**Change** (`app/routers/debug.py:11`):
```python
from fastapi import APIRouter, Request
```
→
```python
from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import require_admin
```

**Change** (`app/routers/debug.py:19-20`):
```python
@router.get("/debug/proxy", response_model=DebugProxyResponse)
async def debug_proxy(request: Request) -> DebugProxyResponse:
```
→
```python
@router.get("/debug/proxy", response_model=DebugProxyResponse, dependencies=[Depends(require_admin)])
async def debug_proxy(request: Request) -> DebugProxyResponse:
```

Per RESEARCH §FastAPI Depends "Form 2" (line 449): "the existing route doesn't need the User object; minimum-diff change."

---

### `app/middleware/session.py` (in-place D-09/D-10 upgrade)

**Self-analog:** current `app/middleware/session.py:177-191` (the existing branch where Phase 1 sets the stub).

**Pattern to REPLACE** (analog `app/middleware/session.py:177-183`):
```python
else:
    scope["state"]["session"] = session_row
    # TODO Phase 2: replace stub with full User row
    # lookup. /debug/whoami (the only Phase 1
    # consumer of request.state.user) treats the
    # presence of a dict as "authenticated" for now.
    scope["state"]["user"] = {"user_id": session_row.user_id}
```

**Pattern to INSERT** (composed from `app/services/sessions.py:118-126` `get_session_by_id` pattern + the CONTEXT D-10 fail-closed branches):
```python
else:
    # D-09: load FULL User row in the same async-session scope
    # already open for the session lookup.
    from app.models.user import User  # local import: keep model out
                                       # of the middleware module's import
                                       # graph until needed.
    result = await db.execute(select(User).where(User.id == session_row.user_id))
    user_row = result.scalar_one_or_none()

    if user_row is None or not user_row.is_active:
        # D-10: deleted or deactivated → treat as no session.
        # Mirror the existing expired-session branch (lines 170-176).
        await delete_session(db, session_id)
        clear_cookie = True
        scope["state"]["user"] = None
        scope["state"]["session"] = None
    else:
        scope["state"]["session"] = session_row
        scope["state"]["user"] = user_row

        # Write-throttled sliding refresh (T-04-06 mitigation) —
        # UNCHANGED from Phase 1.
        elapsed = (
            datetime.now(UTC) - session_row.last_seen
        ).total_seconds()
        if elapsed > self.refresh_threshold_seconds:
            await refresh_last_seen(db, session_id)
```

**New import** (add to `app/middleware/session.py:37` block):
```python
from sqlalchemy import select
```

(plus the local `from app.models.user import User` inside the `else` block per the existing model-keep-out-of-import-graph convention).

**Existing branches that DO NOT change** (analog `app/middleware/session.py:146-176`): the "no cookie", "tampered signature", "no row", and "expired row" paths are all already fail-closed. D-10 simply extends the same idiom to the deleted/deactivated-user branch.

---

### `app/csrf.py` (APPEND `CSRFFormFieldShim`)

**Existing constants/config preserved** (`app/csrf.py:1-87`) — no edits to existing lines. Append the new class + needed imports below the existing `csrf_middleware_kwargs` function.

**Pure-ASGI middleware shell pattern** (analog `app/middleware/fragment_cache.py:53-112`):
```python
class FragmentCacheHeadersMiddleware:
    """Apply D-11..D-13 cache-header policy to every HTTP response.
    ...
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        static_prefixes: tuple[str, ...] = ("/static/",),
    ) -> None:
        self.app = app
        self.static_prefixes = static_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Non-HTTP scopes (lifespan, websocket) — pass through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Static-asset bypass — StaticFiles owns its cache headers.
        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in self.static_prefixes):
            await self.app(scope, receive, send)
            return
        ...
        await self.app(scope, receive, send_wrapper)
```

**For Phase 2 `CSRFFormFieldShim` adapt this shell:**
- `if scope["type"] != "http"` — pass-through.
- `if scope.get("method") != "POST"` — pass-through (D-15: GET passthrough untouched).
- Read content-type from `scope["headers"]` via the raw-bytes inspection idiom in `app/middleware/fragment_cache.py:89-93`:
  ```python
  hx_request = False
  for name, value in scope.get("headers", []):
      if name == b"hx-request" and value.lower() == b"true":
          hx_request = True
          break
  ```
  → translate to checking `b"content-type"` starts with `b"application/x-www-form-urlencoded"` or `b"multipart/form-data"`.
- If header `b"x-csrf-token"` already present → pass-through (D-15 idempotency).
- Else: body-replay branch (see below) → parse form → inject `(b"x-csrf-token", value.encode())` into `scope["headers"]` → call `await self.app(scope, replay_receive, send)`.

**Body-replay ASGI pattern** (NO IN-REPO ANALOG — RESEARCH §1 and Starlette's standard idiom):
```python
# Buffer the entire request body by repeatedly calling receive() until
# more_body is False; then build a fresh receive callable that re-emits
# the buffered chunks in order.
chunks: list[bytes] = []
while True:
    message = await receive()
    if message["type"] != "http.request":
        # disconnect / other → re-emit and stop
        chunks_to_replay = list(chunks)
        chunks_to_replay.append(b"")  # signal; planner refines
        break
    chunks.append(message.get("body", b""))
    if not message.get("more_body", False):
        break

# Reconstruct an async receive that walks the buffered list.
async def replay_receive() -> Message:
    if chunks:
        chunk = chunks.pop(0)
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": bool(chunks),
        }
    return {"type": "http.request", "body": b"", "more_body": False}
```

**Important nuance for multipart preservation (D-15 test_multipart_body_preserved):** the planner MUST preserve chunk boundaries and `more_body` flags so the multipart parser downstream sees the same byte sequence as if no middleware intervened. The buffer-and-replay above does that as long as each `http.request` event is kept in original order.

**Form parsing for token extraction:** parse the concatenated body as `application/x-www-form-urlencoded` using stdlib `urllib.parse.parse_qs` (for urlencoded) — for multipart, the planner uses `email.parser` or, simpler, builds a one-off Starlette `Request` against the buffered body purely to call `await request.form()` and pull the `X-CSRF-Token` field. RESEARCH §1 Option (b) sketch (lines 254-269) shows the same approach.

**Header injection pattern** (extracted from `app/middleware/security_headers.py:221-224`):
```python
existing = list(message.get("headers", []))
existing.append((b"content-security-policy", csp_value))
existing.extend(STATIC_HEADERS)
message["headers"] = existing
```

For Phase 2 (request-side, not response-side): mutate `scope["headers"]` BEFORE calling `await self.app(scope, replay_receive, send)`:
```python
scope_headers = list(scope.get("headers", []))
scope_headers.append((b"x-csrf-token", token_value.encode("ascii")))
scope["headers"] = scope_headers
```

**Mount-order pattern** (analog `app/main.py:173-178`):
```python
# Middleware stack — last added is OUTERMOST (Starlette reverse-of-add).
app.add_middleware(SessionMiddleware, session_factory=async_session_factory)
app.add_middleware(CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY))
app.add_middleware(FragmentCacheHeadersMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
```

**For Phase 2 (CONTEXT D-15 locks the new order):**
```python
app.add_middleware(SessionMiddleware, session_factory=async_session_factory)
app.add_middleware(CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY))
app.add_middleware(CSRFFormFieldShim)   # NEW — outside CSRFMiddleware
app.add_middleware(FragmentCacheHeadersMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
```

Per CONTEXT D-15: "on a request `RequestContext` → `SecurityHeaders` → `FragmentCache` → **shim** → `CSRFMiddleware` → `SessionMiddleware` → route".

**Import addition in `app/main.py`** (analog `app/main.py:66`):
```python
from app.csrf import csrf_middleware_kwargs
```
→
```python
from app.csrf import CSRFFormFieldShim, csrf_middleware_kwargs
```

---

### `app/templates/pages/setup.html` and `pages/login.html` (NEW templates)

**Analog:** `app/templates/pages/index.html` (extends base.html) + `app/templates/base.html` (CSRF token meta surface line 10; CSP nonce pattern line 14).

**Page skeleton pattern** (analog `app/templates/pages/index.html:1-9`):
```html
{% extends "base.html" %}
{% block page_title %}Bootstrap{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">Snobbery</h1>
    <p>Snobbery — setup pending. POST /setup once auth lands.</p>
  </main>
{% endblock %}
```

**CSRF cookie read pattern** (analog `app/templates/base.html:10`):
```html
<meta name="csrf-token" content="{{ request.cookies.get('csrftoken', '') }}">
```

**For Phase 2 `setup.html` form (CONTEXT D-02 / D-15)**:
```html
{% extends "base.html" %}
{% block page_title %}Setup{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">First-time setup</h1>
    <p class="mt-2 text-sm">This creates the household admin account.</p>
    {% if error %}<p class="mt-4 text-red-700">{{ error }}</p>{% endif %}
    <form method="post" action="/setup" class="mt-6 flex flex-col gap-4">
      <!-- D-15: CSRFFormFieldShim hoists this field to the X-CSRF-Token header -->
      <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
      <label>Username <input name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_-]+"></label>
      <label>Email <input name="email" type="email" required></label>
      <label>Password <input name="password" type="password" required minlength="12"></label>
      <button type="submit">Create admin</button>
    </form>
  </main>
{% endblock %}
```

**For Phase 2 `login.html`** (CONTEXT "Claude's Discretion / Login template ergonomics"):
```html
{% extends "base.html" %}
{% block page_title %}Sign in{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">Sign in to Snobbery</h1>
    {% if error %}<p class="mt-4 text-red-700">{{ error }}</p>{% endif %}
    <form method="post" action="/login" class="mt-6 flex flex-col gap-4">
      <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
      <label>Username <input name="username" required value="{{ username or '' }}"></label>
      <label>Password <input name="password" type="password" required></label>
      <button type="submit">Sign in</button>
    </form>
  </main>
{% endblock %}
```

**No `|safe` allowed** — CI grep in `tests/ci/test_no_unsafe_jinja.py` enforces (per CONTEXT §"Integration Points"). Default `autoescape` ON via `app/templates_setup.py:43`.

---

### `app/templates/pages/admin.html` (one-line stub)

**Analog:** `app/templates/pages/index.html` (full content lines 1-9).

**For Phase 2** (CONTEXT D-13 literal body):
```html
{% extends "base.html" %}
{% block page_title %}Admin{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">Admin</h1>
    <p>Admin (stub) — wiring lands in Phase 9.</p>
  </main>
{% endblock %}
```

---

### `app/templates/pages/index.html` (augment with footer)

**Self-analog:** current `app/templates/pages/index.html:1-9`.

**Pattern to INSERT inside the existing `{% block content %}`** (CONTEXT "Claude's Discretion / Where does the sign-out button live in Phase 2"):
```html
{% extends "base.html" %}
{% block page_title %}Bootstrap{% endblock %}
{% block content %}
  <main class="mx-auto max-w-prose px-6 py-12">
    <h1 class="text-2xl font-semibold">Snobbery</h1>
    <p>Snobbery — setup pending. POST /setup once auth lands.</p>
    <footer class="mt-12 text-sm">
      {% if request.state.user %}
        Signed in as {{ request.state.user.username }}
        <form method="post" action="/logout" class="inline">
          <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
          <button type="submit">Sign out</button>
        </form>
      {% else %}
        <a href="/login">Sign in</a>
      {% endif %}
    </footer>
  </main>
{% endblock %}
```

**Critical:** `request.state.user` is now a `User` SQLAlchemy model instance (D-09), NOT a `dict`. Access `.username` not `["username"]`.

---

## Test File Pattern Assignments

### `tests/services/test_auth.py` (NEW)

**Analog:** `tests/services/test_sessions.py`

**Lazy-import + skip pattern** (analog `tests/services/test_sessions.py:22-29`):
```python
def test_regenerate(db_session) -> None:
    """AUTH-05 / D-10: regenerate_session deletes old row + mints new UUID."""
    try:
        from app.services.sessions import regenerate_session
    except ImportError:
        pytest.skip(
            "Wave 1 dependency: app.services.sessions.regenerate_session (Plan 04)"
        )
```

**For Phase 2** the planner uses non-skipping imports (Phase 2 owns these symbols; Wave 0 of Phase 2 IS this file). `test_argon2_roundtrip`, `test_password_hasher_params`, `test_dummy_verify_timing`.

For `test_dummy_verify_timing` (VALIDATION row "AUTH-03 unknown user + dummy-verify timing"): the planner asserts a wall-clock floor via `time.perf_counter()` deltas — there is no in-repo analog for timing assertions.

---

### `tests/services/test_setup.py` (NEW — race fixture)

**Analog:** `tests/services/test_sessions.py` for the lazy-import shape; no in-repo analog for the `asyncio.gather` concurrent-race pattern (CONTEXT §"AUTH-02 concurrent race" + VALIDATION row "AUTH-02 concurrent race").

**Race-fixture sketch** (no analog; planner composes):
```python
import asyncio
import httpx

@pytest.mark.asyncio
async def test_setup_concurrent_race(async_client, fresh_db) -> None:
    # Two concurrent POST /setup with the SAME credentials and a primed CSRF
    # cookie+header pair (from a GET /setup first).
    primer = await async_client.get("/setup")
    token = primer.cookies["csrftoken"]
    headers = {"X-CSRF-Token": token}
    cookies = {"csrftoken": token}
    body = {"username": "admin", "email": "a@b.c", "password": "twelve-chars-min"}
    r1, r2 = await asyncio.gather(
        async_client.post("/setup", data=body, headers=headers, cookies=cookies),
        async_client.post("/setup", data=body, headers=headers, cookies=cookies),
    )
    # Exactly one of the two POSTs sees the empty setup; the other observes
    # setup_completed=true and 302s to /login (D-01 + D-03).
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [302, 303], statuses  # one redirect-to-login, one auto-login
    # Exactly ONE users row.
    # ... (assert via fresh_db fixture's underlying connection)
```

---

### `tests/routers/test_auth.py` (NEW — REPLACES `test_auth_stub.py`)

**Analog:** `tests/middleware/test_csrf.py` (`_csrf_pair` helper, lines 50-73) for the CSRF-paired POST shape; `tests/routers/test_auth_stub.py` (entire file, lines 30-120) for the slowapi-respecting POST scaffold.

**CSRF helper pattern to copy** (analog `tests/middleware/test_csrf.py:60-69`):
```python
primer = client.get("/")
token = primer.cookies.get("csrftoken")
if not token:
    pytest.skip("CSRF cookie 'csrftoken' not yet set by Wave 1 middleware")
response = client.post(
    "/login",
    data={"username": "x", "password": "y"},
    headers={"X-CSRF-Token": token},
    cookies={"csrftoken": token},
)
```

**Cookie-attribute assertion pattern** (analog `tests/middleware/test_session.py:85-91`):
```python
set_cookies = response.headers.get_list("set-cookie") if hasattr(
    response.headers, "get_list"
) else [response.headers.get("set-cookie", "")]
cleared = any(
    "session_id=" in c and ("Max-Age=0" in c or "max-age=0" in c)
    for c in set_cookies
)
```

For Phase 2 `test_session_cookie_attributes` (VALIDATION AUTH-06): assert `HttpOnly`, `Secure`, `SameSite=Lax`, `Max-Age=2592000` substrings in the Set-Cookie header — same scan-with-`any()` shape.

**xfail/note pattern for TestClient limitations** (analog `tests/routers/test_auth_stub.py:43-53`):
```python
@pytest.mark.xfail(
    reason=(
        "Starlette TestClient always reports request.client.host == 'testclient', "
        "so slowapi keys all six requests to the same bucket and rate-limit fires "
        "on the FIRST request rather than the 6th. ..."
    ),
    strict=False,
)
```

Phase 2 inherits this caveat: any `test_login_csrf_blocked` / `test_logout_csrf_blocked` test that depends on `--proxy-headers` IP keying may need the same xfail. CONTEXT does NOT call out a specific need but the planner should be ready to apply this pattern.

**Note on the delete-the-stub-file commit:** VALIDATION line 91 says "replaces `tests/routers/test_auth_stub.py` (delete the stub file in the same plan that creates this one)". The planner ships both ops in one commit.

---

### `tests/routers/test_admin.py` (NEW)

**Analog:** `tests/routers/test_debug_proxy.py` (line 1-66 — router test scaffold).

**Require helper pattern** (analog `tests/routers/test_debug_proxy.py:22-26`):
```python
def _require_debug_proxy() -> None:
    try:
        from app.routers.debug import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.routers.debug (Plan 08)")
```

For Phase 2 `_require_admin()` → import `app.routers.admin`.

**Three-state test shape (VALIDATION AUTH-09):** the planner uses `seeded_admin_user` / `seeded_regular_user` fixtures (planner ADDS to `tests/conftest.py`) to set `session_id` cookies — the test calls `client.get("/admin")` three ways:
1. Anonymous (no cookie) — assert 401 or 403.
2. Regular user (`seeded_regular_user`) — assert 403.
3. Admin (`seeded_admin_user`) — assert 200 + body contains "Admin (stub) — wiring lands in Phase 9".

---

### `tests/dependencies/__init__.py` (package marker)

**Analog:** `tests/services/__init__.py` — empty file. Phase 2 creates an empty `tests/dependencies/__init__.py` matching.

---

### `tests/dependencies/test_auth.py` (NEW — unit test for `require_admin`)

**Analog:** None of the existing tests call FastAPI `Depends`-callables directly. The closest pattern is `tests/middleware/test_session.py:42-73` `test_refresh_throttling` (which calls a helper directly without HTTP).

**Direct-callable unit pattern** (compose from FastAPI Depends mechanics):
```python
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dependencies.auth import require_admin

def _make_request(user) -> Request:
    """Build a minimal Request with state.user set."""
    scope = {"type": "http", "state": {"user": user}}
    req = Request(scope)
    return req

def test_require_admin_raises_for_anon() -> None:
    req = _make_request(None)
    with pytest.raises(HTTPException) as exc:
        require_admin(req)
    assert exc.value.status_code in (401, 403)

def test_require_admin_raises_for_non_admin() -> None:
    class FakeUser:
        is_admin = False
    req = _make_request(FakeUser())
    with pytest.raises(HTTPException) as exc:
        require_admin(req)
    assert exc.value.status_code == 403

def test_require_admin_returns_user_for_admin() -> None:
    class FakeUser:
        is_admin = True
    user = FakeUser()
    req = _make_request(user)
    result = require_admin(req)
    assert result is user
```

---

### `tests/middleware/test_csrf_form_shim.py` (NEW — 5 cases per VALIDATION D-15)

**Analog:** `tests/middleware/test_csrf.py` (1-126) for the CSRF-test scaffold; the `_csrf_pair` shape (lines 60-69) is the planner's starting point.

**Header-passthrough case** (`test_header_passthrough` — VALIDATION row D-15 first item): primer GET to obtain cookie, then POST with BOTH the header AND the form field — assert the header value wins (idempotent). Reuse `_csrf_pair` from `tests/middleware/test_csrf.py:60-69`.

**Form-field hoist case** (`test_form_field_hoisted`): primer GET, then POST `application/x-www-form-urlencoded` with the field ONLY (no header). Assert response is the success path (303 redirect after Phase 2 `/login` real handler exists; for Wave 0 the assertion is "not 403").

**Multipart preservation case** (`test_multipart_body_preserved`): build a multipart body with a small binary blob + the `X-CSRF-Token` field; POST to a planner-provided fixture endpoint that echoes the body hash; assert input-hash == echoed-hash. NO IN-REPO ANALOG — planner composes a small ad-hoc echo route inside the test file (Starlette router stub).

**GET-passthrough case** (`test_get_passthrough`): GET request never touches the shim — assert `scope["headers"]` is identical pre/post. Test via a mock ASGI app captured in a list.

**JSON-passthrough case** (`test_json_passthrough`): POST with `Content-Type: application/json` and the X-CSRF-Token header absent — shim does NOT inject (the field doesn't exist in JSON); the downstream `CSRFMiddleware` 403s, which is the desired behavior (per CONTEXT D-15: "a real API client is responsible for setting the header itself").

---

### `tests/test_phase02_smoke.py` (NEW — cold-container E2E)

**Analog:** `tests/routers/test_csp_report.py` (TestClient happy-path scaffold) + `tests/test_healthz.py` (lifespan-aware fixture usage).

**Lifespan-aware client pattern** (analog `tests/conftest.py:75-95`):
```python
@pytest.fixture
def client(app: Any) -> Iterator[Any]:
    """Sync ``starlette.testclient.TestClient`` wrapping the FastAPI app.
    ...
    Yields inside a context manager so FastAPI's lifespan startup/shutdown runs.
    ...
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import DBAPIError, OperationalError

    try:
        with TestClient(app) as _client:
            yield _client
    except (OperationalError, DBAPIError, ConnectionError, OSError) as exc:
        pytest.skip(...)
```

For Phase 2 smoke: use the existing `client` fixture (already lifespan-aware). The smoke test walks:
1. GET `/setup` → 200 + form rendered.
2. POST `/setup` with valid form → 303 → `/`.
3. Verify Set-Cookie session_id on the 303 response.
4. Follow to GET `/` → 200 + footer contains "Signed in as <username>".
5. POST `/logout` with CSRF pair → 303 → `/login`.
6. Verify session_id cookie cleared (Max-Age=0).

---

### `tests/middleware/test_session.py` (EXTEND with D-09 / D-10 cases)

**Self-analog:** existing file lines 1-97. Add three new tests using the same lazy-import + skip pattern:

- `test_state_user_shape` (D-09 / VALIDATION row): authenticated request resolves `request.state.user` to a `User` ORM instance, NOT a dict. Probe via a debug route or by inspecting an ASGI scope after manually running the middleware.
- `test_deactivated_user_fail_closed` (D-10 / VALIDATION row): seed an `is_active=false` user + a live session row → next request clears cookie + DELETEs the session row.
- `test_deleted_user_fail_closed` (D-10 / VALIDATION row): seed a session row pointing at a DELETEd user_id → next request clears cookie + DELETEs the session row.

The fixture shape inherits from the existing file — no new helpers needed beyond `seeded_*_user` from conftest.

---

### `tests/routers/test_debug_proxy.py` (EXTEND with admin-gate cases)

**Self-analog:** existing file lines 1-66.

Add `test_debug_proxy_admin_only`:
- Anonymous → 401/403.
- Regular user → 403.
- Admin → 200 + existing JSON body shape (the 4-key shape from `test_default_returns_shape`).

The planner reuses the existing `_require_debug_proxy()` helper (line 22) and adds a `_require_admin_router()` helper next to it.

---

### `tests/test_logging.py` (EXTEND with D-15 reason-field assertions)

**Self-analog:** existing file lines 156-203 (`test_redactor_scrubs_sensitive_keys` — capture-handler pattern). The planner adds:

- `test_login_failed_no_username_on_user_not_found`: POST `/login` with a username that doesn't exist; capture the log via `_attach_capture_handler()` (lines 37-55); assert the emitted record has `event=auth.login_failed`, `reason=user_not_found`, NO `user_id`, NO `attempted_username`.
- `test_login_failed_includes_user_id_on_bad_password`: POST `/login` with a real username + wrong password; assert the record has `event=auth.login_failed`, `reason=bad_password`, has `user_id`, NO `attempted_username`.

Reuse `_clean_logging_state` autouse fixture (lines 58-75) and `_last_json_record` helper (lines 78-82).

---

### `tests/conftest.py` (EXTEND with new fixtures)

**Self-analog:** existing fixtures `app` (lines 56-72), `client` (lines 75-95), `db_session` (lines 98-127), `_reset_rate_limiter` autouse (lines 130-147), `forwarded_headers` (lines 150-161).

**New fixtures the planner adds:**

- `async_client`: `httpx.AsyncClient` against the ASGI app — required by AUTH-02 concurrent race. Pattern: `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")` inside an `async def` fixture or pytest-asyncio scope. No in-repo analog — planner composes from httpx docs.

- `fresh_db`: per-test truncate of `users` + reset `app_settings.setup_completed = "false"`. Pattern: open a sync connection via `app.db.SessionLocal()`, run two `text()` statements in a transaction, commit. No in-repo analog — but follow the `app/main.py:130-132` lifespan smoke pattern (`with engine.connect() as conn: conn.execute(text("..."))`).

- `seeded_admin_user`: creates an `is_admin=true` user + opens a live session via `regenerate_session(db, None, user.id)` + signs the cookie via `sign_session_id()` + returns the cookie value the test sets on `client.cookies`. Composition of `app/services/auth.py::hash_password` (Phase 2 new) + `app/services/sessions.py::regenerate_session` + `app/signing.py::sign_session_id`.

- `seeded_regular_user`: same as above with `is_admin=false`.

**Autouse-reset pattern (analog `tests/conftest.py:130-147`):**
```python
@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Clear slowapi's in-memory bucket before each test. ..."""
    yield
    try:
        from app.rate_limit import limiter
        limiter.reset()
    except (ImportError, AttributeError):
        pass
```

Planner considers whether `fresh_db` should be autouse (probably YES for the Phase 2 subset to enforce the AUTH-01 "zero users" precondition between tests).

---

## Shared Patterns

### Authentication (request.state.user access)

**Source:** `app/middleware/session.py:177-183` (Phase 1 stub) + Phase 2 D-09 upgrade (in-place edit).

**Apply to:** all Phase 2 routers + the index template footer.

**After D-09 the contract becomes:**
- `request.state.user` is `User` (SQLAlchemy ORM) or `None`.
- `request.state.session` is `Session` (SQLAlchemy ORM) or `None`.

Read with `user.username`, `user.is_admin`, NOT with subscript access. All Phase 2 templates and route handlers consume the new shape.

---

### CSRF token rendering in templates

**Source:** `app/templates/base.html:10`:
```html
<meta name="csrf-token" content="{{ request.cookies.get('csrftoken', '') }}">
```

**Apply to:** every form template Phase 2 ships — `setup.html`, `login.html`, the `pages/index.html` footer's logout form, the eventual `pages/admin.html` (no form in Phase 2 but Phase 9 will add).

**Form-field shape (per D-15 + the locked `CSRF_HEADER_NAME = "X-CSRF-Token"` constant):**
```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

The shim hoists this into the request header; downstream `starlette-csrf` 3.0 reads it from there.

---

### Structured logging with event constants + D-15 reason policy

**Source:** `app/events.py` (constants) + `app/routers/auth.py:35-39` (Phase 1 stub emit shape) + CONTEXT D-15 (Phase 1 carried) for the per-reason payload policy.

**Apply to:** all Phase 2 auth route handlers + the `setup` service. Always import event names from `app.events` (never hard-code). Always include `ip`, `request_id`. Include `user_id` per D-15 reason matrix. NEVER include `attempted_username`. NEVER log the password.

**Verbatim emit shape** (analog `app/routers/auth.py:35-39`):
```python
log.info(
    AUTH_LOGIN_ATTEMPT,
    ip=request.client.host if request.client else "unknown",
    request_id=getattr(request.state, "request_id", "unknown"),
)
```

Phase 2 replaces `AUTH_LOGIN_ATTEMPT` with `AUTH_LOGIN_SUCCEEDED` / `AUTH_LOGIN_FAILED` / `AUTH_LOGOUT` / `ADMIN_USER_CREATED` per code path.

---

### Pure-ASGI middleware shape (do NOT use `BaseHTTPMiddleware`)

**Source:** `app/middleware/__init__.py:1-20` (package docstring locks the rule) + `app/middleware/fragment_cache.py:53-112` (template) + `app/middleware/security_headers.py:160-228` (template).

**Apply to:** the new `CSRFFormFieldShim` class in `app/csrf.py` (D-15).

**Skeleton (verbatim from `app/middleware/fragment_cache.py:73-77`):**
```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    # Non-HTTP scopes (lifespan, websocket) — pass through untouched.
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return
```

**Header inspection pattern (analog `app/middleware/fragment_cache.py:89-93`):**
```python
hx_request = False
for name, value in scope.get("headers", []):
    if name == b"hx-request" and value.lower() == b"true":
        hx_request = True
        break
```

---

### Cookie-value building from the locked Phase 1 helpers

**Source:** `app/services/sessions.py:152-182` (`build_session_cookie`, `build_session_clear_cookie`) + `app/signing.py:32-38` (`sign_session_id`).

**Apply to:** every Phase 2 success path that mints a session (login, setup auto-login) and every path that clears one (logout, fail-closed branches).

**Verbatim usage (from RESEARCH §FastAPI lines 397-401):**
```python
response = RedirectResponse(url="/", status_code=303)
response.headers["Set-Cookie"] = build_session_cookie(signed_session_id)
return response
```

For `/logout`: `response.headers["Set-Cookie"] = build_session_clear_cookie()`.

---

### Async-session-factory dependency injection

**Source:** `app/main.py:95-96` (the factory) + `app/middleware/session.py:161` (the usage pattern).

**Apply to:** all Phase 2 route handlers that need DB access. The new `app/dependencies/db.py::get_async_session` is the FastAPI dependency wrapper. The middleware uses the factory directly; routes use the dependency.

---

### Test scaffold: `try/except ImportError` skip pattern

**Source:** `tests/services/test_sessions.py:24-29`, `tests/middleware/test_csrf.py:40-43`, `tests/routers/test_auth_stub.py:21-28` (used everywhere).

**Apply to:** Wave 0 of every new Phase 2 test file. By the time the test runs in green-Wave-1, the import succeeds and the test runs.

```python
def _require_<module>() -> None:
    try:
        from app.<module> import <symbol>  # noqa: F401
    except ImportError:
        pytest.skip("Phase 2 dependency: app.<module>.<symbol>")
```

---

## No Analog Found

Files with no close in-repo match. Planner uses RESEARCH.md / external docs:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/dependencies/auth.py` | dependency | request-response | No FastAPI `Depends`-callable exists yet in the codebase. RESEARCH §"FastAPI — `Depends(require_admin)` pattern" lines 407-459 is the canonical source. |
| `CSRFFormFieldShim` body-replay branch (inside `app/csrf.py`) | middleware (request body buffering) | request transform | No `more_body` / receive-replay middleware exists in the codebase. Pattern source: Starlette's own `Request._receive` body-buffering idiom + RESEARCH §1 Option (b) sketch lines 254-269. |

These two files are flagged for the planner to lean on RESEARCH excerpts rather than copy from existing code.

---

## Metadata

**Analog search scope:** `app/`, `app/routers/`, `app/middleware/`, `app/services/`, `app/templates/`, `app/models/`, `tests/`, `tests/routers/`, `tests/middleware/`, `tests/services/`.
**Files scanned:** 38 application files + 19 test files.
**Pattern extraction date:** 2026-05-17.
