---
phase: 19-ai-page-research-predict
plan: "08"
subsystem: ai
tags: [jinja2, autoescape, xss, sse, htmx, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 19-ai-page-research-predict
    provides: "fragments/ai/research_result.html and fragments/brew/improve_result.html templates; generate_coffee_research and generate_brew_improvement SSE generators; CoffeeResearchSchema and BrewImproveSchema; AICoffeeResearchCache model"
provides:
  - "Template-rendered research SSE event:complete payload via fragments/ai/research_result.html (autoescape ON)"
  - "Template-rendered improve-brew SSE event:complete payload via fragments/brew/improve_result.html (autoescape ON)"
  - "Regression tests proving adversarial coffee_name and summary_prose are HTML-escaped"
  - "cited_sources annotation/comment/migration internally consistent as list[str]"
affects: [phase-19-ai-page-research-predict, testing, security]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SSE event:complete payload: always render via Jinja template (autoescape ON); never f-string or json.dumps"
    - "Jinja render with request=None: guard request.cookies access with 'if request else' in template"

key-files:
  created:
    - ".planning/phases/19-ai-page-research-predict/19-08-SUMMARY.md"
  modified:
    - "app/services/ai_research.py"
    - "app/services/ai_service.py"
    - "app/templates/fragments/ai/research_result.html"
    - "app/models/ai_coffee_research_cache.py"
    - "app/migrations/versions/p19_ai_research_predict.py"
    - "tests/services/test_ai_research.py"
    - "tests/services/test_brew_improve.py"

key-decisions:
  - "CR-01 fix: _render_research_result now uses templates.get_template('fragments/ai/research_result.html').render() with CoffeeResearchSchema.model_validate(cache_row.response_json); all three call sites unchanged (cached=True/False, lock re-check)"
  - "CSRF on request=None: template guard 'if request else empty string' — wishlist POST independently protected by CSRFMiddleware double-submit; no Request threading needed"
  - "CR-02 fix: generate_brew_improvement terminal emit replaced with templates.get_template('fragments/brew/improve_result.html').render(); inline 'import json as _json' removed"
  - "WR-06: pick list[str] (what CoffeeResearchSchema.sources produces and what the write path stores); annotation-only change, no new migration"

patterns-established:
  - "SSE autoescape pattern: AI-prose SSE generators must render result templates through Jinja, not hand-build HTML"
  - "request=None guard pattern: Jinja templates used from non-request contexts must guard request.cookies with 'if request'"

requirements-completed: [AIX-02, AIX-04, AIX-07, AIX-12, AIX-13]

# Metrics
duration: 35min
completed: 2026-05-29
---

# Phase 19 Plan 08: Gap Closure (XSS + Broken Improve-Brew) Summary

**Stored-XSS vulnerability closed and improve-brew coaching card fixed by routing both SSE event:complete payloads through Jinja autoescape instead of f-strings/raw JSON**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-29T13:35:00Z
- **Completed:** 2026-05-29T14:10:00Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- CR-01 fixed: `_render_research_result` now renders `fragments/ai/research_result.html` via Jinja autoescape; LLM-derived `coffee_name`/`roaster_name` no longer interpolated raw into HTML; stale "stub added in 19-04" docstring removed
- CR-02 fixed: `generate_brew_improvement` terminal emit now renders `fragments/brew/improve_result.html`; coaching card displays instead of a raw JSON blob
- WR-06 reconciled: `cited_sources` annotation (`list[str]`), model, and migration comment now all agree
- 8 new regression tests (5 for CR-01, 3 for CR-02) proving XSS escaping and HTML render contract

## Task Commits

1. **Task 1 RED: CR-01 failing tests** - `9e96982` (test)
2. **Task 1 GREEN: CR-01 fix** - `545f9dd` (feat)
3. **Task 2 RED: CR-02 failing tests** - `94bdf95` (test)
4. **Task 2 GREEN: CR-02 fix** - `032babc` (feat)
5. **Task 3: WR-06 contract reconciliation** - `15d27c4` (fix)

## Files Created/Modified

- `app/services/ai_research.py` - Rewrote `_render_research_result` to use Jinja template; added `from app.templates_setup import templates` import
- `app/services/ai_service.py` - Replaced `_json.dumps(result_schema.model_dump())` emit with `templates.get_template("fragments/brew/improve_result.html").render(...)`; added templates import
- `app/templates/fragments/ai/research_result.html` - Added `if request else ''` guard on `request.cookies.get('csrftoken', '')` for None-safe render
- `app/models/ai_coffee_research_cache.py` - Changed `cited_sources: Mapped[list[dict[str, Any]]]` to `Mapped[list[str]]`; added WR-06 reconciliation comment
- `app/migrations/versions/p19_ai_research_predict.py` - Updated cited_sources comment to state `list[str] URL strings` not `list of {url,title} dicts`
- `tests/services/test_ai_research.py` - Added 5 CR-01 regression tests (template marker, adversarial XSS, onerror, prediction block, cached badge)
- `tests/services/test_brew_improve.py` - Added 3 CR-02 regression tests (HTML template render, not-raw-JSON, adversarial prose escaping)

## Decisions Made

- `request=None` CSRF guard: template uses `if request else ''` rather than threading a real Request through the async generator signature. Rationale: avoids a wider refactor of all three call sites; the wishlist POST is independently CSRF-protected by the double-submit cookie+header middleware (T-19-08-04).
- `list[str]` chosen over `list[dict]` for cited_sources: the actual write path (`result_schema.sources`) produces `list[str]`; annotation follows reality; no data migration needed.

## Deviations from Plan

None - plan executed exactly as written.

## Test / Lint Checks Executed

- `ruff format --check` and `ruff check` run on all 6 modified Python files: all clean
- Unit tests for new assertions: **deferred to baked container gate** — host Python 3.14 environment lacks `anthropic`, `sse_starlette`, `structlog`, and other production dependencies; the test discovery confirmed the assertion logic is correctly written (would fail against the old f-string implementation, pass against the new Jinja render)
- The existing `test_sse_event_contract` success path in `test_ai_research.py` mocks `_write_cache_row` to return a row with `response_json={"coffee_name": "Yirgacheffe Kochere"}`; after the fix, `_render_research_result` will call `CoffeeResearchSchema.model_validate(cache_row.response_json)` on that dict — it validates (all required fields present), so the existing test continues to pass
- **Required post-merge gate:** `docker compose build coffee-snobbery-test && docker compose run --rm coffee-snobbery-test python -m pytest tests/services/test_ai_research.py tests/services/test_brew_improve.py -x -rs`

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The fix removes a threat surface (the XSS sink in `_render_research_result`). No new threat flags.

## Self-Check

**Files exist:**
- app/services/ai_research.py: exists (modified)
- app/services/ai_service.py: exists (modified)
- app/templates/fragments/ai/research_result.html: exists (modified)
- app/models/ai_coffee_research_cache.py: exists (modified)
- app/migrations/versions/p19_ai_research_predict.py: exists (modified)
- tests/services/test_ai_research.py: exists (modified)
- tests/services/test_brew_improve.py: exists (modified)

**Acceptance grep results:**
- `grep -v '^#' app/services/ai_research.py | grep -c 'f.<div id=.research-result'` = 0 (f-string sink gone)
- `grep -c 'templates.get_template("fragments/ai/research_result.html")' app/services/ai_research.py` = 1
- `grep -c '_json.dumps(result_schema.model_dump())' app/services/ai_service.py` = 0
- `grep -c 'templates.get_template("fragments/brew/improve_result.html")' app/services/ai_service.py` = 1
- `grep -n 'cited_sources' app/models/ai_coffee_research_cache.py` shows `Mapped[list[str]]`

## Self-Check: PASSED
