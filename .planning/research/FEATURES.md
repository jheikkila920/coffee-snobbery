# Feature Landscape: Snobbery

**Domain:** Phone-first self-hosted household coffee log for serious pour-over enthusiasts (multiple brews per day)
**Researched:** 2026-05-16
**Source posture:** Spec (`snobbery-gsd-prompt.md`) cross-checked against shipping competitors — Beanconqueror, Filtru, Bloom, Brewd, iBrewCoffee, BeanBook, Extraction, Tasting Grounds, Brew Logs, Coffee Book, Press, Angels' Cup, Fellow Aiden, Trade Coffee, Crema. Goal: surface gaps and UX traps, not restate spec.

---

## 1. Table Stakes — Covered by Spec (with UX traps to defuse)

| Feature | UX trap | Mitigation |
|---|---|---|
| Add brew session form (12+ fields) | "Too many fields" is the #1 cited reason competitors get abandoned (Press, BeanBook reviews). Single-scroll-with-prefill is the right call — but only if prefill is visibly indicated. | Show prefilled values as muted/ghost text or with a "from last brew" pill so the user trusts what's there and only edits deltas. Otherwise users re-type everything "to be safe" and rage-quit. |
| Roaster + flavor note autocomplete with create-on-save | Mobile keyboards aggressively autocorrect — "Onyx" becomes "Onyx Coffee Roasters" or "onyx" (lowercase) before user notices. Creates fragmentation in the very table you're trying to dedupe. | Case-insensitive match (citext is in spec — good). Also: when a new entry is about to be created, prompt "Add 'onyx coffee' as a new roaster?" instead of silent-creating. The spec's "type new value creates on save" is the trap door if there's no confirmation. |
| Tag input for flavor notes (comma/enter to commit) | Mobile-keyboard comma is buried two layers deep on iOS. "Enter" inserts a newline in some browsers if the input is a textarea. | Use a single-line input, commit on `enter` AND `space-after-comma`, AND tap-to-add from autocomplete suggestion chips. Make sure the keyboard has a visible "Done" key. |
| Photo upload with `capture="environment"` + client-side downscale | iOS Safari ignores `capture` if the file input is hidden via CSS in some HTMX swap orders. EXIF orientation handling — if you downscale via Canvas you'll silently rotate landscape photos on some Android devices. | Test on iOS 17/18 Safari standalone PWA mode (different from in-Safari). Read EXIF orientation before drawing to canvas; bake rotation in. Spec already says strip EXIF — strip *after* baking. |
| Rating 0–5 in 0.25 steps, thumb-operable | Slider with 21 discrete steps is hard to land on a thumb. Star-with-quarter-fills is visually noisy. | Recommend hybrid: large tap-on-star (full + half) for fast input + a "+/- 0.25" nudge for power users. Quarters are a power-user need; defaulting to halves is fine for 90% of brews. |
| LocalStorage draft persistence | **Critical iOS trap**: WebKit ITP clears localStorage after 7 days of no interaction with the site. For an installed PWA, the timer resets on each launch, so this is mostly OK *if installed*. In-browser users will lose drafts. Also: localStorage is cleared when iOS device runs low on storage. | Two safeguards: (1) save draft to server on input blur for logged-in users (small POST every 2–3s debounced); (2) only show "we restored your draft" prompt — don't silently overwrite a fresh form, because users will think the form is broken. |
| Guided Brew Mode wake lock | **Critical iOS trap**: Wake Lock API works in Safari 16.4+ in-browser, but until very recently was broken in installed PWAs (WebKit bug 254545). | Detect support, fall back to: a) keep a silent audio loop playing (legacy iOS wake-lock hack), or b) NoSleep.js. At minimum, warn user "screen may sleep on your device" with a settings toggle to disable auto-lock. Do NOT assume wake lock works. |
| Quick re-log ("Brew again") | Spec is correct — this is the highest-frequency action when working through a bag (mirrors iBrewCoffee's "duplicate" and Coffee Book's long-press-clone). Trap: which fields to clear vs keep is opinionated. Spec gets it right (clear rating/notes/observed flavor; keep everything else). | Protect this scope — don't let scope creep add a "smart re-log" that tries to vary one parameter. Keep it dumb and fast. |
| Days-off-roast computed at query time | Spec gets this right (not stored). Trap: if `roast_date` is null, UI must show "—" cleanly, not "NaN days" or "since the dawn of time". | Render `roast_date` as required when adding a coffee but nullable in schema (so user can save and come back). Show a yellow nudge on coffee detail page if missing. |
| Sweet spots (origin × process × brewer × recipe) | Trap: with 2 users × <50 sessions, GROUP BY HAVING min_sessions=3 will return empty for weeks. Empty state will dominate the home page early. | Show a progress meter: "You've logged 12 sessions across 4 origins. Sweet spots unlock with 3+ sessions per combination." Don't just show "no data". |
| Global search | Trap: live search on every keystroke (even debounced 250ms) hammers the DB and feels janky on a 3G phone. Spec is reasonable but watch for trigram index bloat at scale. | Don't query for <3 characters. Return only top 5 per entity type. |
| Nightly AI regen via signature hash | Trap: signature based only on `brew_session_count + max(updated_at) + equipment/recipe counts` misses the case where a user *edits* a session (rating change) — `updated_at` catches it, good. But misses: if they archive a coffee, signature doesn't change. | Add `coffees_archived_count` or `coffees_active_count` to the signature. Otherwise a recently archived coffee can still be re-recommended. |

