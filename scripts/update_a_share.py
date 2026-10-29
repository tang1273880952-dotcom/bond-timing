"""A-share daily candidate screener. No invented scores. Free-source, incremental.
Market-wide first stage uses AkShare snapshots; BaoStock supplies yearly financials and PB history
for a rotating subset. Incomplete firms are shown as unscored, not 'quality' picks.
"""
import json
import math
import os
import re
import hashlib
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from a_share_value_model import MODEL_VERSION,financial,quick_pass,quick_rank,rotation_key,evaluate

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"a-share"/"data"
OUT.mkdir(parents=True,exist_ok=True)
FILE=OUT/"snapshot.json"
STATUS=OUT/"status.json"
TODAY=datetime.now(ZoneInfo("Asia/Shanghai")).date()
MAX_FINANCIAL=int(os.environ.get("ASHARE_MAX_FINANCIAL","40"))
MAX_FALLBACK=int(os.environ.get("ASHARE_MAX_FALLBACK","70"))
# The screen must not preferentially select companies from past conversations.
# Only user-owned holdings/watchlist have a priority lane; the discovery lane
# rotates through the exchange-wide BaoStock security master.
# Financial sector recognition is implemented in a_share_value_model.
def val(v):
    try:
        if v is None or str(v).strip() in ("","--","nan","None","-"):return None
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None
def scale(x): # BaoStock financial ratios stored in decimal form
    return None if x is None else round(float(x)*100,2)
def clamp(x,lo=0,hi=100):return max(lo,min(hi,x))
def blank(code,name="未同步",prior=None):
    s={"code":code,"name":name,"price":None,"pe":None,"pb":None,
       "score":None,"qualityScore":None,"valuationScore":None,"growthScore":None,"riskScore":None,
       "roe":None,"growth":None,"cfoRatio":None,"debtRatio":None,
       "reportDate":None,"pubDate":None,"date":None,"pbPct":None,"flag":None,
       "financeModelVersion":None,"modelVersion":None,"eligible":False,"action":None,"reasons":[]}
    if prior:
        s.update(prior)
    return s
def baocode(code):return ("sh." if code[0]=="6" else "sz.")+code
def read_old():
    try:
        d=json.loads(FILE.read_text(encoding="utf8"))
        return d if isinstance(d.get("stocks"),list) else {"stocks":[],"history":{},"coverage":{}}
    except Exception:return {"stocks":[],"history":{},"coverage":{}}
def get_portfolio():
    try:
        d=json.loads((OUT/"holdings.json").read_text(encoding="utf8"))
        return {p["code"] for p in d.get("positions",[]) if isinstance(p,dict)} | {w if isinstance(w,str) else w["code"] for w in d.get("watch",[])}
    except Exception:return set()
def snapshot_all():
    import akshare as ak
    df=ak.stock_zh_a_spot_em()
    records={}
    for _,r in df.iterrows():
        code=str(r.get("代码","")).zfill(6)
        if not re.fullmatch(r"(00|30|60|68)\d{4}",code):continue
        name=str(r.get("名称",""))
        price=val(r.get("最新价"));pe=val(r.get("市盈率-动态"));pb=val(r.get("市净率"))
        if not price or price<=0:continue
        records[code]={"name":name,"price":price,"pe":pe,"pb":pb,
                       "marketCap":val(r.get("总市值")),"date":str(TODAY)}
    if len(records)<1000:raise ValueError("全市场快照不足1000只，疑似行情接口不完整")
    return records
def baodata(bs,code,fields,start,end):
    rs=bs.query_history_k_data_plus(baocode(code),fields,start_date=start,end_date=end,frequency="d",adjustflag="3")
    if rs.error_code!="0":
        print("History query failed",code,rs.error_code,str(rs.error_msg)[:140],flush=True)
        return pd.DataFrame()
    # BaoStock 0.9.x get_data() calls pandas.DataFrame.append, removed in
    # pandas >=2. Gather rows using the official iteration API instead.
    records=[]
    while rs.error_code=="0" and rs.next():
        records.append(rs.get_row_data())
    return pd.DataFrame(records,columns=rs.fields)
