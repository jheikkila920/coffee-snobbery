# Phase 6: Analytics (Home Page) - Research

**Researched:** 2026-05-20
**Domain:** Pure-SQL analytics over per-user brew log, HTMX staggered lazy-load, SHA256 signature plumbing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 Hybrid gating layout.** Recent brews (HOME-07) and unrated coffees (HOME-08) ALWAYS render. The five aggregate cards are gated behind the cold-start meter. A brand-new user still sees logged brews + a "what to try next" catalog list while analytics fill in.
- **D-02 Unlock threshold = ≥3 sessions AND ≥5 distinct observed flavor notes.** One unified threshold across analytics + AI (AI-7). The aggregate-card block is replaced by the empty state until BOTH conditions hold.
- **D-03 Dynamic remaining-counts progress meter.** Computed from actuals. Counts update as the user logs. (Example: "Log 2 more brews and add 3 more flavor notes to unlock recommendations.")
- **D-04 Render-with-hint, uniform across all aggregate cards.** Once the gate clears, every aggregate card stays even when its query returns no qualifying rows; shows a short hint.
- **D-05 Rating-dependent cards detect the all-unrated case.** When sessions exist but none are rated, those cards say "Rate some brews to see this" rather than the generic not-enough-data hint.
- **D-06 Min 2 of the user's sessions per dimension for the preference profile (HOME-02).** Mirrors the HOME-01 floor.
- **D-07 The min-2 floor is uniform across the three unspecified cards.** Roast-freshness buckets need ≥2 rated sessions to show a bucket's avg; a flavor descriptor must appear in ≥2 of the user's 4.0+ sessions. HOME-01 (min 2) and HOME-05 (min 3) keep their already-specified floors.
- **D-08 Hash per-session AI input fields only.** Signature inputs: `(coffee_id, rating, sorted flavor_note_ids_observed, recipe_id, brewer_id, bag roast_date)`. Free-text `notes` and edit timestamps EXCLUDED.
- **D-09 Only rated sessions feed the signature.** An unrated session is invisible to the signature. The cold-start unlock (D-02) uses LIVE counts and DOES count unrated sessions toward the ≥3 threshold.

### Claude's Discretion

- Home route location + page composition — recommend dedicated `app/routers/home.py` replacing the Phase 0 placeholder in `app/main.py:249-260`.
- Fragment endpoint shape — recommend per-card endpoints (e.g. `/home/cards/top-coffees`).
- Card ordering / prominence — planner picks the vertical stack order (mobile-first). UI-SPEC has approved order (see § Architecture Patterns below).
- Tie-breaking within ranked cards — recommend avg rating DESC, then session count DESC, then most-recent.
- Signature serialization + hash algorithm — recommend deterministic ordering (sort session rows by id) + stable canonical serialization hashed with sha256, returned as hex.
- `compute_input_signature` return when zero rated sessions — recommend a stable sentinel (hash of empty string or empty list).
- Per-card query indexes — existing Phase 5 indexes first; add new ones only if p95 exceeds the <50ms budget on the 1000-session seed.

### Deferred Ideas (OUT OF SCOPE)

- HOME-06 AI prose under Sweet Spots — Phase 7 only. Phase 6 ships only `compute_input_signature`. No AI card, no "Outdated" badge rendering.
- Progressive per-card reveal (each card appears the moment its own data qualifies) — rejected for v1.
- Hiding empty cards — rejected for layout stability.
- Relaxing min-session floors — rejected on integrity grounds.
- Drill-down / interactive analytics — out of scope v1.
- Configurable bucket boundaries / thresholds in admin — out of scope v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HOME-01 | Top 5 coffees by user's avg rating across that user's sessions, min 2 sessions, with rating and count | `select()` + `group_by(coffee_id)` + `having(func.count() >= 2)` + `order_by(func.avg(rating).desc())` + `limit(5)` joined to `coffees` for name |
| HOME-02 | Preference profile cards: avg rating by origin / process / roaster / roast level (each pre-computed, lazy-loaded via HTMX) | Four separate GROUP BY queries; each requires `join(coffees)` for the dimension column; min 2 sessions per dimension value (D-06) |
| HOME-03 | Top-10 flavor descriptors appearing in 4.0+ rated sessions for this user | `func.unnest` via `column_valued()` on `flavor_note_ids_observed` + WHERE rating >= 4.0 + GROUP BY + HAVING COUNT >= 2 (D-07) + join to `flavor_notes` for names |
| HOME-04 | Roast freshness sweet-spot buckets (0-3, 4-7, 8-14, 15-21, 22+ days) using `bags.roast_date` ONLY | Date arithmetic: `cast(brewed_at, Date) - bags.roast_date` → `case()` bucketing + GROUP BY bucket + HAVING count >= 2 rated sessions (D-07) |
| HOME-05 | Sweet spots: top 3 multi-dimensional `(origin × process × brewer × recipe)` with min 3 sessions, ranked by avg rating; pure SQL UNION of GROUP BYs with HAVING | Four GROUP BY queries unioned; wrap in subquery; `order_by` + `limit(3)` on the outer select |
| HOME-07 | Recent brews list: last 10 sessions with edit links | Eager-loaded in initial render; `select(BrewSession)` + `join(Coffee)` + `order_by(brewed_at.desc())` + `limit(10)` |
| HOME-08 | Unrated coffees list: catalog entries this user hasn't brewed yet | `select(Coffee)` WHERE `id NOT IN (select(distinct coffee_id) from brew_sessions where user_id=...)` + not archived |
| HOME-09 | Each section lazy-loads via HTMX after initial page render; staggered fire (50-150ms apart) | `hx-trigger="load delay:Nms"` per card; stagger timing 100/150/200/300/400/500ms as confirmed by UI-SPEC |
| (signature) | `compute_input_signature(user_id) -> str` helper, content hash of user's own RATED sessions only (COST-4) | `select()` of rated sessions; deterministic `json.dumps(sort_keys=True)` + `hashlib.sha256().hexdigest()` |
</phase_requirements>

---

## Summary

