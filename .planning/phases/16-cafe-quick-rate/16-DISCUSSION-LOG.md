# Phase 16: Cafe Quick-Rate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-27
**Phase:** 16-cafe-quick-rate
**Areas discussed:** Data model & catalog linkage, List view & visual distinction, Entry point for the 20-sec path, AI integration mechanics + cold-start

---

## Data model & catalog linkage

### Q1: Confirm the data-model approach — separate `cafe_logs` table?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — separate cafe_logs table | Research-recommended. Zero impact on brew analytics, AI signature, scheduler. Migration purely additive. | ✓ |
| Revisit unified brew_sessions approach | Would require making brew_sessions.coffee_id nullable (breaks documented invariant) and patching every analytics JOIN with NULL guards. | |
| You decide (defer to planner) | Treat the recommendation as accepted; planner finalizes column types. | |

**User's choice:** Separate `cafe_logs` table.
**Notes:** Confirms STATE.md's open decision in favor of the research recommendation; the unified-table alternatives are architecturally blocked.

### Q2: Brand / roaster on a cafe log

| Option | Description | Selected |
|--------|-------------|----------|
| FK to roasters, create-on-the-fly | Reuses the Phase 4 autocomplete + create-on-the-fly UX. CITEXT UNIQUE collapses casing dupes. Clean GROUP BY in preference derivation. | ✓ |
| Free-text brand column | Faster to type but typos pollute roaster-preference rollups. | |
| Both: FK preferred, free-text fallback | Two columns, slight complexity, best UX. | |

**User's choice:** FK to roasters, create-on-the-fly.
**Notes:** Symmetric with how flavor_notes already works. No free-text fallback at v1.

### Q3: Origin country — FK or free-text?

| Option | Description | Selected |
|--------|-------------|----------|
| Single text column with autocomplete from existing coffee_origins distinct values | No new lookup table; preference query UNIONs cafe.origin_country with coffee_origins.country. | ✓ |
| FK to coffee_origins via a synthetic 'cafe' coffee | Architecturally clean but burns a coffees row per cafe log and confuses the catalog. | |
| Free-text only, no autocomplete | Simplest. Typo risk pollutes origin-preference rollup. | |

**User's choice:** Single text column with autocomplete from existing distinct values.
**Notes:** Avoids creating a countries lookup table for cafe-only use.

### Q4: Flavor notes on a cafe log

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse shared flavor_notes catalog (BIGINT[] GIN-indexed) | Mirrors brew_sessions.flavor_note_ids_observed. Lets get_flavor_descriptors UNION cafe data cleanly. | ✓ |
| Free-text tags column | Faster mobile entry but breaks the analytics integration. | |
| Skip flavor notes at v1.0 of cafe | Defers but partly punts CAFE-04. | |

**User's choice:** Reuse shared flavor_notes catalog.

### Q5: Brew method on a cafe log

| Option | Description | Selected |
|--------|-------------|----------|
| Free-text TEXT column | High variance, low analytics value at v1, mobile-fastest. | ✓ |
| Small enum (espresso/pour-over/immersion/batch/other) | Constrained set; loses information. | |
| FK to a new brew_methods lookup table | Probably over-engineered for v1. | |
| Skip brew_method entirely at v1 | Drops the field. | |

**User's choice:** Free-text TEXT column.

---

## List view & visual distinction

### Q1: Where do cafe logs live in the list view?

| Option | Description | Selected |
|--------|-------------|----------|
| Tab on the existing Sessions page | Same URL family /brew, no new nav slot, survives Phase 17 reshuffle. | ✓ |
| Dedicated /tastings page with new nav slot | Strongest separation but adds nav pressure on the eve of Phase 17. | |
| Combined chronological feed with badge | Smallest footprint but lossy filters. | |
| Section on the Sessions page (one scroll) | No tabs, two sections; cafe scrolls past quickly. | |

**User's choice:** Tab on the existing Sessions page.

### Q2: Visual distinction style

