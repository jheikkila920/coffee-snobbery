# Phase 10: Global Search - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a Postgres-backed global search across the household catalog plus the
searcher's own brew notes, delivering 4 requirements (SEARCH-01..04). This phase
is a **new search service + router + a self-contained search component**
(input + grouped live-results fragment), not changes to the catalog/brew
features themselves.

In scope (locked by ROADMAP success criteria + REQUIREMENTS):
- **SEARCH-01 — Cross-entity search** across six field sets: coffee names,
  roaster names, flavor-note names, recipe name + description, equipment names,
  and the searcher's own brew-session notes. Results grouped under entity-type
  headers; each result links to the entity.
- **SEARCH-02/03 — Scoping:** brew-session notes are visible only to the
  searcher (per-user); the shared catalog (coffees, roasters, recipes,
  equipment, flavor notes) appears in every authenticated user's results.
- **SEARCH-04 — Debounced HTMX live results:** fire 250ms after the last
  keystroke, only at >= 2 chars, with `hx-sync="this:replace"` cancelling
  in-flight requests (HX-4). p95 < 100ms against a seeded dataset.
- **Responsive shell:** inline in the top header at >= 768px; collapses to a
  search icon at < 768px that expands to a full-screen sheet.
- **Index DDL** (FTS or trigram) is this phase's migration work — not landed
  early in Phase 0.

Out of scope (belongs to later phases or deferred):
- **Full global navigation + sign-out + brand wordmark** — Phase 11 (memory:
  `phase-11-owes-nav-and-signout`). Phase 10 adds only a minimal persistent
  header to mount search; Phase 11 absorbs it into the real top/bottom nav.
- **A dedicated full results page / pagination / Enter-to-see-all** — live
  results only in v1 (D-04).
- **Recent searches / pre-search suggestions** — needs new per-user state;
  deferred.
- **Expanding coffee search to origin/process/roast-level fields** — SEARCH-01
  enumerates *names* only; field expansion is out of scope (deferred idea).

4 requirements mapped: SEARCH-01, SEARCH-02, SEARCH-03, SEARCH-04.

</domain>

<decisions>
## Implementation Decisions

### Placement & shell (SEARCH-04 responsive shell)

- **D-01: Minimal persistent search header in `base.html`.** `base.html`
  currently has no nav at all (`{% block content %}` is the whole body). Add a
  thin persistent header that holds *just* the search component, so search is
  available on every page now. Phase 11 grows this header into the full
  top/bottom nav (mirrors Phase 9 D-03: minimal chrome now, full nav later).
  The header must be **auth-gated** — render only when `request.state.user` is
  set, so it does NOT appear on `/login` and `/setup` (which also extend
  `base.html`). Existing per-page action buttons (e.g. home's Admin / Log
  session) stay as-is for now; the new header adds search only. The component
  is self-contained so Phase 11 can relocate it with minimal rework.
- **D-02: Desktop (>= 768px) results = floating dropdown overlay.** An overlay
  panel anchored under the input, grouped by entity type, dismissed on
  outside-click and Esc. Does not push or disturb page content.
- **D-03: Mobile (< 768px) = icon -> full-screen sheet.** The collapsed search
  icon expands to a full-screen sheet with the input auto-focused; results fill
  the sheet. Close affordances: an X button, Esc, and tapping the backdrop
  (scrim). Tapping a result navigates and closes the sheet. **No browser-history
  / pushState entry** — back-button-closes is explicitly not wired in v1.
- **D-04: Live results only — no dedicated results page.** The dropdown/sheet is
  the entire feature. Pressing Enter does nothing special (planner may make it a
  no-op or focus the first result). No `/search` results page, no pagination.

### Result content & match display (SEARCH-01)

- **D-05: Each row shows name + key context.** Coffee -> name + roaster +
  origin; equipment -> name + type; recipe -> name + short description; roaster
  / flavor note -> name; brew note -> coffee name + brew date + a snippet of the
  note around the match. Enough to disambiguate without clutter.
