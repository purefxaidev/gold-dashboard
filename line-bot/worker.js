// LINE x Gemini gold bot — Cloudflare Worker version
// Secrets (wrangler secret put): LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY, ALERT_SECRET
// Optional KV binding MODES (translate mode per user). Voice replies: not in Worker (no m4a encoder) — use line_notify_voice.sh for voice alerts.
const CHAT_MODEL = 'gemini-3.8-flash', TTS_MODEL = 'gemini-3.8-flash-tts', TTS_VOICE = 'Kore';
const DASHBOARD_URL = 'https://purefxaidev.github.io/gold-dashboard/view.json';
const PRICE_URL = 'https://api.gold-api.com/price/XAU';
const LANGS = { th: 'Thai', en: 'English', zh: 'Chinese (Simplified)', ja: 'Japanese', ko: 'Korean', vi: 'Vietnamese', lo: 'Lao', my: 'Burmese', fr: 'French', de: 'German' };
const SYSTEM_PROMPT = [
  'คุณคือผู้ช่วยนักวิเคราะห์ทองคำ (XAUUSD) ระยะสั้น (M5–H1) ตอบเป็นภาษาไทย กระชับ อ่านง่ายบนมือถือ',
  'ใช้ข้อมูลบริบท (ราคาสด แนวรับแนวต้าน แผนเทรด % ความมั่นใจ AI ค่า EV และข่าว) ที่แนบมาเป็นหลัก ถ้าข้อมูลไม่พอให้บอกตรงๆ',
  'ถ้าผู้ใช้ส่งภาพกราฟ ให้อ่านเทรนด์ แนวรับแนวต้านจากภาพ ถ้าส่งเสียง ให้ฟังคำถามแล้วตอบ',
  'ทุกครั้งที่แนะนำจุดเข้า ต้องระบุ Buy/Sell จุดเข้า SL และ TP พร้อมเหตุผลสั้นๆ',
  'ห้ามรับประกันกำไร ปิดท้ายด้วยคำเตือนความเสี่ยง 1 บรรทัด ห้ามขอหรือเปิดเผยรหัสผ่าน/API key'
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
      if (ev.replyToken) await line(env, 'reply', { replyToken: ev.replyToken, messages: [{ type: 'text', text: 'ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งครับ' }] });
    }))));
    return new Response('ok');
  }
};

async function getMode(env, uid) { return uid && env.MODES ? (await env.MODES.get('m:' + uid)) || '' : ''; }
async function setMode(env, uid, v) { if (!uid || !env.MODES) return; v ? await env.MODES.put('m:' + uid, v) : await env.MODES.delete('m:' + uid); }
function quick() {
  return { items: Object.keys(LANGS).map(k => ({ type: 'action', action: { type: 'message', label: k + ' ' + LANGS[k].split(' ')[0], text: '/แปล ' + k } }))
    .concat([{ type: 'action', action: { type: 'message', label: '📈 วิเคราะห์ทอง', text: '/วิเคราะห์' } }]) };
}
const reply = (env, ev, messages) => line(env, 'reply', { replyToken: ev.replyToken, messages });

async function handleEvent(env, ev) {
  if (ev.type !== 'message' || !ev.replyToken) return;
  const m = ev.message, uid = ev.source && ev.source.userId;
  if (m.type === 'text' && m.text.startsWith('/')) {
    const t = m.text.trim();
    if (/^\/(วิเคราะห์|analyst)/i.test(t)) { await setMode(env, uid, ''); return reply(env, ev, [{ type: 'text', text: '📈 กลับสู่โหมดวิเคราะห์ทองแล้วครับ' }]); }
    const mm = /^\/(แปล|translate|tr)\s*([a-z]{2})?/i.exec(t);
    if (mm) {
      const c = (mm[2] || '').toLowerCase();
      if (!LANGS[c]) return reply(env, ev, [{ type: 'text', text: '🌐 เลือกภาษาปลายทาง:', quickReply: quick() }]);
      await setMode(env, uid, c);
      return reply(env, ev, [{ type: 'text', text: `🌐 โหมดแปล → ${LANGS[c]}\nพิมพ์ /วิเคราะห์ เพื่อกลับ` + (env.MODES ? '' : '\n(⚠️ ยังไม่ผูก KV MODES — โหมดจะไม่ถูกจำ)'), quickReply: quick() }]);
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
  } else return reply(env, ev, [{ type: 'text', text: 'ตอนนี้รองรับข้อความ ภาพ และเสียงครับ' }]);

  if (tr) {
    const lang = LANGS[tr];
    const out = await gemini(env, CHAT_MODEL, {
      systemInstruction: { parts: [{ text: `You are a professional translator. Translate into ${lang}. If audio, transcribe first. Reply exactly:\nต้นฉบับ: <original>\nแปล: <translation in ${lang}>\nNo commentary.` }] },
      contents: [{ role: 'user', parts }], generationConfig: { temperature: 0.2, maxOutputTokens: 1200 } });
    return reply(env, ev, [{ type: 'text', text: ('🌐 ' + out).slice(0, 4500), quickReply: quick() }]);
  }
  const now = new Date().toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' });
  const out = await gemini(env, CHAT_MODEL, {
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
    contents: [{ role: 'user', parts: [{ text: 'เวลาไทยตอนนี้: ' + now + '\n\nบริบทตลาด:\n' + await context() }, ...parts] }],
    generationConfig: { temperature: 0.4, maxOutputTokens: 1200 } });
  return reply(env, ev, [{ type: 'text', text: out.slice(0, 4500) }]);
}

async function context() {
  const out = [];
  const [p, d] = await Promise.allSettled([fetch(PRICE_URL).then(r => r.ok ? r.text() : ''), fetch(DASHBOARD_URL + '?t=' + Date.now()).then(r => r.ok ? r.text() : '')]);
  if (p.value) out.push('ราคาสด XAU: ' + p.value.slice(0, 500));
  if (d.value) out.push('ข้อมูลแดชบอร์ด (JSON): ' + d.value.slice(0, 12000));
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
  return (j.candidates?.[0]?.content?.parts || []).map(x => x.text || '').join('').trim() || 'ขออภัย ยังตอบไม่ได้ ลองถามใหม่ครับ';
}
async function tts(env, text) {
  if (!text) return { ok: false, error: 'empty' };
  const speak = text.replace(/[*#_`>]/g, '').replace(/https?:\/\/\S+/g, '').slice(0, 600);
  const j = await geminiRaw(env, TTS_MODEL, { contents: [{ parts: [{ text: 'อ่านด้วยน้ำเสียงนักวิเคราะห์ที่สุภาพ ชัดเจน: ' + speak }] }],
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
