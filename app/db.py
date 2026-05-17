"""SQLAlchemy 2.0 sync engine + sessionmaker with locked pool knobs.

The pool knobs are NOT defaults — they are explicit choices for the
single-worker household-scale shape documented in CONTEXT D-10 and
PITFALL SH-2. The most surprising knob is ``pool_timeout=5`` (vs. the
SQLAlchemy default of 30): we fail-fast on pool exhaustion rather than
block a request for half a minute. ``pool_pre_ping=True`` defends against
stale connections after long idle (NGINX keepalive can hold the upstream
TCP socket open longer than Postgres's ``idle_in_transaction_session_timeout``).

Phase 7 will introduce an async engine for AI service code (see RESEARCH
§3.3 — sync handlers + sync sessions are the default; async is reserved
for AI calls). Phase 0 ships only the sync path.

Anything that needs a DB session should import ``SessionLocal`` and use
the context-manager pattern::

    from app.db import SessionLocal

    with SessionLocal() as session:
        result = session.execute(select(User).where(...)).all()

For FastAPI dependencies, Phase 1 will wrap this in a generator. Phase 0
does not yet have routes that need a DB session — but ``/healthz`` (Plan 04)
will be the first consumer.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base

# Engine pool knobs are LOCKED. Do not change without updating CONTEXT D-10
# and PITFALL SH-2 — and run the pool exhaustion smoke test in Plan 05
# afterward (Phase 0's single-worker household scale assumption is the
# load-bearing constraint).
engine = create_engine(
    settings.DATABASE_URL,  # postgresql+psycopg://USER:PASS@coffee-snobbery-db:5432/DB
    pool_size=10,
    max_overflow=5,
    pool_timeout=5,  # fail-fast vs. SQLAlchemy default of 30s
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,  # never True — would log bound parameters (potential PII leak)
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def dispose_engine() -> None:
    """Close every checked-in connection. Call from FastAPI ``lifespan`` shutdown."""
    engine.dispose()


__all__ = ["Base", "engine", "SessionLocal", "dispose_engine"]
