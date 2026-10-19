// LINE x Gemini gold bot — Cloudflare Worker version
// Secrets (wrangler secret put): LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY, ALERT_SECRET
// Optional KV binding MODES (translate mode per user). Voice replies: not in Worker (no m4a encoder) — use line_notify_voice.sh for voice alerts.
const CHAT_MODEL = 'gemini-3.8-flash', TTS_MODEL = 'gemini-3.8-flash-tts', TTS_VOICE = 'Sulafat';
const DASHBOARD_URL = 'https://purefxaidev.github.io/gold-dashboard/view.json';
const PRICE_URL = 'https://api.gold-api.com/price/XAU';
const KNOWLEDGE_URL = 'https://purefxaidev.github.io/gold-dashboard/knowledge.md';
const LESSONS_URL = 'https://purefxaidev.github.io/gold-dashboard/lessons.md';
const JOURNAL_URL = 'https://purefxaidev.github.io/gold-dashboard/history/trade_journal.jsonl';
const LANGS = { th: 'Thai', en: 'English', zh: 'Chinese (Simplified)', ja: 'Japanese', ko: 'Korean', vi: 'Vietnamese', lo: 'Lao', my: 'Burmese', fr: 'French', de: 'German' };
const SYSTEM_PROMPT = [
  'คุณคือ เลขา ผู้ช่วยหญิงชาวไทย พูดสุภาพลงท้ายด้วย ค่ะ/คะ เสมอ (ห้ามใช้ ครับ) และเป็นผู้ช่วยนักวิเคราะห์ทองคำ (XAUUSD) ระยะสั้น (M5–H1) ตอบเป็นภาษาไทย กระชับ อ่านง่ายบนมือถือ',
  'ใช้ข้อมูลบริบท (ราคาสด แนวรับแนวต้าน แผนเทรด % ความมั่นใจ AI ค่า EV และข่าว) ที่แนบมาเป็นหลัก ถ้าข้อมูลไม่พอให้บอกตรงๆ',
  'ถ้าผู้ใช้ส่งภาพกราฟ ให้อ่านเทรนด์ แนวรับแนวต้านจากภาพ ถ้าส่งเสียง ให้ฟังคำถามแล้วตอบ',
  'ทุกครั้งที่แนะนำจุดเข้า ต้องระบุ Buy/Sell จุดเข้า SL และ TP พร้อมเหตุผลสั้นๆ',
  'ห้ามใช้อีโมจิ ห้ามรับประกันกำไร ปิดท้ายด้วยคำเตือนความเสี่ยง 1 บรรทัด ห้ามขอหรือเปิดเผยรหัสผ่าน/API key'
].join('\n');

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json' } });
const b64 = buf => { let s = ''; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };

async function verifySig(env, body, sig) {
  if (!sig || !env.LINE_CHANNEL_SECRET) return false;
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.LINE_CHANNEL_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = b64(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(body)));
  return mac.length === sig.length && mac.split('').reduce((a, c, i) => a | (c.charCodeAt(0) ^ sig.charCodeAt(i)), 0) === 0;
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === 'GET' && url.pathname === '/autotrade') {
      if (!env.ALERT_SECRET || url.searchParams.get('secret') !== env.ALERT_SECRET) return json({ ok: false, error: 'unauthorized' }, 401);
      const v = env.MODES ? await env.MODES.get('auto_trade') : null;
      return json({ ok: true, enabled: (v || 'on') === 'on' });
    }
    if (req.method !== 'POST') return new Response('LINE gold bot OK');
    const raw = await req.text();
    if (url.pathname === '/alert' || url.pathname === '/tts') {
      let b; try { b = JSON.parse(raw); } catch { return json({ ok: false }, 400); }
      if (!env.ALERT_SECRET || b.secret !== env.ALERT_SECRET) return json({ ok: false, error: 'unauthorized' }, 401);
      if (url.pathname === '/tts') return json(await tts(env, String(b.text || '')).catch(e => ({ ok: false, error: String(e).slice(0, 200) })));
      const code = await line(env, 'broadcast', { messages: [{ type: 'text', text: String(b.text || '').slice(0, 4900) }] });
      return json({ ok: code === 200, line: code });
    }
    if (!(await verifySig(env, raw, req.headers.get('x-line-signature')))) return new Response('bad signature', { status: 401 });
    const body = JSON.parse(raw);
    ctx.waitUntil(Promise.all((body.events || []).map(ev => handleEvent(env, ev).catch(async e => {
      console.error(e);
      if (ev.replyToken) await line(env, 'reply', { replyToken: ev.replyToken, messages: [{ type: 'text', text: 'ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งค่ะ' }] });
    }))));
    return new Response('ok');
  }
};

