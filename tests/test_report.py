"""Render a complete public example in a different working directory, then validate it."""
import contextlib
import hashlib
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_report as render
import verify_report as verify
import install_pre_commit as hook


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.spec = json.loads((ROOT / "examples/demo_spec.json").read_text(encoding="utf-8"))
        self.spec.update(out=str(self.folder / "报告.html"), tracking_file=str(self.folder / "tracking.csv"))

    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return Path(render.render(self.spec))

    def validate(self, path, scan=None):
        argv = ["verify_report", str(path), "--scan", str(scan or ROOT/"examples/demo_scan.json"),
                "--tracking", self.spec["tracking_file"], "--today", "2026-06-02", "--strict"]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return verify.main()

    def test_clean_render_is_self_contained_and_does_not_modify_public_registry(self):
        registry = ROOT / "tracking/forward_picks.csv"
        before = registry.read_bytes()
        old_cwd = Path.cwd()
        try:
            os.chdir(self.folder)
            result = self.generate()
        finally:
            os.chdir(old_cwd)
        html = result.read_text(encoding="utf-8")
        self.assertNotIn("localhost", html)
        self.assertNotIn("{{", html)
        self.assertIn("历史演示", html)
        self.assertIn('"report_date": "2026-06-02"', html)
        self.assertEqual(self.validate(result), 0, verify.F)
        self.assertEqual(registry.read_bytes(), before)
        self.generate()
        with Path(self.spec["tracking_file"]).open(encoding="utf-8") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 2)

    def test_tampered_price_is_rejected(self):
        result = self.generate()
        html = result.read_text(encoding="utf-8").replace('$277.49', '$1.00')
        result.write_text(html, encoding="utf-8")
        self.assertEqual(self.validate(result), 1)

    def test_missing_explicit_scan_is_an_error_not_fallback(self):
        self.assertEqual(self.validate(self.generate(), self.folder / "missing.json"), 2)

    def test_missing_candidate_in_scan_is_rejected(self):
        result = self.generate()
        source = json.loads((ROOT / "examples/demo_scan.json").read_text(encoding="utf-8"))
        incomplete = self.folder / "incomplete.json"
        incomplete.write_text(json.dumps(source[:1]), encoding="utf-8")
        self.assertEqual(self.validate(result, incomplete), 1)

    def test_downtrend_label_does_not_become_early_up(self):
        record = json.loads((ROOT / "examples/demo_scan.json").read_text(encoding="utf-8"))[0]
        record.update(stage="downtrend/basing", range_pos_6mo_pct=20)
        html = render.ruler({record["ticker"]: record}, record["ticker"])
        self.assertIn('DOWNTREND/BASE', html)
        self.assertNotIn('EARLY-UP', html)

    def test_demo_quotes_match_the_previously_public_archive(self):
        provenance = json.loads((ROOT/'examples/provenance.json').read_text(encoding='utf-8'))
        payload = (ROOT/provenance['source_file']).read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(payload).hexdigest(), provenance['source_sha256_lf'])
        old = {r['ticker']: r for r in json.loads(payload)}
        sample = json.loads((ROOT/'examples/demo_scan.json').read_text(encoding='utf-8'))
        self.assertEqual(len(sample), 2)
        for row in sample:
            for field, value in old[row['ticker']].items():
                self.assertEqual(row[field], value)

    def test_hook_install_is_local_and_preserves_existing_hooks(self):
        repo = self.folder / 'fresh clone 中文'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo/'scripts').mkdir()
        (repo/'scripts/verify_tickers.py').write_text('print("ok")', encoding='utf-8')
        installed = hook.install(repo)
        self.assertIn('--staged', installed.read_text(encoding='utf-8'))
        self.assertEqual(hook.install(repo), installed)
        installed.write_text('#!/bin/sh\necho custom\n', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            hook.install(repo)
        self.assertIn('custom', installed.read_text(encoding='utf-8'))

    def test_hook_installer_preserves_custom_hooks_configuration(self):
        repo = self.folder / 'custom'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'config', 'core.hooksPath', str(self.folder/'shared-hooks')], check=True)
        with self.assertRaises(ValueError):
            hook.install(repo)
        self.assertFalse((self.folder/'shared-hooks').exists())


if __name__ == '__main__':
    unittest.main()
