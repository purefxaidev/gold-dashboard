#!/usr/bin/env python3
"""Automatic short-term gold bias + self-learning feedback loop.

Deterministic: log each forecast, score matured forecasts vs later spot,
compute rolling 7d/30d accuracy, and update per-signal weights + probability
calibration. Optional short TH/EN prose via OPENROUTER_API_KEY (never required).
Writes history/predictions.jsonl, history/weights.json, history/accuracy.json
and updates analysis fields in data.json (no portfolio / P&L).
"""
from __future__ import annotations

import json, math, os, re, sys, time, urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone

from spot import BKK, fmt_en, fmt_th, now_bkk, fetch_spot

ROOT = Path(".")
PRED_PATH = ROOT / "history" / "predictions.jsonl"
WEIGHTS_PATH = ROOT / "history" / "weights.json"
ACC_PATH = ROOT / "history" / "accuracy.json"
HORIZON_MIN = 240  # 4-hour forecast horizon
MOVE_USD = 1.5
MIN_W, MAX_W = 0.2, 2.0
DEFAULT_WEIGHTS = {
    "mtf_net": 1.15,
    "mtf_m15": 0.55,
    "mtf_h1": 1.00,
    "mtf_h4": 0.85,
    "mtf_d1": 0.70,
    "rsi_m15": 0.45,
    "rsi_h1": 0.50,
    "ema_h1": 0.80,
    "smc_choch_h1": 0.75,
    "smc_bos_h1": 0.70,
    "smc_zone": 0.30,
}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "nvidia/nemotron-3.5-super-vl:free"


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _parse_ts(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            t = datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") or s.endswith("Z") else s, fmt.replace("Z", "+0000") if "Z" in fmt else fmt)
            if t.tzinfo is None:
                t = t.replace(tzinfo=BKK)
            return t.astimezone(BKK)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(BKK)
    except Exception:
        return None


def load_weights():
    w = _load_json(WEIGHTS_PATH, {})
    sigs = dict(DEFAULT_WEIGHTS)
    stored = w.get("signals") if isinstance(w.get("signals"), dict) else w
    for k, default in DEFAULT_WEIGHTS.items():
        row = stored.get(k) if isinstance(stored, dict) else None
        if isinstance(row, dict) and isinstance(row.get("weight"), (int, float)):
            sigs[k] = float(row["weight"])
        elif isinstance(row, (int, float)):
            sigs[k] = float(row)
        else:
            sigs[k] = float(default)
        sigs[k] = max(MIN_W, min(MAX_W, sigs[k]))
    cal = w.get("calibration") if isinstance(w.get("calibration"), dict) else {}
    slope = float(cal.get("slope", 1.0) or 1.0)
    intercept = float(cal.get("intercept", 0.0) or 0.0)
    stats = stored if isinstance(stored, dict) else {}
    return sigs, {"slope": max(0.4, min(1.3, slope)), "intercept": max(-8, min(8, intercept))}, stats


def trend_sign(t):
    return 1.0 if t == "up" else -1.0 if t == "down" else 0.0


def rsi_signal(rsi):
    if rsi is None:
        return 0.0
    # Oversold -> lean up, overbought -> lean down, scaled.
    return max(-1.0, min(1.0, (50.0 - float(rsi)) / 30.0))


def smc_dir(obj):
    if not obj:
        return 0.0
    d = str(obj.get("dir") or obj or "").lower()
    if "bull" in d or d in ("up", "buy"):
        return 1.0
    if "bear" in d or d in ("down", "sell"):
        return -1.0
    return 0.0


def extract_signals(d, price=None):
    mtf = {m["tf"]: m for m in (d.get("mtf") or []) if isinstance(m, dict) and m.get("tf")}
    ups = sum(1 for m in mtf.values() if m.get("trend") == "up")
    dns = sum(1 for m in mtf.values() if m.get("trend") == "down")
    net = (ups - dns) / 5.0
    h1 = mtf.get("H1") or {}
    px = price or d.get("price_num")
    ema_h1 = 0.0
    if px and h1.get("ema20") and h1.get("ema50"):
        if px > h1["ema20"] > h1["ema50"]:
            ema_h1 = 1.0
        elif px < h1["ema20"] < h1["ema50"]:
            ema_h1 = -1.0
        elif px > h1["ema20"]:
            ema_h1 = 0.35
        elif px < h1["ema20"]:
            ema_h1 = -0.35
    smc = ((d.get("smc") or {}).get("XAUUSD") or {}).get("H1") or {}
    zone = smc.get("zone") or {}
    zname = str(zone.get("name") or "")
    zone_s = 0.4 if zname == "discount" else -0.4 if zname == "premium" else 0.0
    return {
        "mtf_net": round(net, 4),
        "mtf_m15": trend_sign((mtf.get("M15") or {}).get("trend")),
        "mtf_h1": trend_sign((mtf.get("H1") or {}).get("trend")),
        "mtf_h4": trend_sign((mtf.get("H4") or {}).get("trend")),
        "mtf_d1": trend_sign((mtf.get("D1") or {}).get("trend")),
        "rsi_m15": round(rsi_signal((mtf.get("M15") or {}).get("rsi")), 4),
        "rsi_h1": round(rsi_signal((mtf.get("H1") or {}).get("rsi")), 4),
        "ema_h1": ema_h1,
        "smc_choch_h1": smc_dir(smc.get("choch")),
        "smc_bos_h1": smc_dir(smc.get("bos")),
        "smc_zone": zone_s,
    }


def combine(signals, weights, cal):
    num = den = 0.0
    parts = []
    for k, s in signals.items():
        w = float(weights.get(k, DEFAULT_WEIGHTS.get(k, 0.5)))
        num += w * s
        den += w
        parts.append((k, w, s, w * s))
    score = (num / den) if den else 0.0
    raw = 50.0 + 45.0 * math.tanh(score * 1.15)
    up = raw * cal["slope"] + cal["intercept"]
    up = max(15.0, min(85.0, up))
    up_i = int(round(up))
    dn_i = 100 - up_i
    return score, up_i, dn_i, parts


def load_preds():
    rows = []
    if not PRED_PATH.exists():
        return rows
    for line in PRED_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def save_preds(rows):
    PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    # keep a bounded log
    rows = rows[-4000:]
    PRED_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def ema(a, n):
    k = 2 / (n + 1)
    out, e = [], None
    for x in a:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(a, n=14):
    if len(a) < n + 2:
        return None
    g = l = 0
    for i in range(1, n + 1):
        d = a[i] - a[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    g /= n
    l /= n
    for i in range(n + 1, len(a)):
        d = a[i] - a[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
    return round(100 - 100 / (1 + g / l), 1) if l else 100.0


def trend_close(c):
    if len(c) < 55:
        return "sideways", None, None, None
    e20, e50 = ema(c, 20), ema(c, 50)
    sl = e20[-1] - e20[-6]
    t = "up" if e20[-1] > e50[-1] and sl > 0 and c[-1] > e20[-1] else "down" if e20[-1] < e50[-1] and sl < 0 and c[-1] < e20[-1] else "sideways"
    return t, rsi(c), e20[-1], e50[-1]


def signals_from_candles(C, i_h1):
    """Walk-forward signals using only bars up to index i_h1 on H1, plus M15/H4/D1 available at that time."""
    def upto(tf, t_end, n=120):
        rows = [x for x in (C.get(tf) or []) if x[0] <= t_end]
        return rows[-n:]

    h1 = (C.get("H1") or [])
    if i_h1 < 55 or i_h1 >= len(h1):
        return None, None
    t_end = h1[i_h1][0]
    px = h1[i_h1][4]
    mtf = {}
    for tf in ("M5", "M15", "H1", "H4", "D1"):
        rows = upto(tf, t_end)
        closes = [x[4] for x in rows]
        t, r, e20, e50 = trend_close(closes)
        mtf[tf] = {"tf": tf, "trend": t, "rsi": r, "ema20": e20, "ema50": e50}
    fake = {"mtf": list(mtf.values()), "smc": {}, "price_num": px}
    return extract_signals(fake, px), px


def score_row(row, exit_px, move_usd=MOVE_USD):
    entry = float(row["price"])
    move = exit_px - entry
    up_pct = int(row.get("up_pct") or 50)
    if abs(move) < move_usd:
        return "flat", move, None
    actual = "up" if move > 0 else "down"
    pred = "up" if up_pct >= 55 else "down" if up_pct <= 45 else "neutral"
    if pred == "neutral":
        return "flat", move, None
    hit = pred == actual
    return actual, move, hit


def backfill_and_score(C, weights):
    """Walk-forward 4h forecasts on H1 history to bootstrap accuracy + weights."""
    h1 = C.get("H1") or []
    if len(h1) < 80:
        return [], dict(weights), {"slope": 1.0, "intercept": 0.0}, {k: {"hit": 0, "n": 0} for k in DEFAULT_WEIGHTS}
    # 4h horizon ≈ 4 H1 bars
    step = 2
    horizon_bars = max(1, HORIZON_MIN // 60)
    records = []
    # start with defaults; update online
    w = dict(DEFAULT_WEIGHTS)
    cal = {"slope": 1.0, "intercept": 0.0}
    stats = {k: {"hit": 0, "n": 0} for k in DEFAULT_WEIGHTS}
    for i in range(60, len(h1) - horizon_bars, step):
        sig, px = signals_from_candles(C, i)
        if not sig or not px:
            continue
        _, up, dn, _ = combine(sig, w, cal)
        exit_px = h1[i + horizon_bars][4]
        row = {"price": px, "up_pct": up, "signals": sig, "t_unix": h1[i][0]}
        actual, move, hit = score_row(row, exit_px)
        t = datetime.fromtimestamp(h1[i][0], tz=timezone.utc).astimezone(BKK)
        rec = {
            "t": t.strftime("%Y-%m-%d %H:%M"),
            "price": round(px, 3),
            "up_pct": up,
            "down_pct": dn,
            "horizon_min": HORIZON_MIN,
            "source": "backfill",
            "exit_price": round(exit_px, 3),
            "move": round(move, 3),
            "actual": actual,
            "hit": hit,
        }
        records.append(rec)
        if hit is None:
            continue
        actual_sign = 1 if actual == "up" else -1
        for k, s in sig.items():
            if abs(s) < 0.15:
                continue
            agree = (s * actual_sign) > 0
            stats[k]["n"] += 1
            stats[k]["hit"] += 1 if agree else 0
        # slow online weight update
        for k, st in stats.items():
            if st["n"] >= 8:
                rate = st["hit"] / st["n"]
                target = max(MIN_W, min(MAX_W, 0.35 + 1.4 * rate))
                w[k] = round(0.85 * w[k] + 0.15 * target, 4)
        # calibration from recent 40 scored
        scored = [r for r in records if r["hit"] is not None][-40:]
        if len(scored) >= 16:
            acc = sum(1 for r in scored if r["hit"]) / len(scored)
            cal["slope"] = max(0.4, min(1.3, 0.7 + (acc - 0.5)))
    return records, w, cal, stats


def apply_live_scores(preds, spot_px, now, weights, cal, stats_in):
    w = dict(weights)
    cal = dict(cal)
    stats = {k: dict(v) if isinstance(v, dict) else {"hit": 0, "n": 0} for k, v in (stats_in or {}).items()}
    for k in DEFAULT_WEIGHTS:
        stats.setdefault(k, {"hit": 0, "n": 0})
        stats[k].setdefault("hit", 0)
        stats[k].setdefault("n", 0)
    changed = 0
    for row in preds:
        if row.get("hit") is not None or row.get("source") == "backfill":
            continue
        mature = _parse_ts(row.get("mature_at")) or (
            (_parse_ts(row.get("t")) or now) + timedelta(minutes=int(row.get("horizon_min") or HORIZON_MIN))
        )
        if now < mature:
            continue
        # Prefer a later logged price if we stored marks; else current spot (first time we see it matured).
        exit_px = float(row.get("exit_price") or spot_px)
        actual, move, hit = score_row(row, exit_px)
        row["exit_price"] = round(exit_px, 3)
        row["move"] = round(move, 3)
        row["actual"] = actual
        row["hit"] = hit
        row["scored_at"] = now.strftime("%Y-%m-%d %H:%M")
        changed += 1
        if hit is None:
            continue
        actual_sign = 1 if actual == "up" else -1
        for k, s in (row.get("signals") or {}).items():
            if k not in stats or abs(float(s)) < 0.15:
                continue
            stats[k]["n"] = int(stats[k].get("n") or 0) + 1
            if (float(s) * actual_sign) > 0:
                stats[k]["hit"] = int(stats[k].get("hit") or 0) + 1
    for k, st in stats.items():
        n = int(st.get("n") or 0)
        if n >= 8:
            rate = int(st.get("hit") or 0) / n
            target = max(MIN_W, min(MAX_W, 0.35 + 1.4 * rate))
            w[k] = round(0.8 * float(w.get(k, DEFAULT_WEIGHTS.get(k, 1))) + 0.2 * target, 4)
    live_scored = [r for r in preds if r.get("source") != "backfill" and r.get("hit") is not None]
    if len(live_scored) >= 12:
        acc = sum(1 for r in live_scored[-40:] if r["hit"]) / max(1, len(live_scored[-40:]))
        cal["slope"] = max(0.4, min(1.3, 0.7 + (acc - 0.5)))
    return preds, w, cal, stats, changed


def accuracy_from(rows, now):
    def window(days):
        cut = now - timedelta(days=days)
        xs = []
        for r in rows:
            if r.get("hit") is None:
                continue
            t = _parse_ts(r.get("t")) or _parse_ts(r.get("scored_at"))
            if t and t >= cut:
                xs.append(r)
        n = len(xs)
        if n == 0:
            return None, 0
        return round(100.0 * sum(1 for r in xs if r["hit"]) / n, 1), n

    a7, n7 = window(7)
    a30, n30 = window(30)
    return {"acc_7d": a7, "n_7d": n7, "acc_30d": a30, "n_30d": n30}


def fmt_pct(p):
    return "—" if p is None else f"{p:.0f}%" if float(p).is_integer() else f"{p}%"


def swings(rows, w=3):
    hi, lo = [], []
    for i in range(w, len(rows) - w):
        if rows[i][2] == max(x[2] for x in rows[i - w:i + w + 1]):
            hi.append(rows[i][2])
        if rows[i][3] == min(x[3] for x in rows[i - w:i + w + 1]):
            lo.append(rows[i][3])
    return hi, lo


def levels(price, C):
    h1 = (C.get("H1") or [])[-120:]
    h4 = (C.get("H4") or [])[-80:]
    hi, lo = swings(h1 or h4)
    res = sorted({round(x, 1) for x in hi if x > price + 0.8})[:4]
    sup = sorted({round(x, 1) for x in lo if x < price - 0.8}, reverse=True)[:4]
    # also add recent H4 swings
    h4hi, h4lo = swings(h4, w=2) if h4 else ([], [])
    for x in h4hi:
        x = round(x, 1)
        if x > price + 0.8 and x not in res:
            res.append(x)
    for x in h4lo:
        x = round(x, 1)
        if x < price - 0.8 and x not in sup:
            sup.append(x)
    res = sorted(res)[:3]
    sup = sorted(sup, reverse=True)[:3]
    # round-number fallbacks
    rnd = round(price / 20) * 20
    if not res:
        res = [round(price + 12, 1), round(price + 22, 1)]
    if not sup:
        sup = [round(price - 12, 1), round(price - 22, 1)]
    return res, sup, rnd


def f2(n):
    return f"{n:,.1f}" if abs(n - round(n, 1)) < 1e-6 else f"{n:,.2f}"


def build_sr_text(res, sup):
    r_th, r_en, s_th, s_en = [], [], [], []
    tags_th = ("ต้านใกล้", "ต้านถัดไป", "ต้านไกล")
    tags_en = ("nearest resistance", "next resistance", "further resistance")
    st_th = ("แนวรับใกล้", "แนวรับถัดไป", "แนวรับไกล")
    st_en = ("nearest support", "next support", "further support")
    for i, x in enumerate(res):
        r_th.append(f"{f2(x)} ({tags_th[min(i,2)]})")
        r_en.append(f"{f2(x)} ({tags_en[min(i,2)]})")
    for i, x in enumerate(sup):
        s_th.append(f"{f2(x)} ({st_th[min(i,2)]})")
        s_en.append(f"{f2(x)} ({st_en[min(i,2)]})")
    return r_th, r_en, s_th, s_en


def ev_plans(price, res, sup, up_pct):
    atr = 8.0
    if res and sup:
        atr = max(5.0, min(18.0, (res[0] - sup[0]) * 0.55))
    p_up = up_pct / 100.0
    p_down = 1 - p_up
    plans = []
    if res:
        entry = float(res[0])
        sl = round(entry + max(4.5, atr * 0.7), 1)
        tp = round(min(entry - max(6.0, atr * 1.1), (sup[0] if sup else entry - 10)), 1)
        if tp < entry < sl:
            # shade p_win toward down-prob, slightly less at resistance if already extended
            pw = max(0.32, min(0.62, p_down * 0.9 + 0.05))
            plans.append({
                "name": f"SELL รีเทสต์ {f2(entry)}",
                "name_en": f"SELL retest {f2(entry)}",
                "side": "sell",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "p_win": round(pw, 2),
                "status": "รอราคากลับมาแตะต้านแล้วกลับตัว ไม่ไล่ขายกลางทาง",
                "status_en": "Wait for a retest of resistance and a turn; do not chase a mid-move sell",
            })
    if sup:
        entry = float(sup[0])
        sl = round(entry - max(4.5, atr * 0.7), 1)
        tp = round(max(entry + max(6.0, atr * 1.1), (res[0] if res else entry + 10)), 1)
        if sl < entry < tp:
            pw = max(0.32, min(0.62, p_up * 0.9 + 0.05))
            plans.append({
                "name": f"BUY รีเทสต์ {f2(entry)}",
                "name_en": f"BUY retest {f2(entry)}",
                "side": "buy",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "p_win": round(pw, 2),
                "status": "รอราคากลับมาแตะรับแล้วเด้ง ไม่ไล่ซื้อกลางทาง",
                "status_en": "Wait for a retest of support and a bounce; do not chase a mid-move buy",
            })
    return plans[:2]


def reason_lines(parts, d, up, dn):
    th, en = [], []
    mtf = d.get("mtf_align") or ""
    mtf_en = d.get("mtf_align_en") or ""
    order = sorted(parts, key=lambda x: abs(x[3]), reverse=True)
    # always include MTF summary
    side = "down" if dn > up else "up" if up > dn else "neutral"
    if mtf:
        th.append([side if abs(up - dn) >= 8 else "neutral", mtf])
        en.append([side if abs(up - dn) >= 8 else "neutral", mtf_en or mtf])
    labels = {
        "mtf_h1": ("H1 ตาม EMA", "H1 follows EMA"),
        "mtf_h4": ("H4 ตามแนวโน้ม", "H4 follows the trend"),
        "mtf_d1": ("D1 ตามแนวโน้ม", "D1 follows the trend"),
        "mtf_m15": ("M15 ตามแนวโน้ม", "M15 follows the trend"),
        "rsi_m15": ("RSI M15", "M15 RSI"),
        "rsi_h1": ("RSI H1", "H1 RSI"),
        "ema_h1": ("ราคาเทียบ EMA20/50 ชั่วโมง", "Price vs H1 EMA20/50"),
        "smc_choch_h1": ("H1 CHoCH", "H1 CHoCH"),
        "smc_bos_h1": ("H1 BOS", "H1 BOS"),
        "smc_zone": ("โซนพรีเมียม/ดิสเคานต์ H1", "H1 premium/discount zone"),
    }
    used = 0
    for k, w, s, contrib in order:
        if k == "mtf_net" or abs(s) < 0.2 or used >= 3:
            continue
        direc = "up" if s > 0 else "down"
        lab_th, lab_en = labels.get(k, (k, k))
        if k.startswith("rsi"):
            hint_th = " Oversold เอียงขึ้น" if s > 0 else " Overbought เอียงลง"
            hint_en = " oversold, lean up" if s > 0 else " overbought, lean down"
        elif k == "smc_zone":
            hint_th = " อยู่โซนถูก" if s > 0 else " อยู่โซนแพง"
            hint_en = " in discount" if s > 0 else " in premium"
        elif k.startswith("smc"):
            hint_th = " ขาขึ้น" if s > 0 else " ขาลง"
            hint_en = " bullish" if s > 0 else " bearish"
        else:
            hint_th = " เอียงขึ้น" if s > 0 else " เอียงลง"
            hint_en = " leaning up" if s > 0 else " leaning down"
        th.append([direc, lab_th + hint_th])
        en.append([direc, lab_en + hint_en])
        used += 1
    return th[:4], en[:4]


def indicators_text(d):
    th, en = [], []
    lab = {"up": ("ขึ้น", "up"), "down": ("ลง", "down"), "sideways": ("ไซด์เวย์", "sideways")}
    for m in d.get("mtf") or []:
        t = m.get("trend") or "sideways"
        a, b = lab[t]
        rsi = m.get("rsi")
        extra = f" RSI {rsi}" if rsi is not None and m["tf"] in ("M15", "H1") else ""
        th.append(f"{m['tf']} {a}{extra}")
        en.append(f"{m['tf']} {b}{extra}")
    return " · ".join(th), " · ".join(en)


def template_note(price, up, dn, d, acc):
    side = "เอียงลง" if dn > up else "เอียงขึ้น" if up > dn else "ยังไม่ชัด"
    side_en = "lean down" if dn > up else "lean up" if up > dn else "no clear lean"
    mtf = d.get("mtf_align") or ""
    mtf_en = d.get("mtf_align_en") or ""
    a7, a30 = acc.get("acc_7d"), acc.get("acc_30d")
    acc_th = ""
    acc_en = ""
    if a7 is not None or a30 is not None:
        acc_th = f" · ความแม่นยำย้อนหลัง 7 วัน {fmt_pct(a7)} / 30 วัน {fmt_pct(a30)}"
        acc_en = f" · rolling accuracy 7d {fmt_pct(a7)} / 30d {fmt_pct(a30)}"
    note = (
        f"ทองสปอต ~{f2(price)} · AI ระยะสั้น {side} (ขึ้น {up}% ลง {dn}%) · {mtf}"
        f" · จุดเข้าเป็นเพียงกรอบวิเคราะห์ ไม่ใช่คำแนะนำการลงทุน"
        f"{acc_th}"
    )
    note_en = (
        f"Spot gold ~{f2(price)} · short-term AI {side_en} (up {up}% down {dn}%) · {mtf_en}"
        f" · levels are analysis only, not investment advice"
        f"{acc_en}"
    )
    return note, note_en


def llm_prose(facts):
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    prompt = (
        "Write a concise professional XAUUSD analysis from these facts. "
        "Education only, no investment advice, no emoji, no portfolio/P&L/account/tickets, no hype. "
        "Do not invent unseen news. Keep numbers as given.\n"
        f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Return JSON only with keys: note (Thai, <= 400 chars), note_en (English, <= 400 chars), "
        "ai_reasons (list of [up|down|neutral, Thai reason], max 4), "
        "ai_reasons_en (same length/order, English)."
    )
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You write concise bilingual gold analysis as JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://dashboard.purefxai.store/",
        "X-Title": "PUREGOLD dashboard",
    }
    try:
        req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=40) as r:
            payload = json.load(r)
        msg = payload["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning") or ""
        if isinstance(text, list):
            bits = []
            for part in text:
                if isinstance(part, dict):
                    bits.append(str(part.get("text") or part.get("content") or ""))
                else:
                    bits.append(str(part))
            text = "".join(bits)
        if not isinstance(text, str):
            text = str(text or "")
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        obj = json.loads(m.group())
        out = {}
        for k in ("note", "note_en"):
            if isinstance(obj.get(k), str) and obj[k].strip():
                out[k] = re.sub(r"\s+", " ", obj[k]).strip()[:500]
        for k in ("ai_reasons", "ai_reasons_en"):
            rs = obj.get(k)
            if isinstance(rs, list) and rs:
                clean = []
                for row in rs[:4]:
                    if isinstance(row, list) and len(row) >= 2 and str(row[0]) in ("up", "down", "neutral"):
                        clean.append([str(row[0]), re.sub(r"\s+", " ", str(row[1])).strip()[:180]])
                if clean:
                    out[k] = clean
        return out or None
    except Exception as e:
        print("llm prose skipped:", type(e).__name__, str(e)[:180], file=sys.stderr)
        return None


def maybe_new_prediction(preds, now, price, up, dn, signals, horizon=HORIZON_MIN):
    # Avoid duplicates closer than 45 minutes at nearly the same price/prob
    for r in reversed(preds):
        if r.get("source") == "backfill":
            continue
        t = _parse_ts(r.get("t"))
        if t and (now - t).total_seconds() < 45 * 60 and abs(float(r.get("price") or 0) - price) < 1.5 and int(r.get("up_pct") or -1) == up:
            return preds, False
        break
    mature = now + timedelta(minutes=horizon)
    preds.append({
        "t": now.strftime("%Y-%m-%d %H:%M"),
        "t_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mature_at": mature.strftime("%Y-%m-%d %H:%M"),
        "price": round(price, 3),
        "up_pct": up,
        "down_pct": dn,
        "bias": "up" if up >= 55 else "down" if dn >= 55 else "neutral",
        "horizon_min": horizon,
        "signals": signals,
        "source": "live",
        "hit": None,
    })
    return preds, True


def main():
    d = json.load(open("data.json", encoding="utf-8"))
    Cfile = _load_json("candles.json", {})
    C = Cfile.get("candles") or {}
    try:
        spot = _load_json("spot.json", {}) or fetch_spot()
        if not spot.get("price"):
            spot = fetch_spot()
    except Exception as e:
        print("learn: spot unavailable:", e, file=sys.stderr)
        spot = {"price": d.get("price_num") or 0, "src": "analysis", "src_label_th": "ราคาจากบทวิเคราะห์", "src_label_en": "Analysis price"}
    price = float(spot.get("price") or d.get("price_num") or 0)
    if not price:
        sys.exit("learn.py: no price")
    now = now_bkk()
    weights, cal, stored_stats = load_weights()
    stats_seed = {}
    if isinstance(stored_stats, dict):
        for k, row in stored_stats.items():
            if isinstance(row, dict):
                stats_seed[k] = {"hit": int(row.get("hit") or 0), "n": int(row.get("n") or 0)}

    preds = load_preds()
    # Bootstrap from candles if we have almost no scored history
    scored_all = [r for r in preds if r.get("hit") is not None]
    if len(scored_all) < 20 and C.get("H1"):
        bf, bw, bcal, bstats = backfill_and_score(C, weights)
        # keep previous live rows; replace old backfill
        preds = [r for r in preds if r.get("source") != "backfill"] + bf
        weights, cal, stats_seed = bw, bcal, bstats
        print(f"learn: backfilled {len(bf)} historical 4h forecasts")

    preds, weights, cal, stats, nscored = apply_live_scores(preds, price, now, weights, cal, stats_seed)
    acc = accuracy_from(preds, now)
    signals = extract_signals(d, price)
    score, up, dn, parts = combine(signals, weights, cal)

    preds, added = maybe_new_prediction(preds, now, price, up, dn, signals)
    save_preds(preds)

    # persist weights
    wout = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "horizon_minutes": HORIZON_MIN,
        "calibration": cal,
        "signals": {
            k: {
                "weight": round(float(weights[k]), 4),
                "hit": int((stats.get(k) or {}).get("hit") or 0),
                "n": int((stats.get(k) or {}).get("n") or 0),
            }
            for k in DEFAULT_WEIGHTS
        },
    }
    _write_json(WEIGHTS_PATH, wout)

    acc_out = dict(acc)
    acc_out.update({
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "horizon_minutes": HORIZON_MIN,
        "label_th": "โมเดลเรียนรู้จากผลจริงโดยอัตโนมัติ",
        "label_en": "The model learns automatically from results",
    })
    _write_json(ACC_PATH, acc_out)

    res, sup, _ = levels(price, C)
    r_th, r_en, s_th, s_en = build_sr_text(res, sup)
    ind_th, ind_en = indicators_text(d)
    reasons_th, reasons_en = reason_lines(parts, d, up, dn)
    note, note_en = template_note(price, up, dn, d, acc)
    side_th = "เอียงลง" if dn > up else "เอียงขึ้น" if up > dn else "ยังไม่ชัด"
    side_en = "Lean down" if dn > up else "Lean up" if up > dn else "Unclear"
    mtf = d.get("mtf_align") or ""
    mtf_en = d.get("mtf_align_en") or ""
    smc_note = ((d.get("smc_notes") or {}).get("XAUUSD") or "").split("·")[0].strip()
    smc_note_en = ((d.get("smc_notes_en") or {}).get("XAUUSD") or "").split("·")[0].strip()
    bias = " · ".join(x for x in [
        side_th,
        f"ขึ้น {up}% ลง {dn}%",
        f"ราคา ~{f2(price)}",
        mtf,
        smc_note,
    ] if x)
    bias_en = " · ".join(x for x in [
        side_en,
        f"up {up}% down {dn}%",
        f"price ~{f2(price)}",
        mtf_en,
        smc_note_en,
    ] if x)

    facts = {
        "price": price,
        "up_pct": up,
        "down_pct": dn,
        "mtf_align": mtf,
        "mtf_align_en": mtf_en,
        "indicators": ind_th,
        "support": s_th,
        "resistance": r_th,
        "smc": smc_note,
        "accuracy": acc,
        "src": spot.get("src"),
    }
    prose = llm_prose(facts)
    if prose:
        note = prose.get("note") or note
        note_en = prose.get("note_en") or note_en
        if prose.get("ai_reasons"):
            reasons_th = prose["ai_reasons"]
        if prose.get("ai_reasons_en"):
            reasons_en = prose["ai_reasons_en"]

    d["updated"] = fmt_th(now)
    d["updated_en"] = fmt_en(now)
    d["price"] = f"{price:,.2f}"
    d["price_en"] = f"{price:,.2f}"
    d["price_num"] = round(price, 3)
    d["bias"] = bias
    d["bias_en"] = bias_en
    d["indicators"] = ind_th
    d["indicators_en"] = ind_en
    d["resistance"] = r_th
    d["resistance_en"] = r_en
    d["support"] = s_th
    d["support_en"] = s_en
    d["ai_up_pct"] = up
    d["ai_down_pct"] = dn
    d["ai_method"] = "SMC + MTF + RSI/EMA · ถ่วงน้ำหนักอัตโนมัติจากผลย้อนหลัง 4 ชม."
    d["ai_method_en"] = "SMC + MTF + RSI/EMA · weights auto-adjusted from 4-hour outcomes"
    d["ai_reasons"] = reasons_th
    d["ai_reasons_en"] = reasons_en
    d["ev_plans"] = ev_plans(price, res, sup, up)
    d["ev_method"] = "EV = p×RR − (1−p) · p ปรับตามความแม่นยำล่าสุด · จุดเข้าจากแนวรับ/ต้านใกล้"
    d["ev_method_en"] = "EV = p×RR − (1−p) · p calibrated to recent accuracy · entries from nearby S/R"
    d["note"] = note
    d["note_en"] = note_en
    d["plans"] = [[
        f"แผนระยะสั้น {now.strftime('%H:%M')} น.",
        f"Bias {side_th} ขึ้น {up}% ลง {dn}% · ราคา ~{f2(price)}",
        f"รอตามจุดรับ/ต้านด้านล่าง · ไม่ไล่ราคากลางกรอบ",
        "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน",
    ]]
    d["plans_en"] = [[
        f"Short-term plan {now.strftime('%H:%M')}",
        f"Bias {side_en.lower()} up {up}% down {dn}% · price ~{f2(price)}",
        "Wait for the support/resistance levels below · do not chase mid-range",
        "For education only, not investment advice",
    ]]
    # keep auto_trade analysis-only; never publish a portfolio
    at = d.get("auto_trade") if isinstance(d.get("auto_trade"), dict) else {}
    d["auto_trade"] = {
        "enabled": False,
        "lot": at.get("lot", 0.1),
        "interval": "อัปเดตอัตโนมัติ · วิเคราะห์อย่างเดียว (ไม่เผยแพร่พอร์ตสาธารณะ)",
        "interval_en": "Automatic refresh · analysis only (no public portfolio)",
    }
    d["spot"] = {
        "price": round(price, 3),
        "src": spot.get("src"),
        "updated_th": spot.get("updated_th") or fmt_th(now),
        "updated_en": spot.get("updated_en") or fmt_en(now),
        "bid": spot.get("bid"),
        "ask": spot.get("ask"),
    }
    d["accuracy"] = {
        "acc_7d": acc.get("acc_7d"),
        "acc_30d": acc.get("acc_30d"),
        "n_7d": acc.get("n_7d"),
        "n_30d": acc.get("n_30d"),
        "horizon_minutes": HORIZON_MIN,
        "learns": True,
        "label_th": "โมเดลเรียนรู้จากผลจริงโดยอัตโนมัติ",
        "label_en": "The model learns automatically from results",
        "updated": now.strftime("%Y-%m-%d %H:%M"),
    }
    json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(
        f"learn: px={price:.2f} up={up} down={dn} acc7={acc.get('acc_7d')} n7={acc.get('n_7d')} "
        f"acc30={acc.get('acc_30d')} n30={acc.get('n_30d')} scored+={nscored} new={added} src={spot.get('src')}"
    )


if __name__ == "__main__":
    main()
