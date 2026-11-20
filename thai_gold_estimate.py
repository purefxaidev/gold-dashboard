#!/usr/bin/env python3
"""PureGold Next-Gen Thai gold pricing: AI-estimated Thai gold price (96.5% bar).

Inputs (all real, timestamped):
  * XAU/USD spot  : spot.json written by spot.py (Swissquote BBO mid; gold-api fallback)
  * COMEX GC      : Yahoo Finance GC=F (front contract, reference only; free feed may lag)
  * USD/THB       : Yahoo Finance THB=X (1-minute bars)
  * Official rows : thai_gold.json written by thai_gold.py (ราคาประกาศ)

Model:
  theoretical_thb = XAU * USDTHB * 15.244 * 0.965 / 31.1034768   (THB per baht-weight, 96.5%)
  est_mid         = theoretical_thb * ratio
  ratio           = median(official_mid / theoretical_thb) over recent calibration samples
                    (samples only where the official print and the spot tick are <= 10 min apart)
  est_buy/sell    = est_mid -/+ spread/2, rounded to the 50-baht grid used by announcements
Weekend / market-closed model: hold the last close, band = median |Monday open - Friday close|
of COMEX gold over the past 52 weeks (computed from real daily bars).

Accuracy: every time a NEW official print appears we compare it with the estimate we published
before the print (<= 15 min old). Stats start from the first run; nothing is backfilled.
Outputs: thai_gold_estimate.json (public), thai_gold_calib.json, thai_gold_accuracy.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BKK = timezone(timedelta(hours=7))
UTC = timezone.utc
F = 15.244 * 0.965 / 31.1034768  # troy oz of fine gold in one baht-weight of 96.5% bar
UA = {"User-Agent": "Mozilla/5.0 (compatible; PUREGOLD/1.0; +https://gold.purefxai.store/)"}
Y_THB = "https://query1.finance.yahoo.com/v8/finance/chart/THB=X?interval=1m&range=1d"
Y_GC = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
Y_GC_D = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1y"
MAX_SAMPLES = 60
WINDOW = 20  # most recent samples used for the ratio


def now() -> datetime:
    return datetime.now(BKK)


def http_json(url: str, timeout: int = 12):
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1.0)
    raise err


def load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(BKK).isoformat(timespec="seconds") if dt else None


def parse_dt(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=BKK)
    except ValueError:
        return None


def yahoo_last(url: str) -> dict:
    j = http_json(url)
    r = j["chart"]["result"][0]
    m = r["meta"]
    ts = r.get("timestamp") or []
    closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    px, t = None, None
    for tt, c in zip(reversed(ts), reversed(closes)):
        if c:
            px, t = float(c), tt
            break
    if px is None:
        px, t = float(m["regularMarketPrice"]), int(m["regularMarketTime"])
    return {
        "price": round(px, 4),
        "t": datetime.fromtimestamp(int(t), tz=UTC),
        "symbol": m.get("symbol"),
        "exchange": m.get("fullExchangeName") or m.get("exchangeName"),
        "name": m.get("shortName") or m.get("longName"),
    }


def weekend_gap_pct(calib: dict) -> dict:
    """Median |Mon open - Fri close| / Fri close from 1y of COMEX daily bars (cached ~1 day)."""
    c = calib.get("weekend_gap") or {}
    t = parse_dt(c.get("computed_at"))
    if t and (now() - t) < timedelta(hours=20) and c.get("median_pct"):
        return c
    j = http_json(Y_GC_D)
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = [(datetime.fromtimestamp(ts, tz=UTC), o, cl) for ts, o, cl in zip(r["timestamp"], q["open"], q["close"]) if o and cl]
    gaps = []
    for (d0, _o0, c0), (d1, o1, _c1) in zip(rows, rows[1:]):
        if (d1 - d0).days >= 2 and d1.weekday() == 0:
            gaps.append(abs(o1 - c0) / c0 * 100)
    if not gaps:
        return c
    out = {
        "computed_at": iso(now()),
        "weeks": len(gaps),
        "median_pct": round(statistics.median(gaps), 3),
        "p80_pct": round(sorted(gaps)[int(len(gaps) * 0.8) - 1], 3),
        "source": "COMEX GC=F daily bars (Yahoo Finance), 1 year",
    }
    calib["weekend_gap"] = out
    return out


def market_state(spot_t: datetime | None, t_now: datetime) -> dict:
    """Spot gold trades Sun 22:00 UTC - Fri 22:00 UTC (US winter) with a daily break."""
    u = t_now.astimezone(UTC)
    wd = u.weekday()  # Mon=0
    weekend = (wd == 4 and u.hour >= 22) or wd == 5 or (wd == 6 and u.hour < 22)
    age = (t_now - spot_t).total_seconds() if spot_t else None
    if weekend:
        return {"open": False, "state": "weekend", "label_th": "ตลาดโลกปิด (วันหยุดสุดสัปดาห์)", "label_en": "Global market closed (weekend)"}
    if age is not None and age > 20 * 60:
        return {"open": False, "state": "break", "label_th": "ตลาดโลกพักการซื้อขาย", "label_en": "Global market paused"}
    return {"open": True, "state": "open", "label_th": "ตลาดโลกเปิด", "label_en": "Global market open"}


def round50(x: float) -> float:
    return round(x / 50.0) * 50.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot", default="spot.json")
    ap.add_argument("--thai", default="thai_gold.json")
    ap.add_argument("--calib", default="thai_gold_calib.json")
    ap.add_argument("--accuracy", default="thai_gold_accuracy.json")
    ap.add_argument("--out", action="append", default=[])
    a = ap.parse_args(argv)
    t_now = now()
    calib_p, acc_p = Path(a.calib), Path(a.accuracy)
    calib = load(calib_p, {"samples": []})
    acc = load(acc_p, {})
    spot = load(Path(a.spot), {})
    thai = load(Path(a.thai), {})

    xau = float(spot["price"])
    spot_t = parse_dt(spot.get("updated_utc")) or parse_dt(spot.get("fetched_at"))
    goldapi_px = None
    for s in spot.get("sources") or []:
        if s.get("name") == "gold-api" and s.get("ok"):
            goldapi_px = s.get("price")

    prev_doc = None
    for o in a.out:
        prev_doc = load(Path(o), None)
        if prev_doc:
            break
    try:
        thb = yahoo_last(Y_THB)
    except Exception as e:  # noqa: BLE001
        prev = (prev_doc or {}).get("inputs", {}).get("usdthb")
        if not prev:
            raise RuntimeError(f"USD/THB unavailable: {e}")
        thb = {"price": prev["price"], "t": parse_dt(prev["updated_at"]), "symbol": "THB=X", "exchange": "CCY", "name": "USD/THB"}
    try:
        gc = yahoo_last(Y_GC)
    except Exception:  # noqa: BLE001
        gc = None

    mkt = market_state(spot_t, t_now)
    theo = xau * thb["price"] * F

    bar = thai.get("bar") or {}
    o_buy, o_sell = bar.get("buy"), bar.get("sell")
    o_asof = parse_dt(thai.get("as_of"))
    o_rev = thai.get("revision")
    o_key = f"{thai.get('as_of')}#{o_rev}"

    # --- new calibration sample when a fresh official print aligns with a fresh spot tick
    samples = calib.setdefault("samples", [])
    if o_buy and o_sell and o_asof and spot_t and mkt["open"]:
        aligned = abs((o_asof - spot_t).total_seconds()) <= 600 and (t_now - o_asof) <= timedelta(minutes=15)
        if aligned and not any(s.get("key") == o_key for s in samples):
            mid = (o_buy + o_sell) / 2
            samples.append({
                "key": o_key, "as_of": iso(o_asof), "buy": o_buy, "sell": o_sell,
                "xau": xau, "usdthb": thb["price"], "ratio": round(mid / theo, 6), "origin": "live",
            })
    del samples[:-MAX_SAMPLES]
    recent = samples[-WINDOW:]
    if not recent:
        raise RuntimeError("no calibration samples")
    ratio = statistics.median(s["ratio"] for s in recent)
    spreads = [s["sell"] - s["buy"] for s in recent]
    spread = (o_sell - o_buy) if (o_buy and o_sell) else statistics.mode(spreads)
    resid = [abs((s["buy"] + s["sell"]) / 2 - s["xau"] * s["usdthb"] * F * ratio) for s in recent]
    resid_mae = statistics.mean(resid)

    est_mid_raw = theo * ratio
    est_buy = round50(est_mid_raw - spread / 2)
    est_sell = est_buy + spread
    if mkt["state"] == "weekend":
        try:
            wg = weekend_gap_pct(calib)
        except Exception:  # noqa: BLE001
            wg = calib.get("weekend_gap") or {}
        band = est_mid_raw * (wg.get("median_pct") or 0) / 100
        model = {"id": "weekend", "label_th": "โมเดลวันหยุด: ถือราคาปิดล่าสุดของตลาดโลก", "label_en": "Weekend model: last global close held",
                 "band_baht": round(band), "band_basis_th": f"ช่องว่างราคาเปิดวันจันทร์ (ค่ามัธยฐาน {wg.get('weeks', 0)} สัปดาห์) ±{wg.get('median_pct', 0)}%",
                 "weekend_gap": wg}
    else:
        model = {"id": "live" if mkt["open"] else "closed", "label_th": "โมเดลเรียลไทม์: XAU/USD × USD/THB × ค่าปรับเทียบ" if mkt["open"] else "ตลาดพัก: ใช้ราคาล่าสุดก่อนพัก",
                 "label_en": "Live model: XAU/USD × USD/THB × calibration" if mkt["open"] else "Market paused: last tick held",
                 "band_baht": round(max(resid_mae, 50)), "band_basis_th": "ค่าคลาดเคลื่อนเฉลี่ยของโมเดลกับราคาประกาศที่ใช้ปรับเทียบ"}

    dev = None
    if o_sell:
        dev = {"sell": est_sell - o_sell, "buy": est_buy - o_buy, "mid_raw": round(est_mid_raw - (o_buy + o_sell) / 2, 1),
               "pct": round((est_mid_raw - (o_buy + o_sell) / 2) / ((o_buy + o_sell) / 2) * 100, 3)}

    # --- accuracy: compare the estimate published before a NEW print with that print
    acc.setdefault("since", iso(t_now))
    acc.setdefault("events", [])
    last_key = acc.get("last_official_key")
    pend = acc.get("pending")
    if last_key is None:
        acc["last_official_key"] = o_key  # baseline, no backfill
    elif o_key != last_key and o_buy:
        acc["last_official_key"] = o_key
        pt = parse_dt((pend or {}).get("at"))
        if pend and pt and o_asof and pt <= o_asof + timedelta(minutes=5) and (o_asof - pt) <= timedelta(minutes=15):
            err_mid = (pend["buy"] + pend["sell"]) / 2 - (o_buy + o_sell) / 2
            acc["events"].append({
                "official_as_of": iso(o_asof), "revision": o_rev, "official_buy": o_buy, "official_sell": o_sell,
                "est_at": pend["at"], "est_buy": pend["buy"], "est_sell": pend["sell"], "est_mid_raw": pend.get("mid_raw"),
                "error_baht": err_mid, "error_raw_baht": round(pend.get("mid_raw", 0) - (o_buy + o_sell) / 2, 1), "model": pend.get("model"),
            })
            acc["events"] = acc["events"][-500:]
    acc["pending"] = {"at": iso(t_now), "buy": est_buy, "sell": est_sell, "mid_raw": round(est_mid_raw, 1), "model": model["id"]}
    ev = acc["events"]
    errs = [abs(e["error_baht"]) for e in ev]
    stats = {
        "since": acc["since"], "n": len(ev),
        "mae_baht": round(statistics.mean(errs), 1) if errs else None,
        "bias_baht": round(statistics.mean(e["error_baht"] for e in ev), 1) if ev else None,
        "exact_pct": round(sum(1 for x in errs if x < 1) / len(errs) * 100, 1) if errs else None,
        "within_50_pct": round(sum(1 for x in errs if x <= 50) / len(errs) * 100, 1) if errs else None,
        "within_100_pct": round(sum(1 for x in errs if x <= 100) / len(errs) * 100, 1) if errs else None,
        "recent": ev[-12:],
    }

    def age(t):
        return round((t_now - t).total_seconds()) if t else None

    doc = {
        "schema": 1,
        "generated_at": iso(t_now),
        "unit_th": "บาทละ (ทองคำแท่ง 96.5%)",
        "market": mkt,
        "inputs": {
            "xau": {"price": round(xau, 3), "bid": spot.get("bid"), "ask": spot.get("ask"), "kind": "REAL",
                    "source_th": "XAU/USD สปอต · Swissquote" if spot.get("src") == "swissquote" else "XAU/USD สปอต · gold-api",
                    "source_en": "XAU/USD spot · Swissquote" if spot.get("src") == "swissquote" else "XAU/USD spot · gold-api",
                    "updated_at": iso(spot_t), "age_s": age(spot_t), "browser_ref": {"name": "gold-api", "price": goldapi_px}},
            "comex": None if not gc else {"price": gc["price"], "kind": "REAL", "contract": gc.get("name"),
                    "source_th": "COMEX ฟิวเจอร์ส GC · Yahoo Finance", "source_en": "COMEX GC futures · Yahoo Finance",
                    "updated_at": iso(gc["t"]), "age_s": age(gc["t"]), "basis_vs_spot": round(gc["price"] - xau, 2)},
            "usdthb": {"price": round(thb["price"], 4), "kind": "REAL", "source_th": "USD/THB · Yahoo Finance", "source_en": "USD/THB · Yahoo Finance",
                       "updated_at": iso(thb["t"]), "age_s": age(thb["t"])},
        },
        "official": None if not o_sell else {
            "kind": "REAL", "label_th": "ราคาประกาศ", "label_en": "Announced", "source_th": "ราคาประกาศทองไทย",
            "bar_buy": o_buy, "bar_sell": o_sell, "change": bar.get("change"),
            "jewelry_buy": (thai.get("jewelry") or {}).get("buy"), "jewelry_sell": (thai.get("jewelry") or {}).get("sell"),
            "as_of": iso(o_asof), "revision": o_rev, "age_s": age(o_asof), "fetched_at": thai.get("fetched_at"),
        },
        "estimate": {
            "kind": "ESTIMATE", "label_th": "ราคาประเมิน AI", "label_en": "AI estimate",
            "bar_buy": est_buy, "bar_sell": est_sell, "mid_raw": round(est_mid_raw, 1), "theoretical_mid": round(theo, 1),
            "low": round50(est_mid_raw - model["band_baht"]) - spread / 2, "high": round50(est_mid_raw + model["band_baht"]) + spread / 2,
            "model": model, "computed_at": iso(t_now),
        },
        "calibration": {
            "ratio": round(ratio, 6), "premium_pct": round((ratio - 1) * 100, 3), "spread_baht": spread,
            "samples": len(recent), "first": recent[0]["as_of"], "last": recent[-1]["as_of"], "resid_mae_baht": round(resid_mae, 1),
            "formula_th": "XAU/USD × USD/THB × 0.47295 (15.244 กรัม × 96.5% ÷ 31.1035) × ค่าปรับเทียบ",
            "constant": round(F, 6),
        },
        "deviation": dev,
        "accuracy": stats,
        "disclaimer_th": "เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน ราคาประเมินไม่ใช่ราคาซื้อขายจริง",
    }
    calib["updated_at"] = iso(t_now)
    calib_p.write_text(json.dumps(calib, ensure_ascii=False, indent=1) + "\n")
    acc_p.write_text(json.dumps(acc, ensure_ascii=False, indent=1) + "\n")
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    for o in a.out or ["thai_gold_estimate.json"]:
        Path(o).parent.mkdir(parents=True, exist_ok=True)
        Path(o).write_text(text)
    print(f"est {est_buy}/{est_sell} (raw mid {est_mid_raw:.0f}) official {o_buy}/{o_sell} dev {dev and dev['sell']} "
          f"ratio {ratio:.5f} n={len(recent)} model={model['id']} acc_n={len(ev)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
