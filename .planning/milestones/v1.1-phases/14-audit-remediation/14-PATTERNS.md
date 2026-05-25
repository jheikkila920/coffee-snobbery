# Phase 14: Audit Remediation - Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 7 target files (5 source edits + 4 test files with updates/additions)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/routers/admin/users.py` (B1 fix + B4 deletion) | router/handler | CRUD + request-response | same file (existing `select(func.count()).select_from(...)` at :489) | exact — self-analog |
| `app/services/ai_service.py` (S1 `_assert_public_host` + insertion) | service utility | request-response | same file (`_verify_buy_url` :157 and `_fetch_page_text` :1466) | exact — self-analog |
| `app/services/scheduler.py` (B2 new job) | scheduler/service | event-driven (cron) | same file `run_nightly_backup` :340, `register_jobs` :116 | exact — self-analog |
| `app/rate_limit.py` (S4 `SEARCH_LIMIT` constant) | config/middleware | request-response | same file `LOGIN_LIMIT`/`CSP_REPORT_LIMIT` :40-42 | exact — self-analog |
| `app/routers/search.py` (S4 decorator + length cap) | router/handler | request-response | `app/routers/auth.py` login route :229-231 | role-match |
| `tests/phase_09/test_admin_users.py` (B1 multi-admin tests) | test | — | same file `TestDeactivateUser` :213-257 + `two_admins` fixture | exact |
| `tests/services/test_ai_service.py` (S1 SSRF tests) | test | — | same file :192-216 (scheme + redirect tests) | exact |
| `tests/test_scheduler.py` (B2 job count update + sweep tests) | test | — | same file `test_idempotent_job_registration` :23-53 | exact |
| `tests/test_search.py` (S4 length cap test) | test | — | same file `test_short_query_empty` :437-453 | exact |

---

## Pattern Assignments

### B1 — `app/routers/admin/users.py`: Fix `_count_active_admins` (lines 64-68)

**Analog:** `users.py:489` — `select(func.count()).select_from(BrewSession)` (same file, same pattern)

**Current buggy implementation** (lines 64-68):
```python
def _count_active_admins(db: Session) -> int:
    """Count active admin users with a FOR UPDATE row lock (Pitfall 7)."""
    return db.execute(
        text("SELECT COUNT(*) FROM users WHERE is_admin = true AND is_active = true FOR UPDATE")
    ).scalar_one()
```

**Correct count pattern from same file** (lines 489-491):
```python
brew_count = db.execute(
    select(func.count()).select_from(BrewSession).where(BrewSession.user_id == target_id)
).scalar_one()
```

**Fixed implementation to write** (replaces lines 64-68 verbatim):
```python
def _count_active_admins(db: Session) -> int:
    """Count active admin users with a FOR UPDATE row lock (Pitfall 7)."""
    locked_subq = (
        select(User.id)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .with_for_update()
        .subquery()
    )
    return db.execute(
        select(func.count()).select_from(locked_subq)
    ).scalar_one()
```

`text` import can be removed from line 40 after this change (verify no other `text(...)` call remains before removing — `scheduler.py` also uses `text` in `run_nightly_ai_refresh`, but that is a different file). In `users.py` specifically, grep for `text(` to confirm safe removal.

**Call sites confirmed** (all call `_count_active_admins(db)` unchanged):
- `update_user` line 292 — demote path
- `toggle_admin` line 365 (not shown, confirmed by research)
- `deactivate_user` line 416 (not shown, confirmed by research)
- `delete_user` line 484

---

### B4 — `app/routers/admin/users.py`: Delete dead code (lines 298-300)

**Context** (lines 289-302 shown for full picture):
```python
    # D-16 guard if is_admin is being demoted
    if target.is_admin and not new_is_admin_raw:
        # Use transaction for FOR UPDATE count
        admin_count = _count_active_admins(db)
        if admin_count <= 1:
            return _render_error_fragment(request, "Cannot demote the last active admin.", 409)
        if target_id == admin_user.id:
            return _render_error_fragment(request, "Cannot demote yourself.", 409)

    # Self-lockout guard on is_admin demotion   <- DELETE this block (lines 298-300)
    if target.is_admin and not new_is_admin_raw and target_id == admin_user.id:
        return _render_error_fragment(request, "Cannot demote yourself.", 409)

    # Apply changes
```

**Action:** Delete lines 298-300 (the comment + the `if` block). The condition at line 295-296 already covers `target_id == admin_user.id`; the outer guard at 290 also requires `target.is_admin and not new_is_admin_raw`, so line 299 is unreachable in every path.

---

### S1 — `app/services/ai_service.py`: Add `_assert_public_host` helper + insert calls

