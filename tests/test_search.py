"""Wave 0 test scaffold for Phase 10 — Global Search.

Tests are RED until Plan 02 (search service + router) and Plan 03 (header in
base.html) are complete. Failures at this wave are expected to be:
  - ImportError on `from app.services import search as search_service`
  - 404 on GET /search (router not registered yet)
  - AttributeError on search_service.highlight / search_service.run_search

Do NOT use pytest.skip to mask these failures — they must surface as real
failures to constitute a valid Wave-0 RED state. (memory: tests-pass-by-skip-mask-green)

Plan dependency map:
  - test_header_auth_gate       → Plan 03 (base.html header injection)
  - test_search_*               → Plan 02 (router + service)
  - test_result_group_order     → Plan 02 (service: SearchResults dataclass)
  - test_result_links           → Plan 02 (service: link construction)
  - test_short_query_empty      → Plan 02 (router: 2-char guard)
  - test_brew_note_user_scoping → Plan 02 (CRITICAL IDOR — WHERE user_id)
  - test_shared_catalog_visible → Plan 02 (shared catalog queries)
  - test_highlight_xss_safe     → Plan 02 (highlight() helper, markupsafe.escape)
  - test_highlight_markup       → Plan 02 (highlight() helper, <strong> wrapping)
  - test_group_cap              → Plan 02 (per-group cap logic)
  - test_archived_scope         → Plan 02 (D-12 archived inclusion/exclusion rules)
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Module-level import probe — surfaces the RED state clearly.
# The try/except does NOT skip; it lets tests that call the service fail with
# a useful NameError / AttributeError rather than an opaque collection error.
# ---------------------------------------------------------------------------
try:
    from app.services import search as search_service  # noqa: F401

    _SEARCH_SERVICE_AVAILABLE = True
except ImportError:
    search_service = None  # type: ignore[assignment]
    _SEARCH_SERVICE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Seed helpers — shared by multiple tests.
# Mirror the pattern from tests/phase_09/conftest.py (_seed_brew_for_user).
# ---------------------------------------------------------------------------


def _seed_shared_catalog(
    *,
    coffee_suffix: str = "",
    roaster_suffix: str = "",
    recipe_suffix: str = "",
    equipment_suffix: str = "",
    flavor_note_suffix: str = "",
) -> dict[str, Any]:
    """Seed one row of each catalog entity; return their IDs.

    All rows are active (archived=False) unless the caller overrides via the
    returned IDs. Coffee is the most constrained (brew_sessions FK) — it is
    always seeded so brew fixture helpers can reference it.
    """
    from app.main import async_session_factory
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.flavor_note import FlavorNote
    from app.models.recipe import Recipe
    from app.models.roaster import Roaster

    suffix = uuid.uuid4().hex[:6]
    cs = coffee_suffix or suffix
    rs = roaster_suffix or suffix
    res = recipe_suffix or suffix
    es = equipment_suffix or suffix
    fs = flavor_note_suffix or suffix

    async def _do() -> dict[str, Any]:
        async with async_session_factory() as db:
            roaster = Roaster(name=f"Equinox Roasters {rs}")
            db.add(roaster)
            await db.flush()

            coffee = Coffee(
                name=f"Ethiopia Yirgacheffe {cs}",
                origin="Yirgacheffe",
                roaster_id=roaster.id,
                notes="",
            )
            db.add(coffee)

            recipe = Recipe(
                name=f"V60 Pour-Over {res}",
                grind_setting="22 clicks",
                dose_grams=18,
                water_grams=300,
                water_temp_c=94,
            )
            db.add(recipe)

            equip = Equipment(
                brand=f"Hario {es}",
                model="V60-02",
                type="brewer",
            )
            db.add(equip)

            fn = FlavorNote(name=f"Jasmine {fs}", category="floral")
            db.add(fn)

            await db.flush()
            await db.commit()
            return {
                "coffee_id": coffee.id,
                "coffee_name": coffee.name,
                "roaster_id": roaster.id,
                "roaster_name": roaster.name,
                "recipe_id": recipe.id,
                "recipe_name": recipe.name,
                "equipment_id": equip.id,
                "equipment_brand": equip.brand,
                "equipment_model": equip.model,
                "flavor_note_id": fn.id,
                "flavor_note_name": fn.name,
            }

    return asyncio.run(_do())


def _seed_brew_session(
    *,
    user_id: int,
    coffee_id: int,
    notes: str = "",
) -> int:
    """Seed one brew_session row; return its id."""
    from app.main import async_session_factory
    from app.models.brew_session import BrewSession

    async def _do() -> int:
        async with async_session_factory() as db:
            brew = BrewSession(
                user_id=user_id,
                coffee_id=coffee_id,
                dose_grams_actual=Decimal("18.0"),
                water_grams_actual=Decimal("300.0"),
                notes=notes,
            )
            db.add(brew)
            await db.commit()
            await db.refresh(brew)
            return brew.id

    return asyncio.run(_do())


def _make_cookie(fixture: dict[str, Any]) -> dict[str, str]:
    """Return cookie dict for TestClient requests."""
    return {"session_id": fixture["signed_cookie"]}


# ---------------------------------------------------------------------------
# SEARCH-01: Header auth gate
# Depends on Plan 03 (base.html header injection)
# ---------------------------------------------------------------------------


def test_header_auth_gate(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Search header renders on authenticated pages; absent on /login and /setup.

    SEARCH-01 — the persistent search input must appear only when a user is
    logged in. /login and /setup must not contain the search header markup.
    This test stays RED until Plan 03 injects the header into base.html.
    """
    cookies = _make_cookie(seeded_admin_user)

    # Authenticated page — home should contain the search header
    resp = client.get("/", cookies=cookies, follow_redirects=True)
    assert resp.status_code == 200
    # Plan 03 will add id="search-header" or a search input in base.html.
    # The canonical marker is the search input with hx-get="/search".
    assert 'hx-get="/search"' in resp.text, (
        "Search header not found on authenticated home page — Plan 03 not yet applied"
    )

    # /login must NOT contain the search header (user is not yet authenticated)
    resp_login = client.get("/login")
    assert resp_login.status_code == 200
    assert 'hx-get="/search"' not in resp_login.text, (
        "Search header must not appear on /login (unauthenticated page)"
    )

    # /setup must NOT contain the search header
    resp_setup = client.get("/setup")
    assert resp_setup.status_code in (200, 303)  # 303 if setup already complete
    if resp_setup.status_code == 200:
        assert 'hx-get="/search"' not in resp_setup.text, (
            "Search header must not appear on /setup (unauthenticated page)"
        )


