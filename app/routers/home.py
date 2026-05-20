"""Home page router — analytics shell + always-on fragment endpoints (Phase 6).

Replaces the Phase 0 placeholder ``@app.get("/")`` in ``app/main.py``.

Routes:
  GET /                        — full home shell (eager: cold-start gate,
                                 recent brews, unrated coffees)
  GET /home/cards/recent-brews — partial refresh endpoint for the recent-brews
                                 card (also the surface the shell includes eagerly)
  GET /home/cards/unrated-coffees — partial refresh + lazy-load for the
                                    unrated-coffees card

Every handler is gated by ``Depends(require_user)`` (T-06-04 / T-06-05).
``user_id`` is ALWAYS read from ``request.state.user.id`` — never a query param
(T-06-05 IDOR defense). ``FragmentCacheHeadersMiddleware`` applies
``Cache-Control: no-store`` + ``Vary: HX-Request`` automatically to fragment
responses — no per-route header configuration needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import analytics
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
