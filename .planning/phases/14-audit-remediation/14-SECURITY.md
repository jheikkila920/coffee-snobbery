---
phase: 14
slug: audit-remediation
status: verified
threats_open: 0
asvs_level: 2
created: 2026-05-25
---

# Phase 14 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Phase 14 remediated 5 prior code-review findings (B1, B4, S1, B2, S4). The
> threat register was authored at PLAN time across all 4 plans and verified in
> code by gsd-security-auditor.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| admin user → admin user-management endpoints | Authenticated admin issues state-changing POSTs that mutate other users' privilege/active state | user privilege + active-state mutations |
| concurrent admin requests → users table | Two admin mutations in separate threadpool transactions can interleave the read-modify-write on active-admin count | active-admin count (lockout-critical) |
| authenticated user → paste-and-rank (`_fetch_page_text`) | Any logged-in household user supplies an arbitrary URL the server fetches server-side | arbitrary outbound URL (SSRF surface) |
| AI-recommended buy URL → `_verify_buy_url` | An LLM-produced URL is fetched server-side to verify the product | LLM-produced outbound URL (SSRF surface) |
| server → resolved IP (egress) | The server's outbound request can reach private subnets / cloud-metadata if the host resolves internally | internal network / 169.254.169.254 metadata |
| stale session rows → sessions table | Expired but undeleted session rows accumulate; authoritative expiry must be enforced server-side over time | session records (expiry hygiene) |
| authenticated user → GET /search | Logged-in user supplies an arbitrary `q` string at arbitrary frequency | search query string + request rate |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-V4-01 | Denial of Service | `_count_active_admins` (`app/routers/admin/users.py:71-77`) | mitigate | Locked-subquery COUNT `select(func.count()).select_from(locked_subq)` replaces invalid FOR-UPDATE-on-aggregate; no `text(` / `FOR UPDATE` raw string remains. Guard now evaluable instead of 500ing every demote/deactivate/delete of another admin. | closed |
| T-V4-02 | Elevation of Privilege / Lockout | last-admin guard race across 4 call sites (`app/routers/admin/users.py:71-75`) | mitigate | `with_for_update()` retained on the inner `User.id` subquery serializes concurrent admin mutations at the DB level; system can never be demoted to zero active admins. All 4 call sites invoke the guard before mutating. | closed |
| T-V4-03 | Dead code (maintenance risk) | duplicate self-demote guard (was `users.py:298-300`) | accept→remove | Unreachable duplicate removed (D-09). Two remaining `"demote yourself"` strings (lines 305, 374) are both LIVE guards (`update_user` + `toggle_admin`); no dead code, no live guard removed. | closed |
| T-SSRF-priv | Information Disclosure | `_assert_public_host` over both fetchers (`app/services/ai_service.py:253`) | mitigate | `addr.is_private` rejects 10/8, 172.16/12, 192.168/16, fc00::/7 pre-connect for every resolved IP. | closed |
| T-SSRF-lo | Information Disclosure | both fetchers (`ai_service.py:254`) | mitigate | `addr.is_loopback` rejects 127/8 and ::1. | closed |
| T-SSRF-meta | Elevation of Privilege | both fetchers (`ai_service.py:255,257`) | mitigate (HIGH) | `addr.is_link_local` rejects 169.254.0.0/16 incl. 169.254.169.254 cloud-metadata; additional `not addr.is_global` check is defense-in-depth. | closed |
| T-SSRF-mapped | Elevation of Privilege | `_assert_public_host` normalization (`ai_service.py:246-247`) | mitigate (HIGH) | `IPv6Address.ipv4_mapped` normalization reclassifies `::ffff:169.254.169.254` to its IPv4 form before classification — closes the mapped-address bypass. | closed |
| T-SSRF-fetch | Information Disclosure | `_fetch_page_text` (auth-reachable paste-and-rank) (`ai_service.py:1543`) | mitigate | `if not _assert_public_host(url): return ""` placed after scheme check, before httpx — same gate as `_verify_buy_url`, covering the user-reachable fetcher. | closed |
| T-SSRF-dns | Denial of Service / crash | `_assert_public_host` OSError handling (`ai_service.py:228-234`) | mitigate | `socket.getaddrinfo` wrapped in `try/except OSError: return False`; DNS failure is a rejection, no exception escapes the fetcher. | closed |
| T-SSRF-pub | Availability (false-block) | `_assert_public_host` (`ai_service.py:239-260`) | mitigate | Returns `True` only after all resolved IPs pass classification; `test_ssrf_public_url_allowed` confirms no over-blocking of public hosts. | closed |
| T-SSRF-toctou | TOCTOU / DNS-rebinding | resolve-vs-connect gap (`ai_service.py:219-221`) | accept | D-05: pre-resolve validation only; sub-ms TOCTOU / DNS-rebinding window accepted at household scale (both fetchers authenticated-only, 2-person household). Documented in `_assert_public_host` docstring. | closed |
| T-SSRF-base | Regression | existing scheme + no-redirect defenses (`ai_service.py:182-183,190 / 1539-1541,1548`) | mitigate | https-only scheme check and `follow_redirects=False` retained ahead of / alongside the new IP gate. | closed |
| T-V3-01 | Information Disclosure / hygiene | sessions table growth (`app/services/scheduler.py:389-390,131`) | mitigate | Nightly `DELETE FROM sessions WHERE expires_at < now()` (strict `<` on authoritative `expires_at`) at 03:00 APP_TIMEZONE via `CronTrigger(hour=3, minute=0)`. | closed |
| T-V3-02 | Tampering (job duplication) | scheduler job registration (`scheduler.py:129-134`) | mitigate | Stable id `nightly_session_sweep` + `replace_existing=True` keeps registration idempotent across restarts (3 jobs total, never duplicated); asserted by `test_idempotent_job_registration`. | closed |
| T-V3-03 | Excluded scope creep | admin "Sweep now" button | accept | Deferred per D-06 — stale sessions are harmless until swept; a manual endpoint would add CSRF + UI surface for no household-scale benefit. No such endpoint exists in the codebase. | closed |
| T-V5-01 | Denial of Service | `search_results` q length (`app/routers/search.py:44-45`) | mitigate | `if len(q) > 100: return HTMLResponse("", status_code=200)` as first body statement, on RAW `q` before `.strip()`, short-circuiting over-long input before any DB query. | closed |
| T-V10-rl | Denial of Service / scraping | `search_results` request rate (`app/rate_limit.py:44`, `app/routers/search.py:32`) | mitigate | `SEARCH_LIMIT = "60/minute"` + `@limiter.limit(SEARCH_LIMIT)` (route decorator outermost, limiter next), keyed by `get_remote_address`; `test_search_rate_limit` confirms a 429 at request 61. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-14-01 | T-SSRF-toctou | Pre-resolve SSRF validation is not IP-pinned to the eventual connection, leaving a sub-ms TOCTOU / DNS-rebinding window. Both fetchers are authenticated-only at a 2-person household scale; full IP-pinning was scoped out per D-05 (ROADMAP criterion #2 amended). Documented in the `_assert_public_host` docstring. | John (D-05) | 2026-05-25 |
| AR-14-02 | T-V3-03 | No admin "Sweep now" button for sessions; sweeping is scheduler-only (nightly). Stale session rows are harmless until swept; a manual endpoint would add CSRF + UI surface for no household-scale benefit. Deferred per D-06. | John (D-06) | 2026-05-25 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-25 | 17 | 17 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-25
