/* PUREGOLD analysis widgets: multi-timeframe charts, markets, Smart Money mode, AI Edge. Analysis only, no trading.
   Usage: PGX.mount(element, "mtf"|"markets"|"smc"|"edge", {compact:true|false}). Data: view.json (+ candles.json, live Binance PAXG/BTC + gold-api spot). */
(function () {
  const EN = window.LANG === "en", T = (th, en) => EN ? en : th;
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const N = v => (v === null || v === undefined || v === "" || isNaN(Number(v))) ? null : Number(v);
  const F = (v, d = 2) => N(v) == null ? "-" : Number(v).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
  const S = {D: null, C: null, live: null, smc: localStorage.getItem("gd_smc") === "1", corrTf: "H1", smcTf: "H1", mounts: []};
  const css = `.pgx{--pc:#36e2ff;--pg:#f5c542;--pm:#ff3d9a;--pu:#22e39a;--pd:#ff4d6d;--pmu:#8a93a6;--pl:rgba(255,255,255,.08)}
.pgx .hd{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}.pgx .hd b{color:var(--pg);font-size:15px;font-weight:600}.pgx .hd small{color:var(--pmu);font-size:11px}
.pgx .sp{flex:1}.pgx .btn{cursor:pointer;border:1px solid #36e2ff77;background:transparent;color:var(--pc);border-radius:999px;padding:4px 10px;font:600 11px/1.2 inherit;font-family:inherit}.pgx .btn.on{background:#36e2ff;color:#001018}
.pgx .g5{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.pgx .ch{border:1px solid var(--pl);border-radius:10px;padding:6px;background:rgba(0,0,0,.25);min-width:0}
.pgx .ch .t{display:flex;justify-content:space-between;align-items:center;gap:4px;font-size:11px;margin-bottom:2px}.pgx .bdg{font-size:10px;padding:1px 6px;border-radius:999px;border:1px solid;white-space:nowrap}
.pgx .up{color:var(--pu);border-color:#22e39a77}.pgx .dn{color:var(--pd);border-color:#ff4d6d77}.pgx .sw{color:var(--pg);border-color:#f5c54277}.pgx .mu{color:var(--pmu)}
.pgx svg{display:block;width:100%}.pgx svg text{font-family:ui-monospace,Menlo,Consolas,monospace}
.pgx .al{margin-top:8px;font-size:12px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}.pgx .al .bar{display:flex;gap:3px}.pgx .al .bar i{width:22px;height:8px;border-radius:2px;background:#333}
.pgx .lg{font-size:10.5px;color:var(--pmu);margin-top:6px;display:flex;flex-wrap:wrap;gap:4px 12px}.pgx .lg span:before{content:"";display:inline-block;width:14px;height:0;border-top:2px solid currentColor;vertical-align:middle;margin-right:4px}.pgx .lg span.d:before{border-top-style:dashed}
.pgx .mk{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}.pgx .mc{border:1px solid var(--pl);border-radius:10px;padding:8px 10px;background:rgba(0,0,0,.25);min-width:0}
.pgx .mc .r1{display:flex;justify-content:space-between;align-items:baseline;gap:6px}.pgx .mc .px{font:700 15px ui-monospace,Menlo,monospace}.pgx .tfs{display:flex;gap:4px;flex-wrap:wrap;margin:5px 0}.pgx .tfs span{font-size:10px;border:1px solid;border-radius:4px;padding:0 4px}
.pgx .hint{font-size:11.5px;line-height:1.4}.pgx table{width:100%;border-collapse:collapse;font-size:11.5px}.pgx td,.pgx th{padding:5px 6px;border-bottom:1px solid var(--pl);text-align:left;vertical-align:top}.pgx th{color:var(--pmu);font-weight:500}
.pgx .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}.pgx .tw table{min-width:720px}.pgx .two{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:14px}.pgx .help{display:none;border:1px solid #36e2ff55;background:#05121a;border-radius:10px;padding:10px 12px;font-size:12px;line-height:1.5;margin-bottom:10px}.pgx .help.on{display:block}.pgx .help b{color:var(--pc)}
.pgx .note{font-size:12px;line-height:1.5;margin:3px 0}.pgx .warn{color:var(--pg);font-size:11.5px}.pgx ul{margin:4px 0 8px;padding-left:18px}.pgx li{margin:3px 0;font-size:12.5px;line-height:1.45}
.pgx.cp .g5{gap:5px}.pgx.cp .ch{padding:4px;border-radius:4px}.pgx.cp .mc{border-radius:4px}.pgx.cp .hd b{font-size:11px;letter-spacing:2px;color:#8a93a6;font-weight:600}
@media(max-width:980px){.pgx .g5{grid-template-columns:repeat(3,minmax(0,1fr))}.pgx .two{grid-template-columns:minmax(0,1fr)}}
@media(max-width:620px){.pgx .g5{grid-template-columns:repeat(2,minmax(0,1fr))}.pgx .g5 .ch:first-child{grid-column:1/-1}}
@media(max-width:360px){.pgx .g5{grid-template-columns:1fr}}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  // ---------- indicators (same rules as mtf.py) ----------
  const ema = (a, n) => { const k = 2 / (n + 1); let e = null; return a.map(x => e = e == null ? x : x * k + e * (1 - k)); };
  function rsi(a, n = 14) { if (a.length < n + 2) return null; let g = 0, l = 0; for (let i = 1; i <= n; i++) { const d = a[i] - a[i - 1]; g += Math.max(d, 0); l += Math.max(-d, 0); } g /= n; l /= n;
    for (let i = n + 1; i < a.length; i++) { const d = a[i] - a[i - 1]; g = (g * (n - 1) + Math.max(d, 0)) / n; l = (l * (n - 1) + Math.max(-d, 0)) / n; } return l ? +(100 - 100 / (1 + g / l)).toFixed(1) : 100; }
  function trend(c) { if (c.length < 55) return {t: "sideways", rsi: rsi(c)}; const e20 = ema(c, 20), e50 = ema(c, 50), n = c.length - 1, sl = e20[n] - e20[n - 5];
    const t = e20[n] > e50[n] && sl > 0 && c[n] > e20[n] ? "up" : e20[n] < e50[n] && sl < 0 && c[n] < e20[n] ? "down" : "sideways"; return {t, rsi: rsi(c), e20, e50}; }
  const TL = t => t === "up" ? T("ขาขึ้น", "Uptrend") : t === "down" ? T("ขาลง", "Downtrend") : T("ไซด์เวย์", "Sideways");
  const TC = t => t === "up" ? "up" : t === "down" ? "dn" : "sw";

  // ---------- data ----------
  async function pullView() { try { const r = await fetch("view.json?t=" + Date.now(), {cache: "no-store"}); if (r.ok) S.D = await r.json(); } catch (e) {} }
  async function pullCandles() { try { const r = await fetch("candles.json?t=" + Date.now(), {cache: "no-store"}); if (r.ok) S.C = await r.json(); } catch (e) {} }
  const TFS = [["M5", "5m"], ["M15", "15m"], ["H1", "1h"], ["H4", "4h"], ["D1", "1d"]];
  async function pullLive() {
    try {
      const sp = Number((await (await fetch("https://api.gold-api.com/price/XAU", {cache: "no-store"})).json()).price); if (!sp) throw 0;
      const B = "https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&limit=120&interval=";
      const arr = await Promise.all(TFS.map(([, iv]) => fetch(B + iv).then(r => r.json())));
      const last = Number(arr[0][arr[0].length - 1][4]), off = sp - last, C = {};
      TFS.forEach(([tf], i) => C[tf] = arr[i].map(x => [Math.floor(x[0] / 1000), +x[1] + off, +x[2] + off, +x[3] + off, +x[4] + off]));
      S.live = {candles: C, spot: sp, t: new Date().toLocaleTimeString("th-TH", {timeZone: "Asia/Bangkok", hour12: false})};
    } catch (e) {}
    try { const j = await (await fetch("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", {cache: "no-store"})).json(); if (+j.price) S.btc = +j.price; } catch (e) {}
  }
  const gold = () => (S.live && S.live.candles) || (S.C && S.C.candles) || null;

  // ---------- portfolio levels (prices only) ----------
  function levels() {
    const P = (S.D && S.D.pnl) || {}, L = [];
    (P.trades || []).filter(t => t.status === "open").forEach(t => { const b = String(t.side).toLowerCase() === "buy";
      L.push({p: t.entry, k: "e", b, lab: (b ? "BUY " : "SELL ") + F(t.entry, 1)}); if (N(t.sl) != null) L.push({p: t.sl, k: "sl", b, lab: "SL " + F(t.sl, 1)}); if (N(t.tp) != null) L.push({p: t.tp, k: "tp", b, lab: "TP " + F(t.tp, 1)}); });
    (P.pending || []).forEach(o => { const b = /buy/i.test(o.type || ""); const nm = (b ? "BUY" : "SELL") + " LMT";
      L.push({p: o.entry, k: "pe", b, lab: nm + " " + F(o.entry, 1)}); if (N(o.sl) != null) L.push({p: o.sl, k: "sl", b, lab: "SL " + F(o.sl, 1)}); if (N(o.tp) != null) L.push({p: o.tp, k: "tp", b, lab: "TP " + F(o.tp, 1)}); });
    return L.filter(l => N(l.p) != null);
  }

  // ---------- candlestick svg ----------
  function chartSvg(rows, tf, cp) {
    const W = 300, H = cp ? 120 : 170, R = 46, n = cp ? 48 : 64, rs = rows.slice(-n); if (!rs.length) return `<svg viewBox="0 0 ${W} ${H}"><text x="150" y="${H / 2}" text-anchor="middle" fill="#8a93a6" font-size="11">-</text></svg>`;
    let hi = Math.max(...rs.map(r => r[2])), lo = Math.min(...rs.map(r => r[3])); const span0 = hi - lo || 1;
    const lv = levels().filter(l => l.p > lo - span0 * .8 && l.p < hi + span0 * .8); lv.forEach(l => { hi = Math.max(hi, l.p); lo = Math.min(lo, l.p); });
    const pad = (hi - lo) * .06 || 1; hi += pad; lo -= pad;
    const Y = v => (H - 4) - (v - lo) / (hi - lo) * (H - 10), cw = (W - R) / rs.length, X = i => i * cw + cw / 2;
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">`;
    for (let g = 1; g < 4; g++) { const v = lo + (hi - lo) * g / 4; s += `<line x1="0" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="rgba(255,255,255,.05)"/><text x="${W - 2}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end" fill="#5d6b7e" font-size="8">${F(v, 0)}</text>`; }
    // smart money boxes
    if (S.smc && S.D && S.D.smc && S.D.smc.XAUUSD && S.D.smc.XAUUSD[tf]) {
      const z = S.D.smc.XAUUSD[tf], ix = t => { const i = rs.findIndex(r => r[0] >= t); return i < 0 ? rs.length - 1 : i; };
      const box = (o, fill, stroke, lab) => { const y1 = Y(Math.min(hi, o.top)), y2 = Y(Math.max(lo, o.bottom)); if (o.top < lo || o.bottom > hi) return ""; const x = Math.max(0, X(ix(o.t)) - cw / 2);
        return `<rect x="${x.toFixed(1)}" y="${y1.toFixed(1)}" width="${(W - R - x).toFixed(1)}" height="${Math.max(1, y2 - y1).toFixed(1)}" fill="${fill}" stroke="${stroke}" stroke-width=".6" stroke-dasharray="${o.mitigated || o.filled ? "2 2" : ""}"/><text x="${(x + 2).toFixed(1)}" y="${(y1 + 8).toFixed(1)}" fill="${stroke}" font-size="7.5">${lab}</text>`; };
      (z.order_blocks || []).forEach(o => s += box(o, o.type === "bullish" ? "rgba(34,227,154,.13)" : "rgba(255,61,154,.13)", o.type === "bullish" ? "#22e39a" : "#ff3d9a", (o.type === "bullish" ? "OB+" : "OB-") + (o.mitigated ? T(" ใช้แล้ว", " used") : "")));
      (z.fvg || []).forEach(o => s += box(o, o.type === "bullish" ? "rgba(54,226,255,.10)" : "rgba(255,170,60,.10)", o.type === "bullish" ? "#36e2ff" : "#ffaa3c", o.type === "bullish" ? "FVG+" : "FVG-"));
      if (z.zone && N(z.zone.eq) != null && z.zone.eq > lo && z.zone.eq < hi) s += `<line x1="0" x2="${W - R}" y1="${Y(z.zone.eq).toFixed(1)}" y2="${Y(z.zone.eq).toFixed(1)}" stroke="#a78bfa" stroke-dasharray="1 3"/><text x="2" y="${(Y(z.zone.eq) - 2).toFixed(1)}" fill="#a78bfa" font-size="7.5">EQ</text>`;
    }
    const tr = trend(rows.map(r => r[4])), off = rows.length - rs.length;
    ["e20", "e50"].forEach((k, j) => { if (!tr[k]) return; const pts = rs.map((r, i) => `${X(i).toFixed(1)},${Y(tr[k][off + i]).toFixed(1)}`).join(" "); s += `<polyline points="${pts}" fill="none" stroke="${j ? "#a78bfa" : "#f5c542"}" stroke-width=".9" opacity=".8"/>`; });
    rs.forEach((r, i) => { const up = r[4] >= r[1], c = up ? "#22e39a" : "#ff4d6d", x = X(i), bt = Y(Math.max(r[1], r[4])), bb = Y(Math.min(r[1], r[4]));
      s += `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${Y(r[2]).toFixed(1)}" y2="${Y(r[3]).toFixed(1)}" stroke="${c}" stroke-width=".7"/><rect x="${(x - cw * .35).toFixed(1)}" y="${bt.toFixed(1)}" width="${(cw * .7).toFixed(1)}" height="${Math.max(.8, bb - bt).toFixed(1)}" fill="${c}"/>`; });
    let used = [];
    lv.forEach(l => { const y = Y(l.p), col = l.k === "sl" ? "#ff4d6d" : l.k === "tp" ? "#36e2ff" : l.b ? "#22e39a" : "#ff3d9a", dash = l.k === "e" ? "" : l.k === "pe" ? "5 3" : "2 2";
      s += `<line x1="0" x2="${W - R}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${col}" stroke-width="${l.k === "e" || l.k === "pe" ? 1.1 : .8}" stroke-dasharray="${dash}"/>`;
      let ly = y; while (used.some(u => Math.abs(u - ly) < 8)) ly += 8; used.push(ly);
      if (!cp) s += `<text x="${W - R - 2}" y="${(ly - 2).toFixed(1)}" text-anchor="end" fill="${col}" font-size="7.5">${esc(l.lab)}</text>`; });
    const c = rs[rs.length - 1][4]; s += `<rect x="${W - R + 1}" y="${(Y(c) - 6).toFixed(1)}" width="${R - 2}" height="12" rx="2" fill="#f5c542"/><text x="${W - 3}" y="${(Y(c) + 3).toFixed(1)}" text-anchor="end" fill="#111" font-size="8.5" font-weight="700">${F(c, 1)}</text>`;
    return s + "</svg>";
  }
  function mtfHtml(cp) {
    const G = gold(), D = S.D || {};
    const head = `<div class="hd"><b>${cp ? "MULTI-TIMEFRAME · XAUUSD" : T("หลายไทม์เฟรม XAUUSD (M5 · M15 · H1 · H4 · D1)", "Multi-timeframe XAUUSD (M5 · M15 · H1 · H4 · D1)")}</b><small>${S.live ? T("สด ", "live ") + S.live.t + T(" น.", "") : S.C ? T("ข้อมูล ", "data ") + esc(S.C.updated) : "-"}</small><span class="sp"></span><button class="btn ${S.smc ? "on" : ""}" data-smc>Smart Money ${S.smc ? "ON" : "OFF"}</button></div>`;
    if (!G) return head + `<div class="mu">-</div>`;
    let ups = 0, dns = 0;
    const cells = TFS.map(([tf]) => { const rows = G[tf] || []; const tr = rows.length ? trend(rows.map(r => r[4])) : {t: null, rsi: null}; if (tr.t === "up") ups++; if (tr.t === "down") dns++;
      return `<div class="ch"><div class="t"><b>${tf}</b><span class="bdg ${tr.t ? TC(tr.t) : "mu"}">${tr.t ? TL(tr.t) : "-"}</span><span class="mu">RSI ${tr.rsi != null ? tr.rsi : "-"}</span></div>${chartSvg(rows, tf, cp)}</div>`; }).join("");
    const side = ups > dns ? "up" : dns > ups ? "down" : "mixed";
    const bar = TFS.map(([tf]) => { const rows = G[tf] || []; const t = rows.length ? trend(rows.map(r => r[4])).t : null; return `<i title="${tf}" style="background:${t === "up" ? "#22e39a" : t === "down" ? "#ff4d6d" : "#f5c542"}"></i>`; }).join("");
    const al = `<div class="al"><b>${T("ความสอดคล้องหลายไทม์เฟรม", "Multi-timeframe alignment")}:</b><span class="bar">${bar}</span><span class="up">${T("ขึ้น", "Up")} ${ups}/5</span><span class="dn">${T("ลง", "Down")} ${dns}/5</span><span class="sw">${T("ไซด์เวย์", "Sideways")} ${5 - ups - dns}/5</span><span>${side === "up" ? T("ภาพรวมเอียงขึ้น", "Overall leaning up") : side === "down" ? T("ภาพรวมเอียงลง", "Overall leaning down") : T("ภาพรวมยังไม่ชัด รอ", "No clear direction, wait")}</span></div>`;
    const lg = `<div class="lg"><span style="color:#f5c542">EMA20</span><span style="color:#a78bfa">EMA50</span><span style="color:#22e39a">${T("ไม้ Buy", "Buy position")}</span><span class="d" style="color:#22e39a">${T("ออเดอร์รอ", "Pending order")}</span><span class="d" style="color:#ff4d6d">SL</span><span class="d" style="color:#36e2ff">TP</span>${S.smc ? `<span style="color:#22e39a">OB+ / OB-</span><span style="color:#36e2ff">FVG</span><span class="d" style="color:#a78bfa">EQ = ${T("กึ่งกลางกรอบ", "range mid")}</span>` : ""}<span>${T("ราคาสปอต (PAXG ปรับเข้าราคาสปอต)", "Spot-based (PAXG offset to spot)")} · ${T("แนวโน้ม = EMA20 เทียบ EMA50 + ความชัน + ตำแหน่งราคา", "trend = EMA20 vs EMA50 + slope + price position")}</span></div>`;
    return head + `<div class="g5">${cells}</div>` + al + lg;
  }
  function spark(a, up) { if (!a || a.length < 2) return ""; const mn = Math.min(...a), mx = Math.max(...a), rg = mx - mn || 1; const pts = a.map((v, i) => `${(i / (a.length - 1) * 200).toFixed(1)},${(30 - (v - mn) / rg * 26).toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 200 32" preserveAspectRatio="none" style="height:32px"><polyline points="${pts}" fill="none" stroke="${up ? "#22e39a" : "#ff4d6d"}" stroke-width="1.3" vector-effect="non-scaling-stroke"/></svg>`; }
  function marketsHtml(cp) {
    const D = S.D || {}, M = (EN && D.markets_en) || D.markets || [];
    const head = `<div class="hd"><b>${cp ? "MARKETS" : T("ตลาดอื่น (FX และ Bitcoin)", "Markets (FX and Bitcoin)")}</b><small>${T("วิเคราะห์อย่างเดียว ไม่ได้เทรด · ข้อมูล ", "Analysis only, not traded · data ")}${esc(D.mtf_updated || "-")}</small></div>`;
    if (!M.length) return head + `<div class="mu">-</div>`;
    return head + `<div class="mk">` + M.map(m => { const live = m.symbol === "BTCUSD" && S.btc, px = live ? S.btc : m.price, ch = N(m.chg_pct);
      return `<div class="mc"><div class="r1"><b>${esc(m.symbol)}</b><span class="px">${F(px, m.dp)}</span><span class="${ch == null ? "mu" : ch >= 0 ? "up" : "dn"}" style="font-size:11px">${ch == null ? "-" : (ch >= 0 ? "+" : "") + ch.toFixed(2) + "%"}</span></div>
      ${spark(m.spark, ch == null || ch >= 0)}<div class="tfs">${(m.tfs || []).map(t => `<span class="${TC(t.trend)}">${t.tf} ${t.trend === "up" ? T("ขึ้น", "UP") : t.trend === "down" ? T("ลง", "DN") : T("ข้าง", "SIDE")} ${t.rsi != null ? Math.round(t.rsi) : "-"}</span>`).join("")}</div>
      <div class="hint"><b class="${m.bias === "up" ? "up" : m.bias === "down" ? "dn" : "sw"}" style="border:0">${esc(m.bias_label || "-")}</b> · ${esc(m.setup || "-")}</div>
      ${!cp ? `<div class="mu" style="font-size:10.5px;margin-top:3px">S ${F(m.support, m.dp)} · R ${F(m.resistance, m.dp)}${live ? T(" · ราคาสด Binance", " · live Binance price") : ""}</div>` : ""}</div>`; }).join("") + `</div>`;
  }
  const HELP = () => `<div class="help" data-helpbox><b>OB (Order Block)</b> ${T("= แท่งเทียนสีตรงข้ามแท่งสุดท้ายก่อนราคาพุ่งแรงจนทะลุโครงสร้าง มักเป็นจุดที่รายใหญ่วางออเดอร์ ราคากลับมาแตะมักมีแรงเด้ง (ใช้แล้ว = ราคากลับมาแตะแล้ว)", "= the last opposite-colour candle before a strong move that breaks structure; often where big players placed orders, so price may react when it returns (used = price has already come back to it)")}<br>
  <b>FVG (Fair Value Gap)</b> ${T("= ช่องว่างราคาจากแท่งที่วิ่งเร็ว (ไส้แท่งที่ 1 กับแท่งที่ 3 ไม่ซ้อนกัน) ราคามักกลับมาปิดช่องว่าง", "= a price gap left by a fast candle (wicks of candle 1 and 3 do not overlap); price often comes back to fill it")}<br>
  <b>BOS (Break of Structure)</b> ${T("= ราคาปิดทะลุจุดสูงสุด/ต่ำสุดเดิมไปทางเดียวกับแนวโน้ม แปลว่าแนวโน้มยังไปต่อ", "= price closes beyond the last swing high/low in the trend direction; the trend continues")}<br>
  <b>CHoCH (Change of Character)</b> ${T("= ราคาทะลุโครงสร้างสวนทางแนวโน้มเดิมเป็นครั้งแรก สัญญาณแรกว่าอาจกลับตัว", "= the first break of structure against the old trend; an early sign of a possible reversal")}<br>
  <b>${T("Liquidity (สภาพคล่อง)", "Liquidity")}</b> ${T("= จุดที่มีคำสั่ง Stop กองอยู่มาก เช่น ยอดเท่ากัน (equal highs) ก้นเท่ากัน (equal lows) หรือยอด/ก้นล่าสุด ราคามักวิ่งไปกวาดก่อนกลับตัว", "= places where many stop orders sit, such as equal highs, equal lows or the latest swing high/low; price often sweeps them before turning")}<br>
  <b>Premium / Discount</b> ${T("= ราคาอยู่ครึ่งบนของกรอบ (แพง ระวังไล่ซื้อ) หรือครึ่งล่าง (ถูก ระวังไล่ขาย) EQ คือกึ่งกลาง", "= price in the upper half of the range (expensive, avoid chasing buys) or lower half (cheap, avoid chasing sells); EQ is the middle")}</div>`;
  function smcHtml(cp) {
    const D = S.D || {};
    const head = `<div class="hd"><b>${cp ? "SMART MONEY" : T("โหมด Smart Money", "Smart Money mode")}</b><small>${T("วิเคราะห์อย่างเดียว · ", "Analysis only · ")}${esc(D.mtf_updated || "-")}</small><span class="sp"></span><button class="btn" data-help>${T("คำศัพท์", "Terms")}</button><button class="btn ${S.smc ? "on" : ""}" data-smc>${S.smc ? "ON" : "OFF"}</button></div>`;
    if (!S.smc) return head + `<div class="mu" style="font-size:12px">${T("กด ON เพื่อดูตารางความสัมพันธ์ของตลาด, Order Block, FVG, BOS/CHoCH, จุดสภาพคล่อง และโซนแพง/ถูก (และวาดโซนบนกราฟหลายไทม์เฟรม)", "Press ON to see the market correlation matrix, order blocks, FVGs, BOS/CHoCH, liquidity and premium/discount zones (also drawn on the multi-timeframe charts)")}</div>` + HELP();
    const C = (D.correlations || {})[S.corrTf];
    let hm = `<div class="mu">-</div>`;
    if (C && C.symbols) { const n = C.symbols.length, cs = 26, L = 46, sz = L + n * cs;
      hm = `<svg viewBox="0 0 ${sz} ${sz}" style="max-width:${sz + 40}px">` + C.symbols.map((s, i) => `<text x="${L - 3}" y="${L + i * cs + cs / 2 + 3}" text-anchor="end" fill="#8a93a6" font-size="8">${s}</text><text transform="translate(${L + i * cs + cs / 2 + 3},${L - 3}) rotate(-60)" fill="#8a93a6" font-size="8">${s}</text>`).join("") +
        C.matrix.map((row, i) => row.map((v, j) => { const a = v == null ? 0 : Math.abs(v), col = v == null ? "#222" : v >= 0 ? `rgba(54,226,255,${(.12 + a * .85).toFixed(2)})` : `rgba(255,61,154,${(.12 + a * .85).toFixed(2)})`;
          return `<rect x="${L + j * cs}" y="${L + i * cs}" width="${cs - 1}" height="${cs - 1}" fill="${col}"/><text x="${L + j * cs + cs / 2}" y="${L + i * cs + cs / 2 + 3}" text-anchor="middle" fill="#fff" font-size="7.5">${v == null ? "-" : v.toFixed(2)}</text>`; }).join("")).join("") + `</svg>`; }
    const notes = ((EN ? D.correlations_notes_en : D.correlations_notes) || D.correlations_notes || []).filter(x => x.startsWith(S.corrTf));
    const corr = `<div><div class="hd" style="margin-bottom:4px"><small>${T("ความสัมพันธ์ (ผลตอบแทน 50 แท่งล่าสุด)", "Correlation (last 50 bars of returns)")}</small><span class="sp"></span>${["H1", "D1"].map(t => `<button class="btn ${S.corrTf === t ? "on" : ""}" data-ctf="${t}">${t}</button>`).join("")}</div>${hm}
      <div class="lg" style="margin:2px 0 6px"><span style="color:#36e2ff">${T("+ ไปทางเดียวกัน", "+ move together")}</span><span style="color:#ff3d9a">${T("- สวนทางกัน", "- move opposite")}</span><span>DXY = ${T("ดัชนีดอลลาร์", "US dollar index")}</span></div>${notes.map(x => `<div class="note">${esc(x)}</div>`).join("") || ""}</div>`;
    const sm = D.smc || {}, NT = (EN ? D.smc_notes_en : D.smc_notes) || {};
    const dp = s => s === "BTCUSD" ? 0 : s === "XAUUSD" ? 2 : s === "USDJPY" ? 3 : 5;
    const ev = e => !e ? "-" : ({bos_bull: T("BOS ขึ้น", "BOS up"), bos_bear: T("BOS ลง", "BOS down"), choch_bull: T("CHoCH เป็นขึ้น", "CHoCH to up"), choch_bear: T("CHoCH เป็นลง", "CHoCH to down")}[e] || e);
    const rows = Object.keys(sm).map(s => { const z = (sm[s] || {})[S.smcTf]; if (!z) return `<tr><td><b>${s}</b></td><td colspan="5">-</td></tr>`;
      const ob = (z.order_blocks || []).filter(o => !o.mitigated).slice(-2).map(o => `<span class="${o.type === "bullish" ? "up" : "dn"}">${o.type === "bullish" ? "OB+" : "OB-"} ${F(o.bottom, dp(s))}-${F(o.top, dp(s))}</span>`).join("<br>") || "-";
      const fv = (z.fvg || []).slice(-2).map(o => `<span style="color:${o.type === "bullish" ? "#36e2ff" : "#ffaa3c"}">${o.type === "bullish" ? "FVG+" : "FVG-"} ${F(o.bottom, dp(s))}-${F(o.top, dp(s))}</span>`).join("<br>") || "-";
      const lq = (z.liquidity || []).map(l => `${({equal_highs: T("ยอดเท่ากัน", "Equal highs"), equal_lows: T("ก้นเท่ากัน", "Equal lows"), swing_high: T("ยอดล่าสุด", "Swing high"), swing_low: T("ก้นล่าสุด", "Swing low")})[l.type] || l.type} ${F(l.level, dp(s))}`).slice(-3).join("<br>");
      const zn = z.zone ? `${z.zone.name === "premium" ? T("แพง (Premium)", "Premium") : z.zone.name === "discount" ? T("ถูก (Discount)", "Discount") : T("กลาง (EQ)", "Equilibrium")} ${z.zone.pos_pct}%` : "-";
      return `<tr><td><b>${s}</b>${!cp && NT[s] && S.smcTf === "H1" ? `<div class="mu" style="font-size:10.5px;max-width:260px">${esc(NT[s])}</div>` : ""}</td><td>${ev(z.last_event)}</td><td>${zn}</td><td>${ob}</td><td>${fv}</td><td>${lq || "-"}</td></tr>`; }).join("");
    const tab = `<div><div class="hd" style="margin-bottom:4px"><small>${T("วิเคราะห์ SMC ต่อสินทรัพย์", "SMC by instrument")}</small><span class="sp"></span>${["M15", "H1", "H4"].map(t => `<button class="btn ${S.smcTf === t ? "on" : ""}" data-stf="${t}">${t}</button>`).join("")}</div>
      <div class="tw"><table><tr><th>${T("สินทรัพย์", "Symbol")}</th><th>${T("โครงสร้างล่าสุด", "Last structure")}</th><th>${T("โซน", "Zone")}</th><th>${T("OB ยังไม่ถูกทดสอบ", "Untested OB")}</th><th>FVG</th><th>${T("สภาพคล่อง", "Liquidity")}</th></tr>${rows || `<tr><td colspan="6">-</td></tr>`}</table></div></div>`;
    return head + HELP() + `<div class="two">${corr}${tab}</div>`;
  }
  function edgeHtml(cp) {
    const E = (S.D || {}).edge; const head = `<div class="hd"><b>${cp ? "AI EDGE" : T("AI Edge: อะไรได้ผลจริงจากประวัติเทรด", "AI Edge: what has actually worked")}</b><small>${E ? esc(E.updated || "") : "-"}</small></div>`;
    if (!E) return head + `<div class="mu">-</div>`;
    const nt = (EN ? E.notes_en : E.notes) || [], t = E.total || {};
    const best = nt.filter(x => /^(ดีสุด|Best)/.test(x)), worst = nt.filter(x => /^(แย่สุด|Worst)/.test(x)), other = nt.filter(x => !best.includes(x) && !worst.includes(x));
    const strip = x => esc(x.replace(/^(ดีสุด|แย่สุด|Best|Worst):\s*/, ""));
    return head + `<div class="note"><b>${T("ทั้งหมด", "All")}:</b> ${t.n != null ? t.n : "-"} ${T("ไม้", "trades")} · ${T("ชนะ", "win")} ${t.win_rate != null ? t.win_rate + "%" : "-"} · ${T("เฉลี่ย", "avg")} ${t.expectancy_usc != null ? (t.expectancy_usc >= 0 ? "+" : "") + t.expectancy_usc + " USC/" + T("ไม้", "trade") : "-"} · PF ${t.profit_factor != null ? t.profit_factor : "-"}</div>
      <div class="up" style="font-size:12px;margin-top:6px;border:0">${T("ได้ผลดีที่สุด", "Worked best")}</div><ul>${best.map(x => `<li>${strip(x)}</li>`).join("") || "<li>-</li>"}</ul>
      <div class="dn" style="font-size:12px;border:0">${T("ได้ผลแย่ที่สุด", "Worked worst")}</div><ul>${worst.map(x => `<li>${strip(x)}</li>`).join("") || "<li>-</li>"}</ul>
      ${other.map(x => `<div class="warn">${esc(x)}</div>`).join("")}`;
  }
  const R = {mtf: mtfHtml, markets: marketsHtml, smc: smcHtml, edge: edgeHtml};
  function render() { S.mounts.forEach(m => { const h = m.el.querySelector("[data-helpbox].on"); m.el.innerHTML = R[m.kind](m.cp); if (h) { const n = m.el.querySelector("[data-helpbox]"); n && n.classList.add("on"); } }); }
  document.addEventListener("click", e => { const b = e.target.closest && e.target.closest(".pgx [data-smc],.pgx [data-ctf],.pgx [data-stf],.pgx [data-help]"); if (!b) return;
    if (b.hasAttribute("data-smc")) { S.smc = !S.smc; localStorage.setItem("gd_smc", S.smc ? "1" : "0"); }
    if (b.dataset.ctf) S.corrTf = b.dataset.ctf; if (b.dataset.stf) S.smcTf = b.dataset.stf;
    if (b.hasAttribute("data-help")) { const h = b.closest(".pgx").querySelector("[data-helpbox]"); if (h) h.classList.toggle("on"); return; }
    render(); });
  let started = false;
  async function start() { if (started) return; started = true; await Promise.all([pullView(), pullCandles()]); render(); await pullLive(); render();
    setInterval(async () => { await pullView(); render(); }, 20000); setInterval(async () => { await pullLive(); render(); }, 30000); setInterval(pullCandles, 300000); }
  window.PGX = {mount(el, kind, o = {}) { if (!el) return; el.classList.add("pgx", "notr"); if (o.compact) el.classList.add("cp"); S.mounts.push({el, kind, cp: !!o.compact}); el.innerHTML = `<div class="mu">-</div>`; start(); }, state: S};
})();
