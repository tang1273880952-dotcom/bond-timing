import json,re,requests
urls={
"guchacha":"https://guchacha.com/index-valuation/399975",
"etf":"https://etf.whatsid.me/indices/valuation",
"lixinger":"https://www.lixinger.com/equity/index/detail/sz/399975/399975/fundamental/valuation/pb"}
for name,url in urls.items():
 try:
  r=requests.get(url,timeout=18,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
  s=r.text
  print(name,"status",r.status_code,"size",len(s),"doctype",s[:80].replace("\n"," "),flush=True)
  print(name,"next_data",bool(re.search("__NEXT_DATA__|__next_f|window.__NUXT__",s)),"script tags",s.lower().count("<script"),"mentions target",s.count("399975"),"series",s.lower().count("series"),flush=True)
  for key in ["__NEXT_DATA__", "data.pb", "pbHistory","valuationHistory","historicalPb","399975"]:
   ix=s.find(key)
   if ix>=0:print(name,"fragment",key,re.sub(r"\\s+"," ",s[max(0,ix-110):ix+220]),flush=True)
 except Exception as e:print(name,"ERROR",repr(e)[:200],flush=True)
