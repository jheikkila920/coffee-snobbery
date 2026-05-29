---
phase: 19-ai-page-research-predict
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - app/services/ai_research.py
  - app/services/ai_service.py
  - app/services/ai_quota.py
  - app/services/ai_schemas.py
  - app/models/ai_coffee_research_cache.py
  - app/migrations/versions/p19_ai_research_predict.py
  - app/routers/ai.py
  - app/templates/fragments/ai/research_result.html
  - app/templates/fragments/brew/improve_result.html
  - app/templates_setup.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 19: Code Review Report (Gap-Closure Re-Review)

**Reviewed:** 2026-05-29
**Depth:** standard
**Status:** clean

## Summary

This is a re-review of the Phase 19 gap-closure diff (`git diff aae091f..HEAD`),
which landed across plans 19-08 and 19-09 to fix the 2 BLOCKERs and 6 WARNINGs
from the prior review (preserved in commit f8baa48). Scope was limited to the
gap-closure changes; the broader Phase 19 surface (SSRF verifier, advisory locks,
IDOR scoping, CSP posture, charts SQL) was validated sound in the original review
and is unchanged here.

Every in-scope blocker and warning is resolved in the code, the fixes carry
explicit cost-control/accepted-risk commentary that matches the CLAUDE.md
invariants, and regression tests assert the security properties directly
(adversarial XSS payloads come back HTML-escaped; raw-JSON emit is gone). No new
BLOCKER or WARNING was introduced. The highest-priority new-risk check — a new
XSS sink in the now-live render path — came back clean: both result fragments
route exclusively through the autoescape-ON Jinja env with no `|safe`, `Markup`,
or autoescape-off.

Status is `clean`.

## Verification of Prior Findings

**CR-01 (BLOCKER) — Stored XSS via unescaped f-string: RESOLVED.**
`_render_research_result` (`app/services/ai_research.py:689-724`) no longer builds
HTML by f-string. It validates `cache_row.response_json` into a
`CoffeeResearchSchema` and renders `fragments/ai/research_result.html` through
`app.templates_setup.templates`, whose env has `autoescape = select_autoescape([...])`
(`templates_setup.py:47`). The template (`research_result.html`) emits every
AI-derived value via `{{ }}` (coffee_name :46, roaster_name :47, buy_url :48,
prediction.reasoning :35) with no `|safe` anywhere, and its header comment
explicitly forbids the safe filter. The f-string `<div id="research-result">`
sink is gone from both the cache-hit (`:457`, `:493`) and miss (`:658`) paths.
Regression tests assert `&lt;script&gt;` and `&lt;img...&gt;` escaped forms and
that the raw tags are absent (`test_render_research_result_escapes_adversarial_coffee_name`,
`_escapes_onerror_payload`).

**CR-02 (BLOCKER) — improve-brew emitted raw JSON: RESOLVED.**
`generate_brew_improvement` (`app/services/ai_service.py:2158-2168`) now renders
`fragments/brew/improve_result.html` via the autoescape env and emits the HTML as
the `complete` payload; the `_json.dumps(result_schema.model_dump())` emit is
removed. The template autoescapes summary_prose, rationale, parameter, and
suggested_value with no safe filter. Tests assert `id="improve-brew-result"` is
present, that the payload is not parseable JSON, and that an injected
`<script>` prose comes back escaped.

**WR-02 — cache-hit prediction never committed: RESOLVED.**
Explicit `db.commit()` added on both cache-hit branches
(`ai_research.py:457`, `:493`) and the miss path (`:655`), with a comment
documenting that `get_session` rolls back on teardown. Covered by
`test_cache_hit_prediction_committed_and_reused`.

