"""Fetch authentic CSI industry index PE-TTM history, never price-derived valuation.

CSI index-perf records include an independently reported rolling P/E (row[15]).
We deliberately do not substitute index closing price for valuation or fabricate
PB, and we preserve the last verified observations on provider outage.
"""
from __future__ import annotations
import json
import traceback
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"
CACHE=OUT/"industry_cache"
ENDPOINT="https://www.csindex.com.cn/csindex-home/perf/index-perf"
SYMBOLS=[
    ("399975","证券公司","PB"),
    ("399989","中证医疗","PE-TTM"),
    ("399971","中证传媒","PE-TTM"),
    ("399998","中证煤炭","PB"),
    ("000807","食品饮料","PE-TTM"),
    ("399997","中证白酒","PE-TTM"),
    ("399986","中证银行","PB"),
]
MIN_DAYS_PER_YEAR=150
PERCENTILES=(10,20,50,80,90)

def normalize(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date","pe"])
    data=frame.copy()
    data["date"]=pd.to_datetime(data["date"],errors="coerce").dt.normalize()
    data["pe"]=pd.to_numeric(data["pe"],errors="coerce")
    data=data.dropna(subset=["date","pe"])
    data=data[data.pe.between(0.1,1000,inclusive="both")]
    return data.sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)

def parse_csi_payload(payload, symbol):
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        raise ValueError("CSI index-perf response missing data array")
    records=[]
    for row in payload["data"]:
        # Official CSI / AKShare schema: date, code, names, prices, ...,
        # constituents, rolling PE; closing price index 9 MUST NOT be used.
        if not isinstance(row,(list,tuple)) or len(row)<16:
            continue
        if str(row[1]).strip()!=symbol:
            continue
        records.append({"date":row[0],"pe":row[15]})
    return normalize(pd.DataFrame(records,columns=["date","pe"]))

def fetch_official(symbol,start,end,session=None):
    sess=session or requests.Session()
    params={"indexCode":symbol,
            "startDate":pd.Timestamp(start).strftime("%Y%m%d"),
            "endDate":pd.Timestamp(end).strftime("%Y%m%d")}
    r=sess.get(ENDPOINT,params=params,headers={
        "User-Agent":"Mozilla/5.0 (compatible; valuation-research/1.0)",
        "Accept":"application/json, text/plain, */*",
        "Referer":"https://www.csindex.com.cn/"
    },timeout=38)
    r.raise_for_status()
    result=parse_csi_payload(r.json(),symbol)
    if result.empty:
        raise ValueError("Official CSI has no usable rolling PE for "+symbol)
    return result

def load_history(symbol,today,fetcher=fetch_official):
    CACHE.mkdir(parents=True,exist_ok=True)
    p=CACHE/(symbol+"_pe.csv")
    prior=None
    if p.exists():
        try:prior=normalize(pd.read_csv(p,dtype={"date":str}))
        except (OSError,ValueError):prior=None
    # Bootstrap yearly chunks to avoid large CSI API responses. If valid cached
    # historical series exists, only refresh overlapping recent observations.
    start=pd.Timestamp(today)-pd.DateOffset(years=10,days=30)
    fresh_start=(max(start,prior.date.iloc[-1]-pd.Timedelta(days=35))
                 if prior is not None and len(prior)>30 else start)
    today_ts=pd.Timestamp(today)
    chunks=[]
    cursor=fresh_start
    failures=[]
    while cursor<=today_ts:
        stop=min(cursor+pd.DateOffset(years=2)-pd.Timedelta(days=1),today_ts)
        try:
            chunk=fetcher(symbol,cursor,stop)
            if not chunk.empty:chunks.append(chunk)
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            failures.append(str(exc)[:180])
        cursor=stop+pd.Timedelta(days=1)
    if failures and (prior is None or prior.empty):
        # No unverified / partial bootstrap: the next run can retry all chunks.
        raise ValueError("Official historical PE fetch incomplete: "+"; ".join(failures[:2]))
    all_frames=([prior] if prior is not None else [])+chunks
    if not all_frames:raise ValueError("No genuine rolling PE observations available")
    merged=normalize(pd.concat(all_frames,ignore_index=True))
    merged=merged[merged.date>=start].reset_index(drop=True)
    if merged.empty:raise ValueError("No recent PE observations")
    if (today_ts-merged.date.iloc[-1]).days>12:
        raise ValueError("Latest rolling PE is too old: "+str(merged.date.iloc[-1].date()))
    # Do not overwrite verified cache if any request of this update failed;
    # leave real older observations intact and try again on next run.
    if not failures:
        merged.to_csv(p,index=False,float_format="%.7f")
    return merged

