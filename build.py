#!/usr/bin/env python3
"""Build index.html + view.json from data.json (used by the 30-min routine).

data.json fields (Thai text unless noted):
  updated, price, bias, indicators, note       : strings
  resistance, support                          : list of strings; the first number in each string is
                                                 used for the visual ladder (e.g. "4,203 (ยอด 16 ต.ค.)")
  plans                                        : list of string lists (card title first)
  news                                         : list of [thai_summary, url]
  ai_up_pct, ai_down_pct                       : ints, should sum to 100 (probability up/down, short term)
  ai_method                                    : string, short description of how the % was derived
  ai_reasons                                   : list of [direction("up"|"down"|"neutral"), thai_reason]
  pnl                                          : {today_usc, today_points, win_rate, mark_price, note,
                                                 trades:[{time, side, lot, entry, exit|null, pl_usc, pl_points,
                                                 status open|closed, by 'AI'|'ผู้ใช้'}]}  (allowlisted; P/L only)
  ev_plans                                     : list of {name, side("buy"|"sell"), entry, sl, tp,
                                                 p_win (0..1), status (optional text)}

English (optional, same shape as the Thai field, suffix _en; the site falls back to Thai when missing):
  updated_en, price_en, bias_en, indicators_en, note_en, ai_method_en, ev_method_en : strings
  resistance_en, support_en : list of strings   plans_en : list of string lists
  news_en : list of [english_summary, url]       ai_reasons_en : list of [direction, english_reason]
  ev_plans[i].name_en / status_en, pnl.note_en, auto_trade.interval_en
  Full docs: README_DATA.md.  Emoji are stripped from all strings at build time.

EV decision model (computed here, do not hand-edit rr/ev):
  risk   = |entry - sl|            reward = |tp - entry|
  RR     = reward / risk
  EV (R) = p_win * RR - (1 - p_win)        # expected result per trade in units of risk (R)
  decision = "เข้า" if EV > 0 else "รอ"
  risk_free: SL at/beyond breakeven (or risk < max(0.5, 5% of reward)) -> rr/ev/breakeven = null, decision = "ถือ"
  Breakeven win rate = 1 / (1 + RR)

Safety: build fails if data.json contains anything that looks like an API key, email, or account/
ticket/balance fields. Never put credentials or account info into data.json.
"""
import json, re, sys, datetime

d = json.load(open('data.json', encoding='utf-8'))
raw = json.dumps(d, ensure_ascii=False)

# ---- safety guard ----
bad = [r'AIza[0-9A-Za-z_\-]{20,}', r'AQ\.[A-Za-z0-9_\-]{20,}', r'[\w.+-]+@[\w-]+\.[\w.]+',
       r'(?i)"(account|ticket|balance|equity|password|login|api_?key)"']
for pat in bad:
    if re.search(pat, raw):
        sys.exit(f'build.py: refusing to build, data.json matches forbidden pattern {pat!r}')

# ---- pnl allowlist (no balance/equity/account/ticket) ----
PNL_KEYS = {'today_usc', 'today_points', 'win_rate', 'mark_price', 'note', 'trades', 'trade_count', 'open_count', 'pending', 'note_en'}
TRADE_KEYS = {'time', 'symbol', 'side', 'lot', 'entry', 'exit', 'sl', 'tp', 'pl_usc', 'pl_points', 'status', 'by'}
pnl = d.get('pnl')
if pnl is not None:
    extra = set(pnl) - PNL_KEYS
    for t in pnl.get('trades', []): extra |= set(t) - TRADE_KEYS
    for t in pnl.get('pending', []): extra |= set(t) - {'symbol', 'type', 'lot', 'entry', 'sl', 'tp'}
    if extra: sys.exit(f'build.py: pnl has non-allowlisted fields {sorted(extra)}')

# ---- history files guard ----
import glob
for fn in glob.glob('history/*.jsonl') + ['lessons.md']:
    try: txt = open(fn, encoding='utf-8').read()
    except FileNotFoundError: continue
    for pat in bad:
        if re.search(pat, txt): sys.exit(f'build.py: {fn} matches forbidden pattern {pat!r}')

at = d.get('auto_trade')
if at is not None and set(at) - {'enabled', 'interval', 'interval_en', 'lot'}: sys.exit('build.py: auto_trade has unexpected fields')

def first_num(s):
    m = re.search(r'\d[\d,]*\.?\d*', str(s))
    return float(m.group().replace(',', '')) if m else None

EMO = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]')
def noemo(x):
    if isinstance(x, str): return re.sub(r'\s{2,}', ' ', EMO.sub('', x)).strip()
    if isinstance(x, list): return [noemo(i) for i in x]
    if isinstance(x, dict): return {k: noemo(i) for k, i in x.items()}
    return x
d = noemo(d)
for k in list(d):
    if k.endswith('_en') and k[:-3] in d and type(d[k]) is not type(d[k[:-3]]):
        sys.exit(f'build.py: {k} must have the same type as {k[:-3]}')
v = dict(d)
v['price_num'] = first_num(d.get('price', ''))
v['res_nums'] = [first_num(x) for x in d.get('resistance', [])]
v['sup_nums'] = [first_num(x) for x in d.get('support', [])]

