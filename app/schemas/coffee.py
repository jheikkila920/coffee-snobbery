"""Pydantic v2 form schema for /coffees — SEC-06 universal validation pattern.

Two classes:

* ``CoffeeCreate`` — full field set for the inline create-form fragment.
* ``CoffeeUpdate(CoffeeCreate)`` — same shape today; the class split lets a
  future Update diverge without churning Create call sites (Phase 4 PATTERNS).

Validation rules:

* ``name``: required, 1-200 chars.
* ``roaster_id``: nullable (Phase 4 PATTERNS confirms ``coffees.roaster_id``
  is ``ON DELETE SET NULL``); when present must be ``>= 1``.
* ``process`` / ``roast_level``: nullable; when present must match the
  D-01 text+CHECK enum precedent regex.
* ``advertised_flavor_note_ids``: list of FK ids (each ``>= 1``) per
  CONTEXT specifics; default empty list keeps downstream queries
  cleaner than NULL.

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` rejects
any field not declared above — e.g., a malicious ``is_admin=True`` posted
to /coffees raises ``ValidationError`` rather than being silently dropped.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoffeeCreate(BaseModel):
    """Coffee form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    roaster_id: int | None = Field(None, ge=1)
    country: str | None = Field(None, max_length=80)
    origin: str | None = Field(None, max_length=120)
    process: str | None = Field(
        None,
        pattern=r"^(washed|natural|honey|anaerobic|experimental|unknown)$",
    )
    roast_level: str | None = Field(
        None,
        pattern=r"^(light|medium-light|medium|medium-dark|dark|unknown)$",
    )
    varietal: str | None = Field(None, max_length=120)
    notes: str = Field("", max_length=2000)
    advertised_flavor_note_ids: list[int] = Field(default_factory=list)

    @field_validator("advertised_flavor_note_ids")
    @classmethod
    def _all_ids_positive(cls, v: list[int]) -> list[int]:
        if not all(i >= 1 for i in v):
            msg = "advertised_flavor_note_ids must be positive integers (>= 1)"
            raise ValueError(msg)
        return v


class CoffeeUpdate(CoffeeCreate):
    """Same shape as ``CoffeeCreate`` at v1.

    The class split is intentional: keeping the names distinct lets a future
    Update path diverge from Create (e.g., add ``archived`` toggle, drop
    required fields) without churning Create call sites (Phase 4 PATTERNS
    guidance).
    """


__all__ = ["CoffeeCreate", "CoffeeUpdate"]
