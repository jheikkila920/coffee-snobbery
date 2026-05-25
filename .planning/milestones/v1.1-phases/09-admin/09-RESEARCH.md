# Phase 9: Admin - Research

**Researched:** 2026-05-21
**Domain:** FastAPI admin surface (routers + templates + wiring over existing services)
**Confidence:** HIGH — all service signatures verified from source; SDK exceptions verified from GitHub source files

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Sub-pages + index hub. `/admin` lands on a hub page; six focused sub-pages.
- D-02: Persistent section nav via shared `admin_base.html` extending `base.html`.
- D-03: Minimal admin entry link (home/footer area); no Phase 11 global nav.
- D-04: All `app_settings` rows shown; `last_ai_run_status`, `last_backup_status`, `last_backup_at`, `setup_completed` read-only display only.
- D-05: Type-driven inputs matching actual seeded `value_type` set: `int`, `float`, `bool`, `string`, `null`.
- D-06: Per-row inline HTMX save for editable rows.
- D-07: "Run backup now" = sync `def` handler, FastAPI threadpool.
- D-08: Backup download = admin-gated `FileResponse` with strict filename validation (path traversal block).
- D-09: App version from `importlib.metadata.version("coffee-snobbery")`.
- D-10: API health panel data from `app_settings.last_ai_run_status` + `ai_recommendations` rows.
- D-11: System/health panels are read-only (no inline editing).
- D-12: Per-provider "Test connection" probe — cheapest auth-only SDK call. (Research confirms below.)
- D-13: "Run AI refresh now" offers BOTH respect-signature (`force=False`) and force (`force=True`) modes.
- D-14: AI-refresh `generated_by` tag distinct from `"scheduler"` and home-page `"manual_refresh"`.
- D-15: Block-and-deactivate, no cascading hard-delete. Hard-delete blocked when user has `brew_sessions`. (Research confirms FK semantics below.)
- D-16: Last-admin / self-lockout protection (server-side, locked).

### Claude's Discretion
- `is_admin` toggle session regeneration: delete target user's session row(s), not rotate.
- Password reset: admin types new password, 12-char floor, argon2id via `services/auth.py`.
- User create email: optional.
- System/health page split: planner's call.
- Panel manual-refresh: static-on-load is fine.
- Health error-message truncation: planner's call.
- `/debug/proxy` harden/remove: low priority, planner's call.

### Deferred Ideas (OUT OF SCOPE)
- Full global navigation + sign-out restoration (Phase 11).
- Git-SHA build stamp in system info.
- Emailed / generated password reset (no SMTP).
- Background-task / polling backup runner.
- Per-month / per-user AI cost ceiling.
- `settings.refresh_cache()` admin endpoint.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADMIN-01 | User management: list, create, edit (reset password, toggle admin, deactivate), delete | User model confirmed; FK/ondelete semantics confirmed; session delete mechanism confirmed; hash_password signature confirmed |
| ADMIN-02 | API credentials per provider: set/update encrypted key, select model, enable/disable, keys masked | `set_provider_credential`, `set_provider_enabled`, `get_provider_credential`, `ProviderCredential` all confirmed; SEC-6 pattern established |
| ADMIN-03 | `app_settings` editor: value_type-driven input, save persists immediately | `get_raw` + `set_setting` signatures confirmed; full seed row inventory completed |
| ADMIN-04 | Backups page: list files, download, manual "Run backup now" | `run_backup` signature confirmed; backup dir constants confirmed; `FileResponse` pattern from `photos.py` confirmed |
| ADMIN-05 | System info panel: app version, DB version, storage, sessions, last backup | pyproject.toml name confirmed as `"coffee-snobbery"`; all data sources identified |
| ADMIN-06 | API health panel: last AI run per rec type, success/error per provider, last 5 errors | `ai_recommendations` columns confirmed; `last_ai_run_status` row confirmed; read-via-raw-DB note documented |
</phase_requirements>

---

## Summary

Phase 9 is router + template work over services that already exist and are fully tested. The service contracts are stable. All four flagged unknowns from CONTEXT.md have been resolved with file:line evidence. The main risks are:
(1) `sessions.py` is async-only — admin handlers that delete a target user's sessions must use an `AsyncSession`, which means those specific admin handlers must be `async def`, not `sync def`;
(2) `last_backup_status` and `last_ai_run_status` must be read via raw DB query, not `get_str()`, because `set_setting` pops the cache key after every write and the next `prewarm_cache` may not have run;
(3) The existing `admin.html` is a stub that extends `base.html` directly — Phase 9 inserts a new `admin_base.html` layer between it and `base.html`.

**Primary recommendation:** Expand `app/routers/admin.py` into a sub-package; keep all handlers sync except the session-delete paths (which call async `sessions.delete_session`). Use the photos.py FileResponse pattern for backup downloads. Mirror the roasters.py HTMX + CSRF pattern for user CRUD.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| User CRUD | API/Router | DB (SQLAlchemy) | Handler reads form, calls ORM directly (no dedicated user service exists) |
| API credential vault | Router -> `services/credentials.py` | `services/encryption.py` | Credential service owns all encrypt/decrypt; router is thin wrapper |
| `app_settings` editor | Router -> `services/settings.py` | DB | `set_setting` owns coercion + cache invalidation + audit event |
| Backup list + download | Router -> filesystem | `services/backup.py` | List = disk walk; download = `FileResponse`; run = `run_backup()` |
| System info | Router -> DB + filesystem + `importlib.metadata` | — | Pure reads; no service layer needed |
| API health panel | Router -> DB + `app_settings` raw | — | Read-only aggregation from existing rows |
| "Test connection" probe | Router -> SDK client | `services/credentials.py` (decrypt) | Decrypted key used locally in handler scope, never returned |
| "Run AI refresh now" | Router -> `services/ai_service.regenerate` | — | `regenerate()` owns all cost-control; handler iterates eligible users |
| Session invalidation on toggle | Router -> `services/sessions.delete_session` | — | Async; handler must be `async def` for these specific routes |

