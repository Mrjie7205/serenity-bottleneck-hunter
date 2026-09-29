"""告警持久化与并发回归；临时目录、模拟行情，不触发真实抓价。"""
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import triggers
import settings


OLD_TIME = "2026-06-11 16:30:00"
LABEL = "1m 转正(启动信号)"


def pick(symbol):
    return {
        "symbol": symbol, "name": symbol, "theme": "test", "market_label": "US",
        "verdict": "等启动", "entry_stage": "range", "thesis": "test",
        "entry_price": 10, "currency": "USD", "record_date": "2026-06-01",
        "star_count": 2, "stars": "★★", "verdict_class": "amber",
    }


def old_hit(symbol, checked_at=OLD_TIME):
    return {"symbol": symbol, "trigger_label": LABEL, "fired_value": 3,
            "star_count": 2, "checked_at": checked_at}


class TriggersTests(unittest.TestCase):
    def setUp(self):
        demo_patch = patch.object(settings, "DEMO", False)
        demo_patch.start()
        self.addCleanup(demo_patch.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.alerts = base / "alerts.json"
        self.acks = base / "alerts_ack.json"
        for name, value in (("ALERTS_FILE", self.alerts), ("ACK_FILE", self.acks)):
            mock = patch.object(triggers, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        analyze_patch = patch.object(triggers, "analyze", return_value={"ret_1m_pct": 2})
        self.analyze = analyze_patch.start()
        self.addCleanup(analyze_patch.stop)

    def save_alerts(self, symbols):
        self.alerts.write_text(json.dumps({
            "last_run": OLD_TIME, "hit_count": len(symbols),
            "hits": [old_hit(symbol) for symbol in symbols], "manual_watch": [],
        }), encoding="utf-8")

    def check(self, symbols, limit=0):
        with patch.object(triggers, "_watchlist", return_value=[pick(s) for s in symbols]):
            return triggers.run_check(limit)

    def test_quick_30_retains_unchecked_tail_and_original_time(self):
        symbols = [f"S{i:02d}" for i in range(35)]
        self.save_alerts(symbols)
        self.analyze.return_value = {"ret_1m_pct": -1}
        result = self.check(symbols, limit=30)
        self.assertTrue(result["ok"])
        self.assertEqual(result["scope"], "partial")
        self.assertEqual(result["checked_auto"], 30)
        self.assertEqual(result["successful_auto"], 30)
        self.assertEqual([h["symbol"] for h in result["hits"]], symbols[30:])
        self.assertTrue(all(h["checked_at"] == OLD_TIME for h in result["hits"]))
        self.assertEqual(self.analyze.call_count, 30)

    def test_partial_check_retains_items_outside_current_watchlist(self):
        self.save_alerts(["A", "OLD"])
        self.analyze.return_value = {"ret_1m_pct": -1}
        result = self.check(["A"], limit=30)
        self.assertEqual([h["symbol"] for h in result["hits"]], ["OLD"])

    def test_full_check_removes_retired_items_but_preserves_failed(self):
        self.save_alerts(["A", "B", "OLD"])
        self.analyze.side_effect = [{"ret_1m_pct": -1}, {"error": "offline"}]
        result = self.check(["A", "B"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["scope"], "full")
        self.assertEqual(result["successful_auto"], 1)
        self.assertEqual(result["failed_symbols"], ["B"])
        self.assertEqual(result["hits"], [old_hit("B")])
        self.assertEqual(json.loads(self.alerts.read_text(encoding="utf-8"))["hits"], [old_hit("B")])

    def test_repeated_failures_never_erase_old_hits_or_refresh_their_times(self):
        self.save_alerts(["A", "B"])
        self.analyze.side_effect = RuntimeError("unavailable")
        for _ in range(3):
            result = self.check(["A", "B"])
            self.assertFalse(result["ok"])
            self.assertEqual(result["successful_auto"], 0)
            self.assertEqual(result["hits"], [old_hit("A"), old_hit("B")])

    def test_missing_nonfinite_or_wrong_type_fields_are_failed_checks(self):
        self.save_alerts(["A"])
        for snap in ({}, None, {"ret_1m_pct": None}, {"ret_1m_pct": "2"},
                     {"ret_1m_pct": float("nan")}, {"ret_1m_pct": float("inf")},
                     {"ret_1m_pct": True}):
            with self.subTest(snapshot=snap):
                self.analyze.return_value = snap
                result = self.check(["A"])
                self.assertFalse(result["ok"])
                self.assertEqual(result["hits"], [old_hit("A")])

    def test_new_hits_have_check_time_and_keep_original_threshold(self):
        result = self.check(["A"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["hits"][0]["trigger_label"], LABEL)
        self.assertEqual(result["hits"][0]["fired_value"], 2)
        self.assertTrue(result["hits"][0]["checked_at"])
        self.analyze.return_value = {"ret_1m_pct": 0}
        self.assertEqual(self.check(["A"])["hits"], [])

    def test_old_schema_uses_old_run_time_for_retained_item(self):
        self.save_alerts(["A", "B"])
        old = json.loads(self.alerts.read_text(encoding="utf-8"))
        for hit in old["hits"]:
            hit.pop("checked_at")
        self.alerts.write_text(json.dumps(old), encoding="utf-8")
        result = self.check(["A", "B"], limit=1)
        self.assertEqual(next(h for h in result["hits"] if h["symbol"] == "B")["checked_at"], OLD_TIME)

    def test_manual_items_are_not_analyzed_and_stay_in_manual_watch(self):
        record = pick("A")
        record["verdict"] = "等待财报"
        with patch.object(triggers, "_watchlist", return_value=[record]):
            result = triggers.run_check()
        self.analyze.assert_not_called()
        self.assertEqual(result["checked_manual"], 1)
        self.assertEqual(result["manual_watch"][0]["symbol"], "A")

    def test_ack_survives_refresh_and_clear_only_removes_requested_key(self):
        self.assertTrue(triggers.ack("A", LABEL, "done")["ok"])
        self.assertTrue(triggers.ack("B", LABEL, "ignore")["ok"])
        self.check(["A", "B"])
        self.assertEqual([h["ack"] for h in triggers.load_alerts()["hits"]], ["done", "ignore"])
        self.assertTrue(triggers.ack("A", LABEL, "clear")["ok"])
        self.assertEqual([h["ack"] for h in triggers.load_alerts()["hits"]], [None, "ignore"])

    def test_corrupt_alerts_are_visible_and_block_overwrite_before_fetch(self):
        for content in ("{bad", "[]", '{"hits":[null]}', '{"hits":null}',
                        '{"hits":[{"symbol":"A","trigger_label":"test","star_count":"bad"}]}'):
            with self.subTest(content=content):
                self.alerts.write_text(content, encoding="utf-8")
                self.assertFalse(triggers.load_alerts()["ok"])
                result = self.check(["A"])
                self.assertFalse(result["ok"])
                self.assertTrue(result["storage_errors"])
                self.assertEqual(self.alerts.read_text(encoding="utf-8"), content)
        self.analyze.assert_not_called()

    def test_corrupt_ack_is_not_overwritten_and_existing_hits_remain_readable(self):
        self.save_alerts(["A"])
        for content in ("{bad", "[]", '{"A|trigger":null}'):
            with self.subTest(content=content):
                self.acks.write_text(content, encoding="utf-8")
                result = triggers.ack("A", LABEL, "done")
                self.assertFalse(result["ok"])
                self.assertEqual(self.acks.read_text(encoding="utf-8"), content)
                status = triggers.load_alerts()
                self.assertFalse(status["ok"])
                self.assertEqual(status["hits"], [old_hit("A")])

    def test_read_failure_returns_error_without_fetch_or_write(self):
        self.save_alerts(["A"])
        old = self.alerts.read_bytes()
        with patch.object(Path, "read_text", side_effect=PermissionError("locked")):
            self.assertFalse(triggers.load_alerts()["ok"])
            self.assertFalse(self.check(["A"])["ok"])
            self.assertFalse(triggers.ack("A", LABEL, "done")["ok"])
        self.analyze.assert_not_called()
        self.assertEqual(self.alerts.read_bytes(), old)
        self.assertFalse(self.acks.exists())

    def test_alert_write_failure_preserves_old_file_and_returns_old_state(self):
        self.save_alerts(["A"])
        old = self.alerts.read_bytes()
        with patch.object(triggers.os, "replace", side_effect=PermissionError("locked")):
            result = self.check(["B"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["hits"], [old_hit("A")])
        self.assertEqual(self.alerts.read_bytes(), old)
        self.assertEqual(list(self.alerts.parent.glob("*.tmp")), [])

    def test_ack_write_failure_preserves_old_file(self):
        triggers.ack("A", LABEL, "done")
        old = self.acks.read_bytes()
        with patch.object(triggers.os, "replace", side_effect=PermissionError("locked")):
            result = triggers.ack("B", LABEL, "ignore")
        self.assertFalse(result["ok"])
        self.assertEqual(self.acks.read_bytes(), old)
        self.assertEqual(list(self.acks.parent.glob("*.tmp")), [])

    def test_ack_read_modify_write_is_serialized_without_lost_updates(self):
        gate = threading.Barrier(10)

        def mark(i):
            gate.wait(timeout=5)
            return triggers.ack(f"S{i}", LABEL, "done")

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(mark, range(10)))
        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(len(json.loads(self.acks.read_text(encoding="utf-8"))), 10)

    def test_ack_remains_available_while_check_fetches(self):
        entered, release = threading.Event(), threading.Event()

        def fetch(_symbol):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test timed out")
            return {"ret_1m_pct": 2}

        self.analyze.side_effect = fetch
        with ThreadPoolExecutor(max_workers=2) as pool:
            checking = pool.submit(self.check, ["A"])
            self.assertTrue(entered.wait(timeout=5))
            try:
                marked = pool.submit(triggers.ack, "A", LABEL, "done").result(timeout=3)
                self.assertTrue(marked["ok"])
            finally:
                release.set()
            self.assertTrue(checking.result(timeout=5)["ok"])
        self.assertEqual(triggers.load_alerts()["hits"][0]["ack"], "done")

    def test_concurrent_checks_serialize_and_read_latest_persisted_results(self):
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        calls = []
        calls_lock = threading.Lock()

        def fetch(symbol):
            with calls_lock:
                calls.append(symbol)
                call = len(calls)
            if call == 1:
                entered.set()
                if not release.wait(timeout=5):
                    raise RuntimeError("test timed out")
            return {"ret_1m_pct": 2 if symbol == "B" else -1}

        def partial():
            second_started.set()
            return triggers.run_check(limit=1)

        self.analyze.side_effect = fetch
        with patch.object(triggers, "_watchlist", return_value=[pick("A"), pick("B")]):
            with ThreadPoolExecutor(max_workers=2) as pool:
                full = pool.submit(triggers.run_check)
                self.assertTrue(entered.wait(timeout=5))
                partial_result = pool.submit(partial)
                self.assertTrue(second_started.wait(timeout=5))
                self.assertEqual(calls, ["A"])
                release.set()
                self.assertTrue(full.result(timeout=5)["ok"])
                self.assertTrue(partial_result.result(timeout=5)["ok"])
        self.assertEqual(calls, ["A", "B", "A"])
        self.assertEqual([h["symbol"] for h in triggers.load_alerts()["hits"]], ["B"])

    def test_each_atomic_write_uses_a_unique_temporary_path(self):
        replace = triggers.os.replace
        paths = []

        def record(source, target):
            paths.append(source)
            return replace(source, target)

        with patch.object(triggers.os, "replace", side_effect=record):
            triggers.ack("A", LABEL, "done")
            triggers.ack("B", LABEL, "ignore")
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(path.parent == self.acks.parent for path in paths))


if __name__ == "__main__":
    unittest.main()
