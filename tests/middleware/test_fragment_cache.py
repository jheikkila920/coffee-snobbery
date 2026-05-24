"""Wave 0 stubs for D-11 / D-12 (FragmentCacheHeadersMiddleware).

Covers per-task verification map rows for the fragment-cache decisions from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_full_page`` — GET / without HX-Request → Cache-Control: private, no-cache, must-revalidate
- ``test_fragment``     — GET / with HX-Request: true → Cache-Control: no-store + Vary: HX-Request
- ``test_no_overwrite`` — route-set Cache-Control is preserved
- ``test_static_bypass`` — /static/ paths untouched by the middleware

Plan 06 wires ``app.middleware.fragment_cache.FragmentCacheHeadersMiddleware``.
Tests skip cleanly until that lands. The probe route ``/debug/cache-test`` for
``test_no_overwrite`` lives in Plan 06's deliverables; if absent we xfail.
"""

from __future__ import annotations

import pytest


def _require_fragment_cache() -> None:
    try:
        from app.middleware.fragment_cache import (  # noqa: F401
            FragmentCacheHeadersMiddleware,
        )
    except ImportError:
        pytest.skip(
            "Wave 1 dependency: "
            "app.middleware.fragment_cache.FragmentCacheHeadersMiddleware (Plan 06)"
        )


def test_full_page(client) -> None:
    """D-11: full-page response → private, no-cache, must-revalidate."""
    _require_fragment_cache()
    response = client.get("/")
    cache_control = response.headers.get("Cache-Control", "")
    assert "private" in cache_control, cache_control
    assert "no-cache" in cache_control, cache_control
    assert "must-revalidate" in cache_control, cache_control


def test_fragment(client) -> None:
    """D-11 / PITFALL HX-2: HX-Request → no-store + Vary: HX-Request."""
    _require_fragment_cache()
    response = client.get("/", headers={"HX-Request": "true"})
    cache_control = response.headers.get("Cache-Control", "")
    vary = response.headers.get("Vary", "")
    assert "no-store" in cache_control, cache_control
    assert "HX-Request" in vary, vary


def test_no_overwrite(client) -> None:
    """D-12: a route that sets its own Cache-Control is not overridden.

    Plan 06 ships ``/debug/cache-test`` returning ``Cache-Control: public, max-age=60``.
    Wave 0 xfails when the route is missing.
    """
    _require_fragment_cache()
    response = client.get("/debug/cache-test")
    if response.status_code == 404:
        pytest.xfail("/debug/cache-test probe route lands in Plan 06")
    assert response.headers.get("Cache-Control") == "public, max-age=60", (
        f"middleware overwrote route-set Cache-Control: {response.headers.get('Cache-Control')}"
    )


def test_static_bypass(client) -> None:
    """D-11: /static/ paths bypass the middleware (StaticFiles owns its own headers)."""
    _require_fragment_cache()
    # Phase 0 mounts /static; serve any path that exists. If none, xfail
    # rather than fail collection — the rule still holds, we just can't probe.
    response = client.get("/static/healthcheck.txt")
    if response.status_code == 404:
        pytest.xfail(
            "/static/healthcheck.txt probe not provided by Phase 0 — Plan 06 may "
            "stage one alongside the middleware to keep this test green"
        )
    cache_control = response.headers.get("Cache-Control", "")
    # Middleware must not impose its full-page / fragment cache rules here. The
    # cleanest invariant: middleware's "private, no-cache, must-revalidate"
    # string is absent (StaticFiles may set its own short-lived public cache).
    assert "private, no-cache, must-revalidate" not in cache_control, (
        f"middleware applied full-page Cache-Control to /static/: {cache_control!r}"
    )
    assert "no-store" not in cache_control, (
        f"middleware applied fragment Cache-Control to /static/: {cache_control!r}"
    )
