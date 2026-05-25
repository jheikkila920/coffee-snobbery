"""C5 mandated regression test — recipe_row.html enabled-vs-no-steps rendering.

Covers the eafc6e3 dead-span fix: ensures BOTH mode="card" and mode="row"
correctly render the /brew/guided link when a recipe has steps, and the
/recipes/{id}/edit link with "(add steps)" when it has no steps.

Both fragment shapes are covered so a regression in either mode shape is caught.
No silent skips when the Jinja env is available.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _get_jinja_env():
    """Obtain the Jinja2 Environment the same way test_autoescape.py does."""
    try:
        from app.templates_setup import templates  # type: ignore[attr-defined]
    except ImportError:
        try:
            from fastapi.templating import Jinja2Templates
        except ImportError:
            pytest.skip("FastAPI Jinja2Templates not importable")
            return None
        templates_env = Jinja2Templates(directory="app/templates")
        return templates_env.env
    else:
        return getattr(templates, "env", templates)


# A minimal "step" object — the template only checks truthiness of recipe.steps.
_STEP_OBJ = SimpleNamespace(instruction="Bloom", duration_seconds=30)


def _make_recipe(*, with_steps: bool, recipe_id: int = 42) -> SimpleNamespace:
    """Return a fake recipe with or without steps."""
    return SimpleNamespace(
        id=recipe_id,
        name="Test Recipe",
        dose_grams=15,
        water_grams=250,
        water_temp_c=93,
        grind_setting="22",
        steps=[_STEP_OBJ] if with_steps else [],
        archived=False,
    )


@pytest.mark.parametrize("mode", ["card", "row"])
def test_recipe_with_steps_renders_guided_brew_link(mode: str) -> None:
    """recipe_row with steps renders href='/brew/guided?recipe_id=...' in both shapes."""
    env = _get_jinja_env()
    recipe = _make_recipe(with_steps=True, recipe_id=7)

    rendered = env.get_template("fragments/recipe_row.html").render(
        mode=mode,
        recipe=recipe,
        include_oob_form_clear=False,
    )

    assert f'href="/brew/guided?recipe_id={recipe.id}"' in rendered, (
        f"mode={mode!r}: expected /brew/guided?recipe_id={recipe.id} link when recipe has steps"
    )
    assert f'href="/recipes/{recipe.id}/edit"' not in rendered or "Start guided brew" in rendered, (
        f"mode={mode!r}: should not render the no-steps edit link as the guided-brew control"
    )
    assert "Start guided brew" in rendered


@pytest.mark.parametrize("mode", ["card", "row"])
def test_recipe_no_steps_renders_edit_link(mode: str) -> None:
    """recipe_row without steps renders /recipes/{id}/edit + '(add steps)' in both shapes."""
    env = _get_jinja_env()
    recipe = _make_recipe(with_steps=False, recipe_id=99)

    rendered = env.get_template("fragments/recipe_row.html").render(
        mode=mode,
        recipe=recipe,
        include_oob_form_clear=False,
    )

    assert f'href="/recipes/{recipe.id}/edit"' in rendered, (
        f"mode={mode!r}: expected /recipes/{recipe.id}/edit link when recipe has no steps"
    )
    assert "(add steps)" in rendered, (
        f"mode={mode!r}: expected '(add steps)' hint when recipe has no steps"
    )
    assert "/brew/guided" not in rendered, (
        f"mode={mode!r}: must NOT render /brew/guided link when recipe has no steps"
    )
    assert "Start guided brew" in rendered
