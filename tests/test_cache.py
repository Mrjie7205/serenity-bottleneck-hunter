"""Cache policy changes must not reuse legacy raw-price data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tracking'))
import score_tracker


class CacheTests(unittest.TestCase):
    def test_legacy_stale_and_different_policy_caches_are_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache.json'
            prices = {'DEMO': [{'date':'2026-01-01', 'close':100}]}
            for content in (prices, {'policy':'old','generated_on':'2026-01-02','prices':prices},
                            {'policy':score_tracker.CACHE_POLICY,'generated_on':'2026-01-01','prices':prices}):
                path.write_text(json.dumps(content),encoding='utf-8')
                self.assertEqual(score_tracker.load_cache(path, '2026-01-02'), {})
            path.write_text(json.dumps({'policy':score_tracker.CACHE_POLICY,'generated_on':'2026-01-02','prices':prices}),encoding='utf-8')
            self.assertEqual(score_tracker.load_cache(path, '2026-01-02'), prices)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['prices'], prices)
