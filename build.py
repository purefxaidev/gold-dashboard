import json,html
d=json.load(open('data.json'));e=html.escape
li=lambda xs:''.join(f'<li>{e(x)}</li>' for x in xs)
plans=''.join('<div class=card><b>'+e(p[0])+'</b><br>'+'<br>'.join(e(x) for x in p[1:])+'</div>' for p in d['plans'])
news=''.join(f'<li>{e(t)} <a href="{e(u)}" target=_blank>แหล่งข่าว</a></li>' for t,u in d['news'])
open('index.html','w').write(f'''<!doctype html><html lang=th><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=300><title>ทองคำ XAUUSD</title>
<style>body{{font-family:sans-serif;background:#111;color:#eee;margin:0;padding:12px}}.card{{background:#1e1e1e;border-radius:10px;padding:12px;margin:10px 0}}h1{{color:#f5c542;font-size:22px}}a{{color:#6cf}}.r{{color:#f66}}.s{{color:#6f6}}</style>
<h1>📊 ทองคำ XAUUSD</h1><div class=card>อัปเดต: {e(d['updated'])}<br>ราคา: <b>{e(d['price'])}</b><br>มุมมอง: <b>{e(d['bias'])}</b><br><small>{e(d['indicators'])}</small></div>
<div class=card><b class=r>แนวต้าน</b><ul>{li(d['resistance'])}</ul><b class=s>แนวรับ</b><ul>{li(d['support'])}</ul></div>
<h3>จุดเข้า / จุดออก</h3>{plans}
<div class=card><b>ข่าววิเคราะห์</b><ul>{news}</ul></div>
<div class=card style="height:420px;padding:0"><div class="tradingview-widget-container" style="height:100%"><div class="tradingview-widget-container__widget" style="height:100%"></div>
<script src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>{{"autosize":true,"symbol":"OANDA:XAUUSD","interval":"60","timezone":"Asia/Bangkok","theme":"dark","locale":"th_TH"}}</script></div></div>
<p><small>{e(d['note'])}</small></p></html>''')
