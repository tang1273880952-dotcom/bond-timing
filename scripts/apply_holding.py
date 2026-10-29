"""Only repository owner may commit holdings/watchlist Issue Forms submissions."""
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"a-share"/"data"/"holdings.json"
def block(body,label):
    escaped=re.escape(label)
    m=re.search(r"(?ms)^###\s*"+escaped+r"\s*$\n(.*?)(?=^###\s|\Z)",body)
    if not m:return ""
    t=m.group(1).strip()
    return "" if t in ("_No response_","无回复","None") else t.splitlines()[0].strip()
def main():
    event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf8"))
    sender=event["issue"]["user"]["login"]
    owner=os.environ.get("GITHUB_REPOSITORY_OWNER","")
    if sender.casefold()!=owner.casefold():
        raise SystemExit("رفض unauthorized issue owner mismatch")
    body=event["issue"].get("body") or ""
    action=block(body,"操作类型")
    code=block(body,"股票代码")
    if not re.fullmatch(r"(00|30|60|68)\d{4}",code):
        raise ValueError("仅支持沪深A股6位代码（00、30、60、68开头）")
    data=json.loads(FILE.read_text(encoding="utf-8"))
    data.setdefault("positions",[])
    data.setdefault("watch",[])
    oldpositions=data["positions"]
    watch={x["code"] if isinstance(x,dict) else x for x in data["watch"]}
    if action=="新增或更新持仓":
        try:
            cost=float(block(body,"买入成本（元/股）"))
            shares=int(block(body,"当前持仓股数"))
        except (ValueError,TypeError):
            raise ValueError("成本和持仓股数必须有效，股数为整数")
        if not 0<=cost<100000 or not 0<shares<100000000:
            raise ValueError("持仓成本或股数超过允许范围")
        oldpositions=[p for p in oldpositions if p["code"]!=code]
        oldpositions.append({"code":code,"cost":round(cost,4),"shares":shares})
        oldpositions.sort(key=lambda x:x["code"])
        watch.discard(code)
    elif action=="加入观察池":
        if not any(p["code"]==code for p in oldpositions):watch.add(code)
    elif action=="删除持仓":
        oldpositions=[p for p in oldpositions if p["code"]!=code]
    elif action=="移出观察池":
        watch.discard(code)
    else:
        raise ValueError("未找到有效操作类型: "+action)
    data["positions"]=oldpositions
    data["watch"]=sorted(watch)
    data["updatedAt"]=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    data["version"]=1
    FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("Holdings applied",action,code,"positions",len(oldpositions),"watch",len(watch))
if __name__=="__main__": main()
