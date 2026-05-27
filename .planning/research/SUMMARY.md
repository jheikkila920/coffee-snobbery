# Project Research Summary

**Project:** Snobbery v1.2 — Polish & Mobile-First
**Domain:** Self-hosted household coffee log (FastAPI + PostgreSQL + HTMX, PWA, AI-driven recommendations)
**Researched:** 2026-05-25
**Confidence:** HIGH

---

## Executive Summary

Snobbery v1.2 is a polish and capability milestone on top of a fully shipped v1.1 product. The stack is locked and does not change — no new required Python dependencies exist for any confirmed v1.2 feature. Research confirms the existing FastAPI + SQLAlchemy + Jinja/HTMX + Alpine + Tailwind v3 architecture accommodates all planned features through schema additions, new routes, and template changes only. The highest-impact engineering work is in three areas: (1) getting the self-hosted image publishable to GHCR with multi-arch support and a clean operator first-run experience, (2) restructuring the IA (Admin off nav, AI as a bottom-nav destination), and (3) adding two new capabilities — cafe quick-rate and on-demand AI coffee research with predicted rating — both of which integrate into existing infrastructure without new services.

The single highest-risk decision across all research is the cafe quick-rate data model. Three researchers independently proposed conflicting approaches: FEATURES.md recommends a boolean `is_cafe_log` field on `brew_sessions` (unified table); ARCHITECTURE.md recommends a separate `cafe_logs` table (clean isolation); PITFALLS.md recommends a `session_type` discriminator ENUM on `brew_sessions`. The architecture researcher read the actual `brew_sessions` model and `analytics.py` code and found a concrete blocking constraint: `brew_sessions.coffee_id` is `NOT NULL RESTRICT`, which makes the unified-table approach architecturally unsound without breaking an invariant. The separate-table approach is best-grounded and is the recommendation, but the final call belongs to plan-phase.

The second highest-risk area is the on-demand AI research feature's cost model. Unlike the nightly signature-gated regen, on-demand research removes the cadence gate entirely. Without a DB cache table for research results and a per-user daily rate limit, costs scale with user curiosity rather than brew activity. Both the cache table and the rate limit are blocking requirements for this feature — they cannot be deferred to a follow-up phase.

---

## Key Findings

### Recommended Stack

The v1.1 stack is confirmed unchanged. Zero new required Python dependencies exist for v1.2. The release CI workflow is the only structural addition: a new `.github/workflows/release.yml` publishing to GHCR via `docker/build-push-action@v6` with QEMU for multi-arch (amd64 + arm64).

Two conditional dependencies depending on scope decisions: `segno>=1.6,<2` (QR code generation, if QR sharing is in scope — current research recommends skipping) and Chart.js 4.4.9 via CDN (if data visualization charts are in scope — current research recommends skipping).

**Core technologies (unchanged):**
- Python 3.12 + FastAPI 0.136 + Starlette 1.0: locked web framework
- SQLAlchemy 2.0 + Alembic 1.18 + PostgreSQL 16: locked; all v1.2 schema changes are purely additive migrations
- HTMX 2.0.10 + Alpine.js 3.16 + Tailwind v3 standalone CLI: locked frontend; no npm build pipeline
- anthropic SDK 0.102 + openai SDK 2.37: AI research feature reuses these without change
- APScheduler 3.x in-process: unchanged; on-demand AI research does NOT go through the scheduler

**CI-only additions (not in requirements.txt):**
`docker/setup-qemu-action@v3`, `docker/setup-buildx-action@v4`, `docker/login-action@v3`, `docker/metadata-action@v5`, `docker/build-push-action@v6`

### Expected Features

**Must have (table stakes):**
- Background timer surviving phone sleep in Guided Brew Mode — Web Worker vs `setInterval` must be verified; if using `setInterval`, this is a real gap
- Cafe quick-rate form — 20-second log for coffees tasted outside the home; minimum fields are coffee name and rating
- Water profiles as named lookup table — replace freetext `water_type`; one table, one FK

**Should have (differentiators):**
- AI research-a-coffee + predict rating — on-demand web search + preference matching; no other self-hosted household coffee log does this
- Phase-based step timer in Guided Brew Mode — transforms it from a stopwatch to a brewing coach
- First drip + bloom time optional fields — two nullable columns on `brew_sessions`
- Self-host packaging: prebuilt GHCR image, simpler first-run
- IA restructure: Admin off bottom nav, AI as fourth tab
- Mobile-first full rework of every screen to 375px polish bar

**Defer to v2+:**
- BLE scale integration, QR/NFC sharing, SCA cupping, charts/data viz library, SSE streaming for AI, per-user/month AI cost ceiling

**Confirmed anti-features:**
- Point-estimate AI rating ("you'll rate this 4.2") — use range + confidence level instead
- Social sharing of brew cards — counter to private household identity
- Bag inventory management / low-stock alerts — deferred to v2

