# Phase 13: PWA UX Fixes - Context

**Gathered:** 2026-05-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Resolve the buildable iOS-PWA UAT findings from John's testing and ensure deployed
fixes actually reach the installed PWA. Post-launch polish on top of the v1 trunk
(Phases 11-12). **No schema, auth, AI, or deployment-topology changes.**

Ten concrete items (9 ROADMAP success criteria C1-C9 + one added during discussion, C10):

- **C1** iOS standalone header obscured by status bar (safe-area-inset-top).
- **C2** Create equipment/coffee renders a broken card (mode="row" `<tr>` in a non-table div).
- **C3** Equipment cards too tall at 375px (one field per line).
- **C4** Add a manual dark-mode toggle (move `darkMode: media` → `class`).
- **C5** Guided Brew not reachable from Home / Log; missing regression test.
- **C6** Guided-brew audio/haptic cue controls (`role="switch"`) confuse users.
- **C7** Brew form: ratio doesn't recalc on recipe prefill; rating stars wrap at 375px.
- **C8** Export/Import clutters the log view; move to a dedicated page.
- **C9** SW cache version doesn't bump per deploy → fixes invisible on installed PWAs.
- **C10** (added) Circular nav logo + PWA app icon are skewed; regenerate from new `hero.jpg`.

**Out of scope (locked / deferred elsewhere):**
- Sibling fixes already shipped this session via `/gsd-debug`: iOS bottom-nav float
  (commit `982c0e6`) and guided-brew dead-`<span>` (commit `eafc6e3`).
- The login hero art (`snobbery-login.jpg` / `snobbery-login-hero.jpg`) — stays as the
  D-13/D-14 brand moment; C10 only touches the badge + PWA icons.
- PWA offline-write queue (v2), per-user settings page (v1 uses localStorage).

</domain>

<decisions>
## Implementation Decisions

