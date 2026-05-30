# Phase 17: IA Restructure - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Reshape the app's information architecture so the bottom nav reflects daily-use priority — Admin moves off the nav into a Config-page entry, a new AI tab takes its slot, the home page sheds the AI surfaces and slims to action affordances + lightweight recency, and a new `/ai` page shell consolidates AI surfaces (full content lands in Phase 19). Eight locked requirements:

- **IA-01:** Admin reachable from a button on the Config page only; no longer on the bottom nav
- **IA-02:** New AI tab present in the bottom nav, opens a wired AI page shell (Phase 19 fills in research/predict)
- **IA-03:** AI surfaces (recommendation, equipment callout, sweet-spots prose) consolidate on the AI page and are removed from other pages
- **IA-04:** Home page simplified to primary action affordances + lightweight recency
- **IA-05:** Nav + asset changes reach installed PWAs without a manual cache clear
- **IA-06:** Home Top Coffees lists the top 5 rated coffees, no minimum-star / minimum-session floor
- **DIST-07:** Post-`/setup` flow guides a new admin to configure AI API keys (since Admin is no longer on the nav)
- **AIX-08:** Cold-start threshold met + no AI key configured → AI page shows a prominent Admin link, visually distinct from the not-enough-data empty state

Explicitly NOT in this phase:
- **Phase 19 AI content** — research-a-coffee, predict-rating, SSE streaming, the in-depth preference prose, charts, the equipment-rec content rewrite, the wishlist add-from-research flow, and the AIX-09..13 quality bar. Phase 17 wires the shell; Phase 19 ships the brain.
- **Mobile / visual polish to the "major-company bar"** (Phase 21 owns) — Phase 17 changes IA, not aesthetic. Reuse existing component shapes, don't redesign cards.
- **Guided Brew Mode polish** (Phase 20 owns)
- **Cafe quick-rate scope** (Phase 16 — already shipped; Phase 17's nav reshuffle must NOT touch the `/brew` page header's three-button row (Guided Brew + Log session + Quick rate) or the Sessions/Cafe tab toggle introduced in 16-D-09 / 16-D-06)
- **Catalog tab rename** — staying "Config" (decided here)
- **Renaming or moving existing `/ai/*` routes** — `/ai/paste-rank`, `/ai/wishlist`, `/ai/refresh`, `/ai/equipment`, `/ai/wishlist/*` keep their URLs (the new `/ai` page sits at the prefix root)

</domain>

<decisions>
## Implementation Decisions

### Nav slot composition + labels

- **D-01:** Bottom nav slot order becomes **Home / Log / AI / Config** (left → right). AI takes slot 3 (between Log and Config) so it sits alongside the daily-use tabs; Config is rightmost as a less-frequent destination. The Admin slot is fully removed (no admin-gated visibility on the bottom nav). Top nav (≥768px) link order in `base.html:91-98` mirrors the same order.
- **D-02:** AI tab label is **"AI"** (matches REQUIREMENTS / ROADMAP wording — "AI page", "AI tab"). Three-letter label keeps the bottom nav tight at 375px. Icon choice (sparkle / brain / robot) is the planner's call; pick from an existing inline-SVG set used elsewhere (no new asset dependency).
- **D-03:** AI tab is **always visible** to every authenticated user — not gated on cold-start or AI-key presence. The page itself renders the right state for cold-start (D-13) or no-key (D-14/D-15) cases; hiding the tab would hurt discovery and break IA-02's "present in the bottom nav" wording.
- **D-04:** **Keep the "Config" tab label.** With Admin moving under it the label is more accurate ("Config" covers Catalog + Admin entry + Display + Account + Data tools), and zero churn beats minor accuracy. The page's `<h1>` may shift from "Catalog" to "Config" so header and nav match — planner's call. Page route stays `/config`.
- **D-05:** `app/static/js/alpine-components/nav-bar.js` `activeTab` getter gains `if (p.startsWith('/ai')) return 'ai';` BEFORE the `/admin` branch (the `/admin` branch can be removed entirely since the bottom nav no longer has an Admin tab; the top-nav admin link continues to highlight via CSS state on its own `<a>`). Pathname routing order matters because `/admin` is unaffected by /ai.