**Existing imports** (lines 20-30) — stdlib modules to add alongside:
```python
from __future__ import annotations

import asyncio
import hashlib
import html.parser
import json
import time
from typing import Any

import anthropic
import httpx
```
Add `import ipaddress`, `import socket`, and `from urllib.parse import urlparse` to this block.

**Existing SSRF scaffolding in `_verify_buy_url`** (lines 157-202 — the structure the new gate slots into):
```python
async def _verify_buy_url(url: str, roaster_name: str, coffee_name: str) -> bool:
    # Scheme allowlist — no network call for non-https (T-07-SSRF)
    if not url.startswith("https://"):
        return False

    # <-- INSERT: if not _assert_public_host(url): return False

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(5.0),
        ) as client:
            r = await client.get(url, headers={"Range": "bytes=0-65535", "User-Agent": VERIFY_UA})

        if r.status_code not in (200, 206):
            return False
        body = r.text.lower()
        return roaster_name.lower() in body or coffee_name.lower() in body
    except (httpx.TimeoutException, httpx.RequestError):
        return False
```

**Existing SSRF scaffolding in `_fetch_page_text`** (lines 1466-1499 — same insertion point):
```python
async def _fetch_page_text(url: str) -> str:
    # Scheme allowlist — no network call for non-https (T-07-09 SSRF)
    if not url.startswith("https://"):
        return ""

    # <-- INSERT: if not _assert_public_host(url): return ""

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(5.0),
        ) as client:
            r = await client.get(url, headers={"Range": "bytes=0-131071", "User-Agent": VERIFY_UA})

        if r.status_code not in (200, 206):
            return ""
```

**New helper to add** (place near the other SSRF helpers, after line 202 or before `_count_active_admins` — either works; after `_verify_buy_url` is cleanest):
```python
def _assert_public_host(url: str) -> bool:
    """Return False if the URL host resolves to any private/reserved address.

    Handles IPv4, IPv6, and IPv4-mapped IPv6 (::ffff:10.x.x.x).
    TOCTOU caveat: DNS resolution is not pinned to the connection — a
    sub-millisecond window exists. Accepted at household scale (D-05).
    """
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # DNS failure -> reject

    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # Normalize IPv4-mapped IPv6 (::ffff:10.0.0.1 -> 10.0.0.1)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    return True
```

---

### B2 — `app/services/scheduler.py`: Add `nightly_session_sweep` job

**Existing `register_jobs` pattern** (lines 103-127 — copy/extend exactly):
```python
def register_jobs(sched: AsyncIOScheduler | None = None) -> None:
    target = sched if sched is not None else scheduler
    target.add_job(
        run_nightly_ai_refresh,
        CronTrigger(hour=0, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_ai_refresh",
        replace_existing=True,
    )
    target.add_job(
        run_nightly_backup,
        CronTrigger(hour=2, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_backup",
        replace_existing=True,
    )
    # ADD after existing two jobs:
    target.add_job(
        run_nightly_session_sweep,
        CronTrigger(hour=3, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_session_sweep",
        replace_existing=True,
    )
```

**Existing `run_nightly_backup` body pattern** (lines 340-360 — lazy-import style to copy):
```python
def run_nightly_backup() -> None:
    log.info(SCHEDULER_JOB_START, job_id="nightly_backup")
    try:
        from app.services.backup import run_backup  # lazy import avoids cycle

        run_backup()
        log.info(SCHEDULER_JOB_SUCCESS, job_id="nightly_backup")
    except Exception as exc:
        log.error(
            SCHEDULER_JOB_ERROR,
            job_id="nightly_backup",
            error_class=type(exc).__name__,
            error_msg=str(exc),
        )
        raise
```

**New job body to add** (after `run_nightly_backup`, before end of file; lazy-import `SessionModel` to mirror backup pattern):
```python
def run_nightly_session_sweep() -> None:
    """Delete expired sessions. Closes sessions.py:182-185 TODO."""
    log.info(SCHEDULER_JOB_START, job_id="nightly_session_sweep")
    try:
        from sqlalchemy import delete as sql_delete

        from app.models.session import Session as SessionModel

        with SessionLocal() as db:
            db.execute(
                sql_delete(SessionModel).where(SessionModel.expires_at < func.now())
            )
            db.commit()
        log.info(SCHEDULER_JOB_SUCCESS, job_id="nightly_session_sweep")
    except Exception as exc:
        log.error(
            SCHEDULER_JOB_ERROR,
            job_id="nightly_session_sweep",
            error_class=type(exc).__name__,
            error_msg=str(exc),
        )
        raise
```

