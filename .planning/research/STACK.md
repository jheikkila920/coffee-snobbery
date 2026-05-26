# Stack Research — Snobbery v1.2 Additions

**Domain:** Self-hosted household coffee log (FastAPI + PostgreSQL + HTMX) — subsequent milestone
**Researched:** 2026-05-25
**Confidence:** HIGH (PyPI + Docker official docs + GitHub docs verified; locked stack not re-researched)

> This document covers ONLY what is new or changed for v1.2. The locked v1.1 stack is
> treated as settled fact. See CLAUDE.md (Technology Stack section) for the full v1.1 pin table.
> Do not re-open locked decisions.

---

## 1. Locked Stack — Confirmed Unchanged

Nothing in v1.2's feature set requires modifying any locked dependency. Explicitly confirmed as-is:

- Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16
- Jinja2 + HTMX 2.x + Tailwind v3 standalone CLI + Alpine.js
- anthropic SDK (>=0.102,<1.0) + openai SDK (>=2.37,<3.0)
- Single uvicorn worker — unchanged, APScheduler in-process, no new services
- argon2-cffi, itsdangerous, cryptography/MultiFernet, starlette-csrf, slowapi, structlog, Pillow

---

## 2. Feature-by-Feature Stack Analysis

### 2.1 Self-Host Packaging (Prebuilt Container Image to a Registry)

**Registry: GitHub Container Registry (ghcr.io) — not Docker Hub**

Use GHCR. Reasons, in order of importance:

1. The repo is already on GitHub. `GITHUB_TOKEN` is automatically available in Actions with
   `packages: write` permission — zero credential setup, no extra secrets.
2. Public images on GHCR are free with no pull-rate limits for unauthenticated consumers.
   Docker Hub's free tier throttles unauthenticated pulls to 100/6h per IP — a shared VPS
   or home lab hits this instantly.
3. Permissions are scoped to the GitHub repo, not a personal Docker Hub account. The image
   stays with the project if ownership transfers.
4. ghcr.io is the de-facto standard for GitHub-hosted open-source container apps; the
   self-host audience expects it.

Published image name: `ghcr.io/OWNER/coffee-snobbery:TAG`

**Multi-arch: YES — linux/amd64 + linux/arm64**

Rationale: the self-host audience runs on Raspberry Pi 4/5 (arm64), Oracle Cloud free
tier arm64 VMs, and Apple Silicon Macs (Docker Desktop emulates arm64 natively). The
Dockerfile already has the groundwork — Stage 1 has an explicit `case "${TARGETARCH}"` with
`amd64` and `arm64` branches downloading the correct Tailwind binary. Finishing multi-arch
is low-incremental-effort relative to its reach.

**CI Approach: QEMU single-runner, release-only workflow**

A separate `.github/workflows/release.yml` triggered only on `v*.*.*` tags (not every
push/PR — that stays in `ci.yml`). QEMU emulation is sufficient for this Dockerfile because:
- The slow steps (pip install, apt installs) are cacheable via `cache-from: type=gha`
- Tailwind binary curl is fast (~35MB) and runs on the native host (see Stage 1 fix below)
- Release cadence is infrequent; a 10-15min build is acceptable

A native arm64 runner would be faster but is not available on the GitHub Actions free tier.
Do not pay for runners for a hobby project's release CI.

Required GitHub Actions (official Docker-maintained, all widely used):
| Action | Version | Purpose |
|--------|---------|---------|
| `docker/setup-qemu-action` | `@v3` | Installs QEMU for cross-compilation |
| `docker/setup-buildx-action` | `@v4` | Enables buildx multi-platform builds |
| `docker/login-action` | `@v3` | Authenticates to ghcr.io via GITHUB_TOKEN |
| `docker/metadata-action` | `@v5` | Generates image tags from git refs |
| `docker/build-push-action` | `@v6` | Multi-platform build + push |

**Versioning/Tagging Scheme**

Use `docker/metadata-action` semver patterns. On `git tag v1.2.0`:

