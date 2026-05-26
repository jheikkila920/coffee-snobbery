# Requirements: Snobbery v1.2 — Polish & Mobile-First

**Defined:** 2026-05-25
**Core Value:** A returning user can log a brew in under 30 seconds and trust that the home page's "what to buy next" recommendation is grounded in their actual log, not generic taste advice. (Note: v1.2 may relocate the recommendation to the new AI page; the Core Value wording is revisited during UI design.)

REQ-IDs use v1.2-specific category prefixes. v1.1 requirements are archived in `milestones/v1.1-REQUIREMENTS.md`.

## v1.2 Requirements

### Debt Cleanup (DEBT)

Carried v1.1 debt, folded in early so new work sits on a clean base.

- [x] **DEBT-01**: A new operator's first deploy can write backups and photos with no manual `chown` (G-01 fixed via runtime `chown -R app:app /app/data` in `entrypoint.sh` before dropping to the app user)
- [x] **DEBT-02**: The full `pytest tests/` suite runs green twice in a row with no cross-module isolation failures (T-INFRA-1: catalog-table teardown + settings-cache clear in root conftest)
- [x] **DEBT-03**: Every authenticated page shows persistent nav with user identity and a working sign-out (verify/close the Phase 11 gap)
- [x] **DEBT-04**: Outstanding v1.1 human-UAT scenarios are executed and recorded (Phases 01/02/07/11 + the Phase 14 375px search-sheet UAT)
- [x] **DEBT-05**: Outstanding `human_needed` verifications (Phases 01/02/07/09/10/11) are resolved or explicitly re-deferred with a reason

### Self-Host Distribution (DIST)

Make Snobbery cleanly runnable by other households on their own VPS.

- [ ] **DIST-01**: An operator can deploy with no `docker compose build` step (compose references a published `image:`)
- [ ] **DIST-02**: A versioned multi-arch (amd64 + arm64) image is published to GHCR by a release CI workflow triggered on a version tag
- [ ] **DIST-03**: The README gives a complete from-zero self-host walkthrough (prerequisites, env vars, first run, upgrade)
- [ ] **DIST-04**: The deploy doc includes step-by-step Nginx Proxy Manager setup (proxy host to `coffee-snobbery:8000`, `TRUSTED_PROXY_IPS`, shared docker network)
- [ ] **DIST-05**: A fresh install boots cleanly: migrations auto-run on first start and the operator lands on `/setup` to create the first admin
- [ ] **DIST-06**: `.env.example` documents every required env var with generation hints for secrets (`APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`)
- [ ] **DIST-07**: The first-run flow guides the new admin to configure AI API keys after `/setup` (an inline key-entry step or a clear pointer to the Admin page, since admin no longer lives on the bottom nav)

### Information Architecture (IA)

Restructure navigation so AI gets a home and admin gets out of the way. Exact placement of the "what to buy next" recommendation (home vs AI page) is resolved during UI design.

- [ ] **IA-01**: Admin is reachable from a button on the config page (under Flavor Notes), not the bottom nav
- [ ] **IA-02**: A new AI destination is present in the bottom nav (replacing the admin slot)
- [ ] **IA-03**: AI surfaces (coffee recommendation, equipment callout, sweet-spots prose) are consolidated onto the AI page and removed from other pages
- [ ] **IA-04**: The home page is simplified to primary action affordances (e.g. rate a coffee, log a session, top coffees, wishlist)
- [ ] **IA-05**: Nav and asset changes reach installed PWAs without a manual cache clear (cache-bust verified after deploy)

### Cafe Quick-Rate (CAFE)

Log coffees tasted away from home (cafes, travel) without a recipe. Cafe ratings DO shape taste preferences and AI; only brew-parameter sweet-spots exclude them (they have no recipe/grind data). Data model finalized at plan-phase; a separate `cafe_logs` table whose ratings/flavor/origin are unioned into the preference + signature queries is the leading approach. This deliberately refines the research default, which kept cafe logs fully out of analytics.

