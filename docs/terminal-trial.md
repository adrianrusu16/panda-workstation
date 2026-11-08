# 👻 Ghostty vs 🐱 Kitty — Panda Trial

Both terminals intentionally start with the same font, 11.5 pt size, Panda Night palette, padding, Fish shell and Starship prompt.

## Ghostty V1 preview

From the repository root, generate the five profiles in a private temporary
directory. The command prints that directory on stdout.

```fish
set -l preview (python3 -B theme/panda/common/ghostty_preview.py --validate)
echo "$preview/index.html"
```

Open `index.html` to compare the five flavors and inspect each configuration.
Omit `--validate` to generate the same files without a Ghostty executable.
With validation enabled, the installed `ghostty +validate-config` parses each
explicit config using disposable HOME and XDG directories. Parser acceptance
checks settings and syntax. Visual behavior requires the attended trial below.

The profiles combine the existing Ghostty preferences with the shared
Ghostty, Kitty, and Konsole ANSI roles. The GTK build can use the profile's
surface and text colors for its titlebar with `window-theme = ghostty`.
Whether that client titlebar is visible depends on the compositor and
decoration mode. Cyber's cyan, mint, and icy white dots belong to the HTML
illustration. [Ghostty configuration reference](https://ghostty.org/docs/config/reference#window-titlebar-background)

Panda Minimal uses bamboo green for bold prominent headings and commands,
ivory for bold section labels, soft white for body text, and muted gray for
secondary text. This uses the existing Minimal secondary and primary roles
while keeping the canonical manifest compatible with the pinned desktop
visual baseline. The generated Fish trial fragment applies canonical syntax colors.
Panda commands use an explicit `--theme`, the safely read Panda state, or Minimal
as a fallback. They use plain text in redirected output, with `NO_COLOR` or
`--no-color`, and in terminals without a truecolor signal. The Fastfetch summary
runs without user modules and uses plain external text under a Panda heading.
Starship keeps the user's prompt and configuration. Its ANSI styles can reflect
the terminal palette.

## Later attended trial on Plasma Wayland

Use a new disposable directory for each flavor. Run this from the repository
root after generating the preview above. Set `flavor` to `minimal`, `cyber`,
`gothic`, `hybrid`, or `pandawave`.

```fish
set -l flavor minimal
set -l trial (mktemp -d /tmp/panda-ghostty-trial.XXXXXX)
mkdir -p "$trial/config/fish/conf.d"
cp "$preview/$flavor/panda.fish" "$trial/config/fish/conf.d/panda-preview.fish"
env HOME="$trial" XDG_CONFIG_HOME="$trial/config" XDG_DATA_HOME="$trial/data" \
    XDG_CACHE_HOME="$trial/cache" XDG_STATE_HOME="$trial/state" GSETTINGS_BACKEND=memory \
    PANDA_TRIAL_REPO="$PWD" PANDA_TRIAL_THEME="$flavor" \
    ghostty --config-file="$preview/$flavor/config.ghostty" \
    --gtk-single-instance=false --window-save-state=never --command=fish
```

In that isolated window, run the repository-local shell sample:

```fish
fish --no-config "$PANDA_TRIAL_REPO/theme/panda/common/scripts/panda-status.fish" \
    --theme "$PANDA_TRIAL_THEME" --no-health
```

To compare the repository's Starship prompt in the isolated window, use
the installed Starship with the repository config:

```fish
set -gx STARSHIP_CONFIG "$PANDA_TRIAL_REPO/home/dot_config/starship.toml"
starship init fish | source
```

If Plasma supplies its own titlebar, repeat the launch with
`--window-decoration=client` to inspect the Ghostty titlebar.

Check heading weight and spacing, command highlighting, font and ligatures,
cursor and selection, GTK titlebar legibility, and the split shortcuts below.
Resize and move the window to check for repaint artifacts. Close the trial
window before switching flavors. The include hook and live canary are separate
from this workflow.

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
