"""Regression: live monthly observations must survive asynchronous source dates."""
import unittest
import pandas as pd
from update import align_stock_valuations


def data(dates, column, values):
    return pd.DataFrame({"date": pd.to_datetime(dates).astype("datetime64[ns]"),
                         column: values})


class SourceAlignmentTests(unittest.TestCase):
    def test_live_pe_is_not_replaced_by_last_month_when_bond_lags(self):
        pe=data(["2026-09-30", "2026-10-30"], "pe", [25., 22.])
        pb=data(["2026-09-30", "2026-10-30"], "pb", [2.2, 2.])
        yields=data(["2026-09-30", "2026-10-29"], "y10", [1.8, 1.6])
        matched, valid_pb=align_stock_valuations(pe,pb,yields,"2026-10-30")
        self.assertEqual(matched.date.iloc[-1],pd.Timestamp("2026-10-30"))
        self.assertEqual(matched.pe.iloc[-1],22.)
        self.assertEqual(matched.yieldDate.iloc[-1],pd.Timestamp("2026-10-29"))
        self.assertEqual(valid_pb.pb.iloc[-1],2.)

    def test_yields_and_stock_observations_never_look_into_future(self):
        pe=data(["2026-10-29", "2026-10-31"], "pe", [22., 5.])
        pb=data(["2026-10-29", "2026-10-31"], "pb", [2., .5])
        yields=data(["2026-10-28", "2026-10-30", "2026-10-31"],
                    "y10", [1.6, 9., 10.])
        matched, valid_pb=align_stock_valuations(pe,pb,yields,"2026-10-30")
        self.assertEqual(matched.pe.iloc[-1],22.)
        self.assertEqual(matched.y10.iloc[-1],1.6)
        self.assertEqual(valid_pb.pb.iloc[-1],2.)

    def test_missing_nearby_yield_and_stale_pb_are_rejected(self):
        pe=data(["2026-10-30"], "pe", [22.])
        pb=data(["2026-10-30"], "pb", [2.])
        yields=data(["2026-10-20"], "y10", [1.6])
        with self.assertRaises(ValueError):
            align_stock_valuations(pe,pb,yields,"2026-10-30")
        yields=data(["2026-10-30"], "y10", [1.6])
        with self.assertRaises(ValueError):
            align_stock_valuations(pe,data(["2026-08-31"],"pb",[2.]),
                                   yields,"2026-10-30")


if __name__=="__main__":unittest.main()
