# Phase 10: Global Search - Research

**Researched:** 2026-05-22
**Domain:** PostgreSQL trigram search, HTMX 2.x live-results, markupsafe highlight, FastAPI/Jinja2 search service
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Minimal persistent search header in `base.html`, auth-gated on `request.state.user`, Phase 11 absorbs it into full nav
- D-02: Desktop (>=768px) results = floating dropdown overlay, z-50, dismissed on outside-click and Esc
- D-03: Mobile (<768px) = icon -> full-screen sheet, X button, Esc, backdrop tap; no pushState/history entry
- D-04: Live results only — no dedicated results page; Enter is a no-op
- D-05: Each row shows name + key context: coffee = name + roaster + origin; equipment = name + type; recipe = name + short description; roaster/flavor note = name only; brew note = coffee name + brew date + snippet
- D-06: Highlight matched substring via `markupsafe.Markup` composition, never `|safe` on user text
- D-07: Fixed group order — Coffees, Roasters, Recipes, Equipment, Flavor Notes, Your Brew Notes
- D-08: Relevance sort within each group — prefix/exact above mid-string hits; mechanism follows FTS vs trigram research decision
- D-09: Cap ~5 per group + non-clickable "+N more — keep typing to narrow" hint
- D-10: Empty state "Nothing matches. The grounds are clean." below 2 chars keeps dropdown/sheet closed
- D-11: Per-entity link destinations: Coffee -> `/coffees/{id}`; Roaster/Equipment/Recipe/FlavorNote -> `/{entity}/{id}/edit`; BrewNote -> `/brew/{id}/edit`; full-page navigations, not HTMX swaps
- D-12: Include archived coffees/equipment, marked with "Archived" badge

### Claude's Discretion
- FTS vs trigram — explicitly deferred to plan-phase research (this document resolves it)
- Query shape — six per-entity queries vs one UNION ALL: planner's call
- Enter-key / arrow-key behavior — minimal (Enter as no-op acceptable)
- `aria-live` results region for screen-reader announcement
- Snippet length for brew-note matches — sensible window around match

