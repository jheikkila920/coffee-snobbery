"""``api_credentials`` table — admin-managed AI provider keys (D-01..D-04).

One row per AI provider (``'anthropic'``, ``'openai'``). Migration ``p3``
seeds both rows with ``is_enabled=false`` and ``key_ciphertext=NULL`` per
D-04; the Phase 9 admin form is always an UPDATE, never an INSERT.

CLAUDE.md "Architectural invariants": AI keys live encrypted in the DB,
not env vars. Never bypass ``app.services.encryption``. The encrypted
ciphertext lives here; the pure Fernet primitives live there; the CRUD +
audit-emit shim is :mod:`app.services.credentials` (Plan 03-04 — the only
module that touches these rows).

``last_four`` is denormalized (D-03) so the Phase 9 admin list view can
mask the key without invoking the encryption service. This keeps audit
log lines and error messages safely tail-masked (SEC-6: never put the
decrypted key in a Pydantic schema that could leak via ``model_dump()``).

``key_ciphertext`` is :class:`sqlalchemy.LargeBinary` (Postgres ``bytea``)
to preserve Fernet's ``bytes`` contract end-to-end — no base64 round-trips
that could land plaintext-adjacent encoded blobs in log capture.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    LargeBinary,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ApiCredential(Base):
    """One row per AI provider; UPDATE on rotation (D-01).

    Rotating the key overwrites ``key_ciphertext``, ``last_four``,
    ``model_name``, and ``updated_at`` in a single UPDATE. There is no
    key-history table — household scale doesn't need an audit trail of
    every retired key; the structured-log ``admin.api_credential_set``
    event carries the audit trail.

    The :class:`sqlalchemy.CheckConstraint` on ``provider`` mirrors the
    ``Literal["anthropic", "openai"]`` type alias that
    :mod:`app.services.credentials` will expose; the DB layer is the
    canonical authority for the canonical provider set.
    """

    __tablename__ = "api_credentials"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    last_four: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="api_credentials_provider_check",
        ),
    )
