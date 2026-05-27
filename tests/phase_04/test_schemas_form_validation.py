"""Unit tests for the Phase 4 SEC-06 form-validation primitives.

Replaces the Wave-0 ``pytest.skip`` stub shipped by plan 04-01. Every
test exercises one of:

* the SEC-06 numeric-range guarantee (``Field(ge=..., le=...)``),
* the T-04-MASS extras-rejection guarantee (``ConfigDict(extra="forbid")``),
* the D-04 ``errors_by_field`` pivot used by every catalog router POST.

No DB, no FastAPI client, no fixtures from the project conftest — these
are pure schema-layer unit tests. ``ValidationError`` is imported from
``pydantic`` so the tests are agnostic to which ``ValidationError`` shape
the future routers catch.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.bag import BagCreate
from app.schemas.coffee import CoffeeCreate
from app.schemas.equipment import EquipmentCreate
from app.schemas.flavor_note import FlavorNoteCreate
from app.schemas.recipe import RecipeCreate, StepSchema
from app.schemas.roaster import RoasterCreate
from app.services.form_validation import errors_by_field

# --------------------------------------------------------------------------- #
# CoffeeCreate                                                                #
# --------------------------------------------------------------------------- #


def test_coffee_create_valid() -> None:
    """Minimal valid coffee constructs cleanly."""
    coffee = CoffeeCreate(
        name="Geometry",
        roaster_id=1,
        process="washed",
        roast_level="light",
    )
    assert coffee.name == "Geometry"
    assert coffee.roaster_id == 1
    assert coffee.process == "washed"
    assert coffee.roast_level == "light"


def test_coffee_create_rejects_unknown_process() -> None:
    """Process regex rejects values outside the 6-value enum (defense in depth)."""
    with pytest.raises(ValidationError) as exc_info:
        CoffeeCreate(name="x", process="cold_brewed")
    locs = [err["loc"] for err in exc_info.value.errors()]
    assert any("process" in loc for loc in locs)


def test_coffee_create_rejects_blank_name() -> None:
    """min_length=1 enforces a non-empty name."""
    with pytest.raises(ValidationError):
        CoffeeCreate(name="")


def test_coffee_create_rejects_extra_field() -> None:
    """T-04-MASS: posting ``is_admin=True`` must raise (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        CoffeeCreate(name="x", is_admin=True)  # type: ignore[call-arg]
    msgs = " ".join(err["msg"] for err in exc_info.value.errors())
    assert "extra" in msgs.lower() or "not permitted" in msgs.lower() or "forbidden" in msgs.lower()


def test_coffee_create_allows_empty_advertised_notes() -> None:
    """default_factory=list keeps the empty case clean."""
    coffee = CoffeeCreate(name="Geometry", advertised_flavor_note_ids=[])
    assert coffee.advertised_flavor_note_ids == []


def test_coffee_create_rejects_negative_flavor_id() -> None:
    """Custom field_validator rejects ids < 1 (FK semantics)."""
    with pytest.raises(ValidationError):
        CoffeeCreate(name="Geometry", advertised_flavor_note_ids=[-1])


def test_coffee_create_optional_fields_default_none() -> None:
    """Optional fields default to None; notes defaults to empty string.

    Note: country, origin, varietal removed in Plan 15.1-01 (D-05/D-22).
    Origins are handled outside Pydantic via origins_country/origins_region getlist.
    """
    coffee = CoffeeCreate(name="Geometry")
    assert coffee.process is None
    assert coffee.roast_level is None
    assert coffee.notes == ""
    assert coffee.advertised_flavor_note_ids == []


def test_coffee_create_rejects_zero_roaster_id() -> None:
    """ge=1 on roaster_id rejects 0 (FK semantics)."""
    with pytest.raises(ValidationError):
        CoffeeCreate(name="Geometry", roaster_id=0)


# --------------------------------------------------------------------------- #
# RoasterCreate                                                               #
# --------------------------------------------------------------------------- #


def test_roaster_create_valid() -> None:
    """name-only roaster constructs cleanly."""
    roaster = RoasterCreate(name="Onyx")
    assert roaster.name == "Onyx"
    assert roaster.location is None
    assert roaster.website is None
    assert roaster.notes == ""


def test_roaster_create_rejects_invalid_url() -> None:
    """HttpUrl validator rejects free-text strings."""
    with pytest.raises(ValidationError):
        RoasterCreate(name="Onyx", website="not a url")  # type: ignore[arg-type]


def test_roaster_create_accepts_https() -> None:
    """HttpUrl accepts an HTTPS URL; str() yields a parseable URL string."""
    roaster = RoasterCreate(name="Onyx", website="https://onyxcoffeelab.com")  # type: ignore[arg-type]
    assert roaster.website is not None
    assert str(roaster.website).startswith("https://onyxcoffeelab.com")


def test_roaster_create_rejects_long_name() -> None:
    """max_length=200 enforced."""
    with pytest.raises(ValidationError):
        RoasterCreate(name="x" * 201)


def test_roaster_create_rejects_extra_field() -> None:
    """T-04-MASS for roaster schema."""
    with pytest.raises(ValidationError):
        RoasterCreate(name="Onyx", is_admin=True)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# FlavorNoteCreate                                                            #
# --------------------------------------------------------------------------- #


def test_flavor_note_valid() -> None:
    """All 9 categories from CAT-02 should be accepted."""
    for category in (
        "fruit",
        "floral",
        "sweet",
        "chocolate",
        "nutty",
        "spice",
        "savory",
        "fermented",
        "other",
    ):
        note = FlavorNoteCreate(name=f"note-{category}", category=category)
        assert note.category == category


def test_flavor_note_rejects_unknown_category() -> None:
    """Category regex enforces the 9-value enum."""
    with pytest.raises(ValidationError):
        FlavorNoteCreate(name="metal", category="metallic")


def test_flavor_note_rejects_blank_name() -> None:
    """min_length=1 enforced."""
    with pytest.raises(ValidationError):
        FlavorNoteCreate(name="", category="fruit")


# --------------------------------------------------------------------------- #
# EquipmentCreate                                                             #
# --------------------------------------------------------------------------- #


def test_equipment_valid() -> None:
    """Standard brewer constructs cleanly."""
    eq = EquipmentCreate(type="brewer", brand="Hario", model="V60-02", notes="ceramic")
    assert eq.type == "brewer"
    assert eq.brand == "Hario"
    assert eq.model == "V60-02"
    assert eq.notes == "ceramic"


def test_equipment_rejects_unknown_type() -> None:
    """Type regex enforces the 6-value enum from CAT-05."""
    with pytest.raises(ValidationError):
        EquipmentCreate(type="grinder_v2", brand="b", model="m")


def test_equipment_rejects_blank_brand() -> None:
    """min_length=1 on brand."""
    with pytest.raises(ValidationError):
        EquipmentCreate(type="brewer", brand="", model="V60-02")


# --------------------------------------------------------------------------- #
# StepSchema + RecipeCreate                                                   #
# --------------------------------------------------------------------------- #


def test_step_valid() -> None:
    """Standard bloom step constructs cleanly."""
    step = StepSchema(water_grams=50, time_seconds=30, label="Bloom")
    assert step.water_grams == 50
    assert step.time_seconds == 30
    assert step.label == "Bloom"


def test_step_rejects_negative_water() -> None:
    """SEC-06 ge=0 on water_grams."""
    with pytest.raises(ValidationError):
        StepSchema(water_grams=-1, time_seconds=30)


def test_step_rejects_water_over_2000() -> None:
    """SEC-06 le=2000 on water_grams."""
    with pytest.raises(ValidationError):
        StepSchema(water_grams=2001, time_seconds=30)


def test_step_rejects_time_over_3600() -> None:
    """SEC-06 le=3600 on time_seconds."""
    with pytest.raises(ValidationError):
        StepSchema(water_grams=100, time_seconds=3601)


def test_recipe_valid_with_steps() -> None:
    """Full recipe with one bloom + one main pour constructs cleanly."""
    recipe = RecipeCreate(
        name="V60 — 1:16",
        dose_grams=18,
        water_grams=288,
        water_temp_c=94,
        grind_setting="Comandante 22 clicks",
        steps=[
            StepSchema(water_grams=50, time_seconds=10, label="Bloom"),
            StepSchema(water_grams=288, time_seconds=120, label="Main pour"),
        ],
    )
    assert recipe.dose_grams == 18
    assert len(recipe.steps) == 2


def test_recipe_rejects_water_temp_over_100() -> None:
    """SEC-06 le=100 on water_temp_c — matches ROADMAP success #5 verbatim."""
    with pytest.raises(ValidationError):
        RecipeCreate(
            name="x",
            dose_grams=18,
            water_grams=288,
            water_temp_c=101,
        )


def test_recipe_rejects_negative_dose() -> None:
    """SEC-06 ge=1 on dose_grams (zero forbidden)."""
    with pytest.raises(ValidationError):
        RecipeCreate(
            name="x",
            dose_grams=0,
            water_grams=288,
            water_temp_c=94,
        )


def test_recipe_rejects_blank_name() -> None:
    """min_length=1 on recipe name."""
    with pytest.raises(ValidationError):
        RecipeCreate(name="", dose_grams=18, water_grams=288, water_temp_c=94)


def test_recipe_step_loc_carries_index_and_field() -> None:
    """A bad step inside the steps array reports loc=(steps, 0, <field>)."""
    with pytest.raises(ValidationError) as exc_info:
        RecipeCreate(
            name="x",
            dose_grams=18,
            water_grams=288,
            water_temp_c=94,
            steps=[{"water_grams": 99999, "time_seconds": 10}],  # type: ignore[list-item]
        )
    errs = exc_info.value.errors()
    assert any(
        err["loc"][0] == "steps" and err["loc"][1] == 0 and err["loc"][-1] == "water_grams"
        for err in errs
    )


# --------------------------------------------------------------------------- #
# BagCreate                                                                   #
# --------------------------------------------------------------------------- #


def test_bag_valid() -> None:
    """Minimal valid bag is just coffee_id."""
    bag = BagCreate(coffee_id=1)
    assert bag.coffee_id == 1
    assert bag.weight_grams is None
    assert bag.roast_date is None
    assert bag.notes == ""


def test_bag_rejects_negative_weight() -> None:
    """ge=1 on weight_grams rejects 0."""
    with pytest.raises(ValidationError):
        BagCreate(coffee_id=1, weight_grams=0)


def test_bag_rejects_coffee_id_zero() -> None:
    """ge=1 on coffee_id rejects 0 (FK semantics)."""
    with pytest.raises(ValidationError):
        BagCreate(coffee_id=0)


def test_bag_rejects_photo_filename_extra() -> None:
    """T-04-MASS: photo_filename is server-managed, not form-postable."""
    with pytest.raises(ValidationError):
        BagCreate(coffee_id=1, photo_filename="abc.jpg")  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# errors_by_field helper                                                      #
# --------------------------------------------------------------------------- #


def test_errors_by_field_pivots_single() -> None:
    """Single failing field → one key in the returned dict."""
    try:
        CoffeeCreate(name="")
    except ValidationError as exc:
        out = errors_by_field(exc)
    else:
        pytest.fail("expected ValidationError")
    assert "name" in out
    # Pydantic v2 phrasing: "String should have at least 1 character".
    assert "at least 1" in out["name"].lower() or "1 character" in out["name"].lower()


def test_errors_by_field_pivots_multiple() -> None:
    """Two failing fields → both keys present."""
    try:
        CoffeeCreate(name="", process="cold_brewed")
    except ValidationError as exc:
        out = errors_by_field(exc)
    else:
        pytest.fail("expected ValidationError")
    assert "name" in out
    assert "process" in out


def test_errors_by_field_handles_nested_loc() -> None:
    """A step error at loc=(steps, 0, water_grams) → key 'water_grams'."""
    try:
        RecipeCreate(
            name="x",
            dose_grams=18,
            water_grams=288,
            water_temp_c=94,
            steps=[{"water_grams": 99999, "time_seconds": 10}],  # type: ignore[list-item]
        )
    except ValidationError as exc:
        out = errors_by_field(exc)
    else:
        pytest.fail("expected ValidationError")
    assert "water_grams" in out


def test_errors_by_field_extra_field_pivots_to_field_key() -> None:
    """An ``extra_forbidden`` error pivots to the extra field's name."""
    try:
        CoffeeCreate(name="x", is_admin=True)  # type: ignore[call-arg]
    except ValidationError as exc:
        out = errors_by_field(exc)
    else:
        pytest.fail("expected ValidationError")
    assert "is_admin" in out


def test_errors_by_field_returns_dict_of_str() -> None:
    """Return type is dict[str, str] — no Pydantic objects leak through."""
    try:
        BagCreate(coffee_id=0)
    except ValidationError as exc:
        out = errors_by_field(exc)
    else:
        pytest.fail("expected ValidationError")
    assert all(isinstance(k, str) for k in out)
    assert all(isinstance(v, str) for v in out.values())