evs = []
for p in d.get('ev_plans', []):
    risk = abs(p['entry'] - p['sl']); reward = abs(p['tp'] - p['entry'])
    buy = str(p.get('side', '')).lower() == 'buy'
    # SL at/beyond breakeven (or tiny risk) -> no loss risk left; RR/EV are meaningless, do not show them
    tiny = max(0.5, 0.05 * reward)
    if (buy and p['sl'] >= p['entry'] - tiny) or (not buy and p['sl'] <= p['entry'] + tiny):
        evs.append(dict(p, rr=None, ev=None, breakeven=None, risk_free=True, decision='ถือ')); continue
    rr = reward / risk if risk else 0
    pw = float(p['p_win'])
    ev = pw * rr - (1 - pw)
    evs.append(dict(p, rr=round(rr, 2), ev=round(ev, 2), breakeven=round(1 / (1 + rr), 3) if rr else 1,
                    decision='เข้า' if ev > 0 else 'รอ'))
v['ev_plans'] = evs
up, dn = d.get('ai_up_pct'), d.get('ai_down_pct')
if up is not None and dn is None: v['ai_down_pct'] = 100 - up
v['built'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

js = json.dumps(v, ensure_ascii=False).replace('</', '<\\/')
open('view.json', 'w', encoding='utf-8').write(json.dumps(v, ensure_ascii=False, indent=1))
tpl = open('template.html', encoding='utf-8').read()
open('index.html', 'w', encoding='utf-8').write(tpl.replace('/*__DATA__*/null', js))
print('built index.html + view.json', v['built'])

# ---- compact AI context (site chat, live call, LINE bot) : ai_context.txt ----
def _ctx():
    L = []; f = lambda v, dp=2: ('-' if v is None else (f"{v:,.{dp}f}" if isinstance(v, (int, float)) else str(v)))
    L.append(f"GOLD XAUUSD (สปอต) ราคา {f(v.get('price_num'))} · อัปเดต {d.get('updated', '-')} · AI ขึ้น {d.get('ai_up_pct', '-')}% / ลง {v.get('ai_down_pct', '-')}%")
    L.append("bias: " + str(d.get('bias', '-'))[:400])
    L.append("indicators: " + str(d.get('indicators', '-'))[:300])
    L.append("แนวต้าน: " + " | ".join(d.get('resistance', [])) + " · แนวรับ: " + " | ".join(d.get('support', [])))
    for p in v.get('ev_plans', []):
        L.append(f"แผน {p.get('name')} {p.get('side')} เข้า {p.get('entry')} SL {p.get('sl')} TP {p.get('tp')} " + ("ไม่มีความเสี่ยงแล้ว (กันหน้าไม้)" if p.get('risk_free') else f"RR {p.get('rr')} EV {p.get('ev')}R ตัดสินใจ {p.get('decision')}") + f" · {p.get('status', '')}")
    pn = d.get('pnl') or {}
    if pn: L.append(f"ผลวันนี้: {pn.get('trade_count', '-')} ไม้ปิด ชนะ {pn.get('win_rate', '-')}% กำไร {pn.get('today_usc', '-')} USC ({pn.get('today_points', '-')} จุด) · เปิดอยู่ {pn.get('open_count', '-')} · ออเดอร์รอ " + ", ".join(f"{o.get('type')} {o.get('entry')} SL {o.get('sl')} TP {o.get('tp')}" for o in pn.get('pending', [])))
    if d.get('mtf'): L.append("ทองหลายไทม์เฟรม: " + " ".join(f"{m['tf']}={m['trend']}(RSI {m.get('rsi')})" for m in d['mtf']) + " · " + str(d.get('mtf_align', '')))
    for k, n in (d.get('smc_notes') or {}).items(): L.append(f"SMC {k}: {n}")
    for n in d.get('correlations_notes', []): L.append("ความสัมพันธ์ " + n)
    L.append("ตลาดอื่น (วิเคราะห์อย่างเดียว ไม่ได้เทรด, ข้อมูล " + str(d.get('mtf_updated', '-')) + "):")
    for m in d.get('markets', []):
        L.append(f"{m['symbol']} {f(m.get('price'), m.get('dp') or 0)} ({'+' if (m.get('chg_pct') or 0) >= 0 else ''}{m.get('chg_pct')}% วันนี้) " + " ".join(f"{t['tf']}={t['trend']}(RSI {t.get('rsi')})" for t in m.get('tfs', [])) + f" · bias {m.get('bias')} · S {f(m.get('support'), m.get('dp') or 0)} R {f(m.get('resistance'), m.get('dp') or 0)} · {m.get('setup', '')}")
    e = d.get('edge') or {}
    for n in e.get('notes', []): L.append("Edge: " + n)
    for n in (d.get('news') or [])[:4]: L.append("ข่าว: " + str(n[0])[:300])
    L.append("หมายเหตุ: " + str(d.get('note', '')))
    return "\n".join(noemo(L))[:14000]
open('ai_context.txt', 'w', encoding='utf-8').write(_ctx())
