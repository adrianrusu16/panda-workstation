"""In-memory protocol tests: no socket, process or filesystem adapter."""
import importlib.util
from pathlib import Path
import unittest
import base64
import zlib
from unittest.mock import patch

SOURCE = Path(__file__).with_name('host_canary_rpc.py')
if not SOURCE.is_file():
    SOURCE = Path(__file__).resolve().parents[1] / 'theme/panda/common/host_canary_rpc.py'


def load():
    spec = importlib.util.spec_from_file_location('rpc_test', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Ledger:
    def __init__(self): self.events, self.failure = [], None
    def append(self, value):
        if value['kind'] == self.failure: raise OSError('injected sync failure')
        self.events.append(value)


class Store:
    def __init__(self): self.calls, self.preserved = [], False
    def dispatch(self, op, args):
        if self.preserved: raise ValueError('custody lost')
        self.calls.append((op, args))
        return args.get('value')
    def preserve(self, reason): self.preserved = True


class Wire:
    def __init__(self, server): self.server, self.reply, self.frames = server, None, []
    def write(self, fd, raw):
        self.frames.append(raw)
        self.reply = self.server.accept(raw)
        return len(raw)
    def read(self, fd, bound): return self.reply


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.api = load()
        self.store, self.ledger = Store(), Ledger()
        self.server = self.api.Server(self.store, self.ledger, 'a' * 32, 1)
        self.wire = Wire(self.server)
        self.client = self.api.Client(9, 'a' * 32, 1, io=self.wire)

    def test_partial_wrong_generation_duplicate_or_unbounded_request_never_mutates(self):
        for fault in ('session', 'epoch', 'seq', 'duplicate', 'too-large', 'corrupt'):
            with self.subTest(fault=fault):
                self.setUp()
                frames = self.api.request_frames('a' * 32, 1, 1, 'create', {'value': 'x' * 40000})
                frame = self.api.unpack(frames[0])
                if fault == 'session': frame['session'] = 'b' * 32
                elif fault == 'epoch': frame['epoch'] = 2
                elif fault == 'seq': frame['seq'] = 2
                elif fault == 'too-large': frame['total'] = 100000
                elif fault == 'corrupt': frame['data'] = '!!!!'
                if fault == 'duplicate':
                    self.server.accept(frames[0])
                    bad = frames[0]
                else: bad = self.api.pack(frame)
                with self.assertRaises(ValueError): self.server.accept(bad)
                self.assertEqual(self.store.calls, [])
                self.assertTrue(self.store.preserved)

    def test_failed_intent_or_result_or_ack_durability_preserves_and_denies_more_calls(self):
        for failure in ('rpc-content', 'rpc-intent', 'rpc-result', 'rpc-ack'):
            with self.subTest(failure=failure):
                self.setUp()
                self.ledger.failure = failure
                with self.assertRaises((OSError, ValueError)): self.client.call('create', {'value': 1})
                self.assertTrue(self.store.preserved)
                self.assertFalse(self.server.quiescent)
                if failure in ('rpc-content','rpc-intent'): self.assertEqual(self.store.calls, [])
                with self.assertRaises(ValueError): self.client.call('create', {'value': 2})

    def test_lost_reply_never_retries_mutation(self):
        class Dropped(Wire):
            def read(self, fd, bound): return b''
        self.client = self.api.Client(9, 'a' * 32, 1, io=Dropped(self.server))
        with self.assertRaises(ValueError): self.client.call('create', {'value': 1})
        with self.assertRaises(ValueError): self.client.call('create', {'value': 1})
        self.assertEqual(len(self.store.calls), 1)
        self.assertFalse(self.server.quiescent)

    def test_fragmented_request_and_result_commit_once_before_ack(self):
        value = 'x' * 60000
        self.assertEqual(self.client.call('create', {'value': value}), value)
        self.assertEqual(self.store.calls, [('create', {'value': value})])
        kinds = [event['kind'] for event in self.ledger.events if event['kind'] != 'rpc-content']
        self.assertEqual(kinds, ['rpc-intent', 'rpc-result', 'rpc-ack'])
        self.assertTrue(self.server.quiescent)
        self.assertGreater(len(self.wire.frames), 6)
        self.assertEqual(self.client.call('read', {'value': None}), None)

    def test_complete_request_and_result_bytes_are_retained_in_bounded_evidence(self):
        value='text'*20000
        self.client.call('create',{'value':value})
        content=[e for e in self.ledger.events if e['kind']=='rpc-content']
        self.assertTrue(content, 'hashes alone do not retain the authorized bytes')
        for direction,expected in (('request',{'op':'create','args':{'value':value}}),
                                   ('result',{'ok':True,'result':value})):
            records=[e for e in content if e['direction']==direction]
            self.assertEqual([e['part'] for e in records],list(range(len(records))))
            self.assertTrue(all(len(self.api.pack(e))<3500 for e in records))
            raw=zlib.decompress(b''.join(base64.b64decode(e['data'],validate=True) for e in records))
            self.assertEqual(self.api.unpack(raw),expected)

    def test_repeated_exact_content_references_already_durable_payload_without_truncation(self):
        value='repeat'*20000
        self.client.call('read',{'value':value})
        first=[e for e in self.ledger.events if e['kind']=='rpc-content']
        self.client.call('read',{'value':value})
        self.assertEqual([e for e in self.ledger.events if e['kind']=='rpc-content'],first)
        refs=[e for e in self.ledger.events if e['kind']=='rpc-content-reference']
        self.assertEqual(len(refs),2)
        self.assertTrue(all(e['source_seq']==1 and e['seq']==2 for e in refs))
        self.assertEqual({e['sha256'] for e in refs},{e['sha256'] for e in first})

    def test_failed_content_reference_sync_does_not_dispatch_the_repeated_request(self):
        for direction in ('request','result'):
            with self.subTest(direction=direction):
                self.setUp()
                self.client.call('read',{'value':'retained'})
                append=self.ledger.append
                def fail(value):
                    if value['kind']=='rpc-content-reference' and value['direction']==direction:
                        raise OSError('injected reference sync failure')
                    append(value)
                self.ledger.append=fail
                operation='read' if direction=='request' else 'create'
                with self.assertRaises(OSError): self.client.call(operation,{'value':'retained'})
                self.assertEqual(len(self.store.calls),1 if direction=='request' else 2)
                self.assertTrue(self.server.revoked)
                self.assertTrue(self.client.failed)
                self.assertFalse(self.server.quiescent)

    def test_retained_exact_payload_is_compared_without_recompressing_on_every_read(self):
        self.client.call('read',{'value':'stable'*20000})
        with patch.object(self.api.zlib,'compress',side_effect=AssertionError('retained content recompressed')):
            self.assertEqual(self.client.call('read',{'value':'stable'*20000}),'stable'*20000)

    def test_damaged_or_unbounded_retained_payload_never_authorizes_a_reference(self):
        for fault in ('truncated','trailing','different','oversized'):
            with self.subTest(fault=fault):
                self.setUp()
                self.client.call('read',{'value':1})
                digest=self.api.hashlib.sha256(self.api.pack({'op':'read','args':{'value':1}})).hexdigest()
                encoded,seq,direction=self.server.contents[digest]
                if fault=='truncated': encoded=encoded[:-1]
                elif fault=='trailing': encoded+=b'foreign'
                elif fault=='different': encoded=zlib.compress(b'other')
                else: encoded=zlib.compress(b'x'*(self.api.MAX_MESSAGE+1))
                self.server.contents[digest]=(encoded,seq,direction)
                with self.assertRaises(ValueError): self.client.call('read',{'value':1})
                self.assertEqual(len(self.store.calls),1)
                self.assertTrue(self.store.preserved)
                self.assertTrue(self.server.revoked)

    def test_shared_budget_charges_before_dispatch_and_cannot_reset_at_new_epoch(self):
        budget=self.api.RequestBudget(self.store,self.ledger,'a'*32)
        budget.open_epoch(1)
        self.server=self.api.Server(self.store,self.ledger,'a'*32,1,budget=budget)
        self.client=self.api.Client(9,'a'*32,1,io=Wire(self.server))
        self.assertEqual(self.client.call('read',{'value':1}),1)
        self.assertEqual(budget.total,1)
        self.server.retire();budget.close_epoch(1);budget.open_epoch(2)
        server=self.api.Server(self.store,self.ledger,'a'*32,2,budget=budget)
        client=self.api.Client(9,'a'*32,2,io=Wire(server))
        budget._total=self.api.MAX_REQUESTS
        before=len(self.store.calls)
        with self.assertRaises(ValueError):client.call('create',{})
        self.assertEqual(len(self.store.calls),before)
        self.assertTrue(self.store.preserved)

    def test_retired_epoch_replay_preserves_without_dispatch_or_erasing_evidence(self):
        self.client.call('read',{'value':1})
        contents=dict(self.server.contents)
        self.server.retire()
        self.assertTrue(self.server.quiescent)
        with self.assertRaises(ValueError):
            self.server.accept(self.api.request_frames('a'*32,1,2,'create',{})[0])
        self.assertEqual(len(self.store.calls),1)
        self.assertEqual(self.server.contents,contents)
        self.assertTrue(self.store.preserved)

    def test_retired_epoch_cache_remains_charged_in_one_aggregate_budget(self):
        budget=self.api.RequestBudget(self.store,self.ledger,'a'*32)
        servers=[]
        for epoch in (1,2):
            budget.open_epoch(epoch)
            server=self.api.Server(self.store,self.ledger,'a'*32,epoch,budget=budget)
            self.api.Client(9,'a'*32,epoch,io=Wire(server)).call('read',{'value':epoch})
            server.retire();budget.close_epoch(epoch);servers.append(server)
        self.assertEqual(budget.cache_bytes,sum(len(v[0]) for s in servers for v in s.contents.values()))
        self.assertEqual(budget.cache_entries,sum(len(s.contents) for s in servers))
        self.assertEqual(budget.cache_entries,4)

    def test_cache_byte_and_entry_ceiling_refuses_before_dispatch(self):
        for limit in ('MAX_CACHE_BYTES','MAX_CACHE_ENTRIES'):
            with self.subTest(limit=limit):
                self.setUp()
                budget=self.api.RequestBudget(self.store,self.ledger,'a'*32)
                budget.open_epoch(1)
                server=self.api.Server(self.store,self.ledger,'a'*32,1,budget=budget)
                client=self.api.Client(9,'a'*32,1,io=Wire(server))
                with patch.object(self.api,limit,0,create=True):
                    with self.assertRaises(ValueError):client.call('create',{'value':1})
                self.assertFalse(self.store.calls)
                self.assertTrue(self.store.preserved)
                self.assertTrue(server.revoked)

    def test_per_worker_exhaustion_preserves_even_when_called_outside_lifecycle(self):
        self.server.seq = self.api.MAX_REQUESTS + 1
        with self.assertRaises(ValueError): self.server.accept(b'{}')
        self.assertTrue(self.store.preserved)
        self.assertTrue(self.server.revoked)
        self.assertFalse(self.store.calls)

    def test_broker_error_is_terminal_and_not_a_false_success(self):
        def fail(op, args): raise OSError(5, 'injected partial operation')
        self.store.dispatch = fail
        with self.assertRaises(OSError): self.client.call('create', {})
        self.assertTrue(self.store.preserved)
        self.assertFalse(self.server.quiescent, 'failed broker result must never grant closure')
        self.assertTrue(self.server.revoked, 'another client must not resume after a failed result')
        with self.assertRaises(ValueError): self.client.call('read', {})


if __name__ == '__main__': unittest.main()
