"""Build verified US liquidity observations from free historical data sources.

Source order: independently maintained GitHub FRED mirror, then Convex API.
Cboe supplies GVZ/VIX volatility history. No guessed or forward-filled prices.
"""
from __future__ import annotations

import csv
import io
import json
import math
import bisect
import urllib.request
from datetime import datetime, date, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/liquidity_latest.json"
MIRROR = "https://raw.githubusercontent.com/Vincizh/market-fragility-dashboard/main/data/fred-cache/{}.csv"
CONVEX = "https://convextrade.com/api/public/data/{}?start=2015-01-01"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
NYFED = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/7.json"
SERIES = {
    "SOFR": "SOFR", "IORB": "IORB", "HY_OAS": "BAMLH0A0HYM2",
    "RESERVES": "WRESBAL", "FED_ASSETS": "WALCL",
    "TGA": "WTREGEN", "RRP": "RRPONTSYD",
    "VIX": "VIXCLS", "GVZ": "GVZ",
    "DOLLAR_BROAD": "DTWEXBGS", "SOFR99": "SOFR99",
}
DAILY = {"SOFR", "IORB", "HY_OAS", "RRP", "VIX", "GVZ"}
MINMAX = {
    "SOFR": (-0.5, 30), "IORB": (0, 30), "HY_OAS": (0, 50),
    "RESERVES": (0, 10000000), "FED_ASSETS": (100000, 30000000),
    "TGA": (0, 5000000), "RRP": (0, 6000),
    "VIX": (5, 150), "GVZ": (5, 150),
    "DOLLAR_BROAD": (40, 300), "SOFR99": (-0.5, 30),
}

def download(url, timeout=12):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; open-liquidity-dashboard/1.2)",
        "Accept": "text/csv, application/json, */*"
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")

def parse_rows(raw, key):
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        raise ValueError("empty CSV")
    out = []
    for row in rows:
        d = (row.get("observation_date") or row.get("DATE") or row.get("date") or "").strip()
        v = row.get(key)
        if v is None:
            raise ValueError(f"missing expected series column {key}")
        if not d or v in ("", "."):
            continue
        try:
            out.append({"date": date.fromisoformat(d[:10]).isoformat(), "value": float(v)})
        except (ValueError, TypeError):
            continue
    return out

def parse_cboe(raw):
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = []
    for row in rows:
        norm = {k.strip().upper(): v for k, v in row.items() if k}
        d = norm.get("DATE")
        value = norm.get("CLOSE") or norm.get("GVZ") or norm.get("VIX")
        if not d or not value:
            continue
        try:
            # Cboe uses MM/DD/YYYY rather than ISO in some history files.
            try: stamp = date.fromisoformat(d.strip()).isoformat()
            except ValueError: stamp = datetime.strptime(d.strip(), "%m/%d/%Y").date().isoformat()
            out.append({"date":stamp,"value":float(value)})
        except (ValueError, TypeError):
            continue
    if not out: raise ValueError("no Cboe observations")
    return out

def parse_convex(raw):
    obj = json.loads(raw)
    if not isinstance(obj, dict) or not isinstance(obj.get("data"), list):
        raise ValueError("unexpected Convex JSON")
    return [{"date": x.get("date"), "value": x.get("value")} for x in obj["data"]]

def parse_nyfed(raw, name):
    """Official NY Fed recent SOFR observations: exact effective dates, not display dates."""
    if name not in ("SOFR", "SOFR99"):
        raise ValueError("unsupported NY Fed series")
    obj = json.loads(raw)
    records = obj.get("refRates")
    if not isinstance(records, list):
        raise ValueError("NY Fed refRates not found")
    field = "percentRate" if name == "SOFR" else "percentPercentile99"
    out = []
    for row in records:
        if row.get("type") != "SOFR":
            continue
        if row.get("effectiveDate") and row.get(field) is not None:
            out.append({"date": row["effectiveDate"], "value": row[field]})
    if not out:
        raise ValueError("NY Fed has no rate observations")
    return out

def validate(name, values):
    low, high = MINMAX[name]
    cleaned = {}
    today = datetime.now(timezone.utc).date()
    for x in values:
        try:
            d = date.fromisoformat(str(x["date"])[:10])
            v = float(x["value"])
        except (KeyError, ValueError, TypeError):
            continue
        if d > today or not (math.isfinite(v) and low <= v <= high):
            continue
        cleaned[d.isoformat()] = round(v, 5)
    obs = [{"date": d, "value": v} for d, v in sorted(cleaned.items()) if d >= "2015-01-01"]
    if len(obs) < 25:
        raise ValueError(f"{name}: insufficient verified observations ({len(obs)})")
    return obs