---

## Resolved Research Questions

### Q1: Cheapest auth-only SDK probe (D-12)

**Anthropic (>=0.102,<1.0):**

```python
client = anthropic.Anthropic(api_key=cred.key)  # cred.key is str (ProviderCredential.key)
page = client.models.list()  # SyncPage[ModelInfo] — returns quickly, no tokens billed
```

- `client.models.list()` exists and is documented in `api.md` [VERIFIED: github.com/anthropics/anthropic-sdk-python/blob/main/api.md]
- `api_key` parameter is `str` — confirmed by `ProviderCredential.key: str` docstring at `credentials.py:97-103` which states "both the Anthropic and OpenAI SDKs declare `api_key: str | None` on their constructors"
- Auth failure: `anthropic.AuthenticationError` (HTTP 401) [VERIFIED: github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_exceptions.py]
- Network failure: `anthropic.APIConnectionError` (no HTTP code — connection-level) [VERIFIED: same file]
- Quota/billing: `anthropic.RateLimitError` (HTTP 429) — treat as "key valid but quota hit" (not auth failure)
- Pattern: catch `anthropic.AuthenticationError` as "bad key"; catch `anthropic.APIConnectionError` / `anthropic.APITimeoutError` as "network error"; let `anthropic.PermissionDeniedError` (HTTP 403) also count as auth failure

**OpenAI (>=2.37,<3.0):**

```python
client = openai.OpenAI(api_key=cred.key)
page = client.models.list()  # SyncPage[Model] — no content generated
```

- `client.models.list()` exists [VERIFIED: github.com/openai/openai-python/blob/main/api.md]
- `api_key` is `str` — same SDK convention as Anthropic
- Auth failure: `openai.AuthenticationError` (HTTP 401) [VERIFIED: github.com/openai/openai-python/blob/main/src/openai/_exceptions.py]
- Network failure: `openai.APIConnectionError` (connection-level, no HTTP code) [VERIFIED: same file]
- Bad key pattern: catch `openai.AuthenticationError` as "bad key"; `openai.APIConnectionError`/`openai.APITimeoutError` as "network error"

**Both SDKs:** The sync `models.list()` call is the correct probe. It makes one HTTP GET to the models endpoint, returns immediately (no LLM inference), and costs no tokens. The decrypted key is passed only to the SDK constructor in handler scope and discarded on function return (SEC-6 compliance).

**Handler structure (both providers):**

```python
# sync def handler — threadpool; cred.key in local scope only
try:
    client = anthropic.Anthropic(api_key=cred.key)
    client.models.list()
    return {"status": "ok"}
except anthropic.AuthenticationError:
    return {"status": "error", "reason": "invalid_key"}
except (anthropic.APIConnectionError, anthropic.APITimeoutError):
    return {"status": "error", "reason": "network"}
except Exception:
    return {"status": "error", "reason": "unknown"}
finally:
    del client  # explicit cleanup of object holding key reference
```

### Q2: FK `ondelete` semantics for user-related tables

Read from source files. Results verbatim:

**`brew_sessions.user_id`**
- File: `app/migrations/versions/p5_brew_sessions.py` line 75
- Clause: `sa.ForeignKey("users.id", ondelete="RESTRICT")`
- Effect: DELETE on a `users` row with any `brew_sessions` rows will be **REJECTED by the DB** with an `IntegrityError`. The application-level guard in D-15 (block if user has `brew_sessions`) matches the DB constraint — they are redundant defenses.

**`ai_recommendations.user_id`**
- File: `app/migrations/versions/0001_initial.py` line 157
- Clause: `sa.ForeignKey("users.id", ondelete="CASCADE")`
- Effect: Deleting a user CASCADE-deletes their AI recommendation rows. This is DB-level automatic.

**`wishlist_entries.user_id`**
- File: `app/migrations/versions/0001_initial.py` line 130
- Clause: `sa.ForeignKey("users.id", ondelete="CASCADE")`
- Effect: Deleting a user CASCADE-deletes their wishlist entries.

**`app_settings.updated_by_user_id`**
- File: `app/migrations/versions/0001_initial.py` line 212
- Clause: `sa.ForeignKey("users.id", ondelete="SET NULL")`
- Effect: Deleting a user sets the FK to NULL on those settings rows.

**`api_credentials.updated_by_user_id`**
- File: `app/models/api_credential.py` line 79
- Clause: `ForeignKey("users.id", ondelete="SET NULL")`
- Effect: SET NULL on credential rows.

**Sessions table** (relevant for deactivate path):
- File: `app/migrations/versions/p1_sessions_table.py` — need to confirm FK; assumed CASCADE given the session middleware expects the user row to exist. [ASSUMED — not read; not critical for hard-delete logic since sessions are deleted by the handler before or alongside user delete]

**Practical implications for D-15 handler:**
- Hard-delete an empty user (no `brew_sessions`): DB allows it. `ai_recommendations` + `wishlist_entries` cascade automatically. `sessions` rows also need to be deleted first (or will cascade if FK is CASCADE).
- Hard-delete a user WITH `brew_sessions`: DB raises `IntegrityError` due to RESTRICT. The application guard (check `brew_sessions` count > 0, return 400/conflict) should fire before the DB ever sees the DELETE. Belt-and-suspenders.
- The application-level guard is the correct UX layer; the RESTRICT FK is the correctness backstop. Both must exist.

