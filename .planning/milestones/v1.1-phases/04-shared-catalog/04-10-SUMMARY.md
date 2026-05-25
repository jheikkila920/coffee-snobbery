---
phase: 04-shared-catalog
plan: 10
subsystem: photos
tags: [photos, serving, fileresponse, auth-gate, path-traversal, cache-headers, sec-07, t-04-auth, t-04-photo, t-04-poly, d-06, d-12]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: FragmentCacheHeadersMiddleware D-12 "do not overwrite route Cache-Control" escape hatch; SecurityHeadersMiddleware emits the global X-Content-Type-Options nosniff
  - phase: 02-auth
    provides: SessionMiddleware populates request.state.user; seeded_admin_user fixture in tests/conftest.py
  - plan: 04-01
    provides: app/services/photos.py PHOTOS_DIR + _is_safe_photo_filename — single-source regex consumed by the route as the path-traversal defense
provides:
  - app/routers/photos.py — GET /photos/{filename} auth-gated FileResponse with D-06 header contract (Content-Type image/jpeg + Cache-Control private+max-age=31536000+immutable + X-Content-Type-Options nosniff + Content-Disposition inline)
  - app/main.py — registers photos_router in create_app() after roasters_router
  - tests/phase_04/test_routers_photos.py — 15 real router tests replacing the Wave-0 stub
affects:
  - 04-09 (bag photo upload) — <img src="/photos/{filename}"> in bag detail templates can now resolve
  - phase-05 (brew session form) — bag photo thumbnails render via this route
  - phase-06 (home page) — latest bag thumbnail renders via this route
  - phase-08 (orphan sweep) — sweep removes unreferenced files; this route is the read-side counterpart that proves the FS-backed serving contract

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-attribute lookup for monkeypatchable constants — app/routers/photos.py imports the module (from app.services import photos as _photos_svc) instead of the name (from app.services.photos import PHOTOS_DIR) so the Wave-0 photo_volume fixture's monkeypatch on app.services.photos.PHOTOS_DIR is honored at request time."
    - "Auth gate via request.state.user direct-read for 404-on-anonymous routes (D-06 existence-leak defense). Distinct from the Phase 2 Depends(require_user) Form-1 pattern which returns 401."
    - "Belt-and-braces path containment: regex + Path.resolve().relative_to(PHOTOS_DIR.resolve()) double-check for path traversal. The regex is already strict enough; the resolve check survives a future regex regression."
    - "Duplicate-header tolerance: SecurityHeadersMiddleware emits X-Content-Type-Options nosniff globally; the route also emits it (defense in depth per the plan's done-criteria grep). Tests assert containment (\"nosniff\" in value) rather than equality because httpx collapses repeated header values into a comma-joined list — RFC 9110 §5.3 says this is equivalent to a single header."

key-files:
  created:
    - app/routers/photos.py
  modified:
    - app/main.py — adds photos_router import + include_router(photos_router.router) after roasters_router
    - tests/phase_04/test_routers_photos.py — replaced 1-line Wave-0 skip stub with 15 real router tests

key-decisions:
  - "Auth gate reads request.state.user directly instead of Depends(require_user). Rationale (D-06 lock): require_user raises 401, but D-06 mandates 404 to defeat existence enumeration. A handler that raises 401 advertises 'this is an auth-gated route'; a handler that raises 404 says nothing."
  - "Module-attribute lookup (_photos_svc.PHOTOS_DIR) instead of frozen name import (from app.services.photos import PHOTOS_DIR). Without this, the Wave-0 photo_volume fixture's monkeypatch had no effect — the router carried its own pre-patch binding. This is the same shape app/services/photos.py uses internally for sweep_orphans' lazy DB import."
  - "Route emits X-Content-Type-Options nosniff explicitly even though SecurityHeadersMiddleware already does. The done-criteria grep on app/routers/photos.py requires the literal in-file; duplicate headers are RFC-equivalent to a single header so the defense-in-depth posture has no behavioral cost."
  - "Belt-and-braces Path.resolve().relative_to(PHOTOS_DIR.resolve()) re-check after the regex gate. The regex is already strict enough (32 lowercase hex + optional -thumb + .jpg, no separators) — the resolve check is defense in depth against a hypothetical regex relaxation."
  - "media_type='image/jpeg' is hard-coded because plan 04-01 process_and_save always re-encodes to JPEG regardless of upload format (JPEG/PNG/WebP). If a future Phase 4+ revision allows non-JPEG storage, the route must switch on extension. Documented in the route docstring."

