"""快照隔离回归：不访问网络、不写真实研究数据、不启动服务。"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main
import snapshot
import settings


def fixture_pick(record_key, row_id, date, symbol="AAA.US"):
    return {
        "record_key": record_key, "id": row_id, "record_date": date,
        "symbol": symbol, "market": "US", "market_label": "美股",
        "name": symbol, "theme": "示例", "verdict": "候选", "verdict_class": "green",
        "star_count": 2, "archetypes": "①", "layer": 1, "layer_name": "示例层",
    }


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        demo_patch = patch.object(settings, "DEMO", False)
        demo_patch.start()
        self.addCleanup(demo_patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "snapshot.json"
        self.picks = [fixture_pick("first", 0, "2026-01-01"),
                      fixture_pick("second", 1, "2026-01-02", "BBB.US")]
        self.hist = [{"date": f"2026-01-0{i}", "close": i * 10,
                      "open": i * 10, "low": i * 10 - 1, "high": i * 10 + 1}
                     for i in range(1, 4)]
        self.bench = [{**row, "close": 10, "open": 10, "low": 9, "high": 11}
                      for row in self.hist]
        self.enter_patch(patch.object(snapshot, "SNAPSHOT_FILE", self.path))
        self.enter_patch(patch.object(snapshot.data, "load_picks", side_effect=lambda: self.picks))
        # 用稳定标识构造版本；真正 CSV 标识算法由 data 模块的测试负责。
        self.enter_patch(patch.object(snapshot.data, "picks_version", side_effect=self.version,
                                     create=True))
        self.fetch = self.enter_patch(patch.object(snapshot, "fetch_history", side_effect=self.history))
        snapshot._set(running=False, phase="", error=None)

    def enter_patch(self, manager):
        value = manager.start()
        self.addCleanup(manager.stop)
        return value

    def version(self, picks=None):
        rows = self.picks if picks is None else picks
        return hashlib.sha256(json.dumps(sorted(p["record_key"] for p in rows)).encode()).hexdigest()

    def history(self, symbol, days):
        return (self.bench if symbol in snapshot.BENCHMARKS.values() else self.hist), "test"

    def save_baseline(self):
        snapshot.run_snapshot()
        return self.path.read_bytes()

    def test_v2_keys_survive_reordering_and_changed_row_ids(self):
        result = snapshot.run_snapshot()
        self.assertTrue(result["complete"])
        self.assertTrue(result["published"])
        snap = snapshot.load_snapshot()
        self.assertEqual(snap["schema_version"], 2)
        self.assertEqual(set(snap["picks"]), {"first", "second"})
        self.picks = [{**self.picks[1], "id": 0}, {**self.picks[0], "id": 1}]
        rows = main._merge_snapshot(self.picks)
        self.assertEqual([r["since_call_pct"] for r in rows], [50.0, 200.0])
        self.assertEqual(snapshot.scorecard()["sample_n"], 2)
        self.assertEqual(snapshot.scorecard()["by_verdict"][0]["avg_alpha"], 125.0)

    def test_changed_record_invalidates_without_row_number_fallback(self):
        self.save_baseline()
        self.picks[0] = {**self.picks[0], "record_key": "edited"}
        self.assertIsNone(snapshot.load_snapshot())
        self.assertTrue(snapshot.status()["refresh_required"])
        self.assertIn("跟踪记录已变化", snapshot.status()["message"])
        self.assertIsNone(main._merge_snapshot(self.picks)[0]["since_call_pct"])
        self.assertFalse(snapshot.scorecard()["available"])

    def test_legacy_snapshot_invalidates_and_requests_refresh(self):
        self.path.write_text(json.dumps({"picks": {"0": {"since_call_pct": 999}}}), encoding="utf-8")
        self.assertIsNone(snapshot.load_snapshot())
        self.assertFalse(snapshot.status()["exists"])
        self.assertIn("旧快照", snapshot.status()["message"])
        self.assertIsNone(main._merge_snapshot(self.picks)[0]["since_call_pct"])

    def test_corrupt_snapshot_requests_refresh(self):
        self.path.write_text("{", encoding="utf-8")
        self.assertIsNone(snapshot.load_snapshot())
        self.assertTrue(snapshot.status()["refresh_required"])

    def test_missing_required_summary_fields_is_unavailable(self):
        self.save_baseline()
        valid = json.loads(self.path.read_text(encoding="utf-8"))
        for field in ("generated_at", "symbol_count", "error_count"):
            with self.subTest(field=field):
                broken = {k: v for k, v in valid.items() if k != field}
                self.path.write_text(json.dumps(broken), encoding="utf-8")
                self.assertIsNone(snapshot.load_snapshot())
                self.assertFalse(snapshot.status()["exists"])
                self.assertTrue(snapshot.status()["refresh_required"])
                self.assertFalse(snapshot.stage_board()["available"])

    def test_invalid_nested_metrics_or_calculations_safely_invalidate(self):
        self.save_baseline()
        valid = self.path.read_text(encoding="utf-8")
        mutations = (
            lambda obj: obj["symbols"].__setitem__("AAA.US", None),
            lambda obj: obj["symbols"]["AAA.US"].__setitem__("stage_key", "invalid"),
            lambda obj: obj["symbols"]["AAA.US"].__setitem__("last", float("nan")),
            lambda obj: obj["picks"].__setitem__("first", None),
            lambda obj: obj["picks"]["first"].__setitem__("alpha_pct", "invalid"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                broken = json.loads(valid)
                mutate(broken)
                self.path.write_text(json.dumps(broken), encoding="utf-8")
                self.assertIsNone(snapshot.load_snapshot())
                self.assertTrue(snapshot.status()["refresh_required"])
                self.assertIsNone(main._merge_snapshot(self.picks)[0]["last"])
                self.assertFalse(snapshot.stage_board()["available"])
                self.assertFalse(snapshot.scorecard()["available"])

    def test_partial_run_is_separate_and_preserves_formal_snapshot(self):
        before = self.save_baseline()
        result = snapshot.run_snapshot(limit=1)
        self.assertFalse(result["published"])
        self.assertEqual(self.path.read_bytes(), before)
        partial = json.loads((self.path.parent / "snapshot.partial.json").read_text(encoding="utf-8"))
        self.assertTrue(partial["partial"])
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["symbol_count"], 1)
        self.assertEqual(set(partial["picks"]), {"first"})

    def test_fetch_exception_retains_snapshot_releases_lock_and_allows_retry(self):
        before = self.save_baseline()
        self.fetch.side_effect = RuntimeError("模拟行情故障")
        with self.assertRaisesRegex(RuntimeError, "模拟行情故障"):
            snapshot.run_snapshot()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(snapshot.progress()["running"])
        self.assertIn("RuntimeError", snapshot.progress()["error"])
        self.fetch.side_effect = self.history
        self.assertTrue(snapshot.run_snapshot()["published"])
        self.assertIsNone(snapshot.progress()["error"])

    def test_zero_success_retains_formal_snapshot(self):
        before = self.save_baseline()
        self.fetch.side_effect = lambda symbol, days: (None, "none")
        with self.assertRaisesRegex(snapshot.SnapshotIncompleteError, "任何个股行情"):
            snapshot.run_snapshot()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(snapshot.progress()["running"])

    def test_partial_coverage_publishes_and_backs_up_last_complete_snapshot(self):
        before = self.save_baseline()
        self.fetch.side_effect = lambda symbol, days: ((None, "none") if symbol == "BBB.US"
                                                      else self.history(symbol, days))
        result = snapshot.run_snapshot()
        self.assertTrue(result["published"])
        self.assertFalse(result["complete"])
        self.assertIsNone(snapshot.progress()["error"])
        snap = snapshot.load_snapshot()
        self.assertEqual(snap["errors"], ["BBB.US"])
        backup = self.path.parent / "snapshot.last-complete.json"
        self.assertEqual(backup.read_bytes(), before)
        snapshot.run_snapshot()
        self.assertEqual(backup.read_bytes(), before)

    def test_missing_benchmark_is_visible_without_suppressing_prices(self):
        self.fetch.side_effect = lambda symbol, days: ((None, "none") if symbol == "QQQ.US"
                                                      else self.history(symbol, days))
        result = snapshot.run_snapshot()
        self.assertFalse(result["complete"])
        snap = snapshot.load_snapshot()
        self.assertEqual(snap["benchmark_errors"], ["US"])
        self.assertIsNone(snap["picks"]["first"]["alpha_pct"])
        self.assertEqual(main._merge_snapshot(self.picks)[0]["last"], 30)

    def test_input_change_during_build_does_not_publish(self):
        before = self.save_baseline()
        real_version = self.version()
        with patch.object(snapshot.data, "picks_version", side_effect=[real_version, "changed"]):
            with self.assertRaisesRegex(snapshot.SnapshotIncompleteError, "跟踪表已变化"):
                snapshot.run_snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_write_failure_retains_formal_snapshot_and_resets_running(self):
        before = self.save_baseline()
        with patch.object(Path, "replace", side_effect=OSError("模拟写入失败")):
            with self.assertRaisesRegex(OSError, "模拟写入失败"):
                snapshot.run_snapshot()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(snapshot.progress()["running"])
        self.assertIn("OSError", snapshot.progress()["error"])

    def test_formal_replace_failure_after_backup_preserves_snapshot_and_allows_retry(self):
        before = self.save_baseline()
        self.hist[-1].update(close=40, open=40, low=39, high=41)
        backup = self.path.parent / "snapshot.last-complete.json"
        replaced_targets = []
        original_replace = Path.replace

        def fail_formal_replace(source, target):
            replaced_targets.append(target)
            if target == self.path:
                raise OSError("模拟正式快照替换失败")
            return original_replace(source, target)

        with patch.object(Path, "replace", new=fail_formal_replace):
            with self.assertRaisesRegex(OSError, "模拟正式快照替换失败"):
                snapshot.run_snapshot()
        self.assertEqual(replaced_targets, [backup, self.path])
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(snapshot.load_snapshot()["symbols"]["AAA.US"]["last"], 30)
        self.assertFalse(snapshot.progress()["running"])
        self.assertIn("OSError", snapshot.progress()["error"])
        self.assertTrue(snapshot.run_snapshot()["published"])
        self.assertEqual(snapshot.load_snapshot()["symbols"]["AAA.US"]["last"], 40)
        self.assertIsNone(snapshot.progress()["error"])

    def test_public_error_does_not_include_filesystem_path_or_provider_secret(self):
        secret = "C:/Users/private/.env?api_token=private-token"
        self.fetch.side_effect = OSError(secret)
        with self.assertRaises(OSError):
            snapshot.run_snapshot()
        error = snapshot.status()["progress"]["error"]
        self.assertIn("OSError", error)
        self.assertNotIn("private", error)
        self.assertNotIn("api_token", error)

    def test_manual_start_reserves_lock_before_worker_starts(self):
        pending = []

        class DeferredWorker:
            def __init__(self, target, daemon):
                self.target = target
                pending.append(self)

            def start(self):
                pass

        with patch.object(snapshot.threading, "Thread", DeferredWorker):
            self.assertEqual(main.snapshot_run(limit=0), {"started": True, "limit": 0})
            try:
                self.assertTrue(snapshot.progress()["running"])
                self.assertEqual(main.snapshot_run(limit=0).status_code, 409)
                with self.assertRaises(snapshot.SnapshotBusyError):
                    snapshot.run_snapshot()
                self.assertEqual(len(pending), 1)
            finally:
                pending[0].target()
        self.assertFalse(snapshot.progress()["running"])

    def test_scheduled_run_blocks_manual_and_another_scheduled_run(self):
        entered, release = threading.Event(), threading.Event()
        failures = []

        def paused_history(symbol, days):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("测试等待超时")
            return self.history(symbol, days)

        def scheduled():
            try:
                snapshot.run_snapshot()
            except Exception as exc:
                failures.append(exc)

        self.fetch.side_effect = paused_history
        worker = threading.Thread(target=scheduled)
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaises(snapshot.SnapshotBusyError):
                snapshot.run_snapshot()
            self.assertEqual(main.snapshot_run(limit=0).status_code, 409)
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    def test_worker_start_failure_releases_lock(self):
        with patch.object(snapshot.threading.Thread, "start", side_effect=RuntimeError("线程启动失败")):
            with self.assertRaisesRegex(RuntimeError, "线程启动失败"):
                snapshot.start_snapshot()
        self.assertFalse(snapshot.progress()["running"])
        self.assertIn("RuntimeError", snapshot.progress()["error"])
        self.assertTrue(snapshot.run_snapshot()["published"])

    def test_scheduler_can_be_disabled_for_acceptance(self):
        with patch.dict(os.environ, {"SERENITY_SCHEDULER": "0"}), patch.object(main, "_scheduler", None):
            main._start_scheduler()
            self.assertIsNone(main._scheduler)
            self.assertFalse(main.health()["scheduler"])


if __name__ == "__main__":
    unittest.main()