// ---- memory (KV binding MODES, optional) ----
async function getMem(env, uid) { if (!uid || !env.MODES) return { facts: [], hist: [] }; try { return JSON.parse(await env.MODES.get('mem:' + uid)) || { facts: [], hist: [] }; } catch { return { facts: [], hist: [] }; } }
async function setMem(env, uid, m) { if (!uid || !env.MODES) return; m.facts = m.facts.slice(-20); m.hist = m.hist.slice(-20); await env.MODES.put('mem:' + uid, JSON.stringify(m)); }
async function getMode(env, uid) { return uid && env.MODES ? (await env.MODES.get('m:' + uid)) || '' : ''; }
async function setMode(env, uid, v) { if (!uid || !env.MODES) return; v ? await env.MODES.put('m:' + uid, v) : await env.MODES.delete('m:' + uid); }
function quick() {
  return { items: Object.keys(LANGS).map(k => ({ type: 'action', action: { type: 'message', label: k + ' ' + LANGS[k].split(' ')[0], text: '/แปล ' + k } }))
    .concat([{ type: 'action', action: { type: 'message', label: 'วิเคราะห์ทอง', text: '/วิเคราะห์' } }]) };
}
const reply = (env, ev, messages) => line(env, 'reply', { replyToken: ev.replyToken, messages });

