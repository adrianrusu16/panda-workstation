# Panda Theme System — Design Specification

**Date:** 2026-10-06
**Project:** `adrianrusu16/panda-workstation`
**Status:** Approved for implementation
**Scope:** KDE Plasma / Wayland theme family, desktop layout, widgets, shell, terminals, editors, and automatic/manual theme orchestration

---

## 1. Intent

Build a cohesive **Panda Theme System** for Panda Workstation rather than a single static KDE theme.

The system will provide five switchable visual flavors:

1. **Panda Minimal**
2. **Panda Cyber**
3. **Panda Gothic**
4. **Panda Hybrid**
5. **PandaWave Pulse**

All flavors share the same desktop structure and behavior. Switching flavor changes the visual identity and supported application palettes without rearranging the user's workflow.

The system must support:

- manual theme selection,
- deterministic automatic theme selection,
- an immediate return from manual override to automatic mode,
- consistent theming across KDE/Plasma, terminals, shell, and supported applications,
- safe operation on `panda-helios`,
- reproducible installation through `panda-workstation`.

The workstation remains **Wayland-first**. X11 is not a required compatibility target for daily use.

---

## 2. Design principles

### 2.1 One layout, multiple personalities

Theme switching must not destroy or rearrange:

- panels,
- widgets,
- virtual desktops,
- window rules,
- pinned applications,
- terminal workflows,
- user files.

The shared layout is stable. A theme flavor is a visual bundle applied onto that layout.

### 2.2 Opaque-first on Panda Helios

The current Helios graphics stack has shown repaint artifacts around translucent surfaces.

For `panda-helios`:

- transparency is not required,
- blur is not required,
- glass/acrylic effects are not required,
- opaque titlebars and panels are the safe default,
- visual identity must remain strong without compositing-heavy effects.

A future AMD workstation may enable optional richer effects through a separate machine capability profile.

### 2.3 A single palette source

Each flavor defines one canonical palette.

Application-specific files are generated or templated from that palette instead of independently hardcoding near-identical colors in:

- KDE,
- Konsole,
- Ghostty,
- Kitty,
- Starship,
- Fastfetch,
- Zed,
- Kate,
- supported JetBrains themes.

### 2.4 Best-effort application integration

Applications are divided into integration tiers.

A theme switch must never be considered failed merely because an application cannot live-switch its theme. Core desktop state has stricter requirements than optional integrations.

### 2.5 Predictable automation

Automatic mode must be explainable.

`panda-theme status` and `panda-theme auto --explain` must be able to state why a theme is active.

No opaque or random theme selection is allowed.

---

## 3. Theme family

### 3.1 Panda Minimal

**Character:** quiet, monochrome, focused.

Initial palette direction:

| Role | Color |
|---|---|
| Background | `#0B0D0F` |
| Surface | `#14171A` |
| Surface 2 | `#1C2024` |
| Text | `#F1F3F4` |
| Muted | `#8B949E` |
| Primary | `#DDE3E6` |
| Secondary | `#6FCF97` |

Visual language:

- black / graphite / off-white,
- restrained bamboo green,
- thin outlines,
- low visual noise,
- minimal ornament.

Primary uses:

- focus sessions,
- screen sharing,
- distraction-free work.

### 3.2 Panda Cyber

**Character:** technical, futuristic, developer-oriented.

Initial palette direction:

| Role | Color |
|---|---|
| Background | `#070B10` |
| Surface | `#0E1620` |
| Surface 2 | `#14202B` |
| Text | `#E6F7FA` |
| Primary | `#20D7F2` |
| Secondary | `#52E397` |
| Accent dark | `#0F8FA6` |

Visual language:

- cyan outlines,
- green healthy-state indicators,
- subtle system telemetry,
- grids / circuits / scan motifs used sparingly.

Primary uses:

- evening development,
- gaming context,
- system diagnostics.

### 3.3 Panda Gothic

**Character:** elegant, dark, dramatic.

Initial palette direction:

