"""Real Linux adapter methods with every OS boundary replaced, never native execution."""
import importlib.util
from pathlib import Path
import sys
import unittest

path=Path(__file__).with_name('host_canary_native_fixture.py')
spec=importlib.util.spec_from_file_location('full_native_bridge',path)
api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)

class NativeIntegrationTests(unittest.TestCase):
    def test_complete_four_phases_through_concrete_linux_adapter_and_separate_removal(self):
        bridge=api.Bridge();self.addCleanup(bridge.close)
        c=bridge.controller()
        rows=[c.run_phase(p) for p in ('A','B','C','D')]
        self.assertEqual([r['checkpoint']['state'] for r in rows],['enrolled','installed','restored','closed'])
        self.assertEqual(bridge.launches,4);self.assertEqual(bridge.waits,4);self.assertEqual(bridge.signals,0)
        self.assertEqual(c.requests.cache_bytes,sum(len(v[0]) for s in c.scopes for v in s.server.contents.values()))
        for scope in c.scopes:
            self.assertIs(type(scope.transport),bridge.api.LinuxTransport)
            scope.verify_closed();scope.verify_closed()
        self.assertEqual(bridge.waits,4)
        grant=c.s.linux_module().LinuxRemovalGrant(c,rows[-1]['checkpoint']['graph_sha256'])
        c.teardown(removal=grant)
        self.assertTrue(bridge.f.s.closed)
        self.assertEqual(bridge.waits,4);self.assertEqual(bridge.signals,0)

if __name__=='__main__':unittest.main(verbosity=2)
