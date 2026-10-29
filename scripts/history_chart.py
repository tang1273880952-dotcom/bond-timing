"""Historically honest, monthly rolling percentile bands for weekly CSI 500 ERP."""
import math

import pandas as pd

QUANTILES = (10, 20, 50, 80, 90)
WINDOWS = (3, 5, 10)


def _clean(frame, column):
    src = frame[["date", column]].copy()
    src["date"] = (pd.to_datetime(src["date"], errors="coerce")
                   .astype("datetime64[ns]").dt.normalize())
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
    # Some providers expose about 15 years of daily index valuations even if
    # requested for 20. Keep the authentic data; rolling 10y bands will begin
    # only after each historical anchor has its full lookback window.
    required_years = min(years - 1, 12)
    required_count = min(years * 150, 2500)
    if years >= 10 and (len(matched) < required_count or span < required_years * 365):
        raise ValueError("官方日度ERP长期历史不足: " + str(len(matched)))
    if years < 10 and len(matched) < 25:
        raise ValueError("官方近期ERP数据不足")
    if (end - matched.date.max()).days > 8:
        raise ValueError("官方PE历史数据明显滞后: " + str(matched.date.max()))
    return matched[["date", "erp"]].reset_index(drop=True)



def official_csi500_close(end, api=None, start=None):
    """Official CSI Index 000905 daily CLOSE levels (index points, not ETF NAV).

    This shares the CSI index-perf provider used by the existing ERP series.
    Missing data are never interpolated or made up.
    """
    if api is None:
        import akshare as ak
        api = ak.stock_zh_index_hist_csindex
    end = pd.Timestamp(end).normalize()
    start = pd.Timestamp(start).normalize() if start is not None else end - pd.DateOffset(years=10) - pd.Timedelta(days=15)
    cursor = start
    frames = []
    while cursor <= end:
        finish = min(cursor + pd.Timedelta(days=680), end)
        raw = api(symbol="000905", start_date=cursor.strftime("%Y%m%d"),
                  end_date=finish.strftime("%Y%m%d"))
        if raw is None or raw.empty or "日期" not in raw.columns or "收盘" not in raw.columns:
            raise ValueError("中证指数官方日度收盘点位数据不可用")
        if "指数代码" in raw.columns:
            codes = raw["指数代码"].astype(str).str.replace(r"\.0$", "", regex=True)
            raw = raw[codes.str.zfill(6) == "000905"]
        if raw.empty:
            raise ValueError("指数代码非000905，停止导入")
        frames.append(raw[["日期", "收盘"]].rename(columns={"日期": "date", "收盘": "close"}))
        cursor = finish + pd.Timedelta(days=1)
    result = _clean(pd.concat(frames, ignore_index=True), "close")
    result = result[result.close > 0].reset_index(drop=True)
    if result.empty or (end - result.date.iloc[-1]).days > 8:
        raise ValueError("中证500指数历史收盘价过期或空缺")
    return result


def build_index_overlay(daily_close, end):
    """Weekly real index CLOSE observations on the same date axis as ERP."""
    end = pd.Timestamp(end).normalize()
    data = _clean(daily_close, "close")
    data = data[data.close > 0]
    cutoff = end - pd.DateOffset(years=10)
    data = data[(data.date >= cutoff) & (data.date <= end)].copy()
    if len(data) < 1800:
        raise ValueError("中证500指数10年周线日度源样本不足")
    if data.date.iloc[0] > cutoff + pd.Timedelta(days=24):
        raise ValueError("中证500指数历史起点不足10年")
    if (end - data.date.iloc[-1]).days > 8:
        raise ValueError("中证500指数收盘价不是最新交易日")
    data["week"] = data.date.dt.to_period("W-SUN")
    sampled = data.drop_duplicates("week", keep="last")
    if len(sampled) < 470:
        raise ValueError("中证500指数周线历史不足")
    return {
        "code": "000905",
        "name": "中证500指数",
        "unit": "点",
        "source": "中证指数公司官方指数日度收盘点位（不是ETF价格）",
        "frequency": "weekly",
        "date": str(data.date.iloc[-1].date()),
        "latest": round(float(data.close.iloc[-1]), 2),
        "points": [
            [str(row.date.date()), round(float(row.close), 2)]
            for row in sampled.itertuples(index=False)
        ],
    }


def _window_asof(src, anchor, years, frequency):
    """Calculate using only observations available on or before anchor."""
    cutoff = anchor - pd.DateOffset(years=years)
    window = src[(src.date >= cutoff) & (src.date <= anchor)]
    count = len(window)
    minimum = years * (180 if frequency == "weekly" else 8)
    if count < minimum or window.empty:
        return None
    # Refuse to mislabel incomplete lookbacks, even if the count looks high.
    tolerance_days = 31 if frequency == "monthly" else 24
    if window.date.iloc[0] > cutoff + pd.Timedelta(days=tolerance_days):
        return None
    values = window.erp
    return {
        "sampleCount": count,
        "percentile": round(float(values.le(values.iloc[-1]).mean() * 100), 2),
        **{"p" + str(q): round(float(values.quantile(q / 100)), 4)
           for q in QUANTILES},
    }


