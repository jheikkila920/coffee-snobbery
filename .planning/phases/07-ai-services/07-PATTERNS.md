# Phase 7: AI Services - Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 14 (8 new, 6 modified)
**Analogs found:** 14 / 14

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/services/ai_service.py` | service | async request-response + CRUD | `app/services/credentials.py` + `app/services/analytics.py` | role-match (compound) |
| `app/services/wishlist.py` | service | CRUD | `app/services/brew_sessions.py` | exact |
| `app/routers/ai.py` | router | request-response + HTMX fragment | `app/routers/brew.py` + `app/routers/home.py` | exact |
| `app/routers/home.py` (extend) | router | HTMX fragment | `app/routers/home.py` (self) | exact |
| `app/templates/fragments/home/ai_rec_hero.html` | template | request-response | `app/templates/fragments/home/top_coffees.html` | role-match |
| `app/templates/fragments/home/ai_rec_in_flight.html` | template | event-driven (polling) | `app/templates/fragments/home/top_coffees.html` | role-match |
| `app/templates/fragments/home/ai_rec_cold_start.html` | template | request-response | `app/templates/fragments/home/_cold_start.html` | exact |
| `app/templates/fragments/home/ai_rec_not_configured.html` | template | request-response | `app/templates/fragments/home/_card_sparse.html` | role-match |
| `app/templates/fragments/home/ai_rec_try_again.html` | template | request-response | `app/templates/fragments/home/_card_sparse.html` | role-match |
| `app/templates/fragments/home/sweet_spots.html` (extend) | template | request-response | self (append at documented insert point line 5) | exact |
| `app/templates/pages/paste_rank.html` | template | request-response | `app/templates/pages/home.html` | role-match |
| `app/templates/pages/wishlist.html` | template | CRUD | `app/templates/pages/home.html` | role-match |
| `app/events.py` (extend) | config | event-driven | self (append after BREW_CSV_EXPORTED) | exact |
| `app/main.py` (extend — router registration) | config | request-response | self (append after `home_router`) | exact |

---

## Pattern Assignments

### `app/services/ai_service.py` (service, async request-response + CRUD)

**Analogs:** `app/services/credentials.py` (encrypted credential consumption, ProviderCredential handling, structlog pattern) + `app/services/analytics.py` (per-user DB reads, signature computation)

**Imports pattern** (`credentials.py` lines 50-70, `analytics.py` lines 1-35):
```python
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

import anthropic
import httpx
import openai
import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.events import (
    AI_FALLBACK_TRIGGERED,
    AI_GENERATION_ERROR,
    AI_GENERATION_START,
    AI_GENERATION_SUCCESS,
    AI_REGEN_SKIPPED,
    AI_THROTTLE_BLOCK,
    AI_TIER_FALLBACK,
    AI_URL_VERIFY,
)
from app.models.ai_recommendation import AIRecommendation
from app.models.wishlist_entry import WishlistEntry
from app.services import credentials as credentials_service
from app.services import settings as settings_service
from app.services.analytics import compute_input_signature

log = structlog.get_logger(__name__)
```

**ProviderCredential consumption pattern** (`credentials.py` lines 112-163):
```python
# CORRECT: call get_provider_credential, check None, consume cred.key only for SDK init
cred = credentials_service.get_provider_credential(db, "anthropic")
if cred is None:
    return "not_configured"  # drives the AI-not-configured UI state (AI-16)

# Pass cred.key only to the SDK constructor — never into Pydantic, never log it
client = anthropic.Anthropic(api_key=cred.key, max_retries=1)

# For structlog: cred.provider and cred.model_name are safe; cred.key is NOT
log.info(AI_GENERATION_START, provider=cred.provider, model=cred.model_name, user_id=user_id)
```

**Module-level lock + throttle state** (RESEARCH.md Pattern 7):
```python
# In-memory lock dict — process-local, sufficient for single uvicorn worker (AI-13)
_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
# Per-user last-refresh timestamps for 5-minute throttle (AI-14)
_THROTTLE: dict[int, float] = {}

