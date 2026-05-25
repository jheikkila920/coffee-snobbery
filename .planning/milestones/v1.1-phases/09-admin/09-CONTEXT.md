# Phase 9: Admin - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the `/admin` area gated by `is_admin`, delivering 6 requirements
(ADMIN-01..06). The service layer this phase consumes already exists on disk
(`services/credentials.py`, `services/settings.py`, `services/backup.py`,
`services/ai_service.py`, `services/analytics.py`) — Phase 9 is **routers +
templates + a small amount of wiring/safety logic**, not new business logic.

In scope:
- **ADMIN-01 — User CRUD:** list / create / edit (reset password, toggle
  `is_admin`, deactivate) / delete users. Toggling `is_admin` regenerates the
  target user's session; deactivating logs them out on next request (Phase 2
  D-10 path).
- **ADMIN-02 — API credential vault:** set/update Anthropic + OpenAI keys
  (encrypted via `services/encryption.py`), pick a model per provider,
  enable/disable each provider, masked last-4 display after save. The decrypted
  key never enters a Pydantic model (SEC-6).
- **ADMIN-03 — `app_settings` editor:** value_type-driven inputs, per-row
  inline save via `settings.set_setting()`.
- **ADMIN-04 — Backups page:** list retained files (size + timestamp),
  per-file download, "Run backup now" button calling the shared `run_backup()`.
- **ADMIN-05 — System info panel:** app version, DB server version, photo +
  backup storage usage, active session count, last backup status + timestamp.
- **ADMIN-06 — API health panel:** last AI run timestamp per recommendation
  type, last success/error per provider, last 5 error messages per provider —
  surfacing silent failures (model deprecation, quota, key revocation).
- Two manual action buttons beyond "Run backup now" (user-requested): a
  per-provider **"Test connection"** auth probe, and a **"Run AI refresh now"**
  with both respect-signature and force modes (see D-13/D-14).
- A minimal `is_admin`-gated **"Admin" entry link** in the existing home/footer
  area (just enough to reach `/admin`).

Out of scope (belongs to later phases):
- **Full global navigation + sign-out restoration** — Phase 11 (memory:
  `phase-11-owes-nav-and-signout`; Phase 6 removed the last sign-out link).
  Phase 9 adds only the minimal admin entry link, not the Phase 11 nav.
- **Formal admin test suite** — accrue tests as you go per CLAUDE.md; the formal
  suite is Phase 12.
- **Password reset/recovery by email, SMTP** — out of v1 scope (no email infra).

6 requirements mapped: ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04, ADMIN-05,
ADMIN-06.

</domain>

<decisions>
## Implementation Decisions

### Admin layout & navigation

- **D-01: Sub-pages + index hub.** `/admin` is a landing page linking to six
  focused sub-pages: `/admin/users`, `/admin/credentials`, `/admin/settings`,
  `/admin/backups`, `/admin/system` (system info + API health can share one
  page or split — planner's call). Mirrors the existing catalog CRUD router
  pattern (`roasters.py`, `equipment.py`, etc.). Rejected: a single scrollable
  dashboard with every form inline (long page, harder at 375px).
- **D-02: Persistent section nav via a shared admin base template.** Every admin
  page renders a small secondary nav bar (Users | Credentials | Settings |
  Backups | System) from a shared `admin_base.html` (or equivalent) that itself
  extends `base.html`. One tap between sections; collapses cleanly at 375px. The
  index becomes a convenience hub, not the only path.
- **D-03: Minimal admin entry link, full nav deferred.** Add an `is_admin`-gated
  "Admin" link in the existing home/footer area only. Do **not** build the
  Phase 11 global nav and do **not** restore sign-out here (both are Phase 11
  backlog). Just enough to reach and exercise `/admin`.

### `app_settings` editor (ADMIN-03)

- **D-04: All rows shown; system/critical rows read-only.** Render every
  `app_settings` row for transparency. Mark these as read-only display (not
  editable): `last_ai_run_status`, `last_backup_status`, `last_backup_at`
  (system-written; the panels read them), and `setup_completed` (flipping it to
  false re-opens `/setup`). All other rows are editable.
- **D-05: Type-driven inputs, real value_types.** The actual seeded
  `value_type` set is `int`, `float`, `bool`, `string`, `null` — **not** the
  spec's nominal `integer`/`json`. Map: `int`/`float` -> number input (float
  with a step), `bool` -> checkbox, `string` -> single-line text input (the
  editable string rows are all short: `recommendation_region`,
  `ai_tool_version_*`, `ai_provider_default`). Read-only system rows that hold
  JSON-in-string (`last_*_status`) and `null` rows render pretty-printed in a
  monospace block. `settings.set_setting()` is the authoritative server-side
  coercion + validation + cache invalidation point.
