# Phase 9: Admin - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 20 (new/modified files for this phase)
**Analogs found:** 20 / 20

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/routers/admin/__init__.py` | route | request-response | `app/routers/admin.py` | exact (expand stub) |
| `app/routers/admin/users.py` | controller | CRUD | `app/routers/roasters.py` | exact |
| `app/routers/admin/credentials.py` | controller | request-response | `app/routers/roasters.py` | role-match |
| `app/routers/admin/settings_editor.py` | controller | CRUD | `app/routers/roasters.py` | role-match |
| `app/routers/admin/backups.py` | controller | file-I/O | `app/routers/photos.py` | role-match |
| `app/routers/admin/system.py` | controller | request-response | `app/routers/admin.py` + `app/routers/roasters.py` | role-match |
| `app/templates/admin_base.html` | template | request-response | `app/templates/base.html` | role-match |
| `app/templates/pages/admin.html` | template | request-response | `app/templates/pages/roasters.html` | role-match (expand stub) |
| `app/templates/pages/admin_users.html` | template | CRUD | `app/templates/pages/roasters.html` | exact |
| `app/templates/pages/admin_credentials.html` | template | request-response | `app/templates/pages/roasters.html` | role-match |
| `app/templates/pages/admin_settings.html` | template | CRUD | `app/templates/pages/roasters.html` | role-match |
| `app/templates/pages/admin_backups.html` | template | file-I/O | `app/templates/pages/roasters.html` | role-match |
| `app/templates/pages/admin_system.html` | template | request-response | `app/templates/pages/roasters.html` | role-match |
| `app/templates/fragments/admin_user_row.html` | template | CRUD | `app/templates/fragments/roaster_row.html` | exact |
| `app/templates/fragments/admin_user_form.html` | template | CRUD | `app/templates/fragments/roaster_form.html` | exact |
| `app/templates/fragments/admin_setting_row.html` | template | CRUD | `app/templates/fragments/roaster_form.html` | role-match |
| `app/templates/fragments/admin_backup_list.html` | template | file-I/O | `app/templates/fragments/roaster_list.html` | role-match |
| `app/templates/fragments/admin_backup_result.html` | template | file-I/O | `app/templates/fragments/roaster_row.html` | role-match |
| `app/events.py` | config | event-driven | `app/events.py` (self — extend) | exact |
| `app/templates/pages/home.html` | template | request-response | self (modify existing) | exact |

---

## Pattern Assignments

---

### `app/routers/admin/__init__.py` (route package init)

**Analog:** `app/routers/admin.py` (Phase 2 stub)

The stub router is currently a single file at `app/routers/admin.py`. Phase 9 converts it into a sub-package. The `__init__.py` re-exports the router that `app/main.py` already imports.

**Current stub — full file** (`app/routers/admin.py` lines 17-46):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies.auth import require_admin
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin_stub(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="pages/admin.html",
        context={"user": user},
    )
```

**Router registration in `app/main.py`** (line 231):
```python
app.include_router(admin_router.router)
```

The import alias in `main.py` is `admin_router` — the `__init__.py` must export `router` so `admin_router.router` resolves. Sub-module routers (users, credentials, etc.) are included on this router using `router.include_router(...)`.

**No prefix on the top-level router** (current pattern). Sub-routes use explicit `/admin/...` paths OR add `prefix="/admin"` to the top-level router. Recommend `prefix="/admin"` on the package router for cleanliness when expanding — this is a deviation from the stub (which has no prefix and uses the full path `/admin` in the decorator).

---

### `app/routers/admin/users.py` (controller, CRUD)

**Analog:** `app/routers/roasters.py`

**Imports pattern** (`app/routers/roasters.py` lines 60-76):
```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.roaster import RoasterCreate
from app.services import roasters as roasters_service
from app.services.form_validation import DuplicateNameError, errors_by_field
from app.templates_setup import templates
```

For `users.py` adapt as:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.orm import Session

