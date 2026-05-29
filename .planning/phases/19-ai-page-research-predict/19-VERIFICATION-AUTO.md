---
phase: 19-ai-page-research-predict
verified: 2026-05-29T15:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: initial-open-blockers
  gaps_closed:
    - "CR-01 stored XSS: _render_research_result now uses Jinja autoescape via fragments/ai/research_result.html"
    - "CR-02 broken improve-brew: generate_brew_improvement terminal emit now renders fragments/brew/improve_result.html"
    - "WR-02 cache-hit prediction commit: db.commit() added on both hit branches"
    - "WR-03 prediction regen bounded: TTL-only regen gate with explicit cost-control comment"
    - "WR-04 broad except narrowed: (json.JSONDecodeError, PydanticValidationError, openai/anthropic.APIError) at lines 1025, 1119, 1133"
    - "WR-05/IN-02 negative countdown: format_reset() with max(0,...) clamp in ai_quota.py; replaces all 6 sites"
    - "WR-06 cited_sources contract: model annotation and migration comment reconciled to list[str]"
  gaps_remaining: []
  regressions: []
# Deferred (operator-approved, not gaps):
# - WR-01 quota TOCTOU: accepted-risk comment present; no logic change (deliberate)
# - IN-04 hardcoded brew params: deferred to backlog (deliberate)
# - D-15 latency re-measurement + UAT items: Phase 22 / post-phase UAT (human ledger 19-VERIFICATION.md)
human_verification: []
---

# Phase 19: AI Page Research & Predict — Gap-Closure Verification Report

**Phase Goal:** The AI page is fully wired with consolidated recommendations, on-demand coffee research, predicted personal rating, and trend charts — with cost controls that are non-negotiable.

**Verified:** 2026-05-29T15:00:00Z
**Status:** PASSED
**Re-verification:** Yes — after gap closure (plans 19-08 and 19-09 landing)
**Pre-existing test failure excluded:** tests/phase_09/test_admin_system.py::TestSystemInfo::test_system_info (APP_VERSION build-arg not set in dev test image; passes in release builds; not a Phase 19 regression per orchestrator evidence)

---

## Goal Achievement

### Observable Truths — Gap-Closure Focus

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CR-01 closed: research SSE event:complete rendered via fragments/ai/research_result.html, not f-string | VERIFIED | `_render_research_result` calls `templates.get_template("fragments/ai/research_result.html").render(...)` (ai_research.py:718); no `f"<div id="research-result"` found |
| 2 | CR-01: adversarial coffee_name HTML-escaped (never raw in payload) | VERIFIED | `CoffeeResearchSchema.model_validate(cache_row.response_json)` passes result through Jinja autoescape ON; 5 regression tests in test_ai_research.py (lines 565-664) including adversarial `<script>` and `onerror=` payloads |
| 3 | CR-02 closed: improve-brew event:complete rendered via fragments/brew/improve_result.html, not raw JSON | VERIFIED | `templates.get_template("fragments/brew/improve_result.html").render(result=result_schema, session_id=session_id)` at ai_service.py:2164; `_json.dumps(result_schema.model_dump())` pattern absent |
| 4 | CR-02: adversarial summary_prose HTML-escaped in improve-brew payload | VERIFIED | 3 regression tests in test_brew_improve.py (lines 431-500) including template-render marker and adversarial prose escaping |
| 5 | No AI-derived prose rendered via f-string anywhere in ai_research.py or ai_service.py | VERIFIED | `grep f"<div id="research-result"` returns 0; no f-string HTML construction in either service for SSE complete events |
| 6 | WR-02: cache-hit prediction committed (not silently discarded by get_session rollback) | VERIFIED | Explicit `db.commit()` added after `get_or_refresh_prediction` on both hit branches (ai_research.py:459 first hit, :492 lock-recheck hit); WR-02 comment citing get_session rollback semantics present; test_cache_hit_prediction_committed_and_reused at line 666 |
| 7 | WR-03: prediction regeneration bounded — TTL-only, not unbounded per signature change | VERIFIED | `get_or_refresh_prediction` returns existing row when TTL valid even if signature changed (ai_research.py:246-249); explicit WR-03 cost-control comment at lines 236-249; tests at 738 and 788 |
| 8 | WR-04: OpenAI-fallback and retry except clauses no longer swallow programming errors | VERIFIED | ai_service.py:1025 catches `(json.JSONDecodeError, PydanticValidationError, openai.APIError)`; :1119 catches `(json.JSONDecodeError, PydanticValidationError, anthropic.APIError)`; :1133 same OpenAI set; WR-04 comments present; no bare `except Exception` at those sites |
| 9 | WR-05/IN-02: reset countdown cannot display negative time; single format_reset helper | VERIFIED | `def format_reset(reset_time)` in ai_quota.py:94-110 with `max(0, int(delta.total_seconds()))` clamp; 4 usages in ai.py (lines 108, 578, 642, 699), 1 in ai_research.py, 1 in ai_service.py; no inline `total_seconds() // 3600` math remaining in any of the 3 files |
| 10 | IN-02: `__import__("datetime")` hack removed | VERIFIED | `grep __import__ app/services/ai_service.py` returns 0 |
| 11 | WR-06: cited_sources contract consistent (schema = model = migration = list[str]) | VERIFIED | ai_coffee_research_cache.py:45 shows `Mapped[list[str]]`; migration comment at p19:65 states "list[str] URL strings per CoffeeResearchSchema.sources; WR-06"; no new migration file created |
| 12 | WR-01 TOCTOU accepted-risk documented (not silently ignored) | VERIFIED | Accepted-risk comment present at ai_research.py:412-421, mirrors D-05 style; explicitly states "Do NOT implement an advisory-lock-before-quota-read fix here" |

