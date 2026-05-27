---
phase: 15-v1-1-debt-cleanup
reviewed: 2026-05-25T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - Dockerfile
  - entrypoint.sh
  - tests/routers/test_auth.py
  - .github/workflows/ci.yml
findings:
  blocker: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-05-25T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 15 ships two surgical changes: a runtime privilege model (DEBT-01: root-start + conditional chown + `gosu` drop) and a test/CI isolation hardening (DEBT-02: in-test settings-cache clear + CI double-run guard). Both deltas are minimal and align with the plan documents.

No BLOCKER defects. The code is correct on the happy path verified in 15-01-SUMMARY.md (root-owned volume self-heals; uvicorn ends up as UID 1000; <3s SIGTERM). However, the privilege-drop logic has two real-world edge cases the smoke test did not cover (mixed-ownership descendants, GID-only mismatch), the test cache-clear guard uses a broad `except Exception` that defeats the project's own anti-silent-failure rule, the CI step duplicates a six-line `env` block verbatim instead of hoisting to job scope, and a Dockerfile comment is now stale because `USER app` was removed from the runtime stage but its anchor comment was left in place. All findings are WARNING or INFO.

## Warnings

### WR-01: Conditional chown only checks `/app/data` root; mixed-ownership descendants stay broken

**File:** `entrypoint.sh:25-28`
**Issue:** The guard runs `chown -R app:app /app/data` only when the TOP directory's owner UID is not `1000`. If `/app/data` itself is already `1000` but a descendant (e.g., `/app/data/backups/old_root_dump.sql` left by a previous broken-state run, or files restored from a backup taken when root owned the dir) is root-owned, the recursive chown is skipped and the residue stays unwritable. The 15-01-SUMMARY.md idempotency test only proves the clean-already-1000 case; it does not exercise mixed ownership. This is the exact partial-state scenario that produced G-01 in the first place.

**Fix:** Either (a) check `find /app/data ! -uid 1000 -print -quit` returns empty before skipping, or (b) accept the O(n) cost on the first boot per volume and chown unconditionally on first run, gated by a sentinel file:

```bash
# Option B: sentinel-gated unconditional chown
if [ ! -f /app/data/.ownership_normalized ]; then
    chown -R app:app /app/data
    touch /app/data/.ownership_normalized
    chown app:app /app/data/.ownership_normalized
fi
```

This is idempotent after first run (single `test -f` per boot) and covers descendant ownership drift.

### WR-02: Chown guard checks UID only -- a GID mismatch is invisible

