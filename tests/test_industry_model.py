"""Regression tests for genuine industry index valuation history and quantiles."""
import importlib.util
from pathlib import Path
import unittest
import pandas as pd

path=Path(__file__).resolve().parents[1]/"scripts"/"update_industry.py"
spec=importlib.util.spec_from_file_location("industry",path)
industry=importlib.util.module_from_spec(spec)
spec.loader.exec_module(industry)

class IndustryValuationTests(unittest.TestCase):
    def test_seven_expected_symbols(self):
        self.assertEqual([c for c,_,_ in industry.SYMBOLS],
            ["399975","399989","399971","399998","000807","399997","399986"])

    def test_csi_pe_column_not_index_price(self):
        row=["2026-10-29","399997","中证白酒","白酒","CSI", "CSI",
             1,2,3,99999,4,5,6,7,18,20.75]
        out=industry.parse_csi_payload({"data":[row]},"399997")
        self.assertEqual(out.pe.iloc[-1],20.75)
        self.assertNotEqual(out.pe.iloc[-1],99999)
        self.assertTrue(industry.parse_csi_payload({"data":[row]},"399998").empty)
        # Real 2026 official CSI endpoint uses object rows and 'peg' for PE.
        live={"tradeDate":"20261029","indexCode":"399997",
              "close":99999,"peg":20.75}
        actual=industry.parse_csi_payload({"data":[live]},"399997")
        self.assertEqual(actual.pe.iloc[-1],20.75)
        self.assertNotEqual(actual.pe.iloc[-1],99999)

    def test_quantiles_and_current_and_insufficient_history(self):
        dates=pd.bdate_range("2016-09-01","2026-10-29",freq="B")
        frame=pd.DataFrame({"date":dates,"pe":[10+i%100/10 for i in range(len(dates))]})
        result=industry.build_index("399997","中证白酒","PE-TTM",frame,pd.Timestamp("2026-10-30"))
        self.assertEqual(result["metric"],"PE-TTM")
        self.assertEqual(result["points"][-1][0],"2026-10-29")
        for n in ("3","5","10"):
            self.assertIn(n,result["periods"])
            b=result["periods"][n]
            self.assertLessEqual(b["p0"],b["p10"])
            self.assertLessEqual(b["p10"],b["p20"])
            self.assertLessEqual(b["p20"],b["p50"])
            self.assertLessEqual(b["p50"],b["p80"])
            self.assertLessEqual(b["p80"],b["p90"])
            self.assertLessEqual(b["p90"],b["p100"])
            self.assertEqual(b["p0"],round(float(frame.loc[
                (frame.date>=pd.Timestamp(b["referenceDate"])-pd.DateOffset(years=int(n)))&
                (frame.date<=pd.Timestamp(b["referenceDate"])),"pe"].min()),4))
            self.assertEqual(b["p100"],round(float(frame.loc[
                (frame.date>=pd.Timestamp(b["referenceDate"])-pd.DateOffset(years=int(n)))&
                (frame.date<=pd.Timestamp(b["referenceDate"])),"pe"].max()),4))
            self.assertTrue(0<=b["percentile"]<=100)
            self.assertTrue(b["referenceDate"].startswith("2026-09"))
        # Current month is never used to calculate the historical bands/rank.
        # Check the same historical reference produces 0% and 100% when the
        # newest value falls outside the prior complete-month range.
        upper=frame.copy()
        upper.loc[upper.index[-1],"pe"]=200
        out=industry.build_index("399997","中证白酒","PE-TTM",upper,pd.Timestamp("2026-10-30"))
        self.assertEqual(out["periods"]["3"]["percentile"],100)
        self.assertLess(out["periods"]["3"]["p100"],out["value"])
        lower=frame.copy()
        lower.loc[lower.index[-1],"pe"]=1
        out=industry.build_index("399997","中证白酒","PE-TTM",lower,pd.Timestamp("2026-10-30"))
        self.assertEqual(out["periods"]["3"]["percentile"],0)
        self.assertGreater(out["periods"]["3"]["p0"],out["value"])
        # Verify percentile is based on the SAME exact rows as p0-p100.
        q=result["periods"]["3"]
        ref_date=pd.Timestamp(q["referenceDate"])
        sample=frame.loc[(frame.date>=ref_date-pd.DateOffset(years=3))&
                         (frame.date<=ref_date),"pe"]
        self.assertAlmostEqual(q["percentile"],
            round(float(sample.le(result["value"]).mean()*100),2),places=2)
        short=frame[frame.date>="2024-01-01"]
        with self.assertRaises(ValueError):
            industry.build_index("399975","证券公司","PB",short,pd.Timestamp("2026-10-30"))

    def test_verified_pb_weekly_history_distinct_from_pb_multiples(self):
        import json
        days=pd.date_range(end="2026-10-29",periods=500,freq="7D")
        series=[{"date":str(t.date()),"pb_pct":round(i%90+0.1,2)}
                for i,t in enumerate(days)]
        series[-1]["pb_pct"]=1.2
        html=('<html><body>代码： 399975 市场： A股 最新交易日： 2026-10-29 '
              'PB · 市净率 极冷 1.11 近 10 年百分位 1.2% '
              '<script>var d='+json.dumps(series)+';</script></body></html>')
        item=industry.parse_public_pb_page(html,"399975","2026-10-30")
        self.assertEqual(item["metric"],"PB")
        self.assertEqual(item["value"],1.11)
        self.assertEqual(item["pointMetric"],"PB_10Y_PERCENTILE")
        self.assertEqual(item["points"][-1][1],1.2)
        self.assertEqual(item["periods"]["10"]["rankYears"],10)
        self.assertEqual(set(item["periods"]),{"10"})
        self.assertEqual(item["periods"]["10"]["p0"],0)
        self.assertEqual(item["periods"]["10"]["p100"],100)
        self.assertEqual(item["periods"]["10"]["percentile"],1.2)
        self.assertNotIn("pe",item)
        with self.assertRaises(ValueError):
            industry.parse_public_pb_page(html,"399986","2026-10-30")
        with self.assertRaises(ValueError):
            industry.parse_public_pb_page(html.replace("1.11 近","11.11 近"),"399975","2026-11-30")

    def test_actual_broker_historical_pb_has_independent_yearly_bands(self):
        import math
        dates=pd.date_range(end="2026-10-29",periods=685,freq="7D")
        # Make 3-, 5-, 10-year windows have deliberately different PB
        # distributions. This catches any accidental reuse of ten-year rank.
        raw=[]
        for d in dates:
            y=(pd.Timestamp("2026-10-29")-d).days/365.25
            value=(1.18+0.2*math.sin(len(raw)/21)
                   if y<=3 else
                   1.8+0.16*math.sin(len(raw)/17) if y<=5 else
                   2.4+0.22*math.sin(len(raw)/19))
            raw.append({"d":str(d.date()),"v":round(value,4)})
        raw[-1]["v"]=1.80
        payload={"index":{"code":"399975","date":"2026-10-29","pb":1.80},
                 "series":{"pb":raw}}
        item=industry.parse_guchacha_pb(payload,"399975","2026-10-31")
        self.assertEqual(item["metric"],"PB")
        self.assertEqual(item["pointMetric"],"PB_MULTIPLE")
        self.assertEqual(item["value"],1.80)
        self.assertEqual(set(item["periods"]),{"3","5","10"})
        self.assertEqual(item["points"][-1][1],1.80)
        ranks=[item["periods"][str(n)]["percentile"] for n in (3,5,10)]
        self.assertNotEqual(len(set(ranks)),1,"selected PB ranks must change")
        for yrs in (3,5,10):
            period=item["periods"][str(yrs)]
            self.assertEqual(period["rankYears"],yrs)
            self.assertLess(period["p10"],period["p90"])
            self.assertLess(period["p0"],period["p100"])
            self.assertTrue(0<=period["percentile"]<=100)
            self.assertTrue(period["referenceDate"]<"2026-10-01")
        with self.assertRaises(ValueError):
            industry.parse_guchacha_pb(payload,"399986","2026-10-31")
        payload["series"]["pb"][-1]["v"]=5.4
        with self.assertRaises(ValueError):
            industry.parse_guchacha_pb(payload,"399975","2026-10-31")

    def test_missing_data_is_not_fabricated(self):
        with self.assertRaises(ValueError):
            industry.parse_csi_payload({"other":[]},"399975")
        frame=pd.DataFrame({"date":["2026-10-29"],"pe":[0]})
        self.assertTrue(industry.normalize(frame).empty)

if __name__=="__main__":
    unittest.main()
