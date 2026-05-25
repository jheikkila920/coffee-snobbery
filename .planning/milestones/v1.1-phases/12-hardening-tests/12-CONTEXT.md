# Phase 12: Hardening + Tests - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

The final ship-readiness gate. 6 requirements: TEST-01..06.

**Critical framing for downstream agents: this is an AUDIT + GAP-FILL phase, not
a from-scratch test build.** Phases 0-11 each shipped Wave 0 test scaffolding
plus real tests, so TEST-02..05 are *largely already implemented*. Do NOT
re-create existing coverage. Verify what exists, fill the named gaps, and stand
up the ship-gate plumbing.

What ALREADY exists (do not rebuild — verify/extend only):
- Service unit tests: `tests/services/test_ai_service.py`, `test_encryption.py`,
  `test_analytics.py`, `test_settings.py`, `test_credentials.py`,
  `test_analytics_perf.py`.
- CSRF: `tests/middleware/test_csrf.py`, `test_csrf_form_shim.py`.
- `|safe` grep (HX-6): `tests/ci/test_no_unsafe_jinja.py`.
- CSP header presence: `tests/middleware/test_security_headers.py`; autoescape:
  `tests/templates/test_autoescape.py`.
- Doc tests: `tests/docs/test_readme_nginx.py`, `tests/test_env_example.py`,
  `tests/test_no_direct_env.py`.
- ~70 test files total across phases 0-11.

What is a GENUINE gap / net-new work for this phase:
- **TEST-01 full happy-path smoke** — `tests/test_phase02_smoke.py` only covers
  setup → login → home. The chain `create coffee → equipment → recipe → log
  session → home renders all sections (incl. AI cold-start)` does not exist as
  one smoke test.
- **TEST-06 Playwright** — zero playwright in the repo (not in `requirements*`,
  no config). Fully net-new.
- **SEC-6 `model_dump()` grep** on `ApiCredential` — promised in Phase 3 notes,
  not written (`tests/ci/` contains only the `|safe` test today).
- **Scripted CSP audit** — header presence is tested; the template-level "every
  `<script>`/`<style>` carries a nonce, no `unsafe-*`" audit is not.
- **Full-suite green** — blocked by T-INFRA-1 (cross-module isolation
  pollution); the suite currently only runs clean per-phase-isolated.
