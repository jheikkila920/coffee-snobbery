"""Wave 0 pytest scaffolding (Phase 0 env-var setup + Phase 1 fixtures).

Two responsibilities live here:

1. **Env-var bootstrap (Phase 0)** — ``app/config.py`` evaluates
   ``settings = Settings()`` at import time, so the env vars must be in
   ``os.environ`` BEFORE the first ``from app.config import ...`` import
   anywhere in the test process. We use ``os.environ.setdefault`` at module
   import time (before any pytest fixture runs) to guarantee that ordering.

2. **Shared fixtures (Phase 1, Plan 01-01)** — ``app``, ``client``,
   ``db_session``, ``forwarded_headers``. Every fixture wraps the dependency
   it points at in ``try/except ImportError`` (or equivalent) so that a
   missing Wave 1 symbol turns into a clean ``pytest.skip`` rather than a
   collection error. The Wave 0 contract is "every test file is collectable,
   even if most tests are skipped or red."

Note on ``app.main`` import: the module must NOT be imported at module level
here. ``app.main`` pulls in ``app.config``'s side-effecting ``settings``
instance plus Tailwind CSS discovery, both of which can raise. Importing
inside the fixture body keeps collection clean.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

# Wave 0 env-var stubs. Values are syntactically valid but not real secrets;
# the test suite does not perform encryption / decryption round-trips in Wave 0.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/test",
)
# 64-character urlsafe string — satisfies Settings.APP_SECRET_KEY.min_length=32.
os.environ.setdefault("APP_SECRET_KEY", "x" * 64)
# 44-character urlsafe-base64-shaped string — valid Fernet key shape, suitable
# for Wave 0 (Phase 3 will replace with a real Fernet-generated key for its tests).
os.environ.setdefault(
    "APP_ENCRYPTION_KEY",
    "0123456789abcdef0123456789abcdef0123456789a=",
)


# --------------------------------------------------------------------------- #
# Shared fixtures (Plan 01-01)                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture
def app() -> Any:
    """The FastAPI app instance, lazily imported.

    Wrap the import in try/except so that:
    - missing Tailwind CSS hash (``RuntimeError`` from ``compute_tailwind_css_path``
      when the Dockerfile build hasn't produced ``app/static/css/tailwind.<hash>.css``)
      turns into a clean skip rather than a collection error;
    - missing Wave 1+ symbols in ``app.main`` (none today, but defensive) also skip.
    """
    try:
        from app.main import app as _app
    except RuntimeError as exc:
        pytest.skip(f"app.main import failed (likely Tailwind CSS missing): {exc}")
    except ImportError as exc:
        pytest.skip(f"app.main not importable (Wave 1 dependency missing): {exc}")
    return _app


@pytest.fixture
def client(app: Any) -> Iterator[Any]:
    """Sync ``starlette.testclient.TestClient`` wrapping the FastAPI app.

    A sync TestClient (FastAPI re-exports it from Starlette) is sufficient for
    Wave 0 — httpx async-client is unnecessary at this phase. Yields inside a
    context manager so FastAPI's lifespan startup/shutdown runs.

    Catches DB-side errors during lifespan startup (the Phase 0 ``/healthz``
    route triggers a ``SELECT 1`` at startup) and converts them to skips so
    unit-only runs without Postgres stay green.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import DBAPIError, OperationalError

    try:
        with TestClient(app) as _client:
            yield _client
    except (OperationalError, DBAPIError, ConnectionError, OSError) as exc:
        pytest.skip(f"TestClient startup failed (Postgres unreachable?): "
                    f"{type(exc).__name__}: {exc}")


@pytest.fixture
def db_session() -> Iterator[Any]:
    """Per-test transactional rollback DB session.

    Plan 01-01 lands the fixture *shape* (so tests reference it) but Phase 0's
    ``app.db`` ships only a SYNC ``SessionLocal`` (see ``app/db.py``). The
    async ``AsyncSession`` factory the plan references (``app.db:async_session_factory``)
    does not exist yet. Tests requesting this fixture skip cleanly until either
    Phase 7's async engine lands or a Wave 1 plan provides a sync-session
    equivalent under this name.
    """
    try:
        from app.db import async_session_factory  # type: ignore[attr-defined]
    except ImportError:
        pytest.skip(
            "db_session fixture requires app.db:async_session_factory "
            "(Phase 7 introduces async engine; Phase 0 ships sync-only)."
        )
        return  # pragma: no cover — pytest.skip raises

    # Reachable only once the symbol exists; intentional minimal body.
    session = async_session_factory()  # pragma: no cover
    try:  # pragma: no cover
        yield session
    finally:  # pragma: no cover
        # Real implementation will begin a transaction and roll back.
        try:
            session.close()
        except Exception:
            pass


@pytest.fixture
def forwarded_headers() -> dict[str, str]:
    """Simulated NGINX-rewritten proxy headers for tests that exercise SEC-04 / D-16.

    The Trusted-Proxy chain in production sets these on every request; tests
    that hit ``/debug/proxy`` or assert slowapi-keys-by-real-IP use this dict
    directly via ``client.get("/debug/proxy", headers=forwarded_headers)``.
    """
    return {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "203.0.113.7",
    }
