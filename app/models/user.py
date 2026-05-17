"""``users`` table — referenced by ``ai_recommendations`` and ``wishlist_entries``.

Phase 0 ships the schema; Phase 2 wires the ``/setup`` route, argon2id
verification, and the admin user-management surface. Column choices below are
the planner's "Claude's Discretion" finals from
``.planning/phases/00-foundation/00-CONTEXT.md``:

* ``username`` is ``CITEXT UNIQUE NOT NULL`` (FOUND-06 — case-insensitive
  uniqueness; "Admin" and "admin" collide).
* ``email`` is ``CITEXT NULL`` with a *partial* unique index
  (``WHERE email IS NOT NULL``) — multiple NULLs are allowed, but if a value
  is set it must be unique case-insensitively.
* ``password_hash`` is ``TEXT NOT NULL`` (Phase 2 stores the argon2id encoded
  hash here).
* Booleans use Postgres-portable ``server_default=text("false"/"true")``.

CITEXT, pg_trgm, and unaccent are installed by ``0001_initial.py`` BEFORE
this table is created (FOUND-06; CONTEXT D-03).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Identity, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class User(Base):
    """A Snobbery household user. Created via admin or ``/setup``; never self-registered."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    username: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    # email NULL is allowed; partial unique index in __table_args__ enforces
    # uniqueness only when value is provided (CONTEXT — multiple NULLs OK).
    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        # Partial unique index: enforce uniqueness only when email is set.
        Index(
            "ix_users_email",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )
