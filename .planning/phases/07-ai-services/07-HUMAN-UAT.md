---
status: partial
phase: 07-ai-services
source: [07-VERIFICATION.md]
started: 2026-05-21T00:00:00Z
updated: 2026-05-21T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Hero card end-to-end with a live provider key
expected: With an enabled Anthropic or OpenAI credential (configured in /admin) and a gate-open user (>=3 brew sessions and >=5 distinct flavor notes), the home page hero card lazy-loads and shows a single confident pick (coffee name, roaster, why-prose), a buy link in one of three states (verified / verifying / couldn't verify), an add-to-wishlist button, and a manual-refresh button. The stale badge appears after logging a new rated session (signature drift). Sweet-spots prose renders alongside, generated in the same call.
result: [pending]

### 2. 375px layout — hero "generated" and "try-again" states
expected: The hero card's generated state and the try-again state render without horizontal scroll at 375px. (Cold-start, not-configured, and in-flight states plus the paste-rank and wishlist pages were already approved at 375px in the 07-06 and 07-07 checkpoints; these two remaining states need a live provider response to reach.)
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
