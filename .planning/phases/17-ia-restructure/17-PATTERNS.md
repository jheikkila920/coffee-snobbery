# Phase 17: IA Restructure - Pattern Map

**Mapped:** 2026-05-27
**Files analyzed:** 13 (6 modified + 7 new)
**Analogs found:** 13 / 13 (100% — pure IA reshuffle; every new file has a direct codebase analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| **MOD** `app/routers/home.py` | router (view handler) | request-response | self (current handler, lines 40-66) | self-edit |
| **MOD** `app/routers/ai.py` | router (page shell + sub-routes) | request-response | `app/routers/home.py:40-66` `home_shell` + `app/routers/home.py:220-288` `card_ai_recommendation` | exact |
| **MOD** `app/services/analytics.py` | service (SQL aggregation) | CRUD (read) | self (`get_top_coffees` lines 48-74) | self-edit |
| **MOD** `app/templates/base.html` | layout (persistent nav) | template-render | self (lines 244-291 bottom nav, 91-98 top nav) | self-edit |
| **MOD** `app/templates/pages/home.html` | page template | template-render | self (lines 1-178) | self-edit (composition rewrite) |
| **MOD** `app/templates/pages/config_hub.html` | page template | template-render | self (catalog grid lines 14-52) | self-edit (append) |
| **MOD** `app/static/js/alpine-components/nav-bar.js` | alpine component (route gating) | client-state | self (`activeTab` getter lines 19-33) | self-edit |
| **MOD** `app/templates/fragments/home/_cold_start.html` | fragment | template-render | self (full file — relocate to `fragments/ai/`) | move |
| **NEW** `app/templates/pages/ai.html` | page template | template-render | `app/templates/pages/home.html` (whole-file shape) | exact (above-gate branch directly mirrors lines 65-170) |
| **NEW** `app/templates/fragments/ai_key_setup_banner.html` | fragment (admin nudge banner) | template-render + client-state | `app/templates/base.html:313-326` (iOS install banner) + `app/static/js/alpine-components/ios-banner.js` | exact pattern, different storage scope (sessionStorage vs localStorage) |
| **NEW** `app/templates/fragments/ai/_no_key_admin_callout.html` | fragment (empty-state callout) | template-render | `app/templates/fragments/home/_cold_start.html` (same section shape + CTA) + `app/templates/fragments/home/ai_rec_not_configured.html` (is_admin branch) | role-match |
| **NEW** `app/templates/fragments/ai/_no_key_non_admin_callout.html` | fragment (empty-state callout) | template-render | `app/templates/fragments/home/ai_rec_not_configured.html` (non-admin branch + copy treatment) | role-match |
| **NEW** `app/templates/fragments/research_coming_soon.html` | fragment (stub card) | template-render | `app/templates/pages/home.html:71-83` (AI hero card shape) | exact (smaller, disabled variant) |
| **NEW** `app/static/js/alpine-components/banner-dismiss.js` | alpine component | client-state (sessionStorage) | `app/static/js/alpine-components/ios-banner.js` (lines 1-49) | exact |

## Pattern Assignments

### MOD `app/routers/home.py` (router, request-response)

**Analog:** self — extend the existing `home_shell` to drop AI cards / add greeting + ai_key_present.

**Current handler shape** (`app/routers/home.py:37-66`):
```python
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home_shell(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the analytics home shell (Phase 6)."""
    gate = analytics.get_cold_start_counts(db, user.id)
    recent_brews = analytics.get_recent_brews(db, user.id)
    unrated_coffees = analytics.get_unrated_coffees(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="pages/home.html",
        context={
            "gate": gate,
            "recent_brews": recent_brews,
            "unrated_coffees": unrated_coffees,
        },
    )
```

**Imports already in place** (`app/routers/home.py:22-35`):
```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import ai_service, analytics
from app.services import credentials as credentials_service
from app.templates_setup import templates
```

**Phase 17 additions to home_shell context** (planner must add):
- `top_coffees = analytics.get_top_coffees(db, user.id, min_sessions=0)` — D-09 no-floor
- `ai_key_present = (credentials_service.get_provider_credential(db, "anthropic") is not None or credentials_service.get_provider_credential(db, "openai") is not None)` — for DIST-07 banner
- `greeting = derive_greeting(user.username)` — D-10 personalized greeting

---

### MOD `app/routers/ai.py` (router, request-response) — add `GET /ai`

**Analog:** `app/routers/home.py:220-288` `card_ai_recommendation` — the branching logic for "cold-start vs no-key vs ready" is already implemented; the new `GET /ai` handler is a lean version that selects which **page-level** branch to render rather than which **fragment** to return.

**Existing router prefix** (`app/routers/ai.py:47`):
```python
router = APIRouter(prefix="/ai")
```

**Existing route shape inside this router** (`app/routers/ai.py:54-68` — `get_paste_rank_page`):
```python
@router.get("/paste-rank", response_class=HTMLResponse)
def get_paste_rank_page(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Render the paste-and-rank page (empty form, no results)."""
    return templates.TemplateResponse(
        request=request,
        name="pages/paste_rank.html",
        context={"status": None, "results": None},
    )
```

**Canonical AI-key-presence check pattern to copy** (`app/routers/home.py:240-255`):
```python
gate = analytics.get_cold_start_counts(db, user.id)
if not gate["gate_open"]:
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/ai_rec_cold_start.html",
        context={"gate": gate},
    )

# AI-16: not configured when both providers return None
anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
openai_cred = credentials_service.get_provider_credential(db, "openai")
if anthropic_cred is None and openai_cred is None:
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/ai_rec_not_configured.html",
        context={"user": user},
    )
```

**Imports for ai.py already in place** (`app/routers/ai.py:30-40` — `credentials_service` NOT yet imported, must add):
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import ai_service
# ADD: from app.services import analytics
# ADD: from app.services import credentials as credentials_service
from app.templates_setup import templates
```

**Mount-at-prefix-root convention** — `@router.get("")` mounts at exactly `/ai` since `prefix="/ai"`. Insert immediately after line 47, before the first existing handler.

---

### MOD `app/services/analytics.py` (service, CRUD-read) — add `min_sessions` parameter

**Analog:** self — `get_top_coffees` lines 48-74. Single-parameter signature change; preserve all callers (only `card_top_coffees` in `home.py:145` calls it, with no kwarg, so the default keeps the existing floor).

**Current implementation** (`app/services/analytics.py:48-74`):
```python
def get_top_coffees(db: Session, user_id: int) -> list[Row]:
    """Return <=5 coffees ranked by the user's avg rating, min 2 rated sessions.

    Excludes NULL ratings (Pitfall 1). Tie-broken avg_rating DESC, then
    session_count DESC (Claude's Discretion).
    """
    # CAFE-04 not applicable: cafe coffees have no row in coffees table by design (D-14).
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

**Returns:** `list[Row]` where each row exposes `.id`, `.name`, `.avg_rating` (float, from `func.avg`), `.session_count` (int, from `func.count`). Coffees table only — cafe data NOT unioned by design (D-14 from Phase 16).

**Callers in repo today:** ONE — `app/routers/home.py:145` `card_top_coffees` (calls with positional args only). Adding `min_sessions: int = 2` keyword-only parameter is backward compatible.

**Phase 17 patch** (per RESEARCH §"Adding the no-floor parameter"):
```python
def get_top_coffees(db: Session, user_id: int, *, min_sessions: int = 2) -> list[Row]:
    # ... same select() chain ...
    .group_by(Coffee.id, Coffee.name)
    .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
    .limit(5)
)
if min_sessions > 0:
    stmt = stmt.having(func.count(BrewSession.id) >= min_sessions)
return db.execute(stmt).all()
```

---

### MOD `app/templates/base.html` (layout) — bottom-nav slot swap + top-nav link order

**Analog:** self — bottom nav block lines 244-291, top nav block lines 91-98.

**Bottom-nav slot pattern to copy** (`app/templates/base.html:251-258` — the Home tab — exact shape for AI tab):
```html
{# Home tab #}
<a href="/"
   class="flex flex-col items-center justify-center gap-1 flex-1 min-h-[44px] min-w-[44px]"
   :class="activeTab === 'home' ? 'text-espresso-700 dark:text-cream-100' : 'text-espresso-400 dark:text-espresso-400'">
  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>
  </svg>
  <span class="text-xs">Home</span>
</a>
```

**Admin slot to REMOVE** (`app/templates/base.html:279-289`):
```html
{# Admin tab — hidden for non-admins (MOB-02) #}
{% if request.state.user.is_admin %}
<a href="/admin"
   class="flex flex-col items-center justify-center gap-1 flex-1 min-h-[44px] min-w-[44px]"
   :class="activeTab === 'admin' ? 'text-espresso-700 dark:text-cream-100' : 'text-espresso-400 dark:text-espresso-400'">
  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
  </svg>
  <span class="text-xs">Admin</span>
</a>
{% endif %}
```

The shield icon path is reusable for the Admin entry card on `/config` (D-17).

**Top-nav link pattern** (`app/templates/base.html:91-98`):
```html
<nav class="flex items-center gap-5">
  <a href="/" class="text-sm font-semibold text-espresso-600 dark:text-espresso-300 hover:text-espresso-900 dark:hover:text-cream-100">Home</a>
  <a href="/brew" class="text-sm font-semibold text-espresso-600 dark:text-espresso-300 hover:text-espresso-900 dark:hover:text-cream-100">Log</a>
  <a href="/config" class="text-sm font-semibold text-espresso-600 dark:text-espresso-300 hover:text-espresso-900 dark:hover:text-cream-100">Config</a>
  {% if request.state.user.is_admin %}
  <a href="/admin" class="text-sm font-semibold text-espresso-600 dark:text-espresso-300 hover:text-espresso-900 dark:hover:text-cream-100">Admin</a>
  {% endif %}
</nav>
```

Phase 17 inserts `<a href="/ai">AI</a>` between Log and Config (D-01); Admin link stays per D-18.

---

### MOD `app/templates/pages/home.html` (page template) — composition rewrite

**Analog:** self — current home composition lines 1-178.

**Header / action-row pattern to keep / modify** (`app/templates/pages/home.html:8-35`):
```html
<main class="mx-auto max-w-6xl px-6 py-12">
  <header class="flex flex-wrap items-center justify-between gap-4 mb-6">
    <h1 class="text-2xl font-semibold">Home</h1>
    <div class="flex items-center gap-3">
      {# D-03: minimal admin entry link — is_admin-gated; full nav is Phase 11 #}
      {% if request.state.user and request.state.user.is_admin %}
        <a href="/admin"
           class="flex-1 inline-flex items-center justify-center rounded border border-espresso-300 dark:border-espresso-600 px-4 py-2 text-base font-semibold min-h-[44px] hover:bg-espresso-100 dark:hover:bg-espresso-800">
          Admin
        </a>
      {% endif %}
      <a href="/recipes"
         class="flex-1 inline-flex items-center justify-center rounded border border-espresso-300 dark:border-espresso-600 px-4 py-2 text-base font-semibold min-h-[44px] hover:bg-espresso-100 dark:hover:bg-espresso-800">
        Guided Brew
      </a>
      <a href="/brew/new"
         class="flex-1 inline-flex items-center justify-center rounded bg-espresso-700 px-4 py-2 text-base font-semibold min-h-[44px] text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
        Log session
      </a>
    </div>
  </header>
```

**Phase 17 changes to this header:**
- Replace `<h1 class="text-2xl font-semibold">Home</h1>` with `<h1 class="text-2xl font-semibold">{{ greeting }}</h1>` (D-10).
- DELETE the Admin button (`request.state.user.is_admin` block) — admins now reach Admin from `/config` (D-07 / IA-01).
- ADD a third `<a href="/cafe-logs/new">Quick rate</a>` button using the same `flex-1 inline-flex ...` shape (D-06, symmetric with `/brew` header from Phase 16 D-09).

**Card section pattern** (`app/templates/pages/home.html:41-45` — Recent brews eager include):
```html
<section aria-labelledby="recent-brews-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="recent-brews-heading" class="text-xl font-semibold mb-4">Recent brews</h2>
  {% include "fragments/home/recent_brews.html" %}
</section>
```

Same section wrapper shape (`rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800`) is the universal home card shape. Top Coffees on Phase 17 home shifts to this eager include shape (D-08).

**HTMX lazy-load mount pattern** (`app/templates/pages/home.html:47-59` — Unrated coffees):
```html
<section aria-labelledby="unrated-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="unrated-heading" class="text-xl font-semibold mb-4">Not tried yet</h2>
  <div hx-get="/home/cards/unrated-coffees"
       hx-trigger="load delay:150ms"
       hx-swap="innerHTML">
    <div class="animate-pulse space-y-2">
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
      <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
    </div>
  </div>
</section>
```

This is the canonical lazy-mount pattern reused on `/ai` for Preference Profile, Flavor Descriptors, Sweet Spots, AI hero (delays staggered 100/200/300/500/600ms — see existing values in `home.html:117-170`).

**Sections to REMOVE from home** (`app/templates/pages/home.html:61-170`):
- The whole `{% if not gate.gate_open %} {% include "fragments/home/_cold_start.html" %} {% else %} ... {% endif %}` block (D-11 — meter leaves home, no above/below-gate branch on home).
- Lines 71-83 — AI "What to buy next" hero (`hx-get="/home/cards/ai-recommendation"`).
- Lines 87-115 — AI tools section (paste-rank link + wishlist link + equipment form).
- Lines 133-144 — Preference Profile card.
- Lines 146-157 — Top Flavor Descriptors card.
- Lines 159-170 — Sweet Spots card.

**Sections that STAY or MIGRATE on home:**
- Recent brews (lines 41-45) — stays eager.
- Unrated coffees / Not tried yet (lines 47-59) — stays lazy.
- Top Coffees (lines 120-131) — **shifts from lazy to eager** (D-08), uses new no-floor query.
- NEW: small "See AI recommendations →" text link below Top Coffees (D-06).
- NEW: Wishlist entry (link/card) — kept on home (D-06 / D-12 reversal).
- NEW: DIST-07 banner include at top (D-19).

---

### MOD `app/templates/pages/config_hub.html` (page template) — append Admin section

**Analog:** self — catalog grid lines 14-52.

**Catalog card shape to copy** (`app/templates/pages/config_hub.html:14-21` — Coffees card):
```html
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
  <a href="/coffees"
     class="flex items-center gap-3 rounded-xl border border-espresso-200 dark:border-espresso-700 bg-cream-100 dark:bg-espresso-900 px-4 py-4 min-h-[44px] hover:bg-cream-200 dark:hover:bg-espresso-800 transition-colors">
    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-espresso-700 dark:text-cream-100 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
    </svg>
    <span class="text-base font-semibold text-espresso-900 dark:text-cream-100">Coffees</span>
  </a>
```

**Mobile sign-out block boundary** (`app/templates/pages/config_hub.html:54-58` — where the Admin entry section MUST be inserted ABOVE):
```html
{# Mobile-only: account identity + sign-out (D-03, MOB-01).
   Desktop users sign out via the account dropdown in the top nav. #}
<div class="md:hidden mt-8 border-t border-espresso-200 dark:border-espresso-700 pt-6">
  <p class="text-sm text-espresso-600 dark:text-cream-300">Signed in as</p>
  <p class="text-base font-semibold text-espresso-900 dark:text-cream-100 mb-4">{{ user.username }}</p>
```

**Phase 17 insertion point:** between the closing `</div>` of the catalog grid at line 52 and the `<div class="md:hidden mt-8 ...">` at line 56. New section is `is_admin`-gated, NOT `md:hidden` (D-17 — admins on desktop reach Admin from here too). Shield icon path comes from `base.html:285`.

---

### MOD `app/static/js/alpine-components/nav-bar.js` (alpine component)

**Analog:** self — `activeTab` getter lines 19-33.

**Current getter** (`app/static/js/alpine-components/nav-bar.js:19-33`):
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('navBar', () => ({
    // active tab derived from pathname — no eval needed
    get activeTab() {
      const p = window.location.pathname;
      if (p === '/' || p.startsWith('/home')) return 'home';
      if (p.startsWith('/brew')) return 'brew';
      if (p.startsWith('/config') || p.startsWith('/coffees') ||
          p.startsWith('/equipment') || p.startsWith('/recipes') ||
          p.startsWith('/roasters') || p.startsWith('/flavor-notes')) return 'config';
      if (p.startsWith('/admin')) return 'admin';
      return '';
    },
  }));
});
```

**Phase 17 patch (per D-05):**
- ADD `if (p.startsWith('/ai')) return 'ai';` BEFORE the `/config` branch (so `/ai/paste-rank`, `/ai/wishlist` etc. all match `'ai'`, not `'config'`).
- REMOVE `if (p.startsWith('/admin')) return 'admin';` (bottom-nav admin tab is gone).

---

### MOD `app/templates/fragments/home/_cold_start.html` → MOVE to `app/templates/fragments/ai/_cold_start.html`

**Analog:** self (move).

**Existing fragment** (full file, `app/templates/fragments/home/_cold_start.html:1-49`):
```html
{# Cold-start empty state (gate not cleared: sessions < 3 OR distinct_notes < 5).
   Context: gate dict from analytics.get_cold_start_counts():
     gate.sessions         — total sessions (including unrated, D-02)
     gate.distinct_notes   — distinct observed flavor notes
     gate.sessions_needed  — max(0, 3 - sessions)
     gate.notes_needed     — max(0, 5 - notes)
   Progress meter: server-computed pct from live counts (D-03, no Alpine).
   All values autoescaped. CSP-clean. #}

{% set sessions_done = [gate.sessions, 3] | min %}
{% set notes_done = [gate.distinct_notes, 5] | min %}
{% set pct = ((sessions_done + notes_done) / 8 * 100) | round | int %}

<section aria-labelledby="cold-start-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="cold-start-heading" class="text-xl font-semibold mb-4">Build your taste profile.</h2>

  <div class="mb-4">
    <div class="h-2 rounded-full bg-espresso-200 dark:bg-espresso-800 overflow-hidden"
         role="progressbar"
         aria-valuenow="{{ pct }}"
         aria-valuemin="0"
         aria-valuemax="100"
         aria-label="Profile completion">
      <div class="h-2 rounded-full bg-espresso-700" style="width: {{ pct }}%"></div>
    </div>
  </div>

  <p class="text-base mb-2">
    {% if gate.sessions_needed > 0 and gate.notes_needed > 0 %}
      Log {{ gate.sessions_needed }} more brew{% if gate.sessions_needed != 1 %}s{% endif %} and add {{ gate.notes_needed }} more flavor note{% if gate.notes_needed != 1 %}s{% endif %} to unlock insights.
    {% elif gate.sessions_needed == 0 and gate.notes_needed > 0 %}
      Add {{ gate.notes_needed }} more flavor note{% if gate.notes_needed != 1 %}s{% endif %} to your brews to unlock insights.
    {% else %}
      Log {{ gate.sessions_needed }} more brew{% if gate.sessions_needed != 1 %}s{% endif %} to unlock insights.
    {% endif %}
  </p>

  <p class="text-sm text-espresso-600 dark:text-cream-300 mb-4">
    In the meantime, your recent brews and catalog are below.
  </p>

  <a href="/brew/new"
     class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
    Log session
  </a>
</section>
```

**Phase 17 changes:**
- `git mv app/templates/fragments/home/_cold_start.html app/templates/fragments/ai/_cold_start.html` to preserve blame.
- Update second `<p>` copy from "In the meantime, your recent brews and catalog are below." to "AI personalization activates after 3 sessions and 5 distinct flavor notes." (D-14 one-line explainer).
- Existing CTA "Log session" already matches D-14 — keep.
- Drop the `home.html` include at line 64; the new `pages/ai.html` mounts this fragment.

**`gate` dict shape** (consumed by template, produced by `analytics.get_cold_start_counts`, line 378+): `gate.sessions`, `gate.distinct_notes`, `gate.sessions_needed`, `gate.notes_needed`, `gate.gate_open`.

---

### NEW `app/templates/pages/ai.html` (page template)

**Analog:** `app/templates/pages/home.html` (whole file). The `pages/ai.html` is the home template's above-gate branch (`home.html:65-170`) lifted into a dedicated page, plus the new no-key callout branch.

**Page skeleton to copy** (`app/templates/pages/home.html:1-8`):
```html
{% extends "base.html" %}
{% block page_title %}Home{% endblock %}
{% block content %}
  {# Analytics home page (Phase 6). ... #}
  <main class="mx-auto max-w-6xl px-6 py-12">
    <header class="flex flex-wrap items-center justify-between gap-4 mb-6">
      <h1 class="text-2xl font-semibold">Home</h1>
```

For `pages/ai.html`: `{% block page_title %}AI{% endblock %}`, `<h1>AI</h1>` (or skip — D-12 doesn't require a heading specifically).

**Branch structure to mirror** (`app/templates/pages/home.html:61-173`):
```html
{# Cold-start gate: below-gate users see the progress meter; above-gate users
   see the AI top-hero card (D-01) + five staggered aggregate cards (HOME-09). #}
{% if not gate.gate_open %}
  {% include "fragments/home/_cold_start.html" %}
{% else %}
  {# AI hero #}
  <section aria-labelledby="ai-rec-heading"
           class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
    <h2 id="ai-rec-heading" class="text-xl font-semibold mb-4">What to buy next</h2>
    <div id="ai-rec-hero"
         hx-get="/home/cards/ai-recommendation"
         hx-trigger="load delay:600ms"
         hx-swap="outerHTML">
      <div class="animate-pulse space-y-2">
        <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
        <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
      </div>
    </div>
  </section>
  {# Preference Profile, Flavor Descriptors, Sweet Spots — same lazy-mount shape #}
{% endif %}
```

**Phase 17 three-branch structure for `pages/ai.html`:**
```html
{% include "fragments/ai_key_setup_banner.html" %}  {# DIST-07, admin-gated inside fragment #}

{% if not gate.gate_open %}
  {% include "fragments/ai/_cold_start.html" %}     {# D-14 #}
{% elif not ai_key_present %}
  {% if request.state.user.is_admin %}
    {% include "fragments/ai/_no_key_admin_callout.html" %}      {# D-15 #}
  {% else %}
    {% include "fragments/ai/_no_key_non_admin_callout.html" %}  {# D-16 #}
  {% endif %}
{% else %}
  {# AI hero, Preference Profile, Flavor Descriptors, Sweet Spots, AI tools, Research stub #}
  {# Copy verbatim from home.html lines 71-115 and 133-170 #}
  {% include "fragments/research_coming_soon.html" %}
{% endif %}
```

**Card section wrapper** — same shape used everywhere: `rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800` (D-Claude's-discretion: card layout). AI page mounts the existing `/home/cards/*` endpoints with no URL rename (RESEARCH §"Alternatives Considered" / project memory `c9-sw-cache-content-deterministic` — keep URLs to minimize SW cache churn).

---

### NEW `app/templates/fragments/ai_key_setup_banner.html` (fragment, DIST-07)

**Analog:** `app/templates/base.html:313-326` (iOS install banner) — same Alpine `x-data` + `x-show` + dismiss-button shape, scoped via sessionStorage instead of localStorage (per D-19 "reappears on next visit").

**iOS banner shape to mirror** (`app/templates/base.html:313-326`):
```html
<div x-data="iosBanner"
     x-show="show"
     style="display: none"
     class="fixed bottom-16 left-0 right-0 z-30 bg-espresso-900 text-cream-100 px-4 py-3 text-sm flex items-center justify-between md:hidden">
  <p class="flex-1 pr-3">Add to Home Screen: tap the share icon then &ldquo;Add to Home Screen&rdquo; for the best experience.</p>
  <button
    x-on:click="dismiss()"
    aria-label="Dismiss"
    class="flex items-center justify-center min-h-[44px] min-w-[44px] shrink-0 text-cream-100">
    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
    </svg>
  </button>
</div>
```

**Important Alpine CSP-build rule** — `x-data="bannerDismiss"` is a string reference (NOT `x-data="{ ... }"`); the `@alpinejs/csp` build rejects inline object literals (see `app/static/js/alpine-components/ios-banner.js` header comment lines 7-10).

**Phase 17 fragment shape (per RESEARCH Pattern 5):**
```html
{% if request.state.user.is_admin and not ai_key_present %}
<div x-data="bannerDismiss"
     x-show="!dismissed"
     style="display: block"
     class="mx-auto max-w-6xl px-6 mt-4">
  <div class="flex items-start justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:bg-amber-900/20 dark:border-amber-700">
    <div class="flex-1">
      <p class="text-base font-semibold text-espresso-900 dark:text-cream-100">
        Welcome — add your AI API key in Admin to enable recommendations.
      </p>
      <a href="/admin/credentials"
         class="mt-2 inline-flex items-center rounded bg-espresso-700 px-3 py-1.5 text-sm font-semibold text-cream-50 hover:bg-espresso-800 min-h-[44px]">
        Go to Admin
      </a>
    </div>
    <button x-on:click="dismiss()" aria-label="Dismiss banner"
            class="flex items-center justify-center min-h-[44px] min-w-[44px] text-espresso-700 dark:text-cream-100">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>
  </div>
</div>
{% endif %}
```

**Context required from view:** `ai_key_present: bool` (passed in by `home_shell` and `ai_page` handlers).

---

### NEW `app/static/js/alpine-components/banner-dismiss.js`

**Analog:** `app/static/js/alpine-components/ios-banner.js` (full file lines 1-49) — same `Alpine.data` registration, `init()` reads storage, `dismiss()` writes storage. Substitute `sessionStorage` for `localStorage`.

**Full pattern to copy and adapt** (`app/static/js/alpine-components/ios-banner.js:18-48`):
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('iosBanner', () => ({
    show: false,

    init() {
      // Already dismissed — never show again.
      if (localStorage.getItem('snobbery:ios-banner-dismissed')) return;

      const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
      const isStandalone = window.navigator.standalone === true ||
                           window.matchMedia('(display-mode: standalone)').matches;

      if (isIOS && !isStandalone) {
        this.show = true;
      }
    },

    dismiss() {
      this.show = false;
      try {
        localStorage.setItem('snobbery:ios-banner-dismissed', '1');
      } catch (_e) {
        // Private mode or quota exceeded — banner will reappear next visit
      }
    },
  }));
});
```

**Phase 17 banner-dismiss.js (per RESEARCH Pattern 5):**
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('bannerDismiss', () => ({
    dismissed: false,
    init() {
      this.dismissed = sessionStorage.getItem('snobbery:dist07-dismissed') === '1';
    },
    dismiss() {
      this.dismissed = true;
      try {
        sessionStorage.setItem('snobbery:dist07-dismissed', '1');
      } catch (_e) {
        // Storage quota / privacy mode — banner reappears next page-load
      }
    },
  }));
});
```

**Registration in base.html** — add a new `<script defer src="/static/js/alpine-components/banner-dismiss.js" nonce="{{ csp_nonce(request) }}"></script>` next to the existing component registrations at `base.html:46-48`, BEFORE the `@alpinejs/csp` core script at line 60.

---

### NEW `app/templates/fragments/ai/_no_key_admin_callout.html` (D-15)

**Analog:** `app/templates/fragments/home/_cold_start.html` (same section card shape + CTA shape) AND `app/templates/fragments/home/ai_rec_not_configured.html` (the admin-gated message + link).

**Existing "not configured" fragment to extend** (`app/templates/fragments/home/ai_rec_not_configured.html:1-12` — full file):
```html
{# "AI not configured" state — no provider credential is enabled (AI-16).
   Renders gracefully for all users; admin sees a configure link.
   Context: user — User (for is_admin check).
   CSP-clean. All values autoescaped. #}

<p class="text-sm text-espresso-600 dark:text-cream-300">
  AI recommendations are not configured yet.
  {% if user.is_admin %}
    <a href="/admin/settings" class="underline hover:text-espresso-800 dark:hover:text-cream-100">Configure a provider</a>.
  {% endif %}
</p>
```

**Section card wrapper from cold-start (to copy for layout-parity per D-15)** (`fragments/home/_cold_start.html:15-17`):
```html
<section aria-labelledby="cold-start-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="cold-start-heading" class="text-xl font-semibold mb-4">Build your taste profile.</h2>
```

**Phase 17 admin callout shape (D-15: different headline, different icon, primary button, same container size):**
```html
<section aria-labelledby="no-key-admin-heading"
         class="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:bg-amber-900/20 dark:border-amber-700 min-h-[14rem]">
  <div class="flex items-start gap-3">
    {# Key icon — distinct from cold-start's progress meter. Use a key/lock outline (24x24, stroke-currentColor). #}
    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-amber-700 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 7a2 2 0 11-4 0 2 2 0 014 0zm6 1a8 8 0 11-16 0 8 8 0 0116 0z"/>
    </svg>
    <div class="flex-1">
      <h2 id="no-key-admin-heading" class="text-xl font-semibold mb-2">AI keys needed</h2>
      <p class="text-base mb-4">Add an API key in Admin to unlock AI recommendations for the household.</p>
      <a href="/admin/credentials"
         class="inline-flex items-center rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 min-h-[44px]">
        Go to Admin
      </a>
    </div>
  </div>
</section>
```

**Per RESEARCH Pitfall F:** Add `min-h-[14rem]` (or computed match) so layout doesn't jump when a user transitions from below-gate to above-gate-no-key. Verify identical computed height with the cold-start fragment at 375px viewport.

---

### NEW `app/templates/fragments/ai/_no_key_non_admin_callout.html` (D-16)

**Analog:** `app/templates/fragments/home/ai_rec_not_configured.html` (non-admin branch — the message-only variant without the configure link).

**Same section wrapper as the admin callout** (D-15 / Pitfall F: same container size). Body copy per D-16:
```html
<section aria-labelledby="no-key-non-admin-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800 min-h-[14rem]">
  <div class="flex items-start gap-3">
    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-espresso-700 dark:text-cream-100 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 7a2 2 0 11-4 0 2 2 0 014 0zm6 1a8 8 0 11-16 0 8 8 0 0116 0z"/>
    </svg>
    <div class="flex-1">
      <h2 id="no-key-non-admin-heading" class="text-xl font-semibold mb-2">AI is not set up</h2>
      <p class="text-base text-espresso-700 dark:text-cream-200">
        Ask the household admin to configure an API key.
      </p>
      {# No Admin link (they'd 403). No "Notify admin" button (no notification system v1). #}
    </div>
  </div>
</section>
```

D-16 explicit: NO Admin link (non-admins get 403 on `/admin`), NO "Notify admin" button (no notification system).

---

### NEW `app/templates/fragments/research_coming_soon.html` (D-13 stub)

**Analog:** `app/templates/pages/home.html:71-83` (AI hero card shape — `<section ... rounded-lg border ...>` with `<h2>`).

**Stub card shape (small, disabled state per D-13):**
```html
<section aria-labelledby="research-stub-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800 opacity-60">
  <h2 id="research-stub-heading" class="text-xl font-semibold mb-2">Research a coffee</h2>
  <p class="text-base text-espresso-600 dark:text-cream-300">
    Coming in Phase 19 — paste a coffee URL or name and we'll surface roaster history, flavor profile, and a predicted rating.
  </p>
  <button type="button"
          disabled
          class="mt-3 inline-flex items-center rounded border border-espresso-300 dark:border-espresso-600 px-4 py-2 text-base font-semibold min-h-[44px] cursor-not-allowed text-espresso-400 dark:text-espresso-500">
    Coming soon
  </button>
</section>
```

D-13 explicit: single-line copy, disabled state, signals where the Phase 19 research/predict UI will land.

---

## Shared Patterns

### Authentication / authorization gating

**Source:** Established pattern across every authenticated route.

**View-handler dependency** (`app/routers/home.py:42-44` + `app/routers/ai.py:56-57`):
```python
user: User = Depends(require_user),  # noqa: B008
db: Session = Depends(get_session),  # noqa: B008
```

**Template-side `is_admin` gate** (`app/templates/base.html:95-97`, `app/templates/pages/home.html:18`):
```html
{% if request.state.user.is_admin %}
  ...admin-only content...
{% endif %}
```

**Apply to:** New `GET /ai` handler (gate on `require_user`); banner fragment, admin callout, Admin-entry config section (all gate on `request.state.user.is_admin`); non-admin callout renders unconditionally (when reached via the elif branch in `pages/ai.html`).

---

### CSP nonce on inline scripts and script registrations

**Source:** Universal — every `<script>` in `base.html` carries the nonce.

**Pattern** (`app/templates/base.html:32-51`):
```html
<script defer src="/static/js/alpine-components/recipe-step-builder.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/nav-bar.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/ios-banner.js" nonce="{{ csp_nonce(request) }}"></script>
```

**Apply to:** The new `banner-dismiss.js` registration must carry the nonce, inserted before the `@alpinejs/csp` core script at line 60.

---

### CSRF on state-changing forms

**Source:** `app/templates/base.html:161-166` (sign-out form), `app/templates/pages/home.html:102-112` (AI equipment form), `app/templates/pages/config_hub.html:59-65` (mobile sign-out).

**Pattern:**
```html
<form method="post" action="/logout">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  <button type="submit" ...>Sign out</button>
</form>
```

**Apply to:** None — Phase 17 introduces NO new state-changing forms. The DIST-07 banner dismiss is client-only (sessionStorage); the AIX-08 callout uses a plain `<a href>` link. No CSRF additions needed.

---

### Alpine.js CSP-build component registration

**Source:** `app/static/js/alpine-components/ios-banner.js:18-48` (canonical pattern); template usage at `app/templates/base.html:313` (`x-data="iosBanner"` — string reference, NOT inline object).

**Required template attribute pattern:** `x-data="componentName"` (string). NEVER `x-data="{ count: 0 }"` (inline object — rejected by `@alpinejs/csp`).

**Required JS registration pattern:**
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('componentName', () => ({
    field: defaultValue,
    init() { /* ... */ },
    method() { /* ... */ },
  }));
});
```

**Apply to:** The new `banner-dismiss.js` (mirrors `ios-banner.js` exactly).

---

### Template path / section card shape

**Source:** Universal home/page card wrapper (`app/templates/pages/home.html:42-43`):
```html
<section aria-labelledby="X-heading"
         class="rounded-lg border border-espresso-200 bg-cream-100 p-4 dark:bg-espresso-900 dark:border-espresso-800">
  <h2 id="X-heading" class="text-xl font-semibold mb-4">Title</h2>
  ...
</section>
```

**Apply to:** Every new card section on `pages/ai.html`, the relocated cold-start fragment, both no-key callout fragments, and the research-coming-soon stub. Maintains visual consistency without re-design (Phase 21 owns visual polish).

---

### Personalized greeting — server-side template context

**Source:** Established username surfacing across the app:
- `app/templates/base.html:146` — `<span>{{ request.state.user.username }}</span>` (top-nav account button)
- `app/templates/base.html:158` — same in dropdown panel
- `app/templates/pages/index.html:9` — `Signed in as {{ request.state.user.username }}`
- `app/templates/pages/config_hub.html:58` — `{{ user.username }}` (mobile sign-out block; `user` is passed in context)

**Pattern:** Templates access `request.state.user.username` directly (no view-context indirection). For the personalized greeting (D-10), the view handler computes the FULL greeting string (`"Good morning, john"`) server-side and passes it as `greeting`. The template renders `<h1>{{ greeting }}</h1>` with autoescape protecting `user.username`. **No client-side `new Date()` — Alpine CSP build rejects it (RESEARCH Pitfall A).**

**Apply to:** `home_shell` in `app/routers/home.py` — add a `greeting = derive_greeting(user.username)` line in the context. Helper lives in `app/routers/home.py` (or a new small `app/utils/greeting.py` — planner's call) per RESEARCH Pattern 4 (see TZ open question on `APP_TZ` env var vs hard-coded string).

---

### HTMX lazy-load card mount

**Source:** `app/templates/pages/home.html:51-58` (Unrated coffees), `120-130` (Top Coffees), `136-143` (Preference Profile), `149-156` (Flavor Descriptors), `162-169` (Sweet Spots).

**Canonical shape:**
```html
<div hx-get="/home/cards/X"
     hx-trigger="load delay:Yms"
     hx-swap="innerHTML">
  <div class="animate-pulse space-y-2">
    <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
    <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-1/2"></div>
  </div>
</div>
```

**Apply to:** New `pages/ai.html` mounts these endpoints with staggered delays (per RESEARCH Pattern 3):
- AI hero: `load delay:100ms` (drop from 600ms — hero is now the first card on `/ai`)
- Preference Profile: `load delay:200ms`
- Flavor Descriptors: `load delay:300ms`
- Sweet Spots: `load delay:500ms`
- AI tools (paste-rank / wishlist links): eager, no `hx-get`
- Equipment "Analyze my setup" button: eager, POST on click only

---

## Test Pattern (extend existing files; do NOT create new)

**Source:** `tests/test_nav.py` (existing nav-presence tests — extend), `tests/routers/test_home.py` (extend), `tests/routers/test_ai_router.py` (extend), `tests/services/test_analytics.py` (extend).

**Existing test function shape (per `tests/test_nav.py` line 26+):**
- `test_config_hub_returns_200_for_authenticated_user`
- `test_non_admin_home_has_no_admin_link`
- `test_admin_home_has_admin_link`
- `test_authenticated_home_has_nav_bar_component`

**Apply to:** Extend in place. Add Phase 17 assertions (per RESEARCH Validation Architecture table). Project memory `validation-md-vacuous-k-filters` — confirm each `-k` filter collects ≥1 test via `--collect-only`. Project memory `tests-pass-by-skip-mask-green` — run with `-rs` to surface skips.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | — |

**All 13 files in Phase 17 have a clear codebase analog.** This phase is a tightly-scoped IA reshuffle on a mature stack — RESEARCH §"Summary" confirms "Every locked decision in CONTEXT.md maps cleanly onto an existing pattern in the codebase — no new pattern needs to be invented."

---

## Metadata

**Analog search scope:**
- `app/routers/` (home.py, ai.py, auth.py)
- `app/templates/` (base.html, pages/home.html, pages/config_hub.html, fragments/home/*.html)
- `app/static/js/alpine-components/` (nav-bar.js, ios-banner.js, dark-toggle.js)
- `app/services/` (analytics.py, credentials.py)
- `tests/test_nav.py` (existing nav-presence tests)

**Files scanned:** 15
**Pattern extraction date:** 2026-05-27

---

*Phase: 17-ia-restructure*
*Pattern mapping complete: 2026-05-27*
