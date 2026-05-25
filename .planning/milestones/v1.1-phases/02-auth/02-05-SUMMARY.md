---
phase: 02-auth
plan: 05
subsystem: services/setup
tags: [auth-01, auth-02, sqlalchemy, asyncsession, for-update, postgres, race-protection, transaction, argon2, wave-2]

# Dependency graph
requires:
  - phase: 00-foundation
    provides: "users table + app_settings.setup_completed='false' seed row + AppSetting / User SQLAlchemy models"
  - phase: 01-middleware
    provides: "async_session_factory in app.main with expire_on_commit=False; analog pattern in app.services.sessions.regenerate_session"
  - phase: 02-auth/02-01
    provides: "fresh_db autouse fixture (DELETE users + sessions; reset setup_completed='false') and async_client fixture for the future Plan 02-07 HTTP race test"
  - phase: 02-auth/02-02
    provides: "app.services.auth.hash_password — consumed inline at INSERT time"
provides:
  - "app/services/setup.py::create_first_admin async coroutine — one transaction, one commit; SELECT app_settings FOR UPDATE → INSERT users → UPDATE app_settings → COMMIT"
  - "Returns User|None — None signals race-lost so the /setup route (Plan 02-07) can redirect to /login per D-01"
  - "Service enforces is_admin=True / is_active=True — no admin flag in the input signature (T-02-05-02 mitigation)"
affects:
  - "Plan 02-07 (/setup POST handler) — consumer; imports create_first_admin and translates None → 303 /login"
  - "AUTH-01 (zero-users happy path) — service slice complete; HTTP slice owed by Plan 02-07"
  - "AUTH-02 (concurrent setup race) — service slice complete (atomic-transaction proof); HTTP slice via asyncio.gather owed by Plan 02-07"
  - "AUTH-04 (argon2id at INSERT) — call site demonstrated"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SQLAlchemy 2.0 AsyncSession + select().with_for_update() for row-level exclusive lock"
    - "Single-commit-atomic transaction across SELECT FOR UPDATE / INSERT / UPDATE — mirrors app.services.sessions.regenerate_session shape"
    - "SQL-statement-capture test pattern via event.listen(sync_engine, 'before_cursor_execute', ...) + event.listen(..., 'commit', ...) to prove atomicity without mocking the engine"
    - "Service-enforced privilege flags (is_admin=True hard-coded inside the service body, no parameter) to prevent T-02-05-02 input tampering"
    - "Hash-inside-lock pattern: argon2 cost paid while holding FOR UPDATE keeps the wasted hash on the race-losing caller, not the winner (RESEARCH D-04 / T-02-05-03 accept)"

key-files:
  created:
    - "app/services/setup.py — 172 lines; one public async function create_first_admin; module/function docstrings document the AUTH-01/AUTH-02/D-04 contract and the hash-inside-lock rationale"
    - "tests/services/test_setup.py — 298 lines; 5 tests covering happy path, atomic-transaction sequence, race-lost branch, argon2id password, and service-enforced admin flags"
  modified: []

key-decisions:
  - "Hash argon2 INSIDE the FOR UPDATE lock (D-04 / RESEARCH §AUTH-02 / T-02-05-03 accept). Verified mid-implementation against the plan body — kept as specified. Wasted-work cost stays on the losing concurrent caller, not the winner. At household scale (≤2 simultaneous setup attempts on first install) the ~100 ms latency is invisible."
  - "Use SQL-event capture (before_cursor_execute + commit listeners on _async_engine.sync_engine) for the atomic-transaction test rather than mocking AsyncSession or wrapping the engine. This proves the actual driver-level SQL is FOR UPDATE-tagged and the commit count is exactly 1 — a behavioural assertion, not a structural one. Pattern reusable for future transaction-shape tests."
  - "Match the SQL-keyword-search test pattern (look for 'FOR UPDATE' + 'USERS' + 'APP_SETTINGS' substrings in the captured SQL) rather than the simpler 'starts with SELECT/INSERT/UPDATE' shape from the plan example. The simpler shape false-matches Postgres' connection-setup SELECTs (e.g. server version). The richer pattern is more reliable across SQLAlchemy 2.0.x patch releases."
  - "Use docker exec (not docker compose exec) for the verification gate because the worktree lacks a .env file. The container is bind-mount-free per session-init notes, so docker cp is the canonical sync path — tests run against the SAME tree the worktree just produced."

