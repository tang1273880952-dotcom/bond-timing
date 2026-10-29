"""Daily bond, source-frequency stock valuation scores with strict freshness checks."""
import json
import traceback
from datetime import timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import akshare as ak
from history_chart import build_history, build_monthly_erp, official_csi500_erp, official_csi500_close, build_index_overlay, _clean
from bse50 import official_daily as fetch_bse50_daily, build_bse50

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)
CN_TZ = ZoneInfo("Asia/Shanghai")

def dated(frame):
    for field in ("日期", "date", "trade_date"):
        if field in frame.columns:
            x = frame.copy()
            x["date"] = pd.to_datetime(x[field], errors="coerce").dt.normalize()
            return x.dropna(subset=["date"])
    raise ValueError("缺失日期字段: "+str(list(frame.columns)))

def field(frame, exact, fragments):
    if exact in frame.columns:
        return exact
    for x in frame.columns:
        if all(t in str(x) for t in fragments) and not any(t in str(x) for t in ("等权", "中位数")):
            return x
    raise ValueError("缺失估值字段: "+str(list(frame.columns)))

def stock_valuations():
    p = dated(ak.stock_index_pe_lg(symbol="中证500"))
    b = dated(ak.stock_index_pb_lg(symbol="中证500"))
    pc = field(p, "滚动市盈率", ("滚动", "市盈率"))
    bc = field(b, "市净率", ("市净率",))
    p = p[["date", pc]].rename(columns={pc:"pe"})
    b = b[["date", bc]].rename(columns={bc:"pb"})
    p["pe"] = pd.to_numeric(p["pe"], errors="coerce")
    b["pb"] = pd.to_numeric(b["pb"], errors="coerce")
    p = p.dropna().query("pe > 0").drop_duplicates("date").sort_values("date")
    b = b.dropna().query("pb > 0").drop_duplicates("date").sort_values("date")
    print("PE records", len(p), p.date.min(), p.date.max(),flush=True)
    print("PB records", len(b), b.date.min(), b.date.max(),flush=True)
    return p, b

def china_yields(start, end):
    chunks=[]
    current=start
    while current<=end:
        finish=min(current+timedelta(days=330),end)
        data = dated(ak.bond_china_yield(start_date=current.strftime("%Y%m%d"),end_date=finish.strftime("%Y%m%d")))
        if "曲线名称" in data.columns:
            data=data[data["曲线名称"].astype(str).str.contains("中债国债收益率曲线",regex=False,na=False)]
        for col in ("1年","10年","30年"):
            if col not in data:
                raise ValueError("缺失国债期限字段 "+col)
        chunks.append(data[["date","1年","10年","30年"]].rename(columns={"1年":"y1","10年":"y10","30年":"y30"}))
        current=finish+timedelta(days=1)
    out=pd.concat(chunks,ignore_index=True)
    for c in ("y1","y10","y30"):out[c]=pd.to_numeric(out[c],errors="coerce")
    out=out.dropna().drop_duplicates("date",keep="last").sort_values("date")
    print("Bond yield records",len(out),out.date.min(),out.date.max(),flush=True)
    return out

def rank(frame,column,value,min_obs=80):
    values=pd.to_numeric(frame[column],errors="coerce").dropna()
    if len(values)<min_obs:
        raise ValueError(f"{column}有效历史记录只有{len(values)}条，少于{min_obs}")
    return round(float((values<=float(value)).mean()*100),2)

