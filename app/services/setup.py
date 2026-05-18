"""First-admin creation with FOR UPDATE race protection (AUTH-01 / AUTH-02).

This module ships exactly one public coroutine — :func:`create_first_admin`
— that the ``/setup`` route handler (Plan 02-07) will call when a POST
arrives at the setup form. The function is the **race-protection seam**
named by AUTH-02: a concurrent second POST that races ours blocks on a
Postgres row-level exclusive lock until our transaction commits, then
observes ``setup_completed='true'`` and exits via the race-lost branch
(returns ``None`` — the route redirects to ``/login`` per D-01).

SQL contract (one implicit AsyncSession transaction, one commit)
----------------------------------------------------------------

1. ``SELECT * FROM app_settings WHERE key='setup_completed' FOR UPDATE``
   acquires a Postgres row-level exclusive lock. The lock is held until
   this transaction commits (RESEARCH §"SQLAlchemy 2.0 + AsyncSession +
   ``with_for_update()``", verified against psycopg 3.3 + Postgres 16).
   A concurrent second caller blocks on its own ``SELECT ... FOR UPDATE``
   for the same row until our COMMIT releases the lock.
2. ``INSERT INTO users (...)`` with ``is_admin=True`` and ``is_active=True``
   enforced **by this service** — the function signature has no
   ``is_admin`` parameter. The first user is always an admin; the form
   does not (and must not) carry an "I am admin" checkbox.
3. ``UPDATE app_settings SET value='true' WHERE key='setup_completed'``
   inside the same transaction. D-04 locks the same-transaction
   guarantee: a separate UPDATE after a separate INSERT would leave a
   window where the user row exists but the flag is still 'false',
   allowing a third concurrent caller to mint a second admin.
4. ``COMMIT`` — single commit; releases the row lock; INSERT and UPDATE
   land atomically.

Why the argon2 hash is computed INSIDE the FOR UPDATE lock
----------------------------------------------------------

:func:`hash_password` is ~100 ms (argon2id with m=65536, t=3, p=4 — see
``app.services.auth``). Performing it AFTER ``SELECT FOR UPDATE`` means
the lock is held for ~100 ms instead of microseconds — a concurrent
caller waits that long. At household scale (CLAUDE.md, "Core Value")
this is invisible: the realistic worst case is the original setup
attempt being retried in a second browser tab, i.e. at most two callers
during initial install. The alternative (hash BEFORE the SELECT FOR
UPDATE) widens the race window: caller A starts hashing, caller B
hashes, B finishes first, takes the lock, completes; A then takes the
lock, sees 'true', returns None — but A has already paid the 100 ms
argon2 cost on a wasted code path. The wait-inside-lock shape keeps
the wasted-work cost on the loser, where it belongs (RESEARCH §D-04
rationale, T-02-05-03 in 02-05-PLAN threat model — disposition: accept).

Why there is no ``async with db.begin():`` wrapper
--------------------------------------------------

The ``async_session_factory`` from ``app.main`` is the standard SQLAlchemy
2.0 ``async_sessionmaker`` with ``expire_on_commit=False`` (so the
returned :class:`User` keeps populated attributes after commit). The
implicit transaction begins on the first ``execute()`` and is closed by
``commit()`` / ``rollback()``. Wrapping the body in an explicit
``async with db.begin():`` would nest a SAVEPOINT — unnecessary and
slightly slower. See the analog
:func:`app.services.sessions.regenerate_session` which uses the same
pattern (delete + insert + single commit).

Returns
-------

- New :class:`User` row with ``id`` populated (via ``flush()`` BEFORE
  commit so the caller's audit-log emit can reference it) on the happy
  path.
- ``None`` if the race was lost (``setup_completed`` was already
  ``'true'`` when our ``SELECT FOR UPDATE`` returned). The caller —
  the ``/setup`` POST handler — translates ``None`` into a 302/303
  redirect to ``/login`` per D-01.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.user import User
from app.services.auth import hash_password


async def create_first_admin(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    plaintext_password: str,
) -> User | None:
    """One-transaction first-admin creation. Returns the new User or None on race.

    SQL flow (all inside one implicit ``AsyncSession`` transaction):

    1. ``SELECT * FROM app_settings WHERE key = 'setup_completed' FOR UPDATE``
       — Postgres row-level exclusive lock. A concurrent second caller
       blocks on this SELECT until the first transaction commits. When
       unblocked, the second caller sees ``value='true'`` and returns
       ``None`` — AUTH-02 race protection.
    2. ``INSERT INTO users (username, email, password_hash, is_admin, is_active)``.
       ``is_admin=True`` and ``is_active=True`` are enforced by this
       service (NOT taken from input) — the first user is always an
       active admin and the form has no admin checkbox.
    3. ``UPDATE app_settings SET value='true' WHERE key='setup_completed'``.
    4. ``COMMIT`` — single commit; releases the row lock; both INSERT
       and UPDATE land atomically.

    The ``hash_password`` call (argon2id, ~100 ms) is invoked inline,
    INSIDE the FOR UPDATE lock. At household scale this is acceptable;
    see the module docstring for the rationale.

    Args:
        db: An open ``AsyncSession`` — typically yielded by
            :func:`app.dependencies.db.get_async_session`. The caller
            owns the session lifecycle; this function commits but does
            not close.
        username: Already-validated username (Pydantic schema in Plan
            02-07 enforces shape; CITEXT column enforces uniqueness).
        email: Already-validated email (NOT NULL at this layer — the
            ``users.email`` column is nullable but the ``/setup`` form
            REQUIRES it per CONTEXT D-02). Pass a plain string.
        plaintext_password: Already-length-validated plaintext (Pydantic
            enforces the 12-char minimum at the route layer). Hashed
            here via ``app.services.auth.hash_password``.

    Returns:
        New :class:`User` row with ``id`` populated (via ``flush()``
        before commit) on success; ``None`` if the race was lost.
    """
    # 1. SELECT ... FOR UPDATE on the setup_completed row. Phase 0's
    #    initial migration seeded this row with value='false', so
    #    scalar_one() is guaranteed to find it.
    stmt = select(AppSetting).where(AppSetting.key == "setup_completed").with_for_update()
    result = await db.execute(stmt)
    setting = result.scalar_one()

    if setting.value == "true":
        # Race lost — a concurrent /setup POST already completed setup
        # before our FOR UPDATE was granted. Roll back to release the
        # lock immediately (no rows inserted, but psycopg has started an
        # implicit transaction). The caller redirects to /login per D-01.
        await db.rollback()
        return None

    # 2. INSERT users — is_admin / is_active enforced by service.
    new_user = User(
        username=username,
        email=email,
        password_hash=hash_password(plaintext_password),
        is_admin=True,
        is_active=True,
    )
    db.add(new_user)
    # Flush so new_user.id is populated for the caller's audit-log emit;
    # still inside the same transaction (no commit yet).
    await db.flush()

    # 3. UPDATE the flag — same transaction, no separate commit.
    await db.execute(
        update(AppSetting).where(AppSetting.key == "setup_completed").values(value="true")
    )

    # 4. Single commit — atomic across INSERT and UPDATE; releases the
    #    FOR UPDATE lock; concurrent waiters unblock and see 'true'.
    await db.commit()

    # User row remains attached + populated after commit because
    # async_session_factory uses expire_on_commit=False (app/main.py:96).
    return new_user


__all__ = ["create_first_admin"]