def _get_lock(user_id: int, rec_type: str) -> asyncio.Lock:
    key = (user_id, rec_type)
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]

def _evict_stale_throttle(*, now: float, window_secs: float = 600.0) -> None:
    """Evict throttle entries older than window_secs to prevent unbounded growth."""
    stale = [uid for uid, ts in _THROTTLE.items() if now - ts > window_secs]
    for uid in stale:
        del _THROTTLE[uid]
```

**Postgres advisory lock** (`analytics.py` `text()` pattern, RESEARCH.md Pattern 7):
```python
def _advisory_key(user_id: int, rec_type: str) -> int:
    """Stable signed int64 from (user_id, rec_type) for pg_try_advisory_xact_lock."""
    raw = f"{user_id}:{rec_type}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)

def _try_advisory_lock(db: Session, user_id: int, rec_type: str) -> bool:
    key = _advisory_key(user_id, rec_type)
    row = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": key},
    ).scalar()
    return bool(row)
```

**`regenerate()` entry-point signature** (RESEARCH.md Pattern 9 — Phase 8 SCHED-02 contract):
```python
async def regenerate(
    user_id: int,
    generated_by: str,  # "scheduler" | "manual_refresh"
    *,
    db: Session,
    force: bool = False,  # bypass sig check; used by manual_refresh
) -> str:  # "generated" | "skipped" | "error" | "locked" | "try_again" | "not_configured"
    ...
```

**Settings consumption pattern** (`settings.py` public surface):
```python
# Read from module-level cache (no DB round-trip after prewarm)
primary_max_searches: int = settings_service.get_int("ai_primary_max_searches")  # 5
broadened_max_searches: int = settings_service.get_int("ai_broadened_max_searches")  # 3
tool_version: str = settings_service.get_str("ai_tool_version_anthropic")  # "web_search_20250305"
region: str = settings_service.get_str("recommendation_region")  # "US"
```

**Citation projector** (RESEARCH.md Pattern 1 — strip all non-tool_use blocks):
```python
def _project_tool_use_input(content: list, tool_name: str) -> dict:
    """Keep only the named tool_use block; strip all text/server_tool_use/web_search_tool_result blocks."""
    for block in content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input  # type: ignore[return-value]
    raise ValueError(f"No tool_use block with name={tool_name!r} in response")
```

**Anthropic tool definition** (RESEARCH.md Pattern 2):
```python
tools = [
    {
        "type": tool_version,          # from app_settings, e.g. "web_search_20250305"
        "name": "web_search",
        "max_uses": primary_max_searches,  # 5 for primary, 3 for broadened
        "user_location": {
            "type": "approximate",
            "country": region,         # "US"
        },
    },
    {
        "name": "structure_output",
        "description": "Return the structured recommendation",
        "input_schema": CoffeeRecSchema.model_json_schema(),  # Pydantic v2 built-in
    },
]
```

**Pydantic validation after projection** (RESEARCH.md Pattern 1):
```python
try:
    raw = _project_tool_use_input(response.content, "structure_output")
    rec = CoffeeRecSchema.model_validate(raw)
except (ValueError, ValidationError) as exc:
    log.warning(AI_GENERATION_ERROR, error_class=type(exc).__name__, user_id=user_id)
    # write ai_recommendations row with error_status="pydantic_error"
    return "try_again"
```

**Error handling / fallback predicate** (RESEARCH.md Pattern 4):
```python
import anthropic

NON_RETRYABLE = (
    anthropic.AuthenticationError,
    anthropic.BadRequestError,
    anthropic.PermissionDeniedError,
)

try:
    return await _call_anthropic(...)
except NON_RETRYABLE:
    return await _call_openai_fallback(...)
except anthropic.APIStatusError as exc:
    # 529 OverloadedError — also check str(exc) due to SDK streaming bug (#1258)
    if exc.status_code == 529 or "overloaded_error" in str(exc).lower():
        return await _call_openai_fallback(...)
    raise
