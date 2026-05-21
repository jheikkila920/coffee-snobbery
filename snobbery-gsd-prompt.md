# Build: Snobbery (self-hosted coffee log)

## Overview

Build **Snobbery**, a self-hosted household coffee logging web application for serious pour-over enthusiasts. Multi-user with separate brew logs but shared household resources (coffees, equipment, recipes). Self-hosted on a VPS behind an existing NGINX reverse proxy. AI-assisted recommendations for next coffee and equipment upgrades.

## Naming and Branding

- **Display name**: Snobbery
- **Repository name**: `coffee-snobbery`
- **Docker container name**: `coffee-snobbery` (web service); database container: `coffee-snobbery-db`
- **Docker network name**: `coffee-snobbery-net`
- **PWA manifest**:
  - `name`: "Snobbery — Coffee Log"
  - `short_name`: "Snobbery"
  - `description`: "Self-hosted coffee log for households who take pour-over seriously"
- **Browser tab title format**: `Snobbery — {Page Name}` (e.g. "Snobbery — Home", "Snobbery — Log")
- **Top nav branding**: "Snobbery" wordmark on desktop, icon-only on mobile to preserve space
- **Tone**: self-aware about being made for coffee snobs. Empty states and confirmation messages should lean into the bit without becoming a gimmick — e.g. empty home page: "No brews logged yet. The snobbery awaits."

## Tech Stack (required)

- **Language**: Python 3.12
- **Backend**: FastAPI
- **Database**: PostgreSQL 16
- **ORM/Migrations**: SQLAlchemy 2.0 + Alembic
- **Templating**: Jinja2 server-rendered
- **Frontend**: HTMX 1.9+ for partial updates, Tailwind CSS (via CDN, no build pipeline), Alpine.js for client-side interactivity
- **Auth**: argon2-cffi for password hashing, signed session cookies via itsdangerous (no JWT, no OAuth)
- **Secrets**: cryptography.Fernet for symmetric encryption of stored API keys
- **AI SDKs**: `anthropic` and `openai` official Python SDKs
- **HTTP client**: httpx
- **Image handling**: Pillow for thumbnail generation
- **Deployment**: Docker Compose with two services (`web`, `db`)

Do not introduce React, Next.js, Vue, Svelte, Node, or a separate frontend build system. Do not use SQLite. Do not use JWT.

## Mobile-First Design (critical — 90% of use will be from a phone)

This app is brewed-with-in-hand on a phone, not a desktop dashboard. Design and build mobile-first; desktop is the secondary layout.

### Required mobile patterns
- **Bottom tab navigation** on screens <768px wide: Home / Log / Config / Admin (Admin tab hidden for non-admins). Sticky bottom nav, respects iOS safe area.
- **Top horizontal nav** on screens ≥768px.
- **Tables collapse to card lists** on mobile. No horizontal scroll. Each row becomes a card with key info up top and secondary info below. Use Tailwind responsive utilities, not separate templates.
- **Tap targets ≥44×44px** for all buttons, icons, and form controls.
- **Form inputs**:
  - Use `inputmode="decimal"` for grams/temp/rating, `inputmode="numeric"` for integer counts, `type="date"` and `type="datetime-local"` for date fields. This triggers the correct mobile keyboard.
  - Use native `<select>` for dropdowns on mobile (better than custom HTMX dropdowns for accessibility), with searchable HTMX dropdowns reserved for long lists like coffee selection.
  - Tag inputs (flavor notes) must work with mobile keyboards — comma or enter to commit a tag, visible tag chips with tap-to-remove.
- **Photo upload**:
  - `<input type="file" accept="image/*" capture="environment">` so the camera opens directly on mobile.
  - Client-side downscale before upload (use Canvas API) to avoid uploading 12MP files over cell data.
- **Rating control**: tap-to-set on a horizontal 0–5 scale with 0.25 steps. Slider OR tap-on-stars (half/quarter stars). Must be usable with thumb on a phone, not a tiny range input.
- **Modals are full-screen sheets on mobile**, dialogs on desktop.
- **Sticky form action buttons** (Save / Cancel) at the bottom of long forms on mobile so the user doesn't scroll to submit.
- **No hover-dependent UI**. Anything reachable only by hover must also be reachable by tap.

