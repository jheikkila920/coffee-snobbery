"""AI router — state-changing AI routes + wishlist CRUD + Phase 19 flows.

Routes (Phase 7):
  GET  /ai/paste-rank                — dedicated paste-and-rank page (07-07)
  GET  /ai/wishlist                  — minimal wishlist view (07-07)
  POST /ai/refresh                   — manual AI refresh (throttle + in-flight 429)
  POST /ai/equipment                 — on-demand equipment recommendation
  POST /ai/paste-rank                — paste-and-rank coffees (text/URLs)
  POST /ai/wishlist/add              — add wishlist entry (user-scoped)
  POST /ai/wishlist/{entry_id}/purchase — mark purchased (IDOR: 404 cross-user)
  POST /ai/wishlist/{entry_id}/remove   — remove entry (IDOR: 404 cross-user)

Routes (Phase 19 — research/improve/charts):
  POST /ai/research                  — SSE coffee research stream (AIX-01/07)
  GET  /ai/research/quota            — quota counter fragment (AIX-05/D-09)
  POST /ai/improve-brew/{session_id} — SSE improve-brew stream (AIX-12/D-12)
  GET  /ai/coach                     — session-picker fragment (D-12)
  GET  /ai/charts/rating-over-time   — per-user rating trend JSON (VIZ-01)
  GET  /ai/charts/flavor-distribution — per-user flavor counts JSON (VIZ-01)

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
  - POST /ai/research: cold-start gate + per-user quota check BEFORE SSE stream
    starts (T-19-16); 429 + HX-Retarget on exhaustion (D-09).
  - POST /ai/improve-brew/{session_id}: session loaded by_user_id → 404 on
    cross-user (T-19-17 IDOR, not 403 — existence non-leak).
  - GET /ai/charts/*: both query helpers are per-user scoped (T-19-18).
  - SSE responses carry X-Accel-Buffering: no for NPM buffering defense (T-19-20).
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.events import AI_THROTTLE_BLOCK, AI_URL_VERIFY
from app.models.user import User
from app.services import ai_quota, ai_research, ai_service, analytics, charts
from app.services import brew_sessions as brew_sessions_service
from app.services import credentials as credentials_service
from app.services import wishlist as wishlist_service
from app.templates_setup import templates

try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:  # pragma: no cover
    EventSourceResponse = None  # type: ignore[assignment,misc]

log = structlog.get_logger(__name__)

# Throttle window in seconds (5 minutes, AI-14 / COST-2)
_THROTTLE_WINDOW_SECS = 300

router = APIRouter(prefix="/ai")

# ---------------------------------------------------------------------------
# GET /ai — page shell (Phase 17, IA-02 / IA-03 / AIX-08 / D-13..D-16 + D-20)
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def get_ai_page(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the /ai page shell — three-branch composition keyed on the
    cold-start gate state and resolvable AI-key presence.

    - Below gate                → cold-start meter (D-14).
    - Above gate, no key, admin → AIX-08 admin callout with Go to Admin (D-15).
    - Above gate, no key, !admin → D-16 social-action callout (no admin link).
    - Above gate, key present   → consolidated AI surface (hero + cards + tools
                                  + Phase 19 research stub, D-13).

    The DIST-07 banner from plan 17-03 is included at the top of the page;
    it self-gates on ``is_admin AND not ai_key_present`` (D-20 coexistence).
    """
    gate = analytics.get_cold_start_counts(db, user.id)
    anthropic_cred = credentials_service.get_provider_credential(db, "anthropic")
    openai_cred = credentials_service.get_provider_credential(db, "openai")
    ai_key_present = anthropic_cred is not None or openai_cred is not None

    # Research quota context — passed through to research_form.html include (D-09).
    # Only computed when gate is open + key present (avoid extra queries when not needed).
    remaining = 0
    quota_cap = 20
    reset_in = None
    if gate["gate_open"] and ai_key_present:
        remaining = ai_quota.remaining(db, user.id, "coffee_research")
        quota_cap = ai_quota.get_quota_cap("coffee_research")
        if remaining == 0:
            reset_time = ai_quota.get_quota_reset_time(db, user.id, "coffee_research")
            reset_in = ai_quota.format_reset(reset_time)

    return templates.TemplateResponse(
        request=request,
        name="pages/ai.html",
        context={
            "gate": gate,
            "ai_key_present": ai_key_present,
            "user": user,
            "remaining": remaining,
            "quota_cap": quota_cap,
            "reset_in": reset_in,
        },
    )