patterns-established:
  - "Module-attribute lookup pattern for monkeypatchable singletons in routers — when a router consumes a constant that a fixture may patch (filesystem paths, env-driven defaults), import the module not the name."
  - "404-on-anonymous gate pattern for routes whose mere existence is sensitive — read request.state.user directly, 404 on None. Use sparingly: most app routes correctly distinguish 401 (not authenticated) from 403 (not authorized)."

requirements-completed:
  - SEC-07

# Metrics
duration: 35min
completed: 2026-05-18
---

# Phase 4 Plan 10: Photo Serving Route Summary

**Auth-gated GET /photos/{filename} via FastAPI FileResponse — D-06 header contract (explicit Content-Type + nosniff + immutable cache + inline disposition), regex + path-resolve belt-and-braces traversal defense, anonymous-returns-404 existence-leak defense, and Phase 1 D-12 verification that the route's Cache-Control survives FragmentCacheHeadersMiddleware.**

## Performance

- **Duration:** ~35 minutes
- **Started:** 2026-05-18T21:25:00Z
- **Completed:** 2026-05-19T02:35:00Z (UTC; clock drifted across docker exec boundary — duration measured from worktree commit timestamps)
- **Tasks:** 2
- **Files created:** 1 (app/routers/photos.py)
- **Files modified:** 2 (app/main.py + tests/phase_04/test_routers_photos.py)

## Accomplishments

- `app/routers/photos.py` ships the SEC-07 / D-06 photo serving route. Single GET handler at `/photos/{filename}` with the full D-06 header contract: explicit `Content-Type: image/jpeg`, `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`. NOT a `StaticFiles` mount.
- Auth gate reads `request.state.user` directly (NOT `Depends(require_user)`) so anonymous requests return 404 instead of 401 — the D-06 existence-leak defense. Authenticated callers proceed to filename validation.
- Filename validation reuses plan 04-01's `_is_safe_photo_filename` regex (32 lowercase hex + optional `-thumb` + `.jpg`). Belt-and-braces `Path.resolve().relative_to(PHOTOS_DIR.resolve())` re-check defends against a hypothetical future regex relaxation. All four 404 branches (anon, regex-reject, outside PHOTOS_DIR, file-missing) collapse to a single status without leaking which gate fired.
- `app/main.py` registers the new router after `roasters_router` in `create_app()`. Lifespan unchanged.
- `tests/phase_04/test_routers_photos.py` ships 15 real tests replacing the 1-line `pytest.skip` Wave-0 stub. All four D-06 headers asserted, both 404 branches asserted (anon-no-file + anon-with-file), full filename validation matrix (traversal, wrong extension, malformed UUID, uppercase hex, missing file, `-thumb` variant), and Phase 1 D-12 contract verified end-to-end (route Cache-Control survives both the full-page and HX-Request branches of `FragmentCacheHeadersMiddleware`).
- Full test suite green: `208 passed, 8 skipped, 10 xfailed`. The +15 net is the new router tests; no regressions traced to this plan.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement app/routers/photos.py + register in app/main.py** — `6ac5721` (feat)
2. **Task 2: Author 15 real router tests + module-attribute binding auto-fix** — `f78888d` (test)

## Files Created/Modified

### Created
- `app/routers/photos.py` — auth-gated `GET /photos/{filename}` route. Reads `_photos_svc.PHOTOS_DIR` dynamically so the Wave-0 `photo_volume` fixture's monkeypatch is honored at request time. ~90 LOC including module docstring + route docstring.

