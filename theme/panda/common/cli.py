"""Selection previews and explicitly enrolled Phase 3A fixture transactions."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

from palette import PaletteError, contrast_checks, load_family
from selection import ContextSignals, SelectionError, effective_decision, propose_command, select_auto
from state import StateError, read_state
from fixture_fs import FixtureError, initialize_fixture
from transaction import fixture_root, prepare_switch, switch_theme, recover, read_decision, inspect_fixture


def state_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    path = Path(root) if root else Path.home() / ".config"
    if not path.is_absolute():
        raise StateError("XDG_CONFIG_HOME must be absolute; no state was accessed")
    return path / "panda/theme-state.toml"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def main(argv=None, *, now_provider=_local_now) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="list, status, doctor, auto, flavor, next or previous")
    parser.add_argument("--state", type=Path, help="read an explicit isolated state fixture")
    parser.add_argument("--dry-run", action="store_true", help="preview an unapplied state proposal")
    parser.add_argument("--explain", action="store_true", help="explain auto without changing mode")
    parser.add_argument("--fixture-root", type=Path, help="enrolled /tmp/panda-theme-fixture-* root only")
    parser.add_argument("--allow-fixture-writes", action="store_true", help="explicit opt-in; never enables live changes")
    parser.add_argument("--recover", action="store_true", help="doctor: recover an interrupted fixture transaction")
    clock = parser.add_mutually_exclusive_group()
    clock.add_argument("--now", help="inject an ISO local datetime (optional timezone offset)")
    clock.add_argument("--no-time", action="store_true", help="simulate an unavailable local clock")
    parser.add_argument("--special", help="explicit special flavor")
    parser.add_argument("--project", help="explicit project identifier, never a path")
    parser.add_argument("--gaming", action="store_true", help="explicit gaming signal")
    parser.add_argument("--focus", action="store_true", help="explicit focus signal")
    args = parser.parse_args(argv)
    try:
        family = load_family(Path(__file__).resolve().parents[1])
        readonly = args.command in ("list", "status", "doctor")
        fixture = args.fixture_root
        if args.recover and args.command != "doctor":
            raise FixtureError("--recover requires doctor")
        if args.allow_fixture_writes and (fixture is None or args.dry_run or args.explain or
                                          (readonly and not args.recover)):
            raise FixtureError("fixture writes require an explicit root and a mutation command")
        if args.recover and (fixture is None or not args.allow_fixture_writes):
            raise FixtureError("recovery requires --fixture-root and --allow-fixture-writes; live recovery is disabled")
        if fixture is not None and args.state is not None:
            raise FixtureError("--state cannot override an enrolled fixture")
        if args.explain and (args.command != "auto" or args.dry_run):
            raise SelectionError("--explain requires auto and cannot be combined with --dry-run")
        if readonly and args.dry_run:
            raise SelectionError("--dry-run is for flavor, auto, next and previous proposals")
        signals = ContextSignals(args.special, args.project, args.gaming, args.focus)
        if args.command == "init-fixture":
            if (fixture is None or not args.allow_fixture_writes or args.now is not None or args.no_time
                    or args.special is not None or args.project is not None or args.gaming or args.focus):
                raise FixtureError("init-fixture requires only --fixture-root and --allow-fixture-writes")
            initialize_fixture(fixture)
            print("Phase 3A temporary fixture enrolled; no live integration")
            return 0
        if fixture is not None:
            fixture_root(fixture / "config", fixture / "state")
        if readonly and (args.now is not None or args.no_time or args.special is not None or
                         args.project is not None or args.gaming or args.focus):
            raise SelectionError("context and clock options are for selection previews")
        if args.command == "list":
            print("Phase 2 selection-only; no live application")
            for slug, theme in family.items():
                alias = f" (alias: {', '.join(theme.aliases)})" if theme.aliases else ""
                print(f"{slug}{alias}: {theme.name}")
            return 0
        path = fixture / "config/panda/theme-state.toml" if fixture is not None else (
            args.state if args.state is not None else state_path())
        state = read_state(path)
        if not args.allow_fixture_writes:
            print("Phase 3A selection/fixture preview; not applied; state unchanged")
        if args.command == "status":
            print(f"mode: {state.mode if state else 'unset'}")
            print(f"recorded active: {state.active if state else 'none'}")
            print(f"last manual: {state.last_manual or 'none' if state else 'none'}")
            recorded = read_decision(fixture / "config") if fixture is not None else None
            print(f"reason: {recorded.reason}" if recorded else
                  ("reason: historical reason unavailable" if state else "reason: no established state"))
            print("live appearance: unverified")
            return 0
        if args.command == "doctor":
            failed = sum(not c.passes for theme in family.values()
                         for c in contrast_checks(theme) if c.required)
            if failed:
                raise PaletteError("required palette contrast failed")
            print(f"palettes: {len(family)} valid; 140 required contrast pairs pass")
            print(f"state: {'valid' if state else 'absent; no established active theme'}")
            print("application adapters: deferred to Phase 3B; live appearance unverified")
            print("desktop/editor Tier 1 coverage: pending Phase 4")
            if fixture is not None:
                if args.recover:
                    result = recover(fixture / "config", fixture / "state")
                    print(f"fixture recovery: {result.rollback_status}")
                    for warning in result.warnings:
                        print(warning)
                    return 0 if result.success else 1
                for line in inspect_fixture(fixture / "config", fixture / "state"):
                    print(line)
            return 0
        if args.no_time:
            now = None
        elif args.now is not None:
            try:
                now = datetime.fromisoformat(args.now)
            except ValueError as error:
                raise SelectionError("--now must be an ISO local datetime") from error
        else:
            now = now_provider()
        decision = select_auto(now, signals)
        if args.command == "auto" and args.explain:
            effective = effective_decision(state, decision)
            print(f"mode: {state.mode if state else 'unset'}")
            print(f"candidate: {decision.slug}")
            print(f"source: {decision.source}")
            print(f"reason: {decision.reason}")
            print(f"manual blocks candidate: {'yes' if state and state.mode == 'manual' else 'no'}")
            print(f"effective selection: {effective.slug}")
            print(f"effective reason: {effective.reason}")
        else:
            proposal = propose_command(state, args.command, decision)
            proposed_decision = decision if proposal.mode == "auto" else None
            if fixture is not None and args.allow_fixture_writes:
                result = switch_theme(proposal, fixture / "config", fixture / "state", decision=proposed_decision)
                print(f"fixture transaction: {'verified' if result.success else 'failed'}")
                if result.success:
                    print(f"fixture recorded active: {result.active or 'none'}")
                else:
                    print(f"fixture last known-good selection: {result.active or 'none'}")
                print(f"rollback: {result.rollback_status}")
                for warning in result.warnings:
                    print(warning)
                if not result.success:
                    try:
                        fixture_root(fixture / "config", fixture / "state")
                        recorded = read_state(path)
                    except (OSError, StateError, FixtureError):
                        print("fixture recorded active: unknown/unverified (safe read failed; transaction unverified)")
                    else:
                        print(f"fixture recorded active: {recorded.active if recorded else 'none'} "
                              "(read-only observation; transaction unverified)")
                print("live appearance: unverified; Phase 3B disabled")
                return 0 if result.success else 1
            if not args.dry_run:
                raise SelectionError("live commands require separately authorized Phase 3B; use --dry-run for a proposal "
                                     "or auto --explain for read-only evaluation")
            if fixture is not None:
                plan = prepare_switch(proposal, fixture / "config", fixture / "state", decision=proposed_decision)
                for entry in plan.entries:
                    print(f"would {'keep' if entry.before == entry.after else 'replace' if entry.before else 'create'}: {entry.relative}")
            print(f"proposed mode: {proposal.mode}")
            print(f"selected candidate: {proposal.active}")
            print(f"last manual: {proposal.last_manual or 'none'}")
            print(f"source: {decision.source if proposal.mode == 'auto' else 'manual'}")
            print(f"reason: {decision.reason if proposal.mode == 'auto' else 'explicit manual command'}")
        project = "pandawave" if signals.project in ("pandawave", "wave") else (
            "other" if signals.project else "none")
        print(f"inputs: special={signals.special or 'none'} project={project} "
              f"gaming={str(signals.gaming).lower()} focus={str(signals.focus).lower()} "
              f"local-time={now.strftime('%H:%M%z') if now is not None else 'unavailable'}")
        return 0
    except (PaletteError, StateError, SelectionError, FixtureError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
