"""Test real ERP sampling and monthly rolling bands without future leakage."""
import unittest

import pandas as pd
from history_chart import build_history, build_monthly_erp, official_csi500_erp, official_csi500_close, build_index_overlay


class TestHistoryChart(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2005-10-25", "2026-10-28")
        self.frame = pd.DataFrame({
            "date": dates,
            "erp": [0.8 + (i % 311) / 100 for i in range(len(dates))],
        })

    def test_real_weekly_and_complete_bands(self):
        result = build_history(self.frame)
        self.assertEqual(result["frequency"], "weekly")
        self.assertEqual(result["version"], 5)
        stock = result["series"]["csi500"]
        self.assertTrue(480 <= len(stock["points"]) <= 530)
        self.assertEqual(stock["points"][-1][0], "2026-10-28")
        for date, value in stock["points"]:
            actual = self.frame.loc[self.frame.date == pd.Timestamp(date), "erp"]
            self.assertEqual(value, round(float(actual.iloc[0]), 4))
        for years in (3, 5, 10):
            p = stock["periods"][str(years)]
            cutoff = self.frame.date.iloc[-1] - pd.DateOffset(years=years)
            v = self.frame.loc[self.frame.date >= cutoff, "erp"]
            self.assertEqual(p["sampleCount"], len(v))
            self.assertEqual(p["p90"], round(float(v.quantile(.9)), 4))
            self.assertEqual(p["percentile"],
                             round(float(v.le(v.iloc[-1]).mean()*100), 2))
            self.assertTrue(len(p["bands"]) >= 115)
            for row in p["bands"]:
                self.assertEqual(len(row), 6)
            self.assertEqual(p["bands"][-1][0], "2026-10-28")

    def test_no_lookahead_or_backfill(self):
        future = self.frame.copy()
        target = pd.Timestamp("2021-09-30")
        after = future.date > target
        changed = future.copy()
        changed.loc[after, "erp"] += 250
        original = build_history(future)["series"]["csi500"]["periods"]["5"]["bands"]
        modified = build_history(changed)["series"]["csi500"]["periods"]["5"]["bands"]
        before1 = [row for row in original if row[0] <= str(target.date())]
        before2 = [row for row in modified if row[0] <= str(target.date())]
        self.assertEqual(before1, before2)
        self.assertNotEqual(original[-1][3], modified[-1][3])

    def test_real_history_gap_not_fabricated(self):
        f = self.frame[self.frame.date >= pd.Timestamp("2016-10-28")]
        r = build_history(f)
        bands10 = r["series"]["csi500"]["periods"]["10"]["bands"]
        self.assertEqual(len(bands10), 1)
        self.assertEqual(bands10[-1][0], "2026-10-28")
        self.assertTrue(len(r["series"]["csi500"]["periods"]["3"]["bands"]) >= 80)

    def test_monthly_fallback_labelled(self):
        f = self.frame.copy()
        f["month"] = f.date.dt.to_period("M")
        monthly = f.drop_duplicates("month", keep="last")
        r = build_history(monthly, frequency="monthly")
        self.assertEqual(r["frequency"], "monthly")
        self.assertTrue(len(r["series"]["csi500"]["periods"]["10"]["bands"]) >= 110)


    def test_extend_ten_year_band_with_real_monthly_history(self):
        monthly = self.frame.copy()
        monthly["month"] = monthly.date.dt.to_period("M")
        monthly = monthly.drop_duplicates("month", keep="last").drop(columns="month")
        monthly = monthly[monthly.date >= pd.Timestamp("2007-01-01")]
        result = build_history(self.frame, long_term_monthly=monthly)
        p10 = result["series"]["csi500"]["periods"]["10"]
        self.assertEqual(result["version"], 5)
        self.assertEqual(p10["basis"], "月度真实观测")
        self.assertTrue(p10["availableFrom"].startswith("2017"))
        self.assertGreaterEqual(len(p10["bands"]), 115)
        self.assertEqual(p10["bands"][-1][0], "2026-10-28")
        self.assertEqual(p10["p80"], round(float(monthly.loc[
            monthly.date >= monthly.date.iloc[-1] - pd.DateOffset(years=10)
        ].erp.quantile(.8)), 4))
        self.assertEqual(result["series"]["csi500"]["periods"]["3"]["basis"], "日度真实观测")
        self.assertEqual(p10["bands"][0][0][:7], "2017-01")
        self.assertEqual(p10["referenceERP"], round(float(monthly.erp.iloc[-1]), 4))

    def test_monthly_pe_matches_only_past_yield(self):
        dates = pd.date_range("2007-01-31", periods=239, freq="ME")
        pe = pd.DataFrame({"date": dates, "pe": 20.0})
        yields = pd.DataFrame({"date": dates, "y10": 2.0})
        matched = build_monthly_erp(pe, yields)
        self.assertEqual(len(matched), len(dates))
        self.assertAlmostEqual(matched.erp.iloc[-1], 3.0)
        self.assertEqual(str(matched.date.iloc[0].date()), "2007-01-31")


    def test_real_weekly_index_close(self):
        dates = pd.bdate_range("2016-10-18", "2026-10-28")
        data = pd.DataFrame({"date": dates, "close": [3500 + i * 0.6 for i in range(len(dates))]})
        index = build_index_overlay(data, pd.Timestamp("2026-10-28"))
        self.assertEqual(index["code"], "000905")
        self.assertEqual(index["unit"], "点")
        self.assertEqual(index["frequency"], "weekly")
        self.assertTrue(480 <= len(index["points"]) <= 530)
        self.assertEqual(index["points"][-1][0], "2026-10-28")
        self.assertEqual(index["latest"], round(float(data.close.iloc[-1]), 2))
        for date, close in index["points"]:
            self.assertEqual(float(data.loc[data.date == pd.Timestamp(date), "close"].iloc[0]), close)

    def test_index_close_api_is_actual_000905(self):
        dates = pd.bdate_range("2024-01-02", "2026-10-28")
        def fake_api(symbol, start_date, end_date):
            self.assertEqual(symbol, "000905")
            days = dates[(dates >= pd.Timestamp(start_date)) & (dates <= pd.Timestamp(end_date))]
            return pd.DataFrame({"日期": days, "指数代码": "000905",
                                 "收盘": [5000 + j for j in range(len(days))]})
        result = official_csi500_close(pd.Timestamp("2026-10-28"),
                                      api=fake_api, start="2026-01-01")
        self.assertGreater(len(result), 180)
        self.assertEqual(str(result.date.iloc[-1].date()), "2026-10-28")
        self.assertTrue((result.close > 0).all())

    def test_index_overlay_rejects_incomplete_history(self):
        dates = pd.bdate_range("2024-01-01", "2026-10-28")
        with self.assertRaises(ValueError):
            build_index_overlay(pd.DataFrame({"date": dates, "close": 4000}),
                                pd.Timestamp("2026-10-28"))

    def test_index_source_never_uses_future_yield(self):
        dates = pd.bdate_range("2016-10-20", "2026-10-28")
        yields = pd.DataFrame({"date": dates, "y10": 2.0})
        def fake_api(symbol, start_date, end_date):
            self.assertEqual(symbol, "000905")
            day = dates[(dates >= pd.Timestamp(start_date)) &
                        (dates <= pd.Timestamp(end_date))]
            return pd.DataFrame({"日期": day, "指数代码": "000905", "滚动市盈率": 20.})
        matched = official_csi500_erp(yields, pd.Timestamp("2026-10-28"), api=fake_api)
        self.assertGreater(len(matched), 2000)
        self.assertAlmostEqual(matched.erp.iloc[-1], 3.0)


if __name__ == "__main__":
    unittest.main()
