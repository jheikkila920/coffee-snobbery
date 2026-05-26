# Phase 15: v1.1 Debt Cleanup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 15-v1-1-debt-cleanup
**Areas discussed:** Human-gated execution model, Nav/sign-out fix scope, Test isolation (done-bar + race test), G-01 chown mechanism

---

## Gray-area selection

All four presented gray areas were selected for discussion: Human-gated execution model, Nav/sign-out fix scope, Test isolation, G-01 chown mechanism.

---

## Human-gated execution model (DEBT-04 / DEBT-05)

### Execution model

| Option | Description | Selected |
|--------|-------------|----------|
| Runbook + ledger | Build a consolidated on-device UAT runbook + a verification ledger; John executes in one sitting; phase closes on recorded pass/fail | |
| Automate-first, then runbook | Close everything possible via Playwright/automated tests first; runbook only for device-only items | |
| Live interactive | Walk scenarios together in real time during execution; no standalone runbook artifact | ✓ |

**User's choice:** Live interactive
**Notes:** Closure happens together (John + Claude) during phase execution. Outcomes are still recorded (see disposition below) so closure is auditable.

### Safe-area gate

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, fold in | One device session verifies nav (DEBT-03), Phase 11/14 UAT, AND the safe-area fix (commit 982c0e6); closes the Phase 20/21 gate early | ✓ |
| No, leave for Phase 20 | Keep Phase 15 to the 5 DEBT items; safe-area stays an open 20/21 gate | |

**User's choice:** Yes, fold in
**Notes:** John picks up the phone once; safe-area gate closed early so Phases 20/21 aren't blocked.

### Disposition for un-closeable items

| Option | Description | Selected |
|--------|-------------|----------|
| Re-defer with reason | Close everything with evidence; re-defer the rest with a written reason + target phase | ✓ |
| Must close all now | Block phase completion until every item has evidence | |
| You decide per item | Claude judges each case-by-case | |

**User's choice:** Re-defer with reason
**Notes:** Honest ledger, no hollow green — matches the project's "no pass-by-skip" posture.

---

## Nav/sign-out fix scope (DEBT-03)

### Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Correctness-only | Persistent nav + identity + working sign-out on every authed page, on-device verified; no redesign | ✓ |
| Correctness + light polish | Also tidy obvious nav rough edges now if cheap | |

**User's choice:** Correctness-only
**Notes:** Phase 17 (IA Restructure) and Phase 21 (mobile rework) own the redesign; polishing now is throwaway work.

### Phase 11 visual backlog

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to 17/21 | Capture logo-on-every-page, login hero image, cold-start meter position as deferred ideas | ✓ |
| Do cheap ones now | Knock out trivial ones in Phase 15 | |
| Drop them | Remove from backlog entirely | |

**User's choice:** Defer to 17/21
**Notes:** Captured in CONTEXT.md Deferred Ideas, not built in Phase 15.

---

## Test isolation — done-bar + race test (DEBT-02)

### test_setup_concurrent_race treatment

| Option | Description | Selected |
|--------|-------------|----------|
| Fix root cause | Make it pass deterministically inside a full `pytest tests/` run | ✓ |
| Quarantine with reason | Mark xfail/skip with documented reason | |
| Verify already-green | Confirm twice-in-a-row; move on if green | |

**User's choice:** Fix root cause
**Notes:** It's a cross-module ordering/cache-residue artifact, not a feature bug; quarantining would contradict the no-pass-by-skip posture.

### Done-bar / scope of change

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse DB + CI guard, minimal code | Double-run against the SAME test DB + a regression guard; keep existing fixtures | ✓ |
| Stricter per-test rollback rewrite | Replace module TRUNCATE teardown with per-test transactional rollback | |
| Drop+recreate between runs | Fresh DB per run | |

**User's choice:** Reuse DB + CI guard, minimal code
**Notes:** The T-INFRA-1 mechanism already exists in conftest.py; treat as prove-and-lock. No fixture rewrite.

---

## G-01 chown mechanism (DEBT-01)

### Privilege-drop tool

| Option | Description | Selected |
|--------|-------------|----------|
| gosu | Canonical Debian choice; correct SIGTERM forwarding; one apt package | ✓ |
| setpriv (util-linux) | Already on Debian slim, no new package, but fiddlier and weaker signal handling | |
| You decide / research picks | Defer the tool; lock only the behavior | |

**User's choice:** gosu
**Notes:** Base is Debian glibc (`python:3.12-slim`), so gosu over the Alpine-oriented su-exec.

### chown idempotency

| Option | Description | Selected |
|--------|-------------|----------|
| Conditional guard | Only `chown -R` when /app/data isn't already app-owned | ✓ |
| Always chown -R | Unconditional every boot | |
| You decide | Defer the idempotency approach | |

**User's choice:** Conditional guard
**Notes:** Fixes first-boot root-owned volume; near-zero cost on later boots as the photos volume grows.

---

## Claude's Discretion

- Exact `gosu` install line / Dockerfile layer placement (constraints D-01..D-04 hold).
- CI-guard shape for the DEBT-02 double-run (CI step vs pytest marker/assertion).
- Verification-ledger representation (Phase 15 VERIFICATION.md vs per-archived-phase updates), as long as outcomes are auditable.

## Deferred Ideas

- Phase 11 visual backlog (logo-on-every-page, login hero image, cold-start meter position) → Phase 17 / 21.
- All nav/IA redesign → Phase 17.
- All mobile visual polish beyond on-device correctness → Phase 21.