| Role | Color |
|---|---|
| Background | `#090708` |
| Surface | `#151012` |
| Surface 2 | `#21171B` |
| Text | `#F0EAEC` |
| Muted | `#97888D` |
| Primary | `#741D32` |
| Secondary | `#992E4D` |
| Metallic | `#B9B5B7` |

Visual language:

- black,
- burgundy,
- wine,
- silver,
- optional restrained Victorian ornament.

Primary uses:

- night mode,
- personal / aesthetic mode.

### 3.4 Panda Hybrid

**Character:** practical daily-driver theme.

Initial palette direction:

| Role | Color |
|---|---|
| Background | `#0D1117` |
| Surface | `#151B23` |
| Surface 2 | `#1D2630` |
| Text | `#E7EDF2` |
| Muted | `#8796A5` |
| Primary | `#36C5E8` |
| Secondary | `#55D98B` |
| Warning | `#E3B341` |
| Error | `#F47067` |

Visual language:

- Minimal surfaces,
- Cyber semantic accents,
- color communicates state rather than decorating everything.

Primary use:

- default daytime workstation mode.

### 3.5 PandaWave Pulse

**Character:** modern audio / tech identity aligned with the current PandaWave rebrand.

The visual direction is based on the PandaWave headset panda logo introduced in commit:

`bb1e83c3c178e5a315aa799c105c3cab5b662c9c`

Initial palette direction:

| Role | Color |
|---|---|
| Background | `#070A12` |
| Surface | `#101420` |
| Surface 2 | `#191C2B` |
| Text | `#F8F8FA` |
| Muted | `#A4A7B3` |
| Primary | `#FF25AC` |
| Secondary | `#F31599` |
| Plum | `#971B62` |
| Blush | `#F678B2` |

The final values should be sampled/tuned against the actual logo asset rather than assumed from these starting values.

Visual language:

- headset arcs,
- waveforms,
- audio pulse lines,
- circular rings,
- hot-pink active indicators,
- midnight navy / black surfaces.

Primary use:

- PandaWave development context.

---

## 4. Shared desktop layout

All flavors use one layout.

### 4.1 Top system bar

Purpose: workspace navigation + system information.

Left side:

- Panda launcher,
- virtual desktop/workspace indicators,
- optional activity/context indicator.

Center / flexible area:

- active application or contextual title where practical.

Right side:

- optional compact CPU/RAM indicators,
- system tray,
- network,
- audio,
- battery,
- notifications,
- clock/date.

The bar is opaque on `panda-helios`.

### 4.2 Bottom application dock

Purpose: applications only.

Contains:

- pinned applications,
- currently running applications,
- optional trash / quick actions.

No duplicated clock, network, battery, or system telemetry.

### 4.3 Virtual desktops

Initial target:

- 3 stable virtual desktops,
- visually themed indicators,
- layout remains unchanged when flavor switches.

---

## 5. Desktop widgets

Widgets should inherit the active Panda flavor.

The initial implementation should prefer stable KDE/Plasma widgets rather than immediately maintaining custom plasmoids.

### 5.1 Panda system dashboard

A compact desktop system monitor showing:

- machine name,
- safe / experimental GPU profile,
- CPU load,
- CPU temperature when available,
- RAM,
- disk,
- kernel,
- active GPU.

Example semantic presentation:

**Hybrid**

```text
🐼 panda-helios

SAFE MODE          ●

CPU    8%           48°C
RAM    4.9 / 32 GB
DISK   31%

Kernel 6.18 LTS
GPU    Intel HD 630
```

**Cyber**

```text
SYS // PANDA-HELIOS

GPU.INTEL     [ONLINE]
NVIDIA        [ISOLATED]
CPU           [08%]
RAM           [15%]
```

The data remains the same; presentation follows the active flavor.

### 5.2 Clock widget

A themed clock is part of the shared desktop.

Initial behavior:

- 24-hour time,
- date,
- optionally weekday,
- inherits active Plasma/Panda palette,
- no transparency dependency.

If the stock Plasma Digital Clock cannot achieve the intended visual identity using palette/style inheritance, a custom `PandaClock` plasmoid may be introduced in a later implementation phase.