- **D-06: Per-row inline save via HTMX.** Each editable row has its own save
  control; saving POSTs that single key, calls `settings.set_setting(db, key,
  value, *, by_user_id)` (write + cache invalidation + `admin.app_setting_changed`
  audit event), and swaps back a small confirmation fragment. Honors "save
  persists immediately" and reuses the existing HTMX fragment + double-submit
  CSRF pattern.

### Backups page (ADMIN-04)

- **D-07: "Run backup now" = HTMX POST, synchronous in a threadpool.** The
  handler is a **sync `def`** so FastAPI runs it in its threadpool — it will not
  block the event loop or the in-process APScheduler (an `async def` calling the
  sync `run_backup()` would). The button shows a spinner + disables while
  running, then swaps in the `BackupResult` summary and the refreshed file list.
  Acceptable at household scale (a rare, seconds-long operation). Calls the
  shared `run_backup(db, by_user_id=current_user.id)` (Phase 8 D-01) — same
  entry point the scheduler uses; same-day run overwrites the day's file.
- **D-08: Backup download = admin-gated `FileResponse` with strict filename
  validation.** Serve via a router route (not a `StaticFiles` mount), mirroring
  `routers/photos.py`. Validate the requested filename against the actual listed
  files (or a strict regex `db_YYYY-MM-DD.sql` / `photos_YYYY-MM-DD.tar.gz`) to
  block path traversal. Files live in `/app/data/backups`.

### System info + API health panels (ADMIN-05 / ADMIN-06)

- **D-09: App version from `importlib.metadata.version("coffee-snobbery")`** —
  reads the already-defined `0.1.0` from package metadata (single source of
  truth, bump in `pyproject.toml`). No git-SHA build plumbing. DB version via
  `SELECT version()` / `server_version`; photo + backup storage via a disk walk
  of `/app/data/photos` and `/app/data/backups`; active session count via a
  `sessions` row count; last backup status + timestamp from the
  `last_backup_status` row.
- **D-10: API health panel data sources.** Last AI run summary from the
  `app_settings.last_ai_run_status` JSON row (Phase 8 SCHED-03 shape); per-rec
  and per-provider last success/error + last 5 error messages from
  `ai_recommendations` rows (`error_status`, `provider_used`, `model_used`,
  `recommendation_type`, `generated_at`). Read-only display of state the
  scheduler/AI service already write.
- **D-11: Panels are read-only displays** (no inline editing). The only writes
  on these pages are the explicit action buttons (D-07, D-12, D-13/D-14).
- **D-12: Per-provider "Test connection" probe.** A lightweight auth check per
  provider that confirms the saved key authenticates — a minimal/cheapest SDK
  call (e.g., `models.list()` or equivalent), **no recommendations written**,
  reports ok/error per provider. Uses the decrypted key only inside the handler
  scope (never returned to a template/Pydantic model). Planner confirms the
  cheapest auth-only call per SDK via Context7.
- **D-13: "Run AI refresh now" offers BOTH respect-signature and force modes.**
  Two clearly-labeled actions:
  - **Refresh (respect signatures)** — calls `ai_service.regenerate(uid,
    "admin", db=db, force=False)` for each eligible user, identical to the
    nightly scheduler (only regenerates changed users; respects cold-start gate,
    locks, throttle). The cheap, predictable "don't wait until midnight" path.
  - **Force refresh all** — `regenerate(..., force=True)` for every eligible
    user, bypassing the signature check. Clearly labeled as the expensive path
    (re-bills every user). Reuse the Phase 8 eligibility pre-filter
    (`is_active` AND >= 3 sessions); iterate sequentially.
- **D-14: AI-refresh `generated_by` tag.** Use a distinct value (e.g.,
  `"admin"` or `"admin_force"`) so `ai_recommendations.generated_by` /
  telemetry can distinguish admin-triggered runs from `scheduler` and the
  Phase 7 home-page manual refresh. Planner confirms the existing accepted
  values.

### User-management safety (CONFIRMED by John at plan-phase 2026-05-21)

