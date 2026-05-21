# Phase 6: Analytics (Home Page) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 6-Analytics (Home Page)
**Areas discussed:** Cold-start gating, Sparse-card states, Min-session floors, Signature composition

---

## Cold-start gating

### Gate model

| Option | Description | Selected |
|--------|-------------|----------|
| All-or-nothing | Entire analytics view replaced by one empty state + progress meter until the gate clears. One counts query decides the whole page. | |
| Hybrid | Always show recent brews + unrated coffees (no rating/aggregation needed); gate only the aggregate cards behind the meter. | ✓ |
| Progressive reveal | Each card renders the moment ITS own data qualifies; slim progress hint until fully unlocked. | |

**User's choice:** Hybrid
**Notes:** Recent brews + unrated coffees always visible; the five aggregate cards (top coffees, profile, descriptors, freshness, sweet spots) gate behind the meter.

### Unlock threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Sessions-only: ≥3 sessions | Only HOME-03 needs flavor notes; looser gate = value sooner. Refines the ROADMAP success criterion. | |
| Same as AI gate | ≥3 sessions AND ≥5 distinct observed notes. One unified threshold; matches ROADMAP success criterion 4 as written. | ✓ |

**User's choice:** Same as AI gate
**Notes:** Keeps analytics unlock and AI unlock as a single mental model (≥3 sessions AND ≥5 distinct notes).

### Progress meter

| Option | Description | Selected |
|--------|-------------|----------|
| Dynamic remaining counts | "Log 2 more brews and add 3 more flavor notes to unlock recommendations." Computed from actuals. | ✓ |
| Static checklist | Two ticking checkboxes (3 brews / 5 notes). | |
| Single progress bar | One bar to 100% combining both criteria. | |

**User's choice:** Dynamic remaining counts
**Notes:** Exact ROADMAP example copy; most motivating.

---

## Sparse-card states

### Empty-card behavior (past gate)

| Option | Description | Selected |
|--------|-------------|----------|
| Render with a short hint | Card stays in place with e.g. "No coffee with 2+ sessions yet — keep logging." Uniform across cards. | ✓ |
| Hide the card entirely | Empty cards disappear; cleaner but layout shifts and no explanation. | |
| Hint, but hide pure to-do cards | Aggregate cards hint; unrated-coffees hides when empty. | |

**User's choice:** Render with a short hint
**Notes:** Uniform across all aggregate cards; stable layout, teaches each card's threshold.

### All-unrated case (rating is nullable)

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct "rate your brews" nudge | Rating-dependent cards detect the all-unrated case and say "Rate some brews to see this." More actionable. | ✓ |
| Generic empty hint | Same "not enough data" hint regardless of cause. One code path. | |

**User's choice:** Distinct "rate your brews" nudge
**Notes:** A user can clear the gate (≥3 sessions, ≥5 notes) with zero ratings; rating-based cards distinguish that cause.

---

## Min-session floors

### Preference-profile floor

| Option | Description | Selected |
|--------|-------------|----------|
| Min 2 per bucket | A dimension value needs ≥2 of the user's sessions to appear. Mirrors HOME-01. | ✓ |
| Min 3 per bucket | Stricter; mirrors HOME-05 sweet-spots floor. | |
| No floor — show all | Every value with ≥1 rated session appears; a single great cup can dominate. | |

**User's choice:** Min 2 per bucket
**Notes:** Filters one-off noise without hiding too much at household scale.

### Uniformity across cards

| Option | Description | Selected |
|--------|-------------|----------|
| Uniform across all three | Freshness bucket needs ≥floor rated sessions; a descriptor must appear in ≥floor of the 4.0+ sessions. | ✓ |
| Freshness yes, descriptors no | Floor on freshness; descriptors stay pure frequency ranking. | |
| You decide per card | Planner picks per card. | |

**User's choice:** Uniform across all three
**Notes:** Min-2 applied uniformly to preference profile, freshness buckets, and flavor descriptors.

---

## Signature composition

### Hash inputs

| Option | Description | Selected |
|--------|-------------|----------|
| Per-session AI input fields | Hash (coffee_id, rating, sorted flavor_note_ids_observed, recipe_id, brewer_id, bag roast_date); excludes notes + edit timestamps. | ✓ |
| Coarse row-version | session count + max(updated_at) + distinct-note count. Over-sensitive (notes typo invalidates). | |
| All brew columns except notes | Captures dose/water/temp/grind too; most sensitive precise option. | |

**User's choice:** Per-session AI input fields
**Notes:** Signature changes exactly when a recommendation-relevant input changes; a notes typo-fix never invalidates. COST-4: scope is the user's own sessions only.

### Unrated sessions

| Option | Description | Selected |
|--------|-------------|----------|
| No — only rated sessions count | Unrated sessions invisible to the signature until rated. Every AI-consumed derivation is rating-gated. Cost-optimal + correct. | ✓ |
| Yes — any add/remove counts | Any session shifts the signature regardless of rating; can regen on a half-logged brew. | |

**User's choice:** No — only rated sessions count
**Notes:** Distinct from the cold-start unlock (D-02), which uses LIVE counts and DOES count unrated sessions toward ≥3.

---

## Claude's Discretion

- Home route location + page composition (recommend dedicated `app/routers/home.py` replacing the Phase 0 placeholder).
- Fragment endpoint shape (recommend per-card endpoints for independent staggering).
- Card ordering / prominence (mobile-first; UI-SPEC pass optional).
- Tie-breaking within ranked cards (recommend avg rating DESC, session count DESC, recency).
- Signature serialization + hash algorithm (recommend deterministic ordering + sha256 hex).
- `compute_input_signature` return for zero-rated-session users (recommend stable empty-set sentinel).
- Additional analytics indexes only if a query's p95 exceeds the <50ms budget.

## Deferred Ideas

- HOME-06 AI prose under Sweet Spots → Phase 7.
- Progressive per-card reveal → rejected for v1 in favor of Hybrid.
- Hiding empty cards → rejected for layout stability.
- Relaxing min-session floors → rejected on integrity grounds.
- Drill-down / interactive analytics, charts/sparklines → v2.
- Admin-configurable bucket boundaries / thresholds → out of scope v1.
