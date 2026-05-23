---
phase: 11
slug: pwa-mobile-polish
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-23
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at PLAN time (all 5 plans carried a `<threat_model>` block) and
> verified against the implementation by gsd-security-auditor on 2026-05-23.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| anonymous client → /manifest.json, /sw.js | Both routes intentionally public (SW installs before login) | Static brand strings + cache logic; no auth, no PII |
| service worker → cached responses | SW mediates which network responses are stored and replayed | App-shell chrome only; per-user fragments network-first |
| brew form / GBM client → BrewSessionCreate | User-supplied brew_time_seconds crosses into persistence | Integer seconds (bounded) |
| browser → /logout | State-changing POST must be CSRF-protected | Session invalidation |
| client JS → CSP | Every new script must be nonce-tagged; no inline handlers | Script execution context |
| non-admin user → admin nav targets | UI must not advertise admin routes to non-admins | Route visibility |
| anonymous client → /brew/guided | GBM page must require authentication | Authenticated page render |
| client → /brew/new?brew_time= | User-supplied brew_time crosses into the form/persistence | Integer seconds (bounded) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-11-01 | Information disclosure | /manifest.json, /sw.js public routes | accept | Static non-user-specific content; `app/routers/pwa.py` serves brand strings + SW script, no auth/PII (see Accepted Risks AR-1) | closed |
| T-11-02 | Tampering | SW caching a CSRF-protected mutation | mitigate | `app/static/js/sw.js:53` — `if (req.method !== 'GET') return;` is the first guard in the fetch handler; non-GET bypasses SW with CSRF token intact | closed |
| T-11-03 | Tampering | SW serving a stale authed HTML shell on shared device | mitigate | `app/static/js/sw.js:81-98` — network-first for all non-shell/non-static GETs; `/` removed from APP_SHELL (sw.js:18-24); per-user HTMX fragments never cached | closed |
| T-11-04 | Tampering | Stale SW shell surviving a deploy | mitigate | `app/static/js/sw.js:5` — `CACHE_NAME = 'snobbery-v__BUILD_HASH__'`; activate handler (sw.js:37-44) deletes all non-matching caches on each build | closed |
| T-11-05 | Tampering | `source=pwa` query-param injection via start_url | accept | Home route ignores unknown query params; no template/log sink (see Accepted Risks AR-2) | closed |
| T-11-06 | Tampering | brew_time_seconds negative/absurd | mitigate | `app/schemas/brew_session.py:99` — `brew_time_seconds: int \| None = Field(None, ge=0, le=86400)` | closed |
| T-11-07 | Denial of service | Migration locking brew_sessions during deploy | accept | Additive nullable `ADD COLUMN`, metadata-only lock, no backfill, household scale (see Accepted Risks AR-3) | closed |
| T-11-08 | Spoofing / CSRF | Sign-out forms (base.html dropdown + config hub mobile) | mitigate | `base.html:152-157` + `config_hub.html:59-60` — `<form method="post" action="/logout">` with hidden X-CSRF-Token; `auth.py:362` /logout is POST-only | closed |
| T-11-09 | Information disclosure | Admin nav visible to non-admins | mitigate | `base.html:86-88` (top nav) + `base.html:270-279` (bottom tab) — both wrapped in `{% if request.state.user.is_admin %}`; /admin independently 403-gated by require_admin | closed |
| T-11-10 | Tampering (XSS via CSP) | New nav/SW/banner scripts | mitigate | `base.html:40-42,59` — all new scripts nonce-tagged; nav-bar.js/account-dropdown.js/ios-banner.js carry no `eval(`/`new Function`; Alpine CSP build; no inline `hx-on:`, no `\|safe` | closed |
| T-11-11 | Information disclosure | iOS banner localStorage | accept | `ios-banner.js:41` stores only `'1'` under `snobbery:ios-banner-dismissed` (see Accepted Risks AR-4) | closed |
| T-11-12 | Elevation of privilege | /brew/guided accessed unauthenticated | mitigate | `app/routers/brew_guided.py:44` — `user: User = Depends(require_user)` returns 401 for anonymous | closed |
| T-11-13 | Tampering | brew_time injected via ?brew_time= | mitigate | `app/routers/brew.py:649` — parsed via `_int_or_none`; persisted only through `BrewSessionCreate` (ge=0/le=86400) at brew.py:810,926 | closed |
| T-11-14 | Tampering (XSS / CSP) | NoSleep.js + guidedBrewMode scripts | mitigate | `brew_guided.html:21,24` — both scripts nonce-tagged via head_extra; guided-brew-mode.js + vendor/NoSleep.min.js carry no `eval(`/`new Function`; no inline `hx-on:`, no `\|safe` | closed |
| T-11-15 | Information disclosure | GBM cue prefs localStorage | accept | `guided-brew-mode.js:293,301` stores only `{chime, vibrate}` booleans under `snobbery:gbm:cues` (see Accepted Risks AR-5) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-1 | T-11-01 | /manifest.json and /sw.js are intentionally public so the SW can install before login. Both serve only static, non-user-specific content (locked brand strings + cache logic). Auditor confirmed no auth data or PII in either response. | John | 2026-05-23 |
| AR-2 | T-11-05 | `source=pwa` appended to start_url is never read by the home route and reaches no template or log sink; FastAPI ignores the unknown param. No exploitable sink exists. | John | 2026-05-23 |
| AR-3 | T-11-07 | The brew_time_seconds migration is an additive nullable `ADD COLUMN` with no default backfill — Postgres takes a brief metadata-only ACCESS EXCLUSIVE lock with no table rewrite. Negligible at household scale. | John | 2026-05-23 |
| AR-4 | T-11-11 | iOS install banner stores only the boolean dismiss flag `snobbery:ios-banner-dismissed` (value `'1'`) in localStorage — no user-identifying data. | John | 2026-05-23 |
| AR-5 | T-11-15 | Guided Brew Mode cue prefs store only `{chime, vibrate}` booleans under `snobbery:gbm:cues` in localStorage — no user-identifying data. | John | 2026-05-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-23 | 15 | 15 | 0 | gsd-security-auditor (sonnet) via /gsd-secure-phase |

**Audit notes (2026-05-23):**
- Register origin: authored at PLAN time across plans 11-01 … 11-05 (`register_authored_at_plan_time: true`). Plan 11-05 introduced no new threats (UI/CSS-only sweep).
- All 10 `mitigate` threats independently verified present in the implementation with file:line evidence (recorded in the Threat Register).
- All 5 `accept` threats confirmed implementation-consistent and formally logged in the Accepted Risks Log above.
- Improvement noted (not a new threat): `app/static/js/sw.js:61` adds a same-origin guard (`if (url.origin !== self.location.origin) return;`) that further restricts SW scope.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-23