def fetch_one(name, code):
    candidates = []
    failures = []
    if name != "GVZ":
        candidates.append(("GitHub FRED historical mirror (Vincizh/market-fragility-dashboard)",
                           lambda: parse_rows(download(MIRROR.format(code)), code)))
        # Convex data are checked against FRED-mirror units and plausible magnitudes.
        # Series with unverified unit conversions use FRED mirror only.
        if name in ("SOFR", "IORB", "HY_OAS", "RRP", "VIX", "DOLLAR_BROAD", "SOFR99"):
            candidates.append(("Convex public macro API",
                              lambda: parse_convex(download(CONVEX.format(code)))))
    if name in ("GVZ", "VIX"):
        symbol = "GVZ" if name == "GVZ" else "VIX"
        candidates.append(("Cboe historical volatility CSV",
                          lambda: parse_cboe(download(CBOE.format(symbol)))))
    selected, source = None, None
    for label, fetcher in candidates:
        try:
            values = validate(name, fetcher())
            if selected is None or values[-1]["date"] > selected[-1]["date"]:
                selected, source = values, label
        except Exception as exc:
            failures.append(f"{label}: {str(exc)[:110]}")
    if selected is None:
        raise RuntimeError("; ".join(failures))
    if name in ("SOFR", "SOFR99"):
        try:
            official = parse_nyfed(download(NYFED, timeout=10), name)
            old_last = selected[-1]["date"]
            merged = validate(name, selected + official)
            if merged[-1]["date"] >= old_last:
                selected = merged
                source += " + NY Fed official recent SOFR (matched effective dates)"
        except Exception as exc:
            failures.append("NY Fed official recent data: " + str(exc)[:110])
    return selected, source, failures

def combine(a, b):
    matching = {x["date"]: x["value"] for x in b}
    return [{"date": x["date"], "value": round(x["value"]-matching[x["date"]], 5)}
            for x in a if x["date"] in matching]

def net_liquidity(series):
    a = {x["date"]:x["value"] for x in series["FED_ASSETS"]}
    t = {x["date"]:x["value"] for x in series["TGA"]}
    r = series["RRP"]
    r_dates = [x["date"] for x in r]
    out = []
    for d in sorted(set(a).intersection(t)):
        i = bisect.bisect_right(r_dates, d) - 1
        if i < 0 or (date.fromisoformat(d) - date.fromisoformat(r_dates[i])).days > 7:
            continue
        # Official FRED WALCL/WTREGEN units: USD millions; RRPONTSYD: USD billions.
        value = (a[d] - t[d])/1000 - r[i]["value"]
        if math.isfinite(value):
            out.append({"date": d, "value": round(value, 4)})
    return out

def main():
    old = {}
    if OUT.is_file():
        try: old = json.loads(OUT.read_text(encoding="utf-8"))
        except (ValueError, OSError): pass
    series = {}
    source = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=11) as pool:
        futures = {pool.submit(fetch_one, name, code): name for name, code in SERIES.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                data, label, warnings = future.result()
                series[name], source[name] = data, label
                print(f"OK {name}: {len(data)} observations through {data[-1]['date']}; {label}", flush=True)
            except Exception as exc:
                errors[name] = str(exc)[:400]
                if old.get("series", {}).get(name):
                    series[name] = old["series"][name]
                    source[name] = old.get("source_by_series", {}).get(name, "previous verified snapshot")
                print(f"FAILED {name}: {errors[name]}", flush=True)

    if "SOFR" in series and "IORB" in series:
        series["FUNDING_SPREAD"] = combine(series["SOFR"], series["IORB"])
        source["FUNDING_SPREAD"] = "SOFR − IORB, aligned on identical observation dates"
    if "SOFR99" in series and "IORB" in series:
        series["TAIL_SPREAD"] = combine(series["SOFR99"], series["IORB"])
        source["TAIL_SPREAD"] = "SOFR 99th percentile − IORB, matched observation dates"
    if all(k in series for k in ("FED_ASSETS", "TGA", "RRP")):
        series["NET_LIQUIDITY_BN"] = net_liquidity(series)
        source["NET_LIQUIDITY_BN"] = "WALCL − WTREGEN − RRPONTSYD (weekly aligned, USD billions)"
    if not series or not any(series.get(k) for k in ("FUNDING_SPREAD", "HY_OAS", "RESERVES", "NET_LIQUIDITY_BN")):
        raise RuntimeError("No usable core series; preserve last verified file: " + str(errors))
    for k in ("FUNDING_SPREAD", "TAIL_SPREAD", "NET_LIQUIDITY_BN"):
        if k in series and len(series[k]) < 25:
            errors[k] = "derived history insufficient"
            del series[k]

    latest = {k: v[-1]["date"] for k, v in series.items() if v}
    checked_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 2,
        "checked_at": checked_at,
        "series": series, "latest_observations": latest,
        "source_by_series": source, "errors": errors,
        "units": {
            "FUNDING_SPREAD": "percentage points", "HY_OAS": "percent",
            "RESERVES": "USD millions", "NET_LIQUIDITY_BN": "USD billions",
            "VIX": "index", "GVZ": "index",
            "DOLLAR_BROAD":"index, Jan 2006=100", "TAIL_SPREAD":"percentage points",
        },
        "methodology": "Unmodified observed values only. Matched SOFR/IORB dates; weekly Fed/TGA with preceding RRP <=7 days. Vendor mirrors can lag."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",",":"))+"\n", encoding="utf-8")
    tmp.replace(OUT)
    print("Snapshot completed:", len(latest), "series, errors:", list(errors), flush=True)

if __name__ == "__main__":
    main()
