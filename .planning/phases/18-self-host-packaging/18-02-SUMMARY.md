---
phase: 18-self-host-packaging
plan: "02"
subsystem: infra
tags: [dockerfile, oci-labels, version-stamp, packaging, ci-source-tree]

requires:
  - phase: 18-self-host-packaging/18-01
    provides: planning context and phase decisions including D-12

provides:
  - Dockerfile runtime stage accepts APP_VERSION build-arg (default "dev"), stamps it as ENV
  - Six org.opencontainers.image.* LABEL lines on the runtime stage
  - get_app_version() helper in app/config.py (FOUND-10 compliant os.environ read)
  - system.py env-var-first version chain: APP_VERSION env -> importlib.metadata -> pyproject.toml
  - pyproject.toml version bumped to 1.2.0

affects:
  - 18-04-PLAN (release.yml must pass build-args: APP_VERSION=${{ github.ref_name }})
  - future admin panel version display

tech-stack:
  added: []
  patterns:
    - "D-12 env-var-first version resolution: Dockerfile ARG/ENV -> get_app_version() -> importlib.metadata -> pyproject.toml"
    - "FOUND-10 compliant os.environ helper: new env reads go into app/config.py functions, not directly in app modules"

key-files:
  created: []
  modified:
    - Dockerfile
    - app/config.py
    - app/routers/admin/system.py
    - pyproject.toml

key-decisions:
  - "D-12 env-var-first pattern: APP_VERSION env var is first read; importlib.metadata and pyproject.toml are fallbacks for CI and dev"
  - "FOUND-10 compliance: os.environ.get('APP_VERSION') lives in app/config.py get_app_version() helper, not directly in system.py — avoids breaking tests/test_no_direct_env.py"
  - "pyproject.toml version bumped to 1.2.0 so the CI/dev fallback path reports the correct milestone string"
  - "ARG APP_VERSION=dev in runtime stage only (not tailwind-builder) — ARGs do not cross stage boundaries"
  - "OCI labels are static in Dockerfile; docker/metadata-action will override created+revision dynamically in CI"

patterns-established:
  - "Version resolution hierarchy: Dockerfile ENV > importlib.metadata > pyproject.toml"
  - "FOUND-10 extension pattern: new os.environ reads that must live outside Settings go into named helper functions in app/config.py"

requirements-completed: [DIST-02]

duration: 15min
completed: 2026-05-28
---

# Phase 18 Plan 02: APP_VERSION Stamp + OCI Labels Summary

**Dockerfile runtime stage now accepts `APP_VERSION` build-arg and emits 6 OCI image labels; `system.py` admin version display uses an env-var-first fallback chain through a FOUND-10-compliant helper in `app/config.py`; `pyproject.toml` bumped to `1.2.0`.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-28T00:00:00Z
- **Completed:** 2026-05-28
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Dockerfile runtime stage carries `ARG APP_VERSION=dev` + `ENV APP_VERSION=${APP_VERSION}` immediately after the existing ENV block; OCI LABEL block (6 labels) inserted before `EXPOSE 8000`
- `app/config.py` gains `get_app_version()` helper function that reads `os.environ.get("APP_VERSION")` (authorized location per FOUND-10)
- `app/routers/admin/system.py` imports `get_app_version` and uses it as the first step in version resolution before falling through to `importlib.metadata` then `pyproject.toml`
- `pyproject.toml` version bumped from `0.1.0` to `1.2.0` so the pyproject.toml fallback path reports the current milestone

## Task Commits

1. **Task 1: Dockerfile APP_VERSION ARG + OCI labels** - `e3b0cd2` (feat)
2. **Task 2: env-var-first version display + pyproject 1.2.0** - `d07cc6b` (feat)

**Plan metadata:** see below (SUMMARY commit)

## Dockerfile Diff Hunks

**Hunk 1 — ARG/ENV insertion** (after line 72, before the postgresql-client RUN block at line 77):
- Lines inserted: comment block (4 lines) + `ARG APP_VERSION=dev` + `ENV APP_VERSION=${APP_VERSION}` = 6 lines added
- Post-edit ARG is at line 77, ENV at line 78

**Hunk 2 — OCI LABEL insertion** (after `RUN mkdir -p /app/data/...` at line 120, before `EXPOSE 8000`):
- Lines inserted: comment block (4 lines) + 6-line LABEL block = 10 lines added
- All 6 required label keys present: title, description, url, source, version, licenses

## system.py Before / After

**Before (lines 131-144):**
```python
# --- System Info (ADMIN-05) ---
try:
    app_version = pkg_version("coffee-snobbery")
except PackageNotFoundError:
    _pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if _pyproject.exists():
        with _pyproject.open("rb") as _f:
            app_version = tomllib.load(_f).get("project", {}).get("version", "unknown")
    else:
        app_version = "unknown"
```

