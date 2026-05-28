"""AI service — provider abstraction, citation projector, URL verifier, and
concurrency primitives.

This module is the single owner of all AI flow logic. Downstream plans
(07-03, 07-04, 07-05) import the helpers and entry-points defined here;
they do not re-implement any of the security-critical pieces.

Security boundaries (STRIDE register 07-01):
  T-07-01 SSRF: ``_verify_buy_url`` enforces https-only, no cross-host
    redirect, 64KB Range cap, 5s timeout.
  T-07-02 Prompt injection: ``_project_tool_use_input`` keeps ONLY the
    named tool_use block; ``ConfigDict(extra="forbid")`` rejects injected
    fields.
  T-07-03 Secret leakage: ``cred.key`` passes only to the SDK constructor;
    never logged, never placed in a Pydantic model or response_json.
  T-07-04 Unbounded state: ``_evict_stale_throttle`` bounds ``_THROTTLE``
    growth on every access.
"""

from __future__ import annotations

import asyncio
import hashlib
import html.parser
import ipaddress
import json  # noqa: F401 — used in Task 2 OpenAI fallback flow
import socket
import time  # noqa: F401 — used in Task 2/3 for duration_ms calculation
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import anthropic
import httpx
import openai
import structlog
from pydantic import ValidationError

try:
    from sse_starlette.sse import ServerSentEvent
except ImportError:  # pragma: no cover
    # Fallback for environments where sse-starlette is not installed

    class ServerSentEvent:  # type: ignore[no-redef]
        def __init__(self, data: str, event: str | None = None) -> None:
            self.data = data
            self.event = event


from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.events import (
    AI_FALLBACK_TRIGGERED,  # noqa: F401 — used in Task 2 provider/tier fallback
    AI_GENERATION_ERROR,  # noqa: F401 — used in Task 3 error handling
    AI_GENERATION_START,  # noqa: F401 — used in Task 3 regenerate entry point
    AI_GENERATION_SUCCESS,  # noqa: F401 — used in Task 3 regenerate entry point
    AI_REGEN_SKIPPED,  # noqa: F401 — used in Task 3 signature skip
    AI_THROTTLE_BLOCK,  # noqa: F401 — used in Task 3 throttle
    AI_TIER_FALLBACK,  # noqa: F401 — used in Task 2 tier fallback
    AI_URL_VERIFY,  # noqa: F401
)
from app.models.ai_recommendation import AIRecommendation
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.coffee_origin import CoffeeOrigin
from app.models.equipment import Equipment
from app.models.recipe import Recipe
from app.services import analytics as analytics_service  # noqa: F401 — used in Task 3
from app.services import credentials as credentials_service
from app.services import settings as settings_service  # noqa: F401 — used in Task 2
from app.services.ai_schemas import (
    AltBrewerSchema,
    BrewImproveSchema,
    CoffeeRecSchema,  # noqa: F401 — used in Task 2
    EquipmentRecSchema,
    PasteRankSchema,
    PreferenceProfileProseSchema,
    RecipeSuggestionSchema,
    SweetSpotsProseSchema,  # noqa: F401 — used in Task 2
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Realistic User-Agent for the ranged-GET URL verifier (T-07-SSRF).
#: Identifies Snobbery to server logs without exposing a bot signature.
VERIFY_UA = "Mozilla/5.0 (compatible; Snobbery/1.0; +https://github.com)"

#: Anthropic error classes that are non-retryable and trigger OpenAI fallback.
NON_RETRYABLE = (
    anthropic.AuthenticationError,
    anthropic.BadRequestError,
    anthropic.PermissionDeniedError,
)

#: Max URLs fetched per paste-and-rank call (CR-04). Each fetch is a sequential
#: ranged GET with a 5s timeout; cap bounds worst-case event-loop blocking.
_MAX_PASTE_RANK_URLS = 5

# ---------------------------------------------------------------------------
# Module-level concurrency state (process-local; single uvicorn worker)
# ---------------------------------------------------------------------------

#: In-memory lock dict keyed by (user_id, recommendation_type).
#: Process-local; sufficient for single uvicorn worker (AI-13).
_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}

#: Per-user last-refresh timestamps for the 5-minute manual-refresh throttle.
#: Process-local; no Redis needed at household scale (AI-14).
_THROTTLE: dict[int, float] = {}


# ---------------------------------------------------------------------------
# Lock + throttle helpers
# ---------------------------------------------------------------------------


def _get_lock(user_id: int, rec_type: str) -> asyncio.Lock:
    """Return (creating if necessary) the per-(user_id, rec_type) asyncio.Lock."""
    key = (user_id, rec_type)
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]


def _evict_stale_throttle(*, now: float, window_secs: float = 600.0) -> None:
    """Remove throttle entries older than *window_secs* to prevent unbounded growth.

    Called on every throttle check (Pitfall 8 bounded-state guard, T-07-04).
    The default window matches the 10-minute maximum cooldown period.
    """
    stale = [uid for uid, ts in _THROTTLE.items() if now - ts > window_secs]
    for uid in stale:
        del _THROTTLE[uid]


# ---------------------------------------------------------------------------
# Citation projector (T-07-02 prompt-injection defence, AI-04)
# ---------------------------------------------------------------------------


def _project_tool_use_input(content: list[Any], tool_name: str) -> dict[str, Any]:
    """Return the ``input`` dict of the first ``tool_use`` block named *tool_name*.

    The Anthropic web-search response ``content`` array contains mixed
    block types: ``text``, ``server_tool_use``, ``web_search_tool_result``,
    and the custom ``tool_use`` block whose ``input`` is the LLM-generated
    structured output. This projector discards every block except the one
    named *tool_name*, preventing adversarial web-search content from
    reaching Pydantic validation (T-07-02).

    Verified content block types (2026-05-20 Anthropic docs):
    - ``TextBlock(type="text", citations=...)`` — STRIP (may contain injected text)
    - ``ServerToolUseBlock(type="server_tool_use", name="web_search")`` — STRIP
    - ``WebSearchToolResultBlock(type="web_search_tool_result")`` — STRIP
    - ``ToolUseBlock(type="tool_use", name=tool_name, input={...})`` — KEEP

    Raises:
        ValueError: when no matching ``tool_use`` block is found.
    """
    for block in content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input  # type: ignore[return-value]
    raise ValueError(f"No tool_use block with name={tool_name!r} in response")


# ---------------------------------------------------------------------------
# SSRF-hardened URL verifier (T-07-01, AI-05)
# ---------------------------------------------------------------------------


async def _verify_buy_url(url: str, roaster_name: str, coffee_name: str) -> bool:
    """Perform a ranged GET to verify *url* is a live page for this coffee.

    SSRF mitigations (T-07-SSRF):
    - **Scheme allowlist**: rejects any URL that does not start with
      ``https://`` before making any network call. This blocks ``file://``,
      ``http://``, ``ftp://``, and any other scheme an adversarial AI might
      suggest.
    - **No cross-host redirects**: ``follow_redirects=False`` prevents a
      302 to an internal metadata endpoint (e.g. 169.254.169.254).
      Any non-200/206 response (including 3xx) returns ``False``.
    - **Body cap**: ``Range: bytes=0-65535`` (64 KB) caps the download size
      regardless of server compliance.
    - **Timeout**: ``httpx.Timeout(5.0)`` hard-kills the request after 5 s.

    Returns:
        ``True`` when the response status is 200 or 206 AND the body (case-
        insensitive) contains either *roaster_name* or *coffee_name*.
        ``False`` on any failure mode (bad scheme, bad status, timeout,
        network error, name not found in body).
    """
    # Scheme allowlist — no network call for non-https (T-07-SSRF)
    if not url.startswith("https://"):
        return False
    # Resolve-validate gate — reject private/loopback/link-local/reserved IPs (S1)
    if not _assert_public_host(url):
        return False

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,  # SSRF: block cross-host redirects
            timeout=httpx.Timeout(5.0),  # SSRF: hard 5s timeout
        ) as client:
            r = await client.get(
                url,
                headers={
                    "Range": "bytes=0-65535",  # SSRF: 64KB body cap
                    "User-Agent": VERIFY_UA,
                },
            )

        # D-14: archived/gone lots — treat as failure explicitly before general gate
        if r.status_code in (404, 410):
            return False
        if r.status_code not in (200, 206):
            return False

        body = r.text.lower()
        # D-14: sold-out text scan (cheap first-64KB check)
        if "sold out" in body:
            return False
        return roaster_name.lower() in body or coffee_name.lower() in body

    except (httpx.TimeoutException, httpx.RequestError):
        return False


def _assert_public_host(url: str) -> bool:
    """Return False if the URL host resolves to any private/reserved address.

    Resolves *url*'s hostname via ``socket.getaddrinfo`` and classifies every
    returned IP with ``ipaddress``.  IPv4-mapped IPv6 addresses (``::ffff:…``)
    are normalised to their IPv4 form before classification so that
    ``::ffff:169.254.169.254`` is correctly rejected.

    TOCTOU caveat: DNS resolution is not pinned to the connection — a
    sub-millisecond window exists between this check and the ``httpx`` connect.
    Accepted at household scale (D-05).

    Returns:
        ``True`` only when every resolved address is public.
        ``False`` on DNS failure, unparseable address, or any private/loopback/
        link-local/reserved address.
    """
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # DNS failure -> reject

    if not infos:
        return False  # no addresses resolved -> reject (defensive)

    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # Normalise IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254 -> 169.254.169.254)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        # `not is_global` is the primary gate: it rejects anything not globally
        # routable, including CGNAT shared space (100.64.0.0/10, RFC 6598) that
        # none of the is_private/is_reserved flags classify. The explicit flags
        # remain for clarity of intent and defence in depth.
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or not addr.is_global
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Advisory lock helpers (AI-13, Postgres cross-process backstop)
# ---------------------------------------------------------------------------


