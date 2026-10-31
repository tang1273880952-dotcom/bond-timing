import requests, re, json
from bs4 import BeautifulSoup
S=requests.Session(); H={"User-Agent":"Mozilla/5.0"}
for code in ["399975","399998","399986"]:
 for domain in ["guchacha","lixinger"]:
  if domain=="guchacha":
   urls=[f"https://guchacha.com/api/index/valuation/{code}",f"https://guchacha.com/index-valuation/{code}"]
  else:
   urls=[f"https://www.lixinger.com/equity/index/detail/sz/{code}/{code}/fundamental/valuation/pb"]
  for url in urls:
   try:
    r=S.get(url,headers=H,timeout=16)
    print("GET",code,domain,url,"HTTP",r.status_code,"LENGTH",len(r.content),flush=True)
    if "application/json" in r.headers.get("Content-Type",""):print("JSON",r.text[:500],flush=True)
    if domain=="guchacha" and "/index-valuation" in url and r.status_code==200:
     soup=BeautifulSoup(r.text,"html.parser");tag=soup.find("script",id="__NUXT_DATA__")
     if not tag:continue
     arr=json.loads(tag.string or tag.get_text())
     print("NUXT entries",len(arr),"dicts",sum(isinstance(v,dict) for v in arr),flush=True)
     for idx,v in enumerate(arr):
      if isinstance(v,dict) and any(re.search(r"pb|histor|series|chart|data|values|records|weekly|date|list",str(k),re.I) for k in v):
       keys=list(v.keys())
       print("OBJ",idx,"keys",keys[:35],"sample",str(v)[:350],flush=True)
      if isinstance(v,list) and len(v)>120:
       print("ARR",idx,"size",len(v),"sample",str(v[:4])[:240],flush=True)
   except Exception as e:print("ERROR",code,domain,type(e).__name__,str(e)[:180],flush=True)