```

**OpenAI fallback — prompt-based JSON, NOT json_schema** (RESEARCH.md Pattern 3 — CRITICAL):
```python
# DO NOT use text.format.json_schema with web_search_preview — silently disables web search
response = client.responses.create(
    model=cred.model_name,
    input=[{"role": "user", "content": prompt_with_json_instruction}],
    tools=[{"type": "web_search_preview"}],
)
text_out = ""
for item in response.output:
    if item.type == "message":
        for c in item.content:
            if c.type == "output_text":
                text_out = c.text
                break

try:
    raw = json.loads(text_out)
    rec = CoffeeRecSchema.model_validate(raw)
except (json.JSONDecodeError, ValidationError):
    return "try_again"
```

**URL verifier** (RESEARCH.md Pattern 6):
```python
VERIFY_UA = "Mozilla/5.0 (compatible; Snobbery/1.0; +https://github.com)"

async def _verify_buy_url(url: str, roaster_name: str, coffee_name: str) -> bool:
    if not url.startswith("https://"):
        return False  # SSRF: reject non-https (file://, http://, ftp://)
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,        # SSRF: no cross-host redirects
            timeout=httpx.Timeout(5.0),
        ) as client:
            r = await client.get(
                url,
                headers={"Range": "bytes=0-65535", "User-Agent": VERIFY_UA},
            )
        if r.status_code not in (200, 206):
            return False
        body = r.text.lower()
        return roaster_name.lower() in body or coffee_name.lower() in body
    except (httpx.TimeoutException, httpx.RequestError):
        return False
```

**AI telemetry write** (`ai_recommendation.py` columns verified):
```python
# Write the full ai_recommendations row every call (AI-02)
rec_row = AIRecommendation(
    user_id=user_id,
    recommendation_type=rec_type,      # "coffee" | "equipment" | "paste_rank" | "sweet_spots"
    input_signature=current_sig,
    response_json=rec.model_dump(),
    provider_used=cred.provider,
    model_used=cred.model_name,
    tool_version=tool_version,         # from app_settings — never hardcoded
    tokens_input=response.usage.input_tokens,
    tokens_output=response.usage.output_tokens,
    tokens_input_search=0,             # Anthropic does not expose this split in 0.102 (A1)
    web_search_count=getattr(getattr(response.usage, "server_tool_use", None), "web_search_requests", 0),
    url_verified=None,                 # populated later by background verify task
    duration_ms=int((time.monotonic() - start_ts) * 1000),
    generated_by=generated_by,         # "scheduler" | "manual_refresh"
    error_status=None,
)
db.add(rec_row)
db.commit()
```

**structlog emit pattern** (`credentials.py` lines 257-264, `brew_sessions.py` lines 39-49):
```python
log = structlog.get_logger(__name__)

# Every write transaction ends with a structlog emit (no emit on reads)
log.info(
    AI_GENERATION_SUCCESS,
    user_id=user_id,
    rec_type=rec_type,
    provider=cred.provider,      # safe
    model=cred.model_name,       # safe
    tier=search_tier,
    tokens_input=tokens_input,
    tokens_output=tokens_output,
    duration_ms=duration_ms,
    # NEVER: cred.key, cred.last_four in AI context, raw response_json with key fields
)
```

---

### `app/services/wishlist.py` (service, CRUD)

**Analog:** `app/services/brew_sessions.py` (closest per-user CRUD service)

**Imports pattern** (`brew_sessions.py` lines 29-49):
```python
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.wishlist_entry import WishlistEntry

log = structlog.get_logger(__name__)
```

**Per-user scoping pattern** (`brew_sessions.py` docstring lines 1-15, and every function):
```python
def add_to_wishlist(
    db: Session,
    *,
    by_user_id: int,            # ALWAYS a typed kwarg-after-star; never from form
    coffee_name: str,
    roaster_name: str | None,
    source_url: str | None,
    source: str = "ai_recommendation",
) -> WishlistEntry:
    entry = WishlistEntry(
        user_id=by_user_id,    # server-set, never from client
        coffee_name=coffee_name,
        roaster_name=roaster_name,
        source_url=source_url,
        source=source,
    )
    db.add(entry)
    db.commit()
    return entry

