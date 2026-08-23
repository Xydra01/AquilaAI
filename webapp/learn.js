"use strict";

// Learn workspace: Courses (syllabus + tutor + assessments) and Archives.
window.LearnWS = (function () {
  const views = ["learn-list-view", "learn-create-view", "learn-build-view", "learn-detail-view", "learn-chat-view"];
  function show(id) {
    views.forEach((v) => document.getElementById(v).classList.toggle("hidden", v !== id));
  }
  function iidParam() {
    return state.instanceId ? `?instance_id=${encodeURIComponent(state.instanceId)}` : "";
  }
  async function uploadSourcesRaw(url, files) {
    const form = new FormData();
    [...files].forEach((f) => form.append("files", f, f.name));
    return apiJson(url, { method: "POST", body: form });
  }

  /* ---- sub-tabs ---- */
  function switchSubtab(tab) {
    $("#learn-tab-courses").classList.toggle("active", tab === "courses");
    $("#learn-tab-archives").classList.toggle("active", tab === "archives");
    $("#learn-courses").classList.toggle("hidden", tab !== "courses");
    $("#learn-archives").classList.toggle("hidden", tab !== "archives");
    if (tab === "courses") refreshCourses();
    else refreshArchives();
  }

  /* ---- courses list ---- */
  async function refreshCourses() {
    const wrap = $("#course-cards");
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson("/api/learn/courses" + iidParam());
      wrap.innerHTML = "";
      if (!data.courses.length) { wrap.innerHTML = '<p class="muted">No courses yet.</p>'; return; }
      data.courses.forEach((c) => wrap.appendChild(courseCard(c)));
    } catch (e) { wrap.innerHTML = `<p class="muted">${e.message}</p>`; }
  }

  function courseCard(c) {
    const card = el("div", "card");
    card.appendChild(el("div", "card-title", c.title));
    card.appendChild(el("div", "card-sub", c.build_complete ? (c.topic || "Ready") : "⏳ building…"));
    const actions = el("div", "card-actions");
    const open = el("button", "primary", "Open");
    open.addEventListener("click", (e) => { e.stopPropagation(); openCourse(c); });
    const del = el("button", "ghost", "Delete");
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!(await confirmDialog(`Delete course "${c.title}"?`))) return;
      try { await apiJson(`/api/learn/courses/${encodeURIComponent(c.id)}` + iidParam(), { method: "DELETE" }); refreshCourses(); }
      catch (err) { toast(err.message); }
    });
    actions.appendChild(open);
    actions.appendChild(del);
    card.appendChild(actions);
    card.addEventListener("click", () => openCourse(c));
    return card;
  }

  /* ---- course create + syllabus build ---- */
  function renderCourseCreate() {
    const v = $("#learn-create-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, "New course"));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => show("learn-list-view"));
    head.appendChild(back);
    v.appendChild(head);

    const form = el("form", "stacked-form");
    form.innerHTML = `
      <label>Title<input type="text" id="lc-title" placeholder="e.g. Intro to Astrophysics" /></label>
      <label>Topic<input type="text" id="lc-topic" placeholder="defaults to title" /></label>
      <label>Intake
        <select id="lc-intake">
          <option value="files">From files</option>
          <option value="topic_web">From topic + web</option>
          <option value="placement">Placement (infer weak areas)</option>
        </select>
      </label>
      <label class="toggle"><input type="checkbox" id="lc-web" /> <span>Allow web research</span></label>`;
    const chips = el("div", "attach-chips");
    const row = el("div", "composer-row");
    const attachBtn = el("button", "ghost", "Attach source files");
    attachBtn.type = "button";
    const pendingFiles = { list: [] };
    attachBtn.addEventListener("click", async () => {
      const files = await pickFiles();
      if (files && files.length) {
        pendingFiles.list = [...files];
        chips.innerHTML = "";
        pendingFiles.list.forEach((f) => chips.appendChild(el("span", "chip", f.name)));
      }
    });
    const submit = el("button", "primary", "Build syllabus");
    submit.type = "submit";
    row.appendChild(attachBtn);
    row.appendChild(submit);
    form.appendChild(chips);
    form.appendChild(row);
    v.appendChild(form);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = $("#lc-title").value.trim();
      if (!title) { toast("Title required."); return; }
      submit.disabled = true;
      try {
        const wiring = await apiJson("/api/learn/courses", {
          method: "POST",
          body: JSON.stringify({
            instance_id: state.instanceId,
            title: title,
            topic: $("#lc-topic").value.trim(),
            intake: $("#lc-intake").value,
            web: $("#lc-web").checked,
          }),
        });
        if (pendingFiles.list.length) {
          await uploadSourcesRaw(`/api/learn/courses/${encodeURIComponent(wiring.course.id)}/sources` + iidParam(), pendingFiles.list);
        }
        runSyllabusBuild(wiring);
      } catch (err) { toast(err.message); submit.disabled = false; }
    });
    show("learn-create-view");
  }

  function runSyllabusBuild(wiring) {
    const v = $("#learn-build-view");
    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, `Building ${wiring.course.title}`));
    const stopBtn = el("button", "ghost", "Stop");
    head.appendChild(stopBtn);
    v.appendChild(head);
    const runner = el("div", "runner");
    const plan = el("div", "plan-steps");
    const ledger = el("pre", "ledger", "Starting…");
    runner.appendChild(plan);
    runner.appendChild(ledger);
    v.appendChild(runner);
    show("learn-build-view");

    const ctrl = runTask({
      instance_id: state.instanceId,
      task_name: wiring.task_name,
      mode: wiring.mode,
      prompt: wiring.prompt,
      learn_syllabus_web: wiring.learn_syllabus_web,
    }, {
      onLedger: (t) => { ledger.textContent = t; ledger.scrollTop = ledger.scrollHeight; },
      onPlan: (s) => renderPlanSteps(plan, s),
      onBusy: (m) => { toast(m || "Busy"); show("learn-list-view"); },
      onDone: () => { toast("Syllabus built."); refreshCourses(); show("learn-list-view"); },
      onError: (e) => toast(`Build error: ${e}`),
    });
    stopBtn.addEventListener("click", () => { ctrl.stop(); toast("Stopping…"); });
  }

  /* ---- course detail: syllabus tree + tutor + assessments ---- */
  async function openCourse(c) {
    const v = $("#learn-detail-view");
    v.innerHTML = '<p class="muted" style="padding:18px">Loading…</p>';
    show("learn-detail-view");
    let syllabus = null;
    try { syllabus = (await apiJson(`/api/learn/courses/${encodeURIComponent(c.id)}/syllabus` + iidParam())).syllabus; } catch (e) {}

    v.innerHTML = "";
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, c.title));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => show("learn-list-view"));
    head.appendChild(back);
    v.appendChild(head);

    const selected = { node_id: (syllabus && syllabus.current_node_id) || "root" };

    const treeBox = el("div");
    treeBox.appendChild(el("h3", "muted", "Syllabus"));
    const tree = el("div");
    treeBox.appendChild(tree);
    v.appendChild(treeBox);
    renderTree(tree, syllabus, selected);

    const actions = el("div", "composer-row");
    actions.style.marginTop = "12px";
    const tutorBtn = el("button", "primary", "Tutor chat");
    tutorBtn.addEventListener("click", () => openTutorChat(c, selected));
    actions.appendChild(tutorBtn);
    v.appendChild(actions);

    const aHead = el("div", "ws-subhead");
    aHead.appendChild(el("h3", null, "Assessments"));
    v.appendChild(aHead);
    const aWrap = el("div");
    v.appendChild(aWrap);
    loadAssessments(c, aWrap);
  }

  function renderTree(container, syllabus, selected) {
    container.innerHTML = "";
    if (!syllabus || !(syllabus.nodes || []).length) {
      container.appendChild(el("p", "muted", "No syllabus nodes."));
      return;
    }
    const nodes = syllabus.nodes.slice().sort((a, b) => (a.order || 0) - (b.order || 0));
    const byParent = {};
    nodes.forEach((n) => { const p = n.parent_id || "__root"; (byParent[p] = byParent[p] || []).push(n); });
    const ul = el("ul");
    ul.className = "rendered";
    function build(parentKey, host) {
      (byParent[parentKey] || []).forEach((n) => {
        const li = el("li");
        const a = el("button", "ghost", `${n.title} ${"★".repeat(n.mastery_tier || 0)}`);
        a.style.cssText = "padding:4px 8px;font-size:0.85rem;";
        if (n.id === selected.node_id) a.classList.add("primary");
        a.addEventListener("click", () => {
          selected.node_id = n.id;
          container.querySelectorAll("button").forEach((b) => b.className = "ghost");
          a.className = "primary";
        });
        li.appendChild(a);
        const childHost = el("ul");
        li.appendChild(childHost);
        build(n.id, childHost);
        host.appendChild(li);
      });
    }
    build("__root", ul);
    // nodes whose parent is the root id
    if (!byParent["__root"] && nodes.length) build(nodes[0].parent_id || "root", ul);
    container.appendChild(ul);
  }

  async function loadAssessments(c, wrap) {
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson(`/api/learn/courses/${encodeURIComponent(c.id)}/assessments` + iidParam());
      wrap.innerHTML = "";
      if (!data.assessments.length) { wrap.innerHTML = '<p class="muted">No assessments yet (the tutor generates them).</p>'; return; }
      data.assessments.forEach((a) => wrap.appendChild(assessmentCard(c, a, wrap)));
    } catch (e) { wrap.innerHTML = `<p class="muted">${e.message}</p>`; }
  }

  function assessmentCard(c, a, wrap) {
    const card = el("div", "card");
    card.style.cursor = "default";
    card.appendChild(el("div", "card-title", `${a.node_title} (tier ${a.mastery_tier})`));
    const qs = el("ol");
    qs.className = "rendered";
    (a.questions || []).forEach((q) => qs.appendChild(el("li", null, q)));
    card.appendChild(qs);
    const row = el("div", "composer-row");
    const score = el("input");
    score.type = "number";
    score.min = "0"; score.max = "100"; score.value = "70";
    score.style.cssText = "width:90px;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);";
    const submit = el("button", "primary", "Submit score %");
    submit.addEventListener("click", async () => {
      submit.disabled = true;
      try {
        const res = await apiJson(`/api/learn/courses/${encodeURIComponent(c.id)}/assessments/submit`, {
          method: "POST",
          body: JSON.stringify({ instance_id: state.instanceId, node_id: a.node_id, assessment_id: a.assessment_id, score: Number(score.value) }),
        });
        toast(res.message || "Recorded.");
        loadAssessments(c, wrap);
      } catch (e) { toast(e.message); } finally { submit.disabled = false; }
    });
    row.appendChild(score);
    row.appendChild(submit);
    card.appendChild(row);
    return card;
  }

  async function openTutorChat(c, selected) {
    const v = $("#learn-chat-view");
    v.innerHTML = '<p class="muted" style="padding:18px">Loading…</p>';
    show("learn-chat-view");
    let history = [];
    try { history = (await apiJson(`/api/learn/courses/${encodeURIComponent(c.id)}/tutor-history` + iidParam())).history || []; } catch (e) {}
    const header = el("div", "ws-head");
    header.style.padding = "12px 16px 0";
    header.appendChild(el("h2", null, `${c.title} — tutor`));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => openCourse(c));
    header.appendChild(back);
    const extra = { course_id: c.id, node_id: selected.node_id };
    createChat(v, {
      mode: "learn_tutor",
      extra: extra,
      clientHistory: false,
      initialHistory: history,
      placeholder: "Ask the tutor…",
      headerNode: header,
    });
  }

  /* ---- archives ---- */
  async function refreshArchives() {
    const wrap = $("#archive-cards");
    wrap.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await apiJson("/api/learn/archives" + iidParam());
      wrap.innerHTML = "";
      if (!data.archives.length) { wrap.innerHTML = '<p class="muted">No archives yet.</p>'; return; }
      data.archives.forEach((a) => wrap.appendChild(archiveCard(a)));
    } catch (e) { wrap.innerHTML = `<p class="muted">${e.message}</p>`; }
  }

  function archiveCard(a) {
    const card = el("div", "card");
    card.appendChild(el("div", "card-title", a.title));
    card.appendChild(el("div", "card-sub", `${a.source_count} source(s) · ${a.chunk_count} chunks ${a.index_ready ? "· indexed" : ""}`));
    const actions = el("div", "card-actions");
    const open = el("button", "primary", "Open");
    open.addEventListener("click", (e) => { e.stopPropagation(); openArchive(a); });
    const del = el("button", "ghost", "Delete");
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!(await confirmDialog(`Delete archive "${a.title}"?`))) return;
      try { await apiJson(`/api/learn/archives/${encodeURIComponent(a.id)}` + iidParam(), { method: "DELETE" }); refreshArchives(); }
      catch (err) { toast(err.message); }
    });
    actions.appendChild(open);
    actions.appendChild(del);
    card.appendChild(actions);
    card.addEventListener("click", () => openArchive(a));
    return card;
  }

  async function createArchiveFlow() {
    const title = window.prompt("Archive title");
    if (!title || !title.trim()) return;
    try {
      await apiJson("/api/learn/archives", { method: "POST", body: JSON.stringify({ instance_id: state.instanceId, title: title.trim() }) });
      refreshArchives();
    } catch (e) { toast(e.message); }
  }

  async function openArchive(a) {
    const v = $("#learn-detail-view");
    v.innerHTML = "";
    show("learn-detail-view");
    const head = el("div", "ws-head");
    head.appendChild(el("h2", null, a.title));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => show("learn-list-view"));
    head.appendChild(back);
    v.appendChild(head);

    const row = el("div", "composer-row");
    const addBtn = el("button", "ghost", "Add + index sources");
    addBtn.addEventListener("click", async () => {
      const files = await pickFiles();
      if (!files || !files.length) return;
      addBtn.disabled = true;
      try {
        const res = await uploadSourcesRaw(`/api/learn/archives/${encodeURIComponent(a.id)}/sources` + iidParam(), files);
        toast(res.message || "Indexed.");
      } catch (e) { toast(e.message); } finally { addBtn.disabled = false; }
    });
    const chatBtn = el("button", "primary", "Archive chat");
    chatBtn.addEventListener("click", () => openArchiveChat(a));
    row.appendChild(addBtn);
    row.appendChild(chatBtn);
    v.appendChild(row);
    v.appendChild(el("p", "muted", "Upload PDFs/docs, then chat to query them. Ask the archive to draft a study doc or quiz."));
  }

  async function openArchiveChat(a) {
    const v = $("#learn-chat-view");
    v.innerHTML = '<p class="muted" style="padding:18px">Loading…</p>';
    show("learn-chat-view");
    let history = [];
    try { history = (await apiJson(`/api/learn/archives/${encodeURIComponent(a.id)}/history` + iidParam())).history || []; } catch (e) {}
    const header = el("div", "ws-head");
    header.style.padding = "12px 16px 0";
    header.appendChild(el("h2", null, `${a.title} — archive`));
    const back = el("button", "ghost", "Back");
    back.addEventListener("click", () => openArchive(a));
    header.appendChild(back);
    createChat(v, {
      mode: "learn_archive",
      extra: { archive_id: a.id },
      clientHistory: false,
      initialHistory: history,
      placeholder: "Query this archive…",
      headerNode: header,
    });
  }

  return {
    init() {
      $("#learn-tab-courses").addEventListener("click", () => switchSubtab("courses"));
      $("#learn-tab-archives").addEventListener("click", () => switchSubtab("archives"));
      $("#course-new-btn").addEventListener("click", renderCourseCreate);
      $("#archive-new-btn").addEventListener("click", createArchiveFlow);
      refreshCourses();
    },
  };
})();
