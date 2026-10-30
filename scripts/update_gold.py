"""London spot gold and public, publication-dated global AISC reference bands.

The complete Metals Focus cost database is not a free public API. This module
uses only openly readable World Gold Council reports, retains their vintages,
and never backdates a newly published mining cost to the production quarter.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import json
import math
import re
import traceback

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"
TZ=ZoneInfo("Asia/Shanghai")
MULTIPLES=(1.3,1.5,2.2,2.7,3.0)
PRICE_SOURCE="新浪财经 · 伦敦金现货 XAU（日线，美元/盎司）"
PRICE_URL="https://finance.sina.com.cn/futures/quotes/XAU.shtml"
WGC="https://www.gold.org/goldhub/research/gold-demand-trends/"
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; BondTimingResearch/1.0)",
         "Accept":"text/html,application/json,*/*"}
DATE_RE=r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+20\d{2}\b"
METRIC_RE=re.compile(r"\bAISC\b|all[\s-]*in[\s-]*sustaining[\s-]*costs?",re.I)
MONEY_RE=re.compile(r"US\s*\$\s*([\d,]+(?:\.\d+)?)\s*(?:/\s*oz|per\s+(?:troy\s+)?ounce)",re.I)


def report_url(year,quarter):
    name=f"gold-demand-trends-full-year-{year}" if quarter==4 else f"gold-demand-trends-q{quarter}-{year}"
    return WGC+name+"/supply"


def publication_date(soup):
    main=soup.find("main") or soup
    time=main.find("time",attrs={"datetime":True})
    if time:
        return str(pd.Timestamp(time["datetime"]).date())
    match=re.search(DATE_RE,main.get_text(" ",strip=True))
    if not match:
        raise ValueError("Public report has no verifiable publication date")
    return str(pd.to_datetime(match.group(0),format="mixed").date())


def parse_report(html,year,quarter,url,today):
    """Extract the preceding quarter's industry AISC, excluding annual averages."""
    soup=BeautifulSoup(html,"html.parser")
    published=publication_date(soup)
    if pd.Timestamp(published)>pd.Timestamp(today):
        raise ValueError("Report publication is dated in the future")
    cost_year=year if quarter>1 else year-1
    cost_quarter=quarter-1 if quarter>1 else 4
    candidates=[]
    main=soup.find("main") or soup
    for paragraph in main.find_all("p"):
        text=paragraph.get_text(" ",strip=True)
        if not METRIC_RE.search(text):
            continue
        if not re.search(r"global|industry|average",text,re.I):
            continue
        # A paragraph can contain BOTH annual AISC and quarterly AISC. Resolve
        # the sentence mentioning the target quarter before reading its number.
        sentences=re.split(r"(?<=[.!?])\s+",text)
        for sentence in sentences:
            if not METRIC_RE.search(sentence):
                continue
            metric=METRIC_RE.search(sentence)
            numbers=MONEY_RE.findall(sentence[metric.start():])
            if not numbers:
                continue
            mentions=re.findall(r"\bQ([1-4])(?:\s*[’'`]\s*(\d{2,4}))?\b",sentence,re.I)
            explicit=any(int(q)==cost_quarter and (not y or int(y)%100==cost_year%100)
                         for q,y in mentions)
            if mentions and not explicit:
                continue
            if not mentions and re.search(r"\b(?:annual|annually|in\s+20\d{2})\b",sentence,re.I):
                continue
            value=float(numbers[0].replace(",",""))
            if 400<=value<=5000:
                candidates.append((2 if explicit else 1,value))
    if not candidates:
        raise ValueError("No unambiguous public quarterly industry AISC found")
    priority=max(p for p,v in candidates)
    values={v for p,v in candidates if p==priority}
    if len(values)!=1:
        raise ValueError("Public report contains conflicting quarterly AISC values")
    return make_cost(f"{cost_year}Q{cost_quarter}",values.pop(),published,url)


