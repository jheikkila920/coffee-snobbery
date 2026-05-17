"""/healthz smoke test (Phase 0 Plan 00-04 / FOUND-01 / CONTEXT D-08).

The /healthz route is DB-touching by design (CONTEXT D-08): it opens a
transaction, applies a per-transaction 2-second ``statement_timeout``, and
runs ``SELECT 1``. The TestClient construction triggers FastAPI's lifespan,
which itself performs a ``SELECT 1`` against the real engine — so this test
requires a live Postgres reachable at ``settings.DATABASE_URL``.

When Postgres is unreachable (unit-only test runs, CI sandboxes without the
compose stack up), we ``pytest.skip`` the whole test so the suite stays
green. The same skip pattern is used by ``tests/test_migrations.py`` — see
its module docstring for the rationale.

Plan 05's ``make smoke`` is the canonical environment where this test runs
against a live DB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_healthz_returns_ok_when_db_reachable() -> None:
    """``GET /healthz`` answers 200 ``{"status": "ok"}`` against a live DB.

    Constructs the TestClient as a context manager so lifespan startup runs
    (and lifespan shutdown runs on exit). Three skip paths keep the
    unit-only suite green outside the live compose stack:

    1. ``RuntimeError`` from :func:`app.main.compute_tailwind_css_path` —
       raised at app-import time when the Dockerfile build hasn't produced
       ``app/static/css/tailwind.<hash>.css`` yet (Plan 00-05 + Plan 00-04
       Dockerfile stage 1 own this artifact).
    2. ``OperationalError`` / ``DBAPIError`` during ``TestClient`` enter —
       Postgres not running locally (same pattern as
       ``tests/test_migrations.py``).
    3. ``ConnectionError`` / ``OSError`` from any lower-layer transport.
    """
    from sqlalchemy.exc import DBAPIError, OperationalError

    # Defer the import so the module-level Tailwind glob's RuntimeError
    # can be turned into a skip rather than a collection error.
    try:
        from app.main import app
    except RuntimeError as exc:
        pytest.skip(
            f"app.main import failed (likely Tailwind CSS missing — run "
            f"via `make smoke` after Dockerfile build): {exc}"
        )
        return  # pragma: no cover — pytest.skip raises

    try:
        client_cm = TestClient(app)
        with client_cm as client:
            response = client.get("/healthz")
    except (OperationalError, DBAPIError, ConnectionError, OSError) as exc:
        pytest.skip(f"Postgres unreachable for /healthz smoke: {type(exc).__name__}: {exc}")
        return  # pragma: no cover — pytest.skip raises

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}