- [ ] **CAFE-01**: User can log a coffee they did not brew with just a name and a rating in roughly 20 seconds
- [ ] **CAFE-02**: User can optionally add brand/roaster, origin, brew method, notes, flavor notes, and a photo to a cafe log
- [ ] **CAFE-03**: Cafe logs are per-user and listed/viewable, visually distinct from brew sessions
- [ ] **CAFE-04**: Cafe-log ratings, flavor notes, and origin/roaster feed preference derivation and the AI input signature, so they influence "what to buy next" and predicted ratings
- [ ] **CAFE-05**: Cafe logs are excluded only from brew-parameter sweet-spots analytics (grind, ratio, temperature, recipe), which they have no data for
- [ ] **CAFE-06**: User can edit and delete their own cafe logs

### AI Page & Research/Predict (AIX)

The differentiator. A dedicated AI page hosting the consolidated recommendations plus a new on-demand "research a coffee and predict my rating" flow, with cost controls that are non-negotiable.

- [ ] **AIX-01**: User can type a coffee name and get an AI-researched profile (origin, roaster, tasting notes) grounded in web search with cited sources
- [ ] **AIX-02**: The AI predicts how the user would rate that coffee as a range with a confidence level and visible reasoning, never a single point estimate
- [ ] **AIX-03**: AI research/predict is gated by the existing cold-start threshold (>=3 sessions and >=5 distinct flavor notes)
- [ ] **AIX-04**: Repeat lookups of the same coffee are served from a cache (TTL) to avoid redundant web-search cost
- [ ] **AIX-05**: AI research/predict is rate-limited per user per day, with remaining quota visible to the user
- [ ] **AIX-06**: User can add a researched coffee to the wishlist directly from the result
- [ ] **AIX-07**: AI responses on the AI page stream to the user (SSE) instead of polling
- [ ] **AIX-08**: When a user meets the cold-start threshold but no AI API key is configured, the AI page shows a prominent button/banner linking to the Admin page to add a key (distinct from the not-enough-data empty state)

### Guided Brew & Brew Data (GBREW)

Make Guided Brew feel like a purpose-built mobile brewing coach, plus the brew-data additions from the Beanconqueror audit.

- [ ] **GBREW-01**: The Guided Brew timer keeps running when the phone screen sleeps at the kettle (background-safe)
- [ ] **GBREW-02**: Guided Brew steps through recipe phases (bloom, pours) as timed, coached steps
- [ ] **GBREW-03**: User can optionally record first-drip time and bloom time on a brew session
- [ ] **GBREW-04**: User selects water type from a managed water-profiles catalog (named profiles) instead of freetext
- [ ] **GBREW-05**: Guided Brew Mode meets the purpose-built mobile polish bar end to end

### Mobile-First Polish (MOBILE)

A screen-by-screen audit and rework on the working v1.1 base so the whole app feels like a released product. Desktop is <=5% of use.

- [ ] **MOBILE-01**: Every screen is audited and reworked at 375px with no horizontal scroll and correct bottom (<768px) / top (>=768px) nav behavior
- [ ] **MOBILE-02**: All interactive controls meet touch-target sizing and 16px input-font minimums (no iOS zoom-on-focus)
- [ ] **MOBILE-03**: Safe-area insets are correct on iOS PWA standalone, verified on a physical device, across all screens (re-verify the unproven `982c0e6` fix before propagating it)
- [ ] **MOBILE-04**: Form actions stay reachable above the bottom nav on long forms
- [ ] **MOBILE-05**: The app presents a consistent, purpose-built visual polish bar across every page (the "major-company feel")

### Data Visualization (VIZ)

- [ ] **VIZ-01**: Brew/preference trends are presented with charts (e.g. rating over time, flavor distribution) using a CSP-compatible chart library (Chart.js via CDN)

## Future / Deferred Requirements

Tracked, not in this milestone's roadmap.

### Inventory & Offline

