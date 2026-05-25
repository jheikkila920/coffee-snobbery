---
phase: 06-analytics-home-page
reviewed: 2026-05-20T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - app/services/analytics.py
  - app/routers/home.py
  - app/main.py
  - app/templates/pages/home.html
  - app/templates/fragments/home/recent_brews.html
  - app/templates/fragments/home/unrated_coffees.html
  - app/templates/fragments/home/_cold_start.html
  - app/templates/fragments/home/top_coffees.html
  - app/templates/fragments/home/preference_profile.html
  - app/templates/fragments/home/flavor_descriptors.html
  - app/templates/fragments/home/roast_freshness.html
  - app/templates/fragments/home/sweet_spots.html
  - app/templates/fragments/home/_card_sparse.html
  - tests/services/test_analytics.py
  - tests/services/test_analytics_perf.py
  - tests/routers/test_home.py
  - tests/test_phase02_smoke.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-20
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 6 ships the analytics home page: nine read-only SQL derivations in
`analytics.py`, the `/` shell + eight `/home/cards/*` fragment endpoints in
`home.py`, the shell + fragment templates, and three test modules.

**The top security concern — per-user data isolation — passes review.** Every
rating-dependent derivation (`get_top_coffees`, `get_preference_profile`,
`get_flavor_descriptors`, `get_roast_freshness_buckets`, `get_sweet_spots`,
`get_recent_brews`, `compute_input_signature`) and both gate-count queries
filter `BrewSession.user_id == user_id` as the first WHERE predicate.
`get_unrated_coffees` returns shared-catalog `coffees` rows (correct per the
CLAUDE.md "coffees are household-shared" invariant) and scopes only the
"already-brewed" exclusion subquery to `user_id`. No query lets one household
member read another's brew log.

**Other security checks pass:**
- Every handler in `home.py` is gated by `Depends(require_user)`; `user_id` is
  always read from `user.id` (the injected `require_user` return), never a query
  param. The 401-on-anon path is covered by tests.
- The two `text()` derivations (HOME-03 unnest, cold-start note count) use the
  bound `:user_id` parameter — no string interpolation of user input. No SQL
  injection surface.
- No `|safe`, no inline `hx-on:`/`onclick`/`innerHTML` in any template; Jinja
  autoescape protects coffee names, roaster names, flavor descriptors, origin,
  process, and recipe/brewer names. CSP-clean.
- Roast-freshness reads `Bag.roast_date` (joined via `BrewSession.bag_id`),
  never `Coffee.roast_date` (which does not exist) — Pitfall 4 respected.
- Scope guard holds: the sweet-spots card has no AI placeholder, and `home.html`
  exposes the Phase 7 slot only as a Jinja `{# ... #}` comment, not a live
  trigger. `compute_input_signature` exists but is not wired into any Phase 6
  response path.

The findings below are correctness edge cases and quality defects — none are
shipping blockers, but two (WR-01, WR-02) can produce misleading insights and
should be fixed.

## Warnings

### WR-01: Cold-start gate counts flavor-note IDs that may not reference real flavor notes

**File:** `app/services/analytics.py:333-343` (and contrast with `:148-162`)
**Issue:** `get_cold_start_counts` computes `distinct_notes` with a raw
`count(DISTINCT note_id)` over `unnest(bs.flavor_note_ids_observed)` and **no
join to `flavor_notes`**. `get_flavor_descriptors` (the card the gate unlocks)
**does** `JOIN flavor_notes fn ON fn.id = note_id`, so it silently drops any
observed ID that no longer references a live flavor note. `flavor_note_ids_observed`
is a `BIGINT[]` with no FK constraint, so stale/dangling IDs are possible (e.g. a
flavor note deleted after a session referenced it). Result: the gate can open on
5 "distinct notes" that include dangling IDs, then the flavor-descriptors card
renders the sparse hint because the JOIN filtered those IDs out — the user clears
the gate but the card it gates is empty. The test seed even uses
`flavor_note_ids_observed=[1, 2]` with arbitrary IDs (`test_analytics.py:267`),
confirming the gate counts IDs regardless of FK validity.
**Fix:** Make the gate count consistent with the descriptor card by joining to
`flavor_notes` so only live notes count toward the threshold:
```python
note_count_row = db.execute(
    text(
        """
        SELECT count(DISTINCT note_id) AS cnt
        FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
        JOIN flavor_notes fn ON fn.id = note_id
        WHERE bs.user_id = :user_id
        """
    ),
    {"user_id": user_id},
).first()
```

### WR-02: Roast-freshness buckets silently absorb sessions brewed before the roast date