---

## 2. Table Stakes — Missing from Spec

| Feature | Why it matters for this audience | Complexity | Fit for v1? |
|---|---|---|---|
| **Bag-as-instance separate from coffee-as-catalog** | The spec models a "coffee" as one row. In practice, John reorders the same Onyx Geometry bean 3 times a year; each bag has a different roast date, possibly a different lot. Today the spec would force editing the single coffee row's `roast_date` each time, losing history. Beanconqueror, Extraction, BeanBook all model bag-instances separately. | **Medium** — add `bags` (FK coffee, roast_date, weight_grams_remaining, opened_at, finished_at). Brew session FKs to `bag_id` instead of (or in addition to) `coffee_id`. | **Yes, v1.** This is a foundational data-model decision; retrofitting later is a migration headache. Without it, sweet-spots-by-roast-date is unreliable. |
| **"Want to try" / wishlist** | The home page shows AI coffee recommendations — but where does the user *put* a recommendation they want to remember without ordering today? Trade Coffee, Crema, Angels' Cup all have this. Without it, the AI rec card has nowhere to land. | **Low** — boolean on `coffees` plus a `wishlist_entries` table for things not yet in catalog (just URL + note). | **Yes, v1.** Pairs directly with the AI flow; without it the AI rec is a dead end. |
| **Bag depletion / "this bag is done"** | Spec has `archived` on coffees but no concept of "this bag is empty, archive the bag instance, leave the coffee row alive for future re-orders". Closely tied to bag-as-instance above. | **Low** if bags table exists. **High** if not — you end up archiving the coffee then un-archiving it on reorder. | **Yes, v1**, follows from bag-as-instance. |
| **Brew ratio displayed live in the form** | Spec captures dose + water grams but doesn't compute ratio (1:16) in the UI. This is the #1 number pour-over enthusiasts care about; every competitor app shows it live. Spec hides it. | **Low** — Alpine.js reactive expression. | **Yes, v1.** Trivial add, big perceived value. |
| **Brew yield (cup-out weight) field** | Spec captures dose and water in, but not what came out the bottom. For pour-over the difference (retained liquid in slurry) and the yield ratio are key. Beanconqueror, Filtru, Bloom all capture yield. | **Low** — single nullable numeric column. | **Yes, v1.** |
| **TDS / extraction yield (optional field)** | Niche but real for "serious pour-over enthusiasts." If the user has a refractometer (VST, DiFluid R2, Atago), they will want to log TDS. Beanconqueror explicitly supports it; users have requested it across forums. Don't have to build a refractometer integration — just expose the field. | **Low** — two nullable numerics (`tds_pct`, optionally computed `extraction_yield_pct`). | **Yes, v1.** Cheap; signals the app understands the audience. |
| **Water recipe / mineral profile** | Spec has `water_type` as free text. Specialty pour-over crowd cares about water — Third Wave Water profiles, Lotus, custom mineral recipes. Free text is fine to start, but a `water_profiles` shared table (name + optional gh/kh/tds_ppm) is a one-table upgrade that lets sweet-spots include water as a dimension. | **Medium** — one new table, optional FK on brew session. | **No to full mineral profile in v1**, **yes to a `water_profiles` lookup table with just `name`** so it joins the autocomplete-shared-vocabulary pattern. Adds analytics value, almost zero cost. |
| **Grinder-setting reference per grinder** | Spec stores `grind_setting_actual` as free text on each session. "23 clicks" means nothing without knowing it was on a Comandante. Tasting Grounds and similar apps tie settings to a grinder reference. Since `grinder_id` is already captured per session, the grind setting context is implied — but a per-grinder default/reference (e.g. "Comandante C40 = clicks 0–40, V60 range 18–24") makes future cross-session comparison usable. | **Low** — two text fields on `equipment` rows of type=grinder: `grind_min`, `grind_max`. | **Maybe v1.5.** Helpful but not critical for two-person household. Defer. |
| **Cost per brew / "what did this cup cost"** | Spec captures `coffees.price_usd` and `weight_grams`. Combined with `dose_grams_actual` you can derive cost-per-brew. Multiple apps surface this — useful sanity check ("you've brewed $4.20 of Heart Coffee today"). | **Low** — derived field, no schema change. | **Yes, v1.** Cheap analytics win. |
| **Brew session edit history / "what changed"** | Spec has `updated_at` but no audit trail on session edits. With two users sharing a catalog and AI signature based on `max(updated_at)`, an inadvertent rating change by one user can silently trigger an AI regen. Not critical, but a per-session history table or a soft event log helps debug "why did the home page change?" | **Medium** — separate event log table. | **No, defer to v2.** Useful for postmortem; not v1 critical. |
| **Brew comparison view (A vs B)** | Power-user feature: pick two sessions side by side to spot what changed. Several competitors (Bloom, iBrewCoffee) have this. With <50 sessions this is overkill — when sessions count grows past a few hundred, becomes very useful. | **Medium** — new page, two-up template. | **No, defer to v1.5–v2.** |
| **Empty-state "Add 3 sample brew sessions" onboarding** | AI recs are gated at 3+ sessions. New user lands on a sparse home page with "log 3 brews to unlock." That's *correct* but harsh. Consider: import-from-CSV or a "Start with my last 5 brews" template that pre-fills realistic shapes for John & Farrah specifically. | **Low** — single seed form. | **Maybe v1.** John is initial user — he can manually backfill. But it's an obvious cliff. |
| **CSV import (mirror of CSV export)** | Spec has CSV export, no import. John may have a spreadsheet history. Import lets the AI work on day one. | **Medium** — schema mapping, dedup of coffees by name+roaster. | **Maybe v1.** Trivial if scope-limited to "import your prior brew sessions, refusing if coffee doesn't exist in catalog yet." Don't try to auto-create catalog entries from CSV — fragmentation risk. |
| **Two-tap "I'm brewing this now" from a coffee card** | Coffee card already exists; adding a "Brew this" button that jumps to the brew form with `coffee_id` prefilled is one button. Already implied by spec's flow but worth calling out as a deliberate addition because Home page "unrated coffees" should also expose it. | **Low** — link to `/log/new?coffee_id=X`. | **Yes, v1.** Pairs with "unrated coffees" feature. |
| **Notification when a roast hits its sweet window** | Extraction app's marquee feature: "peak alerts fire when a bean enters its sweet window." Spec has no notifications by design (no SMTP, no push). Push notifications via PWA are now possible on iOS 16.4+ but require server keys. | **High** — push infra, opt-in. | **No, v2.** Out of v1 scope; spec explicitly excludes email/notification plumbing. But worth flagging because users *will* ask for it. |
| **AI "why this rating" sanity check** | Subtle one: a user logs a 4.5 on Friday and a 2.0 on Saturday for the same coffee+recipe. The AI's profile will swing wildly. A gentle "your ratings for this coffee have varied a lot — is one of these an outlier?" nudge before the nightly run protects AI quality. | **Medium** — analytics query + non-AI prompt. | **No, defer.** Nice-to-have. |
| **Recipe versioning** | Spec: edit a recipe and all historical sessions still FK to it — but the recipe content has changed. Sweet-spots analysis silently becomes inaccurate. Brewfather solves this with recipe snapshots. | **Medium** — version column or copy-on-edit. | **No, v1**: instead, document the "edit recipe = rewrites history" trade-off, and encourage users to duplicate recipe rather than edit when iterating. Spec already has duplicate-recipe action — good. Just flag this convention in UI. |

