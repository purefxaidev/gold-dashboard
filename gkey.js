/* PUREGOLD AI key manager. The key lives only in this browser (localStorage "gd_gemini_key") and is sent only to
   generativelanguage.googleapis.com. Handles invalid/expired keys (clear + ask again), quota (keep key, offer change),
   validates new keys with a cheap models.list call before saving. No emoji. */
(function () {
  const K = "gd_gemini_key", EN = () => (window.LANG || localStorage.getItem("gd_ui_lang") || "th") === "en", T = (th, en) => EN() ? en : th;
  const API = "https://generativelanguage.googleapis.com/v1beta";
  const subs = [];
  const G = {
    get: () => localStorage.getItem(K) || "",
    clear() { localStorage.removeItem(K); subs.forEach(f => { try { f(""); } catch (e) {} }); },
    onChange(f) { subs.push(f); },
    classify(status, text) {
      const s = String(text || "");
      if (status === 429 || /RESOURCE_EXHAUSTED|quota|rate limit/i.test(s)) return "quota";
      if (status === 401 || status === 403 || /API_KEY_INVALID|API key not valid|API key expired|PERMISSION_DENIED|API_KEY_SERVICE_BLOCKED|unregistered callers|unauthenticated/i.test(s)) return "auth";
      if (status === 400 && /api.?key/i.test(s)) return "auth";
      return null;
    },
    async validate(key) {
      try {
        const r = await fetch(API + "/models?pageSize=1", {headers: {"x-goog-api-key": key}, cache: "no-store"});
        if (r.ok) return {ok: true};
        let m = ""; try { const j = await r.json(); m = (j.error && (j.error.status + " " + j.error.message)) || ""; } catch (e) {}
        const kind = G.classify(r.status, m);
        return {ok: kind === "quota", kind, msg: kind === "auth" ? T("คีย์ไม่ถูกต้องหรือหมดอายุ", "Invalid or expired key") : kind === "quota" ? T("คีย์ใช้ได้ แต่โควตาฟรีหมดชั่วคราว", "Key works but the free quota is used up for now") : T("ตรวจคีย์ไม่ผ่าน (HTTP ", "Key check failed (HTTP ") + r.status + ")"};
      } catch (e) { return {ok: false, kind: "net", msg: T("เชื่อมต่อ Google ไม่ได้ ลองใหม่", "Could not reach Google, try again")}; }
    },
    async save(key) { key = String(key || "").trim(); if (!key) return {ok: false, msg: T("กรุณาวางคีย์", "Please paste a key")};
      const v = await G.validate(key); if (!v.ok) return v; localStorage.setItem(K, key); subs.forEach(f => { try { f(key); } catch (e) {} }); return v; },
    /* response helper: returns {kind, msg} and shows the right box for auth/quota */
    async handleResponse(r) {
      let m = ""; try { const j = await r.clone().json(); m = (j.error && ((j.error.status || "") + " " + (j.error.message || "") + " " + JSON.stringify(j.error.details || []))) || ""; } catch (e) { try { m = await r.clone().text(); } catch (e2) {} }
      const kind = G.classify(r.status, m); G.handle(kind); return {kind, msg: r.status + " " + m.slice(0, 160)};
    },
    handle(kind) { if (kind === "auth") { G.clear(); G.prompt("invalid"); } else if (kind === "quota") G.prompt("quota"); return kind; },
    message(kind) { return kind === "auth" ? T("คีย์ไม่ถูกต้องหรือหมดอายุ กรุณาใส่คีย์ใหม่", "Invalid or expired key, please enter a new one") : kind === "quota" ? T("โควตาฟรีหมดชั่วคราว ลองใหม่ภายหลัง หรือเปลี่ยนคีย์", "Free quota is used up for now. Try again later, or change the key") : ""; },
    prompt(reason, opt = {}) {
      document.querySelectorAll(".gk-ov").forEach(x => x.remove());
      const o = document.createElement("div"); o.className = "gk-ov notr"; o.id = "gkBox";
      o.style.cssText = "position:fixed;inset:0;z-index:2000;background:#000c;display:flex;align-items:center;justify-content:center;padding:16px;font-family:system-ui,'Noto Sans Thai',sans-serif";
      const head = reason === "invalid" ? G.message("auth") : reason === "quota" ? G.message("quota") : reason === "first" ? T("ตั้งค่าครั้งแรก: วาง AI key (Google AI Studio)", "First-time setup: paste your AI key (Google AI Studio)") : T("เปลี่ยน AI key (Google AI Studio)", "Change AI key (Google AI Studio)");
      const col = reason === "invalid" ? "#ff4d6d" : reason === "quota" ? "#fb8c00" : "#f5c542", has = !!G.get();
      o.innerHTML = `<div style="max-width:440px;width:100%;background:#11131a;border:1px solid ${col};border-radius:16px;padding:20px;box-shadow:0 0 40px ${col}44;color:#eee">
        <div id="gkHead" style="font-weight:700;font-size:16px;color:${col};margin-bottom:8px">${head}</div>
        <div style="font-size:13px;color:#aab;line-height:1.5">${T("คีย์ถูกเก็บเฉพาะในเบราว์เซอร์เครื่องนี้ และส่งไปที่ Google เท่านั้น ขอคีย์ฟรีได้ที่", "The key is stored only in this browser and is sent only to Google. Get a free key at")} <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" style="color:#36e2ff">aistudio.google.com/apikey</a></div>
        ${reason === "quota" ? `<div style="font-size:13px;margin-top:8px;color:#ddd">${T("คีย์เดิมยังเก็บไว้ ใช้ต่อได้เมื่อโควตารีเซ็ต หรือวางคีย์ใหม่ด้านล่าง", "Your current key is kept and will work again when the quota resets, or paste a new key below")}</div>` : ""}
        <input id="gkIn" type="password" autocomplete="off" spellcheck="false" placeholder="${has ? T("มีคีย์อยู่ (...", "Key saved (...") + G.get().slice(-4) + T(") วางคีย์ใหม่เพื่อเปลี่ยน", ") paste a new key to change") : T("วาง API key ที่นี่", "Paste API key here")}" style="width:100%;box-sizing:border-box;margin:12px 0 6px;padding:10px;border-radius:10px;border:1px solid #333;background:#0b0d12;color:#eee;font-size:14px">
        <div id="gkErr" role="alert" style="min-height:18px;font-size:12.5px;color:#ff6b81"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          <button id="gkSave" style="flex:1;min-width:120px;padding:10px;border-radius:10px;border:0;background:#f5c542;color:#111;font-weight:700;cursor:pointer">${T("ตรวจและบันทึก", "Check and save")}</button>
          ${has ? `<button id="gkDel" style="padding:10px 12px;border-radius:10px;border:1px solid #ff4d6d88;background:transparent;color:#ff8095;cursor:pointer">${T("ลบคีย์", "Delete key")}</button>` : ""}
          <button id="gkClose" style="padding:10px 12px;border-radius:10px;border:1px solid #444;background:transparent;color:#ccc;cursor:pointer">${reason === "first" ? T("ไว้ทีหลัง", "Later") : T("ปิด", "Close")}</button></div></div>`;
      document.body.appendChild(o);
      const $ = id => o.querySelector("#" + id), close = () => { o.remove(); opt.onClose && opt.onClose(); };
      $("gkIn").focus();
      $("gkSave").onclick = async () => { const k = $("gkIn").value.trim(); if (!k) { $("gkErr").textContent = T("กรุณาวางคีย์", "Please paste a key"); return; }
        $("gkSave").disabled = true; $("gkErr").style.color = "#aab"; $("gkErr").textContent = T("กำลังตรวจคีย์กับ Google...", "Checking the key with Google...");
        const v = await G.save(k); $("gkSave").disabled = false;
        if (!v.ok) { $("gkErr").style.color = "#ff6b81"; $("gkErr").textContent = v.msg + (v.kind === "auth" ? T(" กรุณาตรวจแล้ววางใหม่", ", please check and paste again") : ""); return; }
        o.remove(); opt.onSaved && opt.onSaved(v); };
      $("gkIn").addEventListener("keydown", e => { if (e.key === "Enter") $("gkSave").click(); });
      if ($("gkDel")) $("gkDel").onclick = () => { G.clear(); o.remove(); opt.onDeleted && opt.onDeleted(); };
      $("gkClose").onclick = close;
      return o;
    },
    /* small always-visible button: "เปลี่ยนคีย์ / Change key" */
    button(host, opt = {}) {
      if (!host) return; const b = document.createElement("button"); b.type = "button"; b.className = "gk-btn notr";
      b.style.cssText = "padding:4px 10px;border-radius:999px;border:1px solid #f5c54266;background:transparent;color:#f5c542;font:600 11.5px system-ui,'Noto Sans Thai',sans-serif;cursor:pointer;white-space:nowrap" + (opt.style || "");
      const lab = () => b.textContent = G.get() ? T("เปลี่ยนคีย์", "Change key") : T("ใส่คีย์", "Add key"); lab(); G.onChange(lab);
      b.onclick = () => G.prompt(G.get() ? "change" : "first", opt); host.appendChild(b); return b;
    }
  };
  window.addEventListener("storage", e => { if (e.key === K) subs.forEach(f => { try { f(e.newValue || ""); } catch (x) {} }); });
  window.GKEY = G;
})();
