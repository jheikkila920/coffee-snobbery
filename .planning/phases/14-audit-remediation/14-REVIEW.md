---
phase: 14-audit-remediation
reviewed: 2026-05-25T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - app/rate_limit.py
  - app/routers/admin/users.py
  - app/routers/search.py
  - app/services/ai_service.py
  - app/services/scheduler.py
  - tests/phase_09/test_admin_users.py
  - tests/services/test_ai_service.py
  - tests/test_scheduler.py
  - tests/test_search.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-05-25
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 14 remediated B1 (last-admin guard), S1 (SSRF DNS gate), B2 (nightly session sweep), and S4 (search length cap + rate limit). The implementations are largely correct and the test suites are comprehensive. Two security findings require attention: a real SSRF bypass via CGNAT addresses that the DNS gate does not block, and a test that makes live DNS lookups without mocking, meaning it vacuously passes on DNS failure rather than exercising the intended 404 code path. Three warnings cover a logic ordering issue in `update_user`, an empty-infos edge case, and a stale test docstring.

---

## Critical Issues

### CR-01: SSRF Gate Does Not Block CGNAT Space (100.64.0.0/10)

**File:** `app/services/ai_service.py:245`

**Issue:** `_assert_public_host` classifies addresses using `is_private or is_loopback or is_link_local or is_reserved`. Python's `ipaddress` module does not classify CGNAT space (`100.64.0.0/10`, RFC 6598) as any of those four attributes — `is_global` returns `False` for it, but none of the four checked properties return `True`. A DNS entry that resolves to a CGNAT address (`100.64.x.x`) passes the gate and proceeds to the `httpx` request.

Verified on the running container:
```
100.64.0.1: is_private=False, is_loopback=False, is_link_local=False, is_reserved=False
```

CGNAT is an internal carrier address range. While it is unlikely to appear in legitimate roaster DNS, an adversarially controlled DNS record or a compromised upstream resolver could return a CGNAT address to reach internal services on a host that shares its carrier NAT space. The fix is to add `not addr.is_global` as a gate (which correctly blocks CGNAT while allowing all globally routable addresses), or to add the explicit CGNAT network check.

**Fix:**
```python
# In _assert_public_host, replace:
if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
    return False

# With — adds CGNAT and any other non-global range not covered by the four flags:
if (
    addr.is_private
    or addr.is_loopback
    or addr.is_link_local
    or addr.is_reserved
    or not addr.is_global
):
    return False
```

Note: `not addr.is_global` alone is slightly broader (it also blocks `224.0.0.0/4` multicast), but multicast DNS records don't exist in practice and the extra safety is appropriate here. Alternatively, keep the four-flag form and append one network check:
```python
_CGNAT = ipaddress.IPv4Network("100.64.0.0/10")

if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
    return False
if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT:
    return False
```

---

### CR-02: `test_url_verify_404` Makes a Live DNS Call — Test Passes Vacuously on DNS Failure

**File:** `tests/services/test_ai_service.py:189-195`

**Issue:** `test_url_verify_404` uses `@respx.mock` to intercept the HTTP call but does NOT mock `socket.getaddrinfo`. The `_verify_buy_url` function calls `_assert_public_host` — which calls `socket.getaddrinfo("example-roaster.com", None)` — *before* making the mocked HTTP request. If DNS resolution fails (NXDOMAIN, timeout, or network isolation in CI), `_assert_public_host` returns `False` and `_verify_buy_url` returns `False` immediately, never reaching the `httpx` path. The test assertion `assert result is False` passes — but for the wrong reason (DNS failure, not 404 handling). The 404 code path is never exercised.

Every other test in this file that exercises `_verify_buy_url` or `_fetch_page_text` correctly patches `socket.getaddrinfo`. This one test was overlooked.

**Fix:**
```python
@respx.mock
@pytest.mark.asyncio
async def test_url_verify_404() -> None:
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    url = "https://example-roaster.com/not-found"
    respx.get(url).mock(return_value=httpx.Response(404, text="Not found"))
    mock_public = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=mock_public):
        result = await _verify_buy_url(url, "Counter Culture", "Yirgacheffe")
    assert result is False
```

---

## Warnings

### WR-01: `_assert_public_host` Returns `True` When `getaddrinfo` Returns Empty List

**File:** `app/services/ai_service.py:236-247`

**Issue:** If `socket.getaddrinfo` succeeds but returns an empty list (extremely rare, but the POSIX spec does not guarantee a non-empty result when no error is raised), the `for` loop does not execute and the function returns `True` — allowing the URL through without any address validation. The `OSError` catch handles DNS failures, but a successful zero-result response is not handled.

In practice CPython's implementation always returns at least one record or raises `socket.gaierror`, but relying on undocumented behavior for a security gate is incorrect.

