"""Alembic environment for SQLAlchemy 2.0 + psycopg 3.

This file is the bridge between Alembic's CLI and the project's
runtime configuration. It deliberately reads the database URL from
``app.config.settings`` (which is the SOLE consumer of ``os.environ``
per FOUND-10) — never from Alembic's own config file.

Importing ``app.models`` populates ``Base.metadata`` with every model
module's tables before ``target_metadata`` is read by autogenerate
(Plan 03 ships a hand-authored first migration; autogenerate becomes
the canonical workflow in Phase 1+).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401 — registers every model with Base.metadata
from app.config import settings
from app.db import Base

# Alembic Config object — gives access to alembic.ini values.
config = context.config

# Configure stdlib logging from alembic.ini if a [loggers] section is present.
# Phase 0's alembic.ini intentionally omits logging config (structlog owns
# the project's logging story); this branch is defensively present in case
# Phase 12 hardening adds logger overrides.
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except KeyError:
        # alembic.ini has no [loggers] / [handlers] / [formatters] sections —
        # that's expected for Phase 0. Stdlib logging keeps its defaults.
        pass

# Override alembic.ini's empty sqlalchemy.url with the runtime DATABASE_URL.
# pydantic-settings (app/config.py) already resolved the env var exactly once
# at process start; we never read os.environ here.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# target_metadata is what autogenerate compares against the live DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout, no DB connection.

    Useful for code review and dry-runs. Not used by the production
    entrypoint, which always runs ``alembic upgrade head`` against the
    live ``coffee-snobbery-db`` service.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection.

    Uses ``pool.NullPool`` so each migration run opens a fresh connection
    and disposes it on exit — appropriate for short-lived ``alembic upgrade``
    invocations from ``entrypoint.sh``.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
