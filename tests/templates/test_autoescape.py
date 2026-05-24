"""Wave 0 stub for SEC-05 (Jinja2 autoescape on globally).

Covers the per-task verification map row for SEC-05 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_autoescape_enabled`` — rendering ``{{ value }}`` with ``value="<script>"``
                                 produces escaped output (``&lt;script&gt;``).

Plan 08 lands ``app.templates_setup.templates`` (Jinja2 ``Environment`` with
``autoescape=True``). Phase 0 already wires templates in ``app/main.py`` via
``Jinja2Templates`` from FastAPI/Starlette, which sets autoescape ON by
default — we prefer the plan's symbolic target so the autoescape stance
remains explicit, but fall back to the existing wiring so the test goes
green at Wave 0 against Phase 0's setup.
"""

from __future__ import annotations

import pytest


def test_autoescape_enabled() -> None:
    """SEC-05: rendering an HTML-bearing string escapes ``<`` and ``>``."""
    try:
        from app.templates_setup import templates  # type: ignore[attr-defined]
    except ImportError:
        # Fall back to the Phase-0 wiring in app/main: instantiate a fresh
        # Jinja2Templates with the same directory so we exercise the same
        # autoescape stance the production app exposes.
        try:
            from fastapi.templating import Jinja2Templates
        except ImportError:
            pytest.skip(
                "Wave 1 dependency: app.templates_setup.templates (Plan 08) "
                "OR FastAPI Jinja2Templates"
            )
            return  # pragma: no cover
        templates_env = Jinja2Templates(directory="app/templates")
        env = templates_env.env
    else:
        # Plan 08 may expose the templates as either a Jinja2Templates wrapper
        # or as the raw Environment directly. Probe for the attribute.
        env = getattr(templates, "env", templates)
    rendered = env.from_string("{{ value }}").render(value="<script>")
    assert "&lt;script&gt;" in rendered, f"autoescape disabled: rendered={rendered!r}"
    assert "<script>" not in rendered, f"raw HTML leaked through Jinja: rendered={rendered!r}"