**File:** `entrypoint.sh:25`
**Issue:** `stat -c '%u' /app/data` returns only the owner UID. `chown -R app:app` sets both owner AND group. A directory owned by `1000:0` (UID app, GID root -- possible if a previous root-side `mkdir` ran without an explicit group, or if a bind-mount inherits the host's `root` group) passes the guard with `_data_owner=1000` and the chown is skipped, leaving the group as root. Backups written by `app` would still be GID `root` -- readable on most systems but a subtle ownership-policy violation, and on a host with restrictive `umask` it could surface as a write failure on group-owned subdirs.

**Fix:** Check both UID and GID, or compare to a single `stat -c '%u:%g'` string:

```bash
_data_owner=$(stat -c '%u:%g' /app/data 2>/dev/null || echo "0:0")
if [ "$_data_owner" != "1000:1000" ]; then
    chown -R app:app /app/data
fi
```

### WR-03: `except Exception` on the cache-clear masks any future symbol rename (silent test pass)

**File:** `tests/routers/test_auth.py:148-153`
**Issue:** The new guard catches ALL exceptions:

```python
try:
    import app.services.settings as _svc_mod
    _svc_mod._cache.clear()
except Exception:
    pass
```

The plan rationale (15-02-PLAN.md line 113) was "wrapped in try/except so an import failure never breaks the test" -- i.e., the catch is meant for `ImportError` during Wave-0-style staged imports. Broad `except Exception` also swallows `AttributeError` if `_cache` is renamed (e.g., to `_settings_cache` or moved to a class attribute), `TypeError` if `_cache` becomes a property, etc. The test would then pass with a stale cache exactly as it does today, defeating the fix and reintroducing the original cross-module flake -- silently. This is the project-memory "tests pass-by-skip mask green" pattern manifested as "test pass-by-swallowed-exception".

The corresponding conftest helper (`tests/conftest.py:476-481`) has the same broad catch, so this is a pre-existing pattern -- but the plan explicitly called this a "root-cause fix" and a broad catch undermines that claim.

**Fix:** Narrow to `ImportError` (which is the only failure mode the plan rationale actually anticipates):

```python
try:
    import app.services.settings as _svc_mod
except ImportError:
    pass
else:
    _svc_mod._cache.clear()  # type: ignore[attr-defined]
```

If you keep the broad catch, at minimum log/print the swallowed exception so a future suite run leaves a breadcrumb instead of a silent pass.

### WR-04: CI env block duplicated verbatim between two steps -- maintenance footgun

**File:** `.github/workflows/ci.yml:60-85`
**Issue:** The `Pytest full suite` step (lines 60-69) and the new `Pytest isolation double-run` step (lines 71-85) carry IDENTICAL six-line `env:` blocks (`DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `SNOB_CI`). Any future change (rotating the test secret format, adding a new env var like `APP_FEATURE_FLAG`, changing the DB user) requires editing both blocks. Forgetting one yields a confusing "run 1 green, run 2 red" CI signal that looks like an isolation regression when it is actually env drift.

The plan mandated verbatim duplication (15-02-PLAN.md line 161), so this matches spec, but it leaves the workflow with a step-level env block that should live at job scope.

**Fix:** Hoist the shared env vars to job-level `env:` so steps inherit. Example:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: snobbery
      APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxx...' }}
      APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123...=' }}
      SNOB_CI: "1"
    services: ...
    steps:
      - name: Pytest full suite
        run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
      - name: Pytest isolation double-run
        run: |
          # second run against same DB ...
          python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

This makes the duplication structural rather than copy-pasted.

### WR-05: `stat` fallback returns "0" for a missing `/app/data`, then chown explodes under `set -e`

**File:** `entrypoint.sh:25-28`
**Issue:** If `/app/data` does not exist (the Dockerfile creates it at build time so this is theoretical for the baked image, but a future bind-mount config, a damaged volume, or a `--volumes-from` of a wrong source could remove it), `stat -c '%u' /app/data 2>/dev/null` fails and the fallback `echo "0"` makes `_data_owner=0`. The conditional then runs `chown -R app:app /app/data` against a nonexistent path, which fails with `chown: cannot access '/app/data': No such file or directory`, and `set -euo pipefail` kills the entrypoint. The container exits before `alembic upgrade head` runs and before any logging that explains why.

**Fix:** Either drop the fallback and let `stat` failure abort early with a clearer error, or guard the chown on directory existence:

```bash
if [ ! -d /app/data ]; then
    echo "FATAL: /app/data missing -- check volume mount" >&2
    exit 1
fi
_data_owner=$(stat -c '%u' /app/data)
if [ "$_data_owner" != "1000" ]; then
    chown -R app:app /app/data
fi
```

This makes the missing-mount failure mode loud and diagnosable instead of a generic chown error.

## Info

### IN-01: Dockerfile comment block references the now-removed `USER app` line

**File:** `Dockerfile:113-120`
**Issue:** The comment above the data-mountpoint mkdir (lines 113-119) reads "Create the data mountpoints app-owned BEFORE `USER app`. Named volumes seed their ownership from the image dir on first mount, so this makes a fresh `coffee_snobbery_photos` / `coffee_snobbery_backups` volume writable by the non-root app user." Phase 15 removed `USER app` from the runtime stage. The comment's "BEFORE `USER app`" anchor no longer exists in the runtime stage, and the rationale ("makes a fresh volume writable by the non-root app user") is now satisfied by the entrypoint's conditional chown -- not by the build-time chown the comment is justifying. A reader cross-referencing the comment to the source will be confused.

**Fix:** Update the comment to reflect that the runtime stage now starts as root and the entrypoint handles the drop; the build-time `mkdir`/`chown` is now only useful for fresh named volumes that the entrypoint's idempotency check will short-circuit. Example:

```dockerfile
# Create the data mountpoints app-owned at build time so fresh named
# volumes seed with UID 1000 on first mount -- the entrypoint's
# conditional chown short-circuits in that case (idempotent). Existing
# root-owned volumes from pre-Phase-15 deploys are self-healed at boot
# by entrypoint.sh.
RUN mkdir -p /app/data/photos /app/data/backups && chown -R app:app /app/data
```

### IN-02: `_cache.clear()` lacks the `# type: ignore[attr-defined]` the conftest twin carries

**File:** `tests/routers/test_auth.py:151`
**Issue:** The conftest equivalent (`tests/conftest.py:479`) annotates the access with `_svc._cache.clear()  # type: ignore[attr-defined]` because `_cache` is module-private. The new test guard accesses the same private attribute without the type-ignore comment. If `mypy --strict` (or any stricter ruleset) is enabled later, the test file fails on `Module has no attribute "_cache"`. Consistency with the conftest pattern is the project convention.

**Fix:** Add the `# type: ignore[attr-defined]` comment on the `_cache.clear()` line:

```python
_svc_mod._cache.clear()  # type: ignore[attr-defined]
```

### IN-03: Hardcoded fallback test secrets in CI YAML (informational, expected for CI test gate)

**File:** `.github/workflows/ci.yml:66-67, 77-78`
**Issue:** Both the existing and new pytest steps carry inline fallback values for `APP_SECRET_KEY` (`'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'`) and `APP_ENCRYPTION_KEY` (`'0123456789abcdef0123456789abcdef0123456789a='`). These are intentional test-only fallbacks gated behind `${{ secrets.APP_SECRET_KEY || '...' }}` so a fork without secrets can still run CI, and they are not used to encrypt anything real. This is expected and was pre-existing -- not introduced in Phase 15 -- but worth flagging in the audit trail so a future reader does not "fix" it by removing the fallback and breaking forked-PR CI.

**Fix:** No action required. If consolidating env to job-scope per WR-04, keep the `secrets.X || 'literal'` expression intact so the fallback survives the move.

---

_Reviewed: 2026-05-25T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
