# Snobbery

Self-hosted household coffee log — FastAPI + PostgreSQL 16 + HTMX, deployed via Docker Compose.

## What this is

Snobbery is a self-hosted household coffee log for pour-over enthusiasts who care about beans, grind, water, and ratio. Multiple users share a household catalog (coffees, equipment, recipes, roasters, flavor notes) but keep separate brew session logs and AI-driven recommendations. Designed for phone-in-hand use at the kettle; deployed to a single VPS behind an existing NGINX reverse proxy.

## Stack

- Python 3.12 + FastAPI ≥0.136
- PostgreSQL 16
- SQLAlchemy 2.0 + Alembic + psycopg 3
- Jinja2 + HTMX 2.x + Tailwind CSS (standalone CLI v4) + Alpine.js (CDN, added in Phase 1)
- argon2-cffi + Fernet (`cryptography`) for credentials + API keys
- structlog 25.x for JSON logging
- APScheduler in-process (Phase 8)
- Docker Compose, two containers (`coffee-snobbery` web + `coffee-snobbery-db`)

## Prerequisites

- Docker + Docker Compose v2 on the host. Nothing else.
- No Python or Node required on the host — the image bakes Python 3.12, the Tailwind v4 standalone CLI binary, and `postgresql-client-16` from PGDG.

## Quick start

```bash
cp .env.example .env
# Fill in the four secrets (each .env.example line has a generation hint):
#   POSTGRES_PASSWORD          openssl rand -hex 32
#   APP_SECRET_KEY             python -c "import secrets; print(secrets.token_urlsafe(64))"
#   APP_ENCRYPTION_KEY         python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   DATABASE_URL               (patch the password into the postgresql+psycopg:// URL)
# POSTGRES_USER + POSTGRES_DB default to "snobbery".

make up                                  # docker compose up -d
make logs                                # tail web container logs
curl http://127.0.0.1:8080/healthz       # should return {"status":"ok"}
```

## Working with the code

| Command         | What it does                                                                |
| --------------- | --------------------------------------------------------------------------- |
| `make up`       | `docker compose up -d` — start the two-service stack                        |
| `make down`     | `docker compose down` — stop, keep volumes                                  |
| `make logs`     | Tail the web container logs                                                 |
| `make logs-db`  | Tail the Postgres container logs                                            |
| `make psql`     | Open a `psql` shell inside the db container                                 |
| `make migrate`  | Run `alembic upgrade head` (migrations also run on container start)         |
| `make revision MSG="add foo column"` | Generate a new alembic autogenerate revision        |
| `make test`     | Run `pytest -x` inside the web container                                    |
| `make smoke`    | Cold-start end-to-end: `down -v && up -d --build && /healthz` (phase gate)  |
| `make shell`    | Open a `bash` shell inside the web container                                |
| `make build`    | Rebuild the web image (`docker compose build coffee-snobbery`)              |
| `make fmt`      | Run `ruff format .` inside the web container                                |
| `make lint`     | Run `ruff check .` inside the web container                                 |

Raw `docker compose` commands still work — the Makefile is convenience, not a wrapper-with-state.

## Deployment (single VPS behind NGINX)

### Single uvicorn worker — DO NOT change

The web service runs with **exactly one uvicorn worker** (`--workers 1`). This is **non-negotiable**.

**Why:**
- **APScheduler runs in-process** (Phase 8 — nightly AI runs, nightly `pg_dump`, nightly photo tarball). Two workers = the scheduler fires twice. Four workers = four times. Eight workers = eight times, billing eight times the AI cost.
- **Module-level AI locks** (Phase 7) prevent concurrent AI calls per `(user_id, recommendation_type)`. They're Python `threading.Lock` objects in module globals — useless across processes. Multiple workers would happily race the lock and double-bill an Anthropic web-search call.
- **Signature-based AI regeneration** (the cost control) assumes one process owns the decision. Multi-worker would make it racy and unreliable.

The single-worker rule is documented loudly in **three places** so a future operator trips over it before they can ship a worker-bumped image:

