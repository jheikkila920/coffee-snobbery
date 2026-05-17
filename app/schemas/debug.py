"""Pydantic v2 response model for the /debug/proxy operational endpoint.

The four fields are the smoke-check surface for verifying that NGINX's
``X-Forwarded-Proto`` / ``X-Forwarded-For`` headers flow through uvicorn's
``ProxyHeadersMiddleware`` (``--proxy-headers --forwarded-allow-ips=...``).
``headers_honored`` is the single boolean an operator reads after every
NGINX config change — see README §Operational smoke check.
"""

from __future__ import annotations

from pydantic import BaseModel


class DebugProxyResponse(BaseModel):
    """JSON body for ``GET /debug/proxy`` per D-16."""

    scheme: str
    client_host: str
    trusted_proxy_ips: str
    headers_honored: bool
