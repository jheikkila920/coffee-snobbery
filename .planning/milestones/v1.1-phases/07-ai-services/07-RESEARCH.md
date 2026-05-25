# Phase 7: AI Services - Research

**Researched:** 2026-05-20
**Domain:** AI provider abstraction, web-search tool integration, citation projection, HTMX polling, Postgres advisory locks, SSRF mitigation
**Confidence:** HIGH (Anthropic docs verified via official site; OpenAI verified via source inspection; codebase verified directly)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Provider:** Anthropic default, OpenAI fallback only on non-retryable errors (`AuthenticationError`, `BadRequestError`, `PermissionDeniedError`, persistent `OverloadedError` after one retry); SDK clients built with `max_retries=1` (AI-01).
- **Three-tier fallback:** primary (origin + process + roast level) → broadened (relax process → roast level → origin, in that order) → characteristics-only (no specific bean, no URL); response indicates which tier produced it (AI-03).
- **Delivery:** HTMX polling, not SSE, in v1. Manual refresh while a run is in flight → 429 + HX-Retarget to a "please wait" message.
- **Citation handling:** citation/tool-result blocks projected/stripped before Pydantic validation (AI-04); schema mismatch → "Try again" UI, never garbled JSON.
- **URL verification:** ranged GET (not HEAD), realistic User-Agent, body-contains-roaster-or-coffee-name check, no cross-host redirects, 5s timeout; unverified URL renders as plain text with a "couldn't verify" note (AI-05).
- **Recipe suggestion:** picks from the user's existing `recipes` ranked by historical avg rating for matching origin + process + roast level; never invents; if none match, says so and links to the recipe builder (AI-06).
- **Locking:** in-memory per-`(user_id, recommendation_type)` lock + Postgres advisory-lock backstop (AI-13); single uvicorn worker makes the in-memory lock process-local and the advisory lock the real cross-process guard.
- **Cost controls (load-bearing):** signature-based regen (helper exists), 5-minute manual-refresh throttle (AI-14, COST-2), `max_uses` 5 primary / 3 broadened from `app_settings` (AI-17, COST-5), `recommendation_region=US` scoping. Signature = content hash of the user's OWN rated sessions only (COST-4).
- **Cold-start gate:** <3 sessions OR <5 distinct observed flavor notes → progress meter, no AI section (AI-11). Already built in Phase 6.
- **Schemas:** per-flow Pydantic validation; every response schema includes a `summary_prose` field (AI-18).
- **Telemetry:** every call writes the full `ai_recommendations` row including token splits and `web_search_count` (AI-02).
- **Home page AI surface (D-01):** top-hero placement, above analytics aggregate cards.
- **Single hero pick (D-02):** one confident coffee recommendation per user, not a shortlist.
- **Voice (D-03):** confident expert, lightly wry — never performative. System-prompt concern only.
- **Tight prose (D-04):** 1-2 sentences per `summary_prose` field.
- **Equipment rec on-demand (D-05):** "analyze my setup" button/card; never scheduled.
- **Coffee rec + sweet-spots prose = cached nightly bundle (D-06).**
- **Paste-and-rank on dedicated page (D-07).**
- **Paste-rank accepts text AND URLs (D-08):** detect and fetch URLs via ranged-GET machinery.
- **Wishlist: Add hook + minimal view (D-09).**
- Anthropic `web_search_20250305` (basic) is the v1 tool version per Tech Stack §4; value lives in `app_settings.ai_tool_version_anthropic`.
- Out of scope: nightly scheduling (Phase 8), admin credential vault (Phase 9), nav/PWA (Phase 11), formal test suite under `respx` (Phase 12).

### Claude's Discretion
- Coffee-rec card composition (fields + layout for the hero card).
- URL-verify UX timing (render immediately with "verifying..." OR block on first paint).
- `ai_recommendations` row shape for the cached bundle (separate `sweet_spots` row vs. embedded).
- Route/module layout (`app/routers/ai.py` vs. extending `home.py`).
- `regenerate()` entry-point signature (design for Phase 8 scheduler contract).
- Default model IDs (read from `api_credentials.model_name`; sensible fallback documented, not hardcoded).
- Paste-rank URL extraction depth.
- `ai.*` event taxonomy in `app/events.py`.

### Deferred Ideas (OUT OF SCOPE)
- 3-pick home shortlist.
- Full snob persona prose.
- Bundled nightly equipment-rec card on home.
- Full wishlist CRUD (reorder, tags, auto-move-to-catalog).
- Per-user/month AI cost ceiling.
- SSE streaming for AI responses (v1.1 polish).
- Auto-surfacing equipment rec when weak link detected.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AI-01 | Provider abstraction; Anthropic default, OpenAI fallback on non-retryable errors; `max_retries=1`; tool versions from `app_settings` | Error class taxonomy confirmed; `OverloadedError` is 529; SDK auto-retries 429/5xx by default but `max_retries=1` limits to one retry before raising |
| AI-03 | Three-tier web-search fallback (primary → broadened → characteristics-only); response indicates tier | Tool `max_uses` param confirmed on web_search_20250305; tier indication goes in response schema |
| AI-04 | Citation/tool-result blocks stripped before Pydantic validation; schema mismatch → "Try again" | Citations are INLINE fields on `text` content blocks (not separate block type); server_tool_use + web_search_tool_result blocks also need filtering; see §Citation Projection Pattern |
| AI-05 | Ranged GET URL verification; realistic UA; body-contains-name check; no cross-host redirect; 5s timeout | httpx `follow_redirects=False`, `Range: bytes=0-65535`, `Timeout(5.0)` confirmed |
| AI-06 | Recipe suggestion from existing recipes; never invents | Pure SQL query over `recipes` + `brew_sessions`; no LLM call for this sub-flow |
| AI-07 | Alt-brewer callout when ≥0.5 rating delta for different brewer on matching bean style | SQL aggregation; conditionally included in coffee-rec composite |
| AI-08 | Equipment rec (profile-only, no web search) | Separate LLM call; no web-search tool; read user's equipment from DB |
| AI-09 | Paste-and-rank (on-demand, never cached, never scheduled); top 3 with reasoning | URL detection + ranged-GET fetch; then single LLM call with user log context |
| AI-10 | Sweet-spots prose generated alongside coffee rec; cached together | One regeneration transaction writes both rows; `recommendation_type='sweet_spots'` is a separate row (cleaner telemetry) |
| AI-11 | Cold-start gate (<3 sessions or <5 flavor notes) → progress meter | `get_cold_start_counts()` exists; gate logic already in `home.py` |
| AI-12 | Signature-based regeneration; signature = user's own rated sessions only | `compute_input_signature()` exists in `analytics.py`; returns SHA256 hex |
| AI-13 | In-memory + Postgres advisory lock backstop | `asyncio.Lock` keyed by `(user_id, recommendation_type)` + `pg_try_advisory_xact_lock` via `text()` |
| AI-14 | Manual refresh throttle: 1 per 5 min per user; spinner during run | Per-user timestamp cache (module-level dict, process-local, sufficient for single worker) |
| AI-15 | Stale-indicator badge when current sig ≠ stored sig | Compare `compute_input_signature()` vs. latest `ai_recommendations.input_signature` |
| AI-16 | Graceful "AI not configured" when no provider enabled | `get_provider_credential()` returns None; drives empty-state template branch |
| AI-17 | `max_uses` 5/3 from `app_settings`; configurable | `get_int("ai_primary_max_searches")` / `get_int("ai_broadened_max_searches")` |
| AI-18 | Per-flow Pydantic schemas; every schema has `summary_prose` | Pydantic v2 `model_validate` on extracted `tool_use` input; ValidationError → "Try again" |
| HOME-06 | AI prose interpretation below Sweet Spots when available | Attach to `fragments/home/sweet_spots.html` template; separate `sweet_spots` AI rec row |
</phase_requirements>

