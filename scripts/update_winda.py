"""Wind All-A (881001.WI) genuine PE-TTM based ERP; no proxy substitution.

The named index must be explicitly supported by the provider.  The 'A股平均'
or '中证全指' PE is NOT the Wind All-A PE.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
CACHE=DATA/"winda_pe_daily.csv"
OUTPUT=DATA/"winda_latest.json"
STATUS=DATA/"winda_status.json"
WIND_CODE="881001.WI"
PE_PROVIDER="韭圈儿/基金估值数据库：万得全A历史市盈率（须核实PE口径）"
BOND_PROVIDER="中国中债10年国债到期收益率"
PCTS=(10,20,50,80,90)

def fetch_winda_pe():
    import akshare as ak
    # No approximate stand-ins: only the provider entry named 万得全A.
    source=ak.index_value_hist_funddb(symbol="万得全A",indicator="市盈率")
    return normalize_pe(source)

def normalize_pe(raw):
    if raw is None or raw.empty:
        raise ValueError("万得全A指数PE源为空")
    cols=list(raw.columns)
    date_col=next((c for c in ("日期","date","trade_date") if c in cols),None)
    pe_col=next((c for c in ("市盈率","pe_ttm","PE_TTM") if c in cols),None)
    if not date_col or not pe_col:
        raise ValueError("指数PE源缺少明确的市盈率列："+repr(cols))
    f=raw[[date_col,pe_col]].rename(columns={date_col:"date",pe_col:"pe"}).copy()
    f["date"]=pd.to_datetime(f.date,errors="coerce").dt.normalize()
    f["pe"]=pd.to_numeric(f.pe,errors="coerce")
    f=f.dropna().query("pe >= 5 and pe <= 120")
    f=f.sort_values("date").drop_duplicates("date",keep="last")
    if f.empty:raise ValueError("万得全A历史PE无有效记录")
    return f.reset_index(drop=True)

def normalize_yields(raw):
    if not {"date","y10"}.issubset(raw.columns):
        raise ValueError("缺少中国10年国债收益率")
    f=raw[["date","y10"]].copy()
    f["date"]=pd.to_datetime(f.date,errors="coerce").dt.normalize()
    f["y10"]=pd.to_numeric(f.y10,errors="coerce")
    return f.dropna().query("y10 >= 0 and y10 < 20").sort_values("date").drop_duplicates("date")

def build_winda(pe,bonds,today):
    p=normalize_pe(pe)
    y=normalize_yields(bonds)
    latest_pe=p.iloc[-1]
    today=pd.Timestamp(today).normalize()
    if (today-latest_pe.date).days>12:
        raise ValueError("万得全A PE过期: "+str(latest_pe.date.date()))
    # Compare only genuinely observed dates; no invented yield interpolation.
    joint=pd.merge_asof(p,y,on="date",direction="backward",tolerance=pd.Timedelta(days=5))
    joint=joint.dropna(subset=["y10"]).copy()
    joint["erp"]=100/joint.pe-joint.y10
    joint=joint.sort_values("date")
    if joint.empty:raise ValueError("万得全A PE与10年国债收益率无法匹配")
    last=joint.iloc[-1]
    if (today-last.date).days>12:raise ValueError("最新ERP失效")
    ref=(last.date.replace(day=1)-pd.Timedelta(days=1)).normalize()
    periods={}
    for yrs in (3,5,10):
        start=ref-pd.DateOffset(years=yrs)
        history=joint[(joint.date>=start)&(joint.date<=ref)]
        if (len(history)<yrs*150 or
            history.date.min()>start+pd.Timedelta(days=45) or
            history.date.max()<ref-pd.Timedelta(days=12)):
            continue
        levels={f"p{k}":round(float(history.erp.quantile(k/100)),4) for k in PCTS}
        percentile=round(float(history.erp.le(last.erp).mean()*100),2)
        periods[str(yrs)]={**levels,"percentile":percentile,
            "sampleCount":int(len(history)),
            "referenceDate":str(history.date.max().date()),
            "basis":"日度真实ERP"}
    if not periods:
        raise ValueError("可核验的3/5/10年ERP样本不足，不能绘制历史分位线")
    weekly=joint.groupby(joint.date.dt.to_period("W")).tail(1).copy()
    if weekly.date.iloc[-1]!=last.date:
        weekly=pd.concat([weekly,joint.tail(1)],ignore_index=True)
    weekly=weekly[weekly.date>=last.date-pd.DateOffset(years=10)-pd.Timedelta(days=7)]
    return {"valid":True,"code":WIND_CODE,"name":"万得全A",
        "metric":"ERP","date":str(last.date.date()),"peDate":str(latest_pe.date.date()),
        "pe":round(float(last.pe),4),"yield10":round(float(last.y10),4),
        "erp":round(float(last.erp),4),
        "sourcePE":PE_PROVIDER,"sourceYield":BOND_PROVIDER,
        "periods":periods,"points":[
            [str(row.date.date()),round(float(row.erp),4)]
            for row in weekly.itertuples()
        ],"note":"仅使用明确标注为万得全A的指数市盈率序列；来源口径须与Wind终端核对。"}

def main():
    DATA.mkdir(exist_ok=True)
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    old=None
    if OUTPUT.exists():
        try:
            x=json.loads(OUTPUT.read_text(encoding="utf-8"))
            if x.get("valid") is True:old=x
        except (OSError,ValueError):pass
    try:
        bonds=pd.read_csv(DATA/"china_yields_daily.csv")
        pe=fetch_winda_pe()
        # PE cache records only provider observations and never a guessed formula.
        result=build_winda(pe,bonds,now.date())
        pe.to_csv(CACHE,index=False,float_format="%.7f")
        status={"success":True,"updatedAt":now.isoformat(),
                "peDate":result["peDate"],"error":None}
        print("Wind All A ERP",result["date"],list(result["periods"]),flush=True)
    except Exception as e:
        msg=str(e)[:300]
        print("Wind All A unavailable:",repr(e),flush=True)
        # Keep previously verified data, including its original source timestamp.
        if old:
            result={**old,"stale":True,"note":"数据更新未成功，沿用上次已验证的历史值"}
        else:
            result={"valid":False,"code":WIND_CODE,"name":"万得全A",
                    "reason":"尚未获取到可核验的万得全A真实PE-TTM历史数据，不展示替代估值。",
                    "sourcePE":PE_PROVIDER}
        status={"success":False,"updatedAt":now.isoformat(),"error":msg}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":main()
