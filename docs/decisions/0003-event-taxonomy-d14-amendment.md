# ADR 0003: D-14 Event Taxonomy Amendment — `auth.login_attempt`

- Status: Accepted
- Date: 2026-05-16
- Phase: 1 (Middleware)
- Requirements: AUTH-10
- Supersedes: (none) — amends CONTEXT.md D-14 in place

## Context

`.planning/phases/01-middleware/01-CONTEXT.md` D-14 locks the structlog event taxonomy:

- `auth.login_succeeded`
- `auth.login_failed`
- `auth.logout`
- `admin.user_created`
- `admin.user_deleted`
- `admin.password_reset`
- `admin.is_admin_toggled`
- `csp.violation`

`.planning/ROADMAP.md` Phase 1 success criterion 4, however, explicitly references `event=auth.login_attempt` — which is NOT in the D-14 taxonomy as originally written. RESEARCH §6 open question 1 surfaced this drift and recommended amending D-14 rather than dropping the event from the success criterion. Plan 02 shipped the constant in `app/events.py`; Plan 07 emits it from the stub `POST /login` route.

The drift is meaningful because `auth.login_attempt` and `auth.login_succeeded` measure different things:

- `auth.login_attempt` — request entry, no credential check yet
- `auth.login_succeeded` — after argon2 verify passes

Operators counting authentication health need both: `attempt` to gauge brute-force pressure and conversion baseline, `succeeded` to gauge user success. A single combined event would conflate the two.

## Decision

The D-14 taxonomy is amended to include a fourth `auth.*` event:

| Event | When emitted | Fields beyond standard `{event, request_id, ip, timestamp_iso}` | Phase |
|---|---|---|---|
| `auth.login_attempt` | Request entry to `POST /login`, BEFORE any credential verification | (none) | Phase 1 (stub) + Phase 2 (real) |
| `auth.login_succeeded` | After argon2 verify succeeds | `user_id` | Phase 2 |
| `auth.login_failed` | After argon2 verify fails | `reason` (`"bad_password"` \| `"user_not_found"`); `user_id` only when `reason == "bad_password"` per D-15 | Phase 2 |
| `auth.logout` | After session row deletion | `user_id` | Phase 2 |

Notes on the new `auth.login_attempt`:

- **No `user_id`** — verification hasn't happened yet; the request body's username may or may not match a real user.
- **No `username` field** — D-15 locks the failed-login username policy: usernames are logged only after a real-user match in `auth.login_failed`. The same policy applies here defensively (T-07-04 mitigation).
- **No request body fields** — AUTH-10 invariant: the audit trail records the act, not the content. The stub route in Plan 07 reads zero body fields, and Phase 2 will continue that pattern at the entry log.

`app/events.py` is the canonical source of truth for all event-name strings — including the four `auth.*` events above. Code that emits any of these events MUST import the constant (`from app.events import AUTH_LOGIN_ATTEMPT`), not hard-code the string `"auth.login_attempt"`. The Plan 07 stub does this; Phase 2 must too.

## Consequences

- Operators can count `auth.login_attempt` vs `auth.login_succeeded` independently. Conversion ratio and brute-force pressure become first-class metrics.
- Phase 2 implements `auth.login_succeeded` / `auth.login_failed` / `auth.logout`; Phase 1 ships only `auth.login_attempt` (in the stub route via Plan 07).
- CONTEXT.md D-14 is now read in conjunction with this ADR — the taxonomy is the union of the D-14 list plus `auth.login_attempt`. A future CONTEXT.md amendment may inline this; until then this ADR is the durable record.
- `app/events.py` already exports `AUTH_LOGIN_ATTEMPT`, `AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT` plus the admin and csp constants. No new constants need to be added by Phase 2 for the auth path.

## Alternatives Considered

- **Rename the Phase 1 stub log to `auth.login_stub`** to avoid taxonomy drift — rejected. The ROADMAP success criterion explicitly names `auth.login_attempt`. Renaming the success criterion would also be possible, but `auth.login_attempt` is a meaningful operational event that Phase 2 will continue to emit, so the success criterion is correct.
- **Drop the log line entirely in Phase 1** — rejected. The rate-limit test (`tests/routers/test_auth_stub.py::test_login_rate_limit`) expects an audit log line per request as part of the per-IP keying verification. The event is also useful operationally even from the stub path: operators can see the rate-limit fence working under the stub before Phase 2's real verifier lands.
- **Add the event to CONTEXT.md instead of writing this ADR** — partial alternative. CONTEXT.md is locked by definition; amendments go through an ADR. CONTEXT.md may eventually inline this ADR's content during a future revision, but the ADR is the canonical first-class record.

## Enforcement

- `app/routers/auth.py` imports `AUTH_LOGIN_ATTEMPT` from `app.events` (NOT the literal string `"auth.login_attempt"`). Plan 07 SUMMARY explicitly verifies via `grep -c '"auth.login_attempt"' app/routers/auth.py == 0`.
- Phase 12 may add a CI grep across `app/` for hard-coded event-name literals: `grep -rE '"(auth|admin|csp|rate_limit)\.[a-z_]+"' app/ --exclude-dir=__pycache__` should return zero hits outside `app/events.py`.

## References

- D-14, D-15 (`.planning/phases/01-middleware/01-CONTEXT.md`)
- ROADMAP.md Phase 1 success criterion 4
- RESEARCH.md §6 (event-taxonomy open question), §16 open question 1
- `app/events.py` (canonical source)
- `app/routers/auth.py` (Plan 07 emit site)
