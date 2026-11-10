#!/usr/bin/env python3
"""Fetch XAUUSD FX spot (mid) from public feeds and write spot.json.

Primary: Swissquote public BBO (true FX spot mid).
Fallback: gold-api.com XAU (can drift a few dollars vs broker spot).
Never uses PAXG, XAUT, or gold futures as the displayed spot price.
Times are Asia/Bangkok.
"""
from __future__ import annotations

import json, time, urllib.request, datetime, sys
from zoneinfo import ZoneInfo

BKK = ZoneInfo("Asia/Bangkok")
UA = {"User-Agent": "Mozilla/5.0 (compatible; PUREGOLD/1.0; +https://dashboard.purefxai.store/)"}
TH_MONTHS = "ม.ค. ก.พ. มี.ค. เม.ย. พ.ค. มิ.ย. ก.ค. ส.ค. ก.ย. ต.ค. พ.ย. ธ.ค.".split()
EN_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

SQ_URL = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
GOLDAPI_URL = "https://api.gold-api.com/price/XAU"
YAHOO_XAU = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?interval=1m&range=1d"


def now_bkk() -> datetime.datetime:
    return datetime.datetime.now(BKK)


def fmt_th(dt: datetime.datetime) -> str:
    dt = dt.astimezone(BKK) if dt.tzinfo else dt.replace(tzinfo=BKK)
    return f"{dt.day} {TH_MONTHS[dt.month-1]} {dt.year} {dt.strftime('%H:%M')} น. (เวลาไทย)"


def fmt_en(dt: datetime.datetime) -> str:
    dt = dt.astimezone(BKK) if dt.tzinfo else dt.replace(tzinfo=BKK)
    return f"{EN_MONTHS[dt.month-1]} {dt.day}, {dt.year} {dt.strftime('%H:%M')} (Thai time)"


def http_json(url: str, timeout: int = 12):
    err = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(1.2)
    raise err


def _swissquote() -> dict:
    data = http_json(SQ_URL)
    mids, bid, ask, ts = [], None, None, None
    for block in data or []:
        ts = ts or block.get("ts")
        for p in block.get("spreadProfilePrices") or []:
            b, a = p.get("bid"), p.get("ask")
            if isinstance(b, (int, float)) and isinstance(a, (int, float)) and a >= b > 0:
                mids.append((b + a) / 2)
                # Prefer a tight elite/prime quote for bid/ask display
                if p.get("spreadProfile") in ("elite", "prime") or bid is None:
                    bid, ask = float(b), float(a)
    if not mids:
        raise ValueError("swissquote: no quotes")
    mid = sum(mids) / len(mids)
    when = datetime.datetime.fromtimestamp((ts or 0) / 1000, tz=datetime.timezone.utc) if ts else datetime.datetime.now(datetime.timezone.utc)
    return {
        "name": "swissquote",
        "price": round(mid, 3),
        "bid": round(bid, 3) if bid is not None else None,
        "ask": round(ask, 3) if ask is not None else None,
        "t": when,
        "ok": True,
    }


def _goldapi() -> dict:
    j = http_json(GOLDAPI_URL)
    px = float(j["price"])
    if px <= 0:
        raise ValueError("gold-api: bad price")
    raw = j.get("updatedAt")
    try:
        when = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        when = datetime.datetime.now(datetime.timezone.utc)
    return {"name": "gold-api", "price": round(px, 3), "bid": None, "ask": None, "t": when, "ok": True}


def _yahoo_xau() -> dict:
    j = http_json(YAHOO_XAU)
    meta = j["chart"]["result"][0]["meta"]
    px = float(meta.get("regularMarketPrice") or 0)
    if px <= 0:
        raise ValueError("yahoo: bad price")
    ts = meta.get("regularMarketTime")
    when = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) if ts else datetime.datetime.now(datetime.timezone.utc)
    return {"name": "yahoo-xauusd", "price": round(px, 3), "bid": None, "ask": None, "t": when, "ok": True}


SOURCES = (
    ("swissquote", _swissquote),
    ("gold-api", _goldapi),
)

LABELS = {
    "swissquote": ("สปอต FX · Swissquote", "FX spot · Swissquote"),
    "gold-api": ("สปอต · gold-api.com", "Spot · gold-api.com"),
    "yahoo-xauusd": ("สปอต · Yahoo XAUUSD", "Spot · Yahoo XAUUSD"),
    "cached": ("สปอต (แคชล่าสุด)", "Spot (last cache)"),
}


def _load_cache(path: str = "spot.json"):
    try:
        j = json.load(open(path, encoding="utf-8"))
        px = float(j.get("price") or 0)
        if px > 0:
            return j
    except Exception:
        pass
    return None


def fetch_spot(path: str = "spot.json", write: bool = True) -> dict:
    probed = []
    chosen = None
    for name, fn in SOURCES:
        try:
            row = fn()
            probed.append({"name": name, "price": row["price"], "ok": True})
            if chosen is None:
                chosen = row
            elif name != "swissquote" and chosen["name"] != "swissquote":
                pass
        except Exception as e:
            probed.append({"name": name, "price": None, "ok": False, "error": str(e)[:160]})
    now = now_bkk()
    if chosen is None:
        cache = _load_cache(path)
        if not cache:
            raise RuntimeError("all spot sources failed and no cache")
        cache = dict(cache)
        cache["stale"] = True
        cache["sources"] = probed
        cache["fetched_at"] = now.isoformat()
        if write:
            json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return cache

    th, en = LABELS.get(chosen["name"], (f"สปอต · {chosen['name']}", f"Spot · {chosen['name']}"))
    when = chosen["t"] if isinstance(chosen["t"], datetime.datetime) else now
    out = {
        "price": round(float(chosen["price"]), 3),
        "bid": chosen.get("bid"),
        "ask": chosen.get("ask"),
        "src": chosen["name"],
        "src_label_th": th,
        "src_label_en": en,
        "updated_utc": when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_th": fmt_th(when),
        "updated_en": fmt_en(when),
        "fetched_at": now.isoformat(),
        "stale": False,
        "sources": probed,
    }
    if write:
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


def main():
    try:
        s = fetch_spot()
    except Exception as e:
        print("spot failed:", e, file=sys.stderr)
        sys.exit(1)
    print(f"spot {s['price']} src={s['src']} {s['updated_th']} probes={s.get('sources')}")


if __name__ == "__main__":
    main()
