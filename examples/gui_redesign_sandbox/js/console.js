/* ============================================================
 * SpecImpact Console — Redesign Prototype Logic
 * ============================================================ */

(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  /* ---------- Toast ---------- */
  let toastTimer;
  function toast(msg) {
    $("#toast-msg").textContent = msg;
    $("#toast").classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 2400);
  }

  /* ---------- Navigation ---------- */
  function showView(name) {
    $$(".view").forEach((v) => v.classList.remove("active"));
    const view = $("#view-" + name);
    if (view) view.classList.add("active");
    $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === name));
    if (name === "graph") initGraph();
  }
  $$(".nav-item").forEach((btn) =>
    btn.addEventListener("click", () => showView(btn.dataset.view))
  );
  $$("[data-goto]").forEach((btn) =>
    btn.addEventListener("click", () => showView(btn.dataset.goto))
  );
  $("#btn-new-analyze").addEventListener("click", () => {
    showView("impacts");
    toast("プロトタイプのため、分析済みの結果を表示します");
  });
  /* デモ用のモック操作ボタン(設定変更・取り込みなど) */
  $$("[data-demo-toast]").forEach((btn) =>
    btn.addEventListener("click", () => toast(btn.dataset.demoToast))
  );

  /* ============================================================
   * Dashboard
   * ============================================================ */
  const STAT_DEFS = [
    { key: "documents", label: "Documents", icon: "fa-file-lines" },
    { key: "artifacts", label: "Artifacts", icon: "fa-cube" },
    { key: "entities", label: "Entities", icon: "fa-tag" },
    { key: "relations", label: "Relations", icon: "fa-link" },
    { key: "evidence", label: "Evidence", icon: "fa-quote-left" },
  ];
  $("#stat-grid").innerHTML = STAT_DEFS.map(
    (d) => `
    <div class="stat-card">
      <div class="sc-label"><i class="fa-solid ${d.icon}"></i>${d.label}</div>
      <div class="sc-value">${SI_DATA.stats[d.key]}</div>
    </div>`
  ).join("");

  /* Chart */
  const prioCounts = { must_review: 0, should_review: 0, may_review: 0 };
  SI_DATA.impacts.forEach((i) => prioCounts[i.priority]++);
  new Chart($("#impact-chart"), {
    type: "doughnut",
    data: {
      labels: ["must_review", "should_review", "may_review"],
      datasets: [{
        data: [prioCounts.must_review, prioCounts.should_review, prioCounts.may_review],
        backgroundColor: ["#dc2626", "#d97706", "#2563eb"],
        borderWidth: 2,
        borderColor: "#ffffff",
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: "64%",
      plugins: {
        legend: { position: "right", labels: { boxWidth: 10, boxHeight: 10, font: { size: 11, family: "'JetBrains Mono', monospace" } } },
      },
    },
  });

  /* ============================================================
   * Impact Review Board
   * ============================================================ */
  const PRIO_META = {
    must_review: { cls: "p-must", badge: "prio-must", icon: "fa-circle-exclamation" },
    should_review: { cls: "p-should", badge: "prio-should", icon: "fa-triangle-exclamation" },
    may_review: { cls: "p-may", badge: "prio-may", icon: "fa-circle-info" },
  };
  const KIND_ICONS = {
    SCREEN: "fa-display", API: "fa-plug", DB: "fa-database", CHECK: "fa-list-check",
    EXTERNAL_IF: "fa-arrow-right-arrow-left", TEST: "fa-vial", BATCH: "fa-clock", LOG: "fa-file-lines",
  };
  let impactFilter = "all";
  let impactQuery = "";

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function relPathHtml(path) {
    return path
      .map((seg, i) =>
        i % 2 === 0
          ? `<span class="rel-node">${esc(seg)}</span>`
          : `<span class="rel-edge">—${esc(seg)}→</span>`
      )
      .join("");
  }

  function evidenceHtml(evList) {
    if (!evList.length) {
      return `<div class="no-evidence"><i class="fa-solid fa-triangle-exclamation"></i>直接の evidence なし — graph 上の関連のみ。優先度は自動的に下げられています。</div>`;
    }
    return evList
      .map(
        (ev) => `
      <div class="evidence-quote">
        <div class="eq-src"><i class="fa-solid fa-file-excel"></i>${esc(ev.file)} · ${esc(ev.locator)}</div>
        <div class="eq-text">"${esc(ev.quote)}"</div>
      </div>`
      )
      .join("");
  }

  function renderImpactFilters() {
    const counts = { all: SI_DATA.impacts.length, must_review: 0, should_review: 0, may_review: 0 };
    SI_DATA.impacts.forEach((i) => counts[i.priority]++);
    const pills = [
      ["all", "すべて"],
      ["must_review", "must"],
      ["should_review", "should"],
      ["may_review", "may"],
    ];
    $("#impact-filters").innerHTML = pills
      .map(
        ([key, label]) =>
          `<button class="filter-pill ${impactFilter === key ? "active" : ""}" data-filter="${key}">${label}<span class="cnt">${counts[key]}</span></button>`
      )
      .join("");
    $$("#impact-filters .filter-pill").forEach((p) =>
      p.addEventListener("click", () => {
        impactFilter = p.dataset.filter;
        renderImpactFilters();
        renderImpacts();
      })
    );
  }

  function renderImpacts() {
    const list = $("#impact-list");
    const q = impactQuery.toLowerCase();
    const items = SI_DATA.impacts.filter((imp) => {
      if (impactFilter !== "all" && imp.priority !== impactFilter) return false;
      if (!q) return true;
      const hay = [imp.name, imp.reason, imp.artifactId, ...imp.evidence.map((e) => e.file)].join(" ").toLowerCase();
      return hay.includes(q);
    });

    if (!items.length) {
      list.innerHTML = `<div class="card card-pad" style="text-align:center;color:var(--c-text-3);">該当する候補がありません</div>`;
      return;
    }

    list.innerHTML = items
      .map((imp) => {
        const meta = PRIO_META[imp.priority];
        const confPct = Math.round(imp.llm.confidence * 100);
        return `
      <article class="impact-card ${meta.cls}" data-id="${imp.id}">
        <div class="impact-head" role="button" tabindex="0" aria-expanded="false">
          <span class="prio-badge ${meta.badge}"><i class="fa-solid ${meta.icon}"></i>${imp.priority}</span>
          <div class="ih-main">
            <div class="ih-name">
              ${esc(imp.name)}
              <span class="kind-tag"><i class="fa-solid ${KIND_ICONS[imp.kind] || "fa-cube"}"></i>${imp.kind}</span>
              <span class="status-tag st-${imp.status}">${imp.status}</span>
            </div>
            <div class="ih-reason">${esc(imp.reason)}</div>
          </div>
          <i class="fa-solid fa-chevron-down ih-chevron"></i>
        </div>
        <div class="impact-body">
          <div class="impact-grid">
            <div class="detail-block">
              <div class="detail-label"><i class="fa-solid fa-route"></i>Graph Path</div>
              <div class="rel-path">${relPathHtml(imp.path)}</div>
              <div class="detail-label" style="margin-top:14px;"><i class="fa-solid fa-quote-left"></i>Evidence</div>
              ${evidenceHtml(imp.evidence)}
            </div>
            <div class="detail-block">
              <div class="detail-label"><i class="fa-solid fa-list-check"></i>Required Actions(${esc(imp.impactType)})</div>
              <ul class="action-list">${imp.requiredActions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
              <div class="detail-label" style="margin-top:14px;"><i class="fa-solid fa-wand-magic-sparkles"></i>LLM Hypothesis(作業仮説・未確定)</div>
              <div class="llm-judgement">
                <div class="lj-icon"><i class="fa-solid fa-robot"></i></div>
                <div style="flex:1;">
                  <b>${imp.llm.judgement}</b> — ${esc(imp.llm.reason)}
                  <div class="conf-bar"><div style="width:${confPct}%;"></div></div>
                  <span style="font-size:11px;color:var(--c-text-3);font-family:var(--font-mono);">confidence ${confPct}%</span>
                </div>
              </div>
            </div>
          </div>
          <div class="impact-actions">
            <button class="btn btn-ok btn-sm" data-act="accepted"><i class="fa-solid fa-check"></i>修正対象にする</button>
            <button class="btn btn-ghost btn-sm" data-act="closed"><i class="fa-solid fa-flag-checkered"></i>対応完了</button>
            <button class="btn btn-danger btn-sm" data-act="dismissed"><i class="fa-solid fa-xmark"></i>対象外</button>
            <span class="hint">判断理由は impact decision として JSONL に記録されます</span>
          </div>
        </div>
      </article>`;
      })
      .join("");

    /* expand / collapse */
    $$(".impact-head", list).forEach((head) => {
      const open = () => {
        const card = head.closest(".impact-card");
        card.classList.toggle("open");
        head.setAttribute("aria-expanded", card.classList.contains("open"));
      };
      head.addEventListener("click", open);
      head.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });

    /* status actions */
    $$("[data-act]", list).forEach((btn) =>
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const card = btn.closest(".impact-card");
        const imp = SI_DATA.impacts.find((i) => i.id === card.dataset.id);
        imp.status = btn.dataset.act;
        renderImpacts();
        updateBadges();
        toast(`${imp.id} を ${btn.dataset.act} に更新しました(decision を記録)`);
      })
    );
  }

  $("#impact-search").addEventListener("input", (e) => {
    impactQuery = e.target.value;
    renderImpacts();
  });

  renderImpactFilters();
  renderImpacts();

  /* ============================================================
   * Graph Explorer (D3 force layout)
   * ============================================================ */
  const KIND_COLOR = { artifact: "#4f46e5", entity: "#0891b2", document: "#94a3b8" };
  const STATUS_COLOR = { confirmed: "#10b981", unconfirmed: "#f59e0b", rejected: "#cbd5e1" };
  const NODE_ICON = {
    SCREEN: "\uf108", API: "\uf1e6", DB: "\uf1c0", CHECK: "\uf0ae",
    EXTERNAL_IF: "\uf362", TEST: "\uf492", BATCH: "\uf017",
    "論理項目": "\uf02b", "API項目": "\uf02b", "DBカラム": "\uf02b", DOC: "\uf15c",
  };

  let graphInit = false;
  let simulation, svgRoot, gZoom, nodeSel, linkSel, linkLabelSel;
  let graphLinks = []; /* simulation にバインドされた link オブジェクト(状態更新はこちらを正とする) */
  const impactNodeIds = new Set([
    "ent.credit_limit", "ent.requestedCreditLimit", "ent.REQUESTED_CREDIT_LIMIT",
    "scr.card_entry.apply", "scr.card_entry.confirm", "chk.apply.credit_limit_max",
    "api.card_application.submit", "db.t_card_application", "if.credit_check.if301",
    "test.tc114.boundary", "batch.b220.monthly_agg",
  ]);

  function initGraph() {
    if (graphInit) return;
    graphInit = true;

    const wrap = $(".graph-canvas-wrap");
    const W = wrap.clientWidth || 800;
    const H = wrap.clientHeight || 600;

    const nodes = SI_DATA.graph.nodes.map((d) => ({ ...d }));
    const links = SI_DATA.graph.links.map((d) => ({ ...d }));
    graphLinks = links;

    svgRoot = d3.select("#graph-svg").attr("viewBox", [0, 0, W, H]);

    /* arrow markers per status */
    const defs = svgRoot.append("defs");
    Object.entries(STATUS_COLOR).forEach(([status, color]) => {
      defs.append("marker")
        .attr("id", "arrow-" + status)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 26).attr("refY", 0)
        .attr("markerWidth", 7).attr("markerHeight", 7)
        .attr("orient", "auto")
        .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", color);
    });

    gZoom = svgRoot.append("g");

    svgRoot.call(
      d3.zoom().scaleExtent([0.35, 3]).on("zoom", (e) => gZoom.attr("transform", e.transform))
    );

    linkSel = gZoom.append("g")
      .selectAll("line").data(links).join("line")
      .attr("stroke", (d) => STATUS_COLOR[d.status])
      .attr("stroke-width", (d) => (d.status === "confirmed" ? 2 : 1.5))
      .attr("stroke-dasharray", (d) => (d.status === "rejected" ? "4 4" : d.status === "unconfirmed" ? "6 3" : null))
      .attr("marker-end", (d) => `url(#arrow-${d.status})`)
      .attr("opacity", 0.85);

    linkLabelSel = gZoom.append("g")
      .selectAll("text").data(links).join("text")
      .text((d) => d.rel)
      .attr("font-family", "'JetBrains Mono', monospace")
      .attr("font-size", 8.5)
      .attr("fill", "#94a3b8")
      .attr("text-anchor", "middle")
      .attr("paint-order", "stroke")
      .attr("stroke", "#fbfcfd")
      .attr("stroke-width", 3);

    nodeSel = gZoom.append("g")
      .selectAll("g").data(nodes).join("g")
      .attr("cursor", "pointer")
      .call(
        d3.drag()
          .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      )
      .on("click", (e, d) => selectNode(d));

    nodeSel.append("circle")
      .attr("r", (d) => (d.kind === "artifact" ? 17 : 13))
      .attr("fill", (d) => KIND_COLOR[d.kind])
      .attr("stroke", "#ffffff")
      .attr("stroke-width", 2.5)
      .attr("class", "node-circle");

    nodeSel.append("text")
      .text((d) => NODE_ICON[d.type] || "\uf111")
      .attr("font-family", "'Font Awesome 6 Free'")
      .attr("font-weight", 900)
      .attr("font-size", (d) => (d.kind === "artifact" ? 12 : 10))
      .attr("fill", "#fff")
      .attr("text-anchor", "middle")
      .attr("dy", "0.36em");

    nodeSel.append("text")
      .text((d) => d.label)
      .attr("font-family", "'Noto Sans JP', sans-serif")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("fill", "#334155")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => (d.kind === "artifact" ? 32 : 28))
      .attr("paint-order", "stroke")
      .attr("stroke", "#fbfcfd")
      .attr("stroke-width", 4);

    simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(120).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-520))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collide", d3.forceCollide(46))
      .on("tick", () => {
        linkSel
          .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
          .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
        linkLabelSel
          .attr("x", (d) => (d.source.x + d.target.x) / 2)
          .attr("y", (d) => (d.source.y + d.target.y) / 2 - 5);
        nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
      });

    /* toolbar */
    $("#graph-search").addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      nodeSel.attr("opacity", (d) => (!q || d.label.toLowerCase().includes(q) || d.id.toLowerCase().includes(q) ? 1 : 0.15));
    });
    $("#btn-graph-impact").addEventListener("click", () => {
      nodeSel.attr("opacity", (d) => (impactNodeIds.has(d.id) ? 1 : 0.12));
      linkSel.attr("opacity", (d) => (impactNodeIds.has(d.source.id) && impactNodeIds.has(d.target.id) ? 1 : 0.08));
      linkLabelSel.attr("opacity", (d) => (impactNodeIds.has(d.source.id) && impactNodeIds.has(d.target.id) ? 1 : 0.06));
      toast("CHG-2026-0042 の影響パスを強調表示しています");
    });
    $("#btn-graph-reset").addEventListener("click", () => {
      nodeSel.attr("opacity", 1);
      linkSel.attr("opacity", 0.85);
      linkLabelSel.attr("opacity", 1);
      $("#graph-search").value = "";
    });
  }

  function selectNode(d) {
    nodeSel.select(".node-circle")
      .attr("stroke", (n) => (n.id === d.id ? "#f59e0b" : "#ffffff"))
      .attr("stroke-width", (n) => (n.id === d.id ? 4 : 2.5));

    const rels = graphLinks.filter((l) => (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id);
    const side = $("#graph-side");
    side.innerHTML = `
      <div class="gs-node-head">
        <div class="gs-node-icon" style="background:${KIND_COLOR[d.kind]};"><i class="fa-solid fa-cube"></i></div>
        <div>
          <div class="gs-node-name">${esc(d.label)}</div>
          <div class="gs-node-id">${esc(d.id)}</div>
          <span class="kind-tag" style="margin-top:5px;">${esc(d.kind)} · ${esc(d.type)}</span>
        </div>
      </div>
      <div class="detail-label"><i class="fa-solid fa-link"></i>Relations(${rels.length})</div>
      ${rels.map((l, idx) => {
        const srcId = l.source.id || l.source, tgtId = l.target.id || l.target;
        const peerId = srcId === d.id ? tgtId : srcId;
        const peer = SI_DATA.graph.nodes.find((n) => n.id === peerId);
        const dir = srcId === d.id ? "→" : "←";
        return `
        <div class="gs-rel-item" data-rel-idx="${graphLinks.indexOf(l)}">
          <div class="gs-rel-head">
            <span class="rel-name">${esc(l.rel)} ${dir}</span>
            <span class="peer">${esc(peer ? peer.label : peerId)}</span>
            <span class="gs-rel-status rs-${l.status}"><span class="rs-dot"></span>${l.status}</span>
          </div>
          <div class="evidence-quote" style="margin-top:8px;">
            <div class="eq-src"><i class="fa-solid fa-file-excel"></i>${esc(l.evidence.file)} · ${esc(l.evidence.locator)}</div>
            <div class="eq-text">"${esc(l.evidence.quote)}"</div>
          </div>
          <div class="gs-rel-actions">
            <button class="btn btn-ok btn-sm" data-set="confirmed"><i class="fa-solid fa-check"></i>confirm</button>
            <button class="btn btn-danger btn-sm" data-set="rejected"><i class="fa-solid fa-xmark"></i>reject</button>
          </div>
        </div>`;
      }).join("")}`;

    $$(".gs-rel-item [data-set]", side).forEach((btn) =>
      btn.addEventListener("click", () => {
        const idx = +btn.closest(".gs-rel-item").dataset.relIdx;
        graphLinks[idx].status = btn.dataset.set;
        if (SI_DATA.graph.links[idx]) SI_DATA.graph.links[idx].status = btn.dataset.set; /* 元データも同期 */
        linkSel
          .attr("stroke", (l) => STATUS_COLOR[l.status])
          .attr("stroke-dasharray", (l) => (l.status === "rejected" ? "4 4" : l.status === "unconfirmed" ? "6 3" : null))
          .attr("marker-end", (l) => `url(#arrow-${l.status})`);
        selectNode(d);
        toast(`relation を ${btn.dataset.set} に更新しました(queue 経由で保存)`);
      })
    );
  }

  /* ============================================================
   * Alias Review
   * ============================================================ */
  function renderAliases() {
    $("#alias-list").innerHTML = SI_DATA.aliases
      .map((al) => {
        const confPct = Math.round(al.confidence * 100);
        const done = al.status !== "pending";
        return `
      <article class="alias-card" data-id="${al.id}">
        <div class="alias-pair">
          <span class="alias-term">${esc(al.a)}</span>
          <span class="alias-eq"><i class="fa-solid fa-arrows-left-right"></i></span>
          <span class="alias-term">${esc(al.b)}</span>
          <span class="judge-tag j-${al.llm}">LLM: ${al.llm}</span>
          ${done ? `<span class="status-tag ${al.status === "confirmed" ? "st-accepted" : "st-dismissed"}">${al.status}</span>` : ""}
        </div>
        <div class="evidence-quote" style="margin-top:10px;">
          <div class="eq-src"><i class="fa-solid fa-file-excel"></i>${esc(al.evidence.file)} · ${esc(al.evidence.locator)}</div>
          <div class="eq-text">"${esc(al.evidence.quote)}"</div>
        </div>
        <ul class="alias-signals">${al.signals.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
        <div class="alias-footer">
          ${done ? "" : `
            <button class="btn btn-ok btn-sm" data-al="confirmed"><i class="fa-solid fa-check"></i>same として確定</button>
            <button class="btn btn-danger btn-sm" data-al="rejected"><i class="fa-solid fa-xmark"></i>却下</button>`}
          <span class="conf" style="margin-left:auto;">confidence ${confPct}%</span>
        </div>
      </article>`;
      })
      .join("");

    $$("#alias-list [data-al]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const al = SI_DATA.aliases.find((a) => a.id === btn.closest(".alias-card").dataset.id);
        al.status = btn.dataset.al;
        renderAliases();
        updateBadges();
        toast(`${al.id}: ${al.a} ↔ ${al.b} を ${btn.dataset.al} にしました`);
      })
    );
  }
  renderAliases();

  /* ============================================================
   * Jobs
   * ============================================================ */
  $("#jobs-table tbody").innerHTML = SI_DATA.jobs
    .map(
      (j) => `
    <tr>
      <td class="mono" style="font-size:12px;">${j.id}</td>
      <td><b>${esc(j.type)}</b></td>
      <td style="color:var(--c-text-2);">${esc(j.target)}</td>
      <td><span class="job-status js-${j.status}">${j.status}</span></td>
      <td>${j.external ? '<span class="ext-badge"><i class="fa-solid fa-cloud-arrow-up"></i> 承認済み</span>' : '<span class="local-badge"><i class="fa-solid fa-lock"></i> local</span>'}</td>
      <td class="mono" style="font-size:12px;">${j.time}</td>
      <td class="mono" style="font-size:12px;">${j.duration}</td>
    </tr>`
    )
    .join("");

  /* ---------- Badges ---------- */
  function updateBadges() {
    const openImpacts = SI_DATA.impacts.filter((i) => i.status === "open").length;
    const pendingAliases = SI_DATA.aliases.filter((a) => a.status === "pending").length;
    $("#badge-impacts").textContent = openImpacts;
    $("#badge-aliases").textContent = pendingAliases;
    $("#badge-impacts").style.display = openImpacts ? "" : "none";
    $("#badge-aliases").style.display = pendingAliases ? "" : "none";
  }
  updateBadges();
})();
