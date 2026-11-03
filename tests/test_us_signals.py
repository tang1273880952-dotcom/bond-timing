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
        self.assertTrue(all(v==50 for v in m.rsi14([100.0]*60)[14:]),
                        "No price changes must produce neutral RSI50")
        self.assertTrue(all(v==0 for v in m.rsi14([100-i for i in range(60)])[14:]))
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
    def test_missing_credit_is_not_fabricated_or_treated_as_buy_confirmation(self):
        price,vix,credit,us=self.setup_data()
        d=m.build_model(price,vix,None,us,asof="2026-11-03")
        self.assertEqual(d["coveredWeight"],70)
        self.assertEqual(d["missingWeight"],30)
        self.assertTrue(d["riskDataIncomplete"])
        self.assertIn("credit",d["missingIndicators"])
        self.assertIsNone(d["indicators"]["credit"]["score"])
        self.assertIsNone(d["indicators"]["credit"]["value"])
        self.assertTrue(d["riskVeto"])
        self.assertNotIn(d["action"],["试探性观察买入","关注分批买入"])
        # Fewer than ~one-year daily credit observations must not be
        # presented as a one-year historical spread percentile.
        d=m.build_model(price,vix,credit.tail(50),us,asof="2026-11-03")
        self.assertEqual(d["coveredWeight"],70)
        self.assertTrue(d["riskVeto"])

    def test_free_snp_breadth_and_hy_mirror_have_real_inputs(self):
        import math
        dates=pd.bdate_range(end="2026-10-30",periods=250)
        breadth_doc={"metadata":{"universe":"S&P 500","data_source":"Yahoo Finance (yfinance)"},
           "data":[{"date":str(d.date()),"ma_50":{"count_above":336,
                  "percentage_above":66.93}} for d in dates]}
        breadth=m.parse_breadth_history(breadth_doc)
        self.assertEqual(len(breadth),250)
        self.assertEqual(breadth["value"].iloc[-1],66.93)
        rows=["observation_date,BAMLH0A0HYM2"]+[
          f"{str(d.date())},{round(3.0+0.20*math.sin(i/21),4)}"
          for i,d in enumerate(dates)]
        credit=m.parse_credit_mirror_csv("\n".join(rows))
        self.assertEqual(len(credit),250)
        self.assertIn("FRED",credit.attrs["provider"])
        price,vix,_,us=self.setup_data()
        model=m.build_model(price,vix,credit,us,asof="2026-11-03",breadth=breadth)
        self.assertEqual(model["coveredWeight"],100)
        self.assertEqual(model["missingWeight"],0)
        self.assertEqual(model["missingIndicators"],[])
        self.assertTrue(model["complete"])
        self.assertFalse(model["riskDataIncomplete"])
        self.assertEqual(model["indicators"]["breadth"]["value"],66.93)
        self.assertIsNotNone(model["indicators"]["breadth"]["score"])
        self.assertIsNotNone(model["indicators"]["credit"]["score"])
        self.assertEqual(model["indicators"]["breadth"]["date"],"2026-10-30")

    def test_invalid_or_stale_breadth_cannot_be_fabricated(self):
        dates=pd.bdate_range(end="2026-10-30",periods=160)
        doc={"metadata":{"universe":"S&P 500","data_source":"Yahoo Finance (yfinance)"},
              "data":[{"date":str(d.date()),"ma_50":{"count_above":340,
                       "percentage_above":67.73}} for d in dates]}
        with self.assertRaises(ValueError):
            bad=dict(doc,metadata={"universe":"NASDAQ-100","data_source":"yfinance"})
            m.parse_breadth_history(bad)
        with self.assertRaises(ValueError):
            bad=dict(doc,data=doc["data"][:-1]+[{"date":"2026-10-30","ma_50":
                {"count_above":340,"percentage_above":1}}])
            m.parse_breadth_history(bad)
        breadth=m.parse_breadth_history(doc)
        price,vix,credit,us=self.setup_data()
        old=breadth.iloc[:-15].copy()
        model=m.build_model(price,vix,credit,us,asof="2026-11-03",breadth=old)
        self.assertEqual(model["coveredWeight"],85)
        self.assertIn("breadth",model["missingIndicators"])
        # A malformed historic OAS export cannot be silently scored.
        with self.assertRaises(ValueError):
            m.parse_credit_mirror_csv("observation_date,wrong\n2026-10-30,3.44\n")

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
    def test_future_vix_credit_or_erp_cannot_leak_into_prior_close(self):
        price,vix,credit,us=self.setup_data()
        vix.loc[vix.index[-1],"date"]=pd.Timestamp("2026-11-02")
        with self.assertRaises(ValueError):
            m.build_model(price,vix,credit,us,asof="2026-11-03")
        price,vix,credit,us=self.setup_data()
        credit.loc[credit.index[-1],"date"]=pd.Timestamp("2026-11-02")
        with self.assertRaises(ValueError):
            m.build_model(price,vix,credit,us,asof="2026-11-03")
        price,vix,credit,us=self.setup_data()
        us["valuationDate"]="2026-11-02"
        with self.assertRaises(ValueError):
            m.build_model(price,vix,credit,us,asof="2026-11-03")

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
