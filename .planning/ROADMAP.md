# Snobbery — Roadmap

**Project:** Snobbery (self-hosted household coffee log)

## Milestones

- ✅ **v1.1 Initial Release** — Phases 0–14 (shipped 2026-05-25) — full detail in [`milestones/v1.1-ROADMAP.md`](./milestones/v1.1-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.1 Initial Release (Phases 0–14) — SHIPPED 2026-05-25</summary>

Built over 2026-05-16 → 2026-05-25. Per-phase goals, success criteria, and plan lists
are archived in [`milestones/v1.1-ROADMAP.md`](./milestones/v1.1-ROADMAP.md).

- [x] Phase 0: Foundation (5 plans) — two-container Docker stack, Postgres + extensions, first migration set, Tailwind CLI, config + logging
- [x] Phase 1: Middleware (10 plans) — proxy headers, CSP nonce, security headers, table-backed sessions, double-submit CSRF, slowapi, Jinja autoescape
- [x] Phase 2: Auth (11 plans) — race-protected `/setup`, argon2id login, session regeneration, admin gate
- [x] Phase 3: Encryption + Settings (6 plans) — MultiFernet service, typed `app_settings` reader, `api_credentials`
- [x] Phase 4: Shared Catalog (11 plans) — coffees/roasters/flavor-notes/equipment/recipes CRUD, recipe step builder, hardened photo pipeline
- [x] Phase 5: Brew Sessions (6 plans) — prefill form, tap-stars rating, tag input, drafts, CSV import/export
- [x] Phase 6: Analytics (Home Page) (3 plans) — pure-SQL derivations, HTMX lazy-load, signature plumbing
- [x] Phase 7: AI Services (7 plans) — provider abstraction, three-tier web-search rec, URL verification, advisory-lock regen, cold-start gate
- [x] Phase 8: Scheduler + Backups (3 plans) — APScheduler nightly AI refresh @ 00:00, nightly `pg_dump` + photos @ 02:00 with retention
- [x] Phase 9: Admin (6 plans) — user CRUD, credential vault, settings editor, backups, system + API-health panels
- [x] Phase 10: Global Search (3 plans) — Postgres trigram cross-entity search with per-user note scoping, debounced live results
- [x] Phase 11: PWA + Mobile Polish (5 plans) — manifest + service worker, bottom/top nav, card-list collapse, Guided Brew Mode, dark mode
- [x] Phase 12: Hardening + Tests (7 plans) — pytest smoke + unit suites, Playwright responsive smoke, CSP audit, CI
- [x] Phase 13: PWA UX Fixes (6 plans) — post-UAT polish: safe-area, create-fragment, dark toggle, cue controls, SW cache versioning
- [x] Phase 14: Audit Remediation (4 plans) — last-admin crash fix, SSRF gate, nightly session sweep, `/search` hardening, dead-code removal

</details>

## Progress

| Phase | Milestone | Plans | Status | Completed |
| --- | --- | --- | --- | --- |
| 0. Foundation | v1.1 | 5/5 | Complete | 2026-05 |
| 1. Middleware | v1.1 | 10/10 | Complete | 2026-05 |
| 2. Auth | v1.1 | 11/11 | Complete | 2026-05 |
| 3. Encryption + Settings | v1.1 | 6/6 | Complete | 2026-05-18 |
| 4. Shared Catalog | v1.1 | 11/11 | Complete | 2026-05 |
| 5. Brew Sessions | v1.1 | 6/6 | Complete | 2026-05-20 |
| 6. Analytics (Home Page) | v1.1 | 3/3 | Complete | 2026-05 |
| 7. AI Services | v1.1 | 7/7 | Complete | 2026-05-21 |
| 8. Scheduler + Backups | v1.1 | 3/3 | Complete | 2026-05-21 |
| 9. Admin | v1.1 | 6/6 | Complete | 2026-05-21 |
| 10. Global Search | v1.1 | 3/3 | Complete | 2026-05-22 |
| 11. PWA + Mobile Polish | v1.1 | 5/5 | Complete | 2026-05-23 |
| 12. Hardening + Tests | v1.1 | 7/7 | Complete | 2026-05-24 |
| 13. PWA UX Fixes | v1.1 | 6/6 | Complete | 2026-05-25 |
| 14. Audit Remediation | v1.1 | 4/4 | Complete | 2026-05-25 |

> Open verification/UAT debt deferred at milestone close is tracked in `STATE.md` → "Deferred Items".
</content>