### Home composition after AI leaves

- **D-06:** Home sections after Phase 17, in order:
  1. **Action button row** — Guided Brew + Log session + Quick rate (three equal `flex-1` buttons). Admin button removed (it lives under Config now per IA-01). Quick rate links to the same flow as the `/brew` page header's Quick rate button introduced in 16-D-09 — symmetric entry from both surfaces.
  2. **Recent brews** (eager, unchanged from today)
  3. **Top Coffees** (eager render — see D-08; IA-06 mandates top 5 with no minimum-star / minimum-session floor — see D-09). **Moved above "Not tried yet" 2026-05-29 at user request (reorder of items 3↔4); the "See AI recommendations →" breadcrumb moves up with this section.**
  4. **Not tried yet** (lazy-loaded — list length cap NOT changed in this phase; revisit in Phase 21)
  5. Small inline link at the bottom of the Top Coffees section: **"See AI recommendations →"** linking to `/ai`. Discovery breadcrumb for users who default to home; not a heavy banner.
  6. **Wishlist** stays on home as its current entry (link/card to `/ai/wishlist`). NOT removed despite IA-03's "AI surfaces consolidate" wording — Wishlist is "data the user added" not "AI-generated content"; reach from home is preserved. Wishlist is NOT also rendered on `/ai` (see D-12 reversal).
- **D-07:** Removed from home:
  - **`/home/cards/ai-recommendation`** hero — moves to `/ai`
  - **AI tools section** (Rank these for me + Analyze my setup) — moves to `/ai`
  - **Preference Profile** card — moves to `/ai`
  - **Top Flavor Descriptors** card — moves to `/ai`
  - **Sweet Spots** card — moves to `/ai`
  - **Cold-start meter** fragment (`fragments/home/_cold_start.html`) — moves to `/ai` (D-13)
  - **Admin button** in the home action row — removed entirely (admins reach Admin from Config per IA-01)
- **D-08:** Top Coffees on home renders **eagerly**, not lazy. Home becomes 3 eager sections (action row + Recent brews + Top Coffees) + 1 lazy (Not tried yet) + 1 lazy (Wishlist if kept lazy). Fewer staggered HTMX calls and faster first paint for the new simpler home.
- **D-09:** Top Coffees on home enforces **IA-06's no-floor rule**: top 5 coffees by rating, no `>= 3 sessions` or `>= 4.0 rating` floor. Updates `analytics.get_top_coffees` (or a new home-specific variant) to drop the existing floors when called from the home card path. The `/ai` page may keep a separate stricter "top coffees with confidence" view — planner's call.
- **D-10:** Home `<h1>` becomes a **personalized greeting**: `Good morning, {{ user.username }}` / `Good afternoon, …` / `Good evening, …`. Time-of-day derived server-side (UTC + the existing `TRUSTED_PROXY_IPS` posture — household lives in one TZ, no need for per-user TZ). Implementation tactic (template helper vs view-context value) is the planner's call. Falls back to "Home" if `user` is somehow missing (defensive, shouldn't happen given `require_user`).
- **D-11:** **Cold-start meter does NOT live on home anymore.** Below-gate users on home see the same composition as above-gate users (action row + Recent brews + Not tried + Top Coffees + AI link). The meter lives only on `/ai` (D-13). Keeps home invariant across gate states — simpler mental model.

### AI page shell scope

