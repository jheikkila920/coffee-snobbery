---
phase: 12-hardening-tests
verified: 2026-05-23T22:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
orchestrator_confirmation:
  note: "The two human_verification items were EXECUTED by the execute-phase orchestrator (docker access) from the final committed + freshly-built test image, both GREEN. Status raised human_needed -> passed; score 4/5 -> 5/5. The e2e gate also passed John's blocking human-verify checkpoint approval during execution."
  confirmed: 2026-05-24T00:00:00Z
  results:
    - test: "docker compose run --rm coffee-snobbery-test (non-e2e canonical gate, SNOB_CI=1)"
      result: "PASS — 939 passed, 2 skipped (the two expected architectural skips), 10 xfailed, 0 Tailwind-missing skips"
    - test: "docker compose --profile test run --rm tests/e2e/ (SNOB_E2E_BASE_URL -> a fresh virgin app)"
      result: "PASS — 10 passed (5 assertions x 375x667 + 390x844)"
human_verification: []
---

# Phase 12: Hardening + Tests Verification Report

**Phase Goal:** Ship-readiness gate. Pytest smoke covers the acceptance-criteria happy path end-to-end. Unit tests pin the load-bearing services (ai_service signature + provider fallback under respx, encryption MultiFernet round-trip + rotation, analytics queries against a seeded DB, CSRF middleware positive + negative). Playwright responsive smoke runs at 375x667 and 390x844 and asserts the brew form is usable, the home page cards stack vertically, and no input triggers iOS-style focus zoom. CI grep test forbids |safe in templates/pages/. CSP audit confirms no inline scripts without nonce. README + .env.example + NGINX server-block example are publishable.

**Verified:** 2026-05-23T22:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | pytest runs green inside the web container; smoke covers setup -> create coffee -> create equipment -> create recipe -> log session -> home renders all sections incl. AI cold-start | ? HUMAN | `tests/test_happy_path_smoke.py` implements the full 9-step chain (setup, roaster, coffee, brewer, grinder, kettle, recipe, brew session, GET /). SNOB_CI=1 enforces fail-not-skip for Postgres and Tailwind. Orchestrator reports 939 passed — cannot independently rerun inside docker on this host. |
| 2 | Unit tests pass for ai_service.py (signature, provider fallback under respx, citation projection, manual-refresh throttle), encryption.py (round-trip + MultiFernet rotation), analytics.py (top coffees, preference profile, sweet spots, roast freshness vs seeded DB), CSRF middleware (positive + negative) | ✓ VERIFIED | All four unit test files exist and are substantive: `tests/services/test_ai_service.py` (1256 lines, covers citation projector, URL verifier, fallback predicates, lock identity, throttle eviction, three-tier fallback, regenerate entry point, equipment rec, paste-rank); `tests/services/test_encryption.py` (198 lines, 6 test cases covering round-trip, MultiFernet rotation, unknown-key rejection, startup-check fail/ok, fingerprint stability); `tests/services/test_analytics.py` (807 lines, real-DB tests for top coffees, preference profile, flavor descriptors, roast freshness, sweet spots, recent brews, unrated coffees, cold-start counts, all-unrated edge case, signature determinism); `tests/middleware/test_csrf.py` (182 lines, includes `test_forged_token_rejected` as Phase 12 negative path). All use real fixtures with seed data, not mocks for DB tests. |
| 3 | Playwright responsive smoke at 375x667 + 390x844 asserts: bottom nav present+functional, brew form usable w/o horizontal scroll, photo upload control present, home cards stack vertically, font-size >= 16px on every input/select/textarea (no iOS zoom) | ? HUMAN | `tests/e2e/test_responsive_smoke.py` implements all 5 assertion classes parametrized over both viewports (10 tests total). `tests/e2e/conftest.py` provides session-scoped browser, auth seeding, and viewport parametrization. Excluded from CI (`--ignore=tests/e2e`). Orchestrator reports 10 passed — cannot independently rerun without live stack. |
| 4 | CI grep test fails build if \|safe under templates/pages/; CSP audit confirms every \<script\>/\<style\> carries a nonce and no unsafe-eval/unsafe-inline outside the documented docs/decisions/ trade-off | ✓ VERIFIED | `tests/ci/test_no_unsafe_jinja.py` scans all of `app/templates/` (W-02, wider than pages/ only) for `\|safe`, `hx-on:`, `hx-vals='js:'`, `hx-headers='js:'`. `tests/ci/test_csp_nonce.py` asserts every `<script>`/`<style>` tag carries a nonce and no `unsafe-eval`/`unsafe-inline` literals appear in templates. Both files now anchor to repo root via `Path(__file__).resolve().parents[2]` (WR-05 fix applied to test_csp_nonce.py and test_no_credential_dump.py). NOTE: `test_no_unsafe_jinja.py` still uses `Path("app/templates")` (relative) — this works in CI (CWD=repo root on Actions) and docker (CWD=/app, repo at /app, so /app/app/templates exists), but would silently collect zero cases if run from `tests/` or `tests/ci/` subdirectories by a developer. No actual \|safe usage found in any template (grep confirmed). CSP trade-off documented in `docs/decisions/0001-csp-strict-no-unsafe-eval.md`. |
| 5 | README publishable: NGINX block (X-Forwarded-Proto, Strict-Transport-Security, Cache-Control: no-cache on /sw.js), .env.example hints, single-uvicorn-worker (re-stated), backup restore runbook, iOS Wake-Lock-fallback caveat | ✓ VERIFIED | README.md contains: NGINX server block with `X-Forwarded-Proto $scheme`, `X-Forwarded-For`, `Strict-Transport-Security "max-age=63072000; includeSubDomains"`, explicit `location = /sw.js` block with Cache-Control: no-cache comment; `.env.example` has all required variables with generation hints (DATABASE_URL, POSTGRES_USER/PASSWORD/DB, APP_SECRET_KEY, APP_ENCRYPTION_KEY, TRUSTED_PROXY_IPS, APP_TIMEZONE, BACKUP_RETENTION_DAYS, LOG_LEVEL); single-worker warning documented in 3 places with audit grep; backup restore runbook (`psql < dump.sql` + `tar -xzf photos.tar.gz`); iOS Wake Lock section documents silent-audio fallback. README correctly states "Tailwind CSS (standalone CLI v3.4.17)" (WR-01 fix applied). |

