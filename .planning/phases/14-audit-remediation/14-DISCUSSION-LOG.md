# Phase 14: Audit Remediation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 14-audit-remediation
**Areas discussed:** SSRF connect strategy, Last-admin guard fix, /search limits, Session-sweep schedule

---

## SSRF connect strategy (S1, HIGH)

| Option | Description | Selected |
|--------|-------------|----------|
| Resolve-validate-connect | getaddrinfo → reject any private/loopback/link-local/ULA/reserved (incl. IPv4-mapped IPv6) → normal client.get. ~15 lines, no custom transport. Sub-ms TOCTOU window; relaxes roadmap "pinned IP" wording. | ✓ |
| Full IP pinning | Resolve → validate every A/AAAA → connect to literal IP via custom httpx transport preserving SNI+Host+cert. Closes TOCTOU; matches roadmap wording; fiddly TLS-to-IP plumbing. | |
| You decide at planning | Let planner pick based on how clean httpx pinning is. | |

**User's choice:** Resolve-validate-connect
**Notes:** Both fetchers are authenticated-only (paste-and-rank needs login; household = 2 people), so the DNS-rebinding/TOCTOU window is academic. KISS over TLS-to-IP complexity. Recorded as ROADMAP success-criterion #2 amendment (D-05): grade against "block on pre-resolve validation," not literal "pinned IP."

---

## Last-admin guard fix (B1, CRITICAL)

| Option | Description | Selected |
|--------|-------------|----------|
| Subquery FOR UPDATE | COUNT over a `SELECT id ... FOR UPDATE` subquery. Smallest delta, preserves the Pitfall-7 lock that guards a real concurrent-demote race, matches roadmap fix. | ✓ |
| Plain COUNT, no lock | Drop FOR UPDATE — simplest, but reintroduces the demote-to-zero-admins race. Advised against. | |

**User's choice:** Subquery FOR UPDATE
**Notes:** Claude corrected the "single-worker makes the lock decorative" assumption — sync handlers in a threadpool still race at the DB level, so the lock is legitimate. Multi-admin regression test (the untested A-demotes-B path) ships with the fix.

---

## /search limits (S4, LOW)

| Option | Description | Selected |
|--------|-------------|----------|
| 100 chars + 60/min | Cap q at 100; 60/min per IP — above debounced live-search bursts, still caps abuse. | ✓ |
| 200 chars + 120/min | More headroom on both; essentially only stops pathological abuse. | |
| 100 chars + 30/min | Matches csp-report 30/min; could pinch an active multi-search session. | |

**User's choice:** 100 chars + 60/min (per IP, get_remote_address)
**Notes:** New `SEARCH_LIMIT` constant in `app/rate_limit.py` following the existing constant pattern. Over-long q short-circuits to empty 200.

---

## Session-sweep schedule (B2, MEDIUM)

| Option | Description | Selected |
|--------|-------------|----------|
| 03:00, scheduler-only | After 02:00 backup, low-traffic; id nightly_session_sweep, idempotent; no admin button. | ✓ |
| 03:00 + admin "Sweep now" | Same schedule plus a manual trigger; adds a new endpoint + CSRF + UI (scope creep). | |
| Different time, scheduler-only | Scheduler-only at a different hour. | |

**User's choice:** 03:00, scheduler-only
**Notes:** Stays in roadmap job-only scope. Closes the `sessions.py:182-185` TODO; relies on the existing `expires_at` btree index.

---

## Claude's Discretion

- Wave/plan breakdown and single-PR-vs-split delivery (items largely independent; B1+B4 share `users.py`).
- Location/shape of the SSRF resolve-validate helper (shared `_assert_public_host` vs inline).

## Deferred Ideas

- Admin "Sweep sessions now" button — deferred as scope creep beyond B2's job-only scope.
- Full DNS-rebinding-safe IP pinning — deferred in favor of resolve-validate; revisit only if these fetchers ever become unauthenticated-reachable.
