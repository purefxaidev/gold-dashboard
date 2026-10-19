#!/bin/bash
# usage: line_flex.sh <trade|close|hourly|news|status|portfolio> <json-file | json-string>
# Broadcast LINE Flex card (altText fallback). ล้ม -> line_notify.sh ข้อความธรรมดา. ไม่พิมพ์ token
# DRY_RUN=1 -> พิมพ์ payload JSON แทนการส่ง
# portfolio/close: อัตราชนะคำนวณอัตโนมัติจากไม้ที่ปิดวันนี้ (history/trade_journal.jsonl + data.json pnl.trades) ถ้าไม่ส่ง wins/total มา
TYPE="$1"; IN="$2"
DIR=/workspace
[ -f "$IN" ] && IN="$(cat "$IN")"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/b.py" <<'PY'
import json,sys
T,raw,out=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.loads(raw)
DASH="https://purefxaidev.github.io/gold-dashboard/"
G,R,Y,B,GR="#1DB954","#E53935","#F5C542","#4287F5","#8A8F98"
def tx(t,**k): return {"type":"text","text":str(t) if str(t) else "-","wrap":True,**k}
def row(k,v,c=None): return {"type":"box","layout":"horizontal","contents":[tx(k,size="sm",color=GR,flex=4),tx(v,size="sm",align="end",weight="bold",flex=6,**({"color":c} if c else {}))]}
def sep(): return {"type":"separator","margin":"md"}
def bubble(title,color,body,sub=None,extra_btn=None):
    hdr=[tx("PUREGOLD AI",color="#FFFFFFB3",size="xxs",weight="bold"),tx(title,color="#FFFFFF",weight="bold",size="lg")]+([tx(sub,color="#FFFFFFCC",size="xs")] if sub else [])
    btns=([extra_btn] if extra_btn else [])+[{"type":"button","style":"primary","color":"#C9A227","height":"sm","action":{"type":"uri","label":"ดูแดชบอร์ด","uri":DASH}}]
    return {"type":"bubble","header":{"type":"box","layout":"vertical","backgroundColor":color,"contents":hdr,"paddingAll":"14px"},
            "body":{"type":"box","layout":"vertical","spacing":"sm","contents":body},
            "footer":{"type":"box","layout":"vertical","spacing":"sm","contents":btns}}
f=lambda v:(f"{v:,.2f}" if isinstance(v,(int,float)) else str(v))
import datetime,os
GD="/workspace/gold-dashboard"
def today_closed():
    """today's closed trades: journal (time_close today) + data.json pnl.trades closed not already in journal"""
    day=datetime.datetime.now().strftime("%Y-%m-%d"); out=[]; seen=set()
    try:
        for ln in open(GD+"/history/trade_journal.jsonl",encoding="utf-8"):
            ln=ln.strip()
            if not ln: continue
            j=json.loads(ln)
            if str(j.get("time_close",j.get("time_open","")))[:10]==day:
                out.append(float(j.get("pnl_usc",0))); seen.add((round(float(j.get("entry",0)),2),round(float(j.get("exit") or 0),2)))
    except Exception: pass
    try:
        dj=json.load(open(GD+"/data.json",encoding="utf-8"))
        for x in (dj.get("pnl") or {}).get("trades",[]):
            if x.get("status")=="closed" and (round(float(x.get("entry",0)),2),round(float(x.get("exit") or 0),2)) not in seen:
                out.append(float(x.get("pl_usc",0)))
    except Exception: pass
    return out
def winrate(dd,extra=None):
    """returns (pct, wins, total). Uses dd win_rate/wins/total when given, else computes from today's closed trades"""
    if dd.get("wins") is not None and dd.get("total"):
        w,n=int(dd["wins"]),int(dd["total"]); return (dd.get("win_rate") if dd.get("win_rate") is not None else round(100*w/n,1)),w,n
    pl=today_closed()
    if extra is not None and extra not in pl: pl.append(extra)
    n=len(pl); w=sum(1 for x in pl if x>0)
    if dd.get("win_rate") is not None and not n: return dd["win_rate"],None,None
    return (round(100*w/n,1) if n else None),w,n
def wrtxt(p,w,n):
    if p is None: return "-"
    s=(f"{p:.0f}" if float(p)==int(float(p)) else f"{float(p):.1f}")+"%"
    return s+(f" ({w}/{n})" if n else "")
