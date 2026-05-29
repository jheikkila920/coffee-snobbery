---
phase: 19-ai-page-research-predict
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - app/services/ai_research.py
  - app/services/ai_service.py
  - app/services/ai_quota.py
  - app/services/ai_schemas.py
  - app/services/analytics.py
  - app/services/charts.py
  - app/services/scheduler.py
  - app/routers/ai.py
  - app/routers/home.py
  - app/models/ai_coffee_research_cache.py
  - app/models/ai_rating_prediction.py
  - app/models/__init__.py
  - app/migrations/versions/p19_ai_research_predict.py
  - app/templates/fragments/ai/research_result.html
  - app/templates/fragments/ai/research_form.html
  - app/templates/fragments/ai/preference_profile_prose.html
  - app/templates/fragments/ai/trends_card.html
  - app/templates/fragments/brew/improve_result.html
  - app/templates/fragments/ai/coach_brew_picker.html
  - app/static/js/alpine-components/chart-trends.js
  - app/templates/base.html
  - app/templates/pages/ai.html
findings:
  critical: 2
  warning: 6
  info: 4
  total: 12
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 19 adds the consolidated `/ai` page: SSE coffee research, per-user rating
predictions, improve-brew coaching, preference-profile prose, and two Chart.js
trends. The security primitives that the phase reuses from `ai_service.py`
(SSRF verifier, citation projector, advisory locks, encrypted-credential
handling) are sound, the raw SQL in `charts.py` is correctly parameterized, and
IDOR scoping on the new routes is correct (404-on-cross-user, `user_id` from
`request.state.user.id` only). CSP posture for the Chart.js Alpine component is
clean (nonce-tagged scripts, no eval, `Alpine.data()` registration, no inline
handlers).

However, the review found two BLOCKERs centered on the same root cause: the
Jinja result templates added in plan 19-04/19-06 (`research_result.html`,
`brew/improve_result.html`) are **orphaned** — the SSE generators never render
them. The research generator instead emits a hand-built f-string of HTML that
interpolates LLM/web-search-derived text **without escaping**, which is a stored
XSS sink (it directly violates the project's "never bypass autoescape for AI
prose" invariant). The improve-brew generator emits raw JSON that gets swapped
into the DOM, so that feature renders a JSON blob instead of the coaching card.

Both the XSS and the broken-render bugs are masked by the fact that the
templates exist and look correct on inspection — the defect is purely in the
wiring. Several quota/transaction correctness issues are also flagged below.

## Critical Issues

### CR-01: Stored XSS — research SSE result built via unescaped f-string, bypassing autoescape

**File:** `app/services/ai_research.py:654-675` (sink); emitted at `:433`, `:459`, `:628`
**Issue:**
`generate_coffee_research` renders its `event:complete` payload with
`_render_research_result`, which builds raw HTML by f-string interpolation:

```python
return f'<div id="research-result"><h3>{coffee_name}{cached_badge}</h3>{pred_text}</div>'
```

`coffee_name` comes from `cache_row.response_json` — i.e. `CoffeeResearchSchema.coffee_name`,
which is **LLM output grounded in adversarial web-search content**. The route
(`app/routers/ai.py:623`) returns this via `EventSourceResponse`, and the client
form (`research_form.html:46`, `sse-swap="complete"` → `hx-swap="innerHTML"`)
swaps the payload into the live DOM as HTML. Nothing escapes `coffee_name`, so a
web page the model reads during research (or a crafted coffee/roaster name) can
inject `<img src=x onerror=...>` / `<script>`-equivalent markup that executes in
the victim's authenticated session. `prediction.confidence` / `predicted_low/high`
are also interpolated unescaped (lower risk — numeric/Literal, but still wrong).

This directly violates CLAUDE.md: "autoescaping on every Jinja template... If/when
AI prose output is rendered, render it as plain text... do not allow HTML through."
The correctly-autoescaped `research_result.html` template was written for exactly
this purpose but is **never used** — its context variables (`result`, `is_cached`,
`buy_url_unverified`) don't even match what the generator passes (`cache_row`,
`prediction`, `cached`), confirming it was never wired.

