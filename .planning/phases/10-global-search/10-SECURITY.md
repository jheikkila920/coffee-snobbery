---
phase: 10-global-search
audited_at: 2026-05-22
auditor: gsd-security-auditor (claude-sonnet-4-6)
asvs_level: default
block_on: default
register_authored_at_plan_time: true
result: SECURED
threats_total: 7
threats_closed: 7
threats_open: 0
---

# Phase 10 — Global Search: Security Audit

## Result: SECURED

All 7 threats in the threat register are CLOSED. No mitigations were absent.
No unregistered threat flags were raised by the executor summaries.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-10-IDOR | Information Disclosure | mitigate | CLOSED | `app/services/search.py:279` — `BrewSession.user_id == user_id` is the explicit first `.where()` clause, commented `# ALWAYS first — T-10-IDOR`; `user_id` is the typed `run_search()` function arg, not a global or request attribute. Proving test: `tests/test_search.py:467` `test_brew_note_user_scoping` asserts User A cannot see User B's "secret Ethiopia mango" and User B can. |
| T-10-XSS | Tampering | mitigate | CLOSED | `app/services/search.py:87-90` — `highlight()` calls `markupsafe.escape()` on all three text slices (before, matched, after) before `Markup` composition; only the literal `<strong class='font-semibold'>` tag is raw. No `|safe` applied to any variable in `search_results.html` (one grep match is in the Jinja comment block at line 14, not in executable code). No `|safe` on variables in `base.html` (one match is in the line 1 comment). Proving test: `tests/test_search.py:562` `test_highlight_xss_safe` asserts `&lt;script&gt;` present and raw `<script>` absent. |
| T-10-SQLI | Tampering | mitigate | CLOSED | `app/services/search.py:129` — `pattern = f"%{query}%"` is passed exclusively via `Column.ilike(pattern)` (SQLAlchemy bound parameter). Grep for `text(f"` in search.py returns 0 matches. No raw SQL interpolation exists. Equipment token matching uses `Equipment.brand.ilike(f"%{t}%")` / `Equipment.model.ilike(f"%{t}%")` (bound params, not `text()`). |
| T-10-AUTHZ | Information Disclosure | mitigate | CLOSED | `app/routers/search.py:34` — `user: User = Depends(require_user)` on the `GET /search` endpoint; unauthenticated callers receive 401 (verified by VERIFICATION.md spot-check). Short-query guard at line 42 returns empty 200 only after authentication passes. |
| T-10-HDR-LEAK | Information Disclosure | mitigate | CLOSED | `app/templates/base.html:46` — `{% if request.state.user %}` wraps the entire `<header x-data="searchBar">` block; `{% endif %}` at line 151. Both `/login` and `/setup` extend `base.html` so the gate applies to both. Proving test: `tests/test_search.py:173` `test_header_auth_gate` asserts `hx-get="/search"` absent on `/login` and `/setup`. |
| T-10-CSP | Tampering (script injection) | mitigate | CLOSED | `app/static/js/alpine-components/search-bar.js` — no `eval(` or `new Function(` (grep returns 0 matches). Component registered inside `document.addEventListener('alpine:init', ...)` at line 19-20. `app/templates/base.html:28` — script tag: `<script defer src="/static/js/alpine-components/search-bar.js" nonce="{{ csp_nonce(request) }}">`, placed before the `@alpinejs/csp` core at line 34. `base.html:47` — `x-data="searchBar"` is a string reference (not an inline object literal; grep confirms no object-literal x-data). No `hx-on:` in executable template code (one match is in the line 1 comment). `app/static/css/tailwind.src.css:23-25` — `.htmx-indicator` rule present, not duplicated. |
| T-10-MIG | Denial of Service (index build) | accept | CLOSED | Accepted risk documented in migration file `app/migrations/versions/p10_search_indexes.py:29-33` — "NO CONCURRENTLY — Alembic wraps each migration in a transaction by default; CREATE INDEX CONCURRENTLY cannot run inside a transaction block... These tables have no production traffic at first Phase 10 deploy; a non-concurrent index build is safe and fast." |

---

## Unregistered Threat Flags

None. The executor summaries (10-01-SUMMARY.md, 10-02-SUMMARY.md, 10-03-SUMMARY.md) contain no `## Threat Flags` entries that map outside the registered threat IDs. The three SUMMARY files report: "No new trust boundaries" (10-01), "T-10-IDOR / T-10-XSS / T-10-SQLI / T-10-AUTHZ mitigated" (10-02), and "T-10-HDR-LEAK / T-10-CSP mitigated" (10-03).

---

## Implementation Notes

**T-10-XSS — striptags deviation:** The fragment renders catalog group primaries via `{{ result.primary|striptags }}` (not `{{ result.primary }}` as the plan specified). This is safe: `striptags` on an already-escaped `Markup` object strips the `<strong>` wrapper and emits plain text. No user-controlled HTML reaches the output. Brew notes render `{{ result.primary }}` directly (the Markup is fully escaped). This deviation was documented in 10-02-SUMMARY.md as an auto-fixed rendering bug, not a security regression.

**T-10-SQLI — equipment token matching:** The equipment query uses per-token `OR` matching (`Equipment.brand.ilike(f"%{t}%") OR Equipment.model.ilike(f"%{t}%")`) rather than the plan's `func.concat(...).ilike(pattern)` approach. Both use bound parameters exclusively. No `text()` interpolation. SQLI defense is equivalent.

---

## Accepted Risks Log

| Threat ID | Risk | Rationale |
|-----------|------|-----------|
| T-10-MIG | Brief table lock during index build (non-CONCURRENTLY) | Tables are empty/tiny at first Phase 10 deploy; household scale makes the brief lock acceptable. Documented in migration file and PLAN.md. |