def list_wishlist(db: Session, *, by_user_id: int) -> list[WishlistEntry]:
    return db.execute(
        select(WishlistEntry)
        .where(WishlistEntry.user_id == by_user_id)  # IDOR defense: always filter by user_id
        .order_by(WishlistEntry.added_at.desc())
    ).scalars().all()

def get_wishlist_entry(db: Session, *, entry_id: int, by_user_id: int) -> WishlistEntry | None:
    """Return None (not 404) for cross-user entry_id — router maps sentinel to 404."""
    return db.execute(
        select(WishlistEntry)
        .where(
            WishlistEntry.id == entry_id,
            WishlistEntry.user_id == by_user_id,  # IDOR: cross-user id → None → 404
        )
    ).scalar_one_or_none()
```

**None → 404 sentinel pattern** (`brew.py` lines 824-826):
```python
# Service returns None on IDOR; router maps it to 404 (existence non-leak, not 403)
entry = wishlist_service.get_wishlist_entry(db, entry_id=entry_id, by_user_id=user.id)
if entry is None:
    raise HTTPException(status_code=404)
```

---

### `app/routers/ai.py` (router, request-response + HTMX fragment)

**Analog:** `app/routers/brew.py` (per-user HTMX router with IDOR + CSRF) + `app/routers/home.py` (fragment endpoints with `FragmentCacheHeadersMiddleware`)

**Imports and router setup** (`brew.py` lines 45-66, `home.py` lines 25-37):
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import ai_service
from app.services import wishlist as wishlist_service
from app.templates_setup import templates

router = APIRouter(prefix="/ai")
```

**Auth gate on every handler** (`home.py` lines 40-44, `brew.py` lines 473-478):
```python
@router.post("/refresh", response_class=HTMLResponse)
async def manual_refresh(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    # user_id ALWAYS from request.state.user.id — never a query param
    result = await ai_service.regenerate(user.id, "manual_refresh", db=db, force=True)
    ...
```

**HX-Request dual-render pattern** (`brew.py` lines 484-516):
```python
if request.headers.get("HX-Request") == "true":
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/ai_rec_hero.html",
        context={...},
    )
# Full page fallback (non-HTMX requests)
return templates.TemplateResponse(
    request=request,
    name="pages/home.html",
    context={...},
)
```

**HTMX fragment endpoint** (`home.py` lines 69-92):
```python
@router.get("/home/cards/ai-recommendation", response_class=HTMLResponse)
def card_ai_recommendation(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the AI recommendation hero card (AI-14, polling).

    FragmentCacheHeadersMiddleware adds no-store + Vary: HX-Request automatically.
    Returns spinner fragment (with hx-trigger="every 2s") while in-flight;
    returns hero card fragment (without hx-trigger) when complete.
    """
    gate = analytics.get_cold_start_counts(db, user.id)
    if not gate["gate_open"]:
        return templates.TemplateResponse(
            request=request, name="fragments/home/ai_rec_cold_start.html", context={"gate": gate}
        )
    # ... check in_flight lock, load latest rec, check stale badge, etc.
```

**HTMX 429 + HX-Retarget pattern** (RESEARCH.md locked decision):
```python
# Manual refresh while run is in-flight → 429 + HX-Retarget to "please wait"
return Response(
    status_code=429,
    headers={
        "HX-Retarget": "#ai-rec-hero",
        "HX-Reswap": "outerHTML",
    },
    content=templates.TemplateResponse(
        request=request,
        name="fragments/home/ai_rec_in_flight.html",
        context={},
    ).body,
)
```

**Wishlist POST routes** (`brew.py` lines 728-760, CSRF enforced by middleware):
```python
@router.post("/wishlist/add", response_class=HTMLResponse)
async def wishlist_add(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Add to wishlist — CSRF enforced by starlette-csrf middleware (never exempt)."""
    form = await request.form()
    # Parse coffee_name, roaster_name, source_url from form
    ...
    wishlist_service.add_to_wishlist(db, by_user_id=user.id, ...)
    return Response(status_code=204, headers={"HX-Trigger": "wishlistUpdated"})
```

