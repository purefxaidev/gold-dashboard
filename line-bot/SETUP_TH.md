# ตั้งค่า LINE Bot ทองคำ + Gemini (Google Apps Script)

## 1) สร้างโปรเจกต์
1. เปิด https://script.google.com แล้วกด **โปรเจกต์ใหม่** ตั้งชื่อ เช่น `line-gold-bot`
2. ลบโค้ดเดิมใน `Code.gs` แล้ววางโค้ดทั้งหมดจากไฟล์ `Code.gs` กด 💾 บันทึก
3. ⚙️ **การตั้งค่าโปรเจกต์** → เขตเวลา `Asia/Bangkok`

## 2) ตั้ง Script Properties (เก็บความลับ ห้ามใส่ในโค้ด)
⚙️ การตั้งค่าโปรเจกต์ → **คุณสมบัติของสคริปต์** → เพิ่ม:
| ชื่อ | ค่า |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | จาก LINE Developers → Messaging API |
| `LINE_CHANNEL_SECRET` | จาก Basic settings (เก็บไว้ แต่ Apps Script ใช้ตรวจลายเซ็นไม่ได้ ดูข้อจำกัด) |
| `GEMINI_API_KEY` | **key ใหม่** จาก https://aistudio.google.com/apikey (key ที่เคยพิมพ์ในแชทให้ลบทิ้ง) |
| `ALERT_SECRET` | ข้อความสุ่มยาวๆ สำหรับระบบแจ้งเตือน |
| `WEBHOOK_KEY` | (แนะนำ) ข้อความสุ่มอีกชุด |
| `VOICE_MODE` | `off` (เริ่มต้น) / `wav_experimental` / `converter` |
| `CONVERTER_URL` | (ถ้าใช้ `converter`) |

## 3) ทดสอบในหน้า Editor
เลือกฟังก์ชัน `testGemini` → ▶ เรียกใช้ → อนุญาตสิทธิ์ (UrlFetch, Drive) → ดูผลใน Log

## 4) Deploy เป็น Web App
**ทำให้ใช้งานได้ → การทำให้ใช้งานได้รายการใหม่ → ประเภท: เว็บแอป**
- เรียกใช้ในฐานะ: **ฉัน**
- ผู้มีสิทธิ์เข้าถึง: **ทุกคน (Anyone)**
กด Deploy แล้วคัดลอก URL (`https://script.google.com/macros/s/.../exec`)
> แก้โค้ดภายหลัง: จัดการการทำให้ใช้งานได้ → ✏️ → เวอร์ชันใหม่ (URL เดิม)

## 5) ตั้งใน LINE Developers
1. Messaging API → **Webhook URL** = `URL/exec?key=ค่า WEBHOOK_KEY` → Update → **Verify**
2. เปิด **Use webhook**
3. LINE Official Account Manager → การตอบกลับ → ปิด **Auto-reply** และ Greeting (ถ้าไม่ต้องการ)
4. ทดลองส่งข้อความ / ภาพกราฟ / ข้อความเสียง หาบอท

## 6) แจ้งเตือนเสียงจากระบบเทรด (ใช้งานได้จริง)
- Apps Script มี `action=tts` (ต้องมี `ALERT_SECRET`) คืนเสียง PCM base64 + sample rate
- คอมระบบเทรดตั้ง env: `LINE_ALERT_URL` (URL /exec), `ALERT_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` แล้วใช้ `line_notify_voice.sh "ข้อความ"`
- สคริปต์จะแปลงเป็น m4a ด้วย ffmpeg → push ไป GitHub Pages `gold-dashboard/audio/` (สาธารณะ ลบไฟล์เก่ากว่า 1 วัน) → รอลิงก์พร้อม (≤90 วิ) → broadcast ข้อความ+เสียง
- ล้มขั้นไหนก็ตาม จะส่งข้อความธรรมดาแทน (`line_notify.sh`)
- เสียงตอบแชทในบอท (VOICE_MODE) ยังเป็นตัวเลือกเหมือนเดิม

