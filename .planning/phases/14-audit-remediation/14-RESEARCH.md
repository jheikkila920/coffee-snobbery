# Phase 14: Audit Remediation - Research

**Researched:** 2026-05-25
**Domain:** SQLAlchemy 2.0 subquery locking, stdlib SSRF mitigation, APScheduler 3.x job registration, slowapi rate limiting, pytest test patterns
**Confidence:** HIGH

## Summary

This is a focused confirmation pass. Five defects are locked in CONTEXT.md with pinned file:line root causes and exact fix strategies. No alternative approaches need evaluation. The research confirms the correct SQLAlchemy 2.0 idiom for a subquery `COUNT` with `FOR UPDATE`, verifies the `socket.getaddrinfo` + `ipaddress` SSRF pattern against Python stdlib, confirms APScheduler 3.x `CronTrigger` idempotency behavior, validates the existing `slowapi` decorator pattern, and maps each fix to the test conventions already established in the suite.

All five fixes use only stdlib or libraries already present in the running container. No new dependencies are introduced. The branch strategy (D-10) is feature-branch for B1 + S1 (auth/security); S4, B2, B4 can ship together with the same branch since they are in scope.

**Primary recommendation:** Implement as a single feature branch with five atomic commits (one per defect), in severity order (B1, S1, B2, S4, B4). Tests for each fix live alongside existing test files — no new top-level test modules needed.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Fix `_count_active_admins` by wrapping the locked SELECT in a subquery: `SELECT COUNT(*) FROM (SELECT id FROM users WHERE is_admin = true AND is_active = true FOR UPDATE) sub`. Keeps the row lock. Sync DB handlers in a threadpool can race; FOR UPDATE is not decorative.
- **D-02:** Add regression test for the currently-untested path: admin A demoting/deactivating/deleting admin B with 2+ admins must succeed. Cover all 4 call sites (~292/365/416/484). Existing guard tests must still pass.
- **D-03:** SSRF fix = resolve-validate-connect via `socket.getaddrinfo` + stdlib `ipaddress`. NOT full IP pinning. Sub-ms TOCTOU window is accepted at household scale.
- **D-04:** Block ranges via `ipaddress`: `is_private`, `is_loopback`, `is_link_local`, `is_reserved`. Must handle IPv4-mapped IPv6 (`::ffff:...`). Apply to BOTH `_verify_buy_url` (~:157) and `_fetch_page_text` (~:1466). Extend existing scaffolding; do NOT rewrite.
- **D-05 [Roadmap Amendment]:** Accepted behavior is "block on pre-resolve validation of all resolved IPs" with documented sub-ms TOCTOU window. The "pinned IP" wording in ROADMAP success criterion #2 is superseded.
- **D-06:** Add nightly APScheduler job in `scheduler.py`: `DELETE FROM sessions WHERE expires_at < now()`, scheduled 03:00 APP_TIMEZONE, stable id `nightly_session_sweep`, `replace_existing=True`. Scheduler-only — no admin button. Closes TODO at `sessions.py:182-185`.
- **D-07:** Cap `q` at 100 chars in `search.py` — over-long input short-circuits to empty 200.
- **D-08:** Add `SEARCH_LIMIT = "60/minute"` constant to `app/rate_limit.py`; decorate `search_results` with `@limiter.limit(SEARCH_LIMIT)`.
- **D-09:** Delete unreachable duplicate self-demote guard at `users.py:298-300`.
- **D-10:** B1 and S1 touch auth/admin/security — work on feature branch + merge. John approved the scope.

### Claude's Discretion
- Exact wave/plan breakdown.
- Whether items ship as one PR with atomic per-item commits or split branches (dependency analysis: B1+B4 share `users.py`; B2 is disjoint in `scheduler.py`; S1 is disjoint in `ai_service.py`; S4 is disjoint in `search.py` + `rate_limit.py`).
- Whether the SSRF resolve-and-validate helper is a shared `_assert_public_host(url)` helper (DRY) or inline in each function.