sg=lambda v:(("+" if v>=0 else "")+f"{v:,.2f}") if isinstance(v,(int,float)) else str(v)
if T=="trade":
    buy=str(d["side"]).lower()=="buy"; c=G if buy else R
    body=[row("จุดเข้า",f(d["entry"])),row("SL",f(d["sl"]),R),row("TP",f(d["tp"]),G),row("ล็อต",d.get("lot",0.1))]
    if "rr" in d: body.append(row("RR",d["rr"]))
    if "ev" in d: body.append(row("EV",sg(d["ev"])+"R",G if d["ev"]>0 else R))
    if d.get("reason"): body+= [sep(),tx("เหตุผล: "+d["reason"],size="sm")]
    b=bubble(("BUY" if buy else "SELL")+" XAUUSD"+(" (รอ Limit)" if d.get("pending") else ""),c,body,d.get("time"))
    alt=f'{"BUY" if buy else "SELL"} XAUUSD @{f(d["entry"])} SL {f(d["sl"])} TP {f(d["tp"])}'
elif T=="close":
    r=str(d.get("result","manual")).lower(); lab={"tp":"ชน TP (รับกำไร)","sl":"ชน SL (ตัดขาดทุน)"}.get(r,"ปิดเอง")
    pl=d["pl_usc"]; c=G if pl>=0 else R
    body=[row("ฝั่ง",str(d.get("side","")).upper()),row("เข้า → ออก",f"{f(d.get('entry','-'))} → {f(d.get('exit','-'))}"),row("ล็อต",d.get("lot",0.1)),
          row("กำไร/ขาดทุน",sg(pl)+" USC",c),row("จุด",sg(d.get("pl_points",0)),c)]
    if "today_usc" in d: body+=[sep(),row("รวมวันนี้",sg(d["today_usc"])+" USC",G if d["today_usc"]>=0 else R)]
    wp,ww,wn=winrate(d,None)
    if not (wn and any(abs(x-pl)<0.01 for x in today_closed())): wp,ww,wn=winrate(d,pl)
    body+=([sep()] if "today_usc" not in d else [])+[row("อัตราชนะวันนี้",wrtxt(wp,ww,wn),G if (wp or 0)>=50 else R)]
    b=bubble("ปิดออเดอร์ · "+lab,c,body,d.get("time")); alt=f"ปิดออเดอร์ {lab} {sg(pl)} USC"
elif T=="hourly":
    up=d.get("trend","").lower() in("up","ขึ้น"); dn=d.get("trend","").lower() in("down","ลง")
    arrow="▲ ขาขึ้น" if up else "▼ ขาลง" if dn else "◆ ไซด์เวย์"; c=G if up else R if dn else B
    body=[{"type":"box","layout":"horizontal","contents":[tx(f(d["price"]),size="xxl",weight="bold",flex=5),tx(arrow+(f' {d["confidence"]}%' if "confidence" in d else ""),size="sm",align="end",gravity="center",color=c,flex=5)]},sep(),tx("แนวต้าน",size="xs",color=R,weight="bold")]
    body+=[row("R"+str(i+1),f(x)) for i,x in enumerate(d.get("resistance",[])[:3])]
    body+=[tx("แนวรับ",size="xs",color=G,weight="bold",margin="md")]+[row("S"+str(i+1),f(x)) for i,x in enumerate(d.get("support",[])[:3])]
    p=d.get("plan")
    if p: body+=[sep(),tx("แผน: "+str(p.get("side","")).upper(),size="sm",weight="bold"),row("เข้า",f(p["entry"])),row("SL",f(p["sl"]),R),row("TP",f(p["tp"]),G)]+([row("EV",sg(p["ev"])+"R")] if "ev" in p else [])
    if d.get("events"): body+=[sep(),tx("ข่าวถัดไป",size="xs",weight="bold")]+[tx("• "+e,size="xs",color=GR) for e in d["events"][:4]]
    b=bubble("สรุปทองรายชั่วโมง",c,body,d.get("time")); alt=f"สรุปทอง {f(d['price'])} {arrow}"
