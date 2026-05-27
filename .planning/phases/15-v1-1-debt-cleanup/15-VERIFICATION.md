---
phase: 15-v1-1-debt-cleanup
status: partial
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-RESEARCH.md]
started: 2026-05-26T01:30:00Z
updated: 2026-05-26T02:30:00Z
closed: 13
deferred: 5
deferred_to: Phase 15.1 (verification gap-closure)
findings: 2
---

# Phase 15 Closure Ledger

Auditable closure record for DEBT-01..05 + D-13. Each item resolves to exactly one of:
`pass: <evidence>`, `fail: <details>`, or `deferred: Phase XX -- <reason>` (D-11/D-12).
No hollow green.

**Status after the 2026-05-26 live John+Claude device session (iPhone + desktop browser +
VPS at snobbery.jheikkila.com):** DEBT-01, DEBT-02, DEBT-03, D-13, and Phase 09 item 6 are
fully closed. 7 of 12 DEBT-04 UAT items closed in-session; 5 deferred to Phase 15.1 at
user request (no environmental blockers; skipped to keep session momentum). Two follow-up
findings captured against 07-UAT-1. Phase 15 success criteria #3 (DEBT-03 on physical
device) and #5 (DEBT-05 closed-with-evidence or re-deferred-with-reason) are met; #4
(every outstanding v1.1 human-UAT scenario executed and recorded) is met for the items
executed and recorded-as-deferred for the rest.

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
| `/` (home) | pass (on-device) | pass (desktop) |
| `/brew` | pass (on-device) | pass (desktop) |
| `/brew/guided` | pass (on-device) | pass (desktop) |
| `/coffees` | pass (on-device) | pass (desktop) |
| `/roasters` | pass (on-device) | pass (desktop) |
| `/equipment` | pass (on-device) | pass (desktop) |
| `/recipes` | pass (on-device) | pass (desktop) |
| `/flavor-notes` | pass (on-device) | pass (desktop) |
| `/config` | pass (on-device) | pass (desktop) |
| `/admin/*` | pass (on-device) | pass (desktop) |

375px evidence: on John's physical iPhone (installed PWA, standalone), 2026-05-26 -- the
persistent bottom nav was present on every page in the sweep (Home, Log, Guided Brew,
Coffees, Roasters, Equipment, Recipes, Flavor Notes, Config, Admin); the username/identity
is visible at the bottom of the Config page; sign-out via the config-hub mobile form logged
the session out and landed unauthenticated (session cleared). Satisfies the "confirmed on a
physical device" must-have. No correctness fix was required (D-08/D-09 untouched).

>=768px evidence: desktop browser at snobbery.jheikkila.com, 2026-05-26 -- persistent TOP
nav present on every page swept (Home, Coffees, Roasters, Equipment, Recipes, Flavor Notes,
Log, Config, Admin); username visible in the top-right menu/dropdown.

Sign-out end-to-end: <768px via the config-hub mobile sign-out form -- confirmed on iPhone
(session cleared, landed unauthenticated). >=768px via the desktop user-dropdown form
(`base.html:161`) -- confirmed on desktop browser 2026-05-26 (signed out, landed
unauthenticated, /admin no longer reachable without re-auth). DEBT-03 fully closed: no
correctness fixes needed; all 10 pages have nav + identity + working sign-out at both
viewports.

Fix authorization: the ONLY permitted code change is copying the `base.html:161` CSRF
sign-out form to a page found missing one, followed by a rebuild + re-verify. No restyle,
no IA change.

---

## DEBT-04: Human UAT Closure

