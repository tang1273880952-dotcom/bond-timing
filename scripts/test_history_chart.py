"""Regression checks for historical chart generation."""
import unittest
import pandas as pd
from history_chart import build_history,compact_series

class TestHistoryChart(unittest.TestCase):
    def test_latest_and_reference_points(self):
        dates=pd.bdate_range("2014-01-02","2026-10-28")
        f=pd.DataFrame({"date":dates,
           "erp":[1.5+(i%60)/100 for i in range(len(dates))],
           "y10":[2+(i%80)/100 for i in range(len(dates))],
           "y30":[3+(i%70)/100 for i in range(len(dates))]})
        d=build_history(f,f)["series"]
        for k in ("csi500","bond10","bond30"):
            self.assertEqual(d[k]["date"],"2026-10-28")
            self.assertEqual(d[k]["points"][-1][0],"2026-10-28")
            self.assertGreater(len(d[k]["points"]),100)
            self.assertLessEqual(d[k]["p20"],d[k]["p80"])
        self.assertNotEqual(d["bond10"]["latest"],d["bond30"]["latest"])
    def test_insufficient_data(self):
        with self.assertRaises(ValueError):
            compact_series(pd.DataFrame({"date":pd.date_range("2026-01-01",periods=5),"erp":range(5)}),"erp")
if __name__=="__main__":unittest.main()
