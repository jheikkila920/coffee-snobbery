"""Debug + operational endpoints.

``/debug/proxy`` is admin-gated as of Phase 2 (D-14 — closing the Phase 1
D-16 hand-off). Permanent endpoint — used after every NGINX config change
to confirm ``X-Forwarded-Proto`` / ``X-Forwarded-For`` are flowing
end-to-end. Admins curl this from the deployed app to verify proxy
behavior; non-admins and anonymous users get 403.
See README §NGINX reverse proxy and §Operational smoke check.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.dependencies.auth import require_admin
from app.schemas.debug import DebugProxyResponse

router = APIRouter()


@router.get(
    "/debug/proxy",
    response_model=DebugProxyResponse,
    dependencies=[Depends(require_admin)],
)
async def debug_proxy(request: Request) -> DebugProxyResponse:
    """Echo what uvicorn ProxyHeadersMiddleware concluded about the request.

    ``headers_honored`` is the operator-facing boolean: True when the
    upstream NGINX ``X-Forwarded-Proto`` rewrote ``request.url.scheme`` to
    ``"https"`` AND the client IP was rewritten away from the trust list
    (the proxy itself). False means the trust list is misconfigured or
    NGINX is not setting the X-Forwarded-* headers.
    """
    client_host = request.client.host if request.client else "unknown"
    trusted_proxy_ips = settings.TRUSTED_PROXY_IPS
    scheme = request.url.scheme
    trusted_list = {ip.strip() for ip in trusted_proxy_ips.split(",") if ip.strip()}
    headers_honored = scheme == "https" and client_host not in trusted_list
    return DebugProxyResponse(
        scheme=scheme,
        client_host=client_host,
        trusted_proxy_ips=trusted_proxy_ips,
        headers_honored=headers_honored,
    )