def make_cost(period,value,published,source):
    if not re.fullmatch(r"20\d{2}Q[1-4]",str(period)):
        raise ValueError("Invalid AISC production quarter")
    end=pd.Period(period,freq="Q").end_time.normalize()
    pub=pd.Timestamp(published).normalize()
    if pub<end or not math.isfinite(float(value)) or not 400<=float(value)<=5000:
        raise ValueError("Invalid AISC cost or disclosure timing")
    if urlparse(source).scheme!="https" or urlparse(source).hostname not in ("www.gold.org","gold.org"):
        raise ValueError("AISC observations must cite the original WGC report")
    return {"period":str(period),"periodEnd":str(end.date()),"aisc":float(value),
        "publishedDate":str(pub.date()),"effectiveDate":str((pub+pd.Timedelta(days=1)).date()),
        "source":source,"unit":"USD/troy oz","scope":"global industry average"}


def normalize_costs(records,today):
    cleaned={}
    vintages={}
    for row in records:
        item=make_cost(row["period"],row["aisc"],row["publishedDate"],row["source"])
        if pd.Timestamp(item["publishedDate"])<=pd.Timestamp(today):
            key=(item["period"],item["publishedDate"])
            if key in vintages and vintages[key]!=item["aisc"]:
                raise ValueError("Conflicting AISC values for the same public vintage")
            vintages[key]=item["aisc"]
            cleaned[(item["period"],item["publishedDate"],item["source"])]=item
    return sorted(cleaned.values(),key=lambda r:(r["effectiveDate"],r["period"],r["source"]))


def active_cost_events(records,today):
    """Newer disclosures of OLD quarters never replace a newer known quarter."""
    events=[]
    for item in normalize_costs(records,today):
        if pd.Timestamp(item["effectiveDate"])>pd.Timestamp(today):
            continue
        previous=events[-1] if events else None
        if previous and item["period"]<previous["period"]:
            continue
        if previous and item["period"]==previous["period"] and item["aisc"]==previous["aisc"]:
            continue
        if previous and item["effectiveDate"]==previous["effectiveDate"]:
            events[-1]=item
        else:
            events.append(item)
    if not events:
        raise ValueError("No disclosed AISC observations available at this date")
    return events


def fetch_report(year,quarter,today):
    url=report_url(year,quarter)
    response=requests.get(url,headers=HEADERS,timeout=18)
    response.raise_for_status()
    return parse_report(response.text,year,quarter,url,today)


def refresh_public_costs(records,today):
    # Four recent PUBLIC report pages, never the sign-in-only chart/database.
    completed=pd.Period(pd.Timestamp(today),freq="Q")-1
    plans=[(p.year,p.quarter) for p in (completed-i for i in range(4))]
    new=[];warnings=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[(y,q,pool.submit(fetch_report,y,q,today)) for y,q in plans]
        for year,quarter,future in futures:
            try:new.append(future.result())
            except Exception as exc:warnings.append(f"{year}Q{quarter}: {str(exc)[:150]}")
    result=normalize_costs([*records,*new],today)
    if not result:
        raise ValueError("Public AISC source and verified history both unavailable")
    return result,{"success":bool(new),"warnings":warnings}


def fetch_prices(today,api=None):
    # Sina XAU is London SPOT gold, not the COMEX GC futures contract.
    frame=(api or ak.futures_foreign_hist)(symbol="XAU")
    if not isinstance(frame,pd.DataFrame) or not {"date","close"}.issubset(frame.columns):
        raise ValueError("London XAU source missing date or price")
    data=frame[["date","close"]].copy()
    data["date"]=pd.to_datetime(data.date,errors="coerce").astype("datetime64[ns]").dt.normalize()
    data["close"]=pd.to_numeric(data.close,errors="coerce")
    data=data.dropna().sort_values("date").drop_duplicates("date",keep="last")
    data=data[data.close.map(math.isfinite)&data.close.between(100,50000)]
    data=data[data.date<=pd.Timestamp(today)]
    if len(data)<750 or (pd.Timestamp(today)-data.date.iloc[-1]).days>8:
        raise ValueError("London spot gold history is insufficient or outdated")
    return data.reset_index(drop=True)


def cost_zone(ratio):
    for limit,label,tone in ((1.3,"接近成本区","cheap"),(1.5,"较低成本溢价","cheap"),
        (2.2,"中等成本溢价","neutral"),(2.7,"较高成本溢价","caution"),
        (3.0,"高成本溢价","rich")):
        if ratio<limit:return {"label":label,"tone":tone}
    return {"label":"很高成本溢价","tone":"rich"}