---

## 3. Differentiators in Spec (protect from scope creep)

| Differentiator | Why it matters | What dilutes it |
|---|---|---|
| **Live AI coffee recommendation with verified product URL + tier-aware fallback** | This is the headline. Generic AI suggestions are commodity ("try a washed Ethiopian"); a *specific in-stock SKU at a roaster you've bought from before, with the URL HEAD-verified* is the moat. | Adding a "list of 5 alternatives" view dilutes the single-best-answer punch. Allowing AI to suggest a coffee not currently for sale ruins trust. Hide the temptation to make this a marketplace integration. |
| **Recipe suggestion drawn from user's existing recipe library, never invented** | This is the brilliant constraint. The AI is grounded — it can't hallucinate a recipe that doesn't exist in your kitchen. Builds trust. | Letting the AI "suggest a new recipe" if no existing match exists would re-introduce hallucination risk. The spec's "if no match, link to recipe builder" is correct. Protect it. |
| **Alternative-brewer callout (>0.5 rating delta)** | This is a real insight nobody else surfaces — your data shows you'd do better on the V60 than the Switch for this profile. Subtle, defensible. | Threshold-tuning over time should stay aggressive (≥0.5). Don't water it down to "0.2" or it becomes noise. |
| **Sweet spots (cross-dimensional SQL, no AI)** | Pure SQL on the user's own data, with optional AI prose narration. Competitors either don't surface multi-dimensional patterns at all, or do it as AI-only (less trustworthy, more expensive). | Don't replace the SQL with AI. Don't expand beyond `(origin × process × brewer × recipe)` — adding more dimensions makes empty-set the default for small datasets. |
| **Signature-based regen** | Cost control that's also a UX feature (stale badge). | Don't add a "manual regen daily quota" — the household scale makes this premature. Don't auto-regen on every page load. |
| **Mobile-first with bottom tab nav and aggressive prefill** | 90% phone usage assumption. Most competing web apps (vs native apps) feel desktop-first. | Don't ship "responsive desktop-first" templates because they were faster to build. The 375px viewport is the design target, not the fallback. |
| **Guided Brew Mode with wake lock + audio + haptic cues** | Differentiates from "log after the fact" apps. Active assistant during brewing. | Don't bury the entry point. Should be a prominent button on the recipe page and the brew-session form, not three taps deep. |
| **Shared catalog + per-user logs in a single deployment** | Most apps are either fully shared (community) or fully personal. The household model is genuinely underserved. | Don't add a "make this coffee private" toggle — undermines the shared catalog premise. The spec's design (catalog shared, sessions private) is right. |
| **Self-aware "snobbery" tone in empty states** | Brand differentiation in a sea of beige coffee apps. | Don't make every UI string a joke. Tone lives in empty states and confirmations, not in field labels or error messages. |

