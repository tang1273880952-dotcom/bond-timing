"""Daily bond, source-frequency stock valuation scores with strict freshness checks."""
import json
import traceback
from datetime import timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import akshare as ak
from history_chart import build_history

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
    result = {
        "mode":"live",
        "dataDate":str(market_end.date()),
        "bondDataDate":str(latest_bond.date.date()),
        "stockPEDataDate":str(last.date.date()),
        "stockPBDataDate":str(latest_pb.date.date()),
        "generatedAt":now.isoformat(),
        "history":build_history(stock_win,bond_win),
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
