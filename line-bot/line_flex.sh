#!/bin/bash
# PUREGOLD LINE Flex card sender. Never prints the LINE token.
#
# usage: line_flex.sh <trade|close|hourly|news|status|portfolio> <json-file | json-string>
#   DRY_RUN=1   print the payload JSON (flex + text fallback) and exit, nothing is sent
#   VALIDATE=1  only check the payload with LINE's validate/broadcast endpoint (nothing is sent)
# Every real send is validated first; if Flex is rejected the LINE error body is appended to
# /workspace/line_flex_errors.log and a clean Thai text message (never raw JSON) is sent instead.
#
# Accepted input schema (all fields optional unless noted; numbers may be numbers or strings such as
# "4,176", "+0.50R", "76.5%", "811.89 USC"; unknown fields are ignored):
#   common:    symbol ("XAUUSD" default; e.g. EURUSD, USDJPY, BTCUSD), time (string)
#   trade:     side* (buy|sell), entry*, sl, tp, lot, rr, ev (number or "+0.50R"), confidence (0-100),
#              reason, pending (bool, Limit/Stop order not yet filled)
#   close:     side, entry, exit, lot, pl_usc*, pl_points (ignored when entry+exit given: computed per
#              symbol, pips for FX), result (tp|sl|manual), today_usc, wins, total, win_rate
#   portfolio: today_usc, trades, wins, total, win_rate, balance, equity (private card),
#              open / pending: string | object | array of strings/objects.
#              object keys: symbol, side or type, lot, entry, sl, tp, pl_usc
#              string example: "XAUUSD BUY 0.1 @ 4,176 SL 4,165 TP 4,195" (parsed when possible)
#   hourly:    price*, trend (up|down|side), confidence, resistance [..], support [..],
#              plan {side, entry, sl, tp, ev}, events [..]
#   news:      headline*, summary, impact (high|medium|low), effect (up|down), url (https only)
#   status:    text*, level (info|warning|error), rows {label: value}
# Win rate: when wins/total are not given, it is computed from today's closed trades
# (history/trade_journal.jsonl + data.json pnl.trades).
TYPE="$1"; IN="$2"
DIR=/workspace; LOG=/workspace/line_flex_errors.log
[ -f "$IN" ] && IN="$(cat "$IN")"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/b.py" <<'PY'
import json, sys, re, datetime, traceback
T, raw, out = sys.argv[1], sys.argv[2], sys.argv[3]
DASH = "https://purefxaidev.github.io/gold-dashboard/"
GD = "/workspace/gold-dashboard"
G, R, Y, B, GR = "#1DB954", "#E53935", "#F5C542", "#4287F5", "#8A8F98"

# ---------- normalisation ----------
def load(s):
    try:
        v = json.loads(s)
    except Exception:
        try: v = json.loads(re.sub(r",\s*([}\]])", r"\1", s))
        except Exception: return {"text": str(s)}
    if isinstance(v, list): v = v[0] if v and isinstance(v[0], dict) else {"items": v}
    return v if isinstance(v, dict) else {"text": str(v)}
def num(v):
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+", str(v).replace("\u2212", "-"))
    if not m: return None
    try: return float(m.group(0).replace(",", ""))
    except ValueError: return None
def s(v, d="-"):
    if v is None: return d
    t = str(v).strip(); return t if t else d
FX = ("EUR", "GBP", "USD", "JPY", "AUD", "NZD", "CAD", "CHF")
def symof(x, dflt="XAUUSD"):
    v = s(x.get("symbol") if isinstance(x, dict) else None, "")
    v = re.sub(r"[^A-Za-z]", "", v).upper()
    if v.endswith("M") and len(v) == 7: v = v[:6]   # broker suffix e.g. XAUUSDm
    return v or dflt
def sym_in_text(t, dflt):
    m = re.search(r"\b(XAUUSD|XAGUSD|BTCUSD|ETHUSD|(?:EUR|GBP|USD|AUD|NZD|CAD|CHF|JPY){2})M?\b", str(t or ""), re.I)
    return m.group(1).upper() if m else dflt
