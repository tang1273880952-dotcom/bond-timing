"""Fetch four authentic CSI PE histories and three public PB percentile histories.

CSI index-perf records include an independently reported rolling P/E (row[15]).
We deliberately do not substitute index closing price for valuation or fabricate
PB, and we preserve the last verified observations on provider outage.
"""
from __future__ import annotations
import json
import traceback
import time
import re
from bs4 import BeautifulSoup
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
PB_PAGES={"399975":"zqgs","399998":"zzmt","399986":"zzyh"}
PB_SOURCE="百分位 baifenwei.com · 指数PB近10年历史分位（每周）"
PB_MULTIPLE_SOURCE="股叉叉 guchacha.com · 399975 指数整体市净率历史周度倍数"
PB_MULTIPLE_URL="https://guchacha.com/api/index/valuation/399975"
MIN_DAYS_PER_YEAR=150
PERCENTILES=(0,10,20,50,80,90,100)

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
        # The live CSI JSON API now emits dict records with "peg" for rolling
        # P/E. AKShare's historical wrapper maps the same field to 滚动市盈率.
        # Legacy list records also have rolling PE at position 15.
        if isinstance(row,dict):
            code=str(row.get("indexCode","")).strip().zfill(6)
            if code!=symbol:
                continue
            records.append({"date":row.get("tradeDate"),"pe":row.get("peg")})
        elif isinstance(row,(list,tuple)) and len(row)>=16:
            if str(row[1]).strip().zfill(6)!=symbol:
                continue
            records.append({"date":row[0],"pe":row[15]})
    return normalize(pd.DataFrame(records,columns=["date","pe"]))

def fetch_official(symbol,start,end,session=None):
    sess=session or requests.Session()
    params={"indexCode":symbol,
            "startDate":pd.Timestamp(start).strftime("%Y%m%d"),
            "endDate":pd.Timestamp(end).strftime("%Y%m%d")}
    for attempt in range(3):
        r=sess.get(ENDPOINT,params=params,headers={
            "User-Agent":"Mozilla/5.0 (compatible; valuation-research/1.0)",
            "Accept":"application/json, text/plain, */*",
            "Referer":"https://www.csindex.com.cn/"
        },timeout=38)
        if r.status_code not in (403,429) or attempt==2:
            r.raise_for_status()
            break
        time.sleep(4*(attempt+1))
    payload=r.json()
    result=parse_csi_payload(payload,symbol)
    if result.empty:
        sample=repr((payload.get("data") or [])[:1])[:420]
        print("CSI schema diagnostic",symbol,"rows",len(payload.get("data") or []),
              "first",sample,flush=True)
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
    all_frames=([prior] if prior is not None else [])+chunks
    if not all_frames:raise ValueError("No genuine rolling PE observations available")
    merged=normalize(pd.concat(all_frames,ignore_index=True))
    merged=merged[merged.date>=start].reset_index(drop=True)
    if merged.empty:raise ValueError("No recent PE observations")
    # An incomplete download still contributes genuine official observations
    # to a cache; a future attempt must complete the historical coverage.
    if chunks:
        merged.to_csv(p,index=False,float_format="%.7f")
    if failures:
        raise ValueError("Official historical PE fetch incomplete: "+"; ".join(failures[:2]))
    if (today_ts-merged.date.iloc[-1]).days>12:
        raise ValueError("Latest rolling PE is too old: "+str(merged.date.iloc[-1].date()))
    return merged

def build_index(symbol,name,preferred,frame,today):
    d=normalize(frame)
    if len(d)<MIN_DAYS_PER_YEAR:
        raise ValueError("Not enough genuine index PE samples")
    final=d.iloc[-1]; end=final.date
    ref=(end.replace(day=1)-pd.Timedelta(days=1)).normalize()
    periods={}
    for years in (3,5,10):
        # Both the seven horizontal lines AND current percentile use precisely
        # the same historical sample, ending at the LAST COMPLETE MONTH.
        # A separate live observation can fall outside [p0,p100].
        begin=ref-pd.DateOffset(years=years)
        reference=d[(d.date>=begin)&(d.date<=ref)]
        if (len(reference)<years*MIN_DAYS_PER_YEAR or
            reference.date.iloc[0]>begin+pd.Timedelta(days=45) or
            reference.date.iloc[-1]<ref-pd.Timedelta(days=12)):
            continue
        values=reference.pe
        line={f"p{p}":round(float(values.quantile(p/100)),4) for p in PERCENTILES}
        current_pct=float(values.le(float(final.pe)).mean()*100)
        if any(line[f"p{p}"]>line[f"p{q}"] for p,q in zip(PERCENTILES,PERCENTILES[1:])):
            raise ValueError("Percentile reference order failed")
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


