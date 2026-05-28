"""AI research service — cache lookup, SSE two-phase generator, prediction tying.

This module is the core of the v1.2 research differentiator.  It reuses every
security-critical primitive from ai_service.py verbatim:

  _project_tool_use_input     — citation projector (T-07-02 prompt-injection)
  _get_lock / _try_advisory_lock — double-charge prevention (T-19-10)
  _build_anthropic_client / _build_openai_client — key handling (T-07-03)
  _write_recommendation_row   — telemetry write (AI-02 / AIX-13)
  _verify_buy_url             — SSRF-hardened URL verifier (T-07-01 / D-14)

Threat model:
  T-19-07 — quota bypass: count keyed to user_id only (DB-backed, never form/query)
  T-19-08 — prompt injection: _project_tool_use_input + extra=forbid
  T-19-09 — SSE error events emit short user-facing string only; real exception logged
  T-19-10 — EventSource reconnect double-charge: _try_advisory_lock + _get_lock
  T-19-11 — SSRF on buy_url: _verify_buy_url run as BackgroundTask post-stream

# p95 target: <= 30s
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
import structlog
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.ai_coffee_research_cache import AICoffeeResearchCache
from app.models.ai_rating_prediction import AIRatingPrediction
from app.services import ai_quota, ai_service
from app.services import analytics as analytics_service
from app.services import credentials as credentials_service
from app.services.ai_schemas import CoffeeResearchSchema, RatingPredictionSchema
from app.services.ai_service import (
    SYSTEM_PROMPT_VOICE,
    _get_lock,
    _project_tool_use_input,
    _try_advisory_lock,
)

try:
    from sse_starlette.sse import ServerSentEvent
except ImportError:  # pragma: no cover
    # Fallback for environments where sse-starlette is not installed
    class ServerSentEvent:  # type: ignore[no-redef]
        def __init__(self, data: str, event: str | None = None):
            self.data = data
            self.event = event


log = structlog.get_logger(__name__)

# Research TTL constants
_CACHE_TTL_DAYS = 30
_PREDICTION_TTL_DAYS = 7

# Settings keys for the tool version
_TOOL_VERSION_ANTHROPIC = "web_search_20250305"

# Rec type constant
_REC_TYPE_RESEARCH = "coffee_research"


# ---------------------------------------------------------------------------
# Cache key normalization (AIX-04 / D-06)
# ---------------------------------------------------------------------------


def normalize_cache_key(coffee_name: str, roaster_name: str | None) -> str:
    """Derive the canonical cache key for a (coffee_name, roaster_name) pair.

    Key format: ``lower(coffee_name).strip() + '|' + lower(roaster_name or '').strip()``

    This derivation MUST be identical in the write and read paths (D-06).
    An absent or empty roaster_name produces an empty string after the pipe.
    """
    return f"{coffee_name.lower().strip()}|{(roaster_name or '').lower().strip()}"


# ---------------------------------------------------------------------------
# Cache read with lazy TTL eviction (Pattern 4)
# ---------------------------------------------------------------------------


def get_cached_research(db: Session, cache_key: str) -> AICoffeeResearchCache | None:
    """Read a cache row, evicting expired rows lazily at read time (D-06).

    Deletes any expired row for *cache_key* first, then returns the live row
    or None.  No background sweep required at household scale.
    """
    now = datetime.now(UTC)
    # Lazy eviction: delete expired row for this key (D-06 Pattern 4)
    db.execute(
        delete(AICoffeeResearchCache).where(
            AICoffeeResearchCache.cache_key == cache_key,
            AICoffeeResearchCache.expires_at <= now,
        )
    )
    return db.scalar(
        select(AICoffeeResearchCache).where(
            AICoffeeResearchCache.cache_key == cache_key,
        )
    )


# ---------------------------------------------------------------------------
# Cache write helper
# ---------------------------------------------------------------------------


def _write_cache_row(
    db: Session,
    *,
    cache_key: str,
    response_json: dict[str, Any],
    cited_sources: list[str],
) -> AICoffeeResearchCache:
    """Insert or replace the cache row (PK = cache_key, TTL 30 days)."""
    expires_at = datetime.now(UTC) + timedelta(days=_CACHE_TTL_DAYS)
    # Use ON CONFLICT (cache_key) DO UPDATE for atomic upsert
    stmt = (
        pg_insert(AICoffeeResearchCache)
        .values(
            cache_key=cache_key,
            response_json=response_json,
            cited_sources=cited_sources,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=["cache_key"],
            set_=dict(
                response_json=response_json,
                cited_sources=cited_sources,
                expires_at=expires_at,
            ),
        )
    )
    db.execute(stmt)
    db.flush()
    return db.scalar(
        select(AICoffeeResearchCache).where(
            AICoffeeResearchCache.cache_key == cache_key,
        )
    )


# ---------------------------------------------------------------------------
# Telemetry write (AIX-13 / D-15)
# ---------------------------------------------------------------------------


def _write_research_telemetry(
    db: Session,
    *,
    user_id: int,
    cache_key: str,
    cred: credentials_service.ProviderCredential,
    tool_version: str | None,
    usage: Any,
    duration_ms: int,
    error_status: str | None = None,
) -> None:
    """Write one ai_recommendations row with rec_type='coffee_research' (AIX-13).

    Uses ai_service._write_recommendation_row verbatim to keep telemetry
    consistent across all AI flows (AI-02).
    """
    ai_service._write_recommendation_row(
        db,
        user_id=user_id,
        rec_type=_REC_TYPE_RESEARCH,
        # Cache-keyed signature — not the brew-session signature
        input_signature=cache_key,
        response_json={},  # prose lives in cache row; telemetry row is cost-only
        cred=cred,
        tool_version=tool_version,
        usage=usage,
        web_search_count=getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0)
        if usage is not None
        else 0,
        duration_ms=duration_ms,
        generated_by="user_request",
        error_status=error_status,
    )


# ---------------------------------------------------------------------------
# Signature-versioned prediction (Pattern 5 / D-07 / AIX-02)
# ---------------------------------------------------------------------------


def get_or_refresh_prediction(
    db: Session,
    *,
    user_id: int,
    cache_key: str,
    cache_row: AICoffeeResearchCache,
    current_signature: str,
    cred: credentials_service.ProviderCredential,
) -> AIRatingPrediction | None:
    """Return a fresh or refreshed per-user rating prediction.

    Regenerates without re-firing the web search when:
    - No row exists for (user_id, research_cache_key)
    - expires_at is past (7-day TTL)
    - input_signature has changed (user logged new rated sessions)

    The prediction call is a cheap single structured call with no web_search
    tool — it uses the cached coffee facts for context (RESEARCH Pattern 5).
    """
    now = datetime.now(UTC)
    existing = db.scalar(
        select(AIRatingPrediction).where(
            AIRatingPrediction.user_id == user_id,
            AIRatingPrediction.research_cache_key == cache_key,
        )
    )

    # Check if prediction is fresh
    if (
        existing is not None
        and existing.expires_at > now
        and existing.input_signature == current_signature
    ):
        return existing

    # Regenerate: cheap call — no web_search, uses cache_row coffee facts
    raw = cache_row.response_json
    coffee_name = raw.get("coffee_name", "this coffee")
    roaster_name = raw.get("roaster_name", "")
    origin = raw.get("origin", "")
    tasting_notes = raw.get("tasting_notes", [])
    summary_prose = raw.get("summary_prose", "")

    # Build user preference context for the prediction
    profile = analytics_service.get_preference_profile(db, user_id)
    top_origin = (profile.get("origin", [{}]) or [{}])[0]
    top_origin_label = getattr(top_origin, "label", "") if hasattr(top_origin, "label") else ""

    prompt = (
        f"Coffee: {coffee_name}"
        + (f" by {roaster_name}" if roaster_name else "")
        + (f", {origin}" if origin else "")
        + f"\nFlavor profile: {', '.join(tasting_notes)}"
        + f"\nSummary: {summary_prose}\n\n"
        f"The user's top preferred origin: {top_origin_label}\n"
        "Based on the coffee profile and the user's preferences, predict a rating range. "
        "Return predicted_low, predicted_high (both 0-5), confidence (Low/Medium/High), "
        "and a 1-2 sentence reasoning."
    )

    try:
        if cred.provider == "anthropic":
            client = ai_service._build_anthropic_client(cred)
            response = client.messages.create(
                model=cred.model_name,
                max_tokens=512,
                system=SYSTEM_PROMPT_VOICE,
                messages=[{"role": "user", "content": prompt}],
                tools=[
                    {
                        "name": "structure_output",
                        "description": "Return the rating prediction",
                        "input_schema": RatingPredictionSchema.model_json_schema(),
                    }
                ],  # type: ignore[arg-type]
            )
            pred_raw = _project_tool_use_input(response.content, "structure_output")
        else:
            # OpenAI fallback — non-streaming structured call
            import json

            oai_client = ai_service._build_openai_client(cred)
            schema_hint = json.dumps(
                RatingPredictionSchema.model_json_schema(), separators=(",", ":")
            )
            full_prompt = f"{prompt}\n\nRespond with JSON matching this schema:\n{schema_hint}"
            oai_resp = oai_client.responses.create(
                model=cred.model_name,
                input=[{"role": "user", "content": full_prompt}],
            )
            text_out = ""
            for item in oai_resp.output:
                if item.type == "message":
                    for c in item.content:
                        if c.type == "output_text":
                            text_out = c.text
                            break
            pred_raw = json.loads(text_out)

        pred_schema = RatingPredictionSchema.model_validate(pred_raw)
    except Exception as exc:
        log.warning(
            "ai_research.prediction_failed",
            user_id=user_id,
            cache_key=cache_key,
            error=type(exc).__name__,
        )
        return existing  # return stale if exists, else None

    # Upsert the prediction row (UNIQUE upsert on user_id + research_cache_key)
    expires_at = datetime.now(UTC) + timedelta(days=_PREDICTION_TTL_DAYS)
    stmt = (
        pg_insert(AIRatingPrediction)
        .values(
            user_id=user_id,
            research_cache_key=cache_key,
            predicted_low=pred_schema.predicted_low,
            predicted_high=pred_schema.predicted_high,
            confidence=pred_schema.confidence,
            reasoning=pred_schema.reasoning,
            input_signature=current_signature,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            constraint="uq_ai_rating_pred_user_cache_key",
            set_=dict(
                predicted_low=pred_schema.predicted_low,
                predicted_high=pred_schema.predicted_high,
                confidence=pred_schema.confidence,
                reasoning=pred_schema.reasoning,
                input_signature=current_signature,
                expires_at=expires_at,
            ),
        )
    )
    db.execute(stmt)
    db.flush()
    return db.scalar(
        select(AIRatingPrediction).where(
            AIRatingPrediction.user_id == user_id,
            AIRatingPrediction.research_cache_key == cache_key,
        )
    )


# ---------------------------------------------------------------------------
# Two-phase SSE generator (AIX-07 / D-16 / Pattern 1)
# ---------------------------------------------------------------------------


# p95 target: <= 30s
async def generate_coffee_research(
    db: Session,
    *,
    user_id: int,
    coffee_name: str,
    roaster_name: str | None,
    current_signature: str,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Two-phase SSE generator for coffee research (D-16 / AIX-07).

    Gate ordering (run BEFORE initiating EventSourceResponse):
      1. Cold-start gate (AIX-03)
      2. Quota check (AIX-05 / D-08)
      3. Cache hit → emit event:complete instantly; no LLM; no quota decrement

    Cache miss path:
      4. Advisory lock (T-19-10 / Pitfall 2)
      5. Phase 1: stream prose text deltas as event:message
      6. Phase 2: get_final_message() → _project_tool_use_input → CoffeeResearchSchema
      7. On ValidationError → event:error; return
      8. Write cache row, prediction row, telemetry row
      9. Render research_result.html fragment → event:complete

    OpenAI fallback uses a non-streaming structured call (RESEARCH Open Q#1).
    _verify_buy_url is scheduled as a BackgroundTask by the caller — NOT called here (T-19-11).
    Error events emit a short user-facing message only (T-19-09).
    """
    # (1) Cold-start gate (AIX-03)
    gate = analytics_service.get_cold_start_counts(db, user_id)
    if not gate["gate_open"]:
        log.info(
            "ai_research.cold_start_gate_closed",
            user_id=user_id,
            sessions=gate["sessions"],
            notes=gate["distinct_notes"],
        )
        yield ServerSentEvent(
            data="Please log at least 3 brews and 5 flavor notes before using research.",
            event="error",
        )
        return

    # (2) Quota check (AIX-05 / D-08) — checked before LLM, not inside generator
    remaining = ai_quota.remaining(db, user_id, _REC_TYPE_RESEARCH)
    if remaining <= 0:
        reset_time = ai_quota.get_quota_reset_time(db, user_id, _REC_TYPE_RESEARCH)
        msg = "Daily research limit reached."
        if reset_time:
            delta = reset_time - datetime.now(UTC)
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            msg += f" Resets in {hours}h {mins}m."
        yield ServerSentEvent(data=msg, event="error")
        return

    # (3) Resolve credential
    cred = credentials_service.get_provider_credential(
        db, "anthropic"
    ) or credentials_service.get_provider_credential(db, "openai")
    if cred is None:
        yield ServerSentEvent(data="AI provider not configured.", event="error")
        return

    # (4) Cache check — hit path: instant return, no LLM, no quota decrement
    cache_key = normalize_cache_key(coffee_name, roaster_name)
    cache_row = get_cached_research(db, cache_key)
    if cache_row is not None:
        log.info("ai_research.cache_hit", user_id=user_id, cache_key=cache_key)
        # Tie prediction for this user
        prediction = get_or_refresh_prediction(
            db,
            user_id=user_id,
            cache_key=cache_key,
            cache_row=cache_row,
            current_signature=current_signature,
            cred=cred,
        )
        html = _render_research_result(
            cache_row=cache_row,
            prediction=prediction,
            cached=True,
        )
        yield ServerSentEvent(data=html, event="complete")
        return

    # (5) Advisory lock (T-19-10) — acquire before starting stream
    lock = _get_lock(user_id, _REC_TYPE_RESEARCH)
    if lock.locked():
        yield ServerSentEvent(data="A research request is already in progress.", event="error")
        return

    async with lock:
        if not _try_advisory_lock(db, user_id, _REC_TYPE_RESEARCH):
            yield ServerSentEvent(data="A research request is already in progress.", event="error")
            return

        # Re-check cache under lock (another concurrent request may have written it)
        cache_row = get_cached_research(db, cache_key)
        if cache_row is not None:
            prediction = get_or_refresh_prediction(
                db,
                user_id=user_id,
                cache_key=cache_key,
                cache_row=cache_row,
                current_signature=current_signature,
                cred=cred,
            )
            html = _render_research_result(cache_row=cache_row, prediction=prediction, cached=True)
            yield ServerSentEvent(data=html, event="complete")
            return

        # (6) Build prompt
        prompt = _build_research_prompt(coffee_name, roaster_name)
        tool_version = _TOOL_VERSION_ANTHROPIC

        start_ts = time.monotonic()
        usage_obj: Any = None
        result_schema: CoffeeResearchSchema | None = None

        if cred.provider == "anthropic":
            # Phase 1 + 2: two-phase streaming (RESEARCH Pattern 1)
            async_client = anthropic.AsyncAnthropic(api_key=cred.key, max_retries=1)

            tools: list[dict[str, Any]] = [
                {
                    "type": tool_version,
                    "name": "web_search",
                    "max_uses": 3,
                },
                {
                    "name": "structure_output",
                    "description": "Return the structured coffee research result",
                    "input_schema": CoffeeResearchSchema.model_json_schema(),
                },
            ]

            try:
                async with async_client.messages.stream(
                    model=cred.model_name,
                    max_tokens=2000,
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
                    result_schema = CoffeeResearchSchema.model_validate(raw)
                except (ValueError, ValidationError) as exc:
                    log.warning(
                        "ai_research.validation_failed",
                        user_id=user_id,
                        error=type(exc).__name__,
                    )
                    # T-19-09: short user-facing message only; real exc already logged
                    yield ServerSentEvent(
                        data="Could not parse research result. Please try again.",
                        event="error",
                    )
                    duration_ms = int((time.monotonic() - start_ts) * 1000)
                    _write_research_telemetry(
                        db,
                        user_id=user_id,
                        cache_key=cache_key,
                        cred=cred,
                        tool_version=tool_version,
                        usage=usage_obj,
                        duration_ms=duration_ms,
                        error_status="pydantic_error",
                    )
                    db.commit()
                    return

            except anthropic.APIError as exc:
                log.error(
                    "ai_research.anthropic_error",
                    user_id=user_id,
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

            try:
                oai_client = ai_service._build_openai_client(cred)
                schema_hint = _json.dumps(
                    CoffeeResearchSchema.model_json_schema(), separators=(",", ":")
                )
                full_prompt = (
                    f"{prompt}\n\nRespond with a JSON object matching this schema exactly:"
                    f"\n{schema_hint}"
                )
                oai_response = oai_client.responses.create(
                    model=cred.model_name,
                    input=[{"role": "user", "content": full_prompt}],
                    tools=[{"type": "web_search_preview"}],  # type: ignore[list-item]
                )
                text_out = ""
                for item in oai_response.output:
                    if item.type == "message":
                        for c in item.content:
                            if c.type == "output_text":
                                text_out = c.text
                                break
                raw = _json.loads(text_out)
                result_schema = CoffeeResearchSchema.model_validate(raw)
                usage_obj = oai_response.usage
                tool_version = "web_search_preview"
                # Emit the summary_prose as a single message event for UX
                yield ServerSentEvent(data=result_schema.summary_prose, event="message")

            except Exception as exc:
                log.error(
                    "ai_research.openai_error",
                    user_id=user_id,
                    error=type(exc).__name__,
                )
                yield ServerSentEvent(
                    data="AI provider error. Please try again later.",
                    event="error",
                )
                return

        duration_ms = int((time.monotonic() - start_ts) * 1000)

        # (7) Write cache row
        response_dict = result_schema.model_dump()
        cited_sources = result_schema.sources or []
        new_cache_row = _write_cache_row(
            db,
            cache_key=cache_key,
            response_json=response_dict,
            cited_sources=cited_sources,
        )

        # (8) Write telemetry row (AIX-13 / D-15)
        _write_research_telemetry(
            db,
            user_id=user_id,
            cache_key=cache_key,
            cred=cred,
            tool_version=tool_version,
            usage=usage_obj,
            duration_ms=duration_ms,
        )

        # (9) Tie/refresh prediction
        prediction = get_or_refresh_prediction(
            db,
            user_id=user_id,
            cache_key=cache_key,
            cache_row=new_cache_row,
            current_signature=current_signature,
            cred=cred,
        )

        db.commit()

        # (10) Render result fragment and emit event:complete
        html = _render_research_result(
            cache_row=new_cache_row,
            prediction=prediction,
            cached=False,
        )
        yield ServerSentEvent(data=html, event="complete")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_research_prompt(coffee_name: str, roaster_name: str | None) -> str:
    """Build the research prompt for the given coffee."""
    roaster_clause = f" by {roaster_name}" if roaster_name else ""
    return (
        f"Research the specialty coffee '{coffee_name}'{roaster_clause}. "
        "Find: origin country, process method, roast level, tasting notes, "
        "a buy URL for the current product page (https:// only; null if not available), "
        "and cited source URLs. Write a 2-3 sentence summary_prose for a pour-over enthusiast. "
        "Only recommend coffees that are currently for sale at the roaster's website. "
        "Avoid archived, sold-out, or discontinued lots."
    )


# ---------------------------------------------------------------------------
# Result renderer (stub — routes/templates added in 19-04)
# ---------------------------------------------------------------------------


def _render_research_result(
    *,
    cache_row: AICoffeeResearchCache,
    prediction: AIRatingPrediction | None,
    cached: bool,
) -> str:
    """Render the research result card HTML fragment.

    Returns a minimal HTML string when the templates are not yet wired
    (Phase 19-04 adds the full template). This stub is sufficient for
    the service-layer tests and SSE contract.
    """
    raw = cache_row.response_json
    coffee_name = raw.get("coffee_name", "")
    cached_badge = ' <span class="text-xs text-muted">· cached</span>' if cached else ""
    pred_text = ""
    if prediction is not None:
        pred_text = (
            f'<p class="text-sm">Predicted: {prediction.predicted_low}'
            f"–{prediction.predicted_high}/5 ({prediction.confidence})</p>"
        )
    return f'<div id="research-result"><h3>{coffee_name}{cached_badge}</h3>{pred_text}</div>'
