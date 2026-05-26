# Phase 15: v1.1 Debt Cleanup - Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 6 edit targets + 1 new artifact
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `entrypoint.sh` | config/infra | request-response (process lifecycle) | `entrypoint.sh` itself (current state) | self — capture before-state |
| `Dockerfile` | config/infra | build-time | `Dockerfile` itself (current state) | self — capture before-state |
| `tests/routers/test_auth.py` | test | event-driven (async) | `tests/routers/test_auth.py` itself (current state) | self — minimal edit; capture the interlock pattern to preserve |
| `tests/conftest.py` | test infrastructure | CRUD | `tests/conftest.py` itself (current state) | self — do NOT rewrite; capture as safety-interlock pattern |
| `.github/workflows/ci.yml` | CI config | batch | `.github/workflows/ci.yml` itself (existing pytest step) | self — append new step mirroring existing one |
| `app/templates/base.html` (verify only) | template | request-response | `app/templates/base.html` itself | self — verify/fix-if-broken; no planned rewrite |
| `.planning/phases/15-v1-1-debt-cleanup/15-VERIFICATION.md` | ledger (new) | n/a | `.planning/milestones/v1.1-phases/01-middleware/01-HUMAN-UAT.md` + `01-VERIFICATION.md` | format analog |

---

## Pattern Assignments

### `entrypoint.sh` (DEBT-01 rewrite target)

**Current state** (lines 1-36, full file — read in one pass):

```bash
#!/usr/bin/env bash
# Snobbery container entrypoint (Phase 0 / Plan 00-04).
#
# IMPORTANT: This service MUST run with exactly one uvicorn worker. APScheduler
# (Phase 8) is in-process and module-level AI locks (Phase 7) require single-process.
# A future `--workers 4` would fire every nightly job 4x and bill 4x the AI cost.
# This is reinforced in README.md and app/services/scheduler.py.
#
# This file is location #1 of three places that loudly state the single-worker
# rule. The other two are:
#   (2) app/services/scheduler.py — top-of-file comment block.
#   (3) README.md — deployment section (lands in Plan 00-05).
#
# Anyone trying to add `--workers 4` trips over this note three times before
# they succeed. If you remove or weaken this comment, restore one of the other
# two locations to compensate so the count of warnings stays at three.

set -euo pipefail

# 1) Run migrations. Idempotent (CREATE EXTENSION IF NOT EXISTS;
#    CREATE TABLE against an empty schema). Compose's
#    `depends_on: coffee-snobbery-db: condition: service_healthy`
#    (Plan 00-05) gates this on Postgres being ready.
alembic upgrade head

# 2) Launch uvicorn behind the proxy-headers trust list (FOUND-04 / FOUND-08;
#    PITFALL SH-6). The ${TRUSTED_PROXY_IPS:-127.0.0.1} fallback handles a
#    missing env var gracefully — the var is mandatory in .env.example but
#    we keep a defensive default for local development.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
```

**What changes (D-01 through D-04):**
- The container can no longer start as `app` user — `USER app` in the Dockerfile must be removed (see Dockerfile section below).
- Insert a privilege setup block between `set -euo pipefail` and `alembic upgrade head`:
  ```bash
  _data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
  if [ "$_data_owner" != "1000" ]; then
      chown -R app:app /app/data
  fi
  ```
- Change the final `exec uvicorn ...` to `exec gosu app uvicorn ...` — preserving the exact flags and single-worker comment block verbatim.
- The full warning comment block (lines 3-16) is identity-preserved. `--workers 1` stays unchanged.

**Invariants to preserve:**
- `set -euo pipefail` — must remain.
- `alembic upgrade head` before the privilege drop — runs as root; harmless for Postgres auth.
- `exec` keyword before `gosu` — without it, bash stays as PID 1 and SIGTERM does not reach uvicorn.
- All five uvicorn flags (`--host`, `--port`, `--workers 1`, `--proxy-headers`, `--forwarded-allow-ips`) — unchanged.

---

### `Dockerfile` (DEBT-01: two-line change in runtime stage)

**Current state — runtime stage, lines 66-132:**

Critical lines to change:

**Line 85 (existing apt-get install in runtime stage):**
```dockerfile
    apt-get install -y --no-install-recommends postgresql-client-16; \
```
Add `gosu` to the same install call (do not create a new RUN layer):
```dockerfile
    apt-get install -y --no-install-recommends postgresql-client-16 gosu; \
```

**Line 120-122 (chown + USER app at end of runtime stage):**
```dockerfile
RUN mkdir -p /app/data/photos /app/data/backups && chown -R app:app /app/data

USER app
EXPOSE 8000
```
Remove `USER app` (line 122). Line 120 build-time chown stays — it still seeds ownership for genuinely fresh named volumes. The runtime entrypoint handles the residual root-owned volume case. After the change:
```dockerfile
RUN mkdir -p /app/data/photos /app/data/backups && chown -R app:app /app/data

EXPOSE 8000
```

**Why `USER app` must be removed:** The entrypoint now starts as root to run the conditional chown. If `USER app` is left in the Dockerfile, the entrypoint process starts as UID 1000 and cannot chown — defeating the entire fix.

**The dev stage (lines 141-167) is unaffected** — it already switches `USER root` before its install block and `USER app` afterward. No change needed there.

---

### `tests/routers/test_auth.py` (DEBT-02: minimal fix to `test_setup_concurrent_race`)

**Current state — the target test** (lines 137-183):

```python
@pytest.mark.asyncio
async def test_setup_concurrent_race(async_client) -> None:
    """AUTH-02: two concurrent POST /setups → exactly one 303→/ + one 303→/login."""
    _require_auth_router()

    # Prime the CSRF cookie via an async GET. httpx.AsyncClient stores cookies
    # in its own jar; explicit pass-through into both posts isolates the
    # contract.
    primer = await async_client.get("/setup")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie not primed by GET /setup")
    headers = {"X-CSRF-Token": token}
    cookies = {"csrftoken": token}
    body = {
        "X-CSRF-Token": token,
        "username": "racer",
        "email": "r@example.com",
        "password": "twelve-chars-min-password",
    }

    r1, r2 = await asyncio.gather(
        async_client.post(
            "/setup", data=body, headers=headers, cookies=cookies, follow_redirects=False
        ),
        async_client.post(
            "/setup", data=body, headers=headers, cookies=cookies, follow_redirects=False
        ),
    )

    # One winner (303→/), one loser (303→/login). Both 303 in HTTP —
    # distinguish by Location.
    locations = sorted([r1.headers.get("location", ""), r2.headers.get("location", "")])
    assert locations == ["/", "/login"], (
        f"AUTH-02: expected one 303→/ + one 303→/login, got locations={locations}"
    )

    # Exactly one user row in the DB.
    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1, f"AUTH-02: exactly one user row expected, got {len(users)}"
```

**What changes (D-06):**
Insert a cache-clear guard immediately after `_require_auth_router()`, before the primer GET. This is the only change — the rest of the test body is untouched:

```python
    # Ensure the in-memory settings cache is clean before async_client's lifespan
    # prewarm_cache fires. test_setup_blocked_after_completion updates setup_completed
    # via raw engine.begin() (bypassing set_setting()), so _svc._cache is not
    # invalidated. Without this clear, a stale _cache['setup_completed']='true' from
    # a prior test in the same module causes both concurrent POSTs to see true.
    try:
        import app.services.settings as _svc_mod
        _svc_mod._cache.clear()
    except Exception:
        pass
```

**Existing pattern to mirror** — the module-scoped teardown in `tests/conftest.py` lines 474-481 already does this exact clear for cross-module isolation:
```python
    # Clear the in-memory app_settings cache so test_setup_concurrent_race
    # does not inherit a stale setup_completed=true from a prior module.
    try:
        import app.services.settings as _svc

        _svc._cache.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
```
The in-test fix uses the same try/except import pattern. The import alias (`_svc_mod`) avoids shadowing the local scope.

---

### `tests/conftest.py` (DEBT-02: DO NOT REWRITE — safety-interlock pattern to preserve)

This file is the analog for what the fix must NOT break. Document the safety interlocks so the planner enforces them.

**`fresh_db` fixture (lines 308-385) — safety interlocks:**

