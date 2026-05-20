"""Form-validation helpers shared by every Phase 4+ catalog router.

One function only: :func:`errors_by_field`, which pivots a Pydantic v2
``ValidationError`` into a flat ``{field_name: message}`` mapping suitable
for the D-04 form-fragment re-render (SEC-06).

Why a separate module rather than colocating inside each per-entity service?

* Every Phase 4 router (04-04 .. 04-11) consumes the same shape — keeping
  the helper in one place lets the form-fragment template signature stay
  uniform (``context={"values": ..., "errors": {...}}``).
* The pivot is pure: no DB access, no logging, no I/O. Putting it in a
  domain service module would mix concerns.

Nested ``loc`` handling
-----------------------
Pydantic v2 reports nested errors with ``loc`` tuples like
``("steps", 0, "water_grams")``. The Phase 4 form-fragment templates render
errors against the *leaf* field name, so :func:`errors_by_field` picks the
last non-integer element of the loc tuple. Integer indices (list positions)
are skipped — they are not visible to the template. This matches the
behaviour the recipe step-builder UI expects (UI-SPEC §"Form Validation
Errors").
"""

from __future__ import annotations

from pydantic import ValidationError


class DuplicateNameError(Exception):
    """Raised by a catalog service when a write hits the UNIQUE name constraint.

    The catalog name columns are ``CITEXT() ... unique=True`` (see
    :mod:`app.models.roaster` / :mod:`app.models.flavor_note`), so any create or
    rename onto an existing name (including a case-variant) raises
    :class:`sqlalchemy.exc.IntegrityError` at commit. The service catches that,
    rolls the session back, and re-raises this typed sentinel. The router maps it
    onto the SAME ``errors_by_field`` re-render path used for
    :class:`pydantic.ValidationError` — a friendly inline ``{"name": "Name
    already exists."}`` error at HTTP 200, not a 500.
    """


def errors_by_field(exc: ValidationError) -> dict[str, str]:
    """Pivot ``ValidationError.errors()`` into ``{field_name: message}``.

    Used by every Phase 4 catalog router POST handler to populate the
    inline-form-fragment errors context (SEC-06 + D-04 universal pattern).

    The chosen field name is the last non-integer element of the error's
    ``loc`` tuple. Errors with no usable loc (e.g., ``loc=()``) fall back
    to the sentinel key ``"_form"`` so the template can render a top-of-
    form generic message rather than swallowing the error.

    Multiple errors against the same field collapse: the last one wins.
    That is acceptable because the form fragment renders one error per
    field; if two rules trip on the same field, the user fixes the first
    one and re-submits, which surfaces the next one.
    """
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        field = next(
            (str(p) for p in reversed(loc) if not isinstance(p, int)),
            "_form",
        )
        out[field] = err.get("msg", "Invalid value")
    return out


__all__ = ["DuplicateNameError", "errors_by_field"]
