import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from merge_a_share_quick import merge
class MergeTests(unittest.TestCase):
    def test_financial_not_reintroduced(self):
        x=merge({},{"generatedAt":"2026-10-29T19:00:00+08:00","coverage":{"universe":2,"fullSnapshot":True},"quotes":{
          "601318":{"name":"中国平安","date":"2026-10-29","pe":7,"pb":.9},
          "603345":{"name":"安井食品","date":"2026-10-29","pe":17,"pb":1.6}}})
        self.assertEqual(x["quotes"]["601318"]["stage"],"金融行业待独立估值")
        self.assertEqual(x["quotes"]["603345"]["stage"],"待财报复核")
        self.assertEqual(x["coverage"]["preselected"],1)
        self.assertTrue(x["coverage"]["fullSnapshot"])
    def test_accumulated_old_not_full_snapshot(self):
        x=merge({"coverage":{"universe":3,"fullSnapshot":True},"quotes":{
          "603345":{"name":"安井食品","date":"2026-10-19","pe":17,"pb":1.6},
          "000651":{"name":"格力电器","date":"2026-10-19","pe":10,"pb":1.5}}},
          {"coverage":{"universe":3,"fullSnapshot":False},"quotes":{
          "000333":{"name":"美的集团","date":"2026-10-29","pe":15,"pb":3}}})
        self.assertEqual(x["coverage"]["everQuoted"],3)
        self.assertFalse(x["coverage"]["fullSnapshot"])
if __name__=="__main__":unittest.main()