---

## 4. Anti-Features (do not build, with reasoning)

| Anti-feature | Why not | Industry pressure to re-include |
|---|---|---|
| **Public social feed / community sharing** | Spec already excludes; protect it. Tasting Grounds, CafeConnections, Angels' Cup all built social and it adds noise without depth. The "snobbery" tone is *because* it's a private household tool. | Strong industry pressure — every competitor adds social eventually. Stay disciplined. |
| **Gamification (streaks, badges, "you brewed 7 days in a row")** | Coffee enthusiasts are *not* an audience that needs nudging. The brew log is the reward. Streaks specifically punish travel / illness / a weekend off — exactly the wrong incentive. | Moderate pressure — every consumer app has this. Resist. |
| **Coffee shop / cafe finder integration** | Spec excludes; protect it. Out of domain; brings in mapping infra, scraping, and a "your reviews of cafes" data model. | Low pressure; clearly out of scope. |
| **Decent Espresso / Acaia / Felicita BLE scale integration** | Spec doesn't mention; correct to exclude. Beanconqueror invested heavily here, it's a long tail of device support, and pour-over weights are slow enough to enter manually. Espresso is where BLE actually pays off. | Moderate pressure — power users will ask. Answer: out of scope; this is a log, not a brewing platform. |
| **AI-written tasting notes (auto-generate "this coffee tastes like…")** | Tempting because AI is cheap text. But the *point* of the log is the user's own palate development. Auto-generated notes train the user to trust the AI rather than their tongue. | High pressure — AI feature creep is rampant. Resist; the AI's job is to recommend bean-buying and brewer-pairing, not to taste for you. |
| **Continuous live BLE scale streaming to graph pour profile** | Beanconqueror does this; it's cool. It's also weeks of work for one feature, and most pour-over users don't have BLE scales. | Low immediate pressure; flag for v3 conversation. |
| **"Coffee score" composite metric** | Some apps compute a single "Coffee Index" out of multiple dimensions. It collapses information and feels reductive — the rating + flavor notes + sweet spots already capture this. | Low pressure. |
| **Public profile / username sharing** | Spec excludes. Household scope makes this an anti-pattern. | Low pressure. |
| **"Discover new roasters" curated feed** | The live AI recommendation IS this feature, but personalized. A curated feed competes with it and dilutes the AI as the source of truth for "what next." | Moderate pressure (sounds nice). Resist. |
| **Auto-detect bean from photo (OCR roaster bag)** | Slick demo; flaky in practice. Tasting Grounds and Beanconqueror have experimented. Bag designs vary wildly, OCR fails on textured paper, and the time saved (one form, two minutes per bag) doesn't justify the brittleness. | Moderate pressure (every "AI app" demo has this). Resist for v1; revisit only if AI OCR materially improves and the household catalog grows past 50 coffees. |
| **Subscription billing / tiered pro features** | Self-hosted, household, no revenue model. Spec excludes. | Low pressure for self-hosted. |