- **D-15: Block-and-deactivate, no cascading hard-delete.** Deactivate (soft) is
  the primary user lifecycle control. Hard-delete is BLOCKED when the target user
  has any `brew_sessions`; it is allowed only for empty/never-used accounts. Brew
  history is preserved — never silently cascade-delete a user's data. The planner
  still confirms the FK `ondelete` semantics via research, but the product posture
  is fixed: do NOT ship a cascading hard-delete.
- **D-16: Last-admin / self-lockout protection (locked).** Refuse, server-side,
  to delete, deactivate, or demote (`is_admin` -> false) the last remaining
  active admin; refuse to let an admin lock themselves out via their own account.

### Claude's Discretion (resolve with these prior-phase-grounded defaults)

- **`is_admin` toggle session regeneration:** honor ROADMAP success #1 — toggling
  privilege regenerates/invalidates the target user's session(s) so the new
  privilege takes effect immediately and a stale cookie can't retain old
  privileges. Likely mechanism: delete the target user's `sessions` row(s) via
  `services/sessions.py` so the next request re-auths fresh. Planner confirms.
- **Password reset mechanism:** admin types a new password (subject to the
  Phase 2 12-char floor), confirmed in-form; argon2id hash via
  `services/auth.py`. No emailed reset (no SMTP in v1). No "show generated
  password once" unless John prefers it.
- **User create email:** keep `email` optional (matches the nullable schema),
  per Phase 2 D-02's note that admin user-create likely keeps email optional
  (unlike `/setup` which required it).
- **System/health page split:** ADMIN-05 + ADMIN-06 may share one
  `/admin/system` page or split into two — planner's call.
- **Panel manual-refresh:** whether the read-only panels re-fetch on a button
  or are static-on-load — planner's call (static-on-load is fine).
- **Health error-message truncation/formatting** — planner's call; truncate
  long provider errors sensibly; never render raw HTML (autoescape stays on).
- **`/debug/proxy` smoke endpoint** (ROADMAP Phase 9 Notes): may be hardened or
  removed now that deployment is verified end-to-end — planner's call; low
  priority.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 9: Admin" — goal sentence, the 5 success
  criteria, Notes (COST-3 health panel reads `last_ai_run_status` + latest
  `ai_recommendations.error_status`; AI-5 tool-version rows editable here;
  `/debug/proxy` harden/remove note).
- `.planning/REQUIREMENTS.md` ADMIN-01..06 (lines ~127-132) — verbatim.
- `.planning/PROJECT.md` §"Admin" requirements, §"Constraints" (mobile-first
  375px; CSRF on every state-changing form; full security headers; no public
  registration).
- `.planning/STATE.md` — session continuity + carried research flags.

### Prior phase context (decisions Phase 9 consumes)
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — the credential +
  settings service contracts: `set_provider_credential(db, provider, *, key,
  model_name, by_user_id)`, `set_provider_enabled(db, provider, enabled, *,
  by_user_id)`, `get_provider_credential(...) -> ProviderCredential | None`,
  `last_four` denormalized for masked display (D-03), `model_name` on the row
  edited atomically with the key (D-02), SEC-6 (no decrypted key in a Pydantic
  model), `settings.get_raw(key) -> (value, value_type)` for the editor,
  `settings.set_setting(...)` write-through + audit, the `admin.*` event
  constants.