**Fix:** Render the result through the Jinja template (autoescape ON) instead of
an f-string. Mirror the `improve-brew` JSON approach or render server-side via the
templating env. Minimal server-side render:

```python
from app.templates_setup import templates

def _render_research_result(*, cache_row, prediction, cached, buy_url_unverified=False) -> str:
    raw = cache_row.response_json
    result = CoffeeResearchSchema.model_validate(raw)  # or a lightweight namespace
    return templates.get_template("fragments/ai/research_result.html").render(
        result=result,
        prediction=prediction,
        is_cached=cached,
        buy_url_unverified=buy_url_unverified,
        request=None,  # template references request.cookies for CSRF — see note below
    )
```

Note: `research_result.html:45` reads `request.cookies.get('csrftoken')` for the
wishlist-add CSRF field, so the render needs a real `request`. Either thread the
`Request` into the generator, or have the client read the CSRF token from the
page-level `<meta>`/cookie at submit time. Whichever path you take, the
non-negotiable part is: **the AI-derived strings must pass through autoescape**,
never an f-string `<div>...</div>`.

### CR-02: improve-brew SSE emits raw JSON, never renders the coaching card (broken feature + contract violation)

**File:** `app/services/ai_service.py:2156-2162`; consumed at `app/templates/pages/brew_form.html:339-364`
**Issue:**
`generate_brew_improvement` emits its terminal event as:

```python
yield ServerSentEvent(data=_json.dumps(result_schema.model_dump()), event="complete")
```

But the brew edit page wires `sse-swap="complete"` on `#improve-brew-section`
with `hx-swap="innerHTML"` (`brew_form.html:342,348`), and the mount comment
states it "receives improve_result.html fragment on event:complete"
(`brew_form.html:363`). HTMX swaps the `event:complete` `data` verbatim into the
DOM. Since the generator sends a JSON string (not HTML), the user sees a raw
`{"summary_prose": ..., "next_try": [...]}` blob dumped into the page. The
purpose-built `fragments/brew/improve_result.html` (autoescaped, correctly
structured) is **orphaned** — no code path renders it.

This is a functional BLOCKER: the headline "Coach a brew" feature does not
render. (It is not itself an XSS sink — `innerHTML` of a JSON string is inert
text — but the feature is broken and the contract documented in the template/page
is unmet.)

**Fix:** Render `improve_result.html` server-side in the generator and emit the
HTML as the `complete` payload, the same correction pattern as CR-01:

```python
html = templates.get_template("fragments/brew/improve_result.html").render(
    result=result_schema, session_id=session_id
)
yield ServerSentEvent(data=html, event="complete")
```

Apply the same autoescape discipline (the template already does the right thing;
just route through it). After fixing both CR-01 and CR-02, add a test asserting
the `event:complete` payload contains the rendered HTML markers (e.g.
`id="improve-brew-result"`, `id="research-result"`) and that an injected
`<script>`/`onerror` coffee name comes back escaped.

## Warnings

### WR-01: Quota check is a TOCTOU window — rolling-24h cap is exceedable under concurrent SSE requests

**File:** `app/services/ai_research.py:394-404` (research); `app/services/ai_service.py:1972-1985` (improve-brew); `app/routers/ai.py:582-607`
**Issue:** Quota is checked (`ai_quota.remaining(...) <= 0`) before the LLM call,
and the consuming row is only written *after* the call completes
(`_write_research_telemetry` / `_write_recommendation_row`). Between the check and
the write there is a multi-second LLM call. The per-(user,rec_type) `asyncio.Lock`
+ advisory lock serialize *concurrent* runs, but they are acquired only on the
cache-miss path and released per request — a user firing N requests in sequence,
each passing the `remaining > 0` check before any prior row commits, is not fully
guarded. At household scale and with a 20/day cap the blast radius is small, but
the invariant "rolling-24h quota must not be bypassable" is not strictly held.
The route-level check (`ai.py:582`) and the generator-level check
(`ai_research.py:394`) are also redundant double-reads that can disagree.

