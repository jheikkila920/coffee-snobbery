---
type: bug
severity: high
created: 2026-05-29
source: john-uat-during-phase-20
area: ai-service / frontend
---

# AI "Refresh recommendation" freezes the whole app + no progress indicator

## Symptom (reported by John)
Clicking "Refresh recommendation" shows no feedback, then the entire app freezes
and becomes unresponsive (host appears hung; force-closing does nothing) for 1-2
minutes. Then it returns — sometimes with a new rec, sometimes not.

## Root cause (confirmed)
The coffee-rec path uses the SYNC Anthropic/OpenAI clients inside ASYNC handlers,
blocking the single uvicorn event loop for the full LLM call duration:
- `app/services/ai_service.py:337` `_build_anthropic_client` → `anthropic.Anthropic(...)` (sync)
- `app/services/ai_service.py:351` `_build_openai_client` → `openai.OpenAI(...)` (sync)
- `_generate_coffee_rec` (async, ~868) calls `anthropic_client.messages.create(...)`
  at lines 941 / 955 / 1089 — blocking, on the event loop thread.
- `regenerate` (~1338) awaits it; `POST /ai/refresh` (`app/routers/ai.py:231`) awaits `regenerate`.
With web_search the call takes 30s-2min → whole app frozen (single worker). This is
the §3.3 pitfall in STACK notes. `generate_brew_improvement` (~1935) already does it
correctly with `anthropic.AsyncAnthropic` + `await` — the coffee-rec path was never converted.

Same sync-in-async pattern affects: `_generate_sweet_spots_prose` (736/757),
`generate_equipment_rec` (1511/1546), `rank_pasted_coffees` (1813/1848),
and the generic `_call_*` helpers (626/664).

## Secondary issue
No `hx-indicator` spinner on the refresh control, and the strict nonce-CSP can
suppress htmx's auto-injected `.htmx-indicator` style (same gotcha as the Phase 9
"backups stuck Running" — define the indicator style in tailwind.src.css).

## Fix plan
1. Stop the freeze (critical): convert the coffee-rec / equipment / sweet-spots /
   rank-pasted paths to `AsyncAnthropic`/`AsyncOpenAI` + `await` (mirror
   `generate_brew_improvement`), OR minimal/low-risk: wrap each blocking `.create()`
   in `starlette.concurrency.run_in_threadpool`.
2. Real non-blocking UX: return immediately with a "generating…" state + spinner,
   run regen as a background task (nightly regen already runs in-process), poll/SSE
   for the result.
3. CSP-safe `hx-indicator` spinner on the refresh button.
4. Regression test: assert `POST /ai/refresh` returns promptly and does not block a
   concurrent request while a (mocked, slow) LLM call is in flight.

## Notes
- "Ask first" area (AI service, multiple call sites) — handle as its own /gsd-debug
  or a small phase, not an inline hot-fix.
- Does NOT block Phase 20 on-device testing.