1. `entrypoint.sh` — top-of-file comment block above the `exec uvicorn` invocation (location #1).
2. `app/services/scheduler.py` — top-of-file comment block in the Phase 8 placeholder module (location #2).
3. This README section (location #3).

If you remove or weaken any of these, restore the other locations so the count of warnings stays at three. The audit grep:

```bash
grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py
```

must return at least three hits.

### NGINX server-block snippet

NGINX terminates TLS on the host and proxies to `127.0.0.1:8080` (the compose stack binds there — never to `0.0.0.0`). Canonical server block (SEC-04):

```nginx
# Optional: redirect HTTP → HTTPS so HSTS gets a chance to install on first visit.
server {
  listen 80;
  server_name snobbery.example.com;
  return 301 https://$host$request_uri;
}

server {
  listen 443 ssl http2;
  server_name snobbery.example.com;
  # ssl_certificate / ssl_certificate_key handled by your existing setup.

  # HSTS — two years, includes subdomains. Browsers refuse plaintext after first visit.
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

  # Phase 11 PWA service worker needs scope: / — file is served from /sw.js so the
  # default scope already allows it, but the explicit header is required if the file
  # ever moves under /static/. Documented here now to avoid a retroactive edit.
  #
  # IMPORTANT (PWA-7): the app already sets Cache-Control: no-cache on the /sw.js
  # response. Do NOT add an override like `add_header Cache-Control "public, max-age=..."`.
  # Caching the service worker file causes users to run stale SW code after deploys.
  # The no-cache directive ensures the browser revalidates on every page load.
  location = /sw.js {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    add_header Service-Worker-Allowed "/" always;
    # Do not set Cache-Control here — the app sends Cache-Control: no-cache (PWA-7).
  }

  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Disable response buffering. Phase 1 doesn't need it (no SSE in v1), but Phase 7
    # may switch from polling to SSE in v1.1 and a buffered NGINX silently delays /
    # drops events. Pre-baking the directive avoids retroactive NGINX edits.
    proxy_buffering off;
  }
}
```

The four `proxy_set_header` lines feed uvicorn's `--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` so `request.url.scheme` is rewritten to `https` and `request.client.host` is rewritten to the real upstream IP. Without `proxy_set_header X-Forwarded-Proto $scheme`, cookies marked `Secure` silently break.

### Deploying a change

On the VPS, from the repo root:

```bash
git pull
docker compose build coffee-snobbery
docker compose up -d coffee-snobbery
docker compose logs -f coffee-snobbery   # confirm healthy startup + migrations
```

Migrations run automatically on container start via `entrypoint.sh` (`alembic upgrade head` precedes `exec uvicorn`).

### TRUSTED_PROXY_IPS

The default `TRUSTED_PROXY_IPS=127.0.0.1` aligns with the recommended deployment shape: NGINX runs on the same host, proxies to the compose-exposed `127.0.0.1:8080`, and the X-Forwarded-* headers from NGINX are honored.

If NGINX runs on a different host or a Docker network address, update `TRUSTED_PROXY_IPS` to the comma-separated list of trusted upstream IPs:

- **NGINX on the same VPS as the Docker stack** (recommended): `TRUSTED_PROXY_IPS=127.0.0.1`
- **NGINX in a separate container or on a different host**: the Docker bridge gateway IP, typically `172.18.0.1`. Confirm with `docker network inspect coffee-snobbery-net | grep Gateway`.

**Setting this wrong breaks `Secure` session cookies** (uvicorn ignores `X-Forwarded-Proto`, the app sees `scheme=http`, the cookie's `Secure` flag is dropped on outbound, the browser refuses to send it back, login bounces). The `/debug/proxy` endpoint (see §Operational smoke check) end-to-end-verifies the trust-list configuration.

### Operational smoke check

After deploying — or after any NGINX config change — run:

```bash
curl -i https://snobbery.example.com/debug/proxy
```

A correctly configured stack returns JSON with `"scheme": "https"` and `"headers_honored": true`. If `headers_honored` is `false`:

- Verify NGINX is setting `X-Forwarded-Proto $scheme` and `X-Forwarded-For $proxy_add_x_forwarded_for`.
- Verify `TRUSTED_PROXY_IPS` in `.env` matches the upstream IP NGINX hits the container from.
- Restart the web container after changing `TRUSTED_PROXY_IPS`: `docker compose up -d coffee-snobbery`.

Phase 2 will wrap `/debug/proxy` in the admin gate; until then it is publicly readable (the trust list is operational config, not secret).

## Environment variables

Every variable is documented with a generation hint in `.env.example`. Repeated here for convenience; keep them in the same order:

| Variable                | Generation hint / notes                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| `POSTGRES_USER`         | User-chosen. Default: `snobbery`.                                                                |
| `POSTGRES_PASSWORD`     | `openssl rand -hex 32`                                                                           |
| `POSTGRES_DB`           | User-chosen. Default: `snobbery`.                                                                |
| `DATABASE_URL`          | `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}` |
| `APP_SECRET_KEY`        | `python -c "import secrets; print(secrets.token_urlsafe(64))"`                                   |
| `APP_ENCRYPTION_KEY`    | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — comma-separated list (first key = primary for encryption, all attempted for decryption). Phase 3 wires the `MultiFernet`. |
| `TRUSTED_PROXY_IPS`     | Comma-separated upstream IPs uvicorn trusts for `X-Forwarded-*`. Default: `127.0.0.1`.            |
| `APP_TIMEZONE`          | IANA name, e.g. `America/Chicago`. Consumed by APScheduler (Phase 8).                            |
| `BACKUP_RETENTION_DAYS` | Integer; default `14`. Consumed by the Phase 8 backup job.                                       |
| `LOG_LEVEL`             | `DEBUG | INFO | WARNING | ERROR`. Default: `INFO`.                                               |
| `LOG_FORMAT`            | `json` (default) or `console`.                                                                   |

Adding a new env var? Follow the 4-step procedure in `CLAUDE.md` (`.env.example` → `docker-compose.yml` → `app/config.py` → README).

## Restore from backup

Phase 8 owns the full backup procedure (nightly `pg_dump` + photos tarball into `coffee_snobbery_backups`). For catastrophic-loss recovery in Phase 0:

```bash
# Identify the backup
ls -lh /app/data/backups/   # inside the web container; or via the named volume on the host

# Restore the database via psql (NEVER by copying data files into the volume)
docker compose exec -T coffee-snobbery-db psql -U $POSTGRES_USER $POSTGRES_DB \
  < /app/data/backups/db_YYYY-MM-DD.sql

# Restore the photos
tar -xzf /app/data/backups/photos_YYYY-MM-DD.tar.gz -C /app/data/photos
```

**Warning.** Never restore by copying raw Postgres data files into the `coffee_snobbery_postgres_data` volume. Postgres refuses to start if the on-disk file ownership or pg_version mismatches the running image. Always use `psql < dump.sql` — that path is version-tolerant and survives a Postgres image upgrade.

## Troubleshooting

**Healthcheck failing.** `make logs` and `make logs-db`. `/healthz` opens a transaction with a 2s `statement_timeout` and runs `SELECT 1` — failures usually mean pool exhaustion (raise an ear if you start seeing `QueuePool limit of size 10 overflow 5 reached`) or the db container hasn't passed `pg_isready` yet (compose's `depends_on: condition: service_healthy` should prevent this but is worth a glance).

**Cookies dropping after login (Phase 2+).** Check `TRUSTED_PROXY_IPS`. If uvicorn doesn't trust the NGINX hop, it ignores `X-Forwarded-Proto`, the app sees `scheme=http`, the `Secure` cookie flag means the browser refuses to send the cookie back on the next request, and login bounces. Phase 1's `/debug/proxy` route end-to-end-verifies the trust chain.

**Migrations didn't run on startup.** Look for `Running upgrade ... -> 0001_initial` in `docker compose logs coffee-snobbery`. If you see the line, migrations ran. If you don't, the container is likely in a restart loop — inspect the logs for the alembic error (a duplicate-table conflict means someone ran the migration manually against a populated DB; clean-state recovery is to drop the volume and start over).

**`pg_dump` version mismatch in backups.** The image installs `postgresql-client-16` from the PGDG apt repo specifically because the `python:3.12-slim` default is `postgresql-client-15`, which silently truncates v16-only column types. If a future image bump changes this, `make smoke` will catch it (it asserts `pg_dump --version` reports a `16.x` line).

## Project history

This project was bootstrapped by **GSD** (an agentic planner + builder) from the spec in `docs/snobbery-gsd-prompt.md`. That file is the historical product brief — useful reference for the original intent, but **the code is the source of truth** wherever they conflict. Operational conventions, stack invariants, and the never-do-silently list live in `CLAUDE.md`.

## License

Private. Household use.
