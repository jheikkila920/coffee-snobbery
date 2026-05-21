# Phase 6: Analytics (Home Page) - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

The home page becomes the per-user "preference brain": pure-SQL derivations over
*this user's own* brew log, each card lazy-loaded via HTMX, plus the
`compute_input_signature()` plumbing that Phase 7's AI card will later read to
decide whether a recommendation is stale.

In scope (8 requirements: HOME-01..05, HOME-07..09):
- **HOME-01** Top 5 coffees by the user's avg rating, min 2 sessions, with rating + count.
- **HOME-02** Preference-profile cards: avg rating by origin / process / roaster / roast level.
- **HOME-03** Top-10 flavor descriptors appearing in this user's 4.0+ rated sessions.
- **HOME-04** Roast-freshness buckets (0-3, 4-7, 8-14, 15-21, 22+ days) using `bags.roast_date` (NEVER `coffees.roast_date`); avg rating per bucket.
- **HOME-05** Top 3 sweet spots `(origin × process × brewer × recipe)`, min 3 sessions, ranked by avg rating; pure SQL via UNION of GROUP BY queries with HAVING (no Python loops).
- **HOME-07** Recent brews list: last 10 sessions with edit links (eager-loaded in the initial page render).
- **HOME-08** Unrated coffees list: shared-catalog coffees this user hasn't brewed.
- **HOME-09** Each section lazy-loads via HTMX after initial render; staggered fire (50-150ms apart) to avoid thundering-herd on the connection pool.
- `services/analytics.py::compute_input_signature(user_id) -> str` — content hash of the user's own sessions (COST-4), the stale-data plumbing Phase 7 consumes.

Out of scope (belongs to later phases):
- **HOME-06** AI prose interpretation under Sweet Spots — **Phase 7** (needs the AI service).
- The actual AI recommendation card, "Outdated" badge rendering, manual refresh, regeneration — **Phase 7**. Phase 6 only ships the signature *helper*; nothing in Phase 6 renders an AI card or a stale badge.
- Bottom-tab nav / PWA shell / dark-mode polish / final aesthetic — **Phase 11**. Phase 6 templates must work at 375px (card stacking) but the persistent nav frame is Phase 11.
- Global search across session notes (SEARCH-*) — **Phase 10**.
- Formal Playwright responsive + analytics-query test suite — **Phase 12** (add tests as you go per CLAUDE.md, but the formal suite is Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Cold-start gating
- **D-01: Hybrid gating layout.** Recent brews (HOME-07) and unrated coffees (HOME-08) ALWAYS render — they need no rating or aggregation. The five aggregate cards (top coffees, preference profile, flavor descriptors, roast-freshness buckets, sweet spots) are gated behind the cold-start meter. So a brand-new user still sees their logged brews + a "what to try next" catalog list while the analytics fill in.
- **D-02: Unlock threshold = the same gate as AI (≥3 sessions AND ≥5 distinct observed flavor notes).** One unified threshold across analytics + AI (AI-7), simplest mental model, matches ROADMAP Phase 6 success criterion 4 as written. The aggregate-card block is replaced by the empty state until BOTH conditions hold.
- **D-03: Dynamic remaining-counts progress meter.** Computed from the user's actuals — e.g. "Log 2 more brews and add 3 more flavor notes to unlock recommendations." Counts update as the user logs. (Exact ROADMAP example copy.)

### Sparse-card states (user past the gate, but a card's own query is empty)
- **D-04: Render-with-hint, uniform across all aggregate cards.** Once the gate clears, every aggregate card stays in place even when its specific query returns no qualifying rows; it shows a short hint (e.g. "No coffee with 2+ sessions yet — keep logging"). Keeps layout stable run-to-run and teaches the per-card threshold. No card hides on emptiness in v1.
- **D-05: Rating-dependent cards detect the all-unrated case and show a distinct "rate your brews" nudge.** `rating` is nullable, so a user can clear the gate (≥3 sessions, ≥5 notes) with zero rated sessions — top coffees, preference profile, flavor descriptors, and freshness buckets would all be empty. When the cause is "sessions exist but none are rated," those cards say "Rate some brews to see this" rather than the generic not-enough-data hint. (Distinguish the all-unrated cause from genuine sparsity.)

### Min-session floors (analytics integrity)
- **D-06: Min 2 of the user's sessions per bucket for the preference profile (HOME-02).** A dimension value (origin / process / roaster / roast level) needs ≥2 of the user's sessions to appear, mirroring the HOME-01 top-coffees floor. Prevents a single 5-star session from crowning an "origin."
- **D-07: The min-2 floor is uniform across the three unspecified cards.** Roast-freshness buckets (HOME-04) need ≥2 rated sessions to show a bucket's avg; a flavor descriptor (HOME-03) must appear in ≥2 of the user's 4.0+ sessions to enter the top-10 (not a pure single-occurrence frequency ranking). HOME-01 (min 2) and HOME-05 (min 3) keep their already-specified floors. One consistent integrity rule.

### Signature composition (Phase 7 stale-data plumbing)
- **D-08: Hash per-session AI input fields only.** For each of the user's sessions, the signature inputs are `(coffee_id, rating, sorted flavor_note_ids_observed, recipe_id, brewer_id, bag roast_date)`. Free-text `notes` and edit timestamps are EXCLUDED, so a notes typo-fix never invalidates the recommendation. Signature changes exactly when a recommendation-relevant input changes. (COST-4: scope is the user's OWN sessions only — never shared catalog counts like equipment/recipe totals.)
- **D-09: Only rated sessions feed the signature.** An unrated session is invisible to the signature until it is rated. Every AI-consumed derivation is rating-gated (top coffees, profile, descriptors all need ratings; descriptors need 4.0+), so an unrated brew cannot change the recommendation — excluding it is both cost-optimal and correct. NOTE: this is the *signature* gate only; the cold-start unlock (D-02) is checked from LIVE counts, not the signature, and DOES count unrated sessions toward the ≥3 threshold.

