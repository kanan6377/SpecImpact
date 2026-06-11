/* ============================================================
 * SpecImpact Console - live GUI shell
 * ============================================================ */

(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const TERMINAL = new Set(["succeeded", "failed", "cancelled", "interrupted"]);
  const fallback = typeof SI_DATA !== "undefined" ? SI_DATA : {};

  const state = {
    csrf: "",
    project: null,
    overview: null,
    report: null,
    graph: null,
    aliases: null,
    jobs: [],
    design: null,
    selectedEvidenceIds: [],
    selectedDocumentFile: "",
    projectReady: false,
    impactFilter: "all",
    impactQuery: "",
    designMode: "impacts",
    graphInit: false,
    chart: null,
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function toast(message) {
    const toastEl = $("#toast");
    const msgEl = $("#toast-msg");
    if (!toastEl || !msgEl) return;
    msgEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  async function api(path, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (options.method && options.method !== "GET") {
      if (!state.csrf) await loadSession();
      headers["X-CSRF-Token"] = state.csrf;
    }
    const response = await fetch(path, { credentials: "same-origin", ...options, headers });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const json = await response.json();
        detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail || json);
      } catch (_error) {
        detail = await response.text();
      }
      throw new Error(detail);
    }
    return response.json();
  }

  async function loadSession() {
    const session = await api("/api/session");
    state.csrf = session.csrf_token;
  }

  function projectIdFromUrl() {
    return new URLSearchParams(window.location.search).get("project_id");
  }

  async function resolveProject() {
    const projectId = projectIdFromUrl();
    const data = await api("/api/projects");
    state.project = projectId
      ? data.projects.find((item) => item.project_id === projectId)
      : data.projects[0];
    if (!state.project) throw new Error("プロジェクトが登録されていません。");
  }

  async function refreshAll() {
    if (!state.project) return;
    const id = state.project.project_id;
    const results = await Promise.allSettled([
      api(`/api/projects/${id}/overview`),
      api(`/api/projects/${id}/report`),
      api(`/api/projects/${id}/graph`),
      api(`/api/projects/${id}/aliases`),
      api(`/api/projects/${id}/jobs`),
      api(`/api/projects/${id}/design-documents`),
    ]);
    [state.overview, state.report, state.graph, state.aliases] = results
      .slice(0, 4)
      .map((item) => (item.status === "fulfilled" ? item.value : null));
    state.jobs = results[4].status === "fulfilled" ? results[4].value.jobs || [] : [];
    state.design = results[5].status === "fulfilled" ? results[5].value : null;
    state.projectReady = true;
    renderAll();
  }

  async function loadDesignForEvidence(evidenceIds) {
    state.selectedEvidenceIds = evidenceIds || [];
    if (!state.project) return;
    const query = state.selectedEvidenceIds
      .map((id) => `evidence_id=${encodeURIComponent(id)}`)
      .join("&");
    state.design = await api(
      `/api/projects/${state.project.project_id}/design-documents${query ? `?${query}` : ""}`
    );
    const highlighted = state.design.documents?.find((doc) => (doc.highlight_count || 0) > 0);
    if (highlighted) state.selectedDocumentFile = highlighted.file;
    renderDesignViewer();
  }

  function showView(name) {
    $$(".view").forEach((view) => view.classList.remove("active"));
    const view = $(`#view-${name}`);
    if (view) view.classList.add("active");
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
    if (name === "graph") renderGraph();
  }

  function setupNavigation() {
    $$(".nav-item").forEach((btn) => btn.addEventListener("click", () => showView(btn.dataset.view)));
    $$("[data-goto]").forEach((btn) => btn.addEventListener("click", () => showView(btn.dataset.goto)));
    $("#btn-new-analyze")?.addEventListener("click", () => {
      showView("impacts");
      $("#change-natural-text")?.focus();
    });
    $$("[data-demo-toast]").forEach((btn) =>
      btn.addEventListener("click", () => toast(btn.dataset.demoToast || "この操作は現在の画面では未接続です。"))
    );
  }

  function ensureWorkflowPanel() {
    if ($("#change-workflow-panel")) return;
    const impactView = $("#view-impacts");
    const toolbar = $(".board-toolbar", impactView);
    if (!impactView || !toolbar) return;
    const panel = document.createElement("div");
    panel.id = "change-workflow-panel";
    panel.className = "change-workflow card card-pad";
    panel.innerHTML = `
      <div class="workflow-head">
        <div>
          <div class="detail-label"><i class="fa-solid fa-wand-magic-sparkles"></i>LLM-first change flow</div>
          <h2>設計書を選んで、自然言語で変更内容を入力</h2>
          <p>選択した設計書を起点に、GraphRAG上の関連ノードと証跡から影響候補を作ります。LLM出力はレビュー候補として扱われます。</p>
        </div>
        <div class="view-switch" role="tablist" aria-label="影響候補と設計書参照の切り替え">
          <button class="active" data-design-mode="impacts" type="button"><i class="fa-solid fa-list-check"></i>一覧</button>
          <button data-design-mode="design" type="button"><i class="fa-solid fa-file-excel"></i>設計書参照</button>
        </div>
      </div>
      <div class="workflow-form">
        <label>
          <span>変更したい設計書</span>
          <select id="design-doc-select"></select>
        </label>
        <label class="change-text-label">
          <span>変更箇所・変更内容</span>
          <textarea id="change-natural-text" rows="4" placeholder="例: 入会申込画面の利用限度額上限を999万円から9999万円に変更したい"></textarea>
        </label>
        <button class="btn btn-primary" id="run-natural-analysis" type="button">
          <i class="fa-solid fa-bolt"></i>GraphRAGで影響分析
        </button>
      </div>
      <div class="workflow-status" id="workflow-status"></div>
    `;
    impactView.insertBefore(panel, toolbar);
    $("#run-natural-analysis")?.addEventListener("click", runNaturalAnalysis);
    $$(".view-switch [data-design-mode]").forEach((btn) =>
      btn.addEventListener("click", () => {
        state.designMode = btn.dataset.designMode;
        updateModeSwitch();
      })
    );
  }

  function renderAll() {
    renderTopbar();
    renderDashboard();
    renderImpacts();
    renderAliases();
    renderJobs();
    renderDesignPicker();
    renderDesignViewer();
    updateBadges();
    if ($("#view-graph")?.classList.contains("active")) renderGraph();
  }

  function renderTopbar() {
    const picker = $(".project-picker");
    if (picker) {
      const label = state.project?.display_name || state.project?.path || fallback.project?.label || "SpecImpact project";
      picker.innerHTML = `<span class="dot"></span>${esc(label)}<i class="fa-solid fa-chevron-down"></i>`;
    }
    const llm = state.overview?.llm;
    const llmChip = $(".chip-llm");
    if (llmChip && llm) {
      const provider = llm.enabled ? `${llm.provider || "llm"} / ${llm.model || "default"}` : "LLM未設定 / local fallback";
      llmChip.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i>${esc(provider)}`;
    }
  }

  function counts() {
    return state.overview?.counts || fallback.stats || {};
  }

  function renderDashboard() {
    const defs = [
      ["documents", "Documents", "fa-file-lines"],
      ["artifacts", "Artifacts", "fa-cube"],
      ["entities", "Entities", "fa-tag"],
      ["relations", "Relations", "fa-link"],
      ["evidence", "Evidence", "fa-quote-left"],
    ];
    const grid = $("#stat-grid");
    if (grid) {
      const values = counts();
      grid.innerHTML = defs.map(([key, label, icon]) => `
        <div class="stat-card">
          <div class="sc-label"><i class="fa-solid ${icon}"></i>${label}</div>
          <div class="sc-value">${esc(values[key] ?? 0)}</div>
        </div>
      `).join("");
    }
    renderChart();
  }

  function reportImpacts() {
    if (!state.report) return fallback.impacts || [];
    return ["must_review", "should_review", "may_review", "hidden"].flatMap((priority) =>
      (state.report[priority] || []).map((impact, index) => ({
        id: `impact.${priority}.${impact.artifact_id || index}`,
        priority,
        status: "open",
        name: impact.display_name || impact.artifact_id,
        artifactId: impact.artifact_id,
        kind: impact.artifact_type || "artifact",
        reason: impact.reason || impact.rule_assessment || "",
        impactType: impact.impact_type || "review",
        requiredActions: impact.required_actions || [],
        path: impact.relation_paths || [],
        evidence: (impact.evidence || []).map((item) => ({
          evidence_id: item.evidence_id,
          file: item.source_location?.file || "",
          locator: locationLabel(item.source_location),
          quote: item.quote || "",
        })),
        evidenceIds: impact.evidence_ids || [],
        llm: {
          judgement: impact.llm_judgement || impact.rule_assessment || "candidate",
          reason: impact.llm_reason || impact.reason || "",
          confidence: impact.uncertainty === "low" ? 0.82 : 0.62,
        },
      }))
    );
  }

  function locationLabel(location) {
    if (!location) return "";
    if (location.line_start === location.line_end) return `L${location.line_start}`;
    return `L${location.line_start}-L${location.line_end}`;
  }

  function renderChart() {
    const canvas = $("#impact-chart");
    if (!canvas || !window.Chart) return;
    const countsByPriority = { must_review: 0, should_review: 0, may_review: 0 };
    reportImpacts().forEach((impact) => {
      if (countsByPriority[impact.priority] !== undefined) countsByPriority[impact.priority] += 1;
    });
    if (state.chart) state.chart.destroy();
    state.chart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["must_review", "should_review", "may_review"],
        datasets: [{
          data: [countsByPriority.must_review, countsByPriority.should_review, countsByPriority.may_review],
          backgroundColor: ["#dc2626", "#d97706", "#2563eb"],
          borderWidth: 2,
          borderColor: "#ffffff",
        }],
      },
      options: {
        maintainAspectRatio: false,
        cutout: "64%",
        plugins: { legend: { position: "right", labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    });
  }

  function renderImpacts() {
    const list = $("#impact-list");
    const filters = $("#impact-filters");
    if (!list || !filters) return;
    const impacts = reportImpacts();
    const filterKeys = ["all", "must_review", "should_review", "may_review"];
    const countBy = Object.fromEntries(filterKeys.map((key) => [key, key === "all" ? impacts.length : 0]));
    impacts.forEach((impact) => {
      if (countBy[impact.priority] !== undefined) countBy[impact.priority] += 1;
    });
    filters.innerHTML = filterKeys.map((key) => `
      <button class="filter-pill ${state.impactFilter === key ? "active" : ""}" data-filter="${key}">
        ${key === "all" ? "すべて" : key}<span class="cnt">${countBy[key] || 0}</span>
      </button>
    `).join("");
    $$("#impact-filters .filter-pill").forEach((pill) =>
      pill.addEventListener("click", () => {
        state.impactFilter = pill.dataset.filter;
        renderImpacts();
      })
    );
    const query = state.impactQuery.toLowerCase();
    const items = impacts.filter((impact) => {
      if (state.impactFilter !== "all" && impact.priority !== state.impactFilter) return false;
      if (!query) return true;
      return [impact.name, impact.reason, impact.artifactId, impact.kind].join(" ").toLowerCase().includes(query);
    });
    if (!items.length) {
      list.innerHTML = `<div class="card card-pad empty-state">影響候補はまだありません。変更内容を入力して分析してください。</div>`;
      return;
    }
    list.innerHTML = items.map((impact) => impactCardHtml(impact)).join("");
    $$(".impact-head", list).forEach((head) => {
      head.addEventListener("click", async () => {
        const card = head.closest(".impact-card");
        card.classList.toggle("open");
        head.setAttribute("aria-expanded", String(card.classList.contains("open")));
        const ids = JSON.parse(card.dataset.evidenceIds || "[]");
        await loadDesignForEvidence(ids);
      });
    });
    $$("[data-open-design]", list).forEach((btn) =>
      btn.addEventListener("click", async (event) => {
        event.stopPropagation();
        await loadDesignForEvidence(JSON.parse(btn.closest(".impact-card").dataset.evidenceIds || "[]"));
        state.designMode = "design";
        updateModeSwitch();
        $("#design-reference-panel")?.scrollIntoView({ block: "start", behavior: "smooth" });
      })
    );
  }

  function impactCardHtml(impact) {
    const priorityClass = {
      must_review: "p-must prio-must",
      should_review: "p-should prio-should",
      may_review: "p-may prio-may",
      hidden: "p-may prio-may",
    }[impact.priority] || "p-may prio-may";
    const evidenceHtml = impact.evidence.length
      ? impact.evidence.map((ev) => `
        <button class="evidence-quote evidence-button" type="button" data-open-design>
          <div class="eq-src"><i class="fa-solid fa-file-lines"></i>${esc(ev.file)} ${esc(ev.locator)}</div>
          <div class="eq-text">"${esc(ev.quote)}"</div>
        </button>
      `).join("")
      : `<div class="no-evidence"><i class="fa-solid fa-triangle-exclamation"></i>直接evidenceなし。must_reviewには昇格しません。</div>`;
    return `
      <article class="impact-card ${priorityClass.split(" ")[0]}" data-id="${esc(impact.id)}" data-evidence-ids='${esc(JSON.stringify(impact.evidenceIds || []))}'>
        <div class="impact-head" role="button" tabindex="0" aria-expanded="false">
          <span class="prio-badge ${priorityClass.split(" ")[1]}"><i class="fa-solid fa-circle-exclamation"></i>${esc(impact.priority)}</span>
          <div class="ih-main">
            <div class="ih-name">
              ${esc(impact.name)}
              <span class="kind-tag">${esc(impact.kind)}</span>
              <span class="status-tag st-open">open</span>
            </div>
            <div class="ih-reason">${esc(impact.reason)}</div>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" data-open-design><i class="fa-solid fa-highlighter"></i>設計書で見る</button>
          <i class="fa-solid fa-chevron-down ih-chevron"></i>
        </div>
        <div class="impact-body">
          <div class="impact-grid">
            <div class="detail-block">
              <div class="detail-label"><i class="fa-solid fa-route"></i>Graph Path</div>
              <div class="rel-path">${pathHtml(impact.path)}</div>
              <div class="detail-label" style="margin-top:14px;"><i class="fa-solid fa-quote-left"></i>Evidence</div>
              ${evidenceHtml}
            </div>
            <div class="detail-block">
              <div class="detail-label"><i class="fa-solid fa-list-check"></i>Required Actions (${esc(impact.impactType)})</div>
              <ul class="action-list">${(impact.requiredActions || []).map((action) => `<li>${esc(action)}</li>`).join("") || "<li>レビューして対応要否を判断</li>"}</ul>
              <div class="detail-label" style="margin-top:14px;"><i class="fa-solid fa-robot"></i>LLM Hypothesis</div>
              <div class="llm-judgement">
                <div class="lj-icon"><i class="fa-solid fa-robot"></i></div>
                <div><b>${esc(impact.llm.judgement)}</b> - ${esc(impact.llm.reason)}</div>
              </div>
            </div>
          </div>
        </div>
      </article>`;
  }

  function pathHtml(path) {
    const parts = Array.isArray(path) ? path : [path || ""];
    return parts.length
      ? parts.map((part, index) => index % 2 === 0
        ? `<span class="rel-node">${esc(part)}</span>`
        : `<span class="rel-edge">→ ${esc(part)} →</span>`).join("")
      : `<span class="rel-edge">graph path pending</span>`;
  }

  function renderDesignPicker() {
    const select = $("#design-doc-select");
    if (!select) return;
    const docs = state.design?.documents || [];
    select.innerHTML = docs.length
      ? docs.map((doc) => `<option value="${esc(doc.file)}">${esc(doc.title || doc.file)} (${doc.highlight_count || 0})</option>`).join("")
      : `<option value="">設計書データなし</option>`;
    if (state.selectedDocumentFile && docs.some((doc) => doc.file === state.selectedDocumentFile)) {
      select.value = state.selectedDocumentFile;
    } else if (docs[0]) {
      state.selectedDocumentFile = docs[0].file;
      select.value = docs[0].file;
    }
    select.onchange = () => {
      state.selectedDocumentFile = select.value;
      renderDesignViewer();
    };
  }

  function renderDesignViewer() {
    let panel = $("#design-reference-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "design-reference-panel";
      panel.className = "design-reference card card-pad";
      $("#impact-list")?.insertAdjacentElement("beforebegin", panel);
    }
    renderDesignPicker();
    const docs = state.design?.documents || [];
    const selected = docs.find((doc) => doc.file === state.selectedDocumentFile) || docs[0];
    state.selectedDocumentFile = selected?.file || "";
    if (!selected) {
      panel.innerHTML = `<div class="empty-state">設計書ビューに表示できる証跡がまだありません。まず設計書を取り込んでください。</div>`;
      updateModeSwitch();
      return;
    }
    panel.innerHTML = `
      <div class="design-header">
        <div>
          <div class="detail-label"><i class="fa-solid fa-highlighter"></i>Design reference</div>
          <h2>${esc(selected.title || selected.file)}</h2>
          <p>${esc(selected.file)} / evidence ${selected.evidence_count || 0} / highlight ${selected.highlight_count || 0}</p>
        </div>
        <div class="highlight-summary">${(state.selectedEvidenceIds || []).length} evidence selected</div>
      </div>
      <div class="design-doc-tabs">
        ${docs.map((doc) => `<button class="${doc.file === selected.file ? "active" : ""}" data-doc-file="${esc(doc.file)}">${esc(doc.title || doc.file)}<span>${doc.highlight_count || 0}</span></button>`).join("")}
      </div>
      <div class="design-content">
        ${designRowsHtml(selected)}
      </div>
    `;
    $$("[data-doc-file]", panel).forEach((btn) =>
      btn.addEventListener("click", () => {
        state.selectedDocumentFile = btn.dataset.docFile;
        const picker = $("#design-doc-select");
        if (picker) picker.value = state.selectedDocumentFile;
        renderDesignViewer();
      })
    );
    updateModeSwitch();
  }

  function designRowsHtml(doc) {
    if (doc.cells?.length) return dirtyCellHtml(doc.cells, doc.regions || []);
    if (doc.rows?.length) {
      return `<div class="source-lines">${doc.rows.map((row) => `
        <div class="source-line ${row.highlight ? "is-highlighted" : ""}">
          <span class="line-no">${esc(row.line)}</span>
          <code>${esc(row.text)}</code>
          ${evidenceChips(row.evidence_ids)}
        </div>
      `).join("")}</div>`;
    }
    if (doc.evidence?.length) {
      return doc.evidence.map((ev) => `
        <div class="evidence-quote ${state.selectedEvidenceIds.includes(ev.evidence_id) ? "is-highlighted" : ""}">
          <div class="eq-src">${esc(ev.evidence_id)} / ${esc(locationLabel(ev.source_location))}</div>
          <div class="eq-text">${esc(ev.quote)}</div>
        </div>
      `).join("");
    }
    return `<div class="empty-state">この設計書には表示可能な行またはセルがありません。</div>`;
  }

  function dirtyCellHtml(cells, regions) {
    const regionHtml = regions.length
      ? `<div class="region-strip">${regions.slice(0, 12).map((region) => `
          <span class="${region.highlight ? "active" : ""}">${esc(region.sheet_name)}!${esc(region.range)} ${esc(region.region_type)}</span>
        `).join("")}</div>`
      : "";
    return `${regionHtml}<div class="excel-grid">
      <table>
        <thead><tr><th>Sheet</th><th>Cell</th><th>Value</th><th>Evidence</th></tr></thead>
        <tbody>${cells.map((cell) => `
          <tr class="${cell.highlight ? "is-highlighted" : ""}">
            <td>${esc(cell.sheet_name)}</td>
            <td class="mono">${esc(cell.cell)}${cell.merged_range ? `<span class="cell-note">${esc(cell.merged_range)}</span>` : ""}</td>
            <td>${esc(cell.value)}</td>
            <td>${evidenceChips(cell.evidence_ids)}</td>
          </tr>
        `).join("")}</tbody>
      </table>
    </div>`;
  }

  function evidenceChips(ids) {
    return (ids || []).map((id) => `<span class="evidence-chip">${esc(id)}</span>`).join("");
  }

  function updateModeSwitch() {
    $$(".view-switch [data-design-mode]").forEach((btn) =>
      btn.classList.toggle("active", btn.dataset.designMode === state.designMode)
    );
    const list = $("#impact-list");
    const panel = $("#design-reference-panel");
    if (list) list.style.display = state.designMode === "impacts" ? "" : "none";
    if (panel) panel.style.display = state.designMode === "design" ? "" : "none";
  }

  async function runNaturalAnalysis() {
    const body = $("#change-natural-text")?.value.trim() || "";
    const designDocument = $("#design-doc-select")?.value || "";
    if (!body) {
      toast("変更内容を入力してください。");
      return;
    }
    const status = $("#workflow-status");
    try {
      const params = { body, design_document: designDocument };
      const preview = await api(
        `/api/projects/${state.project.project_id}/external-preview?action=analyze_text_llm_first&params=${encodeURIComponent(JSON.stringify(params))}`
      );
      let approved = false;
      if (preview.required) {
        const lines = (preview.transmissions || []).map((item) =>
          `${item.provider || "provider"} / ${item.model || "model"} / ${item.purpose || "analysis"} / ${item.item_count_label || item.item_count || "n"}件`
        );
        approved = window.confirm(`外部LLM送信が必要です。\n\n${lines.join("\n")}\n\nこのジョブを実行しますか？`);
        if (!approved) return;
      }
      if (status) status.textContent = "分析ジョブを投入しています...";
      const created = await api(`/api/projects/${state.project.project_id}/jobs`, {
        method: "POST",
        body: JSON.stringify({
          action: "analyze_text_llm_first",
          input_kind: "settings",
          external_approved: approved,
          params,
        }),
      });
      toast("LLM-first分析ジョブを開始しました。");
      await pollJob(created.job.job_id);
      await refreshAll();
      state.designMode = "impacts";
      updateModeSwitch();
      if (status) status.textContent = "分析が完了しました。一覧から候補を開くと設計書側がハイライトされます。";
    } catch (error) {
      if (status) status.textContent = `分析に失敗しました: ${error.message}`;
      toast("分析ジョブを開始できませんでした。");
    }
  }

  async function pollJob(jobId) {
    for (let i = 0; i < 120; i += 1) {
      const job = await api(`/api/projects/${state.project.project_id}/jobs/${jobId}`);
      if (TERMINAL.has(job.state)) {
        if (job.state !== "succeeded") throw new Error(job.error_summary || `job ${job.state}`);
        return job;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new Error("job timeout");
  }

  function renderAliases() {
    const list = $("#alias-list");
    if (!list) return;
    const candidates = state.aliases?.candidates || fallback.aliases || [];
    list.innerHTML = candidates.length ? candidates.map((candidate) => {
      const aliases = candidate.aliases || [candidate.a, candidate.b].filter(Boolean);
      const left = candidate.entity_a_id || candidate.target_id || aliases[0] || "";
      const right = candidate.entity_b_id || aliases[1] || "";
      return `
        <article class="alias-card">
          <div class="alias-pair">
            <span class="alias-term">${esc(left)}</span>
            <span class="alias-eq"><i class="fa-solid fa-arrows-left-right"></i></span>
            <span class="alias-term">${esc(right)}</span>
            <span class="judge-tag j-${esc(candidate.judgement || candidate.llm || "unsure")}">LLM: ${esc(candidate.judgement || candidate.llm || "unsure")}</span>
            <span class="status-tag st-${esc(candidate.status || "open")}">${esc(candidate.status || "pending")}</span>
          </div>
          <div class="evidence-quote">
            <div class="eq-src">${evidenceChips(candidate.evidence_ids || [])}</div>
            <div class="eq-text">${esc(candidate.llm_reason || candidate.reason || (candidate.evidence?.quote || ""))}</div>
          </div>
        </article>`;
    }).join("") : `<div class="card card-pad empty-state">Alias候補はまだありません。</div>`;
  }

  function renderJobs() {
    const tbody = $("#jobs-table tbody");
    if (!tbody) return;
    const jobs = state.jobs.length ? state.jobs : fallback.jobs || [];
    tbody.innerHTML = jobs.map((job) => `
      <tr>
        <td class="mono">${esc(job.job_id || job.id)}</td>
        <td><b>${esc(job.action || job.type)}</b></td>
        <td>${esc(job.input_kind || job.target || "")}</td>
        <td><span class="job-status js-${esc(job.state || job.status)}">${esc(job.state || job.status)}</span></td>
        <td>${job.external ? `<span class="ext-badge">外部LLM</span>` : `<span class="local-badge">local</span>`}</td>
        <td class="mono">${esc(job.created_at || job.time || "")}</td>
        <td class="mono">${esc(job.finished_at || job.duration || "")}</td>
      </tr>
    `).join("");
  }

  function renderGraph() {
    const svg = $("#graph-svg");
    if (!svg || !window.d3) return;
    const rawNodes = state.graph?.nodes?.map((item) => item.data) || fallback.graph?.nodes || [];
    const rawEdges = state.graph?.edges?.map((item) => item.data) || fallback.graph?.links || [];
    svg.innerHTML = "";
    const wrap = $(".graph-canvas-wrap");
    const width = wrap?.clientWidth || 900;
    const height = wrap?.clientHeight || 640;
    const nodes = rawNodes.map((node) => ({
      id: node.id,
      label: node.label || node.id,
      kind: node.kind || "reference",
      type: node.type || "",
    }));
    const links = rawEdges
      .filter((edge) => edge.source && edge.target)
      .map((edge) => ({
        source: edge.source,
        target: edge.target,
        label: edge.label || edge.rel || "",
        status: edge.status || "unconfirmed",
      }));
    const colors = { artifact: "#4f46e5", entity: "#0891b2", document: "#94a3b8", reference: "#64748b" };
    const status = { confirmed: "#10b981", unconfirmed: "#f59e0b", rejected: "#cbd5e1" };
    const root = d3.select(svg).attr("viewBox", [0, 0, width, height]);
    const group = root.append("g");
    root.call(d3.zoom().scaleExtent([0.3, 3]).on("zoom", (event) => group.attr("transform", event.transform)));
    const link = group.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", (item) => status[item.status] || "#cbd5e1")
      .attr("stroke-width", 1.6)
      .attr("stroke-dasharray", (item) => item.status === "confirmed" ? null : "6 3");
    const node = group.append("g").selectAll("g").data(nodes).join("g").attr("cursor", "pointer");
    node.append("circle")
      .attr("r", (item) => item.kind === "artifact" ? 17 : 13)
      .attr("fill", (item) => colors[item.kind] || colors.reference)
      .attr("stroke", "#fff")
      .attr("stroke-width", 2);
    node.append("text")
      .text((item) => item.label)
      .attr("y", 30)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("paint-order", "stroke")
      .attr("stroke", "#fbfcfd")
      .attr("stroke-width", 4);
    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((item) => item.id).distance(130))
      .force("charge", d3.forceManyBody().strength(-460))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(48))
      .on("tick", () => {
        link.attr("x1", (item) => item.source.x).attr("y1", (item) => item.source.y)
          .attr("x2", (item) => item.target.x).attr("y2", (item) => item.target.y);
        node.attr("transform", (item) => `translate(${item.x},${item.y})`);
      });
    node.on("click", (_event, item) => {
      const related = links.filter((edge) => (edge.source.id || edge.source) === item.id || (edge.target.id || edge.target) === item.id);
      $("#graph-side").innerHTML = `
        <div class="gs-node-head">
          <div class="gs-node-icon" style="background:${colors[item.kind] || colors.reference};"><i class="fa-solid fa-cube"></i></div>
          <div><div class="gs-node-name">${esc(item.label)}</div><div class="gs-node-id">${esc(item.id)}</div><span class="kind-tag">${esc(item.kind)} / ${esc(item.type)}</span></div>
        </div>
        <div class="detail-label">Relations (${related.length})</div>
        ${related.map((edge) => `<div class="gs-rel-item"><div class="gs-rel-head"><span class="rel-name">${esc(edge.label)}</span><span class="gs-rel-status rs-${esc(edge.status)}">${esc(edge.status)}</span></div></div>`).join("")}
      `;
    });
    $("#graph-search")?.addEventListener("input", (event) => {
      const q = event.target.value.toLowerCase();
      node.attr("opacity", (item) => !q || item.label.toLowerCase().includes(q) || item.id.toLowerCase().includes(q) ? 1 : 0.15);
    }, { once: true });
    $("#btn-graph-reset")?.addEventListener("click", () => renderGraph(), { once: true });
    state.graphInit = true;
  }

  function updateBadges() {
    const impacts = reportImpacts();
    const openImpacts = impacts.filter((item) => item.priority !== "hidden").length;
    const aliasCount = (state.aliases?.candidates || fallback.aliases || []).filter((item) => (item.status || "pending") === "pending").length;
    const impactBadge = $("#badge-impacts");
    const aliasBadge = $("#badge-aliases");
    if (impactBadge) {
      impactBadge.textContent = openImpacts;
      impactBadge.style.display = openImpacts ? "" : "none";
    }
    if (aliasBadge) {
      aliasBadge.textContent = aliasCount;
      aliasBadge.style.display = aliasCount ? "" : "none";
    }
  }

  function setupSearch() {
    $("#impact-search")?.addEventListener("input", (event) => {
      state.impactQuery = event.target.value;
      renderImpacts();
    });
  }

  async function start() {
    setupNavigation();
    ensureWorkflowPanel();
    setupSearch();
    renderAll();
    try {
      await loadSession();
      await resolveProject();
      await refreshAll();
    } catch (error) {
      toast(`実データAPIに接続できません: ${error.message}`);
      renderAll();
    }
    showView(new URL(window.location.href).pathname.split("/").pop() === "graph" ? "graph" : "dashboard");
  }

  document.addEventListener("DOMContentLoaded", start);
})();