def get_latest_bs(bs,code):
    start=(TODAY-timedelta(days=16)).isoformat()
    df=baodata(bs,code,"date,close,peTTM,pbMRQ,isST",start,TODAY.isoformat())
    if df.empty:return None
    r=df.iloc[-1];p=val(r.get("close"))
    return {"price":p,"pe":val(r.get("peTTM")),"pb":val(r.get("pbMRQ")),"peBasis":"TTM市盈率","date":str(r.get("date")),"isST":str(r.get("isST"))=="1"} if p else None
def rows(bs,method,code,year,quarter):
    rs=getattr(bs,method)(code=baocode(code),year=year,quarter=quarter)
    if rs.error_code!="0":return None
    # BaoStock get_data() is incompatible with pandas 2+ / 3.x;
    # iterate records directly, matching the historical-price retrieval.
    record=None
    fields=list(rs.fields)
    while rs.error_code=="0" and rs.next():
        record=dict(zip(fields,rs.get_row_data()))
    if record is None:return None
    pub=record.get("pubDate","")
    if pub and pub>TODAY.isoformat():return None
    return record
def finance(bs,stock,code,old):
    # Profitability: last published FULL YEAR to keep ROE comparable across issuers
    annual=rows(bs,"query_profit_data",code,TODAY.year-1,4)
    cash=rows(bs,"query_cash_flow_data",code,TODAY.year-1,4)
    balance=rows(bs,"query_balance_data",code,TODAY.year-1,4)
    latest_growth=None
    latest_report=None
    for year,q in [(TODAY.year,3),(TODAY.year,2),(TODAY.year,1),(TODAY.year-1,4)]:
        r=rows(bs,"query_growth_data",code,year,q)
        if r:
            latest_growth=r;latest_report=r;break
    if not annual or not cash or not balance or not latest_growth:
        return
    pub=annual.get("pubDate","")
    if not pub or (TODAY-date.fromisoformat(pub)).days>600:
        return
    roe=scale(val(annual.get("roeAvg")));growth=scale(val(latest_growth.get("YOYNI")))
    cfo=val(cash.get("CFOToNP"))
    raw_debt=val(balance.get("liabilityToAsset"))
    equity_multiplier=val(balance.get("assetToEquity"))
    debt=scale(raw_debt)
    # Cross-check published ratios against the independent equity multiplier
    # rather than treating abnormally tiny liability percentages as accurate.
    if debt is not None and debt<1:
        via_multiplier=(100*(1-1/equity_multiplier)) if equity_multiplier and 1<=equity_multiplier<50 else None
        if via_multiplier is not None and 0<=via_multiplier<100:
            debt=round(via_multiplier,2)
            print("Debt ratio recovered via assetToEquity",code,raw_debt,equity_multiplier,debt,flush=True)
        else:
            print("Ambiguous liabilityToAsset units",code,raw_debt,"multiplier",equity_multiplier,flush=True)
            debt=None
    roes=[roe]
    for year in (TODAY.year-2,TODAY.year-3):
        y=rows(bs,"query_profit_data",code,year,4)
        if y:
            prev=scale(val(y.get("roeAvg")))
            if prev is not None:roes.append(prev)
    stock.update(roe=roe,growth=growth,cfoRatio=cfo,debtRatio=debt,
                 roeHistory=roes,financeModelVersion=MODEL_VERSION,
                 reportDate=str(latest_report.get("statDate") or ""),pubDate=str(latest_report.get("pubDate") or ""),
                 financeUpdated=str(TODAY))
