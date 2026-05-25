# Phase 11: PWA + Mobile Polish - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Make Snobbery installable, mobile-polished, branded, and ship Guided Brew Mode.
17 requirements: BREW-12, BREW-13, MOB-01..04, MOB-07..13, UX-01..04.

This phase delivers, concretely:
- A **persistent navigation frame** — bottom tab nav (<768px) / top nav (≥768px),
  user identity + sign-out (the app has had NO sign-out affordance since Phase 6
  retired the placeholder index — see memory `phase-11-owes-nav-and-signout`),
  absorbing the minimal Phase 10 search header.
- **PWA installability** — `manifest.json`, `/sw.js` (root scope), icons
  (192/512 + maskable + apple-touch), iOS install banner, dual theme-color.
- **Guided Brew Mode** (BREW-12/13) — the big net-new feature: full-screen
  recipe-driven timer with audio/haptic cues, wake lock + iOS fallback.
- **Mobile polish** — table→card collapse audit, full-screen modal sheets,
  44px tap targets, native-select audit, 375×667 / 390×844 verification.
- **Aesthetic + branding** — logo on every page, login hero, palette/dark-mode
  confirmation, snobbery-tone copy.

Out of scope (locked elsewhere / deferred):
- PWA offline **write** queue + background sync — v2 (PROJECT Out of Scope).
  v1 ships a cached read-only shell; offline writes show a clear error.
- Manual dark/light toggle — v1 is system-preference only (REQUIREMENTS v2).
- Playwright responsive smoke automation itself — that's TEST-06 in **Phase 12**;
  Phase 11 only manually verifies at 375/390 as it builds (MOB-13 acceptance).
- New per-user settings/preferences page — none exists in v1; GBM cue prefs live
  in localStorage instead.

</domain>

<decisions>
## Implementation Decisions

### Navigation frame (MOB-01, MOB-02; absorbs Phase 10 search header)

- **D-01: Four-tab bottom nav <768px / top horizontal nav ≥768px.** Tabs:
  **Home / Log / Config / Admin**. Admin tab+link hidden for non-admins
  (MOB-02). Bottom nav respects `env(safe-area-inset-bottom)` (iOS).
- **D-02: Absorb the Phase 10 search header into the nav frame.** The auth-gated
  search component in `base.html` (inline ≥768px, icon→full-screen sheet <768px)
  folds into the new nav. Keep it rendering only when `request.state.user` is set
  (still hidden on `/login`, `/setup`). The search component stays self-contained
  (Phase 10 D-01 designed it to relocate).
- **D-03: "Config" tab = catalog hub landing.** A hub screen linking the shared
  catalog: Coffees, Equipment, Recipes, Roasters, Flavor notes. On mobile, the
  user **account + sign-out** live at the bottom of this hub screen.
- **D-04: AI pages stay on Home.** Wishlist (`/wishlist`) and Paste-and-rank
  (`/paste-rank`) remain linked from the Home screen near the AI card (current
  Phase 7 wiring) — not promoted to nav tabs and not duplicated into Config.
- **D-05: Desktop identity + sign-out = account dropdown (top-right).** An Alpine
  CSP-build dropdown component shows the username and a **Sign out** action (room
  for future account links). Sign-out is a **CSRF-protected POST form button**
  hitting the existing `/logout` (NOT a plain link).
- **D-06: Log tab → sessions list (`/brew`) + sticky "+ Log brew".** History is
  primary; the create action is an always-visible sticky/prominent button. (Not
  a jump straight to `/brew/new`.)

### Guided Brew Mode (BREW-12, BREW-13)

- **D-07: Two entry points.** (a) The brew-log form, once a coffee + recipe are
  selected ("Brew with timer") — coffee is pre-set. (b) A recipe's detail page
  ("Start guided brew") — recipe only. **"Done brewing"** returns to the session
  form: form-entry prefills coffee+recipe, recipe-entry prefills recipe only
  (planner handles the two completion paths). GBM is driven by the recipe's
  `steps` JSONB (cumulative water + time offsets).
- **D-08: Auto-advance + manual skip.** Steps auto-advance when the step's time
  offset elapses (firing chime + vibration), AND a "Next step" tap lets the user
  jump early. (Not pure-auto, not manual-only.)
