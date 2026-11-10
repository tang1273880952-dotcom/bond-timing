"""Offline regression tests: data integrity and financial unit conversions."""
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "liquidity", Path(__file__).resolve().parents[1] / "scripts/update_liquidity.py"
)
li = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(li)

class LiquidityTests(unittest.TestCase):
    def test_mirror_csv_and_gap(self):
        raw = "observation_date,SOFR\n2026-10-01,3.95\n2026-10-02,\n2026-10-05,3.94\n"
        self.assertEqual(li.parse_rows(raw, "SOFR"),
                         [{"date":"2026-10-01","value":3.95},
                          {"date":"2026-10-05","value":3.94}])

    def test_cboe_date_formats(self):
        one = "DATE,CLOSE\n10/30/2026,26.15\n11/02/2026,25.45\n"
        self.assertEqual(li.parse_cboe(one)[0],
                         {"date":"2026-10-30","value":26.15})
        other = "DATE,OPEN,HIGH,LOW,CLOSE\n2026-10-30,1,2,1,26.15\n"
        self.assertEqual(li.parse_cboe(other)[0]["date"], "2026-10-30")

    def test_aligned_funding_spread_no_future_fill(self):
        a=[{"date":"2026-10-01","value":3.91},{"date":"2026-10-02","value":3.96}]
        b=[{"date":"2026-10-02","value":3.90}]
        self.assertEqual(li.combine(a,b), [{"date":"2026-10-02","value":0.06}])

    def test_net_liquidity_correct_units(self):
        obj={
          "FED_ASSETS":[{"date":"2026-09-30","value":7000000}],
          "TGA":[{"date":"2026-09-30","value":1000000}],
          "RRP":[{"date":"2026-09-29","value":200}]
        }
        self.assertEqual(li.net_liquidity(obj),
                         [{"date":"2026-09-30","value":5800.0}])
        obj["RRP"]=[{"date":"2026-09-01","value":200}]
        self.assertEqual(li.net_liquidity(obj), [])

    def test_validates_ranges_and_dates(self):
        # One bad value and one future observation are rejected; need >=25 good samples.
        values=[{"date":f"2026-10-{i:02d}","value":3.9} for i in range(1,29)]
        values += [{"date":"2026-10-29","value":99999},{"date":"2099-01-01","value":3.9}]
        result=li.validate("SOFR",values)
        self.assertEqual(len(result), 28)
        self.assertEqual(result[-1]["date"],"2026-10-28")

if __name__=="__main__":
    unittest.main()
