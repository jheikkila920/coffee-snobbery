"""Phase 19 plan 06 template assertions (VIZ-01 / AIX-01/06/09/10/12).

Tests are pure Jinja2 render checks — no Docker, no DB, no HTTP.  They verify
the structural promises made in the plan frontmatter must_haves:

  CDN / indicator assertions (Task 1):
    test_base_has_chartjs_cdn        — Chart.js @4.5.1 with csp_nonce in base.html
    test_base_has_htmx_sse_cdn       — htmx-ext-sse @2.2.4 with csp_nonce in base.html
    test_tailwind_has_htmx_indicator — .htmx-indicator rule in tailwind.src.css
    test_tailwind_has_chart_canvas   — .chart-canvas rule in tailwind.src.css
    test_chart_trends_js_no_eval     — chart-trends.js has no eval()
    test_chart_trends_js_registers   — chart-trends.js registers Alpine.data('chartTrends')

  AI page structure assertions (Task 2):
    test_ai_page_has_research_form_include     — research_form include at top
    test_ai_page_no_research_coming_soon       — research_coming_soon.html absent
    test_ai_page_no_top_flavor_descriptors     — flavor-descriptors hx-get absent
    test_ai_page_has_trends_card_include       — trends_card include present
    test_research_form_has_sse_connect         — research_form.html has sse-connect
    test_research_form_has_quota_counter       — research_form.html has research-quota
    test_research_result_no_safe_filter        — research_result.html has no |safe
    test_research_result_has_prediction_range  — research_result.html has predicted_low/high
    test_research_result_has_wishlist_button   — research_result.html posts to /ai/wishlist/add
    test_preference_profile_prose_no_safe      — preference_profile_prose.html has no |safe
    test_trends_card_has_canvas_refs           — trends_card.html has ratingCanvas + flavorCanvas

  Improve-brew assertions (Task 3):
    test_improve_result_no_safe                — improve_result.html has no |safe
    test_improve_result_has_next_try           — improve_result.html renders next_try rationale
    test_brew_form_has_improve_button          — brew_form.html has improve-brew affordance
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Jinja env + file helpers
# ---------------------------------------------------------------------------


def _get_jinja_env():
    """Obtain the Jinja2 Environment — mirrors test_recipe_row.py pattern."""
    try:
        from app.templates_setup import templates  # type: ignore[attr-defined]
    except ImportError:
        try:
            from fastapi.templating import Jinja2Templates
        except ImportError:
            pytest.skip("Jinja2Templates not importable")
            return None
        t = Jinja2Templates(directory="app/templates")
        return t.env
    else:
        return getattr(templates, "env", templates)


def _repo_root() -> Path:
    """Return the repo root (parent of app/).

    Works when pytest runs from the repo root (typical) or from /app inside
    the container (WORKDIR /app). If 'app' dir not adjacent, fall back to CWD.
    """
    cwd = Path.cwd()
    # container: cwd is /app, source is at /app/app/...
    if (cwd / "app").is_dir():
        return cwd
    # local: cwd might be a subdirectory
    for parent in [cwd, *cwd.parents]:
        if (parent / "app").is_dir():
            return parent
    return cwd


def _read_static(relative: str) -> str:
    """Read a static file relative to the repo root."""
    path = _repo_root() / relative
    if not path.exists():
        pytest.skip(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_template(env, name: str) -> str:
    """Render a template source (not full render — just read its source)."""
    try:
        src, _, _ = env.loader.get_source(env, name)
        return src
    except Exception:
        pytest.skip(f"Template not found: {name}")
        return ""


# ---------------------------------------------------------------------------
# Task 1: base.html CDN + tailwind.src.css + chart-trends.js
# ---------------------------------------------------------------------------


def test_base_has_chartjs_cdn() -> None:
    """Chart.js @4.5.1 CDN tag with csp_nonce must be present in base.html."""
    src = _read_static("app/templates/base.html")
    assert "chart.js@4.5.1" in src, "Missing chart.js@4.5.1 CDN reference in base.html"
    # Ensure nonce is on the same section (not necessarily same line due to wrapping)
    assert 'nonce="{{ csp_nonce(request) }}"' in src, "Missing csp_nonce on base.html scripts"


def test_base_has_htmx_sse_cdn() -> None:
    """htmx-ext-sse @2.2.4 CDN tag with csp_nonce must be present in base.html."""
    src = _read_static("app/templates/base.html")
    assert "htmx-ext-sse@2.2.4" in src, "Missing htmx-ext-sse@2.2.4 CDN reference in base.html"


def test_tailwind_has_htmx_indicator() -> None:
    """.htmx-indicator rule must exist in tailwind.src.css.

    See project memory strict-csp-blocks-htmx-indicator.
    """
    src = _read_static("app/static/css/tailwind.src.css")
    assert ".htmx-indicator" in src, ".htmx-indicator rule missing from tailwind.src.css"
    assert ".htmx-request .htmx-indicator" in src, ".htmx-request .htmx-indicator rule missing"


def test_tailwind_has_chart_canvas() -> None:
    """.chart-canvas rule must exist in tailwind.src.css (canvas sizing without inline style)."""
    src = _read_static("app/static/css/tailwind.src.css")
    assert ".chart-canvas" in src, ".chart-canvas rule missing from tailwind.src.css"


def test_chart_trends_js_no_eval() -> None:
    """chart-trends.js must not contain eval() — CSP-clean requirement."""
    src = _read_static("app/static/js/alpine-components/chart-trends.js")
    # eval( as a call — not a comment or string inside a name
    import re

    assert not re.search(r"\beval\s*\(", src), "eval() found in chart-trends.js — CSP violation"


def test_chart_trends_js_registers() -> None:
    """chart-trends.js must register Alpine.data('chartTrends', ...)."""
    src = _read_static("app/static/js/alpine-components/chart-trends.js")
    assert "chartTrends" in src, (
        "Alpine.data('chartTrends') registration missing from chart-trends.js"
    )
    assert "Alpine.data" in src, "Alpine.data call missing from chart-trends.js"


# ---------------------------------------------------------------------------
# Task 2: AI page structure + fragments
# ---------------------------------------------------------------------------


def test_ai_page_has_research_form_include() -> None:
    """ai.html must include research_form.html at the top of the key-present branch."""
    env = _get_jinja_env()
    src = _read_template(env, "pages/ai.html")
    assert "research_form" in src, "ai.html missing research_form include"


def test_ai_page_no_research_coming_soon() -> None:
    """ai.html must NOT include research_coming_soon.html (Phase 17 stub removed)."""
    env = _get_jinja_env()
    src = _read_template(env, "pages/ai.html")
    assert "research_coming_soon" not in src, "research_coming_soon still included in ai.html"


def test_ai_page_no_top_flavor_descriptors() -> None:
    """ai.html must NOT have the Top Flavor Descriptors section (D-10 delete)."""
    env = _get_jinja_env()
    src = _read_template(env, "pages/ai.html")
    assert "flavor-descriptors" not in src, (
        "flavor-descriptors hx-get still present in ai.html"
        " — Top Flavor Descriptors must be deleted (D-10)"
    )


def test_ai_page_has_trends_card_include() -> None:
    """ai.html must include trends_card.html as the last section."""
    env = _get_jinja_env()
    src = _read_template(env, "pages/ai.html")
    assert "trends_card" in src, "ai.html missing trends_card include"


def test_research_form_has_sse_connect() -> None:
    """research_form.html must contain sse-connect for the SSE result region."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/research_form.html")
    assert "sse-connect" in src, "research_form.html missing sse-connect attribute"


