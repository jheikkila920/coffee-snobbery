# Architecture Research — Snobbery v1.2 Integration

**Domain:** Self-hosted household coffee log (v1.2 new-feature integration into existing FastAPI app)
**Researched:** 2026-05-25
**Confidence:** HIGH — all findings grounded in direct source code reads of the actual v1.1 codebase

---

## System Overview (Current v1.1 State)

```
Browser (mobile-first, 375px primary)
    |  HTMX 2.0.10 + Alpine.js CSP build + Tailwind v3 standalone CLI
    v
Nginx Proxy Manager (host container, owns 80/443)
    -> coffee-snobbery:8000 over shared docker net (TRUSTED_PROXY_IPS=*)
    v
Uvicorn (1 worker, --proxy-headers, --workers 1 enforced in entrypoint.sh)
FastAPI app
    |
    +-- Middleware stack (outer->inner):
    |     RequestContextMiddleware   (nonce + request_id)
    |     SecurityHeadersMiddleware  (nonce-CSP + all security headers)
    |     FragmentCacheHeadersMiddleware (no-store on HX-Request fragments)
    |     CSRFFormFieldShim          (form field -> header hoist)
    |     CSRFMiddleware             (double-submit cookie, starlette-csrf)
    |     SessionMiddleware          (table-backed async, SessionLocal)
    |
    +-- Routers (18 total in app/routers/):
    |     pwa, csp_report, auth, debug, admin,
    |     roasters, flavor_notes, coffees, equipment, recipes, bags,
    |     brew_guided, brew (+data_router), home, config_hub,
    |     ai, photos, search
    |
    +-- Services (app/services/):
    |     ai_service, analytics, scheduler, credentials,
    |     encryption, search, settings, wishlist
    |
    +-- APScheduler (in-process, single worker — INVIOLABLE):
          nightly AI refresh (coffee rec + sweet spots per user)
          nightly pg_dump backup + photos tar + retention prune
    |
    v
PostgreSQL 16 (coffee-snobbery-db container)
    Shared catalog: coffees, roasters, flavor_notes, equipment, recipes, bags
    Per-user:       brew_sessions, ai_recommendations, wishlist_entries, brew_drafts, sessions
    Admin:          users, api_credentials, app_settings
```

---

## Q1: AI Page Consolidation — Router and Template Structure

### Current AI surface map (verified from source)

| Surface | Current location | Current route | Fragment/Template |
|---------|-----------------|---------------|-------------------|
| AI coffee rec hero card | home page | `GET /home/cards/ai-recommendation` in `home.py` | `fragments/home/ai_rec_hero.html` + 4 state variants |
| Manual AI refresh button | home page | `POST /ai/refresh` in `ai.py` | Returns 204 + HX-Trigger or inline HTML |
| Sweet spots AI prose | home page sweet-spots card | `GET /home/cards/sweet-spots` in `home.py` | `fragments/home/sweet_spots.html` (includes prose) |
| Equipment rec (on-demand) | home page | `POST /ai/equipment` in `ai.py` | `fragments/home/equipment_rec.html` |
| Paste-and-rank page | standalone | `GET /ai/paste-rank`, `POST /ai/paste-rank` in `ai.py` | `pages/paste_rank.html`, `fragments/ai/paste_rank_results.html` |
| Wishlist page | standalone | `GET /ai/wishlist` in `ai.py` | `pages/wishlist.html` |
| Wishlist CRUD | anywhere | `POST /ai/wishlist/add`, `/purchase`, `/remove` | 204 + HX-Trigger |

### What moves to the AI page vs what stays on home

**Move to `/ai` page:**
- The AI coffee rec hero card. The fragment endpoint `GET /home/cards/ai-recommendation` becomes `GET /ai/cards/recommendation` (or is aliased). The fragment template relocates from `fragments/home/` to `fragments/ai/`. The polling `hx-trigger` in the AI page template points at the new URL.
- The manual refresh button. `POST /ai/refresh` handler itself does not change — it returns `HX-Retarget="#ai-rec-hero"` and `HX-Reswap="outerHTML"` which targets the hero div wherever it lives. Only the template wiring changes.
- The equipment rec card and its `POST /ai/equipment` handler. Template reference moves from `fragments/home/equipment_rec.html` to `fragments/ai/equipment_rec.html` (rename optional — path is a single string in one handler).
- Sweet spots AI prose. Currently rendered inside `fragments/home/sweet_spots.html` via `sweet_spots_prose` context var loaded in `card_sweet_spots()`. Move the AI prose to the `/ai` page as its own card. Strip the prose from the home card entirely.