### Claude's Discretion
- **Home route location + page composition** — recommend a dedicated `app/routers/home.py` (the real `/` route, replacing the Phase 0 placeholder in `app/main.py:249-260`) with an eager shell + per-card lazy fragment endpoints. Planner picks the exact route/module shape.
- **Fragment endpoint shape** — one combined lazy endpoint vs per-card fragment endpoints (e.g. `/home/cards/top-coffees`). Recommend per-card endpoints so each staggers independently (HOME-09) and a slow card can't block the others; reuse the Phase 4/5 HTMX-fragment + `FragmentCacheHeadersMiddleware` (`no-store` + `Vary: HX-Request`) conventions.
- **Card ordering / prominence on the page** — planner picks the vertical stack order (mobile-first). A UI-SPEC pass (`/gsd-ui-phase 6`) can refine visuals; Phase 11 owns the final aesthetic + nav frame.
- **Tie-breaking within ranked cards** — recommend avg rating DESC, then session count DESC (more evidence wins), then most-recent. Applies to top coffees, profile, sweet spots.
- **Signature serialization + hash algorithm** — recommend deterministic ordering (sort session rows by id) + a stable canonical serialization hashed with sha256, returned as hex. Must be order-independent and reproducible. Planner confirms.
- **`compute_input_signature` return when the user has zero rated sessions** — recommend a stable sentinel (e.g. hash of empty set) so Phase 7 can compare cleanly.
- **Per-card query indexes** — the `(user_id, brewed_at DESC)` and `(user_id, coffee_id, brewed_at DESC)` indexes + the GIN index on `flavor_note_ids_observed` already ship from Phase 5; planner adds any additional analytics index only if a query's p95 exceeds the <50ms budget on the 1000-session seed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 6: Analytics (Home Page)" — goal sentence, 4 success criteria, and Notes (carries HX-5 staggered lazy-load to avoid thundering-herd, SH-2 connection-pool sizing `pool_size=10, max_overflow=5`, COST-4 signature must NOT include shared `equipment_count`/`recipe_count`, AI-7 cold-start gate at `min_sessions=3 AND min_flavor_notes=5`). Confirms HOME-06 (AI prose) is owned by Phase 7 and sweet-spots SQL is a UNION of GROUP BYs with HAVING (no Python loops).
- `.planning/REQUIREMENTS.md` §"Home Page (HOME)" — HOME-01..05, HOME-07..09 verbatim (HOME-04 roast-freshness buckets + `bags.roast_date` rule; HOME-05 `(origin × process × brewer × recipe)` min 3; HOME-09 staggered 50-150ms lazy-load). HOME-06 is mapped to Phase 7.
- `.planning/PROJECT.md` §"Home Page (Analytics)" + §"Key Decisions" rows ("Cost control via signature-based regen only", "Cold-start AI: friendly empty state with progress meter"). §"Architectural invariants" — "Brew sessions and AI recommendations are per-user"; "Signature-based AI regeneration … the nightly job only regenerates when input signature changed … Don't break this — it's the cost control."; mobile-first 375px; security headers on every response.
- `.planning/STATE.md` — decision accumulator. No Phase-6-specific research flag carried forward (live flags belong to Phases 7, 10, 11). Confirms Phase 5 complete (6/6), test-isolation defect resolved (conftest forces `<db>_test`).