def kind(sym):
    if sym.startswith(("XAU", "XAG")): return "metal"
    if sym.startswith(("BTC", "ETH")): return "crypto"
    if len(sym) == 6 and sym[:3] in FX and sym[3:] in FX: return "fx"
    return "other"
def digits(sym, v=None):
    k = kind(sym)
    if k == "fx": return 3 if "JPY" in sym else 5
    if k == "metal":
        if v is not None and abs(round(v, 3) - round(v, 2)) > 1e-9: return 3
        return 2
    if k == "crypto": return 2
    if v is None: return 2
    a = abs(v); return 5 if a < 20 else 3 if a < 200 else 2
def px(v, sym):
    n = num(v)
    if n is None: return s(v)
    return f"{n:,.{digits(sym, n)}f}"
def pxp(v, other):
    """price formatted with the same decimals as its pair (entry/exit)"""
    n, o = num(v), num(other)
    if n is None: return s(v)
    dp = max(digits(SYM, n), digits(SYM, o) if o is not None else 0); return f"{n:,.{dp}f}"
def money(v): n = num(v); return "-" if n is None else f"{n:,.2f}"
def sg(v, dp=2):
    n = num(v)
    if n is None: return s(v)
    return ("+" if n >= 0 else "") + f"{n:,.{dp}f}"
def points(entry, exit_, side, sym):
    e, x = num(entry), num(exit_)
    if e is None or x is None: return None, None
    diff = (x - e) if str(side).lower() != "sell" else (e - x)
    k = kind(sym)
    if k == "fx": return diff / (0.01 if "JPY" in sym else 0.0001), "pips"
    if k == "metal": return diff, "จุด ($)"
    if k == "crypto": return diff, "จุด ($)"
    return diff, "จุด"
def lot(v): n = num(v); return "-" if n is None else (f"{n:g}")
def side_of(x):
    t = s(x.get("side") or x.get("type") or x.get("order_type"), "").lower() if isinstance(x, dict) else str(x).lower()
    return "sell" if "sell" in t else "buy" if "buy" in t else ""
ORD_RE = re.compile(r"(?P<sym>[A-Za-z]{6,7})?\s*(?P<type>(?:buy|sell)(?:\s*(?:limit|stop))?)\s+(?P<lot>[\d.]+)?\s*(?:lot\w*)?\s*@?\s*(?P<entry>[\d,]+(?:\.\d+)?)?"
                    r"(?:.*?\bSL\s*(?P<sl>[\d,]+(?:\.\d+)?))?(?:.*?\bTP\s*(?P<tp>[\d,]+(?:\.\d+)?))?(?:.*?(?P<pl>[-+][\d,]+(?:\.\d+)?)\s*USC)?", re.I)
def orders(v):
    """open/pending -> list of dicts {symbol,type,lot,entry,sl,tp,pl_usc,text}"""
    if v is None or v == "" or v == []: return []
    if isinstance(v, (str, int, float)): v = [x for x in re.split(r"\s*[;\n|]\s*", str(v)) if x.strip()]
    if isinstance(v, dict):
        v = [v] if any(k in v for k in ("entry", "side", "type", "price", "lot")) else [dict(o, symbol=o.get("symbol", k)) if isinstance(o, dict) else f"{k} {o}" for k, o in v.items()]
    res = []
    for o in v if isinstance(v, list) else [v]:
        if isinstance(o, dict):
            sym = symof(o, sym_in_text(o.get("text", ""), "XAUUSD"))
            res.append({"symbol": sym, "type": s(o.get("type") or o.get("side"), "").upper(), "lot": o.get("lot", o.get("volume")),
                        "entry": o.get("entry", o.get("price", o.get("open_price"))), "sl": o.get("sl"), "tp": o.get("tp"),
                        "pl_usc": o.get("pl_usc", o.get("profit")), "text": None})
        else:
            t = str(o).strip(); m = ORD_RE.search(t)
            if m and m.group("type"):
                sym = (m.group("sym") or "").upper()[:6]; sym = sym if kind(sym) != "other" or sym in ("XAUUSD",) else sym_in_text(t, "XAUUSD")
                res.append({"symbol": sym or sym_in_text(t, "XAUUSD"), "type": re.sub(r"\s+", " ", m.group("type")).upper(), "lot": m.group("lot"),
                            "entry": m.group("entry"), "sl": m.group("sl"), "tp": m.group("tp"), "pl_usc": m.group("pl"), "text": None})
            else: res.append({"symbol": sym_in_text(t, ""), "text": t})
    return res
