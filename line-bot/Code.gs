/**
 * LINE x Gemini — ผู้ช่วยวิเคราะห์ทองคำ (XAUUSD) ระยะสั้น ภาษาไทย
 * Google Apps Script Web App
 *  - doPost (LINE webhook): รับ ข้อความ / ภาพ / เสียง -> Gemini -> ตอบข้อความ (+เสียง ถ้าเปิด)
 *  - doPost (action=alert): รับแจ้งเตือนจากระบบเทรด -> broadcast ข้อความ (+เสียง ถ้าเปิด)
 *
 * Script Properties (ห้าม hardcode):
 *   LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY, ALERT_SECRET
 * ตัวเลือก:
 *   VOICE_MODE    = off (ค่าเริ่มต้น) | wav_experimental | converter
 *   CONVERTER_URL = บริการแปลง WAV->M4A ของคุณเอง ตอบกลับ {"url":"https://....m4a"}
 *   WEBHOOK_KEY   = ถ้าตั้งไว้ ต้องใส่ ?key=... ท้าย Webhook URL ใน LINE
 *   OWNER_PIN_HASH = PIN เจ้าของสำหรับสั่งเทรดจากหน้าโทรบนเว็บ (salt:sha256) ตั้งด้วยฟังก์ชัน setOwnerPin()
 *
 * คำสั่งเทรดจากหน้าโทร (call.html) ใช้ POST แบบ text/plain (ไม่มี CORS preflight):
 *   {"action":"webcmd","pin":"...","nonce":"...","cmd":{"type":"open|close|modify","symbol","side","lot","sl","tp","scope","breakeven"}}
 *   {"action":"webstatus","pin":"...","id":"c..."}   (ไม่ใส่ id = 5 คำสั่งล่าสุดจากเว็บ)
 *   คำสั่งเข้าคิวเดียวกับ LINE (action=commands) โดยมี source = 'web-call'
 */

var CHAT_MODEL = 'gemini-3.8-flash';      // REST generateContent รับ text/ภาพ/เสียง
var TTS_MODEL  = 'gemini-3.8-flash-tts';  // REST TTS -> PCM 16-bit mono (24 kHz)
var TTS_VOICE  = 'Sulafat';
var DASHBOARD_URL = 'https://purefxaidev.github.io/gold-dashboard/view.json';
var CONTEXT_URL   = 'https://purefxaidev.github.io/gold-dashboard/ai_context.txt'; // compact all-markets context written by build.py
var PRICE_URL     = 'https://api.gold-api.com/price/XAU';
var KNOWLEDGE_URL = 'https://purefxaidev.github.io/gold-dashboard/knowledge.md';
var LESSONS_URL   = 'https://purefxaidev.github.io/gold-dashboard/lessons.md';
var JOURNAL_URL   = 'https://purefxaidev.github.io/gold-dashboard/history/trade_journal.jsonl';
var MAX_REPLY_CHARS = 4500;
var DRIVE_FOLDER_NAME = 'line-gold-bot-audio';

var SYSTEM_PROMPT = [
  'คุณคือ เลขา PUREGOLD (PUREGOLD AI) ผู้ช่วยหญิงชาวไทย พูดสุภาพลงท้ายด้วย ค่ะ/คะ เสมอ (ห้ามใช้ ครับ) เป็นนักวิเคราะห์ทองคำ (XAUUSD) ระยะสั้น และติดตามตลาดอื่นด้วย ได้แก่ EURUSD GBPUSD USDJPY AUDUSD USDCHF USDCAD BTCUSD ตอบเป็นภาษาไทย กระชับ อ่านง่ายบนมือถือ',
  'ตัวตน: ห้ามบอกชื่อโมเดล ชื่อบริษัทผู้พัฒนาโมเดล หรือชื่อเสียงที่ใช้ ถ้าถูกถามให้ตอบว่าเป็น เลขา PUREGOLD ระบบ AI ของ PUREGOLD',
  'ใช้ข้อมูลบริบทที่แนบมาเป็นหลัก (ราคาทองสด แนวรับแนวต้าน แผนเทรด EV หลายไทม์เฟรม Smart Money ความสัมพันธ์ระหว่างตลาด Edge ข่าว และตลาด FX/BTC: ราคา % วันนี้ เทรนด์แต่ละ TF bias และไอเดีย setup) ตลาดอื่นนอกจากทองให้เป็นการวิเคราะห์เท่านั้น ถ้าข้อมูลไม่พอให้บอกตรงๆ',
  'ถ้าผู้ใช้ส่งภาพกราฟ ให้อ่านเทรนด์ แนวรับแนวต้านจากภาพ ถ้าส่งเสียง ให้ฟังคำถามแล้วตอบ',
  'ทุกครั้งที่แนะนำจุดเข้า ต้องระบุ Buy/Sell จุดเข้า SL และ TP พร้อมเหตุผลสั้นๆ',
  'ห้ามใช้อีโมจิ ห้ามใช้ markdown (ห้าม ** # - ตาราง) ตอบเป็นข้อความธรรมดาแบ่งบรรทัดสั้นๆ ห้ามรับประกันหรือสัญญาว่าจะได้กำไร ปิดท้ายด้วยคำเตือนความเสี่ยงสั้นๆ 1 บรรทัด',
  'ห้ามขอหรือเปิดเผยรหัสผ่าน เลขบัญชี เลขออเดอร์ ยอดเงิน อีเมล หรือ API key ใดๆ',
  'ถ้าผู้ใช้อยากสมัคร เปิดบัญชี หรือเริ่มเทรด ให้ตอบขั้นตอนสั้นๆ เตือนความเสี่ยง และใส่ [[SIGNUP]] ไว้ท้ายคำตอบหนึ่งครั้ง (ระบบจะซ่อนแล้วส่งการ์ดสมัครให้)'
].join('\n');

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }

