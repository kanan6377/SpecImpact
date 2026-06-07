const state = { csrf: null, projectId: null, projects: [], cy: null };
const page = document.body.dataset.page;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function toast(message) {
  const box = $("#toast");
  const text = typeof message === "string" ? message : JSON.stringify(message, null, 2);
  box.textContent = text;
  $("#page-status").textContent = text;
  box.classList.add("show");
  setTimeout(() => {
    box.classList.remove("show");
    $("#page-status").textContent = "";
  }, 5000);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = state.csrf;
    headers.Origin = location.origin;
  }
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  }
  return data;
}

function withProject(path = "") {
  if (!state.projectId) throw new Error("案件を選択してください。");
  return `/api/projects/${state.projectId}${path}`;
}

async function boot() {
  state.csrf = (await api("/api/session")).csrf_token;
  await loadProjects();
  $$("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === page));
  $$(".page").forEach((view) => view.classList.toggle("active", view.dataset.view === page));
  bind();
  await refresh();
}

async function loadProjects() {
  state.projects = (await api("/api/projects")).projects;
  const select = $("#project-select");
  select.innerHTML =
    '<option value="">案件を選択</option>' +
    state.projects
      .map(
        (project) =>
          `<option value="${escapeHtml(project.project_id)}">${escapeHtml(project.display_name)}</option>`,
      )
      .join("");
  const query = new URLSearchParams(location.search).get("project_id");
  const remembered = localStorage.getItem("specimpact.project_id");
  state.projectId = state.projects.some((project) => project.project_id === (query || remembered))
    ? query || remembered
    : state.projects[0]?.project_id || null;
  select.value = state.projectId || "";
  syncProject();
}

function syncProject() {
  if (!state.projectId) return;
  localStorage.setItem("specimpact.project_id", state.projectId);
  const url = new URL(location.href);
  url.searchParams.set("project_id", state.projectId);
  history.replaceState({}, "", url);
}

function bind() {
  $("#project-select").addEventListener("change", async (event) => {
    state.projectId = event.target.value || null;
    syncProject();
    await refresh();
  });
  $("#open-project-dialog").onclick = () => $("#project-dialog").showModal();
  $("#remove-project").onclick = () => $("#remove-project-dialog").showModal();
  $("#cancel-remove-project").onclick = () => $("#remove-project-dialog").close();
  $("#confirm-remove-project").onclick = removeProject;
  $("#save-project").onclick = async (event) => {
    event.preventDefault();
    const form = $("#project-dialog form");
    const values = Object.fromEntries(new FormData(form));
    values.create = form.elements.create.checked;
    try {
      const result = await api("/api/projects", { method: "POST", body: JSON.stringify(values) });
      $("#project-dialog").close();
      await loadProjects();
      state.projectId = result.project.project_id;
      syncProject();
      await refresh();
    } catch (error) {
      toast(error.message);
    }
  };
  $$("[data-action]").forEach((button) => {
    button.onclick = () => enqueue(button.dataset.action, {});
  });
  $$("form[data-job]").forEach((form) => {
    form.onsubmit = (event) => {
      event.preventDefault();
      enqueue(form.getAttribute("data-job"), formValues(form));
    };
  });
  $$("[data-tool]").forEach((button) => {
    button.onclick = () => runTool(button.dataset.tool, {});
  });
  $$("form[data-tool-form]").forEach((form) => {
    form.onsubmit = (event) => {
      event.preventDefault();
      runTool(form.getAttribute("data-tool-form"), formValues(form));
    };
  });
  $("#create-demo")?.addEventListener("click", createDemo);
  $("#upload-form")?.addEventListener("submit", uploadFiles);
  $("#refresh-graph")?.addEventListener("click", loadGraph);
  $("#graph-fit")?.addEventListener("click", fitGraph);
  $("#graph-reset")?.addEventListener("click", resetGraph);
  $("#graph-search")?.addEventListener("input", filterGraphSearch);
  $$(".download").forEach((link) => {
    link.onclick = () => {
      link.href = withProject(`/download/${link.dataset.format}`);
    };
  });
}

async function removeProject() {
  if (!state.projectId) {
    $("#remove-project-dialog").close();
    toast("案件を選択してください。");
    return;
  }
  try {
    await api(`/api/projects/${state.projectId}`, { method: "DELETE", body: "{}" });
    $("#remove-project-dialog").close();
    state.projectId = null;
    await loadProjects();
    await refresh();
    toast("案件の登録を解除しました。");
  } catch (error) {
    toast(error.message);
  }
}

async function runTool(tool, params) {
  try {
    $("#tool-result").textContent = (
      await api(withProject("/tool"), { method: "POST", body: JSON.stringify({ tool, params }) })
    ).result;
  } catch (error) {
    toast(error.message);
  }
}

function formValues(form) {
  const data = Object.fromEntries(new FormData(form));
  $$("input[type=checkbox]", form).forEach((input) => {
    data[input.name] = input.checked;
  });
  Object.keys(data).forEach((key) => {
    if (data[key] === "") delete data[key];
  });
  return data;
}

async function enqueue(action, params) {
  try {
    if (!state.projectId) throw new Error("案件を選択してください。");
    const query = new URLSearchParams({
      action,
      params: JSON.stringify(params),
    });
    let preview;
    try {
      preview = await api(withProject(`/external-preview?${query.toString()}`));
    } catch (error) {
      throw new Error(
        `External preview failed: action=${action}, params=${safeParams(params)}, error=${error.message}`,
      );
    }
    const approved = preview.required ? await confirmExternal(preview.transmissions) : false;
    if (preview.required && !approved) {
      toast("外部送信をキャンセルしました。Job は実行していません。");
      return;
    }
    const result = await api(withProject("/jobs"), {
      method: "POST",
      body: JSON.stringify({ action, params, external_approved: approved, input_kind: "path" }),
    });
    toast(`Job queued: ${result.job.action}`);
    setTimeout(refresh, 450);
  } catch (error) {
    toast(error.message);
  }
}

function safeParams(params) {
  const redacted = {};
  Object.entries(params || {}).forEach(([key, value]) => {
    redacted[key] = /key|token|secret|password/i.test(key) ? "[redacted]" : value;
  });
  return JSON.stringify(redacted);
}

function confirmExternal(rows) {
  return new Promise((resolve) => {
    const dialog = $("#external-dialog");
    $("#external-details").innerHTML = rows
      .map(
        (row) =>
          `<div class="consent-row"><strong>${escapeHtml(row.provider)} / ${escapeHtml(
            row.model || "(model未指定)",
          )}</strong><p>${escapeHtml(row.purpose)} <span class="count-chip">送信対象 ${escapeHtml(
            row.item_count_label ?? row.item_count,
          )}</span></p>${row.note ? `<p class="field-help">${escapeHtml(row.note)}</p>` : ""}</div>`,
      )
      .join("");
    $("#external-cancel").onclick = () => {
      dialog.close();
      resolve(false);
    };
    $("#external-approve").onclick = () => {
      dialog.close();
      resolve(true);
    };
    dialog.showModal();
  });
}

async function createDemo() {
  try {
    const result = await api("/api/demo", { method: "POST", body: "{}" });
    await loadProjects();
    state.projectId = result.project.project_id;
    syncProject();
    $("#project-select").value = state.projectId;
    toast("サンプル案件を作成しました。");
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}

async function uploadFiles(event) {
  event.preventDefault();
  try {
    const form = event.currentTarget;
    const files = [...form.elements.files.files];
    const payload = {
      workflow: form.elements.workflow.value,
      files: await Promise.all(
        files.map(async (file) => ({ filename: file.name, content_base64: await asBase64(file) })),
      ),
    };
    const result = await api(withProject("/uploads"), {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#upload-result").textContent = result.paths.join("\n");
  } catch (error) {
    toast(error.message);
  }
}

function asBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.readAsDataURL(file);
  });
}

async function refresh() {
  if (!state.projectId) return;
  try {
    await Promise.all([loadOverview(), loadJobs()]);
    if (page === "analyze") await loadReport();
    if (page === "dirty-excel") await loadDirtyExcel();
    if (page === "impact-board") await loadImpactDecisions();
    if (page === "graph") await loadGraph();
    if (page === "aliases") await loadAliases();
  } catch (error) {
    toast(error.message);
  }
}

async function loadOverview() {
  const data = await api(withProject("/overview"));
  if ($("#metrics")) {
    $("#metrics").innerHTML = [
      ["documents", data.counts.documents],
      ["artifacts", data.counts.artifacts],
      ["entities", data.counts.entities],
      ["relations", data.counts.relations],
      ["evidence", data.counts.evidence],
      ["latest run", data.latest_run || "-"],
      ["backend", data.backend],
      ["LLM", data.llm.enabled ? data.llm.provider : "disabled"],
    ]
      .map(
        ([key, value]) =>
          `<div class="metric"><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>`,
      )
      .join("");
  }
  if ($("#privacy-doctor")) $("#privacy-doctor").textContent = data.privacy_doctor;
  if ($("#project-pulse")) $("#project-pulse").innerHTML = renderProjectPulse(data);
  if ($("#health-check")) $("#health-check").innerHTML = renderHealthCheck(data.health_check);
  if ($("#analysis-mode")) $("#analysis-mode").innerHTML = renderAnalysisMode(data);
  if ($("#dirty-summary") && data.dirty_excel) {
    $("#dirty-summary").textContent = JSON.stringify(data.dirty_excel, null, 2);
  }
  if ($("#llm-status")) {
    $("#llm-status").innerHTML = `<div class="status-card"><span>Provider</span><strong>${escapeHtml(
      data.llm.enabled ? data.llm.provider : "disabled",
    )}</strong><span>Model</span><strong>${escapeHtml(
      data.llm.model || "-",
    )}</strong><span>OPENAI_API_KEY</span><strong>${
      data.openai_api_key_available ? "available" : "not set"
    }</strong><span>Codex CLI</span><strong>${
      data.codex_cli_available ? "available" : "not found"
    }</strong></div>`;
  }
}

function renderProjectPulse(data) {
  const graphReady = data.counts.relations > 0;
  const latestRun = data.latest_run || "まだありません";
  return [
    ["Graph", graphReady ? "ready" : "empty", `${data.counts.relations} relations / ${data.counts.evidence} evidence`],
    ["Latest run", latestRun, data.latest_run ? "レポートを download できます" : "Analyze を実行してください"],
    [
      "AI mode",
      data.llm.enabled ? `${data.llm.provider} / ${data.llm.model || "-"}` : "local-only",
      data.llm.external_transmission ? "job 単位で外部送信確認あり" : "外部 LLM 送信なし",
    ],
    [
      "Embeddings",
      data.embeddings.enabled ? data.embeddings.provider : "disabled",
      data.embeddings.provider === "openai" ? "外部送信確認あり" : "local retrieval",
    ],
  ]
    .map(
      ([label, value, note]) =>
        `<div class="pulse-row"><strong>${escapeHtml(label)}: ${escapeHtml(
          value,
        )}</strong><span>${escapeHtml(note)}</span></div>`,
    )
    .join("");
}

function renderHealthCheck(health) {
  if (!health) return '<p class="empty-state">Excel ingest を実行すると表示されます。</p>';
  const warnings = health.warnings?.length ? health.warnings.join(" / ") : "警告なし";
  return [
    ["Workbooks", health.workbooks ?? 0, `${health.sheets ?? 0} sheets`],
    [
      "Artifacts",
      health.detected_artifacts ?? 0,
      `${health.possible_relations ?? 0} relation candidates`,
    ],
    [
      "Excel shape",
      `${health.merged_cells ?? 0} merged cells`,
      `${health.hidden_sheets ?? 0} hidden sheets`,
    ],
    ["Alias", `${health.alias_candidates?.length ?? 0} candidates`, warnings],
  ]
    .map(
      ([label, value, note]) =>
        `<div class="pulse-row"><strong>${escapeHtml(label)}: ${escapeHtml(
          value,
        )}</strong><span>${escapeHtml(note)}</span></div>`,
    )
    .join("");
}

function renderAnalysisMode(data) {
  const llmLabel = data.llm.enabled ? `${data.llm.provider} / ${data.llm.model || "-"}` : "local-only";
  const transmission = data.llm.external_transmission
    ? "外部 provider 送信は modal と core consent の二段確認"
    : "外部 LLM 送信なし";
  const codex = data.codex_cli_available ? "Codex CLI: available" : "Codex CLI: not found";
  return `<strong>${escapeHtml(llmLabel)}</strong><span>${escapeHtml(
    transmission,
  )}</span><div class="badge-row"><span>${escapeHtml(codex)}</span><span>batch rerank</span><span>hash-only trace</span></div>`;
}

async function loadJobs() {
  const jobs = (await api(withProject("/jobs"))).jobs;
  const html = jobs.length
    ? jobs
        .map(
          (job) =>
            `<div class="job"><div><strong>${escapeHtml(job.action)}</strong> <span class="status ${escapeHtml(
              job.state,
            )}">${escapeHtml(job.state)}</span><small>${escapeHtml(job.created_at)}<br>${escapeHtml(
              JSON.stringify(job.result_summary || job.error_summary || ""),
            )}${recoveryHint(job)}</small></div>${
              job.state === "queued"
                ? `<button class="button ghost" onclick="cancelJob('${escapeHtml(job.job_id)}')">取消</button>`
                : ""
            }</div>`,
        )
        .join("")
    : '<p class="empty-state">Job はまだありません。</p>';
  if ($("#jobs-list")) $("#jobs-list").innerHTML = html;
  if ($("#dashboard-jobs")) {
    $("#dashboard-jobs").innerHTML =
      jobs
        .slice(0, 5)
        .map(
          (job) =>
            `<div class="job"><div><strong>${escapeHtml(job.action)}</strong> <span class="status ${escapeHtml(
              job.state,
            )}">${escapeHtml(job.state)}</span></div></div>`,
        )
        .join("") || '<p class="empty-state">Job はまだありません。</p>';
  }
  if (jobs.some((job) => ["queued", "running"].includes(job.state))) setTimeout(loadJobs, 1000);
}

async function cancelJob(id) {
  try {
    await api(withProject(`/jobs/${id}/cancel`), { method: "POST", body: "{}" });
    await loadJobs();
  } catch (error) {
    toast(error.message);
  }
}

async function loadReport() {
  const history = (await api(withProject("/runs"))).runs;
  $("#run-history").innerHTML =
    history
      .map(
        (run) =>
          `<p><strong>${escapeHtml(run.run_id)}</strong><br>${escapeHtml(run.title)}<br>${
            run.candidate_count
          } candidates</p>`,
      )
      .join("") || '<p class="empty-state">Run はまだありません。</p>';
  if (!history.length) {
    $("#report").innerHTML = '<p class="empty-state">Analyze を実行してください。</p>';
    return;
  }
  const report = await api(withProject("/report"));
  $("#report").innerHTML = ["must_review", "should_review", "may_review", "hidden"]
    .map(
      (group) =>
        `<section class="priority"><h3>${group} (${report[group].length})</h3>${report[group]
          .map(
            (item, index) =>
              `<details ${index === 0 ? "open" : ""}><summary>${escapeHtml(
                item.display_name,
              )} <code>${escapeHtml(item.artifact_id)}</code></summary><ul><li>${escapeHtml(
                item.reason,
              )}</li><li>${item.relation_paths.map(escapeHtml).join("<br>")}</li>${renderEvidence(
                item.evidence,
              )}</ul></details>`,
          )
          .join("")}</section>`,
    )
    .join("");
}

async function loadDirtyExcel() {
  const data = await api(withProject("/dirty-excel"));
  $("#dirty-summary").textContent = JSON.stringify(data.summary, null, 2);
  $("#dirty-proposals").innerHTML = data.proposals.length
    ? data.proposals
        .map(
          (proposal) => renderGraphProposal(proposal),
        )
        .join("")
    : '<p class="empty-state">proposal はまだありません。</p>';
  $("#dirty-regions").innerHTML = data.regions.length
    ? data.regions
        .map(
          (region) =>
            `<details><summary>${escapeHtml(region.sheet_name)} ${escapeHtml(
              region.range,
            )} <span>${escapeHtml(region.region_type)}</span></summary><pre>${escapeHtml(
              region.rendered_text,
            )}</pre></details>`,
        )
        .join("")
    : '<p class="empty-state">region はまだありません。</p>';
  $$("[data-proposal-id]").forEach((button) => {
    button.onclick = () =>
      enqueue("graph_proposal_decide", {
        proposal_id: button.dataset.proposalId,
        status: button.dataset.proposalStatus,
      });
  });
}

async function loadImpactDecisions() {
  const data = await api(withProject("/impact-decisions"));
  $("#impact-decisions").innerHTML = renderImpactDecisionTable(data.decisions);
  $$("[data-impact-status]").forEach((control) => {
    control.onchange = () =>
      enqueue("impact_status", {
        impact_id: control.dataset.impactId,
        status: control.value,
        reason: control.closest("tr")?.querySelector("[data-impact-reason]")?.value || "",
      }).then(() => setTimeout(loadImpactDecisions, 700));
  });
  $$("[data-impact-save]").forEach((button) => {
    button.onclick = () =>
      enqueue("impact_status", {
        impact_id: button.dataset.impactId,
        status:
          button.closest("tr")?.querySelector("[data-impact-status]")?.value || "unreviewed",
        reason: button.closest("tr")?.querySelector("[data-impact-reason]")?.value || "",
      }).then(() => setTimeout(loadImpactDecisions, 700));
  });
}

function renderGraphProposal(proposal) {
  const nodes = proposal.result.nodes || [];
  const edges = proposal.result.edges || [];
  const warnings = proposal.result.warnings || [];
  const unresolved = proposal.result.unresolved_mentions || [];
  return `<details><summary>${escapeHtml(proposal.proposal_id)} <span class="status ${escapeHtml(
    proposal.status,
  )}">${escapeHtml(proposal.status)}</span></summary>
    <div class="detail-grid">
      <div><span>Region</span><strong>${escapeHtml(proposal.region_id)}</strong></div>
      <div><span>Method</span><strong>${escapeHtml(proposal.extraction_method)}</strong></div>
      <div><span>Diff</span><strong>+${nodes.length} nodes / +${edges.length} edges</strong></div>
    </div>
    <h3>Nodes to add</h3>
    ${renderMiniList(nodes.map((node) => `${node.node_type}: ${node.display_name}`))}
    <h3>Edges to add</h3>
    ${renderMiniList(edges.map((edge) => `${edge.source_temp_id} -${edge.relation_type}-> ${edge.target_temp_id}`))}
    <h3>Evidence</h3>
    ${renderMiniList([...new Set([...nodes, ...edges].flatMap((item) => item.evidence_ids || []))])}
    ${warnings.length ? `<h3>Warnings</h3>${renderMiniList(warnings)}` : ""}
    ${unresolved.length ? `<h3>Unresolved mentions</h3>${renderMiniList(unresolved)}` : ""}
    <button class="button ghost" data-proposal-id="${escapeHtml(
      proposal.proposal_id,
    )}" data-proposal-status="accepted">Accept</button>
    <button class="button ghost" data-proposal-id="${escapeHtml(
      proposal.proposal_id,
    )}" data-proposal-status="rejected">Reject</button>
  </details>`;
}

function renderImpactDecisionTable(decisions) {
  if (!decisions.length) return '<p class="empty-state">Impact decision はまだありません。</p>';
  const statuses = [
    "unreviewed",
    "accepted",
    "rejected",
    "needs_investigation",
    "implemented",
    "tested",
    "closed",
  ];
  const rows = decisions
    .map(
      (item) => `<tr>
        <td><strong>${escapeHtml(item.display_name || item.candidate_node_id)}</strong><br><small>${escapeHtml(
          item.impact_id,
        )}</small></td>
        <td><span class="status ${escapeHtml(item.review_priority || "unconfirmed")}">${escapeHtml(
          item.review_priority || "-",
        )}</span><br><small>${escapeHtml(item.impact_type || item.artifact_type || "")}</small></td>
        <td>${escapeHtml(item.impact_reason || "")}${renderMiniList(item.required_actions || [])}${
          item.warnings?.length ? `<small>${escapeHtml(item.warnings.join(" / "))}</small>` : ""
        }</td>
        <td>${renderEvidenceButtons(item.evidence_ids || [])}</td>
        <td><select data-impact-status data-impact-id="${escapeHtml(item.impact_id)}">${statuses
          .map(
            (status) =>
              `<option ${status === item.status ? "selected" : ""}>${escapeHtml(status)}</option>`,
          )
          .join("")}</select></td>
        <td><input data-impact-reason value="${escapeHtml(item.reason || "")}" placeholder="review reason"></td>
        <td><button class="button ghost" data-impact-save data-impact-id="${escapeHtml(
          item.impact_id,
        )}">Save</button></td>
      </tr>`,
    )
    .join("");
  return `<div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Priority</th><th>Reason / Actions</th><th>Evidence</th><th>Status</th><th>Decision reason</th><th></th></tr></thead><tbody>${rows}</tbody></table></div><div id="impact-evidence-viewer" class="graph-detail"></div>`;
}

function renderMiniList(items) {
  if (!items.length) return '<p class="empty-state">none</p>';
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderEvidenceButtons(ids) {
  if (!ids.length) return "-";
  return ids
    .map(
      (id) =>
        `<button class="table-link" onclick="showEvidence('${escapeHtml(id)}', '#impact-evidence-viewer')">${escapeHtml(
          id,
        )}</button>`,
    )
    .join("<br>");
}

async function showEvidence(id, target = "#graph-detail") {
  const query = new URLSearchParams();
  query.append("evidence_id", id);
  const response = await api(withProject(`/evidence?${query}`));
  const evidence = response.evidence || [];
  const element = $(target);
  if (element) {
    element.innerHTML = `<h3>Evidence</h3>${renderEvidenceList(evidence)}`;
  }
}

async function loadGraph() {
  const query = new URLSearchParams();
  if ($("#graph-status")?.value) query.set("status", $("#graph-status").value);
  if ($("#graph-method")?.value) query.set("extraction_method", $("#graph-method").value);
  const graph = await api(withProject(`/graph?${query}`));
  renderRelations(graph.relations);
  renderGraphStats(graph);
  if (!graph.nodes.length) {
    state.cy?.destroy();
    state.cy = null;
    $("#graph-canvas").innerHTML =
      '<div class="graph-empty"><strong>表示できる node がありません</strong><span>Ingest を実行するか、filter を解除してください。</span></div>';
    $("#graph-view-status").textContent = "表示できる node がありません。";
    $("#graph-detail").innerHTML =
      '<p class="empty-state">node が追加されると、選択項目の詳細と evidence を表示します。</p>';
    return;
  }
  if (!window.cytoscape) return;
  state.cy?.destroy();
  state.cy = cytoscape({
    container: $("#graph-canvas"),
    elements: [...graph.nodes, ...graph.edges],
    style: graphStyles(),
    layout: {
      name: "cose",
      fit: false,
      padding: 28,
      nodeRepulsion: 9500,
      idealEdgeLength: 96,
      edgeElasticity: 110,
      nestingFactor: 1.2,
      gravity: 0.8,
      numIter: 700,
      nodeDimensionsIncludeLabels: true,
      animate: false,
    },
    minZoom: 0.18,
    maxZoom: 2.2,
  });
  state.cy.on("tap", "node,edge", async (event) => {
    focusGraphSelection(event.target);
    await showGraphDetail(event.target);
  });
  state.cy.on("tap", (event) => {
    if (event.target === state.cy) clearGraphFocus();
  });
  const initialNode = pickInitialGraphNode();
  if (initialNode) {
    focusGraphSelection(initialNode);
    await showGraphDetail(initialNode);
  } else {
    fitGraph();
  }
}

function graphStyles() {
  return [
    {
      selector: "node",
      style: {
        "background-color": "#2563eb",
        "border-color": "#ffffff",
        "border-width": 2,
        color: "#163052",
        "font-size": 10,
        "font-weight": 600,
        height: 24,
        label: "data(label)",
        padding: "8px",
        shape: "round-rectangle",
        "text-background-color": "#ffffff",
        "text-background-opacity": 0.88,
        "text-background-padding": "3px",
        "text-max-width": "132px",
        "text-valign": "bottom",
        "text-margin-y": 8,
        "text-wrap": "wrap",
        width: 34,
      },
    },
    {
      selector: 'node[kind="entity"]',
      style: { "background-color": "#0f766e", shape: "ellipse" },
    },
    {
      selector: 'node[kind="reference"]',
      style: { "background-color": "#64748b", shape: "diamond" },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": "#cbd5e1",
        opacity: 0.16,
        "target-arrow-color": "#cbd5e1",
        "target-arrow-shape": "triangle",
        width: 1.4,
      },
    },
    {
      selector: 'edge[status="confirmed"]',
      style: { "line-color": "#0f766e", opacity: 0.28, "target-arrow-color": "#0f766e", width: 2 },
    },
    {
      selector: 'edge[status="rejected"]',
      style: {
        "line-color": "#dc2626",
        "line-style": "dashed",
        opacity: 0.34,
        "target-arrow-color": "#dc2626",
      },
    },
    {
      selector: ".faded",
      style: { opacity: 0.06 },
    },
    {
      selector: ".focused",
      style: {
        "border-color": "#f59e0b",
        "border-width": 4,
        color: "#0f172a",
        label: "data(label)",
        "line-color": "#f59e0b",
        opacity: 1,
        "target-arrow-color": "#f59e0b",
        "text-background-opacity": 1,
        width: 3,
        "z-index": 10,
      },
    },
    {
      selector: "node.anchor",
      style: {
        "background-color": "#f59e0b",
        "border-color": "#92400e",
        "border-width": 4,
        height: 34,
        width: 44,
      },
    },
    {
      selector: "edge.focused",
      style: {
        "font-size": 9,
        label: "data(label)",
        "text-background-color": "#fffbeb",
        "text-background-opacity": 1,
        "text-background-padding": "3px",
      },
    },
    {
      selector: ".highlighted",
      style: { "border-color": "#f59e0b", "border-width": 4 },
    },
  ];
}

function renderRelations(relations) {
  $("#relation-table").innerHTML = relations
    .map(
      (row) =>
        `<tr><td><button class="table-link" data-focus-relation="${escapeHtml(
          row.relation_id,
        )}">${escapeHtml(row.relation_type)}</button></td><td>${escapeHtml(
          row.source_id,
        )}</td><td>${escapeHtml(row.target_id)}</td><td><span class="status ${escapeHtml(
          row.status,
        )}">${escapeHtml(row.status)}</span></td><td><select aria-label="${escapeHtml(
          row.relation_type,
        )} relation status" data-relation-id="${escapeHtml(row.relation_id)}"><option ${
          row.status === "unconfirmed" ? "selected" : ""
        }>unconfirmed</option><option ${
          row.status === "confirmed" ? "selected" : ""
        }>confirmed</option><option ${
          row.status === "rejected" ? "selected" : ""
        }>rejected</option></select></td></tr>`,
    )
    .join("");
  $$("[data-relation-id]").forEach((select) => {
    select.onchange = () => relationStatus(select.dataset.relationId, select.value);
  });
  $$("[data-focus-relation]").forEach((button) => {
    button.onclick = () => focusGraphElement(button.dataset.focusRelation);
  });
}

function renderGraphStats(graph) {
  $("#graph-stats").innerHTML = [
    ["Nodes", graph.nodes.length],
    ["Relations", graph.edges.length],
    ["Artifacts", graph.artifacts.length],
    ["Entities", graph.entities.length],
  ]
    .map(([label, value]) => `<span class="stat-chip"><strong>${value}</strong>${label}</span>`)
    .join("");
}

function fitGraph() {
  if (!state.cy) return;
  clearGraphFocus();
  state.cy.fit(state.cy.elements(), 30);
  $("#graph-view-status").textContent =
    "全 node を表示しています。検索または relation 一覧から対象を選択すると、近傍に絞り込めます。";
}

async function resetGraph() {
  if ($("#graph-search")) $("#graph-search").value = "";
  if ($("#graph-status")) $("#graph-status").value = "";
  if ($("#graph-method")) $("#graph-method").value = "";
  await loadGraph();
}

function filterGraphSearch() {
  if (!state.cy) return;
  const term = ($("#graph-search")?.value || "").trim().toLowerCase();
  state.cy.nodes().removeClass("highlighted");
  if (!term) {
    $("#graph-view-status").textContent =
      "検索条件はありません。node または relation を選択すると、近傍に絞り込めます。";
    return;
  }
  clearGraphFocus();
  const matches = state.cy.nodes().filter((node) => {
    const data = node.data();
    return `${data.label || ""} ${data.id || ""}`.toLowerCase().includes(term);
  });
  matches.addClass("highlighted");
  if (matches.length) {
    state.cy.fit(matches, 90);
    $("#graph-view-status").textContent = `検索「${term}」に一致する ${matches.length} nodes を表示しています。`;
  } else {
    $("#graph-view-status").textContent = `検索「${term}」に一致する node はありません。`;
  }
}

function pickInitialGraphNode() {
  if (!state.cy) return null;
  const artifacts = state.cy.nodes('[kind="artifact"]');
  const candidates = artifacts.length ? artifacts : state.cy.nodes();
  let best = candidates[0];
  candidates.forEach((node) => {
    if (node.degree() > best.degree()) best = node;
  });
  return best;
}

async function focusGraphElement(id) {
  if (!state.cy) return;
  const element = state.cy.getElementById(id);
  if (!element.length) return;
  focusGraphSelection(element);
  await showGraphDetail(element);
}

function focusGraphSelection(element) {
  if (!state.cy) return;
  state.cy.elements().removeClass("faded focused anchor");
  const neighborhood = element.isNode()
    ? element.closedNeighborhood()
    : element.connectedNodes().union(element);
  state.cy.elements().difference(neighborhood).addClass("faded");
  neighborhood.addClass("focused");
  if (element.isNode()) element.addClass("anchor");
  state.cy.fit(neighborhood, 72);
  highlightRelationRow(element.isEdge() ? element.id() : null);
  $("#graph-view-status").textContent = `${element.data("label") || element.id()} の近傍 ${
    neighborhood.nodes().length
  } nodes / ${neighborhood.edges().length} relations を表示しています。`;
}

function clearGraphFocus() {
  state.cy?.elements().removeClass("faded focused anchor");
  highlightRelationRow(null);
}

function highlightRelationRow(relationId) {
  $$("[data-focus-relation]").forEach((button) => {
    button.closest("tr").classList.toggle("is-active", button.dataset.focusRelation === relationId);
  });
}

async function showGraphDetail(element) {
  const data = element.data();
  let evidence = [];
  if (data.evidence_ids?.length) {
    const query = new URLSearchParams();
    data.evidence_ids.forEach((id) => query.append("evidence_id", id));
    evidence = (await api(withProject(`/evidence?${query}`))).evidence;
  }
  $("#graph-detail").innerHTML = renderGraphDetail(data, evidence, element.isEdge());
}

function renderGraphDetail(data, evidence, isEdge) {
  const fields = isEdge
    ? [
        ["Relation", data.label],
        ["Source", data.source],
        ["Target", data.target],
        ["Status", data.status],
        ["Extraction", data.method],
      ]
    : [
        ["Name", data.label],
        ["ID", data.id],
        ["Kind", data.kind],
        ["Type", data.type || "-"],
      ];
  return `<div class="detail-grid">${fields
    .map(
      ([label, value]) =>
        `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "-")}</strong></div>`,
    )
    .join("")}</div><h3>Evidence ${evidence.length ? `(${evidence.length})` : ""}</h3>${
    evidence.length
      ? `<ul class="evidence-list">${evidence
          .map(
            (item) =>
              `<li><code>${escapeHtml(item.evidence_id)}</code><small>${escapeHtml(
                item.source_location.file,
              )}:${item.source_location.line_start}-${item.source_location.line_end}</small><p>${escapeHtml(
                item.quote,
              )}</p></li>`,
          )
          .join("")}</ul>`
      : '<p class="empty-state">関連する evidence はありません。</p>'
  }`;
}