def parse_public_pb_page(html,code,today):
    """Only genuine PB snapshot and *historical PB percentile* observations.

    This provider does NOT expose historical PB multiples. Never call its
    pb_pct values PB multiples or calculate 3/5-year PB value percentiles.
    """
    if code not in PB_PAGES:
        raise ValueError("PB source unsupported for "+code)
    soup=BeautifulSoup(html,"html.parser")
    content=soup.get_text(" ",strip=True)
    check=re.search(r"代码：\s*(\d{6})\b",content)
    if not check or check.group(1)!=code:
        raise ValueError("Wrong public index code")
    date_match=re.search(r"最新交易日：\s*(\d{4}-\d{2}-\d{2})",content)
    pb_match=re.search(r"PB\s*·\s*市净率\s+\S+\s+(\d+(?:\.\d+)?)\s+近\s*10\s*年百分位\s*(\d+(?:\.\d+)?)%",content)
    if not date_match or not pb_match:raise ValueError("PB value or date absent from published page")
    latest=pd.Timestamp(date_match.group(1))
    if (pd.Timestamp(today)-latest).days>9 or latest>pd.Timestamp(today):
        raise ValueError("PB snapshot stale or dated in future")
    pb=float(pb_match.group(1)); rank=float(pb_match.group(2))
    if not (.2<=pb<=20 and 0<=rank<=100):
        raise ValueError("PB or PB rank outside plausible bounds")
    chart=None
    for tag in soup.find_all("script"):
        match=re.search(r"\bvar\s+d\s*=\s*(\[\{.*?\}\])\s*;",tag.string or tag.get_text() or "",flags=re.S)
        if match:
            chart=json.loads(match.group(1))
            break
    if not isinstance(chart,list) or len(chart)<420:
        raise ValueError("PB weekly 10-year percentile history insufficient")
    series=[]
    for row in chart:
        if not isinstance(row,dict):raise ValueError("Malformed public history")
        day=pd.Timestamp(str(row.get("date")))
        p=float(row.get("pb_pct"))
        if not (0<=p<=100) or not pd.notna(day):
            raise ValueError("Bad PB historical percentile")
        series.append((day,round(p,2)))
    if any(series[i][0]>=series[i+1][0] for i in range(len(series)-1)):
        raise ValueError("Unordered or duplicated PB weekly dates")
    if series[-1][0]!=latest or abs(series[-1][1]-rank)>0.11:
        raise ValueError("PB history endpoint and overview percentile disagree")
    if series[0][0]>latest-pd.DateOffset(years=9,months=6):
        raise ValueError("PB history does not cover approximately 10 years")
    # The provider only publishes TEN-YEAR historical rankings, not past PB multiples.
    # Do not expose 3/5-year selections with an unchanged ten-year percentile.
    periods={}
    fromdate=latest-pd.DateOffset(years=10)
    visible=[v for d,v in series if d>=fromdate]
    if len(visible)<420:
        raise ValueError("10y PB rank history not complete")
    periods["10"]={"percentile":rank,"rankYears":10,
        "sampleCount":len(visible),"referenceDate":str(latest.date()),
        **{f"p{k}":float(k) for k in PERCENTILES}}
    name=next(n for c,n,metric in SYMBOLS if c==code)
    return {"code":code,"name":name,"valid":True,"metric":"PB",
        "date":str(latest.date()),"value":pb,"periods":periods,
        "points":[[str(d.date()),v] for d,v in series],
        "pointMetric":"PB_10Y_PERCENTILE","source":PB_SOURCE,
        "note":"来源仅提供最新PB与每周10年PB分位，没有可核验的历史PB倍数；只显示10年视图，不伪造3/5年分位。"}

def fetch_public_pb(code,today,session=None):
    sess=session or requests.Session()
    url="https://baifenwei.com/index/"+PB_PAGES[code]+"/"
    r=sess.get(url,timeout=30,headers={
        "User-Agent":"Mozilla/5.0 (compatible; BondTimingResearch/1.0)",
        "Accept":"text/html"})
    r.raise_for_status()
    return parse_public_pb_page(r.text,code,today)