from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.session import Session as SessionModel
from app.models.user import User
from app.templates_setup import templates
from app import events
```

**Auth pattern — require_admin on every route** (`app/dependencies/auth.py` lines 48-62):
```python
def require_admin(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return user
```

Every handler signature: `user: User = Depends(require_admin)  # noqa: B008`

**Core sync CRUD pattern** (`app/routers/roasters.py` lines 128-147):
```python
@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),    # noqa: B008
) -> Response:
    rows = db.execute(select(User)).scalars().all()
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_list.html",
            context={"users": rows},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_users.html",
        context={"users": rows},
    )
```

**Form POST pattern — CSRF strip + Pydantic validation** (`app/routers/roasters.py` lines 203-265):
```python
@router.post("", response_class=HTMLResponse)
async def create_user(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    try:
        form = UserCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={"values": raw, "errors": errors_by_field(exc), "mode": "create"},
            status_code=200,
        )
    # ... service call, then render fragment
```

**DEVIATION — async def for session-deletion handlers:**

Session-delete handlers (is_admin toggle, deactivate, reactivate, hard-delete) must be `async def` because `sessions.py` is async-only. Use `async with async_session_factory() as async_db:` for the async portion, keeping sync DB work via `get_session`. All other handlers remain `sync def`.

**MANDATORY CSRF read — even when the body is unused:** Every state-changing POST (including deactivate/reactivate, which read no other form fields) MUST call `form_data = await request.form()` and strip `{"X-CSRF-Token"}`. The `CSRFFormFieldShim` hoists the `X-CSRF-Token` field out of the form body; a handler that never awaits `request.form()` is rejected by `CSRFMiddleware` with 403 BEFORE any guard runs. This is why these handlers are `async def` regardless of the session-delete work.

**Async session-delete pattern** (from RESEARCH.md Q4):
```python
from sqlalchemy import delete as sql_delete
from app.models.session import Session as SessionModel
from app.main import async_session_factory

@router.post("/{target_id}/toggle-admin", response_class=HTMLResponse)
async def toggle_is_admin(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),          # noqa: B008
) -> Response:
    # 0. CSRF — mandatory even though no form fields are read here
    form_data = await request.form()
    _ = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}
    # 1. D-16 last-admin guard — sync DB
    # SELECT ... FOR UPDATE within a transaction
    # ...
    # 2. Update is_admin — sync DB
    # ...
    # 3. Delete target's sessions — async DB
    async with async_session_factory() as async_db:
        await async_db.execute(
            sql_delete(SessionModel).where(SessionModel.user_id == target_id)
        )
        await async_db.commit()
    # 4. Render fragment response
```

**D-15 hard-delete guard pattern:**
```python
# Check brew_sessions count before DELETE — application-level belt
from app.models.brew_session import BrewSession
count = db.execute(
    select(func.count()).where(BrewSession.user_id == target_id)
).scalar_one()
if count > 0:
    raise HTTPException(status_code=409, detail="User has brew sessions — deactivate instead.")
```

**Error handling pattern** (`app/routers/roasters.py` lines 243-265):
```python
    try:
        # ... service call
    except DuplicateNameError:
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={"values": raw, "errors": {"name": "Username already exists."}, "mode": "create"},
            status_code=200,
        )
```

For `IntegrityError` (RESTRICT FK on brew_sessions), catch `sqlalchemy.exc.IntegrityError` as a backstop after the application-level count guard.

---

### `app/routers/admin/credentials.py` (controller, request-response)

**Analog:** `app/routers/roasters.py` (form POST pattern)

**Imports deviation** — adds credentials service, never the decrypted key in context:
```python
from app.services import credentials as cred_service
from app.services.credentials import ProviderCredential
```

**GET (list/display) vs POST (set) — two distinct contexts:**

The GET `/credentials` LIST handler renders display rows for BOTH providers,
including disabled ones. It MUST query the `ApiCredential` model directly for
`last_four`, `model_name`, `is_enabled` and MUST NOT call
`get_provider_credential()` — that helper decrypts the key (SEC-6 risk) AND
returns `None` for disabled/keyless rows (so disabled providers would silently
vanish from the list). `get_provider_credential()` is for the POST(set) write-back
fragment and the Plan 06 probe ONLY, never for the list display.

```python
# GET (list) — direct model query, no decryption:
from app.models.api_credential import ApiCredential
rows = db.execute(select(ApiCredential)).scalars().all()
# context per provider: {"provider", "last_four", "model_name", "is_enabled"} only
```

**POST (set) core pattern — SEC-6: key stays in handler scope only:**
```python
@router.post("/credentials/{provider}", response_class=HTMLResponse)
async def set_credential(
    provider: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    api_key = raw.get("api_key", "").strip()
    model_name = raw.get("model_name", "").strip()
    # api_key stays local — NEVER passed to template context
    cred_service.set_provider_credential(db, provider, key=api_key, model_name=model_name, by_user_id=user.id)
    # Fetch back only last_four for display
    cred = cred_service.get_provider_credential(db, provider)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_credential_row.html",
        context={"provider": provider, "last_four": cred.last_four if cred else None, "is_enabled": cred.is_enabled if cred else False},
    )
```

Template context must never include `cred.key` or the `ProviderCredential` dataclass directly — only `last_four`, `model_name`, `is_enabled`.

---

### `app/routers/admin/settings_editor.py` (controller, CRUD)

**Analog:** `app/routers/roasters.py` (per-row inline save via HTMX)

**DEVIATION — raw DB query for status rows** (RESEARCH.md Pitfall 2):
```python
# CORRECT — direct DB query, NOT settings_service.get_str()
from app.models.app_setting import AppSetting
from sqlalchemy import select

row = db.execute(
    select(AppSetting.value, AppSetting.value_type).where(AppSetting.key == "last_backup_status")
).one_or_none()
```

**Core per-row inline save pattern:**
```python
@router.post("/settings/{key}", response_class=HTMLResponse)
async def save_setting(
    key: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    # D-04 read-only guard
    _READ_ONLY_KEYS = {"last_ai_run_status", "last_backup_status", "last_backup_at", "setup_completed"}
    if key in _READ_ONLY_KEYS:
        raise HTTPException(status_code=403, detail="Read-only setting")
    form_data = await request.form()
    raw = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}
    value = raw.get("value", "")
    # set_setting owns coercion + cache invalidation + audit event
    from app.services import settings as settings_service
    settings_service.set_setting(db, key, value, by_user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_setting_row.html",
        context={"key": key, "saved": True},
    )
```

---

### `app/routers/admin/backups.py` (controller, file-I/O)

**Analog:** `app/routers/photos.py` (FileResponse + path validation)

**FileResponse pattern** (`app/routers/photos.py` lines 61-115):
```python
@router.get("/{filename}")
def serve_photo(filename: str, request: Request) -> FileResponse:
    # 1. Auth gate
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # 2. Filename validation — primary path-traversal defense
    if not _is_safe_photo_filename(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # 3. Belt-and-braces resolve check
    photos_dir = _photos_svc.PHOTOS_DIR
    photo_path = (photos_dir / filename).resolve()
    try:
        photo_path.relative_to(photos_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if not photo_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # 4. Serve with explicit headers
    return FileResponse(
        photo_path,
        media_type="image/jpeg",
        headers={...},
    )
```

**Backup download adaptation** (RESEARCH.md Pattern FileResponse for backup download):
```python
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

_BACKUP_FILENAME_RE = re.compile(
    r"^(?:db|photos)_\d{4}-\d{2}-\d{2}\.(?:sql|tar\.gz)$"
)
_BACKUP_DIR = Path("/app/data/backups")

@router.get("/backups/{filename}")
def download_backup(
    filename: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
) -> FileResponse:
    if not _BACKUP_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404)
    backup_path = (_BACKUP_DIR / filename).resolve()
    if not backup_path.is_file() or not backup_path.is_relative_to(_BACKUP_DIR.resolve()):
        raise HTTPException(status_code=404)
    media_type = "application/gzip" if filename.endswith(".gz") else "application/octet-stream"
    return FileResponse(backup_path, media_type=media_type, filename=filename)
```

**DEVIATION — "Run backup now" must be sync def** (D-07):
```python
@router.post("/backups/run", response_class=HTMLResponse)
def run_backup_now(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    # sync def — FastAPI puts this in the threadpool; safe for long-running pg_dump
    from app.services.backup import run_backup
    result = run_backup(db, by_user_id=user.id)
    # render BackupResult into fragment
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_backup_result.html",
        context={"result": result},
    )
```

`run_backup` signature (RESEARCH.md, verified from `backup.py` lines 282-290):
```python
def run_backup(
    db: Session | None = None,
    *,
    backup_dir: str = "/app/data/backups",
    photos_dir: str = "/app/data/photos",
    by_user_id: int | None = None,
) -> BackupResult:
```

---

### `app/routers/admin/system.py` (controller, request-response)

**Analog:** `app/routers/roasters.py` (sync def list handler shape)

**DEVIATION — raw DB query for status rows** (same as settings_editor; RESEARCH.md Pitfall 2):
```python
import json
from importlib.metadata import version as pkg_version
from sqlalchemy import text

@router.get("/system", response_class=HTMLResponse)
def admin_system(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    app_version = pkg_version("coffee-snobbery")
    db_version = db.execute(text("SELECT version()")).scalar()
    session_count = db.execute(
        text("SELECT COUNT(*) FROM sessions WHERE expires_at > now()")
    ).scalar_one()
    # last_backup_status — raw DB query, NOT get_str()
    from app.models.app_setting import AppSetting
    from sqlalchemy import select
    backup_row = db.execute(
        select(AppSetting.value).where(AppSetting.key == "last_backup_status")
    ).scalar_one_or_none()
    last_backup_status = json.loads(backup_row) if backup_row and backup_row != "never_run" else None
    # last_ai_run_status — same pattern
    ai_row = db.execute(
        select(AppSetting.value).where(AppSetting.key == "last_ai_run_status")
    ).scalar_one_or_none()
    last_ai_run_status = json.loads(ai_row) if ai_row else None
    ...
```

**DEVIATION — "Run AI refresh now" must be async def** (RESEARCH.md Pitfall 4):
`ai_service.regenerate()` is `async def` (verified at line 1126). Handler must be `async def`:
```python
@router.post("/system/ai-refresh", response_class=HTMLResponse)
async def run_ai_refresh(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    form_data = await request.form()
    force = form_data.get("force", "false").lower() in ("true", "1", "on")
    generated_by = "admin_force" if force else "admin"
    # COST-CONTROL INVARIANT (D-13): reuse the Phase 8 eligibility pre-filter.
    # _get_eligible_user_ids returns user IDs that are is_active AND have >= 3
    # brew_sessions. Re-implementing this here (e.g. select(User).where(is_active))
    # would re-bill ineligible users and break the Phase 8 cost control.
    # It returns list[int], NOT User rows — iterate the IDs directly.
    from app.services.scheduler import _get_eligible_user_ids
    eligible_ids = _get_eligible_user_ids(db)  # list[int]
    from app.services import ai_service
    results = []
    for uid in eligible_ids:
        status = await ai_service.regenerate(uid, generated_by, db=db, force=force)
        results.append({"user_id": uid, "status": status})
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_ai_refresh_result.html",
        context={"results": results, "force": force},
    )
```

Analog for async def + `await ai_service.regenerate()` shape from `app/routers/ai.py` lines 218-226:
```python
status = await ai_service.regenerate(user_id, "manual_refresh", db=db, force=True)
if status == "generated":
    return Response(status_code=204, headers={"HX-Trigger": "aiRecUpdated"})
```

**"Test connection" handler — sync def, CANONICAL LOCATION** (RESEARCH.md Q1):

The probe handler lives ENTIRELY here in `app/routers/admin/system.py` at
`POST /admin/system/test-connection/{provider}` (Plan 06). This is the single
source of truth — matches the Handler Sync/Async Decision Table. Plan 03 does NOT
register a probe route or handler; it ships only the `admin_test_result.html`
result fragment. The credentials-page "Test connection" button (if shown) targets
this `/admin/system/...` route (cross-page POST is fine; same-origin). `async def`
is unnecessary — no sessions are touched; it decrypts the key in-scope and runs a
single sync SDK call.

```python
@router.post("/system/test-connection/{provider}", response_class=HTMLResponse)
def test_connection(
    provider: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),   # noqa: B008
) -> Response:
    from app.services import credentials as cred_service
    cred = cred_service.get_provider_credential(db, provider)
    if not cred:
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_test_result.html",
            context={"provider": provider, "status": "error", "reason": "not_configured"},
        )
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=cred.key)
            client.models.list()
        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=cred.key)
            client.models.list()
        result = {"status": "ok"}
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
            openai.AuthenticationError):
        result = {"status": "error", "reason": "invalid_key"}
    except (anthropic.APIConnectionError, anthropic.APITimeoutError,
            openai.APIConnectionError, openai.APITimeoutError):
        result = {"status": "error", "reason": "network"}
    except Exception:
        result = {"status": "error", "reason": "unknown"}
    finally:
        del client  # discard object holding key reference
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_test_result.html",
        context={"provider": provider, **result},
    )
```

---

### `app/templates/admin_base.html` (template, request-response)

**Analog:** `app/templates/base.html`

**Block names from `base.html`** (full file, lines 1-49):
- `{% block page_title %}` — in `<title>` tag
- `{% block title %}` — secondary title block (appears unused in sub-templates, legacy)
- `{% block content %}` — entire body content area; `admin_base.html` fills this

**Template chain:** sub-page templates extend `admin_base.html`; `admin_base.html` extends `base.html`.

**`admin_base.html` structure to implement:**
```jinja2
{# admin_base.html — extends base.html; adds persistent admin section nav (D-02) #}
{% extends "base.html" %}
{% block page_title %}Admin — {% block admin_page_title %}{% endblock %}{% endblock %}
{% block content %}
  <main class="mx-auto max-w-5xl px-6 py-12">
    <header class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Admin</h1>
    </header>
    {# Persistent section nav — collapses cleanly at 375px (D-02, mobile-first) #}
    <nav aria-label="Admin sections" class="flex flex-wrap gap-2 mb-8 border-b border-espresso-200 pb-4 dark:border-espresso-800">
      <a href="/admin/users" class="rounded px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">Users</a>
      <a href="/admin/credentials" class="rounded px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">Credentials</a>
      <a href="/admin/settings" class="rounded px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">Settings</a>
      <a href="/admin/backups" class="rounded px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">Backups</a>
      <a href="/admin/system" class="rounded px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">System</a>
    </nav>
    {% block admin_content %}{% endblock %}
  </main>
{% endblock %}
```

Sub-page templates fill `{% block admin_content %}`.

**Existing `admin.html` stub** must change its `{% extends %}` from `base.html` to `admin_base.html` and fill `{% block admin_content %}` instead of `{% block content %}`.

---

### Page templates: `admin_users.html`, `admin_credentials.html`, `admin_settings.html`, `admin_backups.html`, `admin_system.html`

**Analog:** `app/templates/pages/roasters.html`

**Page template pattern** (`app/templates/pages/roasters.html` lines 1-20):
```jinja2
{% extends "base.html" %}
{% block page_title %}Roasters{% endblock %}
{% block content %}
  <main class="mx-auto max-w-5xl px-6 py-12">
    <header class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Roasters</h1>
      <button type="button"
              hx-get="/roasters/new"
              hx-target="#roaster-form-mount"
              hx-swap="innerHTML"
              class="rounded bg-espresso-700 px-4 py-2 text-cream-50 hover:bg-espresso-800">
        Add roaster
      </button>
    </header>
    <div id="roaster-form-mount" class="mb-4"></div>
    <div id="roaster-list" class="space-y-3">
      {% include "fragments/roaster_list.html" %}
    </div>
  </main>
{% endblock %}
```

Admin sub-page templates extend `admin_base.html` and fill `{% block admin_content %}`:
```jinja2
{% extends "admin_base.html" %}
{% block admin_page_title %}Users{% endblock %}
{% block admin_content %}
  <header class="flex items-center justify-between mb-6">
    <h2 class="text-xl font-semibold">Users</h2>
    <button type="button"
            hx-get="/admin/users/new"
            hx-target="#admin-user-form-mount"
            hx-swap="innerHTML"
            class="rounded bg-espresso-700 px-4 py-2 text-cream-50 hover:bg-espresso-800">
      Add user
    </button>
  </header>
  <div id="admin-user-form-mount" class="mb-4"></div>
  <div id="admin-user-list" class="space-y-3">
    {% include "fragments/admin_user_list.html" %}
  </div>
{% endblock %}
```

---

### Fragment templates

**`admin_user_form.html`** — copies `app/templates/fragments/roaster_form.html`

**CSRF hidden field pattern** (`app/templates/fragments/roaster_form.html` line 40):
```jinja2
{# D-15: CSRFFormFieldShim hoists this field into the X-CSRF-Token header. #}
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

This line is mandatory on every state-changing form in every admin template. No exceptions.

**Full form fragment pattern** (`roaster_form.html` lines 11-110):
```jinja2
<div class="rounded-lg border border-espresso-200 bg-cream-100 p-6 mb-4 dark:bg-espresso-900 dark:border-espresso-800">
  <form hx-post="{{ form_action }}"
        hx-target="{{ form_target }}"
        hx-swap="{{ form_swap }}"
        class="flex flex-col gap-4">
    <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
    <label class="flex flex-col gap-1">
      <span class="text-sm font-semibold">Name</span>
      <input name="name" ...
             class="rounded border px-2 py-2 text-base{% if errors.get('name') %} border-red-300{% else %} border-espresso-200{% endif %}">
      {% if errors.get('name') %}
        <p class="text-sm text-red-700 mt-1">{{ errors['name'] }}</p>
      {% endif %}
    </label>
    ...
    {% if errors.get('_form') %}
      <p class="text-sm text-red-700">{{ errors['_form'] }}</p>
    {% endif %}
    <div class="flex gap-3 mt-2">
      <button type="button"
              hx-get="/admin/users/empty-form"
              hx-target="#admin-user-form-mount"
              hx-swap="innerHTML"
              class="rounded border border-espresso-300 px-4 py-2 ...">
        Cancel
      </button>
      <button type="submit" class="rounded bg-espresso-700 px-4 py-2 text-cream-50 ...">
        Save
      </button>
    </div>
  </form>
</div>
```

**`admin_user_row.html`** — copies `app/templates/fragments/roaster_row.html`

Row fragment pattern with `data-row` + `id` for HTMX swap targeting (`roaster_row.html` lines 15-54):
```jinja2
<div id="admin-user-{{ user.id }}"
     data-row
     class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <div class="font-semibold">{{ user.username }}</div>
  <div class="mt-3 flex gap-3">
    <button type="button"
            hx-get="/admin/users/{{ user.id }}/edit"
            hx-target="closest [data-row]"
            hx-swap="outerHTML"
            class="rounded border border-espresso-300 px-3 py-1 text-sm ...">
      Edit
    </button>
    {# Destructive actions use hx-confirm per roaster_row.html pattern #}
    <button type="button"
            hx-post="/admin/users/{{ user.id }}/deactivate"
            hx-target="closest [data-row]"
            hx-swap="outerHTML"
            hx-confirm="Deactivate this user?"
            class="...">
      Deactivate
    </button>
  </div>
</div>
```

OOB form-clear pattern after successful create (`roaster_row.html` lines 95-98):
```jinja2
{% if include_oob_form_clear %}
  <div id="admin-user-form-mount" hx-swap-oob="innerHTML"></div>
{% endif %}
```

---

### `app/events.py` (config, extend)

**Analog:** Self — `app/events.py` lines 44-57 (existing admin.* block)

**Existing admin.* constants** (lines 45-57):
```python
ADMIN_USER_CREATED = "admin.user_created"
ADMIN_USER_DELETED = "admin.user_deleted"
ADMIN_PASSWORD_RESET = "admin.password_reset"  # noqa: S105
ADMIN_IS_ADMIN_TOGGLED = "admin.is_admin_toggled"
ADMIN_APP_SETTING_CHANGED = "admin.app_setting_changed"
ADMIN_API_CREDENTIAL_SET = "admin.api_credential_set"  # noqa: S105
```

**New constants to add** (RESEARCH.md Events section):
```python
ADMIN_USER_UPDATED = "admin.user_updated"          # generic edit
ADMIN_USER_DEACTIVATED = "admin.user_deactivated"  # explicit deactivate action
ADMIN_BACKUP_TRIGGERED = "admin.backup_triggered"  # "Run backup now" button
ADMIN_AI_REFRESH_TRIGGERED = "admin.ai_refresh_triggered"  # manual AI refresh (both modes)
ADMIN_PROVIDER_TEST = "admin.provider_test"        # "Test connection" probe result
```

Add to the `__all__` list in the same block pattern as existing constants.

**Structlog emit pattern** (existing usage across the codebase):
```python
import structlog
log = structlog.get_logger(__name__)
log.info(events.ADMIN_BACKUP_TRIGGERED, user_id=user.id, by="admin")
```

---

### `app/templates/pages/home.html` (template, modify existing — D-03)

**Analog:** Self — `app/templates/pages/home.html`

**Existing header pattern** (lines 9-15):
```jinja2
<header class="flex flex-wrap items-center justify-between gap-4 mb-6">
  <h1 class="text-2xl font-semibold">Home</h1>
  <a href="/brew/new"
     class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
    Log session
  </a>
</header>
```

**Admin entry link to add — is_admin-gated** (D-03):
```jinja2
{# D-03: minimal admin entry link — is_admin-gated; full nav is Phase 11 #}
{% if request.state.user and request.state.user.is_admin %}
  <a href="/admin"
     class="rounded border border-espresso-300 dark:border-espresso-600 px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">
    Admin
  </a>
{% endif %}
```

Place inside the existing `<header>` flex container alongside the "Log session" button. The `request.state.user` object is populated by `SessionMiddleware` — same access pattern used throughout templates.

---

## Shared Patterns

### Authentication — require_admin on every admin route
**Source:** `app/dependencies/auth.py` lines 48-62
**Apply to:** Every handler in every admin sub-router (users, credentials, settings_editor, backups, system)

```python
def require_admin(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return user
```

Dependency form: `user: User = Depends(require_admin)  # noqa: B008`

No admin route is exempt — including fragment endpoints.

---

### CSRF — hidden field in every state-changing form
**Source:** `app/templates/fragments/roaster_form.html` line 40
**Apply to:** Every `<form>` element in admin templates that submits POST/PUT/DELETE

```jinja2
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

The `CSRFFormFieldShim` middleware (registered in `app/main.py` line 222) hoists this field into the `X-CSRF-Token` header before `CSRFMiddleware` validates it.

---

### HTMX form POST — raw form read + CSRF field strip
**Source:** `app/routers/roasters.py` lines 218-228
**Apply to:** All async POST handlers in admin sub-routers

```python
form_data = await request.form()
skip = {"X-CSRF-Token"}
raw = {k: v for k, v in form_data.items() if k not in skip}
```

---

### HTMX fragment vs full-page response split
**Source:** `app/routers/roasters.py` lines 136-147
**Apply to:** Admin list handlers (users, backups, settings)

```python
if request.headers.get("HX-Request") == "true":
    return templates.TemplateResponse(request=request, name="fragments/...", context={...})
return templates.TemplateResponse(request=request, name="pages/...", context={...})
```

---

### Template response — always pass `request=request`
**Source:** `app/routers/roasters.py` line 139
**Apply to:** Every `templates.TemplateResponse()` call

```python
templates.TemplateResponse(
    request=request,   # required — provides request.cookies, request.state for templates
    name="...",
    context={...},
)
```

---

### Structlog audit emit pattern
**Source:** `app/events.py` + existing handler usage across codebase
**Apply to:** Every state-changing admin handler

```python
import structlog
from app import events

log = structlog.get_logger(__name__)

# At end of successful write, before returning the response:
log.info(events.ADMIN_USER_CREATED, user_id=new_user.id, by_user_id=admin_user.id)
```

Never log `api_key`, `password`, or `session_id` — CLAUDE.md "Things to never do silently".

---

### Validation re-render at HTTP 200 (not 422)
**Source:** `app/routers/roasters.py` lines 229-243
**Apply to:** User create/edit and any admin form that validates input

```python
except ValidationError as exc:
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_form.html",
        context={"values": raw, "errors": errors_by_field(exc), "mode": "create"},
        status_code=200,  # NOT 422 — HTMX swaps on any 2xx
    )
```

---

### FileResponse + dual path-traversal defense
**Source:** `app/routers/photos.py` lines 78-115
**Apply to:** `app/routers/admin/backups.py` download handler

```python
# Step 1: strict regex on filename parameter
if not _BACKUP_FILENAME_RE.match(filename):
    raise HTTPException(status_code=404)
# Step 2: resolve and confirm containment
backup_path = (_BACKUP_DIR / filename).resolve()
if not backup_path.is_relative_to(_BACKUP_DIR.resolve()):
    raise HTTPException(status_code=404)
if not backup_path.is_file():
    raise HTTPException(status_code=404)
```

---

### raw DB query for system-written status rows (NOT get_str)
**Source:** RESEARCH.md Pitfall 2, `backup.py` module docstring contract
**Apply to:** `system.py` and `settings_editor.py` wherever `last_backup_status` or `last_ai_run_status` are read

```python
from app.models.app_setting import AppSetting
from sqlalchemy import select

row = db.execute(
    select(AppSetting.value).where(AppSetting.key == "last_backup_status")
).scalar_one_or_none()
status_json = json.loads(row) if row and row != "never_run" else None
```

---

### async_session_factory import path for session-deletion handlers
**Source:** `app/main.py` line 120
**Apply to:** `users.py` handlers for is_admin toggle, deactivate, and delete

```python
from app.main import async_session_factory

# Inside async def handler:
async with async_session_factory() as async_db:
    await async_db.execute(
        sql_delete(SessionModel).where(SessionModel.user_id == target_user_id)
    )
    await async_db.commit()
```

---

## Handler Sync/Async Decision Table

| Handler | def type | Reason |
|---------|----------|--------|
| `GET /admin/users` — list | `def` | sync DB only |
| `GET /admin/users/new` — form | `def` | no DB |
| `POST /admin/users` — create | `async def` | `await request.form()` |
| `GET /admin/users/{id}/edit` | `def` | sync DB only |
| `POST /admin/users/{id}` — update | `async def` | `await request.form()` |
| `POST /admin/users/{id}/toggle-admin` | `async def` | `await request.form()` + async session delete |
| `POST /admin/users/{id}/deactivate` | `async def` | async session delete |
| `POST /admin/users/{id}/delete` | `async def` | async session delete before sync user delete |
| `GET /admin/credentials` | `def` | sync DB only |
| `POST /admin/credentials/{provider}` | `async def` | `await request.form()` |
| `POST /admin/credentials/{provider}/enabled` | `async def` | `await request.form()` |
| `GET /admin/settings` | `def` | sync DB only |
| `POST /admin/settings/{key}` | `async def` | `await request.form()` |
| `GET /admin/backups` | `def` | filesystem walk only |
| `GET /admin/backups/{filename}` — download | `def` | `FileResponse` sync |
| `POST /admin/backups/run` — backup now | `def` | D-07: sync threadpool for `run_backup()` |
| `GET /admin/system` | `def` | sync DB reads only |
| `POST /admin/system/test-connection/{provider}` | `def` | sync SDK call |
| `POST /admin/system/ai-refresh` | `async def` | `await ai_service.regenerate()` |

---

## No Analog Found

All Phase 9 files have usable analogs. The following have no direct data-flow match but use role-match analogs instead:

| File | Role | Data Flow | Closest Analog | Gap |
|------|------|-----------|----------------|-----|
| `app/templates/fragments/admin_setting_row.html` | template | CRUD (per-row inline) | `roaster_form.html` | No existing per-row inline save fragment in codebase; pattern is inferred from roaster form + D-06 description |
| `app/templates/fragments/admin_backup_result.html` | template | file-I/O result | `roaster_row.html` | No existing "operation result" fragment; use `BackupResult` shape from RESEARCH.md |
| `app/templates/fragments/admin_ai_refresh_result.html` | template | request-response | `roaster_row.html` | No existing batch-operation result fragment |

For these three, the planner should use the `BackupResult`/`ArtifactResult` data shape from RESEARCH.md (Phase 8 SCHED-03 shape) and the standard card/section HTML idiom from `roaster_row.html`.

---

## Metadata

**Analog search scope:** `app/routers/`, `app/templates/`, `app/dependencies/`, `app/events.py`, `app/main.py`
**Files scanned:** 14 source files read directly
**Pattern extraction date:** 2026-05-21