---

## 5. Closing Assessment

The spec's feature scope is **right-sized for v1 in volume but has three foundational gaps** that will hurt if deferred:

1. **Bag-as-instance vs coffee-as-catalog** — biggest single gap. Without it, `roast_date` lives on the coffee row and every reorder loses the prior bag's date. Sweet-spots-by-freshness becomes unreliable as soon as a coffee is reordered. Cheap to add now, expensive to retrofit once there are 500 sessions. **Strongly recommend adding to v1.**

2. **Brew yield + ratio display + optional TDS** — these are the difference between "a log" and "a log for serious pour-over people." All three are cheap (1 column, 1 reactive expression, 2 columns). Signal that the app knows its audience.

3. **Wishlist / "want to try"** — the AI recommendation card has nowhere to land. Without a wishlist, the AI feature is suggest-and-forget; with it, the AI flow becomes a closing-the-loop ritual.

Everything else (comparison view, recipe versioning, BLE scales, push notifications) is genuinely fine to defer. The spec correctly resists feature creep on the high-pressure-but-low-value items (social, gamification, cafe finder). The differentiators (live AI coffee rec, alternative-brewer callout, sweet spots, signature-based regen) are well-protected by the explicit Out of Scope list — keep that list aggressive at every phase boundary.

**One additional UX trap worth highlighting at the project level:** the spec defers PWA offline write queue to v2. That's defensible *but* combined with the localStorage 7-day ITP clearance in iOS Safari (not installed), a non-installed iOS user logging a session on cell data could lose their draft if the network fails *and* they don't return for a week. The installed-PWA caveat protects most use, but consider a server-side autosave-on-blur as belt-and-suspenders — see Section 1 traps.

---

## Sources

