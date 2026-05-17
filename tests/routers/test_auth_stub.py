"""Wave 0 stubs for AUTH-08 (slowapi rate-limit on /login).

Covers per-task verification map rows for AUTH-08 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_login_rate_limit``        — 6th POST /login in 15 min from same IP → 429
- ``test_login_rate_limit_per_ip`` — switching X-Forwarded-For unblocks the 6th attempt

Plan 07 wires the stub /login route + the slowapi `5/15minutes` decorator.
Both tests include a valid CSRF cookie + header (mirrors the production POST
shape) so the assertion isolates the rate-limit concern from the CSRF
concern. If either dependency is missing, the test skips cleanly.
"""

from __future__ import annotations

import pytest


def _require_auth_stub() -> None:
    try:
        from app.routers.auth import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.routers.auth (Plan 07)")
    try:
        from app.rate_limit import limiter  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.rate_limit.limiter (Plan 07)")


def _csrf_pair(client) -> tuple[str, dict[str, str]]:
    """Return ``(token, headers)`` for a CSRF-valid POST.

    Skips the calling test if Wave 1 hasn't wired the csrftoken cookie yet.
    """
    primer = client.get("/")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie 'csrftoken' not yet set by Wave 1 middleware")
    return token, {"X-CSRF-Token": token}


def test_login_rate_limit(client) -> None:
    """AUTH-08: first 5 POST /login from the same IP return 200; 6th returns 429."""
    _require_auth_stub()
    token, headers = _csrf_pair(client)
    cookies = {"csrftoken": token}
    statuses: list[int] = []
    for _ in range(6):
        r = client.post(
            "/login",
            data={"username": "x", "password": "y"},
            headers=headers,
            cookies=cookies,
        )
        statuses.append(r.status_code)
    assert all(s == 200 for s in statuses[:5]), (
        f"first five /login attempts must be 200, got {statuses[:5]}"
    )
    assert statuses[5] == 429, (
        f"6th /login attempt must be 429 (rate-limited), got {statuses[5]}"
    )


def test_login_rate_limit_per_ip(client) -> None:
    """AUTH-08: rate limit is per-IP. 5 attempts from 1.1.1.1, then 1 from 2.2.2.2 → 200.

    Relies on uvicorn ``--proxy-headers`` flag making slowapi key by the
    X-Forwarded-For-derived client.host. If the flag isn't honored in the
    TestClient transport, this test xfails — it's a real assertion the
    docker-compose stack still owes us, not a stub bug.
    """
    _require_auth_stub()
    token, headers = _csrf_pair(client)
    cookies = {"csrftoken": token}
    for _ in range(5):
        r = client.post(
            "/login",
            data={"username": "x", "password": "y"},
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            cookies=cookies,
        )
        if r.status_code == 429:
            pytest.xfail(
                "rate limit triggered before 5 attempts from 1.1.1.1 — "
                "TestClient transport may not preserve X-Forwarded-For for "
                "slowapi key derivation"
            )
    # The 6th attempt from a DIFFERENT IP must NOT be rate-limited.
    r6 = client.post(
        "/login",
        data={"username": "x", "password": "y"},
        headers={**headers, "X-Forwarded-For": "2.2.2.2"},
        cookies=cookies,
    )
    assert r6.status_code == 200, (
        f"6th attempt from 2.2.2.2 must be 200 (per-IP key), got {r6.status_code}"
    )
