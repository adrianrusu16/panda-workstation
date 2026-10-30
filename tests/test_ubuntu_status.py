"""GnuPG 2.4.4 DETAILS framing, through the real callback with a process double."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_ubuntu_verification import FPR, NOW, protocol_fixture, runner_context, status
from test_ubuntu_artifacts import synthetic_elf

S4 = Path(__file__).resolve().parent/'native/external_vm/s4'


class UbuntuPlaintextStatus(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(S4)); self.addCleanup(sys.path.remove,str(S4))
        self.protocol=importlib.import_module('ubuntu_verification')
        self.runner=importlib.import_module('ubuntu_bootstrap_runner')

    def test_actual_callback_supports_positive_altered_content_and_empty_keyring(self):
        payload=b'synthetic signed content\n'
        prelude=b'[GNUPG:] PLAINTEXT 74 0 \n'
        bad=('[GNUPG:] NEWSIG\n[GNUPG:] BADSIG '+FPR[-16:]+' name\n').encode()
        missing=('[GNUPG:] NEWSIG\n[GNUPG:] ERRSIG '+FPR[-16:]+' 1 10 01 1793290000 9 '+FPR+
                 '\n[GNUPG:] NO_PUBKEY '+FPR[-16:]+'\n').encode()
        def invoke(tool, args, directory, stdin, limit):
            self.assertEqual(tool,'gpgv')
            self.assertEqual(args,['--homedir',str(directory),'--keyring','./keyring.gpg','--status-fd','1','--output','plain','input'])
            self.assertEqual(limit,2*1024**2)
            ring=(directory/'keyring.gpg').read_bytes(); raw=(directory/'input').read_bytes()
            (directory/'plain').write_bytes(payload)
            return (2,prelude+missing,b'') if not ring else (1,prelude+bad,b'') if raw==b'altered' else (0,prelude+status(),b'')
        toolchain={'tools':{'gpgv':'/usr/bin/gpgv'},'files':{'/usr/bin/gpgv':{'sha256':self.protocol.sha256(b'fixture-gpgv')}}}
        with tempfile.TemporaryDirectory() as name, patch.object(self.runner,'system_file',return_value={'raw':b'fixture-gpgv'}), \
             patch.object(self.runner,'invoke',side_effect=invoke):
            verifier=self.runner.gpgv_verifier(Path(name),toolchain)
            code, records, plain=verifier(b'positive',b'ring')
            self.protocol.signature_status(code,records,FPR,NOW,plaintext=plain)
            for case,raw,ring in (('altered-content',b'altered',b'ring'),('empty-keyring',b'positive',b'')):
                code,records,plain=verifier(raw,ring)
                self.protocol.negative_status(code,records,case,FPR,plaintext=plain)
            self.assertEqual(list(Path(name).iterdir()),[])

    def test_documented_formats_timestamps_escaping_and_partial_length_omission(self):
        for code in ('62','74','75'):
            for stamp in ('0','4294967295'):
                for filename in ('','a%20b%25%0A','café','wide\u2003space','%00','a'*255,'%20'*255):
                    with self.subTest(code=code,stamp=stamp,filename=filename):
                        raw=('[GNUPG:] PLAINTEXT '+code+' '+stamp+' '+filename+'\n').encode()+status()
                        self.protocol.signature_status(0,raw,FPR,NOW,plaintext=b'data')
        # Text postprocessing can change byte count; DETAILS guarantees equality only for binary.
        self.protocol.signature_status(0,b'[GNUPG:] PLAINTEXT 74 0 \n[GNUPG:] PLAINTEXT_LENGTH 5\n'+status(),FPR,NOW,plaintext=b'a\nb\n')
        self.protocol.signature_status(0,b'[GNUPG:] PLAINTEXT 62 0 \n[GNUPG:] PLAINTEXT_LENGTH 4\n'+status(),FPR,NOW,plaintext=b'data')

    def test_full_synthetic_protocol_uses_the_actual_adapter_for_all_nine_checks(self):
        pins,bootstrap,blobs,ring,fixture_verifier,toolchain=protocol_fixture()
        ref=pins['files']['/usr/bin/gpgv']; gpgv=synthetic_elf(ref['needed'],ref['interpreter'])
        self.assertEqual(self.protocol.sha256(gpgv),ref['sha256'])
        calls=[]
        def invoke(tool,args,directory,stdin,limit):
            raw=(directory/'input').read_bytes(); keyring=(directory/'keyring.gpg').read_bytes()
            code,records,plain=fixture_verifier(raw,keyring); calls.append(code)
            (directory/'plain').write_bytes(plain)
            prefix=('[GNUPG:] PLAINTEXT 74 0 \n[GNUPG:] PLAINTEXT_LENGTH '+str(len(plain))+'\n').encode()
            return code,prefix+records,b''
        with tempfile.TemporaryDirectory() as name, patch.object(self.runner,'system_file',return_value={'raw':gpgv}), \
             patch.object(self.runner,'invoke',side_effect=invoke), \
             patch.object(self.protocol,'load_references',return_value=(pins,bootstrap)), \
             patch.object(self.protocol.consistency,'load_pins',return_value=bootstrap):
            verifier=self.runner.gpgv_verifier(Path(name),toolchain)
            bundle=self.protocol.verify_ubuntu(runner_context(),b'ID=ubuntu\nVERSION_ID=24.04\n',NOW,ring,toolchain,
                lambda identity,url,size:blobs[identity],verifier,None)
            self.assertEqual(calls.count(0),3); self.assertEqual(calls.count(1),3); self.assertEqual(calls.count(2),3)
            self.assertFalse(bundle['receipts']['authorization-state']['data']['execution_authorized'])
            self.assertEqual(list(Path(name).iterdir()),[])

    def test_malformed_duplicate_ambiguous_or_contradictory_information_is_rejected(self):
        good=b'[GNUPG:] PLAINTEXT 74 0 \n'
        cases=[b'PLAINTEXT 61 0 ',b'PLAINTEXT 074 0 ',b'PLAINTEXT 74 -1 ',b'PLAINTEXT 74 4294967296 ',
               b'PLAINTEXT 74 00 ',b'PLAINTEXT 74 0',b'PLAINTEXT 74 0 a b',b'PLAINTEXT 74 0 %',
               b'PLAINTEXT 74 0 %0G',b'PLAINTEXT 74 0 '+b'a'*256,
               b'PLAINTEXT_LENGTH -1',b'PLAINTEXT_LENGTH +1',b'PLAINTEXT_LENGTH 01',b'PLAINTEXT_LENGTH 2097153']
        for case in cases:
            raw=(good if case.startswith(b'PLAINTEXT_LENGTH') else b'')+b'[GNUPG:] '+case+b'\n'+status()
            with self.subTest(case=case),self.assertRaises(ValueError): self.protocol.signature_status(0,raw,FPR,NOW,plaintext=b'data')
            negative=('[GNUPG:] NEWSIG\n[GNUPG:] BADSIG '+FPR[-16:]+' name\n').encode()
            raw=raw.removesuffix(status())+negative
            with self.subTest(case=case,negative=True),self.assertRaises(ValueError): self.protocol.negative_status(1,raw,'altered-content',FPR,plaintext=b'data')
        for raw in (good+good,good+b'[GNUPG:] PLAINTEXT_LENGTH 4\n[GNUPG:] PLAINTEXT_LENGTH 4\n',
                    b'[GNUPG:] PLAINTEXT_LENGTH 4\n',
                    b'[GNUPG:] PLAINTEXT_LENGTH 4\n'+good,
                    b'[GNUPG:] PLAINTEXT 62 0 \n[GNUPG:] PLAINTEXT_LENGTH 5\n'):
            with self.subTest(raw=raw),self.assertRaises(ValueError): self.protocol.signature_status(0,raw+status(),FPR,NOW,plaintext=b'data')

    def test_plaintext_information_cannot_replace_signature_evidence_or_resource_limits(self):
        records=b'[GNUPG:] PLAINTEXT 74 0 \n'
        with self.assertRaises(ValueError): self.protocol.signature_status(0,records,FPR,NOW,plaintext=b'data')
        with self.assertRaises(ValueError): self.protocol.negative_status(1,records,'altered-content',FPR,plaintext=b'data')
        with self.assertRaises(ValueError): self.protocol.signature_status(0,records*65+status(),FPR,NOW)
        with self.assertRaises(ValueError): self.protocol.signature_status(0,records+status(),FPR,NOW,plaintext=b'x'*(2*1024**2+1))