- **D-09: Cue config = persisted toggles + in-brew toggle.** Chime on/off +
  vibration on/off toggles on the GBM start screen, persisted per-device in
  **localStorage** (namespaced like the brew draft, e.g. `snobbery:gbm:cues`),
  PLUS a live mute/vibrate toggle visible during the brew.
- **D-10: Add `brew_time_seconds` (nullable int) to `brew_sessions`.** John
  signed off on this additive Phase-5-table deviation (per CLAUDE.md "ask first
  on schema"). GBM populates total elapsed brew time on "Done brewing"; the field
  is **user-editable** on the session form (also allows manual entry). Migration
  is additive + nullable → low risk; **Phase 6 analytics is NOT touched now**
  (display location + any future analytics use is planner/deferred — see
  Discretion).
- **D-11: Wake lock + iOS fallback (research flag).** Request `wakeLock` on
  start; **re-acquire on `visibilitychange` → visible**; show a visible "screen
  will stay on" indicator. iOS Safari has incomplete Wake Lock support →
  prototype the fallback (silent audio loop vs NoSleep.js) **on a real iPhone**
  before declaring done (carried research flag). All JS must be CSP-strict
  (Alpine CSP build, no eval, no inline `hx-on:`). GBM requires a recipe WITH
  steps — planner handles the no-steps case (disable launch / message).

### Branding, palette, install assets (UX-01..04, MOB-09, MOB-11)

- **D-12: Circular mascot badge = logo AND PWA icon.** Crop the mascot to a
  circular/squircle badge from `snobbery-login.jpg`'s circular composition; it
  reads cleanly on BOTH cream (light) and espresso (dark) surfaces. The **same
  badge is the PWA icon source** (consistency). Logo sits upper-left on every
  page **except login**.
- **D-13: Login = centered mascot hero + form below.** `snobbery-login.jpg`
  centered as a hero, login fields in a card directly beneath, whole page
  centered. Crisp (not stretched); careful at 375px.
- **D-14: Login page is ALWAYS dark** (espresso-950), regardless of system
  preference — a deliberate moody brand moment that blends the dark mascot art
  and sidesteps dark-art-on-cream mismatch. **Every other page stays
  theme-adaptive** via the existing `darkMode: media` tokens.
- **D-15: Pre-generate + check in derived assets.** A one-time Pillow script
  produces the circular badge, PWA icons (192/512 + maskable safe-zone),
  apple-touch-icon (180), and an optimized login hero; the small outputs are
  committed to `app/static/img/`. Source JPEGs (~300-360KB) stay as reference.
  No runtime or Docker-build-time generation. (Source images are far too heavy
  to ship as-is.)
- **D-16: Aesthetic largely shipped — confirm, don't rebuild.** Palette
  (cream/espresso), `darkMode: media` form/anchor tokens, dual `theme-color`
  metas, and the `Snobbery — {Page}` title format already exist
  (`tailwind.src.css` + `base.html`). UX-02 PWA strings are LOCKED:
  `name="Snobbery — Coffee Log"`, `short_name="Snobbery"`,
  `description="Self-hosted coffee log for households who take pour-over seriously"`.
  UX-03: desktop top nav shows the badge/wordmark, mobile shows the badge
  icon-only.
- **D-17: Snobbery-tone empty states (UX-04).** Lean in without gimmick, e.g.
  "No brews logged yet. The snobbery awaits." (consistent with Phase 10's
  "Nothing matches. The grounds are clean.").

### Mobile layout polish (MOB-03, MOB-04, MOB-07, MOB-08, MOB-13)

- **D-18: Home KEEPS lists-first order — no reorder.** Recent brews + Not-tried-yet
  stay on top; analytics/cold-start below. The Phase 6 deferred "cold-start meter
  to the top" item is resolved as **leave as shipped**.
- **D-19: Modals = full-screen sheet <768px / dialog ≥768px** (MOB-08). Sheet has
  a header + close X + sticky actions above the safe-area (mirrors the search
  sheet). Applies to the mini-modal (`#modal-mount`, inline create-new) and any
  future modals.
- **D-20: Bottom nav hides only in full-screen contexts.** Hide the bottom tab
  nav in Guided Brew Mode and the search sheet. On the brew form, sticky
  Save/Cancel (BREW-08) stack **directly above the persistent bottom nav**, above
  the iOS safe-area — nav stays available while editing.
- **D-21: Table→card collapse is verify-and-fix, not redesign** (MOB-03). The six
  list fragments (`session_list`, `coffee_list`, `recipe_list`, `equipment_list`,
  `flavor_note_list`, `roaster_list`) already carry dual `md:hidden`/`hidden md:`
  table+card patterns; admin pages use no `<table>`. Audit at 375px, fix gaps,
  ensure no horizontal scroll anywhere. Sweep 44px tap targets (MOB-04) across
  nav + interactive controls. Native `<select>` for short lists; searchable HTMX
  dropdown reserved for the long coffees list (MOB-07) — audit, fix gaps.

### Claude's Discretion (resolve with these defaults)

- **Service-worker cache strategy** — locked by ROADMAP success criterion #2:
  stale-while-revalidate the app shell (base.html + tailwind.css + JS modules +
  manifest + icons), bypass non-GET, network-first every other GET, cache name
  embeds the build hash, `/sw.js` served from root with `Service-Worker-Allowed: /`
  and NGINX `Cache-Control: no-cache` (PWA-3/7). Keep the cached shell tiny
  (PWA-4, iOS ITP). Planner/researcher implement.
- **iOS install banner** (PWA-1/MOB-11) — one-time educational "Tap [share] → Add
  to Home Screen", shown only on iOS Safari when NOT already standalone; dismissal
  persisted in localStorage. Planner finalizes copy + trigger.
- **`start_url: "/?source=pwa"` must return 200, never a redirect** (PWA-2) —
  verify the home route handles the query param without redirecting.
- **`brew_time_seconds` display location** (session detail/list) — planner's call;
  analytics use deferred (additive nullable; no Phase 6 change required now).
- **Active-tab highlighting, exact icon set, catalog-hub layout, GBM timer-screen
  layout, cancel-without-logging confirmation, wake-lock indicator copy** —
  planner's call; keep minimal and CSP-safe.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 11: PWA + Mobile Polish" — goal, the 5 success
  criteria, and Notes (PWA-1..7 pitfalls, MX-2/3/4, the iOS Wake-Lock research
  flag). Depends on Phase 6 + Phase 9.
- `.planning/REQUIREMENTS.md` — verbatim reqs: BREW-12, BREW-13, MOB-01..04,
  MOB-07..13, UX-01..04. (Note MOB-05/06 already Complete in Phase 5; TEST-06
  Playwright is Phase 12.)
- `.planning/PROJECT.md` §"Mobile / PWA", §"Aesthetic", §"Constraints"
  (mobile-first 375px hard rule; CSP nonce; HTMX 2.x; Tailwind standalone CLI;
  single uvicorn worker), §"Key Decisions" (HTMX 2.x; Tailwind CLI; AI polling
  not SSE; PWA offline-write queue deferred to v2).
- `.planning/STATE.md` — session continuity; the carried research flag list
  (Phase 11 iOS Wake Lock fallback).

### Prior phase context (decisions Phase 11 builds on / absorbs)
- `.planning/phases/10-global-search/10-CONTEXT.md` — **D-01** (the minimal
  auth-gated search header in `base.html` that Phase 11 absorbs into full nav;
  desktop dropdown overlay + mobile icon→full-screen sheet patterns; CSP-safe
  Alpine component idiom; `.htmx-indicator` in `tailwind.src.css`).
- `.planning/phases/09-admin/09-CONTEXT.md` — D-03 (minimal admin entry link;
  full global nav + sign-out explicitly deferred to Phase 11); admin section nav
  + `require_admin` gating (the Admin tab target, MOB-02).
- `.planning/phases/05-brew-sessions/05-CONTEXT.md` — `brew_sessions` shape +
  prefill logic (`resolve_prefill`, "Brew again"), sticky form actions (BREW-08),
  localStorage draft namespacing (`snobbery:draft:brew:<user_id>`) — the pattern
  GBM cue prefs mirror; the 16px input baseline.
- `.planning/phases/06-analytics-home-page/06-CONTEXT.md` — Home section order +
  cold-start block (`_cold_start.html`), the D-18 "keep lists-first" subject.

### Code in this repo (read before implementing)
- `app/templates/base.html` — the nav mount point (currently only the Phase 10
  search header + `#modal-mount`); head already has dual `theme-color` metas +
  `Snobbery — {page_title}` title + the Alpine-component load order before the
  `@alpinejs/csp` core. Login/setup extend this — nav must stay auth-gated.
- `app/templates/pages/login.html` — the always-dark hero layout (D-13/D-14).
- `app/templates/pages/home.html` — Home order (D-18), AI card + wishlist/paste-rank
  links (D-04), `request.state.user`/`is_admin` gating reference.
- `app/templates/pages/setup.html` — also extends base.html (keep nav hidden).
- `app/templates/fragments/{session,coffee,recipe,equipment,flavor_note,roaster}_list.html`
  + matching `*_row.html` — the existing dual table/card responsive pattern
  (D-21 audit target).
- `app/templates/pages/admin_*.html` — Admin tab targets; no `<table>` tags
  (verify card/grid layouts at 375px).
- `app/static/js/alpine-components/` — existing CSP components (`search-bar.js`,
  `mini-modal.js`, etc.); add the account-dropdown + GBM + nav components here,
  registered BEFORE the `@alpinejs/csp` core (per `base.html` load order +
  `docs/decisions/0001`).
- `app/static/js/htmx-listeners.js` — `htmx.config.allowEval=false` + CSRF header
  (the constraint all new JS runs under).
- `app/static/css/tailwind.src.css` — palette tokens, `darkMode: media`
  form/anchor rules, `.htmx-indicator` (strict-CSP); extend here for nav + GBM +
  always-dark login (no `custom.css` — MX-1 lock, do NOT create it).
- `app/models/brew_session.py` — add nullable `brew_time_seconds` (D-10).
- `app/models/recipe.py` — `steps` JSONB (cumulative water + time offsets) drives
  the GBM timer.
- `app/routers/auth.py` — existing `/logout` POST (D-05 sign-out target).
- `app/routers/{wishlist,ai}.py` + paste-rank route — Home link targets (D-04).
- `app/main.py` — router registration + static mount; PWA routes (`/manifest.json`,
  `/sw.js` at root with the right headers) register here.
- `app/static/img/snobbery-login.jpg` (badge + login hero source),
  `snobbery-side.jpg`, `snobbery.jpg` — brand assets (D-12/D-13/D-15).
- `entrypoint.sh` / `Dockerfile` — migration auto-run (the `brew_time_seconds`
  migration) + the Tailwind CLI build stage (asset-gen reference for D-15).

### Operational + spec
- `CLAUDE.md` §"Architectural invariants" (mobile-first 375px; PWA manifest/SW/
  install flow must not break; CSRF + security headers + CSP on every response;
  reverse-proxy aware), §"Stack invariants" (Jinja+HTMX+Tailwind CDN→CLI+Alpine,
  no npm), §"Things to never do silently" (don't drop/rename columns; don't
  disable CSRF/CSP).
- `docs/decisions/0001*` — the Alpine CSP-build / eval-free component decision all
  new JS must honor.

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- **Wake Lock API** + iOS Safari support gaps; NoSleep.js vs silent-audio-loop
  fallback (BREW-13 research flag — verify on real hardware).
- **PWA**: web app manifest fields, maskable icon safe-zone, service worker
  registration + scope (`Service-Worker-Allowed`), stale-while-revalidate.
- **Vibration API** + `AudioContext` (iOS autoplay/gesture-unlock caveats for the
  chime).
- **HTMX 2.0.x** + **Alpine.js 3.x CSP build** — nav/dropdown/GBM components.
- **Pillow** — circular crop + maskable padding + icon resize (D-15 script).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 10 search component** (`base.html` header + `search-bar.js`) — the
  full-screen-sheet pattern (open/close, Esc, backdrop, auto-focus) GBM and the
  mobile modal sheet reuse. Search folds INTO the new nav (D-02).
- **`mini-modal.js` + `#modal-mount`** — the modal substrate to upgrade to a
  full-screen sheet <768px (D-19).
- **Alpine CSP component pattern** — eval-free `Alpine.data()` factories loaded
  before the `@alpinejs/csp` core; new account-dropdown / nav / GBM components
  follow it.
- **localStorage namespacing** (`snobbery:draft:brew:<user_id>` from Phase 5) —
  the model for GBM cue prefs (D-09).
- **Dual table/card list fragments** (six `*_list.html` + `*_row.html`) — D-21
  collapse is mostly already implemented; audit + fix, don't redesign.
- **`request.state.user` / `is_admin` gating** (home.html) — the nav auth gate +
  Admin-tab hide (MOB-02).

### Established Patterns
- "Cross-cutting → middleware; feature surface → router; stateful logic →
  service." Nav is a `base.html` template change; PWA routes (`/manifest.json`,
  `/sw.js`) are tiny routes in `main.py`/a small router; GBM is a page + Alpine
  component + the brew form/recipe entry points.
