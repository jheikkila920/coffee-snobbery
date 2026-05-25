# Phase 14: Audit Remediation - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the five verified defects from the Codex audit (independently confirmed against the code, live Postgres, and the test suite). **Correctness + security hardening only.** No schema changes, no AI-scheduling logic changes, no deployment-topology changes, no new features.

The five items, by severity:
- **B1 [CRITICAL]** — `_count_active_admins` `FOR UPDATE`-on-aggregate crash (proven live: `ERROR: FOR UPDATE is not allowed with aggregate functions`)
- **S1 [HIGH]** — SSRF: private/internal IPs not blocked in `_verify_buy_url` / `_fetch_page_text`
- **B2 [MEDIUM]** — no nightly expired-session sweep (deferred TODO at `sessions.py:182-185`)
- **S4 [LOW]** — `/search` has no length cap and no rate limit
- **B4 [LOW]** — dead duplicate self-demote guard at `users.py:298-300`

**Deliberately EXCLUDED after verification** (do NOT re-open in planning): login-CSRF on `/login`+`/setup` (documented accepted household-scale risk, `app/csrf.py:46-55`); app-layer HSTS (offloaded to Nginx Proxy Manager by design); async/sync handler mixing in `run_ai_refresh`/`post_ai_refresh`/`_verify_and_persist_url` (Codex overstated — the AI call is `await`ed on an async client, so the loop is not blocked; only short sync DB ops block); `_LOCKS` dict eviction (negligible, bounded by users × rec-types).

</domain>

<decisions>
## Implementation Decisions

### B1 — Last-admin guard crash (CRITICAL)
- **D-01:** Fix `_count_active_admins` (`app/routers/admin/users.py:64-68`) by wrapping the locked select in a subquery: `SELECT COUNT(*) FROM (SELECT id FROM users WHERE is_admin = true AND is_active = true FOR UPDATE) sub`. This is the minimal correct fix and **keeps the row lock** — it is NOT decorative. These are sync DB handlers in a threadpool, so two concurrent admin mutations can hold separate transactions and interleave the read-modify-write; `FOR UPDATE` serializes that real (if rare) demote-to-zero-admins race. Plain `COUNT` was rejected for reintroducing the bug class.
- **D-02:** Add the regression test for the **currently-untested path**: admin A demoting / deactivating / deleting admin B with 2+ admins present must succeed (today it 500s — existing tests only exercise the self path, which short-circuits before the query). Cover all 4 call sites (`update_user` ~292, `toggle_admin` ~365, `deactivate_user` ~416, `delete_user` ~484). Existing guard tests must still pass.

### S1 — SSRF private-IP block (HIGH)
- **D-03:** Use **resolve-validate-connect**, NOT full IP pinning. Steps: `socket.getaddrinfo(host)` → reject if ANY resolved address is private/loopback/link-local/ULA/reserved → then perform the existing normal `client.get(url)`. ~15 lines, no custom httpx transport. Rationale: both functions are authenticated-only (paste-and-rank requires login; household = John + Farrah), so the sub-millisecond TOCTOU / DNS-rebinding window is academic. KISS wins over fiddly TLS-to-IP plumbing.
- **D-04:** Block ranges via stdlib `ipaddress`: `is_private` (covers `10/8`, `172.16/12`, `192.168/16`, `fc00::/7`), `is_loopback` (`127/8`, `::1`), `is_link_local` (`169.254/16`, `fe80::/10`), `is_reserved`. **Must also handle IPv4-mapped IPv6** (`::ffff:10.0.0.1`) — normalize before checking. Apply the same gate to BOTH `_verify_buy_url` (~`:157`) and `_fetch_page_text` (~`:1466`); extend the existing scaffolding (scheme allowlist, `follow_redirects=False`, 5s timeout, `Range` body cap) rather than rewriting. Tests must prove internal hosts are refused (incl. `169.254.169.254`, `127.0.0.1`, `localhost`-resolving, IPv4-mapped) and public URLs still pass.
- **D-05 [ROADMAP AMENDMENT]:** This relaxes Phase 14 success criterion #2's wording "connects to the pinned resolved IP (DNS-rebinding safe)." The accepted behavior is now "block on **pre-resolve validation** of all resolved IPs," with a documented, accepted sub-ms TOCTOU window at household scale. Planner/verifier should grade against this amended criterion, not the literal "pinned IP" phrasing.