### Deferred Ideas (OUT OF SCOPE)
- Admin "Sweep sessions now" button — scope creep beyond the roadmap's job-only B2.
- Full DNS-rebinding-safe IP pinning for SSRF fetchers — revisit only if threat model changes.
</user_constraints>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| B1: Admin last-admin guard | API / Backend | — | Pure DB query fix in a sync handler; no frontend touch |
| S1: SSRF private-IP block | API / Backend | — | Pre-network validation in the AI service layer |
| B2: Expired-session sweep | API / Backend (scheduler) | Database | APScheduler job issues a DELETE against the sessions table |
| S4: Search rate limit + length cap | API / Backend | — | Handler-level guard + slowapi middleware decoration |
| B4: Dead code removal | API / Backend | — | Pure deletion in the admin router |

---

## Standard Stack

No new libraries. All fixes use the existing container stack.

| Component | Confirmed Version | Purpose in this Phase |
|-----------|------------------|----------------------|
| SQLAlchemy 2.0 | 2.0.49 | Subquery FOR UPDATE pattern (B1) |
| Python stdlib `socket` | 3.12 built-in | `getaddrinfo` DNS resolution (S1) |
| Python stdlib `ipaddress` | 3.12 built-in | Private/reserved IP classification (S1) |
| APScheduler 3.x | 3.11.2 | CronTrigger job registration (B2) |
| slowapi | 0.1.9 | Rate limit decoration (S4) |
| pytest + respx | existing in suite | Test mocking for SSRF + async |

[VERIFIED: codebase grep — all five libraries/modules already imported and used in the running container]

---

## Architecture Patterns

### B1: SQLAlchemy 2.0 Subquery COUNT with FOR UPDATE

**The bug:** PostgreSQL rejects `SELECT COUNT(*) ... FOR UPDATE` as invalid — aggregate functions cannot hold row locks. The current code uses `text("SELECT COUNT(*) FROM users WHERE is_admin = true AND is_active = true FOR UPDATE")`.

**The fix (SQLAlchemy 2.0 ORM style, matching project conventions):**

```python
# Source: SQLAlchemy 2.0 docs — select(), with_for_update(), subquery()
from sqlalchemy import func, select

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

[VERIFIED: codebase — project already uses `select(func.count()).select_from(...)` pattern at `test_admin_users.py:280` and `users.py:489`. The `with_for_update()` method is SQLAlchemy 2.0 standard.]

**Why this is correct PostgreSQL:** `SELECT COUNT(*) FROM (SELECT id ... FOR UPDATE) sub` is valid because the `FOR UPDATE` applies to the inner rows selected by the subquery; the outer `COUNT(*)` aggregates over the already-locked row IDs. PostgreSQL allows this because the lock is on the subquery result set, not the aggregate expression itself.

[ASSUMED — training knowledge on PostgreSQL subquery FOR UPDATE validity; the live error `ERROR: FOR UPDATE is not allowed with aggregate functions` and the fix pattern are both documented in CONTEXT.md as verified against the live DB]

**Call sites confirmed (all use `_count_active_admins(db)` unmodified):**
- `update_user` ~line 292: demote path only (B4 dead code at 298-300 is after this call)
- `toggle_admin` ~line 365: confirmed in source
- `deactivate_user` ~line 416: confirmed in source
- `delete_user` ~line 484: confirmed in source

Single function fix — all four call sites benefit automatically.

### S1: SSRF resolve-validate pattern

**Existing scaffolding to extend (do NOT replace):**
- `_verify_buy_url`: scheme check → `client.get(url, follow_redirects=False, timeout=5s, Range=64KB)` → status check → content check
- `_fetch_page_text`: scheme check → `client.get(url, follow_redirects=False, timeout=5s, Range=128KB)` → status check → text extraction

**The new gate (insert between scheme check and `client.get`):**

```python
# Source: Python 3.12 stdlib — socket, ipaddress
import ipaddress
import socket
from urllib.parse import urlparse

