---
phase: 7
slug: ai-services
status: verified
threats_open: 0
asvs_level: 2
created: 2026-05-21
---

# Phase 7 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 7 PLAN.md files carried a `<threat_model>` block).
> Verified in **verify-mitigations mode** by gsd-security-auditor against the implementation.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| AI provider response → app | LLM/tool output (incl. web-search results) is untrusted input crossing into structured parsing | tool_use blocks, prose, suggested URLs |
| AI-suggested buy_url → outbound fetch | AI-generated URL is an attacker-influencable SSRF vector when fetched for verification | URL string → server-side HTTP GET |
| user-supplied paste-rank URL → outbound fetch | User-controlled URL is a direct SSRF vector | URL string → server-side HTTP GET |
| browser → /ai/* POST routes | Untrusted client requests, including entry ids and pasted input | form fields, entry_id, pasted text |
| AI provider credentials → SDK | Decrypted Fernet key consumed only at client construction | plaintext API key (in-memory only) |
| concurrent callers (manual + scheduler) → regenerate | Race on the same user's coffee bundle / cost abuse | per-user regen requests |
| AI prose + buy_url → rendered HTML | LLM-generated text/URL rendered in the user's browser | prose, coffee names, buy_url |
| browser form → wishlist write | entry_id and coffee fields arrive from the client; user_id must be server-set | wishlist add/purchase/remove |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Info Disclosure / Tampering (SSRF) | `_verify_buy_url` ranged GET; `_verify_and_persist_url` bg task | mitigate | https-only scheme check before network call (`ai_service.py:179`); `follow_redirects=False` (`:184`); 64KB Range cap (`:191`); 5s timeout (`:185`). Tests: `test_url_verify_scheme_rejected`, `test_url_verify_ssrf_redirect`. | closed |
| T-07-02 | Tampering / Elevation (prompt injection) | `_project_tool_use_input` + Pydantic schemas | mitigate | Keep-only-named-tool_use projection discards text/web-search blocks (`ai_service.py:146-149`); `ConfigDict(extra="forbid")` on all schemas (`ai_schemas.py:94,156,187`); ValidationError → "try_again". Tests: `test_citation_projector`, `test_pydantic_validation_error_try_again`. | closed |
| T-07-03 | Info Disclosure (secret leakage) | `_build_*_client`, `_write_recommendation_row`, structlog/events | mitigate | `cred.key` passed only to SDK constructors; logs emit only `provider`/`model` (`ai_service.py:252,266`); write helper persists only `provider_used`/`model_used`; no key field in any schema or event taxonomy. | closed |
| T-07-04 | Denial of Service (unbounded state growth) | `_THROTTLE` module dict | mitigate | `_evict_stale_throttle` removes entries older than 10-min window on every access (`ai_service.py:111-119`), called at `ai.py:181`. Test: `test_throttle_eviction`. | closed |
| T-07-05 | Info Disclosure / Tampering (IDOR) | wishlist get/mark_purchased/remove by entry_id; router None→404 | mitigate | Every query filters `user_id == by_user_id` (`wishlist.py:70-75`); cross-user → None/False; router maps to 404 (`ai.py:404-406,430-432`). Tests: `test_get_wishlist_entry_cross_user_returns_none`, `test_remove_cross_user_false_keeps_row`, `test_wishlist_purchase_cross_user_404`, `test_wishlist_remove_cross_user_404`. | closed |
| T-07-06 | Tampering | user_id assignment on wishlist add | mitigate | `by_user_id` is keyword-only after `*` (`wishlist.py:25`); set from `user.id` via `Depends(require_user)` (`ai.py:372`); never read from form/query. | closed |
| T-07-07 | DoS / cost abuse (concurrent regen + refresh) | `regenerate` locks; `/ai/refresh` | mitigate | In-memory lock + Postgres `pg_try_advisory_xact_lock` → second concurrent run returns "locked" (`ai_service.py:1162-1168`); `/ai/refresh` enforces 5-min throttle (429) + in-flight lock (429) before any LLM call (`ai.py:180-213`). Tests: `test_advisory_lock_concurrent`, `test_throttle_429`, `test_in_flight_429`. | closed |
| T-07-08 | DoS / cost (needless regen) | signature skip | mitigate | Unchanged signature + `force=False` → "skipped" (`ai_service.py:1176`). Test: `test_sig_skip` (asserts generator not called). | closed |
| T-07-09 | Info Disclosure / Tampering (SSRF) | `_fetch_page_text` (user paste-rank URL) | mitigate | https-only check (`ai_service.py:1487-1489`); `follow_redirects=False` (`:1493`); 128KB Range cap (`:1498-1500`); 5s timeout (`:1494`); html.parser only; URL count capped at 5 (`_MAX_PASTE_RANK_URLS`, `:83-84`, applied `:1559`). Tests: `test_paste_rank_fetch_https_only`, `test_paste_rank_fetch_no_cross_host_redirect`. | closed |
| T-07-10 | DoS / cost (paste-rank repeated submits) | paste-rank flow | accept | Accepted risk — see Accepted Risks Log. Bounding verified: single LLM call per invocation; fetch capped at 5 URLs × 128KB / 5s. | closed |
| T-07-11 | Cross-Site Request Forgery | every `/ai/*` POST | mitigate | starlette-csrf double-submit enforced globally; no `/ai/*` POST is csrf-exempt; forms carry `X-CSRF-Token` (`ai_rec_hero.html:86`, `wishlist.html:58,72`, `ai_rec_try_again.html:9`). Test: `test_wishlist_add_requires_csrf` (403 without token). | closed |
| T-07-12 | Spoofing / Access Control | all `/ai/*` routes | mitigate | Every route carries `Depends(require_user)` (`ai.py:57,79,161,271,309,349,393,419`); `user_id` only from `user.id`; no form/query user_id. Tests: `test_wishlist_page_requires_auth`, `test_refresh_requires_auth` (401). | closed |
| T-07-13 | Tampering / XSS | hero card + sweet-spots prose; paste-rank/equipment/wishlist render | mitigate | All AI prose/coffee names rendered via Jinja autoescape; NEVER `\|safe` across six templates; CR-01 fix present (`ai.py:369-370` nulls non-https `source_url` before storage). Test: `test_wishlist_add_drops_non_https_url`. | closed |
| T-07-14 | Tampering (malicious buy_url) | hero buy link | mitigate | `<a>` rendered only when `rec.url_verified` truthy (`ai_rec_hero.html:37`); None → "verifying"; False → plain text. Wishlist add form gates `source_url` on `prose.buy_url and rec.url_verified`. | closed |
| T-07-15 | Info Disclosure (secret) | response_json render | mitigate | `response_json` always a dict from schema `model_dump()`; no schema contains a key/credential field; `cred.key` never enters `_write_recommendation_row`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-10 | No per-user throttle on paste-rank. On-demand, user-gated flow; per-call cost bounded: single LLM call, fetch loop capped at 5 URLs (`ai_service.py:83-84,1559`), each 128KB / 5s. Accepted for v1; revisit if multi-user load increases. | John (plan-time disposition, 07-04-PLAN.md) | 2026-05-21 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 15 | 15 | 0 | gsd-security-auditor (sonnet), verify-mitigations mode |

### Prior code-review criticals confirmed fixed (07-REVIEW.md, commit d9ec8f6)

| Finding | Status | Evidence |
|---------|--------|----------|
| CR-01: Stored XSS via non-https source_url | fixed | `ai.py:369-370` nulls non-https `source_url`; `test_wishlist_add_drops_non_https_url`. |
| CR-02: NoneType crash in `_generate_sweet_spots_prose` | fixed | `ai_service.py:599-601` — `if cred is None: return None` guard. |
| CR-04: Uncapped URL fetch loop | fixed | `_MAX_PASTE_RANK_URLS = 5` (`ai_service.py:83-84`) applied at `:1559`. |
| CR-05: Empty coffee_name accepted | fixed | `ai.py:363-365` raises 422; `test_wishlist_add_empty_name_422`. |

### Non-blocking warnings (operator awareness, not security gaps)

- WR-01: `test_throttle_429` MagicMock pattern may pass for the wrong reason — actual throttle verified by router `_THROTTLE` check.
- WR-02: sync LLM call inside `async def` blocks the event loop during generation — accepted at household scale.
- WR-04: equipment query fetches all users' equipment — shared household catalog, logic not security.
- WR-05: bare `except Exception` in equipment router path — log gap, not a vulnerability.
- WR-06: double-logging of `AI_GENERATION_SUCCESS` — operational noise.
- CR-03: `asyncio.CancelledError` can escape BaseException catch — correctness concern, not a direct vulnerability.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-21
