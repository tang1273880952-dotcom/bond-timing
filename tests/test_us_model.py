"""US model regressions: paired yield date must be the actual past observation."""
import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import pandas as pd

p=Path(__file__).resolve().parents[1]/"scripts"/"update_us.py"
sys.path.insert(0,str(p.parent))
spec=importlib.util.spec_from_file_location("us_model",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class USAudit(unittest.TestCase):
    def history_source(self):
        dates=pd.date_range("2014-01-01","2026-10-01",freq="MS")
        pe=pd.Series([18+i/50 for i in range(len(dates))])
        values=pd.DataFrame({"date":dates,"pe":pe,"yield10":3.0,"estimated":False,
                             "yieldSourceDate":dates})
        values["erp"]=100/values.pe-values.yield10
        return values

    def test_history_uses_distinct_completed_month_windows(self):
        source=self.history_source()
        history=m.build_erp_history(source)
        for years,period in history["periods"].items():
            self.assertEqual(period["referenceDate"],"2026-09-30")
            self.assertEqual(period["sampleCount"],12*int(years))
            sample=source[(source.date>=pd.Timestamp("2026-09-30")-pd.DateOffset(years=int(years))) &
                          (source.date<=pd.Timestamp("2026-09-30"))]
            self.assertAlmostEqual(period["p80"],float(sample.erp.quantile(.8)),places=5)
        changed=source.copy();changed.loc[changed.index[-1],"pe"]=5
        changed["erp"]=100/changed.pe-changed.yield10
        latest=m.build_erp_history(changed)
        for years in ("3","5","10"):
            self.assertEqual(history["periods"][years]["p80"],latest["periods"][years]["p80"])
            self.assertEqual(latest["periods"][years]["percentile"],100)

    def test_history_keeps_only_one_monthly_point_and_negative_erp(self):
        source=self.history_source()
        newer=source.iloc[[-1]].copy();newer["date"]=pd.Timestamp("2026-10-29")
        newer["pe"]=40;newer["yield10"]=5;newer["erp"]=-2.5;newer["estimated"]=True
        history=m.build_erp_history(pd.concat([source,newer],ignore_index=True))
        self.assertEqual(history["points"][-1][0],"2026-10-29")
        self.assertEqual(history["latest"],-2.5)
        self.assertTrue(history["estimatedPE"])
        months=[p[0][:7] for p in history["points"]]
        self.assertEqual(len(set(months)),len(months))

    def test_future_yields_and_incomplete_history_are_rejected(self):
        source=self.history_source()
        with self.assertRaises(ValueError):
            m.build_erp_history(source.tail(30))
        source.loc[source.index[-1],"yieldSourceDate"]=pd.Timestamp("2026-10-02")
        with self.assertRaises(ValueError):
            m.build_erp_history(source)

    def test_snapshot_audit_recomputes_selected_window_quantiles(self):
        from audit_snapshot import audit_us_history
        history=m.build_erp_history(self.history_source())
        payload={"history":history,"valuationDate":history["date"],"yieldDate":history["yieldDate"],
                 "estimatedPE":False,"metrics":[[],[],["ERP",f'{history["latest"]:.2f}%']]}
        audit_us_history(payload)
        history["periods"]["3"]["p80"]+=1
        with self.assertRaises(ValueError):audit_us_history(payload)

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
