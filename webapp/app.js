"use strict";

const TOKEN_KEY = "aquila_remote_token";
const HOST_KEY = "aquila_remote_host_id";
const INSTANCE_KEY = "aquila_remote_instance";

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  hostId: localStorage.getItem(HOST_KEY) || "",
  instanceId: localStorage.getItem(INSTANCE_KEY) || "",
  ws: null,
  streaming: false,
  initialized: { character: false, learn: false, research: false },
  engines: [],
};

/* ---------------- API helpers ---------------- */

function authHeaders(extra) {
  return Object.assign({ Authorization: `Bearer ${state.token}` }, extra || {});
}

async function api(path, opts) {
  opts = opts || {};
  const headers = authHeaders(opts.headers);
  if (opts.body && !headers["Content-Type"] && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  if (resp.status === 401) {
    handleLogout("Session expired — pair again.");
    throw new Error("unauthorized");
  }
  return resp;
}

async function apiJson(path, opts) {
  const resp = await api(path, opts);
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const d = await resp.json();
      detail = d.detail || d.message || detail;
    } catch (e) {}
    throw new Error(detail);
  }
  return resp.json();
}

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}?token=${encodeURIComponent(state.token)}`;
}

/* ---------------- Toast ---------------- */

let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

function confirmDialog(message) {
  return Promise.resolve(window.confirm(message));
}

/* ---------------- Rendering ---------------- */

function renderInto(node, text) {
  node.classList.add("rendered");
  node.innerHTML = AquilaMarkdown.render(text || "");
}

/* ---------------- Views ---------------- */

function showPairView() {
  $("#pair-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
  if (state.hostId) $("#pair-host-id").value = state.hostId;
}

function showAppView() {
  $("#pair-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
}

function switchPanel(targetId) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === targetId));
  document.querySelectorAll(".nav-btn").forEach((t) => t.classList.toggle("active", t.dataset.target === targetId));
  if (targetId === "servers-panel") refreshStatus();
  if (targetId === "character-panel" && !state.initialized.character) initCharacter();
  if (targetId === "learn-panel" && !state.initialized.learn) initLearn();
  if (targetId === "research-panel" && !state.initialized.research) initResearch();
}

/* ---------------- Pairing ---------------- */

async function doPair() {
  const hostId = $("#pair-host-id").value.trim();
  const code = $("#pair-code").value.trim();
  const deviceName = $("#pair-device-name").value.trim() || "device";
  const errEl = $("#pair-error");
  errEl.classList.add("hidden");
  if (!hostId || !code) {
    errEl.textContent = "Enter both Host ID and pairing code.";
    errEl.classList.remove("hidden");
    return;
  }
  $("#pair-btn").disabled = true;
  try {
    const resp = await fetch("/api/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host_id: hostId, pairing_code: code, device_name: deviceName }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || "Pairing failed");
    }
    const data = await resp.json();
    state.token = data.token;
    state.hostId = data.host_id;
    localStorage.setItem(TOKEN_KEY, state.token);
    localStorage.setItem(HOST_KEY, state.hostId);
    await enterApp();
  } catch (e) {
    errEl.textContent = e.message || String(e);
    errEl.classList.remove("hidden");
  } finally {
    $("#pair-btn").disabled = false;
  }
}

function handleLogout(message) {
  state.token = "";
  localStorage.removeItem(TOKEN_KEY);
  if (state.ws) {
    try { state.ws.close(); } catch (e) {}
    state.ws = null;
  }
  showPairView();
  if (message) toast(message);
}

/* ---------------- Instances ---------------- */

async function loadInstances() {
  try {
    const data = await apiJson("/api/instances");
    const sel = $("#instance-select");
    sel.innerHTML = "";
    (data.instances || []).forEach((inst) => {
      const opt = document.createElement("option");
      opt.value = inst.id;
      opt.textContent = `${inst.display_name} [${inst.default_mode}]`;
      sel.appendChild(opt);
    });
    if (state.instanceId && [...sel.options].some((o) => o.value === state.instanceId)) {
      sel.value = state.instanceId;
    } else if (sel.options.length) {
      state.instanceId = sel.value;
    }
  } catch (e) {}
}

/* ---------------- Attachments ---------------- */

// A reusable attachment manager bound to a chips container. Uploads files to
// /api/uploads and tracks the returned upload_tokens to send with messages.
function createAttachments(chipsEl) {
  const tokens = [];
  function render() {
    chipsEl.innerHTML = "";
    tokens.forEach((t, idx) => {
      const chip = el("span", "chip");
      chip.appendChild(el("span", null, t.label));
      const rm = el("button", null, "✕");
      rm.type = "button";
      rm.addEventListener("click", () => {
        tokens.splice(idx, 1);
        render();
      });
      chip.appendChild(rm);
      chipsEl.appendChild(chip);
    });
  }
  async function pick() {
    const files = await pickFiles();
    if (!files || !files.length) return;
    const form = new FormData();
    [...files].forEach((f) => form.append("files", f, f.name));
    try {
      toast(`Uploading ${files.length} file(s)…`);
      const data = await apiJson("/api/uploads", { method: "POST", body: form });
      tokens.push({
        token: data.upload_token,
        label: (data.file_names || []).join(", ") || "files",
      });
      render();
      toast("Attached.");
    } catch (e) {
      toast(`Upload failed: ${e.message}`);
    }
  }
  return {
    pick,
    clear() { tokens.length = 0; render(); },
    tokens() { return tokens.map((t) => t.token); },
    hasAny() { return tokens.length > 0; },
  };
}

let _filePickResolve = null;
function pickFiles() {
  return new Promise((resolve) => {
    const input = $("#hidden-file-input");
    _filePickResolve = resolve;
    input.value = "";
    input.onchange = () => {
      const files = input.files;
      const r = _filePickResolve;
      _filePickResolve = null;
      if (r) r(files);
    };
    input.click();
  });
}

/* ---------------- Reusable chat engine ---------------- */

// Build a chat surface inside `root`. Returns helpers. `opts`:
//   mode: "chat"|"character"|"learn_tutor"|"learn_archive"
//   extra: object merged into each WS request (persona_id, course_id, ...)
//   clientHistory: bool — keep history client-side (default chat). For
//     server-authoritative modes, history is loaded/saved on the host.
//   initialHistory: [{role, content}] to pre-render.
function createChat(root, opts) {
  opts = opts || {};
  const mode = opts.mode || "chat";
  const clientHistory = opts.clientHistory !== false ? mode === "chat" : false;

  root.innerHTML = "";
  const messages = el("div", "messages");
  const form = el("form", "composer");
  const chips = el("div", "attach-chips");
  const row1 = el("div", "composer-row");
  const attachBtn = el("button", "ghost", "Attach");
  attachBtn.type = "button";
  row1.appendChild(attachBtn);
  const row2 = el("div", "composer-row");
  const input = el("textarea");
  input.rows = 1;
  input.placeholder = opts.placeholder || "Message…";
  const sendBtn = el("button", "primary", "Send");
  sendBtn.type = "submit";
  const stopBtn = el("button", "ghost hidden", "Stop");
  stopBtn.type = "button";
  row2.appendChild(input);
  row2.appendChild(sendBtn);
  row2.appendChild(stopBtn);
  form.appendChild(chips);
  if (opts.headerNode) root.appendChild(opts.headerNode);
  form.appendChild(row1);
  form.appendChild(row2);
  root.appendChild(messages);
  root.appendChild(form);

  const attachments = createAttachments(chips);
  attachBtn.addEventListener("click", () => attachments.pick());

  const localHistory = [];
  let streaming = false;
  let ws = null;

  function scroll() { messages.scrollTop = messages.scrollHeight; }

  function addMessage(role, text) {
    const wrap = el("div", `msg ${role}`);
    wrap.appendChild(el("div", "role", role === "user" ? "You" : "🦅 Aquila"));
    const bubble = el("div", "bubble");
    bubble.textContent = text || "";
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    scroll();
    return { wrap, bubble };
  }

  function addThinking(wrap) {
    const details = el("details", "thinking");
    const summary = el("summary", null, "Thinking");
    const body = el("div", "think-body");
    details.appendChild(summary);
    details.appendChild(body);
    wrap.insertBefore(details, wrap.querySelector(".bubble"));
    return { details, body };
  }

  function setStreaming(on) {
    streaming = on;
    sendBtn.classList.toggle("hidden", on);
    stopBtn.classList.toggle("hidden", !on);
  }

  (opts.initialHistory || []).forEach((m) => {
    const { bubble } = addMessage(m.role === "user" ? "user" : "assistant", "");
    if (m.role === "user") bubble.textContent = m.content;
    else renderInto(bubble, m.content);
  });

  function send(evt) {
    if (evt) evt.preventDefault();
    if (streaming) return;
    const message = input.value.trim();
    if (!message) return;

    input.value = "";
    input.style.height = "auto";
    addMessage("user", message);
    const { wrap, bubble } = addMessage("assistant", "");
    let thinking = null;
    let answer = "";

    ws = new WebSocket(wsUrl("/api/chat"));
    state.ws = ws;
    setStreaming(true);

    ws.onopen = () => {
      ws.send(JSON.stringify(Object.assign({
        instance_id: state.instanceId,
        mode: mode,
        message: message,
        light_research: opts.lightResearchEl ? opts.lightResearchEl.checked : false,
        history: clientHistory ? localHistory : undefined,
        upload_tokens: attachments.tokens(),
      }, opts.extra || {})));
      attachments.clear();
    };

    ws.onmessage = (ev) => {
      let frame;
      try { frame = JSON.parse(ev.data); } catch (e) { return; }
      if (frame.type === "thinking") {
        if (!thinking) { thinking = addThinking(wrap); thinking.details.open = true; }
        thinking.body.textContent += frame.delta;
        scroll();
      } else if (frame.type === "token") {
        answer += frame.delta;
        bubble.textContent = answer;
        scroll();
      } else if (frame.type === "done") {
        if (frame.content) answer = frame.content;
        renderInto(bubble, answer);
        if (clientHistory && answer) {
          localHistory.push({ role: "user", content: message });
          localHistory.push({ role: "assistant", content: answer });
        }
        if (thinking) thinking.details.open = false;
        scroll();
        finish();
      } else if (frame.type === "error") {
        if (answer) renderInto(bubble, answer);
        else bubble.textContent = `⚠ ${frame.error}`;
        toast(`Error: ${frame.error}`);
        finish();
      }
    };
    ws.onerror = () => toast("Connection error");
    ws.onclose = () => { setStreaming(false); state.ws = null; ws = null; };
  }

  function finish() {
    setStreaming(false);
    if (ws) { try { ws.close(); } catch (e) {} }
  }

  form.addEventListener("submit", send);
  stopBtn.addEventListener("click", () => { if (ws) { try { ws.close(); } catch (e) {} ws = null; } setStreaming(false); });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });

  return { addMessage, messages, attachments };
}

/* ---------------- Main chat panel ---------------- */

let mainChat = null;
function setupMainChat() {
  // The main chat panel is hand-authored in index.html; wire it directly so
  // we keep the existing markup, but route rendering through markdown.
  const messages = $("#messages");
  const form = $("#chat-form");
  const input = $("#chat-input");
  const chips = $("#chat-attach-chips");
  const attachments = createAttachments(chips);
  mainChat = { attachments };

  $("#chat-panel .attach-btn").addEventListener("click", () => attachments.pick());

  let streaming = false;
  let ws = null;
  const history = [];

  function scroll() { messages.scrollTop = messages.scrollHeight; }
  function setStreaming(on) {
    streaming = on;
    $("#send-btn").classList.toggle("hidden", on);
    $("#stop-btn").classList.toggle("hidden", !on);
  }
  function addMessage(role, text) {
    const wrap = el("div", `msg ${role}`);
    wrap.appendChild(el("div", "role", role === "user" ? "You" : "🦅 Aquila"));
    const bubble = el("div", "bubble");
    bubble.textContent = text || "";
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    scroll();
    return { wrap, bubble };
  }
  function addThinking(wrap) {
    const details = el("details", "thinking");
    details.appendChild(el("summary", null, "Thinking"));
    const body = el("div", "think-body");
    details.appendChild(body);
    wrap.insertBefore(details, wrap.querySelector(".bubble"));
    return { details, body };
  }

  function send(evt) {
    if (evt) evt.preventDefault();
    if (streaming) return;
    const message = input.value.trim();
    if (!message) return;
    if (!state.instanceId) { toast("No instance selected"); return; }
    input.value = "";
    input.style.height = "auto";
    addMessage("user", message);
    const { wrap, bubble } = addMessage("assistant", "");
    let thinking = null;
    let answer = "";

    ws = new WebSocket(wsUrl("/api/chat"));
    state.ws = ws;
    setStreaming(true);
    ws.onopen = () => {
      ws.send(JSON.stringify({
        instance_id: state.instanceId,
        mode: "chat",
        message: message,
        light_research: $("#light-research").checked,
        history: history,
        upload_tokens: attachments.tokens(),
      }));
      attachments.clear();
    };
    ws.onmessage = (ev) => {
      let frame;
      try { frame = JSON.parse(ev.data); } catch (e) { return; }
      if (frame.type === "thinking") {
        if (!thinking) { thinking = addThinking(wrap); thinking.details.open = true; }
        thinking.body.textContent += frame.delta;
        scroll();
      } else if (frame.type === "token") {
        answer += frame.delta;
        bubble.textContent = answer;
        scroll();
      } else if (frame.type === "done") {
        if (frame.content) answer = frame.content;
        renderInto(bubble, answer);
        if (answer) {
          history.push({ role: "user", content: message });
          history.push({ role: "assistant", content: answer });
        }
        if (thinking) thinking.details.open = false;
        scroll();
        finish();
      } else if (frame.type === "error") {
        if (answer) renderInto(bubble, answer); else bubble.textContent = `⚠ ${frame.error}`;
        toast(`Error: ${frame.error}`);
        finish();
      }
    };
    ws.onerror = () => toast("Connection error");
    ws.onclose = () => { setStreaming(false); state.ws = null; ws = null; };
  }
  function finish() { setStreaming(false); if (ws) { try { ws.close(); } catch (e) {} } }

  form.addEventListener("submit", send);
  $("#stop-btn").addEventListener("click", () => { if (ws) { try { ws.close(); } catch (e) {} ws = null; } setStreaming(false); });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("#instance-select").addEventListener("change", (e) => {
    state.instanceId = e.target.value;
    localStorage.setItem(INSTANCE_KEY, state.instanceId);
    history.length = 0;
    messages.innerHTML = "";
  });
}

/* ---------------- Task runner client ---------------- */

// Runs a /api/task job. `payload` -> WS request; callbacks receive frames.
// Returns a controller with stop(). Reused by Research and build flows.
function runTask(payload, handlers) {
  handlers = handlers || {};
  const ws = new WebSocket(wsUrl("/api/task"));
  ws.onopen = () => ws.send(JSON.stringify(payload));
  ws.onmessage = (ev) => {
    let frame;
    try { frame = JSON.parse(ev.data); } catch (e) { return; }
    if (frame.type === "thinking" && handlers.onThinking) handlers.onThinking(frame.delta);
    else if (frame.type === "ledger" && handlers.onLedger) handlers.onLedger(frame.text);
    else if (frame.type === "plan" && handlers.onPlan) handlers.onPlan(frame.state);
    else if (frame.type === "busy" && handlers.onBusy) handlers.onBusy(frame.message);
    else if (frame.type === "done" && handlers.onDone) handlers.onDone(frame);
    else if (frame.type === "error" && handlers.onError) handlers.onError(frame.error);
  };
  ws.onerror = () => { if (handlers.onError) handlers.onError("connection error"); };
  ws.onclose = () => { if (handlers.onClose) handlers.onClose(); };
  return {
    stop() { try { ws.send(JSON.stringify({ action: "stop" })); } catch (e) {} },
    close() { try { ws.close(); } catch (e) {} },
  };
}

function renderPlanSteps(container, planState) {
  container.innerHTML = "";
  const steps = (planState && (planState.steps || planState.plan || planState.todos)) || [];
  if (!Array.isArray(steps) || !steps.length) {
    container.appendChild(el("p", "muted", "Planning…"));
    return;
  }
  steps.forEach((s, i) => {
    const row = el("div", "plan-step");
    const status = (s.status || s.state || "").toLowerCase();
    const badge = el("span", "st-status", status || "pending");
    if (status.includes("done") || status.includes("complete")) badge.classList.add("done");
    else if (status.includes("progress") || status.includes("active") || status.includes("running")) badge.classList.add("active");
    row.appendChild(badge);
    row.appendChild(el("span", null, s.title || s.content || s.description || s.name || `Step ${i + 1}`));
    container.appendChild(row);
  });
}

/* ---------------- Servers ---------------- */

async function refreshStatus() {
  const cards = $("#engine-cards");
  try {
    const data = await apiJson("/api/server/status");
    state.engines = data.engines || [];
    cards.innerHTML = "";
    state.engines.forEach((eng) => cards.appendChild(engineCard(eng)));
    updateEngineIndicator();
  } catch (e) {
    cards.innerHTML = '<p class="muted">Could not load status.</p>';
  }
}

function updateEngineIndicator() {
  const up = state.engines.filter((e) => e.up);
  const ind = $("#engine-indicator");
  const dot = $("#conn-dot");
  if (up.length) {
    const names = up.map((e) => (e.engine === "tq" ? "TurboQuant" : "Stock")).join(" + ");
    ind.textContent = names;
    ind.classList.add("running");
    dot.className = "dot ok";
  } else {
    ind.textContent = "no engine";
    ind.classList.remove("running");
    dot.className = "dot down";
  }
}

function engineCard(eng) {
  const card = el("div", "engine-card");
  const label = eng.engine === "tq" ? "TurboQuant" : "Stock";
  const models = (eng.loaded_models || []).join(", ") || "none loaded";
  card.innerHTML = `
    <div class="head">
      <div class="name">${label}</div>
      <span class="badge ${eng.up ? "up" : "down"}">${eng.up ? "online" : "offline"}</span>
    </div>
    <div class="url">${eng.base_url}</div>
    <div class="models">Loaded: ${models}</div>
    <label class="muted" style="display:block;margin:8px 0 4px">aquila model</label>
    <select class="engine-model-select" data-engine="${eng.engine}"></select>
    <div class="actions"></div>`;
  const select = card.querySelector(".engine-model-select");
  loadEngineModels(eng.engine, select);
  const actions = card.querySelector(".actions");
  actions.appendChild(makeBtn(eng.up ? "Stop" : "Start", eng.up ? "ghost" : "primary", async () => {
    if (eng.up) {
      await serverAction("/api/server/stop", { engine: eng.engine });
    } else {
      await startEngine(eng.engine);
    }
  }));
  actions.appendChild(makeBtn("Use for chat", "ghost", () => useEngineForChat(eng.engine, select.value)));
  actions.appendChild(makeBtn("Warm up", "ghost", () => modelAction("/api/model/warmup", { model: eng.engine })));
  actions.appendChild(makeBtn("Eject", "ghost", () => modelAction("/api/model/eject", { model: eng.engine, all_loaded: true })));
  actions.appendChild(makeBtn("Logs", "ghost", () => showLogs(eng.engine)));
  return card;
}

async function loadEngineModels(engine, selectEl) {
  if (!selectEl) return;
  try {
    const data = await apiJson(`/api/ollama/models?engine=${encodeURIComponent(engine)}`);
    selectEl.innerHTML = "";
    (data.models || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      selectEl.appendChild(opt);
    });
    if (!selectEl.options.length) {
      const opt = document.createElement("option");
      opt.textContent = "(no aquila models)";
      selectEl.appendChild(opt);
    }
    const settings = await apiJson("/api/runtime/settings");
    if (settings.ollama_model && settings.ollama_engine === engine) {
      selectEl.value = settings.ollama_model;
    }
  } catch (e) {
    selectEl.innerHTML = `<option>${e.message}</option>`;
  }
}

async function useEngineForChat(engine, model) {
  try {
    const data = await apiJson("/api/ollama/active", {
      method: "POST",
      body: JSON.stringify({ engine, model: model || undefined }),
    });
    toast(`Active: ${data.ollama_model} @ ${data.ollama_base_url}`);
  } catch (e) {
    toast(e.message);
  }
}

async function startEngine(engine, stopOther) {
  try {
    const data = await apiJson("/api/server/start", {
      method: "POST",
      body: JSON.stringify({ engine, stop_other: !!stopOther }),
    });
    if (data.needs_confirm) {
      const ok = await confirmDialog(data.message || "Stop the other engine first?");
      if (ok) return startEngine(engine, true);
      return;
    }
    toast(data.message || (data.ok ? "ok" : "failed"));
    if (data.ok) {
      const useOk = await confirmDialog(
        `Use ${engine === "tq" ? "TurboQuant" : "Stock"} for chat and tasks?`
      );
      if (useOk) await useEngineForChat(engine);
    }
  } catch (e) {
    toast(e.message);
  }
  setTimeout(refreshStatus, 1200);
}

async function showLogs(engine) {
  try {
    const data = await apiJson(`/api/server/logs?engine=${encodeURIComponent(engine)}&lines=200`);
    const overlay = el("div", "log-overlay");
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:60;display:flex;align-items:center;justify-content:center;padding:18px;";
    const box = el("div");
    box.style.cssText = "background:var(--bg-elev);border:1px solid var(--border);border-radius:14px;max-width:760px;width:100%;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;";
    const head = el("div", "ws-head");
    head.style.padding = "12px 16px";
    head.appendChild(el("h2", null, `${engine === "tq" ? "TurboQuant" : "Stock"} logs`));
    const close = el("button", "ghost", "Close");
    head.appendChild(close);
    const pre = el("pre", "ledger");
    pre.style.margin = "0 16px 16px";
    pre.textContent = data.text || "(empty)";
    box.appendChild(head);
    box.appendChild(pre);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    const dismiss = () => overlay.remove();
    close.addEventListener("click", dismiss);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) dismiss(); });
  } catch (e) {
    toast(`Logs unavailable: ${e.message}`);
  }
}

function makeBtn(text, cls, onClick) {
  const b = el("button", cls, text);
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await onClick(); } finally { b.disabled = false; }
  });
  return b;
}

async function serverAction(path, body) {
  try {
    const data = await apiJson(path, { method: "POST", body: JSON.stringify(body) });
    toast(data.message || (data.ok ? "ok" : "failed"));
  } catch (e) { toast(e.message); return; }
  setTimeout(refreshStatus, 1200);
}

async function modelAction(path, body) {
  try {
    const data = await apiJson(path, { method: "POST", body: JSON.stringify(body) });
    toast(data.message || (data.ok ? "ok" : "failed"));
  } catch (e) { toast(e.message); return; }
  setTimeout(refreshStatus, 800);
}

/* ---------------- Workspaces (filled by feature modules) ---------------- */

function initCharacter() { state.initialized.character = true; if (window.CharacterWS) window.CharacterWS.init(); }
function initLearn() { state.initialized.learn = true; if (window.LearnWS) window.LearnWS.init(); }
function initResearch() { state.initialized.research = true; if (window.ResearchWS) window.ResearchWS.init(); }

/* ---------------- Boot ---------------- */

async function refreshSearchStatus() {
  try {
    const [settings, status] = await Promise.all([
      apiJson("/api/runtime/settings"),
      apiJson("/api/search/status"),
    ]);
    const urlEl = $("#search-url-label");
    const healthEl = $("#search-health-label");
    if (urlEl) urlEl.textContent = settings.searxng_base_url || "—";
    if (healthEl) {
      const docker = status.docker || {};
      const dockerNote = docker.running ? "container running" : (docker.message || "container stopped");
      healthEl.textContent = `${status.ok ? "Reachable" : "Unreachable"}: ${status.message || ""} | Docker: ${dockerNote}`;
    }
  } catch (e) {
    const healthEl = $("#search-health-label");
    if (healthEl) healthEl.textContent = e.message;
  }
}

async function renderEnvSettings() {
  try {
    const sections = await apiJson("/api/runtime/env_sections");
    const container = $("#env-settings-container");
    if (!container) return;
    container.innerHTML = "";
    sections.forEach(sec => {
      const box = el("div", "engine-card");
      box.style.display = "block"; // override flex
      const title = el("h3", null, sec.title);
      title.style.marginBottom = "1rem";
      box.appendChild(title);
      
      sec.variables.forEach(v => {
        const row = el("div", "env-row");
        row.style.marginBottom = "1rem";
        
        const labelBox = el("div");
        const keyLabel = el("strong", null, v.key);
        keyLabel.style.display = "block";
        const descLabel = el("span", "muted", v.description);
        descLabel.style.fontSize = "0.85em";
        descLabel.style.display = "block";
        labelBox.appendChild(keyLabel);
        if (v.description) labelBox.appendChild(descLabel);
        
        let input;
        if (v.inferred_type === "bool") {
          input = el("input");
          input.type = "checkbox";
          input.checked = v.current_value === "1";
        } else if (v.inferred_type === "int") {
          input = el("input");
          input.type = "number";
          input.value = v.current_value;
          input.style.marginTop = "0.5rem";
        } else {
          input = el("input");
          input.type = "text";
          input.value = v.current_value;
          input.style.width = "100%";
          input.style.marginTop = "0.5rem";
        }
        input.dataset.key = v.key;
        input.dataset.default = v.default_value;
        input.dataset.type = v.inferred_type;
        input.classList.add("env-input");
        
        row.appendChild(labelBox);
        row.appendChild(input);
        box.appendChild(row);
      });
      container.appendChild(box);
    });
  } catch (e) {
    toast(`Failed to load settings: ${e.message}`);
  }
}

async function applyEnvSettings() {
  const inputs = document.querySelectorAll(".env-input");
  const updates = {};
  inputs.forEach(inp => {
    let val = "";
    if (inp.dataset.type === "bool") {
      val = inp.checked ? "1" : "0";
    } else {
      val = inp.value.trim();
    }
    updates[inp.dataset.key] = val;
  });
  
  try {
    const btn = $("#save-env-btn");
    btn.disabled = true;
    await apiJson("/api/runtime/env", {
      method: "POST",
      body: JSON.stringify({ updates })
    });
    toast("Settings applied successfully.");
    setTimeout(refreshStatus, 1000);
  } catch (e) {
    toast(`Failed to apply settings: ${e.message}`);
  } finally {
    $("#save-env-btn").disabled = false;
  }
}

async function enterApp() {
  showAppView();
  await loadInstances();
  refreshStatus();
  refreshSearchStatus();
  renderEnvSettings();
}

function wireEvents() {
  $("#pair-btn").addEventListener("click", doPair);
  $("#logout-btn").addEventListener("click", () => handleLogout("Device unpaired."));
  $("#refresh-status").addEventListener("click", refreshStatus);
  $("#refresh-search")?.addEventListener("click", refreshSearchStatus);
  $("#save-env-btn")?.addEventListener("click", applyEnvSettings);
  $("#search-start-btn")?.addEventListener("click", async () => {
    try {
      const data = await apiJson("/api/search/start", { method: "POST" });
      toast(data.message || "started");
      refreshSearchStatus();
    } catch (e) { toast(e.message); }
  });
  $("#search-stop-btn")?.addEventListener("click", async () => {
    try {
      const data = await apiJson("/api/search/stop", { method: "POST" });
      toast(data.message || "stopped");
      refreshSearchStatus();
    } catch (e) { toast(e.message); }
  });
  $("#search-test-btn")?.addEventListener("click", refreshSearchStatus);
  document.querySelectorAll(".nav-btn").forEach((t) => t.addEventListener("click", () => switchPanel(t.dataset.target)));
  setupMainChat();
}

async function init() {
  wireEvents();
  if (state.token) await enterApp();
  else showPairView();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  }
}

init();
