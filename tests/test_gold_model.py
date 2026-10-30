"""AISC is a public quarterly cost vintage, not a backdated gold fair value."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import update_gold as gold
from audit_snapshot import audit_gold

SOURCE="https://www.gold.org/goldhub/research/example-public-report"


class GoldCostTests(unittest.TestCase):
    def setUp(self):
        self.old=gold.make_cost("2019Q4",1000,"2020-01-31",SOURCE)
        self.new=gold.make_cost("2020Q1",1200,"2020-04-30",SOURCE)
        dates=pd.bdate_range("2020-01-01","2022-01-31").astype("datetime64[ns]")
        self.prices=pd.DataFrame({"date":dates,"close":1800.})

    def test_report_uses_quarterly_number_instead_of_annual_average(self):
        html='<main><time datetime="2023-05-05T12:00:00Z"></time><p>'\
             'In 2022, industry average AISC was US$1,276/oz. '\
             'In Q4’22, global average AISC reached US$1,279/oz.</p></main>'
        row=gold.parse_report(html,2023,1,SOURCE,"2023-05-05")
        self.assertEqual(row["aisc"],1279)
        self.assertEqual(row["period"],"2022Q4")
        self.assertEqual(row["effectiveDate"],"2023-05-06")
        with self.assertRaises(ValueError):
            gold.parse_report(html,2023,1,SOURCE,"2023-05-04")

    def test_production_quarter_is_never_used_before_disclosure(self):
        result=gold.build_payload(self.prices,[self.old,self.new],"2022-01-31")
        for day,price,cost,ratio,period,published in result["points"]:
            self.assertGreater(pd.Timestamp(day),pd.Timestamp(published))
            self.assertEqual(cost,1000 if day<"2020-05-01" else 1200)
        self.assertEqual(result["aisc"],1200)
        self.assertEqual(result["ratio"],1.5)
        self.assertGreaterEqual(result["historyStartDate"],"2020-02-01")
        audit_gold(result)

    def test_later_revision_of_old_quarter_never_replaces_new_quarter(self):
        old_revision=gold.make_cost("2019Q4",1050,"2020-06-01",SOURCE)
        events=gold.active_cost_events([self.old,self.new,old_revision],"2022-01-31")
        self.assertEqual(events[-1]["period"],"2020Q1")
        self.assertEqual(events[-1]["aisc"],1200)

    def test_five_reference_bands_equal_cost_times_user_multiple(self):
        result=gold.build_payload(self.prices,[self.old,self.new],"2022-01-31")
        self.assertEqual(result["multiples"],[1.3,1.5,2.2,2.7,3.0])
        for band in result["bands"]:
            self.assertAlmostEqual(band["price"],result["aisc"]*band["multiple"],places=2)
        result["bands"][0]["price"]+=100
        with self.assertRaises(ValueError):audit_gold(result)

    def test_no_cost_before_first_publication_and_no_future_data(self):
        with self.assertRaises(ValueError):
            gold.active_cost_events([self.old],"2020-01-31")
        future=gold.make_cost("2022Q1",1500,"2022-05-01",SOURCE)
        self.assertEqual(gold.active_cost_events([self.old,self.new,future],"2022-01-31")[-1]["aisc"],1200)
        with self.assertRaises(ValueError):
            gold.make_cost("2020Q1",1000,"2020-01-01",SOURCE)

    def test_conflicting_vintage_or_unverifiable_source_rejected(self):
        with self.assertRaises(ValueError):
            gold.normalize_costs([self.old,{**self.old,"aisc":900}],"2022-01-31")
        with self.assertRaises(ValueError):
            gold.make_cost("2020Q1",1200,"2020-04-30","javascript://www.gold.org/x")

    def test_price_symbol_is_london_xau_and_future_quotes_are_ignored(self):
        dates=pd.bdate_range("2018-01-01","2022-01-31")
        source=pd.DataFrame({"date":dates,"close":1800.})
        calls=[]
        def api(**kwargs):calls.append(kwargs);return source
        result=gold.fetch_prices("2021-12-31",api=api)
        self.assertEqual(calls,[{"symbol":"XAU"}])
        self.assertLessEqual(result.date.max(),pd.Timestamp("2021-12-31"))

    def test_reference_classification_has_no_historical_percentile(self):
        self.assertEqual(gold.cost_zone(1.2)["tone"],"cheap")
        self.assertEqual(gold.cost_zone(2.0)["tone"],"neutral")
        self.assertEqual(gold.cost_zone(3.1)["tone"],"rich")


if __name__=="__main__":unittest.main()
