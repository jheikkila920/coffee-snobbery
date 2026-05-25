---
phase: 01-middleware
plan: 10
status: complete
type: execute
wave: 3
completed: 2026-05-17
files_created:
  - docs/decisions/0001-csp-strict-no-unsafe-eval.md
  - docs/decisions/0002-pure-asgi-middleware.md
  - docs/decisions/0003-event-taxonomy-d14-amendment.md
  - app/static/js/alpine-components/__init.js
  - app/static/js/alpine-components/.gitkeep
commits:
  - <single commit> docs(01-10): ADRs 0001-0003 + Alpine CSP components scaffold
executor: orchestrator-mediated
---

## Plan 01-10 — ADRs + Alpine components scaffold

Three Architecture Decision Records and the Phase 4+ Alpine components directory anchor.

## Artifacts

### docs/decisions/0001-csp-strict-no-unsafe-eval.md (85 lines)

- `@alpinejs/csp@3.14.9` pinned and recorded (closes RESEARCH §16 open question 2).
- Full `CSP_TEMPLATE` transcribed authoritatively from `app/middleware/security_headers.py`.
- Four banned HTMX patterns documented: `hx-on:*`, `hx-vals='js:`, `hx-headers='js:`, eval-using `hx-trigger` event filters.
- `htmx.config.allowEval = false` runtime guard documented (defense in depth).
- `x-model` unavailability + `:value`/`@input` replacement recipe documented.
- `style-src-attr 'unsafe-inline'` rationale (designers' inline `style=` + Alpine `x-bind:style` string form; doesn't affect direct property assignment used by `x-transition`).
- Enforcement section lists the module-load `RuntimeError` invariant in `SecurityHeadersMiddleware`, the CI grep test, and the Phase 12 Playwright check follow-up.
- Alternatives considered: standard Alpine + unsafe-eval, unsafe-hashes, no CSP, Alpine v2 — all rejected with rationale.

### docs/decisions/0002-pure-asgi-middleware.md (87 lines)

- `BaseHTTPMiddleware` ban + the contextvars-propagation pitfall (RESEARCH §13.1) documented.
- Canonical pure ASGI class shape shown in a code block (`__init__(self, app)` + `async def __call__(scope, receive, send)`).
- `send_wrapper(message)` pattern for header-mutation middlewares shown.
- Verified third parties (`starlette_csrf.CSRFMiddleware`) called out as pure ASGI compliant.
- All five Phase 1 middlewares already comply; the ADR is forward-looking enforcement for Phase 4+ contributors.

### docs/decisions/0003-event-taxonomy-d14-amendment.md (74 lines)

- `auth.login_attempt` formally added to the D-14 taxonomy (closes RESEARCH §16 open question 1).
- Four-row `auth.*` event table: `attempt` (Phase 1+) / `succeeded` (Phase 2) / `failed` (Phase 2) / `logout` (Phase 2) with the fields beyond the standard set.
- `app/events.py` declared canonical source — code MUST import the constant, not hard-code the literal string. Plan 07 already follows this; the ADR is the durable record.
- Alternatives considered: rename to `auth.login_stub`, drop the event, inline into CONTEXT.md — all rejected with rationale.

### app/static/js/alpine-components/__init.js

- Commented-out registration pattern reference: `Alpine.data('counter', () => ({ count: 0, increment() { ... } }))`.
- Two-way binding recipe under the CSP build (`:value="text"` + `@input="setText($el.value)"`) — replaces unavailable `x-model`.
- Zero live code — Phase 4+ adds the first real components and the corresponding `<script>` tag in `base.html`.
- `.gitkeep` anchors the directory.

## Verification

- All three ADRs contain the required Standard / Context / Decision / Consequences / Alternatives Considered / References sections.
- All three ADRs reference the canonical source files (`security_headers.py`, `middleware/__init__.py`, `events.py`).
- Alpine scaffold has `Alpine.data` only inside the block-comment example; no top-level executable code.
- All Plan acceptance criteria for the four tasks pass.

## Deviations

1. **Executor mode** — orchestrator-mediated (continuation of the Wave 2 / Wave 3 user-authorized override). Tasks 1–4 committed atomically in a single combined commit because all four are documentation-only with no test interdependencies; treating them as one logical unit keeps history readable.
2. **`@alpinejs/csp@3.14.9` pin** — propagated from Plan 08 SUMMARY into ADR 0001 verbatim.

## Open questions closed

- RESEARCH §16 open question 1 (`auth.login_attempt`): CLOSED by ADR 0003.
- RESEARCH §16 open question 2 (Alpine CSP version pin): CLOSED by ADR 0001 (3.14.9).

RESEARCH §16 open question 3 (Postgres FTS vs trigram for Phase 10) remains open — out of scope for Phase 1.
