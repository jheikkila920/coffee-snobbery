"""GBM (Guided Brew Mode) page router — BREW-12/13 (Phase 11 / Plan 04).

Single authenticated route:

    GET /brew/guided?recipe_id=N[&coffee_id=M]

Renders the full-screen ``pages/brew_guided.html`` page with the recipe steps
JSON embedded in a data attribute. The page covers the bottom nav (z-50 over
z-40 nav) and is driven entirely by the ``guidedBrewMode`` Alpine component.

Auth: ``Depends(require_user)`` — anonymous callers get 401 (T-11-12).
404: raised when the recipe_id does not exist.
Zero-steps: the route still 200s; the template renders the disabled launch
state with a "Recipe has no steps." message (UX-04).

Registration note: this router MUST be included in ``app.main`` BEFORE
``brew_router`` so the static segment ``/brew/guided`` is matched before
the dynamic ``/brew/{session_id}`` capture.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.services import coffees as coffees_service
from app.services import recipes as recipes_service
from app.templates_setup import templates

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/brew")


@router.get("/guided", response_class=HTMLResponse)
def brew_guided(
    request: Request,
    recipe_id: int,
    coffee_id: int | None = None,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the full-screen Guided Brew Mode page.

    Loads the recipe (404 if not found) and optionally the coffee for display.
    A recipe with zero steps renders the disabled launch state in the template;
    the route itself still returns 200 in that case.
    """
    recipe = recipes_service.get_recipe(db, recipe_id=recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    coffee = None
    if coffee_id is not None:
        coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)

    log.info(
        "brew_guided.render",
        user_id=user.id,
        recipe_id=recipe_id,
        coffee_id=coffee_id,
        step_count=len(recipe.steps or []),
    )

    return templates.TemplateResponse(
        request=request,
        name="pages/brew_guided.html",
        context={
            "recipe": recipe,
            "coffee": coffee,
        },
    )