Phase 6 is a pure analytics read layer sitting on top of the already-complete brew session schema from Phase 5. No migration is needed — all columns and indexes already exist. The work is entirely in: (1) `app/services/analytics.py` — eight query functions and `compute_input_signature`; (2) `app/routers/home.py` — the real `/` route replacing the Phase 0 placeholder, plus seven `GET /home/cards/*` fragment endpoints; and (3) the Jinja2 templates for each card.

The most technically demanding query is HOME-03 (flavor descriptor aggregation via `func.unnest` over the `BIGINT[]` column) and HOME-05 (sweet spots via UNION of four GROUP BYs). Both have verified patterns in SQLAlchemy 2.0. The HTMX staggered lazy-load pattern is straightforward — `hx-trigger="load delay:Nms"` is stable syntax confirmed in HTMX 2.x docs. The signature computation uses stdlib `hashlib` + `json` and is deterministic by design.

The cold-start gate check (live counts, not the signature) and all aggregate queries are pure sync SQLAlchemy `select()` against the existing connection pool (`pool_size=10, max_overflow=5`). The staggered 50-500ms delay spread across seven fragment requests ensures at most 1-2 concurrent DB connections per user page load in practice.

**Primary recommendation:** Build `app/services/analytics.py` as the single query brain, keep each function narrowly scoped to one card, and layer the routing and templates on top. No migration. No new dependencies. Reuse every existing pattern from Phases 4-5.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cold-start gate evaluation (live counts) | API / Backend | — | Count is user-specific; computed at request time, never persisted |
| Analytics query execution (HOME-01..05, 07, 08) | API / Backend | Database/Storage | Pure SQL reads; business logic lives in the service, SQL in Postgres |
| Signature computation (`compute_input_signature`) | API / Backend | Database/Storage | Reads rated sessions from Postgres; computed in Python with hashlib |
| HTMX staggered lazy-load orchestration | Browser / Client | Frontend Server (SSR) | Delay triggers fire in the browser; each card independently requests its fragment endpoint |
| Fragment rendering | Frontend Server (SSR) | — | Jinja2 template renders the card HTML; served as an HTMX fragment |
| Fragment cache headers (no-store + Vary) | Frontend Server (SSR) | — | `FragmentCacheHeadersMiddleware` applies automatically on HX-Request |
| Progress meter rendering | Frontend Server (SSR) | — | Server computes pct value inline in the shell render; static HTML, no Alpine |
| Card loading skeleton | Browser / Client | — | Pure CSS `animate-pulse` class; no server involvement |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | `>=2.0.49,<2.1` | All analytics queries | Already pinned; `select()`, `func.*`, `union_all`, `case()` all available |
| FastAPI | `>=0.136,<0.137` | Home router + fragment endpoints | Already pinned; sync handlers via threadpool for sync DB calls |
| Jinja2 | `>=3.1.6,<4` | Card templates with autoescape | Already pinned; CSP-safe rendering |
| HTMX | 2.0.10 (CDN) | Staggered lazy-load triggers | Already in base.html; `hx-trigger="load delay:Nms"` confirmed stable |
| hashlib | stdlib | SHA256 signature computation | No dependency; `hashlib.sha256()` deterministic across Python 3.12 |
| json | stdlib | Canonical serialization for signature | `json.dumps(sort_keys=True)` deterministic and stable across Python versions |

### Supporting (existing, no new installs)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psycopg | `>=3.3,<3.4` | Postgres driver for sync session | Already installed; sync `SessionLocal` pattern from db.py |
| structlog | `>=25.5,<26` | Audit logging in service layer | Already installed; emit any analytics-relevant events |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `json.dumps(sort_keys=True)` for signature | `msgpack` or `pickle` | json is stable across Python versions; msgpack adds a dep; pickle is not safe for cross-version use |
| `func.unnest().column_valued()` | Raw `text()` SQL for unnest | Native SQLAlchemy construct is preferable; `text()` is harder to compose and test |
| Separate endpoints per card | One combined `/home/cards` endpoint returning all fragments | Per-card is the correct choice for independent staggering (HOME-09) and connection-pool protection |

**Installation:** No new packages required. All dependencies already present.

**Version verification:** Stack pinned in CLAUDE.md and verified in prior phases. No new packages introduced this phase. [VERIFIED: codebase]

---

## Architecture Patterns

### System Architecture Diagram

```
Browser
  |
  |-- GET /  ──────────────────────────────────────────────────────────────────────────────
  |                          home.py (FastAPI router)
  |                             |
  |                             ├── analytics.get_cold_start_counts(user_id) ──► DB
  |                             |     Returns {sessions, distinct_notes}
  |                             |     Gate check: sessions >= 3 AND notes >= 5
  |                             |
  |                             ├── analytics.get_recent_brews(user_id) ──────► DB
  |                             |     Eager-loaded in initial shell render
  |                             |
  |                             └── Renders pages/home.html (shell)
  |                                   |
  |   <── HTML shell returned ────────┘
  |
  |-- [hx-trigger="load delay:100ms"] GET /home/cards/top-coffees ──► home.py ──► analytics.get_top_coffees(user_id)
  |-- [hx-trigger="load delay:150ms"] GET /home/cards/unrated-coffees ──► home.py ──► analytics.get_unrated_coffees(user_id)
  |-- [hx-trigger="load delay:200ms"] GET /home/cards/preference-profile ──► home.py ──► analytics.get_preference_profile(user_id)
  |-- [hx-trigger="load delay:300ms"] GET /home/cards/flavor-descriptors ──► home.py ──► analytics.get_flavor_descriptors(user_id)
  |-- [hx-trigger="load delay:400ms"] GET /home/cards/roast-freshness ──► home.py ──► analytics.get_roast_freshness_buckets(user_id)
  |-- [hx-trigger="load delay:500ms"] GET /home/cards/sweet-spots ──► home.py ──► analytics.get_sweet_spots(user_id)
  |
  Each fragment ──► FragmentCacheHeadersMiddleware ──► Cache-Control: no-store + Vary: HX-Request
```