---

## Summary

Phase 7 builds Snobbery's core differentiator: a provider-agnostic AI service that generates grounded, web-search-backed coffee recommendations from each user's actual brew log. The domain spans three distinct engineering concerns that must be cleanly separated.

**Concern 1 — Anthropic SDK integration:** The web search tool (`web_search_20250305`) is a server-executed tool; Claude controls when to invoke it. Citations appear as inline `citations` fields on `text` content blocks — NOT as a separate block type. The response also contains `server_tool_use` and `web_search_tool_result` blocks that must be filtered before Pydantic validation. The correct structured-output pattern is a custom `tool_use` schema (a second tool in the tools list whose `input_schema` defines the desired JSON) alongside the web-search server tool; Claude calls both. Extract the `tool_use` input block and validate it against Pydantic — ignore all other block types.

**Concern 2 — OpenAI Responses API fallback:** The Responses API web search tool (`web_search_preview`) and JSON structured output have a well-documented incompatibility (web_search is silently ignored when strict structured output is combined). The correct fallback pattern is: use `client.responses.create` with `tools=[{"type": "web_search_preview"}]` and parse the `output_text` of the response message item as JSON via prompt-based instruction (not schema enforcement), then validate with Pydantic. This is lower-fidelity than Anthropic's approach but is the only viable OpenAI fallback path.

**Concern 3 — Concurrency and cost discipline:** The single-uvicorn-worker constraint makes an in-memory `asyncio.Lock` dict the primary concurrency guard; the Postgres advisory lock is a cross-process backstop for any future scale-out or debugging scenario. The 5-minute manual-refresh throttle is per-user, stored in a module-level dict (process-local, sufficient for single worker). Signature-based regeneration and `max_uses` caps are the primary cost controls; no token ceiling is added in v1.

**Primary recommendation:** Build `app/services/ai_service.py` as the single owner of all AI flow logic. Use `app/routers/ai.py` for AI-specific routes (refresh, in-flight poll, equipment rec, paste-rank, wishlist). Extend `app/routers/home.py` only for the home-shell slot that lazy-loads the AI hero card. Keep the citation projector and URL verifier as private helpers within `ai_service.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Provider credential lookup | API / Backend (`credentials.py`) | — | Decrypted key never exits service layer |
| AI flow execution (LLM calls) | API / Backend (`ai_service.py`) | — | Async SDK calls; DB reads/writes sync |
| URL verification (ranged GET) | API / Backend (`ai_service.py`) | — | Background task after rec is cached |
| Signature computation | API / Backend (`analytics.py`) | — | Already implemented; pure SQL |
| Concurrency locks | API / Backend (`ai_service.py`) | DB (advisory lock) | In-memory primary; Postgres backstop |
| Throttle tracking | API / Backend (module-level dict) | — | Single worker; no Redis needed |
| HTMX polling / in-flight state | Frontend Server (Jinja templates + router) | Browser (HTMX) | hx-trigger="every 2s" until complete |
| AI hero card rendering | Frontend Server (home router + fragments) | — | Fragment endpoint returns HTML |
| Wishlist writes | API / Backend (`wishlist.py`) | DB | Simple CRUD; user-scoped |
| Cost telemetry persistence | API / Backend (`ai_service.py`) | DB (`ai_recommendations`) | Every call writes a row |
| Cold-start gate | API / Backend (`analytics.py`) | Frontend Server (home shell) | Gate data computed in shell render |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | `>=0.102,<1.0` | Primary AI provider SDK | Fast cadence; 0.102 current (May 2026) |
| openai | `>=2.37,<3.0` | Fallback provider SDK | Responses API + web_search |
| httpx | `>=0.28,<0.29` | URL verification + any outbound HTTP | Already in stack; async + sync |
| pydantic | `>=2.13,<3.0` | Per-flow response schema validation | Already in stack |
| asyncio | stdlib | In-memory lock keyed by `(user_id, type)` | Single worker; no extra dep |
| sqlalchemy | `>=2.0.49,<2.1` | Advisory lock via `text()`, DB writes | Already in stack |

[VERIFIED: CLAUDE.md §1 Pinned Stack; PyPI registry current versions confirmed in CLAUDE.md]

**Installation:** No new dependencies required. All libraries are already in `requirements.txt`.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | `>=25.5,<26` | `ai.*` event emission | Every AI flow success/failure/fallback |
| hashlib | stdlib | Lock key derivation (SHA256 → int64) | Advisory lock key from `(user_id, type)` |

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (375px)
    |
    | hx-get="/home/cards/ai-recommendation"
    | hx-trigger="load delay:600ms" (initial)
    | hx-trigger="every 2s" (while in_flight)
    v
home router [GET /home/cards/ai-recommendation]
    |
    +-- check cold_start gate --> cold_start fragment (no LLM)
    |
    +-- check in_flight lock --> in_flight fragment (spinner)
    |
    +-- load latest rec from DB --> stale? show badge
    |
    +-- gate_open + no rec OR stale + manual refresh
         |
         v
    ai_service.regenerate(user_id, generated_by)
         |
         +-- acquire asyncio.Lock (user_id, "coffee")
         +-- pg_try_advisory_xact_lock (derived int64)
         +-- compute_input_signature() --> compare stored sig
         +-- skip if unchanged (unless manual_refresh)
         |
         +-- get_provider_credential("anthropic") --> None? try "openai"
         |
         +-- [Anthropic path]
         |    |
         |    +-- Tier 1: web_search_20250305 (max_uses=5)
         |    |   + custom tool_use schema
         |    |   --> response.content filter:
         |    |       - strip server_tool_use blocks
         |    |       - strip web_search_tool_result blocks
         |    |       - find tool_use block where name=="structure_output"
         |    |       --> Pydantic validate tool_use.input
         |    |
         |    +-- Tier 2: broadened (relax constraints, max_uses=3)
         |    |
         |    +-- Tier 3: characteristics-only (no URL, no web_search)
         |    |
         |    +-- ValidationError at all tiers --> error_status="pydantic_error"
         |    |
         |    +-- non-retryable error --> try OpenAI fallback
         |
         +-- [OpenAI fallback path]
         |    |
         |    +-- client.responses.create (web_search_preview)
         |    +-- parse output_text as JSON via prompt instruction
         |    +-- Pydantic validate --> ValidationError = "Try again"
         |
         +-- write ai_recommendations row (provider, tokens, tier, etc.)
         |
         +-- background: URL verification (ranged GET, 5s)
         |    --> update ai_recommendations.url_verified
         |
         +-- release locks
         |
         v
    home router serves cached rec fragment
         |
         v
Browser swaps hero card (HTMX hx-swap="outerHTML")
```

