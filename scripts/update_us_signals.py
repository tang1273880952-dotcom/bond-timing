"""US S&P 500 market-timing *observation* model, separate from ERP valuation.

Data are daily observed closes (FRED/S&P), VIX (FRED/Cboe), HY OAS (FRED/ICE)
and the site's already verified monthly ERP.  No guessed market breadth.
All thresholds are provisional, NOT backtested trade recommendations.
"""
from __future__ import annotations
import json
import math
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO
from pathlib import Path
import requests
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
FRED="https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; BondTimingResearch/1.0; public educational statistics)","Accept":"text/csv"}
WEIGHTS={"erp":30,"vix":15,"rsi":15,"breadth":15,"credit":15,"trend":10}

def fetch_fred(series,min_rows=40):
    response=requests.get(FRED.format(series),timeout=9,headers=HEADERS)
    response.raise_for_status()
    if len(response.content)<300:raise ValueError(series+": unexpectedly short CSV")
    table=pd.read_csv(StringIO(response.text))
    date_col="observation_date" if "observation_date" in table else "DATE" if "DATE" in table else None
    if date_col is None or series not in table.columns:
        raise ValueError(series+": wrong CSV schema")
    f=table[[date_col,series]].rename(columns={date_col:"date",series:"value"})
    f["date"]=pd.to_datetime(f["date"],errors="coerce").dt.normalize()
    f["value"]=pd.to_numeric(f["value"],errors="coerce")
    f=f.dropna().sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)
    if len(f)<min_rows or not f.date.is_monotonic_increasing:
        raise ValueError(series+": inadequate real EOD history")
    f.attrs["provider"]="FRED "+series
    return f


def fetch_price_yahoo():
    """Yahoo public v8 chart for the ACTUAL S&P 500 index, never SPY."""
    response=requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
        params={"range":"2y","interval":"1d"},
        headers={"User-Agent":"Mozilla/5.0 (compatible; BondTimingResearch/1.0)"},
        timeout=18)
    response.raise_for_status()
    result=response.json()["chart"]["result"][0]
    timestamps=result["timestamp"]
    closes=result["indicators"]["quote"][0]["close"]
    if len(timestamps)!=len(closes):
        raise ValueError("Yahoo S&P500 daily chart length mismatch")
    rows=[]
    ny=ZoneInfo("America/New_York")
    for timestamp,close in zip(timestamps,closes):
        if close is None:continue
        day=datetime.fromtimestamp(int(timestamp),tz=ny).date()
        value=float(close)
        if not (100<value<100000):raise ValueError("Yahoo S&P500 close outside range")
        rows.append((pd.Timestamp(day),value))
    frame=pd.DataFrame(rows,columns=["date","value"]).sort_values("date")
    frame=frame.drop_duplicates("date",keep="last").reset_index(drop=True)
    if len(frame)<230:raise ValueError("Yahoo S&P500 daily history incomplete")
    frame.attrs["provider"]="Yahoo Finance ^GSPC"
    return frame

def fetch_vix_cboe():
    """Cboe's official, freely published historical VIX closes."""
    url="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    response=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
    response.raise_for_status()
    f=pd.read_csv(StringIO(response.text))
    if not {"DATE","CLOSE"}.issubset(f.columns):
        raise ValueError("Cboe VIX CSV changed field names")
    f=f[["DATE","CLOSE"]].rename(columns={"DATE":"date","CLOSE":"value"})
    f["date"]=pd.to_datetime(f.date,errors="coerce").dt.normalize()
    f["value"]=pd.to_numeric(f.value,errors="coerce")
    f=f.dropna().sort_values("date").drop_duplicates("date",keep="last")
    f=f.reset_index(drop=True)
    if len(f)<40:raise ValueError("Cboe VIX historical close missing")
    f.attrs["provider"]="Cboe VIX daily close"
    return f

def fetch_price():
    try:return fetch_price_yahoo()
    except Exception as exc:
        print("Yahoo index close unavailable, checking FRED SP500:",str(exc)[:120],flush=True)
        return fetch_fred("SP500",230)

def fetch_vix():
    try:return fetch_vix_cboe()
    except Exception as exc:
        print("Cboe direct historical VIX unavailable, checking FRED:",str(exc)[:120],flush=True)
        return fetch_fred("VIXCLS",40)

def rsi14(closes):
    """Wilder 14-period RSI computed from index *daily closing prices*."""
    series=pd.Series(closes,dtype="float64")
    if len(series)<45 or (series<=0).any():raise ValueError("Insufficient S&P 500 EOD history for Wilder RSI")
    delta=series.diff()
    gain=delta.clip(lower=0).fillna(0)
    loss=(-delta).clip(lower=0).fillna(0)
    avg_gain=gain.iloc[1:15].mean()
    avg_loss=loss.iloc[1:15].mean()
    output=[None]*len(series)
    for idx in range(14,len(series)):
        if idx>14:
            avg_gain=(avg_gain*13+gain.iloc[idx])/14
            avg_loss=(avg_loss*13+loss.iloc[idx])/14
        if avg_loss==0:
            output[idx]=50.0 if avg_gain==0 else 100.0
        elif avg_gain==0:
            output[idx]=0.0
        else:
            output[idx]=100-100/(1+avg_gain/avg_loss)
    return output