12 catalogued v1.1 UAT items. Each resolves to `pass`/`fail`/`deferred: Phase XX -- reason`.
Note (RESEARCH Open Question #3): the "Phase 14 375px search-sheet UAT" maps to Phase 10's
VERIF-1/2/3 -- recorded under Phase 10 below, NOT a fabricated Phase 14 entry.

### Phase 01 (middleware)
- **01-UAT-1** -- Real NGINX reverse-proxy e2e (`curl https://<host>/debug/proxy`) [needs VPS]: deferred: Phase 15.1 (verification gap-closure) -- skipped at user request during 2026-05-26 live session to keep momentum; VPS is reachable, no environmental blocker.
- **01-UAT-2** -- Browser CSP nonce wiring (DevTools Network tab) [local OK]: deferred: Phase 15.1 (verification gap-closure) -- skipped at user request during 2026-05-26 live session to keep momentum; local-closable, no environmental blocker.
- **01-UAT-3** -- HTMX CSRF double-submit on 2nd fragment swap [local OK]: deferred: Phase 15.1 (verification gap-closure) -- skipped at user request during 2026-05-26 live session to keep momentum; local-closable, no environmental blocker.

### Phase 02 (auth)
- **02-UAT-1** -- Mobile 375px visual smoke for /setup, /login, /admin, / [local OK]: pass: 2026-05-26 at 375px DevTools -- /, /admin, /login all smoke clean (no horizontal scroll, layout intact). /setup is N/A on a provisioned instance (redirects to /login when users exist).

### Phase 07 (ai-services)
- **07-UAT-1** -- Hero card e2e with live provider key [needs VPS + AI creds]: pass-with-findings: 2026-05-26 on snobbery.jheikkila.com -- live AI hero card works end-to-end; a real recommendation renders on browser refresh (cached) and manual "Refresh recommendation" regenerates a new one (streaming placeholder shown during regen). Two follow-up findings (not blocking this UAT, capture as TODOs): (i) manual regen took several minutes (concerning latency vs typical 10-60s for web-search-grounded LLM calls), (ii) the recommendation surfaced a coffee with an active URL but the coffee is ARCHIVED / unavailable to purchase (AI grounding does not filter for purchase availability).
- **07-UAT-2** -- 375px hero "generated" / "try-again" states [needs VPS + AI creds]: pass: 2026-05-26 at 375px DevTools on snobbery.jheikkila.com -- generated-state hero recommendation renders readably (no overflow, layout intact); refresh-recommendation streaming/loading state renders correctly at narrow width.

### Phase 10 (search) -- also covers the "Phase 14 search-sheet" items
- **10-VERIF-1** -- Responsive layout smoke, icon to full-screen sheet (375px) [local OK]: pass: 2026-05-26 at 375px DevTools -- tapping the search icon opens a full-screen sheet (not a small dropdown).
- **10-VERIF-2** -- Debounce + hx-sync in-flight cancellation (Network panel) [local OK]: pass: 2026-05-26 in DevTools Network panel -- requests are debounced (fewer requests than keystrokes) and prior in-flight requests are canceled when a newer query fires (hx-sync working).
- **10-VERIF-3** -- p95 < 100ms latency on seeded dataset [needs VPS-scale data]: deferred: Phase 15.1 (verification gap-closure) -- skipped at user request during 2026-05-26 live session to keep momentum; pairs naturally with a proper load-gen pass rather than ad-hoc DevTools timing.

### Phase 11 (pwa)
- **11-UAT-1** -- iOS Safari installability (MOB-12) [needs VPS + iPhone]: pass: on-device 2026-05-26 -- Add-to-Home-Screen installs and launches standalone (no Safari chrome) from snobbery.jheikkila.com
- **11-UAT-2** -- Android Chrome installability (Lighthouse) [needs VPS + Chrome]: deferred: Phase 15.1 (verification gap-closure) -- skipped at user request during 2026-05-26 live session to keep momentum; local-closable via desktop Chrome Lighthouse PWA audit, no environmental blocker.
- **11-UAT-3** -- Guided Brew wake lock on real device (BREW-13) [needs real devices]: pass: on-device iPhone 2026-05-26 -- screen stayed awake (no dim/lock) during the guided-brew timer countdown

---

## DEBT-05: human_needed Closure

Most items duplicate DEBT-04 behaviors -- cite the recorded DEBT-04 outcome (do not re-test).
The distinct item is Phase 09 item 6.

### Phase 01 (3 items) -- same as 01-UAT-1/2/3
- result: deferred: Phase 15.1 (verification gap-closure) -- mirrors DEBT-04 Phase 01 outcome (all three deferred at user request 2026-05-26 to keep session momentum; no environmental blocker).

### Phase 02 (1 item) -- same as 02-UAT-1
- result: pass: 2026-05-26 -- mirrors DEBT-04 02-UAT-1 outcome (375px visual smoke clean for /, /admin, /login; /setup N/A on a provisioned instance).

### Phase 07 (2 items) -- same as 07-UAT-1/2
- result: pass-with-findings: 2026-05-26 -- mirrors DEBT-04 Phase 07 outcome. 07-UAT-1 pass with two follow-up findings (regen latency several minutes; AI surfaced an archived/unavailable coffee). 07-UAT-2 pass (375px hero generated + try-again states render correctly).

### Phase 09 (admin) item 6 -- AI refresh respect/force modes with real data [DISTINCT]
- Currently "partial (seems good)". Close with evidence IF VPS has live AI creds + an
  eligible cold-start-passed user (exercise respect = signature unchanged -> no regen, and
  force = manual refresh -> regen). Else re-defer with written reason (RESEARCH Open Q #4).
- result: pass: 2026-05-26 on snobbery.jheikkila.com -- both modes confirmed in the same
  session as 07-UAT-1. RESPECT: a browser hard-refresh ("Force Refresh All") with no input
  signature change served the EXISTING cached recommendation instantly (no regen). FORCE:
  clicking the "Refresh recommendation" button triggered a fresh AI regen (streaming
  placeholder shown, new recommendation rendered). Signature-based caching is honoring
  unchanged-input + regenerating on manual force. Closes Phase 09 item 6.

### Phase 10 (3 items) -- same as 10-VERIF-1/2/3
- result: partial: 2026-05-26 -- mirrors DEBT-04 Phase 10 outcome. 10-VERIF-1 (search-sheet at 375px) and 10-VERIF-2 (debounce + hx-sync) pass. 10-VERIF-3 (p95 < 100ms latency) deferred to Phase 15.1 (verification gap-closure) at user request -- pairs naturally with a proper load-gen pass.

### Phase 11 (3 items) -- same as 11-UAT-1/2/3
- result: partial: 2026-05-26 -- mirrors DEBT-04 Phase 11 outcome. 11-UAT-1 (iOS Safari installability) and 11-UAT-3 (Guided Brew wake lock) pass on-device. 11-UAT-2 (Android Chrome installability via Lighthouse) deferred to Phase 15.1 (verification gap-closure) at user request -- local-closable via desktop Chrome Lighthouse.

---

## D-13: Safe-Area Commit 982c0e6

Commit `982c0e6` -- "fix: fill iOS safe-area gap below fixed bottom nav" -- is UNVERIFIED
on-device (project memory `[safe-area fix unverified]`). Verify in the SAME session so John
picks up the phone once. Unblocks Phases 20/21.

- **(a) iOS safe-area inset** -- on John's physical iPhone, installed PWA in standalone mode:
  does the bottom nav clear the iOS home indicator (safe-area inset correct)?
  result: pass: on-device (John's iPhone, installed PWA, standalone) -- bottom nav has a clear
  gap above the iOS home indicator; commit 982c0e6 safe-area fix verified on-device 2026-05-26.
  Unblocks Phases 20/21.
- **(b) NEW-13 follow-up** -- is the bottom nav still raised on the Log/sessions page, or did
  the 100dvh min-height fix resolve it? Record which.
  result: pass: on-device 2026-05-26 -- bottom nav sits correctly on the Log/sessions page
  (no longer raised); the 100dvh min-height fix resolved NEW-13.

---

## Phase Summary

**Outcome:** partial (5 items legitimately deferred to Phase 15.1).

| Bucket | Count | Items |
|--------|-------|-------|
| Closed with evidence | 13 | DEBT-01, DEBT-02, DEBT-03 (10 pages x 2 viewports + sign-out), D-13 (a + b), Phase 09 item 6, 02-UAT-1, 07-UAT-1, 07-UAT-2, 10-VERIF-1, 10-VERIF-2, 11-UAT-1, 11-UAT-3 |
| Deferred to Phase 15.1 | 5 | 01-UAT-1, 01-UAT-2, 01-UAT-3, 10-VERIF-3, 11-UAT-2 |
| Follow-up findings | 2 | 07-UAT-1 regen latency (several minutes for manual refresh); 07-UAT-1 AI surfaced an ARCHIVED coffee in a recommendation (grounding does not filter for purchase availability) |

### What Is Now Unblocked
- **Phases 20 and 21** are unblocked by the D-13 on-device safe-area verification (commit `982c0e6` confirmed correct on iPhone PWA standalone).
- v1.2 feature work can proceed -- the v1.1 base is verified, not just patched (ROADMAP Phase 15 intent satisfied to the extent any single session can; the 5 deferrals carry written reasons and a target phase).

### Phase 15.1 (proposed gap-closure phase)
The 5 deferred items are all environment-unblocked. They are mechanical to close in a single ~30-60min DevTools/curl/Lighthouse pass on the VPS plus one terminal session. Open Phase 15.1 to schedule that work explicitly.

### Follow-up TODOs (not in scope for this verification per D-08/D-09)
1. **AI hero regen latency** -- manual "Refresh recommendation" took several minutes on 2026-05-26 vs the typical 10-60s for web-search-grounded LLM calls. Investigate provider call timing, web-search tool latency, and SSE stream health. Likely target: an AI-perf pass during v1.2.
2. **AI recommends archived/unavailable coffees** -- the recommendation surfaced a coffee with an active URL but the coffee is archived and unavailable to purchase. Grounding does not filter for purchase availability. Likely target: a recommendation-quality pass (filter ground-truth coffees by `is_active` / availability flag before AI sees them, or post-filter results).

### Honored decisions
D-08 (correctness-only nav/sign-out; no redesign): honored -- no fix was required.
D-09 (no IA change): honored.
D-10 (live John+Claude session): honored.
D-11 (record every outcome): honored -- no item left `pending`.
D-12 (re-defer with written reason + target phase): honored -- all 5 deferrals name Phase 15.1 + reason.
D-13 (fold safe-area into the same session): honored -- closed on-device.