```python
@pytest.fixture(autouse=True)
def fresh_db() -> Iterator[None]:
    # ...
    # Safety interlock (defense in depth): NEVER issue the destructive reset
    # against a non-test database.
    try:
        from app.config import settings as _settings
        _active_db = urlparse(
            _settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        ).path.lstrip("/")
    except Exception:
        _active_db = ""
    if "test" not in _active_db.lower():
        yield
        return
```

**`_reset_catalog_tables` fixture (lines 419-481) — safety interlocks + cache clear pattern:**

```python
@pytest.fixture(scope="module", autouse=True)
def _reset_catalog_tables() -> Iterator[None]:
    yield  # teardown-only; setup is a no-op

    # Safety interlock — replicated verbatim from fresh_db.
    if "test" not in _active_db.lower():
        return

    # ... TRUNCATE block ...

    # Clear the in-memory app_settings cache so test_setup_concurrent_race
    # does not inherit a stale setup_completed=true from a prior module.
    try:
        import app.services.settings as _svc
        _svc._cache.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
```

**Rule for DEBT-02 work:** Any change to conftest.py must preserve both the `"test" not in _active_db.lower()` guard and the `_postgres_reachable()` probe. These are non-negotiable safety interlocks per D-05. The only permitted addition is a new fixture or a tweak to an existing fixture's dependency chain — not a rewrite of either `fresh_db` or `_reset_catalog_tables`.

---

### `.github/workflows/ci.yml` (DEBT-02: append double-run guard step)

**Current state — the existing pytest step** (lines 60-69):

```yaml
      - name: Pytest full suite
        env:
          DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
          APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' }}
          APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef0123456789a=' }}
          SNOB_CI: "1"
        run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

**New step to append immediately after** (D-07) — mirrors the existing step's env block exactly, changes only the `name` and `run`:

```yaml
      - name: Pytest isolation double-run
        env:
          DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
          APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' }}
          APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef0123456789a=' }}
          SNOB_CI: "1"
        run: |
          # Second run against the SAME database (no drop/recreate).
          # Teardown residue from run 1 surfaces here as cross-module state pollution.
          python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

**Key constraints:**
- The DB service in the workflow is the same Postgres container — no drop/recreate between runs (D-07 explicitly forbids it).
- `_provision_test_db` is session-scoped and idempotent — it checks existence before creating; run 2 reuses the existing DB.
- Both steps use `SNOB_CI: "1"` — this converts skip-as-green into failures.

---

### `app/templates/base.html` (DEBT-03: verify/fix-if-broken — no planned rewrite)

**Current sign-out form** (lines 161-166, inside `{% if request.state.user %}` block):

```html
            <form method="post" action="/logout">
              <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
              <button type="submit" class="w-full text-left px-4 py-2 text-sm text-espresso-900 dark:text-cream-100 hover:bg-cream-200 dark:hover:bg-espresso-800 min-h-[44px]">
                Sign out
              </button>
            </form>
```

**Auth guard** (line 77 — controls when nav and sign-out are visible):

```html
    {% if request.state.user %}
    {# ── Top horizontal nav (>=768px) ── #}
    <header class="hidden md:flex h-14 ...">
```

**Username display** (line 146 — desktop nav):

```html
          <span>{{ request.state.user.username }}</span>
```

**Mobile sign-out location:** Not in `base.html` — it lives in `app/templates/pages/config_hub.html` (confirmed by `test_config_hub_has_mobile_signout_form` in `tests/test_nav.py`).

**Planner note for DEBT-03:** The automated test suite already verifies sign-out form presence (`test_nav.py` 5 tests, all gated by `_require_nav_wired()`). DEBT-03 is an on-device verification session, not a code rewrite. If a fix IS needed after device verification, the pattern for adding/moving sign-out is the form at lines 161-166 above — copy that CSRF form pattern to wherever sign-out is missing.

---

### `15-VERIFICATION.md` (new ledger artifact)

**Format analog — `01-HUMAN-UAT.md`** (frontmatter + status table per item):

```yaml
---
status: partial
phase: 01-middleware
source: [01-VERIFICATION.md]
started: 2026-05-17T22:50:00Z
updated: 2026-05-17T22:50:00Z
---
```

