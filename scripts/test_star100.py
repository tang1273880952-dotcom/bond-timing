"""Star100 index and point-in-time ERP checks."""
import unittest

import pandas as pd

from star100 import official_daily, build_star100


class TestStar100(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2023-08-07", "2026-10-28")
        self.daily = pd.DataFrame({
            "date": self.dates,
            "close": [950 + i * .3 for i in range(len(self.dates))],
            "pe": [30 + (i % 270) * .1 for i in range(len(self.dates))],
        })
        self.y = pd.DataFrame({"date": self.dates, "y10": 2.0})

    def test_monthly_locked_true_values(self):
        d = build_star100(self.daily, self.y, "2026-10-28")
        self.assertTrue(d["valid"])
        self.assertEqual(set(d["periods"]), {"1", "3"})
        self.assertEqual(d["code"], "000698")
        self.assertEqual(d["date"], "2026-10-28")
        self.assertEqual(d["periods"]["3"]["referenceDate"], "2026-09-30")
        self.assertTrue(145 <= len(d["points"]) <= 180)
        self.assertEqual(d["indexPoints"][-1][0], "2026-10-28")
        for years in ("1", "3"):
            p = d["periods"][years]
            self.assertLess(p["p10"], p["p90"])
        early = build_star100(
            self.daily[self.daily.date <= pd.Timestamp("2026-10-12")],
            self.y, "2026-10-12"
        )
        self.assertEqual(d["periods"]["3"]["p80"], early["periods"]["3"]["p80"])

    def test_mixed_datetime_units_from_csv_cache(self):
        # The real yield cache parsed dates at microsecond precision while
        # per-index CSV price cache used seconds: both must align safely.
        daily = self.daily.copy()
        yields = self.y.copy()
        daily["date"] = daily["date"].astype("datetime64[s]")
        yields["date"] = yields["date"].astype("datetime64[us]")
        result = build_star100(daily, yields, "2026-10-28")
        self.assertTrue(result["valid"])
        self.assertIn("3", result["periods"])

    def test_no_fake_pe_when_missing(self):
        data = self.daily.copy()
        data["pe"] = float("nan")
        result = build_star100(data, self.y, "2026-10-28")
        self.assertFalse(result["valid"])
        self.assertIn("PE", result["reason"])
        self.assertGreater(len(result["indexPoints"]), 150)

    def test_official_symbol_verification(self):
        def fake_api(symbol, start_date, end_date):
            self.assertEqual(symbol, "000698")
            dates = self.dates[(self.dates >= pd.Timestamp(start_date)) &
                               (self.dates <= pd.Timestamp(end_date))]
            return pd.DataFrame({
                "日期": dates, "指数代码": ["000698"] * len(dates),
                "收盘": 1200, "滚动市盈率": 44.0
            })
        data = official_daily("2026-10-28", api=fake_api)
        self.assertEqual(str(data.date.iloc[-1].date()), "2026-10-28")
        self.assertEqual(len(data), len(self.dates))


if __name__ == "__main__":
    unittest.main()
