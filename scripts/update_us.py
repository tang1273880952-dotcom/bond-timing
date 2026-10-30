"""US stock-bond valuation model. Monthly trailing P/E and monthly Treasury yield.
No fabricated scores: if a provider fails, keep the last verified snapshot.
"""
import json
import math
import re
import traceback
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)
TZ = ZoneInfo("Asia/Shanghai")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BondTimingResearch/1.0; educational research)", "Accept": "text/html,text/csv,*/*"}
PE_URL = "https://www.multpl.com/s-p-500-pe-ratio/table/by-month"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
YIELD_MONTHLY_URL = "https://www.multpl.com/10-year-treasury-rate/table/by-month"
PRICE_MONTHLY_URL = "https://www.multpl.com/s-p-500-historical-prices/table/by-month"

def download(url):
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    if len(response.content) < 400:
        raise ValueError("Download unexpectedly short: " + url)
    return response.text

def get_pe():
    html = download(PE_URL)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="datatable") or soup.find("table")
    if table is None:
        raise ValueError("Could not find S&P 500 PE history table")
    records = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        rawdate = cells[0].get_text(" ", strip=True)
        dt = pd.to_datetime(rawdate, format="%b %d, %Y", errors="coerce")
        rawval = cells[1].get_text(" ", strip=True)
        numbers = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", rawval)
        if pd.isna(dt) or not numbers:
            continue
        value = float(numbers[-1].replace(",", ""))
        if not 0 < value < 200:
            continue
        records.append((dt.normalize(), value, ("estimate" in rawval.lower()) or ("†" in rawval) or ((dt.year, dt.month) == (datetime.now(TZ).year, datetime.now(TZ).month))))
    if len(records) < 120:
        raise ValueError("P/E source insufficient points: " + str(len(records)))
    frame = pd.DataFrame(records, columns=["date", "pe", "estimated"])
    # Retain both the monthly label and latest quote until PE/yield matching.
    # Otherwise a newer yield can hide an earlier, usable same-month observation.
    return frame.sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)

def monthly_table(url, value_name):
    html=download(url)
    soup=BeautifulSoup(html, "html.parser")
    table=soup.find("table", id="datatable") or soup.find("table")
    if table is None:
        raise ValueError("Missing monthly history table: "+url)
    rows=[]
    for tr in table.find_all("tr"):
        cells=tr.find_all("td")
        if len(cells)<2:
            continue
        day=pd.to_datetime(cells[0].get_text(" ",strip=True),format="%b %d, %Y",errors="coerce")
        raw=cells[1].get_text(" ",strip=True)
        num=re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?",raw)
        if pd.isna(day) or not num:
            continue
        val=float(num[-1].replace(",",""))
        if val>0 and val<100000:
            rows.append((day.normalize(),val))
    frame=pd.DataFrame(rows,columns=["date",value_name])
    if len(frame)<120:
        raise ValueError("Monthly series too short: "+value_name+" "+str(len(frame)))
    return frame.sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)

def one_per_month(frame):
    result=frame.sort_values("date").copy()
    result["month"]=result.date.dt.to_period("M")
    return result.drop_duplicates("month",keep="last").drop(columns="month").reset_index(drop=True)

def build_erp_history(matched,monthly_prices=None):
    """Actual monthly observations; five references frozen at the last full month.

    Source monthly histories can be revised and include estimated trailing PE.
    This is a current historical comparison, not a point-in-time backtest.
    """
    data=one_per_month(matched)
    if data.empty:
        raise ValueError("S&P 500 matched ERP history is empty")
    for row in data.itertuples(index=False):
        if not all(math.isfinite(float(x)) for x in (row.pe,row.yield10,row.erp)) or row.pe<=0:
            raise ValueError("Invalid US historical valuation")
        if row.yieldSourceDate>row.date or (row.date-row.yieldSourceDate).days>42:
            raise ValueError("US historical yield date is in the future or too old")
        if abs(100/row.pe-row.yield10-row.erp)>1e-8:
            raise ValueError("US historical ERP calculation mismatch")
    latest=data.iloc[-1]
    reference=latest.date.to_period("M").start_time-pd.Timedelta(days=1)
    periods={}
    for years in (3,5,10):
        cutoff=reference-pd.DateOffset(years=years)
        sample=data[(data.date>=cutoff)&(data.date<=reference)]
        if (len(sample)<years*10 or sample.date.iloc[0]>cutoff+pd.Timedelta(days=32)
            or (reference-sample.date.iloc[-1]).days>40
            or sample.date.diff().dropna().max()>pd.Timedelta(days=65)):
            raise ValueError(f"S&P 500 complete {years}-year monthly history unavailable")
        periods[str(years)]={
            "from":str(cutoff.date()),"to":str(reference.date()),
            "referenceDate":str(reference.date()),"sampleCount":len(sample),
            "basis":"月度真实观测",
            "percentile":round(float(sample.erp.le(latest.erp).mean()*100),2),
            **{f"p{q}":round(float(sample.erp.quantile(q/100)),6) for q in (10,20,50,80,90)}
        }
    # Keep one extra year for independently auditing window boundaries.
    start=latest.date.to_period("M").start_time-pd.DateOffset(years=11)
    visible=data[data.date>=start]
    index_points=[]
    if monthly_prices is not None and not monthly_prices.empty:
        prices=one_per_month(monthly_prices)
        prices=prices[(prices.date>=start)&(prices.date<=latest.date)]
        index_points=[[str(r.date.date()),round(float(r.spx),2)]
                      for r in prices.itertuples(index=False) if math.isfinite(float(r.spx)) and r.spx>0]
    return {
        "version":1,"id":"sp500","valid":True,"frequency":"monthly","unit":"%",
        "date":str(latest.date.date()),"latest":round(float(latest.erp),6),
        "pe":round(float(latest.pe),6),"yield10":round(float(latest.yield10),6),
        "yieldDate":str(latest.yieldSourceDate.date()),"estimatedPE":bool(latest.estimated),
        "periods":periods,
        "points":[[str(r.date.date()),round(float(r.erp),6),round(float(r.pe),6),
                   round(float(r.yield10),6),str(r.yieldSourceDate.date()),bool(r.estimated)]
                  for r in visible.itertuples(index=False)],
        "indexClose":{"frequency":"monthly","source":"Multpl 标普500月度指数点位（历史月均价，最新为来源所列观测）",
                      "points":index_points},
        "sources":[PE_URL,YIELD_MONTHLY_URL,PRICE_MONTHLY_URL],
        "method":"ERP＝100÷标普500滚动PE－美国10年国债收益率。按来源日期向前匹配后每月保留一条真实观测；不插值为周线或日线。五条分位线仅使用上个完整月份及以前的3/5/10年样本，当前分位随最新ERP重算。历史月度数据可能修订，月初日期为来源月度标签，并非当日可交易信号；最新PE估算明确标注。"
    }

def fred(series):
    source = download(FRED_CSV.format(series=series))
    frame = pd.read_csv(StringIO(source))
    if frame.shape[1] < 2:
        raise ValueError("FRED missing columns: " + series)
    datecol = "observation_date" if "observation_date" in frame.columns else frame.columns[0]
    frame["date"] = pd.to_datetime(frame[datecol], errors="coerce").dt.normalize()
    valuecol = series if series in frame.columns else frame.columns[1]
    frame["value"] = pd.to_numeric(frame[valuecol], errors="coerce")
    frame = frame[["date", "value"]].dropna()
    frame = frame.drop_duplicates("date").sort_values("date")
    if len(frame) < 250:
        raise ValueError("FRED " + series + " has insufficient observations: " + str(len(frame)))
    return frame

def percent_rank(values, current):
    sample = pd.to_numeric(values, errors="coerce").dropna()
    if len(sample) < 90:
        raise ValueError("Not enough ten-year PE / ERP monthly samples: " + str(len(sample)))
    return float((sample <= current).mean() * 100)

def calculate():
    now = datetime.now(TZ)
    pe = get_pe()
    today=pd.Timestamp(now.date())
    pe=pe[pe.date<=today].copy()
    # Match only backward by source labels. Revised monthly series do not
    # constitute publication-dated information for a historical backtest.
    yield_history = monthly_table(YIELD_MONTHLY_URL, "yield10")
    yield_history=yield_history[yield_history.date<=today].copy()
    yield_history = yield_history.rename(columns={"date":"yieldSourceDate"})
    merged = pd.merge_asof(pe, yield_history,
                           left_on="date",right_on="yieldSourceDate",
                           direction="backward", tolerance=pd.Timedelta(days=42))
    merged = merged.dropna(subset=["yield10"]).copy()
    merged = one_per_month(merged)
    if len(merged) < 120:
        raise ValueError("PE and Treasury yields have too little matched history: "+str(len(merged)))
    merged["erp"] = 100.0 / merged.pe - merged.yield10
    latest = merged.iloc[-1]
    latest_yield = yield_history.iloc[-1]
    if (latest_yield.yieldSourceDate - latest.date).days > 42:
        raise ValueError("US PE stale: " + str(latest.date.date()))
    if (pd.Timestamp(now.date()) - latest_yield.yieldSourceDate).days > 45:
        raise ValueError("US Treasury yield stale: " + str(latest_yield.yieldSourceDate.date()))
    reference=latest.date.to_period("M").start_time-pd.Timedelta(days=1)
    window = merged[(merged.date >= reference-pd.DateOffset(years=10)) & (merged.date<=reference)]
    if len(window) < 90:
        raise ValueError("Insufficient observations in last ten years: " + str(len(window)))
    erp_rank = percent_rank(window.erp, latest.erp)
    pe_rank = percent_rank(window.pe, latest.pe)
    score = max(0, min(100, round(.65 * erp_rank + .35 * (100.0 - pe_rank))))
    trend = "unknown"
    price_date = None
    price = None
    ma10 = None
    price_error = None
    monthly_prices = None
    try:
        monthly_prices=monthly_table(PRICE_MONTHLY_URL, "spx")
        monthly_prices=one_per_month(monthly_prices[monthly_prices.date<=today])
        p0=monthly_prices.iloc[-1]
        if len(monthly_prices)>=24 and (pd.Timestamp(now.date())-p0.date).days<=45:
            price=float(p0.spx)
            price_date=str(p0.date.date())
            ma10=float(monthly_prices.spx.tail(10).mean())
            trend="above_10m" if price>=ma10 else "below_10m"
        else:
            price_error="Monthly S&P 500 price history missing or stale"
    except Exception as exc:
        price_error=str(exc)
        print("Monthly SP500 trend unavailable",price_error,flush=True)
    metrics = [
        ["标普500 PE（TTM）", f"{latest.pe:.2f}倍"],
        ["美国10年国债收益率（月度，与PE对齐）", f"{latest.yield10:.2f}%"],
        ["FED风险溢价（盈利收益率−美债10Y）", f"{latest.erp:+.2f}%"],
        ["风险溢价10年分位", f"{erp_rank:.1f}%"],
        ["PE 10年分位", f"{pe_rank:.1f}%"],
        ["PE数据日期", str(latest.date.date()) + (" · 估算" if latest.estimated else "")],
        ["美国10Y月度来源日期", str(latest.yieldSourceDate.date())]
    ]
    if price is not None:
        metrics.extend([
            ["标普500月度指数点位", f"{price:,.2f}"],
            ["最近10个月均价", f"{ma10:,.2f}"],
            ["月度价格日期", price_date]
        ])
    output = {
        "mode":"live",
        "id":"sp500",
        "name":"标普500",
        "score":int(score),
        "valuationDate":str(latest.date.date()),
        "yieldDate":str(latest.yieldSourceDate.date()),
        "yieldSourceLatestDate":str(latest_yield.yieldSourceDate.date()),
        "priceDate":price_date,
        "generatedAt":now.isoformat(),
        "estimatedPE":bool(latest.estimated),
        "trend":trend,
        "trendSourceWarning":price_error,
        "metrics":metrics,
        "model":"PE和美债按来源月度日期向前配对；月初日期为月度标签，历史可修订，最新PE可能估算。评分=65% ERP历史10年分位+35% PE反向分位，参考样本截止上个完整自然月，未经回测。趋势为标普500月度价格相对于近10个月均值，不能视为200日均线。",
        "sources":[PE_URL,YIELD_MONTHLY_URL,PRICE_MONTHLY_URL]
    }
    output["history"]=build_erp_history(merged,monthly_prices)
    print("US score",score,"PE",latest.pe,"yield",latest.yield10,"ERP",latest.erp,"trend",trend,flush=True)
    return output

def main():
    status={"attemptAt":datetime.now(TZ).isoformat()}
    try:
        result=calculate()
        (OUT/"us_latest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        status.update(success=True,valuationDate=result["valuationDate"],priceDate=result["priceDate"])
    except Exception as exc:
        traceback.print_exc()
        status.update(success=False,error=str(exc))
        print("US score invalid, keeping last verified US snapshot",flush=True)
    (OUT/"us_status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