def order_line(o):
    if o.get("text"): return o["text"], ""
    sym = o["symbol"]; a = " ".join(x for x in [sym, o["type"], lot(o["lot"]) if num(o.get("lot")) is not None else "", "@ " + px(o["entry"], sym) if num(o.get("entry")) is not None else ""] if x)
    b = " · ".join(x for x in [f'SL {px(o["sl"], sym)}' if num(o.get("sl")) is not None else "", f'TP {px(o["tp"], sym)}' if num(o.get("tp")) is not None else ""] if x)
    if num(o.get("pl_usc")) is not None: b = (sg(o["pl_usc"]) + " USC") + (" · " + b if b else "")
    return a, b

# ---------- win rate ----------
def today_closed():
    day = datetime.datetime.now().strftime("%Y-%m-%d"); res = []; seen = set()
    try:
        for ln in open(GD + "/history/trade_journal.jsonl", encoding="utf-8"):
            ln = ln.strip()
            if not ln: continue
            j = json.loads(ln)
            if str(j.get("time_close", j.get("time_open", "")))[:10] == day:
                res.append(num(j.get("pnl_usc")) or 0.0); seen.add((round(num(j.get("entry")) or 0, 2), round(num(j.get("exit")) or 0, 2)))
    except Exception: pass
    try:
        dj = json.load(open(GD + "/data.json", encoding="utf-8"))
        for x in (dj.get("pnl") or {}).get("trades", []):
            if x.get("status") == "closed" and (round(num(x.get("entry")) or 0, 2), round(num(x.get("exit")) or 0, 2)) not in seen:
                res.append(num(x.get("pl_usc")) or 0.0)
    except Exception: pass
    return res
def winrate(dd, extra=None):
    w, n, p = num(dd.get("wins")), num(dd.get("total")), num(dd.get("win_rate"))
    if w is not None and n: return (p if p is not None else round(100 * w / n, 1)), int(w), int(n)
    pl = today_closed()
    if extra is not None and not any(abs(x - extra) < 0.01 for x in pl): pl.append(extra)
    n = len(pl); w = sum(1 for x in pl if x > 0)
    if p is not None and not n: return p, None, None
    return (round(100 * w / n, 1) if n else None), w, n
def wrtxt(p, w, n):
    if p is None: return "-"
    t = (f"{p:.0f}" if float(p) == int(float(p)) else f"{float(p):.1f}") + "%"
    return t + (f" ({w}/{n})" if n else "")

