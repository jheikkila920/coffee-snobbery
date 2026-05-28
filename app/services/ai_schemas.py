"""Per-flow Pydantic v2 response schemas for AI-generated recommendations.

Each schema is the LLM-output contract for one recommendation flow:

- ``CoffeeRecSchema``              — AI-03 / AI-09: next-coffee-to-buy recommendation
- ``SweetSpotsProseSchema``        — HOME-06 / AI-10: dial-in sweet-spot analysis prose
- ``EquipmentRecSchema``           — AI-08: weakest-link equipment recommendation
- ``PasteRankSchema``              — AI-09: rank currently-open bags
- ``CoffeeResearchSchema``         — AIX-01: free-text coffee research result (Phase 19)
- ``RatingPredictionSchema``       — D-02: per-user predicted rating range (Phase 19)
- ``BrewParameterChangeSchema``    — AIX-12: one parameter change suggestion (Phase 19)
- ``BrewImproveSchema``            — AIX-12: full improve-brew coaching result (Phase 19)
- ``PreferenceProfileProseSchema`` — AIX-09: in-depth preference prose (Phase 19)

All top-level schemas carry ``summary_prose: str`` (AI-18, D-04) and
``ConfigDict(extra="forbid")`` (T-07-02 prompt-injection defence: injected
fields raise ``ValidationError`` rather than silently reaching the DB).

The generated ``model_json_schema()`` dict is passed directly as the Anthropic
tool ``input_schema`` — ``Field(description=...)`` annotations guide the model
to produce well-formed output without leaking server implementation details.

Note on ``url_verified``: this field is intentionally ABSENT from all schemas.
Buy-URL verification is server-side (``_verify_buy_url`` in ai_service.py)
and written to the ``AIRecommendation.url_verified`` DB column — it is NOT
LLM output and must not appear in the structured-output schema (any LLM value
would be untrusted and ignored).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Nested sub-schemas (no extra="forbid" needed — they live inside top-levels)
# ---------------------------------------------------------------------------


class RecipeSuggestionSchema(BaseModel):
    """A recipe the AI recommends for the suggested coffee.

    D-11 (Phase 19): ``no_match`` removed; ``ratio``, ``temp_c``, and
    ``grind_hint`` are now required so every recommendation carries concrete
    brew parameters. Constructing this schema with ``no_match=True`` raises
    ``ValidationError`` because ``extra="forbid"`` rejects unknown fields.
    """

    model_config = ConfigDict(extra="forbid")

    recipe_id: int | None = Field(
        None, description="ID of an existing recipe in the user's catalog, or null if none match"
    )
    recipe_name: str | None = Field(
        None, description="Name of the matched recipe, or null if none match"
    )
    summary: str = Field(description="Why this recipe suits the recommended coffee (1-2 sentences)")
    ratio: str = Field(description="e.g. '1:15' coffee-to-water ratio")
    temp_c: int = Field(description="Brew water temperature in Celsius")
    grind_hint: str = Field(description="e.g. 'medium-fine, ~22 clicks Encore'")


class AltBrewerSchema(BaseModel):
    """An alternative brewer that would unlock the coffee's full potential."""

    model_config = ConfigDict(extra="forbid")

    brewer_name: str = Field(
        description="Name of the alternative brewer (e.g., 'Chemex', 'AeroPress')"
    )
    rating_delta: float = Field(
        description=(
            "Expected improvement in enjoyment on the 0-5 scale "
            "(positive = better, negative = worse)"
        )
    )
    summary: str = Field(description="Why this brewer would suit the coffee (1-2 sentences)")