### Architecture Approach

The v1.1 architecture is clean and the v1.2 features slot in without structural surgery. New capabilities require: one new model/migration (`cafe_logs`), one new function in `ai_service.py` (`research_coffee_predict_rating`), one new Pydantic schema (`CoffeePredictSchema`), new routes on the existing `ai.py` router, and template changes for the IA restructure.

**Confirmed unchanged by code read:** `analytics.py`, `scheduler.py`, `encryption.py`, `credentials.py`, `brew_session.py`, `ai_recommendation.py`, `entrypoint.sh`, `sw.js`, `manifest.json`, all existing AI route handlers.

**Major new/modified components:**
1. `app/routers/ai.py` — add `GET /ai` shell, `GET /ai/cards/recommendation` (five-branch state machine relocated from home), `GET /ai/research`, `POST /ai/research`
2. `app/services/ai_service.py` — add `research_coffee_predict_rating()` following the `generate_equipment_rec()` on-demand pattern
3. `app/models/cafe_log.py` + migration — new `cafe_logs` table; purely additive
4. `app/templates/base.html` — bottom nav: Admin tab → AI tab
5. `app/templates/pages/config_hub.html` — add Admin card (conditional on `user.is_admin`)
6. `docker-compose.yml` + `.github/workflows/release.yml` — operator compose + CI release workflow

### Critical Pitfalls

1. **On-demand research removes the cadence gate — surprise bill risk (v1.2-AI-1)** — A DB cache table for research results (7-day TTL) and a slowapi per-user daily limit (10 calls/user/day) are blocking requirements, not optional polish. Both must be in the initial phase plan.

2. **Cafe sessions polluting brew analytics and AI signature (v1.2-CAFE-1)** — Whatever data model is chosen, every analytics query and the AI input signature computation must explicitly exclude cafe-mode rows from brew-parameter analytics. Adding the discriminator/isolation must happen in the same migration as the feature — retroactive data migration is expensive.

3. **G-01 root-volume bug still open (v1.2-IMAGE-3)** — The Dockerfile `RUN chown` only covers fresh volumes. The permanent fix is a runtime `chown -R app:app /app/data` in `entrypoint.sh` before dropping to the app user via `exec gosu app uvicorn ...`. Blocking requirement for the self-host packaging phase.

4. **Unverified iOS safe-area fix spread by mobile rework (v1.2-MOBILE-1)** — Commit `982c0e6` introduced a safe-area fix never verified on a physical device. Verifying on a physical iPhone in PWA standalone mode is a mandatory prerequisite before the mobile rework begins.

5. **Web-search input-token cost (AI-1, COST-5)** — `max_uses` must be capped on the web-search tool (5 for primary, 3 for broadened). Applies to both nightly regen and the new on-demand research feature.

---

## Open Decisions (Flagged for Plan-Phase)

### Decision 1: Cafe Quick-Rate Data Model — ARCHITECTURE Recommendation (Separate Table)

Three researchers proposed conflicting approaches. This must be resolved before the cafe-log phase is written.

**Option A — Unified `brew_sessions` with `is_cafe_log` boolean (FEATURES.md)**
*Problem:* `brew_sessions.coffee_id` is `NOT NULL` with `ForeignKey("coffees.id", ondelete="RESTRICT")` — verified from the actual model. Making it nullable breaks a documented schema invariant. Every analytics function does an INNER JOIN on `BrewSession.coffee_id` without guards — NULL rows would be silently excluded, a maintenance trap.

**Option B — Discriminator ENUM `session_type` on `brew_sessions` (PITFALLS.md)**
*Problem:* Same `coffee_id` constraint applies. PITFALLS.md did not read the model code and missed this. The ENUM approach also requires `coffee_id` to be nullable for cafe sessions, breaking the same invariant.

**Option C — Separate `cafe_logs` table (ARCHITECTURE.md) — RECOMMENDED**
New table: `user_id`, `brand` (text), `coffee_name` (text), `brew_method` (text), `rating`, `notes`, `logged_at`. No FK to `coffees`, `bags`, or `recipes`.

*Why best-grounded:* ARCHITECTURE.md read the actual `brew_sessions` model and `analytics.py` before recommending this. Zero impact on existing analytics, AI signature computation, or scheduler logic. Migration is purely additive. Analytics isolation is explicit: cafe logs do NOT feed `compute_input_signature`, `get_top_coffees`, `get_preference_profile`, or `get_sweet_spots`. The plan-phase researcher should additionally decide whether cafe flavor notes / origin / ratings should feed AI preference derivation through a separate join, and design that if so.

### Decision 2: Charts (Chart.js) and QR Sharing (segno)