// ===== Entry =====
function doPost(e) {
  var body;
  try { body = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false }); }

  // --- แจ้งเตือนจากระบบเทรด ---
  if (body.action === 'alert') {
    var sec = prop_('ALERT_SECRET');
    if (!sec || body.secret !== sec) return json_({ ok: false, error: 'unauthorized' });
    return json_(handleAlert_(String(body.text || ''), body.voice !== false));
  }

  // --- TTS อย่างเดียว (ให้คอมระบบเทรดแปลงเป็น m4a เอง) ---
  if (body.action === 'tts') {
    var sec2 = prop_('ALERT_SECRET');
    if (!sec2 || body.secret !== sec2) return json_({ ok: false, error: 'unauthorized' });
    try { return json_(ttsPcm_(String(body.text || ''))); }
    catch (err) { return json_({ ok: false, error: String(err).slice(0, 200) }); }
  }

  // --- ระบบเทรดรายงานผลคำสั่ง ---
  if (body.action === 'ack') {
    if (!prop_('ALERT_SECRET') || body.secret !== prop_('ALERT_SECRET')) return json_({ ok: false, error: 'unauthorized' });
    var lock = LockService.getScriptLock(); lock.waitLock(10000);
    try {
      var qq = getQueue_(), hit = null;
      qq.forEach(function (c) { if (c.id === body.id) { c.status = body.ok === false ? 'failed' : 'done'; c.result = String(body.result || '').slice(0, 500); c.done_at = new Date().toISOString(); hit = c; } });
      setQueue_(qq);
    } finally { lock.releaseLock(); }
    if (hit && prop_('OWNER_USER_ID')) lineSend_('push', { to: prop_('OWNER_USER_ID'), messages: [{ type: 'text',
      text: (hit.status === 'done' ? 'ทำคำสั่งเรียบร้อยค่ะ' : 'ทำคำสั่งไม่สำเร็จค่ะ') + '\n' + hit.summary + (hit.result ? '\nผล: ' + hit.result : '') }] });
    return json_({ ok: !!hit });
  }

  // --- คำสั่งเทรดจากหน้าโทรบนเว็บ (เฉพาะเจ้าของ ต้องใช้ PIN) ---
  if (body.action === 'webcmd') return json_(webCmd_(body));
  if (body.action === 'webstatus') return json_(webStatus_(body));

  // --- LINE webhook ---
  // Apps Script อ่าน HTTP header ไม่ได้ จึงตรวจ X-Line-Signature ไม่ได้ -> ใช้ WEBHOOK_KEY ใน URL แทน
  var wk = prop_('WEBHOOK_KEY');
  if (wk && (!e.parameter || e.parameter.key !== wk)) return json_({ ok: true });
  (body.events || []).forEach(function (ev) {
    try { handleEvent_(ev); } catch (err) {
      console.error(err);
      if (ev.replyToken) lineSend_('reply', { replyToken: ev.replyToken,
        messages: [{ type: 'text', text: 'ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งค่ะ' }] });
    }
  });
  return json_({ ok: true });
}
function doGet(e) {
  var q = (e && e.parameter) || {};
  if (q.action === 'autotrade') {
    var sec = prop_('ALERT_SECRET');
    if (!sec || q.secret !== sec) return json_({ ok: false, error: 'unauthorized' });
    return json_({ ok: true, enabled: (prop_('AUTO_TRADE') || 'on') === 'on' });
  }
  if (q.action === 'webstatus') return json_(webStatus_(q));
  if (q.action === 'commands') {
    if (!prop_('ALERT_SECRET') || q.secret !== prop_('ALERT_SECRET')) return json_({ ok: false, error: 'unauthorized' });
    return json_({ ok: true, commands: getQueue_().filter(function (c) { return c.status === 'pending'; }) });
  }
  return ContentService.createTextOutput('LINE gold bot OK');
}
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function handleAlert_(text, wantVoice) {
  if (!text) return { ok: false, error: 'empty' };
  var msgs = [{ type: 'text', text: text.slice(0, 4900) }], voiceOk = false;
  if (wantVoice) {
    try { var v = buildVoiceMessage_(text); if (v) { msgs.push(v); voiceOk = true; } }
    catch (err) { console.warn('alert TTS skipped: ' + err); }
  }
  var code = lineSend_('broadcast', { messages: msgs });
  if (code !== 200 && voiceOk) code = lineSend_('broadcast', { messages: [msgs[0]] }), voiceOk = false;
  return { ok: code === 200, voice: voiceOk, line: code };
}

// ===== คิวคำสั่งจากเจ้าของ (LINE -> ระบบเทรด) =====
var ORDER_ACTIONS = ['close_all', 'close_side', 'move_sl_breakeven', 'modify_sl_tp', 'place_order', 'cancel_pending'];
function getQueue_() { try { return JSON.parse(prop_('CMD_QUEUE') || '[]'); } catch (e) { return []; } }
function setQueue_(q) {
  // Script Property จำกัด ~9 KB ต่อค่า: ตัดคำสั่งเก่าที่ทำเสร็จแล้วออกก่อน จนขนาดพอดี
  q = q.slice(-40); var j = JSON.stringify(q);
  while (Utilities.newBlob(j).getBytes().length > 8500 && q.length > 1) {
    var k = 0; for (var i = 0; i < q.length; i++) if (q[i].status !== 'pending') { k = i; break; }
    q.splice(k, 1); j = JSON.stringify(q);
  }
  PropertiesService.getScriptProperties().setProperty('CMD_QUEUE', j);
}
function enqueueNoLock_(cmd) { var q = getQueue_(), t = Date.now(); while (q.some(function (c) { return c.id === 'c' + t; })) t++; cmd.id = 'c' + t; cmd.status = 'pending'; cmd.created_at = new Date().toISOString(); q.push(cmd); setQueue_(q); return cmd.id; }
function enqueue_(cmd) {
  var lock = LockService.getScriptLock(); lock.waitLock(10000);
  try { return enqueueNoLock_(cmd); }
  finally { lock.releaseLock(); }
}

