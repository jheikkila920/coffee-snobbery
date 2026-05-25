---
phase: 9
slug: admin
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-21
---

# Phase 9 — Security (Admin)

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser -> /admin/* | Any authenticated user can attempt admin routes; only is_admin may pass | Session cookie (signed), all admin mutations |
| browser -> home.html | Admin link rendered only for is_admin; defense-in-depth over the route gate | is_admin flag from session state |
| admin form -> sessions table | Privilege/active changes must evict stale cookies immediately | Session row deletes (target user_id) |
| admin form -> users table | Destructive deletes must never silently cascade brew history | User row + FK constraints |
| admin form -> credentials service | Plaintext key crosses here once; encrypted at rest, never echoed back | API key (encrypted via Fernet) |
| handler -> SDK provider | Decrypted key used to authenticate; must stay in handler scope only | API key (in-scope local variable) |
| handler -> template/log | Only last_four may cross; decrypted key must not | last_four, provider, status strings |
| admin form -> settings service | Arbitrary key/value submission; only non-read-only keys writable; coercion server-side | app_settings values |
| browser -> /admin/backups/{filename} | Untrusted filename param; must not escape /app/data/backups | Backup file bytes |
| run-now handler -> event loop | Sync long-running pg_dump must not block the loop / APScheduler | None (sync threadpool) |
| handler -> app_settings status rows | Cache-pop gotcha; must read raw or the panel crashes after a write | last_ai_run_status, last_backup_status |
| admin form -> ai_service.regenerate | Force mode re-bills every eligible user; must be deliberate + tagged | AI token spend, generated_by tag |
| handler -> ai_recommendations error display | Stored error_status may contain untrusted provider text; must be escaped + truncated | error_status strings (max 200 chars) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-09-01 | Elevation of Privilege | every /admin route | mitigate | `Depends(require_admin)` on every handler in users.py, credentials.py, settings_editor.py, backups.py, system.py | closed |
| T-09-02 | Information Disclosure | home.html admin link | mitigate | `{% if request.state.user and request.state.user.is_admin %}` guard in home.html:13 | closed |
| T-09-03 | Spoofing | admin section nav links | accept | See Accepted Risks Log | closed |
| T-09-04 | Elevation of Privilege | session not invalidated after is_admin/deactivate | mitigate | `_delete_user_sessions(target_id)` calls `sql_delete(SessionModel).where(user_id==target_id)` in users.py:76; called on toggle-admin, deactivate, delete, and password reset | closed |
| T-09-05 | Denial of Service | last-admin lockout / self-lockout | mitigate | `_count_active_admins()` with `FOR UPDATE` row lock (users.py:64-68); self-id check on all demote/deactivate/delete paths; blocks when count <= 1 | closed |
| T-09-06 | Tampering | hard-delete cascades brew history | mitigate | `brew_sessions` count guard at users.py:488-492 returns 409 before DELETE; RESTRICT FK is DB backstop | closed |
| T-09-07 | Elevation of Privilege | IDOR on target user_id | mitigate | `target_id` from URL path param in all handler signatures; never from form body | closed |
| T-09-08 | Information Disclosure | password hash / plaintext in template or log | mitigate | No `password_hash` in any admin template; edit form context excludes it; structlog emits user_id/by_user_id only | closed |
| T-09-09 | Tampering | CSRF on user mutations | mitigate | Hidden `X-CSRF-Token` field in admin_user_form.html:30; HTMX configRequest global listener (htmx-listeners.js:37) injects token on all row-button POSTs | closed |
| T-09-10 | Information Disclosure | decrypted API key in template context | mitigate | credentials.py:45 uses `select(ApiCredential)` for display (last_four/model_name/is_enabled only); `api_key` stays local at line 121, never added to template context | closed |
| T-09-11 | Information Disclosure | API key in logs | mitigate | credentials.py:167 emits only `provider` + `last_four`; no key material in any log call | closed |
| T-09-12 | Spoofing / cost abuse | test-connection writes recommendations or bills tokens | mitigate | Probe in system.py uses `client.models.list()` only (lines 391, 396); zero ai_recommendations writes; `del client` in finally | closed |
| T-09-13 | Tampering | CSRF on credential set/enable + test-connection button | mitigate | Hidden `X-CSRF-Token` field in admin_credential_row.html at lines 25, 59, 95 (all three forms per row) | closed |
| T-09-14 | Cryptography misuse | bypassing services/encryption.py | mitigate | No Fernet import in credentials.py; only `set_provider_credential` called for writes (line 145) | closed |
| T-09-15 | Tampering | editing setup_completed re-opens /setup | mitigate | `_READ_ONLY_KEYS` frozenset (settings_editor.py:49-57) includes `setup_completed`; guard at line 162 returns 403 before `set_setting` | closed |
| T-09-16 | Tampering | arbitrary value bypassing type coercion | mitigate | `set_setting` is sole coercion point; router passes raw string at settings_editor.py:194 | closed |
| T-09-17 | Denial of Service | get_str raising on status rows after a write | mitigate | settings_editor.py:113-120 uses `select(AppSetting.key, AppSetting.value, ...)` directly; no `get_str` call anywhere in the handler | closed |
| T-09-18 | Tampering | CSRF on inline settings save | mitigate | Hidden `X-CSRF-Token` field in admin_setting_row.html:31 | closed |
| T-09-19 | Elevation of Privilege | non-admin editing settings | mitigate | `require_admin` on GET /settings (settings_editor.py:104) and POST /settings/{key} (settings_editor.py:146) | closed |
| T-09-20 | Tampering | path traversal on backup download | mitigate | `_BACKUP_FILENAME_RE.match(filename)` first (backups.py:153); then `Path.resolve().is_relative_to(_BACKUP_DIR.resolve())` (backups.py:159); then `is_file()` | closed |
| T-09-21 | Denial of Service | async run-now blocks event loop | mitigate | `def run_backup_now` is `sync def` at backups.py:171 (not async); FastAPI routes to threadpool | closed |
| T-09-22 | Information Disclosure | serving arbitrary file types / wrong content-type | mitigate | `media_type` fixed to `application/gzip` or `application/octet-stream` at backups.py:166; only regex-matched filenames served | closed |
| T-09-23 | Tampering | CSRF on backup run-now | mitigate | Hidden `X-CSRF-Token` field in admin_backups.html:15 | closed |
| T-09-24 | Elevation of Privilege | non-admin download / run-now | mitigate | `require_admin` on GET /backups (backups.py:109), GET /backups/{filename} (backups.py:138), POST /backups/run (backups.py:173) | closed |
| T-09-25 | Denial of Service | get_str raising on status rows after a write | mitigate | system.py:155 uses `select(AppSetting.value).where(key=="last_backup_status")`; system.py:167 uses `select(AppSetting.value).where(key=="last_ai_run_status")`; no `get_str` | closed |
| T-09-26 | Information Disclosure | stored error_status rendered as raw HTML (XSS) | mitigate | Jinja autoescape globally ON (templates_setup.py:47); `_truncate_error()` truncates at 200 chars (system.py:88); no `\|safe` in any admin template | closed |
| T-09-27 | Spoofing / cost abuse | accidental force-refresh re-bills all users | mitigate | `generated_by = "admin_force" if force else "admin"` at system.py:307; force button labeled as expensive re-bill path in UI | closed |
| T-09-28 | Denial of Service | async regenerate blocking event loop | mitigate | `async def run_ai_refresh` at system.py:286; `await ai_service.regenerate(...)` at system.py:317; sequential iteration | closed |
| T-09-29 | Elevation of Privilege | non-admin reaching system/health/refresh/probe | mitigate | `require_admin` on GET /system (system.py:104), POST /system/ai-refresh (system.py:288), POST /system/test-connection/{provider} (system.py:356) | closed |
| T-09-30 | Spoofing / cost abuse | force-refresh re-bills ineligible users | mitigate | `_get_eligible_user_ids(db)` imported from `app.services.scheduler` and called at system.py:310-312; not reimplemented; filter: is_active AND >= 3 brew_sessions | closed |
| T-09-31 | Information Disclosure | decrypted API key leaked by test-connection probe | mitigate | `cred.key` only used as `api_key=cred.key` in SDK client constructor; never in template context or any log line; `del client` in finally block at system.py:420 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-09-01 | T-09-03 | Admin section nav links are plain anchors with no state-change capability. They link to routes that are independently gated by `require_admin`. A non-admin who crafts or clicks these links receives 403 from the route gate — no action or data is exposed by the links themselves. The visual link existing without authentication of the link itself is standard practice for navigation elements pointing to server-enforced access controls. | plan-time design decision | 2026-05-21 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 31 | 31 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-21
