import requests,re,json
from bs4 import BeautifulSoup
for code,slug in [("399975","zqgs"),("399998","zzmt"),("399986","zzyh")]:
 html=requests.get(f"https://baifenwei.com/index/{slug}/",timeout=20).text
 soup=BeautifulSoup(html,"html.parser")
 text=soup.get_text(" ",strip=True)
 for part in ['PB · 市净率','市净率','PB','最新交易日']:
  pos=text.find(part)
  print("FRAG",code,part,repr(text[max(0,pos-70):pos+140]),flush=True)
 js=soup.find_all("script")[3].get_text()
 start=js.find('var d=')+6;stop=js.find('];',start)+1
 rows=json.loads(js[start:stop])
 print("HISTORY",code,len(rows),rows[0],rows[-1], "last3",rows[-3:],flush=True)
