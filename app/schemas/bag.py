"""Pydantic v2 form schema for bags — SEC-06 universal validation pattern.

One class:

* ``BagCreate`` — used by the inline "Open new bag of this coffee" form on
  the coffee detail page (CAT-08).

Validation rules:

* ``coffee_id``: required, ``>= 1``. FK to ``coffees.id`` (constraint added
  in plan 04-03).
* ``roast_date``: optional date.
* ``weight_grams``: optional; when present 1-10000 grams (10kg ceiling per
  Phase 4 CONTEXT specifics).
* ``opened_at`` / ``finished_at``: optional datetimes (lifecycle markers).
* ``notes``: optional, default empty string; max 4000 chars.

``photo_filename`` is intentionally NOT part of this schema — it is
server-managed by ``bags_service.attach_or_replace_photo`` (the photo
upload route consumes ``UploadFile`` separately, then the service writes
the resulting UUID into the DB row).

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` rejects
any field not declared above — including a malicious ``photo_filename``
posted to /bags.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BagCreate(BaseModel):
    """Bag form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    coffee_id: int = Field(..., ge=1)
    roast_date: date | None = None
    weight_grams: int | None = Field(None, ge=1, le=10000)
    opened_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str = Field("", max_length=4000)


__all__ = ["BagCreate"]