| Option | Description | Selected |
|--------|-------------|----------|
| Border accent + cafe icon | Subtle, mobile-readable, no badge clutter. | ✓ |
| Explicit 'Cafe' badge / pill | Loudest signal; competes with rating + flavor chips. | |
| Different card background tint | Subtle but a11y contrast risk in dark mode. | |
| Same visual — only column ordering hints at type | Minimal differentiation. | |

**User's choice:** Border-l-2 amber accent + cafe-cup icon.

### Q3: Empty state for the Cafe tastings tab

| Option | Description | Selected |
|--------|-------------|----------|
| Friendly hint + primary action button | Mirrors brew-sessions empty-state pattern. | |
| Minimal: blank list | Faster to render, but new users won't know the feature exists. | ✓ |
| Sample entry watermark | Risks looking like a real entry. | |

**User's choice:** Minimal blank list.
**Notes:** Deliberate divergence from Snobbery's other empty-state surfaces. Captured in CONTEXT.md specifics so future contributors don't "helpfully" add hint copy.

---

## Entry point for the 20-sec path

### Q1: Primary entry point for starting a cafe log

| Option | Description | Selected |
|--------|-------------|----------|
| Button on /brew header next to 'Log session' | Two taps from launch; survives Phase 17 nav reshuffle. | ✓ |
| Floating Action Button (FAB) | One-tap entry on the two most-visited pages but introduces a new UI pattern. | |
| Home-page CTA card | One tap from launch but Phase 17 is simplifying home. | |
| Both: header button + home CTA card | Belt-and-suspenders entry; more surface to maintain. | |

**User's choice:** Header button on /brew next to Log session.

### Q2: Form interaction shape

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated /cafe-logs/new page, single scroll | Mirrors /brew/new page-level architecture. | ✓ |
| Inline form-block on the Sessions page | Faster perceived UX but breaks autocomplete + photo upload patterns. | |
| Bottom sheet / modal overlay | Native-mobile feel; new pattern for the app. | |

**User's choice:** Dedicated /cafe-logs/new page.

### Q3: Optional-fields strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Single scrollable page, required fields on top | Mirrors brew form's single-scroll philosophy. | ✓ |
| Two-stage: save quick form then 'Add details?' | Cleanest 20-sec path but two saves = double friction. | |
| Expandable 'More' section, collapsed by default | Compact first paint but extra tap to reach enrichment. | |

**User's choice:** Single scrollable page, required fields on top.

---

## AI integration mechanics + cold-start

### Q1: How do cafe rows extend `compute_input_signature`?

| Option | Description | Selected |
|--------|-------------|----------|
| Append cafe rows as a second list in the same payload | Single SHA256, single signature column. | ✓ |
| Two separate signature segments hashed together | More structured but extra moving parts. | |
| Add a separate cafe_signature column | Most diagnostic but adds storage + scheduler logic. | |

**User's choice:** Append cafe rows as a second list in the same payload.

### Q2: Which preference-profile dimensions do cafe logs feed?

| Option | Description | Selected |
|--------|-------------|----------|
| Origin + roaster only | CAFE-04 spec; flavor descriptors UNION rated-4+ datasets. | ✓ |
| Origin + roaster only, explicitly excluding flavor descriptors | Cleaner separation but loses CAFE-04 flavor-note contribution to visible analytics. | |
| All four dims — require user to estimate process + roast_level | Adds friction to the 20-sec path. | |

**User's choice:** Origin + roaster (with flavor descriptors UNIONed).

### Q3: Does `get_top_coffees` include cafe entries?

| Option | Description | Selected (first pass) | Selected (after pushback) |
|--------|-------------|------------------------|----------------------------|
| No — brew-only list stays as-is | Cafe coffees have no row in coffees; preference satisfied via D-13. | | ✓ |
| Yes — separate 'Top cafe tastings' card | Adds a home card on the eve of Phase 17. | | |
| Synthetic merge — fake a coffees-row equivalent | Identity grouping fragile, tap-target dies, schema mismatch. | ✓ (first pass) | |