def build_monthly_erp(pe, bond_yields):
    """Match genuine monthly CSI 500 PE observations to previous 10Y bond yield.

    The PE observations must be authentic month-end history (from the index
    valuation source). No interpolation, forward fill or manufactured PE data.
    """
    pe = _clean(pe, "pe")
    pe = pe[pe.pe > 0]
    yields = _clean(bond_yields, "y10")
    merged = pd.merge_asof(
        pe, yields, on="date", direction="backward",
        tolerance=pd.Timedelta(days=5)
    ).dropna(subset=["y10"])
    merged["erp"] = 100 / merged.pe - merged.y10
    output = _clean(merged, "erp")
    if len(output) < 115 or output.date.iloc[0] > pd.Timestamp("2007-05-31"):
        raise ValueError("月度中证500ERP历史不足，无法延长10年滚动分位带")
    return output


def build_history(erp_frame, frequency="weekly", source=None, long_term_monthly=None):
    """Weekly ERP with five HORIZONTAL valuation references per 3/5/10-year view.

    Reference quantiles are locked at the previous *completed calendar month*,
    so the five lines update once per month, not every trading day. Only real
    historical observations available at that cutoff enter the distribution.
    The displayed current ERP and its rank against that frozen distribution may
    update daily. Ten-year lines use a consistent monthly source when available.
    """
    if frequency not in ("weekly", "monthly"):
        raise ValueError("unsupported history frequency")
    src = _clean(erp_frame, "erp")
    if len(src) < 80:
        raise ValueError("ERP历史样本不足")
    last_date = src.date.iloc[-1]
    first_visible = last_date - pd.DateOffset(years=10)
    visible = src[src.date >= first_visible].copy()
    visible["period"] = visible.date.dt.to_period(
        "W-SUN" if frequency == "weekly" else "M"
    )
    display = visible.drop_duplicates("period", keep="last")
    if len(display) < 24:
        raise ValueError("历史走势图观测点不足")
    latest = float(src.erp.iloc[-1])
    legacy = None
    if long_term_monthly is not None:
        legacy = _clean(long_term_monthly, "erp")
        if len(legacy) < 180 or legacy.date.iloc[0] > pd.Timestamp("2007-05-31"):
            raise ValueError("10年历史月度数据不足")
        if (last_date - legacy.date.iloc[-1]).days > 36 or len(legacy) > 300:
            raise ValueError("10年历史月度数据过期或频率异常")

    # Previous month is always finished; do not move references mid-month.
    month_boundary = last_date.to_period("M").start_time
    month_end = month_boundary - pd.Timedelta(days=1)
    windows = {}
    for years in WINDOWS:
        active = legacy if years == 10 and legacy is not None else src
        basis = "monthly" if active is legacy else frequency
        available = active[active.date <= month_end]
        if available.empty or month_end - available.date.iloc[-1] > pd.Timedelta(days=40):
            raise ValueError(f"近{years}年参考线缺少上一完整月份数据")
        reference_date = available.date.iloc[-1]
        baseline = _window_asof(active, reference_date, years, basis)
        if baseline is None:
            raise ValueError(f"近{years}年完整历史样本不足")
        window = active[
            (active.date >= reference_date - pd.DateOffset(years=years)) &
            (active.date <= reference_date)
        ]
        # Rank today's ERP against the locked historical distribution; the
        # quantile lines remain unchanged until the next completed month.
        latest_rank = round(float(window.erp.le(latest).mean() * 100), 2)
        windows[str(years)] = {
            "from": str((reference_date - pd.DateOffset(years=years)).date()),
            "to": str(reference_date.date()),
            "referenceDate": str(reference_date.date()),
            "referenceMonth": str(reference_date.to_period("M")),
            "referenceMode": "上一个完整自然月的最后有效估值日；每月更新一次水平参考线",
            "percentile": latest_rank,
            "sampleCount": baseline["sampleCount"],
            **{f"p{q}": baseline[f"p{q}"] for q in QUANTILES},
            "basis": "月度真实观测" if basis == "monthly" else "日度真实观测",
            "source": ("乐咕乐股中证500月度PE及中国10年国债收益率"
                       if active is legacy else
                       ("中证指数官方日度PE及中国10年国债收益率"
                        if basis == "weekly" else
                        "月度历史PE及中国10年国债收益率")),
            "referenceERP": round(float(window.erp.iloc[-1]), 4),
        }
    ten = windows["10"]
    return {
        "version": 6,
        "metric": "csi500_erp",
        "unit": "%",
        "frequency": frequency,
        "reference": "水平分位线每月按上个完整月份末3/5/10年真实历史分别计算，当前ERP分位随最新数据变动；非历史逐点买卖信号",
        "source": source or (
            "中证指数官方日度滚动PE及中国10年国债收益率"
            if frequency == "weekly" else "月度滚动PE及中国10年国债收益率"
        ),
        "series": {
            "csi500": {
                "date": str(last_date.date()),
                "latest": round(latest, 4),
                "percentile": ten["percentile"],
                **{f"p{q}": ten[f"p{q}"] for q in QUANTILES},
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