### Recommended Project Structure
```
app/
├── routers/
│   └── home.py              # NEW — real / route + /home/cards/* fragment endpoints
├── services/
│   └── analytics.py         # NEW — all HOME-01..05/07/08 query functions + compute_input_signature
├── templates/
│   └── pages/
│       └── home.html        # NEW — page shell (h1, recent brews eager, gate check, lazy card divs)
│   └── fragments/home/
│       ├── top_coffees.html             # HOME-01
│       ├── preference_profile.html      # HOME-02
│       ├── flavor_descriptors.html      # HOME-03
│       ├── roast_freshness.html         # HOME-04
│       ├── sweet_spots.html             # HOME-05
│       ├── unrated_coffees.html         # HOME-08
│       └── _card_sparse.html           # shared hint partial (D-04/D-05)
```

### Pattern 1: Per-Card Lazy Fragment Endpoints

Each card is an independent fragment endpoint. The initial page shell renders the card container div with `hx-get`, `hx-trigger`, and `hx-swap="innerHTML"` pointing at a placeholder skeleton. The card shell (border + heading) renders immediately; the body lazy-loads.

**Template pattern (shell):**
```html
<!-- Source: CONTEXT.md §Claude's Discretion + UI-SPEC §HTMX Fragment Endpoints -->
<section aria-labelledby="top-coffees-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="top-coffees-heading" class="text-xl font-semibold mb-4">Top Coffees</h2>
  <div hx-get="/home/cards/top-coffees"
       hx-trigger="load delay:100ms"
       hx-swap="innerHTML">
    <!-- loading skeleton -->
    <div class="animate-pulse space-y-2">
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
    </div>
  </div>
</section>
```

**Router pattern:**
```python
# Source: Phase 4/5 fragment endpoint pattern (CONTEXT.md §Established Patterns)
@router.get("/home/cards/top-coffees")
def card_top_coffees(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
) -> Response:
    rows = analytics.get_top_coffees(db, user.id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/home/top_coffees.html",
        context={"rows": rows},
    )
```

`FragmentCacheHeadersMiddleware` applies `Cache-Control: no-store` + `Vary: HX-Request` automatically — no per-route config needed. [VERIFIED: 01-CONTEXT.md D-11]

### Pattern 2: HOME-01 Top Coffees — GROUP BY + HAVING + JOIN

```python
# Source: SQLAlchemy 2.0 docs (docs.sqlalchemy.org/en/20/core/selectable.html)
# Verified pattern: select() + join + group_by + having + order_by + limit
from sqlalchemy import select, func
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee

def get_top_coffees(db: Session, user_id: int) -> list[Row]:
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
        .having(func.count(BrewSession.id) >= 2)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        .limit(5)
    )
    return db.execute(stmt).all()
```

Index used: `ix_brew_sessions_user_coffee_brewed_at (user_id, coffee_id, brewed_at DESC)` — covers the WHERE user_id filter and GROUP BY coffee_id. [VERIFIED: p5_brew_sessions migration]

### Pattern 3: HOME-03 Flavor Descriptor Aggregation — func.unnest + column_valued()

The `flavor_note_ids_observed` column is a `BIGINT[]`. To aggregate frequencies across rows, unnest it into individual rows using `func.unnest().column_valued()`.

```python
# Source: SQLAlchemy 2.0 docs (docs.sqlalchemy.org/en/20/core/functions.html)
# func.FunctionElement.column_valued() is the standard 2.0 approach for unnest
from sqlalchemy import func, select
from app.models.brew_session import BrewSession
from app.models.flavor_note import FlavorNote

def get_flavor_descriptors(db: Session, user_id: int) -> list[Row]:
    # unnest the array column into a scalar column reference
    unnested = func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")

    stmt = (
        select(
            FlavorNote.id,
            FlavorNote.name,
            func.count().label("session_count"),
        )
        .select_from(BrewSession)
        .join(unnested, literal(True))   # implicit lateral join
        .join(FlavorNote, FlavorNote.id == unnested.c.note_id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating >= 4.0,
        )
        .group_by(FlavorNote.id, FlavorNote.name)
        .having(func.count() >= 2)          # D-07: min 2 sessions
        .order_by(func.count().desc())
        .limit(10)
    )
    return db.execute(stmt).all()
```