Followed by sections per test:
```markdown
### 1. [Test name]
expected: [what should happen]
result: [pending | pass | fail | deferred: Phase XX — reason]
```

**Format analog — `01-VERIFICATION.md`** (frontmatter + structured tables):

```yaml
---
phase: 01-middleware
verified: 2026-05-17T00:00:00Z
status: human_needed
score: 8/8 must-haves verified
human_verification:
  - test: "..."
    expected: "..."
    why_human: "..."
---
```

**Recommended structure for `15-VERIFICATION.md`** (as specified by RESEARCH.md):

```markdown
---
phase: 15-v1-1-debt-cleanup
status: in-progress
---

# Phase 15 Closure Ledger

## DEBT-01: Volume Ownership Fix
[automated smoke result]

## DEBT-02: Test Isolation Double-Run
[pytest run 1 output summary]
[pytest run 2 output summary]

## DEBT-03: Nav / Sign-Out On-Device
[per-page result at 375px and ≥768px]

## DEBT-04: Human UAT Closure
### Phase 01 UAT
### Phase 02 UAT
### Phase 07 UAT
### Phase 10 Verification
### Phase 11 UAT

## DEBT-05: human_needed Closure
### Phase 01 / 02 / 07 / 09 / 10 / 11

## D-13: Safe-Area Commit 982c0e6
[on-device result, iOS Safari PWA]
```

Each item's result must be one of: `pass: [evidence]`, `fail: [details]`, or `deferred: Phase XX — [reason]`. No hollow green — per D-11 and D-12.

---

## Shared Patterns

### Safety Interlock (applies to any DEBT-02 work)

**Source:** `tests/conftest.py` lines 351-364 (`fresh_db`) and lines 443-454 (`_reset_catalog_tables`)

**Apply to:** Any new or modified fixture that issues destructive DB operations.

Pattern: always check `"test" not in _active_db.lower()` before executing TRUNCATE or DELETE; always wrap in try/except with a yield-and-return short-circuit.

### Cache-Clear Guard (applies to DEBT-02 test fix and any future async setup test)

**Source:** `tests/conftest.py` lines 474-481 (module teardown) and the new in-test insertion at `tests/routers/test_auth.py` line ~141.

```python
try:
    import app.services.settings as _svc
    _svc._cache.clear()  # type: ignore[attr-defined]
except Exception:
    pass
```

**Apply to:** Any test that uses `async_client` and depends on `setup_completed` being false, if a prior test in the same module uses raw SQL to set `setup_completed='true'`.

### CSRF Form Pattern (applies to DEBT-03 if any sign-out form is missing)

**Source:** `app/templates/base.html` lines 161-166.

```html
<form method="post" action="/logout">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  <button type="submit" ...>Sign out</button>
</form>
```

**Apply to:** Any authenticated page template where sign-out is absent or broken.

### CI Step Env Block (applies to the double-run guard step)

**Source:** `.github/workflows/ci.yml` lines 61-68.

The env block is copied verbatim from the existing "Pytest full suite" step. Both steps must use the same `SNOB_CI: "1"` and identical `APP_SECRET_KEY` / `APP_ENCRYPTION_KEY` references — these are required for the app to start and for skip-to-failure conversion.

---

## No Analog Found

No files in this phase lack an analog. All edit targets are modifications of existing files whose before-state has been captured above. The verification ledger format is covered by the HUMAN-UAT.md + VERIFICATION.md analog from Phase 01.

---

## Metadata

**Analog search scope:** `entrypoint.sh`, `Dockerfile`, `tests/`, `.github/workflows/`, `app/templates/`, `.planning/milestones/v1.1-phases/01-middleware/`
**Files scanned:** 9 (entrypoint.sh, Dockerfile, tests/routers/test_auth.py, tests/conftest.py [lines 300-500], .github/workflows/ci.yml, app/templates/base.html [lines 40-174], .planning/milestones/v1.1-phases/01-middleware/01-VERIFICATION.md, 01-HUMAN-UAT.md, glob of v1.1-phases)
**Pattern extraction date:** 2026-05-25
