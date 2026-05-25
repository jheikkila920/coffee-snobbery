---
phase: 1
slug: middleware
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-16
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 01-RESEARCH.md §11 (Validation Architecture).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 9.0.x + `pytest-asyncio` (per STACK.md §2) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 creates if Phase 0 hasn't already |
| **Quick run command** | `docker compose exec coffee-snobbery pytest tests/middleware -x --tb=short` |
| **Full suite command** | `docker compose exec coffee-snobbery pytest -x` |
| **Estimated runtime** | ~15 seconds (Phase 1 scope only); full suite grows phase by phase |

---

## Sampling Rate

- **After every task commit:** Run `docker compose exec coffee-snobbery pytest tests/middleware -x --tb=short`
- **After every plan wave:** Run `docker compose exec coffee-snobbery pytest -x`
- **Before `/gsd-verify-work`:** Full suite must be green; manual `curl /debug/proxy` smoke documented in plan as a release-blocking checklist item
- **Max feedback latency:** 15 seconds (per-task), 60 seconds (per-wave)

---

## Per-Task Verification Map

> The planner populates this table during `/gsd-plan-phase`. Each task row binds a task ID
> (`{N}-{plan_id}-{task_seq}`) to a requirement, an expected secure behavior, and a runnable
> test command. The map below is the canonical Phase 1 requirement-to-test mapping from
> RESEARCH.md §11; the planner inserts the Task ID + Plan + Wave columns as plans land.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0 | AUTH-05 | — | Session middleware reads cookie, resolves `request.state.user`, 30-day expiry | unit | `pytest tests/middleware/test_session.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-05 | — | `regenerate_session()` deletes old row + mints new UUID + sets new signed cookie | unit | `pytest tests/services/test_sessions.py::test_regenerate -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-05 | — | `last_seen` is only refreshed when >5 minutes stale (write throttling) | unit | `pytest tests/middleware/test_session.py::test_refresh_throttling -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-08 | — | `/login` returns 429 on the 6th request within 15 minutes from the same IP | integration | `pytest tests/routers/test_auth_stub.py::test_login_rate_limit -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-08 | — | slowapi keys on real client IP (uvicorn `--proxy-headers` rewrites `request.client.host`) | integration | `pytest tests/routers/test_auth_stub.py::test_login_rate_limit_per_ip -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-10 | — | Structured log per auth event carries `event`, `request_id`, `ip`; no request body | unit | `pytest tests/middleware/test_logging.py::test_redaction -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-10 | — | Sensitive keys (`password`, `api_key`, `session_token`) redacted from log output | unit | `pytest tests/middleware/test_logging.py::test_redaction_processor -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | AUTH-10 | — | `request_id` propagates via contextvars across all log calls in a single request | unit | `pytest tests/middleware/test_logging.py::test_contextvars_propagation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-01 | — | POST without valid CSRF token returns 403 | integration | `pytest tests/middleware/test_csrf.py::test_missing_token -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-01 | — | POST with valid CSRF cookie + matching header returns 200 | integration | `pytest tests/middleware/test_csrf.py::test_valid_token -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-01 | — | CSRF cookie value remains constant across multiple HTMX fragment swaps (no rotation) | integration | `pytest tests/middleware/test_csrf.py::test_no_rotation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-01 | — | `/csp-report` POST is exempt from CSRF check | integration | `pytest tests/middleware/test_csrf.py::test_csp_report_exempt -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-02 | — | Every response carries `Content-Security-Policy: ... script-src 'self' 'nonce-...'` | integration | `pytest tests/middleware/test_security_headers.py::test_csp_present -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-02 | — | CSP nonce is unique per request (two consecutive requests carry different nonces) | integration | `pytest tests/middleware/test_security_headers.py::test_nonce_uniqueness -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-02 | — | CSP contains NO `'unsafe-eval'` and NO `'unsafe-inline'` in `script-src` | integration | `pytest tests/middleware/test_security_headers.py::test_no_unsafe_eval -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-03 | — | Every response carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` | integration | `pytest tests/middleware/test_security_headers.py::test_all_headers -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-04 | — | README contains the NGINX `Strict-Transport-Security` line and the proxy-header server block | docs | `pytest tests/docs/test_readme_nginx.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-04 | — | `/debug/proxy` returns `scheme`, `client_host`, `trusted_proxy_ips`, `headers_honored` | integration | `pytest tests/routers/test_debug_proxy.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-04 | — | With `X-Forwarded-Proto: https`, `/debug/proxy` reports `scheme=https` | integration | `pytest tests/routers/test_debug_proxy.py::test_https_via_proxy_header -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-05 | — | Jinja2 autoescape is ON globally | unit | `pytest tests/templates/test_autoescape.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-05 | — | CI grep test fails when `\|safe` appears under `app/templates/pages/` | shell/CI | `pytest tests/ci/test_no_unsafe_jinja.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | SEC-05 | — | Same grep covers `hx-on:`, `hx-vals='js:`, `hx-headers='js:` under `app/templates/pages/` | shell/CI | `pytest tests/ci/test_no_unsafe_jinja.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-11) | — | GET without `HX-Request` → `Cache-Control: private, no-cache, must-revalidate` | integration | `pytest tests/middleware/test_fragment_cache.py::test_full_page -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-11) | — | GET with `HX-Request: true` → `Cache-Control: no-store` + `Vary: HX-Request` | integration | `pytest tests/middleware/test_fragment_cache.py::test_fragment -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-12) | — | Route-set `Cache-Control` is not overwritten by FragmentCacheHeadersMiddleware | integration | `pytest tests/middleware/test_fragment_cache.py::test_no_overwrite -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-11) | — | `/static/` paths bypass FragmentCacheHeadersMiddleware | integration | `pytest tests/middleware/test_fragment_cache.py::test_static_bypass -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-06) | — | POST `/csp-report` (`application/csp-report`) logs structured `csp.violation` event | integration | `pytest tests/routers/test_csp_report.py::test_legacy_format -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-06) | — | POST `/csp-report` (`application/reports+json`) logs structured `csp.violation` event | integration | `pytest tests/routers/test_csp_report.py::test_reporting_api_format -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | (D-06, D-17) | — | `/csp-report` rate-limited to 30/min/IP (31st request returns 429) | integration | `pytest tests/routers/test_csp_report.py::test_rate_limit -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Phase 1's Wave 0 MUST land:

