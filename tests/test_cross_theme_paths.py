"""Personal Cockpit indexes must use the selected data, not public historical records."""
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CrossThemePathTests(unittest.TestCase):
    def test_explicit_personal_paths_preserve_input_and_public_index(self):
        public = ROOT/'tracking/cross_theme_index_snapshot.csv'
        before = public.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'personal.csv'
            output = Path(folder)/'index.csv'
            source.write_text('record_date,theme,eodhd_symbol,name,tier,archetypes,entry_stage,skill_verdict\n'
                '2026-01-01,Theme A,DEMO.US,Demo,上游咽喉,④,early-uptrend,🟡\n'
                '2026-01-02,Theme B,DEMO.US,Demo,上游咽喉,④,early-uptrend,🟡\n',encoding='utf-8')
            original = source.read_bytes()
            env = {**os.environ,'PYTHONUTF8':'1'}
            result = subprocess.run([sys.executable,str(ROOT/'tracking/cross_theme_scan.py'),
                '--input',str(source),'--output',str(output)],cwd=folder,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with output.open(encoding='utf-8-sig') as handle:rows=list(csv.DictReader(handle))
            self.assertEqual([(r['symbol'],r['theme_count']) for r in rows],[('DEMO.US','2')])
            self.assertEqual(source.read_bytes(),original)
            collision=subprocess.run([sys.executable,str(ROOT/'tracking/cross_theme_scan.py'),
                '--input',str(source),'--output',str(source)],env=env,capture_output=True)
            self.assertNotEqual(collision.returncode,0)
            self.assertEqual(source.read_bytes(),original)
        self.assertEqual(public.read_bytes(),before)
