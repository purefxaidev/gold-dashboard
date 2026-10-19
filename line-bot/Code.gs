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
 */

var CHAT_MODEL = 'gemini-3.8-flash';      // REST generateContent รับ text/ภาพ/เสียง
var TTS_MODEL  = 'gemini-3.8-flash-tts';  // REST TTS -> PCM 16-bit mono (24 kHz)
var TTS_VOICE  = 'Kore';
var DASHBOARD_URL = 'https://purefxaidev.github.io/gold-dashboard/view.json';
var PRICE_URL     = 'https://api.gold-api.com/price/XAU';
var MAX_REPLY_CHARS = 4500;
var DRIVE_FOLDER_NAME = 'line-gold-bot-audio';

var SYSTEM_PROMPT = [
  'คุณคือผู้ช่วยนักวิเคราะห์ทองคำ (XAUUSD) ระยะสั้น (M5–H1) ตอบเป็นภาษาไทย กระชับ อ่านง่ายบนมือถือ',
  'ใช้ข้อมูลบริบท (ราคาสด แนวรับแนวต้าน แผนเทรด % ความมั่นใจ AI ค่า EV และข่าว) ที่แนบมาเป็นหลัก ถ้าข้อมูลไม่พอให้บอกตรงๆ',
  'ถ้าผู้ใช้ส่งภาพกราฟ ให้อ่านเทรนด์ แนวรับแนวต้าน และรูปแบบแท่งเทียนจากภาพ ถ้าส่งเสียง ให้ฟังคำถามแล้วตอบ',
  'ทุกครั้งที่แนะนำจุดเข้า ต้องระบุ ฝั่ง (Buy/Sell) จุดเข้า SL และ TP ชัดเจน พร้อมเหตุผลสั้นๆ',
  'ห้ามรับประกันหรือสัญญาว่าจะได้กำไร ปิดท้ายทุกคำตอบด้วยคำเตือนความเสี่ยงสั้นๆ 1 บรรทัด',
  'ห้ามขอหรือเปิดเผยรหัสผ่าน เลขบัญชี หรือ API key ใดๆ'
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

  // --- LINE webhook ---
  // Apps Script อ่าน HTTP header ไม่ได้ จึงตรวจ X-Line-Signature ไม่ได้ -> ใช้ WEBHOOK_KEY ใน URL แทน
  var wk = prop_('WEBHOOK_KEY');
  if (wk && (!e.parameter || e.parameter.key !== wk)) return json_({ ok: true });
  (body.events || []).forEach(function (ev) {
    try { handleEvent_(ev); } catch (err) {
      console.error(err);
      if (ev.replyToken) lineSend_('reply', { replyToken: ev.replyToken,
        messages: [{ type: 'text', text: 'ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งครับ' }] });
    }
  });
  return json_({ ok: true });
}
function doGet() { return ContentService.createTextOutput('LINE gold bot OK'); }
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
  }).concat([{ type: 'action', action: { type: 'message', label: '📈 วิเคราะห์ทอง', text: '/วิเคราะห์' } }]) };
}
function handleCommand_(ev, t) {
  var uid = ev.source && ev.source.userId, rt = ev.replyToken;
  if (/^\/(วิเคราะห์|analyst)/i.test(t)) {
    setMode_(uid, '');
    lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: '📈 กลับสู่โหมดวิเคราะห์ทองแล้วครับ' }] });
    return true;
  }
  var mm = /^\/(แปล|translate|tr)\s*([a-z]{2})?/i.exec(t);
  if (mm) {
    var code = (mm[2] || '').toLowerCase();
    if (!LANGS[code]) {
      lineSend_('reply', { replyToken: rt, messages: [{ type: 'text', text: '🌐 เลือกภาษาปลายทาง (หรือพิมพ์ /แปล en):', quickReply: langQuickReply_() }] });
    } else {
      setMode_(uid, code);
      lineSend_('reply', { replyToken: rt, messages: [{ type: 'text',
        text: '🌐 โหมดแปลภาษา → ' + LANGS[code] + '\nส่งข้อความหรือเสียงมาได้เลย · พิมพ์ /วิเคราะห์ เพื่อกลับ', quickReply: langQuickReply_() }] });
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
  return { full: full || 'แปลไม่สำเร็จ ลองใหม่ครับ', translation: mt ? mt[1].trim() : full };
}

function handleEvent_(ev) {
  if (ev.type !== 'message' || !ev.replyToken) return;
  var m = ev.message, parts = [];
  if (m.type === 'text' && m.text.charAt(0) === '/' && handleCommand_(ev, m.text.trim())) return;
  var trCode = getMode_(ev.source && ev.source.userId);
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
    lineSend_('reply', { replyToken: ev.replyToken, messages: [{ type: 'text', text: 'ตอนนี้รองรับข้อความ ภาพ และเสียงครับ' }] });
    return;
  }
  if (trCode) {
    var tr = translate_(parts, trCode);
    var tm = [{ type: 'text', text: ('🌐 ' + tr.full).slice(0, MAX_REPLY_CHARS), quickReply: langQuickReply_() }];
    try { var tv = buildVoiceMessage_(tr.translation, true); if (tv) tm.push(tv); } catch (err) { console.warn('TTS skipped: ' + err); }
    var c2 = lineSend_('reply', { replyToken: ev.replyToken, messages: tm });
    if (c2 === 400 && tm.length > 1) lineSend_('reply', { replyToken: ev.replyToken, messages: [tm[0]] });
    return;
  }
  var answer = askGemini_(parts);
  var msgs = [{ type: 'text', text: answer.slice(0, MAX_REPLY_CHARS) }];
  try { var v = buildVoiceMessage_(answer); if (v) msgs.push(v); } catch (err) { console.warn('TTS skipped: ' + err); }
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
  try { var d = UrlFetchApp.fetch(DASHBOARD_URL + '?t=' + Date.now(), { muteHttpExceptions: true });
        if (d.getResponseCode() === 200) out.push('ข้อมูลแดชบอร์ด (JSON): ' + d.getContentText().slice(0, 12000)); } catch (err) {}
  var s = out.join('\n\n') || 'ไม่มีข้อมูลบริบท';
  cache.put('ctx', s, 60);
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

function askGemini_(userParts) {
  var now = Utilities.formatDate(new Date(), 'Asia/Bangkok', 'yyyy-MM-dd HH:mm');
  var j = gemini_(CHAT_MODEL, {
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
    contents: [{ role: 'user', parts: [{ text: 'เวลาไทยตอนนี้: ' + now + '\n\nบริบทตลาด:\n' + getContext_() }].concat(userParts) }],
    generationConfig: { temperature: 0.4, maxOutputTokens: 1200 }
  });
  var ps = (((j.candidates || [])[0] || {}).content || {}).parts || [];
  return ps.map(function (x) { return x.text || ''; }).join('').trim() || 'ขออภัย ยังตอบไม่ได้ ลองถามใหม่ครับ';
}

// ===== เสียง (TTS) =====
function ttsPcm_(text) {
  if (!text) return { ok: false, error: 'empty' };
  var speak = text.replace(/[*#_`>]/g, '').replace(/https?:\/\/\S+/g, '').slice(0, 600);
  var j = gemini_(TTS_MODEL, {
    contents: [{ parts: [{ text: 'อ่านด้วยน้ำเสียงนักวิเคราะห์ที่สุภาพ ชัดเจน: ' + speak }] }],
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
    contents: [{ parts: [{ text: raw ? speak : 'อ่านด้วยน้ำเสียงนักวิเคราะห์ที่สุภาพ ชัดเจน: ' + speak }] }],
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
function lineSend_(kind, payload) { // kind = reply | broadcast
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
