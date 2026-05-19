"""FastAPI dependencies that hand route handlers a fresh DB session.

Two siblings live here, each owned by a different surface area:

* :func:`get_async_session` — yields an ``AsyncSession``. Used by Phase 2
  auth routes (the only async surface in the app today).
* :func:`get_session` — yields a sync :class:`sqlalchemy.orm.Session` from
  :data:`app.db.SessionLocal`. Used by Phase 4+ catalog routes per Phase 3
  D-07 ("sync DB for the catalog surface"). Synchronous because the catalog
  routes are CPU-bound on Jinja + Pydantic; ``AsyncSession`` adds ceremony
  without ROI at household scale.

Two design choices preserved from the async version:

* **Lazy import of ``async_session_factory``.** The factory currently lives
  at :mod:`app.main` (Phase 1 lock; ``app/main.py:88-95`` records the
  "future Phase 0 follow-up" relocation note). A top-level
  ``from app.main import async_session_factory`` would close a circular
  import: ``app.main → routers → app.dependencies.db → app.main``. Importing
  inside the generator body runs the lookup once per request — measurable
  but negligible at household scale (FOUND-04).

* **Fresh ``AsyncSession`` per request.** Routes need their own session
  with its own transaction scope, distinct from
  :class:`app.middleware.session.SessionMiddleware`'s session (which has
  already committed by the time the handler runs). A route that fails
  mid-body sees the implicit transaction rolled back when the
  ``async with`` exits.

Plan 02-07 / 02-08 will write ``db: AsyncSession = Depends(get_async_session)``
in every handler that touches the DB; Phase 4+ inherits the sync
:func:`get_session` for catalog routes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db import SessionLocal


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield a fresh :class:`AsyncSession` for the lifetime of the request.

    The factory is imported lazily inside the generator body to avoid a
    circular import (see module docstring). The ``yield`` (not ``return``)
    inside an :class:`AsyncIterator`-typed function is what makes this a
    FastAPI-compatible async-generator dependency: FastAPI inspects the
    callable, sees ``isasyncgenfunction`` is True, and wires the cleanup
    into the request lifecycle.
    """
    from app.main import async_session_factory

    async with async_session_factory() as session:
        yield session


def get_session() -> Iterator[Session]:
    """Yield a fresh sync :class:`Session` for the request lifetime.

    Phase 4+ catalog routes consume this dep; Phase 2 auth routes use
    :func:`get_async_session` instead. Sync per Phase 3 D-07 — catalog
    routes are CPU-bound on Jinja + Pydantic; AsyncSession adds
    ceremony without ROI at household scale.
    """
    with SessionLocal() as session:
        yield session


__all__ = ["get_async_session", "get_session"]
