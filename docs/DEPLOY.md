# Deploy Runbook — Snobbery VPS

Ordered checklist for standing Snobbery up on the VPS behind the existing NGINX, then
closing the post-deploy acceptance tests that could only be deferred until a real
deployment existed.

This runbook is the "do it in order" companion to `README.md`. The README is the
reference (full NGINX block, env var table, restore, troubleshooting); this file is the
sequence. Where the README owns canonical content, this runbook links to it rather than
duplicating it.

## Golden rules (do not violate)

- **Single uvicorn worker.** `--workers 1` is non-negotiable — APScheduler and the AI
  locks are in-process. Never pass `--workers N`. (Stated in `entrypoint.sh`,
  `app/services/scheduler.py`, and README.)
- **Localhost bind only.** The web container binds `127.0.0.1:8080`, never `0.0.0.0`.
  NGINX on the host proxies to it.
- **Migrations run themselves.** `entrypoint.sh` runs `alembic upgrade head` before
  uvicorn on every container start. Do not run migrations by hand against a populated DB.
- **All changes go through git.** Never edit files directly on the VPS.

## Stack at a glance

| Service | Image | Host port | Notes |
|---|---|---|---|
| `coffee-snobbery` | built from `Dockerfile` | `127.0.0.1:8080:8000` | FastAPI + uvicorn, 1 worker |
| `coffee-snobbery-db` | `postgres:16-alpine` | none (bridge only) | gated by `pg_isready` healthcheck |

Volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups`.
Network: `coffee-snobbery-net`.

---

## Part 1 — First-time deploy

### 1. Prerequisites on the VPS

- Docker Engine + Compose v2 (`docker compose version`).
- The existing NGINX on the host, with TLS already terminating for the chosen hostname
  (e.g. `snobbery.example.com`) and a DNS A record pointing at the VPS.
- Git access to this repo.

### 2. Get the code

```bash
git clone <repo-url> coffee-snobbery
cd coffee-snobbery
```

### 3. Create and fill `.env`

```bash
cp .env.example .env
```

Generate each secret and paste it into `.env`. These use only `openssl` (present on
every Linux VPS) so they work before the app image is built and do not depend on the
host Python having the app's libraries installed:

```bash
# POSTGRES_PASSWORD
openssl rand -hex 32

# APP_SECRET_KEY
openssl rand -hex 64

