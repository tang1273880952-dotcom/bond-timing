"""A-share stage 1: broad, lightweight valuation scan, independent of deep PB.
Full-market Eastmoney snapshots are attempted; if unavailable, BaoStock fetches
only recent P/E, P/B and closing price for a rotating batch of companies.
No security receives a quality score at this stage.
"""
import hashlib
import json
import os
import re
import traceback
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"a-share"/"data"
DATA.mkdir(parents=True,exist_ok=True)
FILE=DATA/"quick.json"
STATUS=DATA/"quick_status.json"
TZ=ZoneInfo("Asia/Shanghai")
TODAY=datetime.now(TZ).date()
MAX_FAST=max(10,min(500,int(os.getenv("ASHARE_FAST_LIMIT","240"))))
UNIVERSE_FILE=DATA/"snapshot.json"

def numeric(x):
    try:
        f=float(x)
        return f if -1e20<f<1e20 else None
    except (TypeError,ValueError):return None

def code_ok(s):
    return re.fullmatch(r"(00|30|60|68)\d{4}",str(s)) is not None

def old_json(path, fallback):
    try:return json.loads(path.read_text(encoding="utf8"))
    except (ValueError,OSError):return fallback

def official_day():
    return TODAY.isoformat()

def is_ok(r):
    return (numeric(r.get("price")) is not None and r["price"]>0
            and numeric(r.get("pe")) is not None
            and numeric(r.get("pb")) is not None)

def preliminary(r):
    name=str(r.get("name") or "")
    pe=numeric(r.get("pe"))
    pb=numeric(r.get("pb"))
    if "ST" in name.upper():return "风险警示"
    if pe is None or pb is None or pe<=0 or pb<=0:return "暂不入围"
    if pe>45 or pb>6:return "估值初筛未通过"
    if pe<1 or pb<.15:return "异常估值待核实"
    return "待财报复核"

def snapshot_em():
    import akshare as ak
    candidates=[("东方财富全市场",ak.stock_zh_a_spot_em)]
    # Split-market endpoints sometimes work when all-market pagination fails.
    funcs=[(label,getattr(ak,name,None)) for label,name in (
      ("东方财富沪市","stock_sh_a_spot_em"),("东方财富深市","stock_sz_a_spot_em"))]
    for label,func in candidates:
        try:
            df=func()
            if len(df)<2000:raise ValueError("returned "+str(len(df)))
            return parse_em(df),label
        except Exception as exc:
            print("Bulk quote unavailable",label,str(exc)[:180],flush=True)
    partial=[]
    for label,func in funcs:
        if func is None:continue
        try:
            df=func()
            if len(df)<800:raise ValueError("returned "+str(len(df)))
            partial.append(df)
            print("Exchange-level bulk quote",label,len(df),flush=True)
        except Exception as exc:
            print("Exchange bulk quote unavailable",label,str(exc)[:180],flush=True)
    if len(partial)==2:
        import pandas as pd
        return parse_em(pd.concat(partial,ignore_index=True)),"东方财富沪深分市场"
    raise ValueError("No verified exchange-wide valuation snapshot")

def parse_em(df):
    out={}
    for _,row in df.iterrows():
        code=str(row.get("代码","")).zfill(6)
        if not code_ok(code):continue
        price=numeric(row.get("最新价"))
        pe=numeric(row.get("市盈率-动态"))
        pb=numeric(row.get("市净率"))
        if price is None or price<=0:continue
        out[code]={"code":code,"name":str(row.get("名称","")),"price":price,
           "pe":pe,"pb":pb,"date":official_day(),"source":"东方财富",
           "peBasis":"动态市盈率（初筛）"}
    if len(out)<1800:raise ValueError("Bulk quote incomplete: "+str(len(out)))
    return out

def latest_bs(bs,code):
    raw=("sh." if code[0]=="6" else "sz.")+code
    rs=bs.query_history_k_data_plus(raw,
      "date,close,peTTM,pbMRQ,tradestatus,isST",
      start_date=(TODAY-timedelta(days=15)).isoformat(),
      end_date=TODAY.isoformat(),frequency="d",adjustflag="3")
    if rs.error_code!="0":return None
    cols=list(rs.fields)
    latest=None
    while rs.error_code=="0" and rs.next():
        vals=rs.get_row_data()
        latest=dict(zip(cols,vals))
    if not latest:return None
    price=numeric(latest.get("close"))
    if price is None or price<=0:return None
    return {"price":price,"pe":numeric(latest.get("peTTM")),
      "pb":numeric(latest.get("pbMRQ")),"date":latest["date"],
      "isST":str(latest.get("isST"))=="1",
      "peBasis":"TTM市盈率","source":"BaoStock"}

