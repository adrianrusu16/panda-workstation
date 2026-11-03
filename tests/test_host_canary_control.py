"""Synthetic runtime descriptors and native relay packets only; no adapter runs."""
import importlib.util
from pathlib import Path
import hashlib
import json
import os
import stat
import unittest
from types import SimpleNamespace

BASE = Path(__file__).parent
if not (BASE / 'host_canary_lifecycle.py').is_file(): BASE = BASE

def load():
    spec = importlib.util.spec_from_file_location('control_test_api', BASE / 'host_canary_lifecycle.py')
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    return api

SESSION = 'a' * 32

class Kernel:
    def __init__(self):
        self.nodes, self.children, self.data = {}, {}, {}
        self.add(10, True)
        self.add(11, False, b'python', 0o755)
        self.children[10] = {'python': 11}
    def add(self, fd, directory, data=b'', mode=None):
        mode = mode if mode is not None else 0o700 if directory else 0o644
        self.nodes[fd] = dict(dev=1, ino=fd, uid=1000, gid=1000,
            mode=(stat.S_IFDIR if directory else stat.S_IFREG)|mode, nlink=2 if directory else 1,
            size=len(data), ctime=1, mtime=1, atime=1, mount=1, filesystem=0xEF53,
            namespace=((1, 2),(1, 3)), xattrs=(), flags=os.O_RDONLY|os.O_NOATIME, fdflags=1)
        self.children[fd], self.data[fd] = {}, data
    def identity(self): return 1000, 1000
    def snapshot(self, fd): return dict(self.nodes[fd])
    def entries(self, fd): return sorted(self.children[fd])
    def runtime_open(self, parent, name): return self.children[parent][name]
    def observe(self, parent, name): return self.snapshot(self.children[parent][name])
    def read(self, fd, count, offset): return self.data[fd][offset:offset+count]

class RuntimeTests(unittest.TestCase):
    def setUp(self): self.api, self.k = load(), Kernel()
    def digest(self):
        rows = [{'path':'','mode':0o700,'directory':True},
                {'path':'python','mode':0o755,'directory':False,'sha256':hashlib.sha256(b'python').hexdigest(),'bytes':6}]
        return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def test_runtime_refuses_unsupported_or_unapproved_tree_before_worker_start(self):
        for fault in ('symlink','foreign-mount','foreign-owner','hardlink','writable','digest','not-private'):
            with self.subTest(fault=fault):
                self.setUp()
                p=self.k.nodes[11]
                if fault=='symlink': p['mode']=stat.S_IFLNK|0o777
                elif fault=='foreign-mount': p['mount']=2
                elif fault=='foreign-owner': p['uid']=999
                elif fault=='hardlink': p['nlink']=2
                elif fault=='writable': p['mode']=stat.S_IFREG|0o666
                elif fault=='not-private': self.k.nodes[10]['mode']=stat.S_IFDIR|0o755
                digest='b'*64 if fault=='digest' else self.digest()
                with self.assertRaises((ValueError,OSError)):
                    self.api.RuntimeGrant(self.k,10,digest)
    def test_runtime_retains_original_tree_and_rejects_late_replacement_or_content(self):
        grant=self.api.RuntimeGrant(self.k,10,self.digest())
        grant.check()
        self.assertEqual(grant.file('/python'),b'python')
        for fault in ('replacement','content','foreign-child','descriptor','namespace'):
            with self.subTest(fault=fault):
                self.setUp(); grant=self.api.RuntimeGrant(self.k,10,self.digest())
                if fault=='replacement':
                    self.k.add(12,False,b'python',0o755); self.k.children[10]['python']=12
                elif fault=='content': self.k.data[11]=b'PYTHON'
                elif fault=='foreign-child': self.k.children[10]['foreign']=11
                elif fault=='descriptor': self.k.nodes[11]['fdflags']=0
                else: self.k.nodes[11]['namespace']=((9,9),(1,3))
                with self.assertRaises((ValueError,OSError)): grant.check()
    def test_btrfs_regular_directories_use_single_link_and_subvolume_roots_refuse(self):
        for pin in self.k.nodes.values(): pin['filesystem']=0x9123683E
        self.k.nodes[10]['nlink']=1
        self.api.RuntimeGrant(self.k,10,self.digest()).check()
        self.k.nodes[10]['ino']=256
        with self.assertRaises(ValueError): self.api.RuntimeGrant(self.k,10,self.digest())

