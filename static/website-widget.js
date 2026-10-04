/**
 * אורן כהן גרופ — Website Chat Widget
 * הטמעה: <script src="https://YOUR_DOMAIN/static/website-widget.js" defer></script>
 */
(function () {
  const BASE_URL = (window.OCG_BASE_URL || "").replace(/\/$/, "");
  const GREETING = "היי, איך אוכל לעזור? 😊";
  const LOGO = "https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg";

  // ── Styles ──────────────────────────────────────────────────────────────────
  const css = `
    #ocg-widget-btn {
      position: fixed; bottom: 24px; left: 24px; z-index: 9998;
      width: 60px; height: 60px; border-radius: 50%;
      background: #1a3c2e; border: none; cursor: pointer;
      box-shadow: 0 4px 20px rgba(0,0,0,0.35);
      display: flex; align-items: center; justify-content: center;
      transition: transform .2s;
    }
    #ocg-widget-btn:hover { transform: scale(1.08); }
    #ocg-widget-btn img { width: 38px; height: 38px; object-fit: contain; }
    #ocg-widget-btn .ocg-badge {
      position: absolute; top: 0; right: 0;
      width: 14px; height: 14px; border-radius: 50%;
      background: #25d366; border: 2px solid #fff;
    }
    #ocg-widget-box {
      position: fixed; bottom: 96px; left: 24px; z-index: 9999;
      width: 360px; max-width: calc(100vw - 32px);
      height: 520px; max-height: calc(100vh - 120px);
      border-radius: 16px; overflow: hidden;
      box-shadow: 0 8px 40px rgba(0,0,0,0.28);
      display: flex; flex-direction: column;
      font-family: 'Segoe UI', 'Noto Sans Hebrew', Arial, sans-serif;
      direction: rtl;
      transform: scale(0.85) translateY(20px);
      opacity: 0; pointer-events: none;
      transition: transform .25s cubic-bezier(.34,1.56,.64,1), opacity .2s;
    }
    #ocg-widget-box.open {
      transform: scale(1) translateY(0);
      opacity: 1; pointer-events: all;
    }
    .ocg-header {
      background: #1a3c2e; color: #fff;
      padding: 12px 16px; display: flex; align-items: center; gap: 10px;
      flex-shrink: 0;
    }
    .ocg-header img { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }
    .ocg-header-info { flex: 1; }
    .ocg-header-name { font-size: 15px; font-weight: 600; }
    .ocg-header-sub { font-size: 12px; opacity: .75; }
    .ocg-close-btn {
      background: none; border: none; color: #fff; cursor: pointer;
      font-size: 20px; line-height: 1; padding: 4px; opacity: .8;
    }
    .ocg-close-btn:hover { opacity: 1; }
    .ocg-messages {
      flex: 1; overflow-y: auto; padding: 12px;
      background: #efeae2; display: flex; flex-direction: column; gap: 6px;
    }
    .ocg-messages::-webkit-scrollbar { width: 4px; }
    .ocg-messages::-webkit-scrollbar-thumb { background: #c5c5c5; border-radius: 2px; }
    .ocg-msg {
      max-width: 82%; padding: 8px 12px; border-radius: 10px;
      font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
    }
    .ocg-msg.in { background: #fff; align-self: flex-start; border-bottom-right-radius: 3px; }
    .ocg-msg.out { background: #d9fdd3; align-self: flex-end; border-bottom-left-radius: 3px; }
    .ocg-msg-time { font-size: 11px; color: #667781; margin-top: 2px; display: block; text-align: left; }
    .ocg-typing {
      background: #fff; align-self: flex-start;
      padding: 10px 14px; border-radius: 10px; border-bottom-right-radius: 3px;
      display: flex; gap: 4px; align-items: center;
    }
    .ocg-dot {
      width: 7px; height: 7px; border-radius: 50%; background: #aaa;
      animation: ocgBounce 1.4s infinite;
    }
    .ocg-dot:nth-child(2) { animation-delay: .2s; }
    .ocg-dot:nth-child(3) { animation-delay: .4s; }
    @keyframes ocgBounce {
      0%,60%,100% { transform: translateY(0); opacity: .5; }
      30% { transform: translateY(-5px); opacity: 1; }
    }
    .ocg-footer {
      background: #f0f2f5; border-top: 1px solid #e0e0e0;
      padding: 8px 10px; display: flex; align-items: flex-end; gap: 8px;
      flex-shrink: 0;
    }
    .ocg-input {
      flex: 1; background: #fff; border: 1px solid #ddd; border-radius: 22px;
      padding: 8px 14px; font-size: 14px; outline: none; resize: none;
      max-height: 90px; overflow-y: auto; line-height: 1.4;
      font-family: inherit; direction: rtl;
    }
    .ocg-send-btn {
      width: 38px; height: 38px; border-radius: 50%; border: none;
      background: #1a3c2e; cursor: pointer; display: flex;
      align-items: center; justify-content: center; flex-shrink: 0;
      transition: background .15s;
    }
    .ocg-send-btn:hover { background: #25d366; }
    .ocg-send-btn svg { fill: #fff; width: 18px; height: 18px; }
    .ocg-powered {
      text-align: center; font-size: 10px; color: #aaa;
      padding: 4px 0 2px; background: #f0f2f5;
    }
  `;

  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ── HTML ─────────────────────────────────────────────────────────────────────
  const btn = document.createElement("button");
  btn.id = "ocg-widget-btn";
  btn.innerHTML = `<img src="${LOGO}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><circle cx=%2220%22 cy=%2220%22 r=%2220%22 fill=%22%231a3c2e%22/><text x=%2250%%25%22 y=%2255%%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22white%22 font-size=%2218%22>ד</text></svg>'" alt="chat"><span class="ocg-badge"></span>`;

  const box = document.createElement("div");
  box.id = "ocg-widget-box";
  box.innerHTML = `
    <div class="ocg-header">
      <img src="${LOGO}" onerror="this.style.display='none'" alt="logo">
      <div class="ocg-header-info">
        <div class="ocg-header-name">דניאל · אורן כהן גרופ</div>
        <div class="ocg-header-sub">עונה בדרך כלל תוך דקות</div>
      </div>
      <button class="ocg-close-btn" id="ocg-close">✕</button>
    </div>
    <div class="ocg-messages" id="ocg-msgs"></div>
    <div class="ocg-footer">
      <textarea class="ocg-input" id="ocg-input" rows="1" placeholder="כתוב הודעה..."></textarea>
      <button class="ocg-send-btn" id="ocg-send">
        <svg viewBox="0 0 24 24"><path d="M1.1 21.76L23.8 12.03 1.1 2.3l.01 7.91 13.62 1.82-13.62 1.82-.01 7.91z"/></svg>
      </button>
    </div>
    <div class="ocg-powered">Powered by Oren Cohen Group</div>
  `;

  document.body.appendChild(btn);
  document.body.appendChild(box);

  // ── State ────────────────────────────────────────────────────────────────────
  let sessionId = null;
  let isOpen = false;
  let greeted = false;

  const msgs = document.getElementById("ocg-msgs");
  const input = document.getElementById("ocg-input");

  function getTime() {
    return new Date().toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  }

  function addMsg(text, type) {
    const d = document.createElement("div");
    d.className = `ocg-msg ${type}`;
    d.innerHTML = `${text.replace(/\n/g, "<br>")}<span class="ocg-msg-time">${getTime()}</span>`;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    const d = document.createElement("div");
    d.id = "ocg-typing";
    d.className = "ocg-typing";
    d.innerHTML = '<span class="ocg-dot"></span><span class="ocg-dot"></span><span class="ocg-dot"></span>';
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function hideTyping() {
    const el = document.getElementById("ocg-typing");
    if (el) el.remove();
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    addMsg(text, "out");
    input.value = "";
    input.style.height = "auto";
    showTyping();
    try {
      const res = await fetch(BASE_URL + "/agent-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      const data = await res.json();
      sessionId = data.session_id;
      hideTyping();
      addMsg(data.reply, "in");

      // אם הבוט מבקש העברה לסוכן — הצג כפתור WhatsApp
      if (data.handoff_to_human) {
        showHandoff();
      }
    } catch {
      hideTyping();
      addMsg("מצטערים, אירעה שגיאה. נסה שוב.", "in");
    }
  }

  function showHandoff() {
    if (document.getElementById("ocg-handoff")) return;
    const d = document.createElement("div");
    d.id = "ocg-handoff";
    d.style.cssText = "text-align:center; padding: 10px 12px;";
    d.innerHTML = `
      <a href="https://wa.me/972549183150?text=${encodeURIComponent('היי, אני מעוניין לשמוע עוד על נכסים')}"
         target="_blank"
         style="display:inline-flex;align-items:center;gap:6px;background:#25d366;color:#fff;
                padding:8px 18px;border-radius:20px;text-decoration:none;font-size:13px;font-weight:600;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
        דבר עם סוכן
      </a>`;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function open() {
    isOpen = true;
    box.classList.add("open");
    if (!greeted) {
      greeted = true;
      setTimeout(() => addMsg(GREETING, "in"), 300);
    }
    input.focus();
  }

  function close() {
    isOpen = false;
    box.classList.remove("open");
  }

  btn.addEventListener("click", () => (isOpen ? close() : open()));
  document.getElementById("ocg-close").addEventListener("click", close);
  document.getElementById("ocg-send").addEventListener("click", send);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 90) + "px";
  });

  // פתח אוטומטית אחרי 5 שניות (אופציונלי — הסר אם לא רוצה)
  // setTimeout(open, 5000);
})();