// ===== คำสั่งเทรดจากหน้าโทรบนเว็บ (call.html) -> คิวเดียวกัน =====
var WEB_SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF', 'USDCAD', 'BTCUSD'];
var WEB_RATE_PER_HOUR = 10, WEB_MAX_BAD_PIN = 5, WEB_LOCK_MIN = 60, WEB_MAX_LOT = 1;
function sha256Hex_(s) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, s, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + (b & 255).toString(16)).slice(-2); }).join('');
}
function safeEq_(a, b) { a = String(a); b = String(b); if (a.length !== b.length) return false; var d = 0; for (var i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i); return d === 0; }
function pinMatches_(pin) {
  var h = prop_('OWNER_PIN_HASH'); if (!h || !pin) return false;
  var i = h.indexOf(':'); pin = String(pin);
  return i > 0 ? safeEq_(sha256Hex_(h.slice(0, i) + pin), h.slice(i + 1).toLowerCase()) : safeEq_(sha256Hex_(pin), h.toLowerCase());
}
/** ตรวจ PIN + ล็อกหลังผิด 5 ครั้ง (เรียกภายใน script lock) คืน null ถ้าผ่าน */
function checkPin_(pin) {
  var sp = PropertiesService.getScriptProperties();
  if (!prop_('OWNER_PIN_HASH')) return { ok: false, error: 'not_configured' };
  var until = Number(prop_('WEB_LOCK_UNTIL') || 0);
  if (until > Date.now()) return { ok: false, error: 'locked', retry_min: Math.ceil((until - Date.now()) / 60000) };
  if (pinMatches_(pin)) { if (prop_('WEB_BAD_PIN')) sp.deleteProperty('WEB_BAD_PIN'); return null; }
  var bad = Number(prop_('WEB_BAD_PIN') || 0) + 1;
  if (bad >= WEB_MAX_BAD_PIN) {
    sp.setProperty('WEB_LOCK_UNTIL', String(Date.now() + WEB_LOCK_MIN * 60000)); sp.deleteProperty('WEB_BAD_PIN');
    return { ok: false, error: 'locked', retry_min: WEB_LOCK_MIN };
  }
  sp.setProperty('WEB_BAD_PIN', String(bad));
  return { ok: false, error: 'bad_pin', tries_left: WEB_MAX_BAD_PIN - bad };
}
function num_(x) { if (x === undefined || x === null || x === '') return null; var n = Number(x); return isFinite(n) && n > 0 ? Math.round(n * 100000) / 100000 : NaN; }
/** ตรวจและแปลงคำสั่งจากเว็บเป็นรูปแบบคิวเดิม {action, params, summary} */
function validateWebCmd_(c) {
  var type = String(c.type || '').toLowerCase();
  var sym = String(c.symbol || 'XAUUSD').toUpperCase().replace(/[^A-Z]/g, '');
  if (sym === 'GOLD' || sym === 'XAU') sym = 'XAUUSD';
  var anySym = sym === 'ALL' && type !== 'open';
  if (!anySym && WEB_SYMBOLS.indexOf(sym) < 0) return { error: 'symbol' };
  var side = String(c.side || '').toLowerCase(), scope = String(c.scope || '').toLowerCase();
  var sl = num_(c.sl), tp = num_(c.tp), lot = num_(c.lot);
  if (sl !== sl || tp !== tp || lot !== lot) return { error: 'number' }; // NaN
  var gold = sym === 'XAUUSD', notes = [], action, p, sum, symTh = anySym ? 'ทุกสินค้า' : sym;
  var sideTxt = function (x) { return x === 'buy' ? 'Buy' : x === 'sell' ? 'Sell' : 'ทุกฝั่ง'; };
  if (type === 'open') {
    if (side !== 'buy' && side !== 'sell') return { error: 'side' };
    if (lot === null) lot = gold ? 0.1 : 0.01;
    if (lot > WEB_MAX_LOT) return { error: 'lot_too_large' };
    if (sl === null || tp === null) return { error: 'sl_tp_required' };
    if (side === 'buy' ? !(sl < tp) : !(sl > tp)) return { error: 'sl_tp_side' };
    if (gold && lot > 0.1) notes.push('gold lot above 0.1 per trade');
    if (!gold && lot > 0.01) notes.push('lot above minimum for ' + sym);
    action = 'place_order'; p = { symbol: sym, side: side, order_type: 'market', lot: lot, sl: sl, tp: tp };
    sum = 'เปิด ' + sideTxt(side) + ' ' + sym + ' ' + lot + ' ล็อต ราคาตลาด SL ' + sl + ' TP ' + tp;
  } else if (type === 'close' || type === 'modify') {
    if (!scope && (side === 'buy' || side === 'sell')) scope = side;
    if (['all', 'buy', 'sell'].indexOf(scope) < 0) return { error: 'scope' };
    var ps = scope === 'all' ? 'any' : scope;
    if (type === 'close') {
      action = scope === 'all' ? 'close_all' : 'close_side'; p = { symbol: sym, side: ps, scope: scope };
      sum = 'ปิดไม้ ' + sideTxt(ps) + ' ' + symTh;
    } else {
      var be = c.breakeven === true || c.breakeven === 'true';
      if (!be && sl === null && tp === null) return { error: 'nothing_to_modify' };
      if (!be && sl !== null && tp !== null && ps !== 'any' && (ps === 'buy' ? !(sl < tp) : !(sl > tp))) return { error: 'sl_tp_side' };
      action = be ? 'move_sl_breakeven' : 'modify_sl_tp'; p = { symbol: sym, side: ps, scope: scope };
      if (sl !== null && !be) p.sl = sl; if (tp !== null) p.tp = tp;
      sum = (be ? 'เลื่อน SL กันทุน' : 'แก้') + ' ไม้ ' + sideTxt(ps) + ' ' + symTh + (p.sl ? ' SL ' + p.sl : '') + (p.tp ? ' TP ' + p.tp : '');
    }
  } else return { error: 'type' };
  return { cmd: { action: action, params: p, summary: sum, text: '[web-call] ' + sum, rule_ok: !notes.length, rule_note: notes.join('; ') } };
}
function webCmd_(b) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return { ok: false, error: 'busy' };
  try {
    var pe = checkPin_(b.pin); if (pe) return pe;
    var v = validateWebCmd_(b.cmd || {}); if (v.error) return { ok: false, error: 'invalid', detail: v.error };
    var q = getQueue_(), nonce = String(b.nonce || '').replace(/[^\w-]/g, '').slice(0, 40);
    if (nonce) for (var i = 0; i < q.length; i++) if (q[i].nonce === nonce) return { ok: true, id: q[i].id, status: q[i].status, summary: q[i].summary, duplicate: true };
    var now = Date.now(), rl = [];
    try { rl = JSON.parse(prop_('WEB_RATE') || '[]'); } catch (e) {}
    rl = rl.filter(function (t) { return now - t < 3600000; });
    if (rl.length >= WEB_RATE_PER_HOUR) return { ok: false, error: 'rate_limited', retry_min: Math.max(1, Math.ceil((rl[0] + 3600000 - now) / 60000)) };
    rl.push(now); PropertiesService.getScriptProperties().setProperty('WEB_RATE', JSON.stringify(rl));
    var cmd = v.cmd; cmd.source = 'web-call'; if (nonce) cmd.nonce = nonce;
    var id = enqueueNoLock_(cmd);
    return { ok: true, id: id, status: 'pending', summary: cmd.summary, rule_ok: cmd.rule_ok, rule_note: cmd.rule_note };
  } finally { lock.releaseLock(); }
}
function webPick_(c) { return { id: c.id, status: c.status, summary: c.summary, result: c.result || '', created_at: c.created_at, done_at: c.done_at || '', rule_ok: c.rule_ok !== false, rule_note: c.rule_note || '' }; }
function webStatus_(b) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return { ok: false, error: 'busy' };
  try { var pe = checkPin_(b.pin); if (pe) return pe; } finally { lock.releaseLock(); }
  var q = getQueue_().filter(function (c) { return c.source === 'web-call'; });
  if (b.id) {
    for (var i = q.length - 1; i >= 0; i--) if (q[i].id === String(b.id)) { var r = webPick_(q[i]); r.ok = true; return r; }
    return { ok: false, error: 'not_found' };
  }
  return { ok: true, commands: q.slice(-5).map(webPick_) };
}
/**
 * ตั้ง PIN เจ้าของ (รันครั้งเดียวจาก Editor):
 * 1) เพิ่ม Script Property ชื่อ OWNER_PIN_NEW = PIN ที่ต้องการ (6-32 ตัว ไม่มีช่องว่าง)
 * 2) เลือกฟังก์ชัน setOwnerPin แล้วกด เรียกใช้ -> เก็บเป็น OWNER_PIN_HASH (salt:sha256) และลบ OWNER_PIN_NEW ให้อัตโนมัติ
 */
