#!/usr/bin/env python3
"""Multi-timeframe trends for XAUUSD + Markets (FX, BTC). Free sources only, analysis only.
Gold: Binance PAXGUSDT klines (tracks gold), offset-corrected to spot (gold-api.com XAU).
Markets: Yahoo chart API (EURUSD=X ... BTC-USD); H4 = 4 x H1 aggregated.
Writes data.json fields: mtf, mtf_en, mtf_align, mtf_align_en, markets, markets_en, mtf_updated.
Also writes candles.json (gold OHLC per TF, already offset to spot) for the site.
Trend: EMA20>EMA50, EMA20 rising (vs 5 bars ago), close>EMA20 -> up; mirror -> down; else sideways."""
import json, urllib.request, datetime, time, sys
UA = {"User-Agent": "Mozilla/5.0"}
def get(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=15))
        except Exception as e: err = e; time.sleep(1.5)
    raise err
def ema(a, n):
    k = 2 / (n + 1); out = []; e = None
    for x in a: e = x if e is None else x * k + e * (1 - k); out.append(e)
    return out
def rsi(a, n=14):
    if len(a) < n + 2: return None
    g = l = 0
    for i in range(1, n + 1): d = a[i] - a[i - 1]; g += max(d, 0); l += max(-d, 0)
    g /= n; l /= n
    for i in range(n + 1, len(a)): d = a[i] - a[i - 1]; g = (g * (n - 1) + max(d, 0)) / n; l = (l * (n - 1) + max(-d, 0)) / n
    return round(100 - 100 / (1 + g / l), 1) if l else 100.0
def trend(c):
    if len(c) < 55: return "sideways", None, None, None
    e20, e50 = ema(c, 20), ema(c, 50); sl = e20[-1] - e20[-6]
    t = "up" if e20[-1] > e50[-1] and sl > 0 and c[-1] > e20[-1] else "down" if e20[-1] < e50[-1] and sl < 0 and c[-1] < e20[-1] else "sideways"
    return t, rsi(c), e20[-1], e50[-1]
