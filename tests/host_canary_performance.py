"""Invoke the existing full mock test only. Never start a Host Canary worker.

Deep timing is separate from normal measurements. Counts are local injected
wrappers, never runtime configuration or production adapter instrumentation.
"""
import argparse
from collections import Counter
import cProfile
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch

def profile_rows(profiler):
    """Combine raw entries, including engine source loaded under two modules.

    pstats keys by (filename,line,name) and can overwrite distinct code objects
    from repeated source loads. Retain both here; use JSON for combined counts.
    """
    totals={}
    for entry in profiler.getstats():
        code=entry.code
        key=('~',0,code) if isinstance(code,str) else (code.co_filename,code.co_firstlineno,code.co_name)
        row=totals.setdefault(key,dict(file=key[0],line=key[1],name=key[2],
            primitive=0,calls=0,self_seconds=0.0,cumulative_seconds=0.0))
        row['primitive']+=entry.callcount-entry.reccallcount
        row['calls']+=entry.callcount
        row['self_seconds']+=entry.inlinetime
        row['cumulative_seconds']+=entry.totaltime
    return sorted(totals.values(),key=lambda row:row['self_seconds'],reverse=True)

def run(repo, out, mode):
    path = repo/'tests/test_host_canary_broker.py'
    spec=importlib.util.spec_from_file_location('benchmark_test',path)
    tests=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tests;spec.loader.exec_module(tests)
    stats=Counter(); timings=Counter(); actions=[]; objects={}; ordinal=Counter()
    original_load=tests.load
    instrumented=set();guards=[]

    def wrap(owner,name,label,kind=None):
        original=getattr(owner,name)
        if original in instrumented:return
        def measured(*args,**kwargs):
            stats[label]+=1
            if mode=='profile':
                start=time.perf_counter_ns()
                try:return original(*args,**kwargs)
                finally:timings[label]+=(time.perf_counter_ns()-start)/1e9
            return original(*args,**kwargs)
        instrumented.add(measured);setattr(owner,name,measured)

    def action(owner,name,label):
        original=getattr(owner,name)
        def measured(*args,**kwargs):
            ordinal[label]+=1; title=label+str(ordinal[label]) if label=='recover' else label
            kernel=objects['case'].k; ledger=objects['case'].s.ledger
            offset=len(kernel.calls); before=dict(stats); records=ledger.sequence; size=len(ledger.history)
            start=time.perf_counter();cpu=time.process_time()
            try:return original(*args,**kwargs)
            finally:
                elapsed=time.perf_counter()-start
                calls=Counter(c[0] for c in kernel.calls[offset:])
                actions.append(dict(action=title,seconds=elapsed,cpu_seconds=time.process_time()-cpu,
                    calls=dict(calls),counters={k:stats[k]-before.get(k,0) for k in stats},
                    records=ledger.sequence-records,journal_bytes_added=len(ledger.history)-size,
                    journal_bytes_after=len(ledger.history)))
        setattr(owner,name,measured)

    def loaded(name,path):
        api=original_load(name,path)
        filename=Path(path).name
        if filename=='host_canary_broker.py':
            for method,value in vars(api.runtime.LinuxKernel).items():
                if callable(value):
                    guard=patch.object(api.runtime.LinuxKernel,method,
                        side_effect=AssertionError('REAL LINUX ADAPTER FORBIDDEN: '+method))
                    guard.start();guards.append(guard)
            for method in ('start_worker','start_mediated_worker','teardown'):
                guard=patch.object(api.runtime.ProspectiveSession,method,
                    side_effect=AssertionError('LIFECYCLE/TEARDOWN FORBIDDEN: '+method))
                guard.start();guards.append(guard)
        if filename=='host_canary_rpc.py':
            objects['rpc']=api
            for method in ('accept','_retain'):wrap(api.Server,method,'rpc.'+method)
            init=api.Client.__init__
            def client_init(self,*a,**kw):
                init(self,*a,**kw); underlying=self.io
                class IO:
                    def write(inner,fd,raw):
                        stats['frames_tx']+=1;stats['frame_bytes_tx']+=len(raw)
                        return underlying.write(fd,raw)
                    def read(inner,fd,bound):
                        raw=underlying.read(fd,bound)
                        stats['frames_rx']+=1;stats['frame_bytes_rx']+=len(raw);return raw
                self.io=IO();objects['client']=self
            api.Client.__init__=client_init
        elif filename=='host_canary_mediated.py':
            objects['mediated']=api
            for method in ('initialize','provision','cleanup_outputs','close'):
                action(api.MediatedOperator,method,method)
            for method in ('install_minimal','recover'):
                action(api.api,method,method)
            execute=api.execute_plan
            def execute_plan(*a,**kw):
                start=time.perf_counter();cpu=time.process_time()
                def nonce(size):
                    if size!=16:raise AssertionError('unexpected random input in deterministic fixture')
                    return bytes.fromhex('e'*32)
                try:
                    with patch.object(api.api.os,'urandom',side_effect=nonce):
                        return execute(*a,**kw)
                finally:timings['plan']=time.perf_counter()-start;timings['plan_cpu']=time.process_time()-cpu
            api.execute_plan=execute_plan
        return api
    tests.load=loaded
    case=tests.BrokerTests('test_full_transaction_over_rpc_with_real_durable_ledger_stays_within_budgets')
    objects['case']=case
    try:case.setUp()
    except BaseException:
        for guard in reversed(guards):guard.stop()
        raise
    runtime=case.api.runtime;ledger=case.s.ledger; kernel=case.k
    # No Linux method is allowed even if a refactor accidentally selects one.
    check=runtime.DurableLedger.check
    def ledger_check(self):
        stats['ledger_checks']+=1;stats['history_bytes_requested']+=len(self.history)+1
        return check(self)
    runtime.DurableLedger.check=ledger_check
    for name in ('check','append'):wrap(runtime.DurableLedger,name,'ledger.'+name)
    for name in ('check','_verify','_parent_transition'):wrap(runtime.ProspectiveSession,name,'session.'+name)
    for name in ('dispatch','read','expect','_record_transition','_managed_intent','root_receipt'):
        if hasattr(case.api.BrokerStore,name):wrap(case.api.BrokerStore,name,'broker.'+name)
    read=kernel.read
    class Compared:
        def __init__(self,raw):self.raw=raw
        def __ne__(self,other):
            stats['history_comparisons']+=1;stats['history_bytes_compared']+=len(self.raw)
            if mode=='profile':
                start=time.perf_counter_ns();answer=self.raw!=other
                timings['history_comparison']+=(time.perf_counter_ns()-start)/1e9;return answer
            return self.raw!=other
    def read_observed(fd,count,offset):
        raw=read(fd,count,offset)
        if fd==ledger.fd:
            stats['history_read_calls']+=1;stats['history_bytes_returned']+=len(raw)
            return Compared(raw)
        return raw
    kernel.read=read_observed
    profile=cProfile.Profile() if mode=='profile' else None
    start=time.perf_counter();cpu=time.process_time()
    try:
        if profile:profile.enable()
        case.test_full_transaction_over_rpc_with_real_durable_ledger_stays_within_budgets()
        if profile:profile.disable()
        elapsed=time.perf_counter()-start;cpu_elapsed=time.process_time()-cpu
    finally:
        if profile:profile.disable()
        for guard in reversed(guards):guard.stop()
    # Parse/count evidence after timed body, never substitute this for validation.
    history=bytes(ledger.history)  # immutable retained evidence, not a live buffer alias
    kinds=Counter(json.loads(line)['event']['kind'] for line in history.splitlines())
    sources={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        repo/'tests/host_canary_runtime.py',repo/'tests/host_canary_broker.py',
        repo/'tests/test_host_canary_broker.py',repo/'tests/test_host_canary_runtime.py',
        repo/'theme/panda/common/host_canary.py',
        repo/'theme/panda/common/host_canary_mediated.py',repo/'theme/panda/common/host_canary_rpc.py']}
    result=dict(instrumentation_version=3,mode=mode,mock_only=True,success=True,seconds=elapsed,cpu_seconds=cpu_elapsed,
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        journal_sha256=hashlib.sha256(history).hexdigest(),
        plan_seconds=timings['plan'],plan_cpu_seconds=timings['plan_cpu'],
        residual_seconds=timings['plan']-sum(a['seconds'] for a in actions),
        actions=actions,counters=dict(stats),inclusive_seconds=dict(timings),
        kernel_calls=dict(Counter(c[0] for c in kernel.calls)),evidence_kinds=dict(kinds),
        budgets=case.rpc_budget_evidence,source_sha256=sources,
        environment=dict(python=sys.version,executable=sys.executable,platform=platform.platform(),
            machine=platform.machine(),cpu_count=os.cpu_count(),affinity=sorted(os.sched_getaffinity(0)),
            hash_seed=os.environ.get('PYTHONHASHSEED'),isolated=sys.flags.isolated,
            ignore_environment=sys.flags.ignore_environment,hash_randomization=sys.flags.hash_randomization,
            fake_uid=kernel.uid,fake_gid=kernel.gid,
            enrollment_id='e'*32,gc_enabled=gc.isenabled(),
            perf_clock=time.get_clock_info('perf_counter').implementation),
        instrumentation='in-memory FakeKernel + existing test; action timers and counts; proxy exact byte comparisons; profile times overlap')
    if profile:
        profile.dump_stats(str(out.with_suffix('.pstats')))
        result['profile']=profile_rows(profile)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),seconds=elapsed,plan_seconds=timings['plan'],
                         actions=[(a['action'],a['seconds']) for a in actions],budgets=result['budgets']),indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--mode',choices=('counts','profile'),default='counts')
    args=parser.parse_args()
    if args.out.exists() or args.mode=='profile' and args.out.with_suffix('.pstats').exists():
        parser.error('use a new output path; existing performance evidence is retained')
    run(args.repo,args.out,args.mode)