- Strict nonce-CSP + Alpine CSP build (no eval, no inline `hx-on:`); HTMX 2.x;
  no `custom.css` (MX-1 lock — all CSS in `tailwind.src.css`).
- `Cache-Control: no-store` + `Vary: HX-Request` on HTMX fragments
  (`fragment_cache.py`) — applies to any new fragment routes.
- AI delivery via HTMX polling (no SSE) — unchanged.
- Single uvicorn worker — unchanged (no new background work in this phase).

### Integration Points
- `app/templates/base.html` — the nav frame replaces/absorbs the search header;
  logo badge upper-left; account dropdown (desktop) / account section in Config
  hub (mobile); bottom tab nav.
- `app/main.py` — register `/manifest.json` + `/sw.js` (root scope) + any GBM
  router; confirm `start_url` `/?source=pwa` returns 200 (no redirect).
- `app/models/brew_session.py` + a new Alembic migration — `brew_time_seconds`.
- `app/static/img/` — pre-generated badge + icons + optimized hero checked in.
- NGINX (README/docs) — `Cache-Control: no-cache` on `/sw.js` (PWA-7).

</code_context>

<specifics>
## Specific Ideas

- **Sign-out is overdue** — since Phase 6 retired the placeholder index, NO page
  has a sign-out or identity affordance (memory `phase-11-owes-nav-and-signout`).
  This nav frame is the fix. `/logout` POST already works.