Note: `func` is already imported at module level (line 42: `from sqlalchemy import func, select, text`). `SessionLocal` is already imported at module level (line 46). `sql_delete` and `SessionModel` are lazy-imported inside the function body to stay consistent with the backup pattern and avoid any import cycle risk.

**`Session` model `expires_at` column** (`app/models/session.py:60-62`):
```python
expires_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), nullable=False, index=True
)
```
The btree index on `expires_at` makes `WHERE expires_at < func.now()` an index scan.

---

### S4 — `app/rate_limit.py`: Add `SEARCH_LIMIT` constant

**Existing constant block** (lines 40-42 — append after `CSP_REPORT_LIMIT`):
```python
LOGIN_LIMIT: str = "5/15minutes"
SETUP_LIMIT: str = "5/15minutes"
CSP_REPORT_LIMIT: str = "30/minute"
# ADD:
SEARCH_LIMIT: str = "60/minute"
```

`limiter` module-level singleton (line 47):
```python
limiter = Limiter(key_func=get_remote_address, default_limits=[])
```
Both `limiter` and `SEARCH_LIMIT` are imported by `search.py`.

---

### S4 — `app/routers/search.py`: Add decorator + length cap

**Decorator order analog from `app/routers/auth.py`** (lines 229-231 — route decorator outermost, limiter next):
```python
@router.post("/login", response_class=HTMLResponse)
@limiter.limit(LOGIN_LIMIT)
async def login_post(request: Request, ...):
```

**Current `search_results` handler** (lines 30-49 — full function for executor context):
```python
@router.get("", response_class=HTMLResponse)
def search_results(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
) -> Response:
    if len(q.strip()) < 2:
        return HTMLResponse("", status_code=200)
    results = search_service.run_search(db, query=q.strip(), user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/search_results.html",
        context={"results": results, "query": q.strip()},
    )
```

**Modified version** — add import, decorator, and length cap (cap goes before the existing `< 2` check, operates on raw `q` before `.strip()`):
```python
from app.rate_limit import SEARCH_LIMIT, limiter

@router.get("", response_class=HTMLResponse)
@limiter.limit(SEARCH_LIMIT)
def search_results(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
) -> Response:
    if len(q) > 100:                        # S4: cap before strip()
        return HTMLResponse("", status_code=200)
    if len(q.strip()) < 2:
        return HTMLResponse("", status_code=200)
    results = search_service.run_search(db, query=q.strip(), user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/search_results.html",
        context={"results": results, "query": q.strip()},
    )
```

---

## Shared Patterns

### Structured logging in job bodies
**Source:** `app/services/scheduler.py:347-360`
**Apply to:** `run_nightly_session_sweep`
```python
log.info(SCHEDULER_JOB_START, job_id="nightly_session_sweep")
# ... work ...
log.info(SCHEDULER_JOB_SUCCESS, job_id="nightly_session_sweep")
# on except:
log.error(SCHEDULER_JOB_ERROR, job_id="...", error_class=type(exc).__name__, error_msg=str(exc))
```

