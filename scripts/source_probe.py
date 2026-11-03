"""Temporary connectivity probe for public S&P500 breadth and HY OAS. No secrets."""
import requests,json,datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
urls={
"breadth_raw":"https://raw.githubusercontent.com/DeanFinancials/deanfi-data/main/advance-decline/ma_percentage_historical.json",
"breadth_daily":"https://raw.githubusercontent.com/DeanFinancials/deanfi-data/main/advance-decline/daily_breadth.json",
"credit_convex_json":"https://convextrade.com/api/public/data/BAMLH0A0HYM2?start=2025-01-01",
"credit_convex_csv":"https://convextrade.com/api/public/data/BAMLH0A0HYM2?format=csv&start=2025-01-01",
"credit_convex_metrics":"https://convextrade.com/api/public/metrics/bamlh0a0hym2",
"credit_railway":"https://convex-trading-production.up.railway.app/api/public/data/BAMLH0A0HYM2?start=2025-01-01",
"credit_fred":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2025-01-01",
}
def test(name,url):
 try:
  r=requests.get(url,timeout=14,headers={"User-Agent":"Mozilla/5.0 (compatible; PublicMarketResearch/1.0)","Accept":"application/json,text/csv,*/*"})
  result={"status":r.status_code,"len":len(r.content),"content_type":r.headers.get("Content-Type",""),"snippet":r.text[:130].replace("\n"," ")}
  try:
   d=r.json()
   if name.startswith("breadth"):
    data=d.get("data",[])
    result.update(keys=list(d),count=len(data),last=data[-1] if isinstance(data,list) and data else (data.get("date") if isinstance(data,dict) else "n/a"),generated=d.get("metadata",{}).get("generated_at"))
   else:
    data=d.get("data",[])
    result.update(keys=list(d),count=len(data),latest=data[-1] if isinstance(data,list) and data else data,date=d.get("date"),value=d.get("value"))
  except:pass
  return name,result
 except Exception as exc:return name,{"error":type(exc).__name__,"message":str(exc)[:160]}
with ThreadPoolExecutor(max_workers=7) as pool:
 for f in as_completed([pool.submit(test,k,u) for k,u in urls.items()]):
  key,result=f.result()
  print("PROBE",key,json.dumps(result,ensure_ascii=False,default=str)[:1800],flush=True)
