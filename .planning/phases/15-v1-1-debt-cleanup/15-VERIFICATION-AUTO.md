---
phase: 15-v1-1-debt-cleanup
verified: 2026-05-25T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
overrides_applied: 0
---

# Phase 15: v1-1-debt-cleanup -- Auto-Verifier Assessment

**Phase Goal:** All v1.1 carried debt is closed -- the base is clean and verified before any new feature work begins.
**Verified:** 2026-05-25 (auto-verifier run)
**Status:** PASSED
**Re-verification:** No -- initial verification

---

## Verification Approach

Per the phase instructions, this auto-verifier does NOT overwrite or modify `15-VERIFICATION.md` (the human-authored closure ledger). Its role is threefold:

1. Confirm the must_have-cited code/test changes physically exist in the codebase and are substantive.
2. Cross-check the ledger covers every catalogued item with no `pending` remaining.
3. Confirm requirement IDs DEBT-01..05 are accounted for in PLAN frontmatters and REQUIREMENTS.md.

The human ledger (`15-VERIFICATION.md`) is treated as primary evidence for all device-session and UAT outcomes that cannot be programmatically verified. Deferred items with written reasons and a named target phase (Phase 15.1) are treated as legitimate closure under D-12 -- not gaps.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A fresh deploy writes backups and photos without a manual `chown` (G-01 fixed in `entrypoint.sh`) | VERIFIED | `entrypoint.sh` contains the `stat -c '%u' /app/data` guard (line 25) and `exec gosu app uvicorn` (line 42); `Dockerfile` has `gosu` on the existing apt-get line (line 85) and `USER app` is absent from the runtime stage (only appears once, in the dev stage at line 160). Commits 3cb5306 + 25996c5 confirmed in git log with correct author and diff scope. |
| 2 | `pytest tests/` runs green twice in a row with zero cross-module isolation failures | VERIFIED | `tests/routers/test_auth.py` line 151 contains `_svc_mod._cache.clear()` inside `test_setup_concurrent_race`, positioned after `_require_auth_router()` and before the primer GET, wrapped in try/except. `.github/workflows/ci.yml` line 71 has a `Pytest isolation double-run` step immediately after `Pytest full suite`, with identical env block and same pytest invocation, no DB drop/recreate. Commits cb7082e + 677818e confirmed in git log. 15-02-SUMMARY.md records: Run 1 = 999 passed, 2 skipped, 10 xfailed; Run 2 (same DB) = 999 passed, 2 skipped, 10 xfailed; `test_setup_concurrent_race` PASSED (not skipped) in both. |
| 3 | Every authenticated page shows persistent nav with user identity and working sign-out, confirmed on a physical device | VERIFIED | `tests/test_nav.py` contains 6 substantive automated tests (config_hub 200, 401 for anon, mobile sign-out form present at `/logout`, admin link visibility by role, navBar x-data marker on home). These pass as the structural baseline. `15-VERIFICATION.md` DEBT-03 section records per-page on-device results for all 10 pages (/, /brew, /brew/guided, /coffees, /roasters, /equipment, /recipes, /flavor-notes, /config, /admin/*) at both 375px (on-device iPhone, 2026-05-26) and >=768px (desktop, 2026-05-26) as `pass`. Sign-out confirmed to clear session in both viewport modes. No code fix was required. |
| 4 | All outstanding v1.1 human-UAT scenarios (Phases 01/02/07/11 + Phase 14 search-sheet) are executed and recorded | VERIFIED (with D-12 deferrals as legitimate closure) | `15-VERIFICATION.md` DEBT-04 section records all 12 catalogued items: 7 pass/pass-with-findings (02-UAT-1, 07-UAT-1, 07-UAT-2, 10-VERIF-1, 10-VERIF-2, 11-UAT-1, 11-UAT-3) and 5 deferred to Phase 15.1 with written reasons (01-UAT-1/2/3, 10-VERIF-3, 11-UAT-2). Zero items left `pending`. The "Phase 14 search-sheet UAT" is correctly mapped to Phase 10 VERIF-1/2/3 (not a fabricated Phase 14 entry), per RESEARCH Open Question #3. Per D-12, a deferred item with a written reason and a named target phase counts as "executed and recorded" for this criterion. |
| 5 | Every `human_needed` verification is either closed with evidence or explicitly re-deferred with a written reason | VERIFIED (with D-12 deferrals as legitimate closure) | `15-VERIFICATION.md` DEBT-05 section covers all sources (Phases 01/02/07/09/10/11). Phase 09 item 6 (AI refresh respect/force modes) is distinctly closed with evidence: RESPECT confirmed (browser hard-refresh served cached recommendation, no regen); FORCE confirmed (manual "Refresh recommendation" triggered a fresh AI regen with streaming placeholder). All Phase 01 items are recorded as deferred to Phase 15.1 with written reasons. All Phase 10/11 items mirror their DEBT-04 outcomes. No `pending` remains in the ledger. |

**Score: 5/5 truths verified**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `entrypoint.sh` | Root-start, conditional chown guard, gosu drop, exec gosu app uvicorn | VERIFIED | Lines 25-28: stat guard + conditional chown. Line 34: alembic upgrade head (before privilege drop). Lines 42-47: `exec gosu app uvicorn` with all five flags. Single-worker warning comment block (lines 1-17) preserved. |
| `Dockerfile` | gosu in runtime apt block; `USER app` absent from runtime stage | VERIFIED | Line 85: `postgresql-client-16 gosu` on same install call. `USER app` appears exactly once in the file (line 160, dev stage only). Runtime stage ends at line 131 (`ENTRYPOINT`). |
| `tests/routers/test_auth.py` | `_cache.clear()` inside `test_setup_concurrent_race`, before primer GET | VERIFIED | Lines 148-153: try/except block with `import app.services.settings as _svc_mod` and `_svc_mod._cache.clear()`. Positioned after `_require_auth_router()` (line 140) and before primer GET (line 158). No skip/xfail markers on the test. |
| `.github/workflows/ci.yml` | `Pytest isolation double-run` step immediately after `Pytest full suite`, same env, no DB drop | VERIFIED | Line 71: step named exactly "Pytest isolation double-run". Env block lines 72-79 matches lines 61-68. Run command (line 85) matches. No DROP DATABASE / recreate logic. |
| `.planning/phases/15-v1-1-debt-cleanup/15-VERIFICATION.md` | Phase 15 closure ledger with pass/fail/deferred for every item, no `pending` | VERIFIED | File exists, frontmatter `status: partial` (correct -- 5 legitimate deferrals). Title "Phase 15 Closure Ledger" present. DEBT-01/02/03/04/05 + D-13 sections all present. Zero occurrences of `pending` as an item result (sole occurrence is in "no item left `pending`" confirmation line). |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `entrypoint.sh` chown guard | `/app/data` ownership normalization | `stat -c '%u' /app/data` UID check before `chown -R app:app` | WIRED | Pattern confirmed at line 25-28. The stat pattern exactly matches the plan's required pattern. |
| `entrypoint.sh` | uvicorn as PID 1 (UID 1000) | `exec gosu app uvicorn` | WIRED | Line 42 confirmed. |
| `test_setup_concurrent_race` | `app.services.settings._cache` | in-test `_svc_mod._cache.clear()` before async_client lifespan prewarm | WIRED | Lines 148-153 confirmed. |
| `.github/workflows/ci.yml` double-run step | same Postgres service (no drop/recreate) | second `python -m pytest tests/` reusing the session DB | WIRED | Lines 80-85 confirmed; comment explicitly states "Same database (no drop/recreate)". |
| `15-VERIFICATION.md` DEBT-04/05 sections | every catalogued item from the as-found inventory | each item recorded as pass/deferred with evidence/reason | WIRED | All 12 DEBT-04 items and all DEBT-05 items confirmed present with outcomes. |
| `15-VERIFICATION.md` D-13 section | commit `982c0e6` safe-area fix | on-device confirmation with date | WIRED | D-13 section references `982c0e6` and records `pass: on-device (John's iPhone, installed PWA, standalone) ... 2026-05-26`. |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEBT-01 | 15-01-PLAN.md | Fresh deploy writes backups/photos without manual chown | SATISFIED | `entrypoint.sh` + `Dockerfile` changes verified in codebase; commits 3cb5306, 25996c5 confirmed. |
| DEBT-02 | 15-02-PLAN.md | Full pytest suite green twice in a row, no isolation failures | SATISFIED | `test_auth.py` cache-clear guard + CI double-run step verified; commits cb7082e, 677818e confirmed. 999/999 double-run evidence in 15-02-SUMMARY.md. |
| DEBT-03 | 15-03-PLAN.md | Every authenticated page: persistent nav, user identity, working sign-out | SATISFIED | `tests/test_nav.py` automated structural baseline (6 tests). Human-ledger DEBT-03 section records on-device results for all 10 pages at both viewports. |
| DEBT-04 | 15-03-PLAN.md | Outstanding v1.1 human-UAT scenarios executed and recorded | SATISFIED | 12 catalogued items: 7 pass/pass-with-findings, 5 deferred-with-reason to Phase 15.1 per D-12. No pending. |
| DEBT-05 | 15-03-PLAN.md | Outstanding `human_needed` verifications closed or re-deferred with reason | SATISFIED | All items resolved in DEBT-05 section. Phase 09 item 6 closed with on-device evidence. 5 items deferred-with-reason to Phase 15.1 per D-12. No pending. |

All 5 requirements (DEBT-01..05) are accounted for in plan frontmatters (`requirements:` fields in 15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md). All 5 appear in REQUIREMENTS.md traceability table mapped to Phase 15.

Note: REQUIREMENTS.md traceability table still shows "Pending" status and unchecked `[ ]` boxes for DEBT-01..05. This is a cosmetic documentation artifact (the REQUIREMENTS.md was not updated post-completion), not a functional gap. The closure ledger (`15-VERIFICATION.md`) is the authoritative record per the phase plan design.

---

## Anti-Patterns Scan

Files modified in this phase: `entrypoint.sh`, `Dockerfile`, `tests/routers/test_auth.py`, `.github/workflows/ci.yml`, `15-VERIFICATION.md`.

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `tests/routers/test_auth.py:152` | `except Exception: pass` | WARNING | Broad catch as noted in 15-REVIEW.md WR-03. Could swallow future `AttributeError` if `_cache` is renamed. Pre-existing pattern in conftest.py (line 481). Not a stub or hollow implementation -- the actual behavior (cache clear) executes correctly when the import succeeds. The code-review document (15-REVIEW.md) already catalogues this as WR-03 with a proposed narrower fix. Advisory only; does not block goal achievement. |
| `Dockerfile:113-117` | Stale comment referencing removed `USER app` line | INFO | Comment says "Create the data mountpoints app-owned BEFORE `USER app`" but `USER app` was removed from the runtime stage. Noted in 15-REVIEW.md IN-01. Cosmetic documentation inconsistency; does not affect runtime behavior. |
| `entrypoint.sh:25` | UID-only chown guard (GID not checked) | WARNING | Noted in 15-REVIEW.md WR-02. A volume with GID mismatch (UID 1000, GID 0) passes the guard without correction. Theoretical edge case on this codebase; the smoke test and deployment model do not produce that state. Advisory only. |
| `entrypoint.sh:25-28` | Mixed-ownership descendants not covered | WARNING | Noted in 15-REVIEW.md WR-01. If `/app/data` root is already UID 1000 but a descendant is root-owned, the chown is skipped. Acknowledged real-world limitation. Advisory only. |

No `TBD`, `FIXME`, or `XXX` debt markers found in the modified files. No unreferenced debt markers present. No hollow implementations or placeholder stubs.

The code-review document (15-REVIEW.md) pre-identified all four anti-patterns above as WARNING/INFO findings with 0 BLOCKERs. None of the warnings prevent the phase goal from being achieved -- they are hardening improvements for a follow-up pass.

---

## Behavioral Spot-Checks

Step 7b is partially applicable. Full behavioral verification of the Docker privilege-drop mechanism was performed during Plan 15-01 Task 3 (smoke test) and is documented in 15-01-SUMMARY.md with exact command outputs. The verifier confirmed:

- `entrypoint.sh` contains `exec gosu app uvicorn` (runnable, not a stub).
- `.github/workflows/ci.yml` double-run step is structurally correct YAML with a `run:` that invokes pytest (not a placeholder).
- `tests/test_nav.py` 6 tests are substantive (assert specific HTML patterns, not empty stubs).

Full Docker smoke re-run is skipped in this pass (would require Docker daemon access and is already proved in 15-01-SUMMARY.md with recorded outputs). Full pytest double-run is skipped (requires the baked image, 130+ seconds per run, and is already proved in 15-02-SUMMARY.md with exact pass/skip/xfail counts).

---

## Human Verification Required

No new human verification items are raised beyond what is already recorded and addressed in `15-VERIFICATION.md`. The 5 items deferred to Phase 15.1 (01-UAT-1, 01-UAT-2, 01-UAT-3, 10-VERIF-3, 11-UAT-2) are explicitly managed within the phase's closure contract (D-12) and are tracked for Phase 15.1, not for this phase's gate.

---

## Deferred Items

Per Step 9b of the verification process: the 5 items deferred to Phase 15.1 from DEBT-04/DEBT-05 are not gaps in the Phase 15 context -- they are explicitly scheduled by D-12 (re-defer with written reason + target phase) and recorded in the ledger. Phase 15.1 is proposed as the gap-closure phase in the ROADMAP / ledger summary.

| Item | Deferred To | Written Reason |
|------|------------|----------------|
| 01-UAT-1 (real NGINX proxy e2e) | Phase 15.1 | Skipped at user request during live session; VPS reachable, no environmental blocker |
| 01-UAT-2 (CSP nonce wiring) | Phase 15.1 | Skipped at user request; local-closable, no environmental blocker |
| 01-UAT-3 (HTMX CSRF double-submit 2nd swap) | Phase 15.1 | Skipped at user request; local-closable, no environmental blocker |
| 10-VERIF-3 (p95 < 100ms latency) | Phase 15.1 | Pairs with a proper load-gen pass; ad-hoc DevTools timing insufficient |
| 11-UAT-2 (Android Chrome Lighthouse) | Phase 15.1 | Skipped at user request; local-closable via desktop Chrome Lighthouse |

---

## Overall Assessment

**Status: PASSED**

All 5 ROADMAP success criteria are met:

1. DEBT-01: `entrypoint.sh` + `Dockerfile` changes exist in the codebase and are wired correctly. Commits confirmed. Smoke test evidence in 15-01-SUMMARY.md.

2. DEBT-02: `_cache.clear()` guard exists in `test_setup_concurrent_race`. CI double-run step exists. Commits confirmed. 999/999 double-run evidence in 15-02-SUMMARY.md.

3. DEBT-03: All 10 authenticated pages verified on-device (physical iPhone, 2026-05-26) and on desktop. Sign-out confirmed to clear session in both viewport modes. Structural baseline `tests/test_nav.py` (6 substantive tests) is in the codebase.

4. DEBT-04: All 12 catalogued UAT items have recorded outcomes (7 pass/pass-with-findings, 5 deferred with written reasons and target Phase 15.1). Zero left pending. D-12 explicitly authorizes this pattern as "executed and recorded".

5. DEBT-05: All human_needed items resolved. Phase 09 item 6 closed with on-device evidence. No pending items in the ledger.

The 15-REVIEW.md code review identified 5 warnings (WR-01..05) and 3 info items (IN-01..03), all advisory. None are BLOCKERs and none prevent the phase goal. They are improvement candidates for a follow-up pass.

The REQUIREMENTS.md traceability table status fields ("Pending") and unchecked checkboxes are a cosmetic doc issue -- the REQUIREMENTS.md was not updated to reflect completion. This does not affect code correctness or the closure ledger.

---

_Auto-verified: 2026-05-25_
_Verifier: Claude (gsd-verifier, independent assessment)_
_Human ledger (authoritative): .planning/phases/15-v1-1-debt-cleanup/15-VERIFICATION.md_
_This file: .planning/phases/15-v1-1-debt-cleanup/15-VERIFICATION-AUTO.md_