- **Orphaned template** — `app/templates/pages/index.html` is now unused (only a
  stale `.pyc` referenced it); safe to delete during Phase 11 cleanup.
- **Test assertion to update** — `tests/test_phase02_smoke.py::test_cold_container_through_login`
  expects anon `GET /` → 401. If Phase 11 adds a friendly `/login` redirect for
  anonymous full-page requests, update that assertion (memory note).
- **Login is the brand moment** — always-dark, centered mascot hero (D-14/D-13).
- **The logo = the icon** — one circular badge serves both (D-12), so the install
  icon and in-app logo are visually identical.
- **GBM must respect tempo** — auto-advance with a manual skip (D-08); coffee
  people pour at their own pace.
- **Source brand JPEGs are heavy** (~300-360KB) — never ship them directly;
  pre-generate small derivatives (D-15).

</specifics>

<deferred>
## Deferred Ideas

- **PWA offline write queue + background sync** — v2 (PROJECT Out of Scope). v1
  ships a cached read-only shell; offline writes show a clear error.
- **Manual dark/light toggle** — v1 is system-preference only (REQUIREMENTS v2);
  this is why login is hard-coded dark rather than offering a switch.
- **`brew_time_seconds` in analytics** (e.g. avg brew time by recipe, brew-time
  sweet spots) — the column lands now (D-10) but Phase 6 analytics is untouched;
  surfacing it analytically is a future enhancement.
- **Per-user settings/preferences page** — none in v1; GBM cue prefs live in
  localStorage. If a real prefs surface emerges later, migrate them there.
- **Cold-start meter / analytics-first home reorder** — considered and explicitly
  declined for v1 (D-18, keep lists-first); revisit only if home ordering proves
  wrong in use.
- **Bottom-sheet (partial-height) modals** — considered for D-19; chose
  full-screen sheets to match the existing search sheet. Revisit if full-screen
  feels heavy for tiny create-new forms.

### Reviewed Todos (not folded)
- **"Inline add new coffee from the brew-form coffee select"** (STATE pending
  todo) — a brew-form/catalog UX enhancement (Phase 4/5 domain), not PWA/mobile
  chrome. Not in Phase 11 scope; left for a future catalog/brew touch-up.

</deferred>

---

*Phase: 11-PWA + Mobile Polish*
*Context gathered: 2026-05-22*
