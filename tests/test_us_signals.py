"""Source-backed S&P 500 daily trading-observation model tests."""
import importlib.util
import sys
from pathlib import Path
import unittest
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("signals",ROOT/"scripts"/"update_us_signals.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class USSignalsTest(unittest.TestCase):
    def setup_data(self):
        dates=pd.bdate_range(end="2026-10-30",periods=320)
        price=pd.DataFrame({"date":dates,"value":[5500+i*3+30*(i%7) for i in range(len(dates))]})
        vix=pd.DataFrame({"date":dates,"value":[19+(i%11)*.15 for i in range(len(dates))]})
        credit=pd.DataFrame({"date":dates,"value":[3.8+(i%13)*.01 for i in range(len(dates))]})
        us={"id":"sp500","mode":"live","valuationDate":"2026-10-30",
            "history":{"periods":{"10":{"percentile":18.2}}}}
        return price,vix,credit,us
    def test_rsi_wilder_initial_and_bounds(self):
        result=m.rsi14([100+i*.35 for i in range(60)])
        self.assertIsNone(result[13])
        self.assertAlmostEqual(result[14],100)
        self.assertTrue(all(0<=x<=100 for x in result[14:]))
        self.assertEqual(len(result),60)
    def test_stable_no_invented_breadth_and_score_coverage(self):
        d=m.build_model(*self.setup_data(),asof="2026-11-03")
        self.assertTrue(d["valid"])
        self.assertEqual(d["mode"],"sp500-signals-v1")
        self.assertEqual(d["coveredWeight"],85)
        self.assertEqual(d["missingWeight"],15)
        self.assertFalse(d["complete"])
        self.assertIsNone(d["indicators"]["breadth"]["value"])
        self.assertIsNone(d["indicators"]["breadth"]["score"])
        self.assertEqual(len(d["confirmations"]),3)
        self.assertTrue(0<=d["score"]<=100)
        self.assertEqual(len(d["priceHistory"]),260)
        self.assertEqual(d["asof"],"2026-10-30")
        weighted=sum(i["score"] for i in d["indicators"].values() if i["score"] is not None)
        self.assertLessEqual(abs(d["score"]-round(weighted/85*100)),1)
        self.assertEqual(d["indicators"]["erp"]["date"],"2026-10-30")
        self.assertTrue(all("met" in x for x in d["confirmations"]))
    def test_future_or_stale_sources_are_refused(self):
        a=list(self.setup_data())
        with self.assertRaises(ValueError):
            m.build_model(*a,asof="2026-11-20")
        a[1]=a[1].iloc[:-15].copy()
        with self.assertRaises(ValueError):
            m.build_model(*a,asof="2026-11-03")
        a=list(self.setup_data());a[3]["history"]["periods"]["10"]["percentile"]=None
        with self.assertRaises(ValueError):
            m.build_model(*a,asof="2026-11-03")
    def test_no_trade_signal_on_single_vix_extreme(self):
        price,vix,credit,us=self.setup_data()
        vix["value"]=42.0
        # An extreme VIX alone must not force "buy".
        d=m.build_model(price,vix,credit,us,asof="2026-11-03")
        self.assertNotIn(d["action"],["试探性观察买入","关注分批买入"])
    def test_response_rejects_unverified_raw_market_values(self):
        price,vix,credit,us=self.setup_data()
        price.loc[price.index[-1],"value"]=-1
        with self.assertRaises(ValueError):
            m.build_model(price,vix,credit,us,asof="2026-11-03")

if __name__=="__main__":unittest.main()
