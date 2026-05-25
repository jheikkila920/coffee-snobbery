---
phase: 14
slug: audit-remediation
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-25
validated: 2026-05-25
---

# Phase 14 — Validation Strategy

> Per-phase validation contract. Authored pre-execution from `14-RESEARCH.md` § Validation
> Architecture; audited post-execution 2026-05-25 against the running container.
> Rows are keyed by audit Fix ID (B1/S1/B2/S4/B4).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (installed into container on demand — NOT baked into the production image) |
| **Config file** | repo-root pytest config (verify `pytest.ini` / `pyproject.toml`) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py -q` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Install (if missing)** | `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` |
| **Estimated runtime** | quick ~18s (92 tests) · full ~ minutes (baked tree; drop `snobbery_test` DB before a full run to avoid cross-module pollution) |
| **Sync note** | Image is baked (no source bind-mount). Sync changed files file-level before running: `docker compose cp <file> coffee-snobbery:/app/<file>` (dir-level cp nests). |

---

## Sampling Rate

- **After every task commit:** Run the **quick run command** (the 4 phase-touched test files).
- **After every plan wave:** Run the **full suite command**.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** ~18 seconds (quick run, 92 tests).

---

## Per-Task Verification Map

> Keyed by audit Fix ID. All commands below were re-run against the running container on
> 2026-05-25 and collect at least one test (no vacuous `-k` filters).

| Fix | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-----------------|-----------|-------------------|-------------|--------|
| B1 | `_count_active_admins` returns correct count without crashing | T-V4 | Last-admin guard evaluable (no `FOR UPDATE`-on-aggregate crash); locked subquery COUNT | integration | `pytest tests/phase_09/test_admin_users.py -k "other_admin" -x` | ✅ exercised | ✅ green |
| B1 | Admin A demotes admin B with 2+ admins present → succeeds | T-V4 | Demote-other allowed; demote-to-zero still blocked | integration | `pytest tests/phase_09/test_admin_users.py -k "demote_other_admin" -x` | ✅ created | ✅ green |
| B1 | Admin A deactivates admin B with 2+ admins → succeeds | T-V4 | Deactivate-other allowed | integration | `pytest tests/phase_09/test_admin_users.py -k "deactivate_other_admin" -x` | ✅ created | ✅ green |
| B1 | Admin A deletes admin B with 2+ admins → succeeds | T-V4 | Delete-other allowed | integration | `pytest tests/phase_09/test_admin_users.py -k "delete_other_admin" -x` | ✅ created | ✅ green |
| B1 | Existing last-admin guard tests still pass | T-V4 | Demote-to-zero / single-admin still refused | integration | `pytest tests/phase_09/test_admin_users.py -k "last_admin or single_admin" -x` | ✅ exists | ✅ green |
| S1 | Private IPv4 rejected (10.x, 172.16.x, 192.168.x) | T-SSRF-priv | `is_private` host refused pre-connect | unit | `pytest tests/services/test_ai_service.py -k "ssrf_private" -x` | ✅ created | ✅ green |
| S1 | Loopback rejected (127.0.0.1, ::1, localhost) | T-SSRF-lo | `is_loopback` host refused | unit | `pytest tests/services/test_ai_service.py -k "ssrf_loopback" -x` | ✅ created | ✅ green |
| S1 | Link-local / metadata rejected (169.254.169.254) | T-SSRF-meta | `is_link_local` host refused | unit | `pytest tests/services/test_ai_service.py -k "ssrf_link_local" -x` | ✅ created | ✅ green |
| S1 | IPv4-mapped IPv6 rejected (::ffff:169.254.169.254) | T-SSRF-mapped | `ipv4_mapped` normalized before check | unit | `pytest tests/services/test_ai_service.py -k "ssrf_ipv4_mapped" -x` | ✅ created | ✅ green |
| S1 | CGNAT shared space rejected (100.64.0.0/10, RFC 6598) | T-SSRF-cgnat | Non-globally-routable IP refused (CR-01) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_cgnat" -x` | ✅ created (post-review) | ✅ green |
| S1 | Public URL still passes validation | T-SSRF-pub | Public host allowed (no false-block) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_public" -x` | ✅ created | ✅ green |
| S1 | `_fetch_page_text` also rejects private hosts | T-SSRF-fetch | Same gate on paste-and-rank fetcher | unit | `pytest tests/services/test_ai_service.py -k "fetch_page_ssrf" -x` | ✅ created | ✅ green |
| S1 | DNS failure (`OSError`/empty result) treated as rejection | T-SSRF-dns | Unresolvable host refused, not crashed; non-vacuous (CR-02/WR-01) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_dns_failure" -x` | ✅ created | ✅ green |
| S1 | Existing scheme + redirect tests still pass | T-SSRF-base | non-https + redirect still blocked | unit | `pytest tests/services/test_ai_service.py -k "ssrf_redirect or scheme_rejected" -x` | ✅ exists | ✅ green |
| B2 | Expired sessions deleted by sweep job | T-V3 | `expires_at < now()` rows removed | unit | `pytest tests/test_scheduler.py -k "session_sweep_deletes" -x` | ✅ created | ✅ green |
| B2 | Unexpired sessions retained by sweep | T-V3 | Live sessions survive sweep | unit | `pytest tests/test_scheduler.py -k "session_sweep_retains" -x` | ✅ created | ✅ green |
| B2 | 3 jobs registered (idempotency assertion updated) | — | `nightly_session_sweep` present; `replace_existing` idempotent | unit | `pytest tests/test_scheduler.py::test_idempotent_job_registration -x` | ✅ updated | ✅ green |
| S4 | `q` > 100 chars (pre-strip) returns empty 200 | T-V5 | Over-long input short-circuits | unit | `pytest tests/test_search.py -k "long_query or q_length" -x` | ✅ created | ✅ green |
| S4 | Rate limit enforced (`60/minute` per IP) | T-V10-rl | `@limiter.limit(SEARCH_LIMIT)` applied; 61 seq requests → 429 | integration | `pytest tests/test_search.py -k "rate_limit" -x` | ✅ created (automated) | ✅ green |
| B4 | Dead duplicate self-demote guard removed | — | One dead duplicate removed; two LIVE guards remain (`update_user` + `toggle_admin`) | static | `grep -c "demote yourself" app/routers/admin/users.py` → expected **2** | n/a | ✅ verified |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Audit run 2026-05-25:** full quick suite = **92 passed, 0 skipped, 0 failed** (~18s). Every `-k` filter above collects ≥1 test.