**Router registration** (`main.py` lines 219-231):
```python
# In create_app(), after home_router include:
from app.routers import ai as ai_router
app.include_router(ai_router.router)
app.include_router(home_router.router)  # home.py also gets the new /home/cards/ai-recommendation endpoint
```

---

### `app/routers/home.py` (extend — AI hero slot)

**Analog:** Self — extend the existing sweet-spots pattern

**New fragment endpoint to add** (mirrors `card_sweet_spots` at lines 213-230):
```python
@router.get("/home/cards/ai-recommendation", response_class=HTMLResponse)
def card_ai_recommendation(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """AI hero card fragment — polling endpoint (AI-14).

    Returns one of five fragments: cold_start, not_configured, in_flight,
    try_again, or the hero card itself. FragmentCacheHeadersMiddleware
    applies no-store + Vary: HX-Request automatically.
    """
    gate = analytics.get_cold_start_counts(db, user.id)
    if not gate["gate_open"]:
        return templates.TemplateResponse(
            request=request,
            name="fragments/home/ai_rec_cold_start.html",
            context={"gate": gate},
        )
    # check credential, in_flight lock, latest rec, stale sig ...
```

**Insert point in `home.html`** (line 115 verified):
```html
{# Replace this comment (line 115) with the actual AI hero card section: #}
{# Phase 7: AI recommendation card slot — will use hx-get="/home/cards/ai-recommendation" hx-trigger="revealed" hx-swap="innerHTML". HOME-06. Do not implement here. #}

{# Replacement: #}
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
```

---

### `app/templates/fragments/home/ai_rec_hero.html` (template, request-response)

**Analog:** `app/templates/fragments/home/top_coffees.html` (list card body pattern)

**Card body pattern** (`top_coffees.html` lines 1-24):
```html
{# AI recommendation hero card. CSP-clean — no |safe, no hx-on:.
   Context: rec — AIRecommendation row; prose — CoffeeRecSchema fields;
            stale — bool; url_verified — bool|None. #}

{% if rec %}
  <div class="...">
    {# Coffee name and roaster — autoescaped, NEVER |safe #}
    <p class="text-base font-semibold">{{ prose.coffee_name }}</p>
    <p class="text-sm text-espresso-600">{{ prose.roaster_name }}</p>

    {# AI prose — plain text with <br> for newlines, NEVER |safe #}
    <p class="text-sm mt-2">{{ prose.summary_prose }}</p>

    {# Buy link — url_verified drives the UX state #}
    {% if prose.buy_url %}
      {% if rec.url_verified %}
        <a href="{{ prose.buy_url }}" ...>Buy</a>
      {% elif rec.url_verified is none %}
        <span class="text-xs text-espresso-400">verifying link...</span>
      {% else %}
        <span class="text-xs text-espresso-400">{{ prose.buy_url }} (couldn't verify)</span>
      {% endif %}
    {% endif %}

    {# Stale badge — shown when sig changed since last gen #}
    {% if stale %}
      <span class="text-xs text-amber-600">New brews logged — recommendations may be outdated</span>
    {% endif %}
  </div>
{% else %}
  {# No rec yet — spinner state handled by ai_rec_in_flight.html #}
{% endif %}
```

**Fragment polling trigger** (RESEARCH.md Pattern 8 — polling stops when hx-trigger absent):
```html
{# IN-FLIGHT: hx-trigger="every 2s" keeps polling until endpoint returns complete card #}
<div id="ai-rec-hero"
     hx-get="/home/cards/ai-recommendation"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  ...spinner...
</div>

{# COMPLETE: NO hx-trigger → polling stops after this swap #}
<div id="ai-rec-hero">
  ...hero card content...
</div>
```

---

### `app/templates/fragments/home/ai_rec_in_flight.html` (template, polling state)

