"""Inspect and provision the explicitly selected Workspace shell files."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import uuid


REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "home/dot_config"
FISHER_COMMIT = "a04308be92daa6cfecdbb0ca58b1e8508664cff2"
FISHER_URL = f"https://raw.githubusercontent.com/jorgebucaran/fisher/{FISHER_COMMIT}/functions/fisher.fish"
# SHA-256 of the reviewed functions/fisher.fish blob at FISHER_COMMIT.
FISHER_SHA256 = "0fb6c81ae3003e95b5671766fa6c25c3597066e29965b7772f6c1b007387356d"
# Files installed by Fisher from the reviewed v11.0 release.
FZF_FILES = (
    "completions/fzf_configure_bindings.fish",
    "conf.d/fzf.fish",
    "functions/_fzf_configure_bindings_help.fish",
    "functions/_fzf_extract_var_info.fish",
    "functions/_fzf_preview_changed_file.fish",
    "functions/_fzf_preview_file.fish",
    "functions/_fzf_report_diff_type.fish",
    "functions/_fzf_report_file_type.fish",
    "functions/_fzf_search_directory.fish",
    "functions/_fzf_search_git_log.fish",
    "functions/_fzf_search_git_status.fish",
    "functions/_fzf_search_history.fish",
    "functions/_fzf_search_processes.fish",
    "functions/_fzf_search_variables.fish",
    "functions/_fzf_wrapper.fish",
    "functions/fzf_configure_bindings.fish",
)
GROUPS = {
    "fish": ("fish/config.fish", "fish/panda.fish",
             "fish/conf.d/panda-user-path.fish", "fish/fish_plugins"),
    "ghostty": ("ghostty/config.ghostty",),
    "kitty": ("kitty/kitty.conf",),
    "starship": ("starship.toml",),
}


class StageError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def report(operation, outcome, detail):
    with os.fdopen(os.dup(3), "w") as stream:
        print(operation, outcome, detail, sep="\t", file=stream)


def run(args, env, *, quiet=False, strict_stderr=False, timeout=20):
    try:
        result = subprocess.run(args, env=env, cwd=env["HOME"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if error.stderr:
            sys.stderr.buffer.write(error.stderr)
        if error.stdout:
            sys.stderr.buffer.write(error.stdout)
        raise StageError(f"{args[0]} timed out", 124) from error
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    if result.returncode or ((quiet or strict_stderr) and result.stderr) or (quiet and result.stdout):
        if result.stdout:
            sys.stderr.buffer.write(result.stdout)
        code = result.returncode or 1
        raise StageError(f"{args[0]} {args[1]} failed (exit {code})",
                         code if code > 0 else 128 - code)
    return result.stdout


class Home:
    """Address only regular files under a real HOME, without following links."""

    def __init__(self):
        raw_home = os.environ["HOME"]
        raw_config = os.environ.get("XDG_CONFIG_HOME") or f"{raw_home}/.config"
        self.root = Path(raw_home)
        config = Path(raw_config)
        for path in (self.root, config):
            if (not path.is_absolute() or path.anchor != "/" or path == Path("/")
                    or ".." in path.parts or any(ord(char) < 32 for char in str(path))):
                raise StageError(f"Unsupported HOME or XDG configuration path: {str(path)!r}")
        if self.root.resolve(strict=True) != self.root or not self.root.is_dir():
            raise StageError("HOME must be a real directory without symlink components")
        self.config = config.relative_to(self.root)
        if not self.config.parts:
            raise StageError("XDG_CONFIG_HOME must be a subdirectory of HOME")

    @contextmanager
    def parent(self, relative, create=False):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root, flags)
        try:
            for part in relative.parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def read(self, relative):
        try:
            with self.parent(relative) as parent:
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                fd = os.open(relative.name, flags, dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise StageError(f"Expected a regular file at {self.root / relative}")
                    return stream.read()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise StageError(f"Cannot safely inspect {self.root / relative}: {error}") from error

    def list_directory(self, relative):
        try:
            with self.parent(relative) as parent:
                fd = os.open(relative.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
                try:
                    return os.listdir(fd)
                finally:
                    os.close(fd)
        except FileNotFoundError:
            return []
        except OSError as error:
            raise StageError(f"Cannot safely inspect {self.root / relative}: {error}") from error

    def create(self, relative, data):
        # Link a complete file into place without overwriting anything that
        # appeared after review. Directory descriptors keep symlinks out.
        with self.parent(relative, create=True) as parent:
            temporary = f".panda-shell-{uuid.uuid4().hex}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            fd = os.open(temporary, flags, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                os.link(temporary, relative.name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=parent)


@dataclass(frozen=True)
class Target:
    source: Path
    relative: Path
    expected: bytes
    current: bytes | None


def fish_quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def plan(home, show):
    targets = {}
    preserved = set()
    # Workspace's legacy scope is under ~/.config even with a custom XDG root.
    # Check both roots for terminal fallbacks before creating any baseline.
    alternatives = {
        "ghostty": [home.config / "ghostty/config", Path(".config/ghostty/config"),
                    Path(".config/ghostty/config.ghostty")],
        "kitty": [Path(".config/kitty/kitty.conf")],
    }
    for group, files in GROUPS.items():
        entries = []
        for name in files:
            source = BASELINE / name
            relative = home.config / name
            entries.append(Target(source, relative, source.read_bytes(), home.read(relative)))
        primary = {entry.relative for entry in entries}
        other = [str(home.root / path) for path in dict.fromkeys(alternatives.get(group, ()))
                 if path not in primary and home.read(path) is not None]
        if group == "fish":
            snippets = home.config / "fish/conf.d"
            if any(name.endswith(".fish") and name != "panda-user-path.fish"
                   for name in home.list_directory(snippets)):
                other.append(f"other startup snippets in {home.root / snippets}")
            if home.read(Path(".fish_profile")) is not None:
                other.append(str(home.root / ".fish_profile"))
            prompt = home.config / "fish/functions/fish_prompt.fish"
            if home.read(prompt) is not None:
                other.append(str(home.root / prompt))
        override = {"kitty": "KITTY_CONFIG_DIRECTORY", "starship": "STARSHIP_CONFIG"}.get(group)
        if override and os.environ.get(override):
            other.append(f"{override} override")
        customized = [str(home.root / entry.relative) for entry in entries
                      if entry.current is not None and entry.current != entry.expected]
        if other or customized:
            preserved.add(group)
            if show:
                print(f"Preserve {group} (manual review): " + ", ".join(other + customized))
        targets[group] = entries
        if show:
            for entry in entries:
                destination = home.root / entry.relative
                if entry.current == entry.expected:
                    print(f"Already matches: {destination}")
                elif group not in preserved:
                    print(f"Would create: {destination}")
                    print(f"  Inspect: diff -u -- /dev/null {fish_quote(entry.source)}")
                elif entry.current is not None:
                    print(f"  Inspect: diff -u -- {fish_quote(destination)} {fish_quote(entry.source)}")
    return targets, preserved


@contextmanager
def sandbox():
    with tempfile.TemporaryDirectory(prefix="panda-shell-", dir="/tmp") as directory:
        env = {"HOME": directory, "PATH": os.environ.get("PATH", os.defpath),
               "LANG": "C.UTF-8", "TERM": "xterm-256color", "GSETTINGS_BACKEND": "memory",
               "NO_COLOR": "1"}
        for name in ("config", "data", "state", "cache", "runtime"):
            path = Path(directory) / name
            path.mkdir(mode=0o700)
            suffix = "DIR" if name == "runtime" else "HOME"
            env[f"XDG_{name.upper()}_{suffix}"] = str(path)
        yield env


def missing_targets(targets, preserved):
    return [entry for group, entries in targets.items() if group not in preserved
            for entry in entries if entry.current is None]


def portable(home, missing, preserved, mode):
    if mode == "apply" and missing:
        with sandbox() as env:
            args = ["chezmoi", "--source", REPO, "--destination", home.root, "--config",
                    "/dev/null", "--config-format", "toml", "--refresh-externals=never",
                    "--no-tty", "cat", "--"]
            # Confirm every literal source agrees with chezmoi's mapping before
            # creating any files. Map the logical .config paths to the selected XDG root.
            for entry in missing:
                logical = home.root / ".config" / entry.source.relative_to(BASELINE)
                if run([*args, logical], env) != entry.expected:
                    raise StageError(f"Chezmoi returned unexpected content for {logical}")
            for entry in missing:
                home.create(entry.relative, entry.expected)
                print(f"Created {home.root / entry.relative}")
    if preserved or (missing and mode != "apply"):
        detail = "customized groups preserved; review " + ", ".join(sorted(preserved)) if preserved else ""
        if missing and mode != "apply":
            detail = "; ".join(filter(None, (detail, f"{len(missing)} baseline files missing")))
        if missing and mode == "apply":
            detail = f"created {len(missing)} files; {detail}"
        report("configuration", "Pending manual action", detail)
    elif missing:
        report("configuration", "Completed", f"created {len(missing)} baseline files")
    else:
        report("configuration", "Already satisfied", "all scoped files match")


def plugin_specs():
    fisher, fzf = (BASELINE / "fish/fish_plugins").read_text().splitlines()
    if fisher != "jorgebucaran/fisher@4.4.8" or fzf != "PatrickF1/fzf.fish@v11.0":
        raise StageError("Review the repository fish_plugins manifest and update the bootstrap provenance")
    return fisher, fzf


def plugin_state(home):
    config = home.config / "fish"
    manifest = home.read(config / "fish_plugins") or b""
    variables = home.read(config / "fish_variables") or b""
    # Fish stores the Fisher registration as a universal variable using
    # hex escapes and x1e list separators. Read only this record, never
    # start Fish with user config or expose universal variable values.
    receipt = re.search(rb"(?m)^SETUVAR _fisher_plugins:([^\r\n]*)", variables)
    value = receipt[1] if receipt else b""
    value = re.sub(rb"\\x([0-9a-fA-F]{2})", lambda match: bytes.fromhex(match[1].decode()), value)
    return config, manifest.lower().splitlines(), value.lower().split(b"\x1e"), variables


def fisher_path_override(variables):
    return os.environ.get("fisher_path") or re.search(
        rb"(?m)^SETUVAR (?:--export )?fisher_path:", variables
    )


def fisher_readiness(home, preserved, mode, spec):
    config, manifest, receipts, variables = plugin_state(home)
    target = config / "functions/fisher.fish"
    existing = home.read(target)
    if fisher_path_override(variables):
        report("fisher", "Pending manual action", "Fisher path override detected; review the active installation")
        return False
    if existing is not None:
        verified = hashlib.sha256(existing).hexdigest() == FISHER_SHA256
        compatible = verified
        if (not compatible and re.search(rb"(?m)^\s*function fisher(?:\s|$)", existing)
                and re.search(rb"(?m)^\s*set --local fisher_version 4\.4\.8\s*$", existing)):
            with sandbox() as env:
                # Syntax-check without executing or copying a user's function to disk.
                result = subprocess.run(["fish", "--no-config", "-n"], input=existing, env=env,
                                        capture_output=True, timeout=10)
            compatible = result.returncode == 0
        if compatible:
            provenance = ("SHA-256 verified" if verified else "version declaration and syntax checked")
            report("fisher", "Already satisfied", f"existing Fisher 4.4.8 reused; {provenance}")
        else:
            report("fisher", "Pending manual action", "existing Fisher preserved; compatibility needs review")
        return compatible
    if (mode != "apply" or "fish" in preserved or b"_fisher" in variables
            or spec.lower().encode() not in manifest):
        report("fisher", "Pending manual action", "Fisher function missing; review the Fish configuration and plugin state")
        return False
    print(f"Downloading pinned Fisher source: {FISHER_URL}", flush=True)
    with sandbox() as env:
        # Retain the operator's network environment, while disabling curlrc
        # and keeping all downloaded bytes inside the disposable directory.
        downloaded = Path(env["HOME"]) / "fisher.fish"
        run(["curl", "-q", "--fail", "--show-error", "--silent", "--proto", "=https",
             "--max-time", "30", "--output", downloaded, FISHER_URL], os.environ, timeout=35)
        data = downloaded.read_bytes()
        if hashlib.sha256(data).hexdigest() != FISHER_SHA256:
            raise StageError("Fisher download failed SHA-256 verification")
        run(["fish", "--no-config", "-n", downloaded], env)
        home.create(target, data)
    report("fisher", "Completed", f"installed the SHA-256 verified Fisher function at {home.root / target}")
    return True


def fzf_readiness(home, spec, fisher_ready):
    config, manifest, receipts, _ = plugin_state(home)
    pin = spec.lower().encode()
    present = [bool(home.read(config / name)) for name in FZF_FILES]
    if fisher_ready and pin in manifest and pin in receipts and all(present):
        report("fzf-fish", "Already satisfied", f"{spec} registered with Fisher; expected files present")
        return
    detail = "partial registration or files; " if pin in receipts or any(present) else ""
    report("fzf-fish", "Pending manual action", f"{detail}review selective installation of {spec}")


def readiness(home, targets, preserved):
    def config_status(group, detail):
        entries = targets[group]
        if group in preserved:
            return "Pending manual action", f"{detail}; active custom configuration preserved"
        if any(home.read(entry.relative) != entry.expected for entry in entries):
            return "Pending manual action", f"{detail}; user baseline missing or differs"
        return "Already satisfied", detail

    def ghostty(env):
        sys.path.insert(0, str(REPO / "theme/panda/common"))
        from ghostty_preview import load_family, preview_files

        version = run(["ghostty", "+version"], env).decode().splitlines()
        if not version:
            raise StageError("Ghostty did not report a version")
        print(version[0])
        family = load_family(REPO / "theme/panda")
        files = preview_files(family)
        profiles = [f"{slug}/config.ghostty" for slug in family]
        if len(profiles) != 5:
            raise StageError("Expected five standalone Panda Ghostty profiles")
        help_text = run(["ghostty", "+help"], env)
        if b"+validate-config" not in help_text:
            return "Pending manual action", f"{version[0]}; five profiles render; native parser unavailable"
        for name in profiles:
            path = Path(env["HOME"]) / name
            path.parent.mkdir()
            path.write_bytes(files[name])
        configs = [BASELINE / "ghostty/config.ghostty", *(Path(env["HOME"]) / name for name in profiles)]
        for path in configs:
            print(f"Ghostty parser: {path.parent.name}/{path.name}", flush=True)
            run(["ghostty", "+validate-config", f"--config-file={path}"], env, quiet=True)
        print("Standalone profiles: python3 -B theme/panda/common/ghostty_preview.py --validate")
        return config_status("ghostty", f"{version[0]}; baseline and five profiles accepted by native parser")

    def kitty(env):
        version = run(["kitty", "--version"], env).decode().strip()
        parser = ("import sys; from kitty.config import load_config; bad = []; "
                  "load_config(sys.argv[1], accumulate_bad_lines=bad); "
                  "[print(line.exception, file=sys.stderr) for line in bad]; sys.exit(bool(bad))")
        run(["kitty", "+runpy", parser, BASELINE / "kitty/kitty.conf"], env, quiet=True)
        return config_status("kitty", f"{version}; baseline parsed")

    def starship(env):
        path = BASELINE / "starship.toml"
        with path.open("rb") as stream:
            tomllib.load(stream)
        output = run(["starship", "print-config"], {**env, "STARSHIP_CONFIG": str(path)},
                     strict_stderr=True)
        if not tomllib.loads(output.decode()):
            raise StageError("Starship returned an empty computed configuration")
        return config_status("starship", "baseline TOML and Starship computed configuration parsed")

    def font(env):
        families = run(["fc-match", "--format=%{family}", "JetBrainsMono Nerd Font Mono"], env)
        if b"JetBrainsMono Nerd Font Mono" not in families.split(b","):
            raise StageError("Fontconfig did not resolve JetBrainsMono Nerd Font Mono")
        return "Already satisfied", "Fontconfig resolved JetBrainsMono Nerd Font Mono"

    def fish_startup(env):
        local_bin = Path(env["HOME"]) / ".local/bin"
        local_bin.mkdir(parents=True)
        for entry in targets["fish"]:
            relative = entry.source.relative_to(BASELINE)
            path = Path(env["XDG_CONFIG_HOME"]) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(entry.expected)
        shutil.copyfile(BASELINE / "starship.toml", Path(env["XDG_CONFIG_HOME"]) / "starship.toml")
        script = (
            'source "$__fish_config_dir/conf.d/panda-user-path.fish"; or exit $status; '
            'source "$__fish_config_dir/config.fish"; or exit $status; '
            'begin; contains -- "$HOME/.local/bin" $fish_user_paths; '
            'or contains -- "$HOME/.local/bin" $PATH; end; or exit 1; '
            'abbr --query workstation; or exit 1; '
            'for tool in fzf fd bat starship; '
            'command -sq $tool; or begin; echo "Fish command missing: $tool" >&2; exit 127; end; end'
        )
        # Exercise both modes without executing vendor or user snippets.
        run(["fish", "--no-config", "-c", script], env, quiet=True)
        interactive = script + '; and functions fish_prompt | string match -qr "starship prompt"'
        run(["fish", "--no-config", "-i", "-c", interactive], env, quiet=True)
        detail = "disposable baseline loads in both modes; local PATH and fzf/fd/bat/Starship verified"
        return config_status("fish", detail)

    result = 0
    for operation, probe in (("ghostty", ghostty), ("kitty", kitty), ("starship", starship),
                             ("font", font), ("fish-startup", fish_startup)):
        try:
            with sandbox() as env:
                outcome, detail = probe(env)
            report(operation, outcome, detail)
        except (StageError, OSError, ValueError) as error:
            code = failure(operation, error)
            result = result or code
    return result


def failure(operation, error):
    code = getattr(error, "code", 127 if isinstance(error, FileNotFoundError) else 1)
    print(f"Shell tools {operation}: {error}", file=sys.stderr)
    report(operation, "Failed", f"(exit {code}) see the diagnostic above")
    return code


def main(mode, approved=""):
    operation = "configuration"
    try:
        home = Home()
        targets, preserved = plan(home, show=mode == "plan")
        fisher, fzf = plugin_specs()
        # Refuse unsupported plugin paths before applying any selected files.
        config, _, receipts, variables = plugin_state(home)
        fisher_path = config / "functions/fisher.fish"
        existing_fisher = home.read(fisher_path)
        for name in FZF_FILES:
            home.read(config / name)
        missing = missing_targets(targets, preserved)
        install_fisher = (existing_fisher is None and "fish" not in preserved
                          and b"_fisher" not in variables and not fisher_path_override(variables))
        planned = [(str(home.root / entry.relative), hashlib.sha256(entry.expected).hexdigest())
                   for entry in missing]
        if install_fisher:
            planned.append((str(home.root / fisher_path), FISHER_SHA256))
        plan_id = hashlib.sha256(repr(planned).encode()).hexdigest()
        if mode == "plan":
            if existing_fisher is not None:
                print(f"Existing Fisher will be preserved: {home.root / fisher_path}")
            elif install_fisher:
                print(f"Would create: {home.root / fisher_path}")
                print(f"Fisher download: {FISHER_URL} (SHA-256 checked)")
            else:
                print("Fisher function missing; review the existing Fish configuration and plugin state")
            if fzf.lower().encode() in receipts:
                print(f"Found Fisher registration for {fzf}; verify its entry points with --verify")
            else:
                print(f"fzf.fish is reviewed separately: {fzf}")
            with os.fdopen(os.dup(3), "w") as stream:
                print(plan_id, file=stream)
            return 0
        if mode == "apply" and plan_id != approved:
            raise StageError("The shell create plan changed after preview; review a fresh plan before applying")
        portable(home, missing, preserved, mode)
        operation = "fisher"
        fisher_ready = fisher_readiness(home, preserved, mode, fisher)
        operation = "fzf-fish"
        fzf_readiness(home, fzf, fisher_ready)
        return 0 if mode == "check" else readiness(home, targets, preserved)
    except (StageError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        if mode == "plan":
            print(f"Shell tools preflight: {error}", file=sys.stderr)
            return getattr(error, "code", 1)
        return failure(operation, error)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
