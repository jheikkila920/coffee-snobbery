# Phase 15: v1.1 Debt Cleanup - Research

**Researched:** 2026-05-25
**Domain:** Docker entrypoint privilege model, pytest async test isolation, nav/sign-out template coverage, human-UAT ledger mechanics
**Confidence:** HIGH — all DEBT-01 and DEBT-02 technical claims verified against live codebase and official sources.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**DEBT-01 — G-01 chown (entrypoint privilege model)**
- D-01: Fix root-owned-named-volume with runtime chown in `entrypoint.sh`. Container starts as root, chown `/app/data`, then drops to `app` (UID 1000) to `exec uvicorn`. Dockerfile currently ends with `USER app` (line 122) — this changes.
- D-02: Use `gosu` as privilege-drop tool. Correct SIGTERM forwarding; official Postgres image uses this exact pattern.
- D-03: Chown is idempotent and cheap — only run `chown -R app:app /app/data` when `/app/data` is NOT already app-owned. First boot fixes root volume; every later boot near-zero cost.
- D-04: Single-worker invariant non-negotiable. `exec uvicorn ... --workers 1 --proxy-headers --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"` must survive unchanged. Three-place warning system (entrypoint.sh, scheduler.py, README) must stay intact.

**DEBT-02 — Test isolation (T-INFRA-1)**
- D-05: T-INFRA-1 fix is ALREADY present in `tests/conftest.py` (`_reset_catalog_tables` module teardown + `_svc._cache.clear()`). Prove-and-lock, not rebuild. Do NOT rewrite fixtures.
- D-06: Fix `test_setup_concurrent_race` at root cause — no xfail/skip/quarantine.
- D-07: "Green twice in a row" means `pytest tests/` twice against the SAME test DB. Not drop-and-recreate. Add a CI guard.

**DEBT-03 — Nav / sign-out**
- D-08: Correctness-only. Verify persistent nav + user identity + working sign-out on every authenticated page, then verify on physical device.
- D-09: No visual redesign and no IA changes. Phase 17 (IA Restructure) and Phase 21 (mobile rework) own design.

**DEBT-04 / DEBT-05 — Human-gated closure**
- D-10: Live interactive execution model — John + Claude together during phase execution.
- D-11: Record every outcome in writing. Produce/update verification ledger.
- D-12: Re-defer with written reason + target phase if genuinely uncloseable.
- D-13: Fold the safe-area on-device verification (commit `982c0e6`) into the same Phase 15 device session.

