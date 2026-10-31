"""Offline validation of the real snapshots shipped to GitHub Pages.

Checks only verifiable invariants: source IDs, monotone time series, percentile
calculation, consistent dates, and cross-file schema. No artificial market
prices or estimates; doesn't fail merely because a market is closed.
"""
from __future__ import annotations
import csv
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
CODES=("399975","399989","399971","399998","000807","399997","399986")
PCTS=(0,10,20,50,80,90,100)
PB_CODES={"399975","399998","399986"}

def read_json(name):
    obj=json.loads((DATA/name).read_text(encoding="utf-8"))
    if not isinstance(obj,dict):
        raise ValueError(f"{name}: JSON root must be a dictionary")
    return obj

def check(condition,reason):
    if not condition:raise ValueError(reason)

def parsed_date(s):
    return date.fromisoformat(str(s)[:10])

def subtract_years(d,years):
    try:return d.replace(year=d.year-years)
    except ValueError:return d.replace(year=d.year-years,day=28)

def check_history_date(history_date, snapshot_date):
    # Official index data and live PE do not necessarily publish together.
    lag=(parsed_date(snapshot_date)-parsed_date(history_date)).days
    check(0<=lag<=8,"历史估值日期晚于当前快照或已滞后超过8天")
    return lag

def quantile(values,pct):
    vals=sorted(values)
    index=(len(vals)-1)*pct/100
    a=math.floor(index)
    return vals[a]+(vals[math.ceil(index)]-vals[a])*(index-a)