**File:** `app/services/analytics.py:177-185`
**Issue:** `days_expr = cast(BrewSession.brewed_at, SaDate) - Bag.roast_date`
can be negative when a session's `brewed_at` predates the bag's `roast_date`
(a plausible data-entry error — wrong roast date, or backdated brew). The
`case` chain's first arm is `days_expr <= 3`, so any negative day-count is
bucketed into "0-3 days" alongside genuinely fresh brews, inflating the
"freshest" bucket's session count and average rating. Since the freshness card
is one of the home page's headline insights, a few bad rows skew it.
**Fix:** Add a lower-bound guard so negative-day rows are excluded (or routed to
an explicit "invalid" path you choose not to render):
```python
.where(
    BrewSession.user_id == user_id,
    BrewSession.rating.is_not(None),
    Bag.roast_date.is_not(None),
    days_expr >= 0,  # exclude brews dated before the roast date
)
```

### WR-03: `cast(brewed_at, Date)` in freshness is session-timezone dependent

**File:** `app/services/analytics.py:177`
**Issue:** `brewed_at` is `TIMESTAMP(timezone=True)`. Casting a `timestamptz`
to `date` in Postgres uses the connection's `TimeZone` setting, so a brew
logged near midnight UTC can land on a different calendar day than the user
intended, shifting the day-count by 1 and occasionally moving a session across
a bucket boundary (e.g. day 3 vs day 4). The app is reverse-proxy aware and
makes no guarantee about the DB session timezone, so the bucket math is not
fully deterministic across deployments.
**Fix:** Cast in an explicit zone, e.g.
`cast(func.timezone('UTC', BrewSession.brewed_at), SaDate)` (or whatever zone
the household logs in), so the day-count is stable regardless of the server's
`TimeZone` GUC. Document the chosen zone next to `days_expr`.

### WR-04: `<div>` elements are direct children of `<ul>` in three card fragments

**File:** `app/templates/fragments/home/top_coffees.html:7-9`,
`app/templates/fragments/home/roast_freshness.html:8-10`,
`app/templates/fragments/home/sweet_spots.html:8-10`
**Issue:** These fragments open a `<ul>` and then place `<div>` rows directly
inside it inside the `{% for %}`. The only valid children of `<ul>` are `<li>`,
`<script>`, and `<template>`. Browsers will reparent or render the `<div>`s
unpredictably, and it breaks list semantics for screen readers (the `<ul>`
announces "list, 0 items"). `recent_brews.html` and `unrated_coffees.html`
correctly use `<li>`, so this is an inconsistency, not a pattern.
**Fix:** Change each row wrapper from `<div ...>` to `<li ...>` (and the closing
tag), or drop the `<ul>` wrapper if a list is not desired. Example for
`top_coffees.html`:
```html
<ul class="space-y-2">
  {% for row in rows %}
    <li class="flex items-baseline justify-between gap-4 border-b ...">
      ...
    </li>
  {% endfor %}
</ul>
```

## Info

### IN-01: `test_signature_order_independent` does not test order independence

**File:** `tests/services/test_analytics.py:641-655`
**Issue:** The test name and docstring claim it verifies order independence
(Pitfall 5), but it only calls `compute_input_signature` twice against the same
unchanged DB state and asserts equality — identical to
`test_signature_determinism`. It never inserts rows in a different physical order
to prove the `ORDER BY BrewSession.id` actually normalizes ordering. The
order-independence guarantee is therefore untested.
**Fix:** Seed two users whose equivalent sessions are inserted in different
orders (or insert, delete, and re-insert to perturb physical row order) and
assert their signatures match after normalizing the per-user IDs out — or rename
the test to `test_signature_stable_across_calls` so it doesn't overclaim.

### IN-02: Roaster dimension query is duplicated instead of reusing `_dim_query`

**File:** `app/services/analytics.py:106-129`
**Issue:** `get_preference_profile` defines a reusable `_dim_query` helper for
origin/process/roast_level, then hand-writes a near-identical 16-line
`roaster_stmt` solely to add the `JOIN Roaster`. The duplication risks the two
paths drifting (e.g. a future change to the `having` floor applied to one but
not the other).
**Fix:** Extend `_dim_query` to accept an optional extra join, or pass the label
column + an optional join target so all four dimensions flow through one builder.
Minor — leave as-is if the explicitness is preferred, but note the drift risk.

### IN-03: `clean_home_router` omits the `sessions` table that `clean_analytics` cleans

**File:** `tests/routers/test_home.py:119-141`
**Issue:** `clean_home_router` deletes `users` with the test prefixes but does
not explicitly delete their `sessions` rows first, unlike `clean_analytics`
(`test_analytics.py:358-364`). This happens to be safe because
`sessions.user_id` is `ondelete="CASCADE"` (verified in `app/models/session.py`),
so the user delete cascades. Not a failure — but it is a latent inconsistency
between two fixtures that wipe overlapping data; if the FK ever changes to
`RESTRICT`, this fixture breaks while the other survives.
**Fix:** Add `DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE
username LIKE 'hometest-%' OR username LIKE 'analyticstest-%')` before the user
delete for parity, or leave a comment noting the CASCADE reliance.

---

_Reviewed: 2026-05-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
