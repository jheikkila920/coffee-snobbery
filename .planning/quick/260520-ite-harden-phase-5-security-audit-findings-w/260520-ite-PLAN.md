---
phase: quick-260520-ite
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - app/routers/brew.py
  - tests/routers/test_brew_list_csv.py
  - tests/ci/test_no_unsafe_jinja.py
autonomous: true
requirements: [W-01, W-02]

must_haves:
  truths:
    - "An oversized CSV upload (Content-Length > MAX_CSV_BYTES) is rejected BEFORE the multipart body is buffered, with the existing 'too large' error."
    - "The existing post-read size check remains as defense-in-depth for chunked / lying-Content-Length uploads."
    - "The Jinja safety grep test scans every .html under app/templates/ (pages/, fragments/, and any future subdir), not just pages/."
    - "All four forbidden patterns (|safe, hx-on:, hx-vals='js:', hx-headers='js:') are still enforced after widening, and the existing template tree passes."
  artifacts:
    - path: "app/routers/brew.py"
      provides: "import_sessions Content-Length pre-check + corrected docstring"
      contains: "content-length"
    - path: "tests/routers/test_brew_list_csv.py"
      provides: "W-01 oversized-Content-Length rejection test"
      contains: "content-length"
    - path: "tests/ci/test_no_unsafe_jinja.py"
      provides: "TEMPLATES_DIR scope covering all of app/templates/"
      contains: "TEMPLATES_DIR"
  key_links:
    - from: "app/routers/brew.py import_sessions"
      to: "csv_io_service.MAX_CSV_BYTES"
      via: "Content-Length header compared to ceiling before await request.form()"
      pattern: "content-length.*MAX_CSV_BYTES"
    - from: "tests/ci/test_no_unsafe_jinja.py"
      to: "app/templates/"
      via: "TEMPLATES_DIR.rglob('*.html') parametrize"
      pattern: "TEMPLATES_DIR = Path\\(\"app/templates\"\\)"
---

<objective>
Harden two non-blocking findings from the Phase 5 security audit (`.planning/phases/05-brew-sessions/05-SECURITY.md`, "Audit Findings"):

- **W-01 (T-05-11 / T-05-27):** the CSV import handler checks the size ceiling only AFTER `await upload.read()`, so the whole multipart body buffers before rejection. Add a `Content-Length` header pre-check before `await request.form()`.
- **W-02 (T-05-19 / T-05-28):** the CI Jinja-safety grep test scans only `app/templates/pages/`, missing `fragments/`. Widen it to `app/templates/`.

Purpose: close two known gaps that strengthen (never weaken) existing guards, before Phase 6 ships new upload paths and fragments.
Output: a Content-Length pre-check + test (W-01) and a widened template-safety test (W-02). Two independent atomic commits.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<!-- Audit that produced these findings -->
@.planning/phases/05-brew-sessions/05-SECURITY.md

<interfaces>
<!-- Extracted from codebase; executor should NOT need to explore further. -->

From app/services/csv_io.py (constants the handler/tests reference):
```python
MAX_CSV_BYTES = 5 * 1024 * 1024
ALLOWED_CSV_CONTENT_TYPES = frozenset(...)  # csv content-type allow-list
```

From app/routers/brew.py — current import_sessions handler (POST /brew/import), the EXACT current body to modify:
```python
@router.post("/import", response_class=HTMLResponse)
async def import_sessions(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Single-transaction CSV import (BREW-11) → per-row result fragment.

    Enforces a content-type allow-list + a size ceiling BEFORE buffering the
    full body (T-05-27 DoS guard), then hands the bytes to
    :func:`csv_io.import_brews` ...
    """
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        return _render_import_results(request, outcomes=[], error="Choose a CSV file to import.")

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in csv_io_service.ALLOWED_CSV_CONTENT_TYPES:
        return _render_import_results(
            request, outcomes=[], error="That file is not a CSV. Export a CSV and try again."
        )

    raw_bytes = await upload.read()
    if len(raw_bytes) > csv_io_service.MAX_CSV_BYTES:
        return _render_import_results(
            request, outcomes=[], error="That file is too large to import."
        )

    outcomes = csv_io_service.import_brews(db, raw_bytes=raw_bytes, by_user_id=user.id)
    return _render_import_results(request, outcomes=outcomes, error=None)
```

The shared error renderer (already exists, do not change):
```python
def _render_import_results(request: Request, *, outcomes: list[Any], error: str | None) -> Response:
    ...  # renders fragments/csv_import_results.html
```

