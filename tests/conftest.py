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

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio

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


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Clear slowapi's in-memory bucket before each test.

    Without this, a test that intentionally exceeds the rate limit (e.g.,
    ``test_rate_limit`` in test_csp_report.py) leaves the limiter's storage
    populated. Subsequent tests in the same pytest session hit the limiter
    and receive 429s on requests they expected to succeed. The limiter is
    a module-level singleton (``app.rate_limit.limiter``); resetting it per
    test isolates each test's rate-limit state without rebuilding the app.
    """
    yield
    try:
        from app.rate_limit import limiter
        limiter.reset()
    except (ImportError, AttributeError):
        # Wave 1 dependency not present (Plan 03 / Plan 07); harmless.
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


# --------------------------------------------------------------------------- #
# Phase 2 fixtures (Plan 02-01)                                               #
# --------------------------------------------------------------------------- #
#
# Wave 0 of Phase 2 lands the four fixtures every other Phase-2 plan depends
# on. Each fixture wraps its Phase-2 dependency imports in ``try/except
# ImportError`` so the conftest stays collectable BEFORE Plans 02 / 04 / etc.
# land the symbols the seeded fixtures reach for. The contract is "every
# test file is collectable, even if most tests skip" — same as Wave 0 of
# Phase 1.


@pytest_asyncio.fixture
async def async_client(app: Any) -> AsyncIterator[Any]:
    """``httpx.AsyncClient`` wired to the FastAPI ASGI app via ``ASGITransport``.

    Required by AUTH-02 (concurrent ``/setup`` race) — the test fires two
    ``async_client.post('/setup', ...)`` coroutines via ``asyncio.gather``
    and asserts exactly one wins the ``FOR UPDATE`` lock. A sync
    ``TestClient`` cannot exercise that path because it serialises
    requests.

    Lazy-imports ``httpx`` so a missing dev dep yields a clean skip rather
    than a collection error (httpx is in requirements.txt as of Phase 0,
    so this is defensive — not expected to fire).
    """
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed (Phase 0 requirement)")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
def fresh_db() -> Iterator[None]:
    """Reset ``users`` + ``app_settings.setup_completed`` before each test.

    AUTH-01 (zero-users happy path) and AUTH-02 (concurrent setup race)
    BOTH require ``setup_completed='false'`` and zero rows in ``users``
    at the start of the test. Without this autouse reset, a successful
    AUTH-01 leaves a user row behind that breaks AUTH-02 on the same
    pytest session — and vice versa.

    Autouse for the whole test directory so every Phase-2 test starts
    clean. Tests that don't touch the DB pay only the TRUNCATE cost
    (~1 ms on an empty users table). The DB-connection block is wrapped
    in ``try/except`` so unit-only runs (Postgres unreachable) don't
    error here — the test that genuinely needs the DB will skip via
    its own ``try/except ImportError`` / ``OperationalError`` probe.

    TRUNCATE on ``users`` cascades to ``sessions`` via the FK from
    ``sessions.user_id``; the explicit ``DELETE FROM sessions`` after
    the TRUNCATE is a defensive belt-and-braces in case the schema
    evolves to drop the cascade.
    """
    try:
        from app.db import engine
    except ImportError:
        yield
        return
    try:
        from sqlalchemy import text
    except ImportError:
        yield
        return

    # Fast-fail probe — psycopg's default connect timeout is OS-level
    # (~30s on Linux, longer on Windows). When pytest runs on the host
    # (no docker compose), every test would otherwise pay that timeout
    # via the autouse path. A 0.5s TCP probe matches the household-scale
    # "if Postgres isn't already reachable, skip cleanly" intent without
    # adding any cost in docker (where the loopback socket is instant).
    if not _postgres_reachable():
        yield
        return

    try:
        with engine.begin() as conn:
            # NOTE: TRUNCATE ... CASCADE in Postgres truncates every referencing
            # table regardless of FK delete_rule. `app_settings.updated_by_user_id`
            # FKs to `users.id` (ON DELETE SET NULL), so a TRUNCATE on users
            # CASCADE would wipe the 19 seeded app_settings rows — breaking
            # tests/test_migrations.py::test_app_settings_seeded_with_19_rows.
            # Use explicit DELETE so ON DELETE SET NULL is honored.
            conn.execute(text("DELETE FROM sessions"))
            conn.execute(text("DELETE FROM users"))
            conn.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
            conn.execute(
                text("UPDATE app_settings SET value='false' WHERE key='setup_completed'")
            )
    except Exception:
        # Postgres reachable but a table doesn't exist yet (e.g., the
        # initial migration hasn't run in this test DB), or some other
        # transient failure. Tests that need a real DB skip on their
        # own probes; tests that don't are unaffected by the no-op.
        pass

    yield


def _postgres_reachable() -> bool:
    """Return True iff the configured Postgres host:port accepts a TCP connect.

    Parses the host/port out of ``settings.DATABASE_URL`` and tries a 0.5s
    socket connect. Returns False on any failure — DNS, refused, timeout,
    parse error. Used by :func:`fresh_db` to skip the per-test TRUNCATE
    when running on a host without docker compose.
    """
    try:
        from urllib.parse import urlparse

        from app.config import settings
    except ImportError:
        return False

    try:
        parsed = urlparse(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
    except Exception:
        return False

    import socket

    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except (OSError, socket.timeout):
        return False


def _seed_user(*, is_admin: bool) -> dict[str, Any]:
    """Create a ``User`` + session row; return ``{user, session_id, signed_cookie}``.

    Composition helper shared by :func:`seeded_admin_user` and
    :func:`seeded_regular_user`. Pulls the password-hashing helper
    (Plan 02-02 — ``app.services.auth``), the session-mint helper
    (Phase 1 — ``app.services.sessions.regenerate_session``), and the
    cookie signer (Phase 1 — ``app.signing.sign_session_id``).

    Runs the async insert via ``asyncio.run`` because the calling
    fixtures are SYNC — they support sync ``TestClient`` tests, not
    async tests. ``asyncio.run`` opens a fresh event loop per call,
    which is fine because pytest-asyncio only owns a loop during async
    tests; sync fixtures execute outside any pytest-managed loop.
    """
    from app.main import async_session_factory
    from app.models.user import User
    from app.services.auth import hash_password
    from app.services.sessions import regenerate_session
    from app.signing import sign_session_id

    async def _do() -> dict[str, Any]:
        async with async_session_factory() as db:
            suffix = uuid.uuid4().hex[:8]
            uname = f"admin-{suffix}" if is_admin else f"user-{suffix}"
            user = User(
                username=uname,
                email=f"{uname}@example.com",
                password_hash=hash_password("twelve-chars-min-password"),
                is_admin=is_admin,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            session_id = await regenerate_session(db, None, user.id)
            await db.refresh(user)
            return {
                "user": user,
                "session_id": session_id,
                "signed_cookie": sign_session_id(session_id),
            }

    return asyncio.run(_do())


@pytest.fixture
def seeded_admin_user() -> dict[str, Any]:
    """Create an ``is_admin=true`` user + live session.

    Returns ``{"user": User, "session_id": uuid.UUID, "signed_cookie": str}``.
    Tests pass ``cookies={"session_id": seeded_admin_user["signed_cookie"]}``
    to ``client.get("/admin")`` to exercise the AUTH-09 admin-gate path.

    Skips if either the Phase-2 ``hash_password`` (Plan 02) or the
    Phase-1 ``regenerate_session`` is unavailable. The cookie signer
    (``app.signing.sign_session_id``) lands in Phase 1 so is not
    probed separately.
    """
    try:
        from app.services.auth import hash_password  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.services.auth.hash_password (Plan 02)")
    try:
        from app.services.sessions import regenerate_session  # noqa: F401
    except ImportError:
        pytest.skip("Phase 1 dependency: app.services.sessions.regenerate_session")
    return _seed_user(is_admin=True)


@pytest.fixture
def seeded_regular_user() -> dict[str, Any]:
    """Create an ``is_admin=false`` user + live session.

    Same shape as :func:`seeded_admin_user`. Exercises the AUTH-09
    "non-admin → 403" branch of the three-state admin-gate test.
    """
    try:
        from app.services.auth import hash_password  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.services.auth.hash_password (Plan 02)")
    try:
        from app.services.sessions import regenerate_session  # noqa: F401
    except ImportError:
        pytest.skip("Phase 1 dependency: app.services.sessions.regenerate_session")
    return _seed_user(is_admin=False)


# --------------------------------------------------------------------------- #
# Phase 3 fixtures (Plan 03-06)                                               #
# --------------------------------------------------------------------------- #
#
# Phase 3 tests use real ``Fernet.generate_key()`` keys per test (CONTEXT.md
# ``<specifics>`` — "Tests use Fernet.generate_key() per test — no shared
# keys, no respx"). The three fixtures below give tests three layers of
# convenience:
#
# - ``fernet_key`` returns raw ``bytes`` for tests that need the byte form.
# - ``fernet_key_str`` returns the ASCII string form for env-var assignment
#   via ``monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", ...)``.
# - ``monkeypatched_app_encryption_key`` patches the config AND reloads
#   ``app.services.encryption`` so its module-level ``_multi_fernet`` is
#   rebuilt with the fresh key. The reload mechanism is locked per
#   CONTEXT.md ``<specifics>`` (planner pick between module reload vs a
#   ``_rebuild_multi_fernet()`` helper — module reload wins because it keeps
#   the production module's public surface unchanged).


@pytest.fixture
def fernet_key() -> bytes:
    """Fresh Fernet key per test (CONTEXT.md <specifics> — no shared keys)."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key()


@pytest.fixture
def fernet_key_str(fernet_key: bytes) -> str:
    """ASCII str form of the per-test Fernet key for env-var assignment."""
    return fernet_key.decode("ascii")


@pytest.fixture
def monkeypatched_app_encryption_key(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> str:
    """Patch ``APP_ENCRYPTION_KEY`` and rebuild encryption's ``_multi_fernet``.

    Returns the patched key string so the test can read it back. After the
    test, ``monkeypatch`` restores the original env value; the module's
    ``_multi_fernet`` stays rebuilt with the test key, which is harmless
    because every Phase 3 test that touches the singleton requests this
    fixture (or its own override).

    Uses ``importlib.reload`` per CONTEXT.md ``<specifics>`` — the locked
    rebuild mechanism. The alternative ``_rebuild_multi_fernet()`` helper
    inside the module is rejected because it pollutes the module's public
    surface.
    """
    import importlib

    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", fernet_key_str)
    import app.services.encryption as enc_mod

    importlib.reload(enc_mod)
    return fernet_key_str
