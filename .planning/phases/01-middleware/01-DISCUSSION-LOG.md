# Phase 1: Middleware - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 1-Middleware
**Areas discussed:** CSP unsafe-eval fallback policy, sessions table columns, HTMX fragment cache helper API, audit log fields + /debug/proxy posture

---

## CSP unsafe-eval fallback policy

### Q1 — If the Alpine CSP-build prototype shows some directive we want to use requires 'unsafe-eval', what's the fallback?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict — every Alpine component as a module | Alpine CSP build; no 'unsafe-eval' in script-src. Components declared via Alpine.data('name', ...) in app/static/js/alpine-components/*.js; templates reference by name. Costs the inline-x-data DX. | ✓ |
| Pragmatic — ship v1 with 'unsafe-eval', ADR captures the trade-off | script-src 'self' 'nonce-...' 'unsafe-eval'. ADR in docs/decisions/. Phase 12 audit treats it as known. Faster iteration. | |
| Hybrid — default to CSP build, allowlist eval only if a specific need surfaces in plan-phase | Plan-phase research flag is the gate; escalate if prototype hits a wall. | |

**User's choice:** Strict — every Alpine component as a module
**Notes:** Locks the strict path before later phases bake in eval-dependent patterns.

---

### Q2 — How strict on style-src? Alpine x-transition / x-bind:style write inline style attributes.

| Option | Description | Selected |
|--------|-------------|----------|
| Split directive — style-src-elem strict, style-src-attr 'unsafe-inline' | CSP3 split. <style> blocks must be 'self' or nonced; inline style="..." attributes allowed. Lets Alpine animate without giving up CSP on stylesheets. | ✓ |
| Pure strict — style-src 'self', no inline anywhere | No Alpine x-transition or x-bind:style. Animation via Tailwind class toggling. | |
| Permissive — style-src 'self' 'unsafe-inline' | Easy but defeats CSP for styles entirely. | |

**User's choice:** Split directive — style-src-elem strict, style-src-attr 'unsafe-inline'
**Notes:** Compromise that preserves Alpine animation DX without giving up stylesheet integrity.

---

### Q3 — CSP violation reporting? Trades surface for early signal on XSS attempts and CSP regressions.

| Option | Description | Selected |
|--------|-------------|----------|
| Log-only endpoint at /csp-report | report-to / report-uri directive. slowapi 30/min/IP. Strips PII, logs as structured event. No admin UI in v1. | ✓ |
| Skip reporting in v1 | Phase 12 manual audit + |safe grep test are the safety net. | |
| Full pipeline — endpoint + csp_violations table + admin viewer | Endpoint + storage + admin UI. Overbuilt for household scale. | |

**User's choice:** Log-only endpoint at /csp-report
**Notes:** Cheap regression catch; can promote to stored + viewable in Phase 9 if it earns its keep.

---

### Q4 — HTMX hx-on:* inline handlers also need 'unsafe-eval'. Same answer as Alpine?

| Option | Description | Selected |
|--------|-------------|----------|
| Ban hx-on:* inline handlers too — use JS module event delegation | Templates use hx-trigger / hx-target / hx-vals; JS lives in app/static/js/htmx-listeners.js. CI grep test forbids hx-on: in templates/pages/. | ✓ |
| Allow hx-on:* and add 'unsafe-eval' back to script-src | Re-opens the eval hole we just closed. | |
| Permit a tiny audited allowlist of hx-on: directives via hashes ('unsafe-hashes') | 'unsafe-hashes' + sha256 hashes. Template churn every handler edit. | |

**User's choice:** Ban hx-on:* inline handlers too — use JS module event delegation
**Notes:** Consistency with the strict script-src path. CI grep test catches regressions.

---

## sessions table columns

### Q1 — Sessions table columns beyond the obvious (session_id, user_id, last_seen, expires_at, created_at)?

| Option | Description | Selected |
|--------|-------------|----------|
| Audit-rich — add ip, user_agent | Lets Phase 9 admin show 'logged in from <device> at <ip>'. Cheap (text + inet). | |
| Minimal — just the five base columns | session_id, user_id, last_seen, expires_at, created_at and nothing else. Tightest privacy footprint. | ✓ |
| Audit-rich + derived device_label | + denormalized device_label parsed via user-agents library. Nicer Phase 9 UX, one more dependency. | |

**User's choice:** Minimal — just the five base columns
**Notes:** Privacy posture takes precedence over Phase 9 admin convenience. No ip / user_agent / device_label.

---

### Q2 — Logout behavior — current device only, or also offer 'sign out everywhere'?

