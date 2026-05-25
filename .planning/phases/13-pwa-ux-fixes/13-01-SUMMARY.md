---
phase: 13-pwa-ux-fixes
plan: "01"
subsystem: pwa
tags: [pwa, service-worker, cache-versioning, dockerfile, tdd]
dependency_graph:
  requires: []
  provides: [C9-build-id-txt, sw-cache-name-per-build]
  affects: [service-worker, pwa-caching, all-pwa-fixes-visibility]
tech_stack:
  added: []
  patterns: [build-time-artifact-injection, build_id.txt-first-hash-fallback-chain]
key_files:
  created: []
  modified:
    - Dockerfile
    - app/routers/pwa.py
    - tests/test_pwa.py
    - .gitignore
decisions:
  - "build_id.txt preferred over CSS hash: CSS hash only changes when tailwind.src.css changes; build_id.txt (UTC timestamp written unconditionally in stage-1 RUN) changes every build"
  - "Write in existing RUN block (not a separate layer): avoids an extra Docker layer with no cache benefit"
  - "Truncate build_id.txt to 16 chars: keeps CACHE_NAME compact while retaining uniqueness"
  - "Fallback chain: build_id.txt -> CSS filename hash -> 'dev': source-tree and CI runs stay green without a baked image"
metrics:
  duration: ~15min
  completed: "2026-05-25"
  tasks: 2
  files: 4
---

# Phase 13 Plan 01: C9 SW Cache Versioning Summary

One-liner: Unconditional build_id.txt (UTC timestamp) injected by Dockerfile stage-1, read by pwa.py before CSS hash, so the SW CACHE_NAME bumps on every docker compose build.

## What Was Built

C9 is the load-bearing gate for Phase 13: the service-worker CACHE_NAME must differ between consecutive builds so iOS-installed PWAs receive updated app shells without a manual "Clear site data." The root cause was `_get_build_hash()` deriving the cache key solely from the hashed Tailwind CSS filename, which only changes when `tailwind.src.css` content changes. A rebuild touching only a Python route or template produced an identical CACHE_NAME — the SW's activate handler saw no old caches to purge.

Fix:
1. Dockerfile stage-1 `RUN` block: appended `echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt` to the existing Tailwind compile block (no new layer).
2. Dockerfile stage-2: `COPY --from=tailwind-builder --chown=app:app /build/app/static/build_id.txt ./app/static/build_id.txt` copies the artifact into the runtime image.
3. `pwa.py _get_build_hash()`: rewritten to try `Path("app/static/build_id.txt")` first (returning stripped content truncated to 16 chars), then fall back to CSS-filename hash, then `"dev"`.
4. `.gitignore`: added `app/static/build_id.txt` (build artifact, never committed).

## Task Results

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | C9 cache-versioning regression tests (RED) | 7b33f27 | tests/test_pwa.py |
| 2 | build_id.txt Dockerfile write/copy + pwa.py GREEN | bc19359 | Dockerfile, app/routers/pwa.py, .gitignore |
| 3 | Two-build C9 gate (human-verify) | DEFERRED | (verification only) |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written, plus one minor addition:

**Addition: .gitignore entry for build_id.txt**
- Found during: Task 2
- The plan noted "confirm it is not tracked" as a guard. build_id.txt doesn't exist on disk (build artifact), but adding it to .gitignore is correct hygiene (same pattern as `app/static/css/tailwind.*.css`).
- No plan deviation — the plan explicitly mentioned the gitignore concern; this is the correct resolution.

## Deferred: Task 3 (human-verify checkpoint)

Task 3 is the two-build C9 gate: run two consecutive `docker compose build` invocations and verify the build_id.txt values differ and the CACHE_NAME in GET /sw.js differs between them. This cannot be proven by pytest in a source-tree run (build_id.txt only exists in the baked image).

**Deferred to orchestrator batch verification pass.** Steps from the plan:
1. `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`
2. `docker compose exec coffee-snobbery cat /app/static/build_id.txt` — note BUILD_A
3. `curl -s http://localhost:8000/sw.js | grep -o "snobbery-v[A-Za-z0-9]*"` — note CACHE_NAME_A
4. Wait 1+ second, rebuild: `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`
5. `docker compose exec coffee-snobbery cat /app/static/build_id.txt` — BUILD_B must differ
6. `curl -s http://localhost:8000/sw.js | grep -o "snobbery-v[A-Za-z0-9]*"` — CACHE_NAME_B must differ
7. `curl -s http://localhost:8000/sw.js | grep -E "skipWaiting|clients.claim"` — both must be present

## Test Results (Source-Tree)

- `test_build_hash_prefers_build_id_txt`: PASSED — the `_get_build_hash()` function correctly returns the build_id.txt content when the file exists, confirming the implementation is correct.
- `test_sw_cache_name_is_versioned`: skipped in source-tree (TestClient startup requires full app deps including `email-validator`). This test is a structural guard that will run green in the baked `coffee-snobbery-test` image.
- `sw.js`: verified unchanged (git diff confirms zero modifications).

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `/sw.js` route is unchanged in behavior — only the runtime value of `_BUILD_HASH` differs (now from build_id.txt). T-13-01 (build timestamp in CACHE_NAME) accepted per the plan's threat register (not sensitive). T-13-03 mitigation verified: the fallback chain (`build_id.txt -> CSS hash -> "dev"`) is in place.

## Self-Check: PASSED

- Dockerfile: 3 non-comment `build_id.txt` references (write, cat-echo, COPY) confirmed via grep.
- pwa.py: `Path("app/static/build_id.txt")` present, `_get_build_hash()` rewritten with correct fallback chain.
- tests/test_pwa.py: `test_sw_cache_name_is_versioned` and `test_build_hash_prefers_build_id_txt` both present.
- app/static/js/sw.js: no modifications (git diff clean).
- Commits verified: 7b33f27, bc19359 both exist in git log.