# ---------------------------------------------------------------------------
# GET /ai/paste-rank — dedicated "Rank these for me" page (07-07, D-07/D-08)
# ---------------------------------------------------------------------------


@router.get("/paste-rank", response_class=HTMLResponse)
def get_paste_rank_page(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Render the paste-and-rank page (empty form, no results).

    POST /ai/paste-rank (below) populates the results area via HTMX or returns
    the full page with results for non-HTMX clients.
    """
    return templates.TemplateResponse(
        request=request,
        name="pages/paste_rank.html",
        context={"status": None, "results": None},
    )


# ---------------------------------------------------------------------------
# GET /ai/wishlist — minimal wishlist view (07-07, D-09)
# ---------------------------------------------------------------------------


@router.get("/wishlist", response_class=HTMLResponse)
def get_wishlist_page(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the wishlist page for the authenticated user.

    Lists entries newest-first, each with mark-purchased + remove actions.
    Scoped exclusively to request.state.user.id (T-07-05 IDOR).
    """
    entries = wishlist_service.list_wishlist(db, by_user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="pages/wishlist.html",
        context={"entries": entries},
    )


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
    status, _row = await ai_service.generate_equipment_rec(user_id, "manual_refresh", db=db)

    ctx: dict = {"status": status, "row": _row}
    if _row is not None and _row.response_json:
        from app.services.ai_schemas import EquipmentRecSchema

        try:
            ctx["rec"] = EquipmentRecSchema.model_validate(_row.response_json)
        except Exception:  # noqa: BLE001
            ctx["rec"] = None
    else:
        ctx["rec"] = None
    return templates.TemplateResponse(
        request=request,
        name="fragments/home/equipment_rec.html",
        context=ctx,
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

    is_htmx = request.headers.get("HX-Request") == "true"
    ctx: dict = {"status": status, "results": result}
    if is_htmx:
        return templates.TemplateResponse(
            request=request,
            name="fragments/ai/paste_rank_results.html",
            context=ctx,
        )
    # Non-HTMX: full page with results inlined
    return templates.TemplateResponse(
        request=request,
        name="pages/paste_rank.html",
        context=ctx,
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

    # CR-05: a wishlist entry is meaningless without a name.
    if not coffee_name:
        raise HTTPException(status_code=422, detail="coffee_name is required")
    # CR-01: only store https URLs. The template renders source_url as an
    # <a href>, and Jinja autoescaping does NOT neutralise dangerous schemes
    # (javascript:, data:). Match the https-only posture of the buy-URL verifier.
    if source_url is not None and not source_url.startswith("https://"):
        source_url = None

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


# ---------------------------------------------------------------------------
# Phase 19 research routes (AIX-01/03/05/07/D-09/D-16)
# ---------------------------------------------------------------------------

# HTML fragment for quota-exhausted inline error (D-09)
_RESEARCH_QUOTA_EXHAUSTED_HTML = (
    '<div id="research-card" class="text-center py-4 text-amber-600">'
    "Daily research limit reached. Try again when your quota resets."
    "</div>"
)


@router.post("/research", response_class=HTMLResponse)
async def post_ai_research(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream a coffee research result via SSE (AIX-01/03/05/07/D-16).

    Gate ordering (all checked BEFORE starting EventSourceResponse):
      1. Cold-start gate closed → 403 (AIX-03)
      2. Quota exhausted → 429 + HX-Retarget="#research-card" (AIX-05/D-09)

    Cache hit → instant EventSourceResponse with event:complete (no quota decrement, AIX-04).
    Cache miss → EventSourceResponse wrapping generate_coffee_research generator.
    BackgroundTask: _verify_and_persist_url for the buy_url SSRF check (T-19-11).

    user_id ONLY from request.state.user.id (T-19-16 — never from form/query params).
    CSRF flows through CSRFMiddleware (T-07-11).
    X-Accel-Buffering: no for NPM defense-in-depth (T-19-20).
    """
    if EventSourceResponse is None:
        return Response(
            content="SSE not available — sse-starlette not installed.",
            status_code=503,
            media_type="text/plain",
        )

    user_id = user.id
    form = await request.form()
    coffee_name = str(form.get("coffee_name") or "").strip()
    roaster_name = str(form.get("roaster_name") or "").strip() or None

    if not coffee_name:
        raise HTTPException(status_code=422, detail="coffee_name is required")

    # (1) Cold-start gate (AIX-03)
    gate = analytics.get_cold_start_counts(db, user_id)
    if not gate["gate_open"]:
        log.info("ai.research.gate_closed", user_id=user_id)
        return Response(
            content=(
                '<div id="research-card" class="text-center py-4 text-gray-500">'
                "Please log more brews and flavor notes before using research."
                "</div>"
            ),
            status_code=403,
            media_type="text/html",
        )

    # (2) Quota check (AIX-05/D-09) — before SSE starts
    remaining = ai_quota.remaining(db, user_id, "coffee_research")
    if remaining <= 0:
        reset_time = ai_quota.get_quota_reset_time(db, user_id, "coffee_research")
        reset_str = ai_quota.format_reset(reset_time)
        if reset_str:
            content = (
                f'<div id="research-card" class="text-center py-4 text-amber-600">'
                f"Daily research limit reached. Resets in {reset_str}."
                f"</div>"
            )
        else:
            content = _RESEARCH_QUOTA_EXHAUSTED_HTML
        log.info("ai.research.quota_exhausted", user_id=user_id)
        return Response(
            content=content,
            status_code=429,
            media_type="text/html",
            headers={
                "HX-Retarget": "#research-card",
                "HX-Reswap": "outerHTML",
            },
        )

    # (3) Get the user's current input signature for prediction versioning
    current_signature = analytics.compute_input_signature(db, user_id)

    # Schedule buy_url background verification after stream (T-19-11)
    background_tasks.add_task(_verify_and_persist_url, user_id)

    # Return EventSourceResponse wrapping the generator (cache hit or miss handled inside)
    generator = ai_research.generate_coffee_research(
        db,
        user_id=user_id,
        coffee_name=coffee_name,
        roaster_name=roaster_name,
        current_signature=current_signature,
    )
    return EventSourceResponse(
        generator,
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/research/quota", response_class=HTMLResponse)
def get_research_quota(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Return the research quota counter fragment (D-09).

    Renders either:
    - ``"{remaining}/{cap} research calls remaining today"`` when quota > 0
    - ``"Resets in Hh Mm"`` when quota is exhausted
    """
    user_id = user.id
    remaining = ai_quota.remaining(db, user_id, "coffee_research")
    cap = ai_quota.get_quota_cap("coffee_research")

    if remaining > 0:
        content = (
            f'<span id="research-quota" class="text-sm text-gray-500">'
            f"{remaining}/{cap} research calls remaining today"
            f"</span>"
        )
    else:
        reset_time = ai_quota.get_quota_reset_time(db, user_id, "coffee_research")
        reset_str = ai_quota.format_reset(reset_time)
        if reset_str:
            content = (
                f'<span id="research-quota" class="text-sm text-amber-600">'
                f"Resets in {reset_str}"
                f"</span>"
            )
        else:
            content = (
                '<span id="research-quota" class="text-sm text-gray-500">'
                "0/20 research calls remaining today"
                "</span>"
            )
    return Response(content=content, status_code=200, media_type="text/html")


# ---------------------------------------------------------------------------
# Phase 19 improve-brew routes (AIX-12/D-12/D-16)
# ---------------------------------------------------------------------------


@router.post("/improve-brew/{session_id}", response_class=HTMLResponse)
async def post_ai_improve_brew(
    session_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream an improve-brew coaching result via SSE (AIX-12/D-12/D-16).

    Gate ordering:
      1. Session load by_user_id → 404 on cross-user IDOR (T-19-17)
      2. Quota check (improve_brew bucket) → 429 on exhaustion
      3. EventSourceResponse(generate_brew_improvement(...))

    user_id ONLY from request.state.user.id (T-19-16).
    CSRF flows through CSRFMiddleware (T-07-11).
    X-Accel-Buffering: no for NPM buffering defense (T-19-20).
    """
    if EventSourceResponse is None:
        return Response(
            content="SSE not available — sse-starlette not installed.",
            status_code=503,
            media_type="text/plain",
        )

    user_id = user.id

    # (1) Session load — user-scoped (IDOR: T-19-17; 404 non-leak like edit_brew_form)
    session = brew_sessions_service.get_brew_session(db, session_id=session_id, by_user_id=user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Not found")

    # (2) Quota check (improve_brew bucket — separate from research, D-08)
    remaining = ai_quota.remaining(db, user_id, "brew_improvement")
    if remaining <= 0:
        reset_time = ai_quota.get_quota_reset_time(db, user_id, "brew_improvement")
        reset_str = ai_quota.format_reset(reset_time)
        if reset_str:
            content = (
                f'<div id="improve-result" class="text-center py-4 text-amber-600">'
                f"Daily brew-improvement limit reached. Resets in {reset_str}."
                f"</div>"
            )
        else:
            content = (
                '<div id="improve-result" class="text-center py-4 text-amber-600">'
                "Daily brew-improvement limit reached. Try again tomorrow."
                "</div>"
            )
        log.info("ai.improve_brew.quota_exhausted", user_id=user_id, session_id=session_id)
        return Response(
            content=content,
            status_code=429,
            media_type="text/html",
            headers={
                "HX-Retarget": "#improve-result",
                "HX-Reswap": "outerHTML",
            },
        )

    # (3) SSE stream — improve_brew bucket; user_id scoped
    generator = ai_service.generate_brew_improvement(
        db,
        user_id=user_id,
        session_id=session_id,
    )
    return EventSourceResponse(
        generator,
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/coach", response_class=HTMLResponse)
def get_ai_coach(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Return the session-picker fragment for the 'Coach a brew' link (D-12).

    Lists the user's last ~20 brew sessions. Each entry links to the brew edit
    page where the improve-brew result card auto-triggers on load.
    Only the requesting user's sessions are returned (T-19-17 IDOR).
    """
    user_id = user.id
    sessions = brew_sessions_service.list_brew_sessions(db, by_user_id=user_id)[:20]

    # Load coffee names for the picker display
    # Sessions already ordered newest-first from list_brew_sessions
    return templates.TemplateResponse(
        request=request,
        name="fragments/ai/coach_brew_picker.html",
        context={"sessions": sessions},
    )


# ---------------------------------------------------------------------------
# Phase 19 chart JSON routes (VIZ-01/D-17)
# ---------------------------------------------------------------------------


@router.get("/charts/rating-over-time")
def get_chart_rating_over_time(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> JSONResponse:
    """Return per-user rating-over-time JSON for Chart.js (VIZ-01/D-17).

    Response: [{date: "YYYY-MM-DD", rating: float}, ...] ordered by date.
    UNION of brew_sessions + cafe_logs, last 90 days.
    Per-user scoped on user_id (T-19-18).
    """
    data = charts.rating_over_time(db, user.id)
    return JSONResponse(content=data)


@router.get("/charts/flavor-distribution")
def get_chart_flavor_distribution(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> JSONResponse:
    """Return per-user flavor distribution JSON for Chart.js (VIZ-01/D-17).

    Response: [{descriptor: str, count: int}, ...] top-15 by count.
    UNION of brew + cafe flavor note ids, NO rating floor.
    Per-user scoped on user_id (T-19-18).
    """
    data = charts.flavor_distribution(db, user.id)
    return JSONResponse(content=data)


__all__ = ["router"]
