---
phase: 12
slug: hardening-tests
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-23
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `12-RESEARCH.md` §Validation Architecture. This phase IS the ship gate,
> so its own validation must honor D-01 (full-suite green) and D-02 (skips fail the gate).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`>=9.0,<10`) + pytest-asyncio + respx; Playwright (`>=1.59,<2`) for e2e |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (gate run drops `-x`, adds `-rs`) |
| **Quick run command** | `python -m pytest tests/ci/ -rs --tb=short` (grep tests; no Postgres; fast) |
| **Full suite command** | `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e` |
| **Playwright command** | `python -m pytest tests/e2e/ -rs --tb=short` (LOCAL / pre-deploy only — D-06) |
| **Estimated runtime** | ~60–120s full suite (Postgres-backed); <5s grep-only subset — confirm during execution |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ci/ -rs --tb=short` (grep tests, fast, no Postgres)
- **After every plan wave:** Run `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e`
- **Before `/gsd-verify-work`:** Full suite green under `SNOB_CI=1` (skips become failures, D-02) **AND** Playwright responsive smoke run locally (D-05/D-06)
- **Max feedback latency:** ~120 seconds (full suite)

---

## Per-Task Verification Map

*Populated after plans land (task IDs do not exist pre-planning). The requirement→test
map below is the authoritative source the per-task rows derive from; `/gsd-validate-phase`
fills the task-keyed table post-execution.*

| Req ID | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|--------|----------|------------|-----------|-------------------|-------------|--------|
| TEST-01 | Happy path: setup → coffee → equipment → recipe → session → home renders all sections | — | smoke/integration | `pytest tests/test_happy_path_smoke.py -rs -x` | ❌ W0 | ⬜ pending |
| TEST-02 | `ai_service` signature + provider fallback under respx | — | unit | `pytest tests/services/test_ai_service.py -rs` | ✅ verify | ⬜ pending |
| TEST-03 | `encryption` round-trip + MultiFernet rotation | T-12 (V6) | unit | `pytest tests/services/test_encryption.py -rs` | ✅ verify | ⬜ pending |
| TEST-04 | `analytics` queries (top coffees, profile, sweet spots, freshness) | — | unit/integration | `pytest tests/services/test_analytics.py tests/services/test_analytics_perf.py -rs` | ✅ verify | ⬜ pending |
| TEST-05 | CSRF middleware positive + negative | — | unit | `pytest tests/middleware/test_csrf.py tests/middleware/test_csrf_form_shim.py -rs` | ✅ verify | ⬜ pending |
| TEST-06 | Playwright 375×667 + 390×844: nav, no-scroll, photo control, cards stack, font ≥16px | — | e2e | `pytest tests/e2e/ -rs` (local) | ❌ W0 | ⬜ pending |
| D-01 | Full-suite isolation (cross-module catalog teardown; setup cache clear) | — | infrastructure | `pytest tests/ -rs --ignore=tests/e2e` all green | ❌ W0 | ⬜ pending |
| D-02 | Skip gate: `SNOB_CI=1` turns unexpected skips into failures | T-12 (Repudiation) | infrastructure | `SNOB_CI=1 pytest tests/ -rs --ignore=tests/e2e` | ❌ W0 | ⬜ pending |
| D-07a | CSP: every `<script>`/`<style>` carries a nonce; no `unsafe-*` | T-12 (XSS/Tampering) | static grep | `pytest tests/ci/test_csp_nonce.py -rs` | ❌ W0 | ⬜ pending |
| D-07b | SEC-6: no `model_dump()` on `ApiCredential` | T-12 (Info Disclosure) | static grep | `pytest tests/ci/test_no_credential_dump.py -rs` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_happy_path_smoke.py` — TEST-01 end-to-end smoke (hard-requires Postgres, D-02)
- [ ] Root `tests/conftest.py` — module-scoped catalog teardown (TRUNCATE `brew_sessions → bags → coffees` ordering, RESTRICT-FK aware; preserve `"test"`-in-db-name interlock) — D-01
- [ ] Root `tests/conftest.py` — `SNOB_CI` skip-enforcement hook (unexpected skip → failure) — D-02
- [ ] `tests/ci/test_csp_nonce.py` — clone `test_no_unsafe_jinja.py` idiom — D-07a
- [ ] `tests/ci/test_no_credential_dump.py` — D-07b
- [ ] `tests/e2e/__init__.py` + `tests/e2e/conftest.py` + `tests/e2e/test_responsive_smoke.py` — TEST-06
- [ ] `requirements-dev.txt` — add `playwright>=1.59,<2`
- [ ] `Dockerfile` — `dev`/`test` multi-stage target (prod stage stays pytest-free) — D-03
- [ ] `docker-compose.yml` — `test` profile (`docker compose run --rm test`) — D-03
- [ ] `.github/workflows/ci.yml` — ruff + grep + full `pytest -rs` against Postgres 16 service container — D-04

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Playwright responsive smoke before deploy | TEST-06 | Automated (Playwright) but LOCAL-only by decision D-06 (not in CI); a human must run it as the pre-deploy ship step | `docker compose run --rm test pytest tests/e2e/ -rs` (or documented runbook command) — must pass before VPS deploy |

*All other phase behaviors have automated verification in the suite or CI gate.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