---

## Wave 0 Requirements (all satisfied)

- [x] `tests/phase_09/test_admin_users.py` — multi-admin operations (uses existing `two_admins` fixture):
  - `test_demote_other_admin_succeeds`, `test_deactivate_other_admin_succeeds`, `test_delete_other_admin_succeeds` ✅
- [x] `tests/services/test_ai_service.py` — SSRF private-IP suite (mock `socket.getaddrinfo`):
  - `test_ssrf_private_ipv4_blocked`, `test_ssrf_loopback_blocked`, `test_ssrf_link_local_blocked`,
    `test_ssrf_ipv4_mapped_ipv6_blocked`, `test_ssrf_cgnat_blocked` (post-review), `test_ssrf_public_url_allowed`,
    `test_fetch_page_ssrf_private_blocked`, `test_ssrf_dns_failure_blocked` ✅
- [x] `tests/test_scheduler.py` — session sweep:
  - `test_session_sweep_deletes_expired`, `test_session_sweep_retains_unexpired` ✅
  - `test_idempotent_job_registration` updated: `len(jobs) == 3`, expected set includes `nightly_session_sweep` ✅
- [x] `tests/test_search.py` — search hardening:
  - `test_long_query_returns_empty` (101-char `q` → 200, empty) ✅
  - `test_search_rate_limit` (shipped automated; deterministic via `_reset_rate_limiter` autouse fixture at `tests/conftest.py:187`) ✅

---

## Manual-Only Verifications

> None. The `/search` rate-limit behavior originally flagged as a manual-verify fallback (slowapi
> in-memory buckets under TestClient) shipped as a reliable automated test
> (`test_search_rate_limit`): the autouse `_reset_rate_limiter` fixture clears the in-memory bucket
> before each test, so 61 sequential requests deterministically hit the `60/minute` cap. No manual
> verification is required for this phase.

---

## Validation Sign-Off

- [x] All Fix rows have an `<automated>` verify command (B4 is a static grep check)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all formerly-MISSING references
- [x] No watch-mode flags in any command
- [x] Feedback latency < 20s (quick run ~18s)
- [x] Every `-k` filter collects ≥1 test (no vacuous filters)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-25 — all 19 behaviors COVERED by green automated tests.

---

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Coverage gaps found (MISSING/PARTIAL) | 0 |
| Tests authored to fill gaps | 0 |
| Escalated to manual-only | 0 |
| Doc defects corrected in this VALIDATION.md | 4 |

**Coverage:** zero gaps. All test files authored during execution (Plans 14-01..04) plus the
post-review hardening (`d4a6310`) exist and pass. No `gsd-nyquist-auditor` spawn was required.

**Doc corrections made during audit** (commands fixed in place; underlying tests already passed):

1. B1 "count without crashing" — `-k "admin_count or active_admins"` collected 0 tests → changed to
   `-k "other_admin"` (the path that actually exercises the fixed `_count_active_admins`).
2. S1 "public URL passes" — `-k "ssrf_public_allowed"` collected 0 (the `_url_` infix breaks the
   literal) → changed to `-k "ssrf_public"`.
3. B4 static check — expected count was `1`; actual is `2` (the dead duplicate WAS removed, but
   `toggle_admin` retains its own live `"Cannot demote yourself."` guard). Corrected to `2`.
4. Added the S1 CGNAT row (`test_ssrf_cgnat_blocked`) from the post-review fix `d4a6310` and updated
   the DNS-failure row note to reflect the non-vacuous CR-02/WR-01 fix.