def main():
    previous=old_json(FILE,{"quotes":{},"cursor":0})
    quotes=previous.get("quotes",{})
    snapshot=old_json(UNIVERSE_FILE,{"universe":{},"stocks":[]})
    master=snapshot.get("universe") or {}
    if len(master)<2000:raise ValueError("No verified exchange-wide stock master yet")
    # Seed the short-history snapshot from previously verified spot observations,
    # without granting those companies preferential screening rank.
    for stock in snapshot.get("stocks",[]):
        c=stock.get("code")
        if c in master and c not in quotes and is_ok(stock):
            quotes[c]={"code":c,"name":master[c],"price":stock["price"],
              "pe":stock["pe"],"pb":stock["pb"],"date":stock.get("date"),
              "peBasis":"TTM市盈率","source":"BaoStock"}
    complete=False
    source="BaoStock分批估值"
    try:
        full,source=snapshot_em()
        quotes.update(full)
        complete=True
        print("FULL MARKET FOUND",len(full),flush=True)
    except Exception as exc:
        print("Switch to incremental light-quote backfill:",str(exc)[:180],flush=True)
        import baostock as bs
        login=bs.login()
        if login.error_code!="0":raise ValueError("BaoStock unavailable: "+login.error_msg)
        try:
            codes=sorted((c for c in master if code_ok(c)),
              key=lambda c:hashlib.sha256(("market-universe-2026:"+c).encode()).hexdigest())
            manual=old_json(DATA/"holdings.json",{"positions":[],"watch":[]})
            pinned={p["code"] for p in manual.get("positions",[]) if isinstance(p,dict)}
            pinned.update(w if isinstance(w,str) else w.get("code") for w in manual.get("watch",[]))
            pinned={c for c in pinned if c in master}
            # Remember attempts even when a quote source fails so the same
            # few delisted/illiquid codes do not block every subsequent batch.
            recent_attempts=previous.get("attempts") or {}
            cutoff=(TODAY-timedelta(days=5)).isoformat()
            recent_attempts={c:d for c,d in recent_attempts.items() if
                             isinstance(d,str) and d>=cutoff}
            fresh=[c for c in codes if c not in quotes and c not in recent_attempts]
            selected=list(sorted(pinned))[:MAX_FAST]
            selected+=fresh[:max(0,MAX_FAST-len(selected))]
            if len(selected)<MAX_FAST:
                stale=sorted((c for c in codes if c not in selected and c in quotes),
                   key=lambda c:(quotes[c].get("date") or "1970-01-01",c))
                selected+=stale[:MAX_FAST-len(selected)]
            updated=0
            for i,code in enumerate(selected,1):
                recent_attempts[code]=TODAY.isoformat()
                x=latest_bs(bs,code)
                if x:
                    quotes[code]={"code":code,"name":master[code],**x}
                    updated+=1
                if i%40==0:print("FAST backfill",i,"/",len(selected),"ok",updated,flush=True)
            print("FAST batch complete",len(selected),"success",updated,
                  "new before batch",len(fresh),flush=True)
        finally:bs.logout()
    valid={c:{**v,"name":master.get(c,v.get("name","未识别")),
       "stage":preliminary(v)} for c,v in quotes.items() if c in master and is_ok(v)}
    for c,v in valid.items():
        if v.get("isST"):v["stage"]="风险警示"
    # This is cumulative ever-quoted coverage, NOT all current-day quotes.
    freshness=(TODAY-timedelta(days=12)).isoformat()
    recent=sum(1 for v in valid.values() if (v.get("date") or "")>=freshness)
    preselected=sum(1 for v in valid.values() if v["stage"]=="待财报复核")
    data={"mode":"live" if valid else "partial",
          "generatedAt":datetime.now(TZ).isoformat(timespec="seconds"),
          "marketDate":max((v.get("date") for v in valid.values()),default=None),
          "coverage":{"universe":len(master),"everQuoted":len(valid),
                      "recentQuoted":recent,"preselected":preselected,
                      "fullSnapshot":complete,"source":source,
                      "batchLimit":MAX_FAST},
          "cursor":len(valid),"attempts":locals().get("recent_attempts",previous.get("attempts") or {}),"quotes":valid,
          "method":"仅最新价格、PE和PB的粗筛。PE来源可能为动态口径或TTM，不能跨口径直接排名；不含ROE、现金流、历史PB分位或综合评分。","sources":["AKShare Eastmoney spot","BaoStock daily valuations"]}
    FILE.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    print("QUICK success",data["coverage"],flush=True)
    return data

if __name__=="__main__":
    status={"attemptAt":datetime.now(TZ).isoformat(timespec="seconds")}
    try:
        d=main()
        status.update(success=True,coverage=d["coverage"])
    except Exception as exc:
        traceback.print_exc()
        status.update(success=False,error=str(exc))
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf8")
