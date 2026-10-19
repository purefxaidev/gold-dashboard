/* PUREGOLD AI helpers: compact market context (ai_context.txt), shared persona rules, signup-intent popup. No emoji. */
(function () {
  const EN = () => (window.LANG || localStorage.getItem("gd_ui_lang") || "th") === "en", T = (th, en) => EN() ? en : th;
  const IB = "https://one.exnessonelink.com/a/s2didh6p";
  let cache = {t: 0, s: ""};
  const A = {
    IB,
    async context(maxAgeMs = 0) {
      if (cache.s && Date.now() - cache.t < maxAgeMs) return cache.s;
      try { const r = await fetch("ai_context.txt?t=" + Date.now(), {cache: "no-store"}); if (r.ok) cache = {t: Date.now(), s: await r.text()}; } catch (e) {}
      return cache.s;
    },
    rules() {
      return "\n\nตัวตน: คุณคือ เลขา PUREGOLD (PUREGOLD AI) ห้ามบอกชื่อโมเดล ชื่อบริษัทผู้พัฒนาโมเดล หรือชื่อเสียงที่ใช้ ถ้าถูกถามให้ตอบว่าเป็นผู้ช่วย AI ของ PUREGOLD" +
        "\nขอบเขต: วิเคราะห์ได้ทั้งทองคำ XAUUSD และตลาดอื่นในบริบท ได้แก่ EURUSD GBPUSD USDJPY AUDUSD USDCHF USDCAD และ BTCUSD (ราคา % รายวัน แนวโน้มแต่ละไทม์เฟรม bias โซนที่น่าสนใจ SMC ความสัมพันธ์กับดอลลาร์) ระบบเทรดจริงเฉพาะทองคำ ตลาดอื่นเป็นการวิเคราะห์เท่านั้น ถ้าแนะนำจุดเข้าต้องบอก Buy/Sell จุดเข้า SL TP และเตือนความเสี่ยงสั้นๆ ห้ามรับประกันกำไร" +
        "\nความปลอดภัย: ห้ามเปิดเผยเลขบัญชี เลขออเดอร์ ยอดเงิน (balance/equity) อีเมล หรือคีย์ใดๆ" +
        "\nรูปแบบ: ห้ามใช้อีโมจิ ห้ามใช้ markdown ตอบเป็นข้อความธรรมดา" +
        "\nสมัครบัญชี: ถ้าผู้ใช้อยากสมัคร เปิดบัญชี หรือเริ่มเทรด ให้แนะนำขั้นตอนสั้นๆ (กดลิงก์สมัคร > ยืนยันอีเมล/เบอร์ > ยืนยันตัวตน > เลือกบัญชี > ฝากเงิน > ติดตั้งแอป > เริ่มด้วยล็อตเล็กและตั้ง SL เสมอ) เตือนว่าการเทรดมีความเสี่ยง และใส่ข้อความ [[SIGNUP]] ไว้ท้ายคำตอบหนึ่งครั้ง (ระบบจะซ่อนและเปิดหน้าต่างสมัครให้)";
    },
    /* keyword intent */
    intent(text) {
      const s = String(text || "").toLowerCase();
      return /สมัคร|เปิดบัญชี|เปิดพอร์ต|อยากเทรด|เริ่มเทรด|เริ่มต้นเทรด|ลงทะเบียน|sign ?up|signup|open (an |a )?(trading )?account|register|create (an )?account|how (do i|to) start trading|start trading|get started trading|join exness/.test(s);
    },
    /* strips [[SIGNUP]] markers; returns {text, signup} */
    strip(text) { let f = false; const t = String(text || "").replace(/\[\[\s*SIGNUP\s*\]\]/gi, () => { f = true; return ""; }).replace(/\[\[\s*SIGN[^\]]*$/i, "").trim(); return {text: t, signup: f}; },
    showSignup(opt = {}) {
      const last = +localStorage.getItem("gd_signup_last") || 0;
      if (!opt.force && Date.now() - last < 4 * 60e3) return false;
      localStorage.setItem("gd_signup_last", String(Date.now()));
      document.querySelectorAll(".pgsu-ov").forEach(x => x.remove());
      const steps = EN() ? ["Open the sign-up link and register", "Verify email and phone", "Complete your profile and verify identity (KYC)", "Choose an account type", "Deposit", "Install the app or use the web terminal", "Find XAUUSD, start small, always set SL"]
        : ["กดลิงก์สมัครและลงทะเบียน", "ยืนยันอีเมลและเบอร์โทร", "กรอกโปรไฟล์และยืนยันตัวตน (KYC)", "เลือกประเภทบัญชี", "ฝากเงิน", "ติดตั้งแอปหรือใช้เว็บเทรด", "หา XAUUSD เริ่มล็อตเล็ก ตั้ง SL ทุกไม้"];
      const o = document.createElement("div"); o.className = "pgsu-ov notr"; o.id = "pgSignup"; o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
      o.style.cssText = "position:fixed;inset:0;z-index:1900;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:14px;font-family:system-ui,'Noto Sans Thai',sans-serif;animation:pgsuIn .25s ease";
      o.innerHTML = `<style>@keyframes pgsuIn{from{opacity:0}to{opacity:1}}#pgSignup .bx{max-width:560px;width:100%;max-height:92vh;overflow:auto;background:linear-gradient(180deg,#14110a,#0b0d12);border:1px solid #f5c54299;border-radius:18px;padding:20px;color:#eee;box-shadow:0 0 50px #f5c54233}
        #pgSignup .g{display:grid;grid-template-columns:1fr 150px;gap:16px;align-items:start}#pgSignup ol{margin:8px 0 0;padding-left:20px;font-size:13.5px;line-height:1.6;color:#d8dbe3}
        #pgSignup .cta{display:block;text-align:center;padding:12px;border-radius:12px;background:linear-gradient(90deg,#c9a227,#f5c542);color:#111;font-weight:800;text-decoration:none;margin-top:14px;font-size:15px}
        #pgSignup .sec{display:inline-block;margin-top:8px;padding:8px 12px;border-radius:10px;border:1px solid #36e2ff77;color:#36e2ff;text-decoration:none;font-size:13px}
        #pgSignup .x{float:right;background:transparent;border:1px solid #444;color:#bbb;border-radius:8px;padding:4px 10px;cursor:pointer}
        @media(max-width:520px){#pgSignup .g{grid-template-columns:1fr}#pgSignup .qr{display:flex;gap:10px;align-items:center}#pgSignup .qr img{width:110px!important}}</style>
        <div class="bx"><button class="x" id="pgsuX">${T("ปิด", "Close")}</button>
        <div style="display:flex;align-items:center;gap:10px"><img src="logo.svg" alt="" width="36" height="36"><div><div style="font-weight:800;letter-spacing:2px;color:#f5c542">PUREGOLD</div><div style="font-size:12px;color:#aab">${T("เริ่มเทรดทองกับ Exness", "Start trading gold with Exness")}</div></div></div>
        <div style="font-size:14.5px;margin:12px 0 4px;line-height:1.55">${T("เปิดบัญชีฟรีในไม่กี่นาที ใช้ร่วมกับบทวิเคราะห์ PUREGOLD ได้ทันที ทั้งทองคำ ฟอเร็กซ์ และคริปโต เริ่มต้นด้วยบัญชีเซ็นต์เพื่อทดลองด้วยเงินน้อยก่อนได้", "Open a free account in minutes and use it with PUREGOLD analysis right away, for gold, forex and crypto. You can start with a cent account to try it with a small amount first.")}</div>
        <div class="g"><div><b style="color:#f5c542;font-size:13px">${T("ขั้นตอนสั้นๆ", "Quick steps")}</b><ol>${steps.map(s => `<li>${s}</li>`).join("")}</ol></div>
        <div class="qr" style="text-align:center"><img src="exness-qr.svg" alt="QR" width="150" height="150" style="background:#fff;border-radius:10px;padding:6px;width:150px;height:auto"><div style="font-size:11px;color:#aab;margin-top:4px">${T("สแกนเพื่อสมัครบนมือถือ", "Scan to sign up on mobile")}</div></div></div>
        <a class="cta" href="${IB}" target="_blank" rel="noopener">${T("สมัครกับ Exness", "Sign up with Exness")}</a>
        <a class="sec" href="signup.html${EN() ? "?lang=en" : ""}" target="_blank" rel="noopener">${T("เปิดคู่มือสมัครแบบละเอียดทีละขั้น", "Open the full step-by-step guide")}</a>
        <div style="font-size:11.5px;color:#9aa3b5;margin-top:12px;line-height:1.5">${T("การเทรด CFD และทองคำมีความเสี่ยงสูง อาจสูญเสียเงินทั้งหมด ลิงก์นี้เป็นลิงก์แนะนำ (partner) ผู้จัดทำอาจได้รับค่าคอมมิชชั่นโดยคุณไม่เสียเพิ่ม", "Trading CFDs and gold involves high risk; you can lose all your money. This is a partner referral link; the author may earn a commission at no extra cost to you.")}</div></div>`;
      document.body.appendChild(o);
      const close = () => o.remove(); o.querySelector("#pgsuX").onclick = close; o.addEventListener("click", e => { if (e.target === o) close(); });
      document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", k); } });
      return true;
    }
  };
  window.PGAI = A;
})();