**Stays on home:**
- The five analytics data cards: top-coffees, preference-profile, flavor-descriptors, roast-freshness, sweet-spots (the SQL data table view — just without the AI prose overlay). These are the user's log data, not AI output.
- Recent brews and unrated coffees (operational log data, not AI).
- The cold-start gate check in `home_shell()`. The `/` route still calls `analytics.get_cold_start_counts` and passes the gate state to `pages/home.html`. The home page may show a simplified teaser ("AI is ready — see the AI tab") instead of the full rec card.

**New on `/ai` page:**
- The `/ai` router already exists in `app/routers/ai.py`. Add `GET /ai` as the page shell handler alongside the existing POST handlers.
- New `pages/ai.html` template: AI rec hero as primary content, equipment rec on-demand section, sweet spots prose section, links to paste-rank and wishlist.

### Preserving signature-based regen, cold-start gate, and polling

The signature check, regen, and nightly scheduler are entirely inside `ai_service.regenerate()` and `scheduler.py`. Nothing about moving the UI fragment to a different page touches these. Verified: `ai_service._LOCKS`, `_THROTTLE`, `regenerate()`, `in_flight()`, `is_stale()` — all operate on `user_id` and `rec_type` strings; they have no knowledge of which page renders the result.

The cold-start gate (`analytics.get_cold_start_counts`) must be called in the new `GET /ai/cards/recommendation` handler just as it is in the current `GET /home/cards/ai-recommendation` handler. Same function, same signature, same DB query. Copy the exact five-branch logic from `home.py card_ai_recommendation()` into the new AI-router handler.

The polling flow (`hx-trigger="aiRecUpdated"` event from `POST /ai/refresh`) is controlled entirely in the template — the handler returns `HX-Trigger: aiRecUpdated` unconditionally regardless of what page the button is on.

### Concrete component changes

**NEW (v1.2):**
- `app/routers/ai.py` — add `GET /ai` page shell handler (new route on existing router)
- `app/templates/pages/ai.html` — new full page extending base.html
- `app/templates/fragments/ai/recommendation_hero.html` — relocated from `fragments/home/ai_rec_hero.html`
- `app/templates/fragments/ai/equipment_rec.html` — relocated from `fragments/home/equipment_rec.html` (optional rename)

**MODIFIED (v1.2):**
- `app/routers/home.py` — add `GET /ai/cards/recommendation` handler (five-branch state machine, same logic as current `card_ai_recommendation`); strip `get_latest_recommendation` call from `card_sweet_spots()`
- `app/templates/pages/home.html` — remove AI rec hero section; add teaser or link to /ai page
- `app/templates/fragments/home/sweet_spots.html` — remove `sweet_spots_prose` block
- `app/routers/ai.py` — `GET /ai` page shell handler

**UNCHANGED:**
- `POST /ai/refresh`, `POST /ai/equipment`, `POST /ai/paste-rank`, all wishlist POSTs — handlers are not changed
- `app/services/ai_service.py` (existing functions) — zero changes
- `app/services/analytics.py` — zero changes
- `app/services/scheduler.py` — zero changes
- `app/models/ai_recommendation.py` — zero changes

---

## Q2: Cafe Quick-Rate Data Model

### Options analyzed

**Option A — Separate `cafe_logs` table (new entity)**
A new table with: `user_id`, `brand` (text, roaster/brand name), `coffee_name`, `brew_method` (text), `rating`, `notes`, `logged_at`.

**Option B — Optional-field variant on `brew_sessions`**
Add `cafe_mode boolean` + nullable `cafe_brand` to `brew_sessions`; use a sentinel/null `coffee_id`.

**Option C — Nullable-recipe brew session (minimal change)**
A brew session where `coffee_id` points to a shared catalog "cafe placeholder" coffee, `bag_id` / `recipe_id` are NULL.

### Trade-off analysis (grounded in the actual schema)

