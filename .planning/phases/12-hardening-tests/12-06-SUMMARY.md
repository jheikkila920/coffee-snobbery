---
phase: 12-hardening-tests
plan: "06"
subsystem: testing
tags: [playwright, e2e, responsive, mobile, viewports, browser-testing]

# Dependency graph
requires:
  - phase: 12-05
    provides: dev/test Docker image with Playwright + chromium baked in

provides:
  - Playwright e2e responsive smoke suite under tests/e2e/ (TEST-06)
  - tests/e2e/conftest.py: session browser, viewport parametrization (375x667 + 390x844), auth seeding
  - tests/e2e/test_responsive_smoke.py: five criterion-#3 assertions x2 viewports = 10 test items
  - Local/pre-deploy ship gate per D-06 (excluded from CI via --ignore=tests/e2e)

affects: [12-07-ci-workflow, deploy-runbook]

# Tech tracking
tech-stack:
  added: [playwright (sync_api, browser/context/page), urllib.request (auth seed in test infra)]
  patterns:
    - session-scoped browser fixture + function-scoped parametrized viewport page
    - Playwright import guard (skip-clean when Playwright absent on host)
    - auth seeding via /setup then /login fallback with cookie injection into BrowserContext
    - session-scoped data seed fixture (coffee_detail_path) using temporary browser context

key-files:
  created:
    - tests/e2e/__init__.py
    - tests/e2e/conftest.py
    - tests/e2e/test_responsive_smoke.py
  modified:
    - pyproject.toml (add S110/S310 to per-file-ignores for tests/**)

key-decisions:
  - "Playwright import guard uses try/except at module level + session-scoped autouse skip fixture — never errors at collection on hosts without playwright"
  - "Auth seeding uses stdlib urllib (not httpx) to minimize hard deps in test infra; httpx is available in the dev image but this pattern works on both host and container"
  - "coffee_detail_path is session-scoped and uses a temporary browser context (not page_at_viewport) to avoid scope mismatch — seeds a coffee+bag once per session, skips photo test gracefully if seeding fails"
  - "test_home_cards_stack_vertically asserts no-horizontal-scroll (scrollWidth <= clientWidth) as the proxy for vertical stacking — more robust than fragile CSS class assertions against markup that evolves"
  - "bottom nav selector confirmed as nav[x-data='navBar'] from base.html line 236; md:hidden means visible at <768px (the test viewports)"
  - "pyproject.toml per-file-ignores extended with S110/S310 for all tests/**/*.py (e2e fixtures use urllib to localhost and swallow optional bag-creation errors)"

patterns-established:
  - "E2E fixture pattern: session browser + function viewport + session auth-seed + session data-seed"
  - "Playwright availability guard: try-import at module top + autouse session skip fixture"
  - "Photo upload test: seeds coffee+bag via page.request in a temporary context; skips if seeding fails"

requirements-completed: [TEST-06]

# Metrics
duration: 45min
completed: 2026-05-23
---

# Phase 12 Plan 06: Playwright Responsive Smoke (TEST-06) Summary

**Playwright chromium e2e smoke suite at 375x667 and 390x844 asserting nav, no-scroll, photo upload, home cards, and font-size >= 16px (MX-1) — 10 test items, local/pre-deploy only per D-06**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-23T00:00:00Z
- **Completed:** 2026-05-23T00:45:00Z
- **Tasks:** 2 of 3 (Task 3 is orchestrator-owned checkpoint — see below)
- **Files modified:** 4

## Accomplishments

- `tests/e2e/__init__.py` — package marker for the e2e suite
- `tests/e2e/conftest.py` — session browser, `base_url` (env `SNOB_E2E_BASE_URL`, default `http://127.0.0.1:8080`), `page_at_viewport` parametrized at 375x667 + 390x844, session auth seeding via `/setup` + `/login` fallback, Playwright import guard
- `tests/e2e/test_responsive_smoke.py` — five criterion-#3 assertions × 2 viewports = 10 test items: bottom nav, brew form no-scroll, input font-size, photo upload control, home cards no-scroll
- `python -m pytest tests/e2e/ --collect-only -q` collects 10 tests cleanly; skips entire suite when Playwright absent (SNOB_CI safe)

## Task Commits

1. **Task 1: Playwright e2e fixtures** - `55b63a3` (feat)
2. **Task 2: Responsive smoke assertions (TEST-06)** - `6052fb8` (feat)

## Files Created/Modified

- `tests/e2e/__init__.py` — empty package marker (D-05/TEST-06)
- `tests/e2e/conftest.py` — session browser + viewport page + auth seed + data seed fixtures
- `tests/e2e/test_responsive_smoke.py` — 5 test classes, 10 parametrized test items
- `pyproject.toml` — S110/S310 added to per-file-ignores for `tests/**/*.py`

## Decisions Made

- **Playwright guard:** try/except at module top plus a `scope="session"` autouse `_require_playwright` fixture. Collection never errors — the suite skips cleanly when Playwright is absent on the host. SNOB_CI is unaffected because CI excludes `tests/e2e/` entirely via `--ignore=tests/e2e`.
- **Auth seeding via urllib:** No hard dependency on httpx in the e2e conftest. The dev image has httpx but using stdlib `urllib.request` keeps the fixture portable. Falls back from `/setup` to `/login` (idempotent against pre-seeded stacks).
- **coffee_detail_path scope:** Session-scoped data seeding fixture creates a temporary `BrowserContext` (not reusing `page_at_viewport` which is function-scoped) to avoid pytest scope mismatch. Seeds a minimal coffee + bag via `page.request` using the auth session cookies.
- **Photo upload test:** `input[capture='environment']` lives inside `bag_row.html` which renders only when bags exist on a coffee detail page. The test skips gracefully (not fails) if data seeding returns `None` — the orchestrator's live verification step confirms the real pass.
- **Home cards stacking:** no-horizontal-scroll at 375/390px is the robust proxy for vertical stacking. DOM-structure assertions against the Tailwind grid classes would be fragile; scroll-width is the observable effect that matters.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Extended pyproject.toml per-file-ignores**
- **Found during:** Task 1 (ruff lint pass)
- **Issue:** ruff `S310` (urllib.request to localhost in test infra) and `S110` (intentional try-except-pass in data seed fixture) were flagged as errors. The existing `tests/**/*.py` ignore list only covered S101/S105/S106.
- **Fix:** Added S110 and S310 to the same `per-file-ignores` entry with explanatory comment.
- **Files modified:** `pyproject.toml`
- **Verification:** `ruff check tests/e2e/` passes with "All checks passed!"
- **Committed in:** `55b63a3` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical)
**Impact on plan:** Necessary linting hygiene, no behavior change, no scope creep.