### Modified
- `app/main.py` — adds `from app.routers import photos as photos_router` and `app.include_router(photos_router.router)` after `roasters_router`. Two-line addition; no other surface change.
- `tests/phase_04/test_routers_photos.py` — replaced the Wave-0 `pytest.skip` stub with 15 real router tests organized into four groups: (a) anonymous → 404 contract, (b) authed happy path + D-06 header contract, (c) filename validation matrix, (d) Phase 1 D-12 Cache-Control survival. Local fixtures `written_main_jpeg`, `written_thumb_jpeg`, `anon_client` defined inline (the conftest `photo_volume` + `synthetic_jpeg` + `authed_client` cover the rest).

## Decisions Made

- **Auth gate via `request.state.user` direct-read (not `Depends(require_user)`).** Rationale: D-06 mandates 404 for anonymous requests; `require_user` raises 401. The direct-read pattern is the only way to fold "anonymous" into the same 404 status as "file not found" without leaking which gate fired. Documented in the route docstring.
- **Module-attribute lookup for `PHOTOS_DIR`** (`_photos_svc.PHOTOS_DIR`) rather than `from app.services.photos import PHOTOS_DIR`. The Wave-0 `photo_volume` fixture monkeypatches `app.services.photos.PHOTOS_DIR`; a frozen name-import in the router would carry its own pre-patch binding and the fixture would have no effect at request time. This is the same shape `app/services/photos.py` uses for `sweep_orphans`' lazy DB import — module-attribute lookup keeps testability and lazy-binding semantics aligned.
- **Belt-and-braces `Path.resolve().relative_to()` re-check** after the regex gate. The regex (32 lowercase hex + optional `-thumb` + `.jpg`, no separators) is already strict enough that the resolve check is functionally a no-op today. It's there for the hypothetical case where a future plan relaxes the regex (e.g., adds PNG/WebP support) and forgets the containment check — defense in depth at a one-liner cost.
- **`media_type="image/jpeg"` hard-coded.** All files written by `process_and_save` are JPEG regardless of upload format (the pipeline always re-encodes via `Image.save(..., "JPEG", quality=85)`). If a future revision allows non-JPEG storage, the route must switch on extension. Noted in the route docstring.
- **Duplicate `X-Content-Type-Options: nosniff` is acceptable.** The global `SecurityHeadersMiddleware` already emits it; the route emits it too because the plan's `<done>` criterion is a grep on `app/routers/photos.py` for the literal header value. Browsers and HTTP-spec semantics treat duplicate identical values as a single value (RFC 9110 §5.3) — defense in depth at zero behavioral cost. Tests use containment (`"nosniff" in value`) rather than equality to tolerate the duplication.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Frozen `PHOTOS_DIR` binding in `app/routers/photos.py`**

- **Found during:** Task 2 (first test run of `test_authed_returns_photo` returned 404 with the file on disk + a valid session).
- **Issue:** The initial Task 1 implementation imported `PHOTOS_DIR` by name (`from app.services.photos import PHOTOS_DIR`), which captures the value at module-import time. The Wave-0 `photo_volume` fixture patches `app.services.photos.PHOTOS_DIR` for tests — but the router's frozen binding still pointed at the production `/app/data/photos` path. Result: tests wrote files into `tmp_path / "photos"` but the route looked them up in the production volume → `is_file()` False → 404.
- **Fix:** Switched to `from app.services import photos as _photos_svc` (module import) and `_photos_svc.PHOTOS_DIR` lookup at request time. `_is_safe_photo_filename` is a pure function and is fine to bind by name; the alias `_is_safe_photo_filename = _photos_svc._is_safe_photo_filename` is kept at module scope for readability and to satisfy the plan's done-criteria grep.
- **Files modified:** `app/routers/photos.py` (committed in `f78888d` alongside the Task 2 tests).
- **Verification:** All 15 tests pass after the fix. Production behavior is unchanged (the module attribute is set once at process start; no per-request cost). Full phase_04 suite: `95 passed, 6 skipped`. Full repo suite: `208 passed, 8 skipped, 10 xfailed`.