**Score:** 12/12 truths verified

### Deferred Items (not gaps — operator-approved)

| Item | Disposition | Evidence |
|------|-------------|----------|
| IN-04 hardcoded brew params (`suggest_recipe` ratio/temp/grind) | Deferred to backlog | 19-CONTEXT.md; pre-existing, not Phase-19-introduced |
| D-15 latency re-measurement | Deferred to Phase 22 / post-phase UAT | 19-VERIFICATION.md human ledger |
| WR-01 quota TOCTOU code change | Accepted risk; doc-only | Comment at ai_research.py:412-421 |

---

## Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `app/services/ai_research.py` | VERIFIED | `_render_research_result` uses Jinja template; `db.commit()` on both hit branches; WR-03 TTL gate; WR-01 TOCTOU note; `format_reset` usage |
| `app/services/ai_service.py` | VERIFIED | Improve-brew emit via template; narrowed except clauses (3 sites); `format_reset` usage; no `__import__` hack |
| `app/services/ai_quota.py` | VERIFIED | `format_reset(reset_time)` helper with `max(0,...)` clamp (line 94) |
| `app/routers/ai.py` | VERIFIED | 4 countdown sites delegate to `ai_quota.format_reset()` |
| `app/templates/fragments/ai/research_result.html` | VERIFIED | `if request else ''` guard at line 45; no longer orphaned |
| `app/templates/fragments/brew/improve_result.html` | VERIFIED | Rendered by generate_brew_improvement; no longer orphaned |
| `app/models/ai_coffee_research_cache.py` | VERIFIED | `cited_sources: Mapped[list[str]]` at line 45 |
| `app/migrations/versions/p19_ai_research_predict.py` | VERIFIED | cited_sources comment says "list[str] URL strings" |
| `tests/services/test_ai_research.py` | VERIFIED | 5 CR-01 regression tests + 3 WR-02/WR-03 tests present |
| `tests/services/test_brew_improve.py` | VERIFIED | 3 CR-02 regression tests present (HTML render, not-raw-JSON, escaping) |
| `tests/services/test_ai_quota.py` | VERIFIED | 4 `format_reset` unit tests (None, future, past clamp, zero) |

---

## Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `app/services/ai_research.py` | `fragments/ai/research_result.html` | `templates.get_template(...).render(...)` (line 718) | WIRED |
| `app/services/ai_service.py` | `fragments/brew/improve_result.html` | `templates.get_template(...).render(...)` (line 2164) | WIRED |
| `app/routers/ai.py` | `app/services/ai_quota.format_reset` | `ai_quota.format_reset(reset_time)` (4 sites) | WIRED |
| `app/services/ai_research.py` | `app/services/ai_quota.format_reset` | `ai_quota.format_reset(reset_time)` (line 426) | WIRED |
| `app/services/ai_service.py` | `app/services/ai_quota.format_reset` | `ai_quota.format_reset(reset_time)` (line 1986) | WIRED |

