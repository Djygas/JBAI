/* Фронтенд: отправка сообщения на /api/chat и разбор SSE-потока.
   Никаких ключей здесь нет — HF_TOKEN живёт только на сервере (backend/.env). */
(() => {
  "use strict";

  const chatEl = document.getElementById("chat");
  const formEl = document.getElementById("form");
  const inputEl = document.getElementById("input");
  const sendEl = document.getElementById("send");
  const stopEl = document.getElementById("stop");
  const clearEl = document.getElementById("clear");
  const statusEl = document.getElementById("status");

  /** история диалога: [{role:"user"|"assistant", content:"..."}] */
  const history = [];
  let controller = null;
  let busy = false;

  const escapeHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  /* минимальный markdown: ```блоки```, `код`, **жирный** */
  function render(text) {
    let html = escapeHtml(text);
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code data-lang="${lang || ""}">${code.replace(/\n$/, "")}</code></pre>`);
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return html;
  }

  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = render(text || "");
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    scrollDown();
    return bubble;
  }

  const scrollDown = () => { chatEl.scrollTop = chatEl.scrollHeight; };

  function setStatus(text, kind = "") {
    statusEl.textContent = text;
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  function setBusy(state) {
    busy = state;
    sendEl.disabled = state;
    inputEl.disabled = state;
    stopEl.hidden = !state;
  }

  function autoGrow() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
  }

  async function send(text) {
    setBusy(true);
    setStatus("печатает…", "busy");

    history.push({ role: "user", content: text });
    addMessage("user", text);

    const bubble = addMessage("assistant", "");
    bubble.classList.add("cursor");

    let answer = "";
    controller = new AbortController();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText}`);
      }
      if (!res.body) {
        throw new Error("ответ без тела (поток не поддерживается)");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split("\n\n");
        buffer = frames.pop();
        for (const frameText of frames) {
          const line = frameText.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let payload;
          try {
            payload = JSON.parse(line.slice(5).trim());
          } catch {
            continue;
          }
          if (payload.delta) {
            answer += payload.delta;
            bubble.innerHTML = render(answer);
            scrollDown();
          }
          if (payload.error) {
            throw new Error(payload.error);
          }
        }
      }

      if (!answer) bubble.textContent = "(пустой ответ)";
      history.push({ role: "assistant", content: answer });
      setStatus("готов");
    } catch (err) {
      if (err.name === "AbortError") {
        if (answer) history.push({ role: "assistant", content: answer });
        setStatus("остановлено");
      } else {
        bubble.innerHTML = `<span style="color:var(--danger)">Ошибка: ${escapeHtml(err.message)}</span>`;
        setStatus("ошибка", "error");
        history.pop();
      }
    } finally {
      bubble.classList.remove("cursor");
      setBusy(false);
      controller = null;
      inputEl.focus();
      scrollDown();
    }
  }

  formEl.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) return;
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    autoGrow();
    send(text);
  });

  stopEl.addEventListener("click", () => controller && controller.abort());

  clearEl.addEventListener("click", () => {
    if (busy || !confirm("Очистить историю диалога?")) return;
    history.length = 0;
    chatEl.innerHTML = "";
    addMessage("assistant", "История очищена. О чём поговорим?");
    setStatus("готов");
  });

  inputEl.addEventListener("input", autoGrow);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formEl.requestSubmit();
    }
  });

  inputEl.focus();
})();
