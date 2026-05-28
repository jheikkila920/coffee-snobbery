# Snobbery

Self-hosted household coffee log — FastAPI + PostgreSQL 16 + HTMX, deployed via Docker Compose.

## What this is

Snobbery is a self-hosted household coffee log for pour-over enthusiasts who care about beans, grind, water, and ratio. Multiple users share a household catalog (coffees, equipment, recipes, roasters, flavor notes) but keep separate brew session logs and AI-driven recommendations. Designed for phone-in-hand use at the kettle.

## Stack

- Python 3.12 + FastAPI ≥0.136
- PostgreSQL 16
- SQLAlchemy 2.0 + Alembic + psycopg 3
- Jinja2 + HTMX 2.x + Tailwind CSS (standalone CLI v3.4.17) + Alpine.js (CDN)
- argon2-cffi + Fernet (`cryptography`) for credentials + API keys
- structlog 25.x for JSON logging
- APScheduler in-process
- Docker Compose, two containers (`coffee-snobbery` web + `coffee-snobbery-db`)

## Prerequisites

- Docker and Docker Compose v2 on the host. Nothing else.
- The published image bakes Python 3.12, the Tailwind v3.4.17 CLI, and `postgresql-client-16` from PGDG — no Python or Node required on the host.
- A domain name pointing to the VPS (for HTTPS via your reverse proxy).

## Quickstart

```bash
# 1. Get the compose file + env template
git clone https://github.com/jheikkila54/coffee-snobbery.git
cd coffee-snobbery

# 2. Configure secrets (each .env.example line has a generation hint)
cp .env.example .env
# POSTGRES_PASSWORD     openssl rand -hex 32
# APP_SECRET_KEY        python -c "import secrets; print(secrets.token_urlsafe(64))"
# APP_ENCRYPTION_KEY    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# DATABASE_URL          patch the POSTGRES_PASSWORD value into the URL
# TRUSTED_PROXY_IPS     set to * if running behind Nginx Proxy Manager (see Reverse proxy below)
${EDITOR:-vi} .env

# 3. Pull and start
docker compose up -d
docker compose logs -f coffee-snobbery
# Expect: [alembic] Running upgrade ... -> 0001_initial, ... then
#         INFO uvicorn.main Application startup complete.

# 4. Verify the boot
curl -fsS http://127.0.0.1:8080/healthz
# Expect: {"status":"ok"}

# 5. Visit https://<your-domain> (configured in your reverse proxy below) —
#    on a fresh install with zero users you land on /setup to create the first admin.
```

## Environment variables

Every variable is documented with a generation hint in `.env.example`. Repeated here for convenience; keep them in the same order:

| Variable                | Generation hint / notes                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| `POSTGRES_USER`         | User-chosen. Default: `snobbery`.                                                                |
| `POSTGRES_PASSWORD`     | `openssl rand -hex 32`                                                                           |
| `POSTGRES_DB`           | User-chosen. Default: `snobbery`.                                                                |
| `DATABASE_URL`          | `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}` |
| `APP_SECRET_KEY`        | `python -c "import secrets; print(secrets.token_urlsafe(64))"`                                   |
| `APP_ENCRYPTION_KEY`    | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — comma-separated list (first key = primary for encryption, all attempted for decryption). |
| `TRUSTED_PROXY_IPS`     | Comma-separated upstream IPs uvicorn trusts for `X-Forwarded-*`. Default: `127.0.0.1`. Set to `*` when behind Nginx Proxy Manager — see Reverse proxy. |
| `APP_TIMEZONE`          | IANA name, e.g. `America/Chicago`. Consumed by APScheduler.                                      |
| `BACKUP_RETENTION_DAYS` | Integer; default `14`. Consumed by the backup job.                                               |
| `LOG_LEVEL`             | `DEBUG | INFO | WARNING | ERROR`. Default: `INFO`.                                               |
| `LOG_FORMAT`            | `json` (default) or `console`.                                                                   |

For full inline generation hints and per-var notes see `.env.example`. The 4-step procedure for adding a new var is in `CONTRIBUTING.md`.

## Reverse proxy

### Nginx Proxy Manager (recommended)

NPM (`jc21/nginx-proxy-manager`) is the recommended reverse proxy for self-hosted Snobbery — it ships with the Let's Encrypt integration and reaches the Snobbery container by name on a shared Docker network.

**One-time: connect NPM to the Snobbery network.**