## โมเดลที่ใช้ และทำไมไม่ใช้ gemini-3.8-live
- `gemini-3.8-live` (และ `gemini-3.5-live-translate-preview`) มีจริงในเอกสาร Google แต่เป็นโมเดล **Live API** ซึ่งทำงานผ่าน **WebSocket** แบบสตรีม (`ai.live.connect`) — Apps Script มีแค่ `UrlFetchApp` (HTTP request/response) เปิด WebSocket ไม่ได้ และ LINE ก็ส่งเสียงมาเป็นไฟล์ ไม่ใช่สตรีมอยู่แล้ว
- จึงใช้โมเดล REST แทน (แก้ได้ที่ค่าคงที่บนสุดของโค้ด):
  - `CHAT_MODEL = gemini-3.8-flash` — เข้าใจข้อความ ภาพ และไฟล์เสียง m4a ใน `generateContent`
  - `TTS_MODEL = gemini-3.8-flash-tts` — แปลงข้อความเป็นเสียง (ทางเลือกถูกกว่า: `gemini-3.8-flash-lite-tts`)

## ข้อจำกัด
- **เสียงตอบกลับ**: Gemini TTS คืนเสียงเป็น PCM ดิบ (24 kHz) แต่ LINE audio message ต้องเป็นไฟล์ **m4a** ผ่าน HTTPS สาธารณะ + ระยะเวลา Apps Script **แปลงเป็น m4a เองไม่ได้** (ไม่มี ffmpeg/encoder AAC) จึงตั้ง `VOICE_MODE=off` เป็นค่าเริ่มต้น
  - `wav_experimental`: แปลงเป็น WAV เก็บใน Google Drive แชร์ลิงก์สาธารณะ — LINE อาจไม่รับ/เล่นไม่ได้บางเครื่อง (ถ้า LINE ปฏิเสธ ระบบจะส่งแค่ข้อความแทน) ลิงก์ Drive อาจถูก redirect ทำให้เล่นไม่ได้
  - `converter`: ส่ง WAV ไปบริการแปลงของคุณเอง (เช่น Cloud Run + ffmpeg) ที่ตอบ `{"url":"https://...m4a"}` — ทางที่ใช้ได้จริงที่สุด
  - ไฟล์เสียงใน Drive เป็นสาธารณะ ตั้ง Trigger รายวันเรียก `cleanupAudio` เพื่อลบไฟล์เก่า
- **X-Line-Signature**: `doPost` ของ Apps Script อ่าน HTTP header ไม่ได้ จึงตรวจลายเซ็นไม่ได้ ใช้ `WEBHOOK_KEY` ใน URL แทน (ป้องกันได้ระดับหนึ่ง)
- **เวลา**: LINE reply token ใช้ได้ครั้งเดียวและควรตอบเร็ว เปิดเสียงจะช้าขึ้นหลายวินาที; Apps Script ตอบ webhook แบบ redirect 302 ซึ่ง LINE รับได้ แต่ปุ่ม Verify อาจแสดง error ได้แม้ใช้งานจริงได้
- โควตาฟรีของ Apps Script (UrlFetch ต่อวัน) และค่าใช้ Gemini API เป็นของบัญชีคุณ
- คำตอบ AI ไม่ใช่การรับประกันกำไร เทรดมีความเสี่ยง

## โหมดแปลภาษา (LINE)
- พิมพ์ `/แปล` → มีปุ่มเลือกภาษา (Quick Reply) หรือพิมพ์ตรง เช่น `/แปล en`, `/แปล zh`, `/แปล ja` (รองรับ th en zh ja ko vi lo my fr de)
- ในโหมดแปล: ส่งข้อความ / เสียง (ถอดเสียง+แปล) / ภาพ (แปลข้อความในภาพ) → ตอบ "ต้นฉบับ / แปล" + เสียงภาษาปลายทาง (เฉพาะเมื่อเปิด VOICE_MODE)
- พิมพ์ `/วิเคราะห์` เพื่อกลับโหมดวิเคราะห์ทอง · โหมดถูกจำแยกต่อผู้ใช้ (Script Properties `MODE_<userId>`)