**Fix:** Acquire the advisory lock *before* the quota read on the miss path, or
record a pending/in-flight marker row inside the lock before the await so the
count reflects in-flight calls. At minimum, document the accepted-risk explicitly
(like the D-05 TOCTOU note on `_assert_public_host`) rather than leaving the
invariant silently weakened.

### WR-02: `get_or_refresh_prediction` writes prediction rows but the caller never commits on the cache-hit path

**File:** `app/services/ai_research.py:420-434` (cache-hit branch)
**Issue:** On a cache hit, `generate_coffee_research` calls
`get_or_refresh_prediction`, which may regenerate and `db.execute(...) + db.flush()`
a new prediction row (`:335-336`), then the generator `yield`s `event:complete`
and `return`s — **without `db.commit()`**. The miss path commits at `:620`, but
the cache-hit path has no commit. Whether the flushed INSERT/UPDATE persists then
depends entirely on `get_session`'s teardown semantics (commit-on-success vs
rollback). If the dependency rolls back (common pattern), every cache-hit
prediction refresh is silently discarded and re-computed (extra LLM cost) on the
next hit, defeating the 7-day prediction TTL.

**Fix:** Add an explicit `db.commit()` after `get_or_refresh_prediction` on both
cache-hit branches (`:427` and `:457`), or confirm and document that
`get_session` commits on generator completion. Add a test that a second cache-hit
request returns the same prediction row id (no regeneration).

### WR-03: Prediction regeneration burns LLM calls without decrementing or checking quota

**File:** `app/services/ai_research.py:200-342`, called at `:420` and `:611`
**Issue:** `get_or_refresh_prediction` makes a real LLM call
(`client.messages.create` / `oai_client.responses.create`) whenever the
prediction is stale or expired — including on the **cache-hit path**, which the
docstring and `ai_quota.py` header explicitly promise costs no API credits
("Cache hits do NOT decrement quota — only successful LLM calls count"). A user
repeatedly researching cached coffees while logging new sessions (changing
`current_signature`) triggers an unbounded series of prediction LLM calls that
never write an `ai_recommendations` row and so never count against any quota
bucket. This is a cost-control gap against the AI cost invariants.

**Fix:** Either (a) write a telemetry row for the prediction call so it counts
against quota, or (b) gate prediction regeneration behind the same quota check,
or (c) document that prediction calls are intentionally un-metered and bound them
(e.g. the 7-day TTL already limits expiry-driven regen, but signature-driven
regen is unbounded). Decide deliberately — right now it's an implicit bypass.

### WR-04: `_archived_retry_attempted` / `last_error` broad-except swallows real provider failures

**File:** `app/services/ai_service.py:1024`
**Issue:** The OpenAI fallback tier catches `(json.JSONDecodeError, PydanticValidationError, Exception)`.
Listing `Exception` alongside the specific types makes the specific entries dead
and turns this into a bare catch-all that advances to the next tier on *any*
error, including programming errors (AttributeError, TypeError) that should
surface. This can mask bugs and produce a misleading "try_again" instead of a
real error. Same anti-pattern lower in the file at the retry blocks
(`:1114`, `:1126` catch bare `Exception` and silently set `retry_raw = None`).

**Fix:** Catch only the intended provider/parse errors
(`(json.JSONDecodeError, PydanticValidationError, openai.APIError)`); let
unexpected exceptions propagate to the `regenerate()` top-level handler that
already writes an error row.

### WR-05: Reset-time minute math can display a misleading countdown when quota window has aged

**File:** `app/routers/ai.py:586-595`, `:656-663`, `:715-723`; `app/services/ai_research.py:399-402`
**Issue:** `delta = reset_time - datetime.now(UTC)` is computed then split with
`int(delta.total_seconds() // 3600)`. If the oldest in-window row is already
older than 24h at display time (it can be, since `get_quota_reset_time` filters
`generated_at >= since` but the row's `+24h` can still be in the past by the time
this renders), `delta` is negative and the integer floor division yields negative
hours/minutes (e.g. "-1h 59m"). The route at `ai.py:111-115` correctly clamps
with `max(0, ...)`, but the three other call sites and the generator do not.

