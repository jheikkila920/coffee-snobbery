# REQUIREMENTS — Snobbery v1

**Status:** Active scope for v1. Each requirement is a hypothesis until shipped and validated.
**ID format:** `[CATEGORY]-[NUMBER]` — categories listed at bottom of file.
**Last updated:** 2026-05-16 after roadmap creation.

---

## v1 Requirements

### Foundation (FOUND)

- [ ] **FOUND-01**: `docker compose up -d` from a clean checkout brings up a working app on host port 8080 with database initialized
- [ ] **FOUND-02**: Two container services with fixed names: `coffee-snobbery` (web) and `coffee-snobbery-db` (database) on user-defined bridge network `coffee-snobbery-net`
- [ ] **FOUND-03**: Named volumes provisioned: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups`
- [ ] **FOUND-04**: Web service runs as a single uvicorn worker; documented loudly in README and entrypoint so this isn't accidentally scaled
- [ ] **FOUND-05**: Alembic migrations run automatically on container start via `entrypoint.sh`; first run creates schema and seeds `app_settings`
- [ ] **FOUND-06**: Postgres extensions `citext`, `pg_trgm`, `unaccent` installed in the first migration
- [ ] **FOUND-07**: `postgresql-client-16` installed in the web image so backup `pg_dump` version matches the database server
- [ ] **FOUND-08**: App honors `X-Forwarded-Proto` and `X-Forwarded-For` from a configured trust list (`TRUSTED_PROXY_IPS` env var)
- [ ] **FOUND-09**: `.env.example` documents all required env vars with one-liner generation hints: `DATABASE_URL`, `POSTGRES_USER/PASSWORD/DB`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `TRUSTED_PROXY_IPS`, `APP_TIMEZONE`, `BACKUP_RETENTION_DAYS`, `LOG_LEVEL`
- [ ] **FOUND-10**: Pydantic-settings reads env vars in `app/config.py`; no module elsewhere reads `os.environ` directly
- [ ] **FOUND-11**: Structured logging via `structlog` with JSON output and request correlation IDs; auth events tagged for audit
- [ ] **FOUND-12**: Tailwind CSS is compiled by the Tailwind standalone CLI binary baked into the Docker image (no Node, no npm); compiled output served as a static file with a content-hashed filename

### Authentication & Sessions (AUTH)

- [ ] **AUTH-01**: First-run `/setup` flow creates the initial admin user when zero users exist; subsequent visits to `/setup` redirect to `/login`
- [ ] **AUTH-02**: `/setup` uses `SELECT ... FOR UPDATE` on an `app_settings` row to prevent concurrent setup races
- [ ] **AUTH-03**: `/login` accepts username + password; no public registration page
- [ ] **AUTH-04**: Passwords hashed with argon2id (memory_cost 64MB, time_cost 3, parallelism 4)
- [ ] **AUTH-05**: Custom session middleware backed by a `sessions` table (cookie holds session ID), 30-day expiry, refresh on activity
- [ ] **AUTH-06**: Session cookie is `HttpOnly`, `Secure`, `SameSite=Lax`, signed with `APP_SECRET_KEY`
- [ ] **AUTH-07**: Session ID regenerated (old row deleted, new ID minted) on every successful login, logout, and admin-toggle to prevent session fixation
- [ ] **AUTH-08**: `/login` rate-limited to 5 attempts per IP per 15 minutes via slowapi
- [ ] **AUTH-09**: Admin section gated by `is_admin=true`; returns 403 otherwise
- [ ] **AUTH-10**: Auth events (login success/failure, logout, password reset, user create/delete, admin toggle) logged with user ID, IP, timestamp; no PII or request bodies in logs

### Security Hardening (SEC)

- [ ] **SEC-01**: CSRF protection on every state-changing form via `starlette-csrf` double-submit-cookie pattern; HTMX-compatible (no rotated-per-request tokens)
- [ ] **SEC-02**: Content-Security-Policy header on every response: nonce-based for scripts and styles; Alpine.js loaded as the CSP build; HTMX `hx-on:` inline handlers avoided in templates; any residual `'unsafe-eval'` requirement documented in `docs/decisions/`
- [ ] **SEC-03**: Security headers on every response: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(self), microphone=(), geolocation=()`
- [ ] **SEC-04**: README documents the NGINX `Strict-Transport-Security` line so HSTS is set at the proxy layer
- [ ] **SEC-05**: Jinja2 autoescape on for all templates; CI grep test forbids `|safe` in `app/templates/pages/`
- [ ] **SEC-06**: All form input validated via Pydantic v2 schemas with explicit numeric ranges (rating 0–5 in 0.25 steps, temp 0–100°C, dose/water in sensible ranges)
- [ ] **SEC-07**: Image uploads validated by magic-byte check + Pillow decode; EXIF stripped on save; oversized payloads (>5MB) rejected before bytes are buffered
- [ ] **SEC-08**: API keys encrypted at rest with `MultiFernet` (rotation-ready from day one); never logged; admin UI shows only last 4 characters
- [ ] **SEC-09**: `APP_ENCRYPTION_KEY` env var documented with Python one-liner to generate; loaded once at startup; absent or malformed key crashes startup loudly

