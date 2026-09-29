"""Public demo isolation and personal workspace API acceptance without live quotes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cockpit/backend'))
from fastapi.testclient import TestClient
import data
import main
import settings
import snapshot
import triggers

spec = importlib.util.spec_from_file_location('cockpit_runner', ROOT/'cockpit/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
HEADERS = {'X-Serenity-Request': 'cockpit'}


class CockpitTests(unittest.TestCase):
    def client(self):
        return TestClient(main.app, base_url='http://127.0.0.1', headers=HEADERS)

    def test_default_demo_has_two_historical_rows_and_never_fetches(self):
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in settings.DEMO_DIR.rglob('*') if p.is_file()}
        with patch.object(settings, 'DEMO', True), \
             patch.object(main, 'fetch_history', side_effect=AssertionError('unexpected quote fetch')), \
             patch.object(snapshot, 'fetch_history', side_effect=AssertionError('unexpected snapshot')), \
             patch.object(triggers, 'analyze', side_effect=AssertionError('unexpected trigger')), self.client() as client:
            health = client.get('/api/health').json()
            self.assertTrue(health['demo'])
            self.assertFalse(health['scheduler'])
            picks = client.get('/api/picks').json()
            self.assertEqual(picks['count'], 2)
            self.assertTrue(all(p['record_date']=='2026-06-02' for p in picks['rows']))
            self.assertTrue(all(p['alpha_pct'] is None for p in picks['rows']))
            self.assertEqual(client.get('/api/reports').json()['count'], 1)
            self.assertEqual(client.get('/api/picks?q=DDOG').json()['count'], 1)
            chart = client.get('/api/kline/DDOG.US').json()
            self.assertEqual(chart['candles'], [])
            self.assertEqual(len(chart['annotations']), 1)
            self.assertIn('未包含', chart['message'])
            self.assertFalse(client.get('/api/scorecard').json()['available'])
            self.assertEqual(sum(c['count'] for c in client.get('/api/stages').json()['columns']), 2)
            self.assertEqual(client.get('/api/matrix').json()['rows'], [])
            for url in ['/api/snapshot/run', '/api/triggers/run', '/api/triggers/ack?symbol=DDOG.US&trigger_label=test&action=done']:
                self.assertEqual(client.post(url).status_code, 403, url)
        after = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in settings.DEMO_DIR.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_local_write_endpoints_reject_cross_site_or_unmarked_requests(self):
        with self.client() as client:
            self.assertEqual(client.post('/api/snapshot/run', headers={'Origin':'https://untrusted.example'}).status_code,403)
            self.assertEqual(client.post('/api/snapshot/run', headers={'X-Serenity-Request':''}).status_code,403)
            self.assertEqual(client.get('/api/health', headers={'Host':'untrusted.example'}).status_code,400)

    def test_report_paths_and_report_sandbox(self):
        with self.client() as client:
            report = client.get('/api/report-file/demo-report.html')
            self.assertEqual(report.status_code,200)
            self.assertIn('sandbox',report.headers['content-security-policy'])
            self.assertIn('历史演示',report.text)
            self.assertEqual(client.get('/api/report-file/.env').status_code,404)
            self.assertEqual(client.get('/api/not-an-endpoint').status_code,404)
            self.assertEqual(client.get('/.env').status_code,404)
            self.assertEqual(client.get('/api/kline/UNKNOWN.US').status_code,404)

    def test_workspace_init_is_empty_and_will_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'personal 中文'
            runner.init_workspace(target)
            self.assertEqual((target/'tracking/forward_picks.csv').read_bytes(),(ROOT/'examples/blank_tracking.csv').read_bytes())
            original=(target/'tracking/forward_picks.csv').read_bytes()
            with self.assertRaises(FileExistsError): runner.init_workspace(target)
            self.assertEqual((target/'tracking/forward_picks.csv').read_bytes(),original)

    def test_spa_routes_serve_built_ui_without_exposing_parent_files(self):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder);dist=parent/'dist';dist.mkdir();(dist/'assets').mkdir()
            (dist/'index.html').write_text('<html>cockpit-built-ui</html>',encoding='utf-8')
            (dist/'assets/app.js').write_text('console.log("local");',encoding='utf-8')
            (parent/'.env').write_text('test-only-private-marker',encoding='utf-8')
            with patch.object(settings,'WEB_DIST',dist), self.client() as client:
                self.assertIn('cockpit-built-ui',client.get('/').text)
                self.assertIn('cockpit-built-ui',client.get('/tracker').text)
                self.assertEqual(client.get('/assets/app.js').status_code,200)
                self.assertEqual(client.get('/%2e%2e/.env').status_code,404)
                self.assertEqual(client.get('/assets/missing.js').status_code,404)

    def test_personal_mode_uses_mock_quotes_and_keeps_dates_and_scope(self):
        history=[{'date':'2026-06-01','open':10,'high':12,'low':9,'close':11}]
        with tempfile.TemporaryDirectory() as folder, patch.object(settings,'DEMO',False), \
             patch.object(settings,'STATE_DIR',Path(folder)), patch.dict(os.environ,{'SERENITY_SCHEDULER':'0'}), \
             patch.object(main,'fetch_history',return_value=(history,'offline-fixture')) as fetch, self.client() as client:
            response=client.get('/api/kline/DDOG.US?days=90')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['candles'][0]['close'],11)
            fetch.assert_called_once_with('DDOG.US',days=90)
            self.assertEqual(client.get('/api/kline/DDOG.US?days=999999').status_code,422)


if __name__=='__main__': unittest.main()
