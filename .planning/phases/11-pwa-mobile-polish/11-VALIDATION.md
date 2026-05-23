---
phase: 11
slug: pwa-mobile-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-23
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (+ pytest-asyncio, respx); playwright for responsive smoke |
| **Config file** | pyproject.toml / pytest.ini (pytest NOT baked into prod image — install per CLAUDE.md) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest -q tests/<changed>` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Estimated runtime** | ~{N} seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** {N} seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | REQ-{XX} | T-{N}-01 / — | {expected secure behavior or "N/A"} | unit | `{command}` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Populated during execution (Wave 0 + nyquist-auditor). Derived from RESEARCH.md "Validation Architecture".*

---

## Wave 0 Requirements

- [ ] {tests/test_file.py} — stubs for phase REQ-IDs
- [ ] {tests/conftest.py} — shared fixtures
- [ ] pytest install into running container (not baked into prod image)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| iOS Wake Lock + silent-audio/NoSleep.js fallback holds screen on | BREW-13 | Wake Lock + AudioContext cannot be verified in headless browser; iOS-specific | Install PWA on a real iPhone (iOS 16.4–18.3 for fallback path, 18.4+ for native), start Guided Brew, confirm screen stays on and indicator reflects actual lock state |
| Haptic step-transition cues vibrate on Android; silently skip on iOS | BREW-12 | Vibration API unsupported on iOS Safari; no headless verification | On Android Chrome confirm vibration at each step; on iOS confirm no error and no indicator |
| Audio chime fires at step transitions after user-gesture unlock | BREW-12 | AudioContext autoplay gate; iOS re-suspension | On real device confirm chime at each transition; backgrounding/foregrounding does not silence it |
| Installable on iOS Safari (one-time A2HS banner) and Android Chrome | MOB-* / PWA | iOS never prompts; standalone detection needs real install | Add to Home Screen on both platforms; confirm standalone launch, theme-color matches scheme |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