**Option B is the worst choice.** `brew_sessions.coffee_id` is `NOT NULL` with `ForeignKey("coffees.id", ondelete="RESTRICT")` — verified from `app/models/brew_session.py` line 79. Making it nullable is a lossy migration that breaks a documented architectural invariant. More critically, every analytics function in `analytics.py` does an INNER JOIN on `BrewSession.coffee_id == Coffee.id` without any guard. NULL `coffee_id` rows would be silently excluded from all analytics — acceptable in principle, but the implicit exclusion is a maintenance trap. `compute_input_signature()` in `analytics.py` iterates rated sessions by `BrewSession.coffee_id` and would need guards everywhere. Every query becomes `WHERE brew_sessions.cafe_mode IS NOT TRUE`. This is a pervasive pollution.

**Option C is workable but still polluting.** A shared "cafe placeholder" coffee solves the NOT NULL constraint but not the analytics join problem. The placeholder coffee surfaces in `get_top_coffees()` rankings, `get_preference_profile()` origin/process breakdowns, and `get_flavor_descriptors()`. Filtering it out requires a `coffee.is_placeholder` flag and edits to every analytics query. This is a covert schema dependency that makes analytics.py harder to reason about.

**Option A is correct.** Verdict: separate `cafe_logs` table.

- Zero impact on `brew_sessions`. All existing analytics, AI signature computation, and scheduler logic are unaffected. Verified: `compute_input_signature()` queries `BrewSession` with no knowledge of any other table except `Bag` via outer join.
- Zero impact on `compute_input_signature` — cafe logs do not feed AI recommendations by default. If a future milestone wants to incorporate cafe ratings into AI signals, that is an explicit design decision with a clear migration path, not an accident.
- Per-user scoping is trivial: `user_id RESTRICT FK` mirrors `brew_sessions.user_id`.
- The brew session fast path (prefill, sub-30s logging) is untouched.
- Migration is purely additive: one new `CREATE TABLE cafe_logs` with no changes to existing tables.
- Admin user-delete logic needs one additional `DELETE FROM cafe_logs WHERE user_id = ...` before deleting the user — same pattern as brew_sessions (which also uses RESTRICT and requires explicit handling before delete).

### Recommended schema

```python
class CafeLog(Base):
    """A cafe or out-of-home coffee tasting. Per-user; no catalog FK. (v1.2)"""
    __tablename__ = "cafe_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Free text -- no FK to coffees; that is the point of this entity
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)       # roaster/cafe name
    coffee_name: Mapped[str] = mapped_column(Text, nullable=False)
    brew_method: Mapped[str | None] = mapped_column(Text, nullable=True)  # "V60", "espresso", etc.
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)  # 0-5, 0.25 steps
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    logged_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_cafe_logs_user_logged_at", "user_id", text("logged_at DESC")),
    )
```

**FK asymmetry:** `user_id` uses `RESTRICT` (same as `brew_sessions.user_id`). No other FKs.

**Intentionally omitted:** `coffee_id`, `bag_id`, `recipe_id`, `brewer_id`, `grinder_id`, `dose_grams`, `water_grams`, `tds_pct`, `extraction_yield_pct` — the brew session parameters that cafe quick-rate explicitly does not capture.

**Analytics isolation (hard boundary):** Cafe logs do NOT feed `compute_input_signature`, `get_top_coffees`, `get_preference_profile`, `get_sweet_spots`, or any other analytics function. This is correct by design and must remain documented.

---

## Q3: AI Research-a-Coffee + Predict Rating

### Where it lives

**New function in `app/services/ai_service.py`: `research_coffee_predict_rating()`**

Do not extend the existing `regenerate()` entry point. That function runs the nightly bundle (coffee rec + sweet spots per user) and has its own signature-based skip logic, throttle, and advisory lock. `research_coffee_predict_rating` is on-demand, triggered by the user — follow the pattern of `generate_equipment_rec()` which is already on-demand and not nightly.

Do not create a separate `ai_predict_service.py`. The AI provider abstraction, credential loading, client builders (`_build_anthropic_client`, `_build_openai_client`), the structured output pattern (`_project_tool_use_input`), and `_write_recommendation_row` all live in `ai_service.py`. Splitting would require reimporting most of that infrastructure into a new module. Follow the `generate_equipment_rec` pattern exactly.

### How it uses analytics.py as input signal

`analytics.py` functions are already pure read-only SQL: call them directly with no modification.