def interpolate(value,knots):
    if value<=knots[0][0]:return float(knots[0][1])
    for (x0,y0),(x1,y1) in zip(knots,knots[1:]):
        if value<=x1:return y0+(value-x0)*(y1-y0)/(x1-x0)
    return float(knots[-1][1])

def row(f):
    rec=f.iloc[-1]
    return pd.Timestamp(rec.date),float(rec.value)

def pct(x):return round(float(x),2)

def build_model(price,vix,credit,us,asof):
    today=pd.Timestamp(asof).normalize()
    # Require enough observations to justify the reported one-year spread rank.
    credit_available=credit is not None and len(credit)>=220
    if len(price)<230 or len(vix)<40:
        raise ValueError("Daily S&P500 price or VIX history insufficient")
    pdte,close=row(price)
    vdte,vix_value=row(vix)
    cdte,oas=row(credit) if credit_available else (None,None)
    providers=[("S&P500",pdte),("VIX",vdte)]
    if credit_available:providers.append(("HY OAS",cdte))
    for name,dt in providers:
        age=(today-dt).days
        if age<0 or age>8:raise ValueError(f"{name}: stale or future close ({dt.date()})")
    # Never use a VIX or spread observation dated AFTER the price close.
    # Recent lagged provider observations are allowed, not future data.
    vix_lag=(pdte-vdte).days
    credit_lag=(pdte-cdte).days if credit_available else 0
    if not (0<=vix_lag<=4) or (credit_available and not (0<=credit_lag<=7)):
        raise ValueError("Daily source observation leads price or is too old")
    if (not (100<close<100000 and 5<vix_value<120) or
            (credit_available and not (.25<oas<30))):
        raise ValueError("Unreasonable raw SP500, VIX or HY OAS values")
    if us.get("mode")!="live" or us.get("id")!="sp500":
        raise ValueError("Existing monthly ERP valuation unavailable")
    months=us.get("history",{}).get("periods",{})
    period=months.get("10",{})
    erp_rank=period.get("percentile")
    valuation_date=pd.Timestamp(us.get("valuationDate"))
    if valuation_date>pdte or (today-valuation_date).days>48 or not isinstance(erp_rank,(int,float)) or not 0<=erp_rank<=100:
        raise ValueError("10-year real monthly ERP rank missing or too old")
    last=price.value.astype(float).to_list()
    rsi=rsi14(last)
    rsi_value=rsi[-1]
    ma20=float(pd.Series(last[-20:]).mean())
    ma50=float(pd.Series(last[-50:]).mean())
    ma200=float(pd.Series(last[-200:]).mean())
    prior20=float(credit.value.iloc[-21]) if credit_available and len(credit)>=21 else None
    prior5=float(credit.value.iloc[-6]) if credit_available and len(credit)>=6 else None
    oas5=oas-prior5 if prior5 is not None else None
    oas20=oas-prior20 if prior20 is not None else None
    percentile1y=round(100*float((credit.value.iloc[-253:]<=oas).mean()),2) if credit_available else None

    price_source=price.attrs.get("provider","标普500指数收盘价（来源未标记）")
    vix_source=vix.attrs.get("provider","VIX收盘价（来源未标记）")
    scores={
      "erp":30*erp_rank/100,
      "vix":interpolate(vix_value,[(12,0),(16,2),(20,5),(25,8),(30,11),(40,15)]),
      "rsi":interpolate(rsi_value,[(20,15),(30,13),(40,10),(50,6),(60,3),(70,0)]),
      "trend":(5 if close>=ma50 else 0)+(5 if close>=ma200 else 0)
    }
    if credit_available:
        scores["credit"]=min(15,max(0,.10*percentile1y+
            (4 if oas5 is not None and oas5<=-.10 else 0)))
    # A source of verifiable daily SP500 constituents breadth has not been connected.
    # Never manufacture its 15 points or attribute a 100-point total to six signals.
    indicators={
      "erp":{"value":pct(erp_rank),"unit":"%分位","score":pct(scores["erp"]),"weight":30,
             "date":str(valuation_date.date()),"source":"已有标普500真实月度ERP十年分位"},
      "vix":{"value":pct(vix_value),"unit":"","score":pct(scores["vix"]),"weight":15,
             "date":str(vdte.date()),"source":vix_source},
      "rsi":{"value":pct(rsi_value),"unit":"","score":pct(scores["rsi"]),"weight":15,
             "date":str(pdte.date()),"source":price_source+" · Wilder RSI(14)"},
      "breadth":{"value":None,"unit":"%","score":None,"weight":15,
             "date":None,"source":"S&P500成分股50日均线以上占比 · 历史接口待验证"},
      "credit":{"value":pct(oas) if credit_available else None,
             "unit":"%","score":pct(scores["credit"]) if credit_available else None,"weight":15,
             "date":str(cdte.date()) if credit_available else None,
             "source":"FRED: BAMLH0A0HYM2 · ICE BofA；暂时无法访问则不计算",
             "change5":pct(oas5) if oas5 is not None else None,"change20":pct(oas20) if oas20 is not None else None},
      "trend":{"value":pct(close),"unit":"点","score":pct(scores["trend"]),"weight":10,
             "date":str(pdte.date()),"source":price_source+" · MA50/MA200","ma20":pct(ma20),
             "ma50":pct(ma50),"ma200":pct(ma200)}
    }
    covered=sum(WEIGHTS[k] for k in scores)
    score=round(sum(scores.values())/covered*100)
    rsi_rebound=(rsi[-2] is not None and min(x for x in rsi[-11:-1] if x is not None)<35 and rsi[-1]>rsi[-2])
    short_trend=close>ma20 and close>float(price.value.iloc[-6])
    credit_improving=oas5 is not None and oas5<=-.05
    confirmed=[{"name":"RSI超卖后回升","met":bool(rsi_rebound)},
               {"name":"价格站上MA20且近5日走强","met":bool(short_trend)},
               {"name":"信用利差5日收窄≥0.05百分点","met":bool(credit_improving)}]
    confirmation_count=sum(a["met"] for a in confirmed)
    risk_flag=(not credit_available) or (oas20 is not None and oas20>=.75) or (
        vix_value>=40 and vix_value>float(vix.value.iloc[-6]))
    if score>=80 and confirmation_count>=2 and not risk_flag:
        action="关注分批买入";tone="cheap"
    elif score>=70 and confirmation_count>=1 and not risk_flag:
        action="试探性观察买入";tone="watch"
    elif erp_rank<20 and (rsi_value>=70 or (close<ma200 and oas20 is not None and oas20>=.5)):
        action="减仓风险观察";tone="rich"
    else:
        action="等待 / 持有观察";tone="neutral"
    # This is NOT a point-in-time backtest or a prediction of future returns.
    recent=price.tail(260)
    out={
      "valid":True,"mode":"sp500-signals-v1","score":score,"coveredWeight":covered,
      "missingWeight":100-covered,"complete":covered==100,"asof":str(pdte.date()),
      "riskDataIncomplete":not credit_available,
      "missingIndicators":["breadth"]+(["credit"] if not credit_available else []),
      "action":action,"tone":tone,"confirmed":confirmation_count,
      "confirmations":confirmed,"riskVeto":bool(risk_flag),
      "indicators":indicators,"latestPrice":pct(close),
      "priceHistory":[[str(r.date.date()),pct(r.value)] for r in recent.itertuples(index=False)],
      "method":"六因子预设权重30/15/15/15/15/10，未核验来源不计分，按已核验权重折算100并单独显示覆盖率；数据缺失或信用利差不可用不触发买入观察。规则未经历史回测，不代表交易建议。ERP是月度指标，其余为日度指标。",
      "sources":["https://finance.yahoo.com/quote/%5EGSPC/","https://www.cboe.com/tradable_products/vix/vix_historical_data",
                 "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"]
    }
    return out