async function relationStatus(relationId, status) {
  await enqueue("relation_status", { relation_id: relationId, status });
  setTimeout(loadGraph, 700);
}

async function loadAliases() {
  const data = await api(withProject("/aliases"));
  $("#aliases-result").innerHTML = renderAliasReview(data);
  $$("[data-alias-candidate]").forEach((button) => {
    button.onclick = () =>
      enqueue(button.dataset.aliasAction, {
        candidate_id: button.dataset.aliasCandidate,
      }).then(() => setTimeout(loadAliases, 700));
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

function renderEvidence(items = []) {
  if (!items.length) return "<li>evidence: direct match</li>";
  return items
    .map(
      (item) =>
        `<li><code>${escapeHtml(item.evidence_id)}</code><br>${escapeHtml(
          item.source_location.file,
        )}:${item.source_location.line_start}-${item.source_location.line_end}<br>${escapeHtml(
          item.quote,
        )}</li>`,
    )
    .join("");
}

function recoveryHint(job) {
  const text = JSON.stringify(job.error_summary || "").toLowerCase();
  if (!text || job.state !== "failed") return "";
  if (text.includes("llm provider not configured")) {
    return "<br><strong>Next:</strong> Settings で provider を設定するか --no-llm/local-only を選びます。";
  }
  if (text.includes("external transmission") || text.includes("approval")) {
    return "<br><strong>Next:</strong> 外部送信previewを確認して承認してから再実行します。";
  }
  if (text.includes("excel") || text.includes("workbook")) {
    return "<br><strong>Next:</strong> Excel inspect/classify で対象ファイルと未対応要素を確認します。";
  }
  if (text.includes("proposal")) {
    return "<br><strong>Next:</strong> Dirty Excel の proposal / warnings を確認します。";
  }
  return "<br><strong>Next:</strong> 入力path、provider設定、最新jobの詳細を確認します。";
}

function renderEvidenceList(items = []) {
  if (!items.length) return '<p class="empty-state">関連する evidence はありません。</p>';
  return `<ul class="evidence-list">${items
    .map(
      (item) =>
        `<li><code>${escapeHtml(item.evidence_id)}</code><small>${escapeHtml(
          item.source_location.file,
        )}:${item.source_location.line_start}-${item.source_location.line_end}</small><p>${escapeHtml(
          item.quote,
        )}</p></li>`,
    )
    .join("")}</ul>`;
}

function renderAliasReview(data) {
  const candidates = data.candidates || [];
  const candidateTable = candidates.length
    ? `<div class="table-wrap"><table><thead><tr><th>Target</th><th>Aliases</th><th>Judgement</th><th>Evidence</th><th>Action</th></tr></thead><tbody>${candidates
        .map(
          (item) => `<tr>
            <td><strong>${escapeHtml(item.target_id)}</strong><br><small>${escapeHtml(
              (item.compared_entity_ids || []).join(", "),
            )}</small></td>
            <td>${renderMiniList(item.aliases || [])}</td>
            <td><span class="status ${escapeHtml(item.status)}">${escapeHtml(
              item.status,
            )}</span><br><small>${escapeHtml(item.judgement)}: ${escapeHtml(
              item.llm_reason || item.reason || "",
            )}</small></td>
            <td>${renderMiniList(item.evidence_quotes || item.evidence_ids || [])}</td>
            <td><button class="button ghost" data-alias-action="alias_confirm" data-alias-candidate="${escapeHtml(
              item.candidate_id,
            )}">Confirm</button><button class="button ghost" data-alias-action="alias_reject_candidate" data-alias-candidate="${escapeHtml(
              item.candidate_id,
            )}">Reject</button></td>
          </tr>`,
        )
        .join("")}</tbody></table></div>`
    : '<p class="empty-state">alias candidate はまだありません。</p>';
  return `${candidateTable}<h3>Raw aliases</h3><pre>${escapeHtml(
    JSON.stringify({ aliases: data.aliases, suggestions: data.suggestions }, null, 2),
  )}</pre>`;
}

boot().catch((error) => toast(error.message));
