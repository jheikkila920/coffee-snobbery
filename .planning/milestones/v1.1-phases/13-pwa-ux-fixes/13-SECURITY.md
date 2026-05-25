---
phase: 13
slug: pwa-ux-fixes
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-25
---

# Phase 13 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 6 plans carried a `<threat_model>` block). Auditor verified mitigations against the implementation — no retroactive-STRIDE scan needed.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser → GET /sw.js | Unauthenticated GET; service worker served from root with `Service-Worker-Allowed: /` | Build-hash cache key (non-secret) |
| Docker build → runtime image | `build_id.txt` artifact crosses the stage-1 build → runtime boundary | Build timestamp |
| build-time script → committed static assets | `generate_pwa_icons.py` writes PNGs served by StaticFiles and referenced by `/manifest.json` | Brand icon assets (non-sensitive) |
| browser → POST /equipment, POST /coffees | Authenticated, CSRF-protected, Pydantic-validated catalog create | Shared household catalog data |
| browser DOM ↔ Alpine components | Client-side only; cue prefs + ratio live in localStorage / Alpine scope | Non-sensitive device prefs |
| /brew/prefill HTMX swap | Authenticated fragment route returning the prefill region | Prefill field values |
| browser ↔ inline no-FOUC `<head>` script | Runs under strict nonce-CSP; reads localStorage, mutates `<html>` class | Theme preference |
| browser ↔ dark-toggle Alpine component | Client-only; writes `localStorage snobbery:theme` | Theme preference |
| browser → GET /data-tools | Authenticated page route (`require_user`) — relocated entry point, not a new public route | Page render |
| browser → POST /brew/import | Authenticated, CSRF-protected multipart upload (unchanged route) | CSV import payload |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-13-01 | Information Disclosure | build_id timestamp in /sw.js CACHE_NAME | accept | `pwa.py:53` — `_get_build_hash()` returns a UTC timestamp truncated to 16 chars; no env/key/token interpolated into `CACHE_NAME`. | closed |
| T-13-02 | Tampering | /sw.js serve-time string substitution | accept | `pwa.py:132` — `read_text().replace("__BUILD_HASH__", _BUILD_HASH)`; `_BUILD_HASH` is a module constant from a build artifact, no user input path. | closed |
| T-13-03 | Denial of Service | malformed build_id.txt breaks SW registration | mitigate | `pwa.py:51-60` — fallback chain: build_id.txt `strip()[:16]` → CSS glob → `"dev"`; absent/empty never raises. `Dockerfile:63` writes the file unconditionally. | closed |
| T-13-04 | Tampering | regenerated icon PNGs | accept | `scripts/generate_pwa_icons.py` — brand PNG assets only; no auth/integrity surface. | closed |
| T-13-05 | Spoofing | manifest icon filename mismatch | mitigate | `pwa.py:86-104` manifest `icons` references exactly match the 4 filenames from `generate_pwa_icons.py:84-96`; all 4 present on disk. | closed |
| T-13-06 | Tampering / Mass-assignment | create_equipment / create_coffee form parse | accept | `schemas/equipment.py:28` and `schemas/coffee.py:32` — `ConfigDict(extra="forbid")` preserved; no new form fields in Phase 13. | closed |
| T-13-07 | Spoofing (CSRF) | create form POST | mitigate | Global `CSRFMiddleware` (`main.py:250`); hidden `X-CSRF-Token` in `equipment_form.html:28` + `coffee_form.html:61`; `htmx-listeners.js:37` injects the header. hx-target change does not alter CSRF. | closed |
| T-13-08 | Information Disclosure | list fragment returned on create | accept | Equipment + coffees are shared household catalog; create routes behind `require_user` (`equipment.py:176`, `coffees.py:353`). No cross-user data. | closed |
| T-13-09 | Tampering | new x-init / htmx:afterSwap re-sync JS | mitigate | `brew_prefill_fields.html:149,158` — named Alpine methods only (`setDose`/`setWater`); `htmx-listeners.js:64-66` `Alpine.initTree`; `htmx.config.allowEval = false` (line 16). No eval/new Function/x-model. | closed |
| T-13-10 | Information Disclosure | localStorage snobbery:gbm:cues | accept | Chime/vibrate device prefs only; no tokens, keys, or session records. | closed |
| T-13-11 | Tampering / XSS | no-FOUC inline `<head>` script | mitigate | `base.html:26` — IIFE under `nonce="{{ csp_nonce(request) }}"`, reads only localStorage + matchMedia; no user input, no eval/new Function. | closed |
| T-13-12 | Tampering | dark-toggle.js | mitigate | `dark-toggle.js:21-62` — `Alpine.data('darkToggle')` in `alpine:init`, named methods only; nonce-served from 'self' (`base.html:51`); CSP-build compliant. | closed |
| T-13-13 | Information Disclosure | localStorage snobbery:theme | accept | `dark-toggle.js:45-52` — stores `'dark'/'light'` only; non-sensitive. | closed |
| T-13-14 | Spoofing (CSRF) | /data-tools import form | mitigate | `data_tools.html:35` — hidden `X-CSRF-Token` input; POSTs to unchanged `/brew/import` enforced by `CSRFFormFieldShim` → `CSRFMiddleware` (`main.py:250-251`). | closed |
| T-13-15 | Elevation / Access Control | new GET /data-tools route | mitigate | `brew.py:638` — handler has `Depends(require_user)`; `data_router` mounted at `main.py:273`. Same auth posture as `/brew`. | closed |
| T-13-16 | Tampering | CSV import pipeline | accept | `brew.py:558-608` — `POST /brew/import` unchanged: Content-Length pre-check, post-read size check, content-type allowlist, single-transaction `import_brews()` all preserved. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-13-01 | T-13-01 | Build timestamp in SW CACHE_NAME is a cache key, not a secret. | gsd-security-auditor | 2026-05-25 |
| AR-13-02 | T-13-02 | SW serve-time substitution value is server-derived at module load; no user-input path. | gsd-security-auditor | 2026-05-25 |
| AR-13-04 | T-13-04 | Regenerated icons are non-sensitive brand assets; no auth/integrity surface. | gsd-security-auditor | 2026-05-25 |
| AR-13-06 | T-13-06 | `extra="forbid"` on both create schemas; no new fields added in Phase 13. | gsd-security-auditor | 2026-05-25 |
| AR-13-08 | T-13-08 | Equipment/coffee list fragment is shared household catalog; no cross-user data leaked. | gsd-security-auditor | 2026-05-25 |
| AR-13-10 | T-13-10 | `snobbery:gbm:cues` holds non-sensitive device prefs; no encryption warranted. | gsd-security-auditor | 2026-05-25 |
| AR-13-13 | T-13-13 | `snobbery:theme` holds a non-sensitive theme preference; no encryption warranted. | gsd-security-auditor | 2026-05-25 |
| AR-13-16 | T-13-16 | CSV import guards (size, content-type, single-transaction) reused unmodified; entry point only relocated. | gsd-security-auditor | 2026-05-25 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-25 | 16 | 16 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Unregistered Flags

None. No new attack surface appeared in the implementation without a corresponding registered threat ID, and all SUMMARY.md threat flags map to registered threats.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-25
