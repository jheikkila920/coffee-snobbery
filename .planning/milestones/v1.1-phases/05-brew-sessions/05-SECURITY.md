---
phase: 5
slug: brew-sessions
status: verified
threats_open: 0
asvs_level: 2
created: 2026-05-20
---

# Phase 5 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Threats authored at plan time across Plans 01–06; mitigations verified against the implementation by gsd-security-auditor.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client form / CSV → Pydantic schema | Untrusted numeric/text input; ranges + Decimal step + `extra="forbid"` gate it | dose, ratio, rating, notes, CSV rows |
| app → Postgres (DDL/DML) | EY is the DB-owned GENERATED source of truth; app must never write it | extraction_yield_pct |
| router → service (session_id, user_id) | Service scopes every read/write/delete by user_id; a session_id alone never grants access | session ownership |
| URL path /brew/{id} → service | session_id from the URL checked for ownership before any read/write | session ownership |
| draft payload (client JSON) → brew_drafts | Stored opaque, never eval'd, keyed by server-derived user_id | draft autosave blob |
| uploaded CSV bytes → importer | content-type + size guard before buffering; decode defensively; never eval row data | import file |
| import row fields → SQL resolution | Name matches parameterized; user_id never taken from the file | coffee/bag/flavor-note names |
| export cells → downstream spreadsheet | Exported free-text could carry a formula payload when opened in Excel | notes, names |
| filter query params → SQL | Untrusted filters parameterized in list/export queries | list/export filters |
| template-rendered strings → DOM | Prefill values, chip names, refused reasons autoescaped (no `\|safe`) — stored-XSS defense | user text, refused reasons |
| Alpine component config → behavior | Config via `data-*` only (CSP build); no inline JS expressions | component config |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-05-01 | Tampering / Elevation (mass assignment) | BrewSessionCreate | mitigate | `ConfigDict(extra="forbid")` `schemas/brew_session.py:77`; user_id & EY not schema fields; `routers/brew.py:158-160` never reads them | closed |
| T-05-02 | Tampering (rating rounding) | rating field | mitigate | `Decimal` + `multiple_of=0.25` `schemas/brew_session.py:96`; `Numeric(3,2)` `models/brew_session.py:125` | closed |
| T-05-03 | Integrity (EY divergence) | extraction_yield_pct | mitigate | `Computed(...persisted=True)` `models/brew_session.py:118-122`; `GENERATED ALWAYS AS ... STORED` migration `:154-157`; never set in app | closed |
| T-05-04 | Denial of input (unbounded numeric) | numeric fields | mitigate | `gt/ge/le` ranges on every numeric Field `schemas/brew_session.py:89-93` | closed |
| T-05-05 | Elevation / Info disclosure (IDOR) | get/update/delete session; prefill; drafts | mitigate | All queries filtered by `by_user_id` `services/brew_sessions.py:231,272,299,426`; drafts `services/brew_drafts.py:60-62` | closed |
| T-05-06 | Tampering (SQLi) | list/prefill queries | mitigate | Parameterized `select().where(...)` `services/brew_sessions.py:322,354-357`; no string SQL | closed |
| T-05-07 | Integrity (usage_count drift) | edit/delete | mitigate | Same-transaction `_adjust_usage_counts` `services/brew_sessions.py:107-125,205-208,246-247,277-284` | closed |
| T-05-08 | Info disclosure (draft cross-user, server) | brew_drafts | mitigate | `unique=True` on user_id `models/brew_draft.py:43-45`; ops keyed by user_id `services/brew_drafts.py:60-62,72` | closed |
| T-05-09 | Tampering (SQLi — name resolution) | coffee/bag/flavor-note resolve | mitigate | ORM `select().where(name == ...)` `services/csv_io.py:226-236` | closed |
| T-05-10 | Elevation (mass assignment on import) | import row | mitigate | `user_id=by_user_id` `services/csv_io.py:422`; EY never in constructor `:421-440`; `brew_csv` extra=forbid | closed |
| T-05-11 | DoS (oversized upload) | import upload | mitigate | content-type + `MAX_CSV_BYTES` ceiling `routers/brew.py:571-581` (see W-01) | closed |
| T-05-12 | Integrity (partial commit) | import | mitigate | Single `commit()` after all `add()` + `rollback()` on error `services/csv_io.py:447-456` | closed |
| T-05-13 | Tampering (CSV formula injection) | export | mitigate | `_neutralize_formula` prefixes `= + - @` `services/csv_io.py:513-521,591-607` | closed |
| T-05-14 | Info disclosure (export scoping) | export query | mitigate | `where(user_id == by_user_id)` `services/csv_io.py:561` | closed |
| T-05-15 | Elevation / Info disclosure (IDOR — router) | GET/POST /brew/{id}, /brew/new?from= | mitigate | user-scoped + `HTTPException(404)` `routers/brew.py:805-807,861-863,624-635` | closed |
| T-05-16 | Tampering / Elevation (mass assignment — POST) | POST /brew payload | mitigate | `_parse_form_payload` never reads user_id/EY `routers/brew.py:158-160`; user_id from `user.id` `:763-783` | closed |
| T-05-17 | Spoofing (CSRF) | POST /brew, /brew/{id}, /brew/draft | mitigate | hidden token `brew_form.html:100-101`; global header `htmx-listeners.js:34-38`; no route exempt | closed |
| T-05-18 | Info disclosure (server draft cross-user) | get_draft | mitigate | `where(user_id == by_user_id)` `services/brew_drafts.py:60-62` | closed |
| T-05-18b | Info disclosure / IDOR (prefill) | GET /brew/prefill | mitigate | `require_user` + `resolve_prefill(by_user_id=user.id)` `routers/brew.py:661-663,683-685` | closed |
| T-05-19 | Tampering (stored XSS) | brew_form.html | mitigate | no `\|safe`; autoescape ON; `tests/ci/test_no_unsafe_jinja.py` (see W-02) | closed |
| T-05-20 | Code injection (CSP bypass) | Alpine components + template | mitigate | no `x-model`/inline `hx-on:`/`hx-vals='js:'`; `data-*` config; nonce'd scripts | closed |
| T-05-21 | Spoofing (CSRF — autosave) | brew-draft.js | mitigate | `htmx.ajax('POST','/brew/draft')` `:160`; token via `htmx-listeners.js:34-38` | closed |
| T-05-22 | Info disclosure (shared-device draft, client) | localStorage | mitigate | key `snobbery:draft:brew:<user_id>` `brew-draft.js:35`; cleared on submit `:197-201` | closed |
| T-05-23 | Data integrity (EY editable from form) | brew_form.html | mitigate | EY read-only `<span>`, no input `brew_form.html:253-260`; never parsed | closed |
| T-05-24 | Info disclosure / IDOR | GET /brew, GET /brew/export | mitigate | `by_user_id=user.id` `routers/brew.py:487-488,531-532`; `test_list_user_scoped` | closed |
| T-05-25 | Tampering (SQLi — filters) | list/export filters | mitigate | parameterized `select().where(...)` `services/brew_sessions.py:322-336` | closed |
| T-05-26 | Spoofing (CSRF — import) | POST /brew/import | mitigate | hidden token `brew_import.html:23`; not exempt `routers/brew.py:552-584` | closed |
| T-05-27 | DoS (oversized upload — import) | POST /brew/import | mitigate | content-type + size ceiling `routers/brew.py:571-581` (see W-01) | closed |
| T-05-28 | Tampering (stored XSS) | csv_import_results.html | mitigate | no `\|safe` `csv_import_results.html:25,30,36`; autoescape ON (see W-02) | closed |
| T-05-29 | Tampering (downstream — export) | exported CSV in Excel | mitigate | inherited `_neutralize_formula` `services/csv_io.py:513-521,591-607` | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|

