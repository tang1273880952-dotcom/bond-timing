"""Regression tests: monthly-frozen horizontal ERP percentile references."""
import unittest

import pandas as pd

from history_chart import (
    build_history, build_monthly_erp, official_csi500_erp,
    official_csi500_close, build_index_overlay,
)


class TestHistoryChart(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2005-10-25", "2026-10-28")
        self.frame = pd.DataFrame({
            "date": dates,
            "erp": [0.8 + (i % 311) / 100 for i in range(len(dates))],
        })

    def test_weekly_true_erp_and_five_horizontals(self):
        result = build_history(self.frame)
        self.assertEqual(result["version"], 6)
        self.assertEqual(result["frequency"], "weekly")
        d = result["series"]["csi500"]
        self.assertTrue(480 <= len(d["points"]) <= 530)
        self.assertEqual(d["points"][-1][0], "2026-10-28")
        for years in (3, 5, 10):
            ref = d["periods"][str(years)]
            self.assertEqual(ref["referenceDate"], "2026-09-30")
            self.assertEqual(ref["referenceMonth"], "2026-09")
            self.assertNotIn("bands", ref)
            values = self.frame.loc[
                (self.frame.date >= pd.Timestamp("2026-09-30") - pd.DateOffset(years=years)) &
                (self.frame.date <= pd.Timestamp("2026-09-30")), "erp"
            ]
            self.assertEqual(ref["sampleCount"], len(values))
            for q in (10, 20, 50, 80, 90):
                self.assertEqual(ref[f"p{q}"], round(float(values.quantile(q / 100)), 4))
            self.assertEqual(ref["percentile"], round(float(
                values.le(self.frame.erp.iloc[-1]).mean() * 100
            ), 2))
            self.assertTrue(ref["p10"] <= ref["p20"] <= ref["p50"] <=
                            ref["p80"] <= ref["p90"])

    def test_reference_stable_throughout_current_month(self):
        early = self.frame[self.frame.date <= pd.Timestamp("2026-10-09")]
        late = self.frame[self.frame.date <= pd.Timestamp("2026-10-28")]
        x = build_history(early)["series"]["csi500"]["periods"]
        y = build_history(late)["series"]["csi500"]["periods"]
        for years in ("3", "5", "10"):
            for q in (10, 20, 50, 80, 90):
                self.assertEqual(x[years][f"p{q}"], y[years][f"p{q}"])
            self.assertEqual(x[years]["referenceDate"], y[years]["referenceDate"])

    def test_reference_changes_after_month_turn(self):
        early = build_history(self.frame[
            self.frame.date <= pd.Timestamp("2026-09-30")
        ])["series"]["csi500"]["periods"]
        late = build_history(self.frame)["series"]["csi500"]["periods"]
        for years in ("3", "5", "10"):
            self.assertEqual(early[years]["referenceMonth"], "2026-08")
            self.assertEqual(late[years]["referenceMonth"], "2026-09")
            self.assertNotEqual(early[years]["referenceDate"], late[years]["referenceDate"])
            self.assertGreater(late[years]["sampleCount"], 100)

    def test_missing_full_lookback_is_not_fabricated(self):
        incomplete = self.frame[self.frame.date >= pd.Timestamp("2016-10-28")]
        with self.assertRaises(ValueError):
            build_history(incomplete)

    def test_monthly_fallback_labelled(self):
        m = self.frame.copy()
        m["month"] = m.date.dt.to_period("M")
        m = m.drop_duplicates("month", keep="last")
        result = build_history(m, frequency="monthly")
        self.assertEqual(result["frequency"], "monthly")
        self.assertEqual(result["series"]["csi500"]["periods"]["10"]["basis"], "月度真实观测")
        self.assertEqual(result["series"]["csi500"]["periods"]["10"]["referenceMonth"], "2026-09")

    def test_ten_year_legacy_source_is_consistent(self):
        m = self.frame.copy()
        m["month"] = m.date.dt.to_period("M")
        m = m.drop_duplicates("month", keep="last")
        m = m[m.date >= pd.Timestamp("2007-01-01")]
        result = build_history(self.frame, long_term_monthly=m)
        periods = result["series"]["csi500"]["periods"]
        self.assertEqual(periods["10"]["basis"], "月度真实观测")
        self.assertEqual(periods["3"]["basis"], "日度真实观测")
        self.assertEqual(periods["10"]["referenceDate"], "2026-09-30")
        v = m.loc[
            (m.date >= pd.Timestamp("2026-09-30") - pd.DateOffset(years=10)) &
            (m.date <= pd.Timestamp("2026-09-30")), "erp"
        ]
        self.assertEqual(periods["10"]["p80"], round(float(v.quantile(.8)), 4))

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
