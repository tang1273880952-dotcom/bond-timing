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
        self.assertEqual(set(stock["periods"]), {"3", "5", "10"})
        for years in (3, 5, 10):
            period = stock["periods"][str(years)]
            cutoff = self.frame.date.iloc[-1] - pd.DateOffset(years=years)
            values = self.frame.loc[self.frame.date >= cutoff, "erp"]
            self.assertEqual(period["sampleCount"], len(values))
            self.assertEqual(period["p90"], round(float(values.quantile(.9)), 4))
            self.assertEqual(period["p10"], round(float(values.quantile(.1)), 4))
            self.assertEqual(period["percentile"],
                             round(float(values.le(values.iloc[-1]).mean() * 100), 2))
        self.assertEqual(stock["p90"], stock["periods"]["10"]["p90"])

    def test_reference_values_change_with_year_selection(self):
        dates = self.frame["date"]
        years_from_start = (dates - dates.iloc[0]).dt.days / 365.25
        trend = pd.DataFrame({"date": dates, "erp": years_from_start / 2})
        result = build_history(trend)
        periods = result["series"]["csi500"]["periods"]
        self.assertGreater(periods["3"]["p50"], periods["5"]["p50"])
        self.assertGreater(periods["5"]["p50"], periods["10"]["p50"])
        self.assertGreater(periods["3"]["p80"], periods["5"]["p80"])
        self.assertNotEqual(periods["3"]["sampleCount"], periods["10"]["sampleCount"])

    def test_monthly_fallback_is_labelled(self):
        monthly = self.frame.copy()
        monthly["period"] = monthly.date.dt.to_period("M")
        monthly = monthly.drop_duplicates("period", keep="last")
        result = build_history(monthly, frequency="monthly")
        self.assertEqual(result["frequency"], "monthly")
        self.assertTrue(110 <= len(result["series"]["csi500"]["points"]) <= 125)
        self.assertEqual(set(result["series"]["csi500"]["periods"]), {"3", "5", "10"})

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
