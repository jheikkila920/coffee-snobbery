# Phase 9: Admin - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 9-Admin
**Areas discussed:** Admin layout & nav, Settings editor scope, System/health panels
**Areas offered but not selected:** User management safety (resolved via Claude's discretion, grounded in prior phases)

---

## Admin layout & nav

### Q1 — /admin structure

| Option | Description | Selected |
|--------|-------------|----------|
| Sub-pages + index | Landing page linking to six focused sub-pages; mirrors catalog CRUD pattern | ✓ |
| Single dashboard, all sections | One scrollable page, every section inline | |
| Hybrid: dashboard + edit pages | Read-only panels inline, edit areas as sub-pages | |

**User's choice:** Sub-pages + index hub

### Q2 — In-admin navigation

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent section nav | Secondary nav bar on every admin page via a shared admin base template | ✓ |
| Index hub only | Index is the only hub; sub-pages link back to it | |
| You decide | Planner picks | |

**User's choice:** Persistent section nav via shared admin base template

### Q3 — Entry point to /admin (global nav deferred to Phase 11)

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal entry link, defer nav | is_admin-gated "Admin" link in home/footer only | ✓ |
| Direct URL only | No entry link; type the URL | |
| Entry link + restore sign-out | Also restore sign-out on admin pages | |

**User's choice:** Minimal entry link; defer full nav + sign-out to Phase 11
**Notes:** Project memory flags nav + sign-out as Phase 11 backlog (Phase 6 removed the last sign-out link).

---

## Settings editor scope

### Q1 — Which app_settings rows are editable

| Option | Description | Selected |
|--------|-------------|----------|
| All shown, system rows read-only | Render all; system/critical rows (last_*_status, last_backup_at, setup_completed) read-only | ✓ |
| Hide system rows entirely | Only editable rows rendered | |
| Everything editable | No guardrails | |

**User's choice:** All shown, system rows read-only

### Q2 — value_type to input control mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Type-driven, text=single-line | int/float->number, bool->checkbox, string->single-line text; read-only system/JSON/null pretty-printed | ✓ |
| Type-driven, text=textarea | Same but string rows use multi-line textarea | |
| You decide | Planner picks | |

**User's choice:** Type-driven, single-line text; settings.set_setting() does authoritative coercion
**Notes:** Real value_types are int/float/bool/string/null (not the spec's integer/json).

### Q3 — Save behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Per-row inline save via HTMX | Each row saves independently; cache invalidation + audit; confirmation fragment | ✓ |
| Single form, one Save button | All rows in one form, one submit loop | |
| You decide | Planner picks | |

**User's choice:** Per-row inline save via HTMX

---

## System/health panels

### Q1 — "Run backup now" behavior

| Option | Description | Selected |
|--------|-------------|----------|
| HTMX POST, sync in threadpool | Sync def handler -> threadpool; spinner; swap result + refreshed list | ✓ |
| Background task, poll for result | Kick off background, poll for completion | |
| Plain form POST, full reload | Classic submit; page hangs until done | |

**User's choice:** HTMX POST, synchronous in FastAPI threadpool

### Q2 — Manual action buttons beyond "Run backup now"

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only panels | No AI triggers in admin | |
| Add per-provider "Test connection" | Cheap auth probe per provider | |
| Add "Run AI refresh now" | Admin-forced regeneration | |
| Add both test + refresh | Both | ✓ |

**User's choice:** Add both — per-provider "Test connection" AND "Run AI refresh now"

### Q3 — "Run AI refresh now" semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Run nightly job on demand | regenerate(force=False); respects signature/cost controls | |
| Force regenerate all eligible | regenerate(force=True); re-bills everyone | |
| Offer both (respect vs force) | Two clearly-labeled modes | ✓ |

**User's choice:** Offer both modes; force clearly labeled as the expensive path

### Q4 — App version source

| Option | Description | Selected |
|--------|-------------|----------|
| pyproject via importlib.metadata | version("coffee-snobbery") = 0.1.0 | ✓ |
| Git SHA baked at build | Commit SHA via Dockerfile build-arg | |
| Both: version + short SHA | Both, needs build plumbing | |

**User's choice:** importlib.metadata.version("coffee-snobbery")

---

## Claude's Discretion

- **User-management safety** (area offered but not selected): resolved with prior-phase-grounded defaults — deactivate-first lifecycle, guarded hard-delete (planner confirms FK ondelete; do not silently cascade), last-admin/self-lockout protection, is_admin-toggle session regeneration, admin-typed password reset (12-char floor), optional email on user-create. The destructive delete decision is surfaced for John's confirmation at plan-phase.
- System info + API health page split (one page or two).
- Panel manual-refresh vs static-on-load.
- Health error-message truncation/formatting.
- `/debug/proxy` harden-or-remove.

## Deferred Ideas

- Full global nav + sign-out restoration -> Phase 11.
- Git-SHA build stamp in system info -> v2 if needed.
- Emailed/generated password reset -> out of v1 (no SMTP).
- Background-task/polling backup runner -> rejected for v1.
- Per-month/per-user AI cost ceiling -> v2-deferred.
- settings.refresh_cache() admin endpoint -> not needed (write-through invalidate).
