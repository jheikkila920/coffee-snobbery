"""``brew_drafts`` table — server-side backstop for the in-progress brew form.

BREW-06/07 + MX-5: the brew form autosaves to ``localStorage`` as the primary
draft store, but iOS Safari ITP evicts ``localStorage`` after 7 days of
non-installed inactivity. This table is the server backstop: one row per user
(``user_id`` UNIQUE), an upsert-on-blur write, and a clear-on-submit/logout
delete. Reconciliation order (BREW-07): ``localStorage`` is primary; the server
draft is restored only when ``localStorage`` is empty.

``user_id`` uses ``ondelete="CASCADE"`` — this is the ONE place CASCADE is
correct in Phase 5. A draft is meaningless without its user; unlike
``brew_sessions`` (RESTRICT, history is precious), an orphaned draft has no
value and should disappear with the user.

``payload`` is JSONB (mirrors ``recipes.steps``) holding serialized form state:
per-field values, per-field touched-state, and the D-02 advanced-disclosure
open flag. Pydantic does not constrain the shape here — the form schema gates
the values when the draft is reconciled and submitted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class BrewDraft(Base):
    """One in-progress brew-form draft per user. Server backstop to localStorage."""

    __tablename__ = "brew_drafts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    # One active draft per user. CASCADE: a draft dies with its user.
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