**Score:** 3/5 truths independently verified; 2/5 require human confirmation (test gate execution)

### Anti-Hollow-Green Gate (D-02) Status

| Check | Finding | Status |
|-------|---------|--------|
| `_CI_MODE` read from `SNOB_CI` env var | `tests/conftest.py:40` — `_CI_MODE = os.environ.get("SNOB_CI") == "1"` | ✓ VERIFIED |
| `_require_postgres` fails under SNOB_CI=1 | `tests/conftest.py:50-53` — `pytest.fail(...)` when `_CI_MODE` | ✓ VERIFIED |
| `app` fixture fails (not skips) on missing Tailwind under SNOB_CI=1 | `tests/conftest.py:117-119` — RuntimeError branch checks `_CI_MODE` | ✓ VERIFIED (WR-02 fixed) |
| `app` fixture fails (not skips) on ImportError under SNOB_CI=1 | `tests/conftest.py:121-123` — ImportError branch also checks `_CI_MODE` | ✓ VERIFIED |
| `client` fixture routes DB failure through `_require_postgres` | `tests/conftest.py:149-151` — `_require_postgres(...)` called on connection error | ✓ VERIFIED |
| No source bind-mount in compose test profile | `docker-compose.yml:69-100` — comment explicitly forbids bind-mount; no `volumes: - .:/app` | ✓ VERIFIED |
| Test DB isolation guard | `tests/conftest.py:71-84` — rewrites DATABASE_URL to `*_test` database name | ✓ VERIFIED |
| Safety interlock (refuses non-test DB) | `tests/conftest.py:354-363` — `"test" not in _active_db.lower()` guard in `fresh_db` | ✓ VERIFIED |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_happy_path_smoke.py` | TEST-01 smoke: 9-step chain | ✓ VERIFIED | 342 lines, full chain implementation |
| `tests/services/test_ai_service.py` | TEST-02: ai_service unit tests | ✓ VERIFIED | 1256 lines, comprehensive coverage |
| `tests/services/test_encryption.py` | TEST-03: encryption unit tests | ✓ VERIFIED | 198 lines, 6 test rows from validation map |
| `tests/services/test_analytics.py` | TEST-04: analytics unit tests | ✓ VERIFIED | 807 lines, real-DB with seeded data |
| `tests/middleware/test_csrf.py` | TEST-05: CSRF positive + negative | ✓ VERIFIED | 182 lines, includes forged-token negative |
| `tests/e2e/test_responsive_smoke.py` | TEST-06: Playwright responsive | ✓ VERIFIED | 285 lines, 5 test classes × 2 viewports |
| `tests/e2e/conftest.py` | E2e fixtures + auth seeding | ✓ VERIFIED | 298 lines, session-scoped browser + auth |
| `tests/ci/test_csp_nonce.py` | CSP nonce audit | ✓ VERIFIED | Anchored to repo root (WR-05 fixed) |
| `tests/ci/test_no_unsafe_jinja.py` | \|safe ban CI grep | ✓ VERIFIED | Exists and is substantive (relative path is a dev ergonomics warn, not a CI failure) |
| `tests/ci/test_no_credential_dump.py` | model_dump credential audit | ✓ VERIFIED | Anchored to repo root (WR-05 fixed) |
| `tests/conftest.py` | Shared fixtures + SNOB_CI gate | ✓ VERIFIED | 760 lines, full D-02 implementation |
| `.github/workflows/ci.yml` | GitHub Actions CI | ✓ VERIFIED | Postgres service, Tailwind build, SNOB_CI=1, --ignore=tests/e2e |
| `Dockerfile` (dev stage) | Multi-stage with dev/test target | ✓ VERIFIED | `FROM runtime AS dev` with pytest + Playwright + chromium |
| `docker-compose.yml` (test profile) | compose test profile | ✓ VERIFIED | `profiles: [test]`, SNOB_CI=1, no bind-mount |
| `requirements-dev.txt` | Dev dependencies pinned | ✓ VERIFIED | pytest>=9.0,<10; pytest-asyncio>=1.2,<2; respx; playwright>=1.59,<2 |
| `README.md` | Publishable documentation | ✓ VERIFIED | NGINX block, .env.example, worker, restore runbook, Wake Lock caveat |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/conftest.py` | `app.main` | lazy import in `app` fixture | ✓ WIRED | Import inside fixture body with CI-mode fail guard |
| `tests/conftest.py` | `app.db.engine` | `fresh_db` + `_reset_catalog_tables` | ✓ WIRED | Both fixtures use engine for DB resets |
| `tests/test_happy_path_smoke.py` | `client` fixture | function parameter | ✓ WIRED | `test_happy_path_full_chain(client)` |
| `tests/services/test_ai_service.py` | `app.services.ai_service` | lazy import per test | ✓ WIRED | Direct import in each test function |
| `tests/services/test_encryption.py` | `monkeypatched_app_encryption_key` | conftest fixture | ✓ WIRED | Multiple tests use the fixture |
| `tests/services/test_analytics.py` | `app.db.SessionLocal` | `SessionLocal()` context manager | ✓ WIRED | Each test opens its own session |
| `tests/middleware/test_csrf.py` | `app.csrf.csrf_middleware_kwargs` | import sentinel | ✓ WIRED | `test_forged_token_rejected` builds minimal Starlette app |
| `.github/workflows/ci.yml` | Tailwind build step | before pytest step | ✓ WIRED | Step ordering ensures CSS exists before pytest runs |
| `docker-compose.yml` test profile | `Dockerfile` dev stage | `target: dev` | ✓ WIRED | `build.target: dev` explicitly sets the stage |
| CI workflow | `SNOB_CI=1` | env in pytest step | ✓ WIRED | `SNOB_CI: "1"` in Pytest full suite step env |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| TEST-01 | Pytest smoke: setup → coffee → equipment → recipe → session → home | ✓ SATISFIED | `tests/test_happy_path_smoke.py:73-341` — 9-step chain |
| TEST-02 | Unit tests for ai_service.py (signature + provider fallback under respx) | ✓ SATISFIED | `tests/services/test_ai_service.py` — citation projector, URL verifier, fallback predicates, throttle, three-tier fallback, regenerate entry point |
| TEST-03 | Unit tests for encryption.py (round-trip + MultiFernet rotation) | ✓ SATISFIED | `tests/services/test_encryption.py` — 6 validation-map rows covered |
| TEST-04 | Unit tests for analytics.py against seeded DB | ✓ SATISFIED | `tests/services/test_analytics.py` — top coffees, preference profile, sweet spots, roast freshness, recent brews, unrated coffees, cold-start counts, all-unrated edge case, signature determinism |
| TEST-05 | Unit tests for CSRF middleware (positive + negative) | ✓ SATISFIED | `tests/middleware/test_csrf.py` — `test_valid_token` (positive), `test_forged_token_rejected` (negative), 2 xfail tests document known TestClient limitations |
| TEST-06 | Playwright responsive smoke at 375x667 and 390x844 | ✓ SATISFIED | `tests/e2e/test_responsive_smoke.py` — 5 assertion classes × 2 viewports; local-only, excluded from CI |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/ci/test_no_unsafe_jinja.py` | 41 | `TEMPLATES_DIR = Path("app/templates")` — relative path, not anchored to `Path(__file__).resolve().parents[2]` | WARNING | Silently collects zero test cases if run from `tests/ci/` or `tests/` subdirectory by a developer. Not a CI risk (CI runs from repo root; docker test runs from /app which has /app/app/templates). The WR-05 fix from c67942b was applied to test_csp_nonce.py and test_no_credential_dump.py but missed this file. |

No `TBD`, `FIXME`, or `XXX` debt markers found in Phase 12 test files. No unreachable stubs.

### Code-Review Warnings Resolution

| Warning | Resolution | Verified |
|---------|------------|---------|
| WR-01: README said Tailwind v4, code ships v3.4.17 | Fixed in c67942b: README now says "Tailwind CSS (standalone CLI v3.4.17)" in both stack list and prerequisites | ✓ |
| WR-02: `app` fixture skipped even under SNOB_CI=1 when Tailwind missing | Fixed in c67942b: both RuntimeError and ImportError paths now check `_CI_MODE` and `pytest.fail()` | ✓ |
| WR-03: `_require_postgres_hard` dead code, never called | Fixed in c67942b: removed the dead helper; client fixture routes DB failures through `_require_postgres` which already has SNOB_CI=1 enforcement | ✓ |
| WR-04: `pytest-asyncio` unpinned | Fixed in c67942b: pinned to `>=1.2,<2` in requirements-dev.txt | ✓ |
| WR-05: CWD-relative Path in CI security tests | Partially fixed in c67942b: test_csp_nonce.py and test_no_credential_dump.py now use `Path(__file__).resolve().parents[2]`. test_no_unsafe_jinja.py still has relative Path (see Anti-Patterns above). | PARTIAL |

### Human Verification Required

#### 1. Full non-e2e test gate execution

**Test:** Build the dev image and run: `docker compose build coffee-snobbery-test && docker compose run --rm coffee-snobbery-test`

**Expected:** 939 passed, 2 skipped, 10 xfailed. The 2 skips must be exactly:
- `tests/middleware/test_session.py::test_orphaned_session_fail_closed` (FK CASCADE obviates the test)
- `tests/services/test_sessions.py::test_regenerate` (async db_session deferred to Phase 7)

Any count above 2 skipped indicates hollow-green. Any failure (other than xfail) blocks ship.

**Why human:** Requires the docker compose stack with a running Postgres 16 container and a built dev image containing baked Tailwind CSS. Cannot be run on this host.

#### 2. Playwright e2e responsive smoke

**Test:** With the compose stack running on http://127.0.0.1:8080, run: `docker compose run --rm coffee-snobbery-test tests/e2e/ -rs`

**Expected:** 10 passed (5 test cases × 2 viewports: 375x667 + 390x844):
- `TestBottomNav::test_bottom_nav_present` — nav element present, y > 70% of viewport height
- `TestBrewForm::test_brew_form_no_horizontal_scroll` — scrollWidth <= clientWidth on /brew/new
- `TestBrewForm::test_input_font_size_no_ios_zoom` — all visible inputs have computed font-size >= 16px
- `TestPhotoUpload::test_photo_upload_control_present` — input[capture='environment'] found on coffee detail
- `TestHomeCards::test_home_cards_stack_vertically` — no horizontal scroll on /

**Why human:** Requires Playwright Chromium and a live app instance. Excluded from CI intentionally (D-06).

### Gaps Summary

No blocking gaps. The phase goal is substantively achieved: all six TEST-01..06 requirements have real, substantive, wired test implementations. The SNOB_CI=1 anti-hollow-green gate is properly wired. The README is publishable. The CI pipeline is functional.

One informational finding: `test_no_unsafe_jinja.py` was not updated with the WR-05 repo-root path anchor applied to the other two CI test files. This is a developer-ergonomics issue (not a CI risk), but represents an incomplete application of the WR-05 fix.

Two human confirmations are required to reach `passed` status: the orchestrator-reported test results (939 passed, 2 skipped, 10 xfailed) and the Playwright e2e results (10 passed) cannot be independently verified without running the docker stack.

---

_Verified: 2026-05-23T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