async function handleEvent(env, ev) {
  if (ev.type !== 'message' || !ev.replyToken) return;
  const m = ev.message, uid = ev.source && ev.source.userId;
  if (m.type === 'text' && m.text.startsWith('/')) {
    const t = m.text.trim();
    const so = /^\/ตั้งเจ้าของ\s+(\S+)/.exec(t);
    if (so) { const okS = env.ALERT_SECRET && so[1] === env.ALERT_SECRET && env.MODES; if (okS) await env.MODES.put('owner', uid);
      return reply(env, ev, [{ type: 'text', text: okS ? 'ตั้งคุณเป็นเจ้าของบอทแล้วค่ะ' : 'ตั้งไม่สำเร็จค่ะ (รหัสผิด หรือยังไม่ผูก KV)' }]); }
    if (/^\/(เปิดเทรด|ปิดเทรด)/.test(t)) {
      const owner = env.OWNER_USER_ID || (env.MODES && await env.MODES.get('owner'));
      if (!uid || uid !== owner) return reply(env, ev, [{ type: 'text', text: 'คำสั่งนี้ใช้ได้เฉพาะเจ้าของบอทค่ะ' }]);
      if (!env.MODES) return reply(env, ev, [{ type: 'text', text: 'ยังไม่ได้ผูก KV MODES จึงบันทึกไม่ได้ค่ะ' }]);
      const on = /^\/เปิดเทรด/.test(t); await env.MODES.put('auto_trade', on ? 'on' : 'off');
      return reply(env, ev, [{ type: 'text', text: on ? 'เปิดเทรดอัตโนมัติแล้วค่ะ (มีผลรอบถัดไป)' : 'ปิดเทรดอัตโนมัติแล้วค่ะ ระบบจะวิเคราะห์และแจ้งเตือนอย่างเดียว' }]);
    }
    const mj = /^\/จำ\s+([\s\S]+)/.exec(t);
    if (mj || /^\/(ลืม|ความจำ)/.test(t)) {
      if (!env.MODES) return reply(env, ev, [{ type: 'text', text: 'ยังไม่ได้ผูก KV MODES จึงจำไม่ได้ค่ะ' }]);
      const mm0 = await getMem(env, uid);
      if (mj) { mm0.facts.push(mj[1].trim().slice(0, 200)); await setMem(env, uid, mm0); return reply(env, ev, [{ type: 'text', text: 'จำไว้แล้วค่ะ: ' + mj[1].trim() }]); }
      if (/^\/ลืม/.test(t)) { await env.MODES.delete('mem:' + uid); return reply(env, ev, [{ type: 'text', text: 'ล้างความจำทั้งหมดแล้วค่ะ' }]); }
      return reply(env, ev, [{ type: 'text', text: 'ความจำของเลขา\n' + (mm0.facts.map((x, i) => (i + 1) + '. ' + x).join('\n') || '(ยังไม่มี)') + '\n/จำ ข้อความ = เพิ่ม · /ลืม = ล้าง' }]);
    }
    if (/^\/(วิเคราะห์|analyst)/i.test(t)) { await setMode(env, uid, ''); return reply(env, ev, [{ type: 'text', text: 'กลับสู่โหมดวิเคราะห์ทองแล้วค่ะ' }]); }
    const mm = /^\/(แปล|translate|tr)\s*([a-z]{2})?/i.exec(t);
    if (mm) {
      const c = (mm[2] || '').toLowerCase();
      if (!LANGS[c]) return reply(env, ev, [{ type: 'text', text: 'เลือกภาษาปลายทาง:', quickReply: quick() }]);
      await setMode(env, uid, c);
      return reply(env, ev, [{ type: 'text', text: `โหมดแปล → ${LANGS[c]}\nพิมพ์ /วิเคราะห์ เพื่อกลับ` + (env.MODES ? '' : '\n( ยังไม่ผูก KV MODES — โหมดจะไม่ถูกจำ)'), quickReply: quick() }]);
    }
  }
  const tr = await getMode(env, uid), parts = [];
  if (m.type === 'text') parts.push({ text: m.text });
  else if (m.type === 'image' || m.type === 'audio') {
    const r = await fetch(`https://api-data.line.me/v2/bot/message/${m.id}/content`, { headers: { Authorization: 'Bearer ' + env.LINE_CHANNEL_ACCESS_TOKEN } });
    if (!r.ok) throw new Error('LINE content ' + r.status);
    let mime = (r.headers.get('content-type') || '').split(';')[0];
    if (m.type === 'audio' && !mime.startsWith('audio/')) mime = 'audio/mp4';
    if (m.type === 'image' && !mime.startsWith('image/')) mime = 'image/jpeg';
    parts.push({ inlineData: { mimeType: mime, data: b64(await r.arrayBuffer()) } });
    parts.push({ text: tr ? (m.type === 'image' ? 'Translate the text in this image.' : 'Transcribe and translate this audio.')
      : (m.type === 'image' ? 'วิเคราะห์ภาพกราฟนี้สำหรับเทรดทองระยะสั้น' : 'นี่คือข้อความเสียงจากผู้ใช้ ฟังแล้วตอบคำถาม') });
  } else return reply(env, ev, [{ type: 'text', text: 'ตอนนี้รองรับข้อความ ภาพ และเสียงค่ะ' }]);

  if (tr) {
    const lang = LANGS[tr];
    const out = await gemini(env, CHAT_MODEL, {
      systemInstruction: { parts: [{ text: `You are a professional translator. Translate into ${lang}. If audio, transcribe first. Reply exactly:\nต้นฉบับ: <original>\nแปล: <translation in ${lang}>\nNo commentary.` }] },
      contents: [{ role: 'user', parts }], generationConfig: { temperature: 0.2, maxOutputTokens: 1200 } });
    return reply(env, ev, [{ type: 'text', text: (' ' + out).slice(0, 4500), quickReply: quick() }]);
  }
  const now = new Date().toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' });
  const mem = await getMem(env, uid);
  const memP = (mem.facts.length ? '\n\nสิ่งที่จำเกี่ยวกับผู้ใช้:\n- ' + mem.facts.join('\n- ') : '') + '\n\nถ้าผู้ใช้บอกข้อมูลที่ควรจำระยะยาว ให้ใส่ [[จำ: ข้อความสั้น]] ท้ายคำตอบ';
  let out = await gemini(env, CHAT_MODEL, {
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT + memP }] },
    contents: [...mem.hist.map(h => ({ role: h.r, parts: [{ text: h.t }] })), { role: 'user', parts: [{ text: 'เวลาไทยตอนนี้: ' + now + '\n\nบริบทตลาด:\n' + await context() }, ...parts] }],
    generationConfig: { temperature: 0.4, maxOutputTokens: 1200 } });
  const add = []; out = out.replace(/\[\[\s*จำ\s*:\s*([^\]]+)\]\]/g, (_, x) => { add.push(x.trim()); return ''; }).trim();
  add.forEach(x => { if (!mem.facts.includes(x)) mem.facts.push(x); }); if (add.length) out += '\n\nจำไว้แล้วค่ะ: ' + add.join(' · ');
  mem.hist.push({ r: 'user', t: (m.type === 'text' ? m.text : '[' + m.type + ']').slice(0, 400) }, { r: 'model', t: out.slice(0, 600) });
  await setMem(env, uid, mem);
  return reply(env, ev, [{ type: 'text', text: out.slice(0, 4500) }]);
}

