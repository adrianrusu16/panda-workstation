"""Profiler accounting only; no Host Canary adapter or transaction executes."""
import cProfile
import importlib.util
from pathlib import Path
import unittest


class ProfileAccountingTests(unittest.TestCase):
    def test_same_source_loaded_twice_preserves_all_calls_in_profile_rows(self):
        spec=importlib.util.spec_from_file_location('performance_accounting',
            Path(__file__).with_name('host_canary_performance.py'))
        api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
        first,second={},{}
        source='def repeated():\n    return 1\n'
        exec(compile(source,'<two-engine-modules>','exec'),first)
        exec(compile(source,'<two-engine-modules>','exec'),second)
        profiler=cProfile.Profile()
        profiler.enable()
        first['repeated']()
        second['repeated']();second['repeated']()
        profiler.disable()
        rows=[row for row in api.profile_rows(profiler)
              if row['file']=='<two-engine-modules>' and row['name']=='repeated']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['calls'],3)
        self.assertEqual(rows[0]['primitive'],3)


if __name__=='__main__':unittest.main()