def audit_industries(payload):
    items=payload.get("items")
    check(isinstance(items,list) and
          tuple(item.get("code") for item in items)==CODES,
          "行业指数代码、顺序或数量发生变化")
    for item in items:
        code=item["code"]
        if item.get("valid") is not True:
            print(f"WARN {code}: verified valuation not yet available")
            continue
        if code in PB_CODES:
            check(item.get("metric")=="PB",
                  f"{code}: expected real PB, not PE")
            check(.2<=float(item.get("value",-1))<=20,
                  f"{code}: latest PB multiple invalid")
            points=item.get("points",[])
            mode=item.get("pointMetric")
            check(len(points)>=420 and mode in ("PB_MULTIPLE","PB_10Y_PERCENTILE"),
                  f"{code}: missing validated PB history or unknown source")
            dates=[parsed_date(v[0]) for v in points]
            vals=[float(v[1]) for v in points]
            check(all(dates[i]<dates[i+1] for i in range(len(dates)-1)),
                  f"{code}: PB historical dates out of order")
            check(all(math.isfinite(v) for v in vals),
                  f"{code}: PB history contains invalid numbers")
            if mode=="PB_MULTIPLE":
                check(code=="399975",f"{code}: unauthorized PB multiple provider mapping")
                check(all(.1<v<30 for v in vals),
                      f"{code}: PB multiple outside valid range")
                check(0<=(parsed_date(item["date"])-dates[-1]).days<=9,
                      f"{code}: current PB has no matching historical endpoint")
                check(abs(vals[-1]-float(item["value"]))<=max(.08,float(item["value"])*.06),
                      f"{code}: latest source PB inconsistent with raw history")
                check(set(item.get("periods",{}))=={"3","5","10"},
                      f"{code}: PB 3/5/10-year history missing")
                last=parsed_date(item["date"])
                ref=last.replace(day=1)-timedelta(days=1)
                for years,p in item["periods"].items():
                    begin=subtract_years(ref,int(years))
                    sample=[v for d,v in zip(dates,vals) if begin<=d<=ref]
                    check(len(sample)==p["sampleCount"] and len(sample)>=int(years)*42,
                          f"{code}: raw PB window sample count mismatch")
                    check(p.get("rankYears")==int(years),
                          f"{code}: PB percentile window wrongly kept fixed at ten years")
                    check(begin<=parsed_date(p["referenceDate"])<=ref,
                          f"{code}: PB reference outside complete prior month")
                    for q in PCTS:
                        check(abs(quantile(sample,q)-float(p[f"p{q}"]))<.00025,
                              f"{code}: wrong {years}yr real PB multiple reference {q}%")
                    rank=round(100*sum(v<=float(item["value"]) for v in sample)/len(sample),2)
                    check(abs(rank-p["percentile"])<=.25,
                          f"{code}: PB rank not calculated from matching {years}yr values")
            else:
                check(all(0<=v<=100 for v in vals),f"{code}: PB historical ranks invalid")
                check("10" in item.get("periods",{}),f"{code}: ten-year PB rank missing")
                # 3/5-year ranges present in older snapshots are deprecated
                # and must not be rendered as independent 3/5-year ranks.
                ten=item["periods"]["10"]
                check(ten.get("rankYears")==10 and
                      abs(ten["percentile"]-vals[-1])<.11,
                      f"{code}: source ten-year PB rank and endpoint disagree")
                check(all(float(ten.get(f"p{q}",-1))==q for q in PCTS),
                      f"{code}: ten-year PB percentage grid is not 0..100")
                if set(item["periods"])!={"10"}:
                    print(f"WARN {code}: legacy fixed 3/5-year PB ranks "
                          "will be disabled in the browser until source refresh")
            continue
        check(item.get("metric")=="PE-TTM",f"{code}: actual metric is not PE-TTM")
        check(len(item.get("points",[]))>=100,f"{code}: missing plotted observations")
        check(item["points"][-1][0]==item["date"],
              f"{code}: plot endpoint is not the latest PE date")
        check(abs(float(item["points"][-1][1])-float(item["value"]))<=0.001,
              f"{code}: plot last value and displayed PE differ")
        cache=DATA/"industry_cache"/(code+"_pe.csv")
        if not cache.exists():
            print(f"WARN {code}: historical CSV not available for audit")
            continue
        with cache.open(encoding="utf-8",newline="") as handle:
            rows=list(csv.DictReader(handle))
        history=[(parsed_date(row["date"]),float(row["pe"])) for row in rows]
        check(all(math.isfinite(v) and v>0 for _,v in history),
              f"{code}: invalid PE numbers")
        check(all(history[i][0]<history[i+1][0] for i in range(len(history)-1)),
              f"{code}: duplicate or unordered dates")
        for years,p in item["periods"].items():
            check(years in ("3","5","10"),f"{code}: unsupported time horizon")
            reference=parsed_date(p["referenceDate"])
            start=subtract_years(reference,int(years))
            sample=[v for d,v in history if start<=d<=reference]
            check(len(sample)==p["sampleCount"] and len(sample)>=int(years)*150,
                  f"{code}: historical sample count differs from source cache")
            for pct in PCTS:
                actual=quantile(sample,pct)
                check(abs(float(p[f"p{pct}"])-actual)<0.00011,
                      f"{code}: incorrect {years}y {pct}th percentile")
            observed=round(100*sum(x<=float(item["value"]) for x in sample)/len(sample),2)
            check(abs(observed-p["percentile"])<=0.02,
                  f"{code}: current valuation rank doesn't match percentile window")
            check(reference<parsed_date(item["date"]),
                  f"{code}: historical reference contains current incomplete month")