def _advisory_key(user_id: int, rec_type: str) -> int:
    """Derive a stable signed int64 from *(user_id, rec_type)* for advisory locks.

    Uses SHA256 of the UTF-8 colon-joined key, then takes the first 8 bytes
    interpreted as a big-endian signed int64. This produces a stable,
    well-distributed value that fits Postgres ``pg_try_advisory_xact_lock``'s
    signed 64-bit integer parameter.
    """
    raw = f"{user_id}:{rec_type}".encode()
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _try_advisory_lock(db: Session, user_id: int, rec_type: str) -> bool:
    """Attempt to acquire a Postgres advisory transaction lock.

    Returns ``True`` when the lock is granted (no concurrent worker holds
    it for the same key), ``False`` otherwise. The lock is automatically
    released at transaction end — no explicit release is required.
    """
    key = _advisory_key(user_id, rec_type)
    row = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": key},
    ).scalar()
    return bool(row)


# ---------------------------------------------------------------------------
# Provider client builders (AI-01)
# ---------------------------------------------------------------------------


def _build_anthropic_client(cred: credentials_service.ProviderCredential) -> anthropic.Anthropic:
    """Construct a synchronous Anthropic client with ``max_retries=1``.

    Per AI-01: one SDK-level retry is enough — persistent failures trigger
    the OpenAI fallback path rather than retrying indefinitely. The key is
    passed only to the SDK constructor and is NEVER logged (T-07-03, SEC-6).
    """
    # Safe to log: provider, model_name. NEVER log: cred.key.
    log.debug(
        "building_anthropic_client",
        provider=cred.provider,
        model=cred.model_name,
    )
    return anthropic.Anthropic(api_key=cred.key, max_retries=1)


def _build_openai_client(cred: credentials_service.ProviderCredential) -> openai.OpenAI:
    """Construct a synchronous OpenAI client with ``max_retries=1``.

    Per AI-01: same retry cap as Anthropic. The key is passed only to the
    SDK constructor and is NEVER logged (T-07-03, SEC-6).
    """
    log.debug(
        "building_openai_client",
        provider=cred.provider,
        model=cred.model_name,
    )
    return openai.OpenAI(api_key=cred.key, max_retries=1)


# ---------------------------------------------------------------------------
# Fallback predicate (AI-01, Pattern 4)
# ---------------------------------------------------------------------------


def _is_anthropic_fallback_error(exc: BaseException) -> bool:
    """Return ``True`` when *exc* should trigger the OpenAI fallback path.

    Non-retryable errors (fallback immediately):
    - ``anthropic.AuthenticationError`` — invalid API key
    - ``anthropic.BadRequestError``     — malformed request / blocked prompt
    - ``anthropic.PermissionDeniedError`` — key lacks required permissions

    Retryable / overloaded (fallback after SDK's one retry):
    - ``anthropic.APIStatusError`` with ``status_code == 529``
    - ``anthropic.APIStatusError`` whose string representation contains
      ``"overloaded_error"`` — this catches the SDK streaming bug (#1258)
      where a 200-status streaming response can contain an overloaded_error
      payload (Pitfall 1 in RESEARCH.md).

    Rate limit (NOT a fallback trigger):
    - ``anthropic.RateLimitError`` (429) is retryable — the SDK handles one
      retry automatically; if it still fails, let the exception propagate
      rather than burning an OpenAI quota.
    """
    if isinstance(exc, NON_RETRYABLE):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code == 529:
            return True
        if "overloaded_error" in str(exc).lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Voice constant (D-03/D-04) — used in all LLM prompts
# ---------------------------------------------------------------------------

#: System prompt encoding the D-03 voice (confident expert, lightly wry)
#: and D-04 tight prose (1-2 sentences).  All prose stays plain text —
#: rendered autoescaped + <br> in templates; NEVER piped through |safe.
SYSTEM_PROMPT_VOICE: str = (
    "You are a knowledgeable but approachable specialty coffee advisor. "
    "Your recommendations are confident, specific, and lightly wry — "
    "never sycophantic, never wishy-washy. "
    "Keep prose tight: 1-2 sentences unless the field explicitly calls for more. "
    "Cite concrete flavour descriptors and roast parameters. "
    "Do not invent URLs — only include a buy_url if you find a verified, current product page."
)


# ---------------------------------------------------------------------------
# Recipe suggestion sub-flow (AI-06, D-06 — no LLM)
# ---------------------------------------------------------------------------


def suggest_recipe(
    db: Session,
    *,
    user_id: int,
    origin: str | None,
    process: str | None,
    roast_level: str | None,
) -> RecipeSuggestionSchema:
    """Return the user's highest-avg-rated recipe for the given bean style.

    Joins BrewSession → Coffee (case-insensitive match on origin/process/
    roast_level) and BrewSession → Recipe; filters by user_id, non-null
    rating, non-null recipe_id; groups by recipe and picks the top-rated.
    Returns a no-match result when no matching sessions exist.

    NEVER invents a recipe (D-06 / AI-06): recipe_id is always a real DB id
    or None.
    """
    stmt = (
        select(
            Recipe.id.label("recipe_id"),
            Recipe.name.label("recipe_name"),
            func.avg(BrewSession.rating).label("avg_rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(Recipe, BrewSession.recipe_id == Recipe.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
            BrewSession.recipe_id.is_not(None),
            # Case-insensitive style matching. Origin matches ANY of the coffee's
            # origins (D-01 multi-origin): a Yirgacheffe+Bourbon blend counts when
            # filtering by 'Ethiopia'. Process/roast_level remain Coffee columns.
            (
                select(CoffeeOrigin.id)
                .where(
                    CoffeeOrigin.coffee_id == Coffee.id,
                    func.lower(CoffeeOrigin.country) == func.lower(origin),
                )
                .exists()
                if origin
                else text("TRUE")
            ),
            func.lower(Coffee.process) == func.lower(process) if process else text("TRUE"),
            (
                func.lower(Coffee.roast_level) == func.lower(roast_level)
                if roast_level
                else text("TRUE")
            ),
        )
        .group_by(Recipe.id, Recipe.name)
        .order_by(func.avg(BrewSession.rating).desc())
        .limit(1)
    )
    row = db.execute(stmt).first()

    if row is None:
        # D-11: no_match removed; required fields carry sensible defaults when
        # no matching recipe exists in the catalog.  Plan 19-02 wires the LLM
        # to populate these from the structured-output tool call.
        return RecipeSuggestionSchema(
            recipe_id=None,
            recipe_name=None,
            summary="No matching recipe yet — try the recipe builder.",
            ratio="1:15",
            temp_c=94,
            grind_hint="medium-fine",
        )
    return RecipeSuggestionSchema(
        recipe_id=row.recipe_id,
        recipe_name=row.recipe_name,
        summary=(
            f"Based on your rated sessions, {row.recipe_name!r} averaged "
            f"{float(row.avg_rating):.2f}/5 on this bean style."
        ),
        ratio="1:15",
        temp_c=94,
        grind_hint="medium-fine",
    )


# ---------------------------------------------------------------------------
# Alt-brewer callout sub-flow (AI-07, D-06 — no LLM)
# ---------------------------------------------------------------------------


def alt_brewer_callout(
    db: Session,
    *,
    user_id: int,
    origin: str | None,
    process: str | None,
    roast_level: str | None,
    exclude_brewer_id: int | None = None,
) -> AltBrewerSchema | None:
    """Return an AltBrewerSchema if a different brewer shows >=0.5 higher avg rating.

    Joins BrewSession → Coffee → Equipment(brewer) for the given bean style
    and user; groups by brewer; computes avg rating per brewer.  Determines
    the baseline (the exclude_brewer_id if provided, else the worst-rated
    brewer the user has used for this style); returns an AltBrewerSchema
    only when the best *alternate* brewer's avg is >=0.5 above the baseline.

    Returns None below the 0.5 threshold (AI-07).
    """
    brewer = Equipment
    stmt = (
        select(
            Equipment.id.label("brewer_id"),
            Equipment.model.label("brewer_name"),
            func.avg(BrewSession.rating).label("avg_rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(brewer, BrewSession.brewer_id == brewer.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
            BrewSession.brewer_id.is_not(None),
            # Origin matches ANY of the coffee's origins (D-01 multi-origin).
            (
                select(CoffeeOrigin.id)
                .where(
                    CoffeeOrigin.coffee_id == Coffee.id,
                    func.lower(CoffeeOrigin.country) == func.lower(origin),
                )
                .exists()
                if origin
                else text("TRUE")
            ),
            func.lower(Coffee.process) == func.lower(process) if process else text("TRUE"),
            (
                func.lower(Coffee.roast_level) == func.lower(roast_level)
                if roast_level
                else text("TRUE")
            ),
        )
        .group_by(Equipment.id, Equipment.model)
        .order_by(func.avg(BrewSession.rating).desc())
    )
    rows = db.execute(stmt).all()

    if not rows:
        return None

    # Determine the baseline avg (the excluded brewer's avg, or the overall lowest)
    if exclude_brewer_id is not None:
        baseline_rows = [r for r in rows if r.brewer_id == exclude_brewer_id]
        baseline_avg = float(baseline_rows[0].avg_rating) if baseline_rows else None
        alt_rows = [r for r in rows if r.brewer_id != exclude_brewer_id]
    else:
        # No exclusion: compare best vs worst
        baseline_avg = float(rows[-1].avg_rating)
        alt_rows = rows[:-1]

    if baseline_avg is None or not alt_rows:
        return None

    # Best alternate brewer is the first in the sorted list
    best_alt = alt_rows[0]
    delta = float(best_alt.avg_rating) - baseline_avg

    if delta < 0.5:
        return None

    return AltBrewerSchema(
        brewer_name=best_alt.brewer_name,
        rating_delta=round(delta, 2),
        summary=(
            f"Sessions with {best_alt.brewer_name} averaged "
            f"{float(best_alt.avg_rating):.2f}/5 on this bean style — "
            f"{delta:.2f} points above your current setup."
        ),
    )


# ---------------------------------------------------------------------------
# Anthropic coffee-rec LLM caller (AI-03 / Pattern 2)
# ---------------------------------------------------------------------------


def _anthropic_coffee_call(
    client: anthropic.Anthropic,
    *,
    model: str,
    tool_version: str,
    max_uses: int,
    region: str,
    prompt: str,
) -> tuple[dict[str, Any], Any, int]:
    """Call Anthropic with web_search + structure_output tools.

    Builds the two-tool list per 07-PATTERNS lines 155-173:
    - web_search server tool (type=tool_version, name="web_search", max_uses, user_location)
    - structure_output client tool with CoffeeRecSchema.model_json_schema() as input_schema

    Returns (raw_dict, usage, web_search_count).
    Raises ValueError if the projector finds no structure_output block.
    Raises any Anthropic SDK exception for the caller to handle (fallback predicate).
    """
    tools: list[dict[str, Any]] = [
        {
            "type": tool_version,
            "name": "web_search",
            "max_uses": max_uses,
            "user_location": {
                "type": "approximate",
                "country": region,
            },
        },
        {
            "name": "structure_output",
            "description": "Return the structured coffee recommendation",
            "input_schema": CoffeeRecSchema.model_json_schema(),
        },
    ]
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT_VOICE,
        messages=[{"role": "user", "content": prompt}],
        tools=tools,  # type: ignore[arg-type]
    )
    raw = _project_tool_use_input(response.content, "structure_output")
    web_search_count: int = getattr(
        getattr(response.usage, "server_tool_use", None), "web_search_requests", 0
    )
    return raw, response.usage, web_search_count


# ---------------------------------------------------------------------------
# OpenAI coffee-rec fallback caller (Pattern 3 — prompt-based JSON)
# ---------------------------------------------------------------------------


def _openai_coffee_call(
    client: openai.OpenAI,
    *,
    model: str,
    prompt: str,
) -> tuple[dict[str, Any], Any, int]:
    """Call OpenAI Responses API with web_search_preview (NOT json_schema — Pitfall 2).

    Uses prompt-based JSON instruction rather than text.format.json_schema,
    because json_schema silently disables web_search_preview on the OpenAI
    Responses API (RESEARCH.md Pitfall 2).

    Returns (raw_dict, usage, web_search_count).
    Raises json.JSONDecodeError or pydantic.ValidationError on bad output.
    """
    schema_hint = json.dumps(CoffeeRecSchema.model_json_schema(), separators=(",", ":"))
    full_prompt = (
        f"{prompt}\n\nRespond with a JSON object matching this schema exactly:\n{schema_hint}"
    )
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": full_prompt}],
        tools=[{"type": "web_search_preview"}],  # type: ignore[list-item]
    )
    # Extract text output from the response
    text_out = ""
    for item in response.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text_out = c.text
                    break
    raw = json.loads(text_out)
    web_search_count: int = 0  # OpenAI Responses API does not expose search count
    return raw, response.usage, web_search_count