```
ghcr.io/OWNER/coffee-snobbery:1.2.0    # exact (immutable; document this as the pin target)
ghcr.io/OWNER/coffee-snobbery:1.2      # minor-floating (auto-gets patch bumps)
ghcr.io/OWNER/coffee-snobbery:1        # major-floating
ghcr.io/OWNER/coffee-snobbery:latest   # latest stable
ghcr.io/OWNER/coffee-snobbery:sha-XXXX # short git SHA for traceability
```

metadata-action produces all of these automatically from a single `type=semver` + `type=sha`
configuration. Tell end users to pin to `1.2.0` or `1.2` in their compose file — never
`latest` in a running stack.

**Tailwind CLI Build Step in Multi-Arch Context**

The current Dockerfile Stage 1 works but runs under QEMU emulation for arm64 targets.
Fix: add `--platform=$BUILDPLATFORM` to Stage 1 so the Tailwind CLI download and CSS
compilation always run natively on the build host:

```dockerfile
# Recommended — Stage 1 always runs on native build host
FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS tailwind-builder
```

The compiled CSS is architecture-independent (it is a stylesheet). Copying it into the
arm64 Stage 2 is correct and requires no change.

With `--platform=$BUILDPLATFORM`, `$TARGETARCH` in Stage 1 reflects the builder's arch
(amd64 in CI), not the target. Simplify: always download `tailwindcss-linux-x64` in Stage
1 (it runs on the CI host). Remove the `case "${TARGETARCH}"` block from Stage 1; keep it
only in Stage 2 if any arch-specific logic is added there later.

**Alembic Auto-Migrate-On-Start with Prebuilt Image**

No change. `entrypoint.sh` runs `alembic upgrade head` before uvicorn starts. This is
already the documented behavior and works identically whether the image is built locally or
pulled from GHCR. New migrations are baked into the image. Users update by pulling a new
tag and restarting — that's the whole UX improvement for self-hosters.

**Consumer Compose File**

Provide a `docker-compose.ghcr.yml` alongside the existing `docker-compose.yml`. Swap
the `build:` block for `image: ghcr.io/OWNER/coffee-snobbery:1.2`. Everything else
(env_file, volumes, networks, ports, healthcheck) is identical. Developers who clone the
repo still use the original `docker-compose.yml` and build locally.

**No new Python dependencies for this feature.**

---

### 2.2 AI "Research a Coffee + Predict My Rating from Preferences"

**Verdict: Zero new libraries. Reuse existing ai_service.py + structured output pattern.**

The existing stack already provides everything needed:
- `ai_service.py` — provider abstraction (Anthropic/OpenAI), web search tool, structured
  Pydantic output schemas, module-level AI lock for single-worker safety
- `analytics.py` — preference derivation queries (flavor profiles, rating history); read
  these as prompt context
- `anthropic` SDK (>=0.102) — `web_search_20250305` tool for coffee research
- `openai` SDK (>=2.37) — Responses API + web search for same

The new flow is: a new router endpoint + a new Pydantic response schema
(predicted_rating: float, confidence: str, rationale: str, sources: list[str]) wired into
the existing `call_ai_with_web_search()` abstraction (or equivalent). The prompt takes the
coffee name/roaster, the user's top flavor preferences and historical rating distribution,
and asks the model to predict. The web search tool supplements with current reviews.

This is entirely prompt engineering + a new schema. No embedding, no vector store, no local
model, no RAG pipeline.

On-demand vs. nightly: user-triggered. The module-level AI lock in ai_service.py handles
concurrency correctly at single-worker scale. No APScheduler involvement for this flow.

**Do not add:** LangChain, LlamaIndex, sentence-transformers, pgvector, any vector DB,
any local inference library, any new AI SDK. The existing SDK abstractions are sufficient
and adding an orchestration layer adds 100MB+ to the image for zero benefit at this scale.

---

### 2.3 Cafe Quick-Rate (No-Recipe Coffee Log)

**Verdict: Zero new libraries.**

A new DB table (e.g., `cafe_visits`) + a simplified form + a new router. Fields: brand/name,
info text, brew method (select from existing enum or a short list), rating (existing Alpine
slider component), optional photo (existing Pillow upload path), timestamp, user_id FK.