Both containers must share a Docker network so NPM can resolve `coffee-snobbery:8000` by name. From the host that runs NPM:

```bash
docker network connect coffee-snobbery-net <npm-container-name>
# Confirm: docker network inspect coffee-snobbery-net | grep -A2 Containers
# You should see both the NPM container and coffee-snobbery in the Containers list.
```

If NPM lives on a different host you'll need the secondary plain-NGINX path below — NPM cannot reach the container by name across hosts.

**NPM Proxy Host fields:**

*Details tab:*

| Field | Value | Notes |
|-------|-------|-------|
| Domain Names | `snobbery.example.com` | Your FQDN; A record must point to the VPS |
| Scheme | `http` | Snobbery listens on plain HTTP inside Docker; NPM terminates TLS |
| Forward Hostname / IP | `coffee-snobbery` | Container name on the shared `coffee-snobbery-net` network |
| Forward Port | `8000` | The in-container uvicorn port (NOT 8080) |
| Cache Assets | Off | Snobbery sets its own cache headers; leave NPM caching off |
| Block Common Exploits | On | Recommended |
| Websockets Support | Off | Not needed in v1.2 (SSE is planned for a later phase) |

*SSL tab:*

| Field | Value |
|-------|-------|
| SSL Certificate | Let's Encrypt — Request new certificate |
| Force SSL | On |
| HTTP/2 Support | On |
| HSTS Enabled | On |
| HSTS Subdomains | Off (unless you control subdomains) |

*Advanced tab — Custom Nginx Configuration:* paste this `/sw.js` location block to make the service worker survive the proxy without the wrong cache header (PWA-7 invariant — the app already sends `Cache-Control: no-cache` on `/sw.js`; do NOT add a cache override):

```nginx
location = /sw.js {
    proxy_pass http://coffee-snobbery:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    add_header Service-Worker-Allowed "/" always;
    # Do NOT add Cache-Control here — the app already sends no-cache (PWA-7).
}
```

**Load-bearing gotchas (NPM topology):**

1. **`TRUSTED_PROXY_IPS=*` is non-negotiable** behind NPM. Set this in `.env` — uvicorn trusts X-Forwarded-* headers only from the listed upstream IPs, and NPM's container IP is allocated by Docker and can change. Without `*`, `Secure` session cookies silently break on login.
2. **Shared docker network is mandatory.** See the `docker network connect` step above.
3. **`X-Forwarded-Proto: https`** is sent automatically by NPM when SSL is active. Combined with `TRUSTED_PROXY_IPS=*`, uvicorn rewrites `request.url.scheme` to `https` so the `Secure` cookie flag works.
4. **Port mapping is optional under NPM.** The `127.0.0.1:8080:8000` line in `docker-compose.yml` exists for the plain-NGINX fallback below; NPM operators can comment it out for a cleaner posture, but leaving it is harmless.

### Plain NGINX (secondary)

If you run NGINX directly on the host instead of NPM, the compose stack binds to `127.0.0.1:8080` and NGINX proxies to that. Canonical server block (SEC-04):

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

The four `proxy_set_header` lines feed uvicorn's `--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` so `request.url.scheme` is rewritten to `https` and `request.client.host` is rewritten to the real upstream IP. Without `proxy_set_header X-Forwarded-Proto $scheme`, cookies marked `Secure` silently break. With plain NGINX on the same VPS, `TRUSTED_PROXY_IPS=127.0.0.1` is the default and is correct.

### Operational smoke check

After deploying — or after any reverse-proxy config change — run:

```bash
curl -i https://snobbery.example.com/debug/proxy
```

A correctly configured stack returns JSON with `"scheme": "https"` and `"headers_honored": true`. If `headers_honored` is `false`, verify the reverse proxy is sending `X-Forwarded-Proto $scheme` AND verify `TRUSTED_PROXY_IPS` in `.env` matches the upstream IP (or `*` for NPM). Restart the web container after changing `TRUSTED_PROXY_IPS`: `docker compose up -d coffee-snobbery`.

## Single uvicorn worker — DO NOT change

The web service runs with **exactly one uvicorn worker** (`--workers 1`). This is **non-negotiable**.

**Why:**
- **APScheduler runs in-process** (nightly AI runs, nightly `pg_dump`, nightly photo tarball). Two workers = the scheduler fires twice. Four workers = four times. Eight workers = eight times, billing eight times the AI cost.
- **Module-level AI locks** prevent concurrent AI calls per `(user_id, recommendation_type)`. They're Python `threading.Lock` objects in module globals — useless across processes. Multiple workers would happily race the lock and double-bill an Anthropic web-search call.
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

