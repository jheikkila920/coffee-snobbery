"""Wave 0 pytest scaffolding.

This conftest sets the env vars ``app/config.py``'s ``Settings`` instance
needs in order to construct without raising. Plan 03 will extend this with
a real SQLAlchemy session fixture (transactional rollback per test) once
the engine module lands.

Note: ``app/config.py`` evaluates ``settings = Settings()`` at import time,
so the env vars must be in ``os.environ`` BEFORE the first
``from app.config import ...`` import anywhere in the test process. We use
``os.environ.setdefault`` at module import time (before any pytest fixture
runs) to guarantee that ordering.
"""

from __future__ import annotations

import os

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