class RankedCoffeeItem(BaseModel):
    """One entry in the paste-rank ordered list."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(description="Position in the ranking, starting at 1")
    name: str = Field(description="Coffee name as it appears in the user's catalog")
    reasoning: str = Field(description="Why this coffee is ranked here (1-2 sentences)")


# ---------------------------------------------------------------------------
# Top-level per-flow response schemas
# ---------------------------------------------------------------------------


class CoffeeRecSchema(BaseModel):
    """AI-03 / AI-09 next-coffee-to-buy recommendation.

    The LLM populates this via the ``structure_output`` tool call. The
    citation projector (``_project_tool_use_input``) extracts only this
    tool's ``input`` block; ``extra="forbid"`` then rejects any field
    injected by adversarial web-search results (T-07-02).
    """

    model_config = ConfigDict(extra="forbid")

    coffee_name: str = Field(description="Full name of the recommended coffee")
    roaster_name: str = Field(description="Name of the roaster who produces this coffee")
    origin: str = Field(description="Country or region of origin (e.g., 'Ethiopia', 'Colombia')")
    process: str = Field(description="Processing method (e.g., 'Natural', 'Washed', 'Honey')")
    roast_level: str = Field(description="Roast level (e.g., 'Light', 'Medium', 'Dark')")
    buy_url: str | None = Field(
        None,
        description=(
            "Direct purchase URL for this exact coffee (https:// only). "
            "Null if a verified URL cannot be found."
        ),
    )
    search_tier: str = Field(
        description=(
            "Which search strategy found this coffee: "
            "'primary' (exact flavor match), "
            "'broadened' (relaxed constraints), or "
            "'characteristics_only' (flavor profile without session history)"
        )
    )
    summary_prose: str = Field(
        description=(
            "2-3 sentence narrative explaining why this coffee suits the user's taste "
            "profile, written for display on the home page (AI-18, D-04)"
        )
    )
    recipe_suggestion: RecipeSuggestionSchema | None = Field(
        None,
        description="Optional recipe pairing from the user's existing catalog",
    )
    alt_brewer: AltBrewerSchema | None = Field(
        None,
        description=(
            "Optional alternative brewer recommendation, "
            "if the user's current brewer limits the coffee"
        ),
    )


class SweetSpotsProseSchema(BaseModel):
    """HOME-06 / AI-10 dial-in sweet-spot analysis.

    Single prose field: the LLM synthesises the user's best brews into
    actionable grind/ratio/temperature guidance.
    """

    model_config = ConfigDict(extra="forbid")

    summary_prose: str = Field(
        description=(
            "3-5 sentences identifying the user's brew sweet spots "
            "(grind, ratio, temperature, timing) with specific numbers where the data supports it. "
            "Written for display on the home page (AI-18)."
        )
    )


class EquipmentRecSchema(BaseModel):
    """AI-08 weakest-link equipment recommendation."""

    model_config = ConfigDict(extra="forbid")

    weakest_link: str | None = Field(
        None,
        description=(
            "The single piece of equipment most limiting the user's brew quality "
            "(e.g., 'Baratza Encore grinder'). Null if the setup is well-matched."
        ),
    )
    recommendation: str | None = Field(
        None,
        description=(
            "Specific upgrade recommendation with rationale (1-2 sentences). "
            "Null when no upgrade is warranted."
        ),
    )
    summary_prose: str = Field(
        description=(
            "2-3 sentences assessing the user's current equipment setup and "
            "any recommended upgrade, written for display on the home page (AI-18)."
        )
    )


class PasteRankSchema(BaseModel):
    """AI-09 rank currently-open bags by predicted enjoyment.

    Limited to 3 entries (``max_length=3``) to keep the home page focused
    and avoid overwhelming the LLM with a long ranking task.
    """

    model_config = ConfigDict(extra="forbid")

    ranked: list[RankedCoffeeItem] = Field(
        max_length=3,
        description=(
            "Ordered list of up to 3 open bags ranked by predicted enjoyment, "
            "best first. Fewer than 3 is fine when fewer bags are open."
        ),
    )
    summary_prose: str = Field(
        description=(
            "1-2 sentences explaining the ranking logic and recommending "
            "which bag to reach for today (AI-18)."
        )
    )


# ---------------------------------------------------------------------------
# Phase 19 schemas — research, prediction, improve-brew, preference prose
# ---------------------------------------------------------------------------


class CoffeeResearchSchema(BaseModel):
    """AIX-01: Free-text coffee research result with cited sources.

    World-view schema: describes a coffee as the LLM understands it from
    web search + training data.  Stored in ``ai_coffee_research_cache``
    (shared, not per-user).  ``extra="forbid"`` blocks prompt-injection
    (T-19-01).
    """

    model_config = ConfigDict(extra="forbid")

    coffee_name: str = Field(description="Full name of the coffee as found/confirmed")
    roaster_name: str | None = Field(None, description="Name of the roaster, or null if unknown")
    origin: str | None = Field(None, description="Country or region of origin, or null if unknown")
    process: str | None = Field(
        None, description="Processing method (e.g. 'Washed', 'Natural'), or null if unknown"
    )
    roast_level: str | None = Field(
        None, description="Roast level (e.g. 'Light', 'Medium'), or null if unknown"
    )
    tasting_notes: list[str] = Field(
        default_factory=list, description="List of tasting note descriptors"
    )
    buy_url: str | None = Field(None, description="https:// only; null if not found")
    sources: list[str] = Field(
        default_factory=list, description="Cited source URLs from web search"
    )
    summary_prose: str = Field(
        description="2-3 sentence narrative for the result card (AI-18 convention)"
    )


class RatingPredictionSchema(BaseModel):
    """D-02: Per-user predicted rating as a range + confidence + reasoning.

    Never a single number — the range + confidence label communicates
    uncertainty without false precision.  ``extra="forbid"`` blocks
    prompt-injection (T-19-01).
    """

    model_config = ConfigDict(extra="forbid")

    predicted_low: float = Field(
        ge=0, le=5, description="Lower bound of predicted rating, 0.25-step increments"
    )
    predicted_high: float = Field(
        ge=0, le=5, description="Upper bound of predicted rating, 0.25-step increments"
    )
    confidence: Literal["Low", "Medium", "High"] = Field(
        description="Confidence level based on session history depth"
    )
    reasoning: str = Field(description="1-2 sentence 'Why:' block for the result card")


class BrewParameterChangeSchema(BaseModel):
    """AIX-12: One brew parameter change suggestion.

    ``parameter`` is a Literal to prevent the LLM from inventing parameter
    names not handled by the UI.  ``extra="forbid"`` blocks prompt-injection
    (T-19-01).
    """

    model_config = ConfigDict(extra="forbid")

    parameter: Literal["grind", "ratio", "temp_c", "brewer", "recipe"] = Field(
        description="Which brew parameter to change"
    )
    suggested_value: str = Field(
        description="The suggested new value (e.g. '2 clicks coarser', '1:16', '93°C')"
    )
    rationale: str = Field(description="1-2 sentence rationale for the change")


class BrewImproveSchema(BaseModel):
    """AIX-12: Full improve-brew coaching result for one brew session.

    ``next_try`` is an ordered list so the UI can show the highest-priority
    change first.  ``extra="forbid"`` blocks prompt-injection (T-19-01).
    """

    model_config = ConfigDict(extra="forbid")

    summary_prose: str = Field(description="2-3 sentence coaching narrative (AI-18 convention)")
    unchanged_parameters: list[str] = Field(
        description="Dial settings the user already has dialed in (LLM sanity check)"
    )
    next_try: list[BrewParameterChangeSchema] = Field(
        description="Ordered list of parameter changes to attempt next, highest priority first"
    )


class PreferenceProfileProseSchema(BaseModel):
    """AIX-09: In-depth preference profile as AI prose.

    Replaces the structured 'Top Flavor Descriptors' card (D-10).
    Single-field schema; stored as ``recommendation_type='preference_profile_prose'``
    in ``ai_recommendations``.  ``extra="forbid"`` blocks prompt-injection (T-19-01).
    """

    model_config = ConfigDict(extra="forbid")

    summary_prose: str = Field(
        description=(
            "In-depth AI prose cross-cutting flavor × process × origin × varietal × rating. "
            "Written for the /ai page preference card (AI-18 convention)."
        )
    )


__all__ = [
    "AltBrewerSchema",
    "BrewImproveSchema",
    "BrewParameterChangeSchema",
    "CoffeeRecSchema",
    "CoffeeResearchSchema",
    "EquipmentRecSchema",
    "PasteRankSchema",
    "PreferenceProfileProseSchema",
    "RankedCoffeeItem",
    "RatingPredictionSchema",
    "RecipeSuggestionSchema",
    "SweetSpotsProseSchema",
]