### Shared Catalog (CAT)

- [ ] **CAT-01**: `roasters` table with `name` (citext unique), `location`, `website`, `notes`; autocomplete-on-create-on-save in forms
- [ ] **CAT-02**: `flavor_notes` table (normalized vocabulary) with `name` (citext unique lowercased), `category` enum (fruit, floral, sweet, chocolate, nutty, spice, savory, fermented, other); autocomplete-on-create-on-save
- [ ] **CAT-03**: `coffees` table with all spec fields plus `advertised_flavor_note_ids` array referencing `flavor_notes`; soft-delete via `archived`; CRUD UI
- [ ] **CAT-04**: `bags` table (separate instance per physical bag): `id`, `coffee_id`, `roast_date`, `weight_grams`, `opened_at`, `finished_at`, `notes`, `created_at`, `updated_at`; CRUD UI; "open new bag of this coffee" action from coffee detail
- [ ] **CAT-05**: `equipment` table with `type` enum (brewer, grinder, kettle, scale, water_filter, other), brand, model, notes; soft-delete via `archived`; usage count visible; archive (not delete) if any session references it
- [ ] **CAT-06**: `recipes` table with JSONB `steps` array, dose/water/temp/grind fields, free-form `grind_setting`, soft-delete; step builder UI (add/remove/reorder pours with cumulative water + time offsets); visual pour-timeline preview; duplicate-recipe action
- [ ] **CAT-07**: Coffees list view collapses to card list at <768px viewport; filter by roaster/country/process/archived state
- [ ] **CAT-08**: Bag photo upload (`<input capture="environment">`), client-side downscale via Canvas API, server-side resize to ≤1600px wide JPEG/PNG/WebP, 400px thumbnail generated, EXIF stripped, max 5MB; thumbnails served via app route (not direct disk)

### Brew Sessions (BREW)

