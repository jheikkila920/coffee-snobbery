---
phase: 14
slug: audit-remediation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `14-RESEARCH.md` § Validation Architecture. Task IDs are assigned during planning;
> rows below are keyed by audit Fix ID (B1/S1/B2/S4/B4) until plans map them to concrete task IDs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (installed into container on demand — NOT baked into the production image) |
| **Config file** | repo-root pytest config (verify `pytest.ini` / `pyproject.toml`) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py -q` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Install (if missing)** | `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx` |
| **Estimated runtime** | quick ~10-20s · full ~ minutes (baked tree; drop `snobbery_test` DB before a full run to avoid cross-module pollution) |

---

## Sampling Rate

- **After every task commit:** Run the **quick run command** (the 4 phase-touched test files).
- **After every plan wave:** Run the **full suite command**.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** ~20 seconds (quick run).

---

## Per-Task Verification Map

> Keyed by audit Fix ID. The planner maps each row to a concrete Task ID during planning.
> All ❌ rows are Wave 0 gaps (test must be authored as part of this phase).

| Fix | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-----------------|-----------|-------------------|-------------|--------|
| B1 | `_count_active_admins` returns correct count without crashing | T-V4 | Last-admin guard evaluable (no `FOR UPDATE`-on-aggregate crash) | unit | `pytest tests/phase_09/test_admin_users.py -k "admin_count or active_admins" -x` | ⚠️ partial | ⬜ pending |
| B1 | Admin A demotes admin B with 2+ admins present → succeeds | T-V4 | Demote-other allowed; demote-to-zero still blocked | integration | `pytest tests/phase_09/test_admin_users.py -k "demote_other_admin" -x` | ❌ W0 | ⬜ pending |
| B1 | Admin A deactivates admin B with 2+ admins → succeeds | T-V4 | Deactivate-other allowed | integration | `pytest tests/phase_09/test_admin_users.py -k "deactivate_other_admin" -x` | ❌ W0 | ⬜ pending |
| B1 | Admin A deletes admin B with 2+ admins → succeeds | T-V4 | Delete-other allowed | integration | `pytest tests/phase_09/test_admin_users.py -k "delete_other_admin" -x` | ❌ W0 | ⬜ pending |
| B1 | Existing last-admin guard tests still pass | T-V4 | Demote-to-zero / single-admin still refused | integration | `pytest tests/phase_09/test_admin_users.py -k "last_admin or single_admin" -x` | ✅ exists | ⬜ pending |
| S1 | Private IPv4 rejected (10.x, 172.16.x, 192.168.x) | T-SSRF-priv | `is_private` host refused pre-connect | unit | `pytest tests/services/test_ai_service.py -k "ssrf_private" -x` | ❌ W0 | ⬜ pending |
| S1 | Loopback rejected (127.0.0.1, ::1, localhost) | T-SSRF-lo | `is_loopback` host refused | unit | `pytest tests/services/test_ai_service.py -k "ssrf_loopback or ssrf_localhost" -x` | ❌ W0 | ⬜ pending |
| S1 | Link-local / metadata rejected (169.254.169.254) | T-SSRF-meta | `is_link_local` host refused | unit | `pytest tests/services/test_ai_service.py -k "ssrf_link_local or ssrf_metadata" -x` | ❌ W0 | ⬜ pending |
| S1 | IPv4-mapped IPv6 rejected (::ffff:169.254.169.254) | T-SSRF-mapped | `ipv4_mapped` normalized before check | unit | `pytest tests/services/test_ai_service.py -k "ssrf_ipv4_mapped" -x` | ❌ W0 | ⬜ pending |
| S1 | Public URL still passes validation | T-SSRF-pub | Public host allowed (no false-block) | unit | `pytest tests/services/test_ai_service.py -k "ssrf_public_allowed" -x` | ❌ W0 | ⬜ pending |
| S1 | `_fetch_page_text` also rejects private hosts | T-SSRF-fetch | Same gate on paste-and-rank fetcher | unit | `pytest tests/services/test_ai_service.py -k "fetch_page_ssrf" -x` | ❌ W0 | ⬜ pending |
| S1 | DNS failure (`OSError`) treated as rejection | T-SSRF-dns | Unresolvable host refused, not crashed | unit | `pytest tests/services/test_ai_service.py -k "ssrf_dns_fail" -x` | ❌ W0 | ⬜ pending |
| S1 | Existing scheme + redirect tests still pass | T-SSRF-base | non-https + redirect still blocked | unit | `pytest tests/services/test_ai_service.py -k "ssrf_redirect or scheme_rejected" -x` | ✅ exists | ⬜ pending |
| B2 | Expired sessions deleted by sweep job | T-V3 | `expires_at < now()` rows removed | unit | `pytest tests/test_scheduler.py -k "session_sweep" -x` | ❌ W0 | ⬜ pending |
| B2 | Unexpired sessions retained by sweep | T-V3 | Live sessions survive sweep | unit | `pytest tests/test_scheduler.py -k "session_sweep" -x` | ❌ W0 | ⬜ pending |
| B2 | 3 jobs registered (idempotency assertion updated) | — | `nightly_session_sweep` present; `replace_existing` idempotent | unit | `pytest tests/test_scheduler.py::test_idempotent_job_registration -x` | ✅ needs update | ⬜ pending |
| S4 | `q` > 100 chars (pre-strip) returns empty 200 | T-V5 | Over-long input short-circuits | unit | `pytest tests/test_search.py -k "long_query or q_length" -x` | ❌ W0 | ⬜ pending |
| S4 | Rate limit enforced (`60/minute` per IP) | T-V10-rl | `@limiter.limit(SEARCH_LIMIT)` applied | integration | `pytest tests/test_search.py -k "rate_limit" -x` | ❌ W0 (see Manual-Only) | ⬜ pending |
| B4 | Dead duplicate self-demote guard removed | — | Single "cannot demote yourself" guard remains | static | `grep -n "demote yourself" app/routers/admin/users.py \| wc -l` → expected 1 | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/phase_09/test_admin_users.py` — multi-admin operations (uses existing `two_admins` fixture at `tests/phase_09/conftest.py:170-198`):
  - `test_demote_other_admin_succeeds`, `test_deactivate_other_admin_succeeds`, `test_delete_other_admin_succeeds`
