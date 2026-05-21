---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: planning
stopped_at: Phase 9 context gathered
last_updated: "2026-05-21T21:38:34.825Z"
last_activity: 2026-05-21
progress:
  total_phases: 13
  completed_phases: 9
  total_plans: 62
  completed_plans: 62
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-16)

**Core value:** A returning user can log a brew in <30s and trust that the home page's recommendation is grounded in their actual log, not generic taste advice.
**Current focus:** Phase 08 — scheduler-backups

## Current Position

Phase: 9
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-21

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 57
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |
| 01 | 10 | - | - |
| 02 | 11 | - | - |
| 03 | 6 | - | - |
| 04 | 11 | - | - |
| 05 | 6 | - | - |
| 06 | 3 | - | - |
| 07 | 7 | - | - |
| 08 | 3 | - | - |

**Recent Trend:**

- No history yet

*Updated after each plan completion*
| Phase 05 P01 | 12 | 4 tasks | 10 files |
| Phase 05 P02 | 8 | 3 tasks | 5 files |
| Phase 05 P03 | 5 | 2 tasks | 2 files |
| Phase 05 P04 | 14 | 3 tasks | 5 files |
| Phase 05 P05 | 3 rounds | 3 tasks | 9 files |
| Phase 05 P06 | 2 rounds | 3 tasks | 10 files |
| Phase 07-ai-services P03 | 90 | 3 tasks | 2 files |
| Phase 07-ai-services P04 | 45 | 2 tasks | 2 files |
| Phase 07-ai-services P05 | 35 | 3 tasks | 3 files |
| Phase 07-ai-services P07 | 30 | 2 tasks | 8 files |
| Phase 08 P01 | 6 | - tasks | - files |
| Phase 08-scheduler-backups P03 | 6 | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Recent decisions from PROJECT.md Key Decisions table:

- Foundation: `bags`, `wishlist_entries`, brew yield/TDS columns, and `ai_recommendations` cost-observability columns all land in the first migration set — retrofitting later is the painful path
- Foundation: Tailwind via standalone CLI binary in Dockerfile (not CDN) so CSP can stay nonce-based without permanent `'unsafe-inline'`
- Foundation: HTMX 2.x (deviates from spec's 1.9 wording — spec predates 2.x stable)
- Foundation: Single uvicorn worker is non-negotiable; APScheduler in-process + module-level AI locks both require it
- Phase 1: CSRF via double-submit-cookie pattern (rotated-per-request breaks HTMX fragment swaps)
- Phase 3: `MultiFernet` from day one — rotation-ready encryption from first encrypted row
- Phase 7: AI streaming via polling, not SSE, in v1 — simpler, no `proxy_buffering off` requirement
- Phase 8: APScheduler `SQLAlchemyJobStore` + `misfire_grace_time=3600` + `coalesce=True` — defaults would silently miss every restart-bracketing nightly run
- Phase 5: tds_pct stored as WHOLE PERCENT (1.35 = 1.35%); GENERATED extraction_yield_pct = (yield * tds/100.0)/dose*100 yields whole-percent EY
- Phase 5: brew_sessions.user_id ondelete=RESTRICT (not CASCADE) — brew history never silently vanishes on a user delete; Phase 9 admin delete handles logs explicitly
- Phase 5: brew_sessions is the first per-user service — every read/update/delete scoped by user_id; update returns None / delete returns False for non-owned ids (router maps to 404, T-05-05 IDOR)
- Phase 5: equipment.usage_count maintained in the session write transaction — +1 per non-null FK on create, ±1 diff on edit, -1 on delete across all three FKs (Pitfall 6 no-drift)
- Phase 5: brew prefill ordering — source (D-08 named session OR D-04 last/last-with-coffee) then D-06 default bag then D-05 recipe-wins on the four template fields then always blank rating/observed/notes on /brew/new
- Phase 5: brew_drafts upsert via Postgres INSERT ON CONFLICT (user_id) DO UPDATE — atomic one-row-per-user, no read-then-write race on double autosave-on-blur
- [Phase ?]: Phase 5: brew CSV import is header-driven (csv.DictReader + case-insensitive alias map); Snobbery-native EXPORT_FIELDNAMES is the authoritative round-trip format, Beanconqueror aliases shipped TODO-confirm pending a real export file
- [Phase ?]: Phase 5: CSV formula injection (T-05-13) mitigated by prefixing leading = + - @ with a single quote on free-text export columns only; numeric columns untouched
- [Phase ?]: Phase 5: CSV import single-transaction (BREW-11) — refused/skipped rows never enter the txn, all accepted rows + D-09 notes commit once, DB error rolls back the whole batch (no partial commit)
- [Phase ?]: Phase 5: brew router is the first per-user ROUTER — handlers require_user-gated + scoped by request.state.user.id; cross-user session_id returns 404 via the service None sentinel (T-05-15 IDOR non-leak, not 403)
- [Phase ?]: Phase 5: brew create/update success responds 204 + HX-Redirect to /brew; POST /brew/draft is silent 204 and NOT CSRF-exempt; server draft exposed in /brew/new context for client localStorage-primary reconciliation (BREW-07)
- [Phase ?]: Phase 5: GET /brew/prefill is a dynamic re-prefill FRAGMENT reusing resolve_prefill — renders only prefill-dependent fields + D-11 advertised chips; rating/observed/notes deliberately absent so an in-progress entry is never clobbered
- Phase 5 (P05): brew form star colors deviate from UI-SPEC per user preference — selected bright amber, unselected dark espresso (better tap-feedback contrast on cream)
- Phase 5 (P05): app-wide form-control contrast pinned in `app/static/css/tailwind.src.css` `@layer base` — root cause was Tailwind Preflight `color:inherit` + `darkMode:'media'` flipping body ink while the UA input background stayed white (fixed `/login` and every form, not just brew); `custom.css` intentionally NOT created (MX-1 lock)
- Phase 5 (P05): D-07 water type implemented as a native `<datalist>` (suggestions + free-typed Other in one field) instead of select+toggle — CSP-safe, no 5th Alpine component
- Phase 5 (P05): added `POST /brew/draft/clear` (CSRF-enforced, 204) to `app/routers/brew.py` to back the Discard affordance — Discard wipes the namespaced localStorage key AND deletes the server backstop draft (BREW-07); cross-plan touch of the Plan-04-owned router
- Phase 5 (P05): prefill wrapper id is `#brew-prefill-region` (the hx-target); restore notice hidden pre-hydration via inline `style="display:none"` + `x-show` (no `[x-cloak]` rule exists)
- Phase 5 (P06): sessions-list filter panel is a native collapsed `<details>` on BOTH desktop and mobile (collapsed by default), per explicit user preference — CSP-safe, zero JS; replaces the Phase-4 always-visible bar / Alpine toggle
- Phase 5 (P06): one `_parse_list_filters` helper feeds BOTH `GET /brew` and `GET /brew/export`, so "Export CSV" is always exactly the currently-filtered view (D-15) — no filter-logic drift between the two routes
- Phase 5 (P06): the `hx-swap-oob` export-link sync anchor is gated by an `is_fragment` flag emitted ONLY on the HX-Request branch — keeps one persistent Export button on full-page `{% include %}` render while still syncing its href on every filter swap
- Phase 5 (P06): import isinstance guard uses `starlette.datastructures.UploadFile` (not `fastapi.UploadFile`) — `request.form()` returns the Starlette type; the FastAPI class is a subclass so guarding on it wrongly refused valid uploads (Rule-1 bug caught under TDD)
- Phase 5 (P06): app-wide readable anchor color pinned in `tailwind.src.css` `@layer base` (espresso-700 light / espresso-100 dark) — Preflight strips the UA anchor color; cross-cutting fix beyond this plan's files
- Phase 5 (P06): "Discard changes" now returns to `/brew` (sessions list), not `/` (home) — a deliberate cross-plan touch of 05-05-owned `brew-draft.js` + `brew_form.html`, now that `GET /brew` exists
- [Phase ?]: Phase 8 Wave 0: import-guard skip over xfail for undefined symbols keeps collection clean with zero false passes

### Pending Todos

- **Inline "add new coffee" from the brew form coffee select** — while logging a brew, allow adding a coffee not yet in the shared catalog without leaving the form (inline create from the coffee `<select>`). Requested by John during Plan 05-05 verification. Cross-cutting UX enhancement; catalog CRUD is Phase 4 scope — does NOT belong to Phase 5. (No `.planning/todos/` dir exists, so tracked here + in 05-05-SUMMARY follow-ups.)

### Blockers/Concerns

Three plan-phase research flags carried forward:

- Phase 1: prototype Alpine CSP build to confirm `'unsafe-eval'` can be avoided
- Phase 7: confirm citation-block projection and decide polling-vs-SSE
- Phase 10: prototype Postgres FTS vs `pg_trgm` and pick one
- Phase 11: prototype iOS Wake Lock fallback (silent audio loop vs NoSleep.js)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260519-ql9 | Codex review bucket-A fixes (duplicate-name 500→inline error, stale Makefile smoke head, CSRF docstring) | 2026-05-20 | e37cdf3, e9184c2, 9678787 | [260519-ql9-codex-bucket-a-fixes](./quick/260519-ql9-codex-bucket-a-fixes/) |
| 260520-ite | Harden Phase 5 audit findings: W-01 CSV upload Content-Length pre-check, W-02 widen Jinja safety test to all templates | 2026-05-20 | e4f1cf5, ccf98f3 | [260520-ite-harden-phase-5-security-audit-findings-w](./quick/260520-ite-harden-phase-5-security-audit-findings-w/) |
| 260520-qov | Brighten brew-rating stars from dark espresso to amber-400 (home cards + sessions list) | 2026-05-20 | 5c96ec8 | [260520-qov-brighten-rating-stars-amber](./quick/260520-qov-brighten-rating-stars-amber/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Deploy (infra) | G-01: VPS volumes are root-owned — next deploy needs a one-time `docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data` (or recreate empty volumes) so the app user can write backups + photos. Dockerfile now creates app-owned mountpoints for fresh volumes; existing VPS volumes predate the fix. | open | 2026-05-21 (Phase 08) |

## Session Continuity

Last session: 2026-05-21T21:38:34.800Z
Stopped at: Phase 9 context gathered
Resume file: .planning/phases/09-admin/09-CONTEXT.md
Next: Rebuild container and verify paste-rank, wishlist, equipment button at 375px mobile viewport.
