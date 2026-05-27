"""Home page router — analytics shell + always-on + aggregate fragment endpoints (Phase 6).

Replaces the Phase 0 placeholder ``@app.get("/")`` in ``app/main.py``.

Routes:
  GET /                              — full home shell (eager: cold-start gate,
                                       recent brews, unrated coffees)
  GET /home/cards/recent-brews       — partial refresh for the recent-brews card
  GET /home/cards/unrated-coffees    — partial refresh + lazy-load for unrated coffees
  GET /home/cards/top-coffees        — aggregate card (HOME-01)
  GET /home/cards/preference-profile — aggregate card (HOME-02)
  GET /home/cards/flavor-descriptors — aggregate card (HOME-03)
  GET /home/cards/sweet-spots        — aggregate card (HOME-05)

Every handler is gated by ``Depends(require_user)`` (T-06-04 / T-06-05).
``user_id`` is ALWAYS read from ``request.state.user.id`` — never a query param
(T-06-05 IDOR defense). ``FragmentCacheHeadersMiddleware`` applies
``Cache-Control: no-store`` + ``Vary: HX-Request`` automatically to fragment
responses — no per-route header configuration needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.brew_session import BrewSession
from app.models.user import User
from app.services import ai_service, analytics
from app.services import credentials as credentials_service
from app.templates_setup import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home_shell(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the analytics home shell (Phase 6).

    Calls all three eager analytics functions (cold-start gate, recent brews,
    unrated coffees) before rendering.  The ``gate`` dict drives the cold-start
    branch in the template; recent brews + unrated coffees always render (D-01).

    The five aggregate-card sections are lazy-loaded via HTMX in the template
    (staggered 100–500ms, HOME-09); their fragment endpoints live in Plan 06-03.
    """
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


