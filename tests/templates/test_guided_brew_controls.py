"""GAP 2 — C6 + C7 guided-brew template static regression (Phase 13, Plan 13-04).

Reads the raw template sources and asserts string presence/absence. These are
static assertions against committed files — no app imports, no Jinja rendering,
no database, no Tailwind. Must NOT skip.

Criteria:
  C6 (T-13-09): brew_guided.html — role="switch" removed; toggleChime( + toggleVibrate(
    present; no x-model.
  C7a:           brew_prefill_fields.html — setDose( + setWater( + x-init present;
    no x-model.
  C7b:           brew_form.html — flex-nowrap on the star row container; that
    element does NOT use flex-wrap (which would allow stars to line-wrap).
"""

from __future__ import annotations

from pathlib import Path

# Repo root is the pytest working directory (pyproject.toml is there).
_GUIDED = Path("app/templates/pages/brew_guided.html")
_PREFILL = Path("app/templates/fragments/brew_prefill_fields.html")
_BREW_FORM = Path("app/templates/pages/brew_form.html")


# ---------------------------------------------------------------------------
# C6 — brew_guided.html cue-control assertions
# ---------------------------------------------------------------------------


def test_c6_role_switch_absent_from_guided_brew() -> None:
    """role="switch" must NOT appear in brew_guided.html (C6 / T-13-09).

    Phase 13 replaced the confusing toggle pills (role=switch) with clearly
    labelled On/Off button groups. A regression reintroducing role=switch
    would recreate the UX defect.
    """
    text = _GUIDED.read_text(encoding="utf-8")
    assert 'role="switch"' not in text, (
        'brew_guided.html contains role="switch" — this was removed in Phase 13 (C6). '
        "Found unexpected role=switch attribute in the cue controls."
    )


def test_c6_toggle_chime_present_in_guided_brew() -> None:
    """toggleChime( call must be present in brew_guided.html (C6 / T-13-09).

    The in-brew toggle button calls toggleChime() via x-on:click. This is the
    CSP-safe handler that replaced the old x-model binding.
    """
    text = _GUIDED.read_text(encoding="utf-8")
    assert "toggleChime(" in text, (
        "brew_guided.html is missing toggleChime( — the CSP-safe chime toggle "
        "handler (C6). The in-brew cue toggle button must call toggleChime()."
    )


def test_c6_toggle_vibrate_present_in_guided_brew() -> None:
    """toggleVibrate( call must be present in brew_guided.html (C6 / T-13-09).

    Symmetric requirement to the chime toggle above.
    """
    text = _GUIDED.read_text(encoding="utf-8")
    assert "toggleVibrate(" in text, (
        "brew_guided.html is missing toggleVibrate( — the CSP-safe vibrate toggle "
        "handler (C6). The in-brew cue toggle button must call toggleVibrate()."
    )


def test_c6_no_x_model_in_guided_brew() -> None:
    """x-model must NOT appear in brew_guided.html (C6 / T-13-09 CSP constraint).

    x-model is forbidden in @alpinejs/csp builds (ADR 0001). All state
    mutations must use named x-on: methods. A regression adding x-model
    would break the strict CSP policy.
    """
    text = _GUIDED.read_text(encoding="utf-8")
    assert "x-model" not in text, (
        "brew_guided.html contains x-model — forbidden in the @alpinejs/csp build "
        "(ADR 0001 / T-13-09). Use named x-on:click methods instead."
    )


# ---------------------------------------------------------------------------
# C7a — brew_prefill_fields.html ratio re-sync assertions
# ---------------------------------------------------------------------------


def test_c7a_set_dose_present_in_prefill_fields() -> None:
    """setDose( call must be present in brew_prefill_fields.html (C7a).

    The dose input carries both x-init='setDose($el.value)' (for prefill
    initialisation) and x-on:input='setDose($el.value)' (for live updates).
    """
    text = _PREFILL.read_text(encoding="utf-8")
    assert "setDose(" in text, (
        "brew_prefill_fields.html is missing setDose( — the ratio re-sync "
        "call on the dose input (C7a). The dose input must call setDose()."
    )


def test_c7a_set_water_present_in_prefill_fields() -> None:
    """setWater( call must be present in brew_prefill_fields.html (C7a).

    Symmetric to setDose — the water input drives the live 1:N.NN readout.
    """
    text = _PREFILL.read_text(encoding="utf-8")
    assert "setWater(" in text, (
        "brew_prefill_fields.html is missing setWater( — the ratio re-sync "
        "call on the water input (C7a). The water input must call setWater()."
    )


