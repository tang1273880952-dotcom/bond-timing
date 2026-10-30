import re,requests
from bs4 import BeautifulSoup
paths=[
("baifenwei_securities","https://baifenwei.com/index/zqgs/"),
("baifenwei_coal","https://baifenwei.com/index/zzmt/"),
("baifenwei_bank","https://baifenwei.com/index/zzyh/"),
("etf_coal","https://etf.whatsid.me/indices/399998"),
("etf_bank","https://etf.whatsid.me/indices/399986"),
]
for name,url in paths:
 try:
  r=requests.get(url,timeout=18,headers={"User-Agent":"Mozilla/5.0"})
  html=r.text
  soup=BeautifulSoup(html,"html.parser")
  scripts=soup.find_all("script")
  print("SOURCE",name,"status",r.status_code,"bytes",len(html),"scripts",len(scripts),"202x dates",len(re.findall(r"202[0-9]-[01][0-9]-[0-3][0-9]",html)),"timestamp matches",len(re.findall(r"1[5-9][0-9]{11}",html)),flush=True)
  for i,t in enumerate(scripts):
   content=t.string or t.get_text() or ""
   if len(content)>300:
    print("SCRIPT",i,"id",t.get("id"),"type",t.get("type"),"size",len(content),
        "dates",len(re.findall(r"202[0-9]-[01][0-9]-[0-3][0-9]",content)),
        "around first 202x",repr(content[max(0,content.find("2026-")-60):content.find("2026-")+120]) if "2026-" in content else "none",flush=True)
 except Exception as e: print("SOURCE ERROR",name,repr(e)[:200],flush=True)