Both are conditional. Default is deferred. Confirm at requirements phase — do not add either without explicit scope confirmation from John.

### Decision 3: SSE Streaming for AI Responses

Default is deferred. Polling is adequate for the 15-30 second AI research call. Revisit in v1.3 if user feedback identifies this as a pain point.

### Decision 4: AI Prediction Storage — `ai_recommendations` Reuse vs. New Table

ARCHITECTURE.md recommends writing predictions to the existing `ai_recommendations` table with `rec_type="coffee_predict"`. FEATURES.md recommends a separate `ai_coffee_predictions` table to enable a future "did the prediction hold up?" comparison feature. Plan-phase must decide: simpler reuse vs. richer future capability. Either way, the research cache table and per-user rate limit are non-negotiable.

---

## Implications for Roadmap

### Suggested Phase Structure (8 phases)

**Phase 1: v1.1 Debt Cleanup**
Rationale: G-01 and safe-area verification are prerequisite gates for the self-host and mobile-rework phases. T-INFRA-1 gates test suite expansion.
Delivers: Closed G-01 (entrypoint runtime chown via gosu), closed T-INFRA-1 (test isolation), on-device safe-area verification, pending human UAT, `human_needed` sign-offs.
Avoids: v1.2-IMAGE-3 (root-volume bug), v1.2-MOBILE-1 (unverified safe-area spreading to every screen).

**Phase 2: Cafe Quick-Rate**
Rationale: Schema changes are highest-dependency; getting the migration verified early de-risks all dependent work.
Delivers: `cafe_logs` table migration, `CafeLog` model, cafe router with basic CRUD form, no analytics integration yet.
Avoids: v1.2-CAFE-1 (analytics pollution — isolation correct from day one), v1.2-CAFE-2 (brew prefill pulled into cafe form).
Research flag: Plan-phase must resolve the open data model decision before writing this phase.

**Phase 3: IA Restructure**
Rationale: Nav change is prerequisite for AI page consolidation.
Delivers: Updated `base.html` + `config_hub.html` + `nav-bar.js`, new `pages/ai.html` shell, relocated AI rec hero + equipment rec fragments, home page stripped of AI sections, 5 `test_nav.py` updates.
Avoids: v1.2-IA-1 (stale nav in PWA — verify cache-busting), v1.2-IA-2 (nonce-CSP on new AI page).

**Phase 4: Self-Host Packaging**
Rationale: Parallelizable with Phase 3; no shared files. G-01 fix from Phase 1 is prerequisite.
Delivers: GHCR multi-arch image, `release.yml` CI workflow, operator compose (`image:` not `build:`), `/setup` redirect for fresh installs, `depends_on: service_healthy` in compose, `pg_isready` wait in `entrypoint.sh`, updated README + NPM deploy guide.
Avoids: v1.2-IMAGE-1 through v1.2-IMAGE-5.

**Phase 5: AI Page Consolidation + Research/Predict Feature**
Rationale: Depends on Phase 3 (AI page shell). Building consolidation and new predict feature together avoids two waves of AI page template changes.
Delivers: Fully wired `/ai` page (rec hero, equipment rec, sweet spots prose); new `/ai/research` with `research_coffee_predict_rating()`, `CoffeePredictSchema`, result fragment showing predicted range + confidence + rationale + sources + "Add to wishlist" button; DB cache table for research results (7-day TTL); slowapi per-user daily rate limit with UI quota display.
Avoids: v1.2-AI-1 (cost surprise — cache + rate limit are required deliverables), v1.2-AI-2 (point-estimate rating), AI-1 (web-search token cost — `max_uses` cap), COST-2 (manual refresh throttle).
Research flag: Plan-phase must decide prediction storage approach (open decision 4).

**Phase 6: Guided Brew Mode Polish**
Rationale: Self-contained within the brew flow; can run parallel with Phase 5 if capacity allows. Depends on Phase 1 (safe-area verified).
Delivers: Web Worker-based timer surviving phone sleep, phase-based step timer from recipe steps, first drip + bloom time nullable columns on `brew_sessions`, water profiles lookup table with FK, wake-lock re-acquisition on visibility return.
Avoids: MX-4 (wake lock released on tab switch).
Research flag: Plan-phase should verify existing Guided Brew timer implementation before prescribing the fix approach.

**Phase 7: Mobile-First Full Rework**
Rationale: Depends on Phase 1 (safe-area fix verified on-device) and Phases 3-5 (IA and new pages stable). Reworking unstable templates is wasted effort.
Delivers: Every screen audited at 375px; MX-1 fix (16px min on form inputs), MX-3 fix (sticky form actions with safe-area above bottom nav), MX-6 fix (tap-on-stars rating component), MX-5 fix (localStorage draft namespaced by user ID), PWA-1 fix (iOS install banner), PWA-5 fix (theme-color dark/light meta), PWA-6 fix (maskable icon variants).
Avoids: v1.2-MOBILE-1 (must use verified safe-area pattern), v1.2-MOBILE-2 (`|tojson` quoting convention in CLAUDE.md before templates ship), MX-1 through MX-6.

