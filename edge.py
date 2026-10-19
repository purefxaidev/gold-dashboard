#!/usr/bin/env python3
"""Edge finder: what has actually worked in real trade history. Analysis only, never overclaims.
Inputs: history/trade_journal.jsonl (primary) + data.json pnl.trades (closed trades not yet in the journal).
Groups by symbol, side, timeframe, setup type, session (Bangkok time), hour, news context, MTF/SMC alignment at entry.
Per group: n, wins, win rate, avg R (only when the trade has sl or risk_points), expectancy (avg USC and avg points
per trade), profit factor (gross win / gross loss). n < 10 = low confidence.
Writes data.json edge {best, worst, by_symbol, by_side, by_session, by_setup, by_timeframe, by_hour, by_news, by_alignment,
total, notes, notes_en} and refreshes an auto section in lessons.md.
Journal fields used going forward (see README_DATA.md): symbol, timeframe, setup_type, session, sl, news_tag, mtf_align, smc_context."""
import json, re, datetime, os
TRADES = []
for ln in open("history/trade_journal.jsonl", encoding="utf-8"):
    ln = ln.strip()
    if ln: TRADES.append(json.loads(ln))
d = json.load(open("data.json", encoding="utf-8"))
seen = {(t.get("time_open", "")[-5:], round(float(t.get("entry", 0)), 2)) for t in TRADES}
for t in (d.get("pnl") or {}).get("trades", []):
    if t.get("status") == "closed" and (t.get("time"), round(float(t.get("entry", 0)), 2)) not in seen:
        TRADES.append({"time_open": datetime.date.today().isoformat() + " " + t["time"], "side": t["side"], "entry": t["entry"], "exit": t.get("exit"),
                       "pnl_usc": t["pl_usc"], "pnl_points": t["pl_points"], "result": "win" if t["pl_usc"] > 0 else "loss", "by": t.get("by")})
def setup_type(t):
    if t.get("setup_type"): return t["setup_type"]
    s = (t.get("setup", "") + " " + t.get("lesson", "")).lower()
    if "ใกล้ยอด" in s or "ไล่" in s or "chase" in s: return "chase near high"
    if "ob" in s.split() or "order block" in s: return "OB retest"
    if "fvg" in s: return "FVG"
    if "breakout" in s or "เบรก" in s or "ทะลุ" in s: return "breakout"
    if "ไล่" in s or "chase" in s: return "chase near high"
    if "ย่อ" in s or "pullback" in s or "แนวรับ" in s: return "S/R bounce (buy the dip)"
    return "other"
def session(t):
    if t.get("session"): return t["session"]
    h = int(t["time_open"][11:13])
    return "Asia" if 5 <= h < 14 else "London" if 14 <= h < 19 else "New York"
def news(t):
    if t.get("news_tag"): return t["news_tag"]
    s = t.get("news", "")
    return "dovish Fed / softer oil" if ("Warsh" in s or "Fed" in s or "น้ำมัน" in s) else ("unspecified" if not s else "other news")
def R(t):
    risk = t.get("risk_points") or (abs(float(t["entry"]) - float(t["sl"])) if t.get("sl") else None)
    return (float(t["pnl_points"]) / risk) if risk else None
DIMS = {"by_symbol": lambda t: t.get("symbol", "XAUUSD"), "by_side": lambda t: t["side"].upper(), "by_timeframe": lambda t: t.get("timeframe", "not recorded"),
        "by_setup": setup_type, "by_session": session, "by_hour": lambda t: t["time_open"][11:13] + ":00", "by_news": news,
        "by_alignment": lambda t: t.get("mtf_align") or t.get("smc_context") or "not recorded"}
def stats(ts):
    n = len(ts); w = sum(1 for t in ts if float(t["pnl_usc"]) > 0); gw = sum(float(t["pnl_usc"]) for t in ts if float(t["pnl_usc"]) > 0); gl = -sum(float(t["pnl_usc"]) for t in ts if float(t["pnl_usc"]) < 0)
    rs = [R(t) for t in ts if R(t) is not None]
    return {"n": n, "wins": w, "win_rate": round(100 * w / n, 1) if n else None, "expectancy_usc": round(sum(float(t["pnl_usc"]) for t in ts) / n, 2) if n else None,
            "avg_points": round(sum(float(t["pnl_points"]) for t in ts) / n, 2) if n else None, "profit_factor": round(gw / gl, 2) if gl else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None, "r_samples": len(rs), "days": len({t["time_open"][:10] for t in ts}), "confidence": "low" if n < 10 or len({t["time_open"][:10] for t in ts}) < 3 else "medium" if n < 30 else "ok", "net_usc": round(gw - gl, 2)}
