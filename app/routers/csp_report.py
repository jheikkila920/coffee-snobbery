"""``POST /csp-report`` — log-only CSP-violation endpoint (Plan 01-03).

CONTEXT D-06 locks this as a log-only endpoint: every browser-supplied
report becomes exactly one structured ``csp.violation`` log line and the
endpoint returns ``204 No Content`` unconditionally. No DB writes, no
forwarded reporting, no UI surface. Pitfall §13.5 (CSP-report self-DoS):
the handler does the minimum work possible — one ``log.warning`` call per
report — and never blocks on I/O outside structlog's stdlib bridge.

Dual content-type handling
--------------------------
Browsers emit CSP violations in two body shapes:

1. **Legacy** (``application/csp-report``) — single hyphenated-key object::

       {"csp-report": {"blocked-uri": "...", "violated-directive": "..."}}

   Emitted when the response carries ``Content-Security-Policy:
   ... report-uri /csp-report``.

2. **Modern Reporting API** (``application/reports+json``) — array of
   camelCase-key reports::

       [{"type": "csp-violation", "body":
           {"blockedURL": "...", "effectiveDirective": "..."}}, ...]

   Emitted when the response carries ``Content-Security-Policy:
   ... report-to csp-report`` and a matching ``Reporting-Endpoints`` header
   (the ``SecurityHeadersMiddleware`` ships both directives so we receive
   reports from both old and new browsers concurrently — D-05).

Both shapes are reduced to the same four documented fields
(``blocked_uri``, ``violated_directive``, ``line``, ``source_file``) plus
the client ``ip``. Other keys are stripped to limit log surface (threat
T-03-07 — Referer URLs can contain tokens).

Rate limit
----------
``@limiter.limit("30/minute")`` per D-17. Plan 03 ships a no-op
``app.rate_limit:limiter`` stub; Plan 07 swaps in the real slowapi limiter
and adds the 429 exception handler. The ``test_rate_limit`` Wave 0 test
stays red until Plan 07 lands — by design.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request, Response

from app.events import CSP_VIOLATION
from app.rate_limit import limiter

log = structlog.get_logger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Internal helper                                                              #
# --------------------------------------------------------------------------- #


def _log_csp_violation(payload: dict[str, Any], ip: str) -> None:
    """Emit one structured ``csp.violation`` log line for a single report.

    Accepts either the legacy hyphenated-key shape or the Reporting API
    camelCase shape and normalises both to the four documented fields.
    Any other keys in ``payload`` are silently dropped — see threat
    T-03-07 (PII in browser-supplied report bodies).

    Args:
        payload: The inner report object (``raw["csp-report"]`` for legacy
            or ``report["body"]`` for the Reporting API). May be empty —
            we still emit a (mostly-empty) event so an operator can see
            that a malformed report arrived.
        ip: The client IP (``request.client.host`` post ``--proxy-headers``
            rewrite). Already a string; never ``None`` at this site
            (the caller substitutes ``"unknown"`` for missing client).
    """
    # Legacy keys (hyphenated) take precedence over modern keys (camelCase)
    # because if both are present the report is malformed and we prefer the
    # older, more widely-tested key set.
    blocked_uri = payload.get("blocked-uri") or payload.get("blockedURL") or ""
    violated_directive = (
        payload.get("violated-directive")
        or payload.get("effectiveDirective")
        or ""
    )
    line = payload.get("line-number") or payload.get("lineNumber") or 0
    source_file = (
        payload.get("source-file") or payload.get("sourceFile") or ""
    )

    log.warning(
        CSP_VIOLATION,
        blocked_uri=blocked_uri,
        violated_directive=violated_directive,
        line=line,
        source_file=source_file,
        ip=ip,
    )


# --------------------------------------------------------------------------- #
# Endpoint                                                                     #
# --------------------------------------------------------------------------- #


@router.post("/csp-report", status_code=204)
@limiter.limit("30/minute")
async def csp_report(request: Request) -> Response:
    """Accept a CSP violation report, log it, return 204.

    Returns 204 unconditionally — even on malformed JSON or an unknown
    body shape — because browsers do not read the response body, and a
    non-204 status risks the browser retrying and amplifying the report
    flood (pitfall §13.5).

    The ``request: Request`` parameter is required by slowapi's
    ``@limiter.limit`` decorator (it inspects the request to derive the
    rate-limit key). Plan 07's real Limiter relies on this; the Plan 03
    no-op stub tolerates any signature, but we keep the parameter so the
    swap is mechanical.
    """
    content_type = request.headers.get("content-type", "")
    ip = request.client.host if request.client else "unknown"

    # Browsers occasionally send empty bodies or non-JSON garbage when the
    # CSP firing path itself fails. Swallow JSON-decode errors silently —
    # we still return 204 so the browser doesn't retry, but we don't fan
    # out a log line for an unparseable payload.
    try:
        raw = await request.json()
    except (ValueError, UnicodeDecodeError):
        return Response(status_code=204)

    if "application/reports+json" in content_type and isinstance(raw, list):
        # Modern Reporting API: array of reports. We emit one log line per
        # report. The ``type`` field is informational — we only need the
        # body to extract the four documented fields.
        for report in raw:
            if isinstance(report, dict):
                body = report.get("body", {})
                if isinstance(body, dict):
                    _log_csp_violation(body, ip)
    elif isinstance(raw, dict) and "csp-report" in raw:
        # Legacy report-uri body shape. Single report per POST.
        inner = raw.get("csp-report", {})
        if isinstance(inner, dict):
            _log_csp_violation(inner, ip)
    else:
        # Unknown shape: log a single low-severity line so an operator can
        # see that the endpoint received a report we couldn't decode, but
        # don't try to extract fields from an unrecognised structure.
        log.info(CSP_VIOLATION, ip=ip, shape="unknown")

    return Response(status_code=204)
