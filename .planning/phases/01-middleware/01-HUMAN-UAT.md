---
status: partial
phase: 01-middleware
source: [01-VERIFICATION.md]
started: 2026-05-17T22:50:00Z
updated: 2026-05-17T22:50:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Real NGINX reverse-proxy end-to-end — curl https://snobbery.example.com/debug/proxy
expected: JSON body shows `scheme=https` and `headers_honored=true` after deploying the README NGINX server block
result: [pending]

### 2. Browser CSP nonce wiring — load app in Chrome DevTools, inspect network tab
expected: every `<script>` tag carries a `nonce=` attribute matching the CSP header nonce value on every page load; no CSP violations in console
result: [pending]

### 3. HTMX CSRF double-submit on second fragment swap (requires Phase 2 /login)
expected: Second HTMX POST after a fragment swap succeeds (not 403); demonstrates cookie is not rotated
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
