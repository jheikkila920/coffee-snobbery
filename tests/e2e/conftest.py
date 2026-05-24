"""Playwright e2e conftest — session browser + viewport parametrization + auth seeding.

Local / pre-deploy only (D-05 / TEST-06). Excluded from CI via ``--ignore=tests/e2e``
in the GitHub Actions workflow (D-06). Requires the compose stack to be running and
Playwright chromium to be installed (baked into the dev image by Plan 12-05).

If Playwright is not installed on the host the entire module skips cleanly (never
errors at collection). SNOB_CI=1 does not enforce Playwright presence because CI
excludes this directory entirely.

Auth-seeding mirrors test_phase02_smoke.py:
  GET /setup → extract csrftoken cookie → POST /setup with username/password
  → extract session_id cookie → inject into Playwright BrowserContext so all
  navigations are authenticated.

If the app is already set up (zero-user guard fails), falls back to POST /login with
the known credentials. This makes the fixture idempotent against a pre-seeded stack.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

# ── Playwright availability guard ─────────────────────────────────────────────
# Import the sync_playwright factory at module level so collection errors surface
# only as skips, not import failures. Tests in this package rely on this guard.

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


@pytest.fixture(scope="session", autouse=True)
def _require_playwright() -> None:
    """Skip the entire e2e suite cleanly when Playwright is not installed."""
    if not _PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed — e2e suite requires the dev image (Plan 12-05)")


# ── base_url ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def base_url() -> str:
    """Target base URL for the running app.

    Override via ``SNOB_E2E_BASE_URL`` env var.
    - Host bind (local dev): ``http://127.0.0.1:8080`` (default)
    - In-network container run: ``http://coffee-snobbery:8000``
    """
    return os.environ.get("SNOB_E2E_BASE_URL", "http://127.0.0.1:8080")


# ── session-scoped browser ────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def browser() -> Browser:
    """Session-scoped headless Chromium browser.

    Yields the Browser instance; closes it after the session ends.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


# ── auth helpers ──────────────────────────────────────────────────────────────

_E2E_USERNAME = "e2etest"
_E2E_PASSWORD = "twelve-chars-e2e-pw"
_E2E_EMAIL = "e2etest@example.com"


