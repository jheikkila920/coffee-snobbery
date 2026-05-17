"""Rate-limit helper — **temporary Plan 01-03 stub**.

Plan 07 replaces this module with the final slowapi wiring:

- ``limiter = Limiter(key_func=get_remote_address, default_limits=[...])``
  using ``slowapi.util.get_remote_address`` so the keying function honours
  ``X-Forwarded-For`` (via Uvicorn ``--proxy-headers``).
- A ``RateLimitExceeded`` exception handler registered on the FastAPI app
  that returns a 429 with the canonical JSON / HTML response.
- Decoration of ``/login`` (5/15 minutes per IP) and ``/setup``
  (3/hour per IP) under SEC-01 / AUTH-08.

Why a stub now?
    Plan 03 needs to decorate ``POST /csp-report`` with
    ``@limiter.limit("30/minute")`` (D-17). Without this module, Plan 03's
    ``app/routers/csp_report.py`` cannot import; under Wave 1 parallelism
    Plan 03 and Plan 07 must both land independently of each other.

What the stub does
------------------
- Exposes a ``limiter`` object whose ``.limit(rate)`` method returns an
  identity decorator. The decoration site
  (``@limiter.limit("30/minute")``) compiles and runs in isolation, but
  rate-limiting itself is a no-op — every request is served. The dedicated
  Wave 0 test ``tests/routers/test_csp_report.py::test_rate_limit`` is
  expected to remain RED until Plan 07 lands; the other two CSP-report
  tests (``test_legacy_format``, ``test_reporting_api_format``) do not
  depend on rate limiting.
- Falls back to slowapi when it's importable, so Plan 07 can land the real
  ``Limiter`` instance without touching this file's API surface. The
  fallback is intentionally minimal — Plan 07 will rewrite this module
  outright with the final shape, including the exception handler and the
  ``app.state.limiter`` wiring on the FastAPI app.

Stub API surface (Plan 07 must preserve these)
----------------------------------------------
- ``limiter.limit(rate_str: str)`` -> callable decorator that preserves the
  decorated function signature (including the ``request: Request`` parameter
  slowapi requires for keying).
- The ``limiter`` symbol importable via
  ``from app.rate_limit import limiter`` from any router module.

DO NOT add features to this stub. If a Wave 1 plan needs a real rate-limit
behaviour during its own development, raise it as a Plan 07 dependency and
ship a slowapi pin in ``requirements.txt`` as part of that plan.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    # Prefer the real slowapi when present (Plan 07 will pin it in
    # requirements.txt). Until then the import fails and we drop into the
    # no-op shim below.
    from slowapi import Limiter as _SlowapiLimiter
    from slowapi.util import get_remote_address as _get_remote_address

    limiter: Any = _SlowapiLimiter(
        key_func=_get_remote_address,
        default_limits=[],
    )
except ImportError:  # pragma: no cover — exercised only when slowapi is absent

    class _NoOpLimiter:
        """No-op stand-in for ``slowapi.Limiter`` until Plan 07 lands.

        Mirrors the subset of slowapi's surface used by the Wave 1 routers —
        only ``.limit(rate_str)``. Returns the decorated function unchanged.
        Plan 07's real Limiter implements rate enforcement; until then every
        decorated route serves every request without throttling. The
        ``test_rate_limit`` Wave 0 test stays red until Plan 07 swaps this
        out — that's expected and tracked in 01-03-SUMMARY.md.
        """

        def limit(
            self, rate_str: str
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            """Identity decorator. ``rate_str`` is ignored under the stub."""

            def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return func

            return _decorator

    limiter = _NoOpLimiter()