```python
async def research_coffee_predict_rating(
    user_id: int,
    coffee_name: str,
    roaster_name: str | None,
    db: Session,
) -> tuple[str, AIRecommendation | None]:
    # Read preference signals (all existing functions, no changes)
    profile = analytics_service.get_preference_profile(db, user_id)
    top_coffees = analytics_service.get_top_coffees(db, user_id)
    flavor_descriptors = analytics_service.get_flavor_descriptors(db, user_id)
    # Build prompt from preference data + coffee name/roaster
    # Call provider with web_search (to look up the specific coffee) + structure_output
    # Persist via _write_recommendation_row(..., rec_type="coffee_predict", ...)
    # Return (status, row)
```

### New Pydantic schema (add to `app/services/ai_schemas.py`)

```python
class CoffeePredictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicted_rating: float        # 0.0-5.0
    confidence: str                # "high" | "medium" | "low"
    rationale: str                 # 2-3 sentences citing user preference signal
    web_sources_used: list[str]    # URLs the LLM found for this specific coffee
```

### `recommendation_type` value

Use `"coffee_predict"` as the `recommendation_type` string — the existing `ai_recommendations` table already uses text-as-enum for this column (values: `"coffee"`, `"equipment"`, `"paste_rank"`, `"sweet_spots"`). No schema change needed. Cost telemetry works automatically via the existing JSONB `response_json` + token columns. Persist with `generated_by="manual_refresh"`.

### Route placement (add to `app/routers/ai.py`)

