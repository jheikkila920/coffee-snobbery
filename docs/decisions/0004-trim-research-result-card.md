# ADR 0004: Trim Research Result Card to Score + Why + Wishlist (Revises D-03)

- Status: Accepted
- Date: 2026-05-28
- Phase: 19 (AI Page Research + Predict)
- Requirements: AIX-01, AIX-02, AIX-06
- Revises: D-03 (research result card stack)
- Supersedes: (none)

## Context

D-03 defined the research result card stack as:

> title → metadata (origin / process / roast_level / cached badge) → tasting-notes chips → predicted rating + Why → cited sources → wishlist button

This stack was designed under the assumption that surfacing rich coffee metadata alongside the predicted rating would help the user evaluate whether to wishlist the coffee. After live verification of the Phase 19 research flow (Counter Culture / Mpemba, 2026-05-28), the household users concluded the opposite: the metadata and tasting-notes are noise at the point of decision. The predicted score and the one-line "Why" grounding already carry all the signal needed to decide "add to wishlist or not." The cited sources are invisible to casual users on mobile, add visual bulk, and are only useful to a researcher auditing the AI call — not the primary interaction path.

The `buy URL not verified` warning chip was co-located with the metadata row in D-03 purely by proximity. Its semantic home is next to the action it warns about (the wishlist add button), not next to coffee origin data.

The `cached` badge was similarly co-located with metadata. Its value is "this result was not a new AI call," which is cost-control context, not coffee data. Inline next to the title is the minimal-noise location.

## Decision

Trim `app/templates/fragments/ai/research_result.html` to:

**New card stack:**

1. Title row — `roaster_name — coffee_name` + `cached` badge inline (if cached)
2. Predicted rating block — range (`predicted_low – predicted_high`) + confidence + "Why: reasoning" (unchanged from D-03)
3. Wishlist row — Add-to-wishlist button + `buy URL not verified` chip inline (if applicable)

**Removed from display:**

- Origin / process / roast_level metadata spans
- Tasting-notes chips block
- Cited-sources footnote block

**No backend change.** `CoffeeResearchSchema` is unchanged. The AI prompt still requests and receives origin, process, roast_level, tasting_notes, and sources — those fields are inputs to `AIRatingPrediction.reasoning`. Removing them from the result card has zero cost impact and zero schema impact.

**Original D-03 card stack (for reference):**

```
title → metadata (origin · process · roast_level · cached) → tasting notes → predicted rating + Why → sources → wishlist
```

**New card stack (this ADR):**

```
title [+ cached] → predicted rating + Why → wishlist [+ unverified chip]
```

## Consequences

- `research_result.html` is ~47 lines instead of ~85. Easier to maintain.
- Template tests in `tests/templates/test_ai_page_phase19.py` continue to pass: `predicted_low`, `predicted_high`, `confidence`, `reasoning`, `/ai/wishlist/add`, `coffee_name`, `source_url` are all still present. `|safe` is still absent.
- A future ADR can restore any removed field if users decide they want to see it. The data is always available from the schema.
- The cached badge and unverified chip are now at their semantic locations (title context and action context respectively). Any future redesign should keep this separation.
- The CSRF handling in the wishlist form (`X-CSRF-Token` as a form field read from the `csrftoken` cookie) is a **pending verification item** — it should be confirmed to match how other working HTMX POST forms in this app send the CSRF token (see 19-06-SUMMARY.md outstanding UAT items). This ADR does not change the wishlist form's CSRF behavior from D-03.

## Alternatives Considered

- **Keep metadata, hide on mobile only** — rejected. "Hidden on mobile" means the household users never see it; might as well remove it. Desktop is not a primary use case for this app (mobile-first hard rule).
- **Keep tasting notes, remove metadata** — rejected. Tasting notes occupy the most vertical space and are the most subjective field. The predicted score already synthesizes them; showing them separately is redundant.
- **Keep sources as collapsed/expandable** — rejected. Adds JS complexity for a feature no user asked for. If AI sourcing transparency becomes a requirement, a dedicated "AI audit" page is the right vehicle.

## References

- D-03 (`.planning/phases/19-ai-page-research-predict/19-CONTEXT.md`)
- AIX-01, AIX-02, AIX-06 (`.planning/REQUIREMENTS.md`)
- `app/templates/fragments/ai/research_result.html`
- `tests/templates/test_ai_page_phase19.py`
- Phase 19 live verification session, 2026-05-28 (Counter Culture / Mpemba)
