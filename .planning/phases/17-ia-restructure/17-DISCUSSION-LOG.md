# Phase 17: IA Restructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-27
**Phase:** 17-ia-restructure
**Areas discussed:** Nav slot composition + labels, Home composition after AI leaves, AI page shell scope, Admin entry + key-setup prompts

---

## Nav slot composition + labels

### Slot order

| Option | Description | Selected |
|--------|-------------|----------|
| Home / Log / AI / Config | AI sits with daily-use tabs; Config rightmost as less-frequent destination | ✓ |
| Home / Log / Config / AI | Keeps Config in slot 3; AI takes the old Admin rightmost slot | |
| AI / Home / Log / Config | AI leftmost — strongest signal it's a first-class destination | |

**User's choice:** Home / Log / AI / Config

### AI label

| Option | Description | Selected |
|--------|-------------|----------|
| AI | Matches REQUIREMENTS/ROADMAP wording; 3-letter label fits at 375px | ✓ |
| Insights | Avoids the 'AI' branding; broader analytics+intelligence frame | |
| Coach | Frames as recommendation/coaching surface; departs from spec wording | |

**User's choice:** AI

### Tab gate

| Option | Description | Selected |
|--------|-------------|----------|
| Always visible to every authenticated user | Discovery beats hiding; page renders the right state per gate | ✓ |
| Gated on cold-start | Hide tab until enough data; user might not know AI exists | |
| Gated on AI key configured | Hide until admin saves key; non-admins never see it in no-key household | |

**User's choice:** Always visible

### Tab rename

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 'Config' | More accurate now that Admin lives under it; zero churn | ✓ |
| Rename tab to 'Catalog' | Tab matches page title; Admin becomes a subtle entry under catalog grid | |
| Rename tab to 'Settings' | Cleaner mental model; bigger change | |

**User's choice:** Keep 'Config'

**Closing check:** User chose "Next area" — slot order, label, gating, rename are enough; planner picks the icon.

---

## Home composition after AI leaves

### Home shape

| Option | Description | Selected |
|--------|-------------|----------|
| Action buttons + Recent brews + Not tried yet + Top Coffees | Strict "primary action affordances + lightweight recency" | ✓ |
| Action buttons + Recent brews + Top Coffees only | Drop Not tried yet for max simplicity | |
| Keep all non-AI analytics on home | Only AI hero + AI tools move; weakest IA-04 read | |

**User's choice:** Action buttons + Recent brews + Not tried yet + Top Coffees

### Top Coffees eagerness

| Option | Description | Selected |
|--------|-------------|----------|
| Eager render like Recent brews | 3 eager + 1 lazy on home; faster first paint | ✓ |
| Keep Top Coffees lazy-loaded | Match current pattern; one less migration | |

**User's choice:** Eager render

### Action row

| Option | Description | Selected |
|--------|-------------|----------|
| Guided Brew + Log session + Quick rate | Symmetric with /brew page header (Phase 16 D-09) | ✓ |
| Guided Brew + Log session only | Two big buttons; cleaner mobile look | |
| Log session + Quick rate (Guided Brew demoted) | Frees home for the two most-frequent actions | |

**User's choice:** Guided Brew + Log session + Quick rate

### AI pointer from home

| Option | Description | Selected |
|--------|-------------|----------|
| No pointer — bottom-nav AI tab is the only discovery path | Cleanest IA-04 read; no duplicate affordance | |
| Small link under Top Coffees ('See AI recommendations →') | Discovery breadcrumb for home-defaulters; slight clutter | ✓ |
| Banner above Recent brews when fresh AI rec exists | Surface only when fresh content; new 'unseen rec' state | |

**User's choice:** Small link under Top Coffees

**Closing check 1:** User chose "More questions" — wanted cold-start meter + AI tools placement locked.

### Cold-start meter destination