## 📞 คุยสดด้วยเสียงกับ AI (Live API)
- LINE bot รับสายโทรไม่ได้ จึงทำหน้าเว็บ `https://purefxaidev.github.io/gold-dashboard/call.html` เชื่อม Gemini Live API ผ่าน WebSocket ตรงจากเบราว์เซอร์ (ใช้ key ที่บันทึกในแชทแดชบอร์ดของเครื่องนั้น ไม่มี key ในเว็บ)
- โมเดลเริ่มต้น `models/gemini-3.8-live` (มีในเอกสาร Google) เปลี่ยนได้: 3.8-live-extended-thinking, 3.1-flash-live-preview, 2.5 native-audio, 3.5-live-translate-preview · เสียง `Sulafat` · พูดแทรกได้ · แสดงคำถอดเสียง · มีโหมดล่ามแปลภาษา
- ใน LINE ถ้าไมค์ใช้ไม่ได้ ให้กด ⋮ → เปิดในเบราว์เซอร์ภายนอก (ปุ่มในเมนูใส่ `?openExternalBrowser=1` ให้แล้ว)

## Rich Menu (ปุ่มเมนูใน LINE)
1. ใน Apps Script เลือกฟังก์ชัน `createRichMenu` → ▶ เรียกใช้ (ครั้งเดียว)
2. ได้ 4 ปุ่ม: 📞 โทรคุยกับ AI · แดชบอร์ด · สรุปตอนนี้ · โหมดแปล (รูปจาก `richmenu.png` บน GitHub Pages)
3. ถ้ารันซ้ำจะสร้างเมนูใหม่ทับเป็นค่าเริ่มต้น (เมนูเก่าลบได้ใน LINE Official Account Manager)

## ทางเลือก: Cloudflare Worker (`worker.js` + `wrangler.toml`)
ข้อดี: อ่าน header ได้ → **ตรวจ X-Line-Signature จริง** (HMAC-SHA256 ด้วย LINE_CHANNEL_SECRET), ตอบ 200 ทันทีแล้วประมวลผลต่อ (ไม่ติด timeout)
1. ติดตั้ง Node แล้ว `npm i -g wrangler` → `wrangler login`
2. ในโฟลเดอร์ `line-bot/`: `wrangler secret put LINE_CHANNEL_ACCESS_TOKEN` (ทำซ้ำกับ `LINE_CHANNEL_SECRET`, `GEMINI_API_KEY`, `ALERT_SECRET`)
3. (ตัวเลือก) โหมดแปลแบบจำต่อผู้ใช้: `wrangler kv namespace create MODES` แล้วเปิดบรรทัด `[[kv_namespaces]]` ใน wrangler.toml
4. `wrangler deploy` → ได้ URL `https://line-gold-bot.<ชื่อ>.workers.dev` → ใส่เป็น Webhook URL ใน LINE (ไม่ต้องมี ?key=)
5. แจ้งเตือน: `POST /alert` (ข้อความ) และ `POST /tts` (คืน PCM ให้ `line_notify_voice.sh`) — ใช้ JSON `{"secret":..., "text":...}` (สคริปต์ปัจจุบันใช้ `action` แบบ Apps Script; ถ้าใช้ Worker ให้ตั้ง `LINE_ALERT_URL=https://.../tts`)
- Worker ไม่ส่งเสียงตอบในแชท (ไม่มีตัวเข้ารหัส m4a) · Rich Menu ใช้ `createRichMenu()` ใน Apps Script หรือสร้างใน LINE OA Manager