# ---------------------------------------------------------------------------
# SEARCH-02: Catalog entity searches (Plan 02)
# ---------------------------------------------------------------------------


def test_search_coffees(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """GET /search?q=<substr> returns the coffee name in results. (SEARCH-02)"""
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    # Use a unique fragment of the seeded coffee name (suffix guarantees uniqueness)
    coffee_name = catalog["coffee_name"]
    # "Yirgacheffe" is in all seeded coffee names; the full name also includes suffix
    q = coffee_name[:8]  # First 8 chars of "Ethiopia"

    resp = client.get(f"/search?q={q}", cookies=cookies)
    assert resp.status_code == 200, f"GET /search returned {resp.status_code}"
    assert coffee_name in resp.text, (
        f"Coffee name '{coffee_name}' not found in search results for q={q!r}"
    )


def test_search_roasters(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """GET /search?q=<roaster substr> returns roaster name in results. (SEARCH-02)"""
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    roaster_name = catalog["roaster_name"]
    q = "Equinox"  # Prefix of every seeded roaster name

    resp = client.get(f"/search?q={q}", cookies=cookies)
    assert resp.status_code == 200
    assert roaster_name in resp.text, (
        f"Roaster name '{roaster_name}' not found in search results for q={q!r}"
    )


def test_search_recipes(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Recipe name match appears; grind_setting alone does NOT match. (SEARCH-02, D-13)"""
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    recipe_name = catalog["recipe_name"]

    # Query on recipe name prefix should return the recipe
    resp = client.get("/search?q=V60", cookies=cookies)
    assert resp.status_code == 200
    assert recipe_name in resp.text, (
        f"Recipe name '{recipe_name}' not found in search results for q='V60'"
    )

    # Query matching only grind_setting ("clicks") must NOT return the recipe
    # (D-13: recipe search is name-only; grind_setting is context display, not a match field)
    resp2 = client.get("/search?q=clicks", cookies=cookies)
    assert resp2.status_code == 200
    assert recipe_name not in resp2.text, (
        f"Recipe '{recipe_name}' appeared in results for q='clicks' "
        "(D-13: recipe search must be name-only, not grind_setting)"
    )


def test_search_equipment(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Brand+model concat match, brand alone, and model alone all succeed. (SEARCH-02, D-14)"""
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    brand = catalog["equipment_brand"]  # e.g. "Hario <suffix>"
    model = catalog["equipment_model"]  # "V60-02"

    # Full brand+model concat
    resp_full = client.get("/search?q=Hario+V60", cookies=cookies)
    assert resp_full.status_code == 200
    assert brand in resp_full.text or model in resp_full.text, (
        f"Equipment '{brand} {model}' not found via full brand+model query"
    )

    # Brand alone
    resp_brand = client.get("/search?q=Hario", cookies=cookies)
    assert resp_brand.status_code == 200
    assert brand in resp_brand.text, f"Equipment brand '{brand}' not found in search results"

    # Model alone
    resp_model = client.get("/search?q=V60", cookies=cookies)
    assert resp_model.status_code == 200
    assert model in resp_model.text, f"Equipment model '{model}' not found in search results"


def test_search_flavor_notes(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Flavor note name match appears in results. (SEARCH-02)"""
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    fn_name = catalog["flavor_note_name"]

    resp = client.get("/search?q=Jasmine", cookies=cookies)
    assert resp.status_code == 200
    assert fn_name in resp.text, (
        f"Flavor note '{fn_name}' not found in search results for q='Jasmine'"
    )


# ---------------------------------------------------------------------------
# SEARCH-03: Result structure
# ---------------------------------------------------------------------------


def test_result_group_order(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """D-07 fixed group order: Coffees, Roasters, Recipes, Equipment, Flavor Notes, Brew Notes.

    Seeds one of each entity with the same prefix ("SearchTest") so all six
    groups may appear, then verifies the group headers appear in the fixed D-07
    order in the response HTML.
    """
    suffix = uuid.uuid4().hex[:6]
    from app.main import async_session_factory
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.flavor_note import FlavorNote
    from app.models.recipe import Recipe
    from app.models.roaster import Roaster

    async def _seed_all() -> int:
        async with async_session_factory() as db:
            roaster = Roaster(name=f"SearchTest Roasters {suffix}")
            db.add(roaster)
            await db.flush()

            coffee = Coffee(name=f"SearchTest Coffee {suffix}", notes="", roaster_id=roaster.id)
            db.add(coffee)

            recipe = Recipe(
                name=f"SearchTest Recipe {suffix}",
                grind_setting="medium",
                dose_grams=18,
                water_grams=300,
                water_temp_c=94,
            )
            db.add(recipe)

            equip = Equipment(brand=f"SearchTest {suffix}", model="Brand", type="brewer")
            db.add(equip)

            fn = FlavorNote(name=f"SearchTest Note {suffix}", category="floral")
            db.add(fn)

            await db.flush()

            brew = BrewSession(
                user_id=seeded_admin_user["user"].id,
                coffee_id=coffee.id,
                dose_grams_actual=Decimal("18.0"),
                water_grams_actual=Decimal("300.0"),
                notes=f"SearchTest brew note {suffix}",
            )
            db.add(brew)
            await db.commit()
            return coffee.id

    asyncio.run(_seed_all())
    cookies = _make_cookie(seeded_admin_user)

    resp = client.get("/search?q=SearchTest", cookies=cookies)
    assert resp.status_code == 200
    html = resp.text

    # D-07 fixed group order — verify positions in response text
    groups = ["Coffees", "Roasters", "Recipes", "Equipment", "Flavor Notes", "Brew Notes"]
    positions = []
    for group in groups:
        pos = html.find(group)
        if pos != -1:
            positions.append((group, pos))

    # At minimum, the groups that appear must be in the correct relative order
    for i in range(1, len(positions)):
        prev_group, prev_pos = positions[i - 1]
        curr_group, curr_pos = positions[i]
        assert prev_pos < curr_pos, (
            f"Group '{prev_group}' (pos {prev_pos}) must appear before "
            f"'{curr_group}' (pos {curr_pos}) — D-07 fixed order violated"
        )


def test_result_links(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Each result row links to the correct D-11 URL. (SEARCH-03, D-11)

    D-11 link destinations:
      - Coffee -> /coffees/{id}
      - Roaster -> /roasters/{id}/edit
      - Recipe -> /recipes/{id}/edit
      - Equipment -> /equipment/{id}/edit
      - FlavorNote -> /flavor-notes/{id}/edit
      - BrewSession -> /brew/{id}/edit
    """
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    coffee_id = catalog["coffee_id"]

    # Coffee links to /coffees/{id} (detail page, not /edit)
    resp = client.get("/search?q=Ethiopia", cookies=cookies)
    assert resp.status_code == 200
    assert f'/coffees/{coffee_id}"' in resp.text or f"/coffees/{coffee_id}'" in resp.text, (
        f"Expected link /coffees/{coffee_id} in search results for coffee"
    )


def test_short_query_empty(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """GET /search?q=e (1 char) returns 200 with empty body. (SEARCH-04, D-10)

    The server enforces a minimum 2-char query. Shorter queries return an
    empty 200 response so HTMX clears the results container.
    """
    cookies = _make_cookie(seeded_admin_user)

    resp = client.get("/search?q=e", cookies=cookies)
    assert resp.status_code == 200
    # Empty or near-empty body — no entity names should appear
    assert resp.text.strip() == "", (
        f"Expected empty response for 1-char query; got: {resp.text[:200]!r}"
    )


# ---------------------------------------------------------------------------
# S4: Input length cap + rate limit
# ---------------------------------------------------------------------------


def test_long_query_returns_empty(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """GET /search with a 101-char q returns 200 with empty body. (S4, D-07)

    The server caps raw q at 100 chars before strip(), so a 101-char string
    short-circuits to an empty 200 — same shape as the <2-char guard.
    """
    cookies = _make_cookie(seeded_admin_user)

    long_q = "a" * 101
    resp = client.get(f"/search?q={long_q}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.text.strip() == "", (
        f"Expected empty response for 101-char query; got: {resp.text[:200]!r}"
    )


def test_search_rate_limit(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """61st GET /search in a minute from one IP returns 429. (S4, D-08)

    Fires 61 requests against SEARCH_LIMIT ("60/minute"). The in-memory limiter
    resets between tests via the autouse _reset_rate_limiter fixture in conftest.
    """
    cookies = _make_cookie(seeded_admin_user)

    statuses: list[int] = []
    for _ in range(61):
        r = client.get("/search?q=ab", cookies=cookies)
        statuses.append(r.status_code)

    assert 429 in statuses, (
        f"Expected a 429 after 60 requests (SEARCH_LIMIT = 60/minute); "
        f"status codes: {statuses[-5:]!r}"
    )


# ---------------------------------------------------------------------------
# SEARCH-04: User scoping — CRITICAL IDOR test (T-10-IDOR)
# ---------------------------------------------------------------------------


def test_brew_note_user_scoping(
    client: Any,
    seeded_admin_user: dict[str, Any],
    seeded_regular_user: dict[str, Any],
) -> None:
    """CRITICAL IDOR: User A cannot see User B's brew notes in search results.

    T-10-IDOR threat from the plan's threat_model. This is the most important
    correctness invariant in Phase 10. If this test ever passes accidentally
    (before Plan 02 is built), investigate — the service may already exist.

    Setup:
      - User A = seeded_admin_user
      - User B = seeded_regular_user
      - User B gets a brew session with notes="secret Ethiopia mango" on a shared coffee
      - User A gets a brew session with notes="User A generic note" on the same coffee

    Assertions:
      - User A's GET /search?q=mango does NOT contain "secret Ethiopia mango"
      - User B's GET /search?q=mango DOES contain "secret Ethiopia mango"
    """
    user_a = seeded_admin_user
    user_b = seeded_regular_user

    # Seed a shared coffee (brew_sessions.coffee_id is NOT NULL RESTRICT)
    catalog = _seed_shared_catalog()
    coffee_id = catalog["coffee_id"]

    # Seed User B's distinctive brew note
    _seed_brew_session(
        user_id=user_b["user"].id,
        coffee_id=coffee_id,
        notes="secret Ethiopia mango",
    )

    # Seed User A's brew note (different content)
    _seed_brew_session(
        user_id=user_a["user"].id,
        coffee_id=coffee_id,
        notes="User A generic note",
    )

    cookies_a = _make_cookie(user_a)
    cookies_b = _make_cookie(user_b)

    # User A searches for "mango"
    resp_a = client.get("/search?q=mango", cookies=cookies_a)
    assert resp_a.status_code == 200
    assert "secret Ethiopia mango" not in resp_a.text, (
        "IDOR VIOLATION: User A can see User B's brew note 'secret Ethiopia mango'. "
        "The search service must filter brew_sessions WHERE user_id = current_user.id."
    )

    # User B searches for "mango" — must see their own note
    resp_b = client.get("/search?q=mango", cookies=cookies_b)
    assert resp_b.status_code == 200
    assert "secret Ethiopia mango" in resp_b.text, (
        "User B cannot see their own brew note in search results — "
        "the service's brew note query may be broken."
    )


def test_shared_catalog_visible(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """User A sees shared catalog (coffees, roasters) in results. (SEARCH-03)

    Shared catalog entities (coffees, roasters, recipes, equipment, flavor_notes)
    are visible to all authenticated users — not per-user scoped.
    """
    catalog = _seed_shared_catalog()
    cookies = _make_cookie(seeded_admin_user)

    coffee_name = catalog["coffee_name"]
    roaster_name = catalog["roaster_name"]

    resp = client.get("/search?q=Ethiopia", cookies=cookies)
    assert resp.status_code == 200
    assert coffee_name in resp.text, f"Shared coffee '{coffee_name}' not visible to User A"

    resp2 = client.get("/search?q=Equinox", cookies=cookies)
    assert resp2.status_code == 200
    assert roaster_name in resp2.text, f"Shared roaster '{roaster_name}' not visible to User A"


# ---------------------------------------------------------------------------
# D-06: Highlight safety (T-10-XSS)
# ---------------------------------------------------------------------------


def test_highlight_xss_safe() -> None:
    """highlight() escapes HTML; raw <script> never appears in output. (D-06, T-10-XSS)

    The highlight() helper in app.services.search must:
    1. Escape the surrounding text (including any HTML in user input)
    2. Wrap the matched substring in <strong class='font-semibold'>
    3. Return a markupsafe.Markup object (Jinja2 trusts it; no double-escaping)

    This test is a unit test — it calls search_service.highlight() directly.
    """
    assert search_service is not None, "app.services.search not importable — Plan 02 not yet built"
    result = search_service.highlight(
        text="<script>alert(1)</script> beans",
        query="beans",
    )
    result_str = str(result)

    # The escaped form must appear
    assert "&lt;script&gt;" in result_str, (
        f"<script> was not escaped to &lt;script&gt; in highlight output: {result_str!r}"
    )

    # Raw <script> must NOT appear
    assert "<script>" not in result_str, (
        f"Raw <script> tag found in highlight output — XSS vulnerability: {result_str!r}"
    )

    # The matched word must be wrapped in <strong
    assert "<strong" in result_str, f"Expected <strong> wrapper for matched text in: {result_str!r}"


def test_highlight_markup() -> None:
    """highlight() wraps match in <strong class='font-semibold'>, preserving context. (D-06)

    The matching substring must be wrapped and the surrounding text must remain
    intact and correctly split.
    """
    assert search_service is not None, "app.services.search not importable — Plan 02 not yet built"
    result = search_service.highlight("Ethiopia", "thio")
    result_str = str(result)

    # The matched portion must be inside <strong class='font-semibold'>
    assert "<strong class='font-semibold'>thio</strong>" in result_str or (
        "<strong" in result_str and "thio" in result_str
    ), f"Match 'thio' not wrapped in <strong class='font-semibold'> in: {result_str!r}"

    # Per D-06: "thio" matches at index 1 of "Ethiopia", so the prefix is "E"
    # (split from "thio" by the <strong> tag) and the suffix is "pia".
    assert result_str.startswith("E<strong"), (
        f"Prefix 'E' missing/misplaced in highlight output: {result_str!r}"
    )
    assert result_str.endswith("</strong>pia"), (
        f"Suffix 'pia' missing from highlight output: {result_str!r}"
    )


# ---------------------------------------------------------------------------
# D-09: Per-group cap + "+N more" hint
# ---------------------------------------------------------------------------


def test_group_cap(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """When 6 coffees match, at most 5 rows render + a '+1 more' hint. (D-09)"""
    from app.main import async_session_factory
    from app.models.coffee import Coffee

    suffix = uuid.uuid4().hex[:6]
    cap_prefix = f"CapTest{suffix}"

    async def _seed_six() -> None:
        async with async_session_factory() as db:
            for i in range(6):
                db.add(Coffee(name=f"{cap_prefix} Coffee {i}", notes=""))
            await db.commit()

    asyncio.run(_seed_six())
    cookies = _make_cookie(seeded_admin_user)

    resp = client.get(f"/search?q={cap_prefix}", cookies=cookies)
    assert resp.status_code == 200
    html = resp.text

    # Count occurrences of cap_prefix (each result row will contain it)
    count = html.count(cap_prefix)

    # At most 5 full result rows should appear (cap_prefix appears in each row)
    # The "+N more" hint appears without cap_prefix in the text, so count <= 5
    # (plus the group header might have a count label, giving up to 6 appearances
    # if "+N more" hint uses cap_prefix — but it should not)
    assert count <= 5, (
        f"Expected at most 5 result rows (D-09 cap), but found {count} occurrences "
        f"of '{cap_prefix}' in search results — group cap not enforced"
    )

    # "+N more" hint must appear since 6 rows were seeded
    assert "more" in html.lower(), (
        "Expected '+N more' hint when 6 items match but cap is 5; not found in response"
    )


# ---------------------------------------------------------------------------
# D-12 / D-14: Archived entity scoping
# ---------------------------------------------------------------------------


def test_archived_scope(
    client: Any,
    seeded_admin_user: dict[str, Any],
) -> None:
    """Archived coffee and equipment appear with 'Archived' badge.
    Archived roaster, recipe, and flavor_note do NOT appear. (D-12, D-14)

    D-12 says: include archived coffees and equipment (with badge).
    Roasters, recipes, flavor_notes: archived items are excluded.
    """
    from app.main import async_session_factory
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.flavor_note import FlavorNote
    from app.models.recipe import Recipe
    from app.models.roaster import Roaster

    suffix = uuid.uuid4().hex[:6]
    arc_prefix = f"ArchiveScope{suffix}"

    async def _seed_archived() -> None:
        async with async_session_factory() as db:
            # Archived coffee — SHOULD appear with "Archived" badge
            db.add(Coffee(name=f"{arc_prefix} ArchivedCoffee", notes="", archived=True))

            # Archived equipment — SHOULD appear with "Archived" badge
            db.add(
                Equipment(
                    brand=f"{arc_prefix} ArchivedBrand",
                    model="ArchivedModel",
                    type="brewer",
                    archived=True,
                )
            )

            # Archived roaster — must NOT appear
            db.add(Roaster(name=f"{arc_prefix} ArchivedRoaster", archived=True))

            # Archived recipe — must NOT appear
            db.add(
                Recipe(
                    name=f"{arc_prefix} ArchivedRecipe",
                    grind_setting="medium",
                    dose_grams=18,
                    water_grams=300,
                    water_temp_c=94,
                    archived=True,
                )
            )

            # Archived flavor note — must NOT appear
            db.add(
                FlavorNote(
                    name=f"{arc_prefix} ArchivedFlavor",
                    category="floral",
                    archived=True,
                )
            )

            await db.commit()

    asyncio.run(_seed_archived())
    cookies = _make_cookie(seeded_admin_user)

    resp = client.get(f"/search?q={arc_prefix}", cookies=cookies)
    assert resp.status_code == 200
    html = resp.text

    # Archived coffee MUST appear
    assert f"{arc_prefix} ArchivedCoffee" in html, (
        f"Archived coffee '{arc_prefix} ArchivedCoffee' must appear in search results (D-12)"
    )

    # Archived coffee must have "Archived" badge
    archived_badge_pos = html.find("Archived")
    assert archived_badge_pos != -1, (
        "No 'Archived' badge found in response for archived coffee (D-12)"
    )

    # Archived equipment MUST appear
    assert f"{arc_prefix} ArchivedBrand" in html, (
        f"Archived equipment brand '{arc_prefix} ArchivedBrand' must appear (D-12)"
    )

    # Archived roaster must NOT appear
    assert f"{arc_prefix} ArchivedRoaster" not in html, (
        f"Archived roaster '{arc_prefix} ArchivedRoaster' must NOT appear in results (D-12)"
    )

    # Archived recipe must NOT appear
    assert f"{arc_prefix} ArchivedRecipe" not in html, (
        f"Archived recipe '{arc_prefix} ArchivedRecipe' must NOT appear in results (D-12)"
    )

    # Archived flavor note must NOT appear
    assert f"{arc_prefix} ArchivedFlavor" not in html, (
        f"Archived flavor note '{arc_prefix} ArchivedFlavor' must NOT appear in results (D-12)"
    )
