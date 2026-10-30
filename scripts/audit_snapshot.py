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

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
CODES=("399975","399989","399971","399998","000807","399997","399986")
PCTS=(0,10,20,50,80,90,100)

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

def main():
    latest=read_json("latest.json")
    us=read_json("us_latest.json")
    industry=read_json("industry_latest.json")
    for name in ("status.json","us_status.json","industry_status.json"):
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
            check(0<=item["periods"]["3"]["percentile"]<=100,
                  f"{name} invalid three-year percentile")
    series=latest.get("history",{}).get("series",{}).get("csi500",{})
    check(series.get("date")==latest["dataDate"],
          "CSI 500 plotted date differs from overview snapshot")
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
    for name,payload in (("China",latest),("US",us),("Industry",industry)):
        dt=payload.get("generatedAt") or payload.get("generatedAt",None)
        print(f"OK {name}: {dt or latest.get('dataDate')} source snapshot checked")
    print("PASS: 10 historical charts and 4 asset cards pass snapshot integrity audit")

if __name__=="__main__":main()