function setOwnerPin() {
  var sp = PropertiesService.getScriptProperties(), pin = String(prop_('OWNER_PIN_NEW') || '').trim();
  if (!/^\S{6,32}$/.test(pin)) throw new Error('ตั้ง Script Property OWNER_PIN_NEW เป็น PIN 6-32 ตัว (ไม่มีช่องว่าง) ก่อน แล้วรันใหม่');
  var salt = Utilities.getUuid().replace(/-/g, '');
  sp.setProperty('OWNER_PIN_HASH', salt + ':' + sha256Hex_(salt + pin));
  sp.deleteProperty('OWNER_PIN_NEW'); sp.deleteProperty('WEB_BAD_PIN'); sp.deleteProperty('WEB_LOCK_UNTIL');
  console.log('ตั้ง PIN เรียบร้อย และลบ OWNER_PIN_NEW แล้ว');
}
/** สร้าง ALERT_SECRET แบบสุ่มให้ ถ้ายังไม่มี (ดูค่าได้ที่ การตั้งค่าโปรเจกต์ > คุณสมบัติของสคริปต์ ระบบจะไม่พิมพ์ค่าลงบันทึก) */
function makeAlertSecret() {
  if (prop_('ALERT_SECRET')) { console.log('มี ALERT_SECRET อยู่แล้ว ไม่ได้เปลี่ยน'); return; }
  PropertiesService.getScriptProperties().setProperty('ALERT_SECRET', Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, ''));
  console.log('สร้าง ALERT_SECRET แล้ว ดูค่าได้ในคุณสมบัติของสคริปต์');
}
/** ปลดล็อกหลังใส่ PIN ผิดครบ 5 ครั้ง (รันจาก Editor) */
function unlockWebCmd() { var sp = PropertiesService.getScriptProperties(); sp.deleteProperty('WEB_LOCK_UNTIL'); sp.deleteProperty('WEB_BAD_PIN'); console.log('ปลดล็อกแล้ว'); }
/** แปลงข้อความภาษาธรรมชาติเป็นคำสั่ง (Gemini structured output) */
function parseCommand_(text) {
  var j = gemini_(CHAT_MODEL, {
    systemInstruction: { parts: [{ text: 'แยกว่าข้อความของเจ้าของบอทเป็นคำสั่งเทรดทอง XAUUSD หรือไม่ ถ้าเป็นคำถาม/คุยทั่วไป ให้ is_command=false. action: close_all=ปิดทุกไม้, close_side=ปิดเฉพาะฝั่ง buy/sell, move_sl_breakeven=เลื่อน SL กันทุน, modify_sl_tp=แก้ SL/TP, place_order=เปิดไม้ใหม่หรือตั้ง limit/stop, cancel_pending=ยกเลิกออเดอร์รอ, pause_trading=หยุดเทรดอัตโนมัติ, resume_trading=เปิดเทรดอัตโนมัติ, status=ขอสถานะพอร์ต. summary_th = สรุปคำสั่งภาษาไทยสั้นๆ ชัดเจน ห้ามใช้อีโมจิ ถ้าไม่ระบุล็อตให้ใช้ 0.1' }] },
    contents: [{ role: 'user', parts: [{ text: text }] }],
    generationConfig: { temperature: 0, responseMimeType: 'application/json', responseSchema: { type: 'OBJECT', properties: {
      is_command: { type: 'BOOLEAN' },
      action: { type: 'STRING', enum: ['none', 'close_all', 'close_side', 'move_sl_breakeven', 'modify_sl_tp', 'place_order', 'cancel_pending', 'pause_trading', 'resume_trading', 'status'] },
      params: { type: 'OBJECT', properties: { side: { type: 'STRING', enum: ['buy', 'sell', 'any'] }, order_type: { type: 'STRING', enum: ['market', 'limit', 'stop'] },
        lot: { type: 'NUMBER' }, entry: { type: 'NUMBER' }, sl: { type: 'NUMBER' }, tp: { type: 'NUMBER' } } },
      summary_th: { type: 'STRING' } }, required: ['is_command', 'action', 'summary_th'] } }
  });
  var t = (((j.candidates || [])[0] || {}).content || {}).parts || [];
  try { return JSON.parse(t.map(function (x) { return x.text || ''; }).join('')); } catch (e) { return { is_command: false }; }
}
/** เจ้าของส่งข้อความ (ไม่ใช่ /คำสั่ง): คืน true ถ้าจัดการเป็นคำสั่งแล้ว */
function handleOwnerCommand_(ev, text) {
  var rt = ev.replyToken, sp = PropertiesService.getScriptProperties(), t = text.trim();
  var pend = prop_('PENDING_CMD');
  if (/^ยืนยัน$/.test(t) && pend) {
    var c = JSON.parse(pend); sp.deleteProperty('PENDING_CMD');
    if (Date.now() - c.asked > 10 * 60000) { lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'คำสั่งหมดอายุแล้ว (เกิน 10 นาที) กรุณาสั่งใหม่ค่ะ' }] }); return true; }
    delete c.asked; var id = enqueue_(c);
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'รับคำสั่งแล้วค่ะ (' + id + ')\n' + c.summary + '\nระบบเทรดจะดำเนินการในรอบถัดไป และแจ้งผลกลับมาค่ะ' }] }); return true;
  }
  if (/^ยกเลิก$/.test(t) && pend) { sp.deleteProperty('PENDING_CMD'); lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'ยกเลิกคำสั่งแล้วค่ะ' }] }); return true; }
  var p = parseCommand_(t);
  if (!p || !p.is_command || !p.action || p.action === 'none') return false;
  var cmd = { action: p.action, params: p.params || {}, summary: p.summary_th || p.action, text: t.slice(0, 300) };
  if (ORDER_ACTIONS.indexOf(p.action) >= 0) {
    if (p.action === 'place_order' && !(cmd.params.sl && cmd.params.tp)) {
      lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'ทุกไม้ต้องมี SL (ตัดขาดทุน) และ TP (รับกำไร) ค่ะ กรุณาระบุให้ครบ เช่น buy 0.1 ที่ 4163 sl 4145 tp 4191' }] }); return true; }
    cmd.asked = Date.now(); sp.setProperty('PENDING_CMD', JSON.stringify(cmd));
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'ตรวจสอบคำสั่งค่ะ\n' + cmd.summary + '\n\nพิมพ์ "ยืนยัน" เพื่อส่งคำสั่ง หรือ "ยกเลิก" (หมดอายุใน 10 นาที)',
      quickReply: { items: [{ type: 'action', action: { type: 'message', label: 'ยืนยัน', text: 'ยืนยัน' } }, { type: 'action', action: { type: 'message', label: 'ยกเลิก', text: 'ยกเลิก' } }] } }] });
    return true;
  }
  if (p.action === 'pause_trading' || p.action === 'resume_trading') sp.setProperty('AUTO_TRADE', p.action === 'pause_trading' ? 'off' : 'on');
  var id2 = enqueue_(cmd);
  lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'รับคำสั่งแล้วค่ะ (' + id2 + ')\n' + cmd.summary }] });
  return true;
}