def _seed_session(base_url: str) -> tuple[str, str]:
    """Return (session_id_cookie_value, csrf_cookie_value) for an authenticated user.

    Tries /setup first (works on a virgin DB). Falls back to /login if the user
    already exists (idempotent against a pre-seeded stack).

    Uses the stdlib ``urllib.request`` to avoid adding httpx as a hard dependency
    here — the dev image has it, but the fallback keeps the dependency surface
    minimal for this fixture.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    # ── Step 1: GET /setup to obtain the CSRF cookie ────────────────────────
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    setup_url = f"{base_url}/setup"

    try:
        resp = opener.open(setup_url)
        body = resp.read().decode("utf-8", errors="replace")
        # Extract csrftoken from Set-Cookie if present, otherwise parse body meta
        csrf_token: str = ""
        # The CSRF double-submit cookie is named 'csrftoken'
        for header in resp.headers.get_all("set-cookie") or []:
            m = re.search(r"csrftoken=([^;]+)", header)
            if m:
                csrf_token = m.group(1)
        if not csrf_token:
            # Fallback: try the meta tag
            m2 = re.search(r'content="([^"]+)"[^>]*name="csrf-token"', body)
            if not m2:
                m2 = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', body)
            if m2:
                csrf_token = m2.group(1)
    except urllib.error.HTTPError:
        csrf_token = ""

    # ── Step 2: POST /setup to create the first user ─────────────────────────
    setup_succeeded = False
    session_id = ""
    if csrf_token:
        post_data = urllib.parse.urlencode(
            {
                "X-CSRF-Token": csrf_token,
                "username": _E2E_USERNAME,
                "email": _E2E_EMAIL,
                "password": _E2E_PASSWORD,
            }
        ).encode()
        req = urllib.request.Request(
            setup_url,
            data=post_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-Token": csrf_token,
                "Cookie": f"csrftoken={csrf_token}",
            },
        )

        # Disable auto-redirect so we can read Set-Cookie from the 303 response
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
                return None

        no_redir_opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPCookieProcessor()
        )
        try:
            resp2 = no_redir_opener.open(req)
            for header in resp2.headers.get_all("set-cookie") or []:
                m = re.search(r"session_id=([^;]+)", header)
                if m:
                    session_id = m.group(1)
                    setup_succeeded = True
        except urllib.error.HTTPError as e:
            if e.code in (303, 302):
                for header in e.headers.get_all("set-cookie") or []:
                    m = re.search(r"session_id=([^;]+)", header)
                    if m:
                        session_id = m.group(1)
                        setup_succeeded = True

    # ── Step 3: Fallback — POST /login (app already set up) ──────────────────
    if not setup_succeeded or not session_id:
        # First GET /login to refresh the CSRF token
        login_url = f"{base_url}/login"
        try:
            login_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            login_resp = login_opener.open(login_url)
            csrf_token2 = ""
            for header in login_resp.headers.get_all("set-cookie") or []:
                m = re.search(r"csrftoken=([^;]+)", header)
                if m:
                    csrf_token2 = m.group(1)
            if not csrf_token2:
                csrf_token2 = csrf_token  # reuse if rotation didn't happen
        except Exception:
            csrf_token2 = csrf_token

        login_data = urllib.parse.urlencode(
            {
                "X-CSRF-Token": csrf_token2,
                "username": _E2E_USERNAME,
                "password": _E2E_PASSWORD,
            }
        ).encode()

        class _NoRedirect2(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
                return None

        login_req = urllib.request.Request(
            login_url,
            data=login_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-Token": csrf_token2,
                "Cookie": f"csrftoken={csrf_token2}",
            },
        )
        no_redir_opener2 = urllib.request.build_opener(
            _NoRedirect2(), urllib.request.HTTPCookieProcessor()
        )
        try:
            login_resp2 = no_redir_opener2.open(login_req)
            for header in login_resp2.headers.get_all("set-cookie") or []:
                m = re.search(r"session_id=([^;]+)", header)
                if m:
                    session_id = m.group(1)
        except urllib.error.HTTPError as e:
            if e.code in (303, 302):
                for header in e.headers.get_all("set-cookie") or []:
                    m = re.search(r"session_id=([^;]+)", header)
                    if m:
                        session_id = m.group(1)

    if not session_id:
        pytest.skip(
            f"e2e auth seeding failed — could not obtain session_id from {base_url}. "
            "Is the compose stack running? See Plan 12-06 task-3 verify steps."
        )

    return session_id, csrf_token or ""


# ── session-scoped auth seed ──────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _auth_cookies(base_url: str) -> dict[str, str]:
    """Return ``{session_id, csrftoken}`` for the e2e test user.

    Session-scoped so auth is seeded once per pytest run, not per test.
    Skips the suite cleanly if the app is unreachable.
    """
    try:
        session_id, csrf_token = _seed_session(base_url)
    except Exception as exc:
        pytest.skip(f"e2e auth seeding raised an unexpected error: {exc}")
        return {}  # pragma: no cover
    return {"session_id": session_id, "csrftoken": csrf_token}


# ── parametrized viewport page ────────────────────────────────────────────────


@pytest.fixture(params=[(375, 667), (390, 844)], ids=["375x667", "390x844"])
def page_at_viewport(
    request: pytest.FixtureRequest,
    browser: Browser,
    base_url: str,
    _auth_cookies: dict[str, str],
) -> Page:
    """Yield a Playwright Page at the parametrized mobile viewport.

    The page's BrowserContext has the auth session cookie injected so every
    navigation is authenticated. Creates a fresh context per test function and
    closes it on teardown.

    Parametrized across:
    - ``375x667`` (iPhone SE / common 375px baseline)
    - ``390x844``  (iPhone 14 Pro)
    """
    width, height = request.param
    ctx: BrowserContext = browser.new_context(viewport={"width": width, "height": height})
    # Inject auth + CSRF cookies so navigations bypass the login gate.
    cookies = []
    if _auth_cookies.get("session_id"):
        cookies.append(
            {
                "name": "session_id",
                "value": _auth_cookies["session_id"],
                "url": base_url,
            }
        )
    if _auth_cookies.get("csrftoken"):
        cookies.append(
            {
                "name": "csrftoken",
                "value": _auth_cookies["csrftoken"],
                "url": base_url,
            }
        )
    if cookies:
        ctx.add_cookies(cookies)
    page: Page = ctx.new_page()
    yield page
    ctx.close()