## Issues Encountered

- Playwright quota exceeded on Context7 during API verification step. Used research from `12-RESEARCH.md` and `12-PATTERNS.md` which documented the Playwright 1.59 sync API patterns (browser/context/page lifecycle, `add_cookies`, `evaluate`, `bounding_box`, `wait_for_selector`) with sufficient specificity to write the fixtures correctly without the live documentation lookup.

## Task 3 Status: Orchestrator-Owned Live Verification Gate

**Task 3 is `type="checkpoint:human-verify"` and is intentionally NOT executed here.**

Per the plan objective and the execution instructions in the prompt, the Playwright live e2e smoke against the running compose stack MUST be run by the orchestrator/human against the actual deployed stack — not self-certified by the code generator that wrote the tests (generator self-evaluation is the blind spot D-06 guards against).

**What the orchestrator must do to close this plan:**

```bash
# 1. Bring up the stack
docker compose up -d

# 2. Run e2e smoke against the in-network app (compose test profile, Plan 12-05 image)
docker compose --profile test run --rm \
  -e SNOB_E2E_BASE_URL=http://coffee-snobbery:8000 \
  coffee-snobbery-test tests/e2e/ -rs --tb=short

# Or locally against the host bind (requires playwright installed):
python -m pytest tests/e2e/ -rs --tb=short
```

**Expected result:** 10/10 tests pass at both 375x667 and 390x844. If a font-size violation fires, it is a real MX-1 regression — fix the CSS, do not relax the test.

## User Setup Required

None for this plan. The e2e suite requires the live compose stack (Plan 12-05 dev image) which is the orchestrator's responsibility to bring up before running the human-verify checkpoint.

## Next Phase Readiness

- TEST-06 satisfied (code complete; live verification pending orchestrator checkpoint)
- Plan 12-07 (CI workflow) can proceed — it adds `--ignore=tests/e2e` to the Actions `pytest` call, which this plan's exclusion design already anticipates

---
*Phase: 12-hardening-tests*
*Completed: 2026-05-23*