### Q3: Accepted `generated_by` values on `ai_recommendations`

**Column definition** (`app/models/ai_recommendation.py` line 77-78):
```python
# 'scheduler' | 'manual_refresh'
generated_by: Mapped[str] = mapped_column(Text, nullable=False)
```

The column is **free TEXT with no DB CHECK constraint** — application validates the value set. The comment documents two values:

1. `"scheduler"` — written by `services/scheduler.py` nightly job
2. `"manual_refresh"` — written by Phase 7 home-page manual refresh button

**Phase 8 scheduler usage** (`services/scheduler.py`, confirmed in ROADMAP Phase 8 Success Criterion 2):
```python
ai_service.regenerate(uid, "scheduler", db=db)
```

**Phase 7 home-page manual refresh** (from ROADMAP Phase 7 notes): `generated_by="manual_refresh"`

**For Phase 9 D-14 admin refresh:** The field is free text, so any distinct value is valid. Recommended values:
- For "Refresh (respect signatures)" mode: `"admin"` — distinct from both `"scheduler"` and `"manual_refresh"`, unambiguous
- For "Force refresh all" mode: `"admin_force"` — makes the force-flag visible in telemetry without joining to any other table

Both values need to be added to the comment block in `ai_recommendation.py` when Phase 9 ships, but no migration or schema change is required.

### Q4: Session regeneration / invalidation mechanism for `is_admin` toggle

**`services/sessions.py` public surface** (verified from file):

```python
# Both are ASYNC — accept AsyncSession
async def regenerate_session(db: AsyncSession, current_session_id: uuid.UUID | None, user_id: int) -> uuid.UUID
async def delete_session(db: AsyncSession, session_id: uuid.UUID) -> None
```

Key facts:
- ALL session helpers in `services/sessions.py` are `async def` and accept `AsyncSession` (not `Session`)
- `regenerate_session`: deletes old session row + inserts new row in one atomic commit; returns the new `uuid.UUID`; the CALLER must sign the new UUID and set the cookie on the response
- `delete_session`: deletes the session row keyed by `session_id`; no cookie management