# ---------------------------------------------------------------------------
# Sweet-spots prose sub-flow (HOME-06, AI-10)
# ---------------------------------------------------------------------------


async def _generate_sweet_spots_prose(
    db: Session,
    *,
    user_id: int,
    generated_by: str,
    cred: credentials_service.ProviderCredential | None,
    signature: str,
) -> AIRecommendation | None:
    """Generate and persist sweet-spots prose for the user.

    D-15 / AIX-13: p95 latency target ≤ 30s (single structured call, no web search).

    Reads analytics.get_sweet_spots; returns None when empty (no data to
    summarise). Otherwise makes one small LLM call (no web_search) returning
    SweetSpotsProseSchema, then writes a SEPARATE row with
    recommendation_type="sweet_spots" in the same regeneration flow (AI-10).

    The LLM call is synchronous (no web search needed); the async wrapper
    keeps the function signature consistent with the awaited call site.
    """
    # CR-02: the caller re-fetches credentials after the coffee rec; if both
    # providers became unavailable in between, cred is None. Skip prose rather
    # than dereferencing None (which would turn a successful rec into "error").
    if cred is None:
        return None

    sweet_spots = analytics_service.get_sweet_spots(db, user_id)
    if not sweet_spots:
        return None

    # Build a compact summary of the sweet-spot combos for the prompt
    combos = "\n".join(
        f"- {r.origin} {r.process} via {r.brewer_name} / {r.recipe_name}: "
        f"avg {float(r.avg_rating):.2f} ({r.session_count} sessions)"
        for r in sweet_spots
    )
    prompt = (
        f"Here are this user's top brew sweet spots:\n{combos}\n\n"
        "Write 3-5 sentences identifying the key patterns — grind, ratio, temperature, "
        "or timing — with specific numbers where the data supports it. "
        "This will display on the home page as actionable guidance."
    )

    start_ts = time.monotonic()
    tool_version = settings_service.get_str("ai_tool_version_anthropic")

    if cred.provider == "anthropic":
        client = _build_anthropic_client(cred)
        # No web_search for sweet spots — characteristics-only small call
        response = client.messages.create(
            model=cred.model_name,
            max_tokens=512,
            system=SYSTEM_PROMPT_VOICE,
            messages=[{"role": "user", "content": prompt}],
            tools=[
                {
                    "name": "structure_output",
                    "description": "Return the sweet spots prose",
                    "input_schema": SweetSpotsProseSchema.model_json_schema(),
                }
            ],  # type: ignore[arg-type]
        )
        raw = _project_tool_use_input(response.content, "structure_output")
        usage = response.usage
        web_search_count = 0
    else:
        # OpenAI path
        oai_client = _build_openai_client(cred)
        schema_hint = json.dumps(SweetSpotsProseSchema.model_json_schema(), separators=(",", ":"))
        full_prompt = f"{prompt}\n\nRespond with JSON matching this schema:\n{schema_hint}"
        response = oai_client.responses.create(
            model=cred.model_name,
            input=[{"role": "user", "content": full_prompt}],
        )
        text_out = ""
        for item in response.output:
            if item.type == "message":
                for c in item.content:
                    if c.type == "output_text":
                        text_out = c.text
                        break
        raw = json.loads(text_out)
        usage = response.usage
        web_search_count = 0
        tool_version = settings_service.get_str("ai_tool_version_openai")

    from pydantic import ValidationError as PydanticValidationError

    try:
        SweetSpotsProseSchema.model_validate(raw)
    except PydanticValidationError:
        return None  # Skip on validation failure — not worth a "try_again" for prose

    duration_ms = int((time.monotonic() - start_ts) * 1000)
    return _write_recommendation_row(
        db,
        user_id=user_id,
        rec_type="sweet_spots",
        input_signature=signature,
        response_json=raw,
        cred=cred,
        tool_version=tool_version,
        usage=usage,
        web_search_count=web_search_count,
        duration_ms=duration_ms,
        generated_by=generated_by,
    )


# ---------------------------------------------------------------------------
# Coffee-rec composite three-tier driver (AI-03)
# ---------------------------------------------------------------------------


def _build_coffee_rec_prompt(
    profile: dict[str, Any],
    sweet_spots: list[Any],
    *,
    origin: str | None = None,
    process: str | None = None,
    roast_level: str | None = None,
    tier: str = "primary",
) -> str:
    """Build the search prompt for the given tier.

    - primary: uses top origin + process + roast_level from profile
    - broadened: uses top origin only (relaxed constraints)
    - characteristics_only: uses overall preference profile without session history
    """
    # Extract top preferences
    top_origin = origin or (profile.get("origin", [{}])[0].label if profile.get("origin") else "")
    top_process = process or (
        profile.get("process", [{}])[0].label if profile.get("process") else ""
    )
    top_roast = roast_level or (
        profile.get("roast_level", [{}])[0].label if profile.get("roast_level") else ""
    )

    if sweet_spots:
        sweet_text = "; ".join(
            f"{r.origin} {r.process} via {r.brewer_name} (avg {float(r.avg_rating):.1f})"
            for r in sweet_spots[:2]
        )
        grounding = f"Their best brews: {sweet_text}."
    else:
        grounding = ""

    # D-14: for-sale-only clause — append to every tier
    for_sale_clause = (
        " Only recommend coffees that are currently for sale at the roaster's website. "
        "Avoid archived, sold-out, or discontinued lots."
    )

    if tier == "primary":
        style = f"{top_roast} {top_process} {top_origin}".strip()
        return (
            f"Find a specialty coffee to buy next for a pour-over enthusiast. "
            f"Their preferred style: {style}. {grounding} "
            f"Find a currently available, purchasable bag from a reputable specialty roaster. "
            f"Provide the buy URL for the specific product page."
            f"{for_sale_clause}"
        )
    elif tier == "broadened":
        return (
            f"Find a specialty coffee to buy next for a pour-over enthusiast. "
            f"Preferred origin: {top_origin}. {grounding} "
            f"Broaden to any process or roast level from this origin. "
            f"Find a currently available, purchasable bag. Provide the buy URL."
            f"{for_sale_clause}"
        )
    else:  # characteristics_only
        style = f"{top_roast} roast, {top_origin} origin".strip(", ")
        return (
            f"Recommend a specialty coffee for a pour-over enthusiast who enjoys {style}. "
            f"{grounding} "
            f"No web search needed — use your knowledge of well-regarded specialty roasters. "
            f"Set buy_url to null and search_tier to 'characteristics_only'."
            f"{for_sale_clause}"
        )