### 5.3 Weather widget

A themed weather widget is allowed and desirable.

Initial behavior:

- use KDE/Plasma's existing weather/provider infrastructure where practical,
- avoid embedding secret API credentials in the repository,
- inherit the active flavor palette,
- remain compact enough for either the top bar or desktop dashboard.

Desired display:

- current condition icon,
- current temperature,
- concise condition text,
- optional daily high/low.

A future `PandaWeather` plasmoid is allowed only if existing Plasma widgets cannot be styled sufficiently.

### 5.4 Widget styling contract

Widgets must:

- use semantic theme colors,
- avoid hardcoded per-widget palettes when inheritance works,
- remain legible without blur,
- not force background translucency on Helios,
- remain usable if optional sensors or weather data are unavailable.

---

## 6. Icons

A complete icon set is explicitly **not** required for v1.

Use a mature base icon theme for broad coverage and add Panda overrides.

Proposed structure:

```text
Panda Icons
├── common/
└── flavors/
    ├── minimal/
    ├── cyber/
    ├── gothic/
    ├── hybrid/
    └── wave/
```

High-value custom icons include:

- Panda launcher,
- home,
- Workspace,
- Projects,
- Labs,
- AOSP,
- System,
- Tools,
- Scratch,
- terminal,
- developer folders.

Flavor variants primarily change accent/folder identity rather than replacing every system icon.

---

## 7. Wallpaper, lock screen, splash, and login

### 7.1 Wallpapers

Each flavor initially provides:

- `desktop-1920x1080`,
- `lockscreen-1920x1080`.

Future variants may include:

- 2560×1440,
- 3440×1440,
- 3840×2160.

Wallpaper themes:

- **Minimal:** restrained panda silhouette.
- **Cyber:** panda + subtle circuit / telemetry motifs.
- **Gothic:** panda crest / gothic arch / burgundy ornament.
- **Hybrid:** minimal panda with subtle cyan/green systems language.
- **PandaWave:** headset panda + waveform / pulse identity.

### 7.2 Plasma splash

One splash engine, five visual skins.

- Minimal → simple fade.
- Cyber → scan / diagnostics motif.
- Gothic → crest reveal.
- Hybrid → panda + system pulse.
- PandaWave → audio waveform animation.

Animations must remain lightweight.

### 7.3 Lock screen

The lock screen follows the active flavor wallpaper and palette where stable APIs permit.

### 7.4 SDDM

SDDM is intentionally later-phase.

Reason:

- a broken desktop style is recoverable after login,
- a broken display-manager theme is more disruptive.

Initial SDDM behavior may remain neutral Panda or follow the last successfully persisted flavor.

---

## 8. Shell and terminal integration

The active flavor applies to:

- Starship,
- Fastfetch,
- Fish greeting,
- Panda ASCII/dashboard commands,
- Konsole,
- Ghostty,
- Kitty.

### 8.1 Panda shell commands

Desired commands:

```text
panda
panda-big
panda-status
panda-theme
```

`panda`:

- medium Panda artwork,
- compact themed Fastfetch information.

`panda-big`:

- large block/Unicode Panda artwork.

`panda-status`:

- active Panda theme,
- auto/manual mode,
- kernel,
- GPU profile,
- NVIDIA isolation state,
- failed systemd units,
- disk / machine health summary,
- Panda Workstation Git status.

### 8.2 Terminal parity

Ghostty, Kitty, and Konsole should receive equivalent:

- palette,
- font family,
- font size target,
- cursor/accent colors.

Terminal-specific capabilities may differ, but a flavor must remain recognizably the same across all three.

Transparency is off by default on Helios.

---

## 9. Editor and application integration tiers

### Tier 1 — core live-switch targets

Theme Manager should control these directly:

- KDE / Plasma colors,
- Plasma style where supported,
- wallpaper,
- icon flavor,
- splash,
- Konsole,
- Ghostty,
- Kitty,
- Starship,
- Fastfetch,
- Fish,
- Zed,
- Kate.