patterns-established:
  - "Service-layer race-protection contract: one async coroutine accepts AsyncSession + kwargs; runs SELECT-FOR-UPDATE → mutate → UPDATE-sentinel → commit; returns None on race-lost. Phase 9 admin-deactivate/promote flows can copy this shape verbatim."
  - "Atomic-transaction proof test: SQLAlchemy event listeners capture every executed SQL + every commit, then assert keyword order + commit count. Works across sync and async engines (the async engine exposes .sync_engine for event registration)."

requirements-completed: [AUTH-01, AUTH-02]

# Metrics
duration: 25min
completed: 2026-05-17
---

# Phase 02-auth Plan 05: `create_first_admin` Service Summary

**Shipped the AUTH-02 race-protection seam: a single async coroutine that holds Postgres `SELECT … FOR UPDATE` across INSERT users + UPDATE app_settings inside one committed transaction. Concurrent `/setup` POSTs block on the row lock, observe `setup_completed='true'` after the winner's commit, and exit returning `None` — service slice of AUTH-01 / AUTH-02 complete.**

## Performance

- **Duration:** ~25 minutes (worktree fast-forward to wave anchor + 2 TDD tasks + docker-cp verification + SUMMARY)
- **Tasks:** 2 (TDD RED + TDD GREEN)
- **Files created:** 2 (470 net lines: 172 implementation + 298 tests)
- **Files modified:** 0
- **Tests:** 5 added, 5 passing in docker against Postgres 16 / psycopg 3.3 / SQLAlchemy 2.0.49

## Accomplishments

- AUTH-02 satisfied at the service layer — the `test_for_update_atomic` test proves the SQL stream contains `SELECT … FOR UPDATE` on `app_settings`, followed by `INSERT users`, followed by `UPDATE app_settings`, all within exactly one `commit` event firing. RESEARCH §"SQLAlchemy 2.0 + AsyncSession + `with_for_update()`" canonical pattern landed verbatim with one adaptation (chained `select().where().with_for_update()` collapsed by `ruff format` onto a single line — semantics identical).
- AUTH-01 happy path proved at the service layer (`test_create_first_admin_happy_path`). The full HTTP slice (Pydantic form parsing, 303 redirect to `/`, auto-login session mint) is owed by Plan 02-07.
- Service enforces `is_admin=True` / `is_active=True` by literal (no parameter for either flag in the function signature). `test_create_first_admin_sets_admin_active` is the regression test for T-02-05-02 — a future refactor that accidentally accepts `is_admin` from input would fail this assertion.
- Race-lost branch returns `None` and inserts zero user rows (`test_create_first_admin_race_lost` — pre-flips `app_settings.setup_completed='true'` to simulate a concurrent winner, asserts post-call `len(users) == 0`).
- `hash_password` (Plan 02-02 dependency) consumed inline at INSERT time; `test_create_first_admin_uses_hashed_password` asserts the `$argon2id$v=19$m=65536,t=3,p=4$…` prefix and a round-trip `verify_password()` succeeds — proves AUTH-04's parameter pins reach the persisted column.
- Existing service suite stays green: `tests/services/` reports 9 passed + 1 pre-existing skip (`test_sessions::test_regenerate` blocks on `app.db.async_session_factory` which Phase 7 introduces).

## Task Commits

Each task was committed atomically on the worktree branch:

1. **Task 1 (RED): `tests/services/test_setup.py`** — `00cec18` (test) — 5 failing tests; lazy-import gate makes them skip cleanly until Task 2 ships the module.
2. **Task 2 (GREEN): `app/services/setup.py`** — `c366d01` (feat) — implementation; all 5 tests pass in docker.