| Option | Description | Selected |
|--------|-------------|----------|
| On the AI page only | Home stays clean for both gated and ungated users | ✓ |
| On home only | Pulls an AI surface back onto home — weak IA-03 read | |
| On both home and AI page | Maximum discovery; mild duplication to sync | |

**User's choice:** On the AI page only

### AI tools placement

| Option | Description | Selected |
|--------|-------------|----------|
| All move to AI page | Strict IA-03 consolidation | |
| Wishlist stays on home, AI tools move to AI page | Wishlist is read-only data the user added; tools are AI-generated | ✓ |
| All stay on home | Defeats IA-03 | |

**User's choice:** Wishlist stays on home, AI tools move to AI page

### Not tried cap

| Option | Description | Selected |
|--------|-------------|----------|
| Keep current behavior | Lowest risk for IA-only phase; Phase 21 revisits | ✓ |
| Cap at top 5 | Symmetric with Top Coffees IA-06 | |
| Cap at top 10 | More content; still bounded | |

**User's choice:** Keep current behavior

### Home title

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 'Home' | Matches bottom-nav label; zero churn | |
| Drop the h1 entirely | Mobile real estate; wordmark identifies the app | |
| Personalize ('Good morning, {{user.username}}') | Adds warmth; time-of-day logic | ✓ |

**User's choice:** Personalize — diverges from the recommended option; small scope addition explicitly accepted.

**Closing check 2:** User chose "Next area" — composition locked.

---

## AI page shell scope

### Shell scope

| Option | Description | Selected |
|--------|-------------|----------|
| Real content + 'Coming soon' section for Phase 19 | Genuinely useful page at end of Phase 17 | ✓ |
| Just an empty 'AI — coming soon in Phase 19' page | Minimal scope; home stays AI-heavy (weak IA-03) | |
| Move ALL existing AI surfaces now (incl. paste-rank + wishlist routes) | Bigger churn for marginal benefit | |

**User's choice:** Real content + 'Coming soon' section

### AI route