| Option | Description | Selected |
|--------|-------------|----------|
| Current device only | Deletes only the current session row. Other devices wait for 30-day expiry. | ✓ |
| Current device + 'sign out everywhere' link | Adds a 'Sign out of all devices' link that deletes every sessions row for user_id. | |
| Always logs out everywhere | Single button deletes all sessions for user_id. | |

**User's choice:** Current device only
**Notes:** Consistent with the minimal-sessions choice — no device-list UX to attach 'sign out everywhere' to.

---

## HTMX fragment cache helper API

### Q1 — How is no-store + Vary: HX-Request applied to fragment responses?

| Option | Description | Selected |
|--------|-------------|----------|
| Middleware auto-detect on HX-Request — fail-safe | FragmentCacheHeadersMiddleware adds the headers when HX-Request: true. Zero per-route opt-in. | ✓ |
| FragmentResponse subclass — explicit at the route | Routes return FragmentResponse(template_html). Forgetting it is the bug. | |
| Decorator — @no_store_fragment on the route | One extra line per route. Same forgetting risk. | |
| FastAPI dependency — Depends(no_store_fragment) | FastAPI-idiomatic. Noisier. | |

**User's choice:** Middleware auto-detect on HX-Request — fail-safe
**Notes:** Phase 4+ routers correct by default. PITFALL HX-2 solved at the middleware layer.

---

### Q2 — Cache-Control for authenticated full-page responses (non-HTMX)?

| Option | Description | Selected |
|--------|-------------|----------|
| Cache-Control: private, no-cache, must-revalidate | Allows bfcache (fast back-button) but forces revalidation. Logged-out user clicking back can't see cached authenticated page. | ✓ |
| Cache-Control: no-store on all authenticated pages | Disables bfcache. Strongest privacy. Adds latency on every back-navigation. | |
| No special handling — browser default | ~5min browser cache heuristic. Risks 'stale home page after logout' bugs. | |

**User's choice:** Cache-Control: private, no-cache, must-revalidate
**Notes:** Balances mobile back-button UX with privacy. Same middleware handles both HX and non-HX cases.

---

## audit log fields + /debug/proxy posture

### Q1 — Failed-login log fields — how do we treat the attempted username?

| Option | Description | Selected |
|--------|-------------|----------|
| Log username only when it matches a real user | Real user wrong password → log user_id + reason=bad_password. Unknown username → log ip + reason=user_not_found, no username field. | ✓ |
| Always log attempted username | Max audit value; log access reveals every guessed username. | |
| Never log username — only IP + reason | Maximally cautious; lose forensic value when troubleshooting. | |

**User's choice:** Log username only when it matches a real user
**Notes:** Distinguishes mistyped passwords from probing without leaking unknown usernames via log access.

---

### Q2 — /debug/proxy lifecycle after this phase?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 2 gates behind is_admin; keep permanently | Phase 1 public (no auth yet). Phase 2 wraps in admin gate. Permanent operational endpoint for post-NGINX-change verification. | ✓ |
| Remove before VPS deploy | CI smoke test only. Smallest attack surface. | |
| Keep public-but-unlinked permanently | Info disclosure small. Simpler than the admin gate. | |

**User's choice:** Phase 2 gates behind is_admin; keep permanently
**Notes:** Phase 9 note's "or removed here" clause is now dropped — endpoint stays as a permanent admin diagnostic.

---

## Claude's Discretion

- Middleware stack ordering — planner picks based on Starlette `add_middleware` reverse-order semantics. Sensible order documented in CONTEXT.md D-section.
- Nonce plumbing into Jinja (`request.state.csp_nonce` vs context processor vs dependency override).
- Cookie names and signing-serializer choice (`URLSafeSerializer` vs `URLSafeTimedSerializer`).
- Precise CSP directive list (D-05 baseline given; planner verifies each directive against a prototype before locking).
- Whether to emit `report-to` (newer) or `report-uri` (deprecated but universal) or both for CSP violations.
- Extending Permissions-Policy beyond the spec set (interest-cohort, payment, usb, bluetooth) if cheap to be exhaustive.

## Deferred Ideas

- CSP `csp_violations` table + admin viewer — revisit in Phase 9 if log grep'ing becomes a recurring task.
- "Sign out everywhere" UX — revisit only if `device_label` ever lands on the sessions table.
- Audit log retention beyond Docker stdout / host syslog — separate phase if long-term retention becomes a requirement.
- Absolute session-expiry cap on top of sliding 30-day refresh — revisit only if a future security review flags it.