### Recommended Project Structure
```
app/
├── services/
│   ├── ai_service.py        # NEW: all AI flow logic, projector, verifier
│   └── wishlist.py          # NEW: add / list / mark-purchased / remove
├── routers/
│   ├── ai.py                # NEW: /ai/refresh, /ai/poll, /ai/equipment,
│   │                        #      /ai/paste-rank, /ai/wishlist/*
│   └── home.py              # EXTEND: add AI hero card slot endpoint
├── templates/
│   ├── fragments/home/
│   │   ├── ai_rec_hero.html         # NEW: hero card + stale badge
│   │   ├── ai_rec_in_flight.html    # NEW: spinner / "searching..."
│   │   ├── ai_rec_cold_start.html   # NEW: progress meter (or reuse _cold_start.html)
│   │   ├── ai_rec_not_configured.html # NEW: "AI not configured" state
│   │   ├── ai_rec_try_again.html    # NEW: Pydantic validation failure state
│   │   └── sweet_spots.html         # MODIFY: append AI prose block (HOME-06)
│   └── pages/
│       ├── paste_rank.html          # NEW: dedicated paste-and-rank page
│       └── wishlist.html            # NEW: minimal wishlist view
└── events.py                # EXTEND: ai.* event constants
```

### Pattern 1: Citation Projection (AI-04 — CRITICAL)

**What:** The Anthropic web search response content array contains mixed block types. Only `tool_use` blocks (where `name` matches the custom structured-output tool) contain the Pydantic-validated payload. All other blocks must be discarded before validation.

**When to use:** Every Anthropic AI flow that combines web_search with a custom tool_use schema.

**Verified content block types in a web_search + tool_use response:**
```
response.content = [
  TextBlock(type="text", text="I'll search for...", citations=None),
  ServerToolUseBlock(type="server_tool_use", name="web_search", ...),  # STRIP
  WebSearchToolResultBlock(type="web_search_tool_result", ...),         # STRIP
  TextBlock(type="text", text="Based on results...", citations=[...]),  # STRIP (has citations inline)
  ToolUseBlock(type="tool_use", name="structure_output", input={...}),  # KEEP → validate
]
```

[VERIFIED: Anthropic official docs — platform.claude.com/docs/en/docs/build-with-claude/tool-use/web-search-tool — citations are INLINE fields on text blocks, NOT a separate content block type]

**Citation handling finding (resolves STATE.md research flag):** Citations appear as a `citations` field on individual `text` content blocks (each citation is a `web_search_result_location` with `url`, `title`, `encrypted_index`, `cited_text`). There is NO separate "citation" block type in the content array. The projector strips all blocks except `tool_use` blocks named for the custom schema — this automatically discards all citation-bearing text blocks without special citation-detection logic.

```python
# Source: official Anthropic web_search docs (verified 2026-05-20)
def project_tool_use_input(
    content: list,  # response.content from SDK
    tool_name: str,  # e.g. "structure_output"
) -> dict:
    """Strip all non-tool_use blocks; return the first matching tool_use input."""
    for block in content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input  # type: ignore[return-value]
    raise ValueError(f"No tool_use block with name={tool_name!r} found in response")
```

**Pydantic validation after projection:**
```python
from pydantic import ValidationError

try:
    raw = project_tool_use_input(response.content, "structure_output")
    rec = CoffeeRecSchema.model_validate(raw)
except (ValueError, ValidationError) as exc:
    log.warning(AI_GENERATION_PYDANTIC_ERROR, error=str(exc), user_id=user_id)
    # write ai_recommendations row with error_status="pydantic_error"
    return "try_again"
```

### Pattern 2: Anthropic Tool Definition for Structured Output

The custom tool acts as the schema enforcer. Web search is the server tool.

```python
# Source: Anthropic official docs + verified codebase pattern (2026-05-20)
tools = [
    # Server tool: web_search (Anthropic-executed)
    {
        "type": "web_search_20250305",     # from app_settings["ai_tool_version_anthropic"]
        "name": "web_search",
        "max_uses": settings.get_int("ai_primary_max_searches"),  # 5
        "user_location": {
            "type": "approximate",
            "country": settings.get_str("recommendation_region"),  # "US"
        },
    },
    # Client tool: structured output schema
    {
        "name": "structure_output",
        "description": "Return the structured coffee recommendation",
        "input_schema": COFFEE_REC_SCHEMA,  # Pydantic-derived JSON schema
    },
]
```

**Token accounting:**
- `response.usage.input_tokens` → `tokens_input`
- `response.usage.output_tokens` → `tokens_output`
- `response.usage.server_tool_use.web_search_requests` → `web_search_count`
- `tokens_input_search` = tokens from web_search_tool_result blocks (charged at input rate); the SDK does NOT currently expose this as a separate field — use `0` as default unless the `cache_read_input_tokens` / `cache_creation_input_tokens` distinction helps (LOW confidence on exact field name for search-billed tokens)

[VERIFIED: platform.claude.com/docs/en/api/errors and web_search_tool docs for usage shape]

### Pattern 3: OpenAI Responses API Fallback

**CRITICAL FINDING:** OpenAI's web_search_preview tool and strict JSON structured output (`text.format.type="json_schema"`) are incompatible in the Responses API. When combined, the web_search is silently ignored. [VERIFIED: OpenAI Community forums, multiple GitHub issues, confirmed 2026-05-20]

