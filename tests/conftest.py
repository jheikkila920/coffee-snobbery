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
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio

# D-02: CI skip-enforcement gate.
# When SNOB_CI=1 (e.g., GitHub Actions, docker-compose test profile),
# Postgres-dependent fixture skips become hard failures so "green-by-skip"
# cannot masquerade as a passing gate run.
_CI_MODE = os.environ.get("SNOB_CI") == "1"


def _require_postgres(reason: str) -> None:
    """Fail in CI (SNOB_CI=1) instead of skipping when Postgres is unreachable.

    Use in critical-path fixtures in place of bare ``pytest.skip(reason)`` so
    the Phase 12 ship gate surfaces missing Postgres as a real failure rather
    than hollow green.
    """
    if _CI_MODE:
        pytest.fail(f"SNOB_CI=1 but Postgres unreachable: {reason}")
    else:
        pytest.skip(reason)


# Wave 0 env-var stubs + dedicated test-database guard.
#
# app/config.py evaluates ``settings = Settings()`` at import and app/db.py binds
# its engine to ``settings.DATABASE_URL``; the destructive autouse ``fresh_db``
# fixture below issues DELETE/ALTER through that engine. In the app container
# POSTGRES_DB and DATABASE_URL are ALREADY set to the LIVE database (e.g.
# "snobbery"), so a plain ``setdefault`` is a no-op there — which previously let
# the suite TRUNCATE the live DB on every in-container run. Force a sibling
# "<db>_test" database on the SAME server BEFORE any ``from app...`` import so
# settings, the engine, and alembic env.py all resolve the test DB.
# ``_provision_test_db`` (below) creates + migrates it; ``fresh_db`` carries a
# second interlock that refuses to mutate any non-"*test*" database.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

_app_database_url = os.environ.get("DATABASE_URL")
if _app_database_url:
    _parsed_url = urlparse(_app_database_url)
    _test_db_name = _parsed_url.path.lstrip("/") or "test"
    if "test" not in _test_db_name.lower():
        _test_db_name = f"{_test_db_name}_test"
    os.environ["DATABASE_URL"] = urlunparse(_parsed_url._replace(path=f"/{_test_db_name}"))
    os.environ["POSTGRES_DB"] = _test_db_name
else:
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
        # Under SNOB_CI=1 the workflow builds Tailwind before pytest, so a missing
        # hash here means a broken gate, not "not built yet" — fail, never skip
        # (D-02: no hollow green). Locally without the build, skip remains correct.
        if _CI_MODE:
            pytest.fail(f"SNOB_CI=1 but app.main import failed (Tailwind CSS missing?): {exc}")
        pytest.skip(f"app.main import failed (likely Tailwind CSS missing): {exc}")
    except ImportError as exc:
        if _CI_MODE:
            pytest.fail(f"SNOB_CI=1 but app.main not importable: {exc}")
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
        # _require_postgres fails under SNOB_CI=1 (real gate break) and skips
        # otherwise — so client-dependent HARD tests (e.g. the happy-path smoke)
        # cannot go hollow-green in CI when Postgres is down (D-02).
        _require_postgres(
            f"TestClient startup failed (Postgres unreachable?): {type(exc).__name__}: {exc}"
        )