# ---------- flex helpers ----------
def tx(t, **k): t = str(t) if t is not None and str(t).strip() else "-"; return {"type": "text", "text": t[:1900], "wrap": True, **k}
def row(k, v, c=None): return {"type": "box", "layout": "horizontal", "contents": [tx(k, size="sm", color=GR, flex=4), tx(v, size="sm", align="end", weight="bold", flex=6, **({"color": c} if c else {}))]}
def sep(): return {"type": "separator", "margin": "md"}
def bubble(title, color, body, sub=None, extra_btn=None):
    hdr = [tx("PUREGOLD AI", color="#FFFFFFB3", size="xxs", weight="bold"), tx(title, color="#FFFFFF", weight="bold", size="lg")] + ([tx(sub, color="#FFFFFFCC", size="xs")] if sub else [])
    btns = ([extra_btn] if extra_btn else []) + [{"type": "button", "style": "primary", "color": "#C9A227", "height": "sm", "action": {"type": "uri", "label": "ดูแดชบอร์ด", "uri": DASH}}]
    return {"type": "bubble", "header": {"type": "box", "layout": "vertical", "backgroundColor": color, "contents": hdr, "paddingAll": "14px"},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body or [tx("-")]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": btns}}
def col(v): n = num(v); return G if (n or 0) >= 0 else R

d = load(raw); SYM = symof(d, sym_in_text(d.get("reason", "") if T in ("trade", "close") else "", "XAUUSD"))
TH = {"buy": "BUY", "sell": "SELL"}

# ---------- builders: each returns (bubble, alt, text_lines) ----------
def b_trade():
    sd = side_of(d); c = G if sd != "sell" else R; S = TH.get(sd, s(d.get("side")).upper())
    title = f"เปิดออเดอร์ {SYM}" + (" (รอ Limit)" if d.get("pending") in (True, "true", 1, "1") else "")
    rows = [("ฝั่ง", S, c), ("จุดเข้า", px(d.get("entry"), SYM), None), ("SL", px(d.get("sl"), SYM), R), ("TP", px(d.get("tp"), SYM), G), ("ล็อต", lot(d.get("lot", 0.1)), None)]
    if num(d.get("rr")) is not None: rows.append(("RR", f'1:{num(d["rr"]):g}', None))
    if num(d.get("ev")) is not None: rows.append(("EV", sg(d["ev"]) + "R", col(d["ev"])))
    if num(d.get("confidence")) is not None: rows.append(("ความมั่นใจ", f'{num(d["confidence"]):g}%', None))
    body = [row(*r) for r in rows] + ([sep(), tx("เหตุผล: " + s(d["reason"]), size="sm")] if d.get("reason") else [])
    alt = f'{title}: {S} @ {px(d.get("entry"), SYM)} SL {px(d.get("sl"), SYM)} TP {px(d.get("tp"), SYM)}'
    lines = [title] + [f"{k}: {v}" for k, v, _ in rows] + ([f'เหตุผล: {s(d["reason"])}'] if d.get("reason") else [])
    return bubble(title, c, body, d.get("time")), alt, lines
def b_close():
    r = s(d.get("result"), "manual").lower(); lab = {"tp": "ชน TP (รับกำไร)", "sl": "ชน SL (ตัดขาดทุน)"}.get(r, "ปิดเอง")
    pl = num(d.get("pl_usc")); c = col(pl)
    pts, unit = points(d.get("entry"), d.get("exit"), side_of(d), SYM)
    if pts is None and num(d.get("pl_points")) is not None: pts, unit = num(d["pl_points"]), ("pips" if kind(SYM) == "fx" else "จุด")
    rows = [("ฝั่ง", TH.get(side_of(d), s(d.get("side")).upper()), None), ("เข้า → ออก", f'{pxp(d.get("entry"), d.get("exit"))} → {pxp(d.get("exit"), d.get("entry"))}', None), ("ล็อต", lot(d.get("lot", 0.1)), None),
            ("กำไร/ขาดทุน", sg(pl) + " USC" if pl is not None else "-", c)]
    if pts is not None: rows.append((unit, sg(pts, 1 if unit == "pips" else 2), c))
    if num(d.get("today_usc")) is not None: rows.append(("รวมวันนี้", sg(d["today_usc"]) + " USC", col(d["today_usc"])))
    wp, ww, wn = winrate(d, pl); rows.append(("อัตราชนะวันนี้", wrtxt(wp, ww, wn), G if (wp or 0) >= 50 else R))
    body = [row(*x) for x in rows[:-1]] + [sep(), row(*rows[-1])]
    title = f"ปิดออเดอร์ {SYM} · {lab}"; alt = f"{title} {sg(pl)} USC" if pl is not None else title
    return bubble(title, c, body, d.get("time")), alt, [title] + [f"{k}: {v}" for k, v, _ in rows]
def b_hourly():
    tr = s(d.get("trend"), "").lower(); up = tr in ("up", "ขึ้น", "bull", "bullish"); dn = tr in ("down", "ลง", "bear", "bearish")
    arrow = "▲ ขาขึ้น" if up else "▼ ขาลง" if dn else "◆ ไซด์เวย์"; c = G if up else R if dn else B
    cf = f' {num(d["confidence"]):g}%' if num(d.get("confidence")) is not None else ""
    lst = lambda v: v if isinstance(v, list) else ([v] if v not in (None, "") else [])
    rs, ss = lst(d.get("resistance"))[:3], lst(d.get("support"))[:3]
    body = [{"type": "box", "layout": "horizontal", "contents": [tx(px(d.get("price"), SYM), size="xxl", weight="bold", flex=5), tx(arrow + cf, size="sm", align="end", gravity="center", color=c, flex=5)]}, sep(), tx("แนวต้าน", size="xs", color=R, weight="bold")]
    body += [row("R" + str(i + 1), px(x, SYM)) for i, x in enumerate(rs)] or [tx("-", size="xs")]
    body += [tx("แนวรับ", size="xs", color=G, weight="bold", margin="md")] + ([row("S" + str(i + 1), px(x, SYM)) for i, x in enumerate(ss)] or [tx("-", size="xs")])
    lines = [f"สรุป {SYM} รายชั่วโมง", f"ราคา: {px(d.get('price'), SYM)} {arrow}{cf}", "แนวต้าน: " + (", ".join(px(x, SYM) for x in rs) or "-"), "แนวรับ: " + (", ".join(px(x, SYM) for x in ss) or "-")]
    p = d.get("plan")
    if isinstance(p, dict):
        body += [sep(), tx("แผน: " + TH.get(side_of(p), s(p.get("side"), "").upper()), size="sm", weight="bold"), row("เข้า", px(p.get("entry"), SYM)), row("SL", px(p.get("sl"), SYM), R), row("TP", px(p.get("tp"), SYM), G)] + ([row("EV", sg(p["ev"]) + "R")] if num(p.get("ev")) is not None else [])
        lines.append(f'แผน: {TH.get(side_of(p), "")} เข้า {px(p.get("entry"), SYM)} SL {px(p.get("sl"), SYM)} TP {px(p.get("tp"), SYM)}')
    elif p: body += [sep(), tx("แผน: " + s(p), size="sm")]; lines.append("แผน: " + s(p))
    ev = lst(d.get("events"))
    if ev: body += [sep(), tx("ข่าวถัดไป", size="xs", weight="bold")] + [tx("• " + s(e), size="xs", color=GR) for e in ev[:4]]; lines += ["ข่าวถัดไป:"] + [" - " + s(e) for e in ev[:4]]
    return bubble(f"สรุป{'ทอง' if SYM == 'XAUUSD' else ' ' + SYM}รายชั่วโมง", c, body, d.get("time")), f"สรุป {SYM} {px(d.get('price'), SYM)} {arrow}", lines
def b_news():
    imp = s(d.get("impact"), "medium").lower(); ic = {"high": R, "medium": "#FB8C00", "low": GR}.get(imp, GR); il = {"high": "ผลกระทบสูง", "medium": "ผลกระทบกลาง", "low": "ผลกระทบต่ำ"}.get(imp, imp)
    eff = s(d.get("effect"), "").lower(); el = {"up": "▲ หนุนทองขึ้น", "down": "▼ กดดันทองลง"}.get(eff, "◆ กลางๆ")
    hl = s(d.get("headline") or d.get("text") or d.get("title"))
    body = [{"type": "box", "layout": "horizontal", "contents": [{"type": "box", "layout": "vertical", "backgroundColor": ic, "cornerRadius": "8px", "paddingAll": "4px", "contents": [tx(il, color="#FFFFFF", size="xs", align="center")], "flex": 0}, tx(el, size="sm", align="end", weight="bold", color=G if eff == "up" else R if eff == "down" else GR)]},
            tx(hl, weight="bold", size="md", margin="md")] + ([tx(d["summary"], size="sm", color=GR)] if d.get("summary") else [])
    url = s(d.get("url"), ""); btn = {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "uri", "label": "อ่านข่าว", "uri": url}} if url.startswith("https://") and len(url) < 1000 else None
    return bubble("ข่าวทองคำ", ic, body, d.get("time"), btn), "ข่าวทอง: " + hl, ["ข่าวทองคำ (" + il + ", " + el + ")", hl] + ([s(d["summary"])] if d.get("summary") else []) + ([url] if btn else [])
