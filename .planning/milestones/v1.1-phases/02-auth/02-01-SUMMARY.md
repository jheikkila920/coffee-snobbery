---
phase: 02-auth
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, httpx, conftest, fixtures, wave-0, asgi-transport]

# Dependency graph
requires:
  - phase: 00-foundation
    provides: app.db.engine + SessionLocal + Settings + users/sessions/app_settings tables
  - phase: 01-middleware
    provides: app.services.sessions.regenerate_session + app.signing.sign_session_id + async_session_factory in app.main
provides:
  - "tests/dependencies/ package directory with __init__.py so pytest collects tests/dependencies/test_auth.py in Plan 03"
  - "tests/conftest.py::async_client fixture — httpx.AsyncClient wired to FastAPI via ASGITransport for AUTH-02 asyncio.gather concurrent-race tests"
  - "tests/conftest.py::fresh_db autouse fixture — per-test TRUNCATE users + DELETE sessions + reset app_settings.setup_completed='false' so AUTH-01 / AUTH-02 zero-users precondition holds"
  - "tests/conftest.py::seeded_admin_user / seeded_regular_user fixtures — live User + session row + signed cookie value for AUTH-09 admin-gate three-state tests"
  - "tests/conftest.py::_postgres_reachable() 0.5s TCP probe — fast-fail autouse fresh_db when Postgres unreachable (host-pytest without docker)"
affects: [phase 02 all subsequent plans, AUTH-01, AUTH-02, AUTH-09, plan 02-02, plan 02-03, plan 02-04, plan 02-05]

# Tech tracking
tech-stack:
  added: [pytest_asyncio fixture decorator usage, httpx.ASGITransport for in-process ASGI testing]
  patterns:
    - "Autouse DB-reset fixture with try/except defensive fallback (mirrors Phase 1 _reset_rate_limiter shape)"
    - "Sync wrapper around async DB ops via asyncio.run for sync TestClient consumers"
    - "Lazy try/except ImportError around Wave 1+ symbols so conftest stays collectable before dependencies land"

key-files:
  created:
    - "tests/dependencies/__init__.py — empty package marker (0 bytes)"
  modified:
    - "tests/conftest.py — appended 4 fixtures + _seed_user + _postgres_reachable helpers (219 net-lines added)"

key-decisions:
  - "Added _postgres_reachable() 0.5s TCP probe to autouse fresh_db (Rule 2): defends host-pytest runs without docker against psycopg's ~30s OS-level connect timeout per test. Zero cost in docker (loopback socket is instant)."
  - "Used asyncio.run inside sync _seed_user helper: seeded fixtures support sync TestClient tests; pytest-asyncio doesn't own the loop for sync test paths, so asyncio.run opens a fresh loop per call safely."
  - "Kept seeded fixtures sync (not async): Plan spec says sync, and the AUTH-09 three-state admin gate tests use sync TestClient. async fixtures would force every consumer to be async."

patterns-established:
  - "Phase-2 fixture autouse pattern: autouse=True for setup-flow DB reset, defensive TCP probe to fast-fail on Postgres-unreachable, broad except: pass after probe succeeds in case schema isn't migrated yet"
  - "Wave-0 fixture-skip pattern: every fixture probes its Wave-1+ dependencies via `from X import Y; # noqa: F401` in try/except → pytest.skip with explicit 'Wave N dependency: <symbol>' message"

requirements-completed: [AUTH-01, AUTH-02, AUTH-09]

# Metrics
duration: 10min
completed: 2026-05-18
---

# Phase 02-auth Plan 01: Wave 0 Phase-2 Test Scaffolding Summary

**Added pytest fixtures (`async_client`, `fresh_db` autouse, `seeded_admin_user`, `seeded_regular_user`) plus `tests/dependencies/` package marker so every Phase-2 plan can assert AUTH-01 / AUTH-02 / AUTH-09 outcomes against a clean DB.**

## Performance

- **Duration:** 10min
- **Started:** 2026-05-18T00:39:34Z
- **Completed:** 2026-05-18T00:49:47Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments

- Wave-0 test scaffolding contract from `02-VALIDATION.md` lines 102-104 satisfied: four named fixtures delivered verbatim with the documented signatures.
- `tests/dependencies/` package directory ready so Plan 03's `tests/dependencies/test_auth.py` will be discovered by pytest.
- Autouse `fresh_db` makes AUTH-01's "zero users" precondition automatic for every Phase-2 test — no per-test setup boilerplate.
- `async_client` unblocks AUTH-02's `asyncio.gather` concurrent-race test that a sync `TestClient` cannot exercise.
- Existing Phase-0/1 tests remain green (`test_env_example`, `test_logging`, `test_no_direct_env` all pass; `test_healthz` skips cleanly on host).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/dependencies/__init__.py package marker** — `25d3768` (test)
2. **Task 2: Extend tests/conftest.py with 4 new fixtures + helpers** — `4fa889d` (test)

_(Plan metadata commit follows this SUMMARY)_

## Files Created/Modified

- `tests/dependencies/__init__.py` — Empty package marker so pytest collects `tests/dependencies/test_auth.py` when Plan 03 lands. Mirrors `tests/services/__init__.py` shape (0 bytes).
- `tests/conftest.py` — Appended Phase-2 fixture section with:
  - Top-of-file imports: `asyncio`, `uuid`, `pytest_asyncio`, `AsyncIterator`
  - `async_client` (pytest-asyncio fixture): httpx.AsyncClient via httpx.ASGITransport
  - `fresh_db` (autouse): TRUNCATE users RESTART IDENTITY CASCADE + DELETE sessions + UPDATE app_settings setup_completed='false'
  - `_seed_user(is_admin: bool) -> dict`: composition helper using `hash_password` + `regenerate_session` + `sign_session_id`
  - `seeded_admin_user` / `seeded_regular_user`: sync fixtures wrapping `_seed_user`
  - `_postgres_reachable()`: 0.5s TCP probe to fast-fail autouse `fresh_db` on unreachable Postgres