@pytest.fixture
def authed_client(app: Any, seeded_admin_user: dict[str, Any]) -> Iterator[Any]:
    """``TestClient`` with a valid session cookie + HMAC-signed ``csrftoken``.

    Mirrors ``tests/phase_04/conftest.py::authed_client`` so top-level tests
    (e.g. ``tests/test_coffee_origins.py``) can hit auth-gated routes without
    living under ``phase_04/``.

    The ``csrftoken`` is primed by issuing a GET request that coaxes the
    starlette-csrf middleware to mint a real HMAC-signed token. The middleware
    only mints a new token when no ``csrftoken`` cookie is present, so we must
    NOT pre-populate a placeholder. The resulting token is then set as both
    the cookie AND the ``X-CSRF-Token`` default header so POST endpoints pass
    the double-submit-cookie check. This mirrors the ``_prime_csrf`` helper
    used in ``tests/phase_04/``.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as _client:
        _client.cookies.set("session_id", seeded_admin_user["signed_cookie"])
        # Prime a real HMAC-signed CSRF token by issuing a GET (no csrftoken
        # cookie present so the middleware sets a fresh Set-Cookie on the response).
        primer = _client.get("/")
        token = primer.cookies.get("csrftoken") or _client.cookies.get("csrftoken")
        if not token:
            pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
        _client.cookies.set("csrftoken", token)
        _client.headers["X-CSRF-Token"] = token
        yield _client


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


@pytest.fixture(scope="session", autouse=True)
def _provision_test_db() -> Iterator[None]:
    """Create + migrate the dedicated "<db>_test" database once per session.

    Guarantees the suite runs against an isolated test database, never the live
    app DB. A clean no-op when Postgres is unreachable or provisioning fails —
    DB-dependent tests then skip via their own probes rather than touching
    production data. Runs before the function-scoped ``fresh_db`` reset.
    """
    if not _postgres_reachable():
        yield
        return
    try:
        import psycopg

        from app.config import settings as _settings
    except Exception:
        yield
        return

    _parsed = urlparse(_settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
    _test_db = _parsed.path.lstrip("/")
    if "test" not in _test_db.lower():
        # Refuse to CREATE/migrate against a non-test database.
        yield
        return

    _admin_url = urlunparse(_parsed._replace(path="/postgres"))
    try:
        with psycopg.connect(_admin_url, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (_test_db,)
            ).fetchone()
            if exists is None:
                conn.execute(f'CREATE DATABASE "{_test_db}"')
    except Exception:
        yield
        return

    try:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
    except Exception:
        # Schema not provisioned; DB-dependent tests skip on their own probes.
        pass

    yield


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

    # Safety interlock (defense in depth): NEVER issue the destructive reset
    # against a non-test database. Even if the env-forcing at module top is
    # somehow bypassed, this stops the suite from wiping the live app DB.
    try:
        from app.config import settings as _settings

        _active_db = urlparse(
            _settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        ).path.lstrip("/")
    except Exception:
        _active_db = ""
    if "test" not in _active_db.lower():
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
            conn.execute(text("UPDATE app_settings SET value='false' WHERE key='setup_completed'"))
    except Exception:
        # Postgres reachable but a table doesn't exist yet (e.g., the
        # initial migration hasn't run in this test DB), or some other
        # transient failure. Tests that need a real DB skip on their
        # own probes; tests that don't are unaffected by the no-op.
        pass

    yield


def _require_cafe_logs_table() -> None:
    """Skip if the cafe_logs table is not present.

    Prevents tests from silently passing when the p16_cafe_logs migration has
    not been applied (project memory: tests-pass-by-skip-mask-green). Run
    ``pytest -rs`` during gsd-validate-phase to surface every skip.

    The skip message includes the migration revision name so ``-rs`` output
    is actionable: "cafe_logs table not present — migration p16_cafe_logs
    not applied".
    """
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.cafe_logs')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("cafe_logs table not present — migration p16_cafe_logs not applied")


def _require_water_profiles_table() -> None:
    """Skip if the water_profiles table is not present (Phase 20 migration not run).

    Used by Phase 20 tests that assert water_profile endpoint + migration behavior.
    Calling this from the test body keeps the test file free of pytest.skip(
    calls while still surface a clear, actionable skip message under ``pytest -rs``.

    Added Phase 20 Plan 01 — mirrors the _require_cafe_logs_table pattern.
    """
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — water profile tests need the DB")
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.water_profiles')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("water_profiles table not present — p20_water_profiles migration not applied")


def _require_brew_sessions_with_water_profile_id() -> None:
    """Skip if brew_sessions.water_profile_id column is absent (Phase 20 migration not run).

    Used by Phase 20 brew-session timing-column introspection tests.
    """
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — timing column test needs the DB")
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='brew_sessions' "
                    "  AND column_name='water_profile_id'"
                )
            ).fetchone()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip(
            "brew_sessions.water_profile_id column absent — "
            "p20_water_profiles migration not applied"
        )


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
    except (TimeoutError, OSError):
        return False


@pytest.fixture(scope="module", autouse=True)
def _reset_catalog_tables() -> Iterator[None]:
    """Truncate catalog + brew tables after each test module (D-01).

    Teardown-only (yields first, cleans up after). Scope=module keeps
    per-test cost near zero while guaranteeing each test module starts
    with an empty catalog — no cross-module FK pollution.

    FK-safe TRUNCATE order (RESTRICT constraints):
      brew_sessions.coffee_id / bag_id RESTRICT → coffees / bags
      bags.coffee_id RESTRICT → coffees
    So: brew_sessions → bags → coffees → equipment → recipes → roasters → flavor_notes.

    NEVER TRUNCATEs ``users`` — app_settings.updated_by_user_id has
    ON DELETE SET NULL; a CASCADE on users would wipe the 19-row seed and
    break test_app_settings_seeded_with_19_rows. ``fresh_db`` owns users/sessions.

    Safety interlock: refuses to TRUNCATE any database whose name does not
    contain "test" (verbatim from fresh_db, lines 319-332).
    """
    yield  # teardown-only; setup is a no-op

    if not _postgres_reachable():
        return

    # Safety interlock — replicated verbatim from fresh_db.
    try:
        from app.config import settings as _s

        _active_db = urlparse(
            _s.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        ).path.lstrip("/")
    except Exception:
        _active_db = ""
    if "test" not in _active_db.lower():
        return

    try:
        from sqlalchemy import text

        from app.db import engine

        with engine.begin() as conn:
            # FK-safe order: children before parents.
            conn.execute(text("TRUNCATE brew_sessions RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE bags RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE coffees RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE equipment RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE recipes RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE roasters RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE flavor_notes RESTART IDENTITY CASCADE"))
            # Phase 20: water_profiles is a shared catalog; brew_sessions.water_profile_id
            # is ON DELETE SET NULL so brew_sessions must be truncated first (done above).
            conn.execute(text("TRUNCATE TABLE water_profiles RESTART IDENTITY CASCADE"))
    except Exception:
        # Table not yet created (migration not run) or transient error — no-op.
        pass

    # Clear the in-memory app_settings cache so test_setup_concurrent_race
    # does not inherit a stale setup_completed=true from a prior module.
    try:
        import app.services.settings as _svc

        _svc._cache.clear()  # type: ignore[attr-defined]
    except Exception:
        pass


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
    if not _postgres_reachable():
        _require_postgres("Postgres not reachable (seeded_admin_user)")
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
    if not _postgres_reachable():
        _require_postgres("Postgres not reachable (seeded_regular_user)")
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
def monkeypatched_app_encryption_key(monkeypatch: pytest.MonkeyPatch, fernet_key_str: str) -> str:
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


# --------------------------------------------------------------------------- #
# Phase 8 fixtures (Plan 08-01)                                               #
# --------------------------------------------------------------------------- #
#
# Two reusable fixtures consumed by tests/test_scheduler.py (Plans 08-02/03)
# and tests/test_backup.py (Plan 08-02).
#
# Both are wrapped in try/except ImportError so the conftest stays collectable
# before Plans 08-02/03 land their symbols. The Wave 0 contract is unchanged:
# "every test file is collectable, even if most tests are skipped."


@pytest.fixture
def sync_db() -> Iterator[Any]:
    """Yield a sync ``Session`` from ``app.db.SessionLocal``.

    Mirrors the ``fresh_db`` skip pattern: if Postgres is unreachable the
    test is skipped rather than erroring. Tests that need to seed users /
    recommendations and read back ``app_settings`` rows use this fixture.

    T-08-01 interlock: the existing ``_postgres_reachable()`` + ``"test" in
    db_name`` guard in ``fresh_db`` applies here too — the fixture only
    yields a session against a ``*test*`` database, never the live app DB.
    """
    try:
        from app.db import SessionLocal
    except ImportError:
        pytest.skip("app.db.SessionLocal not importable (Phase 0 dependency)")
        return  # pragma: no cover

    if not _postgres_reachable():
        _require_postgres("Postgres not reachable (sync_db)")
        return  # pragma: no cover

    # Safety interlock: refuse to yield a session against the live DB.
    try:
        from urllib.parse import urlparse as _urlparse

        from app.config import settings as _settings

        _active_db = _urlparse(
            _settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        ).path.lstrip("/")
    except Exception:
        _active_db = ""
    if "test" not in _active_db.lower():
        _require_postgres("sync_db refuses to connect to a non-test database (T-08-01)")
        return  # pragma: no cover

    with SessionLocal() as session:
        yield session


@pytest.fixture
def mock_regenerate(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a factory that patches ``app.services.ai_service.regenerate``.

    Usage in tests::

        async def test_something(mock_regenerate):
            patch = mock_regenerate("generated")  # all users return "generated"
            # or: mock_regenerate({"1": "generated", "2": "skipped"})

        # After ``await patch(user_id, ...)`` returns, assert force=False.

    The AI refresh job (Plan 08-03) calls the async ``regenerate()``. The mock
    is an ``AsyncMock`` so it is awaitable. The factory enforces that
    ``force=False`` is asserted on every call — this is the highest-risk
    behavior per 08-VALIDATION.md §"Highest-Risk Behaviors to Validate" #4:
    the scheduler must NEVER call ``regenerate()`` with ``force=True``, which
    would bypass the signature cost-control.
    """
    try:
        from unittest.mock import AsyncMock

        import app.services.ai_service as _ai_mod
    except ImportError:
        pytest.skip("app.services.ai_service not importable (Phase 7 dependency)")
        return  # pragma: no cover

    def _factory(status_or_map: Any) -> AsyncMock:
        """Create and apply an AsyncMock for ``ai_service.regenerate``.

        Args:
            status_or_map: A single status string (all users get the same
                return value) or a dict mapping ``str(user_id)`` → status.
        """
        if isinstance(status_or_map, dict):
            status_map = status_or_map

            async def _side_effect(
                user_id: int,
                generated_by: str,
                *,
                db: Any,
                force: bool = False,
            ) -> str:
                # Highest-risk assertion: force must be False in the scheduler path.
                assert force is False, (
                    f"regenerate called with force=True for user_id={user_id}; "
                    "the scheduler must NEVER bypass the signature cost-control"
                )
                return status_map.get(str(user_id), "skipped")

            mock = AsyncMock(side_effect=_side_effect)
        else:
            fixed_status = status_or_map

            async def _side_effect_fixed(  # type: ignore[misc]
                user_id: int,
                generated_by: str,
                *,
                db: Any,
                force: bool = False,
            ) -> str:
                assert force is False, (
                    f"regenerate called with force=True for user_id={user_id}; "
                    "the scheduler must NEVER bypass the signature cost-control"
                )
                return fixed_status

            mock = AsyncMock(side_effect=_side_effect_fixed)

        monkeypatch.setattr(_ai_mod, "regenerate", mock)
        return mock

    return _factory
