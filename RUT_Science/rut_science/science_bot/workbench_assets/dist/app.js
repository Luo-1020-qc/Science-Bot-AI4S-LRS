"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const labels = { overview: "研究概览", chat: "对话规划", plan: "研究计划", evidence: "证据材料", delivery: "交付中心" };
  const purpose = { comparison: "比较研究", prediction: "预测评估", causal: "因果研究", exploration: "探索研究", replication: "复现研究" };
  const hash = new URLSearchParams(location.hash.slice(1));
  // This is the existing local service capability, never the model API key.
  // It is kept only in memory and removed from the address bar immediately.
  let token = hash.get("access") || "";
  let sessionId = hash.get("session") || "";
  if (location.hash) history.replaceState(null, "", location.href.split("#")[0]);
  let view = null, busy = false, currentTab = "overview", toastTimer = null;
  let displayedSession = "";
  let displayedChoiceId = "";
  const el = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = String(text); if (className) n.className = className; return n; };
  const clear = (id) => $(id).replaceChildren();
  const fact = (name) => view?.planning?.facts.find((r) => r.field === name)?.value || "尚待明确";

  function toast(message, error = false) {
    clearTimeout(toastTimer); $("toast").textContent = message; $("toast").className = "toast" + (error ? " error" : "");
    $("toast").hidden = false; toastTimer = setTimeout(() => { $("toast").hidden = true; }, 6500);
  }
  function requireConnection() {
    if (token) return true;
    toast("当前是只读合成预览。运行 science-bot-web.cmd -Example 打开可交互的本地会话。", true);
    return false;
  }
  function switchTab(name) {
    if (!labels[name]) return;
    currentTab = name; $("crumb").textContent = labels[name];
    document.querySelectorAll("[data-panel]").forEach((n) => { n.hidden = n.dataset.panel !== name; });
    document.querySelectorAll("[data-tab]").forEach((n) => { n.classList.toggle("active", n.dataset.tab === name); n.setAttribute("aria-current", n.dataset.tab === name ? "page" : "false"); });
  }
  function setBusy(value) {
    busy = value;
    $("sendButton").disabled = value;
    $("sendButton").textContent = value ? "正在整理…" : "发送 →";
    $("exportTop").disabled = value; $("exportDelivery").disabled = value;
    $("newSession").disabled = value; $("reviewPlan").disabled = value;
    $("approvePlan").disabled = value || !view?.planning?.ready || !!view?.planning?.approved;
    $("saveState").textContent = value ? "正在处理，请勿重复提交" : token ? "已读取本地会话" : "本地界面示例";
    document.querySelectorAll(".current-choice button").forEach((button) => { button.disabled = value; });
    document.querySelectorAll(".session-row button").forEach((button) => { button.disabled = value || button.dataset.unavailable === "true"; });
  }
  async function request(path, body, key = null) {
    const headers = { "Authorization": "Bearer " + token };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["Idempotency-Key"] = key || crypto.randomUUID();
    }
    let response;
    try { response = await fetch(path, { method: body === undefined ? "GET" : "POST", headers, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store" }); }
    catch (_) { throw new Error("本地服务暂时不可达。请求完成状态不明，请先刷新会话，不要重复提交。"); }
    const data = await response.json();
    if (!response.ok) throw new Error(response.status === 401 ? "本地访问凭据不可用，请重新运行浏览器启动器。" : (data.detail || data.error || "本次操作未完成"));
    return data;
  }
  function message(text, role = "assistant") {
    const item = el("div", undefined, "message " + role);
    item.append(el("span", role === "user" ? "你" : "SCIENCE BOT", "speaker"), document.createTextNode(text));
    $("messages").append(item); $("messages").scrollTop = $("messages").scrollHeight;
  }
  function renderQuestions(plan) {
    clear("questions");
    if (!plan?.questions?.length) {
      $("nextTitle").textContent = plan?.ready ? "现在可以复核当前版本" : plan ? "等待依据或修订边界" : "从一个研究问题开始";
      $("questions").append(el("p", plan?.ready ? "核对目标、设计与验收，再决定是否确认这份规划。" : plan ? "草案仍有未决项，请在研究计划中核对缺口及获取依据的步骤。" : "描述想回答的问题，也可以先说清你还不知道什么。", "subtle"));
      return;
    }
    $("nextTitle").textContent = "先解决关键缺口";
    plan.questions.forEach((q, i) => {
      const row = el("div", undefined, "question-item");
      row.append(el("p", String(i + 1).padStart(2, "0") + "  " + q.question));
      if (q.kind === "proposal" && q.allow_accept !== false) {
        const button = el("button", "确认这项理解 →", "text-button");
        button.addEventListener("click", () => send("/plan accept " + q.field)); row.append(button);
      }
      (q.options || []).forEach((option, index) => {
        const button = el("button", (index + 1) + ". " + option.label, "quick-action");
        button.addEventListener("click", () => send(q.choice_id ? "/plan choose " + q.choice_id + " " + option.id : (q.kind === "conflict" ? "/plan revise " : "/plan ") + q.field + ": " + option.value, option.label)); row.append(button);
      });
      $("questions").append(row);
    });
  }
  function renderChatChoices(plan) {
    const q = plan?.questions?.[0];
    if (q?.choice_id && displayedChoiceId === q.choice_id) return;
    document.querySelectorAll(".choice-message").forEach((node) => {
      node.classList.remove("current-choice");
      node.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    });
    displayedChoiceId = q?.choice_id || "";
    if (!q?.choice_id) return;
    const card = el("div", undefined, "message choice-message current-choice");
    card.setAttribute("role", "group"); card.setAttribute("aria-label", q.question);
    card.append(el("span", "SCIENCE BOT", "speaker"), el("p", q.question));
    q.options.forEach((option, index) => {
      const button = el("button", (index + 1) + ". " + option.label, "quick-action");
      button.disabled = busy;
      button.addEventListener("click", () => send("/plan choose " + q.choice_id + " " + option.id, option.label));
      card.append(button);
    });
    $("messages").append(card); $("messages").scrollTop = $("messages").scrollHeight;
  }
  function renderPlan(plan) {
    clear("pathPreview"); clear("planSteps"); clear("planIssues");
    renderDesign("designReadout", plan);
    (plan?.steps || []).forEach((step, i) => {
      if (i < 6) {
        const item = el("div", undefined, "path-item"), copy = el("div");
        copy.append(el("b", step.label), el("small", step.capability_label));
        item.append(el("span", String(i + 1).padStart(2, "0"), "path-number"), copy); $("pathPreview").append(item);
      }
      const card = el("article", undefined, "card step-card"), title = el("div", undefined, "step-title");
      title.append(el("span", String(i + 1).padStart(2, "0")), el("h3", step.label));
      card.append(title, el("p", step.purpose), el("p", "验收：" + step.acceptance, "acceptance"), el("small", step.owner + " · " + step.capability_label + " · 尚未执行"));
      $("planSteps").append(card);
    });
    (plan?.issues || []).forEach((issue) => $("planIssues").append(el("div", issue.label + "：" + issue.detail, "issue")));
    $("approvalHint").textContent = plan?.approved ? "当前内容版本已确认。任何关键修订都需要重新复核。" : plan?.ready ? "请先逐项检查目标、步骤与验收。确认规划不会启动实验。" : "先处理待确认、未知与冲突，再复核版本。";
    $("hashText").textContent = plan?.hash || "尚未建立规划";
    $("approvePlan").textContent = plan?.approved ? "此版本已确认" : "确认此版本";
  }
  function renderEvidence(plan) {
    clear("sourceList");
    const sources = plan?.evidence || [];
    $("evidenceCount").textContent = sources.length + " 个片段";
    $("sourceSummary").textContent = sources.length ? "已有 " + sources.length + " 个明确选择的片段" : "还没有选择论文证据";
    $("workspaceText").textContent = view.workspace ? "当前工作区：" + view.workspace : "尚未绑定工作区。启动时使用 -Workspace 选择项目目录。";
    if (!sources.length) {
      const box = el("div", undefined, "card empty-card");
      box.append(el("span", "⌑"), el("h3", "从明确选择的一段原文开始"), el("p", "出处与版本会随计划保存。", "subtle")); $("sourceList").append(box);
    }
    sources.forEach((source) => {
      const card = el("article", undefined, "card source-entry");
      const range = source.format === "pdf" ? "PDF第 " + source.start_page + "–" + source.end_page + " 页" : "第 " + source.start_line + "–" + source.end_line + " 行";
      card.append(el("h3", source.path), el("small", range + " · " + source.sha256), el("span", source.share_with_model ? "已允许模型使用所选内容" : "仅本地展示", "tag"));
      const button = el("button", "查看选定时的原文 →", "quick-action");
      button.addEventListener("click", () => send("/plan evidence show " + source.id)); card.append(button);
      if (source.format === "pdf") {
        const understand = el("button", source.interpretation ? "查看已保存的论文解读 →" : "让LLM理解所选页 →", "quick-action");
        understand.disabled = !source.share_with_model;
        understand.title = source.share_with_model ? "使用现有模型理解这些页，保留逐页原文引用" : "请重新选择片段并明确允许模型使用";
        understand.addEventListener("click", () => send("/plan evidence understand " + source.id)); card.append(understand);
        if (source.interpretation) {
          const reading = source.interpretation;
          card.append(el("h3", "模型解读 · 待复核"));
          reading.items.forEach((item) => card.append(el("p", item.statement), el("small", "PDF第 " + item.page + " 页 · 原文：" + item.quote)));
          reading.unanswered.forEach((item) => card.append(el("p", "尚不能判断：" + item, "subtle")));
          if (reading.rejected_items?.length) card.append(el("p", "有 " + reading.rejected_items.length + " 条模型要点未通过引用或数值校验，未采用。", "subtle"));
        }
      }
      $("sourceList").append(card);
    });
  }
  function renderDelivery(plan) {
    if (!$('deliveryReadout')) {
      const container = el('div', undefined, 'step-grid'); container.id = 'deliveryReadout';
      container.setAttribute('aria-label', '交付前的实验设计');
      document.querySelector('[data-panel="delivery"] .format-grid').before(container);
    }
    renderDesign('deliveryReadout', plan);
    const exported = plan?.export;
    $("exportState").textContent = exported ? (plan.export_current ? "当前版本已导出" : "现有导出属于旧内容版本，请重新导出") + " · " + exported.contract_hash.slice(0, 16) : "尚未生成导出版本";
    document.querySelectorAll("[data-download]").forEach((button) => { button.disabled = !token || !exported || busy; });
  }
  function renderDesign(target, plan) {
    clear(target);
    const design = plan?.design_readout;
    if (!design) { $(target).append(el('p', '描述目标后，这里将直接展示实验设计草案。', 'subtle')); return; }
    const status = { proposed: '待确认', unknown: '未知', conflict: '冲突', stale: '需重新核对', missing: '待明确' };
    design.sections.forEach((section) => {
      const card = el('article', undefined, 'card compact'); card.append(el('h3', section.title));
      section.items.forEach((item) => {
        card.append(el('div', item.label + (status[item.status] ? ' · ' + status[item.status] : ''), 'definition-label'), el('p', item.value));
      });
      $(target).append(card);
    });
    if (design.evidence_actions.length) {
      const card = el('article', undefined, 'card compact'); card.append(el('h3', '获取依据的拟议步骤 · 未执行'));
      design.evidence_actions.forEach((item) => card.append(el('p', item.label + '：' + item.text))); $(target).append(card);
    }
    $(target).append(el('p', design.next_step, 'subtle'));
  }
  function render(data) {
    view = data;
    const plan = data.planning;
    $("projectTitle").textContent = plan?.title || "让研究的每一步，都有依据。";
    $("pageSubtitle").textContent = plan ? "保持目标、边界与未知可见。每个决定，都能回到它的依据。" : "从问题出发，明确边界与取舍，形成可以共同复核的计划。";
    $("modePill").textContent = data.example ? "离线 · 合成示例" : data.backend === "offline" ? "离线模式" : "API模式";
    $("previewNotice").hidden = !!token && !data.example;
    $("previewNotice").lastElementChild.textContent = !token ? "合成界面预览 · 未连接私有会话，未执行实验。运行浏览器启动器可进入可交互示例。" : "合成离线示例 · 不调用模型、不读取真实论文，不执行实验。所有约束仅用于演示。";
    $("researchQuestion").textContent = fact("research_question");
    $("objective").textContent = purpose[fact("objective_type")] || fact("objective_type");
    $("revision").textContent = plan ? "第 " + plan.revision + " 版" : "—";
    $("planStatus").textContent = plan?.status || "尚未开始";
    $("scopeText").textContent = fact("scope"); $("exclusionsText").textContent = fact("exclusions");
    $("unitText").textContent = fact("experimental_unit"); $("outcomeText").textContent = fact("outcomes"); $("resourceText").textContent = fact("resources");
    const resources = data.resources;
    $("requestCount").textContent = resources.llm_requests + " / " + resources.limits.llm_requests;
    $("toolCount").textContent = resources.tool_attempts + " / " + resources.limits.tool_calls;
    document.querySelectorAll(".stage").forEach((node, i) => node.classList.toggle("active", !!plan && (i === 0 || i === 1 && plan.facts.length > 5 || i === 2 && plan.ready || i === 3 && plan.export_current)));
    renderQuestions(plan); renderPlan(plan); renderEvidence(plan); renderDelivery(plan); setBusy(busy);
    if (displayedSession !== data.id) {
      clear("messages"); displayedSession = data.id; displayedChoiceId = "";
      message(data.last_answer || "你好。我们可以先明确要回答的问题，也可以从右侧的待澄清项继续。规划确认与实际执行分开。" + (data.example ? "\n\n这是合成离线示例，当前命题待确认，先导依据仍未知。" : ""));
    }
    renderChatChoices(plan);
  }
  async function refresh() {
    if (token && sessionId) render(await request("/ui/sessions/" + sessionId));
    else if (token) render({ id: "", backend: view?.backend || "offline", model: view?.model || "", phase: "ready",
      workspace: view?.workspace || null, resources: { llm_requests: 0, tool_attempts: 0, limits: { llm_requests: 12, tool_calls: 40 } },
      planning: null, last_answer: "尚无研究会话。点击“新建研究”开始。", example: false });
    else render(globalThis.__SCIENCE_BOT_DEMO__ || await (await fetch("/demo.json", { cache: "no-store" })).json());
  }
  async function listSessions() {
    if (!token) return;
    const result = await request("/ui/sessions"); clear("sessionList");
    result.sessions.forEach((session) => {
      const row = el("div", undefined, "session-row");
      const button = el("button", (session.example ? "示例 · " : "") + session.title, "session-open");
      button.title = session.title;
      button.setAttribute("aria-current", session.id === sessionId ? "true" : "false");
      button.dataset.unavailable = String(!!session.deletion_pending);
      button.disabled = busy || !!session.deletion_pending;
      button.addEventListener("click", async () => { if (busy) return; setBusy(true); sessionId = session.id; try { await refresh(); switchTab("overview"); } catch (error) { toast(error.message, true); } finally { setBusy(false); } });
      const remove = el("button", "删除", "session-delete"); remove.type = "button"; remove.disabled = busy;
      remove.title = "删除此研究及对话记录"; remove.setAttribute("aria-label", "删除研究：" + session.title);
      remove.addEventListener("click", () => deleteSession(session));
      row.append(button, remove); $("sessionList").append(row);
    });
    if (!result.sessions.length) $("sessionList").append(el("span", "尚无研究会话", "muted"));
    return result.sessions;
  }
  async function deleteSession(session) {
    if (busy || !requireConnection()) return;
    if (!window.confirm("删除研究“" + session.title + "”？\n\n将清除该会话的研究计划、对话、导出和本地缓存，无法撤销。原始项目文件保留。")) return;
    setBusy(true);
    try {
      await request("/ui/sessions/" + session.id + "/delete", { confirm: session.id });
      if (sessionId === session.id) {
        sessionId = ""; displayedSession = null; displayedChoiceId = ""; clear("messages");
        $("messageText").value = ""; await refresh();
        const remaining = await listSessions();
        const next = remaining.find((item) => !item.deletion_pending);
        if (next) { sessionId = next.id; await refresh(); await listSessions(); }
        switchTab("overview");
      } else await listSessions();
      toast("已删除该研究及对话记录。");
    } catch (error) { toast(error.message + " 请刷新历史列表核对状态。", true); }
    finally { setBusy(false); }
  }
  async function send(text, displayText = text) {
    if (busy || !text.trim() || !requireConnection()) return;
    if (!sessionId) { toast("请先新建研究会话。", true); return; }
    setBusy(true); message(displayText, "user"); switchTab("chat");
    try {
      const result = await request("/v1/sessions/" + sessionId + "/messages", { text: text.trim() });
      if (!result.question_form) message(result.answer || "已保存，请查看研究概览。");
      if (result.planning_error || result.research_error) toast("操作未采纳，请根据回答修正。", true);
      await refresh(); await listSessions();
      if (result.export) { switchTab("delivery"); toast("已导出当前版本，可下载三种交付格式。"); }
    } catch (error) { message(error.message); toast(error.message, true); }
    finally { setBusy(false); renderDelivery(view?.planning); }
  }
  async function newSession(example) {
    if (!requireConnection() || busy) return;
    setBusy(true);
    try {
      const result = await request(example ? "/ui/example" : "/v1/sessions", example ? {} : { backend: $("backendMode").value });
      sessionId = result.id; $("newDialog").close(); await refresh(); await listSessions(); switchTab("overview");
      toast(example ? "已创建独立离线示例，没有模型或实验调用。" : "研究会话已建立，可以描述你的目标。");
    } catch (error) { toast(error.message, true); }
    finally { setBusy(false); }
  }
  async function download(suffix) {
    if (!requireConnection() || !sessionId || !view?.planning?.export) return;
    try {
      const response = await fetch("/ui/sessions/" + sessionId + "/delivery." + suffix, { headers: { Authorization: "Bearer " + token }, cache: "no-store" });
      if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "交付文件不可用，请重新导出。"); }
      const blob = await response.blob(), url = URL.createObjectURL(blob), link = el("a");
      link.href = url; link.download = "science-bot-plan." + suffix; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast("交付文件已下载，版本与缺口记录随文件保留。");
    } catch (error) { toast(error.message, true); }
  }
  document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.go)));
  document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => send(button.dataset.command)));
  document.querySelectorAll("[data-download]").forEach((button) => button.addEventListener("click", () => download(button.dataset.download)));
  $("newSession").addEventListener("click", () => { if (requireConnection()) $("newDialog").showModal(); });
  $("closeDialog").addEventListener("click", () => $("newDialog").close());
  $("newForm").addEventListener("submit", (event) => { event.preventDefault(); newSession(false); });
  $("loadExample").addEventListener("click", () => newSession(true));
  $("refreshSessions").addEventListener("click", async () => { try { await listSessions(); await refresh(); } catch (error) { toast(error.message, true); } });
  $("exportTop").addEventListener("click", () => { if (token) send("/plan export"); else { switchTab("delivery"); toast("当前是只读预览，下方可查看合成交付示例。"); } });
  $("exportDelivery").addEventListener("click", () => { if (token) send("/plan export"); else window.open(globalThis.__SCIENCE_BOT_DEMO__ ? "delivery.html" : "/demo-delivery.html", "_blank", "noopener"); });
  $("reviewPlan").addEventListener("click", () => send("/plan review"));
  $("approvePlan").addEventListener("click", () => { if (view?.planning?.ready) send("/plan approve " + view.planning.hash); });
  $("pilotExample").addEventListener("click", () => {
    if (!view?.example) { toast("此快捷回答仅用于合成示例，真实研究请提供自己的依据。", true); return; }
    $("messageText").value = "/plan sampling: 固定预算先导；先核实独立性与测量流程，不宣称功效保证。"; $("messageText").focus();
  });
  $("messageForm").addEventListener("submit", (event) => { event.preventDefault(); const text = $("messageText").value; if (text.trim() && !busy && token && sessionId) $("messageText").value = ""; send(text); });
  $("messageText").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("messageForm").requestSubmit(); } });
  $("evidenceForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const start = Number($("startLine").value), end = Number($("endLine").value);
    const pdf = /\.pdf$/i.test($("sourcePath").value.trim());
    if (start < 1 || end < start || end - start + 1 > (pdf ? 12 : 120)) { toast(pdf ? "请选择最多12个连续PDF页。" : "请选择最多120行的连续片段。", true); return; }
    const range = pdf ? {start_page:start,end_page:end} : {start_line:start,end_line:end};
    send("/plan evidence add " + JSON.stringify({ path: $("sourcePath").value.trim(), ...range, share_with_model: $("shareSource").checked }));
  });
  $("sourcePath").addEventListener("input", () => {
    const pdf = /\.pdf$/i.test($("sourcePath").value.trim());
    $("startRangeLabel").textContent = pdf ? "起始PDF页" : "起始行";
    $("endRangeLabel").textContent = pdf ? "结束PDF页" : "结束行";
    if (pdf && Number($("endLine").value) > 12) $("endLine").value = "3";
  });
  async function init() {
    try {
      if (token && !sessionId) { const data = await request("/ui/sessions"); if (data.sessions.length) sessionId = data.sessions[0].id; }
      await refresh(); await listSessions();
    } catch (error) { token = ""; sessionId = ""; await refresh(); toast(error.message, true); }
  }
  init();
})();
