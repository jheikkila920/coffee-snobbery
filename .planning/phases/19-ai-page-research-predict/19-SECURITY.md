---
phase: 19
slug: ai-page-research-predict
status: verified
threats_open: 0
asvs_level: 2
created: 2026-05-29
---

# Phase 19 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

**Audit date:** 2026-05-29
**Auditor:** gsd-security-auditor (opus)
**ASVS Level:** 2 | **block_on:** high
**Verdict:** SECURED — 36/36 threats resolved (29 mitigated + verified, 7 accepted)
**Register provenance:** authored at plan time (`register_authored_at_plan_time: true`); verified against implementation, not re-derived. Every `mitigate` threat was confirmed by locating the actual code (file:line), not by trusting SUMMARY claims. Every `accept` threat was confirmed to have a coherent rationale and, where applicable, a present compensating control.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| LLM tool_use output → Pydantic schema | Untrusted model / web-search output crosses into validated app objects | AI-derived structured data (research/improve/prose schemas) |
| AI-provided buy_url → outbound HTTP | SSRF + archived-lot risk crosses to the network | URL |
| web-search results → recommendation prompt | Prompt-injection / stale-lot tampering | Search-grounded text |
| client POST → research / improve-brew flow | Quota-bypass attempts + IDOR (cross-user session access) cross here | coffee_name / roaster / session_id |
| SSE generator → browser | Error events must not leak internals; payload must not be buffered/replayed behind NPM | AI prose / short error strings |
| AI prose → rendered HTML | XSS via injected prose crosses into the authenticated DOM (the CR-01 sink) | AI-derived prose / coffee_name |
| CDN scripts → page CSP | Third-party script execution boundary (Chart.js, htmx-ext-sse) | Third-party JS |
| client → wishlist add | source_url scheme boundary (javascript:/data:) | URL |
| admin settings → quota cap | Privileged change to the cost-control bucket | Admin input |
| user request rate → rolling-24h quota counter | The AI cost-control boundary — quota must bound LLM spend | Request rate |
| migration DDL → runtime | New tables become app-trusted storage | Schema |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Status | Evidence (file:line) |
|-----------|----------|-----------|-------------|--------|----------------------|
| T-19-01 | Tampering | new Pydantic schemas | mitigate | closed | `ConfigDict(extra="forbid")` on every new schema: ai_schemas.py:50,67,84,105,153,167,198,229,260,282,300,319 |
| T-19-02 | Tampering | ai_rating_predictions cross-user rows | mitigate | closed | user_id FK `ondelete="CASCADE"` + `UniqueConstraint(user_id, research_cache_key)`: models/ai_rating_prediction.py:36,62-67; migration p19_ai_research_predict.py:102,128-131; writes user-scoped: ai_research.py:329-337 |
| T-19-03 | Info Disclosure | research cache shared across users | accept | closed | Research cache is world-view/non-personal (D-06); shared by design. See Accepted Risks. |
| T-19-SC | Tampering (supply chain) | sse-starlette pip install | mitigate | closed | `sse-starlette>=3.4,<4` pinned: requirements.txt:34 |
| T-19-04 | Spoofing/SSRF | _verify_buy_url buy_url fetch | mitigate | closed | scheme allowlist (ai_service.py:199), `_assert_public_host` IP gate (234-283), `follow_redirects=False` (207), 64KB Range (213), 5s timeout (208), reject 404/410 (219) |
| T-19-05 | Tampering | recipe recommendation prompt | mitigate | closed | for-sale-only clause on every tier: ai_service.py:834-865; citation projector `_project_tool_use_input`: 147-169; retry bounded: 1063 |
| T-19-06 | DoS | archived-retry amplification | mitigate | closed | single-shot `_archived_retry_attempted` guard: ai_service.py:920,1063,1070; advisory-lock backstop: 304-316 |
| T-19-07 | Elevation | research quota bypass via direct POST | mitigate | closed | quota COUNT keyed to user_id, DB-backed: ai_quota.py:32-50; called with server user_id: ai_research.py:422 |
| T-19-08 | Tampering | CoffeeResearchSchema from web-search | mitigate | closed | `_project_tool_use_input` + `CoffeeResearchSchema.model_validate`: ai_research.py:539-540; extra=forbid: ai_schemas.py:229 |
| T-19-09 | Info Disclosure | SSE event:error leaking stack trace | mitigate | closed | error event emits short string; real exc structlogged: ai_research.py:541-551 |
| T-19-10 | DoS/double-charge | EventSource reconnect re-fires LLM | mitigate | closed | `_get_lock` + `_try_advisory_lock` held across generator: ai_research.py:469-477; concurrent → error event |
| T-19-11 | Spoofing/SSRF | research buy_url | mitigate | closed | `_verify_buy_url` NOT in generator; scheduled as BackgroundTask by route: routers/ai.py:186-220,602; ai_research.py:392 |
| T-19-12 | Elevation/IDOR | generate_brew_improvement session load | mitigate | closed | session loaded `by_user_id=user_id`, None→error: ai_service.py:1974-1977 |
| T-19-13 | Tampering | BrewImproveSchema / PreferenceProfileProseSchema | mitigate | closed | `_project_tool_use_input` + `BrewImproveSchema.model_validate`: ai_service.py:2048-2049; extra=forbid: ai_schemas.py:300,319 |
| T-19-14 | Elevation | improve-brew quota bypass | mitigate | closed | separate `brew_improvement` quota bucket, user-keyed: ai_quota.py:23-26; ai_service.py:1982 |
| T-19-15 | DoS | nightly regen cost growth | accept | closed | prose regenerates only on signature change; brew_improvement on-demand; research cache TTL-driven. See Accepted Risks. |
| T-19-16 | Elevation | research/improve-brew quota bypass | mitigate | closed | quota keyed to `request.state.user.id`, checked BEFORE EventSourceResponse: routers/ai.py:552,575-588 (research), 688,696-712 (improve) |
| T-19-17 | Elevation/IDOR | POST /ai/improve-brew/{session_id} cross-user | mitigate | closed | `get_brew_session(..., by_user_id=user_id)` → HTTPException(404): routers/ai.py:691 + ai_service.py:1974 |
| T-19-18 | Info Disclosure | chart JSON leaking other users' data | mitigate | closed | both chart queries bound `:user_id`, both UNION sides scoped: services/charts.py:54,60,92,96; routes pass user.id: routers/ai.py:776,792 |
| T-19-19 | Info Disclosure | SSE event:error stack trace | mitigate | closed | error events emit user-facing string; structlog server-side: ai_research.py:541-551, ai_service.py:2050-2060 |
| T-19-20 | Tampering | SSE buffered/replayed behind NPM | mitigate | closed | `X-Accel-Buffering: no` on all SSE responses: routers/ai.py:614,731; EventSourceResponse default `Cache-Control: no-cache`; NPM `proxy_buffering off;` documented: docs/DEPLOY.md:138 |
| T-19-21 | Tampering/XSS | AI prose rendered in research/improve fragments | mitigate | closed | research_result.html + improve_result.html fully autoescaped, no `\|safe`; newlines via `.split('\n')` loop not raw HTML |
| T-19-22 | Tampering (CSP) | Chart.js / htmx-ext-sse CDN scripts under strict CSP | mitigate | closed | Chart.js (base.html:63) + htmx-ext-sse (base.html:77) both carry `nonce="{{ csp_nonce(request) }}"`; UMD build, no eval |
| T-19-23 | Tampering | wishlist source_url (javascript:/data:) | mitigate | closed | `/ai/wishlist/add` drops non-https source_url: routers/ai.py:442 |
| T-19-24 | Info Disclosure | stale SW cache serving old /ai | mitigate | closed | content-deterministic SW cache: `CACHE_NAME='snobbery-v__BUILD_HASH__'` (sw.js:5) bumped per-build: routers/pwa.py:30-63 |
| T-19-25 | Tampering | admin lowering/raising quota cap | accept | closed | admin-only quota route, audited via ADMIN_APP_SETTING_CHANGED (D-08). See Accepted Risks. |
| T-19-26 | DoS | misapplied NPM config buffers SSE | accept | closed | functional fallback if NPM misconfigured; operator step + smoke test documented (docs/DEPLOY.md). See Accepted Risks. |
| T-19-27 | Info Disclosure | latency ledger exposing internals | accept | closed | 19-VERIFICATION.md is a planning artifact, not user-facing; no secrets. See Accepted Risks. |
| T-19-08-01 | Stored XSS | _render_research_result event:complete emit | mitigate | closed | renders via fragments/ai/research_result.html (autoescape); no f-string sink: ai_research.py:689-724; acceptance grep clean |
| T-19-08-02 | Tampering (raw-HTML SSE) | generate_brew_improvement terminal emit | mitigate | closed | renders fragments/brew/improve_result.html, emits HTML not JSON: ai_service.py:2164-2168 |
| T-19-08-03 | Residual raw-HTML SSE | any remaining f-string/`\|safe` AI-prose render | mitigate | closed | grep across app/: zero `f"<div id=research-result`, zero `json.dumps(...model_dump())` complete emits; all `\|safe` hits are negation comments |
| T-19-08-04 | CSRF (wishlist add) | wishlist-add form rendered request=None | accept | closed | request=None → empty CSRF field (research_result.html:45 guards None); POST independently protected by CSRFMiddleware double-submit. See Accepted Risks. |
| T-19-09-01 | DoS/cost-abuse | get_or_refresh_prediction signature-driven regen on cache-hit | mitigate | closed | signature-driven regen bounded to TTL window: ai_research.py:246-249; cache-hit prediction committed (WR-02): 459,492 |
| T-19-09-02 | Repudiation/Info Disclosure | broad `except (..., Exception)` swallowing programming errors | mitigate | closed | three broad-except sites narrowed to provider/parse errors: ai_service.py:1025,1119,1133 |
| T-19-09-03 | Elevation/cost-abuse | rolling-24h quota check-then-write TOCTOU | accept | closed | 20/day cap + per-user advisory lock; documented inline ai_research.py:415-421 (D-05). See Accepted Risks. |
| T-19-09-04 | Tampering (misleading UX) | negative reset countdown from unclamped delta | mitigate | closed | `format_reset` clamps `max(0, ...)` before H/M split, single helper at every site: ai_quota.py:94-110; callers ai_research.py:426, ai_service.py:1986, routers/ai.py:642 |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Threat ID | Risk | Rationale | Compensating Control |
|-----------|------|-----------|----------------------|
| T-19-03 | Research cache shared across users | A coffee's world-view (origin, process, tasting notes) is non-personal public data; sharing is the intended cost-saving design (D-06). Per-user data (rating prediction) lives in a separate user-scoped table. | Cache stores only world-view fields; no per-user data in `ai_coffee_research_cache`. |
| T-19-15 | Nightly AI regen cost growth | Prose regenerates only on input-signature change; brew_improvement is on-demand; research served from 30-day TTL cache. Bounded at household scale. | Signature-gated regen; TTL cache; per-bucket daily quota (20/day). |
| T-19-25 | Admin lowering/raising quota cap | Intended admin capability (D-08); admin-only route; every change audited. | `ADMIN_APP_SETTING_CHANGED` audit log; admin-auth gate on route. |
| T-19-26 | Misapplied NPM config buffers SSE | If `proxy_buffering off;` is omitted, SSE degrades to a functional non-streamed fallback (no security impact, UX-only). | Documented operator step + smoke test in docs/DEPLOY.md:138; app emits `X-Accel-Buffering: no` as defense-in-depth. |
| T-19-27 | Latency ledger exposing internals | 19-VERIFICATION.md is a planning artifact in `.planning/`, never served by the app; contains no secrets. | Artifact outside web root; no route serves it. |
| T-19-08-04 | Wishlist-add CSRF field empty when request=None | The SSE-rendered fragment may render with request=None, producing an empty hidden CSRF value, but the POST is independently enforced by CSRFMiddleware (double-submit cookie+header); the client form carries the token from the cookie. | `starlette-csrf` CSRFMiddleware global enforcement; template guards None (research_result.html:45). |
| T-19-09-03 | Rolling-24h quota check-then-write TOCTOU | A check-then-write window exists between `remaining()` and telemetry commit. At household scale with a 20/day cap, the blast radius is a few extra calls/day. Explicitly accepted (WR-01/D-05); the advisory-lock-before-quota fix is deliberately NOT implemented. | Per-(user, rec_type) asyncio.Lock + Postgres advisory lock serialise concurrent misses; 20/day hard cap; documented inline ai_research.py:415-421. |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

None. All `## Threat Flags` / `## Threat Surface Scan` sections across SUMMARYs 19-01 through 19-09 explicitly report no new network endpoints, auth paths, or schema surface beyond the planned register. Every flag maps to an existing T-19-* threat ID. No unmapped attack surface detected.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-29 | 36 | 36 | 0 | gsd-security-auditor (opus) |

---

## Notes

- Implementation files were treated as READ-ONLY; nothing was modified.
- WR-04 scope: only the three `_generate_coffee_rec` except sites (ai_service.py:1025/1119/1133) were in scope for T-19-09-02. The remaining `except Exception` blocks (ai_service.py:1423,1561,1723,1863,2121,2344) are in separate flows outside the WR-04 register entry and emit user-facing error events with structlog — not a gap against this register.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-29
