"""Single source of truth for the Jinja2 templates engine.

Autoescape ON globally per SEC-05 (REQUIREMENTS.md). ``csp_nonce(request)``
is registered as a Jinja global so every template can emit a per-request
nonce on inline ``<script>`` / ``<style>`` tags via::

    <script nonce="{{ csp_nonce(request) }}" src="..."></script>

The nonce itself is minted by :class:`app.middleware.request_context.RequestContextMiddleware`
(Plan 01-02) and stashed on ``request.state.csp_nonce``. When the middleware
has not run (e.g., a unit-test rendering a template directly, or a request
that bypasses the stack), :func:`csp_nonce` returns the empty string —
``script-src 'self' 'nonce-'`` is unmatched by any tag, so the inline
script is silently blocked rather than tripping a template error. This is
the desired fail-safe: a misconfigured request gets no script execution.

Plan 04+ route handlers consume the canonical ``templates`` instance:

    from app.templates_setup import templates

The legacy Phase 0 ``app.main`` ships a second ``Jinja2Templates(directory=...)``
instance pinned to ``app.state.templates``. Plan 01-09 will collapse the two
into this module — until then, the two coexist (both autoescape ON; SEC-05
satisfied either way). The Wave 0 ``test_autoescape_enabled`` falls back to
the Phase 0 wrapper if this module is absent; once this module ships, the
test prefers this symbol (per the test's import-probe order).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from starlette.requests import Request

from app.config import settings

# Single Jinja2Templates instance for the whole application.
templates = Jinja2Templates(directory="app/templates")

# FastAPI's Jinja2Templates wrapper sets autoescape=True by default, but
# ``select_autoescape`` is the more explicit form: it also escapes files
# whose extension is ``.jinja`` or ``.jinja2`` (used by future fragment
# templates if the team ever adopts the ``.jinja2`` extension convention).
# Setting ``env.autoescape`` directly overrides the constructor default.
templates.env.autoescape = select_autoescape(["html", "jinja", "jinja2"])


def csp_nonce(request: Request) -> str:
    """Return the per-request CSP nonce minted by RequestContextMiddleware.

    Falls back to the empty string when the middleware has not run (e.g.,
    a unit test rendering a template directly, or a non-HTTP scope). CSP
    ``script-src 'self' 'nonce-'`` will not match any tag with an empty
    nonce, so the corresponding inline script is silently blocked — the
    fail-safe outcome the threat model (T-08-07) requires.
    """
    return getattr(request.state, "csp_nonce", "")


def localdt(value: datetime | str | None, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    """Jinja filter: convert a UTC datetime (or ISO-8601 string) to APP_TIMEZONE.

    - Naive datetimes are assumed UTC before conversion.
    - ISO-8601 strings are parsed via ``datetime.fromisoformat``; a trailing
      "Z" is normalised to "+00:00" for Python < 3.11 compatibility.
    - On parse error or None input the original value is returned as-is so
      the template degrades gracefully rather than crashing.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if value is None:
        return ""
    try:
        tz = ZoneInfo(settings.APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = UTC

    try:
        if isinstance(value, str):
            # Normalise trailing Z for Python fromisoformat (pre-3.11 doesn't parse it)
            normalised = value.rstrip("Z") + "+00:00" if value.endswith("Z") else value
            dt = datetime.fromisoformat(normalised)
        else:
            dt = value
        # Treat naive datetimes as UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(tz).strftime(fmt)
    except Exception:
        return str(value)


# Registered as a Jinja global so templates can call ``csp_nonce(request)``
# without an explicit context push. RESEARCH §4 Option B — preferred over
# the per-route ``Depends(get_csp_nonce)`` approach because every Phase 4+
# template that extends ``base.html`` would otherwise need the dependency
# threaded through its handler.
templates.env.globals["csp_nonce"] = csp_nonce

# ``localdt`` filter: converts UTC datetimes / ISO-8601 strings to APP_TIMEZONE
# for display. Registered globally so all templates can use it without imports.
templates.env.filters["localdt"] = localdt