### Deferred Ideas (OUT OF SCOPE)
- Full global nav + sign-out + brand wordmark — Phase 11
- Dedicated full results page + pagination + Enter-to-see-all
- Recent searches / pre-search suggestions
- Expanding coffee search to origin/process/roast-level fields
- Keyboard arrow-navigation through results
- Searching recipe step text
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEARCH-01 | Persistent search input in top nav: collapsed to icon at <768px (expands to full-screen sheet on tap), expanded inline at >=768px | §HTMX Wiring, §Alpine Component, §base.html gating |
| SEARCH-02 | Postgres-based search across coffee names, roaster names, flavor note names, brew session notes (only current user's), recipe names/descriptions, equipment names | §FTS vs Trigram recommendation, §Searchable Columns Confirmed |
| SEARCH-03 | HTMX live results with 250ms debounce; results grouped by entity type; each result links to relevant edit page | §HTMX Wiring, §Cross-Entity Query Shape |
| SEARCH-04 | User only sees their own brew session notes in results; shared catalog searchable to every authenticated user | §Per-User Scoping, §Cross-Entity Query Shape |
</phase_requirements>

---

## Summary

Phase 10 adds global search by composing four pieces: (1) a thin auth-gated persistent header in `base.html`, (2) a new `app/services/search.py` executing six sync `select()` queries against PostgreSQL, (3) a new `app/routers/search.py` exposing a GET-only live-results endpoint, and (4) an Alpine CSP component (`search-bar.js`) managing the mobile sheet and desktop dropdown. The entire search stack is brownfield — it slots into patterns already established across Phases 1-9.

**Critical finding:** The `recipes` table has NO `description` column. The CONTEXT.md phrase "recipe name + description" does not match the actual schema. Recipe search must target only `recipes.name`. The `grind_setting` column (free-text) is a plausible secondary match field but was not enumerated in SEARCH-01. Equipment has no `name` column; its display identity is `{brand} {model}` — search must target `equipment.brand || ' ' || equipment.model` as an expression.

**Primary recommendation:** Use `pg_trgm` with GIN trigram indexes and `ILIKE '%term%'` for matching, ordered by `similarity(column, term) DESC`. This wins over FTS for this specific workload: short prefix live-search (>=2 chars, debounced), mostly short name fields, household-scale row counts (<1000 rows per table), and a critical need for partial prefix matching (typing "et" must match "Ethiopia" mid-string). Both `pg_trgm` and `unaccent` extensions are already installed in `0001_initial.py` — no new extension work needed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Search index DDL | Database (Postgres) | — | GIN trigram indexes on six tables; one migration, no app-layer index management |
| Query execution + per-user scoping | API (FastAPI service) | — | Six sync `select()` constructs with ILIKE + user_id guard in `services/search.py` |
| Result highlighting | API (Python) | Template (Jinja2) | Python builds `Markup` objects; Jinja renders them; the split is safety-enforced |
| Debounce + request cancel | Browser (HTMX 2.x) | — | `hx-trigger="keyup changed delay:250ms"` + `hx-sync="this:replace"` |
| Desktop dropdown / mobile sheet state | Browser (Alpine.js CSP) | — | `search-bar.js` component manages `sheetOpen` state and close affordances |
| Cache headers on results fragment | API (middleware) | — | `FragmentCacheHeadersMiddleware` automatically applies `no-store + Vary: HX-Request` |
| Auth gating on header | Frontend server (Jinja2) | — | `{% if request.state.user %}` in `base.html` — no route-level change needed |

---

## Standard Stack

### Already Installed (no new dependencies)
| Library/Extension | Version | Purpose | Status |
|-------------------|---------|---------|--------|
| `pg_trgm` | PostgreSQL 16 built-in | Trigram similarity + GIN indexes | `CREATE EXTENSION IF NOT EXISTS pg_trgm` in `0001_initial.py:61` — ALREADY INSTALLED [VERIFIED: codebase grep] |
| `unaccent` | PostgreSQL 16 built-in | Accent-insensitive matching | `CREATE EXTENSION IF NOT EXISTS unaccent` in `0001_initial.py:62` — ALREADY INSTALLED [VERIFIED: codebase grep] |
| `markupsafe` | Jinja2 dependency | Safe HTML composition without `|safe` | Shipped as Jinja2 transitive dependency |
| `sqlalchemy` | 2.0.49 | `select()` queries, sync Session | Already in stack |

### New Files (no new pip packages)
| File | Purpose |
|------|---------|
| `app/services/search.py` | Six `select()` queries, highlight helpers, result dataclasses |
| `app/routers/search.py` | `GET /search` endpoint, `require_user` dependency |
| `app/static/js/alpine-components/search-bar.js` | `Alpine.data("searchBar", ...)` factory |
| `app/templates/fragments/search_results.html` | Grouped results fragment |
| `app/migrations/versions/p10_search_indexes.py` | GIN trigram index DDL |

**Installation:** No new `pip install` required.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser
  │  keyup + 250ms debounce (HTMX hx-sync=this:replace)
  │
  ▼
GET /search?q={term}
  │  FragmentCacheHeadersMiddleware → Cache-Control: no-store + Vary: HX-Request
  │  SessionMiddleware → request.state.user (already resolved)
  │
  ▼
routers/search.py :: search_results()
  │  require_user dependency (401 if not authenticated)
  │  len(q) < 2 → return empty 200
  │
  ▼
services/search.py :: run_search(db, query, user_id)
  │
  ├── SELECT coffees (ILIKE, GIN trigram, include archived)
  ├── SELECT roasters (ILIKE, GIN trigram)
  ├── SELECT recipes (ILIKE on name only)
  ├── SELECT equipment (ILIKE on brand || ' ' || model, GIN trigram)
  ├── SELECT flavor_notes (ILIKE, GIN trigram)
  └── SELECT brew_sessions WHERE user_id = {current_user.id} (ILIKE on notes)
        │
        ▼
  Six result lists, each capped at 6 (5 shown + count-for-"+N more")
  Highlight applied in Python via markupsafe.Markup
        │
        ▼
  templates/fragments/search_results.html
  Jinja2 renders autoescaped context; Markup objects bypass escaping safely
        │
        ▼
  #search-results div swapped by HTMX (innerHTML)
```

### Recommended Project Structure (additions only)
```
app/
├── services/
│   └── search.py            # New — query logic + highlight helper
├── routers/
│   └── search.py            # New — GET /search endpoint
├── static/js/alpine-components/
│   └── search-bar.js        # New — mobile sheet + desktop dropdown state
├── templates/
│   └── fragments/
│       └── search_results.html  # New — grouped results fragment
└── migrations/versions/
    └── p10_search_indexes.py    # New — GIN trigram DDL
```

---

## Research Question 1: FTS vs pg_trgm — RECOMMENDATION

### Decision: Use pg_trgm with ILIKE and GIN trigram indexes

**Rationale:**

| Factor | FTS (tsvector + to_tsquery) | pg_trgm (ILIKE + similarity) |
|--------|----------------------------|------------------------------|
| Prefix matching (2+ chars) | Requires `to_tsquery('term:*')` — works but awkward for single short tokens; websearch_to_tsquery adds quotes automatically | `ILIKE '%term%'` — natural substring match, handles "et" matching "Ethiopia" mid-string |
| Short name fields (<50 chars) | Token normalization overkill; "Ethiopia Yirgacheffe" as a single tsvector gives no advantage at household scale | Direct substring match on short strings is fast and intuitive |
| Brew notes (free text, longer) | FTS shines on long text with stop-word filtering and stemming | ILIKE on a 40-char snippet field at household scale (<200 sessions) — negligible difference |
| Relevance ranking | `ts_rank(tsvector, tsquery)` — useful but opaque ordering | `similarity(column, query) DESC` — transparent, intuitive prefix-bias when combined with `position()` ordering |
| Extension already installed | N/A | `pg_trgm` already installed in `0001_initial.py` [VERIFIED: codebase] |
| Household scale (<1000 rows/table) | No advantage over trigram at this scale | GIN trigram index on short fields is extremely fast; query plan uses index for `ILIKE '%term%'` where term >= 3 chars |
| CITEXT columns | FTS must handle case explicitly | `ILIKE` is case-insensitive natively; CITEXT is also case-insensitive at storage — both align |
| Unaccent | Need `unaccent()` wrapper or immutable function for FTS index | `unaccent` extension can be composed with ILIKE via `unaccent(column) ILIKE unaccent('%term%')` |

**Short-prefix caveat:** `pg_trgm` GIN indexes only accelerate ILIKE queries when the query string is >= 3 characters (trigrams require at least one trigram to exist). For 2-character queries (the minimum), Postgres will fall back to a sequential scan. At household scale (<1000 rows per table), a 2-char sequential scan on `coffees.name` is sub-millisecond. This is acceptable. The minimum query length (2 chars) is enforced server-side regardless; the GIN index kicks in at 3+ chars.

**Relevance mechanism for D-08:** Order each per-entity result by `similarity(column, query) DESC`. This naturally floats closer matches above partial ones. For brew notes, combine with a position-in-text tie-breaker.

**unaccent:** Worth including. Coffee origins ("Yelp Yirgacheffe", "São Paulo") and roaster names may contain accented characters. The extension is already installed. Use `unaccent(column) ILIKE unaccent(concat('%', :q, '%'))` in the six queries. [VERIFIED: `0001_initial.py` installs unaccent]

### Index DDL for the Migration

**Pattern from `p4_shared_catalog.py`:** `op.execute(...)` for GIN indexes (SQLAlchemy 2.0 autogenerate cannot emit `USING GIN`). [VERIFIED: codebase]

```python
# In p10_search_indexes.py upgrade()
# coffees.name — CITEXT, GIN trigram
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_coffees_name "
    "ON coffees USING GIN (name gin_trgm_ops)"
)
# roasters.name — CITEXT
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_roasters_name "
    "ON roasters USING GIN (name gin_trgm_ops)"
)
# flavor_notes.name — CITEXT
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_flavor_notes_name "
    "ON flavor_notes USING GIN (name gin_trgm_ops)"
)
# recipes.name — Text (no description column exists)
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_recipes_name "
    "ON recipes USING GIN (name gin_trgm_ops)"
)
# equipment — no name column; index expression brand || ' ' || model
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_equipment_brand_model "
    "ON equipment USING GIN ((brand || ' ' || model) gin_trgm_ops)"
)
# brew_sessions.notes — Text (longer free-text, GIN trigram for substring)
op.execute(
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_brew_sessions_notes "
    "ON brew_sessions USING GIN (notes gin_trgm_ops)"
)
```

**Notes on DDL:**
- `CONCURRENTLY` avoids table lock during index build; safe in Alembic `op.execute()` but requires running outside a transaction block — Alembic by default wraps in a transaction. The migration must set `transaction_per_migration = False` or use `op.get_bind().execution_options(isolation_level="AUTOCOMMIT")` before the `CREATE INDEX CONCURRENTLY` calls, then restore it. Alternative: omit `CONCURRENTLY` since this is a new table with no production traffic yet (Phase 10 is pre-deploy). For simplicity, omit `CONCURRENTLY` in the initial migration; document it for future index rebuilds.
- `gin_trgm_ops` is the correct operator class for trigram GIN indexes. [ASSUMED — based on PostgreSQL 16 docs training knowledge; verify against Postgres 16 docs if needed]
- `IF NOT EXISTS` prevents re-run failures if migration is accidentally applied twice.
- No `CREATE EXTENSION` needed — both `pg_trgm` and `unaccent` already installed. [VERIFIED: 0001_initial.py]

---

## Research Question 2: Searchable Columns — CONFIRMED

Reading the actual models and migrations:

| Entity | Searchable Column(s) | Type | Archived Flag | Notes |
|--------|---------------------|------|---------------|-------|
| `coffees` | `name` | `CITEXT` | `archived: bool` | Include archived; show badge (D-12). Origin/process/roast are context-only display fields, NOT match fields. `coffees.notes` is deliberately excluded from SEARCH-01. |
| `roasters` | `name` | `CITEXT` | `archived: bool` | Roasters model has `archived` but it is never filtered on in CONTEXT.md — include all roasters (no D-12 badge specified for roasters). |
| `flavor_notes` | `name` | `CITEXT` | `archived: bool` | Include all (no D-12 badge specified). |
| `recipes` | `name` | `Text` | `archived: bool` (exists in schema) | **CRITICAL: no `description` column exists in the schema.** CONTEXT.md's phrase "recipe name + description" is incorrect — only `name` can be searched. `grind_setting` is free-text but not in SEARCH-01 scope. |
| `equipment` | `brand || ' ' || model` | `Text || Text` | `archived: bool` | **CRITICAL: no `name` column exists.** The display identity is `{brand} {model}`. Search must be an expression on the concatenation. D-05 context shows "name + type" — in practice this means `{brand} {model}` + `type` label. |
| `brew_sessions` | `notes` | `Text` | n/a | Scoped to `WHERE user_id = :current_user_id`. Include sessions with empty `notes = ''` only if they match (they won't, since `ILIKE '%term%'` on empty string never matches). |

**Coffee context columns (D-05, display only, not searched):**
- `coffees.origin` (nullable Text)
- `coffees.country` (nullable Text) — the roaster's name requires a JOIN to `roasters`

**Brew note context columns (D-05, display only, not searched):**
- `brew_sessions.brewed_at` (TIMESTAMP) — format as date
- Coffee name via JOIN to `coffees`

[VERIFIED: all model files and migration p4_shared_catalog.py read in this session]

---

## Research Question 3: Cross-Entity Query Shape

### Recommendation: Six separate `select()` queries (not UNION ALL)

**Rationale:**
- UNION ALL requires identical column counts and types across six heterogeneous entities. Forcing coffees, equipment (brand+model), brew sessions (needs JOIN to coffees for coffee_name) into a single UNION requires either a wide set of NULLable columns or a text-casting exercise that obscures the intent.
- Six separate queries with per-group caps (fetch 6, show 5) are readable, independently testable, and trivially parallelized if needed (they're not, at household scale).
- Per-group caps are enforced by `LIMIT 6` on each query — fetch one extra to detect "+N more" without a second COUNT query.
- Total round-trips: six `SELECT` statements in one DB session. At household scale (<1000 rows per table), each query completes in <5ms. Total p95 well under 100ms. [ASSUMED based on pg_trgm performance characteristics at small scale; no production profiling available]
- The D-07 fixed group order is trivially implemented by Python list ordering — no SQL ORDER BY across groups needed.

**SQLAlchemy 2.0 typed select() pattern:**
```python
# Example — coffees group (fetch 6, keep 6 for overflow detection)
from sqlalchemy import func, select
from markupsafe import Markup, escape

