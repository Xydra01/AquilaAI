"use strict";

// Tasks workspace: launch jobs (Research, Code, Writing, Autonomous), watch ledger/plan, read deliverables.
window.TasksWS = (function () {
  const views = ["tasks-launch-view", "tasks-run-view", "tasks-doc-view", "tasks-explorer-view"];
  function show(id) {
    views.forEach((v) => document.getElementById(v).classList.toggle("hidden", v !== id));
  }
  let attachments = null;

  async function refreshDeliverables() {
    const wrap = $("#tasks-deliverables");
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson("/api/research/deliverables");
      wrap.innerHTML = "";
      if (!data.deliverables || !data.deliverables.length) { wrap.innerHTML = '<p class="muted">No deliverables yet.</p>'; return; }
      data.deliverables.forEach((d) => {
        const card = el("div", "card");
        card.appendChild(el("div", "card-title", d.name));
        const when = d.modified_at ? new Date(d.modified_at * 1000).toLocaleString() : "";
        card.appendChild(el("div", "card-sub", `${Math.round((d.size || 0) / 1024)} KB · ${when}`));
        card.addEventListener("click", () => openDeliverable(d.path));
        wrap.appendChild(card);
      });
    } catch (e) { wrap.innerHTML = `<p class="muted">${e.message}</p>`; }
  }

  async function refreshRepos() {
    const wrap = $("#tasks-repos");
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson("/api/code/repos");
      wrap.innerHTML = "";
      if (!data.repos || !data.repos.length) { wrap.innerHTML = '<p class="muted">No code repositories yet.</p>'; return; }
      data.repos.forEach((r) => {
        const card = el("div", "card");
        card.appendChild(el("div", "card-title", r.name));
        const when = r.modified_at ? new Date(r.modified_at * 1000).toLocaleString() : "";
        card.appendChild(el("div", "card-sub", `Directory · ${when}`));
        card.addEventListener("click", () => openRepoExplorer(r.name));
        wrap.appendChild(card);
      });
    } catch (e) { wrap.innerHTML = `<p class="muted">${e.message}</p>`; }
  }

  function downloadText(name, text) {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function renderDoc(name, text) {
    const v = $("#tasks-doc-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, name || "Deliverable"));
    const dl = el("button", "ghost", "Download");
    dl.addEventListener("click", () => downloadText(name || "deliverable.md", text));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => { show("tasks-launch-view"); refreshDeliverables(); });
    head.appendChild(dl);
    head.appendChild(back);
    v.appendChild(head);
    const body = el("div", "rendered");
    body.innerHTML = AquilaMarkdown.renderSmart(text || "");
    v.appendChild(body);
    show("tasks-doc-view");
  }

  async function openDeliverable(path) {
    try {
      const data = await apiJson(`/api/deliverable?path=${encodeURIComponent(path)}`);
      renderDoc(data.name, data.text);
    } catch (e) { toast(e.message); }
  }

  async function openRepoExplorer(repoName) {
    const v = $("#tasks-explorer-view");
    v.innerHTML = '<div class="ws-head"><h2>Loading...</h2></div>';
    show("tasks-explorer-view");
    try {
      const data = await apiJson(`/api/code/repos/${encodeURIComponent(repoName)}/files`);
      v.innerHTML = "";
      const head = el("div", "ws-head");
      head.appendChild(el("h2", null, repoName));
      const back = el("button", "ghost", "Back");
      back.addEventListener("click", () => show("tasks-launch-view"));
      head.appendChild(back);
      v.appendChild(head);

      const list = el("div", "cards");
      if (!data.files || !data.files.length) {
        list.innerHTML = '<p class="muted">No files found.</p>';
      } else {
        data.files.forEach((f) => {
          const card = el("div", "card");
          card.appendChild(el("div", "card-title", f.rel_path));
          card.appendChild(el("div", "card-sub", `${Math.round((f.size || 0) / 1024)} KB`));
          
          const actions = el("div", "actions");
          actions.style.marginTop = "8px";
          const viewBtn = el("button", "ghost", "View");
          viewBtn.style.padding = "4px 8px";
          viewBtn.style.fontSize = "0.8rem";
          viewBtn.addEventListener("click", (e) => { e.stopPropagation(); openDeliverable(f.abs_path); });
          actions.appendChild(viewBtn);

          card.appendChild(actions);
          list.appendChild(card);
        });
      }
      v.appendChild(list);
    } catch (e) {
      toast(e.message);
      show("tasks-launch-view");
    }
  }

  function launch(evt) {
    evt.preventDefault();
    const prompt = $("#tasks-prompt").value.trim();
    if (!prompt) { toast("Enter a task prompt."); return; }
    const journal = $("#tasks-journal").value.trim();
    const taskName = $("#tasks-task-name").value.trim();
    const mode = $("#tasks-mode").value;
    const fullPrompt = journal ? `${prompt}\n\n[User note]\n${journal}` : prompt;

    const v = $("#tasks-run-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, "Working…"));
    const stopBtn = el("button", "ghost", "Stop");
    head.appendChild(stopBtn);
    v.appendChild(head);
    const runner = el("div", "runner");
    const plan = el("div", "plan-steps");
    const thinkingWrap = el("div", "thinking-wrap");
    let thinkingDetails = null;
    let thinkingBody = null;
    const ledger = el("pre", "ledger", "Starting…");
    runner.appendChild(plan);
    runner.appendChild(thinkingWrap);
    runner.appendChild(ledger);
    v.appendChild(runner);
    show("tasks-run-view");

    const ctrl = runTask({
      instance_id: state.instanceId,
      task_name: taskName || undefined,
      mode: mode,
      prompt: fullPrompt,
      upload_tokens: attachments ? attachments.tokens() : [],
    }, {
      onThinking: (delta) => {
        if (!thinkingDetails) {
          thinkingDetails = el("details", "thinking");
          thinkingDetails.appendChild(el("summary", null, "Thinking"));
          thinkingBody = el("div", "think-body");
          thinkingDetails.appendChild(thinkingBody);
          thinkingWrap.appendChild(thinkingDetails);
          thinkingDetails.open = true;
        }
        thinkingBody.textContent += delta;
        ledger.scrollTop = ledger.scrollHeight;
      },
      onLedger: (t) => { ledger.textContent = t; ledger.scrollTop = ledger.scrollHeight; },
      onPlan: (s) => renderPlanSteps(plan, s),
      onBusy: (m) => { toast(m || "Busy"); show("tasks-launch-view"); },
      onDone: (frame) => {
        if (attachments) attachments.clear();
        if (thinkingDetails) thinkingDetails.open = false;
        if (mode === "code" && frame.message && frame.message.includes("Agent-Code")) {
          // Attempt to auto-open repo explorer if it looks like a repo path
          const match = frame.message.match(/Agent-Code[\\/]([^\s\\]+)/);
          if (match && match[1]) {
            openRepoExplorer(match[1]);
          } else {
            renderDoc("Task deliverable", frame.message || "(no output)");
          }
        } else {
          renderDoc("Task deliverable", frame.message || "(no deliverable text returned)");
        }
        refreshDeliverables();
        refreshRepos();
      },
      onError: (e) => { toast(`Task error: ${e}`); },
    });
    stopBtn.addEventListener("click", () => { ctrl.stop(); toast("Stopping…"); });
  }

  function handleModeChange() {
    const mode = $("#tasks-mode").value;
    const isCode = mode === "code";
    $("#tasks-repos-section").classList.toggle("hidden", !isCode);
    $("#tasks-deliverables-section").classList.toggle("hidden", isCode);
  }

  return {
    init() {
      attachments = createAttachments($("#tasks-attach-chips"));
      const attachBtn = document.querySelector('#tasks-panel .attach-btn');
      if (attachBtn) attachBtn.addEventListener("click", () => attachments.pick());
      $("#tasks-form").addEventListener("submit", launch);
      $("#tasks-refresh").addEventListener("click", refreshDeliverables);
      $("#tasks-repos-refresh").addEventListener("click", refreshRepos);
      $("#tasks-mode").addEventListener("change", handleModeChange);
      
      handleModeChange();
      refreshDeliverables();
      refreshRepos();
    },
  };
})();
