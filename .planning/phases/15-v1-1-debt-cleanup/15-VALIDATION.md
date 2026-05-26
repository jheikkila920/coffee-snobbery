---
phase: 15
slug: v1-1-debt-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `15-RESEARCH.md` § Validation Architecture. This phase is correctness +
> verification only — most automated coverage already exists; the remaining gaps are
> a CI double-run guard, a `test_setup_concurrent_race` fix, a verification ledger,
> and an interactive on-device human session.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x + pytest-asyncio |
| **Config file** | `pyproject.toml` / `pytest.ini` (existing) |
| **Quick run command** | `docker compose run --rm coffee-snobbery-test tests/ --ignore=tests/e2e -rs -x` |
| **Full suite command** | `docker compose run --rm coffee-snobbery-test tests/ --ignore=tests/e2e -rs --tb=short` |
| **Estimated runtime** | ~120s (estimate; 900+ unit/integration tests, e2e excluded) |

> Note: tests run in the baked test image (no source bind-mount) — rebuild or
> `docker compose cp` changed files before re-running. See CLAUDE.md test section.

---

## Sampling Rate

- **After every task commit:** Run quick command (`pytest tests/ --ignore=tests/e2e -rs -x`), plus `pytest tests/test_nav.py -rs` for DEBT-03 tasks
- **After every plan wave:** Run full suite command **twice against the SAME test DB** (the DEBT-02 residue-proof double-run — do NOT drop/recreate between runs)
- **Before `/gsd-verify-work`:** Full suite double-run must be green AND the on-device session complete AND the verification ledger written
- **Max feedback latency:** ~120s

---

## Per-Task Verification Map

> Task IDs are assigned during planning. Rows below are requirement-level; the planner
> maps each to concrete task IDs in the PLAN.md files.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | — | DEBT-01 | Container priv (EoP) | `exec gosu app` drops to UID 1000 before uvicorn; container unprivileged after startup | manual/smoke | `docker compose run --rm -u root coffee-snobbery stat -c '%u' /app/data` → `1000` | ✅ | ⬜ pending |
| TBD | TBD | — | DEBT-02 (run 1) | — | N/A | integration | `pytest tests/ --ignore=tests/e2e -rs` | ✅ | ⬜ pending |
| TBD | TBD | — | DEBT-02 (run 2, same DB) | — | residue surfaces on 2nd run if teardown leaks | integration | `pytest tests/ --ignore=tests/e2e -rs` (2nd invocation) | ✅ | ⬜ pending |
| TBD | TBD | — | DEBT-02 (race fix) | — | N/A | integration | `pytest tests/ -rs --tb=short --ignore=tests/e2e -k test_setup_concurrent_race` | ✅ needs fix | ⬜ pending |
| TBD | TBD | — | DEBT-03 (config_hub signout) | — | mobile sign-out form present | unit | `pytest tests/test_nav.py::test_config_hub_has_mobile_signout_form` | ✅ | ⬜ pending |
| TBD | TBD | — | DEBT-03 (home navbar) | — | navBar component on home | unit | `pytest tests/test_nav.py::test_authenticated_home_has_nav_bar_component` | ✅ | ⬜ pending |
| TBD | TBD | — | DEBT-03 (on-device) | — | nav + sign-out findable at 375px | manual | John on physical device | ❌ W0 (interactive) | ⬜ pending |
| TBD | TBD | — | DEBT-04 | — | each human-UAT item closed or re-deferred w/ reason | manual | interactive device session | ❌ W0 (interactive) | ⬜ pending |
| TBD | TBD | — | DEBT-05 | — | each `human_needed` resolved or re-deferred w/ reason | manual | interactive device session | ❌ W0 (interactive) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `15-VERIFICATION.md` — phase verification ledger scaffold for DEBT-04 / DEBT-05 / D-13 outcomes (close-with-evidence or re-defer-with-reason)
- [ ] CI double-run guard — append a second consecutive full-suite step to `.github/workflows` (same DB, no drop/recreate between runs)
- [ ] `test_setup_concurrent_race` fix lands in the existing test module (research points to `tests/routers/test_auth.py`; planner confirms exact location) — no new test files required

*Existing test infrastructure covers all automated requirements; Wave 0 work is ledger scaffolding + CI guard + the concurrent-race fix.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh deploy writes backups/photos with no manual `chown` | DEBT-01 | Requires a real fresh-volume deploy on the VPS | Deploy to clean volumes; confirm backup + photo write succeed; `stat -c '%u' /app/data` → `1000` |
| Persistent nav + identity + sign-out on every authenticated page | DEBT-03 | Visual + reachability at 375px on a real device | On physical device, every authenticated page shows nav, user identity, and a working sign-out |
| iOS bottom-nav safe-area fix (commit `982c0e6`) | DEBT-03 / D-13 | Cannot reproduce off-device | Confirm bottom nav clears the iOS home indicator on a physical device (folds into the same session) |
| Outstanding v1.1 human-UAT scenarios (Phases 01/02/07/10/11) | DEBT-04 | Human judgment / real device + live env | Execute each catalogued UAT item live; record close-with-evidence or re-defer-with-reason |
| Outstanding `human_needed` verifications | DEBT-05 | Human judgment / real env | Resolve each with evidence or re-defer with a written reason + target phase |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