From tests/routers/test_brew_list_csv.py — patterns the W-01 test MUST reuse:
- Skip gates: `_require_postgres()`, `_require_p5_migration_applied()`, `_require_brew_router()` called at the top of each test.
- Authed client + CSRF: `_authed_client(app, seeded_regular_user["signed_cookie"])` (sets session cookie, primes a real double-submit CSRF pair).
- CSV body helper: `_csv_bytes(rows: list[str]) -> bytes` (prepends the canonical header).
- Fixtures used by import tests: `app`, `seeded_regular_user`, `clean_brew_list`.
- Existing import POST shape: `client.post("/brew/import", files={"file": ("sessions.csv", io.BytesIO(_csv_bytes(rows)), "text/csv")})`.

From tests/ci/test_no_unsafe_jinja.py — current scoping to change:
```python
PAGES_DIR = Path("app/templates/pages")
# ...
@pytest.mark.parametrize(
    "template_path",
    list(PAGES_DIR.rglob("*.html")) if PAGES_DIR.exists() else [],
)
def test_template_safety(template_path: Path) -> None:
    """Every ``.html`` under ``app/templates/pages/`` is free of forbidden patterns."""
    ...
```
FORBIDDEN_PATTERNS and `_strip_comments` (Jinja `{# #}` + HTML `<!-- -->` strip) stay exactly as-is.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: W-01 — Content-Length pre-check on CSV import + test</name>
  <files>app/routers/brew.py, tests/routers/test_brew_list_csv.py</files>
  <behavior>
    - A POST /brew/import whose `Content-Length` header exceeds `MAX_CSV_BYTES` is rejected at the very top of the handler, BEFORE `await request.form()` buffers the body, returning the existing "That file is too large to import." error fragment.
    - The body is NOT processed by `csv_io_service.import_brews` when the pre-check rejects.
    - A normal in-bounds upload still flows through unchanged (existing tests `test_import_outcomes_http`, `test_import_requires_csrf` must still pass — no regression).
    - The existing post-read `len(raw_bytes) > MAX_CSV_BYTES` branch remains untouched as defense-in-depth.
  </behavior>
  <action>
    In `app/routers/brew.py`, edit ONLY the `import_sessions` handler. As the FIRST statements inside the function body (before `form = await request.form()`):
    read `request.headers.get("content-length")`; if it is present, consists only of digits (`str.isdigit()`), and `int(value) > csv_io_service.MAX_CSV_BYTES`, return `_render_import_results(request, outcomes=[], error="That file is too large to import.")` immediately. Reuse the EXACT error string the existing post-read branch uses so the response shape is identical.
    Do NOT add slack/allowance — compare the raw header against `MAX_CSV_BYTES` directly (per W-01: Content-Length bounds the whole multipart body, multipart overhead is negligible at a 5 MiB ceiling, keep it simple). Guard non-digit / absent values: only act when `isdigit()` is true, otherwise fall through to the existing flow (chunked transfer-encoding has no Content-Length).
    KEEP the existing post-read `len(raw_bytes) > MAX_CSV_BYTES` check unchanged — it is the defense-in-depth layer for absent or lying Content-Length.
    Update the docstring so its claim matches reality: the header pre-check rejects oversized uploads BEFORE the body is buffered, and the post-read length check is defense-in-depth (Content-Length may be absent under chunked transfer-encoding or under-report a lying client). Do not change any other handler, import, or surrounding code.

    In `tests/routers/test_brew_list_csv.py`, add a new test alongside the existing import tests (after `test_import_requires_csrf`). Follow the module's established patterns: call the three `_require_*` skip gates first, use `_authed_client(app, seeded_regular_user["signed_cookie"])`, and the `app` / `seeded_regular_user` / `clean_brew_list` fixtures. The test must POST to `/brew/import` with a `Content-Length` header that exceeds `csv_io_service.MAX_CSV_BYTES` and assert (a) the response carries the "too large" error text and (b) the body was rejected at the pre-check (no rows inserted — assert `len(svc.list_brew_sessions(db, by_user_id=uid)) == 0` after, mirroring `test_import_outcomes_http`'s post-state assertion style).
    Note on forcing the header: TestClient/httpx auto-sets Content-Length, so send a SMALL body and explicitly override the header to an oversized value (e.g. set `headers={"Content-Length": str(MAX_CSV_BYTES + 1)}` on the request, or via `client.headers`). If httpx refuses to honor the manual override with the existing client style, fall back to the most faithful achievable approach (e.g. monkeypatching the request header, or asserting the pre-check via a direct call) and document the limitation in the test docstring. Do not weaken the assertion silently — report honestly if the header cannot be forced.
  </action>
  <verify>
    <automated>docker compose exec coffee-snobbery python -m pytest tests/routers/test_brew_list_csv.py -q  (install pytest first per CLAUDE.md if not baked; run locally if a venv exists. If the suite cannot run, report honestly and at minimum run: ruff check app/routers/brew.py tests/routers/test_brew_list_csv.py)</automated>
  </verify>
  <done>
    `import_sessions` rejects oversized Content-Length before `await request.form()`; the post-read check is unchanged; the docstring matches the new behavior; the new test passes (or, if the suite is unrunnable, ruff is clean and the limitation is reported honestly); existing import tests still pass.
  </done>