elif T=="news":
    imp=str(d.get("impact","medium")).lower(); ic={"high":R,"medium":"#FB8C00","low":GR}.get(imp,GR); il={"high":"ผลกระทบสูง","medium":"ผลกระทบกลาง","low":"ผลกระทบต่ำ"}.get(imp,imp)
    eff=str(d.get("effect","")).lower(); el={"up":"▲ หนุนทองขึ้น","down":"▼ กดดันทองลง"}.get(eff,"◆ กลางๆ")
    body=[{"type":"box","layout":"horizontal","contents":[{"type":"box","layout":"vertical","backgroundColor":ic,"cornerRadius":"8px","paddingAll":"4px","contents":[tx(il,color="#FFFFFF",size="xs",align="center")],"flex":0},tx(el,size="sm",align="end",weight="bold",color=G if eff=="up" else R if eff=="down" else GR)]},
          tx(d["headline"],weight="bold",size="md",margin="md")]+([tx(d["summary"],size="sm",color=GR)] if d.get("summary") else [])
    btn={"type":"button","style":"secondary","height":"sm","action":{"type":"uri","label":"อ่านข่าว","uri":d["url"]}} if str(d.get("url","")).startswith("https://") else None
    b=bubble("ข่าวทองคำ",ic,body,d.get("time"),btn); alt="ข่าวทอง: "+d["headline"]
elif T=="portfolio":
    net=d.get("today_usc",0); c=G if net>=0 else R; WR=winrate(d)
    body=[tx("กำไร/ขาดทุนวันนี้",size="xs",color=GR),tx(sg(net)+" USC",size="xxl",weight="bold",color=c),
          row("จำนวนไม้วันนี้",d.get("trades") if d.get("trades") is not None else (WR[2] if WR[2] else 0)),row("อัตราชนะ",wrtxt(*WR),G if (WR[0] or 0)>=50 else R)]
    if "balance" in d or "equity" in d:
        body+=[sep()]+([row("Balance",f(d["balance"])+" USC")] if "balance" in d else [])+([row("Equity",f(d["equity"])+" USC")] if "equity" in d else [])
    op=d.get("open",[])
    body+=[sep(),tx(f"ไม้ที่เปิดอยู่ ({len(op)})",size="sm",weight="bold")]
    body+=[row(f'{str(o["side"]).upper()} {o.get("lot",0.1)} @{f(o["entry"])}',sg(o.get("pl_usc",0))+" USC",G if o.get("pl_usc",0)>=0 else R) for o in op[:8]] or [tx("ไม่มี",size="xs",color=GR)]
    pe=d.get("pending",[])
    body+=[sep(),tx(f"ออเดอร์รอ ({len(pe)})",size="sm",weight="bold")]
    body+=[row(f'{o.get("type","")} {o.get("lot",0.1)} @{f(o["entry"])}',f'SL {f(o.get("sl","-"))} · TP {f(o.get("tp","-"))}') for o in pe[:6]] or [tx("ไม่มี",size="xs",color=GR)]
    b=bubble("สรุปพอร์ต",c,body,d.get("time")+" · ส่วนตัว" if d.get("time") else "ข้อมูลส่วนตัว"); alt=f"พอร์ตวันนี้ {sg(net)} USC · ชนะ {wrtxt(*WR)} · เปิด {len(op)} ไม้"
elif T=="status":
    lv=str(d.get("level","info")).lower(); c={"warning":"#FB8C00","error":R}.get(lv,B); t={"warning":"แจ้งเตือน","error":"ปัญหา"}.get(lv,"สถานะระบบ")
    body=[tx(d["text"],size="md")]+[row(k,v) for k,v in (d.get("rows") or {}).items()]
    b=bubble(t,c,body,d.get("time")); alt=t+": "+d["text"]
else: sys.exit("unknown type")
json.dump({"messages":[{"type":"flex","altText":alt[:390],"contents":b}]},open(out,"w"),ensure_ascii=False)
open(out+".alt","w").write(alt)
PY
python3 "$TMP/b.py" "$TYPE" "$IN" "$TMP/p.json" 2>"$TMP/err" || { echo "flex build failed: $(head -c 200 "$TMP/err")" >&2; exec "$DIR/line_notify.sh" "$(printf '%s' "$IN" | head -c 1500)"; }
[ "$DRY_RUN" = 1 ] && { cat "$TMP/p.json"; exit 0; }
[ -n "$LINE_CHANNEL_ACCESS_TOKEN" ] || { echo "no LINE token" >&2; exit 1; }
CODE=$(curl -s -X POST https://api.line.me/v2/bot/message/broadcast -H "Authorization: Bearer $LINE_CHANNEL_ACCESS_TOKEN" -H 'Content-Type: application/json' -d @"$TMP/p.json" -o "$TMP/out" -w '%{http_code}')
[ "$CODE" = 200 ] && { echo "flex sent ($TYPE) HTTP 200"; exit 0; }
echo "flex failed HTTP $CODE: $(head -c 200 "$TMP/out") -> text fallback" >&2
exec "$DIR/line_notify.sh" "$(cat "$TMP/p.json.alt")"