No accepted risks.

---

## Audit Findings (non-blocking)

Two warnings were raised during verification. Both are assessed CLOSED for their registered threats at ASVS Level 2 and recorded here for awareness — neither blocks phase advancement.

### W-01 — Upload size ceiling checked post-read (T-05-11, T-05-27) — REMEDIATED 2026-05-20 (commit e4f1cf5)

`routers/brew.py` `import_sessions` originally called `await upload.read()` then checked `len(raw_bytes) > MAX_CSV_BYTES`, so the full body (up to 5 MiB) was buffered before rejection. **Fixed:** a `Content-Length` header pre-check now runs as the first statement, before `await request.form()`, rejecting oversized uploads with the existing "too large" error before the body is buffered. The post-read length check is retained as defense-in-depth for chunked / lying-Content-Length clients. (quick task 260520-ite)

### W-02 — CI `|safe` grep test does not cover `app/templates/fragments/` (T-05-19, T-05-28) — REMEDIATED 2026-05-20 (commit ccf98f3)

`tests/ci/test_no_unsafe_jinja.py` originally scanned only `app/templates/pages/`. **Fixed:** `PAGES_DIR` renamed to `TEMPLATES_DIR = Path("app/templates")` so the rglob now covers `pages/`, `fragments/`, and any future subdir; forbidden-pattern logic unchanged. Test passes at 43/43 templates (pages + fragments + base.html). (quick task 260520-ite)

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-20 | 30 | 30 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-20
