"""US stock-bond valuation model. Monthly trailing P/E + daily Treasury yield.
No fabricated scores: if a provider fails, keep the last verified snapshot.
"""
import json
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
        records.append((dt.normalize(), value, "estimate" in rawval.lower()))
    if len(records) < 120:
        raise ValueError("P/E source insufficient points: " + str(len(records)))
    frame = pd.DataFrame(records, columns=["date", "pe", "estimated"])
    # Keep the most recent observation of each calendar month; exclude duplicate month entries.
    frame = frame.sort_values("date").drop_duplicates("date").drop_duplicates(
        frame["date"].dt.to_period("M") if False else "date", keep="last"
    )
    frame["month"] = frame.date.dt.to_period("M")
    frame = frame.drop_duplicates("month", keep="last").drop(columns="month")
    return frame.sort_values("date").reset_index(drop=True)

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
    yield_history = fred("DGS10").rename(columns={"value":"yield10"})
    merged = pd.merge_asof(pe, yield_history, on="date", direction="backward", tolerance=pd.Timedelta(days=7))
    merged = merged.dropna(subset=["yield10"]).copy()
    if len(merged) < 120:
        raise ValueError("PE and Treasury yields have too little matched history: "+str(len(merged)))
    merged["erp"] = 100.0 / merged.pe - merged.yield10
    latest = merged.iloc[-1]
    latest_yield = yield_history.iloc[-1]
    if (latest_yield.date - latest.date).days > 42:
        raise ValueError("US PE stale: " + str(latest.date.date()))
    if (pd.Timestamp(now.date()) - latest_yield.date).days > 10:
        raise ValueError("US Treasury yield stale: " + str(latest_yield.date.date()))
    window = merged[merged.date >= latest.date - pd.DateOffset(years=10)]
    if len(window) < 90:
        raise ValueError("Insufficient observations in last ten years: " + str(len(window)))
    erp_rank = percent_rank(window.erp, latest.erp)
    pe_rank = percent_rank(window.pe, latest.pe)
    score = max(0, min(100, round(.65 * erp_rank + .35 * (100.0 - pe_rank))))
    trend = "unknown"
    price_date = None
    price = None
    ma200 = None
    ma50 = None
    price_error = None
    try:
        prices = fred("SP500").rename(columns={"value":"spx"})
        if len(prices) >= 220 and (pd.Timestamp(now.date()) - prices.iloc[-1].date).days <= 8:
            price = float(prices.iloc[-1].spx)
            price_date = str(prices.iloc[-1].date.date())
            ma200 = float(prices.spx.tail(200).mean())
            ma50 = float(prices.spx.tail(50).mean())
            trend = "above_200d" if price >= ma200 else "below_200d"
        else:
            price_error = "S&P 500 index closing price unavailable or stale"
    except Exception as exc:
        price_error = str(exc)
        print("Price trend optional source unavailable", price_error, flush=True)
    metrics = [
        ["标普500 PE（TTM）", f"{latest.pe:.2f}倍"],
        ["美国10年国债收益率（与PE对齐）", f"{latest.yield10:.2f}%"],
        ["FED风险溢价（盈利收益率−美债10Y）", f"{latest.erp:+.2f}%"],
        ["风险溢价10年分位", f"{erp_rank:.1f}%"],
        ["PE 10年分位", f"{pe_rank:.1f}%"],
        ["PE数据日期", str(latest.date.date()) + (" · 估算" if latest.estimated else "")],
        ["美国10Y最新可用日期", str(latest_yield.date.date())]
    ]
    if price is not None:
        metrics.extend([
            ["标普500收盘点位", f"{price:,.2f}"],
            ["200日均线", f"{ma200:,.2f}"],
            ["收盘日期", price_date]
        ])
    output = {
        "mode":"live",
        "id":"sp500",
        "name":"标普500",
        "score":int(score),
        "valuationDate":str(latest.date.date()),
        "yieldDate":str(latest_yield.date.date()),
        "priceDate":price_date,
        "generatedAt":now.isoformat(),
        "estimatedPE":bool(latest.estimated),
        "trend":trend,
        "trendSourceWarning":price_error,
        "metrics":metrics,
        "model":"PE为历史月度TTM（可能含最新估算）；10年国债日度收益率按PE发布日期向前配对；分位使用最近十年对应月度观测；评分=65% ERP分位+35% PE反向分位，未回测；趋势来自SP500收盘与200日均线，缺失则不提供趋势结论。",
        "sources":[PE_URL,"https://fred.stlouisfed.org/series/DGS10","https://fred.stlouisfed.org/series/SP500"]
    }
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
