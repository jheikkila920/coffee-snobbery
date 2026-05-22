"""Admin credential vault router — ADMIN-02 / SEC-6.

Implements the API credential set/update, enable-toggle, and masked-display
handlers for both Anthropic and OpenAI providers.

SEC-6 invariant: The decrypted API key must NEVER leave handler scope. Only
``last_four`` is passed to template context. The ``ProviderCredential.key``
field stays as a local variable in the POST(set) handler and is garbage-
collected on return. No logging of the key or ciphertext (CLAUDE.md).

Router auto-includes into ``app.routers.admin`` via the Plan 01 import guard
— this file is all that needs to be created; do NOT edit ``__init__.py``.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events
from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.api_credential import ApiCredential
from app.models.user import User
from app.services import credentials as cred_service
from app.templates_setup import templates

log = structlog.get_logger(__name__)

router = APIRouter()

_VALID_PROVIDERS = {"anthropic", "openai"}


def _get_display_rows(db: Session) -> list[dict]:
    """Build display-safe context rows for BOTH providers.

    Uses a DIRECT select(ApiCredential) — never get_provider_credential(),
    which (a) decrypts the key (SEC-6 risk) and (b) returns None for
    disabled/keyless rows, causing them to silently vanish from the list.
    """
    rows = db.execute(select(ApiCredential)).scalars().all()
    # Index by provider so both show up even if DB rows are missing
    by_provider = {r.provider: r for r in rows}
    result = []
    for provider in ("anthropic", "openai"):
        row = by_provider.get(provider)
        result.append(
            {
                "provider": provider,
                "last_four": row.last_four or "" if row else "",
                "model_name": row.model_name or "" if row else "",
                "is_enabled": row.is_enabled if row else False,
            }
        )
    return result


# ---------------------------------------------------------------------------
# GET /admin/credentials — masked list display
# ---------------------------------------------------------------------------


@router.get("/credentials", response_class=HTMLResponse)
def list_credentials(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Masked credentials list. HTMX → fragment(s); full GET → page template.

    SEC-6: context contains ONLY last_four, model_name, is_enabled, provider.
    Never the ProviderCredential dataclass or any key string.
    """
    display_rows = _get_display_rows(db)
    if request.headers.get("HX-Request") == "true":
        # Return each provider row as a fragment sequence
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_credential_row.html",
            context={"rows": display_rows, **display_rows[0]} if display_rows else {},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_credentials.html",
        context={"rows": display_rows},
    )


# ---------------------------------------------------------------------------
# POST /admin/credentials/{provider} — set/update encrypted key
# ---------------------------------------------------------------------------


@router.post("/credentials/{provider}", response_class=HTMLResponse)
async def set_credential(
    provider: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Encrypt + store the API key; return masked row fragment.

    SEC-6:
    - api_key is read into a local variable only.
    - It is NEVER added to template context.
    - set_provider_credential() handles encryption; cred_service never returns
      the plaintext key.
    - The write-back display query uses a direct ApiCredential select (no decrypt).
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}

    api_key = raw.get("api_key", "").strip()  # stays local — never in context
    model_name = raw.get("model_name", "").strip() or None  # None = preserve existing

    # WR-06: blank api_key means "leave key unchanged" — do not encrypt "".
    # If no key and no model_name were submitted, there is nothing to write.
    if not api_key and model_name is None:
        # Nothing to update; re-render the current row as-is.
        row = db.execute(
            select(ApiCredential).where(ApiCredential.provider == provider)
        ).scalar_one_or_none()
        ctx = {
            "provider": provider,
            "last_four": row.last_four or "" if row else "",
            "model_name": row.model_name or "" if row else "",
            "is_enabled": row.is_enabled if row else False,
        }
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_credential_row.html",
            context=ctx,
        )

    # WR-04: pass key=None when blank so set_provider_credential skips the
    # key write (preserves ciphertext + is_enabled; only updates model_name).
    cred_service.set_provider_credential(
        db,
        provider,  # type: ignore[arg-type]
        key=api_key or None,
        model_name=model_name,
        by_user_id=user.id,
        # is_enabled not passed: service defaults True on new key write,
        # preserves existing flag on model-only update (WR-04 fix).
    )

    # Build display row from DB — only last_four/model_name/is_enabled (SEC-6)
    row = db.execute(
        select(ApiCredential).where(ApiCredential.provider == provider)
    ).scalar_one_or_none()

    ctx = {
        "provider": provider,
        "last_four": row.last_four or "" if row else "",
        "model_name": row.model_name or "" if row else "",
        "is_enabled": row.is_enabled if row else False,
    }
    # Emit audit event — provider + last_four only, NEVER the key (T-09-11)
    log.info(events.ADMIN_API_CREDENTIAL_SET, provider=provider, last_four=ctx["last_four"])

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_credential_row.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# POST /admin/credentials/{provider}/enabled — enable/disable toggle
# ---------------------------------------------------------------------------


@router.post("/credentials/{provider}/enabled", response_class=HTMLResponse)
async def toggle_credential_enabled(
    provider: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Toggle is_enabled for the provider; last_four + model_name unchanged.

    Checkbox semantics: an HTML checkbox sends "on" when checked; the field
    is absent (or empty) when unchecked. We parse any truthy value as enabled.
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    form_data = await request.form()
    enabled_raw = form_data.get("enabled", "")
    enabled = str(enabled_raw).lower().strip() in ("on", "true", "1", "yes")

    cred_service.set_provider_enabled(
        db,
        provider,  # type: ignore[arg-type]
        enabled,
        by_user_id=user.id,
    )

    # Build display row — never the ciphertext (SEC-6)
    row = db.execute(
        select(ApiCredential).where(ApiCredential.provider == provider)
    ).scalar_one_or_none()

    ctx = {
        "provider": provider,
        "last_four": row.last_four or "" if row else "",
        "model_name": row.model_name or "" if row else "",
        "is_enabled": row.is_enabled if row else enabled,
    }

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_credential_row.html",
        context=ctx,
    )


__all__ = ["router"]