### Dark mode (C4)
- **D-01: 3-state Auto / Light / Dark, Auto is the default.** Auto = follow system
  (today's exact behavior), so existing users see no change; Light/Dark are explicit
  overrides. Move Tailwind from `darkMode: 'media'` to `darkMode: 'class'` (Tailwind v4
  CSS-config: the `dark:` variant must key off a `.dark` class on `<html>`, e.g.
  `@custom-variant dark`). Persist the choice in `localStorage` (namespaced, e.g.
  `snobbery:theme`). **No flash-of-wrong-theme:** a nonce'd, eval-free inline `<head>`
  script must set the `.dark`/light class from stored choice (or `matchMedia` when Auto)
  **before first paint**. The two existing hardcoded `@media (prefers-color-scheme: dark)`
  blocks in `tailwind.src.css` must also become class-driven so they don't fight the
  toggle when the user overrides to Light on a dark-system device (and vice-versa). All
  CSS stays in `tailwind.src.css` — MX-1 lock, do NOT create `custom.css`.
- **D-02: Login + setup stay ALWAYS dark, regardless of the toggle.** Preserve the
  Phase 11 D-14 brand moment (espresso-950). The toggle affects authenticated pages only.
- **Toggle placement:** on the config hub near the "Signed in as" / Sign out block
  (the requested location; same area as the D-06 export/import link below).

### Create-then-render card (C2)
- **D-03: Create returns the full list fragment, swapped into the list container** (not a
  single card). Root bug: the create route returns the `mode="row"` `<tr>` variant dropped
  into the non-table `#*-form-mount` div, so the card is malformed. Re-rendering the list
  region gives correct sort/filter order and handles the empty-state → first-item
  transition for free. Applies to **equipment and coffees** (the two C2 names).
- **D-04: The create form collapses/closes on success** (not clear-and-stay). Cleaner
  resting state; replaces the current `include_oob_form_clear` reset-in-place behavior.

### Guided Brew reach (C5)
- **D-05: Add a "Guided Brew" action on Home and Log that links to `/recipes`.** GBM
  requires a recipe-WITH-steps and neither Home nor Log has a recipe pre-selected, so the
  action routes to the recipe list, where each steps-bearing recipe already carries the
  now-fixed "Start guided brew" control (and no-steps recipes link to the editor per
  `eafc6e3`). Simplest, reuses existing screens, no new picker UI. **Plus the regression
  test** the criterion mandates: cover `recipe_row.html` enabled-vs-no-steps rendering
  (the coverage gap that let the dead-`<span>` bug ship — see
  `.planning/debug/resolved/guided-brew-does-nothing.md`).

### Export / Import relocation (C8)
- **D-06: Move CSV Export + Import to a dedicated page, linked from the config-hub account
  section** (bottom of `config_hub.html`, near "Signed in as" / Sign out — grouped as a
  utility action, not a catalog card). The log/sessions view (`GET /brew`) loses the
  inline export/import controls. **Routes `/brew/export` + `/brew/import` are unchanged —
  only the entry-point location moves.** Planner picks the new page route/template name.

### Logo + PWA icon regeneration (C10)
- **D-07: Regenerate the circular badge + PWA icons from the new `hero.jpg`.** Source is
  `app/static/img/hero.jpg` (1021×1021, square — the bean + top-hat + monocle + espresso
  cup mascot). The current skew is baked into the PNGs because
  `scripts/generate_pwa_icons.py` points at `snobbery-login.jpg` (**2816×1536 landscape**)
  and `circular_crop()` does `resize((size,size))` with **no aspect preservation** —
  squishing the landscape source. The nav `<img>` markup is already correct
  (`h-12 w-12 rounded-full`, equal dims) — the fix is the asset + script, not CSS.
  - Repoint the script SRC to `hero.jpg`.
  - Harden `circular_crop()` to **center-crop to a square first, then resize, then mask**
    (defensive — correct even though `hero.jpg` is already square; prevents this exact bug
    from recurring with a future non-square source).
  - **Framing: FULL mascot inscribed in the largest circle** (keep the cup / steam / chain;
    do NOT zoom-crop to just the bean's face). John's explicit choice.
  - Regenerate and re-commit: `logo-badge.png`, `icon-192.png`, `icon-512.png`,
    `icon-512-maskable.png`, `apple-touch-icon.png`. Maskable keeps the existing 10%
    safe-zone padding + solid cream-50 background (Pitfall 8).
  - Login hero (`snobbery-login-hero.jpg`) is NOT regenerated — out of scope (brand lock).
  - `hero-alt.jpg` (1149×1149) is an unused alternate John also dropped in; ignore it
    (he named `hero.jpg` as the source). Safe to delete during cleanup.

### Claude's Discretion (resolve with these defaults)
- **C1 safe-area-top:** add `env(safe-area-inset-top)` padding to the mobile top strip +
  any sticky top chrome, mirroring the bottom-nav safe-area handling. **NOTE:** this reuses
  the technique from commit `982c0e6`, which is **committed but UNVERIFIED on-device**
  (memory `snobbery-safe-area-fix-unverified`). If the on-device check fails, revisit the
  approach for BOTH top and bottom (ROADMAP C1 note).
- **C3 equipment card height:** group related fields as flex-wrap pills the way coffee
  cards already do, instead of one field per line, to shorten the 375px card.
- **C6 cue controls:** replace the confusing `role="switch"` toggles on the guided-brew
  page with clearly-labeled on/off controls; **preserve the localStorage-persisted
  chime/vibrate prefs** (`snobbery:gbm:cues` namespacing).
- **C7 brew form:** make the Alpine ratio computed value recalc on **programmatic** prefill
  (use an Alpine `effect`/watcher on dose+water, not just `x-on:input`); make the 0-5
  rating stars fit on a single line at 375px (today they wrap 4 + 1).
- **C9 SW cache versioning:** the SW cache name/version must bump on every deploy so a
  rebuild reaches installed PWAs without a manual "Clear site data." Root-cause why the
  Phase 11 build-hash-in-cache-name mechanism (ROADMAP Phase 11 success criterion #2)
  isn't actually changing per build. This is **cross-cutting** — without it every other
  fix stays invisible on installed PWAs (memory `sw-stale-cache-confounds-ui-verify`).
  Verify a rebuild changes the cache key and old shells purge on activate.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition + UAT root causes (read first)
- `.planning/ROADMAP.md` §"Phase 13: PWA UX Fixes" — the 9 success criteria (C1-C9) +
  Notes (sibling fixes out of scope; C1 reuses the unverified safe-area technique;
  per-criterion root causes with file:line already investigated this session).
- `.planning/debug/resolved/guided-brew-does-nothing.md` — C5 root cause (no-steps recipe
  rendered "Start guided brew" as a dead `<span>`), the `eafc6e3` fix, and the
  post-completion prefill flow. Names the test gap C5 must close.
- `.planning/debug/resolved/bottom-nav-floats-ios-pwa.md` — the `982c0e6` bottom safe-area
  fix C1 mirrors (and whose technique is unverified on-device).
- `.planning/STATE.md` — session continuity, deferred items, the carried research flags.

### Code to read before implementing
- `app/templates/base.html` — nav frame: top nav logo (`h-12 w-12 rounded-full` line ~74),
  mobile top strip logo (line ~167), dual `theme-color` metas (lines 7-8), `<html>` tag
  (line 3, where the `.dark` class + no-FOUC script attach), iOS install banner. **C1, C4, C10.**
- `app/templates/pages/config_hub.html` — catalog hub; the mobile account/Sign-out block
  (lines 54-66) is where the dark toggle (D-01) and export/import link (D-06) attach. **C4, C8.**
- `app/templates/fragments/equipment_row.html` — the `mode="row"`/`mode="card"` split and the
  `include_oob_form_clear` mount-clear (lines 88-91); the C2 + C3 + C4 target. **C2, C3.**
- `app/templates/fragments/equipment_list.html` + the coffees equivalents
  (`coffee_list.html` / `coffee_row.html`) — the list-container the full fragment swaps into
  (D-03), and the coffee-card flex-wrap pill pattern C3 copies. **C2, C3.**
- `app/routers/` — the equipment + coffees create routes that currently return the wrong
  fragment (D-03); the brew router for `/brew` (export/import entry removal, D-06) and the
  brew_guided router (C5 entry targets). Grep for the create handlers + `form-mount`.
- `app/templates/pages/brew_guided.html` + `app/static/js/alpine-components/guided-brew-mode.js`
  — the cue controls (C6) and the localStorage cue prefs to preserve.
- `app/templates/fragments/recipe_row.html` — the fixed enabled/no-steps "Start guided brew"
  control C5's regression test must cover; the link target Home/Log route to via `/recipes`.
- `app/templates/pages/home.html` + `session_list.html` / `session_row.html` — where the C5
  "Guided Brew" action attaches; where C7 brew-form/rating lives is the brew form template.
- `app/static/css/tailwind.src.css` — palette + the two `@media (prefers-color-scheme: dark)`
  blocks (lines ~88, ~111) that must become class-driven (D-01); `.htmx-indicator`,
  `darkMode` config. **All CSS lives here — no `custom.css` (MX-1).** **C4.**
- `scripts/generate_pwa_icons.py` — the icon generator (SRC hardcoded to `snobbery-login.jpg`,
  the non-aspect-safe `circular_crop`); repoint + harden per D-07. **C10.**
- `app/routers/pwa.py` + `app/static/sw.js` (and `/manifest.json` route) — the service-worker
  cache name/version + manifest icon refs; C9 build-hash bump lives here. **C9.**
- `app/static/img/hero.jpg` (new source, 1021² square), `logo-badge.png`, `icon-*.png`,
  `apple-touch-icon.png` — the C10 regenerate targets.
- `app/static/js/htmx-listeners.js` — `htmx.config.allowEval=false` + CSRF header; the
  constraint all new JS (dark-toggle, cue controls) runs under.

### Operational + design locks
- `CLAUDE.md` §"Architectural invariants" (mobile-first 375px; **don't break manifest / SW /
  install flow**; CSRF + CSP + security headers on every response; reverse-proxy aware),
  §"Stack invariants" (Jinja+HTMX+Tailwind CLI+Alpine, no npm), §"Things to never do
  silently" (no schema drops, no disabling CSRF/CSP).
- `docs/decisions/0001*` — the Alpine CSP-build / eval-free component decision the dark-toggle
  + cue-control JS must honor (no inline `hx-on:`, no `eval`; nonce'd inline scripts only).
- `.planning/phases/11-pwa-mobile-polish/11-CONTEXT.md` — D-12..D-16 (the badge=icon decision,
  always-dark login D-14, the D-15 pre-generate-and-commit icon workflow C10 reuses), the SW
  SWR strategy, GBM entry points (D-07/D-08) C5 extends.

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- **Tailwind CSS v4** — `darkMode: 'class'` / `@custom-variant dark` migration from `media`
  (CSS-config, standalone CLI, no JS config file). The load-bearing C4 reference.
- **PWA / service worker** — cache versioning + `activate`-event old-cache purge (C9).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`scripts/generate_pwa_icons.py`** — already produces all six assets from one source;
  C10 is a SRC swap + an aspect-safe crop hardening, not a rewrite (D-15 "generate + commit"
  workflow stays).
- **Coffee card flex-wrap pills** — C3 copies the existing coffee-card field grouping onto
  equipment cards; no new pattern.
- **`config_hub.html` account section** (lines 54-66) — the attach point for BOTH the dark
  toggle (D-01) and the export/import link (D-06).
- **localStorage namespacing** (`snobbery:draft:brew:<user_id>`, `snobbery:gbm:cues`) — the
  model for the `snobbery:theme` dark-mode pref (D-01).
- **Alpine CSP component pattern** (`alpine-components/*.js`, registered before the
  `@alpinejs/csp` core) — the dark-toggle + redesigned cue controls follow it.
- **Recipe-list "Start guided brew" control** (fixed in `eafc6e3`) — C5 reuses it; Home/Log
  just route to `/recipes`.

### Established Patterns
- Strict nonce-CSP + Alpine CSP build (no eval, no inline `hx-on:`); the no-FOUC dark script
  must be an inline `<head>` script carrying the request nonce.
- All CSS in `tailwind.src.css` (MX-1 lock — no `custom.css`).
- HTMX fragment routes: `Cache-Control: no-store` + `Vary: HX-Request`.
- Single uvicorn worker — unchanged (no new background work this phase).
- Derived image assets are pre-generated and committed, never built at Docker/runtime (D-15).

### Integration Points
- `<html>` tag in `base.html` — `.dark` class toggling + the pre-paint nonce'd script (C4).
- `tailwind.src.css` — `media`→`class` dark variant + the two hardcoded media blocks (C4).
- Equipment + coffees create routes — return the list fragment, not the row variant (C2).
- `config_hub.html` — dark toggle + export/import link in the account section (C4, C8).
- `home.html` + `session_list.html` — "Guided Brew" → `/recipes` action (C5).
- `app/static/sw.js` / `pwa.py` — cache version bump per deploy (C9).
- `scripts/generate_pwa_icons.py` + `app/static/img/` — regenerate from `hero.jpg` (C10).

</code_context>

<specifics>
## Specific Ideas

- **The skew is in the PNG, not the CSS** — `snobbery-login.jpg` (2816×1536) squished into a
  square by a non-aspect-safe resize. New `hero.jpg` is a clean 1021² square mascot.
- **Full mascot in the circle** (C10) — keep the espresso cup + steam + monocle chain; don't
  zoom to just the bean face. John's explicit framing choice.
- **Auto stays the dark-mode default** (C4) — existing system-preference behavior is the
  baseline; the toggle is an override, not a replacement. No regression for current users.
- **Login is the brand moment** — stays always-dark regardless of the toggle (D-02 / D-14).
- **C9 is load-bearing** — without the SW cache bump, none of C1-C8/C10 reach the installed
  PWA; treat it as a gate, not a nicety.
- **Per-criterion root causes already exist with file:line** (investigated this session) —
  planning can lean on them and the two resolved debug docs instead of re-researching.

</specifics>

<deferred>
## Deferred Ideas

- **`hero-alt.jpg`** (1149×1149) — alternate mascot art John also dropped in; not chosen as
  the source. Delete during cleanup or keep as reference; not used by C10.
- **`brew_time_seconds` in analytics** — column exists (Phase 11 D-10); surfacing it
  analytically remains a future enhancement (untouched here).
- **Per-user settings/preferences page** — still none in v1; the dark-mode pref lives in
  localStorage like the GBM cue prefs. If a real prefs surface emerges, migrate them there.
- **On-device verification of the safe-area technique** (C1, and the existing `982c0e6`
  bottom fix) — must be checked on a real iPhone; if it fails, both top and bottom need a
  revised approach (memory `snobbery-safe-area-fix-unverified`).

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-pwa-ux-fixes*
*Context gathered: 2026-05-24*
