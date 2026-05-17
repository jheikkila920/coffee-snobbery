"""``sessions`` table — table-backed session store for AUTH-05.

Schema is locked to **exactly five columns** per CONTEXT D-07. No ``ip``,
``user_agent``, or ``device_label`` — the minimal-storage footprint is the
mitigation for T-04-05 (information disclosure from a session-table dump).

The cookie that the browser holds is *just the signed session_id*; this row
is the authoritative expiry source. See ``app.middleware.session`` for the
request-time flow and ``app.services.sessions`` for the helpers Phase 2's
``/login`` and ``/logout`` will call.

No ORM relationship to :class:`app.models.user.User` at this phase: the
middleware joins explicitly via ``select(User).where(User.id == ...)``. This
avoids the import-time circularity that an ``eagerly=joined`` relationship
would create, and keeps the model module dependency-light for Phase 0/1
import order.

CLAUDE.md "Stack invariants": SQLAlchemy 2.0 typed ``Mapped[...]`` columns,
``select()``/``delete()`` constructs only — no legacy ``Query`` API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Session(Base):
    """A live authenticated browser session.

    The PK ``session_id`` is the value (signed) carried in the
    ``session_id`` cookie. ``last_seen`` is write-throttled by
    :mod:`app.middleware.session` to once per 5 minutes per session; the
    sliding ``expires_at`` window is refreshed at the same cadence.

    ``user_id`` is :class:`sqlalchemy.BigInteger` to match
    :class:`app.models.user.User.id` (also BigInteger). Using ``Integer``
    here would silently truncate at 2^31 and silently break the FK on
    actual large IDs.
    """

    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