### Prior phase context (decisions Phase 6 inherits)
- `.planning/phases/05-brew-sessions/05-CONTEXT.md` — the data this phase reads. `brew_sessions` schema, the `flavor_note_ids_observed` BIGINT[] containment-query intent (Phase 6 analytics is the named consumer in the model docstring), `extraction_yield_pct` GENERATED column, the `(user_id, brewed_at)` + `(user_id, coffee_id, brewed_at)` indexes, and the per-user scoping invariant (every read scoped by `user_id`).
- `.planning/phases/04-shared-catalog/04-CONTEXT.md` — HTMX-fragment CRUD conventions, the `coffees`/`bags`/`recipes`/`equipment`/`flavor_notes` schemas analytics joins against, and `coffees.advertised_flavor_note_ids` vs per-session observed notes distinction.
- `.planning/phases/01-middleware/01-CONTEXT.md` — `FragmentCacheHeadersMiddleware` (`Cache-Control: no-store` + `Vary: HX-Request` on HTMX fragments — every lazy analytics fragment relies on it); CSP-strict Alpine (CSP build, `Alpine.data(...)`, no `hx-on:` inline, no `|safe`).
- `.planning/phases/02-auth/02-CONTEXT.md` — `request.state.user` is the full `User` row; `require_user` in `app/dependencies/auth.py` gates the home route; analytics is scoped to `request.state.user.id`.
- `.planning/phases/00-foundation/00-CONTEXT.md` — `app/db.py::SessionLocal` sync session pattern (analytics uses sync sessions); Postgres extensions; one migration per logical change (Phase 6 likely needs NO migration — all columns + indexes already exist).

### Operational + spec
- `CLAUDE.md` §"Architectural invariants" ("Signature-based AI regeneration … Don't break this — it's the cost control"; per-user brew sessions; mobile-first 375px; security headers), §"Files worth knowing" (`app/services/analytics.py` = "the home page brain"), §"Code conventions" (ruff, type hints, Pydantic v2, SQLAlchemy 2.0 `select()` style — no legacy Query API), §"Things to never do silently" (no `|safe`; never disable CSRF/CSP).
- `docs/snobbery-gsd-prompt.md` — original brief; the "what to buy next, grounded in your actual log" core-value framing and the preference-derivation intent originate here. `.planning/` docs are authoritative where they diverge.

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- `sqlalchemy` (`>=2.0.49,<2.1`) — `select()`, `func.avg`/`func.count`, `group_by`/`having`, `union_all` for the sweet-spots UNION-of-GROUP-BYs (HOME-05), `func.unnest` / `ANY` / array containment for flavor-descriptor aggregation over `flavor_note_ids_observed` (HOME-03), date arithmetic for freshness buckets (HOME-04).
- `htmx` 2.0.10 (CDN, in `base.html`) — `hx-trigger="load delay:Nms"` staggered triggers (HOME-09), `hx-get` fragment loads, `hx-target`/`hx-swap`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all on disk from Phases 0-5)
- **`app/db.py::SessionLocal`** + the Phase 0 pool knobs (`pool_size=10, max_overflow=5`) — analytics queries run on sync sessions; staggered lazy-load (D-01 / HOME-09) is specifically to avoid all cards hitting the pool at once.
- **`FragmentCacheHeadersMiddleware`** — every lazy analytics fragment gets `Cache-Control: no-store` + `Vary: HX-Request` for free; no per-route cache wiring needed.
- **HTMX-fragment + `hx-push-url` conventions** from Phase 4/5 lists — the per-card fragment endpoints reuse the same render-fragment-on-HX-Request pattern.
- **CSP-strict Alpine registration** (`app/static/js/alpine-components/` + `__init.js`) — any interactive bit (unlikely; most cards are static SQL render) registers via `Alpine.data`, no inline expressions.
- **`app/dependencies/auth.py::require_user`** + `request.state.user` — gate the home route; scope every query by `request.state.user.id`.
- **`app/templates/base.html`** — CSP nonce + CSRF meta + HTMX/Alpine already loaded; home page extends it.
- **Existing indexes from Phase 5** — `ix_brew_sessions_user_brewed_at`, `ix_brew_sessions_user_coffee_brewed_at`, and the GIN index on `flavor_note_ids_observed` already serve most analytics access paths.

### Established Patterns (Phase 6 follows)
- "Cross-cutting → middleware; feature surface → router; stateful logic → service." Phase 6 adds `app/services/analytics.py` (the derivations + `compute_input_signature`) and a home router (recommend `app/routers/home.py`, replacing the `app/main.py` placeholder `/` route).
- "Pure SQL, no Python loops" for the derivations (ROADMAP lock) — `select()` + `group_by`/`having` + `union_all`; SQLAlchemy 2.0 style, no legacy Query API.
- "CSP-strict: no `unsafe-eval`, no `hx-on:`, no `|safe`" — analytics templates are subject to the existing CI grep tests (Phase 1/12).
- "Add tests as you go" — analytics-query unit tests against a seeded DB are formally a Phase 12 deliverable (TEST-02) but should accrue here per CLAUDE.md.

### Integration Points
- `app/main.py:249-260` — the Phase 0 placeholder `@app.get("/") def home(...)` is REPLACED by the real analytics home route this phase (move to `app/routers/home.py` + `include_router`, or replace in place — planner picks).
- `app/services/analytics.py` — NEW module ("the home page brain" per CLAUDE.md). Houses every HOME-01..05/07/08 derivation + `compute_input_signature`.
- `app/models/__init__.py` — no new model expected; analytics reads existing `brew_sessions`, `coffees`, `bags`, `recipes`, `equipment`, `flavor_notes`.
- `app/migrations/versions/` — likely NO migration needed (all columns + indexes already exist from Phases 0/4/5). Add one only if a query's p95 demands a new index.
- `app/events.py` — optional: an `analytics.*` event if any audit-worthy compute happens; most reads need none.

</code_context>

<specifics>
## Specific Ideas

- **`rating` is nullable** — this drives D-05 (distinct "rate your brews" nudge) and D-09 (only rated sessions feed the signature). Every rating-weighted card must handle the all-unrated user.
- **Two flavor-note arrays must never be conflated:** `coffees.advertised_flavor_note_ids` (roaster-advertised, per coffee) vs `brew_sessions.flavor_note_ids_observed` (what the user tasted, per session). HOME-03 aggregates the OBSERVED array; the descriptor-frequency query unnests `flavor_note_ids_observed` over the user's 4.0+ sessions and joins to `flavor_notes` for names.
- **Roast freshness reads `bags.roast_date`, never `coffees.roast_date`** (HOME-04, hard rule). Freshness-at-brew = `brew_sessions.brewed_at::date - bags.roast_date` in days; bucket boundaries 0-3 / 4-7 / 8-14 / 15-21 / 22+. Sessions with no `bag_id` or a bag missing `roast_date` are excluded from this card.
- **Sweet spots (HOME-05) is a UNION of GROUP BYs with HAVING** — top 3 across the `(origin × process × brewer × recipe)` combination space, min 3 sessions, ranked by avg rating. Pure SQL, single round-trip; no per-row Python iteration.
- **Cold-start unlock counts vs signature inputs are different gates** — D-02 unlock uses LIVE counts (sessions ≥3 incl. unrated, distinct observed notes ≥5); D-09 signature counts only RATED sessions. Don't unify them.
- **Performance budget is load-bearing:** p95 < 50ms per query on a 1000-session seed; home TTI < 2s at 375px on throttled 3G. Staggered lazy-load (50-150ms) is the connection-pool protection (HX-5).

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are captured in the decisions above plus the canonical refs (REQUIREMENTS.md HOME-01..05, HOME-07..09).

</specifics>

<deferred>
## Deferred Ideas

- **HOME-06 AI prose under Sweet Spots** — Phase 7. Phase 6 ships only the `compute_input_signature` helper; no AI card, no "Outdated" badge rendering here.
- **Progressive per-card reveal** (each card appears the moment its own data qualifies, independent of the unified gate) — considered and rejected for v1 in favor of the simpler Hybrid model (D-01). Revisit only if the gated block feels too binary in real use.
- **Hiding empty cards** (vs render-with-hint, D-04) — rejected for layout stability; revisit if the hinted empty cards feel like clutter once the home page is visually polished in Phase 11.
- **Relaxing min-session floors to fill sparse cards** — rejected (D-06/D-07) on integrity grounds; the floors are the point.
- **Drill-down / interactive analytics** (tap a profile card to see the underlying sessions, charts/sparklines) — out of scope; v1 is read-only summary cards. Possible v2.
- **Configurable bucket boundaries / thresholds in admin** — out of scope; the freshness buckets and floors are fixed in v1.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (`todo.match-phase 6` returned 0 matches; the one open todo, "inline add-new-coffee from the brew form," is Phase 4/catalog scope).

</deferred>

---

*Phase: 6-Analytics (Home Page)*
*Context gathered: 2026-05-20*
