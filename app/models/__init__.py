"""SQLAlchemy declarative models.

Every model module is re-exported here so Alembic's metadata discovery is
complete: ``app/migrations/env.py`` does ``import app.models  # noqa: F401``
and then reads ``Base.metadata`` — if a new model isn't re-exported here,
autogenerate won't see it.

When adding a new model in a future phase: add the import below AND extend
``__all__``. Same rule applies whether the model lands in its own module or
reuses an existing one.
"""

from __future__ import annotations

from app.models.ai_recommendation import AIRecommendation
from app.models.api_credential import ApiCredential
from app.models.app_setting import AppSetting
from app.models.bag import Bag
from app.models.base import Base
from app.models.brew_draft import BrewDraft
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.coffee_origin import CoffeeOrigin
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster
from app.models.session import Session
from app.models.user import User
from app.models.wishlist_entry import WishlistEntry

__all__ = [
    "AIRecommendation",
    "ApiCredential",
    "AppSetting",
    "Bag",
    "Base",
    "BrewDraft",
    "BrewSession",
    "Coffee",
    "CoffeeOrigin",
    "Equipment",
    "FlavorNote",
    "Recipe",
    "Roaster",
    "Session",
    "User",
    "WishlistEntry",
]