### Coffee log apps reviewed
- [Beanconqueror](https://beanconqueror.com/) — open-source, 30+ brew parameters, BLE scale/refractometer support, bag depletion tracking. Sets the "comprehensive" bar.
- [Beanconqueror changelog](https://github.com/graphefruit/Beanconqueror/blob/master/changelog.md) — feature evolution over time.
- [Filtru](https://getfiltru.com/) — strong pour-over timer, BLE scales (Acaia/Decent/Felicita), pro-tier brew logs.
- [Bloom Coffee Timer & Journal](https://apps.apple.com/us/app/bloom-coffee-timer-journal/id6759914524) — per-step timers, live extraction ratio.
- [Brewd](https://brewdcoffee.app/) — specialty bean catalog + taste profile build-up.
- [iBrewCoffee](https://ibrew.coffee/) — bag duplication ("Product" model), PDF export, recipe library.
- [BeanBook](https://www.beanbook.app/) — specialty tracker, bean exploration.
- [Extraction](https://extrctn.com/) — freshness tracker, sweet-window peak alerts (push notification differentiator).
- [Brew Logs](https://www.brewlog.app/en) — markets "30-second first brew, one-tap subsequent."
- [Coffee Book: Brew Timer](https://apps.apple.com/us/app/coffee-book-brew-timer/id1512681263) — long-press to clone coffee.
- [Tasting Grounds](https://apps.apple.com/us/app/tasting-grounds/id1526958511) — community + grind-size references per grinder.
- [Fellow Aiden](https://apps.apple.com/us/app/fellow-brew-with-aiden/id6612024910) — hardware-bound but instructive on log UX.
- [Trade Coffee](https://www.cnn.com/cnn-underscored/reviews/best-coffee-subscription-boxes) — rating-driven preference learning.
- [Crema Coffee playlist model](https://drippedcoffee.com/best-coffee-subscription/) — wishlist UX precedent.
- [Press app (DailyCoffeeNews)](https://dailycoffeenews.com/2015/02/03/meet-press-a-new-coffee-brewing-and-origin-logging-app/) — explicit critique of "too regimented" forms; market evidence for user complaints about long forms.

### UX traps & technical pitfalls
- [WebKit ITP 7-day localStorage expiry (NEAR wallet issue)](https://github.com/near/near-wallet/issues/479) — confirms 7-day localStorage clearance in iOS Safari.
- [Tealium on ITP 2.3 localStorage workaround](https://tealium.com/blog/data-governance-privacy/safari-itp-2-3-update-hamstrings-localstorage-workaround-as-expected/) — confirms it applies to in-Safari, installed PWA resets the timer.
- [WebKit bug 254545 — Wake Lock broken in installed iOS PWAs](https://bugs.webkit.org/show_bug.cgi?id=254545) — guided brew wake lock pitfall.
- [Screen Wake Lock browser support (caniuse)](https://caniuse.com/wake-lock) — confirms Safari 16.4+ in-Safari; PWA install nuance.
- [Beanconqueror critique — missing per-pour weight/time](https://www.home-barista.com/knockbox/beanconqueror-app-t68236-70.html) — even comprehensive apps miss things; informs per-pour capture decisions.

### Domain / audience
- [SCA Coffee Taster's Flavor Wheel](https://sca.coffee/research/coffee-tasters-flavor-wheel) — vocabulary standard for flavor notes.
- [Interactive SCA Flavor Wheel (Not Bad Coffee)](https://notbadcoffee.com/flavor-wheel-en/) — UX precedent for navigating a hierarchical flavor vocabulary.
- [Coffee roast freshness windows](https://achillescoffeeroasters.com/blogs/specialty-coffee-blog/the-science-of-freshness-why-roast-date-matters-more-than-you-think) — validates the spec's days-off-roast bucket choices (0-3 / 4-14 / 15-30 / 30+).
- [TDS measurement & extraction yield context](https://fellowproducts.com/blogs/learn/the-beginner-s-guide-to-total-dissolved-solids-and-coffee) — domain justification for optional TDS field.
- [Best coffee apps roundup (Home Grounds)](https://www.homegrounds.co/best-coffee-apps/) — broad market scan.
- [Coffee apps for enthusiasts (CartaCoffee)](https://www.cartacoffee.com/blogs/island-blog/8-best-apps-for-coffee-enthusiasts) — feature comparison across category.

### Confidence
- **HIGH** on UX traps (multiple confirmed sources for ITP, Wake Lock, form-length abandonment).
- **HIGH** on bag-as-instance gap (Beanconqueror, BeanBook, Extraction, iBrewCoffee all confirm this is the prevailing data model).
- **MEDIUM** on differentiator analysis (qualitative competitor comparison; no quantitative user survey).
- **HIGH** on anti-features (each one tied to a named competitor that shipped and either underperformed or diluted focus).
