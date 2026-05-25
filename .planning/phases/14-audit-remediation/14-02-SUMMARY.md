---
phase: 14-audit-remediation
plan: "02"
subsystem: ai-service
tags: [security, ssrf, ai-service, tests]
dependency_graph:
  requires: []
  provides: [ssrf-gate-s1]
  affects: [ai_service, paste-and-rank]
tech_stack:
  added: []
  patterns: [resolve-validate-ssrf, ipv4-mapped-normalisation]
key_files:
  created: []
  modified:
    - app/services/ai_service.py
    - tests/services/test_ai_service.py
decisions:
  - "test_ssrf_public_url_allowed calls _assert_public_host directly with a mocked resolution (93.184.216.34) — avoids respx coupling and keeps the public-IP no-false-block assertion deterministic without a live DNS call"
  - "D-05 amended criterion accepted: pre-resolve validation only, sub-ms TOCTOU window accepted at household scale; documented in _assert_public_host docstring"
  - "Existing test_url_verify_verified and test_paste_rank_fetch_extracts_text required getaddrinfo mocks (Rule 1 fix) so the SSRF gate passes and HTTP-level assertions remain valid"
metrics:
  duration: "~15 min"
  completed: "2026-05-25"
  tasks: 2
  files: 2
---

# Phase 14 Plan 02: SSRF Resolve-Validate Gate (S1) Summary

One-liner: Pre-resolve SSRF gate using socket.getaddrinfo + ipaddress stdlib rejects private/loopback/link-local/reserved IPs (incl. IPv4-mapped ::ffff:169.254.169.254) in both _verify_buy_url and _fetch_page_text.

## What Was Built

Added a shared `_assert_public_host(url) -> bool` helper to `app/services/ai_service.py` and wired it into both URL-fetching functions before any httpx network call. The helper:

- Parses the hostname via `urlparse`
- Resolves via `socket.getaddrinfo` — DNS failure (OSError/gaierror) is treated as rejection
- Classifies every resolved IP with `ipaddress`
- Normalises IPv4-mapped IPv6 (`::ffff:10.x.x.x` → `10.x.x.x`) before classification — critical for bypass via mapped addresses
- Rejects if any address is `is_private`, `is_loopback`, `is_link_local`, or `is_reserved`
- Returns True only when every resolved address is public

Both fetchers already had scheme-allowlist and `follow_redirects=False` defenses; the new gate adds the IP-classification layer between the scheme check and the httpx call.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add _assert_public_host + wire both fetchers | 554a4c9 | app/services/ai_service.py |
| 2 | Author SSRF private-IP test suite | 4b3277e | tests/services/test_ai_service.py |

## Test Coverage

Seven new SSRF tests added (all pass, 0 skips):

| Test | What it covers |
|------|---------------|
| test_ssrf_private_ipv4_blocked | 10.0.0.1, 172.16.0.1, 192.168.0.1 rejected |
| test_ssrf_loopback_blocked | 127.0.0.1 and ::1 rejected |
| test_ssrf_link_local_blocked | 169.254.169.254 (cloud-metadata) rejected |
| test_ssrf_ipv4_mapped_ipv6_blocked | ::ffff:169.254.169.254 normalised then rejected |
| test_ssrf_public_url_allowed | 93.184.216.34 allowed (no false-block) |
| test_fetch_page_ssrf_private_blocked | Gate applies to _fetch_page_text too |
| test_ssrf_dns_failure_blocked | gaierror → rejection, no crash |

Total test count in test_ai_service.py: 52 passed, 0 failed, 0 skipped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing tests broke when getaddrinfo is called pre-httpx**

- **Found during:** Task 2 verification (full suite run)
- **Issue:** `test_url_verify_verified` and `test_paste_rank_fetch_extracts_text` used `respx.mock` to intercept the httpx call, but the new `_assert_public_host` gate calls `socket.getaddrinfo` before httpx — which either DNS-fails or resolves the test hostname in the container. Both caused the gate to reject, returning False/"" before httpx was reached.
- **Fix:** Added `patch("socket.getaddrinfo", return_value=[(AF_INET, ..., ("93.184.216.34", 443))])` to both tests so the gate passes and the tests exercise the HTTP-level behavior they were written to cover.
- **Files modified:** tests/services/test_ai_service.py
- **Commit:** 4b3277e (included in Task 2 commit)

**Note on test_ssrf_public_url_allowed k-filter mismatch:** The VALIDATION `-k "ssrf_public_allowed"` token does not substring-match `test_ssrf_public_url_allowed` (the `_url_` breaks the literal). The test is named per the plan's artifact spec and passes under `-k "ssrf_public"`. This is a documentation inconsistency in the plan, not a test defect.

## Threat Surface Scan

No new network endpoints or auth paths introduced. The helper is internal-only, adds no routes, and tightens an existing security boundary.

## Self-Check

- [x] app/services/ai_service.py modified (contains `def _assert_public_host`, `import socket`, `import ipaddress`, `from urllib.parse import urlparse`)
- [x] grep confirms 3 references to _assert_public_host (1 def + 2 calls)
- [x] tests/services/test_ai_service.py contains all 7 required test functions
- [x] 52 tests pass, 0 skips, 0 failures
- [x] ruff check and ruff format --check clean on both files
- [x] Commits 554a4c9 and 4b3277e exist in git log

## Self-Check: PASSED