def test_research_form_has_quota_counter() -> None:
    """research_form.html must contain research-quota counter element."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/research_form.html")
    assert "research-quota" in src, "research_form.html missing research-quota counter"


def test_research_result_no_safe_filter() -> None:
    """research_result.html must never use |safe on AI prose (T-19-21)."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/research_result.html")
    assert "|safe" not in src, "research_result.html uses |safe — XSS risk (T-19-21)"


def test_research_result_has_prediction_range() -> None:
    """research_result.html must render predicted_low, predicted_high, confidence, reasoning."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/research_result.html")
    assert "predicted_low" in src, "research_result.html missing predicted_low"
    assert "predicted_high" in src, "research_result.html missing predicted_high"
    assert "confidence" in src, "research_result.html missing confidence"
    assert "reasoning" in src, "research_result.html missing reasoning (Why: block)"


def test_research_result_has_wishlist_button() -> None:
    """research_result.html must have wishlist button posting to /ai/wishlist/add (AIX-06/D-05)."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/research_result.html")
    assert "/ai/wishlist/add" in src, "research_result.html missing /ai/wishlist/add button"
    assert "coffee_name" in src, "research_result.html missing coffee_name field for wishlist"
    assert "source_url" in src, "research_result.html missing source_url field for wishlist"


def test_preference_profile_prose_no_safe() -> None:
    """preference_profile_prose.html must never use |safe on AI prose (T-19-21)."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/preference_profile_prose.html")
    assert "|safe" not in src, "preference_profile_prose.html uses |safe — XSS risk (T-19-21)"


def test_trends_card_has_canvas_refs() -> None:
    """trends_card.html must have x-ref='ratingCanvas' and x-ref='flavorCanvas'."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/ai/trends_card.html")
    assert "ratingCanvas" in src, "trends_card.html missing x-ref='ratingCanvas'"
    assert "flavorCanvas" in src, "trends_card.html missing x-ref='flavorCanvas'"


# ---------------------------------------------------------------------------
# Task 3: Improve-brew fragments + brew form
# ---------------------------------------------------------------------------


def test_improve_result_no_safe() -> None:
    """improve_result.html must never use |safe on AI prose (T-19-21)."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/brew/improve_result.html")
    assert "|safe" not in src, "improve_result.html uses |safe — XSS risk (T-19-21)"


def test_improve_result_has_next_try() -> None:
    """improve_result.html must render next_try rationale fields."""
    env = _get_jinja_env()
    src = _read_template(env, "fragments/brew/improve_result.html")
    assert "next_try" in src, "improve_result.html missing next_try rendering"
    assert "rationale" in src, "improve_result.html missing rationale field"


def test_brew_form_has_improve_button() -> None:
    """brew_form.html must have an improve-brew affordance in edit mode (AIX-12/D-12)."""
    env = _get_jinja_env()
    src = _read_template(env, "pages/brew_form.html")
    assert "improve-brew" in src, (
        "brew_form.html missing improve-brew affordance"
        " — check for /ai/improve-brew/{session_id} reference"
    )