async def _generate_coffee_rec(
    db: Session,
    *,
    user_id: int,
    generated_by: str,
    signature: str,
) -> tuple[str, AIRecommendation | None]:
    """Drive the three-tier coffee-rec flow with Anthropic→OpenAI provider fallback.

    D-15 / AIX-13: p95 latency target ≤ 60s (web-search-tool dominates; see 19-CONTEXT.md).

    Returns (status, row) where status is one of:
    "generated" | "try_again" | "not_configured"

    Three tiers (AI-03):
    1. primary (origin+process+roast_level, max_uses=ai_primary_max_searches)
    2. broadened (origin only, max_uses=ai_broadened_max_searches)
    3. characteristics_only (no web_search, no buy_url)

    Provider order: Anthropic first; _is_anthropic_fallback_error → OpenAI.
    All tiers failing Pydantic validation → write error row, return "try_again".
    """
    from pydantic import ValidationError as PydanticValidationError

    # Read credentials — try anthropic first, fall back to openai
    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    if anthropic_cred is None and openai_cred is None:
        return "not_configured", None

    # Gather grounding data (sync reads before the async LLM call — Pitfall 5)
    profile = analytics_service.get_preference_profile(db, user_id)
    sweet_spots = analytics_service.get_sweet_spots(db, user_id)

    primary_max = settings_service.get_int("ai_primary_max_searches")
    broadened_max = settings_service.get_int("ai_broadened_max_searches")
    region = settings_service.get_str("recommendation_region")
    tool_version_anthropic = settings_service.get_str("ai_tool_version_anthropic")
    tool_version_openai = settings_service.get_str("ai_tool_version_openai")

    tiers = [
        ("primary", primary_max),
        ("broadened", broadened_max),
        ("characteristics_only", 0),  # no web search on tier 3
    ]

    cred = anthropic_cred or openai_cred  # active credential for structlog / write
    if cred is None:  # guarded by the not_configured check above
        return "not_configured", None

    start_ts = time.monotonic()
    last_error: Exception | None = None
    _archived_retry_attempted = False  # D-14: one-shot retry guard

    for tier_name, max_uses in tiers:
        prompt = _build_coffee_rec_prompt(
            profile,
            sweet_spots,
            tier=tier_name,
        )

        raw: dict[str, Any] | None = None
        usage: Any = None
        web_search_count = 0
        used_cred = cred
        used_tool_version = tool_version_anthropic

        # Try Anthropic if available
        if anthropic_cred is not None:
            anthropic_client = _build_anthropic_client(anthropic_cred)
            try:
                if tier_name == "characteristics_only":
                    # No web search on tier 3 — use a simple message
                    response = anthropic_client.messages.create(
                        model=anthropic_cred.model_name,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT_VOICE,
                        messages=[{"role": "user", "content": prompt}],
                        tools=[
                            {
                                "name": "structure_output",
                                "description": "Return the structured coffee recommendation",
                                "input_schema": CoffeeRecSchema.model_json_schema(),
                            }
                        ],  # type: ignore[arg-type]
                    )
                else:
                    response = anthropic_client.messages.create(
                        model=anthropic_cred.model_name,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT_VOICE,
                        messages=[{"role": "user", "content": prompt}],
                        tools=[  # type: ignore[arg-type]
                            {
                                "type": tool_version_anthropic,
                                "name": "web_search",
                                "max_uses": max_uses,
                                "user_location": {
                                    "type": "approximate",
                                    "country": region,
                                },
                            },
                            {
                                "name": "structure_output",
                                "description": "Return the structured coffee recommendation",
                                "input_schema": CoffeeRecSchema.model_json_schema(),
                            },
                        ],
                    )
                raw = _project_tool_use_input(response.content, "structure_output")
                usage = response.usage
                web_search_count = getattr(
                    getattr(response.usage, "server_tool_use", None),
                    "web_search_requests",
                    0,
                )
                used_cred = anthropic_cred
            except (ValueError, PydanticValidationError) as e:
                # Projector found no tool_use or schema mismatch — advance tier
                last_error = e
                log.warning(
                    AI_TIER_FALLBACK,
                    user_id=user_id,
                    from_tier=tier_name,
                    to_tier="next",
                    reason=type(e).__name__,
                )
                continue
            except BaseException as e:
                if _is_anthropic_fallback_error(e):
                    log.warning(
                        AI_FALLBACK_TRIGGERED,
                        user_id=user_id,
                        rec_type="coffee",
                        from_provider="anthropic",
                        reason=type(e).__name__,
                    )
                    # Fall through to OpenAI
                    if openai_cred is not None:
                        pass  # handled below
                    else:
                        last_error = e
                        continue
                else:
                    raise

        # OpenAI fallback (or primary if no anthropic cred)
        if raw is None and openai_cred is not None:
            openai_client = _build_openai_client(openai_cred)
            try:
                raw, usage, web_search_count = _openai_coffee_call(
                    openai_client,
                    model=openai_cred.model_name,
                    prompt=prompt,
                )
                used_cred = openai_cred
                used_tool_version = tool_version_openai
            except (json.JSONDecodeError, PydanticValidationError, Exception) as e:
                last_error = e
                log.warning(
                    AI_TIER_FALLBACK,
                    user_id=user_id,
                    from_tier=tier_name,
                    to_tier="next",
                    reason=f"openai_{type(e).__name__}",
                )
                continue

        if raw is None:
            continue

        # Validate the raw dict
        try:
            rec_schema = CoffeeRecSchema.model_validate(raw)
        except PydanticValidationError as e:
            last_error = e
            log.warning(
                AI_TIER_FALLBACK,
                user_id=user_id,
                from_tier=tier_name,
                to_tier="next",
                reason="pydantic_error",
            )
            continue

        # Set the tier on the validated schema
        # (force-set since the LLM may not have set it correctly for broadened/tier3)
        rec_schema = rec_schema.model_copy(update={"search_tier": tier_name})

        # D-14: archived-coffee detection — verify buy_url; retry once with broadened
        # instruction if the first candidate appears archived/gone.
        if rec_schema.buy_url and not _archived_retry_attempted and tier_name == "primary":
            url_ok = await _verify_buy_url(
                rec_schema.buy_url,
                roaster_name=rec_schema.roaster_name or "",
                coffee_name=rec_schema.coffee_name,
            )
            if not url_ok:
                _archived_retry_attempted = True
                log.warning(
                    AI_URL_VERIFY,
                    user_id=user_id,
                    url=rec_schema.buy_url,
                    result="archived_retry",
                )
                retry_prompt = (
                    "Try again with a broader search; the first candidate appears archived. "
                    + _build_coffee_rec_prompt(
                        profile,
                        sweet_spots,
                        tier="broadened",
                    )
                )
                retry_raw: dict[str, Any] | None = None
                if anthropic_cred is not None:
                    anthropic_client_retry = _build_anthropic_client(anthropic_cred)
                    try:
                        retry_resp = anthropic_client_retry.messages.create(
                            model=anthropic_cred.model_name,
                            max_tokens=2048,
                            system=SYSTEM_PROMPT_VOICE,
                            messages=[{"role": "user", "content": retry_prompt}],
                            tools=[  # type: ignore[arg-type]
                                {
                                    "type": tool_version_anthropic,
                                    "name": "web_search",
                                    "max_uses": broadened_max,
                                    "user_location": {
                                        "type": "approximate",
                                        "country": region,
                                    },
                                },
                                {
                                    "name": "structure_output",
                                    "description": "Return the structured coffee recommendation",
                                    "input_schema": CoffeeRecSchema.model_json_schema(),
                                },
                            ],
                        )
                        retry_raw = _project_tool_use_input(retry_resp.content, "structure_output")
                        usage = retry_resp.usage
                        web_search_count = getattr(
                            getattr(retry_resp.usage, "server_tool_use", None),
                            "web_search_requests",
                            0,
                        )
                        used_cred = anthropic_cred
                    except Exception:
                        retry_raw = None
                if retry_raw is None and openai_cred is not None:
                    openai_client_retry = _build_openai_client(openai_cred)
                    try:
                        retry_raw, usage, web_search_count = _openai_coffee_call(
                            openai_client_retry,
                            model=openai_cred.model_name,
                            prompt=retry_prompt,
                        )
                        used_cred = openai_cred
                        used_tool_version = tool_version_openai
                    except Exception:
                        retry_raw = None
                if retry_raw is not None:
                    try:
                        rec_schema = CoffeeRecSchema.model_validate(retry_raw)
                        rec_schema = rec_schema.model_copy(update={"search_tier": "broadened"})
                    except PydanticValidationError:
                        # Retry schema invalid — fall through to next tier
                        continue
                else:
                    # Retry got no raw output — fall through to next tier
                    continue

        # Attach recipe_suggestion and alt_brewer (SQL sub-flows — no LLM)
        recipe_sug = suggest_recipe(
            db,
            user_id=user_id,
            origin=rec_schema.origin,
            process=rec_schema.process,
            roast_level=rec_schema.roast_level,
        )
        alt_brewer = alt_brewer_callout(
            db,
            user_id=user_id,
            origin=rec_schema.origin,
            process=rec_schema.process,
            roast_level=rec_schema.roast_level,
        )
        rec_schema = rec_schema.model_copy(
            update={
                "recipe_suggestion": recipe_sug,
                "alt_brewer": alt_brewer,
            }
        )

        duration_ms = int((time.monotonic() - start_ts) * 1000)
        rec_row = _write_recommendation_row(
            db,
            user_id=user_id,
            rec_type="coffee",
            input_signature=signature,
            response_json=rec_schema.model_dump(),
            cred=used_cred,
            tool_version=used_tool_version,
            usage=usage,
            web_search_count=web_search_count,
            duration_ms=duration_ms,
            generated_by=generated_by,
            url_verified=None,  # deferred to 07-05 background verify task
        )
        log.info(
            AI_GENERATION_SUCCESS,
            user_id=user_id,
            rec_type="coffee",
            provider=used_cred.provider,
            model=used_cred.model_name,
            tier=tier_name,
            tokens_input=getattr(usage, "input_tokens", 0),
            tokens_output=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )
        return "generated", rec_row

    # All tiers failed validation
    duration_ms = int((time.monotonic() - start_ts) * 1000)
    log.error(
        AI_GENERATION_ERROR,
        user_id=user_id,
        rec_type="coffee",
        error_class=type(last_error).__name__ if last_error else "unknown",
        error_status="pydantic_error",
    )
    _write_recommendation_row(
        db,
        user_id=user_id,
        rec_type="coffee",
        input_signature=signature,
        response_json={},
        cred=cred,
        tool_version=tool_version_anthropic,
        usage=None,
        web_search_count=0,
        duration_ms=duration_ms,
        generated_by=generated_by,
        error_status="pydantic_error",
    )
    return "try_again", None


