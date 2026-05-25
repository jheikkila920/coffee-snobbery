"""check_c4_dark.py — structural checker for the C4 dark-mode + C1 safe-area contract.

Runs plain string/substring assertions against source files. No app imports, no
third-party deps, no eval, no x-model. Exits 0 on success, non-zero with a
descriptive message on the first failure.

Default mode (no flags): checks config + CSS + JS component.
--templates flag: additionally checks base.html and config_hub.html.

Usage:
    python scripts/check_c4_dark.py
    python scripts/check_c4_dark.py --templates
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  ok  {msg}")


def check_default() -> None:
    """Default mode: config + CSS + JS component checks."""
    print("check_c4_dark.py — default mode")

    # --- tailwind.config.js ---
    config_path = REPO_ROOT / "tailwind.config.js"
    config_text = config_path.read_text(encoding="utf-8")

    # (1) darkMode is 'selector' or 'class' (v3 canonical values)
    if "'selector'" not in config_text and '"selector"' not in config_text:
        if "'class'" not in config_text and '"class"' not in config_text:
            fail(
                f"{config_path}: darkMode is not set to 'selector' or 'class'. "
                "Expected: darkMode: 'selector'  (v3.4.1+ canonical)."
            )
    ok("tailwind.config.js: darkMode is 'selector' or 'class'")

    # (2) No @custom-variant anywhere in config or CSS
    if "@custom-variant" in config_text:
        fail(
            f"{config_path}: @custom-variant found — this is Tailwind v4 syntax "
            "and will silently no-op or break the v3.4.17 build (Pitfall 1)."
        )
    ok("tailwind.config.js: no @custom-variant (v4-only syntax)")

    css_path = REPO_ROOT / "app" / "static" / "css" / "tailwind.src.css"
    css_text = css_path.read_text(encoding="utf-8")

    if "@custom-variant" in css_text:
        fail(
            f"{css_path}: @custom-variant found — this is Tailwind v4 syntax "
            "and will silently no-op or break the v3.4.17 build (Pitfall 1)."
        )
    ok("tailwind.src.css: no @custom-variant (v4-only syntax)")

    # (3) tailwind.src.css contains .dark-scoped input and anchor rules
    if ".dark input" not in css_text:
        fail(
            f"{css_path}: .dark input rule not found. "
            "Expected class-scoped dark form-control rules (C4)."
        )
    ok("tailwind.src.css: .dark input rule present")

    if ".dark a" not in css_text:
        fail(f"{css_path}: .dark a rule not found. Expected class-scoped dark anchor rules (C4).")
    ok("tailwind.src.css: .dark a rule present")

    # (4) No @media prefers-color-scheme dark blocks remain
    if "prefers-color-scheme: dark" in css_text:
        fail(
            f"{css_path}: @media (prefers-color-scheme: dark) block still present. "
            "All dark-mode CSS must be .dark class-scoped so an explicit Light override wins (C4)."
        )
    ok("tailwind.src.css: no @media prefers-color-scheme: dark blocks remain")

    # --- dark-toggle.js ---
    toggle_path = REPO_ROOT / "app" / "static" / "js" / "alpine-components" / "dark-toggle.js"
    toggle_text = toggle_path.read_text(encoding="utf-8")

    # (5) Alpine.data('darkToggle') registration and snobbery:theme key
    if (
        "Alpine.data('darkToggle'" not in toggle_text
        and 'Alpine.data("darkToggle"' not in toggle_text
    ):
        fail(
            f"{toggle_path}: Alpine.data('darkToggle') registration not found. "
            "Component must register via Alpine.data (CSP-compliant pattern)."
        )
    ok("dark-toggle.js: Alpine.data('darkToggle') registration found")

    if "snobbery:theme" not in toggle_text:
        fail(
            f"{toggle_path}: localStorage key 'snobbery:theme' not found. "
            "Component must use this key for theme persistence (C4)."
        )
    ok("dark-toggle.js: snobbery:theme key present")

    # (6) No eval() and no x-model attribute usage in the component.
    # Strip single-line JS comments before checking to avoid false positives
    # from comment text that mentions forbidden patterns by name.
    import re

    toggle_no_comments = re.sub(r"//[^\n]*", "", toggle_text)
    if "eval(" in toggle_no_comments:
        fail(f"{toggle_path}: eval() found — forbidden by ADR 0001 (strict CSP, no unsafe-eval).")
    ok("dark-toggle.js: no eval()")

    if "x-model" in toggle_no_comments:
        fail(
            f"{toggle_path}: x-model found — forbidden in @alpinejs/csp build (ADR 0001). "
            "Use x-on:click + named methods instead."
        )
    ok("dark-toggle.js: no x-model")

    print("\nAll default checks passed.")


def check_templates() -> None:
    """--templates mode: additionally check base.html and config_hub.html."""
    print("check_c4_dark.py — templates mode")

    base_path = REPO_ROOT / "app" / "templates" / "base.html"
    base_text = base_path.read_text(encoding="utf-8")

    css_link_pos = base_text.find("tailwind_css_path")
    if css_link_pos == -1:
        fail(
            f"{base_path}: tailwind_css_path link not found — cannot verify FOUC script placement."
        )

    # (7) base.html contains a nonce'd inline script with snobbery:theme BEFORE the stylesheet link.
    # Strip Jinja comments first so we find the actual script occurrence, not a comment mention.
    import re as _re

    base_no_jinja_comments = _re.sub(r"\{#.*?#\}", "", base_text, flags=_re.DOTALL)
    fouc_marker = "snobbery:theme"
    fouc_pos_nc = base_no_jinja_comments.find(fouc_marker)
    if fouc_pos_nc == -1:
        fail(
            f"{base_path}: 'snobbery:theme' not found outside Jinja comments. "
            "No-FOUC inline head script must reference this key (C4)."
        )
    ok("base.html: snobbery:theme reference found")

    # css_link_pos is based on raw text; redo with comment-stripped text for comparison
    css_link_pos_nc = base_no_jinja_comments.find("tailwind_css_path")
    if fouc_pos_nc > css_link_pos_nc:
        fail(
            f"{base_path}: 'snobbery:theme' reference appears AFTER the Tailwind stylesheet link. "
            "The no-FOUC script must run BEFORE the CSS link to prevent "
            "flash-of-wrong-theme (C4, Pitfall 4)."
        )
    ok("base.html: snobbery:theme reference appears before the Tailwind stylesheet link (no-FOUC)")

    # Check the no-FOUC script carries a nonce — search backward from the marker in stripped text
    fouc_script_start = base_no_jinja_comments.rfind("<script", 0, fouc_pos_nc)
    if fouc_script_start == -1:
        fail(f"{base_path}: could not locate the <script> tag containing snobbery:theme.")
    fouc_script_tag_end = base_no_jinja_comments.find(">", fouc_script_start)
    fouc_script_tag = base_no_jinja_comments[fouc_script_start : fouc_script_tag_end + 1]
    if "nonce=" not in fouc_script_tag:
        fail(
            f"{base_path}: the no-FOUC script tag does not carry nonce=. "
            "Strict CSP blocks inline scripts without a nonce (Pitfall 3)."
        )
    ok("base.html: no-FOUC script tag carries nonce=")

    # (8) base.html loads dark-toggle.js with defer and nonce
    if "dark-toggle.js" not in base_text:
        fail(
            f"{base_path}: dark-toggle.js script tag not found. "
            "Component must be loaded before the @alpinejs/csp core (C4)."
        )

    # Find the dark-toggle.js script tag and check it has defer and nonce.
    # Use comment-stripped text to avoid false matches in Jinja comments.
    toggle_tag_pos_nc = base_no_jinja_comments.find("dark-toggle.js")
    toggle_script_start = base_no_jinja_comments.rfind("<script", 0, toggle_tag_pos_nc)
    toggle_script_tag_end = base_no_jinja_comments.find(">", toggle_script_start)
    toggle_script_tag = base_no_jinja_comments[toggle_script_start : toggle_script_tag_end + 1]
    if "defer" not in toggle_script_tag:
        fail(
            f"{base_path}: dark-toggle.js script tag is missing 'defer' attribute. "
            "Alpine component scripts must be deferred (C4)."
        )
    if "nonce=" not in toggle_script_tag:
        fail(
            f"{base_path}: dark-toggle.js script tag is missing 'nonce=' attribute. "
            "Strict CSP requires nonce on all script tags (ADR 0001)."
        )
    ok("base.html: dark-toggle.js loaded with defer + nonce")

    # Verify dark-toggle.js loads BEFORE the @alpinejs/csp core script src tag.
    # Use comment-stripped text so comment mentions of @alpinejs/csp don't mislead.
    alpinejs_pos_nc = base_no_jinja_comments.find("cdn.jsdelivr.net/npm/@alpinejs/csp")
    if alpinejs_pos_nc == -1:
        fail(f"{base_path}: @alpinejs/csp CDN script not found — cannot verify load order.")
    if toggle_tag_pos_nc > alpinejs_pos_nc:
        fail(
            f"{base_path}: dark-toggle.js is loaded AFTER @alpinejs/csp core. "
            "Alpine.data registrations must exist before Alpine boots (C4)."
        )
    ok("base.html: dark-toggle.js loads before @alpinejs/csp core")

    # (9) base.html mobile top strip contains safe-area-inset-top
    if "safe-area-inset-top" not in base_text:
        fail(
            f"{base_path}: safe-area-inset-top not found on the mobile top strip. "
            "Expected pt-[env(safe-area-inset-top)] utility on the md:hidden "
            "top strip element (C1)."
        )
    ok("base.html: safe-area-inset-top present on mobile strip")

    # (10) config_hub.html: x-data="darkToggle" and setTheme calls
    hub_path = REPO_ROOT / "app" / "templates" / "pages" / "config_hub.html"
    hub_text = hub_path.read_text(encoding="utf-8")

    if 'x-data="darkToggle"' not in hub_text and "x-data='darkToggle'" not in hub_text:
        fail(
            f'{hub_path}: x-data="darkToggle" not found. '
            "Config hub must include the dark toggle UI block (C4)."
        )
    ok('config_hub.html: x-data="darkToggle" present')

    if "setTheme(" not in hub_text:
        fail(
            f"{hub_path}: setTheme( call not found. "
            "Dark toggle buttons must call setTheme('auto'|'light'|'dark') (C4)."
        )
    ok("config_hub.html: setTheme() calls present")

    print("\nAll template checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Structural checker for C4 dark-mode + C1 safe-area contract."
    )
    parser.add_argument(
        "--templates",
        action="store_true",
        help="Also check base.html and config_hub.html (requires Task 2 complete).",
    )
    args = parser.parse_args()

    check_default()
    if args.templates:
        check_templates()


if __name__ == "__main__":
    main()