def main():
    DATA.mkdir(exist_ok=True)
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    status={"attemptAt":now.isoformat()}
    target=DATA/"us_signals.json"
    try:
        us=json.loads((DATA/"us_latest.json").read_text(encoding="utf-8"))
        price=fetch_price()
        vix=fetch_vix()
        try:
            credit=fetch_fred("BAMLH0A0HYM2",220)
        except Exception as exc:
            print("HY OAS not reachable; keep credit weight missing and veto buy signals:",
                  str(exc)[:180],flush=True)
            credit=None
        result=build_model(price,vix,credit,us,now.date())
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        status.update(success=True,date=result["asof"],coveredWeight=result["coveredWeight"],
                      partial=result["coveredWeight"]<100,missingIndicators=result["missingIndicators"])
        print("US timing indicators verified",result["asof"],result["score"],
              "available weight",result["coveredWeight"],flush=True)
    except Exception as exc:
        traceback.print_exc()
        status.update(success=False,error=str(exc)[:320])
        if not target.exists():
            target.write_text(json.dumps({"valid":False,"mode":"sp500-signals-v1",
               "reason":"真实市场指标数据尚未核验，暂不提供评分与交易提示"},ensure_ascii=False),encoding="utf-8")
        print("US timing source failed: keeping last verified signal with original date",flush=True)
    (DATA/"us_signals_status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":main()
