"""Recipes CRUD service — CAT-06.

Mirrors :mod:`app.services.roasters` (plan 04-04) — the universal Phase 4
catalog service template. Differences from roasters:

* ``steps`` is a ``list[dict]`` persisted to a JSONB column. The Pydantic
  layer validates per-step shape (``StepSchema``); this service hands the
  validated ``list[dict]`` to SQLAlchemy + psycopg 3, which serialise it
  natively.
* :func:`duplicate_recipe` ships the D-12 deep-copy flow — the v1
  substitute for "recipe versioning" (CONTEXT ``<deferred>``).
* Audit events: ``catalog.recipe.{created,updated,archived,duplicated}``.
  ``user_id`` kwarg name (not ``by_user_id``) per Phase 1 D-14 alignment.

The router (:mod:`app.routers.recipes`) translates :class:`RecipeNotFound`
into ``HTTPException(404)`` — the service stays FastAPI-agnostic.
"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_RECIPE_ARCHIVED,
    CATALOG_RECIPE_CREATED,
    CATALOG_RECIPE_DUPLICATED,
    CATALOG_RECIPE_UPDATED,
)
from app.models.recipe import Recipe

log = structlog.get_logger(__name__)


class RecipeNotFound(Exception):
    """Raised by :func:`duplicate_recipe` when the source row is missing.

    Kept as a domain exception (rather than an :class:`HTTPException`) so
    the service module stays free of FastAPI types. The router catches
    and re-raises as ``HTTPException(status_code=404)``.
    """


def create_recipe(
    db: Session,
    *,
    name: str,
    dose_grams: int,
    water_grams: int,
    water_temp_c: int,
    grind_setting: str,
    steps: list[dict],
    by_user_id: int,
) -> Recipe:
    """Insert a new recipe row and emit ``catalog.recipe.created``.

    ``steps`` is a list of dicts (the dump from a validated
    ``list[StepSchema]``). SQLAlchemy 2.0 + psycopg 3 native JSONB
    handles the round-trip directly — no manual ``json.dumps``.
    """
    recipe = Recipe(
        name=name,
        dose_grams=dose_grams,
        water_grams=water_grams,
        water_temp_c=water_temp_c,
        grind_setting=grind_setting,
        steps=steps,
    )
    db.add(recipe)
    db.flush()
    db.commit()
    log.info(
        CATALOG_RECIPE_CREATED,
        recipe_id=recipe.id,
        step_count=len(steps),
        user_id=by_user_id,
    )
    return recipe


def get_recipe(db: Session, *, recipe_id: int) -> Recipe | None:
    """Return the recipe with *recipe_id*, or ``None`` if missing."""
    return db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
    ).scalar_one_or_none()


def list_recipes(db: Session, *, include_archived: bool = False) -> list[Recipe]:
    """Return recipes ordered by name; archived filtered out by default."""
    stmt = select(Recipe).order_by(Recipe.name)
    if not include_archived:
        stmt = stmt.where(Recipe.archived.is_(False))
    return list(db.execute(stmt).scalars().all())


def update_recipe(
    db: Session,
    *,
    recipe_id: int,
    name: str,
    dose_grams: int,
    water_grams: int,
    water_temp_c: int,
    grind_setting: str,
    steps: list[dict],
    by_user_id: int,
) -> Recipe:
    """UPDATE the row, commit, re-fetch, emit ``catalog.recipe.updated``.

    Core ``update()`` is used (matches the roasters pattern) so we can
    stamp ``updated_at = func.now()`` in the same statement that writes
    the user-supplied fields. The re-fetched row keeps the router's
    response shape identical between create and update paths.
    """
    db.execute(
        update(Recipe)
        .where(Recipe.id == recipe_id)
        .values(
            name=name,
            dose_grams=dose_grams,
            water_grams=water_grams,
            water_temp_c=water_temp_c,
            grind_setting=grind_setting,
            steps=steps,
            updated_at=func.now(),
        )
    )
    db.commit()
    recipe = db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
    ).scalar_one()
    log.info(
        CATALOG_RECIPE_UPDATED,
        recipe_id=recipe_id,
        step_count=len(steps),
        user_id=by_user_id,
    )
    return recipe


def archive_recipe(db: Session, *, recipe_id: int, by_user_id: int) -> None:
    """Soft-delete a recipe (``archived=True``) and emit the event."""
    db.execute(
        update(Recipe)
        .where(Recipe.id == recipe_id)
        .values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_RECIPE_ARCHIVED,
        recipe_id=recipe_id,
        user_id=by_user_id,
    )


def duplicate_recipe(db: Session, *, source_id: int, by_user_id: int) -> Recipe:
    """D-12 deep copy of *source_id* into a fresh "(copy)" row.

    Raises :class:`RecipeNotFound` if the source does not exist; the
    router catches and re-raises as ``HTTPException(404)``.

    The deep copy of ``steps`` uses ``[dict(s) for s in src.steps]`` so
    each step dict is a fresh object. A shallow ``list(src.steps)`` would
    share the inner dicts — a subsequent ``update_recipe`` overwriting
    the source's steps would mutate the copy's steps too (since psycopg
    returns the same Python objects from the JSONB column until the next
    fetch). The per-dict copy is the minimal defense.

    Phase 5+ note: ``brew_sessions`` reference recipes by id, NOT by name.
    Duplicating a recipe to edit it preserves the original recipe row,
    so brew sessions logged against the original keep their reference
    intact (D-12 rationale — duplicate-instead-of-version).
    """
    src = db.execute(
        select(Recipe).where(Recipe.id == source_id)
    ).scalar_one_or_none()
    if src is None:
        raise RecipeNotFound(f"recipe {source_id} not found")

    copy = Recipe(
        name=f"{src.name} (copy)",
        dose_grams=src.dose_grams,
        water_grams=src.water_grams,
        water_temp_c=src.water_temp_c,
        grind_setting=src.grind_setting,
        steps=[dict(s) for s in (src.steps or [])],
        archived=False,
    )
    db.add(copy)
    db.flush()
    db.commit()
    log.info(
        CATALOG_RECIPE_DUPLICATED,
        recipe_id=copy.id,
        source_id=source_id,
        user_id=by_user_id,
    )
    return copy


__all__ = [
    "RecipeNotFound",
    "archive_recipe",
    "create_recipe",
    "duplicate_recipe",
    "get_recipe",
    "list_recipes",
    "update_recipe",
]