**User's first-pass choice:** Synthetic merge.
**Claude pushback:** Flagged five concrete problems (no stable identity to GROUP BY; tap-target dies; card schema mismatch with NULL fields; collides with Phase 17 home simplification; CAFE-04 already satisfied via D-13). Asked to reconsider.
**User's revised choice:** Switch to brew-only.
**Notes:** Cafe contribution to CAFE-04 satisfied by origin/roaster/flavor profile. A future "Top cafe tastings" surface, if wanted, belongs in Phase 17 or Phase 19.

### Q4: Do cafe logs count toward the cold-start gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — cafe + brew count together | (brew_count + cafe_count) >= 3 AND distinct flavor_notes across both >= 5. | ✓ |
| No — cold-start stays brew-only | Conservative; cafe data still feeds derivation once gate is reached. | |
| Hybrid — cafe counts toward flavor-notes only, not session count | Splits the difference. | |

**User's choice:** Cafe + brew count together.

---

## Claude's Discretion

The user deferred the following to the planner (all captured in CONTEXT.md `<decisions>` § Claude's Discretion sections):

- **Data model column shapes (mirroring brew_sessions):** `cafe_name TEXT NOT NULL`, `rating Numeric(3,2) NULL`, `notes Text NOT NULL DEFAULT ''`, `photo_filename TEXT NULL`, `user_id ondelete=RESTRICT`, `logged_at TIMESTAMPTZ NOT NULL DEFAULT now()` editable for backfill, per-user visibility, `(user_id, logged_at DESC)` + GIN(flavor_note_ids) indexing.
- **List view operational details:** per-row Edit/Delete via Phase 15.1 D-21 dual-button pattern; filters = rating + date range only (no brand/origin filters at v1); newest-first sort; mirror Sessions pagination + card-tap behavior.
- **Entry-point operational details:** route shapes (`/cafe-logs/new`, `/cafe-logs/{id}/edit`, POST update, POST `_method=DELETE` for delete); CSRF + photo via existing pipelines; no `brew_drafts`-style autosave at v1; autofocus on `cafe_name`; post-save redirect to `/brew?tab=cafe`.
- **AI implementation tactics:** migration revision shape; UNION SQL shape (CTE vs derived table vs raw UNION ALL); cold-start arithmetic placement (single SQL vs Python sum); tab routing implementation (server-side `?tab=` recommended); Pydantic schema + tests file placement; whether to add structlog audit-log entries (likely no — household audit posture is auth + admin events only).

## Deferred Ideas

Captured in CONTEXT.md `<deferred>`. Highlights:

- "Top cafe tastings" home card / widget — re-pitched in Phase 17 or 19 once cafe coffee identity normalization is solved.
- Cafe logs in global trigram search index — Phase 10 surface expansion deferred.
- CSV import / export for cafe logs — brew CSV stays brew-only.
- Brew method enum / lookup table — defer until an analytics query needs the constrained set.
- Optional process + roast_level fields on cafe logs — defer; friction not worth the dim contribution.
- Bottom-sheet / modal form pattern — Phase 21 mobile rework owns this.
- FAB pattern — Phase 21 mobile rework owns this.
- Home-page CTA card for Quick rate — Phase 17 owns home restructure.
- Server-side autosave-on-blur draft for cafe form — revisit if users report draft loss.
- Optional FK from cafe_logs to coffees catalog when the cafe coffee IS in the household — rejected; mixing identity types complicates queries.
- Separate cafe_logs photos volume — rejected; reuse coffee_snobbery_photos.
- Per-user provenance on roaster autocomplete — rejected; shared catalog last-write-wins per Phase 15.1 D-09.
- Audit-log entries on cafe log mutations — Claude's discretion (likely no).
- Two-stage save ("save quick, then add details") — rejected; single-scroll handles both speeds.
- Inline "add new coffee from brew form" carryover (STATE.md Pending Todos) — re-evaluated as out-of-scope here; cafe quick-rate does not enrich the shared coffee catalog.
