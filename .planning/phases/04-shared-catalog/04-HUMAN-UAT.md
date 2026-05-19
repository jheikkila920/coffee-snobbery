---
status: partial
phase: 04-shared-catalog
source: [04-VERIFICATION.md]
started: 2026-05-19T20:00:00Z
updated: 2026-05-19T20:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Recipe step builder live reactivity
expected: Open /recipes/new, add a "Bloom" step (50g / 45s) and a second step (150g / 120s). Step 2's delta row shows "+100g · +1:15"; the pour-timeline preview shows two proportional vertical segments that resize as time values change. Removing step 1 collapses the preview to a single segment.
result: [pending]

### 2. Autocomplete-on-create-on-save (roaster)
expected: Open /coffees/new, type 2+ chars in the roaster field; dropdown appears after the 350ms debounce. Click "+ Create new roaster", enter a name, save — the mini-modal closes and the new roaster is pre-selected in the parent coffee form with no page reload.
result: [pending]

### 3. Flavor note chip widget
expected: Open /coffees/new, type 2+ chars in the flavor note field, select a result — a chip appears immediately. Add a second flavor note, submit the form — both flavor-note IDs land in advertised_flavor_note_ids in the DB.
result: [pending]

### 4. Mini-modal dirty check
expected: Open the roaster mini-modal, type something in the Name field, press ESC or click the backdrop — a confirm prompt fires before the modal closes; cancelling keeps the modal open.
result: [pending]

### 5. Coffee list responsive layout at 375px
expected: Open /coffees at 375px viewport. The desktop table is hidden; the card list is visible; no horizontal scrollbar anywhere on the page.
result: [pending]

### 6. Bag photo upload with device camera (mobile)
expected: On iOS/Android, tap "Upload photo" on a bag row. With capture="environment" now present, the rear camera should open directly (file-picker fallback still available). Upload completes and the thumbnail renders. (Attribute added in commit 71b6774 — this item now verifies the camera actually opens.)
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
