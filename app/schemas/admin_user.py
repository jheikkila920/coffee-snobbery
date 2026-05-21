"""Pydantic v2 form schemas for /admin/users — ADMIN-01.

Two classes:

* ``AdminUserCreate`` — used by the create-user form.
* ``AdminPasswordReset`` — used by the edit form's optional password reset.

Validation rules (Phase 2 D-02):

* ``username``: required, 3-32 chars. CITEXT unique enforced by DB constraint.
* ``password``: required for create; optional for edit (AdminPasswordReset).
  12-char minimum per Phase 9 password-floor decision.
* ``email``: optional (Phase 2 D-02 — admin user-create keeps email optional).
* ``is_admin``: bool, defaults False.

Mass-assignment defense: ``ConfigDict(extra="forbid")`` rejects any field
not declared above. Mirror of the roaster schema idiom.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserCreate(BaseModel):
    """Admin create-user form. 12-char password floor, optional email."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=12)
    email: EmailStr | None = None
    is_admin: bool = False


class AdminPasswordReset(BaseModel):
    """Admin password-reset subform. 12-char floor matches create."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(..., min_length=12)


__all__ = ["AdminPasswordReset", "AdminUserCreate"]
