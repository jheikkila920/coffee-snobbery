# Deferred Items — Phase 15.1

Items discovered during execution that are outside the scope of the plan that found them.
Do NOT fix these unless assigned to a specific plan.

## From Plan 15.1-01 (Multi-Origin Catalog Refactor) — RESOLVED 2026-05-27

The original executor declared the plan complete while leaving five service files referencing the dropped `Coffee.origin` mapped column. This would have crashed the home page on first load. Resolved by an orchestrator-applied deviation commit immediately after Wave 1 merge, before Wave 2 dispatch.

**Policy applied:**
- **Analytics** (`get_preference_profile`, `get_sweet_spots`) — join `coffee_origins`; a blend session contributes one row per origin (every origin a coffee has counts toward that origin's aggregate).
- **AI recs** (`suggest_recipe`, `alt_brewer_callout`) — origin filter becomes an EXISTS subquery against `coffee_origins`; matches any of the coffee's origins.
- **Display** (`get_unrated_coffees`, `search.run_search`) — origin becomes a correlated `array_to_string(array_agg(country ORDER BY sort_order), ', ')` subquery; renders single-origin coffees as `Ethiopia` and blends as `Ethiopia, Brazil`.

**Files fixed on main (post-merge):**
- `app/services/analytics.py`
- `app/services/ai_service.py`
- `app/services/search.py`

**Validation:** Each surface compiled and executed against the live DB after migrations ran (`SessionLocal()` smoke test).

### test_analytics.py line 503 — RESOLVED (covered by the same fixup)

The `rows[0].origin == "Ethiopia"` assertion now reads the labeled column from `CoffeeOrigin.country` instead of the dropped `Coffee.origin`.