### Brew-session form: progressive flow on mobile
The brew session form has ~12 fields. On mobile, present it as a stepped flow (3 steps: Coffee + Recipe → Equipment + Parameters → Rating + Notes) with a progress indicator, OR a single scrollable form with smart defaults that prefill most fields from the last session and the selected recipe. Recommendation: single scrollable form with aggressive prefill is simpler and faster for a returning user. Make that the default.

### Draft persistence
Save in-progress brew session form state to `localStorage` on every input change. If the page reloads, a phone call interrupts, or the user navigates away, restore the draft on return. Clear on successful submit.

### PWA support (required)
- `manifest.json` with app name, icons (192px, 512px, maskable), `display: standalone`, theme color
- Service worker that caches the app shell so it loads instantly on repeat visits and works briefly offline (cached read-only pages — write operations still require connectivity, queue failed POSTs with a "saved offline, will sync" indicator if feasible, otherwise show an error)
- Apple touch icon and meta tags for iOS install prompt
- The app must be installable to the home screen on both iOS Safari and Android Chrome

### Responsive testing
Smoke test must include a Playwright or equivalent check at 375×667 (iPhone SE) and 390×844 (iPhone 14) viewport sizes, verifying:
- Bottom nav is visible and functional
- Brew session form is fully usable without horizontal scroll
- Photo upload control is present
- Home page analytics cards stack vertically and remain readable

## Architecture

```
docker-compose.yml
├── coffee-snobbery     (FastAPI web service, exposed on host port 8080)
└── coffee-snobbery-db  (Postgres 16, internal network only, named volume)
```

Both containers attached to a user-defined bridge network `coffee-snobbery-net`. NGINX runs on the host (already configured separately) and proxies a hostname to `localhost:8080`. The app must work behind a reverse proxy (honor `X-Forwarded-Proto`, `X-Forwarded-For`).

Use a named Docker volume for Postgres data and a bind mount or named volume for uploaded photos (`/app/data/photos`) and backups (`/app/data/backups`).

## Data Model

### users
- `id` (UUID, PK)
- `username` (unique, citext)
- `email` (unique, nullable)
- `password_hash` (argon2)
- `is_admin` (bool, default false)
- `created_at`, `updated_at`

### roasters (shared, normalized)
- `id` (UUID, PK)
- `name` (text, unique citext)
- `location` (text, nullable — e.g. "Bentonville, AR")
- `website` (text, nullable)
- `notes` (text)
- `created_at`, `updated_at`

### flavor_notes (shared, normalized vocabulary)
- `id` (UUID, PK)
- `name` (text, unique citext, lowercased)
- `category` (enum, nullable: fruit, floral, sweet, chocolate, nutty, spice, savory, fermented, other)
- `created_at`

Both tables have autocomplete UI in forms — picking an existing entry is preferred, but typing a new value creates the entry on save. This prevents "Onyx", "Onyx Coffee", "Onyx Coffee Lab" fragmentation while still allowing fast entry.

### coffees (shared across all users — household catalog)
- `id` (UUID, PK)
- `name` (text, required)
- `roaster_id` (FK roasters, required)
- `country` (text)
- `region` (text)
- `producer` (text, nullable)
- `varietal` (text, nullable)
- `process` (enum: washed, natural, honey, anaerobic, experimental, other)
- `roast_level` (enum: light, medium-light, medium, medium-dark, dark)
- `roast_date` (date, nullable)
- `advertised_flavor_note_ids` (array of FK to flavor_notes)
- `price_usd` (numeric, nullable)
- `weight_grams` (integer, nullable)
- `photo_path` (text, nullable — bag photo)
- `notes` (text)
- `archived` (bool, default false — soft delete; finished bags get archived)
- `created_by_user_id` (FK users)
- `created_at`, `updated_at`

### equipment (shared)
- `id` (UUID, PK)
- `name` (text, required — e.g. "Hario Switch")
- `type` (enum: brewer, grinder, kettle, scale, water_filter, other)
- `brand` (text, nullable)
- `model` (text, nullable)
- `notes` (text)
- `archived` (bool, default false)
- `created_at`, `updated_at`

