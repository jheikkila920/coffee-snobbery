# Snobbery

## What This Is

Snobbery is a self-hosted household coffee log for pour-over enthusiasts who care about beans, grind, water, and ratio. Multiple users share a household catalog (coffees, equipment, recipes, roasters, flavor notes) but keep separate brew session logs and AI-driven recommendations. Built primarily for John + Farrah's household; deployed to a VPS behind an existing NGINX reverse proxy.

## Core Value

A returning user — phone in hand, kettle nearby — can log a brew session in under 30 seconds and trust that the home page's "what to buy next" recommendation is grounded in their actual log, not generic taste advice.

## Current Milestone: v1.2 Polish & Mobile-First

**Goal:** Make Snobbery feel purpose-built and major-company polished, truly mobile-first, with AI consolidated into its own destination and the app cleanly self-hostable by others.

**Target features:**
- v1.1 debt cleanup (early phase): G-01 VPS chown, T-INFRA-1 test isolation, Phase 11 nav/sign-out verify, pending human UAT, clear `human_needed` verifications
- Self-host packaging: prebuilt image to a registry (no `docker compose build` for end users), thorough deploy doc including NPM setup, better README, simpler first-run
- Mobile-first audit + rework of every screen at 375px to a major-company polish bar
- IA restructuring: Admin off bottom nav (to a config-page button under Flavor Notes), new AI page on bottom nav consolidating all AI features, simplified action-button home (home/AI/Core-Value split decided during UI design)
- Guided Brew Mode polish (purpose-built mobile feel)
- New capabilities, research-driven: Beanconqueror-inspired parity (selected subset), cafe quick-rate (no-recipe coffee log: brand/name, info, brew method, rating), AI research-a-coffee + predict-rating-from-preferences

**Deferred to v2.0+:** public SaaS, hundreds of users, isolated per-user databases, public signup, invite-code multi-user. Breaks roughly six locked invariants (single worker, shared catalog, no-email, household-scale cost model); a product pivot, not a polish milestone.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**v1.1 Initial Release (shipped 2026-05-25)** — all 116 mapped requirements across Foundation, Auth, Security, Data Model, Brew UX, Catalog, Admin, Home/Analytics, AI, Search, Mobile/PWA, Aesthetic, and Testing shipped. Full traceability table archived in [`milestones/v1.1-REQUIREMENTS.md`](./milestones/v1.1-REQUIREMENTS.md). Headline capabilities now live:

- ✓ Two-container Docker stack behind NGINX, auto-migrations, single uvicorn worker — v1.1
- ✓ Setup/login/admin auth (argon2id, session regeneration, MultiFernet-encrypted API keys) — v1.1
- ✓ Full security posture: nonce-CSP, security headers, double-submit CSRF, hardened uploads — v1.1
- ✓ Shared catalog (coffees/roasters/flavor-notes/equipment/recipes) + per-user brew logging with sub-30s prefill — v1.1
- ✓ Analytics home page (pure-SQL preference derivations, HTMX lazy-load) — v1.1
- ✓ AI differentiator: three-tier web-search coffee rec with verified URLs, SSRF-hardened, signature-based nightly regen — v1.1
- ✓ Admin (users, credential vault, settings, backups, system + API-health) — v1.1
- ✓ APScheduler nightly AI refresh + `pg_dump`/photos backups with retention — v1.1
- ✓ Postgres trigram global search with per-user note scoping — v1.1
- ✓ Installable PWA (service worker, bottom/top nav, dark mode, Guided Brew Mode) — v1.1
- ✓ Test suite (~25.8k LOC) + Playwright responsive smoke + CI — v1.1

**Validation caveat:** shipped is not the same as user-confirmed-valuable. Several phases retain `human_needed` verification and pending human UAT (see Known Gaps below) — these are deferred, not closed. Move items to a stronger "confirmed valuable" footing as on-device UAT is completed.

### Active

<!-- Current scope. Building toward v1.2 (see Current Milestone above). REQUIREMENTS.md holds the REQ-ID breakdown once defined. -->

v1.2 Polish & Mobile-First (in planning). High-level scope:
- [ ] v1.1 debt cleanup (G-01, T-INFRA-1, Phase 11 nav verify, human UAT, human_needed sign-offs)
- [ ] Self-host packaging (prebuilt image, deploy/NPM docs, README, simpler first-run)
- [ ] Mobile-first audit + rework of every screen to a major-company polish bar
- [ ] IA restructuring (Admin off nav, new AI page, simplified home)
- [ ] Guided Brew polish
- [ ] Beanconqueror-inspired parity (subset, post-research)
- [ ] Cafe quick-rate (no-recipe coffee log)
- [ ] AI research-a-coffee + predict-rating

**Still-deferred candidates (not committed to v1.2):**
- [ ] Inventory management (bag count, depletion tracking) — re-evaluate against Beanconqueror research
- [ ] PWA offline write queue + sync — v2
- [ ] SSE streaming for AI responses — could fold into the AI-page rework if cheap; else defer
- [ ] Per-user/month AI cost ceiling — revisit if on-demand AI research/predict cost surprises

### Known Gaps (deferred at v1.1 close)

<!-- Acknowledged debt carried past the milestone, not closed. Also in STATE.md "Deferred Items". -->

- [ ] Human UAT pending: Phase 01 (3 scenarios), 02 (1), 07 (2), 11 (3); Phase 09 partial
- [ ] `human_needed` verification: Phases 01, 02, 07, 09, 10, 11
- [ ] Phase 14 manual UAT: 375px search full-screen sheet behavior + p95 latency
- [ ] Phase 11 nav + sign-out: 11-03 marked complete but project memory flags a possible gap — verify on-device
- [ ] G-01: VPS named volumes are root-owned — next deploy needs one-time `chown -R app:app /app/data`
- [ ] T-INFRA-1: full-suite test isolation gaps (catalog TRUNCATE teardown + settings cache clear)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Public registration / sign-up flow — household app, admin provisions users
- OAuth / SSO / magic links — username+password is sufficient at household scale
- JWT-based auth — signed session cookies are simpler and adequate
- Mobile native app — PWA covers the install + offline case
- Multi-tenant / household separation — single deployment = single household
- Subscription billing — self-hosted, no revenue model
- Email notifications — no SMTP plumbing, no use case at household scale
- Real-time WebSockets — HTMX SSE for AI streaming is sufficient
- Social features, sharing, public profiles — actively counter to the snobbery aesthetic
- Coffee shop / cafe discovery features — out of domain
- Inventory management (bag count, depletion tracking) — maybe v2, not core v1
- Separate frontend build pipeline (React/Vue/Svelte/Node) — server-rendered Jinja + HTMX is the chosen stack
- SQLite — Postgres is required for full-text search, JSONB, and concurrent multi-user writes
- PWA offline write queue — v1 ships cached read shell only; offline writes show a clear error. Queue + sync deferred to v2.
- Per-user/day or per-month AI cost ceiling — signature-based regen is the cost control at household scale; revisit if costs surprise
- Full per-router test coverage — v1 is smoke + critical paths only; expand if regressions become a pattern
- Real-time scraper or product index — AI uses web search at request time, no background ingestion
- Public/hosted multi-user (signup link, hundreds of users, isolated per-user data) — evaluated for v1.2 and deferred; breaks the single-worker, shared-catalog, no-email, and household-scale cost invariants. A potential v2.0 pivot, not a minor milestone.

## Context

**Shipped v1.1 (2026-05-25):** the complete v1 product is built and deployed. ~20,900 LOC Python (`app/`) + 84 Jinja templates + 8 Alembic migrations, backed by ~25,800 LOC of tests. 576 commits over 9 days. Pushed to `origin/main` (`30d25de`).

**Household scope:** Two users today (John, Farrah). Designed for that scale; not engineered for >10 users.