# ---------------------------------------------------------------------------
# Telemetry write helper (AI-02)
# ---------------------------------------------------------------------------


def _write_recommendation_row(
    db: Session,
    *,
    user_id: int,
    rec_type: str,
    input_signature: str,
    response_json: dict[str, Any],
    cred: credentials_service.ProviderCredential,
    tool_version: str | None,
    usage: Any,
    web_search_count: int,
    duration_ms: int | None,
    generated_by: str,
    url_verified: bool | None = None,
    error_status: str | None = None,
) -> AIRecommendation:
    """Persist one ``ai_recommendations`` row with full AI-02 telemetry.

    Token counts are extracted from *usage* via ``getattr`` with 0 defaults
    so both Anthropic (``usage.input_tokens`` / ``usage.output_tokens``) and
    OpenAI (``usage.input_tokens`` / ``usage.output_tokens`` on the Responses
    API) usage shapes work without branching.

    Assumption A1 (TODO): Anthropic SDK 0.102 does not expose the
    ``tokens_input_search`` split (web-search-billed input tokens). We
    default it to 0 and leave a TODO here for when the SDK exposes it.
    Track the open question at: platform.anthropic.com/docs/web-search.
    """
    # TODO(A1): extract tokens_input_search when Anthropic SDK exposes the split
    tokens_input_search = 0

    rec_row = AIRecommendation(
        user_id=user_id,
        recommendation_type=rec_type,
        input_signature=input_signature,
        response_json=response_json,
        provider_used=cred.provider,
        model_used=cred.model_name,
        tool_version=tool_version,
        tokens_input=getattr(usage, "input_tokens", 0),
        tokens_output=getattr(usage, "output_tokens", 0),
        tokens_input_search=tokens_input_search,
        web_search_count=web_search_count,
        url_verified=url_verified,
        duration_ms=duration_ms,
        generated_by=generated_by,
        error_status=error_status,
    )
    db.add(rec_row)
    db.commit()
    return rec_row


# ---------------------------------------------------------------------------
# Read helpers (AI-15, SCHED-02)
# ---------------------------------------------------------------------------


