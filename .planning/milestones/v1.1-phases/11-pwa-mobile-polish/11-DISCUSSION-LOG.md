# Phase 11: PWA + Mobile Polish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 11-PWA + Mobile Polish
**Areas discussed:** Nav architecture, Guided Brew Mode, Branding & icons, Mobile layout polish

---

## Nav architecture

### Config tab destination
| Option | Description | Selected |
|--------|-------------|----------|
| Catalog hub landing | Hub linking coffees/equipment/recipes/roasters/flavor-notes; account+sign-out at bottom | ✓ |
| Full 'More' menu | Catch-all list: catalog + AI pages + account | |
| Straight to Coffees | Opens directly to coffees list | |

### AI-adjacent page placement (wishlist, paste-and-rank)
| Option | Description | Selected |
|--------|-------------|----------|
| Keep on Home | Stay linked from Home near the AI card (current Phase 7 wiring) | ✓ |
| Move to Config hub | List in the catalog hub | |
| Both places | Home + Config | |

### Desktop identity + sign-out
| Option | Description | Selected |
|--------|-------------|----------|
| Always-visible top-right | Username + Sign out button always shown (zero JS) | |
| Account dropdown menu | Alpine CSP dropdown top-right with Sign out | ✓ |
| Icon only | Just a sign-out icon | |

### Log bottom-tab destination
| Option | Description | Selected |
|--------|-------------|----------|
| Sessions list + sticky '+ Log' | /brew list with prominent sticky create button | ✓ |
| Straight to new-session form | /brew/new directly | |
| Recent brews + '+ Log' | Compact recent view + create | |

**User's choice:** Config = catalog hub; AI pages on Home; desktop account dropdown; Log = sessions list + sticky "+ Log".
**Notes:** Mobile account/sign-out lives at the bottom of the Config hub. Nav absorbs the Phase 10 search header.

---

## Guided Brew Mode

### Entry point
| Option | Description | Selected |
|--------|-------------|----------|
| From the brew-log form | Launch after coffee+recipe selected; coffee pre-set | |
| From the recipe page | "Start guided brew"; recipe only | |
| Both entry points | Either; planner handles two completion prefills | ✓ |

### Step advance behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-advance + manual skip | Auto on time offset (chime+vibration) + "Next step" tap | ✓ |
| Pure auto-advance | Strictly follow the recipe clock | |
| Manual advance only | Tap to advance each step | |

### Cue (chime/vibration) configuration
| Option | Description | Selected |
|--------|-------------|----------|
| Start-screen toggles, remembered | Persisted localStorage toggles | |
| In-brew quick toggle only | Transient mute, resets each launch | |
| Persisted + in-brew toggle | localStorage toggles + live in-brew mute | ✓ |

### Elapsed timer data carry-over
| Option | Description | Selected |
|--------|-------------|----------|
| Prefill into notes | Drop a text line into session notes; no schema change | |
| Add brew_time_seconds column | Nullable int column; structured data | ✓ |
| Don't carry time over | Prefill coffee+recipe only | |

**User's choice:** Both entry points; auto-advance + manual skip; persisted + in-brew toggles; add `brew_time_seconds` column.
**Notes:** Schema deviation (touches Phase 5 table) explicitly signed off; migration is additive + nullable, low risk. Phase 6 analytics untouched.

---

## Branding & icons

### In-app logo treatment (dark-bg raster assets on cream theme)
| Option | Description | Selected |
|--------|-------------|----------|
| Circular mascot badge | Cropped circular badge, works on cream + dark; doubles as PWA icon | ✓ |
| Text wordmark + small badge | Wordmark desktop, badge mobile | |
| Transparent mascot cutout | Background-removed PNG (not available yet) | |

### Login page layout
| Option | Description | Selected |
|--------|-------------|----------|
| Centered hero + form below | Mascot hero top, form card below, centered | ✓ |
| Full-bleed background | Art fills page, form floats over | |
| Split panel (desktop) | Art one side, form other | |

### Login theme
| Option | Description | Selected |
|--------|-------------|----------|
| Always dark | Espresso-dark regardless of system theme | ✓ |
| Theme-adaptive | Follows system preference | |

### Derived asset generation
| Option | Description | Selected |
|--------|-------------|----------|
| Pre-generate + check in | One-time Pillow script, commit optimized outputs | ✓ |
| Generate at Docker build | Pillow build step like Tailwind | |
| You decide | Planner picks | |

**User's choice:** Circular mascot badge (= PWA icon); centered login hero + form below; login always dark; pre-generate + check in derived assets.
**Notes:** Source JPEGs are ~300-360KB — too heavy to ship; keep as reference only. Badge sourced from snobbery-login.jpg's circular composition.

---

## Mobile layout polish

### Home page section order
| Option | Description | Selected |
|--------|-------------|----------|
| Insights-first | AI + analytics (or cold-start meter) on top, lists below | |
| Cold-start to top, else unchanged | Move only the cold-start meter up for new users | |
| Keep lists-first | No change from current order | ✓ |

### Mobile modal behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Full-screen sheet | <768px full-screen, ≥768px dialog (per MOB-08) | ✓ |
| Bottom sheet | Slides up from bottom, partial height | |
| Keep centered dialog | Centered at all widths | |

### Bottom nav vs sticky form actions
| Option | Description | Selected |
|--------|-------------|----------|
| Hide nav on full-screen only | Nav hides in GBM + search sheet; form actions stack above persistent nav | ✓ |
| Hide nav on all forms | Nav hides on edit/create forms too | |
| Stack actions above nav always | Nav always visible, even in GBM | |

**User's choice:** Keep Home lists-first (no reorder); full-screen mobile modals; nav hides only in full-screen contexts.
**Notes:** Table→card collapse is verify-and-fix (six list fragments already carry dual patterns; admin pages have no tables).

---

## Claude's Discretion
- PWA service-worker cache strategy (locked by ROADMAP success criterion #2).
- iOS install banner copy + trigger (one-time, iOS-Safari-only, localStorage dismissal).
- `start_url: /?source=pwa` returns-200 verification.
- `brew_time_seconds` display location on session detail/list.
- Active-tab highlighting, icon set, catalog-hub layout, GBM timer-screen layout, cancel-confirmation, wake-lock indicator copy.

## Deferred Ideas
- PWA offline write queue + background sync — v2.
- Manual dark/light toggle — v2 (system-preference only in v1).
- `brew_time_seconds` in analytics — column lands now, analytics use deferred.
- Per-user settings/preferences page — none in v1.
- Insights-first home reorder — considered, declined for v1.
- Bottom-sheet (partial-height) modals — considered, chose full-screen.
- "Inline add new coffee from brew-form coffee select" (STATE todo) — reviewed, not folded (Phase 4/5 domain).