class Ledger:
    def __init__(self): self.events, self.failure = [], None
    def append(self, value):
        if value['kind']==self.failure: raise OSError('injected ledger synchronization failure')
        self.events.append(value)

class Transport:
    def __init__(self, packets): self.packets, self.sent, self.failed = packets, [], False
    def receive(self, timeout):
        if not self.packets: raise TimeoutError('no closure evidence')
        return self.packets.pop(0)
    def check(self):
        if self.failed: raise OSError('original controller channel lost')
    def send(self, packet): self.check(); self.sent.append(packet)
    def bind_birth(self, pid, ns): return dict(pid=pid,namespace=ns,pidfd=40,nsfd=41)
    def wait_closed(self): return dict(helper_status=0,init_pidfd_exited=True,namespace_retained=True)

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.api, self.k, self.ledger = load(), Kernel(), Ledger()
        k=self.k
        k.children[10]={}
        for fd,name in ((12,'app'),(13,'bin')):
            k.add(fd,True); k.children[10][name]=fd
        for fd,parent,name,data,mode in ((14,13,'python3',b'python',0o755),
                 (15,12,'host_canary.py',b'engine',0o644),
                 (16,12,'host_canary_rpc.py',b'rpc',0o644),
                 (17,12,'host_canary_mediated.py',b'driver',0o644)):
            k.add(fd,False,data,mode); k.children[parent][name]=fd
        def rows(fd,path=''):
            p=k.nodes[fd]; directory=stat.S_ISDIR(p['mode'])
            row=dict(path=path,mode=stat.S_IMODE(p['mode']),directory=directory)
            if directory:
                return [row]+[item for name in sorted(k.children[fd]) for item in rows(k.children[fd][name],path+'/'+name if path else name)]
            row.update(sha256=hashlib.sha256(k.data[fd]).hexdigest(),bytes=len(k.data[fd])); return [row]
        digest=hashlib.sha256(self.api.canonical(rows(10))).hexdigest()
        self.runtime=self.api.RuntimeGrant(k,10,digest)
        k.add(20,True)
        self.birth=dict(k.nodes[20])
        owner=self
        class Store:
            def __init__(self):
                self.s=SimpleNamespace(k=k); self.program=SimpleNamespace(data=b'engine')
                self.views,self.programs,self.lease={}, {},None
                self.calls,self.preserved=[],False
            def restrict_plan(self,plan):
                if plan != [{'action':'status'}]: raise ValueError('test controller scope differs')
                self.bound_plan=plan
            def root_receipt(self): return dict(fd=20,pin=k.snapshot(20),birth=dict(owner.birth),session_id=SESSION)
            def dispatch(self,op,args):
                self.calls.append((op,args)); k.nodes[20]['ctime']+=1; return 1
            def preserve(self,reason): self.preserved=True
        self.store=Store()
        self.packets=[f'BIRTH {SESSION} 100 200 1 20',f'TASK {SESSION} 1 BIRTH 2 1',
            f'POLICY {SESSION} 1 2 1 10 broker-v1',f'TASK {SESSION} 2 EXEC 2 1',
            f'TASK {SESSION} 3 EXIT 2 0',f'DONE {SESSION} 0',f'CLOSED {SESSION}']
        self.transport=Transport(self.packets)
        k.process_transport=lambda *args:self.transport
    def start(self):
        return self.api.NativeLifecycle.start_mediated(self.k,self.ledger,4,'b'*64,SESSION,20,self.k.snapshot(20),
            runtime=self.runtime,store=self.store,plan=[{'action':'status'}])
    def test_preexec_policy_and_single_exec_are_required_before_broker_access(self):
        for index,replacement in ((2,f'POLICY {SESSION} 1 3 1 10 broker-v1'),
                  (2,f'POLICY {SESSION} 1 2 1 99 broker-v1'),
                  (2,f'TASK {SESSION} 2 EXEC 2 1'),
                  (3,f'TASK {SESSION} 2 BIRTH 3 2'),
                  (4,f'TASK {SESSION} 3 EXEC 2 1'),
                  (4,f'TASK {SESSION} 3 BIRTH 2 1'),
                  (4,f'RPC {SESSION} 2 2 {{}}'),
                  (4,f'RPC {SESSION} 1 3 {{}}'),
                  (4,f'VIOLATION {SESSION} SIGSYS')):
            with self.subTest(replacement=replacement):
                self.setUp();self.packets[index]=replacement;scope=self.start()
                with self.assertRaises((ValueError,OSError)): scope.run()
                self.assertFalse(scope.mediated_profile)
                self.assertTrue(self.store.preserved)
                self.assertEqual(self.store.calls,[])
                self.assertNotIn(f'STOP {SESSION}',self.transport.sent)
    def test_policy_and_ack_durability_failures_preserve_before_ack(self):
        for event in ('worker-policy','task','worker-complete','namespace-closed'):
            with self.subTest(event=event):
                self.setUp();scope=self.start();self.ledger.failure=event
                with self.assertRaises(OSError): scope.run();scope.finish()
                self.assertTrue(scope.preserved)
                if event=='worker-policy': self.assertNotIn(f'ACK {SESSION} 0',self.transport.sent)
    def test_missing_or_lost_controller_custody_prevents_completion(self):
        for fault in ('pending-rpc','lease','view','program','transport','runtime','closed'):
            with self.subTest(fault=fault):
                self.setUp();scope=self.start()
                if fault=='pending-rpc': scope._mediation[2].parts=[b'partial']
                elif fault=='lease': self.store.lease='original-lock'
                elif fault=='view': self.store.views['v']={}
                elif fault=='program': self.store.programs['g']='original'
                elif fault=='transport': self.transport.failed=True
                elif fault=='runtime': self.k.data[14]=b'foreign'
                else: self.packets[-1]='CLOSED foreign'
                with self.assertRaises((ValueError,OSError)): scope.run();scope.finish()
                self.assertFalse(scope.closed)
    def test_mediated_nonzero_or_stopped_plan_preserves_evidence_instead_of_teardown(self):
        self.packets[4]=f'TASK {SESSION} 3 EXIT 2 1'
        self.packets[5]=f'DONE {SESSION} 1'
        scope=self.start()
        with self.assertRaises(ValueError): scope.run()
        self.assertTrue(scope.preserved)
        self.assertTrue(self.store.preserved)
        self.assertNotIn(f'STOP {SESSION}',self.transport.sent)
        with self.assertRaises(ValueError): scope.finish()
    def test_registered_native_relay_rpc_refreshes_only_original_broker_pin(self):
        rpc_path=BASE/'host_canary_rpc.py'
        if not rpc_path.is_file(): rpc_path=BASE.parent/'theme/panda/common/host_canary_rpc.py'
        spec=importlib.util.spec_from_file_location('control_rpc_test',rpc_path)
        rpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(rpc)
        request=rpc.request_frames(SESSION,1,1,'create',{})[0].decode()
        digest=hashlib.sha256(rpc.pack({'ok':True,'result':1})).hexdigest()
        ack=rpc.frame(SESSION,1,1,'ack',digest=digest).decode()
        self.packets[4:4]=[f'RPC {SESSION} 1 2 {request}',f'RPC {SESSION} 1 2 {ack}']
        scope=self.start();self.assertEqual(scope.run(),0)
        self.assertTrue(scope.mediated_profile)
        self.assertEqual(scope.root_pin,self.k.snapshot(20))
        self.assertEqual(self.store.calls,[('create',{})])
        self.assertTrue(any(e['kind']=='broker-root-transition' for e in self.ledger.events))
        scope.finish();self.assertTrue(scope.closed)
        self.assertEqual(self.ledger.events[-1]['kind'],'namespace-closed')

if __name__=='__main__': unittest.main()
