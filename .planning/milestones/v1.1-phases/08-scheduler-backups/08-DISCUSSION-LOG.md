# Phase 8: Scheduler + Backups - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 8-Scheduler + Backups
**Areas discussed:** Backup result + status shape, Same-day file naming + retention, Backup partial-failure handling, Nightly AI run eligibility + status

---

## Backup result + status shape

| Option | Description | Selected |
|--------|-------------|----------|
| Structured result | Entry point returns a result object (per-artifact filename + bytes + ok/error + duration); writes structured (JSON) `last_backup_status`; reused by Phase 9 "Run backup now" | ✓ |
| Minimal status | `last_backup_status` is ok/error + timestamp + message string only | |

**User's choice:** Structured result (Recommended)
**Notes:** Forward dependency on Phase 9's system-info panel; structured status surfaces a failed artifact and gives the panel real numbers.

---

## Same-day file naming + retention

| Option | Description | Selected |
|--------|-------------|----------|
| Date-only, overwrite | `db_YYYY-MM-DD.sql` one snapshot/day; manual run overwrites the nightly; prune by filename date; matches SC-4 + restore runbook glob | ✓ |
| Timestamped, keep all | `db_YYYY-MM-DD_HHMMSS.sql` keeps every run; more disk; runbook + prune logic need updating | |

**User's choice:** Date-only, overwrite (Recommended)
**Notes:** Zero change to the existing CLAUDE.md restore runbook; idempotent daily snapshot.

---

## Backup partial-failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Keep partial + flag | Artifacts attempted independently; keep what succeeds; status records per-artifact result + overall=error; AI and backup jobs fully independent | ✓ |
| Atomic all-or-nothing | Delete the partial on any failure so no half-backup looks valid | |

**User's choice:** Keep partial + flag (Recommended)
**Notes:** Honest + recoverable for restore drills; a failed photos tarball never discards a good DB dump. AI job and backup job are separate APScheduler jobs — one failing never blocks the other.

---

## Nightly AI run eligibility + status

| Option | Description | Selected |
|--------|-------------|----------|
| Eligible + structured status | Pre-filter = `is_active` AND >=3 sessions; `regenerate()` owns cold-start/signature/locks; `last_ai_run_status` stores full SCHED-03 summary (counts + token split + errors + timestamp) | ✓ |
| Eligible + minimal status | Same filter; `last_ai_run_status` is success/error + message; Phase 9 derives detail from `ai_recommendations` rows | |

**User's choice:** Eligible + structured status (Recommended)
**Notes:** Confirms the scheduler does not re-implement gating — it filters cheaply and tallies `regenerate()` return statuses. Structured status gives Phase 9's API-health panel real per-run numbers.

---

## Claude's Discretion

Resolved with documented defaults (see CONTEXT.md `<decisions>` → "Claude's Discretion"):
- Job-registration idempotency — stable explicit job IDs + `replace_existing=True` with `SQLAlchemyJobStore`.
- Timezone wiring — `CronTrigger(..., timezone=APP_TIMEZONE)`, default `America/Chicago`.
- User iteration — sequential, one user at a time (household scale).
- `pg_dump` invocation — from the web container (matched `postgresql-client-16`), connection from config, via `subprocess.run`; photos via `tarfile` stdlib.
- DB dump format — plain uncompressed `.sql` (locked by the restore runbook).
- `scheduler.*` / `backup.*` event taxonomy in `app/events.py`.

## Deferred Ideas

- Backups list/download UI, "Run backup now" button, system-info + API-health panels — Phase 9.
- Per-month/per-user AI cost ceiling — v2-deferred; signature regen + throttle + `max_uses` is the v1 control.
- Off-site/encrypted backup shipping, restore automation, backup integrity verification — out of scope for v1.
- DB dump compression (`.sql.gz`) — rejected for v1 (breaks restore-runbook glob); revisit if VPS disk pressure appears.
- "Inline add-new-coffee from the brew form" (open todo) — Phase 4/5 catalog scope; reviewed, not folded.