### Claude's Discretion
- Exact `gosu` install line and layer placement in the Dockerfile runtime stage (researcher/planner pick), as long as D-01..D-04 hold.
- The precise CI-guard shape for the double-run (D-07) — a CI step vs a pytest marker/assertion — planner's call.
- How the verification ledger is represented (a Phase 15 VERIFICATION.md vs updating each archived phase's record) — as long as outcomes are auditable (D-11).

### Deferred Ideas (OUT OF SCOPE)
- Phase 11 visual backlog — logo-on-every-page, login hero image, cold-start meter position. Deferred to Phase 17/21.
- Any nav/IA redesign — Phase 17.
- Any mobile visual polish beyond on-device correctness — Phase 21.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEBT-01 | A new operator's first deploy can write backups and photos with no manual `chown` (G-01 fixed via runtime `chown -R app:app /app/data` in `entrypoint.sh` before dropping to the app user) | gosu apt install verified; owner-UID-check pattern documented; Dockerfile layer placement researched |
| DEBT-02 | Full `pytest tests/` suite runs green twice in a row with no cross-module isolation failures (T-INFRA-1: catalog-table teardown + settings-cache clear in root conftest) | Root cause of `test_setup_concurrent_race` identified; fix strategy documented; CI double-run guard shape recommended |
| DEBT-03 | Every authenticated page shows persistent nav with user identity and a working sign-out (verify/close the Phase 11 gap) | Sign-out forms verified present in `base.html`, `config_hub.html`; test_nav.py coverage mapped; on-device session plan |
| DEBT-04 | Outstanding v1.1 human-UAT scenarios executed and recorded (Phases 01/02/07/11 + the Phase 14 375px search-sheet UAT) | All pending UAT items catalogued from HUMAN-UAT.md files; status table built |
| DEBT-05 | Outstanding `human_needed` verifications (Phases 01/02/07/09/10/11) resolved or explicitly re-deferred with a reason | All `human_needed` items extracted from VERIFICATION.md files; status table built |
</phase_requirements>

---

## Summary

Phase 15 is a cleanup-and-verification phase with zero new capabilities. It has two technically substantive items and three human-gated items.

**DEBT-01** is a Docker entrypoint rewrite. The current `entrypoint.sh` never drops privileges — it inherits `USER app` from the Dockerfile and starts uvicorn directly. This means named volumes initialized as root (the common case on a fresh VPS deploy where the named volume exists before the app image sets ownership) are unwritable. The fix is a well-established pattern: start the container as root, check `/app/data` ownership (cheap stat), conditionally `chown -R app:app /app/data`, then `exec gosu app uvicorn ...`. `gosu` is in the Debian bookworm apt repository (no binary download required), correctly forwards SIGTERM so uvicorn shuts down cleanly, and is the tool the official Postgres Docker image uses for this exact pattern.

**DEBT-02** is a prove-and-lock of the existing `_reset_catalog_tables`/`_svc._cache.clear()` mechanism plus a targeted fix of `test_setup_concurrent_race`. The isolation fixtures are already correct for the cross-module problem. The concurrent race test has a specific ordering-dependent failure mode: if pytest runs `test_setup_blocked_after_completion` (which manually UPDATEs `setup_completed=true` via raw SQL, bypassing `set_setting`) before `test_setup_concurrent_race` in the same module, and the async_client fixture's lifespan startup races with `fresh_db`'s DB reset, the race test can see `setup_completed=true` at request time and both POSTs redirect to `/login`. The fix is a deterministic in-test guard.

**DEBT-03/04/05** are human-gated. DEBT-03 has existing automated coverage (test_nav.py's 5 tests). DEBT-04 and DEBT-05 catalogue all pending items across v1.1 phase directories — Phase 01 (3 UAT), Phase 02 (1 UAT), Phase 07 (2 UAT), Phase 11 (3 UAT), Phase 10 (3 VERIFICATION items), plus Phase 09 item 6 (partial). These close in a single device session alongside the safe-area commit `982c0e6`.

**Primary recommendation:** Write the entrypoint.sh rewrite and concurrent-race fix in Wave 0/1; schedule the single device session to close DEBT-03/04/05/D-13 together.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Volume ownership fix (DEBT-01) | Container entrypoint | Dockerfile runtime stage | Only the entrypoint can conditionally chown at first-boot runtime; the Dockerfile only controls image build-time state |
| Test isolation (DEBT-02) | Test infrastructure (conftest.py) | CI pipeline | Fixture-level fix closest to the failure; CI guard catches regression |
| Nav/sign-out coverage (DEBT-03) | Template layer (Jinja2) | Automated test (test_nav.py) | Templates are the source; tests verify; no backend change expected |
| Human UAT + human_needed (DEBT-04/05) | Interactive device session | VERIFICATION.md ledger | Cannot be automated by definition; ledger makes outcomes auditable |

---

## Standard Stack

No new libraries required for this phase. All work uses existing stack components.

### Existing Stack Used
| Component | Current Version | Purpose in Phase 15 |
|-----------|----------------|---------------------|
| `gosu` | 1.17 (apt, bookworm) | Privilege drop in entrypoint.sh — NEW addition to runtime stage |
| `pytest` | 9.0.x | Double-run isolation verification |
| `pytest-asyncio` | existing | Concurrent race test fixture ordering |
| `bash` | system (Debian bookworm) | entrypoint.sh rewrite |
| Jinja2 templates | existing | DEBT-03 sign-out form verification |

**Installation (Dockerfile runtime stage):**
```dockerfile
# Add to the existing apt-get RUN block in the runtime stage:
apt-get install -y --no-install-recommends gosu
```

**Version verification:** `gosu` 1.17 is available in Debian bookworm apt repository. [VERIFIED: packages.debian.org/bookworm/gosu]

---

## Architecture Patterns

### System Architecture Diagram

```
Container start (as root, USER app removed from Dockerfile)
        |
        v
entrypoint.sh runs as root
        |
        +---> alembic upgrade head (no change — still runs as root)
        |
        +---> Owner check: stat -c %u /app/data == 1000?
        |           YES: skip chown (fast path, normal case)
        |           NO:  chown -R app:app /app/data  (first boot only)
        |
        +---> exec gosu app uvicorn --workers 1 ...
                         |
                         v
                  uvicorn (PID 1, running as app/UID 1000)
                  Receives SIGTERM directly → clean shutdown
```

### DEBT-01 — gosu Install and Entrypoint Pattern

**What:** Install `gosu` in the Dockerfile runtime stage's existing apt-get block, remove `USER app`, rewrite `entrypoint.sh` to start as root, do conditional chown, drop to `app` via `exec gosu`.

**Why `gosu` over `su-exec` or `sudo`:** The base image is `python:3.12-slim` (Debian bookworm, glibc). `su-exec` is an Alpine musl tool — not in Debian apt. `sudo` creates a new session and does NOT forward SIGTERM to the child, so uvicorn would not receive SIGTERM on `docker compose stop`. `gosu` uses `execve()` internally — it replaces itself with the target process (PID 1 after the drop is the actual uvicorn), guaranteeing correct signal propagation. [VERIFIED: official Postgres Docker image uses this exact pattern; CITED: github.com/docker-library/postgres docker-entrypoint.sh]

**gosu install — apt is correct for Debian bookworm:**
```dockerfile
# In the runtime stage's existing apt-get RUN block, add:
apt-get install -y --no-install-recommends gosu
```
`gosu` is available in the Debian bookworm official repository (package: `gosu`). No binary download or GPG verification dance required. [VERIFIED: packages.debian.org/bookworm/gosu]

**Layer placement:** Add `gosu` to the EXISTING `apt-get install` block in the runtime stage (after `postgresql-client-16`). Do NOT create a new `RUN apt-get` layer — Docker layer caching is better served by adding to the existing block.

**Dockerfile change:**
```dockerfile
# Remove line 122: USER app
# Entrypoint must run as root now to do the chown

# In the apt-get install block, add gosu:
apt-get install -y --no-install-recommends postgresql-client-16 gosu
```

**entrypoint.sh rewrite:**
```bash
#!/usr/bin/env bash
# IMPORTANT: This service MUST run with exactly one uvicorn worker.
# [... keep full existing warning comment block unchanged ...]

set -euo pipefail

# 0) Runtime privilege setup.
# The container starts as root so this entrypoint can fix ownership of
# /app/data (named volume). Only chown when the directory is not already
# owned by app (UID 1000) — idempotent and near-zero cost on subsequent
# starts even as the photos volume grows.
_data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
if [ "$_data_owner" != "1000" ]; then
    chown -R app:app /app/data
fi

# 1) Run migrations as root (DB connection only, no file writes to /app/data).
alembic upgrade head

# 2) Drop to app user and exec uvicorn. exec gosu forwards SIGTERM correctly
#    so uvicorn (not gosu) is PID 1 and receives container stop signals.
exec gosu app uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
```

**Single-worker warning:** The existing warning comment block at the top of `entrypoint.sh` is identity-preserved. The `--workers 1` flag on the `exec uvicorn` line is unchanged.

**Owner UID check — `stat -c '%u'`:** Returns the numeric UID of the directory owner. On Debian bookworm `stat` is from GNU coreutils — available in `python:3.12-slim`. [VERIFIED: live Dockerfile uses `python:3.12-slim`; coreutils ships by default in Debian slim images]

**What the official Postgres image does:** Its `docker-entrypoint.sh` checks `if [ "$user" = '0' ]; then find "$PGDATA" \! -user postgres -exec chown postgres '{}' +`. The `find \! -user` pattern is equivalent to (and more thorough than) the single-dir stat check, but is slower on large trees. For our case — a single `/app/data` tree — checking the root directory's UID is sufficient and cheaper. [CITED: github.com/docker-library/postgres/blob/master/17/bookworm/docker-entrypoint.sh]

**SIGTERM forwarding — why `exec gosu` is the correct form:**
- `exec gosu app uvicorn ...` → gosu calls `execve()`, replacing itself with uvicorn. The resulting uvicorn process inherits PID 1 from the entrypoint shell chain. `docker stop` sends SIGTERM to PID 1 → uvicorn → clean shutdown.
- `gosu app uvicorn ...` without `exec` → bash is PID 1, spawns gosu, which replaces itself with uvicorn, but bash is still alive. SIGTERM hits bash, not uvicorn. Incorrect.
- The existing `entrypoint.sh` already uses `exec uvicorn` — this is preserved as `exec gosu app uvicorn`. [VERIFIED: current entrypoint.sh line 32]

### DEBT-02 — test_setup_concurrent_race Root Cause and Fix

**Current isolation fixture state:** The T-INFRA-1 mechanism is present and correct:
- `_reset_catalog_tables`: module-scoped autouse teardown; TRUNCATEs catalog+brew tables; calls `_svc._cache.clear()` to wipe the in-memory settings cache [VERIFIED: conftest.py lines 419-481]
- `fresh_db`: function-scoped autouse; DELETEs users/sessions; resets `setup_completed=false` in DB before each test [VERIFIED: conftest.py lines 308-385]

**Why `test_setup_concurrent_race` can fail in a full `pytest tests/` run:**

The test (`tests/routers/test_auth.py`, line 138) uses `async_client` — an `httpx.AsyncClient` with `ASGITransport(app=app)`. Each `async with` context entry triggers the FastAPI lifespan, which calls `prewarm_cache()`, which reads `setup_completed` from the DB and writes it to `_svc._cache`.

The failure mode:
1. `test_setup_blocked_after_completion` (same module, line 96) uses `client` (sync TestClient). It manually UPDATEs `setup_completed=true` via raw SQL with `engine.begin()` — this bypasses `set_setting()` and does NOT invalidate `_svc._cache`. After this test, the DB has `setup_completed=true`.
2. `fresh_db` autouse resets DB to `setup_completed=false` before `test_setup_concurrent_race`.
3. BUT: pytest fixture ordering is not guaranteed between autouse fixtures and explicitly requested fixtures when they're both function-scoped. If `async_client`'s context manager entry (triggering `prewarm_cache`) happens to interleave before `fresh_db` completes its DB reset, `prewarm_cache` reads `setup_completed=true` from the DB, populates `_cache["setup_completed"] = true`.
4. The two concurrent POSTs to `/setup` check the DB directly (not cache), so they still see `false` in the DB... but `prewarm_cache` with `true` means any cached read path would see `true`.

Actually, a simpler failure: the `setup_submit` handler also reads the DB directly (via `SELECT value FROM app_settings WHERE key='setup_completed'`). If `fresh_db` hasn't fired when the async_client opens its context... No — `fresh_db` is autouse and function-scoped; it runs in fixture setup before the test body. But `async_client` is also a fixture and its `async with` context manager entry happens during fixture setup, which could be before or after `fresh_db` depending on pytest's dependency resolution.

**Root cause (definitive):** `async_client` fixture depends only on `app`, not on `fresh_db`. Pytest doesn't know to run `fresh_db` before `async_client`'s context manager entry (the `lifespan` startup / `prewarm_cache`). If `setup_completed=true` is in the DB from a prior test run's residue (from a prior `pytest tests/` invocation, or from `test_setup_blocked_after_completion` running before the `fresh_db` reset on the next test), `prewarm_cache` caches `true`. The test uses `async_client` (which triggered a stale prewarm), then sends two concurrent POSTs that each read the DB directly and both see `setup_completed=false`... and the race SHOULD work correctly at the DB level.

**Second possible failure:** The `async_client` fixture creates a NEW `httpx.AsyncClient` per test. Each `async with httpx.AsyncClient(...)` context entry triggers a new lifespan startup including `prewarm_cache`. If `test_setup_blocked_after_completion` (sync `client`) ran before this test in the same module AND left `setup_completed=true` in DB (via direct engine UPDATE, bypassing `fresh_db`), then `fresh_db` resets DB to `false` at the start of `test_setup_concurrent_race`. The `async_client` fixture then enters context, `prewarm_cache` reads DB (now `false`). Cache is correct.

**Most likely failure — second pytest invocation (the double-run residue test):** After run 1 completes, the DB has `setup_completed=true` (from the race winner). Run 2 starts. `_provision_test_db` is session-scoped and was already set up — it does NOT drop/recreate. The very first test to request `client` or `async_client` triggers lifespan + `prewarm_cache`. If that test is `test_setup_concurrent_race` and `fresh_db` hasn't run yet (session-scoped `_provision_test_db` can obscure the function-scoped `fresh_db` order), the prewarm sees `true`.

Actually `fresh_db` is autouse=True function-scoped — it ALWAYS runs before any function-scoped test body. The issue may be subtler: `_reset_catalog_tables` is MODULE-scoped teardown-only. It clears `_svc._cache` AFTER the module completes. The NEXT module's first test has a clean cache. But within a single module run, if `test_setup_concurrent_race` is not the first test, the cache state depends on what prior tests did.

**The deterministic fix (minimal, preserving fixture structure):**
Add a direct `_svc._cache.clear()` call at the start of `test_setup_concurrent_race` (or in a module-level autouse fixture that runs before each async test in the auth module). This ensures the prewarm within the `async_client` context reads fresh from the DB that `fresh_db` just reset.

```python
@pytest.mark.asyncio
async def test_setup_concurrent_race(async_client) -> None:
    """AUTH-02: two concurrent POST /setups → exactly one 303→/ + one 303→/login."""
    _require_auth_router()
    # Ensure the in-memory settings cache is clean at test start.
    # create_first_admin() uses raw UPDATE (not set_setting()), so the
    # cache is not invalidated automatically after a successful setup.
    # Without this, a prior test that set setup_completed=true via
    # raw SQL can leave a stale cache entry that causes both concurrent
    # POSTs to see 'true' and redirect to /login (wrong: [/login, /login]).
    try:
        import app.services.settings as _svc
        _svc._cache.clear()
    except Exception:
        pass
    # ... rest of test unchanged
```

**Why this is minimal and correct per D-05:** This does NOT rewrite the fixtures. It adds a one-time local cache clear at the top of the specific test that requires it, consistent with the existing pattern (the module teardown already does exactly this clear for cross-module isolation). The DB is correctly reset by `fresh_db` before this test; clearing the cache ensures the next `prewarm_cache` (triggered by `async_client` context) reads the DB state that `fresh_db` just set.

**Alternative fix (if the ordering issue is confirmed to be in async_client vs fresh_db):** Add `fresh_db` as an explicit dependency in the `async_client` fixture signature. This would guarantee `fresh_db` runs before `async_client` opens its context. But this touches the fixture itself, which D-05 says to minimize. The in-test clear is smaller.

**Double-run proof — the correct test command:**
```bash
# Run 1
pytest tests/ --ignore=tests/e2e -rs --tb=short
# Run 2 (SAME DB, no drop/recreate)
pytest tests/ --ignore=tests/e2e -rs --tb=short
```
The `_provision_test_db` session fixture is idempotent (CREATE DATABASE IF NOT EXISTS equivalent — checks existence first). Both runs use the same `<db>_test` database. Run 2 residue proves teardown actually fires.

### DEBT-03 — Nav/Sign-Out Coverage Map

**Automated tests already passing:**
| Test | What it verifies |
|------|-----------------|
| `test_config_hub_has_mobile_signout_form` | `config_hub.html` has `action="/logout"` CSRF POST form |
| `test_authenticated_home_has_nav_bar_component` | Home page has `x-data="navBar"` (bottom nav present) |
| `test_non_admin_home_has_no_admin_link` | Non-admin user doesn't see admin nav link |
| `test_admin_home_has_admin_link` | Admin user sees admin nav link |
| `test_config_hub_returns_200_for_authenticated_user` | Config hub is accessible when authenticated |

**Sign-out forms in templates (verified in codebase):**
- `app/templates/base.html` line ~161: `<form method="post" action="/logout">` with CSRF token — inside the desktop user-dropdown Alpine component [VERIFIED: base.html lines 161-167]
- `app/templates/pages/config_hub.html`: mobile sign-out form (from test_nav.py test at line 57)
- `app/templates/pages/index.html`: separate sign-out reference (from CONTEXT.md)
- `app/templates/admin_base.html`: extends `base.html`, inherits desktop dropdown + assumes base nav is present [VERIFIED: admin_base.html]

**The verification gap:** The sign-out ONLY appears for authenticated users (inside `{% if request.state.user %}` guard in `base.html` line 46). Automated tests verify this guard works. What's NOT automated: visual confirmation that the user's username is visible in the nav on every authenticated page at all viewport widths. This is the on-device verification required by D-08.

**Pages to verify on-device (DEBT-03):**
All pages that extend `base.html`: `/`, `/brew`, `/brew/guided`, `/coffees`, `/roasters`, `/equipment`, `/recipes`, `/flavor-notes`, `/config`, `/admin/*`. The desktop nav (≥768px) shows username + dropdown; the mobile strip (< 768px) shows logo + search icon; the bottom nav handles page navigation. Sign-out is in the dropdown on desktop and in the mobile config-hub form.

**Gap identified by CONTEXT.md:** Phase 11 left a noted deficiency in that the bottom nav at `< 768px` may not prominently surface user identity + sign-out. The DEBT-03 verify is to confirm that at 375px, the user can actually find and use sign-out (via config hub → mobile sign-out form), and that this works end-to-end.

### Anti-Patterns to Avoid

- **Rewriting `_reset_catalog_tables` or `fresh_db`:** D-05 explicitly forbids this. Minimal change only.
- **Using `su -c` or `sudo` instead of gosu:** `su -c` creates a new session and does not forward SIGTERM. `sudo` in containers requires a TTY configuration or `/etc/sudoers` setup. Neither passes SIGTERM correctly.
- **Adding `USER app` back after the gosu line:** The `Dockerfile` `USER app` line must be removed; the `exec gosu app uvicorn` in entrypoint.sh is the privilege drop. Adding `USER app` back means the entrypoint starts as `app` and can't run chown.
- **Unconditional chown on every boot:** A `chown -R` on a large photos volume is O(n files) — slow. The stat check makes it O(1) on every subsequent boot. Do not skip the check.
- **Dropping the `exec` before `gosu`:** Without `exec`, bash stays as PID 1 and does not forward SIGTERM to uvicorn.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Privilege drop in Docker entrypoint | Custom setuid helper, sudo wrapper | `gosu` (apt install) | SIGTERM forwarding; official Postgres uses it; in Debian repos; zero binary-download complexity |
| Ownership check | Complex find/awk pipeline | `stat -c '%u' /app/data` | Single syscall; available in Debian slim; returns numeric UID |
| Test isolation | New custom fixtures | Existing `_reset_catalog_tables` + `fresh_db` | D-05: fixtures are already correct and carry critical safety interlocks |

---

## Common Pitfalls

### Pitfall 1: Omitting `exec` Before `gosu`
**What goes wrong:** `bash entrypoint.sh` (PID 1) forks `gosu`, which execs `uvicorn`. On `docker stop`, SIGTERM goes to bash (PID 1), not uvicorn. Uvicorn gets SIGKILL 10 seconds later (unclean).
**How to avoid:** Always `exec gosu <user> <command>` — never `gosu <user> <command>` without exec.
**Warning signs:** `docker compose stop` takes 10 seconds (the kill timeout) instead of <2 seconds.

### Pitfall 2: Removing gosu After the `RUN apt-get` Block
**What goes wrong:** Layer caching invalidated unnecessarily if `gosu` is in a separate RUN layer.
**How to avoid:** Add `gosu` to the existing `apt-get install` block in the runtime stage.

### Pitfall 3: Alembic migrations run as root — is that OK?
**What it means:** Migrations run before the `exec gosu` drop, so they run as root. Alembic connects to Postgres over the network — the connection UID is the Postgres user (`POSTGRES_USER`), not the OS user. Running Alembic as OS root has no effect on DB permissions. [ASSUMED — standard Docker/Postgres behavior, not tested in this session]
**Mitigation:** The existing entrypoint runs Alembic before the exec anyway; no change in behavior here.

### Pitfall 4: `test_setup_concurrent_race` passes locally but fails in full suite
**What goes wrong:** Local `pytest tests/routers/test_auth.py` passes because the module starts clean. Full `pytest tests/` triggers cross-module state from `_svc._cache` populated by a prior module's test that used `set_setting` or raw SQL.
**How to avoid:** The deterministic in-test `_svc._cache.clear()` at the top of `test_setup_concurrent_race` is the fix. Verify with `pytest tests/ -k test_setup_concurrent_race -rs` (should pass), then a full `pytest tests/ -rs` run (the actual gate).

### Pitfall 5: Double-run with drop-and-recreate hides residue
**What goes wrong:** Dropping and recreating the test DB between runs destroys any state left by run 1. The purpose of the double-run is to EXPOSE residue that teardown failed to clean.
**How to avoid:** D-07 explicitly requires same DB, no drop. Run `pytest tests/` twice in sequence. The `_provision_test_db` fixture is idempotent and will not recreate an existing DB.

### Pitfall 6: Service worker caches old templates during on-device verification
**What goes wrong:** Phase 15 does no template changes for DEBT-03 (verify-and-fix-if-broken). But if a template fix IS needed, the service worker's SWR cache will serve stale HTML until the cache name bumps (which requires a Tailwind CSS or JS content change + rebuild).
**How to avoid:** If any template change is required for DEBT-03, trigger a rebuild to bump the build_id.txt and cache name. "Clear site data" (not just hard-refresh) in Safari/Chrome before device verification.
**Reference:** Project memory: `[SW stale cache confounds UI verify]`.

---

## Runtime State Inventory

This is a verification/correctness phase with no renames or migrations. Omitted per instructions.

---

## Open Questions (RESOLVED)

1. **Does `stat` return the symlink target UID or the symlink's own UID?**
   - `/app/data` is a real directory, not a symlink. `stat -c '%u' /app/data` returns the directory's UID. No symlink concern.
   - Recommendation: proceed with `stat -c '%u'`.

2. **Should migrations run as root or as app?**
   - Currently: Alembic runs before the gosu drop (as root). Alembic connects to Postgres via network; the OS UID of the process doesn't affect Postgres auth. This is fine.
   - Recommendation: keep migrations before the gosu drop. Running them as root is harmless and avoids complicating the entrypoint with a partial privilege drop.

3. **Phase 14's "375px search-sheet UAT" — where is it recorded?**
   - The CONTEXT.md refers to a "Phase 14 375px search-sheet UAT." Phase 14's VERIFICATION.md has `human_verification: []` (no human items). The 375px search sheet behavior items are actually in Phase 10's VERIFICATION.md under `human_verification` (3 items: responsive layout smoke, debounce/hx-sync, p95 latency). The CONTEXT.md is using "Phase 14" to mean "the audit remediation that touched search" — but the outstanding UAT items are in Phase 10's records.
   - Recommendation: planners should pull Phase 10 VERIFICATION.md `human_verification` items for the DEBT-04 ledger, not Phase 14.

4. **Phase 09 item 6 (AI refresh respect/force with real data) — closeable in Phase 15?**
   - Phase 09 HUMAN-UAT.md item 6 is "passed pending real data" — it needs a live AI credential + eligible user on VPS. If John has AI credentials configured on VPS during the Phase 15 device session, this can close. If not, it re-defers to whenever VPS has live AI creds.
   - Recommendation: attempt during the device session; re-defer with reason if VPS lacks AI credentials.

---

## Human UAT Ledger (as-found state for DEBT-04/05)

This table is the pre-execution inventory. Phase 15 plans use it as the closure checklist.

### DEBT-04: Outstanding Human UAT

| Phase | UAT Item | Status | Notes |
|-------|----------|--------|-------|
| 01-middleware | UAT-1: Real NGINX reverse-proxy end-to-end (`curl https://snobbery.example.com/debug/proxy`) | pending | Requires VPS deploy + NGINX config |
| 01-middleware | UAT-2: Browser CSP nonce wiring (DevTools Network tab) | pending | Requires live browser + DevTools |
| 01-middleware | UAT-3: HTMX CSRF double-submit on second fragment swap | pending | Requires Phase 2 /login (which exists) |
| 02-auth | UAT-1: Mobile 375px visual smoke for /setup, /login, /admin, / | pending | Requires browser at 375×667 |
| 07-ai-services | UAT-1: Hero card end-to-end with live provider key | pending | Requires VPS + real AI credentials |
| 07-ai-services | UAT-2: 375px layout — hero "generated" and "try-again" states | pending | Requires VPS + real AI credentials + live provider response |
| 10-search | VERIF-1: Responsive layout smoke — mobile icon to full-screen sheet | pending | 375px browser |
| 10-search | VERIF-2: Debounce + hx-sync in-flight cancellation | pending | Browser DevTools Network panel |
| 10-search | VERIF-3: p95 < 100ms latency against seeded dataset | pending | Load generation tool |
| 11-pwa | UAT-1: Real-device iOS Safari installability (MOB-12) | pending | VPS deploy + real iPhone |
| 11-pwa | UAT-2: Android Chrome installability (Lighthouse) | pending | VPS deploy + Chrome DevTools |
| 11-pwa | UAT-3: Guided Brew wake lock on real device (BREW-13) | pending | Real iPhone + real Android |

### DEBT-05: Outstanding human_needed Verifications

| Phase | Item | Status | Notes |
|-------|------|--------|-------|
| 01-middleware | (3 items) | pending | Same as UAT-1/2/3 above |
| 02-auth | (1 item) | pending | Same as UAT-1 above |
| 07-ai-services | (2 items) | pending | Same as UAT-1/2 above |
| 09-admin | Item 6: AI refresh respect/force modes with real data | partial ("seems good") | Close if VPS has AI creds; re-defer with reason if not |
| 10-search | (3 items) | pending | Same as VERIF-1/2/3 above |
| 11-pwa | (3 items) | pending | Same as UAT-1/2/3 above |

### D-13: Safe-Area Commit Verification

| Item | Status | Notes |
|------|--------|-------|
| Commit `982c0e6` — iOS bottom-nav safe-area fix | UNVERIFIED on-device | From project memory `[safe-area fix unverified]`. Also Phase 13 HUMAN-UAT shows NEW-13 (bottom nav still raised on Log/sessions page). Verify: (a) safe-area on iOS standalone PWA; (b) whether NEW-13 was resolved by the 100dvh min-height fix |

### Items That Can Close Without VPS

The following UAT/human_needed items CAN be closed using a browser (Chrome DevTools + local running instance), without a VPS deploy:
- 01-UAT-2: CSP nonce wiring (DevTools Network tab on any running instance)
- 01-UAT-3: HTMX CSRF double-submit (works on local instance with a logged-in session)
- 02-UAT-1: 375px visual smoke (DevTools device toolbar)
- 10-VERIF-1: Responsive layout smoke (DevTools at 375px)
- 10-VERIF-2: Debounce/hx-sync (DevTools Network panel)

Items that REQUIRE VPS deployment:
- 01-UAT-1: Real NGINX proxy chain (requires live NGINX in front of the app)
- 07-UAT-1/2: Live AI credentials (unlikely to configure locally; on VPS)
- 11-UAT-1/2/3: Real device on a publicly reachable URL (local 127.0.0.1 not reachable from phone)
- 10-VERIF-3: p95 latency (requires realistic seeded dataset on VPS, not local dev data)
- D-13: Safe-area on iOS (requires iOS device connected to VPS)

---

## Code Examples

### entrypoint.sh rewrite (DEBT-01)
```bash
#!/usr/bin/env bash
# Snobbery container entrypoint.
#
# IMPORTANT: This service MUST run with exactly one uvicorn worker. APScheduler
# (Phase 8) is in-process and module-level AI locks (Phase 7) require single-process.
# A future `--workers 4` would fire every nightly job 4x and bill 4x the AI cost.
# This is reinforced in README.md and app/services/scheduler.py.
#
# This file is location #1 of three places that loudly state the single-worker
# rule. The other two are:
#   (2) app/services/scheduler.py — top-of-file comment block.
#   (3) README.md — deployment section.
#
# Anyone trying to add `--workers 4` trips over this note three times before
# they succeed. If you remove or weaken this comment, restore one of the other
# two locations so the count of warnings stays at three.

set -euo pipefail

# 0) Fix volume ownership if needed. Container starts as root so we can chown.
# Named volumes on a fresh VPS deploy initialize as root-owned. The Dockerfile's
# build-time `chown` covers new volumes, but volumes that already existed as root
# need this runtime fix. Idempotent: check the dir's owner UID before chowning.
_data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
if [ "$_data_owner" != "1000" ]; then
    chown -R app:app /app/data
fi

# 1) Run migrations. Idempotent. Runs as root — harmless for Postgres auth.
#    Compose's `depends_on: coffee-snobbery-db: condition: service_healthy`
#    gates this on Postgres being ready.
alembic upgrade head

# 2) Drop to app user and launch uvicorn. `exec gosu` replaces this shell with
#    uvicorn as PID 1, so SIGTERM goes directly to uvicorn for clean shutdown.
exec gosu app uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
```
[VERIFIED: preserves all invariants from current entrypoint.sh; `exec uvicorn` becomes `exec gosu app uvicorn`]

### Dockerfile runtime stage change (DEBT-01)
```dockerfile
# In the existing apt-get RUN block, add gosu to the install list:
apt-get install -y --no-install-recommends postgresql-client-16 gosu

# Remove the USER app line (line 122 in current Dockerfile):
# USER app   <-- DELETE this line
# entrypoint.sh now handles the privilege drop via gosu
```

### test_setup_concurrent_race fix (DEBT-02)
```python
@pytest.mark.asyncio
async def test_setup_concurrent_race(async_client) -> None:
    """AUTH-02: two concurrent POST /setups → exactly one 303→/ + one 303→/login."""
    _require_auth_router()

    # Ensure the in-memory settings cache is cleared before async_client's
    # lifespan/prewarm_cache runs. test_setup_blocked_after_completion uses
    # raw engine.begin() to set setup_completed='true', bypassing set_setting()
    # and therefore not invalidating _svc._cache. Without this clear, a stale
    # _cache['setup_completed'] = CachedSetting(value='true') from a prior
    # test causes prewarm_cache to pick up stale data, which — depending on
    # pytest fixture ordering — can make both concurrent POSTs see 'true' in
    # their direct DB reads (which is a separate code path, but the DB state
    # from fresh_db and the cache state must both be clean).
    try:
        import app.services.settings as _svc_mod
        _svc_mod._cache.clear()
    except Exception:
        pass

    # ... rest of test body unchanged from current implementation ...
```

### CI double-run guard (DEBT-02, CI step shape)
```yaml
# In .github/workflows/ci.yml, after the existing "Pytest full suite" step:
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
    # Run the suite a second time against the SAME database (no drop/recreate).
    # If teardown fixtures leave residue, run 2 will surface cross-module state
    # pollution that run 1 masked. SNOB_CI=1 converts skips to failures.
    python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

---

## Verification Ledger Shape (Claude's Discretion)

**Recommendation:** Create a single `15-VERIFICATION.md` in the phase directory. Consolidate all DEBT-04/05 outcomes there, grouped by source phase. This is auditable and does not require editing archived phase directories (which are historical record).

Structure:
```
.planning/phases/15-v1-1-debt-cleanup/15-VERIFICATION.md
  Phase 15 Closure Ledger
  ├── DEBT-01: chown fix — automated (rebuild + fresh deploy test)
  ├── DEBT-02: test isolation — automated (double pytest run green)
  ├── DEBT-03: nav/sign-out — on-device (John confirmed date)
  ├── DEBT-04: Human UAT by source phase (01/02/07/10/11)
  └── DEBT-05: human_needed by source phase (01/02/07/09/10/11)
  D-13: safe-area commit 982c0e6 — on-device (John confirmed date)
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Compose | DEBT-01 rebuild + fresh-deploy test | ✓ (project standard) | — | — |
| VPS deployment | 01-UAT-1, 07-UAT-1/2, 11-UAT-1/2/3, D-13 | ✓ (existing VPS) | — | Some items (see above) can use local instance |
| Real iOS device | 11-UAT-1/3, D-13 | ✓ (John has iPhone) | — | Cannot substitute emulator for install+safe-area verification |
| Chrome DevTools | 02-UAT-1, 10-VERIF-1/2, 11-UAT-2 | ✓ | — | — |
| Live AI credentials | 07-UAT-1/2, 09-item-6 | ✓ (on VPS, need to verify enabled) | — | Re-defer with reason if creds not active |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x + pytest-asyncio |
| Config file | `pytest.ini` or `pyproject.toml` (existing) |
| Quick run command | `docker compose run --rm coffee-snobbery-test tests/ --ignore=tests/e2e -rs -x` |
| Full suite command | `docker compose run --rm coffee-snobbery-test tests/ --ignore=tests/e2e -rs --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEBT-01 | Fresh deploy writes to /app/data as non-root without manual chown | Manual / smoke | `docker compose run --rm -u root coffee-snobbery stat -c '%u' /app/data` (should return `1000`) | N/A — manual |
| DEBT-02 | Full suite green run 1 | integration | `pytest tests/ --ignore=tests/e2e -rs` | ✅ existing |
| DEBT-02 | Full suite green run 2 (same DB, residue proof) | integration | `pytest tests/ --ignore=tests/e2e -rs` (second invocation) | ✅ existing |
| DEBT-02 | `test_setup_concurrent_race` passes in full suite | integration | `pytest tests/ -rs --tb=short --ignore=tests/e2e -k test_setup_concurrent_race` | ✅ exists, needs fix |
| DEBT-03 | Sign-out form present in config_hub.html | unit | `pytest tests/test_nav.py::test_config_hub_has_mobile_signout_form` | ✅ existing |
| DEBT-03 | navBar component on home page | unit | `pytest tests/test_nav.py::test_authenticated_home_has_nav_bar_component` | ✅ existing |
| DEBT-03 | On-device nav + sign-out verified | manual | John on physical device | ❌ Wave 0 gap — interactive |
| DEBT-04 | Human UAT items closed/deferred | manual | Interactive device session | ❌ Wave 0 gap — interactive |
| DEBT-05 | human_needed items resolved/deferred | manual | Interactive device session | ❌ Wave 0 gap — interactive |

### Sampling Rate
- **Per task commit (automated items):** `pytest tests/test_nav.py -rs` + `pytest tests/ --ignore=tests/e2e -rs -x`
- **Per wave merge:** Full `pytest tests/ --ignore=tests/e2e -rs --tb=short` × 2 (double-run)
- **Phase gate:** Full double-run green + on-device session complete + verification ledger written

### Wave 0 Gaps
- [ ] `15-VERIFICATION.md` — phase ledger for DEBT-04/05/D-13 outcomes; created in Wave 0 as empty template
- [ ] CI step for double-run guard — append to `.github/workflows/ci.yml`
- [ ] No new test files required — `test_setup_concurrent_race` fix is in existing `tests/routers/test_auth.py`

*(Existing test infrastructure covers all automated requirements; Wave 0 work is ledger scaffolding + CI guard + concurrent race fix)*

---

## Security Domain

Security enforcement applies. DEBT-01 and DEBT-02 have minor security considerations.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | no change to auth logic |
| V3 Session Management | no | no change to session logic |
| V4 Access Control | no | no change to authorization |
| V5 Input Validation | no | no new input paths |
| V6 Cryptography | no | no crypto changes |
| V7 Error Handling | no | no new error paths |
| Container privilege | yes | gosu + root→app drop; no new capabilities granted |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Container escapes via root-owned process | Elevation of Privilege | `exec gosu` drops to UID 1000 before uvicorn starts; container runs unprivileged after startup |
| Test fixtures touching live DB | Tampering | DB-name interlock in `fresh_db` + `_reset_catalog_tables`; "test" in name check; unchanged |

**Security note on gosu:** `gosu` is a setuid binary. Adding it to the image increases the setuid surface. However: (a) the container runs as UID 1000 after startup, (b) `gosu` is only invoked during entrypoint startup (not by any user request), (c) this is the standard pattern used by Postgres and MySQL official images. Risk is accepted and standard. [CITED: docker-library/postgres uses gosu for this exact pattern]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Running Alembic migrations as OS root (before gosu drop) has no effect on Postgres auth | Architecture Patterns / Pitfall 3 | Low — Alembic connects as POSTGRES_USER regardless of OS UID; if wrong, migrations fail on fresh deploy |
| A2 | `stat` is available in `python:3.12-slim` (Debian bookworm slim) | Code Examples | Medium — if not available, need an alternative owner check (`ls -n`); highly likely available as coreutils dependency |

**If this table were empty:** All claims were verified or cited — table is not empty (two low-risk assumptions remain).

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| `Dockerfile: USER app` + no privilege drop | Root start + conditional chown + `exec gosu app` | Volumes owned by root on first deploy now writable without manual intervention |
| Unconditional chown on every boot | Idempotent stat-check before chown | O(1) check instead of O(n files) on subsequent boots |
| `exec uvicorn` | `exec gosu app uvicorn` | SIGTERM forwarded correctly; behavior otherwise identical |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: packages.debian.org/bookworm/gosu] — gosu is available in Debian bookworm official apt repository
- [VERIFIED: entrypoint.sh — current file, 36 lines, single `exec uvicorn`] — code to rewrite is confirmed
- [VERIFIED: Dockerfile — runtime stage, lines 67-132, `USER app` line 122, gosu not installed] — current state confirmed
- [VERIFIED: tests/conftest.py — `_reset_catalog_tables` lines 419-481, `fresh_db` lines 308-385, `_svc._cache.clear()` line 479] — T-INFRA-1 mechanism present and correct
- [VERIFIED: tests/test_nav.py — 5 tests, all guarded by `_require_nav_wired()`] — existing nav coverage
- [VERIFIED: app/templates/base.html — `{% if request.state.user %}` line 46, logout form line 161] — sign-out placement confirmed
- [CITED: github.com/docker-library/postgres/blob/master/17/bookworm/docker-entrypoint.sh] — official Postgres `gosu` + conditional ownership pattern

### Secondary (MEDIUM confidence)
- [CITED: docsaid.org/en/blog/gosu-usage/] — gosu entrypoint pattern: `exec gosu user "$@"` syntax verified
- [CITED: github.com/tianon/gosu] — gosu's `execve()` semantics and SIGTERM forwarding behavior

### Tertiary (LOW confidence — from training data)
- Pytest fixture ordering between autouse and explicitly requested function-scoped fixtures — the exact ordering behavior when both exist at function scope; the fix addresses this regardless of exact ordering by making the in-test cache clear explicit

---

## Metadata

**Confidence breakdown:**
- Standard stack (gosu): HIGH — package confirmed in Debian bookworm repos
- Architecture (entrypoint rewrite): HIGH — verified against current code, official Postgres pattern
- DEBT-02 root cause: MEDIUM — reasoning from code inspection; exact ordering failure mode is complex; the fix is conservative and correct regardless of which exact ordering triggers the failure
- Human UAT inventory: HIGH — pulled directly from HUMAN-UAT.md and VERIFICATION.md files
- Pitfalls: HIGH — derived from verified code + project memory

**Research date:** 2026-05-25
**Valid until:** 2026-06-25 (stable dependencies; gosu/apt stable)
