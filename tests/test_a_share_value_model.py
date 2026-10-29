import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from a_share_value_model import evaluate,financial,quick_rank
def stock():
    return dict(code="603345",name="安井食品",pe=17,pb=1.7,roe=14,growth=8,
                cfoRatio=1.4,debtRatio=35,roeHistory=[12,13,14],financeModelVersion=2)
def hist():return dict(pbPct=10,samples=200)
def quote():return dict(stage="待财报复核",pe=17,pb=1.7)
class TestValueModel(unittest.TestCase):
    def test_pass(self):
        self.assertTrue(evaluate(stock(),hist(),quote())["eligible"])
    def test_financial(self):
        self.assertTrue(financial("601318","中国平安"))
        self.assertTrue(financial("300059","东方财富"))
        self.assertFalse(financial("603345","安井食品"))
        self.assertFalse(evaluate({**stock(),"code":"601318","name":"中国平安"},hist(),quote())["eligible"])
    def test_out_of_range(self):
        for key,value in [("pb",6.83),("pe",50),("cfoRatio",.3),("growth",-50)]:
            s=stock();s[key]=value
            self.assertFalse(evaluate(s,hist(),quote())["eligible"])
        self.assertFalse(evaluate(stock(),hist(),{"stage":"估值初筛未通过"})["eligible"])
    def test_old_model(self):
        s=stock();s.pop("financeModelVersion")
        self.assertFalse(evaluate(s,hist(),quote())["eligible"])
    def test_invalid_numeric_and_freshness(self):
        x=stock();x["pb"]=float("nan")
        self.assertFalse(evaluate(x,hist(),quote())["eligible"])
        x=stock();x["roeHistory"]=[10,float("inf")]
        self.assertFalse(evaluate(x,hist(),quote())["eligible"])
        dated={**stock(),"date":"2026-10-28","financeUpdated":"2026-10-29","reportDate":"2026-09-30"}
        q={**quote(),"date":"2026-10-29"}
        h={**hist(),"end":"2026-10-28"}
        self.assertTrue(evaluate(dated,h,q,today="2026-10-29")["eligible"])
        self.assertFalse(evaluate(dated,{**h,"end":"2026-10-27"},q,today="2026-10-29")["eligible"])
        self.assertFalse(evaluate({**dated,"date":"2026-10-10"},{**h,"end":"2026-10-10"},q,today="2026-10-29")["eligible"])
        self.assertFalse(evaluate(dated,h,{**q,"date":"2026-10-19"},today="2026-10-29")["eligible"])
    def test_priority(self):
        self.assertGreater(quick_rank({"pe":10,"pb":1}),quick_rank({"pe":40,"pb":5}))
if __name__=="__main__":unittest.main()
