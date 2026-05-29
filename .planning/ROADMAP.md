# Snobbery — Roadmap

**Project:** Snobbery (self-hosted household coffee log)

## Milestones

- ✅ **v1.1 Initial Release** — Phases 0–14 (shipped 2026-05-25) — full detail in [`milestones/v1.1-ROADMAP.md`](./milestones/v1.1-ROADMAP.md)
- 🚧 **v1.2 Polish & Mobile-First** — Phases 15–22 (in progress)

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

### 🚧 v1.2 Polish & Mobile-First (In Progress)

**Milestone Goal:** Make Snobbery feel purpose-built and major-company polished — truly
mobile-first, AI consolidated into its own nav destination, and cleanly self-hostable by
other households.

- [x] **Phase 15: v1.1 Debt Cleanup** - Close carried debt so new v1.2 work sits on a clean, verified base (completed 2026-05-26)
- [x] **Phase 15.1: Catalog & Session Polish** (INSERTED) - Coffee catalog + brew session form cleanup: drop dead fields, fix edit, add multi-origin (completed 2026-05-27)
- [x] **Phase 16: Cafe Quick-Rate** - Add per-user cafe-log entity with analytics and AI integration (completed 2026-05-27)
- [x] **Phase 17: IA Restructure** - Move Admin off nav; add AI destination tab; simplify home page (completed 2026-05-28)
- [x] **Phase 18: Self-Host Packaging** - Publish prebuilt multi-arch image and complete operator documentation (completed 2026-05-28)
- [ ] **Phase 19: AI Page & Research/Predict** - Wire the AI page; add on-demand coffee research with predicted rating and charts (REOPENED 2026-05-29 — code review found 2 blockers incl. stored XSS; see 19-REVIEW.md, gap closure pending)
- [ ] **Phase 20: Guided Brew Polish** - Purpose-built mobile brewing coach with phase timer and water profiles
- [ ] **Phase 21: Mobile-First Full Rework** - Screen-by-screen audit and polish at 375px to major-company bar
- [ ] **Phase 22: Verification & Release** - Full suite green, Playwright smoke, tag v1.2.0, push GHCR image

## Phase Details

### Phase 15: v1.1 Debt Cleanup
**Goal**: All v1.1 carried debt is closed — the base is clean and verified before any new feature work begins
**Depends on**: Nothing (first phase of v1.2)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04, DEBT-05
**Success Criteria** (what must be TRUE):
  1. A fresh deploy writes backups and photos without any manual `chown` command (G-01 fixed in `entrypoint.sh`)
  2. `pytest tests/` runs green twice in a row with zero cross-module isolation failures (T-INFRA-1 closed)
  3. Every authenticated page shows persistent nav with user identity and a working sign-out, confirmed on a physical device
  4. All outstanding v1.1 human-UAT scenarios (Phases 01/02/07/11 and the Phase 14 375px search-sheet UAT) are executed and recorded
  5. Every `human_needed` verification is either closed with evidence or explicitly re-deferred with a written reason
**Plans**: 3 plans
Plans:
**Wave 1**
- [x] 15-01-PLAN.md — DEBT-01: entrypoint root→chown→gosu privilege drop (G-01 fix)
- [x] 15-02-PLAN.md — DEBT-02: test_setup_concurrent_race fix + CI double-run isolation guard

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 15-03-PLAN.md — DEBT-03/04/05: on-device nav/sign-out + human-UAT + human_needed closure ledger (incl. D-13 safe-area)