**After:**
```python
# --- System Info (ADMIN-05) ---
# D-12: APP_VERSION env var (stamped by the Dockerfile from the git tag)
# is the source of truth on baked images. Fall through to
# importlib.metadata (installed package) then pyproject.toml so the
# display still works on CI source trees and dev runs.
app_version = get_app_version()
if not app_version:
    try:
        app_version = pkg_version("coffee-snobbery")
    except PackageNotFoundError:
        _pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        if _pyproject.exists():
            with _pyproject.open("rb") as _f:
                app_version = tomllib.load(_f).get("project", {}).get("version", "unknown")
        else:
            app_version = "unknown"
```

The `get_app_version()` helper in `app/config.py` handles the `os.environ.get("APP_VERSION")` call, keeping FOUND-10 intact.

## pyproject.toml Version Bump

`version = "0.1.0"` → `version = "1.2.0"` (line 7)

## Verification Results

- `grep -c 'ARG APP_VERSION=dev' Dockerfile` → 1 (V18-15 OK)
- `grep -c 'org.opencontainers.image' Dockerfile` → 7 (6 label lines + 1 in comment; V18-14 OK)
- All 6 OCI label keys confirmed present: title, description, url, source, version, licenses
- `ARG APP_VERSION=dev` is in `runtime` stage only (confirmed via awk position check)
- `ENTRYPOINT ["./entrypoint.sh"]`, `EXPOSE 8000`, `FROM runtime AS dev` all unchanged
- `ruff format --check .` → 224 files already formatted (exit 0)
- `ruff check .` → All checks passed! (exit 0)
- `tests/test_no_direct_env.py` invariant: no `os.environ` outside `app/config.py` (confirmed via grep)
- `tests/test_env_example.py` invariant: APP_VERSION NOT in Settings.model_fields, NOT in .env.example

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Routed os.environ read through app/config.py to preserve FOUND-10**
- **Found during:** Task 2 (env-var-first version resolution)
- **Issue:** The plan called for `import os` + `os.environ.get("APP_VERSION")` directly in `app/routers/admin/system.py`. However, `tests/test_no_direct_env.py` (FOUND-10) asserts that `os.environ` may only be referenced in `app/config.py`. Adding it to `system.py` would have caused that test to fail.
- **Fix:** Added `get_app_version()` helper function to `app/config.py` (the authorized location). `system.py` imports and calls `get_app_version()` instead of reading `os.environ` directly. The D-12 env-var-first semantics are identical; only the location of the `os.environ` call changed.
- **Files modified:** `app/config.py` (new helper), `app/routers/admin/system.py` (import + call)
- **Verification:** `grep -rn "os.environ" app --include="*.py" | grep -v "app/config.py"` returns no app/ offenders; FOUND-10 passes.
- **Committed in:** `d07cc6b` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug: plan's direct os.environ call would break FOUND-10 test)
**Impact on plan:** Functionally identical to the plan's intent. The D-12 env-var-first pattern works exactly as specified; only the call site moved to the authorized module. No scope creep.

## Carry-Forward Note

**Plan 04 (release.yml) MUST pass `build-args: APP_VERSION=${{ github.ref_name }}`** to wire this end-to-end. Without that, baked release images will report `APP_VERSION=dev` (the Dockerfile ARG default) and the `/admin` version display will fall through to `importlib.metadata` / `pyproject.toml`.

## Docker Smoke Check

The live `docker build` smoke check (Task 1 acceptance criteria) was skipped to avoid a >5-min build on this host. Static grep/awk assertions confirmed all structural requirements:
- `ARG APP_VERSION=dev` present in `runtime` stage (post-`FROM python:3.12-slim AS runtime`)
- `ENV APP_VERSION=${APP_VERSION}` present once
- 6 `org.opencontainers.image.*` label lines present before `EXPOSE 8000`
- `dev` stage and `ENTRYPOINT` untouched

## Tests / Parity Invariants

- `tests/test_env_example.py` (FOUND-09 / V18-02): APP_VERSION is in neither Settings nor .env.example — parity preserved. Test re-assertable after Plan 03 lands.
- `tests/test_no_direct_env.py` (FOUND-10): No `os.environ` in any `app/` file outside `app/config.py` — preserved by the get_app_version() approach.

## Issues Encountered

None beyond the FOUND-10 deviation documented above.

## Next Phase Readiness

- Dockerfile is ready: Plan 04 (release.yml) can now pass `--build-arg APP_VERSION=${{ github.ref_name }}` and the resulting image will carry both the ENV and the OCI label
- Admin version display is ready: will show the git tag version on baked images, and `1.2.0` via pyproject.toml on CI/dev runs
- No blockers for Plans 18-03 through 18-05

---
*Phase: 18-self-host-packaging*
*Completed: 2026-05-28*