**For `is_admin` toggle (D-16 ROADMAP success #1):**

The target user's session(s) must be invalidated so stale `is_admin=False` cookies can't retain the old privilege level after toggle. The admin performing the action does NOT have the target user's current `session_id` — only the target's `user_id` is known.

**Correct mechanism:** DELETE all `sessions` rows where `user_id = target_user_id` using a direct SQLAlchemy delete statement. Do NOT call `regenerate_session` (which requires the current session ID and issues a new cookie — inappropriate for a third-party admin action). The target user's next request will find no valid session and be treated as unauthenticated (re-login required).

```python
from sqlalchemy import delete as sql_delete
from app.models.session import Session as SessionModel

# In an async def admin handler:
await async_db.execute(
    sql_delete(SessionModel).where(SessionModel.user_id == target_user_id)
)
await async_db.commit()
```

**Implication for handler design:** Admin routes that delete another user's sessions MUST be `async def` and use the async session (from `app.main.async_session_factory`), not the sync `Session` from `app.dependencies.db.get_session`. All other admin handlers (user CRUD, settings edits, backup, system info) can remain sync `def`.

**For deactivation (not `is_admin` toggle):** Same mechanism — delete sessions. The middleware's `is_active` check will catch it on the next request regardless, but deleting the session row is the immediate, clean eviction.

---

## Standard Stack

### Core (all already installed)
| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| FastAPI | >=0.136,<0.137 | Router + Depends + FileResponse | CLAUDE.md |
| SQLAlchemy 2.0 | >=2.0.49,<2.1 | ORM + sync Session for most handlers | CLAUDE.md |
| sqlalchemy.ext.asyncio | (bundled) | AsyncSession for session-delete paths | `services/sessions.py` |
| Jinja2 | >=3.1.6,<4 | Templates; autoescape ON globally | `app/templates_setup.py` |
| `importlib.metadata` | stdlib | `version("coffee-snobbery")` | confirmed via pyproject.toml |
| anthropic | >=0.102,<1.0 | `models.list()` probe | CLAUDE.md |
| openai | >=2.37,<3.0 | `models.list()` probe | CLAUDE.md |

### Supporting (already in service layer)
| Library | Purpose | Phase 9 usage |
|---------|---------|---------------|
| `services/credentials.py` | API key CRUD | ADMIN-02 form wrapper |
| `services/settings.py` | `get_raw` + `set_setting` | ADMIN-03 editor |
| `services/backup.py` | `run_backup()` | ADMIN-04 "Run backup now" |
| `services/ai_service.regenerate` | AI refresh | ADMIN-06 action buttons |
| `services/auth.hash_password` | Password reset | ADMIN-01 edit form |
| `app/events.py` | Audit constants | New admin.* events to add |

---

## Architecture Patterns

### Recommended Project Structure

The current `app/routers/admin.py` is a single-file stub. Phase 9 has two options:

**Option A (recommended for this phase):** Expand `admin.py` into a sub-package:
```
app/routers/admin/
├── __init__.py          # re-exports router
├── users.py             # ADMIN-01
├── credentials.py       # ADMIN-02
├── settings_editor.py   # ADMIN-03 (avoids name clash with services/settings.py)
├── backups.py           # ADMIN-04
└── system.py            # ADMIN-05 + ADMIN-06 (or split)
```

**Option B (simpler):** Keep `admin.py` as one file, add all routes. At ~500-800 LOC this becomes unwieldy but is valid.

Planner's call — Option A is cleaner and mirrors how `app/routers/brew.py` vs `app/routers/brew/` would evolve.

**Template structure:**
```
app/templates/
├── admin_base.html              # NEW — extends base.html; section nav
├── pages/
│   ├── admin.html               # Expand stub into hub page
│   ├── admin_users.html         # ADMIN-01
│   ├── admin_credentials.html   # ADMIN-02
│   ├── admin_settings.html      # ADMIN-03
│   ├── admin_backups.html       # ADMIN-04
│   └── admin_system.html        # ADMIN-05 + ADMIN-06
└── fragments/
    ├── admin_user_row.html
    ├── admin_user_form.html
    ├── admin_setting_row.html
    ├── admin_backup_list.html
    └── admin_backup_result.html
```

### Pattern: Sync def + async def handlers in the same router

Most admin handlers: **sync `def`** (DB reads/writes via sync `Session` from `get_session`; runs in FastAPI threadpool).

Session-invalidation handlers (is_admin toggle, deactivate, delete): **async `def`** (must call `AsyncSession` to use `sessions.delete_session`).

```python
# sync handler — bulk of admin CRUD
def list_users(db: Session = Depends(get_session), user: User = Depends(require_admin)) -> Response:
    rows = db.execute(select(User)).scalars().all()
    ...

# async handler — session deletion paths
async def toggle_is_admin(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
) -> Response:
    # Sync DB work via get_session (Depends)
    # Async session work via async_session_factory directly
    async with async_session_factory() as async_db:
        await async_db.execute(sql_delete(SessionModel).where(SessionModel.user_id == target_id))
        await async_db.commit()
    ...
```

**Import path for async session:** `from app.main import async_session_factory` — it's already defined in `main.py` line 120.

### Pattern: HTMX + CSRF (from roasters.py)

```python
# Every state-changing form POST:
form_data = await request.form()
skip = {"X-CSRF-Token"}
raw = {k: v for k, v in form_data.items() if k not in skip}
# Validate, then call service
```

```html
<!-- Every state-changing form in templates: -->
<form hx-post="/admin/..." hx-target="#..." hx-swap="...">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  ...
</form>
```

### Pattern: FileResponse for backup download (from photos.py)

```python
@router.get("/admin/backups/{filename}")
def download_backup(filename: str, request: Request, user: User = Depends(require_admin)) -> Response:
    # Strict filename validation
    _BACKUP_FILENAME_RE = re.compile(r"^(?:db|photos)_\d{4}-\d{2}-\d{2}\.(?:sql|tar\.gz)$")
    if not _BACKUP_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404)
    backup_path = (Path("/app/data/backups") / filename).resolve()
    if not backup_path.is_file() or not backup_path.is_relative_to(Path("/app/data/backups").resolve()):
        raise HTTPException(status_code=404)
    media_type = "application/gzip" if filename.endswith(".gz") else "application/octet-stream"
    return FileResponse(backup_path, media_type=media_type, filename=filename)
```

### Pattern: admin_base.html extending base.html

```html
{# admin_base.html — extends base.html; adds section nav #}
{% extends "base.html" %}
{% block content %}
  <nav class="...">
    <a href="/admin/users">Users</a>
    <a href="/admin/credentials">Credentials</a>
    <a href="/admin/settings">Settings</a>
    <a href="/admin/backups">Backups</a>
    <a href="/admin/system">System</a>
  </nav>
  {% block admin_content %}{% endblock %}
{% endblock %}
```

Sub-page templates extend `admin_base.html` and fill `{% block admin_content %}`.

The existing `pages/admin.html` must be updated to extend `admin_base.html` and become the hub page.

### Pattern: `run_backup` from sync def handler

```python
# D-07: sync def so FastAPI runs in threadpool — no event loop blocking
def run_backup_now(
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> Response:
    from app.services.backup import run_backup
    result = run_backup(db, by_user_id=user.id)  # backup_dir / photos_dir default to /app/data/*
    # Render BackupResult fields into an HTMX fragment
    ...
```

`run_backup` signature (verified from `backup.py` lines 282-290):
```python
def run_backup(
    db: Session | None = None,
    *,
    backup_dir: str = "/app/data/backups",    # _DEFAULT_BACKUP_DIR
    photos_dir: str = "/app/data/photos",     # _DEFAULT_PHOTOS_DIR
    by_user_id: int | None = None,
) -> BackupResult:
```

Pass the handler's `db` session and `user.id`. The defaults for `backup_dir` and `photos_dir` are correct for production — no need to pass them.

### Pattern: `last_backup_status` / `last_ai_run_status` reads

**Do NOT use `get_str()` for these rows.** Use a direct DB query:

```python
# Correct pattern for reading system-written status rows in admin handlers
from app.models.app_setting import AppSetting
from sqlalchemy import select

row = db.execute(
    select(AppSetting.value).where(AppSetting.key == "last_backup_status")
).scalar_one_or_none()
status_json = json.loads(row) if row and row != "never_run" else None
```

**Why:** `backup.py` module docstring (line 11-15) explicitly states: "Phase 9's admin panel MUST read it via a raw DB query (SELECT value FROM app_settings WHERE key = ...), NOT via get_str('last_backup_status'). Reason: set_setting pops the cache key after every write. Until the next prewarm_cache() call, calling get_str() would raise SettingNotFoundError."

The same applies to `last_ai_run_status` for the same reason.

### Anti-Patterns to Avoid

- **Async def for regular CRUD handlers:** All non-session-deletion handlers should be sync `def`. Only session-deletion paths need `async def`.
- **`get_str()` for `last_backup_status` / `last_ai_run_status`:** Use raw DB query.
- **Calling `get_provider_credential()` and returning `cred.key` to a template:** The decrypted key must never leave handler scope (SEC-6). Only `last_four` goes to templates.
- **`StaticFiles` mount for backup serving:** Router-gated `FileResponse` only (mirrors photos.py).
- **Omitting `require_admin` on any admin sub-route:** Every route, including fragments.
- **Using `delete(User)` without checking `brew_sessions` count first:** The DB RESTRICT FK will raise `IntegrityError` — handle at application layer.
- **Calling `regenerate()` from a sync `def` handler:** `regenerate()` is `async def`. Admin "Run AI refresh now" handler must be `async def`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing for user create/reset | Custom argon2 setup | `services/auth.hash_password(plaintext: str) -> str` | Already pinned with correct parameters (memory_cost=65536, time_cost=3, parallelism=4, type=ID) |
| API key encryption/storage | Direct Fernet calls | `services/credentials.set_provider_credential(db, provider, *, key, model_name, by_user_id)` | Handles encrypt + last_four + fingerprint + audit event atomically |
| Settings write + cache invalidation | Direct UPDATE | `services/settings.set_setting(db, key, value, *, by_user_id)` | Handles coercion + cache pop + audit event |
| Backup execution | subprocess.run(pg_dump) | `services/backup.run_backup(db, *, backup_dir, photos_dir, by_user_id)` | Already handles keep-partial, status write, prune, structured result |
| AI refresh | Direct LLM calls | `services/ai_service.regenerate(user_id, generated_by, *, db, force=False)` | Owns all locks, throttle, cost-control, signature check |
| Session invalidation | Cookie clearing | `AsyncSession` + `delete(SessionModel).where(user_id=target)` | `sessions.delete_session` works for known session ID only; bulk-by-user requires direct DELETE |

---

## App Settings Inventory (D-04 + D-05)

Complete seed row set from `0001_initial.py`, classified by editability:

**Editable rows (type-driven input):**
| Key | value_type | Input Type | Notes |
|-----|-----------|------------|-------|
| `recommendation_region` | `string` | text | Short string |
| `min_sessions_for_ai` | `int` | number (integer) | Cold-start gate |
| `min_flavor_notes_for_ai` | `int` | number (integer) | Cold-start gate |
| `ai_primary_max_searches` | `int` | number (integer) | COST-5 cap |
| `ai_broadened_max_searches` | `int` | number (integer) | COST-5 cap |
| `ai_tool_version_anthropic` | `string` | text | AI-5 tool version string |
| `ai_tool_version_openai` | `string` | text | AI-5 tool version string |
| `ai_provider_default` | `string` | text | "anthropic" or "openai" |
| `photo_max_bytes` | `int` | number (integer) | Upload size cap |
| `csv_import_max_rows` | `int` | number (integer) | CSV import cap |
| `home_recent_brews_limit` | `int` | number (integer) | Home page limit |
| `home_top_coffees_limit` | `int` | number (integer) | Home page limit |
| `home_top_coffees_min_sessions` | `int` | number (integer) | Analytics threshold |
| `home_top_flavors_min_rating` | `float` | number (step=0.25) | Rating floor |
| `home_sweetspot_min_sessions` | `int` | number (integer) | Analytics threshold |
| `encryption_key_primary_fingerprint` | `string` or `null` | read-only display | System-managed; value_type may be `null` before first key set |

**Read-only rows (D-04 — display only, not editable):**
| Key | value_type | Why Read-Only |
|-----|-----------|---------------|
| `last_ai_run_status` | `string` | System-written JSON blob; scheduler owns it |
| `last_backup_status` | `string` | System-written JSON blob; backup service owns it |
| `last_backup_at` | `null` | System-written; `null` value_type means no value yet |
| `setup_completed` | `bool` | Flipping to false re-opens `/setup` — dangerous |

**Note on `encryption_key_primary_fingerprint`:** This row starts as `value_type="null"` and transitions to `value_type="string"` on first `set_provider_credential` call (via the documented direct UPDATE exception). The admin settings editor should display it read-only regardless of its current type, since it is managed by the encryption service, not the admin. It is NOT in the D-04 explicit read-only list but should be treated as such. **[ASSUMED — D-04 does not name it explicitly; recommend planner confirm with John]**

---

## System Info Data Sources (D-09)

| Data Point | Source | Code |
|------------|--------|------|
| App version | `importlib.metadata.version("coffee-snobbery")` | `pyproject.toml` name = `"coffee-snobbery"` [VERIFIED: pyproject.toml line 6] |
| DB server version | `SELECT version()` or `SHOW server_version` | Raw SQL via sync `db.execute(text("SELECT version()")).scalar()` |
| Active session count | `SELECT COUNT(*) FROM sessions WHERE expires_at > now()` | Direct query on `sessions` table |
| Photo storage usage | `Path("/app/data/photos").rglob("*")` disk walk, sum `.stat().st_size` | Same volume at `_DEFAULT_PHOTOS_DIR` |
| Backup storage usage | `Path("/app/data/backups").iterdir()` disk walk | Same volume at `_DEFAULT_BACKUP_DIR` |
| Last backup status + timestamp | Raw DB query on `app_settings` key `last_backup_status` | JSON parse the value string |

---

## API Health Panel Data Sources (D-10)

**`last_ai_run_status` JSON shape** (from `backup.py` / scheduler Phase 8 SCHED-03):
The Phase 8 scheduler writes this as a JSON string with fields: `users_processed`, `regenerations`, `skips`, `tokens_input_total`, `tokens_output_total`, `tokens_input_search_total`, `errors`, `timestamp`.

**`ai_recommendations` columns for per-provider health:**
From `app/models/ai_recommendation.py` (all verified):
- `provider_used: Text` — `"anthropic"` | `"openai"`
- `model_used: Text` — exact model ID string
- `recommendation_type: Text` — `"coffee"` | `"equipment"` | `"paste_rank"` | `"sweet_spots"`
- `generated_at: TIMESTAMP(timezone=True)` — when the row was written
- `generated_by: Text` — `"scheduler"` | `"manual_refresh"` | (Phase 9: `"admin"` | `"admin_force"`)
- `error_status: Text | None` — NULL on success; short failure code on error

**Query pattern for last 5 errors per provider:**
```sql
SELECT error_status, model_used, generated_at
FROM ai_recommendations
WHERE provider_used = :provider AND error_status IS NOT NULL
ORDER BY generated_at DESC
LIMIT 5
```

---

## Router Registration in main.py

`admin_router.router` is already included in `app/main.py` at line 231:
```python
app.include_router(admin_router.router)
```

The current stub has `router = APIRouter()` with no prefix. Phase 9 sub-routes will either:
- Keep no prefix on the top-level router and use `/admin/...` paths explicitly in each route decorator (current pattern), OR
- Add `prefix="/admin"` to the router and use relative paths

The stub route is `@router.get("/admin", ...)` — no prefix on the router. The expansion can follow the same pattern or switch to prefix. Either works; recommend prefix for cleanliness if the router becomes a sub-package.

---

## Events to Add in app/events.py

Existing admin events (verified from `app/events.py` lines 44-57):
- `ADMIN_USER_CREATED = "admin.user_created"`
- `ADMIN_USER_DELETED = "admin.user_deleted"`
- `ADMIN_PASSWORD_RESET = "admin.password_reset"`
- `ADMIN_IS_ADMIN_TOGGLED = "admin.is_admin_toggled"`
- `ADMIN_APP_SETTING_CHANGED = "admin.app_setting_changed"`
- `ADMIN_API_CREDENTIAL_SET = "admin.api_credential_set"`

**Missing events needed for Phase 9** (add to `app/events.py`):
```python
ADMIN_USER_UPDATED = "admin.user_updated"          # generic edit (deactivate, etc.)
ADMIN_USER_DEACTIVATED = "admin.user_deactivated"  # explicit deactivate action
ADMIN_BACKUP_TRIGGERED = "admin.backup_triggered"  # "Run backup now" button
ADMIN_AI_REFRESH_TRIGGERED = "admin.ai_refresh_triggered"  # manual AI refresh
ADMIN_PROVIDER_TEST = "admin.provider_test"        # "Test connection" probe
```

---

## Common Pitfalls

### Pitfall 1: `sessions.py` is async-only
**What goes wrong:** Admin handler calls `sessions.delete_session(db, session_id)` from a sync `def` handler — this is an `async def` that returns a coroutine; calling it without `await` silently no-ops.
**Root cause:** All session helpers use `AsyncSession`, not sync `Session`.
**How to avoid:** Session-deletion handlers must be `async def`. Use `async with async_session_factory() as async_db:` for the async DB work.
**Warning signs:** If `delete_session` returns without raising but the target user's session survives, the `await` was missing.

### Pitfall 2: `get_str()` raises after backup / AI run
**What goes wrong:** Admin health panel calls `settings_service.get_str("last_backup_status")` and gets `SettingNotFoundError`.
**Root cause:** `backup.write_backup_status` calls `set_setting` which pops the cache key; `prewarm_cache` is not called again until next startup.
**How to avoid:** Use raw DB query for these specific rows. The `backup.py` module docstring explicitly documents this contract.
**Warning signs:** `SettingNotFoundError` on `last_backup_status` or `last_ai_run_status` after a manual backup run.

### Pitfall 3: Decrypted key leaks via template context
**What goes wrong:** Handler passes `ProviderCredential` or raw decrypted key string to the Jinja template context dict.
**Root cause:** SEC-6 violation — the template renders the key in HTML visible in browser dev tools.
**How to avoid:** Only pass `last_four` to templates. The `ProviderCredential` dataclass must not enter the template context.
**Warning signs:** Any `cred.key` or `cred` in a `templates.TemplateResponse(context={...})` call.

### Pitfall 4: `regenerate()` called from sync handler
**What goes wrong:** `TypeError: object Response can't be used in 'await' expression` or silent no-op depending on how it's called.
**Root cause:** `ai_service.regenerate()` is `async def` (verified at line 1126).
**How to avoid:** "Run AI refresh now" handler must be `async def`; iterate eligible users and `await regenerate(...)` per user.

### Pitfall 5: Path traversal in backup download
**What goes wrong:** `GET /admin/backups/../../../etc/passwd` serves arbitrary files.
**How to avoid:** Validate filename against strict regex FIRST (`^(?:db|photos)_\d{4}-\d{2}-\d{2}\.(?:sql|tar\.gz)$`). Then `Path.resolve().is_relative_to(backup_dir.resolve())`. Same dual-check pattern as `photos.py`.

### Pitfall 6: Hard-delete without `brew_sessions` check
**What goes wrong:** DB raises `psycopg.errors.ForeignKeyViolation` (wrapped as `sqlalchemy.exc.IntegrityError`) because of the RESTRICT FK on `brew_sessions.user_id`.
**Root cause:** `brew_sessions.user_id` FK is `ondelete="RESTRICT"` (verified from `p5_brew_sessions.py`).
**How to avoid:** Query `COUNT(brew_sessions) WHERE user_id = target` before attempting DELETE. Return 409 Conflict if count > 0. The application check is the UX layer; the DB RESTRICT is the safety net.

### Pitfall 7: Last-admin / self-lockout race
**What goes wrong:** Two concurrent admin requests both read the admin count as 2, both attempt to demote/delete the same admin, one succeeds and leaves the system with one admin, but then the second request finds count still appears as 1 and also succeeds, leaving zero admins.
**Root cause:** No locking on the admin-count check.
**How to avoid:** Use a `SELECT COUNT(*) FROM users WHERE is_admin=true AND is_active=true FOR UPDATE` check within a transaction before any admin-demotion or admin-delete operation. At household scale this is a theoretical edge case, but the guard must exist per D-16.

### Pitfall 8: Missing CSRF on every state-changing admin route
**What goes wrong:** Admin forms work but security audit fails; CSRF tests fail.
**How to avoid:** Every POST/PUT/DELETE in the admin area must include the CSRF hidden field in the template and the `CSRFFormFieldShim` will hoist it. No route is exempt.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0 + pytest-asyncio |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/phase_09/ -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADMIN-01 | User list renders | smoke | `pytest tests/phase_09/test_admin_users.py::test_list_users -x` | Wave 0 |
| ADMIN-01 | User create succeeds | unit | `pytest tests/phase_09/test_admin_users.py::test_create_user -x` | Wave 0 |
| ADMIN-01 | User create fails < 12-char password | unit | `pytest tests/phase_09/test_admin_users.py::test_create_user_short_password -x` | Wave 0 |
| ADMIN-01 | Last-admin delete blocked | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_last_admin_blocked -x` | Wave 0 |
| ADMIN-01 | Self-demotion blocked | unit | `pytest tests/phase_09/test_admin_users.py::test_self_demote_blocked -x` | Wave 0 |
| ADMIN-01 | Delete user with brew_sessions blocked (D-15) | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_user_with_sessions_blocked -x` | Wave 0 |
| ADMIN-01 | Delete user without brew_sessions succeeds | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_empty_user -x` | Wave 0 |
| ADMIN-01 | is_admin toggle invalidates target sessions | unit | `pytest tests/phase_09/test_admin_users.py::test_toggle_admin_invalidates_sessions -x` | Wave 0 |
| ADMIN-02 | Set credential encrypts; last_four shown, key not in response | unit | `pytest tests/phase_09/test_admin_credentials.py::test_set_credential_masked -x` | Wave 0 |
| ADMIN-02 | Decrypted key never in Pydantic model or template context (SEC-6) | grep/static | CI grep for `cred.key` in template context dicts | Wave 0 |
| ADMIN-03 | Settings editor renders all rows | smoke | `pytest tests/phase_09/test_admin_settings.py::test_settings_list -x` | Wave 0 |
| ADMIN-03 | Editable row save calls `set_setting` + invalidates cache | unit | `pytest tests/phase_09/test_admin_settings.py::test_setting_save -x` | Wave 0 |
| ADMIN-03 | Read-only rows not editable (D-04) | unit | `pytest tests/phase_09/test_admin_settings.py::test_readonly_rows_rejected -x` | Wave 0 |
| ADMIN-04 | Backup list renders retained files | smoke | `pytest tests/phase_09/test_admin_backups.py::test_backup_list -x` | Wave 0 |
| ADMIN-04 | Backup download — valid filename serves file | unit | `pytest tests/phase_09/test_admin_backups.py::test_download_valid -x` | Wave 0 |
| ADMIN-04 | Backup download — path traversal blocked | unit | `pytest tests/phase_09/test_admin_backups.py::test_download_path_traversal -x` | Wave 0 |
| ADMIN-04 | "Run backup now" returns BackupResult | unit/integration | `pytest tests/phase_09/test_admin_backups.py::test_run_backup_now -x` | Wave 0 |
| ADMIN-05 | System info panel renders app version | smoke | `pytest tests/phase_09/test_admin_system.py::test_system_info -x` | Wave 0 |
| ADMIN-06 | Health panel reads last_ai_run_status via raw DB query | unit | `pytest tests/phase_09/test_admin_system.py::test_health_panel_raw_db -x` | Wave 0 |
| SEC | `require_admin` on every admin route | unit | `pytest tests/phase_09/test_admin_security.py::test_non_admin_403 -x` | Wave 0 |
| SEC | CSRF on every state-changing form | unit | `pytest tests/phase_09/test_admin_security.py::test_csrf_required -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/phase_09/ -q`
- **Per wave merge:** `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/phase_09/__init__.py`
- [ ] `tests/phase_09/test_admin_users.py`
- [ ] `tests/phase_09/test_admin_credentials.py`
- [ ] `tests/phase_09/test_admin_settings.py`
- [ ] `tests/phase_09/test_admin_backups.py`
- [ ] `tests/phase_09/test_admin_system.py`
- [ ] `tests/phase_09/test_admin_security.py`
- [ ] Shared fixtures: admin user + regular user + session rows — likely extend existing `conftest.py` fixtures from earlier phases

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `require_admin` Depends on every route; argon2id for password reset |
| V3 Session Management | yes | Delete target user's sessions on privilege change (`AsyncSession` delete) |
| V4 Access Control | yes | `require_admin` gate; last-admin guard; self-lockout guard; IDOR (user_id from path, not form) |
| V5 Input Validation | yes | Pydantic v2 schemas for user create/edit; strict regex for backup filenames |
| V6 Cryptography | partial | Never hand-roll; `services/encryption.py` is the only path for API key material |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal on backup download | Tampering | Strict regex + `Path.resolve().is_relative_to()` double-check (photos.py pattern) |
| Decrypted API key in template / log | Information Disclosure | SEC-6: key stays in handler scope; only `last_four` to templates |
| Last-admin lockout | Denial of Service | Server-side count check in transaction before any admin-demotion; self-lockout guard |
| CSRF on admin forms | Tampering/Elevation | `CSRFFormFieldShim` + hidden `X-CSRF-Token` field in every form |
| IDOR on user management | Elevation of Privilege | User ID from URL path parameter, admin gate via `require_admin`, not from form body |
| Session fixation after is_admin toggle | Elevation of Privilege | Delete all target user's session rows immediately on toggle |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `encryption_key_primary_fingerprint` should be treated as read-only in the settings editor even though D-04 doesn't name it explicitly | App Settings Inventory | If editable, admin could corrupt the fingerprint/credential alignment; low risk since write goes through `set_setting` (not the exception path), but the value should match the running encryption key |
| A2 | `p1_sessions_table.py` sets `ondelete="CASCADE"` on `sessions.user_id -> users.id` | Q2 (sessions FK) | If RESTRICT, hard-deleting a user requires deleting their sessions first; if CASCADE, the DB handles it automatically. Either way the handler must delete sessions before or alongside the user delete |
| A3 | `async_session_factory` imported from `app.main` is the correct factory for session-deletion handlers | Handler design | If the factory is reorganized into `app.db`, import path changes; low risk at current codebase state |

**A2 verification:** The `p1_sessions_table.py` migration was not read in this session. The planner should verify the `ondelete` clause on `sessions.user_id`. Given the Phase 2 CONTEXT note that "deactivating logs them out on next request (Phase 2 D-10 path)" — the middleware handles deactivation gracefully even without session deletion, but explicit deletion is the cleaner UX.

---

## Open Questions (RESOLVED at plan-phase 2026-05-21)

**Resolutions (applied in plans):** (1) `encryption_key_primary_fingerprint` → rendered read-only in the 09-04 settings editor (`_READ_ONLY_KEYS`). (2) ADMIN-05/06 → one `/admin/system` page with System Info + API Health panels (09-06). (3) `brew_drafts` FK → the 09-02 delete handler removes the target's sessions first and wraps the user delete in try/except IntegrityError as a backstop; the `brew_sessions` RESTRICT FK remains the primary D-15 guard.

1. **`encryption_key_primary_fingerprint` in settings editor**
   - What we know: D-04 names four specific read-only rows; `encryption_key_primary_fingerprint` is not among them
   - What's unclear: Whether John wants to see and possibly edit this row
   - Recommendation: Treat as read-only display (matches the spirit of D-04 "system/critical rows read-only")

2. **ADMIN-05 + ADMIN-06 page split**
   - What we know: Context D-11 says "planner's call"
   - Recommendation: One `/admin/system` page with two panels (System Info above, API Health below) at desktop; they stack at 375px. Simpler nav, fewer routes.

3. **`brew_drafts` FK ondelete on user delete**
   - What we know: The migration creates `brew_drafts` but the FK clause was not verified
   - Likely: CASCADE (one draft per user, cleanup is appropriate)
   - Recommendation: Verify in `p5_brew_sessions.py` bottom half before implementing user delete

---

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies — all libraries already installed in the running container; Phase 9 adds no new packages)

---

## Sources

### Primary (HIGH confidence)
- `app/services/credentials.py` — `set_provider_credential`, `set_provider_enabled`, `get_provider_credential`, `ProviderCredential` (all verified)
- `app/services/settings.py` — `get_raw`, `set_setting`, cache invalidation contract (verified)
- `app/services/backup.py` — `run_backup` signature, `BackupResult`/`ArtifactResult`, `write_backup_status`, Phase 9 contract note (verified)
- `app/services/ai_service.py` lines 1126-1132 — `regenerate` signature (verified)
- `app/services/sessions.py` — `delete_session`, `regenerate_session` (both async; verified)
- `app/services/auth.py` — `hash_password(plaintext: str) -> str` (verified)
- `app/migrations/versions/0001_initial.py` — `app_settings` 19 seed rows + value_types + FK ondelete clauses (verified)
- `app/migrations/versions/p5_brew_sessions.py` lines 75-76 — `brew_sessions.user_id ondelete="RESTRICT"` (verified)
- `app/models/ai_recommendation.py` — `generated_by` column type Text with no DB CHECK constraint; comment documents `"scheduler" | "manual_refresh"` (verified)
- `app/models/user.py` — User model columns (verified)
- `app/routers/photos.py` — FileResponse pattern + path traversal defense (verified)
- `app/routers/roasters.py` — HTMX + CSRF form pattern (verified)
- `app/main.py` lines 120, 231 — `async_session_factory` definition + admin router inclusion (verified)
- `app/events.py` — existing admin.* event constants (verified)
- `pyproject.toml` line 6 — `name = "coffee-snobbery"` (verified)
- `github.com/anthropics/anthropic-sdk-python/blob/main/api.md` — `client.models.list()` exists (VERIFIED via WebFetch)
- `github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_exceptions.py` — `AuthenticationError` (HTTP 401), `APIConnectionError` (connection-level) (VERIFIED via WebFetch)
- `github.com/openai/openai-python/blob/main/api.md` — `client.models.list()` exists (VERIFIED via WebFetch)
- `github.com/openai/openai-python/blob/main/src/openai/_exceptions.py` — `AuthenticationError` (HTTP 401), `APIConnectionError` (connection-level) (VERIFIED via WebFetch)

### Tertiary (LOW confidence — training knowledge, not verified this session)
- `p1_sessions_table.py` FK ondelete clause for `sessions.user_id` [ASSUMED — file not read]
- `brew_drafts.user_id` FK ondelete clause [ASSUMED — bottom of `p5_brew_sessions.py` not read]

---

## Metadata

**Confidence breakdown:**
- Resolved unknowns (Q1-Q4): HIGH — all verified from source files and GitHub SDK exception files
- Service contract signatures: HIGH — read directly from source
- App settings inventory: HIGH — read from migration file
- SDK auth probe: HIGH — `models.list()` confirmed in both SDK api.md files; exception classes confirmed from `_exceptions.py`
- Assumptions A2-A3: LOW — files not read this session

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (stable domain; SDK pinned tight)
