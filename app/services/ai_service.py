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
import json  # noqa: F401 — used in Task 2 OpenAI fallback flow
import time  # noqa: F401 — used in Task 2/3 for duration_ms calculation
from typing import Any

import anthropic
import httpx
import openai
import structlog
from pydantic import ValidationError  # noqa: F401 — used in Task 2 projection/validation
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
from app.models.equipment import Equipment
from app.models.recipe import Recipe
from app.services import analytics as analytics_service  # noqa: F401 — used in Task 3
from app.services import credentials as credentials_service
from app.services import settings as settings_service  # noqa: F401 — used in Task 2
from app.services.ai_schemas import (
    AltBrewerSchema,
    CoffeeRecSchema,  # noqa: F401 — used in Task 2
    EquipmentRecSchema,  # noqa: F401
    PasteRankSchema,  # noqa: F401
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

        if r.status_code not in (200, 206):
            return False

        body = r.text.lower()
        return roaster_name.lower() in body or coffee_name.lower() in body

    except (httpx.TimeoutException, httpx.RequestError):
        return False


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
            # Case-insensitive style matching (Coffee columns are nullable)
            func.lower(Coffee.origin) == func.lower(origin) if origin else text("TRUE"),
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
        return RecipeSuggestionSchema(
            recipe_id=None,
            recipe_name=None,
            summary="No matching recipe yet — try the recipe builder.",
            no_match=True,
        )
    return RecipeSuggestionSchema(
        recipe_id=row.recipe_id,
        recipe_name=row.recipe_name,
        summary=(
            f"Based on your rated sessions, {row.recipe_name!r} averaged "
            f"{float(row.avg_rating):.2f}/5 on this bean style."
        ),
        no_match=False,
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
            func.lower(Coffee.origin) == func.lower(origin) if origin else text("TRUE"),
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