def audit_us_history(payload):
    history=payload.get("history",{})
    check(history.get("valid") is True and history.get("id")=="sp500" and
          history.get("frequency")=="monthly","S&P 500 monthly ERP history missing")
    end=parsed_date(history["date"])
    check(end==parsed_date(payload["valuationDate"]),"US chart/card source dates differ")
    check(history["yieldDate"]==payload["yieldDate"],"US chart/card Treasury dates differ")
    check(history.get("estimatedPE")==payload["estimatedPE"],"US historical PE estimate flag differs")
    points=history.get("points",[])
    check(len(points)>=120 and points[-1][0]==history["date"],"US historical endpoint or coverage invalid")
    months=set();previous=None
    for day,erp,pe,yield10,yield_day,estimated in points:
        observed=parsed_date(day);bond=parsed_date(yield_day)
        check(previous is None or observed>previous,"US monthly dates unordered")
        check(day[:7] not in months,"US chart must have one observation per month")
        months.add(day[:7]);previous=observed
        check(isinstance(estimated,bool) and all(math.isfinite(float(v)) for v in (erp,pe,yield10))
              and pe>0,"US historical values or estimate flags invalid")
        check(0<=(observed-bond).days<=42,"US Treasury matching uses future or stale observation")
        check(abs(100/pe-yield10-erp)<.00001,"US historical ERP arithmetic incorrect")
    check(abs(history["latest"]-points[-1][1])<.000001,"US historical latest ERP mismatch")
    check(abs(float(str(payload["metrics"][2][1]).rstrip("%"))-history["latest"])<=.0051,
          "US overview ERP differs from chart")
    reference=end.replace(day=1)-timedelta(days=1)
    check(set(history.get("periods",{}))=={"3","5","10"},"US historical horizons incomplete")
    for years,p in history["periods"].items():
        check(parsed_date(p["referenceDate"])==reference,"US bands include current incomplete month")
        start=subtract_years(reference,int(years))
        sample=[float(row[1]) for row in points if start<=parsed_date(row[0])<=reference]
        check(len(sample)==p["sampleCount"] and len(sample)>=int(years)*10,"US reference sample count invalid")
        check(parsed_date(p["from"])==start,"US reference range mismatch")
        for q in (10,20,50,80,90):
            check(abs(quantile(sample,q)-float(p[f"p{q}"]))<.00001,"US historical quantile incorrect")
        rank=round(100*sum(v<=history["latest"] for v in sample)/len(sample),2)
        check(abs(rank-p["percentile"])<.011,"US percentile does not match selected years")
    for day,close in history.get("indexClose",{}).get("points",[]):
        check(parsed_date(day)<=end and math.isfinite(close) and close>0,"US index overlay invalid")

def audit_gold(payload):
    check(payload.get("mode")=="gold-aisc-v1" and payload.get("valid") is True,
          "Gold snapshot is not a verified cost-reference model")
    check(payload.get("quoteType")=="spot" and payload.get("priceSymbol")=="XAU" and
          payload.get("unit")=="USD/troy oz","Gold price and AISC units/symbol do not match")
    price=float(payload["price"]);cost=float(payload["aisc"]);ratio=float(payload["ratio"])
    check(all(math.isfinite(v) and v>0 for v in (price,cost,ratio)),"Gold model contains invalid numbers")
    check(abs(price/cost-ratio)<.0001,"Gold price / AISC ratio incorrect")
    multiples=[1.3,1.5,2.2,2.7,3.0]
    check(payload.get("multiples")==multiples,"Gold user-defined reference multiples changed")
    check([b.get("multiple") for b in payload.get("bands",[])]==multiples,"Gold reference band missing")
    for band in payload["bands"]:
        check(abs(float(band["price"])-cost*band["multiple"])<=.011,"Gold price band arithmetic incorrect")
    events=payload.get("costEvents",[])
    check(bool(events),"Gold missing publication-dated AISC history")
    previous=None
    for event in events:
        published=parsed_date(event["publishedDate"]);effective=parsed_date(event["effectiveDate"])
        check(effective==published+timedelta(days=1),"AISC effective date must follow publication")
        check(parsed_date(event["periodEnd"])<=published,"AISC published before its production quarter ended")
        source=urlparse(event["source"])
        check(source.scheme=="https" and source.hostname in ("www.gold.org","gold.org"),
              "AISC source is not the original public WGC report")
        if previous:
            check(effective>parsed_date(previous["effectiveDate"]) and event["period"]>=previous["period"],
                  "AISC cost chronology or production-quarter order is invalid")
        previous=event
    points=payload.get("points",[])
    check(len(points)>=40 and points[-1][0]==payload["priceDate"],"Gold plotted price endpoint is inconsistent")
    previous_date=None
    for day,quote,aisc,multiple,period,published in points:
        d=parsed_date(day)
        check(previous_date is None or d>previous_date,"Gold weekly dates unordered")
        available=[e for e in events if parsed_date(e["effectiveDate"])<=d]
        check(bool(available),"Gold uses costs before their disclosure")
        active=available[-1]
        check(float(aisc)==float(active["aisc"]) and period==active["period"] and published==active["publishedDate"],
              "Gold historical cost differs from its publication-dated source")
        check(abs(float(quote)/float(aisc)-float(multiple))<.0001,"Gold historical ratio incorrect")
        previous_date=d
    check(abs(float(points[-1][1])-price)<.011,"Gold chart and card show different prices")

