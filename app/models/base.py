"""SQLAlchemy 2.0 declarative base.

All ORM models in :mod:`app.models` inherit from :class:`Base`. This module
keeps the declarative base in a tiny module of its own so the model modules
and ``app.db`` can both import it without a circular dependency.

The Alembic ``env.py`` (Plan 03) reads ``Base.metadata`` as ``target_metadata``;
every model module must be imported (see ``app/models/__init__.py``) before
``env.py`` queries the metadata so autogenerate sees the full schema.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every Snobbery ORM model."""

    pass