| Option | Description | Selected |
|--------|-------------|----------|
| /ai | Short; matches tab label; existing /ai/* routes natural | ✓ |
| /recommendations | Descriptive; breaks parallelism with /ai/* prefix | |
| /insights | Mismatch with 'AI' nav label | |

**User's choice:** /ai

### Sub-pages

| Option | Description | Selected |
|--------|-------------|----------|
| Stay as separate pages, linked from /ai | Minimum disruption; /ai shows hero + tool launchers | |
| Inline both into /ai as expandable sections | Single-scroll /ai page; bigger refactor risk | ✓ (initial; reversed below) |
| Move only Wishlist inline; paste-rank stays separate | Mixed cognitive model | |

**User's choice (initial):** Inline both into /ai as expandable sections
**User's choice (reconciled after Wishlist conflict):** Wishlist stays on home only and is NOT inlined into /ai. paste-rank and equipment are AI tools on /ai (links to /ai/paste-rank existing page; /ai/equipment POSTed inline). See reconciliation question below.

### Cold state

| Option | Description | Selected |
|--------|-------------|----------|
| Cold-start meter + 'why' explainer + link back to /brew/new | Reuses existing fragment; clear next step | ✓ |
| Just the meter (no CTA or explainer) | Minimal; less helpful | |
| Friendly hero illustration + meter + CTA | Out of scope for IA-only phase | |

**User's choice:** Meter + explainer + CTA

### Wishlist reconciliation (cross-area)

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — both surfaces (home link + /ai inlined) | Mild duplication for discoverability | |
| Only /ai — remove from home | Stronger IA-03; reverses earlier home decision | |
| Only home — don't inline in /ai | Reverses this area's inline decision | ✓ |

**User's choice:** Only home — Wishlist on home only, NOT inlined into /ai. (Reverses the "Inline both" answer from the Sub-pages question above. CONTEXT.md captures the reconciled state.)

**Closing check:** User chose "Next area" — shell scope clear.

---

## Admin entry + key-setup prompts

### Admin entry

| Option | Description | Selected |
|--------|-------------|----------|
| Top-right action button on Config page header | Mirrors home's action button pattern; admin-gated | |
| Card in the catalog grid | Mixes shared catalog with admin function — weak fit | |
| Dedicated section below the catalog grid, before mobile sign-out | Visually separated; same card shape as catalog grid | ✓ |

**User's choice:** Dedicated section below the catalog grid

### Setup nudge

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent in-page banner on home + /ai until a key is saved | Admin-gated; session-dismissable but reappears | ✓ |
| Forced wizard step after /setup (interstitial /setup/keys) | Strongest funneling but breaks 'just sign in' flow | |
| Banner only on AI page | Lower friction; less proactive | |

**User's choice:** Persistent in-page banner on home + /ai

### AIX-08 state

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct callout card with different copy + 'Go to Admin' button | Different headline, icon, and primary button vs cold-start | ✓ |
| Same card layout as cold-start, with different headline text | Visually similar enough to confuse | |
| Full-page takeover ('Set up AI' splash) | Out of proportion for IA phase | |

**User's choice:** Distinct callout card

### Non-admin no-key state

| Option | Description | Selected |
|--------|-------------|----------|
| 'AI is not set up. Ask the household admin to configure an API key.' — no Admin link | Honest, scoped to permission; names the social action | ✓ |
| Same callout but button says 'Notify admin' (no-op v1) | Misleading affordance | |
| Hide the AIX-08 distinction; just show 'not enough data' | Dishonest UX | |

**User's choice:** Honest 'ask admin' copy, no Admin link, no 'Notify admin' button

**Closing check:** User chose "Done with this area" — all four items locked.

---

## Final wrap-up

**Question:** We've discussed all four areas. Anything still unclear?
**User's choice:** I'm ready for context

---

## Claude's Discretion

Areas where the user accepted Claude / planner's call:
- AI tab icon (specific SVG shape) — match existing 24×24 stroke-currentColor icon style
- Time-of-day greeting cutoff boundaries for the personalized home h1 (D-10)
- Whether `/home/cards/*` endpoints rename to `/ai/cards/*` or just get re-mounted from the new template (D-12 area)
- Whether the cold-start fragment moves to `fragments/ai/_cold_start.html` or stays at its current path and is just included from the new page (D-14 area)
- DIST-07 banner template path naming
- Whether to keep or drop the desktop top-nav Admin link (D-18 — kept for now; flag at plan review for user re-confirmation)
- Endpoint vs router placement for `GET /ai` (in existing `app/routers/ai.py` or a new `ai_page.py` module)
- Whether the Admin entry card on Config has a small "Admin only" badge in addition to the `is_admin` template gate

## Deferred Ideas

- Cap on 'Not tried yet' list (Phase 21 mobile rework)
- Pure-removal of the home `<h1>` (Phase 21)
- Banner above Recent brews when fresh AI rec exists (Phase 19 if warranted)
- Forced /setup/keys interstitial (revisit only if banner data shows admins ignore it)
- Inline Wishlist as expandable section on `/ai` (rejected; on home only)
- 'Notify admin' affordance for non-admin no-key state (needs a notification system; out of scope)
- Renaming Config tab to 'Catalog' or 'Settings' (rejected; zero churn beats minor wording change)
- Hiding AI tab when gate closed or no key (rejected; discovery beats hiding)
- Removing the desktop top-nav Admin link (deferred to plan-review user re-confirmation)
- AI page visual polish to 'major-company bar' (Phase 21)
- Renaming `/home/cards/*` endpoints to `/ai/cards/*` (left to planner)
- Charts / data viz on AI page (Phase 19 — VIZ-01)
- AI research-a-coffee, predict-rating, SSE streaming, in-depth preference prose, equipment-rec rewrite, AIX-09..13 (all Phase 19)