def get_pb(bs,code,stock):
    # <= 10 years data; monthly downsample only for chart; quantiles use all traded days.
    start=(TODAY-timedelta(days=3653)).isoformat()
    df=baodata(bs,code,"date,close,pbMRQ",start,TODAY.isoformat())
    if df.empty or len(df)<150:return None
    df["pb"]=pd.to_numeric(df["pbMRQ"],errors="coerce")
    df["price"]=pd.to_numeric(df["close"],errors="coerce")
    df=df[(df.pb>0.05)&(df.pb<100)&(df.price>0)].copy()
    if len(df)<120:return None
    df["bps"]=df.price/df.pb
    if not ((df.bps>0).all()):return None
    q={key:float(df.pb.quantile(v)) for key,v in [("p10",.10),("p25",.25),("p50",.50),("p75",.75),("p90",.90)]}
    last=df.iloc[-1]
    if (TODAY-date.fromisoformat(str(last["date"]))).days>18:return None
    price=val(stock.get("price"))
    pb=val(stock.get("pb"))
    if price is None or pb is None or pb<=0:return None
    bps=price/pb
    # Use 1 historical point a month; source unadjusted price and contemporaneous BPS.
    df["month"]=pd.to_datetime(df.date).dt.to_period("M")
    monthly=df.drop_duplicates("month",keep="last")
    points=[]
    for _,r in monthly.iterrows():
        historical=df.loc[df["date"]<=r["date"],"pb"]
        item={"date":str(r["date"]),"price":round(float(r.price),3),
              "bps":round(float(r.bps),3)}
        if len(historical)>=60:
            for key,pctl in (("b10",.10),("b25",.25),("b50",.50),("b75",.75),("b90",.90)):
                item[key]=round(float(historical.quantile(pctl))*float(r.bps),3)
        points.append(item)
    pct=float((df.pb<=pb).mean()*100)
    return {**{k:round(v,4) for k,v in q.items()},
            "start":str(df.iloc[0]["date"]),"end":str(last["date"]),
            "samples":int(len(df)),"currentBps":round(bps,4),"pbPct":round(pct,1),
            "bandMethod":"rolling-history","points":points}
def rate(stock,h,q):
    stock.update(evaluate(stock,h,q,today=TODAY))
    if h and stock.get("eligible"):stock["pbPct"]=h["pbPct"]

