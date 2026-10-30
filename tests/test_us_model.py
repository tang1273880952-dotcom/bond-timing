"""US model regressions: paired yield date must be the actual past observation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import pandas as pd

p=Path(__file__).resolve().parents[1]/"scripts"/"update_us.py"
spec=importlib.util.spec_from_file_location("us_model",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class USAudit(unittest.TestCase):
    def test_monthly_backfill_uses_earlier_yield_and_reports_matched_date(self):
        now=pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None).normalize()
        end=pd.Timestamp(year=now.year,month=now.month,day=1)
        months=pd.date_range(end=end,periods=133,freq="MS")
        pe=pd.DataFrame({"date":months+pd.Timedelta(days=14),"pe":26.0,
                         "estimated":False})
        yields=pd.DataFrame({"date":months,"yield10":4.5})
        # A newer yield observation exists, but it is AFTER the PE date.
        newer=end+pd.Timedelta(days=22)
        if newer<=now:
            yields=pd.concat([yields,pd.DataFrame([{"date":newer,"yield10":9.9}])],
                             ignore_index=True)
        prices=pd.DataFrame({"date":months,"spx":5000.0})
        def table(url,col):
            return yields.rename(columns={"yield10":col}) if col=="yield10" else prices
        with patch.object(m,"get_pe",return_value=pe),patch.object(m,"monthly_table",side_effect=table):
            result=m.calculate()
        self.assertEqual(result["yieldDate"],str(end.date()))
        self.assertEqual(result["metrics"][6][1],str(end.date()))
        self.assertAlmostEqual(float(result["metrics"][2][1].rstrip("%")),
                               100/26-4.5,places=2)
        self.assertNotIn("9.9",str(result["metrics"]))

if __name__=="__main__":unittest.main()