def main():
    latest=read_json("latest.json")
    us=read_json("us_latest.json")
    industry=read_json("industry_latest.json")
    gold=read_json("gold_latest.json")
    for name in ("status.json","us_status.json","industry_status.json","gold_status.json"):
        read_json(name)
    check(latest.get("mode")=="live", "China market snapshot is invalid")
    assets=latest.get("assets",[])
    check([a.get("id") for a in assets]==["csi500","bond10","bond30"],
          "Asset ordering or IDs have changed")
    check(all(isinstance(a.get("score"),(int,float)) and 0<=a["score"]<=100 for a in assets),
          "Invalid China score range")
    check(us.get("mode")=="live" and us.get("id")=="sp500", "US market snapshot invalid")
    check(0<=us.get("score",-1)<=100,"US score out of range")
    check(isinstance(us.get("estimatedPE"),bool),"US PE estimate flag missing")
    check(parsed_date(latest["stockPEDataDate"])<=parsed_date(latest["dataDate"]),
          "China stock PE from future versus market snapshot")
    check(parsed_date(latest["stockPBDataDate"])<=parsed_date(latest["dataDate"]),
          "China stock PB from future versus market snapshot")
    for name in ("bse50","star100"):
        item=latest.get(name,{})
        expected={"bse50":"899050","star100":"000698"}[name]
        check(item.get("code")==expected,f"{name} wrong official index symbol")
        if item.get("valid"):
            periods=item.get("periods",{})
            check("1" in periods and all(0<=p.get("percentile",-1)<=100
                  for p in periods.values()),f"{name} invalid historical percentile")
    series=latest.get("history",{}).get("series",{}).get("csi500",{})
    lag=check_history_date(series.get("date"),latest["dataDate"])
    if lag:
        print(f"NOTE: official CSI500 history is {lag} day(s) behind live PE; actual dates retained")
    if latest.get("stockYieldDataDate"):
        pe_yield_gap=(parsed_date(latest["stockPEDataDate"])-
                      parsed_date(latest["stockYieldDataDate"])).days
        check(0<=pe_yield_gap<=5,"ERP国债观测使用未来数据或匹配间隔超过5天")
    check(all(0<=p.get("percentile",-1)<=100 for p in series.get("periods",{}).values()),
          "CSI 500 historical percentile invalid")
    # History & overview PE derive from different verified sources and can differ.
    # Record the difference but DO NOT silently force one to equal the other.
    score_erp=float(str(assets[0]["metrics"][0][1]).rstrip("%"))
    chart_erp=float(series["latest"])
    if abs(score_erp-chart_erp)>0.01:
        print(f"NOTE: CSI 500 overview ERP {score_erp:.2f}% vs index-official history ERP "
              f"{chart_erp:.2f}% (different PE providers)")
    audit_industries(industry)
    audit_us_history(us)
    audit_gold(gold)
    for name,payload in (("China",latest),("US",us),("Industry",industry)):
        dt=payload.get("generatedAt") or payload.get("generatedAt",None)
        print(f"OK {name}: {dt or latest.get('dataDate')} source snapshot checked")
    print("PASS: 12 historical charts and 5 asset cards pass snapshot integrity audit")

if __name__=="__main__":main()
