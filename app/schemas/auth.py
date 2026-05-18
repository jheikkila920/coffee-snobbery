"""Pydantic v2 form schemas for /setup and /login (AUTH-01 / AUTH-03).

Validation rules (CONTEXT "Claude's Discretion / Password policy floor"):

* Username: 3-32 chars, ``[A-Za-z0-9_-]`` regex.
* Email: ``EmailStr`` validation (RFC-aware via ``email-validator``).
* Password: 12-char minimum (soft floor; no complexity rules per CONTEXT).

The schemas are constructed inside the route handler from individual
``Form(...)`` parameters (rather than the ``Annotated[..., Form()]``
shortcut) so the ``ValidationError`` can be caught locally and the
template re-rendered with a generic error — instead of letting FastAPI
return the default 422 JSON payload (which would break the D-07 generic-
error contract on ``/login``).

Why ``LoginForm`` validation is intentionally loose
----------------------------------------------------
The ``/login`` POST runs through the constant-time argon2 verify path
even when the username does not match the regex used for ``SetupForm``.
A strict regex on ``LoginForm.username`` would shortcut bad-shape
usernames into a fast "invalid input" rejection — a wall-clock timing
channel that lets an attacker distinguish "username structurally invalid"
from "valid username, wrong password." See threat T-02-07-01 in
``02-07-PLAN.md`` and ``app.services.auth.dummy_verify`` for the broader
symmetry argument.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SetupForm(BaseModel):
    """First-admin setup form. D-02 requires email; 12-char password floor."""

    username: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9_-]{3,32}$",
        description="3-32 chars, alphanumeric plus '-' and '_'.",
    )
    email: EmailStr = Field(..., description="Required for the first admin per D-02.")
    password: str = Field(..., min_length=12, description="Minimum 12 characters.")


class LoginForm(BaseModel):
    """Login form. Loose validation by design — see module docstring."""

    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1)


__all__ = ["LoginForm", "SetupForm"]
