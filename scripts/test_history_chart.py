"""Historical ERP chart regression tests: genuine week-end points and percentiles."""
import unittest

import pandas as pd

from history_chart import build_history, official_csi500_erp


class TestHistoryChart(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2016-10-28", "2026-10-28")
        self.frame = pd.DataFrame({
            "date": dates,
            "erp": [1.25 + (i % 300) / 100 for i in range(len(dates))],
        })

    def test_weekly_true_observations(self):
        result = build_history(self.frame)
        stock = result["series"]["csi500"]
        self.assertEqual(result["frequency"], "weekly")
        self.assertTrue(480 <= len(stock["points"]) <= 530)
        self.assertEqual(stock["points"][-1][0], "2026-10-28")
        self.assertEqual(stock["sampleCount"], len(self.frame))
        for date, value in stock["points"]:
            matching = self.frame[self.frame.date == pd.Timestamp(date)].erp
            self.assertEqual(value, round(float(matching.iloc[0]), 4))
        self.assertTrue(stock["p10"] <= stock["p20"] <= stock["p50"] <=
                        stock["p80"] <= stock["p90"])
        self.assertTrue(0 <= stock["percentile"] <= 100)

    def test_monthly_fallback_is_labelled(self):
        monthly = self.frame.drop_duplicates(
            self.frame.date.dt.to_period("M").rename("period"), keep="last"
        )
        result = build_history(monthly, frequency="monthly")
        self.assertEqual(result["frequency"], "monthly")
        self.assertTrue(110 <= len(result["series"]["csi500"]["points"]) <= 125)

    def test_official_source_matches_yield_without_future_pe(self):
        dates = pd.bdate_range("2016-10-20", "2026-10-28")
        yields = pd.DataFrame({"date": dates, "y10": 2.0})

        def mock_api(symbol, start_date, end_date):
            self.assertEqual(symbol, "000905")
            idx = dates[(dates >= pd.Timestamp(start_date)) &
                        (dates <= pd.Timestamp(end_date))]
            return pd.DataFrame({
                "日期": idx, "指数代码": "000905", "滚动市盈率": 20.0
            })
        daily = official_csi500_erp(yields, pd.Timestamp("2026-10-28"), api=mock_api)
        self.assertGreater(len(daily), 2400)
        self.assertAlmostEqual(daily.erp.iloc[-1], 3.0)

    def test_reject_missing_official_pe(self):
        yields = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=4),
                               "y10": [2, 2, 2, 2]})

        def broken(**kwargs):
            return pd.DataFrame({"日期": ["2026-10-28"]})
        with self.assertRaises(ValueError):
            official_csi500_erp(yields, pd.Timestamp("2026-10-28"), api=broken)


if __name__ == "__main__":
    unittest.main()