- **README / .env.example / NGINX** publishable (criterion #5) — partially
  tested; restore runbook + single-worker restatement + iOS wake-lock caveat +
  /sw.js Cache-Control note are gaps.
- **Ship-gate plumbing** — reproducible test runtime (dev image + compose
  profile) and CI (no `.github/workflows` exists yet).

Out of scope (locked elsewhere / deferred):
- Full per-router test coverage — PROJECT Out of Scope ("v1 is smoke + critical
  paths only"). Do NOT expand into exhaustive route coverage.
- New product features or behavior changes — this phase tests and documents what
  Phases 0-11 shipped; it does not add capabilities.
- The G-01 VPS-volume `chown` deploy fix (STATE Deferred Items) — a deploy-time
  ops task, adjacent but NOT folded into this phase (see Deferred Ideas).

</domain>

<decisions>
## Implementation Decisions

### Green gate + full-suite isolation (criterion #1, TEST-01)

- **D-01: Fix root-conftest isolation so full `pytest tests/` runs green as one
  batch.** This is the only honest reading of criterion #1 ("`pytest` runs green
  inside the web container"). STATE's T-INFRA-1 deferred item explicitly said
  "defer to a dedicated test-hygiene task" — **this phase IS that task.** Root
  cause is documented in T-INFRA-1: (a) the autouse `fresh_db` wipes only
  `users` + `sessions`, never `coffees`/`brew_sessions`, so a 2nd full run trips
  phase_04 `DELETE FROM coffees` (RESTRICT FK); (b) `test_setup_concurrent_race`
  fails in full-suite (Phase 3 `app_settings` in-memory cache for
  `setup_completed` not invalidated between tests). Fix = root-conftest teardown
  that TRUNCATEs the catalog tables + clears the settings cache between modules.
  Memory `full-suite-test-isolation-gaps` records the baseline: a clean full run
  = ~630 pass with only `test_setup_concurrent_race` failing — close that one
  too as part of this work.

- **D-02: The ship gate fails on UNEXPECTED skips — "green" must not be hollow.**
  Run the gate with `-rs` (report skip reasons). In the container gate,
  critical-path tests (the TEST-01 smoke, the load-bearing service tests, CSRF)
  must hard-require Postgres so a skip becomes a FAILURE, not a silent pass. The
  conftest's pervasive `try/except ImportError → pytest.skip` and
  `_postgres_reachable() → skip` patterns are convenient for host-only unit runs
  but dangerous as a ship gate. Direct evidence this has bitten the project:
  memories `tests-pass-by-skip-mask-green` and `test-nav-require-wired-skip-guard`
  (`tests/test_nav.py` wraps all 5 tests in a `_require_nav_wired()` skip guard —
  latent skip-as-green). Planner decides the exact mechanism (a skip-budget
  assertion, an env flag like `SNOB_CI=1` that flips skips to failures on the
  critical path, or an allowlist), but the OUTCOME is locked: an unexpected skip
  fails the container/CI gate.

### Test runtime + CI (criterion #1 reproducibility)

- **D-03: Add a Dockerfile dev/test multi-stage target + a compose `test`
  profile.** `docker compose run --rm test` runs the whole gate in one command
  (full pytest `-rs`, grep tests; Playwright as a separate invocation per D-06).
  The target bakes `requirements-dev.txt` (pytest>=9,<10, pytest-asyncio, httpx,
  respx, + playwright per D-05). This RETIRES the manual
  `docker compose exec ... pip install --user pytest ...` + `docker compose cp`
  flow documented in CLAUDE.md (flagged there as deferred ops). Beware the
  Windows `docker compose cp dir/` nesting footgun (memory
  `docker-cp-into-container-nesting`) — the baked dev image sidesteps it
  entirely. Keep the prod image unchanged (pytest stays OUT of the runtime
  stage).

- **D-04: GitHub Actions full gate on push/PR.** A workflow runs `ruff` (format
  + lint, warnings-as-errors per CLAUDE.md) + the grep tests (`|safe`,
  `model_dump`, CSP) + full `pytest -rs` against a **Postgres 16 service
  container**. The remote already exists (`jheikkila920/coffee-snobbery`); deploy
  stays git pull + docker build on the VPS (Actions is a regression net, NOT a
  deploy pipeline). The Actions job and the local compose `test` profile should
  share the same dev image / dependency source to avoid drift. The test DB
  contract is already isolation-safe: conftest forces a `<db>_test` sibling DB
  and refuses to mutate any non-`*test*` database — CI must set
  `DATABASE_URL`/`POSTGRES_*` so that forcing resolves to the service container.

### Playwright responsive smoke (TEST-06, criterion #3, MX-1)

- **D-05: Real headless browser (Playwright chromium) against the running app,
  full assertion set.** Run at **375×667 and 390×844** and assert the
  criterion-#3 set: bottom nav present + functional, brew session form usable
  with **no horizontal scroll**, photo upload control present, home analytics
  cards stack vertically, and **computed font-size ≥16px on every
  input/select/textarea** (MX-1 — no iOS focus zoom). A real browser is required
  because computed styles + scroll/layout truth cannot come from a static check.
  Target the app over the compose stack (the `test` profile from D-03). Pin
  `playwright>=1.59,<2` per the tech-stack table.

- **D-06: Playwright is a LOCAL / pre-deploy ship-smoke only — NOT in GitHub
  Actions.** Keeps CI fast and stable (no browser install + app-stack
  orchestration + flakiness in Actions). pytest + grep tests still gate in
  Actions (D-04); the responsive smoke is a required manual step before deploy,
  run via the compose `test` profile. Document it in the README/runbook as part
  of the ship checklist.

### Hardening audits → permanent grep tests (criterion #4, SEC-6)

- **D-07: CSP + model_dump audits become permanent scripted grep tests under
  `tests/ci/`.** (a) CSP grep: scan `app/templates/` for `<script>`/`<style>`
  tags lacking a `nonce` and for `'unsafe-eval'`/`'unsafe-inline'` outside the
  documented trade-off in `docs/decisions/`. (b) SEC-6 grep: forbid
  `model_dump()` being called on `ApiCredential` (decrypted key must never enter
  a serializable model). Both follow the existing `tests/ci/test_no_unsafe_jinja.py`
  idiom so they run on every pytest invocation and gate in CI (D-04). The app's
  CSP posture (Alpine CSP build + nonce'd scripts, no inline `hx-on:`, per
  `docs/decisions/0001`) means the grep should pass clean — if it doesn't, that's
  a real finding to fix, not a test to loosen.

### Docs publishability (criterion #5, TEST coverage of docs)

- **D-08: Targeted README gap-fill against the already-tested sections — no full
  rewrite.** `tests/docs/test_readme_nginx.py` and `tests/test_env_example.py`
  already pin the NGINX server block and `.env.example` generation hints. Fill
  ONLY the remaining criterion-#5 gaps: the backup **restore runbook** (lift from
  CLAUDE.md), the **single-uvicorn-worker** restatement, the **iOS Wake-Lock
  fallback caveat** (Phase 11), and the **`/sw.js` `Cache-Control: no-cache`**
  NGINX note (PWA-7). Do not rewrite tested prose (avoids churn + keeps the doc
  tests green). KISS.

### Claude's Discretion (planner/researcher resolve with these defaults)

- **TEST-01 smoke construction** — build it as one end-to-end test
  (`setup → create coffee → create equipment → create recipe → log session →
  GET / renders all sections incl. AI cold-start state if applicable`). Reuse
  the `test_phase02_smoke.py` setup+CSRF idiom and the seeded fixtures in
  `tests/conftest.py`. It must be a HARD test (require Postgres per D-02), not a
  skip-on-missing-DB test.
- **D-01 teardown mechanism** — root-conftest session/module teardown that
  TRUNCATEs catalog + per-user tables and clears the `app_settings` cache;
  planner picks TRUNCATE list + ordering (respect the RESTRICT FK on
  `coffees`/`brew_sessions`). The existing `fresh_db` safety interlock ("test" in
  db name) pattern must be preserved.
- **D-02 skip-enforcement mechanism** — skip-budget assertion vs CI env flag vs
  allowlist; outcome (unexpected skip fails the gate) is locked.
- **Playwright auth + seeding** — how the smoke logs in and seeds the minimal
  data (coffee/recipe/session) to render the brew form + home cards; likely a
  programmatic `/setup` + form POSTs at test start, or a small seed step in the
  compose `test` profile. Planner's call.
- **CSP grep strictness** — exact regex for nonce-on-script/style and the
  unsafe-* allowlist tied to `docs/decisions/`; keep it strict enough to catch a
  real regression without false-positiving on the documented trade-off.
- **GitHub Actions matrix/caching detail** — single job is fine at this scale;
  Postgres 16 service container, Python 3.12, pip cache. Planner's call.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 12: Hardening + Tests" — goal, the 5 success
  criteria, and Notes (HX-6 `|safe` grep, SEC-1 CSP audit follow-through, MX-1
  Playwright zoom assertion, SEC-6 `model_dump()` grep). Final ship gate: "if any
  item slips, the project does not deploy."
- `.planning/REQUIREMENTS.md` — verbatim reqs TEST-01..06 (lines 159-164).
- `.planning/PROJECT.md` §"Testing" (smoke + critical-path units; full per-router
  coverage explicitly Out of Scope), §"Key Decisions" (test posture row;
  single-uvicorn-worker; HTMX 2.x; Tailwind standalone CLI; CSP nonce),
  §"Constraints" (mobile-first 375px hard rule; CSRF + security headers + CSP on
  every response).
- `.planning/STATE.md` — **T-INFRA-1** (Deferred Items: the full-suite isolation
  gap this phase fixes — D-01) and **G-01** (VPS chown deploy fix — adjacent,
  deferred, not folded). Carried research flags list.

### Code in this repo (read before implementing)
- `tests/conftest.py` — the env-var bootstrap, the `<db>_test` forcing + safety
  interlock, autouse `fresh_db` (the D-01 teardown extends this), seeded fixtures
  (`seeded_admin_user`, `seeded_regular_user`, `sync_db`, `async_client`,
  `monkeypatched_app_encryption_key`). The single most important file for D-01/D-02.
- `pyproject.toml` `[tool.pytest.ini_options]` — `addopts = "-x --tb=short"`
  (note `-x` stops at first failure; the audit/gate run wants `-rs` and likely
  drops `-x`), `asyncio_mode = "auto"`, `testpaths = ["tests"]`. The header
  comment literally states "CI YAML (GitHub Actions) is deferred to Phase 12"
  (D-04) and the `S`/`B`/`UP`/`I` ruff set "Phase 12 will tighten".
- `tests/test_phase02_smoke.py` — the setup+CSRF+session idiom the TEST-01 full
  smoke extends (currently auth-only).
- `tests/ci/test_no_unsafe_jinja.py` — the grep-test idiom D-07 follows.
- `tests/middleware/test_security_headers.py` — existing CSP **header** coverage
  (the D-07 CSP grep complements this at the template level).
- `tests/services/test_ai_service.py`, `test_encryption.py`, `test_analytics.py`
  — existing TEST-02/03/04 coverage to verify/extend, NOT rebuild.
- `tests/middleware/test_csrf.py`, `test_csrf_form_shim.py` — existing TEST-05.
- `tests/docs/test_readme_nginx.py`, `tests/test_env_example.py` — the tested doc
  sections D-08 must not break.
- `requirements-dev.txt` — dev dep source of truth (add playwright here per D-03);
  the Dockerfile dev target installs from it.
- `Dockerfile` — add the dev/test multi-stage target (D-03); keep the prod
  runtime stage pytest-free.
- `docker-compose.yml` — add the `test` profile (D-03); two-service stack
  (`coffee-snobbery`, `coffee-snobbery-db`) + named volumes are invariant.
- `app/services/credentials.py` + `app/models/api_credential.py` — the SEC-6
  `model_dump()` grep target (verify the decrypted key never reaches a Pydantic
  model).
- `app/templates/` — the CSP grep scan target (D-07); base.html load order
  (Alpine CSP build before core), `docs/decisions/0001`.
- `entrypoint.sh` — runs `alembic upgrade head` on container start (the gate's
  test DB provisioning mirror lives in conftest `_provision_test_db`).
- `README.md` — the D-08 gap-fill target.

### Operational + spec
- `CLAUDE.md` — "Run tests" section (the manual pip-install flow D-03 replaces;
  the `docker compose cp` fast-iteration note), "Restore from backup" runbook
  (source for the D-08 README restore section), "Code conventions" (ruff format +
  `ruff check` warnings-as-errors → D-04), "Architectural invariants" (CSRF/CSP/
  security headers on every response; mobile-first 375px → TEST-06; single-worker;
  reverse-proxy aware), "Things to never do silently" (don't disable CSRF/CSP;
  don't log keys → SEC-6).
- `docs/decisions/0001*` — the Alpine CSP-build / eval-free decision the D-07 CSP
  grep validates against.

### Prior phase context (decisions this phase verifies/depends on)
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — MultiFernet rotation
  test posture (TEST-03 already implemented) + the SEC-6 `model_dump()` grep
  promise (D-07).
- `.planning/phases/11-pwa-mobile-polish/11-CONTEXT.md` — the iOS Wake-Lock
  caveat (D-08 README), the 375/390 viewports + 44px / no-horizontal-scroll
  patterns TEST-06 (D-05) asserts, the SW stale-cache note (memory
  `sw-stale-cache-confounds-ui-verify`).

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- **Playwright (Python)** `>=1.59,<2` — browser install in Docker, viewport
  config, `boundingBox`/computed-style assertions, headless run (D-05).
- **pytest** `>=9,<10` + **pytest-asyncio** + **respx** — already in use; confirm
  `-rs` + skip-reporting + any plugin for skip-budget enforcement (D-02).
- **GitHub Actions** — Postgres service container, Python setup, pip caching (D-04).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`tests/conftest.py` fixtures** — `seeded_admin_user`/`seeded_regular_user`
  (user + live signed-cookie session), `async_client` (ASGI httpx), `sync_db`,
  `monkeypatched_app_encryption_key` (Fernet reload), the `<db>_test` forcing +
  `_provision_test_db` + `fresh_db` autouse reset. The TEST-01 smoke (D-01) and
  the isolation teardown extend these directly.
- **`tests/ci/test_no_unsafe_jinja.py`** — the grep-test template the CSP +
  model_dump tests (D-07) clone.
- **`tests/test_phase02_smoke.py`** — the working setup → CSRF → session →
  authenticated-GET pattern the TEST-01 happy-path smoke builds on.
- **conftest test-DB safety interlock** ("test" in db name; refuse to mutate the
  live DB) — preserve it verbatim in the D-01 teardown.

### Established Patterns
- "CI grep test" idiom: a plain pytest under `tests/ci/` that scans source/
  templates and asserts a forbidden pattern is absent. `|safe` already done; CSP +
  `model_dump` join it (D-07).
- Per-phase test isolation is the project's *current* default; this phase
  upgrades it to whole-suite isolation (D-01) without removing the per-phase runs.
- ruff `format` + `check` (warnings-as-errors), mypy strict on signatures — CI
  enforces (D-04).
- Single uvicorn worker; APScheduler in-process — unchanged (no new runtime
  behavior this phase).

### Integration Points
- `Dockerfile` + `docker-compose.yml` — new dev/test stage + `test` profile
  (D-03); prod stage untouched.
- `.github/workflows/` (new) — the CI gate (D-04).
- `tests/conftest.py` — the isolation teardown + skip-enforcement seat (D-01/D-02).
- `tests/e2e/` (or similar, new) — the Playwright suite (D-05); excluded from the
  default Actions pytest run (D-06), invoked separately by the compose `test`
  profile / local runbook.
- `tests/ci/` — new CSP + model_dump grep tests (D-07).
- `README.md` — D-08 gap-fill.

</code_context>

<specifics>
## Specific Ideas

- **"Green" must be earned, not asserted.** John's #1 rule is honesty/accuracy;
  the whole shape of this phase reflects that — full-suite green over per-phase
  green (D-01), skips-fail-the-gate over skip-as-green (D-02). The two relevant
  memories (`tests-pass-by-skip-mask-green`, `full-suite-test-isolation-gaps`)
  are the evidence base; treat a green-but-mostly-skipped run as a FAILED gate.
- **Don't rebuild existing tests.** The biggest waste-risk here is an executor
  re-implementing TEST-02..05 from scratch. Verify coverage against the existing
  files first; only add the named gaps.
- **The grep should pass clean.** If the CSP/`model_dump` greps find violations,
  fix the source — do NOT relax the test (CLAUDE.md "never disable CSP", "never
  log keys").
- **CI is a net, not a deploy path.** Deploy stays git pull + docker build on the
  VPS; Actions exists to catch regressions on push.

</specifics>

<deferred>
## Deferred Ideas

- **G-01 VPS-volume `chown` deploy fix** (STATE Deferred Items, Phase 08) — the
  next VPS deploy needs a one-time `chown -R app:app /app/data` so backups +
  photos are writable on the pre-existing root-owned named volumes. This is a
  deploy-time ops task, NOT test/hardening scope. Note it in the README deploy
  runbook (D-08 touches the README anyway) but do not implement infra changes in
  this phase. Memory `vps-deploy-chown-data-volume`.
- **Full per-router test coverage** — PROJECT Out of Scope; expand only if
  regressions become a pattern post-ship.
- **`filterwarnings = ["error"]` (warnings-as-errors in pytest)** — proposed in
  Phase 1 Plan 01 and deferred; if the suite is clean under it, the planner MAY
  flip it as part of tightening, but it is not a phase requirement. Don't let it
  balloon the gate.
- **Playwright in GitHub Actions** — explicitly declined for v1 (D-06); revisit
  if the local pre-deploy smoke proves too easy to skip.
- **Manual UAT gate from Phase 11** (STATE Session Continuity) — the 375px
  search-sheet / debounce / p95 checks were the last Phase 11 gate; TEST-06
  (D-05) partially automates the responsive surface, but the Phase 11 manual UAT
  is its own item, not folded here.

### Reviewed Todos (not folded)
None — `todo.match-phase 12` returned zero matches; the one STATE pending todo
("inline add new coffee from the brew form") is Phase 4/5 catalog/brew domain,
not testing/hardening.

</deferred>

---

*Phase: 12-Hardening + Tests*
*Context gathered: 2026-05-23*
