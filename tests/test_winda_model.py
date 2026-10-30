import importlib.util
from pathlib import Path
import unittest
import pandas as pd

path=Path(__file__).resolve().parents[1]/"scripts"/"update_winda.py"
spec=importlib.util.spec_from_file_location("winda_tested",path)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class WindAllAValuationTests(unittest.TestCase):
    def test_symbol_and_reject_wrong_columns(self):
        self.assertEqual(w.WIND_CODE,"881001.WI")
        with self.assertRaises(ValueError):
            w.normalize_pe(pd.DataFrame({"日期":["2026-10-29"],"中证全指PE":[20.0]}))
        with self.assertRaises(ValueError):
            w.normalize_pe(pd.DataFrame({"日期":["2026-10-29"],"市盈率":[-6]}))

    def test_build_real_matched_erp_and_percentiles(self):
        dates=pd.bdate_range("2016-09-20","2026-10-29")
        pe=pd.DataFrame({"日期":dates,"市盈率":[15+(i%120)*.05 for i in range(len(dates))]})
        y=pd.DataFrame({"date":dates,"y10":[2.0]*len(dates)})
        out=w.build_winda(pe,y,pd.Timestamp("2026-10-30"))
        self.assertEqual(out["code"],"881001.WI")
        self.assertAlmostEqual(out["erp"],round(100/out["pe"]-2,4),places=3)
        for yr in ("3","5","10"):
            p=out["periods"][yr]
            self.assertLess(p["p10"],p["p90"])
            self.assertLess(p["p20"],p["p80"])
            self.assertTrue(0<=p["percentile"]<=100)
            self.assertEqual(p["referenceDate"],"2026-09-30")
            self.assertGreater(p["sampleCount"],int(yr)*150)
        self.assertEqual(out["points"][-1][0],"2026-10-29")

    def test_no_fabricated_history_or_stale_pe(self):
        dates=pd.bdate_range("2025-01-01","2026-10-29")
        pe=pd.DataFrame({"date":dates,"pe":[20.0]*len(dates)})
        y=pd.DataFrame({"date":dates,"y10":[2.0]*len(dates)})
        with self.assertRaises(ValueError):
            w.build_winda(pe,y,pd.Timestamp("2026-10-30"))
        dates=pd.bdate_range("2016-01-01","2026-09-30")
        pe=pd.DataFrame({"date":dates,"pe":[20.0]*len(dates)})
        y=pd.DataFrame({"date":dates,"y10":[2.0]*len(dates)})
        with self.assertRaises(ValueError):
            w.build_winda(pe,y,pd.Timestamp("2026-10-30"))

if __name__=="__main__":unittest.main()