- `GET /ai/research` — page shell, renders `pages/ai_research.html` (form: coffee name + optional roaster; optionally shows user's wishlist so they can click "research this" on a wishlist entry)
- `POST /ai/research` — calls `research_coffee_predict_rating()`, returns HTMX fragment (`fragments/ai/predict_result.html`) with predicted rating + rationale + web sources + "Add to wishlist" button

The result card includes a "Add to wishlist" button that calls `POST /ai/wishlist/add` — the existing endpoint, unchanged.

### Throttle

Apply the same 5-minute per-user throttle. Recommend sharing the existing `_THROTTLE` dict (any AI call within 5 minutes blocks another) — cost control simplicity at household scale. The `_evict_stale_throttle` call already runs on every throttle check.

---

## Q4: IA Changes — Admin Off Bottom Nav, AI Tab In, PWA Implications

### Current bottom nav (verified from `app/templates/base.html`)

```
Home | Log | Config | Admin (conditional: only if request.state.user.is_admin)
```

Four tabs. Admin tab is conditionally rendered via `{% if request.state.user.is_admin %}`. Top nav (>=768px) has the same conditional Admin link.

### Target bottom nav for v1.2

```
Home | Log | Config | AI
```

Admin moves off the bottom nav to the Config hub page. AI replaces it as the fourth tab. All authenticated users see the AI tab (no is_admin condition).

### Changes required — explicit file list

**`app/templates/base.html` (MODIFIED):**
- Bottom nav: remove the Admin tab block (`{% if request.state.user.is_admin %}<a href="/admin">Admin</a>{% endif %}`). Replace with unconditional AI tab (`<a href="/ai">AI</a>`).
- Top nav links section: remove `{% if request.state.user.is_admin %}<a href="/admin">Admin</a>{% endif %}`. Add `<a href="/ai">AI</a>` to the nav links alongside Home, Log, Config.

**`app/templates/pages/config_hub.html` (MODIFIED):**
Add an Admin card in the grid, conditionally rendered for `is_admin`. The grid currently has 5 cards (Coffees, Equipment, Recipes, Roasters, Flavor Notes); Admin becomes a sixth card. Pattern is identical to existing cards:
```html
{% if user.is_admin %}
<a href="/admin" class="flex items-center gap-3 rounded-xl border ... same style as others ...">
  <!-- shield icon SVG -->
  <span class="text-base font-semibold text-espresso-900 dark:text-cream-100">Admin</span>
</a>
{% endif %}
```
The config_hub handler already receives `user` in context — no handler change needed.

**`app/static/js/alpine-components/nav-bar.js` (MODIFIED):**
```javascript
get activeTab() {
  const p = window.location.pathname;
  if (p === '/' || p.startsWith('/home')) return 'home';
  if (p.startsWith('/brew')) return 'brew';
  if (p.startsWith('/config') || p.startsWith('/coffees') ||
      p.startsWith('/equipment') || p.startsWith('/recipes') ||
      p.startsWith('/roasters') || p.startsWith('/flavor-notes')) return 'config';
  if (p.startsWith('/ai')) return 'ai';
  // '/admin' intentionally removed -- Admin is no longer a bottom-nav item
  return '';
}
```

**`tests/test_nav.py` (MODIFIED):**

Current test assertions that will break or need updating:

1. `test_non_admin_home_has_no_admin_link`: Currently asserts `'href="/admin"' not in r.text` on the home page response. After the nav change this assertion will still pass on the home page (admin link is removed from nav). However, the admin link still appears on `/config` for admin users. The test remains valid but its intent should be clarified in the docstring.

2. `test_admin_home_has_admin_link`: Currently asserts `'href="/admin"' in r.text` on the home page (`GET /`). This test WILL FAIL after the change because the home page response will no longer contain `href="/admin"` in the top or bottom nav. Update to assert on `GET /config` for admin user instead.

3. New test needed: `test_ai_tab_present_for_authenticated_users` — assert `href="/ai"` appears in any authenticated page response.

4. New test needed: `test_config_hub_has_admin_link_for_admin` — assert `href="/admin"` appears in `GET /config` response for an admin user.

5. New test needed: `test_config_hub_has_no_admin_link_for_non_admin` — assert `href="/admin"` does not appear in `GET /config` for a non-admin user.

### PWA service worker implications

The service worker in `app/static/js/sw.js` is content-deterministic:
- `APP_SHELL` array contains only: `/manifest.json`, `/static/img/icon-192.png`, `/static/img/icon-512.png`, `/static/img/apple-touch-icon.png`, `/static/img/logo-badge.png`. No nav-specific paths.
- `/` is explicitly NOT precached (CR-02: authenticated shell must not be cached across users).
- `nav-bar.js` lives under `/static/js/alpine-components/nav-bar.js` — served via `StaticFiles`, caught by the `isStatic` stale-while-revalidate branch.

**No changes needed to `sw.js` or `manifest.json` for the nav IA change.** The cache-name bump from `build_id.txt` (written unconditionally on every Docker build) will automatically invalidate the stale-while-revalidate cache for `nav-bar.js` on the next rebuild. The modified `nav-bar.js` reaches the browser on the next page load after the cache updates.

**QA caution (from project memory `[SW stale cache confounds UI verify]`):** The service worker SWRs `/static/`, so during verification the tester must "Clear site data" (not just bypass cache) to get the updated `nav-bar.js`. This is a testing discipline note, not an architecture change.

The `manifest.json` `start_url: "/?source=pwa"` is unaffected. PWA install flow is unaffected. `pwa_router._BUILD_HASH` derivation is unaffected.

---

## Q5: Self-Host Packaging — Prebuilt Image and First-Run Integration

### Current build flow (operator today)

Operator clones repo, runs `docker compose build coffee-snobbery` (multi-stage: Tailwind compile in stage 1, Python runtime in stage 2, pg_client-16 install), then `docker compose up -d`. Requires Docker build toolchain, Tailwind download, build wait (~2 min).

### Target flow for v1.2

Operator pulls prebuilt image from registry (GHCR or Docker Hub), sets env vars in `.env`, runs `docker compose up -d`. No build step.

### Integration points (verified from actual code)

**`entrypoint.sh` (UNCHANGED in behavior):**
```bash
alembic upgrade head   # idempotent -- runs on every container start
exec uvicorn app.main:app --workers 1 ...
```
`alembic upgrade head` is already idempotent. On a fresh database it runs all migrations sequentially and sets up the full schema. On an existing database it runs only the delta since last deployed version. This is exactly correct for a prebuilt image: the operator starts the container, migrations run automatically, zero manual DB setup.

**First-run `/setup` flow (UNCHANGED):**
The `/setup` route in `app/routers/auth.py` gates on zero-users-exist. A brand-new operator hits `https://their-domain.com/setup`, creates the first admin account, redirects to `/login`. Works identically whether the image is built locally or pulled from a registry.

**Startup checks (from `app/main.py lifespan`):**
1. `engine.connect()` + `SELECT 1` — DB smoke check
2. `encryption_startup_check()` — validates `APP_ENCRYPTION_KEY` format, raises `EncryptionStartupError` on failure → uvicorn exits non-zero → HEALTHCHECK trips → container shows unhealthy
3. `credentials.rewrap_if_needed(db)` — MultiFernet key rotation
4. `settings_service.prewarm_cache(db)` — warms settings cache

All four steps run before uvicorn starts accepting requests. A misconfigured `.env` (bad `APP_ENCRYPTION_KEY`, missing `APP_SECRET_KEY`) surfaces as an unhealthy container within 20 seconds (HEALTHCHECK `--start-period=20s`). This is a good operator experience for a prebuilt image: clear failure, not a silent error.

**Build pipeline integration points:**

The Dockerfile stage 1 (Tailwind builder) compiles `tailwind.src.css` and writes `app/static/build_id.txt` with a UTC timestamp on every build. Stage 2 `COPY --from=tailwind-builder` pulls both the compiled CSS and `build_id.txt` into the runtime image. The service worker `CACHE_NAME` is set from `build_id.txt` via `pwa_router._get_build_hash()`. A prebuilt image correctly includes this file — the Dockerfile already handles it.

**`docker-compose.yml` changes for self-host distribution:**

The compose file must switch from `build: .` to `image: ghcr.io/owner/snobbery:latest` (or a pinned semver tag) for the `coffee-snobbery` service. A separate `docker-compose.build.yml` or `docker-compose.override.yml` should be provided for contributors who need to build locally. The operator compose file should contain no build context.

**`.env` documentation:**

`.env.example` already documents all required env vars. The new deploy doc must guide the operator through generating `APP_SECRET_KEY` (random 32-byte hex) and `APP_ENCRYPTION_KEY` (valid Fernet key from `cryptography.fernet.Fernet.generate_key()`). These two are the only non-obvious secrets — all others (`POSTGRES_*`, `TRUSTED_PROXY_IPS`, `APP_TIMEZONE`) are self-explanatory.

### Suggested build order for v1.2 phases

Dependencies must be respected; otherwise build here is "build/phase order for milestone planning":

1. **Cafe log data model** (`p12_cafe_logs.py` migration + `CafeLog` model) — purely additive, no existing table changes. First because other feature work (cafe router, analytics isolation) depends on the schema existing.

2. **Nav / IA restructuring** (`base.html`, `config_hub.html`, `nav-bar.js`, admin link relocation, nav test updates) — no data model dependency; unblocks AI page and mobile audit work. Do early.

3. **AI page consolidation** (new `GET /ai` page shell + `pages/ai.html`, move/rename fragments, update `home.html` and `home.py`) — depends on nav change so AI tab exists. Fragment URL migration can be phased: keep old URLs working via redirect if needed.

4. **AI research-a-coffee + predict rating** (new `research_coffee_predict_rating()` in `ai_service.py`, new `CoffeePredictSchema`, new routes in `ai.py`, new templates) — depends on AI page existing (it lives there). Uses `analytics.py` unmodified.

5. **Self-host packaging** (compose file update, GHCR CI workflow for image push, deploy docs, README update, NPM setup guide) — can be done in parallel with features; no feature dependency. The Dockerfile is already correct.

6. **v1.1 debt cleanup** (G-01 VPS chown, T-INFRA-1 test isolation, human UAT sign-offs) — interleave throughout; G-01 is a VPS one-time operation, T-INFRA-1 is test-code-only.

---

## Component Inventory: New vs Modified vs Unchanged

### NEW components (v1.2 additions)

| Component | Type | Notes |
|-----------|------|-------|
| `app/models/cafe_log.py` | New model | Separate entity for cafe quick-rate |
| `app/migrations/versions/p12_cafe_logs.py` | New migration | `CREATE TABLE cafe_logs (...)`, additive only |
| `app/routers/cafe.py` | New router (suggested) | CRUD for cafe_logs; OR extend `brew.py` with a `/cafe` prefix sub-router |
| `app/templates/pages/ai.html` | New template | AI destination page shell |
| `app/templates/pages/ai_research.html` | New template | Coffee research + predict form/result |
| `app/templates/fragments/ai/recommendation_hero.html` | New fragment | Relocated hero card for AI page (may rename from `fragments/home/ai_rec_hero.html`) |
| `app/templates/fragments/ai/equipment_rec.html` | New fragment | Relocated equipment rec (optional rename from `fragments/home/`) |
| `app/templates/fragments/ai/predict_result.html` | New fragment | Coffee predict result card |
| `app/services/ai_schemas.py: CoffeePredictSchema` | New Pydantic class | Structured output for predict flow |

### MODIFIED components (v1.2 changes to existing code)

| Component | What Changes |
|-----------|-------------|
| `app/routers/ai.py` | Add `GET /ai` page shell, `GET /ai/cards/recommendation` (five-branch state machine), `GET /ai/research` page, `POST /ai/research` handler |
| `app/routers/home.py` | Add `GET /ai/cards/recommendation`; strip `get_latest_recommendation` from `card_sweet_spots()`; update/remove AI hero card endpoint |
| `app/templates/pages/home.html` | Remove AI rec hero section; add teaser or link to /ai page |
| `app/templates/fragments/home/sweet_spots.html` | Remove `sweet_spots_prose` rendering block |
| `app/templates/base.html` | Bottom nav: Admin tab -> AI tab; top nav: remove conditional Admin link, add AI link |
| `app/templates/pages/config_hub.html` | Add admin card (conditional on `user.is_admin`) in catalog grid |
| `app/static/js/alpine-components/nav-bar.js` | Add `/ai` path -> `'ai'` tab; remove `/admin` -> `'admin'` mapping |
| `app/services/ai_service.py` | Add `research_coffee_predict_rating()` function |
| `app/services/ai_schemas.py` | Add `CoffeePredictSchema` |
| `tests/test_nav.py` | Update `test_admin_home_has_admin_link` (now checks /config, not /); add 3 new nav tests |
| `docker-compose.yml` | Switch `build: .` to `image: ghcr.io/...` for self-host distribution |

### UNCHANGED components (confirmed by code reading)

| Component | Why Unchanged |
|-----------|--------------|
| `app/services/analytics.py` | Pure read-only SQL; no changes for any v1.2 feature |
| `app/services/ai_service.py` (existing functions) | `regenerate`, `generate_equipment_rec`, `rank_pasted_coffees`, `suggest_recipe`, `alt_brewer_callout`, `get_latest_recommendation`, `is_stale`, `in_flight` — all unchanged |
| `app/services/scheduler.py` | Nightly AI bundle (coffee + sweet_spots rec_types only) unchanged |
| `app/models/brew_session.py` | Cafe quick-rate uses separate table |
| `app/models/ai_recommendation.py` | `"coffee_predict"` is just a new string value for `recommendation_type` (already text-as-enum) |
| `app/services/encryption.py` | Untouched |
| `app/services/credentials.py` | Untouched |
| `app/services/settings.py` | Untouched |
| `entrypoint.sh` | Already correct for auto-migrate-on-start |
| `Dockerfile` | Already correct for prebuilt image build including `build_id.txt` |
| `app/static/js/sw.js` | No `APP_SHELL` changes needed for nav IA change |
| `app/routers/pwa.py` | No changes needed |
| `app/routers/admin.py` | Admin functionality and routes unchanged; only nav entry point moves |
| `app/templates/admin_base.html` | Unchanged |
| All other existing fragment templates | Unchanged except `sweet_spots.html` and `home.html` |

---

## Data Flow: New AI Research + Predict

```
User fills form on GET /ai/research (coffee name + optional roaster)
    |
    v
POST /ai/research (CSRF-protected, require_user, 5-min throttle)
    |
    v
ai_service.research_coffee_predict_rating(user_id, coffee_name, roaster_name, db)
    |
    +-- reads (sync, no changes to these functions):
    |   analytics.get_preference_profile(db, user_id)
    |   analytics.get_top_coffees(db, user_id)
    |   analytics.get_flavor_descriptors(db, user_id)
    |
    +-- builds prompt: user profile + "what do you know about [coffee_name] by [roaster_name]?"
    |
    +-- async LLM call (Anthropic primary / OpenAI fallback, same pattern as generate_equipment_rec)
    |   Provider web-searches for the specific coffee + roaster
    |   Returns CoffeePredictSchema JSON via structure_output tool
    |
    +-- _write_recommendation_row(db, user_id, rec_type="coffee_predict", generated_by="manual_refresh", ...)
    |
    v
HTMX fragment: fragments/ai/predict_result.html
    - predicted rating + confidence + rationale
    - web sources used (URLs, autoescaped)
    - "Add to wishlist" button -> POST /ai/wishlist/add (existing, unchanged)
```

---

## Architectural Invariants: All Preserved by v1.2 Design

| Invariant | How v1.2 Preserves It |
|-----------|----------------------|
| Single uvicorn worker | No new process-level state added; `research_coffee_predict_rating` uses same module-level `_THROTTLE` dict; `_LOCKS` keyed by `(user_id, rec_type)` — adding `"coffee_predict"` is naturally isolated |
| Auto-migrate on start | `p12_cafe_logs` migration is additive; `alembic upgrade head` in `entrypoint.sh` applies it idempotently on first container start |
| Nonce-CSP | All new templates extend `base.html`; `RequestContextMiddleware` mints nonce per request; no inline scripts without nonce |
| Double-submit CSRF | All new POST handlers gated by `Depends(require_user)` and `Depends(get_session)`; `CSRFMiddleware` + `CSRFFormFieldShim` run globally |
| Signature-based regen | `research_coffee_predict_rating` writes `rec_type="coffee_predict"`, not `"coffee"`. The nightly scheduler iterates `rec_type="coffee"` only (verified in `scheduler.py`). Zero interference |
| Per-user scoping | `cafe_logs.user_id RESTRICT FK`; all new AI route handlers read `user_id` from `request.state.user.id` exclusively |
| Cost discipline | On-demand research uses 5-min throttle (same mechanism as `/ai/refresh`); nightly scheduler unchanged; cafe logs do not trigger AI calls |
| Analytics isolation | `cafe_logs` does not appear in any `analytics.py` function; analytics functions are unchanged |
| Mobile-first | New pages extend `base.html` with bottom/top nav; test all new pages at 375px |
| PWA offline shell | No new `APP_SHELL` entries needed; `nav-bar.js` is under `/static/` (SWR branch); `build_id.txt` cache-bust covers the updated file |
| MultiFernet encryption | AI keys continue to flow through `services/encryption.py`; new predict route uses `credentials_service.get_provider_credential` (same as existing AI routes) |

---

## Sources

All findings are HIGH confidence — grounded in direct reads of the actual codebase:

- `app/main.py` — middleware stack order, router registration sequence, lifespan hooks
- `app/routers/ai.py` — existing AI routes, handler patterns, throttle implementation
- `app/routers/home.py` — AI rec card polling endpoint (`card_ai_recommendation`), five-branch state machine, `card_sweet_spots` sweet_spots_prose loading
- `app/routers/config_hub.py` — handler simplicity (no DB queries, user in context)
- `app/models/brew_session.py` — FK structure (`RESTRICT` on `user_id` and `coffee_id`, `SET NULL` on optional refs), analytics join implications
- `app/models/ai_recommendation.py` — `recommendation_type` text-as-enum pattern, JSONB `response_json`, cost telemetry columns
- `app/models/wishlist_entry.py` — per-user per-source pattern for reference
- `app/services/ai_service.py` — `regenerate()` flow, `generate_equipment_rec()` on-demand pattern, `_write_recommendation_row`, `_LOCKS`, `_THROTTLE`, `_evict_stale_throttle`
- `app/services/analytics.py` — `compute_input_signature()`, all analytics functions, pure-SQL-no-side-effects guarantee
- `app/services/scheduler.py` — nightly job rec_type scope (`"coffee"` + `"sweet_spots"` only)
- `app/templates/base.html` — full nav structure (bottom + top), Alpine component loading order, `{% if request.state.user.is_admin %}` guards
- `app/templates/pages/config_hub.html` — catalog grid card pattern, existing Admin/export links
- `app/static/js/alpine-components/nav-bar.js` — active tab path matching logic
- `app/static/js/sw.js` — `APP_SHELL` array contents, cache strategy (SWR vs network-first)
- `app/routers/pwa.py` — `build_id.txt` hash derivation, `_BUILD_HASH` module var
- `entrypoint.sh` — `alembic upgrade head` + `--workers 1`
- `Dockerfile` — multi-stage build, `build_id.txt` timestamp write, stage-2 `COPY --from`
- `tests/test_nav.py` — existing test assertions verbatim (admin link checks, navBar component check)
- `.planning/PROJECT.md` — v1.2 scope, key decisions table, architectural invariants

---

*Architecture research for: Snobbery v1.2 feature integration into existing FastAPI app*
*Researched: 2026-05-25*