---

## Requirements Coverage

| Requirement | Plans | Status | Evidence |
|-------------|-------|--------|----------|
| AIX-01 | 19-01, 19-03 | SATISFIED | Coffee research SSE endpoint; web-search grounded; delivered in 19-01..07; not regressed |
| AIX-02 | 19-03, 19-08 | SATISFIED | Predicted rating range with confidence via `get_or_refresh_prediction`; CR-01 fix routes result through template |
| AIX-03 | 19-01 | SATISFIED | Cold-start gate at ai_research.py:395-408 (3 sessions + 5 notes) |
| AIX-04 | 19-03, 19-09 | SATISFIED | Cache hit path; WR-02 commit ensures cache-hit prediction persists and TTL is honored |
| AIX-05 | 19-05, 19-09 | SATISFIED | Rolling-24h quota; `format_reset` provides accurate countdown; WR-03 bounds prediction regen cost |
| AIX-06 | 19-04 | SATISFIED | Wishlist-add form in research_result.html (now wired, no longer orphaned) |
| AIX-07 | 19-02, 19-08 | SATISFIED | SSE streaming; event:complete renders HTML fragments (not f-string or raw JSON) |
| AIX-09 | 19-06 | SATISFIED | Preference-profile prose via nightly scheduler; not touched by gap plans |
| AIX-10 | 19-06 | SATISFIED | Progress feedback buttons; not touched by gap plans |
| AIX-11 | 19-01 | SATISFIED | Concrete brew recipe in recommendation; not touched by gap plans |
| AIX-12 | 19-07, 19-08 | SATISFIED | Improve-brew coaching card now renders HTML instead of raw JSON blob (CR-02) |
| AIX-13 | 19-07 | SATISFIED | Latency investigation documented in 19-VERIFICATION.md (human ledger); D-15 deferred to Phase 22 |
| VIZ-01 | 19-06 | SATISFIED | Chart.js trend charts on AI page; not touched by gap plans |

---

## Anti-Patterns Scan (Gap-Plan Files Only)

| File | Pattern | Finding |
|------|---------|---------|
| `app/services/ai_research.py` | f-string HTML construction for SSE | NOT FOUND — `_render_research_result` uses Jinja template |
| `app/services/ai_service.py` | `_json.dumps(result_schema.model_dump())` on complete event | NOT FOUND |
| `app/services/ai_service.py` | `__import__("datetime")` hack | NOT FOUND |
| `app/services/ai_service.py` | `except (..., Exception)` catch-all at former WR-04 sites | NOT FOUND — narrowed to provider/parse errors |
| `app/services/ai_quota.py` | Inline H/M math without clamp | NOT FOUND — only `format_reset` does the math |
| `app/models/ai_coffee_research_cache.py` | `Mapped[list[dict[str, Any]]]` for cited_sources | NOT FOUND — correctly `Mapped[list[str]]` |

No TBD/FIXME/XXX debt markers found in files modified by plans 19-08 and 19-09.

---

## Behavioral Spot-Checks

Runnable checks not applicable without a live container (stack not started). The orchestrator-provided evidence covers this:

- **1331 pass, 3 documented skips, 10 xfailed, 1 pre-existing failure** on the baked `coffee-snobbery-test` image.
- The 1 failure (test_system_info APP_VERSION assertion) is pre-existing/environmental, not a Phase 19 regression.
- CR-01 and CR-02 regression tests confirmed to exist in the test files (lines verified above).

---

## Human Verification Required

None. All gap-closure items are verifiable from code.

Items previously deferred to human UAT remain in the human ledger (`19-VERIFICATION.md`) and are not re-raised here.

---

## Gaps Summary

No gaps found. Both reopen blockers (CR-01 stored XSS, CR-02 broken improve-brew) are confirmed closed in code. All six in-scope warnings (WR-01 through WR-06) are addressed — five via code fixes with tests, one (WR-01) via accepted-risk documentation as planned.

The 13 requirement IDs (AIX-01..07, AIX-09..13, VIZ-01) remain covered across plans 19-01..19-09 with no regressions introduced.

---

_Verified: 2026-05-29T15:00:00Z_
_Verifier: Claude (gsd-verifier) — gap-closure re-verification_
_Human ledger: .planning/phases/19-ai-page-research-predict/19-VERIFICATION.md (preserved, not overwritten)_
