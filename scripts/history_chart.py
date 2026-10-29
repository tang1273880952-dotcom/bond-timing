"""Historical ERP and Chinese sovereign yield series for the compact chart.

Fixed 20%/80% reference lines use the current ten-year daily sample.
Monthly points are for display only, never backtest entry signals or ETF prices.
"""
import math
import pandas as pd

def compact_series(frame, field):
    src=frame[["date",field]].copy()
    src["date"]=pd.to_datetime(src["date"],errors="coerce")
    src[field]=pd.to_numeric(src[field],errors="coerce")
    src=src.dropna(subset=["date",field])
    src=src[src[field].map(math.isfinite)]
    src=src.sort_values("date").drop_duplicates("date",keep="last")
    if src.empty or len(src)<80:
        raise ValueError("历史曲线有效日度样本不足: "+field)
    cutoff=src["date"].iloc[-1]-pd.DateOffset(years=10)
    src=src[src["date"]>=cutoff].copy()
    src["month"]=src["date"].dt.to_period("M")
    monthly=src.drop_duplicates("month",keep="last")
    if len(monthly)<24:
        raise ValueError("历史曲线有效月度样本不足: "+field)
    return {
        "date":str(src["date"].iloc[-1].date()),
        "latest":round(float(src[field].iloc[-1]),4),
        "p20":round(float(src[field].quantile(.2)),4),
        "p80":round(float(src[field].quantile(.8)),4),
        "dailySamples":len(src),
        "points":[[str(row.date.date()),round(float(getattr(row,field)),4)]
                  for row in monthly.itertuples(index=False)]
    }

def build_history(stock_window,bond_window):
    return {
        "version":1,
        "unit":"%",
        "frequency":"每月最后一个有效交易日；本月为最新可用交易日",
        "reference":"近10年日度观测值的20%/80%分位；非ETF价格或历史回测",
        "series":{
            "csi500":compact_series(stock_window,"erp"),
            "bond10":compact_series(bond_window,"y10"),
            "bond30":compact_series(bond_window,"y30")
        }
    }
