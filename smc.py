#!/usr/bin/env python3
"""Smart Money Concepts + correlations. Reads candles.json (written by mtf.py), writes data.json:
  smc: {SYMBOL: {TF: {order_blocks:[{type,top,bottom,mitigated,t}], fvg:[{type,top,bottom,filled,t}],
        bos:{dir,level,t}|null, choch:{dir,level,t}|null, liquidity:[{type,level}], zone:{name,pos_pct,eq,hi,lo}}}}
  smc_notes / smc_notes_en: {SYMBOL: plain-language summary}
  correlations: {H1|D1: {symbols:[...], matrix:[[...]], bars:n}}   correlations_notes / _en: [text]
Rules (simple, deterministic, analysis only):
  swings = 2-bar fractals; close beyond the last swing = break (BOS if same direction as prior break, CHoCH if it flips);
  order block = last opposite-colour candle before the break leg, mitigated once price trades back into it;
  FVG = 3-candle gap (low[i] > high[i-2] bullish, high[i] < low[i-2] bearish), filled once price closes the gap;
  liquidity = equal highs/lows (within 0.1 ATR) + latest swing high/low; zone = premium/discount vs mid of last 60 bars.
Usage: python3 smc.py   (run after mtf.py; the routine can run: python3 mtf.py && python3 smc.py && python3 edge.py)"""
import json, math, datetime
CJ = json.load(open("candles.json")); d = json.load(open("data.json", encoding="utf-8"))
def atr(r, n=14):
    xs = [r[i][2] - r[i][3] for i in range(max(0, len(r) - n), len(r))]; return sum(xs) / len(xs) if xs else 0
def swings(r, w=2):
    hs, ls = [], []
    for i in range(w, len(r) - w):
        if r[i][2] >= max(x[2] for x in r[i - w:i + w + 1]): hs.append((i, r[i][2]))
        if r[i][3] <= min(x[3] for x in r[i - w:i + w + 1]): ls.append((i, r[i][3]))
    return hs, ls