def calculate():
    now=datetime.now(CN_TZ)
    today=now.date()
    pe,pb=stock_valuations()
    y=china_yields(today-timedelta(days=12*366),today)
    if len(y)<1500:raise ValueError("长期国债历史不足: "+str(len(y)))
    y["s10"]=y.y10-y.y1
    y["s30"]=y.y30-y.y10
    y["d10"]=y.y10-y.y10.rolling(252,min_periods=120).mean()
    y["d30"]=y.y30-y.y30.rolling(252,min_periods=120).mean()
    # Match PE observation to most recently published yield (no more than 5 calendar days old).
    matched=pd.merge_asof(pe,y[["date","y10"]],on="date",direction="backward",tolerance=pd.Timedelta(days=5))
    matched=matched.dropna()
    matched["erp"]=100/matched.pe-matched.y10
    market_end=min(matched.date.max(),y.date.max())
    if (y.date.max()-matched.date.max()).days>7:
        raise ValueError("中证500 PE数据明显滞后: "+str(matched.date.max()))
    if (y.date.max()-pb.date.max()).days>40:
        raise ValueError("中证500 PB数据明显滞后: "+str(pb.date.max()))
    m=matched[matched.date<=market_end]
    last=m.iloc[-1]
    latest_bond=y.iloc[-1]
    latest_pb=pb[pb.date<=market_end].iloc[-1]
    stock_win=m[m.date>=market_end-pd.DateOffset(years=10)]
    pb_win=pb[(pb.date>=market_end-pd.DateOffset(years=10))&(pb.date<=market_end)]
    bond_win=y[y.date>=latest_bond.date-pd.DateOffset(years=10)]
    e=rank(stock_win,"erp",last.erp)
    p=rank(stock_win,"pe",last.pe)
    b=rank(pb_win,"pb",latest_pb.pb)
    b10=rank(bond_win,"y10",latest_bond.y10,500)
    b30=rank(bond_win,"y30",latest_bond.y30,500)
    dev10=rank(bond_win,"d10",latest_bond.d10,500)
    dev30=rank(bond_win,"d30",latest_bond.d30,500)
    s10=rank(bond_win,"s10",latest_bond.s10,500)
    s30=rank(bond_win,"s30",latest_bond.s30,500)
    stockscore=round(.5*e+.3*(100-p)+.2*(100-b))
    bond10score=round(.6*b10+.25*dev10+.15*s10)
    bond30score=round(.6*b30+.25*s30+.15*dev30)
    # Bootstrap true 20-year history once, then refresh only recent official PE
    # daily. Rolling 10y historical bands in 2016 require data back to 2006.
    cache_path=OUT/"csi500_erp_daily.csv"
    try:
        cached=None
        if cache_path.exists():
            cached=_clean(pd.read_csv(cache_path),"erp")
            if len(cached)<2400 or cached.date.min()>market_end-pd.DateOffset(years=11):
                cached=None
        if cached is None:
            history_start=market_end-pd.DateOffset(years=16)-pd.Timedelta(days=16)
            older_end=y.date.min()-pd.Timedelta(days=1)
            if older_end>=history_start:
                old_y=china_yields(history_start.date(),older_end.date())
                all_y=pd.concat([old_y,y],ignore_index=True)
            else:
                all_y=y
            raw_erp=official_csi500_erp(all_y,market_end,years=16)
            print("Official CSI500 historical bootstrap",len(raw_erp),flush=True)
        else:
            back_years=max(1,min(9,int((market_end-cached.date.max()).days/365.25+1.5)))
            recent=official_csi500_erp(y,market_end,years=back_years)
            raw_erp=_clean(pd.concat([cached,recent],ignore_index=True),"erp")
            raw_erp=raw_erp[raw_erp.date>=market_end-pd.DateOffset(years=20)]
            print("Official CSI500 cache refreshed",len(raw_erp),flush=True)
        # Use one consistent monthly source for the *entire* historical 10Y
        # percentile band. It begins in 2007, while daily CSI PE starts in 2011.
        # Do not silently combine monthly and daily observations in one ranking.
        monthly_cache=OUT/"csi500_erp_monthly.csv"
        long_term_monthly=None
        try:
            if monthly_cache.exists():
                old=_clean(pd.read_csv(monthly_cache),"erp")
                if len(old)<200 or old.date.min()>pd.Timestamp("2007-05-31"):
                    old=None
            else:
                old=None
            if old is None:
                old_start=pd.Timestamp("2007-01-01")
                if y.date.min()>old_start:
                    older_bonds=china_yields(
                        old_start.date(),(y.date.min()-pd.Timedelta(days=1)).date()
                    )
                    all_bonds=pd.concat([older_bonds,y],ignore_index=True)
                else:
                    all_bonds=y
                long_term_monthly=build_monthly_erp(pe,all_bonds)
                print("10Y genuine monthly ERP history bootstrapped",
                      len(long_term_monthly),flush=True)
            else:
                # Refresh observations covered by the regular 12-year yield feed.
                recent_pe=pe.loc[pe.date>=y.date.min()].copy()
                recent=pd.merge_asof(
                    recent_pe,y[["date","y10"]],on="date",
                    direction="backward",tolerance=pd.Timedelta(days=5)
                ).dropna(subset=["y10"])
                recent["erp"]=100/recent.pe-recent.y10
                if recent.empty:
                    raise ValueError("最近月度PE与国债收益率没有匹配数据")
                long_term_monthly=_clean(pd.concat([
                    old.loc[old.date<y.date.min(),["date","erp"]],
                    recent[["date","erp"]]
                ],ignore_index=True),"erp")
                print("10Y genuine monthly ERP history refreshed",
                      len(long_term_monthly),flush=True)
            if (market_end-long_term_monthly.date.max()).days>36:
                raise ValueError("10Y monthly valuation backfill is stale")
            if len(long_term_monthly)<200:
                raise ValueError("10Y monthly valuation backfill has too few samples")
        except Exception as ex:
            print("Monthly long-history backfill unavailable; keep valid shorter "
                  "daily rolling band:",repr(ex),flush=True)
            long_term_monthly=None
        history=build_history(
            raw_erp,frequency="weekly",long_term_monthly=long_term_monthly
        )
        if long_term_monthly is not None:
            long_term_monthly[["date","erp"]].to_csv(
                monthly_cache,index=False,float_format="%.7f"
            )
        # Commit cache only after all data validations have passed.
        raw_erp[["date","erp"]].to_csv(cache_path,index=False,float_format="%.7f")
        print("CSI500 weekly ERP and monthly-locked horizontal references",
              {k:{"referenceDate":v["referenceDate"],"sampleCount":v["sampleCount"]}
               for k,v in history["series"]["csi500"]["periods"].items()},
              flush=True)
    except Exception as exc:
        print("Official weekly ERP unavailable; using genuine monthly fallback:",
              repr(exc),flush=True)
        history=build_history(stock_win,frequency="monthly")
    # Independent optional overlay: index CLOSE only, never ETF price or ERP.
    # Kept separate so an index-price provider outage cannot break score updates.
    index_cache = OUT/"csi500_index_close_daily.csv"
    try:
        prior = _clean(pd.read_csv(index_cache), "close") if index_cache.exists() else None
        if prior is not None and (
            len(prior) < 1800 or prior.date.iloc[0] > market_end - pd.DateOffset(years=9)
        ):
            prior = None
        if prior is None:
            index_raw = official_csi500_close(market_end)
            print("Official CSI500 index CLOSE bootstrapped", len(index_raw), flush=True)
        else:
            refresh_from = max(
                market_end - pd.Timedelta(days=400),
                prior.date.iloc[-1] - pd.Timedelta(days=15)
            )
            recent_close = official_csi500_close(market_end, start=refresh_from)
            index_raw = _clean(
                pd.concat([prior, recent_close], ignore_index=True), "close"
            )
            index_raw = index_raw[
                index_raw.date >= market_end - pd.DateOffset(years=10) - pd.Timedelta(days=15)
            ]
            print("Official CSI500 index CLOSE refreshed", len(index_raw), flush=True)
        index_overlay = build_index_overlay(index_raw, market_end)
        history["series"]["csi500"]["indexClose"] = index_overlay
        index_raw[["date", "close"]].to_csv(
            index_cache, index=False, float_format="%.4f"
        )
        print("CSI500 index CLOSE weekly overlay",
              len(index_overlay["points"]), index_overlay["latest"], flush=True)
    except Exception as exc:
        print("CSI500 actual index CLOSE unavailable; overlay omitted:",
              repr(exc), flush=True)
        history["series"]["csi500"].pop("indexClose", None)
    # BSE50 is separate from the CSI500/China-bond allocation ranking.
    # Real published 899050 PE only; never fill missing valuations with guesses.
    bse_cache = OUT/"bse50_daily.csv"
    try:
        cached_bse = pd.read_csv(bse_cache) if bse_cache.exists() else None
        if cached_bse is not None:
            cached_bse["date"] = pd.to_datetime(cached_bse["date"],errors="coerce").dt.normalize()
            if len(cached_bse)<450 or (
                market_end-cached_bse.date.max()
            ).days > 90:
                cached_bse = None
        if cached_bse is None:
            bse_raw = fetch_bse50_daily(market_end)
        else:
            # Keep earlier authentic records, refresh the newest observations.
            recent = fetch_bse50_daily(market_end)
            bse_raw = pd.concat([cached_bse,recent],ignore_index=True)
            bse_raw = bse_raw.sort_values("date").drop_duplicates("date",keep="last")
        bse = build_bse50(bse_raw,y[["date","y10"]],market_end)
        bse_raw.to_csv(bse_cache,index=False,float_format="%.6f")
        print("BSE50 observation check",bse["valid"],len(bse.get("points",[])),
              bse.get("reason",""),flush=True)
    except Exception as exc:
        print("BSE50 unavailable; no synthetic ERP:",repr(exc),flush=True)
        bse={"valid":False,"code":"899050","name":"北证50",
             "reason":"官方北证50数据暂时无法验证，本期不展示猜测估值。",
             "source":"中证指数公司899050历史行情"}
    result = {
        "mode":"live",
        "dataDate":str(market_end.date()),
        "bondDataDate":str(latest_bond.date.date()),
        "stockPEDataDate":str(last.date.date()),
        "stockPBDataDate":str(latest_pb.date.date()),
        "generatedAt":now.isoformat(),
        "history":history,
        "bse50":bse,
        "assets":[
          {"id":"csi500","name":"中证500","score":stockscore,"metrics":[
            ["股债风险溢价",f"{last.erp:.2f}%"],
            ["PE-TTM",f"{last.pe:.2f}倍"],
            ["PB",f"{latest_pb.pb:.2f}倍"],
            ["PE观测日期",str(last.date.date())],
            ["PB观测日期",str(latest_pb.date.date())],
            ["ERP近10年分位",f"{e:.1f}%"]]},
          {"id":"bond10","name":"10年国债ETF","score":bond10score,"metrics":[
            ["10Y国债收益率",f"{latest_bond.y10:.3f}%"],
            ["收益率10年分位",f"{b10:.1f}%"],
            ["10Y-1Y期限利差",f"{latest_bond.s10:.3f}%"],
            ["与1年均值差",f"{latest_bond.d10:+.3f}%"]]},
          {"id":"bond30","name":"30年国债ETF","score":bond30score,"metrics":[
            ["30Y国债收益率",f"{latest_bond.y30:.3f}%"],
            ["收益率10年分位",f"{b30:.1f}%"],
            ["30Y-10Y期限利差",f"{latest_bond.s30:.3f}%"],
            ["与1年均值差",f"{latest_bond.d30:+.3f}%"]]}
        ],
        "model":"分开使用股票PE/PB实际观测频率和国债日度数据；历史分位比较不是短期收益预测。"
    }
    print("Score",[(a["name"],a["score"]) for a in result["assets"]],flush=True)
    return result

def main():
    status={"attemptAt":datetime.now(CN_TZ).isoformat()}
    try:
        result=calculate()
        (OUT/"latest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        status.update(success=True,dataDate=result["dataDate"])
    except Exception as exc:
        traceback.print_exc()
        status.update(success=False,error=str(exc))
        print("Last valid snapshot retained",flush=True)
    (OUT/"status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
