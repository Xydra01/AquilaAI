"use strict";

// Character workspace: persona cards, create + build-watch, persona chat.
window.CharacterWS = (function () {
  const views = ["character-list-view", "character-create-view", "character-build-view", "character-chat-view"];
  function show(id) {
    views.forEach((v) => document.getElementById(v).classList.toggle("hidden", v !== id));
  }
  function iidParam() {
    return state.instanceId ? `?instance_id=${encodeURIComponent(state.instanceId)}` : "";
  }

  async function refreshList() {
    const wrap = $("#persona-cards");
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson("/api/character/personas" + iidParam());
      wrap.innerHTML = "";
      if (!data.personas.length) {
        wrap.innerHTML = '<p class="muted">No personas yet. Create one to start.</p>';
        return;
      }
      data.personas.forEach((p) => wrap.appendChild(personaCard(p)));
    } catch (e) {
      wrap.innerHTML = `<p class="muted">Could not load: ${e.message}</p>`;
    }
  }

  function personaCard(p) {
    const card = el("div", "card");
    card.appendChild(el("div", "card-title", p.display_name));
    card.appendChild(el("div", "card-sub", p.build_complete ? (p.tagline || p.description || "Ready") : "⏳ building…"));
    const actions = el("div", "card-actions");
    const open = el("button", "primary", "Chat");
    open.addEventListener("click", (e) => { e.stopPropagation(); openChat(p); });
    const del = el("button", "ghost", "Delete");
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!(await confirmDialog(`Delete persona "${p.display_name}"?`))) return;
      try { await apiJson(`/api/character/personas/${encodeURIComponent(p.id)}` + iidParam(), { method: "DELETE" }); refreshList(); }
      catch (err) { toast(err.message); }
    });
    actions.appendChild(open);
    actions.appendChild(del);
    card.appendChild(actions);
    card.addEventListener("click", () => { if (p.build_complete) openChat(p); });
    return card;
  }

  /* ---- create + build ---- */
  function renderCreate() {
    const v = $("#character-create-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, "New persona"));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => show("character-list-view"));
    head.appendChild(back);
    v.appendChild(head);

    const form = el("form", "stacked-form");
    form.innerHTML = `
      <label>Display name<input type="text" id="cc-name" placeholder="e.g. Captain Vega" /></label>
      <label>Description<textarea id="cc-desc" rows="4" placeholder="Personality, backstory, voice…"></textarea></label>
      <label class="toggle"><input type="checkbox" id="cc-lore" /> <span>Use web research for lore</span></label>`;
    const chips = el("div", "attach-chips");
    const attachments = createAttachments(chips);
    const row = el("div", "composer-row");
    const attachBtn = el("button", "ghost", "Attach sources");
    attachBtn.type = "button";
    attachBtn.addEventListener("click", () => attachments.pick());
    const submit = el("button", "primary", "Build persona");
    submit.type = "submit";
    row.appendChild(attachBtn);
    row.appendChild(submit);
    form.appendChild(chips);
    form.appendChild(row);
    v.appendChild(form);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = $("#cc-name").value.trim();
      const desc = $("#cc-desc").value.trim();
      if (!name || !desc) { toast("Name and description required."); return; }
      submit.disabled = true;
      try {
        const wiring = await apiJson("/api/character/personas", {
          method: "POST",
          body: JSON.stringify({
            instance_id: state.instanceId,
            display_name: name,
            description: desc,
            research_lore: $("#cc-lore").checked,
          }),
        });
        runBuild(wiring, attachments.tokens());
      } catch (err) {
        toast(err.message);
        submit.disabled = false;
      }
    });
    show("character-create-view");
  }

  function runBuild(wiring, uploadTokens) {
    const v = $("#character-build-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, `Building ${wiring.persona.display_name}`));
    const stopBtn = el("button", "ghost", "Stop");
    head.appendChild(stopBtn);
    v.appendChild(head);
    const runner = el("div", "runner");
    const plan = el("div", "plan-steps");
    const ledger = el("pre", "ledger", "Starting…");
    runner.appendChild(plan);
    runner.appendChild(ledger);
    v.appendChild(runner);
    show("character-build-view");

    const ctrl = runTask({
      instance_id: state.instanceId,
      task_name: wiring.task_name,
      mode: wiring.mode,
      prompt: wiring.prompt,
      persona_research_lore: wiring.persona_research_lore,
      upload_tokens: uploadTokens,
    }, {
      onLedger: (t) => { ledger.textContent = t; ledger.scrollTop = ledger.scrollHeight; },
      onPlan: (s) => renderPlanSteps(plan, s),
      onBusy: (m) => { toast(m || "Busy"); show("character-list-view"); },
      onDone: () => { toast("Persona built."); refreshList(); show("character-list-view"); },
      onError: (e) => { toast(`Build error: ${e}`); },
    });
    stopBtn.addEventListener("click", () => { ctrl.stop(); toast("Stopping…"); });
  }

  /* ---- chat ---- */
  async function openChat(p) {
    const v = $("#character-chat-view");
    v.innerHTML = '<p class="muted" style="padding:18px">Loading…</p>';
    show("character-chat-view");
    let history = [];
    try {
      const data = await apiJson(`/api/character/personas/${encodeURIComponent(p.id)}/history` + iidParam());
      history = data.history || [];
    } catch (e) {}

    const header = el("div", "ws-head");
    header.style.padding = "12px 16px 0";
    header.appendChild(el("h2", null, p.display_name));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => { show("character-list-view"); refreshList(); });
    header.appendChild(back);

    createChat(v, {
      mode: "character",
      extra: { persona_id: p.id },
      clientHistory: false,
      initialHistory: history,
      placeholder: `Message ${p.display_name}…`,
      headerNode: header,
    });
  }

  return {
    init() {
      $("#persona-new-btn").addEventListener("click", renderCreate);
      refreshList();
    },
  };
})();