def rnd(v, dp): return round(v, dp)
def analyse(r, dp):
    r = r[-120:]; A = atr(r) or 1e-9; hs, ls = swings(r)
    events, obs = [], []; lastdir = None; hi_i = lo_i = None; used_h = used_l = -1
    hmap = {i: v for i, v in hs}; lmap = {i: v for i, v in ls}
    for i in range(len(r)):
        # swings are confirmed 2 bars later
        if i - 2 in hmap: hi_i = i - 2
        if i - 2 in lmap: lo_i = i - 2
        c = r[i][4]
        for dirn, si, used in (("bull", hi_i, used_h), ("bear", lo_i, used_l)):
            if si is None or si == used: continue
            lvl = r[si][2] if dirn == "bull" else r[si][3]
            if (dirn == "bull" and c > lvl) or (dirn == "bear" and c < lvl):
                kind = "choch" if lastdir and lastdir != dirn else "bos"; lastdir = dirn
                events.append({"kind": kind, "dir": dirn, "level": rnd(lvl, dp), "t": r[i][0], "i": i})
                if dirn == "bull": used_h = si
                else: used_l = si
                # order block: last opposite candle before the leg (search back from swing to break)
                for j in range(i - 1, max(-1, i - 15), -1):
                    o, h, l, cl = r[j][1], r[j][2], r[j][3], r[j][4]
                    if (dirn == "bull" and cl < o) or (dirn == "bear" and cl > o):
                        later = r[i + 1:]
                        mit = any(x[3] <= h for x in later) if dirn == "bull" else any(x[2] >= l for x in later)
                        obs.append({"type": "bullish" if dirn == "bull" else "bearish", "top": rnd(h, dp), "bottom": rnd(l, dp), "mitigated": mit, "t": r[j][0]}); break
    fv = []
    for i in range(2, len(r)):
        if r[i][3] > r[i - 2][2] and r[i][3] - r[i - 2][2] > .1 * A:
            top, bot = r[i][3], r[i - 2][2]; later = r[i + 1:]
            fv.append({"type": "bullish", "top": rnd(top, dp), "bottom": rnd(bot, dp), "filled": any(x[3] <= bot for x in later), "t": r[i - 1][0]})
        if r[i][2] < r[i - 2][3] and r[i - 2][3] - r[i][2] > .1 * A:
            top, bot = r[i - 2][3], r[i][2]; later = r[i + 1:]
            fv.append({"type": "bearish", "top": rnd(top, dp), "bottom": rnd(bot, dp), "filled": any(x[2] >= top for x in later), "t": r[i - 1][0]})
    liq = []
    H = [v for _, v in hs[-12:]]; L = [v for _, v in ls[-12:]]
    for arr, nm in ((H, "equal_highs"), (L, "equal_lows")):
        for a in range(len(arr)):
            for b in range(a + 1, len(arr)):
                if abs(arr[a] - arr[b]) <= .1 * A and not any(abs(x["level"] - arr[b]) <= .1 * A for x in liq if x["type"] == nm):
                    liq.append({"type": nm, "level": rnd((arr[a] + arr[b]) / 2, dp)})
    if hs: liq.append({"type": "swing_high", "level": rnd(hs[-1][1], dp)})
    if ls: liq.append({"type": "swing_low", "level": rnd(ls[-1][1], dp)})
    seg = r[-60:]; hi = max(x[2] for x in seg); lo = min(x[3] for x in seg); eq = (hi + lo) / 2; px = r[-1][4]
    pos = round((px - lo) / (hi - lo) * 100) if hi > lo else 50
    zone = {"name": "premium" if pos > 55 else "discount" if pos < 45 else "equilibrium", "pos_pct": pos, "eq": rnd(eq, dp), "hi": rnd(hi, dp), "lo": rnd(lo, dp)}
    bos = next(({k: e[k] for k in ("dir", "level", "t")} for e in reversed(events) if e["kind"] == "bos"), None)
    ch = next(({k: e[k] for k in ("dir", "level", "t")} for e in reversed(events) if e["kind"] == "choch"), None)
    obs_keep = [o for o in obs if not o["mitigated"]][-3:] + [o for o in obs if o["mitigated"]][-1:]
    fvg_keep = [f for f in fv if not f["filled"]][-3:]
    return {"order_blocks": obs_keep, "fvg": fvg_keep, "bos": bos, "choch": ch, "liquidity": liq[-5:], "zone": zone,
            "last_event": events[-1]["kind"] + "_" + events[-1]["dir"] if events else None, "price": rnd(px, dp)}
