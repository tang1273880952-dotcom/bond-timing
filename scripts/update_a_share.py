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
FINANCIAL_WORDS=("银行","保险","证券","信托")
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
       "reportDate":None,"pubDate":None,"date":None,"pbPct":None,"flag":None}
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
    return {"price":p,"pe":val(r.get("peTTM")),"pb":val(r.get("pbMRQ")),"date":str(r.get("date")),"isST":str(r.get("isST"))=="1"} if p else None
def rows(bs,method,code,year,quarter):
    rs=getattr(bs,method)(code=baocode(code),year=year,quarter=quarter)
    if rs.error_code!="0":return None
    d=rs.get_data()
    if d.empty:return None
    record=d.iloc[-1].to_dict()
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
    stock.update(roe=roe,growth=growth,cfoRatio=cfo,debtRatio=debt,
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
    points=[{"date":str(r["date"]), "price":round(float(r.price),3),"bps":round(float(r.bps),3)} for _,r in monthly.iterrows()]
    pct=float((df.pb<=pb).mean()*100)
    return {**{k:round(v,4) for k,v in q.items()},
            "start":str(df.iloc[0]["date"]),"end":str(last["date"]),
            "samples":int(len(df)),"currentBps":round(bps,4),"pbPct":round(pct,1),
            "points":points}
def rate(stock,h):
    # Refuse to score if quality or valuation has missing data; ignore banks until sector model.
    stock["score"]=None
    stock["qualityScore"]=None
    stock["valuationScore"]=None
    stock["growthScore"]=None
    stock["riskScore"]=None
    stock["flag"]=None
    name=stock.get("name","")
    if "ST" in name.upper() or stock.get("isST"):
        stock["flag"]="ST或风险警示股";return
    if any(w in name for w in FINANCIAL_WORDS) or stock["code"][:3] in ("601",) and any(w in name for w in ("财险",)):
        stock["flag"]="金融企业需独立估值模型";return
    pe,pb=val(stock.get("pe")),val(stock.get("pb"))
    roe,growth,cfo,debt=(val(stock.get(k)) for k in ("roe","growth","cfoRatio","debtRatio"))
    if not h or None in (pe,pb,roe,growth,cfo,debt):return
    if pe<=0 or pb<=0 or roe<=0 or cfo<=0 or debt<0:return
    v=clamp(.6*(100-float(h["pbPct"]))+.4*clamp(100*(35-pe)/35))
    q=clamp(.68*clamp(roe*5)+.32*clamp(cfo*65))
    g=clamp((growth+30)*1.25)
    r=clamp(100-max(0,debt-45)*1.6)
    score=.35*v+.35*q+.20*g+.10*r
    stock.update(score=round(score),qualityScore=round(q),valuationScore=round(v),growthScore=round(g),riskScore=round(r))
    if roe<6 or growth< -30 or cfo<.65 or debt>78:
        stock["flag"]="ROE/增长/现金流/负债存在低质量风险"
    if stock["score"]<60:return
def compute():
    import baostock as bs
    old=read_old()
    cache={s["code"]:blank(s["code"],s.get("name","未同步"),s) for s in old.get("stocks",[]) if re.fullmatch(r"\d{6}",s.get("code",""))}
    hist=old.get("history",{})
    manual=get_portfolio()
    oldcoverage=old.get("coverage",{})
    market_count=oldcoverage.get("market",0)
    spot={}
    spot_success=False
    try:
        spot=snapshot_all()
        market_count=len(spot)
        spot_success=True
        print("All-market A-share quote snapshot",len(spot),flush=True)
    except Exception as exc:
        print("All-market API error; fallback to BaoStock selected stocks:",str(exc),flush=True)
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
        for code,stock in cache.items():
            if stock.get("name") in ("未同步","",None) and code in master:
                stock["name"]=master[code]
        for code,data in spot.items():
            stock=cache.get(code,blank(code,data["name"]))
            stock.update(data)
            cache[code]=stock
        manual=sorted(c for c in manual if re.fullmatch(r"(00|30|60|68)\d{4}",c))
        # Stable, shuffled order prevents a low-code / familiar-stock bias.
        # The first lane reserves the user's holdings, not their conversation history.
        candidates=[c for c in master if not ("ST" in master[c].upper())]
        if spot_success:
            # A full live snapshot allows a cheap valuation prefilter, without
            # removing stocks from the visible exchange-wide universe.
            candidates=[c for c in candidates if c in spot and
                        val(spot[c].get("pe")) is not None and 0<spot[c]["pe"]<=40 and
                        val(spot[c].get("pb")) is not None and 0<spot[c]["pb"]<=5]
        candidates.sort(key=lambda c:hashlib.sha256(("ashare-v3:"+c).encode()).hexdigest())
        recently_attempted=old.get("scanAttempts") or {}
        attempted={c:d for c,d in recently_attempted.items() if isinstance(d,str) and
                   (lambda x: (TODAY-x).days<=14 if x<=TODAY else False)(date.fromisoformat(d))}
        # 75% of each batch broadens the scanned universe, leaving some room
        # for maintaining previously validated data and user holdings.
        limit=MAX_FINANCIAL if spot_success else MAX_FALLBACK
        remaining=max(0,limit-len(manual))
        new_slots=max(0,int(remaining*.75))
        fresh=[c for c in candidates if c not in attempted and
               (c not in cache or
                (c not in hist and not cache[c].get("financeUpdated")))]
        refresh=[c for c in candidates if c not in attempted and c in cache and
                 (c not in hist or not cache[c].get("financeUpdated") or
                  (TODAY-date.fromisoformat(str(cache[c].get("date") or "1970-01-01"))).days>5)]
        # Never spend the whole daily budget repeatedly on the same initial 64.
        refresh.sort(key=lambda c:(0 if cache[c].get("score") is not None else 1,
                                   cache[c].get("financeUpdated",""),c))
        todo=list(dict.fromkeys(manual+fresh[:new_slots]+refresh))[:limit]
        if len(todo)<limit:
            more=[c for c in candidates if c not in todo and c not in attempted]
            todo+=more[:limit-len(todo)]
        # If full security-master access fails, only a known limited sample is
        # eligible; no claims are made about coverage of all listed companies.
        if not todo and not master:
            todo=list(dict.fromkeys(manual+list(cache)))[:limit]
        for code in todo:
            attempted[code]=str(TODAY)
            cache.setdefault(code,blank(code,master.get(code,"未同步")))
        for code,stock in cache.items():
            if code in master and stock.get("name") in ("未同步","",None):
                stock["name"]=master[code]
        print("Selection breadth: universe",len(master),"new",len(fresh[:new_slots]),
              "held",len(manual),"selected",len(todo),flush=True)
        now_fin=0
        for idx,code in enumerate(todo,1):
            s=cache.setdefault(code,blank(code))
            if s.get("name") in ("未同步","",None) and code in master:
                s["name"]=master[code]
            if not spot_success or s.get("price") is None:
                quote=get_latest_bs(bs,code)
                if quote:s.update(quote)
            if s.get("price") is None:
                continue
            need_fin=(not s.get("financeUpdated") or (TODAY-date.fromisoformat(s["financeUpdated"])).days>20 or (val(s.get("debtRatio")) is not None and val(s.get("debtRatio"))<1))
            if need_fin:
                try:finance(bs,s,code,old);now_fin+=1
                except Exception as e:print("Financial partial failure",code,str(e)[:160],flush=True)
            need_pb=code not in hist or (TODAY-date.fromisoformat(hist[code]["end"])).days>15
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
            rate(s,hist.get(code))
        # ensure old stale quotes aren't treated as live data
        for s in cache.values():
            dt=s.get("date")
            if dt:
                try:
                    if (TODAY-date.fromisoformat(str(dt))).days>15:s["score"]=None;s["flag"]="行情数据超过15天"
                except ValueError:s["score"]=None
        stocks=sorted(cache.values(),key=lambda s:s["code"])
        validated=[s for s in stocks if s["score"] is not None and not s["flag"]]
        validated.sort(key=lambda s:s["score"],reverse=True)
        effective_count=sum(1 for s in stocks if val(s.get("price")) and val(s.get("pb")))
        data={"mode":"live" if validated else "partial",
              "generatedAt":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
              "marketDate":max((s.get("date") for s in stocks if s.get("date")),default=None),
              "coverage":{"market":len(master) if master else None,
                          "scanned":effective_count,"qualityVerified":len(validated),"ranking":min(10,len(validated)),
                          "fullQuoteSnapshot":spot_success,"batchSize":len(todo)},
              "universe":master,"scanAttempts":attempted,
              "stocks":stocks,"top":[s["code"] for s in validated[:10]],
              "history":hist,
              "method":"仅沪深A股；全市场行情初筛与轮动核验财务；综合分=估值35%+质量35%+增长20%+风险10%。金融行业等待专用模型；没有报告或PB历史时不生成综合评分。","sources":["AkShare Eastmoney A-share spot","BaoStock financial statements","BaoStock historical daily peTTM/pbMRQ"]}
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
if __name__=="__main__":main()