def _assert_public_host(url: str) -> bool:
    """Return False if the URL host resolves to any private/reserved address.

    Handles IPv4, IPv6, and IPv4-mapped IPv6 (::ffff:10.x.x.x).
    TOCTOU caveat: the DNS resolution is not pinned to the connection — a
    sub-millisecond window exists. Accepted at household scale (D-05).
    """
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        # getaddrinfo returns a list of (family, type, proto, canonname, sockaddr)
        # sockaddr is (address, port) for IPv4, (address, port, flow, scope) for IPv6
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # DNS failure → reject

    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # Normalize IPv4-mapped IPv6 (::ffff:10.0.0.1 -> 10.0.0.1)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
        ):
            return False
    return True
```

[VERIFIED: Python 3.12 stdlib — `socket.getaddrinfo`, `ipaddress.ip_address`, `IPv6Address.ipv4_mapped`, `is_private`, `is_loopback`, `is_link_local`, `is_reserved` all exist in 3.12. `is_private` covers `10/8`, `172.16/12`, `192.168/16`, `fc00::/7` (ULA). `is_loopback` covers `127/8`, `::1`. `is_link_local` covers `169.254/16`, `fe80::/10`. `is_reserved` covers additional special-purpose ranges.]

**IPv4-mapped IPv6 normalization is critical:** `::ffff:169.254.169.254` (the AWS metadata endpoint) would pass `is_link_local` if checked as an IPv6 address — the `ipv4_mapped` attribute returns the embedded IPv4 address when set, enabling correct classification. [VERIFIED: Python 3.12 ipaddress module — `IPv6Address.ipv4_mapped` returns an `IPv4Address` instance when the address is an IPv4-mapped IPv6 address, else `None`]

**DRY recommendation (Claude's Discretion):** Extract as `_assert_public_host(url: str) -> bool` helper function in `ai_service.py`, called by both `_verify_buy_url` and `_fetch_page_text`. Avoids duplicating the 15 lines at both sites. Return convention: `False` from both callers on rejection (matches existing `return False` / `return ""` patterns).

**Placement in each function:**
```python
# In _verify_buy_url — after scheme check, before client.get:
if not _assert_public_host(url):
    return False

# In _fetch_page_text — after scheme check, before client.get:
if not _assert_public_host(url):
    return ""
