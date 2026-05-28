# Phase 17: IA Restructure - Research

**Researched:** 2026-05-27
**Domain:** FastAPI + HTMX 2.x + Jinja2 + Alpine.js IA restructure (nav reshape, page composition, new shell route, session-scoped banner, AI-key presence gating)
**Confidence:** HIGH (codebase verified for every code-touch claim; CONTEXT.md locks decisions; no library research needed beyond what STACK.md already pins)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Nav slot composition + labels**

- **D-01:** Bottom nav slot order becomes **Home / Log / AI / Config** (left → right). AI takes slot 3 (between Log and Config) so it sits alongside the daily-use tabs; Config is rightmost as a less-frequent destination. The Admin slot is fully removed (no admin-gated visibility on the bottom nav). Top nav (≥768px) link order in `base.html:91-98` mirrors the same order.
- **D-02:** AI tab label is **"AI"**. Three-letter label keeps the bottom nav tight at 375px. Icon choice (sparkle / brain / robot) is the planner's call; pick from an existing inline-SVG set used elsewhere (no new asset dependency).
- **D-03:** AI tab is **always visible** to every authenticated user — not gated on cold-start or AI-key presence.
- **D-04:** **Keep the "Config" tab label.** Page route stays `/config`. The page's `<h1>` may shift from "Catalog" to "Config" — planner's call.
- **D-05:** `app/static/js/alpine-components/nav-bar.js` `activeTab` getter gains `if (p.startsWith('/ai')) return 'ai';` BEFORE the `/admin` branch (the `/admin` branch can be removed entirely since the bottom nav no longer has an Admin tab).

**Home composition after AI leaves**

- **D-06:** Home sections in order: action button row (Guided Brew + Log session + Quick rate, no Admin) → Recent brews (eager) → Not tried yet (lazy) → Top Coffees (eager, no floor) → "See AI recommendations →" inline link → Wishlist link/card.
- **D-07:** Removed from home: `/home/cards/ai-recommendation` hero, AI tools section, Preference Profile, Top Flavor Descriptors, Sweet Spots, cold-start meter, Admin button.
- **D-08:** Top Coffees on home renders **eagerly**, not lazy.
- **D-09:** Top Coffees on home enforces IA-06's no-floor rule: top 5, no `>=3 sessions` or `>=4.0 rating` floor.
- **D-10:** Home `<h1>` becomes a **personalized greeting** ("Good morning, {{ user.username }}"). Time-of-day derived server-side. Falls back to "Home" if `user` is missing.
- **D-11:** Cold-start meter does NOT live on home anymore. Below-gate users on home see the same composition as above-gate users.

**AI page shell scope**

- **D-12:** URL is `/ai`. Existing `/ai/paste-rank`, `/ai/wishlist`, `/ai/refresh`, `/ai/equipment`, `/ai/wishlist/*` routes keep their URLs.
- **D-13:** Above-gate, no-key-issues users see on `/ai`: AI hero, Preference Profile, Top Flavor Descriptors, Sweet Spots, AI tools (Rank these / Analyze setup), Research-coming-in-Phase-19 stub.
- **D-14:** Below-gate users on `/ai` see: cold-start meter + "AI personalization activates after 3 sessions and 5 distinct flavor notes." + "Log a session →" CTA.
- **D-15:** Above-gate, no AI key, **admin** users see a distinct callout card: different headline, different icon, primary "Go to Admin" button. Same container size as cold-start card.
- **D-16:** Above-gate, no AI key, **non-admin** users see: "AI is not set up. Ask the household admin to configure an API key." — no Admin link, no notify button.

**Admin entry + key-setup prompts**

- **D-17:** Admin entry on `/config` is a dedicated section below the catalog grid, before the mobile sign-out block. `is_admin`-gated, visible to both mobile and desktop. Single linked tile/card consistent with the catalog grid card shape.
- **D-18:** Admin tab on the top nav (`base.html:95-97`) stays. IA-01's "no longer on the bottom nav" satisfied by removing the bottom-nav slot only.
- **D-19 (DIST-07):** Post-`/setup` admin sees a persistent in-page banner on Home AND `/ai` until at least one AI API key is saved. Admin-gated. **Session-dismissable** (small × hides for the session) but reappears on next visit until a key exists.
- **D-20 (AIX-08):** DIST-07 banner and AIX-08 callout coexist for admins (banner at top, callout in place of the AI hero). For non-admins the banner is silent.
- **D-21:** Existing `/setup` redirect to `/` (`auth.py:209`) is NOT changed. No `/setup/keys` route.

### Claude's Discretion

- AI tab icon — choose from existing inline-SVG set; sparkle/star/brain, monochrome stroke, 24×24 `stroke-currentColor`.
- AI page card layout — copy home card layout (`rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800`).
- Endpoint renames — whether `/home/cards/preference-profile`, `/home/cards/flavor-descriptors`, `/home/cards/sweet-spots`, `/home/cards/ai-recommendation` rename to `/ai/cards/*` or keep their URLs.
- Cold-start fragment factoring — `fragments/home/_cold_start.html` moves to `fragments/ai/_cold_start.html` or stays as a shared `fragments/_cold_start.html`.
- DIST-07 banner template location — `fragments/ai_key_setup_banner.html` or `fragments/admin/key_setup_banner.html`.
- Time-of-day greeting boundaries — e.g., 5am–12pm "morning", 12pm–5pm "afternoon", 5pm–5am "evening".
- Whether the Admin entry on `/config` shows badge text ("Admin only") — `is_admin` gate already hides from non-admins.

### Deferred Ideas (OUT OF SCOPE)

- Cap on "Not tried yet" length (Phase 21).
- Drop the home `<h1>` entirely (Phase 21).
- Banner above Recent brews when a fresh AI rec exists (Phase 19).
- Forced wizard / `/setup/keys` interstitial.
- Inline Wishlist on `/ai`.
- "Notify admin" button on non-admin no-key state.
- Renaming Config tab (locked: stays "Config").
- Hiding AI tab when cold-start gate is closed / no key configured.
- Removing the `/admin` link from the top horizontal nav too (deferred — ask at plan review).
- AI page visual polish to "major-company bar" (Phase 21).
- Charts / data viz on AI page (Phase 19, VIZ-01).
- AI research / predict / SSE / equipment rewrite (Phase 19, AIX-01..07/09..13).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IA-01 | Admin reachable from a button on the Config page only; no longer on the bottom nav | Bottom-nav slot in `base.html:279-289` removed; new `is_admin`-gated section added to `pages/config_hub.html` (D-17). Top-nav Admin link stays (D-18). |
| IA-02 | New AI tab in the bottom nav; opens a wired AI page shell | New slot added to `base.html:244-291` (insertion between Log and Config); new `GET /ai` route mounted (D-12); existing `/ai/*` routes unaffected. |
| IA-03 | AI surfaces consolidated on the AI page and removed from other pages | `home.html` strips AI hero, AI tools, Preference Profile, Flavor Descriptors, Sweet Spots (D-07); `pages/ai.html` mounts the same fragments (D-13). |
| IA-04 | Home page simplified to primary action affordances | New home composition per D-06: greeting → action row → Recent brews → Not tried yet → Top Coffees → AI link → Wishlist. |
| IA-05 | Nav + asset changes reach installed PWAs without manual cache clear | `sw.js:5` build-hash cache name + network-first `/` policy already satisfies this; on-device verification on John's iPhone PWA is the acceptance step. |
| IA-06 | Home Top Coffees lists top 5 with no minimum-star / minimum-session floor | New no-floor variant or parameter on `analytics.get_top_coffees` (D-09); existing `>=2 sessions` `HAVING` clause removed/disabled for the home call path. |
| DIST-07 | Post-`/setup` flow guides new admin to configure AI API keys | Persistent in-page banner on Home + `/ai` (D-19); admin-gated; session-dismissable; reappears next page-load until key saved. |
| AIX-08 | Cold-start met + no AI key → AI page shows prominent Admin link, distinct from "not enough data" state | Distinct callout card on `/ai` (D-15/D-16) — different headline, different icon, primary button (admin) / "ask admin" copy (non-admin). |
</phase_requirements>

## Summary

Phase 17 is a tightly-scoped IA reshuffle with eight requirements. Every locked decision in CONTEXT.md maps cleanly onto an existing pattern in the codebase — no new pattern needs to be invented. The work is:

1. **Nav reshape** — one block removed from `base.html` (Admin bottom-nav slot), one block added in its place (AI tab), one branch removed from `nav-bar.js` (`/admin`), one branch added (`/ai`). Top-nav link order mirrors the bottom (D-01/D-18).
2. **Home reduction** — `pages/home.html` loses six sections (AI hero, AI tools, Preference Profile, Flavor Descriptors, Sweet Spots, cold-start meter) and gains a personalized greeting + a "See AI recommendations →" link. The Admin button comes off the action row.
3. **New AI page** — `pages/ai.html` + `GET /ai` route (live alongside the existing `/ai/*` routes in `app/routers/ai.py`, not in a new module — see §Architecture Patterns). Mounts existing `/home/cards/*` fragments for above-gate users; renders the moved `_cold_start.html` for below-gate users; renders an admin / non-admin no-key callout when keys are missing.
4. **Config-page Admin entry** — appends a single `is_admin`-gated card section to `pages/config_hub.html` below the catalog grid, before the mobile sign-out block.
5. **DIST-07 banner** — single shared fragment included from both `home.html` and `pages/ai.html`; admin-gated; check "does any AI key exist?" in the view context; session-dismiss via Alpine + `sessionStorage` (no server cookie, no DB write).
6. **AIX-08 distinct callouts** — two small fragments (`_no_key_admin_callout.html` / `_no_key_non_admin_callout.html` — or one fragment with an `is_admin` branch); same container shape as the cold-start card to keep layout stable.

