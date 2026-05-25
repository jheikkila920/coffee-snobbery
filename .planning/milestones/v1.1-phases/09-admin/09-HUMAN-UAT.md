---
status: partial
phase: 09-admin
source: [09-VERIFICATION.md]
started: 2026-05-21T00:00:00Z
updated: 2026-05-22T00:00:00Z
---

## Current Test

[complete — John approved 2026-05-22 after item-4 fixes + redesign re-test ("All good now")]

## Tests

### 1. User management lifecycle at 375px (ADMIN-01 / SC-1)
expected: full CRUD lifecycle at 375px, no horizontal scroll, 44px tap targets.
result: passed (John, 2026-05-21)

### 2. Credential masking + test-connection (ADMIN-02 / SC-2)
expected: only last-4 shows after save; test-connection renders status; toggle persists.
result: passed (John, 2026-05-21)

### 3. Settings editor type-driven inputs + read-only guard (ADMIN-03 / SC-3)
expected: editable rows save; read-only keys rejected (403); type-appropriate inputs.
result: passed (John, 2026-05-21)

### 4. Backups list / download / run-now / traversal (ADMIN-04 / SC-4)
expected: run-now produces a file; download works; traversal returns 404; timestamps in local timezone; "Run backup now" spinner clears after completion.
result: passed (John, 2026-05-22 — re-tested after fixes). run-now bugs FIXED in gap closure:
  - "Stuck on Running": root cause was strict nonce-CSP blocking htmx's auto-injected `.htmx-indicator` style. Fixed by adding `.htmx-indicator` rules to app/static/css/tailwind.src.css (commit 71bbce1). Spinner now hides at rest and clears after the request.
  - Timezone: backup filename date + all admin timestamps now use APP_TIMEZONE (America/Chicago) instead of UTC, via the new `localdt` Jinja filter + local-tz `date.today()` (commit f566b1a). An evening run now dates the file to the local day (e.g. db_2026-05-21.sql), not tomorrow's UTC date.
  - Same-name overwrite is by design (one file per day, 14-day retention); the timezone fix aligns "today" with the local day.

### 5. System info + API health panel (ADMIN-05 / ADMIN-06 / SC-5)
expected: all system info fields + per-provider/per-type health render.
result: passed (John, 2026-05-21). Timestamps now render in local timezone (gap-closure).

### 6. Manual AI refresh respect/force modes (ADMIN-05 / D-13/D-14)
expected: generated_by="admin" vs "admin_force"; eligibility respected; force labeled expensive.
result: passed pending real data (John, 2026-05-21 — "seems good"; full confirmation needs real AI creds + an eligible user on the VPS).

### 7. Admin landing redesign (post-UAT enhancement, John-requested)
expected: GET /admin renders the System page (hub card grid removed); "System" is the far-left item in the admin section nav and links to /admin; GET /admin/system 301-redirects to /admin; credential test-connection + AI refresh actions still work.
result: passed (John, 2026-05-22 — re-tested in browser). implemented (commit 0ddc49e); routes + redirect verified, 630-test suite green.

## Summary

total: 7
passed: 6
issues: 0
pending: 1
skipped: 0
blocked: 0
notes: items 1-5, 7 confirmed by John; item 6 (AI refresh respect/force) verified in code + "seems good", full confirmation pending real AI data on the VPS (deploy-time check, non-blocking)

## Gaps

- Item 4 backup defects (stuck-spinner under CSP + UTC timezone) were found in UAT and FIXED in gap closure (commits f566b1a, 71bbce1). Awaiting browser re-test.
