---
phase: 08
slug: scheduler-backups
status: verified
threats_open: 0
asvs_level: 2
created: 2026-05-21
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: authored at PLAN time (all 3 plans carried a `<threat_model>` block). Audit verified each mitigation against the implementation; no retroactive-STRIDE scan was required.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| backup.py → pg_dump subprocess | DB credentials cross from `settings.DATABASE_URL` into a child process. Single-tenant container; no user input reaches this path. | DB connection password (via `env=` dict) |
| backup.py → filesystem (`/app/data/backups`) | Backup files contain full plaintext DB data. Volume reachable only inside the Docker network. | Full database contents, photo archive |
| scheduler job → DB / AI provider | Nightly AI job triggers `regenerate()`, which makes external AI calls. No user input reaches the scheduler; eligibility is server-derived. | Per-user brew data → AI provider |
| lifespan → APScheduler thread pool | Job bodies run in worker threads off the event loop; boundary is the sync→async `asyncio.run` bridge. | None untrusted (internal control flow) |
| tests/conftest.py `sync_db` fixture | Test-only DB session; guarded so it can never bind to the live DB. | Test DB rows only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-08-01 | Tampering | `tests/conftest.py` `sync_db` fixture | mitigate | `_postgres_reachable()` + `"test" in db_name` interlock (`conftest.py:566-582`); skips if not a test DB | closed |
| T-08-02 | Information Disclosure | event field-shape constants (`app/events.py`) | accept | Constants are event-name strings only; no value/comment names a secret (`events.py:157-191`) | closed |
| T-08-03 | Information Disclosure | PGPASSWORD in subprocess env (`backup.py`) | accept | Password via `subprocess_env(PGPASSWORD=...)` only; never a CLI arg, never logged (`backup.py:145`) | closed |
| T-08-04 | Tampering | subprocess injection via DATABASE_URL (`backup.py`) | mitigate | `subprocess.run([...])` list, no `shell=True`; URL parsed via `make_url()` (`backup.py:146-163`) | closed |
| T-08-05 | Information Disclosure | pg_dump plaintext output (`backup.py`) | accept | Dest = `/app/data/backups` Docker volume; no remote upload code; off-site shipping v2-deferred (`backup.py:55,282`) | closed |
| T-08-06 | Information Disclosure | credentials leaking into logs (`backup.py`) | mitigate | `backup.*` log calls carry filenames/bytes/status only; no password/DATABASE_URL field (`backup.py:340,357,384,386,427`) | closed |
| T-08-07 | Denial of Service | runaway nightly AI job (`scheduler.py`) | mitigate | `max_instances=1` + `misfire_grace_time=3600` in `job_defaults` (`scheduler.py:83-84`) | closed |
| T-08-08 | Elevation of Privilege / Access Control | AI job processing inactive users (`scheduler.py`) | mitigate | `_get_eligible_user_ids` filters `is_active.is_(True)` AND `HAVING count(BrewSession.id) >= 3` (`scheduler.py:170,172`) | closed |
| T-08-09 | Tampering | duplicate jobs after restart (N× AI bill) (`scheduler.py`) | mitigate | Stable IDs `nightly_ai_refresh`/`nightly_backup` + `replace_existing=True` (`scheduler.py:119-120,125-126`) | closed |
| T-08-10 | Information Disclosure | `last_ai_run_status` leaking secrets (`scheduler.py`) | accept | Summary holds counts/token totals/status/timestamp only; no credentials or user content (`scheduler.py:265-272,329-330`) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-02 | New `scheduler.*`/`backup.*` event constants document field shapes only; the structlog redactor (`app/logging.py`) is unchanged and summary fields are counts/tokens/statuses, not credentials. | John | 2026-05-21 |
| AR-08-02 | T-08-03 | Linux per-process env is not world-readable via `ps`; container is single-tenant. Standard pg_dump-in-Docker pattern; PGPASSWORD passed via `env=` dict, never logged. | John | 2026-05-21 |
| AR-08-03 | T-08-05 | Backups confined to the `coffee_snobbery_backups` Docker named volume, reachable only within the Docker network. Encrypted off-site shipping explicitly v2-deferred per `08-CONTEXT.md <deferred>`. | John | 2026-05-21 |
| AR-08-04 | T-08-10 | `last_ai_run_status` summary contains only aggregate counts + token totals + timestamp; no user content, no credentials. structlog redactor unmodified by Phase 8. | John | 2026-05-21 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 10 | 10 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-21