- **D-12:** URL is **`/ai`**. Existing `/ai/paste-rank`, `/ai/wishlist`, `/ai/refresh`, `/ai/equipment`, `/ai/wishlist/*` routes keep their URLs and templates (no renames). The new GET `/ai` is the page shell; sub-pages remain reachable at their existing URLs.
- **D-13:** Above-gate, no-key-issues users see on `/ai`:
  1. **AI "What to buy next" hero** — moved from home (`/home/cards/ai-recommendation` endpoint stays; the page just mounts it here instead of home)
  2. **Preference Profile**, **Top Flavor Descriptors**, **Sweet Spots** cards — moved from home (same `/home/cards/*` endpoints; planner can rename to `/ai/cards/*` if it tightens the IA, or keep the URLs and just mount them on the new page — Claude's discretion)
  3. **AI tools** section: "Rank these for me" → links to `/ai/paste-rank` (existing page, unchanged); "Analyze my setup" → POSTs `/ai/equipment` and renders inline result (existing route). Both stay as separate routes/templates per D-12.
  4. **"Research a coffee — coming in Phase 19"** stub card — visible placeholder that signals where the Phase 19 research/predict UI will land. Single-line copy + disabled state.
- **D-14:** Below-gate users on `/ai` see: **cold-start meter** (the existing `fragments/home/_cold_start.html` fragment, moved here unchanged or duplicated as a `fragments/ai/_cold_start.html` — planner's call). Plus a **one-line "why" explainer**: "AI personalization activates after 3 sessions and 5 distinct flavor notes." Plus a **"Log a session →"** CTA linking to `/brew/new`. Gives below-gate users a clear next step rather than a dead meter.
- **D-15:** Above-gate, **no AI key configured** users (AIX-08) see a **distinct callout card**: different headline ("AI keys needed" vs the cold-start "AI personalization activates after…"), different icon, and a **primary "Go to Admin" button** (not just a link). Visually different enough that the two states can't be confused at a glance. Same container size as the cold-start card so layout doesn't jump.
- **D-16:** Above-gate, no AI key, **non-admin** users see a different empty: copy reads **"AI is not set up. Ask the household admin to configure an API key."** — no Admin link (they'd 403 on `/admin`), no "Notify admin" button (no notification system exists v1). Names the social next step honestly. Admin-aware copy is `is_admin`-gated in the template like the existing admin entries.

### Admin entry + key-setup prompts

- **D-17:** Admin entry on `/config` is a **dedicated section below the catalog grid**, before the mobile sign-out block (see `app/templates/pages/config_hub.html:54-97`). Section is `is_admin`-gated, visible to both mobile and desktop (the mobile sign-out block is `md:hidden` but the Admin entry should NOT be — admins on desktop reach Admin from here too). Section is a single linked tile/card consistent with the catalog grid card shape; one Admin destination, links to `/admin`.
- **D-18:** Admin tab on the top nav (`app/templates/base.html:95-97`) stays — IA-01 says "no longer on the bottom nav"; the top horizontal nav at ≥768px keeps the existing admin link for desktop convenience. (Reads of the SC don't require dropping it from the top nav; if user wants it gone too, this is a one-line edit.)
- **D-19 (DIST-07):** Post-`/setup` admin sees a **persistent in-page banner** on Home AND `/ai` until at least one AI API key is saved. Copy: "Welcome — add your AI API key in Admin to enable recommendations." Includes a "Go to Admin" button. Banner is admin-gated (non-admins never see it). Implementation: check `app_settings` / `api_credentials` for any saved key on the request; render the banner template fragment conditionally. Banner is **session-dismissable** (a small × that hides for the session) but reappears on next visit until a key exists — gentle nudge, not a forced wizard, but also not skippable forever.
- **D-20 (AIX-08):** Same "no-key" state on `/ai` is covered by D-15/D-16 above. The DIST-07 banner and the AIX-08 callout coexist for admins (banner at top, callout in place of the AI hero) — they reinforce, don't conflict. For non-admins the banner is silent and only the D-16 callout renders.
- **D-21:** **Existing `/setup` redirect to `/` (line 209 in `app/routers/auth.py`) is NOT changed.** No interstitial wizard, no `/setup/keys` route. The post-setup nudge is the banner (D-19) — a banner is more recoverable than a forced step (user can read it, decide they'll do it later, and the app still works for non-AI features).

### Claude's Discretion (planner picks)

- **AI tab icon** — choose from the existing inline-SVG set in `base.html`; sparkle/star/brain shape, monochrome stroke, matches the other 24×24 `stroke-currentColor` tab icons. No new image asset.
- **AI page card layout** — start by copying the home card layout (`rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800`); Phase 21 mobile rework will polish.
- **Endpoint renames** — whether `/home/cards/preference-profile`, `/home/cards/flavor-descriptors`, `/home/cards/sweet-spots`, `/home/cards/ai-recommendation` rename to `/ai/cards/*` or keep their URLs. Either works; pick what minimizes churn and keeps the SW cache busting clean.
- **Cold-start fragment factoring** — whether `fragments/home/_cold_start.html` moves to `fragments/ai/_cold_start.html` or both home and AI share one `fragments/_cold_start.html` (likely the latter — though home no longer renders the meter per D-11, so it's effectively `fragments/ai/_cold_start.html`).
- **DIST-07 banner template location** — `fragments/ai_key_setup_banner.html` or `fragments/admin/key_setup_banner.html`. Include from `home.html` and `pages/ai.html`.
- **Time-of-day greeting boundaries** — pick reasonable cutoffs (e.g., 5am–12pm "morning", 12pm–5pm "afternoon", 5pm–5am "evening"). Don't over-engineer.
- **Whether the Admin entry on `/config` shows badge text** ("Admin only", "household admin") — planner's call; the `is_admin` gate already hides it from non-admins, so the badge is redundant.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 17: IA Restructure" — goal + 6 success criteria + dependency on Phase 15
- `.planning/REQUIREMENTS.md` § "Information Architecture (IA)" — IA-01..IA-06 wording; § "Self-Host Distribution (DIST)" → DIST-07; § "AI Page & Research/Predict (AIX)" → AIX-08 — precise requirement wording
- `.planning/PROJECT.md` § "Active" — v1.2 milestone scope and the IA restructuring line item; § "Current Milestone" — the AI-page consolidation framing
- `.planning/STATE.md` § "Current Position" — Phase 16 status (gaps_pending on CAFE-02 autocomplete bug); confirm Phase 16 is closed before Phase 17 starts (Phase 16's `/brew` header buttons + Cafe tab must already be live to symmetrize with home's action row)
- `.planning/phases/15-v1-1-debt-cleanup/15-CONTEXT.md` — explicitly defers IA changes to Phase 17 (D-09); also locks the persistent-nav contract Phase 17 reshapes
- `.planning/phases/15.1-catalog-session-polish/15.1-CONTEXT.md` — D-21 dual-Edit-button pattern (mobile inline + desktop mount) — informs how new AI-page interactive surfaces handle mobile/desktop split if needed
- `.planning/phases/16-cafe-quick-rate/16-CONTEXT.md` — D-09 "Quick rate" button on `/brew` header (the entry point home's action row mirrors); D-15 cold-start arithmetic (`brew+cafe >= 3 AND distinct flavor across both >= 5`); D-13 cafe data feeds preference derivation (so the AI page's Preference Profile already reflects cafe data on arrival); D-06 Sessions/Cafe tab toggle (must survive Phase 17 nav reshuffle untouched per Phase 16 D-09 wording)

### IA-01..06 + DIST-07 + AIX-08 — code surfaces this phase modifies

**Existing files that MUST be modified:**
- `app/templates/base.html` — bottom nav (lines 244-291): remove Admin tab, add AI tab between Log and Config (D-01). Top nav (lines 91-98): mirror the same link order (D-01). Optional: remove the desktop Admin link too if D-18 flips (planner confirms with user).
- `app/templates/pages/home.html` — full rewrite of section composition per D-06/D-07/D-08/D-09/D-10/D-11. Replace AI hero, AI tools, Preference Profile, Flavor Descriptors, Sweet Spots, cold-start meter, Admin button with: personalized greeting (D-10), action row (Guided Brew + Log session + Quick rate), Recent brews (eager), Not tried yet (lazy), Top Coffees (eager, no floor per IA-06), "See AI recommendations →" link, Wishlist link/card. Add DIST-07 banner include (D-19).
- `app/templates/pages/config_hub.html` — add an `is_admin`-gated Admin entry section below the catalog grid (line ~53), before the mobile sign-out block (D-17). Section is NOT `md:hidden` (admins on desktop reach Admin from here too).
- `app/static/js/alpine-components/nav-bar.js` — add `/ai` branch to `activeTab` getter; remove the `/admin` branch (no admin tab to highlight on the bottom nav anymore) (D-05).
- `app/routers/home.py` — drop the AI hero / AI tools blocks from the home view context if any were view-level; if Top Coffees eager render needs a query change, call the no-floor variant of `analytics.get_top_coffees` (D-08/D-09). Wire the DIST-07 banner conditional into the home view context.
- `app/services/analytics.py` — `get_top_coffees` (line 47): add or call a no-floor variant for the home Top 5 (IA-06 / D-09). Existing floored variant may stay for other callers; planner reconciles.
- `app/templates/fragments/home/_cold_start.html` — move into the AI page surface (D-13/D-14). Add the "why" one-liner + "Log a session →" CTA.

**New files (planner creates):**
- `app/routers/ai_page.py` — new `GET /ai` page shell route (the existing `app/routers/ai.py` keeps `/ai/paste-rank`, `/ai/wishlist`, `/ai/refresh`, `/ai/equipment`; the new shell route may live in `ai.py` or a new module — planner's call)
- `app/templates/pages/ai.html` — new AI page template (D-12/D-13/D-14/D-15/D-16/D-20)
- `app/templates/fragments/ai/_no_key_admin_callout.html` — AIX-08 admin-facing distinct callout (D-15)
- `app/templates/fragments/ai/_no_key_non_admin_callout.html` — D-16 non-admin "ask admin" copy (or a single conditional template — planner's call)
- `app/templates/fragments/ai_key_setup_banner.html` — DIST-07 persistent banner (D-19)
- `app/templates/fragments/research_coming_soon.html` — D-13 stub card for Phase 19 surface
- `app/templates/fragments/admin_config_entry.html` — D-17 Admin entry section for the Config page (or inline in `config_hub.html` if small — planner's call)

**Pattern files to read before implementing:**
- `app/templates/base.html` — the existing tab-icon shape (24×24 inline SVG, `stroke="currentColor" stroke-width="2"`, `aria-hidden="true"`) — match for the AI tab icon
- `app/templates/pages/home.html` (current state) — the action-row pattern (`flex items-center gap-3` + `flex-1 inline-flex items-center justify-center rounded border border-espresso-300 dark:border-espresso-600 px-4 py-2 text-base font-semibold min-h-[44px]`) — home action row rebuild mirrors this
- `app/templates/pages/config_hub.html` (current state) — the catalog grid card shape (`flex items-center gap-3 rounded-xl border border-espresso-200 ... px-4 py-4 min-h-[44px]`) — Admin entry section can reuse it
- `app/services/analytics.py` module docstring — preference / floor / NULL-rating semantics that the no-floor Top Coffees variant must respect
- `app/templates/fragments/home/_cold_start.html` — the existing cold-start meter shape; preserves layout when moved to `/ai`
- `app/templates/admin_base.html` — the admin sub-nav (`System` / `Users` / `Credentials` / `Settings` / `Backups`) — admins land here after tapping the Admin entry from `/config`
- `app/routers/auth.py:209` — the existing `RedirectResponse(url="/", status_code=303)` post-setup redirect that D-21 does NOT change

### Architectural patterns to follow
- **CSP nonce invariant** — every new template snippet using `<script>` must carry `nonce="{{ csp_nonce(request) }}"`. Project memory `strict-csp-blocks-htmx-indicator` warns against relying on htmx auto-injected styles — define spinner / indicator styles in `tailwind.src.css` if introduced.
- **HTMX 2.x conventions** — kebab-case `hx-on:event`; no `hx-ws` / `hx-sse`; DELETE-as-POST-with-`_method` recommended (CLAUDE.md § 3.2). New AI page interactive surfaces follow these.
- **Tailwind v3 invariant** — `darkMode: 'selector'` + `.dark` selectors; never `@custom-variant` (project memory `tailwind-v3-not-v4`).
- **SW cache invariant** — `CACHE_NAME = 'snobbery-v__BUILD_HASH__'` (`app/static/js/sw.js:5`) and `/` is network-first (`sw.js:81-98`). IA-05 is satisfied by the existing build-hash cache key (project memory `c9-sw-cache-content-deterministic`) — any rebuild that changes `base.html` content bumps the hash. **Verification step required** during the phase: confirm an installed PWA picks up the new nav after a deploy without manual cache clear (specifically on John's iPhone PWA, which is the IA-05 acceptance environment).
- **CSRF + autoescape** — every state-changing form keeps the CSRF token + double-submit cookie pattern. No new endpoints skip it.
- **Mobile-first @ 375px hard rule** — bottom nav tested at 375px, the new AI tab label + icon must fit; the personalized greeting (D-10) must not break the action row's gap at 375px.

No external specs introduced during discussion — the decisions above are the contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Bottom nav tab pattern** (`app/templates/base.html:244-291`) — flex layout, `flex-1 min-h-[44px] min-w-[44px]`, `:class` Alpine binding off `activeTab`, 24×24 inline SVG icon + `text-xs` label. AI tab is a one-block copy with new label, icon, and `href`.
- **Top horizontal nav links** (`app/templates/base.html:91-98`) — semibold espresso-600 text, same simple `<a>` shape per link. Mirror the bottom-nav slot order at ≥768px.
- **Home action button shape** (`app/templates/pages/home.html:16-34`) — `flex items-center gap-3` parent + per-button `flex-1 inline-flex items-center justify-center rounded border border-espresso-300 dark:border-espresso-600 px-4 py-2 text-base font-semibold min-h-[44px]`. The Quick rate button on `/brew` (Phase 16 D-09) uses the same shape — home's three-button row stays visually consistent.
- **Config-page catalog card shape** (`app/templates/pages/config_hub.html:14-52`) — `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4` + per-card `flex items-center gap-3 rounded-xl border border-espresso-200 dark:border-espresso-700 bg-cream-100 dark:bg-espresso-900 px-4 py-4 min-h-[44px]`. Admin entry section (D-17) can reuse the same card shape under a new heading like "Administration".
- **Home card section shape** (`app/templates/pages/home.html:42-170`) — `rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800` with an `<h2 class="text-xl font-semibold mb-4">`. AI page cards copy this exactly so visual style is consistent.
- **Cold-start meter fragment** (`app/templates/fragments/home/_cold_start.html` — referenced from `home.html:64`) — already implements the progress meter. Moves to `/ai` per D-13/D-14; layout reused.
- **Sign-out CSRF POST form** (`app/templates/base.html:161-166`, `app/templates/pages/config_hub.html:59-65`) — unchanged by this phase; verify D-17 Admin section does not visually crowd the mobile sign-out block.
- **`activeTab` getter** (`app/static/js/alpine-components/nav-bar.js:19-33`) — pathname startsWith chain. AI branch added per D-05; admin branch removable.
- **AI hero endpoint** (`app/routers/home.py:229`) — `/home/cards/ai-recommendation` handler returns either the cold-start fragment, the rec fragment, or the "no key" fragment. Logic reusable verbatim from `/ai` page surface; either rename the URL or just mount the same fragment from the new template.
- **Admin top-nav link** (`app/templates/base.html:95-97`) — `{% if request.state.user.is_admin %}` gated; stays per D-18.

### Established Patterns

- **Tab routing via pathname startsWith** — established in `nav-bar.js`. New `/ai` branch follows the same convention. No new active-tab mechanism.
- **`request.state.user.is_admin` gating in templates** — established at `base.html:95-97`, `home.html:18-22`, `config_hub.html` (implicit via the admin admin-only access). DIST-07 banner (D-19), Admin entry on Config (D-17), and AIX-08 admin vs non-admin copy (D-15/D-16) all use the same gate.
- **Lazy-loaded HTMX cards** (`hx-get` + `hx-trigger="load delay:Xms"` + skeleton placeholder) — used for all home analytics cards. AI page cards that aren't immediately above-the-fold can use the same pattern with their own staggered delays.
- **Eager-render cards** — Recent brews on home is server-rendered via `{% include %}`. Top Coffees on home (D-08) shifts to this pattern.
- **Fragment include path naming** — `fragments/home/*.html` for home-specific fragments. AI page fragments go in `fragments/ai/*.html` (new directory, established here).
- **Service-worker stale-while-revalidate** — `/static/*` and shell assets are SWR; `/` (the home page HTML) is network-first (`sw.js:81-98`). IA-05 is satisfied by the build-hash cache name + the network-first `/` path; no SW changes needed (project memory `c9-sw-cache-content-deterministic`).
- **CSP nonce on all inline scripts** — `nonce="{{ csp_nonce(request) }}"` is universal. The AI page introduces no inline scripts beyond existing Alpine components.

### Integration Points

- **Bottom nav** (`base.html`) and **top nav** (`base.html`) — single source of truth for nav slot order. D-01 is a one-file edit (+ the nav-bar.js routing rule).
- **Home page** (`home.html` + `home.py` + `analytics.py` Top Coffees) — rewritten composition per D-06..D-11. The AI hero endpoint `/home/cards/ai-recommendation` either re-homes under `/ai` or stays at its URL but is mounted from `pages/ai.html` instead.
- **Config page** (`config_hub.html`) — Admin entry section appended (D-17). Sign-out + dark-toggle + data-tools blocks at the bottom remain unchanged.
- **AI page surface** — new `pages/ai.html` + new `ai_page.py` router (or new GET handler in `ai.py`). Mounts the existing `/home/cards/ai-recommendation`, `/home/cards/preference-profile`, `/home/cards/flavor-descriptors`, `/home/cards/sweet-spots`, `/ai/equipment` form fragments — endpoints don't have to move, just their consumers.
- **Cold-start gate semantics** (`analytics.get_cold_start_counts` line 378) — Phase 16 D-15 already updated the count arithmetic to `(brew + cafe)`; Phase 17 does NOT change this. The cold-start meter rendered on `/ai` (D-13/D-14) just reads the same dict.
- **`/setup` post-success redirect** (`auth.py:209`) — unchanged per D-21. DIST-07 nudge is delivered via banner, not a new route.
- **AI key presence check** — DIST-07 banner + AIX-08 callouts need a "does any user have an AI key configured?" or "does the app have any AI key?" check. The existing `/admin/credentials` route persists keys to `api_credentials`; planner reads from `app_settings` / `api_credentials` (whichever is the source of truth for "AI is configured") in the view context for `/` and `/ai`. Service layer call lives in `app/services/ai_service.py` or a small new helper.
- **Service worker** (`sw.js`) — no changes. The build-hash cache name + network-first `/` policy already satisfy IA-05; the only verification work is the on-device PWA cache-bust check (call out in plan as a manual step).
- **No scheduler / encryption / search / brew / cafe changes** — APScheduler signature regen is untouched; encryption is API-key-only; search is brew/coffee-scoped (unchanged); `/brew` page header (Phase 16 D-09) is explicitly untouched; cafe routes / Sessions tab toggle untouched.

</code_context>

<specifics>
## Specific Ideas

- **"AI" as the tab label, not "Insights" or "Coach"** (D-02) — matches REQUIREMENTS / ROADMAP wording so spec traceability stays clean. Short label fits at 375px without truncation.
- **AI sits in slot 3, between Log and Config** (D-01) — explicit ordering choice. Not slot 4 (rightmost). Reflects that AI is a primary destination alongside the daily-use tabs.
- **Personalized greeting on home — "Good morning, {{ user.username }}"** (D-10) — specific divergence from the original "Home" h1. Adds warmth without scope creep into a full home redesign; time-of-day boundary specifics are planner's call.
- **Top Coffees with no floor** (D-09) — explicit IA-06 carve-out. Today's `get_top_coffees` enforces a `>= 3 sessions / >= 4.0 rating` floor (or similar); the home variant drops this. Planner adds a no-floor variant or a `min_sessions=0, min_rating=0` parameter.
- **Wishlist on home only — NOT inlined on `/ai`** (D-06 / D-12 reversal) — explicit reconciliation: user wants Wishlist reachable from home (it's "data the user added", not AI-generated content), and explicitly NOT duplicated on `/ai`. The `/ai` page has the AI hero + AI tools + Preference Profile + Flavor Descriptors + Sweet Spots + Research-coming-soon stub.
- **"See AI recommendations →" link under Top Coffees** (D-06) — small text link, not a banner, not a CTA card. Discovery breadcrumb only.
- **Persistent in-page banner for DIST-07, NOT an interstitial wizard** (D-19/D-21) — explicit "no forced wizard" call. Session-dismissable, reappears on next visit until a key exists. Admin-gated.
- **AIX-08 distinct callout: different headline + different icon + primary button** (D-15) — the "distinct from not-enough-data" wording in AIX-08 is satisfied by all three visual axes, not just headline text.
- **Non-admin no-key copy names the social action** ("Ask the household admin to configure an API key") (D-16) — no dead Admin link, no fake "Notify admin" button. Honest scope.
- **Admin entry on `/config` is its own section below the catalog grid** (D-17) — not in the grid (semantic mismatch), not in the header (clutter). Symmetric with the existing `Export / Import sessions` link's positioning.
- **Keep `/admin` top-nav link** (D-18) — IA-01's "no longer on the bottom nav" wording is satisfied without removing the desktop top-nav link. If user later wants it gone too it's a one-line edit; flag at plan review.
- **No SW changes** — the build-hash cache name + network-first `/` policy already satisfy IA-05 (project memory `c9-sw-cache-content-deterministic`). The IA-05 verification is a manual on-device check (John's iPhone PWA), not a code change.

</specifics>

<deferred>
## Deferred Ideas

- **Cap on 'Not tried yet' length** — considered for Phase 17 (cap at 5 or 10) and rejected. Keep current behavior in this IA-focused phase; Phase 21 mobile rework revisits if mobile scroll length is uncomfortable.
- **Drop the home `<h1>` entirely** — considered as a minimalism option and rejected in favor of the personalized greeting (D-10). The greeting is the "purpose-built" upgrade; pure-removal can be revisited in Phase 21.
- **Banner above Recent brews when a fresh AI rec exists** — considered for the home → AI pointer and rejected (D-06 picks the small link instead). Adds an 'unseen rec' state to track. Defer to Phase 19 if the AI-page redesign warrants the extra signal.
- **Forced wizard for AI-key setup after `/setup` (interstitial `/setup/keys`)** — considered for DIST-07 and rejected (D-19/D-21). User wants a banner, not a forced funnel. Revisit only if data shows admins ignore the banner indefinitely.
- **Inline Wishlist as an expandable section on `/ai`** — considered during AI shell discussion and reversed (D-06 / D-12). Wishlist stays on home only.
- **'Notify admin' button on non-admin no-key state** — considered for D-16 and rejected (no notification system; misleading affordance).
- **Renaming the Config tab to "Catalog" or "Settings"** — considered (D-04) and rejected. "Config" is accurate now that Admin lives under it; zero churn beats minor wording change.
- **Hiding the AI tab when cold-start gate is closed or no key configured** — considered (D-03) and rejected. AI tab is always visible; discovery beats hiding.
- **Removing the `/admin` link from the top horizontal nav (≥768px) too** — considered (D-18) and deferred. IA-01 wording is satisfied without removing it; ask user at plan-review if they want it dropped.
- **AI page card / hero visual polish to "major-company bar"** — out of scope; Phase 21 owns mobile-first polish across all screens. Phase 17 reuses existing card shapes.
- **Renaming `/home/cards/*` endpoints to `/ai/cards/*`** — left to the planner as a Claude's discretion choice. Either works; pick what minimizes SW cache churn.
- **Charts / data viz on the AI page (VIZ-01)** — Phase 19 owns. Not in the shell.
- **AI research-a-coffee, predict-rating, SSE streaming, in-depth preference prose, equipment-rec rewrite, AIX-09..13 quality bar** — all Phase 19 scope, not Phase 17. The shell makes room; Phase 19 fills it.

None of the above are dropped — each is captured for the phase or future iteration that owns it.

</deferred>

---

*Phase: 17-ia-restructure*
*Context gathered: 2026-05-27*
