---
phase: 15-v1-1-debt-cleanup
status: in-progress
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-RESEARCH.md]
started: 2026-05-26T01:30:00Z
updated: 2026-05-26T01:30:00Z
---

# Phase 15 Closure Ledger

Auditable closure record for DEBT-01..05 + D-13. Each item resolves to exactly one of:
`pass: <evidence>`, `fail: <details>`, or `deferred: Phase XX -- <reason>` (D-11/D-12).
No hollow green.

**As of scaffold:** DEBT-01 and DEBT-02 are closed by Wave 1 automated proof (evidence
below). DEBT-03 / DEBT-04 / DEBT-05 / D-13 are pending the live John+Claude device session
(Tasks 2-4).

---

## DEBT-01: Volume Ownership Fix

result: pass: closed by Plan 15-01 automated Docker smoke proof (2026-05-26)

Evidence (from 15-01-SUMMARY.md, Task 3 smoke test against a simulated root-owned VPS volume):

| Assertion | Expected | Result |
|-----------|----------|--------|
| (a) `stat -c '%u' /app/data` after start vs root-owned volume | `1000` | `1000` |
| (b) Process UID after `exec gosu app` | `1000` | `1000` (via `gosu app sh -c 'id -u'`) |
| (c) Write to `/app/data/backups` as app user | success | `touch` succeeded |
| (d) `docker stop` duration (SIGTERM forwarding) | <3s | 1527ms |
| (e) Idempotency (already app-owned) | chown skipped | skipped |
| (f) Throwaway volumes/images removed | all removed | confirmed |

Mechanism: container starts as root, conditionally `chown -R app:app /app/data` only when
`stat -c '%u' /app/data != 1000`, runs `alembic upgrade head`, then `exec gosu app uvicorn`
drops to UID 1000. Retires the manual `chown -R app:app /app/data` VPS workaround.
Commits: `3cb5306`, `25996c5`.

---

## DEBT-02: Test Isolation Double-Run

result: pass: closed by Plan 15-02 full-suite double-run (2026-05-26)

Evidence (from 15-02-SUMMARY.md, full suite against `coffee-snobbery-test` baked image,
rebuilt with the Task 1 fix):

- **Run 1:** `999 passed, 2 skipped, 10 xfailed` in 130.82s -- exit 0
- **Run 2 (same DB, no drop/recreate):** `999 passed, 2 skipped, 10 xfailed` in 120.79s -- exit 0
- `test_setup_concurrent_race` confirmed PASSED (not skipped) in BOTH runs.
- The 2 skips are pre-existing structural skips (`test_session.py:261`, `test_sessions.py:22`), unrelated.

Root cause closed: a stale `_svc._cache` entry from `test_setup_blocked_after_completion`
was making the concurrent-race test read `setup_completed=true`. Fix clears the cache before
the `async_client` lifespan prewarm. No conftest rewrite, no skip/xfail (D-05/D-06). CI now
runs the suite twice against the same DB to catch teardown residue (D-07).
Commits: `cb7082e`, `677818e`.

---

## DEBT-03: Nav / Sign-Out On-Device

Structural baseline (already green): `tests/test_nav.py` -- 5 tests (config_hub mobile
sign-out form present; home navBar; admin link visibility by role; config hub 200). CSRF
sign-out form pattern: `base.html:161-166`. Mobile sign-out lives in
`app/templates/pages/config_hub.html`. This section is the on-device CORRECTNESS check
(D-08: correctness only, no redesign; D-09: no IA change).

Per authenticated page -- confirm (1) persistent nav present, (2) user identity visible,
(3) sign-out actually clears the session (lands unauthenticated). Bottom nav <768px, top
nav >=768px.

| Page | 375px (nav / identity / sign-out) | >=768px (nav / identity / sign-out) |
|------|-----------------------------------|-------------------------------------|
| `/` (home) | pending | pending |
| `/brew` | pending | pending |
| `/brew/guided` | pending | pending |
| `/coffees` | pending | pending |
| `/roasters` | pending | pending |
| `/equipment` | pending | pending |
| `/recipes` | pending | pending |
| `/flavor-notes` | pending | pending |
| `/config` | pending | pending |
| `/admin/*` | pending | pending |

Sign-out end-to-end: <768px via the config-hub mobile sign-out form; >=768px via the
desktop user-dropdown form (`base.html:161`). After submit, session cleared + lands
unauthenticated.