### Tier 2 — managed themes with refresh/restart limitations

- CLion,
- Android Studio,
- other JetBrains IDEs.

Five matching Panda JetBrains themes may be generated/maintained.

If external live switching is reliable, Theme Manager may trigger it.

If not:

- no destructive IDE preference rewriting,
- Theme Manager reports the application as requiring manual refresh/restart.

### Tier 3 — best-effort integrations

Examples:

- Firefox,
- optional Git GUI,
- miscellaneous third-party apps.

Failure to live-switch a Tier 3 application does not fail the desktop theme transaction.

---

## 10. Panda Theme Manager

Primary command:

```text
panda-theme
```

Required commands:

```text
panda-theme status
panda-theme list
panda-theme auto
panda-theme minimal
panda-theme cyber
panda-theme gothic
panda-theme hybrid
panda-theme wave
panda-theme next
panda-theme previous
panda-theme doctor
panda-theme auto --explain
```

### 10.1 Theme chooser shortcut

Preferred shortcut:

`Meta + Alt + P`

Expected chooser:

```text
╭────────────────────────────╮
│       🐼 PANDA THEME       │
├────────────────────────────┤
│  A   Automatic             │
│  1   Minimal               │
│  2   Cyber                 │
│  3   Gothic                │
│  4   Hybrid                │
│  5   PandaWave Pulse       │
╰────────────────────────────╯
```

Implementation may use a lightweight KDE-native launcher/menu or another stable chooser mechanism.

### 10.2 Auto/manual toggle

Preferred shortcut:

`Meta + Alt + A`

Behavior:

- if in manual mode → enable Auto,
- if in Auto → return to the most recently selected manual flavor or present a chooser if no manual flavor exists.

A KDE notification confirms mode changes.

### 10.3 Optional cycle shortcut

A secondary shortcut may cycle flavors:

`Meta + Alt + ]`

This is convenience only and not required for initial completion.

---

## 11. Automatic mode

Auto mode is deterministic.

### 11.1 Priority order

Highest to lowest:

1. explicit special context,
2. project/application context,
3. gaming context,
4. focus context,
5. time-of-day schedule,
6. fallback theme.

### 11.2 Initial rules

Special/context rules:

```text
PandaWave project/context  → PandaWave Pulse
Gaming context             → Panda Cyber
Focus context              → Panda Minimal
```

Time rules when no higher-priority context is active:

```text
07:00–18:00  → Panda Hybrid
18:00–21:00  → Panda Cyber
21:00–07:00  → Panda Gothic
```

Fallback:

```text
Panda Hybrid
```

### 11.3 Context sources

The design allows multiple adapters.

Initial implementation should favor simple, observable signals:

- explicit `panda-theme context ...` state,
- Fish working-directory hooks for known project paths,
- detectable Steam/game processes,
- explicit focus-mode command/state.

Later integrations may include:

- Zed project context,
- JetBrains project context,
- KDE/KWin active-window context.

The manager must gracefully ignore unavailable adapters.

### 11.4 Manual override

Running:

```text
panda-theme gothic
```

sets:

```text
mode = manual
active = gothic
```

The theme remains Gothic until:

```text
panda-theme auto
```

is invoked.

Auto does not silently reclaim control from a manual override.

---

## 12. State and configuration

Runtime state:

```text
~/.config/panda/theme-state.toml
```

Example:

```toml
mode = "auto"
active = "hybrid"
last_manual = "gothic"
context = ""
```

This is runtime/local state and is not required to be committed.

Theme definitions are committed.

Each flavor has a declarative manifest, conceptually:

```toml
name = "Panda Hybrid"
slug = "hybrid"

[palette]
background = "#0D1117"
surface = "#151B23"
surface2 = "#1D2630"
text = "#E7EDF2"
muted = "#8796A5"
primary = "#36C5E8"
secondary = "#55D98B"
warning = "#E3B341"
error = "#F47067"
```

Generated configs derive from this manifest.

---

## 13. Transactional switching