def build_payload(prices,records,today):
    events=active_cost_events(records,today)
    cost=pd.DataFrame(events).rename(columns={"effectiveDate":"costEffectiveDate"})
    cost["costEffectiveDate"]=pd.to_datetime(cost.costEffectiveDate).astype("datetime64[ns]")
    merged=pd.merge_asof(prices.sort_values("date"),cost.sort_values("costEffectiveDate"),
        left_on="date",right_on="costEffectiveDate",direction="backward")
    merged=merged.dropna(subset=["aisc"]).copy()
    if len(merged)<250:raise ValueError("Not enough gold history after the first public cost disclosure")
    merged["ratio"]=merged.close/merged.aisc
    last=merged.iloc[-1]
    sampled=merged.groupby(merged.date.dt.to_period("W-SUN")).tail(1)
    current_cost=next(x for x in reversed(events) if pd.Timestamp(x["effectiveDate"])<=last.date)
    age=(pd.Timestamp(today)-pd.Timestamp(current_cost["periodEnd"])).days
    return {"mode":"gold-aisc-v1","id":"gold","name":"黄金","valid":True,
        "priceDate":str(last.date.date()),"price":round(float(last.close),2),
        "priceSource":PRICE_SOURCE,"priceSourceUrl":PRICE_URL,"priceSymbol":"XAU",
        "quoteType":"spot","unit":"USD/troy oz","frequency":"weekly",
        "aisc":round(float(last.aisc),2),"costPeriod":str(last.period),
        "costPublishedDate":str(last.publishedDate),"costEffectiveDate":str(last.costEffectiveDate.date()),
        "costSource":str(last.source),"costAgeDays":age,"costStale":age>365,
        "ratio":round(float(last.ratio),6),"classification":cost_zone(float(last.ratio)),
        "multiples":list(MULTIPLES),"bands":[{"multiple":m,"price":round(m*float(last.aisc),2)} for m in MULTIPLES],
        "historyStartDate":str(merged.date.iloc[0].date()),
        "points":[[str(r.date.date()),round(float(r.close),2),round(float(r.aisc),2),
                   round(float(r.ratio),6),str(r.period),str(r.publishedDate)]
                  for r in sampled.itertuples(index=False)],
        "costEvents":[x for x in events if pd.Timestamp(x["effectiveDate"])<=last.date],
        "method":"五档倍数为用户自设成本参考，并非历史分位或公允价格。全球季度平均AISC在公开报告公布次日生效；期间沿用上次已知成本，不插值、不回填到生产季度。公开报告样本可能缺少更早披露，不适合当作完整市场信息回测。",
        "limitations":"AISC是存量矿山维持经营成本，不是黄金价格底线，也不是黄金内在价值；金价还受实际利率、汇率、央行与投资需求影响。",
        "generatedAt":datetime.now(TZ).isoformat()}


def write_json(path,data):
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def main():
    OUT.mkdir(exist_ok=True)
    now=datetime.now(TZ);today=now.date()
    status={"attemptAt":now.isoformat(),"success":False}
    try:
        registry=OUT/"gold_aisc_public.json"
        records=json.loads(registry.read_text(encoding="utf-8"))["records"]
        records,cost_check=refresh_public_costs(records,today)
        prices=fetch_prices(today)
        result=build_payload(prices,records,today)
        write_json(OUT/"gold_latest.json",result)
        write_json(registry,{"scope":"WGC public report vintages; not complete licensed database","records":records})
        prices[prices.date>=pd.Timestamp(result["historyStartDate"])].to_csv(OUT/"gold_price_daily.csv",index=False,float_format="%.4f")
        status.update(success=True,dataDate=result["priceDate"],costPeriod=result["costPeriod"],
            costCheckSuccess=cost_check["success"],costWarnings=cost_check["warnings"])
        print("Gold verified",result["priceDate"],result["price"],result["costPeriod"],result["aisc"],result["ratio"],flush=True)
    except Exception as exc:
        traceback.print_exc();status["error"]=str(exc)
        print("Gold source failed; retained last real snapshot",flush=True)
    write_json(OUT/"gold_status.json",status)


if __name__=="__main__":main()