- [x] **BREW-01**: `brew_sessions` table per user with `coffee_id` (denormalized for fast queries), `bag_id` (FK to `bags`, nullable for freestyle without specific bag), `recipe_id` (FK, nullable), `brewer_id`, `grinder_id`, `kettle_id`, `water_type`, `dose_grams_actual`, `water_grams_actual`, `yield_grams_actual` (nullable), `tds_pct` (nullable), `extraction_yield_pct` (GENERATED), `water_temp_c_actual`, `grind_setting_actual`, `rating`, `flavor_note_ids_observed`, `notes`, `brewed_at`
- [x] **BREW-02**: Single scrollable add-session form with aggressive prefill from last session + selected recipe; visible prefill indicators (ghost text or pill) so users don't re-type defensively
- [x] **BREW-03**: Tag input for observed flavor notes — autocomplete from existing tags, comma/enter commits a new tag, tap-to-remove chips, mobile keyboard friendly
- [x] **BREW-04**: Rating control 0–5 in 0.25 steps as tap-on-stars (half/quarter stars), thumb-operable, ≥44×44px tap targets
- [x] **BREW-05**: Live brew-ratio readout in the form (computed in Alpine from `dose_grams_actual` and `water_grams_actual`, displayed as `1:N.NN`); no schema column
- [x] **BREW-06**: LocalStorage draft persistence on every input change, key namespaced by `user_id`; cleared on successful submit
- [x] **BREW-07**: Server-side draft autosave on field blur (POST `/brew/draft`); restore from server when localStorage is empty; defends against iOS Safari 7-day ITP wipe
- [x] **BREW-08**: Sticky Save/Cancel buttons at bottom of long forms on mobile
- [x] **BREW-09**: Quick re-log action on every session row: opens a new session form prefilled with that session's coffee, bag (if active), recipe, brewer, grinder, kettle, water type, dose, water, temp, grind setting; leaves rating, observed flavor notes, notes blank
- [x] **BREW-10**: Sessions list view per user with filters: coffee, brewer, rating range, date range; CSV export
- [x] **BREW-11**: CSV import of brew sessions (limited scope: refuse rows where coffee or bag not in catalog; force conscious add)
- [ ] **BREW-12**: Guided Brew Mode full-screen interface: large countdown timer, current step highlighted with cumulative water target and elapsed time, audio chime + vibration at step transitions (configurable), pause/resume, cancel-without-logging, "Done brewing" returns to session form with timer data + recipe + selected coffee prefilled
- [ ] **BREW-13**: Guided Brew Mode requests `wakeLock`; re-acquires on `visibilitychange`; iOS Safari fallback via silent audio loop or NoSleep.js; visible indicator when wake lock is held

### Home Page Analytics (HOME)

- [ ] **HOME-01**: Top coffees: top 5 by user's avg rating across that user's sessions, min 2 sessions, with rating and count
- [ ] **HOME-02**: Preference profile cards: avg rating by origin / process / roaster / roast level (each pre-computed in one query, lazy-loaded via HTMX)
- [ ] **HOME-03**: Top-10 flavor descriptors appearing in 4.0+ rated sessions for this user
- [ ] **HOME-04**: Roast freshness sweet-spot buckets (0–3, 4–7, 8–14, 15–21, 22+ days) using `bags.roast_date` (never `coffees.roast_date`); avg rating per bucket
- [ ] **HOME-05**: Sweet spots: top 3 multi-dimensional combinations `(origin × process × brewer × recipe)` with `min_sessions = 3`, ranked by avg rating; pure SQL via UNION of GROUP BY queries with HAVING
- [x] **HOME-06**: AI prose interpretation paragraph rendered below Sweet Spots when available; pattern data shown without prose when AI disabled or unavailable
- [ ] **HOME-07**: Recent brews list: last 10 sessions with edit links
- [ ] **HOME-08**: Unrated coffees list: catalog entries this user hasn't brewed yet
- [ ] **HOME-09**: Each home section lazy-loads via HTMX after initial page render; staggered fire (50–150ms apart) to avoid thundering-herd on the connection pool

### AI Services (AI)