## Upgrade

Snobbery releases publish to GHCR as multi-arch images (amd64 + arm64). Upgrade by bumping the pinned tag in `docker-compose.yml`:

```bash
# 1. Edit docker-compose.yml — update the image: line to the new semver
#    image: ghcr.io/jheikkila54/coffee-snobbery:v1.3.0
docker compose pull
docker compose up -d
# Migrations run automatically on container start via entrypoint.sh.
docker compose logs -f coffee-snobbery
# Confirm: alembic upgrade completes, then `Application startup complete.`
```

The four published tag forms (per release) — pick the float you want:

- `:v1.2.0` — exact, immutable. Recommended default.
- `:1.2` — mutable, follows the latest patch in the 1.2 line.
- `:1` — mutable, follows the latest minor in the 1.x line.
- `:latest` — mutable, latest stable. Pre-releases (`v*-rc1`, `v*-beta1`) do NOT bump `:latest`.

## Restore from backup

The backup job runs nightly (`pg_dump` + photos tarball into `coffee_snobbery_backups`). For catastrophic-loss recovery:

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

**Healthcheck failing.** Check `docker compose logs coffee-snobbery` and `docker compose logs coffee-snobbery-db`. `/healthz` opens a transaction with a 2s `statement_timeout` and runs `SELECT 1` — failures usually mean pool exhaustion or the db container hasn't passed `pg_isready` yet.

**Cookies dropping after login.** Check `TRUSTED_PROXY_IPS`. If uvicorn doesn't trust the reverse proxy hop, it ignores `X-Forwarded-Proto`, the app sees `scheme=http`, the `Secure` cookie flag means the browser refuses to send the cookie back on the next request, and login bounces. The `/debug/proxy` route end-to-end-verifies the trust chain.

**Migrations didn't run on startup.** Look for `Running upgrade ... -> 0001_initial` in `docker compose logs coffee-snobbery`. If you see the line, migrations ran. If you don't, the container is likely in a restart loop — inspect the logs for the alembic error (a duplicate-table conflict means someone ran the migration manually against a populated DB; clean-state recovery is to drop the volume and start over).

**`pg_dump` version mismatch in backups.** The image installs `postgresql-client-16` from the PGDG apt repo specifically because the `python:3.12-slim` default is `postgresql-client-15`, which silently truncates v16-only column types. If a future image bump changes this, the smoke gate (`docker compose down -v && docker compose up -d --build`) will catch it — it asserts `pg_dump --version` reports a `16.x` line.

**Image pull fails / 403 from ghcr.io.** Snobbery images are public — `docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0` should work without authentication. If you see a 403:
1. Verify the image is public: visit `https://github.com/jheikkila54/coffee-snobbery/pkgs/container/coffee-snobbery`.
2. If the image was just published, wait 1–2 minutes for GHCR's CDN to propagate.
3. If you have stale credentials in Docker's credential store, clear them: `docker logout ghcr.io && docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`.
4. If the image is private (one-time setup after the first release tag), the maintainer must flip visibility — see `CONTRIBUTING.md` § "After first release".

## Known caveats

### iOS Wake Lock — silent-audio fallback

Guided Brew Mode requests the [Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API) (`navigator.wakeLock.request("screen")`) to keep the screen on during a brew timer. iOS Safari has incomplete Wake Lock support (the API exists but is unreliable across iOS versions and low-power mode). When the native API fails or is unavailable, the app falls back to a silent-audio-loop technique (a looped, inaudible audio element) inspired by NoSleep.js to suppress sleep.

The lock is re-acquired on `visibilitychange → visible` (e.g., after the user switches back to the browser tab). A visible on-screen indicator shows whether the screen-stay-on is active. On iOS, test on a real device — simulator behavior does not match.

## Project history

This project was bootstrapped by **GSD** (an agentic planner + builder) from the spec in `docs/snobbery-gsd-prompt.md`. That file is the historical product brief — useful reference for the original intent, but **the code is the source of truth** wherever they conflict. Operational conventions, stack invariants, and the never-do-silently list live in `CLAUDE.md`. Developer setup (Makefile, fast iteration, tests, releases) lives in `CONTRIBUTING.md`.

## License

Private. Household use.