DP = {"XAUUSD": 2, "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3, "AUDUSD": 5, "USDCHF": 5, "USDCAD": 5, "BTCUSD": 0}
src = {"XAUUSD": CJ.get("candles", {})}; src.update({k: v for k, v in CJ.get("markets", {}).items() if k != "DXY"})
smc, nt, ne = {}, {}, {}
for sym, tfs in src.items():
    smc[sym] = {}
    for tf in ("M15", "H1", "H4"):
        if len(tfs.get(tf, [])) >= 30: smc[sym][tf] = analyse(tfs[tf], DP.get(sym, 4))
    h = smc[sym].get("H1") or next(iter(smc[sym].values()), None)
    if not h: continue
    f = lambda v: f"{v:,.{DP.get(sym, 4)}f}"
    zt = {"premium": ("โซนแพง (premium) ระวังไล่ซื้อ", "premium zone, avoid chasing buys"), "discount": ("โซนถูก (discount) ระวังไล่ขาย", "discount zone, avoid chasing sells"), "equilibrium": ("กลางกรอบ", "mid-range")}[h["zone"]["name"]]
    ev = h["last_event"] or ""
    et = {"bos_bull": ("ทะลุโครงสร้างขึ้น (BOS) แนวโน้มขึ้นต่อ", "bullish BOS, uptrend continuing"), "bos_bear": ("หลุดโครงสร้างลง (BOS) แนวโน้มลงต่อ", "bearish BOS, downtrend continuing"),
          "choch_bull": ("เปลี่ยนโครงสร้างเป็นขึ้น (CHoCH)", "CHoCH to bullish"), "choch_bear": ("เปลี่ยนโครงสร้างเป็นลง (CHoCH)", "CHoCH to bearish")}.get(ev, ("ยังไม่มีสัญญาณโครงสร้าง", "no structure signal yet"))
    ob = next((o for o in reversed(h["order_blocks"]) if not o["mitigated"]), None)
    obt = (f" · OB {'ฝั่งซื้อ' if ob['type']=='bullish' else 'ฝั่งขาย'} {f(ob['bottom'])}-{f(ob['top'])} ยังไม่ถูกทดสอบ", f" · untested {ob['type']} OB {f(ob['bottom'])}-{f(ob['top'])}") if ob else ("", "")
    nt[sym] = f"H1: {et[0]} · ราคาอยู่{zt[0]} ({h['zone']['pos_pct']}% ของกรอบ){obt[0]} · FVG ค้าง {len(h['fvg'])} จุด"
    ne[sym] = f"H1: {et[1]} · price in {zt[1]} ({h['zone']['pos_pct']}% of range){obt[1]} · {len(h['fvg'])} open FVG"
d["smc"], d["smc_notes"], d["smc_notes_en"] = smc, nt, ne
# ---------- correlations ----------
ALL = dict(src); ALL["DXY"] = CJ.get("markets", {}).get("DXY", {})
ORDER = ["XAUUSD", "DXY", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "BTCUSD"]
def key(ts, tf): return ts // 3600 if tf == "H1" else datetime.datetime.fromtimestamp(ts + 6 * 3600, datetime.timezone.utc).date().isoformat()
def corr(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb), 2) if sa and sb else None
cor = {}; notes, notes_en = [], []
for tf in ("H1", "D1"):
    ser = {}
    for s in ORDER:
        rows = ALL.get(s, {}).get(tf, [])
        if len(rows) > 10: ser[s] = {key(r[0], tf): r[4] for r in rows}
    syms = [s for s in ORDER if s in ser]
    common = sorted(set.intersection(*[set(ser[s]) for s in syms])) if syms else []
    common = common[-51:]
    if len(common) < 20: continue
    ret = {s: [math.log(ser[s][common[i]] / ser[s][common[i - 1]]) for i in range(1, len(common))] for s in syms}
    M = [[corr(ret[a], ret[b]) if a != b else 1.0 for b in syms] for a in syms]
    cor[tf] = {"symbols": syms, "matrix": M, "bars": len(common) - 1}
    if "XAUUSD" in syms:
        gi = syms.index("XAUUSD"); row = [(syms[j], M[gi][j]) for j in range(len(syms)) if j != gi and M[gi][j] is not None]
        if "DXY" in syms:
            c = M[gi][syms.index("DXY")]
            if c is not None:
                if c <= -.3: notes.append(f"{tf}: ทองเคลื่อนสวนทางดอลลาร์ (DXY {c:+.2f}) ดอลลาร์อ่อน ทองมักขึ้น"); notes_en.append(f"{tf}: gold is moving opposite the US dollar (DXY {c:+.2f}); a weaker dollar tends to lift gold")
                elif c >= .3: notes.append(f"{tf}: ทองเคลื่อนไปทางเดียวกับดอลลาร์ (DXY {c:+.2f}) ผิดปกติ มักเป็นช่วงหนีความเสี่ยง"); notes_en.append(f"{tf}: gold is moving with the US dollar (DXY {c:+.2f}), unusual, often a risk-off phase")
                else: notes.append(f"{tf}: ทองกับดอลลาร์สัมพันธ์กันน้อย (DXY {c:+.2f})"); notes_en.append(f"{tf}: gold and the US dollar are only weakly related (DXY {c:+.2f})")
        mx = max(row, key=lambda x: x[1]); mn = min(row, key=lambda x: x[1])
        notes.append(f"{tf}: ทองไปทางเดียวกับ {mx[0]} มากที่สุด ({mx[1]:+.2f}) และสวนทาง {mn[0]} มากที่สุด ({mn[1]:+.2f}) · {len(common)-1} แท่ง")
        notes_en.append(f"{tf}: gold moves most with {mx[0]} ({mx[1]:+.2f}) and most against {mn[0]} ({mn[1]:+.2f}) · {len(common)-1} bars")
d["correlations"], d["correlations_notes"], d["correlations_notes_en"] = cor, notes, notes_en
json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(ne, ensure_ascii=False, indent=0)); print("\n".join(notes_en))
print({tf: (v["symbols"], v["bars"]) for tf, v in cor.items()})