- **INV-01**: Bag inventory management (count, depletion, low-stock alerts) — re-evaluated against Beanconqueror audit, deferred to v2
- **OFF-01**: PWA offline write queue + background sync — deferred from v1, still v2

### AI

- **AIF-01**: Per-user/month AI cost ceiling — revisit only if on-demand research/predict cost surprises (per-user/day rate limit + cache ship in v1.2 as the control)
- **AIF-02**: Prediction-accuracy tracking ("did the predicted rating hold up?") — depends on the AIX prediction-storage choice; future

### Multi-User

- **MU-01**: Public/hosted multi-user (signup link, isolated per-user data, hundreds of users) — a v2.0 product pivot; see Out of Scope

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Public/hosted multi-user, public signup, isolated per-user databases | Breaks the single-worker, shared-catalog, no-email, and household-scale cost invariants. A v2.0 pivot, not a polish milestone. |
| BLE scale integration / flow profiling | Weeks of device-specific work; out of domain for a pour-over household app |
| QR / NFC bean sharing | Anti-social; no other Snobbery instances exist to share to; counter to the private-household identity |
| SCA cupping scoresheet | Professional workflow that competes with the existing simpler rating model |
| Roasting / green-coffee section | Out of domain |
| Point-estimate AI rating ("you'll rate this 4.2") | Trust anti-pattern; v1.2 uses range + confidence + reasoning instead |
| Social brew-card sharing / public profiles | Counter to the snobbery, private-household identity |

## Traceability

Every v1.2 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 15 | Complete |
| DEBT-02 | Phase 15 | Complete |
| DEBT-03 | Phase 15 | Complete |
| DEBT-04 | Phase 15 | Complete |
| DEBT-05 | Phase 15 | Complete |
| DIST-01 | Phase 18 | Pending |
| DIST-02 | Phase 18 | Pending |
| DIST-03 | Phase 18 | Pending |
| DIST-04 | Phase 18 | Pending |
| DIST-05 | Phase 18 | Pending |
| DIST-06 | Phase 18 | Pending |
| DIST-07 | Phase 17 | Pending |
| IA-01 | Phase 17 | Pending |
| IA-02 | Phase 17 | Pending |
| IA-03 | Phase 17 | Pending |
| IA-04 | Phase 17 | Pending |
| IA-05 | Phase 17 | Pending |
| CAFE-01 | Phase 16 | Pending |
| CAFE-02 | Phase 16 | Pending |
| CAFE-03 | Phase 16 | Pending |
| CAFE-04 | Phase 16 | Pending |
| CAFE-05 | Phase 16 | Pending |
| CAFE-06 | Phase 16 | Pending |
| AIX-01 | Phase 19 | Pending |
| AIX-02 | Phase 19 | Pending |
| AIX-03 | Phase 19 | Pending |
| AIX-04 | Phase 19 | Pending |
| AIX-05 | Phase 19 | Pending |
| AIX-06 | Phase 19 | Pending |
| AIX-07 | Phase 19 | Pending |
| AIX-08 | Phase 17 | Pending |
| GBREW-01 | Phase 20 | Pending |
| GBREW-02 | Phase 20 | Pending |
| GBREW-03 | Phase 20 | Pending |
| GBREW-04 | Phase 20 | Pending |
| GBREW-05 | Phase 20 | Pending |
| MOBILE-01 | Phase 21 | Pending |
| MOBILE-02 | Phase 21 | Pending |
| MOBILE-03 | Phase 21 | Pending |
| MOBILE-04 | Phase 21 | Pending |
| MOBILE-05 | Phase 21 | Pending |
| VIZ-01 | Phase 19 | Pending |

**Coverage:**
- v1.2 requirements: 42 total (DEBT 5, DIST 7, IA 5, CAFE 6, AIX 8, GBREW 5, MOBILE 5, VIZ 1)
- Mapped to phases: 42/42 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-25*
*Last updated: 2026-05-25 — traceability table populated by roadmapper (phases 15–22)*