- [x] **AI-01**: Provider abstraction in `app/services/ai_service.py`; Anthropic default, OpenAI fallback only on non-retryable failures (`max_retries=1`); SDK web-search tool versions read from `app_settings` (not hardcoded)
- [ ] **AI-02**: `ai_recommendations` table persists every call: `id`, `user_id`, `recommendation_type` enum, `input_signature` (indexed), `response_json`, `provider_used`, `model_used`, `tool_version`, `tokens_input`, `tokens_output`, `tokens_input_search`, `web_search_count`, `url_verified`, `duration_ms`, `generated_at`, `generated_by` enum (scheduler / manual_refresh), `error_status`
- [x] **AI-03**: Live coffee recommendation flow uses web-search tool with three-tier fallback: primary (origin + process + roast level) → broadened (relax constraints in order: process → roast level → origin) → characteristics-only (no specific bean, no URL); response indicates which tier produced it
- [x] **AI-04**: Citation/tool-result blocks projected/stripped from the model's response before Pydantic validation; schema mismatch surfaces "Try again" UI in the home page card rather than rendering garbage
- [x] **AI-05**: URL verification background task: ranged GET (not HEAD — many specialty roasters block HEAD), realistic User-Agent, body-contains-roaster-or-coffee-name check, no cross-host redirects, 5s timeout; UI initially shows "verifying..." and updates when the check completes; unverified URLs render as plain text with a "couldn't verify" note
- [x] **AI-06**: Recipe suggestion picks from this user's existing `recipes` rows ranked by historical avg rating for similar bean profiles (matching origin + process + roast level); never invents new recipes; if no recipe matches the bean style, suggestion text says so and links to the recipe builder
- [x] **AI-07**: Alternative-brewer callout populated when historical data for the user shows a ≥0.5 rating delta on a different brewer for the recommended bean style
- [x] **AI-08**: Equipment recommendation flow (profile-only, no web search): identifies weakest link or explicitly says "no changes recommended"
- [x] **AI-09**: Paste-and-rank flow: on-demand only, never cached, never scheduled; top 3 with one-sentence reasoning each grounded in the user's log
- [x] **AI-10**: Sweet-spots AI prose interpretation generated alongside the coffee recommendation, cached together, regenerated together
- [x] **AI-11**: Cold-start empty state when user has <3 brew sessions or <5 distinct observed flavor notes: progress meter ("Log 2 more brews and add 3 more flavor notes to unlock AI recommendations") in place of the AI section
- [x] **AI-12**: Signature-based regeneration: input signature is a content hash of *this user's own* sessions (not shared catalog counts) so adding a coffee to the household doesn't thrash everyone's signature
- [x] **AI-13**: In-memory per-`(user_id, recommendation_type)` lock plus Postgres advisory lock backstop prevents concurrent runs from scheduler and manual refresh
- [x] **AI-14**: Manual refresh button on home AI section; per-user throttle of one manual refresh per 5 minutes; shows spinner with "Searching the web for fresh coffees…"; recommendations swap in on completion
- [x] **AI-15**: Stale-indicator badge inline with each recommendation when current signature ≠ stored signature
- [x] **AI-16**: Graceful "AI not configured" empty state when no provider key is enabled in admin
- [x] **AI-17**: Web-search tool `max_uses` capped at 5 for primary search, 3 for broadened fallback; cap configurable via `app_settings`
- [x] **AI-18**: All AI responses validated against per-flow Pydantic schemas; every response schema includes a `summary_prose` field so output renders as structured UI + short narrative

### AI Run Scheduling (SCHED)

- [x] **SCHED-01**: APScheduler `AsyncIOScheduler` started in FastAPI `lifespan`; `SQLAlchemyJobStore` so jobs survive container restart; `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`
- [x] **SCHED-02**: Nightly AI refresh fires at 00:00 in `APP_TIMEZONE` (default `America/Chicago`); for each active user with ≥3 brew sessions, compute current signature, regenerate only if changed
- [x] **SCHED-03**: Job summary logged at each run: users processed, regenerations triggered, skips, total tokens (split web-search vs non-web-search), errors
- [x] **SCHED-04**: Nightly backup job fires at 02:00 in `APP_TIMEZONE`: `pg_dump` SQL file + photos tarball written to `/app/data/backups`; retention controlled by `BACKUP_RETENTION_DAYS` (default 14)

### Global Search (SEARCH)

