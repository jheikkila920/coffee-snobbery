# Snobbery

## What This Is

Snobbery is a self-hosted household coffee log for pour-over enthusiasts who care about beans, grind, water, and ratio. Multiple users share a household catalog (coffees, equipment, recipes, roasters, flavor notes) but keep separate brew session logs and AI-driven recommendations. Built primarily for John + Farrah's household; deployed to a VPS behind an existing NGINX reverse proxy.

## Core Value

A returning user — phone in hand, kettle nearby — can log a brew session in under 30 seconds and trust that the home page's "what to buy next" recommendation is grounded in their actual log, not generic taste advice.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

**Foundation**
- [ ] Two-container Docker Compose stack (FastAPI web + PostgreSQL 16) reachable on host port 8080
- [ ] Alembic migrations auto-run on container start via entrypoint
- [ ] Behaves correctly behind NGINX reverse proxy (`X-Forwarded-Proto`, `X-Forwarded-For`)
- [ ] Named volumes for Postgres data, photos, and backups

**Authentication & Authorization**
- [ ] First-run `/setup` flow creates initial admin when zero users exist
- [ ] Username + password login with argon2id hashing (no public registration)
- [ ] Signed session cookies (HttpOnly, Secure, SameSite=Lax), 30-day expiry, refresh on activity
- [ ] `is_admin` role gates `/admin`; non-admins return 403
- [ ] Rate limit `/login` to 5 attempts per IP per 15 minutes

**Security Hardening**
- [ ] CSRF protection on every state-changing form, HTMX-aware
- [ ] Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) on every response
- [ ] Pydantic v2 validation on every form, numeric range enforcement
- [ ] Image upload validation (magic bytes, Pillow decode, EXIF strip)
- [ ] API keys encrypted at rest via Fernet (`APP_ENCRYPTION_KEY` env var), never logged, only last-4 shown in admin UI
- [ ] Audit logging for auth events and admin actions; no PII in logs

**Data Model — Shared Household Catalog**
- [ ] `roasters` table with autocomplete + create-on-save
- [ ] `flavor_notes` table (normalized vocabulary) with autocomplete + create-on-save
- [ ] `coffees` table (shared, soft-delete via `archived`)
- [ ] `equipment` table (brewer/grinder/kettle/scale/water_filter/other, soft-delete)
- [ ] `recipes` table with JSONB pour steps and step builder UI

**Data Model — Per-User**
- [ ] `brew_sessions` table tied to user, coffee, optional recipe, brewer/grinder/kettle equipment
- [ ] `api_credentials` table (admin-managed, Fernet-encrypted keys)
- [ ] `app_settings` table for runtime-editable settings, seeded with `recommendation_region=US`
- [ ] Table-backed `sessions` store

**Brew Session UX**
- [ ] Add brew session form with aggressive prefill from last session + selected recipe (single scrollable form, not stepped)
- [ ] Tag input for observed flavor notes (autocomplete + create new)
- [ ] Rating control 0–5 in 0.25 steps, thumb-operable
- [ ] LocalStorage draft persistence across reload/navigation
- [ ] Quick re-log: one-tap "Brew again" on any session prefills everything but rating/flavor notes/notes
- [ ] Guided Brew Mode (full-screen timer, step auto-advance with audio + haptic cues, screen wake lock, prefills session form on completion)

**Coffee Catalog UX**
- [ ] Coffees CRUD with table-on-desktop, card-list-on-mobile
- [ ] Bag photo upload (`capture="environment"`, client-side downscale, server-side resize to ≤1600px wide, 400px thumbnail, EXIF stripped, JPEG/PNG/WebP, max 5MB)
- [ ] Filter by roaster / country / process / archived

**Brew Session Catalog UX**
- [ ] Sessions list with filter by coffee / brewer / rating range / date range
- [ ] CSV export of current user's sessions

**Equipment & Recipes UX**
- [ ] Equipment CRUD grouped by type; archive (not delete) when referenced
- [ ] Recipes CRUD with step builder (add/remove/reorder pours, cumulative water + time offsets), pour timeline preview, duplicate-recipe action

