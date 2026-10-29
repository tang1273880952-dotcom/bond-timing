"""Historically honest, monthly rolling percentile bands for weekly CSI 500 ERP."""
import math

import pandas as pd

QUANTILES = (10, 20, 50, 80, 90)
WINDOWS = (3, 5, 10)


def _clean(frame, column):
    src = frame[["date", column]].copy()
    src["date"] = pd.to_datetime(src["date"], errors="coerce").dt.normalize()
    src[column] = pd.to_numeric(src[column], errors="coerce")
    src = src.dropna(subset=["date", column])
    src = src[src[column].map(math.isfinite)]
    return src.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def official_csi500_erp(yields, end, api=None, years=10):
    """Fetch genuinely observed official daily PE; join past (never future) yields."""
    if api is None:
        import akshare as ak
        api = ak.stock_zh_index_hist_csindex
    end = pd.Timestamp(end).normalize()
    start = end - pd.DateOffset(years=years) - pd.Timedelta(days=14)
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
        frames.append(
            raw[["日期", "滚动市盈率"]].rename(
                columns={"日期": "date", "滚动市盈率": "pe"}
            )
        )
        cursor = finish + pd.Timedelta(days=1)
    pe = _clean(pd.concat(frames, ignore_index=True), "pe")
    pe = pe[pe.pe > 0]
    y = _clean(yields, "y10")
    matched = pd.merge_asof(
        pe, y, on="date", direction="backward", tolerance=pd.Timedelta(days=5)
    ).dropna(subset=["y10"])
    matched["erp"] = 100 / matched.pe - matched.y10
    matched = matched[matched.date >= end - pd.DateOffset(years=years)]
    span = (matched.date.iloc[-1] - matched.date.iloc[0]).days if len(matched) else 0
    if years >= 10 and (len(matched) < years * 150 or span < (years - 1) * 365):
        raise ValueError("官方日度ERP长期历史不足: " + str(len(matched)))
    if years < 10 and len(matched) < 25:
        raise ValueError("官方近期ERP数据不足")
    if (end - matched.date.max()).days > 8:
        raise ValueError("官方PE历史数据明显滞后: " + str(matched.date.max()))
    return matched[["date", "erp"]].reset_index(drop=True)


def _window_asof(src, anchor, years, frequency):
    """Calculate using only observations available on or before anchor."""
    cutoff = anchor - pd.DateOffset(years=years)
    window = src[(src.date >= cutoff) & (src.date <= anchor)]
    count = len(window)
    minimum = years * (180 if frequency == "weekly" else 8)
    if count < minimum or window.empty:
        return None
    # Refuse to mislabel incomplete lookbacks, even if the count looks high.
    if window.date.iloc[0] > cutoff + pd.Timedelta(days=24):
        return None
    values = window.erp
    return {
        "sampleCount": count,
        "percentile": round(float(values.le(values.iloc[-1]).mean() * 100), 2),
        **{"p" + str(q): round(float(values.quantile(q / 100)), 4)
           for q in QUANTILES},
    }


def build_history(erp_frame, frequency="weekly", source=None):
    """Build point-in-time monthly rolling bands for visible last 10 years.

    10y lines need up to 20 years of original ERP. Missing genuine history is
    not filled, extrapolated, or calculated using future observations.
    """
    if frequency not in ("weekly", "monthly"):
        raise ValueError("unsupported history frequency")
    src = _clean(erp_frame, "erp")
    if len(src) < 80:
        raise ValueError("历史ERP有效样本不足: " + str(len(src)))
    last_date = src.date.iloc[-1]
    begin = last_date - pd.DateOffset(years=10)
    visible = src[src.date >= begin].copy()
    period = "W-SUN" if frequency == "weekly" else "M"
    visible["period"] = visible.date.dt.to_period(period)
    display = visible.drop_duplicates("period", keep="last")
    if len(display) < 24:
        raise ValueError("历史走势图有效时间点不足")
    visible["month"] = visible.date.dt.to_period("M")
    anchors = visible.drop_duplicates("month", keep="last").date.tolist()
    latest = float(src.erp.iloc[-1])
    windows = {}
    for years in WINDOWS:
        current = _window_asof(src, last_date, years, frequency)
        if current is None:
            raise ValueError("当前近" + str(years) + "年有效估值样本不足")
        bands = []
        for anchor in anchors:
            stats = _window_asof(src, anchor, years, frequency)
            if stats is None:
                continue  # Gap clearly visible, not an invented historical band.
            bands.append([
                str(anchor.date()),
                *[stats["p" + str(q)] for q in QUANTILES],
            ])
        windows[str(years)] = {
            "from": str((last_date - pd.DateOffset(years=years)).date()),
            "to": str(last_date.date()),
            **current,
            "bands": bands,
            "bandsFrequency": "monthly",
            "availableFrom": bands[0][0] if bands else None,
        }
    current10 = windows["10"]
    return {
        "version": 4,
        "metric": "csi500_erp",
        "unit": "%",
        "frequency": frequency,
        "reference": "月度滚动3/5/10年分位带；每个历史时点只使用当时及之前的真实ERP",
        "source": source or (
            "中证指数官方日度滚动PE及中国10年国债收益率"
            if frequency == "weekly"
            else "月度滚动PE及中国10年国债收益率"
        ),
        "series": {
            "csi500": {
                "date": str(last_date.date()),
                "latest": round(latest, 4),
                "percentile": current10["percentile"],
                **{key: current10[key] for key in ("p10", "p20", "p50", "p80", "p90")},
                "sampleCount": len(visible),
                "historyStartDate": str(src.date.iloc[0].date()),
                "periods": windows,
                "points": [
                    [str(row.date.date()), round(float(row.erp), 4)]
                    for row in display.itertuples(index=False)
                ],
            }
        },
    }
