"""Pydantic v2 form schemas for /cafe-logs — SEC-06 universal validation pattern.

Two classes:

* ``CafeLogCreate`` — the cafe-log form field set.
* ``CafeLogUpdate(CafeLogCreate)`` — same shape today; the class split
  lets a future Update path diverge without churning Create call sites
  (matches the ``BrewSessionCreate`` / ``BrewSessionUpdate`` convention).

Validation rules:

* ``cafe_name``: non-empty string, max 200 characters.
* ``rating``: ``Decimal`` (NOT float — float rounding admits/rejects the wrong
  quarter values), 0-5 in 0.25 steps via ``multiple_of=Decimal("0.25")``.

Mass-assignment / Tampering defense (T-16-02-01, ASVS V5): ``ConfigDict(
extra="forbid")`` rejects any field not declared — a posted ``user_id`` or
``photo_filename`` raises ``ValidationError`` rather than being silently
dropped. Two fields are deliberately ABSENT:

* ``photo_filename`` — the router reads ``UploadFile`` separately and passes
  the result of ``photos.process_and_save()`` to the service; it is NEVER
  a schema field.
* ``user_id`` — the server sets it from ``request.state.user.id`` (the router),
  never the client.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CafeLogCreate(BaseModel):
    """Cafe-log form. Validation errors → 200 + form re-render (SEC-06)."""

    model_config = ConfigDict(extra="forbid")

    # cafe_name + rating are the only required-ish fields (rating still nullable).
    cafe_name: str = Field(..., min_length=1, max_length=200)
    # Decimal (NOT float) so 0.25 quarter-steps validate exactly.
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))

    # Optional enrichment.
    roaster_id: int | None = Field(None, ge=1)
    origin_country: str | None = Field(None, max_length=100)
    brew_method: str | None = Field(None, max_length=100)
    flavor_note_ids: list[int] = Field(default_factory=list)
    notes: str = Field("", max_length=5000)
    # nullable in schema; service defaults to now() when None
    logged_at: datetime | None = None


class CafeLogUpdate(CafeLogCreate):
    """Same shape today — split lets a future Update path diverge."""


__all__ = ["CafeLogCreate", "CafeLogUpdate"]