@router.get("/home/cards/recent-brews", response_class=HTMLResponse)
def card_recent_brews(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the recent-brews card.

    PURPOSE — not dead code: the shell renders recent brews via an eager
    ``{% include %}`` on initial page load (HOME-07, D-01).  This endpoint
    exists for *partial refresh* — an ``hx-get="/home/cards/recent-brews"``
    swap of just the recent-brews section after a new session is logged, so
    the list updates without a full page reload.  Both the eager include and
    this fragment endpoint render the same template, intentionally.

    ``FragmentCacheHeadersMiddleware`` adds ``no-store`` + ``Vary: HX-Request``
    automatically on ``HX-Request: true`` responses.
    """
    recent_brews = analytics.get_recent_brews(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/recent_brews.html",
        context={"recent_brews": recent_brews},
    )


@router.get("/home/cards/unrated-coffees", response_class=HTMLResponse)
def card_unrated_coffees(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the unrated-coffees card (HOME-08).

    The shell lazy-loads this via ``hx-trigger="load delay:150ms"`` on first
    paint; this endpoint also supports partial refresh after a session is logged
    against a previously-unrated coffee.
    """
    unrated_coffees = analytics.get_unrated_coffees(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/unrated_coffees.html",
        context={"unrated_coffees": unrated_coffees},
    )


def _has_rated_sessions(db: Session, user_id: int) -> bool:
    """Return True if the user has at least one rated brew session.

    Used by rating-dependent card handlers to detect the all-unrated case (D-05):
    a single DB scalar rather than iterating over query results.
    """
    count = (
        db.scalar(
            select(func.count(BrewSession.id)).where(
                BrewSession.user_id == user_id,
                BrewSession.rating.is_not(None),
            )
        )
        or 0
    )
    return count > 0


@router.get("/home/cards/top-coffees", response_class=HTMLResponse)
def card_top_coffees(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the top-coffees card (HOME-01).

    Rating-dependent: passes ``all_unrated`` to the template (D-05).
    ``FragmentCacheHeadersMiddleware`` adds ``no-store`` + ``Vary: HX-Request``
    automatically on ``HX-Request: true`` responses.
    """
    rows = analytics.get_top_coffees(db, user.id)
    all_unrated = not rows and not _has_rated_sessions(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/top_coffees.html",
        context={"rows": rows, "all_unrated": all_unrated},
    )


@router.get("/home/cards/preference-profile", response_class=HTMLResponse)
def card_preference_profile(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the preference-profile card (HOME-02).

    Rating-dependent: passes ``all_unrated`` to the template (D-05).
    The ``profile`` dict has keys origin/process/roaster/roast_level.
    """
    profile = analytics.get_preference_profile(db, user.id)
    profile_empty = not any(profile.values())
    all_unrated = profile_empty and not _has_rated_sessions(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/preference_profile.html",
        context={"profile": profile, "all_unrated": all_unrated},
    )


@router.get("/home/cards/flavor-descriptors", response_class=HTMLResponse)
def card_flavor_descriptors(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the top-flavor-descriptors card (HOME-03).

    Rating-dependent: passes ``all_unrated`` to the template (D-05).
    """
    rows = analytics.get_flavor_descriptors(db, user.id)
    all_unrated = not rows and not _has_rated_sessions(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/flavor_descriptors.html",
        context={"rows": rows, "all_unrated": all_unrated},
    )


@router.get("/home/cards/sweet-spots", response_class=HTMLResponse)
def card_sweet_spots(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Fragment endpoint for the sweet-spots card (HOME-05).

    Rating-dependent: passes ``all_unrated`` to the template (D-05).
    Also passes ``sweet_spots_prose`` from the latest sweet_spots AI row (HOME-06).
    """
    rows = analytics.get_sweet_spots(db, user.id)
    all_unrated = not rows and not _has_rated_sessions(db, user.id)
    ss_row = ai_service.get_latest_recommendation(db, user_id=user.id, rec_type="sweet_spots")
    sweet_spots_prose = ss_row.response_json.get("summary_prose") if ss_row else None
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/sweet_spots.html",
        context={
            "rows": rows,
            "all_unrated": all_unrated,
            "sweet_spots_prose": sweet_spots_prose,
        },
    )


@router.get("/home/cards/ai-recommendation", response_class=HTMLResponse)
def card_ai_recommendation(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """AI hero card fragment — polling endpoint (AI-14).

    Returns one of five fragments based on current state, evaluated in order:
    1. cold_start  — gate not cleared (< 3 sessions or < 5 flavor notes, AI-11)
    2. not_configured — no provider credential enabled (AI-16)
    3. in_flight   — a regeneration run holds the in-memory lock (HTMX polls)
    4. hero card   — latest successful coffee row present (stale badge if sig changed)
    5. in_flight   — gate open + configured but no row yet (keep polling)

    ``FragmentCacheHeadersMiddleware`` applies ``no-store`` + ``Vary: HX-Request``
    automatically on ``HX-Request: true`` responses.
    All user_id reads come from ``request.state.user.id`` (T-07-12 IDOR defense).
    """
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

    # AI-14: in-flight lock held → show spinner and poll
    if ai_service.in_flight(user.id):
        return templates.TemplateResponse(
            request=request,
            name="fragments/home/ai_rec_in_flight.html",
            context={},
        )

    # Load the latest coffee recommendation row
    rec = ai_service.get_latest_recommendation(db, user_id=user.id, rec_type="coffee")
    if rec is None:
        # Gate open + configured + no row yet → keep polling (triggers scheduler or
        # manual refresh to generate the first recommendation)
        return templates.TemplateResponse(
            request=request,
            name="fragments/home/ai_rec_in_flight.html",
            context={},
        )

    # AI-04: try_again state when the stored row is an error (error_status set).
    # get_latest_recommendation filters error_status IS NULL, so rec is always
    # a valid row here.  A separate check for a try_again sentinel is not needed;
    # the scheduler writes a row with error_status when generation fails — those
    # are filtered out, leaving rec=None which is handled above.  The try_again
    # fragment is returned by the scheduler path via a future extension point.
    prose = rec.response_json or {}
    stale = ai_service.is_stale(db, user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/ai_rec_hero.html",
        context={"rec": rec, "prose": prose, "stale": stale, "user": user},
    )
