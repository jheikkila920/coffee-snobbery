# Milestones

## v1.1 Initial Release (Shipped: 2026-05-25)

**Phases completed:** 15 phases (0–14), 93 plans, 103 tasks
**Git range:** `5c6f07e` → `30d25de` · 576 commits · 670 files, +146,282 lines
**Codebase:** ~20,900 LOC Python (app/) + 84 templates + 8 migrations · ~25,800 LOC tests
**Timeline:** 9 days (2026-05-16 → 2026-05-25)

**Delivered:** The complete self-hosted household coffee log — shared catalog, per-user
brew logging, AI-driven "what to buy next" recommendations, admin, search, and an
installable PWA — deployed behind NGINX and pushed to `origin/main`.

**Key accomplishments:**

- **Hardened two-container stack** — Postgres 16 + FastAPI with auto-migrations, single-worker uvicorn behind NGINX, nonce-based CSP + full security-header set + double-submit CSRF + table-backed sessions + structured JSON logging (Phases 0–1).
- **Auth + encryption substrate** — race-protected first-admin `/setup` (`SELECT FOR UPDATE`), argon2id login with session regeneration, and MultiFernet-encrypted API keys at rest from the first migration (Phases 2–3).
- **Shared catalog + per-user brew logging** — coffees/roasters/flavor-notes/equipment/recipes CRUD, hardened photo pipeline (magic-byte → Pillow re-encode → EXIF strip → thumbnail), sub-30s prefill brew form with tap-stars rating and CSV import/export (Phases 4–5).
- **Analytics home + AI differentiator** — pure-SQL preference derivations with HTMX lazy-load, plus a provider-agnostic AI service running a three-tier web-search coffee recommendation with verified buy URLs, SSRF-hardened fetchers, and signature-based nightly regeneration for cost control (Phases 6–7).
- **Admin, scheduler & search** — user/credential/settings admin with API-health panel, APScheduler nightly AI refresh + `pg_dump`/photo backups with retention, and Postgres trigram global search with per-user note scoping (Phases 8–10).
- **PWA/mobile polish + ship gate** — installable PWA with service worker, bottom/top nav, dark mode, Guided Brew Mode; ~25.8k LOC test suite + Playwright responsive smoke + CI; followed by post-launch PWA UX fixes (Phase 13) and a Codex audit-remediation pass (Phase 14: last-admin crash, SSRF gate, session sweep, search hardening) (Phases 11–14).

**Known deferred items at close:** Closed with acknowledged debt — open human UAT
(Phases 01/02/07/11) and `human_needed` verifications (Phases 01/02/07/09/10/11), the
Phase 14 375px search UAT, possible Phase 11 nav/sign-out gap (verify), plus the
pre-existing G-01 VPS volume-chown and T-INFRA-1 test-isolation items. See STATE.md
"Deferred Items".
