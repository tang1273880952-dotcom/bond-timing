"""BSE 50 (899050) stock-bond risk premium from actual index daily PE.

No index PE? No fabricated ERP. Price observations may still be shown.
"""
import math

import pandas as pd

CODE = "899050"
LISTING = pd.Timestamp("2022-11-21")
QUANTILES = (10, 20, 50, 80, 90)


def clean(frame, key):
    out = frame[["date", key]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out[key] = pd.to_numeric(out[key], errors="coerce")
    out = out.dropna(subset=["date", key])
    out = out[out[key].map(math.isfinite)]
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def official_daily(end, api=None, start=None):
    """Fetch official 899050 from publication onward, in bounded chunks."""
    if api is None:
        import akshare as ak
        api = ak.stock_zh_index_hist_csindex
    end = pd.Timestamp(end).normalize()
    chunks = []
    cursor = max(LISTING, pd.Timestamp(start).normalize()) if start is not None else LISTING
    while cursor <= end:
        finish = min(cursor + pd.Timedelta(days=590), end)
        raw = api(symbol=CODE, start_date=cursor.strftime("%Y%m%d"),
                  end_date=finish.strftime("%Y%m%d"))
        if raw is None or raw.empty:
            raise ValueError("北证50官方行情没有返回记录")
        if not {"日期", "收盘"}.issubset(raw.columns):
            raise ValueError("北证50官方数据缺少日期或收盘点位")
        if "指数代码" in raw.columns:
            codes = raw["指数代码"].astype(str).str.replace(r"\.0$", "", regex=True)
            raw = raw[codes.str.zfill(6) == CODE]
        if raw.empty:
            raise ValueError("行情返回指数代码与899050不符")
        copy = raw.copy()
        copy["date"] = pd.to_datetime(copy["日期"], errors="coerce").dt.normalize()
        copy["close"] = pd.to_numeric(copy["收盘"], errors="coerce")
        copy["pe"] = pd.to_numeric(
            copy["滚动市盈率"] if "滚动市盈率" in copy else float("nan"),
            errors="coerce",
        )
        chunks.append(copy[["date", "close", "pe"]])
        cursor = finish + pd.Timedelta(days=1)
    result = pd.concat(chunks, ignore_index=True)
    result = result.dropna(subset=["date"]).sort_values("date")
    return result.drop_duplicates("date", keep="last").reset_index(drop=True)


def build_bse50(daily, yields, asof):
    """One- and three-year monthly-locked percentile lines, weekly actual ERP."""
    asof = pd.Timestamp(asof).normalize()
    close = clean(daily, "close")
    close = close[(close.close > 0) & (close.date >= LISTING)]
    if len(close) < 350 or (asof - close.date.iloc[-1]).days > 8:
        raise ValueError("北证50真实指数点位数据不足或过期")
    close["week"] = close.date.dt.to_period("W-SUN")
    close_points = close.drop_duplicates("week", keep="last")
    base = {
        "code": CODE, "name": "北证50", "source": "中证指数公司899050官方历史行情",
        "date": str(close.date.iloc[-1].date()),
        "firstDate": str(close.date.iloc[0].date()),
        "indexLatest": round(float(close.close.iloc[-1]), 2),
        "indexPoints": [[str(r.date.date()), round(float(r.close), 2)]
                        for r in close_points.itertuples(index=False)],
        "valid": False, "frequency": "weekly",
        "note": "北证50于2022年11月21日发布，不存在真实10年历史估值。",
    }
    if "pe" not in daily:
        base["reason"] = "官方数据缺少滚动PE，因此无法核验股债风险溢价"
        return base
    pe = clean(daily, "pe")
    pe = pe[(pe.pe > 0) & (pe.date >= LISTING)]
    if len(pe) < 450 or (asof - pe.date.iloc[-1]).days > 8:
        base["reason"] = "北证50滚动PE有效历史不足或未及时更新，不显示推测ERP"
        return base
    y = clean(yields, "y10")
    aligned = pd.merge_asof(pe, y, on="date", direction="backward",
                            tolerance=pd.Timedelta(days=5))
    aligned = aligned.dropna(subset=["y10"])
    if len(aligned) < 450 or (asof - aligned.date.iloc[-1]).days > 8:
        base["reason"] = "北证50PE与国债收益率的有效同期数据不足"
        return base
    aligned["erp"] = 100 / aligned.pe - aligned.y10
    aligned["week"] = aligned.date.dt.to_period("W-SUN")
    weekly = aligned.drop_duplicates("week", keep="last")
    latest = aligned.iloc[-1]
    cutoff = aligned.date.iloc[-1].to_period("M").start_time - pd.Timedelta(days=1)
    windows = {}
    for years in (1, 3):
        sample = aligned[(aligned.date <= cutoff) &
                         (aligned.date >= cutoff - pd.DateOffset(years=years))]
        if len(sample) < years * 140 or sample.date.iloc[0] > cutoff - pd.DateOffset(
            years=years) + pd.Timedelta(days=24):
            continue
        values = sample.erp
        windows[str(years)] = {
            "referenceDate": str(sample.date.iloc[-1].date()),
            "sampleCount": len(values),
            "percentile": round(float(values.le(latest.erp).mean() * 100), 2),
            **{"p" + str(q): round(float(values.quantile(q / 100)), 4)
               for q in QUANTILES},
        }
    if "1" not in windows:
        base["reason"] = "北证50上一个完整月份的历史ERP样本不足，暂不计算估值分位"
        return base
    base.update({
        "valid": True,
        "pe": round(float(latest.pe), 3),
        "yield10": round(float(latest.y10), 4),
        "erp": round(float(latest.erp), 4),
        "valuationDate": str(latest.date.date()),
        "periods": windows,
        "points": [[str(row.date.date()), round(float(row.erp), 4)]
                   for row in weekly.itertuples(index=False)],
        "note": "ERP=100/北证50滚动PE-中国10年国债收益率；水平分位线每月按上个完整月份更新。北证50不足5年，不能与中证500的10年分位直接比较。",
    })
    return base