- **D-06: Highlight the matched substring.** The matched text is emphasized
  (`<mark>`/bold) in each row so the user sees why it matched (especially
  brew-note snippets). **Must be done without `|safe` on user text** — build the
  highlighted fragment by escaping the surrounding text and composing a
  `markupsafe.Markup` with the match wrapped, so autoescape stays effective and
  there is no injection. (Implementation flagged for research/planner.)

### Ordering, limits & empty states (SEARCH-01)

- **D-07: Fixed group order — catalog then notes.** Coffees, Roasters, Recipes,
  Equipment, Flavor Notes, then Your Brew Notes — the exact order named in
  ROADMAP success criterion #1. Stable, predictable scanning (no layout shift
  while typing).
- **D-08: Relevance sort within each group.** Best match first — prefix/exact
  matches rank above mid-string hits. The exact mechanism (FTS `ts_rank` vs
  `pg_trgm` similarity) follows the FTS-vs-trigram research decision.
- **D-09: Cap ~5 per group + a non-clickable "+N more" hint.** Show the top ~5
  results per group; if more matched, render a non-clickable
  "+N more — keep typing to narrow" line. No expansion control (there is no
  results page). Keeps the dropdown/sheet short.
- **D-10: Empty states.** The dropdown/sheet stays closed below 2 chars (the
  min-length is already locked by SEARCH-04). On a query with no matches, show a
  snobbery-tone empty line (e.g. "Nothing matches. The grounds are clean.").
  No recent-searches or pre-search hint state (no new per-user storage).

### Link targets (SEARCH-01 "links to the entity")

- **D-11: Per-entity result destinations.**
  - Coffee -> `/coffees/{id}` (the richer **detail** page; edit is one tap from
    there). Chosen over the edit form because search is read-first.
  - Roaster / equipment / recipe / flavor note -> `/{entity}/{id}/edit` (the
    only stable per-entity URL; recipe edit is the full step-builder view
    anyway).
  - Brew note -> `/brew/{id}/edit` (the only per-session destination).
  - Result links are **full-page navigations**, not HTMX swaps.

### Scope of searched rows

- **D-12: Include archived coffees/equipment, marked with an "Archived"
  badge.** Archived (soft-deleted) coffees and equipment DO surface in results,
  visually tagged so the user can re-find a discontinued bean without confusion.
  (Chosen over excluding them; needs a small badge style.)

### Claude's Discretion (resolve with these defaults)

- **FTS vs trigram** — explicitly punted to plan-phase research (PROJECT Key
  Decisions). Prototype both `tsvector + to_tsquery` (GIN) and `pg_trgm`
  ILIKE/similarity (GIN trigram) against the seeded dataset; pick one. This also
  fixes D-08's relevance mechanism and the migration's index DDL.
- **Query shape** — six per-entity queries vs one `UNION ALL`: planner's call,
  whichever keeps p95 < 100ms and reads cleanly at household scale.
- **Enter-key / arrow-key behavior** — planner's call; keep minimal (Enter as
  no-op acceptable; basic arrow-nav optional, else deferred).
- **`aria-live` results region** for screen-reader announcement — planner adds
  per accessibility best practice.
