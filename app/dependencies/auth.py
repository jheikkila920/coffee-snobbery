"""FastAPI Depends callables for authentication gates.

Two gates:

* :func:`require_user` — 401 when no authenticated session.
* :func:`require_admin` — 403 when not an admin (folds the no-session case
  into 403 per CONTEXT D-13 wording "returns 403 otherwise"; the AUTH-09
  VALIDATION row "anon → 401 OR 403 / non-admin → 403 / admin → 200"
  permits this).

Phase 2 wires these into ``/admin`` (Plan 02-08) and ``/debug/proxy`` (also
Plan 02-08). Phase 4+ inherits :func:`require_user` for catalog routes that
need an authenticated session but not admin privileges.

Reads from ``request.state.user`` which is set by
:class:`app.middleware.session.SessionMiddleware` (Plan 02-06 upgrades the
stub dict to a real :class:`app.models.user.User` row per D-09).

Why fold anon into 403 in :func:`require_admin` but keep 401 in
:func:`require_user`: an admin-gated route that returns 401 to anonymous and
403 to non-admin leaks "you're logged in but not admin" on the second
response — useless information disclosure (ASVS V7.4.3). Routes that only
need "is a user logged in" still benefit from the distinguishable 401.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.models.user import User


def require_user(request: Request) -> User:
    """Return the authenticated :class:`User`; raise 401 if no session.

    Reads ``request.state.user`` (populated by
    :class:`app.middleware.session.SessionMiddleware` per D-09).
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(request: Request) -> User:
    """Return the authenticated admin :class:`User`; raise 403 otherwise.

    Per CONTEXT D-13 the unified 403 covers both anonymous and non-admin
    cases — no point distinguishing the two for an admin-gated route
    since the 401-then-403 dance leaks "you're logged in but not admin"
    on the second response which is not a useful disclosure.
    """
    user = getattr(request.state, "user", None)
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return user


__all__ = ["require_user", "require_admin"]