No FK to `brew_sessions` or `bags` — this is intentionally decoupled. Logging a cafe drink
is not a home brew; it should not require a coffee to exist in the catalog.

All UI components already exist:
- HTMX form pattern (identical to the brew session form)
- Alpine.js rating slider (already in the codebase)
- Pillow photo upload (already in the codebase, optional)
- CSRF middleware (global; already covers any new POST endpoint)

**Do not add:** barcode scanning libraries, cafe discovery APIs, separate rating widget
libraries (the existing Alpine slider covers it).

---

### 2.4 Beanconqueror-Inspired Features

Beanconqueror (Ionic/Angular mobile app) is feature-rich. The relevant subset for a
server-rendered household app and their stack implications:

| Feature | New library needed? | Verdict |
|---------|---------------------|---------|
| Bean inventory / bag depletion | No | `bags` table already exists; add `remaining_grams` column + form field. Pure schema + Jinja/HTMX. |
| Brew timer (in-page countdown) | No | ~20 LOC Alpine.js `setInterval` on a hidden `x-data` component. |
| Water recipe tracking | No | New table + form. Pure schema work. |
| Grinder grind-setting history | No | `brew_sessions` already has grind_size. A grinder history view is a query, not a library. |
| Rating / tasting notes | No | Already shipped in v1.1. |
| Statistics / charts / sparklines | Conditional | See below. |
| QR code for bean sharing/import | Conditional | See below. |
| Bluetooth scale integration | Out of scope | Web Bluetooth API is incomplete on iOS Safari; too risky for a household PWA. Defer indefinitely. |
| Export to Visualizer JSON format | No | CSV export already ships; a Visualizer-format JSON endpoint is a new serializer, no new dep. |

**Charts/Sparklines — Conditional on scope decision**

If v1.2 includes rating-over-time charts, extraction yield history, or any data visualization
beyond tabular lists, a charting library is needed. Tailwind + Alpine.js cannot render SVG
charts without additional tooling.

Recommendation: **Chart.js 4.x via CDN, if charts are in scope.**

