"""AI bootstrap contracts; external installers are replaced with local CLI fixtures."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bootstrap/dev/ai_tools.py"
SCRIPT = ROOT / "bootstrap/dev/setup-ai-tools.fish"


class CodexConfigContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.exists(), "AI config helper is not implemented")
        spec = importlib.util.spec_from_file_location("ai_tools", HELPER)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / "config.toml"
        self.hooks = self.home / "hooks.json"
        self.original = '# Keep this comment\nmodel = "custom-model"\n[mcp_servers.other]\ncommand = "other"\n'
        self.config.write_text(self.original)
        self.hooks.write_text('{"hooks":{"SessionStart":[{"hooks":[]}]},"custom":true}\n')

    def setup_command(self, *args, **kwargs):
        # Model only the external CLI boundary. Preservation/rollback is real code.
        self.config.write_text(self.original + '\n[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n')
        return subprocess.CompletedProcess(args, 0)

    def test_adds_serena_and_preserves_config_comments_and_hooks(self):
        hooks = self.hooks.read_bytes()
        with patch.object(self.api.subprocess, "run", side_effect=self.setup_command):
            self.api.setup_codex(self.home)
        self.assertTrue(self.config.read_text().startswith(self.original))
        self.assertEqual(self.hooks.read_bytes(), hooks)
        self.assertEqual(tomllib.loads(self.config.read_text())["mcp_servers"]["other"],
                         {"command": "other"})

    def test_second_run_does_not_write_or_invoke_setup(self):
        self.setup_command()
        before = (self.config.read_bytes(), self.config.stat().st_mtime_ns)
        with patch.object(self.api.subprocess, "run", side_effect=AssertionError("setup repeated")):
            self.api.setup_codex(self.home)
        self.assertEqual((self.config.read_bytes(), self.config.stat().st_mtime_ns), before)

    def test_malformed_mcp_settings_fail_before_external_setup(self):
        for content in ('mcp_servers = 7\n',
                        '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", {}, {}]\n'):
            with self.subTest(content=content):
                self.config.write_text(content)
                with patch.object(self.api.subprocess, "run", side_effect=AssertionError("setup called")):
                    with self.assertRaises(RuntimeError):
                        self.api.setup_codex(self.home)
                self.assertEqual(self.config.read_text(), content)

    def test_restores_both_files_when_setup_changes_unrelated_content(self):
        original = self.config.read_bytes(), self.hooks.read_bytes()

        def destructive(*args, **kwargs):
            self.setup_command()
            self.config.write_text(self.config.read_text().replace("custom-model", "lost-model"))
            self.hooks.write_text('{}')
            return subprocess.CompletedProcess(args, 0)

        with patch.object(self.api.subprocess, "run", side_effect=destructive):
            with self.assertRaises(RuntimeError):
                self.api.setup_codex(self.home)
        self.assertEqual((self.config.read_bytes(), self.hooks.read_bytes()), original)

    def test_stale_entry_does_not_lose_custom_serena_options(self):
        self.original += '\n[mcp_servers.serena]\ncommand = "obsolete"\nstartup_timeout_sec = 45\n'
        self.config.write_text(self.original)
        before = self.config.read_bytes()

        def drop_custom_options(*args, **kwargs):
            self.config.write_text('# Keep this comment\nmodel = "custom-model"\n[mcp_servers.other]\ncommand = "other"\n'
                '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n')
            return subprocess.CompletedProcess(args, 0)

        with patch.object(self.api.subprocess, "run", side_effect=drop_custom_options):
            with self.assertRaises(RuntimeError):
                self.api.setup_codex(self.home)
        self.assertEqual(self.config.read_bytes(), before)

    def test_invalid_toml_is_not_overwritten(self):
        self.config.write_text('[broken\n')
        with patch.object(self.api.subprocess, "run", side_effect=AssertionError("setup called")):
            with self.assertRaises((RuntimeError, ValueError)):
                self.api.setup_codex(self.home)
        self.assertEqual(self.config.read_text(), '[broken\n')

    def test_failed_setup_restores_original_and_does_not_print_config(self):
        original = self.config.read_bytes()

        def failed(*args, **kwargs):
            self.config.write_text('model = "changed"\n')
            raise subprocess.CalledProcessError(1, "serena", output="private content")

        with patch.object(self.api.subprocess, "run", side_effect=failed):
            with self.assertRaises(RuntimeError) as caught:
                self.api.setup_codex(self.home)
        self.assertNotIn("private content", str(caught.exception))
        self.assertEqual(self.config.read_bytes(), original)

    def test_codex_version_floor_and_newer_versions(self):
        for output, accepted in (("codex-cli 0.159.0", False), ("codex-cli 0.160.1", True),
                                 ("codex-cli 0.170.0", True), ("other 9.0.0", False)):
            with self.subTest(output=output):
                result = subprocess.CompletedProcess([], 0, stdout=output)
                with patch.object(self.api.subprocess, "run", return_value=result):
                    if accepted:
                        self.api.verify_codex()
                    else:
                        with self.assertRaises(RuntimeError):
                            self.api.verify_codex()


@unittest.skipUnless(shutil.which("fish"), "Fish is required")
class FishBootstrapContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), "AI bootstrap is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin",
                    "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "CODEX_HOME": str(self.home / ".codex"), "SERENA_HOME": str(self.home / ".serena"),
                    "UV_TOOL_DIR": str(self.home / "tools"), "UV_TOOL_BIN_DIR": str(self.bin)}
        self.fixture_cli = self.bin / "fixture-cli"
        self.fixture_cli.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ["HOME"])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (home / "calls.jsonl").open("a") as f: f.write(json.dumps([name, *args]) + "\\n")
if name == "uv":
    if args == ["--version"]: print("uv 0.12.23")
    elif args == ["tool", "dir"]: print(os.environ["UV_TOOL_DIR"])
    elif args[:2] == ["tool", "install"]:
        package = args[-1]
        assert package in ("serena-agent", "graphifyy"), args
        if package == "serena-agent":
            assert "3.14" in args, args
            target = pathlib.Path(os.environ["UV_TOOL_DIR"]) / "serena-agent/bin"
            target.mkdir(parents=True, exist_ok=True)
            (target / "python").write_text("#!/bin/sh\\necho 3.14\\n")
            (target / "python").chmod(0o755)
            (target / "serena").symlink_to(home / ".local/bin/fixture-cli")
            tool = "serena"
        else: tool = "graphify"
        (home / ".local/bin" / tool).symlink_to(home / ".local/bin/fixture-cli")
    else: raise SystemExit(2)
elif name == "codex":
    if args == ["--version"]: print("codex-cli 0.160.1")
    elif args == ["mcp", "get", "serena", "--json"]:
        print(json.dumps({"enabled": True, "transport": {"type": "stdio", "command": "serena",
              "args": ["start-mcp-server", "--context=codex", "--project-from-cwd"]}}))
    else: raise SystemExit(2)
elif name == "serena":
    if args == ["--version"]: print("Serena 1.7.0")
    elif args == ["init"]:
        p = pathlib.Path(os.environ["SERENA_HOME"]) / "serena_config.yml"
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text("language_backend: LSP\\n")
    elif args == ["setup", "codex"]:
        p = pathlib.Path(os.environ["CODEX_HOME"]) / "config.toml"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f: f.write('\\n[mcp_servers.serena]\\ncommand = "serena"\\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\\n')
    else: raise SystemExit(2)
elif name == "graphify":
    assert args in (["--help"], ["--version"]), "Project integration must never run"
    print("graphify 0.9.74")
''')
        self.fixture_cli.chmod(0o755)
        for tool in ("uv", "codex"):
            (self.bin / tool).symlink_to(self.fixture_cli)
        (self.bin / "python").symlink_to(shutil.which("python3"))

    def run_bootstrap(self):
        return subprocess.run(["fish", str(SCRIPT)], env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in (self.home / "calls.jsonl").read_text().splitlines()]

    def test_clean_first_run_then_unchanged_second_run(self):
        first = self.run_bootstrap()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn(["uv", "tool", "install", "--python", "3.14", "serena-agent"], self.calls())
        self.assertIn(["uv", "tool", "install", "graphifyy"], self.calls())
        managed = [self.home / ".codex/config.toml", self.home / ".serena/serena_config.yml",
                   self.home / ".config/fish/conf.d/panda-user-path.fish"]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in managed]
        call_count = len(self.calls())
        second = self.run_bootstrap()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual([(p.read_bytes(), p.stat().st_mtime_ns) for p in managed], before)
        second_calls = self.calls()[call_count:]
        self.assertFalse(any(c[:3] == ["uv", "tool", "install"] for c in second_calls))
        self.assertNotIn(["serena", "init"], second_calls)
        self.assertNotIn(["serena", "setup", "codex"], second_calls)
        path_check = subprocess.run(["fish", "-c",
            'source "$HOME/.config/fish/conf.d/panda-user-path.fish"; source "$HOME/.config/fish/conf.d/panda-user-path.fish"; '
            'count (string match -- "$HOME/.local/bin" $PATH)'],
            env={**self.env, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertEqual(path_check.stdout.strip(), "1")

    def test_missing_codex_stops_before_tool_installs(self):
        (self.bin / "codex").unlink()
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex", result.stdout + result.stderr)
        self.assertFalse(any(c[:3] == ["uv", "tool", "install"] for c in self.calls()))

    def test_shadowed_serena_is_rejected(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.bin / "serena").unlink()
        (self.bin / "serena").write_text('#!/bin/sh\necho "Serena 1.7.0"\n')
        (self.bin / "serena").chmod(0o755)
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uv environment", result.stdout + result.stderr)

    def test_unloadable_serena_config_is_reported(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        interpreter = self.home / "tools/serena-agent/bin/python"
        interpreter.write_text('#!/bin/sh\ncase "$*" in *SerenaConfig*) exit 1;; *) echo 3.14;; esac\n')
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Serena configuration", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