def b_portfolio():
    net = num(d.get("today_usc")) or 0.0; c = col(net); WR = winrate(d)
    trades = num(d.get("trades")); trades = int(trades) if trades is not None else (WR[2] or 0)
    rows = [("จำนวนไม้วันนี้", str(trades), None), ("อัตราชนะ", wrtxt(*WR), G if (WR[0] or 0) >= 50 else R)]
    body = [tx("กำไร/ขาดทุนวันนี้", size="xs", color=GR), tx(sg(net) + " USC", size="xxl", weight="bold", color=c)] + [row(*r) for r in rows]
    lines = ["สรุปพอร์ต (ข้อมูลส่วนตัว)", f"กำไร/ขาดทุนวันนี้: {sg(net)} USC"] + [f"{k}: {v}" for k, v, _ in rows]
    acc = [(k, money(d[key]) + " USC") for k, key in (("Balance", "balance"), ("Equity", "equity")) if num(d.get(key)) is not None]
    if acc: body += [sep()] + [row(k, v) for k, v in acc]; lines += [f"{k}: {v}" for k, v in acc]
    for key, lab, mx in (("open", "ไม้ที่เปิดอยู่", 8), ("pending", "ออเดอร์รอ", 6)):
        ol = orders(d.get(key)); body += [sep(), tx(f"{lab} ({len(ol)})", size="sm", weight="bold")]; lines.append(f"{lab} ({len(ol)}):")
        if not ol: body.append(tx("ไม่มี", size="xs", color=GR)); lines.append(" - ไม่มี")
        for o in ol[:mx]:
            a, b2 = order_line(o); pl = num(o.get("pl_usc"))
            body.append({"type": "box", "layout": "vertical", "contents": [tx(a, size="sm", weight="bold")] + ([tx(b2, size="xs", color=(col(pl) if pl is not None else GR))] if b2 else [])})
            lines.append(" - " + a + (" | " + b2 if b2 else ""))
    nopen = len(orders(d.get("open")))
    sub = (s(d.get("time")) + " · ส่วนตัว") if d.get("time") else "ข้อมูลส่วนตัว"
    return bubble("สรุปพอร์ต", c, body, sub), f"พอร์ตวันนี้ {sg(net)} USC · ชนะ {wrtxt(*WR)} · เปิด {nopen} ไม้", lines
