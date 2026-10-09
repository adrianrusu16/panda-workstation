---
name: panda-theme-system
description: Design, implement, review, test, or extend the Panda Workstation theme family and desktop experience. Use for Panda Minimal, Cyber, Gothic, Hybrid, PandaWave Pulse, panda-theme, KDE/Plasma colors or layout, panels, widgets, clock/weather styling, wallpaper, icons, splash, Konsole, Ghostty, Kitty, Starship, Fastfetch, Fish theming, Zed/Kate/JetBrains integration, or automatic/manual theme switching.
---

# Panda Theme System

Use this skill only for Panda Workstation theme/desktop-experience work.

## Before editing

1. Read the repository `AGENTS.md`.
2. Read only the relevant sections of:
   - `references/design-spec.md`
   - `references/helios-safety.md`
   - `references/design-authority.md`
3. Inspect the current implementation before proposing changes.
4. State the bounded phase you are implementing. Do not silently implement later phases.

## Core model

There is one stable desktop layout and five visual flavors:

- `minimal`
- `cyber`
- `gothic`
- `hybrid`
- `wave` (PandaWave Pulse)

A flavor changes the visual system. It must not rearrange the user's established panel/widget/workspace layout.

## Palette architecture

Each flavor has one canonical semantic palette.

Prefer a structure equivalent to:

- background
- surface
- surface2
- text
- muted
- primary
- secondary
- warning
- error

Generate or template application-specific values from those tokens. Do not independently invent almost-identical colors in each application.

When a color-system skill is available, use it to review ramps, semantic roles, and measured contrast. The Panda manifest remains authoritative.

## Helios rules

On `panda-helios`:

- Wayland remains the daily session.
- Opaque-first rendering is required.
- Do not depend on blur, acrylic, glass, or transparency.
- Do not touch kernel/GPU/boot/suspend/storage safety policy.
- Theme performance must remain reasonable on Intel HD 630.

Read `references/helios-safety.md` before modifying visual effects.

## Theme switching

`panda-theme` must support:

- `status`
- `list`
- `auto`
- `minimal`
- `cyber`
- `gothic`
- `hybrid`
- `wave`
- `next`
- `previous`
- `doctor`
- `auto --explain`

Manual mode remains in control until the user explicitly returns to Auto.

Auto mode is deterministic and explainable.

Initial selection priority:

1. explicit special context
2. PandaWave project/context → Wave
3. gaming → Cyber
4. focus → Minimal
5. time rules
   - 07:00–18:00 → Hybrid
   - 18:00–21:00 → Cyber
   - 21:00–07:00 → Gothic
6. fallback → Hybrid

## Transaction contract

A critical theme switch must conceptually follow:

1. validate requested flavor
2. load the canonical palette
3. render/prepare managed configs
4. validate generated configs
5. snapshot currently managed state
6. apply Tier 1 components
7. verify Tier 1 state
8. refresh supported applications
9. report Tier 2/3 warnings
10. persist new runtime state only after core success

If a critical Tier 1 apply fails, restore the previous managed state.

## Integration tiers

### Tier 1 — core

Expected to follow the active flavor:

- KDE/Plasma color system
- supported Plasma style pieces
- wallpaper
- Panda icon overrides
- splash
- Konsole
- Ghostty
- Kitty
- Starship
- Fastfetch
- Fish
- Zed
- Kate

### Tier 2 — managed with refresh/restart caveats

- CLion
- Android Studio
- other JetBrains IDEs

Never destructively rewrite IDE preferences merely to claim live switching.

### Tier 3 — best effort

- Firefox
- optional Git GUIs
- miscellaneous third-party applications

A Tier 3 limitation must not fail the core transaction.

## Desktop and widgets

Shared desktop structure:

- opaque top system/workspace bar
- bottom application dock
- three stable virtual desktops
- compact Panda system dashboard
- themed clock
- themed weather when provider data is available

Start with stable Plasma widgets/provider infrastructure. Build custom `PandaClock` or `PandaWeather` plasmoids only if the stock widgets cannot meet the approved design without brittle hacks.

Never embed secret weather API keys in the repository.

## External design skills

If installed, these are useful:

- `better-colors`
- `better-accessibility`
- `better-layout`
- `better-ui`
- `prototype`
- `animate`

Use them as review/prototyping tools, not as the source of Panda identity.

Generic style skills such as `minimal`, `futuristic`, `dramatic`, or `pulse` are inspiration only. They must not override approved Panda tokens or platform constraints.

## Implementation discipline

- Keep each phase small.
- Add tests/validation before claiming completion.
- Prefer generated/templates over duplicated hand-edited app configs.
- Avoid one-off manual KDE settings that cannot be reproduced.
- Preserve the existing bootstrap/reporting visual conventions.
- Use Fish for Panda-owned automation.
- Do not use `git add .`.
- Do not commit or push unless explicitly asked.

## Before completion

Verify the scope against the acceptance criteria in `references/design-spec.md`.

At minimum:

- run relevant syntax/static checks,
- run `git diff --check`,
- test the feature on the actual desktop when the change affects runtime UI,
- report anything that could not be verified visually,
- distinguish "files generated" from "desktop behavior verified".
