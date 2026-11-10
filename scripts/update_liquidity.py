"""Free FRED CSV liquidity snapshot. Never fabricate missing observations."""
import csv, io, json, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/liquidity_latest.json"
SERIES={"SOFR":"SOFR","IORB":"IORB","HY_OAS":"BAMLH0A0HYM2","RESERVES":"WRESBAL","FED_ASSETS":"WALCL","TGA":"WTREGEN","RRP":"RRPONTSYD","VIX":"VIXCLS","GVZ":"GVZCLS"}
def fetch(code):
    errors=[]
    # FRED graph endpoint sometimes stalls on GitHub Actions. Try a public
    # DBnomics FRED mirror when direct CSV access is unavailable.
    for source in ("fred", "dbnomics"):
        try:
            if source=="fred":
                url="https://fred.stlouisfed.org/graph/fredgraph.csv?id="+code+"&cosd=2015-01-01"
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req,timeout=10) as resp:
                    rows=list(csv.DictReader(io.StringIO(resp.read().decode("utf-8-sig"))))
                result=[]
                for row in rows:
                    try:
                        d=row.get("DATE") or row.get("observation_date")
                        v=float(row[code])
                        if d and v==v and abs(v)<1e12: result.append({"date":d,"value":v})
                    except (ValueError,TypeError,KeyError): pass
            else:
                url="https://api.db.nomics.world/v22/series/FRED/"+code+"?observations=1"
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=12) as resp:
                    obj=json.load(resp)
                series=obj["series"]["docs"][0]
                result=[]
                for d,v in zip(series["period"],series["value"]):
                    try:
                        v=float(v)
                        if v==v and abs(v)<1e12: result.append({"date":d,"value":v})
                    except (ValueError,TypeError): pass
            if result: return sorted(result,key=lambda x:x["date"])[-2600:]
            errors.append(source+": empty observations")
        except Exception as e: errors.append(source+": "+str(e)[:90])
    raise RuntimeError("; ".join(errors))
def combine(a,b,operation):
    bmap={x["date"]:x["value"] for x in b}
    return [{"date":x["date"],"value":round(operation(x["value"],bmap[x["date"]]),4)} for x in a if x["date"] in bmap]
def main():
    previous={}
    if OUT.exists():
        try: previous=json.loads(OUT.read_text())
        except (ValueError,OSError): pass
    series={};errors={}
    with ThreadPoolExecutor(max_workers=9) as pool:
        futures={pool.submit(fetch,code):name for name,code in SERIES.items()}
        for future in as_completed(futures):
            name=futures[future]
            try: series[name]=future.result()
            except Exception as e:
                errors[name]=str(e)[:250]
                if previous.get("series",{}).get(name): series[name]=previous["series"][name]
    if "SOFR" in series and "IORB" in series:
        series["FUNDING_SPREAD"]=combine(series["SOFR"],series["IORB"],lambda a,b:a-b)
    # Net liquidity uses last known weekly Fed assets/TGA and daily RRP; align weekly, forward-fill RRP only.
    if all(k in series for k in ("FED_ASSETS","TGA","RRP")):
        rrp=series["RRP"];tga={x["date"]:x["value"] for x in series["TGA"]}
        dates=sorted(set(x["date"] for x in series["FED_ASSETS"]) & set(tga))
        vals={x["date"]:x["value"] for x in series["FED_ASSETS"]}
        import bisect
        rd=[x["date"] for x in rrp];rv=[x["value"] for x in rrp]
        net=[]
        for d in dates:
            i=bisect.bisect_right(rd,d)-1
            if i>=0 and (datetime.fromisoformat(d)-datetime.fromisoformat(rd[i])).days<=7:
                # WALCL, WTREGEN are USD millions; RRPONTSYD is USD billions.
                net.append({"date":d,"value":round((vals[d]-tga[d])/1000-rv[i],3)})
        series["NET_LIQUIDITY_BN"]=net
    output={"checked_at":datetime.now(timezone.utc).isoformat(),"series":series,"errors":errors,"source":"FRED public graph CSV; ICE BofA HY OAS licensed source via FRED","units":{"FUNDING_SPREAD":"percentage points","HY_OAS":"percent","RESERVES":"USD millions","NET_LIQUIDITY_BN":"USD billions","VIX":"index","GVZ":"index"}}
    if not series: raise RuntimeError("All FRED and DBnomics endpoints unavailable; no snapshot published: "+str(errors))
    OUT.write_text(json.dumps(output,ensure_ascii=False,separators=(",",":"))+"\n")
    print("Updated:",list(series),"failed:",list(errors))
if __name__=="__main__": main()
