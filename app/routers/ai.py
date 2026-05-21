"""AI router — state-changing AI routes + wishlist CRUD (Phase 7, Plan 07-05).

Routes:
  POST /ai/refresh                   — manual AI refresh (throttle + in-flight 429)
  POST /ai/equipment                 — on-demand equipment recommendation
  POST /ai/paste-rank                — paste-and-rank coffees (text/URLs)
  POST /ai/wishlist/add              — add wishlist entry (user-scoped)
  POST /ai/wishlist/{entry_id}/purchase — mark purchased (IDOR: 404 cross-user)
  POST /ai/wishlist/{entry_id}/remove   — remove entry (IDOR: 404 cross-user)

Security invariants:
  - All routes gated by ``Depends(require_user)``; ``user_id`` read ONLY from
    ``request.state.user.id`` — never from form/query params (T-07-12).
  - No route is CSRF-exempt; every POST passes through ``CSRFFormFieldShim``
    + ``CSRFMiddleware`` (T-07-11).
  - Wishlist purchase/remove return 404 on cross-user entry_id (T-07-05 IDOR).
  - ``/ai/refresh`` enforces a 5-minute per-user throttle (429, AI-14, COST-2)
    and the in-memory lock guard (429, AI-13).
  - Background task ``_verify_and_persist_url`` verifies buy_url after a coffee
    row is generated (AI-05), using the SSRF-hardened ``_verify_buy_url``.
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.events import AI_THROTTLE_BLOCK, AI_URL_VERIFY
from app.models.user import User
from app.services import ai_service
from app.services import wishlist as wishlist_service

log = structlog.get_logger(__name__)

# Throttle window in seconds (5 minutes, AI-14 / COST-2)
_THROTTLE_WINDOW_SECS = 300

router = APIRouter(prefix="/ai")

# ---------------------------------------------------------------------------
# Inline please-wait HTML (used when fragments/home/ai_rec_in_flight.html
# is not yet present — 07-06 will add the real template).
# ---------------------------------------------------------------------------
_PLEASE_WAIT_HTML = (
    '<div id="ai-rec-hero" class="text-center py-8 text-gray-500">'
    "Generating your recommendation&hellip; refresh in a moment."
    "</div>"
)


# ---------------------------------------------------------------------------
# Background task: verify buy_url and update url_verified (AI-05)
# ---------------------------------------------------------------------------


async def _verify_and_persist_url(user_id: int) -> None:
    """Verify the buy_url on the latest coffee rec row and persist url_verified.

    Opens a fresh SessionLocal (not the request session — this runs after the
    response has been sent), loads the latest coffee row, calls _verify_buy_url
    on its buy_url, updates url_verified, and commits. SSRF mitigations are
    entirely inside ``ai_service._verify_buy_url`` (T-07-01).

    Guards:
    - No latest row → skip.
    - No buy_url in response_json → skip (url_verified stays None).
    """
    from app.db import SessionLocal

    with SessionLocal() as db:
        row = ai_service.get_latest_recommendation(db, user_id=user_id, rec_type="coffee")
        if row is None:
            return

        resp_json = row.response_json or {}
        buy_url = resp_json.get("buy_url") or ""
        roaster_name = resp_json.get("roaster_name", "")
        coffee_name = resp_json.get("coffee_name", "")

        if not buy_url:
            # No buy_url — leave url_verified as None
            return

        verified = await ai_service._verify_buy_url(buy_url, roaster_name, coffee_name)
        row.url_verified = verified
        db.commit()

        log.info(
            AI_URL_VERIFY,
            user_id=user_id,
            rec_id=row.id,
            verified=verified,
        )


# ---------------------------------------------------------------------------
# POST /ai/refresh — manual refresh (throttle + in-flight + background verify)
# ---------------------------------------------------------------------------


@router.post("/refresh", response_class=HTMLResponse)
async def post_ai_refresh(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Trigger a manual AI coffee-rec refresh for the authenticated user.

    Throttle check (AI-14, COST-2):
      If the user refreshed within the last 5 minutes, return 429 with
      ``HX-Retarget="#ai-rec-hero"`` and ``HX-Reswap="outerHTML"`` so HTMX
      swaps in the please-wait fragment without a full page reload.

    In-flight check (AI-13):
      If a generation run is already active for this user, return the same 429.

    On success:
      Schedule ``_verify_and_persist_url`` as a background task and return 204
      + ``HX-Trigger: aiRecUpdated`` so the home-card poll re-fetches the hero.
    """
    user_id = user.id
    now = time.monotonic()

    # --- Throttle check (AI-14) -----------------------------------------------
    ai_service._evict_stale_throttle(now=now, window_secs=_THROTTLE_WINDOW_SECS * 2)
    last_refresh = ai_service._THROTTLE.get(user_id)
    if last_refresh is not None:
        elapsed = now - last_refresh
        if elapsed < _THROTTLE_WINDOW_SECS:
            seconds_remaining = int(_THROTTLE_WINDOW_SECS - elapsed)
            log.info(
                AI_THROTTLE_BLOCK,
                user_id=user_id,
                seconds_remaining=seconds_remaining,
            )
            return Response(
                content=_PLEASE_WAIT_HTML,
                status_code=429,
                media_type="text/html",
                headers={
                    "HX-Retarget": "#ai-rec-hero",
                    "HX-Reswap": "outerHTML",
                },
            )

    # --- In-flight check (AI-13) ----------------------------------------------
    if ai_service.in_flight(user_id):
        log.info("ai.refresh.in_flight", user_id=user_id)
        return Response(
            content=_PLEASE_WAIT_HTML,
            status_code=429,
            media_type="text/html",
            headers={
                "HX-Retarget": "#ai-rec-hero",
                "HX-Reswap": "outerHTML",
            },
        )

    # --- Set throttle entry + run regenerate -----------------------------------
    ai_service._THROTTLE[user_id] = now

    status = await ai_service.regenerate(user_id, "manual_refresh", db=db, force=True)

    if status == "generated":
        # Schedule background URL verification (AI-05)
        background_tasks.add_task(_verify_and_persist_url, user_id)
        return Response(
            status_code=204,
            headers={"HX-Trigger": "aiRecUpdated"},
        )
    elif status in ("locked",):
        # Another process grabbed the advisory lock between our check and attempt
        return Response(
            content=_PLEASE_WAIT_HTML,
            status_code=429,
            media_type="text/html",
            headers={
                "HX-Retarget": "#ai-rec-hero",
                "HX-Reswap": "outerHTML",
            },
        )
    elif status == "not_configured":
        # No AI provider configured — render a minimal message
        return Response(
            content=(
                '<div id="ai-rec-hero" class="text-center py-8 text-amber-600">'
                "AI provider not configured. Contact your admin."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )
    else:
        # "try_again" / "skipped" / "error" / unexpected
        return Response(
            content=(
                '<div id="ai-rec-hero" class="text-center py-8 text-gray-500">'
                "Could not generate a recommendation right now. Try again later."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )


# ---------------------------------------------------------------------------
# POST /ai/equipment — on-demand equipment recommendation
# ---------------------------------------------------------------------------


@router.post("/equipment", response_class=HTMLResponse)
async def post_ai_equipment(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Generate an on-demand equipment recommendation for the authenticated user.

    Calls ``generate_equipment_rec`` (D-05 on-demand, not in the nightly bundle).
    Returns a 200 with the equipment result region (or a state message).
    """
    user_id = user.id
    status, _row = await ai_service.generate_equipment_rec(
        user_id, "manual_refresh", db=db
    )

    if status == "generated":
        # 07-06 will add the real equipment fragment; return minimal inline here
        rec_json = _row.response_json if _row else {}
        weakest = rec_json.get("weakest_link") or "No specific recommendation"
        return Response(
            content=(
                f'<div id="ai-equipment-result" class="text-gray-700">'
                f"{weakest}"
                f"</div>"
            ),
            status_code=200,
            media_type="text/html",
        )
    elif status == "not_configured":
        return Response(
            content=(
                '<div id="ai-equipment-result" class="text-amber-600">'
                "AI provider not configured."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )
    else:
        return Response(
            content=(
                '<div id="ai-equipment-result" class="text-gray-500">'
                "Could not generate equipment recommendation. Try again later."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )


# ---------------------------------------------------------------------------
# POST /ai/paste-rank — paste-and-rank coffees
# ---------------------------------------------------------------------------


@router.post("/paste-rank", response_class=HTMLResponse)
async def post_ai_paste_rank(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Rank pasted coffee text/URLs for the authenticated user (D-07/D-08).

    Reads ``input_text`` from the form (strips X-CSRF-Token per brew.py line 962).
    Calls ``rank_pasted_coffees`` and returns the top-3 results or a state message.
    07-07 owns the full paste_rank page; this handler returns results inline.
    """
    form = await request.form()
    input_text = str(form.get("input_text") or "").strip()

    user_id = user.id
    status, result = await ai_service.rank_pasted_coffees(
        user_id, "manual_refresh", db=db, raw_input=input_text
    )

    if status == "generated" and result is not None:
        ranked = result.ranked_coffees or []
        items_html = "".join(
            f"<li class='py-1'>{item.coffee_name} — {item.summary}</li>"
            for item in ranked[:3]
        )
        return Response(
            content=(
                f'<div id="paste-rank-results"><ol class="list-decimal pl-5">'
                f"{items_html}"
                f"</ol></div>"
            ),
            status_code=200,
            media_type="text/html",
        )
    elif status == "not_configured":
        return Response(
            content=(
                '<div id="paste-rank-results" class="text-amber-600">'
                "AI provider not configured."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )
    else:
        return Response(
            content=(
                '<div id="paste-rank-results" class="text-gray-500">'
                "Could not rank coffees right now. Try again later."
                "</div>"
            ),
            status_code=200,
            media_type="text/html",
        )


# ---------------------------------------------------------------------------
# POST /ai/wishlist/add — add wishlist entry (user-scoped)
# ---------------------------------------------------------------------------


@router.post("/wishlist/add")
async def post_wishlist_add(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Add a wishlist entry for the authenticated user (D-09).

    Reads coffee_name / roaster_name / source_url from the form.
    user_id is ALWAYS server-set from request.state.user.id (T-07-12).
    Returns 204 + HX-Trigger: wishlistUpdated.
    """
    form = await request.form()
    coffee_name = str(form.get("coffee_name") or "").strip()
    roaster_name = str(form.get("roaster_name") or "").strip() or None
    source_url = str(form.get("source_url") or "").strip() or None

    wishlist_service.add_to_wishlist(
        db,
        by_user_id=user.id,
        coffee_name=coffee_name,
        roaster_name=roaster_name,
        source_url=source_url,
        source="ai_recommendation",
    )

    return Response(
        status_code=204,
        headers={"HX-Trigger": "wishlistUpdated"},
    )


# ---------------------------------------------------------------------------
# POST /ai/wishlist/{entry_id}/purchase — mark purchased (IDOR: 404 cross-user)
# ---------------------------------------------------------------------------


@router.post("/wishlist/{entry_id}/purchase")
def post_wishlist_purchase(
    entry_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Mark a wishlist entry as purchased.

    Returns 404 when ``entry_id`` does not belong to the authenticated user
    (T-07-05 IDOR — existence non-leak, same sentinel pattern as brew.py).
    """
    result = wishlist_service.mark_purchased(db, entry_id=entry_id, by_user_id=user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        status_code=204,
        headers={"HX-Trigger": "wishlistUpdated"},
    )


# ---------------------------------------------------------------------------
# POST /ai/wishlist/{entry_id}/remove — remove entry (IDOR: 404 cross-user)
# ---------------------------------------------------------------------------


@router.post("/wishlist/{entry_id}/remove")
def post_wishlist_remove(
    entry_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Delete a wishlist entry.

    Returns 404 when ``entry_id`` does not belong to the authenticated user
    (T-07-05 IDOR — existence non-leak, same sentinel pattern as brew.py).
    """
    removed = wishlist_service.remove_entry(db, entry_id=entry_id, by_user_id=user.id)
    if not removed:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        status_code=204,
        headers={"HX-Trigger": "wishlistUpdated"},
    )


__all__ = ["router"]
