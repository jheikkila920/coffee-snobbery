# Phase 12: Hardening + Tests - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-23
**Phase:** 12-hardening-tests
**Areas discussed:** Green gate + suite isolation, Test runtime + CI, Playwright (TEST-06), Hardening audits → tests vs ADR

---

## Green gate + suite isolation

### Q1: Definition of the "green" gate vs the T-INFRA-1 isolation gap

| Option | Description | Selected |
|--------|-------------|----------|
| Fix isolation, full suite green | Root-conftest teardown (TRUNCATE catalog + clear app_settings cache) so `pytest tests/` passes as one batch; honest reading of criterion #1; this phase is the deferred T-INFRA-1 task | ✓ |
| Per-phase isolated gate | Keep per-phase suites green + runbook; whole suite still can't run at once | |
| Full green except documented xfail | Fix cheap issues, xfail the stubborn ones with reasons | |

**User's choice:** Fix isolation, full suite green
**Notes:** Aligns with John's #1 honesty rule — a gate that can't run the whole suite isn't a real gate.

### Q2: Skip policy (preventing skip-as-green)

| Option | Description | Selected |
|--------|-------------|----------|
| Fail on unexpected skips | Run `-rs`; critical-path tests hard-require Postgres so a skip becomes a failure | ✓ |
| Allowlist + -rs | Run `-rs`, maintain known-skip allowlist, fail only on a new skip | |
| Just -rs, manual review | Surface skips, eyeball them, no enforcement | |

**User's choice:** Fail on unexpected skips
**Notes:** Backed by memories `tests-pass-by-skip-mask-green` and `test-nav-require-wired-skip-guard`.

---

## Test runtime + CI

### Q1: Reproducible test execution

| Option | Description | Selected |
|--------|-------------|----------|
| Dockerfile dev target + compose test profile | `docker compose run --rm test` runs the whole gate; retires manual pip-install + docker cp | ✓ |
| Keep manual pip-install flow | Document existing runbook; no new image/profile | |
| Multi-stage dev target only (no profile) | Reproducible image, less ergonomic invocation | |

**User's choice:** Dockerfile dev target + compose test profile

### Q2: CI posture

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub Actions full gate on push/PR | ruff + grep tests + full pytest vs Postgres service container | ✓ |
| In-container gate only, no Actions | Documented `docker compose run --rm test`; no Actions | |
| Actions: lint + grep only | Cheap checks in CI; full pytest stays local | |

**User's choice:** GitHub Actions full gate on push/PR
**Notes:** Remote already exists; deploy stays git pull + docker build on the VPS (Actions is a regression net, not a deploy pipeline).

---

## Playwright (TEST-06)

### Q1: How the responsive smoke runs

| Option | Description | Selected |
|--------|-------------|----------|
| Real headless browser vs running app | Chromium hits the live app at 375×667 + 390×844, full criterion-#3 assertion set incl. computed font-size ≥16px (MX-1) | ✓ |
| Real browser, minimal assertions | Browser, but only font-size + no-horizontal-scroll | |
| Lighter static assertion (no browser) | Grep/parse Tailwind; guts TEST-06 — not recommended | |

**User's choice:** Real headless browser vs running app

### Q2: Playwright in CI?

| Option | Description | Selected |
|--------|-------------|----------|
| Local/in-container ship-smoke only | Runs via compose test profile pre-deploy; not in Actions | ✓ |
| Include in GitHub Actions too | Actions installs browsers + runs the app + Playwright on push | |

**User's choice:** Local/in-container ship-smoke only
**Notes:** Keeps CI fast/stable; pytest + grep still gate in Actions.

---

## Hardening audits → tests vs ADR

### Q1: CSP audit + SEC-6 model_dump enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Permanent grep tests | CSP nonce/unsafe-* grep + SEC-6 model_dump grep under tests/ci/; matches test_no_unsafe_jinja.py idiom | ✓ |
| One-time manual audit + ADR | Audit once, record in docs/decisions/; only model_dump as a test | |
| Both: grep tests + CSP ADR | Scripted tests + an ADR documenting CSP posture | |

**User's choice:** Permanent grep tests

### Q2: Docs publishability depth (criterion #5)

| Option | Description | Selected |
|--------|-------------|----------|
| Targeted gap-fill against tested sections | Fill restore runbook + single-worker + iOS wake-lock + /sw.js Cache-Control; don't rewrite tested prose | ✓ |
| Full README polish pass | Comprehensive rewrite; risks churn/scope creep | |
| Minimal — only what tests demand | Defer prose; leaves criterion #5 partially unmet | |

**User's choice:** Targeted gap-fill against tested sections

---

## Claude's Discretion

- TEST-01 full happy-path smoke construction (one e2e test, hard-require Postgres).
- D-01 teardown mechanism (TRUNCATE list/ordering, preserve the "test"-in-db-name interlock).
- D-02 skip-enforcement mechanism (skip-budget vs CI env flag vs allowlist; outcome locked).
- Playwright auth + seeding approach.
- CSP grep regex strictness + unsafe-* allowlist tied to docs/decisions/.
- GitHub Actions job detail (Postgres 16 service, Python 3.12, pip cache).

## Deferred Ideas

- G-01 VPS-volume chown deploy fix — deploy-time ops; note in README, don't implement here.
- Full per-router coverage — PROJECT Out of Scope.
- `filterwarnings = ["error"]` — optional tightening, not a requirement.
- Playwright in GitHub Actions — declined for v1.
- Phase 11 manual UAT gate — its own item, not folded.