**Admin**
- [ ] User management (list, create, edit, reset password, toggle admin, deactivate, delete)
- [ ] API credentials management per provider (Anthropic, OpenAI) with enable/disable
- [ ] `app_settings` editor with `value_type`-driven input rendering
- [ ] Backups: manual download (pg_dump + photos tarball) and admin list of retained nightly backups
- [ ] Nightly `pg_dump` + photos tarball at 02:00 in `APP_TIMEZONE`, 14-day retention (configurable via `BACKUP_RETENTION_DAYS`)
- [ ] System info panel (versions, storage usage, session count, last backup status)

**Home Page (Analytics)**
- [ ] Top coffees: top 5 by avg rating, min 2 sessions
- [ ] Preference profile: avg rating by origin / process / roaster / roast level
- [ ] Top-10 flavor descriptors appearing in 4.0+ rated sessions
- [ ] Roast freshness sweet spot (buckets: 0–3, 4–7, 8–14, 15–21, 22+ days)
- [ ] Sweet spots: top 3 cross-dimensional combos `(origin × process × brewer × recipe)`, min 3 sessions, ranked by avg rating
- [ ] Recent brews list (last 10) with edit links
- [ ] Unrated coffees list (catalog entries the user hasn't brewed yet)
- [ ] Each section lazy-loads via HTMX after initial render

**AI Integration**
- [ ] Provider abstraction in `services/ai_service.py` (Anthropic default, OpenAI fallback)
- [ ] Live coffee recommendation with web search tool, three-tier fallback (live → broadened → characteristics_only)
- [ ] URL HEAD-check before rendering buy links; unverified URLs surface as plain text with note
- [ ] Recipe suggestion picks from user's existing `recipes` (never invents)
- [ ] Alternative-brewer callout when historical data shows ≥0.5 rating delta for the recommended style
- [ ] Equipment recommendation (profile-only, no web search), allowed to say "no changes recommended"
- [ ] Paste-and-rank flow (on-demand, never cached)
- [ ] Sweet spots AI prose interpretation generated alongside coffee recommendation, cached together
- [ ] Cold-start empty state when user has <3 brew sessions
- [ ] Signature-based regeneration nightly at 00:00 in `APP_TIMEZONE`; skip when input hash unchanged
- [ ] Manual "Refresh recommendations" button bypasses signature check
- [ ] Stale-indicator badge when stored signature ≠ current signature
- [ ] In-memory per-`(user_id, recommendation_type)` lock to prevent concurrent runs
- [ ] All AI responses validated against Pydantic schemas; schema mismatch surfaces "Try again" UI
- [ ] Graceful "AI not configured" state when no provider key enabled

**Global Search**
- [ ] Persistent search input in top nav (collapsed to icon on mobile, expands to full-screen sheet)
- [ ] Postgres full-text search (or trigram indexes — implementation TBD in plan-phase) across coffee names, roaster names, flavor notes, brew session notes, recipe names/descriptions, equipment names
- [ ] Results grouped by entity type; user only sees own session notes; shared catalog visible to all
- [ ] HTMX live-search debounced to 250ms

**Mobile / PWA**
- [ ] Bottom tab nav (Home / Log / Config / Admin) at <768px with iOS safe-area padding
- [ ] Top horizontal nav at ≥768px
- [ ] Tables collapse to card lists at mobile widths; no horizontal scroll
- [ ] All tap targets ≥44×44px
- [ ] `inputmode` / `type` attributes set correctly for grams, temp, rating, dates
- [ ] Native `<select>` for short dropdowns; searchable HTMX dropdowns reserved for long lists (coffees)
- [ ] Modals are full-screen sheets on mobile, dialogs on desktop
- [ ] Sticky form actions on long forms
- [ ] `manifest.json` (name, icons 192/512 + maskable, `display: standalone`, theme color)
- [ ] Service worker caches app shell for instant repeat loads + brief offline read access
- [ ] Apple touch icon + iOS install meta tags
- [ ] Installable to home screen on iOS Safari and Android Chrome
- [ ] Smoke check at 375×667 and 390×844 viewports (Playwright or equivalent)

**Aesthetic**
- [ ] Warm, minimalist palette (off-white/cream surfaces, espresso accents) with system-preference dark mode
- [ ] Empty states lean into the "snobbery" tone without becoming gimmicky (e.g. "No brews logged yet. The snobbery awaits.")

**Testing**
- [ ] Smoke test covering acceptance-criteria happy path (create user → coffee → equipment → recipe → session → view home)
- [ ] Unit tests for `ai_service` signature logic, `encryption` round-trip, `analytics` queries, CSRF middleware
- [ ] Responsive smoke test at 375px and 390px viewports

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

## Context

**Household scope:** Two users today (John, Farrah). Designed for that scale; not engineered for >10 users.

**Phone-first:** ~90% of use is phone-in-hand at the kettle. Desktop is secondary. Every UX decision evaluated at 375px first.

**Deployment shape:** Self-hosted on John's existing VPS with NGINX already terminating TLS and proxying by hostname. App listens on `localhost:8080`. Reverse-proxy header trust is non-optional.

**Existing artifacts:**
- `snobbery-gsd-prompt.md` — the original product brief that defined this project. Historical reference; the code becomes the source of truth as it's built.
- `CLAUDE.md` — operational conventions, stack invariants, communication style, deployment runbook, and "never do silently" list. Authoritative for ongoing work.

**AI flows are the differentiator.** The non-AI build is a competent household log; the AI flows (live coffee recommendation with web search and verified URL, alternative-brewer callout, sweet-spots prose) are why this exists instead of a spreadsheet.

**Cost discipline matters.** Web search is expensive. The signature-based regeneration design is load-bearing for keeping the bill sane. Don't break it.

## Constraints

- **Tech stack**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 — locked. No React/Vue/Svelte. No SQLite. No JWT. No npm build pipeline.
- **Frontend**: Jinja2 templates + HTMX + Tailwind (CDN) + Alpine.js — locked. Custom CSS only when utilities can't cover it (lives in `app/static/css/custom.css`).
- **Auth**: argon2-cffi for password hashing, signed session cookies via itsdangerous, Fernet (`cryptography`) for API key encryption — locked.
- **Deployment**: Docker Compose with two services (`coffee-snobbery`, `coffee-snobbery-db`), single VPS behind existing NGINX. Migrations run automatically on container start.
- **Container naming**: `coffee-snobbery` (web), `coffee-snobbery-db` (db), `coffee-snobbery-net` (network). Volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups`.
- **Scheduling**: APScheduler in-process. No external worker (no Celery / RQ / cron container).
- **Concurrency model**: low — household scale. Synchronous FastAPI handlers are fine where they keep code simpler; async where it pays for itself (AI calls).
- **Mobile-first hard rule**: any UI must be tested at 375px viewport before being declared done. Bottom nav <768px, top nav ≥768px.
- **Security**: CSRF on all state-changing forms, full security header set on every response, autoescaping on every Jinja template. No exceptions.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use existing `snobbery-gsd-prompt.md` as the canonical idea document | The spec is detailed and load-bearing; rewriting it would lose nuance. CLAUDE.md adds the operational layer. | — Pending |
| Greenfield build (no prior scaffold to integrate) | Confirmed by John during init questioning. CLAUDE.md is aspirational guidance, not code-on-disk truth. | — Pending |
| Defer PWA offline write queue to v2 | Service-worker write sync + conflict resolution is non-trivial. Household app is rarely brewing without connectivity. v1 shows a clear error on offline writes; revisit if it bites. | — Pending |
| Cost control via signature-based regen only — no separate AI token ceiling | Household scale + nightly cadence + manual refresh is naturally bounded. Adding a daily/monthly cap before the cost surprises us is premature plumbing. | — Pending |
| Test posture: smoke + critical-path units | Acceptance-criteria smoke test plus unit coverage on `ai_service` signature logic, `encryption`, `analytics`, and CSRF. Full per-router coverage is deferred. | — Pending |
| Aesthetic: warm + minimalist + system-preference dark mode | Matches the "snobbery" tone (off-white/cream surfaces, espresso accents) without crossing into gimmicky. Dark mode follows OS preference — no manual toggle in v1. | — Pending |
| Single-scrollable brew session form with aggressive prefill (not stepped) | Spec recommends this. Returning user logging session N+1 only fills rating/flavor notes/notes; everything else prefills from last session + selected recipe. | — Pending |
| AI: Anthropic by default, OpenAI fallback; both must support web search | Per spec. SDK versions verified at install to confirm web-search tool availability. | — Pending |
| Search implementation: choose between Postgres full-text and trigram indexes during plan-phase | Both viable. Decision punted to the phase that actually builds search so the engineer can prototype both if needed. | — Pending |
| Deviate from spec: HTMX 2.x, not 1.9 | HTMX 2.x is stable; spec wording predates the release. Migration delta is ~6 items. Approved during init. | — Pending |
| Deviate from spec: Tailwind standalone CLI binary in Dockerfile, not CDN | v4 Play CDN permanently requires `unsafe-inline` for styles, blocking a strict nonce-based CSP. CLI is a single executable, not npm — honors the spec's intent ("no build pipeline"). Approved during init. | — Pending |
| Add `bags` table to v1 Foundation (separate from `coffees` catalog) | Without bag-as-instance, sweet-spots-by-roast-date is unreliable as soon as anyone reorders a bean. Cheap migration now; painful later. Approved during init. | — Pending |
| Add `wishlist_entries` table to v1 | AI coffee-rec card needs an "Add to wishlist" landing. Otherwise the rec is suggest-and-forget. Approved during init. | — Pending |
| Add `yield_grams_actual`, `tds_pct`, `extraction_yield_pct` to `brew_sessions` in v1 | Two nullable columns + one GENERATED column. Optional refractometer fields signal audience-awareness without forcing them. Approved during init. | — Pending |
| AI streaming via polling, not SSE, in v1 | Simpler, no `proxy_buffering off` requirement at NGINX, easier to debug. SSE deferred to v1.1 polish. Approved during init. | — Pending |
| CSV import alongside export, scope-limited | Imports only brew sessions; refuses rows where coffee or bag not in catalog. Lets users seed from Beanconqueror to clear the AI cold-start cliff. Approved during init. | — Pending |
| Cold-start AI: friendly empty state with progress meter | Show "Log N more brews and add M more flavor notes" instead of degraded AI output. AI gates at ≥3 sessions and ≥5 distinct flavor notes per user. Approved during init. | — Pending |
| Admin API health panel (not in spec) | Only way to see silent AI failures (model deprecated, key revoked, quota hit). Adds confidence to "set it and forget it" deployment. Approved during init. | — Pending |
| Server-side draft autosave-on-blur as iOS ITP backstop | localStorage alone loses drafts after 7 days of non-installed Safari ITP inactivity. ~50 LOC + a server-side draft store. Approved during init. | — Pending |
| Single uvicorn worker; document loudly in README + entrypoint | APScheduler in-process + module-level AI locks both require single-process. A future `--workers 4` would silently fire every nightly job 4× and bill 4× the AI cost. | — Pending |
| CSRF via double-submit-cookie pattern | Rotated-per-request tokens break HTMX on second POST because fragments don't update `<body>` `hx-headers`. Surfaced by research at Phase 1 timing. | — Pending |
| `MultiFernet` from day one, not single Fernet | Rotation-ready encryption from the first migration. Adding key rotation later orphans previously-encrypted rows. | — Pending |
| APScheduler with `SQLAlchemyJobStore` + `misfire_grace_time=3600` + `coalesce=True` | Default `MemoryJobStore` silently loses every job after a VPS restart. The 1s default grace window means a restart that lands at 00:00:01 misses the nightly run entirely. | — Pending |

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
*Last updated: 2026-05-25 — Phase 13 (PWA UX Fixes) complete: all 9 post-UAT criteria delivered + verified on-device across 3 review rounds. C9 SW cache-bump (content-deterministic build_id), C10 icon regen + cache-busted URLs, C2/C3 create-fragment (CR-01 wipe-on-error blocker found+fixed in code review), C6/C7 cue controls + ratio prefill, C4/C1 dark toggle + iOS safe-areas, C5/C8 guided-brew reach + /data-tools. Notable bug: guided-brew Start did nothing on all platforms — root-caused via live browser repro to a double-quoted `data-steps` attribute truncating the steps JSON; fixed by single-quoting. Canonical gate: 965 passed + e2e. Phase 13 is the FINAL phase of milestone v1.1 — milestone complete (run /gsd-complete-milestone). (Validated/Active requirement reconciliation still overdue — run /gsd-docs-update.)*