**2. [Rule 1 - Bug] Duplicate `X-Content-Type-Options` header concatenation in tests**

- **Found during:** Task 2 (running `test_authed_response_has_nosniff_header` after the binding fix).
- **Issue:** The initial test asserted `resp.headers["x-content-type-options"] == "nosniff"`, but the response carried `"nosniff, nosniff"` because both the route and the global `SecurityHeadersMiddleware` set the header. HTTPX collapses repeated header values into a comma-joined list per RFC 9110 §5.3 — semantically equivalent to a single value, but the equality assertion fails.
- **Fix:** Changed the two affected assertions from `==` to `in` containment. The route's emission stays (the plan's `<done>` criterion requires a grep match in the router file) and the middleware's emission stays (it's the global SEC-03 contract). Both layers asserting `nosniff` is intentional defense in depth.
- **Files modified:** `tests/phase_04/test_routers_photos.py` (committed in `f78888d` alongside the binding fix).
- **Verification:** All 15 tests pass.

---

**Total deviations:** 2 auto-fixed Rule-1 bugs. The first is a real bug in the production code (a frozen-binding correctness issue that breaks testability); the second is a test-assertion calibration to match the runtime header concatenation. Zero scope creep — both fixes sit inside files the plan already names in `files_modified`.

**Impact on plan:** The binding fix is a small production-safety improvement (any future fixture that needs to swap the photos directory now works) and a documented pattern future router authors should follow when consuming module-level mutable constants. The test-assertion fix is purely a test-suite calibration with no production impact.

## Issues Encountered

- **Worktree → container file sync.** The running Docker container has the production image, not the worktree's files. Verification required `docker cp` of each modified file into `coffee-snobbery:/app/...` before each `docker compose exec ... pytest` invocation. Same issue noted in plan 04-03's SUMMARY; no plan-level action item — the structural fix (split runtime/test stages or add a bind-mount dev compose profile) is logged for ops work.
- **`docker compose exec` from the worktree fails on missing `.env`.** The compose file references `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}` from `.env`; the worktree has no `.env`. Workaround: run docker compose commands from the main repo root (`cd C:/Claude/Coffee-Snobbery && docker compose exec ...`) where the `.env` file lives. Pure operational friction; no code change required.
- **`SecurityHeadersMiddleware` emits a `X-Content-Type-Options: nosniff` header globally.** The route also emits one per D-06; httpx surfaces this as `"nosniff, nosniff"` in the response header dict. Behavior is RFC-correct (repeated identical values are equivalent to one) and the test-assertion calibration above handles it. Noted here so future maintainers don't try to "fix" the duplication by removing the route's emission — the plan's `<done>` grep depends on the in-file literal.

## User Setup Required

None — this plan ships a single route + tests. No new env vars, no external service configuration, no DB migration.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1** verify (`docker compose exec coffee-snobbery python -c "from app.routers.photos import router, serve_photo; print(router.prefix)"`) → `/photos` ✓
- **Task 1** done-criteria greps:
  - `grep -c 'FileResponse' app/routers/photos.py` → `3` ✓ (≥1 required)
  - `grep -c 'Cache-Control.*max-age=31536000.*immutable' app/routers/photos.py` → `2` ✓ (≥1 required)
  - `grep -c 'X-Content-Type-Options.*nosniff' app/routers/photos.py` → `3` ✓ (≥1 required)
  - `grep -c 'Content-Disposition.*inline' app/routers/photos.py` → `2` ✓ (≥1 required)
  - `grep -c 'include_router.photos_router' app/main.py` → `1` ✓
