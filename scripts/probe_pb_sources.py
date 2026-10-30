import requests,re,json
from bs4 import BeautifulSoup
for code in ("399975","399998","399986"):
 url="https://guchacha.com/index-valuation/"+code
 try:
  r=requests.get(url,timeout=25,headers={"User-Agent":"Mozilla/5.0"})
  html=r.text
  soup=BeautifulSoup(html,"html.parser")
  print("CODE",code,"http",r.status_code,"length",len(html),flush=True)
  for idx,tag in enumerate(soup.find_all("script")):
   content=tag.string or tag.get_text() or ""
   print("SCRIPT",idx,tag.get("id"),tag.get("type"),"size",len(content),"src",str(tag.get("src"))[:100],
     "dates",len(re.findall(r"202[0-9][-/.][01][0-9][-/.][0-3][0-9]",content)),
     "pb matches",len(re.findall(r"\\bpb\\b|PB",content,flags=re.I)),flush=True)
   if len(content)>500:
    for word in ("__NUXT_DATA__","pbSeries","pbHistory","chartData","399975","399998","399986","2026-10-"):
     pos=content.find(word)
     if pos!=-1:print("NEAR",word,repr(content[max(0,pos-100):pos+300]),flush=True)
  text=soup.get_text(" ",strip=True)
  print("PAGE",repr(text[-250:]),flush=True)
 except Exception as e:print("ERROR",code,repr(e)[:200],flush=True)
