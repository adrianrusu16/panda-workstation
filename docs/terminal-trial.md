# 👻 Ghostty vs 🐱 Kitty — Panda Trial

Both terminals intentionally start with the same font, 11.5 pt size, Panda Night palette, padding, Fish shell and Starship prompt.

## What to compare

Score each terminal from 1–5 after normal use rather than a benchmark-only session.

| Area | Ghostty | Kitty | What to notice |
|---|:---:|:---:|---|
| Startup / first window |  |  | perceived delay, flicker |
| Typing latency |  |  | Fish autosuggestions, long commands |
| Resize / move |  |  | redraw smoothness, artifacts |
| Font rendering |  |  | weight, ligatures, Nerd Font icons |
| Tabs |  |  | discoverability, navigation |
| Splits |  |  | `Ctrl+Shift+Enter`, focus ergonomics |
| Scrollback |  |  | huge build/log output |
| Copy / paste / URLs |  |  | mouse + keyboard behavior |
| Shell integration |  |  | cwd inheritance, prompt marks |
| Full-screen TUI |  |  | `btop`, `lazygit` later, editors |
| SSH behavior |  |  | TERM handling on remote hosts |
| Resource use |  |  | RAM/CPU at idle and under output |
| Overall feel |  |  | which one you naturally reopen |

## Fair comparison commands

```fish
fastfetch
btop
for i in (seq 1 3000); echo "Panda terminal line $i"; end
```

Inside the workstation repo:

```fish
rg 'ui_' bootstrap
./bootstrap/setup-workstation.fish --list
```

## Shared shortcuts

- `Ctrl+Shift+Enter` — create an automatic/new split
- `Ctrl+Shift+Z` — zoom/focus the current split (semantics differ slightly by terminal)

Ghostty also has directional split focus on `Ctrl+Shift+Arrow`.

## Decision rule

Keep both during the trial. Do not change the system default terminal until one wins through normal use. Konsole remains installed as the known-safe KDE fallback.
