"""A-share value/quality screening v2: conservative, non-financial companies only."""
import hashlib
import math
from datetime import date
MODEL_VERSION=2
PE_LIMIT=35
PB_LIMIT=4.5
PB_PCT_LIMIT=35
FINANCE_CODES=set("""000001 000166 000686 000728 000776 000783 002142 002500 002673 002736 002797 002926 002939 300059 600000 600015 600016 600030 600036 600061 600109 600369 600837 600908 600919 600926 600958 600999 601009 601066 601077 601099 601128 601162 601166 601169 601198 601211 601229 601236 601288 601318 601319 601328 601336 601375 601377 601398 601456 601555 601577 601601 601628 601658 601665 601688 601696 601788 601818 601825 601838 601860 601878 601881 601901 601916 601939 601988 601990 601995 601998""".split())
FINANCE_WORDS=("银行","证券","保险","信托","期货","金融控股","金融集团","财险","人寿","资产管理","农商行")
def financial(code,name="",industry=""):
    name=str(name or "");industry=str(industry or "")
    return (str(code) in FINANCE_CODES or any(w in name for w in FINANCE_WORDS)
            or any(w in industry for w in ("银行","证券","保险","信托","金融","券商","资本市场")))
def clamp(x):
    return max(0,min(100,float(x)))
def quick_pass(q):
    if not isinstance(q,dict) or q.get("stage")!="待财报复核":return False
    try:
        return 0<float(q["pe"])<=45 and 0.15<=float(q["pb"])<=6
    except (KeyError,TypeError,ValueError):
        return False
def quick_rank(q):
    try:
        pe,pb=float(q["pe"]),float(q["pb"])
        return .6*clamp((6-pb)/6*100)+.4*clamp((45-pe)/45*100)
    except (KeyError,TypeError,ValueError):
        return -1
def rotation_key(code):
    return hashlib.sha256(("ashare-rotate-v2:"+str(code)).encode()).hexdigest()
def evaluate(s,h,q,today=None):
    r=dict(modelVersion=MODEL_VERSION,eligible=False,score=None,
           qualityScore=None,valuationScore=None,growthScore=None,riskScore=None,
           flag=None,action="数据不足 · 待核验",reasons=[])
    def reject(reason):
        r.update(flag=reason,action="暂不进入精选",reasons=[reason])
        return r
    if "ST" in str(s.get("name","")).upper() or s.get("isST"):
        return reject("ST或风险警示股")
    if financial(s.get("code"),s.get("name"),s.get("industry")):
        return reject("金融行业需独立估值模型")
    if not quick_pass(q):
        return reject("最新快速初筛不通过或缺少新鲜行情")
    if today is not None:
        try:
            current=today if isinstance(today,date) else date.fromisoformat(str(today))
            qday=date.fromisoformat(str(q["date"]))
            stock_day=date.fromisoformat(str(s["date"]))
            band_day=date.fromisoformat(str(h["end"]))
            finance_day=date.fromisoformat(str(s["financeUpdated"]))
            report_day=date.fromisoformat(str(s["reportDate"]))
        except (ValueError,KeyError,TypeError,AttributeError):
            return reject("关键行情、财报或PB历史日期缺失")
        if qday>current or stock_day>current or band_day>current:
            return reject("行情或PB历史日期异常")
        if (current-qday).days>7 or (current-stock_day).days>7:
            return reject("行情数据已超过7天，暂停评分")
        if band_day!=stock_day:
            return reject("PB历史与股票行情日期不一致，需重新计算估值")
        if (current-finance_day).days>35 or (current-report_day).days>240:
            return reject("财报复核或最新报告期已过期")
    if s.get("financeModelVersion")!=MODEL_VERSION:
        return reject("等待新版多年财报核验")
    if not h or h.get("samples",0)<120:
        return reject("历史PB样本不足")
    try:
        pe,pb,roe,growth,cfo,debt=[float(s[k]) for k in ("pe","pb","roe","growth","cfoRatio","debtRatio")]
        pct=float(h["pbPct"])
        roes=[float(v) for v in s.get("roeHistory",[]) if v is not None]
    except (KeyError,ValueError,TypeError):
        return reject("缺少关键估值或财务指标")
    if any(not math.isfinite(x) for x in (pe,pb,roe,growth,cfo,debt,pct,*roes)):
        return reject("估值或财务数据存在非有限数字")
    if len(roes)<2:return reject("至少需要2个已披露年度ROE")
    if not 0<pe<=35 or not 0<pb<=4.5:
        return reject("PE或PB超过低估值策略上限")
    if not 0<=pct<=35:return reject("历史PB分位不够低")
    if roe<8 or min(roes)<5:return reject("ROE不足或多年稳定性差")
    if cfo<.8:return reject("经营现金流对净利润覆盖不足")
    if growth< -25:return reject("净利润同比明显恶化")
    if debt<0 or debt>75:return reject("资产负债率过高或异常")
    stability=clamp(100-(max(roes)-min(roes))*7)
    v=clamp(.55*(100-pct)+.25*clamp((35-pe)/35*100)+.20*clamp((4.5-pb)/4.5*100))
    quality=clamp(.5*clamp(roe*5)+.3*clamp(cfo*65)+.2*stability)
    g=clamp((min(growth,45)+20)*100/65)
    risk=clamp(100-max(0,debt-45)*1.8)
    score=round(.35*v+.35*quality+.15*g+.15*risk)
    r.update(eligible=True,score=score,valuationScore=round(v),
             qualityScore=round(quality),growthScore=round(g),riskScore=round(risk),
             action="估值低位 · 重点研究" if pct<=20 and score>=70 else "符合条件 · 继续观察",
             reasons=["满足当前硬性指标，仍需人工判断行业与盈利可持续性",
                      "历史低PB不等于未来股价必然回归"])
    return r