### Phase 15.1: Catalog & Session Polish (INSERTED)
**Goal**: The coffee catalog and brew session form are simplified, correct, and free of dead or redundant fields, so all downstream v1.2 feature work builds on a clean data model
**Depends on**: Phase 15
**Requirements**: CATALOG-01, CATALOG-02, CATALOG-03, CATALOG-04, CATALOG-05, CATALOG-06, CATALOG-07
**Success Criteria** (what must be TRUE):
  1. The edit-coffee modal renders at the same width as the create-coffee modal on desktop and all coffee edits save successfully (CATALOG-01; item #2 Save/Cancel may add CATALOG-08 after `/gsd-debug` scopes it)
  2. The `country` column is removed from `coffees` with a safe data migration into `origin`, and no UI exposes it (CATALOG-02)
  3. A coffee can be flagged as single-origin or blend and supports multiple structured origins, not a free-text string (CATALOG-03)
  4. The roast-level enum includes Nordic Light and Ultra Light (CATALOG-04)
  5. Varietal stays optional and supports multi-select with autocomplete from a seeded varietal list (CATALOG-05)
  6. A new brew session inherits the parent coffee's flavor notes by default, the user can remove inherited chips, and any flavor-note add or remove on the session is mirrored back to the parent coffee (CATALOG-06)
  7. Roast-freshness tracking is removed app-wide: schema column dropped, AI prompts cleaned, every UI surface scrubbed (CATALOG-07)
**Plans**: 5 plans
Plans:
**Wave 1**
- [x] 15.1-01-PLAN.md — CATALOG-02/03: multi-origin schema (coffee_origins join table) + data migration + form repeating rows + filter bar
- [x] 15.1-02-PLAN.md — CATALOG-07: roast-freshness removal sweep (drop bags.roast_date, scrub analytics + AI prompts + home + CSV)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 15.1-03-PLAN.md — CATALOG-04/05: roast-level enum widening + varietal m2m + autocomplete + seed (depends on 01 for coffee model surface)
- [x] 15.1-04-PLAN.md — CATALOG-06: brew-session flavor-note bidirectional sync + prefill + draft union-merge + CSV parity (depends on 02 for csv_io surface)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 15.1-05-PLAN.md — CATALOG-01: desktop edit-form mount routing + dual Edit buttons across all 5 entity forms (depends on 01/03 for coffee_form settled)
**UI hint**: yes
**Insertion reason**: items surfaced during Phase 15 use of the live app — see commit log + post-Phase-15 capture

### Phase 16: Cafe Quick-Rate
**Goal**: Users can log coffees tasted outside the home in ~20 seconds; those logs shape taste preferences and AI recommendations, while staying isolated from brew-parameter analytics
**Depends on**: Phase 15, Phase 15.1 (shared coffee schema must be clean before adding cafe_logs that mirror its fields)
**Requirements**: CAFE-01, CAFE-02, CAFE-03, CAFE-04, CAFE-05, CAFE-06
**Success Criteria** (what must be TRUE):
  1. User can log a cafe coffee with just a name and a rating in roughly 20 seconds
  2. User can optionally enrich a cafe log with brand/roaster, origin, brew method, notes, flavor notes, and a photo
  3. Cafe logs appear in a per-user list that is visually distinct from brew sessions
  4. Cafe-log ratings, flavor notes, and origin/roaster feed preference derivation and the AI input signature — subsequent AI runs reflect cafe taste data
  5. Cafe logs are absent from grind, ratio, temperature, and recipe sweet-spot analytics
  6. User can edit and delete their own cafe logs
**Plans**: TBD
**UI hint**: yes

### Phase 17: IA Restructure
**Goal**: Navigation reflects usage priority — Admin is out of the daily-use path, AI has a dedicated bottom-nav tab, and home is simplified to primary action affordances
**Depends on**: Phase 15
**Requirements**: IA-01, IA-02, IA-03, IA-04, IA-05, IA-06, DIST-07, AIX-08
**Success Criteria** (what must be TRUE):
  1. The bottom nav has no Admin tab; Admin is reachable via a button on the config/settings page only
  2. A new AI tab is present in the bottom nav and opens an AI page (shell wired; content completed in Phase 19)
  3. The home page shows primary action affordances with no AI recommendation card embedded in it
  4. After `/setup`, a new admin sees a clear in-page prompt to configure AI API keys (since Admin is no longer on the nav)
  5. When a user meets the cold-start threshold but no AI key is configured, the AI page shows a prominent link to the Admin config page — distinct from the not-enough-data empty state
  6. After a rebuild and deploy, installed PWAs pick up the updated nav without a manual cache clear
**Plans**: 5 plans
Plans:
**Wave 1**
- [x] 17-01-PLAN.md — IA-01/IA-02 nav reshape: drop bottom Admin tab, add AI tab, add Config Admin entry (D-01/D-02/D-04/D-05/D-17/D-18)
- [x] 17-02-PLAN.md — IA-03/IA-04/IA-06 home composition: greeting, eager Top Coffees no-floor, drop AI surfaces + cold-start meter (D-06..D-11)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 17-03-PLAN.md — DIST-07 admin AI-key setup banner: sessionStorage dismiss, admin+no-key gate, /admin/credentials button (D-19/D-21)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 17-04-PLAN.md — IA-02/IA-03/AIX-08 /ai page shell: three-branch state machine, AIX-08 admin + non-admin callouts, research-coming-soon stub (D-03/D-12/D-13/D-14/D-15/D-16/D-20)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 17-05-PLAN.md — IA-05 phase close: container rebuild, full suite, ruff gates, on-device PWA cache-freshness verification (manual checkpoint)
**UI hint**: yes

### Phase 18: Self-Host Packaging
**Goal**: A new operator can deploy Snobbery on their own VPS with no `docker compose build` step and a complete, accurate guide
**Depends on**: Phase 15 (G-01 fix landed)
**Requirements**: DIST-01, DIST-02, DIST-03, DIST-04, DIST-05, DIST-06
**Success Criteria** (what must be TRUE):
  1. The published `docker-compose.yml` references a `image: ghcr.io/...` tag and works without a local build step
  2. Pushing a version tag triggers the release CI workflow and publishes a versioned multi-arch (amd64 + arm64) image to GHCR
  3. The README contains a complete from-zero walkthrough: prerequisites, env vars, first run, and upgrade path
  4. The deploy guide covers Nginx Proxy Manager setup, including the `TRUSTED_PROXY_IPS` env var and shared docker network requirement
  5. A fresh install auto-runs migrations on first start and lands the operator at `/setup`
  6. `.env.example` documents every required env var with generation hints for `APP_SECRET_KEY` and `APP_ENCRYPTION_KEY`
**Plans**: 5 plans
Plans:
**Wave 1**
- [x] 18-01-PLAN.md — DIST-01 compose split: pin GHCR image, drop build:, drop test service, override.yml.example + ignores (D-04/D-05/D-06/D-08)
- [x] 18-02-PLAN.md — DIST-02 Dockerfile ARG APP_VERSION + OCI labels + system.py env-var fallback + pyproject 1.2.0 bump (D-12)
- [x] 18-03-PLAN.md — DIST-06 .env.example audit + NPM TRUSTED_PROXY_IPS prose (D-17)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 18-04-PLAN.md — DIST-02 release.yml: tag-triggered test -> multi-arch GHCR push, latest=auto, APP_VERSION build-arg (D-09/D-10/D-11/D-12/D-13)
- [x] 18-05-PLAN.md — DIST-03/04/05 README operator-first rewrite + CONTRIBUTING.md carve-out + CLAUDE.md pointers + DIST-05 smoke procedure (D-07/D-14/D-15/D-16/D-18/D-19/D-20)

### Phase 19: AI Page & Research/Predict
**Goal**: The AI page is fully wired with consolidated recommendations, on-demand coffee research, predicted personal rating, and trend charts — with cost controls that are non-negotiable
**Depends on**: Phase 17 (AI page shell and nav exist), Phase 16 (cafe logs feed preference derivation), Phase 15.1 (roast-freshness removed from AI inputs; multi-origin and varietal shape new preference prose)
**Requirements**: AIX-01, AIX-02, AIX-03, AIX-04, AIX-05, AIX-06, AIX-07, AIX-09, AIX-10, AIX-11, AIX-12, AIX-13, VIZ-01
**Success Criteria** (what must be TRUE):
  1. The AI page shows the coffee recommendation, equipment callout, and sweet-spots prose (relocated from home and other pages)
  2. User can type a coffee name and receive an AI-researched profile (origin, tasting notes, cited sources) grounded in live web search
  3. The prediction displays a rating range with a confidence level and visible reasoning — never a single number
  4. Repeated lookups of the same coffee return instantly from cache within the TTL window — no duplicate web-search charge
  5. The AI research UI shows the user's remaining daily quota and prevents calls when the limit is reached
  6. User can add a researched coffee directly to the wishlist from the result card
  7. AI responses stream to the user via SSE — no polling spinner
  8. Brew and preference trends are visible as charts (rating over time, flavor distribution) using a CSP-compatible chart library
**Plans**: 9 plans (7 executed + 2 gap-closure from 19-REVIEW.md)
Plans:

**Wave 1**
- [x] 19-01-PLAN.md — AIX-01/02/04/09/11/12: sse-starlette + 5 schemas (drop no_match) + 2 tables + migration + quota settings + Wave 0 tests

**Wave 2** *(blocked on Wave 1)*
- [x] 19-02-PLAN.md — AIX-11/13: _verify_buy_url 404/410 + archived-retry + recipe-prompt + no_match test rewrite + latency comments

**Wave 3** *(blocked on Wave 2)*
- [x] 19-03-PLAN.md — AIX-01/02/03/04/05/07/13: ai_quota + ai_research cache/prediction/two-phase-SSE generator
- [x] 19-04-PLAN.md — AIX-09/12/13: brew-improve SSE + preference-prose flow + scheduler rec_type loop

**Wave 4** *(blocked on Wave 3)*
- [x] 19-05-PLAN.md — AIX-01/03/05/07/12/13/VIZ-01: research SSE route + quota fragment + coach picker + improve-brew route + charts + latency query

**Wave 5** *(blocked on Wave 4)*
- [x] 19-06-PLAN.md — AIX-06/09/10/12/VIZ-01: /ai restructure + research/prefs/trends/coach fragments + Chart.js CDN + indicator CSS + improve-brew UI (human-verify)

**Wave 6** *(blocked on Wave 5)*
- [x] 19-07-PLAN.md — AIX-05/13: latency investigation + NPM proxy_buffering off doc + admin quota verification + phase-close gate (human-verify)

**Wave 7 — gap closure (REOPENED 2026-05-29, 19-REVIEW.md)**
- [ ] 19-08-PLAN.md — CR-01/CR-02/WR-06/IN-01/IN-03: render research + improve-brew SSE through autoescaped Jinja templates (fix stored XSS + broken coach card), reconcile cited_sources contract, regression tests

**Wave 8** *(blocked on Wave 7)*
- [ ] 19-09-PLAN.md — WR-01/WR-02/WR-03/WR-04/WR-05/IN-02: commit+reuse cache-hit prediction, bound prediction-regen cost, narrow except clauses, one format_reset helper, accepted-risk TOCTOU note
**UI hint**: yes

### Phase 20: Guided Brew Polish
**Goal**: Guided Brew Mode feels like a purpose-built mobile brewing coach — timer survives phone sleep, phases are coached step-by-step, and water is selected from named profiles
**Depends on**: Phase 15 (safe-area fix verified on-device before spreading to Guided Brew)
**Requirements**: GBREW-01, GBREW-02, GBREW-03, GBREW-04, GBREW-05, GBREW-06
**Success Criteria** (what must be TRUE):
  1. The Guided Brew timer continues counting accurately when the phone screen sleeps during a brew
  2. Guided Brew steps through recipe phases (bloom, pours) as timed, coached steps with phase-specific cues
  3. User can optionally record first-drip time and bloom time on any brew session
  4. Water type is chosen from a named water-profiles catalog instead of free text
  5. Guided Brew Mode passes the 375px mobile audit: correct touch targets, safe-area, no horizontal scroll
**Plans**: TBD
**UI hint**: yes

### Phase 21: Mobile-First Full Rework
**Goal**: Every screen meets the major-company mobile polish bar at 375px — correct touch targets, safe-area insets, no horizontal scroll, and a consistent visual language across the whole app
**Depends on**: Phase 15 (safe-area fix on-device verified), Phase 17 (nav stable), Phase 19 (AI page stable), Phase 20 (Guided Brew stable)
**Requirements**: MOBILE-01, MOBILE-02, MOBILE-03, MOBILE-04, MOBILE-05
**Success Criteria** (what must be TRUE):
  1. Every screen passes a 375px audit with no horizontal scroll and correct bottom (<768px) / top (>=768px) nav behavior
  2. All interactive controls meet touch-target sizing minimums and form inputs use at least 16px font (no iOS zoom-on-focus)
  3. Safe-area insets are correct in iOS PWA standalone mode across all screens, confirmed on a physical iPhone
  4. Form submission actions remain reachable above the bottom nav on every long form
  5. A user picking up the app for the first time on a phone describes it as feeling like a deliberately designed product
**Plans**: TBD
**UI hint**: yes

### Phase 22: Verification & Release
**Goal**: The v1.2 milestone is end-to-end verified, tagged, and the prebuilt image is live — the milestone is shippable
**Depends on**: Phase 18 (GHCR CI in place), Phase 19 (AI page complete), Phase 20 (Guided Brew complete), Phase 21 (mobile rework complete)
**Requirements**: (release gate — verifies all 42 v1.2 requirements are met; no new feature requirements)
**Success Criteria** (what must be TRUE):
  1. `pytest tests/` runs green with v1.2 acceptance behaviors covered
  2. Playwright 375px smoke passes on every new or reworked screen (AI page, cafe log, Guided Brew, water profiles)
  3. On-device verification confirms safe-area insets, PWA install flow, and bottom-nav behavior on a physical iPhone
  4. Pushing `git tag v1.2.0` triggers the release CI workflow and a versioned multi-arch image lands in GHCR
**Plans**: TBD

## Progress

**Execution Order:** 15 → 15.1 → 16 and 17 and 18 (16/17/18 can be sequenced or parallelized; 17 must precede 19; 16 must precede 19; 15.1 must precede 16 and 19) → 19 and 20 (parallel) → 21 → 22

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
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
| 15. v1.1 Debt Cleanup | v1.2 | 3/3 | Complete    | 2026-05-26 |
| 15.1. Catalog & Session Polish (INSERTED) | v1.2 | 5/5 | Complete    | 2026-05-27 |
| 16. Cafe Quick-Rate | v1.2 | 6/6 | Complete   | 2026-05-27 |
| 17. IA Restructure | v1.2 | 5/5 | Complete    | 2026-05-28 |
| 18. Self-Host Packaging | v1.2 | 5/5 | Complete   | 2026-05-28 |
| 19. AI Page & Research/Predict | v1.2 | 7/9 | Reopened (gap closure) | 2026-05-29 |
| 20. Guided Brew Polish | v1.2 | 0/TBD | Not started | - |
| 21. Mobile-First Full Rework | v1.2 | 0/TBD | Not started | - |
| 22. Verification & Release | v1.2 | 0/TBD | Not started | - |

> Open verification/UAT debt deferred at v1.1 close is tracked in `STATE.md` → "Deferred Items". Phase 15 closes it.
