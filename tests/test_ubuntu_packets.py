"""Actual packet writer/reader/upload handoff over synthetic receipt bytes."""
import importlib
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_ubuntu_verification import NOW, protocol_fixture, runner_context

S4=Path(__file__).resolve().parent/'native/external_vm/s4'


class UbuntuPackets(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(S4)); self.addCleanup(sys.path.remove,str(S4))
        self.p=importlib.import_module('ubuntu_packets')
        self.protocol=importlib.import_module('ubuntu_verification')
        pins,bootstrap,blobs,ring,verifier,toolchain=protocol_fixture()
        for obj,name,value in ((self.protocol,'load_references',(pins,bootstrap)),
                               (self.protocol.consistency,'load_pins',bootstrap)):
            mock=patch.object(obj,name,return_value=value); mock.start(); self.addCleanup(mock.stop)
        bundle=self.protocol.verify_ubuntu(runner_context(),b'ID=ubuntu\nVERSION_ID=24.04\n',NOW,ring,toolchain,
                                           lambda name,url,size:blobs[name],verifier,None)
        self.docs={name+'.json':self.protocol.canonical(row) for name,row in bundle['receipts'].items()}
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name); self.dest=self.root/'panda-ubuntu-bootstrap-verification'
        self.context={'job':{'run_id':'123','attempt':'1'},'hardware_attested':False}

    def gate(self,result):
        output=self.root/'github-output'; output.write_bytes(b''); output.chmod(0o600)
        with patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),'PACKET_TOKEN':result['packet_token'] or '',
                                    'GITHUB_OUTPUT':str(output)}):
            try: self.p.github_upload_gate()
            except (ValueError,OSError):
                self.assertEqual(output.read_bytes(),b''); raise
        text=output.read_text(); self.assertIn('complete=true\n',text)
        paths=text.split('paths<<PACKET_PATHS\n',1)[1].split('\nPACKET_PATHS\n',1)[0].splitlines()
        self.assertEqual(set(paths),{str(path) for path in self.dest.iterdir()})
        self.assertTrue(all(Path(path).is_file() for path in paths))
        return self.p.validate_packet(self.dest,expected_token=result['packet_token'])

    def test_success_and_explicit_failure_use_the_same_independent_upload_gate(self):
        for failure in (None,ValueError('synthetic failure')):
            with self.subTest(failure=failure):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context,failure=failure)
                self.assertEqual(result['exit_code'],0 if failure is None else 78)
                packet=self.gate(result)
                self.assertEqual(packet['packet_type'],'success' if failure is None else 'failure')
                self.assertIn('completion.json',packet['files'])
                if failure is not None: self.assertNotIn('elf-closure.json',packet['files'])
                shutil.rmtree(self.dest)

    def test_partial_write_failure_falls_back_to_a_complete_failure_packet(self):
        original=os.write; tripped=False
        def fail(fd,raw):
            nonlocal tripped
            if not tripped: tripped=True; raise OSError('synthetic write failure')
            return original(fd,raw)
        with patch.object(self.p.os,'write',side_effect=fail):
            result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(result['exit_code'],78)
        self.assertEqual(self.gate(result)['packet_type'],'failure')
        self.assertEqual(list(self.root.glob('.panda-packet-*')),[])

    def test_no_packet_or_wrong_publication_token_cannot_open_the_upload_gate(self):
        with self.assertRaises((ValueError,OSError)): self.gate({'packet_token':None})
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        with self.assertRaises(ValueError): self.gate({'packet_token':'0'*64})
        self.assertEqual(self.gate(result)['packet_type'],'success')

    def test_extra_missing_and_corrupted_files_are_not_upload_eligible(self):
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        extra=self.dest/'payload.deb'; extra.write_bytes(b'not a package')
        with self.assertRaises(ValueError): self.gate(result)
        extra.unlink()
        path=self.dest/'authorization-state.json'; path.write_bytes(b'{}\n')
        with self.assertRaises(ValueError): self.gate(result)
        path.unlink()
        with self.assertRaises(ValueError): self.gate(result)

    def test_every_individual_write_and_sync_position_falls_back_completely(self):
        # Thirteen success files and their fsyncs, followed by two directory fsyncs.
        for operation, count in (('write',13),('fsync',15)):
            for position in range(1,count+1):
                with self.subTest(operation=operation,position=position):
                    original=getattr(os,operation); calls=0
                    def fail(*args):
                        nonlocal calls
                        calls+=1
                        if calls==position: raise OSError('synthetic filesystem failure')
                        return original(*args)
                    with patch.object(self.p.os,operation,side_effect=fail):
                        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                    self.assertEqual(result['exit_code'],78)
                    self.assertEqual(self.gate(result)['packet_type'],'failure')
                    self.assertEqual(list(self.root.glob('.panda-packet-*')),[])
                    shutil.rmtree(self.dest)

    def test_positive_short_writes_complete_but_zero_writes_fail_closed(self):
        original=os.write
        with patch.object(self.p.os,'write',side_effect=lambda fd,raw:original(fd,raw[:max(1,len(raw)//2)])):
            result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(self.gate(result)['packet_type'],'success'); shutil.rmtree(self.dest)
        with patch.object(self.p.os,'write',return_value=0):
            result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(result,{'exit_code':78,'packet_token':None})
        self.assertFalse(self.dest.exists()); self.assertEqual(list(self.root.glob('.panda-packet-*')),[])
        with self.assertRaises(ValueError): self.gate(result)

    def test_completion_creation_failure_and_partial_completion_fall_back(self):
        original_open=os.open; original_write=os.write
        for kind in ('create','partial'):
            descriptors={}; tripped=False; partial=False
            def opened(path,flags,*args,**kwargs):
                nonlocal tripped
                if path=='completion.json' and kind=='create' and not tripped:
                    tripped=True; raise OSError('completion creation failure')
                fd=original_open(path,flags,*args,**kwargs)
                if flags & os.O_WRONLY: descriptors[fd]=path
                return fd
            def written(fd,raw):
                nonlocal tripped,partial
                if descriptors.get(fd)=='completion.json' and kind=='partial' and not tripped:
                    if not partial: partial=True; return original_write(fd,raw[:5])
                    tripped=True; raise OSError('partial completion write')
                return original_write(fd,raw)
            with self.subTest(kind=kind),patch.object(self.p.os,'open',side_effect=opened),patch.object(self.p.os,'write',side_effect=written):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
            self.assertTrue(tripped); self.assertEqual(result['exit_code'],78)
            self.assertEqual(self.gate(result)['packet_type'],'failure'); shutil.rmtree(self.dest)
            self.assertEqual(list(self.root.glob('.panda-packet-*')),[])

    def test_atomic_publication_failure_and_failed_fallback_expose_no_partial_packet(self):
        original=self.p._rename_absent; calls=0
        def fail_first(*args):
            nonlocal calls
            calls+=1
            if calls==1: raise OSError('publication failed')
            return original(*args)
        with patch.object(self.p,'_rename_absent',side_effect=fail_first):
            result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(result['exit_code'],78); self.assertEqual(self.gate(result)['packet_type'],'failure')
        shutil.rmtree(self.dest)
        for operation in ('_rename_absent','_write_all'):
            with self.subTest(operation=operation),patch.object(self.p,operation,side_effect=OSError('persistent failure')):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
            self.assertEqual(result,{'exit_code':78,'packet_token':None}); self.assertFalse(self.dest.exists())
            self.assertEqual(list(self.root.glob('.panda-packet-*')),[])
            with self.assertRaises(ValueError): self.gate(result)

    def test_atomic_no_replace_rejects_a_destination_created_during_publication(self):
        original=self.p._rename_absent; inode=None
        def race(*args):
            nonlocal inode
            if not self.dest.exists(): self.dest.mkdir(mode=0o700); inode=self.dest.stat().st_ino
            return original(*args)
        with patch.object(self.p,'_rename_absent',side_effect=race):
            result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(result['packet_token'],None); self.assertEqual(self.dest.stat().st_ino,inode)
        self.assertEqual(list(self.dest.iterdir()),[])
        with self.assertRaises(ValueError): self.gate(result)

    def test_every_failure_fallback_write_and_sync_position_also_fails_closed(self):
        for operation,count in (('write',6),('fsync',8)):
            for position in range(1,count+1):
                with self.subTest(operation=operation,position=position):
                    original=getattr(os,operation); fallback=False; calls=0
                    def publication(*args):
                        nonlocal fallback
                        fallback=True
                        raise OSError('initial publication failure')
                    def fail(*args):
                        nonlocal calls
                        if fallback:
                            calls+=1
                            if calls==position: raise OSError('fallback filesystem failure')
                        return original(*args)
                    with patch.object(self.p,'_rename_absent',side_effect=publication),patch.object(self.p.os,operation,side_effect=fail):
                        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                    self.assertEqual(calls,position)
                    self.assertEqual(result,{'exit_code':78,'packet_token':None}); self.assertFalse(self.dest.exists())
                    self.assertEqual(list(self.root.glob('.panda-packet-*')),[])
                    with self.assertRaises(ValueError): self.gate(result)

    def test_every_packet_file_missing_corrupted_or_replaced_is_refused(self):
        names=sorted(self.p.SUCCESS|self.p.COMMON)
        self.assertEqual(len(names),13)
        for name in names:
            for change in ('missing','corrupted','replaced'):
                with self.subTest(name=name,change=change):
                    result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                    path=self.dest/name
                    if change=='missing': path.unlink()
                    elif change=='corrupted': path.write_bytes(b'{}\n')
                    else:
                        replacement=self.root/'replacement'; replacement.write_bytes(path.read_bytes()); replacement.chmod(0o600)
                        os.replace(replacement,path)
                    with self.assertRaises((ValueError,OSError)): self.gate(result)
                    shutil.rmtree(self.dest)

    def test_file_types_ownership_modes_and_directory_modes_are_checked(self):
        for kind in ('symlink','hardlink','fifo','directory','mode','owner','root-mode'):
            with self.subTest(kind=kind):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                path=self.dest/'authorization-state.json'; original_fstat=os.fstat; target=path.stat().st_ino
                if kind in ('symlink','hardlink','fifo','directory'):
                    outside=self.root/'outside'; outside.write_bytes(path.read_bytes()); outside.chmod(0o600); path.unlink()
                    if kind=='symlink': path.symlink_to(outside)
                    elif kind=='hardlink': os.link(outside,path)
                    elif kind=='fifo': os.mkfifo(path,0o600)
                    else: path.mkdir(mode=0o700)
                elif kind=='mode': path.chmod(0o640)
                elif kind=='root-mode': self.dest.chmod(0o755)
                def wrong_owner(fd):
                    info=original_fstat(fd)
                    if kind=='owner' and info.st_ino==target:
                        values={key:getattr(info,key) for key in dir(info) if key.startswith('st_')}
                        values['st_uid']=os.getuid()+1
                        return SimpleNamespace(**values)
                    return info
                with patch.object(self.p.os,'fstat',side_effect=wrong_owner),self.assertRaises((ValueError,OSError)): self.gate(result)
                shutil.rmtree(self.dest)

    def test_mutation_during_validation_is_detected_before_handoff(self):
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        original=self.p._documents
        def change(*args):
            value=original(*args)
            (self.dest/'authorization-state.json').chmod(0o640)
            return value
        with patch.object(self.p,'_documents',side_effect=change),self.assertRaisesRegex(ValueError,'member changed'):
            self.p.validate_packet(self.dest,expected_token=result['packet_token'])

    def test_numeric_manifest_types_and_invalid_packet_combinations_are_rejected(self):
        for field in ('schema_version','directory','files','packet_type'):
            with self.subTest(field=field):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                path=self.dest/'completion.json'; value=json.loads(path.read_bytes())
                if field=='schema_version': value[field]=1.0
                elif field=='directory': value[field]['device']=float(value[field]['device'])
                elif field=='files': value[field]['SHA256SUMS']['bytes']=float(value[field]['SHA256SUMS']['bytes'])
                else: value[field]='failure'
                path.write_bytes(self.protocol.canonical(value))
                with self.assertRaises(ValueError): self.p.validate_packet(self.dest)
                with self.assertRaises(ValueError): self.gate(result)
                shutil.rmtree(self.dest)
        for docs,kind in (({**self.docs,**self.p.failure_documents('runner-admission',ValueError())},'success'),
                          (self.docs,'failure'),({'authorization-state.json':self.docs['authorization-state.json']},'failure'),
                          ({'../payload.json':b'{}'},'success')):
            with self.subTest(kind=kind),self.assertRaises(ValueError): self.p.publish_packet(self.dest,docs,self.context,packet_type=kind)
        self.assertFalse(self.dest.exists())

    def test_read_only_validator_and_current_invocation_handoff_are_required(self):
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        before={path.name:(path.read_bytes(),path.stat().st_mode,path.stat().st_mtime_ns) for path in self.dest.iterdir()}
        with patch.object(self.p.os,'write',side_effect=AssertionError('validator wrote')):
            self.p.validate_packet(self.dest,expected_token=result['packet_token'])
        self.assertEqual(before,{path.name:(path.read_bytes(),path.stat().st_mode,path.stat().st_mtime_ns) for path in self.dest.iterdir()})
        stale=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        self.assertEqual(stale,{'exit_code':78,'packet_token':None})
        with self.assertRaises(ValueError): self.gate(stale)

    def test_self_consistent_file_checksums_do_not_override_context_or_packet_semantics(self):
        for kind in ('context-binding','run-context'):
            with self.subTest(kind=kind):
                result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
                path=self.dest/(kind+'.json'); value=json.loads(path.read_bytes())
                if kind=='context-binding': value['run_context_sha256']='0'*64
                else: value['hardware_attested']=True
                raw=self.protocol.canonical(value); path.write_bytes(raw); info=path.stat()
                manifest_path=self.dest/'completion.json'; manifest=json.loads(manifest_path.read_bytes())
                manifest['files'][path.name]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),device=info.st_dev,
                    inode=info.st_ino,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)
                manifest_path.write_bytes(self.protocol.canonical(manifest))
                with self.assertRaises(ValueError): self.p.validate_packet(self.dest)
                with self.assertRaises(ValueError): self.gate(result)
                shutil.rmtree(self.dest)
        failure=self.p.failure_documents('runner-admission',ValueError())
        row=json.loads(failure['failure.json']); row['evidence_complete']=True
        failure['failure.json']=self.protocol.canonical(row)
        with self.assertRaises(ValueError): self.p.publish_packet(self.dest,failure,self.context,packet_type='failure')

    def test_directory_entry_scan_stops_at_the_packet_budget(self):
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context)
        visited=[]
        class Entries:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def __iter__(self):
                for i in range(14):
                    visited.append(i)
                    yield SimpleNamespace(name='extra-'+str(i))
                raise AssertionError('directory scan exceeded its entry budget')
        with patch.object(self.p.os,'scandir',return_value=Entries()),self.assertRaisesRegex(ValueError,'entry budget'):
            self.gate(result)
        self.assertEqual(len(visited),14)

    def test_actual_disabled_workflow_script_consumes_only_validated_paths(self):
        workflow=(S4.parents[3]/'.github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled').read_text()
        block=workflow.split('- name: Validate the complete published evidence packet\n',1)[1]
        script=textwrap.dedent(block.split('        run: |\n',1)[1].split('\n      - name:',1)[0])
        self.assertIn("steps.packet.outcome == 'success' && steps.packet.outputs.complete == 'true'",workflow)
        self.assertIn('path: ${{ steps.packet.outputs.paths }}',workflow)
        self.assertNotIn('/*.json',workflow)
        result=self.p.publish_with_fallback(self.dest,self.docs,self.context,failure=ValueError('synthetic'))
        output=self.root/'workflow-output'; output.touch(mode=0o600)
        with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}): self.p.github_publication_handoff(result['packet_token'])
        token=output.read_text().strip().removeprefix('packet_token='); self.assertEqual(token,result['packet_token'])
        output.write_bytes(b''); original_path=list(sys.path)
        try:
            with patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),'PACKET_TOKEN':token,'GITHUB_OUTPUT':str(output)}): exec(script,{})
        finally: sys.path[:]=original_path
        self.assertIn('complete=true\n',output.read_text())
        self.assertNotIn('/elf-closure.json\n',output.read_text())
        (self.dest/'completion.json').unlink(); output.write_bytes(b'')
        try:
            with patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),'PACKET_TOKEN':token,'GITHUB_OUTPUT':str(output)}),self.assertRaises(OSError): exec(script,{})
        finally: sys.path[:]=original_path
        self.assertEqual(output.read_bytes(),b'')