_(Final metadata commit follows this SUMMARY — written by the orchestrator after worktree merge.)_

## Files Created/Modified

- **`app/services/setup.py`** (new, 172 lines): Module + function docstrings document the AUTH-01 / AUTH-02 / D-04 / T-02-05-03 contract; one public async function `create_first_admin(db, *, username, email, plaintext_password)`; `__all__` exposes only the public function; private helpers (none — the function is its own atomic unit).
- **`tests/services/test_setup.py`** (new, 298 lines): Module-level `_require_setup_service()` lazy-import gate + `_require_postgres()` reachability probe (mirrors `tests/services/test_auth.py` shape from Plan 02-02). Five `@pytest.mark.asyncio` tests; SQL-event-capture pattern for the atomic-transaction assertion.

## Decisions Made

- **Hash inside the FOR UPDATE lock** — kept exactly as the plan specified. RESEARCH §D-04 / T-02-05-03 accept the ~100 ms latency under contention at household scale. The opposite shape (hash before SELECT) widens the race window because the second caller could hash AND lock first, leaving the first caller with a wasted argon2 cost on a code path that returns None. Documented in the module docstring "Why the argon2 hash is computed INSIDE the FOR UPDATE lock".
- **No `async with db.begin():` wrapper** — the `async_session_factory` from `app/main.py` is the standard SQLAlchemy 2.0 `async_sessionmaker` with `expire_on_commit=False`. The implicit transaction starts on first `execute()` and the explicit `commit()` / `rollback()` closes it. Matches `app/services/sessions.py::regenerate_session` shape (delete + insert + single commit). A `db.begin()` wrapper would nest a SAVEPOINT — unnecessary.
- **SQL-event-capture test (not engine-wrap or session-mock)** — `before_cursor_execute` + `commit` listeners on `_async_engine.sync_engine` capture the real driver-level SQL and the real commit-event fire count. Proves *behavior* against the installed SQLAlchemy + psycopg + Postgres versions, not structure. Listeners are attached AFTER the autouse `fresh_db` cleanup commit so that pre-test setup commits don't pollute the count.
- **Reachability probe in tests** — added `_require_postgres()` alongside `_require_setup_service()` for symmetry with `tests/services/test_auth.py`. The autouse `fresh_db` fixture already short-circuits on unreachable Postgres, but the explicit probe means a host-pytest run with Postgres down yields five clean skips per test file rather than one cryptic engine-creation error inside the first test body.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Atomic-test SQL pattern matching widened from keyword-prefix to substring-pattern**

- **Found during:** Task 1, while drafting `test_for_update_atomic`.
- **Issue:** The plan example matched on the first SQL keyword only (`statement.strip().split()[0].upper()`) and looked for an exact prefix match against `SELECT`/`INSERT`/`UPDATE`. Postgres' connection bootstrap issues SELECTs of its own (server version, type-info caches) that would land in the `relevant` list and shift the indices — the assertion `assert insert_idx > select_idx` would pass for the wrong SELECT.
- **Fix:** Captured the full SQL string and matched on richer substrings: `"FOR UPDATE" in upper and "APP_SETTINGS" in upper` for the FOR UPDATE select; `upper.lstrip().startswith("INSERT") and "USERS" in upper` for the user insert; `upper.lstrip().startswith("UPDATE") and "APP_SETTINGS" in upper` for the settings update. The richer pattern catches the actual emitted SQL and rejects the bootstrap noise.
- **Files modified:** `tests/services/test_setup.py` (`test_for_update_atomic` body).
- **Verification:** Test passes with `assert len(commits) == 1` and the index ordering check.
- **Committed in:** `00cec18` (the test commit).

### Out-of-Scope Notes

- The HTTP-level AUTH-02 concurrent-race test (`async_client.post('/setup', ...)` × 2 via `asyncio.gather`) is explicitly Plan 02-07's responsibility per the plan's `<verification>` section. This plan ships the service-level proof only.
- `tests/services/test_sessions.py::test_regenerate` is permanently skipped on `app.db.async_session_factory` (Phase-7 dependency). Out of scope for this plan; pre-existing condition.

