---
phase: 14-audit-remediation
verified: 2026-05-25T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "B1 and B4 land on a feature branch (not direct-to-main)"
    reason: "John explicitly chose to execute Phase 14 directly on main. Branch policy exception approved by project owner."
    accepted_by: "John"
    accepted_at: "2026-05-25T00:00:00Z"
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 14: Audit Remediation Verification Report

**Phase Goal:** Fix the verified defects surfaced by a Codex audit (correctness + security hardening only; no schema/AI-scheduling/deployment/feature changes). Five scoped items.
**Verified:** 2026-05-25
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `_count_active_admins` uses locked subquery COUNT; all 4 call sites work; multi-admin regression tests pass; existing guard tests pass | VERIFIED | `with_for_update()` on inner `select(User.id)` subquery; 4 new `TestMultiAdminOperations` tests pass; 14/14 in `test_admin_users.py`; no `text("...FOR UPDATE...")` anywhere |
| 2 | SSRF gate resolves hosts and rejects private/loopback/link-local/ULA/CGNAT; public hosts allowed; gate applies to both fetchers | VERIFIED | `_assert_public_host` in `ai_service.py`; includes `not addr.is_global` (CGNAT fix); wired into both `_verify_buy_url` and `_fetch_page_text`; 9 SSRF tests pass including `test_ssrf_cgnat_blocked` |
| 3 | Nightly `nightly_session_sweep` APScheduler job deletes expired sessions; 3 jobs total; idempotent; tests prove expired deleted and unexpired retained | VERIFIED | `run_nightly_session_sweep` in `scheduler.py` at 03:00; `id="nightly_session_sweep"`, `replace_existing=True`; `test_idempotent_job_registration` asserts `len(jobs) == 3`; sweep tests pass |
| 4 | `/search` caps `q` at 100 chars (over-long → empty 200) and has a `SEARCH_LIMIT = "60/minute"` rate limit via a new constant | VERIFIED | `if len(q) > 100: return HTMLResponse("", ...)` before strip; `SEARCH_LIMIT: str = "60/minute"` in `rate_limit.py`; `@limiter.limit(SEARCH_LIMIT)` on `search_results`; both tests pass |
| 5 | Unreachable duplicate self-demote guard in `update_user` removed | VERIFIED | The original 3-line duplicate (comment + `if target.is_admin and not new_is_admin_raw and target_id == admin_user.id`) was deleted per commit `2ed5055`; two remaining "Cannot demote yourself." guards are both live (one in `update_user` D-16 branch, one in `toggle_admin` D-16 branch — different functions, not duplicates) |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/routers/admin/users.py` | Fixed `_count_active_admins` subquery COUNT + dead guard removal | VERIFIED | Contains `with_for_update()`, `select(func.count()).select_from(locked_subq)`, no `text(` at all; `text` import removed |
| `tests/phase_09/test_admin_users.py` | Multi-admin regression tests for all 4 call sites | VERIFIED | Contains `TestMultiAdminOperations` with 4 tests targeting `admin2_id` via `two_admins` fixture |
| `app/services/ai_service.py` | `_assert_public_host` SSRF gate reused by both fetchers | VERIFIED | `def _assert_public_host` present; `import socket`, `import ipaddress`, `from urllib.parse import urlparse` present; called 3 times (1 def + 2 calls) |
| `tests/services/test_ai_service.py` | SSRF private/loopback/link-local/mapped/public/dns/fetch tests | VERIFIED | 7 required SSRF tests + `test_ssrf_cgnat_blocked` (post-review addition); all pass |
| `app/services/scheduler.py` | `run_nightly_session_sweep` job + registration in `register_jobs` | VERIFIED | `def run_nightly_session_sweep`, `id="nightly_session_sweep"`, `CronTrigger(hour=3, minute=0)`, `expires_at < func.now()` all present |
| `tests/test_scheduler.py` | Sweep deletes-expired/retains-unexpired tests + updated idempotency (3 jobs) | VERIFIED | `test_session_sweep_deletes_expired`, `test_session_sweep_retains_unexpired`, `assert len(jobs) == 3` all present |
| `app/rate_limit.py` | `SEARCH_LIMIT` rate-limit constant | VERIFIED | `SEARCH_LIMIT: str = "60/minute"` at line 44 |
| `app/routers/search.py` | 100-char cap + `@limiter.limit(SEARCH_LIMIT)` decoration | VERIFIED | `if len(q) > 100:` before `len(q.strip()) < 2`; `@limiter.limit(SEARCH_LIMIT)` directly below `@router.get(...)` |
| `tests/test_search.py` | Over-long query empty-200 test + rate-limit test | VERIFIED | `test_long_query_returns_empty` and `test_search_rate_limit` both present and passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_count_active_admins` | users table (locked subquery) | `select(func.count()).select_from(locked_subq)` | WIRED | Verified by grep: `with_for_update()` on inner subquery; `select(func.count()).select_from(locked_subq)` returns the count; no `text()` SQL |
| `test_admin_users.py::TestMultiAdminOperations` | POST routes (demote/toggle/deactivate/delete) | `two_admins` fixture + client POST | WIRED | 4 tests target `admin2_id`; all assert DB state changed; 4/4 pass |
| `_verify_buy_url` | `_assert_public_host` | gate between scheme check and `client.get` | WIRED | Lines 184-186: `if not _assert_public_host(url): return False` |
| `_fetch_page_text` | `_assert_public_host` | gate between scheme check and `client.get` | WIRED | Lines 1542-1544: `if not _assert_public_host(url): return ""` |
| `_assert_public_host` | `socket.getaddrinfo` + `ipaddress` classification | resolve-validate | WIRED | Full chain: `urlparse` → `getaddrinfo` → `ip_address` → classification flags + `not is_global` |
| `register_jobs` | `run_nightly_session_sweep` | `target.add_job(..., id="nightly_session_sweep", replace_existing=True)` | WIRED | 3rd `add_job` call at `CronTrigger(hour=3, minute=0, timezone=settings.APP_TIMEZONE)` |
| `run_nightly_session_sweep` | `sessions` table DELETE | `sql_delete(SessionModel).where(SessionModel.expires_at < func.now())` | WIRED | Lazy-imported inside job body; uses `SessionLocal()` context manager |
| `search_results` | `SEARCH_LIMIT` in `rate_limit.py` | `from app.rate_limit import SEARCH_LIMIT, limiter` + `@limiter.limit(SEARCH_LIMIT)` | WIRED | Import verified; decorator order correct (route outermost, limiter below) |

---

### Data-Flow Trace (Level 4)

Not applicable for this phase. All phase 14 artifacts are guard logic, scheduler jobs, and security gates — none render dynamic data to a UI surface.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `_count_active_admins` no longer uses `text("...FOR UPDATE...")` | `grep -c "text(" app/routers/admin/users.py` | 0 | PASS |
| `_assert_public_host` wired into both fetchers | `grep -c "_assert_public_host" app/services/ai_service.py` | 3 (1 def + 2 calls) | PASS |
| `not addr.is_global` (CGNAT fix) present | `grep "not addr.is_global" app/services/ai_service.py` | line 257 | PASS |
| `nightly_session_sweep` registered at 03:00 | `grep "CronTrigger(hour=3" app/services/scheduler.py` | present | PASS |
| `SEARCH_LIMIT` in `rate_limit.py` | `grep "SEARCH_LIMIT" app/rate_limit.py` | `"60/minute"` at line 44 | PASS |
| len(q) > 100 cap before strip | `grep "len(q) > 100" app/routers/search.py` | line 44, before line 46 | PASS |
| 4-file phase test suite: 92 tests, 0 skips | `pytest tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py -q` | 92 passed, 0 skipped | PASS |

---

### Probe Execution

No probe scripts exist for this phase. Step 7c: N/A.

---

### Requirements Coverage

All 5 ROADMAP success criteria are audit-sourced with no formal REQ-IDs. Coverage assessed directly against the success criteria:

| Criterion | Plan | Description | Status | Evidence |
|-----------|------|-------------|--------|----------|
| #1 CRITICAL: last-admin guard no longer crashes | 14-01 | `_count_active_admins` subquery COUNT; all 4 call sites; multi-admin regression | SATISFIED | `with_for_update()` subquery; 4 `TestMultiAdminOperations` tests pass |
| #2 HIGH: SSRF gate blocks private/internal addresses | 14-02 | `_assert_public_host` in both fetchers; private/loopback/link-local/ULA blocked | SATISFIED (amended D-05) | `_assert_public_host` wired; `not is_global` covers CGNAT; 9 SSRF tests pass |
| #3 MEDIUM: expired sessions swept nightly | 14-03 | `nightly_session_sweep` job at 03:00; idempotent; 3 jobs total | SATISFIED | Job present; `len(jobs) == 3` asserted; sweep tests pass |
| #4 LOW: `/search` hardened | 14-04 | 100-char cap + `SEARCH_LIMIT` constant + rate-limit decorator | SATISFIED | All 3 elements present and tested |
| #5 LOW: dead duplicate self-demote guard removed | 14-01 | Unreachable duplicate in `update_user` deleted | SATISFIED | Commit `2ed5055`; original 3-line duplicate gone; two remaining guards are live (different functions) |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Anti-pattern scan on all modified files: no `TBD`, `FIXME`, `XXX`, `PLACEHOLDER`, `return null/[]/{}`, or empty handlers. No debt markers without formal issue references.

---

### Human Verification Required

None. All success criteria are verifiable programmatically. Tests ran against real Postgres in the container with 0 skips.

---

### Gaps Summary

No gaps. All 5 ROADMAP success criteria are satisfied by code in the repository. Tests pass 92/92 with 0 skips across the 4 phase-touched test files.

**Notes on accepted deviations (not gaps):**

1. **Branch policy (D-10):** The plans specified a feature branch; John overrode this and shipped directly on `main`. Accepted via override above.

2. **`demote yourself` appears twice (not once) in `users.py`:** The plan's Task 3 acceptance criterion said `grep -c "demote yourself"` returns 1. It returns 2. The SUMMARY correctly explains this: the `toggle_admin` handler has its own live D-16 self-demote guard that pre-dated the plan and is not a duplicate. The dead duplicate that was deleted was in `update_user`, and it was removed. Two occurrences = two live guards in two separate functions. This is correct behavior.

3. **DNS-rebinding (TOCTOU) not pinned (D-05):** Criterion #2 originally said "connects to the pinned resolved IP (DNS-rebinding safe)." The implemented gate resolves-and-validates but does not pin the resolved IP to the httpx connection. This was explicitly accepted per D-05 at household scale. Graded against the amended criterion (pre-resolve validation, accepted TOCTOU window).

4. **`test_ssrf_public_url_allowed` `-k` mismatch:** The VALIDATION doc's `-k "ssrf_public_allowed"` token doesn't substring-match `test_ssrf_public_url_allowed` (the `_url_` breaks it). The test is correctly named and passes under `-k "ssrf_public"`. Documentation inconsistency in the plan only; the test itself is correct.

**Post-review remediation confirmed (commit d4a6310):**
- CR-01 (CGNAT bypass): `not addr.is_global` added; `test_ssrf_cgnat_blocked` passes.
- CR-02 (vacuous DNS test): `test_url_verify_404` now patches `socket.getaddrinfo`.
- WR-01 (empty infos): `if not infos: return False` guard added.
- WR-03 (stale docstring): corrected to "3 jobs".

---

_Verified: 2026-05-25_
_Verifier: Claude (gsd-verifier)_
