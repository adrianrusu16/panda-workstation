"""Measure the injected four-phase controller; never execute OS adapters.

Fresh process per sample, real 30s lifecycle run deadlines, real full-prefix
ledger comparisons and synchronization calls over FakeKernel. Native latency,
fsync durability and kernel process custody are not measured or accepted.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
from unittest.mock import patch


def run(repo, out, *, linux_methods=False):
    path = repo / ('tests/host_canary_native_fixture.py' if linux_methods else 'tests/host_canary_phase_fixture.py')
    spec = importlib.util.spec_from_file_location('phase_performance_fixture', path)
    api = importlib.util.module_from_spec(spec); sys.modules[spec.name] = api; spec.loader.exec_module(api)
    bridge = api.Bridge(real_program=True) if linux_methods else None
    fixture = bridge.f if bridge is not None else api.Fixture(real_program=True)
    if bridge is not None:
        fixture.controller = bridge.controller
    phases, counts = [], Counter()
    ledger, kernel = fixture.s.ledger, fixture.k
    check = ledger.check
    def observed_check():
        counts['ledger_checks'] += 1
        counts['history_bytes_checked'] += len(ledger.history)
        return check()
    ledger.check = observed_check
    started, cpu = time.perf_counter(), time.process_time()
    success, failure = False, None
    try:
        controller = fixture.controller()
        for phase in ('A', 'B', 'C', 'D'):
            before = dict(counts)
            records, size, requests = ledger.sequence, len(ledger.history), controller.requests.total
            calls = len(kernel.calls)
            begin, begin_cpu = time.perf_counter(), time.process_time()
            try:
                # Only enrollment randomness is fixed; invocation identities stay fresh.
                with patch.object(fixture.mediated.api.os, 'urandom', return_value=bytes.fromhex('e' * 32)):
                    receipt = controller.run_phase(phase)
                row = dict(receipt, completed=True)
            except BaseException as exc:
                row = dict(phase=phase, completed=False, error=type(exc).__name__ + ': ' + str(exc))
                failure = row['error']
            row.update(elapsed_seconds=time.perf_counter() - begin, cpu_seconds=time.process_time() - begin_cpu,
                       process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       records=ledger.sequence - records, records_after=ledger.sequence,
                       ledger_bytes_added=len(ledger.history) - size, ledger_bytes_after=len(ledger.history),
                       requests=controller.requests.total - requests, requests_after=controller.requests.total,
                       checks={k: counts[k] - before.get(k, 0) for k in counts},
                       kernel_calls=dict(Counter(c[0] for c in kernel.calls[calls:])),
                       retained_rpc_payload_bytes=sum(sum(len(value[0]) for value in s.server.contents.values()) for s in controller.scopes))
            transport = fixture.transports[-1] if fixture.transports else None
            if transport is not None:
                row['wire'] = dict(frames_tx=transport.frames_tx, frames_rx=transport.frames_rx,
                    bytes_tx=transport.bytes_tx, bytes_rx=transport.bytes_rx,
                    stdout_bytes=len(transport.stdout), stderr_bytes=len(transport.stderr))
            if row.get('completed'):
                row['controller_overhead_seconds'] = row['seconds'] - row['worker_seconds']
                row['worker_deadline_margin_seconds'] = 30 - row['worker_seconds']
            phases.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
            if failure: break
        success = len(phases) == 4 and failure is None
        elapsed, cpu_elapsed = time.perf_counter() - started, time.process_time() - cpu
        # No teardown in timing: preservation and exact deletion have separate tests.
        execution_peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        history = bytes(ledger.history)
        kinds = Counter(json.loads(line)['event']['kind'] for line in history.splitlines())
        names = ('tests/host_canary_linux.py', 'tests/host_canary_native_fixture.py', 'tests/host_canary_phases.py', 'tests/host_canary_phase_fixture.py',
                 'tests/host_canary_runtime.py', 'tests/host_canary_broker.py', 'tests/host_canary_lifecycle.py',
                 'theme/panda/common/host_canary.py', 'theme/panda/common/host_canary_rpc.py',
                 'theme/panda/common/host_canary_mediated.py')
        result = dict(version=1, synthetic_only=True, native_custody_validated=False,
            success=success, failure=failure, concrete_linux_methods=linux_methods,
            native_transport_counts=None if bridge is None else dict(launches=bridge.launches, waits=bridge.waits, polls=bridge.polls), phases=phases, seconds=elapsed, cpu_seconds=cpu_elapsed,
            execution_process_peak_rss_kib=execution_peak_rss,
            harness_process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            records=ledger.sequence, ledger_bytes=len(history), ledger_sha256=hashlib.sha256(history).hexdigest(),
            evidence_kinds=dict(kinds), counts=dict(counts),
            source_sha256={name: hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in names},
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            environment=dict(python=sys.version, executable=sys.executable, platform=sys.platform,
                cpu_count=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)),
                hash_seed=os.environ.get('PYTHONHASHSEED'), rss_units='Linux ru_maxrss KiB',
                rss_scope='cumulative process high-water; phase endpoints are not independent phase peaks; harness peak includes evidence export/reporting'),
            limits=dict(worker_seconds=30, requests=4096, stdout_bytes=1048576, stderr_bytes=1048576,
                        history_bytes=67108864, record_bytes=4096, ledger_events=100000))
        out.write_text(json.dumps(result, indent=2) + '\n')
        return success
    finally:
        bridge.close() if bridge is not None else fixture.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--linux-methods', action='store_true', help='Concrete Linux methods over fake OS boundaries; never live adapters')
    args = parser.parse_args()
    if args.out.exists(): parser.error('existing measurements must be preserved; choose a new output path')
    raise SystemExit(0 if run(args.repo, args.out, linux_methods=args.linux_methods) else 1)