**Analog:** Loading skeleton pattern from `home.html` lines 34-38:
```html
{# In-flight spinner fragment — includes hx-trigger so HTMX keeps polling.
   CSP-clean: spinner via Tailwind animate-pulse, no inline JS. #}
<div id="ai-rec-hero"
     hx-get="/home/cards/ai-recommendation"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  <div class="animate-pulse space-y-2">
    <div class="h-4 bg-espresso-100 dark:bg-espresso-800 rounded w-3/4"></div>
    <p class="text-sm text-espresso-500">Searching for your next coffee...</p>
  </div>
</div>
```

---

### `app/templates/fragments/home/ai_rec_cold_start.html` (template)

**Analog:** `app/templates/fragments/home/_cold_start.html` (exact same progress-meter pattern, already built in Phase 6):
```html
{# Cold-start state — gate not open; show progress meter.
   Context: gate dict from analytics.get_cold_start_counts()
   Mirror the _cold_start.html include already in home.html line 44. #}
{% include "fragments/home/_cold_start.html" %}
```

---

### `app/templates/fragments/home/ai_rec_not_configured.html` (template)

**Analog:** `app/templates/fragments/home/_card_sparse.html`:
```html
{# "AI not configured" state — no provider enabled (AI-16). CSP-clean. #}
<p class="text-sm text-espresso-600 dark:text-cream-300">
  AI recommendations are not configured yet.
  {% if user.is_admin %}<a href="/admin/settings" class="underline">Configure a provider</a>.{% endif %}
</p>
```

---

### `app/templates/fragments/home/ai_rec_try_again.html` (template)

**Analog:** `app/templates/fragments/home/_card_sparse.html`:
```html
{# "Try again" state — Pydantic validation failure (AI-04). CSP-clean. #}
<p class="text-sm text-espresso-600 dark:text-cream-300">
  Couldn't generate a recommendation right now.
</p>
<form method="post" action="/ai/refresh">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  <button type="submit" class="text-sm underline">Try again</button>
</form>
```

---

### `app/templates/fragments/home/sweet_spots.html` (extend — HOME-06)

**Analog:** Self — append after the `</ul>` close (line 22 verified as the documented insert point):
```html
{# Append after line 22 (after the </ul> or the {% else %} block ends): #}

{# HOME-06: AI sweet-spots prose — rendered only when a sweet_spots rec exists.
   Prose is PLAIN TEXT with <br> line breaks — NEVER |safe (SEC-05).
   Context: sweet_spots_prose — str | None (from the sweet_spots AIRecommendation row). #}
{% if sweet_spots_prose %}
  <div class="mt-4 pt-4 border-t border-espresso-100 dark:border-espresso-800">
    <p class="text-sm text-espresso-700 dark:text-cream-300">{{ sweet_spots_prose }}</p>
  </div>
{% endif %}
```

---

### `app/templates/pages/paste_rank.html` (template, dedicated page)

**Analog:** `app/templates/pages/home.html` (extends base.html, uses same card structure):
```html
{% extends "base.html" %}
{% block page_title %}Rank these coffees{% endblock %}
{% block content %}
  <main class="mx-auto max-w-6xl px-6 py-12">
    <h1 class="text-2xl font-semibold mb-6">Rank these for me</h1>

    {# Input form — CSRF from meta tag via htmx-listeners.js #}
    <form method="post" action="/ai/paste-rank">
      <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
      <textarea name="input_text" ...></textarea>
      <button type="submit">Rank</button>
    </form>

    {# Results — HTMX-swapped after POST or included on re-render #}
    {% if results %}
      {% for item in results.ranked %}
        <div>{{ item.rank }}. {{ item.name }} — {{ item.reasoning }}</div>
      {% endfor %}
    {% endif %}
  </main>
{% endblock %}
```

---

### `app/templates/pages/wishlist.html` (template, CRUD)