def _search_coffees(db: Session, query: str, limit: int = 6) -> list[dict]:
    pattern = f"%{query}%"
    stmt = (
        select(
            Coffee.id,
            Coffee.name,
            Coffee.origin,
            Coffee.archived,
            Coffee.roaster_id,
            Roaster.name.label("roaster_name"),
            func.similarity(Coffee.name, query).label("score"),
        )
        .outerjoin(Roaster, Coffee.roaster_id == Roaster.id)
        .where(func.unaccent(Coffee.name).ilike(func.unaccent(pattern)))
        .order_by(func.similarity(Coffee.name, query).desc())
        .limit(limit)
    )
    return [row._asdict() for row in db.execute(stmt).all()]
```

**Note on `func.unaccent()`:** SQLAlchemy 2.0 can call PostgreSQL functions via `func.*`. `func.unaccent(column).ilike(func.unaccent(pattern))` composes correctly. The GIN trigram index is on `name` directly — if unaccent is used in the WHERE clause without a matching `unaccent(name)` expression index, Postgres will not use the GIN index for unaccent-wrapped queries. Decision: for v1 at household scale, use plain `ILIKE` without unaccent in the WHERE clause (GIN index is used), and apply unaccent only if accent-insensitive matching becomes a user pain point. Add an unaccent expression index in a follow-up migration if needed.

**Simpler approach for v1:** Use plain `Coffee.name.ilike(pattern)` — CITEXT columns already handle case-insensitivity; GIN trigram index is used; keep the queries readable.

---

## Research Question 4: Safe Highlight Without `|safe`

### Pattern (already established in this codebase)

The existing `app/templates/fragments/autocomplete_list.html` already implements this exact pattern:

```jinja2
{# From autocomplete_list.html lines 45-48 — EXISTING PATTERN #}
{% if q_lower in lower %}
  {% set idx = lower.find(q_lower) %}
  {{ item.name[:idx] }}<strong class="font-semibold">{{ item.name[idx:idx + query|length] }}</strong>{{ item.name[idx + query|length:] }}
{% else %}
  {{ item.name }}
{% endif %}
```

This works because Jinja2 autoescape is ON globally, so `{{ item.name[:idx] }}` escapes the surrounding text fragments, and the literal `<strong>` tag in the template is trusted template code (not user input). No `|safe` filter is used anywhere on user data.

**For search results, use the same Jinja template pattern** rather than a Python-side `Markup` object. The Jinja approach:
1. Is already proven in production (autocomplete_list.html)
2. Requires no Python helper import
3. Is auditable at template-grep time (SEC-05 grep test)

**Python-side alternative (for brew-note snippets where index computation is needed):**

If the snippet extraction is done in Python (to find the match window), the safe helper is:

```python
from markupsafe import Markup, escape

def highlight_match(text: str, query: str) -> Markup:
    """Return text with query match wrapped in <strong>, fully escaped."""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return escape(text)  # No match — return escaped plain text
    before = escape(text[:idx])
    matched = escape(text[idx : idx + len(query)])
    after = escape(text[idx + len(query) :])
    return Markup(f"{before}<strong class='font-semibold'>{matched}</strong>{after}")
```

This function: (1) escapes all three fragments with `markupsafe.escape()`, (2) wraps them in a `Markup` object so Jinja2 does NOT double-escape the already-safe HTML, (3) never calls `|safe` on user text.

**Brew-note snippet window:** Extract a ~80-char window around the match:
```python
def brew_note_snippet(notes: str, query: str, window: int = 40) -> str:
    """Return ±window chars around the match for display."""
    idx = notes.lower().find(query.lower())
    if idx == -1:
        return notes[:80]
    start = max(0, idx - window)
    end = min(len(notes), idx + len(query) + window)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(notes) else ""
    return f"{prefix}{notes[start:end]}{suffix}"
```

Then pass `highlight_match(snippet, query)` to the template as a `Markup` object. The template renders it without escaping because Jinja2 trusts `Markup` instances.

**UI-SPEC alignment:** UI-SPEC §Match highlight specifies `<strong class="font-semibold">` with no background color (weight 600 is the only visual distinction). The `highlight_match` helper above uses `<strong class='font-semibold'>` — exact match.

[VERIFIED: autocomplete_list.html pattern read in this session; markupsafe behavior is ASSUMED based on training knowledge of markupsafe 2.x API]

---

## Research Question 5: HTMX 2.0.x Live-Search Wiring

### Confirmed HTMX 2.0.10 attributes (from UI-SPEC and htmx-listeners.js)

```html
<input
  type="search"
  name="q"
  autocomplete="off"
  minlength="2"
  placeholder="Search coffees, roasters, recipes…"
  hx-get="/search"
  hx-trigger="keyup changed delay:250ms"
  hx-sync="this:replace"
  hx-target="#search-results"
  hx-indicator="#search-spinner"
  hx-swap="innerHTML"
>
```

**`hx-trigger="keyup changed delay:250ms"`:** In HTMX 2.x, `keyup changed delay:250ms` means: fire on keyup, only if the value changed, after 250ms of inactivity. [VERIFIED: base.html uses HTMX 2.0.10; UI-SPEC confirms this syntax]

**`hx-sync="this:replace"`:** Cancels any in-flight request from this same element before issuing a new one (HX-4 requirement from ROADMAP). This is the HTMX 2.x syntax — unchanged from 1.x. [ASSUMED — training knowledge; HTMX changelog shows no syntax change for hx-sync in 2.x]

**Minimum 2-char guard:**
- Client-side: `minlength="2"` attribute — advisory only; HTMX fires regardless of this attribute (it only constrains native form submit, not HTMX requests)
- Server-side authority: `if len(q.strip()) < 2: return HTMLResponse("")` — returns empty 200; HTMX swaps empty content into `#search-results`, effectively hiding the dropdown
- Both layers: belt-and-braces; server is authoritative per UI-SPEC

**`.htmx-indicator` gotcha (memory: `strict-csp-blocks-htmx-indicator`):**
Already resolved in `app/static/css/tailwind.src.css` lines 22-25:
```css
.htmx-indicator { opacity: 0; transition: opacity 150ms ease-in; }
.htmx-request .htmx-indicator { opacity: 1; }
.htmx-request.htmx-indicator { opacity: 1; }
```
[VERIFIED: tailwind.src.css read in this session — the rule is already present]

No new CSS needed for the search spinner indicator.

**GET requests and CSRF:** `GET /search` is read-only. The `htmx-listeners.js` `configRequest` handler adds `X-CSRF-Token` to ALL HTMX requests including GETs — this is harmless (the CSRF middleware only validates POST/PUT/PATCH/DELETE). No special exemption needed. [VERIFIED: htmx-listeners.js + starlette-csrf behavior]

---

## Research Question 6: Auth-Gated Persistent Header in base.html

### Confirmed: login.html and setup.html both extend base.html

```
login.html line 1: {% extends "base.html" %}
setup.html line 1: {% extends "base.html" %}
```
[VERIFIED: both files read in this session]

**Current base.html structure:** The current `base.html` has NO persistent header — only `<body>` → `{% block content %}` → `</body>`. The search header will be injected between `<body>` and `{% block content %}`.

**Auth gate pattern (from home.html lines 12-14):**
```jinja2
{% if request.state.user and request.state.user.is_admin %}
  {# admin-gated content #}
{% endif %}
```

For the search header, the gate is simply `{% if request.state.user %}` — no `is_admin` check needed.

**Injection point in base.html (after `<body class="...">`, before `{% block content %}`):**
```jinja2
{% if request.state.user %}
  <header class="...persistent search header...">
    {# search input + Alpine searchBar component #}
  </header>
{% endif %}
{% block content %}{% endblock %}
```

**Alpine component script loading:** The `search-bar.js` component must be loaded in `<head>` BEFORE the `@alpinejs/csp` core, following the existing pattern. Add to `base.html` head:
```html
<script defer src="/static/js/alpine-components/search-bar.js" nonce="{{ csp_nonce(request) }}"></script>
```
This is the same pattern as `recipe-step-builder.js`, `mini-modal.js`, etc. [VERIFIED: base.html pattern]

**Admin router note:** Phase 9 ships a separate admin router; the search router is a peer. No admin router is in `main.py` yet — checking confirms `from app.routers import admin as admin_router` IS in `main.py` (line 84). The search router follows the same include pattern.

---

## Research Question 7: Results Fragment Headers + Endpoint Shape

### Endpoint shape

```python
# app/routers/search.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import search as search_service
from app.templates_setup import templates

router = APIRouter()

def search_results(
    request: Request,
    q: str = "",
    db: Session = Depends(get_session),
    current_user: User = Depends(require_user),
) -> HTMLResponse:
    if len(q.strip()) < 2:
        return HTMLResponse("")
    results = search_service.run_search(db, query=q.strip(), user_id=current_user.id)
    return templates.TemplateResponse(
        "fragments/search_results.html",
        {"request": request, "results": results, "query": q.strip()},
    )
```

**Sync `def` handler (not async):** Catalog routers all use sync `def` — FastAPI runs them in a threadpool. Search queries are sync `Session.execute()` calls. This matches the established pattern. [VERIFIED: coffees.py, roasters.py patterns]

**No CSRF token:** GET is read-only; `starlette-csrf` enforces only POST/PUT/PATCH/DELETE. [VERIFIED: starlette-csrf behavior from Phase 1 decisions]

**Cache headers:** `FragmentCacheHeadersMiddleware` detects `HX-Request: true` on the HTMX request and applies `Cache-Control: no-store` + `Vary: HX-Request` automatically. [VERIFIED: fragment_cache.py read in this session]

**Security headers:** `SecurityHeadersMiddleware` applies to all responses. No special action needed.

**Autoescape:** `templates` is the shared `Jinja2Templates` instance from `app/templates_setup.py` with autoescape ON. [VERIFIED: base.html comment + SEC-05 requirement]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trigram similarity search | Custom Levenshtein or prefix trees | `pg_trgm` GIN indexes + `ILIKE` | Already installed; handles substring, prefix, mid-string matching natively |
| Case-insensitive name matching | `lower()` in Python | `ILIKE` + `CITEXT` column type | CITEXT columns handle case-insensitivity at storage; ILIKE adds it for Text columns |
| HTML injection-safe highlighting | String concatenation or `|safe` | `markupsafe.Markup` + `escape()` composition | The existing autocomplete pattern already demonstrates the correct approach |
| Rate limiting search endpoint | Custom IP throttle | None needed (GET read-only, no destructive action) | The 250ms debounce + `hx-sync=this:replace` client-side already limits query rate; server adds `len(q) < 2` guard |
| Dropdown/sheet state management | Vanilla JS custom events | Alpine.js CSP `Alpine.data("searchBar", ...)` | Matches existing component pattern; eval-free; CSP-safe |

---

## Common Pitfalls

### Pitfall 1: `description` Column Does Not Exist on Recipe
**What goes wrong:** Executor writes `select(Recipe.description)` — AttributeError at runtime.
**Why it happens:** CONTEXT.md says "recipe name + description" but the `Recipe` model (CAT-06) has no `description` column. The searchable content is `Recipe.name` only. `Recipe.grind_setting` exists (free-text) but is not in SEARCH-01 scope.
**How to avoid:** Search `recipes.name` only. Show `grind_setting` as context (D-05 "short description" for recipe rows can be interpreted as `grind_setting` or omitted entirely).
**Warning signs:** `AttributeError: type object 'Recipe' has no attribute 'description'`

### Pitfall 2: Equipment Has No `name` Column
**What goes wrong:** Executor writes `Equipment.name.ilike(pattern)` — AttributeError.
**Why it happens:** The `Equipment` model has `brand` (Text) and `model` (Text), not `name`. The display identity is `{brand} {model}`.
**How to avoid:** Search on `(Equipment.brand + " " + Equipment.model).ilike(pattern)` or use `func.concat(Equipment.brand, " ", Equipment.model).ilike(pattern)`.
**Warning signs:** `AttributeError: type object 'Equipment' has no attribute 'name'`

### Pitfall 3: GIN Trigram Index Not Used for 2-Char Queries
**What goes wrong:** Search for "et" (2 chars) runs a sequential scan on large tables.
**Why it happens:** pg_trgm GIN indexes require at least one trigram (3 chars) to perform index-accelerated lookup. A 2-char query has no trigrams and falls back to seqscan.
**How to avoid:** At household scale (<1000 rows), this is not a latency problem. Document the behavior. If scale grows, consider adding a btree index on `name` for 2-char prefix lookups.
**Warning signs:** EXPLAIN shows Seq Scan on 2-char queries (acceptable at small scale).

### Pitfall 4: `Alpine.initTree` Not Called on Search Fragment Swap
**What goes wrong:** Result links that carry Alpine bindings don't respond to clicks after HTMX swap.
**Why it happens:** HTMX 2.x swaps new HTML but Alpine has already initialized the DOM. New fragment nodes need `Alpine.initTree(target)` after settle.
**How to avoid:** The existing `htmx-listeners.js` already has this handler (lines 63-67). Search result fragments must be within the `#search-results` target that HTMX swaps — `Alpine.initTree` fires on the swapped element automatically.
**Warning signs:** Alpine `x-on:click` bindings on result rows don't fire.

### Pitfall 5: Forgetting `brew_sessions.notes` Is Empty String by Default
**What goes wrong:** Brew session rows where `notes = ""` (server_default) appear as matches.
**Why it happens:** `"" ILIKE '%term%'` returns false for any non-empty term, so this is actually NOT a problem — empty notes will never match.
**Actual pitfall:** Joining brew sessions to coffees for the coffee_name context column — `BrewSession.coffee_id` is `NOT NULL` (RESTRICT FK) so the JOIN is always inner, but using an outer join is harmless.

### Pitfall 6: CSRF Token Attached to GET by htmx-listeners.js — Harmless
**What goes wrong:** (Perceived) CSRF token is attached to `GET /search` requests.
**Why it happens:** `htmx-listeners.js` attaches `X-CSRF-Token` to ALL HTMX requests including GETs.
**How to avoid:** Do nothing — it's harmless. `starlette-csrf` only validates the token on state-changing methods. The GET endpoint sees the header but ignores it.

### Pitfall 7: `CONCURRENTLY` in Alembic Migration Transaction
**What goes wrong:** `CREATE INDEX CONCURRENTLY` inside a transaction raises `ERROR: CREATE INDEX CONCURRENTLY cannot run inside a transaction block`.
**Why it happens:** Alembic wraps each migration in a transaction by default.
**How to avoid:** Either omit `CONCURRENTLY` (safe for an empty/small table at first deploy) or use `op.get_bind().execution_options(isolation_level="AUTOCOMMIT")` before the statement. Recommended: omit `CONCURRENTLY` in the initial migration since no traffic hits these tables until Phase 10 is deployed.

---

## Code Examples

### Pattern 1: Six-Query Search Service Skeleton

```python
# app/services/search.py
# Source: established SQLAlchemy 2.0 select() pattern from app/services/analytics.py
from __future__ import annotations

from dataclasses import dataclass, field
from markupsafe import Markup, escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster

_GROUP_LIMIT = 6  # Fetch 6, show 5; if 6 returned, "+N more" indicator

@dataclass
class SearchResult:
    id: int
    primary: str          # Highlighted Markup or plain str
    context: str          # Secondary line (roaster, origin, date, etc.)
    link: str             # Full-page navigation URL
    archived: bool = False
    is_markup: bool = False  # True when primary is a Markup object

@dataclass
class SearchResults:
    coffees: list[SearchResult] = field(default_factory=list)
    roasters: list[SearchResult] = field(default_factory=list)
    recipes: list[SearchResult] = field(default_factory=list)
    equipment: list[SearchResult] = field(default_factory=list)
    flavor_notes: list[SearchResult] = field(default_factory=list)
    brew_notes: list[SearchResult] = field(default_factory=list)

def highlight(text: str, query: str) -> Markup:
    """Escape text and wrap matched substring in <strong class='font-semibold'>."""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return escape(text)
    before = escape(text[:idx])
    matched = escape(text[idx : idx + len(query)])
    after = escape(text[idx + len(query):])
    return Markup(f"{before}<strong class='font-semibold'>{matched}</strong>{after}")

def run_search(db: Session, query: str, user_id: int) -> SearchResults:
    pattern = f"%{query}%"
    results = SearchResults()
    # ... six queries each populating results.{group}
    return results
```

### Pattern 2: Equipment Expression Index Query

```python
# Source: SQLAlchemy 2.0 func.concat pattern
from sqlalchemy import func

stmt = (
    select(
        Equipment.id,
        Equipment.brand,
        Equipment.model,
        Equipment.type,
        Equipment.archived,
    )
    .where(
        func.concat(Equipment.brand, " ", Equipment.model).ilike(pattern)
    )
    .order_by(
        func.similarity(func.concat(Equipment.brand, " ", Equipment.model), query).desc()
    )
    .limit(_GROUP_LIMIT)
)
```

### Pattern 3: Brew Session Query with User Scoping

```python
# Source: analytics.py pattern — user_id always first WHERE clause
stmt = (
    select(
        BrewSession.id,
        BrewSession.notes,
        BrewSession.brewed_at,
        Coffee.name.label("coffee_name"),
    )
    .join(Coffee, BrewSession.coffee_id == Coffee.id)
    .where(
        BrewSession.user_id == user_id,  # ALWAYS first — IDOR defense
        BrewSession.notes.ilike(pattern),
        BrewSession.notes != "",
    )
    .order_by(BrewSession.brewed_at.desc())
    .limit(_GROUP_LIMIT)
)
```

### Pattern 4: Migration GIN Trigram Index DDL

```python
# Source: p4_shared_catalog.py op.execute() pattern for GIN indexes
# [VERIFIED: p4_shared_catalog.py lines 174-178]
def upgrade() -> None:
    # No CREATE EXTENSION needed — pg_trgm already installed in 0001_initial.py
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_coffees_name "
        "ON coffees USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_roasters_name "
        "ON roasters USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_flavor_notes_name "
        "ON flavor_notes USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_recipes_name "
        "ON recipes USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_equipment_brand_model "
        "ON equipment USING GIN ((brand || ' ' || model) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_brew_sessions_notes "
        "ON brew_sessions USING GIN (notes gin_trgm_ops)"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_search_brew_sessions_notes")
    op.execute("DROP INDEX IF EXISTS ix_search_equipment_brand_model")
    op.execute("DROP INDEX IF EXISTS ix_search_recipes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_flavor_notes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_roasters_name")
    op.execute("DROP INDEX IF EXISTS ix_search_coffees_name")
```

### Pattern 5: Base Template Auth Gate + Script Registration

```jinja2
{# In base.html head — add before @alpinejs/csp core, same pattern as existing components #}
<script defer src="/static/js/alpine-components/search-bar.js" nonce="{{ csp_nonce(request) }}"></script>

{# In base.html body — add after <body> open tag, before {% block content %} #}
{% if request.state.user %}
  <header x-data="searchBar"
          class="h-14 bg-cream-100 dark:bg-espresso-900 border-b border-espresso-200 dark:border-espresso-700 flex items-center px-6">
    {# Desktop search (shown md+) #}
    <div class="hidden md:flex items-center gap-2 relative w-full max-w-xl">
      {# SVG magnifying glass icon #}
      <input type="search" name="q" autocomplete="off"
             placeholder="Search coffees, roasters, recipes…"
             hx-get="/search"
             hx-trigger="keyup changed delay:250ms"
             hx-sync="this:replace"
             hx-target="#search-results-desktop"
             hx-indicator="#search-spinner"
             hx-swap="innerHTML"
             class="rounded border border-espresso-200 dark:border-espresso-700 bg-cream-50 dark:bg-espresso-900 px-3 py-2 text-base w-64 lg:w-80">
      <span id="search-spinner" class="htmx-indicator">...</span>
      <div id="search-results-desktop"
           role="listbox" aria-live="polite" aria-atomic="false"
           class="absolute top-full left-0 right-0 z-50 bg-cream-100 ..."></div>
    </div>
    {# Mobile icon (shown <md) #}
    <button class="md:hidden min-h-[44px] min-w-[44px]"
            x-on:click="openSheet()"
            aria-label="Open search">
      {# SVG magnifying glass #}
    </button>
    {# Mobile full-screen sheet #}
    <div x-show="sheetOpen" x-on:keydown.escape.window="closeSheet()"
         class="fixed inset-0 z-50 flex flex-col bg-cream-50 dark:bg-espresso-950 md:hidden">
      ...
    </div>
  </header>
{% endif %}
```

### Pattern 6: Jinja Template Highlight (preferred over Python helper for simple cases)

```jinja2
{# From autocomplete_list.html — existing proven pattern; reuse for search results #}
{% set q_lower = query|lower %}
{% set name_lower = result.name|lower %}
{% if q_lower in name_lower %}
  {% set idx = name_lower.find(q_lower) %}
  {{ result.name[:idx] }}<strong class="font-semibold">{{ result.name[idx:idx + query|length] }}</strong>{{ result.name[idx + query|length:] }}
{% else %}
  {{ result.name }}
{% endif %}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTMX 1.x `hx-sse`/`hx-ws` in core | Extensions (`htmx-ext-sse`) loaded separately | HTMX 2.0 (mid-2024) | N/A — not using SSE for search |
| FTS as default Postgres search | `pg_trgm` for short-field substring search | Established best practice | Trigram wins for name-field live search; FTS wins for long-text document search |

**Deprecated/outdated:**
- `to_tsquery('term')` for live prefix search: Works but requires the `:*` suffix `to_tsquery('term:*')` for prefix matching, and doesn't handle mid-string "et" → "Ethiopia" gracefully. Use ILIKE for this use case.
- `bleach` for HTML sanitization: Deprecated since 2023; not used here (no user HTML input).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gin_trgm_ops` is the correct operator class for pg_trgm GIN indexes in Postgres 16 | Index DDL | Migration fails with `ERROR: operator class "gin_trgm_ops" does not exist` — fix is to verify against Postgres 16 docs |
| A2 | `hx-sync="this:replace"` syntax is unchanged in HTMX 2.x | HTMX Wiring | Search fires duplicate concurrent requests — fix: verify against HTMX 2.x changelog |
| A3 | Six queries each completing in <5ms at <1000 rows gives p95 < 100ms total | Query Shape | p95 > 100ms at actual data sizes — fix: profile with EXPLAIN ANALYZE and add LIMIT pushdown |
| A4 | `func.similarity()` in SQLAlchemy 2.0 calls pg_trgm's `similarity()` Postgres function | Query Shape | ORDER BY fails with undefined function — fix: test against live DB |
| A5 | `markupsafe.escape()` returns a `Markup`-typed object that Jinja2 trusts | Highlight | Double-escaping of result text — fix: verify markupsafe 2.x API |

**All remaining claims are VERIFIED from codebase reads or HIGH confidence from Jinja2/SQLAlchemy/HTMX training knowledge validated against the existing code patterns.**

---

## Open Questions

1. **Recipe "description" gap**
   - What we know: `recipes` table has no `description` column; CONTEXT.md says "recipe name + description"
   - What's unclear: Should `grind_setting` be the secondary search field for recipes? Or should a `description` column be added in this phase's migration?
   - Recommendation: Search `name` only for recipes in v1 (no schema change); use `grind_setting` as context text (D-05). If John wants recipe description search, it requires adding a `description TEXT` column to `recipes` in the migration — this is a scope increase and should be confirmed.

2. **`roasters.archived` field in search**
   - What we know: Roaster model has `archived` column (per schema). CONTEXT.md D-12 only mentions coffees and equipment for the archived badge. 
   - What's unclear: Should archived roasters appear in results? Should they show a badge?
   - Recommendation: Include all roasters regardless of archived state (match SEARCH-02 "roaster names" without exclusion qualifier). If a roaster is archived, show the badge for consistency with D-12 spirit. Low risk either way — the planner should decide.

3. **`flavor_notes.archived` field**
   - Same as above — D-12 names only coffees and equipment. Include all; badge on archived for consistency.
   - Recommendation: Include all.

---

## Environment Availability

This phase is code/config/SQL only. No new external services. Postgres 16 with pg_trgm and unaccent already available in the running container. Skipping formal environment table.

---

## Validation Architecture

`workflow.nyquist_validation: true` in `.planning/config.json` — section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (install into container: `pip install --user pytest pytest-asyncio respx`) |
| Config file | none (see CLAUDE.md — pytest not baked into production image; install before testing) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_search.py -x -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEARCH-01 | Search header renders on authenticated pages, absent on `/login` and `/setup` | integration | `pytest tests/test_search.py::test_header_auth_gate -x` | ❌ Wave 0 |
| SEARCH-01 | Desktop input renders inline at >=768px (visual/structural) | manual | 375px Playwright smoke — manual verification | N/A |
| SEARCH-02 | Search returns coffees matching by name | integration | `pytest tests/test_search.py::test_search_coffees -x` | ❌ Wave 0 |
| SEARCH-02 | Search returns roasters matching by name | integration | `pytest tests/test_search.py::test_search_roasters -x` | ❌ Wave 0 |
| SEARCH-02 | Search returns recipes matching by name | integration | `pytest tests/test_search.py::test_search_recipes -x` | ❌ Wave 0 |
| SEARCH-02 | Search returns equipment matching by brand+model | integration | `pytest tests/test_search.py::test_search_equipment -x` | ❌ Wave 0 |
| SEARCH-02 | Search returns flavor notes matching by name | integration | `pytest tests/test_search.py::test_search_flavor_notes -x` | ❌ Wave 0 |
| SEARCH-03 | Results grouped in fixed order (D-07) | unit | `pytest tests/test_search.py::test_result_group_order -x` | ❌ Wave 0 |
| SEARCH-03 | Each result links to correct entity URL (D-11) | unit | `pytest tests/test_search.py::test_result_links -x` | ❌ Wave 0 |
| SEARCH-03 | Empty query (<2 chars) returns empty response | integration | `pytest tests/test_search.py::test_short_query_empty -x` | ❌ Wave 0 |
| SEARCH-04 | User A cannot see User B's brew notes in results | integration | `pytest tests/test_search.py::test_brew_note_user_scoping -x` | ❌ Wave 0 (CRITICAL — IDOR) |
| SEARCH-04 | User A can see shared catalog (coffees, roasters) in results | integration | `pytest tests/test_search.py::test_shared_catalog_visible -x` | ❌ Wave 0 |
| D-06 | Highlight does not use `|safe` on user input (static analysis) | unit | `pytest tests/test_search.py::test_highlight_xss_safe -x` | ❌ Wave 0 |
| D-06 | Highlight wraps match in `<strong>` correctly | unit | `pytest tests/test_search.py::test_highlight_markup -x` | ❌ Wave 0 |
| D-09 | Per-group cap: <=5 results shown, "+N more" when 6th exists | unit | `pytest tests/test_search.py::test_group_cap -x` | ❌ Wave 0 |
| D-12 | Archived coffees appear in results with "Archived" badge | integration | `pytest tests/test_search.py::test_archived_coffee_badge -x` | ❌ Wave 0 |

### Critical Test: SEARCH-04 User Scoping (IDOR)

This test is the most important correctness invariant. It must assert:
1. User B logs a brew session with `notes="secret Ethiopia mango"`
2. User A searches for "mango"
3. User A's results contain zero brew notes
4. User B searches for "mango" — gets their own brew note

```python
# Test shape (Wave 0 gap)
def test_brew_note_user_scoping(client_user_a, client_user_b, db, seed_coffee):
    # User B logs a brew with distinctive notes
    brew_b = create_brew_session(db, user_id=user_b.id, notes="secret Ethiopia mango", ...)
    # User A searches
    resp = client_user_a.get("/search?q=mango")
    assert resp.status_code == 200
    assert "secret Ethiopia mango" not in resp.text
    # User B searches own notes
    resp = client_user_b.get("/search?q=mango")
    assert "secret Ethiopia mango" in resp.text
```

### Sampling Rate

- **Per task commit:** `pytest tests/test_search.py -x -q`
- **Per wave merge:** `pytest tests/ -q` (full suite, per memory: `full-suite-test-isolation-gaps` — drop snobbery_test before full run)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_search.py` — all SEARCH-01..04 unit and integration tests
- [ ] Seeded test fixtures for cross-user scoping test (two users + brew sessions with notes)
- [ ] `highlight_match()` helper unit test (XSS: query = `<script>alert(1)</script>`)

---

## Security Domain

`security_enforcement` not explicitly false in config — section required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `require_user` dependency on `GET /search` — unauthenticated returns 401 |
| V3 Session Management | no | Search is read-only GET; session middleware already handles this globally |
| V4 Access Control | yes | `WHERE brew_sessions.user_id = :user_id` — per-user scoping; SEARCH-04 IDOR defense |
| V5 Input Validation | yes | `len(q.strip()) < 2` guard; query passed as parameterized SQLAlchemy bind (no raw string interpolation into SQL) |
| V6 Cryptography | no | No encryption in this phase |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR: User A viewing User B's brew notes | Information Disclosure | `WHERE brew_sessions.user_id = :current_user_id` — always first WHERE clause per analytics.py pattern |
| XSS via search result highlight | Tampering | `markupsafe.escape()` on all text fragments; `Markup` composition only adds literal `<strong>` tag |
| SQL injection via `q` parameter | Tampering | SQLAlchemy parameterized bind for ILIKE pattern (`%{query}%` as a bound parameter, never string interpolation) |
| Unauthenticated search of user brew notes | Information Disclosure | `require_user` dependency; returns 401 for unauthenticated requests |
| Search endpoint cache poisoning | Information Disclosure | `Cache-Control: no-store` + `Vary: HX-Request` prevents any caching of user-scoped results |

**SQL injection note:** The `pattern = f"%{query}%"` construction in Python is safe ONLY when passed as a SQLAlchemy bound parameter (e.g., `Column.ilike(pattern)` where `pattern` is a Python variable bound via psycopg). It would be unsafe if interpolated into a raw SQL string. Always use `Column.ilike(pattern)` or `text("... ILIKE :pattern").bindparams(pattern=pattern)` — never `text(f"... ILIKE '{pattern}'")`).

---

## Sources

### Primary (HIGH confidence)
- `app/models/coffee.py` — confirmed `coffees` schema: name (CITEXT), archived (bool), roaster_id (FK), origin/country/process/roast_level are context fields
- `app/models/recipe.py` — confirmed: NO `description` column; `name` (Text) is the only searchable field
- `app/models/equipment.py` — confirmed: NO `name` column; `brand` (Text) + `model` (Text) are the identity fields
- `app/models/brew_session.py` — confirmed: `notes` (Text), `user_id` (BigInteger, NOT NULL), `brewed_at` (TIMESTAMP)
- `app/models/roaster.py` — confirmed: `name` (CITEXT unique), `archived` (bool)
- `app/models/flavor_note.py` — confirmed: `name` (CITEXT unique), `archived` (bool)
- `app/migrations/versions/0001_initial.py` — confirmed: `pg_trgm` and `unaccent` installed at lines 60-62
- `app/migrations/versions/p4_shared_catalog.py` — confirmed GIN index DDL pattern: `op.execute("CREATE INDEX ... ON ... USING GIN ...")`
- `app/templates/base.html` — confirmed: no persistent header; login/setup extend it; script load order
- `app/templates/pages/login.html` — confirmed: `{% extends "base.html" %}`
- `app/templates/pages/setup.html` — confirmed: `{% extends "base.html" %}`
- `app/static/css/tailwind.src.css` — confirmed: `.htmx-indicator` rules already present (lines 22-25)
- `app/static/js/htmx-listeners.js` — confirmed: `Alpine.initTree` after HTMX settle; CSRF header on all requests
- `app/templates/fragments/autocomplete_list.html` — confirmed: existing safe highlight pattern using Jinja template splitting (no `|safe`)
- `app/middleware/fragment_cache.py` — confirmed: `HX-Request: true` triggers `Cache-Control: no-store` + `Vary: HX-Request`
- `app/main.py` — confirmed router registration pattern + admin router already included
- `.planning/config.json` — confirmed: `nyquist_validation: true`
- `.planning/phases/10-global-search/10-CONTEXT.md` — locked decisions D-01..D-12
- `.planning/phases/10-global-search/10-UI-SPEC.md` — visual contract, HTMX attribute table, Alpine component spec

### Secondary (MEDIUM confidence)
- Training knowledge of `pg_trgm` GIN index behavior for 2-char vs 3-char queries — consistent with PostgreSQL 16 documentation behavior
- Training knowledge of SQLAlchemy 2.0 `func.similarity()` calling Postgres `similarity()` function — standard pattern

### Tertiary (LOW confidence)
- A1-A5 in Assumptions Log above — all flagged and manageable

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries/extensions verified in codebase; no new dependencies
- Architecture: HIGH — brownfield; all patterns verified against existing code
- Pitfalls: HIGH — columns confirmed from actual model files; pitfalls 1 and 2 are definite facts
- FTS vs trigram recommendation: MEDIUM-HIGH — reasoning is sound but p95 claim is estimated, not measured

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (30 days — stack is stable)
