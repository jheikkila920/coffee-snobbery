"""Unit tests for ``app.dependencies.auth.require_user`` / ``require_admin``.

Synthetic ``starlette.requests.Request`` objects (built from a minimal ASGI
scope) drive the dependencies directly — no FastAPI ``TestClient``, no real
``User`` SQLAlchemy row, no DB. The integration assertion (real ``User`` row +
real ``Depends`` through ``TestClient``) lives in
``tests/routers/test_admin.py::test_admin_gate_three_states`` (Plan 02-08).

This file deliberately uses lazy imports inside each test so the file is
collectable BEFORE Plan 02-03 Task 3 lands ``app.dependencies.auth``; until
then every test skips cleanly via :func:`_require_dep`.

Pattern source: ``.planning/phases/02-auth/02-PATTERNS.md`` lines 905-940 +
``.planning/phases/02-auth/02-RESEARCH.md`` §"FastAPI — ``Depends(require_admin)``
pattern" (lines 407-459).
"""

from __future__ import annotations

import pytest
from starlette.requests import Request


def _require_dep() -> None:
    """Skip cleanly if ``app.dependencies.auth`` has not landed yet."""
    try:
        from app.dependencies.auth import require_admin, require_user  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.dependencies.auth (Plan 02-03 Task 2/3)")


def _make_request(user: object | None) -> Request:
    """Build a minimal :class:`Request` with ``state.user`` set.

    Starlette materialises ``Request.state`` lazily from
    ``scope["state"]`` — providing the dict in the scope is the simplest
    way to populate it without going through a middleware stack.
    """
    scope = {"type": "http", "state": {"user": user}}
    return Request(scope)


class _FakeAdmin:
    """Minimal stand-in for an admin ``User`` row.

    Only ``is_admin`` is read by the dependencies; using a tiny class
    keeps the test independent of the real SQLAlchemy model (no DB).
    """

    is_admin = True


class _FakeRegular:
    """Minimal stand-in for a non-admin ``User`` row."""

    is_admin = False


# --------------------------------------------------------------------------- #
# require_admin                                                               #
# --------------------------------------------------------------------------- #


def test_require_admin_unit_anon_raises() -> None:
    """Anonymous request (``state.user is None``) raises 401 OR 403.

    Per the AUTH-09 VALIDATION row "anon → 401 OR 403" the dependency
    may fold the anon and non-admin cases into one 403 (planner's
    choice, recorded in CONTEXT D-13). Accept either status code here
    so the test pins behavior without over-specifying it.
    """
    _require_dep()
    from fastapi import HTTPException

    from app.dependencies.auth import require_admin

    req = _make_request(None)
    with pytest.raises(HTTPException) as exc:
        require_admin(req)
    assert exc.value.status_code in (401, 403)


def test_require_admin_unit_non_admin_raises() -> None:
    """Authenticated non-admin → 403 (strict)."""
    _require_dep()
    from fastapi import HTTPException

    from app.dependencies.auth import require_admin

    req = _make_request(_FakeRegular())
    with pytest.raises(HTTPException) as exc:
        require_admin(req)
    assert exc.value.status_code == 403


def test_require_admin_unit_admin_returns_user() -> None:
    """Admin user returned unchanged (same identity, not a copy)."""
    _require_dep()
    from app.dependencies.auth import require_admin

    user = _FakeAdmin()
    req = _make_request(user)
    result = require_admin(req)
    assert result is user


# --------------------------------------------------------------------------- #
# require_user                                                                #
# --------------------------------------------------------------------------- #


def test_require_user_unit_anon_raises() -> None:
    """Anonymous request → 401 (strict — anon distinction kept)."""
    _require_dep()
    from fastapi import HTTPException

    from app.dependencies.auth import require_user

    req = _make_request(None)
    with pytest.raises(HTTPException) as exc:
        require_user(req)
    assert exc.value.status_code == 401


def test_require_user_unit_authenticated_returns() -> None:
    """Authenticated user (admin or not) returned unchanged."""
    _require_dep()
    from app.dependencies.auth import require_user

    user = _FakeAdmin()
    req = _make_request(user)
    result = require_user(req)
    assert result is user