**Fix:**
```python
infos = socket.getaddrinfo(host, None)
if not infos:
    return False  # No addresses resolved — treat as rejection

for _family, _type, _proto, _canon, sockaddr in infos:
    ...
```

---

### WR-02: `update_user` D-16 Self-Demotion Check Runs After the DB Lock Is Acquired

**File:** `app/routers/admin/users.py:299-305`

**Issue:** In `update_user`, the D-16 guard sequence is:
1. Acquire `FOR UPDATE` lock via `_count_active_admins` (DB round-trip)
2. Check `admin_count <= 1`
3. Check `target_id == admin_user.id` (self-demotion)

The self-demotion check on line 304 is a pure in-process comparison that requires no DB state. It runs *after* the locking query. With 2 admins present, an admin who submits a self-demotion request will pass the count check (count=2 > 1), acquire the row lock, and then be rejected. This is functionally correct — the guard fires — but the lock is held unnecessarily for the self-demotion case.

More importantly, the `toggle_admin` handler (line 369-374) checks self-demotion *after* the count check in the same order. In `deactivate_user` (line 416-423), the order is reversed: self-demotion is checked *before* acquiring the lock (the better order). The inconsistency across three handlers is a quality concern. If the business rule ever changes such that "last admin" and "self" are conflated, the inconsistency could produce different behaviour per handler.

**Fix:** Move the self-demotion check before the `_count_active_admins` call in `update_user` and `toggle_admin` to match `deactivate_user`:
```python
# D-16 guard if is_admin is being demoted
if target.is_admin and not new_is_admin_raw:
    if target_id == admin_user.id:                      # fast path — no DB needed
        return _render_error_fragment(request, "Cannot demote yourself.", 409)
    admin_count = _count_active_admins(db)
    if admin_count <= 1:
        return _render_error_fragment(request, "Cannot demote the last active admin.", 409)
```

---

### WR-03: Stale Docstring in `test_idempotent_job_registration`

**File:** `tests/test_scheduler.py:25`

**Issue:** The test docstring says "Exactly 2 jobs registered after N register_jobs() calls" but the scheduler registers 3 jobs (`nightly_ai_refresh`, `nightly_backup`, `nightly_session_sweep`). The assertion on line 50 correctly checks `len(jobs) == 3`. The docstring was left at the Phase 8 value (when the session sweep job did not exist) and was not updated when B2 added `nightly_session_sweep` in Phase 14.

While this is a documentation issue, a developer reading the docstring and not the assertion might add a future job and be confused about the expected count.

**Fix:**
```python
"""Exactly 3 jobs registered after N register_jobs() calls — no duplicates.
```

---

## Info

### IN-01: `_split_inputs` Silently Accepts `http://` URLs Into the URL List

**File:** `app/services/ai_service.py:1492-1508`

**Issue:** `_split_inputs` categorises both `http://` and `https://` lines as URLs and adds them to the returned `urls` list. The downstream `_fetch_page_text` correctly rejects `http://` before making a network call. However, `_split_inputs` docstring says "Lines that start with 'http://' or 'https://' are detected as URLs" — implying they will be fetched. A plain-HTTP line passed by a user will silently produce no page text (empty string), with no indication to the caller that the URL was skipped for security reasons. The test in `test_ai_service.py:1207` only verifies that `http://` is rejected at the `_fetch_page_text` level.

This is not an exploitable vulnerability (the scheme check blocks the actual request), but the interface contract between `_split_inputs` and `_fetch_page_text` is leaky.

**Fix (optional):** Filter `http://` lines in `_split_inputs` before adding to `urls`:
```python
if stripped.startswith("https://"):
    urls.append(stripped)
elif stripped.startswith("http://"):
    pass  # HTTP not fetched; treat as freeform text or silently skip
else:
    texts.append(stripped)
```

---

### IN-02: `test_ai_run_summary_tally` Does Not Exercise the Actual Scheduler Code Path

**File:** `tests/test_scheduler.py:164-210`

**Issue:** `test_ai_run_summary_tally` tests the tally logic by re-implementing it inline inside the test body (lines 191-206) rather than calling `run_nightly_ai_refresh` with a mocked regenerate. The `mock_regenerate` fixture verifies that the callable is awaitable and respects `force=False`, but the actual `summary["regenerations"] += 1` / `summary["skips"] += 1` accounting inside `run_nightly_ai_refresh` is never called. A regression in the scheduler's tally path (e.g. wrong status string comparison) would not be caught by this test.

**Fix:** Consider refactoring the test to call `run_nightly_ai_refresh` with the `mock_regenerate` patched in, then assert on the written summary from `app_settings` rather than a manually computed dict.

---

_Reviewed: 2026-05-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
