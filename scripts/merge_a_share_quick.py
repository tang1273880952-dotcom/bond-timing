"""Merge independently computed quick snapshots into the newest GitHub dataset.
Prevents older in-flight GH Action runs from replacing a full-market snapshot
with a small fallback sample. No model scores are inferred here.
Usage: python scripts/merge_a_share_quick.py latest.json calculated.json merged.json
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Asia/Shanghai")
def read(path):
    try:
        obj=json.loads(Path(path).read_text(encoding="utf-8"))
        return obj if isinstance(obj.get("quotes"),dict) else {}
    except (OSError, ValueError, TypeError):
        return {}
def phase(row):
    name=str(row.get("name") or "")
    if row.get("isST") or "ST" in name.upper():return "风险警示"
    try: pe,pb=float(row["pe"]),float(row["pb"])
    except (ValueError,TypeError,KeyError):return "暂不入围"
    if pe<=0 or pb<=0:return "暂不入围"
    if pe>45 or pb>6:return "估值初筛未通过"
    if pe<1 or pb<.15:return "异常估值待核实"
    return "待财报复核"
def merge(old, new):
    left=old.get("quotes") or {}
    right=new.get("quotes") or {}
    united=dict(left)
    for c,item in right.items():
        if c not in united or (item.get("date") or "") >= (united[c].get("date") or ""):
            united[c]=item
    # Preserve verified full-market breadth even if a newer partial task ran
    # from an outdated checkout.
    baseline=old if len(left)>=len(right) else new
    latest=(old if (old.get("generatedAt") or "")>(new.get("generatedAt") or "") else new)
    universe=max(int((old.get("coverage") or {}).get("universe") or 0),
                 int((new.get("coverage") or {}).get("universe") or 0))
    for item in united.values():item["stage"]=phase(item)
    now=datetime.now(TZ)
    cutoff=(now.date()-timedelta(days=12)).isoformat()
    counts={"universe":universe,
            "everQuoted":len(united),
            "recentQuoted":sum((i.get("date") or "")>=cutoff for i in united.values()),
            "preselected":sum(i["stage"]=="待财报复核" for i in united.values()),
            "fullSnapshot":len(united)>=int(universe*.95) if universe else False,
            "source":"合并全市场行情与分批回填" if left and right else
                     (latest.get("coverage") or {}).get("source",""),
            "batchLimit":(latest.get("coverage") or {}).get("batchLimit")}
    attempts={**(old.get("attempts") or {}),**(new.get("attempts") or {})}
    return {"mode":"live" if united else "partial",
            "generatedAt":max(old.get("generatedAt") or "",new.get("generatedAt") or ""),
            "marketDate":max(old.get("marketDate") or "",new.get("marketDate") or ""),
            "coverage":counts,"cursor":len(united),"attempts":attempts,
            "quotes":united,
            "method":latest.get("method") or baseline.get("method") or "A股最新PE/PB初筛；财务和长期PB另行复核。",
            "sources":latest.get("sources") or baseline.get("sources") or []}
if __name__=="__main__":
    if len(sys.argv)!=4:raise SystemExit("usage: merge_a_share_quick.py latest calculated merged")
    obj=merge(read(sys.argv[1]),read(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Safe quick merge:",obj["coverage"],flush=True)