async function context() {
  const out = [];
  const [p, d, k, ls, jn] = await Promise.allSettled([fetch(PRICE_URL).then(r => r.ok ? r.text() : ''), fetch(DASHBOARD_URL + '?t=' + Date.now()).then(r => r.ok ? r.text() : ''),
    fetch(KNOWLEDGE_URL, { cf: { cacheTtl: 3600, cacheEverything: true } }).then(r => r.ok ? r.text() : ''),
    fetch(LESSONS_URL, { cf: { cacheTtl: 600 } }).then(r => r.ok ? r.text() : ''), fetch(JOURNAL_URL, { cf: { cacheTtl: 600 } }).then(r => r.ok ? r.text() : '')]);
  if (p.value) out.push('ราคาสด XAU: ' + p.value.slice(0, 500));
  if (d.value) out.push('ข้อมูลแดชบอร์ด (JSON): ' + d.value.slice(0, 12000));
  if (ls.value || jn.value) out.push('บทเรียน/ประวัติเทรด:\n' + ((ls.value || '').slice(-3000) + '\nบันทึกเทรดล่าสุด:\n' + (jn.value || '').trim().split('\n').slice(-15).join('\n')).slice(0, 5000));
  if (k.value) out.push('คลังความรู้ (หลักการตัดสินใจ):\n' + k.value.slice(0, 9000));
  return out.join('\n\n') || 'ไม่มีข้อมูลบริบท';
}
async function geminiRaw(env, model, payload) {
  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
    method: 'POST', headers: { 'content-type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(model + ' ' + r.status + ' ' + (await r.text()).slice(0, 200));
  return r.json();
}
async function gemini(env, model, payload) {
  const j = await geminiRaw(env, model, payload);
  return (j.candidates?.[0]?.content?.parts || []).map(x => x.text || '').join('').trim() || 'ขออภัย ยังตอบไม่ได้ ลองถามใหม่ค่ะ';
}
async function tts(env, text) {
  if (!text) return { ok: false, error: 'empty' };
  const speak = text.replace(/[*#_`>]/g, '').replace(/https?:\/\/\S+/g, '').slice(0, 600);
  const j = await geminiRaw(env, TTS_MODEL, { contents: [{ parts: [{ text: 'อ่านด้วยน้ำเสียงเลขาผู้หญิงที่สุภาพ ชัดเจน: ' + speak }] }],
    generationConfig: { responseModalities: ['AUDIO'], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: TTS_VOICE } } } } });
  const inl = j.candidates[0].content.parts[0].inlineData;
  return { ok: true, format: 's16le', channels: 1, sampleRate: Number((/rate=(\d+)/.exec(inl.mimeType || '') || [0, 24000])[1]), pcmBase64: inl.data };
}
async function line(env, kind, payload) {
  if (payload.messages) payload.messages = payload.messages.slice(0, 5);
  const r = await fetch('https://api.line.me/v2/bot/message/' + kind, { method: 'POST',
    headers: { 'content-type': 'application/json', Authorization: 'Bearer ' + env.LINE_CHANNEL_ACCESS_TOKEN }, body: JSON.stringify(payload) });
  if (!r.ok) console.error('LINE ' + kind + ' ' + r.status + ' ' + await r.text());
  return r.status;
}
