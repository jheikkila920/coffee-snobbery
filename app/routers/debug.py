"""Debug + operational endpoints.

Phase 1 ships ``/debug/proxy`` public per D-16; Phase 2 will wrap it in the
``is_admin`` gate. Permanent endpoint — used after every NGINX config change
to confirm ``X-Forwarded-Proto`` / ``X-Forwarded-For`` are flowing
end-to-end. See README §NGINX reverse proxy and §Operational smoke check.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas.debug import DebugProxyResponse

router = APIRouter()


@router.get("/debug/proxy", response_model=DebugProxyResponse)
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