**Analog:** `app/templates/pages/home.html` card structure + `top_coffees.html` list pattern:
```html
{% extends "base.html" %}
{% block page_title %}Wishlist{% endblock %}
{% block content %}
  <main class="mx-auto max-w-6xl px-6 py-12">
    <h1 class="text-2xl font-semibold mb-6">Wishlist</h1>
    {% if entries %}
      <ul class="space-y-2">
        {% for entry in entries %}
          <li class="flex items-baseline justify-between gap-4 ...">
            <span>{{ entry.coffee_name }}{% if entry.roaster_name %} — {{ entry.roaster_name }}{% endif %}</span>
            <form method="post" action="/ai/wishlist/{{ entry.id }}/purchase">
              <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
              <button type="submit">Mark purchased</button>
            </form>
          </li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="text-sm text-espresso-600">No coffees saved yet.</p>
    {% endif %}
  </main>
{% endblock %}
```

---

### `app/events.py` (extend — `ai.*` taxonomy)

**Analog:** Self — append after `BREW_CSV_EXPORTED` (line 135) before `__all__`:

```python
# --- ai.* (Phase 7) -------------------------------------------------------
# AI generation lifecycle. Field shapes:
# - AI_GENERATION_START: user_id, rec_type, generated_by
# - AI_GENERATION_SUCCESS: user_id, rec_type, provider, model, tier, tokens_input, tokens_output, duration_ms
# - AI_GENERATION_ERROR: user_id, rec_type, error_class, error_status
# - AI_FALLBACK_TRIGGERED: user_id, rec_type, from_provider, reason
# - AI_TIER_FALLBACK: user_id, from_tier, to_tier, reason
# - AI_URL_VERIFY: user_id, rec_id, verified (bool)
# - AI_THROTTLE_BLOCK: user_id, seconds_remaining
# - AI_REGEN_SKIPPED: user_id, rec_type, reason="sig_unchanged"
AI_GENERATION_START = "ai.generation.start"
AI_GENERATION_SUCCESS = "ai.generation.success"
AI_GENERATION_ERROR = "ai.generation.error"
AI_FALLBACK_TRIGGERED = "ai.fallback.triggered"
AI_TIER_FALLBACK = "ai.tier.fallback"
AI_URL_VERIFY = "ai.url.verify"
AI_THROTTLE_BLOCK = "ai.throttle.block"
AI_REGEN_SKIPPED = "ai.regen.skipped"
```

Also add all 8 constants to `__all__` (follow the alphabetical insertion pattern at lines 138-183).

---

### Test files (Wave 0)

**Analog:** No existing AI service tests. Follow the import + fixture pattern from any future test in `tests/`.

**Test file structure** (RESEARCH.md Validation Architecture):
```python
# tests/services/test_ai_service.py
from __future__ import annotations
import pytest
import respx
import httpx
from unittest.mock import MagicMock, patch
from app.services import ai_service

# Unit tests use respx for httpx mocking + MagicMock for SDK clients
# No live DB needed for projector / throttle / schema tests
# DB tests use a transactional rollback fixture (Phase 12 formal suite)
```

---

## Shared Patterns

### Authentication Gate
**Source:** `app/dependencies/auth.py` lines 33-45
**Apply to:** All handlers in `app/routers/ai.py` + the new endpoint in `app/routers/home.py`
```python
def require_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user

# In every handler:
user: User = Depends(require_user),  # noqa: B008
# user_id ALWAYS from user.id — NEVER from query params or form
```

### IDOR Scoping (None → 404)
**Source:** `app/routers/brew.py` lines 824-826
**Apply to:** All wishlist handlers + any AI rec lookup by ID
```python
entry = wishlist_service.get_wishlist_entry(db, entry_id=entry_id, by_user_id=user.id)
if entry is None:
    raise HTTPException(status_code=404)  # 404 not 403 — existence non-leak
```