**Primary recommendation:** Land the nav + IA changes in a single small wave (one router change + one Alpine getter change + two template edits), then ship the AI page shell + DIST-07 banner + AIX-08 callouts as a second wave. Keep `/home/cards/*` URLs unchanged to minimize SW cache churn (D-Claude's-discretion); the AI page mounts the existing endpoints. The AI-key-presence check is **already implemented** — `credentials_service.get_provider_credential(db, "anthropic")` + `credentials_service.get_provider_credential(db, "openai")` is the pattern used by the existing AI hero fragment (`home.py:248-250`) and is the correct primitive for both DIST-07 and AIX-08.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Nav slot rendering (active-tab styling) | Frontend (Jinja templates + Alpine.js) | — | The active-tab signal is derived from `window.location.pathname` in `nav-bar.js` — no server data needed. |
| Bottom-nav slot composition | Frontend (Jinja `base.html`) | — | Single template owns nav slot order. `is_admin` gating is template-side via `request.state.user.is_admin`. |
| `/ai` page shell route | API (FastAPI router) | — | Lives in `app/routers/ai.py` (already imports `templates`, `require_user`, `credentials_service` — perfect home for the new `GET /ai` handler). |
| AI-key presence check (DIST-07 + AIX-08) | Service layer (`app.services.credentials.get_provider_credential`) | API (view context) | The existing service primitive returns `None` on any failure mode (no row / disabled / no ciphertext / decrypt fail). View handlers call it once for each provider and pass `ai_key_present: bool` into context. |
| Time-of-day greeting | API (view context value) | Frontend (template renders) | Server-side derivation per D-10. Pass `greeting: str` into the home view context — keeps the template `text_xs` simple and avoids client-side `Date` (CSP-clean, no Alpine state). |
| DIST-07 banner session-dismiss | Frontend (Alpine + `sessionStorage`) | — | "Session-dismissable, reappears next visit" maps exactly to `sessionStorage` — survives nav within the same tab, clears on tab close. No server-side dismissed-flag table, no cookie, no DB write. |
| Top Coffees no-floor query | Service layer (`analytics.get_top_coffees` variant) | API | New parameter / new function on the service module. Same SQL shape, drop the `HAVING func.count(...) >= 2` clause. |
| Cold-start meter | Frontend (existing fragment, moved) | API (existing `get_cold_start_counts`) | Pure relocation: same data, new page. |
| AIX-08 callout rendering | Frontend (Jinja fragment) | API (view context: `ai_key_present`, `is_admin`) | Branch in template on the same two booleans the existing `ai_rec_not_configured.html` already uses; no new service call. |
| SW cache invalidation for nav change | Build pipeline (Dockerfile Tailwind stage + `__BUILD_HASH__` substitution in `sw.js`) | — | Already content-deterministic per project memory `c9-sw-cache-content-deterministic`. Phase 17 needs no SW code change. |

## Standard Stack

**Confidence:** HIGH — every library named below is already pinned in `CLAUDE.md § "Pinned Stack"` and already imported by the files Phase 17 touches. No new library is required.

### Core (no change from project pin)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `>=0.136,<0.137` | Route registration for new `GET /ai` | Already the framework; `app/routers/ai.py` already a registered router |
| Jinja2 | `>=3.1.6,<4` | Template authoring for `pages/ai.html`, new fragments | Template engine; autoescape ON globally per `templates_setup.py` |
| HTMX | `2.0.10` | Lazy-load HX-GET on AI page cards (mounting `/home/cards/*` endpoints) | Already loaded in `base.html:62`; existing home cards use the same `hx-get` + `hx-trigger="load delay:Xms"` + skeleton pattern |
| Alpine.js (CSP build) | `@alpinejs/csp@3.15.12` | DIST-07 banner `x-data` for session-dismiss | Already loaded in `base.html:60`; string `x-data="bannerDismiss"` reference (CSP-build constraint, see Pitfall §C below) |
| Tailwind CSS | `v3.4.17` standalone CLI | Utility classes for new template surfaces | Project memory `tailwind-v3-not-v4` — `darkMode: 'selector'` + `.dark` selectors, NEVER `@custom-variant` |

### Supporting (no change from project pin)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLAlchemy 2.0 | `>=2.0.49,<2.1` | `analytics.get_top_coffees` no-floor variant | Drop the `.having(func.count(BrewSession.id) >= 2)` clause for the home call path |
| pydantic v2 | `>=2.13,<3.0` | None directly — Phase 17 doesn't add schemas | — |
| structlog | `>=25.5,<26` | If a new banner-dismiss or admin-entry-click event is added (it shouldn't be — household-scale audit posture is auth+admin only) | Skip — no new audit events for this phase |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New file `app/routers/ai_page.py` | Add `GET /ai` to existing `app/routers/ai.py` | **Recommended: extend `ai.py`.** The existing router already has `router = APIRouter(prefix="/ai")` (`ai.py:47`), already imports `require_user`, `templates`, `credentials_service`, `ai_service`. Adding one new `@router.get("", response_class=HTMLResponse)` handler at the top is a 30-line addition. A new module adds an import in `main.py`, a new `APIRouter()` instance, and duplicates the imports for no gain. **Rationale:** zero churn beats minor file-organization purity. |
| New `fragments/ai/_cold_start.html` | Rename `fragments/home/_cold_start.html` to `fragments/_cold_start.html` (shared) | **Recommended: move to `fragments/ai/_cold_start.html`.** Per D-11, home no longer renders the cold-start meter — only `/ai` does. A "shared" path is fictitious. Mark the move with a `git mv` so blame history survives. The fragment as it exists today reads `gate.sessions_needed`, `gate.notes_needed`, `gate.distinct_notes` — those keys are still in `get_cold_start_counts` return shape (`analytics.py:378`) and require no template change. |
| Add a `dismissed_banners` DB table for DIST-07 session-dismiss | `sessionStorage` via tiny Alpine component | **Recommended: `sessionStorage`.** Per D-19, "session-dismissable but reappears on next visit" — exactly the `sessionStorage` semantic (cleared on tab close, survives nav). A server-side dismissed-flag would require a migration, a CRUD endpoint, CSRF, and a per-page DB read for one boolean — disproportionate for an admin-nudge banner. |
| Keep `/home/cards/preference-profile`, `/home/cards/flavor-descriptors`, `/home/cards/sweet-spots`, `/home/cards/ai-recommendation` URLs | Rename to `/ai/cards/*` | **Recommended: keep URLs.** Renaming churns the SW cache (every cached fragment URL becomes a miss on next visit) and forces template + router edits in five files for purely cosmetic gain. The endpoints are HTMX targets — users don't see them. The `/home/cards/*` name is a historical artifact, not a contract. Cosmetic rename can ride a future "/ai/* canonical URL" cleanup. |
| Compute time-of-day greeting client-side via Alpine `x-text="..."` reading `new Date().getHours()` | Compute server-side, pass into view context as a string | **Recommended: server-side.** The CSP-build Alpine rejects expressions like `new Date().getHours() < 12 ? 'morning' : 'afternoon'` (no `new`, no constructor calls — `@alpinejs/csp` parses bare member access + arithmetic + concat + method-args only per `base.html:55-59`). Also: server-side is simpler, no FOUC, and aligns with D-10 "Time-of-day derived server-side". |

**Installation:** No new packages. All requirements satisfied by the existing `pyproject.toml` / `requirements.txt`.

**Version verification:** Skipped — Phase 17 introduces no new pinned library. Existing pins are documented in `CLAUDE.md § "Pinned Stack — Current Versions"` and were verified against PyPI in the original stack research.

## Architecture Patterns

### System Architecture Diagram

```
                     ┌──────────────────────────────────────────┐
                     │  User (browser, PWA, or mobile sheet)    │
                     └────────────────────┬─────────────────────┘
                                          │ GET /
                                          ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  app/routers/home.py — home_shell()                              │
       │   1. gate = analytics.get_cold_start_counts(db, user.id)         │
       │   2. recent_brews = analytics.get_recent_brews(...)              │
       │   3. unrated = analytics.get_unrated_coffees(...)                │
       │   4. NEW: top_coffees_no_floor = analytics.get_top_coffees(...,  │
       │           min_sessions=0)  (D-09 / IA-06)                        │
       │   5. NEW: ai_key_present = (anthropic OR openai credential set)  │
       │           — for DIST-07 banner conditional                       │
       │   6. NEW: greeting = derive_greeting_for_user(user, now)         │
       │           (D-10)                                                 │
       │   ↓ render pages/home.html                                       │
       └─────────────────────────────────────────────────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
            ▼                             ▼                             ▼
  ┌─────────────────────┐       ┌───────────────────┐         ┌─────────────────┐
  │ DIST-07 banner      │       │ Action row +      │         │ "See AI         │
  │ fragment            │       │ Recent brews +    │         │ recommendations │
  │ (admin + no-key)    │       │ Not tried yet +   │         │ →" link to /ai  │
  │                     │       │ Top Coffees       │         └─────────────────┘
  └─────────────────────┘       │ (eager, no floor) │
                                │ + Wishlist        │
                                └───────────────────┘

                                          │ GET /ai
                                          ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  app/routers/ai.py — NEW ai_page_shell()                         │
       │   1. gate = analytics.get_cold_start_counts(db, user.id)         │
       │   2. ai_key_present = (anthropic OR openai credential set)       │
       │   ↓ render pages/ai.html with branches:                          │
       │      branch A: not gate.gate_open       → cold-start meter +     │
       │                                            "why" + Log session   │
       │                                            CTA (D-14)            │
       │      branch B: gate_open + !ai_key      → AIX-08 callout (admin  │
       │                                            vs non-admin variant, │
       │                                            D-15/D-16)            │
       │      branch C: gate_open + ai_key       → AI hero (mount         │
       │                                            existing              │
       │                                            /home/cards/ai-       │
       │                                            recommendation) +     │
       │                                            Preference Profile +  │
       │                                            Top Flavor Descriptors│
       │                                            + Sweet Spots + AI    │
       │                                            tools + "Research a   │
       │                                            coffee — coming in    │
       │                                            Phase 19" stub (D-13) │
       │   DIST-07 banner included at the top for admins w/ no key.       │
       └─────────────────────────────────────────────────────────────────┘
```

**Reader's trace:** A returning admin user with the AI key not yet configured loads `/` — the view context computes `gate`, `top_coffees`, `ai_key_present=False`, `greeting="Good evening, john"`. The template renders the greeting + action row + recent brews + top coffees + wishlist link + the DIST-07 banner pinned at the top (since `is_admin=True` and `ai_key_present=False`). They tap "See AI recommendations →", landing on `/ai`. The shell handler checks gate (above gate) + key (still missing), renders the AIX-08 admin callout in the hero slot with a "Go to Admin" button. They tap the button, land on `/admin`, save a key. Next page load, banner gone, hero loads normally.

### Recommended Project Structure (additive)

```
app/
├── routers/
│   └── ai.py                    # MODIFIED — add `GET /ai` shell handler at top of file
├── templates/
│   ├── pages/
│   │   ├── home.html            # MODIFIED — full rewrite of section composition
│   │   ├── config_hub.html      # MODIFIED — append admin-entry section
│   │   └── ai.html              # NEW — AI page shell
│   └── fragments/
│       ├── ai/                  # NEW directory
│       │   ├── _cold_start.html               # MOVED from fragments/home/
│       │   ├── _no_key_admin_callout.html     # NEW (D-15)
│       │   ├── _no_key_non_admin_callout.html # NEW (D-16) — or one fragment with is_admin branch
│       │   └── _research_coming_soon.html     # NEW (D-13 stub)
│       └── ai_key_setup_banner.html  # NEW — DIST-07 banner (shared by home + /ai)
├── services/
│   └── analytics.py             # MODIFIED — add `min_sessions` parameter or new `get_top_coffees_no_floor()` for IA-06
└── static/
    └── js/
        └── alpine-components/
            ├── nav-bar.js       # MODIFIED — add /ai branch, remove /admin branch
            └── banner-dismiss.js # NEW — DIST-07 sessionStorage-backed dismiss
```

### Pattern 1: Add a route to an existing FastAPI APIRouter

**What:** Insert `GET /ai` as the first handler in `app/routers/ai.py`, immediately after the prefix declaration (line 47).
**When to use:** Adding a new endpoint to an existing prefix family.
**Example:**
```python
# Source: app/routers/ai.py (existing pattern, e.g. /ai/paste-rank at line 54)
@router.get("", response_class=HTMLResponse)  # mounts at exactly /ai (prefix is "/ai")
def get_ai_page(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the AI page shell (Phase 17, IA-02).

    Branches:
    - below gate              → cold-start fragment + "why" + Log session CTA (D-14)
    - above gate, no key      → AIX-08 callout (admin vs non-admin variant, D-15/D-16)
    - above gate, key present → AI hero + Preference Profile + Top Flavor + Sweet Spots
                                + AI tools + Research-coming-soon stub (D-13)
    """
    gate = analytics.get_cold_start_counts(db, user.id)
    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    ai_key_present = anthropic_cred is not None or openai_cred is not None
    return templates.TemplateResponse(
        request=request,
        name="pages/ai.html",
        context={
            "gate": gate,
            "ai_key_present": ai_key_present,
            "user": user,
        },
    )
```
**Anti-pattern caught:** Creating a new `app/routers/ai_page.py` module would duplicate imports already present in `ai.py` and require an extra `app.include_router(...)` call in `main.py`. Reject — extend in place.

### Pattern 2: AI-key-presence check (canonical primitive)

**What:** `credentials_service.get_provider_credential(db, provider)` returns `ProviderCredential | None`. `None` covers all four failure modes (no row, disabled, no ciphertext, decrypt fails). "AI is configured" === at least one provider returns non-`None`.
**When to use:** Any view that needs to gate UI on "does AI work right now?" — DIST-07 banner, AIX-08 callout, future Phase 19 surfaces.
**Example:**
```python
# Source: app/routers/home.py:248-250 (existing AI hero "not configured" check)
anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
openai_cred = credentials_service.get_provider_credential(db, "openai")
if anthropic_cred is None and openai_cred is None:
    # ... render "not configured" fragment
```
**Tactical note:** The check is two DB SELECTs per request. At household scale (1-3 users), this is free. A future optimization could cache a `boolean any_ai_key_set` in `app_settings`, but that's a Phase 19 concern when AI page traffic actually picks up. **Do not introduce caching in Phase 17.**

### Pattern 3: HTMX lazy-load card mount (mounting existing endpoints)

**What:** A `<div hx-get="/home/cards/X" hx-trigger="load delay:Yms" hx-swap="innerHTML">` with a skeleton placeholder inside. The AI page mounts the same endpoints home used to mount.
**When to use:** Any sub-card on `/ai` that maps to an existing `/home/cards/*` fragment endpoint.
**Example:**
```html
{# Source: app/templates/pages/home.html:120-131 (existing Top Coffees lazy mount) #}
<section aria-labelledby="ai-pref-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="ai-pref-heading" class="text-xl font-semibold mb-4">Preference Profile</h2>
  <div hx-get="/home/cards/preference-profile"
       hx-trigger="load delay:200ms"
       hx-swap="innerHTML">
    <div class="animate-pulse space-y-2">
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
    </div>
  </div>
</section>
```
**Recommended staggering on `/ai`:**
- AI hero: `load delay:100ms` (it was 600ms on home with five other cards ahead of it; on `/ai` the hero IS the first card, drop the delay)
- Preference Profile: `load delay:200ms`
- Top Flavor Descriptors: `load delay:300ms`
- Sweet Spots: `load delay:500ms`
- AI tools (links): eager — no `hx-get`
- Equipment "Analyze my setup" button: eager — POST on click only

### Pattern 4: Personalized greeting (server-side, view context)

**What:** Compute `greeting` in the view handler using Python's `datetime.datetime.now().hour` — pass into context. Template renders `<h1>{{ greeting }}</h1>` with autoescape protecting `user.username`.
**When to use:** D-10 — server-side time-of-day derivation. Household lives in one TZ; rely on the container's local TZ (set in `docker-compose.yml` as a future improvement, today defaults to UTC).
**Example:**
```python
# Source: NEW helper, lives in app/routers/home.py or a small app/utils/greeting.py module.
# Honest disclosure: the container TZ today is UTC unless docker-compose explicitly sets TZ.
# For the household in the US (per CLAUDE.md "Hatco" + Snobbery context), UTC is
# 5-6 hours ahead of Central Time. This means at 11pm local the server says 5am UTC
# = "Good morning". That's wrong.
#
# Recommendation: read the TZ from a new env var (`APP_TZ`, default "America/Chicago")
# via Settings, then `datetime.datetime.now(ZoneInfo(settings.APP_TZ))`. ZoneInfo is
# in the stdlib since 3.9 — no new dependency. This is a small Settings addition
# (one new field in app/config.py + one line in .env.example) but it's the right
# fix because the user-visible greeting hinges on it.
from datetime import datetime
from zoneinfo import ZoneInfo

def derive_greeting(username: str | None, now: datetime | None = None) -> str:
    if not username:
        return "Home"  # defensive fallback per D-10
    h = (now or datetime.now(ZoneInfo("America/Chicago"))).hour
    if 5 <= h < 12:
        part = "morning"
    elif 12 <= h < 17:
        part = "afternoon"
    else:
        part = "evening"
    return f"Good {part}, {username}"
```
**Tactical note:** Whether to introduce `APP_TZ` env var or hard-code `"America/Chicago"` (the John household) is the planner's call. CLAUDE.md "Adding a new env var" lists the four-step procedure. A hard-coded TZ string is acceptable v1; if/when distribution (Phase 18) lands, `APP_TZ` becomes mandatory.

### Pattern 5: Session-dismissable banner via Alpine + sessionStorage

**What:** Wrap the banner in an Alpine `x-data="bannerDismiss"` component that reads/writes a `sessionStorage` key. `x-show="!dismissed"` (declarative). Dismiss button calls `dismiss()`. CSP-clean — Alpine CSP build supports method calls.
**When to use:** DIST-07 banner D-19.
**Example:**
```javascript
// Source: NEW — app/static/js/alpine-components/banner-dismiss.js
// Mirrors the existing ios-banner.js component (base.html:48, /static/js/alpine-components/ios-banner.js)
// which uses the SAME sessionStorage-survives-nav / clear-on-tab-close pattern via localStorage.
//
// For DIST-07 the spec says "session-dismissable but reappears on next visit" —
// sessionStorage (not localStorage) is the right primitive because it clears on
// tab close, which matches the "reappears on next visit" wording.
document.addEventListener('alpine:init', () => {
  Alpine.data('bannerDismiss', () => ({
    dismissed: false,
    init() {
      this.dismissed = sessionStorage.getItem('snobbery:dist07-dismissed') === '1';
    },
    dismiss() {
      this.dismissed = true;
      sessionStorage.setItem('snobbery:dist07-dismissed', '1');
    },
  }));
});
```
```html
{# Source: NEW — app/templates/fragments/ai_key_setup_banner.html
   Loaded from base of home.html and pages/ai.html when is_admin AND not ai_key_present. #}
{% if request.state.user.is_admin and not ai_key_present %}
<div x-data="bannerDismiss"
     x-show="!dismissed"
     style="display: block"
     class="mx-auto max-w-6xl px-6 mt-4">
  <div class="flex items-start justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:bg-amber-900/20 dark:border-amber-700">
    <div class="flex-1">
      <p class="text-base font-semibold text-espresso-900 dark:text-cream-100">
        Welcome — add your AI API key in Admin to enable recommendations.
      </p>
      <a href="/admin/credentials"
         class="mt-2 inline-flex items-center rounded bg-espresso-700 px-3 py-1.5 text-sm font-semibold text-cream-50 hover:bg-espresso-800 min-h-[44px]">
        Go to Admin
      </a>
    </div>
    <button x-on:click="dismiss()"
            aria-label="Dismiss banner"
            class="flex items-center justify-center min-h-[44px] min-w-[44px] text-espresso-700 dark:text-cream-100">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>
  </div>
</div>
{% endif %}
```
**Anti-pattern caught:** A server-side dismissed-flag (DB or cookie) couples a UI presentation choice to the persistence layer. Reject.

### Anti-Patterns to Avoid

- **Embedding `new Date().getHours()` inside an Alpine `x-data` or `x-text` expression** — `@alpinejs/csp` rejects `new` and constructor calls; this silently breaks at runtime (the home page would render an empty greeting). Compute server-side.
- **Renaming `/home/cards/*` URLs to `/ai/cards/*`** — churns the SW cache (`fragments/home/*` URLs already cached) and forces template + router edits in five files for no user-visible gain. Keep URLs.
- **Putting the AIX-08 callout container at a different height than the cold-start card** — D-15 explicitly requires "same container size as the cold-start card so layout doesn't jump." Mirror padding + min-height.
- **Hiding the AI tab for non-admin or below-gate users** — D-03 locks "always visible". Tab visibility is a discoverability concern, not a permission concern.
- **Adding `hx-on:click="…"` directly on inline tab markup** — per project memory `tojson-attr-quoting-and-live-browser-repro` and `executors-skip-ruff-ci-gates-both`, HTMX 2.x `hx-on:click` IS supported but the project's CSP grep test (`tests/ci/test_no_unsafe_jinja.py`) bans it on pages templates. The bottom nav today uses Alpine `:class="activeTab === '…'"` (declarative) — keep that pattern.
- **Writing inline `<script>` without a CSP nonce** — every script in `base.html` already carries `nonce="{{ csp_nonce(request) }}"`. New scripts (banner-dismiss.js) are external files, so the nonce only needs to be on the `<script defer src="...">` tag if added. Best: register a new external file in `base.html` alongside the existing nav/account/banner scripts (lines 46-48).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AI-key presence check | Don't query `api_credentials` directly from a view handler | `credentials_service.get_provider_credential(db, provider)` | The service primitive already handles all four failure modes (no row, disabled, no ciphertext, decrypt fails). Bypassing it would re-implement the InvalidToken catch (T-03-T1) and likely log the ciphertext (security regression). |
| Banner dismiss persistence | Don't create a `user_dismissed_banners` DB table or cookie | `sessionStorage` + tiny Alpine component | "Session-dismissable, reappears next visit" maps exactly to `sessionStorage`. A DB table would require a migration, CSRF-protected dismiss endpoint, and a query per request. Disproportionate. |
| Cold-start gate computation | Don't write a new "is gate open?" helper | `analytics.get_cold_start_counts(db, user_id)` | Already returns `{sessions, distinct_notes, sessions_needed, notes_needed, gate_open}` (`analytics.py:378`) — Phase 16 D-15 already updated to count brews + cafes; Phase 17 just reads the dict. |
| Active-tab routing | Don't write JS that subscribes to navigation events | Existing `nav-bar.js` `activeTab` getter | The getter re-evaluates on every Alpine binding check; pathname-startsWith is the established pattern. Add `/ai` branch, remove `/admin` branch — five lines. |
| Eager Top Coffees no-floor variant | Don't write a parallel SQL function | Add `min_sessions: int = 2` parameter to existing `get_top_coffees`, call with `min_sessions=0` from home view | One function, one signature change. Existing callers (none today, since `card_top_coffees` in `home.py:133` calls without kwarg) keep working. |
| Service worker cache bust | Don't write SW upgrade hooks | Existing `__BUILD_HASH__` substitution in `sw.js:5` | `sw.js` cache name embeds the Docker build hash. Every image rebuild → new cache name → automatic purge on next user visit. Project memory `c9-sw-cache-content-deterministic` confirms this works for template/CSS/JS content changes. **No SW code change for Phase 17.** |
| Time-of-day greeting client-side | Don't use Alpine `new Date()` expressions | Server-side derivation, pass `greeting: str` into context | Alpine CSP build rejects `new`. Server-side is simpler and avoids FOUC. |

**Key insight:** Every "new" thing in Phase 17 has an existing primitive. The only genuine new code is: (1) the `GET /ai` handler body (mirrors `home_shell`), (2) the `pages/ai.html` template (mirrors `pages/home.html`), (3) the four new fragments (`_cold_start.html` moved, two no-key callouts, research-coming-soon stub, banner), and (4) the banner-dismiss Alpine component (~10 lines, mirrors `ios-banner.js`).

## Runtime State Inventory

> Phase 17 includes one rename-adjacent change: removing the `/admin` branch from `nav-bar.js` `activeTab` and adding `/ai`. The pathname-routing rules live in code, not in stored data; no grep audit beyond code search is required. Below is the full inventory for thoroughness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 17 changes UI surfaces and routes; no schema changes, no data renames. The existing `api_credentials` and `app_settings` rows are read but not migrated. | None |
| Live service config | None — no external services (n8n, Datadog, Tailscale, Cloudflare) reference Snobbery's internal route names. | None |
| OS-registered state | None — no Windows Task Scheduler / pm2 / systemd entries embed Snobbery route names. (Snobbery is Docker-only; the only OS-registered thing is the container, whose name is `coffee-snobbery` per `docker-compose.yml` — unchanged.) | None |
| Secrets and env vars | None unless the planner introduces `APP_TZ` for the time-of-day greeting. If added: add to `.env.example` with default `America/Chicago`, plumb via `app/config.py`. | Conditional — only if `APP_TZ` env var is introduced. Hard-coding the TZ string in `derive_greeting()` avoids this; pick at plan-time. |
| Build artifacts / installed packages | **Tailwind CSS rebuild required** — adding any new utility class not yet in the CSS bundle triggers a Tailwind rebuild (`tailwind.<hash>.css`). The cache filename is content-hashed; Dockerfile stage 1 produces it. Project memory `c9-sw-cache-content-deterministic` confirms this drives SW cache invalidation. **Service worker `sw.js:5` `__BUILD_HASH__` substitution** propagates automatically via `pwa_router._BUILD_HASH`. No manual SW edit needed. | Re-run `docker compose build coffee-snobbery` after Phase 17 changes to bake the new templates + CSS + SW hash into the image. |

**The canonical question** *(After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?)*: Nothing. Phase 17 is route-add + template-edit + Alpine-getter-edit. No string is renamed; one is added (`/ai` branch in `nav-bar.js`), one is removed (`/admin` branch). A full Docker rebuild bumps the SW cache hash; PWA users see the new nav on their next visit. IA-05's "no manual cache clear" requirement is satisfied by the existing build-hash design — confirm with the on-device check (see Validation Architecture below).

## Common Pitfalls

### Pitfall A: Alpine CSP build rejects `new` and constructor expressions

**What goes wrong:** A developer writes `x-text="new Date().getHours() < 12 ? 'morning' : 'afternoon'"` in `pages/home.html`. The template parses fine. Alpine boots, walks the DOM, hits the `x-text` expression, and silently rejects it (the CSP build returns an empty string for any expression containing `new` or a constructor call). The home page renders with an empty `<h1>`.
**Why it happens:** `base.html:55-59` documents that the CSP build "rewrote the CSP expression evaluator to support operators/arithmetic/concat/method-args" — but only for those primitives. Constructor invocation is still rejected.
**How to avoid:** Compute the greeting server-side. Pass `greeting: str` into the view context. The template renders `<h1>{{ greeting }}</h1>`. No JavaScript involved.
**Warning signs:** Empty greeting in the rendered HTML at the browser. Browser dev tools console may show no error (the CSP build fails silently in some cases).

### Pitfall B: `|tojson` filter inside double-quoted attributes

**What goes wrong:** A template writes `<div data-config="{{ some_dict | tojson }}">`. Jinja's `|tojson` doesn't escape `"` inside the JSON string — the attribute breaks at the first internal quote.
**Why it happens:** Documented in project memory `tojson-attr-quoting-and-live-browser-repro`. `|tojson` is safe in single-quoted attrs but not double-quoted.
**How to avoid:** Phase 17 has no obvious `|tojson` use case (no JSON config passing). But the AIX-08 callout or research-coming-soon stub *could* tempt a developer to pass a config dict — guard against this in code review. If JSON-in-attr is needed, use single quotes: `<div data-config='{{ some_dict | tojson }}'>`.
**Warning signs:** Template renders fine in pytest's TestClient, but the live browser DOM shows a truncated attribute.

### Pitfall C: Tailwind v3 darkMode selector vs v4 syntax

**What goes wrong:** A developer copies a v4 Tailwind snippet (`@custom-variant`, `darkMode: "class"`-less config) into the project. The class doesn't compile, `dark:` variants don't apply.
**Why it happens:** Project memory `tailwind-v3-not-v4` — Snobbery is on v3.4.17 with `darkMode: 'selector'` + `.dark` selectors. No `@custom-variant`. The `CLAUDE.md § Technology Stack` Tailwind v4 reference is informational about the upstream ecosystem, NOT a directive for this repo. The repo's actual `tailwind.config.js` and `tailwind.src.css` are v3.
**How to avoid:** When adding new dark-mode utility classes (e.g., for the AIX-08 callout's amber accent), use `dark:bg-amber-900/20 dark:border-amber-700` — verify the syntax compiles by running `docker compose build coffee-snobbery` and checking `app/static/css/tailwind.<hash>.css` for the expected rules.
**Warning signs:** Dark-mode variant doesn't apply in the rendered page.

### Pitfall D: SW cache bust skipped because no template content changed

**What goes wrong:** A developer edits `nav-bar.js` (a pure JS file) and rebuilds Docker. The PWA still shows the old nav.
**Why it happens:** Per project memory `c9-sw-cache-content-deterministic`, the `__BUILD_HASH__` is content-deterministic on template/CSS/JS content change. A JS-only edit to `nav-bar.js` SHOULD bump the hash (it's a tracked content file), but if the SW asset isn't being deployed because the rebuild produced an identical hash (unlikely but possible), the PWA could stick on the old script.
**How to avoid:** Phase 17 touches both `base.html` (template) and `nav-bar.js` (JS) — the hash WILL bump. The risk is purely if the planner introduces a separate "one-line tweak" sub-task that only touches a non-tracked file. Keep the IA-05 verification step (manual PWA check on John's iPhone) in the plan as a real device test, not just a pytest assertion.
**Warning signs:** John's PWA shows the old Admin tab after deploy.

### Pitfall E: Banner-dismiss state leaks across users on a shared device

**What goes wrong:** John uses the household tablet, dismisses the DIST-07 banner. Farrah picks up the tablet, signs in. Banner stays dismissed because `sessionStorage` is per-tab, not per-user.
**Why it happens:** `sessionStorage` clears on tab close, not on sign-out. Farrah's session in the same tab inherits John's `sessionStorage` state.
**How to avoid:** Two options. (1) Accept the leak — the banner is admin-gated, so only admin users see it; on a household-shared device both users are likely admin, and the dismiss is per-day-at-most-once anyway. (2) On sign-out, the existing `/logout` flow could broadcast a `sessionStorage.clear()` (would need a small inline script on `/login` re-render). **Recommendation: accept option 1.** The leak is a household-scale non-issue; CONTEXT.md's D-19 says "session-dismissable" — close + reopen the tab and it's back. Document the choice in the plan SUMMARY.
**Warning signs:** None obvious — the planner makes this trade-off explicit and ships.

### Pitfall F: AIX-08 callout container height drift breaks layout

**What goes wrong:** The "no AI key" callout renders at a different height than the cold-start meter. When a user crosses the cold-start gate (3rd brew session), the page reflows on next load — the hero slot jumps from one box height to another.
**Why it happens:** Different number of paragraphs, different padding.
**How to avoid:** D-15 explicitly requires "same container size as the cold-start card so layout doesn't jump." Add a `min-h-[14rem]` (or matching computed value) to both fragments. Test at 375px viewport before declaring done.
**Warning signs:** Layout reflow when a user transitions from below-gate to above-gate-no-key.

### Pitfall G: Executor loosens analytics function signature for missing fixtures

**What goes wrong:** An executor sub-agent runs the tests, sees that the new `min_sessions=0` parameter on `get_top_coffees` breaks a fixture that asserts `>=2 sessions`. Instead of updating the fixture, the executor reverts the parameter or adds a second function.
**Why it happens:** Project memory `executor-loosens-schema-for-bad-fixtures` — executors mis-resolve test breakage by adding unplanned schema/signature changes.
**How to avoid:** The plan's `files_modified` list must explicitly include `app/services/analytics.py` AND the test files that need updating. The validate-phase step diffs against the plan and flags surprise file additions.
**Warning signs:** A sudden new function in `analytics.py` or a reverted parameter signature in the executor's commits.

### Pitfall H: VALIDATION.md `-k` filters collect zero tests

**What goes wrong:** A plan's VALIDATION.md says `pytest -k test_ia_tab_present` but no test by that name exists. The validate-phase command collects 0 tests, exits 0, and the requirement is recorded as "verified" with zero actual checks.
**Why it happens:** Project memory `validation-md-vacuous-k-filters` — the planner writes `-k` filters speculatively; executors add tests with slightly different names; the filter no longer matches.
**How to avoid:** Every `-k` filter in the Validation Architecture section below names a specific function. After plan execution, re-run each filter with `--collect-only` and confirm `>=1 test` collected. The plan-checker pass should catch zero-collect filters as a hard gate.
**Warning signs:** `pytest -k ... --collect-only` reports `collected 0 items`.

## Code Examples

### Adding `/ai` to the `activeTab` getter

```javascript
// Source: NEW patch to app/static/js/alpine-components/nav-bar.js
// Replaces lines 22-31 of the existing getter.
get activeTab() {
  const p = window.location.pathname;
  if (p === '/' || p.startsWith('/home')) return 'home';
  if (p.startsWith('/brew')) return 'brew';
  // NEW (D-05): /ai branch BEFORE /admin (which is being removed)
  if (p.startsWith('/ai')) return 'ai';
  if (p.startsWith('/config') || p.startsWith('/coffees') ||
      p.startsWith('/equipment') || p.startsWith('/recipes') ||
      p.startsWith('/roasters') || p.startsWith('/flavor-notes')) return 'config';
  // REMOVED: if (p.startsWith('/admin')) return 'admin';
  // Rationale: bottom-nav admin tab is removed (IA-01); the top-nav /admin
  // link doesn't use activeTab (it's a plain <a> with hover styling, not
  // an Alpine-bound active-tab state).
  return '';
},
```

### Adding the AI bottom-nav slot in base.html

```html
{# Source: NEW — insert in app/templates/base.html between current "Log" tab
   (lines 261-268) and current "Config" tab (lines 270-278). #}
{# AI tab — always visible to authenticated users (D-03 / IA-02) #}
<a href="/ai"
   class="flex flex-col items-center justify-center gap-1 flex-1 min-h-[44px] min-w-[44px]"
   :class="activeTab === 'ai' ? 'text-espresso-700 dark:text-cream-100' : 'text-espresso-400 dark:text-espresso-400'">
  {# Sparkle icon — matches the 24x24 stroke-currentColor convention of the existing tab icons.
     Source: Heroicons "sparkles" outline (24x24, stroke-currentColor, stroke-width 2). #}
  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/>
  </svg>
  <span class="text-xs">AI</span>
</a>
{# Admin bottom-nav slot REMOVED (IA-01); top-nav Admin link at base.html:95-97 stays (D-18). #}
```

### Adding the no-floor parameter to `get_top_coffees`

```python
# Source: PATCH to app/services/analytics.py lines 48-74
def get_top_coffees(db: Session, user_id: int, *, min_sessions: int = 2) -> list[Row]:
    """Return <=5 coffees ranked by the user's avg rating.

    Args:
        min_sessions: Minimum rated-session count per coffee. Defaults to 2
            (the original floor for confidence). Pass ``min_sessions=0`` from
            the home view to drop the floor entirely per IA-06 / D-09.

    Excludes NULL ratings (Pitfall 1). Tie-broken avg_rating DESC, then
    session_count DESC. Cafe coffees not joined (D-14 in Phase 16).
    """
    stmt = (
        select(
            Coffee.id,
            Coffee.name,
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(Coffee.id, Coffee.name)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        .limit(5)
    )
    if min_sessions > 0:
        stmt = stmt.having(func.count(BrewSession.id) >= min_sessions)
    return db.execute(stmt).all()
```

### Adding the admin entry to config_hub.html

```html
{# Source: NEW — insert in app/templates/pages/config_hub.html between
   the catalog grid (closing </div> at line 52) and the mobile sign-out
   block (line 54). D-17: visible on BOTH mobile and desktop, gated on
   is_admin. Reuses the existing catalog-card shape (config_hub.html:14-21). #}
{% if request.state.user.is_admin %}
<div class="mt-8">
  <h2 class="text-xl font-semibold mb-4 text-espresso-900 dark:text-cream-100">Administration</h2>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    <a href="/admin"
       class="flex items-center gap-3 rounded-xl border border-espresso-200 dark:border-espresso-700 bg-cream-100 dark:bg-espresso-900 px-4 py-4 min-h-[44px] hover:bg-cream-200 dark:hover:bg-espresso-800 transition-colors">
      {# Shield icon — matches the 24x24 stroke-currentColor convention. Source: existing
         admin tab icon in base.html:284-286 (before removal). #}
      <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-espresso-700 dark:text-cream-100 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
      </svg>
      <span class="text-base font-semibold text-espresso-900 dark:text-cream-100">Admin</span>
    </a>
  </div>
</div>
{% endif %}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Home page = central AI dashboard | Home = action affordances + light recency; AI surfaces consolidate on `/ai` | Phase 17 (this phase) | Reduces home complexity; allows Phase 19 to add AI research / predict / SSE without home-page pressure |
| Admin reachable from bottom nav (Phase 11) | Admin from a single button on `/config` + top-nav link at ≥768px | Phase 17 | Reflects observed use frequency — Admin is configuration, not daily-use |
| Cold-start meter on home (Phase 6/11) | Cold-start meter only on `/ai` | Phase 17 | Home invariant across gate states; meter lives with the AI surfaces it enables |
| AI hero polls from home page (Phase 7) | AI hero polls from `/ai` page (same endpoint, new mount point) | Phase 17 | URL of the endpoint unchanged; only the page that mounts it changes |
| Top Coffees with `>=2 sessions` floor | Top Coffees on home with no floor (top 5 by rating); strict variant available for `/ai` | Phase 17 / IA-06 | More immediately-rewarding home for users with sparse rating history |
| Post-`/setup` redirect to `/` (no nudge) | Post-`/setup` redirect to `/` + persistent admin-gated banner until AI key saved | Phase 17 / DIST-07 | Discoverable but non-blocking — admin can use the app without keys |

**Deprecated/outdated:**
- The home `/home/cards/ai-recommendation` mount **on home** is deprecated. The URL stays (D-12 / discretion: keep URLs to minimize SW churn), but the home page no longer renders the slot — only `/ai` does. Plan execution must scrub the home template's `hx-get="/home/cards/ai-recommendation"` lines.
- The `/admin` bottom-nav tab is deprecated entirely. Plan execution removes the `<a href="/admin">` block at `base.html:280-289` and the `if (p.startsWith('/admin')) return 'admin';` line at `nav-bar.js:29`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The household lives in `America/Chicago` (Central US) and the container TZ default is acceptable as a hard-coded string in `derive_greeting()` for v1 | Pattern 4 | If the deploy environment changes TZ (e.g., a future operator in EU), the greeting will be wrong for several hours each day. Mitigation: introduce `APP_TZ` env var — small Settings addition. **Confirm at plan review.** |
| A2 | The Anthropic `sparkles` Heroicon SVG shape is acceptable to John as the AI tab icon | Code Examples §"Adding the AI bottom-nav slot" | If John has a strong preference for `brain` or `robot`, swap the path. Cosmetic, one-line edit. The codebase doesn't bundle an icon library — every existing tab icon is an inline Heroicon outline. |
| A3 | The DIST-07 banner can link directly to `/admin/credentials` (the credentials sub-page of Admin) rather than `/admin` (the admin home) | Pattern 5 | If `/admin/credentials` path is wrong, the link 404s. Verified during plan-phase: planner should grep `app/routers/admin.py` for the credentials route. Project's admin sub-nav per `admin_base.html` includes `System` / `Users` / `Credentials` / `Settings` / `Backups`, so `/admin/credentials` is almost certainly correct. **Verify in plan-phase.** |
| A4 | Banner `sessionStorage` key `snobbery:dist07-dismissed` does not conflict with any existing localStorage / sessionStorage keys | Pattern 5 | Conflict would resurrect a dismissed banner spuriously. The existing namespace uses `snobbery:theme` (dark toggle), `snobbery:ios-banner-dismissed` (iOS install banner). The DIST-07 key is distinct. |
| A5 | Removing the `/admin` line from `nav-bar.js` `activeTab` getter does NOT break the top-nav `/admin` link's hover state | D-05 / Code Examples §"Adding /ai to activeTab" | The top-nav admin link at `base.html:95-97` is a plain `<a>` with `hover:text-espresso-900` — no Alpine binding. Verified — the link does not read `activeTab`. |
| A6 | Phase 16's cafe-tab toggle on `/brew` (D-06 of Phase 16) and the three-button row (D-09 of Phase 16) are untouched by Phase 17's nav reshuffle | CONTEXT D-09 / Phase 16 reference | If a plan task accidentally edits `pages/sessions.html` (the brew page), it could disturb the Sessions/Cafe tab toggle. Plan execution must NOT touch `/brew` files. **Document explicitly in plan must_not_modify list.** |

**If this table is empty:** N/A — six assumptions remain that the planner/discuss-phase should confirm with John before execution.

## Open Questions (RESOLVED)

1. **Time-of-day TZ source**
   - What we know: D-10 says "household lives in one TZ, no need for per-user TZ." CLAUDE.md context implies US Central (Hatco + restaurant in WI/IL area).
   - What was unclear: Whether to introduce a new `APP_TZ` env var (clean, future-proof for Phase 18 distribution) or hard-code `"America/Chicago"` (simpler v1).
   - RESOLVED: Reuse existing `Settings.APP_TIMEZONE` (default "America/Chicago") at `app/config.py:55`; no new env var. Already consumed by APScheduler (Phase 8) — single source of truth. (Plan 17-02 Task 3 wires this.)

2. **Admin tab on the top horizontal nav (>=768px)**
   - What we know: D-18 keeps it. CONTEXT.md `<deferred>` flags "removing the `/admin` link from the top horizontal nav too" as deferred for plan-review confirmation.
   - What was unclear: Whether John actually wants the top-nav admin link removed.
   - RESOLVED: KEEP the top-nav Admin link per D-18 as currently encoded. Removal remains deferred for plan-review user confirmation — not in scope for Phase 17 execution.

3. **Endpoint rename `/home/cards/*` -> `/ai/cards/*`**
   - What we know: Claude's discretion per CONTEXT.md. Both options work.
   - What was unclear: Whether the planner should prioritize URL aesthetics (matches `/ai` namespace) or SW cache stability (keep URLs as-is).
   - RESOLVED: KEEP existing `/home/cards/*` URLs to minimize SW cache churn. Plan 17-04 mounts the existing endpoints from `pages/ai.html` at their current paths. Cosmetic rename can ride a future cleanup.

4. **AIX-08 admin callout link target**
   - What we know: A3 above — likely `/admin/credentials` (the AI key surface inside Admin).
   - What was unclear: Confirmed during plan-phase.
   - RESOLVED: `/admin/credentials` — verified during planning via grep of `app/routers/admin/credentials.py` (file exists) and `app/routers/admin/__init__.py:35` (`router = APIRouter(prefix="/admin")`).

5. **DIST-07 banner placement vertical position on `/ai`**
   - What we know: D-19 says "persistent in-page banner on Home AND `/ai`". D-20 says "banner at top, callout in place of the AI hero" for admins (banner + callout coexist).
   - What was unclear: Whether the banner sits ABOVE the page `<h1>` or BELOW it on `/ai`.
   - RESOLVED: Top of `<main>` (above `<h1>`), mirroring the iOS install banner placement pattern in `base.html:313-326`. Plans 17-02 (Home) and 17-04 (/ai) both place the `{% include "fragments/ai_key_setup_banner.html" %}` directive immediately inside the opening `<main>` tag, before the page `<header>` block.

## Environment Availability

> Phase 17 is a code/config-only IA reshuffle. No external dependencies introduced.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All routers / services | ✓ | 3.12 (locked) | — |
| FastAPI | New `GET /ai` route | ✓ | 0.136+ (locked) | — |
| SQLAlchemy 2.0 | `get_top_coffees` no-floor variant | ✓ | 2.0.49 (locked) | — |
| Jinja2 | New template / fragments | ✓ | 3.1.6 (locked) | — |
| HTMX 2.x | Lazy-load mount cards on `/ai` | ✓ | 2.0.10 (locked) | — |
| Alpine CSP build | Banner-dismiss component | ✓ | 3.15.12 (locked) | — |
| Tailwind v3 standalone CLI | New utility classes (amber accent for AIX-08 callout, etc.) | ✓ | 3.4.17 (locked) | — |
| Postgres 16 | Schema reads (no migrations in Phase 17) | ✓ | 16 (locked) | — |
| Docker Compose | Rebuild + restart for templates / static / SW bake | ✓ | Project standard | — |
| John's iPhone PWA | IA-05 on-device verification | ✓ (per project memory `safe-area-fix-unverified` resolved, indicates iPhone is the verification device) | — | A simulator-only check is NOT a substitute for the on-device verification; the IA-05 test gates Phase 17 close. |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 + pytest-asyncio + FastAPI TestClient (httpx) |
| Config file | `pyproject.toml` (per project convention) + `tests/conftest.py` (T-INFRA-1 mechanism: catalog TRUNCATE teardown + settings cache clear) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_nav.py tests/routers/test_home.py tests/routers/test_ai_router.py tests/services/test_analytics.py -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs` (the `-rs` flag surfaces skipped tests — project memory `tests-pass-by-skip-mask-green`) |
| Pytest install | `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` (pytest is NOT baked into the production image — per CLAUDE.md) |
| Live container test iteration | `docker compose cp tests/ coffee-snobbery:/app/tests/` then re-run pytest (file-level cp; project memory `docker-cp-into-container-nesting` warns against `cp dir/` which nests) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IA-01 (no Admin in bottom nav) | A request to `/` from an authenticated admin user does NOT contain `'href="/admin"'` inside the `<nav x-data="navBar">` bottom-nav block | unit (assert on rendered HTML) | `pytest tests/test_nav.py::test_admin_home_has_no_admin_bottom_nav_tab -x` | ❌ Wave 0 — extend `tests/test_nav.py` (file exists; existing tests assert opposite for top nav) |
| IA-01 (Admin reachable from /config) | A request to `/config` from an admin user contains `'href="/admin"'` inside the new admin-entry section | unit | `pytest tests/test_nav.py::test_admin_config_page_has_admin_entry -x` | ❌ Wave 0 |
| IA-01 (Admin entry hidden from non-admins) | A request to `/config` from a non-admin user does NOT contain `'href="/admin"'` | unit | `pytest tests/test_nav.py::test_non_admin_config_page_has_no_admin_entry -x` | ❌ Wave 0 |
| IA-02 (AI tab present) | A request to `/` from any authenticated user contains an `<a href="/ai">` inside the bottom-nav block | unit | `pytest tests/test_nav.py::test_home_has_ai_bottom_nav_tab -x` | ❌ Wave 0 |
| IA-02 (AI tab opens page shell) | `GET /ai` returns 200 for an authenticated user; 401 for anonymous | unit | `pytest tests/routers/test_ai_router.py::test_get_ai_page_returns_200 -x tests/routers/test_ai_router.py::test_get_ai_page_returns_401_for_anonymous -x` | ❌ Wave 0 — extend existing `tests/routers/test_ai_router.py` |
| IA-03 (AI surfaces removed from home) | A request to `/` does NOT contain `hx-get="/home/cards/preference-profile"`, `hx-get="/home/cards/flavor-descriptors"`, `hx-get="/home/cards/sweet-spots"`, or `hx-get="/home/cards/ai-recommendation"` | unit (template scan) | `pytest tests/routers/test_home.py::test_home_does_not_mount_ai_cards -x` | ❌ Wave 0 |
| IA-03 (AI surfaces present on /ai for above-gate user) | A request to `/ai` from an above-gate user with AI key configured contains all four hx-get mounts | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_mounts_ai_cards_above_gate -x` | ❌ Wave 0 |
| IA-04 (home simplification — eager Top Coffees) | A request to `/` for an above-gate user renders Top Coffees content (not skeleton) inline — no `hx-get` for top-coffees | unit | `pytest tests/routers/test_home.py::test_home_renders_top_coffees_eagerly -x` | ❌ Wave 0 |
| IA-04 (greeting present) | A request to `/` contains `"Good morning, "` or `"Good afternoon, "` or `"Good evening, "` followed by the username | unit | `pytest tests/routers/test_home.py::test_home_renders_personalized_greeting -x` | ❌ Wave 0 |
| IA-04 (Admin button removed from action row) | A request to `/` for an admin user does NOT contain an `<a href="/admin">` inside the home action row `<header>` | unit | `pytest tests/routers/test_home.py::test_home_action_row_has_no_admin_button -x` | ❌ Wave 0 |
| IA-04 (Quick rate in action row) | A request to `/` contains `<a href="/cafe-logs/new">` or equivalent in the home action row | unit | `pytest tests/routers/test_home.py::test_home_action_row_has_quick_rate -x` | ❌ Wave 0 |
| IA-04 (See AI recommendations link) | A request to `/` contains `<a href="/ai">` matching "See AI recommendations" copy near Top Coffees | unit | `pytest tests/routers/test_home.py::test_home_has_see_ai_link -x` | ❌ Wave 0 |
| IA-05 (PWA cache freshness) | After a build that changes `base.html`, the `__BUILD_HASH__` substitution in `sw.js` produces a NEW cache name; PWA visit shows new nav. The build-hash mechanism is itself unit-testable; on-device behavior is manual. | unit (mechanism) + **manual** (on-device) | `pytest tests/test_pwa.py -k build_hash -x` (existing) + manual on-device check on John's iPhone PWA (see Validation Architecture > Manual Steps) | ⚠️ Partial — mechanism test exists; on-device is human |
| IA-06 (Top Coffees no floor) | `get_top_coffees(db, user_id, min_sessions=0)` returns coffees with `session_count == 1` when only one rated session exists | unit | `pytest tests/services/test_analytics.py::test_get_top_coffees_no_floor_includes_single_session_coffees -x` | ❌ Wave 0 — extend `tests/services/test_analytics.py` |
| IA-06 (Top Coffees still capped at 5) | With 7 rated coffees, `get_top_coffees(..., min_sessions=0)` returns exactly 5 rows | unit | `pytest tests/services/test_analytics.py::test_get_top_coffees_no_floor_caps_at_5 -x` | ❌ Wave 0 |
| IA-06 (home uses no-floor variant) | A request to `/` for a user with 1 rated coffee (single session) shows that coffee in Top Coffees | unit (integration) | `pytest tests/routers/test_home.py::test_home_top_coffees_no_floor_integration -x` | ❌ Wave 0 |
| DIST-07 (banner present for admin with no key) | A request to `/` from an admin user with NO `api_credentials` set contains `id="dist07-banner"` or banner-marker class | unit | `pytest tests/routers/test_home.py::test_home_shows_dist07_banner_for_admin_with_no_key -x` | ❌ Wave 0 |
| DIST-07 (banner absent for admin with key) | A request to `/` from an admin user with at least one `api_credentials` row populated does NOT contain the banner | unit | `pytest tests/routers/test_home.py::test_home_hides_dist07_banner_when_key_present -x` | ❌ Wave 0 |
| DIST-07 (banner absent for non-admin) | A request to `/` from a non-admin user (regardless of key state) does NOT contain the banner | unit | `pytest tests/routers/test_home.py::test_home_hides_dist07_banner_for_non_admin -x` | ❌ Wave 0 |
| DIST-07 (banner also on /ai) | Same admin + no key user: `GET /ai` also contains the banner | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_shows_dist07_banner_for_admin_with_no_key -x` | ❌ Wave 0 |
| AIX-08 (admin no-key callout) | A request to `/ai` from an above-gate admin user with no key contains the "Go to Admin" button + admin callout marker | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_shows_admin_callout_above_gate_no_key -x` | ❌ Wave 0 |
| AIX-08 (non-admin no-key callout) | A request to `/ai` from an above-gate non-admin user with no key contains "Ask the household admin" copy and does NOT contain `<a href="/admin">` | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_shows_non_admin_callout_above_gate_no_key -x` | ❌ Wave 0 |
| AIX-08 (below-gate state ≠ no-key state) | A request to `/ai` from a below-gate user shows the cold-start meter, NOT the no-key callout, regardless of key state | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_below_gate_shows_cold_start_not_no_key -x` | ❌ Wave 0 |
| AIX-08 (above-gate + key works normally) | A request to `/ai` from an above-gate user WITH a key configured shows the AI hero mount, NOT the callout | unit | `pytest tests/routers/test_ai_router.py::test_ai_page_above_gate_with_key_shows_hero -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `docker compose exec coffee-snobbery python -m pytest tests/test_nav.py tests/routers/test_home.py tests/routers/test_ai_router.py tests/services/test_analytics.py -q -rs`
- **Per wave merge:** `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs` (full suite — see CLAUDE.md container test instructions; project memory `snobbery-test-gate-runtime` documents the 939+ pass baseline)
- **Phase gate:** Full suite green + manual on-device IA-05 verification before `/gsd-verify-work`. The Playwright responsive smoke (`tests/e2e/test_responsive_smoke.py`) should also pass at 375px — extend it if the home / `/ai` page rework breaks an existing assertion.

### Manual / On-Device Validation Steps

Some checks cannot be automated and must be performed by John:

**IA-05 — PWA picks up nav changes without manual cache clear:**

1. **Pre-deploy snapshot:** From John's iPhone, open the installed Snobbery PWA. Confirm the current bottom nav shows Home / Log / Config / Admin (the pre-Phase-17 state). Take a screenshot.
2. **Deploy:** From the VPS, run `git pull && docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`. Wait for the container to be healthy (`docker compose logs -f coffee-snobbery` shows the lifespan startup message).
3. **Re-visit:** On John's iPhone PWA (without explicitly closing the app, without "Clear site data", without re-installing), tap any tab to trigger a navigation. The bottom nav should update to Home / Log / AI / Config within one navigation cycle. If it takes a second navigation, that's still acceptable (the SW activate runs on the next fetch).
4. **Acceptance:** Bottom nav shows Home / Log / AI / Config; no manual cache clear was performed. Take a post-deploy screenshot.
5. **If fail:** PWA still shows old nav after 2 navigation cycles → check `caches.keys()` in browser DevTools (Settings → Advanced → Web Inspector); inspect `Application → Service Workers` to confirm the new SW activated. Project memory `sw-stale-cache-confounds-ui-verify` notes that "Clear site data" sometimes confuses verification — the IA-05 test is specifically *without* that step.

**IA-04 — Mobile 375px sanity:**

1. In Chrome DevTools or Safari Web Inspector, set viewport to 375×667.
2. Load `/`. Confirm: greeting renders single-line (no wrap that breaks layout), action row's three buttons fit horizontally (Guided Brew + Log session + Quick rate), no horizontal scroll, Top Coffees readable.
3. Load `/ai`. Confirm: page renders without horizontal scroll, AI cards stack vertically, AIX-08 callout (if applicable) doesn't overflow.
4. Load `/config`. Confirm: catalog grid + new Admin entry section render in a column (1-col on mobile), no horizontal scroll.

### Wave 0 Gaps

- [ ] **Test infrastructure:** `tests/test_nav.py` needs new test functions (existing file covers DEBT-03 nav presence; Phase 17 adds IA-01 / IA-02 / IA-04 nav assertions). Extend in place — do NOT create a new test file.
- [ ] **Test infrastructure:** `tests/routers/test_home.py` needs new test functions for IA-03 / IA-04 / IA-06 / DIST-07 assertions. Extend in place.
- [ ] **Test infrastructure:** `tests/routers/test_ai_router.py` needs new test functions for IA-02 / IA-03 / AIX-08 assertions on the new `GET /ai` route. Extend in place.
- [ ] **Test infrastructure:** `tests/services/test_analytics.py` needs new test functions for the `min_sessions` parameter on `get_top_coffees`. Extend in place.
- [ ] **Test fixtures:** A new fixture for "admin user with NO `api_credentials` configured" is needed for DIST-07 banner tests. The existing `seeded_admin_user` fixture (per `tests/test_nav.py:94`) likely does NOT seed credentials — verify in conftest.py during plan-phase.
- [ ] **Framework install:** `pytest pytest-asyncio respx` are NOT in the production image. Plan must include `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` before the first test run (this is documented in CLAUDE.md but executors miss it).
- [ ] **Manual step:** IA-05 on-device verification documented in plan as a phase-close gate.

## Project Constraints (from CLAUDE.md)

The following directives from CLAUDE.md MUST be honored by Phase 17 plans:

1. **Python 3.12** — stack invariant; no language version bump.
2. **FastAPI lifespan only** — `@app.on_event` is deprecated and removed in Starlette 1.0; the new `GET /ai` route uses regular `@router.get(...)`, no lifespan touched.
3. **SQLAlchemy 2.0 typed `Mapped[...]` columns** — Phase 17 doesn't add schemas, but the `analytics.get_top_coffees` modification stays on `select()` + `func.count()` (the existing pattern).
4. **HTMX 2.x kebab-case `hx-on:event`** — Phase 17's new templates carry the same HTMX 2.x conventions; no `hx-ws` / `hx-sse`; DELETE-as-POST with `_method` is unnecessary (no DELETE endpoints added).
5. **Tailwind v3, `darkMode: 'selector'`** — per project memory `tailwind-v3-not-v4`; new dark-mode utilities use `dark:` prefix.
6. **CSP nonce on every inline `<script>`** — Phase 17 introduces ONE new external script (`/static/js/alpine-components/banner-dismiss.js`). External scripts don't need a nonce on the file itself, but the `<script defer src="..." nonce="..">` tag in `base.html` adding the new component MUST carry the nonce just like the existing six Alpine component registrations (`base.html:32-51`).
7. **CSRF on every state-changing form** — DIST-07 banner has NO state-changing form (dismiss is client-side only). AIX-08 admin callout uses an `<a href>` link, not a form. No CSRF concerns.
8. **No new env vars without `.env.example` documentation** — IF `APP_TZ` is introduced, follow the four-step procedure: (1) add to `.env.example`, (2) add to `docker-compose.yml` environment, (3) load via `app/config.py` Settings, (4) document in README.
9. **No silent migrations / no schema drops** — Phase 17 has NO migrations. Plan must verify no `alembic revision` files are created.
10. **ruff format + ruff check before commit** — per project memory `executors-skip-ruff-ci-gates-both`, CI gates on BOTH. Plan must include explicit `ruff format` + `ruff check` step before the wave-close commit.
11. **Conventional commits** — `feat(17-01):`, `feat(17-02):`, etc. per recent commit history.
12. **Architectural invariants** — coffees/equipment/recipes shared across users (Phase 17 doesn't touch); no public registration (untouched); AI keys encrypted in DB (untouched; reads only); signature-based AI regen (untouched); mobile-first (verified at 375px); PWA (verified on John's iPhone); reverse-proxy aware (untouched); CSRF + security headers (universal — verified by template scan).
13. **`docs/snobbery-gsd-prompt.md` not modified** — Phase 17 doesn't touch the spec.

## Security Domain

> Phase 17 has no security-changing surface — no auth changes, no encryption changes, no new state-changing endpoints. The DIST-07 banner is read-only-on-server; the AIX-08 callout is a link. The new `GET /ai` route gates on `require_user` exactly like every other authenticated route. AIX-08 non-admin copy explicitly avoids a fake "Notify admin" affordance to keep the social contract honest.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (read-only of session state via `require_user`) | Existing `require_user` dependency |
| V3 Session Management | no (no session lifecycle change) | Existing table-backed session store |
| V4 Access Control | yes | `is_admin` template gates + `request.state.user.is_admin` on view context — same pattern as `base.html:95-97` and `pages/config_hub.html` |
| V5 Input Validation | no (no new form inputs) | — |
| V6 Cryptography | no (read-only of credential presence; never touches plaintext) | `credentials_service.get_provider_credential` — the established service-layer primitive |
| V7 Error Handling | yes | All view handlers swallow `None` from `get_provider_credential` gracefully (no stack traces leak) |
| V8 Data Protection | yes (banner dismiss state is in `sessionStorage`, not server-side) | `sessionStorage` is per-tab, ephemeral; no PII; no data leakage risk |
| V11 Business Logic | yes | DIST-07 admin-gating + AIX-08 admin vs non-admin branch are template-side; reinforced by `request.state.user.is_admin` (server) — defense-in-depth |
| V14 Configuration | partial | If `APP_TZ` is introduced, it joins the pydantic-settings `Settings` class — no `os.environ` direct read elsewhere |

### Known Threat Patterns for FastAPI + Jinja2 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via personalized greeting injection (`user.username` rendered in `<h1>`) | Tampering / Info Disclosure | Jinja2 autoescape ON globally (already verified by `tests/templates/test_autoescape.py`); username is plain text rendering, no `\|safe` |
| IDOR — non-admin sees admin banner / callout | Elevation of Privilege | Server-side `request.state.user.is_admin` check in view context AND template gates `{% if request.state.user.is_admin %}`; defense-in-depth |
| Open redirect via the banner's "Go to Admin" link | Tampering | Link is a static `<a href="/admin/credentials">` rendered by the template, not from user input — no redirect attack surface |
| Session-storage leak across users on shared device | Info Disclosure | Documented (Pitfall E); accepted v1; no PII in the dismissed-flag, only a `'1'` sentinel |
| CSP-nonce bypass via inline event handler on new banner | Tampering | Use `x-on:click="dismiss()"` (Alpine declarative), not inline `onclick` — same pattern as existing iOS banner (`base.html:319`) |

## Sources

### Primary (HIGH confidence) — verified via codebase reads
- `C:\Claude\Coffee-Snobbery\.planning\phases\17-ia-restructure\17-CONTEXT.md` — locked decisions
- `C:\Claude\Coffee-Snobbery\.planning\REQUIREMENTS.md` — precise IA-01..06 / DIST-07 / AIX-08 wording
- `C:\Claude\Coffee-Snobbery\.planning\STATE.md` — phase position
- `C:\Claude\Coffee-Snobbery\.planning\ROADMAP.md` — phase 17 goal + 6 success criteria
- `C:\Claude\Coffee-Snobbery\.planning\phases\15-v1-1-debt-cleanup\15-CONTEXT.md` — D-09 explicitly defers IA to Phase 17; nav-presence contract
- `C:\Claude\Coffee-Snobbery\.planning\phases\15.1-catalog-session-polish\15.1-CONTEXT.md` — D-21 dual-button pattern
- `C:\Claude\Coffee-Snobbery\.planning\phases\16-cafe-quick-rate\16-CONTEXT.md` — D-09 Quick rate button on /brew header (untouched); D-15 cold-start arithmetic (untouched)
- `C:\Claude\Coffee-Snobbery\app\templates\base.html` (lines 91-98, 244-291, 95-97) — top + bottom nav structure
- `C:\Claude\Coffee-Snobbery\app\templates\pages\home.html` (full file) — current home composition
- `C:\Claude\Coffee-Snobbery\app\templates\pages\config_hub.html` (full file) — Config page structure
- `C:\Claude\Coffee-Snobbery\app\static\js\alpine-components\nav-bar.js` (lines 19-33) — `activeTab` getter
- `C:\Claude\Coffee-Snobbery\app\routers\home.py` — `home_shell` view context pattern; `card_ai_recommendation` AI-key check pattern (lines 248-250)
- `C:\Claude\Coffee-Snobbery\app\routers\ai.py` — existing `/ai/*` router; the file to extend with `GET /ai`
- `C:\Claude\Coffee-Snobbery\app\services\analytics.py` (lines 47-74) — `get_top_coffees` current floor (`HAVING >= 2`); (line 378) `get_cold_start_counts` keys
- `C:\Claude\Coffee-Snobbery\app\services\ai_service.py` (lines 1-50) — module structure for SDK clients
- `C:\Claude\Coffee-Snobbery\app\services\credentials.py` — `get_provider_credential` canonical primitive; `ProviderCredential` shape; all four failure modes documented
- `C:\Claude\Coffee-Snobbery\app\models\api_credential.py` — `ApiCredential` schema; one row per provider; `is_enabled` + `key_ciphertext` columns
- `C:\Claude\Coffee-Snobbery\app\routers\auth.py` (line 209) — `RedirectResponse(url="/", status_code=303)` post-setup redirect (D-21 keeps this)
- `C:\Claude\Coffee-Snobbery\app\static\js\sw.js` (lines 5, 81-98) — `CACHE_NAME = 'snobbery-v__BUILD_HASH__'` + network-first `/` policy
- `C:\Claude\Coffee-Snobbery\app\templates\fragments\home\_cold_start.html` — existing cold-start meter (moves to /ai per D-13/D-14)
- `C:\Claude\Coffee-Snobbery\app\main.py` (lines 86-110, 257-281) — router registration pattern + existing `ai_router` mount
- `C:\Claude\Coffee-Snobbery\tests\test_nav.py` — existing nav presence tests (extend with Phase 17 assertions)
- `C:\Claude\Coffee-Snobbery\tests\routers\test_home.py` — existing home router tests
- `C:\Claude\Coffee-Snobbery\.planning\config.json` — `workflow.nyquist_validation: true` (Validation Architecture section required)
- `C:\Users\John\.claude\projects\C--Claude-Coffee-Snobbery\memory\MEMORY.md` — project memory: `tojson-attr-quoting`, `tailwind-v3-not-v4`, `c9-sw-cache-content-deterministic`, `strict-csp-blocks-htmx-indicator`, `executors-skip-ruff-ci-gates-both`, `validation-md-vacuous-k-filters`, `decision-coverage-gate-scans-musthaves`, `executor-loosens-schema-for-bad-fixtures`, `tests-pass-by-skip-mask-green`, `sw-stale-cache-confounds-ui-verify`, `docker-cp-into-container-nesting`, `snobbery-test-gate-runtime`, `Snobbery VPS uses NPM reverse proxy`

### Secondary (MEDIUM confidence) — referenced from CLAUDE.md / project doc
- `CLAUDE.md § "Pinned Stack — Current Versions"` — library pins (Python 3.12, FastAPI 0.136+, SQLA 2.0.49, HTMX 2.0.10, Alpine CSP 3.15.12, Tailwind v3.4.17)
- `CLAUDE.md § 3.2` — HTMX 2.x migration deltas (kebab-case, no hx-ws/hx-sse, DELETE conventions)
- `CLAUDE.md § Architectural invariants` — admin gate, AI key encryption, signature-based regen, mobile-first, CSRF, security headers

### Tertiary (LOW confidence) — none required
No Context7 / WebFetch / WebSearch calls were needed. Every recommendation traces to a concrete file in the codebase or a documented CLAUDE.md invariant. The phase is a pure IA reshuffle on an already-mature stack.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library pinned, every pattern already implemented
- Architecture: HIGH — `GET /ai` mirrors `home_shell`; banner mirrors `ios-banner`; no-floor query is a trivial parameter add
- Pitfalls: HIGH — project memory documents seven directly-applicable traps; CSP + Tailwind v3 + tojson + SW cache are all known
- Validation Architecture: HIGH — every requirement maps to a specific test command; only IA-05 has a manual on-device component (documented)
- Security: HIGH — no new attack surface; existing primitives reused; AIX-08 non-admin copy avoids the fake-affordance trap

**Research date:** 2026-05-27
**Valid until:** 2026-06-26 (30 days for stable stack; revisit if Phase 19 changes the AI page composition)

---
*Phase: 17-ia-restructure*
*Research complete: 2026-05-27*