### Failure-return convention in SSRF functions
**Source:** `app/services/ai_service.py:179-202`
- `_verify_buy_url`: returns `False` on any guard failure
- `_fetch_page_text`: returns `""` on any guard failure
- `_assert_public_host`: returns `False` on DNS failure or private address (matches `_verify_buy_url`'s convention; callers convert `False` to `""` where needed)

### `HTMLResponse("", status_code=200)` empty-200 shape
**Source:** `app/routers/search.py:43`
```python
return HTMLResponse("", status_code=200)
```
Used for both the existing `< 2` guard and the new `> 100` cap. Same shape — HTMX clears the results container.

---

## Test Pattern Assignments

### `tests/phase_09/test_admin_users.py` — B1 multi-admin tests

**Analog:** same file, `TestDeactivateUser.test_last_admin_deactivate_blocked` (lines ~213-257) + `two_admins` fixture

**`two_admins` fixture** (`tests/phase_09/conftest.py:171-185`):
```python
@pytest.fixture
def two_admins() -> dict[str, Any]:
    a1 = _seed_user(is_admin=True)
    a2 = _seed_user(is_admin=True)
    return {
        "admin1_id": a1["user"].id,
        "admin1_cookie": a1["signed_cookie"],
        "admin2_id": a2["user"].id,
        "admin2_cookie": a2["signed_cookie"],
    }
```

**Existing guard test shape** (lines 236-257 — copy structure for new `TestMultiAdminOperations` class):
```python
def test_self_demote_blocked(self, client: Any, two_admins: dict[str, Any]) -> None:
    admin1_id = two_admins["admin1_id"]
    _prime_csrf(client, two_admins["admin1_cookie"])

    client.post(f"/admin/users/{admin1_id}/deactivate")

    from app.db import SessionLocal
    from app.models.user import User
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.id == admin1_id)).scalar_one_or_none()
    assert user is not None
    assert user.is_active is True
```

New tests follow the same shape but POST to demote admin2 (not admin1) and assert the operation **succeeds** (200, DB state changed). Cover all 4 call sites:
- `POST /admin/users/{admin2_id}` (update with `is_admin=false`) — `update_user`
- `POST /admin/users/{admin2_id}/toggle-admin` — `toggle_admin`
- `POST /admin/users/{admin2_id}/deactivate` — `deactivate_user`
- `POST /admin/users/{admin2_id}/delete` — `delete_user` (requires admin2 to have no brew sessions)

---

### `tests/services/test_ai_service.py` — S1 SSRF private-IP tests

**Analog:** same file, lines 192-216 (scheme + redirect tests)

**Existing test shape** (lines 192-199 — no-network, no respx needed):
```python
@pytest.mark.asyncio
async def test_url_verify_scheme_rejected() -> None:
    from app.services.ai_service import _verify_buy_url
    result = await _verify_buy_url("http://example.com/coffee", "Roaster", "Coffee")
    assert result is False
```

**Existing respx mock shape** (lines 202-216):
```python
@respx.mock
@pytest.mark.asyncio
async def test_url_verify_ssrf_redirect() -> None:
    from app.services.ai_service import _verify_buy_url
    url = "https://legitimate-shop.com/coffee"
    respx.get(url).mock(return_value=httpx.Response(302, headers={"Location": "..."}))
    result = await _verify_buy_url(url, "Roaster", "Coffee")
    assert result is False
```

**New SSRF tests use `unittest.mock.patch("socket.getaddrinfo")`** — no respx needed because `_assert_public_host` runs before the httpx call:
```python
from unittest.mock import patch
import socket

@pytest.mark.asyncio
async def test_ssrf_private_ipv4_blocked() -> None:
    from app.services.ai_service import _verify_buy_url
    mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('10.0.0.1', 443))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False

@pytest.mark.asyncio
async def test_ssrf_ipv4_mapped_ipv6_blocked() -> None:
    from app.services.ai_service import _verify_buy_url
    mock_result = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:169.254.169.254', 443, 0, 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False
```

---

### `tests/test_scheduler.py` — B2 job count update + sweep tests

**Line 49 — update assertion from 2 to 3**:
```python
# Before:
assert len(jobs) == 2
assert job_ids == {"nightly_ai_refresh", "nightly_backup"}

# After:
assert len(jobs) == 3
assert job_ids == {"nightly_ai_refresh", "nightly_backup", "nightly_session_sweep"}
```

**New sweep tests** — follow `test_eligibility_filter` shape (lines 88-159): uses `sync_db` fixture, seeds rows, calls function directly, asserts DB state. Key pattern:
```python
def test_session_sweep_deletes_expired(sync_db: Any) -> None:
    if sync_db is None:
        pytest.skip("sync_db not available")
    from datetime import timedelta
    from app.models.session import Session as SessionModel
    from app.services.scheduler import run_nightly_session_sweep
    # seed expired + unexpired Session rows via sync_db
    # call run_nightly_session_sweep()  (it opens its own SessionLocal internally)
    # query sync_db and assert expired row gone, unexpired row present
```

Note: `run_nightly_session_sweep` opens its own `SessionLocal()` internally, so the test can't rely on the `sync_db` fixture's transaction for the deleted rows — seed, commit, call job, query in a new session.

---

### `tests/test_search.py` — S4 length cap test

**Analog:** same file, `test_short_query_empty` (lines 437-453):
```python
def test_short_query_empty(client: Any, seeded_admin_user: dict[str, Any]) -> None:
    cookies = _make_cookie(seeded_admin_user)
    resp = client.get("/search?q=e", cookies=cookies)
    assert resp.status_code == 200
    assert resp.text.strip() == ""
```

**New test** — same shape, 101-char string:
```python
def test_long_query_returns_empty(client: Any, seeded_admin_user: dict[str, Any]) -> None:
    cookies = _make_cookie(seeded_admin_user)
    long_q = "a" * 101
    resp = client.get(f"/search?q={long_q}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.text.strip() == ""
```

---

## No Analog Found

All five fixes and all test additions have direct in-repo analogs. No file in this phase requires fallback to RESEARCH.md examples alone.

---

## Metadata

**Analog search scope:** `app/routers/admin/`, `app/services/`, `app/routers/`, `app/rate_limit.py`, `tests/phase_09/`, `tests/services/`, `tests/test_scheduler.py`, `tests/test_search.py`
**Files read:** 11 source/test files
**Pattern extraction date:** 2026-05-25