// ===== ความจำต่อผู้ใช้ (Script Properties, จำกัดขนาด) =====
function getMem_(uid) { try { return JSON.parse(prop_('MEM_' + uid) || '') } catch (e) { return { facts: [], hist: [] }; } }
function setMem_(uid, m) {
  if (!uid) return; m.facts = (m.facts || []).slice(-20); m.hist = (m.hist || []).slice(-20);
  var j = JSON.stringify(m); while (j.length > 8500 && m.hist.length) { m.hist.shift(); j = JSON.stringify(m); }
  PropertiesService.getScriptProperties().setProperty('MEM_' + uid, j);
}
function memPrompt_(m) {
  return (m.facts.length ? '\n\nสิ่งที่จำเกี่ยวกับผู้ใช้:\n- ' + m.facts.join('\n- ') : '') +
    '\n\nถ้าผู้ใช้บอกข้อมูลที่ควรจำระยะยาว (ความชอบ สไตล์เทรด เป้าหมาย) ให้ใส่ [[จำ: ข้อความสั้น]] ท้ายคำตอบ';
}
function takeMem_(text, m) {
  var add = [];
  text = text.replace(/\[\[\s*จำ\s*:\s*([^\]]+)\]\]/g, function (_, x) { add.push(x.trim()); return ''; }).trim();
  add.forEach(function (x) { if (m.facts.indexOf(x) < 0) m.facts.push(x); });
  return { text: text + (add.length ? '\n\nจำไว้แล้วค่ะ: ' + add.join(' · ') : ''), added: add.length };
}

// ===== โหมดแปลภาษา (เก็บต่อผู้ใช้ใน Script Properties) =====
var LANGS = { th: 'Thai', en: 'English', zh: 'Chinese (Simplified)', ja: 'Japanese', ko: 'Korean',
              vi: 'Vietnamese', lo: 'Lao', my: 'Burmese', fr: 'French', de: 'German' };