**Correct fallback pattern:** Use prompt-based JSON extraction, not schema enforcement:

```python
# Source: OpenAI Responses API docs + community findings (verified 2026-05-20)
response = client.responses.create(
    model=cred.model_name,  # from api_credentials.model_name
    input=[{"role": "user", "content": prompt_with_json_instruction}],
    tools=[{"type": "web_search_preview"}],
    # DO NOT add text.format.json_schema here — it breaks web_search
)
# Extract text from message output item
text_out = ""
for item in response.output:
    if item.type == "message":
        for c in item.content:
            if c.type == "output_text":
                text_out = c.text
                break

# Parse as JSON then validate with Pydantic
import json
try:
    raw = json.loads(text_out)
    rec = CoffeeRecSchema.model_validate(raw)
except (json.JSONDecodeError, ValidationError) as exc:
    return "try_again"
```

**OpenAI token accounting:**
- `response.usage.input_tokens` → `tokens_input`
- `response.usage.output_tokens` → `tokens_output`
- `web_search_count` = count of `web_search_call` items in `response.output`
- `tokens_input_search` → `0` (OpenAI does not expose this split)

### Pattern 4: Anthropic Error Classes and Fallback Predicate

```python
import anthropic

# SDK auto-retries: 429 RateLimitError, 5xx InternalServerError, connection errors
# with exponential backoff. max_retries=1 means ONE retry attempt before raising.
client = anthropic.Anthropic(max_retries=1)

NON_RETRYABLE = (
    anthropic.AuthenticationError,    # 401 — key invalid
    anthropic.BadRequestError,         # 400 — prompt/schema problem
    anthropic.PermissionDeniedError,   # 403 — org permission issue
)

async def call_anthropic_with_fallback(...):
    try:
        return await _call_anthropic(...)
    except NON_RETRYABLE:
        # Fall through to OpenAI immediately — retrying won't help
        return await _call_openai(...)
    except anthropic.APIStatusError as exc:
        if exc.status_code == 529:  # OverloadedError
            # After max_retries=1, SDK has already retried once
            # 529 is retryable in principle but persistent = fallback
            return await _call_openai(...)
        raise
```

