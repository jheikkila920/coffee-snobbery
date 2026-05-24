"""Session-row helpers + Set-Cookie builders for AUTH-05.

Two surfaces live here:

1. **Async DB helpers** (``create_session``, ``regenerate_session``,
   ``delete_session``, ``get_session_by_id``, ``refresh_last_seen``) used
   by :mod:`app.middleware.session` at request time and by Phase 2's
   ``/login`` / ``/logout`` / admin routes for session lifecycle.

2. **Pure-function cookie builders** (``build_session_cookie``,
   ``build_session_clear_cookie``) returning the ``Set-Cookie`` *value*
   (without the ``Set-Cookie:`` prefix) so ASGI middleware can drop them
   straight into the response header list as ``(b"set-cookie", value)``
   tuples.

Helpers use SQLAlchemy 2.0 :func:`sqlalchemy.select` / :func:`delete` /
:func:`update` constructs only — never the legacy ``Query`` API
(CLAUDE.md "Stack invariants"). :class:`sqlalchemy.ext.asyncio.AsyncSession`
is the session type accepted; the matching async engine + factory land in
a later Phase 0 follow-up or Phase 7 (the async path for AI calls).

Regeneration semantics (CONTEXT D-10):

* On a successful login, logout, or ``is_admin`` toggle, Phase 2 calls
  :func:`regenerate_session` with the current session_id (if any) and the
  user_id. The helper DELETES the old row and INSERTS a new one **under a
  single commit** so the swap is atomic. A new UUID is returned; the
  caller is responsible for re-signing the cookie and emitting it on the
  response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session

# 30 days — matches the cookie Max-Age in :func:`build_session_cookie` and
# CONTEXT D-10. The DB row is the authoritative expiry source (T-04-04
# mitigation); cookie Max-Age handles browser-side eviction.
SESSION_LIFETIME_DAYS = 30
SESSION_MAX_AGE_SECONDS = SESSION_LIFETIME_DAYS * 24 * 3600  # 2_592_000


async def create_session(db: AsyncSession, user_id: int) -> uuid.UUID:
    """Insert a fresh row for *user_id*; return the new session_id.

    Times are recorded in UTC. ``last_seen`` and ``created_at`` are set to
    "now"; ``expires_at`` is "now + 30 days" — sliding refresh, applied at
    request time by :func:`refresh_last_seen`.
    """
    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_LIFETIME_DAYS)
    new_id = uuid.uuid4()
    db.add(
        Session(
            session_id=new_id,
            user_id=user_id,
            last_seen=now,
            expires_at=expires,
            created_at=now,
        )
    )
    await db.commit()
    return new_id


async def regenerate_session(
    db: AsyncSession,
    current_session_id: uuid.UUID | None,
    user_id: int,
) -> uuid.UUID:
    """Atomic delete-then-insert for session-ID regeneration (D-10).

    Phase 2 wires this into ``/login`` (after successful argon2 verify),
    ``/logout``, and the admin ``is_admin`` toggle — anywhere privilege
    context changes — per CONTEXT D-10 / PITFALL SEC-3 (session fixation
    defence; ASVS V3.2.3).

    The delete + insert run in the same transaction and commit ONCE so a
    concurrent reader cannot observe the gap. If *current_session_id* is
    ``None`` (no prior cookie — e.g., first-time login), the delete is
    skipped and only the insert runs.

    Returns the **new** session_id; the caller signs it and sets the
    cookie.
    """
    if current_session_id is not None:
        await db.execute(delete(Session).where(Session.session_id == current_session_id))

    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_LIFETIME_DAYS)
    new_id = uuid.uuid4()
    db.add(
        Session(
            session_id=new_id,
            user_id=user_id,
            last_seen=now,
            expires_at=expires,
            created_at=now,
        )
    )
    # Single commit so the swap is atomic across the delete + insert.
    await db.commit()
    return new_id


async def delete_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Delete the row keyed by *session_id*. Used by Phase 2 ``/logout``."""
    await db.execute(delete(Session).where(Session.session_id == session_id))
    await db.commit()


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    """Return the row for *session_id*, or ``None`` if no such row exists.

    Pure read — no commit, no last_seen update. The middleware decides
    separately whether to issue a write-throttled
    :func:`refresh_last_seen`.
    """
    result = await db.execute(select(Session).where(Session.session_id == session_id))
    return result.scalar_one_or_none()


async def refresh_last_seen(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Slide both ``last_seen`` and ``expires_at`` forward to "now / now+30d".

    Called by :mod:`app.middleware.session` only when
    ``now - last_seen > REFRESH_THRESHOLD_SECONDS`` (5 minutes) — the
    ~98% write-reduction noted in RESEARCH §5. A single UPDATE; one
    commit.
    """
    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_LIFETIME_DAYS)
    await db.execute(
        update(Session)
        .where(Session.session_id == session_id)
        .values(last_seen=now, expires_at=expires)
    )
    await db.commit()


# --------------------------------------------------------------------------- #
# Set-Cookie value builders (pure; no DB; no Set-Cookie: prefix)              #
# --------------------------------------------------------------------------- #


def build_session_cookie(signed_value: str, *, max_age: int = SESSION_MAX_AGE_SECONDS) -> str:
    """Return the literal ``Set-Cookie`` value for a freshly-minted session.

    Attributes are locked by CONTEXT D-10 (T-04-03 mitigation):

    * ``HttpOnly``  — blocks ``document.cookie`` reads (defends XSS leak).
    * ``Secure``    — blocks HTTP transmission.
    * ``SameSite=Lax`` — blocks cross-site CSRF in most browsers.
    * ``Max-Age=2592000`` — 30-day client-side expiry; DB row is server
      authority.
    * ``Path=/``    — cookie scoped to the entire app.

    The returned string is the *value* — ASGI middleware adds the
    ``Set-Cookie:`` header name when injecting the header tuple.
    """
    return f"session_id={signed_value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={max_age}"


def build_session_clear_cookie() -> str:
    """Return the literal ``Set-Cookie`` value that clears the session cookie.

    Used by the middleware when the signed cookie is invalid, the session
    row is missing, or the row has expired. ``Max-Age=0`` is the
    cookie-deletion idiom; the same attributes are repeated so browsers
    match the existing cookie's path/security profile and actually drop
    it (per RFC 6265: attributes must match for deletion to take effect).
    """
    return "session_id=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"


# Phase 8 TODO: schedule a periodic
#     DELETE FROM sessions WHERE expires_at < now()
# job via APScheduler. The expires_at btree index from migration
# p1_sessions makes this cheap. See RESEARCH §5.

__all__ = [
    "SESSION_LIFETIME_DAYS",
    "SESSION_MAX_AGE_SECONDS",
    "build_session_clear_cookie",
    "build_session_cookie",
    "create_session",
    "delete_session",
    "get_session_by_id",
    "refresh_last_seen",
    "regenerate_session",
]