A switch must be treated as a transaction.

Conceptual flow:

```text
1. validate requested flavor
2. load canonical palette
3. render/prepare application configs
4. validate generated configs
5. snapshot currently managed state
6. apply Tier 1 components
7. verify Tier 1 state
8. request/perform supported application refreshes
9. record warnings for Tier 2/3 limitations
10. persist state only after core success
```

If a critical Tier 1 apply or validation fails:

```text
rollback managed state
```

The manager must avoid leaving a half-Cyber / half-Gothic desktop.

---

## 14. Theme-status notifications

Switching to a manual flavor:

```text
🥀 Panda Gothic
Manual override enabled
```

Entering Auto:

```text
🐼 Panda Theme
Automatic mode enabled
Hybrid selected · daytime
```

Context switch:

```text
🎧 PandaWave Pulse
PandaWave project context
```

Notifications must be concise and non-modal.

---

## 15. Repository structure

Target structure:

```text
panda-workstation/
├── theme/
│   └── panda/
│       ├── common/
│       │   ├── icons/
│       │   ├── layout/
│       │   ├── widgets/
│       │   ├── scripts/
│       │   └── templates/
│       │
│       ├── minimal/
│       │   ├── theme.toml
│       │   ├── wallpaper/
│       │   ├── splash/
│       │   └── assets/
│       │
│       ├── cyber/
│       ├── gothic/
│       ├── hybrid/
│       └── pandawave/
│
├── bootstrap/
│   └── setup-panda.fish
│
└── docs/
    └── panda-theme/
```

Application templates may live under `common/templates/` or under application-specific directories when separation improves maintainability.

---

## 16. Machine capability policy

Theme behavior may vary by machine capability without changing flavor identity.

Example:

```text
panda-helios
├── opaque surfaces
├── blur off
├── lightweight effects
└── Intel-safe graphics path

future amd-desktop
├── optional transparency
├── optional blur
├── richer animation
└── same Panda flavor palettes
```

The flavor defines identity. The machine profile defines which effects are safe.

---

## 17. Non-goals for the first release

The first release does not need:

- a completely original set of thousands of application icons,
- a custom weather backend,
- a custom display manager before the desktop is stable,
- arbitrary AI-driven theme selection,
- complex animated desktop backgrounds,
- destructive modification of unsupported third-party application preferences,
- transparency as a requirement.

---

## 18. Acceptance criteria

The design is considered successfully implemented when:

1. All five flavors can be selected manually.
2. Auto mode follows the documented priority/rules.
3. Manual override remains active until explicitly returned to Auto.
4. `panda-theme status` reports mode, active flavor, and reason.
5. `panda-theme auto --explain` explains the selection.
6. KDE/Plasma and wallpaper change coherently.
7. Ghostty, Kitty, Konsole, Starship, Fastfetch, and Fish reflect the active palette.
8. Zed and Kate follow the active flavor.
9. JetBrains integrations fail gracefully if live switching is unavailable.
10. The top bar, bottom dock, virtual desktops, and widgets remain structurally unchanged across flavor switches.
11. Clock and weather are themed using the active palette.
12. Helios mode remains usable with blur/transparency disabled.
13. Theme switching does not alter GPU/kernel safety configuration.
14. A failed critical switch can roll back to the previous managed state.
15. `panda-theme doctor` can detect missing or inconsistent managed components.
16. The system remains reproducible from `panda-workstation`.

---

## 19. Approved design summary

The intended Panda desktop is a **theme family plus desktop personality manager**, not a single KDE skin.

Shared behavior:

```text
Panda Layout
+ Panda Theme Manager
+ machine capability policy
```

Visual choices:

```text
Minimal
Cyber
Gothic
Hybrid
PandaWave Pulse
```

Control:

```text
Manual flavor selection
or
deterministic Auto mode
```

Scope:

```text
Plasma + panels + widgets + wallpaper + icons + splash
+ shell + terminals + editors + supported apps
```

The system is designed to stay stable on the current Intel-only Helios while remaining extensible for richer effects on future hardware.
