import requests,re
from bs4 import BeautifulSoup
for code,slug in [("399975","zqgs"),("399998","zzmt"),("399986","zzyh")]:
 r=requests.get(f"https://baifenwei.com/index/{slug}/",timeout=18)
 s=BeautifulSoup(r.text,"html.parser").find_all("script")[3].get_text()
 print("CODE",code,"LEN",len(s),"prefix",repr(s[:1600]),flush=True)
 print("stats",[(a,len(re.findall(a,s))) for a in ['"pb":','"pb_pct":','"pb_value":','\\"pb\\":','\"series\"','"date"']])
 ix=s.find('"date"')
 print("first series",repr(s[max(ix-220,0):ix+500]),flush=True)