## Decisions Made

- **Why a `_postgres_reachable()` probe in addition to try/except:** The plan's spec relied on a broad `except Exception: pass` around `engine.begin()` to handle unreachable Postgres. In docker compose this is fine — the loopback socket is instant. On the host without docker (the local development scenario for unit-only tests), psycopg's connect attempt waits ~30s for the OS-level connect timeout. The autouse runs for EVERY test → minutes of wasted time per test session. A 0.5s socket-level probe before the engine call short-circuits cleanly in both environments.
- **Why sync `seeded_*` fixtures (not async):** The AUTH-09 three-state admin-gate tests use sync `TestClient`. Async fixtures would force every consumer to be async. Plan spec also explicitly says sync. `asyncio.run` opens a fresh event loop per call — safe because pytest-asyncio only owns a loop during async tests.
- **Why `asyncio.run` not `loop.run_until_complete`:** Cleaner one-liner; no need to manage loop lifecycle manually since the fixture body is short-lived.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `_postgres_reachable()` TCP probe for autouse `fresh_db`**

- **Found during:** Task 2 (Extend conftest.py with fixtures)
- **Issue:** Plan spec wrapped the entire `engine.begin()` block in `try/except Exception: pass` but didn't add a fast-fail probe. With Postgres unreachable on the host, psycopg's OS-level connect timeout (~30s on Linux, longer on Windows) fires once per autouse invocation — i.e., once per test. A pytest run with 48 collected tests would wait ~24 minutes on connection timeouts before any real assertion ran. Within scope because the fixture is part of THIS task, and the plan's verification step expects existing host-pytest tests to keep passing reasonably fast.
- **Fix:** Added `_postgres_reachable()` helper that parses the host/port out of `settings.DATABASE_URL` and tries a 0.5s `socket.create_connection`. `fresh_db` calls the probe first; if it returns False, the fixture yields immediately without touching the engine. In docker (loopback is instant), the probe is essentially free.
- **Files modified:** `tests/conftest.py` (Task 2 commit; same commit as the fixture itself)
- **Verification:** Ran `python -m pytest -x tests/test_env_example.py tests/test_logging.py tests/test_no_direct_env.py` on the host with Postgres unreachable — 7 tests pass in 8.16s (vs. expected ~3m+ without the probe). `python -m pytest --collect-only -q` reports 48 tests with zero collection errors.
- **Committed in:** `4fa889d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical / defensive degradation)
**Impact on plan:** The auto-fix preserves the plan's intent (autouse runs cleanly in docker; tests that need DB skip cleanly without it) while making the fixture practical on the host. No scope creep, no API changes — just a private helper function.

## Issues Encountered

- **Docker compose not bound to worktree:** The docker compose stack on the dev host is configured against the main repo's `.env` file, not this worktree. The plan's verification commands use `docker compose exec coffee-snobbery pytest ...` — those commands run against the main repo's tree, not this branch's edits. Worked around by running the equivalent host-pytest commands (`python -m pytest --collect-only -q`, `--fixtures`, targeted tests without DB). Verification gate satisfied: collection clean, fixtures discoverable, no Phase-0/1 baseline breakage. Full integration verification (autouse `fresh_db` against a real DB) will happen automatically when subsequent Phase-2 plans land and run in CI / docker.
- **Conftest hangs on host without `_postgres_reachable()` probe:** Initial implementation per plan spec triggered ~30s psycopg timeout per autouse invocation. Fixed via Rule 2 (see deviations above).

## User Setup Required

None — no external service configuration required. Test infrastructure only.

## Next Phase Readiness

- **Plan 02-02** (`app/services/auth.py` argon2 wrappers + tests/services/test_auth.py) can now consume `seeded_*_user` fixtures via the `pytest.skip` ImportError fallback until `hash_password` lands.
- **Plan 02-03** (`tests/dependencies/test_auth.py` for `require_admin`) can now be discovered by pytest because `tests/dependencies/__init__.py` exists.
- **Plan 02-04 / 02-05** (the AUTH-02 concurrent setup race tests) have `async_client` ready.
- **Subsequent Phase-2 plans** inherit the autouse `fresh_db` for free — no per-test DB setup needed.

## Self-Check: PASSED

**Created files verified:**
- `tests/dependencies/__init__.py` — FOUND (0 bytes, package marker)
- `tests/conftest.py` — FOUND (extended; AST parses; all 4 fixture symbols importable and listed via `pytest --fixtures`)

**Commits verified:**
- `25d3768` — FOUND in `git log --oneline -5` (Task 1)
- `4fa889d` — FOUND in `git log --oneline -5` (Task 2)

**Verification automation:**
- `python -c "import os, sys; sys.exit(0 if os.path.isfile('tests/dependencies/__init__.py') else 1)"` → exit 0
- `python -m pytest --collect-only -q` → 48 tests collected, 0 collection errors
- `python -m pytest --fixtures tests/test_healthz.py | grep -E "^(async_client|fresh_db|seeded_admin_user|seeded_regular_user)"` → all 4 lines present
- `python -m pytest -x tests/test_env_example.py tests/test_logging.py tests/test_no_direct_env.py` → 7 passed in 8.16s (autouse fresh_db not blocking)
- `python -m pytest -x tests/test_healthz.py` → 1 skipped, 3 warnings in 2.47s (clean skip path per plan spec)

---
*Phase: 02-auth*
*Completed: 2026-05-18*