</task>

<task type="auto">
  <name>Task 2: W-02 — Widen Jinja safety grep test to all templates</name>
  <files>tests/ci/test_no_unsafe_jinja.py</files>
  <action>
    In `tests/ci/test_no_unsafe_jinja.py`, rename `PAGES_DIR = Path("app/templates/pages")` to `TEMPLATES_DIR = Path("app/templates")` so the rglob covers `pages/`, `fragments/`, and any future subdir. Update every reference to the old name: the `@pytest.mark.parametrize` list (`TEMPLATES_DIR.rglob("*.html")` and `TEMPLATES_DIR.exists()`), the test function's docstring/asserts, and the module docstring + inline comments — change all "pages/" wording to "templates/". Leave `FORBIDDEN_PATTERNS`, `_strip_comments`, and the four regex patterns exactly as-is. Do not change matching logic; only the scanned root and its prose.
    Context (verified by the orchestrator, re-confirm by running the test): every existing `|safe` / `hx-on:` / `hx-vals='js:'` / `hx-headers='js:'` under `app/templates/` lives inside a Jinja `{# #}` or HTML `<!-- -->` comment that `_strip_comments` removes, so widening introduces no false failures.
  </action>
  <verify>
    <automated>docker compose exec coffee-snobbery python -m pytest tests/ci/test_no_unsafe_jinja.py -v  (install pytest first per CLAUDE.md if not baked; run locally if a venv exists — the test reads files only, no DB needed. Confirm it now collects fragments/ templates and all pass. If unrunnable, report honestly and run: ruff check tests/ci/test_no_unsafe_jinja.py)</automated>
  </verify>
  <done>
    `TEMPLATES_DIR = Path("app/templates")` replaces `PAGES_DIR`; parametrize, asserts, docstrings, and comments reference `templates/`; the test collects every `.html` under `app/templates/` (pages + fragments) and all cases pass; forbidden-pattern logic unchanged.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → POST /brew/import | Untrusted multipart upload (file bytes + size) crosses here. |
| template authoring → rendered HTML | Trusted authors, but CI must mechanically prevent unsafe Jinja from reaching users. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-11 / T-05-27 | Denial of Service | POST /brew/import oversized upload | mitigate | Content-Length pre-check rejects > MAX_CSV_BYTES before `await request.form()` buffers the body (W-01); existing post-read check kept as defense-in-depth for chunked / lying clients. |
| T-05-19 / T-05-28 | Tampering (stored XSS) | app/templates/ (pages + fragments) | mitigate | Widen CI grep test to scan all of `app/templates/`, mechanically enforcing the `|safe` / `hx-on:` / `hx-vals='js:'` / `hx-headers='js:'` ban on fragments and future subdirs (W-02). |
| — | (regression risk) | existing CSRF + security headers | accept | Changes only ADD guards; no existing check (CSRF, content-type allow-list, post-read size check, security headers) is removed or weakened. Existing import tests (incl. `test_import_requires_csrf`) re-run to confirm. |
</threat_model>

<verification>
- W-01: `import_sessions` reads `Content-Length` and rejects oversized uploads before `await request.form()`; post-read `MAX_CSV_BYTES` check still present; docstring corrected.
- W-01: new test in `tests/routers/test_brew_list_csv.py` proves an oversized Content-Length is rejected with the "too large" error and no rows inserted.
- W-02: `tests/ci/test_no_unsafe_jinja.py` scans `app/templates/` (pages + fragments); all forbidden patterns still enforced; existing tree passes.
- No existing guard removed; `ruff check` clean on all touched files; `ruff format` applied.
</verification>

<success_criteria>
- Oversized CSV uploads rejected before the body buffers (W-01) AND the post-read defense-in-depth check retained.
- Jinja safety test covers every template under `app/templates/` (W-02).
- Affected test modules pass (`tests/routers/test_brew_list_csv.py`, `tests/ci/test_no_unsafe_jinja.py`) — or, if the suite cannot run in the available environment, ruff is clean and the inability to run is reported honestly.
- Two independent atomic commits (Task 1 = W-01, Task 2 = W-02), conventional-commit style.
- No CSRF / security-header / encryption guard weakened.
</success_criteria>

<output>
After completion, create `.planning/quick/260520-ite-harden-phase-5-security-audit-findings-w/260520-ite-SUMMARY.md`
</output>