def build_index(symbol,name,preferred,frame,today):
    d=normalize(frame)
    if len(d)<MIN_DAYS_PER_YEAR:
        raise ValueError("Not enough genuine index PE samples")
    final=d.iloc[-1]; end=final.date
    ref=(end.replace(day=1)-pd.Timedelta(days=1)).normalize()
    periods={}
    for years in (3,5,10):
        begin=end-pd.DateOffset(years=years)
        hist=d[(d.date>=begin)&(d.date<=end)]
        reference=d[(d.date>=begin)&(d.date<=ref)]
        if (len(hist)<years*MIN_DAYS_PER_YEAR or
            len(reference)<years*MIN_DAYS_PER_YEAR-20 or
            hist.date.iloc[0]>begin+pd.Timedelta(days=45)):
            continue
        values=reference.pe
        # Horizontal levels freeze at last complete calendar month.
        # Current percentile uses the available current as-of history.
        line={f"p{p}":round(float(values.quantile(p/100)),4) for p in PERCENTILES}
        current_pct=float((hist.pe<=float(final.pe)).mean()*100)
        periods[str(years)]={**line,"percentile":round(current_pct,2),
            "sampleCount":int(len(reference)),"referenceDate":str(reference.date.iloc[-1].date())}
    if not periods:
        raise ValueError("At least 3 years of continuous genuine PE series required")
    # Weekly view makes a readable chart with compact payload; always include last day.
    sampled=d.groupby(d.date.dt.to_period("W")).tail(1)
    if sampled.date.iloc[-1]!=final.date:
        sampled=pd.concat([sampled,d.tail(1)],ignore_index=True)
    return {"code":symbol,"name":name,"valid":True,
        "metric":"PE-TTM","preferredMetric":preferred,
        "note":("PB历史数据源暂缺，使用官方PE-TTM，不能视为PB"
                if preferred=="PB" else ""),
        "source":"中证指数有限公司 · index-perf 滚动市盈率",
        "date":str(end.date()),"value":round(float(final.pe),4),
        "points":[[str(r.date.date()),round(float(r.pe),4)] for r in sampled.itertuples()],
        "periods":periods}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    today=now.date()
    target=OUT/"industry_latest.json"
    status_path=OUT/"industry_status.json"
    old={}
    try:
        old=json.loads(target.read_text(encoding="utf-8"))
        old={str(i.get("code")):i for i in old.get("items",[]) if i.get("valid") is True}
    except (OSError,ValueError,AttributeError,TypeError):pass
    items=[];problems={}
    for code,name,preferred in SYMBOLS:
        try:
            d=load_history(code,today)
            item=build_index(code,name,preferred,d,today)
            items.append(item)
            print("Industry PE ok",code,item["date"],list(item["periods"]),flush=True)
        except Exception as exc:
            print("Industry PE failed",code,repr(exc),flush=True)
            problems[code]=str(exc)[:240]
            if code in old:
                item=old[code]
                item["note"]=(item.get("note","")+" · 当前刷新失败，显示上次数据").strip(" ·")
                items.append(item)
            else:
                items.append({"code":code,"name":name,"valid":False,
                    "metric":preferred,"reason":"暂未取得足够的真实历史估值数据"})
    target.write_text(json.dumps({"mode":"industry-valuations-v1",
        "generatedAt":now.isoformat(),"items":items},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    status_path.write_text(json.dumps({"attemptAt":now.isoformat(),
        "success":len(problems)==0,"usableCount":sum(bool(i.get("valid")) for i in items),
        "errors":problems},ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
