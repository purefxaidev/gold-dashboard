/* PUREGOLD i18n — TH/EN. Language: ?lang= > localStorage gd_ui_lang > navigator.language (th* -> th, else en) */
(function () {
  const q = new URLSearchParams(location.search).get("lang");
  let L = (q === "en" || q === "th") ? q : localStorage.getItem("gd_ui_lang") || ((navigator.language || "").toLowerCase().startsWith("th") ? "th" : "en");
  if (q) localStorage.setItem("gd_ui_lang", L);
  window.LANG = L; document.documentElement.lang = L;
  const D = {
  // header / common
  "สมัคร Exness": "Open Exness account", "กำลังเชื่อมต่อ…": "Connecting…", "กำลังโหลดข้อมูล…": "Loading data…", "กำลังโหลด…": "Loading…",
  "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน · การเทรดมีความเสี่ยงสูง อาจขาดทุนเกินที่คาด": "For education only, not investment advice · Trading is high risk; losses can exceed expectations",
  // sections
  "กราฟ XAUUSD": "XAUUSD chart", "ราคาทองโลกแบบเรียลไทม์": "Live world gold price", "ความมั่นใจ AI (ระยะสั้น)": "AI confidence (short term)", "แผนที่ราคา 3 มิติ": "3D price map",
  "ลูกทอง = ราคาตอนนี้ · เขียว = แนวรับ · แดง = แนวต้าน · ลากเพื่อหมุน": "Gold orb = current price · green = support · red = resistance · drag to rotate",
  "พอร์ต กำไร/ขาดทุน": "Portfolio P/L", "ราคาทองไทยวันนี้ (บาทละ)": "Thai gold price today (per baht-weight)", "ฮั่วเซ่งเฮง · อัปเดตทุก 30 วินาที": "Hua Seng Heng · updates every 30 s",
  "แนวรับ · แนวต้าน": "Support · Resistance", "จุดเข้า · จุดออก + โมเดลตัดสินใจ EV": "Entries · Exits + EV decision model", "แผนจากระบบ": "System plans", "ข่าววิเคราะห์ทองคำ": "Gold news & analysis",
  "คุยกับกราฟ": "Chat with the chart", "คุยสด": "Live call", "ความจำ": "Memory", "ตั้งค่า": "Settings", "▲ โอกาสขึ้น": "▲ Chance up", "โอกาสลง ▼": "Chance down ▼",
  "EV(R) = p × RR − (1 − p) \u00a0·\u00a0 RR = ระยะ TP ÷ ระยะ SL \u00a0·\u00a0 เข้าเมื่อ EV > 0": "EV(R) = p × RR − (1 − p) · RR = TP distance ÷ SL distance · enter when EV > 0",
  "คำศัพท์ง่ายๆ": "Plain-language glossary", "คำแนะนำตอนนี้": "Recommendation now", "ความมั่นใจ": "Confidence",
  "= จุดตัดขาดทุน ถ้าราคาไปผิดทางถึงตรงนี้ ระบบปิดให้อัตโนมัติ ·": "= stop loss: if price moves against you to here, the position closes automatically ·", "= จุดเก็บกำไร ·": "= take profit ·",
  "= กำไรที่หวังเทียบกับความเสี่ยง เช่น 1.6 คือเสี่ยง 1 ได้ 1.6 ·": "= reward vs. risk, e.g. 1.6 means risk 1 to make 1.6 ·", "= ผลตอบแทนคาดหวังต่อไม้ (หน่วย R) ถ้าเป็นบวกแปลว่าคุ้มเข้าในระยะยาว ·": "= expected return per trade (in R); positive means worth taking over many trades ·",
  "= โอกาสที่ AI ประเมินว่าราคาจะไปทางนั้น (ไม่ใช่การรับประกัน)": "= the AI's estimated chance of that direction (not a guarantee)",
  "ราคาอยู่กลางกรอบ ยังไม่คุ้มเข้า รอให้ถึงจุดด้านล่าง": "Price is mid-range; not worth entering yet. Wait for the levels below.", "ราคาอยู่ที่จุดเข้าตามแผน": "Price is at the planned entry",
  "ขาย": "SELL", "ซื้อ": "BUY", "เข้า": "Enter", "รอ": "Wait", "เปิดอยู่": "Open", "ปิดแล้ว": "Closed", "ขึ้น": "up", "ลง": "down", "ไทย": "Thai",
  "ไม่มีไม้ที่เปิดอยู่ตอนนี้": "No open positions right now", "สปอต · gold-api.com": "Spot · gold-api.com", "ราคาจากบทวิเคราะห์ล่าสุด": "Price from latest analysis",
  "ราคาสดไม่พร้อม · ใช้ราคาจากบทวิเคราะห์": "Live price unavailable · using analysis price", "ตั้งแต่เปิดหน้า": "since page opened",
  "รับซื้อ": "Buy", "ขายออก": "Sell", "ทองคำแท่ง ฮั่วเซ่งเฮง": "Gold bar · Hua Seng Heng", "ทองคำแท่ง สมาคมฯ (อ้างอิง)": "Gold bar · Gold Traders Assoc. (reference)", "ทองรูปพรรณ": "Gold jewelry",
  "ทอง 99.99% : แหล่งข้อมูลสาธารณะยังไม่เปิดให้ดึง": "99.99% gold: no public data source available", "โหลดราคาทองไทยไม่สำเร็จ จะลองใหม่": "Could not load Thai gold price; retrying",
  "แหล่งข่าว ↗": "Source ↗", "AI มองขึ้น": "AI sees up", "· ลง": "· down", "โอกาสชนะ p": "Win chance p", "1น.": "1m", "5น.": "5m", "15น.": "15m", "1ชม.": "1h", "4ชม.": "4h", "วัน": "1D", "สัปดาห์": "1W",
  "กำไร/ขาดทุนวันนี้": "Today's P/L", "จุด (ดอลลาร์)": "Points (USD)", "อัตราชนะ (ไม้ที่ปิด)": "Win rate (closed)", "ไม้เปิด / ไม้วันนี้": "Open / today's trades",
  "เวลา": "Time", "ฝั่ง": "Side", "ล็อต": "Lot", "ออก": "Exit", "จุด": "Pts", "สถานะ": "Status", "โดย": "By", "ผู้ใช้": "User",
  "อุปกรณ์นี้ไม่รองรับ 3D — ดูแนวรับแนวต้านด้านล่างแทน": "This device doesn't support 3D — see support/resistance below", "โหลด 3D ไม่สำเร็จ": "Could not load 3D",
  // chat
  "วิเคราะห์ทอง": "Gold analysis", "แปลภาษา": "Translate", "ส่ง": "Send", "พูด": "Speak", "ถามเรื่องกราฟทอง เช่น ตอนนี้ควร Buy หรือ Sell?": "Ask about gold, e.g. should I buy or sell now?",
  "พิมพ์หรือกด  พูด เพื่อแปล": "Type or tap the mic to translate", "พิมพ์หรือกด พูด เพื่อแปล": "Type or tap the mic to translate",
  "สรุปภาพรวมทองตอนนี้": "Summarize gold right now", "ควร Buy หรือ Sell ระยะสั้น?": "Buy or sell short term?", "แผนไหน EV ดีที่สุด?": "Which plan has the best EV?",
  "ข่าวไหนกระทบทองมากสุด?": "Which news matters most for gold?", "ถ้าหลุดแนวรับจะไปถึงไหน?": "If support breaks, where next?", "ราคาทองไทยวันนี้เป็นไง?": "How is the Thai gold price today?",
  "ความจำของเลขา": "Assistant memory", "(เก็บในเบราว์เซอร์นี้เท่านั้น ไม่ขึ้นเว็บ)": "(stored only in this browser, never uploaded)", "+ จำ": "+ Remember",
  "เพิ่มสิ่งที่ให้จำ เช่น ชอบเทรดช่วง London": "Add something to remember, e.g. I prefer the London session", "บันทึกสรุปบทสนทนา (แก้ไขได้)": "Conversation summary (editable)",
  "บันทึก": "Save", "ล้างความจำ": "Clear memory", "ลบ key": "Delete key", "วาง API key ของคุณที่นี่": "Paste your API key here", "วาง API key ที่นี่": "Paste API key here",
  "ยังไม่มีสิ่งที่จำ": "Nothing remembered yet", "key จะถูกเก็บไว้": "The key is stored", "เฉพาะในเบราว์เซอร์ของเครื่องนี้": "only in this device's browser",
  "(localStorage) เท่านั้น ไม่ถูกส่งขึ้น GitHub หรือเซิร์ฟเวอร์อื่น ส่งตรงไปที่ Google เท่านั้น · อย่าใช้บนเครื่องสาธารณะ · กด “ลบ key” เมื่อเลิกใช้ · หากเคยแปะ key ในแชทหรือที่สาธารณะ ให้ลบแล้วสร้างใหม่ที่ Google AI Studio": "(localStorage). It is never sent to GitHub or any other server, only directly to Google · Don't use on shared devices · Tap “Delete key” when done · If you ever pasted a key publicly, revoke it and create a new one in Google AI Studio",
  "gemini-3.8-flash (แนะนำ)": "gemini-3.8-flash (recommended)", "gemini-3.5-flash-lite (เร็ว/ประหยัด)": "gemini-3.5-flash-lite (fast/cheap)",
  "สวัสดีค่ะ  ดิฉันคือ เลขา ผู้ช่วยวิเคราะห์ทองค่ะ ถามเรื่องกราฟ แนวรับแนวต้าน หรือข่าวได้เลยค่ะ (ต้องใส่ Gemini API key ใน  ตั้งค่า ก่อนใช้ครั้งแรก)": "Hello, I'm your PUREGOLD assistant. Ask me about the chart, support/resistance or news (add a Gemini API key in Settings first).",
  "สวัสดีค่ะ ดิฉันคือ เลขา ผู้ช่วยวิเคราะห์ทองค่ะ ถามเรื่องกราฟ แนวรับแนวต้าน หรือข่าวได้เลยค่ะ (ต้องใส่ Gemini API key ใน ตั้งค่า ก่อนใช้ครั้งแรก)": "Hello, I'm your PUREGOLD assistant. Ask me about the chart, support/resistance or news (add a Gemini API key in Settings first).",
  "กรุณาใส่ Gemini API key ในตั้งค่าก่อน": "Please add a Gemini API key in Settings first", "เบราว์เซอร์นี้อัดเสียงไม่ได้": "This browser can't record audio",
  "บันทึกความจำแล้วค่ะ": "Memory saved", "ล้างความจำเรียบร้อยค่ะ": "Memory cleared", "ลบ key ออกจากเครื่องนี้แล้ว": "Key removed from this device",
  "บันทึกการตั้งค่าแล้ว (key อยู่ในเครื่องนี้เท่านั้น)": "Settings saved (key stays on this device)", "บันทึกการตั้งค่าแล้ว  (key อยู่ในเครื่องนี้เท่านั้น)": "Settings saved (key stays on this device)",
  "บันทึก key แล้วค่ะ ใช้ได้ทั้งแชท แปล และคุยสด": "Key saved. Works for chat, translate and live call", "บันทึก key แล้วค่ะ  ใช้ได้ทั้งแชท แปล และคุยสด": "Key saved. Works for chat, translate and live call",
  "(ไม่มีคำตอบ ลองถามใหม่)": "(No answer, please try again)", "(บันทึกแล้วค่ะ)": "(Saved)",
  // modals
  "ตั้งค่าครั้งแรก": "First-time setup", "ไว้ทีหลัง": "Later", "มีบัญชี Exness แล้วหรือยัง?": "Do you have an Exness account?",
  "ระบบวิเคราะห์นี้ใช้กับบัญชีเทรดทองคำ (XAUUSD) ถ้ายังไม่มี เราสอนสมัครทีละขั้นได้": "This analysis is for gold (XAUUSD) trading accounts. If you don't have one, we can guide you step by step.",
  "ยังไม่มี สอนสมัครหน่อย": "Not yet, show me how", "มีแล้ว": "I already have one",
  "ลิงก์สมัครเป็นลิงก์แนะนำ (partner) · CFD มีความเสี่ยงสูง อาจสูญเสียเงินทั้งหมด": "The sign-up link is a partner referral link · CFDs are high risk; you may lose all your money",
  "วาง Gemini API key ครั้งเดียว ใช้ได้ทั้งแชท แปลภาษา และคุยสด": "Paste a Gemini API key once; it powers chat, translation and live call", "key ถูกเก็บ": "The key is stored ",
  "เฉพาะในเบราว์เซอร์เครื่องนี้": "only in this browser", "ไม่ขึ้นเว็บ/GitHub · สร้างฟรีที่": "never on the site/GitHub · create one free at",
  // call page
  "คุยสดกับ AI ทองคำ": "Live voice call with the gold AI", "Gemini Live API · เสียงต่อเสียงแบบเรียลไทม์ ·": "Gemini Live API · real-time voice ·", "← แดชบอร์ด": "← Dashboard",
  "โหมด": "Mode", "ล่ามแปลภาษา": "Interpreter", "ภาษาปลายทาง": "Target language", "โมเดล Live": "Live model", "เสียง (ผู้หญิง)": "Voice (female)",
  "models/gemini-3.5-live-translate-preview (ล่ามแปล)": "models/gemini-3.5-live-translate-preview (interpreter)", "อนุญาตไมค์และเริ่มสาย": "Allow microphone & start call",
  "แตะปุ่มด้านบน แล้วกด \"อนุญาต\" เมื่อเบราว์เซอร์ถามสิทธิ์ไมค์": "Tap the button above, then choose \"Allow\" when the browser asks for the microphone",
  "แตะเพื่อเปิดเสียงต่อ": "Tap to resume audio", "เปิดในเบราว์เซอร์ภายนอก": "Open in external browser", "ข้อมูลสำหรับแก้ปัญหา (debug)": "Troubleshooting info (debug)", "วางสาย": "Hang up",
  "ใช้ Gemini key ที่บันทึกไว้ในเบราว์เซอร์นี้ (ตั้งค่าได้ที่แชทในหน้าแดชบอร์ด) — ไม่มี key ในเว็บไซต์ · ถ้าเปิดใน LINE แล้วไมค์ใช้ไม่ได้ ให้กด ⋮ →": "Uses the Gemini key saved in this browser (set it in the dashboard chat) — no key is stored on the site · If the mic doesn't work inside LINE, tap ⋮ →",
  "· ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน": "· For education only, not investment advice",
  "กำลังขอสิทธิ์ไมค์…": "Requesting microphone…", "กำลังเชื่อมต่อ Gemini…": "Connecting to Gemini…", "กำลังฟัง… พูดได้เลย (พูดแทรกได้)": "Listening… speak now (you can interrupt)",
  "วางสายแล้ว · กดเพื่อเริ่มใหม่": "Call ended · tap to start again", "เซสชันใกล้หมดเวลา": "Session about to expire",
  "หน้านี้ไม่ได้เปิดผ่าน https จึงใช้ไมค์ไม่ได้ค่ะ": "This page isn't on https, so the microphone can't be used",
  "ยังไม่มี Gemini key — เปิดหน้าแดชบอร์ด > แชท > ตั้งค่า แล้ววาง key ก่อนค่ะ": "No Gemini key yet — open the dashboard > Chat > Settings and paste a key first",
  "ไม่พบไมโครโฟนในเครื่องนี้ค่ะ": "No microphone found on this device", "ไมค์ถูกแอปอื่นใช้อยู่ (เช่น โทรศัพท์/แอปอัดเสียง) ปิดแอปนั้นแล้วลองใหม่ค่ะ": "The microphone is in use by another app (call/recorder). Close it and try again",
  "บันทึกสรุปการคุยไว้ในความจำแล้วค่ะ": "Call summary saved to memory",
  // signup
  "กลับแดชบอร์ด": "Back to dashboard", "สอนสมัคร EXNESS": "EXNESS SIGN-UP GUIDE", "ทำเสร็จแล้วติ๊ก:": "Tick when done:", "ย้อนกลับ": "Back", "ถัดไป": "Next", "เสร็จสิ้น": "Finish"
  };
  const R = [
   [/^อัปเดตล่าสุด (.+?)\s?น\. \(เวลาไทย\)(.*)$/, "Last refresh $1 (Bangkok time)$2"], [/ · ข้อมูล /, " · data "],
   [/^อัปเดตบทวิเคราะห์: (.*)$/, "Analysis updated: $1"], [/^อัปเดต (.+?)\s?น\. \(เวลาไทย\)$/, "Updated $1 (Bangkok time)"], [/^วิธีคำนวณ: /, "Method: "],
   [/^ตอนนี้: (.+)$/, (m, a) => "Now: " + (D[a] || a)], [/^ตอนนี้ (.+)$/, "Now $1"], [/^← โซนซื้อ ?(.*)$/, "← Buy zone $1"], [/^(.*) โซนขาย →$/, "$1 Sell zone →"],
   [/^ถ้าราคาขึ้นถึง (.+?) แล้วยืนได้ → $/, "If price rises to $1 and holds → "], [/^ถ้าราคาลงถึง (.+?) แล้วเด้ง → $/, "If price drops to $1 and bounces → "],
   [/^ถ้าราคาขึ้นถึง (.+?) → $/, "If price rises to $1 → "], [/^ถ้าราคาลงถึง (.+?) → $/, "If price drops to $1 → "], [/^ราคาอยู่แถว (.+?) แล้ว → $/, "Price is around $1 now → "],
   [/^\| ตัดขาดทุน \($/, "| Stop loss ("], [/^\) $/, ") "], [/^\| รับกำไร \($/, "| Take profit ("], [/^· โอกาสชนะ ~(\d+)% ?(.*)$/, "· win chance ~$1% $2"],
   [/^อัปเดตเมื่อ (.*?) · แตะคำ SL\/TP\/RR\/EV เพื่อดูความหมาย · ไม่ใช่การรับประกันกำไร$/, "Updated $1 · tap SL/TP/RR/EV for meanings · no profit guarantee"],
   [/^AI มองขึ้น $/, "AI sees up "], [/^ · ลง $/, " · down "],
   [/^เทรดอัตโนมัติ: เปิด · ไม้ละ (.+?) ล็อต · ทุก (.+?)(?: นาที)? · เช็กถัดไป ~(.+?)\s?น\.$/, (m, a, b, c) => `Auto-trading: ON · ${a} lot per trade · every ${/min/.test(b) ? b : b + " min"} · next check ~${c}`], [/^เทรดอัตโนมัติ: ปิด$/, "Auto-trading: OFF"],
   [/^เข้า (.+)$/, "Entry $1"], [/^ต้องชนะ ≥ (\d+)% ถึงคุ้ม · (.*)$/, "Needs ≥ $1% wins to break even · $2"], [/^รอเข้า: (.*)$/, "Pending: $1"], [/^ตัดขาดทุน (.+) · รับกำไร (.+)$/, "SL $1 · TP $2"],
   [/^(.*) น\.$/, "$1"], 
   [/^ราคาตอนนี้ (.+)$/, "Price now $1"], [/^(.*) · ไม้ที่เปิดอยู่คำนวณสดจากราคาปัจจุบัน$/, "$1 · open positions valued live at current price"],
   [/^มี key บันทึกอยู่ \(…(.+)\) · วางใหม่เพื่อเปลี่ยน$/, "Key saved (…$1) · paste a new one to replace"], [/^○ ยังไม่ใส่ key · (.*)$/, "○ No key yet · $1"],
   [/^จำไว้แล้วค่ะ: (.*)$/, "Remembered: $1"], [/^ใช้ไมค์ไม่ได้: (.*)$/, "Microphone unavailable: $1"], [/^เรียก Gemini ไม่สำเร็จ: (.*) \(ตรวจสอบ key \/ ชื่อโมเดลในตั้งค่า\)$/, "Gemini request failed: $1 (check key / model in Settings)"],
   [/^● พบ Gemini key ในเครื่องนี้ \(…(.+)\)$/, "● Gemini key found on this device (…$1)"], [/^○ ยังไม่มี key — ไปตั้งค่าที่แชทในหน้าแดชบอร์ดก่อน$/, "○ No key — set one in the dashboard chat first"],
   [/^ปิดการเชื่อมต่อ \((\d+)\): (.*)$/, "Connection closed ($1): $2"], [/^ขั้นที่ (\d+) จาก (\d+)$/, "Step $1 of $2"], [/^(\d+) ขั้นเสร็จแล้ว$/, "$1 steps done"], [/^ขั้นที่ (\d+)$/, "STEP $1"],
   [/^(ทองคำแท่ง ฮั่วเซ่งเฮง|ทองคำแท่ง สมาคมฯ \(อ้างอิง\)|ทองรูปพรรณ) (.*)$/, (m, a, b) => (D[a] || a) + " " + b],
   [/^ที่มา: ฮั่วเซ่งเฮง \(huasengheng\.com\) · (.*) · รีเฟรช 30 วินาที$/, (m, a) => "Source: Hua Seng Heng (huasengheng.com) · " + a.replace(/อั[ปพ]เดตล่าสุด วันที่ /, "updated ").replace(/ เวลา /, " ").replace(/\s?น\./, "").replace(/ต\.ค\./, "Oct").replace(/\b(25\d\d)\b/, y => +y - 543) + " · refresh 30 s"],
   [/^แผนที่ราคา/, "3D price map"], [/^คำนี้แปลว่า: /, "Meaning: "]
  ];
  const TIPS_EN = {"SL": "SL = stop loss: if price moves against you to this level, the position closes automatically to limit the loss", "TP": "TP = take profit: if price reaches this level, the position closes automatically to lock in profit",
    "RR": "RR = reward vs. risk, e.g. 1.6 means you risk 1 part to make 1.6", "EV": "EV = expected return per trade (in R). Positive means it should pay off over many trades"};
  window.TIPS_EN = TIPS_EN;
  function tr(s) {
    if (L !== "en" || !s || !/[\u0E00-\u0E7F]/.test(s)) return s;
    const k = s.trim(); if (D[k]) return s.replace(k, D[k]);
    for (const [re, to] of R) if (re.test(k)) { const out = k.replace(re, to); if (out !== k) return s.replace(k, out); }
    return s;
  }
  window.t = tr; window.I18N = D;
  const SKIP = el => el.closest && el.closest(".notr, .m.a, .m.u, #log .u, #log .a, #dbgLog, textarea, script, style, #tv");
  function walk(root) {
    if (L !== "en") return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const ns = []; while (w.nextNode()) ns.push(w.currentNode);
    ns.forEach(n => { if (n.parentElement && SKIP(n.parentElement)) return; const v = tr(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; });
    (root.querySelectorAll ? root.querySelectorAll("[placeholder],[title],[aria-label],[alt]") : []).forEach(el => {
      if (SKIP(el)) return;
      for (const a of ["placeholder", "title", "aria-label", "alt"]) { const v = el.getAttribute(a); if (v && /[\u0E00-\u0E7F]/.test(v)) { const tv = el.classList.contains("tip") && a === "title" ? (TIPS_EN[el.textContent.trim()] ? "Meaning: " + TIPS_EN[el.textContent.trim()] : tr(v)) : tr(v); if (tv !== v) el.setAttribute(a, tv); } }
    });
  }
  window.i18nWalk = walk;
  function toggle() {
    const b = document.createElement("button"); b.className = "langtog"; b.type = "button";
    b.innerHTML = `<span class="${L === "th" ? "on" : ""}">TH</span><span class="${L === "en" ? "on" : ""}">EN</span>`; b.setAttribute("aria-label", "Language / ภาษา");
    b.onclick = () => { const n = L === "th" ? "en" : "th"; localStorage.setItem("gd_ui_lang", n); const u = new URL(location.href); u.searchParams.set("lang", n); location.href = u.toString(); };
    const st = document.createElement("style"); st.textContent = ".langtog{display:inline-flex;border:1px solid #f5c54266;border-radius:999px;background:#0b0d12;padding:2px;cursor:pointer;margin-right:8px;flex:none}.langtog span{font:700 11px/1 system-ui;padding:5px 8px;border-radius:999px;color:#999}.langtog span.on{background:#f5c542;color:#111}";
    document.head.appendChild(st);
    const host = document.querySelector("[data-langtog]") || document.querySelector("header .wrap, header"); if (host) { const ref = host.querySelector(".exbtn, [data-langref]"); if (ref) ref.parentNode.insertBefore(b, ref); else host.appendChild(b); }
  }
  document.addEventListener("DOMContentLoaded", () => {
    toggle(); if (L !== "en") return;
    walk(document.body); document.title = tr(document.title).replace(/วิเคราะห์ทองคำ XAUUSD/, "XAUUSD gold analysis");
    let busy = false;
    new MutationObserver(ms => { if (busy) return; busy = true; try { for (const m of ms) { if (m.type === "characterData") { const p = m.target.parentElement; if (p && !SKIP(p)) { const v = tr(m.target.nodeValue); if (v !== m.target.nodeValue) m.target.nodeValue = v; } } else m.addedNodes.forEach(n => { if (n.nodeType === 1) walk(n); else if (n.nodeType === 3 && n.parentElement && !SKIP(n.parentElement)) { const v = tr(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; } }); } } finally { busy = false; } })
      .observe(document.body, {childList: true, subtree: true, characterData: true});
  });
})();