def b_status():
    lv = s(d.get("level"), "info").lower(); c = {"warning": "#FB8C00", "error": R}.get(lv, B); t = {"warning": "แจ้งเตือน", "error": "ปัญหา"}.get(lv, "สถานะระบบ")
    rw = d.get("rows") if isinstance(d.get("rows"), dict) else {}
    body = [tx(s(d.get("text")), size="md")] + [row(k, s(v)) for k, v in rw.items()]
    return bubble(t, c, body, d.get("time")), t + ": " + s(d.get("text")), [t, s(d.get("text"))] + [f"{k}: {s(v)}" for k, v in rw.items()]

LABEL = {"side": "ฝั่ง", "entry": "จุดเข้า", "exit": "ออก", "sl": "SL", "tp": "TP", "lot": "ล็อต", "rr": "RR", "ev": "EV", "confidence": "ความมั่นใจ", "reason": "เหตุผล",
         "pl_usc": "กำไร/ขาดทุน (USC)", "today_usc": "รวมวันนี้ (USC)", "trades": "จำนวนไม้", "wins": "ชนะ", "total": "ทั้งหมด", "win_rate": "อัตราชนะ %",
         "balance": "Balance", "equity": "Equity", "open": "ไม้ที่เปิดอยู่", "pending": "ออเดอร์รอ", "symbol": "สินค้า", "price": "ราคา", "headline": "ข่าว", "text": "ข้อความ"}
TITLE = {"trade": "เปิดออเดอร์", "close": "ปิดออเดอร์", "portfolio": "สรุปพอร์ต", "hourly": "สรุปรายชั่วโมง", "news": "ข่าวทองคำ", "status": "สถานะระบบ"}
def generic_lines():
    """last-resort readable text: label: value lines, never raw JSON"""
    def v2s(v):
        if isinstance(v, dict): return ", ".join(f"{LABEL.get(k, k)} {v2s(x)}" for k, x in v.items())
        if isinstance(v, list): return "; ".join(v2s(x) for x in v)
        return s(v)
    return ["PUREGOLD AI · " + TITLE.get(T, "แจ้งเตือน") + (" " + SYM if T in ("trade", "close") else "")] + [f"{LABEL.get(k, k)}: {v2s(v)}" for k, v in d.items() if v not in (None, "", [], {})]