- **Task 2** verify (`docker compose exec coffee-snobbery pytest -q tests/phase_04/test_routers_photos.py -x`) → `15 passed` ✓ (≥12 required)
- **Task 2** done-criteria coverage:
  - Four D-06 header assertions present (cache-control via 3 substrings + x-content-type-options + content-disposition + content-type) ✓
  - Anonymous-returns-404 test present (locks the existence-leak defense) — `test_anonymous_returns_404` + `test_anonymous_with_existing_file_still_404` ✓
  - Cache-Control-not-overwritten test present (locks the Phase 1 D-12 contract) — `test_cache_control_not_overwritten_by_middleware` + `test_hx_request_does_not_force_no_store` ✓

Full phase_04 suite: `docker compose exec coffee-snobbery python -m pytest -q tests/phase_04/` → `95 passed, 6 skipped, 7 warnings in 7.02s` ✓.

Full repo suite: `docker compose exec coffee-snobbery python -m pytest -q` → `208 passed, 8 skipped, 10 xfailed, 34 warnings in 14.65s` ✓ (was 193 before this plan; +15 net = 15 new router tests).

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-AUTH | `serve_photo` anonymous branch | Direct `request.state.user` read; raise 404 on None (not 401/403). | `test_anonymous_returns_404`, `test_anonymous_with_existing_file_still_404` |
| T-04-PHOTO (path traversal) | `serve_photo` filename param | `_is_safe_photo_filename` regex (32 lowercase hex + optional `-thumb` + `.jpg`); `Path.resolve().relative_to(PHOTOS_DIR.resolve())` re-check. | `test_authed_path_traversal_returns_404`, `test_authed_wrong_extension_returns_404`, `test_authed_malformed_uuid_returns_404`, `test_authed_uppercase_uuid_returns_404` |
| T-04-POLY (MIME-sniff) | `serve_photo` response | Explicit `Content-Type: image/jpeg` + `X-Content-Type-Options: nosniff` + `Content-Disposition: inline`. | `test_authed_returns_photo`, `test_authed_response_has_nosniff_header`, `test_authed_response_has_content_disposition_inline`, `test_route_emits_route_owned_headers_not_static_files` |
| Cache leak | `serve_photo` Cache-Control | `private` (keeps photos out of shared caches) + `max-age=31536000, immutable` (safe because UUID4 filenames are write-once). Route value survives `FragmentCacheHeadersMiddleware` per Phase 1 D-12. | `test_authed_response_has_d06_cache_headers`, `test_cache_control_not_overwritten_by_middleware`, `test_hx_request_does_not_force_no_store` |

## Next Plan / Consumer Readiness

- **Plan 04-09 (bag photo upload)** can now render `<img src="/photos/{filename}">` in bag detail templates with confidence that the auth gate + cache + nosniff contracts are correct.
- **Plan 04-11 (autocomplete + mini-modal)** referenced `/photos/{filename}` for thumbnail rendering — the route is ready and the `-thumb` regex branch is test-covered.
- **Phase 5 (brew session UI)** can render bag photos in the session form without re-implementing the auth-gate or cache headers.
- **Phase 6 (home page)** can render the latest bag's thumbnail via `/photos/{filename}-thumb.jpg`.
- **Phase 8 (orphan sweep)** is a write-side concern (FS cleanup); this plan is the read-side counterpart. The two have no direct coupling — both go through `_is_safe_photo_filename` for any filename they touch.

## Self-Check: PASSED

- `app/routers/photos.py` exists at the worktree path: FOUND
- `app/main.py` imports and includes `photos_router`: FOUND (both lines present)
- `tests/phase_04/test_routers_photos.py` has 15 real tests (no `pytest.skip` stub): FOUND
- Commit `6ac5721` (Task 1) in `git log`: FOUND
- Commit `f78888d` (Task 2) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_routers_photos.py` returns `15 passed`: FOUND
- Container verify `pytest -q tests/phase_04/` returns `95 passed, 6 skipped`: FOUND
- Container verify `pytest -q` (full repo) returns `208 passed, 8 skipped, 10 xfailed`: FOUND
- No deletions in either Task 1 or Task 2 commits: VERIFIED (`git diff --diff-filter=D HEAD~2..HEAD` is empty)

---
*Phase: 04-shared-catalog*
*Plan: 10*
*Completed: 2026-05-18*