function getMode_(uid) { return uid ? (prop_('MODE_' + uid) || '') : ''; } // '' = วิเคราะห์, หรือรหัสภาษา
function setMode_(uid, v) {
  if (!uid) return; var sp = PropertiesService.getScriptProperties();
  if (v) sp.setProperty('MODE_' + uid, v); else sp.deleteProperty('MODE_' + uid);
}
function langQuickReply_() {
  return { items: Object.keys(LANGS).slice(0, 12).map(function (k) {
    return { type: 'action', action: { type: 'message', label: k + ' ' + LANGS[k].split(' ')[0], text: '/แปล ' + k } };
  }).concat([{ type: 'action', action: { type: 'message', label: 'วิเคราะห์ทอง', text: '/วิเคราะห์' } }]) };
}
// ===== Signup card (Flex) — keyword or AI [[SIGNUP]] marker =====
var SIGNUP_RE = /สมัคร|เปิดบัญชี|เปิดพอร์ต|อยากเทรด|เริ่มเทรด|ลงทะเบียน|sign ?up|open (an |a )?(trading )?account|how (do i |to )start trading|create (an )?account/i;
function signupFlex_() {
  var G = '#d4af37', steps = ['1. กดปุ่มสมัคร Exness ด้านล่าง', '2. กรอกอีเมล ตั้งรหัสผ่าน ยืนยันอีเมล/เบอร์', '3. ยืนยันตัวตน (บัตรประชาชน + ที่อยู่)', '4. เลือกบัญชี Standard แล้วฝากเงิน', '5. ติดตั้งแอป Exness Trade / MT5', '6. เริ่มด้วยล็อตเล็ก ตั้ง SL ทุกไม้'];
  return { type: 'flex', altText: 'สมัครบัญชีเทรด Exness กับ PUREGOLD', contents: { type: 'bubble',
    styles: { body: { backgroundColor: '#0b0d12' }, footer: { backgroundColor: '#0b0d12' } },
    body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
      { type: 'text', text: 'PUREGOLD', color: G, weight: 'bold', size: 'sm' },
      { type: 'text', text: 'เริ่มเทรดทองกับ Exness', color: '#ffffff', weight: 'bold', size: 'lg', wrap: true },
      { type: 'text', text: 'สมัครผ่านลิงก์พาร์ทเนอร์ ใช้เวลาไม่กี่นาที แล้วใช้สัญญาณและเครื่องมือของ PUREGOLD ได้ทันที', color: '#b8bcc8', size: 'xs', wrap: true },
      { type: 'separator', color: '#2a2f3a', margin: 'md' },
      { type: 'box', layout: 'vertical', spacing: 'xs', margin: 'md', contents: steps.map(function (s) { return { type: 'text', text: s, color: '#e6e8ee', size: 'xs', wrap: true }; }) },
      { type: 'text', text: 'คำเตือน: CFD และทองคำมีความเสี่ยงสูง อาจสูญเสียเงินทั้งหมด ไม่มีการรับประกันกำไร', color: '#8a8f9c', size: 'xxs', wrap: true, margin: 'md' } ] },
    footer: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
      { type: 'button', style: 'primary', color: G, height: 'sm', action: { type: 'uri', label: 'สมัคร Exness', uri: 'https://one.exnessonelink.com/a/s2didh6p' } },
      { type: 'button', style: 'secondary', height: 'sm', action: { type: 'uri', label: 'ดูวิธีสมัครทีละขั้น', uri: 'https://purefxaidev.github.io/gold-dashboard/signup.html' } } ] } } };
}
function handleCommand_(ev, t) {
  var uid = ev.source && ev.source.userId, rt = ev.replyToken;
  // --- เจ้าของ + เปิด/ปิดเทรดอัตโนมัติ ---
  if (/^\/สมัคร/.test(t)) { lineSend_('reply', { replyToken: rt, messages: [signupFlex_()] }); return true; }
  var so = /^\/ตั้งเจ้าของ\s+(\S+)/.exec(t);
  if (so && uid) { var okS = prop_('ALERT_SECRET') && so[1] === prop_('ALERT_SECRET');
    if (okS) PropertiesService.getScriptProperties().setProperty('OWNER_USER_ID', uid);
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: okS ? 'ตั้งคุณเป็นเจ้าของบอทแล้วค่ะ' : 'รหัสไม่ถูกต้องค่ะ' }] }); return true; }
  if (/^\/(เปิดเทรด|ปิดเทรด)/.test(t)) {
    if (!uid || uid !== prop_('OWNER_USER_ID')) { lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'คำสั่งนี้ใช้ได้เฉพาะเจ้าของบอทค่ะ' }] }); return true; }
    var on = /^\/เปิดเทรด/.test(t); PropertiesService.getScriptProperties().setProperty('AUTO_TRADE', on ? 'on' : 'off');
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: on ? 'เปิดเทรดอัตโนมัติแล้วค่ะ (มีผลรอบถัดไป)' : 'ปิดเทรดอัตโนมัติแล้วค่ะ ระบบจะวิเคราะห์และแจ้งเตือนอย่างเดียว' }] }); return true; }
  var mj = /^\/จำ\s+([\s\S]+)/.exec(t);
  if (mj && uid) { var m1 = getMem_(uid); m1.facts.push(mj[1].trim().slice(0, 200)); setMem_(uid, m1);
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'จำไว้แล้วค่ะ: ' + mj[1].trim() }] }); return true; }
  if (/^\/ลืม/.test(t) && uid) { PropertiesService.getScriptProperties().deleteProperty('MEM_' + uid);
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'ล้างความจำทั้งหมดแล้วค่ะ' }] }); return true; }
  if (/^\/ความจำ/.test(t) && uid) { var m2 = getMem_(uid);
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'ความจำของเลขา\n' + (m2.facts.length ? m2.facts.map(function (x, i) { return (i + 1) + '. ' + x; }).join('\n') : '(ยังไม่มี)') +
      '\nประวัติแชท: ' + m2.hist.length / 2 + 'รอบล่าสุด\n/จำ ข้อความ = เพิ่ม · /ลืม = ล้างทั้งหมด' }] }); return true; }
  if (/^\/(วิเคราะห์|analyst)/i.test(t)) {
    setMode_(uid, '');
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'กลับสู่โหมดวิเคราะห์ทองแล้วค่ะ' }] });
    return true;
  }
  var mm = /^\/(แปล|translate|tr)\s*([a-z]{2})?/i.exec(t);
  if (mm) {
    var code = (mm[2] || '').toLowerCase();
    if (!LANGS[code]) {
      lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: 'เลือกภาษาปลายทาง (หรือพิมพ์ /แปล en):', quickReply: langQuickReply_() }] });
    } else {
      setMode_(uid, code);
      lineSend_('reply', { replyToken: rt, messages: [{ type: 'text',
        text: 'โหมดแปลภาษา → ' + LANGS[code] + '\nส่งข้อความหรือเสียงมาได้เลย · พิมพ์ /วิเคราะห์ เพื่อกลับ', quickReply: langQuickReply_() }] });
    }
    return true;
  }
  return false;
}
function translate_(parts, code) {
  var lang = LANGS[code] || 'English';
  var j = gemini_(CHAT_MODEL, {
    systemInstruction: { parts: [{ text: 'You are a professional translator. Translate the user message into ' + lang +
      '. If audio is given, transcribe it first. Reply exactly in two lines:\nต้นฉบับ: <original or transcript>\nแปล: <translation in ' + lang +
      '>\nNo commentary. Keep numbers and trading terms.' }] },
    contents: [{ role: 'user', parts: parts }], generationConfig: { temperature: 0.2, maxOutputTokens: 1200 }
  });
  var ps = (((j.candidates || [])[0] || {}).content || {}).parts || [];
  var full = ps.map(function (x) { return x.text || ''; }).join('').trim();
  var mt = /แปล\s*:\s*([\s\S]*)$/.exec(full);
  return { full: full || 'แปลไม่สำเร็จ ลองใหม่ค่ะ', translation: mt ? mt[1].trim() : full };
}