**Phase 8: Verification and Release**
Delivers: Full test suite green, Playwright 375px smoke at every new page, on-device verification, `git tag v1.2.0` → GHCR image push, GitHub release notes.

### Phase Ordering Rationale

- Phase 1 first: G-01 gates Phase 4 (self-host); safe-area verification gates Phase 7 (mobile rework)
- Phase 2 early: schema migrations are lowest-risk, highest-dependency; UI builds on a verified schema
- Phase 3 before Phase 5: AI page shell must exist before AI features live there
- Phase 4 parallelizable with Phase 3: no shared files
- Phase 6 parallelizable with Phase 5: no cross-dependencies
- Phase 7 last among feature phases: reworks every screen, so all new screens must be stable first
- Phase 8 closes with tagged image push

### Research Flags

Phases needing deeper research during plan-phase:
- **Phase 2:** Open data model decision must be resolved. ARCHITECTURE's separate-table recommendation is best-grounded; planner must additionally decide whether cafe flavor/origin signal should feed AI preference derivation.
- **Phase 5:** Decide between `ai_recommendations` table reuse vs. new `ai_coffee_predictions` table. Decide cache key design (coffee name text vs. normalized ID).

Phases with standard patterns (skip additional research):
- **Phase 1:** All items are known and specified; clear fixes documented in STATE.md and project memory
- **Phase 3:** ARCHITECTURE.md provides a complete file-by-file change list
- **Phase 4:** STACK.md provides the complete GitHub Actions workflow pattern and Dockerfile fix
- **Phase 6:** Web Worker timer and wake-lock re-acquisition are well-documented browser APIs
- **Phase 7:** PITFALLS.md provides specific, actionable fixes for every mobile pitfall with exact CSS/JS patterns
- **Phase 8:** Standard milestone release gate

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI; Docker/GHCR workflow from official documentation; no version ambiguity |
| Features | HIGH (verdicts) / MEDIUM (accuracy estimates) | Adopt/skip verdicts well-reasoned from official sources; AI prediction accuracy (±0.5 error) from academic sources is directional |
| Architecture | HIGH | All findings grounded in direct source code reads of the v1.1 codebase; data model analysis read the actual SQLAlchemy model and analytics.py |
| Pitfalls | HIGH | v1.1 pitfalls verified via official docs; v1.2 pitfalls grounded in actual project history (G-01, safe-area commit, `|tojson` quoting, SW cache behavior) — authoritative |

**Overall confidence:** HIGH

### Gaps to Address

- **Cafe data model open decision:** Resolve at plan-phase. ARCHITECTURE's separate-table recommendation is best-grounded.
- **AI prediction storage approach:** Resolve at plan-phase. `ai_recommendations` reuse vs. new `ai_coffee_predictions` table.
- **SSE streaming scope:** Confirm deferred at requirements phase. Default is deferred.
- **Charts and QR code:** Confirm deferred at requirements phase. Default is both deferred.
- **Safe-area verification:** Not a gap — a concrete gating task that must appear as Phase 1's first acceptance criterion.
- **AI research cold-start gate:** Plan-phase should verify whether `analytics.get_ai_eligibility()` (or equivalent) already exists or needs to be added.

---

## Sources

### Primary (HIGH confidence)
- ARCHITECTURE.md — direct reads of `brew_session.py`, `analytics.py`, `ai_service.py`, `scheduler.py`, `base.html`, `nav-bar.js`, `sw.js`, `entrypoint.sh`, `Dockerfile`, `PROJECT.md`
- STACK.md — PyPI version pages, Docker Multi-Platform GitHub Actions official docs, GHCR official docs, segno PyPI, Chart.js GitHub releases
- PITFALLS.md — Anthropic web search tool official docs, APScheduler user guide, MDN Screen Wake Lock API, Snobbery project memory (authoritative on G-01, safe-area fix, SW cache, `|tojson` quoting, nonce-CSP/htmx-indicator incident)
- FEATURES.md — Beanconqueror GitHub repo + official site + changelog; app store sources; arXiv on AI rating prediction

### Secondary (MEDIUM confidence)
- Cafe quick-rate UX patterns — modeled from competitor UX; not validated against production data
- AI predict-rating accuracy claims — academic sources; actual household accuracy unknown until shipped

### Tertiary (LOW confidence)
- structlog performance claim ("25% faster") — single recent source; treat as directional

---

*Research completed: 2026-05-25*
*Ready for roadmap: yes — open decisions flagged above must be resolved by plan-phase researcher before the cafe-log and AI-research phases are written*