Fix authorization: the ONLY permitted code change is copying the `base.html:161` CSRF
sign-out form to a page found missing one, followed by a rebuild + re-verify. No restyle,
no IA change.

---

## DEBT-04: Human UAT Closure

12 catalogued v1.1 UAT items. Each resolves to `pass`/`fail`/`deferred: Phase XX -- reason`.
Note (RESEARCH Open Question #3): the "Phase 14 375px search-sheet UAT" maps to Phase 10's
VERIF-1/2/3 -- recorded under Phase 10 below, NOT a fabricated Phase 14 entry.

### Phase 01 (middleware)
- **01-UAT-1** -- Real NGINX reverse-proxy e2e (`curl https://<host>/debug/proxy`) [needs VPS]: pending
- **01-UAT-2** -- Browser CSP nonce wiring (DevTools Network tab) [local OK]: pending
- **01-UAT-3** -- HTMX CSRF double-submit on 2nd fragment swap [local OK]: pending

### Phase 02 (auth)
- **02-UAT-1** -- Mobile 375px visual smoke for /setup, /login, /admin, / [local OK]: pending

### Phase 07 (ai-services)
- **07-UAT-1** -- Hero card e2e with live provider key [needs VPS + AI creds]: pending
- **07-UAT-2** -- 375px hero "generated" / "try-again" states [needs VPS + AI creds]: pending

### Phase 10 (search) -- also covers the "Phase 14 search-sheet" items
- **10-VERIF-1** -- Responsive layout smoke, icon to full-screen sheet (375px) [local OK]: pending
- **10-VERIF-2** -- Debounce + hx-sync in-flight cancellation (Network panel) [local OK]: pending
- **10-VERIF-3** -- p95 < 100ms latency on seeded dataset [needs VPS-scale data]: pending

### Phase 11 (pwa)
- **11-UAT-1** -- iOS Safari installability (MOB-12) [needs VPS + iPhone]: pending
- **11-UAT-2** -- Android Chrome installability (Lighthouse) [needs VPS + Chrome]: pending
- **11-UAT-3** -- Guided Brew wake lock on real device (BREW-13) [needs real devices]: pending

---

## DEBT-05: human_needed Closure

Most items duplicate DEBT-04 behaviors -- cite the recorded DEBT-04 outcome (do not re-test).
The distinct item is Phase 09 item 6.

### Phase 01 (3 items) -- same as 01-UAT-1/2/3
- result: pending (cross-ref DEBT-04 Phase 01)

### Phase 02 (1 item) -- same as 02-UAT-1
- result: pending (cross-ref DEBT-04 Phase 02)

### Phase 07 (2 items) -- same as 07-UAT-1/2
- result: pending (cross-ref DEBT-04 Phase 07)

### Phase 09 (admin) item 6 -- AI refresh respect/force modes with real data [DISTINCT]
- Currently "partial (seems good)". Close with evidence IF VPS has live AI creds + an
  eligible cold-start-passed user (exercise respect = signature unchanged -> no regen, and
  force = manual refresh -> regen). Else re-defer with written reason (RESEARCH Open Q #4).
- result: pending

### Phase 10 (3 items) -- same as 10-VERIF-1/2/3
- result: pending (cross-ref DEBT-04 Phase 10)

### Phase 11 (3 items) -- same as 11-UAT-1/2/3
- result: pending (cross-ref DEBT-04 Phase 11)

---

## D-13: Safe-Area Commit 982c0e6

Commit `982c0e6` -- "fix: fill iOS safe-area gap below fixed bottom nav" -- is UNVERIFIED
on-device (project memory `[safe-area fix unverified]`). Verify in the SAME session so John
picks up the phone once. Unblocks Phases 20/21.

- **(a) iOS safe-area inset** -- on John's physical iPhone, installed PWA in standalone mode:
  does the bottom nav clear the iOS home indicator (safe-area inset correct)?
  result: pending
- **(b) NEW-13 follow-up** -- is the bottom nav still raised on the Log/sessions page, or did
  the 100dvh min-height fix resolve it? Record which.
  result: pending

---

## Phase Summary

_To be finalized in Task 4: closed-vs-deferred count, and frontmatter `status` set to
`complete` (or `partial` if any item is legitimately re-deferred)._
