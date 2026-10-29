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
    """Build point-in-time monthly rolling bands for visible last 10 years.

    Daily 3y/5y bands never use future observations. Optional monthly 10y
    extension uses a consistent monthly PE source dating back to 2007. No
    interpolation and no mixing monthly with daily observations in a percentile.
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
    legacy = None
    if long_term_monthly is not None:
        legacy = _clean(long_term_monthly, "erp")
        if len(legacy) < 180 or legacy.date.iloc[0] > pd.Timestamp("2007-05-31"):
            raise ValueError("10年滚动带补全源的真实月度历史不足")
        if (last_date - legacy.date.iloc[-1]).days > 36:
            raise ValueError("10年滚动带补全源的最新数据已过期")
        if len(legacy) > 300:
            raise ValueError("长期补全源并非月度观测，拒绝混算")
    windows = {}
    for years in WINDOWS:
        active = legacy if years == 10 and legacy is not None else src
        basis = "monthly" if active is legacy else frequency
        current = _window_asof(active, active.date.iloc[-1], years, basis)
        if current is None:
            raise ValueError("当前近" + str(years) + "年有效估值样本不足")
        bands = []
        for anchor in anchors:
            # For 10-year monthly extension, an anchor is a genuine monthly
            # observation from the month-end provider, not an artificial date.
            if active is legacy:
                monthly_at_anchor = active.loc[active.date <= anchor]
                if monthly_at_anchor.empty:
                    continue
                real_anchor = monthly_at_anchor.date.iloc[-1]
                if anchor - real_anchor > pd.Timedelta(days=35):
                    continue
            else:
                real_anchor = anchor
            stats = _window_asof(active, real_anchor, years, basis)
            if stats is None:
                continue  # Gap clearly visible, not an invented historical band.
            bands.append([
                str(real_anchor.date()),
                *[stats["p" + str(q)] for q in QUANTILES],
            ])
        windows[str(years)] = {
            "from": str((last_date - pd.DateOffset(years=years)).date()),
            "to": str(last_date.date()),
            **current,
            "basis": ("月度真实观测" if basis == "monthly" else "日度真实观测"),
            "source": ("乐咕乐股中证500月度PE及中国10年国债收益率"
                       if active is legacy else
                       ("中证指数官方日度PE及中国10年国债收益率"
                        if basis == "weekly" else "月度历史PE及中国10年国债收益率")),
            "referenceERP": round(float(active.erp.iloc[-1]), 4),
            "bands": bands,
            "bandsFrequency": "monthly",
            "availableFrom": bands[0][0] if bands else None,
        }
    current10 = windows["10"]
    return {
        "version": 5,
        "metric": "csi500_erp",
        "unit": "%",
        "frequency": frequency,
        "reference": "3/5年按日度观测，10年历史补全带按月度真实观测；不同频率不混合计算分位，且每个历史点只用过去数据",
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