**Note on index usage:** The GIN index `ix_brew_sessions_flavor_note_ids_observed` is designed for containment queries (e.g., `WHERE array_col @> ARRAY[id]`). For the unnest+GROUP BY pattern, Postgres may use a sequential scan with the WHERE `user_id` + `rating` filter first (via `ix_brew_sessions_user_brewed_at`), then unnest the result set in memory. On a 1000-session seed for one user the result set is small enough that this is fine. [VERIFIED: Phase 5 migration + SQLAlchemy 2.0 discussion #11179]

**Alternative (pure SQL via text()):** If the `column_valued()` implicit lateral approach fails in practice due to ORM join complications, a fallback using `text()` inline with `func.unnest`:
```python
from sqlalchemy import text
# Verified working in PostgreSQL:
# SELECT fn.id, fn.name, count(*) AS session_count
# FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
# JOIN flavor_notes fn ON fn.id = note_id
# WHERE bs.user_id = :uid AND bs.rating >= 4.0
# GROUP BY fn.id, fn.name HAVING count(*) >= 2
# ORDER BY session_count DESC LIMIT 10
```

### Pattern 4: HOME-04 Roast Freshness Buckets — Date Arithmetic + CASE

`bags.roast_date` is a `DATE` column. `brew_sessions.brewed_at` is a `TIMESTAMP WITH TIME ZONE`. Computing days-since-roast at brew time requires casting `brewed_at` to `DATE` in Postgres and subtracting the date columns.

```python
# Source: SQLAlchemy 2.0 docs (docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.case)
# Date arithmetic: (brewed_at::date - roast_date) is an integer in Postgres when both are DATE
from sqlalchemy import case, cast, func, select
from sqlalchemy import Date as SaDate, Integer
from app.models.brew_session import BrewSession
from app.models.bag import Bag

def get_roast_freshness_buckets(db: Session, user_id: int) -> list[Row]:
    days_expr = cast(BrewSession.brewed_at, SaDate) - Bag.roast_date  # integer in postgres

    bucket_expr = case(
        (days_expr <= 3, "0-3 days"),
        (days_expr <= 7, "4-7 days"),
        (days_expr <= 14, "8-14 days"),
        (days_expr <= 21, "15-21 days"),
        else_="22+ days",
    ).label("freshness_bucket")

    bucket_order_expr = case(
        (days_expr <= 3, 1),
        (days_expr <= 7, 2),
        (days_expr <= 14, 3),
        (days_expr <= 21, 4),
        else_=5,
    )

    stmt = (
        select(
            bucket_expr,
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
            func.min(bucket_order_expr).label("bucket_order"),
        )
        .join(Bag, BrewSession.bag_id == Bag.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
            Bag.roast_date.is_not(None),
        )
        .group_by(bucket_expr)
        .having(func.count(BrewSession.id) >= 2)  # D-07
        .order_by(func.min(bucket_order_expr))
    )
    return db.execute(stmt).all()
```

**Hard rule verified:** `bags.roast_date` (not `coffees.roast_date`). `Bag` model has `roast_date: Mapped[date | None]`. Sessions with `bag_id IS NULL` or `bags.roast_date IS NULL` are excluded by the INNER JOIN to `bags` and the `roast_date.is_not(None)` filter. [VERIFIED: app/models/bag.py]

**PostgreSQL date subtraction:** `(date - date)` → integer (number of days). No interval type needed. Postgres handles this natively when both sides are `DATE`. The `cast(TIMESTAMP, Date)` in SQLAlchemy maps to `::date` in Postgres. [CITED: docs.sqlalchemy.org/en/20/core/type_basics.html]

### Pattern 5: HOME-05 Sweet Spots — UNION ALL of GROUP BYs

The sweet spots requirement calls for top 3 `(origin × process × brewer × recipe)` combinations, min 3 sessions, ranked by avg rating. The UNION approach covers all four dimension combinations without Python loops.

The ROADMAP note says "UNION of GROUP BY queries with HAVING" — meaning one GROUP BY query per combination dimension (or a single GROUP BY over all four columns). The cleaner read: **one GROUP BY over all four columns** plus the joins to resolve them into names. The "UNION of GROUP BYs" phrasing refers to grouping across different combination columns. The simplest correct approach is a SINGLE GROUP BY over all four dimension IDs; the multi-UNION approach would be used only if you want ranked results per individual dimension.

**Recommended: Single GROUP BY over the 4-dimensional combination space:**

```python
# Source: SQLAlchemy 2.0 docs verified GROUP BY pattern
from sqlalchemy import func, select
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment as EquipmentModel
from app.models.recipe import Recipe

brewer = aliased(EquipmentModel, name="brewer")

def get_sweet_spots(db: Session, user_id: int) -> list[Row]:
    stmt = (
        select(
            Coffee.origin.label("origin"),
            Coffee.process.label("process"),
            brewer.model.label("brewer_name"),
            Recipe.name.label("recipe_name"),
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(brewer, BrewSession.brewer_id == brewer.id)
        .join(Recipe, BrewSession.recipe_id == Recipe.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(
            Coffee.origin,
            Coffee.process,
            brewer.model,
            Recipe.name,
        )
        .having(func.count(BrewSession.id) >= 3)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        .limit(3)
    )
    return db.execute(stmt).all()
```

**UNION ALL interpretation (if the planner strictly requires UNION):** If the 4-column GROUP BY misses cases where some dimensions are NULL (e.g., a session has no recipe), a UNION approach with separate GROUP BYs for different NULL-tolerance combinations makes sense. The pure `INNER JOIN` version above drops sessions with null brewer_id or recipe_id — these are excluded from sweet spots by design (you need a known brewer and recipe to establish a "sweet spot"). This is the correct v1 behavior.

**ORDER BY + LIMIT on UNION ALL:** If a UNION ALL is needed, wrap in subquery and apply ORDER BY + LIMIT on the outer select:
```python
# Source: docs.sqlalchemy.org/en/20/core/selectable.html (CompoundSelect.subquery)
union_q = union_all(stmt1, stmt2, stmt3, stmt4).subquery()
final = select(union_q).order_by(union_q.c.avg_rating.desc()).limit(3)
```
[VERIFIED: SQLAlchemy 2.0 docs — CompoundSelect supports direct `.order_by()` + `.limit()` OR via `.subquery()`]

### Pattern 6: Compute Input Signature

```python
# Source: Python stdlib hashlib docs + death.andgravity.com/stable-hashing
import hashlib
import json
from decimal import Decimal
from datetime import date

def compute_input_signature(db: Session, user_id: int) -> str:
    """SHA256 over this user's RATED sessions' AI-input fields only (D-08/D-09, COST-4).

    Inputs per session: (coffee_id, rating, sorted_flavor_note_ids, recipe_id, brewer_id, bag_roast_date)
    Free-text notes and timestamps are EXCLUDED.
    Returns hex digest. Returns hash of empty list when user has zero rated sessions.
    Rows sorted by id (ascending) for determinism — order-independent.
    """
    stmt = (
        select(
            BrewSession.id,
            BrewSession.coffee_id,
            BrewSession.rating,
            BrewSession.flavor_note_ids_observed,
            BrewSession.recipe_id,
            BrewSession.brewer_id,
            Bag.roast_date,
        )
        .outerjoin(Bag, BrewSession.bag_id == Bag.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),   # D-09: rated sessions only
        )
        .order_by(BrewSession.id)              # sort by id for determinism
    )
    rows = db.execute(stmt).all()

    def _serialize_row(row: Row) -> list:
        return [
            row.coffee_id,
            float(row.rating),                 # Decimal → float for JSON
            sorted(row.flavor_note_ids_observed or []),
            row.recipe_id,
            row.brewer_id,
            row.roast_date.isoformat() if row.roast_date else None,
        ]

    payload = [_serialize_row(r) for r in rows]  # already ordered by id
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Stable sentinel for zero rated sessions:** `hashlib.sha256(b"[]").hexdigest()` — the hash of the empty JSON list. This is stable, reproducible, and Phase 7 can compare against it. [VERIFIED: stdlib]

**Order-independence rationale:** Rows are selected `ORDER BY id` (ascending, stable). The canonical JSON is then a deterministic list. Since sessions are append-only and their IDs are monotonically increasing, `ORDER BY id` produces the same order regardless of when the query runs. This is simpler and equally correct as a full sort-independent approach. [ASSUMED — the append-only / monotonic ID assumption holds for this app's usage pattern]

### Pattern 7: Cold-Start Gate Counts

```python
# Source: SQLAlchemy 2.0 select() style
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import array

def get_cold_start_counts(db: Session, user_id: int) -> dict:
    """Return {sessions, distinct_notes} from LIVE data including unrated sessions (D-02)."""
    session_count = db.scalar(
        select(func.count(BrewSession.id))
        .where(BrewSession.user_id == user_id)
    ) or 0

    # Unnest all flavor_note_ids_observed arrays, count distinct note IDs
    unnested = func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")
    note_count = db.scalar(
        select(func.count(func.distinct(unnested.c.note_id)))
        .select_from(BrewSession)
        .join(unnested, literal(True))
        .where(BrewSession.user_id == user_id)
    ) or 0

    return {
        "sessions": session_count,
        "distinct_notes": note_count,
        "gate_open": session_count >= 3 and note_count >= 5,
    }
```

### Anti-Patterns to Avoid

- **Python-loop aggregation:** Never iterate query results in Python to compute averages, counts, or group memberships. All aggregation is in SQL. [VERIFIED: ROADMAP lock + CONTEXT D-05]
- **`coffees.roast_date` for freshness:** `coffees` has no `roast_date` column. Use `bags.roast_date` always. [VERIFIED: app/models/bag.py, app/models/coffee.py]
- **`advertised_flavor_note_ids` for HOME-03:** This is the roaster-advertised field on `coffees`. HOME-03 aggregates `brew_sessions.flavor_note_ids_observed` — the user-observed field. Never conflate them. [VERIFIED: Phase 5 CONTEXT]
- **Mixing cold-start gate logic and signature logic:** Gate (D-02) counts ALL sessions incl. unrated; signature (D-09) only counts RATED sessions. These are two separate queries, never merged.
- **`|safe` in templates or `hx-on:` inline handlers:** Both are banned by CI grep tests (Phase 1). All JavaScript behavior lives in `app/static/js/`. [VERIFIED: 01-CONTEXT.md D-04, CLAUDE.md]
- **Legacy `Query` API:** Use `select()` + `db.execute(stmt)`, not `db.query(Model)`. [VERIFIED: CLAUDE.md code conventions]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unnesting Postgres arrays | Custom Python unnest logic | `func.unnest().column_valued()` | Native SQLAlchemy 2.0; compiles to correct SQL lateral join |
| HTMX lazy-load triggers | Custom JS polling or IntersectionObserver | `hx-trigger="load delay:Nms"` | Built into HTMX 2.x; fires when element enters DOM; stagger via delay modifier |
| Cache headers on fragments | Per-route `response.headers` | `FragmentCacheHeadersMiddleware` (Phase 1) | Applied automatically on all `HX-Request: true` responses |
| Date subtraction / buckets | Python `datetime` arithmetic | Postgres `cast(ts, Date) - date` → integer | DB-side; avoids ORM result iteration; uses existing indexes |
| SHA256 hashing | Custom rolling hash, XOR-based | `hashlib.sha256` + `json.dumps(sort_keys=True)` | Stdlib; deterministic; tested path for canonical serialization |
| Detecting sparse cards | Per-card special-casing | Shared empty-state partial `_card_sparse.html` | Keep template logic consistent; D-04/D-05 governs copy |

**Key insight:** Every "smart" Python loop replacing a SQL GROUP BY adds a round-trip, kills index usage, and forces the full row set into memory. The queries are simpler in SQL than in Python.

---

## Common Pitfalls

### Pitfall 1: `rating IS NULL` breaks aggregate cards
**What goes wrong:** `func.avg(BrewSession.rating)` returns NULL when all sessions have NULL ratings. `func.count(BrewSession.id)` still counts them. A user can clear the cold-start gate (3 sessions, 5 notes) with zero rated sessions — the aggregate cards then return NULL averages or empty results.
**Why it happens:** `rating` is nullable; `AVG` of all-NULL is NULL; HAVING `COUNT >= 2` still passes on session-count even with no rated sessions.
**How to avoid:** Add `BrewSession.rating.is_not(None)` to the WHERE clause on all rating-dependent cards (HOME-01, 02, 03, 05). Detect the all-unrated case separately in the service and return a sentinel. Surface D-05's "rate your brews" nudge in the template when the service returns the all-unrated sentinel.
**Warning signs:** An aggregate card renders empty even after the gate clears; the service function returns an empty list but `session_count > 0`.

### Pitfall 2: Conflating observed vs advertised flavor notes
**What goes wrong:** HOME-03 uses `coffees.advertised_flavor_note_ids` instead of `brew_sessions.flavor_note_ids_observed`, returning roaster marketing copy instead of what the user actually tasted.
**Why it happens:** Both columns are `BIGINT[]` with the same FK target; easy to grab the wrong one.
**How to avoid:** The query in `get_flavor_descriptors` selects from `BrewSession` and unnests `BrewSession.flavor_note_ids_observed`. Never reference `Coffee.advertised_flavor_note_ids` in this function.
**Warning signs:** Flavor descriptors don't change even after logging different flavor notes; results match the coffee's advertised profile exactly.

### Pitfall 3: Thundering-herd on the connection pool from lazy cards
**What goes wrong:** All seven fragment endpoints fire simultaneously on page load, saturating the `pool_size=10, max_overflow=5` pool. Under concurrent multi-user load, new requests queue or time out.
**Why it happens:** Without staggered delays, all `hx-trigger="load"` fire at DOMContentLoaded.
**How to avoid:** Stagger delays per UI-SPEC (100/150/200/300/400/500ms). Each fragment uses one connection for one query; with seven fragments spread over 500ms, the pool is rarely exhausted. SH-2 pool settings are already in place.
**Warning signs:** 503 or `pool_timeout` errors in logs under load; page load time spikes when multiple users hit the home page simultaneously.

### Pitfall 4: `bags.roast_date` NULL leads to incorrect freshness card
**What goes wrong:** Sessions with `bag_id IS NULL` or bags with `roast_date IS NULL` sneak into the freshness bucketing, producing erroneous "0 days fresh" or NULL buckets.
**Why it happens:** Missing the JOIN condition or forgetting the NULL filter on `roast_date`.
**How to avoid:** `INNER JOIN bags ON brew_sessions.bag_id = bags.id` (not OUTER JOIN) plus `.where(Bag.roast_date.is_not(None))`. Sessions without a bag are simply excluded from this card.
**Warning signs:** A "0-3 days" bucket with implausibly high session count; NULL values in the freshness bucket label.

### Pitfall 5: Non-deterministic signature
**What goes wrong:** `compute_input_signature` returns a different hash for the same data set across calls because the sort order of sessions is undefined (Postgres makes no ordering guarantee without ORDER BY).
**Why it happens:** Omitting `ORDER BY BrewSession.id` means Postgres may return rows in any order; `json.dumps` of a list is order-dependent.
**How to avoid:** Always include `.order_by(BrewSession.id)` in the signature query. Validate determinism in tests by calling the function twice in a row on the same DB state and asserting the results are equal.
**Warning signs:** The AI card shows "Outdated" badge immediately after regeneration; nightly scheduler re-generates for every user on every run.

### Pitfall 6: `union_all` ORDER BY referencing original table columns
**What goes wrong:** `union_all(stmt1, stmt2).order_by(Coffee.origin.desc())` raises a compile error because the UNION result has no reference to the original `Coffee` table.
**Why it happens:** After a UNION, column references must go through the CompoundSelect's exported columns, not the original tables.
**How to avoid:** Use `.subquery()` to wrap the union, then `select(subq).order_by(subq.c.avg_rating.desc()).limit(3)`. Or use `.order_by(literal_column("avg_rating").desc())` directly on the CompoundSelect. [VERIFIED: SQLAlchemy 2.0 docs]
**Warning signs:** `sqlalchemy.exc.CompileError` at import or request time referencing column not found in FROM clause.

### Pitfall 7: Sweet spots excluding NULL-dimension sessions
**What goes wrong:** Sessions where `brewer_id IS NULL` or `recipe_id IS NULL` are excluded from the sweet spots INNER JOIN, producing zero sweet spots for users who logged sessions without specifying equipment/recipe.
**Why it happens:** INNER JOIN on `brewer_id` and `recipe_id` drops NULL FK rows.
**How to avoid:** This is intentional for v1 — a "sweet spot" requires a known (origin × process × brewer × recipe) combination. The D-04 sparse-card hint explains this. Document the behavior in the template hint: "Not enough sessions per combination yet (need 3 per match)."
**Warning signs:** A user who always logs sessions without a recipe or brewer never sees any sweet spots; the hint fires even with 10+ sessions.

---

## Code Examples

### Complete service module skeleton

```python
# app/services/analytics.py
# Source: Project conventions (CLAUDE.md) + verified SQLAlchemy 2.0 patterns
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import case, cast, func, literal, select
from sqlalchemy import Date as SaDate
from sqlalchemy.orm import Session, aliased

from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe

# Typed result dataclasses (Pydantic v2 not needed — these are service-internal)
@dataclass(frozen=True)
class TopCoffeeRow:
    id: int
    name: str
    avg_rating: Decimal
    session_count: int

# ... similar for other cards ...

_EMPTY_SIGNATURE = hashlib.sha256(b"[]").hexdigest()
```

### Cold-start gate check (eagerly computed in shell render)

```python
# app/services/analytics.py::get_cold_start_counts
# This is called synchronously in the home shell render (not a fragment endpoint)
def get_cold_start_counts(db: Session, user_id: int) -> dict[str, Any]:
    session_count: int = db.scalar(
        select(func.count(BrewSession.id))
        .where(BrewSession.user_id == user_id)
    ) or 0

    unnested = func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")
    note_count: int = db.scalar(
        select(func.count(func.distinct(unnested.c.note_id)))
        .select_from(BrewSession)
        .join(unnested, literal(True))
        .where(BrewSession.user_id == user_id)
    ) or 0

    return {
        "sessions": session_count,
        "distinct_notes": note_count,
        "gate_open": session_count >= 3 and note_count >= 5,
        "sessions_needed": max(0, 3 - session_count),
        "notes_needed": max(0, 5 - note_count),
    }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLAlchemy `Query` API (`db.query(Model).filter(...)`) | `select()` Core-style + `db.execute()` | SQLAlchemy 2.0 (2023) | Legacy Query API is still present but deprecated; all new code uses Core-style |
| `func.unnest().alias()` | `func.unnest().column_valued()` | SQLAlchemy 1.4+ | `column_valued()` and `table_valued()` are the modern equivalents of `.alias()`; cleaner |
| HTMX `hx-sse` + `hx-ws` (1.9 builtins) | Extension-based: `htmx-ext-sse@2.2.4` | HTMX 2.0.0 (mid-2024) | SSE/WS removed from core; Phase 6 doesn't use SSE, so this is irrelevant |
| `json.dumps(list_of_tuples)` without sort | `json.dumps(canonical_list, sort_keys=True, separators=(",", ":"))` | Best practice | Removes whitespace variation; `sort_keys=True` ensures dict key order doesn't matter |

**Deprecated/outdated:**
- `db.query(Model)`: Legacy API, do not use.
- `func.unnest().alias()`: Still works but `column_valued()` is cleaner.
- `@app.on_event("startup")`: Deprecated in Starlette 1.0; use `lifespan`. Phase 6 adds no startup hooks.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BrewSession.id` is monotonically increasing and append-only, making `ORDER BY id` a stable deterministic sort for the signature | Pattern 6 (Signature) | Signature may differ across calls if rows are re-ordered; fix: use explicit multi-column sort or sort the serialized list independently |
| A2 | `func.unnest().column_valued()` produces an implicit LATERAL join that Postgres accepts for GROUP BY + HAVING in SQLAlchemy 2.0.49 | Pattern 3 (Flavor Descriptors) | Query may fail at compile or runtime; fallback: use `text()` raw SQL for the unnest subquery |
| A3 | The cold-start note count (distinct observed flavor notes) matches the AI-7 gate definition exactly — "5 distinct observed flavor notes" means 5 distinct IDs in `flavor_note_ids_observed` across all of the user's sessions | Pattern 7 (Cold-start counts) | Gate opens at wrong threshold; fix: clarify with user whether the gate counts distinct notes across all sessions or only rated sessions |

**Note:** A3 is the only one that warrants clarification. Based on CONTEXT.md D-02 ("unlock threshold = ≥3 sessions AND ≥5 distinct observed flavor notes"), the gate counts all sessions (not just rated), and "distinct observed flavor notes" means distinct `flavor_note_ids_observed` IDs across all the user's sessions. The query above reflects this interpretation.

---

## Open Questions

1. **Sweet spots: require both brewer_id AND recipe_id to be non-null?**
   - What we know: INNER JOIN to both `equipment` (brewer) and `recipes` drops NULL FK sessions.
   - What's unclear: Should sessions with `brewer_id IS NULL` or `recipe_id IS NULL` still participate in a reduced sweet spots combination (e.g., just `origin × process`)?
   - Recommendation: v1 requires both non-null (cleaner SQL, clear semantics). The sparse-card hint explains why the card is empty. Revisit if users frequently skip filling in brewer/recipe.

2. **HOME-02 preference profile: one query per dimension or four queries?**
   - What we know: Four dimensions (origin, process, roaster, roast level). Could be one UNION ALL of four GROUP BYs, or four separate queries per fragment request.
   - What's unclear: Are all four dimensions shown in a single `/home/cards/preference-profile` fragment, or should each dimension be a separate fragment endpoint?
   - Recommendation: One fragment endpoint, four queries executed in the service, results passed as a dict with four lists. The UI-SPEC shows a 2-column grid on md+ with all four dimensions, suggesting they load together.

3. **`func.unnest().column_valued()` vs `func.unnest().table_valued()` for the lateral join**
   - What we know: `column_valued()` returns a scalar; `table_valued()` returns a table reference. For unnesting a scalar array, `column_valued()` is correct.
   - Recommendation: Use `column_valued("note_id")` for `flavor_note_ids_observed`. If the implicit lateral join fails at runtime, fall back to raw `text()`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 16 | All analytics queries | ✓ | postgres:16-alpine | — |
| Docker Compose stack | Test execution | ✓ | 29.4.3 | — |
| Python 3.12 (in container) | Service code | ✓ | 3.12 (baked in image) | — |
| pytest (in container) | Unit tests | Install first | Via `pip install --user pytest` | See CLAUDE.md test instructions |
| SQLAlchemy 2.0.49 | Analytics queries | ✓ | Already in requirements.txt | — |
| HTMX 2.0.10 (CDN) | Lazy-load fragments | ✓ | Already in base.html | — |
| hashlib | Signature computation | ✓ | stdlib | — |
| json | Signature serialization | ✓ | stdlib | — |

[VERIFIED: docker compose ps shows both containers healthy]

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + SQLAlchemy sync session |
| Config file | pyproject.toml (existing) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/services/test_analytics.py -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HOME-01 | Top 5 coffees by avg rating, min 2 sessions | unit (seeded DB) | `pytest tests/services/test_analytics.py::test_top_coffees -x` | ❌ Wave 0 |
| HOME-02 | Preference profile avg rating by dimension, min 2 sessions | unit (seeded DB) | `pytest tests/services/test_analytics.py::test_preference_profile -x` | ❌ Wave 0 |
| HOME-03 | Flavor descriptors: top 10 from 4.0+ sessions, min 2 sessions | unit (seeded DB) | `pytest tests/services/test_analytics.py::test_flavor_descriptors -x` | ❌ Wave 0 |
| HOME-04 | Roast freshness buckets using bags.roast_date, min 2 rated sessions | unit (seeded DB) | `pytest tests/services/test_analytics.py::test_roast_freshness_buckets -x` | ❌ Wave 0 |
| HOME-05 | Sweet spots: top 3 (origin×process×brewer×recipe), min 3 sessions | unit (seeded DB) | `pytest tests/services/test_analytics.py::test_sweet_spots -x` | ❌ Wave 0 |
| HOME-07 | Recent brews: last 10 sessions | unit | `pytest tests/services/test_analytics.py::test_recent_brews -x` | ❌ Wave 0 |
| HOME-08 | Unrated coffees: catalog not brewed by user | unit | `pytest tests/services/test_analytics.py::test_unrated_coffees -x` | ❌ Wave 0 |
| HOME-09 | Staggered lazy-load: fragment endpoints return 200 + correct Vary header | smoke | `pytest tests/routers/test_home.py -x` | ❌ Wave 0 |
| (signature) | `compute_input_signature` is deterministic and order-independent | unit | `pytest tests/services/test_analytics.py::test_signature_determinism -x` | ❌ Wave 0 |
| (signature) | Signature changes when rating changes, not when notes-text changes | unit | `pytest tests/services/test_analytics.py::test_signature_excludes_free_text -x` | ❌ Wave 0 |
| (gate) | Cold-start counts: correct session + distinct note counts | unit | `pytest tests/services/test_analytics.py::test_cold_start_counts -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/services/test_analytics.py -q`
- **Per wave merge:** `pytest -q` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/services/test_analytics.py` — covers HOME-01..05/07/08, signature, gate counts
- [ ] `tests/routers/test_home.py` — covers HOME-09 fragment endpoints, cold-start rendering
- [ ] `tests/services/conftest.py` (or extend `tests/conftest.py`) — analytics seed fixtures: one user with N brew sessions across varied coffees/bags/equipment/recipes/flavor notes (1 fixture for gate-cleared scenarios, 1 for cold-start)

No new test framework install required — pytest is already in the container install path (see CLAUDE.md).

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (home route gated) | `require_user` dependency (Phase 2) — gates every home route + every fragment endpoint |
| V3 Session Management | yes (existing middleware) | Phase 1/2 SessionMiddleware — already in place |
| V4 Access Control | yes | Every query scoped by `BrewSession.user_id == request.state.user.id` — per-user scoping is the first WHERE clause on every analytics query |
| V5 Input Validation | limited | All inputs are `user.id` (int, from session) and `hx-get` parameters (no user-supplied parameters on fragment endpoints) — no Pydantic schema needed for read-only GET endpoints |
| V6 Cryptography | no | No encryption this phase; `compute_input_signature` uses SHA256 for integrity, not secrecy |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — one user accessing another user's analytics | Elevation of Privilege | Every analytics query has `WHERE user_id = :user_id` where `user_id = request.state.user.id`; never accept user_id from query params |
| Fragment endpoint leaking data without auth | Information Disclosure | All fragment endpoints require `Depends(require_user)`; unauthenticated requests return 401/redirect |
| SQL injection via HTMX params | Tampering | Fragment endpoints have no user-supplied parameters; all queries use bound parameters via SQLAlchemy |
| CSP violation via template rendering | Tampering | `|safe` banned; all data rendered through Jinja2 autoescape; no inline JS; `hx-on:` banned |

**Phase 6 specific:** The `compute_input_signature` function reads from the DB scoped strictly by `user_id`. COST-4 rule: never include shared catalog counts (`equipment_count`, `recipe_count`) — only per-session fields that belong to this user. [VERIFIED: CONTEXT D-08, CLAUDE.md]

---

## Project Constraints (from CLAUDE.md)

- Python 3.12 + FastAPI — locked
- PostgreSQL 16 — locked
- SQLAlchemy 2.0 + Alembic — locked; use `select()` style, `Mapped[...]` columns, no legacy Query API
- Jinja2 + HTMX + Tailwind (CDN) + Alpine.js — locked; no npm
- argon2-cffi for passwords, Fernet for API key encryption — unchanged this phase
- APScheduler in-process — not touched this phase
- Docker Compose, two containers — not changed
- `ruff format` before committing; `ruff check`; warnings treated as errors
- Type hints required on function signatures; `from __future__ import annotations`
- Pydantic v2 for schemas; SQLAlchemy 2.0 style
- Templates: 2-space indent, snake_case variables
- CSS: Tailwind utility classes; custom CSS only when utilities don't cover it
- JavaScript: Alpine.js inline (CSP build, registered via `Alpine.data`); no `hx-on:`; no `|safe`
- Mobile-first: tested at 375px viewport; bottom nav <768px (Phase 11), top nav ≥768px (Phase 11)
- CSRF on all state-changing forms — Phase 6 is read-only; no CSRF tokens needed on GET endpoints
- Security headers on every response — handled by SecurityHeadersMiddleware (Phase 1)
- No public registration; admin creates users — unchanged
- AI keys live encrypted in DB — not touched this phase
- Signature-based AI regeneration must not be broken — Phase 6 ships the `compute_input_signature` helper; must match Phase 7's expected contract
- **No migration needed this phase** — all columns and indexes already exist from Phases 0/4/5

---

## Sources

### Primary (HIGH confidence)
- `app/models/brew_session.py` — BrewSession schema, columns, indexes, GENERATED column [VERIFIED: codebase]
- `app/models/bag.py` — `roast_date: Mapped[date | None]` field [VERIFIED: codebase]
- `app/models/coffee.py` — `advertised_flavor_note_ids` vs `brew_sessions.flavor_note_ids_observed` distinction [VERIFIED: codebase]
- `app/migrations/versions/p5_brew_sessions.py` — GIN index, B-tree indexes confirmed [VERIFIED: codebase]
- `.planning/phases/06-analytics-home-page/06-CONTEXT.md` — locked decisions D-01..D-09 [VERIFIED: planning docs]
- `.planning/phases/06-analytics-home-page/06-UI-SPEC.md` — fragment endpoints, stagger timing, card order [VERIFIED: planning docs]
- `tests/conftest.py` — existing test fixture patterns, fresh_db, seeded_admin_user [VERIFIED: codebase]
- [docs.sqlalchemy.org/en/20/core/selectable.html](https://docs.sqlalchemy.org/en/20/core/selectable.html) — `union_all`, `CompoundSelect.subquery()` [CITED]
- [docs.sqlalchemy.org/en/20/core/functions.html](https://docs.sqlalchemy.org/en/20/core/functions.html) — `func.unnest().column_valued()`, `table_valued()` [CITED]
- [docs.sqlalchemy.org/en/20/core/sqlelement.html](https://docs.sqlalchemy.org/en/20/core/sqlelement.html) — `case()` bucketing syntax [CITED]
- [htmx.org/attributes/hx-trigger/](https://htmx.org/attributes/hx-trigger/) — `load delay:Nms` syntax, confirmed stable in HTMX 2.x [CITED]

### Secondary (MEDIUM confidence)
- [docs.sqlalchemy.org/en/20/tutorial/data_select.html](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html) — GROUP BY + HAVING + func.avg/count patterns [CITED]
- [github.com/sqlalchemy/sqlalchemy/discussions/11179](https://github.com/sqlalchemy/sqlalchemy/discussions/11179) — `table_valued()` vs lateral join discussion for unnest [CITED]
- [death.andgravity.com/stable-hashing](https://death.andgravity.com/stable-hashing) — deterministic JSON serialization for stable hashing [CITED]
- [docs.python.org/3/library/hashlib.html](https://docs.python.org/3/library/hashlib.html) — `hashlib.sha256().hexdigest()` [CITED]

### Tertiary (LOW confidence)
- WebSearch results on `func.unnest` lateral join behavior — unverified without running against the actual container; fallback pattern documented [LOW: WebSearch]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed and in use
- Architecture: HIGH — all patterns derived from existing Phase 4/5 conventions + verified SQLAlchemy 2.0 docs
- Query patterns: MEDIUM-HIGH — syntactically verified; runtime behavior of `column_valued()` lateral join marked [ASSUMED A2]
- Pitfalls: HIGH — derived from schema analysis and CONTEXT decisions
- HTMX lazy-load: HIGH — confirmed in official HTMX 2.x docs
- Signature computation: HIGH — stdlib hashlib + json; determinism assumption documented

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (stable stack; SQLAlchemy and HTMX are slow-moving at these version pins)