res = {"type": T}
try:
    fn = {"trade": b_trade, "close": b_close, "hourly": b_hourly, "news": b_news, "portfolio": b_portfolio, "status": b_status}[T]
    b, alt, lines = fn()
    res["flex"] = {"messages": [{"type": "flex", "altText": (alt or "PUREGOLD AI")[:390], "contents": b}]}
except Exception:
    res["build_error"] = traceback.format_exc()[-1500:]; lines = generic_lines()
text = "\n".join(["PUREGOLD AI"] + lines if lines and not lines[0].startswith("PUREGOLD") else lines)
res["text"] = {"messages": [{"type": "text", "text": text[:4900]}]}
json.dump(res, open(out, "w"), ensure_ascii=False)
PY
log() { printf '%s [%s] %s\n' "$(TZ=Asia/Bangkok date '+%F %H:%M:%S %Z')" "$TYPE" "$1" >> "$LOG"; }
if ! python3 "$TMP/b.py" "$TYPE" "$IN" "$TMP/r.json" 2>"$TMP/err"; then
  log "builder crashed: $(tr '\n' ' ' < "$TMP/err" | head -c 800)"
  # last resort: still not raw JSON
  printf '{"text":{"messages":[{"type":"text","text":"PUREGOLD AI: มีการแจ้งเตือนใหม่ ดูรายละเอียดที่แดชบอร์ด https://purefxaidev.github.io/gold-dashboard/"}]}}' > "$TMP/r.json"
fi
python3 - "$TMP/r.json" "$TMP" <<'PY'
import json,sys; r=json.load(open(sys.argv[1])); d=sys.argv[2]
open(d+"/text.json","w").write(json.dumps(r["text"],ensure_ascii=False))
if "flex" in r: open(d+"/flex.json","w").write(json.dumps(r["flex"],ensure_ascii=False))
if "build_error" in r: open(d+"/build_err","w").write(r["build_error"])
PY
[ -f "$TMP/build_err" ] && log "flex build error -> text: $(tr '\n' ' ' < "$TMP/build_err" | tail -c 600)"
if [ "$DRY_RUN" = 1 ]; then cat "$TMP/r.json"; echo; exit 0; fi
[ -n "$LINE_CHANNEL_ACCESS_TOKEN" ] || { echo "no LINE token" >&2; exit 1; }
post() { curl -s -X POST "https://api.line.me/v2/bot/message/$1" -H "Authorization: Bearer $LINE_CHANNEL_ACCESS_TOKEN" -H 'Content-Type: application/json' -d @"$2" -o "$TMP/out" -w '%{http_code}'; }
if [ -f "$TMP/flex.json" ]; then
  C=$(post validate/broadcast "$TMP/flex.json")
  if [ "$C" = 200 ]; then
    [ "$VALIDATE" = 1 ] && { echo "flex valid ($TYPE)"; exit 0; }
    C=$(post broadcast "$TMP/flex.json"); [ "$C" = 200 ] && { echo "flex sent ($TYPE) HTTP 200"; exit 0; }
    log "broadcast HTTP $C: $(head -c 1500 "$TMP/out")"
  else
    log "validate HTTP $C: $(head -c 1500 "$TMP/out")"
    [ "$VALIDATE" = 1 ] && { echo "flex INVALID ($TYPE) HTTP $C, see $LOG" >&2; exit 2; }
  fi
fi
C=$(post validate/broadcast "$TMP/text.json")
[ "$VALIDATE" = 1 ] && { echo "text fallback validate HTTP $C ($TYPE)"; [ "$C" = 200 ]; exit $?; }
C=$(post broadcast "$TMP/text.json"); [ "$C" = 200 ] && { echo "text fallback sent ($TYPE) HTTP 200"; exit 0; }
log "text broadcast HTTP $C: $(head -c 800 "$TMP/out")"; echo "LINE send failed HTTP $C, see $LOG" >&2; exit 1