E = {"total": stats(TRADES)}
groups = []
for dim, fn in DIMS.items():
    g = {}
    for t in TRADES: g.setdefault(fn(t), []).append(t)
    E[dim] = {k: stats(v) for k, v in sorted(g.items())}
    if dim in ("by_setup", "by_session", "by_hour", "by_news"):
        for k, s in E[dim].items():
            if s["n"] >= 2 and k not in ("other", "not recorded", "unspecified"): groups.append(dict(s, dim=dim[3:], key=k))
groups.sort(key=lambda s: s["expectancy_usc"], reverse=True)
E["best"] = [g for g in groups if g["expectancy_usc"] > 0][:3]; E["worst"] = [g for g in reversed(groups) if g["expectancy_usc"] < 0][:3]
DTH = {"setup": "รูปแบบ", "session": "ช่วงตลาด", "hour": "ชั่วโมง", "news": "บริบทข่าว"}
def line(g, en):
    pf = g["profit_factor"]; pf = ("PF " + str(pf)) if pf is not None else ("PF n/a (no losses)" if en else "PF ไม่มีไม้แพ้")
    if en: return f"{g['dim']} '{g['key']}': {g['n']} trades, win {g['win_rate']}%, avg {g['expectancy_usc']:+.2f} USC/trade, {pf}" + (" (low confidence: under 10 trades or under 3 days)" if g["confidence"] == "low" else "")
    return f"{DTH[g['dim']]} '{g['key']}': {g['n']} ไม้ ชนะ {g['win_rate']}% เฉลี่ย {g['expectancy_usc']:+.2f} USC/ไม้ {pf}" + (" (ความมั่นใจต่ำ: ไม่ถึง 10 ไม้ หรือไม่ถึง 3 วัน)" if g["confidence"] == "low" else "")
tot = E["total"]; days = len({t["time_open"][:10] for t in TRADES})
E["notes"] = [f"ทั้งหมด {tot['n']} ไม้ ชนะ {tot['win_rate']}% สุทธิ {tot['net_usc']:+.2f} USC" + f" จาก {days} วันซื้อขาย" + (" · ตัวอย่างยังน้อย ผลอาจเปลี่ยนได้มาก อย่าเชื่อมากเกินไป" if tot["n"] < 30 or days < 5 else "")] + \
    ["ดีสุด: " + line(g, False) for g in E["best"]] + ["แย่สุด: " + line(g, False) for g in E["worst"]] + \
    (["ยังคำนวณค่า R ไม่ได้ เพราะบันทึกเก่าไม่มี SL ตอนเข้า ต่อไปจะบันทึก sl ทุกไม้"] if tot["r_samples"] == 0 else [])
E["notes_en"] = [f"All {tot['n']} trades: win {tot['win_rate']}%, net {tot['net_usc']:+.2f} USC" + f" over {days} trading day(s)" + (" · Small sample; results can change a lot, do not over-trust them" if tot["n"] < 30 or days < 5 else "")] + \
    ["Best: " + line(g, True) for g in E["best"]] + ["Worst: " + line(g, True) for g in E["worst"]] + \
    (["Average R not available yet: older records have no SL at entry; sl will be recorded on every trade from now on"] if tot["r_samples"] == 0 else [])
E["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
d["edge"] = E
json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# lessons.md auto section
txt = open("lessons.md", encoding="utf-8").read() if os.path.exists("lessons.md") else "# Lessons\n"
blk = "<!-- edge:auto start -->\n## Edge finder (อัปเดตอัตโนมัติ " + E["updated"] + ")\n" + "\n".join("- " + x for x in E["notes"]) + "\n<!-- edge:auto end -->"
txt = re.sub(r"<!-- edge:auto start -->.*?<!-- edge:auto end -->", lambda m: blk, txt, flags=re.S) if "edge:auto start" in txt else txt.rstrip() + "\n\n" + blk + "\n"
open("lessons.md", "w", encoding="utf-8").write(txt)
print("\n".join(E["notes_en"]))