def parse_guchacha_pb(payload,code,today):
    """Parse the public index-wide historical weekly PB *multiples*, not ranks.

    Distinct providers' latest PB levels must NOT be joined to this timeline.
    """
    if code!="399975" or not isinstance(payload,dict):
        raise ValueError("Guchacha provider only verified for broker index 399975")
    head=payload.get("index") or {}
    if str(head.get("code"))!=code:
        raise ValueError("Index code mismatch in PB multiple source")
    lastday=pd.Timestamp(head.get("date"))
    if lastday>pd.Timestamp(today) or (pd.Timestamp(today)-lastday).days>9:
        raise ValueError("Guchacha historic PB multiple snapshot stale")
    current=float(head.get("pb"))
    raw=(payload.get("series") or {}).get("pb")
    if not isinstance(raw,list) or len(raw)<480:
        raise ValueError("Guchacha historic PB multiples need >=480 observations")
    rows=[]
    for item in raw:
        if not isinstance(item,dict):raise ValueError("PB history row not an object")
        d=pd.to_datetime(item.get("d"),errors="coerce")
        v=pd.to_numeric(item.get("v"),errors="coerce")
        if pd.isna(d) or not pd.notna(v) or not (0.1<float(v)<30):
            raise ValueError("Invalid historical PB multiple")
        rows.append((pd.Timestamp(d).normalize(),float(v)))
    if any(rows[i][0]>=rows[i+1][0] for i in range(len(rows)-1)):
        raise ValueError("Duplicate/out-of-order PB multiple dates")
    last=rows[-1]
    if (lastday-last[0]).days>9 or (lastday-last[0]).days<0:
        raise ValueError("Guchacha PB history endpoint date inconsistent")
    if abs(current-last[1])>max(0.08,current*.06):
        raise ValueError("Guchacha PB history and headline PB do not agree")
    reference_end=lastday.to_period("M").start_time-pd.Timedelta(days=1)
    periods={}
    for years in (3,5,10):
        start=reference_end-pd.DateOffset(years=years)
        hist=[v for d,v in rows if start<=d<=reference_end]
        histdates=[d for d,v in rows if start<=d<=reference_end]
        if len(hist)<years*42 or not histdates or \
                histdates[0]>start+pd.Timedelta(days=50) or \
                histdates[-1]<reference_end-pd.Timedelta(days=15):
            continue
        values=pd.Series(hist)
        bands={f"p{k}":round(float(values.quantile(k/100)),4)
               for k in PERCENTILES}
        periods[str(years)]={**bands,
            "percentile":round(float(values.le(current).mean()*100),2),
            "sampleCount":len(hist),
            "referenceDate":str(histdates[-1].date()),
            "rankYears":years}
    if not all(str(year) in periods for year in (3,5,10)):
        raise ValueError("Genuine PB series does not cover all 3/5/10-year windows")
    return {"code":code,"name":"证券公司","valid":True,"metric":"PB",
        "date":str(lastday.date()),"value":round(current,4),
        "pointMetric":"PB_MULTIPLE",
        "source":PB_MULTIPLE_SOURCE,
        "points":[[str(d.date()),round(v,4)] for d,v in rows],
        "periods":periods,
        "note":"真实历史PB倍数；3/5/10年分位线使用对应年限、截止上一个完整自然月的历史样本独立计算。"}

def fetch_guchacha_pb(code,today,session=None):
    sess=session or requests.Session()
    r=sess.get(PB_MULTIPLE_URL,timeout=30,headers={
        "User-Agent":"Mozilla/5.0 (compatible; BondTimingResearch/1.0)",
        "Accept":"application/json"})
    r.raise_for_status()
    return parse_guchacha_pb(r.json(),code,today)

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
    # Prioritize indices with no historical cache: official CSI may rate-limit.
    order=sorted(SYMBOLS,key=lambda item:(CACHE/(item[0]+"_pe.csv")).exists())
    results={}
    for code,name,preferred in order:
        try:
            if code=="399975":
                item=fetch_guchacha_pb(code,today)
                print("Broker REAL PB MULTIPLES verified",code,item["date"],item["value"],flush=True)
            elif code in PB_PAGES:
                item=fetch_public_pb(code,today)
                print("Industry TEN-YEAR PB rank verified",code,item["date"],item["value"],flush=True)
            else:
                d=load_history(code,today)
                item=build_index(code,name,preferred,d,today)
                print("Industry PE verified",code,item["date"],list(item["periods"]),flush=True)
            results[code]=item
        except Exception as exc:
            print("Industry PE failed",code,repr(exc),flush=True)
            problems[code]=str(exc)[:240]
            if code in old and (code not in PB_PAGES or old[code].get("metric")=="PB"):
                item=old[code]
                item["stale"]=True
                item["note"]=(item.get("note","")+" · 当前刷新失败，沿用上次真实数据").strip(" ·")
                results[code]=item
            else:
                results[code]={"code":code,"name":name,"valid":False,
                    "metric":"PB" if code in PB_PAGES else "PE-TTM",
                    "reason":"PB数据暂时不可核验，不回退显示PE" if code in PB_PAGES
                    else "暂未取得足够的真实PE历史数据"}
    items=[results[code] for code,_,_ in SYMBOLS]
    target.write_text(json.dumps({"mode":"industry-valuations-v2",
        "generatedAt":now.isoformat(),"items":items},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    status_path.write_text(json.dumps({"attemptAt":now.isoformat(),
        "success":len(problems)==0,"usableCount":sum(bool(i.get("valid")) for i in items),
        "errors":problems},ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