function handleEvent_(ev) {
  if (ev.type !== 'message' || !ev.replyToken) return;
  var m = ev.message, parts = [];
  if (m.type === 'text' && m.text.charAt(0) === '/' && handleCommand_(ev, m.text.trim())) return;
  var trCode = getMode_(ev.source && ev.source.userId);
  if (m.type === 'text' && !trCode && ev.source && ev.source.userId && ev.source.userId === prop_('OWNER_USER_ID') && handleOwnerCommand_(ev, m.text)) return;
  if (m.type === 'text') {
    parts.push({ text: m.text });
  } else if (m.type === 'image' || m.type === 'audio') {
    var blob = getLineContent_(m.id);
    var mime = blob.getContentType() || (m.type === 'image' ? 'image/jpeg' : 'audio/mp4');
    if (m.type === 'audio' && !/^audio\//.test(mime)) mime = 'audio/mp4'; // m4a อาจมาเป็น video/mp4
    parts.push({ inlineData: { mimeType: mime, data: Utilities.base64Encode(blob.getBytes()) } });
    parts.push({ text: trCode ? (m.type === 'image' ? 'Translate the text in this image.' : 'Transcribe and translate this audio.')
      : (m.type === 'image' ? 'วิเคราะห์ภาพกราฟนี้สำหรับเทรดทองระยะสั้น' : 'นี่คือข้อความเสียงจากผู้ใช้ ฟังแล้วตอบคำถาม') });
  } else {
    lineSend_('reply', { replyToken: ev.replyToken, messages: [{ type: 'text', text: 'ตอนนี้รองรับข้อความ ภาพ และเสียงค่ะ' }] });
    return;
  }
  if (trCode) {
    var tr = translate_(parts, trCode);
    var tm = [{ type: 'text', text: (' ' + tr.full).slice(0, MAX_REPLY_CHARS), quickReply: langQuickReply_() }];
    try { var tv = buildVoiceMessage_(tr.translation, true); if (tv) tm.push(tv); } catch (err) { console.warn('TTS skipped: ' + err); }
    var c2 = lineSend_('reply', { replyToken: ev.replyToken, messages: tm });
    if (c2 === 400 && tm.length > 1) lineSend_('reply', { replyToken: ev.replyToken, messages: [tm[0]] });
    return;
  }
  var uid = ev.source && ev.source.userId, mem = uid ? getMem_(uid) : { facts: [], hist: [] };
  var su = m.type === 'text' && SIGNUP_RE.test(m.text);
  var tk = takeMem_(askGemini_(parts, mem), mem), answer = tk.text.replace(/\[\[\s*SIGNUP\s*\]\]/gi, function () { su = true; return ''; }).trim();
  if (uid) { var q = m.type === 'text' ? m.text : '[' + (m.type === 'image' ? 'ภาพ' : 'เสียง') + ']';
    mem.hist.push({ r: 'user', t: q.slice(0, 400) }, { r: 'model', t: answer.slice(0, 600) }); setMem_(uid, mem); }
  var msgs = [{ type: 'text', text: answer.slice(0, MAX_REPLY_CHARS) }];
  if (su) msgs.push(signupFlex_());
  else try { var v = buildVoiceMessage_(answer); if (v) msgs.push(v); } catch (err) { console.warn('TTS skipped: ' + err); }
  var code = lineSend_('reply', { replyToken: ev.replyToken, messages: msgs });
  // reply ล้ม (เช่นเสียงไม่ผ่าน) -> ลองส่งแค่ข้อความ (token ยังไม่ถูกใช้ถ้า 400)
  if (code === 400 && msgs.length > 1) lineSend_('reply', { replyToken: ev.replyToken, messages: [msgs[0]] });
}

// ===== บริบทตลาด (แคช 60 วิ เพื่อให้ทัน timeout ของ LINE) =====
function getContext_() {
  var cache = CacheService.getScriptCache(), c = cache.get('ctx');
  if (c) return c;
  var out = [];
  try { var p = UrlFetchApp.fetch(PRICE_URL, { muteHttpExceptions: true });
        if (p.getResponseCode() === 200) out.push('ราคาสด XAU: ' + p.getContentText().slice(0, 500)); } catch (err) {}
  var gotCtx = false;
  try { var ac = UrlFetchApp.fetch(CONTEXT_URL + '?t=' + Date.now(), { muteHttpExceptions: true });
        if (ac.getResponseCode() === 200) { out.push('บริบทตลาดทั้งหมด (ทองคำ FX BTC MTF SMC ความสัมพันธ์ Edge):\n' + ac.getContentText().slice(0, 14000)); gotCtx = true; } } catch (err) {}
  if (!gotCtx) try { var d = UrlFetchApp.fetch(DASHBOARD_URL + '?t=' + Date.now(), { muteHttpExceptions: true });
        if (d.getResponseCode() === 200) out.push('ข้อมูลแดชบอร์ด (JSON): ' + d.getContentText().slice(0, 12000)); } catch (err) {}
  var kb = cache.get('kb');
  if (!kb) { try { var k = UrlFetchApp.fetch(KNOWLEDGE_URL, { muteHttpExceptions: true });
    kb = k.getResponseCode() === 200 ? k.getContentText().slice(0, 9000) : ''; if (kb) cache.put('kb', kb, 3600); } catch (err) { kb = ''; } }
  if (kb) out.push('คลังความรู้ (หลักการตัดสินใจ):\n' + kb);
  var hs = cache.get('hist');
  if (hs === null) { hs = ''; try {
    var l = UrlFetchApp.fetch(LESSONS_URL, { muteHttpExceptions: true }), jn = UrlFetchApp.fetch(JOURNAL_URL, { muteHttpExceptions: true });
    if (l.getResponseCode() === 200) hs += l.getContentText().slice(-3000);
    if (jn.getResponseCode() === 200) hs += '\nบันทึกเทรดล่าสุด:\n' + jn.getContentText().trim().split('\n').slice(-15).join('\n');
    hs = hs.slice(0, 5000); cache.put('hist', hs, 600); } catch (err) {} }
  if (hs) out.push('บทเรียน/ประวัติเทรด:\n' + hs);
  var s = (out.join('\n\n') || 'ไม่มีข้อมูลบริบท').slice(0, 25000);
  cache.put('ctx', s.slice(0, 90000), 60);
  return s;
}

// ===== Gemini (REST) =====
function gemini_(model, payload) {
  var r = UrlFetchApp.fetch('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { 'x-goog-api-key': prop_('GEMINI_API_KEY') }, payload: JSON.stringify(payload)
  });
  if (r.getResponseCode() !== 200) throw new Error(model + ' ' + r.getResponseCode() + ': ' + r.getContentText().slice(0, 300));
  return JSON.parse(r.getContentText());
}

function askGemini_(userParts, mem) {
  mem = mem || { facts: [], hist: [] };
  var now = Utilities.formatDate(new Date(), 'Asia/Bangkok', 'yyyy-MM-dd HH:mm');
  var j = gemini_(CHAT_MODEL, {
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT + memPrompt_(mem) }] },
    contents: mem.hist.map(function (h) { return { role: h.r, parts: [{ text: h.t }] }; }).concat([{ role: 'user', parts: [{ text: 'เวลาไทยตอนนี้: ' + now + '\n\nบริบทตลาด:\n' + getContext_() }].concat(userParts) }]),
    generationConfig: { temperature: 0.4, maxOutputTokens: 1200 }
  });
  var ps = (((j.candidates || [])[0] || {}).content || {}).parts || [];
  return ps.map(function (x) { return x.text || ''; }).join('').trim() || 'ขออภัย ยังตอบไม่ได้ ลองถามใหม่ค่ะ';
}

// ===== เสียง (TTS) =====
function ttsPcm_(text) {
  if (!text) return { ok: false, error: 'empty' };
  var speak = text.replace(/[*#_`>]/g, '').replace(/https?:\/\/\S+/g, '').slice(0, 600);
  var j = gemini_(TTS_MODEL, {
    contents: [{ parts: [{ text: 'อ่านด้วยน้ำเสียงเลขาผู้หญิงที่สุภาพ ชัดเจน: ' + speak }] }],
    generationConfig: { responseModalities: ['AUDIO'],
      speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: TTS_VOICE } } } }
  });
  var inl = j.candidates[0].content.parts[0].inlineData;
  var rate = Number((/rate=(\d+)/.exec(inl.mimeType || '') || [0, 24000])[1]);
  return { ok: true, format: 's16le', channels: 1, sampleRate: rate, pcmBase64: inl.data };
}

