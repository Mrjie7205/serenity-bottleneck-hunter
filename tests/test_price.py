"""Offline provider and adjustment tests: all prices are synthetic fixtures."""
import datetime
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import price


def bar(day, value):
    return dict(date=day, open=value, high=value, low=value, close=value)


class PriceTests(unittest.TestCase):
    def test_explicit_split_factor_scales_all_ohlc(self):
        raw = [dict(bar("2026-01-01", 100), adjusted_close=50),
               dict(bar("2026-01-02", 50), adjusted_close=50)]
        self.assertEqual([x["close"] for x in price._adjust_eodhd(raw)], [50, 50])
        self.assertEqual(price._adjust_eodhd(raw)[0]["high"], 50)
        self.assertEqual(raw[0]["close"], 100)

    def test_real_jump_is_not_misclassified_as_split(self):
        raw = [dict(bar("2026-01-01", 100), adjusted_close=100),
               dict(bar("2026-01-02", 150), adjusted_close=150)]
        self.assertEqual([x["close"] for x in price._adjust_eodhd(raw)], [100, 150])

    def test_missing_or_invalid_adjustment_fails_closed(self):
        for adj in (None, 0, -1, float("nan"), float("inf")):
            self.assertIsNone(price._adjust_eodhd([dict(bar("2026-01-01", 100), adjusted_close=adj)]))
        self.assertIsNone(price._adjust_eodhd([bar("2026-01-01", 100)]))

    def test_invalid_bars_are_rejected_and_order_is_chronological(self):
        valid = [bar("2026-01-02", 20), bar("2026-01-01", 10)]
        dirty = valid + [bar("2026-01-03", float("nan")), bar("bad-date", 1), bar("2026-01-04", 0)]
        self.assertEqual(price._clean(dirty), valid[::-1])
        self.assertIsNone(price._clean([bar("2026-01-01", 10), bar("2026-01-01", 11)]))

    def test_us_suffix_is_mapped_only_for_yahoo(self):
        bars = [bar("2026-01-01", 10)]
        with patch.object(price, "EODHD_KEY", "test"), patch.object(price, "_fetch_eodhd", return_value=None) as eod, \
             patch.object(price, "_fetch_yf", return_value=bars) as yahoo:
            self.assertEqual(price.fetch_history("NVDA.US"), (bars, "yfinance-adj"))
        eod.assert_called_once_with("NVDA.US", 400)
        yahoo.assert_called_once_with("NVDA", 400)

    def test_hong_kong_suffix_is_preserved(self):
        with patch.object(price, "EODHD_KEY", ""), patch.object(price, "_fetch_yf", return_value=[bar("2026-01-01", 10)]) as yahoo:
            price.fetch_history("0700.HK")
            yahoo.assert_called_once_with("0700.HK", 400)

    def test_ashare_qfq_has_priority(self):
        bars = [bar("2026-01-01", 10)]
        with patch.object(price, "_fetch_akshare_qfq", return_value=bars), patch.object(price, "_fetch_yf") as yahoo:
            self.assertEqual(price.fetch_history("300579.SHE"), (bars, "akshare-qfq"))
            yahoo.assert_not_called()

    def test_ashare_yahoo_mapping_and_eod_fallback(self):
        bars = [bar("2026-01-01", 10)]
        with patch.object(price, "_fetch_akshare_qfq", return_value=None), patch.object(price, "_fetch_yf", return_value=bars) as yahoo:
            self.assertEqual(price.fetch_history("600000.SHG"), (bars, "yfinance-qfq"))
            yahoo.assert_called_once_with("600000.SS", 400)
        with patch.object(price, "_fetch_akshare_qfq", return_value=None), patch.object(price, "_fetch_yf", return_value=None), \
             patch.object(price, "EODHD_KEY", "test"), patch.object(price, "_fetch_eodhd", return_value=bars):
            result = price.analyze("600000.SHG")
            self.assertTrue(any("EODHD" in warning for warning in result["quality_warnings"]))

    def test_failures_return_no_fabricated_quote(self):
        with patch.object(price, "EODHD_KEY", ""), patch.object(price, "_fetch_yf", return_value=None):
            self.assertIn("error", price.analyze("DEMO.US"))

    def test_stage_formula_and_real_return_are_preserved(self):
        history = [bar((datetime.date(2025, 1, 1)+datetime.timedelta(days=i)).isoformat(), 100.) for i in range(126)]
        history[-1] = bar(history[-1]["date"], 150.)
        with patch.object(price, "fetch_history", return_value=(history, "fixture")):
            result = price.analyze("DEMO.US")
        self.assertEqual(result["ret_1m_pct"], 50.)
        self.assertTrue(result["stage"].startswith("extended"))
        self.assertEqual((result["high_6mo"], result["low_6mo"]), (150., 100.))

    def test_yahoo_requests_adjusted_prices_without_inferred_repair(self):
        ticker = Mock()
        ticker.history.return_value = None
        fake = types.SimpleNamespace(Ticker=Mock(return_value=ticker))
        with patch.dict(sys.modules, {"yfinance": fake}):
            price._fetch_yf("DEMO.US")
        fake.Ticker.assert_called_once_with("DEMO")
        self.assertTrue(ticker.history.call_args.kwargs["auto_adjust"])
        self.assertFalse(ticker.history.call_args.kwargs["repair"])

    def test_valuation_excludes_nonfinite_values(self):
        out = price._yf_valuation("DEMO.US", {"forwardPE": float("inf"), "trailingPE": 20})
        self.assertIsNone(out["forward_pe"])
        self.assertEqual(out["trailing_pe"], 20)

    def test_forecast_uses_next_year_and_does_not_substitute_another_year(self):
        class FixedDate(datetime.date):
            @classmethod
            def today(cls):
                return cls(2030, 9, 29)
        fc, codes, row = MagicMock(), MagicMock(), MagicMock()
        fc.columns = ['2030预测每股收益', '2031预测每股收益']
        codes.__eq__.return_value = 'selected'
        fc.__getitem__.side_effect = lambda key: codes if key == '代码' else row
        row.empty = False
        row.__getitem__.side_effect = lambda key: types.SimpleNamespace(iloc=[2.0 if '2031' in key else 1.0])
        fake_ak = types.SimpleNamespace(stock_zh_valuation_baidu=Mock(side_effect=ValueError), stock_financial_abstract=Mock(side_effect=ValueError))
        with patch.dict(sys.modules, {'akshare': fake_ak}), patch.object(price.datetime, 'date', FixedDate), \
             patch.object(price, '_ak_forecast', return_value=fc):
            self.assertEqual(price._ak_valuation('600000', last=12)['forward_pe'], 6)
            fc.columns = ['2030预测每股收益']
            self.assertIsNone(price._ak_valuation('600000', last=12)['forward_pe'])


if __name__ == "__main__":
    unittest.main()