def compute():
    import baostock as bs
    old=read_old()
    cache={s["code"]:blank(s["code"],s.get("name","未同步"),s) for s in old.get("stocks",[]) if re.fullmatch(r"\d{6}",s.get("code",""))}
    hist=old.get("history",{})
    manual=get_portfolio()
    oldcoverage=old.get("coverage",{})
    market_count=oldcoverage.get("market",0)
    # The independent fast-stage job already checks full-market valuations.
    # Avoid re-downloading all 5,000+ quotes for each deep-scoring run.
    spot={}
    spot_success=False
    print("Stage 2: reuse independent quick.json candidate pool",flush=True)
    login=bs.login()
    if login.error_code!="0":raise RuntimeError("BaoStock login failed: "+login.error_msg)
    try:
        # Obtain the full live listed-stock code universe, independent of the
        # 64 previously discussed names. BaoStock exposes security master fields.
        master = {}
        try:
            basic=bs.query_stock_basic()
            if basic.error_code!="0":
                raise ValueError("BaoStock security master: "+str(basic.error_msg))
            cols=list(basic.fields)
            required=("code","code_name")
            if not all(c in cols for c in required):
                raise ValueError("Missing stock-master fields: "+str(cols))
            while basic.error_code=="0" and basic.next():
                row=dict(zip(cols,basic.get_row_data()))
                raw=str(row["code"])
                if not raw.startswith(("sh.","sz.")):
                    continue
                code=raw[3:]
                if not re.fullmatch(r"(00|30|60|68)\d{4}",code):
                    continue
                if "type" in row and str(row["type"]) not in ("","1"):
                    continue
                if "status" in row and str(row["status"]) in ("0","-1"):
                    continue
                name=str(row["code_name"]).strip()
                if not name:
                    continue
                master[code]=name
            print("Full BaoStock listed A-share universe",len(master),flush=True)
        except Exception as exc:
            print("Security master unavailable:",str(exc)[:180],flush=True)
        if len(master)<2000:
            # Do not mislabel a small fallback sample as an all-A-share scan.
            master={c:v for c,v in (old.get("universe") or {}).items()
                    if re.fullmatch(r"(00|30|60|68)\d{4}",c)}
            print("Using previously verified security master",len(master),flush=True)
        industries={}
        try:
            ir=bs.query_stock_industry()
            if ir.error_code=="0":
                fields=list(ir.fields)
                while ir.error_code=="0" and ir.next():
                    row=dict(zip(fields,ir.get_row_data()))
                    c=str(row.get("code",""))
                    if c.startswith(("sh.","sz.")):
                        industries[c[3:]]=str(row.get("industry") or "")
        except Exception as e:
            print("Industry data unavailable",str(e)[:150],flush=True)
        for code,stock in cache.items():
            if stock.get("name") in ("未同步","",None) and code in master:
                stock["name"]=master[code]
            if industries.get(code):stock["industry"]=industries[code]
        for code,data in spot.items():
            stock=cache.get(code,blank(code,data["name"]))
            stock.update(data)
            cache[code]=stock
        # Stage 2 consumes only the Stage 1 light-valuation preselection.
        # No prior-conversation ticker list, no full ten-year downloads for every stock.
        fastpath=OUT/"quick.json"
        try:quick=json.loads(fastpath.read_text(encoding="utf8"))
        except (OSError,ValueError):quick={}
        rough=quick.get("quotes") or {}
        manual=sorted(c for c in manual if re.fullmatch(r"(00|30|60|68)\d{4}",c))
        earliest=(TODAY-timedelta(days=20)).isoformat()
        candidates=[c for c,q in rough.items()
                    if c in master and quick_pass(q)
                    and not financial(c,master[c],industries.get(c,""))
                    and q.get("date","")>=earliest]
        # If first-stage data is not yet populated, maintain existing verified
        # holdings and scores, but do not claim new broad-market discoveries.
        attempted={c:d for c,d in (old.get("scanAttempts") or {}).items()
                   if isinstance(d,str) and d<=str(TODAY)
                   and (TODAY-date.fromisoformat(d)).days<=12}
        unseen=[c for c in candidates if c not in attempted
                and (c not in cache or c not in hist)]
        unseen.sort(key=lambda c:(-quick_rank(rough[c]),c))
        explore=sorted(unseen,key=rotation_key)
        refresh=[c for c in candidates if c in cache and
                 (cache[c].get("financeModelVersion")!=MODEL_VERSION or c not in hist or
                  not cache[c].get("financeUpdated") or
                  (TODAY-date.fromisoformat(str(cache[c].get("financeUpdated") or "1970-01-01"))).days>=35)]
        refresh.sort(key=lambda c:cache[c].get("financeUpdated") or "1970-01-01")
        limit=MAX_FINANCIAL
        slots=max(0,limit-len(manual))
        # Holders > financial refresh > value opportunities > discovery rotation.
        refresh_slots=min(len(refresh),max(2,slots//5)) if slots else 0
        fresh_slots=max(0,slots-refresh_slots)
        explore_slots=max(1,fresh_slots//4) if fresh_slots else 0
        selected=unseen[:max(0,fresh_slots-explore_slots)]
        selected+= [c for c in explore if c not in selected][:explore_slots]
        todo=list(dict.fromkeys(manual+refresh[:refresh_slots]+selected))
        todo=todo[:limit]
        if len(todo)<limit:
            maintain=[c for c in cache if c not in todo and c in hist]
            maintain.sort(key=lambda c:cache[c].get("financeUpdated") or "1970-01-01")
            todo+=maintain[:limit-len(todo)]
        if not todo and not quick:
            todo=list(dict.fromkeys(manual))[:limit]
        for c in todo:
            attempted[c]=str(TODAY)
            cache.setdefault(c,blank(c,master.get(c,"未同步")))
        for c,v in cache.items():
            if c in master and v.get("name") in ("未同步","",None):v["name"]=master[c]
        print("Deep pipeline: first-stage eligible",len(candidates),
              "new",len(unseen),"prioritized holdings",len(manual),
              "selected",len(todo),flush=True)
        now_fin=0
        for idx,code in enumerate(todo,1):
            s=cache.setdefault(code,blank(code))
            if s.get("name") in ("未同步","",None) and code in master:
                s["name"]=master[code]
            if not spot_success or s.get("price") is None:
                quote=get_latest_bs(bs,code)
                if quote:s.update(quote)
            if industries.get(code):s["industry"]=industries[code]
            if s.get("price") is None:
                continue
            need_fin=(s.get("financeModelVersion")!=MODEL_VERSION or not s.get("financeUpdated") or (TODAY-date.fromisoformat(s["financeUpdated"])).days>20 or (val(s.get("debtRatio")) is not None and val(s.get("debtRatio"))<1))
            if need_fin:
                try:finance(bs,s,code,old);now_fin+=1
                except Exception as e:print("Financial partial failure",code,str(e)[:160],flush=True)
            # Download long PB history only after published fundamental checks.
            roe,growth,cfo,debt=(val(s.get(k)) for k in ("roe","growth","cfoRatio","debtRatio"))
            quality_gate=(None not in (roe,growth,cfo,debt) and
                          roe>=8 and growth>=-25 and cfo>=.8 and debt<=75
                          and len(s.get("roeHistory") or [])>=2)
            need_pb=(code in manual or quality_gate) and (
                code not in hist or hist[code].get("bandMethod")!="rolling-history"
                or hist[code].get("end")!=s.get("date")
                or (TODAY-date.fromisoformat(hist[code]["end"])).days>7)
            if need_pb:
                try:
                    h=get_pb(bs,code,s)
                    if h:hist[code]=h
                except Exception as e:print("PB history partial failure",code,str(e)[:160],flush=True)
            if idx%10==0:print("Processed",idx,"/",len(todo),flush=True)
        print("Financial updates attempted",now_fin,flush=True)
        for code,s in cache.items():
            if code in hist:
                h=hist[code]
                if val(s.get("pb")) is not None and h.get("currentBps") and (s.get("price") or 0)>0:
                    # Recalculate current PB percentile only when pb itself is recent (not old data).
                    s["pbPct"]=h["pbPct"] if h["end"]==s.get("date") else s.get("pbPct")
            q=rough.get(code)
            rate(s,hist.get(code),q if q and q.get("date","")>=earliest else {"stage":"过期"})
        # ensure old stale quotes aren't treated as live data
        for s in cache.values():
            dt=s.get("date")
            if dt:
                try:
                    if (TODAY-date.fromisoformat(str(dt))).days>15:
                        s.update(score=None,eligible=False,flag="行情数据超过15天",action="过期数据 · 暂停判断")
                except ValueError:s["score"]=None
        stocks=sorted(cache.values(),key=lambda s:s["code"])
        validated=[s for s in stocks if s.get("eligible") and s["score"] is not None and not s["flag"]]
        validated.sort(key=lambda s:s["score"],reverse=True)
        effective_count=sum(1 for s in stocks if val(s.get("price")) and val(s.get("pb")))
        data={"mode":"live" if validated else "partial",
              "generatedAt":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
              "marketDate":max((s.get("date") for s in stocks if s.get("date")),default=None),
              "coverage":{"market":len(master) if master else None,
                          "scanned":effective_count,"qualityVerified":len(validated),"ranking":min(20,len(validated)),
                          "fullQuoteSnapshot":spot_success,"batchSize":len(todo),
                          "pipeline":"粗筛 → 财务复核 → PB历史估值",
                          "coarseScanned":(quick.get("coverage") or {}).get("everQuoted",0),
                          "coarseQualified":len(candidates)},
              "universe":master,"scanAttempts":attempted,
              "stocks":stocks,"top":[s["code"] for s in validated[:20]],
              "history":hist,
              "method":"低估值优质股V2：PE≤35、PB≤4.5、PB历史分位≤35%、ROE≥8%、经营现金流/净利≥0.8、利润同比≥-25%、负债率≤75%、至少两年ROE；权重估值35%+质量35%+成长15%+风险15%；金融企业待独立建模。仅已核验样本排名。","sources":["AkShare Eastmoney A-share spot","BaoStock financial statements","BaoStock historical daily peTTM/pbMRQ"]}
        FILE.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf8")
        print("VALIDATED",len(validated),"quotes",effective_count,"universe",len(master),"top",data["top"],flush=True)
        return data
    finally:bs.logout()
def main():
    status={"attemptAt":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")}
    try:
        result=compute()
        status.update(success=True,marketDate=result["marketDate"],verified=result["coverage"]["qualityVerified"])
    except Exception as e:
        traceback.print_exc()
        status.update(success=False,error=str(e))
        print("Retaining prior market snapshot instead of fabricating scores",flush=True)
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf8")
    if not status.get("success"):raise SystemExit(1)
if __name__=="__main__":main()
