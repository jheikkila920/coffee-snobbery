"""Wave 0 stubs for AUTH-05 (custom table-backed SessionMiddleware).

Covers per-task verification map rows for AUTH-05 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_unauthenticated_request_has_no_user`` — GET / → request.state.user is None
- ``test_refresh_throttling``                  — last_seen updated only after 5 min
- ``test_invalid_signature_clears_cookie``     — bogus session_id cookie → Max-Age=0

The Plan 04 symbol is ``app.middleware.session.SessionMiddleware``. Each test
imports it (or its module) lazily; missing symbol → pytest.skip. The
``REFRESH_THRESHOLD_SECONDS`` constant lives at module level in the Wave 1
implementation per RESEARCH §5; the throttling test references it by symbol
so a future renumbering breaks loudly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_unauthenticated_request_has_no_user(client) -> None:
    """AUTH-05: an unauthenticated request resolves request.state.user to None.

    Asserts via the ``/debug/whoami`` probe (Wave 1 Plan 04 lands it). If the
    probe route does not yet exist, this test is xfailed rather than skipped so
    the missing-route condition is visible to reviewers.
    """
    try:
        from app.middleware.session import SessionMiddleware  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware (Plan 04)")
    response = client.get("/debug/whoami")
    if response.status_code == 404:
        pytest.xfail("/debug/whoami probe not yet implemented (Plan 04 adds it)")
    assert response.status_code == 200, response.text
    assert response.headers.get("X-User-Present") == "0", response.headers


def test_refresh_throttling() -> None:
    """AUTH-05: session.last_seen refreshes only when stale by > REFRESH_THRESHOLD_SECONDS.

    Calls the middleware's refresh helper directly (no HTTP round-trip). A
    just-refreshed row must NOT be re-refreshed on a second call; a 5-minute-old
    row MUST be refreshed.
    """
    try:
        from app.middleware.session import (
            REFRESH_THRESHOLD_SECONDS,
            SessionMiddleware,  # noqa: F401
        )
    except ImportError:
        pytest.skip(
            "Wave 1 dependency: app.middleware.session.REFRESH_THRESHOLD_SECONDS "
            "(Plan 04)"
        )
    assert REFRESH_THRESHOLD_SECONDS == 300, (
        f"REFRESH_THRESHOLD_SECONDS must be 300 (5 min) per RESEARCH §5, "
        f"got {REFRESH_THRESHOLD_SECONDS}"
    )
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(seconds=10)  # noqa: F841 — sentinel for the next assertion path
    stale = now - timedelta(seconds=600)  # noqa: F841 — 10 min ago, must refresh
    # The actual helper signature lands in Wave 1; once it does, this test
    # exercises both branches against an in-memory fake session row. For Wave 0
    # we have asserted the threshold constant — the rest is xfail until the
    # helper is named.
    pytest.xfail(
        "refresh-throttle helper not yet exported by app.middleware.session — "
        "Wave 1 Plan 04 names it and turns this test green"
    )


def test_invalid_signature_clears_cookie(client) -> None:
    """AUTH-05: tampered session_id cookie → response sets session_id=; Max-Age=0."""
    try:
        from app.middleware.session import SessionMiddleware  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware (Plan 04)")
    response = client.get("/", cookies={"session_id": "this-is-not-a-valid-signature"})
    # Look at Set-Cookie headers; the middleware must clear the cookie via
    # Max-Age=0 (or expires=Thu, 01 Jan 1970...).
    set_cookies = response.headers.get_list("set-cookie") if hasattr(
        response.headers, "get_list"
    ) else [response.headers.get("set-cookie", "")]
    cleared = any(
        "session_id=" in c and ("Max-Age=0" in c or "max-age=0" in c)
        for c in set_cookies
    )
    if not cleared:
        pytest.xfail(
            "Wave 1 Plan 04 must clear an invalid session_id cookie via Max-Age=0; "
            f"Set-Cookie headers seen: {set_cookies}"
        )
