"""Generate five standalone Ghostty profiles and a static comparison in /tmp."""

import argparse
from html import escape
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from palette import contrast_ratio, load_family, terminal_heading_roles
from render import render_bytes, render_fish, render_ghostty_profile


V2_GHOSTTY_CONFIG = "config-v2.ghostty"


def preview_files(family, *, palette_version="v1"):
    if palette_version not in ("v1", "v2"):
        raise ValueError("palette_version must be v1 or v2")
    v2 = palette_version == "v2"
    ghostty_name = V2_GHOSTTY_CONFIG if v2 else "config.ghostty"
    fish_name = "panda-v2.fish" if v2 else "panda.fish"
    title = "Panda Terminal and Shell V2" if v2 else "Panda Ghostty V1"
    if v2:
        gothic = family["gothic"].palette
        ratio = contrast_ratio(gothic["secondary"], gothic["surface2"])
        description = (
            "<p>Static palette comparison and offline configuration samples. "
            f"Gothic’s secondary fill against surface2 is {ratio:.6f}:1. "
            "Use a visible border and the paired on_secondary text for that fill.</p>"
        )
    else:
        description = """<p>Static palette comparison. Cyber’s three dots are illustrative preview chrome.
Native Ghostty uses the GTK titlebar where supported.</p>"""

    files = {}
    cards = []
    for slug, theme in family.items():
        files[f"{slug}/{ghostty_name}"] = render_ghostty_profile(theme)
        files[f"{slug}/{fish_name}"] = render_fish(theme, trial=True).encode()
        links = [(ghostty_name, "Ghostty configuration")]
        if v2:
            files[f"{slug}/starship-v2.toml"] = render_bytes("starship", theme)
            files[f"{slug}/fastfetch-v2.json"] = render_bytes("fastfetch", theme)
            links.extend(((fish_name, "Fish syntax"), ("starship-v2.toml", "Starship palette"),
                          ("fastfetch-v2.json", "Fastfetch display colors")))
        artifact_links = "\n    ".join(f'<a href="{slug}/{name}">{label}</a>' for name, label in links)
        name = escape(theme.name)
        colors = theme.palette
        prominent, section = terminal_heading_roles(theme)
        dots = ""
        if not v2 and slug == "cyber":
            dots = '<span class="dots" aria-hidden="true">' + "".join(
                f'<i style="background:{colors[role]}"></i>' for role in ("primary", "secondary", "text")
            ) + "</span>"
        cards.append(f"""<section style="--bg:{colors['background']};--surface:{colors['surface']};
--text:{colors['text']};--muted:{colors['muted']};--accent:{colors[prominent]};
--section:{colors[section]};--success:{colors['success']};--border:{colors['border']}">
  <header><h2>{name}</h2>{dots}</header>
  <div class="terminal">
    <p class="heading"><strong>Panda status</strong></p>
    <p><strong class="label">Workspace</strong><br>Shell · Fish<br><small>Display · opaque</small></p>
    <p class="command"><strong>❯ panda --no-health</strong><br><span>● Ready</span></p>
    {artifact_links}
  </div>
</section>""")
    files["index.html"] = ("""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + title + """ · palette comparison</title>
<style>
:root {color-scheme:dark;background:#121519;color:#f1f3f4;font:16px system-ui,sans-serif}
body {margin:0 auto;padding:clamp(1rem,4vw,3rem);max-width:76rem}
main {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));gap:1rem}
h1 {margin:.1em 0 .35em;font-size:clamp(1.6rem,4vw,2.6rem)}
body>p {max-width:65ch;margin:0 0 1.5rem;color:#bcc4cb}
section {background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:.5rem}
header {display:flex;align-items:center;justify-content:space-between;gap:1rem;
padding:.65rem 1rem;background:var(--surface);border-radius:.45rem .45rem 0 0}
h2 {font-size:1rem;margin:0}.dots {display:flex;gap:.35rem}
i {width:.55rem;height:.55rem;border-radius:50%}
.terminal {padding:1rem;font:1rem/1.6 "JetBrainsMono Nerd Font Mono",monospace}
.terminal p {margin:0 0 .8rem}.heading,.command {color:var(--accent)}
.label {color:var(--section)}small {color:var(--muted)}.command span {color:var(--success)}
a {color:var(--text);text-underline-offset:.2em} a:focus-visible {outline:2px solid var(--accent)}
</style>
<h1>""" + title + """</h1>
""" + description + """
<main>
""" + "\n".join(cards) + "\n</main>\n").encode()
    return files


def validate_profiles(directory, slugs, *, config_name="config.ghostty"):
    ghostty = shutil.which("ghostty")
    if ghostty is None:
        raise ValueError("Ghostty is unavailable for native parser validation")
    with tempfile.TemporaryDirectory(prefix="panda-ghostty-parser-", dir="/tmp") as sandbox:
        home = Path(sandbox)
        env = {"PATH": os.defpath, "HOME": sandbox, "LANG": "C.UTF-8"}
        for key in ("CONFIG", "DATA", "STATE", "CACHE", "RUNTIME"):
            path = home / key.lower()
            path.mkdir(mode=0o700)
            env[f"XDG_{key}_DIR" if key == "RUNTIME" else f"XDG_{key}_HOME"] = str(path)
        for slug in slugs:
            config = directory / slug / config_name
            result = subprocess.run([ghostty, "+validate-config", f"--config-file={config}"],
                                    env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=15)
            if result.returncode or result.stdout or result.stderr:
                diagnostic = (result.stderr + result.stdout).strip()
                raise ValueError(f"{slug}: Ghostty validation returned {result.returncode}\n{diagnostic}")
            print(f"Ghostty parser accepted {slug}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="run installed Ghostty's native parser")
    args = parser.parse_args(argv)
    directory = None
    try:
        family = load_family(Path(__file__).resolve().parent.parent)
        files = preview_files(family)
        directory = Path(tempfile.mkdtemp(prefix="panda-ghostty-preview-", dir="/tmp"))
        for relative, data in files.items():
            path = directory / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        if args.validate:
            validate_profiles(directory, family)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Ghostty preview failed: {error}", file=sys.stderr)
        if directory is not None:
            print(f"Generated files: {directory}", file=sys.stderr)
        return 1
    print(directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