**WR-03 — unbounded signature-driven prediction regen: RESOLVED (deliberate TTL bound).**
`get_or_refresh_prediction` (`ai_research.py:246-249`) now returns the existing
prediction whenever it is TTL-valid, even if the input signature changed; an LLM
call fires only when no row exists or the 7-day TTL has expired. The decision is
documented inline as a deliberate cost trade-off and matches the CLAUDE.md
cost-control invariant ("don't break signature-based regeneration — it's the cost
control"). Covered by `test_signature_change_does_not_trigger_regen_within_ttl`
and `test_prediction_regen_fires_on_ttl_expiry`. Note: this is a deliberate
product-behavior change — predictions now refresh on the 7-day TTL rather than
immediately on signature change. It is correctly commented and is the intended
cost control, not a defect.

**WR-04 — broad provider-tier excepts: RESOLVED.**
The three catch sites (`ai_service.py:1025`, `:1119`, `:1133`) narrowed from
catch-all `Exception` to `(json.JSONDecodeError, PydanticValidationError,
openai.APIError)` / `anthropic.APIError`. Both `openai` (`:35`) and `anthropic`
(`:33`) are imported at module level, so the narrowed handlers cannot raise
`NameError`. Programming errors now propagate to the `regenerate()` error-row
handler. The top-level OpenAI branch at `ai_research.py:610` retains a broad
`except Exception` that degrades to a user-facing error event and returns — that
is a different, terminal handler (not a silent tier-skip) and was not in WR-04's
scope; it is acceptable as a last-resort guard.

**WR-05 / IN-02 — duplicated countdown math + negative-clamp + `__import__` hack: RESOLVED.**
Single `format_reset(reset_time)` helper added in `ai_quota.py:94-110`, clamping
`total_secs = max(0, ...)` before the H/M split so a negative countdown is
impossible. All four router sites (`ai.py:108`, `:578`, `:642`, `:699`) and both
service sites (`ai_research.py:425`, `ai_service.py:1985`) now call it. The
`__import__("datetime")` inline hack is gone.

**WR-06 — cited_sources contract mismatch: RESOLVED.**
Reconciled to `list[str]` across all three sources of truth: schema
(`ai_schemas.py:244`, already `list[str]`), model annotation
(`ai_coffee_research_cache.py:45`, changed `list[dict[str, Any]]` → `list[str]`),
and migration comment (`p19_ai_research_predict.py:65`). Annotation-only change;
JSONB column type unchanged, so no migration is required.

## New-Risk Checks (all clear)

- **New XSS sink:** None. `research_result.html` and `improve_result.html`
  contain no `|safe`, `Markup`, or `{% autoescape false %}`; the render env is
  globally autoescape-ON. This is the highest-priority check and it is clean.
- **Cache-row validation safety:** `_render_research_result` calls
  `CoffeeResearchSchema.model_validate(cache_row.response_json)`. `response_json`
  is always written from `result_schema.model_dump()` of the same schema, so the
  round-trip is exact even under `extra="forbid"`. Phase 19 is new — there are no
  legacy rows with a divergent shape. Safe for all real cache rows.
- **WR-04 regression risk:** No graceful-degradation path was broken. The
  narrowed tiers still fall through to the next provider on genuine provider/parse
  errors; only true programming errors now propagate (the intended behavior).
- **Empty CSRF hidden field in SSE-rendered fragment:** `research_result.html:45`
  renders an empty `X-CSRF-Token` hidden value because the render passes
  `request=None`. This does not break the wishlist POST — CSRF is enforced by the
  double-submit cookie+header pattern, and HTMX injects the token header from the
  `<meta name="csrf-token">` via `htmx-listeners.js` at request time
  (`base.html:10`, `:79`). The hidden field is cosmetic. Not a defect.

## Accepted / Deferred (not findings)

- **WR-01 (TOCTOU quota window):** Implemented as a documented accepted-risk, not
  a code change — the explicit comment at `ai_research.py:411-422` records the
  bounded blast radius at household scale with a 20/day cap and instructs against
  the lock-before-read fix. This matches the requested resolution and is an
  accepted risk, not an open finding.
- **IN-04 (hardcoded brew params in `suggest_recipe`):** Pre-existing, out of
  gap-closure scope, deliberately not addressed. Not a Phase-19-introduced defect.

## Test Note (not a finding)

The three changed test files fail on the review host with
`ModuleNotFoundError: No module named 'anthropic'` (and `openai`) at import time —
an environment gap, not a logic failure. Per CLAUDE.md the suite runs inside the
`coffee-snobbery` container (or via `docker compose cp`), where the SDKs are
baked; the phase-close gate already recorded 1316 pass (commit c025a4c). The
escaping guarantees are structurally enforced by the autoescape-ON Jinja env and
the no-`|safe` templates regardless of where the tests run.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