def test_c7a_x_init_present_in_prefill_fields() -> None:
    """x-init must be present in brew_prefill_fields.html (C7a prefill re-sync).

    x-init seeds the brewRatio scope with the prefilled dose/water values on
    fragment swap (htmx:afterSettle → Alpine.initTree). Without x-init the
    ratio readout shows stale data after a coffee/recipe select change.
    """
    text = _PREFILL.read_text(encoding="utf-8")
    assert "x-init" in text, (
        "brew_prefill_fields.html is missing x-init — required for ratio re-sync "
        "after HTMX fragment swap (C7a). The dose/water inputs must use "
        "x-init='setDose($el.value)' / x-init='setWater($el.value)'."
    )


def test_c7a_no_x_model_in_prefill_fields() -> None:
    """x-model must NOT appear in brew_prefill_fields.html (C7a / CSP constraint).

    Forbidden in @alpinejs/csp builds. All bindings must be via named methods.
    """
    text = _PREFILL.read_text(encoding="utf-8")
    assert "x-model" not in text, (
        "brew_prefill_fields.html contains x-model — forbidden in the "
        "@alpinejs/csp build (ADR 0001). Use named x-on:input methods instead."
    )


# ---------------------------------------------------------------------------
# C7b — brew_form.html star-row flex-nowrap assertion
# ---------------------------------------------------------------------------


def test_c7b_star_row_uses_flex_nowrap() -> None:
    """The rating star row container uses flex-nowrap in brew_form.html (C7b).

    The div[role=group] wrapping the 5 star spans must carry flex-nowrap so the
    stars stay on a single line on narrow (375px) viewports. A regression to
    flex-wrap (or omitting flex-nowrap) causes stars to line-wrap and break the
    44px tap-target layout.
    """
    text = _BREW_FORM.read_text(encoding="utf-8")
    assert "flex-nowrap" in text, (
        "brew_form.html is missing flex-nowrap on the star row container (C7b). "
        "The rating group div must use 'flex flex-nowrap' to keep all 5 stars "
        "on a single line at 375px viewport width."
    )


def test_c7b_star_row_container_does_not_use_flex_wrap() -> None:
    """The star-row div[role=group] must NOT use flex-wrap (C7b).

    Checks that the specific star-row container element (the div with
    role="group" aria-label="Rating, 0 to 5 stars") does not have flex-wrap
    as a class. A bare 'flex-wrap' class on that element would override
    flex-nowrap and cause stars to line-break on narrow viewports.

    Looks at the 3-line block containing the star group div to scope the check.
    """
    text = _BREW_FORM.read_text(encoding="utf-8")
    # Find the star group div and extract a narrow window around it to scope the check.
    marker = 'aria-label="Rating, 0 to 5 stars"'
    pos = text.find(marker)
    assert pos != -1, (
        f"Could not find the star group div ('{marker}') in brew_form.html. "
        "The rating control structure may have changed — update this test."
    )
    # Extract from the opening < of the div (look back) to just past the closing >
    # of the element's class attribute line — a 300-char window is sufficient.
    window_start = max(0, pos - 50)
    window_end = min(len(text), pos + 250)
    star_row_window = text[window_start:window_end]

    # In the window, flex-nowrap should be present and there must be no standalone
    # 'flex-wrap' class (which would override flex-nowrap on the same element).
    # 'flex-wrap' matches both 'flex-wrap' and could appear as part of 'flex-nowrap',
    # so we check for ' flex-wrap' (with leading space, as a class token).
    assert "flex-nowrap" in star_row_window, (
        "The star group div does not carry 'flex-nowrap' within 250 chars of the "
        "aria-label. Check that flex-nowrap is on the correct element (C7b)."
    )
    # flex-wrap (without 'no') as a standalone class would be a regression.
    # Split on whitespace tokens to avoid false positive from 'flex-nowrap'.
    tokens = star_row_window.replace('"', " ").replace("'", " ").split()
    assert "flex-wrap" not in tokens, (
        "The star group div window contains 'flex-wrap' as a standalone class token — "
        "this would override flex-nowrap and allow stars to line-break on 375px (C7b)."
    )
