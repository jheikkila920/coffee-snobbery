"""Water profiles CRUD service — GBREW-04, D-01.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14;
structlog audit events per Phase 1 D-14 taxonomy.

Mirrors :mod:`app.services.flavor_notes` structurally — same shape,
same kwarg conventions, same single-commit-per-write rule.

Public surface (consumed by :mod:`app.routers.water_profiles`):

* :func:`create_water_profile` — INSERT + commit + ``water_profile.created``.
* :func:`get_water_profile` — single-row fetch by id; returns ``None`` if missing.
* :func:`list_water_profiles` — ordered by name.

Architectural invariant: water_profiles is household-shared. No per-user
ownership gate — any authenticated user can create or list profiles.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.water_profile import WaterProfile
from app.services.form_validation import DuplicateNameError

log = structlog.get_logger(__name__)


def create_water_profile(
    db: Session,
    *,
    name: str,
    notes: str | None,
    by_user_id: int,
) -> WaterProfile:
    """Insert a new water profile row and emit ``water_profile.created``.

    ORM instantiate → ``add`` → ``commit`` → ``refresh`` (populate id).
    On UNIQUE name collision: rollback, raise :class:`DuplicateNameError`.
    """
    profile = WaterProfile(name=name, notes=notes)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateNameError(name) from exc
    db.refresh(profile)
    log.info(
        "water_profile.created",
        water_profile_id=profile.id,
        name=profile.name,
        by_user_id=by_user_id,
    )
    return profile


def list_water_profiles(db: Session) -> list[WaterProfile]:
    """Return all water profiles ordered by name."""
    return list(db.scalars(select(WaterProfile).order_by(WaterProfile.name)))


def get_water_profile(db: Session, *, water_profile_id: int) -> WaterProfile | None:
    """Return the water profile with *water_profile_id*, or ``None`` if missing."""
    return db.get(WaterProfile, water_profile_id)


__all__ = [
    "create_water_profile",
    "get_water_profile",
    "list_water_profiles",
]