### B2 — Expired-session sweep (MEDIUM)
- **D-06:** Add one nightly APScheduler job in `app/services/scheduler.py` running `DELETE FROM sessions WHERE expires_at < now()` (the `expires_at` btree index from migration `p1_sessions` makes it cheap). Schedule **03:00 `APP_TIMEZONE`** (after the 02:00 backup, before the 00:00 AI job's window — clean low-traffic slot). Stable id `nightly_session_sweep`, idempotent via `replace_existing=True` exactly like the existing two jobs (→ 3 total). **Scheduler-only — no admin "Sweep now" button** (that endpoint would be scope creep; stale sessions are harmless until swept). Close the deferred TODO at `sessions.py:182-185`. Test proves expired rows are deleted and unexpired rows retained.

### S4 — /search hardening (LOW)
- **D-07:** In `app/routers/search.py`, cap `q` length at **100 chars** — over-long input short-circuits to an empty `200` (same shape as the existing `<2 chars` guard at line 42). No legitimate search is longer.
- **D-08:** Add a slowapi rate limit of **`60/minute` per IP** via a new `SEARCH_LIMIT` constant in `app/rate_limit.py` (mirror the existing `LOGIN_LIMIT`/`CSP_REPORT_LIMIT` constant pattern + `@limiter.limit(SEARCH_LIMIT)` decoration; keep `get_remote_address` keying). 60/min sits comfortably above debounced live-search bursts (250ms debounce + `hx-sync` cancels in-flight) while still capping a scripted abuse loop. The current `search_results` handler is sync — slowapi decoration requires the handler to accept `request: Request` (already present).

### B4 — Dead code removal (LOW)
- **D-09:** Delete the unreachable duplicate self-demote guard at `app/routers/admin/users.py:298-300` — its condition is already fully handled at lines 290-296 (the `admin_count <= 1` and `target_id == admin_user.id` checks both run first). Pure deletion, no behavioral change.

### Cross-cutting
- **D-10:** Items B1 and S1 touch auth/admin and security (CLAUDE.md "ask-first" areas, and touch the AI service) — work on a **feature branch + merge**, not direct-to-`main`, per CLAUDE.md branch policy. John approved this scope.

### Claude's Discretion
- Exact wave/plan breakdown and whether items ship as one PR with atomic per-item commits or split. The five items are largely independent (B1+B4 share `users.py`; the rest are disjoint files) — let dependency analysis decide.
- Where the SSRF resolve-and-validate helper lives (e.g., a small `_assert_public_host(url)` helper in `ai_service.py` reused by both functions vs inline) — DRY it sensibly.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Authoritative scope + success criteria
- `.planning/ROADMAP.md` — Phase 14 section (≈ lines 416-431): the five success criteria with pinned file:line root causes, plus the verified-and-EXCLUDED list. **This is the contract.** Note D-05 amends success criterion #2's "pinned IP" wording.

### Accepted-risk / excluded-item evidence
- `app/csrf.py:46-55` — documents the deliberately-accepted login-CSRF risk (the reason login-CSRF is excluded from this phase).

### No dedicated ADRs
- No `docs/decisions/` ADR governs these five items; the ROADMAP Phase 14 entry + this CONTEXT are the decision record. If S1's amendment (D-05) warrants a standing record, the planner may add a short ADR under `docs/decisions/` rather than editing the GSD spec.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets / Patterns to extend (do NOT rewrite)
- **SSRF scaffolding** already in `_verify_buy_url` (`ai_service.py:157-202`) and `_fetch_page_text` (`:1466-1505`): scheme allowlist (`startswith("https://")`), `follow_redirects=False`, `httpx.Timeout(5.0)`, `Range` body cap, broad `except (TimeoutException, RequestError)`. Add the resolve-validate gate ahead of the existing `client.get`; reuse the failure-return convention (`False` / `""`).
- **Rate-limit constant pattern**: `app/rate_limit.py` defines `LOGIN_LIMIT`/`SETUP_LIMIT`/`CSP_REPORT_LIMIT` strings; routers import the constant and decorate with `@limiter.limit(...)`. `limiter` is module-level `Limiter(key_func=get_remote_address)`. Add `SEARCH_LIMIT` the same way.
- **Scheduler job pattern**: `register_jobs()` (`scheduler.py:103-127`) uses `target.add_job(fn, CronTrigger(hour=, minute=, timezone=settings.APP_TIMEZONE), id=, replace_existing=True)`. The new sweep follows this exactly; idempotency test mirrors the existing 2-job assertion.

### Integration Points
- `_count_active_admins` (`users.py:64`) + 4 call sites (≈292/365/416/484) — single-function fix, all call sites benefit.
- `sessions.py:182-185` — the TODO the sweep job closes; `SessionModel` + `expires_at` column + `p1_sessions` btree index already exist.
- `search_results` handler (`search.py:30-49`) — add length cap inline + the limiter decorator; already takes `request: Request`.

### Test surface
- `tests/services/test_ai_service.py` — existing SSRF tests cover only scheme rejection (`test_url_verify_scheme_rejected` :193) and redirect blocking (`test_url_verify_ssrf_redirect` :204, `test_paste_rank_fetch_no_cross_host_redirect` :1092). **No private-IP/DNS test exists** — this is the S1 coverage gap to close.
- B1's multi-admin path is **entirely untested** today — that absence is what let the crash ship.

</code_context>

<specifics>
## Specific Ideas

- SSRF gate decision favors KISS explicitly because the attack surface is authenticated-only at a 2-person household — John (security-conscious IT infra manager) weighed the TOCTOU window as academic here and chose the simpler resolve-validate over IP pinning.
- The `FOR UPDATE` lock in B1 is kept deliberately after correcting the "single-worker makes it decorative" assumption — sync handlers in a threadpool still race at the DB level.

</specifics>

<deferred>
## Deferred Ideas

- **Admin "Sweep sessions now" button** — considered for consistency with the existing "Run AI refresh now" / "Run backup now" admin controls; deferred as scope creep (new endpoint + CSRF + UI) beyond the roadmap's job-only B2. Revisit only if a manual sweep is ever actually needed.
- **Full DNS-rebinding-safe IP pinning** for the SSRF fetchers — deferred in favor of resolve-validate (D-03). Revisit only if the threat model changes (e.g., the app ever exposes these fetchers to unauthenticated callers).

</deferred>

---

*Phase: 14-audit-remediation*
*Context gathered: 2026-05-25*