- `.planning/phases/08-scheduler-backups/08-CONTEXT.md` — `run_backup(db, *,
  backup_dir, photos_dir, by_user_id) -> BackupResult` (the shared "Run backup
  now" entry point), `BackupResult`/`ArtifactResult` shapes, the
  `last_backup_status` + `last_ai_run_status` JSON shapes the panels read,
  date-only filenames + retention, the AI eligibility pre-filter (`is_active`
  AND >= 3 sessions).
- `.planning/phases/07-ai-services/07-CONTEXT.md` — `regenerate(user_id,
  generated_by, *, db, force=False) -> str` contract + its return-status set,
  the cost controls `regenerate()` owns, and the manual-refresh-bypasses-
  signature behavior (basis for D-13's two modes); `error_status` semantics for
  the health panel.
- `.planning/phases/02-auth/02-CONTEXT.md` — `require_admin` dependency
  (`app/dependencies/auth.py`), session regeneration/`delete_session`,
  D-09/D-10 deactivated-user fail-closed path, the 12-char password floor +
  username 3-32 rule, D-02 (admin user-create likely keeps email optional), the
  `/admin` stub + `pages/admin.html` hook.
- `.planning/phases/00-foundation/00-CONTEXT.md` — `app_settings` seed rows +
  value_types (`int`/`float`/`bool`/`string`/`null`); the `/app/data/backups`
  and `/app/data/photos` volumes; single-uvicorn-worker invariant.

### Code in this repo (read before implementing)
- `app/routers/admin.py` — current Phase 2 stub (`GET /admin` gated by
  `require_admin`); expand into the sub-router set.
- `app/dependencies/auth.py` — `require_admin` (Form-1 Depends shape).
- `app/services/credentials.py` — credential CRUD + `ProviderCredential`
  dataclass + `rewrap_if_needed`.
- `app/services/settings.py` — `get_raw`, `get_str/int/bool/json`,
  `set_setting`, `prewarm_cache`, `invalidate`.
- `app/services/backup.py` — `run_backup`, `BackupResult`, `ArtifactResult`,
  `prune_old_backups`, `write_backup_status`.
- `app/services/ai_service.py` — `regenerate(...)` (AI refresh button + the
  test/probe path reference).
- `app/services/sessions.py` — `regenerate_session`, `delete_session` (is_admin
  toggle + deactivate effects).
- `app/services/auth.py` — `hash_password` (user create + password reset).
- `app/models/user.py` — `User` schema (citext username, nullable citext email,
  password_hash, is_admin, is_active, timestamps, last_login_at).
- `app/models/ai_recommendation.py` — `error_status`, `provider_used`,
  `model_used`, `recommendation_type`, `generated_at`, `generated_by`,
  `tokens_*` (health panel + telemetry).
- `app/models/api_credential.py` — `provider`, `last_four`, `model_name`,
  `is_enabled`.
- `app/migrations/versions/0001_initial.py` — `app_settings` seed rows + the
  real value_type set the editor must handle.
- `app/routers/equipment.py` / `app/routers/roasters.py` — the catalog CRUD
  router + HTMX fragment + CSRF hidden-field template pattern to mirror.
- `app/routers/photos.py` — auth-gated `FileResponse` pattern + header contract
  (template for the backup download route, D-08).
- `app/templates_setup.py` — the shared `Jinja2Templates` instance (autoescape
  on; `csp_nonce` + CSRF cookie helpers in `base.html`).
- `app/events.py` — existing `ADMIN_USER_CREATED`, `ADMIN_APP_SETTING_CHANGED`,
  `ADMIN_API_CREDENTIAL_SET`; add user-update/delete + manual-backup +
  manual-AI-refresh event constants following the taxonomy.

### Operational + spec
- `CLAUDE.md` §"Architectural invariants" (no public registration; AI keys
  encrypted, never bypass `services/encryption.py`; signature-based regen is the
  cost control; mobile-first 375px; CSRF + security headers on every response),
  §"When to ask vs proceed" (changes to AI scheduling/cost = ask first;
  auth/encryption/API-key changes = ask first), §"Things to never do silently"
  (no logging keys/passwords/tokens; no dropping data without a preservation
  plan).

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- `anthropic` (>=0.102,<1.0) / `openai` (>=2.37,<3.0) — cheapest auth-only call
  for the "Test connection" probe (e.g., `models.list()`); confirm `api_key`
  is `str`.
- `FastAPI` 0.136 — `FileResponse` for the backup download; `Depends(require_admin)`;
  sync `def` handler -> threadpool behavior for "Run backup now" (D-07).
- `importlib.metadata` — `version("coffee-snobbery")` for the app-version field.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`services/credentials.py`** — full credential CRUD already exists; the
  ADMIN-02 form is a thin wrapper over `set_provider_credential` /
  `set_provider_enabled` with no `api_key` round-trip field (SEC-6). `last_four`
  is already denormalized for masked display.
- **`services/settings.py`** — `get_raw` + `set_setting` are exactly what the
  ADMIN-03 editor needs; cache invalidation + audit event are built in.
- **`services/backup.py::run_backup`** — the shared "Run backup now" entry
  point; returns a structured `BackupResult` ready to render.
- **`services/ai_service.py::regenerate`** — drives both "Run AI refresh now"
  modes; the status string is render-ready.
- **`require_admin`** (`app/dependencies/auth.py`) — every admin sub-route
  reuses this single gate.
- **Catalog CRUD routers + templates** (`roasters.py`, `equipment.py`, …) — the
  list/form/fragment + HTMX + CSRF idiom to copy for user CRUD and the settings
  editor.
- **`routers/photos.py`** — auth-gated `FileResponse` + strict serving pattern
  for the backup download.

### Established Patterns
- "Cross-cutting -> middleware; feature surface -> router; stateful logic ->
  service." Phase 9 is router + templates only; it calls existing services.
- HTMX fragment swaps with `Cache-Control: no-store` + `Vary: HX-Request`
  (Phase 1) and the double-submit-cookie CSRF token in every state-changing
  form.
- Sync DB for the bulk of CRUD (the established Phase-4-onward pattern); admin
  handlers are sync `def` (also gives the threadpool behavior D-07 wants).
- `app_settings` is the runtime key/value store; status rows are written by the
  system and read (not edited) by the panels.
- structlog one-JSON-line-per-event for audit (`admin.*`); never log keys,
  passwords, or session tokens.
- Single uvicorn worker — the `settings` cache is consistent; the synchronous
  backup must not block the event loop (D-07).

### Integration Points
- `app/routers/admin.py` — expand the stub into the `/admin` index + six
  sub-pages (or a sub-package of routers); all share `require_admin`.
- `app/main.py` — register any new admin routers (the stub router is already
  included; confirm include path).
- `app/templates/pages/` (+ a new `admin_base.html`) — admin base template with
  the persistent section nav (D-02); sub-page templates per area.
- Home/footer template — add the `is_admin`-gated "Admin" entry link (D-03).
- `app/events.py` — new audit event constants for user update/delete, manual
  backup, manual AI refresh, test-connection.

</code_context>

<specifics>
## Specific Ideas

- **value_type reality check:** the editor must handle the ACTUAL seeded types
  (`int`, `float`, `bool`, `string`, `null`) — the spec's `integer`/`json`
  naming does not match the data. No `json`-typed row exists; the JSON content
  lives inside `string`-typed status rows that D-04 makes read-only.
- **"Run backup now" must use a sync `def` handler** so it lands in FastAPI's
  threadpool and never blocks the event loop / APScheduler (single-worker).
- **The decrypted key never leaves the handler scope** — masked `last_four`
  display only; the "Test connection" probe (D-12) uses the decrypted key
  locally and discards it; no Pydantic model carries it (SEC-6).
- **"Force refresh all" is the expensive path** — label it explicitly in the UI;
  it re-bills every eligible user. The default refresh respects signatures.
- **User-delete is genuinely destructive** — see Claude's Discretion; confirm FK
  `ondelete` and the last-admin/self-lockout guards at plan-phase before
  shipping any cascade.

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are ADMIN-01..06 in
REQUIREMENTS.md plus the decisions above and the canonical refs.

## Research flags (for gsd-phase-researcher)
- Cheapest auth-only SDK call for the per-provider "Test connection" probe
  (Anthropic + OpenAI) that verifies a key without generating recommendations.
- Confirm the FK `ondelete` behavior of `brew_sessions` / `ai_recommendations` /
  `wishlist_entries` -> `users` to decide hard-delete vs block-and-deactivate.
- Confirm the accepted `generated_by` values on `ai_recommendations` so the
  admin-triggered refresh can be tagged distinctly from `scheduler` / home-page
  manual refresh.
- Confirm the mechanism for "regenerate the target user's session on is_admin
  toggle" against `services/sessions.py` (delete vs rotate the session row).

</specifics>

<deferred>
## Deferred Ideas

- **Full global navigation + sign-out restoration** — Phase 11 (memory:
  `phase-11-owes-nav-and-signout`). Phase 9 adds only the minimal admin entry
  link.
- **Git-SHA build stamp in system info** — rejected for v1 (needs Dockerfile
  build-arg plumbing; no git tags). Revisit if "which exact build is running"
  becomes operationally important.
- **Emailed / generated password reset** — out of v1 scope (no SMTP). Admin
  types the new password.
- **Background-task / polling backup runner** — rejected; the sync-threadpool
  HTMX approach is sufficient at household scale. Revisit only if backups grow
  long enough to bother an admin waiting.
- **Per-month / per-user AI cost ceiling** — already v2-deferred (PROJECT);
  signature regen + throttle + `max_uses` remains the v1 control. The admin
  "Force refresh all" button must not add a new ceiling.
- **`settings.refresh_cache()` admin endpoint for out-of-band psql edits** —
  Phase 3 deferred; not needed (write-through invalidate covers in-app edits).

### Reviewed Todos (not folded)
- **"Inline add-new-coffee from the brew form"** (carried in prior STATE) —
  Phase 4/5 catalog scope, unrelated to admin. Not folded.

</deferred>

---

*Phase: 9-Admin*
*Context gathered: 2026-05-21*