# APP_ENCRYPTION_KEY  (Fernet key; comma-separated list, first = primary)
# Fernet requires url-safe base64 of 32 bytes; the tr step converts +/ to -_.
openssl rand -base64 32 | tr '+/' '-_'
```

> The Fernet key MUST be url-safe base64 — do not use a bare `openssl rand -base64 32`
> (its `+`/`/` characters are rejected by Fernet). The `tr '+/' '-_'` step is required.
>
> Alternatively, once the image is built (step 4), generate the key with the app's own
> `cryptography` (the canonical method) — no host Python needed:
>
> ```bash
> docker run --rm coffee-snobbery:latest \
>   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
> ```
>
> Do NOT run `python -c "from cryptography.fernet import Fernet; ..."` directly on the
> host unless `cryptography` is installed there — a fresh host Python will raise
> `ModuleNotFoundError: No module named 'cryptography'`.

Then review the rest:

- `POSTGRES_USER` / `POSTGRES_DB` — defaults (`snobbery`) are fine.
- `DATABASE_URL` — compose **recomputes this at runtime** from `POSTGRES_*` to point at the
  `coffee-snobbery-db` service, so the container always uses the right host. Keep the
  password in the `.env` line in sync anyway (host-side tooling and the env-parity test
  read it).
- `TRUSTED_PROXY_IPS=127.0.0.1` — correct when NGINX runs on the same host (the
  recommended shape). If NGINX is in a separate container/host, set it to the bridge
  gateway IP (`docker network inspect coffee-snobbery-net | grep Gateway`). Getting this
  wrong silently breaks `Secure` session cookies → login bounces.
- `APP_TIMEZONE` — IANA name (e.g. `America/Chicago`); drives the nightly jobs.
- `BACKUP_RETENTION_DAYS`, `LOG_LEVEL`, `LOG_FORMAT` — defaults are fine.

Never commit `.env`.

### 4. Build and start

```bash
docker compose build coffee-snobbery
docker compose up -d
docker compose logs -f coffee-snobbery
```

In the logs, confirm:
- `Running upgrade  -> 0001_initial` (migrations ran), then later migrations to head.
- Uvicorn startup line with **1 worker**.
- No restart loop.

### 5. One-time volume ownership fix — only if reusing old volumes (G-01)

Skip this on a genuinely fresh deploy — the Dockerfile creates `app`-owned mountpoints for
new volumes. Only needed if these volumes predate the Phase 8 fix and you later see
permission errors on backups/photo uploads:

```bash
docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data
docker compose up -d coffee-snobbery
```

### 6. Wire NGINX

Add the canonical server block from **README §"NGINX server-block snippet"** to your NGINX
config. Substitute your real `server_name` and TLS cert paths. The block already covers the
three things that bite if omitted:

- `proxy_pass http://127.0.0.1:8080;` with the four `X-Forwarded-*` / `Host`
  `proxy_set_header` lines (feeds uvicorn's `--proxy-headers`).
- `location = /sw.js` with **no** `Cache-Control` override (PWA-7 — the app sends
  `no-cache`; caching the service worker strands users on stale code after deploys).
- `proxy_buffering off;`

Then:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 7. Smoke checks

```bash
# Liveness — unauthenticated. Expect HTTP 200 and a healthy JSON body.
curl -i https://snobbery.example.com/healthz
```

Then verify the proxy trust chain. `/debug/proxy` is **admin-gated** (anonymous curl
returns 403, which is correct), so check it after you create the admin user in step 8 —
log in as admin in the browser and open:

```
https://snobbery.example.com/debug/proxy
```

Expect JSON with `"scheme": "https"` and `"headers_honored": true`. If `headers_honored`
is `false`, fix `X-Forwarded-Proto`/`X-Forwarded-For` in NGINX or `TRUSTED_PROXY_IPS` in
`.env`, then `docker compose up -d coffee-snobbery` and re-check.

### 8. Create the first admin

`/setup` works **only while zero users exist** (it locks to `/login` after the first admin
is created). There is no public registration — all later users are created from `/admin`.

```
https://snobbery.example.com/setup
```

Create the admin account, then log in.

### 9. Configure an AI provider key

Required to exercise the AI features (and to close the Phase 07/09 AI acceptance tests).
In the browser as admin:

```
/admin/credentials
```

Add an Anthropic or OpenAI key, confirm only the last 4 digits display, and click
**Test connection**. Keys are stored Fernet-encrypted in the DB, never in env.

---

## Part 2 — Deploying a later change

On the VPS, from the repo root:

```bash
git pull
docker compose build coffee-snobbery
docker compose up -d coffee-snobbery
docker compose logs -f coffee-snobbery   # confirm healthy startup + migrations
```

Migrations apply automatically on container start. Re-run the `/healthz` and `/debug/proxy`
smoke checks after any change that touches middleware, auth, or NGINX.

---

## Part 3 — Post-deploy acceptance tests (option A close-out)

These 21 items were correctly deferred because they require a real deployment, live
provider key, or physical devices. Walk them once after the first deploy and check them
off. Source: `/gsd-audit-uat`.

### Phase 01 — Middleware / proxy / CSP
- [ ] **Proxy E2E** — `/debug/proxy` (as admin) shows `scheme=https`, `headers_honored=true`.
- [ ] **CSP nonce** — DevTools: every `<script>` carries a `nonce=` matching the CSP header; no CSP violations in console.
- [ ] **HTMX CSRF on 2nd swap** — a second HTMX POST after a fragment swap succeeds (not 403); cookie is not rotated.

### Phase 02 — Auth UI
- [ ] **375px visual** — `/setup`, `/login`, `/admin`, `/` have no horizontal scroll; inputs ≥16px (no iOS focus-zoom).
- _Items 1 and 3 in the audit (restart stale uvicorn, clean a duplicated `dependencies/` dir) were local dev-container `docker cp` artifacts — they do not recur on a clean VPS image build. Confirm they're absent, then disregard._

### Phase 07 — AI hero card (needs provider key + a gate-open user: ≥3 sessions, ≥5 flavor notes)
- [ ] **Hero card E2E** — home page lazy-loads a single pick (name, roaster, why-prose), buy link tri-state (verified/verifying/couldn't verify), add-to-wishlist, manual refresh. Stale badge appears after logging a new rated session.
- [ ] **375px AI states** — all five hero states (cold-start meter, not-configured, in-flight spinner, try-again, hero card) plus paste-rank and wishlist pages render with no horizontal scroll.

### Phase 09 — Admin (375px, live)
- [ ] **Users** — at `/admin/users`: create, reset password, toggle admin, deactivate, reactivate, delete-empty-user all work; ≥44px tap targets; inline errors readable.
- [ ] **Credentials** — set a key, only last-4 shows; Test connection returns ok/invalid_key; disable persists.
- [ ] **Settings** — edit `min_sessions_for_ai` saves with confirmation; saving `setup_completed` is rejected (403); helper text + type-appropriate inputs.
- [ ] **Backups** — Run backup now produces a result card; download works with correct content-type; URL path-traversal returns 404.
- [ ] **System** — app/DB version, storage sizes, session count, last backup all populated; API health panel renders after an AI/backup run (no `SettingNotFoundError`).
- [ ] **AI refresh** — "Refresh (respect signatures)" vs "Force refresh all" tag rows `admin` vs `admin_force`; only eligible users refreshed; force path labeled expensive.

### Phase 10 — Global search
- [ ] **Mobile sheet** — at 375px the search icon opens a full-screen sheet with auto-focused input; X / Esc / backdrop all close and clear; at ≥768px the inline input shows and no icon.
- [ ] **Debounce + cancel** — typing rapidly fires at most 1–2 queries; DevTools shows in-flight requests cancelled (`hx-sync`).
- [ ] **Latency** — `GET /search?q=` p95 < 100ms on a realistic dataset.

### Phase 11 — PWA / mobile
- [ ] **iOS Safari** — installable on a real iPhone (Add to Home Screen → standalone launch).
- [ ] **Android Chrome** — Lighthouse PWA audit passes installability.
- [ ] **Wake lock** — screen stays awake during a guided brew on a real device.
- [ ] **Responsive** — clean at 375×667 and 390×844.

When all boxes are checked, record results with `/gsd-verify-work <phase>` per phase (or
re-run `/gsd-audit-uat`), then close the milestone with `/gsd-complete-milestone`.

---

## Rollback and recovery

- **Bad release:** `git checkout <previous-tag>` (or revert the commit), then rebuild +
  `up -d`. Migrations are forward-only — if a release added a migration, rolling back code
  without a down-migration plan can leave schema ahead of code. Prefer fixing forward.
- **Restore from backup:** see README §"Restore from backup" (`psql < dump.sql`; never copy
  raw Postgres data files into the volume).

## When something is wrong

See README §"Troubleshooting" for the common failures (healthcheck failing, cookies
dropping after login → `TRUSTED_PROXY_IPS`, migrations not running, `pg_dump` version
mismatch).