def get_latest_recommendation(
    db: Session,
    *,
    user_id: int,
    rec_type: str,
) -> AIRecommendation | None:
    """Return the newest successful row for (user_id, rec_type), or None.

    Filters out error rows (error_status IS NULL) so callers always
    receive a valid recommendation or None. User-scoped (IDOR: always
    filters by user_id == user_id first).
    """
    return db.execute(
        select(AIRecommendation)
        .where(
            AIRecommendation.user_id == user_id,
            AIRecommendation.recommendation_type == rec_type,
            AIRecommendation.error_status.is_(None),
        )
        .order_by(AIRecommendation.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def is_stale(db: Session, *, user_id: int) -> bool:
    """Return True when the current signature differs from the stored coffee row's.

    Implements AI-15: the router/poll uses this to show the "stale badge"
    when the user has logged new rated sessions since the last generation.
    """
    current_sig = analytics_service.compute_input_signature(db, user_id)
    row = get_latest_recommendation(db, user_id=user_id, rec_type="coffee")
    if row is None:
        return False  # no row → not stale (not yet generated)
    return current_sig != row.input_signature


def in_flight(user_id: int, rec_type: str = "coffee") -> bool:
    """Return True when an active regeneration run holds the in-memory lock.

    The router/poll endpoint calls this to decide whether to show the
    in-flight spinner vs. the complete hero card.
    """
    return _get_lock(user_id, rec_type).locked()


# ---------------------------------------------------------------------------
# regenerate() — SCHED-02 entry point (Phase 8 calls this directly)
# ---------------------------------------------------------------------------


async def regenerate(
    user_id: int,
    generated_by: str,
    *,
    db: Session,
    force: bool = False,
) -> str:
    """Generate (or skip) the user's cached nightly bundle (D-06).

    Returns one of:
    - ``"generated"``      — new coffee + sweet_spots rows written
    - ``"skipped"``        — unchanged signature (force=False) or cold-start gate closed
    - ``"locked"``         — concurrent run in progress (in-memory or advisory lock)
    - ``"try_again"``      — all tiers failed Pydantic validation
    - ``"not_configured"`` — no provider credential enabled
    - ``"error"``          — unexpected exception; error row written

    SCHED-02 contract (frozen signature): Phase 8 calls:
        ``regenerate(uid, "scheduler", db=db)``

    DB / async interaction (Pitfall 5 / Open Question 2):
    Sync DB reads are done BEFORE the awaited LLM call, and sync DB writes
    are done AFTER it returns. We never hold a sync Session open across an
    ``await`` on the event loop — the pre-read/post-write bracketing approach
    keeps the event loop unblocked during the potentially multi-second LLM
    network call.
    """
    log.info(AI_GENERATION_START, user_id=user_id, rec_type="coffee", generated_by=generated_by)

    # (1) Cold-start gate — no AI for users below the session/note threshold (AI-11)
    gate = analytics_service.get_cold_start_counts(db, user_id)
    if not gate["gate_open"]:
        log.info(AI_REGEN_SKIPPED, user_id=user_id, rec_type="coffee", reason="cold_start")
        return "skipped"

    # (2) In-memory lock — process-local guard for single uvicorn worker (AI-13)
    lock = _get_lock(user_id, "coffee")
    if lock.locked():
        return "locked"

    async with lock:
        # (3) Advisory lock — Postgres cross-process backstop (AI-13)
        if not _try_advisory_lock(db, user_id, "coffee"):
            return "locked"

        # (4) Signature check (sync DB read before the LLM await — Pitfall 5)
        current_sig = analytics_service.compute_input_signature(db, user_id)
        stored_row = get_latest_recommendation(db, user_id=user_id, rec_type="coffee")
        stored_sig = stored_row.input_signature if stored_row else None

        if stored_sig == current_sig and not force:
            log.info(
                AI_REGEN_SKIPPED,
                user_id=user_id,
                rec_type="coffee",
                reason="sig_unchanged",
            )
            return "skipped"

        try:
            # (5) Coffee-rec flow (contains the awaited LLM call)
            status, _coffee_row = await _generate_coffee_rec(
                db,
                user_id=user_id,
                generated_by=generated_by,
                signature=current_sig,
            )
            if status in ("try_again", "not_configured"):
                return status

            # (6) Sweet-spots prose (written in same regeneration flow, AI-10)
            await _generate_sweet_spots_prose(
                db,
                user_id=user_id,
                generated_by=generated_by,
                cred=(
                    credentials_service.get_provider_credential(db, "anthropic")
                    or credentials_service.get_provider_credential(db, "openai")
                ),
                signature=current_sig,
            )

            log.info(AI_GENERATION_SUCCESS, user_id=user_id, rec_type="coffee")
            return "generated"

        except Exception as exc:
            log.error(
                AI_GENERATION_ERROR,
                user_id=user_id,
                rec_type="coffee",
                error_class=type(exc).__name__,
                error_status="unexpected_error",
            )
            return "error"


# ---------------------------------------------------------------------------
# Equipment recommendation flow (AI-08, D-05 — profile-only, no web search)
# ---------------------------------------------------------------------------


async def generate_equipment_rec(
    user_id: int,
    generated_by: str,
    *,
    db: Session,
) -> tuple[str, AIRecommendation | None]:
    """Generate an on-demand equipment recommendation for *user_id*.

    D-15 / AIX-13: p95 latency target ≤ 20s (single structured call, no web search).

    Profile-only: reads the user's active equipment list + preference profile
    and makes ONE LLM call with NO web_search server tool (D-05 / AI-08).
    The LLM may return weakest_link=None when the setup is well-matched —
    that is a valid, common outcome.

    Returns (status, row) where status is one of:
    "generated" | "try_again" | "not_configured"

    This function is NEVER called from ``regenerate()`` — it is on-demand
    only and writes a telemetry row with rec_type="equipment".
    """
    from pydantic import ValidationError as PydanticValidationError

    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    if anthropic_cred is None and openai_cred is None:
        return "not_configured", None

    # Sync reads before any awaited call (Pitfall 5)
    equipment_rows = (
        db.execute(select(Equipment).where(Equipment.archived.is_(False))).scalars().all()
    )
    profile = analytics_service.get_preference_profile(db, user_id)

    # Build equipment summary for the prompt
    if equipment_rows:
        equip_lines = "\n".join(f"- {e.type}: {e.brand} {e.model}" for e in equipment_rows)
    else:
        equip_lines = "(no equipment logged yet)"

    # Build preference summary
    top_origins = [r.label for r in profile.get("origin", [])[:3]]
    top_processes = [r.label for r in profile.get("process", [])[:3]]
    top_roasts = [r.label for r in profile.get("roast_level", [])[:2]]
    pref_text = (
        f"Preferred origins: {', '.join(top_origins) or 'varied'}. "
        f"Preferred processes: {', '.join(top_processes) or 'varied'}. "
        f"Preferred roast levels: {', '.join(top_roasts) or 'varied'}."
    )

    prompt = (
        f"Assess the following pour-over brewing setup and identify the weakest link, "
        f"if any.\n\nEquipment:\n{equip_lines}\n\n"
        f"User taste profile: {pref_text}\n\n"
        f"If the setup is well-matched and no upgrade would meaningfully improve the cup, "
        f"set weakest_link and recommendation to null. "
        f"Only recommend an upgrade when it would make a concrete, noticeable difference."
    )

    cred = anthropic_cred or openai_cred
    if cred is None:
        return "not_configured", None

    start_ts = time.monotonic()
    tool_version = settings_service.get_str("ai_tool_version_anthropic")
    raw: dict[str, Any] | None = None
    usage: Any = None

    # Anthropic path (no web_search tool — profile-only, AI-08/D-05)
    if anthropic_cred is not None:
        client = _build_anthropic_client(anthropic_cred)
        try:
            response = client.messages.create(
                model=anthropic_cred.model_name,
                max_tokens=512,
                system=SYSTEM_PROMPT_VOICE,
                messages=[{"role": "user", "content": prompt}],
                tools=[  # type: ignore[arg-type]
                    {
                        "name": "structure_output",
                        "description": "Return the equipment recommendation",
                        "input_schema": EquipmentRecSchema.model_json_schema(),
                    }
                ],
            )
            raw = _project_tool_use_input(response.content, "structure_output")
            usage = response.usage
            cred = anthropic_cred
        except BaseException as e:
            if _is_anthropic_fallback_error(e):
                log.warning(
                    AI_FALLBACK_TRIGGERED,
                    user_id=user_id,
                    rec_type="equipment",
                    from_provider="anthropic",
                    reason=type(e).__name__,
                )
                raw = None  # fall through to OpenAI
            else:
                raise

    # OpenAI fallback (prompt-based JSON, no tools needed)
    if raw is None and openai_cred is not None:
        oai_client = _build_openai_client(openai_cred)
        schema_hint = json.dumps(EquipmentRecSchema.model_json_schema(), separators=(",", ":"))
        full_prompt = f"{prompt}\n\nRespond with JSON matching this schema:\n{schema_hint}"
        try:
            response = oai_client.responses.create(
                model=openai_cred.model_name,
                input=[{"role": "user", "content": full_prompt}],
            )
            text_out = ""
            for item in response.output:
                if item.type == "message":
                    for c in item.content:
                        if c.type == "output_text":
                            text_out = c.text
                            break
            raw = json.loads(text_out)
            usage = response.usage
            cred = openai_cred
            tool_version = settings_service.get_str("ai_tool_version_openai")
        except Exception as e:
            log.error(
                AI_GENERATION_ERROR,
                user_id=user_id,
                rec_type="equipment",
                error_class=type(e).__name__,
                error_status="provider_error",
            )

    if raw is None:
        return "try_again", None

    # Validate via EquipmentRecSchema (T-07-02)
    try:
        EquipmentRecSchema.model_validate(raw)
    except PydanticValidationError as e:
        log.error(
            AI_GENERATION_ERROR,
            user_id=user_id,
            rec_type="equipment",
            error_class=type(e).__name__,
            error_status="pydantic_error",
        )
        _write_recommendation_row(
            db,
            user_id=user_id,
            rec_type="equipment",
            input_signature="",
            response_json={},
            cred=cred,
            tool_version=tool_version,
            usage=usage,
            web_search_count=0,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            generated_by=generated_by,
            error_status="pydantic_error",
        )
        return "try_again", None

    duration_ms = int((time.monotonic() - start_ts) * 1000)
    rec_row = _write_recommendation_row(
        db,
        user_id=user_id,
        rec_type="equipment",
        input_signature="",  # no signature gate for on-demand flows
        response_json=raw,
        cred=cred,
        tool_version=tool_version,
        usage=usage,
        web_search_count=0,  # never any web search (AI-08/D-05)
        duration_ms=duration_ms,
        generated_by=generated_by,
    )
    log.info(
        AI_GENERATION_SUCCESS,
        user_id=user_id,
        rec_type="equipment",
        provider=cred.provider,
        model=cred.model_name,
        duration_ms=duration_ms,
    )
    return "generated", rec_row


# ---------------------------------------------------------------------------
# Paste-and-rank helpers (AI-09, D-07/D-08)
# ---------------------------------------------------------------------------


class _TextExtractor(html.parser.HTMLParser):
    """Collect text content inside p, h1, h2 tags.

    Ignores script/style blocks and all other elements. Tolerates truncated
    HTML (assumption A5 — html.parser handles parse errors gracefully).
    """

    _COLLECT_TAGS = frozenset({"p", "h1", "h2"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._collecting = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._COLLECT_TAGS:
            self._collecting = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._COLLECT_TAGS:
            self._collecting = False

    def handle_data(self, data: str) -> None:
        if self._collecting:
            stripped = data.strip()
            if stripped:
                self.chunks.append(stripped)

    def error(self, message: str) -> None:
        # Tolerate parse errors on truncated HTML (assumption A5)
        pass


def _split_inputs(raw: str) -> tuple[list[str], list[str]]:
    """Split a paste-rank textarea into URL lines and freeform text blocks.

    Lines that start with 'http://' or 'https://' are detected as URLs.
    All other non-empty lines accumulate into the text blocks list (D-08).
    """
    urls: list[str] = []
    texts: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("http://") or stripped.startswith("https://"):
            urls.append(stripped)
        else:
            texts.append(stripped)
    return urls, texts


async def _fetch_page_text(url: str) -> str:
    """Fetch a URL and extract paragraph/heading text for paste-rank grounding.

    SSRF mitigations (T-07-09, mirrors _verify_buy_url):
    - **Scheme allowlist**: rejects any non-https URL before making a network
      call (http://, file://, ftp://, etc. all return empty string).
    - **No cross-host redirects**: ``follow_redirects=False`` so a 302 to an
      internal metadata endpoint is never followed.
    - **Body cap**: ``Range: bytes=0-131071`` (128 KB) bounds the download.
    - **Timeout**: ``httpx.Timeout(5.0)`` hard-kills the request after 5 s.

    Returns extracted text (p/h1/h2 content via stdlib html.parser), capped
    to approximately 8000 tokens (~32 000 chars). Returns empty string on any
    failure mode (bad scheme, bad status, timeout, network error).
    """
    # Scheme allowlist — no network call for non-https (T-07-09 SSRF)
    if not url.startswith("https://"):
        return ""
    # Resolve-validate gate — reject private/loopback/link-local/reserved IPs (S1)
    if not _assert_public_host(url):
        return ""

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,  # SSRF: block cross-host redirects
            timeout=httpx.Timeout(5.0),  # SSRF: hard 5s timeout
        ) as client:
            r = await client.get(
                url,
                headers={
                    "Range": "bytes=0-131071",  # SSRF: 128KB body cap
                    "User-Agent": VERIFY_UA,
                },
            )

        if r.status_code not in (200, 206):
            return ""

        parser = _TextExtractor()
        try:
            parser.feed(r.text)
        except Exception:  # noqa: S110 — tolerate truncated HTML parse errors (assumption A5)
            pass

        extracted = " ".join(parser.chunks)
        # Cap at ~32 000 chars ≈ 8 000 tokens to stay well inside context limits
        return extracted[:32_000]

    except (httpx.TimeoutException, httpx.RequestError):
        return ""


async def rank_pasted_coffees(
    user_id: int,
    generated_by: str,
    *,
    db: Session,
    raw_input: str,
) -> tuple[str, PasteRankSchema | None]:
    """Rank pasted coffee descriptions or URLs by predicted enjoyment (AI-09, D-07/D-08).

    D-15 / AIX-13: p95 latency target ≤ 45s (URL fetches + single structured call).

    Accepts freeform text AND/OR https:// URLs in *raw_input*. URLs are
    fetched via the SSRF-hardened ranged-GET machinery (_fetch_page_text)
    before being fed to the model alongside any pasted text. Failed fetches
    are silently skipped — the model still ranks the text entries.

    Returns at most 3 ranked items (PasteRankSchema.ranked max_length=3),
    each with one-sentence reasoning grounded in the user's taste profile.

    This function is NEVER called from ``regenerate()`` and is never
    cached or signature-gated. A telemetry row with rec_type="paste_rank"
    is always written (D-07 / AI-09).
    """
    from pydantic import ValidationError as PydanticValidationError

    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    if anthropic_cred is None and openai_cred is None:
        return "not_configured", None

    # Sync reads before any awaited calls (Pitfall 5)
    profile = analytics_service.get_preference_profile(db, user_id)

    # Split input into URLs and text blocks (D-08)
    urls, text_blocks = _split_inputs(raw_input)

    # Fetch URL content (SSRF-hardened; failed fetches silently omitted).
    # CR-04: cap the number of fetches — each is a sequential ranged GET with a
    # 5s timeout, so an unbounded list could block the event loop for minutes.
    url_texts: list[str] = []
    for url in urls[:_MAX_PASTE_RANK_URLS]:
        fetched = await _fetch_page_text(url)
        if fetched:
            url_texts.append(f"[From {url}]: {fetched[:4000]}")  # cap per URL

    # Combine all input text for the model
    all_text_parts = text_blocks + url_texts
    combined_input = "\n\n".join(all_text_parts) if all_text_parts else raw_input

    # Build preference summary
    top_origins = [r.label for r in profile.get("origin", [])[:3]]
    top_processes = [r.label for r in profile.get("process", [])[:3]]
    pref_text = (
        f"Preferred origins: {', '.join(top_origins) or 'varied'}. "
        f"Preferred processes: {', '.join(top_processes) or 'varied'}."
    )

    prompt = (
        f"Rank these coffees by predicted enjoyment for a pour-over enthusiast.\n\n"
        f"User taste profile: {pref_text}\n\n"
        f"Coffees to rank:\n{combined_input}\n\n"
        f"Return up to 3 ranked coffees. For each, give one sentence of reasoning "
        f"grounded in the user's actual taste profile. "
        f"Best match goes first. Fewer than 3 is fine if fewer are provided."
    )

    cred = anthropic_cred or openai_cred
    if cred is None:
        return "not_configured", None

    start_ts = time.monotonic()
    tool_version = settings_service.get_str("ai_tool_version_anthropic")
    raw: dict[str, Any] | None = None
    usage: Any = None

    # Anthropic path (no web_search — user-supplied URLs already fetched above)
    if anthropic_cred is not None:
        client = _build_anthropic_client(anthropic_cred)
        try:
            response = client.messages.create(
                model=anthropic_cred.model_name,
                max_tokens=1024,
                system=SYSTEM_PROMPT_VOICE,
                messages=[{"role": "user", "content": prompt}],
                tools=[  # type: ignore[arg-type]
                    {
                        "name": "structure_output",
                        "description": "Return the ranked coffee list",
                        "input_schema": PasteRankSchema.model_json_schema(),
                    }
                ],
            )
            raw = _project_tool_use_input(response.content, "structure_output")
            usage = response.usage
            cred = anthropic_cred
        except BaseException as e:
            if _is_anthropic_fallback_error(e):
                log.warning(
                    AI_FALLBACK_TRIGGERED,
                    user_id=user_id,
                    rec_type="paste_rank",
                    from_provider="anthropic",
                    reason=type(e).__name__,
                )
                raw = None  # fall through to OpenAI
            else:
                raise

    # OpenAI fallback (prompt-based JSON)
    if raw is None and openai_cred is not None:
        oai_client = _build_openai_client(openai_cred)
        schema_hint = json.dumps(PasteRankSchema.model_json_schema(), separators=(",", ":"))
        full_prompt = f"{prompt}\n\nRespond with JSON matching this schema:\n{schema_hint}"
        try:
            response = oai_client.responses.create(
                model=openai_cred.model_name,
                input=[{"role": "user", "content": full_prompt}],
            )
            text_out = ""
            for item in response.output:
                if item.type == "message":
                    for c in item.content:
                        if c.type == "output_text":
                            text_out = c.text
                            break
            raw = json.loads(text_out)
            usage = response.usage
            cred = openai_cred
            tool_version = settings_service.get_str("ai_tool_version_openai")
        except Exception as e:
            log.error(
                AI_GENERATION_ERROR,
                user_id=user_id,
                rec_type="paste_rank",
                error_class=type(e).__name__,
                error_status="provider_error",
            )

    if raw is None:
        return "try_again", None

    # Validate via PasteRankSchema (T-07-02)
    try:
        PasteRankSchema.model_validate(raw)
    except PydanticValidationError as e:
        log.error(
            AI_GENERATION_ERROR,
            user_id=user_id,
            rec_type="paste_rank",
            error_class=type(e).__name__,
            error_status="pydantic_error",
        )
        _write_recommendation_row(
            db,
            user_id=user_id,
            rec_type="paste_rank",
            input_signature="",
            response_json={},
            cred=cred,
            tool_version=tool_version,
            usage=usage,
            web_search_count=0,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            generated_by=generated_by,
            error_status="pydantic_error",
        )
        return "try_again", None

    duration_ms = int((time.monotonic() - start_ts) * 1000)
    _write_recommendation_row(
        db,
        user_id=user_id,
        rec_type="paste_rank",
        input_signature="",  # not signature-gated (D-07/AI-09)
        response_json=raw,
        cred=cred,
        tool_version=tool_version,
        usage=usage,
        web_search_count=0,
        duration_ms=duration_ms,
        generated_by=generated_by,
    )
    log.info(
        AI_GENERATION_SUCCESS,
        user_id=user_id,
        rec_type="paste_rank",
        provider=cred.provider,
        model=cred.model_name,
        duration_ms=duration_ms,
    )
    return "generated", PasteRankSchema.model_validate(raw)


# ---------------------------------------------------------------------------
# Improve-brew SSE flow (AIX-12 / D-12 / D-16)
# ---------------------------------------------------------------------------

_REC_TYPE_BREW_IMPROVEMENT = "brew_improvement"


# p95 target: <= 20s
async def generate_brew_improvement(
    db: Session,
    *,
    user_id: int,
    session_id: int,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Two-phase SSE generator for the 'coach this brew' flow (AIX-12 / D-16).

    Gate ordering:
      1. Credential check
      2. Session load with user_id scope (IDOR: T-19-12)
      3. Quota check against improve_brew bucket (T-19-14)
      4. Advisory lock (T-19-10 reconnect guard)
      5. Phase 1: stream prose text deltas as event:message
      6. Phase 2: get_final_message() -> _project_tool_use_input -> BrewImproveSchema
      7. On ValidationError -> event:error; return
      8. Write telemetry row (rec_type='brew_improvement', duration_ms)
      9. Emit event:complete with validated result

    Prior sessions: ALL of the user's brew sessions for the session's coffee_id are
    serialized into the prompt (D-12) so the LLM proposes parameters NOT already tried.
    The user-scoped list_brew_sessions call is the IDOR boundary (T-19-12).

    Quota: counted against improve_brew bucket, separate from research (T-19-14 / D-08).
    OpenAI fallback uses a non-streaming structured call (RESEARCH Open Q#1).
    Error events emit a short user-facing string only (T-19-09 reused).
    """
    from app.services import ai_quota
    from app.services import brew_sessions as brew_sessions_service

    # (1) Credential check
    cred = credentials_service.get_provider_credential(
        db, "anthropic"
    ) or credentials_service.get_provider_credential(db, "openai")
    if cred is None:
        yield ServerSentEvent(data="AI provider not configured.", event="error")
        return

    # (2) Session load — user-scoped (IDOR: T-19-12)
    session = brew_sessions_service.get_brew_session(db, session_id=session_id, by_user_id=user_id)
    if session is None:
        yield ServerSentEvent(data="Brew session not found.", event="error")
        return

    coffee_id: int = session.coffee_id

    # (3) Quota check against improve_brew bucket (T-19-14 / D-08)
    remaining = ai_quota.remaining(db, user_id, _REC_TYPE_BREW_IMPROVEMENT)
    if remaining <= 0:
        reset_time = ai_quota.get_quota_reset_time(db, user_id, _REC_TYPE_BREW_IMPROVEMENT)
        msg = "Daily brew-improvement limit reached."
        if reset_time:
            delta = reset_time - __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            msg += f" Resets in {hours}h {mins}m."
        yield ServerSentEvent(data=msg, event="error")
        return

    # Load ALL prior sessions for this user + coffee (D-12 — prior-session-aware)
    prior_sessions = brew_sessions_service.list_brew_sessions(
        db, by_user_id=user_id, coffee_id=coffee_id
    )

    # (4) Advisory lock (T-19-10 reconnect guard)
    lock = _get_lock(user_id, _REC_TYPE_BREW_IMPROVEMENT)
    if lock.locked():
        yield ServerSentEvent(
            data="A brew-improvement request is already in progress.", event="error"
        )
        return

    async with lock:
        if not _try_advisory_lock(db, user_id, _REC_TYPE_BREW_IMPROVEMENT):
            yield ServerSentEvent(
                data="A brew-improvement request is already in progress.", event="error"
            )
            return

        prompt = _build_brew_improve_prompt(session, prior_sessions)
        tool_version: str | None = None
        start_ts = time.monotonic()
        usage_obj: Any = None
        result_schema: BrewImproveSchema | None = None

        if cred.provider == "anthropic":
            # Phase 1 + 2: two-phase streaming (D-16 Pattern 1 — mirrored from ai_research)
            async_client = anthropic.AsyncAnthropic(api_key=cred.key, max_retries=1)
            tool_version = "custom"

            tools: list[dict[str, Any]] = [
                {
                    "name": "structure_output",
                    "description": "Return the structured brew improvement coaching result",
                    "input_schema": BrewImproveSchema.model_json_schema(),
                }
            ]

            try:
                async with async_client.messages.stream(
                    model=cred.model_name,
                    max_tokens=1500,
                    system=SYSTEM_PROMPT_VOICE,
                    messages=[{"role": "user", "content": prompt}],
                    tools=tools,  # type: ignore[arg-type]
                ) as stream:
                    # Phase 1: emit prose deltas as event:message
                    async for text in stream.text_stream:
                        yield ServerSentEvent(data=text, event="message")

                    # Phase 2: extract structured output from final message
                    final_msg = await stream.get_final_message()
                    usage_obj = final_msg.usage

                try:
                    raw = _project_tool_use_input(final_msg.content, "structure_output")
                    result_schema = BrewImproveSchema.model_validate(raw)
                except (ValueError, ValidationError) as exc:
                    log.warning(
                        "ai_service.brew_improve.validation_failed",
                        user_id=user_id,
                        session_id=session_id,
                        error=type(exc).__name__,
                    )
                    yield ServerSentEvent(
                        data="Could not parse brew improvement result. Please try again.",
                        event="error",
                    )
                    duration_ms = int((time.monotonic() - start_ts) * 1000)
                    _write_recommendation_row(
                        db,
                        user_id=user_id,
                        rec_type=_REC_TYPE_BREW_IMPROVEMENT,
                        input_signature=str(session_id),
                        response_json={},
                        cred=cred,
                        tool_version=tool_version,
                        usage=usage_obj,
                        web_search_count=0,
                        duration_ms=duration_ms,
                        generated_by="user_request",
                        error_status="pydantic_error",
                    )
                    return

            except anthropic.APIError as exc:
                log.error(
                    "ai_service.brew_improve.anthropic_error",
                    user_id=user_id,
                    session_id=session_id,
                    error=type(exc).__name__,
                )
                yield ServerSentEvent(
                    data="AI provider error. Please try again later.",
                    event="error",
                )
                return

        else:
            # OpenAI fallback: non-streaming structured call (RESEARCH Open Q#1)
            import json as _json

            tool_version = "openai_structured"
            try:
                oai_client = _build_openai_client(cred)
                schema_hint = _json.dumps(
                    BrewImproveSchema.model_json_schema(), separators=(",", ":")
                )
                full_prompt = (
                    f"{prompt}\n\nRespond with a JSON object matching this schema exactly:"
                    f"\n{schema_hint}"
                )
                oai_response = oai_client.responses.create(
                    model=cred.model_name,
                    input=[{"role": "user", "content": full_prompt}],
                )
                text_out = ""
                for item in oai_response.output:
                    if item.type == "message":
                        for c in item.content:
                            if c.type == "output_text":
                                text_out = c.text
                                break
                raw = _json.loads(text_out)
                result_schema = BrewImproveSchema.model_validate(raw)
                usage_obj = oai_response.usage
                yield ServerSentEvent(data=result_schema.summary_prose, event="message")

            except Exception as exc:
                log.error(
                    "ai_service.brew_improve.openai_error",
                    user_id=user_id,
                    session_id=session_id,
                    error=type(exc).__name__,
                )
                yield ServerSentEvent(
                    data="AI provider error. Please try again later.",
                    event="error",
                )
                return

        duration_ms = int((time.monotonic() - start_ts) * 1000)

        # (8) Write telemetry row (AIX-13 / D-15)
        _write_recommendation_row(
            db,
            user_id=user_id,
            rec_type=_REC_TYPE_BREW_IMPROVEMENT,
            input_signature=str(session_id),
            response_json=result_schema.model_dump(),
            cred=cred,
            tool_version=tool_version,
            usage=usage_obj,
            web_search_count=0,
            duration_ms=duration_ms,
            generated_by="user_request",
        )

        log.info(
            AI_GENERATION_SUCCESS,
            user_id=user_id,
            rec_type=_REC_TYPE_BREW_IMPROVEMENT,
            session_id=session_id,
            provider=cred.provider,
            model=cred.model_name,
            duration_ms=duration_ms,
        )

        # (9) Emit event:complete with validated result JSON
        import json as _json

        yield ServerSentEvent(
            data=_json.dumps(result_schema.model_dump()),
            event="complete",
        )


def _build_brew_improve_prompt(session: Any, prior_sessions: list[Any]) -> str:
    """Build the prompt for the brew improvement flow.

    Serializes the target session's dial settings and ALL prior sessions for
    the same coffee so the LLM can propose parameters NOT already tried (D-12).
    prior_sessions includes the target session — the LLM sees the full history.
    """

    # Serialize each session's dial fields
    def _session_to_dict(s: Any) -> dict[str, Any]:
        return {
            "session_id": s.id,
            "grind": str(s.grind_setting_actual or ""),
            "ratio": (
                f"1:{float(s.water_grams_actual) / float(s.dose_grams_actual):.1f}"
                if s.dose_grams_actual and float(s.dose_grams_actual) > 0
                else ""
            ),
            "temp_c": str(s.water_temp_c_actual or ""),
            "brewer_id": s.brewer_id,
            "recipe_id": s.recipe_id,
            "rating": str(s.rating or "unrated"),
        }

    target_dict = _session_to_dict(session)
    prior_dicts = [_session_to_dict(s) for s in prior_sessions]

    import json as _json

    return (
        f"Analyze this brew session and coach the user on what to adjust next time.\n\n"
        f"Target session:\n{_json.dumps(target_dict, indent=2)}\n\n"
        f"All prior sessions for this coffee (including the target):\n"
        f"{_json.dumps(prior_dicts, indent=2)}\n\n"
        "Propose specific parameter changes the user has NOT already tried "
        "(compare with unchanged_parameters you identify from prior sessions). "
        "Focus on the most impactful dial. Keep coaching concrete and actionable."
    )


# ---------------------------------------------------------------------------
# Preference-profile prose flow (AIX-09 / D-10 / D-15)
# ---------------------------------------------------------------------------

_REC_TYPE_PREFERENCE_PROSE = "preference_profile_prose"


# p95 target: <= 30s
async def generate_preference_profile_prose(
    db: Session,
    *,
    user_id: int,
) -> tuple[str, AIRecommendation | None]:
    """Generate in-depth preference profile prose for *user_id* (AIX-09 / D-10).

    Non-SSE: signature-driven card refresh (D-16 limits SSE to three flows;
    preference_profile_prose is not one of them). Uses structured output via
    one synchronous LLM call.

    Prompt inputs (D-10):
    - get_preference_profile: origin / process / roaster / roast_level dimensions
    - get_flavor_descriptors: top-10 flavor notes (4.0+ rated sessions, min 2)
    - brew/cafe rating distribution: from compute_input_signature + flavor data
    - varietal preferences: highest-rated coffees from the preference profile

    Writes ai_recommendations with rec_type='preference_profile_prose' (signature-keyed,
    one row per user+signature). duration_ms telemetry (AIX-13 / D-15).

    Returns:
        ("generated", row) — new prose written
        ("skipped", row)   — signature unchanged, existing row returned
        ("try_again", None) — all provider paths failed validation
        ("not_configured", None) — no provider credential enabled
    """
    from pydantic import ValidationError as PydanticValidationError

    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    if anthropic_cred is None and openai_cred is None:
        return "not_configured", None

    cred = anthropic_cred or openai_cred

    # Sync reads before any awaited call (Pitfall 5 — pre-read/post-write bracketing)
    current_sig = analytics_service.compute_input_signature(db, user_id)

    # Signature check — skip if prose is already fresh for this signature
    existing_row = get_latest_recommendation(
        db, user_id=user_id, rec_type=_REC_TYPE_PREFERENCE_PROSE
    )
    if existing_row is not None and existing_row.input_signature == current_sig:
        return "skipped", existing_row

    # Build prompt inputs from analytics helpers (D-10)
    profile = analytics_service.get_preference_profile(db, user_id)
    flavor_descriptors = analytics_service.get_flavor_descriptors(db, user_id)

    prompt = _build_preference_prose_prompt(profile, flavor_descriptors)
    start_ts = time.monotonic()
    usage_obj: Any = None
    tool_version: str | None = None

    if anthropic_cred is not None:
        tool_version = "custom"
        client = anthropic.Anthropic(api_key=anthropic_cred.key, max_retries=1)
        try:
            resp = client.messages.create(
                model=anthropic_cred.model_name,
                max_tokens=1000,
                system=SYSTEM_PROMPT_VOICE,
                messages=[{"role": "user", "content": prompt}],
                tools=[  # type: ignore[arg-type]
                    {
                        "name": "structure_output",
                        "description": "Return the structured preference profile prose",
                        "input_schema": PreferenceProfileProseSchema.model_json_schema(),
                    }
                ],
            )
            usage_obj = resp.usage
            raw = _project_tool_use_input(resp.content, "structure_output")
            prose_schema = PreferenceProfileProseSchema.model_validate(raw)
        except (ValueError, PydanticValidationError, anthropic.APIError) as exc:
            log.error(
                AI_GENERATION_ERROR,
                user_id=user_id,
                rec_type=_REC_TYPE_PREFERENCE_PROSE,
                error_class=type(exc).__name__,
                error_status="pydantic_error",
            )
            _write_recommendation_row(
                db,
                user_id=user_id,
                rec_type=_REC_TYPE_PREFERENCE_PROSE,
                input_signature=current_sig,
                response_json={},
                cred=cred,  # type: ignore[arg-type]
                tool_version=tool_version,
                usage=usage_obj,
                web_search_count=0,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                generated_by="scheduler",
                error_status="pydantic_error",
            )
            return "try_again", None
    else:
        # OpenAI fallback: non-streaming structured call (RESEARCH Open Q#1)
        import json as _json

        tool_version = "openai_structured"
        try:
            oai_client = _build_openai_client(openai_cred)  # type: ignore[arg-type]
            schema_hint = _json.dumps(
                PreferenceProfileProseSchema.model_json_schema(), separators=(",", ":")
            )
            full_prompt = (
                f"{prompt}\n\nRespond with a JSON object matching this schema exactly:"
                f"\n{schema_hint}"
            )
            oai_resp = oai_client.responses.create(
                model=openai_cred.model_name,  # type: ignore[union-attr]
                input=[{"role": "user", "content": full_prompt}],
            )
            text_out = ""
            for item in oai_resp.output:
                if item.type == "message":
                    for c in item.content:
                        if c.type == "output_text":
                            text_out = c.text
                            break
            pred_raw = _json.loads(text_out)
            prose_schema = PreferenceProfileProseSchema.model_validate(pred_raw)
            usage_obj = oai_resp.usage
        except Exception as exc:
            log.error(
                AI_GENERATION_ERROR,
                user_id=user_id,
                rec_type=_REC_TYPE_PREFERENCE_PROSE,
                error_class=type(exc).__name__,
                error_status="pydantic_error",
            )
            _write_recommendation_row(
                db,
                user_id=user_id,
                rec_type=_REC_TYPE_PREFERENCE_PROSE,
                input_signature=current_sig,
                response_json={},
                cred=cred,  # type: ignore[arg-type]
                tool_version=tool_version,
                usage=usage_obj,
                web_search_count=0,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                generated_by="scheduler",
                error_status="pydantic_error",
            )
            return "try_again", None

    duration_ms = int((time.monotonic() - start_ts) * 1000)
    rec_row = _write_recommendation_row(
        db,
        user_id=user_id,
        rec_type=_REC_TYPE_PREFERENCE_PROSE,
        input_signature=current_sig,
        response_json=prose_schema.model_dump(),
        cred=cred,  # type: ignore[arg-type]
        tool_version=tool_version,
        usage=usage_obj,
        web_search_count=0,
        duration_ms=duration_ms,
        generated_by="scheduler",
    )

    log.info(
        AI_GENERATION_SUCCESS,
        user_id=user_id,
        rec_type=_REC_TYPE_PREFERENCE_PROSE,
        provider=cred.provider,  # type: ignore[union-attr]
        model=cred.model_name,  # type: ignore[union-attr]
        duration_ms=duration_ms,
    )

    return "generated", rec_row


def _build_preference_prose_prompt(
    profile: dict[str, list[Any]],
    flavor_descriptors: list[Any],
) -> str:
    """Build the preference profile prose prompt from analytics helper outputs.

    Serializes get_preference_profile dimensions and get_flavor_descriptors to JSON
    so the LLM has structured input to reason over (D-10).
    """
    import json as _json

    profile_data = {
        dim: [
            {
                "label": row.label,
                "avg_rating": float(row.avg_rating),
                "session_count": row.session_count,
            }
            for row in rows
        ]
        for dim, rows in profile.items()
    }
    flavor_data = [
        {
            "name": row.name,
            "session_count": row.session_count,
        }
        for row in flavor_descriptors
    ]

    return (
        "Write an in-depth preference profile for this coffee drinker. "
        "Cross-cut flavor, process, origin, varietal, and rating data. "
        "Be specific — cite actual labels, numbers, and patterns from the data. "
        "Do not pad with generic advice.\n\n"
        f"Preference dimensions:\n{_json.dumps(profile_data, indent=2)}\n\n"
        f"Top flavor descriptors (from 4.0+ rated sessions):\n"
        f"{_json.dumps(flavor_data, indent=2)}"
    )