**Total deviations:** 1 auto-fixed (test bug — pattern matching). **Impact:** Strengthens the atomic-transaction proof without changing the implementation.

## Issues Encountered

- **Worktree base mismatch on entry:** The worktree branch started at commit `56d3091` but the orchestrator-supplied anchor was `ef40d72c…` — the wave-2 anchor that included plans 02-01 through 02-04 and 02-06. Resolved with a clean fast-forward merge (`git merge --ff-only ef40d72c…`), bringing in 23 upstream commits including the AsyncSession factory, `fresh_db` fixture, `hash_password` service, and CSRF middleware. No merge conflicts (worktree had nothing on the branch ahead of the anchor — all prior work was upstream).
- **Container is a baked snapshot, not bind-mounted:** Per session init notes, `/app` inside `coffee-snobbery` is its own filesystem snapshot. Required `docker cp` for both the test file and the implementation file before running pytest inside the container. The verification command in the plan (`docker compose exec coffee-snobbery pytest …`) failed initially because (a) the worktree lacks `.env` so docker-compose couldn't resolve env vars, and (b) the container's command path is `python -m pytest`, not bare `pytest`. Worked around by running `docker compose exec -T coffee-snobbery python -m pytest …` from the main repo's working directory (which has `.env`).

## User Setup Required

None. The implementation is complete and verified end-to-end against the running docker stack. Plan 02-07 will consume `create_first_admin` from its `/setup` POST handler.

## Next Phase Readiness

- **Plan 02-07** (`/setup` POST route) is unblocked. Import path: `from app.services.setup import create_first_admin`. Expected wiring: parse Pydantic form schema → call `create_first_admin(db, …)` → if `None`, `RedirectResponse('/login', status_code=303)`; else mint session via `regenerate_session(db, None, new_user.id)` and redirect to `/`. The User row's `id` is populated via the in-function `flush()` so the session-mint call works immediately.
- **Plan 02-07** also owns the HTTP-level concurrent-race test (`asyncio.gather(client.post('/setup', …), client.post('/setup', …))`). The service-level atomic-transaction proof in `test_for_update_atomic` means that HTTP test only needs to assert "exactly one of the two POSTs returns 303 to `/`, the other returns 303 to `/login`" — the SQL-level correctness is already covered here.

## TDD Gate Compliance

Both gates satisfied in commit order:

1. **RED:** `00cec18 test(02-05): add failing tests for create_first_admin service` — 5 tests skipped via lazy-import gate (module doesn't exist).
2. **GREEN:** `c366d01 feat(02-05): create_first_admin service — FOR UPDATE race-protected first-admin transaction` — 5 tests passing in docker.

No REFACTOR commit — the implementation is the canonical pattern from RESEARCH and required no cleanup pass.

## Self-Check: PASSED

**Created files verified:**
- `app/services/setup.py` — FOUND (172 lines; `ruff check` clean; `ruff format --check` clean after the auto-format pass)
- `tests/services/test_setup.py` — FOUND (298 lines; AST parses; pytest collects 5 tests)
- `.planning/phases/02-auth/02-05-SUMMARY.md` — FOUND (this file)

**Commits verified:**
- `00cec18` — FOUND in `git log --oneline -3` (Task 1 RED)
- `c366d01` — FOUND in `git log --oneline -3` (Task 2 GREEN)

**Verification automation:**
- `docker compose exec -T coffee-snobbery python -m pytest -x tests/services/test_setup.py -v` → 5 passed, 1 cache-perm warning, 2.04s.
- `docker compose exec -T coffee-snobbery python -m pytest tests/services/ -v` → 9 passed, 1 pre-existing skip, 3.09s. No regression in `test_auth.py`.
- `python -m ruff check app/services/setup.py` → All checks passed.
- `git diff --diff-filter=D --name-only HEAD~2 HEAD` → empty (no file deletions).

---
*Phase: 02-auth*
*Completed: 2026-05-17*