- [ ] **SEARCH-01**: Persistent search input in top nav: collapsed to icon at <768px (expands to full-screen sheet on tap), expanded inline at ≥768px
- [ ] **SEARCH-02**: Postgres-based search across coffee names, roaster names, flavor note names, brew session notes (only the current user's), recipe names/descriptions, equipment names; implementation choice (full-text vs trigram) made in plan-phase
- [ ] **SEARCH-03**: HTMX live results with 250ms debounce; results grouped by entity type; each result links to the relevant edit page
- [ ] **SEARCH-04**: User only sees their own brew session notes in results; all shared catalog (coffees, equipment, recipes, roasters, flavor notes) is searchable to every authenticated user

### Admin (ADMIN)

- [x] **ADMIN-01**: User management: list, create, edit (reset password, toggle admin, deactivate), delete
- [x] **ADMIN-02**: API credentials per provider (Anthropic, OpenAI): set/update encrypted key, select model per provider, enable/disable toggle; keys masked after save (last-4 only)
- [x] **ADMIN-03**: `app_settings` editor: one row per setting, input control selected by `value_type` (string → text, integer → number, boolean → checkbox, json → textarea); description shown as helper text; save persists immediately
- [x] **ADMIN-04**: Backups page: list of retained nightly backups with size + timestamp, download button per backup, manual "Run backup now" button, manual `pg_dump` + photos tarball download
- [x] **ADMIN-05**: System info panel: app version, DB server version, photo storage usage, backup storage usage, active session count, last backup status + timestamp
- [x] **ADMIN-06**: API health panel: last AI run timestamp per recommendation type, last success/error status per provider, last 5 error messages per provider; surfaces silent failures (model deprecation, quota, key revoke)

### Mobile-First + PWA (MOB)

- [ ] **MOB-01**: Bottom tab nav (Home / Log / Config / Admin) at <768px with iOS safe-area inset respected; top horizontal nav at ≥768px
- [ ] **MOB-02**: Admin tab hidden for non-admins
- [ ] **MOB-03**: Tables collapse to card lists at mobile widths; no horizontal scroll anywhere
- [ ] **MOB-04**: All tap targets ≥44×44px
- [x] **MOB-05**: Form inputs use correct `inputmode` (`decimal` for grams/temp/rating, `numeric` for integer counts) and `type` (`date`, `datetime-local`) so mobile keyboards match
- [x] **MOB-06**: Global CSS rule `input, select, textarea { font-size: 16px; }` to prevent iOS Safari auto-zoom; Playwright assertion at 375px confirms no zoom on focus
- [ ] **MOB-07**: Native `<select>` for short dropdowns on mobile; searchable HTMX dropdowns for long lists (coffees only)
- [ ] **MOB-08**: Modals are full-screen sheets at <768px, dialogs at ≥768px
- [ ] **MOB-09**: `manifest.json` with name, `short_name`, `description`, icons (192px, 512px, maskable), `display: standalone`, dual `theme-color` (light + dark), `start_url: "/?source=pwa"` that returns 200 (no redirect)
- [ ] **MOB-10**: Service worker served from `/sw.js` with `Service-Worker-Allowed: /` header; caches app shell + offline read-only fallback; explicit version + cache-bust on deploy
- [ ] **MOB-11**: Apple touch icon + iOS install meta tags; in-app "Add to Home Screen" instructions banner for iOS Safari (since iOS never prompts)
- [ ] **MOB-12**: Installable to home screen on iOS Safari and Android Chrome
- [ ] **MOB-13**: Responsive smoke check (Playwright) at 375×667 and 390×844 viewports asserts: bottom nav present and functional, brew session form fully usable without horizontal scroll, photo upload control present, home page analytics cards stack vertically and remain readable

### Aesthetic (UX)

- [ ] **UX-01**: Warm minimalist palette (off-white/cream surfaces, espresso accents) implemented as Tailwind theme; system-preference dark mode (no manual toggle in v1)
- [ ] **UX-02**: PWA branding: name `"Snobbery — Coffee Log"`, short_name `"Snobbery"`, description `"Self-hosted coffee log for households who take pour-over seriously"`
- [ ] **UX-03**: Browser tab title format `Snobbery — {Page Name}`; top nav wordmark on desktop, icon-only on mobile
- [ ] **UX-04**: Empty states lean into the "snobbery" tone without being gimmicky (e.g. home page when no brews logged: "No brews logged yet. The snobbery awaits.")

### Testing (TEST)

- [ ] **TEST-01**: Pytest smoke test covers the acceptance-criteria happy path: create user → create coffee → create equipment → create recipe → log session → view home page renders
- [ ] **TEST-02**: Unit tests for `services/ai_service.py` signature computation + provider fallback logic (using `respx` for HTTP fixtures)
- [ ] **TEST-03**: Unit tests for `services/encryption.py` round-trip + MultiFernet key rotation
- [ ] **TEST-04**: Unit tests for `services/analytics.py` queries against a seeded test DB (top coffees, preference profile, sweet spots, roast freshness)
- [ ] **TEST-05**: Unit tests for CSRF middleware (positive + negative)
- [ ] **TEST-06**: Playwright responsive smoke at 375×667 and 390×844 viewports

---

## v2 — Deferred

- PWA offline write queue (service worker background sync + conflict resolution) — defer until use-case proves out
- Inventory management (bag count, depletion tracking) — possible v2 if it earns its keep
- SSE for AI streaming — polish on AI-streaming UX
- Per-user/day or per-month AI cost ceiling — add if signature regen proves insufficient
- Materialized search index — only if trigram/FTS query latency degrades at scale
- Full per-router test coverage — expand if regressions become a pattern
- Manual dark/light toggle (currently system-preference only)
- Recipe versioning (currently edit-in-place; "duplicate to iterate" convention in UI)
- Cost-per-brew home page tile (decided household-by-household)
- Hierarchical flavor wheel UI (currently flat tags with category enum)

## Out of Scope

- Public registration / sign-up — household app, admin provisions users
- OAuth / SSO / magic links — username+password is sufficient at household scale
- JWT-based auth — signed session cookies are simpler and adequate
- Mobile native app — PWA covers the install + offline-read case
- Multi-tenant / household separation — single deployment = single household
- Subscription billing — self-hosted, no revenue model
- Email notifications — no SMTP plumbing, no use case at household scale
- Real-time WebSockets — HTMX polling/SSE is sufficient
- Social features, sharing, public profiles — actively counter to the snobbery aesthetic
- Coffee shop / cafe discovery features — out of domain
- Separate frontend build pipeline (React/Vue/Svelte/Node) — server-rendered Jinja + HTMX is the chosen stack
- SQLite — Postgres is required for FTS, JSONB, citext, and concurrent multi-user writes
- Real-time scraper or product index — AI uses web search at request time, no background ingestion

## Traceability

Every v1 REQ-ID is mapped to exactly one phase. Coverage: **116/116**.

| Requirement | Phase | Status |
|---|---|---|
| FOUND-01 | Phase 0 — Foundation | Pending |
| FOUND-02 | Phase 0 — Foundation | Pending |
| FOUND-03 | Phase 0 — Foundation | Pending |
| FOUND-04 | Phase 0 — Foundation | Pending |
| FOUND-05 | Phase 0 — Foundation | Pending |
| FOUND-06 | Phase 0 — Foundation | Pending |
| FOUND-07 | Phase 0 — Foundation | Pending |
| FOUND-08 | Phase 0 — Foundation | Pending |
| FOUND-09 | Phase 0 — Foundation | Pending |
| FOUND-10 | Phase 0 — Foundation | Pending |
| FOUND-11 | Phase 0 — Foundation | Pending |
| FOUND-12 | Phase 0 — Foundation | Pending |
| AUTH-01 | Phase 2 — Auth | Pending |
| AUTH-02 | Phase 2 — Auth | Pending |
| AUTH-03 | Phase 2 — Auth | Pending |
| AUTH-04 | Phase 2 — Auth | Pending |
| AUTH-05 | Phase 1 — Middleware | Pending |
| AUTH-06 | Phase 2 — Auth | Pending |
| AUTH-07 | Phase 2 — Auth | Pending |
| AUTH-08 | Phase 1 — Middleware | Pending |
| AUTH-09 | Phase 2 — Auth | Pending |
| AUTH-10 | Phase 1 — Middleware | Pending |
| SEC-01 | Phase 1 — Middleware | Pending |
| SEC-02 | Phase 1 — Middleware | Pending |
| SEC-03 | Phase 1 — Middleware | Pending |
| SEC-04 | Phase 1 — Middleware | Pending |
| SEC-05 | Phase 1 — Middleware | Pending |
| SEC-06 | Phase 4 — Shared Catalog | Pending |
| SEC-07 | Phase 4 — Shared Catalog | Pending |
| SEC-08 | Phase 3 — Encryption + Settings | Pending |
| SEC-09 | Phase 3 — Encryption + Settings | Pending |
| CAT-01 | Phase 4 — Shared Catalog | Pending |
| CAT-02 | Phase 4 — Shared Catalog | Pending |
| CAT-03 | Phase 4 — Shared Catalog | Pending |
| CAT-04 | Phase 0 — Foundation | Pending |
| CAT-05 | Phase 4 — Shared Catalog | Pending |
| CAT-06 | Phase 4 — Shared Catalog | Pending |
| CAT-07 | Phase 4 — Shared Catalog | Pending |
| CAT-08 | Phase 4 — Shared Catalog | Pending |
| BREW-01 | Phase 5 — Brew Sessions | Complete |
| BREW-02 | Phase 5 — Brew Sessions | Complete |
| BREW-03 | Phase 5 — Brew Sessions | Complete |
| BREW-04 | Phase 5 — Brew Sessions | Complete |
| BREW-05 | Phase 5 — Brew Sessions | Complete |
| BREW-06 | Phase 5 — Brew Sessions | Complete |
| BREW-07 | Phase 5 — Brew Sessions | Complete |
| BREW-08 | Phase 5 — Brew Sessions | Complete |
| BREW-09 | Phase 5 — Brew Sessions | Complete |
| BREW-10 | Phase 5 — Brew Sessions | Complete |
| BREW-11 | Phase 5 — Brew Sessions | Complete |
| BREW-12 | Phase 11 — PWA + Mobile Polish | Pending |
| BREW-13 | Phase 11 — PWA + Mobile Polish | Pending |
| HOME-01 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-02 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-03 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-04 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-05 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-06 | Phase 7 — AI Services | Complete |
| HOME-07 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-08 | Phase 6 — Analytics (Home Page) | Pending |
| HOME-09 | Phase 6 — Analytics (Home Page) | Pending |
| AI-01 | Phase 7 — AI Services | Complete |
| AI-02 | Phase 0 — Foundation | Pending |
| AI-03 | Phase 7 — AI Services | Complete |
| AI-04 | Phase 7 — AI Services | Complete |
| AI-05 | Phase 7 — AI Services | Complete |
| AI-06 | Phase 7 — AI Services | Complete |
| AI-07 | Phase 7 — AI Services | Complete |
| AI-08 | Phase 7 — AI Services | Complete |
| AI-09 | Phase 7 — AI Services | Complete |
| AI-10 | Phase 7 — AI Services | Complete |
| AI-11 | Phase 7 — AI Services | Complete |
| AI-12 | Phase 7 — AI Services | Complete |
| AI-13 | Phase 7 — AI Services | Complete |
| AI-14 | Phase 7 — AI Services | Complete |
| AI-15 | Phase 7 — AI Services | Complete |
| AI-16 | Phase 7 — AI Services | Complete |
| AI-17 | Phase 7 — AI Services | Complete |
| AI-18 | Phase 7 — AI Services | Complete |
| SCHED-01 | Phase 8 — Scheduler + Backups | Complete |
| SCHED-02 | Phase 8 — Scheduler + Backups | Complete |
| SCHED-03 | Phase 8 — Scheduler + Backups | Complete |
| SCHED-04 | Phase 8 — Scheduler + Backups | Complete |
| SEARCH-01 | Phase 10 — Global Search | Pending |
| SEARCH-02 | Phase 10 — Global Search | Pending |
| SEARCH-03 | Phase 10 — Global Search | Pending |
| SEARCH-04 | Phase 10 — Global Search | Pending |
| ADMIN-01 | Phase 9 — Admin | Complete |
| ADMIN-02 | Phase 9 — Admin | Complete |
| ADMIN-03 | Phase 9 — Admin | Complete |
| ADMIN-04 | Phase 9 — Admin | Complete |
| ADMIN-05 | Phase 9 — Admin | Complete |
| ADMIN-06 | Phase 9 — Admin | Complete |
| MOB-01 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-02 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-03 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-04 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-05 | Phase 5 — Brew Sessions | Complete |
| MOB-06 | Phase 5 — Brew Sessions | Complete |
| MOB-07 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-08 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-09 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-10 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-11 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-12 | Phase 11 — PWA + Mobile Polish | Pending |
| MOB-13 | Phase 11 — PWA + Mobile Polish | Pending |
| UX-01 | Phase 11 — PWA + Mobile Polish | Pending |
| UX-02 | Phase 11 — PWA + Mobile Polish | Pending |
| UX-03 | Phase 11 — PWA + Mobile Polish | Pending |
| UX-04 | Phase 11 — PWA + Mobile Polish | Pending |
| TEST-01 | Phase 12 — Hardening + Tests | Pending |
| TEST-02 | Phase 12 — Hardening + Tests | Pending |
| TEST-03 | Phase 12 — Hardening + Tests | Pending |
| TEST-04 | Phase 12 — Hardening + Tests | Pending |
| TEST-05 | Phase 12 — Hardening + Tests | Pending |
| TEST-06 | Phase 12 — Hardening + Tests | Pending |

### Phase Coverage Summary

| Phase | Requirements Mapped |
|---|---|
| Phase 0 — Foundation | 14 (FOUND-01..12, CAT-04, AI-02) |
| Phase 1 — Middleware | 8 (SEC-01..05, AUTH-05, AUTH-08, AUTH-10) |
| Phase 2 — Auth | 7 (AUTH-01, 02, 03, 04, 06, 07, 09) |
| Phase 3 — Encryption + Settings | 2 (SEC-08, SEC-09) |
| Phase 4 — Shared Catalog | 9 (CAT-01..03, CAT-05..08, SEC-06, SEC-07) |
| Phase 5 — Brew Sessions | 13 (BREW-01..11, MOB-05, MOB-06) |
| Phase 6 — Analytics (Home Page) | 8 (HOME-01..05, HOME-07..09) |
| Phase 7 — AI Services | 18 (AI-01, AI-03..18, HOME-06) |
| Phase 8 — Scheduler + Backups | 4 (SCHED-01..04) |
| Phase 9 — Admin | 6 (ADMIN-01..06) |
| Phase 10 — Global Search | 4 (SEARCH-01..04) |
| Phase 11 — PWA + Mobile Polish | 17 (BREW-12, 13, MOB-01..04, MOB-07..13, UX-01..04) |
| Phase 12 — Hardening + Tests | 6 (TEST-01..06) |
| **Total** | **116** |

---

## Categories

| Category | Prefix | Scope |
|---|---|---|
| Foundation | FOUND | Docker, migrations, env, logging, Tailwind build |
| Authentication & Sessions | AUTH | Login, setup flow, session middleware, rate-limit |
| Security Hardening | SEC | CSRF, CSP, headers, validation, encryption |
| Shared Catalog | CAT | Coffees, roasters, equipment, recipes, flavor notes, bags |
| Brew Sessions | BREW | Session form, drafts, rating, guided brew, CSV |
| Home Page Analytics | HOME | Top coffees, preference profile, sweet spots, freshness |
| AI Services | AI | Recommendations, fallback chain, URL verify, cost telemetry |
| AI Run Scheduling | SCHED | APScheduler, nightly AI + backup jobs |
| Global Search | SEARCH | Cross-entity search, debounced HTMX |
| Admin | ADMIN | User mgmt, API keys, app_settings, backups, system info, API health |
| Mobile-First + PWA | MOB | Responsive layout, manifest, service worker, installability |
| Aesthetic | UX | Palette, dark mode, copy, branding |
| Testing | TEST | Smoke, units, Playwright responsive |
