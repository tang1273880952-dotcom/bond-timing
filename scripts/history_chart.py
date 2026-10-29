"""Historical CSI 500 ERP chart. Never invent weekly observations."""
import math

import pandas as pd


QUANTILES = (10, 20, 50, 80, 90)


def _clean(frame, column):
    src = frame[["date", column]].copy()
    src["date"] = pd.to_datetime(src["date"], errors="coerce").dt.normalize()
    src[column] = pd.to_numeric(src[column], errors="coerce")
    src = src.dropna(subset=["date", column])
    src = src[src[column].map(math.isfinite)]
    return src.sort_values("date").drop_duplicates("date", keep="last")


def official_csi500_erp(yields, end, api=None):
    """Get *actual daily* rolling PE of CSI 500 from CSI Index and match 10Y yields.

    Chunk official historical index records to avoid server response limits.
    No historical interpolations or look-ahead-filled PE observations.
    """
    if api is None:
        import akshare as ak
        api = ak.stock_zh_index_hist_csindex
    end = pd.Timestamp(end).normalize()
    start = end - pd.DateOffset(years=10) - pd.Timedelta(days=14)
    cursor = start
    frames = []
    while cursor <= end:
        finish = min(cursor + pd.Timedelta(days=680), end)
        raw = api(
            symbol="000905",
            start_date=cursor.strftime("%Y%m%d"),
            end_date=finish.strftime("%Y%m%d"),
        )
        if raw is None or raw.empty:
            raise ValueError("中证指数官方历史估值接口没有返回数据")
        if "滚动市盈率" not in raw.columns:
            raise ValueError("中证指数官方历史行情缺少滚动市盈率字段")
        if "指数代码" in raw.columns:
            codes = raw["指数代码"].astype(str).str.replace(r"\.0$", "", regex=True)
            raw = raw[codes.str.zfill(6) == "000905"]
        if raw.empty:
            raise ValueError("官方接口未返回中证500指数数据")
        frame = raw[["日期", "滚动市盈率"]].rename(
            columns={"日期": "date", "滚动市盈率": "pe"}
        )
        frames.append(frame)
        cursor = finish + pd.Timedelta(days=1)

    pe = _clean(pd.concat(frames, ignore_index=True), "pe")
    pe = pe[pe.pe > 0]
    y = _clean(yields, "y10")
    matched = pd.merge_asof(
        pe, y, on="date", direction="backward", tolerance=pd.Timedelta(days=5)
    ).dropna(subset=["y10"])
    matched["erp"] = 100 / matched.pe - matched.y10
    matched = matched[matched.date >= end - pd.DateOffset(years=10)]
    span = (matched.date.iloc[-1] - matched.date.iloc[0]).days if len(matched) else 0
    if len(matched) < 1200 or span < 9 * 365:
        raise ValueError("官方真实日度ERP历史样本不足10年: " + str(len(matched)))
    if (end - matched.date.max()).days > 8:
        raise ValueError("官方PE历史数据不是最新交易日: " + str(matched.date.max()))
    return matched


def build_history(erp_frame, frequency="weekly", source=None):
    """Quantiles use all raw observations; weekly plotting takes last real day.

    When daily data are unavailable, retain monthly data honestly labelled monthly.
    """
    if frequency not in ("weekly", "monthly"):
        raise ValueError("unsupported history frequency")
    src = _clean(erp_frame, "erp")
    if len(src) < 80:
        raise ValueError("历史ERP有效样本不足: " + str(len(src)))
    src = src[src.date >= src.date.iloc[-1] - pd.DateOffset(years=10)].copy()
    period = "W-SUN" if frequency == "weekly" else "M"
    src["period"] = src.date.dt.to_period(period)
    display = src.drop_duplicates("period", keep="last")
    if len(display) < 24:
        raise ValueError("历史走势图有效时间点不足")
    erp = src["erp"]
    latest = float(erp.iloc[-1])
    last_date = src.date.iloc[-1]
    periods = {}
    for years in (3, 5, 10):
        cutoff = last_date - pd.DateOffset(years=years)
        window = src.loc[src.date >= cutoff, "erp"]
        minimum = 8 * years if frequency == "monthly" else 150 * years
        if len(window) < minimum:
            raise ValueError(f"近{years}年ERP真实样本不足: {len(window)} < {minimum}")
        periods[str(years)] = {
            "from": str(cutoff.date()),
            "to": str(last_date.date()),
            "sampleCount": len(window),
            "percentile": round(float(window.le(latest).mean() * 100), 2),
            **{"p" + str(n): round(float(window.quantile(n / 100)), 4)
               for n in QUANTILES},
        }
    ten_year = periods["10"]
    return {
        "version": 3,
        "metric": "csi500_erp",
        "unit": "%",
        "frequency": frequency,
        "source": source or ("中证指数官方滚动PE及中国10年国债收益率" if frequency == "weekly"
                            else "乐咕乐股月度滚动PE及中国10年国债收益率"),
        "reference": "3年、5年、10年各自用对应区间的真实ERP观测计算分位；不是ETF价格或回测",
        "series": {
            "csi500": {
                "date": str(src.date.iloc[-1].date()),
                "latest": round(latest, 4),
                "percentile": ten_year["percentile"],
                **{key: ten_year[key] for key in ("p10", "p20", "p50", "p80", "p90")},
                "sampleCount": len(src),
                "periods": periods,
                "points": [[str(row.date.date()), round(float(row.erp), 4)]
                           for row in display.itertuples(index=False)],
            }
        },
    }