function buildVoiceMessage_(text, raw) {
  var mode = (prop_('VOICE_MODE') || 'off').toLowerCase();
  if (mode === 'off') return null;
  var speak = text.replace(/[*#_`>]/g, '').replace(/https?:\/\/\S+/g, '').slice(0, 600);
  var j = gemini_(TTS_MODEL, {
    contents: [{ parts: [{ text: raw ? speak : 'อ่านด้วยน้ำเสียงเลขาผู้หญิงที่สุภาพ ชัดเจน: ' + speak }] }],
    generationConfig: { responseModalities: ['AUDIO'],
      speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: TTS_VOICE } } } }
  });
  var inl = j.candidates[0].content.parts[0].inlineData;     // mimeType เช่น audio/L16;codec=pcm;rate=24000
  var pcm = Utilities.base64Decode(inl.data);
  var rate = Number((/rate=(\d+)/.exec(inl.mimeType || '') || [0, 24000])[1]);
  var durationMs = Math.round(pcm.length / 2 / rate * 1000);
  var wav = pcmToWav_(pcm, rate);
  var url;
  if (mode === 'converter') {
    var cu = prop_('CONVERTER_URL'); if (!cu) return null;
    var cr = UrlFetchApp.fetch(cu, { method: 'post', contentType: 'audio/wav', payload: wav, muteHttpExceptions: true });
    if (cr.getResponseCode() !== 200) return null;
    url = JSON.parse(cr.getContentText()).url;
  } else { // wav_experimental — LINE ระบุให้ใช้ m4a; WAV อาจเล่นไม่ได้ในบางเครื่อง/ถูกปฏิเสธ
    var f = getAudioFolder_().createFile(Utilities.newBlob(wav, 'audio/wav', 'r' + Date.now() + '.wav'));
    f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    url = 'https://drive.google.com/uc?export=download&id=' + f.getId();
  }
  if (!url || url.indexOf('https://') !== 0) return null;
  return { type: 'audio', originalContentUrl: url, duration: durationMs };
}

function pcmToWav_(pcm, rate) {
  var len = pcm.length, h = [];
  function s(t) { for (var i = 0; i < t.length; i++) h.push(t.charCodeAt(i)); }
  function u32(n) { h.push(n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255); }
  function u16(n) { h.push(n & 255, (n >> 8) & 255); }
  s('RIFF'); u32(36 + len); s('WAVE'); s('fmt '); u32(16); u16(1); u16(1);
  u32(rate); u32(rate * 2); u16(2); u16(16); s('data'); u32(len);
  return h.map(function (b) { return b > 127 ? b - 256 : b; }).concat(pcm);
}

function getAudioFolder_() {
  var it = DriveApp.getFoldersByName(DRIVE_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(DRIVE_FOLDER_NAME);
}
/** ตั้ง Trigger รายวัน: ลบไฟล์เสียงเก่ากว่า 1 วัน */
function cleanupAudio() {
  var cutoff = Date.now() - 864e5, fs = getAudioFolder_().getFiles();
  while (fs.hasNext()) { var f = fs.next(); if (f.getDateCreated().getTime() < cutoff) f.setTrashed(true); }
}

// ===== LINE =====
function getLineContent_(id) {
  var r = UrlFetchApp.fetch('https://api-data.line.me/v2/bot/message/' + id + '/content', {
    headers: { Authorization: 'Bearer ' + prop_('LINE_CHANNEL_ACCESS_TOKEN') }, muteHttpExceptions: true });
  if (r.getResponseCode() !== 200) throw new Error('LINE content ' + r.getResponseCode());
  return r.getBlob();
}
function plain_(t) { return String(t).replace(/^\s*#{1,6}\s*/gm, '').replace(/\*\*(.+?)\*\*/g, '$1').replace(/^\s*[-*+]\s+/gm, '• ').replace(/`/g, '').replace(/^\s*-{3,}\s*$/gm, '').replace(/\*/g, ''); }
function lineSend_(kind, payload) {
  (payload.messages || []).forEach(function (m) { if (m.type === 'text') m.text = plain_(m.text); }); // kind = reply | broadcast | push
  if (payload.messages) payload.messages = payload.messages.slice(0, 5);
  var r = UrlFetchApp.fetch('https://api.line.me/v2/bot/message/' + kind, {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + prop_('LINE_CHANNEL_ACCESS_TOKEN') }, payload: JSON.stringify(payload) });
  if (r.getResponseCode() !== 200) console.error('LINE ' + kind + ' ' + r.getResponseCode() + ' ' + r.getContentText());
  return r.getResponseCode();
}

// ===== ทดสอบจาก Editor =====
function testGemini() { console.log(askGemini_([{ text: 'ตอนนี้ทองควรเข้า Buy หรือ Sell ระยะสั้น?' }])); }
function testAlert() { console.log(JSON.stringify(handleAlert_('ทดสอบแจ้งเตือนทองจากระบบ', true))); }

// ===== Rich Menu (รันครั้งเดียวจาก Editor) =====
var CALL_URL = 'https://purefxaidev.github.io/gold-dashboard/call.html';
var DASH_URL = 'https://purefxaidev.github.io/gold-dashboard/';
var RICHMENU_IMG = 'https://purefxaidev.github.io/gold-dashboard/richmenu.png';
function createRichMenu() {
  var tok = prop_('LINE_CHANNEL_ACCESS_TOKEN'), w = 625, h = 843;
  function area(i, action) { return { bounds: { x: i * w, y: 0, width: w, height: h }, action: action }; }
  var menu = { size: { width: 2500, height: 843 }, selected: true, name: 'gold-menu', chatBarText: 'เมนูทองคำ',
    areas: [
      area(0, { type: 'uri', label: 'โทรคุยกับ AI', uri: DASH_URL + '?openExternalBrowser=1#call' }),
      area(1, { type: 'uri', label: 'แดชบอร์ด', uri: DASH_URL }),
      area(2, { type: 'message', label: 'สรุปตอนนี้', text: 'สรุปภาพรวมทองตอนนี้ พร้อมจุดเข้า SL TP' }),
      area(3, { type: 'message', label: 'โหมดแปล', text: '/แปล' })
    ] };
  var r = UrlFetchApp.fetch('https://api.line.me/v2/bot/richmenu', { method: 'post', contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + tok }, payload: JSON.stringify(menu), muteHttpExceptions: true });
  if (r.getResponseCode() !== 200) throw new Error('create ' + r.getContentText());
  var id = JSON.parse(r.getContentText()).richMenuId;
  var img = UrlFetchApp.fetch(RICHMENU_IMG).getBlob();
  var u = UrlFetchApp.fetch('https://api-data.line.me/v2/bot/richmenu/' + id + '/content', { method: 'post', contentType: 'image/png',
    headers: { Authorization: 'Bearer ' + tok }, payload: img.getBytes(), muteHttpExceptions: true });
  if (u.getResponseCode() !== 200) throw new Error('image ' + u.getContentText());
  var d = UrlFetchApp.fetch('https://api.line.me/v2/bot/user/all/richmenu/' + id, { method: 'post',
    headers: { Authorization: 'Bearer ' + tok }, muteHttpExceptions: true });
  console.log('Rich menu ' + id + ' default=' + d.getResponseCode());
}
