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
            self.assertLessEqual(b["p10"],b["p20"])
            self.assertLessEqual(b["p20"],b["p50"])
            self.assertLessEqual(b["p50"],b["p80"])
            self.assertLessEqual(b["p80"],b["p90"])
            self.assertTrue(0<=b["percentile"]<=100)
            self.assertTrue(b["referenceDate"].startswith("2026-09"))
        short=frame[frame.date>="2024-01-01"]
        with self.assertRaises(ValueError):
            industry.build_index("399975","证券公司","PB",short,pd.Timestamp("2026-10-30"))

    def test_missing_data_is_not_fabricated(self):
        with self.assertRaises(ValueError):
            industry.parse_csi_payload({"other":[]},"399975")
        frame=pd.DataFrame({"date":["2026-10-29"],"pe":[0]})
        self.assertTrue(industry.normalize(frame).empty)

if __name__=="__main__":
    unittest.main()