### CSRF on All State-Changing AI POSTs
**Source:** `app/templates/base.html` lines 9-10 + `app/routers/brew.py` (CSRF-enforced on every POST)
**Apply to:** Manual refresh, wishlist add/purchase/remove, paste-rank submit, equipment-rec generate
```html
{# starlette-csrf double-submit cookie — htmx-listeners.js reads meta tag and injects header #}
<meta name="csrf-token" content="{{ request.cookies.get('csrftoken', '') }}">

{# For non-HTMX forms (paste-rank, wishlist): also include the hidden field #}
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

### FragmentCacheHeadersMiddleware (automatic — no per-route config needed)
**Source:** `app/routers/home.py` docstring lines 19-21 + `app/routers/brew.py` line 487
**Apply to:** Every fragment endpoint returning `HX-Request: true` responses
```python
# FragmentCacheHeadersMiddleware applies Cache-Control: no-store + Vary: HX-Request
# automatically on HX-Request: true responses. No per-route header config needed.
# The middleware is already wired in main.py line 215.
```

### No `|safe` on AI Prose
**Source:** `CLAUDE.md` architectural invariants + `app/templates/base.html` comment line 1
**Apply to:** Every template that renders AI-generated text (`summary_prose`, `reasoning`)
```html
{# CORRECT: autoescaped plain text #}
<p>{{ prose.summary_prose }}</p>

{# WRONG: NEVER do this for AI prose #}
<p>{{ prose.summary_prose | safe }}</p>
```

### structlog Emit Pattern
**Source:** `app/services/credentials.py` lines 257-264 + `app/services/brew_sessions.py` lines 39-49
**Apply to:** `ai_service.py` + `wishlist.py` on every write transaction
```python
log = structlog.get_logger(__name__)

# End of successful write transaction:
log.info(EVENT_CONSTANT, field1=value1, field2=value2)
# NEVER log: cred.key, raw API responses that might embed the key, session tokens
```

### Pydantic v2 Schema Conventions
**Source:** `app/schemas/brew_session.py` lines 1-60
**Apply to:** All per-flow AI response schemas in `ai_service.py`
```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field

class CoffeeRecSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejects unexpected LLM fields

    coffee_name: str = Field(description="Full coffee name as sold")
    summary_prose: str = Field(description="1-2 sentence reasoning (D-04)")
    # ... other fields

# Use model_json_schema() for the Anthropic tool input_schema — NOT a hand-rolled dict
tool_input_schema = CoffeeRecSchema.model_json_schema()
```

### SQLAlchemy 2.0 Select Pattern
**Source:** `app/services/analytics.py` lines 52-70, `app/services/credentials.py` lines 140-143
**Apply to:** All DB reads in `ai_service.py` + `wishlist.py`
```python
# Typed Mapped[] columns + select() constructs — no legacy Query API
row = db.execute(
    select(AIRecommendation)
    .where(
        AIRecommendation.user_id == user_id,           # IDOR: always filter by user_id first
        AIRecommendation.recommendation_type == rec_type,
    )
    .order_by(AIRecommendation.generated_at.desc())
    .limit(1)
).scalar_one_or_none()
```

### Alpine.js CSP-Safe Component Pattern
**Source:** `app/templates/base.html` lines 13-31 (component scripts load before alpine-csp core)
**Apply to:** Any interactive AI card elements (stale-badge toggle, wishlist add confirmation)
```html
{# Register component in /static/js/alpine-components/<name>.js BEFORE alpine-csp loads #}
{# In base.html, add the script tag before the alpine-csp cdn line: #}
<script defer src="/static/js/alpine-components/ai-rec-card.js" nonce="{{ csp_nonce(request) }}"></script>

{# In the template, use x-data with registered component name: #}
<div x-data="aiRecCard({ ... })">
  ...
</div>

{# NEVER: hx-on:click="..." or x-on:click with eval #}
```

---

## No Analog Found

All files have close analogs in the codebase. No greenfield patterns without a reference.

| File | Note |
|---|---|
| `app/services/ai_service.py` | Compound analog (credentials + analytics + brew_sessions). The async LLM call path has no exact analog — use the RESEARCH.md patterns directly for the Anthropic/OpenAI SDK calls, citation projector, and advisory lock. |
| `tests/services/test_ai_service.py` | No AI service tests exist yet. RESEARCH.md Validation Architecture section defines the test structure and required mocking approach (respx for httpx, MagicMock for SDK clients). |

---

## Metadata

**Analog search scope:** `app/services/`, `app/routers/`, `app/templates/`, `app/models/`, `app/dependencies/`, `app/events.py`, `app/main.py`
**Files scanned:** 18
**Pattern extraction date:** 2026-05-20