```

### B2: APScheduler nightly session sweep

**Exact pattern to follow (from `scheduler.py:116-127`):**

```python
# Add to register_jobs() after the existing two add_job calls:
target.add_job(
    run_nightly_session_sweep,
    CronTrigger(hour=3, minute=0, timezone=settings.APP_TIMEZONE),
    id="nightly_session_sweep",
    replace_existing=True,
)
```

**Job body:** Must be a plain `sync def`, runs in `ThreadPoolExecutor` (same pattern as `run_nightly_ai_refresh` and `run_nightly_backup`).

```python
def run_nightly_session_sweep() -> None:
    """Delete expired sessions. Closes sessions.py:182-185 TODO."""
    log.info(SCHEDULER_JOB_START, job_id="nightly_session_sweep")
    try:
        with SessionLocal() as db:
            db.execute(
                sql_delete(SessionModel).where(
                    SessionModel.expires_at < func.now()
                )
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

[VERIFIED: codebase — `SessionLocal` imported at top of `scheduler.py`. `sql_delete` is imported as `from sqlalchemy import delete as sql_delete` in `users.py`; same import needed in `scheduler.py`. `func.now()` already imported in `scheduler.py` via `from sqlalchemy import func`. `SessionModel` needs to be imported (currently not in `scheduler.py` — lazy import inside function body is the established pattern for avoiding import cycles, matching `run_nightly_backup`'s lazy `from app.services.backup import run_backup`).

The `expires_at` btree index (`p1_sessions` migration) makes the DELETE cheap: index scan + delete, no seq scan.

**Job count after this fix:** 3 total (`nightly_ai_refresh` at 00:00, `nightly_backup` at 02:00, `nightly_session_sweep` at 03:00).

### S4: Search hardening

**Length cap (insert before the existing `< 2` guard):**

```python
# In search_results handler, before the existing len(q.strip()) < 2 check:
if len(q) > 100:
    return HTMLResponse("", status_code=200)
```

Note: cap on raw `q` (before `.strip()`) prevents a 101-char all-spaces string from sneaking through.

**Rate limit decoration:**

In `app/rate_limit.py`, add after `CSP_REPORT_LIMIT`:
```python
SEARCH_LIMIT: str = "60/minute"
```

In `app/routers/search.py`, add import and decorator:
```python
from app.rate_limit import SEARCH_LIMIT, limiter

@router.get("", response_class=HTMLResponse)
@limiter.limit(SEARCH_LIMIT)
def search_results(
    request: Request,
    ...
```

[VERIFIED: codebase — `search_results` is a `def` (sync), already takes `request: Request` as first positional parameter (required by slowapi for keying). The existing `LOGIN_LIMIT` decoration on `/login` uses the identical pattern. `limiter` is module-level in `rate_limit.py` and imported by other routers.]

**Pitfall:** slowapi requires `request: Request` to be a parameter of the decorated handler — it is already present in `search_results`. No change needed to the function signature.

### B4: Dead code removal

Lines 298-300 in `users.py`:
```python
    # Self-lockout guard on is_admin demotion
    if target.is_admin and not new_is_admin_raw and target_id == admin_user.id:
        return _render_error_fragment(request, "Cannot demote yourself.", 409)
```

This condition is unreachable because lines 290-296 already check:
- `admin_count <= 1` → returns early (which subsumes any single-admin scenario)
- `target_id == admin_user.id` → returns early at line 295-296

Pure deletion. No behavioral change.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IP range classification | Custom CIDR checkers | `ipaddress` stdlib | stdlib handles IPv4, IPv6, IPv4-mapped IPv6, all special ranges correctly |
| Scheduler idempotency | Manual duplicate detection | `replace_existing=True` in APScheduler | Built-in deduplication via stable job ID |
| Rate limit state | In-process dict | `slowapi` (already wired) | Already handles IP keying, 429 response, audit logging |

---

## Common Pitfalls

### Pitfall 1: FOR UPDATE on aggregate (the existing bug)
**What goes wrong:** PostgreSQL raises `ERROR: FOR UPDATE is not allowed with aggregate functions` when `FOR UPDATE` appears in the same SELECT as `COUNT(*)` or any aggregate.
**Why it happens:** Row locking (`FOR UPDATE`) operates on individual rows; aggregates collapse rows into scalars. PostgreSQL cannot lock a scalar.
**How to avoid:** Use a subquery: `SELECT COUNT(*) FROM (SELECT id ... FOR UPDATE) sub`. The inner query locks rows; the outer query counts the locked result set.
**Warning signs:** Any `text("SELECT COUNT(*) ... FOR UPDATE")` or `select(func.count()).with_for_update()` on the same query object.

### Pitfall 2: IPv4-mapped IPv6 bypass in SSRF checks
**What goes wrong:** `::ffff:169.254.169.254` is an IPv6 address. Without normalization, `addr.is_link_local` returns `False` (it's technically classified as an IPv4-mapped address in IPv6 space, not link-local IPv6). The AWS/GCP/Azure metadata endpoint would pass the check.
**Why it happens:** IPv4-mapped IPv6 addresses occupy `::ffff:0:0/96` which is in the "global" unicast range for IPv6 purposes.
**How to avoid:** Check `addr.ipv4_mapped is not None` first; if so, reclassify against the embedded IPv4 address before applying `is_private`/`is_loopback`/`is_link_local`/`is_reserved`.
**Warning signs:** Any SSRF guard that doesn't explicitly handle `IPv6Address.ipv4_mapped`.

### Pitfall 3: APScheduler job count assertion in tests
**What goes wrong:** Existing test `test_idempotent_job_registration` asserts `len(jobs) == 2` and `job_ids == {"nightly_ai_refresh", "nightly_backup"}`. After adding the third job, this test will fail.
**How to avoid:** Update the assertion to `len(jobs) == 3` and include `"nightly_session_sweep"` in the expected set. Both the assertion and the set must be updated together.
**Warning signs:** CI failure on `test_idempotent_job_registration` after the B2 commit.

### Pitfall 4: slowapi decorator order
**What goes wrong:** `@limiter.limit(...)` must be applied *after* `@router.get(...)` in the decorator stack (i.e., written *before* the route decorator, closer to the function). If written in the wrong order, slowapi's instrumentation may not fire.
**How to avoid:** Follow the established pattern from `app/routers/auth.py` — `@router.post(...)` is the outermost decorator, `@limiter.limit(LOGIN_LIMIT)` is the next line. [VERIFIED: codebase — confirmed in auth router: `@router.post("/login")` then `@limiter.limit(LOGIN_LIMIT)` on the next line, above `async def login_post`.]

### Pitfall 5: Session sweep deletes unexpired rows
**What goes wrong:** Using `<=` instead of `<` in the sweep condition (`expires_at <= func.now()`) would delete sessions that expire exactly at the current second — technically fine but semantically imprecise. Using the wrong column (`last_seen` instead of `expires_at`) would delete recently-active sessions.
**How to avoid:** The condition is `SessionModel.expires_at < func.now()`. `expires_at` is the authoritative expiry; `last_seen` is not.

### Pitfall 6: sync_db fixture vs client fixture for B1/B2 tests
**What goes wrong:** Tests that need to verify DB state (session rows deleted, admin guard behavior) must use a real DB. Tests using `sync_db` fixture skip cleanly when Postgres is unavailable; tests using the HTTP `client` fixture also skip. The B1 multi-admin test requires both an HTTP client (to POST to the admin endpoints) and DB verification.
**How to avoid:** Use the `two_admins` fixture pattern from `tests/phase_09/conftest.py` (seeds two admin rows via `_seed_user(is_admin=True)`) + the `client` fixture for HTTP calls + `SessionLocal()` for DB verification. The pattern is already established in `test_admin_users.py::TestDeleteUser`.

### Pitfall 7: `socket.getaddrinfo` can raise on invalid hostnames
**What goes wrong:** Malformed hostnames or valid-looking hostnames with no DNS record raise `OSError` (specifically `socket.gaierror`, a subclass of `OSError`). Unhandled, this propagates out of `_verify_buy_url`/`_fetch_page_text` rather than returning the failure sentinel.
**How to avoid:** Wrap the `getaddrinfo` call in `try/except OSError: return False` (or `return ""`). This matches the existing broad `except (httpx.TimeoutException, httpx.RequestError)` failure-return convention in both functions.

---

## Code Examples

### SQLAlchemy 2.0 — subquery with FOR UPDATE

```python
# Source: SQLAlchemy 2.0 ORM — select(), with_for_update(), subquery(), scalar_one()
from sqlalchemy import func, select
from sqlalchemy.orm import Session

def _count_active_admins(db: Session) -> int:
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

### Python 3.12 stdlib — SSRF resolve-validate

```python
# Source: Python 3.12 stdlib — socket.getaddrinfo, ipaddress
import ipaddress
import socket
from urllib.parse import urlparse

def _assert_public_host(url: str) -> bool:
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for _family, _type, _proto, _canon, sockaddr in infos:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    return True
```

### respx mock pattern for SSRF tests

```python
# Source: existing tests/services/test_ai_service.py:181-199 — respx.mock + pytest.mark.asyncio
import httpx
import respx
import pytest

@pytest.mark.asyncio
async def test_ssrf_private_ip_blocked() -> None:
    from app.services.ai_service import _verify_buy_url

    # No respx mock needed — socket.getaddrinfo runs before any httpx call.
    # Use a hostname that resolves to a loopback/private address, or mock socket.getaddrinfo.
    # Simplest approach: test with a known-private literal URL.
    # For "localhost" resolving to 127.0.0.1:
    result = await _verify_buy_url("https://localhost/coffee", "Roaster", "Coffee")
    assert result is False
```

For mock-based tests (avoiding DNS resolution in CI), use `unittest.mock.patch("socket.getaddrinfo")`:

```python
from unittest.mock import patch
import socket

@pytest.mark.asyncio
async def test_ssrf_ipv4_mapped_ipv6_blocked() -> None:
    from app.services.ai_service import _verify_buy_url

    # Mock getaddrinfo to return an IPv4-mapped IPv6 metadata address
    mock_result = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:169.254.169.254', 443, 0, 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False
```

[VERIFIED: codebase — existing SSRF tests at `test_ai_service.py:192-216` use `@respx.mock` and `@pytest.mark.asyncio`. The `unittest.mock.patch` approach works alongside respx for pre-network gates.]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PostgreSQL validates `SELECT COUNT(*) FROM (SELECT id ... FOR UPDATE) sub` as legal | B1 pattern | The fix would still fail at runtime; use `text()` raw SQL as fallback |
| A2 | `socket.getaddrinfo` on `localhost` always returns `127.0.0.1` in the Docker container network | S1 test | Test would be a false positive; use explicit mock instead |
| A3 | `slowapi 0.1.9` decorator order: route decorator outermost, limiter next | S4 pitfall | Rate limit would silently not fire; verify against auth router source |

A1 is low-risk: the CONTEXT.md confirmed the bug exists (`ERROR: FOR UPDATE is not allowed with aggregate functions`) and the subquery form is the PostgreSQL-documented workaround.
A3 is verified: [VERIFIED: `app/routers/auth.py` confirmed `@router.post` before `@limiter.limit`].

---

## Open Questions (RESOLVED)

> Both questions are answered inline by their Recommendation lines and implemented by the plans (14-03 chooses the lazy import; 14-01 relies on SQLAlchemy autobegin). Retained for provenance.

1. **B2 — SessionModel import in scheduler.py**
   - What we know: `scheduler.py` does not currently import `SessionModel`. The established lazy-import pattern (used by `run_nightly_backup`) avoids import cycles.
   - What's unclear: Whether a module-level `from app.models.session import Session as SessionModel` is safe (no import cycle) or whether a lazy import inside `run_nightly_session_sweep` is required.
   - Recommendation: Check the import graph — `scheduler.py` already imports from `app.db`, `app.config`, `app.events`. Adding `app.models.session` should be safe at module level. Use lazy import as a fallback if a cycle is detected at test time.

2. **B1 — transaction ownership in sync handlers**
   - What we know: `_count_active_admins(db)` is called inside async handlers that received the `db: Session` via `Depends(get_session)`. The `get_session` dependency opens a session; the handler controls commit/rollback.
   - What's unclear: Whether `with_for_update()` in a subquery correctly acquires the lock within the existing session's transaction, or whether it requires an explicit `BEGIN`.
   - Recommendation: SQLAlchemy 2.0 auto-begins a transaction on first execute — `with_for_update()` will participate in the current transaction. No explicit `BEGIN` needed. [ASSUMED — training knowledge; low risk given SQLAlchemy's autobegin semantics]

---

## Environment Availability

Step 2.6: SKIPPED — this phase is code/config-only changes with no new external dependencies. All tools (Python 3.12, SQLAlchemy 2.0, socket stdlib, ipaddress stdlib, APScheduler 3.x, slowapi) are already present in the running container.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x (installed into container on demand; not baked into production image) |
| Config file | `pytest.ini` or inline (check repo root) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |
| Install command | `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` |

### Phase Requirements → Test Map

| Fix ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| B1 | `_count_active_admins` returns correct count without crashing | unit | `pytest tests/phase_09/test_admin_users.py -k "admin_count or active_admins" -x` | Partially (existing guard tests pass; new multi-admin path missing) |
| B1 | Admin A can demote admin B when 2+ admins exist | integration | `pytest tests/phase_09/test_admin_users.py -k "demote or two_admins" -x` | ❌ Wave 0 gap |
| B1 | Admin A can deactivate admin B when 2+ admins exist | integration | `pytest tests/phase_09/test_admin_users.py -k "deactivate_other_admin" -x` | ❌ Wave 0 gap |
| B1 | Admin A can delete admin B when 2+ admins exist | integration | `pytest tests/phase_09/test_admin_users.py -k "delete_other_admin" -x` | ❌ Wave 0 gap |
| B1 | Existing last-admin guard tests still pass | integration | `pytest tests/phase_09/test_admin_users.py -k "last_admin or single_admin" -x` | ✅ exists |
| S1 | Private IPv4 addresses rejected (10.x, 172.16.x, 192.168.x) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_private" -x` | ❌ Wave 0 gap |
| S1 | Loopback rejected (127.0.0.1, ::1) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_loopback or ssrf_localhost" -x` | ❌ Wave 0 gap |
| S1 | Link-local rejected (169.254.169.254) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_link_local or ssrf_metadata" -x` | ❌ Wave 0 gap |
| S1 | IPv4-mapped IPv6 rejected (::ffff:10.0.0.1) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_ipv4_mapped" -x` | ❌ Wave 0 gap |
| S1 | Public URL still passes validation | unit | `pytest tests/services/test_ai_service.py -k "ssrf_public_allowed" -x` | ❌ Wave 0 gap |
| S1 | `_fetch_page_text` also rejects private hosts | unit | `pytest tests/services/test_ai_service.py -k "fetch_page_ssrf" -x` | ❌ Wave 0 gap |
| S1 | Existing scheme + redirect tests still pass | unit | `pytest tests/services/test_ai_service.py -k "ssrf_redirect or scheme_rejected" -x` | ✅ exists |
| B2 | Expired sessions deleted by sweep job | unit | `pytest tests/test_scheduler.py -k "session_sweep or nightly_session" -x` | ❌ Wave 0 gap |
| B2 | Unexpired sessions not deleted | unit | `pytest tests/test_scheduler.py -k "session_sweep" -x` | ❌ Wave 0 gap |
| B2 | 3 jobs registered (idempotency assertion updated) | unit | `pytest tests/test_scheduler.py::test_idempotent_job_registration -x` | ✅ exists (needs update) |
| S4 | `q` > 100 chars returns empty 200 | unit | `pytest tests/test_search.py -k "long_query or q_length" -x` | ❌ Wave 0 gap |
| S4 | Rate limit 429 after >60/minute | integration | `pytest tests/test_search.py -k "rate_limit" -x` | ❌ Wave 0 gap |
| B4 | Dead code removed (no behavioral test needed) | static | `grep -n "Cannot demote yourself" app/routers/admin/users.py \| wc -l` → must be 1 | n/a |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py -q`
- **Per wave merge:** Full suite: `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

The following test additions are required before or alongside implementation:

- [ ] `tests/phase_09/test_admin_users.py` — add `TestMultiAdminOperations` class (or equivalent) with:
  - `test_demote_other_admin_succeeds` — uses `two_admins` fixture, POSTs update to demote admin2
  - `test_deactivate_other_admin_succeeds` — uses `two_admins` fixture, POSTs deactivate admin2
  - `test_delete_other_admin_succeeds` — uses `two_admins` fixture (admin2 has no brews), POSTs delete admin2
- [ ] `tests/services/test_ai_service.py` — add SSRF private-IP tests:
  - `test_ssrf_private_ipv4_blocked` — `10.0.0.1` via mock patch
  - `test_ssrf_loopback_blocked` — `127.0.0.1` / `localhost`
  - `test_ssrf_link_local_blocked` — `169.254.169.254` via mock patch
  - `test_ssrf_ipv4_mapped_ipv6_blocked` — `::ffff:169.254.169.254` via mock patch
  - `test_ssrf_public_url_allowed` — `example.com` resolving to a public IP
  - `test_fetch_page_ssrf_private_blocked` — same gate on `_fetch_page_text`
- [ ] `tests/test_scheduler.py` — add session sweep tests:
  - `test_session_sweep_deletes_expired` — seeds expired + unexpired rows, calls sweep function, asserts expired gone
  - `test_session_sweep_retains_unexpired` — asserts the unexpired row survived
  - Update `test_idempotent_job_registration` — change `len(jobs) == 2` to `len(jobs) == 3`, add `"nightly_session_sweep"` to expected set
- [ ] `tests/test_search.py` — add search hardening tests:
  - `test_long_query_returns_empty` — GET `/search?q=<101-char string>` → 200, empty body
  - `test_search_rate_limit` — optional; rate limit tests are difficult in-process (slowapi uses in-memory buckets that reset between requests in TestClient); mark as manual-verify if needed

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a |
| V3 Session Management | yes (B2 sweep) | APScheduler DELETE expired rows |
| V4 Access Control | yes (B1 guard) | `_count_active_admins` subquery fix |
| V5 Input Validation | yes (S4 length cap) | 100-char cap in handler |
| V6 Cryptography | no | n/a |
| V7 Error Handling | no | n/a |
| V10 Web Services | yes (S1 SSRF, S4 rate limit) | stdlib ipaddress + slowapi |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF to internal metadata endpoint (169.254.169.254) | Elevation of Privilege | resolve-validate via `socket.getaddrinfo` + `ipaddress` |
| SSRF to private subnet (10.x, 192.168.x) | Information Disclosure | `ipaddress.is_private` |
| SSRF via IPv4-mapped IPv6 bypass | Elevation of Privilege | `IPv6Address.ipv4_mapped` normalization |
| Admin last-admin lockout via concurrent requests | Denial of Service | `FOR UPDATE` row lock on subquery |
| Search endpoint abuse / scraping | Denial of Service | slowapi `60/minute` per IP |

---

## Sources

### Primary (HIGH confidence)

- Codebase direct inspection:
  - `app/routers/admin/users.py:64-68` — current buggy `_count_active_admins`
  - `app/services/ai_service.py:157-202, 1466-1512` — SSRF scaffolding
  - `app/services/scheduler.py:103-127` — `register_jobs` pattern
  - `app/rate_limit.py:40-47` — `LOGIN_LIMIT` / `limiter` pattern
  - `app/routers/search.py:30-49` — `search_results` handler
  - `tests/test_scheduler.py:23-53` — idempotency test to update
  - `tests/phase_09/test_admin_users.py:236-258` — existing guard tests
  - `tests/services/test_ai_service.py:192-216` — existing SSRF tests
  - `app/models/session.py:34-64` — `Session` model with `expires_at`
  - `tests/phase_09/conftest.py:170-198` — `two_admins` / `single_admin` fixtures

- Python 3.12 stdlib:
  - `socket.getaddrinfo` — DNS resolution with address family info
  - `ipaddress.ip_address`, `IPv6Address.ipv4_mapped`, `is_private`, `is_loopback`, `is_link_local`, `is_reserved`

### Secondary (MEDIUM confidence)

- CONTEXT.md — verified-live error message `ERROR: FOR UPDATE is not allowed with aggregate functions` (confirmed against the live Postgres DB per CONTEXT.md provenance)
- ROADMAP.md Phase 14 — success criteria and excluded items

### Tertiary (LOW confidence)

None — all claims are verified against the codebase or stdlib.

---

## Metadata

**Confidence breakdown:**
- B1 fix pattern: HIGH — codebase uses `select(func.count()).select_from(...)` already at line 489 of `users.py`; `with_for_update()` is SQLAlchemy 2.0 standard
- S1 SSRF pattern: HIGH — Python 3.12 stdlib; IPv4-mapped normalization verified against `ipaddress` module semantics
- B2 scheduler pattern: HIGH — exact clone of existing `register_jobs` pattern
- S4 slowapi pattern: HIGH — verified against existing auth router decoration
- Test conventions: HIGH — verified against existing test files

**Research date:** 2026-05-25
**Valid until:** 2026-06-25 (stable stdlib + locked stack; all five fixes are self-contained)