- Pin: `chart.js@4.4.9` (current stable; verify at implementation time via
  https://github.com/chartjs/Chart.js/releases)
- Load via CDN: `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js">`
- Size: ~60KB gzipped — acceptable
- CSP integration: Chart.js does not need `unsafe-eval`. Render data server-side as a JSON
  blob in the template, initialize the chart in a `<script nonce="{{ nonce }}">` block.
  This is fully compatible with the existing nonce-CSP.
- Alpine.js integration: use `x-init="initChart($el, chartData)"` or a dedicated vanilla
  JS file in `app/static/js/charts.js` (no npm required)

Alternative if charts are simple trend lines only: hand-rolled SVG `<polyline>` via a
Jinja2 macro. Zero JS, zero library, CSP-clean. Not suitable for interactive or labeled
charts.

**Do not add** Chart.js if charts are not in the confirmed v1.2 scope. Decide at
requirements phase and treat it as a conditional dep.

**QR Code for Bean Sharing/Import — Conditional on scope decision**

If v1.2 includes shareable bean cards (QR → pre-fill bean form), server-side QR generation
is needed.

Recommendation: **`segno` (pure Python, no C extensions, native SVG output)**

- Pin: `segno>=1.6,<2` (1.6.1 current on PyPI)
- Generate as SVG for inline template embedding or as a `/api/beans/{id}/qr.svg` endpoint
- No Pillow dependency (Pillow is already installed, but segno doesn't need it)
- ~80KB installed size — minimal
- Alternative: `qrcode` (python-qrcode) is fine if PNG raster output is required (e.g., for
  printable labels) since Pillow is already in the image. Prefer segno for web/SVG use.

Client-side QR scanning is out of scope. The workflow is: generate QR → user scans with
phone camera's native reader → opens URL → form pre-fills. No in-app scanner needed.
Do not add ZXing, jsQR, or any JS barcode scanning library — iOS Safari lacks native
BarcodeDetector API support as of 2026.

---

## 3. New Dependencies Summary

### Required (confirmed, no conditions)

No new Python dependencies for confirmed v1.2 features. The release CI workflow adds GitHub
Actions steps, not Python packages.

### Conditional (requires scope decision at requirements phase)

| Addition | Type | Condition | Pin |
|----------|------|-----------|-----|
| `segno` | Python (pip) | QR code bean sharing in scope | `>=1.6,<2` |
| Chart.js | Frontend CDN | Charts/data viz in scope | `4.4.9` pinned CDN URL |

### CI-Only Additions (not in requirements.txt)

| Action | Purpose |
|--------|---------|
| `docker/setup-qemu-action@v3` | QEMU for arm64 emulation |
| `docker/setup-buildx-action@v4` | Multi-platform buildx |
| `docker/login-action@v3` | GHCR auth via GITHUB_TOKEN |
| `docker/metadata-action@v5` | Semver tag generation |
| `docker/build-push-action@v6` | Multi-platform build + push |

---

## 4. Do Not Add (Explicit Rejection List)

| Rejected | Reason |
|----------|--------|
| LangChain / LlamaIndex | No RAG, no agent orchestration, no local models. Existing SDK abstractions are sufficient. Would bloat the image by 200MB+ |
| sentence-transformers / pgvector / any vector store | No embedding-based search needed. Trigram FTS already ships. |
| Any new AI SDK | anthropic + openai already cover both providers. |
| Docker Hub | Pull-rate limits hurt self-hosters; GHCR is free and auth-integrated with GitHub. |
| Native arm64 GitHub Actions runner | Free tier is amd64-only; QEMU emulation is sufficient for release cadence. |
| Redis | No use case warrants a third container at household scale. |
| Celery / RQ / separate worker | Single-process APScheduler is a locked invariant. |
| ZXing / jsQR (JS barcode scanner) | iOS Safari lacks BarcodeDetector API; native camera handles QR scans. |
| D3.js | Overkill for the charting scope here; Chart.js CDN is sufficient and far simpler. |
| ApexCharts / Recharts | Require npm build step; violates no-build-pipeline invariant. |
| workbox / vite-plugin-pwa | npm dependency; violates no-build-pipeline invariant. |
| bleach | Deprecated (Mozilla EOL). No HTML sanitization scope in v1.2. |
| qrcode (python-qrcode) as primary | If QR is in scope, prefer segno (lighter, native SVG). Exception: use qrcode if PNG raster output is specifically required. |
| SSE streaming for AI responses | Listed as deferred in PROJECT.md. Can fold in if cheap during AI page rework; assess at requirements. Not a new library — sse-starlette is already in the v1.1 stack doc as a gap library. |

---

## 5. Version Compatibility (Conditional Additions)

| Addition | Compatible With | Integration Notes |
|----------|-----------------|-------------------|
| Chart.js 4.x CDN | HTMX 2.x, Alpine.js 3.x, nonce-CSP | Init in `<script nonce="{{ nonce }}">` block; pass data as server-rendered JSON |
| segno 1.6.x | Python 3.12, no C extensions | No Pillow dependency; pure Python; serve as SVG response or base64 data URI |

---

## Sources

- [GitHub Container Registry docs](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) — free tier, pull limits, GITHUB_TOKEN auth (HIGH)
- [Docker Multi-Platform GitHub Actions docs](https://docs.docker.com/build/ci/github-actions/multi-platform/) — QEMU vs native runner tradeoffs, workflow YAML (HIGH)
- [docker/metadata-action](https://github.com/docker/metadata-action) — semver tag generation patterns (HIGH)
- [Beanconqueror features](https://beanconqueror.gitbook.io/beanconqueror/features/most-important-features) — feature inventory for parity assessment (MEDIUM)
- [segno on PyPI](https://pypi.org/project/segno/) — version, capabilities, pure-Python status (HIGH)
- [Chart.js GitHub releases](https://github.com/chartjs/Chart.js/releases) — 4.4.x current stable (HIGH)
- Docker image tagging best practices — multiple community + Docker official sources (MEDIUM)

---

*Stack research for: Snobbery v1.2 Polish & Mobile-First — new-feature stack additions only*
*Researched: 2026-05-25*
