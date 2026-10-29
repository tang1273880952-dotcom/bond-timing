"""Regression: 12y China-yield cache refreshes only the recent tail."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from update import cached_china_yields


class YieldCacheTest(unittest.TestCase):
    def setUp(self):
        self.today=pd.Timestamp("2026-10-29")
        dates=pd.bdate_range(self.today-pd.Timedelta(days=12*366),self.today)
        self.all_data=pd.DataFrame({
            "date":dates,"y1":1.25,"y10":2.1,"y30":2.5,
        })
        self.calls=[]

    def fetch(self,start,end):
        self.calls.append((pd.Timestamp(start),pd.Timestamp(end)))
        f=self.all_data
        return f[(f.date>=pd.Timestamp(start))&(f.date<=pd.Timestamp(end))].copy()

    def test_full_bootstrap_then_short_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"china_yields_daily.csv"
            first=cached_china_yields(self.today,self.fetch,path)
            self.assertEqual(len(self.calls),1)
            self.assertGreater((self.calls[0][1]-self.calls[0][0]).days,4000)
            self.assertGreater(len(first),2500)
            second=cached_china_yields(self.today,self.fetch,path)
            self.assertEqual(len(self.calls),2)
            self.assertLessEqual((self.calls[1][1]-self.calls[1][0]).days,60)
            self.assertEqual(len(first),len(second))
            self.assertEqual(float(second.y10.iloc[-1]),2.1)
            self.assertEqual(second.date.nunique(),len(second))

    def test_incomplete_history_never_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"china_yields_daily.csv"
            short=self.all_data.tail(300)
            def broken(start,end):
                return short.copy()
            with self.assertRaises(ValueError):
                cached_china_yields(self.today,broken,path)
            self.assertFalse(path.exists())


if __name__=="__main__":
    unittest.main()