TH = {"up": "ขาขึ้น", "down": "ขาลง", "sideways": "ไซด์เวย์"}; EN = {"up": "Uptrend", "down": "Downtrend", "sideways": "Sideways"}
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
d = json.load(open("data.json", encoding="utf-8"))
CJ = {"updated": now, "candles": {}}
MC = {}
# ---------- gold ----------
try:
    spot = float(get("https://api.gold-api.com/price/XAU")["price"])
    TFS = [("M5", "5m"), ("M15", "15m"), ("H1", "1h"), ("H4", "4h"), ("D1", "1d")]
    C = {}; mtf = []; off = None
    for tf, iv in TFS:
        k = get(f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval={iv}&limit=120")
        if off is None:
            last = float(get("https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=1m&limit=1")[-1][4]); off = spot - last
        o = [[int(x[0] / 1000), *(round(float(x[j]) + off, 2) for j in (1, 2, 3, 4))] for x in k]
        C[tf] = o; t, r, e20, e50 = trend([x[4] for x in o])
        mtf.append({"tf": tf, "trend": t, "trend_th": TH[t], "rsi": r, "ema20": round(e20, 2) if e20 else None, "ema50": round(e50, 2) if e50 else None})
    ups = sum(m["trend"] == "up" for m in mtf); dns = sum(m["trend"] == "down" for m in mtf)
    d["mtf"] = [{"tf": m["tf"], "trend": m["trend"], "label": m["trend_th"], "rsi": m["rsi"], "ema20": m["ema20"], "ema50": m["ema50"]} for m in mtf]
    d["mtf_en"] = [dict(x, label=EN[x["trend"]]) for x in d["mtf"]]
    side = "up" if ups > dns else "down" if dns > ups else "mixed"
    d["mtf_align"] = f"ขาขึ้น {ups}/5 · ขาลง {dns}/5 · ไซด์เวย์ {5-ups-dns}/5 · " + {"up": "ภาพรวมเอียงขึ้น", "down": "ภาพรวมเอียงลง", "mixed": "ภาพรวมยังไม่ชัด"}[side]
    d["mtf_align_en"] = f"Up {ups}/5 · Down {dns}/5 · Sideways {5-ups-dns}/5 · " + {"up": "overall leaning up", "down": "overall leaning down", "mixed": "no clear overall direction"}[side]
    CJ = {"updated": now, "source": "Binance PAXGUSDT offset to gold-api.com spot", "offset": round(off, 2), "spot": spot, "candles": C}
except Exception as e: print("gold mtf failed:", e, file=sys.stderr)
# ---------- markets ----------
SYM = [("EURUSD", "EURUSD=X", 5), ("GBPUSD", "GBPUSD=X", 5), ("USDJPY", "JPY=X", 3), ("AUDUSD", "AUDUSD=X", 5), ("USDCHF", "CHF=X", 5), ("USDCAD", "CAD=X", 5), ("BTCUSD", "BTC-USD", 0)]
def yc(s, iv, rg):
    r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval={iv}&range={rg}")["chart"]["result"][0]
    q = r["indicators"]["quote"][0]; rows = [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if c is not None and h is not None]
    return r["meta"], rows
def pivots(rows, w=3):
    hi, lo = [], []
    for i in range(w, len(rows) - w):
        if rows[i][2] == max(x[2] for x in rows[i - w:i + w + 1]): hi.append(rows[i][2])
        if rows[i][3] == min(x[3] for x in rows[i - w:i + w + 1]): lo.append(rows[i][3])
    return hi, lo
mk, mk_en = [], []
for name, s, dp in SYM:
    try:
        meta, m15 = yc(s, "15m", "5d"); _, h1 = yc(s, "60m", "1mo"); _, d1 = yc(s, "1d", "1y")
        _, h1l = yc(s, "60m", "3mo")
        h4 = []
        for r in h1l:
            b = r[0] // 14400 * 14400
            if h4 and h4[-1][0] == b: x = h4[-1]; h4[-1] = (b, x[1], max(x[2], r[2]), min(x[3], r[3]), r[4])
            else: h4.append((b, *r[1:]))
        MC[name] = {k: [[int(r[0]), *(round(v, 6) for v in r[1:])] for r in rows[-120:]] for k, rows in (("M15", m15), ("H1", h1), ("H4", h4), ("D1", d1))}
        px = meta.get("regularMarketPrice") or m15[-1][4]
        prev = d1[-2][4] if len(d1) > 1 else None
        chg = round((px - prev) / prev * 100, 2) if prev else None
        tfs = []
        for tf, rows in (("M15", m15), ("H1", h1), ("H4", h4), ("D1", d1)):
            t, r, _, _ = trend([x[4] for x in rows]); tfs.append({"tf": tf, "trend": t, "rsi": r})
        ups = sum(x["trend"] == "up" for x in tfs); dns = sum(x["trend"] == "down" for x in tfs)
        bias = "up" if ups >= 3 or (ups == 2 and dns == 0) else "down" if dns >= 3 or (dns == 2 and ups == 0) else "neutral"
        hi, lo = pivots(h1[-120:]); res = min([x for x in hi if x > px], default=None); sup = max([x for x in lo if x < px], default=None)
        atr = sum(x[2] - x[3] for x in h1[-14:]) / 14
        f = (lambda v: f"{v:,.{dp}f}") if dp else (lambda v: f"{v:,.0f}")
        if bias == "up" and sup: th = f"รอซื้อโซน {f(sup)}–{f(sup + atr * .5)} (แนวรับใกล้สุด)"; en = f"Buy zone {f(sup)}–{f(sup + atr * .5)} (nearest support)"
        elif bias == "down" and res: th = f"รอขายโซน {f(res - atr * .5)}–{f(res)} (แนวต้านใกล้สุด)"; en = f"Sell zone {f(res - atr * .5)}–{f(res)} (nearest resistance)"
        else: th = "รอ ยังไม่มีทิศชัด" + (f" กรอบ {f(sup)}–{f(res)}" if sup and res else ""); en = "Wait, no clear direction" + (f"; range {f(sup)}–{f(res)}" if sup and res else "")
        base = {"symbol": name, "price": round(px, dp if dp else 0), "dp": dp, "chg_pct": chg, "spark": [round(x[4], dp + 1 if dp else 0) for x in h1[-48:]],
                "tfs": tfs, "bias": bias, "support": round(sup, dp) if sup else None, "resistance": round(res, dp) if res else None}
        bl = {"up": ("เอียงขึ้น", "Bullish"), "down": ("เอียงลง", "Bearish"), "neutral": ("กลางๆ", "Neutral")}[bias]
        mk.append(dict(base, bias_label=bl[0], setup=th)); mk_en.append(dict(base, bias_label=bl[1], setup=en))
    except Exception as e: print("market", name, "failed:", e, file=sys.stderr)
try:
    _, dx1 = yc("DX-Y.NYB", "60m", "1mo"); _, dxd = yc("DX-Y.NYB", "1d", "1y")
    MC["DXY"] = {"H1": [[int(r[0]), *r[1:]] for r in dx1[-120:]], "D1": [[int(r[0]), *r[1:]] for r in dxd[-120:]]}
except Exception as e: print("DXY failed:", e, file=sys.stderr)
CJ["markets"] = MC
json.dump(CJ, open("candles.json", "w"), separators=(",", ":"))
if mk: d["markets"], d["markets_en"] = mk, mk_en
d["mtf_updated"] = now
json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("mtf:", " ".join(f'{m["tf"]}={m["trend"]}/{m["rsi"]}' for m in d.get("mtf", [])), "|", d.get("mtf_align_en"))
for m in mk_en: print(m["symbol"], m["price"], m["chg_pct"], m["bias"], [x["trend"][0] for x in m["tfs"]], m["setup"])