**Fix:** Clamp before splitting in every site:
`total_secs = max(0, int(delta.total_seconds()))` then derive hours/mins from
`total_secs`. Extract a shared `format_reset_countdown(reset_time)` helper to kill
the five duplicated copies of this math (DRY; also fixes WR-08-adjacent dupes).

### WR-06: `cited_sources` write/read shape mismatch — list[str] written, list[dict] modeled

**File:** `app/services/ai_research.py:591` (`cited_sources = result_schema.sources or []`, a `list[str]`) vs `app/models/ai_coffee_research_cache.py:43` and migration `:65` (documented/typed as `list[dict[str,Any]]`, e.g. `[{"url":...,"title":...}]`)
**Issue:** `CoffeeResearchSchema.sources` is `list[str]` (`ai_schemas.py:244`), and
that's what gets stored in `cited_sources`. But the model annotation is
`Mapped[list[dict[str, Any]]]` and the migration comment documents a list of
`{"url","title"}` dicts. JSONB tolerates either shape at the DB layer, so this
won't error — but any future reader that assumes `source["url"]` will break on a
plain string. The schema, model, and migration disagree about the contract.

**Fix:** Pick one shape. Given the schema produces `list[str]`, update the model
annotation/docstring and the migration comment to `list[str]`, or change the
write to project `[{"url": s} for s in sources]`. Don't leave three sources of
truth in conflict.

## Info

### IN-01: Orphaned/misleading templates left in the tree

**File:** `app/templates/fragments/ai/research_result.html` (context vars don't match any caller); `app/templates/fragments/brew/improve_result.html` (no renderer)
**Issue:** Both result templates are unreachable as written (see CR-01/CR-02).
Once the generators are fixed to render them, verify the context variable names
align (`research_result.html` expects `result`/`is_cached`/`buy_url_unverified`;
the generator currently passes `cache_row`/`prediction`/`cached`). Until wired,
they are dead code that misleads reviewers into thinking the safe path is active.

**Fix:** Wire them per CR-01/CR-02 and reconcile context names, or remove if a
different render path is chosen.

### IN-02: Duplicated reset-countdown + quota-format blocks across router and services

**File:** `app/routers/ai.py:107-115`, `:586-595`, `:656-663`, `:715-723`; `app/services/ai_research.py:399-402`; `app/services/ai_service.py:1977-1983`
**Issue:** The "delta → Hh Mm" formatting and the `__import__("datetime")`
inline-import hack (`ai_service.py:1978-1979`) are copy-pasted in ~6 places, with
inconsistent clamping (see WR-05). The `__import__` form is also a code smell vs a
normal module-level `from datetime import datetime, timezone`.

**Fix:** One helper in `ai_quota.py`, e.g.
`def format_reset(reset_time: datetime | None) -> str | None`. Replace all sites.

### IN-03: `_render_research_result` docstring claims it is a temporary stub "added in 19-04"

**File:** `app/services/ai_research.py:649-665`
**Issue:** The docstring says "Returns a minimal HTML string when the templates
are not yet wired (Phase 19-04 adds the full template). This stub is sufficient
for the service-layer tests." This stub is the live render path in Phase 19 — it
was never replaced. The stale "stub" framing likely caused the XSS in CR-01 to be
overlooked (it reads as throwaway test scaffolding, but it ships).

**Fix:** Remove the stub once CR-01 is addressed; if any test depends on the
f-string shape, update the test to assert against the real template output.

### IN-04: `suggest_recipe` / `alt_brewer_callout` return hardcoded magic brew parameters

**File:** `app/services/ai_service.py:470-488` (`ratio="1:15"`, `temp_c=94`, `grind_hint="medium-fine"`)
**Issue:** The no-match and matched branches both return hardcoded `1:15` / `94C`
/ `medium-fine` defaults regardless of the user's actual best recipe. The matched
branch even computes `avg_rating` from the user's real top recipe but then
discards the recipe's real ratio/temp/grind in favor of the constants. Minor
(pre-existing, not Phase-19-introduced), but worth a constant + comment or pulling
the real recipe fields.

**Fix:** Source the parameters from the matched `Recipe` row, or hoist the
defaults to named module constants with a comment explaining they're placeholders.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