**Phone-first:** ~90% of use is phone-in-hand at the kettle. Desktop is secondary. Every UX decision evaluated at 375px first.

**Deployment shape:** Self-hosted on John's existing VPS — the shared n8n box where Nginx Proxy Manager (containerized) owns 80/443. Snobbery attaches as an NPM Proxy Host → `coffee-snobbery:8000` over the shared docker network; `TRUSTED_PROXY_IPS=*` is required or Secure cookies break. App listens on `localhost:8080` locally.

**AI flows are the differentiator.** The non-AI build is a competent household log; the AI flows (live coffee recommendation with web search and verified URL, alternative-brewer callout, sweet-spots prose) are why this exists instead of a spreadsheet.

**Cost discipline matters.** Web search is expensive. The signature-based regeneration design is load-bearing for keeping the bill sane. Don't break it.

**Known debt at v1.1:** human UAT and `human_needed` verifications remain open on several phases; the VPS data-volume chown (G-01) and full-suite test-isolation (T-INFRA-1) items are unresolved. See Known Gaps.

## Constraints

- **Tech stack**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 — locked. No React/Vue/Svelte. No SQLite. No JWT. No npm build pipeline.
- **Frontend**: Jinja2 templates + HTMX + Tailwind (standalone CLI, v3) + Alpine.js — locked. Custom CSS only when utilities can't cover it (lives in `app/static/css/custom.css`).
- **Auth**: argon2-cffi for password hashing, signed session cookies via itsdangerous, Fernet (`cryptography`) for API key encryption — locked.
- **Deployment**: Docker Compose with two services (`coffee-snobbery`, `coffee-snobbery-db`), single VPS behind existing NGINX (Nginx Proxy Manager). Migrations run automatically on container start.
- **Container naming**: `coffee-snobbery` (web), `coffee-snobbery-db` (db), `coffee-snobbery-net` (network). Volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups`.
- **Scheduling**: APScheduler in-process. No external worker (no Celery / RQ / cron container).
- **Concurrency model**: low — household scale. Synchronous FastAPI handlers are fine where they keep code simpler; async where it pays for itself (AI calls).
- **Mobile-first hard rule**: any UI must be tested at 375px viewport before being declared done. Bottom nav <768px, top nav ≥768px.
- **Security**: CSRF on all state-changing forms, full security header set on every response, autoescaping on every Jinja template. No exceptions.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use existing `snobbery-gsd-prompt.md` as the canonical idea document | The spec is detailed and load-bearing; rewriting it would lose nuance. CLAUDE.md adds the operational layer. | ✓ Good — spec drove the whole build |
| Greenfield build (no prior scaffold to integrate) | Confirmed by John during init questioning. | ✓ Shipped v1.1 |
| Defer PWA offline write queue to v2 | Service-worker write sync + conflict resolution is non-trivial; household app rarely brews offline. | — Still deferred (v2) |
| Cost control via signature-based regen only — no separate AI token ceiling | Household scale + nightly cadence + manual refresh is naturally bounded. | ✓ Shipped v1.1 — revisit if costs surprise |
| Test posture: smoke + critical-path units | Acceptance-criteria smoke + unit coverage on the load-bearing services. | ✓ Shipped v1.1 (~25.8k LOC tests + CI) |
| Aesthetic: warm + minimalist + system-preference dark mode | Matches the "snobbery" tone without gimmicks. | ✓ Shipped v1.1 — Phase 13 added a manual 3-state toggle |
| Single-scrollable brew session form with aggressive prefill (not stepped) | Returning user logging session N+1 only fills rating/notes. | ✓ Shipped v1.1 (sub-30s path) |
| AI: Anthropic by default, OpenAI fallback; both must support web search | Per spec; SDK web-search availability verified at install. | ✓ Shipped v1.1 |
| Search implementation: FTS vs trigram decided at plan-phase | Both viable; punted to the phase that builds search. | ✓ trigram (`pg_trgm`) chosen — Phase 10 |
| Deviate from spec: HTMX 2.x, not 1.9 | HTMX 2.x is stable; spec wording predates the release. | ✓ Good — 2.0.10 in production |
| Deviate from spec: Tailwind standalone CLI binary, not CDN | v4 Play CDN forces `unsafe-inline`, blocking nonce-CSP. CLI is a single executable, no npm. | ✓ Shipped v1.1 — built on Tailwind **v3** (JS config, `darkMode:'selector'`) |
| Add `bags` instance table to v1 Foundation | Bag-as-instance keeps sweet-spots-by-roast-date reliable across reorders. | ✓ Shipped v1.1 (migration 1) |
| Add `wishlist_entries` table to v1 | AI coffee-rec card needs an "Add to wishlist" landing. | ✓ Shipped v1.1 |
| Add refractometer columns to `brew_sessions` (yield/TDS/EY) | Optional fields signal audience-awareness; EY is a GENERATED whole-percent column. | ✓ Shipped v1.1 |
| AI streaming via polling, not SSE, in v1 | Simpler, no `proxy_buffering off` at NGINX, easier to debug. | ✓ Shipped v1.1 — SSE deferred (still unbuilt) |
| CSV import alongside export, scope-limited | Imports only brew sessions; refuses rows where coffee/bag not in catalog. | ✓ Shipped v1.1 |
| Cold-start AI: friendly empty state with progress meter | Gate AI at ≥3 sessions and ≥5 distinct flavor notes per user. | ✓ Shipped v1.1 |
| Admin API health panel (not in spec) | Surfaces silent AI failures (deprecated model, revoked key, quota). | ✓ Shipped v1.1 (Phase 9) |
| Server-side draft autosave-on-blur as iOS ITP backstop | localStorage alone loses drafts after 7 days of ITP inactivity. | ✓ Shipped v1.1 |
| Single uvicorn worker; document loudly | APScheduler in-process + module-level AI locks require single-process. | ✓ Good — enforced + documented in 3 places |
| CSRF via double-submit-cookie pattern | Rotated-per-request tokens break HTMX on second POST. | ✓ Good — stable across HTMX swaps |
| `MultiFernet` from day one, not single Fernet | Rotation-ready encryption from the first migration. | ✓ Shipped v1.1 |
| APScheduler `SQLAlchemyJobStore` + `misfire_grace_time=3600` + `coalesce=True` | Defaults silently lose jobs across restarts. | ✓ Shipped v1.1 (Phase 8) |
| Deploy behind Nginx Proxy Manager on the shared n8n box | No host nginx; NPM container owns 80/443. `TRUSTED_PROXY_IPS=*` required. | ✓ Good — documented deployment topology |
| Execute Phase 14 directly on `main` (branch-policy exception) | John's explicit call; recorded as a verification override. | ⚠ Acceptable once — prefer feature branches for auth/security work |
| v1.2 scope: self-host-friendly distribution, not multi-user | Public/invite multi-user breaks ~6 locked invariants (single worker, shared catalog, no email, cost model); a v2.0 pivot | — Pending (v1.2 in planning) |
| v1.2: mobile-first audit + rework, not rewrite | App is already mobile-first; a rewrite throws away a working v1.1 at high risk | — Pending |
| v1.2: consolidate AI to its own bottom-nav page; Admin off nav | Admin is rare-access; frees a nav slot; AI is the differentiator and deserves a destination | — Pending |
| v1.2: home/AI split + Core Value wording deferred to UI design | Needs mockups before deciding whether the what-to-buy-next rec leaves the home page | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-25 — v1.2 Polish & Mobile-First milestone started. Direction: self-host-friendly distribution (not multi-user), mobile-first audit + rework (not rewrite), AI consolidated to its own bottom-nav page, v1.1 debt folded in early. Public/hosted multi-user deferred to v2.0. v1.1 archive preserved in milestones/v1.1-REQUIREMENTS.md, milestones/v1.1-ROADMAP.md, and milestones/v1.1-phases/. Next: research -> requirements -> roadmap.*