- **Snippet length** for brew-note matches — planner's call (sensible window
  around the match).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 10: Global Search" — goal, the 4 success
  criteria, and Notes (HX-4 debounce 250ms + min-length + `hx-sync`; the
  FTS-vs-trigram plan-phase research flag; "indexes are migration work — defer
  index creation to this phase").
- `.planning/REQUIREMENTS.md` SEARCH-01..04 — verbatim requirements.
- `.planning/PROJECT.md` §"Global Search" requirements, §"Constraints"
  (mobile-first 375px; CSP; full security headers; no public registration;
  Postgres required for FTS), §"Key Decisions" (search FTS-vs-trigram chosen at
  plan-phase).
- `.planning/STATE.md` — session continuity.

### Prior phase context (decisions Phase 10 builds on)
- `.planning/phases/09-admin/09-CONTEXT.md` — D-03 (minimal entry link, full
  global nav + sign-out deferred to Phase 11); the catalog CRUD router + HTMX
  fragment + `Cache-Control: no-store` + `Vary: HX-Request` idiom; sync `def`
  handler / threadpool pattern.
- `.planning/phases/04-shared-catalog/04-CONTEXT.md` — the catalog entities,
  their routers/templates, the autocomplete grouped-list fragment pattern, and
  the `archived` soft-delete convention on coffees/equipment.
- `.planning/phases/05-brew-sessions/05-CONTEXT.md` — `brew_sessions` shape, the
  free-text notes field that is the per-user searchable target, and per-user
  scoping (sessions are the searcher's own).
- `.planning/phases/01-middleware/01-CONTEXT.md` (if present) — the fragment
  cache-header middleware + CSP nonce + Alpine-CSP-build constraints the search
  component must honor.

### Code in this repo (read before implementing)
- `app/templates/base.html` — the mount point for the persistent search header
  (currently no nav); also where the search Alpine component script loads
  (before the `@alpinejs/csp` core, like the other components). Login/setup
  extend this — header must conditionally render on `request.state.user`.
- `app/templates/pages/home.html` — existing ad-hoc per-page header pattern +
  `request.state.user` / `is_admin` gating reference.
- `app/routers/coffees.py` — `GET /coffees/{id}` (detail target, D-11) and
  `/coffees/{id}/edit`; searchable `name` + the `archived` flag.
- `app/routers/roasters.py`, `app/routers/equipment.py`,
  `app/routers/recipes.py`, `app/routers/flavor_notes.py` — `/{id}/edit` targets
  (D-11) + the searchable `name`/`description` columns; equipment `archived`.
- `app/routers/brew.py` — `GET /brew/{session_id}/edit` (D-11 brew-note target)
  + the brew-session notes field.
- `app/main.py` — router registration block (add the new search router here).
- `app/models/` — `coffee.py`, `roaster.py`, `flavor_note.py`, `recipe.py`,
  `equipment.py`, `brew_session.py`: confirm the exact searchable columns and
  `archived`/`user_id` columns.
- `app/static/css/tailwind.src.css` — define/confirm the `.htmx-indicator`
  style here so the search spinner shows under strict nonce-CSP (memory:
  `strict-csp-blocks-htmx-indicator`).
- `app/static/js/htmx-listeners.js` — HTMX config (allowEval=false, CSRF header)
  the search requests run under.
- `app/middleware/fragment_cache.py` — the `no-store` + `Vary: HX-Request`
  policy the results fragment inherits.
- `app/templates_setup.py` — the shared autoescape-on `Jinja2Templates`
  instance + `csp_nonce` / CSRF helpers.
- `app/templates/fragments/autocomplete_list.html` — closest existing analog for
  rendering a grouped live-results fragment.
- `app/services/` — new `search.py` lives here (CLAUDE.md "Files worth knowing"
  reserves `app/services/search.py` for global search; it does not exist yet).

### Operational + spec
- `CLAUDE.md` §"Architectural invariants" (shared catalog vs per-user data;
  mobile-first 375px; CSRF + security headers on every response; reverse-proxy
  aware), §"Code conventions" (SQLAlchemy 2.0 `select()` + `Mapped[...]`;
  Pydantic v2; 2-space Jinja; no `|safe` on user content).

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- PostgreSQL 16 — `pg_trgm` (GIN trigram, `similarity()`, ILIKE) vs FTS
  (`tsvector`, `to_tsquery`/`websearch_to_tsquery`, `ts_rank`, GIN) for the
  D-08 relevance mechanism + the index migration.
- HTMX 2.0.x — `hx-trigger` debounce (`keyup changed delay:250ms`),
  `hx-sync="this:replace"`, `hx-indicator` (HX-4).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Catalog CRUD routers + fragment templates** (`roasters.py`, `equipment.py`,
  `coffees.py`, `recipes.py`, `flavor_notes.py`) — the HTMX list/fragment idiom
  + route shapes the search results link into; `autocomplete_list.html` is the
  closest analog for a grouped live-results fragment.
- **`fragment_cache.py` middleware** — gives the results fragment the right
  `no-store` + `Vary: HX-Request` headers for free.
- **Alpine CSP component pattern** (`base.html` script block) — a new
  `search-bar.js` (expand/collapse + full-screen sheet + dropdown open/close)
  follows the same eval-free registration loaded before the `@alpinejs/csp`
  core.
- **`request.state.user` gating** (home.html) — the auth gate the persistent
  header reuses to hide search on login/setup.

### Established Patterns
- "Cross-cutting -> middleware; feature surface -> router; stateful logic ->
  service." Phase 10 = new `services/search.py` (queries) + `routers/search.py`
  (the live-results endpoint + the component) + templates/fragments. Search is a
  **GET, read-only** endpoint — CSRF does not apply (no token needed), but
  security headers + autoescape still do.
- Sync DB sessions for CRUD-style reads (Phase 4-onward pattern); search queries
  are sync `select()` constructs.
- Snobbery-tone empty states; strict nonce-CSP; no `|safe` on user text
  (D-06 highlight must respect this).

### Integration Points
- `app/templates/base.html` — add the auth-gated persistent header + load the
  new search Alpine component.
- `app/main.py` — register `routers/search.py`.
- `app/migrations/versions/` — new migration adds the search index(es) (FTS GIN
  or `pg_trgm` GIN — decided at plan-phase). This is the only schema work.
- `app/static/css/tailwind.src.css` — ensure `.htmx-indicator` style is present
  for the search spinner under strict CSP.

</code_context>

<specifics>
## Specific Ideas

- **The persistent header is auth-gated** — render only when
  `request.state.user` is set; it must not appear on `/login` or `/setup`
  (both extend `base.html`).
- **Highlight without `|safe`** — escape the surrounding text, wrap the match in
  `<mark>` via `markupsafe.Markup` composition; never pass user text through
  `|safe`. This is the one subtle correctness trap in the phase.
- **Results fragment** served with `Cache-Control: no-store` + `Vary: HX-Request`
  (inherited from the Phase 1 middleware).
- **Search input wiring** — `hx-trigger="keyup changed delay:250ms"` (>= 2-char
  guard), `hx-sync="this:replace"`, `hx-indicator` spinner. GET request.
- **Brew-note search target** — the free-text notes field on `brew_sessions`,
  filtered to `brew_sessions.user_id == current_user.id`.
- **Coffee search is name-only** — origin/process/roast-level are NOT searched
  (SEARCH-01 enumerates names); a coffee's origin shows as result *context*
  (D-05) but is not a match field.

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are SEARCH-01..04 in
REQUIREMENTS.md plus the decisions above and the canonical refs.

## Research flags (for gsd-phase-researcher)
- **FTS vs `pg_trgm`** — prototype both against the seeded dataset; pick one.
  Decides D-08's relevance mechanism (`ts_rank` vs `similarity`) and the
  migration's index DDL. Both are pure-Postgres, no architecture impact.
- **Exact searchable columns per entity** — confirm: `coffees.name` (+ `archived`),
  `roasters.name`, `flavor_notes.name`, `recipes.name` + `recipes.description`,
  `equipment.name` (+ `archived`), `brew_sessions.notes` (user-scoped). Confirm
  coffee origin/process are deliberately excluded.
- **Cross-entity query shape** — six queries vs one `UNION ALL`; keep p95 < 100ms.
- **Safe highlight in Jinja/Python** without `|safe` (markupsafe composition).
- **Confirm `login.html`/`setup.html` extend `base.html`** so the auth-gated
  header conditional is required.

</specifics>

<deferred>
## Deferred Ideas

- **Full global nav + sign-out + brand wordmark** — Phase 11 (absorbs this
  phase's minimal search header). Memory: `phase-11-owes-nav-and-signout`.
- **Dedicated full results page + pagination + Enter-to-see-all** — live-only in
  v1 (D-04); revisit if the dropdown/sheet feels limiting.
- **Recent searches / pre-search suggestions** — needs new per-user state;
  deferred.
- **Expanding coffee search to origin / process / roast-level fields** (typing
  "ethiopia" matching coffees by origin) — beyond SEARCH-01's enumerated name
  fields; revisit if name-only search feels limiting in use.
- **Keyboard arrow-navigation through results** — nice-to-have; planner may add
  a basic version, else deferred.
- **Searching recipe step text** — only recipe name + description are in scope.

None of the above were folded; discussion stayed within phase scope.

</deferred>

---

*Phase: 10-Global Search*
*Context gathered: 2026-05-21*
