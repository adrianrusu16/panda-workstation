"""Small stdlib-only guards around the official Serena/Codex setup command."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tomllib


# The CLI used to verify this bootstrap; newer working installs are preserved.
MIN_CODEX = (0, 160, 1)
SERENA_ARGS = {"--context=codex", "--project-from-cwd"}


def verify_codex():
    result = subprocess.run(["codex", "--version"], check=True, capture_output=True, text=True)
    match = re.fullmatch(r"codex-cli (\d+)\.(\d+)\.(\d+)\s*", result.stdout)
    if not match or tuple(map(int, match.groups())) < MIN_CODEX:
        raise RuntimeError("Codex CLI >= 0.160.1 is required; update your existing official installation")
    print(result.stdout.strip())


def valid_server(server):
    if not isinstance(server, dict):
        return False
    args = server.get("args", [])
    return ("url" not in server and server.get("command") == "serena"
            and server.get("enabled", True) is True
            and isinstance(args, list) and len(args) == 3
            and all(isinstance(arg, str) for arg in args)
            and args[0] == "start-mcp-server" and set(args[1:]) == SERENA_ARGS)


def open_config(path, flags):
    return os.open(path, flags | os.O_NONBLOCK)


def read_config(path):
    try:
        with open(path, "rb", opener=open_config) as config:
            if not stat.S_ISREG(os.fstat(config.fileno()).st_mode):
                raise RuntimeError("Codex config.toml must be a regular file")
            data = tomllib.load(config)
    except FileNotFoundError:
        data = {}
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("Codex config.toml is invalid; repair it before running setup") from error
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise RuntimeError("Codex mcp_servers must be a TOML table")
    server = servers.get("serena", {})
    if (not isinstance(server, dict) or not isinstance(server.get("args", []), list)
            or not all(isinstance(arg, str) for arg in server.get("args", []))):
        raise RuntimeError("Codex Serena settings are malformed; repair them before setup")
    return data


def unrelated_config(data):
    data = copy.deepcopy(data)
    servers = data.get("mcp_servers", {})
    servers.pop("serena", None)
    if not servers:
        data.pop("mcp_servers", None)
    return data


def setup_codex(home):
    config, hooks = home / "config.toml", home / "hooks.json"
    before = read_config(config)
    if valid_server(before.get("mcp_servers", {}).get("serena")):
        print("Serena MCP configuration already valid; config and hooks unchanged")
        return
    # Keep rollback data only in memory; never create a credential/config backup.
    originals = {p: p.read_bytes() if p.exists() else None for p in (config, hooks)}
    try:
        subprocess.run(["serena", "setup", "codex"], check=True, capture_output=True,
                       text=True, env={**os.environ, "CODEX_HOME": str(home)})
        after = read_config(config)
        if not valid_server(after.get("mcp_servers", {}).get("serena")):
            raise RuntimeError("Serena setup did not produce the expected enabled stdio MCP entry")
        if unrelated_config(before) != unrelated_config(after):
            raise RuntimeError("Serena setup changed unrelated Codex settings")
        old_server = before.get("mcp_servers", {}).get("serena", {})
        new_server = after["mcp_servers"]["serena"]
        if any(new_server.get(key) != value for key, value in old_server.items()
               if key not in ("command", "args", "enabled")):
            raise RuntimeError("Serena setup lost custom MCP settings")
        if (hooks.read_bytes() if hooks.exists() else None) != originals[hooks]:
            raise RuntimeError("Serena setup changed existing Codex hooks")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        for path, original in originals.items():
            current = path.read_bytes() if path.exists() else None
            if current != original:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
        raise RuntimeError("Serena setup failed preservation checks; original config/hooks restored") from error
    print("Official serena setup codex completed; unrelated settings and hooks preserved")


def verify_mcp():
    result = subprocess.run(["codex", "mcp", "get", "serena", "--json"],
                            check=True, capture_output=True, text=True)
    entry = json.loads(result.stdout)
    transport = entry.get("transport") if isinstance(entry, dict) else None
    if (not isinstance(transport, dict) or entry.get("enabled") is not True
            or transport.get("type") != "stdio"
            or not valid_server(transport)):
        raise RuntimeError("Codex CLI does not report the expected enabled Serena MCP server")
    print("Codex MCP verified: serena start-mcp-server --context=codex --project-from-cwd")


def report_mcp(home):
    try:
        configured = valid_server(read_config(home / "config.toml").get("mcp_servers", {}).get("serena"))
    except (OSError, RuntimeError):
        print("Pending manual action: review the Serena MCP entry in Codex config.toml.")
        return
    if configured:
        print("Serena MCP is configured in Codex.")
    else:
        print("Pending manual action: configure Serena MCP explicitly with "
              "fish bootstrap/dev/setup-ai-tools.fish --configure-codex-mcp.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("codex-version", "setup-codex", "verify-mcp", "report-mcp"))
    args = parser.parse_args()
    try:
        if args.action == "codex-version":
            verify_codex()
        elif args.action in ("setup-codex", "report-mcp"):
            home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
            if args.action == "setup-codex":
                setup_codex(home)
            else:
                report_mcp(home)
        else:
            verify_mcp()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # External command output and config values may contain private data.
        message = str(error) if isinstance(error, RuntimeError) else "AI tool verification failed"
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