**OverloadedError:** HTTP 529 (`overloaded_error`). The Anthropic SDK has a bug where 529 received AFTER streaming starts may surface as `APIStatusError(status_code=200)` instead of `APIStatusError(status_code=529)`. Catch both: check `exc.status_code == 529` OR check `"overloaded_error"` in `str(exc)`. [VERIFIED: GitHub anthropics/anthropic-sdk-python issue #1258, GitHub anthropics/claude-code issue #39784]

### Pattern 5: OpenAI Error Classes for Fallback Predicate

```python
import openai

client = openai.OpenAI(max_retries=1)

OAI_NON_RETRYABLE = (
    openai.AuthenticationError,    # 401
    openai.BadRequestError,         # 400
    openai.PermissionDeniedError,   # 403
)

# RateLimitError (429), InternalServerError (5xx), APITimeoutError → retryable
# SDK auto-retries these once (max_retries=1)
```

[VERIFIED: GitHub openai/openai-python /_exceptions.py source, verified 2026-05-20]

### Pattern 6: URL Verification — Ranged GET (AI-05)

```python
# Source: httpx official docs (python-httpx.org) + verified (2026-05-20)
import httpx

VERIFY_UA = (
    "Mozilla/5.0 (compatible; Snobbery/1.0; +https://github.com)"
)

async def verify_buy_url(
    url: str,
    roaster_name: str,
    coffee_name: str,
    *,
    db: Session,
    rec_id: int,
) -> bool:
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,   # NO cross-host redirects (SSRF)
            timeout=httpx.Timeout(5.0),
        ) as client:
            r = await client.get(
                url,
                headers={
                    "Range": "bytes=0-65535",  # ~64KB is enough for a roaster page
                    "User-Agent": VERIFY_UA,
                },
            )
        # Accept 200 or 206 Partial Content
        if r.status_code not in (200, 206):
            return False
        body = r.text.lower()
        return (
            roaster_name.lower() in body
            or coffee_name.lower() in body
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return False
```

**SSRF defense checklist for URL verification:**
- `follow_redirects=False` — prevents cross-host redirect to internal IPs or metadata endpoint.
- No scheme allowlist currently enforced by httpx; the AI service MUST validate URL scheme is `https://` before calling (reject `file://`, `ftp://`, `http://` to internal ranges).
- The ranged GET limits response body size (64KB cap); the full response body is never buffered to disk.
- 5-second hard timeout covers both connect and read phases.

**Paste-rank URL fetch (D-08):** Reuse the same ranged-GET helper with a larger range (`bytes=0-131071`, 128KB) to get enough page text for ranking. Extract `<p>` + `<h1>`/`<h2>` text from the partial HTML (use stdlib `html.parser`; no third-party HTML library needed). Feed max ~8,000 tokens of extracted text to the model. This path does NOT perform roaster/coffee-name body-check — the user is explicitly providing the URL for ranking.

### Pattern 7: Postgres Advisory Lock (AI-13)

```python
# Source: verified via PostgreSQL docs + SQLAlchemy text() pattern (2026-05-20)
import hashlib
from sqlalchemy import text

def _advisory_key(user_id: int, rec_type: str) -> int:
    """Derive stable signed 64-bit int from (user_id, rec_type)."""
    raw = f"{user_id}:{rec_type}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)

def try_advisory_lock(db: Session, user_id: int, rec_type: str) -> bool:
    """Attempt a transaction-scoped advisory lock. Returns True if acquired."""
    key = _advisory_key(user_id, rec_type)
    row = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": key},
    ).scalar()
    return bool(row)
```

**Lock scope:** `pg_try_advisory_xact_lock` is transaction-scoped; it releases automatically on `COMMIT` or `ROLLBACK`. This is correct for the regeneration pattern — the lock is held for the duration of the LLM call + DB write transaction. Use `pg_try_advisory_lock` (session-scoped) ONLY if the call spans multiple transactions, which it does not here.

**In-memory lock (primary guard):**
```python
import asyncio
from typing import ClassVar

_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_LOCKS_META: dict[tuple[int, str], float] = {}  # last_refresh timestamps

def _get_lock(user_id: int, rec_type: str) -> asyncio.Lock:
    key = (user_id, rec_type)
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]
```

### Pattern 8: HTMX Polling for AI in-flight state

```html
{# AI hero card — polling fragment (AI-14) #}
{# Initial load: hx-trigger="load delay:600ms" #}
{# In-flight: swap to this spinner card that polls every 2s #}
<div id="ai-rec-hero"
     hx-get="/home/cards/ai-recommendation"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  <p class="text-sm text-espresso-500">Searching the web for fresh coffees...</p>
  {# Alpine spinner — CSP-safe via Alpine.data #}
</div>
```

The endpoint returns:
- **In-flight:** the spinner fragment with `hx-trigger="every 2s"` (HTMX keeps polling)
- **Complete:** the hero card fragment WITHOUT `hx-trigger` (polling stops)

### Pattern 9: `regenerate()` Entry-Point Signature (SCHED-02 contract)

```python
async def regenerate(
    user_id: int,
    generated_by: str,  # "scheduler" | "manual_refresh"
    *,
    db: Session,
    force: bool = False,  # bypass sig check (used by manual_refresh)
) -> str:  # "generated" | "skipped" | "error" | "locked" | "try_again"
    ...
```

Phase 8's scheduler calls `regenerate(user_id, "scheduler", db=db)`. Manual refresh calls `regenerate(user_id, "manual_refresh", db=db, force=True)`.

### Pattern 10: Pydantic v2 Response Schemas

```python
# Source: Pydantic v2 docs + codebase convention (2026-05-20)
from pydantic import BaseModel, Field

class CoffeeRecSchema(BaseModel):
    """Per-flow schema for the coffee recommendation (AI-18)."""
    coffee_name: str = Field(description="Full coffee name as sold")
    roaster_name: str = Field(description="Roaster name")
    origin: str = Field(description="Country/region of origin")
    process: str = Field(description="Processing method")
    roast_level: str = Field(description="Roast level descriptor")
    buy_url: str | None = Field(None, description="Direct purchase URL if found")
    url_verified: bool | None = Field(None, description="None until verification runs")
    summary_prose: str = Field(description="1-2 sentence recommendation reasoning (D-04)")
    search_tier: str = Field(description="'primary'|'broadened'|'characteristics_only'")
    recipe_suggestion: RecipeSuggestionSchema | None = None
    alt_brewer: AltBrewerSchema | None = None

class SweetSpotsProseSchema(BaseModel):
    """Per-flow schema for sweet-spots AI interpretation (HOME-06, AI-18)."""
    summary_prose: str = Field(description="1-2 sentence interpretation of sweet-spot data")

class EquipmentRecSchema(BaseModel):
    """Per-flow schema for equipment recommendation (AI-08, AI-18)."""
    summary_prose: str = Field(description="1-2 sentence recommendation or 'no changes'")
    weakest_link: str | None = None
    recommendation: str | None = None

class PasteRankSchema(BaseModel):
    """Per-flow schema for paste-and-rank (AI-09, AI-18)."""
    ranked: list[RankedCoffeeItem] = Field(max_length=3)
    summary_prose: str

class RankedCoffeeItem(BaseModel):
    rank: int
    name: str
    reasoning: str = Field(description="1 sentence grounded in user log")
```

### Anti-Patterns to Avoid

- **Calling `model_dump()` on anything that holds a decrypted key** — `ProviderCredential` is `frozen+slots` and intentionally has no `__dict__`. Never extract the `key` field into a dict or log it. [VERIFIED: credentials.py SEC-6 design]
- **Using `response.content` directly as Pydantic input** — the raw content list contains citation-bearing text blocks, server_tool_use, and web_search_tool_result blocks. Always project first.
- **Using OpenAI `text.format.json_schema` with `web_search_preview`** — the web_search tool is silently ignored; use prompt-based JSON extraction instead. [VERIFIED: community forums + GitHub issues]
- **Using `pg_advisory_lock` (session-scoped)** instead of `pg_try_advisory_xact_lock` (transaction-scoped) — session-scoped locks survive transaction rollback and require explicit release. Use `xact` variant.
- **Using `HEAD` for URL verification** — many specialty coffee roasters block HEAD requests (AI-05 requirement explicitly states ranged GET). [ASSUMED: based on AI-05 requirement wording; the specific roasters that block HEAD are not enumerated]
- **Issuing sync DB calls inside an `async def` handler** — the event loop blocks. Read DB inputs sync up front (use a sync Session), call LLM async, write back sync. Or use `run_in_executor` for the DB writes. [VERIFIED: CLAUDE.md Tech Stack §3.3]
- **Rendering AI prose via `|safe`** — all AI prose goes through Jinja autoescape; use `<br>` replacements via a template filter, never `|safe`. [VERIFIED: CLAUDE.md architectural invariants + SEC-05]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retries with backoff | Custom retry loop | `max_retries=1` in SDK constructor | SDK handles backoff; 1 retry is the spec |
| JSON schema from Pydantic | Manual schema dict | `Model.model_json_schema()` | Pydantic v2 built-in; stays in sync |
| Advisory lock key | Rolling hash | `hashlib.sha256` → `int.from_bytes` | Collision-resistant; deterministic |
| HTML page text extraction | Regex | `html.parser.HTMLParser` (stdlib) | Sufficient for `<p>`/`<h>` extraction from partial HTML |
| Token counting | Manual estimate | `response.usage` object fields | SDK provides exact token counts |

---

## Common Pitfalls

### Pitfall 1: OverloadedError 529 Bug in Streaming Path
**What goes wrong:** If the Anthropic API returns 529 after streaming starts, the SDK surfaces `APIStatusError(status_code=200)` instead of `APIStatusError(status_code=529)`. Code checking `exc.status_code == 529` misses it.
**Why it happens:** HTTP 200 is returned when streaming begins; the 529 arrives as an SSE event mid-stream. [VERIFIED: GitHub anthropics/anthropic-sdk-python #1258]
**How to avoid:** Catch `anthropic.APIStatusError` and check both `exc.status_code == 529` AND `"overloaded_error" in str(exc).lower()` in the fallback predicate.
**Warning signs:** Uncaught `APIStatusError` with `status_code=200` in logs that correspond to known overload periods.

### Pitfall 2: OpenAI Web Search + Structured Output Conflict
**What goes wrong:** Using `text.format.json_schema` with `web_search_preview` causes the web search to be silently ignored. The model responds as if it has no web access. [VERIFIED: OpenAI Community forums, multiple GitHub issues]
**Why it happens:** Known OpenAI API limitation (as of May 2026).
**How to avoid:** Use prompt-based JSON extraction for the OpenAI fallback. State explicitly in the prompt: "Return a JSON object matching this schema: {...}". Then `json.loads()` → Pydantic validate.
**Warning signs:** OpenAI fallback responses contain no search citations; response is clearly from training data only.

### Pitfall 3: Citation Blocks Are NOT a Separate Block Type
**What goes wrong:** Code that tries to filter a `"citations"` content block type finds nothing and fails or passes raw content through to Pydantic.
**Why it happens:** Citations are inline fields on `text` blocks, not standalone blocks. [VERIFIED: official Anthropic web_search_tool docs]
**How to avoid:** Project by keeping ONLY `tool_use` blocks named for the custom schema. All citation-bearing text blocks are discarded automatically.

### Pitfall 4: Advisory Lock Key Overflow
**What goes wrong:** Postgres advisory locks require a signed 64-bit integer. Python `int` is arbitrary precision; passing a large value via SQLAlchemy without explicit type coercion raises an integer overflow error in psycopg3.
**Why it happens:** psycopg3 does not auto-cast large Python ints to `bigint`.
**How to avoid:** Use `int.from_bytes(digest[:8], byteorder="big", signed=True)` which always produces a signed int64. Pass via parameterized `text()` with `{"key": key}`.

### Pitfall 5: Sync DB Call Inside Async Handler Blocks Event Loop
**What goes wrong:** `async def` handler calls `db.execute(...)` on a sync `Session`. Event loop is blocked for the duration of the DB call.
**Why it happens:** FastAPI runs sync handlers in a threadpool but async handlers on the event loop directly.
**How to avoid:** Pre-read all DB inputs in a sync context before entering the async LLM call. Post-write DB results synchronously after the awaited call returns. Or run DB ops via `asyncio.run_in_executor(None, sync_fn)`. [VERIFIED: CLAUDE.md Tech Stack §3.3]

### Pitfall 6: Decrypted Key in Pydantic model_dump()
**What goes wrong:** A `ProviderCredential` is accidentally put into a Pydantic schema and `model_dump()` is called, leaking the plaintext key to a JSON log or response.
**Why it happens:** `ProviderCredential` looks like a dataclass; it's easy to include in a schema dict.
**How to avoid:** `ProviderCredential` has `slots=True, frozen=True` specifically to block `__dict__` access. Never pass it to `model_dump()`. Extract only `cred.provider` and `cred.model_name` for logging.

### Pitfall 7: SSRF via Paste-Rank or Buy-URL Fetch
**What goes wrong:** A user supplies a URL pointing to `169.254.169.254` (AWS metadata) or an internal service. The ranged GET fetches it.
**Why it happens:** `httpx` does not block private IP ranges by default.
**How to avoid:** Before any `httpx.AsyncClient.get()` call: (a) parse the URL, (b) assert scheme is `https`, (c) do NOT resolve to check for private IPs at the app level (that requires DNS resolution — add if security posture demands); for v1, scheme allowlist + `follow_redirects=False` is the control. Document this in the threat model.

### Pitfall 8: Module-Level Throttle Dict Growth
**What goes wrong:** `_THROTTLE: dict[int, float]` grows unbounded as users make refresh requests over many days.
**Why it happens:** Old user_id entries are never evicted.
**How to avoid:** Evict on access: before adding a new entry, remove all entries older than 5 minutes + some headroom (e.g., 10 minutes). With 2 users this is never a problem, but code it correctly.

---

## Reusable Asset Contracts (Verified)

These exist on disk. Phase 7 consumes them; do NOT re-implement.

### `credentials.get_provider_credential(db, provider)` → `ProviderCredential | None`
- Returns `None` on: no row, `is_enabled=False`, `key_ciphertext IS NULL`, or `InvalidToken` (decrypt fail).
- `ProviderCredential` fields: `provider: Literal["anthropic","openai"]`, `key: str`, `model_name: str`, `last_four: str`.
- `key` NEVER enters Pydantic / `model_dump()` / logs. [VERIFIED: credentials.py lines 88-163]

### `settings.get_int(key)` / `get_str(key)` / `get_bool(key)`
- Module-level cache; populated at lifespan startup via `prewarm_cache`.
- Relevant keys verified in migration 0001: `recommendation_region` (string, "US"), `min_sessions_for_ai` (int, 3), `min_flavor_notes_for_ai` (int, 5), `ai_primary_max_searches` (int, 5), `ai_broadened_max_searches` (int, 3), `ai_tool_version_anthropic` (string, "web_search_20250305"), `ai_tool_version_openai` (string, "web_search"), `ai_provider_default` (string, "anthropic"), `last_ai_run_status` (string). [VERIFIED: 0001_initial.py lines 230-310]

### `analytics.compute_input_signature(db, user_id)` → `str` (SHA256 hex)
- Returns `_EMPTY_SIGNATURE` (sha256(b"[]")) for users with zero rated sessions.
- Inputs: (coffee_id, float(rating), sorted flavor_note_ids_observed, recipe_id, brewer_id, roast_date). Excludes free-text notes + timestamps (COST-4). [VERIFIED: analytics.py lines 370-419]

### `analytics.get_cold_start_counts(db, user_id)` → `dict`
- Returns: `{sessions: int, distinct_notes: int, gate_open: bool, sessions_needed: int, notes_needed: int}`. [VERIFIED: analytics.py lines 323-362]

### `AIRecommendation` model columns (verified)
- `id`, `user_id`, `recommendation_type` (text: coffee/equipment/paste_rank/sweet_spots), `input_signature`, `response_json` (JSONB), `provider_used`, `model_used`, `tool_version`, `tokens_input`, `tokens_output`, `tokens_input_search`, `web_search_count`, `url_verified` (bool|None), `duration_ms`, `generated_at`, `generated_by` (text: scheduler/manual_refresh), `error_status`. [VERIFIED: ai_recommendation.py]

### `WishlistEntry` model columns (verified)
- `id`, `user_id`, `coffee_name`, `roaster_name`, `source_url`, `source` (text: "ai_recommendation"|"manual"), `notes`, `added_at`, `purchased_at`. [VERIFIED: wishlist_entry.py]

### `home.py` integration points (verified)
- The home shell already checks the cold-start gate and renders the `{% if not gate.gate_open %}` branch. [VERIFIED: home.py lines 54-66]
- `sweet_spots.html` has a Jinja comment "Ends after the SQL-derived list — Phase 7 owns the recommendation prose (HOME-06)." The template is ready for a HOME-06 append block after the `</ul>`. [VERIFIED: sweet_spots.html line 5]
- `pages/home.html` line 115 has: `{# Phase 7: AI recommendation card slot — will use hx-get="/home/cards/ai-recommendation" hx-trigger="revealed" hx-swap="innerHTML" #}`. This comment is the insert point for the AI hero card. Replace the comment with the actual card section. [VERIFIED: home.html line 115]

### `events.py` — AI event taxonomy to add
Currently has no `ai.*` events. Phase 7 adds:
```python
AI_GENERATION_START = "ai.generation.start"        # user_id, rec_type, generated_by
AI_GENERATION_SUCCESS = "ai.generation.success"    # user_id, rec_type, provider, tier, tokens_input, tokens_output, duration_ms
AI_GENERATION_ERROR = "ai.generation.error"        # user_id, rec_type, error_class, error_status
AI_FALLBACK_TRIGGERED = "ai.fallback.triggered"    # user_id, rec_type, from_provider, reason
AI_TIER_FALLBACK = "ai.tier.fallback"              # user_id, from_tier, to_tier, reason
AI_URL_VERIFY = "ai.url.verify"                    # user_id, rec_id, verified (bool)
AI_THROTTLE_BLOCK = "ai.throttle.block"            # user_id, seconds_remaining
AI_REGEN_SKIPPED = "ai.regen.skipped"              # user_id, rec_type, reason="sig_unchanged"
```

---

## Runtime State Inventory

Step 2.6 SKIPPED — this is a greenfield feature phase, not a rename/refactor. No existing runtime state to inventory.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| anthropic SDK | AI-01 primary provider | ✓ | >=0.102 (in requirements) | OpenAI fallback |
| openai SDK | AI-01 fallback provider | ✓ | >=2.37 (in requirements) | Graceful "not configured" state |
| httpx | AI-05 URL verification | ✓ | >=0.28 (in requirements) | — (required) |
| psycopg + PostgreSQL 16 | AI-13 advisory lock | ✓ | pg 16, psycopg 3.3 | — (required) |
| asyncio | In-memory lock | ✓ | stdlib | — |

**No missing dependencies.** All required libraries are already pinned in `requirements.txt`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest]` (check existing) |
| Quick run command | `python -m pytest tests/services/test_ai_service.py -x -q` |
| Full suite command | `python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AI-01 | Provider fallback: non-retryable Anthropic error → OpenAI | unit | `pytest tests/services/test_ai_service.py::test_fallback_on_auth_error -x` | ❌ Wave 0 |
| AI-01 | Provider fallback: OverloadedError (529) → OpenAI | unit | `pytest tests/services/test_ai_service.py::test_fallback_on_overloaded -x` | ❌ Wave 0 |
| AI-01 | max_retries=1: SDK retries exactly once on 5xx | unit (mock SDK) | `pytest tests/services/test_ai_service.py::test_max_retries_one -x` | ❌ Wave 0 |
| AI-03 | Three-tier fallback: primary → broadened → characteristics-only | unit | `pytest tests/services/test_ai_service.py::test_three_tier_fallback -x` | ❌ Wave 0 |
| AI-04 | Citation projection: strips server_tool_use + web_search_tool_result blocks | unit | `pytest tests/services/test_ai_service.py::test_citation_projector -x` | ❌ Wave 0 |
| AI-04 | Citation projection: ValidationError → "try_again" state | unit | `pytest tests/services/test_ai_service.py::test_pydantic_validation_error -x` | ❌ Wave 0 |
| AI-05 | URL verification: HTTPS, 5s timeout, body check, 200/206 only | unit (respx mock) | `pytest tests/services/test_ai_service.py::test_url_verify_verified -x` | ❌ Wave 0 |
| AI-05 | URL verification: cross-host redirect blocked (follow_redirects=False) | unit (respx mock) | `pytest tests/services/test_ai_service.py::test_url_verify_ssrf_redirect -x` | ❌ Wave 0 |
| AI-05 | URL verification: non-https scheme rejected | unit | `pytest tests/services/test_ai_service.py::test_url_verify_scheme_rejected -x` | ❌ Wave 0 |
| AI-11 | Cold-start gate: <3 sessions → gate_open=False | unit (analytics, existing DB) | `pytest tests/services/test_analytics.py::test_cold_start_gate -x` | ❌ Wave 0 |
| AI-12 | Signature regen skip: same sig → "skipped" result | unit | `pytest tests/services/test_ai_service.py::test_sig_skip -x` | ❌ Wave 0 |
| AI-13 | Advisory lock: second concurrent call returns "locked" | unit (DB required) | `pytest tests/services/test_ai_service.py::test_advisory_lock_concurrent -x` | ❌ Wave 0 |
| AI-14 | Throttle: second manual refresh within 5 min → 429 | unit | `pytest tests/routers/test_ai_router.py::test_throttle_429 -x` | ❌ Wave 0 |
| AI-16 | "AI not configured": credentials return None → empty state | unit | `pytest tests/services/test_ai_service.py::test_no_credential_empty_state -x` | ❌ Wave 0 |
| AI-17 | max_uses from settings: reads ai_primary_max_searches | unit | `pytest tests/services/test_ai_service.py::test_max_uses_from_settings -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/services/test_ai_service.py tests/routers/test_ai_router.py -x -q`
- **Per wave merge:** `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/services/test_ai_service.py` — covers AI-01, AI-03, AI-04, AI-05, AI-12, AI-13, AI-16, AI-17
- [ ] `tests/routers/test_ai_router.py` — covers AI-14, AI-15
- [ ] `tests/services/test_analytics.py` (may exist partially) — covers AI-11 cold-start gate behavior

**Required for Wave 0:** `respx` mock library (for httpx outbound calls). Already identified in Phase 7 test scope (TEST-02). Install into the running container: `pip install --user respx`.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (indirect) | `require_user` on all AI routes |
| V4 Access Control | yes | Per-user IDOR scoping; cross-user rec_id → 404 |
| V5 Input Validation | yes | Pydantic v2 schemas on all AI response parsing; URL scheme allowlist |
| V6 Cryptography | yes (credential handling) | `ProviderCredential.key` never logged / never in Pydantic |
| V10 Malicious Code | yes (SSRF) | `follow_redirects=False`, scheme allowlist, 5s timeout, 64KB body cap |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF via buy_url / paste-rank URL | Tampering / Information Disclosure | Scheme allowlist (https only), `follow_redirects=False`, 5s timeout, 64KB range limit |
| SSRF via AI-suggested URL (web search result) | Tampering | Same as above — AI-generated URLs are also untrusted inputs |
| Prompt injection from web search results into structured output | Tampering / Elevation | Per-flow Pydantic validation rejects unexpected fields; tool_use schema constrains output shape |
| IDOR: user A reads user B's recommendations | Information Disclosure | All rec queries filter by `user_id = request.state.user.id`; rec_id → 404 for wrong user |
| Cost / DoS via manual refresh | Denial of Service | 5-minute per-user throttle; advisory lock prevents concurrent runs |
| API key leakage via logs or Pydantic | Information Disclosure | `ProviderCredential` has `slots=True, frozen=True`; never in `model_dump()`; structlog redactor pattern |
| CSRF on manual refresh POST | Cross-Site Request Forgery | `starlette-csrf` double-submit cookie on every state-changing AI POST |
| Wishlist add/remove CSRF | Cross-Site Request Forgery | Same CSRF middleware; all wishlist writes are POST |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Anthropic citations as separate block type | Citations inline on `text` blocks as `citations` field | Web search tool GA (2025) | Citation projector cannot filter by block type; must discard all text/server_tool_use blocks and keep only named tool_use blocks |
| OpenAI JSON structured output with web_search | Prompt-based JSON extraction only (structured output + web_search incompatible) | Responses API launch (2025) | OpenAI fallback has weaker schema enforcement; compensated by Pydantic validation on parsed JSON |
| Anthropic tool version hardcoded | Tool version in `app_settings.ai_tool_version_anthropic` | Phase 0 design | Admin-configurable; logged to telemetry; enables upgrade to `web_search_20260209` (dynamic filtering) from admin panel without code change |
| APScheduler 4.x (alpha) | APScheduler 3.11 | — | Phase 8 scheduler uses 3.x API |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `tokens_input_search` for Anthropic web-search billed tokens is not exposed as a distinct field in `response.usage`; using `0` as default for this column | Standard Stack / Pattern 2 | If Anthropic does expose this, the telemetry column stays at 0; low operational risk; easy to fix in Phase 12 |
| A2 | Using `HEAD` is blocked by specialty roasters; ranged GET is required per AI-05 spec wording | Common Pitfalls | If `HEAD` works for most roasters, ranged GET still works too — no regression risk |
| A3 | OpenAI web_search + structured output incompatibility persists as of May 2026 | Pattern 3 | If fixed by OpenAI, the prompt-based extraction still works; migration is additive |
| A4 | A realistic User-Agent is sufficient to avoid bot-blocking on buy URLs; no cookie or JS required | Pattern 6 | Some roasters require JS rendering; verification returns `False` (unverified state); user sees "couldn't verify" note — acceptable degraded behavior |
| A5 | `html.parser` from stdlib is adequate for `<p>`/`<h>` extraction from partial HTML for paste-rank | Pattern 1 / Architecture | Malformed partial HTML (Range stops mid-tag) may corrupt parser state; limit extraction to text content only, ignore parser errors |

---

## Open Questions (RESOLVED)

> Both items are implementation-time confirmations with a safe default already chosen; neither blocks planning. Resolutions are carried into the plans (07-01 T3, 07-03 T3).

1. **`tokens_input_search` exact field name**
   - What we know: Anthropic charges web-search billed input tokens separately. The `response.usage` object in 0.102.0 has `server_tool_use.web_search_requests` (count). The CLAUDE.md spec shows `cache_read_input_tokens` / `cache_creation_input_tokens` in the example JSON.
   - What's unclear: Whether a separate field for search-attributed input tokens exists in the Python SDK at 0.102.
   - **RESOLVED:** At implementation time, `print(response.usage.model_dump())` in a test call to see exact field names. Default `tokens_input_search=0` until confirmed (the DB column exists; populate when field is confirmed). Implemented as assumption A1 in **07-01 Task 3** (telemetry writer defaults the field to 0 with a TODO to confirm the SDK field).

2. **Advisory lock + async handler**
   - What we know: `db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})` works in a sync Session. The `regenerate()` function is `async def` for the LLM call.
   - What's unclear: How to run the sync lock acquire/release around an async LLM call without blocking the event loop.
   - **RESOLVED:** Bracket the `await llm_call()` with discrete sync DB work (lock + input reads before, writes + release after) — do NOT hold a sync Session across the await; offload via `run_in_executor` only if a sync call must occur mid-await. The single-worker invariant makes the advisory lock the cross-process backstop, not the hot path. Implemented in **07-03 Task 3** (the `regenerate()` docstring + structure required to acquire/release the advisory lock on a sync Session bracketing the async LLM call).

---

## Sources

### Primary (HIGH confidence)
- [Anthropic web search tool docs](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use/web-search-tool) — confirmed `web_search_20250305` tool shape, `max_uses` param, citation inline on text blocks, usage object shape, error codes
- [Anthropic API errors docs](https://platform.claude.com/docs/en/api/errors) — 400/401/403/429/500/529 status codes confirmed
- [OpenAI Python SDK exceptions.py](https://github.com/openai/openai-python/blob/main/src/openai/_exceptions.py) — exception class hierarchy verified
- [OpenAI Responses API cookbook](https://developers.openai.com/cookbook/examples/responses_api/responses_example) — output item types (web_search_call, message), output_text extraction
- Codebase: `app/services/credentials.py`, `app/services/settings.py`, `app/services/analytics.py`, `app/models/ai_recommendation.py`, `app/models/wishlist_entry.py`, `app/routers/home.py`, `app/templates/pages/home.html`, `app/migrations/versions/0001_initial.py`, `app/events.py` — all verified directly

### Secondary (MEDIUM confidence)
- [PostgreSQL advisory locks Python guide](https://leontrolski.github.io/postgres-advisory-locks.html) — `pg_try_advisory_xact_lock` pattern + key derivation
- [httpx documentation](https://www.python-httpx.org/api/) — `follow_redirects`, `Range` header, `Timeout` object
- [Anthropic error handling guide](https://tessl.io/registry/tessl/pypi-anthropic/0.75.0/files/docs/guides/error-handling.md) — error classes confirmed; `OverloadedError` not in that guide (found via separate search)

### Tertiary (LOW confidence)
- OpenAI Community forums + GitHub issues — OpenAI web_search + structured output incompatibility (multiple corroborating sources → elevated to MEDIUM)
- [GitHub anthropics/anthropic-sdk-python #1258](https://github.com/anthropics/anthropic-sdk-python/issues/1258) — OverloadedError 529 streaming bug
- [GitHub anthropics/claude-code #39784](https://github.com/anthropics/claude-code/issues/39784) — additional 529 bug evidence

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all library versions verified against CLAUDE.md pinned stack
- Citation projection pattern: HIGH — verified against official Anthropic docs
- OpenAI fallback pattern: MEDIUM-HIGH — structured output + web_search incompatibility confirmed across multiple independent sources
- Advisory lock: MEDIUM — pattern verified; exact integration with async handler needs implementation-time testing
- Pitfalls: HIGH — most verified against SDK source or official docs

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (30 days; Anthropic SDK is on fast cadence — check changelog before starting)