### recipes (shared)
- `id` (UUID, PK)
- `name` (text, required — e.g. "Hario Switch 20g/320g three-pour")
- `description` (text)
- `default_brewer_id` (FK equipment, nullable)
- `dose_grams` (numeric)
- `water_grams` (numeric)
- `water_temp_c` (numeric)
- `total_time_seconds` (integer)
- `grind_setting` (text, free-form since grinders differ)
- `steps` (jsonb — array of `{time_seconds, action, water_grams_cumulative, notes}`)
- `notes` (text)
- `archived` (bool, default false)
- `created_at`, `updated_at`

### brew_sessions (per-user)
- `id` (UUID, PK)
- `user_id` (FK users, required)
- `coffee_id` (FK coffees, required)
- `recipe_id` (FK recipes, nullable — freestyle brews allowed)
- `brewer_id` (FK equipment, required)
- `grinder_id` (FK equipment, nullable)
- `kettle_id` (FK equipment, nullable)
- `water_type` (text — e.g. "Third Wave Water", "tap filtered")
- `dose_grams_actual` (numeric)
- `water_grams_actual` (numeric)
- `water_temp_c_actual` (numeric)
- `grind_setting_actual` (text)
- `rating` (numeric, 0.0–5.0, in 0.25 increments)
- `flavor_note_ids_observed` (array of FK to flavor_notes)
- `notes` (text)
- `brewed_at` (timestamptz, default now)
- `days_off_roast` (computed in query from coffee.roast_date and brewed_at — don't store)
- `created_at`, `updated_at`

### api_credentials (admin-only)
- `id` (PK)
- `provider` (enum: anthropic, openai)
- `api_key_encrypted` (bytea — Fernet-encrypted)
- `model` (text — e.g. "claude-opus-4-7", "gpt-4o")
- `enabled` (bool)
- `updated_at`

The Fernet key comes from an env var `APP_ENCRYPTION_KEY` set in the container. Document how to generate it.

### app_settings (admin-managed runtime configuration)

Generic key-value store for application settings that should be editable at runtime without a redeploy. Distinct from env vars, which are reserved for bootstrapping (DB connection, secrets) and infrastructure (timezone, log level).

- `key` (text, PK)
- `value` (text — JSON-encoded; app parses to typed value on read)
- `description` (text — human-readable, shown in admin UI)
- `value_type` (enum: string, integer, boolean, json — hint for the admin UI to render the right input control)
- `updated_at`
- `updated_by_user_id` (FK users, nullable for system-seeded defaults)

**Initial seed values (created by first migration)**:
- `recommendation_region` → `"US"` (controls geographic scope of live coffee search; comma-separated region codes or `"any"`)

Future settings will live here as the app grows (e.g. backup retention, AI rate limits, default min sessions for recommendations). Adding a new setting = adding a row in a migration + reading it via the settings service.

### sessions
Standard table-backed session store (signed cookie holds session ID). 30-day expiry, refresh on activity.

## Pages

### 1. Home page (`/`)

Authenticated. Shows the current user's data, derived from their brew sessions:

- **Top coffees**: top 5 by avg rating (min 2 sessions), with avg rating and session count
- **Preference profile** (data-derived, not user-entered):
  - Avg rating by origin (country)
  - Avg rating by process
  - Avg rating by roaster
  - Avg rating by roast level
  - Top 10 flavor descriptors appearing in 4.0+ rated sessions
  - Roast freshness sweet spot (rating vs days-off-roast scatter or bucketed averages: 0-3, 4-7, 8-14, 15-21, 22+ days)
- **Sweet spots** (cross-dimensional patterns — pure SQL, no AI):
  - Top 3 multi-dimensional combinations from user's data, ranked by avg rating
  - Each row groups by `(origin, process, brewer, recipe)` with `min_sessions = 3` filter
  - Display: descriptor chips ("Washed · Ethiopia · Hario Switch · 20g/320g three-pour") + avg rating + session count
  - Below the data: AI-narrated interpretation paragraph (1–2 sentences) tying the patterns together — generated as part of the coffee recommendation flow, cached the same way. If AI is disabled or unavailable, show the patterns without prose.
  - Query implementation: union of multiple GROUP BY queries with HAVING clauses; pre-compute as a materialized view if performance becomes an issue
- **AI: Live coffee recommendation** (single best match with verified product URL and suggested recipe — see AI Integration below)
- **AI: Equipment recommendation**
- **AI: Paste-and-rank** (collapsed by default, expands on tap)
- **Recent brews**: last 10 sessions, table form, link to edit
- **Unrated coffees**: coffees in the catalog the user hasn't brewed yet

Each home-page section should lazy-load via HTMX after initial page render, so the page is responsive even if AI calls are slow.

### 2. Log page (`/log`)

Tabbed interface (Coffees / Brew Sessions). Tabs are full-width segmented control on mobile, inline tabs on desktop. Default tab: Brew Sessions (most common action).

### Guided Brew Mode

From any recipe or brew session form, a "Start guided brew" button launches a full-screen brewing assistant:
- Large countdown timer (readable from across a kitchen)
- Current step highlighted with cumulative water target and elapsed time
- Auto-advance to next step at the configured time (with 3-second visual + haptic warning before transition)
- Audible chime + vibration at each step transition (configurable)
- Pause/resume controls
- Cancel returns to the previous screen without logging
- "Done brewing" returns to the brew session form with timer data, recipe, and selected coffee prefilled — user only fills in rating, observed flavor notes, and notes

Designed for thumb operation while pouring water with the other hand. Wake lock requested to keep the screen on during the session.

**Coffees tab (household catalog)**
- Add new coffee form (modal or inline)
- All non-archived coffees in a table: name, roaster, origin, process, roast date, days off roast (computed), avg rating across all users, your avg rating, photo thumbnail
- Edit / archive actions
- Filter by roaster, country, process, archived state
- Bag photo upload (single image, JPEG/PNG/WebP, max 5MB, auto-resize to max 1600px wide, generate 400px thumbnail)

**Brew Sessions tab (yours only)**
- Add new brew session form. Fields:
  - Coffee (searchable dropdown, required)
  - Recipe (searchable dropdown, optional — if selected, prefills dose/water/temp/grind which can be overridden)
  - Brewer (required, dropdown filtered to equipment type=brewer)
  - Grinder (dropdown, type=grinder, optional)
  - Kettle (dropdown, type=kettle, optional)
  - Water type (free text with autocomplete from prior entries)
  - Dose, water, temp, grind setting (numeric/text)
  - Rating (slider or numeric, 0–5 in 0.25 steps)
  - Flavor notes observed (tag input — autocomplete from existing tags, allow new)
  - Notes (textarea)
  - Brewed at (datetime, default now)
- Table of your sessions below: date, coffee, rating, brewer, recipe, days off roast, edit/delete actions
- **Quick re-log**: each session row has a one-tap "Brew again" action that opens a new session form prefilled with that session's coffee, recipe, brewer, grinder, kettle, water type, dose, water, temp, and grind setting — leaving only rating, observed flavor notes, and notes blank. Highest-frequency action when working through a bag.
- Filter by coffee, brewer, rating range, date range
- CSV export of your sessions

### 3. Config page (`/config`)

Authenticated, any user. Manages shared household resources.

**Equipment section**
- CRUD on equipment. Group by type. Show usage count (how many brew sessions reference it).
- Archive instead of hard delete if equipment is referenced by any session.

**Recipes section**
- CRUD on recipes. Step builder UI: add/remove/reorder steps, each with cumulative water grams and time offset.
- Visual preview of pour timeline.
- Duplicate-recipe action for easy variants.

### 4. Admin page (`/admin`)

Restricted to `is_admin=true`. Returns 403 otherwise.

- **User management**: list, create, edit (reset password, toggle admin, deactivate), delete
- **API credentials**: configure Anthropic key, OpenAI key, model selection per provider, enable/disable toggle. Keys masked after save (show only last 4 chars).
- **Application settings**: edit values from the `app_settings` table. UI renders one row per setting using `value_type` to choose the right input control (text input, number input, checkbox, or JSON textarea). Each row shows the description as helper text. Save persists to DB and is reflected immediately on next read — no restart required.
- **Backup**: 
  - Manual: download `pg_dump` SQL file and ZIP of photos directory on demand
  - Automated: nightly `pg_dump` + photos tarball written to `/app/data/backups` (mounted volume), 14-day retention (configurable via `BACKUP_RETENTION_DAYS`), runs at 02:00 in `APP_TIMEZONE` via APScheduler
  - Admin UI shows list of available backups with size and timestamp, download button per backup, manual "Run backup now" button
- **System info**: app version, DB version, photo storage usage, backup storage usage, session count, last backup timestamp + status

## Global Search

Persistent search input in the top navigation (collapsed to an icon on mobile, expands to full-width search sheet on tap). Searches across:
- Coffee names
- Roaster names
- Flavor note names (both advertised and observed)
- Brew session notes
- Recipe names and descriptions
- Equipment names

Implementation: PostgreSQL full-text search with a single materialized `search_index` view or trigram indexes on relevant columns. Results grouped by entity type, each result linking to the relevant edit page. HTMX-powered live results as the user types (debounced 250ms).

Scope: a user only sees their own brew session notes in results, but all shared catalog (coffees, equipment, recipes, roasters, flavor notes) is searchable.

## Authentication

- Login page at `/login` (username + password). No registration page — admin creates users.
- Logout at `/logout`.
- Argon2id with sensible parameters (memory_cost 64MB, time_cost 3, parallelism 4).
- Session cookie: HttpOnly, Secure, SameSite=Lax, signed with `APP_SECRET_KEY` (env var).
- Rate limit `/login`: 5 attempts per IP per 15 minutes.
- First-run bootstrap: if no users exist, the first `/login` request redirects to `/setup` which creates the initial admin user.

## Security Hardening (required)

- **CSRF tokens** on all state-changing forms (POST/PUT/DELETE). Use `fastapi-csrf-protect` or hand-rolled double-submit cookie pattern. HTMX requests include the token via `hx-headers` from a meta tag.
- **Security headers** on every response:
  - `Content-Security-Policy`: restrictive — self for scripts/styles/images, allow Tailwind CDN and any required HTMX CDN explicitly, no inline scripts (use nonces if required)
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(self), microphone=(), geolocation=()`
  - `Strict-Transport-Security` set at the NGINX layer (document in README, not the app)
- **Input validation**: all form inputs validated via Pydantic schemas. Numeric ranges enforced (rating 0–5, temp 0–100°C, etc.). Reject oversized payloads early.
- **File upload validation**: verify image magic bytes match declared content-type, reject anything that doesn't decode as a valid image via Pillow, strip EXIF on upload.
- **Output escaping**: Jinja2 autoescape on for all templates. Never use `|safe` on user-provided content.
- **API key storage**: encrypted at rest via Fernet (already specified). Never logged. Never echoed back in API responses (only show last 4 chars in admin UI).
- **Audit-friendly logging**: log auth events (login success/failure, password reset, user creation, admin actions) with user ID, IP, timestamp. Do NOT log PII or request bodies.

## AI Integration

All flows are exposed on the home page and gated behind admin-configured API keys (graceful "AI not configured" message if disabled).

### Flow 1: Live coffee recommendation (primary)

The headline AI feature. Generates a single best-match coffee recommendation that is currently available for purchase, with a verified product URL and a suggested brewing approach grounded in the user's own data.

**Inputs to the model**:
- User's taste profile derived from brew sessions: top-rated origins, processes, roasters, roast levels, flavor descriptors from 4.0+ sessions, lowest-rated patterns (what to avoid)
- User's roaster history (which roasters they've bought from and how those rated)
- User's current equipment (so recommendations match their brewing capability)
- User's existing recipe library
- Recent sessions for freshness context
- Geographic scope (read from `app_settings.recommendation_region`; default `US`)

**Required tool**: web search. Anthropic's `web_search_20250305` tool or OpenAI's equivalent search tool. The model uses search to find currently-available specialty coffee matching the user's profile.

**Generation flow (must follow this order)**:
1. **Primary search**: model searches for coffees matching the user's strongest preferences (top origin + process + roast level). Returns single best match if found.
2. **Broadened search fallback**: if primary search finds nothing in stock matching all preferences, relax constraints in priority order (process → roast level → origin) and re-search.
3. **Characteristics-only fallback**: if even the broadened search returns nothing useful, return a characteristics-only recommendation (no specific bean, no link) describing what to look for.

The response must indicate which tier of the fallback chain produced it (`live`, `broadened`, `characteristics_only`) so the UI can show appropriate context.

**Recipe suggestion (part of the same response)**:
For the recommended coffee, suggest **which of the user's existing recipes** to brew with. Selection logic:
- Prefer the user's primary brewer (Hario Switch — identified as the brewer used in >50% of recent sessions). Recommend the recipe that has historically scored highest for similar bean profiles (matching origin + process + roast level).
- **If the user's data shows a different brewer scores meaningfully higher (e.g. >0.5 point avg rating delta) for this style of bean**, surface that as a callout: "Your data suggests trying this on the V60 instead — your washed Ethiopians score 4.4 on V60 vs 3.9 on Switch." Do not silently change the primary recommendation; flag the pattern and let the user decide.
- Never invent novel recipes. Only suggest from `recipes` table entries.
- If no existing recipe is a good match for the bean style, say so and link to the recipe builder.

**URL validation**: after the model returns a recommendation with a product URL, the backend MUST issue a HEAD request (with sane timeout, 5s) to verify the URL is reachable and returns 2xx. If validation fails, log it, strip the URL from the response, and append a note that the URL couldn't be verified. Do not display unverified URLs as clickable links.

**Pydantic response schema (structured output)**:
```python
class CoffeeRecommendation(BaseModel):
    tier: Literal["live", "broadened", "characteristics_only"]
    coffee_name: str | None  # null for characteristics_only
    roaster_name: str | None
    product_url: str | None  # null if validation failed or characteristics_only
    url_verified: bool
    process: str | None
    origin: str | None
    roast_level: str | None
    flavor_notes: list[str]
    price_usd: float | None
    why_recommended: str  # reasoning tied to user's data
    suggested_recipe_id: UUID | None  # FK to recipes
    suggested_recipe_rationale: str | None
    alternative_brewer_callout: str | None  # populated if a different brewer scores higher
    broadening_applied: list[str] | None  # which constraints were relaxed, if tier=broadened
    summary_prose: str  # short narrative paragraph
```

**UI rendering**:
- Card with coffee name, roaster, "Buy" button (only if URL verified), process/origin/roast badges, flavor note chips
- "Why this" section with the reasoning
- "Brew with: {recipe name}" section with link to recipe + the rationale
- Yellow callout if `alternative_brewer_callout` is populated
- Yellow banner if `tier == "broadened"` showing what was relaxed
- Gray empty-state styling if `tier == "characteristics_only"`

### Flow 2: Profile + paste (paste-and-rank)

User pastes text (a roaster's full lineup, scraped product list, anything). AI ranks the items against the user's taste profile, returning top 3 with reasoning grounded in the user's actual log data. Does NOT use web search — input is provided by the user.

UI: text area + submit button → results render below with ranking, score, and one-sentence reasoning each. On-demand only, never scheduled, not cached.

### Flow 3: Equipment recommendation

Profile-only (no web search). Inputs: current equipment, brewing patterns, ratings. Output: identifies weakest link in current setup OR confirms current setup is well-matched. Explicitly allowed to say "your current setup is well-aligned with what you brew, no changes recommended." Should not push purchases for the sake of it.

### Implementation notes
- Use Anthropic by default if both keys configured; fall back to OpenAI. Both providers must support web search — verify SDK versions at install time.
- Wrap all calls in a `ai_service.py` module with provider abstraction.
- **All AI endpoints use structured output** (Anthropic tool use / OpenAI function calling). Define Pydantic schemas per endpoint. Every schema includes a `summary_prose` field so the response renders as both structured UI and a short narrative paragraph. Validate response against schema; on schema mismatch, surface a "Try again" UI rather than rendering garbage.
- Web search adds 10–30s latency. All web-search flows must run async with progress indicator on the UI side (HTMX polling or SSE).
- URL validation runs in a background task after the model response is returned; the UI initially shows the URL as "verifying..." and updates once the HEAD check completes.
- Stream prose where the SDK supports it; render incrementally with HTMX SSE.

### AI run scheduling and cost control

AI calls are expensive (web search especially). Use signature-based regeneration:

**Input signature**: For each user, compute a hash of the data that feeds their AI calls:
- Coffee recommendation: `(brew_session_count, max(brew_sessions.updated_at), equipment_count, recipe_count for this user)`
- Equipment rec: same as above

Store the signature alongside each cached recommendation in an `ai_recommendations` table:
- `id`, `user_id`, `recommendation_type` (enum: coffee, equipment), `response_json`, `input_signature`, `generated_at`, `model_used`, `provider_used`, `tokens_used`, `web_search_used` (bool)

**Scheduled job (APScheduler, in-process)**:
- Fires nightly at 00:00 in `APP_TIMEZONE` (env var, default `America/Chicago`)
- For each active user with ≥3 brew sessions:
  - Compute current input signature
  - If different from stored signature for each recommendation type, regenerate that recommendation
  - If unchanged, skip — no API call
- Log job summary: users processed, regenerations triggered, skips, total tokens used (split by web-search and non-web-search calls), errors

**Manual refresh button**:
- "Refresh recommendations" button in the AI section header on home page
- Available to any authenticated user (refreshes their own recs)
- Bypasses signature check, always regenerates
- Runs async via HTMX (POST to `/ai/refresh`, returns 202 + polling endpoint or SSE), button shows spinner with "Searching the web for fresh coffees..." copy, recommendations swap in on completion
- In-memory lock per `(user_id, recommendation_type)` prevents concurrent runs from the scheduler and manual trigger

**Stale indicator**:
- On page render, compare current input signature to stored signature
- If mismatched, show a small "Outdated — refresh?" badge inline with the recommendation
- Gives users mid-day awareness without forcing automatic regeneration

**Paste-and-rank flow**: on-demand only, never scheduled, not cached (input changes every time the user pastes).

**Cold start**: Users with <3 brew sessions see a friendly empty state ("Log at least 3 brews to unlock recommendations") instead of a degraded AI output.

## Container & Deployment

### docker-compose.yml requirements
- Two services with explicit `container_name`: `coffee-snobbery` (web), `coffee-snobbery-db` (database)
- Both on user-defined bridge network `coffee-snobbery-net`
- `coffee-snobbery` exposes port 8080 to host
- `coffee-snobbery-db` only on internal Docker network
- Named volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups`
- `coffee-snobbery` depends_on `coffee-snobbery-db` with healthcheck
- Both services restart unless-stopped

### Environment variables (document in .env.example)
- `DATABASE_URL` (constructed from POSTGRES_USER/PASSWORD/DB)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `APP_SECRET_KEY` (for session signing)
- `APP_ENCRYPTION_KEY` (Fernet key for API credential encryption)
- `TRUSTED_PROXY_IPS` (for X-Forwarded-* honoring)
- `APP_TIMEZONE` (default `America/Chicago`, used for scheduled jobs)
- `BACKUP_RETENTION_DAYS` (default 14)
- `LOG_LEVEL` (default INFO)

Include a one-liner in the README for generating both keys via Python `secrets` / Fernet.

### Reverse proxy
The app must work correctly when proxied. Set `root_path` if needed. Generate URLs respecting `X-Forwarded-Proto`. Do not bake host assumptions into templates.

### Migrations
Alembic migrations auto-run on container startup via an entrypoint script. First-run creates schema.

## Project Layout

```
coffee-snobbery/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
├── alembic.ini
├── pyproject.toml (or requirements.txt)
├── entrypoint.sh
├── app/
│   ├── main.py            (FastAPI app factory)
│   ├── config.py          (settings via pydantic-settings)
│   ├── database.py        (SQLAlchemy engine, session)
│   ├── models/            (SQLAlchemy models, one file per entity)
│   ├── schemas/           (Pydantic schemas for forms)
│   ├── routers/           (one file per page: home, log, config, admin, auth)
│   ├── services/
│   │   ├── auth.py
│   │   ├── ai_service.py
│   │   ├── encryption.py
│   │   ├── settings.py    (typed read/write of app_settings table, with simple in-memory cache)
│   │   ├── photos.py
│   │   ├── search.py
│   │   ├── backup.py
│   │   ├── scheduler.py   (APScheduler setup, nightly AI + backup jobs)
│   │   └── analytics.py   (preference derivation queries)
│   ├── templates/
│   │   ├── base.html
│   │   ├── partials/      (HTMX fragments)
│   │   └── pages/
│   ├── static/            (any custom CSS beyond Tailwind, JS for Alpine components)
│   └── migrations/        (Alembic)
└── tests/
    └── test_smoke.py
```

## Out of Scope (do not build)

- Social features, sharing, public profiles
- Mobile app (web responsive only)
- Multi-tenant / org separation (single household = single deployment)
- Subscription billing
- Email notifications
- OAuth / SSO
- Real-time websockets (HTMX SSE for AI streaming is fine)
- Inventory management (count of bags in cupboard, depletion tracking) — maybe v2
- Coffee shop / cafe discovery features

## Acceptance Criteria

- `docker compose up -d` from a clean checkout brings up a working app on port 8080
- First visit redirects to `/setup` to create the initial admin
- Admin can create additional users via `/admin`
- Each user can log brew sessions tied to shared coffees, equipment, recipes
- Home page renders preference analytics from real session data
- Home page AI recommendations work when keys are configured, gracefully degrade when not
- Live coffee recommendation uses web search, returns a verified product URL, and falls back through broadened search and then characteristics-only as in-stock matches diminish
- Recommended recipe is selected from the user's existing recipe library, never invented
- Alternative-brewer callout appears when historical data shows a different brewer scores meaningfully higher for the recommended bean's style
- Product URLs are HEAD-checked before being rendered as clickable links; unverified URLs surface as text with a "couldn't verify" note
- Sweet spots section on home page shows top 3 cross-dimensional combinations (origin × process × brewer × recipe) from pure SQL, with AI prose interpretation when available
- AI recommendations regenerate nightly only when input signature has changed; manual refresh button bypasses signature check
- Stale recommendation badge appears when underlying data changes between scheduled runs
- Guided brew mode launches from a recipe, keeps the screen awake, advances steps with audio + haptic cues, and prefills the brew session form on completion
- Quick re-log action on any session prefills a new session form correctly
- Global search returns results across coffees, roasters, flavor notes, recipes, equipment, and the current user's session notes
- Roaster and flavor note autocomplete prevents fragmentation while allowing new entries
- Bag photo upload works, thumbnails generated, served via app (not directly from disk), EXIF stripped
- CSV export of brew sessions produces a valid file with all relevant columns
- App functions correctly when proxied behind NGINX with HTTPS termination
- App is installable as a PWA on iOS Safari and Android Chrome
- Brew session form is fully usable at 375px viewport width without horizontal scroll
- Bottom tab nav appears below 768px, top nav at or above 768px
- Camera opens directly when tapping the bag photo upload control on mobile
- Automated nightly backup runs at 02:00 local time, retains 14 days by default, admin can download any retained backup
- CSRF protection blocks forged state-changing requests; security headers present on all responses
- Smoke test passes: create user, create coffee, create equipment, create recipe, log session, view home page

## README must include

- Project title: "Snobbery" with tagline "A self-hosted coffee log for people who own a gooseneck kettle and have opinions about water"
- Stack overview
- Prerequisites (Docker, Docker Compose)
- Setup steps (copy .env.example, generate keys, compose up)
- NGINX server block example for reverse proxy (using `coffee-snobbery` as the proxy_pass target name)
- Backup and restore procedure
- How to add the AI keys via the admin UI
- Troubleshooting common issues