- [ ] `tests/services/test_ai_service.py` — SSRF private-IP suite (mock `socket.getaddrinfo`):
  - `test_ssrf_private_ipv4_blocked`, `test_ssrf_loopback_blocked`, `test_ssrf_link_local_blocked`,
    `test_ssrf_ipv4_mapped_ipv6_blocked`, `test_ssrf_public_url_allowed`, `test_fetch_page_ssrf_private_blocked`,
    `test_ssrf_dns_failure_blocked`
- [ ] `tests/test_scheduler.py` — session sweep:
  - `test_session_sweep_deletes_expired`, `test_session_sweep_retains_unexpired`
  - Update `test_idempotent_job_registration`: `len(jobs) == 2` → `== 3`, add `"nightly_session_sweep"` to expected set
- [ ] `tests/test_search.py` — search hardening:
  - `test_long_query_returns_empty` (101-char `q` → 200, empty)
  - `test_search_rate_limit` (see Manual-Only — slowapi in-process buckets are awkward under TestClient)

---

## Manual-Only Verifications

| Behavior | Fix | Why Manual | Test Instructions |
|----------|-----|------------|-------------------|
| `/search` rate-limit returns 429 after burst | S4 | slowapi uses in-memory buckets that can reset between TestClient requests; reliable assertion in-process is brittle | If the in-process `test_search_rate_limit` proves flaky, verify manually: hit `/search?q=ab` >60×/min from one IP and confirm a `429`. Otherwise keep it automated. |

---

## Validation Sign-Off

- [ ] All Fix rows have an `<automated>` verify command or a Wave 0 test dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ MISSING references
- [ ] No watch-mode flags in any command
- [ ] Feedback latency < 20s (quick run)
- [ ] `nyquist_compliant: true` set in frontmatter (set after planner wires every task to a verify)

**Approval:** pending
