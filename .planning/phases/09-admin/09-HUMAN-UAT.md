---
status: partial
phase: 09-admin
source: [09-VERIFICATION.md]
started: 2026-05-21T00:00:00Z
updated: 2026-05-21T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. User management lifecycle at 375px (ADMIN-01 / SC-1)
expected: At /admin/users on a 375px viewport — create a user, reset password, toggle is_admin, deactivate, reactivate, and delete an empty user. All actions succeed; no horizontal scroll; forms readable; inline errors display below fields; action buttons have >=44px tap targets.
result: [pending]

### 2. Credential masking + test-connection (ADMIN-02 / SC-2)
expected: At /admin/credentials — set an Anthropic (or OpenAI) key; after save only the last 4 chars show (full key never in page source); "Test connection" renders ok / invalid_key / network; the enable/disable toggle persists independently of the key save.
result: [pending]

### 3. Settings editor type-driven inputs + read-only guard (ADMIN-03 / SC-3)
expected: At /admin/settings — edit min_sessions_for_ai and save (shows "Saved", new value persists); description shows as helper text; input control matches value_type (number/checkbox/text); attempting to save setup_completed (read-only) is rejected with 403 and no mutation.
result: [pending]

### 4. Backups list / download / run-now / traversal (ADMIN-04 / SC-4)
expected: At /admin/backups — "Run backup now" produces a result card; the produced file downloads with correct content-type; a manual traversal attempt (e.g. /admin/backups/../../etc/passwd) returns 404. (Local note: backups dir must be writable; on the VPS this needs the deferred G-01 chown.)
result: [pending]

### 5. System info + API health panel (ADMIN-05 / ADMIN-06 / SC-5)
expected: At /admin/system — app version, DB version, photo + backup storage, active session count, and last backup status+timestamp all present; API health panel renders the last AI run summary, per-provider last success/error + last 5 errors, and per-recommendation-type last run; no SettingNotFoundError after a backup or AI run.
result: [pending]

### 6. Manual AI refresh respect/force modes (ADMIN-05 / D-13/D-14)
expected: "Run AI refresh now" writes ai_recommendations rows tagged generated_by="admin" (respect signature/eligibility) and the force path tagged generated_by="admin_force"; only eligible users (>=3 sessions) are refreshed in respect mode; the force action is labeled as expensive in the UI. (Requires real AI credentials + an eligible user; verify telemetry via DB query.)
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