- [ ] `tests/__init__.py` — empty (if not already created in Phase 0)
- [ ] `tests/conftest.py` — TestClient + database fixtures (transaction rollback per test)
- [ ] `tests/middleware/__init__.py` — empty
- [ ] `tests/middleware/test_session.py` — covers AUTH-05 behaviors (cookie roundtrip, expiry refresh throttle, regenerate, missing-row handling)
- [ ] `tests/middleware/test_csrf.py` — covers SEC-01 (missing-token 403, valid-token 200, no-rotation, `/csp-report` exempt)
- [ ] `tests/middleware/test_security_headers.py` — covers SEC-02, SEC-03 (CSP present, nonce uniqueness, no `'unsafe-eval'`, full header set)
- [ ] `tests/middleware/test_fragment_cache.py` — covers D-11/D-12 (HX-Request branch, full-page branch, no-overwrite, static bypass)
- [ ] `tests/middleware/test_logging.py` — covers AUTH-10 (contextvars propagation, redaction processor, event taxonomy)
- [ ] `tests/routers/__init__.py` — empty
- [ ] `tests/routers/test_auth_stub.py` — covers AUTH-08 (`/login` rate limit, per-IP key)
- [ ] `tests/routers/test_csp_report.py` — covers D-06 (both report content-types, rate limit)
- [ ] `tests/routers/test_debug_proxy.py` — covers SEC-04 + D-16 (`/debug/proxy` response shape, `X-Forwarded-Proto` honored)
- [ ] `tests/templates/__init__.py` — empty
- [ ] `tests/templates/test_autoescape.py` — covers SEC-05 (Jinja2 autoescape on)
- [ ] `tests/ci/__init__.py` — empty
- [ ] `tests/ci/test_no_unsafe_jinja.py` — grep test forbidding `|safe`, `hx-on:`, `hx-vals='js:`, `hx-headers='js:` under `app/templates/pages/`
- [ ] `tests/docs/__init__.py` — empty
- [ ] `tests/docs/test_readme_nginx.py` — grep test confirming README NGINX block + HSTS line are present
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 confirms or creates (Phase 0 may have already)
- [ ] Test dependencies present in `pyproject.toml`: `pytest>=9,<10`, `pytest-asyncio`, `httpx>=0.28,<0.29`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real NGINX rewrites `X-Forwarded-Proto: https` and uvicorn honors it end-to-end | SEC-04, FOUND-08 | Requires a real reverse proxy in front of uvicorn; docker-compose could include one but complicates CI | After deploying to VPS: `curl -i https://snobbery.example.com/debug/proxy` and assert response body shows `"scheme": "https"`, `"headers_honored": true`. Document in README as a release-blocking checklist item. |
| HSTS header reaches the browser via NGINX `add_header` | SEC-04 | NGINX-layer behavior; CI does not run NGINX | Manual: `curl -I https://snobbery.example.com/` from a non-localhost client → `Strict-Transport-Security: max-age=63072000; includeSubDomains`. |
| CSP nonce is picked up correctly by Alpine.js + HTMX in a real browser | SEC-02 | Browser-DOM-level behavior; Playwright lands in Phase 12 | Manual: open DevTools → Network → confirm `<script>` `nonce=` attribute matches the CSP header `'nonce-...'` value on each refresh. Move to Playwright in Phase 12. |
| `htmx.config.allowEval = false` blocks `hx-on:` even if a template slips it past grep | SEC-02, D-04 | Runtime browser behavior (CSP enforcement + HTMX runtime guard) | Manual: temporarily author a template with `hx-on:click="alert(1)"`; observe console CSP-violation error and confirm the handler does not fire. |
| HSTS preload eligibility | SEC-04 (out of scope for v1) | Preload submission is a manual process at `hstspreload.org`; not a CI concern | Documented as a v1.1 follow-up if John wants to submit the domain to the preload list. |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify command OR a Wave 0 dependency that creates the test file
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all `❌ W0` references in the per-task map
- [ ] No watch-mode flags (`--watch`, `-w`) in any commit-time test command
- [ ] Feedback latency < 15s per task, < 60s per wave
- [ ] `nyquist_compliant: true` set in frontmatter once all rows are populated by the planner and Wave 0 lands green

**Approval:** pending
